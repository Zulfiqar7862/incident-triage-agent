import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Timeline } from './Timeline'
import type { AgentEvent, OperatorDisplay } from '@/types/api'

const raw = 'DB_POOL_SIZE 50→5 ERROR POST /api/checkout TimeoutError Traceback rollback_deploy()'
const display = (title: string, summary = ''): OperatorDisplay => ({
  title,
  summary,
  fields: [],
  evidence: [],
  impact: '',
})
const event = (
  seq: number,
  type: string,
  payload: Record<string, unknown>,
  operator?: OperatorDisplay | null,
): AgentEvent => ({ seq, type, run_id: 'run', payload, operator })
const events = [
  event(1, 'llm.call', { text: raw }),
  event(2, 'agent.message', { text: raw }, null),
  event(
    3,
    'tool.call',
    { id: 'logs', name: 'search_logs', args: { query: raw }, summary: raw },
    display('Review diagnostic evidence'),
  ),
  event(31, 'tool.retry', { id: 'logs' }, null),
  event(
    4,
    'tool.result',
    { id: 'logs', name: 'search_logs', content: raw },
    display('Review diagnostic evidence', 'Service diagnostics were retrieved.'),
  ),
  event(
    5,
    'tool.call',
    { id: 'change', name: 'rollback_deploy', kind: 'write', args: { reason: raw } },
    display('Restore the previous version'),
  ),
  event(6, 'approval.requested', { summary: raw }, null),
  event(7, 'run.status', { status: 'awaiting_approval', reason: raw }, null),
]

function expectPlain(container: HTMLElement) {
  expect(container.textContent).not.toMatch(
    /DB_POOL_SIZE|ERROR POST|TimeoutError|Traceback|rollback_deploy\(/,
  )
  expect(container.textContent).not.toMatch(/thinking|checkpoint|Waiting for your approval/i)
}

describe('operator timeline', () => {
  it('renders safe evidence once on pending SSE and reload without thought blobs or duplicate proposals', () => {
    const { container, rerender } = render(<Timeline events={events} status="awaiting_approval" />)
    expectPlain(container)
    expect(screen.queryByText('This check is being retried.')).not.toBeInTheDocument()
    expect(screen.getAllByTestId('tool-card')).toHaveLength(1)
    expect(screen.getByText('Service diagnostics were retrieved.')).toBeInTheDocument()
    expect(screen.queryByText('Restore the previous version')).not.toBeInTheDocument()
    rerender(<Timeline events={[...events]} status="awaiting_approval" />)
    expectPlain(container)
    expect(screen.queryByText('This check is being retried.')).not.toBeInTheDocument()
    expect(screen.getAllByTestId('tool-card')).toHaveLength(1)
  })

  it('never falls back to raw final report or rejection feedback', () => {
    const later = [
      ...events,
      event(
        8,
        'approval.decided',
        { decision: 'rejected', feedback: raw },
        display('Change rejected', 'The proposed change was not applied.'),
      ),
      event(
        9,
        'run.finished',
        { result: { summary: raw, root_cause: raw } },
        display('Investigation finished', 'The agent finished without confirming recovery.'),
      ),
    ]
    const { container } = render(<Timeline events={later} status="completed" />)
    expectPlain(container)
    expect(screen.getByText('Change rejected')).toBeInTheDocument()
    expect(screen.getByText('The agent finished without confirming recovery.')).toBeInTheDocument()
  })

  it('fails safely if old event schemas omit display fields', () => {
    const { container } = render(
      <Timeline events={events.map(({ operator: _operator, ...item }) => item)} status="failed" />,
    )
    expectPlain(container)
  })
})
