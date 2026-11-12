import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { createRun, fetchScenarios } from '@/lib/api'
import { mapError } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

type Options = {
  successToast: string
  onError?: (e: Error) => void
}

function toastMappedError(e: Error) {
  const f = mapError(e)
  toast.error(`${f.title} — ${f.explanation}`)
}

/**
 * Start a triage run and open it. Pass a scenario id, or nothing to start the first
 * available scenario. Shared by the toolbar and the empty state.
 */
export function useStartRun({ successToast, onError = toastMappedError }: Options) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  return useMutation({
    mutationFn: async (scenarioId?: string) => {
      if (scenarioId) return createRun(scenarioId)
      const first = (await fetchScenarios())[0]
      if (!first) throw new Error('No scenarios available')
      return createRun(first.id)
    },
    onSuccess: (run) => {
      void qc.invalidateQueries({ queryKey: queryKeys.runs })
      navigate(`/runs/${run.run_id}`)
      toast.success(successToast)
    },
    onError,
  })
}
