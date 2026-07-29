"""Serialising a world to JSON and back.

This is only possible because ``World`` is plain data. If a socket, a mesh
handle or a model client ever leaks into it, this module is the first thing
that breaks — which makes it a useful canary as well as a feature.

Round-tripping is exact: ``load(dump(w)) == w``. Floats go through
``repr``-equivalent JSON encoding, which for IEEE doubles is lossless, so a
world restored from disk continues to a bit-identical future.
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from typing import Any

from .types import (
    DoGesture,
    Emote,
    Entity,
    Gesture,
    Goto,
    Idle,
    Intent,
    Landmark,
    Look,
    Memory,
    MoveTo,
    Speak,
    Speech,
    Stop,
    Utterance,
    Vec3,
    Walk,
    World,
)

SCHEMA_VERSION = 1

_ACTIONS = {"idle": Idle, "walk": Walk, "gesture": Gesture}
_INTENTS = {
    "speak": Speak,
    "goto": Goto,
    "moveto": MoveTo,
    "gesture": DoGesture,
    "emote": Emote,
    "look": Look,
    "stop": Stop,
}


def dump(world: World) -> str:
    """Serialise a world. Keys are sorted so output is byte-stable."""
    return json.dumps(to_dict(world), sort_keys=True, separators=(",", ":"))


def load(text: str) -> World:
    return from_dict(json.loads(text))


def to_dict(world: World) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "tick": world.tick,
        "rng": world.rng,
        "dt": world.dt,
        "entities": {eid: _enc(e) for eid, e in sorted(world.entities.items())},
        "landmarks": {lid: _enc(m) for lid, m in sorted(world.landmarks.items())},
        "transcript": [_enc(u) for u in world.transcript],
    }


def from_dict(d: dict[str, Any]) -> World:
    version = d.get("schema")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"snapshot schema {version!r} is not supported "
            f"(this build reads schema {SCHEMA_VERSION})"
        )

    return World(
        tick=d["tick"],
        rng=d["rng"],
        dt=d["dt"],
        entities={eid: _dec_entity(e) for eid, e in d["entities"].items()},
        landmarks={lid: _dec_landmark(m) for lid, m in d["landmarks"].items()},
        transcript=tuple(_dec_utterance(u) for u in d["transcript"]),
    )


# --------------------------------------------------------------------------
# intents — recorded alongside snapshots so a run can be replayed exactly
# --------------------------------------------------------------------------


def dump_intents(batches: list[tuple[Intent, ...]]) -> str:
    """Serialise a per-tick intent log.

    A seed, an initial world and this log fully determine a run. Everything
    nondeterministic — model sampling, network timing — has already been
    collapsed into the record of what was actually proposed.
    """
    return json.dumps(
        [[_enc(i) for i in batch] for batch in batches],
        sort_keys=True,
        separators=(",", ":"),
    )


def load_intents(text: str) -> list[tuple[Intent, ...]]:
    return [tuple(_dec_intent(i) for i in batch) for batch in json.loads(text)]


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------


def _enc(obj: Any) -> Any:
    if isinstance(obj, Vec3):
        return [obj.x, obj.y, obj.z]
    if is_dataclass(obj):
        return {f.name: _enc(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, tuple):
        return [_enc(v) for v in obj]
    return obj


def _vec(v: Any) -> Vec3:
    return Vec3(v[0], v[1], v[2])


def _dec_entity(d: dict[str, Any]) -> Entity:
    return Entity(
        id=d["id"],
        pos=_vec(d["pos"]),
        facing=_vec(d["facing"]),
        vel=_vec(d["vel"]),
        action=_dec_action(d["action"]),
        emotion=d["emotion"],
        emotion_weight=d["emotion_weight"],
        gaze=d["gaze"],
        speech=_dec_speech(d["speech"]),
        memory=tuple(
            Memory(tick=m["tick"], text=m["text"], salience=m["salience"])
            for m in d["memory"]
        ),
        avatar_pack=d["avatar_pack"],
        rng=d["rng"],
        speed=d["speed"],
        turn_rate=d["turn_rate"],
        radius=d["radius"],
    )


def _dec_action(d: dict[str, Any]):
    cls = _ACTIONS[d["kind"]]
    if cls is Walk:
        return Walk(target=_vec(d["target"]))
    if cls is Gesture:
        return Gesture(motion=d["motion"], elapsed=d["elapsed"], duration=d["duration"])
    return Idle()


def _dec_speech(d: dict[str, Any] | None) -> Speech | None:
    if d is None:
        return None
    return Speech(
        text=d["text"],
        start_tick=d["start_tick"],
        duration_ticks=d["duration_ticks"],
        word_timings=tuple((w[0], w[1]) for w in d["word_timings"]),
    )


def _dec_landmark(d: dict[str, Any]) -> Landmark:
    return Landmark(id=d["id"], pos=_vec(d["pos"]), description=d["description"])


def _dec_utterance(d: dict[str, Any]) -> Utterance:
    return Utterance(tick=d["tick"], speaker=d["speaker"], text=d["text"])


def _dec_intent(d: dict[str, Any]) -> Intent:
    cls = _INTENTS[d["kind"]]
    payload = {k: v for k, v in d.items() if k != "kind"}
    # Vectors round-trip as [x, y, z]; restore the type so a replayed
    # MoveTo behaves identically to the one that was originally proposed.
    if "pos" in payload:
        payload["pos"] = _vec(payload["pos"])
    return cls(**payload)
