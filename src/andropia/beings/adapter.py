"""The model call. The only impure module in this package.

Speaks the OpenAI chat-completions wire format, because it is the one dialect
every serving stack understands: vLLM, llama.cpp's server, Ollama, LM Studio,
TGI, OpenAI, and anything else with a compatibility shim. So "bring your own
model" costs a base URL and, if the endpoint wants one, a key.

Deliberately hand-rolled over ``httpx`` rather than using a vendor SDK. The
surface actually needed here is one POST and a line-oriented stream, and an SDK
would bring a dependency, a release cadence and an opinion about retries in
exchange for code we would have to read anyway. It also keeps the shape of the
request visible, which matters when someone is pointing this at a local server
that implements two thirds of the spec.

Everything that can be decided without the network is decided elsewhere. This
module builds a request, reads a response, and turns failure into a value.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field

import httpx

from .prompt import Message

#: Where configuration comes from. Public, because the entry point prints them
#: and the README documents them — a name a user has to type is interface.
#: A key lives here and never in the world, so it cannot reach a snapshot.
ENV_KEY = "ANDROPIA_API_KEY"
ENV_BASE_URL = "ANDROPIA_BASE_URL"
ENV_MODEL = "ANDROPIA_MODEL"

#: A local vLLM or llama.cpp server on its usual port. Chosen as the default
#: because the project is aimed at people running their own models.
DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"


@dataclass(frozen=True, slots=True)
class Model:
    """Where to reach a model, and how to ask it.

    Not part of ``World``: it holds a credential, it is deployment config
    rather than simulation state, and a recorded run must never depend on it.
    """

    name: str = "local"
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    temperature: float = 0.8
    max_tokens: int = 160
    timeout: float = 30.0
    #: Sent verbatim in the request body. An escape hatch for the settings a
    #: particular server cares about — `top_k`, `repeat_penalty`, `min_p` —
    #: without this module needing to know which ones exist.
    extra: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_env(cls, **over) -> Model:
        """Build from the environment, so keys stay out of code and snapshots."""
        return cls(
            name=os.environ.get(ENV_MODEL, cls.name),
            base_url=os.environ.get(ENV_BASE_URL, cls.base_url).rstrip("/"),
            api_key=os.environ.get(ENV_KEY, ""),
            **over,
        )


@dataclass(frozen=True, slots=True)
class Reply:
    """What came back. A value, including when nothing did.

    Failure is returned rather than raised because a being whose model is slow,
    rate-limited or simply absent should stand there — not take down the tick
    loop that every other being shares.
    """

    text: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def body(model: Model, messages: Iterable[Message], *, stream: bool) -> dict:
    """The request body. Pure, so it can be asserted on without a server."""
    return {
        "model": model.name,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "temperature": model.temperature,
        "max_tokens": model.max_tokens,
        "stream": stream,
        **model.extra,
    }


def headers(model: Model) -> dict[str, str]:
    """Auth only when a key exists.

    A local server usually has none, and sending ``Authorization: Bearer``
    with an empty value makes some of them reject the request outright.
    """
    out = {"Content-Type": "application/json"}
    if model.api_key:
        out["Authorization"] = f"Bearer {model.api_key}"
    return out


async def complete(
    client: httpx.AsyncClient, model: Model, messages: Iterable[Message]
) -> Reply:
    """Ask once, wait for the whole answer.

    The client is passed in rather than created here so connections are pooled
    across beings and turns, and so a test can hand over a transport.
    """
    try:
        response = await client.post(
            f"{model.base_url}/chat/completions",
            json=body(model, messages, stream=False),
            headers=headers(model),
            timeout=model.timeout,
        )
    except httpx.HTTPError as exc:
        # Includes timeouts, DNS failures and connection refused — the ordinary
        # case of "the server is not running yet".
        return Reply(error=f"{type(exc).__name__}: {exc}")

    if response.status_code != 200:
        return Reply(error=f"http {response.status_code}: {_snippet(response.text)}")

    return _content(response.text)


async def stream(
    client: httpx.AsyncClient, model: Model, messages: Iterable[Message]
) -> AsyncIterator[str]:
    """Ask once, yielding text as it arrives.

    Streaming is what lets a being start speaking before it has finished
    thinking, which is most of the difference between a conversation and a
    series of announcements. The protocol parser is a fold precisely so the
    chunks this yields can be fed to it directly.

    Errors end the stream rather than raising, on the same reasoning as
    :class:`Reply`: one being's endpoint failing is not everyone's problem.
    """
    try:
        async with client.stream(
            "POST",
            f"{model.base_url}/chat/completions",
            json=body(model, messages, stream=True),
            headers=headers(model),
            timeout=model.timeout,
        ) as response:
            if response.status_code != 200:
                await response.aread()
                return

            async for line in response.aiter_lines():
                piece = _delta(line)
                if piece:
                    yield piece
    except httpx.HTTPError:
        return


# --------------------------------------------------------------------------
# wire format
# --------------------------------------------------------------------------


def _content(payload: str) -> Reply:
    """Pull the message text out of a non-streamed response.

    Tolerant on purpose. Local servers vary in which optional fields they send,
    and a missing ``finish_reason`` is not a reason to lose the reply — but a
    body shaped nothing like a completion is worth reporting rather than
    silently treating as silence.
    """
    try:
        data = json.loads(payload)
        choices = data["choices"]
        if not choices:
            return Reply()  # a legal, if unhelpful, answer
        return Reply(text=choices[0]["message"]["content"] or "")
    except (json.JSONDecodeError, KeyError, TypeError, IndexError) as exc:
        return Reply(error=f"unexpected response shape: {type(exc).__name__}")


def _delta(line: str) -> str:
    """One server-sent-events line to the text it carries, if any.

    Returns "" for keepalives, the terminating sentinel, and anything that does
    not parse. A stream is a poor place to be strict: the alternative to
    skipping a malformed frame is discarding a reply that is otherwise fine.
    """
    if not line.startswith("data:"):
        return ""

    payload = line[len("data:") :].strip()
    if not payload or payload == "[DONE]":
        return ""

    try:
        choices = json.loads(payload)["choices"]
        return choices[0]["delta"].get("content") or "" if choices else ""
    except (json.JSONDecodeError, KeyError, TypeError, IndexError):
        return ""


def _snippet(text: str, limit: int = 200) -> str:
    """Enough of an error body to diagnose, not enough to fill a log."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
