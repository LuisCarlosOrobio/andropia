"""Steering, arrival and collision separation."""

from __future__ import annotations

from andropia.sim import Entity, Vec3, vec
from andropia.sim.movement import (
    ARRIVAL_RADIUS,
    advance,
    has_arrived,
    resolve_overlaps,
    steer,
)
from andropia.sim.types import Walk


def test_steer_reduces_distance():
    e = Entity(id="a", pos=Vec3(0.0, 0.0, 0.0), facing=Vec3(1.0, 0.0, 0.0))
    target = Vec3(10.0, 0.0, 0.0)

    moved = steer(e, target, 0.05)
    assert vec.distance(moved.pos, target) < vec.distance(e.pos, target)


def test_steer_at_target_does_not_move():
    e = Entity(id="a", pos=Vec3(1.0, 0.0, 1.0))
    moved = steer(e, Vec3(1.0, 0.0, 1.0), 0.05)

    assert moved.pos == e.pos
    assert moved.vel == vec.ZERO


def test_being_turns_toward_its_target():
    """A being facing away should end up facing roughly the right way."""
    e = Entity(id="a", pos=Vec3(0.0, 0.0, 0.0), facing=Vec3(0.0, 0.0, -1.0))
    target = Vec3(10.0, 0.0, 0.0)

    for _ in range(40):
        e = steer(e, target, 0.05)

    desired = vec.normalize(vec.sub(target, e.pos))
    assert vec.dot(e.facing, desired) > 0.95


def test_facing_stays_unit_length():
    e = Entity(id="a", facing=Vec3(0.0, 0.0, 1.0))
    for _ in range(200):
        e = steer(e, Vec3(-7.0, 0.0, 3.0), 0.05)
        assert abs(vec.length(e.facing) - 1.0) < 1e-9


def test_exactly_opposed_facing_resolves():
    """Turning 180 degrees blends through a zero vector; the code must not
    produce a NaN or an undefined heading."""
    e = Entity(id="a", pos=Vec3(0.0, 0.0, 0.0), facing=Vec3(0.0, 0.0, 1.0), turn_rate=2.0)
    e = steer(e, Vec3(0.0, 0.0, -10.0), 0.05)

    assert abs(vec.length(e.facing) - 1.0) < 1e-9
    assert e.facing.x == e.facing.x  # not NaN


def test_vertical_component_is_ignored():
    """Beings walk on a plane; a target above ground does not lift them."""
    e = Entity(id="a", pos=Vec3(0.0, 0.0, 0.0))
    moved = steer(e, Vec3(5.0, 9.0, 0.0), 0.05)

    assert moved.pos.y == 0.0


def test_has_arrived_uses_the_arrival_radius():
    e = Entity(id="a", pos=Vec3(0.0, 0.0, 0.0))

    assert has_arrived(e, Vec3(ARRIVAL_RADIUS * 0.5, 0.0, 0.0))
    assert not has_arrived(e, Vec3(ARRIVAL_RADIUS * 2.0, 0.0, 0.0))


def test_advance_is_a_noop_for_idle_beings():
    e = Entity(id="a", pos=Vec3(2.0, 0.0, 2.0))
    assert advance(e, 0.05) == e


def test_advance_walks_when_the_action_is_walk():
    e = Entity(id="a", pos=Vec3(0.0, 0.0, 0.0), action=Walk(target=Vec3(8.0, 0.0, 0.0)))
    moved = advance(e, 0.05)

    assert moved.pos != e.pos


def test_overlapping_beings_are_pushed_apart():
    a = Entity(id="a", pos=Vec3(0.0, 0.0, 0.0), radius=0.5)
    b = Entity(id="b", pos=Vec3(0.4, 0.0, 0.0), radius=0.5)

    out = resolve_overlaps({"a": a, "b": b})
    separation = vec.distance(out["a"].pos, out["b"].pos)

    assert separation > vec.distance(a.pos, b.pos)
    assert separation >= 1.0 - 1e-9


def test_non_overlapping_beings_are_left_alone():
    a = Entity(id="a", pos=Vec3(0.0, 0.0, 0.0), radius=0.3)
    b = Entity(id="b", pos=Vec3(5.0, 0.0, 0.0), radius=0.3)

    out = resolve_overlaps({"a": a, "b": b})

    assert out["a"].pos == a.pos
    assert out["b"].pos == b.pos


def test_coincident_beings_separate_deterministically():
    """Two beings at exactly the same point have no separation direction.
    The resolution must be fixed, not dependent on floating-point noise."""
    a = Entity(id="a", pos=Vec3(1.0, 0.0, 1.0), radius=0.4)
    b = Entity(id="b", pos=Vec3(1.0, 0.0, 1.0), radius=0.4)

    first = resolve_overlaps({"a": a, "b": b})
    second = resolve_overlaps({"a": a, "b": b})

    assert first["a"].pos == second["a"].pos
    assert first["b"].pos == second["b"].pos
    assert first["a"].pos != first["b"].pos


def test_separation_is_independent_of_dict_order():
    """Insertion order differs between a live run and one restored from a
    snapshot; the outcome must not."""
    a = Entity(id="a", pos=Vec3(0.0, 0.0, 0.0), radius=0.5)
    b = Entity(id="b", pos=Vec3(0.3, 0.0, 0.1), radius=0.5)
    c = Entity(id="c", pos=Vec3(0.1, 0.0, 0.4), radius=0.5)

    forward = resolve_overlaps({"a": a, "b": b, "c": c})
    shuffled = resolve_overlaps({"c": c, "a": a, "b": b})

    for k in ("a", "b", "c"):
        assert forward[k].pos == shuffled[k].pos
