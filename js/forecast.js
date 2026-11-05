/* Seven days for every lake: the best Bite of each day, and whether the day is
 * fit to be out on the water.
 *
 * The conditions panel scores one lake in detail. The week bar, the gold pins
 * and "Best near you" need the same answer for every lake at once, so this
 * scores each lake's day with the same engine — ConditionsUI's scoreAt, which
 * is Conditions.scoreSlot with the lake's own astronomy, water and depth — and
 * keeps only the summary. Anything that drifts between the panel and the pins
 * would be a bug in both, which is why nothing here scores on its own.
 *
 * Hourly slots, from half an hour before civil dawn to half an hour after
 * civil dusk. The night is left out: the panel's own grid already shows it,
 * and a lake's "best day" is a day you can see the water.
 */
(function () {
  "use strict";

  var HOUR = 3600000;
  var cache = {};

  function num(v) { return typeof v === "number" && isFinite(v) ? v : null; }

  /** The lake's own midnights, from the weather response; device midnights
   *  when there is no weather. Seven of them, today first. */
  function dayStarts(data) {
    var out = [], i;
    if (data && data.dailyT && data.dailyT.length) {
      var nowSec = Date.now() / 1000, today = -1;
      for (i = 0; i < data.dailyT.length; i++) if (data.dailyT[i] <= nowSec) today = i;
      if (today >= 0) {
        for (i = today; i < data.dailyT.length && out.length < 7; i++) out.push(new Date(data.dailyT[i] * 1000));
      }
    }
    if (!out.length) {
      var d0 = new Date();
      d0.setHours(0, 0, 0, 0);
      out.push(d0);
    }
    while (out.length < 7) out.push(new Date(out[out.length - 1].getTime() + 86400000));
    return out;
  }

  /** The seven full days before today, for the ice guard — as the panel does. */
  function pastWeek(data) {
    if (!data || !data.dailyT) return [];
    var nowSec = Date.now() / 1000, todayT = null;
    data.dailyT.forEach(function (t) { if (t <= nowSec) todayT = t; });
    return todayT === null ? [] : Weather.dailyMeansUpTo(data, new Date((todayT - 1) * 1000));
  }

  function seasonText(lake) {
    var reg = typeof regulationFor === "function" ? regulationFor(lake) : null;
    return reg && reg.season && reg.season.text;
  }

  /* Build 4 (decision 5A): when the ice estimate (the same one Lake info shows)
   * puts ice cover inside the forecast, the days from then on get no open-water
   * score. Only a date worked out from this forecast counts: the "usual dates"
   * fallback is a calendar average, and it would blank warm weeks too. */
  function iceWindow(lake, wx, iced) {
    if (!wx.data || typeof Estimates === "undefined" || iced) return null;
    var depth = (typeof depthFor === "function" ? depthFor(lake) : null) || {};
    var elev = typeof elevationFor === "function" ? elevationFor(lake) : null;
    var e = Estimates.ice({
      dailyT: wx.data.dailyT || [], dailyMeanC: wx.data.dailyMeanC || [],
      airOffsetC: Conditions.heightOffsetC(wx.data.elevM, elev), lat: lake.lat, elevM: elev, cellElevM: wx.data.elevM,
      maxDepthM: depth.max_depth_m, iced: false, now: new Date(), offset: wx.data.offset,
    });
    var on = null, off = null;
    // The calendar date alone does not remove a score; it adds a warning line.
    var usual = e.iceOn && e.iceOn.basis === "usual dates" && e.iceOn.date.getTime() <= Date.now() + 7 * 24 * HOUR
      ? e.iceOn.date : null;
    if (e.state === "ice") on = new Date(0);
    else if (e.iceOn && e.iceOn.basis === "forecast") on = e.iceOn.date;
    if (e.iceOff && e.iceOff.basis === "forecast") off = e.iceOff.date;
    if (!on) return usual ? { on: null, usual: usual } : null;
    return { on: on, off: off && off > on ? off : null };
  }

  function formingOn(w, start) {
    if (!w || !w.on) return false;
    var end = start.getTime() + 24 * HOUR;
    return end > w.on.getTime() && !(w.off && start.getTime() >= w.off.getTime());
  }

  function summarise(lake) {
    var CUI = ConditionsUI._internal;
    var place = { lat: lake.lat, lon: lake.lon, name: lake.name, lake: lake,
                  species: filteredDominantOrder(lake) };
    var wx = Weather.peek(lake.lat, lake.lon);
    var water = CUI.waterFor(place, wx);
    var iced = !!(wx.data && Conditions.iceLikely(pastWeek(wx.data)));
    var season = seasonText(lake);
    var starts = dayStarts(wx.data);
    var freeze = iceWindow(lake, wx, iced);
    var days = starts.map(function (start) {
      var astro = CUI.astroFor(place, CUI.startOfDay(new Date(start.getTime() + 12 * HOUR)));
      var sun = astro.sun || {};
      var noon = sun.solarNoon || new Date(start.getTime() + 13 * HOUR);
      var from = sun.civilDawn ? sun.civilDawn.getTime() - HOUR / 2 : noon.getTime() - 9 * HOUR;
      var to = sun.civilDusk ? sun.civilDusk.getTime() + HOUR / 2 : noon.getTime() + 9 * HOUR;
      var rise = sun.sunrise ? sun.sunrise.getTime() : noon.getTime() - 6 * HOUR;
      var set = sun.sunset ? sun.sunset.getTime() : noon.getTime() + 6 * HOUR;

      var best = null, bestWhen = null, winter = null, winterWhen = null;
      var wind = [], gustMax = null, rain = 0, rainSeen = false, chanceMax = null;
      var airMax = null, airMin = null, chillMin = null, hours = [];
      // Today's best time is never one already gone; the rest of the day still counts.
      var nowMs = Date.now();
      for (var t = Math.ceil(from / HOUR) * HOUR; t <= to; t += HOUR) {
        var when = new Date(t);
        var r = CUI.scoreAt(place, when, wx, water);
        var later = t + HOUR > nowMs || to < nowMs;
        if (later && (!best || r.scoreRaw > best.scoreRaw)) { best = r; bestWhen = when; }
        // Build 2 (C17): the winter score of the same slot, for frozen lakes.
        var ws = Conditions.scoreWinter(r);
        if (later && ws.score !== null && (!winter || ws.scoreRaw > winter.scoreRaw)) { winter = ws; winterWhen = when; }
        var w = wx.data ? Weather.at(wx.data, when) : null;
        var sunUp = t >= rise && t <= set;
        if (w) hours.push({ when: when, cloudPct: w.cloudCoverPct, sunUp: sunUp });
        if (!w || !sunUp) continue;
        if (num(w.windKph) !== null) wind.push(w.windKph);
        if (num(w.gustKph) !== null) gustMax = gustMax === null ? w.gustKph : Math.max(gustMax, w.gustKph);
        if (num(w.precipMm) !== null) { rain += w.precipMm; rainSeen = true; }
        if (num(w.precipChancePct) !== null) chanceMax = chanceMax === null ? w.precipChancePct : Math.max(chanceMax, w.precipChancePct);
        if (num(w.airTempC) !== null) {
          airMax = airMax === null ? w.airTempC : Math.max(airMax, w.airTempC);
          airMin = airMin === null ? w.airTempC : Math.min(airMin, w.airTempC);
          var c = Conditions.windChill(w.airTempC, w.windKph);
          chillMin = chillMin === null ? c : Math.min(chillMin, c);
        }
      }
      var windMean = wind.length ? wind.reduce(function (a, b) { return a + b; }, 0) / wind.length : null;
      var out = wx.data ? Conditions.dayOut({
        windKph: windMean, gustKph: gustMax, precipMm: rainSeen ? rain : null,
        precipChancePct: chanceMax, airTempC: airMax, areaHa: lake.surface_area_ha,
      }) : null;
      var closed = season ? Conditions.seasonOpenOn(season, new Date(start.getTime() + 12 * HOUR)) === false : false;
      var w3 = best && best.factors && best.factors.pressure ? best.factors.pressure.value : null;
      return {
        start: start,
        bite: best ? best.score : null,
        band: best ? best.band : null,
        best: best,
        bestWhen: bestWhen,
        confidence: best ? best.confidence : "Astronomy only",
        dayOut: out && out.score !== null ? out.score : null,
        dayOutDetail: out,
        gustMax: gustMax, windMean: windMean,
        precipMm: rainSeen ? rain : null, precipChancePct: chanceMax,
        airMax: airMax, airMin: airMin, chillMin: chillMin,
        winter: winter ? winter.score : null,
        winterDetail: winter,
        winterWhen: winterWhen,
        comfort: Conditions.comfortNote(chillMin),
        pressureTrend3h: w3,
        clearing: Conditions.clearingHint(hours),
        closed: closed,
        iced: iced,
        iceForming: !iced && formingOn(freeze, start),
      };
    });
    var pick = Conditions.bestDay(days.map(function (d) {
      return { bite: d.closed || d.iceForming || d.confidence === "Astronomy only" ? null : d.bite,
               dayOut: d.dayOut, gustMax: d.gustMax, iced: d.iced || d.iceForming };
    }));
    return { key: lakeKey(lake), days: days, bestDay: pick, iced: iced, iceOn: freeze ? freeze.on : null, iceUsual: freeze ? freeze.usual || null : null,
             hasWeather: !!wx.data, fetchedAt: wx.fetchedAt, offset: wx.data ? wx.data.offset : null };
  }

  function cacheKey(lake) {
    var wx = Weather.peek(lake.lat, lake.lon);
    var o = state.conditions.waterOverrides[lakeKey(lake)];
    return [wx.fetchedAt || 0, filteredDominantOrder(lake).join(""), o ? o.tempC : "",
            new Date().toDateString()].join("|");
  }

  /* Build 5: a river stretch has a forecast spot about every 25 km. It is
   * scored at each one with the same engine, and the spot with the best day of
   * the week stands for the stretch (the panel names it). */
  function spotsOf(lake) {
    return lake && lake.river && Array.isArray(lake.spots) && lake.spots.length > 1 ? lake.spots : null;
  }
  function riverKey(lake) {
    return lake.spots.map(function (p) { var wx = Weather.peek(p[0], p[1]); return wx.fetchedAt || 0; }).join(",")
      + "|" + new Date().toDateString();
  }
  function summariseRiver(lake) {
    var best = null;
    lake.spots.forEach(function (p, i) {
      // Each spot has its own height ("<stretch id>#<n>" in lake_elevation.json).
      var v = summarise(Object.assign({}, lake, { lat: p[0], lon: p[1], _spotKey: lakeKey(lake) + "#" + i }));
      v.spot = i;
      var b = v.bestDay >= 0 && v.days[v.bestDay].bite != null ? v.days[v.bestDay].bite : -1;
      var w = v.hasWeather ? 1 : 0;
      if (!best || w > best.w || (w === best.w && b > best.b)) best = { v: v, b: b, w: w };
    });
    best.v.spots = lake.spots.length;
    return best.v;
  }

  /** Seven days for one lake, computed once per forecast and filter. */
  function forLake(lake) {
    if (!lake || lake.lat == null || lake.lon == null) return null;
    var k = lakeKey(lake), river = spotsOf(lake), ck = river ? riverKey(lake) : cacheKey(lake);
    var hit = cache[k];
    if (hit && hit.ck === ck) return hit.value;
    var value = river ? summariseRiver(lake) : summarise(lake);
    cache[k] = { ck: ck, value: value };
    return value;
  }

  /** Whether a lake's summary is already computed for the current inputs. */
  function ready(lake) {
    var hit = cache[lakeKey(lake)];
    return !!(hit && hit.ck === (spotsOf(lake) ? riverKey(lake) : cacheKey(lake)));
  }

  /** Score many lakes in small slices so the page keeps answering taps.
   *  Calls onDone once every lake is in. */
  var job = 0;
  function computeAll(lakes, onDone) {
    var mine = ++job;
    var list = (lakes || []).filter(function (l) { return l.lat != null && l.lon != null && !ready(l); });
    var i = 0;
    (function slice() {
      if (mine !== job) return;
      var until = Date.now() + 30;
      while (i < list.length && Date.now() < until) forLake(list[i++]);
      if (i < list.length) setTimeout(slice, 0);
      else if (onDone) onDone();
    })();
  }

  function clear() { cache = {}; }

  /* The Bite score of a lake on a day, or null when it should not be ranked:
   * closed, frozen or scored on astronomy alone. */
  function rankable(f, d) {
    if (!f) return null;
    var day = f.days[d];
    if (!day || day.closed || day.iceForming || f.iced || day.confidence === "Astronomy only") return null;
    return day.bite;
  }

  window.Forecast = {
    forLake: forLake,
    ready: ready,
    computeAll: computeAll,
    clear: clear,
    rankable: rankable,
    _internal: { dayStarts: dayStarts, pastWeek: pastWeek, iceWindow: iceWindow, formingOn: formingOn },
  };
})();
