"""Reading world packs off disk. The shell around a pure validator.

Mirrors :mod:`andropia.packs.load`: a pack is a directory holding a manifest,
discovery reports every pack it found along with why any of them failed, and
nothing here decides whether a pack is good — that is
:func:`andropia.worlds.schema.validate`, which touches no filesystem.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import Invalid, Result, WorldError, validate

MANIFEST = "world.json"


def load_pack(directory: Path) -> Result:
    """Read and validate one world pack directory."""
    manifest = directory / MANIFEST

    if not manifest.is_file():
        return Invalid(
            (
                WorldError(
                    MANIFEST,
                    f"not found in {directory.name}/",
                    f"a world pack is a directory containing {MANIFEST}",
                ),
            )
        )

    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return Invalid((WorldError(MANIFEST, f"is not valid JSON: {exc}"),))
    except OSError as exc:
        return Invalid((WorldError(MANIFEST, f"could not be read: {exc}"),))

    return validate(raw)


def discover(root: Path) -> dict[str, Result]:
    """Every world pack under ``root``, keyed by directory name.

    Failures are returned rather than skipped. A pack that does not load is the
    thing its author most needs to hear about, and dropping it silently is how
    someone spends an afternoon wondering why their world never appears.
    """
    if not root.is_dir():
        return {}

    return {
        directory.name: load_pack(directory)
        for directory in sorted(root.iterdir())
        if directory.is_dir()
    }
