import { act, renderHook } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { approveRun, rejectRun } from '@/lib/api'
import { useRunActions } from './useRunActions'

vi.mock('@/lib/api', () => ({
  approveRun: vi.fn(),
  rejectRun: vi.fn(),
  cancelRun: vi.fn(),
  messageRun: vi.fn(),
  pauseRun: vi.fn(),
  resumeRun: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

it('propagates approval failure to the card and does not signal success', async () => {
  vi.mocked(approveRun).mockRejectedValueOnce(new Error('Unavailable'))
  const refresh = vi.fn()
  const { result } = renderHook(() => useRunActions('incident', refresh))
  await act(async () => {
    await expect(result.current.approve({ service: 'checkout' })).rejects.toThrow('Unavailable')
  })
  expect(result.current.busy).toBe(false)
  expect(refresh).not.toHaveBeenCalled()
})

it('preserves rejection feedback and refreshes after success', async () => {
  vi.mocked(rejectRun).mockResolvedValueOnce({} as Awaited<ReturnType<typeof rejectRun>>)
  const refresh = vi.fn()
  const { result } = renderHook(() => useRunActions('incident', refresh))
  await act(async () => {
    await result.current.reject('Wrong scope')
  })
  expect(rejectRun).toHaveBeenCalledWith('incident', 'Wrong scope')
  expect(refresh).toHaveBeenCalledOnce()
  expect(result.current.busy).toBe(false)
})
