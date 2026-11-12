import { useState } from 'react'

const MAX_STRING = 160

/** Long text clipped to a readable length with a Show more / Show less toggle. */
export function Truncated({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  if (text.length <= MAX_STRING) return <span className="break-words">{text}</span>
  return (
    <span className="break-words">
      {open ? text : `${text.slice(0, MAX_STRING)}…`}{' '}
      <button
        type="button"
        className="text-[var(--color-accent)] underline-offset-2 hover:underline"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? 'Show less' : 'Show more'}
      </button>
    </span>
  )
}
