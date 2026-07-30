"""The agent runner and the model adapter.

No model, no key and no socket. The adapter is exercised through httpx's mock
transport, which means the wire-format handling — including every way a local
server can disappoint — is tested rather than hoped about.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from andropia.beings import adapter, runner
from andropia.beings.adapter import Model
from andropia.beings.prompt import Message
from andropia.beings.runner import Cast, Mind
from andropia.sim.step import step
from andropia.sim.types import (
    Entity,
    Landmark,
    Remember,
    Speak,
    Speech,
    Utterance,
    Vec3,
    World,
)

MODEL = Model(name="test", base_url="http://model.invalid/v1")


def a_world(tick=0, **over):
    return World(
        tick=tick,
        entities={
            "ava": Entity(id="ava", persona="You are curious."),
            "bob": Entity(id="bob", pos=Vec3(0.0, 0.0, 2.0)),
        },
        landmarks={"pond": Landmark("pond", Vec3(0.0, 0.0, 6.0), "the pond")},
        **over,
    )


def a_cast_world(tick=0):
    """Three beings, all present. `wants_turn` refuses a being that is not in
    the world, so a scheduling test needs every id it schedules."""
    return World(
        tick=tick,
        entities={
            eid: Entity(id=eid, pos=Vec3(float(i), 0.0, 0.0))
            for i, eid in enumerate(("ava", "claude", "mistral"))
        },
    )


def transport(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def mind(eid, client, model=None):
    """A Mind wired to an OpenAI-compatible endpoint.

    Minds hold a brain rather than a model config, so the runner never learns
    which provider answered — the provider modules own that difference.
    """
    return Mind(eid, adapter.brain(client, model or MODEL))


def completion(text):
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    return handler


# -- arbitration -----------------------------------------------------------


def test_a_being_does_not_think_twice_in_quick_succession():
    world = a_world(tick=10)
    assert runner.wants_turn(world, "ava", since=10) is False
    assert runner.wants_turn(world, "ava", since=9) is False


def test_a_being_stirs_on_its_own_in_a_quiet_world():
    # Otherwise a world with nothing happening freezes into a tableau.
    world = a_world(tick=runner.IDLE_THINK_TICKS + 1)
    assert runner.wants_turn(world, "ava", since=0) is True


def test_a_being_thinks_when_it_has_heard_something():
    world = a_world(
        tick=runner.MIN_THINK_TICKS + 5,
        transcript=(Utterance(tick=runner.MIN_THINK_TICKS, speaker="bob", text="hi"),),
    )
    assert runner.wants_turn(world, "ava", since=1) is True


def test_a_being_is_not_prompted_by_its_own_voice():
    # Or it answers itself forever.
    world = a_world(
        tick=runner.MIN_THINK_TICKS + 5,
        transcript=(Utterance(tick=runner.MIN_THINK_TICKS, speaker="ava", text="hi"),),
    )
    assert runner.wants_turn(world, "ava", since=1) is False


def test_nobody_thinks_while_someone_else_is_speaking():
    """The whole of turn-taking.

    Without this every being replies to the same line at once, and the
    transcript reads as three people talking over each other — the
    characteristic failure of multi-agent chat.
    """
    world = a_world(tick=runner.IDLE_THINK_TICKS + 1)
    talking = Entity(
        id="bob",
        pos=Vec3(0.0, 0.0, 2.0),
        speech=Speech(text="I am mid-sentence", start_tick=0, duration_ticks=40),
    )
    world = World(
        tick=world.tick,
        entities={"ava": world.entities["ava"], "bob": talking},
    )
    assert runner.wants_turn(world, "ava", since=0) is False
    # The speaker itself is not blocked by its own voice.
    assert runner.wants_turn(world, "bob", since=0) is True


def test_a_being_not_in_the_world_never_wants_a_turn():
    assert runner.wants_turn(a_world(tick=999), "ghost", since=0) is False


def test_heard_since_is_bounded_by_the_last_thought():
    # An old line must not keep re-triggering turns forever.
    world = a_world(
        tick=runner.IDLE_THINK_TICKS - 1,
        transcript=(Utterance(tick=5, speaker="bob", text="ancient"),),
    )
    assert runner.wants_turn(world, "ava", since=100) is False


def test_nobody_is_starved_by_the_alphabet():
    """The regression for a being that spoke once in seventy seconds.

    Only one being thinks at a time, so how the one is chosen decides who gets
    heard. Taking the first eligible being in id order gives `ava` and `claude`
    strict priority and `mistral` only ever speaks when neither wants a turn —
    which reads as a sulking personality rather than a scheduler bug.
    """
    cast = Cast(minds=dict.fromkeys(("ava", "claude", "mistral")))
    heard: list[str] = []
    tick = runner.IDLE_THINK_TICKS + 1

    # Advancing a full idle interval per round, because with an empty
    # transcript that is the only thing that makes a being due — nothing has
    # been said for it to react to. A shorter step correctly yields nobody.
    for _ in range(9):
        world = a_cast_world(tick=tick)
        eid = runner.next_speaker(cast, world)
        assert eid is not None, f"nobody was due at tick {tick} after {heard}"
        heard.append(eid)
        cast.last_thought[eid] = tick
        tick += runner.IDLE_THINK_TICKS + 1

    # Every being spoke, and roughly evenly — not one of them three times
    # while another never got a word in.
    assert set(heard) == {"ava", "claude", "mistral"}
    assert all(heard.count(eid) == 3 for eid in set(heard)), heard


def test_an_active_conversation_does_not_starve_anyone():
    """The condition the bug actually needed, and the reason the test above is
    not enough on its own.

    With an empty transcript nobody is due twice running, so any scheduler
    trivially round-robins and the alphabetical version looks fine. Starvation
    needs a *live* conversation: each utterance keeps every other being due, so
    several are eligible every round and id order becomes strict priority.
    Simulated over thirty rounds, the shipped version gave `ava` and `claude`
    fifteen turns each and `mistral` none.
    """
    beings = ("ava", "claude", "mistral")
    cast = Cast(minds=dict.fromkeys(beings))
    transcript: tuple[Utterance, ...] = ()
    heard: list[str] = []
    tick = runner.IDLE_THINK_TICKS + 1

    for _ in range(30):
        world = World(
            tick=tick,
            entities={
                eid: Entity(id=eid, pos=Vec3(float(i), 0.0, 0.0))
                for i, eid in enumerate(beings)
            },
            transcript=transcript,
        )
        eid = runner.next_speaker(cast, world)
        if eid is not None:
            heard.append(eid)
            cast.last_thought[eid] = tick
            # Speaking is what keeps the others due, and so what exposes the
            # bug: without this the transcript never grows and nobody is.
            transcript = (*transcript, Utterance(tick=tick, speaker=eid, text="..."))
        tick += runner.MIN_THINK_TICKS + 1

    counts = {eid: heard.count(eid) for eid in beings}
    assert all(counts.values()), f"starved: {counts}"
    # Within one turn of even. The old version was 15 / 15 / 0.
    assert max(counts.values()) - min(counts.values()) <= 1, counts


def test_the_longest_waiting_being_goes_next():
    cast = Cast(minds=dict.fromkeys(("ava", "claude", "mistral")))
    world = a_cast_world(tick=1000)
    cast.last_thought.update({"ava": 900, "claude": 500, "mistral": 800})

    assert runner.next_speaker(cast, world) == "claude"


def test_turn_choice_is_deterministic_when_beings_tie():
    # Same world and same cast must give the same answer, or a replay of the
    # scheduler diverges from the run it recorded.
    cast = Cast(minds=dict.fromkeys(("mistral", "ava", "claude")))
    world = a_cast_world(tick=runner.IDLE_THINK_TICKS + 1)
    assert runner.next_speaker(cast, world) == runner.next_speaker(cast, world) == "ava"


def test_nobody_speaks_when_nobody_is_due():
    cast = Cast(minds=dict.fromkeys(("ava", "claude")))
    world = a_cast_world(tick=10)
    cast.last_thought.update({"ava": 10, "claude": 10})
    assert runner.next_speaker(cast, world) is None


def test_a_failing_being_waits_longer_each_time():
    """Written during a real outage.

    The API returned 500s and 529s for three minutes. Each being retried the
    moment MIN_THINK_TICKS elapsed, so the world issued a request every second
    and a half throughout — which helps nobody, and is billed on the failures
    that are billed.
    """
    cast = Cast(minds=dict.fromkeys(("ava",)))
    world = a_cast_world(tick=runner.IDLE_THINK_TICKS + 1)
    cast.last_thought["ava"] = 0

    assert runner.next_speaker(cast, world) == "ava"  # no failures yet

    cast.misses["ava"] = 3
    assert runner.next_speaker(cast, world) is None  # inside the backoff

    later = a_cast_world(tick=runner.backoff(3) + 1)
    cast.last_thought["ava"] = 0
    assert runner.next_speaker(cast, later) == "ava"  # past it


def test_backoff_grows_and_then_stops_growing():
    delays = [runner.backoff(n) for n in range(len(runner.BACKOFF_TICKS) + 4)]
    assert delays[0] == 0  # a first failure costs nothing extra
    assert delays == sorted(delays)  # never shrinks
    # Capped: a being that backs off forever never comes back, and an outage
    # ends eventually.
    assert delays[-1] == delays[len(runner.BACKOFF_TICKS) - 1]


def test_a_healthy_being_is_not_delayed_by_a_broken_one():
    # One endpoint failing must not quiet the whole world.
    cast = Cast(minds=dict.fromkeys(("ava", "claude")))
    cast.misses["ava"] = 5
    cast.last_thought.update({"ava": 0, "claude": 0})
    world = a_cast_world(tick=runner.IDLE_THINK_TICKS + 1)

    assert runner.next_speaker(cast, world) == "claude"


async def test_a_successful_turn_clears_the_backoff():
    world = a_world(tick=runner.IDLE_THINK_TICKS + 1)
    cast = Cast()
    proposed: list = []

    async with transport(completion("[happy]Hi.")) as client:
        cast.minds["ava"] = mind("ava", client)
        cast.misses["ava"] = 4
        await runner._turn(world, cast.minds["ava"], cast, proposed.append)

    assert "ava" not in cast.misses
    assert "ava" not in cast.trouble


async def test_a_failed_turn_counts_toward_the_backoff():
    world = a_world(tick=runner.IDLE_THINK_TICKS + 1)
    cast = Cast()

    def handler(request):
        return httpx.Response(529, text="Overloaded")

    async with transport(handler) as client:
        cast.minds["ava"] = mind("ava", client)
        for expected in (1, 2, 3):
            await runner._turn(world, cast.minds["ava"], cast, lambda _: None)
            assert cast.misses["ava"] == expected


def test_a_goto_nowhere_is_reported_rather_than_silently_dropped():
    """Beings ask to walk to places the world does not have.

    A live run had them announce "I'll walk the rim", "past the rock", "the
    flat" — none of which are landmarks, so `step` discards the intent and the
    being stands there having announced a journey. From outside that is
    identical to a being that never emitted a tag at all, and the two have
    completely different fixes.
    """
    from andropia.sim.types import Goto

    world = a_world()
    assert runner.unresolved(world, (Goto(entity="ava", target="the rim"),)) == "the rim"
    assert runner.unresolved(world, (Goto(entity="ava", target="pond"),)) is None


def test_a_reachable_goto_reports_nothing():
    from andropia.sim.types import DoGesture, Speak

    world = a_world()
    intents = (Speak(entity="ava", text="hi"), DoGesture(entity="ava", motion="nod"))
    assert runner.unresolved(world, intents) is None


async def test_an_unreachable_place_is_recorded_against_the_being():
    world = a_world(tick=runner.IDLE_THINK_TICKS + 1)
    cast = Cast()

    async with transport(completion("Off to the rim.[goto:the_rim]")) as client:
        cast.minds["ava"] = mind("ava", client)
        await runner._turn(world, cast.minds["ava"], cast, lambda _: None)

    assert cast.unreachable["ava"] == "the_rim"


async def test_reaching_somewhere_real_clears_the_record():
    world = a_world(tick=runner.IDLE_THINK_TICKS + 1)
    cast = Cast()
    cast.unreachable["ava"] = "the_rim"

    async with transport(completion("[goto:pond]")) as client:
        cast.minds["ava"] = mind("ava", client)
        await runner._turn(world, cast.minds["ava"], cast, lambda _: None)

    assert "ava" not in cast.unreachable


# -- memory ----------------------------------------------------------------


def test_a_turn_that_said_something_is_remembered():
    note = runner.turn_memory((Speak(entity="ava", text="Hello there."),))
    assert "Hello there." in note


def test_a_silent_turn_is_not_remembered():
    from andropia.sim.types import DoGesture

    assert runner.turn_memory((DoGesture(entity="ava", motion="nod"),)) == ""


def test_a_long_utterance_is_trimmed():
    note = runner.turn_memory((Speak(entity="ava", text="x" * 500),), limit=40)
    assert len(note) < 80
    assert note.endswith('…"')


# -- adapter: request shape ------------------------------------------------


def test_request_body_carries_messages_and_settings():
    body = adapter.body(MODEL, [Message("system", "rules")], stream=False)
    assert body["model"] == "test"
    assert body["messages"] == [{"role": "system", "content": "rules"}]
    assert body["stream"] is False


def test_extra_settings_pass_straight_through():
    # So a server's own knobs work without this module knowing they exist.
    model = Model(extra={"top_k": 40, "min_p": 0.05})
    assert adapter.body(model, [], stream=False)["top_k"] == 40


def test_no_auth_header_without_a_key():
    """A local server usually has no key, and some reject an empty Bearer."""
    assert "Authorization" not in adapter.headers(Model())
    assert adapter.headers(Model(api_key="sk-x"))["Authorization"] == "Bearer sk-x"


def test_api_key_never_appears_in_the_request_body():
    body = adapter.body(Model(api_key="sk-secret"), [], stream=False)
    assert "sk-secret" not in json.dumps(body)


# -- adapter: responses ----------------------------------------------------


async def test_a_normal_completion_is_returned():
    async with transport(completion("[happy]Hello!")) as client:
        reply = await adapter.complete(client, MODEL, [])
    assert reply.ok
    assert reply.text == "[happy]Hello!"


async def test_an_http_error_becomes_a_value_not_an_exception():
    """A being whose endpoint is unhappy should stand there, not take down the
    tick loop every other being shares."""

    def handler(request):
        return httpx.Response(429, text="rate limited")

    async with transport(handler) as client:
        reply = await adapter.complete(client, MODEL, [])
    assert not reply.ok
    assert "429" in reply.error


async def test_a_connection_failure_becomes_a_value():
    # The ordinary case of "the model server is not running yet".
    def handler(request):
        raise httpx.ConnectError("refused")

    async with transport(handler) as client:
        reply = await adapter.complete(client, MODEL, [])
    assert not reply.ok
    assert "ConnectError" in reply.error


async def test_a_response_of_the_wrong_shape_is_reported():
    def handler(request):
        return httpx.Response(200, json={"unexpected": True})

    async with transport(handler) as client:
        reply = await adapter.complete(client, MODEL, [])
    assert not reply.ok


async def test_an_empty_choices_list_is_silence_not_an_error():
    # Legal, if unhelpful. A being simply says nothing.
    def handler(request):
        return httpx.Response(200, json={"choices": []})

    async with transport(handler) as client:
        reply = await adapter.complete(client, MODEL, [])
    assert reply.ok
    assert reply.text == ""


async def test_a_null_content_is_treated_as_silence():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})

    async with transport(handler) as client:
        reply = await adapter.complete(client, MODEL, [])
    assert reply.ok and reply.text == ""


# -- adapter: streaming ----------------------------------------------------


def sse(*chunks):
    lines = []
    for c in chunks:
        lines.append(
            "data: " + json.dumps({"choices": [{"delta": {"content": c}}]}) + "\n\n"
        )
    lines.append("data: [DONE]\n\n")
    return "".join(lines)


async def test_streaming_yields_text_in_order():
    def handler(request):
        return httpx.Response(200, text=sse("Hel", "lo ", "there"))

    async with transport(handler) as client:
        got = [piece async for piece in adapter.stream(client, MODEL, [])]
    assert "".join(got) == "Hello there"


async def test_streaming_skips_keepalives_and_junk():
    """A stream is a poor place to be strict: the alternative to skipping a
    malformed frame is discarding a reply that is otherwise fine."""
    body = "\n".join(
        [
            ": keepalive",
            "",
            "data: not json at all",
            'data: {"choices": []}',
            'data: {"choices": [{"delta": {}}]}',
            "data: " + json.dumps({"choices": [{"delta": {"content": "real"}}]}),
            "data: [DONE]",
        ]
    )

    def handler(request):
        return httpx.Response(200, text=body)

    async with transport(handler) as client:
        got = [piece async for piece in adapter.stream(client, MODEL, [])]
    assert got == ["real"]


async def test_a_failed_stream_ends_quietly():
    def handler(request):
        return httpx.Response(500, text="boom")

    async with transport(handler) as client:
        got = [piece async for piece in adapter.stream(client, MODEL, [])]
    assert got == []


def test_streamed_chunks_feed_the_protocol_parser():
    """The reason the parser is a fold.

    Whatever the server chunks look like, feeding them straight through must
    give the same result as parsing the whole reply.
    """
    from andropia.beings import protocol

    whole = "[happy]Hi there [motion:wave] friend.[goto:pond]"
    carry = ""
    events: tuple[protocol.Event, ...] = ()
    for i in range(0, len(whole), 7):  # arbitrary, server-chosen boundaries
        got, carry = protocol.feed(carry, whole[i : i + 7])
        events += got
    events += protocol.finish(carry)

    assert protocol.to_intents(events, "ava") == protocol.to_intents(
        protocol.parse(whole), "ava"
    )


# -- a whole turn ----------------------------------------------------------


async def test_a_turn_produces_intents_and_a_memory():
    async with transport(completion("[happy]Hello, bob! [motion:wave]")) as client:
        intents, error = await runner.think(a_world(), mind("ava", client))

    assert error is None
    assert any(isinstance(i, Speak) and "Hello, bob!" in i.text for i in intents)
    assert any(isinstance(i, Remember) for i in intents)
    assert all(i.entity == "ava" for i in intents)


async def test_a_failed_turn_yields_no_intents():
    def handler(request):
        return httpx.Response(503, text="down")

    async with transport(handler) as client:
        intents, error = await runner.think(a_world(), mind("ava", client))

    assert intents == ()
    assert error is not None


async def test_a_turn_for_a_missing_being_is_reported_not_raised():
    async with transport(completion("hi")) as client:
        intents, error = await runner.think(a_world(), mind("ghost", client))
    assert intents == () and error is not None


async def test_the_prompt_actually_sent_contains_the_situation():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    async with transport(handler) as client:
        await runner.think(a_world(), mind("ava", client))

    contents = [m["content"] for m in seen["body"]["messages"]]
    assert any("You are curious." in c for c in contents)  # persona
    assert any("bob" in c for c in contents)  # perception
    assert any("[motion:wave]" in c for c in contents)  # vocabulary


# -- the loop --------------------------------------------------------------


async def test_drive_proposes_intents_and_respects_shutdown():
    world = a_world(tick=runner.IDLE_THINK_TICKS + 1)
    proposed: list[tuple] = []
    stop = asyncio.Event()

    async with transport(completion("[happy]Hi.")) as client:
        cast = Cast.of(mind("ava", client))
        task = asyncio.create_task(
            runner.drive(cast, lambda: world, proposed.append, poll=0.01, stop=stop)
        )
        for _ in range(200):
            await asyncio.sleep(0.005)
            if proposed:
                break
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)

    assert proposed, "the runner never proposed anything"
    assert any(isinstance(i, Speak) for i in proposed[0])


async def test_a_being_has_only_one_request_in_flight():
    """A slow endpoint must not queue up turns behind itself."""
    world = a_world(tick=runner.IDLE_THINK_TICKS + 1)
    calls = 0
    release = asyncio.Event()

    async def handler(request):
        nonlocal calls
        calls += 1
        await release.wait()
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    stop = asyncio.Event()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cast = Cast.of(mind("ava", client))
        task = asyncio.create_task(
            runner.drive(
                cast, lambda: world, lambda _: None, poll=0.005, stop=stop
            )
        )
        await asyncio.sleep(0.1)  # many poll cycles
        assert calls == 1, f"started {calls} concurrent turns for one being"

        release.set()
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)


async def test_one_beings_broken_endpoint_does_not_stop_the_others():
    world = a_world(tick=runner.IDLE_THINK_TICKS + 1)
    proposed: list[tuple] = []
    stop = asyncio.Event()

    def handler(request):
        body = json.loads(request.content)
        if body["model"] == "broken":
            return httpx.Response(500, text="no")
        return httpx.Response(200, json={"choices": [{"message": {"content": "fine"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cast = Cast.of(
            mind("ava", client, Model(name="broken", base_url=MODEL.base_url)),
            mind("bob", client, Model(name="working", base_url=MODEL.base_url)),
        )
        task = asyncio.create_task(
            runner.drive(
                cast, lambda: world, proposed.append, poll=0.01, stop=stop
            )
        )
        for _ in range(200):
            await asyncio.sleep(0.005)
            if proposed:
                break
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)

    assert proposed, "the working being never got a turn"
    assert "ava" in cast.trouble  # and the failure was recorded for the operator
    assert "bob" not in cast.trouble


async def test_only_one_being_thinks_at_a_time():
    """Found by running it, not by testing it.

    `wants_turn` refuses to start while someone is *speaking*, which is not
    enough: two beings can both come due while the world is silent and their
    replies then land on the same tick. Against a fake model that happened five
    times in thirty seconds, and the transcript read as people talking over each
    other — the exact failure turn-taking was supposed to prevent.
    """
    world = a_world(tick=runner.IDLE_THINK_TICKS + 1)
    concurrent = 0
    peak = 0
    release = asyncio.Event()

    async def handler(request):
        nonlocal concurrent, peak
        concurrent += 1
        peak = max(peak, concurrent)
        await release.wait()
        concurrent -= 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    stop = asyncio.Event()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cast = Cast.of(mind("ava", client), mind("bob", client))
        task = asyncio.create_task(
            runner.drive(
                cast, lambda: world, lambda _: None, poll=0.005, stop=stop
            )
        )
        await asyncio.sleep(0.1)  # many poll cycles, both beings due
        release.set()
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)

    assert peak == 1, f"{peak} beings were thinking at once"


def test_a_being_cannot_gaze_at_itself():
    """Also found by running it.

    A model handed its own name in the observation will occasionally look at
    itself, and the renderer would then aim a being's gaze at its own head.
    """
    from andropia.sim.types import Look

    world = step(a_world(), (Look(entity="ava", at="ava"),))
    assert world.entities["ava"].gaze is None

    world = step(a_world(), (Look(entity="ava", at="bob"),))
    assert world.entities["ava"].gaze == "bob"


# -- determinism -----------------------------------------------------------


def test_intents_from_a_model_replay_without_the_model():
    """The claim the whole architecture rests on.

    A being's reply becomes intents; intents go in the log; replay reads the log
    and never calls a model. So the same intents give the same world, whatever
    the temperature was and whether or not the endpoint still exists.
    """
    from andropia.beings import protocol

    intents = protocol.to_intents(protocol.parse("[happy]Hello.[goto:pond]"), "ava")

    def run(world):
        world = step(world, intents)  # the model's turn, applied once
        for _ in range(120):  # then only time passing
            world = step(world)
        return world

    first, second = run(a_world()), run(a_world())
    assert first == second
    # And it actually did something, or the comparison is vacuous.
    assert first.entities["ava"].pos != a_world().entities["ava"].pos


@pytest.mark.parametrize("reply", ["", "   ", "[nonsense]", "[]", "plain words"])
async def test_odd_replies_never_raise(reply):
    """Whatever a model does, a turn ends in intents or an error — never a
    traceback that stops the world."""
    async with transport(completion(reply)) as client:
        intents, error = await runner.think(a_world(), mind("ava", client))
    assert error is None
    assert isinstance(intents, tuple)
