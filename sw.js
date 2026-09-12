/* Offline support for the Alberta Trout Map.
 *
 * Why this exists: almost none of these lakes have usable cell signal, and that
 * is precisely where the map is worth having. A visit at home should leave
 * enough behind that the map still draws at the water.
 *
 * Four caching rules, one per kind of request, because they want opposite
 * things:
 *
 *   the page        network first  — so an update reaches you as soon as you
 *                                    are online, without a version to bump
 *   libraries       cache first    — vendored and pinned, so they never change
 *   data files      cache first,   — the year files are large and change only
 *                   refreshed        when a report is rebuilt, so serve the
 *                   in the           copy instantly and quietly fetch a newer
 *                   background       one for next time
 *   basemap tiles   cache first,   — whatever you looked at at home is what you
 *                   capped           get at the lake
 */

/* v2: the shell is served cache-first-then-revalidate, so a returning user
   gets yesterday's JavaScript alongside today's HTML on the first load after a
   deploy. That is survivable for a tweak and not for this release, which adds a
   file (js/calendar.js) the new index.html calls into, and fixes the photo URLs
   in js/lake-panel.js. Bumping the name retires the old shell outright. */
const SHELL_CACHE = "troutmap-shell-v2";
const DATA_CACHE = "troutmap-data-v1";
const TILE_CACHE = "troutmap-tiles-v1";
const WX_CACHE = "troutmap-wx-v1";
/* Every troutmap-* cache missing from this list is deleted on activate, so a
 * cache added above and forgotten here is wiped on the next worker update —
 * silently, and only noticed by someone offline at a lake. */
const KNOWN_CACHES = [SHELL_CACHE, DATA_CACHE, TILE_CACHE, WX_CACHE];
const WX_LIMIT = 25;

/* Tiles are unbounded — Alberta at zoom 17 is millions of them — so the tile
 * cache is capped and trimmed oldest-first. 600 tiles is roughly a province at
 * low zoom plus a few lakes at fishing zoom. */
const TILE_LIMIT = 600;

const SHELL_FILES = [
  "./",
  "index.html",
  "manifest.webmanifest",
  "icon.svg",
  "vendor/leaflet.css",
  "vendor/leaflet.js",
  "vendor/MarkerCluster.css",
  "vendor/leaflet.markercluster.js",
  "vendor/chart.umd.js",
  "js/astro.js",
  "js/conditions.js",
  "js/weather.js",
  "js/conditions-ui.js",
  "js/lake-panel.js",
  "js/calendar.js",
  "evidence.html",
  "vendor/images/marker-icon.png",
  "vendor/images/marker-icon-2x.png",
  "vendor/images/marker-shadow.png",
  "vendor/images/layers.png",
  "vendor/images/layers-2x.png",
];

/** The year files are not knowable in advance, so read the manifest the app
 *  itself reads. A year that fails to cache must not fail the install: partial
 *  offline support beats none. */
async function precacheData() {
  const cache = await caches.open(DATA_CACHE);
  const fixed = ["data/manifest.json", "data/quality_summary.json",
                 "data/lake_regulations.json", "data/lake_depth.json",
                 // Not lake_photos.json: the pictures it points at live on
                 // Alberta's server, this worker does not handle other
                 // origins, and an index of images that cannot load offline
                 // is not worth the bytes. The photo COUNT is in the profile
                 // file, so a lake still says how many there are.
                 "data/lake_profile.json",
                 "live/advisories.json"];
  await Promise.all(fixed.map(u => cache.add(u).catch(() => {})));

  let years = [];
  try {
    const res = await fetch("data/manifest.json", { cache: "no-store" });
    const manifest = await res.json();
    years = Array.isArray(manifest.years) ? manifest.years : [];
  } catch {
    return;
  }
  await Promise.all(years.map(y =>
    cache.add(`data/lakes_${y}.json`).catch(() => {})));
}

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const shell = await caches.open(SHELL_CACHE);
    // addAll is all-or-nothing; one missing vendor file would leave the app
    // with no offline support at all, so each file is added on its own.
    await Promise.all(SHELL_FILES.map(u => shell.add(u).catch(() => {})));
    await precacheData();
  })());
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names
      .filter(n => n.startsWith("troutmap-") && !KNOWN_CACHES.includes(n))
      .map(n => caches.delete(n)));
    await self.clients.claim();
  })());
});

