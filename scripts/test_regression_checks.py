import collections
import csv
import json
import re
import statistics
import unittest
import unittest.mock
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

    def test_every_data_file_the_page_fetches_is_precached(self):
        """A forgotten cache entry is noticed only by someone offline at a lake.

        sw.js already says that about scripts. The same hazard applies to data
        files and nothing checked it, so a new one could ship uncached and the
        app would work perfectly until it was needed.

        One file is exempt and named here rather than skipped silently: the
        photo index points at images on Alberta's server, this worker does not
        handle other origins, and an index of pictures that cannot load is not
        worth the bytes. The photo COUNT lives in the profile file, which is
        cached, so a lake still says how many there are.
        """
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        worker = (ROOT / "sw.js").read_text(encoding="utf-8")
        lazy_on_purpose = {"data/lake_photos.json"}

        fetched = set(re.findall(r'fetch\("((?:data|live)/[^"]+)"\)', page))
        self.assertTrue(fetched, "no data fetches found; has the loader moved?")
        for url in sorted(fetched):
            if url in lazy_on_purpose:
                self.assertNotIn('"' + url + '"', worker,
                                 url + " is meant to stay out of the cache")
                continue
            self.assertIn('"' + url + '"', worker,
                          "index.html fetches " + url + " but sw.js never caches it")

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

    def test_the_collector_discovers_the_page_schema(self):
        """The collector was written without being able to open the site, so it
        must not depend on having guessed the labels. It harvests every
        label/value pair the markup offers, in whatever form, and maps those
        onto the columns the build wants."""
        import fetch_lake_pages as collector

        definition_list = ("<h1>Beauvais Lake - Fish Stocking</h1>"
                           "<dl><dt>Watershed Unit</dt><dd>ES1</dd>"
                           "<dt>Surface Area</dt><dd>219.2 ha</dd>"
                           "<dt>Maximum Depth</dt><dd>12.0 m</dd></dl>")
        found = collector.interpret(collector.harvest(definition_list), definition_list)
        self.assertEqual(found["page_name"], "Beauvais Lake")
        self.assertEqual(found["zone"], "ES1")
        self.assertEqual(found["max_depth_m"], 12.0)
        self.assertEqual(found["surface_area_ha"], 219.2)

        table = ("<title>Chain Lakes Reservoir | My Wild Alberta</title>"
                 "<table><tr><th>Zone</th><td>ES1</td></tr>"
                 "<tr><th>Max. Depth</th><td>9.1 m</td></tr></table>")
        found = collector.interpret(collector.harvest(table), table)
        self.assertEqual(found["max_depth_m"], 9.1,
                         "a differently worded label was missed")
        self.assertEqual(found["page_name"], "Chain Lakes Reservoir")

        # A zone mentioned only in prose still counts: it is the field that
        # decides whether a lake gets catch limits at all.
        prose = "<h1>Jarvis Creek</h1><p>Lies within watershed unit ES3.</p>"
        self.assertEqual(
            collector.interpret(collector.harvest(prose), prose)["zone"], "ES3")

    def test_no_depth_available_is_an_answer_not_a_failure(self):
        import fetch_lake_pages as collector
        stated = "<h1>Some Pond</h1><p>Depth information is not available.</p>"
        found = collector.interpret(collector.harvest(stated), stated)
        self.assertIsNone(found.get("max_depth_m"))
        self.assertTrue(found["depth_stated_unavailable"])

        silent = "<h1>Quiet Lake</h1><p>Stocked with trout.</p>"
        found = collector.interpret(collector.harvest(silent), silent)
        self.assertIsNone(found.get("max_depth_m"))
        self.assertFalse(found["depth_stated_unavailable"],
                         "a page that simply says nothing must not be read as "
                         "Alberta stating no depth exists")

    def test_reconciliation_separates_filling_from_overwriting(self):
        """Alberta is the authority on its own lakes, but this repo's values came
        from its own sources for reasons. A blank may be filled; a disagreement
        goes to a person."""
        import reconcile
        lakes = [
            {"lake_id": "wb1", "waterbody_id": "1", "name": "Blank Zone", "zone": None},
            {"lake_id": "wb2", "waterbody_id": "2", "name": "Agrees", "zone": "ES1"},
            {"lake_id": "wb3", "waterbody_id": "3", "name": "Differs", "zone": "PP2"},
            {"lake_id": "wb4", "waterbody_id": "4", "name": "Close Area",
             "surface_area_ha": 100.0},
        ]
        site = {
            "1": {"waterbody_id": "1", "zone": "ES2"},
            "2": {"waterbody_id": "2", "zone": "ES1"},
            "3": {"waterbody_id": "3", "zone": "NB1"},
            "4": {"waterbody_id": "4", "surface_area_ha": "104"},
        }
        fills, confirms, disagreements = reconcile.compare(lakes, site)
        self.assertEqual([r["lake"] for r in fills], ["Blank Zone"])
        self.assertEqual({r["lake"] for r in confirms}, {"Agrees", "Close Area"},
                         "a 4% area difference should count as agreement")
        self.assertEqual([r["lake"] for r in disagreements], ["Differs"])

    def test_coordinates_are_read_however_the_page_spells_them(self):
        """Alberta writes a west longitude either as a minus sign or as a
        trailing W, and puts both coordinates on one line. Each of those broke a
        different part of the collector, and each one silently: a missed
        coordinate is indistinguishable from a page that does not publish one."""
        import fetch_lake_pages as collector
        spellings = {
            "minus sign": "<p>Latitude: 53.487212  Longitude: -114.173756</p>",
            "trailing W": "<p>Latitude: 53.487212  Longitude: 114.173756 W</p>",
            "numeric entity": "<p>53.487212&#176; N, 114.173756&#176; W</p>",
            "named entity": "<p>53.487212&deg;N, 114.173756&deg;W</p>",
            "table": ("<table><tr><th>Latitude</th><td>53.487212</td></tr>"
                      "<tr><th>Longitude</th><td>-114.173756</td></tr></table>"),
        }
        for how, body in spellings.items():
            html = "<h1>Hasse Lake</h1>" + body
            found = collector.interpret(collector.harvest(html), html)
            self.assertEqual(found.get("latitude"), 53.487212, how)
            self.assertEqual(found.get("longitude"), -114.173756,
                             f"{how}: a west longitude must be stored negative")

    def test_two_labels_on_one_line_are_both_read(self):
        """The plain-text pass used to take everything after the first colon,
        so "Latitude: 53.4 Longitude: 114.1" stored the whole remainder as the
        latitude and lost the longitude entirely."""
        import fetch_lake_pages as collector
        html = "<p>Maximum Depth: 14 m Surface Area: 90 ha</p>"
        found = collector.interpret(collector.harvest(html), html)
        self.assertEqual(found.get("max_depth_m"), 14.0)
        self.assertEqual(found.get("surface_area_ha"), 90.0,
                         "the second pair on the line was swallowed by the first")

    def test_a_quarter_section_matches_whatever_the_spacing(self):
        """Alberta prints SW 13-52-2-W5 and this repo stores SW13-52-2-W5. They
        are the same quarter section, and comparing them as written would report
        every lake in the province as a disagreement."""
        import reconcile
        lakes = [
            {"lake_id": "wb1", "waterbody_id": "1", "name": "Spaced",
             "ats_codes": ["SW13-52-2-W5"]},
            {"lake_id": "wb2", "waterbody_id": "2", "name": "Several",
             "ats_codes": ["NE9-47-19-W5", "SE9-47-19-W5"]},
            {"lake_id": "wb3", "waterbody_id": "3", "name": "Elsewhere",
             "ats_codes": ["SW13-52-2-W5"]},
            {"lake_id": "wb4", "waterbody_id": "4", "name": "None Held",
             "ats_codes": []},
        ]
        site = {
            "1": {"waterbody_id": "1", "legal_land_description": "SW 13-52-2-W5"},
            "2": {"waterbody_id": "2", "legal_land_description": "SE 9-47-19-W5"},
            "3": {"waterbody_id": "3", "legal_land_description": "NE 1-1-1-W4"},
            "4": {"waterbody_id": "4", "legal_land_description": "SW 13-52-2-W5"},
        }
        fills, confirms, disagreements = reconcile.compare(lakes, site)
        self.assertEqual({r["lake"] for r in confirms}, {"Spaced", "Several"},
                         "a lake touching several quarter sections agrees if the "
                         "published one is any of them")
        self.assertEqual([r["lake"] for r in disagreements], ["Elsewhere"])
        self.assertEqual([r["lake"] for r in fills], ["None Held"])

    def test_a_published_position_checks_a_derived_one(self):
        """Most of this repo's coordinates were derived from land descriptions,
        and a derivation cannot catch its own arithmetic error. An independently
        published pair can — but only if "the same lake described from a
        different point" is not reported as a disagreement."""
        import reconcile
        held_lat, held_lon = 53.269494, -117.792760
        lakes = [
            {"lake_id": "wb1", "waterbody_id": "1", "name": "Exact",
             "lat": held_lat, "lon": held_lon},
            {"lake_id": "wb2", "waterbody_id": "2", "name": "Boat Launch",
             "lat": held_lat, "lon": held_lon},
            {"lake_id": "wb3", "waterbody_id": "3", "name": "Wrong Lake",
             "lat": held_lat, "lon": held_lon},
            {"lake_id": "wb4", "waterbody_id": "4", "name": "Unplaced",
             "lat": None, "lon": None},
        ]
        site = {
            "1": {"waterbody_id": "1", "latitude": str(held_lat),
                  "longitude": str(held_lon)},
            # ~520 m away: the same lake, measured from somewhere else on it.
            "2": {"waterbody_id": "2", "latitude": str(held_lat + 0.004),
                  "longitude": str(held_lon + 0.004)},
            # Most of a province away.
            "3": {"waterbody_id": "3", "latitude": "52.0", "longitude": "-113.0"},
            "4": {"waterbody_id": "4", "latitude": str(held_lat),
                  "longitude": str(held_lon)},
        }
        fills, confirms, disagreements = reconcile.compare(lakes, site)
        self.assertEqual({r["lake"] for r in confirms}, {"Exact", "Boat Launch"})
        self.assertEqual([r["lake"] for r in disagreements], ["Wrong Lake"])
        self.assertEqual([r["lake"] for r in fills], ["Unplaced"])
        # The distance is recorded either way, so the threshold never has to be
        # taken on trust when someone reads the review file.
        apart = {r["lake"]: r["note"] for r in confirms + disagreements}
        self.assertEqual(apart["Exact"], "0 m apart")
        self.assertTrue(apart["Boat Launch"].endswith("m apart"))
        self.assertGreater(int(apart["Wrong Lake"].split()[0]), 100000)

    def test_a_disagreeing_position_is_never_applied(self):
        """--apply fills blanks. A coordinate the repo already holds is a
        disagreement for a person to settle, and must survive --apply untouched
        however confident the published value looks."""
        import reconcile
        lakes = [{"lake_id": "wb1", "waterbody_id": "1", "name": "Wrong Lake",
                  "lat": 53.269494, "lon": -117.792760}]
        site = {"1": {"waterbody_id": "1", "latitude": "52.0", "longitude": "-113.0"}}
        fills, _, disagreements = reconcile.compare(lakes, site)
        self.assertEqual(fills, [], "an existing coordinate is not a blank")
        self.assertEqual(len(disagreements), 1)


