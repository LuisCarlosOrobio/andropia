"""The projection sent to renderers.

    view :: World -> dict

Pure, and deliberately *not* a serialisation of ``World``. A renderer needs
much less than the simulation carries — it has no use for memory, per-being
RNG streams or walk targets — and coupling the wire format to the internal
model would mean every refactor of one broke the other.

Two properties worth keeping as this grows:

* **Derived, never stored.** Bone transforms, animation phase and viseme
  weights are all functions of entity state and are computed by the renderer.
  Sending them would be caching a projection inside the source of truth.
* **A body is a reference.** ``avatar_pack`` is a string; the mesh lives in
  the renderer's asset registry. The simulation never learns what a being
  looks like.
"""

from __future__ import annotations

from typing import Any

from ..sim.types import Gesture, Walk, World

WIRE_VERSION = 1


def view(world: World) -> dict[str, Any]:
    """Everything a renderer needs to draw one frame of this world."""
    return {
        "v": WIRE_VERSION,
        "tick": world.tick,
        "dt": world.dt,
        "entities": [_entity(e) for e in _stable(world.entities)],
        "landmarks": [_landmark(m) for m in _stable(world.landmarks)],
    }


def scene(world: World) -> dict[str, Any]:
    """The parts that rarely change, sent once on connect.

    Landmarks and dt do not move; re-sending them twenty times a second is
    waste. Kept as a separate call so the per-tick payload stays small.

    ``world`` is the id of the world pack to draw, not the scene itself — the
    same arrangement as ``pack`` on an entity. The renderer fetches the manifest
    from ``/api/worlds`` and builds from it, so the numbers that describe the
    place to beings are the numbers that draw it.
    """
    return {
        "v": WIRE_VERSION,
        "dt": world.dt,
        "world": world.world_pack,
        "landmarks": [_landmark(m) for m in _stable(world.landmarks)],
    }


def frame(world: World) -> dict[str, Any]:
    """The per-tick payload: only what moves."""
    return {
        "tick": world.tick,
        "entities": [_entity(e) for e in _stable(world.entities)],
    }


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------


def _stable(mapping: dict[str, Any]) -> list[Any]:
    """Iterate in sorted-key order.

    Same reasoning as collision resolution: dict order reflects insertion
    history, which differs between a live run and one restored from a
    snapshot. A renderer diffing frames should never see a spurious reorder.
    """
    return [mapping[k] for k in sorted(mapping)]


def _entity(e: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": e.id,
        "pos": [e.pos.x, e.pos.y, e.pos.z],
        "facing": [e.facing.x, e.facing.y, e.facing.z],
        "radius": e.radius,
        "pack": e.avatar_pack,
        "action": e.action.kind,
        "emotion": e.emotion,
        "emotionWeight": round(e.emotion_weight, 4),
    }

    # Only present when they carry information, so idle beings stay cheap.
    if isinstance(e.action, Walk):
        out["target"] = [e.action.target.x, e.action.target.y, e.action.target.z]
    elif isinstance(e.action, Gesture):
        out["motion"] = e.action.motion
        # Normalised so the renderer needs no knowledge of durations.
        phase = (
            min(1.0, e.action.elapsed / e.action.duration)
            if e.action.duration
            else 1.0
        )
        out["motionPhase"] = round(phase, 4)

    if e.gaze is not None:
        out["gaze"] = e.gaze

    if e.speech is not None:
        out["speech"] = {
            "text": e.speech.text,
            "startTick": e.speech.start_tick,
            "durationTicks": e.speech.duration_ticks,
        }

    return out


def _landmark(m: Any) -> dict[str, Any]:
    return {
        "id": m.id,
        "pos": [m.pos.x, m.pos.y, m.pos.z],
        "description": m.description,
    }
