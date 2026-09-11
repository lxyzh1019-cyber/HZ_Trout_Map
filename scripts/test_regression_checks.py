import csv
import json
import statistics
import unittest
from pathlib import Path

import ats
import registry
import sources
import build_history as bh

ROOT = Path(__file__).parent.parent
PROFILES_CSV = ROOT / "profiles" / "mywildalberta_profiles.csv"
DATA_DIR = ROOT / "data"


def to_float(text):
    try:
        return float((text or "").strip())
    except (TypeError, ValueError):
        return None


class AtsGeometryTests(unittest.TestCase):
    def test_section_1_is_south_east_corner(self):
        self.assertEqual(ats.section_grid_xy(1), (5, 0))   # east column, south row
        self.assertEqual(ats.section_grid_xy(6), (0, 0))   # west column, south row
        self.assertEqual(ats.section_grid_xy(7), (0, 1))   # snake turns north
        self.assertEqual(ats.section_grid_xy(12), (5, 1))
        self.assertEqual(ats.section_grid_xy(31), (0, 5))
        self.assertEqual(ats.section_grid_xy(36), (5, 5))

    def test_east_column_is_closer_to_the_meridian(self):
        _, east_lon = ats.ats_to_latlng("SE1-20-5-W5")
        _, west_lon = ats.ats_to_latlng("SW6-20-5-W5")
        self.assertGreater(east_lon, west_lon)
        self.assertLess(abs(east_lon - west_lon), 0.2)     # five miles, not fifty

    def test_north_township_is_further_north(self):
        north, _ = ats.ats_to_latlng("SW1-100-5-W5")
        south, _ = ats.ats_to_latlng("SW1-1-5-W5")
        self.assertGreater(north, south)

    def test_township_1_starts_at_the_border(self):
        lat, _ = ats.ats_to_latlng("SW1-1-1-W4")
        self.assertAlmostEqual(lat, 49.0, delta=0.05)

    def test_meridians_anchor_longitude(self):
        for code, meridian in (("SE1-20-1-W4", -110.0), ("SE1-20-1-W5", -114.0),
                               ("SE1-20-1-W6", -118.0)):
            _, lon = ats.ats_to_latlng(code)
            self.assertLess(abs(lon - meridian), 0.05, code)

    def test_malformed_codes_return_none(self):
        for bad in ("", None, "nonsense", "XX1-2-3-W4", "NE99-2-3-W4", "NE1-2-3-W9"):
            self.assertEqual(ats.ats_to_latlng(bad), (None, None), repr(bad))


class AtsAccuracyTests(unittest.TestCase):
    """Guard the fix that moved every pin onto the right lake.

    The report gives a land description; the profiles CSV gives a hand-verified
    coordinate for the same lake. Two independent sources, so a correct
    conversion puts them within about a quarter-section of each other. Before
    the fix the median gap was 6.08 km.
    """

    @classmethod
    def setUpClass(cls):
        cls.gaps = []
        with open(PROFILES_CSV, newline="", encoding="cp1252") as f:
            for row in csv.DictReader(f):
                lat, lon = to_float(row.get("lat")), to_float(row.get("lon"))
                est_lat, est_lon = ats.ats_to_latlng(row.get("ats"))
                if lat is None or lon is None or est_lat is None:
                    continue
                cls.gaps.append(ats.haversine_km(lat, lon, est_lat, est_lon))

    def test_enough_lakes_to_be_meaningful(self):
        self.assertGreater(len(self.gaps), 200)

    def test_median_gap_stays_under_one_kilometre(self):
        self.assertLess(statistics.median(self.gaps), 1.0)

    def test_nearly_every_lake_lands_in_the_right_neighbourhood(self):
        within = sum(g <= 1.5 for g in self.gaps)
        self.assertGreater(within / len(self.gaps), 0.95)


class NameMatchingTests(unittest.TestCase):
    def test_keeps_the_words_that_distinguish_lakes(self):
        # Dropping "Reservoir" made these score a perfect 1.00 against each other.
        self.assertLess(registry.name_similarity("Chain Lakes Reservoir", "Chain Lake"), 0.95)

    def test_short_name_matches_its_own_longer_form(self):
        # Character similarity alone ranks "Jane Lake" above the right answer.
        payne = registry.name_similarity("Payne Lake", "Payne (Mami) Lake")
        jane = registry.name_similarity("Payne Lake", "Jane Lake")
        self.assertGreater(payne, jane)

    def test_sharing_only_a_generic_word_is_not_a_match(self):
        self.assertLess(registry.name_similarity("Muir Lake", "Spring Lake"), 0.7)

    def test_paired_lakes_are_flagged_as_conflicting(self):
        for a, b in (("Champion Lakes (Upper)", "Champion Lakes (Lower)"),
                     ("East Dollar Lake", "West Dollar Lake"),
                     ("Pierre Greys Lakes #1", "Pierre Greys Lakes #2")):
            self.assertTrue(registry.discriminating_conflict(a, b), f"{a} vs {b}")

    def test_a_shorter_name_is_not_a_conflict_with_itself(self):
        self.assertFalse(registry.discriminating_conflict("Alford Lake", "Alford Lake"))


