import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApprovalCard } from './ApprovalCard'
import type { PendingApproval } from '@/lib/types'
import { looksLikeFunctionCall } from '@/lib/humanize'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() },
}))

const pending: PendingApproval = {
  kind: 'approval',
  tool_call_id: 'tc1',
  tool: 'rollback_deploy',
  args: { service: 'payments-api', to_version: 'v1.2.3', reason: 'pool exhaustion', confidence: 0.82 },
  step: 4,
}

describe('ApprovalCard', () => {
  it('shows plain-English summary without function-call jargon', () => {
    render(
      <ApprovalCard pending={pending} operator="Alex" onApprove={vi.fn()} onReject={vi.fn()} />,
    )
    expect(screen.getByTestId('approval-card')).toBeInTheDocument()
    const summary = screen.getByTestId('approval-summary').textContent || ''
    expect(summary).toMatch(/Roll back payments-api to version v1\.2\.3/i)
    expect(looksLikeFunctionCall(summary)).toBe(false)
    expect(summary).not.toMatch(/\w+_\w+\(/)
    expect(screen.getByText(/82%/)).toBeInTheDocument()
    expect(screen.getByText(/needs a careful look/i)).toBeInTheDocument()
    expect(screen.queryByText(/Keyboard/i)).not.toBeInTheDocument()
    expect(document.getElementById('apOk')).toBeTruthy()
    expect(document.getElementById('apNo')).toBeTruthy()
    expect(screen.getByText('Approve fix')).toBeInTheDocument()
  })
})
