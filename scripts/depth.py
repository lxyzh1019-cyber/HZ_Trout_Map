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
                "surface_area_ha": number("surface_area_ha"),
                "stated_unavailable": (row.get("depth_stated_unavailable") or "").strip() == "yes",
                "page_name": (row.get("page_name") or "").strip(),
            }
    return out


def load_aerated():
    """Waterbodies the province aerates, if that list has been collected."""
    if not AERATED_CSV.exists():
        return set()
    with AERATED_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        field = "waterbody_id" if "waterbody_id" in (reader.fieldnames or []) else None
        if not field:
            return set()
        return {(row.get(field) or "").strip() for row in reader if row.get(field)}


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


def build(lakes):
    """Per-lake depth, stratification and winterkill, keyed as the app keys them."""
    depths = load_depths()
    aerated = load_aerated()
    aeration_known = bool(aerated)

    out, with_depth, unavailable = {}, 0, 0
    for lake in lakes:
        wid = str(lake.get("waterbody_id") or "")
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
        entry = {
            "max_depth_m": depth,
            "surface_area_ha": found["surface_area_ha"],
            "source": "mywildalberta",
            "depth_stated_unavailable": found["stated_unavailable"],
            "stratification": stratification(depth, found["surface_area_ha"]),
            "winterkill": winterkill(depth, wid in aerated, aeration_known),
        }
        if wid in aerated:
            entry["aerated"] = True
        out[key] = entry
    return out, {"with_depth": with_depth, "stated_unavailable": unavailable,
                 "aeration_known": aeration_known, "rows": len(depths)}


def write(lakes, data_dir):
    built, stats = build(lakes)
    if not built:
        return None
    (Path(data_dir) / "lake_depth.json").write_text(
        json.dumps({"lakes": built, "source": "MyWildAlberta stocked lake pages",
                    "joined_on": "Alberta waterbody id"},
                   indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")
    return stats
