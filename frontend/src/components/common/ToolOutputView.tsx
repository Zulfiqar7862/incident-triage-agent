import { DataView, TechnicalDetails } from '@/components/common/DataView'
import { formatScalar, parseMaybeJson } from '@/lib/dataDisplay'
import { humanizeKey } from '@/lib/errors'
import { num } from '@/lib/format'

function isObj(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

function LogLines({ text }: { text: string }) {
  const lines = text.split('\n').filter((l) => l.length > 0)
  const header = lines[0]?.startsWith('#') ? lines[0] : null
  const body = header ? lines.slice(1) : lines
  return (
    <div data-testid="tool-logs">
      {header ? <p className="mt-0 mb-2 text-xs text-[var(--color-fg-secondary)]">{header.replace(/^#\s*/, '')}</p> : null}
      <ol className="m-0 max-h-72 list-none space-y-1 overflow-auto rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] p-2.5">
        {body.map((line, i) => (
          <li key={i} className="border-b border-[var(--color-border)]/60 pb-1 font-mono text-[11.5px] leading-snug last:border-0">
            {line}
          </li>
        ))}
      </ol>
    </div>
  )
}

function MetricsView({ data }: { data: Record<string, unknown> }) {
  const points = Array.isArray(data.points) ? (data.points as Array<Record<string, unknown>>) : []
  const latest = points.length ? points[points.length - 1] : null
  return (
    <div className="space-y-3" data-testid="tool-metrics">
      <dl className="m-0 grid grid-cols-[minmax(7rem,32%)_1fr] gap-x-4 gap-y-2 text-sm">
        {(['service', 'metric', 'unit', 'window_minutes', 'baseline'] as const).map((k) =>
          data[k] != null ? (
            <div key={k} className="contents">
              <dt className="font-medium text-[var(--color-fg-secondary)]">{humanizeKey(k)}</dt>
              <dd className="m-0">{formatScalar(data[k], k)}</dd>
            </div>
          ) : null,
        )}
        {latest ? (
          <div className="contents">
            <dt className="font-medium text-[var(--color-fg-secondary)]">Latest</dt>
            <dd className="m-0 font-semibold">
              {formatScalar(latest.value, String(data.metric || ''))}
              <span className="ml-2 text-xs font-normal text-[var(--color-fg-tertiary)]">
                ({formatScalar(latest.minutes_ago, 'minutes_ago')} min ago)
              </span>
            </dd>
          </div>
        ) : null}
      </dl>
      {points.length ? (
        <div>
          <div className="mb-1 text-xs font-semibold text-[var(--color-fg-secondary)]">Recent samples</div>
          <DataView data={points.slice(-12)} compact />
        </div>
      ) : null}
    </div>
  )
}

function DeploysView({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="space-y-3" data-testid="tool-deploys">
      <dl className="m-0 grid grid-cols-[minmax(7rem,32%)_1fr] gap-x-4 gap-y-2 text-sm">
        <div className="contents">
          <dt className="font-medium text-[var(--color-fg-secondary)]">Service</dt>
          <dd className="m-0">{formatScalar(data.service)}</dd>
        </div>
        <div className="contents">
          <dt className="font-medium text-[var(--color-fg-secondary)]">Current version</dt>
          <dd className="m-0 font-semibold">{formatScalar(data.current_version)}</dd>
        </div>
      </dl>
      {Array.isArray(data.deploys) ? (
        <div>
          <div className="mb-1 text-xs font-semibold text-[var(--color-fg-secondary)]">Deploy history</div>
          <DataView data={data.deploys} compact />
        </div>
      ) : null}
      {Array.isArray(data.actions_during_this_incident) && data.actions_during_this_incident.length ? (
        <div>
          <div className="mb-1 text-xs font-semibold text-[var(--color-fg-secondary)]">Actions this incident</div>
          <DataView data={data.actions_during_this_incident} compact />
        </div>
      ) : null}
    </div>
  )
}

function RunbooksView({ data }: { data: unknown }) {
  const list = Array.isArray(data) ? data : isObj(data) && Array.isArray(data.results) ? data.results : null
  if (!list) return <DataView data={data} />
  return (
    <div className="space-y-3" data-testid="tool-runbooks">
      {list.map((rb, i) => {
        const r = isObj(rb) ? rb : { title: String(rb) }
        return (
          <article key={i} className="rounded-[10px] border border-[var(--color-border)] bg-[var(--color-elevated)] p-3">
            <h4 className="m-0 text-sm font-semibold">{formatScalar(r.title || r.name || `Runbook ${i + 1}`)}</h4>
            {r.score != null ? (
              <p className="mt-1 mb-0 text-xs text-[var(--color-fg-tertiary)]">Match score {formatScalar(r.score, 'score')}</p>
            ) : null}
            {r.excerpt || r.summary || r.content ? (
              <p className="mt-2 mb-0 text-sm leading-relaxed text-[var(--color-fg-secondary)]">
                {String(r.excerpt || r.summary || r.content)}
              </p>
            ) : (
              <div className="mt-2">
                <DataView data={r} compact />
              </div>
            )}
          </article>
        )
      })}
    </div>
  )
}

function ServicesView({ data }: { data: unknown }) {
  return (
    <div data-testid="tool-services">
      <DataView data={data} />
    </div>
  )
}

export function ToolArgsView({ args }: { args: Record<string, unknown> }) {
  const entries = Object.entries(args || {})
  if (!entries.length) return <p className="m-0 text-sm text-[var(--color-fg-tertiary)]">No arguments</p>
  return <DataView data={args} compact />
}

export function ToolOutputView({
  toolName,
  content,
}: {
  toolName: string
  content: string
}) {
  if (!content) return <p className="m-0 text-sm text-[var(--color-fg-tertiary)]">No output</p>

  if (toolName === 'search_logs' || (!content.trim().startsWith('{') && content.includes('\n') && /^\d{4}-\d{2}-\d{2}T|# /.test(content))) {
    return (
      <>
        <LogLines text={content} />
        <TechnicalDetails data={content} />
      </>
    )
  }

  const parsed = parseMaybeJson(content)

  if (typeof parsed === 'string') {
    return (
      <>
        <p className="m-0 whitespace-pre-wrap text-sm leading-relaxed">{parsed}</p>
        <TechnicalDetails data={parsed} />
      </>
    )
  }

  if (toolName === 'query_metrics' && isObj(parsed)) {
    return (
      <>
        <MetricsView data={parsed} />
        <TechnicalDetails data={parsed} />
      </>
    )
  }
  if (toolName === 'get_recent_deploys' && isObj(parsed)) {
    return (
      <>
        <DeploysView data={parsed} />
        <TechnicalDetails data={parsed} />
      </>
    )
  }
  if (toolName === 'search_runbooks') {
    return (
      <>
        <RunbooksView data={parsed} />
        <TechnicalDetails data={parsed} />
      </>
    )
  }
  if (toolName === 'list_services' || toolName === 'describe_service' || toolName === 'get_alert') {
    return (
      <>
        <ServicesView data={parsed} />
        <TechnicalDetails data={parsed} />
      </>
    )
  }
  if ((toolName === 'rollback_deploy' || toolName === 'restart_service') && isObj(parsed)) {
    return (
      <>
        <div className="rounded-[10px] border border-[var(--color-success-border,var(--color-border))] bg-[var(--color-success-soft)] p-3 text-sm">
          <div className="font-semibold text-[var(--color-success)]">{parsed.ok === false ? 'Change failed' : 'Change applied'}</div>
          <p className="mt-1 mb-0 leading-relaxed">{formatScalar(parsed.message || parsed)}</p>
          {parsed.idempotent_replay ? (
            <p className="mt-1 mb-0 text-xs text-[var(--color-fg-tertiary)]">Idempotent replay — already applied earlier.</p>
          ) : null}
        </div>
        <TechnicalDetails data={parsed} />
      </>
    )
  }
  if (toolName === 'finish' && isObj(parsed)) {
    return (
      <>
        <DataView data={parsed} />
        <TechnicalDetails data={parsed} />
      </>
    )
  }

  return (
    <>
      <DataView data={parsed} />
      <TechnicalDetails data={parsed} />
      {Array.isArray(parsed) ? (
        <p className="mt-1 mb-0 text-[11px] text-[var(--color-fg-tertiary)]">{num(parsed.length)} items</p>
      ) : null}
    </>
  )
}
