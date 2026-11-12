import { useState } from 'react'
import { Button } from '@/components/ui/button'
import type { PendingInput } from '@/types/api'
import type { RunActions } from '../api/useRunActions'

/** Answer box shown while the agent waits on an ``ask_operator`` question. */
export function OperatorAnswerForm({
  pending,
  actions,
}: {
  pending: PendingInput
  actions: RunActions
}) {
  const [answer, setAnswer] = useState('')
  return (
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
          disabled={actions.busy || !answer.trim()}
          onClick={() => {
            void actions.message(answer.trim()).then((ok) => {
              if (ok) setAnswer('')
            })
          }}
        >
          Send answer
        </Button>
      </div>
    </section>
  )
}
