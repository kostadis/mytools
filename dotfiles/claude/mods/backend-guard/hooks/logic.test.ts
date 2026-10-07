import { expect, test } from 'claude-code/testing'

import { denial, inspect } from './logic'

test('a pipeline with no backend resolves to the API key and is denied', () => {
  const v = inspect('enhance_summary --session-dir summaries/ch52', undefined)
  expect(v?.backend).toBe('anthropic')
  expect(denial(v!, 'claude-code')).toContain('CG_BACKEND=claude-code')
})

test('an inline CG_BACKEND passes', () => {
  const v = inspect('CG_BACKEND=claude-code sd_narrate --vtt x.vtt', undefined)
  expect(v?.backend).toBe('claude-code')
  expect(denial(v!, 'claude-code')).toBe(null)
})

test('an explicit non-anthropic --backend wins', () => {
  const v = inspect('/home/k/.venv/bin/scene_extract --backend dgx', undefined)
  expect(v?.source).toBe('flag')
  expect(denial(v!, 'claude-code')).toBe(null)
})

test('--backend anthropic defers to CG_BACKEND, as the CLI does', () => {
  const v = inspect('sd_plan --backend anthropic', 'claude-code')
  expect(v?.backend).toBe('claude-code')
})

test('--backend anthropic with no env is denied', () => {
  const v = inspect('sd_plan --backend=anthropic', undefined)
  expect(denial(v!, 'dgx')).toContain('--backend dgx')
})

test('CG_ALLOW_API=1 lets the API key through', () => {
  const v = inspect('CG_ALLOW_API=1 enhance_summary', undefined)
  expect(denial(v!, 'claude-code')).toBe(null)
})

test('the process environment counts', () => {
  expect(inspect('summary_native synth world_state', 'dgx')?.backend).toBe('dgx')
})

test('python -m on a pipeline module is caught', () => {
  expect(inspect('python -m session_doc.sd_narrate --x', undefined)?.script).toBe(
    'session_doc.sd_narrate',
  )
})

test('non-pipeline commands and look-alikes are ignored', () => {
  expect(inspect('git status', undefined)).toBe(null)
  expect(inspect('grep -rn partyline docs/', undefined)).toBe(null)
  expect(inspect('cat docs/party.md', undefined)).toBe(null)
  expect(inspect('ls planning_notes/', undefined)).toBe(null)
  expect(inspect('grep -rn query docs', undefined)).toBe(null)
  expect(inspect('ls docs/query', undefined)).toBe(null)
})

test('wrappers, loops and chained commands are caught', () => {
  expect(inspect('cd ~/oota && timeout 600 enhance_summary x', undefined)?.script).toBe('enhance_summary')
  expect(inspect('for c in 1 2; do sd_narrate --ch $c; done', undefined)?.script).toBe('sd_narrate')
  expect(inspect('FOO=1 nohup scene_extract', undefined)?.script).toBe('scene_extract')
})
