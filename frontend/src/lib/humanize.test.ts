import { describe, expect, it } from 'vitest'
import {
  confidenceLabel,
  describeTool,
  humanizeEmbeddedCalls,
  looksLikeFunctionCall,
  severityLabel,
  statusLabel,
  toolNoun,
} from './humanize'

describe('describeTool', () => {
  it('maps write tools to plain sentences', () => {
    expect(describeTool('rollback_deploy', { service: 'checkout-service', to_version: 'v2.13.2' })).toBe(
      'Roll back checkout-service to version v2.13.2',
    )
    expect(describeTool('restart_service', { service: 'checkout-service' })).toBe('Restart checkout-service')
    expect(describeTool('scale_service', { service: 'api', replicas: 5 })).toBe('Scale api to 5 instances')
  })

  it('maps read tools', () => {
    expect(describeTool('search_logs', { service: 'checkout-service', query: 'ERROR' })).toContain('checkout-service')
    expect(describeTool('query_metrics', { service: 'payments', metric: 'error_rate' })).toContain('error rate')
    expect(describeTool('get_alert')).toMatch(/alert/i)
  })

  it('never emits function-call style text', () => {
    const s = describeTool('rollback_deploy', {
      service: 'checkout-service',
      to_version: 'v2.13.2',
      confidence: 0.85,
    })
    expect(looksLikeFunctionCall(s)).toBe(false)
    expect(s).not.toMatch(/\w+_\w+\(/)
    expect(toolNoun('rollback_deploy')).toBe('Rollback')
  })

  it('falls back without parentheses or underscores', () => {
    const s = describeTool('custom_probe_tool', { service: 'web' })
    expect(s).not.toContain('_')
    expect(s).not.toContain('(')
  })
})

describe('humanizeEmbeddedCalls', () => {
  it('rewrites approval status strings from the API', () => {
    const raw =
      'Approve, edit, or reject rollback_deploy(service=checkout-service, to_version=v2.13.2, confidence=0.85).'
    const out = humanizeEmbeddedCalls(raw)
    expect(looksLikeFunctionCall(out)).toBe(false)
    expect(out).not.toMatch(/\w+_\w+\(/)
    expect(out.toLowerCase()).toContain('roll back')
    expect(out).toContain('checkout-service')
    expect(out).toContain('v2.13.2')
  })
})

describe('labels', () => {
  it('formats confidence and severity for operators', () => {
    expect(confidenceLabel(0.85)).toEqual({ percent: 85, phrase: 'likely safe', tone: 'ok' })
    expect(severityLabel('P1')).toBe('Priority: Critical')
    expect(statusLabel('awaiting_approval')).toBe('Needs your approval')
  })
})
