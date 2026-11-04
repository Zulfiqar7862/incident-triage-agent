import { ArrowDown } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { ToolCard, type ToolCardModel } from '@/components/run/ToolCard'
import { money, num } from '@/lib/format'
import type { AgentEvent } from '@/lib/types'

function buildTools(events: AgentEvent[]): Map<string, ToolCardModel> {
  const map = new Map<string, ToolCardModel>()
  for (const ev of events) {
    const p = ev.payload || {}
    if (ev.type === 'tool.call') {
      map.set(String(p.id), {
        id: String(p.id),
        name: String(p.name || ''),
        args: (p.args as Record<string, unknown>) || {},
        kind: p.kind as string | undefined,
        status: p.kind === 'write' ? 'waiting' : 'running',
      })
    } else if (ev.type === 'tool.retry') {
      const t = map.get(String(p.id))
      if (t) t.retryNote = `Attempt ${p.attempt} failed: ${p.error}. Retrying in ${p.retry_in_s}s.`
    } else if (ev.type === 'tool.result') {
      const id = String(p.id)
      const existing =
        map.get(id) ||
        ({
          id,
          name: String(p.name || 'tool'),
          args: {},
          status: 'ok',
        } satisfies ToolCardModel)
      existing.status = p.is_error ? 'error' : 'ok'
      existing.content = String(p.content ?? '')
      existing.duration_ms = p.duration_ms as number | undefined
      existing.attempts = p.attempts as number | undefined
      existing.truncated = p.truncated as ToolCardModel['truncated']
      map.set(id, existing)
    } else if (ev.type === 'approval.requested') {
      const t = map.get(String(p.tool_call_id))
      if (t) t.status = 'waiting'
    }
  }
  return map
}

function labelFor(ev: AgentEvent): string {
  const p = ev.payload || {}
  switch (ev.type) {
    case 'operator.message':
      return `${p.actor || 'Operator'} said: “${p.text}”${p.queued ? ' (queued for next step)' : ''}`
    case 'operator.control':
      return `Operator asked to ${p.action}`
    case 'memory.update':
      return `Updated working memory: ${((p.changed as string[]) || []).join(', ') || 'nothing'}`
    case 'memory.saved':
      return 'Saved a short summary to long-term memory'
    case 'context.compacted':
      return `Compacted ${p.dropped_groups} oldest step(s) to stay under ${num(p.budget as number)} tokens`
    case 'llm.retry':
      return `Model call failed (${p.error}). Retrying in ${p.retry_in_s}s.`
    default:
      return ev.type
  }
}

