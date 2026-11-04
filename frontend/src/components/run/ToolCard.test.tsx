import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ToolCard } from './ToolCard'

describe('ToolCard', () => {
  it('shows name and expands args', async () => {
    const user = userEvent.setup()
    render(
      <ToolCard
        tool={{
          id: '1',
          name: 'get_metrics',
          args: { service: 'api', window: '15m' },
          status: 'ok',
          content: '{"cpu":0.9}',
          duration_ms: 12,
        }}
      />,
    )
    expect(screen.getByTestId('tool-card')).toBeInTheDocument()
    expect(screen.getByText('get_metrics')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /get_metrics/i }))
    expect(screen.getByText('Arguments')).toBeInTheDocument()
  })
})
