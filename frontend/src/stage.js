/**
 * The three.js scene.
 *
 * Holds every object that exists only to be looked at — meshes, lights,
 * camera, materials — and nothing the simulation depends on.
 *
 * Bodies load asynchronously. Until one arrives a being is drawn as a
 * capsule, and if its model fails it *stays* a capsule with a warning in the
 * console. A broken avatar costs you one body, never the world.
 */

import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { wrapText } from './stage-text.js'
import { build as buildWorld } from './world.js'
import { bodyState } from './pose.js'

const PLACEHOLDER_COLOUR = {
  idle: 0x5c6672,
  walk: 0x2c6d8c,
  gesture: 0xa05714,
}

export class Stage {
  constructor(container) {
    this.scene = new THREE.Scene()
    // Deliberately bare. The ground, the sky, the lights and everything
    // standing on them arrive through `setWorld`, from a world pack, so the
    // numbers that draw this place are the numbers beings are told about it.
    // Until one arrives there is nothing to look at, which is honest.
    this.world = null
    this.groundPlane = null

    this.camera = new THREE.PerspectiveCamera(50, 1, 0.1, 500)
    this.camera.position.set(8, 6, 11)

    this.renderer = new THREE.WebGLRenderer({ antialias: true })
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio))
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    container.appendChild(this.renderer.domElement)

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.target.set(0, 1, 0)

    this.beings = new Map() // id -> { group, placeholder, body, label, speech }
    this.landmarks = new Map()
    this.bodyCache = null

    this.raycaster = new THREE.Raycaster()
    this.pointer = new THREE.Vector2()
    this.selected = null
    this.onPick = null

    this._resize()
    window.addEventListener('resize', () => this._resize())
    this.renderer.domElement.addEventListener('pointerdown', (e) => this._pick(e))
  }

  setBodyCache(cache) {
    this.bodyCache = cache
  }

  // -- the world ---------------------------------------------------------

  /**
   * Replace the world with the one this manifest declares.
   *
   * Repeatable by teardown: the previous world's geometry and materials are
   * released before the next is built, so a viewer reconnecting to a restarted
   * server gets a fresh scene rather than two worlds on the same ground.
   */
  setWorld(manifest) {
    if (this.world) {
      this.scene.remove(this.world)
      release(this.world)
    }

    const { group, background, fog, missing } = buildWorld(manifest)
    this.scene.add(group)
    this.scene.background = background
    this.scene.fog = fog
    this.world = group
    this.groundPlane = group.getObjectByName('floor')

    // Said out loud. A shape nobody drew is a place beings can walk to and
    // nobody can see, and that failing quietly is why this format exists.
    for (const name of missing) {
      console.warn(`world: no shape implemented for ${name} — nothing drawn`)
    }
  }


  setScene(scene) {
    for (const mark of scene.landmarks ?? []) this._landmark(mark)
  }

  _landmark({ id, pos, description }) {
    if (this.landmarks.has(id)) return

    const group = new THREE.Group()
    group.position.set(pos[0], pos[1], pos[2])

    // A nameplate and nothing else. The thing itself is drawn by the world
    // pack — a cone pin used to stand in for it, which was right when a
    // landmark was a point on a bare plane and is a second object over the
    // same spot now that the pond is actually a pond.
    const mark = makePlate(description || id)
    mark.position.y = this._clearanceAt(id)
    group.add(mark)

    this.scene.add(group)
    this.landmarks.set(id, group)
  }

  /** How high a landmark's plate must float to clear what was drawn there. */
  _clearanceAt(id) {
    const drawn = this.world?.getObjectByName(`feature:${id}`)
    if (!drawn) return 1.5

    // Measured rather than taken from the manifest, so a shape that offsets its
    // own geometry — and every shape here does — cannot put a label inside
    // itself. The box is local, and the group is already at the feature.
    const box = new THREE.Box3().setFromObject(drawn)
    return box.max.y - drawn.position.y + 0.5
  }

  _being(id) {
    if (this.beings.has(id)) return this.beings.get(id)

    const group = new THREE.Group()

    // Stand-in until the real body arrives, and permanent if it never does.
    const placeholder = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.28, 0.95, 6, 12),
      new THREE.MeshStandardMaterial({
        color: 0x5c6672,
        roughness: 0.6,
        transparent: true,
        opacity: 0.85,
      })
    )
    placeholder.position.y = 0.78
    placeholder.castShadow = true
    group.add(placeholder)

    const label = makePlate(id)
    group.add(label)

    const speech = makePlate('', { wrap: SPEECH_WRAP, tone: 'speech' })
    speech.visible = false
    group.add(speech)

    this.scene.add(group)
    const entry = {
      id,
      group,
      placeholder,
      body: null,
      label,
      speech,
      requested: false,
      // Top of the placeholder capsule, until a real body reports its own.
      // Plates are stacked from here, so it is the one measurement that has to
      // track whichever avatar is actually loaded — a fixed offset puts the
      // name inside a tall head or floating above a short one.
      head: 1.62,
    }
    this.beings.set(id, entry)
    return entry
  }

  // -- per-frame ---------------------------------------------------------

  draw(previous, current, alpha, packs, dt) {
    const before = new Map((previous?.entities ?? []).map((e) => [e.id, e]))
    const seen = new Set()

    for (const now of current.entities) {
      seen.add(now.id)
      const entry = this._being(now.id)
      const was = before.get(now.id) ?? now
      const pack = packs?.get(now.pack) ?? null

      this._ensureBody(entry, now.pack)

      const state = bodyState(was, now, pack, alpha)
      state.selected = this.selected === now.id

      if (entry.body) {
        entry.body.apply(state, dt)
      } else {
        this._applyPlaceholder(entry, state, now)
      }

      // Label and speech live on the outer group, so they stay upright and
      // in place whichever kind of body is underneath.
      entry.group.position.set(...state.position)
      if (state.yaw !== null && !entry.body) entry.group.rotation.y = state.yaw

      // Stacked from the head, bottom edge upward: name first, then speech
      // clearing whatever height the name turned out to be. Recomputed per
      // frame because the speech plate changes height with its line count.
      entry.label.position.y = entry.head + 0.06
      if (state.speech) {
        setPlate(entry.speech, state.speech)
        entry.speech.position.y =
          entry.label.position.y + entry.label.userData.height + 0.05
        entry.speech.visible = true
      } else {
        entry.speech.visible = false
      }
    }

    for (const [id, entry] of this.beings) {
      if (seen.has(id)) continue
      entry.body?.dispose()
      this.scene.remove(entry.group)
      this.beings.delete(id)
    }
  }

  _ensureBody(entry, packId) {
    if (entry.requested || !this.bodyCache || !packId) return
    entry.requested = true

    this.bodyCache.create(packId, entry.id).then((body) => {
      // A null body leaves the capsule in place. That is deliberate: a
      // visible placeholder says "this avatar did not load" far more
      // clearly than a being that silently vanishes.
      if (!body) return
      entry.body = body
      entry.group.add(body.group)
      entry.placeholder.visible = false
      entry.head = headHeight(body)
    })
  }

  _applyPlaceholder(entry, state, now) {
    const colour = PLACEHOLDER_COLOUR[now.action] ?? 0x5c6672
    entry.placeholder.material.color.setHex(colour)
    entry.placeholder.material.emissive.setHex(state.selected ? 0x224455 : 0x000000)

    // A gesture with no clip still has to look like something, or it is
    // indistinguishable from a bug. B3 replaces this with real poses.
    if (state.gesture) {
      entry.placeholder.position.y =
        0.78 + Math.sin(state.gesture.phase * Math.PI) * 0.16
    } else {
      entry.placeholder.position.y = 0.78
    }
  }

  render() {
    this.controls.update()
    this.renderer.render(this.scene, this.camera)
  }

  // -- interaction -------------------------------------------------------

  _pick(event) {
    const rect = this.renderer.domElement.getBoundingClientRect()
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
    this.raycaster.setFromCamera(this.pointer, this.camera)

    // Test whole being groups, so clicking any part of a rendered body
    // selects it rather than only its capsule.
    const groups = [...this.beings.values()].map((b) => b.group)
    const hit = this.raycaster.intersectObjects(groups, true)[0]

    if (hit) {
      const id = this._ownerOf(hit.object)
      if (id) {
        this.selected = this.selected === id ? null : id
        return
      }
    }

    // No world yet means no floor to click on, which happens for the fraction
    // of a second between the socket opening and the manifest arriving.
    if (!this.selected || !this.groundPlane) return
    const onGround = this.raycaster.intersectObject(this.groundPlane, false)[0]
    if (onGround && this.onPick) {
      const p = onGround.point
      this.onPick(this.selected, [p.x, 0, p.z])
    }
  }

  _ownerOf(object) {
    for (const [id, entry] of this.beings) {
      let node = object
      while (node) {
        if (node === entry.group) return id
        node = node.parent
      }
    }
    return null
  }

  _resize() {
    const w = window.innerWidth
    const h = window.innerHeight
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    this.renderer.setSize(w, h)
  }
}

