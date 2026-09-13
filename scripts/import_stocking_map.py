"""Alberta's stocking map, read from an exported workbook instead of the site.

    python3 import_stocking_map.py            # rewrite the CSVs under data/raw/
    python3 import_stocking_map.py --check    # report drift, write nothing
    python3 import_stocking_map.py --report   # coverage, and every contradiction

fetch_lake_pages.py was written to collect exactly this material from
mywildalberta.ca one lake page at a time. It was never run, so
data/raw/mywildalberta_lakes.csv has never existed, so depth.py and
reconcile.py have never had an input and the map has shown no depth for any
lake. This reads the same facts out of a workbook exported from the map by
hand, and writes the same CSV, so both of those scripts work unchanged.

The output is committed rather than rebuilt
-------------------------------------------
Like fetch_lake_pages.py, this runs once and its CSVs are committed. The build
never calls it. data/raw/ holds inputs, and a build that writes into its own
input directory inverts the check that data/ is exactly what the pipeline
produced. The input is also a hand-made snapshot that cannot change without a
person, so re-deriving it on every build buys nothing and would make openpyxl
a hard dependency of a step that currently degrades quietly when absent.

What CI would have got from an in-build importer is recovered by a test that
re-runs this transform in memory and compares it to the committed CSVs.

Unknown is never zero
---------------------
The workbook writes "Unknown" where Alberta publishes nothing, and its own
notes insist that is preserved. Every such cell becomes an empty field, never
a 0, because a lake with no published depth and a lake that is 0 m deep are
not the same claim and the second one is not true of anything.

depth_stated_unavailable stays empty for the same reason. fetch_lake_pages.py
sets it only when a page says in words that no depth is available. "Unknown"
here means the exporter found none, which is a weaker claim, and writing it
would put words in Alberta's mouth.

Rows are checked against themselves
-----------------------------------
Watridge Lake publishes a position 140 km from its own land description and
from the district it also publishes: a single digit typo in the longitude.
The repo's own coordinate is right. So a position that contradicts the land
description on the same row is dropped rather than passed on, and every such
contradiction is written to data/raw/mywildalberta_issues.csv where a person
can see what was refused and why.
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import ats
import registry

ROOT = Path(__file__).parent.parent
WORKBOOK = ROOT / "data" / "raw" / "mywildalberta" / "Alberta_Stocked_Waterbodies_20260911.xlsx"
REGISTRY = ROOT / "data" / "lake_registry.json"
LAKES_CSV = ROOT / "data" / "raw" / "mywildalberta_lakes.csv"
AERATED_CSV = ROOT / "data" / "raw" / "aca_aerated_lakes.csv"
PHOTOS_CSV = ROOT / "data" / "raw" / "mywildalberta_photos.csv"
ISSUES_CSV = ROOT / "data" / "raw" / "mywildalberta_issues.csv"
DESCRIPTIONS_CSV = ROOT / "data" / "raw" / "mywildalberta_descriptions.csv"
OUT_OF_SCOPE_CSV = ROOT / "data" / "out_of_scope.csv"
WEIGHTS_CSV = ROOT / "data" / "raw" / "mywildalberta_weights.csv"
ATLAS_CSV = ROOT / "data" / "raw" / "lake_species_atlas.csv"
ACA_ROSTER = ROOT / "data" / "aca_aeration_roster.csv"

# The header sits on row 5 of every data sheet; rows 1-4 are the title block.
HEADER_ROW = 5

# Values that mean "nothing published here", in any column.
BLANKS = {"unknown", "not stated", "not stated on map.", "n/a", ""}

# Far enough that the position and the land description cannot both describe
# the same lake.
#
# Measured over the 341 rows that publish both: median 0.52 km, 90th
# percentile 1.02 km, 99th 1.64 km, then Little Fish Lake at 2.14 km and
# nothing at all until Watridge Lake at 140.63 km. A quarter section is
# about 800 m across and a big lake's reference point sits further still
# from its centre, so a couple of kilometres is ordinary and refusing it
# would throw away good positions to catch nothing.
#
# The threshold belongs in the empty space between those two numbers. Ten
# kilometres is far outside anything the geometry explains and far inside
# the one row that is actually wrong, so exactly one position is refused.
POSITION_CONTRADICTION_KM = 10.0

# Alberta's own notes name these two: their only aeration evidence is a photo
# caption, and the export declines to call them aerated on that basis. Carried
# so the evidence is visible, and never applied to a winterkill band.
CAPTION_ONLY_EVIDENCE = "photo_caption"


def cell_text(value):
    """One spelling per value, so re-running writes the same bytes.

    openpyxl hands back int for 7, float for 7.3 and str for "Unknown" in the
    same column. %g would turn 6218.3 into 6218.3 but 1e-05 into 1e-05 and
    100000 into 1e+05, so the numbers are spelled out instead.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return repr(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value).strip()


