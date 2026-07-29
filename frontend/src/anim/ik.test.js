/**
 * Inverse kinematics and the gait that drives it.
 *
 * The important test in this file is the round trip: solve for a target, run
 * the result back through forward kinematics, and check the foot arrives.
 * Everything else about IK is opinion until that holds.
 */

import { describe, expect, it } from 'vitest'
import { forwardLeg, solveLeg } from './ik.js'
import { DEFAULT_GAIT, STANCE, STRIDE_RATIO, footTargets, gaitFor, pelvisDrop } from './gait.js'
import { DEFAULT_RIG, idleLayer, walkGait, walkHipOffset, walkLayer } from './layers.js'
import { IDENTITY_QUAT, composeLayers } from './pose.js'

/** Rotate a vector by a quaternion, to ask where a bone actually ended up. */
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

const UPPER = 0.42
const LOWER = 0.42
const REACH = UPPER + LOWER

describe('two-bone solve', () => {
  it('puts the foot where it was asked to', () => {
    // The whole contract. If this fails nothing else about the walk matters.
    const targets = [
      [0, -0.8, 0],
      [0, -0.75, 0.3],
      [0, -0.75, -0.3],
      [0, -0.6, 0.4],
      [0, -0.7, -0.35],
      [0, -0.5, 0.1],
      [0, -0.82, 0.05],
    ]

    for (const target of targets) {
      const { hip, knee } = solveLeg(target, UPPER, LOWER)
      const [, y, z] = forwardLeg(hip, knee, UPPER, LOWER)
      expect(y).toBeCloseTo(target[1], 6)
      expect(z).toBeCloseTo(target[2], 6)
    }
  })

  it('reaches as far as it can toward an impossible target', () => {
    // A gait can briefly ask for more than the leg has. Clamping keeps the
    // foot on the line to the target instead of throwing mid-frame.
    const { hip, knee } = solveLeg([0, -2, 0], UPPER, LOWER)
    const [, y] = forwardLeg(hip, knee, UPPER, LOWER)
    expect(y).toBeLessThan(-REACH * 0.99)
    expect(y).toBeGreaterThanOrEqual(-REACH)
  })

  it('never inverts or locks the knee', () => {
    // A knee bending backwards is the single most obviously-wrong thing a
    // procedural leg can do; a locked one snaps and reads as broken.
    for (let z = -0.5; z <= 0.5; z += 0.01) {
      for (let y = -0.84; y <= -0.4; y += 0.02) {
        const { knee } = solveLeg([0, y, z], UPPER, LOWER)
        expect(knee).toBeGreaterThan(0)
        expect(knee).toBeLessThan(Math.PI)
      }
    }
  })

  it('bends the knee forward, not backward', () => {
    // With the foot ahead of the hip the knee must lead forward (+Z). Get
    // this sign wrong and you have built a flamingo.
    const { hip, knee } = solveLeg([0, -0.7, 0.2], UPPER, LOWER)
    const kneeZ = -Math.sin(hip) * UPPER
    expect(kneeZ).toBeGreaterThan(0)
    expect(knee).toBeGreaterThan(0)
  })

  it('handles asymmetric limbs', () => {
    // Nothing guarantees an avatar's shin matches its thigh.
    const { hip, knee } = solveLeg([0, -0.6, 0.25], 0.5, 0.3)
    const [, y, z] = forwardLeg(hip, knee, 0.5, 0.3)
    expect(y).toBeCloseTo(-0.6, 6)
    expect(z).toBeCloseTo(0.25, 6)
  })

  it('survives a degenerate target at the hip', () => {
    // Distance zero would divide by zero in the law of cosines.
    const { hip, knee } = solveLeg([0, 0, 0], UPPER, LOWER)
    expect(Number.isFinite(hip)).toBe(true)
    expect(Number.isFinite(knee)).toBe(true)
  })
})

