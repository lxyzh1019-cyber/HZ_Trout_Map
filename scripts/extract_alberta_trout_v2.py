"""
Alberta Trout Stocking Report — PDF Extraction & Geocoding (v2)
================================================================
Extracts trout stocking data from Alberta Environment PDF reports and
geocodes ATS (Alberta Township System) codes to lat/lng coordinates.

USAGE:
    pip install pdfplumber
    python extract_alberta_trout_v2.py <path-to-pdf> [year]

OUTPUT:
    lakes_<year>.json      — aggregated by lake with full stocking history
    trout_<year>.json      — flat list of every stocking event

Changes from v1:
    1. ATS longitude math fixed. v1 treated each range increment as 1 mile;
       it's actually 6 miles. Longitude errors of 20–60 km (for lakes far
       from the W5 meridian) are eliminated; residual error is the inherent
       quarter-section tolerance (~2–8 km).
    2. Name parsing uses word x-coordinates to separate Official Name and
       Common Name columns, instead of concatenating everything before the
       ATS code. No more "Payne Lake Mami Lake" garbage.
    3. Name resolution rule:
         - If Official == "Unnamed" → use Common
         - If Common is blank → use Official
         - Otherwise → "Official (Common)"
    4. Walleye (WALL) rows are parsed but filtered out of trout output.
"""

import pdfplumber
import json
import re
import math
import sys
from pathlib import Path

TROUT_SPECIES = {"RNTR", "BKTR", "BNTR", "TGTR", "CTTR"}

# Column x-coordinate boundaries (derived from inspecting the PDF word layout).
# Any word's x0 places it into one column. These are inclusive-lower, exclusive-upper.
COL_BOUNDS = {
    "official":  (50,  156),
    "common":    (156, 245),
    "ats":       (245, 341),
    "species":   (341, 390),
    "strain":    (390, 480),
    "genotype":  (480, 525),
    "length":    (525, 565),
    "number":    (565, 635),
    "date":      (635, 9999),
}

ATS_RE = re.compile(r"^(?:NE|NW|SE|SW)\d+-\d+-\d+-W[456]$")
DATE_RE = re.compile(r"^\d+-[A-Z][a-z]+-\d+$")
SPECIES_RE = re.compile(r"^(RNTR|BKTR|BNTR|TGTR|CTTR|WALL)$")
GENOTYPE_RE = re.compile(r"^(AF2N|AF3N|2N|3N)$")


def classify_col(x0):
    for col, (lo, hi) in COL_BOUNDS.items():
        if lo <= x0 < hi:
            return col
    return None


def extract_rows_from_page(page):
    """
    Yield dicts per data row on this page. Each dict has:
      official, common, ats, species, strain, genotype, length, number, date
    Values are strings (empty if missing).
    Handles word-wrap in the Official/Common columns: if a row has only
    Official/Common words and no ATS, it's a wrap continuation and its words
    are appended to the most recent row's corresponding column.
    """
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    # Filter out page furniture: header is above y=18, footer below y=555
    words = [w for w in words if 18 < w["top"] < 555]
    # Bucket words by y-coordinate (round to nearest 2 pixels — rows are ~12 apart)
    y_buckets = {}
    for w in words:
        y = round(w["top"] / 2) * 2
        y_buckets.setdefault(y, []).append(w)

    rows_out = []
    last_anchor_y = None  # y of the most recent ATS-anchored row
    for y in sorted(y_buckets.keys()):
        row_words = sorted(y_buckets[y], key=lambda w: w["x0"])
        cols = {k: [] for k in COL_BOUNDS}
        for w in row_words:
            col = classify_col(w["x0"])
            if col:
                cols[col].append(w["text"])
        joined = {k: " ".join(v).strip() for k, v in cols.items()}

        # Stop sentinel: the last page has a "Total Trout Stocked ..." summary block
        # that sits after the real data. Any row whose first official-column word
        # is "Total" terminates processing for this page.
        if joined["official"].startswith("Total "):
            break

        # Is this a real data row (has ATS code) or a wrap continuation?
        if ATS_RE.match(joined["ats"]):
            rows_out.append(joined)
            last_anchor_y = y
        else:
            # Wrap continuation must be close to its anchor (legit wraps are ~10–12px below).
            # A big gap means this "row" is actually page furniture or a legend.
            if rows_out and (joined["official"] or joined["common"]) \
               and last_anchor_y is not None and (y - last_anchor_y) <= 20:
                last = rows_out[-1]
                if joined["official"]:
                    last["official"] = (last["official"] + " " + joined["official"]).strip()
                if joined["common"]:
                    last["common"] = (last["common"] + " " + joined["common"]).strip()
            # Otherwise it's header text or page furniture — ignore

    return rows_out


def resolve_lake_name(official, common):
    """
    Produce one canonical lake name from the two PDF columns.
      - Unnamed + Common   → Common
      - Official + ""      → Official
      - Official + Common  → "Official (Common)"
    """
    o = official.strip()
    c = common.strip()
    if o == "Unnamed":
        return c if c else o
    if not c:
        return o
    # Both present and non-Unnamed
    if o == c:
        return o
    return f"{o} ({c})"


# ═══════════════════════════════════════════════════════
# ATS → Lat/Lng conversion (fixed in v2)
# ═══════════════════════════════════════════════════════
# Alberta Township System:
#   Quarter-Section-Township-Range-Meridian (e.g., SW4-36-8-W5)
#   - Meridians: W4 = 110°W, W5 = 114°W, W6 = 118°W
#   - Townships: 6 miles N/S, numbered from 49°N (US border) going north
#   - Ranges: 6 miles E/W, numbered from each meridian going west
#   - Sections: 6×6 grid (36 per township) in boustrophedon (snake) order
#   - Quarters: NE/NW/SE/SW of each 1-mile section
# Accuracy: ~2–8 km (returns approx centroid of quarter-section)

