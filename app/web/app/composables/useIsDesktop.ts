export function useIsDesktop() {
  const isDesktop = ref(import.meta.client ? window.matchMedia('(min-width: 1024px)').matches : true)

  onMounted(() => {
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
