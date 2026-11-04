import { ShieldAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { DataView, TechnicalDetails } from '@/components/common/DataView'
import { Button } from '@/components/ui/button'
import { humanizeKey, mapError } from '@/lib/errors'
import type { PendingApproval } from '@/lib/types'
import { cn } from '@/lib/utils'

type Props = {
  pending: PendingApproval
  operator: string
  onApprove: (args: Record<string, unknown>) => Promise<void>
  onReject: (feedback: string) => Promise<void>
  busy?: boolean
}

function riskLabel(confidence: number) {
  if (confidence >= 0.85) return { label: 'Lower risk', tone: 'text-[var(--color-success)]' }
  if (confidence >= 0.6) return { label: 'Moderate risk', tone: 'text-[var(--color-warning)]' }
  return { label: 'Higher risk', tone: 'text-[var(--color-danger)]' }
}

const EDITABLE = ['service', 'to_version', 'reason', 'confidence'] as const

export function ApprovalCard({ pending, operator, onApprove, onReject, busy }: Props) {
  const original = pending.args
  const [draft, setDraft] = useState<Record<string, unknown>>(() => ({ ...original }))
  const [feedback, setFeedback] = useState('')
  const [showEdit, setShowEdit] = useState(false)

  useEffect(() => {
    setDraft({ ...pending.args })
    setShowEdit(false)
    // Reset when a new approval request arrives
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending.tool_call_id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'TEXTAREA' || tag === 'INPUT') return
      if (e.key === 'a' || e.key === 'A') {
        e.preventDefault()
        void handleApprove()
      }
      if (e.key === 'r' || e.key === 'R') {
        e.preventDefault()
        void handleReject()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, feedback, operator, pending])

  const conf = Math.round(Number(draft.confidence ?? original.confidence ?? 0) * 100)
  const risk = riskLabel(Number(draft.confidence ?? original.confidence ?? 0))
  const edited = useMemo(() => JSON.stringify(draft) !== JSON.stringify(original), [draft, original])
  const service = String(draft.service || original.service || '')
  const reason = String(draft.reason || original.reason || '')

  async function handleApprove() {
    if (!operator.trim()) {
      toast.error('Enter your name first — approvals are recorded in the audit log.')
      return
    }
    try {
      await onApprove(draft)
      toast.success(edited ? 'Approved with edited arguments' : 'Approved — change is applying')
    } catch (e) {
      const f = mapError(e)
      toast.error(`${f.title} — ${f.explanation}`)
    }
  }

  async function handleReject() {
    try {
      await onReject(feedback)
      toast.message('Rejected — feedback sent to the agent')
    } catch (e) {
      const f = mapError(e)
      toast.error(`${f.title} — ${f.explanation}`)
    }
  }

  const displayArgs = Object.fromEntries(
    Object.entries(draft).filter(([k]) => !['reason', 'confidence'].includes(k)),
  )

  return (
    <div
      className={cn(
        'animate-attention rounded-[14px] border border-[var(--color-warning-border)] bg-[var(--color-warning-soft)] p-4 shadow-sm',
      )}
      role="region"
      aria-label="Approval required"
      data-testid="approval-card"
    >
      <div className="mb-2 flex items-center gap-2 text-[var(--color-warning)]">
        <ShieldAlert className="size-4" />
        <h2 className="m-0 text-sm font-semibold tracking-tight">Approve a production change</h2>
      </div>
      <p className="m-0 mb-1.5 text-sm leading-relaxed">
        The agent wants to run <span className="font-semibold">{humanizeKey(pending.tool)}</span>
        {service ? (
          <>
            {' '}
            on <b>{service}</b>
          </>
        ) : null}
        .
      </p>
      {reason ? <p className="m-0 mb-3 text-xs leading-relaxed text-[var(--color-fg-secondary)]">{reason}</p> : null}
      <div className="mb-1 flex items-center justify-between text-xs">
        <span>
          Agent confidence: <b>{conf}%</b>
        </span>
        <span className={cn('font-semibold', risk.tone)}>{risk.label}</span>
      </div>
      <div
        className="mb-3 h-1.5 overflow-hidden rounded-sm bg-[var(--color-elevated)]"
        role="meter"
        aria-valuenow={conf}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <i className="block h-full rounded-sm bg-[var(--color-warning)]" style={{ width: `${conf}%` }} />
      </div>

      <div className="mb-3 rounded-[10px] border border-[var(--color-border)] bg-[var(--color-elevated)] p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-fg-tertiary)]">Proposed change</div>
        <DataView data={displayArgs} compact />
        <TechnicalDetails data={original} />
      </div>

      <button
        type="button"
        className="mb-2 text-xs font-medium text-[var(--color-accent)] underline-offset-2 hover:underline"
        onClick={() => setShowEdit((v) => !v)}
      >
        {showEdit ? 'Hide edit fields' : 'Edit before approving'}
      </button>

      {showEdit ? (
        <div className="mb-3 space-y-2 rounded-[10px] border border-[var(--color-border)] bg-[var(--color-elevated)] p-3" data-testid="args-diff">
          {EDITABLE.filter((k) => k in original || k in draft).map((key) => (
            <label key={key} className="block text-xs">
              <span className="mb-1 block font-medium text-[var(--color-fg-secondary)]">{humanizeKey(key)}</span>
              {key === 'reason' ? (
                <textarea
                  className="w-full min-h-[72px] resize-y rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] px-2.5 py-1.5 text-sm"
                  value={String(draft[key] ?? '')}
                  onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                />
              ) : key === 'confidence' ? (
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] px-2.5 py-1.5 text-sm"
                  value={Number(draft[key] ?? 0)}
                  onChange={(e) => setDraft((d) => ({ ...d, [key]: Number(e.target.value) }))}
                />
              ) : (
                <input
                  className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] px-2.5 py-1.5 text-sm"
                  value={String(draft[key] ?? '')}
                  onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                />
              )}
            </label>
          ))}
          {edited ? <p className="m-0 text-[11px] text-[var(--color-warning)]">Edits will be recorded in the audit log.</p> : null}
        </div>
      ) : null}

      <Button id="apOk" variant="approve" disabled={busy} onClick={() => void handleApprove()} className="w-full sm:w-auto">
        Approve and run <kbd className="ml-2 rounded bg-black/15 px-1.5 text-[10px]">A</kbd>
      </Button>
      <div className="mt-2.5 flex gap-1.5">
        <input
          id="apFb"
          className="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] px-2.5 py-1.5 text-sm"
          placeholder="Reason for rejecting (sent to the agent)"
          aria-label="Rejection feedback"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
        />
        <Button id="apNo" variant="danger" disabled={busy} onClick={() => void handleReject()}>
          Reject <kbd className="ml-1 rounded bg-black/10 px-1 text-[10px]">R</kbd>
        </Button>
      </div>
      <p className="mt-2 text-[11px] text-[var(--color-fg-tertiary)]">
        Keyboard: <kbd>A</kbd> approve · <kbd>R</kbd> reject (when not typing)
      </p>
    </div>
  )
}
