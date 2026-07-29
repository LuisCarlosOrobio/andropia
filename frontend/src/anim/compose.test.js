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
import { idleLayer, gestureLayer, walkGait, walkLayer } from './layers.js'

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

/**
 * Where the left hand ends up, given composed upper- and lower-arm rotations.
 *
 * Two bones of forward kinematics. Joint angles are a poor way to reason
 * about whether an arm looks right — a rotation about the wrong axis is a
 * perfectly large number that moves nothing. The hand is where it shows.
 */
function handPosition(upper, lower) {
  const BONE = [1, 0, 0] // the left arm extends +X in normalised rest
  const UPPER = 0.26
  const LOWER = 0.24

  const elbow = rotate(upper, BONE).map((v) => v * UPPER)
  const forearm = rotate(quatMul(upper, lower), BONE).map((v) => v * LOWER)
  return elbow.map((v, i) => v + forearm[i])
}

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

  it('applies later layers in the parent frame', () => {
    // Pinning the order, because both directions look equally plausible in
    // the source and only one of them swings an arm.
    const rest = { leftUpperArm: [0, 0, Math.PI / 2] }
    const swing = { leftUpperArm: [Math.PI / 2, 0, 0] }

    const composed = composeLayers([{ pose: rest }, { pose: swing }]).leftUpperArm
    const expected = quatNormalize(
      quatMul(eulerToQuat(swing.leftUpperArm), eulerToQuat(rest.leftUpperArm))
    )
    near(composed, expected, 9)
  })

  it('swings the arm forward and back rather than in its socket', () => {
    // The order bug, measured where it shows. REST rolls the upper arm down
    // out of the T-pose by 1.32 rad about Z, and the walk's swing is a pitch
    // about X meaning "about the shoulder". Composed the wrong way round the
    // roll drags the pitch axis with it — X becomes nearly −Y — and the swing
    // turns into the arm rotating inside its own socket. Forward travel at
    // the hand: 0.037 wrong, 0.71 right.
    const gait = walkGait()
    let lowest = Infinity
    let highest = -Infinity

    for (let d = 0; d < gait.stride; d += gait.stride / 60) {
      const q = composeLayers([
        { pose: idleLayer(0) },
        { pose: walkLayer(0, { distance: d }) },
      ]).leftUpperArm
      // The left upper arm bone points +X at rest, so its Z component is how
      // far forward the arm reaches.
      const forward = rotate(q, [1, 0, 0])[2]
      lowest = Math.min(lowest, forward)
      highest = Math.max(highest, forward)
    }

    expect(highest - lowest).toBeGreaterThan(0.4)
  })

  it('raises the arm for gestures that mean raised', () => {
    // A delta that merely cancels REST's 1.32 roll puts the arm back at
    // T-pose — straight out sideways. Both wave and cheer shipped that way:
    // the shapes were right and the magnitudes were not, which is the
    // characteristic failure of authoring angles by reasoning about a rig
    // instead of looking at it.
    for (const gesture of ['wave', 'cheer']) {
      const q = composeLayers([
        { pose: idleLayer(0) },
        { pose: gestureLayer(gesture, 0.5) },
      ]).rightUpperArm

      expect(rotate(q, [-1, 0, 0])[1], gesture).toBeGreaterThan(0.3)
    }
  })

  it('bends the elbow rather than rolling the forearm', () => {
    // Same class of bug as the shoulder, one joint further down and easy to
    // miss because a wrist roll does move the mesh — just not the hand. The
    // walk drove the elbow about X, which for a down-hanging arm runs along
    // the forearm. Measured where it shows: at the hand.
    // Isolated from the shoulder, which dominates hand travel and hid this
    // when measured naively: compare the hand against where it would be with
    // the elbow contributing nothing. A wrist roll leaves that difference at
    // essentially zero while still being a large angle.
    const gait = walkGait()
    let mostMoved = 0

    for (let d = 0; d < gait.stride; d += gait.stride / 40) {
      const walk = walkLayer(0, { distance: d })
      const idle = idleLayer(0)

      const withElbow = composeLayers([{ pose: idle }, { pose: walk }])
      const withoutElbow = composeLayers([
        { pose: idle },
        { pose: { ...walk, leftLowerArm: [0, 0, 0] } },
      ])

      const a = handPosition(withElbow.leftUpperArm, withElbow.leftLowerArm)
      const b = handPosition(withoutElbow.leftUpperArm, withoutElbow.leftLowerArm)
      mostMoved = Math.max(mostMoved, Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]))
    }

    // The X-axis version manages 0.017 at peak; a real bend clears 0.05.
    expect(mostMoved).toBeGreaterThan(0.05)
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
