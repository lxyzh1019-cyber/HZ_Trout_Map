#!/usr/bin/env python3
"""Reference pictures of the map: python3 tests/pictures.py before|after|compare.

before  -> takes every screen at every size into tests/reference/ (the baseline)
after   -> takes the same pictures into tests/out/after/
compare -> pixel-compares tests/out/after/ with tests/reference/ and prints the Proof line

Everything that could move between runs is pinned: the repo root is served by
http.server on a free port, the clock is fixed at 2026-10-13T12:00:00 in
America/Edmonton, open-meteo answers from tests/fixtures/, every other outside
request (map tiles, photos) is aborted, storage starts empty, no geolocation and
no service worker. Needs: pip install -r tests/requirements.txt (Chromium comes
from PLAYWRIGHT_BROWSERS_PATH; do not run playwright install here).
"""
import functools
import http.server
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
REFERENCE = TESTS / "reference"
OUT_AFTER = TESTS / "out" / "after"
OUT_DIFF = TESTS / "out" / "diff"
FIXTURES = TESTS / "fixtures"

TIMEZONE = "America/Edmonton"
CLOCK = "2026-10-13T12:00:00-06:00"   # 12:00 local, MDT

SIZES = {
    "phone": (390, 844),
    "ipad": (820, 1180),
    "pc": (1440, 900),
}

# Kerbe's Pond: a bait-ban lake (data/lake_regulations.json) that is also on the
# aeration roster (data/aca_aeration_roster.csv) and has photos for the panel.
POPUP_LAKE = "wb6770"

SCREENS = {
    # name: (query string, weather fixture)
    "map": ("", "weather-october.json"),
    "filters": ("", "weather-october.json"),
    "popup": ("?lake=" + POPUP_LAKE, "weather-october.json"),
    "lake-panel": ("?lake=" + POPUP_LAKE, "weather-october.json"),
    "conditions": ("?cx=now", "weather-october.json"),
    "conditions-freeze": ("?cx=now", "weather-freeze.json"),
}

TOLERANCE = 0.002        # share of pixels allowed to differ per picture (0.2 %)
CHANNEL_THRESHOLD = 16   # a pixel differs when any channel moves more than this
SETTLE_MS = 1500         # after the screen is ready, for Leaflet pans and fades


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def start_server():
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def make_router(base, fixture_body):
    def route(r):
        url = r.request.url
        if url.startswith(base):
            return r.continue_()
        if "api.open-meteo.com" in url:
            return r.fulfill(status=200, content_type="application/json",
                             headers={"Access-Control-Allow-Origin": "*"},
                             body=fixture_body)
        return r.abort()      # tiles, photos and anything else outside
    return route


def wait_ready(page):
    page.wait_for_selector("#loading.hidden", state="attached", timeout=60000)
    page.wait_for_load_state("networkidle")


def prepare(page, screen):
    if screen == "filters":
        page.wait_for_selector("#season-group:not([hidden])", timeout=30000)
        # A phone opens the slide-over with #menu-btn; a wider screen whose
        # sidebar was collapsed opens it with #sidebar-open.
        for sel in ("#menu-btn", "#sidebar-open"):
            opener = page.locator(sel)
            if opener.is_visible():
                opener.click()
                break
        page.locator("#season-group").scroll_into_view_if_needed()
    elif screen in ("popup", "lake-panel"):
        page.wait_for_selector(".leaflet-popup", timeout=30000)
        page.wait_for_timeout(SETTLE_MS)
        if screen == "lake-panel":
            page.locator(".leaflet-popup [data-photos]").click()
            page.wait_for_selector("#lake-panel:not([hidden])", timeout=30000)
    elif screen.startswith("conditions"):
        page.wait_for_selector("#conditions-panel:not([hidden])", timeout=30000)
        page.wait_for_load_state("networkidle")
    page.wait_for_timeout(SETTLE_MS)


def shoot(out_dir):
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    server = start_server()
    base = "http://127.0.0.1:%d/" % server.server_address[1]
    taken = 0
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for screen, (query, fixture) in SCREENS.items():
                body = (FIXTURES / fixture).read_text()
                for size, (w, h) in SIZES.items():
                    ctx = browser.new_context(
                        viewport={"width": w, "height": h},
                        device_scale_factor=1,
                        timezone_id=TIMEZONE,
                        locale="en-CA",
                        permissions=[],
                        service_workers="block",
                        reduced_motion="reduce",
                    )
                    ctx.route("**/*", make_router(base, body))
                    page = ctx.new_page()
                    page.clock.install(time=CLOCK)
                    page.goto(base + "index.html" + query)
                    wait_ready(page)
                    prepare(page, screen)
                    path = out_dir / ("%s-%s.png" % (screen, size))
                    page.screenshot(path=str(path), animations="disabled", caret="hide")
                    ctx.close()
                    taken += 1
                    print("took", path.relative_to(ROOT))
            browser.close()
    finally:
        server.shutdown()
    print("%d pictures in %s" % (taken, out_dir.relative_to(ROOT)))


def compare():
    from PIL import Image, ImageChops

    OUT_DIFF.mkdir(parents=True, exist_ok=True)
    changed, missing = [], []
    for screen in SCREENS:
        for size in SIZES:
            name = "%s-%s.png" % (screen, size)
            ref, new = REFERENCE / name, OUT_AFTER / name
            if not ref.exists() or not new.exists():
                missing.append(name)
                continue
            a = Image.open(ref).convert("RGB")
            b = Image.open(new).convert("RGB")
            if a.size != b.size:
                changed.append((name, 1.0))
                print("%-30s size %s -> %s" % (name, a.size, b.size))
                continue
            diff = ImageChops.difference(a, b)
            mask = diff.convert("L").point(lambda v: 255 if v > CHANNEL_THRESHOLD else 0)
            share = mask.histogram()[255] / float(a.size[0] * a.size[1])
            status = "ok" if share <= TOLERANCE else "DIFFERS"
            print("%-30s %.4f%% %s" % (name, share * 100, status))
            if share > TOLERANCE:
                changed.append((name, share))
                Image.composite(Image.new("RGB", a.size, (255, 0, 0)), b, mask).save(OUT_DIFF / name)
    total = len(SCREENS) * len(SIZES)
    for name in missing:
        print("%-30s MISSING" % name)
    names = ", ".join(n for n, _ in changed)
    print("%d of %d pictures differ, %d missing%s" % (len(changed), total, len(missing),
                                                     (": " + names) if names else ""))
    print("Proof: pictures %d screens × %d sizes × 1 looks, %d changed%s" % (
        len(SCREENS), len(SIZES), len(changed), (" (" + names + ")") if names else ""))
    return 1 if (changed or missing) else 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "before":
        shoot(REFERENCE)
    elif cmd == "after":
        shoot(OUT_AFTER)
    elif cmd == "compare":
        return compare()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
