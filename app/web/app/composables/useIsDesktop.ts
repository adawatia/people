export function useIsDesktop() {
  const isDesktop = ref(
    import.meta.client && typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(min-width: 1024px)').matches
      : true
  )

  onMounted(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const media = window.matchMedia('(min-width: 1024px)')
    isDesktop.value = media.matches

    const onChange = (event: MediaQueryListEvent) => {
      isDesktop.value = event.matches
    }

    media.addEventListener('change', onChange)
    onBeforeUnmount(() => {
      media.removeEventListener('change', onChange)
    })
  })

  return { isDesktop }
}
