import { Check, ChevronDown, Loader2, XCircle } from 'lucide-react'
import { useState } from 'react'
import { OperatorFacts } from './OperatorFacts'
import type { OperatorDisplay } from '@/lib/types'
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

export function ToolCard({ tool }: { tool: ToolCardModel }) {
  const [open, setOpen] = useState(false)
  const tag = {
    running: 'In progress',
    waiting: 'Proposed',
    error: 'Unavailable',
    ok: 'Checked',
    stopped: 'Not completed',
  }[tool.status]
  const icon =
    tool.status === 'running' ? (
      <Loader2 className="size-4 animate-spin" />
    ) : tool.status === 'ok' ? (
      <Check className="size-4" />
    ) : tool.status === 'error' ? (
      <XCircle className="size-4" />
    ) : (
      <span className="size-2 rounded-full bg-current" />
    )
  return (
    <div className="activity-check" data-testid="tool-card">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-start gap-3 py-3 text-left"
      >
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
          {icon}
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
        <span className="mt-0.5 text-[11px] text-[var(--color-fg-secondary)]">{tag}</span>
        <ChevronDown
          className={cn(
            'mt-0.5 size-4 shrink-0 text-[var(--color-fg-tertiary)]',
            open && 'rotate-180',
          )}
        />
      </button>
      {tool.retryNote ? (
        <p className="text-xs text-[var(--color-warning)]">{tool.retryNote}</p>
      ) : null}
      {open ? (
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
