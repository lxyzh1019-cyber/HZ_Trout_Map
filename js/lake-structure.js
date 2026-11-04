/* The shape of a lakebed, read from its depth grid: islands, points, humps,
 * basins, drop-offs and flats, plus the shoreline facts the spot finder and
 * the 3D model share.
 *
 * Pure functions on a grid object, no page and no 3D library, so the tests
 * run them in node:
 *
 *   grid = { w, h, cell,            cells across, down, and metres per cell
 *            depth: Float32Array }  per cell, row 0 is north: > 0 water depth
 *                                   in metres, <= 0 land
 *
 *   LakeStructure.fromInt16(meta, int16)  the grid from a data/depth_grids file
 *   LakeStructure.find(grid)              { labels, dropCells, shore, slopeCut }
 *   LakeStructure.contour(grid, depth)    segments of one depth line
 *
 * Every label is an estimate from the survey's lakebed. Each one carries a
 * reason in plain words, shown when it is tapped.
 */
(function () {
  "use strict";

  var NODATA = -32768;

  function fromInt16(meta, cells) {
    var n = meta.w * meta.h;
    var depth = new Float32Array(n), land = new Float32Array(n);
    for (var k = 0; k < n; k++) {
      var v = cells[k];
      if (v > 0) depth[k] = v / 10;
      else { depth[k] = 0; land[k] = v === NODATA ? NaN : -v / 10; }
    }
    return { w: meta.w, h: meta.h, cell: meta.cell_m, depth: depth, landHeight: land };
  }

  function cellsFor(grid, metres, min) {
    return Math.max(min || 1, Math.round(metres / grid.cell));
  }

  function water(grid, i, j) {
    return i >= 0 && j >= 0 && i < grid.w && j < grid.h && grid.depth[j * grid.w + i] > 0;
  }

  function depthAt(grid, i, j) {
    return water(grid, i, j) ? grid.depth[j * grid.w + i] : 0;
  }

  /* Land reachable from the grid edge is the mainland; any other land is an
   * island. */
  function mainland(grid) {
    var w = grid.w, h = grid.h, main = new Uint8Array(w * h), stack = [];
    for (var i = 0; i < w; i++) stack.push(i, (h - 1) * w + i);
    for (var j = 0; j < h; j++) stack.push(j * w, j * w + w - 1);
    while (stack.length) {
      var k = stack.pop();
      if (main[k] || grid.depth[k] > 0) continue;
      main[k] = 1;
      var x = k % w, y = (k - x) / w;
      if (x > 0) stack.push(k - 1);
      if (x < w - 1) stack.push(k + 1);
      if (y > 0) stack.push(k - w);
      if (y < h - 1) stack.push(k + w);
    }
    return main;
  }

  /** Every water cell next to land, with the direction it faces (east, north
   *  as a unit vector pointing out of the water), whether it is on a point,
   *  and the deepest water within a 30 m cast. */
  function shoreCells(grid) {
    var w = grid.w, out = [];
    var r = cellsFor(grid, 30, 1), win = cellsFor(grid, 36, 2);
    for (var j = 1; j < grid.h - 1; j++) {
      for (var i = 1; i < w - 1; i++) {
        if (!water(grid, i, j)) continue;
        var nx = 0, ny = 0, l = 0;
        if (!water(grid, i + 1, j)) { nx += 1; l++; }
        if (!water(grid, i - 1, j)) { nx -= 1; l++; }
        if (!water(grid, i, j - 1)) { ny += 1; l++; }
        if (!water(grid, i, j + 1)) { ny -= 1; l++; }
        if (!l) continue;
        var len = Math.hypot(nx, ny);
        if (!len) continue;
        var landN = 0, all = 0, reach = grid.depth[j * w + i];
        for (var b = -win; b <= win; b++) {
          for (var a = -win; a <= win; a++) {
            all++;
            if (!water(grid, i + a, j + b)) landN++;
            if (a * a + b * b <= r * r) reach = Math.max(reach, depthAt(grid, i + a, j + b));
          }
        }
        out.push({ i: i, j: j, k: j * w + i, z: grid.depth[j * w + i], nx: nx / len, ny: ny / len,
                   point: landN / all < 0.37, reach: reach, reachM: Math.max(30, Math.round(r * grid.cell)) });
      }
    }
    return out;
  }

  function slopes(grid) {
    var w = grid.w, s = new Float32Array(w * grid.h), list = [];
    for (var j = 2; j < grid.h - 2; j++) {
      for (var i = 2; i < w - 2; i++) {
        var k = j * w + i, z = grid.depth[k];
        if (z <= 0) continue;
        var m = 0;
        [k + 2, k - 2, k + 2 * w, k - 2 * w].forEach(function (t) {
          if (grid.depth[t] > 0) m = Math.max(m, Math.abs(grid.depth[t] - z));
        });
        s[k] = m / (2 * grid.cell);
        list.push(s[k]);
      }
    }
    list.sort(function (a, b) { return a - b; });
    // The steepest 6 % of this lakebed, but never a slope gentler than 1 m in 40 m.
    var cut = Math.max(list.length ? list[Math.floor(list.length * 0.94)] : 0, 0.025);
    return { slope: s, cut: cut };
  }

  function farEnough(list, c, metres, cell) {
    return list.every(function (o) { return Math.hypot(o.i - c.i, o.j - c.j) * cell >= metres; });
  }

  function find(grid) {
    var w = grid.w, h = grid.h, n = w * h, labels = [];
    var main = mainland(grid);

    // Islands: land that is not the mainland.
    var seen = new Uint8Array(n);
    for (var k0 = 0; k0 < n; k0++) {
      if (grid.depth[k0] > 0 || main[k0] || seen[k0]) continue;
      var q = [k0], si = 0, sj = 0, cnt = 0;
      seen[k0] = 1;
      while (q.length) {
        var c = q.pop(), x = c % w, y = (c - x) / w;
        si += x; sj += y; cnt++;
        [c + 1, c - 1, c + w, c - w].forEach(function (t) {
          if (t >= 0 && t < n && !seen[t] && grid.depth[t] <= 0 && !main[t]) { seen[t] = 1; q.push(t); }
        });
      }
      if (cnt * grid.cell * grid.cell < 50) continue;   // a single noisy cell is not an island
      labels.push({ kind: "island", name: "Island", i: Math.round(si / cnt), j: Math.round(sj / cnt),
                    why: "Island: land in the lake. Fish its shallow edges and the drop beside it." });
    }

    var shore = shoreCells(grid);

    // Point: the mainland shore with the least land around it.
    var win = cellsFor(grid, 60, 3), best = null;
    for (var j = win; j < h - win; j++) {
      for (var i = win; i < w - win; i++) {
        if (!main[j * w + i]) continue;
        var landN = 0, wet = 0;
        for (var b = -win; b <= win; b++) for (var a = -win; a <= win; a++) {
          if (grid.depth[(j + b) * w + i + a] > 0) wet++; else landN++;
        }
        var share = landN / (landN + wet);
        if (wet > 0 && share < 0.42 && (!best || share < best.share)) best = { share: share, i: i, j: j };
      }
    }
    if (best) labels.push({ kind: "point", name: "Point", i: best.i, j: best.j,
                            why: "Point: land that reaches into the lake. Wind and fish both swing around its tip." });

    // Basins and humps: the deepest and the highest spots in their surroundings.
    var R = cellsFor(grid, 100, 3), cand = [];
    for (var jj = R; jj < h - R; jj++) {
      for (var ii = R; ii < w - R; ii++) {
        var z = grid.depth[jj * w + ii];
        if (z <= 0) continue;
        var mx = -1, mn = 1e9, landR = 0;
        for (var bb = -R; bb <= R; bb++) for (var aa = -R; aa <= R; aa++) {
          if (aa * aa + bb * bb > R * R) continue;
          var v = grid.depth[(jj + bb) * w + ii + aa];
          if (v <= 0) { landR++; continue; }
          if (v > mx) mx = v;
          if (v < mn) mn = v;
        }
        if (z >= mx && z >= 4) cand.push({ kind: "basin", i: ii, j: jj, z: z, score: z });
        if (!landR && z <= mn && mx - z >= 2.5) cand.push({ kind: "hump", i: ii, j: jj, z: z, mx: mx, score: mx - z });
      }
    }
    cand.sort(function (a, b) { return b.score - a.score; });
    var kept = [];
    cand.forEach(function (c) {
      var same = kept.filter(function (o) { return o.kind === c.kind; });
      // Spaced within its own kind only: a hump beside a basin is the point.
      if (same.length < 2 && farEnough(same, c, 300, grid.cell)) kept.push(c);
    });
    kept.forEach(function (c) {
      labels.push(c.kind === "basin"
        ? { kind: "basin", name: "Basin " + c.z.toFixed(0) + " m", i: c.i, j: c.j,
            why: "Basin: the deepest hole here, " + c.z.toFixed(1) + " m. Trout hold near basins in summer heat and in mid-winter." }
        : { kind: "hump", name: "Hump " + c.z.toFixed(1) + " m", i: c.i, j: c.j,
            why: "Hump: the lakebed rises to " + c.z.toFixed(1) + " m with " + c.mx.toFixed(0) + " m of water around it. Fish its top edge." });
    });

    // Drop-offs: the steepest part of this lakebed.
    var sl = slopes(grid), dropCells = [], top = -1;
    for (var k = 0; k < n; k++) {
      if (grid.depth[k] > 0 && sl.slope[k] >= sl.cut) {
        dropCells.push(k);
        if (top < 0 || sl.slope[k] > sl.slope[top]) top = k;
      }
    }
    if (top >= 0) {
      var ti = top % w, tj = (top - ti) / w, lo = 1e9, hi = 0, rr = cellsFor(grid, 25, 1);
      for (var y2 = -rr; y2 <= rr; y2++) for (var x2 = -rr; x2 <= rr; x2++) {
        if (water(grid, ti + x2, tj + y2)) { var d2 = depthAt(grid, ti + x2, tj + y2); lo = Math.min(lo, d2); hi = Math.max(hi, d2); }
      }
      labels.push({ kind: "drop", name: "Drop-off", i: ti, j: tj,
                    why: "Drop-off: the steepest slope here, " + lo.toFixed(0) + " m to " + hi.toFixed(0) + " m within about "
                      + Math.round(2 * rr * grid.cell) + " m. A good edge to cast along." });
    }

    // Flat: the widest shallow shelf.
    var flat = new Uint8Array(n);
    for (var kf = 0; kf < n; kf++) if (grid.depth[kf] >= 0.5 && grid.depth[kf] <= 3 && sl.slope[kf] < sl.cut * 0.5) flat[kf] = 1;
    var done = new Uint8Array(n), big = null;
    for (var ks = 0; ks < n; ks++) {
      if (!flat[ks] || done[ks]) continue;
      var st = [ks], cells = [];
      done[ks] = 1;
      while (st.length) {
        var cc = st.pop();
        cells.push(cc);
        var cx = cc % w;
        [cx > 0 ? cc - 1 : -1, cx < w - 1 ? cc + 1 : -1, cc - w, cc + w].forEach(function (t) {
          if (t >= 0 && t < n && flat[t] && !done[t]) { done[t] = 1; st.push(t); }
        });
      }
      if (!big || cells.length > big.length) big = cells;
    }
    if (big && big.length * grid.cell * grid.cell > 20000) {
      var mi = 0, mj = 0;
      big.forEach(function (c) { mi += c % w; mj += Math.floor(c / w); });
      mi /= big.length; mj /= big.length;
      var bc = big[0], bd = 1e18;
      big.forEach(function (c) { var d = Math.pow(c % w - mi, 2) + Math.pow(Math.floor(c / w) - mj, 2); if (d < bd) { bd = d; bc = c; } });
      labels.push({ kind: "flat", name: "Flat 1–3 m", i: bc % w, j: Math.floor(bc / w),
                    why: "Flat: a wide shallow shelf, " + (big.length * grid.cell * grid.cell / 10000).toFixed(1)
                      + " ha at 1–3 m. Weeds and bugs grow here; best at dawn, dusk and in spring." });
    }

    return { labels: labels, dropCells: dropCells, shore: shore, slopeCut: sl.cut };
  }

  /** One depth line by marching squares: a flat list x1, y1, x2, y2, … in
   *  cell units (x east, y south). Cells touching land are skipped. */
  function contour(grid, level) {
    var w = grid.w, out = [];
    var C = [[0, 0], [1, 0], [1, 1], [0, 1]];
    for (var j = 0; j < grid.h - 1; j++) {
      for (var i = 0; i < w - 1; i++) {
        var c = [grid.depth[j * w + i], grid.depth[j * w + i + 1], grid.depth[(j + 1) * w + i + 1], grid.depth[(j + 1) * w + i]];
        if (c[0] <= 0 || c[1] <= 0 || c[2] <= 0 || c[3] <= 0) continue;
        var lo = c.map(function (v) { return v < level; });
        if (lo[0] === lo[1] && lo[1] === lo[2] && lo[2] === lo[3]) continue;
        var e = [];
        for (var k = 0; k < 4; k++) {
          var a = c[k], b = c[(k + 1) % 4];
          if ((a < level) !== (b < level)) {
            var t = (level - a) / (b - a), A = C[k], B = C[(k + 1) % 4];
            e.push(i + A[0] + (B[0] - A[0]) * t, j + A[1] + (B[1] - A[1]) * t);
          }
        }
        if (e.length >= 4) out.push(e[0], e[1], e[2], e[3]);
        if (e.length === 8) out.push(e[4], e[5], e[6], e[7]);
      }
    }
    return out;
  }

  window.LakeStructure = {
    NODATA: NODATA,
    fromInt16: fromInt16,
    find: find,
    contour: contour,
    shoreCells: shoreCells,
    _internal: { mainland: mainland, slopes: slopes },
  };
})();
