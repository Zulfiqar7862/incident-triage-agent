import { ShieldAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { DataView, TechnicalDetails } from '@/components/common/DataView'
import { Button } from '@/components/ui/button'
import { mapError, humanizeKey } from '@/lib/errors'
import { FIELD_LABELS, confidencePhrase } from '@/lib/format'
import type { PendingApproval } from '@/lib/types'
import { cn } from '@/lib/utils'

type Props = {
  pending: PendingApproval
  operator: string
  onApprove: (args: Record<string, unknown>) => Promise<void>
  onReject: (feedback: string) => Promise<void>
  busy?: boolean
}

const EDITABLE = ['service', 'to_version', 'reason', 'confidence'] as const

export function ApprovalCard({ pending, operator, onApprove, onReject, busy }: Props) {
  const original = pending.args
  const [draft, setDraft] = useState<Record<string, unknown>>(() => ({ ...original }))
  const [feedback, setFeedback] = useState('')
  const [showEdit, setShowEdit] = useState(false)
  const [submitting, setSubmitting] = useState<'approve' | 'reject' | null>(null)

  useEffect(() => {
    setDraft({ ...pending.args })
    setShowEdit(false)
    setFeedback('')
    setSubmitting(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending.tool_call_id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'TEXTAREA' || tag === 'INPUT') return
      if (busy || submitting) return
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
  }, [draft, feedback, operator, pending, busy, submitting])

  const conf = confidencePhrase(Number(draft.confidence ?? original.confidence ?? 0))
  const edited = useMemo(() => JSON.stringify(draft) !== JSON.stringify(original), [draft, original])
  const reason = String(draft.reason || original.reason || '')
  // Prefer backend summary/title; never invent tool sentences on the client.
  const summary =
    pending.summary ||
    pending.title ||
    `Production change: ${pending.tool.replaceAll('_', ' ')}`

  const locked = Boolean(busy || submitting || pending.executing)

  async function handleApprove() {
    if (locked) return
    if (!operator.trim()) {
      toast.error('Enter your name first — approvals are recorded for the audit trail.')
      return
    }
    setSubmitting('approve')
    try {
      await onApprove(draft)
      toast.success(edited ? 'Approved with your edits' : 'Approved — applying the change')
    } catch (e) {
      const f = mapError(e)
      toast.error(`${f.title} — ${f.explanation}`)
      setSubmitting(null)
    }
  }

  async function handleReject() {
    if (locked) return
    setSubmitting('reject')
    try {
      await onReject(feedback)
      toast.message('Rejected — feedback sent')
    } catch (e) {
      const f = mapError(e)
      toast.error(`${f.title} — ${f.explanation}`)
      setSubmitting(null)
    }
  }

  const displayArgs = Object.fromEntries(
    Object.entries(draft).filter(([k]) => !['reason', 'confidence'].includes(k)),
  )

  return (
    <div
      className={cn(
        'animate-attention rounded-[14px] border border-[var(--color-warning-border)] bg-[var(--color-warning-soft)] p-5 shadow-sm',
      )}
      role="region"
      aria-label="Approval required"
      data-testid="approval-card"
    >
      <div className="mb-3 flex flex-wrap items-center gap-2 text-[var(--color-warning)]">
        <ShieldAlert className="size-4 shrink-0" />
        <h2 className="m-0 text-sm font-semibold tracking-tight">Needs your approval</h2>
        {pending.risk === 'high' ? (
          <span className="rounded-full bg-[var(--color-danger-soft)] px-2 py-0.5 text-[11px] font-semibold text-[var(--color-danger)]">
            High risk
          </span>
        ) : null}
      </div>
      <p className="m-0 mb-2 text-[15px] font-medium leading-snug text-[var(--color-fg)]" data-testid="approval-summary">
        {summary}
      </p>
      {reason ? <p className="m-0 mb-3 text-sm leading-relaxed text-[var(--color-fg-secondary)]">{reason}</p> : null}
      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <span>
          Confidence: <b>{conf.percent}%</b>
          <span className="text-[var(--color-fg-secondary)]"> — {conf.phrase}</span>
        </span>
      </div>

      <div className="mb-3 rounded-[10px] border border-[var(--color-border)] bg-[var(--color-elevated)] p-3">
        <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-fg-tertiary)]">
          Proposed change
        </div>
        <DataView data={displayArgs} compact />
        <TechnicalDetails data={{ tool: pending.tool, ...draft }} label="Technical details" />
      </div>

      <button
        type="button"
        className="mb-3 text-xs font-medium text-[var(--color-accent)] underline-offset-2 hover:underline"
        onClick={() => setShowEdit((v) => !v)}
        disabled={locked}
      >
        {showEdit ? 'Hide edit fields' : 'Edit before approving'}
      </button>

      {showEdit ? (
        <div className="mb-3 space-y-2 rounded-[10px] border border-[var(--color-border)] bg-[var(--color-elevated)] p-3" data-testid="args-diff">
          {EDITABLE.filter((k) => k in original || k in draft).map((key) => (
            <label key={key} className="block text-xs">
              <span className="mb-1 block font-medium text-[var(--color-fg-secondary)]">
                {FIELD_LABELS[key] || humanizeKey(key)}
              </span>
              {key === 'reason' ? (
                <textarea
                  className="w-full min-h-[72px] resize-y rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] px-2.5 py-1.5 text-sm"
                  value={String(draft[key] ?? '')}
                  onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                  disabled={locked}
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
                  disabled={locked}
                />
              ) : (
                <input
                  className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] px-2.5 py-1.5 text-sm"
                  value={String(draft[key] ?? '')}
                  onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                  disabled={locked}
                />
              )}
            </label>
          ))}
          {edited ? <p className="m-0 text-[11px] text-[var(--color-warning)]">Edits will be recorded in the audit trail.</p> : null}
        </div>
      ) : null}

      <div className="flex flex-col gap-3">
        <Button
          id="apOk"
          variant="approve"
          disabled={locked}
          onClick={() => void handleApprove()}
          className="w-full"
          data-testid="approve-btn"
        >
          {submitting === 'approve' ? 'Approving…' : 'Approve fix'}
        </Button>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
          <input
            id="apFb"
            className="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] px-2.5 py-1.5 text-sm"
            placeholder="Why are you rejecting? (optional)"
            aria-label="Rejection feedback"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            disabled={locked}
          />
          <Button
            id="apNo"
            variant="danger"
            disabled={locked}
            onClick={() => void handleReject()}
            className="w-full shrink-0 sm:w-auto"
            data-testid="reject-btn"
          >
            {submitting === 'reject' ? 'Rejecting…' : 'Reject'}
          </Button>
        </div>
      </div>
    </div>
  )
}
