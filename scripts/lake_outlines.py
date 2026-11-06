"""Lake shorelines for matching the owner's imported spots to lakes (Build 5 Stage 3a,
decision 30).

The app knows most lakes only by a centre point, and many listed areas are wrong
(Sylvan Lake is listed at 5.3 ha; its lakebed survey has 4,226 ha of water), so a
spot near a big lake's shore could not be matched from the centre point. This keeps
each lake's real outline from the federal CanVec water layer.

Usage (CanVec 1:50 000 Alberta water layer, the same download waterbodies.py reads):

    cd scripts && python3 lake_outlines.py <canvec folder or zip>

For each lake in the app (the stocked lakes in data/lakes_*.json and the waters not
stocked in data/waters_unstocked.json):
    rings    the CanVec outline that contains the lake's point; else an outline with
             the lake's name within NAMED_NEAR_KM of the point; plus every piece with
             the piece joined to it at a map sheet edge (CanVec cuts lakes there). The
             outer edges only (a spot on an island is on the lake), simplified to
             SIMPLIFY_M. Two lakes can share an outline (Peerless and Graham Lakes):
             the app then takes the lake whose point is nearer.
    circle   no such outline: a circle at the lake's point, its radius from the
             lakebed survey's water area where there is one, else the listed area,
             plus CIRCLE_PAD_M (the build list's "area plus 1 km").

Writes data/lake_outlines.json:
    {"source", "licence", "licence_url", "simplify_m", "counts",
     "lakes": {"<lake key>": {"rings": [[lat0, lon0, dlat1, dlon1, ...], ...]}   # 1e-5 degrees, deltas
                          | {"circle": [lat, lon, radius_m], "from": "survey" | "listed" | "none"}}}

The app loads it only while importing spots: each spot keeps the lake it matched.
"""

import glob
import json
import math
import sys
from pathlib import Path

import waterbodies as wb

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "lake_outlines.json"
SIMPLIFY_M = 25.0
NAMED_NEAR_KM = 1.0
CIRCLE_PAD_M = 1000.0
CELL = 0.1                  # degrees, for the point index


def app_lakes():
    """key -> {name, lat, lon, area_ha} for every lake the app shows (not rivers)."""
    out = {}
    for f in sorted(glob.glob(str(DATA / "lakes_20*.json"))):
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        for x in (doc["lakes"] if isinstance(doc, dict) else doc):
            key = x.get("lake_id") or x.get("ats")
            if key and x.get("lat") is not None:
                out[key] = {"name": x.get("name") or "", "lat": x["lat"], "lon": x["lon"],
                            "area_ha": x.get("surface_area_ha")}
    for x in json.loads((DATA / "waters_unstocked.json").read_text(encoding="utf-8"))["lakes"]:
        key = x.get("lake_id") or x.get("ats")
        if key and x.get("lat") is not None and key not in out:
            out[key] = {"name": x.get("name") or "", "lat": x["lat"], "lon": x["lon"], "area_ha": None}
    return out


def survey_ha():
    """key -> water area (ha) from the lakebed survey grid, for the 114 lakes with one."""
    idx = json.loads((DATA / "depth_grids" / "index.json").read_text(encoding="utf-8"))
    out = {}
    for key, v in idx["lakes"].items():
        g = idx["grids"].get(v["grid"] if isinstance(v, dict) else v)
        if g and g.get("water_ha"):
            out[key] = g["water_ha"]
    return out


def ring_dist_km(p, ring):
    return min(wb.seg_dist(p, a, b) for a, b in zip(ring, ring[1:] + ring[:1]))


def simplify_ring(ring, tol_m=SIMPLIFY_M):
    """Douglas-Peucker on a closed ring (iterative), keeping at least a triangle."""
    if len(ring) <= 4:
        return list(ring)
    pts = list(ring)
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    # Split at the point farthest from the first, so both halves are open lines.
    far = max(range(len(pts)), key=lambda k: (pts[k][0] - pts[0][0]) ** 2 + (pts[k][1] - pts[0][1]) ** 2)
    keep = {0, far, len(pts) - 1}
    stack = [(0, far), (far, len(pts) - 1)]
    tol = tol_m / 1000.0
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        best, idx = 0.0, -1
        for k in range(a + 1, b):
            d = wb.seg_dist(pts[k], pts[a], pts[b])
            if d > best:
                best, idx = d, k
        if best > tol:
            keep.add(idx)
            stack.append((a, idx))
            stack.append((idx, b))
    out = [pts[k] for k in sorted(keep)]
    return out if len(out) >= 3 else pts[:3]


def encode(ring):
    """[lat0, lon0, dlat, dlon, ...] in 1e-5 degrees (about 1 m)."""
    flat, last = [], (0, 0)
    for lat, lon in ring:
        q = (round(lat * 1e5), round(lon * 1e5))
        flat += [q[0] - last[0], q[1] - last[1]]
        last = q
    return flat


def decode(flat):
    out, lat, lon = [], 0, 0
    for k in range(0, len(flat), 2):
        lat += flat[k]; lon += flat[k + 1]
        out.append((lat / 1e5, lon / 1e5))
    return out


def on_sheet_line(axis, v):
    """A 1:50 000 map sheet edge: a multiple of 0.25 degrees of latitude or 0.5 of longitude."""
    step = 0.25 if axis == "lat" else 0.5
    return abs(v / step - round(v / step)) < 1e-6


