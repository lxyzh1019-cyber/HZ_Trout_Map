"""Build 5 Stage 2: the waters the 2026 sportfishing guide names that the
stocking reports never list, and the guide's river stretches.

The map began as a map of stocked lakes. The guide's tables name about 460
lakes, reservoirs and ponds and about 60 rivers and creeks, most of them never
stocked. This places each one and copies its rule row from the guide, so the
app can score it and show its rules like any stocked lake.

Usage (network inputs are downloaded first, then read from disk):

    python -I scripts/waterbodies.py <canvec_250K_AB_Hydro folder or .zip> <cgn_ab_csv_eng.zip>

Inputs
    the guide          data/raw/alberta-sportfishing-regulations-2026-tables.pdf (read by regulations.py)
    place names        NRCan CGNDB, Alberta CSV (Open Government Licence - Canada)
    water data         NRCan CanVec 1:250,000 Hydro, Alberta (waterbody_2, watercourse_1;
                       Open Government Licence - Canada)
    the stocked lakes  data/lakes_20*.json and data/lake_regulations.json (to leave them out)

Writes
    data/waters_unstocked.json   lakes the guide names that are not on the map yet
    data/rivers.json            river and creek stretches, simplified lines and forecast spots
    data/waters_review.csv      guide lakes that could not be placed with confidence

How a lake is placed, first match wins, and the label says which:
    "ats"          the guide prints a land location (e.g. Gleniffer Lake, 30-35-2-W5)
    "outline"      exactly one CanVec lake outline of that name in the lake's zone
    "place names"  exactly one CGNDB lake point of that name in the lake's zone
A name with no candidate, or more than one in the zone, is not placed: it goes
to the review file. Guessing a position is worse than leaving a lake off.

The zone of a point is the zone of the nearest stocked lakes (the guide's
Watershed Units have no published outline in this repository). That is good
enough to tell the three Gull Lakes apart, and the review file catches the rest.
"""

import csv
import io
import json
import math
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import shapefile  # pyshp

import ats
import regulations

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
PDF = DATA / "raw" / "alberta-sportfishing-regulations-2026-tables.pdf"

LAKE_TERMS = {"Lake", "Lakes", "Reservoir", "Pond", "Ponds", "Slough"}
FLOWING = re.compile(r"\b(River|Creek|Brook)\b")
NOT_LINES = ("Station", "Wilderness Area", "Provincial Park", "Backcountry", "Tributaries and Outflows")
SPOT_KM = 25.0
SIMPLIFY_KM = 0.15
ATS_RE = re.compile(r"(?:(NE|NW|SE|SW)\s*)?(\d{1,2})-(\d{1,3})-(\d{1,2})-(W[456])")
LICENCE = "Open Government Licence - Canada"
LICENCE_URL = "https://open.canada.ca/en/open-government-licence-canada"


def km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, h)))


def norm(name):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (name or "").casefold())).strip()


def slug(name):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (name or "").casefold())).strip("-")


def variants(name):
    """The guide's name, then the names in it: "Ethel (Bear) Lake" -> Ethel Lake,
    Bear Lake; "Ghost Reservoir" -> Ghost Lake; "Hays (Grantham Reservoir) Lake"."""
    out = [name]
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*(.*)$", name)
    if m:
        a, inner, tail = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        out.append(f"{a} {tail}".strip())
        if inner.lower() != "unnamed":
            out.append(inner if re.search(r"(Lake|Reservoir|Pond)$", inner) else f"{inner} {tail}".strip())
    for v in list(out):
        if v.endswith(" Reservoir"):
            out.append(v[:-len(" Reservoir")] + " Lake")
        elif v.endswith(" Lake") and not v.startswith("Lac "):
            out.append(v[:-len(" Lake")] + " Reservoir")
    seen, uniq = set(), []
    for v in out:
        if v and norm(v) not in seen:
            seen.add(norm(v)); uniq.append(v)
    return uniq


def groups(outl, within_km=5.0):
    """Outline pieces within a few km of each other are one lake."""
    out = []
    for o in sorted(outl, key=lambda o: -o[2]):
        for g in out:
            if any(km(o[:2], q[:2]) <= within_km for q in g):
                g.append(o)
                break
        else:
            out.append([o])
    return out


GENERIC = {"lake", "lakes", "reservoir", "pond", "ponds", "upper", "lower", "east", "west", "north", "south",
           "middle", "big", "little", "the", "lac", "de", "la", "summit", "unnamed"}


