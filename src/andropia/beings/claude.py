"""Beings driven by the Anthropic Messages API.

A separate module from :mod:`adapter` because the Anthropic API is **not**
OpenAI-compatible, and pretending otherwise would fail in five different ways.
There is no ``/v1/chat/completions``; auth is ``x-api-key`` rather than a bearer
token; the system prompt is a top-level parameter instead of a message; the
streaming events are shaped differently; and on current models several
parameters an OpenAI client always sends are rejected outright.

Uses the official ``anthropic`` SDK rather than raw HTTP. It is an optional
dependency — ``pip install 'andropia[claude]'`` — so the simulation core and the
OpenAI-compatible path stay free of it, and a user running a local model never
installs it at all.

Four differences are load-bearing, and each one is a bug if missed:

**The system prompt is top-level.** ``prompt.messages`` puts the rules, the
persona and the being's memory in system-role messages, because that is what an
OpenAI-compatible endpoint wants. Here they are lifted into the ``system``
parameter. Passing them as ``messages`` entries would either be rejected or,
worse, quietly reinterpreted — mid-conversation system messages exist on some
models but cannot come first.

**Sampling parameters are rejected.** ``temperature`` returns a 400 on the
current Opus and Fable models. The ``Model`` dataclass carries one for the
OpenAI path; it is deliberately not forwarded here.

**Thinking is on by default, and ``max_tokens`` bounds thinking plus text.** A
being says a sentence or two, so the 160-token ceiling that suits the
OpenAI-compatible path would truncate mid-thought here. Hence a much larger
budget with low effort: the reply stays short because the prompt says so, not
because it ran out of room.

**Thinking stays enabled.** Disabling it is permitted at low effort, and would
be cheaper, but it can leak ``<thinking>`` tags into the visible response — and
this project's visible response is a being's spoken dialogue. A stray tag would
be spoken aloud by an avatar in front of a user. Low effort with thinking on
costs a little more and cannot do that.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .adapter import Brain, Reply
from .prompt import Message

#: Overrides the model id. Auth comes from the SDK's own resolution — an
#: ``ANTHROPIC_API_KEY``, an ``ANTHROPIC_AUTH_TOKEN``, or a logged-in profile —
#: so no credential is ever named, read or stored by this project.
ENV_MODEL = "ANDROPIA_CLAUDE_MODEL"

#: Selects this provider over the OpenAI-compatible one.
ENV_PROVIDER = "ANDROPIA_PROVIDER"

DEFAULT_MODEL = "claude-opus-5"


@dataclass(frozen=True, slots=True)
class Claude:
    """How to ask Claude. Deployment config, never part of the world."""

    name: str = DEFAULT_MODEL

    #: Room for thinking *and* the reply — the two share this budget. Far
    #: larger than the OpenAI-compatible default because thinking is on;
    #: brevity is enforced by the prompt, not by the ceiling.
    max_tokens: int = 1024

    #: A being's turn is a short conversational move, which is exactly what
    #: low effort is for. Raise it for beings meant to reason at length.
    effort: str = "low"

    timeout: float = 60.0

    #: Extra request fields, for settings this module does not model.
    extra: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_env(cls, **over) -> Claude:
        return cls(name=os.environ.get(ENV_MODEL, DEFAULT_MODEL), **over)


def configured() -> bool:
    """Whether to use Claude rather than an OpenAI-compatible endpoint.

    Explicit opt-in, or the presence of a credential the SDK would find anyway.
    Checked rather than assumed, so a machine with both an Anthropic key and a
    local vLLM server does what the operator asked.
    """
    if os.environ.get(ENV_PROVIDER, "").lower() == "claude":
        return True
    return bool(
        os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    )


def split(messages: Iterable[Message]) -> tuple[list[dict], list[dict]]:
    """Separate the system prompt from the conversation. Pure.

    Returns system blocks and message entries in the shapes the Messages API
    wants. Extracted as its own function because it is the piece most likely to
    be wrong and the easiest to test without a network call.

    A cache breakpoint goes on the **first** system block, which is the rules —
    identical for every being on every turn, and the largest stable span in the
    prompt. Marking a later block instead would key the cache to content that
    changes as a being accumulates memory, paying the write premium every turn
    for a read that rarely comes.
    """
    system: list[dict] = []
    chat: list[dict] = []

    for message in messages:
        if message.role == "system":
            system.append({"type": "text", "text": message.content})
        else:
            chat.append({"role": message.role, "content": message.content})

    if system:
        system[0] = {**system[0], "cache_control": {"type": "ephemeral"}}

    # The API requires at least one message, and it must not be an assistant
    # turn. A being with nothing in its situation report should not happen, but
    # a request that 400s is a worse way to find out.
    if not chat:
        chat = [{"role": "user", "content": "What do you do?"}]

    return system, chat


def brain(client, model: Claude) -> Brain:
    """A :data:`Brain` bound to one Claude model."""

    async def think(messages: Sequence[Message]) -> Reply:
        return await complete(client, model, messages)

    return think


async def complete(client, model: Claude, messages: Sequence[Message]) -> Reply:
    """Ask once. Failure is a value, exactly as on the OpenAI-compatible path.

    A being whose model is rate-limited or unreachable should stand there; it
    must not take down the tick loop every other being shares.
    """
    import anthropic

    system, chat = split(messages)

    try:
        response = await client.messages.create(
            model=model.name,
            max_tokens=model.max_tokens,
            system=system,
            messages=chat,
            # Adaptive rather than disabled: see the module docstring — a
            # leaked <thinking> tag here would be spoken by an avatar.
            thinking={"type": "adaptive"},
            output_config={"effort": model.effort},
            timeout=model.timeout,
            **model.extra,
        )
    except anthropic.NotFoundError as exc:
        return Reply(error=f"no such model {model.name!r}: {exc}")
    except anthropic.RateLimitError as exc:
        return Reply(error=f"rate limited: {exc}")
    except anthropic.APIStatusError as exc:
        return Reply(error=f"http {exc.status_code}: {exc}")
    except anthropic.APIConnectionError as exc:
        return Reply(error=f"unreachable: {exc}")
    except TypeError as exc:
        # The SDK raises TypeError, not an API error, when it cannot resolve a
        # credential — so without this the most likely misconfiguration of all
        # escapes the "failure is a value" contract, lands in the runner's
        # catch-all, and presents as beings that silently never speak.
        if "authentication" in str(exc).lower():
            return Reply(error="no credential — set ANTHROPIC_API_KEY")
        raise

    return _reply(response)


def _reply(response) -> Reply:
    """Read a Messages response, honouring the refusal stop reason.

    ``stop_reason == "refusal"`` arrives as a perfectly ordinary HTTP 200 with
    an empty or partial ``content``, so code that indexes the first block
    unconditionally breaks on it. Checked first, and reported as an error so the
    being simply says nothing rather than speaking half a sentence.
    """
    if getattr(response, "stop_reason", None) == "refusal":
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        return Reply(error=f"declined{f' ({category})' if category else ''}")

    # Text blocks only. Thinking blocks also appear in `content`, and their
    # text is empty by default — concatenating them blindly would be harmless
    # today and would start speaking reasoning aloud the moment someone turned
    # summaries on.
    said = "".join(
        block.text
        for block in getattr(response, "content", ())
        if getattr(block, "type", None) == "text"
    )
    return Reply(text=said)
