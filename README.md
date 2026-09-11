# Alberta Trout Stocking Map

Interactive map of Alberta Environment's annual trout stocking reports,
spanning multiple years with filterable species, distance, year selection,
and charts showing stocking trends.

Hosted via GitHub Pages: just push to `main` and the map is live at
`https://<your-username>.github.io/<repo-name>/`.

## Folder structure

```
alberta-trout-map/
├── index.html                      ← the map (open in browser)
├── vendor/                         ← Leaflet 1.9.4 + Chart.js 4.4.0, checked in
├── data/
│   ├── manifest.json               ← which years are available
│   ├── lakes_2025.json             ← one file per year
│   └── lakes_YYYY.json
├── profiles/
│   └── mywildalberta_profiles.csv  ← coordinates, zone, amenities
├── scripts/
│   ├── ats.py                      ← land description → lat/lon
│   ├── extract_alberta_trout_v2.py ← PDF → lakes_YYYY.json
│   ├── merge_profiles.py           ← enrich a year's JSON with profile data
│   ├── check_consistency.py        ← report mismatches across years
│   └── test_regression_checks.py   ← the test suite
└── README.md
```

The map libraries are committed under `vendor/` rather than loaded from a CDN,
so the map keeps working offline and cannot break when a CDN is unreachable.

## Adding a new year

### From a PDF report

```bash
# 1. Extract stocking data from the Alberta Environment PDF
cd scripts
python extract_alberta_trout_v2.py path/to/stocking_2026.pdf 2026

# 2. Move the output into data/
mv lakes_2026.json ../data/lakes_2026.json

# 3. Enrich with profile data (zone, amenities, authoritative coords)
python merge_profiles.py ../data/lakes_2026.json
# Fix any "UNMATCHED" lakes by adding them to profiles/mywildalberta_profiles.csv,
# then re-run merge_profiles.py.

# 4. Add the year to data/manifest.json:
#    { "years": [2025, 2026] }

# 5. Run the consistency check across all years
python check_consistency.py
# Eyeball the report; fix any genuine mismatches before committing.

# 6. Commit and push
git add data/ profiles/
git commit -m "Add 2026 stocking data"
git push
```

### From a CSV

Convert your CSV to match the JSON schema, save it as
`data/lakes_YYYY.json`, then run `merge_profiles.py` and
`check_consistency.py` as above. The target schema:

```json
[
  {
    "ats": "NE10-2-28-W4",
    "name": "Payne Lake",
    "lat": 49.1117,
    "lon": -113.6558,
    "stockings": [
      {
        "species": "RNTR",
        "strain": "Campbell Lake",
        "genotype": "3N",
        "length_cm": 20.0,
        "number": 12000,
        "date": "14-Apr-26",
        "year": 2026
      }
    ],
    "total_fish": 12000,
    "species_set": ["RNTR"]
  }
]
```

Species codes: `RNTR` Rainbow, `BKTR` Brook, `BNTR` Brown, `TGTR` Tiger,
`CTTR` Cutthroat. Date format `D-Mon-YY` (e.g. `14-Apr-26`).

## Where lake coordinates come from

The stocking report never prints a latitude or longitude. It prints a land
description such as `SW4-36-8-W5`, which names a quarter-section: an 800 m
square on the survey grid. So every pin is positioned from one of three
sources, and `merge_profiles.py` records which in each lake's `coord_source`:

| `coord_source` | Where it comes from | Typical accuracy |
| --- | --- | --- |
| `override` | `override_lat` / `override_lon` in the profiles CSV | exact, you placed it |
| `profile` | `lat` / `lon` in the profiles CSV, verified by hand | on the lake |
| `ats` | Computed from the land description by `ats.py` | ~0.5 km |

To correct a single lake, add `override_lat` and `override_lon` columns to
`profiles/mywildalberta_profiles.csv`, fill them in for that row, and re-run
`merge_profiles.py`. An override always wins, so your correction survives every
later data refresh.

The `html_lat` / `html_lon` columns are deliberately ignored. They are not an
independent observation: for 249 of 265 rows they reproduce an old, buggy grid
calculation to within 50 m, which used to place every pin a median 6 km from
the water.

