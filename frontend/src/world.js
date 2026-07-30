/**
 * Building the scene from a world pack.
 *
 * The other half of `src/andropia/worlds/`. The same manifest that
 * `describe.setting` turns into the paragraph a being reads is turned here into
 * the ground it stands on, and neither side holds a number the other does not.
 *
 * That is the whole point. Before this file the scene was a set of constants a
 * few lines further down in `stage.js` and the description was a paragraph
 * someone had typed, so a world could be described as a lush meadow and drawn
 * as a dark void with no test noticing. Three beings once spent two minutes
 * discussing the falling water level of a pond that was a point on a flat
 * plane, and nothing they had been told contradicted them.
 *
 * A shape this file does not implement is an invisible landmark and no error at
 * all — a place beings can walk to and nobody can see. `world.test.js` reads
 * `worlds/example/world.json` and asserts every shape in it builds; the Python
 * suite asserts that pack uses every shape the schema accepts. The two together
 * are what closes the loop across the language boundary.
 */

import * as THREE from 'three'

/**
 * How a material behaves under light.
 *
 * Declared once here rather than per feature, because "water" should look the
 * same in every world that has any — and because a pack author naming a
 * material has said everything they need to. Values are three.js standard
 * material properties; the colour always comes from the feature.
 */
export const FINISH = {
  water: { roughness: 0.08, metalness: 0.1, opacity: 0.82 },
  ice: { roughness: 0.15, metalness: 0.05, opacity: 0.75 },
  metal: { roughness: 0.35, metalness: 0.9 },
  stone: { roughness: 0.85 },
  wood: { roughness: 0.75 },
  grass: { roughness: 1.0 },
  earth: { roughness: 1.0 },
  sand: { roughness: 0.95 },
}

const DEFAULT_FINISH = { roughness: 0.9, metalness: 0.0 }

/**
 * Geometry per shape, in world units.
 *
 * Every shape is described by the same two numbers — `radius` and `height` —
 * so a pack author has one mental model rather than four, and adding a shape
 * cannot change what an existing manifest means. Each returns geometry already
 * oriented and offset so that the feature's declared position is where it meets
 * the ground, which is also the point a being walks to.
 */
export const SHAPES = {
  /** Flat and lying on the ground: water, a paved circle, a patch of anything. */
  disc: (radius) => {
    const g = new THREE.CircleGeometry(radius, 48)
    g.rotateX(-Math.PI / 2)
    // Clear of the floor by less than it is possible to see, so the two planes
    // do not fight over the same depth values.
    g.translate(0, 0.01, 0)
    return g
  },

  /** Squared and solid: an altar, a slab, a crate. */
  block: (radius, height) => {
    const g = new THREE.BoxGeometry(radius * 2, height, radius * 2)
    g.translate(0, height / 2, 0)
    return g
  },

  /** Upright and thin: a post, a pillar, a trunk. */
  column: (radius, height) => {
    const g = new THREE.CylinderGeometry(radius, radius * 1.1, height, 16)
    g.translate(0, height / 2, 0)
    return g
  },

  /** A swelling in the ground: a bank, a rise, a stand of reeds. */
  mound: (radius, height) => {
    const g = new THREE.SphereGeometry(radius, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2)
    g.scale(1, height / radius, 1)
    return g
  },
}

/**
 * One feature as a mesh, or null if its shape is not implemented.
 *
 * Null rather than a thrown error: one shape nobody drew should cost that
 * landmark and not the world, the same trade the avatar loader makes. The
 * caller says so on the console, because a silently missing landmark is the
 * failure this whole format exists to remove.
 */
export function feature(f) {
  const make = SHAPES[f.shape]
  if (!make) return null

  const radius = f.radius ?? 1
  const height = f.height ?? 1
  const finish = FINISH[f.material] ?? DEFAULT_FINISH

  const mesh = new THREE.Mesh(
    make(radius, height),
    new THREE.MeshStandardMaterial({
      color: new THREE.Color(f.colour ?? '#3a444e'),
      roughness: finish.roughness ?? DEFAULT_FINISH.roughness,
      metalness: finish.metalness ?? DEFAULT_FINISH.metalness,
      transparent: finish.opacity !== undefined,
      opacity: finish.opacity ?? 1,
    })
  )

  mesh.position.set(f.pos[0], f.pos[1], f.pos[2])
  // A flat disc has nothing to cast, and self-shadowing acne on a puddle is the
  // one artefact that reads as a bug rather than as weather.
  mesh.castShadow = f.shape !== 'disc'
  mesh.receiveShadow = true
  mesh.name = `feature:${f.id}`

  return mesh
}

