import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function load() {
  const source = readFileSync(new URL('../server/utils/origin.ts', import.meta.url), 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }
  }).outputText
  // `URL` is not a JS intrinsic, so it must be supplied explicitly to the
  // sandbox; the Nitro runtime has it as a global.
  const context = { exports: {}, URL }
  vm.runInNewContext(output, context)
  return context.exports
}

function check(overrides) {
  const { checkRequestOrigin } = load()
  return { ...checkRequestOrigin({ origin: null, referer: null, host: null, forwardedHost: null, allowedOrigins: [], ...overrides }) }
}

test('same-host requests are accepted for localhost, IPv4 and IPv6 hosts', () => {
  for (const host of ['localhost:3000', '127.0.0.1:3000', '[::1]:3000']) {
    assert.deepEqual(check({ origin: `http://${host}`, host }), { allowed: true, reason: 'same-host' }, host)
  }
})

test('a referer-only same-host request is accepted', () => {
  assert.deepEqual(
    check({ referer: 'http://localhost:3000/admin/login', host: 'localhost:3000' }),
    { allowed: true, reason: 'same-host' }
  )
})

test('a foreign origin is rejected', () => {
  assert.deepEqual(
    check({ origin: 'http://evil.example', host: 'localhost:3000' }),
    { allowed: false, reason: 'unexpected-origin' }
  )
})

test('a configured origin is accepted even when it differs from the request host', () => {
  assert.deepEqual(
    check({ origin: 'http://localhost:3000', host: '127.0.0.1:3000', allowedOrigins: ['http://localhost:3000'] }),
    { allowed: true, reason: 'configured' }
  )
})

test('a request with no origin or referer is treated as a non-browser client', () => {
  assert.deepEqual(
    check({ host: 'localhost:3000' }),
    { allowed: true, reason: 'no-origin-header' }
  )
})
