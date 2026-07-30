"""Projecting a world pack into simulation data. Pure.

A pack declares features; the simulation carries landmarks. This is the one
place that converts between them, so a feature's material and extent reach
perception without the simulation ever importing this package — the same
arrangement as ``Entity.avatar_pack``, where the world holds an id and the
renderer does the loading.
"""

from __future__ import annotations

from ..sim.types import Landmark, Vec3
from .schema import WorldPack


def landmarks(pack: WorldPack) -> dict[str, Landmark]:
    """The pack's features as landmarks, keyed by id.

    Sorted, because a dict built in file order would differ between a live run
    and one restored from a snapshot — and perception iterates landmarks to
    build a prompt, so the order is the difference between a cache hit and a
    cache miss.
    """
    return {
        feature.id: Landmark(
            id=feature.id,
            pos=Vec3(*feature.pos),
            description=feature.description,
            material=feature.material,
            enterable=feature.enterable,
            radius=feature.radius,
        )
        for feature in sorted(pack.features, key=lambda f: f.id)
    }
