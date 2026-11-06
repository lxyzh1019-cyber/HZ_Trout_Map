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


if __name__ == "__main__":
    unittest.main()
