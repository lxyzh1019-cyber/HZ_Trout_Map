"""
check_consistency.py — scan all lakes_YYYY.json files and report mismatches
that could cause a single physical lake to show up as separate pins on the
map (or split its stocking history).

Checks:
  [1] Unmatched ATS codes — lakes in stocking data with no entry in
      profiles CSV (no zone/amenities).
  [2] Same ATS, different names across years — cosmetic, but worth
      standardizing so popups are consistent.
  [3] Same name, different ATS codes — could be two different lakes with
      the same name, OR a typo creating a phantom pin. Distance between
      coordinates helps tell them apart.
  [4] ATS code variants — same township-range-meridian but different
      section letter (NE vs NW etc). Usually a typo.

USAGE:
    python check_consistency.py
    python check_consistency.py --csv report.csv   # also write CSV

Run this after adding a new year's data, before committing.
"""

import csv
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path


DATA_DIR = Path(__file__).parent.parent / "data"
PROFILES_CSV = Path(__file__).parent.parent / "profiles" / "mywildalberta_profiles.csv"

ATS_RE = re.compile(r"^(?P<sec>NE|NW|SE|SW)(?P<rest>\d+-\d+-\d+-W[456])$")


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    to_rad = math.radians
    dlat = to_rad(lat2 - lat1)
    dlon = to_rad(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(to_rad(lat1)) * math.cos(to_rad(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def load_all_years():
    """Return dict year -> list of lakes."""
    by_year = {}
    for path in sorted(DATA_DIR.glob("lakes_*.json")):
        m = re.match(r"lakes_(\d{4})\.json", path.name)
        if not m:
            continue
        year = int(m.group(1))
        by_year[year] = json.loads(path.read_text(encoding="utf-8"))
    return by_year


def load_profile_ats():
    """Return set of ATS codes present in the profiles CSV."""
    ats = set()
    if not PROFILES_CSV.exists():
        return ats
    with open(PROFILES_CSV, newline="", encoding="cp1252") as f:
        for row in csv.DictReader(f):
            code = (row.get("ats") or "").strip()
            if code:
                ats.add(code)
    return ats


def normalize_name(name):
    """Lowercase, strip punctuation/parenthetical, for name-matching."""
    n = name.lower()
    n = re.sub(r"\(.*?\)", "", n)          # drop parentheticals
    n = re.sub(r"[^\w\s]", " ", n)         # punctuation -> space
    n = re.sub(r"\s+", " ", n).strip()
    return n


def run_checks(by_year, profile_ats):
    findings = {
        "unmatched": [],        # (year, ats, name)
        "name_mismatch": [],    # (ats, [(year, name), ...])
        "ats_mismatch": [],     # (norm_name, [(ats, year, lat, lon, name), ...], max_dist_km)
        "ats_variants": [],     # (rest_code, [(full_ats, year), ...])
    }

    # [1] Unmatched — any lake ATS not in profiles CSV
    seen_unmatched = set()
    for year, lakes in by_year.items():
        for lk in lakes:
            if lk["ats"] not in profile_ats and (year, lk["ats"]) not in seen_unmatched:
                findings["unmatched"].append((year, lk["ats"], lk["name"]))
                seen_unmatched.add((year, lk["ats"]))

    # [2] Same ATS -> different names across years
    names_by_ats = defaultdict(list)   # ats -> [(year, name), ...]
    for year, lakes in by_year.items():
        for lk in lakes:
            names_by_ats[lk["ats"]].append((year, lk["name"]))
    for ats, entries in names_by_ats.items():
        distinct_names = sorted({name for _, name in entries})
        if len(distinct_names) > 1:
            findings["name_mismatch"].append((ats, sorted(entries)))

    # [3] Same normalized name -> different ATS codes
    ats_by_name = defaultdict(set)     # norm_name -> set of (ats, year, lat, lon, raw_name)
    for year, lakes in by_year.items():
        for lk in lakes:
            ats_by_name[normalize_name(lk["name"])].add(
                (lk["ats"], year, lk["lat"], lk["lon"], lk["name"])
            )
    for norm_name, entries in ats_by_name.items():
        distinct_ats = {e[0] for e in entries}
        if len(distinct_ats) > 1:
            # compute max pairwise distance between coords
            coords = [(e[2], e[3]) for e in entries]
            max_dist = 0.0
            for i in range(len(coords)):
                for j in range(i + 1, len(coords)):
                    d = haversine_km(coords[i][0], coords[i][1],
                                     coords[j][0], coords[j][1])
                    if d > max_dist:
                        max_dist = d
            findings["ats_mismatch"].append(
                (norm_name, sorted(entries), max_dist)
            )

    # [4] ATS variants — same rest, different section prefix
    variants = defaultdict(set)        # rest_code -> set of (full_ats, year)
    for year, lakes in by_year.items():
        for lk in lakes:
            m = ATS_RE.match(lk["ats"])
            if m:
                variants[m.group("rest")].add((lk["ats"], year))
    for rest, pairs in variants.items():
        distinct_full = {p[0] for p in pairs}
        if len(distinct_full) > 1:
            findings["ats_variants"].append((rest, sorted(pairs)))

    return findings


def print_report(findings):
    print("=" * 70)
    print("Consistency Report")
    print("=" * 70)

    print(f"\n[1] Unmatched ATS codes (not in profiles CSV): {len(findings['unmatched'])}")
    for year, ats, name in findings["unmatched"]:
        print(f"    {year}  {ats:<20}  {name}")

    print(f"\n[2] Same ATS, different names across years: {len(findings['name_mismatch'])}")
    for ats, entries in findings["name_mismatch"]:
        print(f"    {ats}")
        for year, name in entries:
            print(f"      {year}: {name}")

    print(f"\n[3] Same name, different ATS codes: {len(findings['ats_mismatch'])}")
    for norm_name, entries, max_dist in findings["ats_mismatch"]:
        raw_names = {e[4] for e in entries}
        all_have_parens = all("(" in n for n in raw_names)
        if all_have_parens and len(raw_names) == len(entries):
            hint = "probably intentional (different names in parentheticals)"
        elif max_dist < 20:
            hint = "likely typo"
        else:
            hint = "likely different lakes"
        print(f"    '{norm_name}'  (max {max_dist:.1f} km apart — {hint})")
        for ats, year, lat, lon, raw_name in entries:
            print(f"      {ats:<20}  {year}  ({lat:.4f}, {lon:.4f})  {raw_name}")

    print(f"\n[4] ATS section-letter variants (same township-range): {len(findings['ats_variants'])}")
    for rest, pairs in findings["ats_variants"]:
        print(f"    *-{rest}")
        for full_ats, year in pairs:
            print(f"      {full_ats}  ({year})")

    print()


def write_csv_report(findings, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category", "key", "detail"])
        for year, ats, name in findings["unmatched"]:
            w.writerow(["unmatched", f"{year} / {ats}", name])
        for ats, entries in findings["name_mismatch"]:
            for year, name in entries:
                w.writerow(["name_mismatch", ats, f"{year}: {name}"])
        for norm_name, entries, max_dist in findings["ats_mismatch"]:
            for ats, year, lat, lon, raw_name in entries:
                w.writerow([
                    "ats_mismatch",
                    norm_name,
                    f"{ats} | {year} | {lat},{lon} | {raw_name} | max_dist={max_dist:.1f}km",
                ])
        for rest, pairs in findings["ats_variants"]:
            for full_ats, year in pairs:
                w.writerow(["ats_variant", rest, f"{full_ats} ({year})"])
    print(f"CSV written to {path}")


if __name__ == "__main__":
    by_year = load_all_years()
    if not by_year:
        print(f"No lakes_*.json files found in {DATA_DIR}")
        sys.exit(1)
    print(f"Loaded years: {sorted(by_year)}")

    profile_ats = load_profile_ats()
    print(f"Profiles CSV: {len(profile_ats)} ATS codes")

    findings = run_checks(by_year, profile_ats)
    print_report(findings)

    if "--csv" in sys.argv:
        idx = sys.argv.index("--csv")
        out = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "consistency_report.csv"
        write_csv_report(findings, out)