class SourceReaderTests(unittest.TestCase):
    """Every year must be readable, with the fields that year is meant to have."""

    @classmethod
    def setUpClass(cls):
        cls.rows = {y: sources.read_year(y) for y in sorted(sources.YEAR_SOURCES)}

    def test_every_year_yields_rows(self):
        for year, rows in self.rows.items():
            self.assertGreater(len(rows), 150, f"{year} produced only {len(rows)} rows")

    def test_every_row_has_a_species_a_count_and_a_date(self):
        for year, rows in self.rows.items():
            for r in rows:
                self.assertTrue(r["species"], year)
                self.assertIsInstance(r["number"], int)
                self.assertGreater(r["number"], 0)
                self.assertRegex(r["date"] or "", r"^\d{4}-\d{2}-\d{2}$", f"{year} {r}")

    def test_dates_fall_in_their_own_season(self):
        for year, rows in self.rows.items():
            for r in rows:
                self.assertEqual(int(r["date"][:4]), year, f"{year} {r['date']}")

    def test_waterbody_id_present_exactly_where_expected(self):
        with_id = {y for y, rows in self.rows.items() if any(r["waterbody_id"] for r in rows)}
        self.assertEqual(with_id, {2012, 2013, 2014, 2016, 2017, 2018, 2019})

    def test_early_reports_are_month_precision(self):
        for year in (2011, 2012, 2013):
            if sources.YEAR_SOURCES[year][0] != "pdf_early":
                continue
            self.assertTrue(all(r["date_precision"] == "month" for r in self.rows[year]), year)

    def test_district_names_are_not_welded_to_the_lake_name(self):
        # "ROCKY MOUNTAIN HOUSE" + "TWIN LAKE" once came out as
        # "MOUNTAIN HOUSETWIN LAKE" because the PDF fuses the two words.
        for r in self.rows[2015]:
            self.assertNotRegex(r["official_name"], r"HOUSE[A-Z]", r["official_name"])
            self.assertNotIn("MEDICINE", r["official_name"])

    def test_modern_reports_keep_strain_out_of_the_lake_name(self):
        for year in (2025, 2026):
            for r in self.rows[year]:
                self.assertNotIn("Lodge/", r["official_name"], f"{year} {r['official_name']}")
                self.assertNotIn("Kamloops", r["official_name"], f"{year} {r['official_name']}")

    def test_genotypes_are_not_sliced_in_half(self):
        for year in (2025, 2026):
            for r in self.rows[year]:
                if r["genotype"]:
                    self.assertRegex(r["genotype"], r"^A?F?[23]N[A-Z]*$",
                                     f"{year} {r['genotype']} / {r['strain']}")


class LinkingAccuracyTests(unittest.TestCase):
    """Hold out real years and check the linker against Alberta's own ids.

    The registry is built from 2012-2016, then 2017-2019 are linked with the
    waterbody id and the published coordinates hidden — leaving only a name and
    a land description, which is exactly what 2021 onward gives us. Every
    answer is then compared against the id that was hidden.

    The bar is not "mostly right". A wrong link silently merges two lakes'
    histories and nobody ever notices, so the test demands zero.
    """

    @classmethod
    def setUpClass(cls):
        rows = {y: sources.read_year(y) for y in range(2012, 2020)}
        cls.reg = bh.build_spine({y: rows[y] for y in range(2012, 2017)})
        bh.attach_profiles(cls.reg)
        bh.settle_coordinates(cls.reg)
        cls.correct = cls.wrong = cls.review = cls.absent = cls.absent_linked = 0
        for year in (2017, 2018, 2019):
            for r in rows[year]:
                if r["species"] not in sources.TROUT_SPECIES or not r["waterbody_id"]:
                    continue
                blind = dict(r, waterbody_id=None, lat=None, lon=None)
                lake, *_ = cls.reg.resolve(blind)
                if f"wb{r['waterbody_id']}" not in cls.reg.by_id:
                    cls.absent += 1
                    if lake is not None:
                        cls.absent_linked += 1
                elif lake is None:
                    cls.review += 1
                elif lake["lake_id"] == f"wb{r['waterbody_id']}":
                    cls.correct += 1
                else:
                    cls.wrong += 1

    def test_the_sample_is_large_enough_to_mean_something(self):
        self.assertGreater(self.correct + self.wrong + self.review, 1000)

    def test_no_row_is_ever_linked_to_the_wrong_lake(self):
        self.assertEqual(self.wrong, 0)

    def test_lakes_absent_from_the_registry_are_never_absorbed_into_another(self):
        self.assertGreater(self.absent, 0, "no held-out lakes, so this proves nothing")
        self.assertEqual(self.absent_linked, 0)

    def test_most_rows_link_without_a_human(self):
        total = self.correct + self.wrong + self.review
        self.assertGreater(self.correct / total, 0.95)


