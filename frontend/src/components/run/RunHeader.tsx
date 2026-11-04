import { Clock, Coins, Hash, Layers } from 'lucide-react'
import { StatusBadge } from '@/components/ui/badge'
import { useElapsed } from '@/hooks/useElapsed'
import { formatElapsed, money, num } from '@/lib/format'
import type { RunDetail } from '@/lib/types'

export function RunHeader({ run }: { run: RunDetail }) {
  const elapsed = useElapsed(run.created_at, run.status)
  return (
    <header className="trace-head mb-2 border-b border-[var(--color-border)] pb-4" data-testid="run-header">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <StatusBadge status={run.status} className="text-sm" />
        <span className="inline-flex items-center gap-1 text-xs text-[var(--color-fg-tertiary)]">
          <Clock className="size-3.5" /> {formatElapsed(elapsed)}
        </span>
        <span className="inline-flex items-center gap-1 font-mono text-xs text-[var(--color-fg-tertiary)]">
          <Layers className="size-3.5" /> {run.step}/{run.max_steps}
        </span>
        <span className="inline-flex items-center gap-1 font-mono text-xs text-[var(--color-fg-tertiary)]">
          <Hash className="size-3.5" /> {num(run.usage.input_tokens + run.usage.output_tokens)} tok
        </span>
        <span className="inline-flex items-center gap-1 font-mono text-xs text-[var(--color-fg-tertiary)]">
          <Coins className="size-3.5" /> {money(run.usage.cost_usd)}
        </span>
      </div>
      <h1 className="m-0 max-w-[70ch] text-[22px] font-semibold tracking-tight">{run.title}</h1>
      <p className="mt-1.5 mb-0 max-w-[80ch] text-[var(--color-fg-secondary)]">{run.task}</p>
    </header>
  )
}
