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
    spine: [
      REST.spine?.[0] ?? 0 + breath * 0.018 * intensity,
      sway * 0.02 * intensity,
      drift * 0.012 * intensity,
    ],
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
 * A walk, for bodies with no walk clip.
 *
 * Deliberately restrained: procedural locomotion is the one thing that
 * genuinely looks wrong if you push it, because people are exquisitely
 * sensitive to how walking looks. This does not attempt a stride — it adds
 * the counter-rotation and bob that read as *moving with purpose*, and lets
 * the body glide. Understated and plausible beats ambitious and uncanny.
 *
 * A pack that supplies a walk clip should use it; this is the fallback.
 */
export function walkLayer(t, { phase = 0 } = {}) {
  const cycle = t * 4.6 + phase // ~2.3 strides/second
  const step = Math.sin(cycle)
  const bob = Math.abs(Math.cos(cycle))

  return {
    hips: [0.02, step * 0.09, 0],
    spine: [0.03, step * -0.05, 0],
    chest: [0.02, step * -0.03, 0],
    // Arms counter-swing against the hips, which is most of what makes a
    // walk read as a walk rather than a slide.
    leftUpperArm: [step * 0.34, 0, REST.leftUpperArm[2] + 0.06],
    rightUpperArm: [step * -0.34, 0, REST.rightUpperArm[2] - 0.06],
    leftLowerArm: [Math.max(0, step) * 0.2, REST.leftLowerArm[1], REST.leftLowerArm[2]],
    rightLowerArm: [Math.max(0, -step) * 0.2, REST.rightLowerArm[1], REST.rightLowerArm[2]],
    head: [bob * -0.015, 0, 0],
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
