"""The avatar pack format, and its validator.

A pack is a directory holding a model, a manifest describing it, and a
licence. The manifest's job is to translate between Andropia's canonical
vocabulary and whatever the artist happened to name things — so application
code refers to ``happy`` and ``wave`` and never to a rig-specific string.

Three properties shape the design:

* **Conformant VRMs need no mapping at all.** The canonical emotion names
  *are* the VRM standard expression presets, so the common case is an empty
  ``expressions`` block. Elegance here is the default being nothing.
* **Motions are optional.** A pack that ships no clips still works; those
  motions fall back to procedural poses authored in normalised humanoid
  space, which run on any rig.
* **A licence is mandatory.** The schema refuses to validate without one.
  Given how often a badge, a filename or a registry was found to contradict
  the file it described, making provenance structurally required is a
  correctness property of the ecosystem rather than bureaucracy.

Validation is total and cross-checks against the *actual model file*. It
returns every problem at once, and names what the rig really contains —
"clip 'Wave' not found — available: Idle, Walking, …" is the difference
between a format people adopt and one they abandon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..vocab import EMOTIONS, GESTURES

SCHEMA_VERSION = 1
PROTOCOL_VERSION = 1

PackType = Literal["vrm", "gltf"]


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
class Motion:
    """How a canonical gesture is realised for this body.

    ``clip`` names an animation baked into the model. When absent, the
    gesture is produced procedurally, which works on any rig and is why a
    pack may legitimately declare no motions at all.
    """

    clip: str | None = None

    @property
    def procedural(self) -> bool:
        return self.clip is None


@dataclass(frozen=True, slots=True)
class Pack:
    id: str
    name: str
    type: PackType
    model: str
    license: License
    persona: str = ""
    # canonical name -> name in this rig
    expressions: dict[str, str] = field(default_factory=dict)
    motions: dict[str, Motion] = field(default_factory=dict)
    schema: int = SCHEMA_VERSION
    protocol: int = PROTOCOL_VERSION

    def emotion_target(self, canonical: str) -> str | None:
        """The rig-specific name for a canonical emotion, if supported."""
        return self.expressions.get(canonical)

    @property
    def supported_emotions(self) -> tuple[str, ...]:
        """Canonical emotions this body can show.

        ``neutral`` is always included: it is the *absence* of expression —
        every morph at zero — so it needs no mapping and no rig can fail to
        do it. Requiring packs to declare it would be asking artists to name
        a shape that does not exist.
        """
        return tuple(
            e for e in EMOTIONS if e == "neutral" or e in self.expressions
        )

    @property
    def supported_gestures(self) -> tuple[str, ...]:
        """Every gesture this body can perform.

        All of them: those with clips play the clip, the rest are generated.
        A pack never *loses* a gesture by not declaring it.
        """
        return GESTURES


# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PackError:
    field: str
    problem: str
    hint: str = ""

    def __str__(self) -> str:
        base = f"{self.field}: {self.problem}"
        return f"{base}\n    {self.hint}" if self.hint else base


@dataclass(frozen=True, slots=True)
class Invalid:
    errors: tuple[PackError, ...]

    ok: Literal[False] = False

    def __str__(self) -> str:
        lines = "\n".join(f"  - {e}" for e in self.errors)
        return f"{len(self.errors)} problem(s):\n{lines}"


@dataclass(frozen=True, slots=True)
class Valid:
    pack: Pack
    warnings: tuple[str, ...] = ()

    ok: Literal[True] = True


Result = Valid | Invalid


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------


def validate(raw: Any, rig: Any = None) -> Result:
    """Check a manifest, optionally against the model it describes.

    ``rig`` is a :class:`~andropia.packs.gltf.RigFacts`. Passing it turns
    validation from "does this parse" into "does this work", which is the
    only version worth having — so callers should pass it whenever the model
    file is available.

    Every error is collected. Stopping at the first would mean an artist
    fixes one name, re-runs, and discovers the next.
    """
    errors: list[PackError] = []
    warnings: list[str] = []

    if not isinstance(raw, dict):
        return Invalid((PackError("<root>", "manifest must be a JSON object"),))

    # -- versions ---------------------------------------------------------
    schema = raw.get("schema")
    if schema != SCHEMA_VERSION:
        errors.append(
            PackError(
                "schema",
                f"expected {SCHEMA_VERSION}, got {schema!r}",
                "this build reads schema 1 packs",
            )
        )

    protocol = raw.get("protocol", PROTOCOL_VERSION)
    if protocol != PROTOCOL_VERSION:
        warnings.append(
            f"pack targets action protocol {protocol}, this build speaks "
            f"{PROTOCOL_VERSION}; unknown tags will be ignored"
        )

    # -- identity ---------------------------------------------------------
    for key in ("id", "name", "model"):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(PackError(key, "required, must be a non-empty string"))

    pack_type = raw.get("type")
    if pack_type not in ("vrm", "gltf"):
        errors.append(
            PackError("type", f"expected 'vrm' or 'gltf', got {pack_type!r}")
        )

    persona = raw.get("persona", "")
    if not isinstance(persona, str):
        errors.append(PackError("persona", "must be a string"))
        persona = ""

    # -- licence, mandatory ----------------------------------------------
    license_ = _license(raw.get("license"), errors)

    # -- expressions ------------------------------------------------------
    expressions = _expressions(raw, pack_type, rig, errors, warnings)

    # -- motions ----------------------------------------------------------
    motions = _motions(raw, rig, errors, warnings)

    # -- model file consistency ------------------------------------------
    if rig is not None and pack_type == "vrm" and not rig.is_vrm:
        errors.append(
            PackError(
                "type",
                "declared 'vrm' but the model has no VRM extension",
                "either the type is wrong or the file is a plain glTF",
            )
        )

    if errors:
        return Invalid(tuple(errors))

    return Valid(
        Pack(
            id=raw["id"],
            name=raw["name"],
            type=pack_type,
            model=raw["model"],
            license=license_,
            persona=persona,
            expressions=expressions,
            motions=motions,
            schema=schema,
            protocol=protocol,
        ),
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------


def _license(raw: Any, errors: list[PackError]) -> License:
    if not isinstance(raw, dict):
        errors.append(
            PackError(
                "license",
                "required",
                'e.g. {"id": "CC0-1.0", "attribution": "…"} — packs must '
                "state their terms so downstream users can rely on them",
            )
        )
        return License(id="")

    ident = raw.get("id")
    if not isinstance(ident, str) or not ident.strip():
        errors.append(
            PackError("license.id", "required", "an SPDX id where one applies")
        )
        ident = ""

    return License(
        id=ident,
        url=str(raw.get("url", "")),
        attribution=str(raw.get("attribution", "")),
        notice=str(raw.get("notice", "")),
    )


def _expressions(
    raw: dict,
    pack_type: Any,
    rig: Any,
    errors: list[PackError],
    warnings: list[str],
) -> dict[str, str]:
    declared = raw.get("expressions")

    if declared is None:
        if pack_type == "vrm":
            # The canonical names *are* the VRM presets, so a conformant
            # avatar needs no mapping. Derive it from the rig when we can.
            if rig is not None:
                present = set(rig.vrm_expressions)
                mapping = {e: e for e in EMOTIONS if e in present}
                # `neutral` is the rest pose, not a shape; never missing.
                missing = [
                    e for e in EMOTIONS if e != "neutral" and e not in present
                ]
                if missing:
                    warnings.append(
                        "VRM lacks standard presets "
                        f"{', '.join(missing)}; those emotions will not show"
                    )
                return mapping
            return {e: e for e in EMOTIONS if e != "neutral"}

        errors.append(
            PackError(
                "expressions",
                "required for glTF packs",
                "map canonical emotions to this rig's morph names, e.g. "
                '{"happy": "Smiling"}. VRM packs may omit this.',
            )
        )
        return {}

    if not isinstance(declared, dict):
        errors.append(PackError("expressions", "must be an object"))
        return {}

    mapping: dict[str, str] = {}
    available = _available_expressions(rig, pack_type)

    for canonical, rig_name in declared.items():
        if canonical not in EMOTIONS:
            errors.append(
                PackError(
                    f"expressions.{canonical}",
                    "not a canonical emotion",
                    f"expected one of: {', '.join(EMOTIONS)}",
                )
            )
            continue
        if not isinstance(rig_name, str) or not rig_name.strip():
            errors.append(
                PackError(f"expressions.{canonical}", "must be a non-empty string")
            )
            continue
        if available is not None and rig_name not in available:
            errors.append(
                PackError(
                    f"expressions.{canonical}",
                    f"{rig_name!r} is not in the model",
                    _found(available),
                )
            )
            continue
        mapping[canonical] = rig_name

    return mapping


def _motions(
    raw: dict, rig: Any, errors: list[PackError], warnings: list[str]
) -> dict[str, Motion]:
    declared = raw.get("motions")
    if declared is None:
        return {}

    if not isinstance(declared, dict):
        errors.append(PackError("motions", "must be an object"))
        return {}

    motions: dict[str, Motion] = {}
    clips = tuple(rig.clips) if rig is not None else None

    for canonical, spec in declared.items():
        if canonical not in GESTURES:
            errors.append(
                PackError(
                    f"motions.{canonical}",
                    "not a canonical gesture",
                    f"expected one of: {', '.join(GESTURES)}",
                )
            )
            continue

        if not isinstance(spec, dict):
            errors.append(
                PackError(
                    f"motions.{canonical}",
                    'must be an object, e.g. {"clip": "Wave"}',
                )
            )
            continue

        clip = spec.get("clip")
        if clip is None:
            # Explicitly procedural. Legitimate, and the default anyway.
            motions[canonical] = Motion()
            continue

        if not isinstance(clip, str) or not clip.strip():
            errors.append(
                PackError(
                    f"motions.{canonical}.clip", "must be a non-empty string"
                )
            )
            continue

        if clips is not None and clip not in clips:
            errors.append(
                PackError(
                    f"motions.{canonical}.clip",
                    f"{clip!r} is not in the model",
                    _found(clips),
                )
            )
            continue

        motions[canonical] = Motion(clip=clip)

    return motions


def _available_expressions(rig: Any, pack_type: Any) -> tuple[str, ...] | None:
    if rig is None:
        return None
    if pack_type == "vrm" and rig.is_vrm:
        return tuple(rig.vrm_expressions)
    return tuple(rig.morphs)


def _found(names: tuple[str, ...]) -> str:
    """Say what the rig actually has.

    The single most useful line in any error this module produces: it turns
    "that name is wrong" into "here is the name you meant".
    """
    if not names:
        return "the model declares none at all"
    listed = ", ".join(sorted(names)[:12])
    more = f" (+{len(names) - 12} more)" if len(names) > 12 else ""
    return f"available: {listed}{more}"
