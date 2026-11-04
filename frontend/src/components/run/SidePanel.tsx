import { useState } from 'react'
import { toast } from 'sonner'
import { ApprovalCard } from '@/components/run/ApprovalCard'
import { Button } from '@/components/ui/button'
import {
  approveRun,
  cancelRun,
  messageRun,
  pauseRun,
  rejectRun,
  resumeRun,
} from '@/lib/api'
import { mapError } from '@/lib/errors'
import { money, num } from '@/lib/format'
import { RESUMABLE, TERMINAL, type PendingApproval, type RunDetail } from '@/lib/types'
import { useUiStore } from '@/store/uiStore'

export function SidePanel({
  run,
  onRefresh,
  onInspectContext,
}: {
  run: RunDetail
  onRefresh: () => void
  onInspectContext: () => void
}) {
  const operator = useUiStore((s) => s.operator)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [answer, setAnswer] = useState('')

  async function act(fn: () => Promise<unknown>) {
    setBusy(true)
    try {
      await fn()
      onRefresh()
    } catch (e) {
      const f = mapError(e)
      toast.error(`${f.title} — ${f.explanation}`)
    } finally {
      setBusy(false)
    }
  }

  const pending = run.pending

  return (
    <aside className="col side sticky top-0 flex max-h-[100dvh] flex-col gap-0 overflow-auto border-l border-[var(--color-border)] bg-[var(--color-elevated)] p-4" aria-label="Run controls and state">
      <section className="mb-4 border-b border-[var(--color-border)] pb-4">
        <div className="text-sm font-semibold capitalize">{run.status.replaceAll('_', ' ')}</div>
        {run.status_reason ? <p className="mt-1.5 text-[12.5px] text-[var(--color-fg-secondary)]">{run.status_reason}</p> : null}
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Button disabled={busy || !(run.active && run.status === 'running')} onClick={() => void act(() => pauseRun(run.run_id))}>
            Pause
          </Button>
          <Button disabled={busy || !RESUMABLE.includes(run.status)} onClick={() => void act(() => resumeRun(run.run_id))}>
            Resume
          </Button>
          <Button
            variant="danger"
            disabled={busy || TERMINAL.includes(run.status)}
            onClick={() => {
              if (!window.confirm('Cancel this run? It cannot be resumed afterwards.')) return
              void act(() => cancelRun(run.run_id))
            }}
          >
            Cancel run
          </Button>
          <Button onClick={onInspectContext}>Inspect context</Button>
        </div>
      </section>

      {pending && pending.kind === 'approval' && run.status === 'awaiting_approval' ? (
        <section className="mb-4 border-b border-[var(--color-border)] pb-4">
          <ApprovalCard
            pending={pending as PendingApproval}
            operator={operator}
            busy={busy}
            onApprove={async (args) => {
              setBusy(true)
              try {
                await approveRun(run.run_id, args)
                onRefresh()
              } finally {
                setBusy(false)
              }
            }}
            onReject={async (feedback) => {
              setBusy(true)
              try {
                await rejectRun(run.run_id, feedback)
                onRefresh()
              } finally {
                setBusy(false)
              }
            }}
          />
        </section>
      ) : null}

      {pending && pending.kind === 'input' && run.status === 'awaiting_input' ? (
        <section className="mb-4 rounded-[14px] border border-[var(--color-warning-border)] bg-[var(--color-warning-soft)] p-4">
          <h2 className="m-0 mb-2 text-sm font-semibold text-[var(--color-warning)]">The agent needs an answer</h2>
          <p className="mb-2.5 text-sm">{pending.question}</p>
          <div className="flex gap-1.5">
            <input
              className="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] px-2.5 py-1.5 text-sm"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Your answer"
              aria-label="Answer"
            />
            <Button
              variant="approve"
              disabled={busy || !answer.trim()}
              onClick={() =>
                void act(async () => {
                  await messageRun(run.run_id, answer.trim())
                  setAnswer('')
                })
              }
            >
              Send answer
            </Button>
          </div>
        </section>
      ) : null}

      {!TERMINAL.includes(run.status) && run.status !== 'awaiting_input' ? (
        <section className="mb-4 border-b border-[var(--color-border)] pb-4">
          <h2 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-tertiary)]">
            Message the agent
          </h2>
          <div className="flex gap-1.5">
            <input
              id="opMsg"
              className="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] px-2.5 py-1.5 text-sm"
              placeholder="Add context or correct its course"
              aria-label="Message to the agent"
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && msg.trim()) {
                  void act(async () => {
                    await messageRun(run.run_id, msg.trim())
                    setMsg('')
                    toast.success('Message queued')
                  })
                }
              }}
            />
            <Button
              id="opSend"
              disabled={busy || !msg.trim()}
              onClick={() =>
                void act(async () => {
                  await messageRun(run.run_id, msg.trim())
                  setMsg('')
                  toast.success('Message queued')
                })
              }
            >
              Send
            </Button>
          </div>
          <p className="mt-1.5 text-[12.5px] text-[var(--color-fg-secondary)]">The agent reads it at its next step.</p>
        </section>
      ) : null}

      {run.result ? (
        <section className="mb-4 border-b border-[var(--color-border)] pb-4">
          <h2 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-tertiary)]">
            Incident report
          </h2>
          <div
            className={`rounded-r-[10px] border-l-4 px-3.5 py-3 ${
              run.result.resolved
                ? 'border-[var(--color-success)] bg-[var(--color-success-soft)]'
                : 'border-[var(--color-danger)] bg-[var(--color-danger-soft)]'
            }`}
          >
            <b>{run.result.resolved ? 'Resolved' : 'Not resolved'}</b>
            <p className="mt-1.5 mb-0">{run.result.summary}</p>
          </div>
          <p className="mt-2 text-sm">
            <b>Root cause.</b> {run.result.root_cause}
          </p>
          {run.result.fix_applied ? (
            <p className="text-sm">
              <b>Fix.</b> <code className="font-mono text-[12.5px]">{run.result.fix_applied}</code>
            </p>
          ) : null}
        </section>
      ) : null}

      <section className="mb-4 border-b border-[var(--color-border)] pb-4">
        <h2 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-tertiary)]">Plan</h2>
        {run.plan.length ? (
          <ol className="m-0 list-decimal pl-5">
            {run.plan.map((x) => (
              <li key={x} className="my-1">
                {x}
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-xs text-[var(--color-fg-secondary)]">No plan yet.</p>
        )}
      </section>

      <section className="mb-4 border-b border-[var(--color-border)] pb-4">
        <h2 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-tertiary)]">
          Hypotheses
        </h2>
        {run.hypotheses.length ? (
          run.hypotheses.map((h, i) => (
            <div
              key={i}
              className="mb-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] px-3 py-2.5 text-[13px]"
            >
              <span className="mr-1.5 text-[11px] font-bold uppercase tracking-wide text-[var(--color-fg-tertiary)]">
                {h.status}
              </span>
              <span className={h.status === 'rejected' ? 'line-through text-[var(--color-fg-tertiary)]' : ''}>
                {h.text}
              </span>
              {h.evidence ? <div className="mt-1 text-xs text-[var(--color-fg-secondary)]">{h.evidence}</div> : null}
            </div>
          ))
        ) : (
          <p className="text-xs text-[var(--color-fg-secondary)]">None yet.</p>
        )}
      </section>

      <section>
        <h2 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-tertiary)]">
          Telemetry
        </h2>
        <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1.5 text-[13px]">
          <dt className="text-[var(--color-fg-secondary)]">Steps</dt>
          <dd className="m-0 text-right font-mono text-[12.5px]">
            {run.step} / {run.max_steps}
          </dd>
          <dt className="text-[var(--color-fg-secondary)]">Model calls</dt>
          <dd className="m-0 text-right font-mono text-[12.5px]">{run.usage.llm_calls}</dd>
          <dt className="text-[var(--color-fg-secondary)]">Tokens in / out</dt>
          <dd className="m-0 text-right font-mono text-[12.5px]">
            {num(run.usage.input_tokens)} / {num(run.usage.output_tokens)}
          </dd>
          <dt className="text-[var(--color-fg-secondary)]">Estimated cost</dt>
          <dd className="m-0 text-right font-mono text-[12.5px]">{money(run.usage.cost_usd)}</dd>
          <dt className="text-[var(--color-fg-secondary)]">Tool calls</dt>
          <dd className="m-0 text-right font-mono text-[12.5px]">{run.usage.tool_calls}</dd>
          <dt className="text-[var(--color-fg-secondary)]">Checkpoint</dt>
          <dd className="m-0 text-right font-mono text-[12.5px]">v{run.checkpoint_version}</dd>
        </dl>
      </section>
    </aside>
  )
}
