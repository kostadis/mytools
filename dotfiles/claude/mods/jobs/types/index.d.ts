export type JobKind = 'shell' | 'agent' | 'monitor' | 'task'

export type Job = {
  id: string
  kind: JobKind
  label: string
  startedAt: number
  endedAt: number | null
  // 'running', or how it ended: completed, failed, killed, expired, ...
  status: string
  last: string | null
  events: number
}

declare module 'claude-code' {
  interface PluginState {
    jobs: { jobs: Job[]; now: number }
  }
}
