const APP_VERSION = "{{ version }}";
const CACHE_NAME = `weblate-pwa-cache-${APP_VERSION}`;

const urlsToCache = [
  // Core pages
  "/",

  // User account pages
  "/accounts/profile/",
  "/accounts/login/",
  "/accounts/register/",

  // Common static assets
  "/static/css/style.css",
  "/static/js/main.js",
  "/static/weblate.js",
  "/static/bootstrap/css/bootstrap.min.css",
  "/static/bootstrap/js/bootstrap.bundle.min.js",
  "/static/font-awesome/css/font-awesome.min.css",
  "/static/favicon.ico",
  "/static/weblate-192.png",
  "/css/custom.css",
  "/js/i18n/",

  "/site.webmanifest",
  "/robots.txt",

  // The service worker itself
  "/service-worker.js",
];

// Install event: Pre-cache static assets
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
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
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, responseToCache);
        });
        return response; // Return the network response
      })
      .catch(() => {
        // Fallback to cache if the network request fails
        return caches.match(event.request);
      }),
  );
});

// Activate event: Clean up old caches
self.addEventListener("activate", (event) => {
  const cacheWhitelist = [CACHE_NAME];

  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (!cacheWhitelist.includes(cacheName)) {
            return caches.delete(cacheName);
          }
        }),
      );
    }),
  );
});
