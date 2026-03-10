/**
 * Service Worker for PC Events PWA
 *
 * Strategy:
 * - Cache-first for static assets (CSS, JS, images, fonts)
 * - Network-first for API/page requests (show cached if offline)
 * - Offline fallback page when network unavailable
 */

const CACHE_VERSION = 'pc-events-v1';
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `dynamic-${CACHE_VERSION}`;

// Static assets to pre-cache on install
const PRECACHE_ASSETS = [
  '/offline',
  '/static/css/design-tokens.css',
  '/static/css/style.css',
  '/static/css/responsive.css',
  '/static/css/components/bottom-nav.css',
  '/static/css/components/sidebar.css',
  '/static/css/components/modal.css',
  '/static/css/loading-states.css',
  '/static/js/main.js',
  '/static/js/navigation.js',
  '/static/img/PC-Logo_Primary_Full-Color-1024x251.png',
  '/static/img/pwa-icon-192.png',
  '/static/manifest.json'
];

// Install: pre-cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// Activate: clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== STATIC_CACHE && key !== DYNAMIC_CACHE)
          .map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: route requests to appropriate strategy
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') return;

  // Skip cross-origin requests
  if (url.origin !== self.location.origin) return;

  // API requests: network-first
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // HTML pages: network-first with offline fallback
  if (request.headers.get('Accept')?.includes('text/html')) {
    event.respondWith(networkFirstWithFallback(request));
    return;
  }

  // Everything else: network-first
  event.respondWith(networkFirst(request));
});

/**
 * Cache-first strategy for static assets.
 * Serves from cache if available, fetches and caches if not.
 */
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('Offline', { status: 503 });
  }
}

/**
 * Network-first strategy for API/dynamic data.
 * Tries network, falls back to cache.
 */
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ error: 'Offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

/**
 * Network-first with offline HTML fallback.
 * For page navigations — shows offline page if both network and cache fail.
 */
async function networkFirstWithFallback(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;

    // Show offline fallback page
    const offlinePage = await caches.match('/offline');
    if (offlinePage) return offlinePage;

    return new Response('<h1>Offline</h1><p>Check your connection and try again.</p>', {
      status: 503,
      headers: { 'Content-Type': 'text/html' }
    });
  }
}