describe('the gait', () => {
  it('slides a planted foot backward at exactly walking speed', () => {
    // The no-slip condition, stated directly. A foot on the ground is fixed
    // in the world, so in the body's frame it must move backward by exactly
    // the distance the body moved forward — a ratio of −1, not −0.9.
    const gait = gaitFor(0.84)
    const step = 0.001

    for (let d = 0.05; d < gait.stride * STANCE - 0.05; d += 0.01) {
      const a = footTargets(d, 0, gait).left
      const b = footTargets(d + step, 0, gait).left
      if (!a.planted || !b.planted) continue
      expect((b.pos[2] - a.pos[2]) / step).toBeCloseTo(-1, 6)
    }
  })

  it('keeps a planted foot in contact with the ground', () => {
    // The ANKLE is no longer on the floor during stance — the contact point
    // is. The foot rolls over its heel as it lands and its toe as it leaves,
    // so the ankle rides up at both ends and is only down at mid-stance.
    // Asserting ankle-height-zero would forbid the roll.
    for (let d = 0; d < 5; d += 0.013) {
      const { left, right } = footTargets(d)
      for (const foot of [left, right]) {
        if (!foot.planted) continue
        expect(foot.pos[1]).toBeGreaterThanOrEqual(0)
        expect(foot.pos[1]).toBeLessThanOrEqual(DEFAULT_GAIT.rocker + 1e-9)
      }
    }
  })

  it('puts the sole flat at mid-stance', () => {
    // The roll has to pass through flat, or the foot is forever on an edge.
    const flat = footTargets(DEFAULT_GAIT.stride * (STANCE / 2), 0).left
    expect(flat.planted).toBe(true)
    expect(flat.pos[1]).toBeCloseTo(0, 9)
    expect(flat.pitch).toBeCloseTo(0, 9)
  })

  it('never leaves both feet in the air', () => {
    // Both down is double support, which is what makes it a walk. Neither
    // down is a run, and this gait does not have one.
    for (let d = 0; d < 5; d += 0.011) {
      const { left, right } = footTargets(d)
      expect(left.planted || right.planted).toBe(true)
    }
  })

  it('does not teleport a foot at the stance-swing seam', () => {
    // The two halves are written separately and have to agree at the join.
    const step = 1e-4
    for (let d = 0; d < 5; d += step) {
      const a = footTargets(d).left.pos
      const b = footTargets(d + step).left.pos
      expect(Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2])).toBeLessThan(0.01)
    }
  })

  it('lifts the swinging foot clear of the ground', () => {
    let peak = 0
    for (let d = 0; d < DEFAULT_GAIT.stride; d += 0.005) {
      const { left } = footTargets(d)
      if (!left.planted) peak = Math.max(peak, left.pos[1])
    }
    // Measured from the rocker height the swing starts and ends at, not from
    // the floor — the arc has to meet stance at both seams.
    expect(peak).toBeCloseTo(DEFAULT_GAIT.rocker + DEFAULT_GAIT.lift, 3)
  })

  it('hands the foot between stance and swing without a jump', () => {
    // Both seams. The swing used to arc from the floor while stance left the
    // ankle 4 cm up on the toe, so the foot teleported twice per cycle — which
    // moved the pelvis and flicked the knee 14 degrees in one frame.
    const step = 1e-5
    for (const seam of [STANCE, 1.0]) {
      const at = (c) => footTargets(c * DEFAULT_GAIT.stride, 0).left
      const before = at(seam - step)
      const after = at(seam + step)
      for (const axis of [0, 1, 2]) {
        expect(after.pos[axis], `axis ${axis} at seam ${seam}`).toBeCloseTo(
          before.pos[axis],
          4
        )
      }
      expect(after.pitch).toBeCloseTo(before.pitch, 4)
    }
  })

  it('separates the feet laterally', () => {
    // Feet on one line is a tightrope walk, not a gait.
    const { left, right } = footTargets(0.4)
    expect(left.pos[0]).toBeLessThan(0)
    expect(right.pos[0]).toBeGreaterThan(0)
  })

  it('scales the stride to the leg', () => {
    // A short avatar and a tall one must not take the same stride in metres,
    // or the short one walks at a permanent crouch.
    expect(gaitFor(0.5).stride).toBeLessThan(gaitFor(1.0).stride)
  })
})

