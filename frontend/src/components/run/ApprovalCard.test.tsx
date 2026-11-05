import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  args: { service: 'payments-api', to_version: 'v1.2.3', reason: 'pool exhaustion', confidence: 0.82 },
  step: 4,
  title: 'Rollback',
  summary: 'Roll back payments-api to version v1.2.3',
  risk: 'high',
}

describe('ApprovalCard', () => {
  it('renders backend summary/risk without function-call jargon', () => {
    render(<ApprovalCard pending={pending} operator="Alex" onApprove={vi.fn()} onReject={vi.fn()} />)
    expect(screen.getByTestId('approval-card')).toBeInTheDocument()
    const summary = screen.getByTestId('approval-summary').textContent || ''
    expect(summary).toBe('Roll back payments-api to version v1.2.3')
    expect(summary).not.toMatch(/\w+_\w+\(/)
    expect(screen.getByText(/High risk/i)).toBeInTheDocument()
    expect(screen.getByText(/82%/)).toBeInTheDocument()
    expect(screen.getByTestId('approve-btn')).toBeInTheDocument()
    expect(screen.getByTestId('reject-btn')).toBeInTheDocument()
  })

  it('calls onApprove with draft args', async () => {
    const onApprove = vi.fn().mockResolvedValue(undefined)
    render(<ApprovalCard pending={pending} operator="Alex" onApprove={onApprove} onReject={vi.fn()} />)
    fireEvent.click(screen.getByTestId('approve-btn'))
    await waitFor(() => expect(onApprove).toHaveBeenCalledTimes(1))
    expect(onApprove.mock.calls[0][0]).toMatchObject({ service: 'payments-api', to_version: 'v1.2.3' })
  })

  it('calls onReject with feedback', async () => {
    const onReject = vi.fn().mockResolvedValue(undefined)
    render(<ApprovalCard pending={pending} operator="Alex" onApprove={vi.fn()} onReject={onReject} />)
    fireEvent.change(screen.getByLabelText(/Rejection feedback/i), { target: { value: 'wrong service' } })
    fireEvent.click(screen.getByTestId('reject-btn'))
    await waitFor(() => expect(onReject).toHaveBeenCalledWith('wrong service'))
  })

  it('disables actions while busy', () => {
    render(<ApprovalCard pending={pending} operator="Alex" onApprove={vi.fn()} onReject={vi.fn()} busy />)
    expect(screen.getByTestId('approve-btn')).toBeDisabled()
    expect(screen.getByTestId('reject-btn')).toBeDisabled()
  })
})
