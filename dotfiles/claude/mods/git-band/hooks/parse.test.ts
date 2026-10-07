import { expect, test } from 'claude-code/testing'

import { parsePr, parseStatus } from './parse'

test('branch with upstream, ahead/behind and dirty files', () => {
  const s = parseStatus('## feat/x...origin/feat/x [ahead 2, behind 1]\n M a.py\nA  b.py\n?? scratch/\n')
  expect(s).toEqual({ branch: 'feat/x', isDetached: false, hasUpstream: true, ahead: 2, behind: 1, changed: 2, untracked: 1 })
})

test('branch with no upstream', () => {
  const s = parseStatus('## feat/new\n')
  expect(s.branch).toBe('feat/new')
  expect(s.hasUpstream).toBe(false)
})

test('detached head', () => {
  expect(parseStatus('## HEAD (no branch)\n').isDetached).toBe(true)
})

test('fresh repo', () => {
  expect(parseStatus('## No commits yet on main\n').branch).toBe('main')
})

test('gh pr view json, and nothing', () => {
  expect(parsePr('{"number":340,"state":"OPEN","isDraft":false}')).toEqual({ number: 340, state: 'open', isDraft: false })
  expect(parsePr('no pull requests found')).toBe(null)
})
