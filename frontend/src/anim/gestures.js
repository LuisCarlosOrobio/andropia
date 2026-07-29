/**
 * The gesture library: eight canonical gestures as pose keyframes.
 *
 * Data, not code, and data you own. Authoring gestures here rather than
 * sourcing animation clips sidesteps the entire licensing problem — these
 * are a few kilobytes of numbers written for this project, they need no
 * NOTICE entry, and because they are expressed in VRM normalised humanoid
 * space they work on **any** conformant avatar without retargeting.
 *
 * Each gesture is a list of keyframes:
 *
 *     { t: 0..1, bones: { boneName: [x, y, z] } }
 *
 * Rotations are **deltas from REST**, in radians. Keyframes interpolate with
 * easing, and the whole gesture fades in and out so it never snaps.
 *
 * These values are hand-tuned by reasoning about the rig rather than by
 * watching them, so treat them as a working first pass: the shapes are
 * right, the exact angles will want a pass with eyes on them.
 */

/** Right arm raised, forearm oscillating. The canonical greeting. */
export const wave = {
  duration: 1.8,
  keys: [
    { t: 0.0, bones: {} },
    {
      t: 0.2,
      bones: {
        rightUpperArm: [0, 0, -1.15],
        rightLowerArm: [0, -0.5, -0.45],
        rightShoulder: [0, 0, -0.12],
      },
    },
    {
      t: 0.42,
      bones: {
        rightUpperArm: [0, 0, -1.2],
        rightLowerArm: [0, -0.5, -0.95],
        rightShoulder: [0, 0, -0.12],
      },
    },
    {
      t: 0.62,
      bones: {
        rightUpperArm: [0, 0, -1.15],
        rightLowerArm: [0, -0.5, -0.35],
        rightShoulder: [0, 0, -0.12],
      },
    },
    {
      t: 0.8,
      bones: {
        rightUpperArm: [0, 0, -1.2],
        rightLowerArm: [0, -0.5, -0.85],
        rightShoulder: [0, 0, -0.1],
      },
    },
    { t: 1.0, bones: {} },
  ],
}

/** Head dips forward and returns. Agreement. */
export const nod = {
  duration: 0.9,
  keys: [
    { t: 0.0, bones: {} },
    { t: 0.3, bones: { head: [0.32, 0, 0], neck: [0.14, 0, 0] } },
    { t: 0.55, bones: { head: [-0.06, 0, 0], neck: [-0.03, 0, 0] } },
    { t: 0.78, bones: { head: [0.2, 0, 0], neck: [0.09, 0, 0] } },
    { t: 1.0, bones: {} },
  ],
}

/** Head turns side to side. Refusal. */
export const shake = {
  duration: 1.0,
  keys: [
    { t: 0.0, bones: {} },
    { t: 0.22, bones: { head: [0, 0.38, 0], neck: [0, 0.16, 0] } },
    { t: 0.5, bones: { head: [0, -0.38, 0], neck: [0, -0.16, 0] } },
    { t: 0.76, bones: { head: [0, 0.26, 0], neck: [0, 0.11, 0] } },
    { t: 1.0, bones: {} },
  ],
}

/** Shoulders up, palms out, head tilts. "Who knows." */
export const shrug = {
  duration: 1.4,
  keys: [
    { t: 0.0, bones: {} },
    {
      t: 0.35,
      bones: {
        leftShoulder: [0, 0, 0.34],
        rightShoulder: [0, 0, -0.34],
        leftUpperArm: [0, 0, 0.3],
        rightUpperArm: [0, 0, -0.3],
        leftLowerArm: [0, -0.55, -0.5],
        rightLowerArm: [0, 0.55, 0.5],
        head: [0.1, 0, 0.12],
      },
    },
    {
      t: 0.68,
      bones: {
        leftShoulder: [0, 0, 0.34],
        rightShoulder: [0, 0, -0.34],
        leftUpperArm: [0, 0, 0.3],
        rightUpperArm: [0, 0, -0.3],
        leftLowerArm: [0, -0.55, -0.5],
        rightLowerArm: [0, 0.55, 0.5],
        head: [0.1, 0, 0.12],
      },
    },
    { t: 1.0, bones: {} },
  ],
}

