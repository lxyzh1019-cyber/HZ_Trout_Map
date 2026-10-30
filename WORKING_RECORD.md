# WORKING RECORD — HZ_Trout_Map — rules v2

Single working record for this repository. Updated by the main session at the end of every implementation turn (the record guard hook checks this). Keep it terse; history lives in git.

## Approved baseline
- Plan v1 approved 2026-10-11 (D20): Build 1a (aeration, ice season, bait ban, known fixes) in chat; Build 1b (forecast, two scores, layout) prototyped in chat, built in Claude Code; Build 2 (estimates, elevation, hot spots, winter view) same Claude Code session; Build 3 (Firebase sync, email alert) later.
- Build 1a merged 2026-10-16 (PR #15), live.

## Pending
- Build 1b prototype, Round 1 (three directions), awaiting the owner's pick — 2026-10-29.

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
| B3 | 10-11 | Low harvest limit tag (trout limit 0–2, 54 lakes) | open | 1b |
| B4 | 10-11 | Trophy size-rule tag | open | 1b |
| B5 | 10-11 | Popularity estimate from Anglers Atlas report count, labelled estimate | open | 1b |
| B6 | 10-11 | Stocked size + date instead of typical size; no growth guess | open | 1b |
| B7 | 10-11 | Links to Alberta licence and rules pages | open | 1b |
| C1 | 10-11 | Keep Bite score and its weights; do not copy BC weights | done | exists |
| C2 | 10-11 | Gusts stay out of the Bite score; warning at 40 km/h | done | exists |
| C3 | 10-11 | Day out score: wind + half gust spread scaled by lake size; rain amount + chance; air temp | open | 1b, D17 |
| C4 | 10-11 | Best-day banner: day name, 7 bars, Best/Good/Fair/Poor | open | 1b |
| C5 | 10-11 | Banner uses both scores (bite + boat day) | open | 1b |
| C6 | 10-11 | Best day skips gusty days and says gusty | open | 1b, D14 |
| C7 | 10-11 | Favourites ranked by best day | open | 1b |
| C8 | 10-11 | Gold pins: Best this week colour mode | open | 1b, D15; needs H4 |
| C9 | 10-11 | Score column in list view | open | 1b |
| C10 | 10-11 | Line chart for wind, gusts, rain | open | 1b |
| C11 | 10-11 | Grid / Lines toggle | open | 1b |
| C12 | 10-11 | Forecast tabs Wind/Weather/Barometer/Solunar + 3/7-day switch | open | 1b |
| C13 | 10-11 | Today's feeding windows: major/minor clock times + moon phase | open | 1b |
| C14 | 10-11 | Plain-language daily tip from own data, no outside service | open | 1b |
| C15 | 10-11 | Clearing reminder (sun breaking through), labelled anglers' reports, not scored | open | 1b |
| C16 | 10-11 | Winter guard: hide open-water score when frozen (K9) | done | moved to 1a by D22 |
| C17 | 10-11 | Winter score: light, pressure, moon + cold/wind-chill comfort note | open | Build 2 |
| C18 | 10-11 | Elevation from weather service, for ice and water temperature only | open | Build 2 |
| D1 | 10-11 | Near me one-tap list | open | 1b |
| D2 | 10-11 | Browse by area: zone opens a list of its lakes | open | 1b |
| D3 | 10-11 | Split view with scores, PC only | open | 1b |
| D4 | 10-11 | Fold-open popup sections | open | 1b |
| D5 | 10-11 | Lake panel slides up on phones | open | 1b |
| D6 | 10-11 | Phone bottom bar: Near me, Saved, Area, Clear | open | 1b |
| D7 | 10-11 | Satellite basemap | open | 1b |
| D8 | 10-11 | Apple Maps link | open | 1b |
| D9 | 10-11 | List only the lakes on screen | open | 1b |
| D10 | 10-11 | Plain explainers (Reading the barometer) | open | 1b |
| D11 | 10-11 | Reading room: 6 guides + species pages with licensed photos | open | 1b |
| D12 | 10-11 | First-visit walkthrough + install guide | open | 1b |
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
| H4 | 10-11 | Measure free weather limit before gold pins go live | open | 1b |
| H5 | 10-11 | CRLF package, Windows-style dry-run, tests, coverage gate | open | every build |
| H6 | 10-11 | Work split: 1a chat; 1b prototype in chat, build in Claude Code; Build 2 same session | done | D20 |
| K7 | 10-29 | Fill WORKING_RECORD.md | done | 10-29, this change |
| K8 | 10-29 | Distance slider label | done | 1a |
| K10 | 10-29 | Unused functions recencyDays, chart_ref | open | remove when 1b touches that code |

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
| Build 1b | NOT STARTED | prototype Round 1 pending |
| Build 2 | NOT STARTED | |
| Build 3 | NOT STARTED | |

## Checks and evidence
- 2026-10-29 unittest discover on main → 183 passed; live site has bait-chip, ice-chip, aerated-chip; live stamp troutmap-shell-v3

## Open questions / blockers
- H4: Open-Meteo free limit is assumed to count per device; measure one load before gold pins go live.
