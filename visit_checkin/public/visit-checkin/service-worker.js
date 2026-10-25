/*
 * App-shell cache for the Visit Check-in PWA.
 *
 *  - install  : pre-cache the shell (index.html + manifest are critical, icons best-effort)
 *  - fetch    : shell files are served cache-first for instant / offline start, and
 *               refreshed in the background (stale-while-revalidate) so a new release
 *               reaches users on their next launch without bumping anything.
 *  - API calls (/api/method/...) are NOT touched: the page's own IndexedDB queue
 *    handles offline data.
 */
var CACHE_NAME = "visit-checkin-shell-v1";
var SHELL_BASE = "/assets/visit_checkin/visit-checkin/";

var CRITICAL = [SHELL_BASE + "index.html", SHELL_BASE + "manifest.json"];
var OPTIONAL = [SHELL_BASE + "icon-192.png", SHELL_BASE + "icon-512.png"];

function fetchFresh(url) {
  return fetch(url, { cache: "reload", credentials: "same-origin" });
}

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      var critical = Promise.all(
        CRITICAL.map(function (url) {
          return fetchFresh(url).then(function (resp) {
            if (!resp.ok) throw new Error("Failed to cache " + url);
            return cache.put(url, resp);
          });
        })
      );
      var optional = Promise.all(
        OPTIONAL.map(function (url) {
          return fetchFresh(url)
            .then(function (resp) { if (resp.ok) return cache.put(url, resp); })
            .catch(function () {});
        })
      );
      return Promise.all([critical, optional]);
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k !== CACHE_NAME; })
            .map(function (k) { return caches.delete(k); })
      );
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  var req = event.request;
  if (req.method !== "GET") return;

  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.indexOf(SHELL_BASE) !== 0) return;
  if (url.pathname === SHELL_BASE + "service-worker.js") return;

  // Normalise: ignore query strings (e.g. ?utm / login redirects) and bare "/" folder URL.
  var key = url.pathname === SHELL_BASE ? SHELL_BASE + "index.html" : url.pathname;

  event.respondWith(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.match(key).then(function (cached) {
        var network = fetchFresh(key)
          .then(function (resp) {
            if (resp && resp.ok) cache.put(key, resp.clone());
            return resp;
          })
          .catch(function () { return cached; });

        return cached || network;
      });
    })
  );
});
