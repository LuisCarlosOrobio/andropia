/**
 * The procedural animation stack.
 *
 * Every function under test is pure, so none of this needs a browser, a
 * WebGL context or a model file. That is the payoff of keeping the mutation
 * in one place: when a body looks wrong, "is the maths wrong or is the scene
 * wrong?" is an answerable question.
 */

import { describe, expect, it } from 'vitest'
import { GESTURES, GESTURE_NAMES } from './gestures.js'
import {
  blinkWeight,
  gestureLayer,
  idleLayer,
  layersFor,
  sampleKeys,
  visemeWeights,
  STRIDE_LENGTH,
  WALK_RATE,
  walkLayer,
} from './layers.js'
import { REST, addPose, blendLayers, easeBack, lerpPose, scalePose } from './pose.js'

const state = (over = {}) => ({
  locomotion: { state: 'idle', clip: null, procedural: true },
  gesture: null,
  speech: null,
  ...over,
})

// --------------------------------------------------------------------------

describe('the rest pose', () => {
  it('brings the arms down out of the T-pose', () => {
    // A VRM's normalised rest orientation is a T-pose, so without this a
    // body with no animation stands like a scarecrow. This layer is what
    // makes an avatar read as a person at all.
    expect(REST.leftUpperArm[2]).toBeLessThan(-1)
    expect(REST.rightUpperArm[2]).toBeGreaterThan(1)
  })

  it('is mirrored left to right', () => {
    // Left arm points +X, right points −X, so bringing both down takes
    // opposite signs. Equal magnitudes mean the body is symmetric.
    expect(REST.leftUpperArm[2]).toBeCloseTo(-REST.rightUpperArm[2])
    expect(REST.leftShoulder[2]).toBeCloseTo(-REST.rightShoulder[2])
  })
})

describe('pose arithmetic', () => {
  it('adds rotations bone by bone', () => {
    const out = addPose({ head: [1, 0, 0] }, { head: [0, 2, 0], hips: [0, 0, 3] })
    expect(out.head).toEqual([1, 2, 0])
    expect(out.hips).toEqual([0, 0, 3])
  })

  it('scales a contribution by weight', () => {
    const out = addPose({}, { head: [1, 1, 1] }, 0.5)
    expect(out.head).toEqual([0.5, 0.5, 0.5])
  })

  it('leaves the base untouched at zero weight', () => {
    const base = { head: [1, 1, 1] }
    expect(addPose(base, { head: [9, 9, 9] }, 0)).toBe(base)
  })

  it('does not mutate its inputs', () => {
    const base = { head: [1, 0, 0] }
    addPose(base, { head: [5, 0, 0] })
    expect(base.head).toEqual([1, 0, 0])
  })

  it('treats bones absent from one side as zero when interpolating', () => {
    expect(lerpPose({}, { head: [2, 0, 0] }, 0.5).head).toEqual([1, 0, 0])
  })

  it('scales a whole pose toward identity', () => {
    expect(scalePose({ head: [2, 4, 6] }, 0.5).head).toEqual([1, 2, 3])
  })

  it('blends a stack in order', () => {
    const out = blendLayers([
      { pose: { head: [1, 0, 0] } },
      { pose: { head: [0, 1, 0] }, weight: 2 },
    ])
    expect(out.head).toEqual([1, 2, 0])
  })

  it('skips empty and zero-weight layers', () => {
    const out = blendLayers([
      { pose: null },
      { pose: { head: [9, 9, 9] }, weight: 0 },
      { pose: { head: [1, 0, 0] } },
    ])
    expect(out.head).toEqual([1, 0, 0])
  })
})

describe('easing', () => {
  it('overshoots and settles', () => {
    // Real limbs do not stop dead at their destination. The overshoot is
    // most of the difference between "animated" and "moved".
    expect(easeBack(0.8)).toBeGreaterThan(1)
    expect(easeBack(1)).toBeCloseTo(1)
    expect(easeBack(0)).toBeCloseTo(0)
  })
})

