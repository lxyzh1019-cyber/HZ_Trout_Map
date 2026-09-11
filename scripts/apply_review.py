"""
apply_review.py — turn your answers in data/link_review.csv into permanent
aliases, so the same question is never asked twice.

    python3 apply_review.py            # apply answers
    python3 apply_review.py --list     # show what is still unanswered

How to answer
-------------
Open data/link_review.csv. Each row is one report name the linker would not
guess at, with up to three candidate lakes and how far each sits from where
the report puts it. Fill in the `lake_id` column with any of:

    1, 2, 3     the candidate in that column — usually the easiest way
    wb6608      the id of the right lake, if you would rather be explicit
    NEW         this really is a lake we have never recorded before
    SKIP        leave these rows out of the history entirely

Answers are checked before they are recorded. Two kinds are refused rather
than applied, because both silently corrupt a lake's history:

  - an answer that contradicts the report's own name, such as sending a row
    named "Pond #2" to the lake called "Pond #1"
  - the same report name sent to different lakes in different years, which
    splits one lake's history in two

Then run this. Your answer is written to data/lake_aliases.csv and applied on
every future build, including future years, so a name Alberta keeps
misspelling is settled once and stays settled.
"""

import argparse
import csv
import sys
from pathlib import Path

from registry import (ALIASES_PATH, REVIEW_PATH, discriminating_conflict,
                      load_registry, normalize_name)

VALID_KINDS = ("name", "ats", "new", "skip")


def read_answers():
    if not REVIEW_PATH.exists():
        print(f"No review file at {REVIEW_PATH}. Run build_history.py first.")
        return None
    # Excel writes this file back in a Windows encoding, so do not insist on
    # UTF-8 and do not fail on the one mangled apostrophe that results.
    for encoding in ("utf-8", "cp1252"):
        try:
            with open(REVIEW_PATH, newline="", encoding=encoding) as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    with open(REVIEW_PATH, newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def existing_aliases():
    rows = []
    if ALIASES_PATH.exists():
        with open(ALIASES_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    return rows


def candidate_id(row, choice):
    """Turn an answer into a lake id. Accepts a column number or an id."""
    if choice.isdigit() and 1 <= int(choice) <= 3:
        text = (row.get(f"candidate_{choice}") or "").strip()
        return text.split("|")[0].strip() or None
    return choice


def candidate_name(row, lake_id):
    for key in ("candidate_1", "candidate_2", "candidate_3"):
        text = (row.get(key) or "").strip()
        if text.split("|")[0].strip() == lake_id:
            parts = [p.strip() for p in text.split("|")]
            return parts[1] if len(parts) > 1 else ""
    return ""


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
    added, bad, refused = 0, [], []

    # An answer that sends the same report name to two different lakes in
    # different years splits one lake's history, so catch it before applying.
    by_name = {}
    for r in answered:
        choice = r["lake_id"].strip()
        if choice.upper() in ("NEW", "SKIP"):
            continue
        lake_id = candidate_id(r, choice)
        if lake_id:
            by_name.setdefault(normalize_name(r.get("report_name") or ""), set()).add(lake_id)
    contradictory = {n for n, ids in by_name.items() if len(ids) > 1}

    for r in answered:
        choice = r["lake_id"].strip()
        name = (r.get("report_name") or "").strip()
        code = (r.get("ats") or "").strip()

        if choice.upper() == "SKIP":
            kind, value, lake_id = "skip", normalize_name(name), ""
        elif choice.upper() == "NEW":
            kind, value, lake_id = "new", normalize_name(name), ""
        else:
            lake_id = candidate_id(r, choice)
            if not lake_id or (known and lake_id not in known):
                bad.append((name, choice))
                continue
            target = candidate_name(r, lake_id)
            if target and discriminating_conflict(name, target):
                refused.append((r["year"], name, lake_id, target,
                                "the report name and that lake disagree on which of a pair this is"))
                continue
            if normalize_name(name) in contradictory:
                refused.append((r["year"], name, lake_id, target,
                                "the same report name was sent to a different lake in another year"))
                continue
            kind, value = "name", normalize_name(name)

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
        print("These answers name no candidate:")
        for name, choice in bad:
            print(f"  {choice!r} for {name}")
        print("Use 1, 2 or 3 for a candidate column, an explicit id, or NEW / SKIP.\n")

    if refused:
        print("REFUSED — these would corrupt a lake's history, so they were not recorded:")
        for year, name, lake_id, target, why in refused:
            print(f"  {year}  {name}")
            print(f"        -> {lake_id} {target}")
            print(f"        {why}")
        print("  Fix the lake_id for these rows and run this again.\n")

    ALIASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ALIASES_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["kind", "value", "lake_id", "note"])
        w.writeheader()
        w.writerows(rows)

    print(f"Recorded {added} new alias(es) in {ALIASES_PATH}")
    print(f"{len(blank)} question(s) still unanswered, {len(refused)} refused.")
    print("\nNow re-run:  python3 build_history.py")
    return 1 if (bad or refused) else 0


if __name__ == "__main__":
    sys.exit(main())
