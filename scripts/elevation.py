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
     "count": 380, "lakes": {"wb854": 1187.0, ...}}
"""

import datetime
import json
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
    # A height already saved for the same id is kept: the DEM does not change, and
    # each point is one call on Open-Meteo's free limit. Only new points are asked for.
    if OUT.exists():
        saved = json.loads(OUT.read_text(encoding="utf-8")).get("lakes", {})
        out = {k: v for k, v in saved.items() if k in lakes}
    out = dict(out)
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
    }
    OUT.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\r\n")
    print(f"{len(out)} of {len(keys)} lakes, {calls} calls -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
