/**
 * The pure half of rendering a body.
 *
 *     bodyState :: (Entity, Entity, Pack, alpha) -> BodyState
 *
 * Takes two frames and an interpolation factor, returns plain data
 * describing what the body should look like. No three.js, no mutation, no
 * DOM — so it is testable in isolation and cannot be the reason a frame
 * looks wrong for reasons that only reproduce in a browser.
 *
 * Everything downstream of this is one imperative function (`Body.apply`)
 * that pushes these numbers into three.js objects. That split is the same
 * one the simulation uses: compute functionally, apply once.
 */

/** Canonical emotions. Mirrors `andropia.vocab.EMOTIONS`. */
export const EMOTIONS = [
  'neutral',
  'happy',
  'angry',
  'sad',
  'relaxed',
  'surprised',
]

/**
 * Compute the visual state of one being.
 *
 * @param was      the previous frame's entity (or the current one)
 * @param now      the current frame's entity
 * @param pack     its avatar pack, or null while the model is still loading
 * @param alpha    0 at `was`, 1 at `now`
 */
export function bodyState(was, now, pack, alpha) {
  return {
    position: lerp3(was.pos, now.pos, alpha),
    yaw: facingToYaw(lerp3(was.facing, now.facing, alpha)),
    expressions: expressionWeights(now, pack),
    locomotion: locomotionFor(now, pack),
    gesture: gestureFor(now, pack),
    speech: now.speech?.text ?? null,
    selected: false,
  }
}

/**
 * Canonical emotion -> weight, resolved through the pack's mapping.
 *
 * A pack that cannot show an emotion simply yields no weight for it. That is
 * the graceful half of the contract: the model is never *told* it can look
 * happy on a rig with no happy morph, but if a tag arrives anyway — from a
 * stale prompt, or a finetune with its own ideas — nothing breaks.
 */
export function expressionWeights(entity, pack) {
  const out = {}
  if (!pack) return out

  const canonical = entity.emotion
  const weight = entity.emotionWeight ?? 0

  if (canonical === 'neutral' || weight <= 0) return out

  const rigName = pack.expressions?.[canonical]
  if (!rigName) return out // unsupported by this body; silently neutral

  out[rigName] = clamp01(weight)
  return out
}

/**
 * Which looping clip should be playing, and how strongly.
 *
 * Returns a crossfade weight rather than a hard switch so a being eases
 * between standing and striding instead of popping between them.
 */
export function locomotionFor(entity, pack) {
  const walking = entity.action === 'walk'
  const clips = pack?.locomotion ?? {}

  return {
    state: walking ? 'walk' : 'idle',
    clip: walking ? (clips.walk ?? null) : (clips.idle ?? null),
    // Procedural when the pack supplies no clip for this state.
    procedural: walking ? !clips.walk : !clips.idle,
  }
}

/**
 * The one-shot gesture in progress, if any.
 *
 * `phase` is already normalised by the server, so the renderer never needs
 * to know how long a gesture lasts — which means changing a duration on the
 * simulation side cannot desynchronise the display.
 */
export function gestureFor(entity, pack) {
  if (entity.action !== 'gesture') return null

  const name = entity.motion
  const clip = pack?.clips?.[name] ?? null

  return {
    name,
    phase: entity.motionPhase ?? 0,
    clip,
    // No clip: B3's procedural pose library will drive this. Until then it
    // is a visible placeholder rather than a silent nothing, because a
    // gesture that does nothing is indistinguishable from a bug.
    procedural: clip === null,
  }
}

// --------------------------------------------------------------------------

export function lerp(a, b, t) {
  return a + (b - a) * t
}

export function lerp3(a, b, t) {
  return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]
}

export function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v
}

/**
 * A facing vector to a Y rotation.
 *
 * Returns null for a degenerate vector so callers can hold the previous
 * orientation rather than snapping to zero — a being interpolating through
 * an exactly-opposed turn briefly has no defined heading.
 */
export function facingToYaw([x, , z]) {
  if (x === 0 && z === 0) return null
  return Math.atan2(x, z)
}
