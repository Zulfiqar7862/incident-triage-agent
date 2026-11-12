import { Activity, ArrowRight, ClipboardCheck, ShieldCheck, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function EmptyState({
  onStartScenario,
  busy,
}: {
  onStartScenario: () => void
  busy?: boolean
}) {
  return (
    <div className="empty-workspace" data-testid="empty-state">
      <div className="inline-flex items-center gap-2 rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-fg-secondary)]">
        <Activity className="size-4 text-[var(--color-accent)]" aria-hidden /> Operator console
        ready
      </div>
      <h1>
        Investigate with autonomy.
        <br />
        Stay in control.
      </h1>
      <p>
        Choose an incident scenario to begin. The agent gathers evidence, proposes a fix, and
        verifies recovery. You decide what changes.
      </p>
      <div className="workflow-guide">
        <div>
          <Search className="size-5 text-[var(--color-accent)]" aria-hidden />
          <h2>Follow the evidence</h2>
          <p>Watch the plan, tool results, and recovery from failures in one activity stream.</p>
        </div>
        <div>
          <ShieldCheck className="size-5 text-[var(--color-warning)]" aria-hidden />
          <h2>Review every change</h2>
          <p>Approve, edit, or reject the proposed fix before it can apply.</p>
        </div>
        <div>
          <ClipboardCheck className="size-5 text-[var(--color-success)]" aria-hidden />
          <h2>Keep the record</h2>
          <p>Durable state and an audit trail preserve the investigation across restarts.</p>
        </div>
      </div>
      <div className="empty-guidance">
        <h2 className="mb-2 text-sm font-semibold">Ready for an investigation?</h2>
        <p className="mb-4 text-sm leading-relaxed text-[var(--color-fg-secondary)]">
          Use the scenario selector above, or start the first available scenario. Platform tools
          operate on a simulated cluster; no production credentials are held.
        </p>
        <Button variant="primary" onClick={onStartScenario} disabled={busy} id="startScenarioBtn">
          {busy ? 'Starting…' : 'Start triage'} <ArrowRight className="size-4" aria-hidden />
        </Button>
      </div>
    </div>
  )
}
