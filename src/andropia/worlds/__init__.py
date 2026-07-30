"""World packs: one declaration of a place, drawn and described from the same
fields.

    schema    validate(raw) -> Valid | Invalid      pure
    describe  setting(pack) -> str                  pure

The renderer reads the same manifest. That is the whole idea: a description
that cannot drift from what is drawn, because both come from one file.
"""

from __future__ import annotations
