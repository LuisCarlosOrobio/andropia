/**
 * Building a scene from a world pack.
 *
 * One test here matters more than the rest. `every shape in the example pack
 * builds` is half of a contract that spans two languages: the Python suite
 * asserts `worlds/example/world.json` uses every shape the schema accepts, and
 * this asserts every shape in that file draws something. Either half alone
 * passes while a shape goes undrawn — which is a place beings can walk to and
 * nobody can see, and no error at all.
 *
 * The manifests are read off disk rather than fixtured, so the files that ship
 * are the files under test.
 */

import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import * as THREE from 'three'

import { FINISH, SHAPES, atmosphere, build, feature, ground, lights } from './world.js'

const pack = (name) =>
  JSON.parse(readFileSync(new URL(`../../worlds/${name}/world.json`, import.meta.url), 'utf8'))

const EXAMPLE = pack('example')
const MEADOW = pack('meadow')

/** Size on each axis, which is the only way to tell "drawn" from "degenerate". */
function extentOf(object) {
  const box = new THREE.Box3().setFromObject(object)
  return box.getSize(new THREE.Vector3())
}

// -- the cross-language contract -------------------------------------------

describe('shapes', () => {
  it('draws every shape the example pack uses', () => {
    const { group, missing } = build(EXAMPLE)
    expect(missing).toEqual([])

    for (const f of EXAMPLE.features) {
      const mesh = group.getObjectByName(`feature:${f.id}`)
      expect(mesh, `${f.id} (${f.shape}) was not drawn`).toBeDefined()
    }
  })

  it('gives every shape a size on all three axes', () => {
    // A shape that builds and measures zero is exactly as invisible as one that
    // does not build, and only this catches it.
    for (const f of EXAMPLE.features) {
      const size = extentOf(feature(f))
      expect(size.x, f.id).toBeGreaterThan(0)
      expect(size.z, f.id).toBeGreaterThan(0)
      if (f.shape !== 'disc') expect(size.y, f.id).toBeGreaterThan(0)
    }
  })

  it('reports a shape it cannot draw instead of dropping it', () => {
    const { missing } = build({ features: [{ id: 'spire', shape: 'pyramid', pos: [0, 0, 0] }] })
    expect(missing).toEqual(['spire (pyramid)'])
  })

  it('sits every shape on the ground rather than through it', () => {
    // A block centred on its declared position is half buried, and the position
    // is also the point a being walks to.
    for (const name of Object.keys(SHAPES)) {
      const mesh = feature({ id: name, shape: name, pos: [0, 0, 0], radius: 2, height: 3 })
      const box = new THREE.Box3().setFromObject(mesh)
      expect(box.min.y, name).toBeGreaterThanOrEqual(-1e-6)
      expect(box.max.y, name).toBeGreaterThan(0)
    }
  })

  it('honours the declared radius and height', () => {
    const size = extentOf(feature({ id: 'x', shape: 'block', pos: [0, 0, 0], radius: 2, height: 5 }))
    expect(size.x).toBeCloseTo(4)
    expect(size.y).toBeCloseTo(5)
  })

  it('puts a feature where the manifest says', () => {
    const mesh = feature({ id: 'x', shape: 'column', pos: [3, 0, -7] })
    expect([mesh.position.x, mesh.position.y, mesh.position.z]).toEqual([3, 0, -7])
  })
})

// -- materials -------------------------------------------------------------

describe('materials', () => {
  it('makes water look wet', () => {
    // The same declaration that tells a being the pond is water. If this were a
    // second table keyed on something else, the two could disagree.
    const pond = feature(EXAMPLE.features.find((f) => f.material === 'water'))
    expect(pond.material.roughness).toBeLessThan(0.3)
    expect(pond.material.transparent).toBe(true)
  })

  it('makes grass look dry', () => {
    const bank = feature(EXAMPLE.features.find((f) => f.material === 'grass'))
    expect(bank.material.roughness).toBeGreaterThan(0.9)
    expect(bank.material.transparent).toBe(false)
  })

  it('takes the colour from the feature and never from the material', () => {
    for (const material of Object.keys(FINISH)) {
      const mesh = feature({ id: 'x', shape: 'block', pos: [0, 0, 0], material, colour: '#ff0000' })
      expect(mesh.material.color.getHexString(), material).toBe('ff0000')
    }
  })

  it('falls back to a plain finish for a material it has no opinion about', () => {
    const mesh = feature({ id: 'x', shape: 'block', pos: [0, 0, 0], material: 'cheese' })
    expect(mesh.material.roughness).toBeGreaterThan(0)
    expect(mesh.material.transparent).toBe(false)
  })
})

