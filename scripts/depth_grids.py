"""Lakebed grids for the 3D depth model, one small file per surveyed lake.

Every lake in data/depth_charts.json has, besides its contour map, an Alberta
Geological Survey (AGS) "Digital Elevation Model (Arc ascii grid format)": a
50 m grid of lakebed height in metres above sea level, in Alberta 10TM
(NAD83, central meridian 115 W, scale 0.9992, false easting 500 000). The
grid is a separate DIG publication, listed under "Related Publications" on the
contour map's page. Licence: Open Government Licence - Alberta, credit AGS.

Depth needs the water level, which the grid does not hold. The AGS contour
layer does: each contour carries its height (CONTOUR) and its depth
(CALC_DEP_M), so height + depth is the water level the survey used. One DIG
can hold several lakes at different levels (the Pierre Greys chain), so each
connected piece of water picks the level that fits its own shore.

The AGS grid itself is smoothed: on small lakes its deepest cell can read
half the depth the contour map shows (Chickakoo: 6 m against 15 m). So depth
comes from the contour lines: each line is drawn into the fine grid at its own
depth, the shore is 0, and the cells in between are filled by relaxation
(the smoothest surface through the lines). The AGS grid is the start value for
that fill and gives the land heights.

Water is decided by the AGS lake outline, not by the grid, because the grid
runs about 200 m past the shore. The outline is sampled on a finer grid than
50 m, so the shoreline in the 3D model is smooth; the lakebed between the
50 m cells is bilinear.

Usage:

    python -I scripts/depth_grids.py --fetch   # download into data/raw/ags_bathymetry
    python -I scripts/depth_grids.py           # build data/depth_grids/ from the saved files

The build reads only the saved files, so it repeats without a network.

Output, data/depth_grids/<grid DIG>.bin: the cells, little-endian Int16,
row-major (see "d" below), and data/depth_grids/index.json: "lakes" maps
each lake id to its grid, "grids" holds each grid's facts:
    w, h, cell_m       grid size and cell size in metres, row 0 is north
    x0, y0             10TM easting/northing of the north-west cell centre
    centre             [lat, lon] of the grid centre
    affine             10TM easting/northing near the centre as a linear
                       function of lat/lon: [E0, N0, lat0, lon0, dE/dlat,
                       dE/dlon, dN/dlat, dN/dlon]
    north_deg          grid azimuth of true north (clockwise from grid up)
    level_m            water level(s) used, m above sea level
    max_depth_m        deepest cell
    file               the .bin with one Int16 per cell, row-major:
                       > 0 water depth in decimetres; < 0 land height above
                       the water in decimetres; -32768 no data (land with no
                       height).
"""

import argparse
import io
import json
import math
import re
import struct
import sys
import urllib.parse
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from elevation import get_json  # noqa: E402

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw" / "ags_bathymetry"
OUT = ROOT / "data" / "depth_grids"
CHARTS = ROOT / "data" / "depth_charts.json"
ARC = "https://services2.arcgis.com/jQV6VMr2Loovu7GU/arcgis/rest/services/"
STATIC = "https://static.ags.aer.ca/files/document/DIG/"

LONG_SIDE = 160      # cells on the long side after resampling
MIN_CELL = 8.0       # metres; finer than this adds bytes, not shape
MARGIN_M = 150.0     # land kept around the outline
NODATA = -32768
MAX_LAND_DM = 300    # land height is capped at 30 m

# --- Alberta 10TM (NAD83 / GRS80) ------------------------------------------
A = 6378137.0
F = 1 / 298.257222101
E2 = F * (2 - F)
K0 = 0.9992
LON0 = math.radians(-115.0)
FE = 500000.0


