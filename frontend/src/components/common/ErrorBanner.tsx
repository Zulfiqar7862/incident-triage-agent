import { AlertTriangle, RefreshCw } from 'lucide-react'
import * as Collapsible from '@radix-ui/react-collapsible'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { type FriendlyError } from '@/lib/errors'
import { cn } from '@/lib/utils'

export function ErrorBanner({
  error,
  onAction,
  className,
}: {
  error: FriendlyError
  onAction?: () => void
  className?: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <div
      className={cn(
        'rounded-[12px] border border-[var(--color-danger)]/25 bg-[var(--color-danger-soft)] p-4 text-[var(--color-fg)]',
        className,
      )}
      role="alert"
      data-testid="error-banner"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-[var(--color-danger)]" aria-hidden />
        <div className="min-w-0 flex-1">
          <h3 className="m-0 text-[15px] font-semibold text-[var(--color-danger)]">
            {error.title}
          </h3>
          <p className="mt-1 mb-0 text-sm leading-relaxed text-[var(--color-fg-secondary)]">
            {error.explanation}
          </p>
          <p className="mt-1.5 mb-0 text-sm text-[var(--color-fg)]">
            <span className="font-medium">Next:</span> {error.nextStep}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {onAction && error.actionLabel ? (
              <Button variant="primary" size="sm" onClick={onAction}>
                <RefreshCw className="size-3.5" /> {error.actionLabel}
              </Button>
            ) : null}
            {error.technical ? (
              <Collapsible.Root open={open} onOpenChange={setOpen}>
                <Collapsible.Trigger asChild>
                  <Button size="sm" variant="ghost" aria-expanded={open}>
                    {open ? 'Hide engineering details' : 'For engineers'}
                  </Button>
                </Collapsible.Trigger>
                <Collapsible.Content>
                  <div
                    className="mt-2 max-h-40 overflow-auto rounded-md border border-[var(--color-border)] bg-[var(--color-elevated)] p-2.5 font-mono text-[11px] text-[var(--color-fg-tertiary)] whitespace-pre-wrap"
                    data-testid="error-technical"
                  >
                    {error.technical}
                  </div>
                </Collapsible.Content>
              </Collapsible.Root>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