def published(value):
    """The text as published, or "" when the workbook is saying it has none."""
    text = cell_text(value)
    return "" if text.strip().lower() in BLANKS else text


def number(value):
    text = published(value)
    try:
        return float(text)
    except ValueError:
        return None


def read_sheet(workbook, title):
    sheet = workbook[title]
    rows = list(sheet.iter_rows(min_row=HEADER_ROW, values_only=True))
    header = [cell_text(h) for h in rows[0]]
    out = []
    for row in rows[1:]:
        if row and row[0] is not None:
            out.append(dict(zip(header, row)))
    return out


def load_registry():
    """Alberta's waterbody id and land description, as this repo holds them."""
    if not REGISTRY.exists():
        return {}, {}
    lakes = json.loads(REGISTRY.read_text(encoding="utf-8"))
    by_id, by_ats = {}, defaultdict(list)
    for lake in lakes:
        wid = str(lake.get("waterbody_id") or "").strip()
        if wid:
            by_id[wid] = lake
        for code in lake.get("ats_codes") or []:
            by_ats[normalise_ats(code)].append(lake)
    return by_id, by_ats


def normalise_ats(text):
    """SW 13-52-2-W5 and SW13-52-2-W5 are the same quarter section."""
    return re.sub(r"[^A-Z0-9-]", "", str(text or "").upper())


def stocked_years(details):
    """The years each waterbody has a record in, the way the collector wrote them."""
    years = defaultdict(set)
    for row in details:
        wid = cell_text(row.get("Lake ID"))
        year = row.get("Year")
        if wid and year:
            years[wid].add(int(year))
    return {wid: " ".join(str(y) for y in sorted(ys)) for wid, ys in years.items()}


def self_consistency(waterbodies, photos):
    """Every way a row contradicts itself, before any of it is published.

    The workbook is a good source and is not a perfect one. Each check here
    compares a row against another field of the same row, never against the
    repo — a disagreement with the repo is reconcile.py's job and goes to a
    person, but a row that disagrees with itself cannot be published either way.
    """
    issues = []
    seen_position = defaultdict(list)
    captioned = {cell_text(p.get("Lake ID")) for p in photos
                 if re.search(r"(?i)aerat|windmill|bubbler|diffuser", cell_text(p.get("Photo caption")))}

    for row in waterbodies:
        wid = cell_text(row.get("Lake ID"))
        name = cell_text(row.get("Waterbody name"))
        lat, lon = number(row.get("Latitude")), number(row.get("Longitude"))
        code = published(row.get("ATS"))

        if lat is not None and lon is not None and code:
            grid = ats.ats_to_latlng(normalise_ats(code))
            if grid:
                km = ats.haversine_km(lat, lon, grid[0], grid[1])
                if km > POSITION_CONTRADICTION_KM:
                    issues.append({
                        "waterbody_id": wid, "name": name, "check": "position_vs_ats",
                        "published": f"{lat},{lon}", "derived": f"{grid[0]:.5f},{grid[1]:.5f}",
                        "note": f"{km:.1f} km from its own land description {code}; "
                                f"position not published"})

        mx, mn = number(row.get("Max depth (m)")), number(row.get("Mean depth (m)"))
        if mx is not None and mn is not None and mn > mx:
            issues.append({
                "waterbody_id": wid, "name": name, "check": "mean_exceeds_max",
                "published": f"mean {mn:g} m, max {mx:g} m", "derived": "",
                "note": "a mean deeper than the maximum; depth.py refuses the pair "
                        "rather than swapping them"})

        if lat is not None and lon is not None:
            seen_position[(round(lat, 4), round(lon, 4))].append((wid, name))

        if cell_text(row.get("Stocking records")) == "0":
            issues.append({
                "waterbody_id": wid, "name": name, "check": "zero_records",
                "published": "0 stocking records", "derived": "",
                "note": "on the map with no stocking history of its own"})

        if wid in captioned and cell_text(row.get("Aerated")) != "Yes":
            issues.append({
                "waterbody_id": wid, "name": name, "check": "aeration_caption_only",
                "published": cell_text(row.get("Aerated")), "derived": "photo caption",
                "note": "a photograph shows aeration equipment but the description "
                        "does not say so; recorded, never applied"})

    for point, holders in sorted(seen_position.items()):
        if len(holders) > 1:
            for wid, name in holders:
                others = ", ".join(f"{w} {n}" for w, n in holders if w != wid)
                issues.append({
                    "waterbody_id": wid, "name": name, "check": "duplicate_position",
                    "published": f"{point[0]},{point[1]}", "derived": others,
                    "note": "two published ids at the same point; one is likely stale"})

    return issues, {i["waterbody_id"] for i in issues if i["check"] == "position_vs_ats"}, captioned