def one_edit(a, b):
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return a[i + 1:] == b[i + 1:] or a[i + 1:] == b[i:] or a[i:] == b[i + 1:]


def similar(a, b):
    """Two names for one water: a shared name word, or one letter different
    ("Kehiwin" / "Kehewin", "Phillips" / "Phillipps", "Chin Lakes" / "Chin Reservoir")."""
    wa = {w for w in norm(a).split() if w not in GENERIC and len(w) > 2}
    wb = {w for w in norm(b).split() if w not in GENERIC and len(w) > 2}
    return any(one_edit(x, y) for x in wa for y in wb)


def first_ats(text):
    m = ATS_RE.search(text or "")
    if not m:
        return None
    q, sec, twp, rng, mer = m.groups()
    code = f"{q or ''}{sec}-{twp}-{rng}-{mer}"
    lat, lon = ats.ats_to_latlng(code)
    return (lat, lon, code) if lat is not None else None


# ------------------------------------------------------------------ the map today
def stocked_lakes():
    lakes = {}
    for path in sorted(DATA.glob("lakes_20*.json")):
        for lk in json.loads(path.read_text(encoding="utf-8")):
            key = lk.get("lake_id") or lk.get("ats")
            if lk.get("lat") is not None:
                lakes[key] = (lk["name"], lk["lat"], lk["lon"], lk.get("zone"))
    return lakes


class Zones:
    """The zone of a point: the most common zone of its 5 nearest stocked lakes."""

    def __init__(self, lakes):
        self.pts = [(v[1], v[2], v[3]) for v in lakes.values() if v[3]]

    def _near(self, lat, lon, n):
        return sorted(self.pts, key=lambda p: (p[0] - lat) ** 2 + ((p[1] - lon) * math.cos(math.radians(lat))) ** 2)[:n]

    def of(self, lat, lon):
        return Counter(p[2] for p in self._near(lat, lon, 5)).most_common(1)[0][0]

    def touches(self, lat, lon, zone):
        """The zone is among the 8 nearest stocked lakes: a point near a zone edge."""
        return any(p[2] == zone for p in self._near(lat, lon, 8))


# ------------------------------------------------------------------ inputs
def cgn_rows(path):
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        text = z.read(name).decode("utf-8-sig")
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("Generic Term") in LAKE_TERMS:
            try:
                out.append((r["Geographical Name"], float(r["Latitude"]), float(r["Longitude"])))
            except ValueError:
                pass
    return out


def canvec(path, layer):
    path = Path(path)
    if path.suffix.lower() == ".zip":
        z = zipfile.ZipFile(path)
        base = next(n[:-4] for n in z.namelist() if n.endswith(layer + ".shp"))
        return shapefile.Reader(shp=io.BytesIO(z.read(base + ".shp")), shx=io.BytesIO(z.read(base + ".shx")),
                                dbf=io.BytesIO(z.read(base + ".dbf")), encoding="utf-8")
    return shapefile.Reader(str(path / layer), encoding="utf-8")


def ring_area_km2(ring):
    if len(ring) < 3:
        return 0.0
    lat0 = sum(p[1] for p in ring) / len(ring)
    kx = 111.32 * math.cos(math.radians(lat0))
    a = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        a += (x1 * kx) * (y2 * 110.57) - (x2 * kx) * (y1 * 110.57)
    return abs(a) / 2


def outlines(path):
    """name -> [(lat, lon, area_ha)] for named CanVec lake outlines."""
    r = canvec(path, "waterbody_2")
    out = defaultdict(list)
    for i, rec in enumerate(r.iterRecords(fields=["name_en", "namelk1en"])):
        name = rec[0] or rec[1]
        if not name:
            continue
        shp = r.shape(i)
        parts = list(shp.parts) + [len(shp.points)]
        ring = shp.points[parts[0]:parts[1]]
        area = ring_area_km2(ring) - sum(ring_area_km2(shp.points[a:b]) for a, b in zip(parts[1:-1], parts[2:]))
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        out[norm(name)].append((round((min(ys) + max(ys)) / 2, 5), round((min(xs) + max(xs)) / 2, 5), round(area * 100, 1)))
    return out


COURSE_LAYERS = ("watercourse_1", "water_linear_flow_1_1", "water_linear_flow_1_2")


