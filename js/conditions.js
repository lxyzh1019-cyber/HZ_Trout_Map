/* How good the fishing is likely to be, and how much of that we actually know.
 *
 * The weights here are not conventional, deliberately. Most fishing calendars
 * blend sun, moon and barometric pressure as though the evidence behind them
 * were comparable. It is not:
 *
 *   light            strong    salmonids are demonstrably crepuscular, and
 *                              light governs prey detection directly
 *   water temperature strong   fish are ectotherms; appetite follows metabolism,
 *                              and the thermal optima are well published
 *   pressure         moderate  but only as a proxy for an arriving front. A
 *                              controlled feeding trial on yellow perch found no
 *                              direct effect, and the arithmetic says why:
 *                              1 hPa is 1.02 cm of water, so a 30 hPa storm is
 *                              31 cm of depth — less than a fish feels drifting
 *                              up off a shoal
 *   moon             weak      real, and measured: 341,959 muskellunge gave a
 *                              genuine lunar signal worth about 5% at most
 *                              (Vinson & Angradi 2014)
 *
 * So light and water carry three quarters of the score, pressure is labelled as
 * the front proxy it is, and the moon is a multiplier hard-capped at five
 * percent that is applied after everything else. It can never move a peak.
 *
 * scoreSlot is pure and total: no fetch, no DOM, it never throws, and it never
 * returns NaN. Every caller depends on that, and so does the self-check.
 */
