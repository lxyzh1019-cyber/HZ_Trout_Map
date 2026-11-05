"""Build 5 Stage 2: the waters the 2026 sportfishing guide names that the
stocking reports never list, and the guide's river stretches.

The map began as a map of stocked lakes. The guide's tables name about 460
lakes, reservoirs and ponds and about 60 rivers and creeks, most of them never
stocked. This places each one and copies its rule row from the guide, so the
app can score it and show its rules like any stocked lake.

Usage (network inputs are downloaded first, then read from disk):

    python -I scripts/waterbodies.py <CanVec 1:50,000 Hydro folder or .zip> <cgn_ab_csv_eng.zip>

Inputs
    the guide          data/raw/alberta-sportfishing-regulations-2026-tables.pdf (read by regulations.py)
    place names        NRCan CGNDB, Alberta CSV (Open Government Licence - Canada)
    water data         NRCan CanVec 1:50,000 Hydro, Alberta (watercourse_1, water_linear_flow_1_*,
                       waterbody_2; Open Government Licence - Canada)
    the stocked lakes  data/lakes_20*.json and data/lake_regulations.json (to leave them out)

Writes
    data/waters_unstocked.json   lakes the guide names that are not on the map yet
    data/rivers.json            river and creek stretches, simplified lines and forecast spots;
                                each stretch's rules carry every guide row for it (the rest in
                                "also"), and "stocked_twin" names a stocked water it duplicates
    data/waters_review.csv      guide waters that could not be placed with confidence

How a lake is placed, first match wins, and the label says which:
    "ats"          the guide prints a land location (e.g. Gleniffer Lake, 30-35-2-W5)
    "outline"      exactly one CanVec lake outline of that name in the lake's zone,
                   or one lake of that name much bigger than the others there
    "place names"  exactly one CGNDB lake point of that name in the lake's zone,
                   or the one in the biggest outline of that name there
A name with no candidate, or more than one in the zone, is not placed: it goes
to the review file. Guessing a position is worse than leaving a lake off.

The zone of a point is the zone of the nearest stocked lakes (the guide's
Watershed Units have no published outline in this repository). That is good
enough to tell the three Gull Lakes apart, and the review file catches the rest.

A guide lake that is already on the map as a stocked lake is left out; its rule
row reaches that lake through data/regs_aliases.csv. The run prints each such
twin whose stocked lake does not carry the row yet.
"""

import csv
import io
import json
import math
import re
import sys
import unicodedata
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
STANDING = re.compile(r"\b(Reservoir|Lake|Lakes|Pond|Ponds)\s*$")
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


def plain(name):
    """Accents off before anything else: "Lac Santé" is the guide's "Lac Sante"."""
    s = unicodedata.normalize("NFKD", name or "")
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


def norm(name):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", plain(name))).strip()


def slug(name):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", plain(name))).strip("-")


def flowing(name):
    """A river or creek: "Berry Creek (Carolside) Reservoir" is a lake."""
    return bool(FLOWING.search(name or "")) and not STANDING.search(name or "")


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


def box_gap_km(o, q):
    """How far apart two outlines' boxes are (0 when they overlap)."""
    a, b = o[4], q[4]
    dlat = max(0.0, a[0] - b[2], b[0] - a[2]) * 110.57
    dlon = max(0.0, a[1] - b[3], b[1] - a[3]) * 111.32 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dlat, dlon)


def groups(outl, within_km=5.0):
    """Outline pieces that are one lake: their middles within a few km of each
    other, or their boxes touching (Buffalo Lake is drawn as pieces 10 km across)."""
    outl = sorted(outl, key=lambda o: -o[2])
    root = list(range(len(outl)))

    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]; i = root[i]
        return i
    for i, o in enumerate(outl):
        for j in range(i):
            q = outl[j]
            if km(o[:2], q[:2]) <= within_km or (len(o) > 4 and len(q) > 4 and box_gap_km(o, q) <= 0.2):
                root[find(i)] = find(j)
    out = {}
    for i, o in enumerate(outl):
        out.setdefault(find(i), []).append(o)
    return sorted(out.values(), key=lambda g: -sum(o[2] for o in g))


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
    if len(a) == len(b) and a[i:i + 2] == b[i:i + 2][::-1] and a[i + 2:] == b[i + 2:]:
        return True     # two neighbouring letters swapped: "Sawn" / "Swan"
    return a[i + 1:] == b[i + 1:] or a[i + 1:] == b[i:] or a[i:] == b[i + 1:]