describe('the pelvis', () => {
  it('drops only as far as the constraint demands', () => {
    // Too little and the leg cannot reach its foot, the solver clamps, and
    // the sliding this whole module exists to remove comes straight back.
    const legLength = 0.8
    for (let d = 0; d < 4; d += 0.01) {
      const feet = footTargets(d, 0, gaitFor(legLength))
      const hipY = legLength - pelvisDrop(feet, legLength)

      for (const foot of [feet.left, feet.right]) {
        if (!foot.planted) continue
        const need = Math.hypot(hipY - foot.pos[1], foot.pos[2])
        expect(need).toBeLessThanOrEqual(legLength + 1e-9)
      }
    }
  })

  it('keeps the planted foot on the ground through a whole cycle', () => {
    // The end-to-end claim: gait plus solver plus pelvis put the foot where
    // the gait asked, so it does not skate. Solved exactly as walkLayer does.
    const rig = DEFAULT_RIG
    // Derived from the gait rather than restated, so this cannot quietly go
    // on testing a standing height the layer stopped using.
    const gait = walkGait(rig)
    const legLength = gait.stride / STRIDE_RATIO

    for (let d = 0; d < gait.stride * 2; d += 0.01) {
      const feet = footTargets(d, 0, gait)
      const hipY = legLength - pelvisDrop(feet, legLength)

      for (const foot of [feet.left, feet.right]) {
        if (!foot.planted) continue
        const target = [0, foot.pos[1] - hipY, foot.pos[2]]
        const { hip, knee } = solveLeg(target, rig.upperLeg, rig.lowerLeg)
        const [, y, z] = forwardLeg(hip, knee, rig.upperLeg, rig.lowerLeg)
        // Under a millimetre, which is invisible on a 1.6 m character.
        expect(Math.hypot(y - target[1], z - target[2])).toBeLessThan(0.001)
      }
    }
  })

  it('does not let anything above the legs slide the planted foot', () => {
    // The regression for "it moves more to the sides".
    //
    // Every other test in this file checks the gait and the solver in their
    // own frame, which is why they all passed while the walk visibly crabbed.
    // The legs hang off `hips`, so a rotation there moves feet the solver has
    // already pinned — and `hips` carried a ±0.1 rad pelvis yaw, which is
    // anatomically correct and dragged each planted foot 2 cm sideways per
    // cycle. This measures the foot through the composed pose, where it shows.
    const gait = walkGait()
    let widest = 0

    for (let d = 0; d < gait.stride * 2; d += gait.stride / 400) {
      const pose = composeLayers([
        { pose: idleLayer(d * 0.7) },
        { pose: walkLayer(0, { distance: d }) },
      ])
      const feet = footTargets(d, 0, gait)

      for (const foot of [feet.left, feet.right]) {
        if (!foot.planted) continue
        // A planted foot's lateral offset is a constant, so any sideways
        // movement in world space came from a bone above it.
        const world = rotate(pose.hips ?? IDENTITY_QUAT, foot.pos)
        widest = Math.max(widest, Math.abs(world[0] - foot.pos[0]))
      }
    }

    // Under a millimetre. The pelvis yaw managed ten times this.
    expect(widest).toBeLessThan(0.001)
  })

  it('never rises above standing height', () => {
    for (let d = 0; d < 4; d += 0.007) {
      expect(walkHipOffset(d)).toBeLessThanOrEqual(0)
    }
  })

  it('stays a walk, not a squat', () => {
    // Some drop is the point; a lot of it is a character creeping along in a
    // crouch, which is what an over-long stride produces.
    const legLength = DEFAULT_RIG.upperLeg + DEFAULT_RIG.lowerLeg
    for (let d = 0; d < 4; d += 0.007) {
      expect(walkHipOffset(d)).toBeGreaterThan(-legLength * 0.12)
    }
  })
})

describe('the walk layer', () => {
  it('solves against the rig it is given', () => {
    // Proof the measured proportions are actually used, rather than the
    // defaults quietly winning.
    const short = walkLayer(0, { distance: 0.4, rig: { upperLeg: 0.2, lowerLeg: 0.2 } })
    const tall = walkLayer(0, { distance: 0.4, rig: { upperLeg: 0.6, lowerLeg: 0.6 } })
    expect(short.leftUpperLeg[0]).not.toBeCloseTo(tall.leftUpperLeg[0], 3)
  })

  it('gives the sole exactly the angle the gait asked for', () => {
    // Bone rotations compound down the chain, so the ankle has to undo the
    // thigh and shin before adding anything of its own. Previously that meant
    // holding the sole level; now the gait dictates a roll, and the check is
    // that the chain delivers it rather than whatever the knee left behind.
    const gait = walkGait()
    for (let d = 0; d < 3; d += 0.01) {
      const pose = walkLayer(0, { distance: d })
      const total = pose.leftUpperLeg[0] + pose.leftLowerLeg[0] + pose.leftFoot[0]
      expect(total).toBeCloseTo(footTargets(d, 0, gait).left.pitch, 9)
    }
  })

  it('holds a plausible stance knee', () => {
    // Caught a real regression the rest of the suite was blind to. The stance
    // knee angle IS the standing-height fraction, held for as long as the
    // foot is down, and at 0.97 it sat at a permanent 28° — every test still
    // passed while the character crept along in a visible crouch. A person's
    // stance knee lives somewhere around 5-20°.
    const gait = walkGait()

    for (let d = 0; d < gait.stride * 2; d += 0.01) {
      const pose = walkLayer(0, { distance: d })
      const feet = footTargets(d, 0, gait)

      for (const [side, foot] of [
        ['left', feet.left],
        ['right', feet.right],
      ]) {
        if (!foot.planted) continue
        const knee = pose[`${side}LowerLeg`][0]
        expect(knee).toBeGreaterThan(0.02) // never locked straight
        expect(knee).toBeLessThan(0.55) // ~31°, and not a squat
      }
    }
  })

  it('flexes the swinging knee enough to clear the ground', () => {
    // A swing leg that stays near-straight scuffs the floor, which is the
    // other half of looking like a walk.
    const gait = walkGait()
    let peak = 0

    for (let d = 0; d < gait.stride; d += 0.005) {
      if (footTargets(d, 0, gait).left.planted) continue
      peak = Math.max(peak, walkLayer(0, { distance: d }).leftLowerLeg[0])
    }
    expect(peak).toBeGreaterThan(0.7) // ~40°
  })

  it('produces finite angles everywhere in the cycle', () => {
    for (let d = 0; d < 6; d += 0.005) {
      for (const angle of Object.values(walkLayer(0, { distance: d }))) {
        for (const v of angle) expect(Number.isFinite(v)).toBe(true)
      }
    }
  })
})
