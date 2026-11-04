import { Clock, Coins, Hash, Layers } from 'lucide-react'
import { StatusBadge } from '@/components/ui/badge'
import { useElapsed } from '@/hooks/useElapsed'
import { formatElapsed, money, num } from '@/lib/format'
import type { RunDetail } from '@/lib/types'

function severityFromTask(task: string): string | null {
  const m = task.match(/\b(P[1-4]|SEV[1-4]|Critical|High|Medium|Low)\b/i)
  return m ? m[1].toUpperCase() : null
}

export function RunHeader({ run }: { run: RunDetail }) {
  const elapsed = useElapsed(run.created_at, run.status)
  const severity = severityFromTask(run.task)
  const currentStep = run.plan?.[Math.min(run.step, Math.max(run.plan.length - 1, 0))] || null

  return (
    <header className="trace-head mb-3 border-b border-[var(--color-border)] pb-5" data-testid="run-header">
      <div className="mb-3 flex flex-wrap items-center gap-2.5">
        <StatusBadge status={run.status} className="text-sm" />
        {severity ? (
          <span className="rounded-full bg-[var(--color-danger-soft)] px-2 py-0.5 text-[11px] font-semibold text-[var(--color-danger)]">
            {severity}
          </span>
        ) : null}
        <span className="inline-flex items-center gap-1 text-xs text-[var(--color-fg-tertiary)]">
          <Clock className="size-3.5" aria-hidden /> {formatElapsed(elapsed)}
        </span>
        <span className="inline-flex items-center gap-1 text-xs text-[var(--color-fg-tertiary)]">
          <Layers className="size-3.5" aria-hidden /> Step {run.step}/{run.max_steps}
        </span>
        <span className="inline-flex items-center gap-1 text-xs text-[var(--color-fg-tertiary)]">
          <Hash className="size-3.5" aria-hidden /> {num(run.usage.input_tokens + run.usage.output_tokens)} tokens
        </span>
        <span className="inline-flex items-center gap-1 text-xs text-[var(--color-fg-tertiary)]">
          <Coins className="size-3.5" aria-hidden /> {money(run.usage.cost_usd)}
        </span>
      </div>
      <h1 className="m-0 max-w-[48rem] text-[1.375rem] font-semibold leading-snug tracking-tight">{run.title}</h1>
      <p className="mt-2 mb-0 max-w-[48rem] text-[0.9375rem] leading-relaxed text-[var(--color-fg-secondary)]">{run.task}</p>
      {currentStep && run.status !== 'completed' && run.status !== 'failed' && run.status !== 'cancelled' ? (
        <p className="mt-3 mb-0 text-sm text-[var(--color-fg)]">
          <span className="text-[var(--color-fg-tertiary)]">Current focus:</span> {currentStep}
        </p>
      ) : null}
    </header>
  )
}
