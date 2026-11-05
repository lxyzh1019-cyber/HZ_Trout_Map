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

    python -I scripts/lake_zones.py

Writes data/lake_zones.csv, one row per stocked lake:

    lake_id, name, alberta_zone, how, guide_zones

"guide_zones" lists the zones whose tables or put-and-take list name the lake.
scripts/build_history.py reads only this file, so the build stays offline and
repeatable, and it decides there which zone a lake takes (see apply_zones).
"""

import csv
import datetime
import glob
import json
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
            with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=120) as r:
                out = json.load(r)
            if "error" in out:
                raise RuntimeError(out["error"])
            return out
        except Exception as e:  # network trouble: wait and try again
            if attempt == 3:
                raise
            print(f"  retry {layer}: {e}", file=sys.stderr)
            time.sleep(2 ** (attempt + 1))


def by_id(layer, ids):
    """WB_ID -> set of FMZ codes in one regulations layer."""
    out = {}
    ids = sorted(ids)
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        r = query(layer, where=f"WB_ID IN ({','.join(chunk)})", outFields="WB_ID,FMZ",
                  returnGeometry="false")
        for f in r.get("features", []):
            a = f["attributes"]
            if a.get("FMZ"):
                out.setdefault(str(a["WB_ID"]), set()).add(a["FMZ"].strip())
    return out


def zone_outlines():
    """[(code, [ring of (lon, lat)])] for the zone outlines, simplified to about 50 m."""
    r = query(4, where="1=1", outFields="FISHUNIT_CODE,FISHUNIT_NAME", outSR=4326,
              maxAllowableOffset=0.0005, returnGeometry="true")
    out = []
    for f in r["features"]:
        a = f["attributes"]
        code = zone_code(a.get("FISHUNIT_NAME"), a.get("FISHUNIT_CODE"))
        for ring in f["geometry"]["rings"]:
            out.append((code, ring))
    return out


def zone_code(name, code):
    """ES1 etc. from the outline's name, e.g. "ES1 - Eastern Slopes ..."."""
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


def point_zone(outlines, lat, lon):
    """The zone whose outline holds the point. Holes are counted with the even-odd rule."""
    count = {}
    for code, ring in outlines:
        if inside(lon, lat, ring):
            count[code] = count.get(code, 0) + 1
    zones = sorted(c for c, n in count.items() if n % 2 == 1)
    return zones[0] if len(zones) == 1 else None


def norm(name):
    s = re.sub(r"\(.*?\)", " ", (name or "").lower())
    s = s.replace("’", "'").replace("'s", "s")
    return re.sub(r"[^a-z0-9]", "", s)


def guide_zones():
    """normalised guide name -> zones whose tables or put-and-take list name it."""
    sys.path.insert(0, str(Path(__file__).parent))
    import regulations
    regs = regulations.load(GUIDE)
    out = {}
    for zone, tables in regs["zones"].items():
        for key in ("lakes", "rivers"):
            for name in tables[key]:
                out.setdefault(norm(name), set()).add(zone)
    for name, entry in regs["stocked"].items():
        if entry.get("zone"):
            out.setdefault(norm(name), set()).add(entry["zone"])
    return out


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
    outlines = zone_outlines()
    guide = guide_zones()
    print(f"  lake layer {len(lake_layer)}, river layer {len(river_layer)}, "
          f"{len(outlines)} zone outline rings")

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
        named = set()
        for n in names_of(lake):
            named |= guide.get(n, set())
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
