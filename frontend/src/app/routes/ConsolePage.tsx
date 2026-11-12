import { useNavigate, useParams } from 'react-router-dom'
import { useState } from 'react'
import { ErrorBanner } from '@/components/common/ErrorBanner'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { RunViewSkeleton } from '@/components/common/Skeletons'
import { AppHeader } from '@/app/AppHeader'
import { ContextInspector } from '@/features/run/components/ContextInspector'
import { EmptyState } from '@/features/run/components/EmptyState'
import { ReconnectBanner } from '@/features/run/components/ReconnectBanner'
import { RunHeader } from '@/features/run/components/RunHeader'
import { ThinkingIndicator } from '@/features/run/components/ThinkingIndicator'
import { Timeline } from '@/features/run/components/Timeline'
import { RunList } from '@/features/run/components/RunList'
import { useActiveRun } from '@/features/run/hooks/useActiveRun'
import { useStartRun } from '@/features/run/api/useStartRun'
import { mapError } from '@/lib/errors'
import { useUiStore } from '@/stores/uiStore'
import { RunSidebar } from './RunSidebar'

export function ConsolePage() {
  const { runId } = useParams()
  const navigate = useNavigate()
  const thinkingPhase = useUiStore((s) => s.thinkingPhase)
  const [ctxOpen, setCtxOpen] = useState(false)

  const { runQuery, stream, run } = useActiveRun(runId)

  const startScenario = useStartRun({ successToast: 'Scenario started' })

  return (
    <div className="console-shell flex flex-col">
      <a className="skip-link" href="#console-content">
        Skip to investigation
      </a>
      <AppHeader />
      {stream.reconnecting && stream.error ? (
        <ReconnectBanner message={stream.error} onReconnect={stream.reconnectNow} />
      ) : null}
      <main
        id="console-content"
        tabIndex={-1}
        className={`app workspace ${runId ? '' : 'workspace--empty'}`}
      >
        <RunList selectedId={runId || null} />
        <ErrorBoundary>
          <section
            className="col trace flex min-h-0 flex-col overflow-hidden"
            aria-label="Incident investigation"
          >
            {!runId ? (
              <div className="flex min-h-0 flex-1 overflow-auto">
                <EmptyState
                  onStartScenario={() => startScenario.mutate(undefined)}
                  busy={startScenario.isPending}
                />
              </div>
            ) : runQuery.isLoading ? (
              <RunViewSkeleton />
            ) : runQuery.error ? (
              <div className="overflow-auto p-6">
                <ErrorBanner
                  error={mapError(runQuery.error)}
                  onAction={() => {
                    const f = mapError(runQuery.error)
                    if (f.kind === 'not_found') navigate('/')
                    else void runQuery.refetch()
                  }}
                />
              </div>
            ) : run ? (
              <>
                <div className="incident-overview">
                  <RunHeader run={run} />
                  <ThinkingIndicator status={run.status} phase={thinkingPhase} step={run.step} />
                </div>
                <Timeline events={stream.events} status={run.status} />
              </>
            ) : null}
          </section>
        </ErrorBoundary>
        {run ? (
          <RunSidebar
            run={run}
            onRefresh={() => void runQuery.refetch()}
            onInspectContext={() => setCtxOpen(true)}
          />
        ) : null}
      </main>
      {runId ? <ContextInspector runId={runId} open={ctxOpen} onOpenChange={setCtxOpen} /> : null}
    </div>
  )
}
