import { Check, ChevronDown, Copy, Loader2, XCircle } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { TechnicalDetails } from '@/components/common/DataView'
import { ToolArgsView, ToolOutputView } from '@/components/common/ToolOutputView'
import { humanToolName } from '@/lib/dataDisplay'
import { Button } from '@/components/ui/button'
import { humanizeKey } from '@/lib/errors'
import { cn } from '@/lib/utils'

export type ToolCardModel = {
  id: string
  name: string
  args: Record<string, unknown>
  kind?: string
  status: 'running' | 'ok' | 'error' | 'waiting'
  content?: string
  duration_ms?: number
  attempts?: number
  retryNote?: string
  truncated?: { omitted_chars?: number }
}

function summaryArgs(args: Record<string, unknown>): string {
  const prefer = ['service', 'metric', 'query', 'to_version', 'window_minutes']
  const parts: string[] = []
  for (const k of prefer) {
    if (args[k] != null && args[k] !== '') parts.push(`${humanizeKey(k)}: ${String(args[k])}`)
  }
  if (!parts.length) {
    for (const [k, v] of Object.entries(args).slice(0, 3)) {
      if (typeof v === 'object') continue
      parts.push(`${humanizeKey(k)}: ${String(v)}`)
    }
  }
  return parts.join(' · ')
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

  const tag =
    tool.status === 'running'
      ? 'Running'
      : tool.status === 'waiting'
        ? 'Waiting for you'
        : tool.status === 'error'
          ? `Error${tool.duration_ms != null ? ` · ${tool.duration_ms} ms` : ''}`
          : `Done${tool.duration_ms != null ? ` · ${tool.duration_ms} ms` : ''}${tool.attempts && tool.attempts > 1 ? ` · ${tool.attempts} tries` : ''}`

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
        tool.kind === 'write' ? 'border-[var(--color-warning-border)]' : 'border-[var(--color-border)]',
        tool.status === 'error' && 'border-[var(--color-danger)]/40',
      )}
      data-testid="tool-card"
    >
      <button
        type="button"
        className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13px] hover:bg-[var(--color-subtle)]"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {statusIcon}
        <span className="font-semibold tracking-tight">{humanToolName(tool.name)}</span>
        <span className="min-w-0 flex-1 truncate text-[12.5px] text-[var(--color-fg-tertiary)]" title={summaryArgs(tool.args)}>
          {summaryArgs(tool.args)}
        </span>
        <span
          className={cn(
            'rounded-full px-2 py-0.5 text-[11px] font-semibold',
            tool.status === 'ok' && 'bg-[var(--color-success-soft)] text-[var(--color-success)]',
            tool.status === 'error' && 'bg-[var(--color-danger-soft)] text-[var(--color-danger)]',
            tool.status === 'waiting' && 'bg-[var(--color-warning-soft)] text-[var(--color-warning)]',
            tool.status === 'running' && 'bg-[var(--color-muted)] text-[var(--color-fg-secondary)]',
          )}
        >
          {tag}
        </span>
        <ChevronDown className={cn('size-4 text-[var(--color-fg-tertiary)] transition-transform', open && 'rotate-180')} />
      </button>
      {tool.retryNote ? <div className="px-3.5 pb-2 text-xs text-[var(--color-warning)]">{tool.retryNote}</div> : null}
      {open ? (
        <div className="space-y-3 border-t border-[var(--color-border)] bg-[var(--color-subtle)]/60 px-3.5 py-3">
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-fg-tertiary)]">Inputs</span>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => copy(JSON.stringify(tool.args, null, 2), 'Inputs')}
              >
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
                    ? ` · ${tool.truncated.omitted_chars.toLocaleString()} chars trimmed for the model`
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
