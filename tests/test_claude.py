"""Beings driven by the Anthropic Messages API.

The Anthropic API is not OpenAI-compatible, and every test here is about one of
the ways that matters. No key and no network.

Two layers. Most tests drive a fake client, which is how you assert that a
parameter the API would reject is genuinely *not* being sent. One test drives
the real SDK through a mock transport, so the SDK validates every parameter and
the assertions are about the bytes that actually go on the wire — a kwarg the
SDK would refuse fails there rather than on a user's first live call.
"""

from __future__ import annotations

import pytest

from andropia.beings import claude, perception, prompt, runner
from andropia.sim.types import Entity, Landmark, Speak, Vec3, World

pytest.importorskip("anthropic", reason="pip install 'andropia[claude]'")

MODEL = claude.Claude(name="claude-opus-5")


def a_world():
    return World(
        entities={
            "ava": Entity(id="ava", persona="You are curious."),
            "bob": Entity(id="bob", pos=Vec3(0.0, 0.0, 2.0)),
        },
        landmarks={"pond": Landmark("pond", Vec3(0.0, 0.0, 6.0), "the pond")},
    )


def messages_for(eid="ava"):
    world = a_world()
    return prompt.messages(world.entities[eid], perception.observe(world, eid))


# -- fakes -----------------------------------------------------------------


class Block:
    def __init__(self, type_, text=""):
        self.type = type_
        self.text = text


class Response:
    def __init__(self, content, stop_reason="end_turn", stop_details=None):
        self.content = content
        self.stop_reason = stop_reason
        self.stop_details = stop_details


class FakeMessages:
    def __init__(self, response=None, raises=None):
        self.response = response
        self.raises = raises
        self.seen: dict = {}

    async def create(self, **kwargs):
        self.seen = kwargs
        if self.raises is not None:
            raise self.raises
        return self.response


class FakeClient:
    def __init__(self, response=None, raises=None):
        self.messages = FakeMessages(response, raises)


def text(s):
    return FakeClient(Response([Block("text", s)]))


# -- the system prompt is a top-level parameter ----------------------------


def test_system_messages_are_lifted_out_of_the_conversation():
    """The single biggest structural difference.

    `prompt.messages` emits system-role entries because that is what an
    OpenAI-compatible endpoint wants. Here they belong in the top-level
    `system` parameter — the Messages API will not take them as conversation,
    and a mid-conversation system message cannot come first even on the models
    that support one.
    """
    system, chat = claude.split(messages_for())

    assert system, "the rules and persona never made it into `system`"
    assert all(entry["role"] != "system" for entry in chat)
    assert any("You are curious." in block["text"] for block in system)


def test_the_situation_stays_in_the_conversation():
    _, chat = claude.split(messages_for())
    assert chat[-1]["role"] == "user"
    assert "What do you do?" in chat[-1]["content"]


def test_nothing_is_lost_in_the_split():
    original = messages_for()
    system, chat = claude.split(original)
    assert len(system) + len(chat) == len(original)


def test_a_cache_breakpoint_goes_on_the_stable_rules():
    """The rules are identical for every being on every turn, which makes them
    the one span worth caching. Marking a later block would key the cache to
    content that grows as a being accumulates memory."""
    system, _ = claude.split(messages_for())

    assert system[0].get("cache_control") == {"type": "ephemeral"}
    assert prompt.RULES in system[0]["text"]
    assert not any("cache_control" in block for block in system[1:])


def test_a_conversation_is_never_empty():
    # The API requires at least one message; a 400 is a poor way to discover
    # that a situation report came back blank.
    _, chat = claude.split([])
    assert chat and chat[0]["role"] == "user"


# -- parameters the API rejects --------------------------------------------


async def test_temperature_is_never_sent():
    """It returns a 400 on the current Opus and Fable models.

    The `Model` dataclass carries a temperature for the OpenAI-compatible path,
    so the risk is real: forwarding the config wholesale would break every
    request against Anthropic.
    """
    client = text("hi")
    await claude.complete(client, MODEL, messages_for())

    for banned in ("temperature", "top_p", "top_k"):
        assert banned not in client.messages.seen, banned


