"""Build 5 Stage 3a: My spots (import, matching, the panel and the 3D layer) and the
lake outlines they match against (decision 30).

    PYTHONPATH=scripts python3 -m unittest scripts/test_my_spots.py

The owner's own file (my-spots-private.geojson) is never in the repository. These
tests use made-up places with the same shape as Google's exports: a Takeout
"Saved Places.json", saved-list CSVs, a My Maps KML and its KMZ, and GeoJSON.
"""

import base64
import io
import json
import re
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path

import lake_outlines as lo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
JS = ROOT / "js" / "my-spots.js"

SYLVAN_SPOT = (52.3321, -114.1462)        # the owner's test case: 5.5 km from Sylvan's centre point
PINE_POINT = (52.08954, -113.44167)
GULL_POINT = (52.57, -114.0)
RIVER_POINT = (52.0605, -114.0023)        # on the Red Deer River line (rv-pp2-red-deer-river-1)
CALGARY_CAFE = (51.0447, -114.0719)

TAKEOUT = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [SYLVAN_SPOT[1], SYLVAN_SPOT[0]]},
         "properties": {"date": "2024-06-01T00:00:00Z", "google_maps_url": "http://maps.google.com/?cid=1",
                        "location": {"name": "Sunbreaker point", "address": "", "country_code": "CA"}}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [CALGARY_CAFE[1], CALGARY_CAFE[0]]},
         "properties": {"location": {"name": "Coffee shop", "address": "123 8 Ave SW, Calgary, AB", "country_code": "CA"}}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]},
         "properties": {"location": {"name": "Strubel Lake"}}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]},
         "properties": {"location": {"name": "Kalamalka Lake"}}},
    ],
}
WALLEYE_CSV = ("Title,Note,URL,Comment\n"
               '"Pine Lake, south bay",Jig 4 m,"https://www.google.com/maps/search/?api=1&query=%s,%s",\n'
               'Gull weed edge,,"https://www.google.com/maps/place/Gull/@%s,%s,15z",evening\n'
               "Hasse Lake,,,\n") % (PINE_POINT + GULL_POINT)
CHECK_CSV = ("Title,Note,URL,Comment\n"
             'River bend,,"https://www.google.com/maps/search/%s,%s",\n'
             '"Pine Lake, south bay",,"https://www.google.com/maps/search/?api=1&query=%s,%s",\n') % (RIVER_POINT + PINE_POINT)
KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Fishing</name>
<Folder><name>Perch</name>
  <Placemark><name>Sylvan reef</name><description><![CDATA[Ice, 6 m<br>north side]]></description>
    <Point><coordinates>%s,%s,0</coordinates></Point></Placemark>
</Folder>
<Folder><name>Pike</name>
  <Placemark><name>Gull point</name><Point><coordinates>%s,%s,0</coordinates></Point></Placemark>
