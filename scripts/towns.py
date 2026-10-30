"""Build the offline list of Alberta towns from the national names database.

The app lets someone type "Olds" or "Hinton" and jump the map there, with no
connection, at a lake. That needs a small list of places that people actually
live in, with a point for each. Natural Resources Canada publishes exactly
that as part of the Canadian Geographical Names Database (CGNDB), under the
Open Government Licence - Canada 2.0.

Usage:

    python -I scripts/towns.py <path to cgn_ab_csv_eng.csv or its .zip>

The download is treated as untrusted data: it is only ever read as CSV text,
never imported or executed, and nothing in it decides where output goes.

What is kept
------------
Only names whose feature is a populated place: cities, towns, villages,
summer villages, hamlets, urban communities, Metis settlements, townsites,
localities, plus specialized municipalities, Indian reserves and First
Nation administrative locations. "Former Locality", "Former Post Office",
"Post Office", "Railway Point", "Customs Point" and the historic river-lot
"Settlement" entries are dropped — a railway siding or a post
office that closed in 1940 is not somewhere a person can drive to and find a
town. Counties, municipal districts, improvement districts and special areas
are dropped too: their point sits somewhere in an area hundreds of
kilometres wide, so jumping to it would mislead.

The database also lists some places twice — once as a hamlet and once as a
locality, or a reserve and its townsite. The same name within 5 km is one
place; the more specific kind wins (a town beats a locality).
"""

import csv
import io
import json
import math
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "towns_ab.json"

# Generic Term in the CGNDB -> the kind the app shows. Order is priority when
# two entries collapse into one: earlier wins.
KINDS = [
    ("City", "city"),
    ("Town", "town"),
    ("Specialized Municipality", "specialized municipality"),
    ("Urban Community", "urban community"),
    ("Village", "village"),
    ("Summer Village", "summer village"),
    ("Hamlet", "hamlet"),
    ("Metis Settlement", "Metis settlement"),
    ("Townsite", "townsite"),
    ("First Nation Administrative Location", "First Nation"),
    ("Indian Reserve", "Indian reserve"),
    ("Locality", "locality"),
]
KIND_OF = dict(KINDS)
PRIORITY = {kind: i for i, (_, kind) in enumerate(KINDS)}

SAME_PLACE_KM = 5.0


def _rows(path):
    """The CSV rows, from the .csv itself or from the .zip NRCan publishes."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".csv")]
            if len(names) != 1:
                raise SystemExit(f"expected one CSV in {path}, found {names}")
            text = z.read(names[0]).decode("utf-8-sig")
    else:
        text = path.read_text(encoding="utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def _km(a, b):
    """Great-circle distance between two (lat, lon) points, in kilometres."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, h)))


def build(rows):
    """[[name, lat, lon, kind], ...] sorted by name, one entry per place."""
    picked = []
    for r in rows:
        if r.get("Province - Territory") != "Alberta":
            continue
        kind = KIND_OF.get(r.get("Generic Term"))
        if not kind:
            continue
        name = (r.get("Geographical Name") or "").strip()
        try:
            lat = float(r["Latitude"])
            lon = float(r["Longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        # Alberta's box, loosely. A point outside it is a typo, not a town.
        if not name or not (48.9 <= lat <= 60.1 and -120.1 <= lon <= -109.9):
            continue
        picked.append((name, lat, lon, kind))

    # Best kind first, so the survivor of a collapse is the most specific one.
    picked.sort(key=lambda p: (p[0].casefold(), PRIORITY[p[3]]))
    kept = []
    by_name = {}
    for name, lat, lon, kind in picked:
        others = by_name.setdefault(name.casefold(), [])
        if any(_km((lat, lon), o) <= SAME_PLACE_KM for o in others):
            continue
        others.append((lat, lon))
        kept.append([name, round(lat, 5), round(lon, 5), kind])

    kept.sort(key=lambda p: (p[0].casefold(), p[0], p[1], p[2]))
    return kept


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__.split("Usage:")[1].split("The download")[0].strip())
    towns = build(_rows(argv[1]))
    OUT.write_text(
        "[" + ",\n".join(json.dumps(t, ensure_ascii=False, separators=(",", ":"))
                         for t in towns) + "]\n",
        encoding="utf-8", newline="\r\n")
    kinds = {}
    for t in towns:
        kinds[t[3]] = kinds.get(t[3], 0) + 1
    print(json.dumps({"count": len(towns), "bytes": OUT.stat().st_size,
                      "kinds": kinds}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
