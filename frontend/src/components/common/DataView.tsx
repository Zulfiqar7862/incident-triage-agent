import type { ReactNode } from 'react'
import { humanizeKey } from '@/lib/errors'
import { formatScalar, statusTone } from '@/lib/dataDisplay'
import { cn } from '@/lib/utils'
import { TechnicalDetails } from './TechnicalDetails'
import { Truncated } from './Truncated'

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'ok' | 'warn' | 'danger' | 'accent'
}) {
  const tones = {
    neutral: 'bg-[var(--color-muted)] text-[var(--color-fg-secondary)]',
    ok: 'bg-[var(--color-success-soft)] text-[var(--color-success)]',
    warn: 'bg-[var(--color-warning-soft)] text-[var(--color-warning)]',
    danger: 'bg-[var(--color-danger-soft)] text-[var(--color-danger)]',
    accent: 'bg-[var(--color-accent-soft)] text-[var(--color-accent)]',
  }
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold',
        tones[tone],
      )}
    >
      {children}
    </span>
  )
}

function arrayOfObjects(arr: unknown[]): arr is Record<string, unknown>[] {
  return arr.length > 0 && arr.every(isPlainObject)
}

function TableFromObjects({ rows }: { rows: Record<string, unknown>[] }) {
  const keys = Array.from(new Set(rows.flatMap((r) => Object.keys(r)))).slice(0, 8)
  return (
    <div className="overflow-auto rounded-md border border-[var(--color-border)]">
      <table className="w-full min-w-[320px] border-collapse text-left text-[12.5px]">
        <thead className="bg-[var(--color-subtle)] text-[var(--color-fg-secondary)]">
          <tr>
            {keys.map((k) => (
              <th key={k} className="px-2.5 py-1.5 font-semibold">
                {humanizeKey(k)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 40).map((row, i) => (
            <tr key={i} className="border-t border-[var(--color-border)]">
              {keys.map((k) => (
                <td key={k} className="px-2.5 py-1.5 align-top text-[var(--color-fg)]">
                  {isPlainObject(row[k]) || Array.isArray(row[k]) ? (
                    <DataView data={row[k]} depth={1} compact />
                  ) : (
                    <Truncated text={formatScalar(row[k], k)} />
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 40 ? (
        <div className="border-t border-[var(--color-border)] px-2.5 py-1 text-[11px] text-[var(--color-fg-tertiary)]">
          Showing 40 of {rows.length}
        </div>
      ) : null}
    </div>
  )
}

type DataViewProps = {
  data: unknown
  depth?: number
  compact?: boolean
  className?: string
}

export function DataView({ data, depth = 0, compact = false, className }: DataViewProps) {
  if (data == null) {
    return <span className="text-[var(--color-fg-tertiary)]">—</span>
  }

  if (typeof data !== 'object') {
    const text = formatScalar(data)
    return (
      <span className={cn('text-sm text-[var(--color-fg)]', className)} data-testid="data-view">
        <Truncated text={text} />
      </span>
    )
  }

  if (Array.isArray(data)) {
    if (data.length === 0) {
      return <span className="text-sm text-[var(--color-fg-tertiary)]">None</span>
    }
    if (arrayOfObjects(data)) {
      return (
        <div className={className} data-testid="data-view">
          <TableFromObjects rows={data} />
        </div>
      )
    }
    if (data.every((x) => typeof x !== 'object' || x == null)) {
      return (
        <ul
          className={cn('m-0 list-disc space-y-1 pl-4 text-sm', className)}
          data-testid="data-view"
        >
          {data.map((item, i) => (
            <li key={i}>
              <Truncated text={formatScalar(item)} />
            </li>
          ))}
        </ul>
      )
    }
    return (
      <div className={cn('space-y-2', className)} data-testid="data-view">
        {data.map((item, i) => (
          <div
            key={i}
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] p-2.5"
          >
            <DataView data={item} depth={depth + 1} compact />
          </div>
        ))}
      </div>
    )
  }

  const entries = Object.entries(data as Record<string, unknown>)
  if (!entries.length) {
    return <span className="text-sm text-[var(--color-fg-tertiary)]">Empty</span>
  }

  return (
    <dl
      className={cn(
        'm-0 grid gap-x-4 gap-y-2',
        compact
          ? 'grid-cols-[minmax(5rem,30%)_1fr] text-[12.5px]'
          : 'grid-cols-[minmax(7rem,32%)_1fr] text-sm',
        className,
      )}
      data-testid="data-view"
    >
      {entries.map(([key, value]) => {
        const label = humanizeKey(key)
        let body: ReactNode
        if (isPlainObject(value) || Array.isArray(value)) {
          if (depth >= 3) {
            body = <TechnicalDetails data={value} label={`Expand ${label.toLowerCase()}`} />
          } else {
            body = <DataView data={value} depth={depth + 1} compact />
          }
        } else if (
          typeof value === 'string' &&
          (key === 'status' || key === 'severity' || /status|severity|level/i.test(key))
        ) {
          body = <Badge tone={statusTone(value)}>{formatScalar(value, key)}</Badge>
        } else if (typeof value === 'boolean') {
          body = <Badge tone={value ? 'ok' : 'neutral'}>{formatScalar(value, key)}</Badge>
        } else {
          body = <Truncated text={formatScalar(value, key)} />
        }
        return (
          <div key={key} className="contents">
            <dt className="font-medium text-[var(--color-fg-secondary)]">{label}</dt>
            <dd className="m-0 min-w-0 text-[var(--color-fg)]">{body}</dd>
          </div>
        )
      })}
    </dl>
  )
}