function renderEvent(ev: AgentEvent): ReactNode {
  const p = ev.payload || {}
  switch (ev.type) {
    case 'run.created':
      return (
        <div className="text-[13px] text-[var(--color-fg-secondary)]">
          Run started with <b className="text-[var(--color-fg)]">{String(p.model)}</b>
        </div>
      )
    case 'memory.recalled':
      return (
        <div className="text-[13px] text-[var(--color-fg-secondary)]">
          Recalled {(p.memories as unknown[])?.length || 0} past incident(s)
        </div>
      )
    case 'run.status':
      return (
        <div className="text-[13px] text-[var(--color-fg-secondary)]">
          Status: <b className="text-[var(--color-fg)]">{String(p.status).replaceAll('_', ' ')}</b>
          {p.reason ? `. ${String(p.reason)}` : ''}
        </div>
      )
    case 'llm.call':
    case 'gen_ai.span': {
      const c = (p.context || {}) as Record<string, number>
      return (
        <div className="rounded-[10px] border border-[var(--color-border)] bg-[var(--color-elevated)] px-3.5 py-2.5 text-[13px] text-[var(--color-fg-secondary)]">
          <div className="mb-1 text-xs font-semibold text-[var(--color-fg-tertiary)]">Model call</div>
          <div className="flex flex-wrap gap-x-3.5 gap-y-1 text-[12.5px]">
            <span>{num(p.input_tokens as number)} tokens in</span>
            <span>{num(p.output_tokens as number)} out</span>
            <span>{num(p.latency_ms as number)} ms</span>
            <span>{money(p.cost_usd as number)}</span>
            {c.total_tokens != null ? (
              <span>
                context {num(c.total_tokens)}/{num(c.budget)}
              </span>
            ) : null}
          </div>
        </div>
      )
    }
    case 'agent.message':
      return (
        <div className="max-w-[80ch] whitespace-pre-wrap rounded-[10px] border border-[var(--color-accent)]/20 bg-[var(--color-accent-soft)] px-3.5 py-3 leading-relaxed">
          {String(p.text || '')}
        </div>
      )
    case 'policy.blocked':
      return (
        <div className="rounded-r-[10px] border-l-4 border-[var(--color-danger)] bg-[var(--color-danger-soft)] px-3.5 py-2.5 text-[13px]">
          Blocked <code>{String(p.tool)}</code>: confidence {String(p.confidence)} below{' '}
          {String(p.min_confidence)}
        </div>
      )
    case 'approval.requested':
      return (
        <div className="rounded-r-[10px] border-l-4 border-[var(--color-warning)] bg-[var(--color-warning-soft)] px-3.5 py-3">
          <b>Waiting for your approval</b>
          <br />
          <code className="font-mono text-[12.5px]">{String(p.tool)}</code>
        </div>
      )
    case 'approval.decided':
      return (
        <div className="text-[13px] text-[var(--color-fg-secondary)]">
          <b className="text-[var(--color-fg)]">{String(p.actor || 'Operator')}</b> {String(p.decision)}{' '}
          {String(p.tool)}
          {p.edited ? ' with edited arguments' : ''}
          {p.feedback ? `: “${String(p.feedback)}”` : ''}
        </div>
      )
    case 'input.requested':
      return (
        <div className="rounded-r-[10px] border-l-4 border-[var(--color-warning)] bg-[var(--color-warning-soft)] px-3.5 py-3">
          <b>The agent asks:</b> {String(p.question)}
        </div>
      )
    case 'run.finished': {
      const r = p.result as { resolved?: boolean; summary?: string }
      return (
        <div
          className={`outcome rounded-r-[10px] border-l-4 px-3.5 py-3 ${
            r?.resolved
              ? 'border-[var(--color-success)] bg-[var(--color-success-soft)]'
              : 'border-[var(--color-danger)] bg-[var(--color-danger-soft)]'
          }`}
        >
          <b>{r?.resolved ? 'Resolved' : 'Not resolved'}.</b> {r?.summary}
        </div>
      )
    }
    case 'operator.message':
    case 'operator.control':
    case 'memory.update':
    case 'memory.saved':
    case 'context.compacted':
    case 'llm.retry':
      return <div className="text-[13px] text-[var(--color-fg-secondary)]">{labelFor(ev)}</div>
    default:
      return (
        <div className="text-[13px] text-[var(--color-fg-tertiary)]">
          {ev.type.replaceAll('.', ' · ').replaceAll('_', ' ')}
        </div>
      )
  }
}

export function Timeline({ events }: { events: AgentEvent[] }) {
  const colRef = useRef<HTMLDivElement>(null)
  const [pinned, setPinned] = useState(true)
  const tools = useMemo(() => buildTools(events), [events])

  useEffect(() => {
    const el = colRef.current
    if (!el || !pinned) return
    el.scrollTop = el.scrollHeight
  }, [events.length, pinned, tools])

  useEffect(() => {
    const el = colRef.current
    if (!el) return
    const onScroll = () => {
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120
      setPinned(nearBottom)
    }
    el.addEventListener('scroll', onScroll)
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  const items: ReactNode[] = []
  let lastStep: number | null = null
  const seenTools = new Set<string>()

  for (const ev of events) {
    const p = ev.payload || {}
    const step = typeof p.step === 'number' ? p.step : null
    const showStep = step != null && step !== lastStep
    if (showStep) lastStep = step
    const gut = showStep ? (
      <span className="rounded bg-[var(--color-bg)] py-0.5 pl-1">s{step}</span>
    ) : null

    const wrap = (inner: ReactNode, key: string) => (
      <div key={key} className="animate-in relative grid grid-cols-[48px_minmax(0,1fr)] gap-x-3">
        <div className="absolute bottom-0 left-[23px] top-0 w-0.5 bg-[var(--color-border)]" />
        <div className="relative z-[1] pt-3 pr-2 text-right font-mono text-[11px] font-semibold text-[var(--color-fg-tertiary)]">
          {gut}
        </div>
        <div className="min-w-0 py-1 pb-2.5">{inner}</div>
      </div>
    )

    if (ev.type === 'tool.call') {
      const id = String(p.id)
      if (!seenTools.has(id)) {
        seenTools.add(id)
        const tool = tools.get(id)
        if (tool) items.push(wrap(<ToolCard tool={{ ...tool }} />, `tool-${id}`))
      }
      continue
    }
    if (ev.type === 'tool.result' || ev.type === 'tool.retry') continue
    items.push(wrap(renderEvent(ev), `e${ev.seq}`))
  }

  return (
    <div className="relative min-h-0 flex-1">
      <div ref={colRef} className="h-full overflow-auto px-7 pb-24 pt-2" id="traceCol" data-testid="timeline">
        {items}
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
          <ArrowDown className="size-3.5" /> Jump to latest
        </Button>
      ) : null}
    </div>
  )
}
