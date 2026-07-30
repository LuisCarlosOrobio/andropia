"""Turning a world pack into the words a being is given. Pure.

The one function that makes the format worth having. ``World.setting`` used to
be a paragraph someone typed while the scene was a set of constants in
``stage.js``, and nothing connected them — so a description could say "lush
meadow" over a dark void and no test would notice. Three beings once spent two
minutes reporting the falling water level of a pond that is a point on a flat
plane, and nothing they were told contradicted it.

Now the same fields that draw the ground write the sentence about the ground.

Deliberately *only* the ambient — ground, sky, atmosphere. What is standing in
the world is perception's business, for three reasons that all point the same
way. Perception knows where each thing is relative to the being looking, which
is the part that is actually useful. It reports only what is in sight, whereas
an inventory here would name things across the whole world and contradict the
standing rule that a being may refer only to what it can currently see. And an
inventory does not scale: a world with fifty features would spend its entire
cached prefix listing them.

So this describes the place, and perception describes its contents. The one
exception is a world with no features at all, which is a fact about the place
rather than an inventory of it, and worth saying out loud — a being told nothing
about where it is will furnish it.
"""

from __future__ import annotations

from .schema import WorldPack


def setting(pack: WorldPack) -> str:
    """How the place itself should be described, in the being's own terms.

    Generated rather than authored, save for ``atmosphere`` — which is the one
    field with no rendered counterpart to contradict, being about mood.
    """
    parts = []

    if pack.atmosphere:
        parts.append(pack.atmosphere)

    parts.append(f"Underfoot: {pack.ground.description}.")
    parts.append(f"Overhead: {pack.sky.description}.")

    if not pack.features:
        parts.append(
            "Nothing has been placed here — there is the ground, the sky, and "
            "whoever else is present, and nothing else to examine."
        )


    return "\n\n".join(parts)
