"""Locomotion and collision.

Deliberately simple: beings steer toward a point on a horizontal plane and
push each other apart when they overlap. No navmesh — an open world does not
need one, and the moment obstacles appear this is the module that grows a
pathfinder behind the same interface.

Collision operates on **capsule radii, never on meshes**. The simulation
moves a proxy; the renderer draws whatever body the being happens to be
wearing at that transform. That separation is what lets bodies be swapped
without touching simulation.

No ``sin``/``cos``/``atan2`` anywhere. Turning is exponential smoothing of a
direction vector, which needs only arithmetic and one square root — both
correctly rounded, so a run reproduces exactly.
"""

from __future__ import annotations

from . import vec
from .types import Entity, Idle, Vec3, Walk

# How close counts as "arrived". Larger than it looks: beings have radius,
# and stopping dead on a point produces visible jitter.
ARRIVAL_RADIUS = 0.35


def steer(ent: Entity, target: Vec3, dt: float) -> Entity:
    """Advance a being one step toward ``target``.

    Returns the being unchanged in position if it has arrived; the caller
    decides whether arriving ends the action.
    """
    to_target = vec.flatten_y(vec.sub(target, ent.pos))

    if vec.length_sq(to_target) <= ARRIVAL_RADIUS * ARRIVAL_RADIUS:
        return _halt(ent)

    desired = vec.normalize(to_target)
    facing = _turn_toward(ent.facing, desired, ent.turn_rate, dt)

    # Move along the *current* facing rather than straight at the target, so
    # a being visibly turns into its path instead of sliding sideways.
    step_len = ent.speed * dt
    velocity = vec.scale(facing, ent.speed)
    pos = vec.add(ent.pos, vec.scale(facing, step_len))

    return _replace(ent, pos=pos, facing=facing, vel=velocity)


def has_arrived(ent: Entity, target: Vec3) -> bool:
    flat = vec.flatten_y(vec.sub(target, ent.pos))
    return vec.length_sq(flat) <= ARRIVAL_RADIUS * ARRIVAL_RADIUS


def advance(ent: Entity, dt: float) -> Entity:
    """Advance whatever the being is currently doing by one step."""
    action = ent.action

    if isinstance(action, Walk):
        moved = steer(ent, action.target, dt)
        if has_arrived(moved, action.target):
            return _replace(moved, action=Idle(), vel=vec.ZERO)
        return moved

    # Idle and Gesture do not move the body. Gesture timing is advanced by
    # `step`, which owns the clock; movement only owns the body.
    return ent


def resolve_overlaps(entities: dict[str, Entity]) -> dict[str, Entity]:
    """Push apart any beings whose capsules intersect.

    A single relaxation pass, not an iterative solver. Beings are slow and
    the timestep is small, so one pass is enough to keep them from occupying
    the same space, and it cannot oscillate the way repeated passes can.

    Iteration is over **sorted ids**, never dict order. Dict order reflects
    insertion history, which may differ between a live run and one restored
    from a snapshot; sorting makes the result depend only on the data.
    """
    ids = sorted(entities)
    out = dict(entities)

    for i, a_id in enumerate(ids):
        for b_id in ids[i + 1 :]:
            a, b = out[a_id], out[b_id]
            delta = vec.flatten_y(vec.sub(b.pos, a.pos))
            min_sep = a.radius + b.radius
            dist_sq = vec.length_sq(delta)

            if dist_sq >= min_sep * min_sep:
                continue

            if dist_sq == 0.0:
                # Exactly coincident: no meaningful direction. Separate along
                # a fixed axis so the outcome stays deterministic rather than
                # depending on floating-point noise.
                push = Vec3(min_sep * 0.5, 0.0, 0.0)
            else:
                overlap = min_sep - vec.length(delta)
                push = vec.scale(vec.normalize(delta), overlap * 0.5)

            out[a_id] = _replace(a, pos=vec.sub(a.pos, push))
            out[b_id] = _replace(b, pos=vec.add(b.pos, push))

    return out


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------


def _turn_toward(facing: Vec3, desired: Vec3, rate: float, dt: float) -> Vec3:
    """Rotate ``facing`` toward ``desired``.

    Exponential smoothing rather than constant angular velocity: the being
    turns fastest when most misaligned and eases in as it lines up, which
    reads as natural and avoids trigonometry entirely. ``rate`` is therefore
    a responsiveness constant, not radians per second.
    """
    t = rate * dt
    if t >= 1.0:
        return desired
    blended = vec.lerp(facing, desired, t)
    turned = vec.normalize(blended)
    # Exactly opposed vectors blend to zero and have no defined direction.
    # Snapping to the target is the only sensible resolution and is stable.
    return desired if turned == vec.ZERO else turned


def _halt(ent: Entity) -> Entity:
    return _replace(ent, vel=vec.ZERO) if ent.vel != vec.ZERO else ent


def _replace(ent: Entity, **changes) -> Entity:
    from dataclasses import replace

    return replace(ent, **changes)