/* The page asks for this before reloading, so a waiting worker never takes over
 * mid-session and reloads the page out from under someone. */
self.addEventListener("message", event => {
  if (event.data && event.data.type === "skip-waiting") self.skipWaiting();
});

function isWeather(url) {
  return url.hostname === "api.open-meteo.com";
}

function isTile(url) {
  return /tile\.opentopomap\.org|tile\.openstreetmap\.org/.test(url.hostname);
}

async function trimCache(name, limit) {
  const cache = await caches.open(name);
  const keys = await cache.keys();
  // Cache.keys() returns insertion order, so the front is the oldest.
  for (let i = 0; i < keys.length - limit; i++) await cache.delete(keys[i]);
}

/** Serve the cached copy at once, and refresh it in the background for the next
 *  visit. Never let the background failure surface: being offline is normal. */
async function cacheFirstRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(request);
  if (hit) {
    fetch(request).then(res => { if (res.ok) cache.put(request, res.clone()); }).catch(() => {});
    return hit;
  }
  const res = await fetch(request);
  if (res.ok) cache.put(request, res.clone());
  return res;
}

async function cacheFirst(request, cacheName, { limit } = {}) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  // Tile servers answer cross-origin requests opaquely; an opaque response has
  // status 0 but is still a perfectly good tile to store and replay.
  if (res.ok || res.type === "opaque") {
    await cache.put(request, res.clone());
    if (limit) trimCache(cacheName, limit);
  }
  return res;
}

/** Weather is the one thing here that is wrong when it is old, and the one thing
 *  you cannot get where it matters most. So: take the network when there is one
 *  and it answers quickly, and otherwise fall back to whatever is cached,
 *  however stale, because an old forecast beats an empty panel.
 *
 *  The timeout is the point. Neither existing strategy fits — cacheFirst never
 *  refreshes, so the forecast freezes; cacheFirstRevalidate always shows you
 *  last session's weather. And the common field failure is not being offline,
 *  which fetch rejects on promptly. It is one bar of signal, where fetch simply
 *  hangs and navigator.onLine cheerfully reports true, so the offline badge
 *  never appears and the panel spins forever. */
async function networkFirstTimed(request, cacheName, timeoutMs, limit) {
  const cache = await caches.open(cacheName);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(request, { signal: controller.signal });
    clearTimeout(timer);
    if (res.ok) {
      const body = await res.clone().arrayBuffer();
      const headers = new Headers(res.headers);
      headers.set("x-troutmap-fetched", String(Date.now()));
      await cache.put(request, new Response(body, { status: 200, headers }));
      if (limit) trimCache(cacheName, limit);
    }
    return res;
  } catch (err) {
    clearTimeout(timer);
    const hit = await cache.match(request);
    if (hit) return hit;
    // A shape the page can read, rather than a network error it cannot.
    return new Response('{"error":"offline"}',
      { status: 503, headers: { "content-type": "application/json" } });
  }
}

/** The page itself: take the network when there is one, so an update lands
 *  without any version here to remember to bump. */
async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const res = await fetch(request);
    if (res.ok) cache.put(request, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(request) || await cache.match("index.html");
    if (hit) return hit;
    throw err;
  }
}

self.addEventListener("fetch", event => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  if (isTile(url)) {
    event.respondWith(cacheFirst(request, TILE_CACHE, { limit: TILE_LIMIT }));
    return;
  }

  // Before the same-origin bail below, because the forecast is someone else's
  // to serve but very much ours to keep.
  if (isWeather(url)) {
    event.respondWith(networkFirstTimed(request, WX_CACHE, 6000, WX_LIMIT));
    return;
  }

  // Everything else is only handled for this app's own origin. Google Maps
  // links and the regulations site are someone else's to serve.
  if (url.origin !== location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request, SHELL_CACHE));
    return;
  }
  // Advisories change daily and matter most where there is no signal, so they
  // are cached like data rather than fetched fresh.
  if (url.pathname.includes("/live/")) {
    event.respondWith(cacheFirstRevalidate(request, DATA_CACHE));
    return;
  }
  if (url.pathname.includes("/data/")) {
    event.respondWith(cacheFirstRevalidate(request, DATA_CACHE));
    return;
  }
  if (url.pathname.includes("/vendor/")) {
    event.respondWith(cacheFirst(request, SHELL_CACHE));
    return;
  }
  event.respondWith(cacheFirstRevalidate(request, SHELL_CACHE));
});