// --------------------------------------------------------------------------

/**
 * A nameplate or speech bubble, in the MMO idiom.
 *
 * Two things make these stack predictably instead of drifting.
 *
 * **Bottom-anchored.** A three.js sprite is centred on its position by
 * default, so a taller bubble grows in both directions and a fixed y offset
 * puts a long line straight through the name below it. Setting `center` to the
 * bottom edge makes the anchor the one point that must not move: everything
 * grows upward from the head.
 *
 * **A fixed world height per line.** Canvas pixels are converted at one
 * constant, so a plate's size in the world depends on how many lines it has and
 * nothing else. Text length changes the width; it can never change the height,
 * which is what stops a long utterance from shoving its own name off the head.
 */
function makePlate(text, { wrap = 0, tone = "name" } = {}) {
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ transparent: true, depthTest: false })
  )
  // Anchor the bottom edge. Everything above a being's head is stacked from
  // here, so this is the line that has to be stable.
  sprite.center.set(0.5, 0)
  sprite.userData.wrap = wrap
  sprite.userData.tone = tone
  setPlate(sprite, text)
  return sprite
}

/**
 * How high above a being's origin its plates should start.
 *
 * Measured from the loaded model rather than assumed, because avatars differ:
 * the same offset that clears a 1.6 m anime figure sits inside the head of a
 * shorter one and floats above a taller one. A VRM exposes its head bone, which
 * is the honest anchor; anything else falls back to the bounding box, and a
 * model that reports neither keeps the placeholder's height.
 */
