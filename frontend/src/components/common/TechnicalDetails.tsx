import * as Collapsible from '@radix-ui/react-collapsible'
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'

/** Collapsed raw JSON / text, for engineers only. */
export function TechnicalDetails({
  data,
  label = 'Technical details',
}: {
  data: unknown
  label?: string
}) {
  const [open, setOpen] = useState(false)
  let raw = ''
  try {
    raw = typeof data === 'string' ? data : JSON.stringify(data, null, 2)
  } catch {
    raw = String(data)
  }
  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="mt-2">
      <Collapsible.Trigger
        className="inline-flex items-center gap-1 text-xs font-medium text-[var(--color-fg-tertiary)] hover:text-[var(--color-fg-secondary)]"
        data-testid="technical-details-trigger"
      >
        <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} />
        {label}
      </Collapsible.Trigger>
      <Collapsible.Content>
        <pre
          className="mt-1.5 max-h-56 overflow-auto rounded-md border border-[var(--color-border)] bg-[var(--color-subtle)] p-2.5 font-mono text-[11px] text-[var(--color-fg-tertiary)] whitespace-pre-wrap"
          data-testid="technical-details"
        >
          {raw}
        </pre>
      </Collapsible.Content>
    </Collapsible.Root>
  )
}
