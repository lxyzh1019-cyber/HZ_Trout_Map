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
├── sw.js                           ← service worker: makes the map work offline
├── manifest.webmanifest            ← lets the map install as an app
├── icon.svg                        ← the app icon
├── vendor/                         ← Leaflet, MarkerCluster and Chart.js, checked in
├── js/                             ← scores, weather, sun/moon, the week bar and the lake panel
├── learn/                          ← the Learn room: 6 guides and the species pages
├── live/
│   └── advisories.json             ← what Alberta published today, collected daily
├── evidence.html                   ← the working shown, lake by lake
├── data/
│   ├── raw/                        ← inputs; see "What data/raw holds" below
│   ├── manifest.json               ← which years exist, and which are provisional
│   ├── lakes_YYYY.json             ← one file per year, generated
│   ├── lake_registry.json          ← one entry per physical lake, generated
│   ├── lake_depth.json             ← depth, summer layer and winterkill, generated
│   ├── lake_profile.json           ← facilities, description, photo count, generated
│   ├── lake_photos.json            ← photo links, generated, fetched on demand
│   ├── towns_ab.json               ← Alberta place names for town search, offline
│   ├── out_of_scope.csv            ← waters stocked with no trout, generated
│   ├── lake_regulations.json       ← seasons and catch limits per lake, generated
│   ├── lake_aliases.csv            ← your answers to past linking questions
│   ├── lake_facts.csv              ← your answers to past attribute questions
│   ├── aca_aeration_roster.csv     ← ACA's aerated-lakes roster, transcribed
│   ├── lake_facts_review.csv       ← attribute questions still open, generated
│   ├── link_review.csv             ← linking questions still open, generated
│   ├── regs_review.csv             ← lakes the guide could not be matched to
│   └── quality_summary.json        ← headline data-quality figures, generated
├── profiles/
│   └── mywildalberta_profiles.csv  ← coordinates, zone, amenities
├── scripts/
│   ├── ats.py                      ← land description → lat/lon
│   ├── sources.py                  ← reads every year's report, whatever its format
│   ├── registry.py                 ← lake identity and the matching rules
│   ├── build_history.py            ← the pipeline: raw reports → data/
│   ├── apply_review.py             ← turns your review answers into aliases
│   ├── import_stocking_map.py      ← the stocking-map workbook → CSVs in data/raw/
│   ├── profile.py                  ← facilities, prose and photos → lake_profile.json
│   ├── fetch_lake_pages.py         ← the same facts from the live site, one page at a time
│   ├── depth.py                    ← depth → summer layer and winterkill risk
│   ├── reconcile.py                ← the repo against Alberta, field by field
│   ├── regulations.py              ← seasons and limits out of the sportfishing guide
│   ├── strip_regulations.py        ← the published guide → only its regulatory pages
│   ├── advisories.py               ← closures and consumption advisories, daily
│   └── test_regression_checks.py   ← the test suite
└── README.md
```

Everything under `data/` except `raw/`, `lake_aliases.csv`, `lake_facts.csv`,
`aca_aeration_roster.csv`, `regs_aliases.csv` and the profiles CSV is generated. Never edit those by hand;
change the inputs and rebuild.

**`lake_registry.json` is a build artefact, not a store.** `build_history.py`
rebuilds it from the reports every run, so anything written into it directly is
gone by the next rebuild. Answers live in the input files above.

### What `data/raw/` holds

Two kinds of thing, and the difference matters:

**Documents as Alberta published them** — every year's stocking report, the
sportfishing guide, and the stocking-map workbook under `mywildalberta/`. These
arrive by hand and are never written by the build.

**One-time collector output, committed** — `mywildalberta_lakes.csv`,
`aca_aerated_lakes.csv`, `mywildalberta_photos.csv` and
`mywildalberta_issues.csv`. These are derived, but they are committed rather
than rebuilt, so a rebuild never has to reach the network and never depends on
a spreadsheet parser. Regenerate them with:

```bash
cd scripts && python3 import_stocking_map.py         # rewrite them
cd scripts && python3 import_stocking_map.py --check # confirm they still match
```

`--check` is also a test, so a workbook edited without a re-import fails CI the
same way hand-edited generated data would.

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

With the reviewed answers applied, **all 7,255 trout rows across sixteen years
are linked** and the review queue is empty.

Two housekeeping rules keep the registry honest:

- **A position given to two lakes is not verified.** The profiles CSV repeats
  one coordinate across five pairs. North and South Two Lake, both in Two Lakes
  Provincial Park near Grande Prairie, shared a single point although their
  land descriptions put them 3.4 km apart; Sibbald Lake carried Sibbald Meadows
  Pond's, 5.3 km from its own. Where a coordinate is shared, it stays with
  whichever lake's land description agrees and the others fall back to the grid.
- **A registry entry that no row resolves to is dropped.** Alberta has issued
  two waterbody ids for one water more than once — Magrath Children's Pond and
  East Stormwater Pond each had a twin holding nothing, which cluttered the
  review candidates and forced a disambiguating suffix onto a name with no real
  twin.

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

## When two lakes sit on one quarter section

Seven of this repo's 640 land descriptions are held by two lakes, and every one
is a pair the survey grid cannot separate: Upper and Lower Champion, Upper and
Lower Smuts, Pit 35 and Pit 45, MD Peace Pond #1 and #2.

For those seven, the land description is the **weakest** evidence there is. It
is the one field that is identical for both, and the name is all that can tell
them apart. Two rules follow:

**A recorded answer about one row is not a rule about its neighbour.**
`apply_review.py` records a confirmed answer as a land-description rule as well
as a name, because a land description is usually the stronger key — and for 633
of them it is. On a shared quarter section `link_all` now honours that rule only
when the row's own name does not contradict it. Without this, MD Peace Pond #1's
fish were credited to #2 for six years while #1 vanished from the map, and Lower
Champion Lake's went to Upper the same way.

**A surface area is never copied to a neighbour.** `attach_profiles` claims a
shared profile row for the lake whose name fits it best, and the area on that
row belongs to that lake — Alberta's stocking map confirms it for seven of the
eight shared rows. The neighbour reports nothing until its own area is filled
in, which is true, rather than borrowing hectares that are not its own.

Alberta's stocking map publishes 2021–2026 separately from the annual reports
this repo reads. The two agree on **2,028 of 2,030** lake-year-species totals.
The two that remain are the two publications disagreeing with each other about
individual stocking events, not this repo getting them wrong, and both are named
in the test suite rather than silently tolerated. Dates are deliberately not
compared: 64% of the map's events sit one day earlier than the reports', which
is a rendering difference and not a disagreement about what happened.


## Answering the attribute questions

`reconcile.py` compares what this repo holds against what Alberta publishes on
its stocking map, field by field, joined on Alberta's own waterbody id.

```bash
python3 scripts/reconcile.py          # writes data/lake_facts_review.csv
python3 scripts/reconcile.py --apply  # records the blanks in data/lake_facts.csv
python3 scripts/build_history.py      # and the rebuild keeps them
```

Three verdicts. **CONFIRM** where both agree — 1,096 of them, which is the main
result: two independently produced sources describing the same lakes.
**FILL** where the repo has nothing and Alberta publishes a value. **DISAGREE**
where both have a value and they differ, which is never resolved automatically.

Each answer in `data/lake_facts.csv` says which kind it is:

| `decision` | who writes it | what it does |
| --- | --- | --- |
| `fill` | `--apply` | applies only while the repo still has nothing there |
| `settled` | you | two sources disagreed, you picked one, and it wins |
| `keep` | you | you compared them and kept what the repo had; nothing is written |

`--apply` writes `fill` and nothing else, so nothing can start overriding the
pipeline on its own. It filled 34 fishing zones, 34 surface areas, and
Alberta's own id for eight lakes this repo had minted from a land description.

A `settled` or `keep` row also stops `reconcile.py` raising that question
again. A disagreement is a question, not a defect, and re-asking one that has
been answered teaches people to ignore the file.

### The four that were settled

- **Emerald Lake (Hart Lake)** — `keep`. The map's row for id 4532 publishes no
  land description, the wrong district and no stocking history, and the survey
  grid puts this repo's position 0.37 km away against the map's 527 km. The
  map carries the Whitecourt lake separately as 6821.
- **Lloydminster Trout Pond** — `settled`, and the repo lost. Both sources
  publish the same land description, `SE6-50-1-W4`, and the survey grid sits
  0.99 km from the map's position and **6.49 km from the hand-verified profile
  pair**. A profile row that contradicts its own land description by six
  kilometres is not verification. This is the one lake whose `coord_source` is
  `mywildalberta`.
- **Upper Kananaskis Lake** — `keep`. 1.19 km apart, but the map gives
  `50.625, -115.15` to three and two decimal places against the repo's six, and
  the lake is 846 ha. Both positions are on the water; one of them is precise.
- **Champion Lakes** — `settled`. The profile and the map disagree on *both*
  halves (profile 8.0 / 4.0, map 4.0 / 0.4), and the profile's Upper equals the
  map's Lower, so one of the two has the pair crossed. The map agrees with the
  profile exactly on the other four shared-quarter-section pairs, so the pair is
  taken from the map. Which source is crossed is still unknown — what is now
  fixed is that the published pair came from *one* source. It previously held
  Lower from the profile and Upper from the map, a combination no source
  anywhere states.

### Alberta's id for a lake the reports never numbered

Thirteen lakes come from reports that print a land description and no waterbody
id, so the exact id join the rest of the pipeline relies on cannot see them —
which is why they had no depth even where Alberta publishes one. Eight are
recoverable from the stocking map, and the recovery needs two independent
fields to agree:

1. the land description must identify **exactly one lake on each side** — seven
   of this repo's codes are shared by two lakes and five of the map's are, so a
   code that is not unique both ways proves nothing; and
2. the name must match. Watridge Lake is why that is not optional: the map
   publishes a position for it 140 km from this very land description.

All eight score 0.95 or better on the name. The result is stored as
`published_waterbody_id`, deliberately **not** as `waterbody_id`: `lake_id` is
minted as `wb` + the waterbody id wherever the reports give one, so writing it
into that field would either contradict the `lake_id` or force `lk0006` to
become `wb417506`, breaking every `?lake=` link and every answer already
recorded against the old id. It is a join key and nothing more.


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
| `mywildalberta` | Filled from the stocking map where the repo had no position | on the lake |

A published position that contradicts its own land description is discarded
rather than passed on. Watridge Lake's row on the stocking map places it 140 km
from the quarter section printed beside it and from the district printed beside
that — one digit of the longitude, and the repo's own coordinate agrees with the
land description exactly. Every other lake sits within 2.2 km of its own
quarter section, which is what the survey grid predicts, so the rule refuses
one row and keeps the other 340. The refusal is written to
`data/raw/mywildalberta_issues.csv` with the distance, so nobody has to take it
on trust.

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

## How deep each lake is

Alberta publishes a depth for some of its stocked lakes and not for others.
Where it does, two pieces of advice follow; where it does not, the map says
nothing at all rather than estimating, because sending someone to fish eight
metres down in three metres of water is a real harm.

| | lakes |
| --- | --- |
| a maximum depth is published | 109 |
| an average depth is published | 54 |
| an average depth is estimated from the maximum | 59 |
| deep enough to form a summer layer | 83 |
| the province aerates it | 24 |
| nothing is published, so nothing is shown | the rest |

**The summer layer.** Below about 5 m an Alberta lake stays mixed all summer and
a hot surface reading describes the water the trout are actually in. Above it
the lake separates and they sit under the warm top. The band is set by how far
the wind can blow across the water — surface area is the usable stand-in — and
not by a fraction of the maximum depth, which would put a deep lake's
thermocline shallower than it belongs.

**Winterkill.** A risk band with its inputs named, not a prediction. Depth and
aeration are real inputs. Eutrophy is not available at all. Ice duration is
deliberately not modelled: across these lakes it varies far less than depth
does, so it would add arithmetic without adding discrimination. The app names
what was not counted.

**Two sources, and neither is the whole truth.** Alberta's own lake pages name
twelve aerated lakes. ACA's published Lake Aeration Program roster names
twenty-two, and the lists only partly overlap: Camp 9 Trout Pond and Salter's
Lake are stated by Alberta and absent from ACA's, which is what a fish-and-game
club windmill outside the province's programme looks like. Both are kept.

The roster is transcribed by hand into `data/aca_aeration_roster.csv`, which is
an input like `data/lake_aliases.csv` and never generated. It is keyed on
`lake_id` and not on name, because Swan, Spring and Birch Lake are each one of
several in Alberta and a name alone would aerate the wrong water. Swan Lake is
the case that proves it — the roster says only "Swan Lake", and ACA places it
42 km west of Valleyview, which settles which one.

**Aeration is known one lake at a time.** Alberta names the lakes it aerates and
says nothing whatsoever about the rest, so absence from that list is not a
statement that a lake is unaerated — the stocking map's own notes say so in
those words. A lake off the list therefore reads "not counting whether it is
aerated", never "not on the aerated list".

Aeration cuts both ways and the app says both halves: a lake is aerated because
the province expects it to winterkill, and is less likely to winterkill because
it is aerated.

**A photograph is not enough.** Castaway Trout Pond and Lara Fish Pond show a
windmill aerator in a picture and say nothing about it in prose. That evidence
is recorded and shown, and never lowers a risk band: a photograph shows that
equipment existed when it was taken, not that the programme runs now, and the
export's own notes say the operating status was never verified. Marking a lake
aerated makes it read as safer than it is, which is the one direction worth
being careful in.

**A contradiction is refused, not repaired.** Castor Eastside Trout Pond
publishes a mean depth of 22 m against a maximum of 7 m on a one-hectare pond.
The maximum is kept and the mean is dropped. Swapping them would not be a
repair, only a different guess, and a pond that size is neither.

**Five lakes publish an average depth and no maximum.** The average is shown,
because it is a fact. It unlocks nothing: both the summer layer and the
winterkill band are set by how deep a lake *gets*, not how deep it is on
average, so neither appears for those five. The ratio is not inverted to guess
a maximum either — the inverse is worse in the tail, and the maximum is the
number that decides whether to fish eight metres down, where over-estimating is
the harmful direction.

### The one estimated number in the repo

Where Alberta publishes a maximum depth and no average, the average is shown as
a **band**, never as a figure, and the band is a restatement of Alberta's own
published pairs rather than a model of anything.

Fifty-five lakes publish both depths. Across them the average runs between
**0.39 and 0.97 of the maximum** (median 0.64), and a band drawn at those outer
percentiles contains **78%** of them. Held out one lake at a time, the median
ratio misses the true average by **25%**, and by 70% for the worst tenth.

So the band is wide — a 7 m lake reads "probably 2.7–6.8 m" — and the width is
the honest part. It is on its own line in the popup, in italics, with the word
*estimated* beside the number rather than in a footnote, so it can never be
read as equally firm by glancing along a line.

Three rules hold it in place, each with a test:

- **It is never stored where a measurement is stored.** A published average is
  `{"m": 4.0}`; an estimated one is `{"range_m": [2.7, 6.8]}`. Reading one field
  is enough to know which kind it is.
- **It never changes the advice.** `stratification()` and `winterkill()` take
  the measured maximum and nothing else — they cannot see an average at all.
  Every lake an estimate could serve already has a measured maximum, so an
  estimate could only ever *alter* advice that already exists, never extend it
  to a lake that had none. Zero upside, in the one place where being wrong puts
  someone in eight metres of water.
- **The band cannot reach the bottom.** A lake whose average depth equals its
  maximum has vertical sides.

Splitting the ratio at 6 m does measurably better — 20% median error against
25%, and 82% coverage against 78% — but the 6 m threshold was chosen by eye
from these same 55 lakes and one side of it holds only 20 of them. That is
fitting the split to the sample, so it is recorded here and not used.

**A maximum depth is never estimated.** The only thing available to predict it
from is surface area, and across the 114 lakes publishing both, the log-log
correlation is 0.23. That is noise. The 225 lakes with no depth at all keep
showing nothing.


## What Alberta says about the place

Beyond how deep a lake is and what swims in it, Alberta publishes facilities, a
paragraph of its own about each lake, and photographs.

| | lakes |
| --- | --- |
| facilities stated | 210 |
| a description | 305 |
| photographs (662 of them) | 184 |
| **state no facilities at all** | **135** |

**Absence is not absence.** That last row is the important one. A lake with a
blank amenities cell is Alberta not saying, which is not a lake with no toilet.
Those lakes are stored as `null` rather than an empty list so the app can tell
the two apart, every filter count reads *"lakes known to have"*, and the panel
says how many lakes are being left out for want of a statement rather than for
want of a boat launch.

**Facilities roll up.** The published vocabulary is hierarchical — `Trails
Hiking` and `Trails Cross-Country Ski` are both `Trails`, `Paddling Canoe` is
`Paddling` — so a filter for Trails matches a lake that only says Trails
Hiking. The rollup happens at build time in `scripts/profile.py`, not in the
browser, for the same reason the regulations are matched at build time.

Only parents and standalone tokens are offered as filters. After the rollup a
child is redundant: every lake with Paddling Canoe also has Paddling, so the two
have identical counts and offering both is offering one filter twice under two
names. That leaves **15 facets**, each covering at least 15 lakes, ordered by
what decides a fishing trip rather than by count — `Day Use` covers 116 lakes
and settles nothing.

Two vocabularies describe the same lakes: the controlled token list above, and
hand-written prose in the profiles CSV (*"Day use, camping on site, boat launch,
pit toilets."*). They are **not** merged — one is a list and the other is
English, and reconciling them would be guesswork. Chips where there are tokens,
the sentence where there are not.

### The photographs stay on Alberta's server

They are linked, never copied. Three consequences, all deliberate:

- They load **only when someone opens the panel**, so browsing the map never
  tells a government server which lakes you looked at.
- Every request carries **no referrer**, so opening the panel does not announce
  where it was opened from.
- They **cannot work offline**. The service worker only handles this app's own
  origin, and caching a few hundred photographs would evict the map tiles that
  make the app useful at the lake. So `data/lake_photos.json` is deliberately
  *not* precached — a test names it as the one exception and fails if any other
  data file the page fetches is left uncached. The photo *count* lives in the
  profile file, which is cached, so a lake still says how many there are with no
  signal, and a picture that fails to load is replaced by its caption as a link.

### One lake panel

Since Build 1b a lake opens in one panel — sliding up on a phone, in the right
column on a PC — instead of a pin popup, a conditions panel and a photos panel
fighting for the same corner. It opens on what decides the trip: the bait ban,
the verdict line (how recently stocked, whether the season is open, the
winterkill risk), the best day this week and why. The forecast, the fish, the
lake, the rules and the way there follow in sections that fold open, and the
description and photographs sit inside "Lake info", so they never push the
catch limits out of reach.

## Walleye and pike waters

Waters Alberta stocks with walleye or pike and no trout are shown on the map,
not hidden: 35 of them in the data (Sylvan, Lake Newell, McGregor, Travers,
Pinehurst, Winagami and more). Walleye, northern pike and Arctic grayling each
have their own pin colour and letter, picked to stay apart from the six trout
under normal vision and the three common colour-vision deficiencies.
`data/out_of_scope.csv` is kept with its header only: no stocked water is left
out for its species. A test fails if the number above and the data disagree.


## Tests

```bash
cd scripts && python3 -m unittest discover -p "test_*.py"
```

Covers the survey-grid conversion and its accuracy, the name-matching rules,
every year's reader (including the specific parsing failures that once welded
a district onto a lake name and a fish strain into another), the linker's
held-out accuracy, the committed data itself, and the stocking-map import —
that the CSVs still match the workbook, that "Unknown" never becomes zero, that
a position contradicting its own land description is not published, and that a
lake Alberta says nothing about is never reported as unaerated.

It also checks that two lakes on one quarter section keep their own fish and
their own surface area, that the published totals still agree with Alberta's
stocking map, and that an answer you record survives the next rebuild.

GitHub Actions runs the same suite on every pull request, on every push to
`main` and on a manual run, and additionally rebuilds
`data/` from the raw reports, failing if the result differs from what is
committed. Generated data can therefore never drift from its sources.

## Running locally

The map fetches JSON over HTTP, so opening `index.html` from disk will not work.
Offline support is skipped on a `file://` page for the same reason.

