// Cache version — updated automatically by CI or pre-commit hook.
// To bump manually: change the date suffix below.
const CACHE_VERSION = "aurion-v0.6.0";
const ASSETS = [
  "/",
  "/index.html",
  "/styles.css",
  "/app.js",
  "/manifest.webmanifest",
  "/vendor/chart.umd.min.js",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-512-maskable.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_VERSION).then((cache) => cache.addAll(ASSETS)));
  // Intentionally NOT calling skipWaiting() here. A new service worker version
  // stays in "waiting" state until the page explicitly posts {type: "SKIP_WAITING"}
  // (or all clients close). This avoids swapping the app bundle underneath a user
  // who is in the middle of viewing a prediction.
});

self.addEventListener("message", (event) => {
  // The page can opt-in to immediate activation by posting this message after
  // prompting the user to refresh.
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key.startsWith("aurion-") && key !== CACHE_VERSION).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  if (request.method !== "GET") {
    return;
  }

  const requestUrl = new URL(request.url);
  if (requestUrl.origin !== self.location.origin) {
    return;
  }

  // API requests: network-first, offline fallback
  if (requestUrl.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(request).catch(
        () =>
          new Response(
            JSON.stringify({
              error: {
                code: "provider_unavailable",
                message: "Offline: API temporarily unavailable.",
                retryable: true,
              },
            }),
            {
              status: 503,
              headers: { "Content-Type": "application/json" },
            },
          ),
      ),
    );
    return;
  }

  // Static assets: network-first with cache fallback
  const isShellAsset = ASSETS.includes(requestUrl.pathname);
  if (!isShellAsset && request.mode !== "navigate") return;
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response && response.ok && isShellAsset) {
          const responseClone = response.clone();
          // Canonical keys bound cache size even when URLs carry cache-busting queries.
          event.waitUntil(caches.open(CACHE_VERSION)
            .then((cache) => cache.put(requestUrl.pathname, responseClone))
            .catch(() => {}));
        }
        return response;
      })
      .catch(async () => {
        const cache = await caches.open(CACHE_VERSION);
        const cached = await cache.match(requestUrl.pathname);
        if (cached) {
          return cached;
        }

        if (request.mode === "navigate") {
          const shell = await cache.match("/index.html");
          if (shell) {
            return shell;
          }
        }

        return Response.error();
      }),
  );
});