MERIDIAN_LON = {"W4": -110.0, "W5": -114.0, "W6": -118.0}
MILES_PER_DEG_LAT = 69.0

QUARTER_OFFSETS = {
    "NE": (0.75, 0.75), "NW": (0.25, 0.75),
    "SE": (0.75, 0.25), "SW": (0.25, 0.25),
}


def section_offset(section):
    """(col, row) 0-5 for section within 6x6 township grid (snake ordering)."""
    s = section - 1
    row = s // 6
    pos_in_row = s % 6
    col = 5 - pos_in_row if row % 2 == 0 else pos_in_row
    return col, row


def ats_to_latlng(ats):
    m = re.match(r"^(NE|NW|SE|SW)(\d+)-(\d+)-(\d+)-(W[456])$", ats)
    if not m:
        return None, None
    quarter, section, township, rng, meridian = m.groups()
    section, township, rng = int(section), int(township), int(rng)
    # Township south edge: 6 mi × (township - 1) north of 49°N
    township_south_lat = 49.0 + (township - 1) * (6.0 / MILES_PER_DEG_LAT)
    col, row = section_offset(section)       # miles 0–5 within township
    qcol, qrow = QUARTER_OFFSETS[quarter]    # 0.25 or 0.75 mile
    lat = township_south_lat + (row + qrow) * (1.0 / MILES_PER_DEG_LAT)
    miles_per_deg_lon = MILES_PER_DEG_LAT * math.cos(math.radians(lat))
    # FIX: each range is 6 miles wide; col/qcol are miles within the range
    miles_west_of_meridian = (rng - 1) * 6.0 + col + qcol
    lon = MERIDIAN_LON[meridian] - miles_west_of_meridian / miles_per_deg_lon
    return round(lat, 5), round(lon, 5)


# ═══════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════
def extract_all_rows(pdf_path, year):
    """Extract every stocking row from the PDF (trout + walleye)."""
    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            if page_num == 0:
                continue  # skip cover
            raw = extract_rows_from_page(page)
            for r in raw:
                # Validate required fields
                if not SPECIES_RE.match(r["species"]):
                    continue
                if not GENOTYPE_RE.match(r["genotype"]):
                    continue
                if not DATE_RE.match(r["date"]):
                    continue
                try:
                    length = float(r["length"])
                    number = int(r["number"].replace(",", ""))
                except ValueError:
                    continue
                name = resolve_lake_name(r["official"], r["common"])
                lat, lon = ats_to_latlng(r["ats"])
                all_rows.append({
                    "ats": r["ats"],
                    "lake_name": name,
                    "species": r["species"],
                    "strain": r["strain"],
                    "genotype": r["genotype"],
                    "length_cm": length,
                    "number": number,
                    "date": r["date"],
                    "year": year,
                    "lat": lat,
                    "lon": lon,
                })
    return all_rows


def aggregate_lakes(events):
    """Group events into one record per ATS (a lake), keeping full stocking history."""
    lakes = {}
    for r in events:
        key = r["ats"]
        if key not in lakes:
            lakes[key] = {
                "ats": r["ats"],
                "name": r["lake_name"],
                "lat": r["lat"],
                "lon": r["lon"],
                "stockings": [],
            }
        lakes[key]["stockings"].append({
            "species": r["species"],
            "strain": r["strain"],
            "genotype": r["genotype"],
            "length_cm": r["length_cm"],
            "number": r["number"],
            "date": r["date"],
            "year": r["year"],
        })
    lake_list = list(lakes.values())
    for lk in lake_list:
        lk["total_fish"] = sum(s["number"] for s in lk["stockings"])
        lk["species_set"] = sorted({s["species"] for s in lk["stockings"]})
    lake_list.sort(key=lambda x: -x["total_fish"])
    return lake_list


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_alberta_trout_v2.py <pdf_path> [year]")
        sys.exit(1)
    pdf_path = sys.argv[1]
    year = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
    out_dir = Path.cwd()

    print(f"Extracting from {pdf_path} (year={year})...")
    all_events = extract_all_rows(pdf_path, year)
    trout_events = [r for r in all_events if r["species"] in TROUT_SPECIES]
    walleye_events = [r for r in all_events if r["species"] == "WALL"]

    trout_lakes = aggregate_lakes(trout_events)
    walleye_lakes = aggregate_lakes(walleye_events)

    # Species breakdown
    counts = {}
    for r in trout_events:
        counts[r["species"]] = counts.get(r["species"], 0) + 1

    print(f"\n✓ Trout stocking events:     {len(trout_events)}")
    print(f"✓ Unique trout lakes:        {len(trout_lakes)}")
    print(f"✓ Trout species breakdown:   {counts}")
    print(f"✓ Walleye events (excluded): {len(walleye_events)} in {len(walleye_lakes)} lakes")
    print(f"\nTop 10 trout lakes by total fish:")
    for lk in trout_lakes[:10]:
        print(f"  {lk['name']:<45} | {lk['total_fish']:>7,} | {','.join(lk['species_set']):<20} | ({lk['lat']}, {lk['lon']})")

    trout_file = out_dir / f"trout_{year}.json"
    lakes_file = out_dir / f"lakes_{year}.json"
    with open(trout_file, "w") as f:
        json.dump(trout_events, f, indent=2)
    with open(lakes_file, "w") as f:
        json.dump(trout_lakes, f, indent=2)
    print(f"\nWrote {trout_file}")
    print(f"Wrote {lakes_file}")


if __name__ == "__main__":
    main()
