import * as Collapsible from '@radix-ui/react-collapsible'
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ApprovalCard } from '@/features/approval'
import { OperatorFacts } from './OperatorFacts'
import { DataView } from '@/components/common/DataView'
import { Button } from '@/components/ui/button'
import { useRunActions } from '@/features/run/hooks/useRunActions'
import { money, num } from '@/lib/format'
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
  const [answer, setAnswer] = useState('')
  const [techOpen, setTechOpen] = useState(false)
  const actions = useRunActions(run.run_id, onRefresh)
  const { busy } = actions

  const pending = run.pending
  const report = run.operator?.report || run.result?.operator

  return (
    <aside
      className="col side flex min-h-0 flex-col gap-0 overflow-auto border-l border-[var(--color-border)]"
      aria-label="Run controls and state"
    >
      {pending && pending.kind === 'approval' && run.status === 'awaiting_approval' ? (
        <section className="mb-5 border-b border-[var(--color-border)] pb-5">
          <ApprovalCard
            pending={pending as PendingApproval}
            operator={operator}
            busy={busy}
            onApprove={async (args) => {
              await actions.approve(args)
            }}
            onReject={async (feedback) => {
              await actions.reject(feedback)
            }}
          />
        </section>
      ) : null}

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
              if (!window.confirm('Stop this investigation? It cannot be resumed afterwards.'))
                return
              void actions.cancel()
            }}
          >
            Stop
          </Button>
        </div>
      </section>

      {pending && pending.kind === 'input' && run.status === 'awaiting_input' ? (
        <section className="mb-5 rounded-[14px] border border-[var(--color-warning-border)] bg-[var(--color-warning-soft)] p-4">
          <h2 className="m-0 mb-2 text-sm font-semibold text-[var(--color-warning)]">
            Your answer is needed
          </h2>
          <p className="mb-3 text-sm leading-relaxed">
            {pending.operator?.summary ||
              'The agent needs guidance. Review its full question in the engineering record before answering.'}
          </p>
          <label className="field-label" htmlFor="operator-answer">
            Your answer
          </label>
          <div className="flex gap-2">
            <input
              id="operator-answer"
              className="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] px-2.5 py-1.5 text-sm"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Type your answer"
              aria-label="Answer"
            />
            <Button
              variant="approve"
              disabled={busy || !answer.trim()}
              onClick={() => {
                const t = answer.trim()
                void actions.message(t).then((ok) => {
                  if (ok) setAnswer('')
                })
              }}
            >
              Send answer
            </Button>
          </div>
        </section>
      ) : null}

      {!TERMINAL.includes(run.status) && run.status !== 'awaiting_input' ? (
        <section className="mb-5 border-b border-[var(--color-border)] pb-5">
          <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-tertiary)]">
            Guide the investigation
          </h2>
          <label className="field-label" htmlFor="opMsg">
            Additional context or direction
          </label>
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
                  const t = msg.trim()
                  void actions.message(t).then((ok) => {
                    if (ok) {
                      setMsg('')
                      toast.success('Message sent')
                    }
                  })
                }
              }}
            />
            <Button
              id="opSend"
              disabled={busy || !msg.trim()}
              onClick={() => {
                const t = msg.trim()
                void actions.message(t).then((ok) => {
                  if (ok) {
                    setMsg('')
                    toast.success('Message sent')
                  }
                })
              }}
            >
              Send
            </Button>
          </div>
        </section>
      ) : null}

      {run.result ? (
        <section className="mb-5 border-b border-[var(--color-border)] pb-5">
          <h2 className="section-eyebrow mb-3">Incident report</h2>
          <div className="activity-outcome">
            <p className="m-0 text-sm font-semibold">{report?.title || 'Investigation finished'}</p>
            <p className="mt-1 text-[13px] leading-relaxed">
              {report?.summary || 'Review the recorded outcome in the engineering record.'}
            </p>
          </div>
          <OperatorFacts display={report || undefined} />
        </section>
      ) : null}

      <Collapsible.Root
        open={techOpen || showEngineer}
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
            <ChevronDown
              className={cn(
                'size-4 transition-transform',
                (techOpen || showEngineer) && 'rotate-180',
              )}
            />
          </button>
        </Collapsible.Trigger>
        <Collapsible.Content className="mt-3 space-y-3">
          <p className="text-xs text-[var(--color-fg-secondary)]">
            Original model reasoning, diagnostic evidence, and unverified hypotheses. These are not
            operator instructions.
          </p>
          <DataView
            data={{
              proposal: pending,
              report: run.result,
              plan: run.plan,
              hypotheses: run.hypotheses,
            }}
            compact
          />
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
            <dd
              className="m-0 max-w-[14ch] truncate text-right font-mono text-[11px]"
              title={run.run_id}
            >
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
