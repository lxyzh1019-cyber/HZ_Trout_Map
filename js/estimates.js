/* Estimates: ice-on and ice-off, insect hatches, turnover, flies and lures,
 * and how to fish a lake (Build 2, E1-E5).
 *
 * None of these is measured, and every one says so. Each result carries
 * { label: "estimated", inputs: [...] }: the word the panel prints next to it,
 * and the plain list of what it was worked out from, so a reader can judge it.
 *
 * The rules that bind:
 *   ice      dates of ice cover only. Never a thickness, never "safe".
 *            "Legal is not safe. Ice thickness is never forecast." goes next
 *            to every ice date.
 *   turnover reuses the lake's summer layer (stratification). No second model.
 *   tackle   never suggests bait on a bait-ban lake. The regulations stay the
 *            only legal source.
 *
 * Pure functions: no fetch, no DOM. They never throw on missing inputs; a
 * missing input drops out and the inputs list says what was used.
 */
(function () {
  "use strict";

  var DAY_MS = 86400000;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var ICE_WARNING = "Legal is not safe. Ice thickness is never forecast.";
  var LEGAL = "The regulations are the only legal source: check bait, hook and gear rules before you go.";

  function num(v) { return typeof v === "number" && isFinite(v) ? v : null; }
  function round1(v) { return Math.round(v * 10) / 10; }

  /** "Nov 12" in the lake's own calendar (offset in seconds), or the device's. */
  function fmtDate(date, offset) {
    if (!date) return "";
    if (offset == null) return MONTHS[date.getMonth()] + " " + date.getDate();
    var s = new Date(date.getTime() + offset * 1000);
    return MONTHS[s.getUTCMonth()] + " " + s.getUTCDate();
  }

  function depthClass(maxDepthM) {
    var d = num(maxDepthM);
    if (d === null) return { id: "unknown", label: "depth unknown: a medium-depth lake is used" };
    if (d < 5) return { id: "shallow", label: "max depth " + d + " m (shallow)" };
    if (d > 15) return { id: "deep", label: "max depth " + d + " m (deep)" };
    return { id: "medium", label: "max depth " + d + " m" };
  }

  // ============================================================
  // E1. ICE-ON AND ICE-OFF
  // ============================================================

  /* Degree-days. A lake freezes over once enough cold has piled up after it
   * cools: the sum of each day's mean air temperature below 0 °C. It opens once
   * enough warmth has piled up on the ice: the sum above 0 °C. A shallow lake
   * has little heat to lose and thin ice to melt; a deep one has more of both.
   * These thresholds are rules of thumb, which is why the result is labelled.
   *
   * The forecast covers 14 days (7 past, 7 ahead). Beyond it, the date comes
   * from the trend of the last forecast days, and failing that from the usual
   * dates for the lake's latitude and height. */
  var FREEZE_DD = { shallow: 20, medium: 40, unknown: 40, deep: 70 };
  var THAW_DD = { shallow: 40, medium: 70, unknown: 70, deep: 110 };
  var TREND_DAYS_MAX = 30;

  /* Usual dates: about Nov 8 for ice-on and Apr 28 for ice-off on a medium
   * lake at 53° N and 700 m, the middle of the stocked lakes. Further north
   * and higher up, ice comes earlier and goes later. */
  var USUAL = { onDoy: 312, offDoy: 118, refLat: 53, refElevM: 700,
                daysPerDegLat: 3, daysPer100m: 2,
                depthOn: { shallow: -5, medium: 0, unknown: 0, deep: 10 },
                depthOff: { shallow: -5, medium: 0, unknown: 0, deep: 7 } };

  function dayOfYearDate(year, doy) { return new Date(year, 0, 1 + Math.round(doy)); }

  function usualDates(lat, elevM, depthId, year) {
    var dLat = num(lat) === null ? 0 : lat - USUAL.refLat;
    var dElev = num(elevM) === null ? 0 : (elevM - USUAL.refElevM) / 100;
    var shift = dLat * USUAL.daysPerDegLat + dElev * USUAL.daysPer100m;
    return {
      on: dayOfYearDate(year, USUAL.onDoy - shift + USUAL.depthOn[depthId]),
      off: dayOfYearDate(year, USUAL.offDoy + shift + USUAL.depthOff[depthId]),
    };
  }

  /** o: { dailyT (unix s), dailyMeanC, airOffsetC, lat, elevM, cellElevM,
   *  maxDepthM, iced (the past-week guard), now (Date), offset (s) } */
  function ice(o) {
    o = o || {};
    var now = o.now instanceof Date ? o.now : new Date();
    var shift = num(o.airOffsetC) || 0;
    var depth = depthClass(o.maxDepthM);
    var thrOn = FREEZE_DD[depth.id], thrOff = THAW_DD[depth.id];
    var days = [];
    (o.dailyT || []).forEach(function (t, i) {
      var v = num((o.dailyMeanC || [])[i]);
      if (num(t) !== null && v !== null) days.push({ date: new Date(t * 1000), airC: v + shift });
    });

    var inputs = [];
    inputs.push(days.length ? days.length + " days of daily mean air (past and forecast), Open-Meteo" : "no forecast: usual dates only");
    if (num(o.elevM) !== null) {
      inputs.push("lake height " + Math.round(o.elevM) + " m (Open-Meteo elevation, Copernicus DEM)"
        + (num(o.cellElevM) !== null ? "; forecast spot " + Math.round(o.cellElevM) + " m, so the air is "
          + (shift >= 0 ? "+" : "") + round1(shift) + " °C" : ""));
    }
    if (num(o.lat) !== null) inputs.push("latitude " + round1(o.lat) + "°");
    inputs.push(depth.label);
    inputs.push("ice forms after about " + thrOn + " degree-days below 0 °C and goes after about " + thrOff + " above");

    var year = now.getFullYear();
    var usualNow = usualDates(o.lat, o.elevM, depth.id, year);
    var inUsualIce = now >= usualNow.on || now < usualNow.off;

    // State at the first day: the guard, or the usual season with a cold week.
    var firstWeek = days.slice(0, 7).map(function (d) { return d.airC; });
    var firstMean = firstWeek.length ? firstWeek.reduce(function (a, b) { return a + b; }, 0) / firstWeek.length : null;
    var covered = !!o.iced || (inUsualIce && firstMean !== null && firstMean < 0);
    var startCovered = covered;
    var freeze = 0, thaw = 0, onDate = null, offDate = null, todayCovered = covered;
    days.forEach(function (d) {
      if (!covered) {
        freeze = Math.max(0, freeze - d.airC);
        if (freeze >= thrOn) { covered = true; onDate = d.date; thaw = 0; }
      } else {
        thaw = Math.max(0, thaw + d.airC);
        if (thaw >= thrOff) { covered = false; offDate = d.date; freeze = 0; }
      }
      if (d.date.getTime() <= now.getTime()) todayCovered = covered;
    });
    if (o.iced) todayCovered = true;

    // Beyond the forecast: the trend of the last three days, then usual dates.
    var tail = days.slice(-3).map(function (d) { return d.airC; });
    var tailMean = tail.length ? tail.reduce(function (a, b) { return a + b; }, 0) / tail.length : null;
    var lastDay = days.length ? days[days.length - 1].date : now;
    var next = null;
    if (!covered && !onDate) {
      if (tailMean !== null && tailMean < 0) {
        var need = Math.ceil((thrOn - freeze) / -tailMean);
        if (need <= TREND_DAYS_MAX) next = { kind: "on", date: new Date(lastDay.getTime() + need * DAY_MS), basis: "trend" };
      }
      if (!next) {
        // Open water between the usual dates: the usual ice-on has passed.
        var on = now < usualNow.off ? usualDates(o.lat, o.elevM, depth.id, year - 1).on : usualNow.on;
        next = { kind: "on", date: on, basis: "usual dates", passed: inUsualIce };
      }
    } else if (covered && !offDate) {
      if (tailMean !== null && tailMean > 0) {
        var needT = Math.ceil((thrOff - thaw) / tailMean);
        if (needT <= TREND_DAYS_MAX) next = { kind: "off", date: new Date(lastDay.getTime() + needT * DAY_MS), basis: "trend" };
      }
      if (!next) {
        var off = usualNow.off;
        if (off < now) off = usualDates(o.lat, o.elevM, depth.id, year + 1).off;
        next = { kind: "off", date: off, basis: "usual dates" };
      }
    }

    var lines = [];
    var when = function (d) { return d.getTime() <= now.getTime() ? "past" : "forecast"; };
    if (onDate) {
      lines.push(when(onDate) === "past" ? "Ice cover likely since about " + fmtDate(onDate, o.offset) + "."
        : "Ice cover estimated to form about " + fmtDate(onDate, o.offset) + ".");
    }
    if (offDate) {
      lines.push(when(offDate) === "past" ? "Ice-off likely about " + fmtDate(offDate, o.offset) + "."
        : "Ice-off estimated about " + fmtDate(offDate, o.offset) + ".");
    }
    if (!onDate && !offDate && startCovered) lines.push("Ice cover likely now.");
    if (next) {
      var dateText = fmtDate(next.date, next.basis === "usual dates" ? null : o.offset);
      if (next.kind === "on") {
        lines.push(next.basis === "trend" ? "At the forecast's end trend, ice cover about " + dateText + "."
          : next.passed ? "Ice usually forms here by about " + dateText + ": it could form any week now."
          : "Ice usually forms here about " + dateText + ".");
      } else {
        lines.push(next.basis === "trend" ? "At the forecast's end trend, ice-off about " + dateText + "."
          : "Ice-off usually about " + dateText + " here.");
      }
    }
    return {
      label: "estimated",
      inputs: inputs,
      state: todayCovered ? "ice" : "open",
      iceOn: onDate ? { date: onDate, basis: when(onDate) === "past" ? "past days" : "forecast" }
        : next && next.kind === "on" ? { date: next.date, basis: next.basis } : null,
      iceOff: offDate ? { date: offDate, basis: when(offDate) === "past" ? "past days" : "forecast" }
        : next && next.kind === "off" ? { date: next.date, basis: next.basis } : null,
      text: lines.join(" "),
      warning: ICE_WARNING,
    };
  }

  // ============================================================
  // E2. HATCHES
  // ============================================================

  var HATCHES = [
    { id: "chironomid", name: "Chironomids", startC: 10 },
    { id: "mayfly", name: "Mayflies", startC: 14 },
    { id: "damselfly", name: "Damselflies", startC: 16 },
    { id: "sedge", name: "Sedges (caddis)", startC: 17 },
  ];
  var SOON_C = 2;

  /** o: { waterC, waterSource ("measured"|"modeled"), sigmaC, month (1-12), iced } */
  function hatch(o) {
    o = o || {};
    var w = num(o.waterC), month = num(o.month);
    var inputs = [w === null ? "no water temperature" : o.waterSource === "measured"
      ? "water " + round1(w) + " °C, measured" : "water about " + Math.round(w) + " °C ±" + Math.round(num(o.sigmaC) || 2) + ", estimated from the air"];
    if (month !== null) inputs.push("month " + MONTHS[month - 1]);
    inputs.push("hatches start at: " + HATCHES.map(function (h) { return h.name.split(" ")[0].toLowerCase() + " " + h.startC + " °C"; }).join(", "));
    var fall = month !== null && month >= 9;
    var list = HATCHES.map(function (h) {
      var status;
      if (o.iced) status = "under ice";
      else if (w === null) status = "unknown";
      else if (w >= h.startC) status = fall && h.id !== "chironomid" ? "ending" : "likely";
      else if (fall) status = h.id === "chironomid" && w >= 6 ? "fall hatch possible" : "done for the year";
      else if (w >= h.startC - SOON_C) status = "soon";
      else status = "not yet";
      return { id: h.id, name: h.name, startC: h.startC, status: status };
    });
    return { label: "estimated", inputs: inputs, hatches: list };
  }

  // ============================================================
  // E3. TURNOVER
  // ============================================================

  /* Turnover is the summer layer coming and going, so this reads the same
   * stratification the Summer layer row shows: stratifies or not, and its band.
   * Spring turnover follows ice-off; fall turnover comes when the surface cools
   * to between 4 and 10 °C. A lake that does not layer has no turnover. */
  var FALL_LO_C = 4, FALL_HI_C = 10, SPRING_WEEKS = 3;

  /** o: { stratification ({stratifies, band_m}) or null, maxDepthM, waterC,
   *  month (1-12), iced, iceOffDate, now } */
  function turnover(o) {
    o = o || {};
    var s = o.stratification || null;
    var w = num(o.waterC), month = num(o.month);
    var now = o.now instanceof Date ? o.now : new Date();
    var inputs = [];
    inputs.push(num(o.maxDepthM) === null ? "no depth survey" : "max depth " + o.maxDepthM + " m");
    if (s && s.stratifies && s.band_m) inputs.push("summer layer about " + s.band_m[0] + "–" + s.band_m[1] + " m");
    if (w !== null) inputs.push("surface about " + Math.round(w) + " °C");
    if (month !== null) inputs.push("month " + MONTHS[month - 1]);
    var out = function (state, text) { return { label: "estimated", inputs: inputs, state: state, text: text }; };

    if (!s || num(o.maxDepthM) === null) {
      return out("unknown", "Not known: there is no depth survey, so whether this lake layers in summer is not known.");
    }
    if (!s.stratifies) {
      return out("mixed", "Too shallow to layer: wind keeps it mixed all summer, so there is no turnover to wait out.");
    }
    if (o.iced) return out("ice", "Under ice. Spring turnover follows ice-off.");
    var sinceOff = o.iceOffDate instanceof Date ? (now - o.iceOffDate) / DAY_MS : null;
    var spring = month !== null && month <= 6
      && ((sinceOff !== null && sinceOff >= 0 && sinceOff <= SPRING_WEEKS * 7) || (w !== null && w >= FALL_LO_C && w <= FALL_HI_C));
    if (spring) {
      return out("spring", "Spring turnover likely now: after ice-off the lake mixes top to bottom. Fish spread out and the bite can be off for a few days.");
    }
    if (month !== null && month >= 9) {
      if (w !== null && w >= FALL_LO_C && w <= FALL_HI_C) {
        return out("fall", "Fall turnover likely now: the surface has cooled to about " + Math.round(w)
          + " °C and the lake mixes top to bottom. Fish spread out and the bite can be off for a few days.");
      }
      if (w !== null && w < FALL_LO_C) return out("cold", "Mixed and cold after turnover. Ice comes next.");
      return out("layered", "Still layered. Fall turnover comes when the surface cools to about 10 °C.");
    }
    if (month !== null && month >= 6) {
      return out("layered", "Layered: in warm weather fish the summer layer, about " + s.band_m[0] + "–" + s.band_m[1] + " m.");
    }
    return out("cold", "Cold and mixed before the summer layer forms.");
  }

  // ============================================================
  // E4. FLIES AND LURES
  // ============================================================

  var WARMWATER = ["WALL", "NRPK", "YLPR"];

  function seasonOf(month, iced, waterC) {
    if (iced) return "ice";
    if (month >= 9 && month <= 11) return "fall";
    if (month >= 6 && month <= 8 && (num(waterC) === null || waterC >= 12)) return "summer";
    if (month >= 3 && month <= 6) return "spring";
    return "open winter";
  }

  /** o: { month (1-12), iced, waterC, baitBan, species: [codes], hatches (hatch() result) } */
  function tackle(o) {
    o = o || {};
    var month = num(o.month) || (new Date().getMonth() + 1);
    var w = num(o.waterC);
    var season = seasonOf(month, !!o.iced, w);
    var flies = [], lures = [], bait = [];
    if (season === "ice") {
      flies.push("chironomid pupa under a small float, just off the bottom");
      lures.push("small jigging spoon", "small jig, 1/32 to 1/16 oz");
      bait.push("maggots or a piece of worm on the jig");
    } else if (season === "fall") {
      flies.push("leech, slow strip", "scud", "water boatman near the weeds");
      lures.push("small spoon", "spinner");
      bait.push("worm under a float");
    } else if (w !== null && w < 10) {
      flies.push("chironomid pupa under an indicator, 1 to 3 m off the bottom", "leech, slow strip");
      lures.push("small spoon near shore", "small spinner");
      bait.push("worm under a float");
    } else if (w !== null && w >= 17) {
      flies.push("leech or dragonfly nymph on a sinking line, down in the cooler water", "sedge dry fly at dusk");
      lures.push("spoon trolled deep, in the summer layer");
      bait.push("worm fished deep");
    } else {
      flies.push("chironomid pupa", "mayfly nymph", "leech");
      lures.push("spinner, size 1 or 2", "small spoon");
      bait.push("worm", "dough bait for stocked trout");
    }
    (o.hatches && o.hatches.hatches || []).forEach(function (h) {
      if (h.status !== "likely") return;
      var pattern = { damselfly: "damselfly nymph in the weeds", mayfly: "mayfly nymph or dry", sedge: "sedge pupa or dry at dusk" }[h.id];
      if (pattern && flies.indexOf(pattern) < 0 && flies.join(" ").indexOf(h.id) < 0) flies.push(pattern);
    });
    if ((o.species || []).some(function (c) { return WARMWATER.indexOf(c) >= 0; })) {
      lures.push("jig with a soft plastic, for walleye, pike or perch");
    }
    var inputs = ["season: " + season, w === null ? "no water temperature" : "water about " + Math.round(w) + " °C",
                  o.baitBan ? "bait ban in the regulations" : "bait allowed in the regulations"];
    if ((o.species || []).length) inputs.push("stocked species: " + o.species.join(", "));
    return {
      label: "estimated",
      inputs: inputs,
      season: season,
      flies: flies,
      lures: lures,
      // Never bait on a bait-ban lake: the list is not shortened, it is gone.
      bait: o.baitBan ? null : bait,
      baitNote: o.baitBan ? "Bait ban: flies and lures only, no bait, not even on a jig." : null,
      legal: LEGAL,
    };
  }

  // ============================================================
  // E5. HOW TO FISH THIS LAKE
  // ============================================================

  var ICE_WORDS = { "all-winter": "open all winter", "early-late": "early and late ice", "early": "early ice only",
                    "late": "late ice only", "closed": "closed in winter" };

  /** o: { maxDepthM, stratification, areaHa, aerated, amenities: [..], baitBan,
   *  iceKind, troutLimit } */
  function howToFish(o) {
    o = o || {};
    var lines = [], inputs = [];
    var area = num(o.areaHa);
    if (area === null) lines.push("Size unknown: walk the shore first and look for drop-offs and weed edges.");
    else if (area < 10) lines.push("Small water (" + area + " ha): fish from shore or a float tube, along the drop-offs.");
    else if (area <= 200) lines.push("Medium lake (" + area + " ha): shore or a small boat; work the weed edges and points.");
    else lines.push("Big water (" + area + " ha): a boat covers it best. Wind builds waves fast here.");
    inputs.push(area === null ? "no area" : "area " + area + " ha");

    var depth = num(o.maxDepthM), s = o.stratification;
    if (depth === null) lines.push("No depth survey: find the drop-offs with a sounder or a weighted line.");
    else if (s && s.stratifies && s.band_m) {
      lines.push("Max depth " + depth + " m. In midsummer fish the summer layer, about " + s.band_m[0] + "–" + s.band_m[1]
        + " m; in spring and fall fish shallower, 1 to 4 m.");
    } else lines.push("Shallow (max " + depth + " m): fish the whole lake. In summer fish early and late.");
    inputs.push(depth === null ? "no depth" : "max depth " + depth + " m");

    var have = function (a) { return (o.amenities || []).indexOf(a) >= 0; };
    var fac = [];
    if (have("Boat Launch")) fac.push("a boat launch");
    if (have("Dock/Pier")) fac.push("a dock or pier for shore fishing");
    if (have("Fishing Access")) fac.push("a fishing access point");
    if (have("Paddling") || have("Paddling Canoe") || have("Paddling Kayak")) fac.push("paddling: a canoe or kayak works");
    if (fac.length) lines.push("On site: " + fac.join(", ") + ".");
    inputs.push((o.amenities || []).length ? "facilities from Alberta's lake page" : "no facilities listed");

    if (o.aerated) {
      lines.push("Aerated: in winter there is thin ice and open water near the aerators. Stay behind the fence.");
      inputs.push("aerated (ACA or Alberta)");
    }
    if (o.baitBan) lines.push("Bait ban: flies and lures only.");
    if (o.iceKind) lines.push("Ice fishing season: " + (ICE_WORDS[o.iceKind] || o.iceKind) + ". " + ICE_WARNING);
    var lim = num(o.troutLimit);
    if (lim !== null) lines.push(lim === 0 ? "Catch and release only for trout." : "Trout limit " + lim + ": keep few, release the rest.");
    inputs.push("regulations: bait rule, ice season, trout limit");
    lines.push(LEGAL);
    return { label: "estimated", inputs: inputs, lines: lines };
  }

  window.Estimates = {
    ice: ice,
    hatch: hatch,
    turnover: turnover,
    tackle: tackle,
    howToFish: howToFish,
    usualDates: usualDates,
    fmtDate: fmtDate,
    HATCHES: HATCHES,
    FREEZE_DD: FREEZE_DD,
    THAW_DD: THAW_DD,
    ICE_WARNING: ICE_WARNING,
    LEGAL: LEGAL,
  };
})();