def waterbody_rows(waterbodies, details, by_id, refused_positions):
    """The 19 columns fetch_lake_pages.py writes, so its readers work unchanged."""
    years = stocked_years(details)
    rows = []
    for row in waterbodies:
        wid = cell_text(row.get("Lake ID"))
        lake = by_id.get(wid)
        lat = "" if wid in refused_positions else published(row.get("Latitude"))
        lon = "" if wid in refused_positions else published(row.get("Longitude"))
        rows.append({
            "waterbody_id": wid,
            "lake_id": (lake or {}).get("lake_id", ""),
            "registry_name": (lake or {}).get("name", ""),
            # The name the map itself uses. For the 41 waterbodies this repo
            # does not hold by id, it is the only name there is.
            "page_name": cell_text(row.get("Waterbody name")),
            "max_depth_m": published(row.get("Max depth (m)")),
            "mean_depth_m": published(row.get("Mean depth (m)")),
            "surface_area_ha": published(row.get("Surface area (ha)")),
            "zone": published(row.get("Zone")),
            "legal_land_description": published(row.get("ATS")),
            "latitude": lat,
            "longitude": lon,
            # Not published by the map export. The repo already carries species
            # and lengths from Alberta's own stocking reports, which are the
            # better source for both, so these stay empty rather than duplicated.
            "elevation_m": "", "species": "", "average_length_cm": "",
            "stocked_years": years.get(wid, ""),
            "access": published(row.get("Directions URL")),
            "amenities": published(row.get("Amenities")),
            "region": published(row.get("District")),
            "county": "",
            # Only set when a page says in words that no depth is available.
            # "Unknown" is the exporter finding none, which is not that claim.
            "depth_stated_unavailable": "",
        })
    return rows


def load_aca_roster(by_id):
    """The lakes ACA publishes as being on its Lake Aeration Program.

    Hand-owned, like data/lake_aliases.csv, because it comes from a person
    reading ACA's own roster rather than from anything in the workbook. Alberta
    lake pages name twelve aerated lakes; ACA's roster names twenty-two, and the
    two lists only partly overlap — Camp 9 Trout Pond and Salter's Lake are
    stated by Alberta and absent from ACA's, which is what you would expect of a
    fish-and-game club windmill that is not part of the province's programme.

    Keyed on lake_id and not on name: Swan Lake, Spring Lake and Birch Lake are
    each one of several in Alberta, and a name alone would pick the wrong water.
    """
    if not ACA_ROSTER.exists():
        return {}
    out = {}
    with ACA_ROSTER.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            lake_id = (row.get("lake_id") or "").strip()
            if lake_id:
                out[lake_id] = row
    by_lake_id = {v.get("lake_id"): k for k, v in by_id.items() if v.get("lake_id")}
    return {by_lake_id[lid]: row for lid, row in out.items() if lid in by_lake_id}


