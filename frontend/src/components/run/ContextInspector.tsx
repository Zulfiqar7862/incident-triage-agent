import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { fetchContext } from '@/lib/api'
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
  const q = useQuery({
    queryKey: ['context', runId],
    queryFn: () => fetchContext(runId),
    enabled: open,
  })

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/55 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[88vh] w-[min(920px,94vw)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-[14px] border border-[var(--color-border)] bg-[var(--color-elevated)] shadow-xl">
          <div className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3.5">
            <Dialog.Title className="m-0 text-[15px] font-semibold">What the model sees on its next step</Dialog.Title>
            <Dialog.Close asChild>
              <Button>Close</Button>
            </Dialog.Close>
          </div>
          <div className="overflow-auto p-4">
            {q.isLoading ? <p className="text-sm text-[var(--color-fg-tertiary)]">Loading context…</p> : null}
            {q.error ? (
              <p className="text-sm text-[var(--color-danger)]">{(q.error as Error).message}</p>
            ) : null}
            {q.data ? (
              <>
                <p className="mt-0 text-xs text-[var(--color-fg-secondary)]">
                  Rebuilt from the latest checkpoint. About {num(q.data.stats.total_tokens)} of{' '}
                  {num(q.data.stats.budget)} tokens.
                </p>
                <div className="mb-3">
                  <div className="mb-1 text-xs font-semibold text-[var(--color-fg-secondary)]">System prompt</div>
                  <pre className="max-h-60 overflow-auto rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] p-2.5 font-mono text-[11.5px] whitespace-pre-wrap">
                    {q.data.system}
                  </pre>
                </div>
                {q.data.messages.map((m, i) => {
                  const role = String(m.role || '')
                  const label =
                    role === 'tool'
                      ? `Tool result: ${String(m.name || '')}`
                      : role === 'assistant'
                        ? 'Agent'
                        : 'User'
                  const body =
                    role === 'assistant'
                      ? `${m.text ? String(m.text) + '\n' : ''}${((m.tool_calls as Array<{ name: string; args: unknown }>) || [])
                          .map((t) => `→ ${t.name}(${JSON.stringify(t.args)})`)
                          .join('\n')}`
                      : String(m.content || '')
                  return (
                    <div key={i} className="mb-3">
                      <div className="mb-1 text-xs font-semibold text-[var(--color-fg-secondary)]">{label}</div>
                      <pre className="max-h-60 overflow-auto rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] p-2.5 font-mono text-[11.5px] whitespace-pre-wrap">
                        {body}
                      </pre>
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
