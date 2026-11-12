import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import type { RunActions } from '../api/useRunActions'
import { SidePanel } from './SidePanel'
import { ThinkingIndicator } from './ThinkingIndicator'
import { ErrorBanner } from '@/components/common/ErrorBanner'
import { ApiError } from '@/lib/api'
import { mapError } from '@/lib/errors'
import type { RunDetail } from '@/types/api'
import { useUiStore } from '@/stores/uiStore'

const raw = 'DB_POOL_SIZE ERROR POST /api/checkout TimeoutError Traceback rollback_deploy()'
const run: RunDetail = {
  run_id: 'run',
  scenario_id: 'incident',
  title: raw,
  task: raw,
  status: 'completed',
  status_reason: raw,
  active: false,
  step: 7,
  max_steps: 25,
  plan: [raw],
  hypotheses: [{ text: raw, status: 'confirmed', evidence: raw }],
  pending: null,
  usage: {
    llm_calls: 1,
    input_tokens: 1,
    output_tokens: 1,
    cost_usd: 0,
    llm_ms: 1,
    tool_calls: 1,
    tool_retries: 0,
    tool_errors: 0,
  },
  result: { resolved: true, summary: raw, root_cause: raw, fix_applied: raw },
  created_at: 0,
  checkpoint_version: 1,
  operator: {
    title: 'Service disruption',
    summary: 'Review the evidence',
    status: 'Investigation complete',
    plan: [],
    evidence: [],
    report: {
      title: 'Incident resolved',
      summary: 'The agent marked this incident resolved.',
      fields: [{ label: 'Cause', value: 'Not independently confirmed' }],
      evidence: ['Failed requests: 0.29%. Usual level: 0.3%.'],
      impact: '',
    },
  },
}
beforeEach(() => useUiStore.setState({ showEngineerDetails: false }))

it('shows only structured report facts; original reasoning is in the separate explicit engineering disclosure', () => {
  const { container } = render(
    <SidePanel run={run} actions={{ busy: false } as RunActions} onInspectContext={vi.fn()} />,
  )
  expect(container.textContent).not.toContain('DB_POOL_SIZE')
  expect(container.textContent).not.toContain('TimeoutError')
  expect(screen.getByText('Failed requests: 0.29%. Usual level: 0.3%.')).toBeInTheDocument()
  fireEvent.click(screen.getByTestId('engineer-details-toggle'))
  expect(container.textContent).toContain('DB_POOL_SIZE')
  fireEvent.click(screen.getByTestId('engineer-details-toggle'))
  expect(container.textContent).not.toContain('DB_POOL_SIZE')
})

it('never shows raw validation failures by default, but preserves engineering evidence', () => {
  const { container } = render(<ErrorBanner error={mapError(new ApiError(422, raw))} />)
  expect(container.textContent).not.toContain('TimeoutError')
  fireEvent.click(screen.getByRole('button', { name: 'For engineers' }))
  expect(screen.getByTestId('error-technical')).toHaveTextContent(raw)
})

it('never claims thinking while waiting, paused, queued or finished', () => {
  const { container, rerender } = render(
    <ThinkingIndicator status="awaiting_approval" phase="Agent is thinking" />,
  )
  expect(container).toBeEmptyDOMElement()
  for (const status of ['paused', 'queued', 'completed', 'awaiting_input'] as const) {
    rerender(<ThinkingIndicator status={status} phase="Agent is thinking" />)
    expect(container).toBeEmptyDOMElement()
  }
  rerender(<ThinkingIndicator status="running" phase="Agent is thinking" />)
  expect(screen.getByTestId('thinking-indicator')).toHaveTextContent('Investigation in progress')
})
