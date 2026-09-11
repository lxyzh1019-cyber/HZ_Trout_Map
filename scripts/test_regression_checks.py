import csv
import json
import re
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


class CoordinateHygieneTests(unittest.TestCase):
    """Two lakes must never sit on the same point, and no lake may be a ghost."""

    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((DATA_DIR / "lake_registry.json").read_text(encoding="utf-8"))

    def test_no_two_lakes_share_a_verified_coordinate(self):
        # The profiles CSV repeats one position across five pairs, including
        # North and South Two Lake, whose land descriptions put them 3.4 km
        # apart. A position given to two lakes is not verified.
        seen = {}
        for lake in self.registry:
            if lake["coord_source"] != "profile" or lake["lat"] is None:
                continue
            key = (round(lake["lat"], 6), round(lake["lon"], 6))
            self.assertNotIn(key, seen, f"{lake['name']} shares a point with {seen.get(key)}")
            seen[key] = lake["name"]

    def test_two_lakes_provincial_park_holds_two_distinct_lakes(self):
        by_name = {l["name"]: l for l in self.registry}
        north, south = by_name.get("North Two Lake"), by_name.get("South Two Lake")
        self.assertIsNotNone(north)
        self.assertIsNotNone(south)
        apart = ats.haversine_km(north["lat"], north["lon"], south["lat"], south["lon"])
        self.assertGreater(apart, 1.0, "the two lakes are stacked on one point")
        self.assertLess(apart, 12.0, "they should both be in the same park")

    def test_no_lake_in_the_registry_is_empty(self):
        """Alberta has issued two ids for one water more than once; the twin
        holds nothing and only clutters the review candidates."""
        used = set()
        for year in json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))["years"]:
            for lake in json.loads((DATA_DIR / f"lakes_{year}.json").read_text(encoding="utf-8")):
                used.add(lake["lake_id"])
        empty = [l["lake_id"] for l in self.registry if l["lake_id"] not in used]
        self.assertEqual(empty, [], f"registry entries with no rows: {empty}")

    def test_no_name_needs_a_disambiguating_suffix_any_more(self):
        suffixed = [l["name"] for l in self.registry if "[" in l["name"]]
        self.assertEqual(suffixed, [])

    def test_a_land_description_ruled_wrong_is_never_learned(self):
        """Alberta filed the 2014 North Two Lake shipment under a second id,
        with a land description 166 km away near Valleyview. The fish belong to
        North Two Lake; the location does not. Learning it would tell the
        matcher that a real place belongs to a lake that is not there, so a
        future report naming that spot would silently link here."""
        wrong = registry.load_aliases()["wrong_ats"]
        self.assertIn("NW1-73-25-W5", wrong, "the ruling itself has gone missing")
        for lake in self.registry:
            for code in lake["ats_codes"]:
                self.assertNotIn(code.upper(), wrong,
                                 f"{lake['name']} learned a land description ruled wrong")

    def test_the_two_unqualified_two_lakes_rows_belong_to_north(self):
        """Both carry exactly 7,200 rainbows, which is North Two Lake's
        standing shipment in ten other years. South is stocked with cutthroat
        in every year but 2024, and never at that size."""
        for year, when in ((2014, "2014-05-26"), (2015, "2015-05-25")):
            lakes = json.loads((DATA_DIR / f"lakes_{year}.json").read_text(encoding="utf-8"))
            owner = [l for l in lakes
                     if any(s["date"] == when and s["species"] == "RNTR" and s["number"] == 7200
                            for s in l["stockings"])]
            self.assertEqual([l["lake_id"] for l in owner], ["wb6535"],
                             f"the {year} unqualified Two Lakes row moved off North Two Lake")

    def test_north_two_lake_is_stocked_in_every_year_on_record(self):
        """The point of both rulings. While the 2014 shipment sat under a
        second Alberta id and the 2015 one under South, North's history showed
        two holes in a run that has otherwise never missed a year."""
        years = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))["years"]
        missing = [y for y in years
                   if not any(l["lake_id"] == "wb6535" and l["stockings"]
                              for l in json.loads((DATA_DIR / f"lakes_{y}.json").read_text(encoding="utf-8")))]
        self.assertEqual(missing, [], f"North Two Lake has no stocking in {missing}")


