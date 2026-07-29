/**
 * The pose tuner.
 *
 * Gesture angles cannot be tuned by reasoning about a rig — they have to be
 * watched. Triggering one through the simulation and waiting out its 1.5
 * seconds is far too slow a loop to converge on anything, so this loads a
 * single avatar with no simulation attached and lets you scrub a gesture
 * frame by frame, edit its keyframes live, and copy the result back into
 * `anim/gestures.js`.
 *
 * A development tool, not part of the product. It imports the same pure
 * layer functions the renderer uses, so what you see here is exactly what a
 * being will do — there is no second implementation to drift.
 */

import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { applyExpressions, applyPose } from './anim/apply.js'
import { GESTURES } from './anim/gestures.js'
import { blinkWeight, idleLayer, sampleKeys, walkLayer } from './anim/layers.js'
import { blendLayers, arc, clamp01, scalePose } from './anim/pose.js'
import { loadBody } from './body.js'
import { fetchPacks } from './packs.js'

// A working copy, so edits do not mutate the imported module.
const gestures = structuredClone(GESTURES)

const ui = {
  avatar: document.getElementById('avatar'),
  gesture: document.getElementById('gesture'),
  phase: document.getElementById('phase'),
  phaseValue: document.getElementById('phase-value'),
  loop: document.getElementById('loop'),
  slow: document.getElementById('slow'),
  reset: document.getElementById('reset'),
  idle: document.getElementById('idle'),
  walk: document.getElementById('walk'),
  key: document.getElementById('key'),
  keyLabel: document.getElementById('key-label'),
  copy: document.getElementById('copy'),
  boneList: document.getElementById('bone-list'),
  addBone: document.getElementById('add-bone'),
  status: document.getElementById('status'),
}

const state = {
  gesture: 'wave',
  keyIndex: 1,
  phase: 0,
  looping: true,
  slow: false,
  idle: true,
  walk: false,
  body: null,
}

// -- scene -----------------------------------------------------------------

const scene = new THREE.Scene()
scene.background = new THREE.Color(0x0e1114)

const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100)
camera.position.set(0, 1.35, 2.6)

const renderer = new THREE.WebGLRenderer({ antialias: true })
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio))
document.body.appendChild(renderer.domElement)

const controls = new OrbitControls(camera, renderer.domElement)
controls.enableDamping = true
controls.target.set(0, 1.0, 0)

scene.add(new THREE.HemisphereLight(0x9fb8cc, 0x1a1f24, 1.6))
const key = new THREE.DirectionalLight(0xffffff, 2.2)
key.position.set(2, 4, 3)
scene.add(key)
const rim = new THREE.DirectionalLight(0x88aacc, 0.9)
rim.position.set(-3, 2, -3)
scene.add(rim)

const grid = new THREE.GridHelper(8, 16, 0x2a3036, 0x1c2126)
grid.material.transparent = true
grid.material.opacity = 0.35
scene.add(grid)

function resize() {
  camera.aspect = window.innerWidth / window.innerHeight
  camera.updateProjectionMatrix()
  renderer.setSize(window.innerWidth, window.innerHeight)
}
resize()
window.addEventListener('resize', resize)

// -- loading ---------------------------------------------------------------

let packs = new Map()

async function boot() {
  packs = await fetchPacks()

  ui.avatar.innerHTML = ''
  for (const pack of packs.values()) {
    const option = document.createElement('option')
    option.value = pack.id
    option.textContent = `${pack.name} (${pack.type})`
    ui.avatar.append(option)
  }

  ui.gesture.innerHTML = ''
  for (const name of Object.keys(gestures)) {
    const option = document.createElement('option')
    option.value = name
    option.textContent = name
    ui.gesture.append(option)
  }
  ui.gesture.value = state.gesture

  // Prefer a VRM: procedural poses only drive normalised humanoid bones, so
  // a plain glTF has nothing for them to move.
  const vrmPack = [...packs.values()].find((p) => p.type === 'vrm')
  ui.avatar.value = vrmPack?.id ?? ui.avatar.value
  await swapAvatar(ui.avatar.value)

  rebuildKeyList()
  rebuildBoneList()
}

async function swapAvatar(packId) {
  const pack = packs.get(packId)
  if (!pack) return

  ui.status.textContent = `loading ${pack.name}…`
  state.body?.dispose()
  state.body = null

  const buffer = await fetch(pack.model).then((r) => r.arrayBuffer())
  const body = await loadBody(pack, buffer, 'tuner')
  scene.add(body.group)
  state.body = body

  ui.status.textContent =
    pack.type === 'vrm'
      ? `${pack.name} — procedural poses active`
      : `${pack.name} — plain glTF, so procedural bone poses do nothing here`
}

// -- editing ---------------------------------------------------------------

function currentGesture() {
  return gestures[state.gesture]
}

function currentKey() {
  return currentGesture().keys[state.keyIndex]
}

function rebuildKeyList() {
  const keys = currentGesture().keys
  ui.key.innerHTML = ''
  keys.forEach((k, i) => {
    const option = document.createElement('option')
    option.value = String(i)
    const count = Object.keys(k.bones).length
    option.textContent = `${i}  ·  t=${k.t.toFixed(2)}  ·  ${count} bone${count === 1 ? '' : 's'}`
    ui.key.append(option)
  })
  state.keyIndex = Math.min(state.keyIndex, keys.length - 1)
  ui.key.value = String(state.keyIndex)
  ui.keyLabel.textContent = `${state.keyIndex} (t=${currentKey().t.toFixed(2)})`
}

