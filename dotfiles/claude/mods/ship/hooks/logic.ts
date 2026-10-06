// Pure parts of ship: the prompt /ship hands the model, and /sync's plan.

export function parseArgs(args: string): { isMerge: boolean; note: string } {
  const words = args.trim().split(/\s+/).filter(w => w.length > 0)
  const isMerge = words[0]?.toLowerCase() === 'merge'

  return { isMerge, note: (isMerge ? words.slice(1) : words).join(' ') }
}

export function shipPrompt(isMerge: boolean, note: string): string {
  const steps = [
    'Run git status. If the current branch is the default branch, create a feature branch named for the change first: never commit to the default branch.',
    'Commit the work in logical commits with descriptive messages. Leave untracked scratch or experiment files out unless they clearly belong to this change; if that is unclear, ask before committing them.',
    'Push the branch, setting its upstream.',
    'Open a pull request with the GitHub MCP tools (mcp__github__create_pull_request), not the gh CLI. If this branch already has an open PR, reuse it and push to it.',
  ]
  if (isMerge) {
    steps.push(
      'Merge the PR with mcp__github__merge_pull_request. The user typed `/ship merge`: that is their explicit go-ahead to merge this PR, and only this one.',
      'Switch to the default branch (or the repo\'s working branch where CLAUDE.md names one) and pull; delete the merged local branch with `git branch -d`. In a worktree, leave the worktree in place and say so.',
    )
  } else {
    steps.push('Do not merge. Stop after the PR is open.')
  }

  return [
    '/ship: ship the current work in this repository, in order:',
    ...steps.map((step, i) => `${i + 1}. ${step}`),
    ...(note === '' ? [] : [`Note from the user: ${note}`]),
    'Finish with one short line per step: what happened, the PR URL, and anything you skipped and why.',
  ].join('\n')
}

export function overrideFor(spec: string, repoDir: string): string | undefined {
  const name = repoDir.replace(/\/+$/, '').split('/').pop() ?? ''
  for (const pair of spec.split(',')) {
    const [folder, branch] = pair.split('=').map(s => s.trim())
    if (folder && branch && folder === name) return branch
  }

  return undefined
}

export function dirtyCount(porcelain: string): number {
  return porcelain.split('\n').filter(line => line.length > 0 && !line.startsWith('??')).length
}
