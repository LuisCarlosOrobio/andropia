/**
 * Composing rotations.
 *
 * The bug this exists for: adding Euler angles is not the same as composing
 * rotations. It holds for the small deltas one layer contributes, and breaks
 * once a gesture, a walk swing and the rest pose stack on one shoulder — the
 * sum lands somewhere the sequence never goes, which reads as a limb
 * snapping and then recovering.
 */

import { describe, expect, it } from 'vitest'
import {
  blendLayers,
  composeLayers,
  eulerToQuat,
  quatMul,
  quatNormalize,
} from './pose.js'
import { idleLayer, gestureLayer, walkLayer } from './layers.js'

/** Rotate a vector by a quaternion — how we check where a limb ends up. */
function rotate([x, y, z, w], [vx, vy, vz]) {
  const tx = 2 * (y * vz - z * vy)
  const ty = 2 * (z * vx - x * vz)
  const tz = 2 * (x * vy - y * vx)
  return [
    vx + w * tx + (y * tz - z * ty),
    vy + w * ty + (z * tx - x * tz),
    vz + w * tz + (x * ty - y * tx),
  ]
}

const near = (a, b, digits = 6) =>
  a.forEach((v, i) => expect(v).toBeCloseTo(b[i], digits))

describe('quaternion basics', () => {
  it('turns a zero rotation into identity', () => {
    near(eulerToQuat([0, 0, 0]), [0, 0, 0, 1])
  })

  it('stays unit length', () => {
    for (const e of [[0.3, -1.2, 0.8], [Math.PI, 0, -Math.PI / 3], [-2, 2, 2]]) {
      const [x, y, z, w] = eulerToQuat(e)
      expect(Math.hypot(x, y, z, w)).toBeCloseTo(1, 9)
    }
  })

  it('rotates a vector the way the angle says', () => {
    // +90° about Z takes +X to +Y.
    near(rotate(eulerToQuat([0, 0, Math.PI / 2]), [1, 0, 0]), [0, 1, 0], 6)
  })

  it('composes in order — b first, then a', () => {
    const a = eulerToQuat([0, Math.PI / 2, 0])
    const b = eulerToQuat([0, 0, Math.PI / 2])
    // Applying b then a to +X: b takes it to +Y, a leaves +Y alone.
    near(rotate(quatMul(a, b), [1, 0, 0]), [0, 1, 0], 6)
  })

  it('normalises a degenerate quaternion to identity', () => {
    expect(quatNormalize([0, 0, 0, 0])).toEqual([0, 0, 0, 1])
  })
})

describe('composeLayers', () => {
  it('matches addition when only one layer touches a bone', () => {
    // With a single contribution there is nothing to compose, so the two
    // approaches must agree — which is why the bug hid for so long.
    const layers = [{ pose: { head: [0.2, -0.1, 0.35] } }]
    near(composeLayers(layers).head, eulerToQuat(blendLayers(layers).head), 9)
  })

  it('diverges from addition once layers stack', () => {
    // The actual bug. Three layers on one shoulder is the real case.
    const layers = [
      { pose: { rightUpperArm: [0.06, 0, 1.32] } }, // rest
      { pose: { rightUpperArm: [0.38, 0, -0.05] } }, // walk swing
      { pose: { rightUpperArm: [0, 0, -1.2] } }, // wave
    ]

    const composed = composeLayers(layers).rightUpperArm
    const summed = eulerToQuat(blendLayers(layers).rightUpperArm)

    const apart = Math.hypot(
      ...rotate(composed, [0, -1, 0]).map((v, i) => v - rotate(summed, [0, -1, 0])[i])
    )
    expect(apart).toBeGreaterThan(0.01)
  })

  it('produces unit quaternions for every bone', () => {
    const layers = [
      { pose: idleLayer(2.2) },
      { pose: walkLayer(2.2, { distance: 3.1 }) },
      { pose: gestureLayer('wave', 0.5) },
    ]

    for (const [bone, q] of Object.entries(composeLayers(layers))) {
      expect(Math.hypot(...q), bone).toBeCloseTo(1, 9)
    }
  })

  it('never sends a limb somewhere the sequence does not go', () => {
    // Sweep a whole gesture while walking and check the arm direction stays
    // in a plausible cone. Summed Euler angles fail this; composition does
    // not. This is the regression for "arms sometimes kind of break".
    for (let phase = 0; phase <= 1; phase += 0.02) {
      for (let d = 0; d < 4; d += 0.25) {
        const q = composeLayers([
          { pose: idleLayer(d) },
          { pose: walkLayer(d, { distance: d }) },
          { pose: gestureLayer('wave', phase) },
        ]).rightUpperArm

        const dir = rotate(q, [-1, 0, 0]) // right arm points −X at rest
        expect(Math.hypot(...dir)).toBeCloseTo(1, 6)
        // Never folded up through the torso.
        expect(dir[1]).toBeLessThan(0.98)
      }
    }
  })

  it('skips empty and zero-weight layers', () => {
    const out = composeLayers([
      { pose: null },
      { pose: { head: [1, 0, 0] }, weight: 0 },
      { pose: { head: [0.2, 0, 0] } },
    ])
    near(out.head, eulerToQuat([0.2, 0, 0]), 9)
  })

  it('scales a layer by its weight', () => {
    const full = composeLayers([{ pose: { head: [0.4, 0, 0] } }]).head
    const half = composeLayers([{ pose: { head: [0.8, 0, 0] }, weight: 0.5 }]).head
    near(half, full, 9)
  })
})