/** Hand toward the chin, head tilted, gaze up. Deliberation. */
export const think = {
  duration: 2.2,
  keys: [
    { t: 0.0, bones: {} },
    {
      t: 0.28,
      bones: {
        rightUpperArm: [0, 0, -0.55],
        rightLowerArm: [0, 1.15, -0.95],
        rightHand: [0.2, 0, 0],
        head: [-0.12, -0.16, 0.08],
        neck: [-0.05, -0.07, 0],
      },
    },
    {
      t: 0.72,
      bones: {
        rightUpperArm: [0, 0, -0.58],
        rightLowerArm: [0, 1.18, -0.98],
        rightHand: [0.22, 0, 0],
        head: [-0.16, -0.1, 0.08],
        neck: [-0.06, -0.04, 0],
      },
    },
    { t: 1.0, bones: {} },
  ],
}

/** Arm extends forward. Direction of attention. */
export const point = {
  duration: 1.5,
  keys: [
    { t: 0.0, bones: {} },
    {
      t: 0.3,
      bones: {
        rightUpperArm: [0, -1.15, 1.15],
        rightLowerArm: [0, 0.1, 0],
        rightShoulder: [0, -0.1, 0],
        head: [0, -0.1, 0],
      },
    },
    {
      t: 0.72,
      bones: {
        rightUpperArm: [0, -1.18, 1.15],
        rightLowerArm: [0, 0.1, 0],
        rightShoulder: [0, -0.1, 0],
        head: [0, -0.1, 0],
      },
    },
    { t: 1.0, bones: {} },
  ],
}

/** Both arms up. Celebration. */
export const cheer = {
  duration: 1.6,
  keys: [
    { t: 0.0, bones: {} },
    {
      t: 0.22,
      bones: {
        leftUpperArm: [0, 0, 1.05],
        rightUpperArm: [0, 0, -1.05],
        leftLowerArm: [0, -0.3, -0.2],
        rightLowerArm: [0, 0.3, 0.2],
        spine: [-0.08, 0, 0],
        head: [-0.14, 0, 0],
      },
    },
    {
      t: 0.45,
      bones: {
        leftUpperArm: [0, 0, 1.2],
        rightUpperArm: [0, 0, -1.2],
        leftLowerArm: [0, -0.2, -0.1],
        rightLowerArm: [0, 0.2, 0.1],
        spine: [-0.1, 0, 0],
        head: [-0.18, 0, 0],
      },
    },
    {
      t: 0.7,
      bones: {
        leftUpperArm: [0, 0, 1.05],
        rightUpperArm: [0, 0, -1.05],
        spine: [-0.06, 0, 0],
        head: [-0.12, 0, 0],
      },
    },
    { t: 1.0, bones: {} },
  ],
}

/** A weight shift and a glance. Breaks the stillness of a long idle. */
export const idle_variant = {
  duration: 2.6,
  keys: [
    { t: 0.0, bones: {} },
    {
      t: 0.3,
      bones: {
        hips: [0, 0.06, 0.03],
        spine: [0, 0.05, -0.02],
        head: [0.04, 0.18, 0],
        leftUpperArm: [0, 0, 0.06],
        rightUpperArm: [0, 0, -0.04],
      },
    },
    {
      t: 0.7,
      bones: {
        hips: [0, -0.04, -0.03],
        spine: [0, -0.03, 0.02],
        head: [-0.02, -0.12, 0],
      },
    },
    { t: 1.0, bones: {} },
  ],
}

export const GESTURES = {
  wave,
  nod,
  shake,
  shrug,
  think,
  point,
  cheer,
  idle_variant,
}

/** Names this library can perform procedurally. Mirrors `andropia.vocab.GESTURES`. */
export const GESTURE_NAMES = Object.keys(GESTURES)
