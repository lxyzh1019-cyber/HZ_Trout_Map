"""Each stocked lake's fishing zone (watershed unit), from Alberta's own map.

The zone normally comes from the lake's MyWildAlberta profile. 60 stocked lakes
have no profile zone, so their own guide rows cannot attach: a guide row only
attaches inside the lake's zone. Alberta's sportfishing regulations map gives
the zone of every regulated lake and river:

    https://geospatial.alberta.ca/titan/rest/services/fisheries/fisheries_regulations/MapServer
      layer 1 "Lake Regulations"     WB_ID, FMZ (the zone of the lake)
      layer 0 "River Regulations"    WB_ID, FMZ
      layer 4 "Fish Managment Zones" the zone outlines

A lake with an Alberta waterbody id (lake_id "wb<id>") is looked up by that id
in layers 1 and 0. Any other lake, or one the layers do not list, takes the
zone whose outline holds its position.

Usage:

    python -I scripts/lake_zones.py [zone outlines cache file]

With a cache file (kept outside the repository, e.g. next to the CanVec
download), the zone outlines are read from it, or fetched once and saved to it.

Writes data/lake_zones.csv, one row per stocked lake:

    lake_id, name, alberta_zone, how, guide_zones

"guide_zones" lists the zones in which the guide's tables or put-and-take list
name this lake: an entry counts when its land description is within 15 km of the
lake, or, with no land description, when it carries the lake's own name and that
name is in one zone only (see confirming_zones).
scripts/build_history.py reads only this file, so the build stays offline and
repeatable, and it decides there which zone a lake takes (see apply_zones).
"""

import csv
import datetime
import glob
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
OUT = DATA / "lake_zones.csv"
BASE = "https://geospatial.alberta.ca/titan/rest/services/fisheries/fisheries_regulations/MapServer/"
GUIDE = DATA / "raw" / "alberta-sportfishing-regulations-2026-tables.pdf"
FIELDS = ["lake_id", "name", "alberta_zone", "how", "guide_zones"]


def query(layer, **params):
    params.setdefault("f", "json")
    url = BASE + f"{layer}/query"
    body = urllib.parse.urlencode(params).encode()
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=180) as r:
                out = json.load(r)
            if "error" in out:
                raise RuntimeError(out["error"])
            break
        except Exception as e:  # network trouble: wait and try again
            if attempt == 3:
                raise
            print(f"  retry {layer}: {e}", file=sys.stderr)
            time.sleep(2 ** (attempt + 1))
    # A cut-short answer would quietly send lakes to the outline lookup.
    if out.get("exceededTransferLimit"):
        raise RuntimeError(f"layer {layer}: the server cut the answer short; ask in smaller parts")
    return out


def by_id(layer, ids):
    """WB_ID -> set of FMZ codes in one regulations layer."""
    out = {}
    ids = sorted(ids)
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        r = query(layer, where=f"WB_ID IN ({','.join(chunk)})", outFields="WB_ID,FMZ",
                  returnGeometry="false")
        for f in r.get("features", []):
            a = f["attributes"]
            if a.get("FMZ"):
                out.setdefault(str(a["WB_ID"]), set()).add(a["FMZ"].strip())
    return out


def zone_outlines(cache=None):
    """[(code, [rings of (lon, lat)], box)] for the zone outlines, one entry per
    outline as Alberta draws it, not simplified. With cache (a file path), the
    outlines are read from it when it exists and saved to it when fetched, so a
    re-run does not depend on the map service."""
    if cache and Path(cache).exists():
        raw = json.loads(Path(cache).read_text(encoding="utf-8"))
    else:
        r = query(4, where="1=1", outFields="FISHUNIT_CODE,FISHUNIT_NAME", outSR=4326,
                  geometryPrecision=5, returnGeometry="true")
        raw = [{"code": zone_code(f["attributes"].get("FISHUNIT_NAME"), f["attributes"].get("FISHUNIT_CODE")),
                "rings": f["geometry"]["rings"]} for f in r["features"]]
        if cache:
            Path(cache).write_text(json.dumps(raw), encoding="utf-8")
    out = []
    for f in raw:
        pts = [p for ring in f["rings"] for p in ring]
        box = (min(p[1] for p in pts), min(p[0] for p in pts), max(p[1] for p in pts), max(p[0] for p in pts))
        out.append((f["code"], f["rings"], box))
    return out


def zone_code(name, code):
    """ES1 etc. from the outline's name ("NB3", or "ES1 - Eastern Slopes ...")."""
    m = re.search(r"\b(ES|PP|NB)\s*-?\s*(\d)\b", name or "")
    if m:
        return m.group(1) + m.group(2)
    raise ValueError(f"zone outline without a code: {name!r} {code!r}")


def inside(lon, lat, ring):
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def _edge_km(lat, lon, ring):
    kx = 111.32 * math.cos(math.radians(lat))
    best = 1e18
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        ax, ay, bx, by = (x1 - lon) * kx, (y1 - lat) * 110.57, (x2 - lon) * kx, (y2 - lat) * 110.57
        dx, dy = bx - ax, by - ay
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def point_zone(outlines, lat, lon, near_km=2.0):
    """The zone whose outline holds the point. Each outline counts its own rings
    with the even-odd rule, so a hole is a hole of that outline only. A point
    in no outline, or in two (a sliver along a shared border), takes the zone
    whose edge is nearest, if it is within near_km; else None (outside Alberta)."""
    held = set()
    for code, rings, box in outlines:
        if not (box[0] <= lat <= box[2] and box[1] <= lon <= box[3]):
            continue
        if sum(inside(lon, lat, ring) for ring in rings) % 2 == 1:
            held.add(code)
    if len(held) == 1:
        return next(iter(held))
    pad = near_km / 100.0 * 2
    best = None
    for code, rings, box in outlines:
        if held and code not in held:
            continue
        if not (box[0] - pad <= lat <= box[2] + pad and box[1] - pad <= lon <= box[3] + pad):
            continue
        d = min(_edge_km(lat, lon, ring) for ring in rings)
        if d <= near_km and (best is None or d < best[0]):
            best = (d, code)
    return best[1] if best else None