describe('idle', () => {
  it('starts from rest and stays near it', () => {
    const pose = idleLayer(0)
    expect(pose.leftUpperArm[2]).toBeCloseTo(REST.leftUpperArm[2], 1)
  })

  it('never holds perfectly still', () => {
    // A frozen body reads as a bug, not a character.
    const a = idleLayer(0)
    const b = idleLayer(1.4)
    expect(a.chest[0]).not.toBeCloseTo(b.chest[0], 5)
  })

  it('keeps breathing small enough to read as breathing', () => {
    for (let t = 0; t < 12; t += 0.1) {
      expect(Math.abs(idleLayer(t).chest[0])).toBeLessThan(0.05)
    }
  })

  it('desynchronises bodies by phase', () => {
    // Two beings breathing in unison is uncanny in a way that is hard to
    // name and impossible to miss.
    const a = idleLayer(3, { phase: 0 })
    const b = idleLayer(3, { phase: 2.1 })
    expect(a.chest[0]).not.toBeCloseTo(b.chest[0], 3)
  })

  it('is a pure function of time', () => {
    expect(idleLayer(5.5, { phase: 1 })).toEqual(idleLayer(5.5, { phase: 1 }))
  })
})

describe('walk', () => {
  it('counter-swings the arms', () => {
    // Opposite arm signs are most of what makes a walk read as a walk
    // rather than a slide.
    const pose = walkLayer(0.3)
    expect(Math.sign(pose.leftUpperArm[0])).toBe(-Math.sign(pose.rightUpperArm[0]))
  })

  it('stays restrained', () => {
    // Procedural locomotion looks wrong if pushed; people are exquisitely
    // sensitive to how walking looks.
    for (let t = 0; t < 6; t += 0.05) {
      expect(Math.abs(walkLayer(t).hips[1])).toBeLessThan(0.15)
    }
  })

  it('cycles', () => {
    // Derived from the exported rate, so the two cannot drift apart.
    const a = walkLayer(0)
    const b = walkLayer((2 * Math.PI) / WALK_RATE)
    expect(a.leftUpperArm[0]).toBeCloseTo(b.leftUpperArm[0], 5)
  })
})

describe('gestures', () => {
  it('defines every canonical gesture', () => {
    expect(new Set(GESTURE_NAMES)).toEqual(
      new Set(['wave', 'nod', 'shake', 'shrug', 'think', 'point', 'cheer', 'idle_variant'])
    )
  })

  it('starts and ends at rest so nothing snaps', () => {
    for (const [name, gesture] of Object.entries(GESTURES)) {
      expect(gesture.keys[0].bones, name).toEqual({})
      expect(gesture.keys.at(-1).bones, name).toEqual({})
    }
  })

  it('keeps keyframes ordered and within [0, 1]', () => {
    for (const [name, gesture] of Object.entries(GESTURES)) {
      const times = gesture.keys.map((k) => k.t)
      expect(times, name).toEqual([...times].sort((a, b) => a - b))
      expect(Math.min(...times), name).toBe(0)
      expect(Math.max(...times), name).toBe(1)
    }
  })

  it('samples between keyframes', () => {
    const keys = [
      { t: 0, bones: {} },
      { t: 1, bones: { head: [1, 0, 0] } },
    ]
    expect(sampleKeys(keys, 0.5).head[0]).toBeGreaterThan(0)
    expect(sampleKeys(keys, 0.5).head[0]).toBeLessThan(1)
  })

  it('clamps outside the keyframe range', () => {
    const keys = [
      { t: 0, bones: { head: [1, 0, 0] } },
      { t: 1, bones: { head: [2, 0, 0] } },
    ]
    expect(sampleKeys(keys, -5).head).toEqual([1, 0, 0])
    expect(sampleKeys(keys, 5).head).toEqual([2, 0, 0])
  })

  it('fades in and out rather than snapping', () => {
    const start = gestureLayer('wave', 0)
    const middle = gestureLayer('wave', 0.4)
    const end = gestureLayer('wave', 1)

    const reach = (p) => Math.abs(p.rightUpperArm?.[2] ?? 0)
    expect(reach(start)).toBeLessThan(0.05)
    expect(reach(middle)).toBeGreaterThan(0.5)
    expect(reach(end)).toBeLessThan(0.05)
  })

  it('returns null for an unknown gesture rather than throwing', () => {
    // A model may emit a tag from a stale prompt or a finetune with its own
    // ideas. That must degrade, not break.
    expect(gestureLayer('backflip', 0.5)).toBe(null)
  })

  it('drives from the phase the simulation sent', () => {
    // Durations live in the simulation; changing one there must not
    // desynchronise the display.
    expect(gestureLayer('nod', 0.3)).not.toEqual(gestureLayer('nod', 0.7))
  })
})