class ImportedSourceTests(unittest.TestCase):
    """The stocking-map export, and the CSVs built from it.

    The build never re-derives these, so nothing in the ordinary pipeline would
    notice them drifting away from the workbook they came from. That is what
    these tests are for.
    """

    @classmethod
    def setUpClass(cls):
        import import_stocking_map
        cls.mod = import_stocking_map
        if not cls.mod.WORKBOOK.exists():
            raise unittest.SkipTest("the stocking-map workbook is not present")
        cls.built, cls.stats = cls.mod.build()
        cls.rows = list(csv.DictReader(cls.built[cls.mod.LAKES_CSV].splitlines()))

    def test_the_committed_csvs_match_the_workbook(self):
        """What is committed is what the workbook says, still.

        The importer is deliberately outside the build, so this stands in for
        the byte-exact check that covers everything else under data/.
        """
        for path, text in self.built.items():
            name = path.relative_to(ROOT)
            self.assertTrue(path.exists(), f"{name} has not been built")
            self.assertEqual(path.read_text(encoding="utf-8"), text,
                             f"{name} no longer matches the workbook; "
                             f"re-run import_stocking_map.py")

    def test_the_import_is_idempotent(self):
        again, _ = self.mod.build()
        for path, text in self.built.items():
            self.assertEqual(again[path], text, f"{path.name} changed between runs")

    def test_the_schema_is_exactly_what_the_collector_writes(self):
        """depth.py and reconcile.py read the collector's columns by name.

        If fetch_lake_pages.py ever changes its fields, this fails rather than
        letting the two quietly diverge and the readers find nothing.
        """
        import fetch_lake_pages
        expected = (["waterbody_id", "lake_id", "registry_name", "page_name"]
                    + list(fetch_lake_pages.INTERESTING) + ["depth_stated_unavailable"])
        header = self.built[self.mod.LAKES_CSV].splitlines()[0].split(",")
        self.assertEqual(header, expected)

    def test_unknown_never_becomes_zero(self):
        """A lake with no published depth is not a lake that is 0 m deep."""
        for column in ("max_depth_m", "mean_depth_m", "surface_area_ha"):
            for row in self.rows:
                value = row[column]
                self.assertNotEqual(value, "0", f"{row['waterbody_id']} {column}")
                if value:
                    self.assertGreater(float(value), 0,
                                       f"{row['waterbody_id']} {column} is {value}")

    def test_alberta_is_never_made_to_say_it_has_no_depth(self):
        """The collector sets this only when a page says so in words.

        The workbook's "Unknown" means its author found none, which is a
        weaker claim, and passing it through would put words in Alberta's mouth.
        """
        self.assertEqual([r for r in self.rows if r["depth_stated_unavailable"]], [])

    def test_a_position_that_contradicts_its_own_land_description_is_not_published(self):
        """Watridge Lake publishes a point 140 km from its own quarter section.

        The land description and the district agree with each other and with the
        repo; one digit of the longitude does not. The row is refused rather
        than passed on, and the refusal is written down.
        """
        watridge = [r for r in self.rows if r["waterbody_id"] == "6120"]
        self.assertEqual(len(watridge), 1)
        self.assertEqual(watridge[0]["latitude"], "")
        self.assertEqual(watridge[0]["longitude"], "")
        self.assertEqual(watridge[0]["legal_land_description"], "SW11-22-11-W5")
        issues = list(csv.DictReader(self.built[self.mod.ISSUES_CSV].splitlines()))
        self.assertIn("6120", [i["waterbody_id"] for i in issues
                               if i["check"] == "position_vs_ats"])

    def test_only_one_position_is_ever_refused(self):
        """The threshold sits in measured empty space, not on a round number.

        Every other lake is within 2.2 km of its own land description, which is
        what the geometry predicts. A tighter rule throws away good positions.
        """
        issues = list(csv.DictReader(self.built[self.mod.ISSUES_CSV].splitlines()))
        refused = [i for i in issues if i["check"] == "position_vs_ats"]
        self.assertEqual(len(refused), 1, [i["name"] for i in refused])

    def test_aeration_not_stated_is_not_recorded_as_no(self):
        """Alberta names the aerated lakes and says nothing about the others."""
        aerated = list(csv.DictReader(self.built[self.mod.AERATED_CSV].splitlines()))
        self.assertTrue(aerated)
        for row in aerated:
            self.assertIn(row["confidence"], {"stated", "published_list", "photo_caption"})
            self.assertTrue(row["evidence"], f"{row['name']} is on the list with no reason")
        stated = [r for r in aerated if r["confidence"] == "stated"]
        self.assertEqual(len(stated), 12)

    def test_a_photograph_is_never_enough_to_call_a_lake_aerated(self):
        """Castaway and Lara show a windmill in a picture and nothing in prose.

        A photograph shows that equipment existed when it was taken, not that
        the programme runs now. Marking a lake aerated makes it read as safer
        than it is, so that evidence is carried and not applied.
        """
        import depth
        aerated = list(csv.DictReader(self.built[self.mod.AERATED_CSV].splitlines()))
        caption_only = {r["waterbody_id"] for r in aerated
                        if r["confidence"] == "photo_caption"}
        self.assertEqual(caption_only, {"20258", "24053"})
        self.assertFalse(caption_only & depth.load_aerated()[0],
                         "photo evidence reached the applied list")

    def test_photo_evidence_never_lowers_a_winterkill_band(self):
        import depth
        applied, noted = depth.load_aerated()
        for wid in noted:
            self.assertNotIn(wid, applied)
        shallow = 2.0
        self.assertEqual(depth.winterkill(shallow, False, False)["level"], "high")
        self.assertEqual(depth.winterkill(shallow, True, True)["level"], "moderate")


