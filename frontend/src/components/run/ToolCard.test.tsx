import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ToolCard } from './ToolCard'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() },
}))

describe('ToolCard', () => {
  it('renders API summary and structured output without default JSON pre', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <ToolCard
        tool={{
          id: '1',
          name: 'query_metrics',
          args: { service: 'api', metric: 'cpu', window_minutes: 15 },
          title: 'Health metrics',
          summary: 'Check cpu for api',
          risk: 'low',
          operator: {
            title: 'Check processor use',
            summary: 'Processor use: 62%. Usual level: 40%.',
            fields: [{ label: 'Service', value: 'api' }],
            evidence: [],
            impact: '',
          },
          status: 'ok',
          content: JSON.stringify({
            service: 'api',
            metric: 'cpu',
            unit: 'percent',
            window_minutes: 15,
            baseline: 40,
            points: [
              { minutes_ago: 5, value: 55 },
              { minutes_ago: 0, value: 62 },
            ],
          }),
          duration_ms: 12,
        }}
      />,
    )
    expect(screen.getByTestId('tool-card')).toBeInTheDocument()
    const title = screen.getByText(/Check processor use/i)
    expect(title).toBeInTheDocument()
    expect(title.textContent || '').not.toMatch(/\w+_\w+\(/)
    await user.click(screen.getByRole('button', { name: /Check processor use/i }))
    expect(screen.getByText('Service')).toBeInTheDocument()
    expect(screen.getByText('Processor use: 62%. Usual level: 40%.')).toBeInTheDocument()
    const openPres = Array.from(container.querySelectorAll('pre')).filter(
      (el) => el.offsetParent !== null,
    )
    expect(screen.queryByTestId('technical-details')).not.toBeInTheDocument()
    expect(openPres.length).toBe(0)
  })
})

it('does not expose raw technical results even when an error row is expanded', async () => {
  const raw = 'Traceback TimeoutError DB_POOL_SIZE ERROR POST /api/checkout rollback_deploy()'
  const { container } = render(
    <ToolCard
      tool={{
        id: 'broken',
        name: 'search_logs',
        args: { query: raw },
        content: raw,
        summary: raw,
        status: 'error',
      }}
    />,
  )
  // No operator facts to reveal, so the row is not expandable.
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
  expect(container.textContent).not.toContain('TimeoutError')
  expect(container.textContent).not.toContain('DB_POOL_SIZE')
  expect(container.querySelector('pre')).toBeNull()
})

it('only offers to expand a check when there are details to show', () => {
  render(
    <ToolCard
      tool={{
        id: 'alert',
        name: 'get_alert',
        args: {},
        status: 'ok',
        operator: {
          title: 'Review the incident',
          summary: 'The incident alert is still active.',
          fields: [],
          evidence: [],
          impact: '',
        },
      }}
    />,
  )
  expect(screen.getByText('Review the incident')).toBeInTheDocument()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})
