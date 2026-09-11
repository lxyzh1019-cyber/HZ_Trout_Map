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
import math
import re
import sys
from pathlib import Path

from registry import name_similarity

ROOT = Path(__file__).parent.parent
SITE_CSV = ROOT / "data" / "raw" / "mywildalberta_lakes.csv"
REGISTRY = ROOT / "data" / "lake_registry.json"
REVIEW = ROOT / "data" / "lake_facts_review.csv"
FACTS = ROOT / "data" / "lake_facts.csv"

# Fields the registry actually carries. Depth and the stocking years are read
# straight from the collected CSV by depth.py, so recording them here would
# copy a value the pipeline already has from its own source.
APPLICABLE = {"position", "legal_land_description", "zone", "surface_area_ha",
              "published_waterbody_id"}

# How alike two names must be before a land description is allowed to join a
# lake to a published waterbody. The eight that qualify score 0.95 and above.
PUBLISHED_ID_NAME_FLOOR = 0.6

# What to compare, and how close counts as agreement. A field with no repo
# counterpart is fill-only: there is nothing to disagree with.
COMPARE = [
    ("zone", "zone", None),
    ("surface_area_ha", "surface_area_ha", 0.10),   # within 10%
    ("max_depth_m", None, None),                     # nothing to compare to yet
    ("average_length_cm", None, None),
    ("stocked_years", None, None),
]

# The land description and the coordinates are the two independent checks on a
# position this repo largely derived from land descriptions itself, so they get
# their own comparators rather than a string match.
#
# A quarter section is about 800 m on a side, so a point anywhere inside one can
# sit ~570 m from its centre; a large lake's centroid and Alberta's own
# reference point for it can differ by more again. A kilometre therefore still
# means "the same lake, described from a different point", while a genuinely
# wrong match lands tens of kilometres out. The distance is written into the
# review file either way, so nobody has to take the threshold on trust.
POSITION_TOLERANCE_M = 1000.0
EARTH_RADIUS_M = 6371008.8


