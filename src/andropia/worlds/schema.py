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


def validate(raw: Any) -> Result:
    """Check a world manifest. Pure, and total: every problem at once."""
    if not isinstance(raw, dict):
        return Invalid((WorldError("<root>", "manifest must be a JSON object"),))

    errors: list[WorldError] = []
    warnings: list[str] = []

    version = raw.get("schema")
    if version != SCHEMA_VERSION:
        errors.append(
            WorldError(
                "schema",
                f"expected {SCHEMA_VERSION}, got {version!r}",
                f"this build reads schema {SCHEMA_VERSION} world packs",
            )
        )

    for key in ("id", "name"):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(WorldError(key, "required, must be a non-empty string"))

    licence = _license(raw, errors)
    ground = _ground(raw.get("ground", {}), errors)
    sky = _sky(raw.get("sky", {}), errors)
    light = _light(raw.get("light", {}), errors)
    features = _features(raw.get("features", []), errors, warnings)

    atmosphere = raw.get("atmosphere", "")
    if not isinstance(atmosphere, str):
        errors.append(WorldError("atmosphere", "must be a string"))
        atmosphere = ""

    if errors:
        return Invalid(tuple(errors))

    return Valid(
        WorldPack(
            id=raw["id"],
            name=raw["name"],
            license=licence,
            ground=ground,
            sky=sky,
            light=light,
            features=features,
            atmosphere=atmosphere.strip(),
        ),
        tuple(warnings),
    )


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------


def _license(raw: dict, errors: list[WorldError]) -> License:
    """A licence is required, for the same reason it is on an avatar pack:
    every time provenance was optional, something turned out to contradict its
    own label."""
    block = raw.get("license")
    if not isinstance(block, dict):
        errors.append(
            WorldError(
                "license",
                "required",
                'every pack must declare its terms, e.g. {"id": "CC0-1.0"}',
            )
        )
        return License(id="")

    ident = block.get("id")
    if not isinstance(ident, str) or not ident.strip():
        errors.append(WorldError("license.id", "required, must be a non-empty string"))
        ident = ""

    return License(
        id=ident,
        url=_text(block.get("url", "")),
        attribution=_text(block.get("attribution", "")),
        notice=_text(block.get("notice", "")),
    )


def _ground(raw: Any, errors: list[WorldError]) -> Ground:
    if not isinstance(raw, dict):
        errors.append(WorldError("ground", "must be an object"))
        return Ground()

    extent = _number(raw.get("extent", 200.0), "ground.extent", errors, low=1.0)
    return Ground(
        colour=_colour(raw.get("colour", "#151a1f"), "ground.colour", errors),
        extent=extent,
        grid=_flag(raw.get("grid", True), "ground.grid", errors),
        description=_text(raw.get("description", "level ground")) or "level ground",
    )


def _sky(raw: Any, errors: list[WorldError]) -> Sky:
    if not isinstance(raw, dict):
        errors.append(WorldError("sky", "must be an object"))
        return Sky()

    fog = raw.get("fog")
    near_far: tuple[float, float] | None = None
    if fog is not None:
        if (
            not isinstance(fog, list | tuple)
            or len(fog) != 2
            or not all(isinstance(v, int | float) for v in fog)
        ):
            errors.append(
                WorldError("sky.fog", "must be [near, far]", "or omit it for no fog")
            )
        elif fog[0] >= fog[1]:
            errors.append(
                WorldError("sky.fog", f"near {fog[0]} is not before far {fog[1]}")
            )
        else:
            near_far = (float(fog[0]), float(fog[1]))

    return Sky(
        colour=_colour(raw.get("colour", "#0e1114"), "sky.colour", errors),
        fog=near_far,
        description=_text(raw.get("description", "an empty dark sky"))
        or "an empty dark sky",
    )


def _light(raw: Any, errors: list[WorldError]) -> Light:
    if not isinstance(raw, dict):
        errors.append(WorldError("light", "must be an object"))
        return Light()

    return Light(
        key=_number(raw.get("key", 2.0), "light.key", errors, low=0.0),
        sky_colour=_colour(
            raw.get("sky_colour", "#9fb8cc"), "light.sky_colour", errors
        ),
        ground_colour=_colour(
            raw.get("ground_colour", "#1a1f24"), "light.ground_colour", errors
        ),
    )


