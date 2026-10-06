import { expect, test } from 'claude-code/testing'

import { bandParts } from './parse'

const INFO = {
  branch: 'feat/ch52-spell', isDetached: false, isWorktree: true,
  changed: 3, untracked: 5, ahead: 2, behind: 0, hasUpstream: true,
  defaultBranch: 'main', defaultBehind: 4,
  pr: { number: 340, state: 'open', isDraft: false },
}

test('band names everything worth acting on', () => {
  expect(bandParts(INFO).map(p => p.text)).toEqual([
    '⎇ feat/ch52-spell', 'worktree', '3 changed', '5 untracked', '↑2', 'PR #340 open', 'main ↓4 vs origin',
  ])
})

test('a clean, unpushed branch says so', () => {
  const texts = bandParts({ ...INFO, isWorktree: false, changed: 0, untracked: 0, ahead: 0, hasUpstream: false, pr: null, defaultBehind: 0 }).map(p => p.text)
  expect(texts).toEqual(['⎇ feat/ch52-spell', 'clean', 'not pushed'])
})

test('no band outside a repo', async ($, on) => {
  on('ui.render', () => h('Box', {}) as never)
  const ui = await $.ui.mount({ plugin: 'git-band', surface: 'terminal', component: 'AbovePrompt', props: { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 120, scroll: { offset: 0, bodyRows: 10 } } } as never)
  expect(JSON.stringify(await ui.drawn())).not.toContain('⎇')
})