async def test_thinking_is_enabled_rather_than_disabled():
    """Disabling it is cheaper and permitted at low effort, but it can leak
    `<thinking>` tags into the visible response — and in this project the
    visible response is a being's spoken dialogue."""
    client = text("hi")
    await claude.complete(client, MODEL, messages_for())

    assert client.messages.seen["thinking"] == {"type": "adaptive"}


async def test_effort_is_sent_inside_output_config():
    # Top-level `effort` is not a parameter; it lives in output_config.
    client = text("hi")
    await claude.complete(client, MODEL, messages_for())

    assert client.messages.seen["output_config"] == {"effort": "low"}
    assert "effort" not in client.messages.seen


async def test_max_tokens_leaves_room_for_thinking():
    """`max_tokens` bounds thinking *and* text on current models, so the
    160-token ceiling that suits the OpenAI path would truncate mid-thought."""
    assert MODEL.max_tokens >= 512

    client = text("hi")
    await claude.complete(client, MODEL, messages_for())
    assert client.messages.seen["max_tokens"] == MODEL.max_tokens


async def test_the_model_id_carries_no_date_suffix():
    # Appending one 404s; the published aliases are complete as written.
    assert claude.DEFAULT_MODEL == "claude-opus-5"
    client = text("hi")
    await claude.complete(client, MODEL, messages_for())
    assert client.messages.seen["model"] == "claude-opus-5"


# -- reading the response --------------------------------------------------


async def test_text_blocks_become_the_reply():
    client = FakeClient(Response([Block("text", "[happy]Hello.")]))
    reply = await claude.complete(client, MODEL, messages_for())
    assert reply.ok and reply.text == "[happy]Hello."


async def test_thinking_blocks_are_not_spoken():
    """Thinking blocks share `content` with text blocks. Concatenating
    everything is harmless while their text is empty, and starts speaking
    reasoning aloud the moment someone turns summaries on."""
    client = FakeClient(
        Response([Block("thinking", "I should greet them"), Block("text", "Hello.")])
    )
    reply = await claude.complete(client, MODEL, messages_for())
    assert reply.text == "Hello."


async def test_a_refusal_is_an_error_not_content():
    """It arrives as an ordinary HTTP 200 with empty or partial content, so
    code that reads the first block unconditionally breaks on it."""

    class Details:
        category = "cyber"

    client = FakeClient(Response([], stop_reason="refusal", stop_details=Details()))
    reply = await claude.complete(client, MODEL, messages_for())

    assert not reply.ok
    assert "cyber" in reply.error


async def test_a_refusal_with_no_category_is_still_an_error():
    client = FakeClient(Response([], stop_reason="refusal", stop_details=None))
    reply = await claude.complete(client, MODEL, messages_for())
    assert not reply.ok


async def test_an_empty_response_is_silence_not_an_error():
    client = FakeClient(Response([]))
    reply = await claude.complete(client, MODEL, messages_for())
    assert reply.ok and reply.text == ""


# -- failure is a value ----------------------------------------------------


async def test_a_rate_limit_becomes_a_value():
    """A being whose model is throttled stands there; it does not take down the
    tick loop every other being shares."""
    import anthropic
    import httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, request=request, json={"error": {}})
    raised = anthropic.RateLimitError("slow down", response=response, body=None)

    reply = await claude.complete(FakeClient(raises=raised), MODEL, messages_for())
    assert not reply.ok and "rate limited" in reply.error


async def test_an_unreachable_endpoint_becomes_a_value():
    import anthropic
    import httpx

    raised = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    reply = await claude.complete(FakeClient(raises=raised), MODEL, messages_for())
    assert not reply.ok and "unreachable" in reply.error


