"""The world pack format, and its validator.

A world pack is one declaration of a place, read by two consumers that must
never disagree: the renderer draws from it, and :mod:`andropia.worlds.describe`
generates from it the words beings are given. Today those two are a paragraph
someone typed and a set of constants in ``stage.js``, connected by nothing —
which is how three beings came to spend two minutes reporting the falling water
level of a pond that is a point on a flat plane. Nothing was lying; the
description had simply never been answerable to what was drawn.

Parameters rather than geometry, deliberately. Every value the scene currently
hardcodes — background, fog, light, floor extent, grid divisions, landmark
positions — is a number, so a manifest of numbers replaces all of it with no art
pipeline and no licence provenance to establish. A pack that ships a model file
is a later increment; the manifest grows a field and this schema grows a branch.

Two properties shape the design, both inherited from the avatar pack format:

* **A licence is mandatory.** The schema refuses to validate without one. Given
  how often a badge, a filename or a registry has been found to contradict the
  file it described, structurally required provenance is a correctness property
  rather than bureaucracy.
* **Validation is total.** Every problem is reported at once, and an unknown
  value names the ones that would have worked. An author who fixes one field,
  re-runs, and meets the next has been failed by the validator.

The shape vocabulary is the cross-language seam. A shape this module accepts and
the renderer does not implement is an invisible landmark and no error — so
``worlds/example`` uses every one of them, and is a fixture for tests on both
sides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = 1

#: Shapes the renderer knows how to draw.
#:
#: Adding one here without implementing it in ``frontend/src/world.js`` produces
#: a landmark that validates and never appears. The example pack exercises every
#: entry so that both sides fail loudly instead.
SHAPES: tuple[str, ...] = ("disc", "block", "column", "mound")

#: What a landmark is made of. Perception reports this, so a being asking
#: whether something is wet gets an answer from the world rather than from its
#: own imagination — which is the failure this whole format exists to retire.
MATERIALS: tuple[str, ...] = (
    "water",
    "stone",
    "wood",
    "grass",
    "earth",
    "sand",
    "metal",
    "ice",
)


# --------------------------------------------------------------------------
# the pack
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class License:
    id: str
    url: str = ""
    attribution: str = ""
    notice: str = ""


@dataclass(frozen=True, slots=True)
class Ground:
    """The floor. ``grid`` draws the reference lines, which are honest for an
    unbuilt space and wrong for a meadow — so it is declared, not assumed."""

    colour: str = "#151a1f"
    extent: float = 200.0
    grid: bool = True
    description: str = "level ground"


@dataclass(frozen=True, slots=True)
class Sky:
    colour: str = "#0e1114"
    #: Distances at which fog begins and becomes total. Empty means none.
    fog: tuple[float, float] | None = None
    description: str = "an empty dark sky"


@dataclass(frozen=True, slots=True)
class Light:
    key: float = 2.0
    sky_colour: str = "#9fb8cc"
    ground_colour: str = "#1a1f24"


@dataclass(frozen=True, slots=True)
class Feature:
    """A landmark: something drawn, named, and describable.

    ``radius`` gives a landmark extent rather than a bare point, which is what
    lets walking to it arrive at its edge. ``material`` and ``enterable`` are
    the fields perception reports — the difference between a pond a being can
    ask about and a name floating over nothing.
    """

    id: str
    pos: tuple[float, float, float]
    shape: str
    description: str
    material: str
    colour: str = "#3a444e"
    radius: float = 1.0
    height: float = 1.0
    enterable: bool = False


@dataclass(frozen=True, slots=True)
class WorldPack:
    id: str
    name: str
    license: License
    ground: Ground = field(default_factory=Ground)
    sky: Sky = field(default_factory=Sky)
    light: Light = field(default_factory=Light)
    features: tuple[Feature, ...] = ()
    #: One or two sentences of authored atmosphere. Everything else in the
    #: description is generated, so this is the only prose that can be wrong —
    #: and it is about mood, which has no rendered counterpart to contradict.
    atmosphere: str = ""


# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorldError:
    field: str
    problem: str
    hint: str = ""

    def __str__(self) -> str:
        base = f"{self.field}: {self.problem}"
        return f"{base}\n    {self.hint}" if self.hint else base


@dataclass(frozen=True, slots=True)
class Invalid:
    errors: tuple[WorldError, ...]

    ok: Literal[False] = False

    def __str__(self) -> str:
        lines = "\n".join(f"  - {e}" for e in self.errors)
        return f"{len(self.errors)} problem(s):\n{lines}"


@dataclass(frozen=True, slots=True)
class Valid:
    pack: WorldPack
    warnings: tuple[str, ...] = ()

    ok: Literal[True] = True


Result = Valid | Invalid


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------
#
# Every check below is a pure function from its input to ``(value, errors)``.
#
# The first draft threaded a mutable error list into each helper — the caller
# passed a list and every helper appended to it. That is the shape the avatar
# schema uses, and it is an out-parameter: shared mutable state, helpers that
# cannot be called without constructing an accumulator, and no way to test one
# check in isolation.
#
# It is also not this project's idiom. ``rng.next_u64(state) -> (value, state)``
# and ``protocol.feed(carry, chunk) -> (events, carry)`` both return their carry
# rather than mutating one. Validation errors are simpler still: they are
# independent rather than sequential, so they need no threading at all — only
# concatenation. Each check answers for its own field and knows nothing about
# any other.

#: One check's result: the value to use, and whatever was wrong with it.
Checked = tuple[Any, tuple[WorldError, ...]]

NO_ERRORS: tuple[WorldError, ...] = ()


def validate(raw: Any) -> Result:
    """Check a world manifest. Pure, and total: every problem at once.

    Reads as a list of independent questions about the manifest, because that
    is what it is. An author who fixes one field, re-runs, and meets the next
    has been failed by the validator.
    """
    if not isinstance(raw, dict):
        return Invalid((WorldError("<root>", "manifest must be a JSON object"),))

    licence, licence_errors = _license(raw.get("license"))
    ground, ground_errors = _ground(raw.get("ground", {}))
    sky, sky_errors = _sky(raw.get("sky", {}))
    light, light_errors = _light(raw.get("light", {}))
    features, feature_errors, warnings = _features(raw.get("features", []))
    atmosphere, atmosphere_errors = _atmosphere(raw.get("atmosphere", ""))

    errors = (
        *_version(raw.get("schema")),
        *_identity(raw),
        *licence_errors,
        *ground_errors,
        *sky_errors,
        *light_errors,
        *feature_errors,
        *atmosphere_errors,
    )
    if errors:
        return Invalid(errors)

    return Valid(
        WorldPack(
            id=raw["id"],
            name=raw["name"],
            license=licence,
            ground=ground,
            sky=sky,
            light=light,
            features=features,
            atmosphere=atmosphere,
        ),
        warnings,
    )


# --------------------------------------------------------------------------
# the manifest, field by field
# --------------------------------------------------------------------------


def _version(raw: Any) -> tuple[WorldError, ...]:
    if raw == SCHEMA_VERSION:
        return NO_ERRORS
    return (
        WorldError(
            "schema",
            f"expected {SCHEMA_VERSION}, got {raw!r}",
            f"this build reads schema {SCHEMA_VERSION} world packs",
        ),
    )


def _identity(raw: dict) -> tuple[WorldError, ...]:
    return tuple(
        WorldError(key, "required, must be a non-empty string")
        for key in ("id", "name")
        if not _named(raw.get(key))
    )


def _atmosphere(raw: Any) -> tuple[str, tuple[WorldError, ...]]:
    if not isinstance(raw, str):
        return "", (WorldError("atmosphere", "must be a string"),)
    return raw.strip(), NO_ERRORS


def _license(raw: Any) -> tuple[License, tuple[WorldError, ...]]:
    """A licence is required, for the same reason it is on an avatar pack:
    every time provenance was optional here, something turned out to
    contradict its own label."""
    if not isinstance(raw, dict):
        return License(id=""), (
            WorldError(
                "license",
                "required",
                'every pack must declare its terms, e.g. {"id": "CC0-1.0"}',
            ),
        )

    ident = raw.get("id")
    if not _named(ident):
        return License(id=""), (
            WorldError("license.id", "required, must be a non-empty string"),
        )

    return (
        License(
            id=ident,
            url=_text(raw.get("url")),
            attribution=_text(raw.get("attribution")),
            notice=_text(raw.get("notice")),
        ),
        NO_ERRORS,
    )


def _ground(raw: Any) -> tuple[Ground, tuple[WorldError, ...]]:
    if not isinstance(raw, dict):
        return Ground(), (WorldError("ground", "must be an object"),)

    colour, bad_colour = _colour(raw.get("colour", "#151a1f"), "ground.colour")
    extent, bad_extent = _number(raw.get("extent", 200.0), "ground.extent", low=1.0)
    grid, bad_grid = _flag(raw.get("grid", True), "ground.grid")

    return (
        Ground(
            colour=colour,
            extent=extent,
            grid=grid,
            description=_text(raw.get("description")) or "level ground",
        ),
        (*bad_colour, *bad_extent, *bad_grid),
    )


def _sky(raw: Any) -> tuple[Sky, tuple[WorldError, ...]]:
    if not isinstance(raw, dict):
        return Sky(), (WorldError("sky", "must be an object"),)

    colour, bad_colour = _colour(raw.get("colour", "#0e1114"), "sky.colour")
    fog, bad_fog = _fog(raw.get("fog"))

    return (
        Sky(
            colour=colour,
            fog=fog,
            description=_text(raw.get("description")) or "an empty dark sky",
        ),
        (*bad_colour, *bad_fog),
    )


def _fog(raw: Any) -> tuple[tuple[float, float] | None, tuple[WorldError, ...]]:
    if raw is None:
        return None, NO_ERRORS
    if not _pair(raw):
        return None, (
            WorldError("sky.fog", "must be [near, far]", "or omit it for no fog"),
        )
    near, far = float(raw[0]), float(raw[1])
    if near >= far:
        return None, (
            WorldError("sky.fog", f"near {near} is not before far {far}"),
        )
    return (near, far), NO_ERRORS


def _light(raw: Any) -> tuple[Light, tuple[WorldError, ...]]:
    if not isinstance(raw, dict):
        return Light(), (WorldError("light", "must be an object"),)

    key, bad_key = _number(raw.get("key", 2.0), "light.key", low=0.0)
    sky, bad_sky = _colour(raw.get("sky_colour", "#9fb8cc"), "light.sky_colour")
    ground, bad_ground = _colour(
        raw.get("ground_colour", "#1a1f24"), "light.ground_colour"
    )

    return (
        Light(key=key, sky_colour=sky, ground_colour=ground),
        (*bad_key, *bad_sky, *bad_ground),
    )


# --------------------------------------------------------------------------
# features
# --------------------------------------------------------------------------


def _features(
    raw: Any,
) -> tuple[tuple[Feature, ...], tuple[WorldError, ...], tuple[str, ...]]:
    """Validate each feature independently, then the one thing that is not
    independent: whether any two share a name."""
    if not isinstance(raw, list):
        return (), (WorldError("features", "must be a list"),), ()

    checked = [_feature(item, f"features[{i}]") for i, item in enumerate(raw)]

    features = tuple(f for f, _, _ in checked)
    errors = tuple(e for _, errs, _ in checked for e in errs)
    warnings = tuple(w for _, _, warns in checked for w in warns)

    return features, (*errors, *_unique(features)), warnings


def _unique(features: tuple[Feature, ...]) -> tuple[WorldError, ...]:
    """The only cross-feature rule: a being names a place by its id and has no
    way to disambiguate two of them."""
    seen: set[str] = set()
    clashes: list[WorldError] = []

    for index, feature in enumerate(features):
        if feature.id and feature.id in seen:
            clashes.append(
                WorldError(
                    f"features[{index}].id",
                    f"{feature.id!r} appears more than once",
                    "a being names a place by its id and cannot disambiguate two",
                )
            )
        seen.add(feature.id)

    return tuple(clashes)


def _feature(
    raw: Any, where: str
) -> tuple[Feature, tuple[WorldError, ...], tuple[str, ...]]:
    if not isinstance(raw, dict):
        return _placeholder(), (WorldError(where, "must be an object"),), ()

    ident, bad_id = _feature_id(raw.get("id"), f"{where}.id")
    shape, bad_shape = _one_of(raw.get("shape"), SHAPES, f"{where}.shape", "shape")
    material, bad_material = _one_of(
        raw.get("material"), MATERIALS, f"{where}.material", "material"
    )
    described, bad_description = _description(raw.get("description"), where)
    pos, bad_pos = _position(raw.get("pos"), f"{where}.pos")
    colour, bad_colour = _colour(raw.get("colour", "#3a444e"), f"{where}.colour")
    radius, bad_radius = _number(raw.get("radius", 1.0), f"{where}.radius", low=0.0)
    height, bad_height = _number(raw.get("height", 1.0), f"{where}.height", low=0.0)
    enterable, bad_enterable = _flag(raw.get("enterable", False), f"{where}.enterable")

    # Strange rather than invalid: a pack may mean it, and refusing a coherent
    # world over an odd declaration would be the wrong trade.
    warnings = (
        (
            f"{where}: {material!r} is declared enterable, which beings will be "
            f"told they can walk into",
        )
        if enterable and material not in _WALKABLE
        else ()
    )

    return (
        Feature(
            id=ident,
            pos=pos,
            shape=shape,
            description=described,
            material=material,
            colour=colour,
            radius=radius,
            height=height,
            enterable=enterable,
        ),
        (
            *bad_id,
            *bad_shape,
            *bad_material,
            *bad_description,
            *bad_pos,
            *bad_colour,
            *bad_radius,
            *bad_height,
            *bad_enterable,
        ),
        warnings,
    )


#: Materials a being can be told it may walk into without the claim being odd.
_WALKABLE = ("water", "grass", "sand", "earth")


def _placeholder() -> Feature:
    """Stand-in for a feature too malformed to read.

    Returned alongside the error rather than omitted, so ``features[3]`` in a
    later message still refers to the fourth entry the author wrote.
    """
    return Feature(
        id="",
        pos=(0.0, 0.0, 0.0),
        shape=SHAPES[0],
        description="",
        material=MATERIALS[0],
    )


def _feature_id(raw: Any, where: str) -> tuple[str, tuple[WorldError, ...]]:
    """A feature id is also the word a being types into ``[goto:...]``, so an id
    the tag grammar cannot carry is a place nobody can reach — and nothing else
    in the system would ever say so."""
    if not _named(raw):
        return "", (WorldError(where, "required, must be a non-empty string"),)
    if not raw.replace("_", "").replace("-", "").isalnum():
        return "", (
            WorldError(
                where,
                f"{raw!r} is not usable in a tag",
                "letters, digits, hyphen and underscore only — a being refers "
                "to this place by writing [goto:<id>]",
            ),
        )
    return raw, NO_ERRORS


def _description(raw: Any, where: str) -> tuple[str, tuple[WorldError, ...]]:
    if not _named(raw):
        return "", (
            WorldError(
                f"{where}.description",
                "required, must be a non-empty string",
                "this is what a being is told when it looks at the place",
            ),
        )
    return raw.strip(), NO_ERRORS


# --------------------------------------------------------------------------
# leaves
# --------------------------------------------------------------------------


def _one_of(
    raw: Any, allowed: tuple[str, ...], where: str, kind: str
) -> tuple[str, tuple[WorldError, ...]]:
    if raw in allowed:
        return raw, NO_ERRORS
    return allowed[0], (
        WorldError(
            where, f"unknown {kind} {raw!r}", "available: " + ", ".join(allowed)
        ),
    )


def _position(
    raw: Any, where: str
) -> tuple[tuple[float, float, float], tuple[WorldError, ...]]:
    if (
        not isinstance(raw, list | tuple)
        or len(raw) != 3
        or not all(_numeric(v) for v in raw)
    ):
        return (0.0, 0.0, 0.0), (WorldError(where, "must be [x, y, z]"),)
    return (float(raw[0]), float(raw[1]), float(raw[2])), NO_ERRORS


def _colour(raw: Any, where: str) -> tuple[str, tuple[WorldError, ...]]:
    """Hex only. A named colour would mean two lookup tables agreeing across
    two languages, which is exactly the seam this format exists to remove."""
    if not isinstance(raw, str) or not _is_hex(raw):
        return "#000000", (
            WorldError(where, f"expected a hex colour, got {raw!r}", "e.g. #4a5f3a"),
        )
    return raw.lower(), NO_ERRORS


def _number(
    raw: Any, where: str, *, low: float
) -> tuple[float, tuple[WorldError, ...]]:
    if not _numeric(raw):
        return low, (WorldError(where, f"expected a number, got {raw!r}"),)
    if raw < low:
        return low, (WorldError(where, f"must be at least {low}, got {raw}"),)
    return float(raw), NO_ERRORS


def _flag(raw: Any, where: str) -> tuple[bool, tuple[WorldError, ...]]:
    if not isinstance(raw, bool):
        return False, (WorldError(where, f"expected true or false, got {raw!r}"),)
    return raw, NO_ERRORS


def _numeric(raw: Any) -> bool:
    # `True` is an int in Python, and a radius of True would validate and then
    # draw something a millimetre across.
    return isinstance(raw, int | float) and not isinstance(raw, bool)


def _pair(raw: Any) -> bool:
    return (
        isinstance(raw, list | tuple)
        and len(raw) == 2
        and all(_numeric(v) for v in raw)
    )


def _is_hex(value: str) -> bool:
    return (
        len(value) == 7
        and value.startswith("#")
        and all(c in "0123456789abcdefABCDEF" for c in value[1:])
    )


def _named(raw: Any) -> bool:
    return isinstance(raw, str) and bool(raw.strip())


def _text(raw: Any) -> str:
    return raw.strip() if isinstance(raw, str) else ""