class LinkingCompletenessTests(unittest.TestCase):
    def test_every_report_row_found_a_lake(self):
        """Reviewed answers are applied, so nothing should be left unlinked."""
        review = DATA_DIR / "link_review.csv"
        if not review.exists():
            return
        with open(review, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows, [], f"{len(rows)} linking question(s) still open")

    def test_the_published_years_carry_every_trout_row_we_can_read(self):
        read = sum(1 for y in sources.YEAR_SOURCES
                   for r in sources.read_year(y) if r["species"] in sources.TROUT_SPECIES)
        published = 0
        for year in json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))["years"]:
            for lake in json.loads((DATA_DIR / f"lakes_{year}.json").read_text(encoding="utf-8")):
                published += len(lake["stockings"])
        self.assertEqual(published, read)


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


class OfflineAssetTests(unittest.TestCase):
    """Every script the page loads must also be precached.

    This is the one bug class that cannot be caught by using the app: a file
    missing from SHELL_FILES works perfectly at a desk with a network and throws
    a ReferenceError at a lake with no signal, months later. Cheap to assert,
    impossible to notice otherwise.
    """

    INDEX = ROOT / "index.html"
    SW = ROOT / "sw.js"

    def shell_files(self):
        text = self.SW.read_text(encoding="utf-8")
        start = text.index("const SHELL_FILES = [")
        end = text.index("]", start)
        return set(re.findall(r'"([^"]+)"', text[start:end]))

    def test_every_js_file_is_precached(self):
        shell = self.shell_files()
        for path in sorted((ROOT / "js").glob("*.js")):
            rel = f"js/{path.name}"
            self.assertIn(rel, shell, f"{rel} exists but is not in SHELL_FILES in sw.js")

    def test_every_script_tag_is_precached(self):
        shell = self.shell_files()
        srcs = re.findall(r'<script src="([^"]+)"', self.INDEX.read_text(encoding="utf-8"))
        for src in srcs:
            self.assertIn(src, shell, f"index.html loads {src} but sw.js does not precache it")

    def test_every_script_tag_points_at_a_real_file(self):
        srcs = re.findall(r'<script src="([^"]+)"', self.INDEX.read_text(encoding="utf-8"))
        for src in srcs:
            self.assertTrue((ROOT / src).is_file(), f"index.html loads {src}, which does not exist")

    def test_missing_library_check_names_every_script(self):
        """The app promises a named, actionable error for a missing library."""
        text = self.INDEX.read_text(encoding="utf-8")
        # Find the array that actually lists the libraries, not merely the first
        # variable that happens to share the name — an unrelated `const missing
        # = []` elsewhere in the file silently emptied this check once.
        block = re.search(r"const missing = \[(.*?)\]\.filter\(Boolean\)", text, re.S)
        self.assertIsNotNone(block, "could not find the missing-library check")
        named = set(re.findall(r'"((?:vendor|js)/[^"]+)"', block.group(1)))
        self.assertTrue(named, "the missing-library check named nothing at all")
        for src in re.findall(r'<script src="([^"]+)"', text):
            self.assertIn(src, named,
                          f"{src} is loaded but not named in the missing-library check")


