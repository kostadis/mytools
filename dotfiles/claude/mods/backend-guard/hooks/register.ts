import type { EngineInterface, Register } from 'claude-code'

import { denial, inspect } from './logic'

async function guard(
  $: EngineInterface,
  command: string,
  preferred: string,
): Promise<string | null> {
  const verdict = inspect(command, await $.env.get('CG_BACKEND'))
  if (verdict === null) return null

  const reason = denial(verdict, preferred)
  if (reason !== null) {
    $.ui.toast(`backend-guard: blocked ${verdict.script} on the API key`)
  }

  return reason
}

export const register: Register = (on, options) => {
  const preferred = String(options.preferred_backend ?? 'claude-code')

  // A guard that throws lets the command through: it must never stall work.
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const reason = await guard($, e.command, preferred)

    return reason === null ? next(e) : { deny: reason }
  }).catch(($, e, next) => next(e))

  on('tool.call', { tool: 'Monitor' }, async ($, e, next) => {
    const reason =
      e.command === undefined ? null : await guard($, e.command, preferred)

    return reason === null ? next(e) : { deny: reason }
  }).catch(($, e, next) => next(e))
}
