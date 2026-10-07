export type GitInfo = {
  isRepo: boolean
  branch: string
  isDetached: boolean
  isWorktree: boolean
  changed: number
  untracked: number
  ahead: number
  behind: number
  hasUpstream: boolean
  defaultBranch: string
  isOnDefault: boolean
  // Commits origin/<default> has that the local <default> lacks.
  defaultBehind: number
  pr: { number: number; state: string; isDraft: boolean } | null
  fetchedAt: number
}

declare module 'claude-code' {
  interface PluginState {
    'git-band': { info: GitInfo | null }
  }
}
