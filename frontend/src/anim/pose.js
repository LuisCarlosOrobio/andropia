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

// -- composing rotations ---------------------------------------------------
//
// Adding Euler angles is not the same as composing rotations. For the small
// deltas a single layer contributes the approximation is fine, but when a
// gesture, a walk swing and the rest pose all stack on one shoulder the sum
// passes through orientations that are not the rotation you would get by
// applying them in sequence — which is visible as a limb snapping and then
// recovering as the gesture fades.
//
// So layers are authored and blended as Euler triples, because those are
// readable and tunable, and composed as quaternions, because those are
// correct. Hand-rolled rather than imported, so this module stays free of
// three.js and testable without a browser.
//
// Convention matches three.js Euler order 'YXZ'.

/** Euler [x, y, z] in radians -> quaternion [x, y, z, w]. */
export function eulerToQuat([x, y, z]) {
  const c1 = Math.cos(x / 2)
  const c2 = Math.cos(y / 2)
  const c3 = Math.cos(z / 2)
  const s1 = Math.sin(x / 2)
  const s2 = Math.sin(y / 2)
  const s3 = Math.sin(z / 2)

  return [
    s1 * c2 * c3 + c1 * s2 * s3,
    c1 * s2 * c3 - s1 * c2 * s3,
    c1 * c2 * s3 - s1 * s2 * c3,
    c1 * c2 * c3 + s1 * s2 * s3,
  ]
}

/** Hamilton product. Applies `b` first, then `a`. */
export function quatMul(a, b) {
  const [ax, ay, az, aw] = a
  const [bx, by, bz, bw] = b
  return [
    ax * bw + aw * bx + ay * bz - az * by,
    ay * bw + aw * by + az * bx - ax * bz,
    az * bw + aw * bz + ax * by - ay * bx,
    aw * bw - ax * bx - ay * by - az * bz,
  ]
}

export function quatNormalize([x, y, z, w]) {
  const n = Math.hypot(x, y, z, w)
  return n === 0 ? [0, 0, 0, 1] : [x / n, y / n, z / n, w / n]
}

export const IDENTITY_QUAT = [0, 0, 0, 1]

/**
 * Compose a stack of layers into per-bone quaternions.
 *
 * The correct counterpart to `blendLayers`: same inputs, but rotations are
 * multiplied rather than summed, so a limb driven by three layers at once
 * ends up where those three rotations actually put it.
 *
 * Each layer rotates the result so far **in the parent bone's frame** — the
 * new rotation multiplies on the left, so it applies after everything
 * beneath it. That ordering is the whole ballgame for an arm.
 *
 * REST rolls the upper arm down out of the T-pose by 1.32 rad about Z. A walk
 * swing is a pitch about X, and it means "swing forward and back about the
 * shoulder" — an axis in the shoulder's frame, not in the frame of the
 * already-rolled arm. Multiplying on the right applies the pitch first, so
 * the roll then drags its axis round with it: X maps to nearly −Y, and a
 * 0.38 rad forward swing turns into a twist of the upper arm about its own
 * length. Measured at the hand, that order gave 0.037 of forward travel
 * against 0.71 for this one — which is to say the arms were not swinging,
 * they were rotating in their sockets.
 */
export function composeLayers(layers) {
  const out = {}

  for (const { pose, weight = 1 } of layers) {
    if (!pose || weight === 0) continue

    for (const bone in pose) {
      const e = pose[bone]
      const scaled = weight === 1 ? e : [e[0] * weight, e[1] * weight, e[2] * weight]
      const q = eulerToQuat(scaled)
      out[bone] = bone in out ? quatMul(q, out[bone]) : q
    }
  }

  for (const bone in out) out[bone] = quatNormalize(out[bone])
  return out
}
