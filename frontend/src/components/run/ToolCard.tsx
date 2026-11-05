import { Check, ChevronDown, Copy, Loader2, XCircle } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { TechnicalDetails } from '@/components/common/DataView'
import { ToolArgsView, ToolOutputView } from '@/components/common/ToolOutputView'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export type ToolCardModel = {
  id: string
  name: string
  args: Record<string, unknown>
  kind?: string
  /** Backend present_tool fields */
  title?: string
  summary?: string
  risk?: string
  status: 'running' | 'ok' | 'error' | 'waiting'
  content?: string
  duration_ms?: number
  attempts?: number
  retryNote?: string
  truncated?: { omitted_chars?: number }
}

function statusTag(tool: ToolCardModel): string {
  if (tool.status === 'running') return 'In progress'
  if (tool.status === 'waiting') return 'Waiting for you'
  if (tool.status === 'error') return 'Couldn’t finish'
  return 'Done'
}

export function ToolCard({ tool }: { tool: ToolCardModel }) {
  const [open, setOpen] = useState(tool.status === 'error')

  const statusIcon =
    tool.status === 'running' ? (
      <Loader2 className="size-3.5 animate-spin text-[var(--color-accent)]" />
    ) : tool.status === 'error' ? (
      <XCircle className="size-3.5 text-[var(--color-danger)]" />
    ) : tool.status === 'waiting' ? (
      <span className="size-2 rounded-full bg-[var(--color-warning)]" />
    ) : (
      <Check className="size-3.5 text-[var(--color-success)]" />
    )

  const tag = statusTag(tool)
  const headline = tool.summary || tool.title || tool.name.replaceAll('_', ' ')

  const copy = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(`${label} copied`)
    } catch {
      toast.error('Copy failed')
    }
  }

  return (
    <div
      className={cn(
        'overflow-hidden rounded-[12px] border bg-[var(--color-elevated)] shadow-sm',
        tool.kind === 'write' || tool.risk === 'high'
          ? 'border-[var(--color-warning-border)]'
          : 'border-[var(--color-border)]',
        tool.status === 'error' && 'border-[var(--color-danger)]/40',
      )}
      data-testid="tool-card"
    >
      <button
        type="button"
        className="flex w-full items-start gap-2.5 px-3.5 py-2.5 text-left text-[13px] hover:bg-[var(--color-subtle)]"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="mt-0.5 shrink-0">{statusIcon}</span>
        <span className="min-w-0 flex-1 whitespace-normal break-words font-semibold leading-snug tracking-tight" title={headline}>
          {headline}
        </span>
        <span
          className={cn(
            'shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold',
            tool.status === 'ok' && 'bg-[var(--color-success-soft)] text-[var(--color-success)]',
            tool.status === 'error' && 'bg-[var(--color-danger-soft)] text-[var(--color-danger)]',
            tool.status === 'waiting' && 'bg-[var(--color-warning-soft)] text-[var(--color-warning)]',
            tool.status === 'running' && 'bg-[var(--color-muted)] text-[var(--color-fg-secondary)]',
          )}
        >
          {tag}
        </span>
        <ChevronDown className={cn('mt-0.5 size-4 shrink-0 text-[var(--color-fg-tertiary)] transition-transform', open && 'rotate-180')} />
      </button>
      {tool.retryNote ? <div className="px-3.5 pb-2 text-xs text-[var(--color-warning)]">{tool.retryNote}</div> : null}
      {open ? (
        <div className="space-y-3 border-t border-[var(--color-border)] bg-[var(--color-subtle)]/60 px-3.5 py-3">
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-fg-tertiary)]">Inputs</span>
              <Button size="sm" variant="ghost" onClick={() => copy(JSON.stringify(tool.args, null, 2), 'Inputs')}>
                <Copy className="size-3.5" /> Copy
              </Button>
            </div>
            <ToolArgsView args={tool.args} />
          </div>
          {tool.content != null ? (
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-fg-tertiary)]">
                  Result
                  {tool.truncated?.omitted_chars
                    ? ` · ${tool.truncated.omitted_chars.toLocaleString()} characters trimmed`
                    : ''}
                </span>
                <Button size="sm" variant="ghost" onClick={() => copy(tool.content || '', 'Result')}>
                  <Copy className="size-3.5" /> Copy
                </Button>
              </div>
              <ToolOutputView toolName={tool.name} content={tool.content} />
            </div>
          ) : (
            <TechnicalDetails data={tool.args} label="Technical details" />
          )}
        </div>
      ) : null}
    </div>
  )
}
