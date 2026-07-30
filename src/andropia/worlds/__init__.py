"""World packs: one declaration of a place, drawn and described from the same
fields.

    schema    validate(raw) -> Valid | Invalid       pure
    describe  setting(pack) -> str                   pure
    build     landmarks(pack) -> {id: Landmark}      pure
    load      load_pack(dir) -> Valid | Invalid      the shell

`frontend/src/world.js` reads the same manifest. That is the whole idea: a
description that cannot drift from what is drawn, because both come from one
file. Before this, the description was a paragraph in Python and the scene was a
set of constants in `stage.js`, and three beings once spent two minutes
discussing the falling water level of a pond that was a point on a flat plane.

The division of labour is worth stating, because it is the part that is easy to
get wrong: `describe` says what the *place* is like — ground, sky, atmosphere —
and `andropia.beings.perception` says what is *in* it. Perception knows where
each thing is relative to the being looking, reports only what is in sight, and
does not grow the cached prompt prefix by one line per feature in the world.
"""

from __future__ import annotations

from .build import landmarks
from .describe import setting
from .load import discover, load_pack
from .schema import (
    MATERIALS,
    SCHEMA_VERSION,
    SHAPES,
    Feature,
    Invalid,
    Result,
    Valid,
    WorldError,
    WorldPack,
    validate,
)

__all__ = [
    "MATERIALS",
    "SCHEMA_VERSION",
    "SHAPES",
    "Feature",
    "Invalid",
    "Result",
    "Valid",
    "WorldError",
    "WorldPack",
    "discover",
    "landmarks",
    "load_pack",
    "setting",
    "validate",
]
