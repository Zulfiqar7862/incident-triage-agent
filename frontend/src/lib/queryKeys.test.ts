import { describe, expect, it } from 'vitest'
import { queryKeys } from './queryKeys'

describe('queryKeys', () => {
  it('keeps run keys scoped so invalidating one run does not touch another', () => {
    expect(queryKeys.run('run-a')).toEqual(['run', 'run-a'])
    expect(queryKeys.run('run-a')).not.toEqual(queryKeys.run('run-b'))
    expect(queryKeys.runs).toEqual(['runs'])
    expect(queryKeys.context('run-a')).toEqual(['context', 'run-a'])
  })
})
