"""Collect maximum depth and surface area from Alberta's own stocked-lake pages.

Run this once; the result is committed and the build reads it from there, so a
rebuild never touches the network:

    python3 fetch_depths.py                 # everything missing
    python3 fetch_depths.py --limit 5       # try a handful first
    python3 fetch_depths.py --refresh       # fetch again even if cached

Why depth is worth the trouble: it is the difference between advice and a guess.
A lake shallower than about five metres stays mixed all summer, so telling
someone to fish the thermocline there is telling them to fish water that does
not exist; a deep lake genuinely stratifies and the fish really are down there.
Depth is also the first term in winterkill risk. Without it both have to fail
closed and say nothing.

The join is exact, which is the nice part. MyWildAlberta addresses each lake as
stocking-maps.aspx?id=6537, and the registry already carries Alberta's own
waterbody id for 332 of its lakes — wb6537 is that same lake. So there is no
name matching here at all, and none of the ambiguity that comes with it.

Pages are fetched one at a time with a pause between them. This is a public
service run for anglers, and there is no reason to hammer it: the whole set is a
few minutes, once.

Every page is saved under data/raw/mywildalberta/ as well as parsed. If the
parse comes back empty the saved HTML is what makes it fixable — commit those
and the patterns can be corrected without anyone having to fetch again.
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
REGISTRY = ROOT / "data" / "lake_registry.json"
CACHE_DIR = ROOT / "data" / "raw" / "mywildalberta"
OUT_CSV = ROOT / "data" / "raw" / "mywildalberta_depths.csv"

URL = "https://mywildalberta.ca/fishing/fish-stocking/stocking-maps.aspx?id={id}"
PAUSE_SECONDS = 1.0
TIMEOUT = 30
USER_AGENT = ("HZ_Trout_Map/1.0 (open-source Alberta stocked-lake map; "
              "one-time collection of published lake attributes)")


def strip_tags(html):
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(p|div|tr|li|h\d)>", "\n", html)
    html = re.sub(r"<[^>]+>", " ", html)
    html = (html.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&#39;", "'").replace("&rsquo;", "’")
                .replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"[ \t ]+", " ", html)


def first_number(text):
    if text is None:
        return None
    found = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
    return float(found.group(1)) if found else None


# Several shapes are tried because the page's wording is not under our control,
# and a label that quietly stops matching would show up as "no depth" rather
# than as an error.
DEPTH_PATTERNS = [
    r"(?i)maximum\s+depth[^0-9a-zA-Z]{0,20}([0-9.,]+)\s*m\b",
    r"(?i)max(?:\.|imum)?\s*depth\s*(?:\(m\))?\s*[:\-]?\s*([0-9.,]+)",
    r"(?i)depth\s*\(\s*m\s*\)\s*[:\-]?\s*([0-9.,]+)",
    r"(?i)\bdepth\b[^0-9\n]{0,30}([0-9.,]+)\s*(?:m|metres|meters)\b",
]
AREA_PATTERNS = [
    r"(?i)surface\s+area[^0-9a-zA-Z]{0,20}([0-9.,]+)\s*ha\b",
    r"(?i)surface\s*area\s*(?:\(ha\))?\s*[:\-]?\s*([0-9.,]+)",
    r"(?i)area\s*\(\s*ha\s*\)\s*[:\-]?\s*([0-9.,]+)",
]
NAME_PATTERNS = [
    r"(?is)<h1[^>]*>(.*?)</h1>",
    r"(?is)<title[^>]*>(.*?)</title>",
]


def parse(html):
    text = strip_tags(html)
    out = {"max_depth_m": None, "surface_area_ha": None, "page_name": ""}
    for pattern in DEPTH_PATTERNS:
        found = re.search(pattern, text)
        if found:
            out["max_depth_m"] = first_number(found.group(1))
            break
    for pattern in AREA_PATTERNS:
        found = re.search(pattern, text)
        if found:
            out["surface_area_ha"] = first_number(found.group(1))
            break
    for pattern in NAME_PATTERNS:
        found = re.search(pattern, html)
        if found:
            out["page_name"] = strip_tags(found.group(1)).strip()
            break
    # "Depth information is not available" is a real answer, and not the same as
    # a page we failed to read.
    out["states_unavailable"] = bool(
        re.search(r"(?i)depth[^.\n]{0,40}(not available|unavailable|unknown)", text))
    return out


def fetch(waterbody_id, refresh=False):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"{waterbody_id}.html"
    if cached.exists() and not refresh:
        return cached.read_text(encoding="utf-8", errors="replace"), True
    request = urllib.request.Request(URL.format(id=waterbody_id),
                                     headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        html = response.read().decode("utf-8", errors="replace")
    cached.write_text(html, encoding="utf-8")
    return html, False


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="stop after this many lakes")
    parser.add_argument("--refresh", action="store_true", help="re-fetch cached pages")
    parser.add_argument("--pause", type=float, default=PAUSE_SECONDS)
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    lakes = registry["lakes"] if isinstance(registry, dict) and "lakes" in registry else registry
    targets = [l for l in lakes if l.get("waterbody_id")]
    if args.limit:
        targets = targets[:args.limit]

    print(f"{len(targets)} lake(s) carry an Alberta waterbody id, out of {len(lakes)}")
    rows, got_depth, unreadable = [], 0, []
    for i, lake in enumerate(targets, 1):
        wid = str(lake["waterbody_id"])
        try:
            html, from_cache = fetch(wid, args.refresh)
        except (urllib.error.URLError, OSError) as err:
            print(f"  [{i}/{len(targets)}] {lake['name']}: {err}")
            continue
        found = parse(html)
        if found["max_depth_m"] is not None:
            got_depth += 1
        elif not found["states_unavailable"]:
            unreadable.append((wid, lake["name"]))
        rows.append({
            "waterbody_id": wid,
            "lake_id": lake.get("lake_id", ""),
            "registry_name": lake.get("name", ""),
            "page_name": found["page_name"],
            "max_depth_m": "" if found["max_depth_m"] is None else found["max_depth_m"],
            "surface_area_ha": "" if found["surface_area_ha"] is None else found["surface_area_ha"],
            "depth_stated_unavailable": "yes" if found["states_unavailable"] else "",
        })
        if i % 25 == 0 or i == len(targets):
            print(f"  [{i}/{len(targets)}] {got_depth} with a depth so far")
        if not from_cache:
            time.sleep(args.pause)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "waterbody_id", "lake_id", "registry_name", "page_name",
            "max_depth_m", "surface_area_ha", "depth_stated_unavailable"])
        writer.writeheader()
        for row in sorted(rows, key=lambda r: int(r["waterbody_id"])):
            writer.writerow(row)

    print(f"\nwrote {OUT_CSV.relative_to(ROOT)} — {len(rows)} row(s), {got_depth} with a depth")
    if unreadable:
        print(f"\n{len(unreadable)} page(s) had no depth and did not say it was unavailable.")
        print("That usually means the page wording moved. The HTML is saved under")
        print(f"  {CACHE_DIR.relative_to(ROOT)}/ — commit a couple of these and the")
        print("patterns in this file can be corrected without fetching again. For example:")
        for wid, name in unreadable[:5]:
            print(f"  {wid}.html  ({name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