def courses(path, wanted):
    """normalised river name -> [polyline [(lat, lon), ...]] for the named watercourses wanted.
    Narrow streams are in watercourse_1; a wide river is drawn as water, and its
    centre line is in water_linear_flow (1:50,000 data). A layer the file does
    not have is skipped."""
    out = defaultdict(list)
    for layer in COURSE_LAYERS:
        try:
            r = canvec(path, layer)
        except Exception:
            continue
        for i, rec in enumerate(r.iterRecords(fields=["name_en", "name_1_en", "name_2_en"])):
            names = {norm(n) for n in rec if n}
            hit = names & wanted
            if not hit:
                continue
            pts = [(round(p[1], 5), round(p[0], 5)) for p in r.shape(i).points]
            for n in hit:
                out[n].append(pts)
    return out


# ------------------------------------------------------------------ lines
def simplify(line, tol_km=SIMPLIFY_KM):
    if len(line) < 3:
        return line
    a, b = line[0], line[-1]
    best, idx = 0.0, 0
    for i in range(1, len(line) - 1):
        d = seg_dist(line[i], a, b)
        if d > best:
            best, idx = d, i
    if best <= tol_km:
        return [a, b]
    return simplify(line[:idx + 1], tol_km)[:-1] + simplify(line[idx:], tol_km)


def seg_dist(p, a, b):
    kx = 111.32 * math.cos(math.radians(p[0]))
    px, py = p[1] * kx, p[0] * 110.57
    ax, ay, bx, by = a[1] * kx, a[0] * 110.57, b[1] * kx, b[0] * 110.57
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def spots_for(lines):
    """Forecast spots about every SPOT_KM along the lines: a vertex becomes a spot
    when no spot is within SPOT_KM of it. At least one."""
    spots = []
    for line in lines:
        for p in line:
            if all(km(p, s) >= SPOT_KM for s in spots):
                spots.append(p)
    return [[round(p[0], 4), round(p[1], 4)] for p in spots] or []


def line_km(lines):
    return sum(km(a, b) for line in lines for a, b in zip(line, line[1:]))


# ------------------------------------------------------------------ build
def placed_lakes(regs, zones, cgn, lines_by_name, stocked):
    matched = set()
    resolved = json.loads((DATA / "lake_regulations.json").read_text(encoding="utf-8"))["lakes"]
    for v in resolved.values():
        if v.get("basis") == "site-specific" and v.get("matched_name"):
            matched.add((v.get("zone"), norm(v["matched_name"])))
    stocked_names = {(v[3], norm(v[0])) for v in stocked.values()}
    cgn_by = defaultdict(list)
    for n, lat, lon in cgn:
        cgn_by[norm(n)].append((lat, lon))
    out, review, seen = [], [], set()
    for zone, unit in sorted(regs["zones"].items()):
        for name, row in sorted(unit["lakes"].items()):
            # The guide's tables for some units list rivers among the lakes;
            # those are drawn as rivers, and areas are not places on a map.
            if FLOWING.search(name) or any(w in name for w in NOT_LINES) or "Area" in name:
                continue
            key = (zone, norm(name))
            if key in matched or key in stocked_names or key in seen:
                continue
            seen.add(key)
            rules = regulations.resolve(name, zone, regs)
            pos = first_ats(row.get("detail"))
            outl = [o for o in lines_by_name.get(norm(name), []) if zones.of(o[0], o[1]) == zone]
            pts = []
            for v in variants(name):
                pts = [p for p in cgn_by.get(norm(v), []) if zones.of(p[0], p[1]) == zone]
                if not pts:
                    # Near a zone edge the nearest-lake zone can be the neighbour's:
                    # accept the one place of that name whose neighbours include the zone.
                    edge = [p for p in cgn_by.get(norm(v), []) if zones.touches(p[0], p[1], zone)]
                    if len(edge) == 1:
                        pts = edge
                if pts:
                    break
            entry = {"name": name, "zone": zone}
            if pos:
                lat, lon, code = pos
                # The land location can sit at one end of a long reservoir
                # (Gleniffer Lake): the outline pieces within 8 km give its size.
                near = [o for v in variants(name) for o in lines_by_name.get(norm(v), []) if km((lat, lon), o[:2]) <= 8]
                entry.update(lat=lat, lon=lon, ats=code, coord_source="ats")
                if near:
                    g = min(groups(near), key=lambda g: min(km((lat, lon), o[:2]) for o in g))
                    entry["surface_area_ha"] = round(sum(o[2] for o in g), 1)
            elif outl and len(groups(outl)) == 1:
                # The 1:50,000 data can draw one lake as several pieces: they sit together.
                g = groups(outl)[0]
                big = max(g, key=lambda o: o[2])
                entry.update(lat=big[0], lon=big[1], surface_area_ha=round(sum(o[2] for o in g), 1), coord_source="outline")
            elif outl and len(pts) == 1:
                near = [o for o in outl if km(o[:2], pts[0]) <= 5]
                entry.update(lat=round(pts[0][0], 5), lon=round(pts[0][1], 5), coord_source="place names")
                if near:
                    entry["surface_area_ha"] = round(sum(o[2] for o in near), 1)
            elif outl:
                review.append({"lake": name, "zone": zone, "why": f"{len(groups(outl))} separate lakes of that name in the zone"})
                continue
            elif len(pts) == 1:
                entry.update(lat=round(pts[0][0], 5), lon=round(pts[0][1], 5), coord_source="place names")
            else:
                review.append({"lake": name, "zone": zone,
                               "why": "no place of that name in the zone" if not pts else f"{len(pts)} places of that name in the zone"})
                continue
            # Already on the map as a stocked lake (its zone or name form may differ).
            # Same name within 10 km, or any stocked lake within 3 km (another spelling:
            # Kehiwin / Kehewin Lake, Chin Lakes / Chin Reservoir).
            here = (entry["lat"], entry["lon"])
            twins = [k for k, v in stocked.items()
                     if (km((v[1], v[2]), here) <= 3 and similar(v[0], name))
                     or (norm(v[0]) in {norm(x) for x in variants(name)} and km((v[1], v[2]), here) <= 10)]
            if twins:
                continue
            entry["lake_id"] = f"gu-{zone.lower()}-{slug(name)}"
            if rules:
                entry["rules"] = rules
            out.append(entry)
    return out, review