class PublishedDataTests(unittest.TestCase):
    """The committed data is what GitHub Pages serves, so check it directly."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
        cls.years = cls.manifest["years"]
        cls.by_year = {y: json.loads((DATA_DIR / f"lakes_{y}.json").read_text(encoding="utf-8"))
                       for y in cls.years}
        cls.registry = json.loads((DATA_DIR / "lake_registry.json").read_text(encoding="utf-8"))

    def test_the_manifest_covers_every_year_we_can_read(self):
        self.assertEqual(sorted(self.years), sorted(sources.YEAR_SOURCES))

    def test_the_current_season_is_marked_provisional(self):
        self.assertEqual(sorted(self.manifest["provisional"]),
                         sorted(sources.PROVISIONAL_YEARS))

    def test_every_lake_has_an_identity_and_a_declared_coordinate_source(self):
        for year, lakes in self.by_year.items():
            for lk in lakes:
                self.assertTrue(lk.get("lake_id"), f"{year} {lk['name']}")
                self.assertIn(lk.get("coord_source"),
                              ("profile", "alberta", "ats", "unknown"), lk["name"])
                # A missing position is allowed only when it is declared as
                # such, never as a silent null that would drop a pin.
                if lk.get("lat") is None or lk.get("lon") is None:
                    self.assertEqual(lk["coord_source"], "unknown", f"{year} {lk['name']}")

    def test_almost_every_lake_can_be_placed_on_the_map(self):
        registry_ids = {lk["lake_id"] for lk in self.registry}
        unplaced = {lk["lake_id"] for lk in self.registry if lk["coord_source"] == "unknown"}
        self.assertLess(len(unplaced) / len(registry_ids), 0.02,
                        f"{len(unplaced)} lakes have no position")

    def test_coordinates_are_inside_alberta(self):
        for year, lakes in self.by_year.items():
            for lk in (l for l in lakes if l["lat"] is not None):
                self.assertTrue(48.9 < lk["lat"] < 60.1, f"{year} {lk['name']} {lk['lat']}")
                self.assertTrue(-120.5 < lk["lon"] < -109.9, f"{year} {lk['name']} {lk['lon']}")

    def test_most_lakes_use_a_verified_coordinate(self):
        for year, lakes in self.by_year.items():
            verified = sum(lk["coord_source"] != "ats" for lk in lakes)
            self.assertGreater(verified / len(lakes), 0.9, year)

    def test_a_lake_id_means_the_same_lake_in_every_year(self):
        """The whole point of the registry: one id, one place, one name."""
        seen = {}
        for year, lakes in self.by_year.items():
            for lk in lakes:
                prev = seen.setdefault(lk["lake_id"], lk)
                self.assertEqual(prev["name"], lk["name"], lk["lake_id"])
                if prev["lat"] is not None and lk["lat"] is not None:
                    self.assertAlmostEqual(prev["lat"], lk["lat"], places=4)
                    self.assertAlmostEqual(prev["lon"], lk["lon"], places=4)

    def test_no_two_lakes_share_a_name_and_a_position(self):
        for year, lakes in self.by_year.items():
            keyed = [(lk["name"], round(lk["lat"], 4), round(lk["lon"], 4))
                     for lk in lakes if lk["lat"] is not None]
            self.assertEqual(len(keyed), len(set(keyed)), year)

    def test_stocking_rows_are_well_formed(self):
        allowed = sources.TROUT_SPECIES
        for year, lakes in self.by_year.items():
            for lk in lakes:
                for s in lk["stockings"]:
                    self.assertIn(s["species"], allowed, f"{year} {lk['name']}")
                    self.assertIsInstance(s["number"], int)
                    self.assertGreater(s["number"], 0)
                    self.assertRegex(s["date"], r"^\d{4}-\d{2}-\d{2}$")
                    self.assertEqual(int(s["date"][:4]), year)
                    self.assertIn(s["date_precision"], ("day", "month"))

    def test_total_fish_matches_the_stocking_rows(self):
        for year, lakes in self.by_year.items():
            for lk in lakes:
                self.assertEqual(lk["total_fish"], sum(s["number"] for s in lk["stockings"]),
                                 f"{year} {lk['name']}")

    def test_every_year_carries_a_plausible_amount_of_data(self):
        for year, lakes in self.by_year.items():
            self.assertGreater(len(lakes), 100, year)
            total = sum(lk["total_fish"] for lk in lakes)
            self.assertGreater(total, 500_000, f"{year} stocked only {total}")

    def test_registry_ids_are_unique_and_cover_the_year_files(self):
        ids = [lk["lake_id"] for lk in self.registry]
        self.assertEqual(len(ids), len(set(ids)))
        known = set(ids)
        for year, lakes in self.by_year.items():
            for lk in lakes:
                self.assertIn(lk["lake_id"], known, f"{year} {lk['name']}")


if __name__ == "__main__":
    unittest.main()