```bash
python3 -m http.server 8000    # from the project root
# open http://localhost:8000
```

On GitHub Pages it works natively.

## Features

Built around one question: where should I fish, and has anything been put in
there lately.

**Which lake, which day**
- A week bar over the map. Tap a day and every pin shows that day's Bite score.
  On a phone a "Best near you" card lists the top three; on a PC the right-hand
  column lists them all, with Near me, Saved, Area and Clear.
- Two scores. **Bite** is whether the fish will feed: light 40, water
  temperature 35, pressure trend 15, wind 6, rain 4, with the moon as a
  multiplier capped at 5%. Gusts are never in it. **Day out** is whether you
  want to be on the water: wind plus half the gust spread, made larger on a
  big lake (over 200 ha, ×1.3) and smaller on a pond (under 10 ha, ×0.7), rain
  amount and chance, and air temperature. A lake with no published area is
  treated as medium and says "size unknown".
- Each lake's best day: the highest Bite on a day with gusts under 40 km/h and
  a Day out of Fair or better. Gusty days are named "not a boat day".
- "Why this score" shows the parts that add up to the number, and compares
  with the nearest lake that has a different forecast spot or size.
- Gold pins: *Best this week* colours each lake by its best day.
- Forecast tabs for wind, weather, barometer and solunar times, over 3 or 7
  days, as lines or a grid, with today's feeding times and the moon phase.