def _m(phi):
    e4, e6 = E2 * E2, E2 * E2 * E2
    return A * ((1 - E2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                - (3 * E2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
                + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
                - (35 * e6 / 3072) * math.sin(6 * phi))


def tm_forward(lat, lon):
    """Latitude/longitude in degrees → 10TM easting, northing (Snyder 8-9, 8-10)."""
    phi, lam = math.radians(lat), math.radians(lon)
    ep2 = E2 / (1 - E2)
    n = A / math.sqrt(1 - E2 * math.sin(phi) ** 2)
    t = math.tan(phi) ** 2
    c = ep2 * math.cos(phi) ** 2
    a = (lam - LON0) * math.cos(phi)
    x = K0 * n * (a + (1 - t + c) * a ** 3 / 6 + (5 - 18 * t + t * t + 72 * c - 58 * ep2) * a ** 5 / 120)
    y = K0 * (_m(phi) + n * math.tan(phi) * (a * a / 2 + (5 - t + 9 * c + 4 * c * c) * a ** 4 / 24
                                             + (61 - 58 * t + t * t + 600 * c - 330 * ep2) * a ** 6 / 720))
    return FE + x, y


def tm_inverse(e, nn):
    """10TM easting, northing → latitude/longitude in degrees (Snyder 8-12)."""
    ep2 = E2 / (1 - E2)
    m = nn / K0
    mu = m / (A * (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    c1 = ep2 * math.cos(phi1) ** 2
    t1 = math.tan(phi1) ** 2
    n1 = A / math.sqrt(1 - E2 * math.sin(phi1) ** 2)
    r1 = A * (1 - E2) / (1 - E2 * math.sin(phi1) ** 2) ** 1.5
    d = (e - FE) / (n1 * K0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (d * d / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * ep2) * d ** 4 / 24
                                               + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * ep2 - 3 * c1 * c1) * d ** 6 / 720)
    lon = LON0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                  + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * ep2 + 24 * t1 * t1) * d ** 5 / 120) / math.cos(phi1)
    return math.degrees(lat), math.degrees(lon)


def from_web_mercator(x, y):
    """Web Mercator (EPSG 3857, the outline layer's own system) → 10TM."""
    lon = math.degrees(x / A)
    lat = math.degrees(2 * math.atan(math.exp(y / A)) - math.pi / 2)
    return tm_forward(lat, lon)


# --- fetch ------------------------------------------------------------------

def related_grid_dig(page_url):
    """The grid DIG listed under "Related Publications" on a contour page."""
    import urllib.request
    req = urllib.request.Request(page_url, headers={"User-Agent": "HZ-Trout-Map data build"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
    block = re.search(r"Related Publications.*?</div></div>", html, re.S)
    for dig, title in re.findall(r'href="/publications/all-publications/(dig-[0-9-]+)"[^>]*>([^<]*)',
                                 block.group(0) if block else ""):
        if "ascii" in title.lower() or "Elevation Model" in title:
            return dig.upper().replace("-", "_")
    return None


def fetch():
    import urllib.request
    RAW.mkdir(parents=True, exist_ok=True)
    charts = json.loads(CHARTS.read_text(encoding="utf-8"))["lakes"]
    index, levels = {}, {}
    for wid, c in sorted(charts.items()):
        grid = related_grid_dig(c["url"])
        if not grid:
            print("no grid for", c["name"], file=sys.stderr)
            continue
        zpath = RAW / (grid + ".zip")
        if not zpath.exists():
            req = urllib.request.Request(STATIC + grid + ".zip", headers={"User-Agent": "HZ-Trout-Map data build"})
            zpath.write_bytes(urllib.request.urlopen(req, timeout=120).read())
        index[wid] = {"name": c["name"], "contour_dig": c["dig"], "grid_dig": grid, "zip": zpath.name}
        if c["dig"] in levels:
            continue
        where = urllib.parse.urlencode({"where": "BATHYMETRY_DIG_NUM='%s'" % c["dig"], "outFields": "CONTOUR,CALC_DEP_M",
                                        "returnGeometry": "false", "f": "json"})
        cont = get_json(ARC + "Alberta_Lake_Bathymetry/FeatureServer/0/query?" + where)
        lv = {}
        for f in cont.get("features", []):
            a = f["attributes"]
            if a.get("CONTOUR") is not None and a.get("CALC_DEP_M") is not None:
                k = round(a["CONTOUR"] + a["CALC_DEP_M"], 1)
                lv[k] = lv.get(k, 0) + 1
        where = urllib.parse.urlencode({"where": "BATHYMETRY_DIG_NUM='%s'" % c["dig"], "outFields": "LAKE_NAME,ATS_GRID",
                                        "returnGeometry": "true", "maxAllowableOffset": 5, "geometryPrecision": 1, "f": "json"})
        bnd = get_json(ARC + "Lake_Boundary/FeatureServer/0/query?" + where)
        levels[c["dig"]] = {
            "levels": sorted(lv.items(), key=lambda kv: -kv[1]),
            "max_contour_depth_m": max((f["attributes"].get("CALC_DEP_M") or 0) for f in cont.get("features", [])) if cont.get("features") else None,
            "ats": [f["attributes"].get("ATS_GRID") for f in bnd.get("features", [])],
            "rings": [r for f in bnd.get("features", []) for r in f["geometry"]["rings"]],
            "rings_sr": (bnd.get("spatialReference") or {}).get("latestWkid") or (bnd.get("spatialReference") or {}).get("wkid"),
        }
    contours = {}
    for dig in sorted(levels):
        where = urllib.parse.urlencode({"where": "BATHYMETRY_DIG_NUM='%s'" % dig, "outFields": "CALC_DEP_M",
                                        "returnGeometry": "true", "maxAllowableOffset": 3, "geometryPrecision": 0, "f": "json"})
        cont = get_json(ARC + "Alberta_Lake_Bathymetry/FeatureServer/0/query?" + where)
        contours[dig] = {"sr": cont.get("spatialReference"),
                         "lines": [[f["attributes"]["CALC_DEP_M"], [[int(x), int(y)] for x, y in path]]
                                   for f in cont.get("features", []) for path in f["geometry"]["paths"]
                                   if f["attributes"].get("CALC_DEP_M") is not None]}
    (RAW / "contours.json").write_text(json.dumps(contours, separators=(",", ":")), encoding="utf-8")
    (RAW / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    (RAW / "levels_boundaries.json").write_text(json.dumps(levels), encoding="utf-8")
    print(len(index), "lakes,", len({v["grid_dig"] for v in index.values()}), "grids saved")


# --- build ------------------------------------------------------------------

def read_asc(zpath):
    z = zipfile.ZipFile(zpath)
    name = next(n for n in z.namelist() if n.lower().endswith(".asc"))
    tok = z.read(name).decode("latin1").split()
    hdr = {tok[i].lower(): float(tok[i + 1]) for i in range(0, 12, 2)}
    vals = [float(v) for v in tok[12:]]
    nc, nr = int(hdr["ncols"]), int(hdr["nrows"])
    assert len(vals) == nc * nr, zpath
    nod = hdr["nodata_value"]
    grid = [None if v == nod else v for v in vals]
    # centre of the north-west cell
    x0 = hdr["xllcorner"] + hdr["cellsize"] / 2
    y0 = hdr["yllcorner"] + (nr - 0.5) * hdr["cellsize"]
    return {"nc": nc, "nr": nr, "cell": hdr["cellsize"], "x0": x0, "y0": y0, "v": grid}


def sample(g, e, n):
    """Bilinear lakebed height at 10TM e, n; None where no corner has data."""
    fx = (e - g["x0"]) / g["cell"]
    fy = (g["y0"] - n) / g["cell"]
    i, j = math.floor(fx), math.floor(fy)
    tx, ty = fx - i, fy - j
    acc = wsum = 0.0
    for di, dj, w in ((0, 0, (1 - tx) * (1 - ty)), (1, 0, tx * (1 - ty)), (0, 1, (1 - tx) * ty), (1, 1, tx * ty)):
        x, y = i + di, j + dj
        if 0 <= x < g["nc"] and 0 <= y < g["nr"]:
            v = g["v"][y * g["nc"] + x]
            if v is not None and w > 0:
                acc += v * w
                wsum += w
    return acc / wsum if wsum > 1e-9 else None


def row_crossings(rings, n):
    """Eastings where the outline crosses northing n, sorted. Between the 1st
    and 2nd, 3rd and 4th, … crossing is water (even-odd, so islands are holes)."""
    xs = []
    for r in rings:
        k = len(r) - 1
        for i in range(len(r)):
            xi, yi = r[i]
            xk, yk = r[k]
            if (yi > n) != (yk > n):
                xs.append((xk - xi) * (n - yi) / (yk - yi) + xi)
            k = i
    return sorted(xs)


def components(mask, w, h):
    seen = [False] * (w * h)
    comps = []
    for s in range(w * h):
        if not mask[s] or seen[s]:
            continue
        stack, cells = [s], []
        seen[s] = True
        while stack:
            c = stack.pop()
            cells.append(c)
            x, y = c % w, c // w
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < w and 0 <= ny < h:
                    t = ny * w + nx
                    if mask[t] and not seen[t]:
                        seen[t] = True
                        stack.append(t)
        comps.append(cells)
    return comps


def pick_level(beds, candidates):
    """The contour water level that fits this piece of water: shore beds sit
    just under it, so take the level nearest above the 90th percentile."""
    if not candidates:
        return None
    if len(candidates) == 1 or not beds:
        return candidates[0][0]
    p90 = sorted(beds)[int(len(beds) * 0.9)]
    above = [lv for lv, _ in candidates if lv >= p90 - 1.0]
    return min(above, key=lambda lv: lv - p90) if above else candidates[0][0]


RELAX_SWEEPS = 400
OMEGA = 1.85


def burn_contours(lines, mask, w, h, x0, y0, cell):
    """Depth fixed by the contour lines, per cell; None where no line passes."""
    fixed = [None] * (w * h)
    for depth, path in lines:
        for (ax, ay), (bx, by) in zip(path, path[1:]):
            steps = max(1, int(math.hypot(bx - ax, by - ay) / (cell * 0.5)))
            for s in range(steps + 1):
                t = s / steps
                i = int(round((ax + (bx - ax) * t - x0) / cell))
                j = int(round((y0 - (ay + (by - ay) * t)) / cell))
                if 0 <= i < w and 0 <= j < h and mask[j * w + i]:
                    k = j * w + i
                    fixed[k] = depth if fixed[k] is None else max(fixed[k], depth)
    return fixed


def relax(depth, fixed, mask, w, h):
    """Fill the cells between contour lines with the smoothest surface: each
    free water cell moves toward the mean of its 4 neighbours, land counts as
    0 m (the shore), contour cells stay put. Successive over-relaxation."""
    free = [k for k in range(w * h) if mask[k] and fixed[k] is None]
    for k in range(w * h):
        if fixed[k] is not None:
            depth[k] = fixed[k]
    for _ in range(RELAX_SWEEPS):
        for k in free:
            x = k % w
            a = depth[k - 1] if x > 0 and mask[k - 1] else 0.0
            b = depth[k + 1] if x < w - 1 and mask[k + 1] else 0.0
            c = depth[k - w] if k >= w and mask[k - w] else 0.0
            d = depth[k + w] if k + w < w * h and mask[k + w] else 0.0
            depth[k] += OMEGA * ((a + b + c + d) / 4 - depth[k])
    return depth


def build_one(grid_dig, raw, info, lines):
    g = read_asc(RAW / raw["zip"])
    rings = info["rings"]
    if info.get("rings_sr") in (3857, 102100):
        rings = [[from_web_mercator(x, y) for x, y in r] for r in rings]
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    e_min, e_max = min(xs) - MARGIN_M, max(xs) + MARGIN_M
    n_min, n_max = min(ys) - MARGIN_M, max(ys) + MARGIN_M
    cell = max(MIN_CELL, max(e_max - e_min, n_max - n_min) / LONG_SIDE)
    w = int(math.ceil((e_max - e_min) / cell)) + 1
    h = int(math.ceil((n_max - n_min) / cell)) + 1
    x0, y0 = e_min, n_max
    mask, bed = [False] * (w * h), [None] * (w * h)
    for j in range(h):
        n = y0 - j * cell
        xs = row_crossings(rings, n)
        for a, b in zip(xs[0::2], xs[1::2]):
            for i in range(max(0, math.ceil((a - x0) / cell)), min(w - 1, math.floor((b - x0) / cell)) + 1):
                mask[j * w + i] = True
        for i in range(w):
            bed[j * w + i] = sample(g, x0 + i * cell, n)
    level = [None] * (w * h)
    used = set()
    for comp in components(mask, w, h):
        lv = pick_level([bed[c] for c in comp if bed[c] is not None], info["levels"])
        used.add(lv)
        for c in comp:
            level[c] = lv
    main_level = info["levels"][0][0] if info["levels"] else None
    start = [0.0] * (w * h)
    for k in range(w * h):
        if mask[k]:
            start[k] = 0.2 if bed[k] is None or level[k] is None else max(0.2, level[k] - bed[k])
    fixed = burn_contours(lines, mask, w, h, x0, y0, cell)
    depth = relax(start, fixed, mask, w, h) if any(f is not None for f in fixed) else start
    out = []
    deepest = 0.0
    for k in range(w * h):
        b = bed[k]
        if mask[k]:
            d = max(0.2, depth[k])
            deepest = max(deepest, d)
            out.append(min(32767, int(round(d * 10))))
        elif b is None or main_level is None:
            out.append(NODATA)
        else:
            out.append(-max(1, min(MAX_LAND_DM, int(round((b - main_level) * 10)))))
    ce, cn = x0 + (w - 1) * cell / 2, y0 - (h - 1) * cell / 2
    lat0, lon0 = tm_inverse(ce, cn)
    e0, n0 = tm_forward(lat0, lon0)
    de_dlat = (tm_forward(lat0 + 0.001, lon0)[0] - tm_forward(lat0 - 0.001, lon0)[0]) / 0.002
    dn_dlat = (tm_forward(lat0 + 0.001, lon0)[1] - tm_forward(lat0 - 0.001, lon0)[1]) / 0.002
    de_dlon = (tm_forward(lat0, lon0 + 0.001)[0] - tm_forward(lat0, lon0 - 0.001)[0]) / 0.002
    dn_dlon = (tm_forward(lat0, lon0 + 0.001)[1] - tm_forward(lat0, lon0 - 0.001)[1]) / 0.002
    north = math.degrees(math.atan2(de_dlat, dn_dlat))
    cells = struct.pack("<%dh" % len(out), *out)
    return cells, {
        "schema": 1,
        "source": "Alberta Geological Survey %s (lakebed grid) and %s (contours, water level)" % (
            grid_dig.replace("_", " ", 1).replace("_", "-"), raw["contour_dig"]),
        "licence": "Open Government Licence - Alberta",
        "w": w, "h": h, "cell_m": round(cell, 2),
        "x0": round(x0, 1), "y0": round(y0, 1),
        "centre": [round(lat0, 6), round(lon0, 6)],
        "affine": [round(e0, 2), round(n0, 2), round(lat0, 6), round(lon0, 6),
                   round(de_dlat, 3), round(de_dlon, 3), round(dn_dlat, 3), round(dn_dlon, 3)],
        "north_deg": round(north, 3),
        "level_m": sorted(v for v in used if v is not None),
        "max_depth_m": round(deepest, 1),
        "contour_max_depth_m": info.get("max_contour_depth_m"),
        "ats": info.get("ats"),
    }


def water_summary(cells, cell_m):
    """Build 4: mean depth and water area from a saved grid, so Lake info can say
    "measured" for the surveyed lakes. Water cells are the positive ones (dm)."""
    vals = struct.unpack("<%dh" % (len(cells) // 2), cells)
    water = [v for v in vals if v > 0 and v != NODATA]
    if not water:
        return {"mean_depth_m": None, "water_ha": None}
    return {"mean_depth_m": round(sum(water) / len(water) / 10, 1),
            "water_ha": round(len(water) * cell_m * cell_m / 10000, 1)}


def add_summaries():
    """Add the mean depth to index.json from the saved grid files, without a rebuild."""
    path = OUT / "index.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    for g in index["grids"].values():
        g.update(water_summary((ROOT / g["file"]).read_bytes(), g["cell_m"]))
    path.write_text(json.dumps(index, indent=1, sort_keys=True), encoding="utf-8")
    print("%d grids: mean depth added" % len(index["grids"]))


def build():
    raw_index = json.loads((RAW / "index.json").read_text(encoding="utf-8"))
    info = json.loads((RAW / "levels_boundaries.json").read_text(encoding="utf-8"))
    contours = json.loads((RAW / "contours.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    index, done = {}, {}
    for wid, raw in sorted(raw_index.items()):
        gd = raw["grid_dig"]
        if gd not in done:
            cells, meta = build_one(gd, raw, info[raw["contour_dig"]],
                                    contours.get(raw["contour_dig"], {}).get("lines", []))
            meta["file"] = "data/depth_grids/%s.bin" % gd
            meta.update(water_summary(cells, meta["cell_m"]))
            (OUT / (gd + ".bin")).write_bytes(cells)
            done[gd] = meta
        index[wid] = {"name": raw["name"], "grid": gd}
    (OUT / "index.json").write_text(json.dumps({"schema": 1, "grids": done, "lakes": index}, indent=1, sort_keys=True),
                                    encoding="utf-8")
    total = sum((OUT / (gd + ".bin")).stat().st_size for gd in done) + (OUT / "index.json").stat().st_size
    print("%d lakes, %d grid files, %.0f KB" % (len(index), len(done), total / 1024))
    return index, done


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fetch", action="store_true", help="download into data/raw/ags_bathymetry first")
    ap.add_argument("--summaries", action="store_true", help="only add mean depth to index.json from the saved grids")
    args = ap.parse_args()
    if args.summaries:
        add_summaries()
        return 0
    if args.fetch:
        fetch()
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
