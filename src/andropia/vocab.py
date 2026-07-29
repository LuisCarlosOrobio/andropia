"""The canonical vocabulary.

These names are a **public contract**. Prompts, finetune datasets and avatar
packs are all written against them, so changing one breaks other people's
work — treat additions as cheap and renames as breaking.

Emotions are exactly the VRM standard expression presets. That is not a
coincidence and it is the single most valuable constraint in the format: a
conformant VRM needs no mapping table at all, and a third-party avatar works
unmodified. Projects that invented their own larger emotion sets ended up
with tags that silently no-op on most rigs.
"""

from __future__ import annotations

#: The six VRM standard expression presets.
EMOTIONS: tuple[str, ...] = (
    "neutral",
    "happy",
    "angry",
    "sad",
    "relaxed",
    "surprised",
)

#: Discrete one-shot gestures. Andropia-defined, deliberately few.
#: A pack may back any of these with an animation clip; those it does not
#: are generated procedurally in normalised humanoid space, so every gesture
#: works on every rig.
GESTURES: tuple[str, ...] = (
    "wave",
    "nod",
    "shake",
    "shrug",
    "think",
    "point",
    "cheer",
    "idle_variant",
)

#: Continuous locomotion states. Distinct from gestures: these loop and
#: reflect what a being *is doing*, rather than firing once and ending.
#: A pack may back them with clips; procedural fallbacks cover the rest.
LOCOMOTION: tuple[str, ...] = (
    "idle",
    "walk",
)

#: `goto` is a motion in the tag grammar but resolves to navigation rather
#: than to a clip, so it is not a gesture and is not listed above.
NAVIGATION_MOTION = "goto"
