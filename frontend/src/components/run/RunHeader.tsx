import { Clock } from 'lucide-react'
import { StatusBadge } from '@/components/ui/badge'
import { useElapsed } from '@/hooks/useElapsed'
import { phaseLine, relativeTime } from '@/lib/format'
import type { RunDetail } from '@/lib/types'

export function RunHeader({ run }: { run: RunDetail }) {
  const elapsed = useElapsed(run.created_at, run.status)
  const alert = run.alert
  const severity = alert?.severity
  const currentStep = run.plan?.[Math.min(run.step, Math.max(run.plan.length - 1, 0))] || null
  const phase = phaseLine(run.status, currentStep, run.step, run.max_steps)
  const task = alert?.summary || run.task

  return (
    <header className="trace-head mb-4 border-b border-[var(--color-border)] pb-5" data-testid="run-header">
      <div className="mb-3 flex flex-wrap items-center gap-2.5">
        <StatusBadge status={run.status} label={run.status_label} className="text-sm" />
        {severity ? (
          <span className="rounded-full bg-[var(--color-danger-soft)] px-2.5 py-0.5 text-[11px] font-semibold text-[var(--color-danger)]">
            {severity}
          </span>
        ) : null}
        {alert?.service ? (
          <span className="rounded-full bg-[var(--color-muted)] px-2.5 py-0.5 text-[11px] font-medium text-[var(--color-fg-secondary)]">
            {alert.service}
          </span>
        ) : null}
        <span className="inline-flex items-center gap-1 text-xs text-[var(--color-fg-tertiary)]">
          <Clock className="size-3.5" aria-hidden /> {relativeTime(elapsed)}
        </span>
      </div>
      <h1 className="m-0 max-w-[48rem] text-[1.375rem] font-semibold leading-snug tracking-tight">
        {alert?.title || run.title}
      </h1>
      <p className="mt-2 mb-0 max-w-[48rem] text-[0.9375rem] leading-relaxed text-[var(--color-fg-secondary)]">
        {task}
      </p>
      {run.status !== 'completed' && run.status !== 'failed' && run.status !== 'cancelled' ? (
        <p className="mt-3 mb-0 text-sm text-[var(--color-fg)]">
          <span className="text-[var(--color-fg-tertiary)]">Now:</span> {phase}
        </p>
      ) : null}
    </header>
  )
}
