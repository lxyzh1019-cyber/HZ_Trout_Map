"""
merge_profiles.py — enrich a lakes_YYYY.json file with profile data from the
MyWildAlberta profiles CSV (coordinates, zone, surface area, amenities, and the
display name).

USAGE:
    python merge_profiles.py ../data/lakes_2025.json

The file is updated in place. Unmatched ATS codes are reported; you can add
them to profiles/mywildalberta_profiles.csv and re-run.

Where coordinates come from
---------------------------
Each lake gets a ``coord_source`` field recording which of these was used, in
descending order of preference:

  ``override``  ``override_lat`` / ``override_lon`` — a coordinate you placed
                by hand to correct a specific lake. Always wins.
  ``profile``   ``lat`` / ``lon`` — the hand-verified MyWildAlberta coordinates.
                Median 0.53 km from the ATS quarter-section the stocking report
                names for the same lake, so the two independent sources agree.
  ``ats``       Derived from the ATS code by ats.py. Used only when the lake has
                no profile row or no profile coordinate. Expect ~0.5 km error.

The ``html_lat`` / ``html_lon`` columns are deliberately NOT used. They are not
an independent observation: for 249 of 265 rows they reproduce the old (buggy)
ATS estimate to within 50 m, which put every pin a median 6 km off the water.

CSV columns used:
    ats                          ATS code — primary key for the join
    lat, lon                     Hand-verified coordinates (preferred)
    override_lat, override_lon   Manual per-lake correction (optional column)
    Trout Map Name               Display name (falls back to `name`)
    name                         Profile name (falls back if Trout Map Name blank)
    zone                         Regulatory zone (e.g. ES1, PP2)
    surface_area                 Surface area, e.g. "(ha): 123.4 hectares"
    site_amenities               Free-text amenities list
"""

import csv
import json
import re
import sys
from pathlib import Path

from ats import ats_to_latlng, haversine_km


PROFILES_CSV = Path(__file__).parent.parent / "profiles" / "mywildalberta_profiles.csv"

# Flag any lake whose profile coordinate sits further than this from the ATS
# quarter-section the stocking report names for it. Beyond a couple of km the
# two sources are describing different places and one of them is wrong.
COORD_DISAGREEMENT_KM = 2.0


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
    """Pull a hectare figure out of the CSV's surface-area text.

    The column is free text and comes in several shapes:
        "(ha): 123.4 hectares"   "1,234 ha"   "13.2"   "n/a"   ""
    Returns None when there is no number to find.
    """
    if not s:
        return None
    text = s.replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1))
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
                "lat": parse_float(row.get("lat")),
                "lon": parse_float(row.get("lon")),
                "override_lat": parse_float(row.get("override_lat")),
                "override_lon": parse_float(row.get("override_lon")),
                "zone": (row.get("zone") or "").strip() or None,
                "surface_area_ha": parse_area_ha(row.get("surface_area")),
                "amenities": (row.get("site_amenities") or "").strip() or None,
            }
    return profiles


def resolve_coordinates(ats, prof):
    """Pick the best coordinate for a lake.

    Returns (lat, lon, source). Source is "override", "profile" or "ats".
    """
    if prof:
        if prof["override_lat"] is not None and prof["override_lon"] is not None:
            return prof["override_lat"], prof["override_lon"], "override"
        if prof["lat"] is not None and prof["lon"] is not None:
            return prof["lat"], prof["lon"], "profile"
    lat, lon = ats_to_latlng(ats)
    return lat, lon, "ats"


def merge(lakes_path):
    lakes_path = Path(lakes_path)
    lakes = json.loads(lakes_path.read_text(encoding="utf-8"))
    profiles = load_profiles()

    name_changes = 0
    by_source = {"override": 0, "profile": 0, "ats": 0}
    unmatched = []
    disagreements = []

    for lk in lakes:
        # A stable identifier for the physical lake. Today it equals the ATS
        # code; once years are linked it becomes the registry id and stops
        # changing when a report mistypes an ATS code.
        lk["lake_id"] = lk["ats"]

        prof = profiles.get(lk["ats"])
        if not prof:
            unmatched.append(lk)

        if prof and prof["display_name"] and prof["display_name"] != lk["name"]:
            lk["name"] = prof["display_name"]
            name_changes += 1

        lat, lon, source = resolve_coordinates(lk["ats"], prof)
        if lat is not None and lon is not None:
            lk["lat"], lk["lon"] = lat, lon
        lk["coord_source"] = source
        by_source[source] += 1

        # Cross-check the chosen coordinate against the ATS code in the report.
        ats_lat, ats_lon = ats_to_latlng(lk["ats"])
        if source != "ats" and ats_lat is not None:
            gap = haversine_km(lat, lon, ats_lat, ats_lon)
            lk["ats_gap_km"] = round(gap, 2)
            if gap > COORD_DISAGREEMENT_KM:
                disagreements.append((lk["name"], lk["ats"], gap))
        else:
            lk["ats_gap_km"] = None

        lk["zone"] = prof["zone"] if prof else None
        lk["surface_area_ha"] = prof["surface_area_ha"] if prof else None
        lk["amenities"] = prof["amenities"] if prof else None

    lakes_path.write_text(json.dumps(lakes, indent=2), encoding="utf-8")

    print(f"Merged {lakes_path.name}:")
    print(f"  Total lakes:     {len(lakes)}")
    print(f"  Names updated:   {name_changes}")
    print(f"  Coordinates:     {by_source['override']} override, "
          f"{by_source['profile']} profile, {by_source['ats']} ATS estimate")
    print(f"  Unmatched:       {len(unmatched)}")
    for lk in unmatched:
        print(f"    UNMATCHED: {lk['name']}  ({lk['ats']})")
    print(f"  Coordinate disagreements (>{COORD_DISAGREEMENT_KM} km from ATS code): "
          f"{len(disagreements)}")
    for name, ats, gap in sorted(disagreements, key=lambda x: -x[2]):
        print(f"    {gap:5.1f} km  {ats:<18} {name}")
    if disagreements:
        print("    Check these on satellite imagery. If the profile coordinate is")
        print("    right the report's ATS code is a typo; if not, set override_lat/")
        print("    override_lon in the profiles CSV and re-run.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python merge_profiles.py <path-to-lakes_YYYY.json>")
        sys.exit(1)
    merge(sys.argv[1])
