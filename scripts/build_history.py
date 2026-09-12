"""
build_history.py — turn sixteen years of stocking reports into one linked
history, keyed by a stable lake identity.

    python3 build_history.py              # build everything
    python3 build_history.py --years 2011 2012
    python3 build_history.py --report     # summary only, write nothing

What it writes
--------------
    data/lake_registry.json   one entry per physical lake, with every name and
                              land description that lake has ever been given
    data/lakes_YYYY.json      one file per year, as the map already expects
    data/manifest.json        the year list, marking provisional seasons
    data/link_review.csv      rows the rules would not guess at — your answers
                              go back in as aliases

How the review loop works
-------------------------
1. Run this. Anything unresolved lands in data/link_review.csv.
2. Open it. Each row shows the report's name, its land description, and the
   candidate lakes with distances. Put the right lake_id in the `lake_id`
   column, or `NEW` if it is genuinely a lake we have never seen.
3. Run `python3 apply_review.py`. Your answers become permanent aliases.
4. Run this again. Those rows now resolve by themselves, forever.
"""

import argparse
import csv
import json
import sys
from collections import defaultdict

import sources
from ats import ats_to_latlng, haversine_km
from registry import (ALIASES_PATH, DATA_DIR, FACTS_PATH, REVIEW_PATH, Registry, display_name,
                      best_matching_name, discriminating_conflict,
                      load_aliases, load_profiles, name_similarity, normalise_code,
                      normalize_name, shared_land_descriptions,
                      save_registry, _title)

TROUT = sources.TROUT_SPECIES


