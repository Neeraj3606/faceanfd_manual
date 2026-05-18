const CACHE_NAME = 'face-attendance-v10';
const STATIC_ASSETS = [
  '/static/login.html',
  '/static/super_admin.html',
  '/static/admin_dashboard.html',
  '/static/teacher.html',
  '/static/manifest.json'
];

// Install: cache static assets
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: network-first for API, cache-first for static
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // HTML pages: network-first to avoid stale dashboard logic from old cache.
  if (request.mode === 'navigate' || url.pathname.endsWith('.html')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const cloned = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, cloned));
          }
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match('/static/login.html')))
    );
    return;
  }

  // API calls: network only (don't cache dynamic data)
  if (url.pathname.startsWith('/auth/') || url.pathname.startsWith('/attendance/') ||
      url.pathname.startsWith('/students') || url.pathname.startsWith('/filters/') ||
      url.pathname.startsWith('/analytics/') || url.pathname.startsWith('/enroll') ||
      url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request).catch(() => {
      // Offline fallback for API
      return new Response(JSON.stringify({ ok: false, message: 'You are offline' }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }));
    return;
  }

  // Other static assets: cache first, then network
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        // Don't cache non-success or opaque responses
        if (!response || response.status !== 200 || response.type === 'opaque') {
          return response;
        }
        const responseToCache = response.clone();
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(request, responseToCache);
        });
        return response;
      }).catch(() => {
        // If HTML page is requested offline, serve login page
        if (request.headers.get('accept')?.includes('text/html')) {
          return caches.match('/static/login.html');
        }
        return new Response('Offline', { status: 503 });
      });
    })
  );
});
