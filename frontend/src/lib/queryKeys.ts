/** Single source of TanStack Query keys, so invalidation and reads cannot drift apart. */
export const queryKeys = {
  health: ['health'] as const,
  scenarios: ['scenarios'] as const,
  runs: ['runs'] as const,
  run: (runId: string | undefined) => ['run', runId] as const,
  context: (runId: string) => ['context', runId] as const,
}
