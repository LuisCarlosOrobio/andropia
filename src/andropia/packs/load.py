"""Loading packs from disk.

The one effectful part of this package: everything in :mod:`schema` is a pure
function of values, and this reads files and hands them over.

Loading always validates against the real model file. There is no "trust the
manifest" path, because the interesting failure — a manifest naming a clip
the rig does not have — is invisible without opening the model.
"""

from __future__ import annotations

import json
from pathlib import Path

from .gltf import MalformedModel, read_rig_facts
from .schema import Invalid, PackError, Result, Valid, validate

MANIFEST = "avatar.json"


def load_pack(directory: Path) -> Result:
    """Read and validate the pack in ``directory``.

    Returns a :class:`~andropia.packs.schema.Valid` or
    :class:`~andropia.packs.schema.Invalid` rather than raising: a broken
    pack is an ordinary thing a user will hit while making one, and it
    deserves a list of problems rather than a traceback.
    """
    manifest_path = directory / MANIFEST

    if not manifest_path.is_file():
        return Invalid(
            (
                PackError(
                    MANIFEST,
                    f"not found in {directory}",
                    "a pack is a directory containing avatar.json and a model",
                ),
            )
        )

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return Invalid(
            (PackError(MANIFEST, f"is not valid JSON: {exc}", f"at line {exc.lineno}"),)
        )
    except OSError as exc:
        return Invalid((PackError(MANIFEST, f"could not be read: {exc}"),))

    model_name = raw.get("model") if isinstance(raw, dict) else None
    rig = None
    model_errors: list[PackError] = []

    if isinstance(model_name, str) and model_name:
        model_path = directory / model_name
        if not model_path.is_file():
            model_errors.append(
                PackError(
                    "model",
                    f"{model_name!r} not found in {directory}",
                    _nearby_models(directory),
                )
            )
        else:
            try:
                rig = read_rig_facts(model_path)
            except MalformedModel as exc:
                model_errors.append(PackError("model", str(exc)))

    result = validate(raw, rig)

    if model_errors:
        existing = result.errors if isinstance(result, Invalid) else ()
        return Invalid((*model_errors, *existing))

    return result


def discover(root: Path) -> dict[str, Result]:
    """Load every pack directly under ``root``.

    Returns results keyed by directory name — including the failures, so a
    caller can report which packs are broken rather than silently offering a
    shorter list than the user expects.
    """
    if not root.is_dir():
        return {}

    out: dict[str, Result] = {}
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / MANIFEST).is_file():
            out[child.name] = load_pack(child)
    return out


def valid_packs(root: Path) -> dict[str, object]:
    """Just the packs that loaded, keyed by their declared id."""
    return {
        result.pack.id: result.pack
        for result in discover(root).values()
        if isinstance(result, Valid)
    }


def _nearby_models(directory: Path) -> str:
    """Name the model files that *are* present.

    Same reasoning as listing a rig's real clips: telling someone what exists
    is far more useful than telling them what does not.
    """
    found = sorted(
        p.name for p in directory.iterdir() if p.suffix.lower() in (".glb", ".vrm")
    )
    if not found:
        return "no .glb or .vrm files in this directory"
    return f"found: {', '.join(found)}"
