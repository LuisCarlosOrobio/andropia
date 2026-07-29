"""Avatar packs: the format, its validator, and the bundled examples.

The validator's job is not to accept good manifests — that is easy — but to
*explain* bad ones. Several tests below assert on error text rather than just
on failure, because "clip 'Waev' not found — available: Wave, Yes, No…" is
the difference between a format someone adopts and one they give up on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from andropia.packs import (
    Invalid,
    MalformedModel,
    Valid,
    load_pack,
    read_rig_facts,
    validate,
)
from andropia.packs.gltf import RigFacts
from andropia.vocab import EMOTIONS, GESTURES

REPO = Path(__file__).resolve().parents[1]
ROBOT = REPO / "avatars" / "robot"


def minimal(**overrides) -> dict:
    base = {
        "schema": 1,
        "id": "x",
        "name": "X",
        "type": "gltf",
        "model": "x.glb",
        "expressions": {"happy": "Smile"},
        "license": {"id": "CC0-1.0"},
    }
    base.update(overrides)
    return base


def rig(clips=(), morphs=(), vrm_expressions=(), is_vrm=False) -> RigFacts:
    return RigFacts(
        clips=tuple(clips),
        morphs=tuple(morphs),
        vrm_expressions=tuple(vrm_expressions),
        is_vrm=is_vrm,
    )


def errors_for(result, field_prefix: str) -> list:
    return [e for e in result.errors if e.field.startswith(field_prefix)]


# --------------------------------------------------------------------------
# reading a real model
# --------------------------------------------------------------------------


def test_reads_clips_and_morphs_from_a_real_glb():
    facts = read_rig_facts(ROBOT / "RobotExpressive.glb")

    assert "Wave" in facts.clips
    assert "Dance" in facts.clips
    assert len(facts.clips) == 14
    assert set(facts.morphs) == {"Angry", "Surprised", "Sad"}
    assert not facts.is_vrm


def test_a_non_glb_is_rejected_with_a_useful_message(tmp_path):
    fake = tmp_path / "not.glb"
    fake.write_text("this is not a model")

    with pytest.raises(MalformedModel, match="not a binary glTF"):
        read_rig_facts(fake)


def test_a_truncated_glb_is_rejected(tmp_path):
    import struct

    fake = tmp_path / "cut.glb"
    fake.write_bytes(b"glTF" + struct.pack("<II", 2, 999) + struct.pack("<II", 500, 0x4E4F534A))

    with pytest.raises(MalformedModel, match="truncated"):
        read_rig_facts(fake)


# --------------------------------------------------------------------------
# the bundled packs
# --------------------------------------------------------------------------


def test_the_robot_pack_is_valid():
    result = load_pack(ROBOT)
    assert result.ok, str(result)


def test_the_robot_maps_only_expressions_it_actually_has():
    """A rig with three morphs must not claim six emotions.

    Unsupported emotions are left out of the model's prompt entirely, rather
    than accepted and silently ignored at render time.
    """
    pack = load_pack(ROBOT).pack

    assert set(pack.supported_emotions) == {"neutral", "angry", "sad", "surprised"}
    assert "happy" not in pack.supported_emotions


def test_neutral_needs_no_morph():
    """Neutral is the absence of expression, so every rig can do it."""
    pack = load_pack(ROBOT).pack

    assert "neutral" in pack.supported_emotions
    assert pack.emotion_target("neutral") is None


def test_every_gesture_is_available_clip_backed_or_not():
    """A pack never loses a gesture by not declaring it."""
    pack = load_pack(ROBOT).pack

    assert set(pack.supported_gestures) == set(GESTURES)
    assert pack.motions["wave"].clip == "Wave"
    assert not pack.motions["wave"].procedural
    assert "shrug" not in pack.motions  # falls back to procedural


def test_the_ava_manifest_is_wellformed_without_its_model():
    """The VRM is fetched, not committed. The manifest must still parse.

    Validated without a rig, which is the "does this parse" path; loading the
    directory once the model is present exercises the stronger one.
    """
    raw = json.loads((REPO / "avatars" / "ava" / "avatar.json").read_text())
    result = validate(raw, rig=None)

    assert result.ok, str(result)
    assert result.pack.type == "vrm"
    assert "pixiv" in result.pack.license.attribution


def test_the_ava_licence_is_not_claimed_as_apache():
    """The bundled VRM is redistributable but not sublicensed.

    Guards against a future edit quietly relabelling it, which is exactly the
    mistake this project found in other repositories.
    """
    raw = json.loads((REPO / "avatars" / "ava" / "avatar.json").read_text())
    notice = raw["license"]["notice"].lower()

    assert "not apache" in notice
    assert raw["license"]["id"] != "Apache-2.0"


# --------------------------------------------------------------------------
# validation — the error messages are the product
# --------------------------------------------------------------------------


def test_a_missing_clip_names_what_the_rig_does_have():
    result = validate(
        minimal(motions={"wave": {"clip": "Waev"}}),
        rig(clips=("Wave", "Yes", "No"), morphs=("Smile",)),
    )

    assert isinstance(result, Invalid)
    err = errors_for(result, "motions.wave.clip")[0]
    assert "Waev" in err.problem
    assert "Wave" in err.hint and "Yes" in err.hint


def test_a_missing_morph_names_what_the_rig_does_have():
    result = validate(
        minimal(expressions={"happy": "Grin"}), rig(morphs=("Smile", "Frown"))
    )

    assert isinstance(result, Invalid)
    err = errors_for(result, "expressions.happy")[0]
    assert "Smile" in err.hint and "Frown" in err.hint


def test_an_empty_rig_says_so_rather_than_listing_nothing():
    result = validate(minimal(expressions={"happy": "Grin"}), rig(morphs=()))

    err = errors_for(result, "expressions.happy")[0]
    assert "none at all" in err.hint


def test_every_error_is_reported_not_just_the_first():
    """An artist should fix a pack in one pass, not discover problems
    one re-run at a time."""
    result = validate(
        minimal(
            expressions={"happy": "Nope", "sad": "AlsoNope"},
            motions={"wave": {"clip": "Missing"}, "nod": {"clip": "AlsoMissing"}},
        ),
        rig(clips=("Idle",), morphs=("Smile",)),
    )

    assert isinstance(result, Invalid)
    assert len(result.errors) == 4


def test_a_licence_is_mandatory():
    raw = minimal()
    del raw["license"]
    result = validate(raw)

    assert isinstance(result, Invalid)
    assert errors_for(result, "license")


def test_a_licence_without_an_id_is_rejected():
    result = validate(minimal(license={"url": "http://example.com"}))
    assert isinstance(result, Invalid)
    assert errors_for(result, "license.id")


def test_an_unknown_emotion_is_rejected_with_the_valid_set():
    result = validate(minimal(expressions={"ecstatic": "Grin"}))

    assert isinstance(result, Invalid)
    err = errors_for(result, "expressions.ecstatic")[0]
    for emotion in EMOTIONS:
        assert emotion in err.hint


def test_an_unknown_gesture_is_rejected_with_the_valid_set():
    result = validate(minimal(motions={"backflip": {"clip": "Dance"}}))

    assert isinstance(result, Invalid)
    err = errors_for(result, "motions.backflip")[0]
    assert "wave" in err.hint


def test_a_gltf_pack_must_declare_expressions():
    """Only VRM gets to omit them, because only VRM standardises the names."""
    raw = minimal()
    del raw["expressions"]
    result = validate(raw)

    assert isinstance(result, Invalid)
    assert errors_for(result, "expressions")


def test_a_vrm_pack_may_omit_expressions_entirely():
    result = validate(
        minimal(type="vrm", expressions=None) | {"expressions": None},
        rig(vrm_expressions=EMOTIONS, is_vrm=True),
    )
    # `expressions: null` is treated as absent, the same as omitting the key.
    assert result.ok
    assert set(result.pack.supported_emotions) == set(EMOTIONS)


def test_a_vrm_missing_presets_warns_rather_than_fails():
    """A partial rig is usable; it just cannot show every emotion."""
    raw = minimal(type="vrm")
    del raw["expressions"]

    result = validate(raw, rig(vrm_expressions=("happy", "sad"), is_vrm=True))

    assert result.ok
    assert set(result.pack.supported_emotions) == {"neutral", "happy", "sad"}
    assert any("angry" in w for w in result.warnings)


def test_declaring_vrm_over_a_plain_gltf_is_caught():
    raw = minimal(type="vrm")
    del raw["expressions"]

    result = validate(raw, rig(morphs=("Smile",), is_vrm=False))

    assert isinstance(result, Invalid)
    assert errors_for(result, "type")


def test_a_wrong_schema_version_is_rejected():
    result = validate(minimal(schema=99))
    assert isinstance(result, Invalid)
    assert errors_for(result, "schema")


def test_a_future_protocol_warns_but_loads():
    """A pack from a newer build should degrade, not fail."""
    result = validate(minimal(protocol=99))
    assert result.ok
    assert any("protocol" in w for w in result.warnings)


def test_a_non_object_manifest_is_rejected():
    assert isinstance(validate([1, 2, 3]), Invalid)


# --------------------------------------------------------------------------
# loading from disk
# --------------------------------------------------------------------------


def test_a_missing_manifest_explains_what_a_pack_is(tmp_path):
    result = load_pack(tmp_path)

    assert isinstance(result, Invalid)
    assert "avatar.json" in result.errors[0].field
    assert "directory containing" in result.errors[0].hint


def test_malformed_json_reports_the_line(tmp_path):
    (tmp_path / "avatar.json").write_text('{"schema": 1,,}')
    result = load_pack(tmp_path)

    assert isinstance(result, Invalid)
    assert "line" in result.errors[0].hint


def test_a_missing_model_names_the_files_that_are_there(tmp_path):
    (tmp_path / "avatar.json").write_text(json.dumps(minimal(model="ghost.glb")))
    (tmp_path / "actual.glb").write_bytes(b"glTF")

    result = load_pack(tmp_path)

    assert isinstance(result, Invalid)
    model_err = errors_for(result, "model")[0]
    assert "actual.glb" in model_err.hint


def test_a_directory_with_no_models_says_so(tmp_path):
    (tmp_path / "avatar.json").write_text(json.dumps(minimal()))
    result = load_pack(tmp_path)

    assert isinstance(result, Invalid)
    assert "no .glb or .vrm" in errors_for(result, "model")[0].hint


def test_discover_finds_the_bundled_packs():
    from andropia.packs import discover

    found = discover(REPO / "avatars")

    assert "robot" in found
    assert isinstance(found["robot"], Valid)
    # Ava's model is fetched, not committed, so it is present but incomplete
    # until `fetch.sh` runs — reported rather than silently omitted.
    assert "ava" in found
