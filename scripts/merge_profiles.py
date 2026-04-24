"""
merge_profiles.py — enrich a lakes_YYYY.json file with profile data from the
MyWildAlberta profiles CSV (zone, surface area, amenities, and name/coord
overrides).

USAGE:
    python merge_profiles.py ../data/lakes_2025.json

The file is updated in place. Unmatched ATS codes are reported; you can add
them to profiles/mywildalberta_profiles.csv and re-run.

CSV columns used (from mywildalberta_profiles.csv):
    ats              ATS code — primary key for the join
    html_lat         Authoritative latitude (overrides extractor's lat)
    html_lon         Authoritative longitude (overrides extractor's lon)
    Trout Map Name   Display name (falls back to `name`)
    name             Profile name (falls back if Trout Map Name blank)
    zone             Regulatory zone (e.g. ES1, PP2)
    surface_area     Surface area, usually "123.4 ha"
    site_amenities   Free-text amenities list
"""

import csv
import json
import re
import sys
from pathlib import Path


PROFILES_CSV = Path(__file__).parent.parent / "profiles" / "mywildalberta_profiles.csv"


def parse_float(s):
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_area_ha(s):
    """Surface area in the CSV is like '123.4 ha' or '1,234 ha' or blank."""
    if not s:
        return None
    s = s.strip().replace(",", "")
    m = re.match(r"^([\d.]+)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def load_profiles():
    """Return dict ats -> profile."""
    profiles = {}
    with open(PROFILES_CSV, newline="", encoding="cp1252") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ats = (row.get("ats") or "").strip()
            if not ats:
                continue
            display_name = (row.get("Trout Map Name") or "").strip() or (row.get("name") or "").strip()
            profiles[ats] = {
                "display_name": display_name or None,
                "lat": parse_float(row.get("html_lat")),
                "lon": parse_float(row.get("html_lon")),
                "zone": (row.get("zone") or "").strip() or None,
                "surface_area_ha": parse_area_ha(row.get("surface_area")),
                "amenities": (row.get("site_amenities") or "").strip() or None,
            }
    return profiles


def merge(lakes_path):
    lakes_path = Path(lakes_path)
    lakes = json.loads(lakes_path.read_text(encoding="utf-8"))
    profiles = load_profiles()

    name_changes = 0
    coord_changes = 0
    unmatched = []

    for lk in lakes:
        prof = profiles.get(lk["ats"])
        if not prof:
            lk["zone"] = None
            lk["surface_area_ha"] = None
            lk["amenities"] = None
            unmatched.append(lk)
            continue

        if prof["display_name"] and prof["display_name"] != lk["name"]:
            lk["name"] = prof["display_name"]
            name_changes += 1

        if prof["lat"] is not None and prof["lon"] is not None:
            if (lk["lat"], lk["lon"]) != (prof["lat"], prof["lon"]):
                lk["lat"] = prof["lat"]
                lk["lon"] = prof["lon"]
                coord_changes += 1

        lk["zone"] = prof["zone"]
        lk["surface_area_ha"] = prof["surface_area_ha"]
        lk["amenities"] = prof["amenities"]

    lakes_path.write_text(json.dumps(lakes, indent=2), encoding="utf-8")

    print(f"Merged {lakes_path.name}:")
    print(f"  Total lakes:     {len(lakes)}")
    print(f"  Names updated:   {name_changes}")
    print(f"  Coords updated:  {coord_changes}")
    print(f"  Unmatched:       {len(unmatched)}")
    for lk in unmatched:
        print(f"    UNMATCHED: {lk['name']}  ({lk['ats']})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python merge_profiles.py <path-to-lakes_YYYY.json>")
        sys.exit(1)
    merge(sys.argv[1])
