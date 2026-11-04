import type { HealthInfo, RunDetail, RunSummary, Scenario } from './types'

const TOKEN_KEY = 'apiToken'
const OPERATOR_KEY = 'operator'

export function getToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setToken(t: string) {
  try {
    sessionStorage.setItem(TOKEN_KEY, t)
  } catch {
    /* private mode */
  }
}

export function getOperator(): string {
  try {
    return localStorage.getItem(OPERATOR_KEY) || ''
  } catch {
    return ''
  }
}

export function setOperator(name: string) {
  try {
    localStorage.setItem(OPERATOR_KEY, name)
  } catch {
    /* */
  }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function api<T>(path: string, opts: RequestInit = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = {
    'content-type': 'application/json',
    'x-operator': getOperator().trim(),
    ...(opts.headers as Record<string, string> | undefined),
  }
  const tok = getToken()
  if (tok) headers.authorization = `Bearer ${tok}`

  const r = await fetch(path, { ...opts, headers })
  if (r.status === 401 && !retried) {
    const t = window.prompt('This server requires an API token. Paste it to continue:')
    if (t) {
      setToken(t.trim())
      return api(path, opts, true)
    }
  }
  const j = await r.json().catch(() => ({}))
  if (!r.ok) {
    const detail = typeof (j as { detail?: unknown }).detail === 'string'
      ? (j as { detail: string }).detail
      : `${r.status} ${r.statusText}`
    throw new ApiError(r.status, detail)
  }
  return j as T
}

const post = <T>(p: string, body?: unknown) =>
  api<T>(p, { method: 'POST', body: JSON.stringify(body ?? {}) })

export const fetchHealth = () => api<HealthInfo>('/api/health')
export const fetchScenarios = () => api<Scenario[]>('/api/scenarios')
export const fetchRuns = () => api<RunSummary[]>('/api/runs')
export const fetchRun = (id: string) => api<RunDetail>(`/api/runs/${encodeURIComponent(id)}`)
export const createRun = (scenario_id: string) =>
  post<RunDetail>('/api/runs', { scenario_id })
export const approveRun = (id: string, args?: Record<string, unknown>) =>
  post<RunDetail>(`/api/runs/${encodeURIComponent(id)}/approve`, { args })
export const rejectRun = (id: string, feedback: string) =>
  post<RunDetail>(`/api/runs/${encodeURIComponent(id)}/reject`, { feedback })
export const messageRun = (id: string, text: string) =>
  post<RunDetail>(`/api/runs/${encodeURIComponent(id)}/message`, { text })
export const pauseRun = (id: string) => post<RunDetail>(`/api/runs/${encodeURIComponent(id)}/pause`)
export const resumeRun = (id: string) => post<RunDetail>(`/api/runs/${encodeURIComponent(id)}/resume`)
export const cancelRun = (id: string) => post<RunDetail>(`/api/runs/${encodeURIComponent(id)}/cancel`)
export const fetchContext = (id: string) =>
  api<{
    system: string
    messages: Array<Record<string, unknown>>
    stats: { total_tokens: number; budget: number }
    tools: string[]
  }>(`/api/runs/${encodeURIComponent(id)}/context`)

export function streamUrl(id: string, after: number): string {
  const q = new URLSearchParams()
  const tok = getToken()
  if (tok) q.set('token', tok)
  if (after > 0) q.set('after', String(after))
  const qs = q.toString()
  return `/api/runs/${encodeURIComponent(id)}/stream${qs ? `?${qs}` : ''}`
}
