import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { createRequire } from 'node:module'

const { computed, reactive, ref, watch, nextTick } = createRequire(import.meta.resolve('nuxt'))('vue')

function mount(query = {}) {
  const route = reactive({ query })
  const history = []
  const cleanup = []
  const source = readFileSync(new URL('../app/composables/useListState.ts', import.meta.url), 'utf8').replace(/^import type[^\n]+\n/m, '').replace('export function', 'function') + '\nglobalThis.factory = useListState'
  const context = {
    computed,
    ref,
    watch,
    setTimeout,
    clearTimeout,
    onBeforeUnmount: fn => cleanup.push(fn),
    useRoute: () => route,
    useRouter: () => ({
      push: async ({ query }) => {
        history.push(query)
        route.query = query
      }
    })
  }
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None } }).outputText, context)
  return { list: context.factory({ status: 'ALL', sort_order: 'desc' }), route, history, unmount: () => cleanup.forEach(fn => fn()) }
}

test('paging preserves filters, resets atomically on changes, and restores route state', async () => {
  const { list, route, history, unmount } = mount({ page: '7', status: 'PENDING', search: 'Alice', workspace: 'HR' })
  list.page.value = 2
  await nextTick()
  assert.equal(route.query.status, 'PENDING')
  assert.equal(route.query.search, 'Alice')
  list.field('status').value = 'APPROVED'
  await nextTick()
  assert.equal(list.page.value, 1)
  assert.equal(route.query.workspace, 'HR')
  route.query = history[0]
  await nextTick()
  assert.equal(list.page.value, 2)
  assert.equal(list.field('status').value, 'PENDING')
  list.clear()
  await nextTick()
  assert.equal(list.search.value, '')
  assert.equal(list.field('status').value, 'ALL')
  assert.equal(list.page.value, 1)
  unmount()
})

test('search debounces multiple keystrokes into one route request', async () => {
  const { list, history, unmount } = mount({ page: '4' })
  list.search.value = 'a'
  await nextTick()
  list.search.value = 'ali'
  await nextTick()
  list.search.value = 'alice'
  await nextTick()
  assert.equal(history.length, 0)
  await new Promise(resolve => setTimeout(resolve, 360))
  assert.equal(history.length, 1)
  assert.equal(list.page.value, 1)
  assert.equal(list.query.value.search, 'alice')
  unmount()
})
