import { type RefObject, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { mapError } from '@/lib/errors'
import type { PendingApproval } from '@/types/api'

export type ApprovalFormOptions = {
  pending: PendingApproval
  operator: string
  onApprove: (args: Record<string, unknown>) => Promise<void>
  onReject: (feedback: string) => Promise<void>
  busy?: boolean
}

type FormOptions = ApprovalFormOptions & {
  /** The card element; keyboard shortcuts apply only when focus is inside it. */
  cardRef: RefObject<HTMLDivElement | null>
}

type Submitting = 'approve' | 'reject' | null

/**
 * State and actions behind the approval card: the editable draft, rejection
 * feedback, submit state, and the A / R keyboard shortcuts scoped to the card.
 */
export function useApprovalForm({
  pending,
  operator,
  onApprove,
  onReject,
  busy,
  cardRef,
}: FormOptions) {
  const original = pending.args
  const [error, setError] = useState('')
  const [draft, setDraft] = useState<Record<string, unknown>>(() => ({ ...original }))
  const [feedback, setFeedback] = useState('')
  const [showEdit, setShowEdit] = useState(false)
  const [submitting, setSubmitting] = useState<Submitting>(null)

  useEffect(() => {
    setError('')
    setDraft({ ...pending.args })
    setShowEdit(false)
    setFeedback('')
    setSubmitting(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending.tool_call_id])

  const edited = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(original),
    [draft, original],
  )
  const locked = Boolean(busy || submitting || pending.executing)

  async function approve() {
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

  async function reject() {
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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (!(target instanceof HTMLElement) || !cardRef.current?.contains(target)) return
      if (e.ctrlKey || e.metaKey || e.altKey || target.isContentEditable) return
      if (['TEXTAREA', 'INPUT', 'SELECT'].includes(target.tagName)) return
      if (busy || submitting) return
      if (e.key === 'a' || e.key === 'A') {
        e.preventDefault()
        void approve()
      }
      if (e.key === 'r' || e.key === 'R') {
        e.preventDefault()
        void reject()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, feedback, operator, pending, busy, submitting])

  return {
    original,
    draft,
    setDraft,
    feedback,
    setFeedback,
    showEdit,
    toggleEdit: () => setShowEdit((v) => !v),
    submitting,
    error,
    edited,
    locked,
    approve,
    reject,
  }
}
