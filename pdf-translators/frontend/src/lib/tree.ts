// Pure Markdown heading-tree logic, ported verbatim from the original
// single-file markdown_editor.py vanilla JS. No Vue/DOM dependencies — kept
// pure so it stays trivially testable and the store can call it directly.

export interface Block {
  id: number
  level: number // 0 = preamble (no heading), 1..6 = #..######
  text: string
  body: string
}

// ── Parse / serialize ──────────────────────────────────────────────────────

export function parseMarkdown(md: string): Block[] {
  const lines = md.split('\n')
  const result: Block[] = []
  let cur: Block | null = null
  let pre: string | null = null // preamble accumulator

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const m = line.match(/^(#{1,6})\s+(.*)/)
    if (m) {
      if (cur) result.push(cur)
      else if (pre !== null) {
        if (pre.trim()) result.push({ id: result.length, level: 0, text: '', body: pre })
        pre = null
      }
      cur = { id: result.length, level: m[1].length, text: m[2], body: '' }
    } else {
      if (cur) {
        cur.body += line + (i < lines.length - 1 ? '\n' : '')
      } else {
        if (pre === null) pre = ''
        pre += line + (i < lines.length - 1 ? '\n' : '')
      }
    }
  }
  if (cur) result.push(cur)
  else if (pre !== null && pre.trim())
    result.push({ id: result.length, level: 0, text: '', body: pre })

  result.forEach((b, i) => { b.id = i })
  return result
}

export function blocksToMarkdown(blks: Block[]): string {
  // Each block's `body` already carries its own trailing newline(s) (parse
  // appends '\n' after every non-final line), and the heading line always gets
  // exactly one '\n' before its body. So blocks concatenate directly with
  // join('') — joining with '\n' instead injects an extra blank line at every
  // heading boundary on *each* save, growing the file every time. join('')
  // makes parse↔serialize idempotent.
  return blks
    .map((b) => {
      if (b.level === 0) return b.body
      return '#'.repeat(b.level) + ' ' + b.text + '\n' + b.body
    })
    .join('')
}

// ── Tree helpers ───────────────────────────────────────────────────────────

export function hasChildren(blks: Block[], i: number): boolean {
  return i + 1 < blks.length && blks[i + 1].level > blks[i].level
}

// Exclusive end index of the section starting at i
export function sectionEnd(blks: Block[], i: number): number {
  const lvl = blks[i].level
  let j = i + 1
  while (j < blks.length && blks[j].level > lvl) j++
  return j
}

// Visible block indices given the current collapsed set
export function visibleIndices(blks: Block[], col: Set<number>): number[] {
  const vis: number[] = []
  const hideStack: number[] = []
  for (let i = 0; i < blks.length; i++) {
    const lvl = blks[i].level
    while (hideStack.length && lvl <= hideStack[hideStack.length - 1]) hideStack.pop()
    if (!hideStack.length) {
      vis.push(i)
      if (col.has(i) && hasChildren(blks, i)) hideStack.push(lvl)
    }
  }
  return vis
}

// Previous sibling index at same level (or -1)
export function prevSibling(blks: Block[], i: number): number {
  const lvl = blks[i].level
  let j = i - 1
  while (j >= 0 && blks[j].level > lvl) j--
  return j >= 0 && blks[j].level === lvl ? j : -1
}

// Next sibling index at same level (or -1)
export function nextSibling(blks: Block[], i: number): number {
  const end = sectionEnd(blks, i)
  return end < blks.length && blks[end].level === blks[i].level ? end : -1
}

// ── Mutations (return new arrays; never mutate input) ──────────────────────

export function moveSectionUp(blks: Block[], i: number): Block[] {
  const prev = prevSibling(blks, i)
  if (prev < 0) return blks
  const end = sectionEnd(blks, i)
  return [
    ...blks.slice(0, prev),
    ...blks.slice(i, end),
    ...blks.slice(prev, i),
    ...blks.slice(end),
  ]
}

export function moveSectionDown(blks: Block[], i: number): Block[] {
  const next = nextSibling(blks, i)
  if (next < 0) return blks
  const myEnd = next
  const nxtEnd = sectionEnd(blks, next)
  return [
    ...blks.slice(0, i),
    ...blks.slice(next, nxtEnd),
    ...blks.slice(i, myEnd),
    ...blks.slice(nxtEnd),
  ]
}

export function changeLevel(blks: Block[], i: number, delta: number): Block[] {
  const b = blks[i]
  const newLvl = Math.max(1, Math.min(6, b.level + delta))
  if (newLvl === b.level) return blks
  return blks.map((x, j) => (j === i ? { ...x, level: newLvl } : x))
}

export function deleteSection(blks: Block[], i: number): Block[] {
  const end = sectionEnd(blks, i)
  return [...blks.slice(0, i), ...blks.slice(end)]
}
