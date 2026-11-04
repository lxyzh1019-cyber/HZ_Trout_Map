/* The 3D depth model: one lake's bed, turned freely with a finger, with the
 * wind over it, its structure and the spots you can reach from the shore, by
 * boat or on the ice.
 *
 *   DepthModel.has(lake)    true when the lake has a lakebed grid
 *   DepthModel.open(lake)   full-screen view over the map
 *   DepthModel.close()
 *
 * Data: data/depth_grids/index.json and one .bin per grid (Alberta Geological
 * Survey, see scripts/depth_grids.py), data/boating_rules.json (Transport
 * Canada TP 15587E and MyWildAlberta, see scripts/boating_rules.py). The
 * shapes and spots come from js/lake-structure.js and js/fishing-spots.js;
 * this file only draws them.
 *
 * Smooth on a phone
 * -----------------
 * Nothing is drawn unless something moves. One requestAnimationFrame loop runs
 * while a finger drags, the model glides after it, the zoom eases, Default
 * view slides back, or the wind arrows turn to a new hour; then it stops. The
 * Height slider only rescales one group, so it never rebuilds the lakebed. An
 * hour change rebuilds only the spots and the calm, sun and shade dots.
 *
 * The 3D library (vendor/three.min.js, MIT) loads the first time a model
 * opens, so a visit that never opens one pays nothing for it.
 */