</Folder>
</Document></kml>""" % (SYLVAN_SPOT[1] + 0.001, SYLVAN_SPOT[0], GULL_POINT[1], GULL_POINT[0])


def kmz_b64():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", KML)
    return base64.b64encode(buf.getvalue()).decode()


def app_context():
    """The lakes and rivers the app gives the matcher (spotsContext in index.html)."""
    lakes = [{"key": k, "name": v["name"], "lat": v["lat"], "lon": v["lon"]} for k, v in sorted(lo.app_lakes().items())]
    rivers = [{"key": r["lake_id"], "line": r["line"]}
              for r in json.loads((DATA / "rivers.json").read_text(encoding="utf-8"))["stretches"]]
    return {"lakes": lakes, "rivers": rivers}


def run(expr, args):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not installed")
    script = (
        "const fs=require('fs'),vm=require('vm');"
        "const ctx={window:{},console,URL,TextDecoder,Blob,Response,"
        "DecompressionStream:typeof DecompressionStream==='undefined'?undefined:DecompressionStream,"
        "atob:(s)=>Buffer.from(s,'base64').toString('binary')};"
        "vm.createContext(ctx);"
        "const a=JSON.parse(fs.readFileSync(0,'utf8'));ctx.A=a.args;"
        "vm.runInContext(fs.readFileSync(a.file,'utf8'),ctx);"
        "Promise.resolve(vm.runInContext(a.expr,ctx)).then(r=>process.stdout.write(JSON.stringify(r)),"
        "e=>{process.stdout.write(JSON.stringify({error:String(e&&e.message||e)}))});"
    )
    arg = json.dumps({"file": str(JS), "expr": expr, "args": args})
    out = subprocess.run([node, "-e", script], input=arg, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


IMPORT_ALL = """(async function () {
  var M = window.MySpots, ctx = A.ctx;
  ctx.outlines = M.prepOutlines(A.outlines);
  var bytes = Uint8Array.from(atob(A.kmz), function (c) { return c.charCodeAt(0); });
  var files = [["Saved Places.json", A.takeout], ["Walleye.csv", A.walleye],
               ["Fishing spot (need to validate).csv", A.check], ["Fishing.kml", A.kml]];
  var places = [];
  for (var f of files) places = places.concat(await M.parseFile(f[0], f[1]));
  var kmz = await M.parseFile("Fishing.kmz", bytes.buffer);
  var r = M.classify(places, ctx);
  var one = M.classify(places.slice(0, 1), ctx);
  await M.save(r, "test"); var first = M.forLake("wb5952").length;
  await M.save(M.classify(places, ctx), "test"); var second = M.forLake("wb5952").length;
  return { r: r, one: one, kmz: kmz, first: first, second: second, offLake: M.offLake().length,
           savedPine: M.savedFor("wb5919").length };
})()"""


class MySpotsImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run(IMPORT_ALL, {"ctx": app_context(),
                                   "outlines": json.loads((DATA / "lake_outlines.json").read_text(encoding="utf-8")),
                                   "takeout": json.dumps(TAKEOUT), "walleye": WALLEYE_CSV, "check": CHECK_CSV,
                                   "kml": KML, "kmz": kmz_b64()})
        assert "error" not in cls.out, cls.out
        cls.r = cls.out["r"]
        cls.by_name = {s["name"]: s for s in cls.r["spots"]}

    def test_the_sylvan_spot_matches_sylvan_lake(self):
        # 5.5 km from the centre point the app has, but on Sylvan's shore.
        self.assertEqual(self.out["one"]["spots"][0]["lake"], "wb5952")
        self.assertEqual(self.by_name["Sunbreaker point"]["lake"], "wb5952")
        self.assertLessEqual(self.by_name["Sunbreaker point"]["shoreM"], 500)

    def test_links_give_positions_and_lists_give_tags(self):
        pine = self.by_name["Pine Lake, south bay"]
        self.assertEqual(pine["lake"], "gu-pp2-pine-lake")
        self.assertEqual(self.by_name["Gull weed edge"]["lake"], "gu-pp2-gull-lake")
        self.assertIn("Walleye", pine["tags"])
        self.assertIn("Jig 4 m", self.by_name["Pine Lake, south bay"]["note"])
        self.assertEqual(self.by_name["Gull weed edge"]["note"], "evening")

    def test_need_to_validate_becomes_unconfirmed(self):
        bend = self.by_name["River bend"]
        self.assertEqual(bend["tags"], ["Unconfirmed"])
        self.assertTrue(bend["unconfirmed"])
        # The same Pine Lake place is in two lists: one spot, both tags.
        pine = self.by_name["Pine Lake, south bay"]
        self.assertEqual(sorted(pine["tags"]), ["Unconfirmed", "Walleye"])
        self.assertEqual(self.r["counts"]["duplicates"], 1)

    def test_a_river_spot_and_a_town_place(self):
        self.assertEqual(self.by_name["River bend"]["river"], "rv-pp2-red-deer-river-1")
        self.assertIsNone(self.by_name["River bend"]["lake"])
        self.assertNotIn("Coffee shop", self.by_name)
        self.assertEqual(self.r["counts"]["skipped"], 1)

    def test_names_without_a_pin(self):
        saved = {s["name"]: s["lake"] for s in self.r["saved"]}
        self.assertEqual(saved, {"Strubel Lake": "wb5919", "Hasse Lake": "wb4794"})
        np = {s["name"]: s["why"] for s in self.r["notPlaced"]}
        self.assertEqual(np, {"Kalamalka Lake": "no Alberta lake with this name"})
        self.assertEqual(self.out["savedPine"], 1)

    def test_kml_folders_are_tags_and_the_kmz_reads_the_same(self):
        reef = self.by_name["Sylvan reef"]
        self.assertEqual((reef["lake"], reef["tags"]), ("wb5952", ["Perch"]))
        self.assertEqual(reef["note"], "Ice, 6 m north side")
        self.assertEqual(self.by_name["Gull point"]["tags"], ["Pike"])
        self.assertEqual([p["name"] for p in self.out["kmz"]], ["Sylvan reef", "Gull point"])

    def test_the_counts_add_up_to_the_file(self):
        c = self.r["counts"]
        self.assertEqual(sum(c.values()), self.r["total"])
        self.assertEqual(self.r["total"], 4 + 3 + 2 + 2)
        self.assertEqual(c["lake"] + c["river"] + c["offLake"], len(self.r["spots"]))

    def test_a_second_import_replaces_the_first(self):
        self.assertEqual(self.out["first"], self.out["second"])
        self.assertEqual(self.out["first"], 2)            # Sunbreaker point and Sylvan reef


class MySpotsParserTests(unittest.TestCase):
    def test_coordinates_from_google_links(self):
        expr = """[ "https://www.google.com/maps/search/?api=1&query=52.1,-114.2",
                    "https://maps.google.com/?q=52.1%2C-114.2",
                    "https://www.google.com/maps/place/X/@52.1,-114.2,15z",
                    "https://www.google.com/maps/place/X/data=!3d52.1!4d-114.2",
                    "https://www.google.com/maps/search/52.1,+-114.2",
                    "http://maps.google.com/?cid=123" ].map(window.MySpots._internal.coordsFromUrl)"""
        self.assertEqual(run(expr, {}), [[52.1, -114.2]] * 5 + [None])

    def test_csv_quotes_and_names(self):
        text = 'Title,Note\n"A, b","say ""hi"""\r\n'
        self.assertEqual(run("window.MySpots._internal.csvRows(A.t)", {"t": text}), [["Title", "Note"], ["A, b", 'say "hi"']])
        self.assertEqual(run('window.MySpots._internal.nameForms("Graham (Trout) Lake")', {}),
                         ["graham trout lake", "graham lake"])

    def test_list_names_in_a_lists_property_are_tags(self):
        doc = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": None,
               "properties": {"name": "Some Lake", "tags": ["Pike"], "lists": ["Fishing spot (need to validate)"]}}]}
        out = run("window.MySpots._internal.parseGeoJson(A.d, '')", {"d": doc})
        self.assertEqual(out[0]["tags"], ["Pike", "Unconfirmed"])

    def test_an_unknown_file_type_says_what_it_reads(self):
        out = run('window.MySpots.parseFile("spots.txt", "x")', {})
        self.assertEqual(out, {"error": "The app reads .json, .geojson, .csv, .kml and .kmz files."})


