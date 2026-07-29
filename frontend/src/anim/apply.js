/**
 * The mutation boundary.
 *
 * Everything upstream — layers, blending, easing, keyframe sampling — is a
 * pure function over plain numbers. This file is where those numbers become
 * rotations on a skeleton, and it is the only place in the animation system
 * that touches three.js.
 *
 * It mutates, on purpose. Sixty frames a second with a few dozen bones per
 * body forbids allocating fresh objects per frame, and three.js is built
 * around in-place mutation. The scratch objects below are allocated once at
 * module scope and reused forever.
 *
 * Everything here writes to the **normalised** humanoid rig. three-vrm maps
 * that onto whatever the artist actually built, which is what lets one
 * authored pose apply correctly to any conformant avatar.
 */

/**
 * Write composed rotations onto a VRM's normalised humanoid bones.
 *
 * Takes quaternions, not Euler angles: `composeLayers` has already
 * multiplied the layer stack, and converting back to Euler here would
 * reintroduce exactly the gimbal artefacts that composition avoids.
 *
 * Bones the pose does not mention are reset to identity, so a gesture
 * ending releases the limb rather than leaving it wherever the last frame
 * put it.
 */
export function applyPose(vrm, quats, hipY = null) {
  const humanoid = vrm?.humanoid
  if (!humanoid) return

  for (const boneName of TRACKED_BONES) {
    const node = humanoid.getNormalizedBoneNode(boneName)
    if (!node) continue // rig lacks this optional bone; skip rather than fail

    const q = quats[boneName]
    if (q) {
      node.quaternion.set(q[0], q[1], q[2], q[3])
    } else {
      node.quaternion.identity()
    }
  }

  // The pelvis is the one bone that translates. A walking body is shorter
  // than a standing one, and without this the legs get asked to reach further
  // than they can, the solver clamps, and the feet start sliding again — the
  // exact problem the IK exists to remove.
  //
  // Hips only: VRM reserves translation for that bone, and moving any other
  // stretches the mesh rather than the body. An absolute height rather than a
  // delta, because the caller measured the rig and this file has not — it is
  // a mutation boundary, and keeping the arithmetic upstream keeps it one.
  if (hipY !== null) {
    const hips = humanoid.getNormalizedBoneNode('hips')
    if (hips) hips.position.y = hipY
  }
}

/**
 * Push expression weights, resetting any that are no longer present.
 *
 * Resetting first matters: without it a weight that disappears from the
 * computed state simply persists, and a being that stopped being angry
 * stays angry forever.
 */
export function applyExpressions(vrm, weights) {
  const manager = vrm?.expressionManager
  if (!manager) return

  for (const expression of manager.expressions) {
    manager.setValue(expression.expressionName, 0)
  }
  for (const name in weights) {
    manager.setValue(name, weights[name])
  }
}

/**
 * Point the gaze at a world position, or release it.
 *
 * VRM's own look-at handles the eye and head rotation limits, so this only
 * has to move a target. Gaze is the cheapest presence cue after blinking —
 * a being that tracks you feels aware in a way a still one does not.
 */
export function applyGaze(vrm, target, worldPosition) {
  if (!vrm?.lookAt) return

  if (worldPosition) {
    target.position.set(worldPosition[0], worldPosition[1], worldPosition[2])
    vrm.lookAt.target = target
  } else {
    vrm.lookAt.target = null
  }
}

/**
 * The bones the procedural system drives.
 *
 * A fixed list rather than "every bone in the rig". Fingers are absent
 * because nothing authored here needs them, and resetting them every frame
 * would fight any clip that does.
 *
 * Legs were absent at first, on the reasoning that procedural locomotion
 * without IK looks wrong. That was the wrong call: a being that glides
 * across the ground reads as *broken*, while an imperfect walk reads as
 * stylised. Doing something beats doing nothing here.
 */
export const TRACKED_BONES = [
  'hips',
  'spine',
  'chest',
  'upperChest',
  'neck',
  'head',
  'leftShoulder',
  'leftUpperArm',
  'leftLowerArm',
  'leftHand',
  'rightShoulder',
  'rightUpperArm',
  'rightLowerArm',
  'rightHand',
  'leftUpperLeg',
  'leftLowerLeg',
  'leftFoot',
  'rightUpperLeg',
  'rightLowerLeg',
  'rightFoot',
]
