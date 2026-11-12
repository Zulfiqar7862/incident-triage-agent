import * as Collapsible from '@radix-ui/react-collapsible'
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { DataView } from '@/components/common/DataView'
import { Button } from '@/components/ui/button'
import { money, num } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useUiStore } from '@/stores/uiStore'
import type { RunDetail } from '@/types/api'

/** "For engineers" disclosure: raw proposal, report, plan, hypotheses, and usage. */
export function EngineerDetails({
  run,
  onInspectContext,
}: {
  run: RunDetail
  onInspectContext: () => void
}) {
  const showEngineer = useUiStore((s) => s.showEngineerDetails)
  const setShowEngineer = useUiStore((s) => s.setShowEngineerDetails)
  const [techOpen, setTechOpen] = useState(false)
  const open = techOpen || showEngineer
  return (
    <Collapsible.Root
      open={open}
      onOpenChange={(o) => {
        setTechOpen(o)
        setShowEngineer(o)
      }}
    >
      <Collapsible.Trigger asChild>
        <button
          type="button"
          className="flex w-full items-center justify-between rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] px-3 py-2.5 text-left text-sm font-medium"
          data-testid="engineer-details-toggle"
        >
          For engineers
          <ChevronDown className={cn('size-4 transition-transform', open && 'rotate-180')} />
        </button>
      </Collapsible.Trigger>
      <Collapsible.Content className="mt-3 space-y-3">
        <p className="text-xs text-[var(--color-fg-secondary)]">
          Original model reasoning, diagnostic evidence, and unverified hypotheses. These are not
          operator instructions.
        </p>
        <DataView
          data={{
            proposal: run.pending,
            report: run.result,
            plan: run.plan,
            hypotheses: run.hypotheses,
          }}
          compact
        />
        <UsageList run={run} />
        <Button variant="ghost" className="w-full justify-start" onClick={onInspectContext}>
          Open context inspector
        </Button>
      </Collapsible.Content>
    </Collapsible.Root>
  )
}

function UsageList({ run }: { run: RunDetail }) {
  const rows: [string, string | number][] = [
    ['Steps', `${run.step} / ${run.max_steps}`],
    ['Model calls', run.usage.llm_calls],
    ['Tokens in / out', `${num(run.usage.input_tokens)} / ${num(run.usage.output_tokens)}`],
    ['Estimated cost', money(run.usage.cost_usd)],
    ['Tool calls', run.usage.tool_calls],
  ]
  return (
    <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1.5 text-[13px]">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-[var(--color-fg-secondary)]">{label}</dt>
          <dd className="m-0 text-right">{value}</dd>
        </div>
      ))}
      <dt className="text-[var(--color-fg-secondary)]">Run id</dt>
      <dd className="m-0 max-w-[14ch] truncate text-right font-mono text-[11px]" title={run.run_id}>
        {run.run_id}
      </dd>
    </dl>
  )
}
