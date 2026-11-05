"""Build 3 data: the lakebed grids of the 3D depth model and the boating rules.

Run with the other checks:  python -m unittest discover -s scripts -p "test_*.py"
"""

import json
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import boating_rules  # noqa: E402
import depth_grids  # noqa: E402

ROOT = Path(__file__).parent.parent
INDEX = ROOT / "data" / "depth_grids" / "index.json"
RULES = ROOT / "data" / "boating_rules.json"


def load_index():
    return json.loads(INDEX.read_text(encoding="utf-8"))


def lake_id(index, name):
    return next(w for w, v in index["lakes"].items() if v["name"] == name)


class DepthGridTests(unittest.TestCase):

    def test_every_depth_chart_lake_has_a_grid(self):
        charts = json.loads((ROOT / "data" / "depth_charts.json").read_text(encoding="utf-8"))["lakes"]
        index = load_index()
        # Every stocked lake with a depth chart has its lakebed grid. Build 5 Stage 2
        # adds depth chart links for lakes that are not stocked ("gu-..."); their
        # grids come from static.ags.aer.ca, which this build could not reach yet,
        # so they show the Alberta link without the 3D model until fetched.
        stocked = {k for k in charts if not k.startswith("gu-")}
        self.assertEqual(stocked, {k for k in index["lakes"] if not k.startswith("gu-")})
        self.assertTrue(set(index["lakes"]) <= set(charts))
        self.assertEqual(len(stocked), 43)

    def test_every_grid_file_exists_with_one_cell_per_grid_point(self):
        index = load_index()
        for gd, g in index["grids"].items():
            path = ROOT / g["file"]
            self.assertTrue(path.exists(), g["file"])
            self.assertEqual(path.stat().st_size, g["w"] * g["h"] * 2, gd)
            self.assertLessEqual(max(g["w"], g["h"]), depth_grids.LONG_SIDE + 1)
        for v in index["lakes"].values():
            self.assertIn(v["grid"], index["grids"])

    def test_all_grids_stay_inside_the_size_target(self):
        total = sum((ROOT / g["file"]).stat().st_size for g in load_index()["grids"].values())
        self.assertLess(total, 1.5 * 1024 * 1024)

    def test_deepest_cell_matches_the_contour_map(self):
        # Depth is filled from the contour lines, so the deepest cell sits at
        # the deepest contour, within a metre and a half.
        for gd, g in load_index()["grids"].items():
            if g["contour_max_depth_m"]:
                self.assertLess(abs(g["max_depth_m"] - g["contour_max_depth_m"]), 1.5, gd)

    def test_each_grid_has_water_and_a_believable_north(self):
        for gd, g in load_index()["grids"].items():
            cells = struct.unpack("<%dh" % (g["w"] * g["h"]), (ROOT / g["file"]).read_bytes())
            self.assertGreater(sum(1 for c in cells if c > 0), 100, gd)
            # Alberta 10TM grid north is within 5 degrees of true north.
            self.assertLess(abs(g["north_deg"]), 5, gd)
            lat, lon = g["centre"]
            self.assertTrue(48.9 <= lat <= 60.1 and -120.1 <= lon <= -109.9, gd)

    def test_two_lakes_rebuild_byte_for_byte_from_the_saved_files(self):
        raw = json.loads((depth_grids.RAW / "index.json").read_text(encoding="utf-8"))
        info = json.loads((depth_grids.RAW / "levels_boundaries.json").read_text(encoding="utf-8"))
        contours = json.loads((depth_grids.RAW / "contours.json").read_text(encoding="utf-8"))
        index = load_index()
        for name in ("Chickakoo Lake", "Beaver Mines Lake"):
            r = raw[lake_id(index, name)]
            cells, meta = depth_grids.build_one(r["grid_dig"], r, info[r["contour_dig"]], contours[r["contour_dig"]]["lines"])
            saved = (ROOT / index["grids"][r["grid_dig"]]["file"]).read_bytes()
            self.assertEqual(meta["w"], index["grids"][r["grid_dig"]]["w"])
            self.assertEqual(len(cells), len(saved), name)
            # Same water and land everywhere; depths may differ by 1 dm where a
            # value sits on a rounding edge (Linux and Windows maths differ in
            # the last bits).
            a = struct.unpack("<%dh" % (len(cells) // 2), cells)
            b = struct.unpack("<%dh" % (len(saved) // 2), saved)
            self.assertEqual([x > 0 for x in a], [y > 0 for y in b], name)
            self.assertLessEqual(max(abs(x - y) for x, y in zip(a, b) if x > 0), 1, name)

    def test_10tm_round_trip(self):
        e, n = depth_grids.tm_forward(53.5, -113.5)
        lat, lon = depth_grids.tm_inverse(e, n)
        self.assertAlmostEqual(lat, 53.5, places=6)
        self.assertAlmostEqual(lon, -113.5, places=6)
        # 115 W is the central meridian: easting is the false easting there.
        self.assertAlmostEqual(depth_grids.tm_forward(55, -115)[0], 500000, places=3)


class BoatingRuleTests(unittest.TestCase):

    def rules(self):
        return json.loads(RULES.read_text(encoding="utf-8"))

    def rule(self, name):
        return self.rules()["lakes"][lake_id(load_index(), name)]

    def test_location_reading(self):
        self.assertIn((8, 3, "W4"), boating_rules.tc_places("23,25-8-3-W4"))
        self.assertEqual(boating_rules.tc_places("61-11,12-W5"), {(61, 11, "W5"), (61, 12, "W5")})
        self.assertIn((39, 1, "W5"), boating_rules.tc_places("39-1-2-W5"))
        self.assertIn((39, 2, "W5"), boating_rules.tc_places("39-1-2-W5"))
        self.assertEqual(boating_rules.ags_places(["005-03-W5, 035-07-W5"]), {(5, 3, "W5"), (35, 7, "W5")})

    def test_qualifiers_are_dropped_from_names(self):
        self.assertEqual(boating_rules.row_key("Sylvan Lake, as indicated by signs"), "sylvan")
        self.assertEqual(boating_rules.row_key("That part of Wabamun Lake that is a zone extending"), "wabamun")

    def test_transport_canada_wins_and_both_are_named(self):
        victor = self.rule("Victor Lake")
        self.assertEqual(victor["motor"], "electric")
        self.assertEqual(victor["kw_max"], 7.5)
        self.assertEqual(victor["mywildalberta"], "none")
        self.assertTrue(victor["differs"])
        self.assertEqual(len(victor["sources"]), 2)

    def test_a_same_name_lake_elsewhere_is_not_used(self):
        # Transport Canada's Cow Lake (28-7-W5) and Spring Lake (75-11-W6) are
        # other lakes of the same name.
        self.assertEqual(self.rule("Cow Lake")["tc_rows"], [])
        self.assertNotEqual(self.rule("Spring Lake")["motor"], "electric")

    def test_speed_limit_and_signed_zones(self):
        beaver = self.rule("Beaver Mines Lake")
        self.assertEqual(beaver["speed_kmh"], 12)
        self.assertTrue(beaver["signed_no_boat_zones"])
        sylvan = self.rule("Sylvan Lake")
        self.assertEqual(sylvan["speed_kmh_signed"], 12)
        self.assertTrue(sylvan["signed_no_boat_zones"])

    def test_mywildalberta_alone_and_no_rule(self):
        self.assertEqual(self.rule("Obed Lake")["motor"], "allowed")
        burn = self.rule("Burnstick Lake")
        self.assertIsNone(burn["motor"])
        self.assertEqual(burn["sources"], [])

    def test_the_licence_terms_travel_with_the_file(self):
        tc = self.rules()["sources"]["tc"]
        self.assertIn("Not the official version", tc["note"])
        self.assertTrue(tc["url"].startswith("https://tc.canada.ca/"))


if __name__ == "__main__":
    unittest.main()
