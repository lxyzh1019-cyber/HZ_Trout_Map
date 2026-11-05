"""How high each lake sits, from Open-Meteo's elevation service.

The weather comes per grid cell, a quarter of a degree wide, and its air
temperature is the temperature at the cell's own height. A lake in a valley
or on a plateau can sit a few hundred metres off that, and air cools about
6.5 °C for every kilometre up. The water model and the ice estimates use the
lake's own height to correct the air for that. Nothing else uses it.

Usage:

    python -I scripts/elevation.py

Every lake with a position, merged across the years the way the page merges
them, 100 points per request: 380 lakes is 4 requests. The service returns a
90 m digital elevation model value per point (Copernicus DEM GLO-90).

Writes data/lake_elevation.json:

    {"source": ..., "licence": ..., "retrieved": "YYYY-MM-DD", "calls": 4,
     "count": 380, "lakes": {"wb854": 1187.0, ...},
     "points": {"wb854": [53.63381, -117.709012], ...}}

"lakes" is what the app reads. "points" is where each height was asked for: a
saved height is kept only while its water is still within 100 m of that point,
so a lake or river spot that moved is asked for again.
"""

import datetime
import json
import math
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
OUT = DATA / "lake_elevation.json"
ENDPOINT = "https://api.open-meteo.com/v1/elevation"
PER_CALL = 100
MOVED_M = 100.0


def metres(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(min(1.0, h)))


def still_good(saved, key, point):
    """The saved height for key, if it was asked for within MOVED_M of point."""
    h = saved.get("lakes", {}).get(key)
    at = saved.get("points", {}).get(key)
    if h is None or not at or metres(at, point) > MOVED_M:
        return None
    return h


def placed_lakes():
    """lake key -> (lat, lon), the last year's position winning, as the page does."""
    lakes = {}
    for path in sorted(DATA.glob("lakes_20*.json")):
        for lake in json.loads(path.read_text(encoding="utf-8")):
            key = lake.get("lake_id") or lake.get("ats")
            if lake.get("lat") is not None and lake.get("lon") is not None:
                lakes[key] = (lake["lat"], lake["lon"])
    # Build 5 Stage 2: the guide's lakes that are not stocked, and each forecast
    # spot of a river stretch ("<stretch id>#<n>"), from scripts/waterbodies.py.
    extra = DATA / "waters_unstocked.json"
    if extra.exists():
        for lake in json.loads(extra.read_text(encoding="utf-8")).get("lakes", []):
            if lake.get("lat") is not None:
                lakes.setdefault(lake["lake_id"], (lake["lat"], lake["lon"]))
    rivers = DATA / "rivers.json"
    if rivers.exists():
        for st in json.loads(rivers.read_text(encoding="utf-8")).get("stretches", []):
            for i, (lat, lon) in enumerate(st.get("spots") or []):
                lakes[f"{st['lake_id']}#{i}"] = (lat, lon)
    return dict(sorted(lakes.items()))


def get_json(url):
    """GET a JSON document. Falls back to curl when Python's own certificate
    store refuses the chain (seen on one Windows PC); curl uses the system store."""
    req = urllib.request.Request(url, headers={"User-Agent": "troutmap-build/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        # A refused certificate chain (seen on one Windows PC) or a reset
        # connection: curl uses the system store and its own connection.
        out = subprocess.run(["curl", "-sfL", "-A", "troutmap-build/1.0", url],
                             capture_output=True, check=True, timeout=90).stdout
        return json.loads(out.decode("utf-8"))


def fetch(points):
    lats = ",".join(f"{lat:.5f}" for lat, _ in points)
    lons = ",".join(f"{lon:.5f}" for _, lon in points)
    # A reset connection is retried a few times before the build gives up.
    # A reset connection or a rate limit (HTTP 429) is retried, waiting longer each time.
    for attempt in range(8):
        try:
            body = get_json(f"{ENDPOINT}?latitude={lats}&longitude={lons}")
            break
        except (urllib.error.URLError, ConnectionError, TimeoutError, subprocess.CalledProcessError):
            if attempt == 7:
                raise
            time.sleep(15 * (attempt + 1))
    heights = body.get("elevation")
    if not isinstance(heights, list) or len(heights) != len(points):
        raise ValueError(f"expected {len(points)} heights, got {body!r:.200}")
    return heights


def main():
    lakes = placed_lakes()
    keys = list(lakes)
    out, calls = {}, 0
    # A height already saved for the same id at the same place is kept: the DEM
    # does not change, and each point is one call on Open-Meteo's free limit. A
    # new id, or one whose water moved more than 100 m (or has no saved point),
    # is asked for again. Ids no longer on the map are dropped.
    saved = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for k in keys:
        h = still_good(saved, k, lakes[k])
        if h is not None:
            out[k] = h
    need = [k for k in keys if k not in out]
    for i in range(0, len(need), PER_CALL):
        chunk = need[i:i + PER_CALL]
        heights = fetch([lakes[k] for k in chunk])
        calls += 1
        for k, h in zip(chunk, heights):
            if isinstance(h, (int, float)) and -100 < h < 5000:
                out[k] = round(float(h), 1)
        time.sleep(1)
    if len(out) != len(keys):
        missing = sorted(set(keys) - set(out))
        print(f"{len(out)} of {len(keys)} lakes have a height; missing {missing[:10]}. File not written.")
        return 1
    record = {
        "source": "Open-Meteo Elevation API (Copernicus DEM GLO-90, 90 m)",
        "url": ENDPOINT,
        "licence": "CC BY 4.0 (Open-Meteo); Copernicus DEM © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA",
        "retrieved": datetime.date.today().isoformat(),
        # Calls a build from nothing takes (100 points per call); this run made calls_this_run.
        "calls": -(-len(out) // PER_CALL),
        "calls_this_run": calls,
        "count": len(out),
        "lakes": dict(sorted(out.items())),
        "points": {k: [round(lakes[k][0], 6), round(lakes[k][1], 6)] for k in sorted(out)},
    }
    OUT.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\r\n")
    print(f"{len(out)} of {len(keys)} lakes, {len(need)} asked for in {calls} calls -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
