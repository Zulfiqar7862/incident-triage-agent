import { Check, Circle, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { RunStatus } from '@/lib/types'

const PHASES = ['Intake', 'Investigate', 'Diagnose', 'Propose', 'Approval', 'Resolve'] as const

function phaseIndex(status: RunStatus, step: number, hasPlan: boolean, hasResult: boolean): number {
  if (status === 'completed') return 5
  if (status === 'awaiting_approval' || status === 'awaiting_input') return 4
  if (hasResult) return 5
  if (step <= 1) return 0
  if (step <= 3) return 1
  if (!hasPlan || step <= 5) return 2
  return 3
}

export function StepProgress({
  status,
  step,
  plan,
  hasResult,
}: {
  status: RunStatus
  step: number
  plan: string[]
  hasResult: boolean
}) {
  const current = phaseIndex(status, step, plan.length > 0, hasResult)
  const labels = plan.length >= 3 && plan.length <= 8 ? plan : [...PHASES]

  return (
    <ol
      className="mb-4 flex flex-wrap items-center gap-1 overflow-x-auto pb-1"
      aria-label="Investigation progress"
      data-testid="step-progress"
    >
      {labels.map((label, i) => {
        const done = i < current || status === 'completed'
        const active = i === current && status !== 'completed'
        return (
          <li key={`${label}-${i}`} className="flex items-center gap-1">
            <span
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold',
                done && 'border-[var(--color-success)]/40 bg-[var(--color-success-soft)] text-[var(--color-success)]',
                active && 'border-[var(--color-accent)]/40 bg-[var(--color-accent-soft)] text-[var(--color-accent)]',
                !done && !active && 'border-[var(--color-border)] bg-[var(--color-elevated)] text-[var(--color-fg-tertiary)]',
              )}
              title={label}
            >
              {done ? (
                <Check className="size-3" />
              ) : active ? (
                <Loader2 className="size-3 animate-spin" />
              ) : (
                <Circle className="size-3" />
              )}
              <span className="max-w-[12ch] truncate">{label}</span>
            </span>
            {i < labels.length - 1 ? <span className="mx-0.5 h-px w-3 bg-[var(--color-border)]" aria-hidden /> : null}
          </li>
        )
      })}
    </ol>
  )
}
