"""Boating rules for the lakes with a 3D depth model.

Two sources, read as data:

1. Transport Canada, TP 15587E "Schedules of the Vessel Operation Restriction
   Regulations", 2nd edition, April 2026 — the federal law on where boats,
   motors, speeds and towing are restricted. Its Alberta rows give a name, a
   local name and an Alberta Land Titles location (sections-township-range-
   meridian). Licence: Transport Canada allows copying for personal and public
   non-commercial use, with credit and not as the official version.

       Schedule 1  no vessels (on Alberta lakes almost always "as indicated by
                   signs": swimming areas and the like)
       Schedule 2  no electric or power-driven vessels (paddle only)
       Schedule 3  electric only, at most 7.5 kW
       Schedule 5  speed limit, km/h
       Schedule 6  no towing (water skis, tubes)
       Schedule 7  no wake surfing

2. MyWildAlberta lake pages (data/raw/mywildalberta_descriptions.csv and the
   "Boating Motorized" amenity), which state a rule for some lakes in words.

A Transport Canada row counts for a lake only when BOTH the name (or local
name) and the township-range-meridian agree with the AGS outline of that lake:
Alberta has many Spring, Star and Goose Lakes. Transport Canada wins when both
sources speak, because it is the law; the file keeps both.

Usage:

    python -I scripts/boating_rules.py --fetch   # save the Alberta rows
    python -I scripts/boating_rules.py           # write data/boating_rules.json
"""

import argparse
import csv
import datetime
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from depth_charts import norm  # noqa: E402

ROOT = Path(__file__).parent.parent
RAW_TC = ROOT / "data" / "raw" / "tp15587e_alberta.json"
GRIDS = ROOT / "data" / "depth_grids" / "index.json"
BOUNDS = ROOT / "data" / "raw" / "ags_bathymetry" / "levels_boundaries.json"
AGS_INDEX = ROOT / "data" / "raw" / "ags_bathymetry" / "index.json"
MWA_TEXT = ROOT / "data" / "raw" / "mywildalberta_descriptions.csv"
MWA_LAKES = ROOT / "data" / "raw" / "mywildalberta_lakes.csv"
OUT = ROOT / "data" / "boating_rules.json"
TC_URL = ("https://tc.canada.ca/en/marine-transportation/marine-safety/boating-safety/"
          "schedules-vessel-operation-restriction-regulations-2nd-edition-april-2026")
TC_SOURCE = "Transport Canada, TP 15587E (2nd edition, April 2026)"
TC_NOTE = "Not the official version. Reproduced with permission for non-commercial use."


