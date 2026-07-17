import { describe, expect, it } from 'vitest'
import { parseStatblockText, parseTableText } from './blockParse'

describe('parseTableText', () => {
  it('parses a tab-separated table', () => {
    const text = 'Roll\tResult\n1\tNothing\n2\tTreasure'
    const parsed = parseTableText(text)
    expect(parsed).toEqual({
      colLabels: ['Roll', 'Result'],
      rows: [
        ['1', 'Nothing'],
        ['2', 'Treasure'],
      ],
    })
  })

  it('parses a pipe-separated table, skipping a markdown separator row', () => {
    const text = 'Roll | Result\n---|---\n1 | Nothing\n2 | Treasure'
    const parsed = parseTableText(text)
    expect(parsed?.colLabels).toEqual(['Roll', 'Result'])
    expect(parsed?.rows).toEqual([
      ['1', 'Nothing'],
      ['2', 'Treasure'],
    ])
  })

  it('parses key:value pairs into a 2-column table', () => {
    const text = 'Armor Class: 14\nHit Points: 27\nSpeed: 30 ft.'
    const parsed = parseTableText(text)
    expect(parsed?.colLabels).toEqual(['Attribute', 'Value'])
    expect(parsed?.rows).toEqual([
      ['Armor Class', '14'],
      ['Hit Points', '27'],
      ['Speed', '30 ft.'],
    ])
  })

  it('pads short rows to the header width', () => {
    const text = 'A\tB\tC\n1\t2'
    const parsed = parseTableText(text)
    expect(parsed?.rows).toEqual([['1', '2', '']])
  })

  it('returns null for unparseable text', () => {
    expect(parseTableText('just one line')).toBeNull()
  })
})

describe('parseStatblockText', () => {
  it('extracts known key-value stat rows', () => {
    const text = 'Armor Class 14 (natural armor)\nHit Points 27\nSpeed 30 ft.'
    const parsed = parseStatblockText(text)
    expect(parsed.rows).toEqual([
      ['Armor Class', '14 (natural armor)'],
      ['Hit Points', '27'],
      ['Speed', '30 ft.'],
    ])
  })

  it('extracts an ability score line', () => {
    const text = '12 (+1) 14 (+2) 13 (+1) 10 (+0) 11 (+0) 9 (-1)'
    const parsed = parseStatblockText(text)
    expect(parsed.rows).toEqual([
      ['STR', '12 (+1)'],
      ['DEX', '14 (+2)'],
      ['CON', '13 (+1)'],
      ['INT', '10 (+0)'],
      ['WIS', '11 (+0)'],
      ['CHA', '9 (-1)'],
    ])
  })

  it('collects trailing lines as named traits', () => {
    const text = 'Armor Class 14\nMultiattack. The creature makes two attacks.\nBite. Melee Weapon Attack.'
    const parsed = parseStatblockText(text)
    expect(parsed.traits).toEqual([
      { name: 'Multiattack', text: 'The creature makes two attacks.' },
      { name: 'Bite', text: 'Melee Weapon Attack.' },
    ])
  })

  it('appends unlabelled continuation lines to the current trait', () => {
    const text = 'Multiattack. The creature makes two attacks:\none with its bite and one with its claw.'
    const parsed = parseStatblockText(text)
    expect(parsed.traits).toEqual([
      { name: 'Multiattack', text: 'The creature makes two attacks: one with its bite and one with its claw.' },
    ])
  })
})
