"""README counts must match the data and index.html."""
import glob
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUMBERS = {"six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def species_by_lake():
    out = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "lakes_20*.json"))):
        with open(path, encoding="utf-8") as f:
            for row in json.load(f):
                out.setdefault(row["lake_id"], set()).update(
                    s["species"] for s in row.get("stockings", []))
    return out


def readme_section():
    m = re.search(r"^## Walleye and pike waters\n(.*?)(?=^## )",
                  read("README.md"), re.S | re.M)
    assert m, "README section 'Walleye and pike waters' not found"
    return " ".join(m.group(1).split())


class ReadmeCounts(unittest.TestCase):
    def test_walleye_pike_waters(self):
        only = [s for s in species_by_lake().values() if s and s <= {"WALL", "NRPK"}]
        wall = sum(s == {"WALL"} for s in only)
        pike = sum(s == {"NRPK"} for s in only)
        both = sum(s == {"WALL", "NRPK"} for s in only)
        text = readme_section()
        m = re.search(r"(\d+) waters stocked only with walleye or pike "
                      r"\((\d+) walleye, (\d+) pike, (\d+) both\)", text)
        self.assertIsNotNone(m, "README sentence with the 35 (33/1/1) split not found")
        self.assertEqual((len(only), wall, pike, both), tuple(int(x) for x in m.groups()[:1]) + tuple(int(x) for x in m.groups()[1:]))

    def test_species_count_word(self):
        m = re.search(r"const SPECIES_ORDER = \[(.*?)\]", read("index.html"), re.S)
        n = len(re.findall(r'"[A-Z]+"', m.group(1)))
        r = re.search(r"\*\*Species\*\* — (\w+)", read("README.md"))
        self.assertIsNotNone(r)
        self.assertEqual(NUMBERS.get(r.group(1)), n)


if __name__ == "__main__":
    unittest.main()
