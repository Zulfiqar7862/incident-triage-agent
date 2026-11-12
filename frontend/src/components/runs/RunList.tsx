import { Link } from 'react-router-dom'
import { RunListSkeleton } from '@/components/common/Skeletons'
import { StatusBadge } from '@/components/ui/badge'
import { useRuns } from '@/features/run/hooks/queries'
import { cn } from '@/lib/utils'

export function RunList({ selectedId }: { selectedId: string | null }) {
  const q = useRuns()

  return (
    <nav
      className="col runs min-h-0 border-r border-[var(--color-border)] bg-[var(--color-subtle)]"
      aria-label="Investigations"
    >
      <h2 className="section-eyebrow mb-4 flex items-center justify-between">
        Investigations{' '}
        <span
          className="rounded-md border border-[var(--color-border)] px-2 py-0.5 tabular-nums"
          aria-label={`${q.data?.length || 0} investigations`}
        >
          {q.data?.length || 0}
        </span>
      </h2>
      {q.isLoading ? <RunListSkeleton /> : null}
      {q.error ? (
        <div
          className="rounded-md bg-[var(--color-danger-soft)] p-3 text-xs text-[var(--color-danger)]"
          role="alert"
        >
          Couldn’t load investigations. {(q.error as Error).message}
          <button type="button" className="mt-2 block underline" onClick={() => void q.refetch()}>
            Retry
          </button>
        </div>
      ) : null}
      {!q.isLoading && !q.error && !(q.data || []).length ? (
        <p className="p-3 text-xs text-[var(--color-fg-secondary)]">
          Your incident history will appear here. Start triage to open an investigation.
        </p>
      ) : null}
      <ul className="m-0 list-none p-0">
        {(q.data || []).map((r) => (
          <li key={r.id} className="mb-1">
            <Link
              to={`/runs/${r.id}`}
              className={cn(
                'run-link block rounded-[10px] border border-transparent px-3 py-2.5 no-underline transition-colors hover:border-[var(--color-border)] hover:bg-[var(--color-elevated)]',
                r.id === selectedId &&
                  'border-[var(--color-border)] bg-[var(--color-elevated)] shadow-[inset_3px_0_0_var(--color-accent)]',
              )}
              aria-current={r.id === selectedId ? 'page' : undefined}
            >
              <div className="text-[13px] font-semibold tracking-tight text-[var(--color-fg)]">
                {r.title}
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs text-[var(--color-fg-tertiary)]">
                <StatusBadge status={r.status} />
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  )
}