def build_spine(rows_by_year):
    """Seed the registry from the years Alberta published its own waterbody id.

    Those eight years (2012-2019) are the backbone: the id is stable, it comes
    with coordinates, and it tells us which differing land descriptions and
    names belong to the same lake.
    """
    reg = Registry()
    groups = defaultdict(list)
    for year in sorted(rows_by_year):
        for row in rows_by_year[year]:
            if row["waterbody_id"]:
                groups[row["waterbody_id"]].append(row)

    for wb, rows in sorted(groups.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        names = [display_name(r["official_name"], r["common_name"]) for r in rows]
        names = [n for n in names if n]
        # Prefer the fullest name seen; it usually carries the common name too.
        canonical = _title(max(names, key=len)) if names else f"Waterbody {wb}"
        coords = [(r["lat"], r["lon"]) for r in rows if r["lat"] is not None]
        lat, lon = (coords[-1] if coords else (None, None))
        lake = reg.add_lake(
            lake_id=f"wb{wb}", name=canonical, lat=lat, lon=lon, waterbody_id=wb,
            ats_codes={r["ats"] for r in rows if r["ats"]},
            aliases=set(names))
        lake["name_variants"] = sorted({_title(n) for n in names})
    reg.reindex()
    return reg


def apply_facts(reg):
    """Your answers to past attribute questions, from data/lake_facts.csv.

    reconcile.py compares the repo against what Alberta publishes and writes
    the answers here, because the registry is regenerated from the reports on
    every build and anything written into it directly is gone by the next run.
    This is the same arrangement as data/lake_aliases.csv, which holds the
    answers to past linking questions.

    Three kinds of answer, in the decision column:

      fill     what reconcile.py --apply records: Alberta publishes a value and
               the repo had none. Applied only while the repo still has none, so
               a value the pipeline later derives for itself is never replaced.

      settled  a person compared two sources that disagreed and picked one.
               This wins, because a disagreement is exactly the case a blanks-
               only rule cannot resolve and a person just did.

      keep     a person compared them and kept what the repo already had. No
               value is written; the row exists so reconcile.py stops raising a
               question that has been answered.

    Only a person writes settled or keep. --apply emits fill and nothing else,
    so nothing here can start overriding the pipeline on its own.
    """
    if not FACTS_PATH.exists():
        return 0
    by_id = {lake["lake_id"]: lake for lake in reg.lakes}
    applied = 0
    with FACTS_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            lake = by_id.get(row["lake_id"])
            field, value = row["field"], row["value"]
            decision = (row.get("decision") or "fill").strip()
            if not lake or decision == "keep":
                continue
            if not value:
                continue
            settled = decision == "settled"
            if field == "position":
                if settled or lake.get("lat") is None:
                    lat, lon = value.split(",")
                    lake["lat"], lake["lon"] = float(lat), float(lon)
                    lake["coord_source"] = "mywildalberta"
                    applied += 1
            elif field == "legal_land_description":
                if settled or not lake["ats_codes"]:
                    lake["ats_codes"] = [normalise_code(value)]
                    applied += 1
            elif field == "surface_area_ha":
                if settled or lake.get(field) is None:
                    lake[field] = float(value)
                    applied += 1
            elif field == "zone":
                if settled or lake.get(field) is None:
                    lake[field] = value
                    applied += 1
            elif field == "published_waterbody_id":
                # Deliberately NOT waterbody_id, and not a rename. lake_id is
                # minted as "wb" + the waterbody id where one exists, so
                # setting the field would either contradict the id or force
                # lk0006 to become wb417506 — which breaks the ?lake= links
                # people have bookmarked and every answer already recorded
                # against the old id. This is a join key and nothing more.
                if not lake.get("waterbody_id") and not lake.get("published_waterbody_id"):
                    lake["published_waterbody_id"] = value
                    applied += 1
    if applied:
        reg.reindex()
    return applied


def attach_profiles(reg):
    """Add zone, amenities and the hand-verified coordinates from the profiles CSV."""
    profiles = load_profiles()
    matched = 0
    # Alberta gives Upper and Lower Champion Lake the same land description, so
    # a profile row can match two different lakes. Letting both take the
    # profile's name leaves two lakes called "Champion Lakes (Lower)". Claim
    # each profile row once, for the lake whose own name fits it best.
    claimants = defaultdict(list)
    for lake in reg.lakes:
        for code in lake["ats_codes"]:
            if code in profiles:
                claimants[code].append(lake)
                break

    for code, lakes in claimants.items():
        prof = profiles[code]
        best = max(lakes, key=lambda l: name_similarity(prof["name"] or "", l["name"]))
        for lake in lakes:
            matched += 1
            # A fish management zone covers both halves of a pair, and the
            # amenities describe the site they share, so those are safe to
            # copy. Surface area is not: it measures one body of water.
            #
            # The profile row's area belongs to the lake the row is NAMED
            # after — Alberta's stocking map confirms it for seven of the
            # eight shared rows, matching Hogarth Lower at 0.8 ha, Lower
            # Smuts at 2.0, MD Peace Pond #1 at 1.1 and Lower Wildhorse at
            # 25.4 while their neighbours measure something else entirely.
            # Copying it to both put the same hectares on two lakes and made
            # Upper Wildhorse ten times its real size.
            #
            # The neighbour gets nothing instead, and says so.
            lake["zone"] = prof["zone"]
            lake["amenities"] = prof["amenities"]
            if lake is best:
                lake["surface_area_ha"] = prof["surface_area_ha"]
            if prof["lat"] is not None and prof["lon"] is not None and lake is best:
                lake["lat"], lake["lon"] = prof["lat"], prof["lon"]
                lake["coord_source"] = "profile"
            if prof["name"] and lake is best:
                lake["name_variants"] = sorted(set(lake["name_variants"]) | {prof["name"]})
                lake["aliases"] = sorted(set(lake["aliases"]) | {normalize_name(prof["name"])})
                lake["name"] = prof["name"]
    for lake in reg.lakes:
        lake["base_name"] = lake["name"]
    reg.reindex()
    return matched


def resolve_duplicate_coordinates(reg):
    """A coordinate given to two different lakes is not a verified coordinate.

    The profiles CSV repeats one position across five pairs — North and South
    Two Lake share a point (and an area) though their land descriptions put
    them 3.4 km apart, and Sibbald Lake carries Sibbald Meadows Pond's. In each
    pair the position fits one lake and not the other, so keep it for whichever
    lake's own land description agrees, and fall the rest back to the grid.
    """
    groups = defaultdict(list)
    for lake in reg.lakes:
        if lake["coord_source"] == "profile" and lake["lat"] is not None:
            groups[(round(lake["lat"], 6), round(lake["lon"], 6))].append(lake)

    demoted = []
    for (lat, lon), lakes in groups.items():
        if len(lakes) < 2:
            continue

        def gap(lake):
            for code in lake["ats_codes"]:
                est = ats_to_latlng(code)
                if est[0] is not None:
                    return haversine_km(lat, lon, est[0], est[1])
            return float("inf")

        keeper = min(lakes, key=gap)
        for lake in lakes:
            if lake is keeper:
                continue
            for code in lake["ats_codes"]:
                est = ats_to_latlng(code)
                if est[0] is not None:
                    lake["lat"], lake["lon"] = est
                    lake["coord_source"] = "ats"
                    demoted.append((lake["name"], round(gap(lake), 1)))
                    break
    reg.reindex()
    return demoted


def drop_empty_lakes(reg, linked):
    """Remove registry entries that no report row resolved to.

    Alberta has issued two waterbody ids for the same water more than once —
    Magrath Children's Pond and East Stormwater Pond each have a twin that
    ends up holding nothing. Left in, they clutter the review candidates and
    force a disambiguating suffix onto a name that has no real twin.
    """
    used = {lake_id for rows in linked.values() for lake_id, _ in rows}
    dropped = [l for l in reg.lakes if l["lake_id"] not in used]
    reg.lakes = [l for l in reg.lakes if l["lake_id"] in used]
    reg.reindex()
    return dropped


def settle_coordinates(reg):
    """Every lake needs a position. Prefer verified, then Alberta's, then the grid."""
    counts = defaultdict(int)
    for lake in reg.lakes:
        # A position that already names where it came from keeps that name.
        # Everything else with a position came from the report rows, which is
        # what "alberta" means. Without this, a coordinate taken from the
        # stocking map or settled by hand in data/lake_facts.csv was relabelled
        # "alberta" on the very next line and the map claimed a provenance the
        # value does not have.
        if lake["coord_source"] in ("profile", "mywildalberta"):
            counts[lake["coord_source"]] += 1
            continue
        if lake["lat"] is not None:
            lake["coord_source"] = "alberta"
            counts["alberta"] += 1
            continue
        for code in lake["ats_codes"]:
            lat, lon = ats_to_latlng(code)
            if lat is not None:
                lake["lat"], lake["lon"] = lat, lon
                lake["coord_source"] = "ats"
                counts["ats"] += 1
                break
        else:
            # Minted from a report row that gave only a name — 2015 publishes
            # nothing else. It stays in the history and its fish still count,
            # but it cannot be drawn until someone gives it a position.
            lake["coord_source"] = "unknown"
            counts["none"] += 1
    reg.reindex()
    return counts


def disambiguate_names(reg):
    """Give every lake a name a person can tell apart from its neighbours.

    Alberta sometimes issues two waterbody ids with the same name at the same
    coordinates (two "East Stormwater Pond" entries differing only in their
    land description). They stay separate lakes, because Alberta says they are,
    but two identical pins on the map help nobody — so the land description
    goes into the name of each.
    """
    for lake in reg.lakes:
        lake["name"] = lake.get("base_name", lake["name"])
    groups = defaultdict(list)
    for lake in reg.lakes:
        if lake["lat"] is None:
            continue
        groups[(normalize_name(lake["name"]), round(lake["lat"], 3),
                round(lake["lon"], 3))].append(lake)
    fixed = 0
    for lakes in groups.values():
        if len(lakes) < 2:
            continue
        for lake in lakes:
            code = lake["ats_codes"][0] if lake["ats_codes"] else lake["lake_id"]
            lake["name"] = f"{lake['name']} [{code}]"
            fixed += 1
    reg.reindex()
    return fixed


def link_all(reg, rows_by_year, aliases, verbose=True):
    """Resolve every row to a lake. Returns (per-year rows, review list, stats)."""
    linked = defaultdict(list)
    review = []
    stats = defaultdict(int)
    shared_codes = shared_land_descriptions(reg)

    for year in sorted(rows_by_year):
        for row in rows_by_year[year]:
            if row["species"] not in TROUT:
                stats["not_trout"] += 1
                continue

            row_name = display_name(row["official_name"], row["common_name"])
            key = normalize_name(row_name)
            if key in aliases["skip"]:
                stats["skipped_by_you"] += 1
                continue
            if key in aliases["new"]:
                review.append(dict(row=row, note="you marked this a new lake",
                                   alts=[], method="none"))
                stats["new_by_you"] += 1
                continue

            # A decision you already made in a past review always wins.
            #
            # A land description is consulted before a name because it is
            # usually the stronger key, and for 633 of the registry's 640
            # quarter sections it is. For the other seven it is the WEAKEST
            # evidence there is, because it is the one field that is identical
            # for both lakes on it, and the name is all that can separate them.
            #
            # apply_review.py records a confirmed answer as a land-description
            # rule as well as a name, which is right for the 633 and turns an
            # answer about one row into a rule about its neighbour for the
            # seven. So on a shared quarter section the rule is only honoured
            # when the row's own name does not contradict it; otherwise the row
            # falls through to resolve(), where the name is weighed properly.
            #
            # Without this, MD Peace Pond #1's fish were credited to #2 and
            # Lower Champion Lake's to Upper, for six years each.
            forced = None
            if row.get("ats") and row["ats"].upper() in aliases["ats"]:
                candidate = aliases["ats"][row["ats"].upper()]
                target = reg.by_id.get(candidate)
                contested = normalise_code(row["ats"]) in shared_codes
                if not contested or target is None or not discriminating_conflict(
                        row_name, best_matching_name(target, row_name)):
                    forced = candidate
            if not forced and key in aliases["name"]:
                forced = aliases["name"][key]
            if forced and forced in reg.by_id:
                lake, method, conf = reg.by_id[forced], "reviewed", 1.0
                alts, note = [], ""
            else:
                lake, method, conf, note, alts = reg.resolve(row)

            if lake is None:
                review.append(dict(row=row, note=note, alts=alts, method=method))
                stats["review"] += 1
                continue

            reg.absorb(lake, row, wrong_ats=aliases["wrong_ats"])
            linked[year].append((lake["lake_id"], row))
            stats[method] += 1

    if verbose:
        print("\n  how each row was resolved")
        for method in sorted(stats, key=lambda m: -stats[m]):
            print(f"    {method:<22} {stats[method]:>6}")
    return linked, review, stats


def mint_unlinked(reg, review):
    """Create new lakes for review rows that clearly are not in the registry.

    Only for rows with a land description that sits far from anything known.
    Everything else stays in the review file for a human.
    """
    minted, still = [], []
    groups = defaultdict(list)
    for item in review:
        code = item["row"].get("ats")
        # "none" = nothing at all nearby. "unknown_lake" = the nearest known
        # lake is far away and named nothing like this one. Both mean new.
        # A row you marked NEW yourself counts even with no land description:
        # some 2015 rows give a name and nothing else, and leaving them in the
        # queue forever would quietly drop their fish from the history.
        if item["method"] in ("none", "unknown_lake"):
            key = code or ("name:" + normalize_name(
                display_name(item["row"]["official_name"], item["row"]["common_name"])))
            if code or item["note"].startswith("you marked"):
                groups[key].append(item)
                continue
        still.append(item)

    for key, items in groups.items():
        row = items[0]["row"]
        code = row.get("ats")
        if row["lat"] is not None:
            lat, lon, source = row["lat"], row["lon"], "alberta"
        elif code:
            lat, lon = ats_to_latlng(code)
            source = "ats" if lat is not None else "unknown"
        else:
            lat, lon, source = None, None, "unknown"
        name = _title(display_name(row["official_name"], row["common_name"])) or key
        lake = reg.mint(name, lat, lon, ats_codes=[code] if code else [], aliases=[name])
        lake["coord_source"] = source
        minted.append((lake, items))
    reg.reindex()
    return minted, still


def write_review(review, reg):
    """Write the rows a human needs to settle, richest context first."""
    import csv as _csv
    seen, unique = set(), []
    for item in review:
        row = item["row"]
        key = (normalize_name(display_name(row["official_name"], row["common_name"])),
               row.get("ats"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW_PATH, "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(["lake_id", "year", "report_name", "ats", "why",
                    "candidate_1", "candidate_2", "candidate_3", "rows_affected"])
        counts = defaultdict(int)
        for item in review:
            row = item["row"]
            counts[(normalize_name(display_name(row["official_name"], row["common_name"])),
                    row.get("ats"))] += 1
        for item in sorted(unique, key=lambda i: (i["row"]["year"], i["row"]["official_name"])):
            row = item["row"]
            name = display_name(row["official_name"], row["common_name"])
            lat, lon = (row["lat"], row["lon"])
            if lat is None and row.get("ats"):
                lat, lon = ats_to_latlng(row["ats"])
            cands = []
            for lake_id in item["alts"][:3]:
                lake = reg.by_id.get(lake_id)
                if not lake:
                    continue
                d = (haversine_km(lat, lon, lake["lat"], lake["lon"])
                     if lat is not None and lake["lat"] is not None else None)
                sim = name_similarity(name, lake["name"])
                cands.append(f"{lake_id} | {lake['name']} | "
                             f"{'%.1f km' % d if d is not None else 'no position'} | name {sim:.2f}")
            cands += [""] * (3 - len(cands))
            w.writerow(["", row["year"], name, row.get("ats") or "", item["note"] or item["method"],
                        *cands[:3],
                        counts[(normalize_name(name), row.get("ats"))]])
    return len(unique)


def write_year_files(reg, linked, provisional):
    """Emit one file per year in the shape the map already reads."""
    manifest_years = []
    for year in sorted(linked):
        by_lake = defaultdict(list)
        for lake_id, row in linked[year]:
            by_lake[lake_id].append(row)
        out = []
        for lake_id, rows in by_lake.items():
            lake = reg.by_id[lake_id]
            stockings = []
            for r in sorted(rows, key=lambda r: (r["date"] or "", r["species"])):
                stockings.append(dict(
                    species=r["species"], strain=r["strain"] or None,
                    genotype=r["genotype"] or None, length_cm=r["length_cm"],
                    number=r["number"], date=r["date"], year=year,
                    date_precision=r["date_precision"]))
            out.append(dict(
                lake_id=lake_id,
                ats=(lake["ats_codes"][0] if lake["ats_codes"] else None),
                name=lake["name"], lat=lake["lat"], lon=lake["lon"],
                coord_source=lake["coord_source"],
                zone=lake.get("zone"), surface_area_ha=lake.get("surface_area_ha"),
                amenities=lake.get("amenities"),
                stockings=stockings,
                total_fish=sum(s["number"] for s in stockings),
                species_set=sorted({s["species"] for s in stockings})))
        out.sort(key=lambda l: -l["total_fish"])
        (DATA_DIR / f"lakes_{year}.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest_years.append(year)

    manifest = dict(years=manifest_years,
                    provisional=sorted(y for y in manifest_years if y in provisional))
    (DATA_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_years


def write_quality_summary(reg, review_count, linked_rows, trout_rows):
    """A small file the map reads to tell the user how solid the data is."""
    sources_count = defaultdict(int)
    for lake in reg.lakes:
        sources_count[lake["coord_source"] or "unknown"] += 1
    summary = dict(
        lakes=len(reg.lakes),
        verified_coords=sources_count["profile"],
        alberta_coords=sources_count["alberta"],
        estimated_coords=sources_count["ats"],
        no_coords=sources_count["unknown"],
        confusable=len(reg.confusable),
        rows_linked=linked_rows,
        rows_total=trout_rows,
        rows_awaiting_review=review_count,
        lakes_with_multiple_land_descriptions=sum(1 for l in reg.lakes if len(l["ats_codes"]) > 1),
    )
    (DATA_DIR / "quality_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    return summary


REGULATIONS_PDF = "alberta-sportfishing-regulations-2026-tables.pdf"


def write_depths(reg):
    """Lake depth, and what it implies in summer and winter.

    Skipped quietly when the collection has not been run: a missing depth file
    should cost the map its depth advice, not its data. Everything downstream
    is built to say nothing rather than guess when depth is absent.
    """
    import depth
    stats = depth.write(reg.lakes, DATA_DIR)
    if not stats:
        print("\nNo data/raw/mywildalberta_lakes.csv; skipping depth and winterkill.")
        print("  Build it once with: cd scripts && python3 import_stocking_map.py")
        return None
    print("\nReading lake depth...")
    print(f"  {stats['with_depth']} lake(s) with a depth, "
          f"{stats['stated_unavailable']} where Alberta states none is available")
    if stats["aerated"]:
        print(f"  {stats['aerated']} aerated; Alberta states nothing either way "
              f"for the rest")
    else:
        print("  no aerated-lake list present; winterkill uses depth alone")
    print(f"  mean depth: {stats['mean_published']} published, "
          f"{stats['mean_estimated']} estimated as a range"
          + (f", {stats['mean_contradicted']} refused for contradicting the maximum"
             if stats["mean_contradicted"] else ""))
    if stats["aeration_photo_only"]:
        print(f"  {stats['aeration_photo_only']} with aeration seen only in a photo, "
              f"shown but not counted")
    return stats


def write_profiles(reg):
    """Amenities, the province's own prose, and the photo index.

    Skipped quietly when the collection has not been run, like the depth step:
    a missing profile file should cost the map its facilities filter, not its
    data.
    """
    import profile
    stats = profile.write(reg.lakes, DATA_DIR)
    if not stats:
        return None
    print("\nReading what Alberta says about each lake...")
    print(f"  {stats['with_amenities']} with amenities, "
          f"{stats['with_description']} with a description")
    print(f"  {stats['photos']} photo(s) across {stats['with_photos']} lake(s), "
          f"linked and not copied")
    print(f"  {stats['facets']} facet(s) worth filtering by")
    return stats


def write_regulations(reg=None):
    """Catch limits and seasons, read out of the sportfishing guide.

    Skipped quietly when the guide is not present, so the rest of the pipeline
    still builds: a missing guide should cost the map its limits, not its data.
    """
    source = sources.RAW_DIR / REGULATIONS_PDF
    if not source.exists():
        print(f"\n{REGULATIONS_PDF} not present; skipping catch limits.")
        return None
    import regulations
    print("\nReading catch limits from the sportfishing regulations...")
    regs = regulations.load(source)
    year = regs["guide_year"]
    rows = sum(len(z["lakes"]) + len(z["rivers"]) for z in regs["zones"].values())
    # The full parse is deliberately not written out. Only the per-lake
    # resolution below is read by anything; a second copy of the guide in
    # data/ was 404 KB that every build rewrote and nothing ever opened.
    print(f"  {rows} site-specific rows, {len(regs['defaults'])} watershed defaults, "
          f"{len(regs['stocked'])} put-and-take waters")

    if reg is not None:
        resolved, review = regulations.match_lakes(regs, reg.lakes)
        (DATA_DIR / "lake_regulations.json").write_text(
            json.dumps({"guide_year": year, "lakes": resolved},
                       indent=1, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8")
        with (DATA_DIR / "regs_review.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["lake", "lake_id", "zone", "why", "closest", "score"])
            writer.writeheader()
            for row in sorted(review, key=lambda r: (r["zone"], r["lake"])):
                writer.writerow(row)
        basis = {}
        for entry in resolved.values():
            basis[entry["basis"]] = basis.get(entry["basis"], 0) + 1
        print(f"  matched {len(resolved)} lakes: "
              + ", ".join(f"{n} {k}" for k, n in sorted(basis.items(), key=lambda kv: -kv[1])))
        if review:
            print(f"  {len(review)} lake(s) left unresolved on purpose "
                  f"-> data/regs_review.csv")
    return year, rows, len(regs["stocked"])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", nargs="*", type=int)
    ap.add_argument("--report", action="store_true", help="summarize only, write nothing")
    args = ap.parse_args()

    years = args.years or sorted(sources.YEAR_SOURCES)
    print(f"Reading {len(years)} year(s) of reports...")
    rows_by_year = {y: sources.read_year(y) for y in years}
    total = sum(len(v) for v in rows_by_year.values())
    print(f"  {total:,} rows read")

    print("\nBuilding the registry from Alberta's waterbody identifiers...")
    reg = build_spine(rows_by_year)
    print(f"  {len(reg.lakes)} lakes with an Alberta identifier")
    drift = sum(1 for l in reg.lakes if len(l["ats_codes"]) > 1)
    print(f"  {drift} of them carry more than one land description across years")

    matched = attach_profiles(reg)
    confirmed = apply_facts(reg)
    print(f"  {matched} matched to a profile entry (zone, amenities, verified position)")
    demoted = resolve_duplicate_coordinates(reg)
    for name, gap in demoted:
        print(f"  shared coordinate: {name} moved to its own land description ({gap} km away)")
    counts = settle_coordinates(reg)
    print(f"  positions: {counts['profile']} verified, {counts['alberta']} from Alberta, "
          f"{counts['mywildalberta']} from the stocking map, "
          f"{counts['ats']} from the land description, {counts['none']} unknown")
    renamed = disambiguate_names(reg)
    if renamed:
        print(f"  {renamed} lake(s) renamed to tell same-named neighbours apart")
    print(f"  {len(reg.confusable)} lakes flagged confusable (never auto-linked by similarity)")

    aliases = load_aliases()
    if aliases["name"] or aliases["ats"]:
        print(f"  {len(aliases['name']) + len(aliases['ats'])} alias(es) from past reviews")

    print("\nLinking every row to a lake...")
    linked, review, _ = link_all(reg, rows_by_year, aliases)

    minted, still = mint_unlinked(reg, review)
    if minted:
        print(f"\n  {len(minted)} new lake(s) created for rows with a land description "
              f"far from anything known")
        # Re-resolve the rows that just got a home.
        for lake, items in minted:
            for item in items:
                reg.absorb(lake, item["row"])
                linked[item["row"]["year"]].append((lake["lake_id"], item["row"]))

    # Again, now that the lakes minted from a land description exist: those are
    # precisely the ones with no waterbody id, so they are the ones a published
    # id is recorded for, and they are not in the registry during the first pass.
    confirmed += apply_facts(reg)
    if confirmed:
        print(f"\n  {confirmed} field(s) from data/lake_facts.csv, your past answers")

    dropped = drop_empty_lakes(reg, linked)
    if dropped:
        print(f"\n  {len(dropped)} registry entr(ies) held no rows and were dropped: "
              f"{', '.join(l['name'] for l in dropped[:6])}")
    disambiguate_names(reg)

    linked_rows = sum(len(v) for v in linked.values())
    trout_rows = sum(1 for y in rows_by_year.values() for r in y if r["species"] in TROUT)
    print(f"\n  {linked_rows:,} of {trout_rows:,} trout rows linked "
          f"({linked_rows / trout_rows * 100:.1f}%)")
    print(f"  {len(still)} row(s) need a human decision")

    if args.report:
        print("\n--report given; nothing written.")
        return 0

    settle_coordinates(reg)
    save_registry(reg)
    n_review = write_review(still, reg)
    years_written = write_year_files(reg, linked, sources.PROVISIONAL_YEARS)
    write_quality_summary(reg, len(still), linked_rows, trout_rows)
    n_depth = write_depths(reg)
    n_profile = write_profiles(reg)
    n_regs = write_regulations(reg)
    print(f"\nWrote data/lake_registry.json ({len(reg.lakes)} lakes)")
    if n_depth:
        print(f"Wrote data/lake_depth.json ({n_depth['with_depth']} lakes with a depth)")
    if n_profile:
        print(f"Wrote data/lake_profile.json and data/lake_photos.json "
              f"({n_profile['with_amenities']} with amenities, "
              f"{n_profile['photos']} photos)")
    if n_regs:
        print(f"Wrote data/lake_regulations.json (guide {n_regs[0]}: "
              f"{n_regs[1]} site-specific rows, {n_regs[2]} put-and-take waters)")
    print(f"Wrote {len(years_written)} year file(s): {years_written[0]}-{years_written[-1]}")
    print(f"Wrote data/link_review.csv ({n_review} question(s) for you)")
    if n_review:
        print("\nNext: fill in the lake_id column in data/link_review.csv, then run")
        print("      python3 apply_review.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
