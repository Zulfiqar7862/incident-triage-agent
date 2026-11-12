import { Activity, Moon, Sun } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useHealth, useScenarios } from '@/features/run/hooks/queries'
import { useStartRun } from '@/features/run/hooks/useStartRun'
import { useUiStore } from '@/store/uiStore'

export function AppHeader() {
  const operator = useUiStore((s) => s.operator)
  const setOperator = useUiStore((s) => s.setOperator)
  const theme = useUiStore((s) => s.theme)
  const setTheme = useUiStore((s) => s.setTheme)

  const health = useHealth()
  const scenarios = useScenarios()

  const [scenarioId, setScenarioId] = useState('')
  const effectiveScenarioId = scenarioId || scenarios.data?.[0]?.id || ''

  const start = useStartRun({
    successToast: 'Triage started',
    onError: (e: Error) => toast.error(e.message),
  })

  const offline = health.data?.llm.provider === 'scripted'

  return (
    <header className="console-toolbar">
      <div className="toolbar-brand">
        <span className="brand-mark">
          <Activity className="size-5" aria-hidden />
        </span>
        <div>
          <div className="text-base font-semibold tracking-tight">Incident triage</div>
          <div className="mt-0.5 text-xs text-[var(--color-fg-secondary)]">
            Operations workspace
          </div>
        </div>
      </div>
      <div className="toolbar-fields">
        <div>
          <label className="field-label" htmlFor="operator">
            Operator · audit identity
          </label>
          <input
            id="operator"
            className="console-input w-[160px]"
            placeholder="Your name"
            autoComplete="name"
            aria-label="Your name for the audit log"
            value={operator}
            onChange={(e) => setOperator(e.target.value)}
          />
        </div>
        <div className="scenario-field">
          <label className="field-label" htmlFor="scenario">
            Incident scenario
          </label>
          <select
            id="scenario"
            className="console-input max-w-[280px]"
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
        </div>
        <Button
          id="startBtn"
          className="start-triage"
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
          {start.isPending ? 'Starting…' : 'Start triage'}
        </Button>
        <Button
          variant="ghost"
          aria-label="Toggle color theme"
          title={`Theme: ${theme}`}
          onClick={() =>
            setTheme(theme === 'dark' ? 'light' : theme === 'light' ? 'system' : 'dark')
          }
        >
          {theme === 'dark' ? (
            <Moon className="size-4" aria-hidden />
          ) : (
            <Sun className="size-4" aria-hidden />
          )}
        </Button>
      </div>
      {health.isError ? (
        <p className="w-full text-sm text-[var(--color-danger)]" role="status">
          Can’t reach the server. Reconnecting…
        </p>
      ) : null}
      <span className="sr-only" id="mode">
        {offline ? 'Scripted model provider' : 'Live model provider'}
      </span>
    </header>
  )
}
