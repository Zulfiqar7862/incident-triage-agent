import { formatElapsed, money, num } from './format'

export function formatScalar(value: unknown, keyHint?: string): string {
  if (value == null) return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') {
    if (keyHint && /confidence|ratio|rate/i.test(keyHint) && value >= 0 && value <= 1) {
      return `${Math.round(value * 100)}%`
    }
    if (keyHint && /cost|usd/i.test(keyHint)) return money(value)
    if (keyHint && /(ms|latency|duration)/i.test(keyHint)) return `${num(value)} ms`
    if (keyHint && /(seconds|elapsed)/i.test(keyHint)) return formatElapsed(value)
    if (value > 1_000_000_000_000 || (value > 1_000_000_000 && value < 4_000_000_000)) {
      const ms = value > 4_000_000_000 ? value : value * 1000
      return new Date(ms).toLocaleString()
    }
    return num(value)
  }
  if (typeof value === 'string') {
    if (/^\d{4}-\d{2}-\d{2}T/.test(value) || /^\d{4}-\d{2}-\d{2} /.test(value)) {
      const d = new Date(value)
      if (!Number.isNaN(d.getTime())) return d.toLocaleString()
    }
    if (keyHint && /severity|priority|sev/i.test(keyHint)) {
      const map: Record<string, string> = {
        P1: 'Critical',
        P2: 'High',
        P3: 'Medium',
        P4: 'Low',
        SEV1: 'Critical',
        SEV2: 'High',
        SEV3: 'Medium',
        SEV4: 'Low',
      }
      const hit = map[value.toUpperCase()] || map[value]
      if (hit) return hit
    }
    // Never surface raw alert ticket ids in the default operator view
    if (keyHint && /^id$/i.test(keyHint) && /^ALRT-/i.test(value)) return 'Alert'
    return value
  }
  return String(value)
}

export function parseMaybeJson(raw: string): unknown {
  const t = raw.trim()
  if (!t) return ''
  if ((t.startsWith('{') && t.endsWith('}')) || (t.startsWith('[') && t.endsWith(']'))) {
    try {
      return JSON.parse(t)
    } catch {
      return raw
    }
  }
  return raw
}

export function statusTone(s: string): 'ok' | 'warn' | 'danger' | 'accent' | 'neutral' {
  const v = s.toLowerCase()
  if (/(ok|ready|running|confirmed|resolved|success|healthy|firing|completed)/.test(v)) return 'ok'
  if (/(pending|waiting|investigating|warning|degraded)/.test(v)) return 'warn'
  if (/(error|failed|rejected|crash|oom|critical)/.test(v)) return 'danger'
  if (/(p1|p2|sev)/.test(v)) return 'danger'
  return 'neutral'
}
