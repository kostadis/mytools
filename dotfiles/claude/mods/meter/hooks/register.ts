import type { Register } from 'claude-code'

import { CONTEXT_REARM, CONTEXT_WARN, limitWarning, statusText } from './logic'

export const register: Register = on => {
  // Module variables reset on a reload: at worst one warning repeats.
  const warned = new Set<string>()
  let isContextWarned = false

  on('session.measure', async ($, e, next) => {
    $.ui.status(statusText(e.rateLimits, e.context.percent))

    const now = await $.clock.now()
    for (const w of e.rateLimits) {
      const warning = limitWarning(w, warned, now)
      if (warning !== null) {
        warned.add(warning.key)
        $.ui.toast(warning.text, { timeoutMs: 15000 })
      }
    }

    const percent = e.context.percent
    if (percent !== undefined && percent < CONTEXT_REARM) isContextWarned = false
    if (percent !== undefined && percent >= CONTEXT_WARN && !isContextWarned) {
      isContextWarned = true
      $.ui.toast(`context ${percent}% full: /compact at the next clean break (between chapters or stages)`, { timeoutMs: 15000 })
    }

    return next(e)
  })
}