class AerationIsKnownPerLakeTests(unittest.TestCase):
    """Absence from the aerated list is not a statement that a lake is not aerated.

    The flag used to be set once for the whole run, so the moment any aerated
    list existed every lake missing from it was told "not on the aerated list".
    """

    def test_a_lake_off_the_list_is_not_told_it_is_unaerated(self):
        import depth
        found = depth.winterkill(2.0, False, False)
        self.assertFalse(found["inputs"]["aeration"])
        self.assertNotIn("not on the aerated list", found["reasons"])

    def test_the_published_file_never_asserts_the_negative(self):
        path = DATA_DIR / "lake_depth.json"
        if not path.exists():
            self.skipTest("depth has not been built")
        lakes = json.loads(path.read_text(encoding="utf-8"))["lakes"]
        wrong = [k for k, v in lakes.items()
                 if not v.get("aerated") and v.get("winterkill")
                 and any("not on the aerated list" in r for r in v["winterkill"]["reasons"])]
        self.assertEqual(wrong, [], "lakes told they are not aerated")

    def test_an_aerated_lake_still_says_it_cuts_both_ways(self):
        path = DATA_DIR / "lake_depth.json"
        if not path.exists():
            self.skipTest("depth has not been built")
        lakes = json.loads(path.read_text(encoding="utf-8"))["lakes"]
        aerated = [v for v in lakes.values() if v.get("aerated") and v.get("winterkill")]
        self.assertTrue(aerated, "no aerated lake carries a winterkill band")
        for entry in aerated:
            self.assertTrue(entry["winterkill"]["inputs"]["aeration"])
            self.assertTrue(any("aerated by the province" in r
                                for r in entry["winterkill"]["reasons"]))


