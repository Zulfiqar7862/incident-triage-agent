import { Check, ChevronDown, Copy, Loader2, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { argStr, prettyJson } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useUiStore } from '@/store/uiStore'

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

export function ToolCard({ tool }: { tool: ToolCardModel }) {
  const [open, setOpen] = useState(tool.status === 'error')
  const theme = useUiStore((s) => s.theme)
  const isDark =
    theme === 'dark' ||
    (theme === 'system' && typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches)

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
      ? 'running'
      : tool.status === 'waiting'
        ? 'waiting for you'
        : tool.status === 'error'
          ? `error${tool.duration_ms != null ? `, ${tool.duration_ms} ms` : ''}`
          : `ok${tool.duration_ms != null ? `, ${tool.duration_ms} ms` : ''}${tool.attempts && tool.attempts > 1 ? `, ${tool.attempts} tries` : ''}`

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
        'overflow-hidden rounded-[10px] border bg-[var(--color-elevated)] shadow-sm',
        tool.kind === 'write' ? 'border-[var(--color-warning-border)]' : 'border-[var(--color-border)]',
        tool.status === 'error' && 'border-[var(--color-danger)]',
      )}
      data-testid="tool-card"
    >
      <button
        type="button"
        className="flex w-full items-center gap-2.5 px-3 py-2 text-left font-mono text-[12.5px] hover:bg-[var(--color-subtle)]"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {statusIcon}
        <span className="font-semibold">{tool.name}</span>
        <span className="min-w-0 flex-1 truncate text-[var(--color-fg-tertiary)]" title={argStr(tool.args)}>
          {argStr(tool.args)}
        </span>
        <span
          className={cn(
            'rounded-full px-2 text-[11px] font-semibold',
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
      {tool.retryNote ? <div className="px-3 pb-1 text-xs text-[var(--color-warning)]">{tool.retryNote}</div> : null}
      {open ? (
        <div className="border-t border-[var(--color-border)] bg-[var(--color-subtle)]">
          <div className="flex items-center justify-between px-3 pt-2">
            <span className="text-xs text-[var(--color-fg-tertiary)]">Arguments</span>
            <Button size="sm" variant="ghost" onClick={() => copy(prettyJson(tool.args), 'Args')}>
              <Copy className="size-3.5" /> Copy
            </Button>
          </div>
          <SyntaxHighlighter
            language="json"
            style={isDark ? oneDark : oneLight}
            customStyle={{ margin: 0, background: 'transparent', fontSize: 11.5, maxHeight: 220 }}
          >
            {prettyJson(tool.args)}
          </SyntaxHighlighter>
          {tool.content != null ? (
            <>
              <div className="flex items-center justify-between border-t border-[var(--color-border)] px-3 pt-2">
                <span className="text-xs text-[var(--color-fg-tertiary)]">
                  Output ({tool.content.length.toLocaleString()} chars
                  {tool.truncated?.omitted_chars
                    ? `, ${tool.truncated.omitted_chars.toLocaleString()} trimmed for model`
                    : ''}
                  )
                </span>
                <Button size="sm" variant="ghost" onClick={() => copy(tool.content || '', 'Output')}>
                  <Copy className="size-3.5" /> Copy
                </Button>
              </div>
              <SyntaxHighlighter
                language="json"
                style={isDark ? oneDark : oneLight}
                customStyle={{ margin: 0, background: 'transparent', fontSize: 11.5, maxHeight: 360 }}
              >
                {(() => {
                  try {
                    return prettyJson(JSON.parse(tool.content))
                  } catch {
                    return tool.content
                  }
                })()}
              </SyntaxHighlighter>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
