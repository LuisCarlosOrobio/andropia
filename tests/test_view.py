"""The wire projection.

Pure, so these are plain input/output tables. The point of the module is that
the wire format is decoupled from ``World``; the point of these tests is that
it stays that way — every field asserted here is one a renderer depends on.
"""

from __future__ import annotations

import json

from andropia.runtime import view
from andropia.sim import (
    DoGesture,
    Emote,
    Entity,
    Goto,
    Landmark,
    Look,
    Speak,
    Vec3,
    World,
    run,
    step,
)


def a_world() -> World:
    return World(
        entities={
            "ava": Entity(id="ava", pos=Vec3(1.0, 0.0, 2.0), avatar_pack="ava"),
            "bo": Entity(id="bo", pos=Vec3(-3.0, 0.0, 1.0), avatar_pack="robot"),
        },
        landmarks={"pond": Landmark("pond", Vec3(-8.0, 0.0, 3.0), "the pond")},
    )


def test_view_is_json_serialisable():
    """The whole point of a projection: it must survive the wire."""
    payload = view.view(a_world())
    assert json.loads(json.dumps(payload)) == payload


def test_entities_are_sorted_not_dict_ordered():
    """A renderer diffing frames should never see a spurious reorder."""
    forward = World(entities={"a": Entity(id="a"), "z": Entity(id="z")})
    reverse = World(entities={"z": Entity(id="z"), "a": Entity(id="a")})

    assert [e["id"] for e in view.frame(forward)["entities"]] == ["a", "z"]
    assert view.frame(forward) == view.frame(reverse)


def test_frame_carries_position_and_facing():
    f = view.frame(a_world())
    ava = next(e for e in f["entities"] if e["id"] == "ava")

    assert ava["pos"] == [1.0, 0.0, 2.0]
    assert len(ava["facing"]) == 3
    assert ava["pack"] == "ava"


def test_scene_carries_landmarks_and_dt():
    s = view.scene(a_world())
    assert s["dt"] == 0.05
    assert s["landmarks"][0]["id"] == "pond"
    assert s["landmarks"][0]["description"] == "the pond"


def test_walk_target_only_present_while_walking():
    w = a_world()
    assert "target" not in view.frame(w)["entities"][0]

    w = step(w, (Goto(entity="ava", target="pond"),))
    ava = next(e for e in view.frame(w)["entities"] if e["id"] == "ava")

    assert ava["action"] == "walk"
    assert ava["target"] == [-8.0, 0.0, 3.0]


def test_gesture_phase_is_normalised():
    """The renderer should not need to know how long a gesture lasts."""
    w = step(a_world(), (DoGesture(entity="ava", motion="wave"),))
    ava = next(e for e in view.frame(w)["entities"] if e["id"] == "ava")

    assert ava["action"] == "gesture"
    assert ava["motion"] == "wave"
    assert 0.0 < ava["motionPhase"] < 1.0

    w = run(w, [() for _ in range(15)])
    ava = next(e for e in view.frame(w)["entities"] if e["id"] == "ava")
    assert ava["motionPhase"] > 0.4


def test_speech_appears_and_disappears():
    w = step(a_world(), (Speak(entity="ava", text="over here"),))
    ava = next(e for e in view.frame(w)["entities"] if e["id"] == "ava")
    assert ava["speech"]["text"] == "over here"

    w = run(w, [() for _ in range(200)])
    ava = next(e for e in view.frame(w)["entities"] if e["id"] == "ava")
    assert "speech" not in ava


def test_gaze_only_present_when_looking():
    w = a_world()
    assert "gaze" not in view.frame(w)["entities"][0]

    w = step(w, (Look(entity="ava", at="bo"),))
    ava = next(e for e in view.frame(w)["entities"] if e["id"] == "ava")
    assert ava["gaze"] == "bo"


def test_emotion_and_weight_are_reported():
    w = step(a_world(), (Emote(entity="ava", emotion="happy"),))
    ava = next(e for e in view.frame(w)["entities"] if e["id"] == "ava")

    assert ava["emotion"] == "happy"
    assert ava["emotionWeight"] > 0.9


def test_view_leaks_no_internal_state():
    """Memory, RNG streams and velocity are the simulation's business.

    Sending them would couple the wire format to the internal model and
    invite renderers to depend on things that may change.
    """
    payload = json.dumps(view.view(a_world()))
    for internal in ("memory", "rng", "vel", "turn_rate", "started_at"):
        assert internal not in payload


def test_frame_is_smaller_than_a_full_snapshot():
    """Per-tick payloads exclude landmarks, which never move."""
    w = a_world()
    assert len(json.dumps(view.frame(w))) < len(json.dumps(view.view(w)))
