import { ShieldAlert } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { OperatorFacts } from './OperatorFacts'
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
  const cardRef = useRef<HTMLDivElement>(null)
  const [error, setError] = useState('')
  const original = pending.args
  const [draft, setDraft] = useState<Record<string, unknown>>(() => ({ ...original }))
  const [feedback, setFeedback] = useState('')
  const [showEdit, setShowEdit] = useState(false)
  const [submitting, setSubmitting] = useState<'approve' | 'reject' | null>(null)

  useEffect(() => {
    setError('')
    setDraft({ ...pending.args })
    setShowEdit(false)
    setFeedback('')
    setSubmitting(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending.tool_call_id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (!(target instanceof HTMLElement) || !cardRef.current?.contains(target)) return
      if (e.ctrlKey || e.metaKey || e.altKey || target.isContentEditable) return
      if (['TEXTAREA', 'INPUT', 'SELECT'].includes(target.tagName)) return
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
  const edited = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(original),
    [draft, original],
  )
  const display = pending.operator
  const summary = display?.title || 'Review the proposed change'

  const locked = Boolean(busy || submitting || pending.executing)

  async function handleApprove() {
    if (locked) return
    if (!operator.trim()) {
      setError(
        'Enter your name in the Operator field above. Approvals are recorded for the audit trail.',
      )
      document.getElementById('operator')?.focus()
      return
    }
    setError('')
    setSubmitting('approve')
    try {
      await onApprove(draft)
      toast.success(edited ? 'Approved with your edits' : 'Approved — applying the change')
    } catch (e) {
      const f = mapError(e)
      setError(`${f.title} — ${f.explanation}`)
      setSubmitting(null)
    }
  }

  async function handleReject() {
    if (locked) return
    setError('')
    setSubmitting('reject')
    try {
      await onReject(feedback)
      toast.message('Rejected — feedback sent')
    } catch (e) {
      const f = mapError(e)
      setError(`${f.title} — ${f.explanation}`)
      setSubmitting(null)
    }
  }

  return (
    <div
      className={cn('approval-panel border border-[var(--color-warning-border)]')}
      ref={cardRef}
      role="region"
      aria-label="Approval required"
      aria-busy={locked}
      data-testid="approval-card"
    >
      <div className="mb-3 flex flex-wrap items-center gap-2 text-[var(--color-warning)]">
        <ShieldAlert className="size-5 shrink-0" aria-hidden />
        <h2 className="m-0 text-sm font-semibold tracking-tight">Review proposed change</h2>
        {pending.risk === 'high' ? (
          <span className="rounded-full bg-[var(--color-danger-soft)] px-2 py-0.5 text-[11px] font-semibold text-[var(--color-danger)]">
            High risk
          </span>
        ) : null}
      </div>
      <p className="approval-notice">Nothing changes until you approve.</p>
      <h3 className="decision-label">Evidence reviewed</h3>
      <ul className="operator-evidence">
        {(
          display?.evidence || [
            'Structured evidence is not available. Review the engineering record before deciding.',
          ]
        ).map((fact, index) => (
          <li key={index}>{fact}</li>
        ))}
      </ul>
      <p className="mb-4 text-xs leading-relaxed text-[var(--color-fg-secondary)]">
        {display?.summary || 'The cause has not been independently confirmed.'}
      </p>
      <h3 className="decision-label">Proposed action</h3>
      {error ? (
        <p
          className="mb-4 rounded-md bg-[var(--color-danger-soft)] p-3 text-sm text-[var(--color-danger)]"
          role="alert"
        >
          {error}
        </p>
      ) : null}
      <p
        className="m-0 mb-2 text-[16px] font-medium leading-snug text-[var(--color-fg)]"
        data-testid="approval-summary"
      >
        {summary}
      </p>
      <OperatorFacts display={display} evidence={false} />
      <h3 className="decision-label mt-4">Impact &amp; risk</h3>
      <p className="mb-3 text-[13px] leading-relaxed text-[var(--color-fg-secondary)]">
        {display?.impact || 'This changes the running service. Confirm its scope before approving.'}
      </p>
      <p className="mb-4 text-xs text-[var(--color-fg-secondary)]">
        Agent confidence: <b>{conf.percent}%</b> (not a guarantee).
      </p>

      <button
        type="button"
        className="mb-3 text-xs font-medium text-[var(--color-accent)] underline-offset-2 hover:underline"
        onClick={() => setShowEdit((v) => !v)}
        disabled={locked}
        aria-expanded={showEdit}
        aria-controls="approval-edit-fields"
      >
        {showEdit ? 'Hide edit fields' : 'Edit before approving'}
      </button>

      {showEdit ? (
        <div
          className="mb-3 space-y-2 rounded-[10px] border border-[var(--color-border)] bg-[var(--color-elevated)] p-3"
          id="approval-edit-fields"
          data-testid="args-diff"
        >
          {EDITABLE.filter((k) => k in original || k in draft).map((key) => (
            <label key={key} className="block text-xs" htmlFor={`approval-${key}`}>
              <span
                id={`approval-${key}-label`}
                className="mb-1 block font-medium text-[var(--color-fg-secondary)]"
              >
                {FIELD_LABELS[key] || humanizeKey(key)}
              </span>
              {key === 'reason' ? (
                <textarea
                  id={`approval-${key}`}
                  aria-labelledby={`approval-${key}-label`}
                  className="w-full min-h-[72px] resize-y rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] px-2.5 py-1.5 text-sm"
                  value={String(
                    key === 'reason' && draft.reason === original.reason ? '' : (draft[key] ?? ''),
                  )}
                  placeholder="Add your reason (original reasoning remains in the engineering record)"
                  onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                  disabled={locked}
                />
              ) : key === 'confidence' ? (
                <input
                  id={`approval-${key}`}
                  aria-labelledby={`approval-${key}-label`}
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
                  id={`approval-${key}`}
                  aria-labelledby={`approval-${key}-label`}
                  className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] px-2.5 py-1.5 text-sm"
                  value={String(draft[key] ?? '')}
                  onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                  disabled={locked}
                />
              )}
            </label>
          ))}
          {edited ? (
            <p className="m-0 text-[11px] text-[var(--color-warning)]">
              Edits will be recorded in the audit trail.
            </p>
          ) : null}
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
        <label className="field-label mb-0" htmlFor="apFb">
          Rejection feedback <span className="font-normal">(optional)</span>
        </label>
        <div className="flex flex-col gap-2">
          <input
            id="apFb"
            className="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] px-2.5 py-1.5 text-sm"
            placeholder="Explain what should change"
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
