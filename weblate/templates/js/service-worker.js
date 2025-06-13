const APP_VERSION = "{{ version }}";
const staticCacheName = `weblate-pwa-cache-${APP_VERSION}`;

const urlsToCache = [
  // Offline page
  "{% url 'pwa-offline' %}",

  // Common static assets
  "/static/styles/main.css",
  "/static/loader-bootstrap.js",
  "/static/vendor/bootstrap/css/bootstrap.css",
  "/static/vendor/bootstrap/js/bootstrap.js",
  "/favicon.ico",
  "/static/weblate-192.png",
  "/css/custom.css",
  "/js/i18n/",

  "/site.webmanifest",

  // The service worker itself
  "/service-worker.js",
];

// Install event: Pre-cache static assets
self.addEventListener("install", (event) => {
  this.skipWaiting();
  event.waitUntil(
    caches.open(staticCacheName).then((cache) => {
      return cache.addAll(urlsToCache);
    }),
  );
});

// Fetch event: Network-first strategy that falls back to cache
self.addEventListener("fetch", (event) => {
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Clone the response and store it in the cache
        const responseToCache = response.clone();
        caches.open(staticCacheName).then((cache) => {
          cache.put(event.request, responseToCache);
        });
        return response; // Return the network response
      })
      .catch(() => {
        // Fallback to offline page
        return caches.match("/pwa/offline/");
      }),
  );
});

// Activate event: Clean up old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((cacheName) => cacheName !== staticCacheName)
          .map((cacheName) => caches.delete(cacheName)),
      );
    }),
  );
});
