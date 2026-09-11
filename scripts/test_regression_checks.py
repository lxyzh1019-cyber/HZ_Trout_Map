import csv
import json
import statistics
import tempfile
import unittest
from pathlib import Path

import ats
import check_consistency
import merge_profiles


PROFILES_CSV = Path(__file__).parent.parent / "profiles" / "mywildalberta_profiles.csv"


class AtsGeometryTests(unittest.TestCase):
    def test_section_1_is_south_east_corner(self):
        # Sections are numbered from the SE corner, snaking west.
        self.assertEqual(ats.section_grid_xy(1), (5, 0))   # east column, south row
        self.assertEqual(ats.section_grid_xy(6), (0, 0))   # west column, south row
        self.assertEqual(ats.section_grid_xy(7), (0, 1))   # snake turns north
        self.assertEqual(ats.section_grid_xy(12), (5, 1))
        self.assertEqual(ats.section_grid_xy(31), (0, 5))  # west column, north row
        self.assertEqual(ats.section_grid_xy(36), (5, 5))

    def test_east_column_is_closer_to_the_meridian(self):
        # Ranges run west from the meridian, so a section in the east column
        # must have a longitude east of (greater than) one in the west column.
        _, east_lon = ats.ats_to_latlng("SE1-20-5-W5")
        _, west_lon = ats.ats_to_latlng("SW6-20-5-W5")
        self.assertGreater(east_lon, west_lon)
        # They are five miles apart, not fifty.
        self.assertLess(abs(east_lon - west_lon), 0.2)

    def test_north_township_is_further_north(self):
        north, _ = ats.ats_to_latlng("SW1-100-5-W5")
        south, _ = ats.ats_to_latlng("SW1-1-5-W5")
        self.assertGreater(north, south)

    def test_township_1_starts_at_the_border(self):
        lat, _ = ats.ats_to_latlng("SW1-1-1-W4")
        self.assertAlmostEqual(lat, 49.0, delta=0.05)

    def test_meridians_anchor_longitude(self):
        for code, meridian in (("SE1-20-1-W4", -110.0), ("SE1-20-1-W5", -114.0), ("SE1-20-1-W6", -118.0)):
            _, lon = ats.ats_to_latlng(code)
            self.assertLess(abs(lon - meridian), 0.05, code)

    def test_malformed_codes_return_none(self):
        for bad in ("", None, "nonsense", "XX1-2-3-W4", "NE99-2-3-W4", "NE1-2-3-W9"):
            self.assertEqual(ats.ats_to_latlng(bad), (None, None), repr(bad))


class AtsAccuracyTests(unittest.TestCase):
    """Guard the fix that moved every pin onto the right lake.

    The stocking report gives an ATS land description; the profiles CSV gives a
    hand-verified coordinate for the same lake. Two independent sources, so if
    the conversion is right they agree to within about a quarter-section.
    Before the fix the median gap was 6.08 km.
    """

    @classmethod
    def setUpClass(cls):
        cls.gaps = []
        with open(PROFILES_CSV, newline="", encoding="cp1252") as f:
            for row in csv.DictReader(f):
                lat = merge_profiles.parse_float(row.get("lat"))
                lon = merge_profiles.parse_float(row.get("lon"))
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


class AreaParsingTests(unittest.TestCase):
    def test_parses_the_shapes_the_csv_actually_uses(self):
        cases = {
            "(ha): 13.2 hectares": 13.2,
            "(ha): 2 hectares": 2.0,
            "1,234 ha": 1234.0,
            "846.4": 846.4,
        }
        for text, expected in cases.items():
            self.assertEqual(merge_profiles.parse_area_ha(text), expected, text)

    def test_missing_or_unparseable_area_is_none(self):
        for text in ("", None, "n/a", "unknown"):
            self.assertIsNone(merge_profiles.parse_area_ha(text), repr(text))

    def test_real_csv_yields_areas_for_most_lakes(self):
        # Regression: the old regex required a leading digit, so "(ha): 13.2
        # hectares" parsed as None and no popup ever showed an area.
        with open(PROFILES_CSV, newline="", encoding="cp1252") as f:
            areas = [merge_profiles.parse_area_ha(r.get("surface_area")) for r in csv.DictReader(f)]
        self.assertGreater(sum(a is not None for a in areas) / len(areas), 0.9)


class CoordinateSourceTests(unittest.TestCase):
    def profile(self, **kw):
        base = {"display_name": None, "lat": None, "lon": None,
                "override_lat": None, "override_lon": None,
                "zone": None, "surface_area_ha": None, "amenities": None}
        base.update(kw)
        return base

    def test_override_wins(self):
        prof = self.profile(lat=52.0, lon=-114.0, override_lat=53.0, override_lon=-115.0)
        self.assertEqual(merge_profiles.resolve_coordinates("SW4-36-8-W5", prof),
                         (53.0, -115.0, "override"))

    def test_profile_coordinates_beat_the_ats_estimate(self):
        prof = self.profile(lat=52.0, lon=-114.0)
        self.assertEqual(merge_profiles.resolve_coordinates("SW4-36-8-W5", prof),
                         (52.0, -114.0, "profile"))

    def test_falls_back_to_ats_when_no_profile(self):
        lat, lon, source = merge_profiles.resolve_coordinates("SW4-36-8-W5", None)
        self.assertEqual(source, "ats")
        self.assertEqual((lat, lon), ats.ats_to_latlng("SW4-36-8-W5"))

    def test_half_a_profile_coordinate_is_not_used(self):
        prof = self.profile(lat=52.0, lon=None)
        self.assertEqual(merge_profiles.resolve_coordinates("SW4-36-8-W5", prof)[2], "ats")


