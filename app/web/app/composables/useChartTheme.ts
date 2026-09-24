export function useChartTheme() {
  const mode = useColorMode()
  return computed(() => mode.value === 'dark' ? 'dark' : undefined)
}
