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


def courses(path, wanted):
    """normalised river name -> [polyline [(lat, lon), ...]] for the named watercourses wanted."""
    r = canvec(path, "watercourse_1")
    out = defaultdict(list)
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
                near = [o for o in lines_by_name.get(norm(name), []) if km((lat, lon), o[:2]) <= 3]
                entry.update(lat=lat, lon=lon, ats=code, coord_source="ats")
                if near:
                    entry["surface_area_ha"] = near[0][2]
            elif len(outl) == 1:
                entry.update(lat=outl[0][0], lon=outl[0][1], surface_area_ha=outl[0][2], coord_source="outline")
            elif len(outl) > 1:
                review.append({"lake": name, "zone": zone, "why": f"{len(outl)} outlines of that name in the zone"})
                continue
            elif len(pts) == 1:
                entry.update(lat=round(pts[0][0], 5), lon=round(pts[0][1], 5), coord_source="place names")
            else:
                review.append({"lake": name, "zone": zone,
                               "why": "no place of that name in the zone" if not pts else f"{len(pts)} places of that name in the zone"})
                continue
            # Already on the map as a stocked lake (its zone or name form may differ).
            twins = [k for k, v in stocked.items()
                     if norm(v[0]) in {norm(x) for x in variants(name)} and km((v[1], v[2]), (entry["lat"], entry["lon"])) <= 10]
            if twins:
                continue
            entry["lake_id"] = f"gu-{zone.lower()}-{slug(name)}"
            if rules:
                entry["rules"] = rules
            out.append(entry)
    return out, review


LIMIT_RE = re.compile(r"(?:from\s+)?(.+?)\s+downstream\s+to\s+(?:the\s+)?(.+)", re.I)


def find_limit(text, river_lines, feature_lines, outl):
    """A point on the river for one named limit, or None."""
    t = (text or "").strip()
    a = first_ats(t)
    if a:
        return a[:2]
    if re.search(r"Saskatchewan border", t, re.I):
        pts = [p for line in river_lines for p in line]
        return min(pts, key=lambda p: abs(p[1] + 110.0)) if pts else None
    m = re.match(r"(?:the\s+)?([A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*)*\s+(?:River|Creek|Lake|Reservoir))\b", t)
    if not m:
        return None
    target = norm(m.group(1))
    tpts = [p for line in feature_lines.get(target, []) for p in line] + [o[:2] for o in outl.get(target, [])]
    if not tpts:
        return None
    best, bd = None, 3.0
    for line in river_lines:
        for p in line:
            d = min(km(p, q) for q in tpts[:: max(1, len(tpts) // 400)])
            if d < bd:
                best, bd = p, d
    return best


def cut(lines, a, b):
    """The vertices of the river between two limit points (along the longest line)."""
    line = max(lines, key=len)
    ia = min(range(len(line)), key=lambda i: km(line[i], a))
    ib = min(range(len(line)), key=lambda i: km(line[i], b))
    lo, hi = sorted((ia, ib))
    return [line[lo:hi + 1]] if hi > lo else None


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
            lines = [l for l in river_lines.get(norm(name), [])
                     if zones.of(*l[len(l) // 2]) == zone]
            if not lines:
                continue
            lines = chain(lines)
            rest = []
            n = 0
            for r in rows:
                rules = {k: v for k, v in r.items() if k != "also"}
                rules.update(basis="site-specific", zone=zone, matched_name=name)
                m = LIMIT_RE.search(r.get("detail") or "")
                part = None
                if m:
                    a = find_limit(m.group(1), lines, river_lines, outl)
                    b = find_limit(m.group(2), lines, river_lines, outl)
                    if a and b:
                        part = cut(lines, a, b)
                if part:
                    n += 1
                    out.append(stretch(zone, name, n, r.get("detail"), part, rules, [rules], "found"))
                else:
                    rest.append(rules)
            if rest:
                n += 1
                out.append(stretch(zone, name, n, rest[0].get("detail") or "", lines, rest[0], rest, "estimated"))
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
    print(f"river stretches {len(rivers)}: limits found {sum(1 for r in rivers if r['limits'] == 'found')}, "
          f"spots {sum(len(r['spots']) for r in rivers)}, km {round(sum(r['length_km'] for r in rivers))}")


if __name__ == "__main__":
    main(sys.argv)
