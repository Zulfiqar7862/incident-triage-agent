/** Plain-English copy for operators — never show function-call / snake_case jargon in the default UI. */

export function titleCaseWords(raw: string): string {
  return (raw || '')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_./-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function str(args: Record<string, unknown> | undefined, key: string): string {
  const v = args?.[key]
  if (v == null || v === '') return ''
  return String(v)
}

function numArg(args: Record<string, unknown> | undefined, key: string): number | null {
  const v = args?.[key]
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim() && !Number.isNaN(Number(v))) return Number(v)
  return null
}

/** Map a backend tool name + args to one plain sentence. */
export function describeTool(name: string, args: Record<string, unknown> = {}): string {
  const service = str(args, 'service')
  const metric = str(args, 'metric')
  const query = str(args, 'query')
  const toVersion = str(args, 'to_version')
  const window = numArg(args, 'window_minutes')
  const limit = numArg(args, 'limit')
  const topK = numArg(args, 'top_k')

  switch (name) {
    case 'get_alert':
      return 'Read the alert that started this incident'
    case 'list_services':
      return 'List services and their health'
    case 'describe_service':
      return service ? `Inspect ${service}` : 'Inspect a service'
    case 'query_metrics':
    case 'get_metrics':
      if (service && metric) return `Check ${metric.replaceAll('_', ' ')} for ${service}`
      if (service) return `Check health metrics for ${service}`
      return 'Check service health metrics'
    case 'search_logs':
    case 'query_logs':
      if (service && query && query !== '*') return `Read recent logs for ${service} matching “${query}”`
      if (service) return `Read recent error logs for ${service}`
      return 'Read recent error logs'
    case 'search_runbooks':
      return query ? `Search runbooks for “${query}”` : 'Search internal runbooks'
    case 'get_recent_deploys':
      return service ? `Review recent deploys for ${service}` : 'Review recent deploys'
    case 'rollback_deploy':
      if (service && toVersion) return `Roll back ${service} to version ${toVersion}`
      if (service) return `Roll back ${service} to a previous version`
      return 'Roll back a service to a previous version'
    case 'restart_service':
      return service ? `Restart ${service}` : 'Restart a service'
    case 'scale_service': {
      const n = numArg(args, 'replicas') ?? numArg(args, 'instances') ?? numArg(args, 'count')
      if (service && n != null) return `Scale ${service} to ${n} instances`
      if (service) return `Scale ${service}`
      return 'Scale a service'
    }
    case 'update_working_memory':
      return 'Update the investigation notes'
    case 'ask_operator':
      return str(args, 'question') || 'Ask you a question'
    case 'finish':
      return 'Wrap up the incident report'
    default: {
      // Generic fallback: Title Case words, no parentheses / snake_case
      const base = titleCaseWords(name)
      if (service && toVersion) return `${base} on ${service} to ${toVersion}`
      if (service) return `${base} for ${service}`
      if (metric) return `${base}: ${metric.replaceAll('_', ' ')}`
      if (query) return `${base}: ${query}`
      if (window != null) return `${base} (last ${window} min)`
      if (limit != null) return `${base} (up to ${limit})`
      if (topK != null) return `${base} (top ${topK})`
      return base || 'Run a check'
    }
  }
}

/** Short noun phrase for cards / badges (no full sentence). */
export function toolNoun(name: string): string {
  const map: Record<string, string> = {
    get_alert: 'Alert details',
    list_services: 'Service list',
    describe_service: 'Service details',
    query_metrics: 'Health metrics',
    get_metrics: 'Health metrics',
    search_logs: 'Log search',
    query_logs: 'Log search',
    search_runbooks: 'Runbook search',
    get_recent_deploys: 'Deploy history',
    rollback_deploy: 'Rollback',
    restart_service: 'Restart',
    scale_service: 'Scale',
    update_working_memory: 'Notes update',
    ask_operator: 'Question for you',
    finish: 'Incident report',
  }
  return map[name] || titleCaseWords(name)
}

const FN_CALL_RE = /\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\s*\(([^)]*)\)/gi

