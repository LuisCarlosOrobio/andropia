"""The HTTP and WebSocket surface.

Driven through Starlette's TestClient, so a real ASGI stack runs but no
socket is bound. The session starts paused in these tests, which makes them
deterministic: nothing advances unless a test asks it to.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from andropia.runtime.server import create_app, demo_world


@pytest.fixture
def client():
    with TestClient(create_app(demo_world())) as c:
        yield c


# --------------------------------------------------------------------------
# state and control
# --------------------------------------------------------------------------


def test_state_reports_a_paused_world(client):
    s = client.get("/api/state").json()

    assert s["mode"] == "paused"
    assert s["tick"] == 0
    assert s["entities"] == 3
    assert s["speed"] == 1.0


def test_step_advances_exactly_one_tick(client):
    client.post("/api/control/step")
    assert client.get("/api/state").json()["tick"] == 1

    client.post("/api/control/step")
    assert client.get("/api/state").json()["tick"] == 2


def test_advance_fast_forwards(client):
    client.post("/api/control/advance", json={"ticks": 250})
    assert client.get("/api/state").json()["tick"] == 250


def test_pause_and_resume_round_trip(client):
    assert client.post("/api/control/resume").json()["mode"] == "running"
    assert client.post("/api/control/pause").json()["mode"] == "paused"


def test_speed_is_validated(client):
    assert client.post("/api/control/speed", json={"value": 8.0}).json()["speed"] == 8.0
    assert client.post("/api/control/speed", json={"value": -1.0}).status_code == 400


def test_unknown_command_is_404(client):
    assert client.post("/api/control/detonate").status_code == 404


# --------------------------------------------------------------------------
# intents
# --------------------------------------------------------------------------


def test_goto_intent_is_queued_then_applied(client):
    r = client.post("/api/intent", json={"kind": "goto", "entity": "ava", "target": "pond"})
    assert r.json()["queued"] == 1

    client.post("/api/control/step")

    with client.websocket_connect("/ws/view") as ws:
        ws.receive_json()  # scene
        frame = ws.receive_json()

    ava = next(e for e in frame["entities"] if e["id"] == "ava")
    assert ava["action"] == "walk"


def test_moveto_accepts_a_bare_position(client):
    """Clicking the ground sends coordinates, not a landmark name."""
    r = client.post(
        "/api/intent", json={"kind": "moveto", "entity": "ava", "pos": [5.0, 0.0, 5.0]}
    )
    assert r.status_code == 200

    client.post("/api/control/step")

    with client.websocket_connect("/ws/view") as ws:
        ws.receive_json()
        frame = ws.receive_json()

    ava = next(e for e in frame["entities"] if e["id"] == "ava")
    assert ava["action"] == "walk"
    assert ava["target"] == [5.0, 0.0, 5.0]


def test_malformed_position_is_rejected(client):
    r = client.post("/api/intent", json={"kind": "moveto", "entity": "ava", "pos": "nope"})
    assert r.status_code == 400


def test_unknown_intent_kind_is_rejected(client):
    r = client.post("/api/intent", json={"kind": "levitate", "entity": "ava"})
    assert r.status_code == 400


def test_intent_with_missing_field_is_rejected(client):
    r = client.post("/api/intent", json={"kind": "goto", "entity": "ava"})
    assert r.status_code == 400


# --------------------------------------------------------------------------
# the view socket
# --------------------------------------------------------------------------


def test_connect_receives_scene_then_frame(client):
    with client.websocket_connect("/ws/view") as ws:
        scene = ws.receive_json()
        frame = ws.receive_json()

    assert scene["type"] == "scene"
    assert {m["id"] for m in scene["landmarks"]} == {"tree", "pond", "rock"}
    assert scene["dt"] == 0.05

    assert frame["type"] == "frame"
    assert {e["id"] for e in frame["entities"]} == {"ava", "mistral", "claude"}


def test_scene_is_sent_once_not_per_tick(client):
    """Landmarks do not move; re-sending them 20 times a second is waste."""
    with client.websocket_connect("/ws/view") as ws:
        ws.receive_json()
        first = ws.receive_json()
        ws.send_json({"type": "step"})
        second = ws.receive_json()

    assert "landmarks" not in first
    assert "landmarks" not in second


def test_control_over_the_view_socket(client):
    with client.websocket_connect("/ws/view") as ws:
        ws.receive_json()
        ws.receive_json()

        ws.send_json({"type": "step"})
        frame = ws.receive_json()

    assert frame["tick"] == 1


def test_intent_over_the_view_socket(client):
    with client.websocket_connect("/ws/view") as ws:
        ws.receive_json()
        ws.receive_json()

        ws.send_json(
            {"type": "intent", "intent": {"kind": "goto", "entity": "ava", "target": "tree"}}
        )
        ws.send_json({"type": "step"})
        frame = ws.receive_json()

    ava = next(e for e in frame["entities"] if e["id"] == "ava")
    assert ava["action"] == "walk"


def test_a_malformed_message_does_not_kill_the_socket(client):
    """A viewer sending nonsense should not take the connection down."""
    with client.websocket_connect("/ws/view") as ws:
        ws.receive_json()
        ws.receive_json()

        ws.send_json({"type": "nonsense"})
        ws.send_json({"type": "step"})
        frame = ws.receive_json()

    assert frame["tick"] == 1


def test_viewer_count_is_tracked(client):
    assert client.get("/api/state").json()["viewers"] == 0

    with client.websocket_connect("/ws/view") as ws:
        ws.receive_json()
        ws.receive_json()
        assert client.get("/api/state").json()["viewers"] == 1

    assert client.get("/api/state").json()["viewers"] == 0


# --------------------------------------------------------------------------
# regressions
# --------------------------------------------------------------------------


def test_intents_proposed_between_ticks_are_not_lost(client):
    """Regression: the tick loop must not own a private copy of the session.

    The first version drove the world with ``clock.drive``, which threads a
    session through its own loop. An intent proposed by an HTTP handler
    landed on ``hub.session`` and was then silently overwritten when the loop
    wrote back its own copy — so the world ran perfectly and simply ignored
    every instruction. Unit tests missed it because they never had a tick
    loop and an HTTP handler racing for the same value.
    """
    hub = client.app.state.hub

    # Interleave: propose, tick, propose, tick — as a live client would.
    client.post("/api/intent", json={"kind": "goto", "entity": "ava", "target": "pond"})
    client.post("/api/control/step")
    client.post("/api/intent", json={"kind": "gesture", "entity": "mistral", "motion": "wave"})
    client.post("/api/control/step")

    assert hub.session.world.entities["ava"].action.kind == "walk"
    assert hub.session.world.entities["mistral"].action.kind == "gesture"


def test_the_hub_is_the_single_owner_of_the_session(client):
    """State visible over HTTP and over the socket must be the same object."""
    hub = client.app.state.hub
    client.post("/api/control/advance", json={"ticks": 7})

    over_http = client.get("/api/state").json()["tick"]
    with client.websocket_connect("/ws/view") as ws:
        ws.receive_json()
        over_socket = ws.receive_json()["tick"]

    assert over_http == over_socket == hub.session.world.tick == 7
