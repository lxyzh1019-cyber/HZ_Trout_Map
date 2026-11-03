"""Which stocked lakes have a published depth chart, and where to get it.

The Alberta Geological Survey (AGS) digitised Alberta's historic hydrographic
survey maps into bathymetry datasets, one DIG publication per lake. Its
interactive Lake Bathymetry Data page draws them from one ArcGIS layer of lake
outlines, each carrying the lake name and its bathymetry DIG number:

    https://ags.aer.ca/interactive-data-and-tools/lake-bathymetry-data

A stocked lake gets a link only when BOTH its name and its position agree with
an outline: the name, with "lake", chain parts ("Upper", "#3"), brackets and
punctuation dropped, must be the same, and the lake's point must fall inside
the outline or within 2 km of it. A one-letter spelling difference ("Kehewin"
and "Kehiwin") counts only with the point inside the outline. A name
alone is not enough — Alberta has several lakes of most names — and a position
alone is not enough either, since a pond can sit on the shore of a surveyed lake.

Usage:

    python -I scripts/depth_charts.py

Writes data/depth_charts.json and prints the match count. The layer is read
as data only; nothing in it decides where output goes.
"""

import datetime
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from elevation import get_json, placed_lakes  # noqa: E402

ROOT = Path(__file__).parent.parent
OUT = ROOT / "data" / "depth_charts.json"
PAGE = "https://ags.aer.ca/interactive-data-and-tools/lake-bathymetry-data"
LAYER = ("https://services2.arcgis.com/jQV6VMr2Loovu7GU/arcgis/rest/services/"
         "Lake_Boundary/FeatureServer/0/query")
NEAR_KM = 2.0


def norm(name):
    """Name without the words that vary between lists: "lake", a part of a
    chain ("Upper", "#3") and anything in brackets."""
    n = str(name or "").lower().replace("&", " and ")
    n = re.sub(r"\(.*?\)", " ", n)
    n = re.sub(r"#\s*\d+", " ", n)
    n = re.sub(r"\b(lake|lakes|reservoir|pond|the|upper|middle|lower)\b", " ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


def one_edit(a, b):
    """True when a and b differ by at most one letter added, dropped or changed."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i + (len(a) == len(b)):] == b[i + 1:]


def same_lake(our_name, their_name, km_off):
    """Same name, near the outline; or a one-letter spelling difference
    ("Kehewin" and "Kehiwin") with the point inside the outline."""
    a, b = norm(our_name), norm(their_name)
    if not a or not b:
        return False
    if a == b:
        return km_off <= NEAR_KM
    return km_off == 0 and min(len(a), len(b)) >= 3 and one_edit(a, b)


def km(lat1, lon1, lat2, lon2):
    r = math.radians
    a = (math.sin(r(lat2 - lat1) / 2) ** 2
         + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(r(lon2 - lon1) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(a))


def inside(lat, lon, ring):
    hit = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            hit = not hit
        j = i
    return hit


def distance_to_outline(lat, lon, rings):
    """0 inside the outline, else km to the nearest vertex (outlines are dense)."""
    if any(inside(lat, lon, ring) for ring in rings):
        return 0.0
    return min(km(lat, lon, y, x) for ring in rings for x, y in ring)


def dig_url(dig):
    m = re.match(r"DIG\s*(\d{4})-(\d{4})", str(dig or ""), re.I)
    return f"https://ags.aer.ca/publication/dig-{m.group(1)}-{m.group(2)}" if m else None


def outlines():
    url = (LAYER + "?where=1%3D1&outFields=LAKE_NAME,ATS_GRID,BATHYMETRY_DIG_NUM"
           "&returnGeometry=true&outSR=4326&geometryPrecision=5&f=json")
    body = get_json(url)
    out = []
    for f in body.get("features", []):
        a = f.get("attributes") or {}
        rings = (f.get("geometry") or {}).get("rings") or []
        if a.get("LAKE_NAME") and rings and dig_url(a.get("BATHYMETRY_DIG_NUM")):
            out.append({"name": a["LAKE_NAME"], "ats": a.get("ATS_GRID"),
                        "dig": a["BATHYMETRY_DIG_NUM"], "rings": rings})
    return out


def lake_names():
    names = {}
    for path in sorted((ROOT / "data").glob("lakes_20*.json")):
        for lake in json.loads(path.read_text(encoding="utf-8")):
            key = lake.get("lake_id") or lake.get("ats")
            if lake.get("name"):
                names[key] = lake["name"]
    return names


def main():
    charts = outlines()
    names = lake_names()
    lakes = placed_lakes()
    matched = {}
    for key, (lat, lon) in lakes.items():
        ours = names.get(key)
        if not norm(ours):
            continue
        best = None
        for c in charts:
            if not one_edit(norm(ours), norm(c["name"])):
                continue
            d = distance_to_outline(lat, lon, c["rings"])
            if same_lake(ours, c["name"], d) and (best is None or d < best[0]):
                best = (d, c)
        if best:
            c = best[1]
            matched[key] = {"name": c["name"], "dig": c["dig"], "url": dig_url(c["dig"]),
                            "km_from_outline": round(best[0], 2)}
    record = {
        "source": "Alberta Geological Survey, Lake Bathymetry Data (Lake_Boundary layer)",
        "page": PAGE,
        "layer": LAYER.rsplit("/query", 1)[0],
        "retrieved": datetime.date.today().isoformat(),
        "surveyed": len(charts),
        "placed_lakes": len(lakes),
        "matched": len(matched),
        "rule": ("same name without 'lake', chain parts (Upper, #3), brackets and punctuation, with the lake's "
                 "point inside the outline or within 2 km; or one letter different with the point inside"),
        "lakes": dict(sorted(matched.items())),
    }
    OUT.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\r\n")
    print(f"{len(matched)} of {len(lakes)} placed lakes match one of {len(charts)} surveyed lakes -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
