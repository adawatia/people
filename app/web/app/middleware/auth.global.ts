const publicPaths = ['/login', '/forgot-password', '/reset-password', '/invitation', '/verify-email', '/auth/invitation']

export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuth()
  await auth.fetchUser()
  const isPublic = publicPaths.some(path => to.path === path || to.path.startsWith(`${path}/`))
  if (!auth.user.value && !isPublic) return navigateTo({ path: '/login', query: { redirect: to.fullPath } })
  if (auth.user.value && to.path === '/login') return navigateTo('/')
})
