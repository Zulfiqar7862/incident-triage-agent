import { useCallback, useState } from 'react'
import { toast } from 'sonner'
import { approveRun, cancelRun, messageRun, pauseRun, rejectRun, resumeRun } from '@/lib/api'
import { mapError } from '@/lib/errors'

/**
 * Operator control actions for a single run (approve / reject / pause / …).
 * Keeps SidePanel presentational: mutations + toast error mapping live here.
 */
export function useRunActions(runId: string, onSettled?: () => void) {
  const [busy, setBusy] = useState(false)

  const act = useCallback(
    async (fn: () => Promise<unknown>, okToast?: string): Promise<boolean> => {
      setBusy(true)
      try {
        await fn()
        if (okToast) toast.success(okToast)
        onSettled?.()
        return true
      } catch (e) {
        const f = mapError(e)
        toast.error(`${f.title} — ${f.explanation}`)
        return false
      } finally {
        setBusy(false)
      }
    },
    [onSettled],
  )

  const decide = async (fn: () => Promise<unknown>): Promise<void> => {
    setBusy(true)
    try {
      await fn()
      onSettled?.()
    } finally {
      setBusy(false)
    }
  }

  return {
    busy,
    pause: () => act(() => pauseRun(runId)),
    resume: () => act(() => resumeRun(runId)),
    cancel: () => act(() => cancelRun(runId)),
    approve: (args?: Record<string, unknown>) => decide(() => approveRun(runId, args)),
    reject: (feedback: string) => decide(() => rejectRun(runId, feedback)),
    message: (text: string) => act(() => messageRun(runId, text)),
  }
}
