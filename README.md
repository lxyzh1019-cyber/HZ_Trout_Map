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
├── data/
│   ├── manifest.json               ← which years are available
│   ├── lakes_2025.json             ← one file per year
│   └── lakes_YYYY.json
├── profiles/
│   └── mywildalberta_profiles.csv  ← zone/amenities/coord overrides
├── scripts/
│   ├── extract_alberta_trout_v2.py ← PDF → lakes_YYYY.json
│   ├── merge_profiles.py           ← enrich a year's JSON with profile data
│   └── check_consistency.py        ← report mismatches across years
└── README.md
```

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
```

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
- **Popups** — per-lake stocking history, zone link, amenities, Google
  Maps link. Reflects current filters.