def find_outlines(path, lakes):
    """key -> (how, [ring, ...]) with how "inside" or "named".

    CanVec cuts a lake at each 1:50 000 map sheet's edge (every 15' of latitude and
    30' of longitude), so a big lake is several pieces, often with no name
    (Lesser Slave Lake's first piece ends at 116 W). The lake gets every piece that
    shares a cut edge with it, directly or through another piece."""
    grid = {}
    for key, x in lakes.items():
        grid.setdefault((int(math.floor(x["lat"] / CELL)), int(math.floor(x["lon"] / CELL))), []).append(key)
    wanted = {key: set(wb.variants(x["name"])) | {wb.norm(x["name"])} for key, x in lakes.items()}
    pad = NAMED_NEAR_KM / 111.0 * 1.6
    best = {}                    # key -> (how, shape index, area)
    boxes = []
    r = wb.canvec(path, "waterbody_2")
    for i, shp in enumerate(r.iterShapes()):
        if not shp.points:
            boxes.append(None)
            continue
        x0, y0, x1, y1 = shp.bbox
        boxes.append((x0, y0, x1, y1))
        cands = []
        for ci in range(int(math.floor((y0 - pad) / CELL)), int(math.floor((y1 + pad) / CELL)) + 1):
            for cj in range(int(math.floor((x0 - pad * 1.7) / CELL)), int(math.floor((x1 + pad * 1.7) / CELL)) + 1):
                for key in grid.get((ci, cj), ()):
                    x = lakes[key]
                    if y0 - pad <= x["lat"] <= y1 + pad and x0 - pad * 1.7 <= x["lon"] <= x1 + pad * 1.7:
                        cands.append(key)
        if not cands:
            continue
        _lat, _lon, area, ring, _box = wb.outline_of(shp.parts, shp.points)
        name = None
        for key in cands:
            p = (lakes[key]["lat"], lakes[key]["lon"])
            if wb.inside(p, list(ring)):
                cur = best.get(key)
                # The smallest outline that holds the point wins (a pond beside a big lake's box).
                if cur is None or cur[0] != "inside" or area < cur[2]:
                    best[key] = ("inside", i, area)
                continue
            if best.get(key, ("",))[0] == "inside":
                continue
            if name is None:
                rec = r.record(i)
                name = wb.norm(rec["name_en"] or rec["namelk1en"] or "")
            if name and name in wanted[key] and ring_dist_km(p, list(ring)) <= NAMED_NEAR_KM:
                cur = best.get(key)
                if cur is None or area > cur[2]:
                    best[key] = ("named", i, area)

    rings = {}

    def piece(i):
        if i not in rings:
            shp = r.shape(i)
            rings[i] = list(wb.outline_of(shp.parts, shp.points)[3])
        return rings[i]

    sheet_side = {}                  # (axis, value) -> [(lo, hi, shape index)]
    for i, box in enumerate(boxes):
        if box is None:
            continue
        x0, y0, x1, y1 = box
        for axis, v, lo, hi in (("lat", y0, x0, x1), ("lat", y1, x0, x1), ("lon", x0, y0, y1), ("lon", x1, y0, y1)):
            if on_sheet_line(axis, v):
                sheet_side.setdefault((axis, round(v, 4)), []).append((lo, hi, i))

    def cuts(i):
        """The piece's edges that lie on a map sheet line: [(axis, value, lo, hi)]."""
        ring = piece(i)
        out = []
        for (y1, x1), (y2, x2) in zip(ring, ring[1:] + ring[:1]):
            if abs(y1 - y2) < 1e-7 and on_sheet_line("lat", y1):
                out.append(("lat", round(y1, 4), min(x1, x2), max(x1, x2)))
            elif abs(x1 - x2) < 1e-7 and on_sheet_line("lon", x1):
                out.append(("lon", round(x1, 4), min(y1, y2), max(y1, y2)))
        return out

    def neighbours(i):
        found = set()
        for axis, v, lo, hi in cuts(i):
            for blo, bhi, k in sheet_side.get((axis, v), ()):
                if k == i or bhi < lo - 1e-7 or blo > hi + 1e-7:
                    continue
                if any(a2 == axis and v2 == v and l2 < hi - 1e-7 and h2 > lo + 1e-7 for a2, v2, l2, h2 in cuts(k)):
                    found.add(k)
        return found

    out = {}
    for key, (how, i, _area) in sorted(best.items()):
        group, todo = {i}, [i]
        while todo:
            for k in neighbours(todo.pop()):
                if k not in group:
                    group.add(k); todo.append(k)
        out[key] = (how, [piece(g) for g in sorted(group)])
    return out


def build(path):
    lakes = app_lakes()
    survey = survey_ha()
    found = find_outlines(path, lakes)
    out, counts = {}, {"inside": 0, "named": 0, "circle_survey": 0, "circle_listed": 0, "circle_none": 0}
    for key in sorted(lakes):
        x = lakes[key]
        if key in found:
            how, rs = found[key]
            out[key] = {"rings": [encode(simplify_ring(ring)) for ring in rs]}
            counts[how] += 1
            continue
        ha, frm = (survey[key], "survey") if key in survey else (x["area_ha"], "listed") if x["area_ha"] else (0.0, "none")
        radius = math.sqrt(ha * 10000.0 / math.pi) + CIRCLE_PAD_M
        out[key] = {"circle": [round(x["lat"], 5), round(x["lon"], 5), round(radius)], "from": frm}
        counts["circle_" + frm] += 1
    doc = {
        "source": "CanVec 1:50 000 water bodies (Natural Resources Canada), outer edge simplified to %d m" % SIMPLIFY_M,
        "licence": wb.LICENCE, "licence_url": wb.LICENCE_URL, "simplify_m": SIMPLIFY_M,
        "counts": counts, "lakes": out,
    }
    OUT.write_text(json.dumps(doc, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    print("%d lakes: %s -> %s (%d kB)" % (len(out), counts, OUT.relative_to(ROOT), OUT.stat().st_size // 1024))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    build(sys.argv[1])
