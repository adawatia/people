export default defineAppConfig({
  ui: {
    button: { slots: { base: 'min-h-11' } },
    input: { slots: { base: 'min-h-11' } },
    select: { slots: { base: 'min-h-11' } },
    selectMenu: { slots: { base: 'min-h-11' } },
    modal: { slots: { content: 'max-h-[90dvh]', body: 'overflow-y-auto', close: 'min-h-11 min-w-11' } },
    drawer: { slots: { content: 'max-h-[90dvh]', body: 'overflow-y-auto' } },
    colors: {
      primary: 'brand',
      neutral: 'slate',
      success: 'emerald',
      warning: 'amber',
      error: 'rose',
      info: 'sky'
    }
  }
})
