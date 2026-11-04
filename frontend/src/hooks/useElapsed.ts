import { useEffect, useState } from 'react'
import { TERMINAL, type RunStatus } from '@/lib/types'

export function useElapsed(createdAt: number | undefined, status: RunStatus | undefined) {
  const [now, setNow] = useState(() => Date.now() / 1000)
  const terminal = status ? TERMINAL.includes(status) : true

  useEffect(() => {
    if (!createdAt || terminal) return
    const id = window.setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => window.clearInterval(id)
  }, [createdAt, terminal])

  if (!createdAt) return 0
  return Math.max(0, now - createdAt)
}
