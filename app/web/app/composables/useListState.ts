import type { LocationQueryRaw } from 'vue-router'

/** Route state is the source of truth, so refresh and browser history restore a list. */
export function useListState(defaults: Record<string, string> = {}, prefix = '') {
  const route = useRoute()
  const router = useRouter()
  const key = (name: string) => `${prefix}${name}`
  const value = (name: string, fallback = '') => typeof route.query[key(name)] === 'string' ? String(route.query[key(name)]) : fallback
  function update(values: Record<string, string | number>, reset = true) {
    const query: LocationQueryRaw = { ...route.query }
    for (const [name, entry] of Object.entries(values)) {
      if (String(entry) === (defaults[name] ?? '') || entry === '') query[key(name)] = undefined
      else query[key(name)] = String(entry)
    }
    if (reset) query[key('page')] = undefined
    return router.push({ query })
  }
  function field(name: string, fallback = defaults[name] ?? '') {
    defaults[name] = fallback
    return computed({ get: () => value(name, fallback), set: (next) => {
      void update({ [name]: next })
    } })
  }
  const page = computed({ get: () => Number.isSafeInteger(Number(value('page', '1'))) ? Math.max(1, Number(value('page', '1'))) : 1, set: (next) => {
    void update({ page: next }, false)
  } })
  const pageSize = computed({ get: () => [10, 25, 50, 100].includes(Number(value('page_size'))) ? Number(value('page_size')) : 25, set: (next) => {
    void update({ page_size: next })
  } })
  const search = ref(value('search'))
  let timer: ReturnType<typeof setTimeout> | undefined
  watch(search, (next) => {
    clearTimeout(timer)
    timer = setTimeout(() => {
      if (next.trim() !== value('search')) void update({ search: next.trim() })
    }, 300)
  })
  watch(() => route.query[key('search')], () => {
    clearTimeout(timer)
    search.value = value('search')
  })
  onBeforeUnmount(() => clearTimeout(timer))
  const sortBy = field('sort_by')
  const sortOrder = field('sort_order', defaults.sort_order || 'desc')
  const query = computed(() => ({ page: page.value, page_size: pageSize.value, search: value('search') || undefined, sort_by: sortBy.value || undefined, sort_order: sortOrder.value }))
  const active = computed(() => Boolean(search.value || Object.entries(defaults).some(([name, fallback]) => value(name, fallback) !== fallback) || sortBy.value))
  function clear() {
    clearTimeout(timer)
    search.value = ''
    void update({ ...defaults, search: '', sort_by: '' })
  }
  return { page, pageSize, search, sortBy, sortOrder, query, field, active, clear, update }
}
