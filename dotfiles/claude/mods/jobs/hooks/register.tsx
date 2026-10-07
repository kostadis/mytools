import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Job } from '../types'
import { apply, duration, launched, mark, parseNotice, prune, rowLine } from './logic'

const PANE = 'jobs'
const jobs = atom({ plugin: 'jobs', key: 'jobs' } as const, [])
const now = atom({ plugin: 'jobs', key: 'now' } as const, 0)

function running(list: readonly Job[]): number {
  return list.filter(job => job.endedAt === null).length
}

function showCount($: EngineInterface, list: readonly Job[]): void {
  const n = running(list)
  $.ui.status(n === 0 ? undefined : `jobs ${n} running`)
}

function blockText(content: readonly unknown[]): string {
  return content
    .map(block => {
      const b = block as { type?: string; text?: unknown }
      return b.type === 'text' && typeof b.text === 'string' ? b.text : ''
    })
    .join('\n')
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    await $.command.register({
      name: 'jobs',
      description: 'Show background shells, subagents and monitors in a pane',
      argumentHint: '[clear]',
    })
    // Keeps the elapsed times moving while anything runs.
    $.clock.every(5000, () => {
      void (async () => {
        if (running(await read($, jobs)) > 0) {
          const at = await $.clock.now()
          await update($, now, () => at)
        }
      })()
    })

    return started
  })

  on('command.run', { command: 'jobs' }, async ($, e) => {
    if (e.args.trim() === 'clear') {
      await update($, jobs, list => list.filter(job => job.endedAt === null))
    }
    await $.ui.open({ id: PANE, title: 'Jobs' })

    return { text: 'Jobs pane opened.' }
  })

  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    if (ran.deny !== undefined || ran.isError === true) return ran

    const launch = launched(String(e.tool), e as unknown as Record<string, unknown>, ran.result)
    if (launch !== null) {
      const startedAt = await $.clock.now()
      const list = await update($, jobs, list =>
        prune([
          ...list.filter(job => job.id !== launch.id),
          { ...launch, startedAt, endedAt: null, status: 'running', last: null, events: 0 },
        ]),
      )
      showCount($, list)
      await $.ui.open({ id: PANE, title: 'Jobs' })
    }

    return ran
  }).catch(($, e, next) => next(e))

  on('session.append', async ($, e, next) => {
    if (e.message.role === 'user') {
      const notice = parseNotice(blockText(e.message.content))
      if (notice !== null && !notice.isArtifact) {
        const at = await $.clock.now()
        let ended: Job | null = null
        const list = await update($, jobs, list => {
          const applied = apply(list, notice, at)
          ended = applied.ended
          return applied.jobs
        })
        showCount($, list)
        const done = ended as Job | null
        if (done !== null) {
          $.ui.toast(`${mark(done.status)} ${done.label}: ${done.status} after ${duration(at - done.startedAt)}`, { timeoutMs: 10000 })
        }
      }
    }

    return next(e)
  })

  // A notification row is one dim line; ctrl+o still shows it whole.
  on('ui.render', { component: 'UserMessage', props: { origin: { kind: 'task-notification' } } }, async ($, e, next) => {
    if (e.props.isExpanded) return next(e)
    const notice = parseNotice(e.props.text)
    if (notice === null || notice.isArtifact) return next(e)

    const job = (await read($, jobs)).find(one => one.id === notice.id)
    const { Text } = $.ui.resolve(e)

    return <Text dimColor wrap="truncate">{`⚙ ${rowLine(notice, job)}`}</Text>
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const list = await read($, jobs)
    const at = Math.max(await read($, now), await $.clock.now())
    const live = list.filter(job => job.endedAt === null)
    const done = list.filter(job => job.endedAt !== null).reverse()
    const room = Math.max(3, (e.viewport?.rows ?? 24) - 3)

    const row = (job: Job) => (
      <Box flexDirection="column">
        <Text wrap="truncate" dimColor={job.endedAt !== null} color={job.status === 'running' ? 'suggestion' : job.status === 'completed' ? 'success' : job.status === 'expired' ? 'subtle' : 'error'}>
          {`${mark(job.status)} ${job.kind.padEnd(7)} ${duration((job.endedAt ?? at) - job.startedAt).padStart(7)}  ${job.label}`}
        </Text>
        {job.last !== null && job.endedAt === null && (
          <Text dimColor wrap="truncate">{`    ↳ ${job.last}${job.events > 1 ? ` (${job.events} events)` : ''}`}</Text>
        )}
      </Box>
    )

    return (
      <Box flexDirection="column">
        {list.length === 0 && <Text dimColor>No background work yet.</Text>}
        {live.length > 0 && <Text bold>{`Running (${live.length})`}</Text>}
        {live.slice(0, room).map(row)}
        {done.length > 0 && <Text bold>Finished</Text>}
        {done.slice(0, Math.max(0, room - live.length * 2)).map(row)}
      </Box>
    )
  })
}
