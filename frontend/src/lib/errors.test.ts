import { describe, expect, it } from 'vitest'
import { ApiError } from '@/lib/api'
import { humanizeKey, mapError } from '@/lib/errors'

describe('mapError', () => {
  it('maps network failures', () => {
    const f = mapError(new TypeError('Failed to fetch'))
    expect(f.kind).toBe('network')
    expect(f.title).toMatch(/Cannot reach/i)
    expect(f.actionLabel).toBe('Retry')
  })

  it('maps auth, not found, conflict, validation, rate limit, 5xx', () => {
    expect(mapError(new ApiError(401, 'nope')).kind).toBe('auth')
    expect(mapError(new ApiError(404, 'missing')).title).toMatch(/not found/i)
    expect(mapError(new ApiError(409, 'cas')).kind).toBe('conflict')
    const v = mapError(new ApiError(422, 'service: field required; confidence: ensure <= 1'))
    expect(v.kind).toBe('validation')
    expect(v.explanation).toMatch(/Service/i)
    expect(mapError(new ApiError(429, 'slow down')).kind).toBe('rate_limit')
    expect(mapError(new ApiError(503, 'boom')).kind).toBe('server')
  })

  it('maps SSE disconnects', () => {
    const f = mapError('EventSource failed', { sse: true })
    expect(f.kind).toBe('sse')
    expect(f.title).toMatch(/Live updates/i)
  })

  it('humanizes keys', () => {
    expect(humanizeKey('error_rate')).toBe('Error Rate')
    expect(humanizeKey('to_version')).toBe('To Version')
  })
})