describe('blink', () => {
  it('is shut only briefly', () => {
    let closed = 0
    const samples = 2000
    for (let i = 0; i < samples; i++) {
      if (blinkWeight(i * 0.01) > 0.5) closed++
    }
    const fraction = closed / samples
    expect(fraction).toBeGreaterThan(0)
    expect(fraction).toBeLessThan(0.08)
  })

  it('stays within range', () => {
    for (let t = 0; t < 40; t += 0.017) {
      const w = blinkWeight(t, { phase: 1.3 })
      expect(w).toBeGreaterThanOrEqual(0)
      expect(w).toBeLessThanOrEqual(1)
    }
  })

  it('is reproducible', () => {
    // A replay must blink on exactly the frames the original did.
    expect(blinkWeight(12.34, { phase: 2 })).toBe(blinkWeight(12.34, { phase: 2 }))
  })

  it('desynchronises by phase', () => {
    const a = Array.from({ length: 400 }, (_, i) => blinkWeight(i * 0.05, { phase: 0 }))
    const b = Array.from({ length: 400 }, (_, i) => blinkWeight(i * 0.05, { phase: 3.1 }))
    expect(a).not.toEqual(b)
  })
})

describe('visemes', () => {
  it('is silent when not speaking', () => {
    expect(visemeWeights(1.2, false)).toEqual({})
  })

  it('moves the mouth while speaking', () => {
    const a = visemeWeights(1.0, true)
    const b = visemeWeights(1.3, true)
    expect(a.aa).not.toBeCloseTo(b.aa, 3)
  })

  it('stays within range', () => {
    for (let t = 0; t < 10; t += 0.03) {
      const w = visemeWeights(t, true, { phase: 0.7 })
      expect(w.aa).toBeGreaterThanOrEqual(0)
      expect(w.aa).toBeLessThanOrEqual(1)
    }
  })
})

describe('composition', () => {
  it('always includes idle', () => {
    expect(layersFor(state(), 0)).toHaveLength(1)
  })

  it('adds a walk layer only when the pack has no walk clip', () => {
    const procedural = layersFor(
      state({ locomotion: { state: 'walk', clip: null, procedural: true } }),
      0
    )
    const clipBacked = layersFor(
      state({ locomotion: { state: 'walk', clip: 'Walking', procedural: false } }),
      0
    )

    expect(procedural).toHaveLength(2)
    expect(clipBacked).toHaveLength(1)
  })

  it('adds a gesture layer only when the gesture has no clip', () => {
    const procedural = layersFor(
      state({ gesture: { name: 'wave', phase: 0.5, clip: null, procedural: true } }),
      0
    )
    const clipBacked = layersFor(
      state({ gesture: { name: 'wave', phase: 0.5, clip: 'Wave', procedural: false } }),
      0
    )

    expect(procedural).toHaveLength(2)
    expect(clipBacked).toHaveLength(1)
  })

  it('ignores an unknown procedural gesture', () => {
    const layers = layersFor(
      state({ gesture: { name: 'backflip', phase: 0.5, clip: null, procedural: true } }),
      0
    )
    expect(layers).toHaveLength(1)
  })

  it('blends to a finite pose', () => {
    const layers = layersFor(
      state({
        locomotion: { state: 'walk', clip: null, procedural: true },
        gesture: { name: 'wave', phase: 0.5, clip: null, procedural: true },
      }),
      3.2
    )
    const pose = blendLayers(layers)

    for (const [bone, rotation] of Object.entries(pose)) {
      for (const value of rotation) {
        expect(Number.isFinite(value), bone).toBe(true)
        expect(Math.abs(value), bone).toBeLessThan(Math.PI)
      }
    }
  })
})

