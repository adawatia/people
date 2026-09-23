/**
 * Keep direct URLs inside the active presentation workspace. Resource access is
 * still enforced by FastAPI; this guard prevents confusing cross-workspace UI
 * and sends hidden tabs back to the active workspace dashboard.
 */
export default defineNuxtRouteMiddleware((to) => {
  const auth = useAuth()
  if (!auth.user.value || to.matched.length === 0) return

  const workspace = useWorkspace()
  if (!workspace.canVisit(to.path)) return navigateTo(workspace.link('/'))
})
