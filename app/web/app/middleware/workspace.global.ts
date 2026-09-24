import { canVisitWorkspace, resolveWorkspace } from '~/composables/useWorkspace'

/**
 * Keep direct URLs inside the active presentation workspace. Resource access is
 * still enforced by FastAPI; this guard prevents confusing cross-workspace UI
 * and sends hidden tabs back to the active workspace dashboard.
 */
export default defineNuxtRouteMiddleware((to) => {
  const auth = useAuth()
  if (!auth.user.value || to.matched.length === 0) return

  const saved = useCookie('people_workspace')
  const workspace = resolveWorkspace(auth.user.value, to.query.workspace, saved.value)
  if (!canVisitWorkspace(auth.user.value, workspace, to.path)) {
    return navigateTo({ path: '/', query: { workspace } })
  }
})