def aerated_rows(waterbodies, captioned, roster):
    """Aeration, with how strongly it is known kept beside it.

    Alberta's lake descriptions name twelve. Two more appear only in a
    photograph, and the export itself declines to call those aerated: a picture
    shows that equipment existed when the picture was taken, not that the
    programme runs now. Both are carried, and only the stated ones are allowed
    to move a winterkill band, because a lake wrongly marked aerated reads as
    safer than it is.

    aca_aeration.py adds the published_list tier from ACA's own roster.
    """
    rows = []
    for row in waterbodies:
        wid = cell_text(row.get("Lake ID"))
        name = cell_text(row.get("Waterbody name"))
        evidence = published(row.get("Aeration evidence / notes"))
        listed = roster.get(wid)
        if cell_text(row.get("Aerated")) == "Yes":
            rows.append({"waterbody_id": wid, "name": name, "confidence": "stated",
                         "evidence": evidence or "the lake description says so"})
        elif listed:
            rows.append({"waterbody_id": wid, "name": name,
                         "confidence": "published_list",
                         "evidence": f"ACA's Lake Aeration Program roster, as "
                                     f"{listed['on_the_roster_as']}"
                                     + (f" — {listed['note']}" if listed.get("note") else "")})
        elif wid in captioned:
            rows.append({"waterbody_id": wid, "name": name,
                         "confidence": CAPTION_ONLY_EVIDENCE,
                         "evidence": evidence or "a photo caption shows aeration equipment"})
    return rows


# What this map is for. sources.py discards every other species before linking,
# so these never reach the registry — but a gap between 346 published
# waterbodies and the number mapped should be a decision on the record rather
# than an absence nobody can account for.
TROUT_ON_THE_MAP = {"RAINBOW TROUT", "BROOK TROUT", "BROWN TROUT", "TIGER TROUT",
                    "CUTTHROAT TROUT", "WESTSLOPE CUTTHROAT TROUT"}


def out_of_scope_rows(waterbodies, details, by_id):
    """Waters Alberta stocks that this map deliberately does not show.

    This used to list 31 lakes — every one stocked with walleye or pike and no
    trout — on the grounds that adding them was not an import but a change of
    what the project is. That change has since been made: sources.py now carries
    walleye, pike and grayling, so the reports are read with the wider species
    set and those lakes are on the map with the rest.

    The file stays, and now writes no rows. It is the record of a decision and
    of its reversal, and if Alberta stocks something genuinely outside the map's
    scope one day, this is where it will say so.
    """
    species = defaultdict(set)
    records = defaultdict(int)
    for row in details:
        wid = cell_text(row.get("Lake ID"))
        species[wid].add(cell_text(row.get("Species")))
        records[wid] += 1

    rows = []
    for row in waterbodies:
        wid = cell_text(row.get("Lake ID"))
        if wid in by_id:
            continue                       # already on the map
        found = species.get(wid, set())
        if found & TROUT_ON_THE_MAP:
            continue                       # trout: not out of scope, see the issues file
        rows.append({
            "waterbody_id": wid,
            "name": cell_text(row.get("Waterbody name")),
            "species": "; ".join(sorted(found)) or "none published",
            "records": str(records.get(wid, 0)),
            "zone": published(row.get("Zone")),
            "why": "stocked with no trout; this is a trout map",
        })
    return rows


# The four-letter codes the reports use, for the full names the workbook writes.
SPECIES_CODE = {
    "RAINBOW TROUT": "RNTR", "BROOK TROUT": "BKTR", "BROWN TROUT": "BNTR",
    "TIGER TROUT": "TGTR", "CUTTHROAT TROUT": "CTTR",
    "WESTSLOPE CUTTHROAT TROUT": "WSCT", "WALLEYE": "WALL",
    "NORTHERN PIKE": "NRPK", "ARCTIC GRAYLING": "ARGR",
}

# A weight averaged over records that disagree by more than this fraction of
# itself is not one batch described twice. Police Lake's 2023 rainbows are
# published at 1400 g and 2600 g for the same 45 cm, which is two different
# fish; one number for both would be a number that is true of neither.
WEIGHT_SPREAD_LIMIT = 0.20


