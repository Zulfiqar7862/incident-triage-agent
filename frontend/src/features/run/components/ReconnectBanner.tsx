import { Button } from '@/components/ui/button'
import { mapError } from '@/lib/errors'

export function ReconnectBanner({
  message,
  onReconnect,
}: {
  message: string
  onReconnect: () => void
}) {
  const friendly = mapError(message, { sse: true })
  return (
    <div
      className="banner visible flex flex-wrap items-center gap-2.5 border-b border-[var(--color-border)] bg-[var(--color-warning-soft)] px-[18px] py-2.5 text-[13px] text-[var(--color-warning)]"
      role="status"
      data-testid="sse-banner"
    >
      <div className="min-w-0 flex-1">
        <strong className="font-semibold">{friendly.title}.</strong> {friendly.explanation}
      </div>
      <Button className="ml-auto" size="sm" onClick={onReconnect}>
        {friendly.actionLabel || 'Reconnect'}
      </Button>
    </div>
  )
}
