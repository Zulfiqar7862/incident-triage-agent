import * as Collapsible from '@radix-ui/react-collapsible'
import { ChevronDown } from 'lucide-react'
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
import { humanizeEmbeddedCalls, statusLabel } from '@/lib/humanize'
import { RESUMABLE, TERMINAL, type PendingApproval, type RunDetail } from '@/lib/types'
import { useUiStore } from '@/store/uiStore'
import { cn } from '@/lib/utils'

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
  const showEngineer = useUiStore((s) => s.showEngineerDetails)
  const setShowEngineer = useUiStore((s) => s.setShowEngineerDetails)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [answer, setAnswer] = useState('')
  const [techOpen, setTechOpen] = useState(false)

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
  const reason = humanizeEmbeddedCalls(run.status_reason)

  return (
    <aside
      className="col side sticky top-0 flex max-h-[100dvh] flex-col gap-0 overflow-auto border-l border-[var(--color-border)] bg-[var(--color-elevated)] p-5"
      aria-label="Run controls and state"
    >
      <section className="mb-5 border-b border-[var(--color-border)] pb-5">
        <div className="text-base font-semibold tracking-tight">{statusLabel(run.status)}</div>
        {reason ? <p className="mt-2 text-sm leading-relaxed text-[var(--color-fg-secondary)]">{reason}</p> : null}
        <div className="mt-4 flex flex-wrap gap-2">
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
              if (!window.confirm('Stop this investigation? It cannot be resumed afterwards.')) return
              void act(() => cancelRun(run.run_id))
            }}
          >
            Stop
          </Button>
        </div>
      </section>

      {pending && pending.kind === 'approval' && run.status === 'awaiting_approval' ? (
        <section className="mb-5 border-b border-[var(--color-border)] pb-5">
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
        <section className="mb-5 rounded-[14px] border border-[var(--color-warning-border)] bg-[var(--color-warning-soft)] p-4">
          <h2 className="m-0 mb-2 text-sm font-semibold text-[var(--color-warning)]">Your answer is needed</h2>
          <p className="mb-3 text-sm leading-relaxed">{pending.question}</p>
          <div className="flex gap-2">
            <input
              className="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] px-2.5 py-1.5 text-sm"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Type your answer"
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
        <section className="mb-5 border-b border-[var(--color-border)] pb-5">
          <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-tertiary)]">
            Message the assistant
          </h2>
          <div className="flex gap-2">
            <input
              id="opMsg"
              className="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] px-2.5 py-1.5 text-sm"
              placeholder="Add context or correct its course"
              aria-label="Message to the assistant"
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && msg.trim()) {
                  void act(async () => {
                    await messageRun(run.run_id, msg.trim())
                    setMsg('')
                    toast.success('Message sent')
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
                  toast.success('Message sent')
                })
              }
            >
              Send
            </Button>
          </div>
        </section>
      ) : null}

      {run.result ? (
        <section className="mb-5 border-b border-[var(--color-border)] pb-5">
          <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-tertiary)]">
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
            <p className="mt-1.5 mb-0 leading-relaxed">{run.result.summary}</p>
          </div>
          <p className="mt-3 text-sm leading-relaxed">
            <b>Root cause.</b> {run.result.root_cause}
          </p>
          {run.result.fix_applied ? (
            <p className="text-sm leading-relaxed">
              <b>Fix applied.</b> {humanizeEmbeddedCalls(String(run.result.fix_applied))}
            </p>
          ) : null}
        </section>
      ) : null}

      <section className="mb-5 border-b border-[var(--color-border)] pb-5">
        <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-tertiary)]">Plan</h2>
        {run.plan.length ? (
          <ol className="m-0 list-decimal space-y-1.5 pl-5 text-sm leading-relaxed">
            {run.plan.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-[var(--color-fg-secondary)]">No plan yet.</p>
        )}
      </section>

      <section className="mb-5 border-b border-[var(--color-border)] pb-5">
        <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-tertiary)]">
          Working theories
        </h2>
        {run.hypotheses.length ? (
          run.hypotheses.map((h, i) => (
            <div
              key={i}
              className="mb-2 rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] px-3 py-2.5 text-sm"
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
          <p className="text-sm text-[var(--color-fg-secondary)]">None yet.</p>
        )}
      </section>

      <Collapsible.Root open={techOpen || showEngineer} onOpenChange={(o) => { setTechOpen(o); setShowEngineer(o) }}>
        <Collapsible.Trigger asChild>
          <button
            type="button"
            className="flex w-full items-center justify-between rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] px-3 py-2.5 text-left text-sm font-medium"
            data-testid="engineer-details-toggle"
          >
            For engineers
            <ChevronDown className={cn('size-4 transition-transform', (techOpen || showEngineer) && 'rotate-180')} />
          </button>
        </Collapsible.Trigger>
        <Collapsible.Content className="mt-3 space-y-3">
          <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1.5 text-[13px]">
            <dt className="text-[var(--color-fg-secondary)]">Steps</dt>
            <dd className="m-0 text-right">
              {run.step} / {run.max_steps}
            </dd>
            <dt className="text-[var(--color-fg-secondary)]">Model calls</dt>
            <dd className="m-0 text-right">{run.usage.llm_calls}</dd>
            <dt className="text-[var(--color-fg-secondary)]">Tokens in / out</dt>
            <dd className="m-0 text-right">
              {num(run.usage.input_tokens)} / {num(run.usage.output_tokens)}
            </dd>
            <dt className="text-[var(--color-fg-secondary)]">Estimated cost</dt>
            <dd className="m-0 text-right">{money(run.usage.cost_usd)}</dd>
            <dt className="text-[var(--color-fg-secondary)]">Tool calls</dt>
            <dd className="m-0 text-right">{run.usage.tool_calls}</dd>
            <dt className="text-[var(--color-fg-secondary)]">Run id</dt>
            <dd className="m-0 max-w-[14ch] truncate text-right font-mono text-[11px]" title={run.run_id}>
              {run.run_id}
            </dd>
          </dl>
          <Button variant="ghost" className="w-full justify-start" onClick={onInspectContext}>
            Open context inspector
          </Button>
        </Collapsible.Content>
      </Collapsible.Root>
    </aside>
  )
}
