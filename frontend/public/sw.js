/* UBOS service worker — DEV KILL-SWITCH.
 *
 * The previous caching service worker (network-first shell, cache-first for
 * /static/*) caused stale JS bundles to be served during local development,
 * masking code changes. This self-unregistering version neutralises any
 * previously-installed SW: on activate it deletes all caches, unregisters
 * itself, and reloads open tabs. Browsers always fetch sw.js from the network
 * on navigation, so this replacement is picked up automatically.
 *
 * ⚠ Before shipping the PWA to production, restore the original caching SW
 *   from git history (git log -- frontend/public/sw.js) and bump its VERSION.
 */
self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
      await self.registration.unregister();
      const clients = await self.clients.matchAll({ type: "window" });
      clients.forEach((c) => c.navigate(c.url));
    } catch (_e) {
      /* best-effort cleanup */
    }
  })());
});

// Never serve from cache — always go to network.
self.addEventListener("fetch", () => { /* pass-through */ });
