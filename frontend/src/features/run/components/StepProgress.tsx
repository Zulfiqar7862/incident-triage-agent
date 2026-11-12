import type { RunStatus } from '@/types/api'

/** Plans contain intent, not per-item completion. Never infer completed actions from model-step counts. */
export function StepProgress({
  step,
  plan,
}: {
  status: RunStatus
  step: number
  plan: string[]
  hasResult: boolean
}) {
  if (!plan.length) return null
  return (
    <details
      className="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-subtle)] px-4 py-3"
      data-testid="step-progress"
    >
      <summary className="text-sm font-medium">
        Investigation plan{' '}
        <span className="ml-2 text-xs font-normal text-[var(--color-fg-secondary)]">
          {plan.length} planned actions · agent step {step}
        </span>
      </summary>
      <ol
        className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-relaxed text-[var(--color-fg-secondary)]"
        aria-label="Investigation plan"
      >
        {plan.map((label, i) => (
          <li key={`${label}-${i}`}>{label}</li>
        ))}
      </ol>
    </details>
  )
}