**How we know the coordinates are right.** The hand-verified `lat` / `lon`
column and the report's land descriptions are two independently produced
sources. Converted correctly, they agree to a median of 0.53 km, with 252 of
256 lakes inside 1.5 km — about the width of a quarter-section. Three lakes
still disagree by more than 2 km and `merge_profiles.py` prints them on every
run; check those on satellite imagery and set an override if needed.
`test_regression_checks.py` fails the build if that median ever rises above
1 km.

## Consistency checks

`check_consistency.py` scans all year files and reports:

1. **Unmatched ATS codes** — lake in stocking data, no profile row. Add
   the lake to `profiles/mywildalberta_profiles.csv` and re-run
   `merge_profiles.py`.
2. **Same ATS, different names** across years — cosmetic, but standardize
   the name so popups read consistently.
3. **Same name, different ATS codes** — could be two genuinely different
   lakes (report hints "different names in parentheticals" or coordinates
   far apart), or a typo creating a phantom pin (hints "likely typo" when
   coordinates are close).
4. **ATS section-letter variants** — same township/range with different
   NE/NW/SE/SW prefix. Usually a typo.

Run after every data update:

```bash
python scripts/check_consistency.py
# Or export to CSV for spreadsheet review:
python scripts/check_consistency.py --csv report.csv
# Or generate machine-readable planning summary:
python3 scripts/check_consistency.py --json-out data/consistency_summary.json
```

## Tests

```bash
cd scripts && python3 -m unittest discover -p "test_*.py"
```

The suite covers the survey-grid conversion and its accuracy against the
verified coordinates, the coordinate precedence rules, area parsing, and the
committed data itself (every lake has coordinates inside Alberta, totals match
their stocking rows, dates parse).

GitHub Actions runs the same suite on every push, and additionally fails the
build when `data/lakes_2025.json` or `data/consistency_summary.json` no longer
match what the scripts would produce — so committed data can never drift away
from the profiles CSV.

## Running locally

Because the map fetches JSON files over HTTP, opening `index.html` via
`file://` won't work in most browsers (CORS blocks the fetches). Use a
simple local server:

```bash
# From the project root:
python -m http.server 8000
# Open http://localhost:8000
```

On GitHub Pages the fetches work natively — no server setup needed.

## Features

- **Species filter** — toggle which trout species show on the map and
  in charts.
- **Distance slider** — hide lakes beyond N km from Red Deer (0–1000).
- **Year chips** — click to toggle individual years. Shortcuts: All /
  None / Last 5 / Latest.
- **Charts panel** — toggle bottom panel with three views:
  - Stacked by species (how much of each species per year)
  - Spring vs Fall (seasonal split per year)
  - Trend (line chart per species over time)
- **Basemap toggle** — topographic (default) or street.
- **Popups** — per-lake stocking history, zone link, surface area, amenities,
  Google Maps link. Reflects current filters and stays open while you change
  them. Lakes positioned from the land description say so.
- **Planning summary** — year-over-year total fish and trend direction
  in the chart panel.
- **Data quality indicator** — how many lakes sit at verified coordinates,
  how many are estimated, and anything left to review.

## Operator workflow (planning use)

Use this repeatable flow to turn the map into a planning aid.

1. **Select planning window**
   - Use year chips (`All`, `Latest`, `Last 5`) to set your decision horizon.
2. **Inspect species mix shifts**
   - Open charts and compare:
     - **Stacked by species** for composition
     - **Trend** for direction over time
     - **Spring vs Fall** for season balance
3. **Find understocked periods**
   - Watch the planning summary values:
     - YoY change and percent change
     - trend direction over the selected range
4. **Zoom to candidate lakes**
   - Use distance + species filters, then click a lake pin.
   - Chart focus switches to that single lake until reset.
5. **Check data confidence before decisions**
   - Run:
     ```bash
     python3 scripts/check_consistency.py
     ```
   - In the sidebar, check how many lakes are at verified coordinates. A lake
     shown as estimated is within about half a kilometre, which is fine for
     finding a lake but not for a specific pond in a city park.
   - Resolve unmatched/mismatch findings in the profiles CSV, re-run
     `merge_profiles.py`, then re-run the consistency checks.
