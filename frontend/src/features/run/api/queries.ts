import { useQuery } from '@tanstack/react-query'
import { fetchContext, fetchHealth, fetchRuns, fetchScenarios } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'

/** Server-state reads used across the console. Components stay presentational. */
export const useHealth = () =>
  useQuery({ queryKey: queryKeys.health, queryFn: fetchHealth, retry: 1 })

export const useScenarios = () =>
  useQuery({ queryKey: queryKeys.scenarios, queryFn: fetchScenarios })

export const useRuns = () =>
  useQuery({ queryKey: queryKeys.runs, queryFn: fetchRuns, refetchInterval: 4000 })

export const useRunContext = (runId: string, enabled: boolean) =>
  useQuery({ queryKey: queryKeys.context(runId), queryFn: () => fetchContext(runId), enabled })
