/**
 * The layer stack. Every function here is pure.
 *
 *     idle      always on          spine, chest, hips
 *     locomotion while walking     whole body sway
 *     gesture   transient          arms and head, overrides idle
 *     blink     always on          an expression, not a bone
 *     viseme    while speaking     mouth expressions
 *
 * Layers take time and entity state and return plain data. They are blended
 * into one pose and applied to three.js exactly once, which means the entire
 * animation system can be tested without a browser.
 *
 * Time is passed in, never read. `t` is seconds since the being appeared,
 * derived from the simulation tick — so two runs of the same recording
 * animate identically, and a replay looks like the original.
 */

import { footTargets, gaitFor, pelvisDrop } from './gait.js'
import { GESTURES } from './gestures.js'
import { solveLeg } from './ik.js'
import { REST, arc, clamp01, easeInOut, lerpPose, scalePose } from './pose.js'

// -- idle ------------------------------------------------------------------

/**
 * Breathing and micro-sway, on top of REST.
 *
 * The layer that does the most work for the least code. A body holding
 * perfectly still reads as frozen — as a bug, not a character — and a slow
 * sine on the spine is most of the difference between "3D model" and
 * "someone standing there".
 *
 * Phase is offset per being so a crowd does not breathe in unison, which is
 * uncanny in a way that is hard to name but immediately obvious.
 */
export function idleLayer(t, { phase = 0, intensity = 1 } = {}) {
  const breath = Math.sin(t * 1.15 + phase) // ~11 breaths/minute
  const sway = Math.sin(t * 0.37 + phase * 1.7)
  const drift = Math.sin(t * 0.23 + phase * 0.6)

  return {
    ...REST,
    spine: [breath * 0.018 * intensity, sway * 0.02 * intensity, drift * 0.012 * intensity],
    chest: [breath * 0.026 * intensity, 0, 0],
    hips: [0, sway * 0.014 * intensity, drift * 0.01 * intensity],
    neck: [breath * -0.008 * intensity, drift * 0.03 * intensity, 0],
    head: [breath * -0.006 * intensity, drift * 0.045 * intensity, sway * 0.02 * intensity],
    // Arms hang from the shoulders, so they inherit a little of the sway.
    leftUpperArm: [
      REST.leftUpperArm[0],
      REST.leftUpperArm[1],
      REST.leftUpperArm[2] + breath * 0.014 * intensity,
    ],
    rightUpperArm: [
      REST.rightUpperArm[0],
      REST.rightUpperArm[1],
      REST.rightUpperArm[2] - breath * 0.014 * intensity,
    ],
  }
}

// -- locomotion ------------------------------------------------------------

/**
 * Fallback rate, in radians per second, used only when no distance is
 * supplied. Present so the layer stays callable from a tuner or a test that
 * has no notion of a being moving through a world.
 */
export const WALK_RATE = 5.2

/**
 * Leg proportions to solve against when nobody has measured the real rig.
 *
 * Roughly a 1.6 m humanoid. A body should measure its own bones and pass
 * them in — these exist so the layer is callable from a test or a tuner, not
 * because guessing is good enough.
 */
export const DEFAULT_RIG = { upperLeg: 0.42, lowerLeg: 0.42 }

/**
 * Standing hip height as a fraction of full leg length.
 *
 * Never 1: a locked knee reads as a mannequin and leaves the solver no room
 * to absorb error. But not much below it either — this fraction *is* the
 * stance knee bend, held for the whole time the foot is down, and at 0.97 the
 * knee sits at a permanent 28° and the character creeps along in a crouch.
 * 0.99 puts it near 16°, which is inside the range a person's stance knee
 * actually holds.
 *
 * It also stays above the solver's own extension clamp, so that clamp remains
 * a safety net for impossible targets rather than the thing setting the pose.
 */
const STAND = 0.99

/**
 * A walk, for bodies with no walk clip.
 *
 * A pack that supplies a walk clip should use it; this is the fallback, and
 * for VRM it is the only option, because essentially every VRM ships with
 * zero animations.
 *
 * The legs are inverse kinematics: `gait.js` decides where the feet belong
 * and `ik.js` works out the joint angles that put them there. Everything else
 * — torso, arms, head — is still forward kinematics driven by the cycle, and
 * should be, since no constraint governs where an elbow "should" be.
 *
 * Two earlier versions are worth remembering, because each fixed a real
 * problem and neither was enough. The first drove the joints from sines,
 * which glides whenever ground speed disagrees with the animation rate. The
 * second drove the cycle from distance travelled, which fixed the gross
 * skating but still left the feet tracing an arc that only approximates the
 * ground. Only pinning the foot as an input removes the last of it.
 */