def norm(name):
    s = re.sub(r"\(.*?\)", " ", (name or "").lower())
    s = s.replace("\u2019", "'").replace("'s", "s")
    return re.sub(r"[^a-z0-9]", "", s)


ATS_IN_TEXT = re.compile(r"(?:(NE|NW|SE|SW)\s*)?(\d{1,2})-(\d{1,3})-(\d{1,2})-(W[456])")
NEAR_KM = 15.0


def where(text):
    """(lat, lon) of the first land description in a guide entry, or None."""
    sys.path.insert(0, str(Path(__file__).parent))
    import ats
    m = ATS_IN_TEXT.search(text or "")
    if not m:
        return None
    q, sec, twp, rng, mer = m.groups()
    lat, lon = ats.ats_to_latlng(f"{q or ''}{sec}-{twp}-{rng}-{mer}")
    return (lat, lon) if lat is not None else None


def guide_entries():
    """normalised guide name -> [(zone, (lat, lon) or None)], one per table row or
    put-and-take entry that names it."""
    sys.path.insert(0, str(Path(__file__).parent))
    import regulations
    regs = regulations.load(GUIDE)
    out = {}
    for zone, tables in regs["zones"].items():
        for key in ("lakes", "rivers"):
            for name, row in tables[key].items():
                out.setdefault(norm(name), []).append((zone, where(row.get("detail"))))
    for name, entry in regs["stocked"].items():
        if entry.get("zone"):
            out.setdefault(norm(name), []).append((entry["zone"], where(entry.get("ats"))))
    return out


def km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, h)))


def confirming_zones(lake, entries):
    """The zones in which the guide names THIS lake. A guide entry counts when its
    land description is within NEAR_KM of the lake; an entry without one counts
    only for the lake's own name (not a name in its brackets) and only when that
    name is in one zone across the whole guide. Same-named lakes elsewhere, such
    as the many Swan, Fish and Jackfish lakes, then confirm nothing."""
    pos = (float(lake["lat"]), float(lake["lon"])) if lake.get("lat") is not None else None
    main = norm(lake["name"])
    zones = set()
    for n in names_of(lake):
        hits = entries.get(n, [])
        unique = len({z for z, _ in hits}) == 1
        for zone, at in hits:
            if at and pos:
                if km(at, pos) <= NEAR_KM:
                    zones.add(zone)
            elif not at and n == main and unique:
                zones.add(zone)
    return zones


def stocked_lakes():
    """lake_id -> the newest year's record, as the app merges the year files."""
    lakes = {}
    for path in sorted(glob.glob(str(DATA / "lakes_20*.json"))):
        for lake in json.loads(Path(path).read_text(encoding="utf-8")):
            lakes[lake["lake_id"]] = lake
    return lakes


def names_of(lake):
    """The lake's name and the names inside its brackets, e.g. Running Rain Lake (Storm Lake)."""
    out = {norm(lake["name"])}
    for inner in re.findall(r"\((.*?)\)", lake["name"]):
        out.add(norm(inner))
    return out


def main():
    lakes = stocked_lakes()
    ids = {re.match(r"wb(\d+)$", k).group(1) for k in lakes if re.match(r"wb(\d+)$", k)}
    print(f"{len(lakes)} stocked lakes, {len(ids)} with an Alberta waterbody id")
    lake_layer = by_id(1, ids)
    river_layer = by_id(0, ids)
    outlines = zone_outlines(sys.argv[1] if len(sys.argv) > 1 else None)
    entries = guide_entries()
    print(f"  lake layer {len(lake_layer)}, river layer {len(river_layer)}, "
          f"{len(outlines)} zone outlines")

    rows = []
    for lake_id, lake in sorted(lakes.items(), key=lambda kv: (kv[1]["name"], kv[0])):
        m = re.match(r"wb(\d+)$", lake_id)
        zones, how = set(), ""
        if m and m.group(1) in lake_layer:
            zones, how = lake_layer[m.group(1)], "lake layer by waterbody id"
        elif m and m.group(1) in river_layer:
            zones, how = river_layer[m.group(1)], "river layer by waterbody id"
        if len(zones) != 1 and lake.get("lat") is not None:
            z = point_zone(outlines, float(lake["lat"]), float(lake["lon"]))
            if z:
                zones, how = {z}, "zone outline at the lake's position"
        alberta = next(iter(zones)) if len(zones) == 1 else ""
        named = confirming_zones(lake, entries)
        rows.append(dict(lake_id=lake_id, name=lake["name"], alberta_zone=alberta,
                         how=how if alberta else "not found", guide_zones=" ".join(sorted(named))))

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    missing = [r["name"] for r in rows if not r["alberta_zone"]]
    if missing:
        print(f"  {len(missing)} not found on Alberta's map: " + ", ".join(missing))
    print(f"Wrote {OUT.relative_to(ROOT)} ({datetime.date.today().isoformat()})")


if __name__ == "__main__":
    main()
