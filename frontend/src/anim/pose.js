/**
 * Poses, and how to combine them. Pure throughout.
 *
 * A Pose is plain data: bone name -> [x, y, z] Euler rotation in radians,
 * expressed in **VRM normalised humanoid space**. That space is the whole
 * reason procedural animation works across avatars — every conformant VRM
 * exposes the same bone names in the same rest orientation, so a pose
 * authored once applies correctly to any body regardless of its proportions
 * or how the artist built the rig.
 *
 * Euler rather than quaternions, deliberately. These poses are hand-authored
 * and hand-tuned; a human reading `rightUpperArm: [0, 0, 1.35]` can tell
 * what it does, and a quaternion literal is unreadable. The rotations are
 * small and never gimbal-locked in practice, and conversion happens once at
 * the mutation boundary.
 *
 *     Pose = { [bone: string]: [number, number, number] }
 */

/**
 * The rest orientation of a VRM humanoid is a **T-pose** — arms straight out
 * along ±X. Which means an avatar with no animation applied does not stand
 * neutrally; it stands like a scarecrow.
 *
 * So this is not a decorative base layer. It is what makes a body look like
 * a person rather than a bug, and everything else composes on top of it.
 */
export const REST = {
  // Arms down and slightly forward of the coronal plane. Left points +X and
  // right points −X, so bringing both down needs opposite signs.
  leftUpperArm: [0.06, 0, -1.32],
  rightUpperArm: [0.06, 0, 1.32],
  // A little elbow bend; perfectly straight arms read as stiff.
  leftLowerArm: [0, -0.18, -0.1],
  rightLowerArm: [0, 0.18, 0.1],
  leftHand: [0, 0, -0.05],
  rightHand: [0, 0, 0.05],
  // Shoulders drop very slightly out of the T.
  leftShoulder: [0, 0, -0.06],
  rightShoulder: [0, 0, 0.06],
}

export const EMPTY = Object.freeze({})

/**
 * Add rotations bone by bone.
 *
 * Additive rather than replacing, so a breathing layer can nudge the spine
 * while a gesture drives the arms and neither has to know about the other.
 */
export function addPose(base, delta, weight = 1) {
  if (weight === 0) return base
  const out = { ...base }

  for (const bone in delta) {
    const d = delta[bone]
    const b = out[bone]
    out[bone] = b
      ? [b[0] + d[0] * weight, b[1] + d[1] * weight, b[2] + d[2] * weight]
      : [d[0] * weight, d[1] * weight, d[2] * weight]
  }

  return out
}

/** Interpolate between two poses, bone-wise. Bones absent from one side are treated as zero. */
export function lerpPose(a, b, t) {
  const out = {}
  for (const bone of new Set([...Object.keys(a), ...Object.keys(b)])) {
    const x = a[bone] ?? [0, 0, 0]
    const y = b[bone] ?? [0, 0, 0]
    out[bone] = [
      x[0] + (y[0] - x[0]) * t,
      x[1] + (y[1] - x[1]) * t,
      x[2] + (y[2] - x[2]) * t,
    ]
  }
  return out
}

/** Scale a pose toward identity. Used to fade a gesture in and out. */
export function scalePose(pose, weight) {
  if (weight === 1) return pose
  const out = {}
  for (const bone in pose) {
    const p = pose[bone]
    out[bone] = [p[0] * weight, p[1] * weight, p[2] * weight]
  }
  return out
}

/**
 * Blend a stack of weighted layers into one pose.
 *
 * Layers are additive and applied in order, so later ones sit on top. The
 * whole frame is computed as data here and applied to three.js exactly once,
 * which is the same discipline the simulation uses.
 */
export function blendLayers(layers) {
  let pose = EMPTY
  for (const { pose: p, weight = 1 } of layers) {
    if (!p || weight === 0) continue
    pose = addPose(pose, p, weight)
  }
  return pose
}

// -- easing ----------------------------------------------------------------
//
// Linear interpolation between poses reads as robotic. These are what make
// procedural motion look deliberate rather than mechanical, and they cost
// nothing.

/** Smooth start and stop. The default for almost everything. */
export function easeInOut(t) {
  return t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2
}

/** Fast out, slow in — good for a limb arriving at a position. */
export function easeOut(t) {
  return 1 - (1 - t) ** 3
}

/**
 * Overshoot slightly and settle.
 *
 * The single most valuable easing for gestures: real limbs do not stop dead
 * at their destination, and a small overshoot is most of the difference
 * between "animated" and "moved".
 */
export function easeBack(t, overshoot = 1.7) {
  const c = overshoot + 1
  return 1 + c * (t - 1) ** 3 + overshoot * (t - 1) ** 2
}

/** Rises to 1 at the midpoint and returns to 0. For one-shot gestures. */
export function arc(t) {
  return Math.sin(Math.PI * clamp01(t))
}

export function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v
}
