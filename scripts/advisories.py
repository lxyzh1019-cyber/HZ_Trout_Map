"""Alberta's fishing advisories, closures and corrections, collected daily.

    python3 advisories.py            # fetch and write live/advisories.json

This is the one thing on the map that changes between the time you plan a trip
and the time you take it, and it is the one that changes whether you should go
at all: a closure or a consumption advisory outranks any bite score.

Why it is written to live/ and not to data/
-------------------------------------------
The build checks that data/ is exactly what the pipeline produces, and fails if
anything differs. That check is worth keeping — it is what stops anyone editing
the published data by hand. But a scheduled job committing a fresh advisory file
into data/ would trip it every single day, and the usual fix for that is to
weaken the check. So the advisories live outside data/ instead, and the check
stays as strict as it was.

What this does NOT do
---------------------
It does not decide that a lake is closed. It records what Alberta published and
when, and the app shows it beside the lake. Turning prose into a closure flag
would mean guessing at the scope of a sentence written for a human, and getting
that wrong in the permissive direction puts someone on shut water.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "live" / "advisories.json"

SOURCES = [
    ("advisories", "https://mywildalberta.ca/fishing/advisories-corrections-closures/default.aspx"),
    ("consumption", "https://mywildalberta.ca/fishing/advisories-corrections-closures/fish-consumption-advisory.aspx"),
]
TIMEOUT = 30
USER_AGENT = ("HZ_Trout_Map/1.0 (open-source Alberta stocked-lake map; "
              "daily check of published fishing advisories)")


def strip_tags(html):
    html = re.sub(r"(?is)<(script|style|nav|header|footer).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(p|div|tr|li|h\d)>", "\n", html)
    html = re.sub(r"<[^>]+>", " ", html)
    for entity, plain in (("&nbsp;", " "), ("&amp;", "&"), ("&#39;", "'"),
                          ("&rsquo;", "’"), ("&lt;", "<"), ("&gt;", ">")):
        html = html.replace(entity, plain)
    html = re.sub(r"[ \t ]+", " ", html)
    return re.sub(r"\n\s*\n+", "\n", html).strip()


def entries(text):
    """Lines that name a waterbody and say something about it.

    Deliberately generous: a line kept that turns out to be boilerplate costs a
    reader one glance, while a line dropped that was a real closure costs them
    the trip or the fine.
    """
    found = []
    for line in text.split("\n"):
        line = line.strip()
        if len(line) < 25 or len(line) > 400:
            continue
        if not re.search(r"(?i)\b(lake|reservoir|pond|river|creek|watershed|zone)\b", line):
            continue
        if not re.search(r"(?i)\b(clos|advisor|correct|restrict|prohibit|suspend|"
                         r"do not eat|consumption|limit|open)\w*", line):
            continue
        found.append(line)
    # Preserve order, drop repeats.
    seen, unique = set(), []
    for line in found:
        if line not in seen:
            seen.add(line)
            unique.append(line)
    return unique


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode("utf-8", errors="replace")


def main():
    collected, failures = {}, []
    for name, url in SOURCES:
        try:
            text = strip_tags(fetch(url))
            collected[name] = {"url": url, "entries": entries(text)}
        except (urllib.error.URLError, OSError) as err:
            failures.append(f"{name}: {err}")

    if not collected:
        # Writing an empty file on a bad day would erase yesterday's real
        # advisories and read as "nothing to worry about".
        print("every source failed; leaving the existing file alone", file=sys.stderr)
        for line in failures:
            print("  " + line, file=sys.stderr)
        return 1

    existing = {}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
        except ValueError:
            existing = {}
    for name, url in SOURCES:
        if name not in collected and name in existing.get("sources", {}):
            collected[name] = existing["sources"][name]     # keep what we had
            collected[name]["stale"] = True

    payload = {
        "checked": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": collected,
        "note": ("Recorded as published by Alberta. Nothing here is interpreted "
                 "into a closure flag — read the source before you fish."),
    }
    if failures:
        payload["failed"] = failures

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fresh = json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    if OUT.exists():
        previous = json.loads(OUT.read_text(encoding="utf-8"))
        previous.pop("checked", None)
        compare = dict(payload)
        compare.pop("checked", None)
        if json.dumps(previous, sort_keys=True) == json.dumps(compare, sort_keys=True):
            # Nothing changed but the clock; do not make a commit out of that.
            print("no change since the last check")
            return 0
    OUT.write_text(fresh, encoding="utf-8")
    total = sum(len(s["entries"]) for s in collected.values())
    print(f"wrote {OUT.relative_to(ROOT)} — {total} line(s) across "
          f"{len(collected)} source(s)")
    for line in failures:
        print("  could not reach " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