class ConsistencyChecksTests(unittest.TestCase):
    def test_normalize_name_strips_parenthetical_and_punctuation(self):
        self.assertEqual(
            check_consistency.normalize_name("Spring (Cottage) Lake!"),
            "spring lake",
        )

    def test_ats_variants_detected(self):
        by_year = {
            2025: [
                {"ats": "NE16-21-10-W5", "name": "A", "lat": 50.0, "lon": -115.0},
                {"ats": "SW16-21-10-W5", "name": "B", "lat": 50.1, "lon": -115.1},
            ]
        }
        findings = check_consistency.run_checks(by_year, profile_ats=set())
        self.assertEqual(len(findings["ats_variants"]), 1)
        rest_code, pairs = findings["ats_variants"][0]
        self.assertEqual(rest_code, "16-21-10-W5")
        self.assertEqual(len(pairs), 2)


class MergeProfilesTests(unittest.TestCase):
    def test_profile_merge_overrides_name_coords_and_sets_profile_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profiles = tmp_path / "profiles.csv"
            lakes = tmp_path / "lakes_2025.json"

            profiles.write_text(
                "ats,lat,lon,Trout Map Name,name,zone,surface_area,site_amenities\n"
                "NE10-2-28-W4,49.2,-113.6,Preferred Name,Original Name,ES1,(ha): 123.4 hectares,Boat Launch\n",
                encoding="utf-8",
            )

            lakes.write_text(
                json.dumps(
                    [
                        {
                            "ats": "NE10-2-28-W4",
                            "name": "Original Name",
                            "lat": 49.0,
                            "lon": -113.0,
                            "stockings": [],
                            "total_fish": 0,
                            "species_set": [],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            original_profiles_csv = merge_profiles.PROFILES_CSV
            try:
                merge_profiles.PROFILES_CSV = profiles
                merge_profiles.merge(str(lakes))
            finally:
                merge_profiles.PROFILES_CSV = original_profiles_csv

            merged = json.loads(lakes.read_text(encoding="utf-8"))[0]
            self.assertEqual(merged["name"], "Preferred Name")
            self.assertEqual(merged["lat"], 49.2)
            self.assertEqual(merged["lon"], -113.6)
            self.assertEqual(merged["zone"], "ES1")
            self.assertEqual(merged["surface_area_ha"], 123.4)
            self.assertEqual(merged["amenities"], "Boat Launch")
            self.assertEqual(merged["coord_source"], "profile")
            self.assertEqual(merged["lake_id"], "NE10-2-28-W4")


class PublishedDataTests(unittest.TestCase):
    """The committed data is what GitHub Pages serves, so check it directly."""

    @classmethod
    def setUpClass(cls):
        data_dir = Path(__file__).parent.parent / "data"
        manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
        cls.years = manifest["years"]
        cls.by_year = {y: json.loads((data_dir / f"lakes_{y}.json").read_text(encoding="utf-8"))
                       for y in cls.years}

    def test_every_manifest_year_has_a_data_file(self):
        self.assertTrue(self.years)

    def test_every_lake_has_coordinates_and_a_source(self):
        for year, lakes in self.by_year.items():
            for lk in lakes:
                self.assertIsNotNone(lk.get("lat"), f"{year} {lk['ats']}")
                self.assertIsNotNone(lk.get("lon"), f"{year} {lk['ats']}")
                self.assertIn(lk.get("coord_source"), ("override", "profile", "ats"),
                              f"{year} {lk['ats']}")
                self.assertIsNotNone(lk.get("lake_id"), f"{year} {lk['ats']}")

    def test_coordinates_are_inside_alberta(self):
        for year, lakes in self.by_year.items():
            for lk in lakes:
                self.assertTrue(48.9 < lk["lat"] < 60.1, f"{year} {lk['ats']} lat {lk['lat']}")
                self.assertTrue(-120.1 < lk["lon"] < -109.9, f"{year} {lk['ats']} lon {lk['lon']}")

    def test_most_lakes_use_a_verified_coordinate(self):
        for year, lakes in self.by_year.items():
            verified = sum(lk["coord_source"] != "ats" for lk in lakes)
            self.assertGreater(verified / len(lakes), 0.9, year)

    def test_stocking_rows_are_well_formed(self):
        for year, lakes in self.by_year.items():
            for lk in lakes:
                for s in lk["stockings"]:
                    self.assertIn(s["species"], {"RNTR", "BKTR", "BNTR", "TGTR", "CTTR"})
                    self.assertIsInstance(s["number"], int)
                    self.assertGreater(s["number"], 0)
                    day, month, _ = s["date"].split("-")
                    self.assertTrue(day.isdigit(), s["date"])
                    self.assertIn(month, {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"}, s["date"])

    def test_total_fish_matches_the_stocking_rows(self):
        for year, lakes in self.by_year.items():
            for lk in lakes:
                self.assertEqual(lk["total_fish"], sum(s["number"] for s in lk["stockings"]),
                                 f"{year} {lk['ats']}")


if __name__ == "__main__":
    unittest.main()
