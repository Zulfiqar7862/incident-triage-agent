import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Moon, Sun } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { createRun, fetchHealth, fetchScenarios } from '@/lib/api'
import { useUiStore } from '@/store/uiStore'

export function AppHeader() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const operator = useUiStore((s) => s.operator)
  const setOperator = useUiStore((s) => s.setOperator)
  const theme = useUiStore((s) => s.theme)
  const setTheme = useUiStore((s) => s.setTheme)

  const health = useQuery({ queryKey: ['health'], queryFn: fetchHealth, retry: 1 })
  const scenarios = useQuery({ queryKey: ['scenarios'], queryFn: fetchScenarios })

  const [scenarioId, setScenarioId] = useState('')
  const effectiveScenarioId = scenarioId || scenarios.data?.[0]?.id || ''

  const start = useMutation({
    mutationFn: (scenario_id: string) => createRun(scenario_id),
    onSuccess: (run) => {
      void qc.invalidateQueries({ queryKey: ['runs'] })
      navigate(`/runs/${run.run_id}`)
      toast.success('Triage started')
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const offline = health.data?.llm.provider === 'scripted'

  return (
    <header className="app-header flex min-h-14 flex-wrap items-center gap-3 border-b border-[var(--color-border)] bg-[var(--color-elevated)] px-[18px] py-2 shadow-sm z-10">
      <div className="brand flex items-center gap-2.5 text-[15px] font-semibold tracking-tight" aria-label="Incident triage agent">
        <span className="brand-mark grid size-7 place-items-center rounded-lg bg-gradient-to-br from-[var(--color-accent)] to-[#7c3aed] text-[13px] font-bold text-white">
          IT
        </span>
        <span>Incident triage</span>
      </div>
      <span
        id="mode"
        className={`mode text-[12.5px] ${offline ? 'text-[var(--color-warning)]' : 'text-[var(--color-fg-secondary)]'}`}
        role="status"
      >
        <span
          className={`dot mr-1.5 inline-block size-1.5 rounded-full align-middle ${
            offline ? 'bg-[var(--color-warning)]' : 'bg-[var(--color-success)]'
          }`}
        />
        {health.isError
          ? 'API unreachable'
          : offline
            ? 'Offline deterministic provider — set an API key for a live model'
            : `Model: ${health.data?.llm.model || '…'}`}
      </span>
      <span className="min-w-2 flex-1" />
      <div className="header-actions flex flex-wrap items-center gap-2">
        <label className="text-xs text-[var(--color-fg-secondary)]" htmlFor="operator">
          Signed in as
        </label>
        <input
          id="operator"
          className="w-[140px] rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] px-2.5 py-1.5 text-sm"
          placeholder="Your name"
          autoComplete="name"
          aria-label="Your name for the audit log"
          value={operator}
          onChange={(e) => setOperator(e.target.value)}
        />
        <label className="sr-only" htmlFor="scenario">
          Incident scenario
        </label>
        <select
          id="scenario"
          className="rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] px-2.5 py-1.5 text-sm"
          aria-label="Incident scenario"
          value={effectiveScenarioId}
          onChange={(e) => setScenarioId(e.target.value)}
        >
          <option value="" disabled>
            Select scenario
          </option>
          {(scenarios.data || []).map((s) => (
            <option key={s.id} value={s.id} title={s.description}>
              {s.title}
            </option>
          ))}
        </select>
        <Button
          id="startBtn"
          variant="primary"
          disabled={start.isPending}
          onClick={() => {
            if (!effectiveScenarioId) {
              toast.error('Pick a scenario first')
              return
            }
            start.mutate(effectiveScenarioId)
          }}
        >
          Start triage
        </Button>
        <Button
          variant="ghost"
          aria-label="Toggle color theme"
          onClick={() => setTheme(theme === 'dark' ? 'light' : theme === 'light' ? 'system' : 'dark')}
          title={`Theme: ${theme}`}
        >
          {theme === 'dark' ? <Moon className="size-4" /> : <Sun className="size-4" />}
        </Button>
      </div>
    </header>
  )
}
