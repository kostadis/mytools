// Pure rules for backend-guard: which commands launch a CampaignGenerator
// pipeline that picks a model backend, and which backend it would resolve to.
// Mirrors campaignlib/api/client.py `_effective_backend`: an explicit
// non-anthropic `--backend` wins; otherwise CG_BACKEND; otherwise anthropic.

// Console scripts in pyproject.toml whose module selects a backend.
export const MODEL_SCRIPTS = [
  'prep', 'transform', 'dnd_sheet', 'distill', 'campaign_state', 'planning',
  'party', 'npc_table', 'make_tracking', 'thread_registry', 'grounding_sections',
  'ensemble', 'ensemble_batch', 'ensemble_extract', 'extract_facts',
  'narrate_chapter', 'facts_to_state', 'synthesise_polish',
  'synthesise_world_state', 'polish', 'query', 'sd_consistency', 'sd_agent',
  'sd_plan', 'sd_narrate', 'summary_native', 'scene_extract', 'enhance_summary',
  'check_consistency', 'vtt_voice_compare', 'kanka_mcp', 'scabard_sync',
] as const

// A script counts only in command position: at the start, after a separator
// or `do`/`then`, past env assignments and wrappers, with or without a path.
const SCRIPT_RE = new RegExp(
  '(?:^|[;&|(\\n]\\s*|\\b(?:do|then)\\s+)' +
    '(?:[A-Za-z_]\\w*=\\S*\\s+)*' +
    '(?:(?:nohup|time|env|timeout\\s+\\S+|uv\\s+run)\\s+)*' +
    '(?:[A-Za-z_]\\w*=\\S*\\s+)*' +
    `(?:\\S*/)?(${MODEL_SCRIPTS.join('|')})(?:\\.py)?(?=$|[\\s;&|)])`,
)
const MODULE_RE =
  /\s-m\s+((?:session_doc|pipelines|entity_registry|provenance)\.[\w.]+)/
const FLAG_RE = /--backend(?:=|\s+)["']?([\w-]+)/
const ENV_RE = /(?:^|[\s;&|(])(?:export\s+)?CG_BACKEND=["']?([\w-]*)/
const ALLOW_RE = /(?:^|[\s;&|(])(?:export\s+)?CG_ALLOW_API=1\b/

export type Source = 'flag' | 'inline-env' | 'process-env' | 'default'

export type Verdict = {
  script: string
  backend: string
  source: Source
  isAllowed: boolean
}

// A heredoc body is data unless a shell reads it (`bash <<EOF`).
const HEREDOC_RE =
  /<<-?[ \t]*(['"]?)(\w+)\1([^\n]*)\n[\s\S]*?(?:\n[ \t]*\2[ \t]*(?=\n|$)|$)/g
const SHELL_FEED_RE = /\b(?:ba|z|da)?sh(?:\s+-\w+)*\s*$/
// A quoted string is data unless it is a shell's `-c` or `eval` argument.
const QUOTED_RE =
  /(\b(?:ba|z|da)?sh\s+(?:-\w+\s+)*-\w*c\s+|\beval\s+)?("(?:[^"\\]|\\.)*"|'[^']*')/g

function dropHeredocBodies(command: string): string {
  return command.replace(HEREDOC_RE, (whole, _q, _tag, rest, offset) => {
    const before = command.slice(command.lastIndexOf('\n', offset) + 1, offset)
    return SHELL_FEED_RE.test(before) ? whole : `<<${rest}\n`
  })
}

function dropQuotedText(command: string): string {
  // Unwrap a `-c`/`eval` argument so its first word reads as a command.
  return command.replace(QUOTED_RE, (_whole, exec, quoted) =>
    exec ? `${exec}; ${quoted.slice(1, -1)}` : '""',
  )
}

export function inspect(
  command: string,
  processBackend: string | undefined,
): Verdict | null {
  // Look for the script only where a shell would run it, so a file written
  // with a heredoc or printf can mention a pipeline by name.
  const code = dropHeredocBodies(command)
  const runnable = dropQuotedText(code)
  const script =
    runnable.match(SCRIPT_RE)?.[1] ?? runnable.match(MODULE_RE)?.[1]
  if (script === undefined) return null

  const flag = code.match(FLAG_RE)?.[1]
  const inline = code.match(ENV_RE)?.[1]
  const isAllowed = ALLOW_RE.test(code)

  if (flag !== undefined && flag !== 'anthropic') {
    return { script, backend: flag, source: 'flag', isAllowed }
  }
  if (inline !== undefined && inline !== '') {
    return { script, backend: inline, source: 'inline-env', isAllowed }
  }
  if (processBackend) {
    return { script, backend: processBackend, source: 'process-env', isAllowed }
  }

  return {
    script,
    backend: 'anthropic',
    source: flag === 'anthropic' ? 'flag' : 'default',
    isAllowed,
  }
}

export function denial(v: Verdict, preferred: string): string | null {
  if (v.backend !== 'anthropic' || v.isAllowed) return null

  const why =
    v.source === 'flag' ? 'it passes --backend anthropic' : 'no backend is set'

  return (
    `backend-guard: ${v.script} would run on the Anthropic API key (${why}). ` +
    `The preferred backend is "${preferred}": prefix the command with ` +
    `CG_BACKEND=${preferred} (harmless for a subcommand that calls no model) ` +
    `or pass --backend ${preferred}. Use the API key only if the user ` +
    `explicitly asked for it in this conversation; then add CG_ALLOW_API=1 to the command.`
  )
}
