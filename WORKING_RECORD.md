# WORKING RECORD — HZ_Trout_Map — rules v2

Single working record for this repository. Updated by the main session at the end of every implementation turn (the record guard hook checks this). Keep it terse; history lives in git.

## Approved baseline
- Plan v1 approved 2026-10-11 (D20): Build 1a (aeration, ice season, bait ban, known fixes) in chat; Build 1b (forecast, two scores, layout) prototyped in chat, built in Claude Code; Build 2 (estimates, elevation, hot spots, winter view) same Claude Code session; Build 3 (Firebase sync, email alert) later.
- Build 1a merged 2026-10-16 (PR #15), live.
- Build 1b prototype picked by the owner 2026-10-29: design/build-1b-prototype.html (PR #17), for feature reference only.
- Plan "Build 1b and Build 2" Rev 2 approved 2026-10-29: decisions 1–15 at option A.

## Design decisions
- [agreed] Filters stay in a Filters panel (left on a wide PC, slide-over below) — search: Filters panel
- [agreed] Town list from NRCan CGNDB, Open Government Licence – Canada, with credit — search: towns_ab
- [agreed] Species photos from Wikimedia Commons, free licences only, credited — search: vendor/species
- [agreed] Satellite basemap is Esri World Imagery with credit — search: basemaps.sat
- [agreed] Score bands unchanged (Fair from 42) — search: BAND
- [agreed] Popularity = largest Anglers Atlas agree count, labelled estimate — search: popularity
- [agreed] BC Trout Finder table remade from the request ledger — search: BC Trout Finder
- [agreed] Day out: size ×0.7 under 10 ha, ×1.0 medium, ×1.3 over 200 ha; rain > 60% or > 2 mm and air < 5 °C or > 28 °C lower it — search: dayOut
- [agreed] Pictures and questions first, PR opens ready after the answers — search: side-by-side
- [agreed] A picked town moves the distance filter origin, never home — search: setOrigin
- [agreed] Charts button in the header — search: chart-toggle
- [agreed] Separate Conditions panel and popup button nudge removed — search: intentionally removed
- [agreed] Colour-blind-safe score scale grey, blue, light blue, gold, with numbers — search: SCORE_PIN
- [agreed] Winter week bar when more than half the lakes on screen have the guard on — search: winterOn

## Pending
- Build 1b: comparison of prototype and build sent to the owner; PR opens after the answers — 2026-10-30.
- Build 2: starts on a new branch from main after the owner merges Build 1b.

## Request ledger
| # | Round/date | Requirement (user's words, short) | Status | Note |
|---|---|---|---|---|
| A1 | 10-11 | Aerated badge on all 24 stated-aerated lakes | done | 1a, PR #15 |
| A2 | 10-11 | Thin-ice warning Oct–Apr | done | 1a |
| A3 | 10-11 | Aerated filter chip | done | 1a |
| A4 | 10-11 | Open for ice fishing chip: all winter + early ice + late ice (303) | done | 1a |
| A5 | 10-11 | Ice season line in every popup | done | 1a |
| A6 | 10-11 | "Legal is not safe. Ice thickness is never forecast." | done | 1a |
| A7 | 10-11 | ACA Winter Angling column + test vs regulations | done | 1a |
| A8 | 10-11 | Spring Lake land-location note, link kept | done | 1a |
| A9 | 10-11 | Split-season reader fix (K1) | done | 1a |
| A10 | 10-11 | Filter group named "Season and ice" | done | 1a |
| A11 | 10-11 | Regulations stay the only legal source | done | 1a |
| B1 | 10-11 | Bait ban stated clearly in the popup | done | 1a; red line changed to filled red badge by owner 10-16 |
| B2 | 10-11 | Bait ban filter chip | done | 1a |
| B3 | 10-11 | Low harvest limit tag (trout limit 0–2, 54 lakes) | done | 1b; 54 lakes, test_tags_come_from_the_regulations_and_the_atlas |
| B4 | 10-11 | Trophy size-rule tag | done | 1b; 24 lakes, test_tags_come_from_the_regulations_and_the_atlas |
| B5 | 10-11 | Popularity estimate from Anglers Atlas report count, labelled estimate | done | 1b; largest agree count, labelled estimate (decision 6) |
| B6 | 10-11 | Stocked size + date instead of typical size; no growth guess | done | 1b; panel Fish and stocking |
| B7 | 10-11 | Links to Alberta licence and rules pages | done | 1b; albertaregulations.ca + mywildalberta.ca (alberta.ca pages 404) |
| C1 | 10-11 | Keep Bite score and its weights; do not copy BC weights | done | exists |
| C2 | 10-11 | Gusts stay out of the Bite score; warning at 40 km/h | done | exists |
| C3 | 10-11 | Day out score: wind + half gust spread scaled by lake size; rain amount + chance; air temp | done | 1b; Conditions.dayOut, decision 9 |
| C4 | 10-11 | Best-day banner: day name, 7 bars, Best/Good/Fair/Poor | done | 1b; lake-sheet banner + bars |
| C5 | 10-11 | Banner uses both scores (bite + boat day) | done | 1b; bestDay needs Day out ≥ Fair |
| C6 | 10-11 | Best day skips gusty days and says gusty | done | 1b; gust ≥ 40 km/h → not a boat day |
| C7 | 10-11 | Favourites ranked by best day | done | 1b; Saved list |
| C8 | 10-11 | Gold pins: Best this week colour mode | done | 1b; cm=best; H4 measured |
| C9 | 10-11 | Score column in list view | done | 1b; Bite + Day out columns, CSV |
| C10 | 10-11 | Line chart for wind, gusts, rain | done | 1b; Forecast Wind tab, 40 km/h line |
| C11 | 10-11 | Grid / Lines toggle | done | 1b |
| C12 | 10-11 | Forecast tabs Wind/Weather/Barometer/Solunar + 3/7-day switch | done | 1b |
| C13 | 10-11 | Today's feeding windows: major/minor clock times + moon phase | done | 1b; Astro.periods |
| C14 | 10-11 | Plain-language daily tip from own data, no outside service | done | 1b; Conditions.dailyTip |
| C15 | 10-11 | Clearing reminder (sun breaking through), labelled anglers' reports, not scored | done | 1b; Conditions.clearingHint, not in score |
| C16 | 10-11 | Winter guard: hide open-water score when frozen (K9) | done | moved to 1a by D22 |
| C17 | 10-11 | Winter score: light, pressure, moon + cold/wind-chill comfort note | open | Build 2 |
| C18 | 10-11 | Elevation from weather service, for ice and water temperature only | open | Build 2 |
| D1 | 10-11 | Near me one-tap list | done | 1b |
| D2 | 10-11 | Browse by area: zone opens a list of its lakes | done | 1b; 10 fish management zones |
| D3 | 10-11 | Split view with scores, PC only | done | 1b; ≥ 1024 px |
| D4 | 10-11 | Fold-open popup sections | done | 1b; lake panel sections |
| D5 | 10-11 | Lake panel slides up on phones | done | 1b |
| D6 | 10-11 | Phone bottom bar: Near me, Saved, Area, Clear | done | 1b |
| D7 | 10-11 | Satellite basemap | done | 1b; Esri World Imagery |
| D8 | 10-11 | Apple Maps link | done | 1b |
| D9 | 10-11 | List only the lakes on screen | done | 1b |
| D10 | 10-11 | Plain explainers (Reading the barometer) | done | 1b; Barometer tab text + learn/barometer.html |
| D11 | 10-11 | Reading room: 6 guides + species pages with licensed photos | done | 1b; 6 guides, 9 species, 9 free-licence photos |
| D12 | 10-11 | First-visit walkthrough + install guide | done | 1b; first visit, troutmap.visited |
| D13 | 10-11 | Popup close button covered by top-right buttons (K4) | done | 1a |
| D14 | 10-11 | This winter view: ice and aerated lakes first | open | Build 2 |
| E1 | 10-11 | Ice-on / ice-off estimates, labelled estimated | open | Build 2 |
| E2 | 10-11 | Hatch timing | open | Build 2 |
| E3 | 10-11 | Turnover | open | Build 2 |
| E4 | 10-11 | Fly and lure choice | open | Build 2 |
| E5 | 10-11 | How to fish each lake, from own data | open | Build 2 |
| E6 | 10-11 | Lake notes and hot spots via Gemini, each with source link and date | open | Build 2, D18 |
| E7 | 10-11 | Depth chart links vs Alberta's 169 surveyed lakes | open | Build 2 |
| E8 | 10-11 | Trout depth finder | done | exists as Summer layer |
| F1 | 10-11 | Saved lakes on every device (Firebase) | open | Build 3 |
| F2 | 10-11 | Weekly email when a saved lake has a top day | open | Build 3 |
| G1 | 10-11 | Wildfire and smoke | superseded | not doing: live outside source |
| G2 | 10-11 | Forum | superseded | not doing: accounts and upkeep |
| G3 | 10-11 | Ads and sponsor blocks | superseded | not doing: personal app |
| G4 | 10-11 | Visitor tracking | superseded | not doing: collects user data |
| G5 | 10-11 | Typical size from a growth guess | superseded | not doing: invented number |
| G6 | 10-11 | Campsite counts per lake | superseded | not published by Alberta |
| G7 | 10-11 | Trophy records per lake | superseded | not published by Alberta |
| H1 | 10-11 | README walleye/pike and species count correction (K5) | done | 1a |
| H2 | 10-11 | Fill FEATURES.md (K6) | done | 10-29, this change |
| H3 | 10-11 | Updated BC comparison table at the end of each build | open | every build |
| H4 | 10-11 | Measure free weather limit before gold pins go live | done | 1b; 250 calls per full load in 5 requests, counted per IP; ≤ 2,000 a day at 8 loads |
| H5 | 10-11 | CRLF package, Windows-style dry-run, tests, coverage gate | open | every build; 1b done 10-30 (see Checks) |
| H6 | 10-11 | Work split: 1a chat; 1b prototype in chat, build in Claude Code; Build 2 same session | done | D20 |
| K7 | 10-29 | Fill WORKING_RECORD.md | done | 10-29, this change |
| K8 | 10-29 | Distance slider label | done | 1a |
| K10 | 10-29 | Unused functions recencyDays, chart_ref | done | 1b; removed, test_unused_functions_are_gone |

## Hotspot counter
| Area / feature | Fix rounds | Recurrences | Regressions caused | Workarounds/exceptions | Last symptom | Rewrite-vs-repair reviewed? |
|---|---|---|---|---|---|---|
| Season reader (js/conditions.js) | 1 | 0 | 0 | 0 | split season read as closed (K1) | no |
Thresholds: 3 fix rounds, 2 recurrences, 1 regression caused by a fix, or 3 workarounds/exceptions → no further patch until the rewrite-vs-repair comparison is presented; then set the last cell to "yes <date>". The hooks read this table: keep the header words.

## Deliverable ledger
| Deliverable | State | Evidence |
|---|---|---|
| Build 1a | COMPLETE | PR #15 merged 2026-10-16; 183 tests pass on main (2026-10-29) |
| FEATURES.md, WORKING_RECORD.md | COMPLETE | this change, 2026-10-29 |
| Build 1b | IN REVIEW | branch build-1b; comparison with the prototype sent 2026-10-30 |
| Build 2 | NOT STARTED | |
| Build 3 | NOT STARTED | |

## Checks and evidence
- 2026-10-29 unittest discover on main → 183 passed; live site has bait-chip, ice-chip, aerated-chip; live stamp troutmap-shell-v3
- 2026-10-30 build-1b: unittest 191 run → 184 passed, 2 skipped, 5 need openpyxl (CI installs it), 2 fail only on a non-UTF-8 Windows locale (pass with PYTHONUTF8=1)
- 2026-10-30 layout check (headless Chrome, fresh profile) at 360×740, 390×844, 768×1024, 1024×768, 1440×900, no lake and lake open → 0 problems; Learn at 360 → 0 tap targets under 44 px
- 2026-10-30 weather: one full load = 250 calls, 5 requests, 250 cells, 0 failed; reload within 3 h = 0 calls (250 from IndexedDB)
- 2026-10-30 behaviour: town pick keeps home; No signal card once per visit with the town-list sentence; winter guard → wind-chill week bar, ice pins, "Ice likely"; Why stays open and focus stays on a redraw; close returns focus to the row; Species mode kept in Copy link
- 2026-10-30 coverage gate (hz-change-guard) on FEATURES.md items → 42 of 42 present
- 2026-10-30 reviewer pass → 19 findings, all fixed; prototype vs build comparison: https://claude.ai/artifact/7dPaCHfY45Yw7xB9gruG7q (17 questions)
- Dry-run: passed — the working tree served as the owner's clone would be after Pull origin, opened in a fresh browser profile, compared screen by screen with the prototype

## Open questions / blockers
- H4 answered 2026-10-30: Open-Meteo counts per IP; one full load = 250 calls in 5 requests (measured in the browser), 3 h cache.
- Species page facts from general knowledge (Athabasca rainbow at risk, westslope cutthroat Threatened, walleye special licence, bull trout protected): owner to check.
