/** API-owned prose and scalar fields. Canonical model/evidence strings are never display fallbacks. */
export interface OperatorDisplay {
  state?: 'applied' | 'rejected' | 'unverified' | 'failed'
  title: string
  summary: string
  fields: Array<{ label: string; value: string }>
  evidence: string[]
  impact: string
}
export interface OperatorRun {
  title: string
  summary: string
  status: string
  evidence: string[]
  plan: string[]
  report: OperatorDisplay | null
}

export type RunStatus =
  | 'queued'
  | 'running'
  | 'awaiting_approval'
  | 'awaiting_input'
  | 'paused'
  | 'interrupted'
  | 'needs_attention'
  | 'completed'
  | 'failed'
  | 'cancelled'

export const TERMINAL: RunStatus[] = ['completed', 'failed', 'cancelled']
export const RESUMABLE: RunStatus[] = ['paused', 'interrupted', 'failed', 'needs_attention']
export const ACTIVE: RunStatus[] = ['queued', 'running']

export interface Scenario {
  id: string
  title: string
  description: string
}

export interface RunSummary {
  id: string
  scenario_id: string
  title: string
  status: RunStatus
  created_at: number
  updated_at: number
}

export interface Usage {
  llm_calls: number
  input_tokens: number
  output_tokens: number
  cost_usd: number
  llm_ms: number
  tool_calls: number
  tool_retries: number
  tool_errors: number
}

export interface Hypothesis {
  text: string
  status: string
  evidence?: string
}

export interface PendingApproval {
  operator?: OperatorDisplay
  kind: 'approval'
  tool_call_id: string
  tool: string
  args: Record<string, unknown>
  step: number
  requested_at?: number
  executing?: boolean
  /** Backend display helpers (app/presentation/views/tool_labels.py) */
  title?: string
  summary?: string
  risk?: 'high' | 'low' | string
}

export interface PendingInput {
  operator?: OperatorDisplay
  kind: 'input'
  tool_call_id: string
  tool: string
  args: Record<string, unknown>
  question: string
  step: number
  title?: string
  summary?: string
  risk?: string
}

export interface AlertCard {
  title: string
  summary: string
  service: string
  severity: string
  severity_code?: string
  fired_min_ago?: number
  fired_at?: number
}

export type Pending = PendingApproval | PendingInput | null

export interface RunResult {
  operator?: OperatorDisplay
  resolved: boolean
  summary: string
  root_cause: string
  operator_summary?: string
  fix_summary?: string
  fix_applied?: string
  follow_ups?: string[]
  sim_resolved?: boolean
}

export interface ContextStats {
  total_tokens: number
  budget: number
  system_tokens: number
  tools_tokens: number
  memory_tokens: number
  history_tokens: number
  shrunk_messages: number
  dropped_groups: number
}

export interface RunDetail {
  operator?: OperatorRun
  run_id: string
  scenario_id: string
  title: string
  task: string
  status: RunStatus
  status_label?: string
  status_reason?: string
  active: boolean
  step: number
  max_steps: number
  plan: string[]
  hypotheses: Hypothesis[]
  usage: Usage
  pending: Pending
  result: RunResult | null
  created_at: number
  checkpoint_version: number
  last_context?: ContextStats
  recalled_memories?: Array<{ date: string; age_days: number; root_cause: string }>
  service?: string
  alert?: AlertCard
}

export interface AgentEvent {
  operator?: OperatorDisplay | null
  seq: number
  run_id: string
  type: string
  ts?: number
  payload: Record<string, unknown>
}

export interface HealthInfo {
  ok: boolean
  auth: boolean
  llm: { provider: string; model: string }
}
