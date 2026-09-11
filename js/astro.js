/* Where the sun and moon are, computed from the clock alone.
 *
 * Why this exists: almost none of these lakes have usable cell signal, and the
 * best-supported thing we can say about when to fish — that trout feed at dawn
 * and dusk — depends only on the date and a coordinate. So none of this touches
 * the network. A phone in airplane mode at the water can still draw the whole
 * week.
 *
 * Accuracy, and why it is enough: the sun is Meeus chapter 25 (low accuracy),
 * good to about a minute for rise and set at Alberta latitudes. The moon is
 * Meeus chapter 47 truncated to its largest terms, good to roughly 0.05 degrees
 * of longitude, which is about five minutes of transit time. The windows this
 * feeds are one and two hours wide, so five minutes is invisible.
 *
 * The one thing worth guarding carefully: the sun does not rise or set every day
 * everywhere, and the moon skips a rise roughly once a month even here. Inside
 * Alberta the sun always does both — civil twilight only fails to end north of
 * about 60.6 degrees, which is just past the provincial line — but the guards
 * still matter, because a home pin can be dragged anywhere. Those cases are not
 * errors: they must come back as null and as empty arrays, never as a NaN that
 * reaches a score.
 */
(function () {
  "use strict";

  var RAD = Math.PI / 180;
  var DEG = 180 / Math.PI;
  var J2000 = 2451545;
  var DAY_MS = 86400000;
  /* Obliquity of the ecliptic. Fixed: it drifts by well under an arcsecond a
   * year, which is nothing next to our truncation error. */
  var OBLIQUITY = 23.4397 * RAD;

  /* Apparent altitude of the sun's upper limb at rise and set: 34' of
   * refraction plus 16' of semidiameter. */
  var SUN_H0 = -0.833;
  var CIVIL_H0 = -6;
  /* The moon's is different in sign because parallax (57') is larger than
   * refraction and semidiameter together. */
  var MOON_H0 = 0.125;

  function toJulian(date) { return date.getTime() / DAY_MS + 2440587.5; }
  function fromJulian(j) { return new Date((j - 2440587.5) * DAY_MS); }
  function daysSinceJ2000(date) { return toJulian(date) - J2000; }
  function sin(d) { return Math.sin(d * RAD); }
  function cos(d) { return Math.cos(d * RAD); }
  function norm360(d) { return ((d % 360) + 360) % 360; }

  // ============================================================
  // SUN
  // ============================================================

  /** Geometric solar longitude and declination, Meeus ch. 25 low accuracy. */
  function sunEcliptic(d) {
    var M = norm360(357.5291 + 0.98560028 * d);          // mean anomaly
    var C = 1.9148 * sin(M) + 0.0200 * sin(2 * M) + 0.0003 * sin(3 * M);
    var L = norm360(M + C + 102.9372 + 180);             // true longitude
    return { M: M, L: L };
  }

  function declinationOf(lonDeg, latDeg) {
    return Math.asin(
      Math.sin(latDeg * RAD) * Math.cos(OBLIQUITY) +
      Math.cos(latDeg * RAD) * Math.sin(OBLIQUITY) * sin(lonDeg)
    ) * DEG;
  }

  function rightAscensionOf(lonDeg, latDeg) {
    return Math.atan2(
      sin(lonDeg) * Math.cos(OBLIQUITY) - Math.tan(latDeg * RAD) * Math.sin(OBLIQUITY),
      cos(lonDeg)
    ) * DEG;
  }

  /** Greenwich mean sidereal time, degrees. Good to about a second over decades. */
  function siderealTime(d, lonEastDeg) {
    return norm360(280.16 + 360.9856235 * d) + lonEastDeg;
  }

  function altitudeOf(haDeg, latDeg, decDeg) {
    return Math.asin(
      sin(latDeg) * sin(decDeg) + cos(latDeg) * cos(decDeg) * cos(haDeg)
    ) * DEG;
  }

  function sunPosition(date, lat, lon) {
    var d = daysSinceJ2000(date);
    var ec = sunEcliptic(d);
    var dec = declinationOf(ec.L, 0);
    var ra = rightAscensionOf(ec.L, 0);
    var ha = siderealTime(d, lon) - ra;
    return { altitude: altitudeOf(ha, lat, dec), declination: dec, longitude: ec.L };
  }

  /* Solar noon and the two times either side of it when the sun crosses a given
   * altitude. Returns nulls rather than NaN when the sun never gets there, which
   * at 56-60 degrees north happens for weeks around each solstice. */
  function sunTimes(date, lat, lon) {
    var lw = -lon;
    var d = daysSinceJ2000(date);
    var n = Math.round(d - 0.0009 - lw / 360);
    var ds = 0.0009 + lw / 360 + n;
    var ec = sunEcliptic(ds);
    var dec = declinationOf(ec.L, 0);
    var jNoon = J2000 + ds + 0.0053 * sin(ec.M) - 0.0069 * sin(2 * ec.L);

    function crossing(h0) {
      var cosW = (sin(h0) - sin(lat) * sin(dec)) / (cos(lat) * cos(dec));
      // Outside [-1, 1] means the sun never reaches this altitude today.
      if (!(cosW >= -1 && cosW <= 1)) return null;
      var w = Math.acos(cosW) * DEG;
      var jSet = J2000 + (0.0009 + (w + lw) / 360 + n) +
                 0.0053 * sin(ec.M) - 0.0069 * sin(2 * ec.L);
      return { rise: fromJulian(jNoon - (jSet - jNoon)), set: fromJulian(jSet) };
    }

    var day = crossing(SUN_H0);
    var civil = crossing(CIVIL_H0);
    return {
      solarNoon: fromJulian(jNoon),
      sunrise: day ? day.rise : null,
      sunset: day ? day.set : null,
      civilDawn: civil ? civil.rise : null,
      civilDusk: civil ? civil.set : null,
      /* True when the sun stays up, false when it stays down, null when it does
       * rise and set normally. The caller needs to tell those apart. */
      alwaysUp: day ? null : sunPosition(fromJulian(jNoon), lat, lon).altitude > SUN_H0,
    };
  }

  // ============================================================
  // MOON
  // ============================================================

  /* Meeus ch. 47, truncated. The three-term version everyone copies gives the
   * longitude to only about 0.3 degrees, and the moon moves 0.55 degrees an
   * hour — half an hour of transit error, which is a third of a major period.
   * These ten terms cost about twenty lines and buy back that half hour. */
  function moonEcliptic(d) {
    var T = d / 36525;
    var Lp = norm360(218.3164477 + 481267.88123421 * T);  // mean longitude
    var D  = norm360(297.8501921 + 445267.1114034 * T);   // mean elongation
    var M  = norm360(357.5291092 + 35999.0502909 * T);    // sun's mean anomaly
    var Mp = norm360(134.9633964 + 477198.8675055 * T);   // moon's mean anomaly
    var F  = norm360(93.2720950 + 483202.0175233 * T);    // argument of latitude

    var lon = Lp
      + 6.288774 * sin(Mp)
      + 1.274027 * sin(2 * D - Mp)
      + 0.658314 * sin(2 * D)
      + 0.213618 * sin(2 * Mp)
      - 0.185116 * sin(M)
      - 0.114332 * sin(2 * F)
      + 0.058793 * sin(2 * D - 2 * Mp)
      + 0.057066 * sin(2 * D - M - Mp)
      + 0.053322 * sin(2 * D + Mp)
      + 0.045758 * sin(2 * D - M);

    var lat = 5.128122 * sin(F)
      + 0.280602 * sin(Mp + F)
      + 0.277693 * sin(Mp - F)
      - 0.173237 * sin(2 * D - F)
      + 0.055413 * sin(2 * D - Mp + F)
      + 0.046271 * sin(2 * D - Mp - F)
      + 0.032573 * sin(2 * D + F)
      + 0.017198 * sin(2 * Mp + F);

    var distKm = 385000.56
      - 20905.355 * cos(Mp)
      - 3699.111 * cos(2 * D - Mp)
      - 2955.968 * cos(2 * D)
      - 569.925 * cos(2 * Mp);

    return { longitude: norm360(lon), latitude: lat, distanceKm: distKm };
  }

  function moonPosition(date, lat, lon) {
    var d = daysSinceJ2000(date);
    var ec = moonEcliptic(d);
    var dec = declinationOf(ec.longitude, ec.latitude);
    var ra = rightAscensionOf(ec.longitude, ec.latitude);
    var ha = siderealTime(d, lon) - ra;
    return {
      altitude: altitudeOf(ha, lat, dec),
      declination: dec,
      distanceKm: ec.distanceKm,
      longitude: ec.longitude,
    };
  }

  /** Illuminated fraction and where we are in the 29.5-day cycle.
   *  phase 0 = new, 0.25 = first quarter, 0.5 = full, 0.75 = last quarter. */
  function moonPhase(date) {
    var d = daysSinceJ2000(date);
    var elong = norm360(moonEcliptic(d).longitude - sunEcliptic(d).L);
    return {
      phase: elong / 360,
      illumination: (1 - cos(elong)) / 2,
      elongation: elong,
      name: phaseName(elong / 360),
    };
  }

  function phaseName(p) {
    if (p < 0.03 || p >= 0.97) return "new moon";
    if (p < 0.22) return "waxing crescent";
    if (p < 0.28) return "first quarter";
    if (p < 0.47) return "waxing gibbous";
    if (p < 0.53) return "full moon";
    if (p < 0.72) return "waning gibbous";
    if (p < 0.78) return "last quarter";
    return "waning crescent";
  }

  /* Finding rise, set and transit means finding where a smooth curve crosses a
   * level and where it turns over. Both are done by sampling the real altitude
   * every half hour and then refining, rather than by fitting one parabola per
   * two-hour block the way the textbook scan does.
   *
   * That choice is not fussiness. Tiled two-hour windows share their edges, and
   * an extremum that lands on a join belongs to the interior of neither window,
   * so it is missed by both — a real moon minimum at exactly midday disappeared
   * this way. A two-hour parabola is also too coarse near a sharp peak: at sixty
   * degrees of altitude it put transit four minutes out. Sampling finely and
   * refining costs a few dozen extra trig evaluations per day and removes both
   * failure modes.
   */
  var SCAN_STEP_MIN = 30;

  /** Bisect for the instant a curve crosses level, given a bracketing pair. */
  function refineCrossing(f, tLo, tHi, level) {
    var lo = tLo, hi = tHi;
    for (var i = 0; i < 24; i++) {          // 30 min -> well under a second
      var mid = (lo + hi) / 2;
      if ((f(lo) - level) * (f(mid) - level) <= 0) hi = mid; else lo = mid;
    }
    return new Date(Math.round((lo + hi) / 2));
  }

  /* Refine a turning point by fitting a parabola through three samples and
   * stepping to its vertex, then shrinking the spacing and repeating. Converges
   * quadratically, so three passes land inside a second. */
  function refineExtremum(f, tGuess, halfWidthMs) {
    var t = tGuess, h = halfWidthMs;
    for (var i = 0; i < 4; i++) {
      var ym = f(t - h), yz = f(t), yp = f(t + h);
      var a = 0.5 * (ym + yp) - yz;
      var b = 0.5 * (yp - ym);
      if (a !== 0) {
        var shift = (-b / (2 * a)) * h;
        // A vertex further than the bracket means the samples were not yet
        // straddling the turn; step to the edge instead of leaping past it.
        if (shift > h) shift = h;
        if (shift < -h) shift = -h;
        t = t + shift;
      }
      h = h / 4;
    }
    return { at: new Date(Math.round(t)), altitude: f(t) };
  }

  /* Scan a local day and pick out every horizon crossing and every turning
   * point. Arrays, not single values, because the moon transits every 24h50m:
   * some local days get two transits and some get none. Treating either as "the"
   * transit is how a solunar table ends up an hour wrong. */
  function moonTimes(dayStart, lat, lon) {
    var t0 = dayStart.getTime();
    var stepMs = SCAN_STEP_MIN * 60000;
    var n = Math.round(24 * 60 / SCAN_STEP_MIN);
    var altAt = function (ms) {
      return moonPosition(new Date(ms), lat, lon).altitude;
    };

    var samples = [];
    for (var i = 0; i <= n; i++) samples.push(altAt(t0 + i * stepMs));

    var rises = [], sets = [], transits = [], antiTransits = [];

    for (var k = 0; k < n; k++) {
      var a0 = samples[k] - MOON_H0, a1 = samples[k + 1] - MOON_H0;
      if (a0 === 0 || (a0 < 0) !== (a1 < 0)) {
        var when = refineCrossing(altAt, t0 + k * stepMs, t0 + (k + 1) * stepMs, MOON_H0);
        (a1 > a0 ? rises : sets).push(when);
      }
    }

    // Interior turning points only: a day that merely starts high is the tail of
    // yesterday's transit, not one of today's.
    for (var j = 1; j < n; j++) {
      var pm = samples[j - 1], pz = samples[j], pp = samples[j + 1];
      if (pz >= pm && pz >= pp && !(pm === pz && pz === pp)) {
        transits.push(refineExtremum(altAt, t0 + j * stepMs, stepMs));
      } else if (pz <= pm && pz <= pp && !(pm === pz && pz === pp)) {
        antiTransits.push(refineExtremum(altAt, t0 + j * stepMs, stepMs));
      }
    }

    return { rises: rises, sets: sets, transits: transits, antiTransits: antiTransits };
  }

  // ============================================================
  // SOLUNAR PERIODS
  // ============================================================

  /* Majors centre on the moon overhead and underfoot, minors on moonrise and
   * moonset. This is pure geometry and has nothing to do with light, which is
   * why it comes back as its own list: the caller must keep it apart from the
   * dawn and dusk peaks rather than adding the two together. A major landing at
   * three in the afternoon is a fact about where the moon is, not a claim that
   * the fish ignored sunrise.
   *
   * The moon transits fifty minutes later each day, so over a month these sweep
   * every hour of the clock. Near new and full moon they sit close to noon and
   * midnight; near the quarters they sit close to dawn and dusk. */
  var MAJOR_HALF_MS = 60 * 60000;
  var MINOR_HALF_MS = 30 * 60000;

  function periods(dayStart, lat, lon) {
    var t = moonTimes(dayStart, lat, lon);
    var out = [];
    function push(kind, when, halfMs, label) {
      if (!when) return;
      out.push({
        kind: kind,
        label: label,
        centre: when,
        start: new Date(when.getTime() - halfMs),
        end: new Date(when.getTime() + halfMs),
      });
    }
    t.transits.forEach(function (x) { push("major", x.at, MAJOR_HALF_MS, "moon overhead"); });
    t.antiTransits.forEach(function (x) { push("major", x.at, MAJOR_HALF_MS, "moon underfoot"); });
    t.rises.forEach(function (x) { push("minor", x, MINOR_HALF_MS, "moonrise"); });
    t.sets.forEach(function (x) { push("minor", x, MINOR_HALF_MS, "moonset"); });
    out.sort(function (a, b) { return a.centre - b.centre; });
    return out;
  }

  /** Which period, if any, contains an instant. Majors win ties. */
  function periodAt(when, list) {
    var found = null;
    for (var i = 0; i < list.length; i++) {
      var p = list[i];
      if (when >= p.start && when <= p.end) {
        if (p.kind === "major") return p;
        if (!found) found = p;
      }
    }
    return found;
  }

  /* Everything one lake needs for one day, computed once and handed to the
   * scorer for every slot in that day. */
  function dayFor(lat, lon, dayStart) {
    var noonish = new Date(dayStart.getTime() + 12 * 3600000);
    return {
      dayStart: dayStart,
      lat: lat,
      lon: lon,
      sun: sunTimes(noonish, lat, lon),
      moon: moonPhase(noonish),
      moonTimes: moonTimes(dayStart, lat, lon),
      periods: periods(dayStart, lat, lon),
    };
  }

  /** Minutes to the nearest of civil dawn, sunrise, sunset, civil dusk.
   *  Null when the sun neither rises nor sets, which the light score treats as
   *  "no crepuscular peak today" rather than as an error. */
  function minutesToNearestEdge(when, sun) {
    var edges = [sun.civilDawn, sun.sunrise, sun.sunset, sun.civilDusk]
      .filter(function (e) { return e instanceof Date && !isNaN(e); });
    if (!edges.length) return null;
    var best = Infinity;
    edges.forEach(function (e) {
      var m = Math.abs(when - e) / 60000;
      if (m < best) best = m;
    });
    return best;
  }

  window.Astro = {
    sunPosition: sunPosition,
    sunTimes: sunTimes,
    moonPosition: moonPosition,
    moonPhase: moonPhase,
    moonTimes: moonTimes,
    periods: periods,
    periodAt: periodAt,
    dayFor: dayFor,
    minutesToNearestEdge: minutesToNearestEdge,
    _internal: { toJulian: toJulian, fromJulian: fromJulian, moonEcliptic: moonEcliptic },
  };
})();