def similar(a, b):
    """Two names for one water: a shared name word, one letter different or two
    neighbouring letters swapped ("Kehiwin" / "Kehewin", "Phillips" / "Phillipps",
    "Chin Lakes" / "Chin Reservoir", "Sawn" / "Swan")."""
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


TWP_RE = re.compile(r"(?<![\d-])(\d{1,3})-(\d{1,2})-(W[456])\b")
TWP_KM = 10.0


def township(text):
    """The middle of a township the guide names without a section ("Island Lake,
    62-17-W4"): a lake of the name must lie within TWP_KM of it."""
    if not text or ATS_RE.search(text):
        return None
    m = TWP_RE.search(text)
    if not m:
        return None
    pts = [ats.ats_to_latlng(f"{s}-{m.group(1)}-{m.group(2)}-{m.group(3)}") for s in (15, 16, 21, 22)]
    pts = [p for p in pts if p[0] is not None]
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def box_km(p, o):
    """How far a point is from an outline's box (0 inside it)."""
    b = o[4]
    dlat = max(0.0, b[0] - p[0], p[0] - b[2]) * 110.57
    dlon = max(0.0, b[1] - p[1], p[1] - b[3]) * 111.32 * math.cos(math.radians(p[0]))
    return math.hypot(dlat, dlon)


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
def read_cgn(path):
    """Every row of the CGNDB Alberta CSV."""
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        text = z.read(name).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def cgn_rows(rows):
    """(name, lat, lon) of the CGNDB lakes, reservoirs and ponds."""
    out = []
    for r in rows:
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
    """name -> [(lat, lon, area_ha, ring, box)] for named CanVec lake outlines: lat, lon
    is the middle of the outline's box, ring its outer edge as [(lat, lon), ...] and
    box (min lat, min lon, max lat, max lon)."""
    r = canvec(path, "waterbody_2")
    out = defaultdict(list)
    for i, rec in enumerate(r.iterRecords(fields=["name_en", "namelk1en"])):
        name = rec[0] or rec[1]
        if not name:
            continue
        shp = r.shape(i)
        out[norm(name)].append(outline_of(shp.parts, shp.points))
    return out


def outline_of(parts, points):
    parts = list(parts) + [len(points)]
    ring = points[parts[0]:parts[1]]
    area = ring_area_km2(ring) - sum(ring_area_km2(points[a:b]) for a, b in zip(parts[1:-1], parts[2:]))
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (round((min(ys) + max(ys)) / 2, 5), round((min(xs) + max(xs)) / 2, 5), round(area * 100, 1),
            tuple((p[1], p[0]) for p in ring), (min(ys), min(xs), max(ys), max(xs)))


