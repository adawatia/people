/**
 * Global route guard: runs before every page navigation.
 *
 * - Unauthenticated users are redirected to /login (remembering where they
 *   were headed via the `redirect` query param), except on public paths.
 *   `/admin/login` is public too: it is the separate technical entry point.
 * - Authenticated users hitting a sign-in page are bounced to the dashboard.
 */
const publicPaths = ['/login', '/admin/login', '/forgot-password', '/reset-password', '/invitation', '/verify-email', '/auth/invitation']
const signInPaths = ['/login', '/admin/login']

export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuth()
  // Ensure session state is loaded before deciding (no-op after first fetch).
  await auth.fetchUser()
  const isPublic = publicPaths.some(path => to.path === path || to.path.startsWith(`${path}/`))
  if (!auth.user.value && !isPublic) return navigateTo({ path: '/login', query: { redirect: to.fullPath } })
  if (auth.user.value && signInPaths.includes(to.path)) return navigateTo('/')
})
