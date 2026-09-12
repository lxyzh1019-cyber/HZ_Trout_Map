"""What Alberta says about a lake, beyond how deep it is and what swims in it.

Amenities, the paragraph the province writes, and the photographs it has taken.
Joined on Alberta's own waterbody id, the same exact join depth.py uses, and
keyed the way the app keys its lakes so a lookup is one dictionary access.

Why this is not in the year files
---------------------------------
index.html merges lakes across every selected year and lets a later year
overwrite a scalar field. None of this changes from year to year, so putting it
there would write the same prose into sixteen files and make which copy you see
depend on which years happen to be selected. It is a property of the lake, so
it lives in one file keyed by lake.

Amenity facets
--------------
Alberta publishes 48 distinct amenity tokens and they are hierarchical:
"Trails Hiking" and "Trails Cross-Country Ski" both live under "Trails",
"Paddling Canoe" under "Paddling". A filter for Trails has to match a lake that
only says Trails Hiking, so every child is rolled up into its parent.

Only parents and standalone tokens are offered as filters. A child is always
redundant after the rollup — every lake with Paddling Canoe also has Paddling,
so the two have identical counts and offering both is offering the same filter
twice under two names.

Absence is not absence
----------------------
Ninety-five mapped lakes have no amenities cell at all. That is Alberta not
saying, which is not the same as a lake with no toilet. They are stored as null
rather than an empty list, so the app can tell the two apart and say "known to
have" rather than "has".
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
LAKES_CSV = ROOT / "data" / "raw" / "mywildalberta_lakes.csv"
DESCRIPTIONS_CSV = ROOT / "data" / "raw" / "mywildalberta_descriptions.csv"
PHOTOS_CSV = ROOT / "data" / "raw" / "mywildalberta_photos.csv"
CONFIRMED_CSV = ROOT / "data" / "raw" / "lake_species_confirmed.csv"

# A token that begins with one of these and a space is a narrower kind of it.
PARENT_FACETS = ("Trails", "Paddling", "Camping", "Day Use", "Boating",
                 "Fishing Access", "Sports", "Swimming")

# Two labels for one thing. Alberta uses both; a filter should not.
SYNONYMS = {"Washrooms": "Toilets"}

# Below this, a facet is worth showing on a lake and not worth filtering by:
# a three-lake checkbox is a novelty, not a way through 345 lakes.
FILTER_FLOOR = 15

# The ones that decide whether a fishing trip works, before the ones that
# decide whether a camping trip does. Anything unlisted follows, by count.
FISHING_FIRST = ("Boat Launch", "Dock/Pier", "Fish Cleaning", "Toilets", "Camping")


def parent_of(token):
    for parent in PARENT_FACETS:
        if token.startswith(parent + " "):
            return parent
    return None


def facets_for(tokens):
    """Every facet a lake matches, its parents included."""
    out = set()
    for token in tokens:
        token = SYNONYMS.get(token, token)
        out.add(token)
        parent = parent_of(token)
        if parent:
            out.add(parent)
    return out


def load_rows(path, key="lake_id"):
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {row[key]: row for row in csv.DictReader(handle) if row.get(key)}


def load_confirmed():
    """What is reported to actually swim in a lake, as opposed to what was put in.

    The two are not the same question and this map could only answer the second
    one. Stocking records say what a hatchery delivered; they say nothing about
    the pike that got in on their own, and nothing about whether last decade's
    trout are still there.

    Catch limits are not an answer either, and reading them as one is the trap.
    Cow Lake's regulation row lists a walleye limit, and 64 of the 65
    site-specific rows in the guide carry the identical pike-walleye-perch
    triplet: that is boilerplate covering species that may or may not be
    present, not a survey. Independent reports of Cow Lake list rainbow, brown,
    pike and perch, and no walleye at all.

    So presence gets its own source, with a URL per lake so any row can be
    checked. Angler's Atlas is an angling site rather than the province, and
    the app says so rather than passing it off as a government fact.

    Coverage is partial and a missing lake means NOT CHECKED. It must never
    render as a lake with no fish in it.
    """
    if not CONFIRMED_CSV.exists():
        return {}
    out = {}
    with CONFIRMED_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            codes = [c.strip() for c in (row.get("species") or "").split(";") if c.strip()]
            if not row.get("lake_id") or not codes:
                continue
            out[row["lake_id"]] = {
                "species": sorted(set(codes)),
                "source": row.get("source") or None,
                "url": row.get("source_url") or None,
                "retrieved": row.get("retrieved") or None,
            }
    return out


def load_photos():
    if not PHOTOS_CSV.exists():
        return {}
    out = defaultdict(list)
    with PHOTOS_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("lake_id"):
                out[row["lake_id"]].append({"caption": row["caption"], "url": row["url"]})
    return out


def build(lakes):
    """Per-lake amenities, prose and photo count, keyed as the app keys them."""
    if not LAKES_CSV.exists():
        return None, None, {}
    site = load_rows(LAKES_CSV)
    prose = load_rows(DESCRIPTIONS_CSV)
    photos = load_photos()
    confirmed = load_confirmed()

    profiles, gallery = {}, {}
    counts = defaultdict(int)
    with_amenities = with_description = with_photos = with_confirmed = 0

    for lake in lakes:
        key = lake.get("lake_id") or lake.get("ats")
        if not key:
            continue
        row = site.get(key)
        entry = {}

        raw = (row or {}).get("amenities", "")
        if raw:
            tokens = [t.strip() for t in raw.split(";") if t.strip()]
            entry["amenities"] = sorted(tokens)
            entry["facets"] = sorted(facets_for(tokens))
            for facet in entry["facets"]:
                counts[facet] += 1
            with_amenities += 1
        else:
            # Alberta said nothing. Not the same as a lake with nothing.
            entry["amenities"] = None
            entry["facets"] = None

        text = (prose.get(key) or {}).get("description", "")
        if text:
            entry["description"] = text
            with_description += 1

        district = (row or {}).get("region", "")
        if district:
            entry["district"] = district

        seen = confirmed.get(key)
        if seen:
            entry["confirmed"] = seen
            with_confirmed += 1

        shots = photos.get(key) or []
        if shots:
            entry["photo_count"] = len(shots)
            gallery[key] = shots
            with_photos += 1

        if any(v is not None for k, v in entry.items() if k != "facets"):
            profiles[key] = entry

    filterable = [f for f, n in counts.items() if n >= FILTER_FLOOR and not parent_of(f)]
    order = {name: i for i, name in enumerate(FISHING_FIRST)}
    filterable.sort(key=lambda f: (order.get(f, len(order)), -counts[f], f))

    return (
        {"lakes": profiles,
         "facets": [{"name": f, "lakes": counts[f]} for f in filterable],
         "source": "MyWildAlberta stocking map, exported 2026-09-11",
         "joined_on": "Alberta waterbody id"},
        {"lakes": gallery,
         "source": "MyWildAlberta stocking map, exported 2026-09-11",
         "note": ("Photographs stay on Alberta's own server. They are linked, "
                  "never copied, and they need a connection.")},
        {"with_amenities": with_amenities, "with_description": with_description,
         "with_photos": with_photos, "photos": sum(len(v) for v in gallery.values()),
         "with_confirmed": with_confirmed, "facets": len(filterable)},
    )


def write(lakes, data_dir):
    profiles, gallery, stats = build(lakes)
    if not profiles:
        return None
    out = Path(data_dir)
    (out / "lake_profile.json").write_text(
        json.dumps(profiles, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")
    (out / "lake_photos.json").write_text(
        json.dumps(gallery, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")
    return stats
