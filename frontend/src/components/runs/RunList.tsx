import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { RunListSkeleton } from '@/components/common/Skeletons'
import { StatusBadge } from '@/components/ui/badge'
import { fetchRuns } from '@/lib/api'
import { cn } from '@/lib/utils'

export function RunList({ selectedId }: { selectedId: string | null }) {
  const q = useQuery({
    queryKey: ['runs'],
    queryFn: fetchRuns,
    refetchInterval: 4000,
  })

  return (
    <nav className="col runs border-r border-[var(--color-border)] bg-[var(--color-subtle)] p-4" aria-label="Runs">
      <h2 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-tertiary)]">Runs</h2>
      {q.isLoading ? <RunListSkeleton /> : null}
      {q.error ? (
        <div className="rounded-md bg-[var(--color-danger-soft)] p-3 text-xs text-[var(--color-danger)]" role="alert">
          Failed to load runs: {(q.error as Error).message}
          <button type="button" className="mt-2 block underline" onClick={() => void q.refetch()}>
            Retry
          </button>
        </div>
      ) : null}
      {!q.isLoading && !q.error && !(q.data || []).length ? (
        <p className="p-3 text-xs text-[var(--color-fg-secondary)]">No runs yet. Pick a scenario and start triage.</p>
      ) : null}
      <ul className="m-0 list-none p-0">
        {(q.data || []).map((r) => (
          <li key={r.id} className="mb-1">
            <Link
              to={`/runs/${r.id}`}
              className={cn(
                'block rounded-[10px] border border-transparent px-3 py-2.5 no-underline transition-colors hover:border-[var(--color-border)] hover:bg-[var(--color-elevated)]',
                r.id === selectedId &&
                  'border-[var(--color-border)] bg-[var(--color-elevated)] shadow-[inset_3px_0_0_var(--color-accent)]',
              )}
              aria-current={r.id === selectedId ? 'page' : undefined}
            >
              <div className="text-[13px] font-semibold tracking-tight text-[var(--color-fg)]">{r.title}</div>
              <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs text-[var(--color-fg-tertiary)]">
                <StatusBadge status={r.status} />
                <span className="font-mono text-[11px]">{r.id}</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  )
}