/** The floor, and the reference grid if the pack asked for one. */
export function ground(g = {}) {
  const extent = g.extent ?? 200
  const group = new THREE.Group()
  group.name = 'ground'

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(extent, extent),
    new THREE.MeshStandardMaterial({
      color: new THREE.Color(g.colour ?? '#151a1f'),
      roughness: 1.0,
    })
  )
  floor.rotation.x = -Math.PI / 2
  floor.receiveShadow = true
  floor.name = 'floor'
  group.add(floor)

  // Honest for an unbuilt space and wrong for a meadow, so the pack decides.
  if (g.grid ?? true) {
    const grid = new THREE.GridHelper(
      Math.min(extent, 120),
      Math.round(Math.min(extent, 120) / 2),
      0x2a3036,
      0x1c2126
    )
    grid.material.transparent = true
    grid.material.opacity = 0.4
    grid.position.y = 0.002
    grid.name = 'grid'
    group.add(grid)
  }

  return group
}

/**
 * The lights, sized to the ground so shadows cover the world rather than a
 * fixed box around the origin.
 */
export function lights(manifest = {}) {
  const light = manifest.light ?? {}
  const extent = manifest.ground?.extent ?? 200

  const sky = new THREE.HemisphereLight(
    new THREE.Color(light.sky_colour ?? '#9fb8cc'),
    new THREE.Color(light.ground_colour ?? '#1a1f24'),
    (light.ambient ?? 0.6) * 2
  )
  sky.name = 'ambient'

  const key = new THREE.DirectionalLight(0xffffff, light.key ?? 2.0)
  key.position.set(6, 12, 5)
  key.castShadow = true
  key.shadow.mapSize.set(2048, 2048)
  key.shadow.camera.near = 1
  key.shadow.camera.far = extent
  // Wide enough to hold the beings and whatever they are standing next to, and
  // no wider: a shadow camera stretched over a 200m floor spends its whole map
  // on empty grass and gives the bodies none.
  const reach = 24
  Object.assign(key.shadow.camera, {
    left: -reach,
    right: reach,
    top: reach,
    bottom: -reach,
  })
  key.shadow.bias = -0.0005
  key.name = 'key'

  return [sky, key]
}

/** Background colour and fog, which share a colour so the horizon closes. */
export function atmosphere(manifest = {}) {
  const sky = manifest.sky ?? {}
  const colour = new THREE.Color(sky.colour ?? '#0e1114')
  const fog = sky.fog?.length === 2 ? new THREE.Fog(colour.clone(), sky.fog[0], sky.fog[1]) : null
  return { background: colour, fog }
}

/**
 * Everything a manifest declares, as one group plus the scene-level settings
 * that are not objects.
 *
 * Returned rather than applied so this stays a function of its input: the
 * caller decides what to do with a scene, and a test can build a world without
 * one. `missing` names the shapes that went undrawn, because the alternative is
 * a landmark beings can reach and nobody can see.
 */
export function build(manifest = {}) {
  const group = new THREE.Group()
  group.name = `world:${manifest.id ?? 'unnamed'}`

  group.add(ground(manifest.ground))
  for (const light of lights(manifest)) group.add(light)

  const missing = []
  for (const f of manifest.features ?? []) {
    const mesh = feature(f)
    if (mesh) group.add(mesh)
    else missing.push(`${f.id} (${f.shape})`)
  }

  return { group, missing, ...atmosphere(manifest) }
}


// --------------------------------------------------------------------------
// the shell
// --------------------------------------------------------------------------

/**
 * Every world pack the server found, keyed by id.
 *
 * The only impure function here. Broken packs are reported rather than dropped,
 * the same as avatar packs: an author who typo'd a manifest should see why their
 * world is missing instead of a scene that is quietly the default one.
 */
export async function fetchWorlds() {
  const response = await fetch('/api/worlds')
  if (!response.ok) throw new Error(`/api/worlds returned ${response.status}`)

  const body = await response.json()

  for (const [directory, problem] of Object.entries(body.broken ?? {})) {
    console.warn(`[andropia] world pack "${directory}" is not usable:\n${problem}`)
  }

  return new Map(Object.entries(body.worlds ?? {}))
}
