import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import type { RunActions } from '../api/useRunActions'

/** Free-text guidance queued for the agent's next step. */
export function GuidanceForm({ actions }: { actions: RunActions }) {
  const [msg, setMsg] = useState('')
  const send = () => {
    const text = msg.trim()
    if (!text) return
    void actions.message(text).then((ok) => {
      if (ok) {
        setMsg('')
        toast.success('Message sent')
      }
    })
  }
  return (
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
            if (e.key === 'Enter') send()
          }}
        />
        <Button id="opSend" disabled={actions.busy || !msg.trim()} onClick={send}>
          Send
        </Button>
      </div>
    </section>
  )
}
