import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { DataView } from './DataView'
import { TechnicalDetails } from './TechnicalDetails'

describe('DataView', () => {
  it('renders structured fields without a default JSON <pre>', () => {
    const { container } = render(
      <DataView
        data={{
          service: 'checkout-service',
          error_rate: 0.12,
          status: 'firing',
          pods: [
            { name: 'a', ready: true },
            { name: 'b', ready: false },
          ],
        }}
      />,
    )
    expect(screen.getAllByTestId('data-view').length).toBeGreaterThan(0)
    expect(screen.getByText('Service')).toBeInTheDocument()
    expect(screen.getByText('checkout-service')).toBeInTheDocument()
    expect(screen.getByText('Error Rate')).toBeInTheDocument()
    expect(screen.getByText('12%')).toBeInTheDocument()
    // No raw JSON dump by default
    expect(container.querySelector('pre')).toBeNull()
    expect(container.textContent).not.toMatch(/\{\s*"service"/)
  })

  it('keeps raw JSON behind Technical details disclosure', async () => {
    const user = userEvent.setup()
    render(<TechnicalDetails data={{ a: 1, nested: { b: true } }} />)
    expect(screen.queryByTestId('technical-details')).not.toBeInTheDocument()
    await user.click(screen.getByTestId('technical-details-trigger'))
    expect(screen.getByTestId('technical-details')).toBeInTheDocument()
    expect(screen.getByTestId('technical-details').textContent).toContain('"a": 1')
  })
})
