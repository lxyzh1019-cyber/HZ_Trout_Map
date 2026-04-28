import json
import tempfile
import unittest
from pathlib import Path

import check_consistency
import merge_profiles


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
                "ats,html_lat,html_lon,Trout Map Name,name,zone,surface_area,site_amenities\n"
                "NE10-2-28-W4,49.2,-113.6,Preferred Name,Original Name,ES1,123.4 ha,Boat Launch\n",
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

            merged = json.loads(lakes.read_text(encoding="utf-8"))
            self.assertEqual(merged[0]["name"], "Preferred Name")
            self.assertEqual(merged[0]["lat"], 49.2)
            self.assertEqual(merged[0]["lon"], -113.6)
            self.assertEqual(merged[0]["zone"], "ES1")
            self.assertEqual(merged[0]["surface_area_ha"], 123.4)
            self.assertEqual(merged[0]["amenities"], "Boat Launch")


if __name__ == "__main__":
    unittest.main()
