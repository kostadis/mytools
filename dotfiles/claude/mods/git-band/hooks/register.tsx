import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { GitInfo } from '../types'
import { bandParts, parsePr, parseStatus } from './parse'

const info = atom({ plugin: 'git-band', key: 'info' } as const, null)

const FETCH_EVERY_MS = 5 * 60 * 1000
const GIT_TOUCH = /(^|[\s;&|(])(git|gh)\s/

async function git($: EngineInterface, cwd: string, args: string[], timeoutMs = 10000) {
  return $.process.run(['git', ...args], { cwd, timeoutMs })
}

async function readPr($: EngineInterface, cwd: string): Promise<GitInfo['pr']> {
  try {
    const { exitCode, stdout } = await $.process.run(
      ['gh', 'pr', 'view', '--json', 'number,state,isDraft'],
      { cwd, timeoutMs: 8000 },
    )

    return exitCode === 0 ? parsePr(stdout) : null
  } catch {
    return null
  }
}

// Reads the repo state at the session's cwd. `isFetching` also runs a quiet
// `git fetch` first and re-asks GitHub for the branch's PR.
async function refresh($: EngineInterface, isFetching: boolean): Promise<void> {
  const cwd = await $.session.cwd()
  const dirs = await git($, cwd, ['rev-parse', '--git-dir', '--git-common-dir'])
  if (dirs.exitCode !== 0) {
    await update($, info, () => null)
    return
  }

  if (isFetching) {
    await git($, cwd, ['fetch', '--quiet', '--prune'], 30000).catch(() => undefined)
  }

  const [gitDir, commonDir] = dirs.stdout.trim().split('\n')
  const status = parseStatus((await git($, cwd, ['status', '--porcelain=v1', '-b'])).stdout)
  const originHead = await git($, cwd, ['symbolic-ref', '--short', 'refs/remotes/origin/HEAD'])
  const defaultBranch = originHead.exitCode === 0
    ? originHead.stdout.trim().replace(/^origin\//, '')
    : 'main'
  const isOnDefault = status.branch === defaultBranch

  const stale = await git($, cwd, ['rev-list', '--count', `${defaultBranch}..origin/${defaultBranch}`])
  const defaultBehind = stale.exitCode === 0 ? Number(stale.stdout.trim()) || 0 : 0

  const previous = await read($, info)
  const isSameBranch = previous?.isRepo === true && previous.branch === status.branch
  const pr = isOnDefault || status.isDetached
    ? null
    : isFetching || !isSameBranch
      ? await readPr($, cwd)
      : previous.pr

  const next: GitInfo = {
    isRepo: true,
    branch: status.branch,
    isDetached: status.isDetached,
    isWorktree: gitDir !== commonDir,
    changed: status.changed,
    untracked: status.untracked,
    ahead: status.ahead,
    behind: status.behind,
    hasUpstream: status.hasUpstream,
    defaultBranch,
    isOnDefault,
    defaultBehind,
    pr,
    fetchedAt: isFetching ? await $.clock.now() : previous?.fetchedAt ?? 0,
  }
  await update($, info, () => next)
}

// Hooks only mark what is wanted; a timer started at session.start does the
// work, so no git call runs on a dispatch that has already returned.
let isBusy = false
let wantsRefresh = false
let wantsFetch = false

async function tick($: EngineInterface): Promise<void> {
  if (isBusy || (!wantsRefresh && !wantsFetch)) return
  isBusy = true
  const isFetching = wantsFetch
  wantsRefresh = false
  wantsFetch = false
  try {
    await refresh($, isFetching)
  } catch (error) {
    $.ui.log(`git-band: ${String(error)}`, { to: 'debug' })
  } finally {
    isBusy = false
  }
}

const READ_ONLY_GITHUB = /^mcp__github__(get|list|search|issue_read|pull_request_read)/

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    wantsFetch = true
    $.clock.every(1000, () => void tick($))
    $.clock.every(FETCH_EVERY_MS, () => {
      wantsFetch = true
    })

    return started
  })

  on('turn.complete', ($, e, next) => {
    wantsRefresh = true

    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    const tool = String(e.tool)

    if (tool.startsWith('mcp__github__') && !READ_ONLY_GITHUB.test(tool)) {
      wantsFetch = true
    } else if (tool === 'EnterWorktree' || tool === 'ExitWorktree') {
      wantsRefresh = true
    } else if (e.tool === 'Bash' && GIT_TOUCH.test(e.command)) {
      if (/\b(push|pull|fetch|merge)\b/.test(e.command)) wantsFetch = true
      else wantsRefresh = true
    }

    return ran
  }).catch(($, e, next) => next(e))

  // /sync (the ship mod) runs git outside any tool call.
  on('command.run', { command: 'sync' }, async ($, e, next) => {
    const ran = await next(e)
    wantsFetch = true

    return ran
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const state = await read($, info)
    if (e.props.hasSurvey || state === null || !state.isRepo) return next(e)

    const { Box, Text } = $.ui.resolve(e)
    const items = bandParts(state).flatMap((part, i) => [
      ...(i > 0 ? [<Text dimColor> · </Text>] : []),
      <Text color={part.color} dimColor={part.isDim} bold={part.isBold}>{part.text}</Text>,
    ])
    const line = <Box flexDirection="row">{items}</Box>
    const below = await next(e)

    return below ? <Box flexDirection="column">{line}{below}</Box> : line
  })
}
