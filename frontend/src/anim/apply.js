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

import * as THREE from 'three'

// Allocated once. Reusing these is the entire reason this file is imperative.
const _euler = new THREE.Euler()
const _quat = new THREE.Quaternion()

/**
 * Write a pose onto a VRM's normalised humanoid bones.
 *
 * Bones the pose does not mention are reset to their rest orientation, so a
 * gesture ending actually releases the arm rather than leaving it stuck
 * where the last frame put it.
 */
export function applyPose(vrm, pose) {
  const humanoid = vrm?.humanoid
  if (!humanoid) return

  for (const boneName of TRACKED_BONES) {
    const node = humanoid.getNormalizedBoneNode(boneName)
    if (!node) continue // rig lacks this optional bone; skip rather than fail

    const rotation = pose[boneName]
    if (rotation) {
      _euler.set(rotation[0], rotation[1], rotation[2], 'YXZ')
      node.quaternion.setFromEuler(_euler)
    } else {
      node.quaternion.identity()
    }
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
 * Deliberately a fixed list rather than "every bone in the rig". Legs are
 * absent because procedural locomotion of the lower body looks wrong at any
 * effort level short of real IK — bodies glide, and a walk clip is the right
 * answer when one exists. Fingers are absent because nothing authored here
 * needs them and resetting them every frame would fight any clip that does.
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
]
