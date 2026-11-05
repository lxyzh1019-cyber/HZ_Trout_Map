"""Build 5 Stage 2 data checks: the guide's waters that are not stocked, its river
stretches, the rule rows they carry, and the heights for each of them.

    PYTHONPATH=scripts python3 -m unittest scripts/test_build5_waters.py

These read data/ only (and scripts/waterbodies.py for its name helpers), so
they run without the CanVec or CGNDB downloads.
"""

import csv
import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"


def km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, h)))


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def stocked():
    """lake key -> (name, lat, lon), the last year's position winning, as the page does."""
    out = {}
    for path in sorted(DATA.glob("lakes_20*.json")):
        for lk in json.loads(path.read_text(encoding="utf-8")):
            key = lk.get("lake_id") or lk.get("ats")
            if lk.get("lat") is not None and lk.get("lon") is not None:
                out[key] = (lk["name"], lk["lat"], lk["lon"])
    return out


class Build5WatersTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.waters = load("waters_unstocked.json")
        cls.rivers = load("rivers.json")
        cls.regs = load("lake_regulations.json")["lakes"]
        cls.stocked = stocked()
        with (DATA / "waters_review.csv").open(newline="", encoding="utf-8") as f:
            cls.review = list(csv.DictReader(f))
        cls.lake = {(l["name"], l["zone"]): l for l in cls.waters["lakes"]}
        cls.by_id = {s["lake_id"]: s for s in cls.rivers["stretches"]}

    # ---------------------------------------------------------- rule rows
    def test_every_stretch_has_rules_with_a_season(self):
        for s in self.rivers["stretches"]:
            rules = s.get("rules")
            self.assertTrue(rules, s["lake_id"])
            self.assertIn("season", rules, s["lake_id"])
            self.assertIn("text", rules["season"], s["lake_id"])
            self.assertNotIn("rows", s, "the rows are in rules.also now")
            for a in rules.get("also") or []:
                self.assertIn("detail", a, s["lake_id"])
                self.assertIn("text", a["season"], s["lake_id"])
                for k in ("bait", "species", "trout_total", "page"):
                    self.assertIn(k, a, (s["lake_id"], k))
            # A line that stands for parts with different seasons is neither open nor
            # closed as a whole, and lists every part.
            if rules["season"]["text"] == "See each part below":
                self.assertIn(s["limits"], ("unit", "estimated"), s["lake_id"])
                self.assertGreaterEqual(len([a for a in rules["also"] if a["detail"] != "(same stretch)"]), 2)

    def test_grouped_stretches_keep_every_guide_row(self):
        bow = self.by_id["rv-pp1-bow-river-1"]["rules"]
        self.assertEqual(bow["season"]["text"], "See each part below")
        self.assertEqual([a["season"]["text"] for a in bow["also"]], ["OPEN ALL YEAR", "OPEN MAY 8 TO MAR. 15"])
        self.assertTrue(bow["also"][1]["detail"].startswith("Bassano Dam downstream"))
        self.assertEqual(bow["bait"], "", "the parts differ on bait: nothing is said for the whole line")
        owl = self.by_id["rv-nb1-owl-river-1"]["rules"]
        self.assertEqual(owl["season"]["text"], "See each part below")
        self.assertEqual({a["season"]["text"] for a in owl["also"]}, {"CLOSED ALL YEAR", "OPEN JUNE 1 TO OCT. 31"})
        battle = self.by_id["rv-pp2-battle-river-1"]["rules"]
        self.assertEqual(battle["season"]["text"], "See each part below")
        self.assertEqual(len(battle["also"]), 4)
        self.assertEqual(sum(1 for a in battle["also"] if a.get("see")), 2, "the two See ... rows")
        for a in battle["also"]:
            self.assertTrue(a["season"]["text"], "a See ... row is never shown as closed")

    def test_a_blank_detail_row_is_another_period_of_the_same_stretch(self):
        for sid in ("rv-es1-jumpingpound-creek-1", "rv-es1-waiparous-creek-1"):
            rules = self.by_id[sid]["rules"]
            self.assertEqual(rules["detail"], "Includes tributaries")
            self.assertEqual(len(rules["also"]), 1, sid)
            self.assertEqual(rules["also"][0]["detail"], "(same stretch)")
            self.assertEqual(rules["also"][0]["season"]["text"], "OPEN SEPT. 1 TO OCT. 31")
            # Open in either period (the app reads every range of a season).
            self.assertEqual(rules["season"]["text"], "OPEN JUNE 16 TO AUG. 31 AND SEPT. 1 TO OCT. 31")
            self.assertEqual(rules["also"][0]["species"]["MNWH"]["count"], 0)

    def test_guide_rows_reach_the_stocked_twins(self):
        kehewin = self.regs["wb4977"]
        self.assertEqual(kehewin["basis"], "site-specific")
        self.assertEqual(kehewin["matched_name"], "Kehiwin Lake")
        self.assertEqual(kehewin["confirmed_by"], "Build 5 match")
        for key in ("wb6605", "wb6606"):          # Lower and Upper Smuts Lake
            smuts = self.regs[key]
            self.assertEqual(smuts["basis"], "site-specific", key)
            self.assertEqual(smuts["matched_name"], "Smuts Lakes", key)
            self.assertEqual(smuts["season"]["text"], "OPEN ALL YEAR", key)
        for key, name in (("wb4265", "Chin Lakes"), ("wb5568", "Phillips Lake"), ("wb6044", "Twin Lakes")):
            self.assertEqual(self.regs[key]["matched_name"], name, key)
            self.assertEqual(self.regs[key]["basis"], "site-specific", key)
        # The twin is not a second pin.
        for name, zone in (("Kehiwin Lake", "NB1"), ("Smuts Lakes", "ES1"), ("Sawn Lake", "NB3")):
            self.assertNotIn((name, zone), self.lake)

    # ---------------------------------------------------------- places
    def test_red_deer_below_the_dickson_dam_starts_at_the_dam(self):
        s = self.by_id["rv-pp2-red-deer-river-1"]
        self.assertTrue(s["detail"].startswith("Mainstem from Dickson Dam"))
        dam = (52.05, -114.22)                    # east end of Gleniffer Lake
        self.assertLess(km(s["line"][0][0], dam), 2.0, s["line"][0][0])

    def test_no_stretch_duplicates_a_stocked_water(self):
        """A stretch of a river that is on the map as a stocked water names that
        lake in stocked_twin (the app shows one pin); no other stretch has one."""
        names = {}
        for key, (name, lat, lon) in self.stocked.items():
            names.setdefault(name.casefold(), []).append((key, lat, lon))
        for s in self.rivers["stretches"]:
            near = [key for key, lat, lon in names.get(s["name"].casefold(), [])
                    if min(km((lat, lon), p) for p in s["spots"]) <= 30]
            if near:
                self.assertIn(s.get("stocked_twin"), near, s["lake_id"])
            else:
                self.assertNotIn("stocked_twin", s, s["lake_id"])
        self.assertEqual(self.by_id["rv-es1-kananaskis-river-1"]["stocked_twin"], "wb2081")
        self.assertEqual(self.by_id["rv-nb1-medley-river-1"]["stocked_twin"], "wb2129")
        why = {(r["lake"], r["why"]) for r in self.review}
        self.assertIn(("Kananaskis River", "on the map as a stocked water"), why)
        self.assertIn(("Medley River", "on the map as a stocked water"), why)

    def test_rivers_with_no_line_are_in_the_review_file(self):
        # No CanVec line of the name at all, or none in the zone (the line there is
        # in a neighbouring unit by the nearest stocked lakes).
        missing = {r["lake"] for r in self.review if r["why"] in (
            "no river line of that name in the water data", "no river line of that name in the zone")}
        for name in ("South Castle River", "Redwater River", "Muskwa River",
                     "Nipisi River", "Birch Creek", "Monday Creek", "Sunday Creek"):
            self.assertIn(name, missing)
        # Piche River is "Piché River" in CanVec: found once accents are dropped.
        self.assertIn("rv-nb1-piche-river-1", self.by_id)
        placed = {s["name"] for s in self.rivers["stretches"]}
        self.assertFalse(missing & placed)

    def test_big_lakes_and_accented_names_are_placed(self):
        buffalo = self.lake[("Buffalo Lake", "PP2")]
        self.assertLess(km((buffalo["lat"], buffalo["lon"]), (52.47, -112.9)), 10)
        self.assertGreater(buffalo["surface_area_ha"], 8000)
        utikuma = self.lake[("Utikuma Lake", "NB3")]
        self.assertGreater(utikuma["surface_area_ha"], 20000)
        sante = self.lake[("Lac Sante", "NB1")]       # Lac Santé in the place names
        self.assertLess(km((sante["lat"], sante["lon"]), (53.84, -111.55)), 3)
        self.assertIn(("Berry Creek (Carolside) Reservoir", "PP2"), self.lake)

    def test_name_helpers(self):
        import waterbodies as w
        self.assertEqual(w.norm("Lac Santé"), "lac sante")
        self.assertEqual(w.slug("Lac Santé"), "lac-sante")
        self.assertTrue(w.similar("Sawn Lake", "Swan Lake"))
        self.assertTrue(w.similar("Kehiwin Lake", "Kehewin Lake"))
        self.assertFalse(w.similar("Swan Lake", "Snaw Lake"))
        self.assertFalse(w.flowing("Berry Creek (Carolside) Reservoir"))
        self.assertTrue(w.flowing("Jumpingpound Creek"))

    # ---------------------------------------------------------- heights and credits
    def test_heights_cover_every_water_and_spot(self):
        rec = load("lake_elevation.json")
        want = {}
        for key, (_, lat, lon) in self.stocked.items():
            want[key] = (lat, lon)
        for l in self.waters["lakes"]:
            want.setdefault(l["lake_id"], (l["lat"], l["lon"]))
        for s in self.rivers["stretches"]:
            for i, p in enumerate(s["spots"]):
                want[f"{s['lake_id']}#{i}"] = tuple(p)
        self.assertEqual(set(rec["lakes"]), set(want))
        self.assertEqual(set(rec["points"]), set(want))
        self.assertEqual(rec["count"], len(want))
        for key, p in want.items():
            self.assertIsInstance(rec["lakes"][key], (int, float), key)
            self.assertLess(km(rec["points"][key], p), 0.1, f"{key}: the height was asked for elsewhere")

    def test_water_source_is_canvec_50k(self):
        for rec in (self.waters, self.rivers):
            self.assertIn("1:50,000", rec["source"]["water"])
            self.assertNotIn("250,000", rec["source"]["water"])
        src = (ROOT / "scripts" / "waterbodies.py").read_text(encoding="utf-8")
        self.assertNotIn("250,000", src)
        self.assertNotIn("250K", src)



