"""
apply_review.py — turn your answers in data/link_review.csv into permanent
aliases, so the same question is never asked twice.

    python3 apply_review.py            # apply answers
    python3 apply_review.py --list     # show what is still unanswered

How to answer
-------------
Open data/link_review.csv. Each row is one report name the linker would not
guess at, with up to three candidate lakes and how far each sits from where
the report puts it. Fill in the `lake_id` column with either:

    wb6608      the id of the right lake, copied from a candidate column
    NEW         this really is a lake we have never recorded before
    SKIP        leave these rows out of the history entirely

Then run this. Your answer is written to data/lake_aliases.csv and applied on
every future build, including future years, so a name Alberta keeps
misspelling is settled once and stays settled.
"""

import argparse
import csv
import sys
from pathlib import Path

from registry import ALIASES_PATH, REVIEW_PATH, load_registry, normalize_name

VALID_KINDS = ("name", "ats", "new", "skip")


def read_answers():
    if not REVIEW_PATH.exists():
        print(f"No review file at {REVIEW_PATH}. Run build_history.py first.")
        return None
    with open(REVIEW_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def existing_aliases():
    rows = []
    if ALIASES_PATH.exists():
        with open(ALIASES_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="show unanswered questions")
    args = ap.parse_args()

    answers = read_answers()
    if answers is None:
        return 1

    answered = [r for r in answers if (r.get("lake_id") or "").strip()]
    blank = [r for r in answers if not (r.get("lake_id") or "").strip()]

    if args.list:
        print(f"{len(blank)} unanswered of {len(answers)}:\n")
        for r in blank:
            print(f"  {r['year']}  {r['report_name']}  [{r['ats'] or 'no land description'}]")
            print(f"      {r['why']}")
            for key in ("candidate_1", "candidate_2", "candidate_3"):
                if r.get(key):
                    print(f"      -> {r[key]}")
        return 0

    if not answered:
        print(f"Nothing answered yet. {len(answers)} question(s) waiting in {REVIEW_PATH}.")
        print("Fill in the lake_id column, then run this again.")
        return 0

    try:
        registry = load_registry()
        known = set(registry.by_id)
    except FileNotFoundError:
        known = set()

    rows = existing_aliases()
    seen = {(r["kind"], r["value"]) for r in rows}
    added, bad = 0, []

    for r in answered:
        choice = r["lake_id"].strip()
        name = (r.get("report_name") or "").strip()
        code = (r.get("ats") or "").strip()

        if choice.upper() == "SKIP":
            kind, value, lake_id = "skip", normalize_name(name), ""
        elif choice.upper() == "NEW":
            kind, value, lake_id = "new", normalize_name(name), ""
        else:
            if known and choice not in known:
                bad.append((name, choice))
                continue
            kind, value, lake_id = "name", normalize_name(name), choice

        if value and (kind, value) not in seen:
            rows.append(dict(kind=kind, value=value, lake_id=lake_id,
                             note=f"{r['year']} {name}"))
            seen.add((kind, value))
            added += 1
        # A land description is a stronger key than a name, so record it too.
        if code and kind == "name" and ("ats", code) not in seen:
            rows.append(dict(kind="ats", value=code, lake_id=lake_id,
                             note=f"{r['year']} {name}"))
            seen.add(("ats", code))
            added += 1

    if bad:
        print("These lake_id values are not in the registry:")
        for name, choice in bad:
            print(f"  {choice!r} for {name}")
        print("Copy an id from one of the candidate columns, or use NEW / SKIP.\n")

    ALIASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ALIASES_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["kind", "value", "lake_id", "note"])
        w.writeheader()
        w.writerows(rows)

    print(f"Recorded {added} new alias(es) in {ALIASES_PATH}")
    print(f"{len(blank)} question(s) still unanswered.")
    print("\nNow re-run:  python3 build_history.py")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
