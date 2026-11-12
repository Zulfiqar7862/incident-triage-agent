import { ArrowDown } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { ToolCard, type ToolCardModel } from './ToolCard'
import type { AgentEvent, RunStatus } from '@/lib/types'

function buildTools(events: AgentEvent[], status?: RunStatus) {
  const tools = new Map<string, ToolCardModel>()
  for (const event of events) {
    const p = event.payload
    const id = String(p.id || '')
    if (event.type === 'tool.call')
      tools.set(id, {
        id,
        name: String(p.name || ''),
        args: {},
        kind: String(p.kind || ''),
        operator: event.operator,
        status: 'running',
      })
    if (event.type === 'tool.result') {
      const prior = tools.get(id)
      tools.set(id, {
        id,
        name: String(p.name || ''),
        args: {},
        ...prior,
        retryNote: undefined,
        operator: event.operator,
        status:
          event.operator?.state === 'rejected' || event.operator?.state === 'unverified'
            ? 'stopped'
            : p.is_error
              ? 'error'
              : 'ok',
      })
    }
    if (event.type === 'tool.retry') {
      const tool = tools.get(id)
      if (tool) tool.retryNote = 'This check is being retried.'
    }
  }
  if (status && status !== 'running' && status !== 'queued')
    for (const tool of tools.values()) if (tool.status === 'running') tool.status = 'stopped'
  return tools
}

export function Timeline({ events, status }: { events: AgentEvent[]; status?: RunStatus }) {
  const colRef = useRef<HTMLDivElement>(null)
  const [pinned, setPinned] = useState(true)
  const tools = useMemo(() => buildTools(events, status), [events, status])
  useEffect(() => {
    const el = colRef.current
    if (el && pinned) el.scrollTop = el.scrollHeight
  }, [events.length, pinned, tools])

  const seen = new Set<string>()
  const items: ReactNode[] = []
  for (const event of events) {
    if (event.type === 'tool.call' || event.type === 'tool.result') {
      const id = String(event.payload.id)
      const tool = tools.get(id)
      if (!tool || seen.has(id) || !tool.operator) continue
      // A proposed write belongs in the decision panel, not a duplicate checkpoint.
      if (tool.kind === 'write' && (tool.status === 'running' || tool.status === 'stopped'))
        continue
      seen.add(id)
      items.push(<ToolCard key={`tool-${id}`} tool={tool} />)
      continue
    }
    if (!event.operator || event.type === 'tool.retry') continue
    const display = event.operator
    const finished = event.type === 'run.finished'
    items.push(
      <div key={event.seq} className={finished ? 'outcome activity-outcome' : 'activity-note'}>
        <p className="m-0 text-sm font-semibold">{display.title}</p>
        {display.summary ? (
          <p className="m-0 mt-1 text-[13px] leading-relaxed text-[var(--color-fg-secondary)]">
            {display.summary}
          </p>
        ) : null}
      </div>,
    )
  }
  return (
    <div className="activity-stream relative flex min-h-0 flex-1 flex-col">
      <div className="activity-heading">
        <h2 className="text-sm font-semibold">What was checked</h2>
        <span className="text-xs text-[var(--color-fg-secondary)]">
          {pinned ? 'Following latest' : 'Reading earlier activity'}
        </span>
      </div>
      <div
        ref={colRef}
        className="activity-body min-h-0 flex-1 overflow-auto"
        id="traceCol"
        tabIndex={0}
        aria-label="Investigation activity"
        data-testid="timeline"
        onScroll={() => {
          const el = colRef.current
          if (el) setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 120)
        }}
      >
        {items.length ? (
          items
        ) : (
          <p className="text-sm text-[var(--color-fg-secondary)]">
            Checks will appear here as the investigation progresses.
          </p>
        )}
      </div>
      {!pinned ? (
        <Button
          className="absolute bottom-4 left-1/2 z-10 -translate-x-1/2 shadow-md"
          variant="primary"
          size="sm"
          onClick={() => {
            setPinned(true)
            const el = colRef.current
            if (el) el.scrollTop = el.scrollHeight
          }}
        >
          <ArrowDown className="size-3.5" aria-hidden /> Jump to latest
        </Button>
      ) : null}
    </div>
  )
}
