/**
 * Attendance PWA Service Worker
 * Strategy: Cache-first for static assets, Network-first for API calls
 */
const CACHE_VERSION = 'v4';
const STATIC_CACHE  = `attendance-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `attendance-dynamic-${CACHE_VERSION}`;

const STATIC_ASSETS = [
  '/static/login.html',
  '/static/admin_dashboard.html',
  '/static/teacher.html',
  '/static/super_admin.html',
  '/static/manifest.json',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png',
];

// Offline fallback HTML
const OFFLINE_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Offline — Attendance</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:system-ui,sans-serif;background:#07101e;color:#e4edff;
         display:flex;flex-direction:column;align-items:center;justify-content:center;
         min-height:100vh;padding:24px;text-align:center;}
    .icon{font-size:64px;margin-bottom:24px;animation:pulse 2s infinite;}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
    h1{font-size:24px;font-weight:700;margin-bottom:12px;}
    p{font-size:14px;color:#8ea9cf;max-width:340px;line-height:1.6;margin-bottom:24px;}
    button{padding:12px 28px;border-radius:10px;background:#1547c0;color:#fff;
           border:none;font-size:14px;font-weight:600;cursor:pointer;}
    button:hover{background:#1d6ae5;}
  </style>
</head>
<body>
  <div class="icon">📡</div>
  <h1>You're Offline</h1>
  <p>Attendance needs an internet connection to work. Please check your connection and try again.</p>
  <button onclick="location.reload()">Try Again</button>
</body>
</html>`;

// ── Install: cache static assets ──────────────────────────────────────────
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => {
      return Promise.allSettled(
        STATIC_ASSETS.map(url => cache.add(url).catch(() => {}))
      );
    })
  );
});

// ── Activate: clean old caches ────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== STATIC_CACHE && k !== DYNAMIC_CACHE)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch: route strategy ─────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET and cross-origin
  if (request.method !== 'GET') return;
  if (url.origin !== location.origin) return;

  // API calls → Network-first, fallback cached
  if (url.pathname.startsWith('/auth/') || url.pathname.startsWith('/analytics/') || url.pathname.startsWith('/attendance/') || url.pathname.startsWith('/students')) {
    event.respondWith(
      fetch(request)
        .then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(DYNAMIC_CACHE).then(cache => cache.put(request, clone));
          }
          return res;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Static HTML/assets → Cache-first, then network, then offline page
  event.respondWith(
    caches.match(request).then(cached => {
      if (cached) return cached;
      return fetch(request)
        .then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(STATIC_CACHE).then(cache => cache.put(request, clone));
          }
          return res;
        })
        .catch(() => {
          // Return offline page for HTML navigation requests
          if (request.headers.get('accept')?.includes('text/html')) {
            return new Response(OFFLINE_HTML, {
              headers: { 'Content-Type': 'text/html' }
            });
          }
        });
    })
  );
});

// ── Push notifications (future) ───────────────────────────────────────────
self.addEventListener('push', event => {
  if (!event.data) return;
  const data = event.data.json();
  self.registration.showNotification(data.title || 'Attendance', {
    body: data.body || '',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/icon-72x72.png',
    vibrate: [200, 100, 200],
    data: { url: data.url || '/static/login.html' }
  });
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification.data?.url || '/static/login.html';
  event.waitUntil(clients.openWindow(url));
});