/** Parse `key=value, key2=value2` from a brief_args fragment. */
function parseBriefArgs(inner: string): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const part of inner.split(',')) {
    const idx = part.indexOf('=')
    if (idx < 0) continue
    const k = part.slice(0, idx).trim()
    let v = part.slice(idx + 1).trim()
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      v = v.slice(1, -1)
    }
    if (!k) continue
    const n = Number(v)
    out[k] = v !== '' && !Number.isNaN(n) && /^-?\d+(\.\d+)?$/.test(v) ? n : v
  }
  return out
}

/**
 * Rewrite backend status / event text that embeds function-call strings
 * like `rollback_deploy(service=checkout-service, …)`.
 */
export function humanizeEmbeddedCalls(text: string | null | undefined): string {
  if (!text) return ''
  let out = text
  out = out.replace(FN_CALL_RE, (_m, name: string, inner: string) => {
    return describeTool(name, parseBriefArgs(inner))
  })
  // Soften stock approval copy
  out = out.replace(
    /^Approve, edit, or reject\s+/i,
    'Please approve, edit, or reject: ',
  )
  // Drop leftover snake_case identifiers that look like tools (not service names with hyphens)
  out = out.replace(/\b([a-z]+_[a-z0-9_]+)\b/g, (m) => {
    // keep confidence-like decimals context; humanize known tools / memory keys
    if (
      /^(rollback_deploy|restart_service|scale_service|query_metrics|get_metrics|search_logs|query_logs|get_alert|list_services|describe_service|search_runbooks|get_recent_deploys|update_working_memory|ask_operator|finish|error_rate|to_version|window_minutes)$/.test(
        m,
      )
    ) {
      return titleCaseWords(m)
    }
    return m
  })
  return out
}

export function confidenceLabel(confidence: number): { percent: number; phrase: string; tone: 'ok' | 'warn' | 'danger' } {
  const percent = Math.round(Math.max(0, Math.min(1, confidence)) * 100)
  if (percent >= 85) return { percent, phrase: 'likely safe', tone: 'ok' }
  if (percent >= 60) return { percent, phrase: 'needs a careful look', tone: 'warn' }
  return { percent, phrase: 'higher risk — review carefully', tone: 'danger' }
}

export function severityLabel(raw: string | null | undefined): string | null {
  if (!raw) return null
  const u = raw.toUpperCase()
  const map: Record<string, string> = {
    P1: 'Priority: Critical',
    P2: 'Priority: High',
    P3: 'Priority: Medium',
    P4: 'Priority: Low',
    SEV1: 'Priority: Critical',
    SEV2: 'Priority: High',
    SEV3: 'Priority: Medium',
    SEV4: 'Priority: Low',
    CRITICAL: 'Priority: Critical',
    HIGH: 'Priority: High',
    MEDIUM: 'Priority: Medium',
    LOW: 'Priority: Low',
  }
  return map[u] || (map[raw] ?? null) || (/^(P|SEV)[1-4]$/i.test(raw) ? `Priority: ${raw}` : null)
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    queued: 'Queued',
    running: 'Investigating',
    awaiting_approval: 'Needs your approval',
    awaiting_input: 'Needs your answer',
    paused: 'Paused',
    interrupted: 'Interrupted',
    needs_attention: 'Needs attention',
    completed: 'Finished',
    failed: 'Failed',
    cancelled: 'Stopped',
  }
  return map[status] || titleCaseWords(status)
}

/** Friendly relative / elapsed time: "just now", "2 min ago", "1h 3m". */
export function friendlyElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  if (s < 10) return 'just now'
  if (s < 60) return `${s} sec ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.floor(m / 60)
  const rm = m % 60
  return rm ? `${h}h ${rm}m` : `${h}h`
}

export function friendlyPhase(status: string, planStep: string | null | undefined, step: number, maxSteps: number): string {
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

/** True if a string looks like a function-call snippet (for tests / guards). */
export function looksLikeFunctionCall(text: string): boolean {
  return /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\s*\([^)]*=/.test(text)
}