class SharedLandDescriptionTests(unittest.TestCase):
    """Two lakes on one quarter section must keep their own fish.

    Seven of the registry's land descriptions are shared, and every one is a
    pair the survey grid cannot separate: Upper and Lower Champion, Upper and
    Lower Smuts, Pit 35 and Pit 45, MD Peace Pond #1 and #2. For those the land
    description is the WEAKEST evidence, not the strongest, because it is the
    one field that is identical for both — and the name is all that is left.
    """

    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((DATA_DIR / "lake_registry.json").read_text(encoding="utf-8"))
        cls.by_id = {e["lake_id"]: e for e in cls.registry}

    def totals(self, lake_id):
        """Every year's fish for one lake, out of the published year files."""
        out = {}
        for year in json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))["years"]:
            for lake in json.loads((DATA_DIR / f"lakes_{year}.json").read_text(encoding="utf-8")):
                if lake["lake_id"] == lake_id:
                    out[year] = sum(s["number"] for s in lake["stockings"])
        return out

    def test_both_halves_of_a_pair_are_published(self):
        """Alberta stocks both ponds every year and names them apart every year.

        A land-description rule written from an answer about one of them used
        to send the other's rows to it too, so one lake carried double and the
        other vanished from the map entirely.
        """
        for first, second in (("wb6721", "wb22995"), ("wb6607", "wb6608")):
            for lake_id in (first, second):
                self.assertIn(lake_id, self.by_id)
                totals = self.totals(lake_id)
                self.assertTrue(totals, f"{self.by_id[lake_id]['name']} has no stocking at all")
                recent = {y: n for y, n in totals.items() if y >= 2021}
                self.assertTrue(recent, f"{self.by_id[lake_id]['name']} disappears after 2020")

    def test_neither_half_carries_the_others_fish(self):
        """The pairs are stocked in equal measure, so a doubled total is visible."""
        for first, second in (("wb6721", "wb22995"), ("wb6607", "wb6608")):
            a, b = self.totals(first), self.totals(second)
            for year in sorted(set(a) & set(b)):
                if year < 2021:
                    continue
                self.assertEqual(
                    a[year], b[year],
                    f"{year}: {self.by_id[first]['name']} has {a[year]} and "
                    f"{self.by_id[second]['name']} has {b[year]}; Alberta stocks them equally")

    def test_a_shared_profile_row_gives_its_area_to_one_lake_only(self):
        """Surface area measures one body of water, so it cannot be copied.

        Eight profile rows are claimed by two lakes each. The area on such a
        row belongs to the lake the row is named after — Alberta's stocking map
        confirms it for seven of the eight — so the neighbour gets nothing and
        says so, rather than reporting hectares that are not its own.
        """
        from registry import load_profiles, name_similarity
        profiles = load_profiles()
        claimants = collections.defaultdict(list)
        for lake in self.registry:
            for code in lake["ats_codes"]:
                if code in profiles:
                    claimants[code].append(lake)
                    break
        shared = {c: ls for c, ls in claimants.items() if len(ls) > 1}
        self.assertTrue(shared, "expected some profile rows claimed by two lakes")
        for code, lakes in shared.items():
            prof = profiles[code]
            if prof["surface_area_ha"] is None:
                continue
            carrying = [l for l in lakes if l["surface_area_ha"] == prof["surface_area_ha"]]
            self.assertLessEqual(
                len(carrying), 1,
                f"{code}: {[l['name'] for l in carrying]} all report "
                f"{prof['surface_area_ha']} ha from one profile row")
            if carrying:
                best = max(lakes, key=lambda l: name_similarity(prof["name"] or "", l["name"]))
                self.assertIs(carrying[0], best,
                              f"{code}: the area went to a lake the row does not name")

    def test_no_two_lakes_report_the_same_area_on_the_same_quarter_section(self):
        by_code = collections.defaultdict(list)
        for lake in self.registry:
            for code in lake["ats_codes"]:
                by_code[code].append(lake)
        for code, lakes in by_code.items():
            areas = [l["surface_area_ha"] for l in lakes if l["surface_area_ha"] is not None]
            self.assertEqual(len(areas), len(set(areas)),
                             f"{code}: {[(l['name'], l['surface_area_ha']) for l in lakes]}")

    def test_every_shared_land_description_rule_is_guarded(self):
        """These rules are kept, because for the 2011-2013 reports they are the
        answer: those years print a quarter section and no waterbody id, and
        without the recorded rule 58 rows go back to the review queue.

        What makes them safe is that link_all re-checks the row's own name
        before honouring one. This asserts the guard covers every shared code
        that actually appears as a rule, so a new one cannot arrive unprotected.
        """
        import registry as registry_module
        shared = registry_module.shared_land_descriptions(registry_module.load_registry())
        self.assertTrue(shared, "no shared land descriptions found to guard against")
        with (DATA_DIR / "lake_aliases.csv").open(newline="", encoding="utf-8") as handle:
            contested = [r for r in csv.DictReader(handle) if r["kind"] == "ats"
                         and registry_module.normalise_code(r["value"]) in shared]
        self.assertTrue(contested, "expected some rules on shared quarter sections")
        for row in contested:
            target = self.by_id.get(row["lake_id"])
            self.assertIsNotNone(target, f"{row['lake_id']} is not a lake")
            # The neighbour's name must be refused by the guard, or the rule
            # would take its rows too.
            neighbours = [e for e in self.registry
                          if e["lake_id"] != row["lake_id"]
                          and any(registry_module.normalise_code(c)
                                  == registry_module.normalise_code(row["value"])
                                  for c in e.get("ats_codes") or [])]
            for other in neighbours:
                self.assertTrue(
                    registry_module.discriminating_conflict(
                        other["name"],
                        registry_module.best_matching_name(target, other["name"])),
                    f"{row['value']} -> {target['name']} would also swallow "
                    f"{other['name']}")

    def test_a_land_description_rule_never_outranks_a_name_that_disagrees(self):
        """The second guard, in case such a rule is ever written by hand."""
        import registry as registry_module
        pond = {"lake_id": "wb22995", "name": "Md Peace Pond #2",
                "name_variants": ["Md Peace Pond #2", "Peace Pond #2"]}
        self.assertTrue(registry_module.discriminating_conflict(
            "Md Peace Pond #1", registry_module.best_matching_name(pond, "Md Peace Pond #1")))
        self.assertFalse(registry_module.discriminating_conflict(
            "Md Peace Pond #2", registry_module.best_matching_name(pond, "Md Peace Pond #2")))


class StockingMapAgreementTests(unittest.TestCase):
    """The published totals, against Alberta's other publication of the same years.

    The stocking map and the annual reports are two separate publications by the
    same agency, and this repo reads the reports. Comparing the two is how the
    doubled ponds were found, so it stays as a standing check rather than a
    one-off audit.

    Dates are deliberately not compared: 64% of the map's events sit one day
    earlier than the report's, which is a rendering difference and not a
    disagreement about what happened.
    """

    SPECIES = {"RAINBOW TROUT": "RNTR", "BROOK TROUT": "BKTR", "BROWN TROUT": "BNTR",
               "TIGER TROUT": "TGTR", "CUTTHROAT TROUT": "CTTR",
               "WESTSLOPE CUTTHROAT TROUT": "WSCT"}

    # Where the two publications genuinely disagree about individual events.
    # Neither is this repo getting it wrong, so they are named rather than
    # silently tolerated, and the count is asserted so a new one cannot hide.
    KNOWN_DISAGREEMENTS = {
        ("6818", 2023, "RNTR"),      # Goldspring Park Pond: the reports carry a
                                     # 19 May pair (2,528 fish) the map does not
        ("3524", 2021, "RNTR"),      # Michichi Reservoir: the map carries three
                                     # 55 cm September events the reports do not,
                                     # and the reports a 70-fish one the map lacks
    }

    @classmethod
    def setUpClass(cls):
        import import_stocking_map
        if not import_stocking_map.WORKBOOK.exists():
            raise unittest.SkipTest("the stocking-map workbook is not present")
        import openpyxl
        book = openpyxl.load_workbook(import_stocking_map.WORKBOOK, data_only=True)
        rows = list(book["Stocking details"].iter_rows(min_row=5, values_only=True))
        header = [str(h) for h in rows[0]]
        col = {name: header.index(name) for name in header}
        cls.export = collections.Counter()
        for row in rows[1:]:
            if not row or row[0] is None:
                continue
            species = cls.SPECIES.get(row[col["Species"]])
            if species:
                cls.export[(str(row[col["Lake ID"]]).strip(),
                            row[col["Year"]], species)] += row[col["Fish stocked"]]
        registry = json.loads((DATA_DIR / "lake_registry.json").read_text(encoding="utf-8"))
        cls.waterbody = {e["lake_id"]: str(e.get("waterbody_id") or "") for e in registry}
        cls.published = collections.Counter()
        for year in range(2021, 2027):
            for lake in json.loads((DATA_DIR / f"lakes_{year}.json").read_text(encoding="utf-8")):
                wid = cls.waterbody.get(lake["lake_id"], "")
                for row in lake["stockings"]:
                    cls.published[(wid, row["year"], row["species"])] += row["number"]

    def test_the_two_publications_agree_on_almost_every_lake_year(self):
        both = [k for k in set(self.export) | set(self.published)
                if self.export[k] and self.published[k]]
        differ = [k for k in both if self.export[k] != self.published[k]]
        unexplained = [k for k in differ if k not in self.KNOWN_DISAGREEMENTS]
        self.assertEqual(
            unexplained, [],
            "\n".join(f"{k}: map {self.export[k]}, reports {self.published[k]}"
                      for k in unexplained))
        self.assertGreater(len(both), 2000, "the comparison covered too little to mean anything")

    def test_no_lake_carries_exactly_twice_what_the_map_says(self):
        """The signature of one lake absorbing its neighbour's rows."""
        doubled = [k for k in self.export
                   if self.export[k] and self.published[k] == self.export[k] * 2]
        self.assertEqual(doubled, [], f"{len(doubled)} lake-year(s) at exactly double")


