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
 * A ratio rather than a constant, because what the pelvis has to do depends on
 * the stride relative to the leg: a stride that flatters a tall avatar makes a
 * short one waddle at a crouch.
 *
 * This was 1.15, chosen to keep the pelvis drop shallow, and that was the
 * wrong thing to optimise. At a walking speed of 1.6 m/s it put the cadence at
 * 1.67 cycles a second — 3.3 steps — and short quick steps under a body
 * gliding forward do not read as walking, they read as the feet shuffling
 * while something else moves the character. 1.8 puts the cadence near 1.07
 * cycles/s, which is what a person actually does, and the rocker below is what
 * pays for the longer stride.
 */
export const STRIDE_RATIO = 1.8

/** Peak foot lift during swing, as a fraction of leg length. */
export const LIFT_RATIO = 0.13

/** Lateral offset of each foot from the centre line, per leg length. */
export const TRACK_RATIO = 0.11

/**
 * How high the ankle rides over the heel or toe at the ends of stance, as a
 * fraction of leg length.
 *
 * This is the heel-to-toe roll, and it is what makes a long stride possible.
 * A flat-footed model is a pair of compasses: the hip can never be further
 * from the planted foot than the leg is long, so a longer stride forces the
 * pelvis to sink, and past a few centimetres that reads as creeping along in a
 * crouch. A real foot instead pivots over the heel as it lands and over the
 * toe as it leaves, which lifts the ankle at exactly the moments the leg is
 * most stretched and buys back most of the drop.
 *
 * 0.05 of leg length corresponds to a foot around 0.24 m pitching 20°, which
 * is the right order for a 1.6 m character.
 */
export const ROCKER_RATIO = 0.05

/** Sole pitch at the ends of stance, in radians. Heel strike and toe-off. */
export const ROCKER_PITCH = 0.35

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
    rocker: legLength * ROCKER_RATIO,
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
    const along = half - u * excursion

    // Where in the roll this foot is: +1 heel-strike at the front, 0 flat
    // underneath, −1 toe-off at the back. The ankle rides up over whichever
    // end is still touching the ground, and the sole pitches to keep that end
    // down — the toe lifts as the heel lands, the heel lifts as the toe
    // leaves. Squared, so the foot is flat through the middle of stance
    // rather than perpetually tilting.
    const roll = along / half
    return {
      pos: [x, gait.rocker * roll * roll, along],
      planted: true,
      pitch: -roll * ROCKER_PITCH,
    }
  }

  // Swinging: back to the front, lifting clear of the ground on the way. A
  // sine arc rather than a straight line, because a foot dragged flat along
  // the ground reads as a limp.
  //
  // The arc starts and ends at rocker height, not at zero. Stance leaves the
  // ankle up on the toe and takes it back up on the heel, so an arc from the
  // floor would jump the ankle 4 cm at both seams — which moved the pelvis,
  // which flicked the knee 14° in a single frame. Both ends have to agree with
  // stance or the leg snaps twice per cycle.
  const u = (cycle - STANCE) / (1 - STANCE)
  return {
    pos: [x, gait.rocker + Math.sin(Math.PI * u) * gait.lift, -half + u * excursion],
    planted: false,
    // Rolls from toe-off through level to toe-up, ready for heel strike.
    pitch: ROCKER_PITCH * (1 - 2 * u),
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
  // Each foot imposes a ceiling on the hip: it can sit no higher than that
  // foot plus however much leg reaches diagonally across to it. The lowest
  // ceiling wins.
  //
  // **Both** feet, regardless of `planted`. The constraint is reachability,
  // not weight-bearing — a leg has to reach its foot whether or not that foot
  // is carrying the body. Gating on `planted` looked more physical and was a
  // bug: a foot a hair before its plant is in the same place as a hair after
  // it, so the flag flipping made a continuous geometric constraint switch on
  // instantly, dropping the pelvis 2.4 cm and flicking the knee 14° in one
  // frame, twice per cycle. Dropping the gate makes it continuous by
  // construction rather than by tuning, and a swinging foot never binds
  // anyway: it is either lifted or nearly underneath the body.
  //
  // The ankle's own height counts, and that is precisely how the rocker earns
  // a longer stride: at the ends of stance, where the leg is most stretched
  // and the hip would otherwise have to sink, the foot has rolled up onto its
  // heel or toe and handed the hip a few centimetres back.
  const ceilings = [targets.left, targets.right].map((foot) => {
    const horizontal = Math.min(Math.abs(foot.pos[2]), legLength)
    const diagonal = Math.sqrt(legLength * legLength - horizontal * horizontal)
    return foot.pos[1] + diagonal
  })

  // Never lift the hip above standing height; the legs would have to stretch.
  return Math.max(0, legLength - softMin(ceilings[0], ceilings[1], legLength * BLEND))
}

/** Width of the hand-off between the two legs, as a fraction of leg length. */
const BLEND = 0.04

/**
 * A minimum with the corner rounded off.
 *
 * A hard `Math.min` is not differentiable where its arguments cross, and that
 * crossing is the moment the body hands its weight from one leg to the other —
 * so the pelvis changed direction instantly and the knee that had just become
 * the binding one snapped straight at about 900°/s. Real legs share the load
 * through the hand-off instead of switching at an instant.
 *
 * Safe in the only direction that matters: the result never exceeds either
 * input, so the hip only ever sits *lower* than strictly required. A lower hip
 * is always reachable — the knee simply bends a little more — whereas a higher
 * one is not reachable at all, which is what would put the sliding back.
 */
function softMin(a, b, k) {
  if (k <= 0) return Math.min(a, b)
  const h = Math.max(0, Math.min(1, 0.5 + (0.5 * (b - a)) / k))
  return b * (1 - h) + a * h - k * h * (1 - h)
}

function wrap(v) {
  return v - Math.floor(v)
}
