"""Build 5 Stage 3b: Species mode, and the species recorded in each water.

    PYTHONPATH=scripts python3 -m unittest scripts/test_species_mode.py
"""

import csv
import json
import unittest
from pathlib import Path

import species_presence as sp

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


class SpeciesPresenceDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads((DATA / "species_presence.json").read_text(encoding="utf-8"))
        cls.p = cls.doc["presence"]

    def test_only_presence_is_kept_never_a_2021_rule(self):
        # The owner: the 2021 guide is for species confirmation only (2026-11-06).
        text = (DATA / "species_presence.json").read_text(encoding="utf-8")
        for word in ("season", "limit", "bait", "OPEN ", "CLOSED"):
            self.assertNotIn(word, text.replace("species presence only", ""), word)
        allowed = {"guide2021", "stocked", "reports"}
        for key, rec in self.p.items():
            self.assertTrue(set(rec) <= set(sp.MODE_SPECIES), key)
            for code, srcs in rec.items():
                self.assertTrue(srcs and set(srcs) <= allowed, (key, code, srcs))

    def test_every_key_is_an_app_water_and_the_counts_add_up(self):
        waters = sp.app_waters()
        self.assertTrue(set(self.p) <= set(waters))
        self.assertEqual(self.doc["waters"], len(waters))
        for code in sp.MODE_SPECIES:
            self.assertEqual(self.doc["counts"][code], sum(1 for r in self.p.values() if code in r), code)
        self.assertGreater(self.doc["counts"]["WALL"], 100)
        self.assertGreater(self.doc["counts"]["MNWH"], 20)

    def test_the_lakes_read_from_the_2021_tables(self):
        # Page 65 of the 2021 guide: Sylvan and Gull list walleye, lake whitefish and burbot;
        # Pine Lake walleye (with pike and perch); Wizard Lake only pike and perch.
        self.assertEqual(set(self.p["wb5952"]), {"WALL", "BURB", "LKWH"})
        self.assertIn("guide2021", self.p["wb5952"]["WALL"])
        self.assertEqual(set(self.p["gu-pp2-gull-lake"]), {"WALL", "BURB", "LKWH"})
        self.assertEqual(set(self.p["gu-pp2-pine-lake"]), {"WALL"})
        self.assertNotIn("gu-pp2-wizard-lake", self.p)

    def test_the_source_is_named_with_its_checksum(self):
        g = self.doc["sources"]["guide2021"]
        self.assertTrue(g["url"].startswith("https://open.alberta.ca/"))
        self.assertRegex(g["sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("presence only", self.doc["about"])

    def test_names_too_close_to_call_are_listed_not_used(self):
        with (DATA / "species_review.csv").open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertTrue(rows)
        for r in rows:
            self.assertLess(float(r["score"]), 0.92)
            rec = self.p.get(r["key"], {})
            self.assertFalse(any("guide2021" in s for s in rec.values()), r)


SCORE = """(function () {
  var C = window.Conditions;
  function at(mode, iso, opts) {
    var when = new Date(iso), lat = 52.36, lon = -114.15;
    var astro = window.Astro.dayFor(lat, lon, new Date(when.getFullYear(), when.getMonth(), when.getDate()));
    var o = Object.assign({ when: when, lat: lat, lon: lon, species: ["RNTR"], astro: astro, mode: mode,
      weather: { cloudCoverPct: 20, dP3h: 0, dP12h: 0, windKph: 10, gustKph: 15, precipMm: 0, pressureMslHpa: 1010 },
      water: { tempC: 8, source: "modeled", sigmaC: 2 }, leadDays: 0 }, opts || {});
    return C.scoreSlot(o);
  }
  var noonJul = "2026-07-15T19:00:00Z", midnightJul = "2026-07-16T07:00:00Z";
  var noonFeb = "2026-02-15T19:00:00Z", midnightFeb = "2026-02-16T07:00:00Z";
  var t1 = at(null, noonJul), t2 = at(undefined, noonJul), t3 = at("XXXX", noonJul);
  var burbFebNight = at("BURB", midnightFeb, { water: { tempC: 2, source: "modeled", sigmaC: 2 } });
  var burbJulNight = at("BURB", midnightJul, { water: { tempC: 2, source: "modeled", sigmaC: 2 } });
  return {
    troutSame: t1.scoreRaw === t2.scoreRaw && t1.scoreRaw === t3.scoreRaw && t1.mode === null,
    troutLight: C._internal.lightScore(40, null, null),
    burbNight: at("BURB", midnightJul).factors.light.s, burbNoon: at("BURB", noonJul).factors.light.s,
    troutNight: at(null, midnightJul).factors.light.s,
    burbFeb: burbFebNight.scoreRaw, burbJul: burbJulNight.scoreRaw, burbFebNote: burbFebNight.seasonNote,
    burbWinterFeb: C.scoreWinter(burbFebNight).scoreRaw, burbWinterJul: C.scoreWinter(burbJulNight).scoreRaw,
    wallNoon: at("WALL", noonJul).factors.light.s, wallSpecies: at("WALL", noonJul).factors.water.species,
    lkwhJan: C._internal.seasonFor("LKWH", new Date("2026-01-20T12:00:00Z")),
    weights: C.WEIGHTS,
    whySum: (function () { var r = burbFebNight, w = C.whyParts(r); return [w.total, w.parts.reduce(function (a, p) { return a + p.points; }, 0)]; })()
  };
})()"""


class SpeciesScoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_regression_checks import run_js
        cls.r = run_js(["astro.js", "conditions.js"], SCORE)

    def test_trout_mode_is_todays_model(self):
        self.assertTrue(self.r["troutSame"])
        self.assertEqual(self.r["troutLight"], 0.20)            # high sun, trout floor unchanged
        self.assertEqual(self.r["weights"], {"light": 0.40, "water": 0.35, "pressure": 0.15, "wind": 0.06, "precip": 0.04})

    def test_burbot_feed_at_night_and_peak_under_the_ice_in_february(self):
        self.assertGreater(self.r["burbNight"], self.r["burbNoon"])
        self.assertGreater(self.r["burbNight"], self.r["troutNight"])
        self.assertGreater(self.r["burbFeb"], self.r["burbJul"])
        self.assertGreater(self.r["burbWinterFeb"], self.r["burbWinterJul"])
        self.assertIn("Alberta, Feb", self.r["burbFebNote"])

    def test_walleye_dislike_bright_sun_and_score_on_their_own_band(self):
        self.assertLess(self.r["wallNoon"], self.r["troutLight"] + 0.01)
        self.assertEqual(self.r["wallSpecies"], "WALL")

    def test_lake_whitefish_winter_is_good_season_and_the_parts_add_up(self):
        self.assertGreater(self.r["lkwhJan"]["mult"], 1)
        self.assertIn("shallow flats over mud", self.r["lkwhJan"]["note"])
        total, parts = self.r["whySum"]
        self.assertEqual(total, parts)


class SpeciesViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.sheet = (ROOT / "js" / "lake-sheet.js").read_text(encoding="utf-8")

    def test_the_switch_and_its_memory(self):
        self.assertIn('<div class="chips" id="mode-chips" role="radiogroup" aria-label="Fishing for"></div>', self.page)
        self.assertIn('const STORE_SPECIES = "troutmap.species";', self.page)
        self.assertIn('const SPECIES_MODES = { WALL: "Walleye", BURB: "Burbot", LKWH: "Lake whitefish", MNWH: "Mountain whitefish" };', self.page)
        fx = (ROOT / "js" / "forecast.js").read_text(encoding="utf-8")
        self.assertIn('(speciesMode() || "trout") + ":"', fx)          # switching re-scores
        ui = (ROOT / "js" / "conditions-ui.js").read_text(encoding="utf-8")
        self.assertIn("species: scoringSpecies(lake), mode: speciesMode()", ui)

    def test_alberta_experience_first_and_the_bait_rule_kept(self):
        self.assertIn("shallow flats over mud are very productive in Alberta (owner's experience: Sylvan, Gull, Lake Newell)", self.sheet)
        self.assertIn("goby-style lures, popular in Ontario, do less well here (owner's experience)", self.sheet)
        self.assertIn('(ban ? " Bait ban here (2026 guide): fish it without bait." : "")', self.sheet)
        self.assertIn("not recorded here</b>: check before you go.", self.sheet)
        # Every study from outside Alberta names its place.
        for place in ("Wisconsin", "China", "Utah, USA"):
            self.assertIn(place, self.sheet)

    def test_presence_is_offline_and_on_the_evidence_page(self):
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn('"data/species_presence.json"', sw)
        ev = (ROOT / "evidence.html").read_text(encoding="utf-8")
        self.assertIn('<tr data-band="BURB">', ev)
        self.assertIn("Ussuri River, China", ev)


if __name__ == "__main__":
    unittest.main()