export function walkLayer(t, { phase = 0, distance = null, rig = DEFAULT_RIG } = {}) {
  const { gait, legLength } = solveSpace(rig)

  // Distance-driven when we know how far the being has walked, which is what
  // plants the feet; time-driven otherwise, so the layer stays callable.
  const travelled =
    distance === null ? (t * WALK_RATE * gait.stride) / (2 * Math.PI) : distance

  const feet = footTargets(travelled, phase, gait)
  const legs = legPose(feet, rig, legLength)

  // Torso and arms still run off the cycle. Expressed as an angle so the
  // sines below read the same way they did before the legs changed.
  const cycle = feet.cycle * 2 * Math.PI
  const step = Math.sin(cycle)
  const opposite = Math.sin(cycle + Math.PI)
  // Twice the stride frequency: the body rises on each foot, not each cycle.
  const bob = Math.cos(cycle * 2)

  return {
    ...legs,

    // Torso. Small counter-rotation against the hips, and a lean into the
    // direction of travel. The vertical bob that used to live on the hips is
    // gone — the pelvis now moves because the legs cannot reach any higher,
    // which is both the real cause and always in phase.
    hips: [0.03, step * 0.1, 0],
    spine: [0.04, step * -0.06, 0],
    chest: [0.02, step * -0.04, 0],

    // Arms counter-swing against the legs — the left arm goes back as the
    // left leg comes forward. Getting this backwards produces a gait that is
    // subtly and unmistakably wrong in a way that is hard to name.
    //
    // These are **deltas**. The idle layer already places the arms at rest,
    // and layers compose, so repeating the rest rotation here applied it
    // twice and swung the arms far past the body.
    leftUpperArm: [step * 0.3, 0, 0.05],
    rightUpperArm: [opposite * 0.3, 0, -0.05],
    // Elbow flexion is about **Y**, not X. The arm hangs down, so X in the
    // forearm's frame runs along the arm and a rotation about it is a wrist
    // roll: measured at the hand, the X version moved it 0.017 while the same
    // angle on Y moved it 0.069 forward and up. REST already bends the elbow
    // on Y; this disagreed with it and spun the forearm instead of bending
    // it. Signs mirror, since the two arms bend toward each other.
    leftLowerArm: [0, -Math.max(0, step) * 0.24, 0],
    rightLowerArm: [0, Math.max(0, opposite) * 0.24, 0],

    head: [bob * -0.018, 0, 0],
  }
}

/**
 * How far the pelvis sits below its standing height at this moment, in metres
 * and negative downward.
 *
 * Separate from the pose because it is a translation, not a rotation. Folding
 * it into a Pose would mean every consumer of a Pose had to know about one
 * bone whose three numbers meant something different from all the others.
 *
 * Two things lower the pelvis, and both belong here rather than in the gait:
 * the small permanent crouch of never locking a knee, and the stride-driven
 * drop of a leg reaching out.
 */
export function walkHipOffset(distance, phase = 0, rig = DEFAULT_RIG) {
  const { gait, legLength } = solveSpace(rig)
  const crouch = rig.upperLeg + rig.lowerLeg - legLength
  return -(crouch + pelvisDrop(footTargets(distance, phase, gait), legLength))
}

/**
 * The gait a given rig walks with. Exposed because stride is no longer a
 * constant anyone can assume — it is proportioned to the legs, so a caller
 * that needs to know how far a cycle covers has to ask.
 */
export function walkGait(rig = DEFAULT_RIG) {
  return solveSpace(rig).gait
}

/**
 * The two numbers every function here needs: the standing leg length to solve
 * against, and the gait proportioned to it.
 *
 * Derived in one place so the stride the feet follow and the leg that has to
 * reach them can never be computed from different assumptions — which would
 * show up as a permanent limp nobody could locate.
 */
function solveSpace(rig) {
  const legLength = (rig.upperLeg + rig.lowerLeg) * STAND
  return { gait: gaitFor(legLength), legLength }
}

/**
 * Solve both legs for a set of foot targets.
 *
 * Targets arrive in the body's frame with the origin on the ground; the
 * solver wants them relative to the hip joint, so the only work here is
 * moving the origin up to the pelvis and handing each leg to `solveLeg`.
 */
function legPose(feet, rig, legLength) {
  const { upperLeg, lowerLeg } = rig
  const hipY = legLength - pelvisDrop(feet, legLength)

  const left = solveLeg([0, feet.left.pos[1] - hipY, feet.left.pos[2]], upperLeg, lowerLeg)
  const right = solveLeg([0, feet.right.pos[1] - hipY, feet.right.pos[2]], upperLeg, lowerLeg)

  return {
    leftUpperLeg: [left.hip, 0, 0],
    rightUpperLeg: [right.hip, 0, 0],
    leftLowerLeg: [left.knee, 0, 0],
    rightLowerLeg: [right.knee, 0, 0],
    // Ankle cancels the thigh and shin so the sole stays level with the
    // ground. Bone rotations compound down the chain, so keeping a foot flat
    // means undoing everything above it.
    leftFoot: [-(left.hip + left.knee), 0, 0],
    rightFoot: [-(right.hip + right.knee), 0, 0],
  }
}

