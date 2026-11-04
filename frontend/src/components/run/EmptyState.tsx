import { Button } from '@/components/ui/button'

export function EmptyState({ onStartScenario, busy }: { onStartScenario: () => void; busy?: boolean }) {
  return (
    <div
      className="empty-state mx-auto my-10 max-w-[48ch] rounded-[14px] border border-dashed border-[var(--color-border)] bg-[var(--color-elevated)] px-6 py-14 text-center text-[var(--color-fg-secondary)]"
      data-testid="empty-state"
    >
      <svg
        width="72"
        height="72"
        viewBox="0 0 72 72"
        fill="none"
        className="mx-auto mb-4 opacity-90"
        aria-hidden
      >
        <rect x="8" y="14" width="56" height="44" rx="8" stroke="currentColor" strokeWidth="2" />
        <path d="M20 30h20M20 38h32M20 46h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <circle cx="52" cy="30" r="6" fill="var(--color-accent)" opacity="0.85" />
      </svg>
      <strong className="mb-1.5 block text-[15px] text-[var(--color-fg)]">Ready when you are</strong>
      <p className="m-0 mb-4 text-sm leading-relaxed">
        Choose a scenario and start triage. The agent&apos;s plan, tool calls, and any production change it wants to
        make appear here as they happen — with a durable approval gate before anything mutates the cluster.
      </p>
      <Button variant="primary" onClick={onStartScenario} disabled={busy} id="startScenarioBtn">
        Start a scenario
      </Button>
    </div>
  )
}
