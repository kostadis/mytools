import { describe, expect, it } from 'vitest'
import { escapeHtml, joinLines } from './textUtils'

describe('joinLines', () => {
  it('joins a hyphenated line break', () => {
    const text = 'Five guards are alert here at all times. One fac-\ning the door'
    expect(joinLines(text)).toBe('Five guards are alert here at all times. One facing the door')
  })

  it('joins a hyphenated word split across lines', () => {
    expect(joinLines('sur-\ncoats')).toBe('surcoats')
  })

  it('joins a soft-wrapped line with a space', () => {
    const text = 'the guards alert\narea 130 (or 128, as appropriate).'
    expect(joinLines(text)).toBe('the guards alert area 130 (or 128, as appropriate).')
  })

  it('preserves paragraph breaks at blank lines', () => {
    expect(joinLines('First paragraph.\n\nSecond paragraph.')).toBe('First paragraph.\n\nSecond paragraph.')
  })

  it('joins a full PDF paste', () => {
    const text = [
      'Five guards are alert here at all times. One fac-',
      'ing the door, and another posted ten feet up',
      'the northeast corridor (position G on the',
      'map), are armed with heavy crossbows and',
      'longswords.',
    ].join('\n')
    const result = joinLines(text)
    expect(result).not.toContain('fac-')
    expect(result).toContain('facing the door')
    expect(result).not.toContain('\n')
    expect(result.startsWith('Five guards')).toBe(true)
    expect(result.endsWith('longswords.')).toBe(true)
  })

  it('joins hyphens across multiple paragraphs independently', () => {
    expect(joinLines('First para-\ngraph text.\n\nSecond para-\ngraph text.')).toBe(
      'First paragraph text.\n\nSecond paragraph text.',
    )
  })

  it('handles the empty string', () => {
    expect(joinLines('')).toBe('')
  })

  it('leaves a single line with no breaks untouched', () => {
    expect(joinLines('No breaks here.')).toBe('No breaks here.')
  })
})

describe('escapeHtml', () => {
  it('escapes &, <, > but not quotes', () => {
    expect(escapeHtml(`a & b < c > d "e" 'f'`)).toBe(`a &amp; b &lt; c &gt; d "e" 'f'`)
  })

  it('treats a falsy input as empty', () => {
    expect(escapeHtml('')).toBe('')
  })
})
