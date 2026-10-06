import { expect, test } from 'claude-code/testing'

import { apply, duration, launched, parseNotice, rowLine } from './logic'

const SHELL_DONE = '<task-notification>\n<task-id>bxb1262nu</task-id>\n<tool-use-id>toolu_01K</tool-use-id>\n<output-file>/tmp/x.output</output-file>\n<status>completed</status>\n<summary>Background command "Run build chain in order" completed (exit code 0)</summary>\n</task-notification>'
const MONITOR_EVENT = '<task-notification>\n<task-id>btjyypaoq</task-id>\n<summary>Monitor event: "Phase 1 run progress"</summary>\n<event>e1_prose/nox: 766 rows, 0 errors, 138s\ne1_rawB/nox: 766 rows</event>\nIf this event is something the user would act on now, send a PushNotification.\n</task-notification>'
const MONITOR_EXPIRED = '<task-notification>\n<task-id>btjyypaoq</task-id>\n<summary>Monitor event: "Phase 1 run progress"</summary>\n<event>[Monitor expired after 30m with 3 events delivered. Re-arm it if you still need the watch.]</event>\n</task-notification>'
const ARTIFACT = '<task-notification> <task-type>artifact-auto-react</task-type> <summary>10 artifact auto-reply subscriptions paused</summary></task-notification>'

test('a background Bash, async Agent and Monitor are launches', () => {
  expect(launched('Bash', { command: 'make', description: 'Run build chain in order' }, { backgroundTaskId: 'bxb1262nu', stdout: '' }))
    .toEqual({ id: 'bxb1262nu', kind: 'shell', label: 'Run build chain in order' })
  expect(launched('Agent', { description: 'Review ch52' }, { status: 'async_launched', agentId: 'a1', description: 'Review ch52' })?.kind).toBe('agent')
  expect(launched('Monitor', { description: 'Phase 1 run progress' }, { taskId: 'btjyypaoq', timeoutMs: 1 })?.kind).toBe('monitor')
  expect(launched('Bash', { command: 'ls' }, { stdout: 'x' })).toBe(null)
  expect(launched('Agent', {}, { status: 'completed', agentId: 'a2' })).toBe(null)
})

test('a shell completion ends its job', () => {
  const start = [{ id: 'bxb1262nu', kind: 'shell' as const, label: 'Run build chain in order', startedAt: 0, endedAt: null, status: 'running', last: null, events: 0 }]
  const { jobs, ended } = apply(start, parseNotice(SHELL_DONE)!, 125000)
  expect(ended?.status).toBe('completed')
  expect(jobs[0]?.endedAt).toBe(125000)
  expect(duration(125000)).toBe('2m 5s')
})

test('monitor events update the last line, expiry ends it', () => {
  const first = apply([], parseNotice(MONITOR_EVENT)!, 1000)
  expect(first.ended).toBe(null)
  expect(first.jobs[0]).toMatchObject({ id: 'btjyypaoq', kind: 'monitor', label: 'Phase 1 run progress', last: 'e1_prose/nox: 766 rows, 0 errors, 138s', events: 1 })
  const second = apply(first.jobs, parseNotice(MONITOR_EXPIRED)!, 2000)
  expect(second.ended?.status).toBe('expired')
})

test('artifact lifecycle notices are recognised and left alone', () => {
  expect(parseNotice(ARTIFACT)?.isArtifact).toBe(true)
  expect(parseNotice('plain prompt')).toBe(null)
})

test('a compacted row reads in one line', () => {
  expect(rowLine(parseNotice(MONITOR_EVENT)!, undefined)).toBe('Phase 1 run progress: e1_prose/nox: 766 rows, 0 errors, 138s')
  expect(rowLine(parseNotice(SHELL_DONE)!, undefined)).toBe('✓ Run build chain in order: completed')
})