class ConfirmedFactsSurviveTests(unittest.TestCase):
    """An answer you give must outlive the next rebuild.

    reconcile.py --apply used to write straight into data/lake_registry.json,
    and build_history.py — the command --apply prints on its very next line —
    rebuilds that file from the reports and overwrites every field in it. So
    every answer was erased by the step you were told to run next, and CI, which
    runs exactly that sequence and then diffs, would have failed on the first
    such commit. Nothing caught it because reconcile.py had no input at all
    until the stocking map was imported.
    """

    def test_apply_never_writes_to_the_registry(self):
        """The registry is a build artefact. Answers belong in an input."""
        source = (Path(__file__).parent / "reconcile.py").read_text(encoding="utf-8")
        self.assertNotIn("REGISTRY.write_text", source,
                         "reconcile.py writes the registry, which the next build overwrites")

    def test_a_confirmed_fact_survives_a_rebuild(self):
        """Every row in lake_facts.csv is present in the built registry."""
        facts = DATA_DIR / "lake_facts.csv"
        if not facts.exists():
            self.skipTest("no confirmed facts recorded yet")
        registry = {e["lake_id"]: e
                    for e in json.loads((DATA_DIR / "lake_registry.json").read_text(encoding="utf-8"))}
        checked = 0
        with facts.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                lake = registry.get(row["lake_id"])
                self.assertIsNotNone(lake, f"{row['lake_id']} is not in the registry")
                if row["field"] == "zone":
                    self.assertEqual(lake["zone"], row["value"], row["note"])
                    checked += 1
                elif row["field"] == "surface_area_ha":
                    self.assertEqual(lake["surface_area_ha"], float(row["value"]), row["note"])
                    checked += 1
        self.assertGreater(checked, 0, "nothing checkable was recorded")

    def test_a_confirmed_fact_never_overwrites_what_the_pipeline_found(self):
        """Blanks only, in both directions.

        reconcile.py records a row only where the repo had nothing, and
        apply_facts fills only where the repo still has nothing. A value the
        pipeline derived for itself is a disagreement for a person to settle,
        never something replaced from a file.
        """
        import build_history, registry as registry_module

        class Fake:
            lakes = [{"lake_id": "wb1", "zone": "ES1", "surface_area_ha": 3.0,
                      "ats_codes": ["SW1-2-3-W4"], "lat": 50.0, "lon": -114.0,
                      "coord_source": "profile"}]
            def reindex(self):
                pass

        lake = Fake.lakes[0]
        original = dict(lake)
        facts = registry_module.FACTS_PATH
        backup = facts.read_text(encoding="utf-8") if facts.exists() else None
        try:
            facts.write_text(
                "lake_id,field,value,note\n"
                "wb1,zone,PP2,trying to overwrite\n"
                "wb1,surface_area_ha,999,trying to overwrite\n"
                "wb1,position,1.0,2.0,trying to overwrite\n",
                encoding="utf-8")
            build_history.apply_facts(Fake())
        finally:
            if backup is not None:
                facts.write_text(backup, encoding="utf-8")
            else:
                facts.unlink()
        self.assertEqual(lake["zone"], original["zone"])
        self.assertEqual(lake["surface_area_ha"], original["surface_area_ha"])
        self.assertEqual(lake["lat"], original["lat"])

    def test_reconcile_reaches_a_fixed_point(self):
        """Running --apply twice records nothing the second time."""
        facts = DATA_DIR / "lake_facts.csv"
        if not facts.exists():
            self.skipTest("no confirmed facts recorded yet")
        import reconcile
        lakes = json.loads((DATA_DIR / "lake_registry.json").read_text(encoding="utf-8"))
        site = reconcile.load_site()
        if site is None:
            self.skipTest("the collected CSV is not present")
        fills, _, _ = reconcile.compare(lakes, site)
        applicable = [f for f in fills if f["field"] in reconcile.APPLICABLE]
        self.assertEqual(
            applicable, [],
            f"{len(applicable)} answer(s) still unrecorded after a build; "
            f"run reconcile.py --apply and rebuild")


