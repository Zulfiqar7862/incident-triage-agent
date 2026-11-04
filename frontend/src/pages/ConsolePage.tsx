import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useEffect, useState } from 'react'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { RunViewSkeleton } from '@/components/common/Skeletons'
import { AppHeader } from '@/components/layout/AppHeader'
import { ContextInspector } from '@/components/run/ContextInspector'
import { EmptyState } from '@/components/run/EmptyState'
import { ReconnectBanner } from '@/components/run/ReconnectBanner'
import { RunHeader } from '@/components/run/RunHeader'
import { SidePanel } from '@/components/run/SidePanel'
import { StepProgress } from '@/components/run/StepProgress'
import { ThinkingIndicator } from '@/components/run/ThinkingIndicator'
import { Timeline } from '@/components/run/Timeline'
import { RunList } from '@/components/runs/RunList'
import { useRunStream } from '@/hooks/useRunStream'
import { createRun, fetchRun, fetchScenarios } from '@/lib/api'
import { ACTIVE } from '@/lib/types'
import { useUiStore } from '@/store/uiStore'
import { useNavigate } from 'react-router-dom'

export function ConsolePage() {
  const { runId } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const thinkingPhase = useUiStore((s) => s.thinkingPhase)
  const [ctxOpen, setCtxOpen] = useState(false)

  const runQuery = useQuery({
    queryKey: ['run', runId],
    queryFn: () => fetchRun(runId!),
    enabled: Boolean(runId),
    refetchInterval: (q) => {
      const st = q.state.data?.status
      if (!st) return 2000
      if (ACTIVE.includes(st) || st === 'awaiting_approval' || st === 'awaiting_input') return 1500
      return false
    },
  })

  const stream = useRunStream(runId || null)

  useEffect(() => {
    if (stream.events.length) {
      void qc.invalidateQueries({ queryKey: ['run', runId] })
      void qc.invalidateQueries({ queryKey: ['runs'] })
    }
  }, [stream.events.length, qc, runId])

  const startScenario = useMutation({
    mutationFn: async () => {
      const scenarios = await fetchScenarios()
      const first = scenarios[0]
      if (!first) throw new Error('No scenarios available')
      return createRun(first.id)
    },
    onSuccess: (run) => {
      void qc.invalidateQueries({ queryKey: ['runs'] })
      navigate(`/runs/${run.run_id}`)
      toast.success('Scenario started')
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const run = runQuery.data

  return (
    <div className="flex h-full flex-col">
      <a className="sr-only absolute left-0 top-0 z-50 -translate-y-full bg-[var(--color-elevated)] p-2 focus:translate-y-0" href="#traceCol">
        Skip to live trace
      </a>
      <AppHeader />
      {stream.reconnecting && stream.error ? (
        <ReconnectBanner message={stream.error} onReconnect={stream.reconnectNow} />
      ) : null}
      <main className="app grid min-h-0 flex-1 grid-cols-[260px_minmax(0,1fr)_380px] max-[1150px]:grid-cols-[200px_minmax(0,1fr)] max-[1150px]:grid-rows-[minmax(0,1fr)_auto] max-[720px]:flex max-[720px]:flex-col">
        <RunList selectedId={runId || null} />
        <ErrorBoundary>
          <section className="col trace flex min-h-0 flex-col overflow-hidden" aria-live="polite" aria-label="Live reasoning trace">
            {!runId ? (
              <div className="overflow-auto p-6">
                <EmptyState onStartScenario={() => startScenario.mutate()} busy={startScenario.isPending} />
              </div>
            ) : runQuery.isLoading ? (
              <RunViewSkeleton />
            ) : runQuery.error ? (
              <div className="m-6 rounded-[10px] border border-[var(--color-danger)]/30 bg-[var(--color-danger-soft)] p-4 text-[var(--color-danger)]" role="alert">
                {(runQuery.error as Error).message}
                <button type="button" className="ml-3 underline" onClick={() => void runQuery.refetch()}>
                  Retry
                </button>
              </div>
            ) : run ? (
              <>
                <div className="shrink-0 px-7 pt-6">
                  <RunHeader run={run} />
                  <StepProgress
                    status={run.status}
                    step={run.step}
                    plan={run.plan}
                    hasResult={Boolean(run.result)}
                  />
                  <ThinkingIndicator status={run.status} phase={thinkingPhase} step={run.step} />
                </div>
                <Timeline events={stream.events} />
              </>
            ) : null}
          </section>
        </ErrorBoundary>
        {run ? (
          <SidePanel run={run} onRefresh={() => void runQuery.refetch()} onInspectContext={() => setCtxOpen(true)} />
        ) : (
          <aside className="border-l border-[var(--color-border)] bg-[var(--color-elevated)] p-4 text-sm text-[var(--color-fg-tertiary)] max-[1150px]:col-span-full max-[1150px]:border-l-0 max-[1150px]:border-t" />
        )}
      </main>
      {runId ? <ContextInspector runId={runId} open={ctxOpen} onOpenChange={setCtxOpen} /> : null}
    </div>
  )
}
