/**
 * Two-bone inverse kinematics. Pure, no dependencies.
 *
 * The rest of the animation system is forward kinematics: rotations drive
 * where a limb ends up. This inverts that — you say where the foot should
 * be, and it works out the hip and knee angles that put it there.
 *
 * That inversion is the whole point for walking. With FK, a foot's ground
 * position is whatever falls out of the joint angles, so it slides whenever
 * the body's speed disagrees with the animation. With IK the planted foot is
 * an *input*: it stays exactly where it was put while the body travels over
 * it, and slip is zero by construction rather than by tuning.
 *
 * Everything here works in the hip's local frame, with the leg hanging along
 * −Y at rest, +Z forward. Rotations are about X only: a leg swinging forward
 * and back and a knee folding are both single-axis, and pretending otherwise
 * would add gimbal problems to solve nothing.
 */

/** Never fully straighten a joint — a locked knee snaps and reads as broken. */
const MAX_EXTENSION = 0.995

/**
 * Solve for the joint angles that place a foot at `target`.
 *
 * @param target [x, y, z] in the hip's local frame; x is ignored, since a
 *               leg swinging sideways is not what a walk needs and solving
 *               for it would make the result ambiguous.
 * @param upper  thigh length
 * @param lower  shin length
 * @returns {{ hip: number, knee: number }} X rotations in radians
 */
export function solveLeg(target, upper, lower) {
  const dy = target[1]
  const dz = target[2]

  const reach = upper + lower
  const raw = Math.hypot(dy, dz)

  // Unreachable targets are clamped rather than rejected. A gait can ask for
  // a stride longer than the leg during a transition, and the honest answer
  // is "as far as it goes" — throwing would turn a cosmetic overreach into a
  // crash.
  const distance = Math.min(raw, reach * MAX_EXTENSION)
  const safe = Math.max(distance, Math.abs(upper - lower) + 1e-5)

  // Interior angle at the knee, by the law of cosines.
  const kneeCos = clamp(
    (upper * upper + lower * lower - safe * safe) / (2 * upper * lower),
    -1,
    1
  )
  const interior = Math.acos(kneeCos)
  // A straight leg has an interior angle of π, so the bend is the remainder.
  const knee = Math.PI - interior

  // Angle between the thigh and the straight hip-to-target line.
  const thighCos = clamp(
    (upper * upper + safe * safe - lower * lower) / (2 * upper * safe),
    -1,
    1
  )
  const offset = Math.acos(thighCos)

  // Direction from hip to target. The leg rests along −Y, and a positive X
  // rotation swings it toward −Z, so this is the angle that aims it.
  const aim = raw === 0 ? 0 : Math.atan2(-dz, -dy)

  // Tilt the thigh off the aim line so the knee leads forward, which is the
  // way a human knee bends. The sign here is the difference between a leg
  // and a flamingo.
  return { hip: aim - offset, knee }
}

/**
 * Where the foot actually lands for a given pair of angles.
 *
 * The inverse of `solveLeg`, and the reason the solver can be trusted: a
 * test can solve for a target, run it forward, and check the foot arrives.
 * Without this, IK correctness is a matter of opinion.
 */
export function forwardLeg(hip, knee, upper, lower) {
  // Thigh, from the hip.
  const kneeY = -Math.cos(hip) * upper
  const kneeZ = -Math.sin(hip) * upper

  // Shin, whose rotation compounds with the thigh's.
  const total = hip + knee
  return [0, kneeY - Math.cos(total) * lower, kneeZ - Math.sin(total) * lower]
}

function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v
}
