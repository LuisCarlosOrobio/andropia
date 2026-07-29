"""A deterministic autopilot, so the demo world is alive without an LLM.

Phase 3 puts language models behind these decisions. Until then this stands
in for them: it proposes the same kinds of intents an agent would, so the
whole pipeline — simulation, wire format, renderer, bodies, procedural
animation — can be seen working end to end by running one command and
opening a page.

Pure, like everything else in the simulation. Given a world it returns the
intents to propose, deriving its choices from the tick rather than from a
clock or a global RNG. Two runs of the same world produce the same
behaviour, so the demo is reproducible and replays correctly.
"""

from __future__ import annotations

from .sim import DoGesture, Emote, Goto, Intent, Look, Speak, World, rng
from .vocab import EMOTIONS, GESTURES

# How often a being considers doing something, in ticks. At 20 Hz this is
# roughly every three seconds — brisk enough to look alive, slow enough that
# a viewer can follow what happened.
DECISION_INTERVAL = 60

_LINES = (
    "I think I'll head over there.",
    "Hello — good to see you.",
    "It's quiet here today.",
    "Did you notice that?",
    "I've been wondering about something.",
    "This is a nice spot.",
    "Let me think about that for a moment.",
    "Where did everyone go?",
)


def autopilot(world: World) -> tuple[Intent, ...]:
    """Intents to propose for this tick.

    Each being decides on its own offset, so they act in a staggered rhythm
    rather than all moving on the same beat — which reads as a crowd rather
    than a chorus line.
    """
    if not world.entities:
        return ()

    out: list[Intent] = []

    for index, eid in enumerate(sorted(world.entities)):
        # Stagger decisions across the interval.
        offset = (index * DECISION_INTERVAL) // max(1, len(world.entities))
        if (world.tick + offset) % DECISION_INTERVAL != 0:
            continue

        out.extend(_decide(world, eid))

    return tuple(out)


def _decide(world: World, eid: str) -> list[Intent]:
    """One being's choice, seeded from the tick and its own id."""
    state = rng.seed(world.tick * 2654435761 + _hash(eid))

    roll, state = rng.next_below(state, 100)
    being = world.entities[eid]
    walking = being.action.kind == "walk"

    # Setting off somewhere. Skipped if already walking — re-routing every
    # few seconds reads as twitching, whereas letting a journey finish reads
    # as intent. Everything else stays available while walking, because
    # people talk and gesture on the move.
    if roll < 30:
        if not walking and world.landmarks:
            marks = sorted(world.landmarks)
            pick, state = rng.next_below(state, len(marks))
            return [Goto(entity=eid, target=marks[pick])]
        # Already going somewhere: say something about it instead.
        pick, state = rng.next_below(state, len(_LINES))
        return [Speak(entity=eid, text=_LINES[pick])]

    if roll < 55:
        pick, state = rng.next_below(state, len(GESTURES))
        # A gesture usually comes with a feeling; people rarely wave blankly.
        emotion_pick, state = rng.next_below(state, len(EMOTIONS))
        return [
            DoGesture(entity=eid, motion=GESTURES[pick]),
            Emote(entity=eid, emotion=EMOTIONS[emotion_pick]),
        ]

    if roll < 80:
        pick, state = rng.next_below(state, len(_LINES))
        return [Speak(entity=eid, text=_LINES[pick])]

    if roll < 92:
        others = [o for o in sorted(world.entities) if o != eid]
        if others:
            pick, state = rng.next_below(state, len(others))
            return [Look(entity=eid, at=others[pick])]

    emotion_pick, state = rng.next_below(state, len(EMOTIONS))
    return [Emote(entity=eid, emotion=EMOTIONS[emotion_pick])]


def _hash(text: str) -> int:
    """FNV-1a. Small, stable, and not the built-in ``hash``, which is salted
    per process and would make the demo differ between runs."""
    h = 2166136261
    for char in text.encode():
        h = ((h ^ char) * 16777619) & 0xFFFFFFFF
    return h
