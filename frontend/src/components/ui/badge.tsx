import { cn } from '@/lib/utils'
import type { RunStatus } from '@/lib/types'

const tone: Record<string, string> = {
  running: 'text-[var(--color-accent)]',
  queued: 'text-[var(--color-fg-secondary)]',
  awaiting_approval: 'text-[var(--color-warning)]',
  awaiting_input: 'text-[var(--color-warning)]',
  paused: 'text-[var(--color-warning)]',
  interrupted: 'text-[var(--color-warning)]',
  needs_attention: 'text-[var(--color-warning)]',
  completed: 'text-[var(--color-success)]',
  failed: 'text-[var(--color-danger)]',
  cancelled: 'text-[var(--color-danger)]',
}

const dot: Record<string, string> = {
  running: 'bg-[var(--color-accent)] status-dot-running',
  queued: 'bg-[var(--color-fg-tertiary)]',
  awaiting_approval: 'bg-[var(--color-warning)]',
  awaiting_input: 'bg-[var(--color-warning)]',
  paused: 'bg-[var(--color-warning)]',
  interrupted: 'bg-[var(--color-warning)]',
  needs_attention: 'bg-[var(--color-warning)]',
  completed: 'bg-[var(--color-success)]',
  failed: 'bg-[var(--color-danger)]',
  cancelled: 'bg-[var(--color-danger)]',
}

/** Fallback only when API omits status_label (should be rare). */
const FALLBACK: Record<string, string> = {
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

export function StatusBadge({
  status,
  label,
  className,
}: {
  status: RunStatus | string
  label?: string
  className?: string
}) {
  const s = String(status)
  const text = label || FALLBACK[s] || s.replaceAll('_', ' ')
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 text-xs font-semibold',
        tone[s] || 'text-[var(--color-fg-secondary)]',
        className,
      )}
    >
      <span className={cn('inline-block size-1.5 rounded-full', dot[s] || 'bg-[var(--color-fg-tertiary)]')} />
      {text}
    </span>
  )
}
