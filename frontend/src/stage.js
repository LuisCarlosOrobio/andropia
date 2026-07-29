/**
 * The three.js scene.
 *
 * Holds every object that exists only to be looked at — meshes, lights,
 * camera, materials — and nothing that the simulation depends on. This is
 * the one place in the frontend permitted to mutate, for the same reason
 * `applyPose` is on the Python side: sixty frames a second forbids
 * allocating fresh objects, and three.js is built around in-place mutation.
 *
 * Everything upstream (frame data, interpolation factors) is plain values.
 */

import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

const EMOTION_COLOUR = {
  neutral: 0x9aa4ae,
  happy: 0x7fbe9d,
  angry: 0xe08b82,
  sad: 0x7a93b8,
  relaxed: 0x9dc4a8,
  surprised: 0xddab6c,
}

const ACTION_COLOUR = {
  idle: 0x5c6672,
  walk: 0x2c6d8c,
  gesture: 0xa05714,
}

export class Stage {
  constructor(container) {
    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(0x0e1114)
    this.scene.fog = new THREE.Fog(0x0e1114, 30, 90)

    this.camera = new THREE.PerspectiveCamera(50, 1, 0.1, 500)
    this.camera.position.set(10, 9, 14)

    this.renderer = new THREE.WebGLRenderer({ antialias: true })
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio))
    container.appendChild(this.renderer.domElement)

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.target.set(0, 1, 0)

    this._lights()
    this._ground()

    // id -> { group, body, nose, label }
    this.beings = new Map()
    this.landmarks = new Map()

    this.raycaster = new THREE.Raycaster()
    this.pointer = new THREE.Vector2()
    this.selected = null
    this.onPick = null

    this._resize()
    window.addEventListener('resize', () => this._resize())
    this.renderer.domElement.addEventListener('pointerdown', (e) => this._pick(e))
  }

  // -- construction ------------------------------------------------------

  _lights() {
    this.scene.add(new THREE.HemisphereLight(0x9fb8cc, 0x1a1f24, 1.1))
    const key = new THREE.DirectionalLight(0xffffff, 1.6)
    key.position.set(8, 14, 6)
    this.scene.add(key)
  }

  _ground() {
    const grid = new THREE.GridHelper(120, 60, 0x2a3036, 0x1c2126)
    grid.material.transparent = true
    grid.material.opacity = 0.55
    this.scene.add(grid)

    // An invisible plane, purely to catch clicks for "walk there".
    this.groundPlane = new THREE.Mesh(
      new THREE.PlaneGeometry(200, 200),
      new THREE.MeshBasicMaterial({ visible: false })
    )
    this.groundPlane.rotation.x = -Math.PI / 2
    this.scene.add(this.groundPlane)
  }

  setScene(scene) {
    for (const mark of scene.landmarks ?? []) this._landmark(mark)
  }

  _landmark({ id, pos, description }) {
    if (this.landmarks.has(id)) return

    const group = new THREE.Group()
    group.position.set(pos[0], pos[1], pos[2])

    const pin = new THREE.Mesh(
      new THREE.ConeGeometry(0.32, 1.1, 6),
      new THREE.MeshStandardMaterial({ color: 0x3a444e, roughness: 0.9 })
    )
    pin.position.y = 0.55
    group.add(pin)
    group.add(makeLabel(description || id, 0.8))

    this.scene.add(group)
    this.landmarks.set(id, group)
  }

  _being(id) {
    if (this.beings.has(id)) return this.beings.get(id)

    const group = new THREE.Group()

    const body = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.3, 1.0, 6, 12),
      new THREE.MeshStandardMaterial({ color: 0x9aa4ae, roughness: 0.55 })
    )
    body.position.y = 0.8
    group.add(body)

    // A wedge showing which way the being faces — without it, a capsule
    // gives no clue that turning is happening at all.
    const nose = new THREE.Mesh(
      new THREE.ConeGeometry(0.12, 0.34, 4),
      new THREE.MeshStandardMaterial({ color: 0xe6e9ec, roughness: 0.4 })
    )
    nose.rotation.x = Math.PI / 2
    nose.position.set(0, 1.15, 0.36)
    group.add(nose)

    const label = makeLabel(id, 1.85)
    group.add(label)

    const speech = makeLabel('', 2.25)
    speech.visible = false
    group.add(speech)

    this.scene.add(group)
    const entry = { group, body, nose, label, speech }
    this.beings.set(id, entry)
    return entry
  }

  // -- per-frame ---------------------------------------------------------

  /**
   * Draw the interpolated state between two frames.
   * `alpha` is 0 at `previous`, 1 at `current`.
   */
  draw(previous, current, alpha) {
    const before = new Map((previous?.entities ?? []).map((e) => [e.id, e]))
    const seen = new Set()

    for (const now of current.entities) {
      seen.add(now.id)
      const was = before.get(now.id) ?? now
      const { group, body, nose, speech } = this._being(now.id)

      // Position and facing are interpolated; everything else snaps.
      group.position.set(
        lerp(was.pos[0], now.pos[0], alpha),
        lerp(was.pos[1], now.pos[1], alpha),
        lerp(was.pos[2], now.pos[2], alpha)
      )

      const fx = lerp(was.facing[0], now.facing[0], alpha)
      const fz = lerp(was.facing[2], now.facing[2], alpha)
      if (fx !== 0 || fz !== 0) group.rotation.y = Math.atan2(fx, fz)

      // Colour carries emotion when there is any, action otherwise — so an
      // idle being reads as grey and a walking one reads as blue until it
      // feels something.
      const emotive = now.emotionWeight > 0.05
      const target = emotive
        ? EMOTION_COLOUR[now.emotion] ?? 0x9aa4ae
        : ACTION_COLOUR[now.action] ?? 0x5c6672
      body.material.color.setHex(target)

      // Gesture reads as a small hop, so it is visible without a rig.
      if (now.action === 'gesture') {
        body.position.y = 0.8 + Math.sin((now.motionPhase ?? 0) * Math.PI) * 0.18
        nose.material.color.setHex(0xffd8a8)
      } else {
        body.position.y = 0.8
        nose.material.color.setHex(0xe6e9ec)
      }

      if (now.speech) {
        setLabel(speech, now.speech.text)
        speech.visible = true
      } else {
        speech.visible = false
      }

      const isSelected = this.selected === now.id
      body.material.emissive.setHex(isSelected ? 0x224455 : 0x000000)
    }

    // Beings that left the world take their meshes with them.
    for (const [id, entry] of this.beings) {
      if (seen.has(id)) continue
      this.scene.remove(entry.group)
      this.beings.delete(id)
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

    const bodies = [...this.beings.values()].map((b) => b.body)
    const onBeing = this.raycaster.intersectObjects(bodies, false)[0]

    if (onBeing) {
      const id = [...this.beings.entries()].find(
        ([, v]) => v.body === onBeing.object
      )?.[0]
      this.selected = this.selected === id ? null : id
      return
    }

    if (!this.selected) return
    const onGround = this.raycaster.intersectObject(this.groundPlane, false)[0]
    if (onGround && this.onPick) {
      const p = onGround.point
      this.onPick(this.selected, [p.x, 0, p.z])
    }
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

function lerp(a, b, t) {
  return a + (b - a) * t
}

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
  ctx.fillStyle = 'rgba(14,17,20,0.72)'
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
  sprite.scale.set(canvas.width / 110, canvas.height / 110, 1)
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
