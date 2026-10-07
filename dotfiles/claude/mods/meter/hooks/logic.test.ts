import { expect, test } from 'claude-code/testing'

import { limitWarning, statusText } from './logic'

const now = Date.parse('2026-10-06T20:00:00Z')

test('status joins every window and the context fill', () => {
  expect(statusText([{ kind: 'five_hour', percentUsed: 62.4 }, { kind: 'seven_day', percentUsed: 31 }], 78)).toBe('5h 62% · 7d 31% · ctx 78%')
})

test('status is cleared when there is nothing to show', () => {
  expect(statusText([], undefined)).toBe(undefined)
})

test('a window warns once per period at its threshold', () => {
  const warned = new Set<string>()
  const w = { kind: 'five_hour', percentUsed: 86, resetsAt: '2026-10-06T21:20:00Z' }
  const first = limitWarning(w, warned, now)
  expect(first?.text).toContain('resets in 1h 20m')
  warned.add(first!.key)
  expect(limitWarning(w, warned, now)).toBe(null)
  expect(limitWarning({ ...w, resetsAt: '2026-10-07T02:00:00Z' }, warned, now)).not.toBe(null)
})

test('below the threshold, no warning', () => {
  expect(limitWarning({ kind: 'seven_day', percentUsed: 89 }, new Set(), now)).toBe(null)
})