function rebuildBoneList() {
  const bones = currentKey().bones
  ui.boneList.innerHTML = ''

  const names = Object.keys(bones)
  if (names.length === 0) {
    const empty = document.createElement('p')
    empty.className = 'note'
    empty.textContent =
      'This keyframe is empty. The first and last keyframe of every gesture ' +
      'should stay empty so it starts and ends at rest.'
    ui.boneList.append(empty)
    return
  }

  for (const bone of names) {
    ui.boneList.append(boneEditor(bone, bones[bone]))
  }
}

function boneEditor(bone, rotation) {
  const wrap = document.createElement('div')
  wrap.className = 'bone'

  const name = document.createElement('div')
  name.className = 'name'
  name.textContent = bone
  wrap.append(name)

  ;['x', 'y', 'z'].forEach((axis, i) => {
    const row = document.createElement('div')
    row.className = 'axis'

    const label = document.createElement('span')
    label.textContent = axis

    const slider = document.createElement('input')
    slider.type = 'range'
    slider.min = '-2.2'
    slider.max = '2.2'
    slider.step = '0.01'
    slider.value = String(rotation[i])

    const readout = document.createElement('span')
    readout.textContent = rotation[i].toFixed(2)

    slider.addEventListener('input', () => {
      rotation[i] = Number(slider.value)
      readout.textContent = rotation[i].toFixed(2)
    })

    row.append(label, slider, readout)
    wrap.append(row)
  })

  return wrap
}

// -- wiring ----------------------------------------------------------------

ui.avatar.addEventListener('change', () => swapAvatar(ui.avatar.value))

ui.gesture.addEventListener('change', () => {
  state.gesture = ui.gesture.value
  state.keyIndex = 1
  rebuildKeyList()
  rebuildBoneList()
})

ui.key.addEventListener('change', () => {
  state.keyIndex = Number(ui.key.value)
  ui.keyLabel.textContent = `${state.keyIndex} (t=${currentKey().t.toFixed(2)})`
  rebuildBoneList()
})

ui.phase.addEventListener('input', () => {
  state.looping = false
  ui.loop.classList.remove('on')
  state.phase = Number(ui.phase.value)
})

ui.loop.addEventListener('click', () => {
  state.looping = !state.looping
  ui.loop.classList.toggle('on', state.looping)
})

ui.slow.addEventListener('click', () => {
  state.slow = !state.slow
  ui.slow.classList.toggle('on', state.slow)
})

ui.idle.addEventListener('click', () => {
  state.idle = !state.idle
  ui.idle.classList.toggle('on', state.idle)
})

ui.walk.addEventListener('click', () => {
  state.walk = !state.walk
  ui.walk.classList.toggle('on', state.walk)
})

ui.reset.addEventListener('click', () => {
  gestures[state.gesture] = structuredClone(GESTURES[state.gesture])
  rebuildKeyList()
  rebuildBoneList()
})

ui.addBone.addEventListener('click', () => {
  const bone = prompt(
    'Bone name (VRM humanoid):\n\n' +
      'hips, spine, chest, upperChest, neck, head,\n' +
      'leftShoulder, leftUpperArm, leftLowerArm, leftHand,\n' +
      'rightShoulder, rightUpperArm, rightLowerArm, rightHand'
  )
  if (!bone) return
  currentKey().bones[bone] = [0, 0, 0]
  rebuildKeyList()
  rebuildBoneList()
})

ui.copy.addEventListener('click', async () => {
  const g = currentGesture()
  const body = g.keys
    .map((k) => {
      const bones = Object.entries(k.bones)
        .map(([b, r]) => `        ${b}: [${r.map((v) => round(v)).join(', ')}],`)
        .join('\n')
      return bones
        ? `    {\n      t: ${k.t},\n      bones: {\n${bones}\n      },\n    },`
        : `    { t: ${k.t}, bones: {} },`
    })
    .join('\n')

  const text = `export const ${state.gesture} = {\n  duration: ${g.duration},\n  keys: [\n${body}\n  ],\n}\n`

  try {
    await navigator.clipboard.writeText(text)
    ui.status.textContent = `copied ${state.gesture} — paste over it in anim/gestures.js`
  } catch {
    console.log(text)
    ui.status.textContent = 'clipboard blocked — the JSON is in the console'
  }
})

function round(v) {
  return Math.abs(v) < 0.005 ? 0 : Number(v.toFixed(2))
}

// -- loop ------------------------------------------------------------------

let last = performance.now()
let clock = 0

function frame() {
  requestAnimationFrame(frame)

  const now = performance.now()
  const dt = Math.min(0.1, (now - last) / 1000)
  last = now
  clock += dt

  if (state.looping) {
    const duration = currentGesture().duration * (state.slow ? 2 : 1)
    state.phase = (state.phase + dt / duration) % 1
    ui.phase.value = String(state.phase)
  }
  ui.phaseValue.textContent = state.phase.toFixed(2)

  const body = state.body
  if (body?.vrm) {
    // The same pure functions the renderer uses. No second implementation
    // to drift out of step with the real thing.
    const layers = []
    if (state.idle) layers.push({ pose: idleLayer(clock) })
    if (state.walk) layers.push({ pose: walkLayer(clock) })

    const sampled = sampleKeys(currentGesture().keys, clamp01(state.phase))
    const fade = Math.min(1, arc(state.phase) * 2.2)
    layers.push({ pose: scalePose(sampled, fade) })

    applyPose(body.vrm, blendLayers(layers))
    applyExpressions(body.vrm, { blink: blinkWeight(clock) })
    body.vrm.update(dt)
  }

  controls.update()
  renderer.render(scene, camera)
}

boot()
  .then(frame)
  .catch((error) => {
    console.error(error)
    ui.status.textContent = `failed to start: ${error.message}`
  })
