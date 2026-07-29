"""Three-component vectors.

A ``NamedTuple`` rather than a dataclass: it is immutable by construction,
unpacks, compares and serialises for free, and costs a tuple rather than an
object. Every operation returns a new value; nothing here mutates.

Only IEEE-754 basic arithmetic and ``math.sqrt`` are used. Both are
correctly rounded and therefore reproduce exactly across runs, which is what
lets the simulation replay bit-for-bit. Transcendental functions (``sin``,
``cos``, ``atan2``) are deliberately absent — libm implementations differ
between platforms and would break cross-machine determinism.
"""

from __future__ import annotations

import math
from typing import NamedTuple


class Vec3(NamedTuple):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


ZERO = Vec3(0.0, 0.0, 0.0)


def add(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.x + b.x, a.y + b.y, a.z + b.z)


def sub(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.x - b.x, a.y - b.y, a.z - b.z)


def scale(v: Vec3, k: float) -> Vec3:
    return Vec3(v.x * k, v.y * k, v.z * k)


def dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def length_sq(v: Vec3) -> float:
    """Squared length. Prefer this for comparisons — it avoids a sqrt."""
    return v.x * v.x + v.y * v.y + v.z * v.z


def length(v: Vec3) -> float:
    return math.sqrt(length_sq(v))


def distance(a: Vec3, b: Vec3) -> float:
    return length(sub(a, b))


def distance_sq(a: Vec3, b: Vec3) -> float:
    return length_sq(sub(a, b))


def normalize(v: Vec3) -> Vec3:
    """Unit vector, or ZERO if the input has no direction.

    Returning ZERO rather than raising keeps callers total: a being asked to
    walk to the spot it already occupies has no heading, and that is an
    ordinary state rather than an error.
    """
    n = length(v)
    if n == 0.0:
        return ZERO
    return Vec3(v.x / n, v.y / n, v.z / n)


def clamp_length(v: Vec3, max_len: float) -> Vec3:
    """Shorten ``v`` to ``max_len`` if it is longer, leave it otherwise."""
    n_sq = length_sq(v)
    if n_sq <= max_len * max_len:
        return v
    return scale(normalize(v), max_len)


def lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    """Linear interpolation. ``t`` is not clamped; callers may extrapolate."""
    return Vec3(
        a.x + (b.x - a.x) * t,
        a.y + (b.y - a.y) * t,
        a.z + (b.z - a.z) * t,
    )


def flatten_y(v: Vec3) -> Vec3:
    """Drop the vertical component. Beings walk on a plane."""
    return Vec3(v.x, 0.0, v.z)