- Winter: when most lakes on screen have had a frozen week, the week bar shows
  wind chill, pins show the legal ice season, and lakes say "Ice likely".
- Tags: low harvest limit, trophy size rule (in the guide's words),
  popularity estimate (Angler's Atlas reports, labelled an estimate).

**Finding a lake**
- Search lakes and towns. The saved Alberta town list answers first and works
  with no signal; online, Open-Meteo place search adds more Canadian places.
  Picking a town lists the lakes near it and measures from it, without moving
  home.
- Pins group together when zoomed out and separate as you zoom in, so the
  Kananaskis and Pierre Greys clusters stop being one unreadable blob.
- Hover a pin for the name, distance, fish in view and last stocking date.
- Zoom to fit whatever the current filters leave on the map.

**Filters**
- **Stocked recently** — 30, 60, 90 days, or this season. Each option shows how
  many lakes it would find, and the panel states the newest stocking on record,
  so an empty window is never a mystery.
- **Species** — nine: rainbow, brook, brown, tiger and cutthroat trout,
  westslope cutthroat (reported separately since 2023), walleye, northern pike
  and Arctic grayling.
- **Fish size** — fry under 15 cm, 15 to 20 cm, and catchable 20 cm and over.
  A lake given 60,000 fry is not the same prospect as one given 3,000 catchable
  trout.
- **Distance from home**, where home is yours to set: use your location, pick a
  point on the map, drag the marker, or go back to Red Deer. It is remembered
  between visits.
- **Years** — 2011 to 2026, with All / None / Last 5 / Latest. A year marked
  `*` is still in progress.
- **Season and ice** — *Open today*; *Open for ice fishing*, which keeps lakes
  with any legal ice season: open all winter (every day from Dec. 15 to Mar. 1,
  such as open all year or "May 15 to Mar. 31"), early ice (open until Nov. 30)
  or late ice (open from Apr. 1); *Aerated*; and *Bait ban*, which keeps only
  lakes the regulations put under a bait ban. A lake not matched to the
  regulations is never hidden by a season or ice filter.

**Aeration and thin ice**
- Every lake stated as aerated — ACA's roster or Alberta's own lake page — shows
  an *Aerated* badge, with or without a known depth.
- From October to April the badge carries ACA's warning: thin ice and open
  water near the aerators; stay behind the fence and the danger signs.
- `data/aca_aeration_roster.csv` records ACA's *Winter Angling* Yes/No. The map
  uses the regulations, and a test fails if ACA's column ever disagrees.
- Every lake panel has an *Ice season* line — all winter, early ice only, late
  ice only, early and late ice, or closed — with "Legal is not safe. Ice
  thickness is never forecast."
- A lake under a bait ban shows a red *Bait ban* line at the top of its panel.
- When every day of the past 7 days had a mean air temperature below freezing,
  the lake panel shows *Ice likely* and no open-water score.

**Reading the history**
- Charts: by species, by season, per-species trend, and a stocking calendar
  that folds every selected year into one twelve-month view, so you can see
  which weeks a lake is usually stocked.
- Seasons are Spring (Mar–Jun), Summer (Jul–Aug) and Fall (Sep–Nov).
- Planning summary with year-over-year totals, direction, and the lakes that
  moved most. A provisional year is labelled, so a partial report does not read
  as a collapse in stocking.
- Open a lake to scope every chart to that lake.

**Seeing the shape of it**
- **Pin colour** is the Bite score on the picked day, the best day this week,
  the main species, or year-over-year change: how the
  latest selected year compares with the one before it, on a diverging scale
  where orange is down and purple is up. Change needs two selected years, and
  says so rather than colouring everything "about the same".
- **Zone view** ranks Alberta's ten fish management zones by fish stocked, with
  a bubble at the centre of each zone's stocked lakes. Alberta does not publish
  zone outlines here, so a bubble marks where a zone's lakes are, not how far
  the zone reaches — the map says so rather than drawing an invented boundary.

**Taking it with you**
- List view, sortable on any column, with Bite and Day out for the picked day
  and a CSV download.
- Google Maps and Apple Maps directions to any lake, in the lake panel, and
  Google Maps in the list. Google gives the road distance and time, which is what matters:
  the straight line this app measures understates most of these drives.
- Favourites, saved in your browser, and a one-click multi-stop driving route
  from home through all of them.
- Every filter and your home location live in the URL, so a link reproduces
  exactly what you are looking at. `?lake=wb6051` opens one lake directly, and
  each lake panel has a button that copies its own link.
- **Works with no signal.** On first visit the map caches itself, the
  libraries, all sixteen years of data and the basemap tiles you have looked
  at, so it still opens at the lake. It says when it is offline, and offers a
  reload when a newer version has been fetched. It can be installed as an app.
- Works at phone width, with the filters in a slide-over panel.
- Forecasts for every lake are fetched in one go — about 250 forecast spots,
  50 per request, inside Open-Meteo's free limit of 600 calls a minute and
  10,000 a day — and saved on the device for 3 hours.
- A Learn room: how the scores work, winterkill and aeration, ice safety,
  reading the barometer, what stocked sizes mean, telling the trout apart, and
  a page for each species.

**Honesty about the data**
- The lake panel says when a position is estimated from the land description
  rather than verified.
- The data quality panel reports how many lakes sit at verified coordinates,
  how many cannot be placed at all, and how much of the sixteen-year history
  linked without a human.

## Licences and credits

- **Town list** (`data/towns_ab.json`): Natural Resources Canada, Canadian
  Geographical Names Database. Contains information licensed under the Open
  Government Licence – Canada
  (https://open.canada.ca/en/open-government-licence-canada). Rebuild it with
  `python -I scripts/towns.py <cgn_ab_csv_eng.zip>`; the source and date are in
  `data/towns_ab.provenance.json`.
- **Weather**: weather data by Open-Meteo.com, CC BY 4.0.
- **Place search online**: Open-Meteo geocoding, built on GeoNames, CC BY 4.0.
- **Satellite map**: Imagery © Esri, Maxar, Earthstar Geographics and the GIS
  User Community.
- **Species photos** (`vendor/species/`), from Wikimedia Commons, free licences
  only; each species page names the author and licence and links the file page:
  - RNTR: Harka, Akos, CC BY 3.0 — https://commons.wikimedia.org/wiki/File:Oncorhynchus_mykiss_Hungary.jpg
  - BKTR: Engbretson, Eric, Public domain — https://commons.wikimedia.org/wiki/File:Salvelinus_fontinalis.jpg
  - BNTR: USFWS Mountain Prairie, Public domain — https://commons.wikimedia.org/wiki/File:Brown_Trout_(Salmo_trutta).jpg
  - TGTR: U.S. Department of Agriculture, Public domain — https://commons.wikimedia.org/wiki/File:Swimming_Tiger_Trout.jpg
  - CTTR: USFWS - Pacific Region, Public domain — https://commons.wikimedia.org/wiki/File:Cutthroat_trout,_western_Washington_(53815470250).jpg
  - WSCT: Craig D. Young, Public domain — https://commons.wikimedia.org/wiki/File:Wscutt.jpg
  - WALL: USFWS Mountain Prairie, Public domain — https://commons.wikimedia.org/wiki/File:Walleye_(Sander_vitreus).jpg
  - NRPK: Arnstein Rønning, CC BY-SA 4.0 — https://commons.wikimedia.org/wiki/File:Esox_lucius_(no).JPG
  - ARGR: U.S. Fish and Wildlife Service, Public domain — https://commons.wikimedia.org/wiki/File:Arctic_grayling_showing_iridescent_dorsal_fin.jpg

## Accessibility note

Species colours come from a validated categorical palette, ordered so every
neighbouring pair stays separable for colour-blind readers. The previous
naturalistic set put brown trout and brook trout 2.0 ΔE apart under
protanopia, which is indistinguishable. Six categories still cannot be made
safe on colour alone, so each pin also carries the species initial and every
popup names the species in words.
