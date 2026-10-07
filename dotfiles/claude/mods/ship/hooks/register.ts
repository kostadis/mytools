import type { EngineInterface, Register } from 'claude-code'

import { dirtyCount, overrideFor, parseArgs, shipPrompt } from './logic'

async function git($: EngineInterface, cwd: string, args: string[], timeoutMs = 60000) {
  return $.process.run(['git', ...args], { cwd, timeoutMs })
}

const lastLine = (s: string) => s.trim().split('\n').pop() ?? ''

// Switches to the default branch, fast-forwards it, and deletes the branch it
// left if git calls it merged. Never stashes, resets or forces.
async function sync($: EngineInterface, overrides: string): Promise<string> {
  const cwd = await $.session.cwd()
  const top = await git($, cwd, ['rev-parse', '--show-toplevel'])
  if (top.exitCode !== 0) return 'sync: not a git repository.'
  const repo = top.stdout.trim()

  const dirty = dirtyCount((await git($, repo, ['status', '--porcelain'])).stdout)
  if (dirty > 0) {
    return `sync: ${dirty} uncommitted change${dirty === 1 ? '' : 's'}; nothing done. /ship or commit them first.`
  }

  const head = await git($, repo, ['symbolic-ref', '--short', 'refs/remotes/origin/HEAD'])
  const target = overrideFor(overrides, repo)
    ?? (head.exitCode === 0 ? head.stdout.trim().replace(/^origin\//, '') : 'main')
  const current = (await git($, repo, ['rev-parse', '--abbrev-ref', 'HEAD'])).stdout.trim()
  const lines: string[] = []

  if (current !== target) {
    const switched = await git($, repo, ['switch', target])
    if (switched.exitCode !== 0) {
      await git($, repo, ['fetch', '--prune'])
      return `sync: could not switch to ${target} (${lastLine(switched.stderr)}). Fetched origin instead.`
    }
    lines.push(`switched ${current} → ${target}`)
  }

  const pulled = await git($, repo, ['pull', '--ff-only', '--prune'])
  if (pulled.exitCode !== 0) {
    lines.push(`pull failed: ${lastLine(pulled.stderr)}`)
    return `sync: ${lines.join('; ')}`
  }
  lines.push(lastLine(pulled.stdout) || 'pulled')

  if (current !== target && current !== 'HEAD') {
    const deleted = await git($, repo, ['branch', '-d', current])
    lines.push(deleted.exitCode === 0
      ? `deleted merged branch ${current}`
      : `kept ${current} (git does not see it merged; squash-merged? delete with git branch -D)`)
  }

  return `sync: ${lines.join('; ')}`
}

export const register: Register = (on, options) => {
  const overrides = String(options.branch_overrides ?? '')

  on('session.start', async ($, e, next) => {
    const started = await next(e)
    await $.command.register({
      name: 'ship',
      description: 'Commit, push and open a PR (add "merge" to merge it and pull)',
      argumentHint: '[merge] [note]',
    })
    await $.command.register({
      name: 'sync',
      description: 'Switch to the default branch and pull, without the model',
    })

    return started
  })

  on('command.run', { command: 'ship' }, async ($, e) => {
    const { isMerge, note } = parseArgs(e.args)
    void $.prompt.submit({ text: shipPrompt(isMerge, note) })

    return { text: `ship: ${isMerge ? 'commit → push → PR → merge → pull' : 'commit → push → PR'} queued` }
  })

  on('command.run', { command: 'sync' }, async $ => ({ text: await sync($, overrides) }))
}
