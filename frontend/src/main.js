/**
 * Andropia viewer — capsule stage.
 *
 * Deliberately draws beings as capsules rather than rigged avatars. If
 * something is wrong in the simulation you want to see it as a box moving
 * oddly, not debug it through a rig, a shader and spring-bone physics.
 * Bodies arrive later; this proves the loop.
 *
 * The renderer is a *projection*. It owns no world state — it holds the last
 * two frames and interpolates between them for display. Everything it draws
 * is derived from what the server sent; nothing here can affect what happens
 * next in the simulation.
 */

import { connect } from './net.js'
import { createBodyCache, fetchPacks } from './packs.js'
import { Stage } from './stage.js'

const stage = new Stage(document.body)
const hud = {
  tick: document.getElementById('tick'),
  mode: document.getElementById('mode'),
  speed: document.getElementById('speed'),
  beings: document.getElementById('beings'),
  status: document.getElementById('status'),
  play: document.getElementById('btn-play'),
}

// --- world state as received -------------------------------------------
// Two frames, so display can interpolate. The simulation ticks at 20 Hz and
// the screen refreshes at 60; without this, motion visibly steps.
let previous = null
let current = null
let arrivedAt = 0
let dtSeconds = 0.05  // learned from the scene message on connect
let lastDrawAt = performance.now()

// Avatar packs, fetched once. Bodies load lazily per pack; until one
// arrives its being is a capsule, and if it fails it stays one.
let packs = new Map()
fetchPacks()
  .then((found) => {
    packs = found
    stage.setBodyCache(createBodyCache(found))
    console.info(`[andropia] ${found.size} avatar pack(s) available`)
  })
  .catch((error) => {
    console.error('[andropia] could not load avatar packs:', error)
    hud.status.textContent = 'no avatar packs — showing placeholders'
  })

const net = connect({
  onScene: (scene) => {
    dtSeconds = scene.dt ?? 0.05
    stage.setScene(scene)
  },
  onFrame: (frame) => {
    previous = current ?? frame
    current = frame
    arrivedAt = performance.now()
    hud.tick.textContent = frame.tick
    hud.beings.textContent = frame.entities.length
  },
  onStatus: (text, ok) => {
    hud.status.textContent = text
    hud.status.classList.toggle('bad', !ok)
  },
})

// --- controls -----------------------------------------------------------

let running = false
hud.play.addEventListener('click', () => {
  running = !running
  net.send({ type: running ? 'resume' : 'pause' })
  hud.play.textContent = running ? 'pause' : 'resume'
  hud.mode.textContent = running ? 'running' : 'paused'
})

document.getElementById('btn-step').addEventListener('click', () => {
  net.send({ type: 'step' })
})

for (const b of document.querySelectorAll('.spd')) {
  b.addEventListener('click', () => {
    const value = Number(b.dataset.v)
    net.send({ type: 'speed', value })
    hud.speed.textContent = `${value}×`
    for (const other of document.querySelectorAll('.spd')) {
      other.classList.toggle('on', other === b)
    }
  })
}

// Click a being, then a spot on the ground, to send it there.
//
// `moveto`, not `goto`: goto names a landmark, which is what an agent uses
// because a language model reasons about "the pond" rather than about
// coordinates. A human clicking the ground has a point and no name for it.
stage.onPick = (entityId, point) => {
  if (!entityId || !point) return
  net.send({
    type: 'intent',
    intent: { kind: 'moveto', entity: entityId, pos: point },
  })
}

// --- render loop --------------------------------------------------------

function tick() {
  requestAnimationFrame(tick)

  if (current) {
    // Where we are between the last two simulation ticks. Clamped, so a
    // late frame holds at the newest state rather than extrapolating into
    // positions the simulation never produced.
    const nowMs = performance.now()
    const dtMs = dtSeconds * 1000
    const alpha = Math.min(1, (nowMs - arrivedAt) / dtMs)

    // Real frame delta, for animation mixers and spring bones. Clamped so a
    // backgrounded tab does not resume with one enormous step.
    const frameDt = Math.min(0.1, (nowMs - lastDrawAt) / 1000)
    lastDrawAt = nowMs

    stage.draw(previous, current, alpha, packs, frameDt)
  }

  stage.render()
}

tick()
