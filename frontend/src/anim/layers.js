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

import { GESTURES } from './gestures.js'
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
 * Metres of ground covered per full walk cycle — two steps, so roughly a
 * 0.75 m stride. Driving the cycle by DISTANCE rather than by time is what
 * keeps the feet planted: a being moving slowly takes slow steps and a
 * being hurrying takes quick ones, both landing at the same points on the
 * ground, with no rate constant to keep in sync with anything.
 */
export const STRIDE_LENGTH = 1.5

/**
 * Fallback rate, in radians per second, used only when no distance is
 * supplied. Present so the layer stays callable from a tuner or a test
 * that has no notion of a being moving through a world.
 */
export const WALK_RATE = 5.2

/**
 * A walk, for bodies with no walk clip.
 *
 * A pack that supplies a walk clip should use it; this is the fallback, and
 * for VRM it is the only option, because essentially every VRM ships with
 * zero animations.
 *
 * The first version deliberately left the legs alone, reasoning that
 * procedural locomotion without IK looks wrong. That was the wrong call: a
 * being gliding across the ground reads as *broken*, while an imperfect
 * walk reads as stylised. Doing something beats doing nothing.
 *
 * Still not IK — no solver pins a foot to a spot and holds it there. But
 * the cycle advances with distance travelled rather than with the clock,
 * which removes the cause of most visible skating: the feet now complete a
 * stride per STRIDE_LENGTH of ground regardless of how fast the being is
 * moving. What remains is the residual from the foot arc not exactly
 * matching the ground plane, which is a much smaller error and needs real
 * IK to remove entirely.
 */
export function walkLayer(t, { phase = 0, distance = null } = {}) {
  // Distance-driven when we know how far the being has walked, which is the
  // real fix for skating; time-driven otherwise.
  const cycle =
    distance === null
      ? t * WALK_RATE + phase
      : (distance / STRIDE_LENGTH) * 2 * Math.PI + phase
  const step = Math.sin(cycle)
  const opposite = Math.sin(cycle + Math.PI)
  // Twice the stride frequency: the body rises on each foot, not each cycle.
  const bob = Math.cos(cycle * 2)

  return {
    // Legs. A being that glides reads as broken, whereas an imperfect walk
    // reads as stylised — so this errs toward doing something rather than
    // nothing. It is not IK: there is no foot planting, so at very high
    // speeds the feet will skate. Matching stride rate to ground speed
    // would fix most of that and is the obvious next refinement.
    //
    // Legs point −Y at rest, so a negative X rotation swings forward.
    leftUpperLeg: [-step * 0.52, 0, 0],
    rightUpperLeg: [-opposite * 0.52, 0, 0],
    // Knees only bend one way. Clamping at zero is what keeps the joint
    // from inverting, which is the single most obviously-wrong thing a
    // procedural leg can do.
    leftLowerLeg: [Math.max(0, Math.sin(cycle - 0.9)) * 0.95, 0, 0],
    rightLowerLeg: [Math.max(0, Math.sin(cycle - 0.9 + Math.PI)) * 0.95, 0, 0],
    // Ankles roughly counter the thigh so the feet stay near level.
    leftFoot: [step * 0.26, 0, 0],
    rightFoot: [opposite * 0.26, 0, 0],

    // Torso. Small counter-rotation against the hips, and a lean into the
    // direction of travel.
    hips: [0.03, step * 0.1, bob * 0.02],
    spine: [0.04, step * -0.06, 0],
    chest: [0.02, step * -0.04, 0],

    // Arms counter-swing against the legs — the left arm goes back as the
    // left leg comes forward. Getting this backwards produces a gait that is
    // subtly and unmistakably wrong in a way that is hard to name.
    //
    // These are **deltas**. The idle layer already places the arms at rest,
    // and layers add, so repeating the rest rotation here applied it twice
    // and swung the arms far past the body.
    leftUpperArm: [step * 0.38, 0, 0.05],
    rightUpperArm: [opposite * 0.38, 0, -0.05],
    leftLowerArm: [Math.max(0, step) * 0.24, 0, 0],
    rightLowerArm: [Math.max(0, opposite) * 0.24, 0, 0],

    head: [bob * -0.018, 0, 0],
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

  if (proceduralWalk) {
    layers.push({ pose: walkLayer(t, options), weight: 1 })
  }

  if (state.gesture?.procedural) {
    const pose = gestureLayer(state.gesture.name, state.gesture.phase)
    if (pose) layers.push({ pose, weight: 1 })
  }

  return layers
}
