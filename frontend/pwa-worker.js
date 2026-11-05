/* Replaced by the build plugin. No API responses or answer mutations are cached. */
const STATIC_CACHE = 'academy-static-__VERSION__';
const PRECACHE = __PRECACHE__;
self.addEventListener('install', event => {
  event.waitUntil(caches.open(STATIC_CACHE).then(cache => cache.addAll(PRECACHE)));
  // A new worker waits for old tabs to close; don't replace code during a lesson.
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    // Retain the preceding shell for already-open tabs during an explicit update.
    const old = keys.filter(key => key.startsWith('academy-static-') && key !== STATIC_CACHE);
    await Promise.all(old.slice(0, -1).map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});
self.addEventListener('message', event => {
  if (event.data?.type === 'CHECK_OFFLINE_SHELL' && event.ports?.[0]) {
    event.waitUntil((async () => {
      const cache = await caches.open(STATIC_CACHE);
      const entries = await Promise.all(PRECACHE.map(path => cache.match(path)));
      event.ports[0].postMessage({ready:entries.every(Boolean)});
    })());
    return;
  }
  if (event.data?.type !== 'ACTIVATE_UPDATE' || !event.ports?.[0]) return;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({type:'window', includeUncontrolled:true});
    if (windows.length > 1) { event.ports[0].postMessage({status:'other-tabs'}); return; }
    event.ports[0].postMessage({status:'activating'});
    await self.skipWaiting();
  })());
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname === '/api' || url.pathname.startsWith('/api/')) return;
  if (event.request.mode === 'navigate') {
    // HTML and JS come from one build, including when the web server is returning 503.
    event.respondWith(caches.open(STATIC_CACHE).then(async cache => (await cache.match('/index.html')) || fetch(event.request)));
  } else if (PRECACHE.includes(url.pathname)) {
    event.respondWith(caches.open(STATIC_CACHE).then(async cache => (await cache.match(event.request)) || fetch(event.request)));
  } else if (/^\/assets\/[^/]+-[A-Za-z0-9_-]+\.(js|css)$/.test(url.pathname)) {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
  }
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({type:'window',includeUncontrolled:true});
    const existing = windows.find(client => new URL(client.url).origin === self.location.origin);
    if (existing) { await existing.focus(); await existing.navigate('/#plan'); }
    else await self.clients.openWindow('/#plan');
  })());
});
