export const num = (n: number | undefined | null) => Number(n || 0).toLocaleString()
export const human = (s: string) => (s || '').replaceAll('_', ' ')
export const money = (n: number) => `$${(n || 0).toFixed(4)}`

export function argStr(a: Record<string, unknown> | undefined): string {
  return Object.entries(a || {})
    .map(([k, v]) => {
      if (v == null) return `${k}=—`
      if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean')
        return `${k}=${v}`
      return `${k}=…`
    })
    .join(', ')
}

export function withoutKeys(o: Record<string, unknown> | undefined, ks: string[]) {
  return Object.fromEntries(Object.entries(o || {}).filter(([k]) => !ks.includes(k)))
}

export function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const m = Math.floor(s / 60)
  const r = s % 60
  if (m >= 60) {
    const h = Math.floor(m / 60)
    return `${h}h ${m % 60}m`
  }
  return m > 0 ? `${m}m ${r.toString().padStart(2, '0')}s` : `${r}s`
}

/** For clipboard / technical disclosure only — never render in the default UI. */
export function prettyJson(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

/** Confidence display for approval cards (not tool copy — that comes from the API). */
export function confidencePhrase(confidence: number): { percent: number; phrase: string } {
  const percent = Math.round(Math.max(0, Math.min(1, confidence)) * 100)
  if (percent >= 85) return { percent, phrase: 'likely safe' }
  if (percent >= 60) return { percent, phrase: 'needs a careful look' }
  return { percent, phrase: 'higher risk — review carefully' }
}

/** Friendly relative time for run headers. */
export function relativeTime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  if (s < 10) return 'just now'
  if (s < 60) return `${s} sec ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.floor(m / 60)
  const rm = m % 60
  return rm ? `${h}h ${rm}m` : `${h}h`
}

/** Editable-field labels for approval forms (keys only — not tool narratives). */
export const FIELD_LABELS: Record<string, string> = {
  service: 'Service',
  to_version: 'Target version',
  reason: 'Reason',
  confidence: 'Confidence',
}

export function phaseLine(
  status: string,
  planStep: string | null | undefined,
  step: number,
  maxSteps: number,
): string {
  if (status === 'awaiting_approval') return 'Waiting for your approval'
  if (status === 'awaiting_input') return 'Waiting for your answer'
  if (status === 'paused') return 'Paused — resume when ready'
  if (status === 'completed') return 'Incident closed'
  if (status === 'failed') return 'Stopped with an error'
  if (status === 'cancelled') return 'Stopped by you'
  if (planStep) return planStep
  if (step <= 1) return 'Starting the investigation'
  if (step >= maxSteps - 1) return 'Wrapping up'
  return 'Working through the investigation'
}
