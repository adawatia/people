const CACHE_NAME = 'emploi-static-v1'
const OFFLINE_URL = '/offline.html'
const STATIC_PREFIXES = ['/_nuxt/', '/brand/', '/fonts/']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll([
        OFFLINE_URL,
        '/site.webmanifest',
        '/icon-192.png',
        '/icon-512.png',
        '/icon-maskable-512.png',
        '/apple-touch-icon.png',
        '/favicon.svg',
        '/favicon.ico'
      ]))
      .then(() => self.skipWaiting())
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => (key.startsWith('emploi-static-') || key.startsWith('people-static-')) && key !== CACHE_NAME).map(key => caches.delete(key))))
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
      const cached = await cache.match(request)
      if (cached) return cached

      try {
        const response = await fetch(request)
        if (response && response.status === 200) {
          cache.put(request, response.clone())
        }
        return response
      } catch {
        return cached || new Response('', { status: 408, statusText: 'Request timed out' })
      }
    })())
  }
})
