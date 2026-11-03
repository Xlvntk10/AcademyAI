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
    await Promise.all(keys.filter(key => key.startsWith('academy-static-') && key !== STATIC_CACHE).map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(async () => (await caches.open(STATIC_CACHE)).match('/index.html')));
  } else if (PRECACHE.includes(url.pathname)) {
    event.respondWith(caches.open(STATIC_CACHE).then(async cache => (await cache.match(event.request)) || fetch(event.request)));
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
