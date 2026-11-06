"""Decision 23 A: boat launches and roads from OpenStreetMap in the 3D view.

    PYTHONPATH=scripts python3 -m unittest scripts/test_lake_access.py

The script checks use a made-up Overpass answer on a real lakebed grid, so they
run without a network. The data checks run once data/lake_access.json exists.
"""

import json
import unittest
from pathlib import Path

import depth_grids
import lake_access as la

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"


def node(i, lat, lon, **tags):
    return {"type": "node", "id": i, "lat": lat, "lon": lon, "tags": tags}


def way(i, pts, **tags):
    return {"type": "way", "id": i, "geometry": [{"lat": a, "lon": b} for a, b in pts], "tags": tags}


class AccessScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stem, cls.meta = la.grids()[0]
        cls.g = la.Grid(cls.meta)
        g = cls.g
        # A water cell next to land, and a land cell far from any water.
        cls.edge = cls.far = None
        for k in range(g.w * g.h):
            i, j = k % g.w, k // g.w
            if cls.edge is None and g.water[k] and any(
                    0 <= m < g.w * g.h and not g.water[m] for m in (k - 1, k + 1, k - g.w, k + g.w)):
                cls.edge = (i, j)
            if cls.far is None and g.dist[k] * g.c > 1000:
                cls.far = (i, j)
        assert cls.edge and cls.far

    def ll(self, i, j):
        m = self.meta
        return depth_grids.tm_inverse(m["x0"] + i * m["cell_m"], m["y0"] - j * m["cell_m"])

    def test_cell_and_position_agree(self):
        lat, lon = self.ll(10, 20)
        i, j = self.g.cell(lat, lon)
        self.assertAlmostEqual(i, 10, places=2)
        self.assertAlmostEqual(j, 20, places=2)

    def test_a_launch_on_the_shore_is_kept_and_one_inland_is_not(self):
        shore = self.ll(*self.edge)
        inland = self.ll(*self.far)
        out = la.keep_for(self.g, [node(1, *shore, leisure="slipway", name="Test launch"),
                                   node(2, *shore, leisure="slipway", access="private"),
                                   node(3, *inland, leisure="slipway")])
        self.assertEqual(len(out["launches"]), 2)
        self.assertEqual({x.get("name") for x in out["launches"]}, {"Test launch", None})
        self.assertEqual(sum(1 for x in out["launches"] if x.get("private")), 1)

    def test_roads_are_cut_to_the_grid_and_service_roads_kept_only_near_water(self):
        g = self.g
        across = [self.ll(-40, g.h // 2), self.ll(g.w // 2, g.h // 2), self.ll(g.w + 40, g.h // 2)]
        far_a, far_b = self.ll(*self.far), self.ll(self.far[0], self.far[1] + 3)
        out = la.keep_for(g, [way(10, across, highway="tertiary", name="Range Road 1"),
                              way(11, [far_a, far_b], highway="service"),
                              way(12, [far_a, far_b], highway="footway")])
        self.assertEqual(len(out["roads"]), 1)
        r = out["roads"][0]
        self.assertEqual((r["kind"], r["name"]), ("tertiary", "Range Road 1"))
        # Cut exactly at the edge (one cell outside), give or take the 5-decimal rounding (about 1 m).
        ends = [g.cell(*r["pts"][0]), g.cell(*r["pts"][-1])]
        self.assertAlmostEqual(min(e[0] for e in ends), -1, delta=0.05)
        self.assertAlmostEqual(max(e[0] for e in ends), g.w, delta=0.05)
        for lat, lon in r["pts"]:
            self.assertTrue(g.inside(*g.cell(lat, lon), margin=1.05), (lat, lon))

    def test_short_pieces_are_dropped(self):
        a = self.ll(*self.edge)
        b = self.ll(self.edge[0] + 0.5, self.edge[1])     # about half a cell: under 60 m
        self.assertEqual(la.keep_for(self.g, [way(20, [a, b], highway="residential")])["roads"], [])


@unittest.skipUnless((DATA / "lake_access.json").exists(), "data/lake_access.json not built yet")
class AccessDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads((DATA / "lake_access.json").read_text(encoding="utf-8"))
        cls.index = json.loads((DATA / "depth_grids" / "index.json").read_text(encoding="utf-8"))

    def test_credit_and_licence(self):
        self.assertEqual(self.doc["credit"], "© OpenStreetMap contributors")
        self.assertIn("ODbL", self.doc["licence"])
        self.assertEqual(self.doc["url"], "https://www.openstreetmap.org/copyright")
        self.assertRegex(self.doc["retrieved"], r"^\d{4}-\d{2}-\d{2}$")

    def test_every_lakebed_grid_has_an_entry_and_launches_lie_on_it(self):
        stems = {Path(m["file"]).stem: m for m in self.index["grids"].values()}
        self.assertEqual(set(self.doc["grids"]), set(stems))
        for stem, v in self.doc["grids"].items():
            g = la.Grid(stems[stem])
            for s in v["launches"]:
                i, j = g.cell(s["lat"], s["lon"])
                self.assertTrue(g.inside(i, j, 0), (stem, s))
                self.assertLessEqual(g.water_m(i, j), la.LAUNCH_NEAR_M, (stem, s))


class AccessViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d3 = (ROOT / "js" / "depth-3d.js").read_text(encoding="utf-8")

    def test_the_layer_is_on_at_the_start_with_its_credit(self):
        self.assertIn('"drop", "access"];', self.d3)
        self.assertIn('access: ["Boat launches and roads", "c", "#F4F1E8"]', self.d3)
        self.assertIn('href="https://www.openstreetmap.org/copyright"', self.d3)
        self.assertIn("© OpenStreetMap contributors</a> (ODbL)", self.d3)
        self.assertIn("OpenStreetMap shows no boat launch on this lake.", self.d3)

    def test_a_launch_gives_directions_and_roads_follow_the_layer_switch(self):
        draw = self.d3[self.d3.index("// ---- decision 23 A"):self.d3.index('var noAcc = el.querySelector("[data-noaccess]")')]
        self.assertIn("shore: true", draw)                  # pick() adds the directions link
        self.assertIn("L.roads.add(line)", draw)
        self.assertEqual(self.d3.count('if (id === "access") L.roads.visible = c.checked;'), 2)
        self.assertIn('if (c.dataset.layer === "access") L.roads.visible = c.checked;', self.d3)
        self.assertIn("L.access, L.spots", self.d3)        # launches answer a tap first

    def test_the_view_opens_without_the_file(self):
        self.assertIn("loadAccess()]).then(function (got) {", self.d3)
        self.assertEqual(self.d3.count("mine.access = accessFor(e.grid, got[2]);"), 2)
        self.assertIn("accessLoading = null; return null;", self.d3)

    def test_offline_and_learn(self):
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn('"data/lake_access.json"', sw)
        learn = (ROOT / "learn" / "depth-model.html").read_text(encoding="utf-8")
        self.assertIn('<h3 id="layer-access">Boat launches and roads</h3>', learn)
        self.assertIn('data-demo="access"', learn)
        self.assertIn("    access: { layers: [\"access\"]", self.d3)


if __name__ == "__main__":
    unittest.main()
