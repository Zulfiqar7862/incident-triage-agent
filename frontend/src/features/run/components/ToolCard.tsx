import { Check, ChevronDown, Loader2, XCircle } from 'lucide-react'
import { useState } from 'react'
import { OperatorFacts } from '@/components/common/OperatorFacts'
import type { OperatorDisplay } from '@/types/api'
import { cn } from '@/lib/utils'

export type ToolCardModel = {
  id: string
  name: string
  args: Record<string, unknown>
  kind?: string
  title?: string
  summary?: string
  risk?: string
  operator?: OperatorDisplay | null
  status: 'running' | 'ok' | 'error' | 'waiting' | 'stopped'
  content?: string
  duration_ms?: number
  attempts?: number
  retryNote?: string
  truncated?: { omitted_chars?: number }
}

const STATUS_TAG: Record<ToolCardModel['status'], string> = {
  running: 'In progress',
  waiting: 'Proposed',
  error: 'Unavailable',
  ok: 'Checked',
  stopped: 'Not completed',
}

function StatusIcon({ status }: { status: ToolCardModel['status'] }) {
  if (status === 'running') return <Loader2 className="size-4 animate-spin" />
  if (status === 'ok') return <Check className="size-4" />
  if (status === 'error') return <XCircle className="size-4" />
  return <span className="size-2 rounded-full bg-current" />
}

function hasDetails(display?: OperatorDisplay | null): boolean {
  return Boolean(display?.fields.length || display?.evidence.length || display?.impact)
}

/** One investigation check. Expandable only when the API supplied operator facts. */
export function ToolCard({ tool }: { tool: ToolCardModel }) {
  const [open, setOpen] = useState(false)
  const expandable = hasDetails(tool.operator)
  const header = (
    <>
      <span
        className={cn(
          'mt-0.5 shrink-0',
          tool.status === 'error'
            ? 'text-[var(--color-danger)]'
            : tool.status === 'ok'
              ? 'text-[var(--color-success)]'
              : 'text-[var(--color-fg-tertiary)]',
        )}
      >
        <StatusIcon status={tool.status} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold">
          {tool.operator?.title || 'Investigation action'}
        </span>
        <span className="mt-1 block text-[13px] leading-relaxed text-[var(--color-fg-secondary)]">
          {tool.operator?.summary ||
            'The action is recorded. Detailed evidence is available in the engineering record.'}
        </span>
      </span>
      <span className="mt-0.5 text-[11px] text-[var(--color-fg-secondary)]">
        {STATUS_TAG[tool.status]}
      </span>
    </>
  )
  const rowClass = 'flex w-full items-start gap-3 py-3 text-left'
  return (
    <div className="activity-check" data-testid="tool-card">
      {expandable ? (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className={rowClass}
        >
          {header}
          <ChevronDown
            className={cn(
              'mt-0.5 size-4 shrink-0 text-[var(--color-fg-tertiary)]',
              open && 'rotate-180',
            )}
          />
        </button>
      ) : (
        <div className={cn(rowClass, 'pr-7')}>{header}</div>
      )}
      {tool.retryNote ? (
        <p className="text-xs text-[var(--color-warning)]">{tool.retryNote}</p>
      ) : null}
      {expandable && open ? (
        <div className="pb-3 pl-7">
          <OperatorFacts display={tool.operator || undefined} />
          {tool.operator?.impact ? (
            <p className="mt-2 text-xs leading-relaxed text-[var(--color-fg-secondary)]">
              {tool.operator.impact}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
