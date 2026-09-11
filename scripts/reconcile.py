"""Compare what Alberta publishes against what this repository holds.

    python3 reconcile.py            # report, and write the review file
    python3 reconcile.py --apply    # also fill blanks the repo simply lacks

Three questions, answered separately because they deserve different treatment:

  FILL      the repo has nothing and Alberta publishes something. Zone is the
            big one — 87 lakes carry no zone, and a lake with no zone gets no
            catch limits at all, so this single field is worth more to the map
            than anything else on the page.

  CONFIRM   both agree. Worth counting rather than ignoring: agreement across a
            few hundred lakes is the evidence that the join is sound, and it is
            the only check this repo has on coordinates it derived from land
            descriptions.

  DISAGREE  both have a value and they differ. Never resolved automatically.
            Alberta is the authority on its own lakes, but this repo's values
            came from its own sources for reasons, and quietly overwriting them
            would erase work that was done deliberately. These go to a review
            file for a person.

--apply only ever fills blanks. It cannot change a value that already exists.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SITE_CSV = ROOT / "data" / "raw" / "mywildalberta_lakes.csv"
REGISTRY = ROOT / "data" / "lake_registry.json"
REVIEW = ROOT / "data" / "lake_facts_review.csv"

# What to compare, and how close counts as agreement. Depth has no repo value
# to compare against, so it is fill-only.
COMPARE = [
    ("zone", "zone", None),
    ("surface_area_ha", "surface_area_ha", 0.10),   # within 10%
    ("max_depth_m", None, None),                     # nothing to compare to yet
]


def load_site():
    if not SITE_CSV.exists():
        return None
    with SITE_CSV.open(newline="", encoding="utf-8") as handle:
        return {(row.get("waterbody_id") or "").strip(): row
                for row in csv.DictReader(handle) if row.get("waterbody_id")}


def number(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def close_enough(a, b, tolerance):
    a, b = number(a), number(b)
    if a is None or b is None:
        return None
    if tolerance is None:
        return a == b
    if max(abs(a), abs(b)) == 0:
        return True
    return abs(a - b) / max(abs(a), abs(b)) <= tolerance


def compare(lakes, site):
    fills, confirms, disagreements = [], [], []
    for lake in lakes:
        wid = str(lake.get("waterbody_id") or "")
        row = site.get(wid)
        if not row:
            continue
        for site_field, repo_field, tolerance in COMPARE:
            published = (row.get(site_field) or "").strip()
            if not published:
                continue
            held = "" if not repo_field else str(lake.get(repo_field) or "").strip()
            held = "" if held in ("None", "") else held
            record = {"lake_id": lake.get("lake_id", ""), "waterbody_id": wid,
                      "lake": lake.get("name", ""), "field": site_field,
                      "repo_value": held, "alberta_value": published}
            if not held:
                fills.append(record)
            elif tolerance is None and held.strip().lower() == published.strip().lower():
                confirms.append(record)
            elif close_enough(held, published, tolerance):
                confirms.append(record)
            else:
                disagreements.append(record)
    return fills, confirms, disagreements


def sample(rows, n=6):
    return rows[:n]


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="fill blanks in the registry (never overwrites)")
    args = parser.parse_args()

    site = load_site()
    if site is None:
        print(f"No {SITE_CSV.relative_to(ROOT)}.")
        print("Collect it first:  python3 fetch_lake_pages.py --probe")
        print("                   python3 fetch_lake_pages.py")
        return 1

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    lakes = registry["lakes"] if isinstance(registry, dict) and "lakes" in registry else registry
    fills, confirms, disagreements = compare(lakes, site)

    print(f"{len(site)} lake(s) collected from Alberta, {len(lakes)} in the registry\n")
    print(f"  FILL      {len(fills):>4}  the repo has nothing and Alberta publishes a value")
    print(f"  CONFIRM   {len(confirms):>4}  both agree")
    print(f"  DISAGREE  {len(disagreements):>4}  both have a value and they differ")

    for title, rows in (("FILL", fills), ("DISAGREE", disagreements)):
        if not rows:
            continue
        print(f"\n{title}, a sample:")
        for row in sample(rows):
            held = row["repo_value"] or "—"
            print(f"  {row['lake'][:32]:<34} {row['field']:<16} "
                  f"repo {held:<12} alberta {row['alberta_value'][:24]}")

    by_field = {}
    for row in fills:
        by_field[row["field"]] = by_field.get(row["field"], 0) + 1
    if by_field:
        print("\nwhat could be filled, by field:")
        for field, count in sorted(by_field.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>4}  {field}")

    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "verdict", "lake", "lake_id", "waterbody_id", "field",
            "repo_value", "alberta_value"])
        writer.writeheader()
        for verdict, rows in (("disagree", disagreements), ("fill", fills)):
            for row in sorted(rows, key=lambda r: (r["field"], r["lake"])):
                writer.writerow({"verdict": verdict, **row})
    print(f"\nwrote {REVIEW.relative_to(ROOT)} "
          f"({len(disagreements)} to settle, {len(fills)} fillable)")

    if args.apply:
        index = {str(l.get("waterbody_id") or ""): l for l in lakes}
        applied = 0
        for row in fills:
            lake = index.get(row["waterbody_id"])
            field = row["field"]
            if not lake or field not in ("zone", "surface_area_ha"):
                continue
            if lake.get(field) in (None, "", "None"):
                lake[field] = (number(row["alberta_value"])
                               if field.endswith("_ha") else row["alberta_value"])
                applied += 1
        REGISTRY.write_text(json.dumps(registry, indent=1, ensure_ascii=False,
                                       sort_keys=True) + "\n", encoding="utf-8")
        print(f"filled {applied} blank field(s) in the registry — nothing was overwritten")
        print("Now rebuild:  python3 build_history.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
