import { useCallback, useEffect, useReducer, useRef } from 'react'
import { streamUrl } from '@/lib/api'
import type { AgentEvent } from '@/lib/types'
import { useUiStore } from '@/store/uiStore'

export type StreamState = {
  events: AgentEvent[]
  cursor: number
  connected: boolean
  reconnecting: boolean
  error: string | null
}

type Action =
  | { type: 'reset' }
  | { type: 'open' }
  | { type: 'event'; event: AgentEvent }
  | { type: 'error'; message: string }
  | { type: 'reconnecting' }
  | { type: 'end' }

export function streamReducer(state: StreamState, action: Action): StreamState {
  switch (action.type) {
    case 'reset':
      return { events: [], cursor: 0, connected: false, reconnecting: false, error: null }
    case 'open':
      return { ...state, connected: true, reconnecting: false, error: null }
    case 'event': {
      if (state.events.some((e) => e.seq === action.event.seq)) return state
      const events = [...state.events, action.event]
      return { ...state, events, cursor: Math.max(state.cursor, action.event.seq) }
    }
    case 'error':
      return { ...state, connected: false, reconnecting: true, error: action.message }
    case 'reconnecting':
      return { ...state, connected: false, reconnecting: true }
    case 'end':
      return { ...state, connected: false, reconnecting: false }
    default:
      return state
  }
}

function phaseFromEvent(ev: AgentEvent): string | null {
  switch (ev.type) {
    case 'run.created':
      return 'Starting run…'
    case 'memory.recalled':
      return 'Recalling past incidents…'
    case 'llm.call':
      return 'Agent is thinking…'
    case 'llm.retry':
      return 'Trying again…'
    case 'agent.message':
      return 'Updating the plan…'
    case 'tool.call': {
      const name = String(ev.payload.name || '')
      if (name === 'update_working_memory') return 'Agent is thinking…'
      return 'Gathering evidence…'
    }
    case 'tool.result':
      return 'Reading results…'
    case 'memory.update':
      return 'Agent is thinking…'
    case 'approval.requested':
      return 'Waiting for your approval…'
    case 'input.requested':
      return 'Waiting for your answer…'
    case 'run.finished':
      return null
    default:
      return null
  }
}

export function useRunStream(runId: string | null) {
  const [state, dispatch] = useReducer(streamReducer, {
    events: [],
    cursor: 0,
    connected: false,
    reconnecting: false,
    error: null,
  })
  const cursorRef = useRef(0)
  const retryRef = useRef(0)
  const esRef = useRef<EventSource | null>(null)
  const timerRef = useRef<number | null>(null)
  const setSseDisconnected = useUiStore((s) => s.setSseDisconnected)
  const setThinkingPhase = useUiStore((s) => s.setThinkingPhase)

  const disconnect = useCallback(() => {
    if (timerRef.current) window.clearTimeout(timerRef.current)
    if (esRef.current) {
      try {
        esRef.current.close()
      } catch {
        /* */
      }
      esRef.current = null
    }
  }, [])

  const connectRef = useRef<(id: string) => void>(() => undefined)

  const connect = useCallback(
    (id: string) => {
      disconnect()
      const es = new EventSource(streamUrl(id, cursorRef.current))
      esRef.current = es

      es.onopen = () => {
        retryRef.current = 0
        dispatch({ type: 'open' })
        setSseDisconnected(false)
      }

      es.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data) as AgentEvent
          if (e.lastEventId)
            cursorRef.current = Math.max(cursorRef.current, Number(e.lastEventId) || 0)
          else if (ev.seq) cursorRef.current = Math.max(cursorRef.current, ev.seq)
          if (ev.run_id === id) {
            dispatch({ type: 'event', event: ev })
            const phase = phaseFromEvent(ev)
            if (phase !== null) setThinkingPhase(phase)
            if (ev.type === 'run.finished') setThinkingPhase(null)
          }
        } catch (err) {
          console.warn('bad SSE frame', err)
        }
      }

      es.addEventListener('end', () => {
        dispatch({ type: 'end' })
        setThinkingPhase(null)
        disconnect()
      })

      es.onerror = () => {
        disconnect()
        setSseDisconnected(true)
        dispatch({ type: 'reconnecting' })
        const delay = Math.min(1000 * 2 ** retryRef.current, 15000)
        retryRef.current += 1
        dispatch({
          type: 'error',
          message: `Live stream disconnected. Reconnecting in ${Math.round(delay / 1000)}s…`,
        })
        timerRef.current = window.setTimeout(() => {
          if (runId === id) connectRef.current(id)
        }, delay)
      }
    },
    [disconnect, runId, setSseDisconnected, setThinkingPhase],
  )

  useEffect(() => {
    connectRef.current = connect
  }, [connect])

  useEffect(() => {
    cursorRef.current = 0
    retryRef.current = 0
    dispatch({ type: 'reset' })
    setThinkingPhase(null)
    if (!runId) {
      disconnect()
      setSseDisconnected(false)
      return
    }
    connect(runId)
    return () => disconnect()
  }, [runId, connect, disconnect, setThinkingPhase, setSseDisconnected])

  const reconnectNow = useCallback(() => {
    if (runId) {
      retryRef.current = 0
      connect(runId)
    }
  }, [runId, connect])

  return { ...state, reconnectNow }
}