class Build5ZoneTests(unittest.TestCase):
    """Zones from Alberta's regulations map (data/lake_zones.csv), the zone of each
    entry in the guide's put-and-take list, and the guide rows they let attach."""

    @classmethod
    def setUpClass(cls):
        cls.regs = load("lake_regulations.json")["lakes"]
        cls.lakes = {}
        for path in sorted(DATA.glob("lakes_20*.json")):
            for lk in json.loads(path.read_text(encoding="utf-8")):
                cls.lakes[lk["lake_id"]] = lk
        with (DATA / "lake_zones.csv").open(newline="", encoding="utf-8") as f:
            cls.zones = list(csv.DictReader(f))

    def by_name(self, name):
        hits = [k for k, lk in self.lakes.items() if lk["name"] == name]
        self.assertTrue(hits, name)
        return hits[0]

    def test_lakes_that_had_no_zone_now_have_their_guide_rows(self):
        for name, zone in [("Headwall Lakes (Lower Headwall Lake)", "ES1"),
                           ("Memorial Lakes (West Memorial Lake)", "ES1"),
                           ("Running Rain Lake (Storm Lake)", "ES1"),
                           ("Lower Kananaskis Lake", "ES1"),
                           ("Wabamun Lake", "PP2")]:
            key = self.by_name(name)
            self.assertEqual(self.lakes[key]["zone"], zone, name)
            self.assertEqual(self.regs[key]["basis"], "site-specific", name)

    def test_a_wrong_profile_zone_is_replaced_only_when_the_guide_agrees(self):
        key = self.by_name("Pine Coulee Reservoir")
        self.assertEqual(self.lakes[key]["zone"], "ES1")
        self.assertEqual(self.regs[key]["basis"], "site-specific")
        self.assertEqual(self.lakes[self.by_name("Brooks Aquaduct Pond")]["zone"], "PP1")
        # The guide names Victor Lake in two zones; Alberta's map, which finds
        # the lake by its waterbody id, decides.
        self.assertEqual(self.lakes[self.by_name("Victor Lake")]["zone"], "ES4")
        # No guide row in Alberta's zone (NB3): the profile's ES4 stays.
        key = next(k for k, lk in self.lakes.items() if lk["name"].startswith("Montagneuse"))
        row = next(r for r in self.zones if r["lake_id"] == key)
        self.assertEqual(row["alberta_zone"], "NB3")
        self.assertEqual(self.lakes[key]["zone"], "ES4")

    def test_zones_reach_the_year_files(self):
        for r in self.zones:
            lk = self.lakes.get(r["lake_id"])
            if lk and r["alberta_zone"] and r["alberta_zone"] in r["guide_zones"].split():
                self.assertEqual(lk["zone"], r["alberta_zone"], r["name"])
        missing = sorted(lk["name"] for lk in self.lakes.values() if not lk.get("zone"))
        self.assertEqual(missing, ["Morinville Lake", "Niton Pond"])

    def test_put_and_take_entries_carry_their_watershed_unit(self):
        import regulations
        st = regulations.load(DATA / "raw" / "alberta-sportfishing-regulations-2026-tables.pdf")["stocked"]
        self.assertTrue(all(v.get("zone") for v in st.values()))
        for name, zone in [("Allison Lake", "ES1"), ("Dickson Trout Pond", "ES2"),
                           ("Mayan Lake", "ES3"), ("Brooks Aquaduct Pond", "PP1"),
                           ("Castor Eastside Trout Pond", "PP2"), ("Michichi Reservoir", "PP2"),
                           ("Chatwin Lake", "NB1")]:
            self.assertEqual(st[name]["zone"], zone, name)
        # Two entries on one printed line, from two columns, used to read as one.
        for name in ("Kramer Pond", "Innisfree Trout Pond", "Ashland Reservoir", "Boulder Lake"):
            self.assertIn(name, st)
        self.assertEqual(self.regs[self.by_name("Kramer Pond")]["basis"], "put-and-take")


