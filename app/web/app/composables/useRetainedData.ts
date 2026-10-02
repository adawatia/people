/** Keep successful results while the same view refreshes; never cache across account/workspace boundaries. */
export function useRetainedData<T>(source: Ref<T | null | undefined>) {
  const last = shallowRef<T>()
  const route = useRoute()
  const auth = useAuth()
  const workspace = useWorkspace()
  watch(() => `${auth.user.value?.id}:${workspace.current.value}:${route.path}`, () => {
    last.value = undefined
  }, { flush: 'sync' })
  watch(source, (value) => {
    if (value !== null && value !== undefined) last.value = value
  }, { immediate: true })
  return computed({
    get: () => source.value ?? last.value,
    set: (value: T | null | undefined) => {
      source.value = value
      if (value === null || value === undefined) last.value = undefined
    }
  })
}
