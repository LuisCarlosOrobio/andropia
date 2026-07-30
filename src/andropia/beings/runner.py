"""Deciding when a being thinks, and getting its intents into the world.

Two things live here and they are kept apart. :func:`wants_turn` is pure: given
a world and when a being last thought, it says whether now is the moment. The
runner around it is a shell that owns the awkward parts — concurrency, one
in-flight request per being, a client to pool connections.

The split matters because turn-taking is the behaviour most likely to need
tuning and the least pleasant to debug through a network call. All of it is a
function over plain data.

**Why the simulation stays deterministic.** Model calls take hundreds of
milliseconds and the world ticks at 20 Hz, so a being's reply always lands some
unpredictable number of ticks after the observation that prompted it. That
would destroy determinism if the reply *were* the state change — but it is not.
The reply becomes intents, intents are queued, and the tick that consumes them
records them in the intent log. Replay reads that log and never calls a model,
so the run reproduces exactly regardless of how long the endpoint took or
whether it still exists. Non-determinism is confined to *which* intents get
produced, which is upstream of the recording.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field

from ..sim.types import EntityId, Intent, Remember, Speak, World
from . import perception, prompt, protocol
from .adapter import ENV_BASE_URL, ENV_KEY, ENV_MODEL, Brain, Model

#: Ticks a being must let pass before thinking again. At 20 Hz this is about a
#: second and a half — fast enough to hold a conversation, slow enough that a
#: local model can keep up and that beings are not billed for thinking while
#: nothing has changed.
MIN_THINK_TICKS = 30

#: A being with nothing new to react to still stirs eventually, so a quiet
#: world does not freeze into a tableau. About twelve seconds.
IDLE_THINK_TICKS = 240

#: Extra ticks to wait after each consecutive failed turn, so a struggling
#: endpoint is not hammered by three beings in rotation.
#:
#: At 20 Hz: no wait, then roughly 3s, 9s, 20s, 45s, 90s. Capped rather than
#: unbounded — a being that backs off forever is a being that never comes back,
#: and an outage ends eventually.
#:
#: This exists because of a real one. The API returned 500s and 529s for three
#: minutes; each being retried the moment `MIN_THINK_TICKS` elapsed, so the world
#: issued a request every second and a half throughout, which helps nobody and
#: is charged for on the failures that are billed.
BACKOFF_TICKS: tuple[int, ...] = (0, 60, 180, 400, 900, 1800)

#: How much of its own turn a being commits to memory. Enough to keep continuity
#: past the transcript window without writing an essay.
MEMORY_CHARS = 160


@dataclass(frozen=True, slots=True)
class Mind:
    """One being's wiring. Deployment config, never part of the world.

    Holds a :data:`Brain` rather than a model config, so this module — and the
    loop below — never learns which provider answered. Anthropic's API and the
    OpenAI-compatible one share almost nothing on the wire, and the difference
    belongs in the provider modules, not here.
    """

    entity: EntityId
    brain: Brain


@dataclass(slots=True)
class Cast:
    """Who thinks, and what each of them is up to.

    The one mutable structure in this package, and deliberately so: it tracks
    in-flight requests, which is exactly the kind of state that should live in
    a shell rather than be threaded through pure code.
    """

    minds: dict[EntityId, Mind] = field(default_factory=dict)
    #: Tick at which each being last began thinking.
    last_thought: dict[EntityId, int] = field(default_factory=dict)
    #: Beings with a request in flight. One at a time, each.
    thinking: set[EntityId] = field(default_factory=set)
    #: Last error per being, for the operator. Beings do not see these.
    trouble: dict[EntityId, str] = field(default_factory=dict)
    #: Consecutive failed turns per being, which drives the backoff.
    misses: dict[EntityId, int] = field(default_factory=dict)

    @classmethod
    def of(cls, *minds: Mind) -> Cast:
        return cls(minds={m.entity: m for m in minds})


# --------------------------------------------------------------------------
# arbitration — pure
# --------------------------------------------------------------------------


def wants_turn(world: World, eid: EntityId, since: int) -> bool:
    """Whether ``eid`` should think now, having last thought at tick ``since``.

    Three rules, in order of how often they matter:

    A being does not think twice in quick succession, or a fast endpoint turns
    into a monologue and a slow one into a queue.

    A being does not start thinking while someone else is mid-sentence. This is
    the whole of turn-taking, and it is enough: without it every being replies
    to the same line at once and the transcript reads as three people talking
    over each other, which is the characteristic failure of multi-agent chat.

    Otherwise a being thinks when it has heard something since it last thought,
    or when it has been quiet long enough to stir on its own.
    """
    ent = world.entities.get(eid)
    if ent is None:
        return False

    elapsed = world.tick - since
    if elapsed < MIN_THINK_TICKS:
        return False

    if _someone_else_speaking(world, eid):
        return False

    if elapsed >= IDLE_THINK_TICKS:
        return True

    return _heard_since(world, eid, since)


def _someone_else_speaking(world: World, eid: EntityId) -> bool:
    return any(
        other.speech is not None
        for other_id, other in world.entities.items()
        if other_id != eid
    )


def _heard_since(world: World, eid: EntityId, since: int) -> bool:
    """Anything said by anyone else since this being last thought.

    Range is not consulted, unlike in perception. A being across the world is
    inaudible and its line will not appear in the observation, so at worst this
    spends a turn on a being that then has nothing new to say — whereas
    duplicating the audibility rule here would be a second place for it to
    drift out of step with perception.
    """
    return any(
        line.tick >= since and line.speaker != eid for line in world.transcript
    )


def backoff(misses: int) -> int:
    """Extra ticks a being waits after ``misses`` consecutive failed turns."""
    return BACKOFF_TICKS[min(misses, len(BACKOFF_TICKS) - 1)]


def next_speaker(cast: Cast, world: World) -> EntityId | None:
    """Which being gets the next turn: whoever has waited longest.

    Only one being thinks at a time, so *how* the one is chosen decides who
    gets heard. Taking the first eligible being in id order starves everyone
    after it — a being late in the alphabet only ever speaks when nobody
    earlier wants to.

    That is not hypothetical. Against three beings on a live model, `mistral`
    managed one line in seventy minutes of ticks while `ava` and `claude` held
    the floor; `claude` addressed it directly twice and it never answered,
    which reads as a sulking personality rather than a scheduler bug.

    Longest-waiting is fair without needing a queue, and ties break on id so
    the choice stays deterministic for the same world and the same cast.
    """
    never = -(10**9)
    waiting = []

    for eid in sorted(cast.minds):
        since = cast.last_thought.get(eid, never)
        # A being whose last few turns failed waits longer than one whose did
        # not. Additional to `wants_turn`, which enforces the ordinary minimum.
        if world.tick - since < backoff(cast.misses.get(eid, 0)):
            continue
        if wants_turn(world, eid, since):
            waiting.append((since, eid))

    return min(waiting)[1] if waiting else None


def turn_memory(intents: tuple[Intent, ...], limit: int = MEMORY_CHARS) -> str:
    """A one-line note of what a being just did, for its own memory.

    Written from the intents rather than the raw reply so it records what
    actually happened in the world, not what the model claimed. A turn that
    changed nothing is worth nothing and returns "".
    """
    said = next((i.text for i in intents if isinstance(i, Speak)), "")
    if not said:
        return ""

    trimmed = said if len(said) <= limit else said[: limit - 1].rstrip() + "…"
    return f'I said: "{trimmed}"'


# --------------------------------------------------------------------------
# the shell
# --------------------------------------------------------------------------


async def think(
    world: World,
    mind: Mind,
) -> tuple[tuple[Intent, ...], str | None]:
    """One being's turn: observe, ask, parse. Returns intents and any error.

    Reads the world but never writes it, so it is safe to run several of these
    concurrently against the same snapshot. Their intents queue and the next
    tick applies them in order.
    """
    obs = perception.observe(world, mind.entity)
    if obs is None:
        return (), "not in the world"

    ent = world.entities[mind.entity]
    reply = await mind.brain(prompt.messages(ent, obs))
    if not reply.ok:
        return (), reply.error

    intents = protocol.to_intents(protocol.parse(reply.text), mind.entity)
    note = turn_memory(intents)
    if note:
        intents += (Remember(entity=mind.entity, text=note, salience=0.5),)

    return intents, None


async def drive(
    cast: Cast,
    snapshot: Callable[[], World],
    propose: Callable[[tuple[Intent, ...]], None],
    *,
    poll: float = 0.1,
    stop: asyncio.Event | None = None,
) -> None:
    """Run every being in ``cast`` for as long as the world runs.

    Takes callables rather than a session so it cannot hold a stale world or
    become a second owner of one. ``snapshot`` hands over the current world;
    ``propose`` queues intents for the next tick. That is the entire contract,
    and it is what keeps the tick loop the single writer.

    Each being gets its own task per turn. A being whose endpoint is slow falls
    behind on its own without stalling anyone else, which matters when one
    being is on a local 7B and another is on a hosted frontier model.
    """
    stop = stop or asyncio.Event()
    running: set[asyncio.Task] = set()

    try:
        while not stop.is_set():
            world = snapshot()

            # One being thinks at a time across the whole cast, and the one
            # that has waited longest goes next.
            #
            # `wants_turn` refuses to start while someone is *speaking*, which
            # is not enough on its own: two beings can both come due while the
            # world is silent, and their replies then land on the same tick.
            # Serialising starts fixes that completely, because a turn cannot
            # begin until the previous being has finished speaking.
            #
            # The cost is that beings in separate conversations wait for each
            # other, which is wrong for a crowd and right for the handful this
            # is built for. Per-group arbitration is the thing to add when a
            # world is busy enough to need it.
            if not cast.thinking:
                eid = next_speaker(cast, world)
                if eid is not None:
                    cast.thinking.add(eid)
                    cast.last_thought[eid] = world.tick
                    task = asyncio.create_task(
                        _turn(world, cast.minds[eid], cast, propose)
                    )
                    running.add(task)
                    task.add_done_callback(running.discard)

            await _sleep_or_stop(stop, poll)
    finally:
        for task in tuple(running):
            task.cancel()


async def _turn(
    world: World,
    mind: Mind,
    cast: Cast,
    propose: Callable[[tuple[Intent, ...]], None],
) -> None:
    """One turn, with the bookkeeping that must happen however it ends."""
    try:
        intents, error = await think(world, mind)
        if error:
            cast.misses[mind.entity] = cast.misses.get(mind.entity, 0) + 1
            # Printed only when it changes. A being whose endpoint is down
            # fails every turn, and a line every second and a half would bury
            # the world's own output — but saying nothing at all is worse,
            # because the symptom is a being that stands there mutely and the
            # cause is invisible.
            if cast.trouble.get(mind.entity) != error:
                print(f"[andropia] {mind.entity}: {error}")
            cast.trouble[mind.entity] = error
        else:
            if mind.entity in cast.trouble:
                print(f"[andropia] {mind.entity}: recovered")
            cast.trouble.pop(mind.entity, None)
            cast.misses.pop(mind.entity, None)
        if intents:
            propose(intents)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - one being must not stop the world
        # A bug in parsing or prompting should cost this being its turn and
        # nothing more. Swallowing it here is what keeps a crash in one mind
        # from being an outage for everyone.
        cast.trouble[mind.entity] = f"{type(exc).__name__}: {exc}"
    finally:
        cast.thinking.discard(mind.entity)


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    """Wait, but wake immediately on shutdown rather than serving out the poll."""
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


def personas(world: World, brains: dict[EntityId, Brain]) -> Cast:
    """A cast for every being in the world that has a brain configured."""
    return Cast.of(
        *(
            Mind(entity=eid, brain=brains[eid])
            for eid in sorted(world.entities)
            if eid in brains
        )
    )


__all__ = [
    "ENV_BASE_URL",
    "ENV_KEY",
    "ENV_MODEL",
    "Brain",
    "Cast",
    "Mind",
    "Model",
    "backoff",
    "drive",
    "next_speaker",
    "personas",
    "think",
    "turn_memory",
    "wants_turn",
]
