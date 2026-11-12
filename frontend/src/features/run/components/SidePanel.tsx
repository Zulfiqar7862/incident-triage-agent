import type { ReactNode } from 'react'
import { TERMINAL, type RunDetail } from '@/types/api'
import type { RunActions } from '../api/useRunActions'
import { EngineerDetails } from './EngineerDetails'
import { GuidanceForm } from './GuidanceForm'
import { IncidentReport } from './IncidentReport'
import { OperatorAnswerForm } from './OperatorAnswerForm'
import { RunControls } from './RunControls'

type Props = {
  run: RunDetail
  actions: RunActions
  /** Decision card for a pending approval, composed by the app layer (keeps features independent). */
  approval?: ReactNode
  onInspectContext: () => void
}

/** Right-hand column: decision, controls, guidance, report, engineering details. */
export function SidePanel({ run, actions, approval, onInspectContext }: Props) {
  const pending = run.pending
  return (
    <aside
      className="col side flex min-h-0 flex-col gap-0 overflow-auto border-l border-[var(--color-border)]"
      aria-label="Run controls and state"
    >
      {approval ? (
        <section className="mb-5 border-b border-[var(--color-border)] pb-5">{approval}</section>
      ) : null}
      <RunControls run={run} actions={actions} />
      {pending && pending.kind === 'input' && run.status === 'awaiting_input' ? (
        <OperatorAnswerForm pending={pending} actions={actions} />
      ) : null}
      {!TERMINAL.includes(run.status) && run.status !== 'awaiting_input' ? (
        <GuidanceForm actions={actions} />
      ) : null}
      {run.result ? <IncidentReport run={run} /> : null}
      <EngineerDetails run={run} onInspectContext={onInspectContext} />
    </aside>
  )
}
