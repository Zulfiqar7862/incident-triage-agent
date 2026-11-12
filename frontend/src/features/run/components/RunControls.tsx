import { Button } from '@/components/ui/button'
import { RESUMABLE, TERMINAL, type RunDetail } from '@/types/api'
import type { RunActions } from '../api/useRunActions'

/** Pause / Resume / Stop for one run, with the operator-facing status line. */
export function RunControls({ run, actions }: { run: RunDetail; actions: RunActions }) {
  const { busy } = actions
  return (
    <section className="run-controls mb-5">
      <h2 className="section-eyebrow mb-2">Operator control</h2>
      {run.status !== 'awaiting_approval' ? (
        <p className="mt-2 text-sm leading-relaxed text-[var(--color-fg-secondary)]">
          {run.operator?.status || 'Review the current investigation state.'}
        </p>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          disabled={busy || !(run.active && run.status === 'running')}
          onClick={() => void actions.pause()}
        >
          Pause
        </Button>
        <Button
          disabled={busy || !RESUMABLE.includes(run.status)}
          onClick={() => void actions.resume()}
        >
          Resume
        </Button>
        <Button
          variant="danger"
          disabled={busy || TERMINAL.includes(run.status)}
          onClick={() => {
            if (!window.confirm('Stop this investigation? It cannot be resumed afterwards.')) return
            void actions.cancel()
          }}
        >
          Stop
        </Button>
      </div>
    </section>
  )
}
