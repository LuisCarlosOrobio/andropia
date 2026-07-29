"""The simulation core.

Pure, dependency-free, and buildable with no models, no renderer and no
network. Everything else in Andropia is a producer of intents or a consumer
of worlds.

    from andropia.sim import step, World, Entity

    w = World(entities={"ava": Entity(id="ava")})
    w = step(w, (Goto(entity="ava", target="pond"),))
"""

from .step import run, step
from .types import (
    DoGesture,
    Emote,
    Entity,
    Gesture,
    Goto,
    Idle,
    Intent,
    Landmark,
    Look,
    Memory,
    Speak,
    Speech,
    Stop,
    Utterance,
    Walk,
    World,
)
from .vec import Vec3

__all__ = [
    "DoGesture", "Emote", "Entity", "Gesture", "Goto", "Idle", "Intent",
    "Landmark", "Look", "Memory", "Speak", "Speech", "Stop", "Utterance",
    "Vec3", "Walk", "World", "run", "step",
]
