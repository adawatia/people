import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
import vm from 'node:vm'

function loadUpstreamError() {
  const source = readFileSync(new URL('../server/utils/hrms.ts', import.meta.url), 'utf8')
    .replace(/^import type[^\n]+\n/m, '')
    .replaceAll('import.meta.dev', 'true')
    .replace('export function upstreamError', 'function upstreamError')
    .replace('export function upstreamStatus', 'function upstreamStatus')
    + '\nglobalThis.upstreamError = upstreamError'
  const context = {
    createError: value => value,
    setResponseHeader: () => undefined,
    exports: {}
  }
  vm.runInNewContext(
    ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None } }).outputText,
    context
  )
  return context.upstreamError
}

test('BFF preserves a password-policy reason from a 400 response', () => {
  const upstreamError = loadUpstreamError()
  const result = upstreamError({
    statusCode: 400,
    data: { detail: 'This password appears in a known breach. Choose a different one.' }
  })
  assert.equal(result.statusCode, 400)
  assert.equal(result.statusMessage, 'This password appears in a known breach. Choose a different one.')
})

test('BFF gives a useful validation message for a 422 response', () => {
  const upstreamError = loadUpstreamError()
  const result = upstreamError({
    statusCode: 422,
    data: { detail: [{ msg: 'String should have at least 8 characters.' }] }
  })
  assert.equal(result.statusCode, 422)
  assert.equal(result.statusMessage, 'String should have at least 8 characters.')
})
