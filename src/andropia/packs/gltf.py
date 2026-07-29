"""Reading what a model file actually contains.

A minimal GLB/VRM header parser: enough to answer "which animation clips and
which morph targets does this file really have?", and nothing more. No
dependency on a glTF library, because loading geometry is the renderer's job
and this only needs the JSON chunk.

This exists so pack validation can be *evidence* rather than assertion. A
manifest that merely parses is not a manifest that works — the interesting
failure is a manifest naming a clip the rig does not have, and catching that
requires opening the file.

VRM is glTF underneath, so the same parser handles both. Its expression
presets live in a ``VRMC_vrm`` (1.x) or ``VRM`` (0.x) extension.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

_GLB_MAGIC = b"glTF"
_JSON_CHUNK = 0x4E4F534A


@dataclass(frozen=True, slots=True)
class RigFacts:
    """What a model file demonstrably contains."""

    clips: tuple[str, ...] = ()
    morphs: tuple[str, ...] = ()
    vrm_expressions: tuple[str, ...] = ()
    vrm_version: str | None = None
    is_vrm: bool = False
    # Present only for VRM, which embeds its own licence terms. Surfaced so a
    # pack whose manifest contradicts the file it describes can be caught.
    vrm_meta: dict = field(default_factory=dict)


class MalformedModel(Exception):
    """The file is not a readable GLB."""


def read_rig_facts(path: Path) -> RigFacts:
    """Parse a ``.glb`` or ``.vrm`` and report its capabilities."""
    data = path.read_bytes()
    doc = _json_chunk(data)

    clips = tuple(
        a["name"] for a in doc.get("animations", []) if isinstance(a.get("name"), str)
    )

    # Morph target names live in mesh `extras`, by glTF convention. A mesh
    # may declare them once for all its primitives.
    morphs: list[str] = []
    for mesh in doc.get("meshes", []):
        names = mesh.get("extras", {}).get("targetNames")
        if isinstance(names, list):
            morphs.extend(n for n in names if isinstance(n, str))

    extensions = doc.get("extensions", {})
    vrm_1 = extensions.get("VRMC_vrm")
    vrm_0 = extensions.get("VRM")

    if vrm_1 is not None:
        presets = tuple((vrm_1.get("expressions", {}).get("preset") or {}).keys())
        meta = vrm_1.get("meta", {}) or {}
        version = vrm_1.get("specVersion") or meta.get("version") or "1.0"
    elif vrm_0 is not None:
        # 0.x calls them blend shape groups and keys them by `presetName`.
        groups = (vrm_0.get("blendShapeMaster", {}) or {}).get("blendShapeGroups", [])
        presets = tuple(
            g["presetName"]
            for g in groups
            if isinstance(g.get("presetName"), str) and g["presetName"] != "unknown"
        )
        meta = vrm_0.get("meta", {}) or {}
        version = vrm_0.get("specVersion") or "0.x"
    else:
        presets, meta, version = (), {}, None

    return RigFacts(
        clips=clips,
        morphs=tuple(dict.fromkeys(morphs)),  # dedupe, keep order
        vrm_expressions=presets,
        vrm_version=version,
        is_vrm=vrm_1 is not None or vrm_0 is not None,
        vrm_meta=meta,
    )


def _json_chunk(data: bytes) -> dict:
    if len(data) < 12 or data[:4] != _GLB_MAGIC:
        raise MalformedModel(
            "not a binary glTF — expected a .glb or .vrm "
            "(a text .gltf must be converted first)"
        )

    _, version, _ = struct.unpack("<III", data[:12])
    if version != 2:
        raise MalformedModel(f"glTF version {version} is not supported (expected 2)")

    if len(data) < 20:
        raise MalformedModel("truncated: no chunk header")

    length, kind = struct.unpack("<II", data[12:20])
    if kind != _JSON_CHUNK:
        raise MalformedModel("first chunk is not JSON, which a valid GLB requires")
    if 20 + length > len(data):
        raise MalformedModel("truncated: JSON chunk extends past end of file")

    try:
        return json.loads(data[20 : 20 + length])
    except json.JSONDecodeError as exc:
        raise MalformedModel(f"JSON chunk is not valid JSON: {exc}") from exc
