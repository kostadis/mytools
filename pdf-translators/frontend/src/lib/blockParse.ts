// Smart-paste parsers for the Add Block modal, ported verbatim from
// adventure_editor.py's parseTableText / parseStatblockText.

export interface ParsedTable {
  colLabels: string[]
  rows: string[][]
}

export function parseTableText(text: string): ParsedTable | null {
  // Try tab-separated first, then pipe-separated, then multi-space.
  const lines = text.trim().split('\n').filter((l) => l.trim())
  if (lines.length < 2) return null

  let separator: string | RegExp | null = null
  if (lines[0].includes('\t')) separator = '\t'
  else if (lines[0].includes('|')) separator = '|'
  else if (lines[0].match(/ {2,}/)) separator = / {2,}/

  if (!separator) {
    // Try key:value or key=value format (2-column)
    const kvLines = lines.filter((l) => l.match(/^[^:=]+[:=].+/))
    if (kvLines.length >= lines.length * 0.6) {
      const rows: string[][] = []
      for (const l of lines) {
        const m = l.match(/^([^:=]+)[:=]\s*(.*)/)
        if (m) rows.push([m[1].trim(), m[2].trim()])
        else rows.push([l.trim(), ''])
      }
      return { colLabels: ['Attribute', 'Value'], rows }
    }
    return null
  }

  const splitLine = (line: string): string[] => {
    if (separator instanceof RegExp) return line.split(separator).map((s) => s.trim())
    return line
      .split(separator as string)
      .map((s) => s.trim())
      .filter((s) => s !== '')
  }

  const headerCells = splitLine(lines[0])
  if (headerCells.length < 2) return null

  // Skip separator lines (e.g., "---|---" or "====")
  let startRow = 1
  if (lines[startRow] && lines[startRow].match(/^[\s|=\-:+]+$/)) startRow++

  const rows: string[][] = []
  for (let i = startRow; i < lines.length; i++) {
    const cells = splitLine(lines[i])
    while (cells.length < headerCells.length) cells.push('')
    rows.push(cells.slice(0, headerCells.length))
  }

  return { colLabels: headerCells, rows }
}

export interface ParsedTrait {
  name: string
  text: string
}

export interface ParsedStatblock {
  rows: string[][]
  traits: ParsedTrait[]
}

const KNOWN_STATBLOCK_KEYS = [
  'Type', 'Armor Class', 'Hit Points', 'Speed', 'STR', 'DEX', 'CON',
  'INT', 'WIS', 'CHA', 'Saving Throws', 'Skills', 'Damage Resistances',
  'Damage Immunities', 'Condition Immunities', 'Senses', 'Languages',
  'Challenge', 'Proficiency Bonus', 'Damage Vulnerabilities',
]

export function parseStatblockText(text: string): ParsedStatblock {
  const lines = text.trim().split('\n').filter((l) => l.trim())
  const rows: string[][] = []
  const traits: ParsedTrait[] = []

  let inTraits = false
  let currentTrait: ParsedTrait | null = null

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) continue

    let matched = false
    if (!inTraits) {
      for (const key of KNOWN_STATBLOCK_KEYS) {
        if (trimmed.startsWith(key)) {
          let value = trimmed.slice(key.length).replace(/^[\s.:]+/, '').trim()
          if (!value) {
            const m = trimmed.match(new RegExp(`^${key}\\s+(.+)`, 'i'))
            if (m) value = m[1]
          }
          rows.push([key, value])
          matched = true
          break
        }
      }
      // Ability score line: "12 (+1) 14 (+2) ..."
      if (!matched && trimmed.match(/^\d+\s*\([+-]\d+\)/)) {
        const scores = trimmed.match(/(\d+)\s*\([+-]?\d+\)/g)
        if (scores && scores.length >= 6) {
          const abilities = ['STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA']
          for (let i = 0; i < 6 && i < scores.length; i++) {
            rows.push([abilities[i], scores[i]])
          }
          matched = true
        }
      }
    }

    if (!matched) {
      inTraits = true
      const traitMatch = trimmed.match(/^([A-Z][^.]+)\.\s*(.*)/)
      if (traitMatch) {
        if (currentTrait) traits.push(currentTrait)
        currentTrait = { name: traitMatch[1].trim(), text: traitMatch[2] || '' }
      } else if (currentTrait) {
        currentTrait.text += (currentTrait.text ? ' ' : '') + trimmed
      } else {
        if (currentTrait) traits.push(currentTrait)
        currentTrait = { name: '', text: trimmed }
      }
    }
  }
  if (currentTrait) traits.push(currentTrait)

  return { rows, traits }
}
