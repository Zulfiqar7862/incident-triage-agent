import { Button } from '@/components/ui/button'

type Props = {
  feedback: string
  setFeedback: (value: string) => void
  submitting: 'approve' | 'reject' | null
  locked: boolean
  onApprove: () => void
  onReject: () => void
}

/** Approve button, optional rejection feedback, and reject button. */
export function ApprovalDecision({
  feedback,
  setFeedback,
  submitting,
  locked,
  onApprove,
  onReject,
}: Props) {
  return (
    <div className="flex flex-col gap-3">
      <Button
        id="apOk"
        variant="approve"
        disabled={locked}
        onClick={onApprove}
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
          onClick={onReject}
          className="w-full shrink-0 sm:w-auto"
          data-testid="reject-btn"
        >
          {submitting === 'reject' ? 'Rejecting…' : 'Reject'}
        </Button>
      </div>
    </div>
  )
}
