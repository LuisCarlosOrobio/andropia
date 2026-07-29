/**
 * Fetching avatar packs and their models.
 *
 * Loading is lazy and per-pack: a world referencing three bodies loads three
 * models, not every pack on disk. Failures are contained — a body that will
 * not load leaves its being as a capsule with a visible warning rather than
 * taking down the scene, because one broken avatar should not cost you the
 * whole world.
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

/**
 * A cache that loads each model at most once, even if several beings ask
 * for it simultaneously — the promise is cached, not just the result.
 */
export function createBodyCache(packs) {
  const pending = new Map()

  return {
    /** @returns {Promise<Body|null>} null if the pack is unknown or broken */
    async get(packId) {
      if (!packId) return null

      if (!pending.has(packId)) {
        const pack = packs.get(packId)
        if (!pack) {
          console.warn(`[andropia] no avatar pack named "${packId}"`)
          pending.set(packId, Promise.resolve(null))
        } else {
          pending.set(
            packId,
            loadBody(pack).catch((error) => {
              console.error(`[andropia] failed to load body "${packId}":`, error)
              return null
            })
          )
        }
      }

      return pending.get(packId)
    },

    has(packId) {
      return packs.has(packId)
    },
  }
}
