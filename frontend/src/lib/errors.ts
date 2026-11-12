import { ApiError } from './api'

export type FriendlyError = {
  title: string
  explanation: string
  nextStep: string
  actionLabel?: string
  technical?: string
  kind:
    | 'network'
    | 'auth'
    | 'not_found'
    | 'conflict'
    | 'validation'
    | 'rate_limit'
    | 'server'
    | 'run_failed'
    | 'sse'
    | 'unknown'
}

function detailText(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  try {
    return JSON.stringify(err)
  } catch {
    return String(err)
  }
}

function isNetwork(err: unknown): boolean {
  if (err instanceof TypeError) return true
  const msg = detailText(err).toLowerCase()
  return (
    msg.includes('failed to fetch') ||
    msg.includes('networkerror') ||
    msg.includes('network request failed') ||
    msg.includes('load failed') ||
    msg.includes('err_connection')
  )
}

/** Map API / SSE / agent errors to short operator-facing copy. */
function fallbackError(
  err: unknown,
  context?: { runFailed?: boolean; sse?: boolean },
): FriendlyError {
  const technical = detailText(err)

  if (
    context?.sse ||
    technical.toLowerCase().includes('sse') ||
    technical.toLowerCase().includes('eventsource')
  ) {
    return {
      kind: 'sse',
      title: 'Live updates paused',
      explanation: 'The connection to the live event stream dropped.',
      nextStep: 'We will keep trying to reconnect. You can also refresh the run.',
      actionLabel: 'Reconnect',
      technical,
    }
  }

  if (isNetwork(err)) {
    return {
      kind: 'network',
      title: 'Cannot reach the server',
      explanation: 'The operator console could not talk to the triage API.',
      nextStep: 'Check that the backend is running, then try again.',
      actionLabel: 'Retry',
      technical,
    }
  }

  if (err instanceof ApiError) {
    switch (err.status) {
      case 401:
      case 403:
        return {
          kind: 'auth',
          title: 'Sign-in required',
          explanation: 'This server needs a valid API token before it will show run data.',
          nextStep: 'Paste your API token when prompted, or ask your admin for access.',
          actionLabel: 'Retry',
          technical,
        }
      case 404:
        return {
          kind: 'not_found',
          title: 'Run not found',
          explanation: 'That triage run is missing or was deleted.',
          nextStep: 'Pick another run from the sidebar, or start a new scenario.',
          actionLabel: 'Back to runs',
          technical,
        }
      case 409:
        return {
          kind: 'conflict',
          title: 'Already handled',
          explanation: 'The decision was already handled, or the investigation has moved on.',
          nextStep: 'Refresh the run to see the latest state.',
          actionLabel: 'Refresh',
          technical,
        }
      case 422: {
        return {
          kind: 'validation',
          title: 'That input looks off',
          explanation:
            'One or more fields could not be accepted. Review your entries and try again.',
          nextStep: 'Fix the highlighted fields and try again.',
          actionLabel: 'Retry',
          technical,
        }
      }
      case 429:
        return {
          kind: 'rate_limit',
          title: 'Model is rate-limited',
          explanation: 'The language model provider asked us to slow down.',
          nextStep:
            'Wait a moment, then resume the run. A fallback model may be used automatically.',
          actionLabel: 'Retry',
          technical,
        }
      default:
        if (err.status >= 500) {
          return {
            kind: 'server',
            title: 'Something went wrong on the server',
            explanation: 'The triage API hit an unexpected error.',
            nextStep: 'Retry in a few seconds. If it keeps failing, check server logs.',
            actionLabel: 'Retry',
            technical,
          }
        }
    }
  }

  if (context?.runFailed || /failed|crash|traceback/i.test(technical)) {
    return {
      kind: 'run_failed',
      title: 'This run stopped with an error',
      explanation: 'The agent could not finish investigating this incident.',
      nextStep: 'Read the summary in the timeline, then resume or start a fresh run.',
      actionLabel: 'Refresh',
      technical,
    }
  }

  return {
    kind: 'unknown',
    title: 'Something went wrong',
    explanation: 'The console hit an unexpected problem.',
    nextStep: 'Try again. If it persists, open Technical details and share them with your team.',
    actionLabel: 'Retry',
    technical,
  }
}

export function humanizeKey(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_./-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function toastFriendlyError(err: unknown, toastFn: (msg: string) => void) {
  const f = mapError(err)
  toastFn(`${f.title} — ${f.explanation}`)
}

/** Prefer the API-owned error projection; legacy/transport failures use safe static copy. */
export function mapError(
  err: unknown,
  context?: { runFailed?: boolean; sse?: boolean },
): FriendlyError {
  const friendly = fallbackError(err, context)
  if (err instanceof ApiError && err.operator)
    return { ...friendly, title: err.operator.title, explanation: err.operator.summary }
  return friendly
}
