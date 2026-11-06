/* My spots (Build 5 Stage 3a): the owner's own saved places, imported from a file
 * he picks on each device, kept only in this browser (IndexedDB "troutmap-spots").
 * Nothing here sends a spot anywhere, and none is ever in the repository.
 *
 * Files read: Google Takeout "Saved Places.json" (GeoJSON), Takeout saved-list
 * CSV (Title, Note, URL, Comment), Google My Maps KMZ (zipped KML), KML and
 * GeoJSON. Each place becomes {name, lat, lon, note, address, tags, url}.
 *
 * Matching (decision 30, the lake outlines in data/lake_outlines.json):
 *   a lake      inside its outline or within LAKE_NEAR_M of its shore (a lake with
 *               no outline has a circle: its area plus 1 km); two lakes match →
 *               the nearer shore, then the nearer lake point
 *   skipped     a place with a street address more than TOWN_FAR_M from every lake
 *               (restaurants, shops): counted, not kept
 *   a river     within RIVER_NEAR_M of a river stretch's line
 *   not on a lake   the rest with a position
 *   saved lake  a place with only a name, matched by name to one lake
 *   not placed  a name with no lake, or with several lakes of that name
 * The counts always add up to the places in the file.
 */
(function () {
  "use strict";

  var UNCONFIRMED = "Unconfirmed";
  var LAKE_NEAR_M = 500, RIVER_NEAR_M = 300, TOWN_FAR_M = 1000;
  var DB = "troutmap-spots", STORE = "imports", KEY = "current";

  // ============================================================ geometry
  function kx(lat) { return 111320 * Math.cos(lat * Math.PI / 180); }
  var KY = 110570;

  function metres(a, b) {
    var x = (b[1] - a[1]) * kx((a[0] + b[0]) / 2), y = (b[0] - a[0]) * KY;
    return Math.sqrt(x * x + y * y);
  }

  function segM(p, a, b) {
    var k = kx(p[0]);
    var px = p[1] * k, py = p[0] * KY, ax = a[1] * k, ay = a[0] * KY, bx = b[1] * k, by = b[0] * KY;
    var dx = bx - ax, dy = by - ay, t = 0;
    if (dx || dy) t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)));
    var ex = px - ax - t * dx, ey = py - ay - t * dy;
    return Math.sqrt(ex * ex + ey * ey);
  }

  function inRing(p, ring) {
    var y = p[0], x = p[1], hit = false;
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      var yi = ring[i][0], xi = ring[i][1], yj = ring[j][0], xj = ring[j][1];
      if ((yi > y) !== (yj > y) && x < xi + (y - yi) * (xj - xi) / (yj - yi)) hit = !hit;
    }
    return hit;
  }

  function decodeRing(flat) {
    var out = [], lat = 0, lon = 0;
    for (var k = 0; k < flat.length; k += 2) { lat += flat[k]; lon += flat[k + 1]; out.push([lat / 1e5, lon / 1e5]); }
    return out;
  }

  /** data/lake_outlines.json → {key: {rings, box} | {circle: [lat, lon, r]}} */
  function prepOutlines(doc) {
    var out = {};
    Object.keys((doc && doc.lakes) || {}).forEach(function (key) {
      var v = doc.lakes[key];
      if (v.rings) {
        var rings = v.rings.map(decodeRing), box = [90, 180, -90, -180];
        rings.forEach(function (r) {
          r.forEach(function (q) {
            if (q[0] < box[0]) box[0] = q[0]; if (q[1] < box[1]) box[1] = q[1];
            if (q[0] > box[2]) box[2] = q[0]; if (q[1] > box[3]) box[3] = q[1];
          });
        });
        out[key] = { rings: rings, box: box };
      } else if (v.circle) {
        out[key] = { circle: v.circle };
      }
    });
    return out;
  }

  /** Metres from p to the lake's shore: 0 inside. A circle counts as the shore. */
  function shoreM(p, o) {
    if (o.circle) return Math.max(0, metres(p, o.circle) - o.circle[2]);
    var best = Infinity;
    for (var r = 0; r < o.rings.length; r++) {
      var ring = o.rings[r];
      if (inRing(p, ring)) return 0;
      for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        var d = segM(p, ring[j], ring[i]);
        if (d < best) best = d;
      }
    }
    return best;
  }

  function nearBox(p, o, m) {
    if (o.circle) return metres(p, o.circle) <= o.circle[2] + m;
    var dy = m / KY, dx = m / kx(p[0]);
    return p[0] >= o.box[0] - dy && p[0] <= o.box[2] + dy && p[1] >= o.box[1] - dx && p[1] <= o.box[3] + dx;
  }

  /** The matching lake for a point, or null; also the nearest shore in metres. */
  function matchLake(p, ctx) {
    var best = null, nearest = Infinity;
    for (var n = 0; n < ctx.lakes.length; n++) {
      var lake = ctx.lakes[n], o = ctx.outlines[lake.key];
      if (!o || !nearBox(p, o, TOWN_FAR_M)) continue;
      var m = shoreM(p, o);
      if (m < nearest) nearest = m;
      var ok = o.circle ? m === 0 : m <= LAKE_NEAR_M;
      if (!ok) continue;
      var byPoint = metres(p, [lake.lat, lake.lon]);
      if (!best || m < best.m - 1e-6 || (Math.abs(m - best.m) <= 1e-6 && byPoint < best.byPoint))
        best = { key: lake.key, m: m, byPoint: byPoint };
    }
    return { lake: best, nearestShoreM: nearest };
  }

  function matchRiver(p, ctx) {
    var best = null;
    (ctx.rivers || []).forEach(function (rv) {
      (rv.line || []).forEach(function (part) {
        for (var i = 1; i < part.length; i++) {
          var d = segM(p, part[i - 1], part[i]);
          if (d <= RIVER_NEAR_M && (!best || d < best.m)) best = { key: rv.key, m: d };
        }
      });
    });
    return best;
  }

  // ============================================================ names
  var NOISE = /\b(the|a|an|of|and)\b/g;
  var WATER_WORD = /\b(lake|lakes|pond|ponds|reservoir|slough|river|creek)\b/;

  function plain(s) {
    s = String(s || "");
    if (s.normalize) s = s.normalize("NFKD").replace(/[̀-ͯ]/g, "");
    return s.toLowerCase();
  }

  /** scripts/registry.py normalize_name, in the browser. */
  function normName(s) {
    return plain(s).replace(/&/g, " and ").replace(/[^a-z0-9 ]/g, " ").replace(NOISE, " ").replace(/\s+/g, " ").trim();
  }

  function nameForms(s) {
    var forms = {}, n = normName(s), bare = normName(String(s || "").replace(/\([^)]*\)/g, " "));
    [n, bare].forEach(function (f) {
      if (!f) return;
      forms[f] = 1;
      if (!WATER_WORD.test(f)) forms[f + " lake"] = 1;
    });
    return Object.keys(forms);
  }

  function matchName(name, ctx) {
    var forms = nameForms(name), hits = {};
    if (!forms.length) return { why: "no name" };
    if (!ctx.byName) {
      ctx.byName = {};
      ctx.lakes.forEach(function (l) {
        nameForms(l.name).forEach(function (f) { (ctx.byName[f] = ctx.byName[f] || []).push(l.key); });
      });
    }
    forms.forEach(function (f) { (ctx.byName[f] || []).forEach(function (k) { hits[k] = 1; }); });
    var keys = Object.keys(hits);
    if (keys.length === 1) return { key: keys[0] };
    return { why: keys.length ? "several lakes have this name" : "no Alberta lake with this name" };
  }

  // ============================================================ tags
  function cleanTags(list) {
    var out = [];
    (list || []).forEach(function (t) {
      t = String(t || "").replace(/\.(csv|kml|kmz|json|geojson)$/i, "").trim();
      if (!t) return;
      if (/need to validate|unconfirmed/i.test(t)) t = UNCONFIRMED;
      if (out.indexOf(t) < 0) out.push(t);
    });
    return out;
  }

  function tagList(v) {
    if (!v) return [];
    if (Array.isArray(v)) return v.map(String);
    return String(v).split(/[,;]/);
  }

  // ============================================================ parsers
  function num(v) { var x = Number(v); return isFinite(x) ? x : NaN; }

  function goodLatLon(lat, lon) {
    return isFinite(lat) && isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 && !(lat === 0 && lon === 0);
  }

  function coordsFromUrl(url) {
    if (!url) return null;
    var u = String(url);
    try { u = decodeURIComponent(u); } catch (e) { /* keep as is */ }
    var pats = [/[?&](?:q|query|ll|destination)=(-?\d+(?:\.\d+)?)\s*,\s*\+?(-?\d+(?:\.\d+)?)/,
      /\/maps\/search\/(-?\d+(?:\.\d+)?)\s*,\s*\+?(-?\d+(?:\.\d+)?)/,
      /!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)/,
      /@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/];
    for (var i = 0; i < pats.length; i++) {
      var m = u.match(pats[i]);
      if (m) {
        var lat = num(m[1]), lon = num(m[2]);
        if (goodLatLon(lat, lon)) return [lat, lon];
      }
    }
    return null;
  }

  function place(o) {
    var lat = num(o.lat), lon = num(o.lon);
    if (!goodLatLon(lat, lon)) {
      var c = coordsFromUrl(o.url);
      if (c) { lat = c[0]; lon = c[1]; } else { lat = lon = null; }
    }
    return {
      name: String(o.name || "").trim(), lat: lat, lon: lon,
      note: String(o.note || "").trim(), address: String(o.address || "").trim(),
      tags: cleanTags(o.tags), url: String(o.url || "").trim()
    };
  }

  /** CSV with quotes (RFC 4180), first row the header. */
  function csvRows(text) {
    var rows = [], row = [], cell = "", q = false;
    text = String(text || "").replace(/^﻿/, "");
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      if (q) {
        if (ch === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; }
        else cell += ch;
      } else if (ch === '"') q = true;
      else if (ch === ",") { row.push(cell); cell = ""; }
      else if (ch === "\n" || ch === "\r") {
        if (ch === "\r" && text[i + 1] === "\n") i++;
        row.push(cell); cell = "";
        if (row.length > 1 || row[0] !== "") rows.push(row);
        row = [];
      } else cell += ch;
    }
    if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
    return rows;
  }

  function parseCsv(text, listName) {
    var rows = csvRows(text);
    if (!rows.length) return [];
    var head = rows[0].map(function (h) { return h.trim().toLowerCase(); });
    var col = function (names) {
      for (var i = 0; i < names.length; i++) { var k = head.indexOf(names[i]); if (k >= 0) return k; }
      return -1;
    };
    var cName = col(["title", "name"]), cNote = col(["note", "notes", "description"]), cUrl = col(["url", "link", "google maps url"]),
      cComment = col(["comment", "comments"]), cTags = col(["tags", "tag", "list"]), cLat = col(["latitude", "lat"]),
      cLon = col(["longitude", "lon", "lng"]), cAddr = col(["address"]);
    var get = function (r, k) { return k >= 0 && k < r.length ? r[k] : ""; };
    return rows.slice(1).map(function (r) {
      var note = [get(r, cNote), get(r, cComment)].filter(function (s) { return s && s.trim(); }).join(" — ");
      return place({ name: get(r, cName), note: note, url: get(r, cUrl), lat: get(r, cLat), lon: get(r, cLon),
        address: get(r, cAddr), tags: (listName ? [listName] : []).concat(tagList(get(r, cTags))) });
    }).filter(function (p) { return p.name || p.lat != null; });
  }

  /** GeoJSON, including Google Takeout's "Saved Places.json". */
  function parseGeoJson(doc, fileTag) {
    var feats = doc && doc.type === "FeatureCollection" ? doc.features || [] : doc && doc.type === "Feature" ? [doc] : [];
    return feats.map(function (f) {
      var p = f.properties || {}, loc = p.location || p.Location || {};
      var g = f.geometry || {}, c = g.type === "Point" && Array.isArray(g.coordinates) ? g.coordinates : null;
      var tags = tagList(p.tags || p.Tags).concat(tagList(p.list || p.List || p.folder || p.layer || p.category));
      if (!tags.length && fileTag) tags = [fileTag];
      return place({
        name: p.name || p.Name || p.title || p.Title || loc.name || loc.Name || "",
        note: p.note || p.Note || p.description || p.Description || p.comment || p.Comment || "",
        address: p.address || p.Address || loc.address || loc.Address || "",
        url: p.google_maps_url || p["Google Maps URL"] || p.url || p.URL || "",
        lat: c ? c[1] : loc.latitude, lon: c ? c[0] : loc.longitude, tags: tags
      });
    });
  }

  function xmlText(s) {
    s = String(s || "").replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1");
    s = s.replace(/<br\s*\/?>/gi, " ").replace(/<[^>]+>/g, " ");
    s = s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&amp;/g, "&");
    return s.replace(/\s+/g, " ").trim();
  }

  function firstTag(block, tag) {
    var m = block.match(new RegExp("<" + tag + "\\b[^>]*>([\\s\\S]*?)</" + tag + ">", "i"));
    return m ? m[1] : "";
  }

  /** KML (also the inside of a My Maps KMZ): each Folder name (a My Maps layer) is a tag. */
  function parseKml(text, fileTag) {
    var out = [], folders = [], re = /<Folder\b[^>]*>|<\/Folder>|<Placemark\b[^>]*>([\s\S]*?)<\/Placemark>/gi, m;
    text = String(text || "");
    while ((m = re.exec(text))) {
      var t = m[0];
      if (/^<Folder/i.test(t)) {
        var rest = text.slice(re.lastIndex), cut = rest.search(/<(Placemark|Folder)\b/i);
        folders.push(xmlText(firstTag(cut >= 0 ? rest.slice(0, cut) : rest, "name")));
      } else if (/^<\/Folder/i.test(t)) folders.pop();
      else {
        var body = m[1], point = firstTag(body, "Point"), coords = firstTag(point, "coordinates").trim().split(/[\s]+/)[0] || "";
        var xy = coords.split(",");
        var tags = folders.filter(Boolean);
        if (!tags.length && fileTag) tags = [fileTag];
        out.push(place({ name: xmlText(firstTag(body, "name")), note: xmlText(firstTag(body, "description")),
          address: xmlText(firstTag(body, "address")), lat: point ? xy[1] : NaN, lon: point ? xy[0] : NaN, tags: tags }));
      }
    }
    return out;
  }

  /** The first .kml inside a KMZ (a zip), unzipped in the browser. */
  function unzipKml(buf, inflate) {
    var b = new Uint8Array(buf), dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
    var eocd = -1;
    for (var i = b.length - 22; i >= Math.max(0, b.length - 65557); i--) if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    if (eocd < 0) return Promise.reject(new Error("This KMZ is not a zip file."));
    var n = dv.getUint16(eocd + 10, true), p = dv.getUint32(eocd + 16, true), pick = null;
    for (var e = 0; e < n; e++) {
      if (dv.getUint32(p, true) !== 0x02014b50) break;
      var method = dv.getUint16(p + 10, true), size = dv.getUint32(p + 20, true);
      var nl = dv.getUint16(p + 28, true), xl = dv.getUint16(p + 30, true), cl = dv.getUint16(p + 32, true), off = dv.getUint32(p + 42, true);
      var name = new TextDecoder().decode(b.subarray(p + 46, p + 46 + nl));
      if (/\.kml$/i.test(name) && (!pick || /(^|\/)doc\.kml$/i.test(name))) pick = { method: method, size: size, off: off };
      p += 46 + nl + xl + cl;
    }
    if (!pick) return Promise.reject(new Error("No KML inside this KMZ."));
    var lo = pick.off, start = lo + 30 + dv.getUint16(lo + 26, true) + dv.getUint16(lo + 28, true);
    var data = b.subarray(start, start + pick.size);
    if (pick.method === 0) return Promise.resolve(new TextDecoder().decode(data));
    if (pick.method !== 8) return Promise.reject(new Error("This KMZ uses a zip method the app cannot read."));
    return (inflate || inflateRaw)(data).then(function (out) { return new TextDecoder().decode(out); });
  }

  function inflateRaw(data) {
    if (typeof DecompressionStream === "undefined")
      return Promise.reject(new Error("This browser cannot open a KMZ. Export the map as KML instead, or use another browser."));
    var ds = new DecompressionStream("deflate-raw");
    var stream = new Blob([data]).stream().pipeThrough(ds);
    return new Response(stream).arrayBuffer().then(function (a) { return new Uint8Array(a); });
  }

  /** name, and the file's text or bytes → places. */
  function parseFile(name, data) {
    var base = String(name || "").replace(/^.*[\\/]/, ""), ext = (base.match(/\.([a-z0-9]+)$/i) || [])[1] || "";
    var tag = base.replace(/\.[^.]+$/, "");
    var text = function () { return typeof data === "string" ? data : new TextDecoder().decode(new Uint8Array(data)); };
    ext = ext.toLowerCase();
    try {
      if (ext === "kmz") return unzipKml(data).then(function (k) { return parseKml(k, tag); });
      if (ext === "kml") return Promise.resolve(parseKml(text(), tag));
      if (ext === "csv") return Promise.resolve(parseCsv(text(), tag));
      if (ext === "json" || ext === "geojson") {
        // A Takeout "Saved Places.json" has no list; its places keep no tag from the file name.
        var fileTag = /saved places/i.test(tag) ? "" : tag;
        return Promise.resolve(parseGeoJson(JSON.parse(text()), fileTag));
      }
    } catch (e) {
      return Promise.reject(new Error("This file could not be read: " + e.message));
    }
    return Promise.reject(new Error("The app reads .json, .geojson, .csv, .kml and .kmz files."));
  }

  // ============================================================ classify
  function spotId(p) {
    var s = p.name + "|" + (p.lat == null ? "" : p.lat.toFixed(5)) + "|" + (p.lon == null ? "" : p.lon.toFixed(5)), h = 5381;
    for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
    return "s" + h.toString(36);
  }

  function hasStreet(address) { return /\d/.test(address || ""); }

  /** places → {spots, saved, notPlaced, skipped, total, counts}. ctx = {lakes, outlines, rivers}. */
  function classify(places, ctx) {
    var spots = [], saved = [], notPlaced = [], skipped = 0, seen = {};
    places.forEach(function (p) {
      var id = spotId(p);
      if (seen[id]) { seen[id].tags = cleanTags(seen[id].tags.concat(p.tags)); return; }   // the same place in two lists
      if (p.lat != null) {
        var pt = [p.lat, p.lon], m = matchLake(pt, ctx);
        var rec = { id: id, name: p.name, lat: p.lat, lon: p.lon, note: p.note, tags: p.tags, url: p.url,
          unconfirmed: p.tags.indexOf(UNCONFIRMED) >= 0, lake: null, river: null };
        if (m.lake) { rec.lake = m.lake.key; rec.shoreM = Math.round(m.lake.m); }
        else if (hasStreet(p.address) && !(m.nearestShoreM <= TOWN_FAR_M)) { skipped++; seen[id] = rec; return; }
        else { var rv = matchRiver(pt, ctx); if (rv) rec.river = rv.key; }
        seen[id] = rec;
        spots.push(rec);
      } else {
        var nm = matchName(p.name, ctx);
        var r2 = { id: id, name: p.name, note: p.note, tags: p.tags, unconfirmed: p.tags.indexOf(UNCONFIRMED) >= 0 };
        seen[id] = r2;
        if (nm.key) { r2.lake = nm.key; saved.push(r2); } else { r2.why = nm.why; notPlaced.push(r2); }
      }
    });
    var dup = places.length - spots.length - saved.length - notPlaced.length - skipped;
    var counts = {
      lake: spots.filter(function (s) { return s.lake; }).length,
      river: spots.filter(function (s) { return !s.lake && s.river; }).length,
      offLake: spots.filter(function (s) { return !s.lake && !s.river; }).length,
      saved: saved.length, notPlaced: notPlaced.length, skipped: skipped, duplicates: dup
    };
    return { spots: spots, saved: saved, notPlaced: notPlaced, skipped: skipped, total: places.length, counts: counts };
  }

  // ============================================================ storage (this browser only)
  var memory = null, dbPromise = null;

  function openDb() {
    if (dbPromise) return dbPromise;
    dbPromise = new Promise(function (resolve) {
      try {
        if (typeof indexedDB === "undefined" || !indexedDB) { resolve(null); return; }
        var req = indexedDB.open(DB, 1);
        req.onupgradeneeded = function () { req.result.createObjectStore(STORE); };
        req.onsuccess = function () { resolve(req.result); };
        req.onerror = req.onblocked = function () { resolve(null); };
      } catch (e) { resolve(null); }
    });
    return dbPromise;
  }

  function tx(mode, fn) {
    return openDb().then(function (db) {
      if (!db) return null;
      return new Promise(function (resolve) {
        try {
          var t = db.transaction(STORE, mode), out = fn(t.objectStore(STORE));
          t.oncomplete = function () { resolve(out && "result" in out ? out.result : true); };
          t.onerror = t.onabort = function () { resolve(null); };
        } catch (e) { resolve(null); }
      });
    });
  }

  /** A new import replaces the last one, so importing twice never doubles the spots. */
  function save(result, fileName) {
    memory = { file: String(fileName || ""), importedAt: new Date().toISOString(), result: result };
    return tx("readwrite", function (s) { s.put(memory, KEY); }).then(function () { return memory; });
  }

  function load() {
    return tx("readonly", function (s) { return s.get(KEY); }).then(function (rec) {
      memory = rec || null;
      return memory;
    });
  }

  function clear() {
    memory = null;
    return tx("readwrite", function (s) { s.delete(KEY); });
  }

  function current() { return memory; }

  function forLake(key) {
    if (!memory) return [];
    return memory.result.spots.filter(function (s) { return s.lake === key || (!s.lake && s.river === key); });
  }

  function savedFor(key) {
    if (!memory) return [];
    return memory.result.saved.filter(function (s) { return s.lake === key; });
  }

  function offLake() {
    if (!memory) return [];
    return memory.result.spots.filter(function (s) { return !s.lake && !s.river; });
  }

  window.MySpots = {
    UNCONFIRMED: UNCONFIRMED,
    parseFile: parseFile, classify: classify, prepOutlines: prepOutlines,
    save: save, load: load, clear: clear, current: current,
    forLake: forLake, savedFor: savedFor, offLake: offLake,
    _internal: { parseCsv: parseCsv, parseGeoJson: parseGeoJson, parseKml: parseKml, unzipKml: unzipKml,
      coordsFromUrl: coordsFromUrl, normName: normName, nameForms: nameForms, matchLake: matchLake,
      matchName: matchName, shoreM: shoreM, cleanTags: cleanTags, csvRows: csvRows, spotId: spotId,
      setMemory: function (m) { memory = m; } }
  };
})();
