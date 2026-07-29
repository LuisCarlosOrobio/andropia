"""The fold at the centre of everything.

    step :: (World, [Intent], dt) -> World

Pure. Given the same world, the same intents and the same ``dt`` it produces
the same world, every time, on every run. That property is the reason the
sandbox can be replayed, forked, snapshotted and fast-forwarded, and it is
worth more than any individual feature built on top of it.

Phase order is fixed and must not be rearranged casually — it is part of the
observable behaviour:

1. **Intents** are applied. Agents propose; the simulation disposes.
2. **Actions** advance: walking moves bodies, gestures age.
3. **Overlaps** resolve, after movement has happened.
4. **Speech** expires once its duration has elapsed.
5. **Tick** increments last, so everything above sees a consistent "now".
"""

from __future__ import annotations

from dataclasses import replace

from . import movement
from .types import (
    DoGesture,
    Emote,
    Entity,
    Gesture,
    Goto,
    Idle,
    Intent,
    Look,
    Memory,
    MoveTo,
    Remember,
    Speak,
    Speech,
    Stop,
    Utterance,
    Walk,
    World,
)

# Speech duration is estimated from length until synthesis reports back with
# real timings. ~2.8 words/second is unhurried conversational pace.
_WORDS_PER_SECOND = 2.8
_MIN_SPEECH_SECONDS = 0.8

#: Memories one being may hold. A cap rather than a policy: beyond this the
#: least salient is dropped, so a long-lived being keeps what mattered instead
#: of the most recent thing that happened.
MEMORY_LIMIT = 64

#: Lines of shared transcript the world keeps. Perception reads only the last
#: handful and older lines belong in memory, so an uncapped transcript is pure
#: growth — invisible for a demo, and the thing that makes a world left running
#: overnight snapshot to something enormous.
TRANSCRIPT_LIMIT = 256


def step(
    world: World,
    intents: tuple[Intent, ...] = (),
    dt: float | None = None,
) -> World:
    """Advance the world by one tick."""
    dt = world.dt if dt is None else dt

    world = _apply_intents(world, intents)
    world = _advance_actions(world, dt)
    world = _resolve_overlaps(world)
    world = _expire_speech(world, dt)

    return replace(world, tick=world.tick + 1)


def run(
    world: World,
    script: list[tuple[Intent, ...]],
    dt: float | None = None,
) -> World:
    """Fold ``step`` over a sequence of per-tick intent batches.

    The whole simulation is this: a fold. Replay is re-running it, forking is
    starting it from a snapshot, and fast-forward is running it without a
    renderer attached.
    """
    for batch in script:
        world = step(world, batch, dt)
    return world


# --------------------------------------------------------------------------
# 1. intents
# --------------------------------------------------------------------------


def _apply_intents(world: World, intents: tuple[Intent, ...]) -> World:
    if not intents:
        return world

    entities = dict(world.entities)
    transcript = world.transcript

    for it in intents:
        ent = entities.get(it.entity)
        if ent is None:
            # An intent naming a being that no longer exists is dropped
            # rather than raised. Agents act on a world one tick stale.
            continue

        match it:
            case Goto():
                mark = world.landmarks.get(it.target)
                if mark is not None:
                    entities[ent.id] = replace(ent, action=Walk(target=mark.pos))

            case MoveTo():
                entities[ent.id] = replace(ent, action=Walk(target=it.pos))

            case DoGesture():
                entities[ent.id] = replace(ent, action=Gesture(motion=it.motion))

            case Emote():
                entities[ent.id] = replace(ent, emotion=it.emotion, emotion_weight=1.0)

            case Look():
                # A being cannot look at itself. The renderer would aim its
                # gaze at its own head, and a model handed its own name back
                # will occasionally take it — which is how `ava gaze=ava`
                # turned up the first time this ran against a real reply.
                gaze = None if it.at == ent.id else it.at
                entities[ent.id] = replace(ent, gaze=gaze)

            case Stop():
                entities[ent.id] = replace(ent, action=Idle(), vel=ent.vel.__class__())

            case Speak():
                speech = Speech(
                    text=it.text,
                    start_tick=world.tick,
                    duration_ticks=_speech_ticks(it.text, world.dt),
                )
                entities[ent.id] = replace(ent, speech=speech)
                transcript = (*transcript, Utterance(world.tick, ent.id, it.text))[
                    -TRANSCRIPT_LIMIT:
                ]

            case Remember():
                entities[ent.id] = replace(
                    ent,
                    memory=_remember(
                        ent.memory,
                        Memory(tick=world.tick, text=it.text, salience=it.salience),
                    ),
                )

    return replace(world, entities=entities, transcript=transcript)


def _remember(memory: tuple[Memory, ...], fresh: Memory) -> tuple[Memory, ...]:
    """Add a memory, evicting the least worth keeping if over the cap.

    Evicts by salience first and age second, so a being forgets the trivial
    before the old. Sorting on an explicit key rather than relying on tuple
    order keeps the choice deterministic when several memories tie.
    """
    grown = (*memory, fresh)
    if len(grown) <= MEMORY_LIMIT:
        return grown

    doomed = min(grown, key=lambda m: (m.salience, m.tick, m.text))
    return tuple(m for m in grown if m is not doomed)


def _speech_ticks(text: str, dt: float) -> int:
    words = max(1, len(text.split()))
    seconds = max(_MIN_SPEECH_SECONDS, words / _WORDS_PER_SECOND)
    return max(1, int(seconds / dt))


# --------------------------------------------------------------------------
# 2. actions
# --------------------------------------------------------------------------


def _advance_actions(world: World, dt: float) -> World:
    entities = {
        eid: _advance_one(ent, dt) for eid, ent in sorted(world.entities.items())
    }
    return replace(world, entities=entities)


def _advance_one(ent: Entity, dt: float) -> Entity:
    ent = movement.advance(ent, dt)

    action = ent.action
    if isinstance(action, Gesture):
        elapsed = action.elapsed + dt
        if elapsed >= action.duration:
            ent = replace(ent, action=Idle())
        else:
            ent = replace(ent, action=replace(action, elapsed=elapsed))

    # Emotion decays toward neutral so a being does not stay furious forever
    # after one angry line. Linear, framerate-independent, no clock read.
    if ent.emotion_weight > 0.0:
        decayed = max(0.0, ent.emotion_weight - dt * 0.12)
        ent = replace(ent, emotion_weight=decayed)
        if decayed == 0.0 and ent.emotion != "neutral":
            ent = replace(ent, emotion="neutral")

    return ent


# --------------------------------------------------------------------------
# 3. overlaps
# --------------------------------------------------------------------------


def _resolve_overlaps(world: World) -> World:
    if len(world.entities) < 2:
        return world
    return replace(world, entities=movement.resolve_overlaps(world.entities))


# --------------------------------------------------------------------------
# 4. speech
# --------------------------------------------------------------------------


def _expire_speech(world: World, dt: float) -> World:
    entities = dict(world.entities)
    changed = False

    for eid, ent in sorted(entities.items()):
        sp = ent.speech
        if sp is None:
            continue
        if world.tick - sp.start_tick >= sp.duration_ticks:
            entities[eid] = replace(ent, speech=None)
            changed = True

    return replace(world, entities=entities) if changed else world
