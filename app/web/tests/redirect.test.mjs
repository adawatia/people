import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function load() {
  const source = readFileSync(new URL('../app/utils/redirect.ts', import.meta.url), 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }
  }).outputText
  const context = { exports: {} }
  vm.runInNewContext(output, context)
  return context.exports
}

test('accepts an absolute path on this origin', () => {
  const { safeInternalPath } = load()
  assert.equal(safeInternalPath('/leaves?page=2'), '/leaves?page=2')
  assert.equal(safeInternalPath('  /dashboard  '), '/dashboard')
})

test('rejects protocol-relative redirects that leave the origin', () => {
  const { safeInternalPath } = load()
  for (const value of ['//evil.example', '/\\evil.example', '///evil.example', '/\\\\evil.example']) {
    assert.equal(safeInternalPath(value), '/', value)
  }
})

test('rejects absolute URLs, relative paths and non-strings', () => {
  const { safeInternalPath } = load()
  for (const value of ['https://evil.example', 'javascript:alert(1)', 'dashboard', '', null, undefined, 42]) {
    assert.equal(safeInternalPath(value), '/', String(value))
  }
})

test('rejects control characters that could smuggle a scheme', () => {
  const { safeInternalPath } = load()
  assert.equal(safeInternalPath('/path\u0000'), '/')
  assert.equal(safeInternalPath('/path\nfoo'), '/')
})

test('honours a custom fallback so callers can skip navigation entirely', () => {
  const { safeInternalPath } = load()
  assert.equal(safeInternalPath('https://evil.example', ''), '')
  assert.equal(safeInternalPath('/ok', ''), '/ok')
})
