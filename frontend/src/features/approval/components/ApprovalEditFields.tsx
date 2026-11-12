import type { Dispatch, SetStateAction } from 'react'
import { humanizeKey } from '@/lib/errors'
import { FIELD_LABELS } from '@/lib/format'

const EDITABLE = ['service', 'to_version', 'reason', 'confidence'] as const
const INPUT_CLASS =
  'w-full rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] px-2.5 py-1.5 text-sm'

type Props = {
  original: Record<string, unknown>
  draft: Record<string, unknown>
  setDraft: Dispatch<SetStateAction<Record<string, unknown>>>
  edited: boolean
  locked: boolean
}

/** Editable arguments of a proposed change; edits are recorded in the audit trail. */
export function ApprovalEditFields({ original, draft, setDraft, edited, locked }: Props) {
  const set = (key: string, value: unknown) => setDraft((d) => ({ ...d, [key]: value }))
  return (
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
              className={`${INPUT_CLASS} min-h-[72px] resize-y`}
              value={String(draft.reason === original.reason ? '' : (draft[key] ?? ''))}
              placeholder="Add your reason (original reasoning remains in the engineering record)"
              onChange={(e) => set(key, e.target.value)}
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
              className={INPUT_CLASS}
              value={Number(draft[key] ?? 0)}
              onChange={(e) => set(key, Number(e.target.value))}
              disabled={locked}
            />
          ) : (
            <input
              id={`approval-${key}`}
              aria-labelledby={`approval-${key}-label`}
              className={INPUT_CLASS}
              value={String(draft[key] ?? '')}
              onChange={(e) => set(key, e.target.value)}
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
  )
}