function headHeight(body, fallback = 1.62) {
  const head = body.vrm?.humanoid?.getNormalizedBoneNode?.('head')
  if (head) {
    // Rest height in the normalised rig, plus a little for the skull above the
    // bone itself — the head bone sits at the neck join, not the crown.
    const y = new THREE.Vector3()
    head.getWorldPosition(y)
    if (Number.isFinite(y.y) && y.y > 0.2) return y.y + 0.18
  }

  const box = new THREE.Box3().setFromObject(body.root)
  return Number.isFinite(box.max.y) && box.max.y > 0.2 ? box.max.y + 0.06 : fallback
}

/** World metres per canvas pixel. One constant, so line height never varies. */
const PLATE_SCALE = 1 / 115

/** Longest a speech line may get before it wraps, in characters. */
const SPEECH_WRAP = 34

const PLATE_TONES = {
  name: { font: "600 30px ui-monospace, Menlo, monospace", fill: "#cfd6dd",
          back: "rgba(14,17,20,0.66)", pad: 12, line: 44 },
  speech: { font: "500 30px ui-sans-serif, system-ui, sans-serif", fill: "#f2f5f8",
            back: "rgba(20,26,32,0.86)", pad: 16, line: 40 },
}

function setPlate(sprite, text) {
  if (sprite.userData.text === text) return
  sprite.userData.text = text

  const tone = PLATE_TONES[sprite.userData.tone] ?? PLATE_TONES.name
  const canvas = document.createElement("canvas")
  const ctx = canvas.getContext("2d")

  ctx.font = tone.font
  const lines = sprite.userData.wrap ? wrapText(text, sprite.userData.wrap) : [text]
  const widest = Math.max(8, ...lines.map((l) => ctx.measureText(l).width))

  canvas.width = Math.ceil(widest) + tone.pad * 2
  canvas.height = lines.length * tone.line + tone.pad

  // Re-set after resizing: changing canvas dimensions resets the 2d context,
  // so a font assigned before this point is silently discarded and every plate
  // renders in the browser default.
  ctx.font = tone.font
  ctx.fillStyle = tone.back
  roundRect(ctx, 0, 0, canvas.width, canvas.height, 10)
  ctx.fill()

  ctx.fillStyle = tone.fill
  ctx.textBaseline = "middle"
  lines.forEach((line, i) => {
    ctx.fillText(line, tone.pad, tone.pad / 2 + tone.line * (i + 0.5))
  })

  sprite.material.map?.dispose()
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  sprite.material.map = texture
  sprite.material.needsUpdate = true
  sprite.scale.set(canvas.width * PLATE_SCALE, canvas.height * PLATE_SCALE, 1)
  // What the next plate up has to clear.
  sprite.userData.height = canvas.height * PLATE_SCALE
}

/**
 * Free the GPU memory an object tree holds.
 *
 * Removing a group from a scene drops the reference and nothing else; geometry
 * and materials live on the GPU until told otherwise. Called when a world is
 * replaced, which is rare — but a viewer left reconnecting to a restarting
 * server would otherwise leak a whole world each time.
 */
function release(root) {
  root.traverse((node) => {
    node.geometry?.dispose()
    for (const material of [node.material].flat()) {
      material?.map?.dispose()
      material?.dispose?.()
    }
  })
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}
