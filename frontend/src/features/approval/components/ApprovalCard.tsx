import { ShieldAlert } from 'lucide-react'
import { useRef } from 'react'
import { OperatorFacts } from '@/components/common/OperatorFacts'
import { confidencePhrase } from '@/lib/format'
import { cn } from '@/lib/utils'
import { type ApprovalFormOptions, useApprovalForm } from '../hooks/useApprovalForm'
import { ApprovalDecision } from './ApprovalDecision'
import { ApprovalEditFields } from './ApprovalEditFields'

const NO_EVIDENCE = [
  'Structured evidence is not available. Review the engineering record before deciding.',
]

/** Operator decision card for one pending production change. */
export function ApprovalCard(props: ApprovalFormOptions) {
  const { pending } = props
  const cardRef = useRef<HTMLDivElement>(null)
  const form = useApprovalForm({ ...props, cardRef })
  const display = pending.operator
  const conf = confidencePhrase(Number(form.draft.confidence ?? form.original.confidence ?? 0))

  return (
    <div
      className={cn('approval-panel border border-[var(--color-warning-border)]')}
      ref={cardRef}
      role="region"
      aria-label="Approval required"
      aria-busy={form.locked}
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
        {(display?.evidence || NO_EVIDENCE).map((fact, index) => (
          <li key={index}>{fact}</li>
        ))}
      </ul>
      <p className="mb-4 text-xs leading-relaxed text-[var(--color-fg-secondary)]">
        {display?.summary || 'The cause has not been independently confirmed.'}
      </p>
      <h3 className="decision-label">Proposed action</h3>
      {form.error ? (
        <p
          className="mb-4 rounded-md bg-[var(--color-danger-soft)] p-3 text-sm text-[var(--color-danger)]"
          role="alert"
        >
          {form.error}
        </p>
      ) : null}
      <p
        className="m-0 mb-2 text-[16px] font-medium leading-snug text-[var(--color-fg)]"
        data-testid="approval-summary"
      >
        {display?.title || 'Review the proposed change'}
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
        onClick={form.toggleEdit}
        disabled={form.locked}
        aria-expanded={form.showEdit}
        aria-controls="approval-edit-fields"
      >
        {form.showEdit ? 'Hide edit fields' : 'Edit before approving'}
      </button>
      {form.showEdit ? (
        <ApprovalEditFields
          original={form.original}
          draft={form.draft}
          setDraft={form.setDraft}
          edited={form.edited}
          locked={form.locked}
        />
      ) : null}
      <ApprovalDecision
        feedback={form.feedback}
        setFeedback={form.setFeedback}
        submitting={form.submitting}
        locked={form.locked}
        onApprove={() => void form.approve()}
        onReject={() => void form.reject()}
      />
    </div>
  )
}