describe('walk regressions', () => {
  it('emits arm deltas, never absolute rest rotations', () => {
    // Layers ADD. The first version repeated REST here, so while walking the
    // arms had rest applied twice and swung far past the body — reported as
    // "her arms move but weirdly".
    const pose = walkLayer(0.4)
    expect(Math.abs(pose.leftUpperArm[2])).toBeLessThan(0.3)
    expect(Math.abs(pose.rightUpperArm[2])).toBeLessThan(0.3)
  })

  it('stays near rest once blended with idle', () => {
    for (let t = 0; t < 4; t += 0.05) {
      const pose = blendLayers([{ pose: idleLayer(t) }, { pose: walkLayer(t) }])
      // Comfortably short of straight out to the side, which is where the
      // doubled rotation used to put it.
      expect(Math.abs(pose.leftUpperArm[2])).toBeGreaterThan(0.9)
      expect(Math.abs(pose.leftUpperArm[2])).toBeLessThan(1.7)
    }
  })

  it('actually moves the legs', () => {
    // Reported as "she just slides through the ground". Legs were excluded
    // from TRACKED_BONES on purpose; gliding looks worse than an imperfect
    // walk, so they are driven now.
    const a = walkLayer(0)
    const b = walkLayer(0.3)
    expect(a.leftUpperLeg[0]).not.toBeCloseTo(b.leftUpperLeg[0], 3)
    expect(a.rightUpperLeg[0]).not.toBeCloseTo(b.rightUpperLeg[0], 3)
  })

  it('swings the legs in opposition', () => {
    for (const t of [0.1, 0.4, 0.9, 1.6]) {
      const pose = walkLayer(t)
      expect(Math.sign(pose.leftUpperLeg[0])).toBe(-Math.sign(pose.rightUpperLeg[0]))
    }
  })

  it('never inverts a knee', () => {
    // The single most obviously-wrong thing a procedural leg can do.
    for (let t = 0; t < 6; t += 0.02) {
      const pose = walkLayer(t)
      expect(pose.leftLowerLeg[0]).toBeGreaterThanOrEqual(0)
      expect(pose.rightLowerLeg[0]).toBeGreaterThanOrEqual(0)
    }
  })

  it('counter-swings arms against legs', () => {
    // Left arm forward with right leg forward is what reads as walking.
    const pose = walkLayer(0.35)
    expect(Math.sign(pose.leftUpperArm[0])).toBe(-Math.sign(pose.leftUpperLeg[0]))
  })

  it('bobs at twice the stride rate', () => {
    // The body rises on each foot, not once per full cycle.
    const period = (2 * Math.PI) / WALK_RATE
    expect(walkLayer(0).hips[2]).toBeCloseTo(walkLayer(period).hips[2], 5)
    expect(walkLayer(0).hips[2]).toBeCloseTo(walkLayer(period / 2).hips[2], 5)
  })
})

describe('foot planting', () => {
  it('advances the cycle with distance, not time', () => {
    // The fix for skating: a being that has not moved has not stepped,
    // however long it has been standing there.
    const a = walkLayer(0, { distance: 0 })
    const b = walkLayer(99, { distance: 0 })
    expect(a).toEqual(b)
  })

  it('completes one cycle per stride length', () => {
    const a = walkLayer(0, { distance: 0 })
    const b = walkLayer(0, { distance: STRIDE_LENGTH })
    expect(a.leftUpperLeg[0]).toBeCloseTo(b.leftUpperLeg[0], 5)
  })

  it('steps at the same ground positions whatever the speed', () => {
    // Slow and fast beings covering the same ground must be at the same
    // point in their gait. This is what stops the feet sliding.
    for (const d of [0.3, 0.75, 1.1, 2.4]) {
      const slow = walkLayer(d / 0.4, { distance: d }) // 0.4 m/s
      const fast = walkLayer(d / 3.0, { distance: d }) // 3.0 m/s
      expect(slow.leftUpperLeg[0]).toBeCloseTo(fast.leftUpperLeg[0], 9)
      expect(slow.rightLowerLeg[0]).toBeCloseTo(fast.rightLowerLeg[0], 9)
    }
  })

  it('falls back to time when distance is unknown', () => {
    // Keeps the layer callable from the tuner, which has no world.
    const a = walkLayer(0)
    const b = walkLayer(0.3)
    expect(a.leftUpperLeg[0]).not.toBeCloseTo(b.leftUpperLeg[0], 3)
  })
})