def _clean(x):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def fetch():
    import urllib.request
    req = urllib.request.Request(TC_URL, headers={"User-Agent": "HZ-Trout-Map data build"})
    page = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "ignore")
    rows, schedule = [], None
    for m in re.finditer(r"<h[1-4][^>]*>.*?</h[1-4]>|<table.*?</table>", page, re.S):
        x = m.group(0)
        if x.startswith("<h"):
            s = re.match(r"Schedule (\d+(?:\.\d+)?)", _clean(x))
            if s:
                schedule = s.group(1)
            continue
        if "Alberta Land Titles" not in x:
            continue
        trs = re.findall(r"<tr.*?</tr>", x, re.S)
        head = [_clean(c).lower() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", trs[0], re.S)]
        speed_col = next((i for i, h in enumerate(head) if "speed" in h), None)
        for tr in trs[1:]:
            c = [_clean(v) for v in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
            if len(c) < 4:
                continue
            row = {"schedule": schedule, "name": c[1], "local": c[2], "location": c[3]}
            if speed_col is not None and speed_col < len(c):
                row["speed_kmh"] = c[speed_col]
            rows.append(row)
    RAW_TC.write_text(json.dumps({"source": TC_SOURCE, "url": TC_URL,
                                  "retrieved": datetime.date.today().isoformat(),
                                  "licence": "Transport Canada: personal and public non-commercial use, "
                                             "credit Transport Canada, not the official version",
                                  "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(len(rows), "Alberta rows saved")


def tc_places(location):
    """'23,25-8-3-W4', '61-11,12-W5' or '39-1-2-W5' → {(twp, rge, mer), …}.

    Four parts are read both ways — sections-township-range ('23,25-8-3') and
    township-range-range ('39-1-2', a lake across two ranges) — because the
    list uses both; the name must match as well, so the extra reading is safe."""
    out = set()

    def add(twps, rges, mer):
        for t in twps.split(","):
            for r in rges.split(","):
                if t.strip().isdigit() and r.strip().isdigit():
                    out.add((int(t), int(r), mer))

    for part in re.split(r"\s+(?:and|to)\s+|;", location):
        p = [x.strip() for x in part.strip().split("-")]
        if len(p) < 3 or not re.match(r"W[456]$", p[-1]):
            continue
        add(p[-3], p[-2], p[-1])
        if len(p) >= 4:
            add(p[-4], p[-3] + "," + p[-2], p[-1])
    return out


def row_key(name):
    """Lake name of a list row without its qualifier: "Sylvan Lake, as
    indicated by signs" and "That part of Wabamun Lake that is …" both name
    the lake before the comma or the word after "lake"."""
    n = re.sub(r"(?i)^that part of\s+", "", name or "")
    n = re.split(r",", n)[0]
    m = re.match(r"(?i)(.*?\b(?:lakes?|reservoir|pond))\b", n)
    return norm(m.group(1) if m else n)


def ags_places(ats_list):
    """['005-03-W5, 035-07-W5'] → {(5, 3, 'W5'), (35, 7, 'W5')}."""
    out = set()
    for s in ats_list or []:
        for t, r, m in re.findall(r"(\d+)-(\d+)-(W[456])", s or ""):
            out.add((int(t), int(r), m))
    return out


def mwa_rule(text):
    """Motor rule stated in words on MyWildAlberta, or None."""
    t = (text or "").lower()
    if re.search(r"electric", t) or re.search(r"gas[- ]powered motors are (prohibited|not permitted)|no gas", t):
        if re.search(r"non-motori[sz]ed or electric|electric or non-motori[sz]ed|electric motors? only|electric[- ]powered|"
                     r"electric motor or hand|gas[- ]powered motors are|no gas|electric powered", t):
            return "electric"
    if re.search(r"no motori[sz]ed boats|motori[sz]ed boats are not permitted|non-motori[sz]ed boats only|"
                 r"canoeing and non-motori[sz]ed boats", t):
        return "none"
    return None


def load_mwa():
    text, motorized = {}, set()
    with open(MWA_TEXT, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            text[r["lake_id"]] = r.get("description") or ""
    with open(MWA_LAKES, encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd, None)
        for r in rd:
            line = ",".join(r)
            m = re.search(r"\bwb\d+\b", line) or (re.match(r"\d+", r[0]) and re.match(r"(\d+)", r[0]))
            if "Boating Motorized" in line and m:
                wid = m.group(0) if m.group(0).startswith("wb") else "wb" + m.group(1)
                motorized.add(wid)
    return text, motorized


def build():
    tc = json.loads(RAW_TC.read_text(encoding="utf-8"))
    grids = json.loads(GRIDS.read_text(encoding="utf-8"))
    bounds = json.loads(BOUNDS.read_text(encoding="utf-8"))
    ags = json.loads(AGS_INDEX.read_text(encoding="utf-8"))
    text, motorized = load_mwa()
    lakes, unmatched_names = {}, []
    for wid, g in sorted(grids["lakes"].items()):
        name = g["name"]
        places = ags_places(bounds[ags[wid]["contour_dig"]]["ats"])
        key = norm(name)
        rule = {"motor": None, "kw_max": None, "speed_kmh": None, "speed_kmh_signed": None, "signed_no_boat_zones": False,
                "no_boats": False, "no_towing": False, "no_wake_surf": False, "sources": [], "tc_rows": []}
        for row in tc["rows"]:
            if key not in (row_key(row["name"]), row_key(row["local"])):
                continue
            if not (tc_places(row["location"]) & places):
                unmatched_names.append((name, row["schedule"], row["location"]))
                continue
            s = row["schedule"]
            rule["tc_rows"].append({"schedule": s, "name": row["name"], "local": row["local"],
                                    "location": row["location"], **({"speed_kmh": row["speed_kmh"]} if "speed_kmh" in row else {})})
            partial = "as indicated by signs" in row["name"] or row["name"].lower().startswith("that part")
            if s == "1":
                if partial:
                    rule["signed_no_boat_zones"] = True
                else:
                    rule["no_boats"] = True
            elif s == "2" and not partial:
                rule["motor"] = "none"
            elif s == "3" and not partial and rule["motor"] != "none":
                rule["motor"], rule["kw_max"] = "electric", 7.5
            elif s == "5":
                try:
                    rule["speed_kmh_signed" if partial else "speed_kmh"] = int(row.get("speed_kmh"))
                except (TypeError, ValueError):
                    pass
            elif s == "6":
                rule["no_towing"] = True
            elif s == "7":
                rule["no_wake_surf"] = True
        if rule["tc_rows"]:
            rule["sources"].append(TC_SOURCE)
        stated = mwa_rule(text.get(wid))
        if stated is None and wid in motorized:
            stated = "allowed"
        if stated:
            rule["mywildalberta"] = stated
            rule["sources"].append("MyWildAlberta lake page")
            # Transport Canada lists only limits, so "no motor row" agrees with
            # any MyWildAlberta wording; it is overruled only by a TC motor row.
            if rule["motor"] is None:
                rule["motor"] = stated
            if rule["motor"] != stated:
                rule["differs"] = True
        lakes[wid] = rule
    OUT.write_text(json.dumps({"schema": 1, "sources": {"tc": {"name": TC_SOURCE, "url": tc["url"],
                                                               "retrieved": tc["retrieved"], "note": TC_NOTE},
                                                        "mywildalberta": "MyWildAlberta lake pages, saved in data/raw"},
                               "lakes": lakes}, indent=1, sort_keys=True), encoding="utf-8")
    have = sum(1 for r in lakes.values() if r["sources"])
    print("%d of %d lakes have a boating rule; %d name matches dropped for location" % (
        have, len(lakes), len(unmatched_names)))
    for n in unmatched_names:
        print("  dropped:", n)
    return lakes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fetch", action="store_true")
    if ap.parse_args().fetch:
        fetch()
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