def weight_rows(details):
    """How heavy the fish were, which only the stocking map publishes.

    The annual reports give a length and never a weight, so 'a 20 cm rainbow'
    has always been as much as this map could say. The workbook gives both.

    The two publications do not agree row for row — dates and quantities differ
    between them often enough that matching on those lands only a third of the
    time. They do agree on what was put in: one lake, one season, one species,
    one size. That is a hatchery batch, and a batch has one weight. Keyed that
    way, 3,218 of the 3,289 rows from 2021 on find their weight.

    Where several records share a key they almost always agree exactly; the
    median disagreement is zero grams. Where they disagree by more than
    WEIGHT_SPREAD_LIMIT, nothing is written rather than an average of two
    different fish. A published 0.0 is dropped for the same reason "Unknown"
    is: it means below the scale, not weightless.
    """
    groups = defaultdict(list)
    for row in details:
        weight = row.get("Avg weight (g)")
        length = row.get("Avg length (cm)")
        if not isinstance(weight, (int, float)) or not isinstance(length, (int, float)):
            continue                        # "Unknown" is not a weight
        if weight <= 0:
            # Alberta writes 0.0 for walleye fry too small to weigh at the
            # precision it publishes — Lake Newell's 2022 stocking among them.
            # That is a fish below the scale, not a fish weighing nothing, and
            # carrying it forward would put a 0 g fish on the map as a fact.
            continue
        code = SPECIES_CODE.get(cell_text(row.get("Species")).upper())
        if not code:
            continue
        key = (cell_text(row.get("Lake ID")), cell_text(row.get("Year")),
               code, f"{float(length):.1f}")
        groups[key].append(float(weight))

    rows = []
    for (wid, year, code, length), weights in groups.items():
        mean = sum(weights) / len(weights)
        if mean > 0 and (max(weights) - min(weights)) / mean > WEIGHT_SPREAD_LIMIT:
            continue
        rows.append({
            "waterbody_id": wid, "year": year, "species": code,
            "length_cm": length, "weight_g": f"{mean:.1f}",
            "records": str(len(weights)),
        })
    return rows


# Every fish name the Species evidence sheet uses, in Alberta's four-letter
# codes where the province has one. The rough fish have no code in the
# regulations, so they keep their names and are marked as what they are.
ATLAS_SPECIES = {
    "Rainbow Trout": ("RNTR", "sport"),
    "Brook Trout": ("BKTR", "sport"),
    "Brown Trout": ("BNTR", "sport"),
    "Tiger Trout": ("TGTR", "sport"),
    "Cutthroat Trout": ("CTTR", "sport"),
    "Westslope Cutthroat": ("WSCT", "sport"),
    "Bull Trout": ("BLTR", "sport"),
    "Lake Trout": ("LKTR", "sport"),
    "Golden Trout": ("GLTR", "sport"),
    "Arctic Grayling": ("ARGR", "sport"),
    "Walleye": ("WALL", "sport"),
    "Northern Pike": ("NRPK", "sport"),
    "Yellow Perch": ("YLPR", "sport"),
    "Lake Whitefish": ("LKWH", "sport"),
    "Mountain Whitefish": ("MNWH", "sport"),
    "Burbot": ("BURB", "sport"),
    "White Perch": ("WHPR", "sport"),
    "White Sucker": ("WHSC", "rough"),
    "Mountain Sucker": ("MTSC", "rough"),
    "Lake Chub": ("LKCH", "rough"),
    "Emerald Shiner": ("EMSH", "rough"),
    "Fathead Minnow": ("FHMN", "rough"),
    "Brassy Minnow": ("BRMN", "rough"),
    "Brook Stickleback": ("BRST", "rough"),
    "Nine Spine Stickleback": ("NSST", "rough"),
    # Prohibited in Alberta, and the one listing here worth going out of its
    # way to show: an invasive in a lake is a fact about the lake.
    "Prussian Carp": ("PRCP", "invasive"),
}

# The only match grade whose species reach the map. The export distinguishes
# four, and the other three all mean the same thing for our purposes: we do not
# know which lake the page is about, or the page says nothing.
VERIFIED_MATCH = "Matched — species listed"

# Listings the site itself disputes. The export excludes them from its species
# columns and so does this — re-admitting them here would quietly overturn a
# judgement someone already made.
DISPUTED = "Disputed by site"


def registry_id_for(wid, waterbodies, by_id, by_ats):
    """The id this repo actually files a lake under.

    Alberta carries two of these waters under two waterbody ids at once — the
    stocking map calls Magrath Children's Pond 317719 where the annual reports
    call it 6751, same quarter section and same coordinates. build_history.py
    keeps the reports' id and drops the duplicate, so a row keyed on the other
    one would find no lake and vanish silently.

    So: the id if we hold it, otherwise the lake on the same quarter section
    whose name agrees. Anything else returns None and is left out rather than
    guessed at.
    """
    if wid in by_id:
        return wid
    row = waterbodies.get(wid)
    if not row:
        return None
    code = normalise_ats(cell_text(row.get("ATS")))
    name = cell_text(row.get("Waterbody name"))
    for lake in by_ats.get(code, ()):
        if registry.name_similarity(name, lake["name"]) >= 0.85:
            return str(lake.get("waterbody_id") or "")
    return None


