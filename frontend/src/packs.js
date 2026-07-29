/**
 * Fetching avatar packs and instantiating bodies.
 *
 * Two beings may wear the same pack — a world with three robots is one pack
 * and three bodies. So the **bytes** are cached and shared, while each being
 * gets its own instance with its own scene graph, skeleton and animation
 * mixer. Sharing the instance instead would put two beings in one mesh at
 * one position, which looks exactly like one of them failing to spawn.
 *
 * Instantiating means parsing the file again per being. That is real work
 * for a 21 MB VRM, but it is correct for both containers — three-vrm has no
 * general clone, and a plain `Object3D.clone()` does not handle skinned
 * meshes. If instantiation ever becomes a bottleneck the fix is
 * `SkeletonUtils.clone` for plain glTF and keeping the parse for VRM.
 */

import { loadBody } from './body.js'

export async function fetchPacks() {
  const response = await fetch('/api/packs')
  if (!response.ok) throw new Error(`/api/packs returned ${response.status}`)

  const body = await response.json()
  const byId = new Map(body.packs.map((p) => [p.id, p]))

  // The server reports broken packs rather than filtering them out, so a
  // typo in a manifest is visible here instead of silently producing a
  // shorter list than the user expects.
  for (const [directory, problem] of Object.entries(body.broken ?? {})) {
    console.warn(`[andropia] avatar pack "${directory}" is not usable:\n${problem}`)
  }

  return byId
}

export function createBodyCache(packs) {
  // packId -> Promise<ArrayBuffer>. Fetched at most once even if several
  // beings ask simultaneously, because the promise is cached rather than
  // the result.
  const bytes = new Map()

  function fetchBytes(pack) {
    if (!bytes.has(pack.id)) {
      bytes.set(
        pack.id,
        fetch(pack.model).then((r) => {
          if (!r.ok) throw new Error(`${pack.model} returned ${r.status}`)
          return r.arrayBuffer()
        })
      )
    }
    return bytes.get(pack.id)
  }

  return {
    /**
     * A body for one being.
     *
     * @param packId  which pack to wear
     * @param beingId who is wearing it — seeds the animation phase, so two
     *                beings in identical bodies do not breathe and blink in
     *                lockstep, which is uncanny in a way that is hard to
     *                name and impossible to miss once seen.
     * @returns {Promise<Body|null>} null if unknown or unloadable
     */
    async create(packId, beingId) {
      if (!packId) return null

      const pack = packs.get(packId)
      if (!pack) {
        console.warn(`[andropia] no avatar pack named "${packId}"`)
        return null
      }

      try {
        const buffer = await fetchBytes(pack)
        return await loadBody(pack, buffer, beingId)
      } catch (error) {
        console.error(`[andropia] could not build a body from "${packId}":`, error)
        return null
      }
    },

    has(packId) {
      return packs.has(packId)
    },
  }
}
