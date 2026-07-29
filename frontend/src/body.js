/**
 * A loaded body, and the one place that mutates it.
 *
 * Everything above this file is plain data: `bodyState` computes numbers,
 * `Body.apply` pushes them into three.js. That is the whole imperative
 * surface of the renderer — sixty frames a second forbids allocating fresh
 * objects, and three.js is built around in-place mutation, so this is where
 * the codebase's rule about contained imperative blocks is spent.
 *
 * Handles both container formats behind one interface:
 *
 *   VRM   expressions via `expressionManager`, humanoid rig, spring bones
 *   glTF  expressions via morph target influences, plain skinned mesh
 *
 * The caller never learns which it got. That is what makes bodies swappable.
 */

import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'

// Crossfade time between locomotion states. Short enough to feel responsive,
// long enough that a being does not snap between standing and walking.
const LOCOMOTION_FADE = 0.22

export async function loadBody(pack) {
  const loader = new GLTFLoader()
  if (pack.type === 'vrm') {
    loader.register((parser) => new VRMLoaderPlugin(parser))
  }

  const gltf = await loader.loadAsync(pack.model)
  const vrm = gltf.userData.vrm ?? null

  if (vrm) {
    // Removes unused vertices and joints; without it VRMs carry a lot of
    // geometry that is never drawn.
    VRMUtils.removeUnnecessaryVertices(gltf.scene)
    VRMUtils.combineSkeletons(gltf.scene)
    vrm.scene.traverse((o) => {
      o.frustumCulled = false // skinned meshes get culled wrongly when posed
    })
  }

  return new Body(pack, gltf, vrm)
}

export class Body {
  constructor(pack, gltf, vrm) {
    this.pack = pack
    this.vrm = vrm
    this.root = vrm ? vrm.scene : gltf.scene

    // VRM 1.0 faces +Z; glTF convention here faces -Z. Wrapping in a group
    // means the caller sets one rotation and never thinks about it again.
    this.group = new THREE.Group()
    if (vrm) this.root.rotation.y = Math.PI
    this.group.add(this.root)

    this.mixer = new THREE.AnimationMixer(this.root)
    this.actions = new Map()
    for (const clip of gltf.animations ?? []) {
      this.actions.set(clip.name, this.mixer.clipAction(clip))
    }

    this.currentLocomotion = null
    this.currentGesture = null

    // glTF morph targets, resolved once: name -> [mesh, index] pairs, since
    // one named target may exist on several primitives.
    this.morphs = new Map()
    if (!vrm) this._indexMorphs()

    this._lastYaw = 0
  }

  get clipNames() {
    return [...this.actions.keys()]
  }

  /** Push a computed BodyState into the scene. The only mutation here. */
  apply(state, dt) {
    const [x, y, z] = state.position
    this.group.position.set(x, y, z)
    if (state.yaw !== null) this._lastYaw = state.yaw
    this.group.rotation.y = this._lastYaw

    this._applyExpressions(state.expressions)
    this._applyLocomotion(state.locomotion)
    this._applyGesture(state.gesture)

    this.mixer.update(dt)
    // Spring bones read the skeleton after animation, so this must come
    // last. Hair and clothing are purely cosmetic and may be sloppy —
    // nothing here can affect what the simulation does next.
    if (this.vrm) this.vrm.update(dt)
  }

  dispose() {
    this.mixer.stopAllAction()
    if (this.vrm) VRMUtils.deepDispose(this.vrm.scene)
    this.group.removeFromParent()
  }

  // -- internals ---------------------------------------------------------

  _indexMorphs() {
    this.root.traverse((obj) => {
      const dict = obj.morphTargetDictionary
      if (!dict) return
      for (const [name, index] of Object.entries(dict)) {
        if (!this.morphs.has(name)) this.morphs.set(name, [])
        this.morphs.get(name).push([obj, index])
      }
    })
  }

  _applyExpressions(weights) {
    if (this.vrm?.expressionManager) {
      const manager = this.vrm.expressionManager
      // Reset every preset first, so a weight that disappears from the state
      // actually clears rather than sticking at its last value.
      for (const expression of manager.expressions) {
        manager.setValue(expression.expressionName, 0)
      }
      for (const [name, weight] of Object.entries(weights)) {
        manager.setValue(name, weight)
      }
      return
    }

    for (const [name, targets] of this.morphs) {
      const weight = weights[name] ?? 0
      for (const [mesh, index] of targets) {
        mesh.morphTargetInfluences[index] = weight
      }
    }
  }

  _applyLocomotion({ clip }) {
    if (clip === this.currentLocomotion) return

    const next = clip ? this.actions.get(clip) : null
    const previous = this.currentLocomotion
      ? this.actions.get(this.currentLocomotion)
      : null

    if (next) {
      next.reset().setLoop(THREE.LoopRepeat, Infinity).fadeIn(LOCOMOTION_FADE).play()
    }
    if (previous) previous.fadeOut(LOCOMOTION_FADE)

    this.currentLocomotion = clip
  }

  _applyGesture(gesture) {
    const name = gesture?.clip ?? null

    if (name === this.currentGesture) {
      // Drive the clip from the simulation's normalised phase rather than
      // letting the mixer run free, so a gesture stays in step with the
      // world even if the browser drops frames.
      if (name) {
        const action = this.actions.get(name)
        if (action) action.time = gesture.phase * action.getClip().duration
      }
      return
    }

    if (this.currentGesture) {
      this.actions.get(this.currentGesture)?.fadeOut(0.15)
    }

    if (name) {
      const action = this.actions.get(name)
      if (action) {
        action.reset().setLoop(THREE.LoopOnce, 1).fadeIn(0.1).play()
        action.clampWhenFinished = true
      }
    }

    this.currentGesture = name
  }
}
