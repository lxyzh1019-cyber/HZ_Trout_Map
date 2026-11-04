/* Possible spots on a lake with a depth grid, by how you can fish it:
 * from the shore (a 30 m cast), from a boat (a trolling route), or on the ice.
 * Plus the shoreline layers that depend on the hour: calm shore, sun and
 * shade shore.
 *
 * Pure functions on the grid and shoreline from js/lake-structure.js; no page
 * and no 3D library, so the tests run them in node. Bearings here are GRID
 * bearings (clockwise from grid up); the 3D view turns a true bearing into a
 * grid bearing with the grid's north_deg. Every spot is an estimate and says
 * why it was picked.
 */
(function () {
  "use strict";

  var CALM_KPH = 8;
  var SPACING_M = 150;
  var CAST_M = 30;

  function vec(bearing) {
    var r = bearing * Math.PI / 180;
    return { x: Math.sin(r), y: Math.cos(r) };   // east, north
  }

  function water(grid, i, j) {
    return i >= 0 && j >= 0 && i < grid.w && j < grid.h && grid.depth[j * grid.w + i] > 0;
  }

  function spaced(list, n, metres, cell) {
    var out = [];
    for (var a = 0; a < list.length && out.length < n; a++) {
      var p = list[a];
      if (out.every(function (q) { return Math.hypot(q.i - p.i, q.j - p.j) * cell >= metres; })) out.push(p);
    }
    return out;
  }

  /* Open water behind a shore cell, measured against the wind. */
  function fetchM(grid, s, w) {
    var f = 0, x = s.i, y = s.j;
    while (f < 8000) {
      x -= w.x; y += w.y;                        // one cell upwind (y runs south)
      if (!water(grid, Math.round(x), Math.round(y))) break;
      f += grid.cell;
    }
    return f;
  }

  /** Up to 3 shore spots: water 3 m or deeper within a 30 m cast. With wind,
   *  the shore must face the wind's push; more open water behind it scores
   *  higher. */
  function shoreSpots(grid, shore, bearingTo, kph) {
    var windy = kph != null && kph >= CALM_KPH && bearingTo != null;
    var w = windy ? vec(bearingTo) : null, c = [];
    shore.forEach(function (s) {
      if (s.reach < 3) return;
      var drop = s.reach - s.z, score = Math.min(1, drop / 5) * (s.point ? 1.2 : 1), f = 0;
      if (windy) {
        var dot = s.nx * w.x + s.ny * w.y;
        if (dot <= 0.3) return;
        f = fetchM(grid, s, w);
        score *= Math.min(1, f / 1500) * (0.6 + 0.4 * dot);
      }
      c.push({ i: s.i, j: s.j, z: s.z, reach: s.reach, reachM: s.reachM || CAST_M, point: s.point, fetch: f, score: score });
    });
    c.sort(function (a, b) { return b.score - a.score; });
    return spaced(c, 3, SPACING_M, grid.cell).map(function (p, n) {
      return {
        kind: "shore", name: "Shore spot " + (n + 1), i: p.i, j: p.j,
        why: "Shore spot " + (n + 1) + " (estimate): " + (p.reachM <= CAST_M
            ? "stand here and cast " + CAST_M + " m to " + p.reach.toFixed(1) + " m water"
            : "water " + p.reach.toFixed(1) + " m deep within about " + p.reachM + " m of this shore (this big lake's grid is coarse)")
          + (windy ? "; the wind pushes food to this shore over " + (p.fetch / 1000).toFixed(1) + " km of open water" : "")
          + (p.point ? "; on a point." : "."),
      };
    });
  }

  /** The depth a trolling route follows: 5 m, or less on a shallow lake. */
  function trollDepth(maxDepth) {
    return maxDepth >= 7 ? 5 : Math.max(1.5, Math.round(maxDepth * 0.6 * 2) / 2);
  }

  /** Segments of the trolling line (cell units, from LakeStructure.contour),
   *  only on the downwind half of the lake when there is wind. */
  function trollingRoute(grid, segments, bearingTo, kph) {
    var windy = kph != null && kph >= CALM_KPH && bearingTo != null;
    if (!windy) return { segments: segments, downwind: false };
    var w = vec(bearingTo), cx = 0, cy = 0, n = 0;
    for (var k = 0; k < grid.depth.length; k++) {
      if (grid.depth[k] > 0) { cx += k % grid.w; cy += Math.floor(k / grid.w); n++; }
    }
    cx /= n || 1; cy /= n || 1;
    var out = [];
    for (var s = 0; s < segments.length; s += 4) {
      var mx = (segments[s] + segments[s + 2]) / 2, my = (segments[s + 1] + segments[s + 3]) / 2;
      if ((mx - cx) * w.x + (cy - my) * w.y > 0) out.push(segments[s], segments[s + 1], segments[s + 2], segments[s + 3]);
    }
    return { segments: out, downwind: true };
  }

  /** Up to 3 ice spots: 1.5–4 m water within about 60 m of a drop-off,
   *  scored by the size of the drop, at least 150 m from the aerator. */
  function iceSpots(grid, dropCells, aerator) {
    var w = grid.w, n = w * grid.h, dist = new Int32Array(n).fill(-1), q = new Int32Array(n), h = 0, t = 0;
    dropCells.forEach(function (k) { dist[k] = 0; q[t++] = k; });
    var maxSteps = Math.max(1, Math.round(60 / grid.cell));
    while (h < t) {
      var k = q[h++];
      if (dist[k] >= maxSteps) continue;
      var x = k % w;
      [x > 0 ? k - 1 : -1, x < w - 1 ? k + 1 : -1, k - w, k + w].forEach(function (m) {
        if (m >= 0 && m < n && dist[m] < 0 && grid.depth[m] > 0) { dist[m] = dist[k] + 1; q[t++] = m; }
      });
    }
    var r = Math.max(1, Math.round(60 / grid.cell)), c = [];
    for (var kk = 0; kk < n; kk++) {
      var z = grid.depth[kk];
      if (z < 1.5 || z > 4 || dist[kk] < 0) continue;
      var i = kk % w, j = (kk - i) / w;
      if (aerator && Math.hypot(i - aerator.i, j - aerator.j) * grid.cell < 150) continue;
      var mx = z;
      for (var b = -r; b <= r; b++) for (var a = -r; a <= r; a++) {
        if (water(grid, i + a, j + b)) mx = Math.max(mx, grid.depth[(j + b) * w + i + a]);
      }
      c.push({ i: i, j: j, z: z, mx: mx, score: (mx - z) * (1 - dist[kk] / (maxSteps + 1)) });
    }
    c.sort(function (a, b) { return b.score - a.score; });
    return spaced(c, 3, SPACING_M, grid.cell).map(function (p, m) {
      return {
        kind: "ice", name: "Ice spot " + (m + 1), i: p.i, j: p.j,
        why: "Ice spot " + (m + 1) + " (estimate): " + p.z.toFixed(1) + " m, next to a drop to " + p.mx.toFixed(0)
          + " m within about " + Math.max(60, Math.round(r * grid.cell)) + " m. Check the ice thickness before you walk out.",
      };
    });
  }

  /** Shore the wind blows away from: flat water. */
  function calmShore(shore, bearingTo, kph) {
    if (kph == null || kph < CALM_KPH || bearingTo == null) return [];
    var w = vec(bearingTo);
    return shore.filter(function (s) { return s.nx * w.x + s.ny * w.y < -0.5; });
  }

  /** Shade shore faces the sun (its bank shades the water); sunny shore is
   *  the far side. Nothing while the sun is down. */
  function sunShore(shore, sunAzGrid, sunAlt) {
    if (sunAlt == null || sunAlt <= 0) return { shade: [], sun: [] };
    var s = vec(sunAzGrid);
    return {
      shade: shore.filter(function (c) { return c.nx * s.x + c.ny * s.y > 0.5; }),
      sun: shore.filter(function (c) { return c.nx * s.x + c.ny * s.y < -0.5; }),
    };
  }

  function castReach(shore) {
    return shore.filter(function (s) { return s.reach >= 4; });
  }

  /** The boating rule in plain words, for the trolling route. */
  function boatingText(rule, hasLaunch) {
    var r = rule || {}, parts = [];
    if (r.no_boats) parts.push("No boats on this lake.");
    else if (r.motor === "none") parts.push("Paddle, canoe or float tube only: no motors.");
    else if (r.motor === "electric") parts.push("Electric motors only" + (r.kw_max ? " (up to " + r.kw_max + " kW)" : "") + ".");
    else if (r.motor === "allowed") parts.push("Motors allowed.");
    else parts.push("No motor rule found in the Transport Canada list or on MyWildAlberta. Check the boating rules.");
    if (r.speed_kmh) parts.push("Speed limit " + r.speed_kmh + " km/h.");
    if (r.speed_kmh_signed) parts.push(r.speed_kmh_signed + " km/h where signs say so.");
    if (r.signed_no_boat_zones) parts.push("No boats in signed areas, often swimming areas.");
    if (r.no_towing) parts.push("No towing (skis, tubes).");
    parts.push("On every Alberta lake: 10 km/h within 30 m of shore (Vessel Operation Restriction Regulations, s. 2(7); towing straight out from shore is excepted, s. 2(8)).");
    if (r.differs && r.mywildalberta === "none" && r.motor === "electric") {
      parts.push("MyWildAlberta says no motors; the Transport Canada list allows electric motors. The law is the Transport Canada list.");
    }
    parts.push(hasLaunch ? "Boat launch listed." : "No boat launch listed: use a car-top boat, canoe or float tube.");
    var src = (r.sources || []).join("; ");
    if (src) parts.push("Source: " + src + (src.indexOf("Transport Canada") >= 0 ? ", not the official version." : "."));
    return parts.join(" ");
  }

  window.FishingSpots = {
    CALM_KPH: CALM_KPH,
    shoreSpots: shoreSpots,
    trollDepth: trollDepth,
    trollingRoute: trollingRoute,
    iceSpots: iceSpots,
    calmShore: calmShore,
    sunShore: sunShore,
    castReach: castReach,
    boatingText: boatingText,
  };
})();
