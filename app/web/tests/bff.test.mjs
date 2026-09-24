import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function handler({ retryStatus, refreshStatus, initialStatus = 401 }) {
  const source = readFileSync(new URL('../server/api/hrms/[...path].ts', import.meta.url), 'utf8').replace(/import\s*\{[\s\S]*?from [^\n]+\n/, '').replace('export default', 'globalThis.handler =')
  const calls = { upstream: 0, refresh: 0, clear: 0, access: 0, refreshCookie: 0 }
  const context = {
    defineEventHandler: fn => fn, getRouterParam: () => 'leaves/1/approve', getMethod: () => 'PATCH', getQuery: () => ({ page: '2' }), readBody: async () => ({}), apiUrl: () => '/api/v1/leaves/1/approve',
    getCookie: () => 'cookie', SESSION_COOKIE: 'access', REFRESH_COOKIE: 'refresh',
    upstreamStatus: error => error.statusCode, upstreamError: error => error,
    clearSessionCookies: () => calls.clear++, setAccessCookie: () => calls.access++, setRefreshCookie: () => calls.refreshCookie++,
    refreshSession: async () => {
      calls.refresh++
      if (refreshStatus) throw { statusCode: refreshStatus }
      return { access_token: 'new', refresh_token: 'rotated', expires_in: 900 }
    },
    $fetch: async (_url, options) => {
      assert.equal(options.retry, 0)
      calls.upstream++
      if (calls.upstream === 1) throw { statusCode: initialStatus }
      if (retryStatus) throw { statusCode: retryStatus }
      return { ok: true }
    }
  }
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None } }).outputText, context)
  return { call: () => context.handler({}), calls }
}

test('a conflict after successful refresh preserves the session and its real error', async () => {
  const { call, calls } = handler({ retryStatus: 409 })
  await assert.rejects(call, error => error.statusCode === 409)
  assert.deepEqual(calls, { upstream: 2, refresh: 1, clear: 0, access: 1, refreshCookie: 1 })
})

test('refresh outages preserve cookies; rejected refresh credentials clear cookies', async () => {
  for (const status of [401, 502]) {
    const { call, calls } = handler({ refreshStatus: status })
    await assert.rejects(call, error => error.statusCode === status)
    assert.equal(calls.upstream, 1)
    assert.equal(calls.clear, status === 401 ? 1 : 0)
  }
})

test('unsafe writes have no automatic transport retry and no retry for business errors', async () => {
  const { call, calls } = handler({ initialStatus: 403 })
  await assert.rejects(call, error => error.statusCode === 403)
  assert.equal(calls.upstream, 1)
  assert.equal(calls.refresh, 0)
})