// -- gestures --------------------------------------------------------------

/**
 * Sample a gesture's keyframes at a normalised phase.
 *
 * `phase` comes from the simulation, so a gesture stays in step with the
 * world even if the browser drops frames — and changing a duration on the
 * server cannot desynchronise the display.
 *
 * Returns null for an unknown gesture rather than throwing. A model may emit
 * a tag from a stale prompt or a finetune with its own ideas, and that
 * should degrade rather than break.
 */
export function gestureLayer(name, phase) {
  const gesture = GESTURES[name]
  if (!gesture) return null

  const t = clamp01(phase)
  const pose = sampleKeys(gesture.keys, t)

  // Fade in and out at the edges so a gesture never snaps on or off, and
  // blends with whatever the idle layer is doing underneath.
  const fade = Math.min(1, arc(t) * 2.2)
  return scalePose(pose, fade)
}

/** Interpolate a keyframe list at `t`, with easing between frames. */
export function sampleKeys(keys, t) {
  if (keys.length === 0) return {}
  if (t <= keys[0].t) return keys[0].bones
  if (t >= keys[keys.length - 1].t) return keys[keys.length - 1].bones

  for (let i = 0; i < keys.length - 1; i++) {
    const a = keys[i]
    const b = keys[i + 1]
    if (t >= a.t && t <= b.t) {
      const span = b.t - a.t
      const local = span === 0 ? 0 : (t - a.t) / span
      return lerpPose(a.bones, b.bones, easeInOut(local))
    }
  }

  return keys[keys.length - 1].bones
}

// -- blink -----------------------------------------------------------------

/**
 * Eyelid weight from a deterministic schedule.
 *
 * Blinking is the cheapest signal of aliveness there is, and its absence is
 * the single most unsettling thing about a still avatar.
 *
 * The schedule is a function of time and a per-being seed rather than a
 * timer or a random draw, which keeps it reproducible: a replay blinks on
 * exactly the ticks the original did.
 */
export function blinkWeight(t, { phase = 0, interval = 4.2, duration = 0.13 } = {}) {
  // Vary the gap so blinks are not metronomic, without consulting an RNG.
  const jitter = Math.sin(phase * 12.9898) * 1.4
  const period = interval + jitter
  const local = ((t + phase * 7) % period) / duration

  if (local > 1) return 0
  // Fast close, slower open — how a real blink is shaped.
  return local < 0.4 ? local / 0.4 : 1 - (local - 0.4) / 0.6
}

// -- visemes ---------------------------------------------------------------

/**
 * Mouth shapes while speaking.
 *
 * A placeholder in the honest sense: it drives the `aa` viseme from a
 * plausible envelope so a speaking being's mouth moves, rather than a
 * character talking with a closed mouth. Real lip-sync arrives with the TTS
 * word timings, which is why the wire format already carries them.
 */
export function visemeWeights(t, speaking, { phase = 0 } = {}) {
  if (!speaking) return {}

  // Two detuned sines make an envelope that avoids an obvious rhythm.
  const a = Math.sin(t * 11.3 + phase)
  const b = Math.sin(t * 7.1 + phase * 2.3)
  const openness = clamp01(0.35 + a * 0.3 + b * 0.2)

  return { aa: openness * 0.8, ih: clamp01(0.2 - openness * 0.2) }
}

// -- composition -----------------------------------------------------------

/**
 * Everything above, assembled.
 *
 * Returns the layer stack rather than a finished pose, so the caller decides
 * how to blend — and so a test can assert on which layers are active
 * without reasoning about the arithmetic.
 */
export function layersFor(state, t, options = {}) {
  const layers = []

  const walking = state.locomotion?.state === 'walk'
  const proceduralWalk = walking && state.locomotion?.procedural

  layers.push({ pose: idleLayer(t, options), weight: 1 })

  // `walkWeight` lets the caller fade the walk in and out rather than
  // switching it. That matters more since the legs became IK: the pelvis now
  // rides several centimetres lower while walking, and switching that on in
  // one frame is a visible hop. Defaults to a hard switch so a test or a
  // tuner need not thread a blend it does not care about.
  const weight = proceduralWalk ? (options.walkWeight ?? 1) : 0
  if (weight > 0.001) {
    layers.push({ pose: walkLayer(t, options), weight })
  }

  if (state.gesture?.procedural) {
    const pose = gestureLayer(state.gesture.name, state.gesture.phase)
    if (pose) layers.push({ pose, weight: 1 })
  }

  return layers
}
