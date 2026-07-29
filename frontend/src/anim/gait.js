/**
 * The gait model. Pure.
 *
 * Decides where each foot should be, in the body's own frame, as a function
 * of how far the being has walked. The IK solver then works out the joint
 * angles; this module never touches a bone.
 *
 * The trick that removes foot sliding is to think in the body's frame rather
 * than the world's. A planted foot is motionless in the world, so relative to
 * a body moving forward at speed v it travels *backward* at exactly v. That
 * is not an approximation to tune — it is a constraint, and it pins down the
 * stance excursion completely: a foot planted for `STANCE` of a cycle must
 * travel back by `STANCE * stride`, because that is how far the body moves
 * while it is down. Getting that number from anywhere else puts the slide
 * back.
 *
 * Which is why every quantity here is a function of `distance`, in metres,
 * and the clock appears nowhere.
 *
 *     Foot = { pos: [x, y, z], planted: boolean }
 */

/**
 * Stride length as a multiple of leg length — how far the body travels per
 * full cycle of two steps.
 *
 * A ratio rather than a constant because the pelvis has to drop far enough
 * for the stance leg to reach, and how far that is depends entirely on the
 * stride relative to the leg. A stride that flatters a tall avatar makes a
 * short one waddle at a crouch. Around 1.15 keeps the drop near 5% of leg
 * length, which is roughly what a person walking unhurriedly does.
 */
export const STRIDE_RATIO = 1.15

/** Peak foot lift during swing, as a fraction of leg length. */
export const LIFT_RATIO = 0.13

/** Lateral offset of each foot from the centre line, per leg length. */
export const TRACK_RATIO = 0.11

/**
 * Fraction of the cycle a foot spends on the ground. Above 0.5, so there is
 * a moment with both feet down — a walk. Below it there would be a moment
 * with neither, which is a run.
 */
export const STANCE = 0.55

/** Proportions for a leg of unit length, so callers can supply metres. */
export function gaitFor(legLength) {
  return {
    stride: legLength * STRIDE_RATIO,
    lift: legLength * LIFT_RATIO,
    track: legLength * TRACK_RATIO,
  }
}

/** Fallback proportions, for a caller with no rig to hand. */
export const DEFAULT_GAIT = gaitFor(0.84)

/**
 * Foot targets for one moment in the cycle, in the body's local frame:
 * +Z forward, +Y up, origin on the ground between the hips.
 *
 * @param distance metres travelled since the being started walking
 * @param phase    per-being offset in radians, so a crowd does not march in
 *                 lockstep
 * @param gait     proportions from `gaitFor`
 */
export function footTargets(distance, phase = 0, gait = DEFAULT_GAIT) {
  // Cycle position in [0, 1). The two feet are half a cycle apart, which is
  // the entire definition of a walk as opposed to a hop.
  const cycle = wrap(distance / gait.stride + phase / (2 * Math.PI))

  return {
    left: footAt(cycle, -gait.track, gait),
    right: footAt(wrap(cycle + 0.5), gait.track, gait),
    cycle,
  }
}

/**
 * One foot's position, given where it is in its own cycle.
 *
 * Stance runs from 0 to STANCE, swing from there to 1. The two halves share
 * the same endpoints rather than being tuned independently, because if they
 * disagree the foot teleports at the seam.
 */
function footAt(cycle, x, gait) {
  // Ground covered while this foot is down, and therefore exactly how far it
  // travels backward through the body's frame. The whole no-slip property is
  // this one line.
  const excursion = STANCE * gait.stride
  const half = excursion / 2

  if (cycle < STANCE) {
    // Planted: sliding backward at precisely the rate the body advances,
    // which is what "planted" means from in here.
    const u = cycle / STANCE
    return { pos: [x, 0, half - u * excursion], planted: true }
  }

  // Swinging: back to the front, lifting clear of the ground on the way. A
  // sine arc rather than a straight line, because a foot dragged flat along
  // the ground reads as a limp.
  const u = (cycle - STANCE) / (1 - STANCE)
  return {
    pos: [x, Math.sin(Math.PI * u) * gait.lift, -half + u * excursion],
    planted: false,
  }
}

/**
 * How far the pelvis drops below its standing height.
 *
 * A walking body is shorter than a standing one: with a leg reaching out, the
 * hip cannot sit as high as it does with that leg straight underneath.
 * Deriving the drop from the stance foot means the bob is always exactly in
 * phase with the stride, where a sine on the hips is only ever approximately
 * in phase and drifts visibly at the extremes.
 *
 * A minimum, not a preference. The hip may sit lower than this — the knee
 * simply bends more — but any higher and the leg cannot reach its foot, the
 * solver clamps, and the sliding comes straight back.
 */
export function pelvisDrop(targets, legLength) {
  // Whichever foot bears weight sets the ceiling. During double support both
  // are down, and the one reaching furthest wins: it is the one that cannot
  // reach any higher.
  const reach = Math.max(
    targets.left.planted ? Math.abs(targets.left.pos[2]) : 0,
    targets.right.planted ? Math.abs(targets.right.pos[2]) : 0
  )
  const clamped = Math.min(reach, legLength)
  return legLength - Math.sqrt(legLength * legLength - clamped * clamped)
}

function wrap(v) {
  return v - Math.floor(v)
}
