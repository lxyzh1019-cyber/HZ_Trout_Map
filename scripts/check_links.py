"""Check that every link the app shows from its own data files still opens.

Hot spots must each carry a source link and a date, and a spot whose source
has gone is a spot nobody can check, so those links are tested live. The depth
chart links are tested too: one per matched lake.

Usage:

    python -I scripts/check_links.py            # hot spots and depth charts
    python -I scripts/check_links.py --hot-spots

Prints one line per broken link and exits 1 if any is broken. Reads the data
files only; nothing in them is run.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"


def links(hot_only):
    spots = json.loads((DATA / "hot_spots.json").read_text(encoding="utf-8"))
    for s in spots.get("spots", []):
        yield f"hot spot {s.get('lake')} / {s.get('name')}", s.get("source_url")
    if hot_only:
        return
    charts = json.loads((DATA / "depth_charts.json").read_text(encoding="utf-8"))
    seen = set()
    for key, c in charts.get("lakes", {}).items():
        if c["url"] not in seen:
            seen.add(c["url"])
            yield f"depth chart {key} {c['name']}", c["url"]


def opens(url):
    if not str(url or "").startswith("https://"):
        return False, "not an https link"
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": "troutmap-linkcheck/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status < 400:
                    return True, str(resp.status)
        except urllib.error.HTTPError as err:
            if method == "GET":
                return False, f"HTTP {err.code}"
        except (urllib.error.URLError, TimeoutError) as err:
            if method == "GET":
                return False, str(getattr(err, "reason", err))
    return False, "no answer"


def main(argv):
    hot_only = "--hot-spots" in argv
    checked = broken = 0
    for label, url in links(hot_only):
        checked += 1
        ok, why = opens(url)
        if not ok:
            broken += 1
            print(f"BROKEN  {label}: {url} ({why})")
    print(f"{checked} links checked, {broken} broken")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
