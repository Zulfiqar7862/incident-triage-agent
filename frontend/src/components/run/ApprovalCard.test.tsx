import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApprovalCard } from './ApprovalCard'
import type { PendingApproval } from '@/lib/types'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() },
}))

const pending: PendingApproval = {
  kind: 'approval',
  tool_call_id: 'tc1',
  tool: 'rollback_deploy',
  args: { service: 'payments-api', reason: 'pool exhaustion', confidence: 0.82 },
  step: 4,
}

describe('ApprovalCard', () => {
  it('renders confidence, risk, and keyboard hints', () => {
    render(
      <ApprovalCard pending={pending} operator="Alex" onApprove={vi.fn()} onReject={vi.fn()} />,
    )
    expect(screen.getByTestId('approval-card')).toBeInTheDocument()
    expect(screen.getByText(/Rollback Deploy/i)).toBeInTheDocument()
    expect(screen.getByText(/82%/)).toBeInTheDocument()
    expect(screen.getByText(/Moderate risk/i)).toBeInTheDocument()
    expect(screen.getByText(/Keyboard/i)).toBeInTheDocument()
    expect(document.getElementById('apOk')).toBeTruthy()
    expect(document.getElementById('apNo')).toBeTruthy()
  })
})
