/* UBOS service worker — Phase 6-A
 *
 * Strategy:
 *   • App shell (index.html, JS/CSS chunks) → NETWORK-FIRST with cache fallback.
 *   • Static icons/fonts under /icons/ and /static/ → CACHE-FIRST with network fallback.
 *   • /api/* → NEVER cached (bypass to network).
 *
 * On `activate`, old caches (any name that doesn't match SHELL_CACHE) are wiped.
 * On installation of a new SW version, we notify the client via postMessage so the
 * SPA can render a "New version available — Reload" toast.
 */
const VERSION = "v1";
const SHELL_CACHE = `ubos-shell-${VERSION}`;
const ASSET_CACHE = `ubos-assets-${VERSION}`;

const PRECACHE_URLS = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) =>
      Promise.all(
        PRECACHE_URLS.map((u) => cache.add(u).catch(() => null))
      )
    )
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(
      names
        .filter((n) => n !== SHELL_CACHE && n !== ASSET_CACHE)
        .map((n) => caches.delete(n))
    );
    await self.clients.claim();
    const clients = await self.clients.matchAll({ type: "window" });
    clients.forEach((c) => c.postMessage({ type: "sw-activated", version: VERSION }));
  })());
});

function isApi(url) {
  return url.pathname.startsWith("/api/");
}
function isStatic(url) {
  return (
    url.pathname.startsWith("/icons/") ||
    url.pathname.startsWith("/static/") ||
    url.pathname === "/manifest.webmanifest"
  );
}
function isShell(url, req) {
  if (req.mode === "navigate") return true;
  return url.pathname.endsWith(".js") ||
         url.pathname.endsWith(".css") ||
         url.pathname === "/" ||
         url.pathname === "/index.html";
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (isApi(url)) return; // bypass — always fresh

  if (isStatic(url)) {
    event.respondWith((async () => {
      const cache = await caches.open(ASSET_CACHE);
      const cached = await cache.match(req);
      if (cached) return cached;
      try {
        const res = await fetch(req);
        if (res.ok) cache.put(req, res.clone()).catch(() => {});
        return res;
      } catch (e) {
        return cached || new Response("Offline", { status: 503 });
      }
    })());
    return;
  }

  if (isShell(url, req)) {
    event.respondWith((async () => {
      const cache = await caches.open(SHELL_CACHE);
      try {
        const res = await fetch(req);
        if (res.ok && req.method === "GET") {
          cache.put(req, res.clone()).catch(() => {});
        }
        return res;
      } catch (e) {
        const cached = await cache.match(req);
        if (cached) return cached;
        if (req.mode === "navigate") {
          const shell = await cache.match("/index.html");
          if (shell) return shell;
        }
        return new Response("Offline", { status: 503, headers: { "Content-Type": "text/plain" } });
      }
    })());
    return;
  }
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "skip-waiting") {
    self.skipWaiting();
  }
});
