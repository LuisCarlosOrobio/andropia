/**
 * The pure half of rendering.
 *
 * No three.js, no DOM, no WebGL context — which is the point. If a body
 * looks wrong, the question "is the maths wrong or is the scene wrong?" is
 * answerable, because half of it is a plain function over plain values.
 */

import { describe, expect, it } from 'vitest'
import {
  bodyState,
  expressionWeights,
  facingToYaw,
  gestureFor,
  lerp3,
  locomotionFor,
} from './pose.js'

const ROBOT = {
  id: 'robot',
  type: 'gltf',
  // Three morphs only: no happy, no relaxed. A deliberately partial rig.
  expressions: { angry: 'Angry', sad: 'Sad', surprised: 'Surprised' },
  clips: { wave: 'Wave', nod: 'Yes' },
  locomotion: { idle: 'Idle', walk: 'Walking' },
}

const VRM = {
  id: 'ava',
  type: 'vrm',
  expressions: {
    happy: 'happy',
    angry: 'angry',
    sad: 'sad',
    relaxed: 'relaxed',
    surprised: 'surprised',
  },
  clips: {},
  locomotion: {}, // every VRM ships zero clips
}

const being = (over = {}) => ({
  id: 'a',
  pos: [0, 0, 0],
  facing: [0, 0, 1],
  action: 'idle',
  emotion: 'neutral',
  emotionWeight: 0,
  ...over,
})

// --------------------------------------------------------------------------

describe('interpolation', () => {
  it('blends position between two frames', () => {
    expect(lerp3([0, 0, 0], [10, 0, 4], 0.5)).toEqual([5, 0, 2])
  })

  it('holds at the newest frame rather than extrapolating', () => {
    const was = being({ pos: [0, 0, 0] })
    const now = being({ pos: [4, 0, 0] })
    expect(bodyState(was, now, ROBOT, 1).position).toEqual([4, 0, 0])
  })

  it('turns a facing vector into a yaw', () => {
    expect(facingToYaw([0, 0, 1])).toBeCloseTo(0)
    expect(facingToYaw([1, 0, 0])).toBeCloseTo(Math.PI / 2)
  })

  it('returns null yaw for a degenerate facing', () => {
    // Interpolating through an exactly-opposed turn passes through zero.
    // Callers hold the previous heading rather than snapping to zero.
    expect(facingToYaw([0, 0, 0])).toBe(null)
  })
})

describe('expressions', () => {
  it('maps a canonical emotion through the pack', () => {
    const w = expressionWeights(being({ emotion: 'angry', emotionWeight: 0.8 }), ROBOT)
    expect(w).toEqual({ Angry: 0.8 })
  })

  it('yields nothing for an emotion this body cannot show', () => {
    // The robot has no happy morph. It should go neutral, not throw and not
    // guess at a substitute.
    const w = expressionWeights(being({ emotion: 'happy', emotionWeight: 1 }), ROBOT)
    expect(w).toEqual({})
  })

  it('yields nothing for neutral', () => {
    const w = expressionWeights(being({ emotion: 'neutral', emotionWeight: 1 }), ROBOT)
    expect(w).toEqual({})
  })

  it('yields nothing once the weight has decayed', () => {
    const w = expressionWeights(being({ emotion: 'sad', emotionWeight: 0 }), ROBOT)
    expect(w).toEqual({})
  })

  it('clamps a weight above one', () => {
    const w = expressionWeights(being({ emotion: 'sad', emotionWeight: 3 }), ROBOT)
    expect(w).toEqual({ Sad: 1 })
  })

  it('uses identity mapping for a conformant VRM', () => {
    const w = expressionWeights(being({ emotion: 'happy', emotionWeight: 0.5 }), VRM)
    expect(w).toEqual({ happy: 0.5 })
  })

  it('yields nothing when no pack has loaded yet', () => {
    expect(expressionWeights(being({ emotion: 'sad', emotionWeight: 1 }), null)).toEqual({})
  })
})