def species_rows(overview, evidence, waterbodies, by_id, by_ats):
    """What is reported to swim in a lake, as against what was put in it.

    Stocking records answer only the second question. They say nothing about
    the pike that arrived on their own, and nothing about whether a decade of
    trout is still there. The catch limits answer neither: 64 of the 65 lakes
    the guide lists by name carry the identical pike-walleye-perch triplet,
    which is boilerplate covering what might be present.

    These rows come from Angler's Atlas, which is an angling site and not the
    province — community reports, not a fish survey, and not proof of current
    presence. Everything downstream has to say so. What makes them worth
    carrying anyway is that they are per-lake, cited, and carry the community's
    own agreement and disagreement counts, so a reader can weigh them.

    Only lakes the export graded as a verified match, and never a listing the
    site disputes.
    """
    sites = {cell_text(r.get("Lake ID")): r for r in waterbodies}
    verified = {}
    for row in overview:
        if cell_text(row.get("Match status")) == VERIFIED_MATCH:
            verified[cell_text(row.get("Lake ID"))] = row

    rows = []
    for row in evidence:
        wid = cell_text(row.get("Lake ID"))
        if wid not in verified:
            continue
        wid = registry_id_for(wid, sites, by_id, by_ats)
        if not wid:
            continue
        listing = cell_text(row.get("Listing status"))
        if listing == DISPUTED:
            continue
        mapped = ATLAS_SPECIES.get(cell_text(row.get("Species")))
        if not mapped:
            continue
        code, kind = mapped
        seen = row.get("Visible confirmation date")
        rows.append({
            "waterbody_id": wid,
            "species": code,
            "kind": kind,
            "listing": listing,
            "agree": cell_text(row.get("Agree votes")),
            "disagree": cell_text(row.get("Disagree votes")),
            "confirmed_on": seen.date().isoformat() if hasattr(seen, "date") else "",
            "additional": "yes" if cell_text(
                row.get("Additional to stocking history")).lower() == "yes" else "no",
            "source_url": cell_text(row.get("Source lake page")),
        })
    return rows


def description_rows(waterbodies, by_id):
    """The paragraph Alberta writes about each lake.

    Kept out of mywildalberta_lakes.csv on purpose. That file has to stay
    column-for-column what fetch_lake_pages.py writes, so depth.py and
    reconcile.py can read either one, and a page's prose is not one of the
    label-and-value pairs that collector harvests. Prose belongs in its own
    file rather than bent into a schema that was not built for it.
    """
    rows = []
    for row in waterbodies:
        text = published(row.get("Description"))
        if not text:
            continue
        wid = cell_text(row.get("Lake ID"))
        rows.append({
            "waterbody_id": wid,
            "lake_id": (by_id.get(wid) or {}).get("lake_id", ""),
            "name": cell_text(row.get("Waterbody name")),
            "description": text,
        })
    return rows


def photo_rows(photos, by_id):
    rows = []
    for row in photos:
        wid = cell_text(row.get("Lake ID"))
        rows.append({
            "waterbody_id": wid,
            "lake_id": (by_id.get(wid) or {}).get("lake_id", ""),
            "caption": cell_text(row.get("Photo caption")),
            "url": cell_text(row.get("Original photo URL")),
        })
    return rows


def render(fields, rows, key):
    """The CSV as text, so --check can compare without writing anything."""
    import io
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in sorted(rows, key=key):
        writer.writerow(row)
    return buffer.getvalue()


def by_waterbody(row):
    wid = row["waterbody_id"]
    return (int(wid) if wid.isdigit() else 0, wid)