class MySpotsPrivacyTests(unittest.TestCase):
    def test_spots_never_leave_the_browser(self):
        js = JS.read_text(encoding="utf-8")
        for call in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "localStorage"):
            self.assertNotIn(call, js, call)
        self.assertIn('var DB = "troutmap-spots"', js)
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        glue = page[page.index("async function importSpots("):page.index("function renderMySpots(")]
        self.assertEqual(re.findall(r'fetch\("([^"]+)"', glue), ["data/lake_outlines.json"])

    def test_no_private_spots_file_in_the_repository(self):
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        self.assertFalse([f for f in tracked if "private" in f.lower() and f.endswith((".geojson", ".json", ".kml", ".kmz", ".csv"))])
        self.assertFalse([f for f in tracked if f.lower().endswith((".kml", ".kmz"))])


class LakeOutlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads((DATA / "lake_outlines.json").read_text(encoding="utf-8"))

    def test_every_lake_has_an_outline_or_a_circle(self):
        lakes = lo.app_lakes()
        self.assertEqual(set(self.doc["lakes"]), set(lakes))
        c = self.doc["counts"]
        self.assertEqual(sum(c.values()), len(lakes))
        self.assertGreater(c["inside"] + c["named"], 0.75 * len(lakes))
        self.assertEqual(self.doc["licence"], "Open Government Licence - Canada")

    def test_big_lakes_keep_every_map_sheet_piece(self):
        import waterbodies as wb

        def ha(key):
            return sum(wb.ring_area_km2([(q[1], q[0]) for q in lo.decode(r)]) * 100 for r in self.doc["lakes"][key]["rings"])
        # Against the lakebed surveys (water_ha), within 15 %.
        self.assertAlmostEqual(ha("wb5952"), 4226, delta=0.15 * 4226)                       # Sylvan
        self.assertAlmostEqual(ha("gu-nb1-lac-la-biche"), 23642, delta=0.15 * 23642)
        self.assertGreater(len(self.doc["lakes"]["gu-nb2-lesser-slave-lake"]["rings"]), 3)
        self.assertGreater(ha("gu-nb2-lesser-slave-lake"), 100000)

    def test_ring_encoding_and_sheet_lines(self):
        ring = [(52.1, -114.2), (52.10001, -114.19), (52.2, -114.0)]
        self.assertEqual(lo.decode(lo.encode(ring)), ring)
        self.assertTrue(lo.on_sheet_line("lat", 55.5) and lo.on_sheet_line("lon", -116.0))
        self.assertFalse(lo.on_sheet_line("lat", 55.6) or lo.on_sheet_line("lon", -115.75))
        sq = [(0, 0), (0, 0.01), (0.00001, 0.02), (0, 0.03), (0.01, 0.03), (0.01, 0)]
        self.assertEqual(lo.simplify_ring(sq), [(0, 0), (0, 0.03), (0.01, 0.03), (0.01, 0)])   # points on a straight edge go


class MySpotsViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.sheet = (ROOT / "js" / "lake-sheet.js").read_text(encoding="utf-8")
        cls.d3 = (ROOT / "js" / "depth-3d.js").read_text(encoding="utf-8")

    def test_the_import_controls(self):
        # Several files at once (Takeout has one CSV per saved list); a new import replaces the last.
        self.assertIn('<input type="file" id="spots-file" accept=".json,.geojson,.csv,.kml,.kmz" multiple hidden>', self.page)
        self.assertIn("for (const file of files) {", self.page)
        self.assertIn("They stay in this browser only and are never sent anywhere.", self.page)
        self.assertIn('if (!confirm("Remove your imported spots from this browser?")) return;', self.page)
        self.assertIn("Spots not on a lake (${offs.length})", self.page)

    def test_the_lake_panel_section(self):
        self.assertIn('section("mine", "My spots"', self.sheet)
        self.assertIn('<span class="tag hollow">Unconfirmed</span>', self.sheet)
        self.assertIn("Saved lake in your list", self.sheet)

    def test_the_3d_layer(self):
        self.assertIn('mine: ["My spots", "c", "#14B8A6"]', self.d3)
        self.assertIn("var groups = [L.mine, L.access,", self.d3)
        self.assertIn("MySpots.forLake(lakeKey(lake))", self.d3)
        self.assertIn("wireframe: true", self.d3)                  # Unconfirmed: a hollow ring
        learn = (ROOT / "learn" / "depth-model.html").read_text(encoding="utf-8")
        self.assertIn('<h3 id="layer-mine">My spots</h3>', learn)

    def test_offline(self):
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn('"js/my-spots.js"', sw)
        self.assertIn('const SHELL_CACHE = "troutmap-shell-v14";', sw)


if __name__ == "__main__":
    unittest.main()
