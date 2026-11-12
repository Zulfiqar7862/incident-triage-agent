import * as Dialog from '@radix-ui/react-dialog'
import { DataView, TechnicalDetails } from '@/components/common/DataView'
import { parseMaybeJson } from '@/lib/dataDisplay'
import { ErrorBanner } from '@/components/common/ErrorBanner'
import { Button } from '@/components/ui/button'
import { useRunContext } from '@/features/run/hooks/queries'
import { mapError } from '@/lib/errors'
import { num } from '@/lib/format'

export function ContextInspector({
  runId,
  open,
  onOpenChange,
}: {
  runId: string
  open: boolean
  onOpenChange: (o: boolean) => void
}) {
  const q = useRunContext(runId, open)

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/55 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[88vh] w-[min(920px,94vw)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-[14px] border border-[var(--color-border)] bg-[var(--color-elevated)] shadow-xl">
          <div className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3.5">
            <Dialog.Title className="m-0 text-[15px] font-semibold">Context inspector (for engineers)</Dialog.Title>
            <Dialog.Close asChild>
              <Button>Close</Button>
            </Dialog.Close>
          </div>
          <div className="overflow-auto p-4">
            {q.isLoading ? <p className="text-sm text-[var(--color-fg-tertiary)]">Loading context…</p> : null}
            {q.error ? <ErrorBanner error={mapError(q.error)} onAction={() => void q.refetch()} /> : null}
            {q.data ? (
              <>
                <p className="mt-0 text-xs text-[var(--color-fg-secondary)]">
                  Snapshot of what the assistant will see next. Context size:{' '}
                  {num(q.data.stats.total_tokens)} / {num(q.data.stats.budget)}.
                </p>
                <div className="mb-4">
                  <div className="mb-1 text-xs font-semibold text-[var(--color-fg-secondary)]">System prompt</div>
                  <p className="m-0 max-h-40 overflow-auto rounded-[10px] border border-[var(--color-border)] bg-[var(--color-subtle)] p-3 text-sm leading-relaxed whitespace-pre-wrap">
                    {q.data.system}
                  </p>
                </div>
                {q.data.messages.map((m, i) => {
                  const role = String(m.role || '')
                  const label =
                    role === 'tool'
                      ? `Result: ${String(m.name || '').replaceAll('_', ' ')}`
                      : role === 'assistant'
                        ? 'Assistant'
                        : 'You'
                  return (
                    <div key={i} className="mb-4">
                      <div className="mb-1.5 text-xs font-semibold text-[var(--color-fg-secondary)]">{label}</div>
                      {role === 'assistant' ? (
                        <div className="space-y-2 rounded-[10px] border border-[var(--color-border)] bg-[var(--color-subtle)] p-3">
                          {m.text ? <p className="m-0 text-sm leading-relaxed whitespace-pre-wrap">{String(m.text)}</p> : null}
                          {Array.isArray(m.tool_calls) && m.tool_calls.length ? (
                            <div className="space-y-2">
                              {(m.tool_calls as Array<{ name: string; args: unknown }>).map((t, j) => (
                                <div key={j}>
                                  <div className="text-xs font-medium text-[var(--color-fg-secondary)]">
                                    {String(t.name || '').replaceAll('_', ' ')}
                                  </div>
                                  <DataView data={t.args} compact />
                                </div>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      ) : (
                        <div className="rounded-[10px] border border-[var(--color-border)] bg-[var(--color-subtle)] p-3">
                          {typeof m.content === 'string' ? (
                            (() => {
                              const parsed = parseMaybeJson(String(m.content))
                              return typeof parsed === 'string' ? (
                                <p className="m-0 max-h-48 overflow-auto text-sm leading-relaxed whitespace-pre-wrap">{parsed}</p>
                              ) : (
                                <DataView data={parsed} compact />
                              )
                            })()
                          ) : (
                            <DataView data={m.content} compact />
                          )}
                          <TechnicalDetails data={m} />
                        </div>
                      )}
                    </div>
                  )
                })}
              </>
            ) : null}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
