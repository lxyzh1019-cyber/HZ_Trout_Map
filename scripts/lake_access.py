"""Boat launches and roads around the lakes with a 3D depth model (decision 23 A).

The lake data says only "Boat launch: yes" for some lakes, with no position.
OpenStreetMap has the positions: boat launches are tagged leisure=slipway, and
roads are highway ways. This asks the Overpass API once for the box around
each lakebed grid, keeps what lies on that grid, and saves it for the 3D view.

Usage:

    python -I scripts/lake_access.py --fetch <cache folder>   # ask Overpass, save the answers
    python -I scripts/lake_access.py <cache folder>           # build data/lake_access.json

The build reads only the saved answers, so it repeats without a network. The
cache folder lives outside the repository.

Licence: OpenStreetMap data is © OpenStreetMap contributors, under the Open
Database License (ODbL 1.0). The saved file is a derived database under the same
licence; the 3D view carries the credit line OpenStreetMap asks for.

What is kept, per lakebed grid
    launches   leisure=slipway (node, or the middle of a way) on the grid, within
               LAUNCH_NEAR_M of the grid's water; name and access=private kept
    roads      highway ways of ROAD_KINDS, cut to the grid (one cell outside
               allowed), simplified to SIMPLIFY_M; pieces under MIN_ROAD_M dropped.
               Service roads and tracks only within SERVICE_NEAR_M of the water.

Writes data/lake_access.json:
    {"source", "licence", "credit", "url", "retrieved", "kinds",
     "grids": {"DIG_2008_0366": {"launches": [{"lat", "lon", "name"?, "private"?}],
                                 "roads": [{"kind", "name"?, "pts": [[lat, lon], ...]}]}}}
"""

import json
import math
import struct
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import depth_grids

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "lake_access.json"
# The main Overpass server first, then a public mirror of the same OpenStreetMap data
# (decision 26 A: the main one dropped every connection from the build session on 2026-11-06).
SERVERS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
USER_AGENT = "HZ-Trout-Map data build (github.com/lxyzh1019-cyber/HZ_Trout_Map)"
ROAD_KINDS = ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
              "residential", "service", "track"]
NEAR_WATER_ONLY = {"service", "track"}
LAUNCH_NEAR_M = 150.0
SERVICE_NEAR_M = 400.0
SIMPLIFY_M = 12.0
MIN_ROAD_M = 60.0
BATCH = 4                 # grids per request: 12 made the mirror time out (504)


def grids():
    """Each lakebed grid once: (stem, meta)."""
    idx = json.loads((DATA / "depth_grids" / "index.json").read_text(encoding="utf-8"))
    out = {}
    for meta in idx["grids"].values():
        out[Path(meta["file"]).stem] = meta
    return sorted(out.items())


def bbox(meta):
    """(south, west, north, east) around the grid, from its corner cells."""
    c = meta["cell_m"]
    xs = (meta["x0"] - c, meta["x0"] + meta["w"] * c)
    ys = (meta["y0"] + c, meta["y0"] - meta["h"] * c)
    pts = [depth_grids.tm_inverse(x, y) for x in xs for y in ys]
    lats, lons = [p[0] for p in pts], [p[1] for p in pts]
    return round(min(lats), 5), round(min(lons), 5), round(max(lats), 5), round(max(lons), 5)


def query(boxes):
    parts = []
    kinds = "|".join(ROAD_KINDS)
    for s, w, n, e in boxes:
        b = "%s,%s,%s,%s" % (s, w, n, e)
        parts.append('nwr["leisure"="slipway"](%s);' % b)
        parts.append('way["highway"~"^(%s)$"](%s);' % (kinds, b))
    return "[out:json][timeout:180];(" + "".join(parts) + ");out tags geom;"


def ask(q, tries=4):
    """The answer and the server that gave it. Each server gets a few tries, with a
    longer wait each time (429 or 504 when busy)."""
    body = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for url in SERVERS:
        for t in range(tries):
            req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.loads(r.read().decode("utf-8")), url
            except Exception as e:
                last = e
                time.sleep(15 * (t + 1))
    raise SystemExit("no Overpass server answered: %s" % last)


