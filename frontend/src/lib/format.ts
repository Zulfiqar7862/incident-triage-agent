export const num = (n: number | undefined | null) => Number(n || 0).toLocaleString()
export const human = (s: string) => (s || '').replaceAll('_', ' ')
export const money = (n: number) => `$${(n || 0).toFixed(4)}`

export function argStr(a: Record<string, unknown> | undefined): string {
  return Object.entries(a || {})
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
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

export function prettyJson(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}