def metres_apart(lat1, lon1, lat2, lon2):
    """Great-circle distance. Flat-earth would do at these separations, but this
    costs four trig calls and cannot be wrong near a meridian."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def normalise_ats(text):
    """SW 13-52-2-W5 and SW13-52-2-W5 are the same quarter section.

    Alberta prints the space, this repo stores it closed up, and comparing the
    two as written would report every single lake as a disagreement.
    """
    return re.sub(r"[^A-Z0-9-]", "", str(text or "").upper())


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


def land_description(lake, row, base):
    """Alberta's quarter section against the repo's, as a verdict or nothing.

    A lake can legitimately touch several quarter sections and the repo stores a
    list, so a published description matching ANY held code is agreement. Only a
    description matching none of them is a disagreement worth a person's time.
    """
    published = str(row.get("legal_land_description") or "").strip()
    if not published:
        return None
    held = [c for c in (lake.get("ats_codes") or []) if c]
    record = dict(base, field="legal_land_description",
                  repo_value=" ".join(str(c) for c in held),
                  alberta_value=published, note="")
    if not held:
        return "fill", record
    wanted = normalise_ats(published)
    if any(normalise_ats(code) == wanted for code in held):
        return "confirm", record
    record["note"] = "matches none of the quarter sections held"
    return "disagree", record


def position(lake, row, base):
    """Alberta's coordinates against the repo's, as a distance.

    This is the check the repo could not previously make: most of its
    coordinates were derived from land descriptions, and a derivation has no way
    to catch its own arithmetic error. An independently published pair does.
    """
    lat, lon = number(row.get("latitude")), number(row.get("longitude"))
    if lat is None or lon is None:
        return None
    held_lat, held_lon = number(lake.get("lat")), number(lake.get("lon"))
    record = dict(base, field="position",
                  repo_value=("" if held_lat is None or held_lon is None
                              else f"{held_lat:.5f},{held_lon:.5f}"),
                  alberta_value=f"{lat:.5f},{lon:.5f}", note="")
    if not record["repo_value"]:
        return "fill", record
    apart = metres_apart(held_lat, held_lon, lat, lon)
    record["note"] = f"{apart:.0f} m apart"
    return ("confirm" if apart <= POSITION_TOLERANCE_M else "disagree"), record


def compare(lakes, site):
    fills, confirms, disagreements = [], [], []
    bucket = {"fill": fills, "confirm": confirms, "disagree": disagreements}
    for lake in lakes:
        wid = str(lake.get("waterbody_id") or "")
        row = site.get(wid)
        if not row:
            continue
        base = {"lake_id": lake.get("lake_id", ""), "waterbody_id": wid,
                "lake": lake.get("name", "")}
        for site_field, repo_field, tolerance in COMPARE:
            published = str(row.get(site_field) or "").strip()
            if not published:
                continue
            held = "" if not repo_field else str(lake.get(repo_field) or "").strip()
            held = "" if held in ("None", "") else held
            record = dict(base, field=site_field, repo_value=held,
                          alberta_value=published, note="")
            if not held:
                fills.append(record)
            elif tolerance is None and held.strip().lower() == published.strip().lower():
                confirms.append(record)
            elif close_enough(held, published, tolerance):
                confirms.append(record)
            else:
                disagreements.append(record)
        for verdict in (land_description(lake, row, base), position(lake, row, base)):
            if verdict:
                bucket[verdict[0]].append(verdict[1])
    return fills, confirms, disagreements


def sample(rows, n=6):
    return rows[:n]


def propose_published_ids(lakes, site):
    """Alberta's own id for lakes the repo minted from a land description.

    Thirteen lakes were minted from reports that print no waterbody id, so the
    id join every other part of this pipeline relies on cannot see them — which
    is also why they get no depth. The stocking map publishes ids for eight of
    them.

    The join is the land description, and it is only allowed when the code
    identifies exactly one lake on EACH side. Seven of the registry's codes are
    shared by two lakes and five of the map's are, so a code that is not unique
    both ways proves nothing. A name check on top of that is what makes it
    evidence rather than a coincidence of geometry: all eight score 0.95 or
    better against the name the map itself uses.

    Watridge Lake is the reason the name check is not optional. Its published
    position is 140 km from this very land description, and the importer
    already refuses it; the land description and the name still agree.
    """
    ours, theirs = {}, {}
    for lake in lakes:
        for code in lake.get("ats_codes") or []:
            ours.setdefault(normalise_ats(code), []).append(lake)
    for row in site.values():
        code = row.get("legal_land_description")
        if code:
            theirs.setdefault(normalise_ats(code), []).append(row)
    taken = {str(l.get("waterbody_id") or "") for l in lakes if l.get("waterbody_id")}

    proposals = []
    for lake in lakes:
        if lake.get("waterbody_id"):
            continue
        for code in lake.get("ats_codes") or []:
            key = normalise_ats(code)
            if len(ours.get(key, [])) != 1 or len(theirs.get(key, [])) != 1:
                continue
            row = theirs[key][0]
            if row["waterbody_id"] in taken:
                continue
            published = row.get("page_name") or ""
            score = name_similarity(lake["name"], published)
            if score < PUBLISHED_ID_NAME_FLOOR:
                continue
            proposals.append({
                "lake": lake["name"], "lake_id": lake["lake_id"],
                "waterbody_id": row["waterbody_id"],
                "field": "published_waterbody_id",
                "repo_value": "", "alberta_value": row["waterbody_id"],
                "note": f"{key} identifies one lake on each side; "
                        f"the map calls it {published!r} ({score:.2f})"})
            break
    return proposals


def existing_facts():
    if not FACTS.exists():
        return []
    with FACTS.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_facts(lakes, fills):
    """Record the answers where a rebuild will find them.

    They used to be written straight into data/lake_registry.json, and the
    rebuild this prints on the next line regenerates that file from the reports
    and overwrites every one of them. Nothing noticed, because reconcile.py had
    no input until the stocking map was imported, so --apply had never run.

    The registry is a build artefact. The durable inputs are data/raw/, the
    profiles CSV and data/lake_aliases.csv, and this is the fourth: the same
    shape as lake_aliases.csv, which holds your answers to past linking
    questions, for your answers to past attribute questions.
    """
    by_waterbody = {str(l.get("waterbody_id") or ""): l for l in lakes if l.get("waterbody_id")}
    by_lake_id = {l["lake_id"]: l for l in lakes}
    rows = existing_facts()
    seen = {(r["lake_id"], r["field"]) for r in rows}
    added = 0
    for row in fills:
        # A published-id proposal names the lake it is for, because the lake it
        # is for is precisely the one with no waterbody id to look it up by.
        lake = by_lake_id.get(row.get("lake_id") or "") or by_waterbody.get(row["waterbody_id"])
        field = row["field"]
        if not lake or field not in APPLICABLE:
            continue
        # Blanks only. A value the repo already holds is a disagreement for a
        # person to settle, never something this fills in silently.
        if field == "position":
            if lake.get("lat") is not None:
                continue
        elif field == "legal_land_description":
            if lake.get("ats_codes"):
                continue
        elif field == "published_waterbody_id":
            if lake.get("waterbody_id") or lake.get("published_waterbody_id"):
                continue
        elif lake.get(field) not in (None, "", "None"):
            continue
        if (lake["lake_id"], field) in seen:
            continue
        rows.append({"lake_id": lake["lake_id"], "field": field,
                     "value": row["alberta_value"],
                     "note": f"{row['lake']} — {row['note'] or 'Alberta publishes it, the repo had nothing'}"})
        seen.add((lake["lake_id"], field))
        added += 1
    with FACTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["lake_id", "field", "value", "note"],
                                lineterminator="\n")
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["lake_id"], r["field"])):
            writer.writerow(row)
    return added


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
    # Lakes minted from a land description carry no waterbody id, so
    # compare() cannot see them at all. These are proposals, not facts.
    fills.extend(propose_published_ids(lakes, site))

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
            print(f"  {row['lake'][:32]:<34} {row['field']:<22} "
                  f"repo {held[:22]:<24} alberta {row['alberta_value'][:22]:<24}"
                  f"{row.get('note', '')}")

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
            "repo_value", "alberta_value", "note"])
        writer.writeheader()
        for verdict, rows in (("disagree", disagreements), ("fill", fills)):
            for row in sorted(rows, key=lambda r: (r["field"], r["lake"])):
                writer.writerow({"verdict": verdict, **row})
    print(f"\nwrote {REVIEW.relative_to(ROOT)} "
          f"({len(disagreements)} to settle, {len(fills)} fillable)")

    if args.apply:
        applied = write_facts(lakes, fills)
        print(f"\nrecorded {applied} answer(s) in {FACTS.relative_to(ROOT)} "
              f"— blanks only, nothing was overwritten")
        print("Now rebuild:  python3 build_history.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