async def test_a_bad_model_id_says_so():
    import anthropic
    import httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(404, request=request, json={"error": {}})
    raised = anthropic.NotFoundError("nope", response=response, body=None)

    reply = await claude.complete(FakeClient(raises=raised), MODEL, messages_for())
    assert not reply.ok and "claude-opus-5" in reply.error


# -- what actually goes on the wire ----------------------------------------


async def test_the_real_sdk_accepts_the_request_and_sends_the_right_thing():
    """The strongest test here, and the one the fake client cannot give.

    Driving the genuine SDK through a mock transport means the SDK itself
    validates every parameter — so a kwarg it would reject, or a shape it would
    serialise differently, fails here rather than on the user's first live call.
    """
    import json

    import anthropic
    import httpx

    seen: dict = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "content": [{"type": "text", "text": "[happy]Hello."}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    client = anthropic.AsyncAnthropic(
        api_key="sk-test",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    reply = await claude.complete(client, MODEL, messages_for())
    assert reply.ok and reply.text == "[happy]Hello."

    # The Messages API, not chat completions — pointing an OpenAI-compatible
    # client at Anthropic would just 404 here.
    assert seen["url"].endswith("/v1/messages")

    # x-api-key, not a bearer token.
    assert "x-api-key" in seen["headers"]
    assert "authorization" not in seen["headers"]
    assert seen["headers"]["anthropic-version"] == "2023-06-01"

    body = seen["body"]
    assert "temperature" not in body  # would 400 on current models
    assert body["system"] and "cache_control" in body["system"][0]
    assert [m["role"] for m in body["messages"]] == ["user"]


async def test_a_missing_credential_is_a_value_not_a_traceback():
    """The most likely misconfiguration of all, and it escapes the API-error
    handlers: the SDK raises TypeError, not an anthropic exception, when it
    cannot resolve a credential. Without this it lands in the runner's catch-all
    and presents as beings that silently never speak."""
    import anthropic

    reply = await claude.complete(
        anthropic.AsyncAnthropic(api_key=None, auth_token=None),
        MODEL,
        messages_for(),
    )
    assert not reply.ok
    assert "credential" in reply.error


async def test_an_unrelated_type_error_still_raises():
    # The guard is narrow on purpose — swallowing every TypeError would hide
    # real bugs in prompt assembly behind a being that just goes quiet.
    class Broken:
        class messages:
            @staticmethod
            async def create(**kwargs):
                raise TypeError("something else entirely")

    with pytest.raises(TypeError):
        await claude.complete(Broken(), MODEL, messages_for())


# -- provider selection ----------------------------------------------------


def test_an_api_key_selects_claude(monkeypatch):
    monkeypatch.delenv(claude.ENV_PROVIDER, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert claude.configured() is True


def test_nothing_configured_selects_nothing(monkeypatch):
    for var in (claude.ENV_PROVIDER, "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    assert claude.configured() is False


def test_the_provider_can_be_named_without_a_key_in_the_environment(monkeypatch):
    # A logged-in profile is a credential the SDK finds on its own; this project
    # never reads it, so an explicit opt-in has to be possible.
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(claude.ENV_PROVIDER, "claude")
    assert claude.configured() is True


# -- end to end through the runner ----------------------------------------


async def test_a_whole_turn_runs_through_the_runner():
    """The point of the brain abstraction: the runner drives Claude without
    knowing it is Claude."""
    client = FakeClient(Response([Block("text", "[happy]Hello, bob! [motion:wave]")]))
    mind = runner.Mind("ava", claude.brain(client, MODEL))

    intents, error = await runner.think(a_world(), mind)

    assert error is None
    assert any(isinstance(i, Speak) and "Hello, bob!" in i.text for i in intents)
    assert all(i.entity == "ava" for i in intents)


async def test_a_refused_turn_yields_no_intents():
    client = FakeClient(Response([], stop_reason="refusal"))
    mind = runner.Mind("ava", claude.brain(client, MODEL))

    intents, error = await runner.think(a_world(), mind)
    assert intents == () and error is not None
