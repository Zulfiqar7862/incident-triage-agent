import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ToolCard } from './ToolCard'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() },
}))

describe('ToolCard', () => {
  it('shows human name and structured output without default JSON pre', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <ToolCard
        tool={{
          id: '1',
          name: 'query_metrics',
          args: { service: 'api', metric: 'cpu', window_minutes: 15 },
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
    expect(screen.getByText('Query Metrics')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Query Metrics/i }))
    expect(screen.getByText('Inputs')).toBeInTheDocument()
    expect(screen.getByTestId('tool-metrics')).toBeInTheDocument()
    // Expanded view may include technical details disclosure, but no default open <pre> of JSON args
    const openPres = Array.from(container.querySelectorAll('pre')).filter((el) => el.offsetParent !== null)
    // technical details content is collapsed by default (Collapsible unmounts content)
    expect(screen.queryByTestId('technical-details')).not.toBeInTheDocument()
    expect(openPres.length).toBe(0)
  })
})
