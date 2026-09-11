"""Collect what Alberta publishes about each stocked lake, and discover its shape.

Run once; the result is committed and the build reads it from there, so a
rebuild never touches the network:

    python3 fetch_lake_pages.py --probe      # ONE page, print what it found
    python3 fetch_lake_pages.py --listing    # the whole list view, one request
    python3 fetch_lake_pages.py              # per-lake pages for anything missing

Why this does not hard-code the field names
-------------------------------------------
It was written without being able to open the site. Guessing at labels would
mean a field that is present but spelled differently comes back empty and looks
like "Alberta does not publish that", which is the worst kind of wrong: silent,
and indistinguishable from a real absence.

So instead of looking for known labels, this pulls out EVERY label-and-value
pair it can see — definition lists, two-column table rows, "Label: value" runs
of text — and reports the union of the labels it found. Run --probe first and
the page tells you its own schema; nothing here has to have guessed right.

The join is exact. MyWildAlberta addresses each lake as
stocking-maps.aspx?id=6537 and the registry already carries Alberta's own
waterbody id, so wb6537 is that same lake — no name matching anywhere.

Every page is saved under data/raw/mywildalberta/ as well as parsed, so a
wording change can be fixed from the saved copy without fetching again. Pages
are taken one at a time with a pause: this is a public service run for anglers.
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
OUT_CSV = ROOT / "data" / "raw" / "mywildalberta_lakes.csv"

BASE = "https://mywildalberta.ca/fishing/fish-stocking/"
PAGE_URL = BASE + "stocking-maps.aspx?id={id}"
LISTING_URL = BASE + "stocking-maps.aspx?listing=1"
PAUSE_SECONDS = 1.0
TIMEOUT = 30
USER_AGENT = ("HZ_Trout_Map/1.0 (open-source Alberta stocked-lake map; "
              "one-time collection of published lake attributes)")

# Labels worth promoting to their own column, matched loosely so a rewording
# still lands. Anything not listed here is still collected — it simply keeps
# whatever label the page gave it.
INTERESTING = {
    "max_depth_m": r"(?i)^(maximum |max\.? ?)?depth",
    "mean_depth_m": r"(?i)^(mean|average) depth",
    "surface_area_ha": r"(?i)^(surface )?area",
    "zone": r"(?i)^(fish management |watershed )?(zone|unit)",
    "elevation_m": r"(?i)^elevation",
    "species": r"(?i)^(species|fish|stocked with)",
    "access": r"(?i)^(access|directions|how to get)",
    "amenities": r"(?i)^(amenities|facilities|services)",
    "region": r"(?i)^region",
    "county": r"(?i)^(county|municipal)",
}


def strip_tags(html):
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(p|div|tr|li|h\d|dd|dt)>", "\n", html)
    html = re.sub(r"<[^>]+>", " ", html)
    for entity, plain in (("&nbsp;", " "), ("&amp;", "&"), ("&#39;", "'"),
                          ("&rsquo;", "’"), ("&lt;", "<"), ("&gt;", ">"),
                          ("&quot;", '"'), ("&deg;", "°")):
        html = html.replace(entity, plain)
    html = re.sub(r"[ \t ]+", " ", html)
    return re.sub(r"\n\s*\n+", "\n", html)


def harvest(html):
    """Every label-and-value pair the page offers, however it is marked up."""
    pairs = {}

    def record(label, value):
        label = re.sub(r"\s+", " ", strip_tags(label)).strip(" :–-")
        value = re.sub(r"\s+", " ", strip_tags(value)).strip(" :–-")
        if label and value and len(label) < 60 and len(value) < 400:
            pairs.setdefault(label, value)

    for label, value in re.findall(r"(?is)<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", html):
        record(label, value)
    for label, value in re.findall(r"(?is)<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", html):
        record(label, value)
    for label, value in re.findall(
            r"(?is)<td[^>]*>\s*<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>\s*</td>\s*<td[^>]*>(.*?)</td>", html):
        record(label, value)
    for label, value in re.findall(r"(?is)<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>\s*:?\s*([^<]{1,200})", html):
        record(label, value)
    # Plain "Label: value" lines, last so marked-up pairs win.
    for line in strip_tags(html).split("\n"):
        found = re.match(r"\s*([A-Za-z][A-Za-z ()./'-]{2,40}?)\s*:\s*(.+?)\s*$", line)
        if found:
            record(found.group(1), found.group(2))
    return pairs


def number(text):
    if not text:
        return None
    found = re.search(r"(-?\d+(?:\.\d+)?)", str(text).replace(",", ""))
    return float(found.group(1)) if found else None


def page_name(html):
    for pattern in (r"(?is)<h1[^>]*>(.*?)</h1>", r"(?is)<title[^>]*>(.*?)</title>"):
        found = re.search(pattern, html)
        if found:
            name = re.sub(r"\s+", " ", strip_tags(found.group(1))).strip()
            # Titles tend to carry the site name; keep the lake.
            return re.split(r"\s*[-|]\s*(?:Fish Stocking|My Wild Alberta|Stocking Maps)", name)[0].strip()
    return ""


def interpret(pairs, html):
    """Map the harvested labels onto the columns the build actually wants."""
    out = {"page_name": page_name(html)}
    for column, pattern in INTERESTING.items():
        for label, value in pairs.items():
            if re.search(pattern, label):
                if column.endswith(("_m", "_ha")):
                    out[column] = number(value)
                else:
                    out[column] = value
                break
    # A zone may only appear as a code in the prose.
    if not out.get("zone"):
        found = re.search(r"\b(ES[1-4]|NB[1-4]|PP[12])\b", strip_tags(html))
        if found:
            out["zone"] = found.group(1)
    else:
        found = re.search(r"\b(ES[1-4]|NB[1-4]|PP[12])\b", str(out["zone"]))
        if found:
            out["zone"] = found.group(1)
    out["depth_stated_unavailable"] = bool(
        re.search(r"(?i)depth[^.\n]{0,40}(not available|unavailable|unknown)", strip_tags(html)))
    return out


def fetch(url, cache_name, refresh=False):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / cache_name
    if cached.exists() and not refresh:
        return cached.read_text(encoding="utf-8", errors="replace"), True
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        html = response.read().decode("utf-8", errors="replace")
    cached.write_text(html, encoding="utf-8")
    return html, False


def load_targets():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    lakes = registry["lakes"] if isinstance(registry, dict) and "lakes" in registry else registry
    return [l for l in lakes if l.get("waterbody_id")]


def probe(waterbody_id, refresh):
    """Print one page's own schema, so nothing downstream has to have guessed."""
    html, _ = fetch(PAGE_URL.format(id=waterbody_id), f"{waterbody_id}.html", refresh)
    pairs = harvest(html)
    print(f"\n{PAGE_URL.format(id=waterbody_id)}")
    print(f"page name: {page_name(html)!r}\n")
    print(f"{len(pairs)} label/value pair(s) found:")
    for label, value in sorted(pairs.items()):
        print(f"  {label:<30} {value[:90]!r}")
    print("\nmapped onto the build's columns:")
    for key, value in sorted(interpret(pairs, html).items()):
        print(f"  {key:<26} {value!r}")
    print("\nIf a column above is None but the pair list shows it under another")
    print("label, add that spelling to INTERESTING in this file.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--probe", nargs="?", const="6537", metavar="ID",
                        help="fetch one lake page and print the fields it carries")
    parser.add_argument("--listing", action="store_true",
                        help="fetch the whole list view in one request")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--pause", type=float, default=PAUSE_SECONDS)
    args = parser.parse_args()

    if args.probe:
        probe(args.probe, args.refresh)
        return 0

    if args.listing:
        html, _ = fetch(LISTING_URL, "listing.html", args.refresh)
        text = strip_tags(html)
        ids = sorted(set(re.findall(r"[?&]id=(\d+)", html)), key=int)
        print(f"list view: {len(html):,} bytes, {len(ids)} lake id(s) linked")
        print(f"saved to {(CACHE_DIR / 'listing.html').relative_to(ROOT)}")
        print("\nfirst 40 lines of its text, so its columns can be read:")
        for line in [l for l in text.split("\n") if l.strip()][:40]:
            print("  " + line[:150])
        return 0

    targets = load_targets()
    if args.limit:
        targets = targets[:args.limit]
    print(f"{len(targets)} lake(s) carry an Alberta waterbody id")

    rows, labels_seen, unreadable = [], {}, []
    for i, lake in enumerate(targets, 1):
        wid = str(lake["waterbody_id"])
        try:
            html, from_cache = fetch(PAGE_URL.format(id=wid), f"{wid}.html", args.refresh)
        except (urllib.error.URLError, OSError) as err:
            print(f"  [{i}/{len(targets)}] {lake['name']}: {err}")
            continue
        pairs = harvest(html)
        for label in pairs:
            labels_seen[label] = labels_seen.get(label, 0) + 1
        found = interpret(pairs, html)
        if found.get("max_depth_m") is None and not found["depth_stated_unavailable"]:
            unreadable.append((wid, lake["name"]))
        row = {"waterbody_id": wid, "lake_id": lake.get("lake_id", ""),
               "registry_name": lake.get("name", "")}
        for column in INTERESTING:
            value = found.get(column)
            row[column] = "" if value is None else value
        row["depth_stated_unavailable"] = "yes" if found["depth_stated_unavailable"] else ""
        rows.append(row)
        if i % 25 == 0 or i == len(targets):
            got = sum(1 for r in rows if r["max_depth_m"] != "")
            zones = sum(1 for r in rows if r["zone"] != "")
            print(f"  [{i}/{len(targets)}] {got} with a depth, {zones} with a zone")
        if not from_cache:
            time.sleep(args.pause)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = (["waterbody_id", "lake_id", "registry_name"] + list(INTERESTING)
              + ["depth_stated_unavailable"])
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: int(r["waterbody_id"])):
            writer.writerow(row)
    print(f"\nwrote {OUT_CSV.relative_to(ROOT)} — {len(rows)} row(s)")

    print("\nlabels the pages actually used, most common first:")
    for label, count in sorted(labels_seen.items(), key=lambda kv: -kv[1])[:25]:
        print(f"  {count:>4}x  {label}")
    if unreadable:
        print(f"\n{len(unreadable)} page(s) had no depth and did not say it was unavailable;")
        print(f"their HTML is under {CACHE_DIR.relative_to(ROOT)}/ if the patterns need work.")
    print("\nNext: python3 reconcile.py — compares all of this against the repo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
