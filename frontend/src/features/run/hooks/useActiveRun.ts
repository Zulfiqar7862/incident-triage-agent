import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useRunStream } from '@/hooks/useRunStream'
import { fetchRun } from '@/lib/api'
import { ACTIVE } from '@/lib/types'

/** TanStack Query + SSE for the selected run — shared by ConsolePage. */
export function useActiveRun(runId: string | undefined) {
  const qc = useQueryClient()
  const runQuery = useQuery({
    queryKey: ['run', runId],
    queryFn: () => fetchRun(runId!),
    enabled: Boolean(runId),
    refetchInterval: (q) => {
      const st = q.state.data?.status
      if (!st) return 2000
      if (ACTIVE.includes(st) || st === 'awaiting_approval' || st === 'awaiting_input') return 1500
      return false
    },
  })
  const stream = useRunStream(runId || null)

  useEffect(() => {
    if (stream.events.length) {
      void qc.invalidateQueries({ queryKey: ['run', runId] })
      void qc.invalidateQueries({ queryKey: ['runs'] })
    }
  }, [stream.events.length, qc, runId])

  return { runQuery, stream, run: runQuery.data }
}
