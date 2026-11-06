"""Which fish are recorded in each water, for Species mode (Build 5 Stage 3b).

The 2026 guide gives every water in a zone the same species list, which is why
trout ponds there show walleye and pike. The 2021 guide's waterbody tables
still named species water by water: in its own words, "an empty cell indicates
the species is not likely present at that waterbody". The owner chose to use that
edition FOR SPECIES PRESENCE ONLY (2026-11-06): no 2021 season, limit or bait
rule is kept here or shown anywhere. The rules in the app stay the 2026 guide's.

Usage (the 2021 guide is not kept in the repository, 28 MB):

    cd scripts && python3 species_presence.py <alberta-guide-sportfishing-regulations-2021.pdf>

Sources for each water and species, any of:
    guide2021   a non-empty cell in the water's own row of the 2021 tables,
                matched by name within the fish management zone, with
                regulations.py's matcher and confidence (and data/regs_aliases.csv)
    stocked     a stocking record (data/lakes_*.json)
    reports     anglers' reports gathered in data/lake_profile.json (Anglers Atlas)

Writes data/species_presence.json and data/species_review.csv (names too close
to call, which get no 2021 claim).
"""

import csv
import glob
import hashlib
import json
import sys
from pathlib import Path

import pdfplumber

import regulations as rg

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "species_presence.json"
REVIEW = DATA / "species_review.csv"
GUIDE_URL = ("https://open.alberta.ca/dataset/dbf392f4-266f-4947-adc0-fa4bdf4e2c9c/resource/"
             "a4af881c-b069-41c1-84bc-a339f0880e30/download/alberta-guide-sportfishing-regulations-2021.pdf")
# The species Species mode can pick (trout is today's model and needs no list).
MODE_SPECIES = ("WALL", "BURB", "LKWH", "MNWH")


def app_waters():
    """key -> {name, zone, kind} for every lake, water not stocked, and river stretch."""
    out = {}
    for f in sorted(glob.glob(str(DATA / "lakes_20*.json"))):
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        for x in (doc["lakes"] if isinstance(doc, dict) else doc):
            key = x.get("lake_id") or x.get("ats")
            if key:
                out[key] = {"name": x.get("name") or "", "zone": x.get("zone"), "kind": "lake"}
    for x in json.loads((DATA / "waters_unstocked.json").read_text(encoding="utf-8"))["lakes"]:
        out.setdefault(x["lake_id"], {"name": x.get("name") or "", "zone": x.get("zone"), "kind": "lake"})
    for x in json.loads((DATA / "rivers.json").read_text(encoding="utf-8"))["stretches"]:
        out[x["lake_id"]] = {"name": x.get("name") or "", "zone": x.get("zone"), "kind": "river"}
    return out


def stocked_species():
    out = {}
    for f in sorted(glob.glob(str(DATA / "lakes_20*.json"))):
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        for x in (doc["lakes"] if isinstance(doc, dict) else doc):
            key = x.get("lake_id") or x.get("ats")
            codes = set(x.get("species_set") or []) | {s.get("species") for s in x.get("stockings") or [] if s.get("species")}
            if key and codes:
                out.setdefault(key, set()).update(codes)
    return out


def reported_species():
    lakes = json.loads((DATA / "lake_profile.json").read_text(encoding="utf-8"))["lakes"]
    out = {}
    for key, v in lakes.items():
        seen = (v or {}).get("confirmed") or {}
        codes = {s["code"] for s in seen.get("species", []) if s.get("code") and s.get("agree", 0) > s.get("disagree", 0)}
        if codes:
            out[key] = codes
    return out


def guide_species(tables, waters):
    """key -> species codes from the water's own 2021 row; and the names too close to call."""
    aliases = rg.load_aliases()
    found, review = {}, []
    for key in sorted(waters):
        w = waters[key]
        bucket = tables.get(w["zone"] or "", {}).get("lakes" if w["kind"] == "lake" else "rivers", {})
        if not bucket:
            continue
        settled = aliases.get(key)
        if settled and settled["regulation_name"].strip() in bucket:
            best, score = settled["regulation_name"].strip(), 1.0
        else:
            best, score = rg._best_match(w["name"], list(bucket))
        if best and score >= rg.CONFIDENT:
            found[key] = {"row": best, "species": set(bucket[best]["species"]), "page": bucket[best].get("page")}
        elif best and score >= rg.CLEARLY_ABSENT:
            review.append({"water": w["name"], "key": key, "zone": w["zone"], "closest_2021": best, "score": "%.2f" % score})
    return found, review


def build(pdf_path):
    pdf_path = Path(pdf_path)
    sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    with pdfplumber.open(str(pdf_path)) as pdf:
        tables = rg.read_tables(pdf)
    waters = app_waters()
    guide, review = guide_species(tables, waters)
    stocked, reports = stocked_species(), reported_species()
    out, counts = {}, {c: 0 for c in MODE_SPECIES}
    for key in sorted(waters):
        rec = {}
        for code in MODE_SPECIES:
            srcs = []
            if code in guide.get(key, {}).get("species", ()):
                srcs.append("guide2021")
            if code in stocked.get(key, ()):
                srcs.append("stocked")
            if code in reports.get(key, ()):
                srcs.append("reports")
            if srcs:
                rec[code] = srcs
                counts[code] += 1
        if rec:
            out[key] = rec
    doc = {
        "about": "Which of walleye, burbot, lake whitefish and mountain whitefish are recorded in each water. "
                 "For species presence only: no rule from the 2021 guide is used.",
        "sources": {
            "guide2021": {"title": "Alberta Guide to Sportfishing Regulations 2021 (waterbody tables; an empty cell: species not likely present)",
                          "url": GUIDE_URL, "sha256": sha},
            "stocked": "Alberta fish stocking reports (data/lakes_*.json)",
            "reports": "Anglers' reports, Anglers Atlas (data/lake_profile.json)",
        },
        "matched_2021_rows": len(guide), "waters": len(waters), "counts": counts, "presence": out,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    with REVIEW.open("w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["water", "key", "zone", "closest_2021", "score"])
        wr.writeheader()
        wr.writerows(review)
    print("%d waters, %d matched to a 2021 row, %d too close to call; recorded: %s -> %s (%d kB)"
          % (len(waters), len(guide), len(review), counts, OUT.relative_to(ROOT), OUT.stat().st_size // 1024))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    build(sys.argv[1])