class PublishedWaterbodyIdTests(unittest.TestCase):
    """Alberta's id for lakes this repo minted from a land description.

    Thirteen lakes come from reports that print no waterbody id, so the exact
    id join the rest of the pipeline relies on cannot see them — which is why
    they got no depth even where Alberta publishes one. Eight are recoverable
    from the stocking map.
    """

    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((DATA_DIR / "lake_registry.json").read_text(encoding="utf-8"))

    def test_a_published_id_is_never_mistaken_for_the_reports_own(self):
        """They are different claims and live in different fields.

        lake_id is minted as "wb" + the waterbody id wherever the reports give
        one. Writing a recovered id into waterbody_id would either contradict
        the lake_id or force a rename that breaks every ?lake= link and every
        answer already recorded against the old id.
        """
        for lake in self.registry:
            if lake.get("published_waterbody_id"):
                self.assertIsNone(lake.get("waterbody_id"),
                                  f"{lake['name']} carries both kinds of id")
                self.assertFalse(lake["lake_id"].startswith("wb"),
                                 f"{lake['name']} has a minted id and a wb lake_id")

    def test_no_published_id_collides_with_a_real_one(self):
        reported = {str(l["waterbody_id"]) for l in self.registry if l.get("waterbody_id")}
        for lake in self.registry:
            recovered = lake.get("published_waterbody_id")
            if recovered:
                self.assertNotIn(str(recovered), reported,
                                 f"{lake['name']} claims an id another lake already holds")

    def test_every_published_id_rests_on_two_agreeing_fields(self):
        """A land description unique on BOTH sides, and a name that matches.

        Seven registry codes are shared by two lakes and five of the map's are,
        so a code that is not unique both ways proves nothing. Watridge Lake is
        why the name check is not optional: its published position is 140 km
        from this very land description.
        """
        import reconcile
        site = reconcile.load_site()
        if site is None:
            self.skipTest("the collected CSV is not present")
        proposals = {p["lake_id"]: p for p in
                     reconcile.propose_published_ids(self.registry, site)}
        recovered = [l for l in self.registry if l.get("published_waterbody_id")]
        self.assertTrue(recovered, "no published ids were recovered")
        for lake in recovered:
            # Already applied, so it no longer proposes; re-derive it against a
            # copy with the field cleared.
            blank = dict(lake)
            blank.pop("published_waterbody_id")
            others = [l for l in self.registry if l["lake_id"] != lake["lake_id"]]
            again = reconcile.propose_published_ids(others + [blank], site)
            match = [p for p in again if p["lake_id"] == lake["lake_id"]]
            self.assertEqual(len(match), 1,
                             f"{lake['name']}'s id no longer follows from the evidence")
            self.assertEqual(match[0]["alberta_value"],
                             str(lake["published_waterbody_id"]))

    def test_a_name_that_disagrees_blocks_the_join(self):
        """The land description alone happens to be enough for today's eight.

        It is not enough in general — seven registry codes are shared and five
        of the map's are — so the name has to agree too. This tests the guard
        rather than the current data, which would pass without it.
        """
        import reconcile
        lake = {"lake_id": "lk9999", "name": "Somewhere Entirely Else",
                "ats_codes": ["NW1-2-3-W4"], "waterbody_id": None}
        site = {"999999": {"waterbody_id": "999999",
                           "legal_land_description": "NW1-2-3-W4",
                           "page_name": "Not The Same Lake At All"}}
        self.assertEqual(reconcile.propose_published_ids([lake], site), [],
                         "a land description matched two lakes with unrelated names")

        agreeing = dict(lake, name="Not The Same Lake At All")
        self.assertEqual(len(reconcile.propose_published_ids([agreeing], site)), 1,
                         "an agreeing name was refused")

    def test_a_shared_land_description_blocks_the_join(self):
        """A code held by two lakes on either side proves nothing."""
        import reconcile
        shared = [{"lake_id": "lk9998", "name": "Twin Lake", "waterbody_id": None,
                   "ats_codes": ["NW1-2-3-W4"]},
                  {"lake_id": "lk9997", "name": "Twin Lake", "waterbody_id": None,
                   "ats_codes": ["NW1-2-3-W4"]}]
        site = {"999999": {"waterbody_id": "999999",
                           "legal_land_description": "NW1-2-3-W4",
                           "page_name": "Twin Lake"}}
        self.assertEqual(reconcile.propose_published_ids(shared, site), [],
                         "a land description two lakes share was used as evidence")

    def test_the_recovered_lakes_reach_the_depth_file(self):
        """The whole point: they were invisible to the join before."""
        path = DATA_DIR / "lake_depth.json"
        if not path.exists():
            self.skipTest("depth has not been built")
        depths = json.loads(path.read_text(encoding="utf-8"))["lakes"]
        recovered = [l for l in self.registry if l.get("published_waterbody_id")]
        self.assertTrue(recovered)
        for lake in recovered:
            self.assertIn(lake["lake_id"], depths,
                          f"{lake['name']} still has no entry despite a published id")

    def test_a_watridge_style_position_is_still_refused(self):
        """The id is recovered; the bad coordinate is not adopted with it."""
        watridge = [l for l in self.registry if l["name"] == "Watridge Lake"]
        self.assertEqual(len(watridge), 1)
        lake = watridge[0]
        self.assertEqual(str(lake.get("published_waterbody_id")), "6120")
        self.assertLess(abs(lake["lon"] - (-115.43)), 0.1,
                        "Watridge moved to the map's published longitude")