// -- the ground ------------------------------------------------------------

describe('ground', () => {
  it('takes its colour and size from the pack', () => {
    const group = ground({ colour: '#4a6b3a', extent: 80 })
    const floor = group.getObjectByName('floor')
    expect(floor.material.color.getHexString()).toBe('4a6b3a')
    expect(extentOf(floor).x).toBeCloseTo(80)
  })

  it('draws the grid only when the pack asks for one', () => {
    // Honest over an unbuilt space and wrong over a meadow, which is why it is
    // declared rather than assumed.
    expect(ground({ grid: true }).getObjectByName('grid')).toBeDefined()
    expect(ground({ grid: false }).getObjectByName('grid')).toBeUndefined()
    expect(ground({}).getObjectByName('grid')).toBeDefined()
  })

  it('is named so the picker can find it', () => {
    // Clicking the ground sends coordinates; a rename here silently breaks that.
    expect(build(MEADOW).group.getObjectByName('floor')).toBeDefined()
  })
})

// -- sky and light ---------------------------------------------------------

describe('atmosphere', () => {
  it('fogs to the same colour as the sky, so the horizon closes', () => {
    const { background, fog } = atmosphere(MEADOW)
    expect(fog.color.getHexString()).toBe(background.getHexString())
    expect([fog.near, fog.far]).toEqual(MEADOW.sky.fog)
  })

  it('has no fog when the pack declares none', () => {
    expect(atmosphere({ sky: { colour: '#000000' } }).fog).toBeNull()
  })

  it('reads the sky colour from the pack', () => {
    expect(atmosphere(MEADOW).background.getHexString()).toBe(MEADOW.sky.colour.slice(1))
  })
})

describe('lights', () => {
  it('gives a world a sun and a sky', () => {
    const [sky, key] = lights(MEADOW)
    expect(sky).toBeInstanceOf(THREE.HemisphereLight)
    expect(key).toBeInstanceOf(THREE.DirectionalLight)
    expect(key.intensity).toBeCloseTo(MEADOW.light.key)
  })

  it('scales ambient light with the pack', () => {
    const dim = lights({ light: { ambient: 0.1 } })[0]
    const bright = lights({ light: { ambient: 0.9 } })[0]
    expect(bright.intensity).toBeGreaterThan(dim.intensity)
  })

  it('casts shadows', () => {
    expect(lights(MEADOW)[1].castShadow).toBe(true)
  })
})

// -- the whole world -------------------------------------------------------

describe('build', () => {
  it('works from an empty manifest', () => {
    // The honest rendering of a world with no pack, and the ground the picker
    // needs in order to accept a click at all.
    const { group, missing } = build({})
    expect(missing).toEqual([])
    expect(group.getObjectByName('floor')).toBeDefined()
    expect(group.getObjectByName('grid')).toBeDefined()
  })

  it('works from no manifest at all', () => {
    expect(() => build()).not.toThrow()
  })

  it('builds the same world twice over', () => {
    // Called again whenever a viewer reconnects to a restarted server.
    const names = (m) => build(m).group.children.map((c) => c.name).sort()
    expect(names(MEADOW)).toEqual(names(MEADOW))
  })

  it('draws every feature the shipped packs declare', () => {
    for (const manifest of [EXAMPLE, MEADOW]) {
      const { group, missing } = build(manifest)
      expect(missing, manifest.id).toEqual([])
      expect(
        group.children.filter((c) => c.name.startsWith('feature:')).length,
        manifest.id
      ).toBe(manifest.features.length)
    }
  })
})