LIMIT_RE = re.compile(r"(?:from\s+)?(.+?)\s+downstream\s+to\s+(?:the\s+)?(.+)", re.I)


PLACES = {}


def snap(river_lines, pts, within_km):
    best, bd = None, within_km
    for line in river_lines:
        for p in line:
            d = min(km(p, q) for q in pts)
            if d < bd:
                best, bd = p, d
    return best


def find_limit(text, river_lines, feature_lines, outl):
    """(point on the river, how it was found) for one named limit, or (None, None).
    How: "exact" (land location, border, another named water), "place" (a
    named place next to the limit, e.g. the hamlet a dam or bridge is named
    after), "head" (the headwater: the upper end of the river)."""
    t = re.sub(r"^(?:Mainstem and tributaries|Mainstem|Tributaries(?: of [A-Z][\w ]*?)?)?\s*(?:-|from)?\s*", "", (text or "").strip(), flags=re.I)
    a = first_ats(t)
    if a:
        return a[:2], "exact"
    if re.match(r"(?:the\s+)?headwaters?\b", t, re.I):
        return None, "head"
    if re.search(r"Saskatchewan border", t, re.I):
        pts = [p for line in river_lines for p in line]
        return (min(pts, key=lambda p: abs(p[1] + 110.0)), "exact") if pts else (None, None)
    m = re.match(r"(?:the\s+)?([A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*)*)\s+(Dam|Bridge|Weir)\b", t)
    if m and PLACES.get(norm(m.group(1))):
        p = snap(river_lines, PLACES[norm(m.group(1))], 12.0)
        return (p, "place") if p else (None, None)
    m = re.match(r"(?:the\s+)?([A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*)*\s+(?:River|Creek|Lake|Reservoir))\b", t)
    if not m:
        return None, None
    target = norm(m.group(1))
    tpts = [p for line in feature_lines.get(target, []) for p in line] + [o[:2] for o in outl.get(target, [])]
    if not tpts:
        return None, None
    p = snap(river_lines, tpts[:: max(1, len(tpts) // 400)], 3.0)
    return (p, "exact") if p else (None, None)


HEIGHTS = {}


def higher_end(line):
    """The end of a line that sits higher (the headwater), from Open-Meteo heights."""
    import elevation
    ends = [line[0], line[-1]]
    key = tuple(ends)
    if key not in HEIGHTS:
        try:
            HEIGHTS[key] = elevation.fetch(ends)
        except Exception:
            HEIGHTS[key] = None
    h = HEIGHTS[key]
    if not h or None in h:
        return None
    return ends[0] if h[0] >= h[1] else ends[1]


def cut(lines, a, b):
    """The river between two limit points: the shortest way along its lines,
    over every piece (braids and islands split a river into many pieces)."""
    import heapq
    node = lambda p: (round(p[0], 4), round(p[1], 4))
    graph = defaultdict(list)
    for line in lines:
        for p, q in zip(line, line[1:]):
            u, v = node(p), node(q)
            if u != v:
                d = km(u, v)
                graph[u].append((v, d)); graph[v].append((u, d))
    if not graph:
        return None
    # Pieces from different layers (a narrow stream line, a wide river's centre
    # line) end near each other but not on the same point: join ends within 150 m.
    ends = [node(l[0]) for l in lines if l] + [node(l[-1]) for l in lines if l]
    cell = defaultdict(list)
    for e in ends:
        cell[(round(e[0], 2), round(e[1], 2))].append(e)
    for e in ends:
        for dx in (-0.01, 0, 0.01):
            for dy in (-0.01, 0, 0.01):
                for f in cell.get((round(e[0] + dx, 2), round(e[1] + dy, 2)), []):
                    if f != e and km(e, f) <= 0.15:
                        graph[e].append((f, km(e, f)))
    # A river crosses reservoirs and wide water where its line stops: join the
    # pieces at their nearest loose ends (at most 40 km apart: Gleniffer
    # Reservoir is about 25 km between the river's lines), nearest first.
    comp = {}
    for start in graph:
        if start in comp:
            continue
        comp[start] = start; todo = [start]
        while todo:
            u = todo.pop()
            for v, _ in graph[u]:
                if v not in comp:
                    comp[v] = start; todo.append(v)
    roots = {c: c for c in set(comp.values())}

    def find(c):
        while roots[c] != c:
            roots[c] = roots[roots[c]]; c = roots[c]
        return c
    leaves = [n for n, e in graph.items() if len(e) == 1]
    pairs = sorted((km(u, v), u, v) for i, u in enumerate(leaves) for v in leaves[i + 1:]
                   if comp[u] != comp[v] and abs(u[0] - v[0]) < 0.5 and abs(u[1] - v[1]) < 0.8)
    for d, u, v in pairs:
        if d > 40:
            break
        ru, rv = find(comp[u]), find(comp[v])
        if ru != rv:
            roots[ru] = rv
            graph[u].append((v, d)); graph[v].append((u, d))
    nodes = list(graph)
    sa = min(nodes, key=lambda n: km(n, a)); sb = min(nodes, key=lambda n: km(n, b))
    if sa == sb:
        return None
    dist, prev, heap = {sa: 0.0}, {}, [(0.0, sa)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == sb:
            break
        if d > dist.get(u, 1e18):
            continue
        for v, w in graph[u]:
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd; prev[v] = u; heapq.heappush(heap, (nd, v))
    if sb not in dist:
        return None
    path = [sb]
    while path[-1] != sa:
        path.append(prev[path[-1]])
    return [path[::-1]]


def chain(lines):
    """Join segments that share an end point, so a river is a few long lines."""
    lines = [list(l) for l in lines if len(l) >= 2]
    changed = True
    while changed:
        changed = False
        for i in range(len(lines)):
            for j in range(len(lines)):
                if i == j or not lines[i] or not lines[j]:
                    continue
                a, b = lines[i], lines[j]
                if a[-1] == b[0]:
                    lines[i] = a + b[1:]; lines[j] = []; changed = True
                elif a[-1] == b[-1]:
                    lines[i] = a + b[::-1][1:]; lines[j] = []; changed = True
            lines = [l for l in lines if l]
            if changed:
                break
    return lines


def river_stretches(regs, zones, river_lines, outl):
    out = []
    for zone, unit in sorted(regs["zones"].items()):
        flowing = dict(unit["rivers"])
        for name, row in unit["lakes"].items():
            if FLOWING.search(name) and name not in flowing:
                flowing[name] = row
        for name, row in sorted(flowing.items()):
            if any(w in name for w in NOT_LINES):
                continue
            rows = [row] + list(row.get("also") or [])
            whole = river_lines.get(norm(name), [])
            lines = [l for l in whole if zones.of(*l[len(l) // 2]) == zone]
            if not lines:
                continue
            lines = chain(lines)
            whole = chain(whole)
            rest = []
            n = 0
            for r in rows:
                rules = {k: v for k, v in r.items() if k != "also"}
                rules.update(basis="site-specific", zone=zone, matched_name=name)
                m = LIMIT_RE.search(r.get("detail") or "")
                part, how = None, None
                if m:
                    # Limits are looked for on the whole river: a dam or bridge at a
                    # unit's edge can sit on the part the nearest-lake zone gives the neighbour.
                    (a, ha), (b, hb) = (find_limit(m.group(1), whole, river_lines, outl),
                                        find_limit(m.group(2), whole, river_lines, outl))
                    if "head" in (ha, hb) and (a or b):
                        top = higher_end(max(whole, key=len))
                        a, b = (top, b) if ha == "head" else (a, top)
                        ha = hb = "exact" if top else None
                    if a and b:
                        part = cut(whole, a, b)
                        how = "approximate" if "place" in (ha, hb) else "found"
                if part:
                    n += 1
                    out.append(stretch(zone, name, n, r.get("detail"), part, rules, [rules], how))
                else:
                    rules["_from_to"] = bool(m)
                    rest.append(rules)
            if rest:
                n += 1
                # Rows with no "from … to …" cover the river in this unit; a row whose
                # limits could not be placed makes the whole line an estimate.
                limits = "estimated" if any(r.pop("_from_to") for r in rest) else "unit"
                out.append(stretch(zone, name, n, rest[0].get("detail") or "", lines, rest[0], rest, limits))
    return out


def stretch(zone, name, n, detail, lines, rules, rows, limits):
    simple = [simplify(l) for l in lines]
    simple = [[[round(p[0], 4), round(p[1], 4)] for p in l] for l in simple if len(l) >= 2]
    return {"lake_id": f"rv-{zone.lower()}-{slug(name)}-{n}", "name": name, "zone": zone, "detail": detail,
            "limits": limits, "length_km": round(line_km(lines), 1), "line": simple, "spots": spots_for(lines),
            "rules": rules, "rows": rows if len(rows) > 1 else None}


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    canvec_path, cgn_path = argv[1], argv[2]
    regs = regulations.load(PDF)
    with zipfile.ZipFile(cgn_path) as z:
        text = z.read([n for n in z.namelist() if n.lower().endswith(".csv")][0]).decode("utf-8-sig")
    for r in csv.DictReader(io.StringIO(text)):
        try:
            PLACES.setdefault(norm(r["Geographical Name"]), []).append((float(r["Latitude"]), float(r["Longitude"])))
        except ValueError:
            pass
    stocked = stocked_lakes()
    zones = Zones(stocked)
    outl = outlines(canvec_path)
    lakes, review = placed_lakes(regs, zones, cgn_rows(cgn_path), outl, stocked)
    wanted = {norm(n) for u in regs["zones"].values() for n in list(u["rivers"]) + [x for x in u["lakes"] if FLOWING.search(x)]}
    for u in regs["zones"].values():
        for r in u["rivers"].values():
            for rr in [r] + list(r.get("also") or []):
                for m in re.finditer(r"([A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*)*\s+(?:River|Creek))", rr.get("detail") or ""):
                    wanted.add(norm(m.group(1)))
    rivers = river_stretches(regs, zones, courses(canvec_path, wanted), outl)
    src = {"guide": f"Alberta Guide to Sportfishing Regulations {regs['guide_year']} (site-specific tables)",
           "places": "Natural Resources Canada, Canadian Geographical Names Database (CGNDB), Alberta",
           "water": "Natural Resources Canada, CanVec 1:250,000 Hydro, Alberta",
           "licence": LICENCE, "licence_url": LICENCE_URL,
           "attribution": "Contains information licensed under the Open Government Licence - Canada."}
    (DATA / "waters_unstocked.json").write_text(json.dumps(
        {"source": src, "guide_year": regs["guide_year"], "count": len(lakes),
         "by_position": dict(Counter(l["coord_source"] for l in lakes)), "lakes": lakes},
        indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (DATA / "rivers.json").write_text(json.dumps(
        {"source": src, "guide_year": regs["guide_year"], "count": len(rivers),
         "spot_km": SPOT_KM, "stretches": rivers}, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8")
    with (DATA / "waters_review.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["lake", "zone", "why"])
        w.writeheader()
        for r in sorted(review, key=lambda r: (r["zone"], r["lake"])):
            w.writerow(r)
    print(f"lakes placed {len(lakes)} {dict(Counter(l['coord_source'] for l in lakes))}; review {len(review)}")
    print(f"river stretches {len(rivers)}: limits {dict(Counter(r['limits'] for r in rivers))}, "
          f"spots {sum(len(r['spots']) for r in rivers)}, km {round(sum(r['length_km'] for r in rivers))}")


if __name__ == "__main__":
    main(sys.argv)
