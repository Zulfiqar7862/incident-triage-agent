import { ApprovalCard } from '@/features/approval/components/ApprovalCard'
import { useRunActions } from '@/features/run/api/useRunActions'
import { SidePanel } from '@/features/run/components/SidePanel'
import { useUiStore } from '@/stores/uiStore'
import type { PendingApproval, RunDetail } from '@/types/api'

type Props = { run: RunDetail; onRefresh: () => void; onInspectContext: () => void }

/**
 * App-layer composition of two features: the run side panel and the approval card.
 * One ``useRunActions`` instance so every control shares the same busy state.
 */
export function RunSidebar({ run, onRefresh, onInspectContext }: Props) {
  const operator = useUiStore((s) => s.operator)
  const actions = useRunActions(run.run_id, onRefresh)
  const pending = run.pending
  const approval =
    pending && pending.kind === 'approval' && run.status === 'awaiting_approval' ? (
      <ApprovalCard
        pending={pending as PendingApproval}
        operator={operator}
        busy={actions.busy}
        onApprove={async (args) => {
          await actions.approve(args)
        }}
        onReject={async (feedback) => {
          await actions.reject(feedback)
        }}
      />
    ) : null
  return (
    <SidePanel
      run={run}
      actions={actions}
      approval={approval}
      onInspectContext={onInspectContext}
    />
  )
}
