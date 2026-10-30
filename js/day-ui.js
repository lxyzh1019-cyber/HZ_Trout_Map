/* The day picker and everything that hangs off it: the week bar over the map,
 * "Best near you", the list beside the map on a PC, the four buttons (Near me,
 * Saved, Area, Clear), search for towns and lakes, and the few full-screen
 * messages (no signal, no lakes in range, first visit).
 *
 * The question this answers is "which lake, which day". The filters panel
 * still answers "which lakes at all", and every list here only ranks lakes the
 * filters let through.
 *
 * A town picked in search is a place to look from, not a new home: home is
 * where the directions start and it stays put. While a town is picked the
 * distances, the distance filter and the lists all measure from the town.
 */
(function () {
  "use strict";

  var NEAR_KM = [100, 200, Infinity];   // "near you" widens until it has three lakes
  var TOWNS = null, townsLoading = null;
  var GEO = "https://geocoding-api.open-meteo.com/v1/search";
  var STORE_VISITED = "troutmap.visited";
  var fx = { loading: false, done: 0, of: 0, lastSummary: null };

  function num(v) { return typeof v === "number" && isFinite(v) ? v : null; }
  function $(id) { return document.getElementById(id); }
  function pct(s) { return num(s) === null ? null : Math.round(s * 100); }
  function isPc() { return matchMedia("(min-width: 1024px)").matches; }

  // ============================================================
  // WHERE WE ARE LOOKING FROM
  // ============================================================

  function originPoint() { return state.origin || state.home; }

  function setOrigin(o) {
    state.origin = o ? { lat: Number(o.lat), lon: Number(o.lon), name: o.name, kind: o.kind || "town" } : null;
    recomputeDistances();
    if (typeof placeOriginMarker === "function") placeOriginMarker();
    onFilterChange();
  }

  // ============================================================
  // WHICH LAKES, AND HOW THEY RANK
  // ============================================================

  function pool() {
    var lakes = mappableLakes();
    if (state.onScreen && map) {
      var b = map.getBounds();
      lakes = lakes.filter(function (l) { return b.contains([l.lat, l.lon]); });
    }
    return lakes;
  }

  function biteOn(lake, d) { return Forecast.rankable(Forecast.forLake(lake), d); }

  function bestWeek(lake) {
    var f = Forecast.forLake(lake);
    // A frozen lake has no open-water best day (winter guard).
    if (!f || f.iced || f.bestDay < 0) return null;
    return f.days[f.bestDay].bite;
  }

  /** Higher score first; lakes that cannot be ranked go last, nearest first. */
  function byScore(score) {
    return function (a, b) {
      var sa = score(a), sb = score(b);
      if (sa === null && sb === null) return a.distanceKm - b.distanceKm;
      if (sa === null) return 1;
      if (sb === null) return -1;
      return sb - sa || a.distanceKm - b.distanceKm;
    };
  }

  function nearby(lakes) {
    for (var i = 0; i < NEAR_KM.length; i++) {
      var within = lakes.filter(function (l) { return l.distanceKm <= NEAR_KM[i]; });
      if (within.length >= 3 || i === NEAR_KM.length - 1) return within;
    }
    return lakes;
  }

  /* More than half the lakes in view have had a frozen week: the bar shows
   * wind chill and the pins show the ice season (Build 1b, decision 15). */
  function winterOn() {
    // Only lakes already computed: computing the rest here would undo the sliced computeAll.
    var lakes = inView().filter(Forecast.ready);
    if (!lakes.length) return false;
    var iced = lakes.filter(function (l) { var f = Forecast.forLake(l); return f && f.iced; }).length;
    return iced * 2 > lakes.length;
  }

  function inView() {
    var lakes = mappableLakes();
    if (map && map.getBounds) {
      var b = map.getBounds();
      var shown = lakes.filter(function (l) { return b.contains([l.lat, l.lon]); });
      if (shown.length) return shown;
    }
    return lakes;
  }

  function ranked() {
    var d = state.day, lakes = pool(), winter = winterOn();
    var title, list;
    if (state.nav === "saved") {
      list = lakes.filter(function (l) { return state.favourites.has(lakeKey(l)); }).sort(byScore(bestWeek));
      title = "Saved lakes, by best day";
    } else if (state.nav === "near") {
      list = lakes.slice().sort(function (a, b) { return a.distanceKm - b.distanceKm; });
      title = "Nearest lakes";
    } else if (state.nav === "area") {
      var zone = state.area || zonesInPlay()[0];
      list = lakes.filter(function (l) { return l.zone === zone; }).sort(byScore(function (l) { return biteOn(l, d); }));
      title = "Lakes in " + (zone || "a zone");
    } else if (winter) {
      list = nearby(lakes).sort(function (a, b) {
        var ia = lakeIceKind(a) && lakeIceKind(a) !== "closed" ? 0 : 1;
        var ib = lakeIceKind(b) && lakeIceKind(b) !== "closed" ? 0 : 1;
        return ia - ib || a.distanceKm - b.distanceKm;
      });
      title = "Ice season lakes near " + originPoint().name;
    } else if (state.origin) {
      list = lakes.slice().sort(function (a, b) { return a.distanceKm - b.distanceKm; });
      title = "Lakes near " + state.origin.name;
    } else {
      list = nearby(lakes).sort(byScore(function (l) { return biteOn(l, d); }));
      title = "Best near you, " + dayLabel(d);
    }
    return { title: title, list: list, winter: winter };
  }

  function zonesInPlay() {
    var seen = {};
    mappableLakes().forEach(function (l) { if (l.zone) seen[l.zone] = (seen[l.zone] || 0) + 1; });
    return Object.keys(seen).sort();
  }

  // ============================================================
  // DAY NAMES AND THE WEEK BAR
  // ============================================================

  function refForecast() {
    var lakes = inView();
    for (var i = 0; i < lakes.length; i++) {
      var f = Forecast.forLake(lakes[i]);
      if (f && f.hasWeather) return f;
    }
    return lakes.length ? Forecast.forLake(lakes[0]) : null;
  }

  function dayLabel(d) {
    var f = refForecast();
    if (f) return d === 0 ? "today" : LakeSheet.dayName(f, d);
    var t = new Date(Date.now() + d * 86400000);
    return d === 0 ? "today" : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][t.getDay()];
  }

  function median(vals) {
    if (!vals.length) return null;
    var s = vals.slice().sort(function (a, b) { return a - b; });
    return s[Math.floor(s.length / 2)];
  }

  function drawWeek() {
    var host = $("week");
    if (!host) return;
    var lakes = inView();
    var f = refForecast();
    var winter = winterOn();
    var out = "";
    for (var d = 0; d < 7; d++) {
      var top = null, gusty = 0, chills = [], n = 0;
      lakes.forEach(function (l) {
        var g = Forecast.forLake(l);
        if (!g) return;
        var day = g.days[d];
        n++;
        var s = Forecast.rankable(g, d);
        if (s !== null && (top === null || s > top)) top = s;
        if (num(day.gustMax) !== null && day.gustMax >= Conditions.GUST_WARN_KPH) gusty++;
        if (num(day.chillMin) !== null) chills.push(day.chillMin);
      });
      var name = f ? LakeSheet.dayName(f, d) : dayLabel(d);
      var value = winter ? (median(chills) === null ? "—" : Math.round(median(chills)) + "°")
        : (top === null ? "—" : pct(top));
      var label = name + ": " + (winter ? "wind chill " + value : "top Bite " + value)
        + (!winter && gusty * 2 > n && n ? ", gusty on most lakes" : "");
      out += '<button type="button" data-day="' + d + '" aria-pressed="' + (d === state.day) + '" aria-label="' + esc(label) + '">'
        + '<span class="d">' + esc(d === 0 ? "Today" : name) + "</span>"
        + '<span class="b">' + esc(value) + "</span>"
        + (!winter && n && gusty * 2 > n ? '<span class="flag">gusty</span>' : "")
        + "</button>";
    }
    host.innerHTML = out;
    host.setAttribute("aria-label", winter ? "Pick a day: wind chill" : "Pick a day: top Bite score on screen");
  }

  function drawLegend() {
    var host = $("score-legend");
    if (!host) return;
    var mode = state.colorMode;
    if (state.view !== "map" || (mode !== "bite" && mode !== "best")) { host.hidden = true; return; }
    host.hidden = false;
    if (winterOn()) {
      host.innerHTML = '<span><i style="background:' + ICE_PIN.all + '"></i>Open all winter</span>'
        + '<span><i style="background:' + ICE_PIN.part + '"></i>Early or late ice</span>'
        + '<span><i style="background:' + ICE_PIN.closed + '"></i>Closed in winter</span>'
        + "<span>Week bar: wind chill</span>";
      return;
    }
    host.innerHTML = (mode === "best" ? "<span><b>Best this week</b></span>" : "")
      + ["Prime", "Good", "Fair", "Poor"].map(function (b) {
        return '<span><i style="background:' + SCORE_PIN[b] + '"></i>' + LakeSheet.BAND_WORD[b] + "</span>";
      }).join("");
  }

  // ============================================================
  // ROWS: THE LIST, THE CARD AND SEARCH
  // ============================================================

  function dayOutPill(lake, d, winter) {
    var f = Forecast.forLake(lake);
    var day = f && f.days[d];
    if (!day) return ["", ""];
    if (winter || f.iced) return ["cold", num(day.chillMin) === null ? "ice likely" : Math.round(day.chillMin) + " °C wind chill"];
    if (day.closed) return ["shut", "season shut"];
    if (num(day.gustMax) !== null && day.gustMax >= Conditions.GUST_WARN_KPH) return ["gusty", "gusts " + Math.round(day.gustMax) + " km/h"];
    if ((num(day.precipChancePct) || 0) > 60 || (num(day.precipMm) || 0) > 2) return ["rainy", "rain likely"];
    if (num(day.dayOut) === null) return ["", "no forecast"];
    return [day.dayOut >= 0.6 ? "calm" : day.dayOut >= 0.42 ? "breezy" : "gusty",
            "Day out " + LakeSheet.bandWord(day.dayOut)];
  }

  function rowHtml(lake, d, winter) {
    var f = Forecast.forLake(lake);
    var s = f ? Forecast.rankable(f, d) : null;
    var pill = dayOutPill(lake, d, winter);
    var km = Number.isFinite(lake.distanceKm) ? Math.round(lake.distanceKm) + " km" : "";
    var size = lake.surface_area_ha != null ? lake.surface_area_ha + " ha" : "size unknown";
    var score = winter || (f && f.iced) ? "ice" : s === null ? "—" : pct(s);
    return '<button type="button" class="row" data-lake="' + esc(lakeKey(lake)) + '">'
      + '<span><span class="nm">' + esc(lake.name) + "</span><br>"
      + '<span class="sub">' + esc([km, size].filter(Boolean).join(" · ")) + (lakeBaitBan(lake) ? " · bait ban" : "") + "</span></span>"
      + '<span class="sc" title="Bite score">' + esc(score) + "</span>"
      + '<span class="dayout ' + pill[0] + '">' + esc(pill[1]) + "</span></button>";
  }

  var NOTE = '<p class="note">Bite = will the fish feed. Day out = wind, gusts, rain and cold for being on the water. '
    + "Nearby lakes can differ on the same day: each has its own forecast spot, size and water temperature. Open a lake and tap Why.</p>";

  function zonesHtml() {
    if (state.nav !== "area") return "";
    var zone = state.area || zonesInPlay()[0];
    return '<div class="zones" role="group" aria-label="Fish management zone">' + zonesInPlay().map(function (z) {
      return '<button type="button" data-zone="' + esc(z) + '" aria-pressed="' + (z === zone) + '">' + esc(z)
        + (ZONE_REGIONS[z.slice(0, 2)] ? " <small>" + esc(ZONE_REGIONS[z.slice(0, 2)]) + "</small>" : "") + "</button>";
    }).join("") + "</div>";
  }

  function originChip() {
    if (!state.origin) return "";
    return '<button type="button" class="chipbtn" data-clear-origin aria-label="Stop measuring from '
      + esc(state.origin.name) + '">Near ' + esc(state.origin.name) + " ✕</button>";
  }

  function drawLists() {
    var r = ranked(), d = state.day;
    var rows = r.list.map(function (l) { return rowHtml(l, d, r.winter); }).join("");
    var empty = !r.list.length ? '<p class="note">' + (state.nav === "saved"
      ? "No saved lakes pass the filters. Tap ☆ on a lake to save it."
      : "No lakes here pass the filters.") + "</p>" : "";
    var route = state.nav === "saved" && state.favourites.size
      ? '<button type="button" class="btn" data-route>Plan a route through saved lakes ↗</button>' : "";
    if ($("list-title")) $("list-title").textContent = r.title;
    if ($("origin-chip")) $("origin-chip").innerHTML = originChip();
    if ($("side-list")) $("side-list").innerHTML = zonesHtml() + route + rows + empty + NOTE;
    var best = $("best");
    if (best) {
      var expanded = best.classList.contains("expanded");
      var shown = expanded ? r.list : r.list.slice(0, 3);
      best.innerHTML = '<div class="best-head"><h2>' + esc(r.title) + "</h2>" + originChip()
        + (r.list.length > 3 ? '<button type="button" class="chipbtn" data-expand>' + (expanded ? "Fewer" : "All " + r.list.length) + "</button>" : "")
        + "</div>" + zonesHtml() + route
        // The full list on a phone gets the same "Only lakes on screen" switch as the PC column.
        + (expanded ? '<button type="button" class="chipbtn onscreen" data-onscreen aria-pressed="' + !!state.onScreen + '">Only lakes on screen</button>' : "")
        + '<div class="best-rows">' + shown.map(function (l) { return rowHtml(l, d, r.winter); }).join("") + empty + "</div>";
    }
    document.querySelectorAll("[data-nav]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.nav === state.nav));
    });
    var os = $("on-screen");
    if (os) os.setAttribute("aria-pressed", String(!!state.onScreen));
  }

  // ============================================================
  // THE LAKE PANEL
  // ============================================================

  function selectedLake() {
    return state.selectedKey ? LAKES.find(function (l) { return lakeKey(l) === state.selectedKey; }) : null;
  }

  function renderSheet() {
    var lake = selectedLake();
    var pc = isPc();
    var host = $(pc ? "side-sheet" : "sheet"), other = $(pc ? "sheet" : "side-sheet");
    if (other) { other.hidden = true; other.innerHTML = ""; }
    document.body.classList.toggle("lake-open", !!lake);
    if (!host) return;
    if (!lake) { host.hidden = true; host.innerHTML = ""; return; }
    var scroll = host.scrollTop;
    var refocus = focusKey(host);
    host.innerHTML = LakeSheet.html(lake);
    host.hidden = false;
    LakeSheet.wire(host, lake);
    host.scrollTop = scroll;
    if (refocus) {
      var el = host.querySelector(refocus);
      if (el) el.focus({ preventScroll: true });
    }
  }

  /* A selector for the focused control in the panel, so a redraw can give the
   * focus back to the same control instead of dropping it to the page. */
  var FOCUS_ATTRS = ["data-fxtab", "data-fxspan", "data-fxview", "data-fav", "data-close-lake", "data-photos", "data-lakelink"];
  function focusKey(host) {
    var a = document.activeElement;
    if (!a || !host.contains(a)) return null;
    if (a.tagName === "SUMMARY" && a.parentNode.dataset.sec) return 'details[data-sec="' + a.parentNode.dataset.sec + '"] > summary';
    for (var i = 0; i < FOCUS_ATTRS.length; i++) {
      if (a.hasAttribute(FOCUS_ATTRS[i])) return "[" + FOCUS_ATTRS[i] + '="' + a.getAttribute(FOCUS_ATTRS[i]) + '"]';
    }
    return null;
  }

  function openLake(key, opts) {
    var lake = LAKES.find(function (l) { return lakeKey(l) === key; });
    if (!lake) return;
    var changed = state.selectedKey !== key;
    state.selectedKey = key;
    state.focusedLakeAts = key;
    if (changed) state.sections = null;
    var from = document.activeElement;
    if (from && from !== document.body && !from.closest(".sheet")) opener = from;
    closeSearch();
    if (typeof updateChartScopeUI === "function") updateChartScopeUI();
    if (lake.lat != null && map && !(opts && opts.noPan)) {
      map.setView([lake.lat, lake.lon], Math.max(map.getZoom(), 10));
    }
    renderSheet();
    var host = $(isPc() ? "side-sheet" : "sheet");
    if (host && changed) host.scrollTop = 0;
    renderPins();
    renderChart();
    writeUrl();
    var title = $("sheet-title");
    if (title && !(opts && opts.noFocus)) { title.setAttribute("tabindex", "-1"); title.focus({ preventScroll: true }); }
    // A lake with no saved forecast gets one now, so its panel fills in.
    if (lake.lat != null && Weather.peek(lake.lat, lake.lon).source === "none") {
      Weather.load(lake.lat, lake.lon).then(function () { refresh(); });
    }
  }

  var opener = null;
  function closeLake() {
    var key = state.selectedKey;
    state.selectedKey = null;
    state.focusedLakeAts = null;
    if (typeof updateChartScopeUI === "function") updateChartScopeUI();
    renderSheet();
    renderPins();
    renderChart();
    writeUrl();
    // Focus goes back to what opened the lake, or its row if the list was redrawn.
    var back = opener && document.contains(opener) ? opener
      : key ? document.querySelector('[data-lake="' + key + '"]') : null;
    opener = null;
    if (back && back.focus) back.focus({ preventScroll: true });
  }

  // ============================================================
  // SEARCH: TOWNS AND LAKES
  // ============================================================

  function loadTowns() {
    if (TOWNS) return Promise.resolve(TOWNS);
    if (townsLoading) return townsLoading;
    townsLoading = fetch("data/towns_ab.json").then(function (r) { return r.ok ? r.json() : []; })
      .catch(function () { return []; })
      .then(function (list) { TOWNS = Array.isArray(list) ? list : []; return TOWNS; });
    return townsLoading;
  }

  function nearestLakeTo(lat, lon) {
    var best = null, km = Infinity;
    mappableLakes().forEach(function (l) {
      var k = haversineKm(lat, lon, l.lat, l.lon);
      if (k < km) { km = k; best = l; }
    });
    return best ? { lake: best, km: km } : null;
  }

  var geoTimer = null, geoSeq = 0, active = -1;

  function closeSearch() {
    var res = $("search-results");
    if (res) res.innerHTML = "";
    var input = $("search");
    if (input) { input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); }
    active = -1;
  }

  function placeRow(p, i) {
    var near = nearestLakeTo(p.lat, p.lon);
    return '<li role="option" id="sr-' + i + '" class="row place" data-place="' + i + '"' + (i === active ? ' aria-selected="true"' : "") + ">"
      + '<span><span class="nm">' + esc(p.name) + "</span><br><span class=\"sub\">"
      + esc(p.sub || "Place") + (near ? " · nearest lake: " + esc(near.lake.name) + ", " + Math.round(near.km) + " km" : "")
      + "</span></span><span class=\"sc\"></span><span class=\"dayout calm\">Show lakes</span></li>";
  }

  function lakeRow(l, i) {
    var winter = winterOn();
    var f = Forecast.forLake(l);
    var s = f ? Forecast.rankable(f, state.day) : null;
    var pill = dayOutPill(l, state.day, winter);
    return '<li role="option" id="sr-' + i + '" class="row" data-key="' + esc(lakeKey(l)) + '"' + (i === active ? ' aria-selected="true"' : "") + ">"
      + '<span><span class="nm">' + esc(l.name) + '</span><br><span class="sub">'
      + (Number.isFinite(l.distanceKm) ? Math.round(l.distanceKm) + " km from " + esc(originPoint().name) : "no position")
      + "</span></span>"
      + '<span class="sc" title="Bite score">' + (winter || (f && f.iced) ? "ice" : s === null ? "—" : pct(s)) + "</span>"
      + '<span class="dayout ' + pill[0] + '">' + esc(pill[1]) + "</span></li>";
  }

  var lastPlaces = [], lastLakes = [];

  function drawResults(q, places, online) {
    var res = $("search-results");
    var lakes = LAKES.filter(function (l) { return l.name.toLowerCase().indexOf(q) >= 0; })
      .sort(function (a, b) {
        var sa = a.name.toLowerCase().indexOf(q) === 0 ? 0 : 1, sb = b.name.toLowerCase().indexOf(q) === 0 ? 0 : 1;
        return sa - sb || a.distanceKm - b.distanceKm;
      }).slice(0, 8);
    lastPlaces = places.slice(0, 6);
    lastLakes = lakes;
    var i = 0;
    var html = "";
    if (lastPlaces.length) html += '<li class="note" role="presentation">Places</li>' + lastPlaces.map(function (p) { return placeRow(p, i++); }).join("");
    if (lastLakes.length) html += '<li class="note" role="presentation">Lakes</li>' + lastLakes.map(function (l) { return lakeRow(l, i++); }).join("");
    if (!html) html = '<li class="note" role="presentation">No place or lake matches. Try part of a town or lake name.</li>';
    if (!online) html += '<li class="note" role="presentation">No signal: town search uses the saved Alberta town list.</li>';
    html += '<li class="note credit" role="presentation">Places: Natural Resources Canada, Canadian Geographical Names. Contains information licensed under the Open Government Licence – Canada.'
      + (online ? " More places from Open-Meteo geocoding (GeoNames, CC BY 4.0)." : "") + "</li>";
    res.innerHTML = html;
    $("search").setAttribute("aria-expanded", "true");
  }

  function search() {
    var input = $("search");
    var q = input.value.trim().toLowerCase();
    if (q.length < 2) { closeSearch(); return; }
    var mine = ++geoSeq;
    loadTowns().then(function (towns) {
      if (mine !== geoSeq) return;
      var local = towns.filter(function (t) { return String(t[0]).toLowerCase().indexOf(q) >= 0; })
        .sort(function (a, b) {
          var sa = String(a[0]).toLowerCase().indexOf(q) === 0 ? 0 : 1, sb = String(b[0]).toLowerCase().indexOf(q) === 0 ? 0 : 1;
          return sa - sb || String(a[0]).localeCompare(String(b[0]));
        })
        .slice(0, 6)
        .map(function (t) { return { name: t[0], lat: t[1], lon: t[2], sub: (t[3] || "Place") + ", Alberta" }; });
      drawResults(q, local, navigator.onLine);
      clearTimeout(geoTimer);
      if (!navigator.onLine || q.length < 3) return;
      geoTimer = setTimeout(function () {
        fetch(GEO + "?name=" + encodeURIComponent(q) + "&count=10&language=en&format=json&countryCode=CA")
          .then(function (r) { return r.ok ? r.json() : { results: [] }; })
          .then(function (json) {
            if (mine !== geoSeq) return;
            var seen = {};
            local.forEach(function (p) { seen[p.name.toLowerCase()] = true; });
            var o = originPoint();
            // Alberta first, then the rest of Canada by distance.
            var more = (json.results || []).filter(function (p) {
              return p.country_code === "CA" && !seen[String(p.name).toLowerCase()];
            }).map(function (p) {
              return { name: p.name, lat: p.latitude, lon: p.longitude, ab: p.admin1 === "Alberta" ? 0 : 1,
                       km: haversineKm(o.lat, o.lon, p.latitude, p.longitude),
                       sub: [p.admin1, "Canada"].filter(Boolean).join(", ") };
            }).sort(function (a, b) { return a.ab - b.ab || a.km - b.km; });
            drawResults(q, local.concat(more), true);
          })
          .catch(function () { /* the saved list is already shown */ });
      }, 350);
    });
  }

  function pickResult(li) {
    if (!li) return;
    if (li.dataset.key) { $("search").value = ""; closeSearch(); openLake(li.dataset.key); return; }
    var p = lastPlaces[Number(li.dataset.place)];
    if (!p) return;
    $("search").value = "";
    closeSearch();
    state.nav = null;
    state.selectedKey = null;
    state.focusedLakeAts = null;
    if (typeof updateChartScopeUI === "function") updateChartScopeUI();
    setOrigin({ name: p.name, lat: p.lat, lon: p.lon });
    if (map) map.setView([p.lat, p.lon], 9);
    renderSheet();
    render();
    writeUrl();
  }

  function buildSearch() {
    var input = $("search"), res = $("search-results");
    input.addEventListener("focus", loadTowns);
    input.addEventListener("input", function () { active = -1; search(); });
    input.addEventListener("keydown", function (e) {
      var items = Array.prototype.slice.call(res.querySelectorAll("li[data-key],li[data-place]"));
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!items.length) return;
        active = (active + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items.forEach(function (li, i) { li.setAttribute("aria-selected", String(i === active)); });
        input.setAttribute("aria-activedescendant", items[active].id);
      } else if (e.key === "Enter") {
        e.preventDefault();
        pickResult(items[active >= 0 ? active : 0]);
      } else if (e.key === "Escape") closeSearch();
    });
    res.addEventListener("click", function (e) { pickResult(e.target.closest("li[data-key],li[data-place]")); });
    document.addEventListener("click", function (e) { if (!e.target.closest(".search")) closeSearch(); });
  }

  // ============================================================
  // MESSAGES OVER THE MAP
  // ============================================================

  function showState(title, text, button, onButton) {
    var host = $("state");
    host.innerHTML = '<div class="card" role="dialog" aria-modal="false" aria-labelledby="state-h"><h3 id="state-h">' + esc(title) + "</h3>"
      + text + (button ? '<button type="button" data-state-ok>' + esc(button) + "</button>" : "") + "</div>";
    host.hidden = false;
    var ok = host.querySelector("[data-state-ok]");
    if (ok) {
      ok.addEventListener("click", function () { hideState(); if (onButton) onButton(); });
      ok.focus();
    }
  }

  function hideState() { var host = $("state"); host.hidden = true; host.innerHTML = ""; }

  function firstVisit() {
    var seen = false;
    try { seen = !!localStorage.getItem(STORE_VISITED); } catch (e) { seen = true; }
    if (seen) return;
    showState("Find a lake in 3 taps",
      "<ol><li>Pick a day on the week bar.</li><li>The brightest pins are the best lakes that day.</li>"
      + "<li>Tap a pin for its forecast and rules.</li></ol>"
      + "<p><b>Install it:</b> on an iPhone, tap Share, then Add to Home Screen. On Android or a PC, open the browser menu, then Install app. "
      + "It then works with no signal, with the forecast you saved last.</p>",
      "Start", function () { try { localStorage.setItem(STORE_VISITED, "1"); } catch (e) { /* private mode */ } });
  }

  /* Once per visit: opened with no signal, or the signal went while open. */
  var offlineShown = false;
  function offlineNotice(summary) {
    if (offlineShown) return;
    offlineShown = true;
    var age = null;
    var f = refForecast();
    if (f && f.fetchedAt) age = new Date(f.fetchedAt);
    showState("No signal",
      "<p>" + (age ? "Showing the forecast saved at " + LakeSheet.clock(age, f.offset) + " (" + esc(Weather.ageText(f.fetchedAt)) + ")."
        : "No forecast is saved on this device yet, so scores use the sun and moon only.")
      + " Scores update when you are back online.</p><p>Town search uses the saved Alberta town list.</p>", "OK");
  }

  function emptyCheck() {
    if (mappableLakes().length || state.view !== "map") {
      // Lakes are back: take down the card if it is the one this check put up.
      var h = $("state-h");
      if (h && h.textContent === "No lakes in range") hideState();
      return;
    }
    var wider = state.maxDistanceKm < 1000 ? Math.min(1000, Math.max(100, state.maxDistanceKm * 2)) : null;
    showState("No lakes in range",
      "<p>" + (wider ? "No lakes within " + state.maxDistanceKm + " km pass the filters." : "No lakes pass the filters.")
      + " Widen the distance or turn off a filter.</p>",
      wider ? "Widen to " + wider + " km" : "Open filters",
      function () {
        if (wider) {
          state.maxDistanceKm = wider;
          $("dist-slider").value = wider;
          updateDistanceLabel();
          onFilterChange();
        } else openFilters();
      });
  }

  function progressHtml() {
    var host = $("fx-progress");
    if (!host) return;
    if (!fx.loading) { host.hidden = true; return; }
    host.hidden = false;
    host.textContent = "Getting the forecast for " + mappableLakes().length + " lakes · " + fx.done + " of " + fx.of
      + ". Saved forecasts show first.";
  }

  // ============================================================
  // GETTING EVERY LAKE'S FORECAST
  // ============================================================

  function fetchAll(force) {
    var lakes = LAKES.filter(function (l) { return l.lat != null && l.lon != null; });
    fx.loading = true; fx.done = 0; fx.of = 0;
    progressHtml();
    return Weather.loadAll(lakes, {
      force: force,
      onProgress: function (p) { fx.done = p.done; fx.of = p.of; progressHtml(); },
    }).then(function (summary) {
      fx.loading = false;
      fx.lastSummary = summary;
      progressHtml();
      if (typeof updateDataQualitySummary === "function") updateDataQualitySummary();
      Forecast.clear();
      refresh();
      if (!navigator.onLine) offlineNotice(summary);
      return summary;
    });
  }

  // ============================================================
  // RENDER
  // ============================================================

  function render() {
    drawWeek();
    drawLegend();
    drawLists();
    renderSheet();
  }

  /** Re-score whatever changed, then draw. Cheap when nothing did. */
  var refreshTimer = null;
  function refresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(function () {
      Forecast.computeAll(mappableLakes(), function () { render(); renderPins(); });
      render();
    }, 30);
  }

  function openFilters() {
    var app = $("app");
    if (matchMedia("(max-width: 1023px)").matches) app.classList.add("menu-open");
    else setSidebarHidden(false);
  }

  function nav(which) {
    if (which === "clear") {
      state.nav = null;
      state.area = null;
      state.onScreen = false;
      state.selectedKey = null;
      state.focusedLakeAts = null;
      if (state.origin) { setOrigin(null); }
      renderPins();
      render();
      writeUrl();
      return;
    }
    if (which === "near") {
      state.nav = state.nav === "near" ? null : "near";
      // Near me off: the list goes back to Best near you, not lakes near you.
      if (state.nav !== "near" && state.origin && state.origin.kind === "me") setOrigin(null);
      if (state.nav === "near" && navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function (pos) {
          setOrigin({ name: "you", lat: pos.coords.latitude, lon: pos.coords.longitude, kind: "me" });
          render();
        }, function () { render(); }, { timeout: 10000, maximumAge: 300000 });
      }
    } else {
      state.nav = state.nav === which ? null : which;
    }
    state.selectedKey = null;
    state.focusedLakeAts = null;
    if (typeof updateChartScopeUI === "function") updateChartScopeUI();
    renderSheet();
    render();
    writeUrl();
  }

  function init() {
    buildSearch();
    $("week").addEventListener("click", function (e) {
      var b = e.target.closest("[data-day]");
      if (!b) return;
      state.day = Number(b.dataset.day);
      if (state.colorMode !== "bite" && state.colorMode !== "best") setColorMode("bite");
      renderPins();
      render();
      writeUrl();
    });
    document.addEventListener("click", function (e) {
      var row = e.target.closest("[data-lake]");
      if (row && (row.closest("#best") || row.closest("#side-list"))) { openLake(row.dataset.lake); return; }
      var n = e.target.closest("[data-nav]");
      if (n) { nav(n.dataset.nav); return; }
      var z = e.target.closest("[data-zone]");
      if (z) { state.area = z.dataset.zone; render(); return; }
      if (e.target.closest("[data-clear-origin]")) { setOrigin(null); render(); return; }
      if (e.target.closest("[data-expand]")) { $("best").classList.toggle("expanded"); drawLists(); return; }
      if (e.target.closest("[data-onscreen]")) { state.onScreen = !state.onScreen; render(); return; }
      if (e.target.closest("[data-route]")) { var url = favouriteRouteUrl(); if (url) window.open(url, "_blank", "noopener"); }
    });
    $("on-screen").addEventListener("click", function () { state.onScreen = !state.onScreen; render(); });
    $("learn-btn").addEventListener("click", function () {
      if (window.ReadingRoom) ReadingRoom.open();
      else showState("Learn", "<p>The guides are not saved on this device yet. They open when you are back online.</p>", "OK");
    });
    $("filters-btn").addEventListener("click", function () {
      var app = $("app");
      if (matchMedia("(max-width: 1023px)").matches) app.classList.toggle("menu-open");
      else setSidebarHidden(!app.classList.contains("sidebar-hidden"));
    });
    if (map) {
      map.on("moveend", function () { if (state.onScreen || winterOn() !== lastWinter) { lastWinter = winterOn(); render(); renderPins(); } else drawWeek(); });
    }
    var mq = matchMedia("(min-width: 1024px)");
    var onMq = function () { renderSheet(); if (map) setTimeout(function () { map.invalidateSize(); }, 60); };
    if (mq.addEventListener) mq.addEventListener("change", onMq); else if (mq.addListener) mq.addListener(onMq);
    // Q15: on a phone the header also holds Filters, Charts and Learn, so the long hint was cut off.
    var phone = matchMedia("(max-width: 767px)");
    var onPhone = function () {
      $("search").placeholder = phone.matches ? "Search a lake or a town" : "Search a lake or a town, e.g. Innisfail";
    };
    onPhone();
    if (phone.addEventListener) phone.addEventListener("change", onPhone); else if (phone.addListener) phone.addListener(onPhone);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && state.selectedKey && !document.querySelector("#reading-room:not([hidden])")) closeLake();
    });
    addEventListener("online", function () { fetchAll(false); });
    addEventListener("offline", function () { offlineNotice(); });

    Weather.restore().then(function () {
      Forecast.clear();
      refresh();
      fetchAll(false);
    });
    render();
    firstVisit();
    emptyCheck();
  }
  var lastWinter = false;

  window.DayUI = {
    init: init,
    render: render,
    refresh: refresh,
    renderSheet: renderSheet,
    openLake: openLake,
    closeLake: closeLake,
    originPoint: originPoint,
    setOrigin: setOrigin,
    winterOn: winterOn,
    fetchAll: fetchAll,
    emptyCheck: emptyCheck,
    showState: showState,
    lastSummary: function () { return fx.lastSummary; },
    _internal: { ranked: ranked, rowHtml: rowHtml, dayOutPill: dayOutPill, pool: pool },
  };
})();
