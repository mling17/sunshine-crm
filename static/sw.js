/* 极简 service worker：只服务 PWA 安装 + 断网兜底，不做离线业务逻辑。
 *
 * 策略：/crm/ 下（排除 /crm/api/）的 GET 走 network-first ——
 *   在线永远拿最新文件（发版不用清缓存），断网才回退到缓存壳；
 * 绝不缓存 /crm/api/ 的响应：客户数据是隐私，也必须实时。
 */
const CACHE = 'crm-shell-v2';
const SHELL = ['/crm/', '/crm/index.html', '/crm/app.js', '/crm/app.css', '/crm/manifest.json',
  '/crm/views/shared.js', '/crm/views/dashboard.js', '/crm/views/leads.js', '/crm/views/customers.js',
  '/crm/views/deals.js', '/crm/views/orders.js', '/crm/views/aftersales.js', '/crm/views/logistics.js',
  '/crm/views/followups.js', '/crm/views/stats.js', '/crm/views/import.js'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') { return; }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) { return; }
  if (!url.pathname.startsWith('/crm/') || url.pathname.startsWith('/crm/api/')) { return; }

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response && response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy)).catch(() => {});
        }
        return response;
      })
      .catch(() => caches.match(request).then((hit) => hit || caches.match('/crm/index.html')))
  );
});