def fetch(cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    # Grids already answered are skipped, so a run cut short by a busy server goes on
    # where it stopped; each saved answer names its own grids.
    done = set()
    for f in cache.glob("batch_*.json"):
        done.update(json.loads(f.read_text(encoding="utf-8"))["stems"])
    gs = [g for g in grids() if g[0] not in done]
    for k in range(0, len(gs), BATCH):
        part = gs[k:k + BATCH]
        f = cache / ("batch_%s.json" % part[0][0])
        ans, url = ask(query([bbox(m) for _, m in part]))
        f.write_text(json.dumps({"stems": [s for s, _ in part], "server": url, "answer": ans}), encoding="utf-8")
        time.sleep(5)               # one request at a time, with a pause: Overpass's fair use
    (cache / "retrieved.txt").write_text(time.strftime("%Y-%m-%d", time.gmtime()), encoding="utf-8")


class Grid:
    def __init__(self, meta):
        self.m = meta
        self.w, self.h, self.c = meta["w"], meta["h"], meta["cell_m"]
        raw = (ROOT / meta["file"]).read_bytes()
        cells = struct.unpack("<%dh" % (len(raw) // 2), raw)
        self.water = [v > 0 for v in cells]
        # Distance to water, in cells (4-neighbour steps), for every cell.
        n = self.w * self.h
        dist = [-1] * n
        q = [k for k in range(n) if self.water[k]]
        for k in q:
            dist[k] = 0
        a = 0
        while a < len(q):
            k = q[a]; a += 1
            x = k % self.w
            for m in (k - 1 if x > 0 else -1, k + 1 if x < self.w - 1 else -1, k - self.w, k + self.w):
                if 0 <= m < n and dist[m] < 0:
                    dist[m] = dist[k] + 1
                    q.append(m)
        self.dist = dist

    def cell(self, lat, lon):
        e, n = depth_grids.tm_forward(lat, lon)
        return (e - self.m["x0"]) / self.c, (self.m["y0"] - n) / self.c

    def inside(self, i, j, margin=1.0):
        return -margin <= i <= self.w - 1 + margin and -margin <= j <= self.h - 1 + margin

    def water_m(self, i, j):
        """Metres from (i, j) to the nearest water cell; None off the grid."""
        ii, jj = int(round(i)), int(round(j))
        if not (0 <= ii < self.w and 0 <= jj < self.h):
            return None
        d = self.dist[jj * self.w + ii]
        return None if d < 0 else d * self.c


def metres(a, b):
    k = 111320.0
    return math.hypot((a[0] - b[0]) * k, (a[1] - b[1]) * k * math.cos(math.radians(a[0])))


def simplify(pts, tol):
    """Douglas-Peucker in metres."""
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    best, at = 0.0, 0
    for k in range(1, len(pts) - 1):
        p = pts[k]
        ab = metres(a, b)
        if ab == 0:
            d = metres(a, p)
        else:
            # distance from p to the line a-b, on a local flat plane
            kx = 111320.0 * math.cos(math.radians(a[0]))
            ax, ay, bx, by, x, y = a[1] * kx, a[0] * 111320.0, b[1] * kx, b[0] * 111320.0, p[1] * kx, p[0] * 111320.0
            t = max(0.0, min(1.0, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / (ab * ab)))
            d = math.hypot(x - (ax + t * (bx - ax)), y - (ay + t * (by - ay)))
        if d > best:
            best, at = d, k
    if best <= tol:
        return [a, b]
    return simplify(pts[:at + 1], tol)[:-1] + simplify(pts[at:], tol)


def length_m(pts):
    return sum(metres(p, q) for p, q in zip(pts, pts[1:]))


def clip_segment(a, b, lo_i, hi_i, lo_j, hi_j):
    """The part of segment a-b (cell coordinates) inside the box, as (t0, t1), or None
    (Liang-Barsky)."""
    t0, t1 = 0.0, 1.0
    di, dj = b[0] - a[0], b[1] - a[1]
    for p, q in ((-di, a[0] - lo_i), (di, hi_i - a[0]), (-dj, a[1] - lo_j), (dj, hi_j - a[1])):
        if p == 0:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return None
    return t0, t1


def clip_line(g, latlons):
    """A road cut to the grid (one cell outside allowed), exactly at the edge: a list of
    pieces, each [(lat, lon, i, j), ...]."""
    lo_i, hi_i, lo_j, hi_j = -1.0, g.w, -1.0, g.h
    cells = [(lat, lon) + g.cell(lat, lon) for lat, lon in latlons]
    pieces, piece = [], []

    def at(a, b, t):
        return tuple(a[k] + (b[k] - a[k]) * t for k in range(4))

    for a, b in zip(cells, cells[1:]):
        c = clip_segment(a[2:], b[2:], lo_i, hi_i, lo_j, hi_j)
        if c is None:
            if piece:
                pieces.append(piece); piece = []
            continue
        start, end = at(a, b, c[0]), at(a, b, c[1])
        if not piece:
            piece = [start]
        piece.append(end)
        if c[1] < 1.0:                      # leaves the grid here
            pieces.append(piece); piece = []
    if piece:
        pieces.append(piece)
    return [[(round(p[0], 5), round(p[1], 5), p[2], p[3]) for p in pc] for pc in pieces if len(pc) >= 2]


def keep_for(g, elements):
    launches, roads, seen = [], [], set()
    for el in elements:
        tags = el.get("tags") or {}
        key = (el["type"], el["id"])
        if key in seen:
            continue
        if tags.get("leisure") == "slipway":
            if el["type"] == "node":
                lat, lon = el["lat"], el["lon"]
            else:
                geom = el.get("geometry") or []
                if not geom:
                    continue
                lat = sum(p["lat"] for p in geom) / len(geom)
                lon = sum(p["lon"] for p in geom) / len(geom)
            i, j = g.cell(lat, lon)
            near = g.water_m(i, j)
            if near is None or near > LAUNCH_NEAR_M:
                continue
            seen.add(key)
            item = {"lat": round(lat, 5), "lon": round(lon, 5)}
            if tags.get("name"):
                item["name"] = tags["name"]
            if tags.get("access") in ("private", "no"):
                item["private"] = True
            launches.append(item)
            continue
        kind = tags.get("highway")
        if el["type"] != "way" or kind not in ROAD_KINDS:
            continue
        seen.add(key)
        pieces = clip_line(g, [(p["lat"], p["lon"]) for p in (el.get("geometry") or []) if p])
        for pc in pieces:
            if kind in NEAR_WATER_ONLY:
                near = [g.water_m(i, j) for _, _, i, j in pc]
                near = [d for d in near if d is not None]
                if not near or min(near) > SERVICE_NEAR_M:
                    continue
            pts = simplify([(a, b) for a, b, _, _ in pc], SIMPLIFY_M)
            if length_m(pts) < MIN_ROAD_M:
                continue
            r = {"kind": kind, "pts": [[a, b] for a, b in pts]}
            name = tags.get("name") or tags.get("ref")
            if name:
                r["name"] = name
            roads.append(r)
    launches.sort(key=lambda x: (x["lat"], x["lon"]))
    roads.sort(key=lambda r: (r["kind"], r["pts"][0]))
    return {"launches": launches, "roads": roads}


def build(cache):
    cache = Path(cache)
    metas = dict(grids())
    out, servers = {}, set()
    for f in sorted(cache.glob("batch_*.json")):
        saved = json.loads(f.read_text(encoding="utf-8"))
        servers.add(urllib.parse.urlparse(saved.get("server") or SERVERS[0]).netloc)
        elements = saved["answer"].get("elements", [])
        for stem in saved["stems"]:
            out[stem] = keep_for(Grid(metas[stem]), elements)
    missing = sorted(set(metas) - set(out))
    if missing:
        raise SystemExit("no saved answer for %d grids, e.g. %s: run --fetch" % (len(missing), missing[0]))
    doc = {
        "source": "OpenStreetMap, via the Overpass API (%s)" % ", ".join(sorted(servers)),
        "licence": "Open Database License (ODbL 1.0)",
        "credit": "© OpenStreetMap contributors",
        "url": "https://www.openstreetmap.org/copyright",
        "retrieved": (cache / "retrieved.txt").read_text(encoding="utf-8").strip(),
        "kinds": {"launch": "leisure=slipway", "roads": ROAD_KINDS},
        "grids": out,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    nl = sum(len(v["launches"]) for v in out.values())
    nr = sum(len(v["roads"]) for v in out.values())
    with_l = sum(1 for v in out.values() if v["launches"])
    print("%d grids: %d boat launches on %d of them, %d road pieces -> %s (%d kB)"
          % (len(out), nl, with_l, nr, OUT.relative_to(ROOT), OUT.stat().st_size // 1024))


def main(argv):
    if len(argv) == 3 and argv[1] == "--fetch":
        fetch(argv[2])
        build(argv[2])
    elif len(argv) == 2:
        build(argv[1])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