(function () {
  "use strict";

  var ROOT_ID = "depth3d";
  var THREE_SRC = "vendor/three.min.js";
  var SIZE = 4.4;                    // model width in scene units
  var D0 = 6.4;                      // camera distance at the default view
  var LAND_CAP_M = 6;                // land is drawn at most this high
  var LAYERS_ON = ["wind", "spots", "struct", "drop"];
  var LAYERS_OFF = ["weed", "summer", "cast", "calm", "sun", "rep", "ice"];
  var LAYER_INFO = {
    wind: ["Wind arrows", "l", "#E24B4A"], spots: ["Possible spots", "c", "#EF9F27"],
    struct: ["Structure", "c", "#D4537E"], drop: ["Drop-offs", "c", "#D85A30"],
    weed: ["Weed line (estimate)", "l", "#3B6D11"], summer: ["Summer layer", "l", "#BA7517"],
    cast: ["Deep within a cast", "c", "#993556"], calm: ["Calm shore", "c", "#1D9E75"],
    sun: ["Sun and shade shore", "c", "#FAC775"], rep: ["Reported spots", "c", "#7F77DD"],
    ice: ["Under-ice band", "c", "#FFFFFF"],
  };
  var KIND_COLOUR = { island: 0x5F5E5A, point: 0xBA7517, basin: 0x534AB7, hump: 0xD4537E, drop: 0xD85A30, flat: 0x639922 };
  var DIRS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

  var webgl = null;          // checked once
  var threeLoading = null;
  var gridCache = {};
  var view = null;           // the open view, or null

  function index() { return typeof DEPTH_GRIDS !== "undefined" && DEPTH_GRIDS && DEPTH_GRIDS.lakes ? DEPTH_GRIDS : null; }
  function entry(lake) {
    var I = index();
    var e = I && lake ? I.lakes[lakeKey(lake)] : null;
    return e && I.grids[e.grid] ? { lake: e, grid: I.grids[e.grid] } : null;
  }
  function has(lake) { return !!entry(lake); }

  function canWebGL() {
    if (webgl !== null) return webgl;
    try {
      var c = document.createElement("canvas");
      webgl = !!(window.WebGLRenderingContext && (c.getContext("webgl") || c.getContext("experimental-webgl")));
    } catch (e) { webgl = false; }
    return webgl;
  }

  function loadThree() {
    if (window.THREE) return Promise.resolve(true);
    if (threeLoading) return threeLoading;
    threeLoading = new Promise(function (resolve) {
      var s = document.createElement("script");
      s.src = THREE_SRC;
      s.onload = function () { resolve(!!window.THREE); };
      s.onerror = function () { threeLoading = null; resolve(false); };
      document.head.appendChild(s);
    });
    return threeLoading;
  }

  function loadGrid(meta) {
    if (gridCache[meta.file]) return Promise.resolve(gridCache[meta.file]);
    return fetch(meta.file).then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.arrayBuffer(); })
      .then(function (buf) {
        var cells = new Int16Array(buf);
        if (cells.length !== meta.w * meta.h) throw new Error("size");
        gridCache[meta.file] = LakeStructure.fromInt16(meta, cells);
        return gridCache[meta.file];
      });
  }

  function dirName(d) { return DIRS[Math.round((((d % 360) + 360) % 360) / 45) % 8]; }
  function round1(v) { return Math.round(v * 10) / 10; }
  function escHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ============================================================
  // THE OVERLAY
  // ============================================================

  var CSS = "\
#depth3d [hidden]{display:none!important}#depth3d{position:fixed;inset:0;z-index:4500;display:flex;flex-direction:column;background:var(--bg,#2b2e2a);color:var(--ink,#e8e4d8);font:14px/1.4 system-ui,sans-serif}\
#depth3d .d3-bar{display:flex;align-items:center;gap:6px;padding:6px 8px;background:var(--panel,#3a3d38);border-bottom:1px solid var(--panel-edge,#1f211e)}\
#depth3d .d3-title{flex:1;min-width:0;margin:0;font-size:15px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}\
#depth3d button{min-height:40px;min-width:40px;border-radius:6px;border:1px solid var(--panel-edge,#1f211e);background:var(--panel-2,#33362f);color:inherit;font:inherit;cursor:pointer}\
#depth3d .d3-stage{position:relative;flex:1 1 55%;min-height:220px;background:#1f211e}\
#depth3d canvas{position:absolute;inset:0;width:100%;height:100%;display:block;touch-action:none;cursor:grab}\
#depth3d .d3-sign{position:absolute;top:8px;right:8px;width:92px;text-align:center;background:rgba(43,46,42,.88);border:1px solid var(--panel-edge,#1f211e);border-radius:10px;padding:4px;font-size:12px;pointer-events:none}\
#depth3d .d3-sign b{display:block;font-size:13px}\
#depth3d .d3-wait{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:16px;text-align:center;color:var(--ink-dim,#a8a396)}\
#depth3d .d3-panel{flex:0 1 auto;max-height:45%;overflow-y:auto;background:var(--panel,#3a3d38);border-top:1px solid var(--panel-edge,#1f211e)}\
#depth3d .d3-row{display:flex;align-items:center;gap:8px;padding:5px 10px;flex-wrap:wrap}\
#depth3d .d3-row input[type=range]{flex:1;min-width:120px}\
#depth3d .d3-row .lab{min-width:52px;color:var(--ink-dim,#a8a396)}\
#depth3d .d3-key{display:flex;align-items:center;gap:6px;padding:6px 10px;font-size:12px;color:var(--ink-dim,#a8a396)}\
#depth3d .d3-key span.g{flex:1;height:10px;border-radius:4px;background:linear-gradient(90deg,#B5D4F4,#378ADD,#0C447C,#042C53)}\
#depth3d .d3-msg{padding:2px 10px;color:#FAC775}\
#depth3d .d3-read{padding:8px 10px;border-top:1px solid var(--panel-edge,#1f211e);min-height:38px}\
#depth3d .d3-hd{padding:8px 10px 0;font-size:12px;color:var(--ink-dim,#a8a396);border-top:1px solid var(--panel-edge,#1f211e)}\
#depth3d .d3-lay{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:2px 10px;padding:4px 10px 8px}\
#depth3d .d3-lay label{display:flex;align-items:center;gap:6px;min-height:36px}\
#depth3d .d3-lay i.c{display:inline-block;width:10px;height:10px;border-radius:50%;flex:none}\
#depth3d .d3-lay i.l{display:inline-block;width:14px;height:3px;flex:none}\
#depth3d .d3-lay .q{min-height:28px;min-width:28px;padding:0;border-radius:50%;margin-left:auto;font-size:13px}\
#depth3d .d3-foot{padding:6px 10px 12px;font-size:11px;color:var(--ink-dim,#a8a396)}\
";

  function ensureStyle() {
    if (document.getElementById(ROOT_ID + "-style")) return;
    var s = document.createElement("style");
    s.id = ROOT_ID + "-style";
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function layerRow(id) {
    var inf = LAYER_INFO[id];
    var sw = inf[1] === "l" ? '<i class="l" style="background:' + inf[2] + '"></i>'
      : '<i class="c" style="background:' + inf[2] + (id === "ice" ? ";border:1px solid #888780" : "") + '"></i>';
    return '<label><input type="checkbox" data-layer="' + id + '"' + (LAYERS_ON.indexOf(id) >= 0 ? " checked" : "") + ">" + sw
      + escHtml(inf[0]) + '<button type="button" class="q" data-learn="layer-' + id + '" aria-label="About ' + escHtml(inf[0]) + '">?</button></label>';
  }

  function shell(lake, meta, aerated) {
    ensureStyle();
    var el = document.createElement("div");
    el.id = ROOT_ID;
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-label", "3D depth model of " + lake.name);
    el.innerHTML = '<div class="d3-bar"><h2 class="d3-title">' + escHtml(lake.name) + " · 3D depth</h2>"
      + '<button type="button" data-learn="" aria-label="About the 3D depth model">i</button>'
      + '<button type="button" data-default>Default view</button>'
      + '<button type="button" data-close aria-label="Close the 3D depth model">✕</button></div>'
      + '<div class="d3-stage"><canvas></canvas><div class="d3-wait">Loading the lakebed…</div>'
      + '<div class="d3-sign" hidden><svg viewBox="-50 -50 100 100" width="70" height="70" aria-hidden="true"><g data-rose>'
      + '<circle r="44" fill="none" stroke="#888780" stroke-width="1.5"/>'
      + '<text x="0" y="-30" text-anchor="middle" font-size="15" fill="#E24B4A" font-weight="600">N</text>'
      + '<text x="34" y="5" text-anchor="middle" font-size="11" fill="#a8a396">E</text><text x="0" y="41" text-anchor="middle" font-size="11" fill="#a8a396">S</text>'
      + '<text x="-34" y="5" text-anchor="middle" font-size="11" fill="#a8a396">W</text>'
      + '<circle data-sun r="6" fill="#EF9F27" stroke="#fff" stroke-width="1.5"/>'
      + '<g data-arrow><path d="M0 -24 L9 -6 L3 -6 L3 22 L-3 22 L-3 -6 L-9 -6 Z" fill="#E24B4A"/></g></g></svg>'
      + '<b data-kph>—</b><span data-from></span><br><span data-sunw style="font-size:11px"></span></div></div>'
      + '<div class="d3-panel">'
      + '<div class="d3-key"><span>0 m</span><span class="g"></span><span>' + round1(meta.max_depth_m) + " m</span></div>"
      + '<div class="d3-msg" data-msg></div>'
      + '<div class="d3-row"><span class="lab">Time</span><button type="button" data-play aria-label="Play the wind hours">▶</button>'
      + '<input type="range" data-hour min="0" max="0" step="1" value="0" aria-label="Forecast hour"><span data-hourtxt style="min-width:84px">Now</span></div>'
      + '<div class="d3-row"><span class="lab">Height</span><input type="range" data-height min="1" max="200" step="1" aria-label="Height"><span data-heighttxt style="min-width:84px"></span></div>'
      + '<div class="d3-read" data-read aria-live="polite">Drag to turn any way; let go and it glides. Pinch or scroll to zoom. Point at or tap a marker for its name.</div>'
      + '<div class="d3-hd">On at the start</div><div class="d3-lay">' + LAYERS_ON.map(layerRow).join("") + "</div>"
      + '<div class="d3-hd">Turn on when you need them</div><div class="d3-lay">' + LAYERS_OFF.map(layerRow).join("")
      + (aerated ? '<label style="color:var(--ink-dim,#a8a396)"><i class="c" style="border:2px solid #E24B4A"></i>Aerator warning (always on)'
        + '<button type="button" class="q" data-learn="layer-aerator" aria-label="About the aerator warning">?</button></label>' : "")
      + "</div>"
      + '<div class="d3-foot">Depth at the survey water level; the real level changes. Height is made taller so the shape is easy to see. '
      + "Spots and layers are estimates. Lakebed: Alberta Geological Survey (" + escHtml(meta.source) + "), Open Government Licence – Alberta. "
      + "Boating rules: Transport Canada TP 15587E (2026), not the official version, and MyWildAlberta. Wind: Open-Meteo.com (CC BY 4.0). 3D: three.js (MIT).</div>"
      + "</div>";
    document.body.appendChild(el);
    return el;
  }

  // ============================================================
  // OPEN
  // ============================================================

  function open(lake) {
    var e = entry(lake);
    if (!e) return;
    close();
    var aerated = typeof lakeAerated === "function" && lakeAerated(lake);
    var el = shell(lake, e.grid, aerated);
    var wait = el.querySelector(".d3-wait");
    var returnFocus = document.activeElement;
    view = { el: el, lake: lake, meta: e.grid, aerated: aerated, returnFocus: returnFocus, alive: true };
    el.querySelector("[data-close]").addEventListener("click", close);
    el.querySelector("[data-close]").focus();
    el.addEventListener("keydown", function (ev) { if (ev.key === "Escape") close(); });
    el.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-learn]");
      if (!b || !window.ReadingRoom) return;
      ev.preventDefault();
      ReadingRoom.open("depth-model" + (b.dataset.learn ? "#" + b.dataset.learn : ""));
    });
    if (!canWebGL()) { wait.textContent = "This phone cannot show 3D. The Alberta depth chart link in Lake info still works."; return; }
    var mine = view;
    Promise.all([loadThree(), loadGrid(e.grid).catch(function () { return null; })]).then(function (got) {
      if (view !== mine || !mine.alive) return;
      if (!got[0]) { wait.textContent = "3D add-on not saved yet — open the app once with signal."; return; }
      if (!got[1]) { wait.textContent = "This lakebed is not saved yet — open the app once with signal."; return; }
      wait.hidden = true;
      try { build(mine, got[1]); } catch (err) {
        wait.hidden = false;
        wait.textContent = "The 3D model could not start on this device.";
        if (window.console) console.warn("depth3d:", err);
      }
    });
  }

  function close() {
    if (!view) return;
    var v = view;
    view = null;
    v.alive = false;
    if (v.stop) v.stop();
    if (v.el && v.el.parentNode) v.el.parentNode.removeChild(v.el);
    if (v.returnFocus && v.returnFocus.focus) { try { v.returnFocus.focus(); } catch (e) { /* gone */ } }
  }

  // ============================================================
  // THE SCENE
  // ============================================================

  function build(v, grid) {
    var T = window.THREE, el = v.el, lake = v.lake, meta = v.meta, aerated = v.aerated;
    var w = grid.w, h = grid.h, n = w * h, cell = grid.cell;
    var U = SIZE / (Math.max(w, h) * cell);
    var px = function (i) { return (i - (w - 1) / 2) * cell * U; };
    var py = function (j) { return ((h - 1) / 2 - j) * cell * U; };
    var maxD = Math.max(1, meta.max_depth_m);
    var structure = LakeStructure.find(grid);
    // Land relief stays small next to the lake, at any Height setting.
    var landCap = Math.min(LAND_CAP_M, Math.max(0.5, 0.25 * maxD));
    var shore = structure.shore;

    // Land with no height in the grid gets a gentle bank from its distance to water.
    var landZ = new Float32Array(n);
    (function () {
      var dist = new Int32Array(n).fill(-1), q = new Int32Array(n), a = 0, b = 0;
      for (var k = 0; k < n; k++) if (grid.depth[k] > 0) { dist[k] = 0; q[b++] = k; }
      while (a < b) {
        var c = q[a++], x = c % w;
        [x > 0 ? c - 1 : -1, x < w - 1 ? c + 1 : -1, c - w, c + w].forEach(function (m) {
          if (m >= 0 && m < n && dist[m] < 0) { dist[m] = dist[c] + 1; q[b++] = m; }
        });
      }
      for (var k2 = 0; k2 < n; k2++) {
        if (grid.depth[k2] > 0) continue;
        var lh = grid.landHeight[k2];
        var bank = Math.min(landCap, 0.3 + dist[k2] * cell * 0.02);
        landZ[k2] = Math.min(landCap, isFinite(lh) ? Math.max(0.3, lh) : bank);
      }
    })();
    var bedZ = function (i, j) { var k = j * w + i; return grid.depth[k] > 0 ? -grid.depth[k] * U : landZ[k] * U; };

    var canvas = el.querySelector("canvas");
    var ren = new T.WebGLRenderer({ canvas: canvas, antialias: true });
    ren.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    ren.setClearColor(0x1f211e);
    var sc = new T.Scene(), cam = new T.PerspectiveCamera(38, 1, 0.05, 100);
    // The start zoom fits the model's width on a narrow phone screen too.
    var fitDist = function () {
      var half = Math.tan(19 * Math.PI / 180) * Math.min(1.3, cam.aspect || 1);
      return Math.max(D0, (SIZE / 2) * 1.08 / half);
    };
    var dist = D0, distT = D0;
    cam.position.set(0, 0, dist);
    var root = new T.Group(), bed = new T.Group(), top = new T.Group();
    root.add(bed, top);
    sc.add(root);
    sc.add(new T.AmbientLight(0xffffff, 0.55));
    var sunL = new T.DirectionalLight(0xffffff, 0.75);
    sunL.position.set(-2, 3, 5);
    sc.add(sunL);

    // Height: a lake-by-lake start so the shape is easy to see.
    // A 20 km lake 10 m deep needs far more than a 1 km pond 15 m deep.
    var ex = Math.max(1, Math.min(150, Math.round(0.06 * Math.max(w, h) * cell / maxD)));
    bed.scale.z = ex;

    // ---- lakebed mesh
    var stops = [[181, 212, 244], [55, 138, 221], [12, 68, 124], [4, 44, 83]];
    var col = function (z) {
      var t = Math.min(1, z / maxD) * (stops.length - 1), i = Math.min(stops.length - 2, Math.floor(t)), f = t - i;
      return stops[i].map(function (c, k) { return (c + (stops[i + 1][k] - c) * f) / 255; });
    };
    var geo = new T.PlaneGeometry((w - 1) * cell * U, (h - 1) * cell * U, w - 1, h - 1);
    var pos = geo.attributes.position, cols = new Float32Array(n * 3);
    for (var k = 0; k < n; k++) {
      var i0 = k % w, j0 = (k - i0) / w;
      pos.setZ(k, bedZ(i0, j0));
      if (grid.depth[k] > 0) cols.set(col(grid.depth[k]), k * 3);
      else { var bt = landZ[k] / landCap; cols.set([0.43 + 0.12 * bt, 0.5 + 0.08 * bt, 0.34 + 0.06 * bt], k * 3); }
    }
    geo.setAttribute("color", new T.BufferAttribute(cols, 3));
    geo.computeVertexNormals();
    var mesh = new T.Mesh(geo, new T.MeshLambertMaterial({ vertexColors: true, side: T.DoubleSide, polygonOffset: true,
                                                            polygonOffsetFactor: 1, polygonOffsetUnits: 1 }));
    bed.add(mesh);
    top.add(new T.Mesh(new T.PlaneGeometry((w - 1) * cell * U, (h - 1) * cell * U),
                       new T.MeshBasicMaterial({ color: 0x85B7EB, transparent: true, opacity: 0.08, depthWrite: false })));

    // ---- helpers
    var lineGeo = function (segs, depthM) {
      var P = new Float32Array(segs.length / 2 * 3);
      for (var s = 0, o = 0; s < segs.length; s += 2) {
        P[o++] = (segs[s] - (w - 1) / 2) * cell * U;
        P[o++] = ((h - 1) / 2 - segs[s + 1]) * cell * U;
        P[o++] = depthM == null ? 0.012 : -depthM * U;
      }
      var g = new T.BufferGeometry();
      g.setAttribute("position", new T.BufferAttribute(P, 3));
      return g;
    };
    var lines = function (segs, depthM, color, op, ud) {
      var l = new T.LineSegments(lineGeo(segs, depthM), new T.LineBasicMaterial({ color: color, transparent: true, opacity: op }));
      if (ud) l.userData = ud;
      return l;
    };
    var dots = function (cells, color, zf, size, ud) {
      var P = new Float32Array(cells.length * 3);
      cells.forEach(function (c, m) { P[m * 3] = px(c.i); P[m * 3 + 1] = py(c.j); P[m * 3 + 2] = zf(c); });
      var g = new T.BufferGeometry();
      g.setAttribute("position", new T.BufferAttribute(P, 3));
      var p = new T.Points(g, new T.PointsMaterial({ color: color, size: size || 4, sizeAttenuation: false }));
      p.userData = ud;
      return p;
    };
    var hex = function (c) { return "#" + c.toString(16).padStart(6, "0"); };

    // ---- contour lines
    var step = maxD <= 8 ? 1 : maxD <= 25 ? 2 : 5;
    for (var lv = step; lv < maxD; lv += step) {
      if (lv === 4 && maxD > 4) continue;     // the weed line draws 4 m
      bed.add(lines(LakeStructure.contour(grid, lv), lv, 0x042C53, 0.55));
    }

    // ---- layers
    var L = {};
    ["weed", "drop", "summer", "ice"].forEach(function (id) { L[id] = new T.Group(); bed.add(L[id]); });
    ["wind", "spots", "struct", "cast", "calm", "sun", "rep"].forEach(function (id) { L[id] = new T.Group(); top.add(L[id]); });

    if (maxD > 4) L.weed.add(lines(LakeStructure.contour(grid, 4), 4, 0x3B6D11, 1, { name: "Weed line ~4 m (estimate)", color: "#3B6D11",
      why: "Weed line (estimate): weeds usually stop near 4 m. Trout cruise this edge for bugs and minnows." }));
    L.drop.add(dots(structure.dropCells.filter(function (k2, m) { return m % 2 === 0; }).map(function (k3) { return { i: k3 % w, j: Math.floor(k3 / w) }; }),
      0xD85A30, function (c) { return -grid.depth[c.j * w + c.i] * U; }, 3,
      { name: "Drop-off", color: "#D85A30", why: "Drop-off: the lakebed is steep here. Trout follow these edges." }));
    var strat = (typeof depthFor === "function" ? (depthFor(lake) || {}).stratification : null) || null;
    var band = strat && strat.stratifies && strat.band_m ? strat.band_m : null;
    if (band) {
      [band[0], band[1]].forEach(function (dm) {
        var p = new T.Mesh(new T.PlaneGeometry((w - 1) * cell * U * 0.96, (h - 1) * cell * U * 0.96),
          new T.MeshBasicMaterial({ color: 0xBA7517, transparent: true, opacity: 0.16, side: T.DoubleSide, depthWrite: false }));
        p.position.z = -dm * U;
        p.userData = { name: "Summer layer " + band[0] + "–" + band[1] + " m", color: "#BA7517",
          why: "Summer layer: in July and August trout hold about " + band[0] + "–" + band[1] + " m, above the cold, low-oxygen water." };
        L.summer.add(p);
      });
    }
    var iceCells = [];
    for (var kk = 0; kk < n; kk += 1) if (grid.depth[kk] >= 1.5 && grid.depth[kk] <= 4 && ((kk % w) + Math.floor(kk / w)) % 2 === 0) iceCells.push({ i: kk % w, j: Math.floor(kk / w) });
    L.ice.add(dots(iceCells, 0xffffff, function (c) { return -grid.depth[c.j * w + c.i] * U; }, 3, { name: "Under-ice band 1.5–4 m", color: "#888780",
      why: "Under-ice band: in winter trout feed in 1.5–4 m water, along weed edges and drop-offs, where there is more food and oxygen. Drill your holes in this band." }));
    L.cast.add(dots(FishingSpots.castReach(shore), 0x993556, function () { return 0.012; }, 5, { name: "Deep within a cast", color: "#993556",
      why: "Deep within a cast: from this shore, water 4 m or deeper is within 30 m. Good bank spots." }));

    // ---- pins
    var pins = [];
    var pin = function (color, r, i, j, tz, group, ud) {
      var g = new T.Group(), m = new T.MeshBasicMaterial({ color: color });
      var ball = new T.Mesh(new T.SphereGeometry(r, 16, 12), m);
      ball.position.z = tz;
      g.add(ball);
      var stick = new T.Mesh(new T.CylinderGeometry(0.008, 0.008, 1, 6), m);
      stick.rotation.x = Math.PI / 2;
      g.add(stick);
      g.position.set(px(i), py(j), 0);
      g.userData = Object.assign({ i: i, j: j, tz: tz, stick: stick }, ud);
      group.add(g);
      pins.push(g);
      placePin(g);
      return g;
    };
    function placePin(g) {
      var u = g.userData, zb = bedZ(u.i, u.j) * ex, len = Math.max(0.01, u.tz - zb);
      u.stick.scale.set(1, len, 1);
      u.stick.position.z = zb + len / 2;
    }
    function unpinAll(group) {
      group.children.slice().forEach(function (c) {
        group.remove(c);
        var at = pins.indexOf(c);
        if (at >= 0) pins.splice(at, 1);
        c.traverse(function (o) { if (o.geometry) o.geometry.dispose(); });
      });
    }
    structure.labels.forEach(function (s) {
      pin(KIND_COLOUR[s.kind] || 0xD4537E, 0.028, s.i, s.j, 0.22, L.struct, { name: s.name, color: hex(KIND_COLOUR[s.kind] || 0xD4537E), why: s.why });
    });

    // Lat/lon → grid cell, from the file's local linear fit of Alberta 10TM.
    var A = meta.affine;
    var toCell = function (lat, lon) {
      var E = A[0] + A[4] * (lat - A[2]) + A[5] * (lon - A[3]);
      var N = A[1] + A[6] * (lat - A[2]) + A[7] * (lon - A[3]);
      return { i: (E - meta.x0) / cell, j: (meta.y0 - N) / cell };
    };
    var inGrid = function (c, marginCells) {
      return c.i >= -marginCells && c.j >= -marginCells && c.i <= w - 1 + marginCells && c.j <= h - 1 + marginCells;
    };
    (typeof hotSpotsFor === "function" ? hotSpotsFor(lake) : []).forEach(function (s) {
      if (!isFinite(s.lat) || !isFinite(s.lon)) return;
      var c = toCell(s.lat, s.lon);
      if (!inGrid(c, 0)) return;
      pin(0x7F77DD, 0.045, Math.round(c.i), Math.round(c.j), 0.3, L.rep, { name: "Reported: " + s.name, color: "#7F77DD",
        why: "Reported spot: " + s.name + (s.note ? ". " + s.note : "") + " (source " + s.source_date + ")." });
    });

    // ---- wind arrows: small, about every 300 m of water
    var shp = new T.Shape();
    shp.moveTo(0, 0.5); shp.lineTo(0.24, 0.16); shp.lineTo(0.08, 0.16); shp.lineTo(0.08, -0.5);
    shp.lineTo(-0.08, -0.5); shp.lineTo(-0.08, 0.16); shp.lineTo(-0.24, 0.16); shp.closePath();
    var aG = new T.ShapeGeometry(shp), aM = new T.MeshBasicMaterial({ color: 0xE24B4A, transparent: true, opacity: 0.7, side: T.DoubleSide, depthWrite: false });
    var arrows = [];
    var spacing = Math.max(3, Math.round(Math.max(w, h) / 7));
    for (var aj = Math.round(spacing / 2); aj < h; aj += spacing) {
      for (var ai = Math.round(spacing / 2); ai < w; ai += spacing) {
        if (grid.depth[aj * w + ai] > 0) {
          var m = new T.Mesh(aG, aM);
          m.position.set(px(ai), py(aj), 0.02);
          L.wind.add(m);
          arrows.push(m);
        }
      }
    }
    var aA = 0, aT = 0, sA = 0.2, sT = 0.2;

    // ---- your position, asked once
    var me = null;
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(function (p) {
        if (!v.alive) return;
        var c = toCell(p.coords.latitude, p.coords.longitude);
        if (!inGrid(c, 2000 / cell)) return;
        var ci = Math.max(0, Math.min(w - 1, Math.round(c.i))), cj = Math.max(0, Math.min(h - 1, Math.round(c.j)));
        me = pin(0x378ADD, 0.05, ci, cj, 0.36, top, { name: "You", color: "#378ADD", why: "You are here." });
        req();
      }, function () { /* no pin, no second question */ }, { maximumAge: 300000, timeout: 15000 });
    }

    // ---- name tag, one at a time
    var tagCache = {};
    var tag = function (text, color) {
      var key = text + color;
      if (tagCache[key]) return tagCache[key];
      var c = document.createElement("canvas"), x = c.getContext("2d");
      x.font = "600 40px system-ui, sans-serif";
      var tw = Math.ceil(x.measureText(text).width) + 40;
      c.width = tw; c.height = 60;
      x.fillStyle = "rgba(255,255,255,0.95)"; x.fillRect(0, 0, tw, 60);
      x.fillStyle = color; x.fillRect(0, 0, 12, 60);
      x.font = "600 40px system-ui, sans-serif"; x.fillStyle = "#2C2C2A"; x.fillText(text, 24, 44);
      var t = new T.CanvasTexture(c);
      t.minFilter = T.LinearFilter;
      var s = new T.Sprite(new T.SpriteMaterial({ map: t, depthTest: false, sizeAttenuation: false }));
      s.scale.set(0.042 * tw / 60, 0.042, 1);
      s.center.set(-0.08, -0.3);
      s.renderOrder = 10;
      return (tagCache[key] = s);
    };
    var tipHolder = new T.Group();
    top.add(tipHolder);
    var tipFor = null;
    var showTip = function (o, p) {
      tipHolder.clear();
      tipFor = o;
      if (!o) return;
      tipHolder.add(tag(o.userData.name, o.userData.color || "#D4537E"));
      tipHolder.position.copy(p);
    };
    var tapMark = new T.Mesh(new T.SphereGeometry(0.025, 16, 12), new T.MeshBasicMaterial({ color: 0xffffff }));
    tapMark.visible = false;
    top.add(tapMark);

    // ---- controls
    var $ = function (sel) { return el.querySelector(sel); };
    var readEl = $("[data-read]"), msgEl = $("[data-msg]");
    var heightIn = $("[data-height]"), heightTxt = $("[data-heighttxt]");
    heightIn.value = ex;
    heightTxt.textContent = ex + "× taller";
    $(".d3-sign").hidden = false;

    var boating = (typeof BOATING_RULES !== "undefined" && BOATING_RULES && BOATING_RULES.lakes) ? BOATING_RULES.lakes[lakeKey(lake)] : null;
    var amen = (typeof profileFor === "function" ? (profileFor(lake) || {}).amenities : null) || [];
    var hasLaunch = amen.indexOf("Boat Launch") >= 0;
    var trollDepth = FishingSpots.trollDepth(maxD);
    var trollSegs = LakeStructure.contour(grid, trollDepth);

    // Forecast hours: from now to the end of the saved forecast.
    var wx = Weather.peek(lake.lat, lake.lon), data = wx && wx.data;
    var hours = [];
    if (data && data.t && data.t.length) {
      var startI = Math.max(0, Weather.nearestIndex(data, new Date()));
      for (var hi = startI; hi < data.t.length; hi++) hours.push(hi);
    }
    var hourIn = $("[data-hour]"), hourTxt = $("[data-hourtxt]");
    hourIn.max = Math.max(0, hours.length - 1);
    var hasDir = data && Array.isArray(data.windDir) && data.windDir.length > 0;

    // Ice for a moment, from the same estimate Lake info shows.
    var iceEst = null;
    try {
      if (window.LakeSheet && LakeSheet._internal && LakeSheet._internal.estimatesFor) {
        iceEst = LakeSheet._internal.estimatesFor(lake, typeof Forecast !== "undefined" ? Forecast.forLake(lake) : null).ice;
      }
    } catch (e1) { iceEst = null; }
    var icedAt = function (when) {
      if (!iceEst) return false;
      if (iceEst.state === "ice") return !(iceEst.iceOff && iceEst.iceOff.date && when >= iceEst.iceOff.date);
      return !!(iceEst.iceOn && iceEst.iceOn.date && when >= iceEst.iceOn.date);
    };

    var hourIdx = 0;
    function momentFor(idx) {
      if (!hours.length) return { when: new Date(), kph: null, fromTrue: null };
      var di = hours[idx];
      // Rounded once, so the number shown and the calm test always agree.
      var kph = typeof data.wind[di] === "number" ? Math.round(data.wind[di]) : null;
      var from = hasDir && typeof data.windDir[di] === "number" ? data.windDir[di] : null;
      return { when: new Date(data.t[di] * 1000), kph: kph, fromTrue: from };
    }
    function clockText(when) {
      var off = data && typeof data.offset === "number" ? data.offset : null;
      var dd = off == null ? when : new Date(when.getTime() + off * 1000);
      var day = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][off == null ? dd.getDay() : dd.getUTCDay()];
      var hh = off == null ? dd.getHours() : dd.getUTCHours();
      return day + " " + (hh < 10 ? "0" : "") + hh + ":00";
    }
    function clearGroup(g) { g.children.slice().forEach(function (c) { g.remove(c); if (c.geometry) c.geometry.dispose(); }); }

    function hourUpdate() {
      var mo = momentFor(hourIdx), iced = icedAt(mo.when);
      hourTxt.textContent = hourIdx === 0 ? "Now" : clockText(mo.when);
      var windy = !iced && mo.kph != null && mo.fromTrue != null;
      // Grid bearing the wind blows TO.
      var toGrid = windy ? (mo.fromTrue + 180 + meta.north_deg) % 360 : null;
      if (windy) { aT = -toGrid * Math.PI / 180; sT = 0.12 + mo.kph / 110; }
      L.wind.visible = windy && layerOn("wind");
      var rose = $("[data-arrow]");
      rose.style.display = windy ? "" : "none";
      if (windy) rose.setAttribute("transform", "rotate(" + ((mo.fromTrue + 180) % 360) + ")");
      $("[data-kph]").textContent = iced ? "Under ice" : mo.kph == null ? "No wind" : Math.round(mo.kph) + " km/h";
      $("[data-from]").textContent = iced ? "no wind" : mo.fromTrue == null ? "" : "from " + dirName(mo.fromTrue);

      var msgs = [];
      if (!hours.length) msgs.push("No forecast saved for this lake — open the app once with signal.");
      else if (!hasDir) msgs.push("No wind direction saved — open the app once with signal.");
      if (iced) msgs.push("Under ice: ice spots only, in the 1.5–4 m band next to a drop. Check the ice thickness first.");
      else if (windy && mo.kph < FishingSpots.CALM_KPH) msgs.push("Wind too light to move food. Spots use the drop-offs only.");
      var month = mo.when.getMonth() + 1;
      if (aerated && (iced || month >= 10 || month <= 4)) msgs.push("Aerated lake: open water and thin ice near the aerator from October to April. Stay off that area.");
      msgEl.textContent = msgs.join(" ");

      unpinAll(L.spots);
      clearGroup(L.spots);
      showTip(null);
      if (iced) {
        FishingSpots.iceSpots(grid, structure.dropCells, null).forEach(function (s) {
          pin(0xEF9F27, 0.045, s.i, s.j, 0.3, L.spots, { name: s.name, color: "#EF9F27", why: s.why });
        });
      } else {
        FishingSpots.shoreSpots(grid, shore, toGrid, windy ? mo.kph : null).forEach(function (s) {
          pin(0xEF9F27, 0.045, s.i, s.j, 0.3, L.spots, { name: s.name, color: "#EF9F27", why: s.why });
        });
        var route = FishingSpots.trollingRoute(grid, trollSegs, toGrid, windy ? mo.kph : null);
        var tl = lines(route.segments, null, 0xEF9F27, hasLaunch ? 1 : 0.45, {
          name: "Trolling route ~" + trollDepth + " m", color: "#EF9F27",
          why: "Trolling route (estimate): along " + trollDepth + " m" + (route.downwind ? " on the downwind side, where food piles up. " : " around the lake (light wind). ")
            + FishingSpots.boatingText(boating, hasLaunch) });
        if (!(boating && boating.no_boats)) L.spots.add(tl);
      }
      clearGroup(L.calm);
      if (windy) L.calm.add(dots(FishingSpots.calmShore(shore, toGrid, mo.kph), 0x1D9E75, function () { return 0.014; }, 5,
        { name: "Calm shore", color: "#1D9E75", why: "Calm shore: the wind blows away from this shore, so the water is flat. Best for a float tube or a fly line." }));
      clearGroup(L.sun);
      var sp = window.Astro ? Astro.sunPosition(mo.when, lake.lat, lake.lon) : null;
      var sunDot = $("[data-sun]"), sunW = $("[data-sunw]");
      if (sp && sp.altitude > 0) {
        var a = sp.azimuth * Math.PI / 180;
        sunDot.setAttribute("cx", (38 * Math.sin(a)).toFixed(1));
        sunDot.setAttribute("cy", (-38 * Math.cos(a)).toFixed(1));
        sunDot.style.display = "";
        sunW.textContent = "Sun " + Math.round(sp.altitude) + "° " + dirName(sp.azimuth);
        if (!iced) {
          var ss = FishingSpots.sunShore(shore, (sp.azimuth + meta.north_deg) % 360, sp.altitude);
          L.sun.add(dots(ss.shade, 0x444441, function () { return 0.016; }, 5, { name: "Shade shore", color: "#444441",
            why: "Shade shore: the bank on the sun side shades the water next to it. Trout come shallower in shade on bright days." }));
          L.sun.add(dots(ss.sun, 0xFAC775, function () { return 0.016; }, 5, { name: "Sunny shore", color: "#FAC775",
            why: "Sunny shore: the sun is on this water. It warms first in spring and fall." }));
        }
      } else {
        sunDot.style.display = "none";
        sunW.textContent = "Sun down";
      }
      L.ice.visible = iced && layerOn("ice");
      req();
    }

    function layerOn(id) { var c = el.querySelector('[data-layer="' + id + '"]'); return !!(c && c.checked); }
    Array.prototype.forEach.call(el.querySelectorAll("[data-layer]"), function (c) {
      var id = c.dataset.layer;
      var sync = function () { L[id].visible = c.checked; showTip(null); if (id === "wind" || id === "ice") hourUpdate(); req(); };
      L[id].visible = c.checked;
      c.addEventListener("change", sync);
    });

    // ---- the frame loop
    var q0 = new T.Quaternion().setFromAxisAngle(new T.Vector3(1, 0, 0), -0.95);
    root.quaternion.copy(q0);
    var tween = null, need = false, vA = 0, dragging = false, lastMove = 0, hoverEv = null;
    var vAx = new T.Vector3(1, 0, 0), tq = new T.Quaternion(), v0 = new T.Vector3(), v1 = new T.Vector3();
    var northV = new T.Vector3(Math.sin(meta.north_deg * Math.PI / 180), Math.cos(meta.north_deg * Math.PI / 180), 0);
    var roseEl = $("[data-rose]");
    var raf = window.requestAnimationFrame || function (f) { return setTimeout(function () { f(Date.now()); }, 16); };
    function req() { if (!need && v.alive) { need = true; raf(frame); } }
    function frame(t) {
      need = false;
      if (!v.alive) return;
      var more = false;
      if (!dragging && vA > 0.0004) { root.quaternion.premultiply(tq.setFromAxisAngle(vAx, vA)); vA *= 0.9; more = true; }
      if (tween) {
        var kq = Math.min(1, ((t || Date.now()) - tween.t0) / 450), e3 = 1 - Math.pow(1 - kq, 3);
        root.quaternion.copy(tween.qa).slerp(q0, e3);
        if (kq < 1) more = true; else tween = null;
      }
      if (Math.abs(distT - dist) > 0.002) { dist += (distT - dist) * 0.25; more = true; }
      cam.position.z = dist;
      var d = Math.atan2(Math.sin(aT - aA), Math.cos(aT - aA));
      if (Math.abs(d) > 0.002 || Math.abs(sT - sA) > 0.002) { aA += d * 0.22; sA += (sT - sA) * 0.22; more = true; }
      for (var ia = 0; ia < arrows.length; ia++) { arrows[ia].rotation.z = aA; arrows[ia].scale.set(sA, sA, 1); }
      if (hoverEv) {
        var hh = hit(hoverEv);
        hoverEv = null;
        if ((hh && hh.o) !== tipFor) { showTip(hh && hh.o, hh && hh.p); canvas.style.cursor = hh ? "pointer" : "grab"; }
      }
      ren.render(sc, cam);
      v0.set(0, 0, 0).applyQuaternion(root.quaternion).project(cam);
      v1.copy(northV).applyQuaternion(root.quaternion).project(cam);
      roseEl.setAttribute("transform", "rotate(" + (Math.atan2(v1.x - v0.x, (v1.y - v0.y) / cam.aspect) * 180 / Math.PI).toFixed(1) + ")");
      if (more) req();
    }
    function size() {
      var cw = canvas.clientWidth, ch = canvas.clientHeight;
      if (!cw || !ch) return;
      ren.setSize(cw, ch, false);
      var first = !cam.userData.sized;
      cam.aspect = cw / ch;
      cam.updateProjectionMatrix();
      cam.userData.sized = true;
      if (first) { dist = distT = fitDist(); }
      req();
    }

    // ---- picking
    var ray = new T.Raycaster();
    ray.params.Points.threshold = 0.03;
    ray.params.Line.threshold = 0.03;
    function owner(o) { while (o && !(o.userData && o.userData.name)) o = o.parent; return o; }
    function hit(ev) {
      var b = canvas.getBoundingClientRect();
      ray.setFromCamera(new T.Vector2((ev.clientX - b.left) / b.width * 2 - 1, -(ev.clientY - b.top) / b.height * 2 + 1), cam);
      var groups = [L.spots, L.struct, L.rep, L.cast, L.calm, L.sun, L.ice, L.drop, L.weed, L.summer];
      for (var g = 0; g < groups.length; g++) {
        if (!groups[g].visible || !groups[g].parent.visible) continue;
        var hs = ray.intersectObjects(groups[g].children, true)[0];
        var o = hs && owner(hs.object);
        if (o) return { o: o, p: top.worldToLocal(hs.point.clone()) };
      }
      if (me && ray.intersectObject(me, true)[0]) return { o: me, p: top.worldToLocal(me.localToWorld(new T.Vector3(0, 0, 0.36))) };
      return null;
    }
    function pick(ev) {
      var hh = hit(ev);
      if (hh) { showTip(hh.o, hh.p); readEl.textContent = hh.o.userData.why; req(); return; }
      showTip(null);
      var r = ray.intersectObject(mesh)[0];
      if (!r) { req(); return; }
      var l = bed.worldToLocal(r.point.clone());
      var ci = Math.round(l.x / (cell * U) + (w - 1) / 2), cj = Math.round((h - 1) / 2 - l.y / (cell * U));
      var z = ci >= 0 && cj >= 0 && ci < w && cj < h ? grid.depth[cj * w + ci] : 0;
      if (!(z > 0)) { tapMark.visible = false; readEl.textContent = "That is land. Tap the lakebed."; req(); return; }
      tapMark.visible = true;
      tapMark.userData.z = z;
      tapMark.position.set(l.x, l.y, -z * U * ex + 0.02);
      readEl.textContent = "Depth here: " + z.toFixed(1) + " m (survey water level).";
      req();
    }

    // ---- pointer: turn, glide, pinch, wheel, hover, tap
    var ptrs = new Map(), moved = 0, pinch0 = 0;
    canvas.addEventListener("pointerdown", function (ev) {
      canvas.setPointerCapture(ev.pointerId);
      ptrs.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
      moved = 0; vA = 0; tween = null; dragging = true;
      if (ptrs.size === 2) { var pp = Array.from(ptrs.values()); pinch0 = Math.hypot(pp[0].x - pp[1].x, pp[0].y - pp[1].y); }
    });
    canvas.addEventListener("pointermove", function (ev) {
      if (!ptrs.has(ev.pointerId)) {
        if (ev.pointerType === "mouse") { hoverEv = { clientX: ev.clientX, clientY: ev.clientY }; req(); }
        return;
      }
      var p = ptrs.get(ev.pointerId), dx = ev.clientX - p.x, dy = ev.clientY - p.y;
      ptrs.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
      if (ptrs.size === 2) {
        var pp = Array.from(ptrs.values()), dd = Math.hypot(pp[0].x - pp[1].x, pp[0].y - pp[1].y);
        if (pinch0 && dd) distT = Math.max(1.5, Math.min(20, distT * pinch0 / dd));
        pinch0 = dd; moved += 10; vA = 0; req();
        return;
      }
      var len = Math.hypot(dx, dy);
      if (!len) return;
      moved += len;
      if (moved > 6 && tipFor) showTip(null);
      vAx.set(dy, dx, 0).normalize();
      vA = len * 0.008;
      root.quaternion.premultiply(tq.setFromAxisAngle(vAx, vA));
      lastMove = (window.performance ? performance.now() : Date.now());
      req();
    });
    function endPtr(ev, tap) {
      var before = ptrs.size;
      ptrs.delete(ev.pointerId);
      if (ptrs.size < 2) pinch0 = 0;
      if (!ptrs.size) {
        dragging = false;
        if ((window.performance ? performance.now() : Date.now()) - lastMove > 80) vA = 0;
        vA = Math.min(vA, 0.08);
        req();
      }
      if (tap && before === 1 && moved < 6) pick(ev);
    }
    canvas.addEventListener("pointerup", function (ev) { endPtr(ev, true); });
    canvas.addEventListener("pointercancel", function (ev) { endPtr(ev, false); });
    canvas.addEventListener("pointerleave", function () { if (tipFor && !ptrs.size) { showTip(null); req(); } });
    canvas.addEventListener("wheel", function (ev) {
      ev.preventDefault();
      distT = Math.max(1.5, Math.min(20, distT * (ev.deltaY > 0 ? 1.12 : 0.89)));
      req();
    }, { passive: false });

    $("[data-default]").addEventListener("click", function () {
      tween = { qa: root.quaternion.clone(), t0: (window.performance ? performance.now() : Date.now()) };
      vA = 0; distT = fitDist(); req();
    });
    heightIn.addEventListener("input", function () {
      ex = Number(heightIn.value) || 1;
      heightTxt.textContent = ex + "× taller";
      bed.scale.z = ex;
      pins.forEach(placePin);
      if (tapMark.visible) tapMark.position.z = -tapMark.userData.z * U * ex + 0.02;
      showTip(null);
      req();
    });
    hourIn.addEventListener("input", function () { hourIdx = Number(hourIn.value) || 0; hourUpdate(); });
    var playT = null, playBtn = $("[data-play]");
    playBtn.addEventListener("click", function () {
      if (playT) { clearInterval(playT); playT = null; playBtn.textContent = "▶"; return; }
      if (!hours.length) return;
      playBtn.textContent = "❚❚";
      playT = setInterval(function () {
        hourIdx = (hourIdx + 1) % hours.length;
        hourIn.value = hourIdx;
        hourUpdate();
      }, 450);
    });

    // A phone that drops the 3D context in the background gets it back here.
    canvas.addEventListener("webglcontextlost", function (ev) { ev.preventDefault(); });
    canvas.addEventListener("webglcontextrestored", function () { req(); });
    var ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(size) : null;
    if (ro) ro.observe(canvas); else window.addEventListener("resize", size);

    v.stop = function () {
      if (playT) clearInterval(playT);
      if (ro) ro.disconnect(); else window.removeEventListener("resize", size);
      sc.traverse(function (o) {
        if (o.geometry) o.geometry.dispose();
        if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose(); }
      });
      ren.dispose();
      if (ren.forceContextLoss) ren.forceContextLoss();
    };

    size();
    hourUpdate();
  }

  window.DepthModel = { has: has, open: open, close: close, _internal: { canWebGL: canWebGL } };
})();
