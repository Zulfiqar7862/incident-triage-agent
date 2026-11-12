import { Brain } from 'lucide-react'
import { type RunStatus } from '@/types/api'
import { cn } from '@/lib/utils'

export function ThinkingIndicator({
  status,
}: {
  status: RunStatus
  phase: string | null
  step?: number
}) {
  if (status !== 'running') return null
  return (
    <div
      className={cn(
        'sticky top-0 z-[5] mb-3 flex items-center gap-3 rounded-[10px] border border-[var(--color-accent)]/25 bg-[var(--color-accent-soft)] px-3.5 py-2.5 text-sm text-[var(--color-accent)] shadow-sm',
      )}
      role="status"
      aria-live="polite"
      data-testid="thinking-indicator"
    >
      <Brain className="size-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="font-medium">Investigation in progress</div>
      </div>
      <div className="animate-think flex gap-1" aria-hidden>
        <span className="size-1.5 rounded-full bg-current" />
        <span className="size-1.5 rounded-full bg-current" />
        <span className="size-1.5 rounded-full bg-current" />
      </div>
    </div>
  )
}
