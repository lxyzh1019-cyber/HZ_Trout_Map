"""How deep each lake is, and what that implies in summer and in winter.

Depth arrives from fetch_lake_pages.py, joined on Alberta's own waterbody id, so
this is an exact join rather than a name match.

Two things depend on it, and both of them have to say nothing at all when the
depth is unknown — which is most of the point of the file.

Stratification. In midsummer a deep lake separates into layers and the trout
sit below the warm top, so a hot surface reading describes water they are
avoiding. Telling someone to fish the thermocline in a lake that has none is
worse than saying nothing: a prairie pothole three metres deep stays mixed all
summer, and eight metres down is the bottom.

Winterkill. Alberta's own guidance names the mechanism — shallow, eutrophic,
and long under ice. Two of those three are measurable here and one is not, so
what this produces is a risk band with its inputs named, not a prediction.
Ice duration is deliberately NOT modelled: across the stocked lakes it varies
far less than depth does, so it would add arithmetic without adding
discrimination. Eutrophy is not available at all and is simply absent, which is
stated rather than quietly assumed away.

The aeration list is the strongest single signal when it is present, and it
cuts both ways: a lake is aerated because the province expects it to winterkill,
and it is less likely to winterkill because it is aerated. Both halves are
reported.
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEPTHS_CSV = ROOT / "data" / "raw" / "mywildalberta_lakes.csv"
AERATED_CSV = ROOT / "data" / "raw" / "aca_aerated_lakes.csv"

# Below this, wind keeps an Alberta lake mixed through the summer and there is
# no cooler layer to drop to.
MIN_STRATIFYING_DEPTH_M = 5.0
# Shallow enough that a long winter under ice and snow can strip the oxygen.
SHALLOW_M = 3.0
MODERATE_M = 5.0

# Where a mean depth can be guessed at from a maximum, and how loosely.
#
# Measured over the 55 lakes in the 2026-09-11 stocking map that publish both
# depths. The ratio of mean to maximum runs p10 0.39, median 0.64, p90 0.97,
# and a band drawn at those outer percentiles contains 78% of them. Held out
# one lake at a time, the median ratio misses by 25% of the true mean, and by
# 70% for the worst tenth.
#
# So this is published as a band and never as a number, and the band is simply
# a restatement of that spread rather than a model of anything. It is wide
# because the underlying relationship is weak, and the width is the honest part.
#
# Splitting the ratio at 6 m does measurably better — 20% median, 56% at p90,
# 82% coverage — but the 6 m threshold was chosen by eye from these same 55
# lakes, and one side of it holds only 20 of them. That is fitting the split to
# the sample, so it is recorded here and not used.
MEAN_MAX_RATIO_LOW = 0.39
MEAN_MAX_RATIO_HIGH = 0.97
MEAN_ESTIMATE_BASIS = ("55 lakes publishing both depths, MyWildAlberta "
                       "stocking map 2026-09-11")
MEAN_ESTIMATE_COVERS = 0.78


def load_depths():
    if not DEPTHS_CSV.exists():
        return {}
    out = {}
    with DEPTHS_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            wid = (row.get("waterbody_id") or "").strip()
            if not wid:
                continue
            def number(key):
                raw = (row.get(key) or "").strip()
                try:
                    return float(raw)
                except ValueError:
                    return None
            out[wid] = {
                "max_depth_m": number("max_depth_m"),
                "mean_depth_m": number("mean_depth_m"),
                "surface_area_ha": number("surface_area_ha"),
                "stated_unavailable": (row.get("depth_stated_unavailable") or "").strip() == "yes",
            }
    return out


# Evidence strong enough to lower a winterkill band: Alberta's own lake
# description, or ACA's published roster with the region agreeing. A photograph
# is deliberately not on this list — it shows that equipment existed when the
# picture was taken, not that the programme runs now, and the export's own notes
# say the operating status was never verified. Marking a lake aerated makes it
# read as safer than it is, so that is the one direction to be careful in.
APPLIED_EVIDENCE = {"stated", "published_list"}


def load_aerated():
    """Waterbodies the province aerates, and the ones only a photo suggests.

    Returns two sets: the ones whose evidence may move a risk band, and the
    ones that are recorded and shown but never applied.
    """
    if not AERATED_CSV.exists():
        return set(), set()
    applied, noted = set(), set()
    with AERATED_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "waterbody_id" not in (reader.fieldnames or []):
            return set(), set()
        for row in reader:
            wid = (row.get("waterbody_id") or "").strip()
            if not wid:
                continue
            # An older file with no confidence column is Alberta's stated list.
            confidence = (row.get("confidence") or "stated").strip()
            (applied if confidence in APPLIED_EVIDENCE else noted).add(wid)
    return applied, noted


def stratification(max_depth_m, surface_area_ha):
    """Whether the lake can layer at all, and roughly where.

    Returns None when the depth is unknown, and the caller must then show no
    depth advice whatsoever. Sending someone to eight metres in three metres of
    water is a real harm, and "probably deep enough" is not a defence.
    """
    if max_depth_m is None:
        return None
    if max_depth_m < MIN_STRATIFYING_DEPTH_M:
        return {"stratifies": False, "max_depth_m": max_depth_m,
                "why": "shallow enough that wind keeps it mixed all summer"}
    # A band, never a single number: this stands in for a temperature profile
    # nobody has measured.
    #
    # The band is set by FETCH — how far the wind can blow across the lake, for
    # which surface area is the usable stand-in — and not by a fraction of the
    # maximum depth. Depth sets where the bottom is, not where the layer forms:
    # a first attempt here took a quarter of max depth and gave a 7.6 m lake and
    # a 12 m lake the same 3-5 m band, with the deeper lake's thermocline placed
    # shallower than it belongs. Wind mixes the top of a big lake deeper than
    # the top of a small one at the same depth.
    if not surface_area_ha:
        lower, upper = 4, 7          # the middling case, said plainly
    elif surface_area_ha < 50:
        lower, upper = 3, 5
    elif surface_area_ha < 500:
        lower, upper = 4, 7
    else:
        lower, upper = 6, 10

    # The layer cannot be below the bottom. Leave a metre of water under it,
    # and if that leaves no room the lake does not usefully stratify after all.
    ceiling = max_depth_m - 1
    upper = min(upper, ceiling)
    if upper - lower < 1:
        return {"stratifies": False, "max_depth_m": max_depth_m,
                "why": "not deep enough for a layer to form clear of the bottom"}
    return {"stratifies": True, "max_depth_m": max_depth_m,
            "band_m": [round(lower), round(upper)],
            "why": "deep enough to layer in midsummer"}


def mean_depth(max_depth_m, mean_depth_m):
    """What can be said about the average depth, and how firmly.

    Four answers, and they are deliberately different shapes so that a measured
    depth and a guessed one can never be confused by reading one field:

      published    Alberta prints a mean depth.           {"m": 4.0}
      contradicted it prints one deeper than the maximum. {"why": ...}
      estimated    only a maximum is published.           {"range_m": [lo, hi]}
      None         neither is published, so nothing.

    An estimate is never returned under the key a measurement uses. Nothing
    here reaches stratification() or winterkill(): both take the measured
    maximum only, and this cannot change a word of the advice they give.
    """
    if mean_depth_m is not None:
        if max_depth_m is not None and mean_depth_m > max_depth_m:
            # Castor Eastside Trout Pond publishes 22 m against a maximum of
            # 7 m on a one-hectare pond. The maximum is the plausible half, so
            # it is kept and this is dropped. Swapping them is not a repair,
            # only a different guess, and a pond that size is neither.
            return {"source": "contradicted",
                    "why": f"the published mean of {mean_depth_m:g} m is deeper "
                           f"than the published maximum of {max_depth_m:g} m"}
        return {"m": mean_depth_m, "source": "mywildalberta"}

    if max_depth_m is None:
        return None

    low = round(max_depth_m * MEAN_MAX_RATIO_LOW, 1)
    high = round(max_depth_m * MEAN_MAX_RATIO_HIGH, 1)
    if high >= max_depth_m:
        # The band cannot reach the bottom: a lake whose average depth equals
        # its maximum is a lake with vertical sides.
        high = round(max_depth_m - 0.1, 1)
    if low < 0.5 or high <= low:
        return None
    return {"range_m": [low, high], "source": "estimated",
            "from_max_depth_m": max_depth_m,
            "method": "the maximum depth times the range of mean-to-maximum "
                      "ratios Alberta's own published pairs show",
            "basis": MEAN_ESTIMATE_BASIS, "covers": MEAN_ESTIMATE_COVERS}


def winterkill(max_depth_m, aerated, aeration_known):
    """A risk band with its reasons, or None when depth is unknown.

    Not a prediction. Depth and aeration are real inputs; eutrophy is not
    available and ice duration barely discriminates between these lakes, so the
    answer is a band and the missing pieces are named.
    """
    if max_depth_m is None:
        return None
    reasons = []
    if max_depth_m < SHALLOW_M:
        level = "high"
        reasons.append(f"only {max_depth_m:g} m at its deepest")
    elif max_depth_m < MODERATE_M:
        level = "moderate"
        reasons.append(f"{max_depth_m:g} m at its deepest")
    else:
        level = "low"
        reasons.append(f"{max_depth_m:g} m deep")

    if aerated:
        # Both halves are true and both matter.
        reasons.append("aerated by the province, which both marks it as a lake "
                       "expected to winterkill and makes it less likely to")
        level = {"high": "moderate", "moderate": "low", "low": "low"}[level]
    elif aeration_known:
        reasons.append("not on the aerated list")

    return {"level": level, "reasons": reasons,
            "inputs": {"depth": True, "aeration": bool(aeration_known),
                       "eutrophy": False, "ice_duration": False}}


def join_id(lake):
    """Alberta's id for this lake, however the repo came by it.

    A lake minted from a land description has no waterbody id of its own, so
    the exact join every other part of this pipeline relies on cannot see it —
    which is why eight lakes had no depth despite Alberta publishing one. The
    id recorded from a confirmed land-description match stands in, and is kept
    in its own field so it can never be mistaken for the report's own.
    """
    return str(lake.get("waterbody_id") or lake.get("published_waterbody_id") or "")


def build(lakes):
    """Per-lake depth, stratification and winterkill, keyed as the app keys them."""
    depths = load_depths()
    aerated, aeration_noted = load_aerated()

    out, with_depth, unavailable = {}, 0, 0
    mean_published, mean_estimated, mean_contradicted = 0, 0, 0
    for lake in lakes:
        wid = join_id(lake)
        key = lake.get("lake_id") or lake.get("ats")
        if not key:
            continue
        found = depths.get(wid)
        if not found:
            continue
        depth = found["max_depth_m"]
        if depth is not None:
            with_depth += 1
        elif found["stated_unavailable"]:
            unavailable += 1
        # Aeration is known per lake, not per file. Alberta publishes the
        # aerated ones and says nothing whatsoever about the rest, so for any
        # lake off the list the status is unknown, not negative. The flag used
        # to be set once for the whole run, which meant that the moment an
        # aerated list existed at all, every one of the other 300-odd lakes was
        # told "not on the aerated list" — which reads as "not aerated". The
        # export's own notes are explicit: not stated does not mean no.
        is_aerated = wid in aerated
        aeration_known = is_aerated
        average = mean_depth(depth, found["mean_depth_m"])
        entry = {
            "max_depth_m": depth,
            "mean_depth": average,
            "surface_area_ha": found["surface_area_ha"],
            "source": "mywildalberta stocking map export 2026-09-11",
            "depth_stated_unavailable": found["stated_unavailable"],
            "stratification": stratification(depth, found["surface_area_ha"]),
            "winterkill": winterkill(depth, is_aerated, aeration_known),
        }
        if average:
            source = average.get("source")
            if source == "mywildalberta":
                mean_published += 1
            elif source == "estimated":
                mean_estimated += 1
            elif source == "contradicted":
                mean_contradicted += 1
        if is_aerated:
            entry["aerated"] = True
        elif wid in aeration_noted:
            # Shown beside the lake so the photograph is not lost, and kept
            # out of the risk band because a photograph cannot carry it.
            entry["aeration_photo_only"] = True
        out[key] = entry
    return out, {"with_depth": with_depth, "stated_unavailable": unavailable,
                 "aerated": len(aerated), "aeration_photo_only": len(aeration_noted),
                 "mean_published": mean_published, "mean_estimated": mean_estimated,
                 "mean_contradicted": mean_contradicted, "rows": len(depths)}


def write(lakes, data_dir):
    built, stats = build(lakes)
    if not built:
        return None
    (Path(data_dir) / "lake_depth.json").write_text(
        json.dumps({"lakes": built,
                    "source": "MyWildAlberta stocking map, exported 2026-09-11",
                    "joined_on": "Alberta waterbody id"},
                   indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")
    return stats
