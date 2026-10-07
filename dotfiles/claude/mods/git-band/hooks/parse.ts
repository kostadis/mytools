// Pure parsing of `git status --porcelain=v1 -b` and `gh pr view --json`.

export type StatusSummary = {
  branch: string
  isDetached: boolean
  hasUpstream: boolean
  ahead: number
  behind: number
  changed: number
  untracked: number
}

export function parseStatus(out: string): StatusSummary {
  const lines = out.split('\n').filter(line => line.length > 0)
  const head = (lines[0] ?? '').replace(/^## /, '')
  const summary: StatusSummary = {
    branch: '?', isDetached: false, hasUpstream: false,
    ahead: 0, behind: 0, changed: 0, untracked: 0,
  }

  if (head.startsWith('HEAD (no branch)')) {
    summary.branch = 'HEAD'
    summary.isDetached = true
  } else if (head.startsWith('No commits yet on ')) {
    summary.branch = head.slice('No commits yet on '.length)
  } else {
    const [names = '', counts = ''] = head.split(' [')
    const [branch = '?', upstream] = names.split('...')
    summary.branch = branch
    summary.hasUpstream = upstream !== undefined
    summary.ahead = Number(counts.match(/ahead (\d+)/)?.[1] ?? 0)
    summary.behind = Number(counts.match(/behind (\d+)/)?.[1] ?? 0)
  }

  for (const line of lines.slice(1)) {
    if (line.startsWith('??')) summary.untracked += 1
    else summary.changed += 1
  }

  return summary
}

export function parsePr(out: string): { number: number; state: string; isDraft: boolean } | null {
  try {
    const pr = JSON.parse(out)
    if (typeof pr?.number !== 'number') return null

    return { number: pr.number, state: String(pr.state ?? '').toLowerCase(), isDraft: pr.isDraft === true }
  } catch {
    return null
  }
}

// The band's pieces, in order, each with a theme colour; pure, so testable
// without drawing.
export type Part = { text: string; color?: string; isDim?: boolean; isBold?: boolean }

export type BandInfo = {
  branch: string
  isDetached: boolean
  isWorktree: boolean
  changed: number
  untracked: number
  ahead: number
  behind: number
  hasUpstream: boolean
  defaultBranch: string
  defaultBehind: number
  pr: { number: number; state: string; isDraft: boolean } | null
}

export function bandParts(s: BandInfo): Part[] {
  const parts: Part[] = [{ text: `⎇ ${s.branch}`, color: 'suggestion', isBold: true }]
  if (s.isWorktree) parts.push({ text: 'worktree', color: 'ide' })
  if (s.changed > 0) parts.push({ text: `${s.changed} changed`, color: 'warning' })
  if (s.untracked > 0) parts.push({ text: `${s.untracked} untracked`, isDim: true })
  if (s.changed === 0 && s.untracked === 0) parts.push({ text: 'clean', color: 'success' })
  if (!s.isDetached && !s.hasUpstream) parts.push({ text: 'not pushed', color: 'warning' })
  if (s.ahead > 0) parts.push({ text: `↑${s.ahead}`, color: 'success' })
  if (s.behind > 0) parts.push({ text: `↓${s.behind}`, color: 'error' })
  if (s.pr !== null) {
    parts.push({
      text: `PR #${s.pr.number} ${s.pr.isDraft ? 'draft' : s.pr.state}`,
      color: s.pr.state === 'merged' ? 'success' : 'merged',
    })
  }
  if (s.defaultBehind > 0) {
    parts.push({ text: `${s.defaultBranch} ↓${s.defaultBehind} vs origin`, color: 'error' })
  }

  return parts
}