(function () {
  "use strict";

  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  function clamp01(v) { return clamp(v, 0, 1); }
  function num(v) { return typeof v === "number" && isFinite(v) ? v : null; }

  // ============================================================
  // WEIGHTS AND EVIDENCE TIERS
  // ============================================================

  var WEIGHTS = { light: 0.40, water: 0.35, pressure: 0.15, wind: 0.06, precip: 0.04 };

  /* Tiers are per reading, not per factor. Water is strong physiology measured
   * with a thermometer and weak guesswork modelled from the air, and the chip
   * has to say which — otherwise it is decoration. */
  var TIERS = {
    light: "strong",
    pressure: "moderate",
    wind: "moderate",
    precip: "weak",
    moon: "weak",
  };

  /* Environment Canada issues a wind warning at 70 km/h sustained or 90 gusting,
   * which is a warning about property. This is lower on purpose: it is the
   * point where a small boat and a light presentation stop working, not the
   * point where something blows over. */
  var GUST_WARN_KPH = 40;

  var MOON_CAP = 0.05;   // Vinson & Angradi 2014. Not a tuning knob.

  // ============================================================
  // SPECIES THERMAL BANDS (degrees C)
  // ============================================================

  /* lo and hi are where feeding effectively stops; optLo to optHi is the band
   * where growth and feed conversion are best. Sources are listed on
   * evidence.html. Tiger trout is interpolated between its parents rather than
   * cited — it is an inference, and the page says so. */
  var BANDS = {
    RNTR: { lo: 4, optLo: 12, optHi: 18, hi: 24 },
    BKTR: { lo: 3, optLo: 11, optHi: 16, hi: 21 },
    BNTR: { lo: 4, optLo: 12, optHi: 19, hi: 25 },
    TGTR: { lo: 3, optLo: 11, optHi: 17, hi: 22 },
    CTTR: { lo: 3, optLo: 9,  optHi: 16, hi: 22 },
    WSCT: { lo: 2, optLo: 8,  optHi: 15, hi: 20 },

    /* The three warmwater and coldwater species that are not salmonids.
     *
     * These went unbanded when walleye, pike and grayling first came onto the
     * map, because handing any of them a trout curve would not have been an
     * approximation: at 22 °C a rainbow is near the top of its tolerance and a
     * walleye is close to where it grows best, so the same water would have
     * read nearly lethal and prime depending only on which fish you asked
     * about. Better to score nothing than to score it backwards.
     *
     * The numbers come from the same USFWS Habitat Suitability Index series the
     * salmonid bands above rest on, so this is the existing kind of evidence
     * extended rather than a new kind admitted. Cited on evidence.html.
     *
     * The COLD bound on all three is an inference, not a quoted figure, and is
     * marked with an asterisk on that page. The published work bounds growth,
     * and all three of these feed under the ice in Alberta — a pike taken
     * through a hole in February is not a pike that has stopped feeding. So
     * `lo` is set where feeding plausibly ceases rather than where growth does,
     * which is the softer claim and the one this band is about. */
    WALL: { lo: 2, optLo: 20, optHi: 24, hi: 29 },
    NRPK: { lo: 1, optLo: 19, optHi: 21, hi: 29 },
    ARGR: { lo: 1, optLo: 10, optHi: 17, hi: 22 },
  };
  var FALLBACK_BAND = BANDS.RNTR;

  // ============================================================
  // SUB-SCORES
  // ============================================================

  /* Light is the one factor that is always available, because it needs no
   * network. The floor comes from where the sun is; the peak is a Gaussian on
   * the distance to the nearest of civil dawn, sunrise, sunset and civil dusk.
   *
   * Cloud lifts a bright afternoon and does nothing at dusk, which is already
   * dim. That interaction is why an overcast day fishes well all day — a real
   * effect that a sun-and-moon calendar cannot express at all. */
  var PEAK_SIGMA_MIN = 45;

  function lightScore(sunAltDeg, minsToEdge, cloudFrac) {
    var alt = num(sunAltDeg);
    if (alt === null) return null;
    var floor =
      alt >  30 ? 0.20 :
      alt >  10 ? 0.35 :
      alt >   0 ? 0.70 :
      alt >  -6 ? 0.90 :        // civil twilight, the best of it
      alt > -12 ? 0.55 :
      alt > -18 ? 0.40 : 0.30;  // full dark: trout are visual feeders

    var m = num(minsToEdge);
    var peak = m === null ? 0 : Math.exp(-(m * m) / (2 * PEAK_SIGMA_MIN * PEAK_SIGMA_MIN));
    var s = Math.max(floor, peak);

    var cloud = num(cloudFrac);
    if (cloud !== null && alt > 10) s += 0.25 * clamp01(cloud) * (1 - s);
    return clamp01(s);
  }

  /** Trapezoid across a species band: flat through the optimum, tapering out. */
  function waterScoreFor(tempC, band) {
    var t = num(tempC);
    if (t === null || !band) return null;
    if (t <= band.lo || t >= band.hi) return 0.05;
    if (t >= band.optLo && t <= band.optHi) return 1;
    return t < band.optLo
      ? (t - band.lo) / (band.optLo - band.lo)
      : (band.hi - t) / (band.hi - band.optHi);
  }

  /* Across several species take the best, and name it. Averaging would report
   * "mediocre for everything" on a day when one species is squarely on, which is
   * the opposite of useful. */
  function waterScore(tempC, speciesCodes) {
    var codes = (speciesCodes && speciesCodes.length) ? speciesCodes : ["RNTR"];
    var best = null, bestCode = null;
    codes.forEach(function (c) {
      var s = waterScoreFor(tempC, BANDS[c] || FALLBACK_BAND);
      if (s !== null && (best === null || s > best)) { best = s; bestCode = c; }
    });
    return { score: best, species: bestCode };
  }

  /* Pressure is scored on its trend, never its level: Alberta lakes sit between
   * roughly 600 and 1500 m, so an absolute reading says more about elevation
   * than about weather. Falling means a front is on the way. The level is still
   * printed beside the trend — it is what you can check against your own
   * barometer — but nothing below ever reads it. */
  function pressureScore(dP3h, dP12h) {
    var d3 = num(dP3h);
    if (d3 === null) return null;
    if (d3 <= -2.0) return 0.85;          // front already on you, often raining
    if (d3 <= -0.7) return 1.00;          // pre-frontal, the classic window
    if (d3 < 0.7) {                        // steady: let the longer trend decide
      var d12 = num(dP12h);
      if (d12 === null) return 0.65;
      if (d12 <= -3) return 0.80;          // sitting in a trough
      if (d12 >= 3) return 0.50;           // sitting in a ridge
      return 0.65;
    }
    if (d3 < 2.0) return 0.40;            // post-frontal bluebird
    return 0.30;
  }

  /* Open-Meteo answers in hectopascals, which is what a meteorologist reads.
   * Environment Canada publishes kilopascals, which is what an Alberta angler
   * reads and what the barometer in a truck shows. Ten hectopascals to the
   * kilopascal, applied here at the edge and nowhere else — every score above
   * still runs on the hPa the API sent, so no threshold moves. */
  function kPa(hPa) {
    var v = num(hPa);
    return v === null ? null : v / 10;
  }

  /* The trend is what predicts the bite, so it leads. The level is shown beside
   * it because it is the number you can check against your own barometer, and
   * because a trend with nothing to hang it on is hard to trust. */
  function pressureNote(dP3h, hPa) {
    var trend = kPa(dP3h);
    var text = (trend > 0 ? "+" : "") + trend.toFixed(2) + " kPa/3h — front proxy";
    var level = kPa(hPa);
    return level === null ? text : level.toFixed(1) + " kPa, " + text;
  }

  /* Gusts are shown and never scored. What a gust decides is whether you can
   * hold a drift or turn over a light float — a question about the boat and the
   * cast. What the feeding evidence is actually about is the mean wind that
   * puts a ripple on the surface. Folding gusts into the score would be tuning
   * on a hunch, which is the one thing this file will not do. */
  function windNote(kph, gustKph) {
    var text = Math.round(kph) + " km/h";
    var g = num(gustKph);
    // Only when the gust is meaningfully above the mean; otherwise it is noise.
    if (g !== null && g >= kph + 8) text += " · gusting " + Math.round(g);
    return text;
  }

  /** A ripple beats a mirror; a gale is a safety problem before a fishing one. */
  function windScore(kph) {
    var w = num(kph);
    if (w === null) return null;
    if (w < 3) return 0.65;
    if (w < 6) return 0.85;
    if (w <= 16) return 1.00;
    if (w <= 25) return 0.80;
    if (w <= 35) return 0.50;
    return 0.25;
  }

  function precipScore(mm) {
    var p = num(mm);
    if (p === null) return null;
    if (p === 0) return 1.00;
    if (p < 1) return 0.85;
    if (p < 4) return 0.60;
    return 0.35;
  }

  /* Forecast skill decays, and pressure decays fastest. Rather than greying a
   * cell out and leaving the number alone, shrink pressure's weight with lead
   * time and let the renormaliser push that weight onto light, which is exact at
   * any range. Seven days out the score honestly becomes "when is dusk, and
   * roughly how warm is the water". */
  function leadDecay(leadDays) {
    var d = num(leadDays);
    if (d === null) return 1;
    return clamp(1 - Math.max(0, d - 2) / 5, 0.2, 1);
  }

  // ============================================================
  // WATER TEMPERATURE FROM AIR
  // ============================================================

  /* Lake surface temperature follows a lagged, smoothed air temperature — but
   * not in a straight line, and the difference matters here.
   *
   * A straight line is the obvious model and it is wrong at the top. Fitting
   * water = 1.5 + 0.9 x air to a hot Alberta week of 28 C gives 26 C of water,
   * which no lake in this province reaches: evaporation and mixing cap a prairie
   * lake around the low twenties no matter how hot the air gets. Since water
   * carries the second largest weight in the score, over-predicting it would
   * push lakes past the trout band and fire depth advisories for a problem that
   * is not there.
   *
   * So this uses the S-shaped form instead (Mohseni, Stefan and Erickson 1998),
   * which saturates at both ends: near zero under ice, and at a ceiling in
   * midsummer.
   *
   * Say the uncomfortable part out loud: these four constants are not calibrated
   * for any particular Alberta lake. They are the model's assumption and the
   * weakest numbers in this file. That is why nothing here returns a bare
   * temperature — sigma travels with it, the UI prints it dimmed and marked as
   * modelled, and a reading taken with a thermometer replaces it outright.
   */
  var WT_MAX_C = 22;        // ceiling a prairie lake surface actually reaches
  var WT_MIN_C = 0;         // floor: ice
  var WT_INFLECTION_C = 12; // air temperature at the steepest part of the curve
  var WT_STEEPNESS = 0.13;
  var WT_HALFLIFE_DAYS = 3;

  function waterFromAir(dailyMeanC, opts) {
    var o = opts || {};
    var series = (dailyMeanC || []).map(num).filter(function (v) { return v !== null; });
    if (!series.length) return null;

    // Exponentially weighted, most recent last, so recent days dominate.
    var lambda = Math.pow(0.5, 1 / WT_HALFLIFE_DAYS);
    var wsum = 0, acc = 0;
    for (var i = series.length - 1, age = 0; i >= 0; i--, age++) {
      var w = Math.pow(lambda, age);
      acc += w * series[i];
      wsum += w;
    }
    var mean = acc / wsum;
    var tempC = clamp(
      WT_MIN_C + (WT_MAX_C - WT_MIN_C) /
        (1 + Math.exp(WT_STEEPNESS * (WT_INFLECTION_C - mean))),
      0, WT_MAX_C);

    var sigma = 2.0;
    if (num(o.areaHa) !== null && o.areaHa > 500) sigma += 1.0;  // big water lags harder
    var slope = series.length > 1
      ? (series[series.length - 1] - series[0]) / (series.length - 1) : 0;
    if (Math.abs(slope) > 3) sigma += 1.5;                        // moving fast, model behind

    /* Ice is not a nuance here, it is most of the Alberta year. If the air has
     * been below freezing for most of the window, say hardwater rather than
     * scoring the lake near zero and calling it poor. */
    var belowFreezing = series.filter(function (v) { return v < 0; }).length;
    var likelyIce = series.length >= 5 &&
      belowFreezing >= Math.ceil(series.length * 0.8) && mean < -2;

    return {
      tempC: likelyIce ? clamp(tempC, 0, 4) : tempC,
      sigmaC: sigma,
      source: "modeled",
      likelyIce: likelyIce,
      airMeanC: mean,
    };
  }

  // ============================================================
  // STRATIFICATION
  // ============================================================

  /* In midsummer a deep lake separates into layers and the trout sit below the
   * warm top, so a hot surface reading describes water they are avoiding.
   * Scoring the lake badly on it would be actively wrong advice.
   *
   * This fails closed. Without a depth we do not know whether the lake even
   * stratifies — a three metre prairie pothole stays mixed all summer — and
   * sending someone to fish eight metres in three metres of water is a real
   * harm, so with no depth there is no advisory at all. */
  var MIN_STRATIFYING_DEPTH_M = 5;

  function stratification(opts) {
    var o = opts || {};
    var surface = num(o.surfaceC), band = o.band || FALLBACK_BAND;
    var month = num(o.month);
    var depth = num(o.maxDepthM);
    var inSeason = month !== null && month >= 6 && month <= 9;

    if (surface === null || !inSeason || surface <= band.optHi) {
      return { stratified: false, advisory: null, depthKnown: depth !== null };
    }
    if (depth === null) {
      return {
        stratified: false,
        depthKnown: false,
        advisory: "Surface is above this species' band. Whether the lake is deep " +
                  "enough to hold cooler water below is unknown — there is no depth " +
                  "survey for it here.",
      };
    }
    if (depth < MIN_STRATIFYING_DEPTH_M) {
      return {
        stratified: false,
        depthKnown: true,
        advisory: "Shallow enough that wind keeps it mixed, so there is no cooler " +
                  "layer to drop to. Fish the dawn and dusk windows instead.",
      };
    }
    /* A band, never a number, and scaled only weakly by size. This is a rule of
     * thumb standing in for a temperature profile we do not have. */
    var lo = Math.max(3, Math.round(depth * 0.25));
    var hi = Math.max(lo + 2, Math.round(depth * 0.5));
    return {
      stratified: true,
      depthKnown: true,
      bandM: [lo, hi],
      advisory: "Surface is above this species' band, but the lake is deep enough " +
                "to layer. Expect fish near the thermocline, roughly " + lo + "–" + hi +
                " m — cooler below that, but the oxygen thins out near the bottom by " +
                "late summer. A rule of thumb, not a measurement.",
    };
  }

  // ============================================================
  // THE SCORE
  // ============================================================

  function bandName(score) {
    return score >= 0.75 ? "Prime" : score >= 0.60 ? "Good" : score >= 0.42 ? "Fair" : "Poor";
  }

  /* Say what is missing, rather than bucketing a number. "Astronomy only" has to
   * mean exactly one thing — that sun and moon are all we had — or the label
   * stops being trustworthy the moment the weights are touched. */
  function confidenceOf(hasWeather, hasWater) {
    if (!hasWeather && !hasWater) return "Astronomy only";
    if (hasWeather && hasWater) return "Full";
    return "Partial";
  }

  /* The moon, applied once, here, after the weighted sum is already finished.
   * lightScore is never handed a lunar quantity of any kind, and the cap is
   * arithmetic rather than a clamp on a larger number: raw sits in [0,1], so the
   * multiplier cannot leave [0.95, 1.05] even if the terms change. The clamp is
   * a belt on top of that.
   *
   * Consequence worth stating: a dusk slot scores above 0.90 and a midday slot
   * below 0.45, so a five percent rescale cannot reorder them. The best window
   * of the day does not depend on the moon. That is asserted, not just intended.
   */
  function moonMultiplier(phase, period) {
    var p = num(phase);
    if (p === null) return { mult: 1, raw: null, note: null };
    var periodBonus = !period ? 0 : period.kind === "major" ? 1 : 0.5;
    var phaseBonus = Math.abs(Math.cos(2 * Math.PI * p));   // 1 at new and full
    var raw = 0.6 * periodBonus + 0.4 * phaseBonus;
    return {
      mult: clamp(1 + MOON_CAP * (2 * raw - 1), 1 - MOON_CAP, 1 + MOON_CAP),
      raw: raw,
      note: period ? (period.kind === "major" ? "major period" : "minor period") + " (" + period.label + ")" : null,
    };
  }

  function scoreSlot(input) {
    var o = input || {};
    var astro = o.astro || null;
    var weather = o.weather || null;
    var water = o.water || null;
    var species = o.species || null;

    var factors = {};
    var advisories = [];

    // --- light ------------------------------------------------------------
    var sunAlt = null, minsEdge = null;
    if (astro && o.when && window.Astro) {
      sunAlt = window.Astro.sunPosition(o.when, astro.lat, astro.lon).altitude;
      minsEdge = window.Astro.minutesToNearestEdge(o.when, astro.sun);
    }
    var cloudFrac = weather && num(weather.cloudCoverPct) !== null
      ? clamp01(weather.cloudCoverPct / 100) : null;
    factors.light = {
      s: lightScore(sunAlt, minsEdge, cloudFrac),
      tier: TIERS.light,
      value: sunAlt === null ? null : Math.round(sunAlt * 10) / 10,
      note: sunAlt === null ? null : "sun " + Math.round(sunAlt) + "°"
        + (cloudFrac === null ? "" : ", cloud " + Math.round(cloudFrac * 100) + "%"),
    };

    // --- water ------------------------------------------------------------
    var w = waterScore(water ? water.tempC : null, species);
    var waterTier = num(water && water.tempC) === null ? null
      : water.source === "measured" ? "strong" : "moderate";

    var strat = stratification({
      surfaceC: water ? water.tempC : null,
      band: species && species.length ? (BANDS[w.species] || FALLBACK_BAND) : FALLBACK_BAND,
      month: o.when ? o.when.getMonth() + 1 : null,
      maxDepthM: o.maxDepthM,
      areaHa: o.areaHa,
    });
    if (strat.advisory) {
      advisories.push(strat.advisory);
      waterTier = "weak";
      /* Score the water the fish can actually reach, not the surface they are
       * avoiding. The cost lands on confidence, not on the number. */
      if (strat.stratified) {
        var band = BANDS[w.species] || FALLBACK_BAND;
        w = { score: waterScoreFor(Math.min(water.tempC, band.optHi), band),
              species: w.species };
      }
    }
    if (water && water.likelyIce) {
      advisories.push("Air has been below freezing for most of the past week — " +
                      "expect ice, and treat this as a hardwater trip.");
    }
    factors.water = {
      s: w.score, tier: waterTier,
      value: num(water && water.tempC),
      species: w.species,
      source: water ? water.source : null,
      sigmaC: num(water && water.sigmaC),
      note: num(water && water.tempC) === null ? null
        : (water.source === "measured"
            ? water.tempC.toFixed(1) + "°C measured"
            : "~" + Math.round(water.tempC) + "°C ±" + Math.round(num(water.sigmaC) || 2) + " modeled"),
    };

    // --- pressure, wind, precipitation -------------------------------------
    factors.pressure = {
      s: weather ? pressureScore(weather.dP3h, weather.dP12h) : null,
      tier: TIERS.pressure,
      value: num(weather && weather.dP3h),
      note: !weather || num(weather.dP3h) === null ? null
        : pressureNote(weather.dP3h, weather.pressureMslHpa),
    };
    factors.wind = {
      s: weather ? windScore(weather.windKph) : null,
      tier: TIERS.wind,
      value: num(weather && weather.windKph),
      note: !weather || num(weather.windKph) === null ? null
        : windNote(weather.windKph, weather.gustKph),
    };
    /* A gust that pulls the score down would be double-counting the mean wind
     * it comes with. A gust that flips a boat is a different kind of fact, and
     * it belongs where the ice warning goes, not in the arithmetic. */
    if (weather && num(weather.gustKph) !== null && weather.gustKph >= GUST_WARN_KPH) {
      advisories.push("Gusting to " + Math.round(weather.gustKph) + " km/h \u2014 hard to hold a "
        + "drift or turn over a light float, and a small boat's problem before "
        + "it is a fishing one.");
    }

    factors.precip = {
      s: weather ? precipScore(weather.precipMm) : null,
      tier: TIERS.precip,
      value: num(weather && weather.precipMm),
      note: !weather || num(weather.precipMm) === null ? null
        : weather.precipMm.toFixed(1) + " mm",
    };

    // --- combine, renormalising over whatever is actually present ----------
    var decay = leadDecay(o.leadDays);
    var numer = 0, denom = 0, available = 0;
    Object.keys(WEIGHTS).forEach(function (k) {
      var f = factors[k];
      if (!f || f.s === null) return;
      var weight = WEIGHTS[k] * (k === "pressure" ? decay : 1);
      numer += weight * f.s;
      denom += weight;
      available += WEIGHTS[k];
      f.weight = weight;
    });

    var base = denom > 0 ? numer / denom : 0.5;
    var moon = moonMultiplier(astro && astro.moon ? astro.moon.phase : null,
                              astro && astro.periods && o.when
                                ? window.Astro.periodAt(o.when, astro.periods) : null);

    /* Two numbers, deliberately. The displayed score is clamped to [0,1] because
     * that is the contract, but clamping destroys the ordering exactly where it
     * matters most: on a flawless evening several adjacent slots all peg at 1.00
     * and "best moment" becomes whichever one happened to be tested first. So
     * ranking uses the unclamped value. Nothing outside this file should display
     * scoreRaw — it is for comparing slots, not for showing. */
    var raw = base * moon.mult;
    var score = clamp01(raw);

    return {
      score: score,
      scoreRaw: raw,
      band: bandName(score),
      factors: factors,
      moonMult: moon.mult,
      moonNote: moon.note,
      moonTier: TIERS.moon,
      coverage: available,
      confidence: confidenceOf(factors.pressure.s !== null || factors.wind.s !== null ||
                               factors.precip.s !== null,
                               factors.water.s !== null),
      advisories: advisories,
      when: o.when || null,
    };
  }

  /** Best slot in a list, for a day part or a six-hour window. Ranks on the
   *  unclamped score so a ceiling of ties cannot make the answer arbitrary. */
  function bestOf(results) {
    var best = null, bestKey = -Infinity;
    (results || []).forEach(function (r) {
      if (!r) return;
      var key = num(r.scoreRaw) !== null ? r.scoreRaw : r.score;
      if (key > bestKey) { bestKey = key; best = r; }
    });
    return best;
  }

  // ============================================================
  // SEASONS
  // ============================================================

  var MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
                "jul", "aug", "sep", "oct", "nov", "dec"];

  /* Whether a season from the regulations covers a date.
   *
   * Returns null rather than guessing when the wording is not one we
   * recognise. An unrecognised season must not quietly become "open".
   *
   * The case worth writing a test for is that seasons wrap the new year. NB1
   * lakes run May 15 to Mar. 31 — most of the year, but shut through April.
   * Treated as an ordinary start-before-end range that reads backwards for
   * eleven months of the twelve, which is the kind of wrong that looks right
   * in January.
   */
  function seasonOpenOn(text, when) {
    var t = String(text || "");
    if (!t) return null;
    if (/CLOSED\s+ALL\s+YEAR/i.test(t)) return false;
    if (/OPEN\s+ALL\s+YEAR/i.test(t)) return true;
    /* A season can name more than one range: "OPEN MAY 15 TO OCT. 31 AND
     * DEC. 11 TO MAR. 31". Reading only the first range shut that lake all
     * winter, so every range is read and any one of them opens the day. */
    var re = /([A-Za-z]+)\.?\s+(\d{1,2})\s+TO\s+([A-Za-z]+)\.?\s+(\d{1,2})/gi;
    if (!/^\s*OPEN\b/i.test(t)) return null;
    var at = function (mo, d) { return mo * 100 + d; };
    var day = when instanceof Date ? when : new Date();
    var now = at(day.getMonth(), day.getDate());
    var m, found = false;
    while ((m = re.exec(t)) !== null) {
      var from = MONTHS.indexOf(m[1].slice(0, 3).toLowerCase());
      var to = MONTHS.indexOf(m[3].slice(0, 3).toLowerCase());
      if (from < 0 || to < 0) return null;
      found = true;
      var start = at(from, Number(m[2])), end = at(to, Number(m[4]));
      var open = start <= end ? (now >= start && now <= end)
                              : (now >= start || now <= end);
      if (open) return true;
    }
    return found ? false : null;
  }

  /* Whether a season is open for ice fishing: open on every day from
   * Dec. 15 to Mar. 1, the part of the winter that has fishable ice across
   * Alberta. Open all year passes, and so does "May 15 to Mar. 31", which is
   * shut in April and open all winter. Null when the wording is not read. */
  function seasonOpenAllWinter(text) {
    var day = new Date(2026, 11, 15), last = new Date(2027, 2, 1);
    for (; day <= last; day.setDate(day.getDate() + 1)) {
      var open = seasonOpenOn(text, new Date(day.getTime()));
      if (open !== true) return open;
    }
    return true;
  }

  /* Which part of the ice season the regulations allow. Early ice is the
   * first ice of the year, so a season still open on Nov. 30 has it; late ice
   * is the last, so a season open on Apr. 1 has it. A season can have both
   * ("Apr. 1 to Nov. 30") and still be shut in midwinter. Null when the
   * wording is not read. Legal is not the same as safe, and nothing here
   * knows how thick the ice is. */
  function seasonIceKind(text) {
    var winter = seasonOpenAllWinter(text);
    if (winter === null) return null;
    if (winter) return "all-winter";
    var early = seasonOpenOn(text, new Date(2026, 10, 30)) === true;
    var late = seasonOpenOn(text, new Date(2027, 3, 1)) === true;
    return early && late ? "early-late" : early ? "early" : late ? "late" : "closed";
  }

  /* Ice likely: every one of the last seven daily mean air temperatures was
   * below freezing. Fewer than seven days is not enough to say so. */
  function iceLikely(dailyMeanC) {
    var days = (dailyMeanC || []).map(num).filter(function (v) { return v !== null; });
    if (days.length < 7) return false;
    return days.slice(-7).every(function (v) { return v < 0; });
  }

  // ============================================================
  // WHY THIS SCORE
  // ============================================================

  var PART_NAMES = { light: "Light", water: "Water temperature", pressure: "Pressure trend",
                     wind: "Wind", precip: "Rain" };

  /* The parts of a Bite score, as whole points that add up to the number shown.
   *
   * The score is a weighted mean over whichever factors were present, times the
   * moon, then clamped. A multiplier is not a part you can add, so the moon is
   * folded into every part in proportion, and the clamp the same way. Each part
   * is its share of the weights times how well that factor scored. Rounding is
   * by largest remainder, so the parts never sum to one more or one less than
   * the score beside them. `max` is the most that part could have given. */
  function whyParts(result) {
    var r = result || {};
    var factors = r.factors || {};
    var total = Math.round(clamp01(num(r.score) || 0) * 100);
    var raw = num(r.scoreRaw), score = num(r.score);
    var squash = raw && raw > 0 && score !== null ? score / raw : 1;
    var mult = (num(r.moonMult) || 1) * squash;
    var denom = 0;
    Object.keys(WEIGHTS).forEach(function (k) {
      var f = factors[k];
      if (f && f.s !== null && num(f.weight) !== null) denom += f.weight;
    });
    var parts = Object.keys(WEIGHTS).map(function (k) {
      var f = factors[k];
      var present = f && f.s !== null && num(f.weight) !== null && denom > 0;
      var share = present ? f.weight / denom : 0;
      return {
        id: k, label: PART_NAMES[k],
        exact: present ? share * f.s * mult * 100 : 0,
        // The moon can lift a part above its weight, so its most is moon-sized too.
        max: present ? Math.round(share * 100 * Math.max(1, num(r.moonMult) || 1)) : 0,
        present: !!present,
        note: f ? f.note : null,
      };
    });
    var floors = parts.map(function (p) { return Math.floor(p.exact); });
    var short = total - floors.reduce(function (a, b) { return a + b; }, 0);
    var order = parts.map(function (p, i) { return i; })
      .filter(function (i) { return parts[i].present; })
      .sort(function (a, b) { return (parts[b].exact - floors[b]) - (parts[a].exact - floors[a]); });
    for (var i = 0; short > 0 && order.length; i = (i + 1) % order.length, short--) floors[order[i]]++;
    for (var j = order.length - 1; short < 0 && order.length; j = (j - 1 + order.length) % order.length) {
      if (floors[order[j]] > 0) { floors[order[j]]--; short++; }
    }
    parts.forEach(function (p, i) { p.points = floors[i]; delete p.exact; });
    return { parts: parts, total: total, moonMult: num(r.moonMult) || 1 };
  }

  // ============================================================
  // DAY OUT
  // ============================================================

  /* Day out is about the person and the boat, not the fish. Gusts are left out
   * of the Bite score on purpose, so this is where they count: the mean wind
   * plus half of the gust spread above it, made larger on big water, where wind
   * has the fetch to build waves, and smaller on a pond. Rain counts by amount
   * and by chance, and the air by how cold or hot it is.
   *
   * The size cut-offs and factors are the owner's approved numbers (Build 1b
   * plan, decision 9), not measurements. A lake with no published area is
   * treated as medium and says so. */
  var DAYOUT_WEIGHTS = { wind: 0.6, rain: 0.25, air: 0.15 };
  var SIZE_CLASSES_HA = [
    { id: "small", factor: 0.7, label: "small lake" },
    { id: "medium", factor: 1.0, label: "medium lake" },
    { id: "large", factor: 1.3, label: "large lake" },
  ];

  function sizeClass(areaHa) {
    var a = num(areaHa);
    if (a === null || a <= 0) {
      return { id: "medium", factor: 1.0, label: "size unknown", unknown: true };
    }
    // Under 10 ha is small; 10 to 200 ha inclusive is medium; over 200 is large.
    var c = a < 10 ? SIZE_CLASSES_HA[0] : a <= 200 ? SIZE_CLASSES_HA[1] : SIZE_CLASSES_HA[2];
    return { id: c.id, factor: c.factor, label: c.label, unknown: false };
  }

  function dayOutWindScore(effKph) {
    var w = num(effKph);
    if (w === null) return null;
    if (w <= 10) return 1.00;
    if (w <= 20) return 0.80;
    if (w <= 30) return 0.50;
    if (w <= 40) return 0.25;
    return 0.05;
  }

  function dayOutRainScore(mm, chancePct) {
    var p = num(mm), c = num(chancePct);
    if (p === null && c === null) return null;
    var s = 1;
    // Decision 9: only over 2 mm, or a chance over 60%, lowers the score.
    if (p !== null) s = p >= 4 ? 0.30 : p > 2 ? 0.55 : 1;
    if (c !== null && c > 60) s = Math.min(s, 0.70);
    return s;
  }

  function dayOutAirScore(tempC) {
    var t = num(tempC);
    if (t === null) return null;
    if (t < 5) return clamp(1 - (5 - t) * 0.08, 0.2, 1);
    if (t > 28) return clamp(1 - (t - 28) * 0.1, 0.3, 1);
    return 1;
  }

  /** Day out for one stretch of daylight: { windKph, gustKph, precipMm,
   *  precipChancePct, airTempC, areaHa }. Never throws; null parts drop out. */
  function dayOut(input) {
    var o = input || {};
    var size = sizeClass(o.areaHa);
    var wind = num(o.windKph), gust = num(o.gustKph);
    var eff = wind === null ? null
      : (wind + 0.5 * Math.max(0, (gust === null ? wind : gust) - wind)) * size.factor;
    var parts = {
      wind: { s: dayOutWindScore(eff), value: eff === null ? null : Math.round(eff) },
      rain: { s: dayOutRainScore(o.precipMm, o.precipChancePct),
              value: num(o.precipMm), chance: num(o.precipChancePct) },
      air: { s: dayOutAirScore(o.airTempC), value: num(o.airTempC) },
    };
    var numer = 0, denom = 0;
    Object.keys(DAYOUT_WEIGHTS).forEach(function (k) {
      if (parts[k].s === null) return;
      numer += DAYOUT_WEIGHTS[k] * parts[k].s;
      denom += DAYOUT_WEIGHTS[k];
    });
    var score = denom > 0 ? clamp01(numer / denom) : null;
    return {
      score: score,
      band: score === null ? null : bandName(score),
      parts: parts,
      size: size,
      gustWarn: gust !== null && gust >= GUST_WARN_KPH,
      gustKph: gust,
    };
  }

  // ============================================================
  // THE BEST DAY, AND THE COLD
  // ============================================================

  /* The best day is the highest Bite among the days you can actually be out:
   * gusts under the warning and a Day out of Fair or better. A tie goes to the
   * calmer day. Frozen days are never best. Returns -1 when no day qualifies. */
  function bestDay(days) {
    var best = -1;
    (days || []).forEach(function (d, i) {
      if (!d || num(d.bite) === null || d.iced) return;
      if (num(d.gustMax) !== null && d.gustMax >= GUST_WARN_KPH) return;
      if (num(d.dayOut) !== null && d.dayOut < 0.42) return;
      if (best < 0) { best = i; return; }
      var b = days[best];
      if (d.bite > b.bite || (d.bite === b.bite && (num(d.dayOut) || 0) > (num(b.dayOut) || 0))) best = i;
    });
    return best;
  }

  /* Environment Canada's wind chill index, defined for air at or below 10 °C
   * and wind of at least 5 km/h. Outside that the air temperature is the honest
   * answer, so that is what comes back. */
  function windChill(tempC, windKph) {
    var t = num(tempC), v = num(windKph);
    if (t === null) return null;
    if (v === null || t > 10 || v < 5) return t;
    var p = Math.pow(v, 0.16);
    return 13.12 + 0.6215 * t - 11.37 * p + 0.3965 * t * p;
  }

  // ============================================================
  // PLAIN WORDS
  // ============================================================

  /* One line a person can act on, made only from the numbers this app already
   * has. Pressure first because it is the part people ask about, then wind,
   * then the best time if there is one. */
  function dailyTip(day) {
    var d = day || {};
    var bits = [];
    var p = num(d.pressureTrend3h);
    if (p !== null) {
      bits.push(p <= -0.7 ? "Falling pressure: a front is coming, and the bite is often short and strong before it."
        : p >= 0.7 ? "Rising pressure after a front: fish can be slow, so fish deeper and slower."
        : "Steady pressure: fish feed at normal depths.");
    }
    var g = num(d.gustMax);
    if (g !== null && g >= GUST_WARN_KPH) bits.push("Gusts to " + Math.round(g) + " km/h: not a boat day, so fish from shore.");
    else if (num(d.windMean) !== null && d.windMean < 3) bits.push("Flat calm: use a long, light leader.");
    if (d.bestTime) bits.push("Best time: " + d.bestTime + ".");
    return bits.join(" ");
  }

  /* The sun breaking through after a cloudy spell. Anglers report a short bite
   * when that happens; there is no study behind it, so this is a reminder with
   * its source named, and it never touches a score. Looks for the first daylight
   * hour where cloud falls by 40 points or more within three hours, from at
   * least 70%. Hours are { when: Date, cloudPct, sunUp }. */
  function clearingHint(hours) {
    var h = hours || [];
    for (var i = 0; i + 3 < h.length; i++) {
      var a = h[i], b = h[i + 3];
      if (!a || !b || !b.sunUp) continue;
      var ca = num(a.cloudPct), cb = num(b.cloudPct);
      if (ca === null || cb === null) continue;
      if (ca >= 70 && ca - cb >= 40) return { when: b.when, from: ca, to: cb };
    }
    return null;
  }

  window.Conditions = {
    whyParts: whyParts,
    dayOut: dayOut,
    sizeClass: sizeClass,
    bestDay: bestDay,
    windChill: windChill,
    dailyTip: dailyTip,
    clearingHint: clearingHint,
    GUST_WARN_KPH: GUST_WARN_KPH,
    DAYOUT_WEIGHTS: DAYOUT_WEIGHTS,
    scoreSlot: scoreSlot,
    seasonOpenOn: seasonOpenOn,
    seasonOpenAllWinter: seasonOpenAllWinter,
    seasonIceKind: seasonIceKind,
    iceLikely: iceLikely,
    bestOf: bestOf,
    waterFromAir: waterFromAir,
    stratification: stratification,
    bandName: bandName,
    BANDS: BANDS,
    WEIGHTS: WEIGHTS,
    TIERS: TIERS,
    MOON_CAP: MOON_CAP,
    _internal: {
      lightScore: lightScore, waterScore: waterScore, pressureScore: pressureScore,
      windScore: windScore, precipScore: precipScore, leadDecay: leadDecay,
      moonMultiplier: moonMultiplier,
    },
  };
})();
