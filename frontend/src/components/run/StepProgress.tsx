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

/** Vertical full-text step list — never truncated pills. */
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
      className="mb-4 flex flex-col gap-1.5 border-l border-[var(--color-border)] pl-3"
      aria-label="Investigation progress"
      data-testid="step-progress"
    >
      {labels.map((label, i) => {
        const done = i < current || status === 'completed'
        const active = i === current && status !== 'completed'
        return (
          <li
            key={`${label}-${i}`}
            className={cn(
              'relative flex items-start gap-2 text-sm leading-snug',
              done && 'text-[var(--color-success)]',
              active && 'font-semibold text-[var(--color-accent)]',
              !done && !active && 'text-[var(--color-fg-tertiary)]',
            )}
          >
            <span className="mt-0.5 shrink-0">
              {done ? (
                <Check className="size-3.5" aria-hidden />
              ) : active ? (
                <Loader2 className="size-3.5 animate-spin" aria-hidden />
              ) : (
                <Circle className="size-3.5" aria-hidden />
              )}
            </span>
            <span className="min-w-0 whitespace-normal break-words">{label}</span>
          </li>
        )
      })}
    </ol>
  )
}
