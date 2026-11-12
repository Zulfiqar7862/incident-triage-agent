import { describe, expect, it } from 'vitest'
import { streamReducer, type StreamState } from './useRunStream'
import type { AgentEvent } from '@/types/api'

const base: StreamState = {
  events: [],
  cursor: 0,
  connected: false,
  reconnecting: false,
  error: null,
}

describe('streamReducer', () => {
  it('appends events and advances cursor', () => {
    const ev = { seq: 3, run_id: 'r1', type: 'run.created', payload: {} } as AgentEvent
    const next = streamReducer(base, { type: 'event', event: ev })
    expect(next.events).toHaveLength(1)
    expect(next.cursor).toBe(3)
  })

  it('dedupes by seq', () => {
    const ev = { seq: 1, run_id: 'r1', type: 'run.status', payload: {} } as AgentEvent
    const s1 = streamReducer(base, { type: 'event', event: ev })
    const s2 = streamReducer(s1, { type: 'event', event: ev })
    expect(s2.events).toHaveLength(1)
  })

  it('marks reconnecting on error', () => {
    const next = streamReducer({ ...base, connected: true }, { type: 'error', message: 'down' })
    expect(next.connected).toBe(false)
    expect(next.reconnecting).toBe(true)
    expect(next.error).toBe('down')
  })
})
