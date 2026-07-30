/**
 * Nameplate layout.
 *
 * The wrap is the part worth testing without a browser: an unwrapped utterance
 * became a single enormous quad spanning the scene, which is what made several
 * beings talking at once unreadable.
 */
import { describe, expect, it } from 'vitest'
import { wrapText } from './stage-text.js'

describe('speech wrapping', () => {
  it('breaks on word boundaries within the limit', () => {
    const lines = wrapText('the moss only grows on the side facing the tree', 20)
    expect(lines.every((l) => l.length <= 20)).toBe(true)
    expect(lines.join(' ')).toBe('the moss only grows on the side facing the tree')
  })

  it('never breaks a word', () => {
    // One over-long line is better than a word split down the middle.
    expect(wrapText('extraordinarily', 5)).toEqual(['extraordinarily'])
  })

  it('collapses runs of whitespace', () => {
    // Models emit doubled spaces and stray newlines; a plate should not show
    // them as gaps.
    expect(wrapText('a  b\n\nc', 40)).toEqual(['a b c'])
  })

  it('gives one line for empty text rather than none', () => {
    // A zero-line plate would have zero height, and the plate above it would
    // land on the name.
    expect(wrapText('', 40)).toEqual([''])
  })

  it('keeps every word', () => {
    const words = 'one two three four five six seven eight nine ten'.split(' ')
    expect(wrapText(words.join(' '), 11).join(' ').split(' ')).toEqual(words)
  })
})
