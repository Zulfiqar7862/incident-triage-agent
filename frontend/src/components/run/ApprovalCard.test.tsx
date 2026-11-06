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
  args: {
    service: 'payments-api',
    to_version: 'v1.2.3',
    reason: 'pool exhaustion',
    confidence: 0.82,
  },
  step: 4,
  title: 'Rollback',
  summary: 'Roll back payments-api to version v1.2.3',
  risk: 'high',
  operator: {
    title: 'Restore the previous version',
    summary: 'The cause has not been independently confirmed.',
    fields: [
      { label: 'Service', value: 'payments-api' },
      { label: 'Restore version', value: 'v1.2.3' },
    ],
    evidence: ['Failed requests: 12%. Usual level: 0.3%.'],
    impact: 'Requests may be briefly interrupted.',
  },
}

describe('ApprovalCard', () => {
  it('renders backend summary/risk without function-call jargon', () => {
    render(
      <ApprovalCard pending={pending} operator="Alex" onApprove={vi.fn()} onReject={vi.fn()} />,
    )
    expect(screen.getByTestId('approval-card')).toBeInTheDocument()
    const summary = screen.getByTestId('approval-summary').textContent || ''
    expect(summary).toBe('Restore the previous version')
    expect(summary).not.toMatch(/\w+_\w+\(/)
    expect(screen.getByText(/High risk/i)).toBeInTheDocument()
    expect(screen.getByText(/82%/)).toBeInTheDocument()
    expect(screen.getByTestId('approve-btn')).toBeInTheDocument()
    expect(screen.getByTestId('reject-btn')).toBeInTheDocument()
  })

  it('calls onApprove with draft args', async () => {
    const onApprove = vi.fn().mockResolvedValue(undefined)
    render(
      <ApprovalCard pending={pending} operator="Alex" onApprove={onApprove} onReject={vi.fn()} />,
    )
    fireEvent.click(screen.getByTestId('approve-btn'))
    await waitFor(() => expect(onApprove).toHaveBeenCalledTimes(1))
    expect(onApprove.mock.calls[0][0]).toMatchObject({
      service: 'payments-api',
      to_version: 'v1.2.3',
    })
  })

  it('calls onReject with feedback', async () => {
    const onReject = vi.fn().mockResolvedValue(undefined)
    render(
      <ApprovalCard pending={pending} operator="Alex" onApprove={vi.fn()} onReject={onReject} />,
    )
    fireEvent.change(screen.getByLabelText(/Rejection feedback/i), {
      target: { value: 'wrong service' },
    })
    fireEvent.click(screen.getByTestId('reject-btn'))
    await waitFor(() => expect(onReject).toHaveBeenCalledWith('wrong service'))
  })

  it('disables actions while busy', () => {
    render(
      <ApprovalCard
        pending={pending}
        operator="Alex"
        onApprove={vi.fn()}
        onReject={vi.fn()}
        busy
      />,
    )
    expect(screen.getByTestId('approve-btn')).toBeDisabled()
    expect(screen.getByTestId('reject-btn')).toBeDisabled()
  })
})

it('keeps failed approvals retryable and announces the error inline', async () => {
  const onApprove = vi.fn().mockRejectedValue(new Error('Connection failed'))
  render(
    <ApprovalCard pending={pending} operator="Alex" onApprove={onApprove} onReject={vi.fn()} />,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Approve fix' }))
  await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  expect(screen.getByRole('button', { name: 'Approve fix' })).toBeEnabled()
})

it('exposes edit disclosure state and retains backend summary while editing', () => {
  render(<ApprovalCard pending={pending} operator="Alex" onApprove={vi.fn()} onReject={vi.fn()} />)
  const edit = screen.getByRole('button', { name: 'Edit before approving' })
  expect(edit).toHaveAttribute('aria-expanded', 'false')
  fireEvent.click(edit)
  expect(edit).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByLabelText('Service')).toBeInTheDocument()
  expect(screen.getByTestId('approval-summary')).toHaveTextContent(pending.operator!.title)
})

it('never approves through a page-wide or modified keyboard shortcut', () => {
  const onApprove = vi.fn()
  render(
    <ApprovalCard pending={pending} operator="Alex" onApprove={onApprove} onReject={vi.fn()} />,
  )
  fireEvent.keyDown(window, { key: 'a' })
  fireEvent.keyDown(screen.getByRole('button', { name: 'Approve fix' }), {
    key: 'a',
    ctrlKey: true,
  })
  expect(onApprove).not.toHaveBeenCalled()
})

it('never uses raw reason, legacy summary, args or backend errors as operator copy', async () => {
  const raw = 'DB_POOL_SIZE 50→5 ERROR POST /api/checkout TimeoutError rollback_deploy()'
  const onApprove = vi.fn().mockRejectedValue(new Error(raw))
  const { container } = render(
    <ApprovalCard
      pending={{ ...pending, summary: raw, args: { ...pending.args, reason: raw } }}
      operator="Alex"
      onApprove={onApprove}
      onReject={vi.fn()}
    />,
  )
  expect(container.textContent).not.toContain('DB_POOL_SIZE')
  fireEvent.click(screen.getByRole('button', { name: 'Edit before approving' }))
  expect(screen.getByLabelText('Reason')).toHaveValue('')
  fireEvent.click(screen.getByTestId('approve-btn'))
  await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  expect(container.textContent).not.toContain('TimeoutError')
  expect(screen.getByText('Failed requests: 12%. Usual level: 0.3%.')).toBeInTheDocument()
})

it('fails safely when an older API response has no operator projection', () => {
  const { container } = render(
    <ApprovalCard
      pending={{
        ...pending,
        operator: undefined,
        title: 'rollback_deploy()',
        summary: 'DB_POOL_SIZE',
      }}
      operator="Alex"
      onApprove={vi.fn()}
      onReject={vi.fn()}
    />,
  )
  expect(container.textContent).not.toContain('DB_POOL_SIZE')
  expect(container.textContent).not.toContain('rollback_deploy(')
})
