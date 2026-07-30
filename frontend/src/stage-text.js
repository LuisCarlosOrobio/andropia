/**
 * Text layout for nameplates. Pure, and separate from `stage.js` so it can be
 * tested without a WebGL context or a canvas.
 */

/**
 * Break text into lines of at most `limit` characters, on word boundaries.
 *
 * Wrapping rather than letting the sprite grow: an unwrapped utterance becomes
 * a single enormous quad spanning the scene, which is what made several beings
 * talking at once unreadable. A word longer than the limit is left alone —
 * breaking it mid-word would be worse than one over-long line.
 */
export function wrapText(text, limit) {
  const lines = []
  let line = ""

  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    if (!line) {
      line = word
    } else if (line.length + 1 + word.length <= limit) {
      line += " " + word
    } else {
      lines.push(line)
      line = word
    }
  }
  if (line) lines.push(line)
  return lines.length ? lines : [""]
}
