/**
 * Import-boundary fitness test (bulletproof-react's unidirectional rule):
 *   shared (components, hooks, lib, stores, types) -> features -> app
 * Shared code never imports a feature or the app; a feature never imports another
 * feature or the app. Composition across features happens in src/app.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import { expect, it } from 'vitest'

const SRC = path.resolve(import.meta.dirname, '..')
const SHARED = ['components', 'hooks', 'lib', 'stores', 'types']
const MAX_COMPONENT_LINES = 200

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name)
    return statSync(full).isDirectory() ? walk(full) : /\.(ts|tsx)$/.test(name) ? [full] : []
  })
}

const files = walk(SRC).map((f) => ({
  rel: path.relative(SRC, f).split(path.sep).join('/'),
  text: readFileSync(f, 'utf8'),
}))

function imports(text: string): string[] {
  return [...text.matchAll(/from\s+['"](@\/[^'"]+)['"]/g)].map((m) => m[1].slice(2))
}

it('keeps shared code free of feature and app imports', () => {
  const bad = files
    .filter((f) => SHARED.includes(f.rel.split('/')[0]))
    .flatMap((f) =>
      imports(f.text)
        .filter((i) => /^(features|app)\//.test(i))
        .map((i) => `${f.rel} -> ${i}`),
    )
  expect(bad).toEqual([])
})

it('keeps features independent of each other and of the app layer', () => {
  const bad = files
    .filter((f) => f.rel.startsWith('features/'))
    .flatMap((f) => {
      const own = f.rel.split('/')[1]
      return imports(f.text)
        .filter(
          (i) => i.startsWith('app/') || (i.startsWith('features/') && i.split('/')[1] !== own),
        )
        .map((i) => `${f.rel} -> ${i}`)
    })
  expect(bad).toEqual([])
})

it('has no barrel files inside features', () => {
  expect(
    files.filter((f) => /^features\/[^/]+\/index\.tsx?$/.test(f.rel)).map((f) => f.rel),
  ).toEqual([])
})

it('keeps components small', () => {
  const big = files
    .filter((f) => f.rel.endsWith('.tsx') && !f.rel.includes('.test.'))
    .map((f) => ({ rel: f.rel, lines: f.text.split('\n').length }))
    .filter((f) => f.lines > MAX_COMPONENT_LINES)
  expect(big).toEqual([])
})
