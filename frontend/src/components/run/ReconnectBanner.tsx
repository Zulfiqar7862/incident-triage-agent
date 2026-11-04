import { Button } from '@/components/ui/button'

export function ReconnectBanner({
  message,
  onReconnect,
}: {
  message: string
  onReconnect: () => void
}) {
  return (
    <div
      className="banner visible flex items-center gap-2.5 border-b border-[var(--color-border)] bg-[var(--color-warning-soft)] px-[18px] py-2 text-[13px] text-[var(--color-warning)]"
      role="status"
      data-testid="sse-banner"
    >
      <span>{message}</span>
      <Button className="ml-auto" size="sm" onClick={onReconnect}>
        Reconnect now
      </Button>
    </div>
  )
}
