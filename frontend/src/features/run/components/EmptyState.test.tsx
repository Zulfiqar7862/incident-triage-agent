import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { EmptyState } from './EmptyState'

it('explains operator control and starts a real investigation', () => {
  const start = vi.fn()
  render(<EmptyState onStartScenario={start} />)
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Stay in control')
  expect(screen.getByText(/simulated cluster/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /Start triage/ }))
  expect(start).toHaveBeenCalledOnce()
})

it('shows pending feedback and prevents another start', () => {
  render(<EmptyState onStartScenario={vi.fn()} busy />)
  expect(screen.getByRole('button', { name: /Starting/ })).toBeDisabled()
})
