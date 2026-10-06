// Pure rules for meter: the status text, and which warning (if any) a new
// reading crosses for the first time.

export type Window = { kind: string; percentUsed: number; resetsAt?: string }

export const LIMIT_WARN: Record<string, number> = { five_hour: 85, seven_day: 90 }
export const LIMIT_WARN_OTHER = 90
export const CONTEXT_WARN = 80
// Context fill falls back under this after a compaction; the warning re-arms.
export const CONTEXT_REARM = 50

const LABEL: Record<string, string> = { five_hour: '5h', seven_day: '7d' }

export function statusText(windows: readonly Window[], contextPercent?: number): string | undefined {
  const parts = windows.map(w => `${LABEL[w.kind] ?? w.kind} ${Math.round(w.percentUsed)}%`)
  if (contextPercent !== undefined) parts.push(`ctx ${contextPercent}%`)

  return parts.length === 0 ? undefined : parts.join(' · ')
}

export function until(resetsAt: string | undefined, now: number): string {
  if (resetsAt === undefined) return ''
  const minutes = Math.max(0, Math.round((Date.parse(resetsAt) - now) / 60000))
  if (Number.isNaN(minutes)) return ''
  const h = Math.floor(minutes / 60)

  return ` (resets in ${h > 0 ? `${h}h ` : ''}${minutes % 60}m)`
}

// The key identifies one window's period, so the warning fires once per period.
export function limitWarning(w: Window, warned: ReadonlySet<string>, now: number): { key: string; text: string } | null {
  const threshold = LIMIT_WARN[w.kind] ?? LIMIT_WARN_OTHER
  const key = `${w.kind}@${w.resetsAt ?? ''}`
  if (w.percentUsed < threshold || warned.has(key)) return null
  const label = LABEL[w.kind] ?? w.kind

  return {
    key,
    text: `${label} usage at ${Math.round(w.percentUsed)}%${until(w.resetsAt, now)}: split the batch or pause before it stalls`,
  }
}
