/**
 * Global route guard: runs before every page navigation.
 *
 * - Unauthenticated users are redirected to /login (remembering where they
 *   were headed via the `redirect` query param), except on public paths.
 * - Authenticated users hitting /login are bounced to the dashboard.
 */
const publicPaths = ['/login', '/forgot-password', '/reset-password', '/invitation', '/verify-email', '/auth/invitation']

export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuth()
  // Ensure session state is loaded before deciding (no-op after first fetch).
  await auth.fetchUser()
  const isPublic = publicPaths.some(path => to.path === path || to.path.startsWith(`${path}/`))
  if (!auth.user.value && !isPublic) return navigateTo({ path: '/login', query: { redirect: to.fullPath } })
  if (auth.user.value && to.path === '/login') return navigateTo('/')
})
