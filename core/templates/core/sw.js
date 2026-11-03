// SmartCart BD service worker: fast repeat visits, an offline page and push notifications.
const VERSION = 'scb-v2';
const OFFLINE_URL = '{% url "offline" %}';
const PRECACHE = [OFFLINE_URL{% for url in precache %}, '{{ url }}'{% endfor %}];

self.addEventListener('install', (event) => {
    event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET') return;
    const url = new URL(request.url);

    // Pages: always try the network (prices and stock change), fall back to the offline page.
    if (request.mode === 'navigate') {
        event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
        return;
    }

    // Our static files and product images: cache first, they are versioned or rarely change.
    if (url.origin === self.location.origin && (url.pathname.startsWith('/static/') || url.pathname.startsWith('/media/'))) {
        event.respondWith(
            caches.match(request).then((cached) => cached || fetch(request).then((response) => {
                if (response.ok) {
                    const copy = response.clone();
                    caches.open(VERSION).then((cache) => cache.put(request, copy));
                }
                return response;
            }))
        );
    }
});

// Push notifications sent by the server (accounts/push.py): {title, body, url}.
self.addEventListener('push', (event) => {
    let data = {};
    try { data = event.data ? event.data.json() : {}; } catch (err) { data = { body: event.data.text() }; }
    event.waitUntil(self.registration.showNotification(data.title || 'SmartCart BD', {
        body: data.body || '',
        icon: '{{ icon_url }}',
        badge: '{{ icon_url }}',
        data: { url: data.url || '/' },
    }));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const url = new URL(event.notification.data.url || '/', self.location.origin).href;
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
            const open = windows.find((w) => w.url === url);
            return open ? open.focus() : self.clients.openWindow(url);
        })
    );
});
