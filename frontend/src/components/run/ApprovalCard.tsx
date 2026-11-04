import { ShieldAlert } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { prettyJson, withoutKeys } from '@/lib/format'
import type { PendingApproval } from '@/lib/types'
import { cn } from '@/lib/utils'

type Props = {
  pending: PendingApproval
  operator: string
  onApprove: (args: Record<string, unknown>) => Promise<void>
  onReject: (feedback: string) => Promise<void>
  busy?: boolean
}

function riskLabel(confidence: number) {
  if (confidence >= 0.85) return { label: 'Lower risk', tone: 'text-[var(--color-success)]' }
  if (confidence >= 0.6) return { label: 'Moderate risk', tone: 'text-[var(--color-warning)]' }
  return { label: 'Higher risk', tone: 'text-[var(--color-danger)]' }
}

export function ApprovalCard({ pending, operator, onApprove, onReject, busy }: Props) {
  const original = useMemo(() => prettyJson(pending.args), [pending.args])
  const [argsText, setArgsText] = useState(original)
  const [feedback, setFeedback] = useState('')
  const [editing, setEditing] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setArgsText(original)
    setEditing(false)
  }, [original, pending.tool_call_id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'TEXTAREA' || tag === 'INPUT') return
      if (e.key === 'a' || e.key === 'A') {
        e.preventDefault()
        void handleApprove()
      }
      if (e.key === 'r' || e.key === 'R') {
        e.preventDefault()
        void handleReject()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [argsText, feedback, operator, pending])

  const conf = Math.round(Number(pending.args.confidence || 0) * 100)
  const risk = riskLabel(Number(pending.args.confidence || 0))
  const edited = argsText.trim() !== original.trim()
  const service = String(pending.args.service || '')
  const reason = String(pending.args.reason || '')
  const briefArgs = withoutKeys(pending.args, ['reason', 'confidence'])

  async function handleApprove() {
    if (!operator.trim()) {
      toast.error('Enter your name first — approvals are recorded in the audit log.')
      return
    }
    let args: Record<string, unknown>
    try {
      args = JSON.parse(argsText) as Record<string, unknown>
    } catch {
      toast.error('Arguments must be valid JSON.')
      return
    }
    try {
      await onApprove(args)
      toast.success(edited ? 'Approved with edited arguments' : 'Approved — change is applying')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Approve failed')
    }
  }

  async function handleReject() {
    try {
      await onReject(feedback)
      toast.message('Rejected — feedback sent to the agent')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Reject failed')
    }
  }

  return (
    <div
      ref={rootRef}
      className={cn(
        'animate-attention rounded-[14px] border border-[var(--color-warning-border)] bg-[var(--color-warning-soft)] p-4 shadow-sm',
      )}
      role="region"
      aria-label="Approval required"
      data-testid="approval-card"
    >
      <div className="mb-2 flex items-center gap-2 text-[var(--color-warning)]">
        <ShieldAlert className="size-4" />
        <h2 className="m-0 text-sm font-semibold tracking-tight">Approve a production change</h2>
      </div>
      <p className="m-0 mb-1.5 text-sm">
        The agent wants to run <code className="font-mono text-[12.5px]">{pending.tool}</code>
        {service ? (
          <>
            {' '}
            on <b>{service}</b>
          </>
        ) : null}
        .
      </p>
      {reason ? <p className="m-0 mb-2 text-xs text-[var(--color-fg-secondary)]">{reason}</p> : null}
      <div className="mb-1 flex items-center justify-between text-xs">
        <span>
          Agent confidence: <b>{conf}%</b>
        </span>
        <span className={cn('font-semibold', risk.tone)}>{risk.label}</span>
      </div>
      <div
        className="mb-3 h-1.5 overflow-hidden rounded-sm bg-[var(--color-elevated)]"
        role="meter"
        aria-valuenow={conf}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <i className="block h-full rounded-sm bg-[var(--color-warning)]" style={{ width: `${conf}%` }} />
      </div>
      <div className="mb-2 rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] p-2 font-mono text-[11.5px] text-[var(--color-fg-secondary)]">
        {pending.tool}({argPreview(briefArgs)})
      </div>
      <label className="text-xs text-[var(--color-fg-secondary)]" htmlFor="apArgs">
        Arguments {edited ? <span className="text-[var(--color-warning)]">(edited — diff below)</span> : '(edit before approving if needed)'}
      </label>
      <textarea
        id="apArgs"
        spellCheck={false}
        className="mt-1.5 mb-2 w-full min-h-[120px] resize-y rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] p-2.5 font-mono text-xs leading-relaxed"
        value={argsText}
        onChange={(e) => {
          setArgsText(e.target.value)
          setEditing(true)
        }}
      />
      {editing && edited ? (
        <div className="mb-3 grid gap-2 md:grid-cols-2" data-testid="args-diff">
          <pre className="max-h-40 overflow-auto rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] p-2 text-[11px] text-[var(--color-fg-tertiary)]">
            {original}
          </pre>
          <pre className="max-h-40 overflow-auto rounded-md border border-[var(--color-warning-border)] bg-[var(--color-elevated)] p-2 text-[11px]">
            {argsText}
          </pre>
        </div>
      ) : null}
      <Button id="apOk" variant="approve" disabled={busy} onClick={() => void handleApprove()} className="w-full sm:w-auto">
        Approve and run <kbd className="ml-2 rounded bg-black/15 px-1.5 text-[10px]">A</kbd>
      </Button>
      <div className="mt-2.5 flex gap-1.5">
        <input
          id="apFb"
          className="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] px-2.5 py-1.5 text-sm"
          placeholder="Reason for rejecting (sent to the agent)"
          aria-label="Rejection feedback"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
        />
        <Button id="apNo" variant="danger" disabled={busy} onClick={() => void handleReject()}>
          Reject <kbd className="ml-1 rounded bg-black/10 px-1 text-[10px]">R</kbd>
        </Button>
      </div>
      <p className="mt-2 text-[11px] text-[var(--color-fg-tertiary)]">
        Keyboard: <kbd>A</kbd> approve · <kbd>R</kbd> reject (when not typing)
      </p>
    </div>
  )
}

function argPreview(a: Record<string, unknown>) {
  return Object.entries(a)
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join(', ')
}
