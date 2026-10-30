/* One lake, all of it, in one panel: on a phone it slides up from the bottom,
 * on a PC it fills the right-hand column.
 *
 * It replaces three things that used to float over the map at once — the pin
 * popup, the conditions panel and the photographs panel — which fought for the
 * same corner and could not all be read together. The order is the order of
 * the decision: should I go and when (the banner and why), what will it be like
 * (the forecast), and then what is there, what may I keep, how do I get there.
 *
 * Everything the old popup said is still here, in fold-open sections, built by
 * the same functions in index.html. Nothing in this file scores anything: the
 * numbers come from Forecast, which uses the conditions engine.
 */
(function () {
  "use strict";

  var DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var BAND_WORD = { Prime: "Best", Good: "Good", Fair: "Fair", Poor: "Poor" };
  var TROUT = ["RNTR", "BKTR", "BNTR", "TGTR", "CTTR", "WSCT", "BLTR", "LKTR", "GLTR", "SPLK"];
  var RULES_URL = "https://albertaregulations.ca/fishingregs/";
  var LICENCE_URL = "https://mywildalberta.ca/buy-licences/";

  function num(v) { return typeof v === "number" && isFinite(v) ? v : null; }
  function pct(s) { return num(s) === null ? null : Math.round(s * 100); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }

  // ============================================================
  // DAYS AND CLOCKS AT THE LAKE
  // ============================================================

  /** Short day name of a lake day, in the lake's own calendar. */
  function dayName(f, d) {
    var day = f && f.days[d];
    if (!day) return "";
    var noon = new Date(day.start.getTime() + 12 * 3600000);
    return f.offset == null ? DAY_NAMES[noon.getDay()]
      : DAY_NAMES[new Date(noon.getTime() + f.offset * 1000).getUTCDay()];
  }

  function clock(date, offset) {
    if (!date) return "";
    if (offset == null) return pad(date.getHours()) + ":" + pad(date.getMinutes());
    var s = new Date(date.getTime() + offset * 1000);
    return pad(s.getUTCHours()) + ":" + pad(s.getUTCMinutes());
  }

  function bandWord(score) {
    return num(score) === null ? "" : BAND_WORD[Conditions.bandName(score)];
  }

  // ============================================================
  // TAGS FROM THE REGULATIONS AND THE ATLAS
  // ============================================================

  /** Trout a person may keep here, or null when the guide does not say. */
  function troutLimit(lake) {
    var reg = regulationFor(lake);
    if (!reg) return null;
    if (reg.trout_total && num(reg.trout_total.count) !== null) return reg.trout_total.count;
    if (reg.limits && reg.limits.Trout) {
      var m = /^(\d+)/.exec(String(reg.limits.Trout));
      return m ? Number(m[1]) : null;
    }
    if (reg.species) {
      var total = null;
      TROUT.forEach(function (c) {
        var s = reg.species[c];
        if (s && num(s.count) !== null) total = (total || 0) + s.count;
      });
      return total;
    }
    return null;
  }

  /** The guide's own words for a trout size rule ("1 trout over 50 cm"), or
   *  null. Copied, never paraphrased: it is a legal limit. */
  function trophyRule(lake) {
    var reg = regulationFor(lake);
    if (!reg) return null;
    var hasCm = function (t) { return /\d+\s*cm/i.test(String(t || "")); };
    if (reg.trout_total && hasCm(reg.trout_total.text)) return reg.trout_total.text;
    var found = null;
    if (reg.species) {
      TROUT.forEach(function (c) {
        var s = reg.species[c];
        if (!found && s && (num(s.size_cm) !== null || hasCm(s.text))) found = fishName(c) + ": " + s.text;
      });
    }
    if (!found && reg.limits && hasCm(reg.limits.Trout)) found = reg.limits.Trout;
    return found;
  }

  /** The largest Angler's Atlas agree count: how many anglers reported their
   *  fish here. A rough sign of how often the lake is fished, and labelled so. */
  function popularity(lake) {
    var seen = (profileFor(lake) || {}).confirmed;
    if (!seen || !seen.species || !seen.species.length) return null;
    var n = 0;
    seen.species.forEach(function (s) { if (num(s.agree) !== null && s.agree > n) n = s.agree; });
    return n || null;
  }

  /** Advisories that name this lake. */
  function advisoriesFor(lake) {
    if (typeof ADVISORIES === "undefined" || !ADVISORIES || !ADVISORIES.sources) return [];
    var name = String(lake.name || "").toLowerCase();
    if (name.length < 4) return [];
    var out = [];
    Object.keys(ADVISORIES.sources).forEach(function (k) {
      var src = ADVISORIES.sources[k];
      (src.entries || []).forEach(function (text) {
        if (String(text).toLowerCase().indexOf(name) >= 0) out.push({ text: text, url: src.url });
      });
    });
    return out;
  }

  function tagsHtml(lake, winter) {
    var t = [];
    if (lakeAerated(lake)) t.push('<span class="tag aer">Aerated</span>');
    var lim = troutLimit(lake);
    if (lim !== null && lim <= 2) {
      t.push('<span class="tag low" title="Fewer fish taken, so more can grow big.">Low harvest limit: '
        + lim + " trout</span>");
    }
    var trophy = trophyRule(lake);
    if (trophy) t.push('<span class="tag trophy" title="From the ' + esc(REGULATIONS.guide_year || "")
      + ' regulations, in the guide\'s words.">Trophy size rule: ' + esc(trophy) + "</span>");
    var pop = popularity(lake);
    if (pop) t.push('<span class="tag est" title="Estimate: the largest number of anglers who reported one fish here on Angler\'s Atlas. Not a count of visits.">Popularity estimate: '
      + pop + " angler report" + (pop === 1 ? "" : "s") + "</span>");
    if (winter) {
      var kind = lakeIceKind(lake);
      if (kind) t.push('<span class="tag ice">Ice season: ' + esc(ICE_KIND_TEXT[kind]) + "</span>");
    }
    advisoriesFor(lake).forEach(function (a) {
      t.push('<a class="tag warn-tag" href="' + esc(a.url) + '" target="_blank" rel="noopener">Advisory: '
        + esc(a.text) + "</a>");
    });
    return t.length ? '<div class="tags">' + t.join("") + "</div>" : "";
  }

  // ============================================================
  // THE BANNER: WHICH DAY
  // ============================================================

  function barsHtml(f) {
    var best = f.bestDay;
    return '<div class="bars" role="img" aria-label="Bite score for 7 days: ' + esc(f.days.map(function (day, i) {
      var p = day.closed ? null : pct(day.bite);
      return dayName(f, i) + " " + (p === null ? (day.closed ? "shut" : "no score") : p);
    }).join(", ")) + '">' + f.days.map(function (day, i) {
      // A shut day has no score, the same rule as the rest of the app.
      var p = day.closed ? null : pct(day.bite);
      var gust = num(day.gustMax) !== null && day.gustMax >= Conditions.GUST_WARN_KPH;
      var cls = i === best ? "top" : gust ? "gust" : day.closed ? "shut" : "";
      var label = dayName(f, i) + ": " + (p === null ? "no score" : "Bite " + p + ", " + bandWord(day.bite))
        + (gust ? ", gusts " + Math.round(day.gustMax) + " km/h" : "") + (day.closed ? ", season shut" : "");
      return '<div class="' + cls + '" title="' + esc(label) + '">'
        + '<b>' + (p === null ? "—" : p) + "</b>"
        + '<span style="height:' + Math.max(4, (p || 0) * 0.5) + 'px"></span>'
        + dayName(f, i) + '<i>' + esc(day.closed ? "Shut" : bandWord(day.bite)) + "</i></div>";
    }).join("") + "</div>";
  }

  function bannerHtml(lake, f, d) {
    var day = f.days[d];
    if (lakeOpenNow(lake) === false && day.closed) {
      var reg = regulationFor(lake);
      return '<div class="banner shut"><div class="go">Season shut</div><div class="why">'
        + esc((reg && reg.season && reg.season.text) || "") + ". No score is shown for a shut lake.</div></div>";
    }
    if (f.iced) {
      var chill = num(day.chillMin);
      return '<div class="banner ice"><div class="go">Ice likely</div><div class="why">'
        + "Every day of the past 7 days had a mean air temperature below freezing, so the open-water Bite score is hidden. "
        + (chill === null ? "" : "Day out: " + Math.round(chill) + " °C wind chill on " + dayName(f, d) + ". ")
        + "Legal is not safe. Ice thickness is never forecast.</div></div>";
    }
    var gusty = f.days.map(function (x, i) { return [x, i]; })
      .filter(function (p) { return num(p[0].gustMax) !== null && p[0].gustMax >= Conditions.GUST_WARN_KPH; })
      .map(function (p) { return dayName(f, p[1]) + " gusts to " + Math.round(p[0].gustMax) + " km/h"; });
    var gustText = gusty.length ? " " + gusty.join(", ") + ": not a boat day." : "";
    if (f.bestDay < 0) {
      return '<div class="banner none"><div class="go">' + (f.hasWeather ? "No good day this week" : "No forecast yet") + '</div><div class="why">'
        + (f.hasWeather ? "Every day is gusty, rough on the water or shut." : "No forecast yet for this lake, so only the sun and moon are known.")
        + gustText + "</div>" + barsHtml(f) + "</div>";
    }
    var b = f.days[f.bestDay];
    return '<div class="banner"><div class="go">Go ' + dayName(f, f.bestDay) + " · " + pct(b.bite) + "</div>"
      + '<div class="why">Best bite on a day you can be out: Bite ' + bandWord(b.bite)
      + ", Day out " + bandWord(b.dayOut) + (b.bestWhen ? ", best around " + clock(b.bestWhen, f.offset) : "") + "."
      + gustText + "</div>" + barsHtml(f) + "</div>";
  }

  // ============================================================
  // WHY THIS SCORE
  // ============================================================

  var SAY_MORE = {
    light: "more cloud in the bright hours, or a better time of day",
    water: "water closer to the best temperature (estimated from the air)",
    pressure: "a better pressure trend",
    wind: "a better ripple on the water",
    precip: "less rain",
  };
  var SAY_LESS = {
    light: "brighter sun",
    water: "water further from the best temperature",
    pressure: "a worse pressure trend",
    wind: "too much or too little wind",
    precip: "more rain",
  };

  /* The nearest lake that can actually differ: one in another weather cell, or
   * one of another size. Two lakes in the same cell share every forecast number,
   * and comparing them would say nothing. */
  function neighbourFor(lake) {
    var cell = Weather.cellKey(lake.lat, lake.lon);
    var size = Conditions.sizeClass(lake.surface_area_ha).id;
    var best = null, bestKm = Infinity;
    LAKES.forEach(function (o) {
      if (o === lake || o.lat == null || o.lon == null) return;
      if (Weather.cellKey(o.lat, o.lon) === cell && Conditions.sizeClass(o.surface_area_ha).id === size) return;
      var km = haversineKm(lake.lat, lake.lon, o.lat, o.lon);
      if (km < bestKm) { bestKm = km; best = o; }
    });
    return best && bestKm <= 60 ? { lake: best, km: bestKm } : null;
  }

  function compareSentence(lake, f, d) {
    var near = neighbourFor(lake);
    if (!near) return "No lake within 60 km has a different forecast spot or size, so there is nothing useful to compare.";
    var g = Forecast.forLake(near.lake);
    var mine = f.days[d], theirs = g && g.days[d];
    if (!mine || !mine.best || !theirs || !theirs.best || g.iced || theirs.closed) {
      return "Nearest lake to compare, " + esc(near.lake.name) + ", has no score on " + dayName(f, d) + ".";
    }
    var a = Conditions.whyParts(mine.best), b = Conditions.whyParts(theirs.best);
    var diffs = a.parts.map(function (p, i) { return [p.id, p.points - b.parts[i].points]; })
      .filter(function (x) { return x[1] !== 0; })
      .sort(function (x, y) { return Math.abs(y[1]) - Math.abs(x[1]); })
      .slice(0, 2)
      .map(function (x) { return (x[1] > 0 ? SAY_MORE[x[0]] : SAY_LESS[x[0]]) + " (" + (x[1] > 0 ? "+" : "") + x[1] + ")"; });
    var mp = pct(mine.bite), tp = pct(theirs.bite);
    var word = mp > tp ? "Higher than" : mp < tp ? "Lower than" : "Same as";
    return "<b>" + word + " " + esc(near.lake.name) + " (" + tp + ", " + Math.round(near.km) + " km away):</b> "
      + (diffs.length ? diffs.join("; ") : "the parts are almost the same") + ".";
  }

  function whyHtml(lake, f, d) {
    var day = f.days[d];
    // A shut day has no score, so it has no parts either.
    if (!day || !day.best || f.iced || day.closed) return "";
    var w = Conditions.whyParts(day.best);
    var rows = w.parts.map(function (p) {
      if (!p.present) {
        return '<div class="fac absent"><span>' + esc(p.label) + '</span><span class="track"></span><b>—</b></div>';
      }
      return '<div class="fac"><span>' + esc(p.label) + '</span><span class="track"><span style="width:'
        + (p.max ? Math.min(100, Math.round(p.points / p.max * 100)) : 0) + '%"></span></span><b>' + p.points + "/" + p.max + "</b></div>";
    }).join("");
    var moon = Math.round((w.moonMult - 1) * 100);
    var out = day.dayOutDetail;
    var size = out ? out.size : Conditions.sizeClass(lake.surface_area_ha);
    var whyOpen = !!(state.sections && state.sections.why);
    return '<details class="why" data-sec="why"' + (whyOpen ? " open" : "") + "><summary>Why " + w.total + " on " + dayName(f, d) + "?</summary><div class=\"body\">"
      + '<p class="lead">These parts add up to the Bite score at the best time of the day'
      + (day.bestWhen ? " (" + clock(day.bestWhen, f.offset) + ")" : "") + ". The moon is already inside each part: "
      + (moon >= 0 ? "+" : "") + moon + "%.</p>"
      + rows
      + '<p class="lead">Day out ' + (pct(day.dayOut) === null ? "—" : pct(day.dayOut)) + ": wind plus half the gust spread, times "
      + size.factor + " for a " + esc(size.label) + (size.unknown ? " (a medium lake is used)" : "")
      + "; rain amount and chance; air temperature. Gusts are not in the Bite score.</p>"
      + '<p class="compare">' + compareSentence(lake, f, d) + "</p>"
      + "</div></details>";
  }

  function tipHtml(lake, f, d) {
    var day = f.days[d];
    if (!day || f.iced || !f.hasWeather || day.closed) return "";
    var tip = Conditions.dailyTip({
      pressureTrend3h: day.pressureTrend3h, gustMax: day.gustMax, windMean: day.windMean,
      bestTime: day.bestWhen ? clock(day.bestWhen, f.offset) : null,
    });
    var clear = day.clearing
      ? '<div class="tip clear">Sun breaking through around ' + clock(day.clearing.when, f.offset) + " " + dayName(f, d)
        + ". Anglers report a short bite when that happens. A reminder only, not in the score.</div>"
      : "";
    return (tip ? '<div class="tip">' + esc(tip) + "</div>" : "") + clear;
  }

  // ============================================================
  // FORECAST: TABS, DAYS, LINES OR GRID
  // ============================================================

  var TABS = ["Wind", "Weather", "Barometer", "Solunar"];

  function hourly(wx, from, to) {
    var out = [];
    if (!wx.data) return out;
    var t = wx.data.t;
    for (var i = 0; i < t.length; i++) {
      var ms = t[i] * 1000;
      if (ms < from || ms > to) continue;
      out.push({ t: ms, wind: num(wx.data.wind[i]), gust: num(wx.data.gust[i]), air: num(wx.data.airC[i]),
                 rain: num(wx.data.precip[i]), chance: num((wx.data.precipChance || [])[i]),
                 kpa: num(wx.data.pressure[i]) === null ? null : wx.data.pressure[i] / 10,
                 cloud: num(wx.data.cloud[i]) });
    }
    return out;
  }

  function lineSvg(f, rows, series, opts) {
    var W = 320, H = 130, L = 30, R = 8, T = 10, B = 20;
    if (!rows.length) return '<p class="dim">No forecast yet for this lake.</p>';
    var t0 = rows[0].t, t1 = rows[rows.length - 1].t || t0 + 1;
    var vals = [];
    series.forEach(function (s) { rows.forEach(function (r) { if (r[s.k] !== null) vals.push(r[s.k]); }); });
    if (opts.ref !== undefined) vals.push(opts.ref);
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (opts.zero) lo = Math.min(0, lo);
    if (hi - lo < (opts.minSpan || 1)) { var mid = (hi + lo) / 2; lo = mid - (opts.minSpan || 1) / 2; hi = mid + (opts.minSpan || 1) / 2; }
    var px = function (t) { return L + (t - t0) / (t1 - t0 || 1) * (W - L - R); };
    var py = function (v) { return T + (hi - v) / (hi - lo) * (H - T - B); };
    var paths = series.map(function (s) {
      var d = "", pen = false;
      rows.forEach(function (r) {
        if (r[s.k] === null) { pen = false; return; }
        d += (pen ? "L" : "M") + px(r.t).toFixed(1) + " " + py(r[s.k]).toFixed(1) + " ";
        pen = true;
      });
      return '<path d="' + d + '" stroke="' + s.colour + '" fill="none" stroke-width="2"' + (s.dash ? ' stroke-dasharray="3 3"' : "") + "/>";
    }).join("");
    var bars = opts.bars ? rows.map(function (r) {
      var v = r[opts.bars.k];
      if (!v) return "";
      var h = Math.min(H - T - B, v * opts.bars.scale);
      return '<rect x="' + (px(r.t) - 1).toFixed(1) + '" y="' + (H - B - h).toFixed(1) + '" width="2.5" height="' + h.toFixed(1) + '" fill="' + opts.bars.colour + '"/>';
    }).join("") : "";
    var ticks = f.days.filter(function (d) { return d.start.getTime() >= t0 && d.start.getTime() <= t1; }).map(function (d) {
      var x = px(d.start.getTime()).toFixed(1);
      var i = f.days.indexOf(d);
      return '<line x1="' + x + '" x2="' + x + '" y1="' + T + '" y2="' + (H - B) + '" stroke="#55584f" stroke-width="1"/>'
        + '<text x="' + (Number(x) + 3) + '" y="' + (H - 6) + '" font-size="9" fill="#b4ae9f">' + dayName(f, i) + "</text>";
    }).join("");
    var axis = '<text x="2" y="' + (T + 8) + '" font-size="9" fill="#b4ae9f">' + Math.round(hi * 10) / 10 + "</text>"
      + '<text x="2" y="' + (H - B) + '" font-size="9" fill="#b4ae9f">' + Math.round(lo * 10) / 10 + "</text>";
    var ref = opts.ref !== undefined
      ? '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + py(opts.ref).toFixed(1) + '" y2="' + py(opts.ref).toFixed(1) + '" stroke="#d9534f" stroke-dasharray="4 3"/>'
        + '<text x="' + (W - R - 2) + '" y="' + (py(opts.ref) - 3).toFixed(1) + '" font-size="9" fill="#f0b3ae" text-anchor="end">' + esc(opts.refLabel) + "</text>"
      : "";
    return '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(opts.label) + '">'
      + ticks + bars + ref + paths + axis + "</svg>"
      + '<div class="key">' + series.map(function (s) { return '<span style="color:' + s.colour + '">' + esc(s.name) + "</span>"; }).join(" · ")
      + (opts.bars ? ' · <span style="color:' + opts.bars.colour + '">' + esc(opts.bars.name) + "</span>" : "") + " · " + esc(opts.unit) + "</div>";
  }

  var PARTS = [["dawn", "Dawn"], ["morning", "Morning"], ["midday", "Midday"], ["evening", "Evening"], ["night", "Night"]];

  function gridTable(lake, f, wx, span, tab) {
    var CUI = ConditionsUI._internal;
    var place = { lat: lake.lat, lon: lake.lon };
    var head = "<tr><th></th>" + f.days.slice(0, span).map(function (d, i) { return "<th>" + dayName(f, i) + "</th>"; }).join("") + "</tr>";
    var body = PARTS.map(function (p) {
      return "<tr><th>" + p[1] + "</th>" + f.days.slice(0, span).map(function (d) {
        var a = CUI.astroFor(place, CUI.startOfDay(new Date(d.start.getTime() + 12 * 3600000)));
        var n = CUI.astroFor(place, CUI.startOfDay(new Date(d.start.getTime() + 36 * 3600000)));
        var win = CUI.partWindow(p[0], d.start, a.sun, n.sun);
        var rows = hourly(wx, win[0].getTime(), win[1].getTime());
        if (!rows.length) return "<td>—</td>";
        var max = function (k) { var v = null; rows.forEach(function (r) { if (r[k] !== null) v = v === null ? r[k] : Math.max(v, r[k]); }); return v; };
        var mean = function (k) { var s = 0, c = 0; rows.forEach(function (r) { if (r[k] !== null) { s += r[k]; c++; } }); return c ? s / c : null; };
        var sum = function (k) { var s = 0; rows.forEach(function (r) { if (r[k] !== null) s += r[k]; }); return s; };
        if (tab === "Wind") {
          var g = max("gust");
          return '<td class="' + (g !== null && g >= Conditions.GUST_WARN_KPH ? "hot" : "") + '">' + Math.round(mean("wind") || 0) + "<small>/" + Math.round(g || 0) + "</small></td>";
        }
        if (tab === "Weather") {
          var rain = sum("rain");
          return "<td>" + Math.round(mean("air")) + "°" + (rain >= 0.2 ? "<small> " + rain.toFixed(1) + " mm</small>" : "") + "</td>";
        }
        return "<td>" + (mean("kpa") === null ? "—" : mean("kpa").toFixed(1)) + "</td>";
      }).join("") + "</tr>";
    }).join("");
    var unit = tab === "Wind" ? "wind / gust, km/h; red cell = gusts 40 km/h or more" : tab === "Weather" ? "air °C and rain" : "kPa";
    return '<div class="gridwrap"><table class="fxgrid">' + head + body + '</table></div><div class="key">' + unit + ". Day parts follow the sun, not the clock.</div>";
  }

  function solunarRows(lake, f, span) {
    var CUI = ConditionsUI._internal;
    var place = { lat: lake.lat, lon: lake.lon };
    return '<div class="solunar">' + f.days.slice(0, span).map(function (d, i) {
      var a = CUI.astroFor(place, CUI.startOfDay(new Date(d.start.getTime() + 12 * 3600000)));
      var per = (a.periods || []).map(function (p) {
        return '<span class="per ' + p.kind + '"><b>' + (p.kind === "major" ? "Major" : "Minor") + "</b> "
          + clock(p.start, f.offset) + "–" + clock(p.end, f.offset) + "</span>";
      }).join("");
      return '<div class="srow"><span class="sday">' + dayName(f, i) + "</span><span>"
        + esc(a.moon ? a.moon.name + ", " + Math.round(a.moon.illumination * 100) + "% lit" : "") + "</span>"
        + '<span class="pers">' + (per || "no lunar period") + "</span></div>";
    }).join("") + '</div><div class="key">Solunar periods are shown for reference. The moon changes the Bite score by 5% at most.</div>';
  }

  /* Today's feeding windows, as clock times: always shown, whatever the tab. */
  function feedHtml(lake, f) {
    var CUI = ConditionsUI._internal;
    var a = CUI.astroFor({ lat: lake.lat, lon: lake.lon }, CUI.startOfDay(new Date()));
    var list = function (kind) {
      return (a.periods || []).filter(function (p) { return p.kind === kind; })
        .map(function (p) { return clock(p.start, f.offset) + "–" + clock(p.end, f.offset); }).join(" · ") || "none today";
    };
    return '<div class="feed" aria-label="Feeding windows today"><b>Major</b><span>' + list("major")
      + "</span><b>Minor</b><span>" + list("minor") + "</span><b>Moon</b><span>"
      + esc(a.moon ? a.moon.name + ", " + Math.round(a.moon.illumination * 100) + "% lit" : "—") + "</span></div>";
  }

  var BAROMETER_TEXT = '<p class="explain"><b>Reading the barometer:</b> the direction matters, not the number. '
    + "Steady or slowly rising: normal feeding. A sharp fall before a front: often a short, strong bite. "
    + "High pressure after a front, with a bright sky: fish are often slow.</p>";

  function forecastHtml(lake, f) {
    var fx = state.fx;
    var wx = Weather.peek(lake.lat, lake.lon);
    var span = fx.span;
    var from = f.days[0].start.getTime();
    var to = from + span * 86400000;
    var rows = hourly(wx, from, to);
    var body;
    if (fx.tab === "Solunar") body = solunarRows(lake, f, span);
    else if (fx.view === "Grid") body = gridTable(lake, f, wx, span, fx.tab);
    else if (fx.tab === "Wind") {
      body = lineSvg(f, rows, [{ k: "wind", name: "Wind", colour: "#a6dcb9" }, { k: "gust", name: "Gusts", colour: "#f0b3ae" }],
        { ref: Conditions.GUST_WARN_KPH, refLabel: "gust warning 40", zero: true, label: "Wind and gusts", unit: "km/h", minSpan: 10 });
    } else if (fx.tab === "Weather") {
      body = lineSvg(f, rows, [{ k: "air", name: "Air", colour: "#e8c27a" }],
        { bars: { k: "rain", scale: 12, colour: "#7fb8d8", name: "Rain mm" }, label: "Air temperature and rain", unit: "°C", minSpan: 4 });
    } else {
      body = lineSvg(f, rows, [{ k: "kpa", name: "Pressure", colour: "#c9b8f0" }],
        { label: "Barometer", unit: "kPa at sea level", minSpan: 1 });
    }
    if (fx.tab === "Barometer") body += BAROMETER_TEXT;
    if (fx.tab === "Weather" && f.hasWeather) {
      body += '<p class="dim">Rain chance: ' + f.days.slice(0, span).map(function (d, i) {
        return dayName(f, i) + " " + (num(d.precipChancePct) === null ? "—" : Math.round(d.precipChancePct) + "%");
      }).join(" · ") + "</p>";
    }
    return '<div class="tabs" role="tablist">' + TABS.map(function (t) {
      return '<button type="button" role="tab" aria-selected="' + (t === fx.tab) + '" data-fxtab="' + t + '">' + t + "</button>";
    }).join("") + "</div>"
      + '<div class="seg"><button type="button" aria-pressed="' + (span === 3) + '" data-fxspan="3">3 days</button>'
      + '<button type="button" aria-pressed="' + (span === 7) + '" data-fxspan="7">7 days</button></div>'
      + (fx.tab === "Solunar" ? "" : '<div class="seg"><button type="button" aria-pressed="' + (fx.view === "Lines") + '" data-fxview="Lines">Lines</button>'
      + '<button type="button" aria-pressed="' + (fx.view === "Grid") + '" data-fxview="Grid">Grid</button></div>')
      + '<div class="chart">' + body + "</div>"
      + feedHtml(lake, f)
      + '<div class="src">' + (wx.source === "none" ? "No forecast saved for this lake yet."
        : "Forecast " + esc(Weather.ageText(wx.fetchedAt)) + " · weather data by Open-Meteo.com (CC BY 4.0)") + "</div>";
  }

  // ============================================================
  // THE REST OF WHAT THE POPUP SAID
  // ============================================================

  function stockingHtml(lake) {
    var rows = lake.stockings.filter(stockingPasses)
      .sort(function (a, b) { return stockingSortKey(b).localeCompare(stockingSortKey(a)); });
    var last = rows[0];
    var age = last ? daysAgo(last.date) : null;
    var lastText = last
      ? fmtDate(last.date, last.date_precision) + (last.length_cm ? ", " + Number(last.length_cm).toFixed(1) + " cm" : "")
        + (age != null && age <= 365 ? " · " + age + " days ago" : "")
      : "—";
    var years = yearRuns(Array.from(new Set(rows.map(function (s) { return s.year; }))).sort(function (a, b) { return a - b; }));
    var species = filteredDominantOrder(lake).map(function (c) { return (SPECIES_META[c] || {}).short || c; }).join(", ") || "none";
    var pair = changeYearPair();
    var change = changeText(lake, pair);
    var cls = changeClassOf(lake, pair);
    var table = rows.map(function (s) {
      var color = (SPECIES_META[s.species] || {}).color || "#888";
      return "<tr>" + dateCell(s.date, s.date_precision)
        + '<td><span class="sp-tag" style="background:' + color + '">' + esc(s.species) + "</span></td>"
        + "<td>" + (esc(s.strain) || "—") + "</td>"
        + "<td>" + (s.length_cm ? Number(s.length_cm).toFixed(1) : "—") + "</td>"
        + "<td>" + (s.weight_g == null ? "—" : fmtNum(Math.round(Number(s.weight_g)))) + "</td>"
        + "<td>" + fmtNum(s.number) + "</td></tr>";
    }).join("");
    return '<dl class="kv"><dt>Species</dt><dd>' + esc(species) + "</dd>"
      + "<dt>Last stocked</dt><dd>" + esc(lastText) + "</dd>"
      + "<dt>Years</dt><dd>" + esc(years || "—") + "</dd>"
      + "<dt>Fish shown</dt><dd>" + fmtNum(filteredFishTotal(lake)) + "</dd>"
      + "<dt>Typical size</dt><dd>Not published by Alberta. Shown: stocked size and date. Growth is never guessed.</dd>"
      + (change ? "<dt>Versus " + pair.previous + '</dt><dd><span class="change-tag" style="background:' + cls.color
        + ";color:" + glyphInk(cls.id) + '">' + cls.glyph + "</span> " + esc(change) + "</dd>" : "")
      + "</dl>"
      + (lake.coord_source === "ats" ? '<p class="dim">Position estimated from the report\'s land description; expect a few hundred metres of error.</p>' : "")
      + '<div class="ats">' + esc(lake.ats || lakeKey(lake)) + "</div>"
      + '<div class="gridwrap"><table class="stock"><thead><tr><th>Date</th><th>Sp.</th><th>Strain</th><th>cm</th><th>g</th><th>Number</th></tr></thead><tbody>'
      + table + "</tbody></table></div>";
  }

  function directionsFrom(lake) {
    var o = DayUI.originPoint();
    return "https://www.google.com/maps/dir/?api=1&origin=" + o.lat + "," + o.lon
      + "&destination=" + lake.lat + "," + lake.lon + "&travelmode=driving";
  }

  function appleMapsUrl(lake) {
    var o = DayUI.originPoint();
    return "https://maps.apple.com/?saddr=" + o.lat + "," + o.lon + "&daddr=" + lake.lat + "," + lake.lon
      + "&dirflg=d&q=" + encodeURIComponent(lake.name);
  }

  function section(id, title, body, open) {
    return '<details data-sec="' + id + '"' + (open ? " open" : "") + "><summary>" + title + '</summary><div class="body">' + body + "</div></details>";
  }

  // ============================================================
  // THE WHOLE PANEL
  // ============================================================

  function html(lake) {
    var key = lakeKey(lake);
    var f = Forecast.forLake(lake);
    var d = state.day;
    var winter = DayUI.winterOn();
    var fav = state.favourites.has(key);
    var origin = DayUI.originPoint();
    var km = Number.isFinite(lake.distanceKm) ? Math.round(lake.distanceKm) + " km from " + esc(origin.name) : "";
    var size = lake.surface_area_ha != null ? esc(lake.surface_area_ha) + " ha" : "size unknown";
    var ban = lakeBaitBan(lake);
    var open = state.sections || {};
    var isOpen = function (id, def) { return open[id] === undefined ? def : open[id]; };
    var forecast = f ? forecastHtml(lake, f) : '<p class="dim">This lake has no position, so it has no forecast.</p>';

    return '<div class="grab" aria-hidden="true"></div>'
      + '<div class="lh"><div><h2 id="sheet-title">' + esc(lake.name) + '</h2><div class="sub">' + km + (km ? " · " : "") + size + "</div></div>"
      + '<div class="lh-btns"><button type="button" class="icon-btn star' + (fav ? " on" : "") + '" data-fav="' + esc(key) + '" aria-pressed="' + fav
      + '" aria-label="' + (fav ? "Remove from saved lakes" : "Save this lake") + '">' + (fav ? "★" : "☆") + "</button>"
      + '<button type="button" class="icon-btn" data-close-lake aria-label="Close lake">✕</button></div></div>'
      // The bait ban first, before anything else is read.
      + '<div class="lake-top">' + baitBanLine(lake)
      + tagsHtml(lake, winter)
      + verdictLine(lake) + "</div>"
      + (f ? bannerHtml(lake, f, d) + whyHtml(lake, f, d) : "")
      + aerationBlock(lake)
      + (f ? tipHtml(lake, f, d) : "")
      + section("forecast", "Forecast", forecast, isOpen("forecast", true))
      + section("bite", "Bite by time of day", '<div class="cx-embed" data-cx></div>', isOpen("bite", false))
      + section("fish", "Fish and stocking", stockingHtml(lake), isOpen("fish", false))
      + section("info", "Lake info", profileBlock(lake) + facilityBlock(lake) + depthBlock(lake)
          + '<div class="about" data-about></div>' + photoBlock(lake), isOpen("info", false))
      + section("rules", "Rules" + (ban ? " · bait ban" : ""), iceSeasonBlock(lake) + regulationBlock(lake)
          + '<a class="btn" href="' + RULES_URL + '" target="_blank" rel="noopener">Alberta fishing rules ↗</a>'
          + '<a class="btn" href="' + LICENCE_URL + '" target="_blank" rel="noopener">Buy a licence ↗</a>', isOpen("rules", ban))
      + section("go", "Getting there", lake.lat == null ? '<p class="dim">No recorded position.</p>'
          : '<a class="btn" href="' + directionsFrom(lake) + '" target="_blank" rel="noopener">Google Maps ↗</a>'
          + '<a class="btn" href="' + appleMapsUrl(lake) + '" target="_blank" rel="noopener">Apple Maps ↗</a>'
          + '<button type="button" class="btn" data-lakelink="' + esc(key) + '">Copy link to this lake</button>', isOpen("go", false));
  }

  function wire(host, lake) {
    var key = lakeKey(lake);
    var rerender = function () { DayUI.renderSheet(); };
    var q = function (sel) { return Array.prototype.slice.call(host.querySelectorAll(sel)); };
    q("[data-close-lake]").forEach(function (b) { b.addEventListener("click", function () { DayUI.closeLake(); }); });
    q("[data-fav]").forEach(function (b) { b.addEventListener("click", function () { toggleFavourite(key); }); });
    q("[data-fxtab]").forEach(function (b) { b.addEventListener("click", function () { state.fx.tab = b.dataset.fxtab; rerender(); }); });
    q("[data-fxspan]").forEach(function (b) { b.addEventListener("click", function () { state.fx.span = Number(b.dataset.fxspan); rerender(); }); });
    q("[data-fxview]").forEach(function (b) { b.addEventListener("click", function () { state.fx.view = b.dataset.fxview; rerender(); }); });
    q("details[data-sec]").forEach(function (det) {
      det.addEventListener("toggle", function () {
        state.sections = state.sections || {};
        state.sections[det.dataset.sec] = det.open;
        if (det.open && det.dataset.sec === "bite") fillBite(host, key);
      });
    });
    var bite = host.querySelector('details[data-sec="bite"]');
    if (bite && bite.open) fillBite(host, key);
    q("[data-photos]").forEach(function (b) {
      b.addEventListener("click", function () {
        state.sections = state.sections || {};
        state.sections.photos = true;
        LakePanel.open(key, host.querySelector("[data-about]"));
      });
    });
    // A redraw keeps the photos and description that were already opened.
    if (state.sections && state.sections.photos && host.querySelector("[data-about]")) {
      LakePanel.open(key, host.querySelector("[data-about]"));
    }
    q("[data-lakelink]").forEach(function (link) {
      link.addEventListener("click", function () {
        var url = lakeLinkUrl(key);
        var done = function (text) { link.textContent = text; setTimeout(function () { link.textContent = "Copy link to this lake"; }, 2500); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(url).then(function () { done("Link copied"); }, function () { done(url); });
        } else done(url);
      });
    });
  }

  function fillBite(host, key) {
    var slot = host.querySelector("[data-cx]");
    if (slot) ConditionsUI.renderInto(slot, key);
  }

  window.LakeSheet = {
    html: html,
    wire: wire,
    dayName: dayName,
    clock: clock,
    bandWord: bandWord,
    troutLimit: troutLimit,
    trophyRule: trophyRule,
    popularity: popularity,
    BAND_WORD: BAND_WORD,
    RULES_URL: RULES_URL,
    LICENCE_URL: LICENCE_URL,
  };
})();