class MeanDepthTests(unittest.TestCase):
    """A mean depth Alberta published, and one nobody did.

    The second kind is the first derived quantity this repo publishes, so the
    rules around it are the point of these tests: it is never stored where a
    measurement is stored, and it can never change a word of the advice.
    """

    def test_a_published_mean_is_carried_through_unchanged(self):
        import depth
        self.assertEqual(depth.mean_depth(7.0, 4.0),
                         {"m": 4.0, "source": "mywildalberta"})

    def test_a_mean_deeper_than_the_max_is_refused_not_repaired(self):
        """Castor Eastside Trout Pond: 22 m mean against a 7 m max, on 1 ha.

        One of the two numbers is wrong and there is no way to tell which, so
        the implausible one is dropped and the other kept. Swapping them would
        not be a repair, only a different guess, and a one-hectare pond is
        neither 22 m deep nor 7 m deep on average.
        """
        import depth
        found = depth.mean_depth(7.0, 22.0)
        self.assertEqual(found["source"], "contradicted")
        self.assertNotIn("m", found)
        self.assertNotIn("range_m", found)
        # and no estimate is substituted for it either
        self.assertIsNone(found.get("range_m"))

    def test_an_estimate_is_never_stored_as_a_measurement(self):
        """Reading one field must be enough to know which kind it is."""
        import depth
        found = depth.mean_depth(7.0, None)
        self.assertIn("range_m", found)
        self.assertNotIn("m", found)
        self.assertEqual(found["source"], "estimated")
        self.assertIn("from_max_depth_m", found)
        self.assertIn("method", found)

    def test_the_published_file_keeps_the_two_kinds_apart(self):
        path = DATA_DIR / "lake_depth.json"
        if not path.exists():
            self.skipTest("depth has not been built")
        lakes = json.loads(path.read_text(encoding="utf-8"))["lakes"]
        estimated = 0
        for key, entry in lakes.items():
            mean = entry.get("mean_depth")
            if not mean:
                continue
            if mean.get("source") == "estimated":
                estimated += 1
                self.assertNotIn("m", mean, f"{key} stores an estimate as a measurement")
                self.assertIn("from_max_depth_m", mean, key)
            elif mean.get("source") == "mywildalberta":
                self.assertIn("m", mean, key)
                self.assertNotIn("range_m", mean, key)
        self.assertGreater(estimated, 40, "almost nothing was estimated")

    def test_an_estimate_never_changes_the_advice(self):
        """The decisive rule.

        Every lake an estimate could serve already has a measured maximum, so
        an estimate can only ever alter advice that already exists — it can
        never extend it to a lake that had none. Zero upside, in the one place
        where being wrong puts someone in eight metres of water.
        """
        import depth, inspect

        # Neither advice function can even see a mean depth.
        for fn in (depth.stratification, depth.winterkill):
            names = list(inspect.signature(fn).parameters)
            self.assertNotIn("mean_depth_m", names, f"{fn.__name__} takes a mean depth")

        # And end to end: the same lake built with a published mean, with none
        # (so it is estimated), and with a contradictory one, must produce
        # byte-identical stratification and winterkill all three times.
        lakes = [{"lake_id": "wbtest", "waterbody_id": "999001"}]
        rows = {"999001": {"max_depth_m": 7.0, "surface_area_ha": 40.0,
                           "stated_unavailable": False}}
        advice = []
        for mean in (4.0, None, 22.0):
            rows["999001"]["mean_depth_m"] = mean
            with unittest.mock.patch.object(depth, "load_depths", lambda: rows), \
                 unittest.mock.patch.object(depth, "load_aerated", lambda: (set(), set())):
                built, _ = depth.build(lakes)
            entry = built["wbtest"]
            advice.append((entry["stratification"], entry["winterkill"]))
            # the mean itself does differ, which is the point of storing it apart
            self.assertIsNotNone(entry["mean_depth"])
        self.assertEqual(advice[0], advice[1], "an estimate changed the advice")
        self.assertEqual(advice[0], advice[2], "a contradiction changed the advice")

    def test_a_band_never_reaches_the_bottom(self):
        """A lake whose average depth equals its maximum has vertical sides."""
        import depth
        for max_depth in (2.0, 5.0, 7.0, 12.0, 65.0):
            found = depth.mean_depth(max_depth, None)
            if not found:
                continue
            low, high = found["range_m"]
            self.assertLess(low, high, max_depth)
            self.assertLess(high, max_depth, f"{max_depth} m band reaches the bottom")
            self.assertGreater(low, 0, max_depth)

    def test_a_pond_too_shallow_to_say_anything_about_gets_no_band(self):
        import depth
        self.assertIsNone(depth.mean_depth(1.0, None))

    def test_the_estimator_is_still_as_good_as_it_claims(self):
        """Leave one lake out, predict it from the rest, and measure the miss.

        Re-derived from the committed CSV rather than trusted from a comment,
        the same way the coordinate test re-measures the survey-grid error. The
        README quotes 25%; this fails if it drifts past 30%.
        """
        import statistics
        csv_path = ROOT / "data" / "raw" / "mywildalberta_lakes.csv"
        if not csv_path.exists():
            self.skipTest("the collected CSV is not present")
        pairs = []
        with csv_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    mx, mn = float(row["max_depth_m"]), float(row["mean_depth_m"])
                except ValueError:
                    continue
                if mn <= mx:
                    pairs.append((mx, mn))
        self.assertGreater(len(pairs), 40, "too few pairs to measure anything")
        errors = []
        for i, (mx, mn) in enumerate(pairs):
            others = [b / a for j, (a, b) in enumerate(pairs) if j != i]
            errors.append(abs(mx * statistics.median(others) - mn) / mn)
        self.assertLess(statistics.median(errors), 0.30,
                        f"median relative error is now {statistics.median(errors):.0%}")

    def test_the_published_band_matches_the_ratios_it_claims_to_come_from(self):
        """The constants are hard-coded; this checks they still describe the data."""
        import depth, statistics
        csv_path = ROOT / "data" / "raw" / "mywildalberta_lakes.csv"
        if not csv_path.exists():
            self.skipTest("the collected CSV is not present")
        ratios = []
        with csv_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    mx, mn = float(row["max_depth_m"]), float(row["mean_depth_m"])
                except ValueError:
                    continue
                if mn <= mx:
                    ratios.append(mn / mx)
        ratios.sort()
        def percentile(p):
            i = p * (len(ratios) - 1)
            lo = int(i)
            hi = min(lo + 1, len(ratios) - 1)
            return ratios[lo] + (i - lo) * (ratios[hi] - ratios[lo])
        self.assertAlmostEqual(depth.MEAN_MAX_RATIO_LOW, percentile(0.10), places=1)
        self.assertAlmostEqual(depth.MEAN_MAX_RATIO_HIGH, percentile(0.90), places=1)
        inside = sum(1 for r in ratios
                     if depth.MEAN_MAX_RATIO_LOW <= r <= depth.MEAN_MAX_RATIO_HIGH)
        self.assertAlmostEqual(inside / len(ratios), depth.MEAN_ESTIMATE_COVERS, places=1)


class LakeProfileTests(unittest.TestCase):
    """Facilities, the province's prose, and the photo index."""

    @classmethod
    def setUpClass(cls):
        path = DATA_DIR / "lake_profile.json"
        if not path.exists():
            raise unittest.SkipTest("profiles have not been built")
        cls.doc = json.loads(path.read_text(encoding="utf-8"))
        cls.lakes = cls.doc["lakes"]
        cls.registry = json.loads((DATA_DIR / "lake_registry.json").read_text(encoding="utf-8"))

    def test_it_is_keyed_the_way_the_app_keys_lakes(self):
        known = {e["lake_id"] for e in self.registry}
        for key in self.lakes:
            self.assertIn(key, known, f"{key} is not a lake")

    def test_a_blank_amenities_cell_is_null_and_not_an_empty_list(self):
        """Alberta not saying is not a lake with no toilet.

        An empty list would let the app report "has no facilities", which is a
        claim nobody made. null is the absence of a statement, and the filter
        panel says how many lakes are in that position.
        """
        nulls = 0
        for key, entry in self.lakes.items():
            if entry.get("amenities") is None:
                nulls += 1
                self.assertIsNone(entry.get("facets"), key)
            else:
                self.assertNotEqual(entry["amenities"], [], f"{key} has an empty list")
                self.assertTrue(entry.get("facets"), key)
        self.assertGreater(nulls, 0, "expected some lakes to state nothing")

    def test_every_child_facet_carries_its_parent(self):
        """A filter for Trails must match a lake that only says Trails Hiking."""
        import profile
        for key, entry in self.lakes.items():
            facets = entry.get("facets") or []
            for facet in facets:
                parent = profile.parent_of(facet)
                if parent:
                    self.assertIn(parent, facets,
                                  f"{key} has {facet} without {parent}")

    def test_no_facet_offered_as_a_filter_is_a_child(self):
        """After the rollup a child is the same filter under another name.

        Every lake with Paddling Canoe also has Paddling, so the two have
        identical counts and offering both is offering one filter twice.
        """
        import profile
        for facet in self.doc["facets"]:
            self.assertIsNone(profile.parent_of(facet["name"]),
                              f"{facet['name']} is a narrower kind of something else")

    def test_every_offered_facet_is_worth_filtering_by(self):
        import profile
        self.assertTrue(self.doc["facets"])
        for facet in self.doc["facets"]:
            self.assertGreaterEqual(facet["lakes"], profile.FILTER_FLOOR, facet["name"])

    def test_the_counts_match_the_lakes(self):
        counted = collections.Counter()
        for entry in self.lakes.values():
            for facet in entry.get("facets") or []:
                counted[facet] += 1
        for facet in self.doc["facets"]:
            self.assertEqual(facet["lakes"], counted[facet["name"]], facet["name"])

    def test_no_photo_leaves_the_published_host(self):
        """These are Alberta's photographs and they stay on Alberta's server."""
        path = DATA_DIR / "lake_photos.json"
        if not path.exists():
            self.skipTest("photos have not been built")
        gallery = json.loads(path.read_text(encoding="utf-8"))["lakes"]
        total = 0
        for key, shots in gallery.items():
            for shot in shots:
                total += 1
                self.assertTrue(shot["url"].startswith("https://mywildalberta.ca/"),
                                f"{key}: {shot['url']}")
        self.assertGreater(total, 500)

    def test_a_photo_count_is_never_published_without_the_photos(self):
        path = DATA_DIR / "lake_photos.json"
        if not path.exists():
            self.skipTest("photos have not been built")
        gallery = json.loads(path.read_text(encoding="utf-8"))["lakes"]
        for key, entry in self.lakes.items():
            if entry.get("photo_count"):
                self.assertEqual(entry["photo_count"], len(gallery.get(key, [])), key)

    def test_the_year_files_did_not_grow(self):
        """None of this changes year to year, so none of it belongs in a year file.

        index.html merges lakes across the selected years and lets a later year
        overwrite a scalar, so a description stored there would be written into
        sixteen files and which copy you saw would depend on which years happen
        to be selected.
        """
        sample = json.loads((DATA_DIR / "lakes_2026.json").read_text(encoding="utf-8"))
        for lake in sample:
            for field in ("description", "facets", "photo_count", "photos"):
                self.assertNotIn(field, lake, f"{field} leaked into a year file")