def build():
    """Every file this produces, as text, keyed by the path it belongs at."""
    import openpyxl
    workbook = openpyxl.load_workbook(WORKBOOK, data_only=True)
    waterbodies = read_sheet(workbook, "Waterbodies")
    details = read_sheet(workbook, "Stocking details")
    photos = read_sheet(workbook, "Pictures")
    overview = read_sheet(workbook, "Species overview")
    evidence = read_sheet(workbook, "Species evidence")
    by_id, by_ats = load_registry()

    issues, refused, captioned = self_consistency(waterbodies, photos)

    # The schema is fetch_lake_pages.py's, taken from the module rather than
    # copied, so the two cannot drift apart without a test noticing.
    import fetch_lake_pages
    fields = (["waterbody_id", "lake_id", "registry_name", "page_name"]
              + list(fetch_lake_pages.INTERESTING) + ["depth_stated_unavailable"])

    return {
        LAKES_CSV: render(fields, waterbody_rows(waterbodies, details, by_id, refused),
                          by_waterbody),
        AERATED_CSV: render(["waterbody_id", "name", "confidence", "evidence"],
                            aerated_rows(waterbodies, captioned, load_aca_roster(by_id)),
                            by_waterbody),
        PHOTOS_CSV: render(["waterbody_id", "lake_id", "caption", "url"],
                           photo_rows(photos, by_id),
                           lambda r: (by_waterbody(r), r["caption"])),
        ISSUES_CSV: render(["waterbody_id", "name", "check", "published", "derived", "note"],
                           issues, lambda r: (by_waterbody(r), r["check"])),
        DESCRIPTIONS_CSV: render(["waterbody_id", "lake_id", "name", "description"],
                                 description_rows(waterbodies, by_id), by_waterbody),
        OUT_OF_SCOPE_CSV: render(["waterbody_id", "name", "species", "records", "zone", "why"],
                                 out_of_scope_rows(waterbodies, details, by_id), by_waterbody),
        WEIGHTS_CSV: render(["waterbody_id", "year", "species", "length_cm", "weight_g", "records"],
                            weight_rows(details),
                            lambda r: (by_waterbody(r), r["year"], r["species"], float(r["length_cm"]))),
        ATLAS_CSV: render(["waterbody_id", "species", "kind", "listing", "agree",
                           "disagree", "confirmed_on", "additional", "source_url"],
                          species_rows(overview, evidence, waterbodies, by_id, by_ats),
                          lambda r: (by_waterbody(r), r["species"])),
    }, {"waterbodies": len(waterbodies), "details": len(details),
        "photos": len(photos), "issues": len(issues), "refused_positions": len(refused)}


def report(built, stats):
    rows = list(csv.DictReader(built[LAKES_CSV].splitlines()))
    def filled(column):
        return sum(1 for r in rows if r[column])
    print(f"{stats['waterbodies']} waterbodies, {stats['details']} stocking records, "
          f"{stats['photos']} photos")
    for column in ("lake_id", "max_depth_m", "mean_depth_m", "surface_area_ha",
                   "zone", "legal_land_description", "latitude", "amenities"):
        print(f"  {filled(column):>4} of {len(rows)} have {column}")
    print(f"\n{stats['issues']} row(s) contradict themselves:")
    for row in csv.DictReader(built[ISSUES_CSV].splitlines()):
        print(f"  {row['check']:<22} {row['name']:<32} {row['note'][:60]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="compare with what is committed and write nothing")
    parser.add_argument("--report", action="store_true",
                        help="coverage, and every contradiction found")
    args = parser.parse_args()

    if not WORKBOOK.exists():
        print(f"{WORKBOOK.relative_to(ROOT)} is not here.")
        return 1

    built, stats = build()

    if args.report:
        report(built, stats)
        return 0

    if args.check:
        drifted = [p for p, text in built.items()
                   if not p.exists() or p.read_text(encoding="utf-8") != text]
        for path in drifted:
            print(f"differs from the workbook: {path.relative_to(ROOT)}")
        if drifted:
            print("\nRun without --check to rewrite them.")
            return 1
        print(f"{len(built)} file(s) match the workbook.")
        return 0

    for path, text in built.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        lines = text.count("\n") - 1
        print(f"wrote {path.relative_to(ROOT)} — {lines} row(s)")
    if stats["refused_positions"]:
        print(f"\n{stats['refused_positions']} position(s) refused for contradicting "
              f"their own land description;")
    print(f"{stats['issues']} note(s) in {ISSUES_CSV.relative_to(ROOT)}")
    print("\nNext: python3 build_history.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