class RegulationTests(unittest.TestCase):
    """The catch limits are the only thing here with a legal consequence.

    Every value asserted below was read off the published guide by eye first.
    The point is not that the parser is self-consistent — it is that it agrees
    with the document a warden would hold.
    """

    _cache = None

    @classmethod
    def regs(cls):
        if cls._cache is None:
            import regulations
            pdf = ROOT / "data" / "raw" / "alberta-sportfishing-regulations-2026-tables.pdf"
            if not pdf.exists():
                raise unittest.SkipTest(f"{pdf.name} is not present")
            cls._cache = regulations.load(pdf)
        return cls._cache

    # -- the three rules that are easy to get backwards --------------------

    def test_unlisted_waterbody_takes_the_zone_default(self):
        """"If a ES1 lake ... is not listed, follow the default regulations."

        Not "unknown". A lake absent from every table still has a limit.
        """
        import regulations
        found = regulations.resolve("No Such Lake At All", "ES1", self.regs())
        self.assertEqual(found["basis"], "watershed-default")
        self.assertEqual(found["limits"]["Trout"], "5")
        self.assertEqual(found["season"]["text"], "OPEN all year")

        northern = regulations.resolve("No Such Lake At All", "NB1", self.regs())
        self.assertEqual(northern["limits"]["Trout"], "3")
        self.assertEqual(northern["season"]["text"], "OPEN May 15 to Mar. 31")

    def test_blank_season_on_a_listed_waterbody_means_closed(self):
        """"If a listed waterbody does not have a season listed, it is CLOSED."

        Reading this as "unknown" would put someone on water that is shut.
        """
        import regulations
        self.assertEqual(regulations.parse_season(""),
                         {"text": "", "closed": True, "implied": True})
        self.assertTrue(regulations.parse_season("CLOSED ALL YEAR")["closed"])
        self.assertFalse(regulations.parse_season("CLOSED ALL YEAR")["implied"])
        self.assertFalse(regulations.parse_season("OPEN ALL YEAR")["closed"])

    def test_blank_species_cell_means_absent_not_unlimited(self):
        """An empty cell indicates the species is not likely present."""
        import regulations
        self.assertIsNone(regulations.parse_limit(""))
        self.assertIsNone(regulations.parse_limit(None))

    # -- the legend, parsed and preserved ----------------------------------

    def test_limit_is_parsed_without_losing_the_original_wording(self):
        """"'3 over 63 cm' indicates ... '3 fish each over 63 cm'."

        The structured form is for filtering. The words are what gets shown,
        because a paraphrase of a legal limit is a liability.
        """
        import regulations
        limit = regulations.parse_limit("3 over 63 cm")
        self.assertEqual(limit["count"], 3)
        self.assertEqual(limit["size_op"], "over")
        self.assertEqual(limit["size_cm"], 63)
        self.assertEqual(limit["text"], "3 over 63 cm")
        self.assertEqual(regulations.parse_limit("10 fish")["count"], 10)
        self.assertTrue(regulations.parse_limit("0 trout")["zero"])

    # -- a row read off the page by hand -----------------------------------

    def test_barnaby_lake_matches_the_printed_page(self):
        row = self.regs()["zones"]["ES1"]["lakes"]["Barnaby Lake"]
        self.assertEqual(row["season"]["text"], "OPEN JULY 16 TO OCT. 31")
        self.assertEqual(row["trout_total"]["text"], "1 trout over 40 cm")
        self.assertEqual(row["trout_total"]["count"], 1)
        self.assertEqual(row["trout_total"]["size_cm"], 40)
        self.assertEqual(row["bait"], "Bait ban")
        # Its tributaries carry their own, stricter season.
        self.assertTrue(any(sub["season"]["text"] == "CLOSED ALL YEAR"
                            for sub in row.get("also", [])))

    def test_a_cross_reference_is_not_reported_as_a_closure(self):
        """PP1's Bassano Reservoir has no season and points at the Bow River.

        Applied blindly, the blank-season rule calls that CLOSED ALL YEAR,
        which is false. Errs safe rather than dangerous, but still wrong.
        """
        import regulations
        found = regulations.resolve("Bassano Reservoir", "PP1", self.regs())
        self.assertEqual(found["basis"], "cross-reference")
        self.assertIn("Bow River", found["see"])

    # -- precedence ---------------------------------------------------------

    def test_resolution_follows_the_guide_precedence(self):
        """Site-specific, then the put-and-take list, then the zone default."""
        import regulations
        regs = self.regs()
        site = regulations.resolve("Barnaby Lake", "ES1", regs)
        self.assertEqual(site["basis"], "site-specific")
        stocked = regulations.resolve("Beauvais Lake", "ES1", regs)
        self.assertEqual(stocked["basis"], "put-and-take")
        self.assertEqual(stocked["limits"]["Trout"], "5 trout of any size")
        default = regulations.resolve("Nowhere Lake", "ES3", regs)
        self.assertEqual(default["basis"], "watershed-default")

    # -- coverage and hygiene ----------------------------------------------

    def test_every_zone_in_the_published_data_has_a_default(self):
        """A zone whose defaults failed to parse would silently leave its
        unlisted lakes with no limit at all."""
        regs = self.regs()
        latest = max(int(p.stem.split("_")[1]) for p in DATA_DIR.glob("lakes_*.json"))
        lakes = json.loads((DATA_DIR / f"lakes_{latest}.json").read_text())
        lakes = lakes["lakes"] if isinstance(lakes, dict) and "lakes" in lakes else lakes
        for zone in {lk.get("zone") for lk in lakes if lk.get("zone")}:
            self.assertIn(zone, regs["defaults"], f"no default parsed for {zone}")
            self.assertTrue(regs["defaults"][zone]["lakes"]["limits"],
                            f"{zone} default parsed with no limits")

    def test_all_ten_watershed_units_have_tables(self):
        regs = self.regs()
        for zone in ("ES1", "ES2", "ES3", "ES4", "PP1", "PP2",
                     "NB1", "NB2", "NB3", "NB4"):
            self.assertGreater(len(regs["zones"].get(zone, {}).get("lakes", {})), 5,
                               f"{zone} has almost no site-specific rows")

    def test_the_bait_legend_marker_is_expanded(self):
        """Three quarters of rows print a lone "l" in the bait column, defined
        in the heading as "Bait except Bait fish allowed". Passed through, it
        would put a bare glyph in front of an angler."""
        import regulations
        self.assertEqual(regulations.parse_bait("l"), "Bait allowed, except bait fish")
        self.assertEqual(regulations.parse_bait("Bait ban"), "Bait ban")
        self.assertEqual(regulations.parse_bait(""), "")
        baits = {row["bait"] for zone in self.regs()["zones"].values()
                 for row in zone["lakes"].values()}
        self.assertNotIn("l", baits, "a raw legend marker reached the output")

    def test_an_unmatched_lake_gets_no_limits_rather_than_the_default(self):
        """The unsafe fallback is the watershed default, because it is often
        more permissive than the site-specific row it would stand in for: ES1
        defaults to five trout with bait allowed, while Barnaby Lake inside ES1
        is one trout over 40 cm under a bait ban. A near-miss on the name must
        publish nothing, not the default."""
        import regulations
        regs = self.regs()
        # A name close to a real one, but not close enough to trust.
        resolved, review = regulations.match_lakes(regs, [
            {"lake_id": "test1", "name": "Barnaby Lakes Reservoir", "zone": "ES1"},
        ])
        self.assertNotIn("test1", resolved, "a near-miss was resolved anyway")
        self.assertEqual(len(review), 1)

        # A name nothing in the zone resembles really is unlisted, and the
        # guide says an unlisted water takes the default.
        resolved, review = regulations.match_lakes(regs, [
            {"lake_id": "test2", "name": "Zzyzx Quagmire", "zone": "ES1"},
        ])
        self.assertEqual(resolved["test2"]["basis"], "watershed-default")
        self.assertEqual(review, [])

    def test_published_per_lake_regulations_are_consistent(self):
        path = DATA_DIR / "lake_regulations.json"
        if not path.exists():
            self.skipTest("data/lake_regulations.json not built")
        published = json.loads(path.read_text())
        self.assertEqual(published["guide_year"], self.regs()["guide_year"])
        for key, entry in published["lakes"].items():
            self.assertIn(entry["basis"],
                          {"site-specific", "put-and-take", "watershed-default",
                           "cross-reference"},
                          f"{key} has an unknown basis")
            if entry["basis"] != "cross-reference":
                self.assertIn("season", entry, f"{key} published without a season")

    def test_stocked_names_are_not_corrupted_by_the_column_layout(self):
        """The stocked list is set in columns, and reading it flat merges
        neighbours — "Tim Horton Children's Pond Fairfax Lake" was one entry,
        and a land description was glued onto another. Either would attach a
        real limit to the wrong water."""
        stocked = self.regs()["stocked"]
        for name in stocked:
            self.assertFalse(re.match(r"^(NE|NW|SE|SW|\d)", name),
                             f"{name!r} starts with a land description fragment")
            self.assertLess(len(name), 46, f"{name!r} looks like two merged entries")
        for expected in ("Beauvais Lake", "Chain Lakes Reservoir", "Fairfax Lake",
                         "Shunda (Fish) Lake", "Mcleod Lake (Carson Lake)",
                         "Tim Horton Children’s Pond"):
            self.assertIn(expected, stocked, f"{expected!r} missing from the stocked list")


