const CACHE_NAME = 'people-static-v1'
const OFFLINE_URL = '/offline.html'
const STATIC_PREFIXES = ['/_nuxt/', '/branding/', '/brand/', '/fonts/']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll([
        OFFLINE_URL,
        '/manifest.webmanifest',
        '/branding/people-app-icon-192.png',
        '/branding/people-app-icon-512.png',
        '/branding/people-app-icon-maskable-512.png'
      ]))
      .then(() => self.skipWaiting())
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key.startsWith('people-static-') && key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  const url = new URL(request.url)

  if (request.method !== 'GET' || url.origin !== self.location.origin) return

  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)))
    return
  }

  if (STATIC_PREFIXES.some(prefix => url.pathname.startsWith(prefix))) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME)
      try {
        const response = await fetch(request)
        if (response.ok) await cache.put(request, response.clone()).catch(() => undefined)
        return response
      } catch {
        return await cache.match(request) || Response.error()
      }
    })())
  }
})
