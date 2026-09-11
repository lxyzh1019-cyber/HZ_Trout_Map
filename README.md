# Alberta Trout Stocking Map

Interactive map of Alberta's annual trout stocking reports, 2011 to 2026,
with filterable species, distance, year selection, and charts showing stocking
trends.

Hosted via GitHub Pages: push to `main` and the map is live at
`https://<your-username>.github.io/<repo-name>/`.

## Folder structure

```
alberta-trout-map/
├── index.html                      ← the map (open in browser)
├── vendor/                         ← Leaflet 1.9.4 + Chart.js 4.4.0, checked in
├── data/
│   ├── raw/                        ← the reports as published (PDF, CSV, XLSX)
│   ├── manifest.json               ← which years exist, and which are provisional
│   ├── lakes_YYYY.json             ← one file per year, generated
│   ├── lake_registry.json          ← one entry per physical lake, generated
│   ├── lake_aliases.csv            ← your answers to past linking questions
│   ├── link_review.csv             ← linking questions still open, generated
│   └── quality_summary.json        ← headline data-quality figures, generated
├── profiles/
│   └── mywildalberta_profiles.csv  ← coordinates, zone, amenities
├── scripts/
│   ├── ats.py                      ← land description → lat/lon
│   ├── sources.py                  ← reads every year's report, whatever its format
│   ├── registry.py                 ← lake identity and the matching rules
│   ├── build_history.py            ← the pipeline: raw reports → data/
│   ├── apply_review.py             ← turns your review answers into aliases
│   └── test_regression_checks.py   ← the test suite
└── README.md
```

Everything under `data/` except `raw/`, `lake_aliases.csv` and the profiles CSV
is generated. Never edit those by hand; change the inputs and rebuild.

The map libraries are committed under `vendor/` rather than loaded from a CDN,
so the map keeps working offline and cannot break when a CDN is unreachable.

## Rebuilding everything

```bash
pip install pdfplumber openpyxl
cd scripts
python3 build_history.py
```

That reads all sixteen reports, links every row to a lake, and rewrites the
year files, the registry, the manifest and the quality summary. It takes about
fifteen seconds and is idempotent: running it twice produces identical files.

## Adding a new year

1. Drop the report into `data/raw/`.
2. Add a line to `YEAR_SOURCES` in `scripts/sources.py` naming the file and
   which reader it needs. If the year is still in progress, add it to
   `PROVISIONAL_YEARS` too.
3. Run `python3 build_history.py`.
4. Answer anything that lands in `data/link_review.csv` (see below).

## The four report formats

Alberta has changed this report's layout repeatedly, and for some years the
machine-readable file is only a partial snapshot. `sources.py` picks the best
source per year, decided by comparing row counts:

| Years | Source used | Why |
| --- | --- | --- |
| 2011 | PDF | No spreadsheet exists. Month only, and the land description omits the quarter-section. |
| 2012–2014 | CSV | Carries Alberta's waterbody id, coordinates and an exact date. |
| 2015 | PDF | The CSV holds 79 rows against 304 in the PDF. |
| 2016–2019 | CSV | Those PDFs carry no land description at all, only a district and a name. |
| 2020 | CSV | Coordinates and land description, comparable to the PDF. |
| 2021–2024 | XLSX | Comparable to the PDF and already tabular. |
| 2025 | PDF | The spreadsheet holds 279 rows against 591 in the PDF, and undercounts Payne Lake alone by 130,000 fish. |
| 2026 | PDF | Current season, so the figures are provisional. |

## How years are linked

The hard part is knowing that a row in one year is the same lake as a row in
another. Names drift, and land descriptions get mistyped: of the 340 lakes
Alberta tracked with its own waterbody id between 2012 and 2019, 58 carry more
than one land description across those years.

So no single field is trusted. Each row is resolved against the registry using
whatever evidence it has, strongest first:

1. **Alberta's waterbody id** — present 2012 to 2019, and decisive.
2. **An exact land description.**
3. **A land description without the quarter letter** — all 2011 to 2013 gives.
4. **A name already confirmed for that lake**, including every past review answer.
5. **Position, with the name as tiebreaker** — lakes are far apart, so a
   position is nearly unique. The median lake has no neighbour within 12 km.
6. **Name alone**, for 2015, which publishes nothing else.