class DepthTests(unittest.TestCase):
    """Depth decides two pieces of advice, and both must stay silent without it.

    Sending someone to fish eight metres down in three metres of water is a real
    harm, so "probably deep enough" is never good enough.
    """

    def test_unknown_depth_produces_no_advice_at_all(self):
        import depth
        self.assertIsNone(depth.stratification(None, 120))
        self.assertIsNone(depth.winterkill(None, False, False))

    def test_a_shallow_lake_is_never_told_to_fish_deep(self):
        import depth
        for shallow in (1.5, 2.0, 3.0, 4.9):
            found = depth.stratification(shallow, 120)
            self.assertFalse(found["stratifies"], f"{shallow} m reported as stratifying")
            self.assertNotIn("band_m", found)

    def test_the_layer_never_sits_below_the_bottom(self):
        """A big lake's thermocline band is deeper than a small one's, so a
        large but shallow lake has nowhere to put it."""
        import depth
        found = depth.stratification(7.6, 900)      # big surface, not deep
        self.assertFalse(found["stratifies"])
        deep = depth.stratification(25.0, 900)
        self.assertTrue(deep["stratifies"])
        self.assertLessEqual(deep["band_m"][1], 25.0 - 1)

    def test_the_band_follows_fetch_not_a_fraction_of_depth(self):
        """Thermocline depth is set by how far the wind blows across the water.
        Taking a fraction of max depth gave a 7.6 m and a 12 m lake the same
        band, with the deeper one's layer placed too shallow."""
        import depth
        small = depth.stratification(20.0, 20)
        large = depth.stratification(20.0, 900)
        self.assertGreater(large["band_m"][0], small["band_m"][0])
        # Same lake size, different depths, both deep enough: same band.
        self.assertEqual(depth.stratification(12.0, 120)["band_m"],
                         depth.stratification(25.0, 120)["band_m"])

    def test_winterkill_says_what_it_did_not_count(self):
        import depth
        risk = depth.winterkill(2.0, aerated=False, aeration_known=False)
        self.assertEqual(risk["level"], "high")
        self.assertFalse(risk["inputs"]["eutrophy"])
        self.assertFalse(risk["inputs"]["ice_duration"])
        self.assertFalse(risk["inputs"]["aeration"])

    def test_aeration_cuts_both_ways(self):
        """A lake is aerated because it is expected to winterkill, and is less
        likely to because it is aerated. Both belong in the reasons."""
        import depth
        plain = depth.winterkill(2.0, aerated=False, aeration_known=True)
        helped = depth.winterkill(2.0, aerated=True, aeration_known=True)
        self.assertEqual(plain["level"], "high")
        self.assertEqual(helped["level"], "moderate")
        self.assertTrue(any("expected to winterkill" in r for r in helped["reasons"]))

    def test_depth_is_joined_on_albertas_own_waterbody_id(self):
        """The join is exact rather than by name: MyWildAlberta addresses a lake
        as ?id=6537 and the registry stores that same id."""
        registry_file = DATA_DIR / "lake_registry.json"
        data = json.loads(registry_file.read_text())
        lakes = data["lakes"] if isinstance(data, dict) and "lakes" in data else data
        with_id = [l for l in lakes if l.get("waterbody_id")]
        self.assertGreater(len(with_id), 300, "the id join would cover too few lakes")
        for lake in with_id[:50]:
            self.assertTrue(str(lake["waterbody_id"]).isdigit())
            self.assertEqual(lake["lake_id"], "wb" + str(lake["waterbody_id"]))

    def test_the_parser_reads_the_shapes_the_page_uses(self):
        import fetch_depths
        found = fetch_depths.parse(
            "<h1>Somewhere Lake</h1><tr><th>Maximum Depth</th><td>7.6 m</td></tr>"
            "<tr><th>Surface Area</th><td>25.4 ha</td></tr>")
        self.assertEqual(found["max_depth_m"], 7.6)
        self.assertEqual(found["surface_area_ha"], 25.4)
        # "no depth available" is an answer, not a failure to read the page
        stated = fetch_depths.parse("<p>Depth information is not available.</p>")
        self.assertIsNone(stated["max_depth_m"])
        self.assertTrue(stated["states_unavailable"])
        # and a page with neither is neither
        blank = fetch_depths.parse("<h1>Quiet Lake</h1><p>Stocked with trout.</p>")
        self.assertIsNone(blank["max_depth_m"])
        self.assertFalse(blank["states_unavailable"])