describe('locomotion', () => {
  it('selects the walk clip while walking', () => {
    const l = locomotionFor(being({ action: 'walk' }), ROBOT)
    expect(l).toEqual({ state: 'walk', clip: 'Walking', procedural: false })
  })

  it('selects the idle clip otherwise', () => {
    const l = locomotionFor(being({ action: 'idle' }), ROBOT)
    expect(l.clip).toBe('Idle')
  })

  it('falls back to procedural when the pack has no clips', () => {
    // True of essentially every VRM, so this is the common case rather
    // than the exception.
    const l = locomotionFor(being({ action: 'walk' }), VRM)
    expect(l).toEqual({ state: 'walk', clip: null, procedural: true })
  })

  it('treats a gesturing being as not walking', () => {
    const l = locomotionFor(being({ action: 'gesture' }), ROBOT)
    expect(l.state).toBe('idle')
  })
})

describe('gestures', () => {
  it('is null when no gesture is in progress', () => {
    expect(gestureFor(being({ action: 'idle' }), ROBOT)).toBe(null)
  })

  it('resolves a clip-backed gesture', () => {
    const g = gestureFor(
      being({ action: 'gesture', motion: 'wave', motionPhase: 0.4 }),
      ROBOT
    )
    expect(g).toEqual({ name: 'wave', phase: 0.4, clip: 'Wave', procedural: false })
  })

  it('marks a gesture with no clip as procedural', () => {
    // The robot has no shrug clip, so this falls to the pose library.
    const g = gestureFor(
      being({ action: 'gesture', motion: 'shrug', motionPhase: 0.2 }),
      ROBOT
    )
    expect(g.procedural).toBe(true)
    expect(g.clip).toBe(null)
  })

  it('marks every gesture procedural on a pack with no clips', () => {
    const g = gestureFor(
      being({ action: 'gesture', motion: 'wave', motionPhase: 0.5 }),
      VRM
    )
    expect(g.procedural).toBe(true)
  })

  it('uses the phase the server sent rather than timing anything itself', () => {
    // Durations live in the simulation. Changing one there must not
    // desynchronise the display.
    const g = gestureFor(
      being({ action: 'gesture', motion: 'wave', motionPhase: 0.9 }),
      ROBOT
    )
    expect(g.phase).toBe(0.9)
  })
})

describe('bodyState', () => {
  it('assembles a complete frame', () => {
    const was = being({ pos: [0, 0, 0] })
    const now = being({
      pos: [2, 0, 0],
      facing: [1, 0, 0],
      action: 'walk',
      emotion: 'sad',
      emotionWeight: 0.6,
      speech: { text: 'over here' },
    })

    const s = bodyState(was, now, ROBOT, 0.5)

    expect(s.position).toEqual([1, 0, 0])
    // Halfway through a quarter turn: facing blends [0,0,1] -> [1,0,0], so
    // the yaw is π/4 rather than the π/2 it reaches at alpha = 1. The being
    // is caught mid-turn, which is the whole point of interpolating.
    expect(s.yaw).toBeCloseTo(Math.PI / 4)
    expect(s.expressions).toEqual({ Sad: 0.6 })
    expect(s.locomotion.clip).toBe('Walking')
    expect(s.gesture).toBe(null)
    expect(s.speech).toBe('over here')
  })

  it('reaches the full turn at the end of the interval', () => {
    const was = being({ facing: [0, 0, 1] })
    const now = being({ facing: [1, 0, 0] })

    expect(bodyState(was, now, ROBOT, 0).yaw).toBeCloseTo(0)
    expect(bodyState(was, now, ROBOT, 1).yaw).toBeCloseTo(Math.PI / 2)
  })

  it('degrades to a positioned placeholder with no pack', () => {
    const b = being({ pos: [1, 0, 1], action: 'walk' })
    const s = bodyState(b, b, null, 1)

    expect(s.position).toEqual([1, 0, 1])
    expect(s.expressions).toEqual({})
    expect(s.locomotion.procedural).toBe(true)
  })
})
