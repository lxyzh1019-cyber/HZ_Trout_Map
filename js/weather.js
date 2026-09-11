/* One weather call per patch of the province, kept for when there is no signal.
 *
 * Three things shape this file, all of them the same concern: the lake is where
 * the forecast matters and where you cannot get one.
 *
 *   fetched per grid cell, never per lake   a thousand pins must not become a
 *                                           thousand requests
 *   mirrored into localStorage              so a forecast downloaded at home
 *                                           still draws at the water, stamped
 *                                           with how old it is
 *   abandoned after eight seconds           the common field failure is not
 *                                           being offline, it is one bar, where
 *                                           fetch hangs instead of failing and
 *                                           navigator.onLine still says true
 *
 * Times come back as unix seconds rather than local strings. Open-Meteo will
 * return "2026-09-11T14:00" if asked, and that has to be parsed against a
 * timezone offset which changes twice a year — an hour of silent drift across
 * a daylight-saving boundary, in a file whose whole job is to say when. Unix
 * time has no such ambiguity, and the offset is applied only for display.
 */
(function () {
  "use strict";

  var ENDPOINT = "https://api.open-meteo.com/v1/forecast";
  var HOURLY = ["temperature_2m", "cloud_cover", "wind_speed_10m", "wind_gusts_10m",
                "precipitation", "pressure_msl", "weather_code"];
  var TIMEOUT_MS = 8000;
  var TTL_MS = 3 * 3600 * 1000;      // past this it is served, but stamped stale
  var STORE_PREFIX = "troutmap.wx.";
  var MAX_CELLS = 20;

  /* A quarter of a degree: about 28 km north to south, 17 km east to west at
   * Alberta's latitude. Coarse enough that neighbouring lakes share a forecast,
   * fine enough that the forecast still belongs to them. */
  function cellKey(lat, lon) {
    return (Math.round(lat * 4) / 4).toFixed(2) + "," + (Math.round(lon * 4) / 4).toFixed(2);
  }

  function url(lat, lon) {
    var cell = cellKey(lat, lon).split(",");
    return ENDPOINT
      + "?latitude=" + cell[0] + "&longitude=" + cell[1]
      + "&hourly=" + HOURLY.join(",")
      + "&daily=temperature_2m_mean"
      + "&past_days=7&forecast_days=7"
      + "&timezone=auto&timeformat=unixtime"
      + "&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm";
  }

  // ============================================================
  // STORAGE
  // ============================================================

  function read(key) {
    try {
      var raw = localStorage.getItem(STORE_PREFIX + key);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  /* Written through and read back, because a quota failure here is silent
   * otherwise and the consequence — no weather at the lake — only shows up
   * somewhere with no way to debug it. */
  function write(key, record) {
    try {
      localStorage.setItem(STORE_PREFIX + key, JSON.stringify(record));
      if (localStorage.getItem(STORE_PREFIX + key) === null) return false;
      evict();
      return true;
    } catch (e) {
      evict(true);
      try {
        localStorage.setItem(STORE_PREFIX + key, JSON.stringify(record));
        return true;
      } catch (e2) {
        if (window.console) console.warn("weather: could not cache,", e2 && e2.name);
        return false;
      }
    }
  }

  /** Drop the least recently fetched cells. */
  function evict(aggressive) {
    var keep = aggressive ? Math.floor(MAX_CELLS / 2) : MAX_CELLS;
    var cells = [];
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (k && k.indexOf(STORE_PREFIX) === 0) {
          var rec = read(k.slice(STORE_PREFIX.length));
          cells.push({ key: k, at: (rec && rec.fetchedAt) || 0 });
        }
      }
      cells.sort(function (a, b) { return a.at - b.at; });
      while (cells.length > keep) localStorage.removeItem(cells.shift().key);
    } catch (e) { /* nothing we can do, and nothing that should stop a render */ }
  }

  // ============================================================
  // FETCH
  // ============================================================

  /* Only the fields that are used, as parallel arrays. The full response is
   * about 70 KB per cell and most of it is never read; stripped it is closer to
   * 25 KB, which is the difference between caching a handful of cells and
   * filling the quota. */
  function compact(json) {
    var h = json.hourly || {};
    return {
      offset: json.utc_offset_seconds || 0,
      timezone: json.timezone || "",
      t: h.time || [],
      airC: h.temperature_2m || [],
      cloud: h.cloud_cover || [],
      wind: h.wind_speed_10m || [],
      gust: h.wind_gusts_10m || [],
      precip: h.precipitation || [],
      pressure: h.pressure_msl || [],
      code: h.weather_code || [],
      dailyT: (json.daily || {}).time || [],
      dailyMeanC: (json.daily || {}).temperature_2m_mean || [],
    };
  }

  var inflight = {};

  /** Fetch a cell, or hand back what we already have. Never rejects. */
  function load(lat, lon, opts) {
    var key = cellKey(lat, lon);
    var cached = read(key);
    var force = opts && opts.force;
    var fresh = cached && (Date.now() - cached.fetchedAt) < TTL_MS;
    if (fresh && !force) {
      return Promise.resolve({ data: cached.data, fetchedAt: cached.fetchedAt, source: "cache" });
    }
    if (inflight[key]) return inflight[key];

    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timer = setTimeout(function () { if (controller) controller.abort(); }, TIMEOUT_MS);

    inflight[key] = fetch(url(lat, lon), controller ? { signal: controller.signal } : undefined)
      .then(function (res) {
        // A rate limit is not an error worth showing anyone: it means the same
        // thing to this app as being offline does.
        if (res.status === 429) throw new Error("rate-limited");
        if (!res.ok) throw new Error("http " + res.status);
        return res.json();
      })
      .then(function (json) {
        var data = compact(json);
        var at = Date.now();
        write(key, { data: data, fetchedAt: at });
        return { data: data, fetchedAt: at, source: "network" };
      })
      .catch(function () {
        // Stale beats blank: an old forecast at the lake is worth more than
        // nothing, as long as it says how old it is.
        if (cached) return { data: cached.data, fetchedAt: cached.fetchedAt, source: "cache" };
        return { data: null, fetchedAt: null, source: "none" };
      })
      .then(function (out) {
        clearTimeout(timer);
        delete inflight[key];
        return out;
      });
    return inflight[key];
  }

  /** Whatever is already cached for this point, without going near the network. */
  function peek(lat, lon) {
    var cached = read(cellKey(lat, lon));
    if (!cached) return { data: null, fetchedAt: null, source: "none" };
    return { data: cached.data, fetchedAt: cached.fetchedAt, source: "cache" };
  }

  // ============================================================
  // READING A MOMENT OUT OF IT
  // ============================================================

  function nearestIndex(data, when) {
    if (!data || !data.t || !data.t.length) return -1;
    var target = Math.round(when.getTime() / 1000);
    var lo = 0, hi = data.t.length - 1;
    if (target <= data.t[0]) return 0;
    if (target >= data.t[hi]) return hi;
    while (hi - lo > 1) {
      var mid = (lo + hi) >> 1;
      if (data.t[mid] <= target) lo = mid; else hi = mid;
    }
    return (target - data.t[lo]) <= (data.t[hi] - target) ? lo : hi;
  }

  function value(list, i) {
    var v = list && list[i];
    return typeof v === "number" && isFinite(v) ? v : null;
  }

  /** The shape js/conditions.js expects, for one instant. */
  function at(data, when) {
    var i = nearestIndex(data, when);
    if (i < 0) return null;
    var p = value(data.pressure, i);
    var back = function (hours) {
      var j = i - hours;
      var earlier = j >= 0 ? value(data.pressure, j) : null;
      return (p === null || earlier === null) ? null : p - earlier;
    };
    return {
      airTempC: value(data.airC, i),
      cloudCoverPct: value(data.cloud, i),
      windKph: value(data.wind, i),
      gustKph: value(data.gust, i),
      precipMm: value(data.precip, i),
      pressureMslHpa: p,
      dP3h: back(3),
      dP12h: back(12),
      weatherCode: value(data.code, i),
      index: i,
    };
  }

  /** Daily mean air temperature up to a date, for the water model. */
  function dailyMeansUpTo(data, when) {
    if (!data || !data.dailyT) return [];
    var cutoff = Math.round(when.getTime() / 1000);
    var out = [];
    for (var i = 0; i < data.dailyT.length; i++) {
      if (data.dailyT[i] > cutoff) break;
      var v = value(data.dailyMeanC, i);
      if (v !== null) out.push(v);
    }
    return out.slice(-7);
  }

  /** How far ahead of now a moment is, in days, for the forecast-decay term. */
  function leadDays(when) {
    return Math.max(0, (when.getTime() - Date.now()) / 86400000);
  }

  /** Plain words for how old a cached forecast is. */
  function ageText(fetchedAt) {
    if (!fetchedAt) return "";
    var mins = Math.round((Date.now() - fetchedAt) / 60000);
    if (mins < 2) return "just now";
    if (mins < 60) return mins + " min ago";
    var hours = Math.round(mins / 60);
    if (hours < 24) return hours + " h ago";
    return Math.round(hours / 24) + " d ago";
  }

  window.Weather = {
    cellKey: cellKey,
    url: url,
    load: load,
    peek: peek,
    at: at,
    dailyMeansUpTo: dailyMeansUpTo,
    leadDays: leadDays,
    ageText: ageText,
    nearestIndex: nearestIndex,
    TTL_MS: TTL_MS,
    _internal: { compact: compact, read: read, write: write, evict: evict },
  };
})();