class Build5ZoneHelperTests(unittest.TestCase):
    """scripts/lake_zones.py and the --lakes-only and height rules, offline."""

    def test_zone_code_and_point_zone_with_a_hole(self):
        import lake_zones as lz
        self.assertEqual(lz.zone_code("NB3", "00009"), "NB3")
        self.assertEqual(lz.zone_code("ES1 - Eastern Slopes", None), "ES1")
        with self.assertRaises(ValueError):
            lz.zone_code("Zone", "1")
        outer = [[0, 0], [10, 0], [10, 10], [0, 10]]
        hole = [[4, 4], [6, 4], [6, 6], [4, 6]]
        island = [[4, 4], [6, 4], [6, 6], [4, 6]]
        outlines = [("ES1", [outer, hole], (0, 0, 10, 10)), ("PP1", [island], (4, 4, 6, 6))]
        self.assertEqual(lz.point_zone(outlines, 2, 2), "ES1")
        self.assertEqual(lz.point_zone(outlines, 5, 5), "PP1")      # in ES1's hole, in PP1
        self.assertIsNone(lz.point_zone(outlines, 50, 50))          # far outside every outline
        self.assertEqual(lz.point_zone(outlines, 5, 10.01, near_km=5), "ES1")  # a sliver past the edge

    def test_a_same_named_lake_elsewhere_confirms_nothing(self):
        import lake_zones as lz
        lake = {"name": "Swan Lake", "lat": 56.98, "lon": -115.92}
        far = {"swanlake": [("ES2", (52.0, -115.0)), ("ES4", (54.0, -118.0))]}
        self.assertEqual(lz.confirming_zones(lake, far), set())
        near = {"swanlake": [("NB3", (56.95, -115.90))]}
        self.assertEqual(lz.confirming_zones(lake, near), {"NB3"})
        # No land description: only the lake's own name, and only if it is in one zone.
        self.assertEqual(lz.confirming_zones(lake, {"swanlake": [("NB3", None)]}), {"NB3"})
        self.assertEqual(lz.confirming_zones(lake, {"swanlake": [("NB3", None), ("ES2", None)]}), set())
        bracket = {"name": "Little Bear Lake (Hasse Lake)", "lat": 53.5, "lon": -114.2}
        self.assertEqual(lz.confirming_zones(bracket, {"hasselake": [("PP2", None)]}), set())

    def test_lakes_only_keeps_the_river_rows(self):
        import waterbodies as wb
        regs = {"zones": {"ES1": {"rivers": {"Bow River": {}}, "lakes": {"Elbow River": {}, "Bow Lake": {}}}}}
        names = wb.river_names(regs)
        self.assertIn(wb.norm("Bow River"), names)
        self.assertIn(wb.norm("Elbow River"), names)
        self.assertNotIn(wb.norm("Bow Lake"), names)

    def test_a_refused_height_stops_the_build(self):
        import elevation
        import waterbodies as wb
        real, cache = elevation.fetch, dict(wb.HEIGHT_CACHE)
        try:
            def refuse(points):
                raise RuntimeError("Daily API request limit exceeded")
            elevation.fetch = refuse
            wb.HEIGHT_CACHE["path"] = None
            with self.assertRaises(SystemExit):
                wb.heights_of([(52.0, -114.0), (52.1, -114.1)])
        finally:
            elevation.fetch = real
            wb.HEIGHT_CACHE.update(cache)


if __name__ == "__main__":
    unittest.main()
