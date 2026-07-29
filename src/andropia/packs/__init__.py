"""Avatar packs: bodies a being can wear.

A pack is a directory holding a model, a manifest, and a licence. The
manifest translates between Andropia's canonical vocabulary and whatever the
artist named things, so application code never references a rig-specific
string.

    from andropia.packs import load_pack

    result = load_pack(Path("avatars/robot"))
    if result.ok:
        result.pack.expressions["happy"]   # -> "Surprised" or whatever
    else:
        print(result)                      # every problem, with fixes
"""

from .gltf import MalformedModel, RigFacts, read_rig_facts
from .load import discover, load_pack
from .schema import (
    Invalid,
    License,
    Motion,
    Pack,
    PackError,
    Result,
    Valid,
    validate,
)

__all__ = [
    "Invalid", "License", "MalformedModel", "Motion", "Pack", "PackError",
    "Result", "RigFacts", "Valid", "discover", "load_pack", "read_rig_facts",
    "validate",
]