Two guards stop the failure that quietly corrupts a history — a lake absorbed
into its neighbour:

- **Confusable clusters.** Lakes that sit close together *and* have similar
  names (Burstall Upper and Lower, the Pierre Greys chain, Pit 35/44/45) are
  never linked by similarity. Only an exact id or land description will do.
- **Distinguishing words.** If one name says "Upper" and the other says
  "Lower", they are not the same water however alike the rest of the string
  looks. Upper and Lower Champion Lake share a land description, so without
  this they merge.

Measured on held-out real years — the registry built from 2012 to 2016, then
2017 to 2019 linked with Alberta's id and coordinates hidden, leaving only what
2021 onward gives us — the result is **1,237 correct, 0 wrong, 15 sent for
review**, and none of the 32 rows for lakes absent from the registry were
absorbed into another. `test_regression_checks.py` fails the build if a single
wrong link ever appears.

## Answering the linking questions

Anything the rules will not guess at goes to `data/link_review.csv` rather than
being decided silently.

```bash
cd scripts
python3 apply_review.py --list     # see what is open
# edit data/link_review.csv: put a lake_id, or NEW, or SKIP, in each row
python3 apply_review.py            # record the answers
python3 build_history.py           # rebuild; those rows now resolve themselves
```

Each answer is written to `data/lake_aliases.csv` and applied on every future
build, including future years. A name Alberta keeps misspelling is settled once
and stays settled, so the list shrinks every year instead of repeating.

## Where lake coordinates come from

The report never prints a latitude or longitude. It prints a land description
such as `SW4-36-8-W5`, naming a quarter-section: an 800 m square on the survey
grid. Every pin is positioned from one of three sources, recorded per lake in
`coord_source`:

| `coord_source` | Where it comes from | Typical accuracy |
| --- | --- | --- |
| `profile` | `lat`/`lon` in the profiles CSV, verified by hand | on the lake |
| `alberta` | Coordinates Alberta published in the 2012–2020 files | on the lake |
| `ats` | Computed from the land description by `ats.py` | ~0.5 km |

To correct a single lake, add `override_lat` and `override_lon` columns to
`profiles/mywildalberta_profiles.csv`, fill them in for that row, and rebuild.
An override always wins, so the correction survives every later refresh.

The `html_lat`/`html_lon` columns are deliberately ignored. They are not an
independent observation: for 249 of 265 rows they reproduce an old, buggy grid
calculation to within 50 m, which used to place every pin a median 6 km from
the water.

**How we know the coordinates are right.** The hand-verified `lat`/`lon` column
and the report's land descriptions are two independently produced sources.
Converted correctly they agree to a median of 0.53 km, with 252 of 256 lakes
inside 1.5 km — about the width of a quarter-section. The test suite fails if
that median ever rises above 1 km.

## Tests

```bash
cd scripts && python3 -m unittest discover -p "test_*.py"
```

Covers the survey-grid conversion and its accuracy, the name-matching rules,
every year's reader (including the specific parsing failures that once welded
a district onto a lake name and a fish strain into another), the linker's
held-out accuracy, and the committed data itself.

GitHub Actions runs the same suite on every push and additionally rebuilds
`data/` from the raw reports, failing if the result differs from what is
committed. Generated data can therefore never drift from its sources.

## Running locally

The map fetches JSON over HTTP, so opening `index.html` from disk will not work.

```bash
python3 -m http.server 8000    # from the project root
# open http://localhost:8000
```

On GitHub Pages it works natively.

## Features

- **Species filter** — six species, including westslope cutthroat, which
  Alberta began reporting separately in 2023.
- **Distance slider** — hide lakes beyond N km from Red Deer.
- **Year chips** — 2011 to 2026. Shortcuts: All / None / Last 5 / Latest.
  A year marked `*` is still in progress.
- **Charts** — stacked by species, spring versus fall, and per-species trend.
- **Basemap toggle** — topographic or street.
- **Popups** — per-lake stocking history, zone link, surface area, amenities,
  Google Maps link. Reflects current filters and stays open while you change
  them. Dates from 2011 to 2013 show a month only, because that is all those
  reports give.
- **Planning summary** — year-over-year totals and trend direction.
- **Data quality indicator** — how many lakes sit at verified coordinates and
  how much of the history linked without a human.