class OutOfScopeTests(unittest.TestCase):
    """Waters Alberta stocks that this map deliberately does not show."""

    @classmethod
    def setUpClass(cls):
        path = DATA_DIR / "out_of_scope.csv"
        if not path.exists():
            raise unittest.SkipTest("the out-of-scope list has not been built")
        with path.open(newline="", encoding="utf-8") as handle:
            cls.rows = list(csv.DictReader(handle))

    def test_nothing_trout_bearing_was_quietly_dropped(self):
        import sources
        names = {"RAINBOW TROUT", "BROOK TROUT", "BROWN TROUT", "TIGER TROUT",
                 "CUTTHROAT TROUT", "WESTSLOPE CUTTHROAT TROUT"}
        self.assertEqual(len(names), len(sources.TROUT_SPECIES),
                         "the species this map covers changed; revisit the list")
        for row in self.rows:
            published = {s.strip() for s in row["species"].split(";")}
            self.assertFalse(published & names,
                             f"{row['name']} is stocked with trout and is not out of scope")

    def test_every_row_names_a_reason(self):
        self.assertTrue(self.rows)
        for row in self.rows:
            self.assertTrue(row["why"], row["name"])
            self.assertTrue(row["species"], row["name"])

    def test_none_of_them_is_on_the_map(self):
        registry = json.loads((DATA_DIR / "lake_registry.json").read_text(encoding="utf-8"))
        mapped = {str(e.get("waterbody_id") or "") for e in registry}
        mapped |= {str(e.get("published_waterbody_id") or "") for e in registry}
        for row in self.rows:
            self.assertNotIn(row["waterbody_id"], mapped,
                             f"{row['name']} is both mapped and listed as out of scope")

    def test_no_waterbody_was_minted_from_the_stocking_map(self):
        """The failure mode the README spends a page on: an invented lake.

        The importer reads Alberta's map and writes CSVs. It never adds a lake;
        only the stocking reports do that, through build_history.
        """
        source = (Path(__file__).parent / "import_stocking_map.py").read_text(encoding="utf-8")
        for forbidden in ("reg.mint", ".mint(", "add_lake"):
            self.assertNotIn(forbidden, source,
                             f"the importer calls {forbidden}")


class AcaRosterTests(unittest.TestCase):
    """ACA's published Lake Aeration Program roster, transcribed by hand.

    Alberta's lake pages name twelve aerated lakes. ACA's roster names
    twenty-two, and the two only partly overlap — Camp 9 Trout Pond and
    Salter's Lake are stated by Alberta and absent from ACA's, which is what a
    fish-and-game club windmill outside the province's programme looks like.
    Both are kept; neither list is treated as the whole truth.
    """

    @classmethod
    def setUpClass(cls):
        cls.roster_path = DATA_DIR / "aca_aeration_roster.csv"
        if not cls.roster_path.exists():
            raise unittest.SkipTest("the roster has not been transcribed")
        with cls.roster_path.open(newline="", encoding="utf-8") as handle:
            cls.roster = list(csv.DictReader(handle))
        cls.registry = {e["lake_id"]: e for e in
                        json.loads((DATA_DIR / "lake_registry.json").read_text(encoding="utf-8"))}

    def test_every_roster_row_names_a_lake_on_the_map(self):
        for row in self.roster:
            self.assertIn(row["lake_id"], self.registry,
                          f"{row['name']} is not a lake this map holds")

    def test_the_roster_is_keyed_on_an_id_and_not_a_name(self):
        """Swan, Spring and Birch Lake are each one of several in Alberta.

        Matching ACA's roster on name alone would aerate the wrong water. Swan
        Lake is the case that proves it: the roster says only "Swan Lake", and
        ACA's own page places it 42 km west of Valleyview, which is wb5944 and
        not the Red Earth one.
        """
        header = self.roster_path.read_text(encoding="utf-8").splitlines()[0]
        self.assertTrue(header.startswith("lake_id,"), header)
        swan = [r for r in self.roster if r["lake_id"] == "wb5944"]
        self.assertEqual(len(swan), 1)
        self.assertIn("Valleyview", swan[0]["note"])

    def test_the_roster_reaches_the_aerated_list(self):
        import depth
        applied, _ = depth.load_aerated()
        self.assertTrue(applied)
        for row in self.roster:
            lake = self.registry[row["lake_id"]]
            wid = str(lake.get("waterbody_id") or lake.get("published_waterbody_id") or "")
            self.assertIn(wid, applied, f"{row['name']} is on the roster but not applied")

    def test_both_sources_survive_each_other(self):
        """Alberta states two lakes ACA does not list. They stay aerated."""
        path = ROOT / "data" / "raw" / "aca_aerated_lakes.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        tiers = collections.Counter(r["confidence"] for r in rows)
        self.assertGreaterEqual(tiers["stated"], 12)
        self.assertGreaterEqual(tiers["published_list"], 10)
        stated_names = {r["name"] for r in rows if r["confidence"] == "stated"}
        self.assertIn("Camp 9 Trout Pond", stated_names)
        self.assertIn("Salter's Lake", stated_names)

    def test_aeration_still_only_lowers_a_band_on_a_measured_depth(self):
        path = DATA_DIR / "lake_depth.json"
        if not path.exists():
            self.skipTest("depth has not been built")
        lakes = json.loads(path.read_text(encoding="utf-8"))["lakes"]
        for key, entry in lakes.items():
            if entry.get("aerated"):
                if entry["max_depth_m"] is None:
                    self.assertIsNone(entry["winterkill"], key)
                else:
                    self.assertTrue(entry["winterkill"]["inputs"]["aeration"], key)
