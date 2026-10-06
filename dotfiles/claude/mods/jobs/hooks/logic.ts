// Pure rules for jobs: what a tool result launched, what a notification says,
// and how the list changes.
import type { Job, JobKind } from '../types'

export const KEEP_FINISHED = 15

export type Launch = { id: string; kind: JobKind; label: string }

export function launched(tool: string, input: Record<string, unknown>, result: unknown): Launch | null {
  const r = (result ?? {}) as Record<string, unknown>
  const text = (v: unknown) => (typeof v === 'string' && v.length > 0 ? v : undefined)

  if (tool === 'Bash' && text(r.backgroundTaskId)) {
    const label = text(input.description) ?? String(input.command ?? '').slice(0, 60)
    return { id: String(r.backgroundTaskId), kind: 'shell', label }
  }
  if (tool === 'Agent' && r.status === 'async_launched' && text(r.agentId)) {
    return { id: String(r.agentId), kind: 'agent', label: text(r.description) ?? text(input.description) ?? 'subagent' }
  }
  if (tool === 'Monitor' && text(r.taskId)) {
    return { id: String(r.taskId), kind: 'monitor', label: text(input.description) ?? 'monitor' }
  }

  return null
}

export type Notice = {
  id: string
  status: string | null
  summary: string | null
  event: string | null
  isArtifact: boolean
}

const tag = (text: string, name: string) =>
  text.match(new RegExp(`<${name}>([\\s\\S]*?)</${name}>`))?.[1]?.trim() ?? null

export function parseNotice(text: string): Notice | null {
  if (!text.includes('<task-notification>')) return null
  const id = tag(text, 'task-id')
  const type = tag(text, 'task-type')
  if (id === null && type === null) return null

  return {
    id: id ?? `${type}`,
    status: tag(text, 'status'),
    summary: tag(text, 'summary'),
    event: tag(text, 'event'),
    isArtifact: type?.startsWith('artifact') === true,
  }
}

const firstLine = (s: string) => (s.split('\n').find(line => line.trim() !== '') ?? '').slice(0, 120)

export function labelFrom(summary: string | null): string {
  if (summary === null) return 'task'
  return summary.match(/"([^"]+)"/)?.[1] ?? summary.slice(0, 60)
}

// Applies one notice; `ended` is the job when this notice finished it.
export function apply(jobs: readonly Job[], n: Notice, now: number): { jobs: Job[]; ended: Job | null } {
  let list = [...jobs]
  let index = list.findIndex(job => job.id === n.id)
  if (index === -1) {
    list.push({
      id: n.id, kind: n.event !== null ? 'monitor' : 'task', label: labelFrom(n.summary),
      startedAt: now, endedAt: null, status: 'running', last: null, events: 0,
    })
    index = list.length - 1
  }

  const job = { ...list[index]! }
  let ended: Job | null = null

  if (n.event !== null) {
    const expired = /^\[Monitor expired/.test(n.event)
    if (expired) {
      job.status = 'expired'
      job.endedAt = now
      ended = job
    } else {
      job.events += 1
      job.last = firstLine(n.event)
    }
  }
  if (n.status !== null && job.endedAt === null) {
    job.status = n.status
    job.endedAt = now
    job.last = n.summary === null ? job.last : firstLine(n.summary)
    ended = job
  }

  list[index] = job
  list = prune(list)

  return { jobs: list, ended }
}

export function prune(jobs: readonly Job[]): Job[] {
  const running = jobs.filter(job => job.endedAt === null)
  const finished = jobs.filter(job => job.endedAt !== null).slice(-KEEP_FINISHED)

  return [...running, ...finished]
}

export function duration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s % 60}s`
  return `${s}s`
}

export function mark(status: string): string {
  if (status === 'running') return '●'
  if (status === 'completed') return '✓'
  if (status === 'expired') return '○'
  return '✗'
}

// One line for a compacted notification row.
export function rowLine(n: Notice, job: Job | undefined): string {
  const label = job?.label ?? labelFrom(n.summary)
  if (n.event !== null) return `${label}: ${firstLine(n.event)}`
  if (n.status !== null) return `${mark(n.status)} ${label}: ${n.status}`

  return `${label}: ${n.summary ?? ''}`
}
