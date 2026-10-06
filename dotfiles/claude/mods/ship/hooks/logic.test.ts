import { expect, test } from 'claude-code/testing'

import { dirtyCount, overrideFor, parseArgs, shipPrompt } from './logic'

test('merge is the first word only', () => {
  expect(parseArgs('merge also the docs')).toEqual({ isMerge: true, note: 'also the docs' })
  expect(parseArgs('')).toEqual({ isMerge: false, note: '' })
  expect(parseArgs('docs only, merge later')).toEqual({ isMerge: false, note: 'docs only, merge later' })
})

test('without merge the prompt forbids merging', () => {
  const text = shipPrompt(false, '')
  expect(text).toContain('Do not merge')
  expect(text).not.toContain('merge_pull_request')
  expect(text).toContain('mcp__github__create_pull_request')
})

test('with merge the prompt names the go-ahead and the pull', () => {
  const text = shipPrompt(true, 'skip scratch/')
  expect(text).toContain('explicit go-ahead')
  expect(text).toContain('Note from the user: skip scratch/')
})

test('branch overrides match the repo folder', () => {
  expect(overrideFor('Mempalace=kostadis-dev', '/home/k/src/Mempalace')).toBe('kostadis-dev')
  expect(overrideFor('Mempalace=kostadis-dev', '/home/k/src/CampaignGenerator')).toBe(undefined)
})

test('untracked files do not block a sync', () => {
  expect(dirtyCount('?? scratch/\n M a.py\n')).toBe(1)
  expect(dirtyCount('?? x\n')).toBe(0)
})