def _features(
    raw: Any, errors: list[WorldError], warnings: list[str]
) -> tuple[Feature, ...]:
    if not isinstance(raw, list):
        errors.append(WorldError("features", "must be a list"))
        return ()

    out: list[Feature] = []
    seen: set[str] = set()

    for index, item in enumerate(raw):
        where = f"features[{index}]"
        if not isinstance(item, dict):
            errors.append(WorldError(where, "must be an object"))
            continue

        ident = item.get("id")
        if not isinstance(ident, str) or not ident.strip():
            errors.append(
                WorldError(f"{where}.id", "required, must be a non-empty string")
            )
            ident = ""
        elif not ident.replace("_", "").replace("-", "").isalnum():
            # A feature id is also the word a being types into [goto:...], so
            # it has to survive the tag grammar or the place is unreachable.
            errors.append(
                WorldError(
                    f"{where}.id",
                    f"{ident!r} is not usable in a tag",
                    "letters, digits, hyphen and underscore only — a being "
                    "refers to this place by writing [goto:<id>]",
                )
            )
        elif ident in seen:
            errors.append(
                WorldError(
                    f"{where}.id",
                    f"{ident!r} appears more than once",
                    "a being names a place by its id and cannot disambiguate two",
                )
            )
        else:
            seen.add(ident)

        shape = item.get("shape")
        if shape not in SHAPES:
            errors.append(
                WorldError(f"{where}.shape", f"unknown shape {shape!r}", _found(SHAPES))
            )

        material = item.get("material")
        if material not in MATERIALS:
            errors.append(
                WorldError(
                    f"{where}.material",
                    f"unknown material {material!r}",
                    _found(MATERIALS),
                )
            )

        description = item.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append(
                WorldError(
                    f"{where}.description",
                    "required, must be a non-empty string",
                    "this is what a being is told when it looks at the place",
                )
            )
            description = ""

        pos = _position(item.get("pos"), f"{where}.pos", errors)

        enterable = _flag(item.get("enterable", False), f"{where}.enterable", errors)
        if enterable and material not in ("water", "grass", "sand", "earth"):
            warnings.append(
                f"{where}: {material!r} is declared enterable, which beings will "
                f"be told they can walk into"
            )

        out.append(
            Feature(
                id=ident,
                pos=pos,
                shape=shape if shape in SHAPES else SHAPES[0],
                description=description.strip(),
                material=material if material in MATERIALS else MATERIALS[0],
                colour=_colour(
                    item.get("colour", "#3a444e"), f"{where}.colour", errors
                ),
                radius=_number(
                    item.get("radius", 1.0), f"{where}.radius", errors, low=0.0
                ),
                height=_number(
                    item.get("height", 1.0), f"{where}.height", errors, low=0.0
                ),
                enterable=enterable,
            )
        )

    return tuple(out)


def _position(
    raw: Any, where: str, errors: list[WorldError]
) -> tuple[float, float, float]:
    if (
        not isinstance(raw, list | tuple)
        or len(raw) != 3
        or not all(isinstance(v, int | float) for v in raw)
    ):
        errors.append(WorldError(where, "must be [x, y, z]"))
        return (0.0, 0.0, 0.0)
    return (float(raw[0]), float(raw[1]), float(raw[2]))


def _colour(raw: Any, where: str, errors: list[WorldError]) -> str:
    """Hex only. A named colour would mean two lookup tables agreeing across
    two languages, which is exactly the kind of seam this format exists to
    remove."""
    if not isinstance(raw, str) or not _is_hex(raw):
        errors.append(
            WorldError(where, f"expected a hex colour, got {raw!r}", "e.g. #4a5f3a")
        )
        return "#000000"
    return raw.lower()


def _is_hex(value: str) -> bool:
    return (
        len(value) == 7
        and value.startswith("#")
        and all(c in "0123456789abcdefABCDEF" for c in value[1:])
    )


def _number(raw: Any, where: str, errors: list[WorldError], *, low: float) -> float:
    if not isinstance(raw, int | float) or isinstance(raw, bool):
        errors.append(WorldError(where, f"expected a number, got {raw!r}"))
        return low
    if raw < low:
        errors.append(WorldError(where, f"must be at least {low}, got {raw}"))
        return low
    return float(raw)


def _flag(raw: Any, where: str, errors: list[WorldError]) -> bool:
    if not isinstance(raw, bool):
        errors.append(WorldError(where, f"expected true or false, got {raw!r}"))
        return False
    return raw


def _text(raw: Any) -> str:
    return raw.strip() if isinstance(raw, str) else ""


def _found(names: tuple[str, ...]) -> str:
    return "available: " + ", ".join(names)
