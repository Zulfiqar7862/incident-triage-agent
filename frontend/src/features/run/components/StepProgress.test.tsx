import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { StepProgress } from './StepProgress'

it('discloses the actual plan without inventing per-item completion', () => {
  render(
    <StepProgress
      step={7}
      status="awaiting_approval"
      plan={['Gather evidence', 'Verify recovery']}
      hasResult={false}
    />,
  )
  expect(screen.getByText(/2 planned actions · agent step 7/)).toBeInTheDocument()
  fireEvent.click(screen.getByText('Investigation plan'))
  expect(screen.getByRole('list', { name: 'Investigation plan' })).toBeVisible()
  expect(screen.queryByText(/completed/i)).not.toBeInTheDocument()
})