def inside(p, ring):
    """Point in polygon (ray casting), ring as [(lat, lon), ...]."""
    y, x = p
    hit = False
    for (y1, x1), (y2, x2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def in_box(p, o, pad=0.0):
    """The point is in the outline's box, widened by pad degrees."""
    b = o[4]
    return b[0] - pad <= p[0] <= b[2] + pad and b[1] - pad <= p[1] <= b[3] + pad


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
def dominant(gs):
    """Of several lakes of one name, the one whose outline pieces cover more than
    5 times the area of any other (Buffalo Lake by Stettler among the small ones)."""
    if len(gs) < 2:
        return None
    areas = sorted(((sum(o[2] for o in g), i) for i, g in enumerate(gs)), reverse=True)
    return gs[areas[0][1]] if areas[0][0] > 5 * areas[1][0] else None


def placed_lakes(regs, zones, cgn, lines_by_name, stocked):
    """(lakes placed, review rows, twins): twins are the guide lakes left out because
    they are on the map as a stocked lake, with how they matched."""
    matched = set()
    resolved = json.loads((DATA / "lake_regulations.json").read_text(encoding="utf-8"))["lakes"]
    for v in resolved.values():
        if v.get("basis") == "site-specific" and v.get("matched_name"):
            matched.add((v.get("zone"), norm(v["matched_name"])))
    stocked_names = {(v[3], norm(v[0])) for v in stocked.values()}
    # Names the guide lists in their own right (the zone's table, or the stocked
    # list for a stocked lake of the same zone): a stocked lake of one of those
    # names is not another spelling of a guide lake nearby (South Sundance Lake is
    # not Sundance Lake 1.4 km away; the stocked list's Swan Lake is the ES4 one).
    listed = {norm(n) for n in regs["stocked"]}
    in_table = {z: {norm(n) for n in u["lakes"]} for z, u in regs["zones"].items()}
    cgn_by = defaultdict(list)
    for n, lat, lon in cgn:
        cgn_by[norm(n)].append((lat, lon))
    out, review, seen, twin_rows = [], [], set(), []
    for zone, unit in sorted(regs["zones"].items()):
        zone_names = {norm(n) for n in unit["lakes"]}
        for name, row in sorted(unit["lakes"].items()):
            # The guide's tables for some units list rivers among the lakes;
            # those are drawn as rivers, and areas are not places on a map.
            if flowing(name) or any(w in name for w in NOT_LINES) or "Area" in name:
                continue
            key = (zone, norm(name))
            if key in matched or key in stocked_names or key in seen:
                continue
            seen.add(key)
            rules = regulations.resolve(name, zone, regs)
            pos = first_ats(row.get("detail"))
            twp = township(row.get("detail"))
            cand = lines_by_name.get(norm(name), [])
            if twp:
                # The guide names the township: that settles which lake, whatever
                # zone the nearest stocked lakes give it.
                outl = [o for g in groups(cand) if any(box_km(twp, o) <= TWP_KM for o in g) for o in g]
            else:
                outl = [o for o in cand if zones.of(o[0], o[1]) == zone]
            if not outl and not twp:
                # Near a zone edge, as for place names below: one lake of that name
                # with a piece whose neighbours include the zone (Utikuma Lake).
                # A lake the neighbour's own table names is the neighbour's (Long Lake).
                edge = [g for g in groups(cand) if any(zones.touches(o[0], o[1], zone) for o in g)
                        and norm(name) not in in_table.get(zones.of(g[0][0], g[0][1]), ())]
                if len(edge) == 1:
                    outl = edge[0]
            pts = []
            for v in variants(name):
                if twp:
                    pts = [p for p in cgn_by.get(norm(v), []) if km(p, twp) <= TWP_KM]
                    if pts:
                        break
                    continue
                pts = [p for p in cgn_by.get(norm(v), []) if zones.of(p[0], p[1]) == zone]
                if not pts:
                    # Near a zone edge the nearest-lake zone can be the neighbour's:
                    # accept the one place of that name whose neighbours include the zone.
                    edge = [p for p in cgn_by.get(norm(v), []) if zones.touches(p[0], p[1], zone)
                            and norm(v) not in in_table.get(zones.of(p[0], p[1]), ())]
                    if len(edge) == 1:
                        pts = edge
                if pts:
                    break
            big = dominant(groups(outl)) if outl else None
            entry = {"name": name, "zone": zone}
            if pos or twp:
                entry["_located"] = True     # the guide's land location backs the place
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
                piece = max(g, key=lambda o: o[2])
                entry.update(lat=piece[0], lon=piece[1], surface_area_ha=round(sum(o[2] for o in g), 1), coord_source="outline")
            elif outl and len(pts) == 1:
                near = [o for o in outl if km(o[:2], pts[0]) <= 5]
                entry.update(lat=round(pts[0][0], 5), lon=round(pts[0][1], 5), coord_source="place names")
                if near:
                    entry["surface_area_ha"] = round(sum(o[2] for o in near), 1)
            elif big:
                # Several lakes of the name, one far bigger than the rest: the place
                # point inside it (or the nearest within its box), else its middle.
                piece = max(big, key=lambda o: o[2])
                inn = [p for p in pts if any(in_box(p, o) and inside(p, o[3]) for o in big)]
                by = sorted(inn or [p for p in pts if any(in_box(p, o, 0.05) for o in big)],
                            key=lambda p: km(p, piece[:2]))
                if by:
                    entry.update(lat=round(by[0][0], 5), lon=round(by[0][1], 5), coord_source="place names")
                else:
                    entry.update(lat=piece[0], lon=piece[1], coord_source="outline")
                entry["surface_area_ha"] = round(sum(o[2] for o in big), 1)
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
            # Same name within 10 km, or a stocked lake of a similar name within 3 km
            # (another spelling: Kehiwin / Kehewin Lake, Chin Lakes / Chin Reservoir).
            here = (entry["lat"], entry["lon"])
            names = {norm(x) for x in variants(name)}
            twins = []
            for k, v in stocked.items():
                d = km((v[1], v[2]), here)
                if norm(v[0]) in names and d <= 10:
                    twins.append((k, v[0], v[3], round(d, 1), "same name"))
                elif d <= 3 and similar(v[0], name) and not (norm(v[0]) in zone_names
                                                            or (norm(v[0]) in listed and v[3] == zone)):
                    twins.append((k, v[0], v[3], round(d, 1), "similar name"))
            if twins:
                twin_rows.append({"lake": name, "zone": zone, "coord_source": entry["coord_source"], "twins": twins})
                continue
            entry["lake_id"] = f"gu-{zone.lower()}-{slug(name)}"
            if rules:
                entry["rules"] = rules
            out.append(entry)
    # Two guide lakes on one spot: when the guide's land location puts one there,
    # the other only matched a shared name (Fish (Jackfish) Lake, 76-11-W6, and
    # Hebephrenic (Jackfish) Lake both found Jackfish Lake).
    keep = []
    for e in out:
        other = next((o for o in out if o is not e and o.get("_located") and not e.get("_located")
                      and km((o["lat"], o["lon"]), (e["lat"], e["lon"])) <= 0.5), None)
        if other:
            review.append({"lake": e["name"], "zone": e["zone"],
                           "why": f"the place of that name is {other['name']} (by its land location)"})
        else:
            keep.append(e)
    for e in keep:
        e.pop("_located", None)
    return keep, review, twin_rows


HEIGHTS = {}

# "A downstream to B", or "A upstream to B" (Owl River: from Lac La Biche upstream to ...).
LIMIT_RE = re.compile(r"(?:from\s+)?(.+?)\s+(downstream|upstream)\s+to\s+(?:the\s+)?(.+)", re.I)


PLACES = {}
DAM_NEAR_KM = 5.0


def snap(river_lines, pts, within_km):
    best, bd = None, within_km
    for line in river_lines:
        for p in line:
            d = min(km(p, q) for q in pts)
            if d < bd:
                best, bd = p, d
    return best


def dam_ends(river_lines, place, outl):
    """The two ends, along the river, of the biggest lake or reservoir outline the
    river passes through within DAM_NEAR_KM of the place a dam is named after
    (Gleniffer Lake for the Dickson Dam); None when there is no such outline.
    The river's points in or next to the outline (within 300 m: its line can stop
    at the shore) are the river in the reservoir; the two farthest apart are its ends."""
    pts = [p for line in river_lines for p in line]
    best = None
    for olist in outl.values():
        for o in olist:
            if o[2] < 20 or not any(in_box(q, o, 0.08) for q in place):
                continue
            ring = o[3]
            step = max(1, len(ring) // 600)
            edge = ring[::step]
            if not any(inside(q, ring) or min(km(q, e) for e in edge) <= DAM_NEAR_KM for q in place):
                continue
            on = [p for p in pts if in_box(p, o, 0.005)
                  and (inside(p, ring) or min(km(p, e) for e in edge) <= 0.3)]
            if len(on) >= 2 and (best is None or o[2] > best[0]):
                best = (o[2], on)
    if not best:
        return None
    on = best[1]
    e1 = max(on, key=lambda p: km(p, on[0]))
    e2 = max(on, key=lambda p: km(p, e1))
    return (e1, e2) if e1 != e2 else None


WATER = {"path": None}      # the CanVec data, for water polygons near a dam
LAKE_POINTS = []            # CGNDB lake and reservoir points (name, lat, lon)
FLAT_M = 1.5                # a reservoir's surface in the DEM: within this of its level


def water_in(lat, lon, pad):
    """Every CanVec water polygon (named or not) whose box comes within pad degrees."""
    if not WATER["path"]:
        return []
    r = canvec(WATER["path"], "waterbody_2")
    return [outline_of(shp.parts, shp.points)
            for shp in r.iterShapes(bbox=(lon - pad, lat - pad, lon + pad, lat + pad))]


def dam_by_height(river_lines, place):
    """Where a reservoir near the place sits, when no outline of it exists (the
    1:50,000 water near Dickson is from 1972, before the Dickson Dam closed
    Gleniffer Lake in 1983). The old river's water polygons near the reservoir's
    CGNDB point are sampled in the DEM (Copernicus, 2010s): the reservoir is the
    part at the reservoir's own level, and its end downstream is the dam.
    Returns the sampled points at that level, or None."""
    import elevation
    river = [p for line in river_lines for p in line[::5]]
    for name, lat, lon in sorted(LAKE_POINTS, key=lambda r: min(km(r[1:], q) for q in place)):
        rp = (lat, lon)
        if min(km(rp, q) for q in place) > 8:
            break
        polys = [o for o in water_in(lat, lon, 0.15) if o[2] >= 20 and box_km(rp, o) <= 1.0]
        ring = [v for o in polys for v in o[3]]
        if not ring or not any(min(km(v, q) for q in ring[::20]) <= 1.0 for v in river if km(v, rp) <= 30):
            continue
        sample = ring[::max(1, len(ring) // 99)][:99] + [rp]
        key = tuple(sample)
        if key not in HEIGHTS:
            try:
                HEIGHTS[key] = elevation.fetch(sample)
            except Exception:
                HEIGHTS[key] = None
        h = HEIGHTS[key]
        if not h or h[-1] is None:
            continue
        flat = [p for p, x in zip(sample[:-1], h[:-1]) if x is not None and abs(x - h[-1]) <= FLAT_M]
        if len(flat) >= 3:
            return flat
    return None


def find_limit(text, river_lines, feature_lines, outl):
    """(point on the river, how it was found) for one named limit, or (None, None).
    How: "exact" (land location, border, another named water), "place" (a
    named place next to the limit, e.g. the hamlet a dam or bridge is named
    after), "head" (the headwater: the upper end of the river), "dam" (a dam at
    the end of a reservoir the river passes through: the point is the pair of
    the reservoir's two ends, and river_stretches picks the downstream one),
    "dam off the line" (the same where the river's line stops at the reservoir
    and no outline of it exists: the points are the reservoir's surface)."""
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
        place = PLACES[norm(m.group(1))]
        if m.group(2) == "Dam":
            # "Dickson Dam" is not at Dickson: a dam closes a reservoir, and the
            # hamlet sits by the reservoir's upper end, 6 km from the dam.
            ends = dam_ends(river_lines, place, outl)
            if ends:
                return ends, "dam"
            flat = dam_by_height(river_lines, place)
            if flat:
                return flat, "dam off the line"
        p = snap(river_lines, place, 12.0)
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


_GRAPHS = {}
BRIDGES = {}    # id(lines) -> the gaps joined across (pairs of loose ends)


def node(p):
    return (round(p[0], 4), round(p[1], 4))


def river_graph(lines):
    """The river's lines as one graph (built once per river)."""
    if id(lines) in _GRAPHS and _GRAPHS[id(lines)][0] is lines:
        return _GRAPHS[id(lines)][1]
    graph = defaultdict(list)
    for line in lines:
        for p, q in zip(line, line[1:]):
            u, v = node(p), node(q)
            if u != v:
                d = km(u, v)
                graph[u].append((v, d)); graph[v].append((u, d))
    if not graph:
        _GRAPHS[id(lines)] = (lines, graph)
        return graph
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
    BRIDGES[id(lines)] = []
    pairs = sorted((km(u, v), u, v) for i, u in enumerate(leaves) for v in leaves[i + 1:]
                   if comp[u] != comp[v] and abs(u[0] - v[0]) < 0.5 and abs(u[1] - v[1]) < 0.8)
    for d, u, v in pairs:
        if d > 40:
            break
        ru, rv = find(comp[u]), find(comp[v])
        if ru != rv:
            roots[ru] = rv
            graph[u].append((v, d)); graph[v].append((u, d))
            BRIDGES[id(lines)].append((u, v))
    _GRAPHS[id(lines)] = (lines, graph)
    return graph


def shortest(lines, a, b):
    """(km along the river, [path]) between the river nodes nearest a and b, or (None, None)."""
    import heapq
    graph = river_graph(lines)
    if not graph:
        return None, None
    nodes = list(graph)
    sa = min(nodes, key=lambda n: km(n, a)); sb = min(nodes, key=lambda n: km(n, b))
    if sa == sb:
        return None, None
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
        return None, None
    path = [sb]
    while path[-1] != sa:
        path.append(prev[path[-1]])
    return dist[sb], path[::-1]


def cut(lines, a, b):
    """The river between two limit points: the shortest way along its lines,
    over every piece (braids and islands split a river into many pieces)."""
    _, path = shortest(lines, a, b)
    return [path] if path else None


def from_point(lines, src):
    """(km, previous node) from the river node nearest src to every node it reaches."""
    import heapq
    graph = river_graph(lines)
    s0 = min(graph, key=lambda n: km(n, src))
    dist, prev, heap = {s0: 0.0}, {}, [(0.0, s0)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, 1e18):
            continue
        for v, w in graph[u]:
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd; prev[v] = u; heapq.heappush(heap, (nd, v))
    return dist, prev, s0


def cut_from_off(lines, d, b):
    """The river from a point its lines do not reach (a dam across a gap in the
    line) to b: d joined to the river node that makes the shortest way to b."""
    if not river_graph(lines):
        return None
    dist, prev, sb = from_point(lines, b)
    near = [n for n in dist if km(n, d) <= 25]
    if not near:
        return None
    # Join where the river's line picks up again: of the gap the dam sits in (the
    # joined loose ends passing nearest it), the end that is nearer b.
    gaps = [(seg_dist(d, u, v), u, v) for u, v in BRIDGES.get(id(lines), ()) if u in dist and v in dist]
    gaps = [g for g in gaps if g[0] <= 5.0]
    if gaps:
        _, u, v = min(gaps)
        n = u if dist[u] < dist[v] else v
    else:
        n = min(near, key=lambda n: km(n, d))
    path = [n]
    while path[-1] != sb:
        path.append(prev[path[-1]])
    return [[tuple(d)] + path] if len(path) > 1 else None


def along_km(lines, a, b):
    d, _ = shortest(lines, a, b)
    return 1e18 if d is None else d


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


SEE_PARTS = {"text": "See each part below", "closed": False, "implied": True}
OPEN_RANGE = re.compile(r"^\s*OPEN\s+(?!ALL\s+YEAR)", re.I)


def extra(r, detail=None):
    """One guide row as an entry of rules["also"]."""
    e = {k: r.get(k) for k in ("detail", "season", "bait", "species", "trout_total", "page")}
    if detail is not None:
        e["detail"] = detail
    see = r.get("cross_reference") or see_also(r)
    if see:
        # "... - See Battle Lake": the rules are under that entry, not "closed".
        e["season"] = {"text": "see that entry", "closed": False, "implied": True, "unknown": True}
        e["see"] = see
    return e


def see_also(r):
    """"See Forestburg Reservoir" at the end of a row with no season of its own
    (regulations.py marks only rows that start with "See")."""
    m = re.search(r"\bSee\s+([A-Z].*)$", r.get("detail") or "")
    if m and not ((r.get("season") or {}).get("text") or "").strip():
        return "See " + m.group(1).strip()
    return None


def rules_for(parts, zone, name):
    """The rule row of one stretch from its guide rows. parts is [(row, [periods])]:
    a row and the blank-detail rows right after it, which are more season periods
    of the same water (Jumpingpound Creek: June 16 to Aug. 31, then Sept. 1 to
    Oct. 31 with another whitefish limit). Every row is kept: the first is the
    rule row, the rest are in "also". When the stretch stands for parts of the
    river with different seasons, the line as a whole is neither open nor
    closed: its season says so, and each part is in "also"."""
    head, periods = parts[0]
    if len(parts) == 1 and not periods and (head.get("cross_reference") or see_also(head)):
        return {"basis": "cross-reference", "zone": zone, "matched_name": name,
                "see": head.get("cross_reference") or see_also(head),
                "detail": head.get("detail"), "page": head.get("page"),
                "season": {"text": "", "closed": False, "implied": False, "unknown": True}}
    rules = {k: v for k, v in head.items() if k not in ("also", "cross_reference")}
    rules.update(basis="site-specific", zone=zone, matched_name=name)
    also = []
    for i, (h, ps) in enumerate(parts):
        if i:
            also.append(extra(h))
        also += [extra(q, "(same stretch)") for q in ps]
    seasons = {(h.get("season") or {}).get("text") or "" for h, _ in parts}
    differ = [k for k in ("bait", "trout_total", "species") if any(h.get(k) != head.get(k) for h, _ in parts)]
    if len(parts) > 1 and (len(seasons) > 1 or differ):
        # Only what every part shares is said for the whole line; the first row
        # joins the others in "also", so each part's own rule is still there.
        also = [extra(head)] + also
        for k in differ:
            rules[k] = {"bait": "", "trout_total": None, "species": {}}[k]
    if len(parts) > 1 and len(seasons) > 1:
        rules["season"] = dict(SEE_PARTS)
    elif periods:
        texts = [(head.get("season") or {}).get("text") or ""] + [(q.get("season") or {}).get("text") or "" for q in periods]
        if all(OPEN_RANGE.match(t) for t in texts):
            # Open in either period: "OPEN JUNE 16 TO AUG. 31 AND SEPT. 1 TO OCT. 31",
            # the guide's own way of writing two ranges, which the app reads.
            rules["season"] = {"text": texts[0] + "".join(" AND " + OPEN_RANGE.sub("", t) for t in texts[1:]),
                               "closed": False, "implied": False}
    if also:
        rules["also"] = also
    return rules


def river_stretches(regs, zones, river_lines, outl, stocked=None):
    """(stretches, review rows)."""
    out, review = [], []
    stocked = stocked or {}
    for zone, unit in sorted(regs["zones"].items()):
        rivers = dict(unit["rivers"])
        for name, row in unit["lakes"].items():
            if flowing(name) and name not in rivers:
                rivers[name] = row
        for name, row in sorted(rivers.items()):
            if any(w in name for w in NOT_LINES):
                continue
            whole = river_lines.get(norm(name), [])
            if not whole:
                review.append({"lake": name, "zone": zone, "why": "no river line of that name in the water data"})
                continue
            lines = [l for l in whole if zones.of(*l[len(l) // 2]) == zone]
            if not lines:
                review.append({"lake": name, "zone": zone, "why": "no river line of that name in the zone"})
                continue
            lines = chain(lines)
            whole = chain(whole)
            # A blank-detail row belongs to the row above it (another season period).
            parts = []
            for r in [row] + list(row.get("also") or []):
                if parts and not (r.get("detail") or "").strip():
                    parts[-1][1].append(r)
                else:
                    parts.append((r, []))
            mine, rest = [], []
            for head, periods in parts:
                m = LIMIT_RE.search(head.get("detail") or "")
                part, how = None, None
                if m:
                    # Limits are looked for on the whole river: a dam or bridge at a
                    # unit's edge can sit on the part the nearest-lake zone gives the neighbour.
                    up, down = (m.group(1), m.group(3)) if m.group(2).lower() == "downstream" else (m.group(3), m.group(1))
                    (a, ha), (b, hb) = (find_limit(up, whole, river_lines, outl),
                                        find_limit(down, whole, river_lines, outl))
                    if "head" in (ha, hb) and (a or b):
                        top = higher_end(max(whole, key=len))
                        a, b = (top, b) if ha == "head" else (a, top)
                        ha, hb = ("exact" if top else None, hb) if ha == "head" else (ha, "exact" if top else None)
                    # A dam is at the downstream end of its reservoir: the end nearer
                    # the lower limit when the dam is the upper one, else the farther.
                    if ha == "dam" and b is not None and not str(hb).startswith("dam"):
                        a, ha = min(a, key=lambda e: along_km(whole, e, b)), "exact"
                    if hb == "dam" and a is not None and not str(ha).startswith("dam"):
                        b, hb = max(b, key=lambda e: along_km(whole, e, a)), "exact"
                    # Off the line: the river's line has a gap through the reservoir,
                    # so the dam is joined to it (straight distances to the other limit).
                    if ha == "dam off the line" and b is not None and not str(hb).startswith("dam"):
                        a = min(a, key=lambda e: km(e, b))
                        part, ha = cut_from_off(whole, a, b), "exact"
                    elif hb == "dam off the line" and a is not None and not str(ha).startswith("dam"):
                        b = max(b, key=lambda e: km(e, a))
                        back = cut_from_off(whole, b, a)
                        part, hb = ([back[0][::-1]] if back else None), "exact"
                    elif a and b and not any(str(h).startswith("dam") for h in (ha, hb)):
                        part = cut(whole, a, b)
                    if part:
                        how = "approximate" if "place" in (ha, hb) else "found"
                if part:
                    mine.append((part, [(head, periods)], how, head.get("detail")))
                else:
                    rest.append((head, periods, bool(m)))
            if rest:
                # Rows with no "from … to …" cover the river in this unit; a row whose
                # limits could not be placed makes the whole line an estimate.
                limits = "estimated" if any(x[2] for x in rest) else "unit"
                mine.append((lines, [(h, ps) for h, ps, _ in rest], limits, rest[0][0].get("detail") or ""))
            n = 0
            for part, ps, how, detail in mine:
                st = stretch(zone, name, n + 1, detail, part, rules_for(ps, zone, name), how)
                # On the map already as a stocked water (Kananaskis River, Medley
                # River): the stretch names that lake, so the app shows one pin. The
                # stretch is kept for its line and its guide rows, which the stocked
                # entry does not carry (regulations.py matches lakes, not rivers).
                twin = sorted((min(km((v[1], v[2]), sp) for sp in st["spots"]), k) for k, v in stocked.items()
                              if norm(v[0]) == norm(name))
                twin = [k for d, k in twin if d <= 30]
                if twin:
                    st["stocked_twin"] = twin[0]
                    if not any(r["lake"] == name and r["zone"] == zone and r["why"].startswith("on the map") for r in review):
                        review.append({"lake": name, "zone": zone, "why": "on the map as a stocked water"})
                n += 1
                out.append(st)
    return out, review


def stretch(zone, name, n, detail, lines, rules, limits):
    simple = [simplify(l) for l in lines]
    simple = [[[round(p[0], 4), round(p[1], 4)] for p in l] for l in simple if len(l) >= 2]
    return {"lake_id": f"rv-{zone.lower()}-{slug(name)}-{n}", "name": name, "zone": zone, "detail": detail,
            "limits": limits, "length_km": round(line_km(lines), 1), "line": simple, "spots": spots_for(lines),
            "rules": rules}


WATER_SOURCE = ("Natural Resources Canada, CanVec 1:50,000 Hydro, Alberta "
                "(watercourse, water_linear_flow, waterbody)")


def unsettled_twins(twin_rows):
    """The twins whose stocked lake does not carry the guide row yet: each wants a
    line in data/regs_aliases.csv (lake_id, lake, regulation_name, confirmed_by, note)."""
    resolved = json.loads((DATA / "lake_regulations.json").read_text(encoding="utf-8"))["lakes"]
    out = []
    for t in twin_rows:
        for k, sname, szone, d, how in t["twins"]:
            have = resolved.get(k) or {}
            if have.get("basis") == "site-specific" and norm(have.get("matched_name")) == norm(t["lake"]) \
                    and have.get("zone") == t["zone"]:
                continue
            out.append({"lake_id": k, "lake": sname, "zone": szone, "regulation_name": t["lake"],
                        "guide_zone": t["zone"], "km": d, "how": how, "placed_by": t["coord_source"],
                        "now": have.get("basis") or "nothing"})
    return out


def run(canvec_path, cgn_path, regs=None, cgn=None, outl=None, river_lines=None):
    """Everything main() writes, as (lakes, review, rivers, twins). The inputs can
    be handed in (the tests and a re-run read them once)."""
    regs = regs or regulations.load(PDF)
    cgn = cgn if cgn is not None else read_cgn(cgn_path)
    PLACES.clear()
    for r in cgn:
        try:
            PLACES.setdefault(norm(r["Geographical Name"]), []).append((float(r["Latitude"]), float(r["Longitude"])))
        except ValueError:
            pass
    stocked = stocked_lakes()
    zones = Zones(stocked)
    outl = outl if outl is not None else outlines(canvec_path)
    WATER["path"] = canvec_path
    LAKE_POINTS[:] = cgn_rows(cgn)
    lakes, review, twins = placed_lakes(regs, zones, LAKE_POINTS, outl, stocked)
    wanted = {norm(n) for u in regs["zones"].values() for n in list(u["rivers"]) + [x for x in u["lakes"] if flowing(x)]}
    for u in regs["zones"].values():
        for r in u["rivers"].values():
            for rr in [r] + list(r.get("also") or []):
                for m in re.finditer(r"([A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*)*\s+(?:River|Creek))", rr.get("detail") or ""):
                    wanted.add(norm(m.group(1)))
    river_lines = river_lines(wanted) if callable(river_lines) else courses(canvec_path, wanted)
    rivers, river_review = river_stretches(regs, zones, river_lines, outl, stocked)
    return regs, lakes, review + river_review, rivers, twins


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    regs, lakes, review, rivers, twins = run(argv[1], argv[2])
    write(regs, lakes, review, rivers)
    report(lakes, review, rivers, twins)


def write(regs, lakes, review, rivers):
    src = {"guide": f"Alberta Guide to Sportfishing Regulations {regs['guide_year']} (site-specific tables)",
           "places": "Natural Resources Canada, Canadian Geographical Names Database (CGNDB), Alberta",
           "water": WATER_SOURCE,
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
        for r in sorted(review, key=lambda r: (r["zone"], r["lake"], r["why"])):
            w.writerow(r)


def report(lakes, review, rivers, twins):
    print(f"lakes placed {len(lakes)} {dict(Counter(l['coord_source'] for l in lakes))}; review {len(review)}")
    print(f"river stretches {len(rivers)}: limits {dict(Counter(r['limits'] for r in rivers))}, "
          f"spots {sum(len(r['spots']) for r in rivers)}, km {round(sum(r['length_km'] for r in rivers))}")
    print(f"guide lakes on the map as stocked lakes: {len(twins)}")
    for t in unsettled_twins(twins):
        print(f"  not settled yet: {t['lake_id']} {t['lake']} ({t['zone']}, now {t['now']}) is guide "
              f"{t['regulation_name']} ({t['guide_zone']}), {t['how']}, {t['km']} km, placed by {t['placed_by']}")


if __name__ == "__main__":
    main(sys.argv)
