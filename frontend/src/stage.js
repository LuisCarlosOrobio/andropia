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
import { bodyState } from './pose.js'

const PLACEHOLDER_COLOUR = {
  idle: 0x5c6672,
  walk: 0x2c6d8c,
  gesture: 0xa05714,
}

export class Stage {
  constructor(container) {
    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(0x0e1114)
    this.scene.fog = new THREE.Fog(0x0e1114, 34, 95)

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

    this._lights()
    this._ground()

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

  // -- construction ------------------------------------------------------

  _lights() {
    this.scene.add(new THREE.HemisphereLight(0x9fb8cc, 0x1a1f24, 1.4))

    const key = new THREE.DirectionalLight(0xffffff, 2.0)
    key.position.set(6, 12, 5)
    key.castShadow = true
    key.shadow.mapSize.set(2048, 2048)
    key.shadow.camera.near = 1
    key.shadow.camera.far = 60
    const extent = 22
    Object.assign(key.shadow.camera, {
      left: -extent,
      right: extent,
      top: extent,
      bottom: -extent,
    })
    key.shadow.bias = -0.0005
    this.scene.add(key)

    // A cool rim from behind, so silhouettes read against the dark ground.
    const rim = new THREE.DirectionalLight(0x88aacc, 0.7)
    rim.position.set(-7, 5, -8)
    this.scene.add(rim)
  }

  _ground() {
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(200, 200),
      new THREE.MeshStandardMaterial({ color: 0x151a1f, roughness: 1.0 })
    )
    floor.rotation.x = -Math.PI / 2
    floor.receiveShadow = true
    this.scene.add(floor)

    const grid = new THREE.GridHelper(120, 60, 0x2a3036, 0x1c2126)
    grid.material.transparent = true
    grid.material.opacity = 0.4
    grid.position.y = 0.002
    this.scene.add(grid)

    this.groundPlane = floor
  }

  setScene(scene) {
    for (const mark of scene.landmarks ?? []) this._landmark(mark)
  }

  _landmark({ id, pos, description }) {
    if (this.landmarks.has(id)) return

    const group = new THREE.Group()
    group.position.set(pos[0], pos[1], pos[2])

    const pin = new THREE.Mesh(
      new THREE.ConeGeometry(0.3, 1.0, 6),
      new THREE.MeshStandardMaterial({ color: 0x3a444e, roughness: 0.9 })
    )
    pin.position.y = 0.5
    pin.castShadow = true
    group.add(pin)
    group.add(makeLabel(description || id, 1.5))

    this.scene.add(group)
    this.landmarks.set(id, group)
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

    const label = makeLabel(id, 1.95)
    group.add(label)

    const speech = makeLabel('', 2.35)
    speech.visible = false
    group.add(speech)

    this.scene.add(group)
    const entry = { group, placeholder, body: null, label, speech, requested: false }
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

      if (state.speech) {
        setLabel(entry.speech, state.speech)
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

    this.bodyCache.get(packId).then((body) => {
      // A null body leaves the capsule in place. That is deliberate: a
      // visible placeholder says "this avatar did not load" far more
      // clearly than a being that silently vanishes.
      if (!body) return
      entry.body = body
      entry.group.add(body.group)
      entry.placeholder.visible = false
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

    if (!this.selected) return
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

function makeLabel(text, y) {
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ transparent: true, depthTest: false })
  )
  sprite.position.y = y
  setLabel(sprite, text)
  return sprite
}

function setLabel(sprite, text) {
  if (sprite.userData.text === text) return
  sprite.userData.text = text

  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  const font = '500 32px ui-monospace, Menlo, monospace'

  ctx.font = font
  const width = Math.max(8, ctx.measureText(text).width)
  canvas.width = Math.ceil(width) + 24
  canvas.height = 48

  ctx.font = font
  ctx.fillStyle = 'rgba(14,17,20,0.75)'
  roundRect(ctx, 0, 0, canvas.width, canvas.height, 8)
  ctx.fill()
  ctx.fillStyle = '#e6e9ec'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, 12, canvas.height / 2)

  sprite.material.map?.dispose()
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  sprite.material.map = texture
  sprite.material.needsUpdate = true
  sprite.scale.set(canvas.width / 115, canvas.height / 115, 1)
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
