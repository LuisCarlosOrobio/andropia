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
import { applyExpressions, applyGaze, applyPose } from './anim/apply.js'
import { blendLayers } from './anim/pose.js'
import { blinkWeight, layersFor, visemeWeights } from './anim/layers.js'

// Crossfade time between locomotion states. Short enough to feel responsive,
// long enough that a being does not snap between standing and walking.
const LOCOMOTION_FADE = 0.22

/**
 * Build one body from already-fetched bytes.
 *
 * Takes a buffer rather than a URL so the caller can share the download
 * across several beings wearing the same pack, while each still gets its
 * own skeleton and mixer.
 */
export async function loadBody(pack, buffer, beingId = pack.id) {
  const loader = new GLTFLoader()
  if (pack.type === 'vrm') {
    loader.register((parser) => new VRMLoaderPlugin(parser))
  }

  const gltf = await loader.parseAsync(buffer, '')
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

  return new Body(pack, gltf, vrm, beingId)
}

export class Body {
  constructor(pack, gltf, vrm, beingId = pack.id) {
    this.pack = pack
    this.vrm = vrm
    this.root = vrm ? vrm.scene : gltf.scene

    // A wrapping group, so the caller sets one rotation and never thinks
    // about the model's internal orientation.
    //
    // No flip. VRM 1.0 faces +Z, and `facingToYaw` uses atan2(x, z) so that
    // yaw 0 also means +Z — the two already agree. An earlier version
    // rotated the root by π, which made every avatar face away from its
    // direction of travel. Invisible while bodies slid; unmistakable the
    // moment their legs started moving.
    this.group = new THREE.Group()
    this.group.add(this.root)

    this.mixer = new THREE.AnimationMixer(this.root)
    this.actions = new Map()
    for (const clip of gltf.animations ?? []) {
      this.actions.set(clip.name, this.mixer.clipAction(clip))
    }

    this.currentLocomotion = null
    this.currentGesture = null

    // Seconds of animation time. Advanced by dt rather than read from a
    // clock, so two runs of the same recording animate identically.
    this.clock = 0
    // Ground distance travelled. The walk cycle is driven by this rather
    // than by time, so a being's feet land at consistent points on the
    // ground instead of skating whenever its speed differs from whatever
    // stride rate happened to be hardcoded.
    this.distance = 0
    this._lastPos = null
    // Per-body offset, so a crowd does not breathe or blink in unison —
    // which is uncanny in a way that is hard to name and impossible to miss.
    this.phase = hashPhase(beingId)

    // A gaze target, moved rather than reallocated each frame.
    this.gazeTarget = new THREE.Object3D()
    this.group.add(this.gazeTarget)

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
    this.clock += dt

    const [x, y, z] = state.position
    if (this._lastPos) {
      const dx = x - this._lastPos[0]
      const dz = z - this._lastPos[2]
      this.distance += Math.hypot(dx, dz)
    }
    this._lastPos = state.position

    this.group.position.set(x, y, z)
    if (state.yaw !== null) this._lastYaw = state.yaw
    this.group.rotation.y = this._lastYaw

    this._applyLocomotion(state.locomotion)
    this._applyGesture(state.gesture)

    if (this.vrm) {
      // Procedural: breathing, sway, blink, gaze and any gesture with no
      // clip. Composed as data, applied once.
      const options = { phase: this.phase, distance: this.distance }
      const pose = blendLayers(layersFor(state, this.clock, options))
      applyPose(this.vrm, pose)

      applyExpressions(this.vrm, {
        ...state.expressions,
        ...visemeWeights(this.clock, Boolean(state.speech), options),
        blink: blinkWeight(this.clock, options),
      })

      applyGaze(this.vrm, this.gazeTarget, state.gazeAt ?? null)
    } else {
      this._applyMorphs(state.expressions)
    }

    this.mixer.update(dt)
    // Spring bones read the skeleton after everything else, so this comes
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

  _applyMorphs(weights) {
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


/**
 * A stable per-being phase offset in [0, 2π).
 *
 * Keyed on the being, not the pack: three robots in one world must not
 * breathe and blink in lockstep. Derived by hashing rather than drawn
 * randomly, so the same being always breathes on the same beat and a replay
 * looks like the run it recorded.
 */
function hashPhase(id) {
  let h = 2166136261
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return ((h >>> 0) / 4294967296) * Math.PI * 2
}
