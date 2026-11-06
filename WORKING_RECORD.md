# WORKING RECORD — HZ_Trout_Map — rules v2

Single working record for this repository. Updated by the main session at the end of every implementation turn (the record guard hook checks this). Keep it terse; history lives in git.

## Approved baseline
- Plan v1 approved 2026-10-11 (D20): Build 1a (aeration, ice season, bait ban, known fixes) in chat; Build 1b (forecast, two scores, layout) prototyped in chat, built in Claude Code; Build 2 (estimates, elevation, hot spots, winter view) same Claude Code session; Build 3 (Firebase sync, email alert) later.
- Build 1a merged 2026-10-16 (PR #15), live.
- Build 1b prototype picked by the owner 2026-10-29: design/build-1b-prototype.html (PR #17), for feature reference only.
- Plan "Build 1b and Build 2" Rev 2 approved 2026-10-29: decisions 1–15 at option A.
- Build 1b merged 2026-10-30 (PR #18, merge 64852ae).
- Build 2 started 2026-11-03 on branch build-2 from 64852ae; Stage 2 shown again in plan mode and approved 2026-11-03.

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
- [agreed] Prototype differences Q1–Q17 (comparison page 2026-10-30): keep the build for Q1–Q14 and Q16–Q17; Q15 shorter search hint on phones — search: Search a lake or a town
- [agreed] Build 2 differences Q1–Q8 (like-for-like comparison page 2026-11-03, https://claude.ai/artifact/5AM4Tg8tnJcL8u7GuiDpaJ): owner accepted all 8 recommendations; build kept as is — search: This winter near
- [agreed] 3D depth model, free turning in every direction (decision 1B, 2026-11-04) — search: DepthModel
- [agreed] Button in the Depth chart row of Lake info (2A) — search: Show 3D depth model
- [agreed] All 43 lakes saved on the first visit (3A) and the 3D add-on too (5A) — search: depth_grids/index.json
- [agreed] Opens full screen over the map with Close, Default view and the depth key (4A) — search: data-default
- [agreed] Full detail; first visit may grow to about 2.2 MB (6A) — search: LONG_SIDE
- [agreed] 4 layers on at the start (wind, spots, structure, drop-offs), the rest turned on (7B with 4 on) — search: LAYERS_ON
- [agreed] All 4 extras: sun and shade shore, under-ice band, aerator warning, reported spots (8A) — search: sunShore
- [agreed] Layer explanations in a Learn guide, opened from "i" and each layer's "?" (9A) — search: depth-model
- [agreed] Motor rules from Transport Canada TP 15587E and MyWildAlberta (10B); the app stays free, so the non-commercial terms hold (11A) — search: boating_rules
- [agreed] Names hidden until hover or tap; smaller wind arrows; spots by access (shore, trolling, ice) — search: showTip
- [agreed] Rev 5 smoothness: glide, eased zoom, Default view glide, instant Height, gentle land bank, Play button — search: requestAnimationFrame
- [agreed] (owner kept it 2026-11-04) three.js r149, not r159: r150+ prints a deprecation warning on every open; same API used — search: three@0.149
- [agreed] (owner kept it 2026-11-04) Depth from the contour lines (relaxation between them), not the AGS grid alone: the grid reads half the depth on small lakes (Chickakoo 6 m vs 15 m) — search: RELAX_SWEEPS
- [agreed] (owner kept it 2026-11-04) Time slider from now to the end of the forecast, not from 24 h back: past hours add nothing to planning — search: A saved forecast that ended
- [differs from plan] A new 3D renderer per open, freed on Close (plan: one reused); "This phone cannot show 3D" shows in the view, not on the button; credit lines in the 3D view footer and the Learn guide, not in the search credits — search: v.stop
- [differs from plan] Transport Canada Schedule 4 (engine power) has no Alberta rows, so it is not read; structure sizes in metres (point window 60 m, basin and hump radius 100 m, basin from 4 m) so they work on every grid size; Learn ids layer-struct and layer-rep — search: cellsFor
- [agreed] Build 4 plan Rev 3 approved 2026-11-04: Learn 3D guide has one model with "Show on the model" per section (1A) — search: mountDemo
- [agreed] Learn demo lake is a real surveyed lake with island, hump, point and basin, fixed example wind (2A) — search: DEMO_LAKE
- [agreed] New Learn guide "Reading a river", Red Deer River example (3B) — search: learn/river.html
- [agreed] Filters count shows only changed filters; default years listed as a chip but not counted (4B) — search: filter-count
- [agreed] Days on or after the estimated ice-on date: "Ice forming — no score", out of Best (5A) — search: iceForming
- [agreed] Depth range rule: ice 1.5–4; <10 °C 1–4; 10–18 °C 2–6; >18 °C layered = summer layer, else half depth to bottom; rising deeper half, falling shallower half; capped at max depth — search: fishDepth
- [agreed] Tap a day bar in the lake panel to pick the day; Why starts with the change from today — search: dayCompareSentence
- [agreed] (owner accepted 2026-11-04) "3D" in list rows and the hover card is a label, not a button (a button inside the row button is invalid); the lake panel gets a "Show 3D depth model" button at its top instead — search: btn3d
- [agreed] (owner accepted 2026-11-04) Ice forming removes the score only on an ice-on date worked out from this forecast; near or past the usual (calendar) date the score stays and the banner warns "Ice usually forms here about …" — search: iceUsual
- [agreed] (owner accepted 2026-11-04) Survey depths go beyond the mean: 18 surveyed lakes with no published max depth get the survey's max, so their summer layer, winterkill band and fish depth change; chain grids (Pierre Greys, Wildhorse) give none — search: load_survey
- [agreed] Build 5 Plan v1 approved 2026-11-04 (Edmonton): 4 stages, one PR each; decisions 1–6 at option A (no score without a forecast anywhere; answer line + tags + thin-ice warning open, week bars in "This week"; best hour ±1 h; usual month only at 60%+; rules-year warning at panel top and in Rules; CRLF for .md only) — search: answerHtml
- [agreed] Build 5 Rev 3 (owner 2026-11-04 evening): keep the best-day box format open at the top (Go day · score, reason, ice line, 7 bars); "8 reports" tag the same size as the others; decisions 7–9 at A ("Bite by hour", safety lines whole, one wind word) — search: Tip and status
- [agreed] Build 5 Rev 5 (owner 2026-11-05): decision 11 at A = CanVec 1:50,000 (the 1:250,000 file has no names); decision 15 at A = static.ags.aer.ca allowed, 3D for the guide's depth-chart lakes — search: water_linear_flow
- [differs from plan] Kananaskis and Medley Rivers are stocked waters; their stretch joins the stocked pin instead of a second "not stocked" pin; stocked lakes with no zone (Headwall, Memorial, Running Rain, Badger and others) cannot take their guide row until a zone is set; Oldman, Bearspaw and Pine Coulee Reservoirs are in neither the place names nor CanVec under that name — search: stocked_twin
- [agreed] (owner accepted 2026-11-04) River guide has one labelled bend drawing (A–G), not one drawing per water type; the sample 3D model in the guide is a second small view, off while a lake's 3D view is open — search: data-demo-host

## Pending
- Build 1b: merged 2026-10-30 (PR #18). Owner still to do: device check, and the 4 species facts on the Learn pages.
- Build 2: merged 2026-11-04 (PR #19, cd9a470). Owner still to do: device check.
- Build 3 (3D depth model): merged 2026-11-04 (PR #20, d3e3c0d). Owner still to do: device check.
- Build 4 (feature check fixes and connections): merged 2026-11-04 (PR #21, 922ddb0). Owner still to do: device check.
- Build 5 Stage 1 (fewer words): merged 2026-11-04 (PR #22, d70bc8a). Owner still to do: device check.
- Leftover helper worktree .claude/worktrees/agent-a00cd60cf51c9739a: removal needs the owner's separate yes (QC2).

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
| C17 | 10-11 | Winter score: light, pressure, moon + cold/wind-chill comfort note | done | 2; Conditions.scoreWinter + comfortNote, test_winter_score_renormalises_light_pressure_and_moon |
| C18 | 10-11 | Elevation from weather service, for ice and water temperature only | done | 2; 380 lakes in 4 calls, data/lake_elevation.json; test_lake_height_only_feeds_the_water_model_and_ice |
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
| D14 | 10-11 | This winter view: ice and aerated lakes first | done | 2; "This winter near …", test_this_winter_puts_ice_season_and_aerated_lakes_first |
| E1 | 10-11 | Ice-on / ice-off estimates, labelled estimated | done | 2; Estimates.ice degree-days, warning next to dates; test_ice_forms_and_goes_by_degree_days |
| E2 | 10-11 | Hatch timing | done | 2; 10/14/16/17 °C, test_hatch_thresholds |
| E3 | 10-11 | Turnover | done | 2; reuses stratification, test_turnover_reuses_the_summer_layer |
| E4 | 10-11 | Fly and lure choice | done | 2; no bait on 25 bait-ban lakes, test_never_bait_on_a_bait_ban_lake |
| E5 | 10-11 | How to fish each lake, from own data | done | 2; Estimates.howToFish, test_how_to_fish_uses_the_lake_data |
| E6 | 10-11 | Lake notes and hot spots via Gemini, each with source link and date | done | 2; empty data/hot_spots.json (0 spots), schema test, scripts/check_links.py; filling it is the owner's step |
| E7 | 10-11 | Depth chart links vs Alberta's 169 surveyed lakes | done | 2; AGS layer has 166 outlines; 43 of 380 lakes matched by name and position |
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
| L1 | 11-04 | Overall feature check: anything broken or lost | done | 4; nothing lost; 2 bugs fixed (double Escape, repeated credit name), search Escape found in review |
| L2 | 11-04 | New connections, e.g. lake with 3D, map in the filter | done | 4; 3D filter, 3D mark, panel 3D button, boating in Rules, survey depths, shapes in How to fish, Learn links |
| L3 | 11-04 | Other features that help me | done | 4; fish depth layer, shore directions, ice-forming days, day-vs-today |
| L4 | 11-04 | "Steady pressure: fish feed at normal depths" — what depth in this lake | done | 4; Estimates.fishDepth, test_fish_depth_rule |
| L5 | 11-04 | Filters shows 2 but I cannot tell which filters | done | 4; the 2 were Alberta notices; chips + changed-filter count + ⚠ |
| L6 | 11-04 | 3D map in the Learn guide with the rule texts (points 7–20) | done | 4; sample model + Show on the model, test_learn_guides_match_the_3d_view |
| L7 | 11-04 | Pick a different day and see why its score differs from today | done | 4; day bars + dayCompareSentence |
| L8 | 11-04 | How to read a river and find the fish, Red Deer River example | done | 4; learn/river.html; facts for the owner to check |
| M1 | 11-04 | W1 No forecast: no scores, no 7-day bars, "Needs a forecast" | done | 5.1; bannerHtml, whyHtml, conditions-ui; test_no_forecast_shows_no_score_and_no_bars |
| M2 | 11-04 | W2 Remove the extra "AERATED kept aerated…" row; keep tag and thin-ice warning | done | 5.1; aerationBlock |
| M3 | 11-04 | W3 One "Map" button with a small menu of the 5 map buttons | done | 5.1; #map-menu, Escape and outside tap close it |
| M4 | 11-04 | W4 One answer line at the top; everything else folded | superseded | owner 11-04 (Rev 3): keep the best-day box open as before; tip and status folded |
| M5 | 11-04 | W5 Short tags, full wording on tap | done | 5.1; tagList, .tag-full |
| M6 | 11-04 | W6 Each estimate's "From: …" behind a small ⓘ | done | 5.1; estHead(title, inputs) |
| M7 | 11-04 | At most 60 words on the panel's first phone screen; before and after counts | done, target not met by owner's choice | 5.1 Rev 3 with the box open: Beaver Lake 390 px no forecast 107 → 76 first screen, 246 → 84 whole panel; made-up weather 174 → 123 |
| M8 | 11-04 | Rules year check banner from 1 Apr 2027; README refresh steps | done | 5.1; rulesYearWarning; README "Refreshing the rules" |
| M9 | 11-04 | "Usually stocked" months at 60%+, "Too few years to tell" under 3 years | done | 5.1; usualMonths; 282 of 382 lakes |
| M10 | 11-04 | Every stage: tests, 5-size layout check, before/after pictures, FEATURES and record, CRLF, final report | open | 5.1 done; stages 2–4 to come |
| M11 | 11-04 | Stage 2: score all lakes and rivers in the 2026 guide, Red Deer River below Dickson Dam, CGNDB and CanVec positions, weather budget, Stocked filter | done | 5.2; 286 lakes, 86 stretches, 318 spots, 3D on 114 lakes; 52 names in data/waters_review.csv; spot count M15 |
| M14 | 11-05 | Zones for the stocked lakes that have none, from the Alberta Conservation Association's documents | done, other source | the Association's site blocks automated reading (bot check); decision 16 A: Alberta's sportfishing regulations map (geospatial.alberta.ca); 58 filled, 14 corrected where the guide agrees; owner corrected Emerald (Hart) ES1 and Dormer ES2 in lake_facts.csv |
| M15 | 11-05 | Count the owner's 218 pins: lake, river stretch (300 m) or nothing; read the file only | done | 143 lake (128 outline holds the lake point, 13 outline with the lake's name, 2 size circle + 1 km), 10 river only, 65 nothing; file read in place, nothing saved; .claude/state/checks/spots_count.py |
| M16 | 11-05 | River edges from Alberta's zone outlines (decision 18 A) | done | Open-Meteo answered 00:10 UTC 11-06; 91 stretches (5 new), 24 changed, 351 spots; Red Deer keeps "found"; own pull request after #24 was merged |
| M17 | 11-05 | Phone check after Stage 2: rules first and red bait ban; rivers off with Not stocked; Red Deer River line does not open; 3D always 2.5–4 m, colours, no move, roads and launches; colours clash; filters auto-hide?; small text | done | plan Rev 9 decisions 20–24 at A; owner OK on the pictures 11-05 (text two sizes larger again, "Bait Ban"); roads and launches are decision 23 A, own pull request |
| M12 | 11-04 | Stage 3: import my spots (browser only), species mode | open | Build 5 Stage 3 |
| M13 | 11-04 | Stage 4: Firebase sync and weekly email (ASK first) | open | Build 5 Stage 4; replaces F1, F2 |

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
| Build 1b | COMPLETE | PR #18 merged 2026-10-30 (64852ae) |
| Build 2 | COMPLETE | PR #19 merged 2026-11-04 (cd9a470) |
| Build 3 | COMPLETE | PR #20 merged 2026-11-04 (d3e3c0d) |
| Build 4 | COMPLETE | PR #21 merged 2026-11-04 (922ddb0) |
| Build 5 Stage 1 | COMPLETE | PR #22 merged 2026-11-04 (d70bc8a); 274 tests pass on GitHub |
| Build 5 Stage 2 | COMPLETE | PR #23 merged 2026-11-05 (2f53fba); GitHub checks passed |
| Stage 2 phone-check fixes | COMPLETE | PR #24 merged 2026-11-06 (f374b77); GitHub checks passed |
| Stage 2 river edges | READY FOR REVIEW | M16; branch claude/funny-ritchie-bealq0 from f374b77 |
| Build 5 Stage 3 | NOT STARTED | |
| Build 5 Stage 4 | NOT STARTED | |

## Checks and evidence
- 2026-10-29 unittest discover on main → 183 passed; live site has bait-chip, ice-chip, aerated-chip; live stamp troutmap-shell-v3
- 2026-10-30 build-1b: unittest 191 run → 184 passed, 2 skipped, 5 need openpyxl (CI installs it), 2 fail only on a non-UTF-8 Windows locale (pass with PYTHONUTF8=1)
- 2026-10-30 layout check (headless Chrome, fresh profile) at 360×740, 390×844, 768×1024, 1024×768, 1440×900, no lake and lake open → 0 problems; Learn at 360 → 0 tap targets under 44 px
- 2026-10-30 weather: one full load = 250 calls, 5 requests, 250 cells, 0 failed; reload within 3 h = 0 calls (250 from IndexedDB)
- 2026-10-30 behaviour: town pick keeps home; No signal card once per visit with the town-list sentence; winter guard → wind-chill week bar, ice pins, "Ice likely"; Why stays open and focus stays on a redraw; close returns focus to the row; Species mode kept in Copy link
- 2026-10-30 coverage gate (hz-change-guard) on FEATURES.md items → 42 of 42 present
- 2026-10-30 reviewer pass → 19 findings, all fixed; prototype vs build comparison: https://claude.ai/artifact/7dPaCHfY45Yw7xB9gruG7q (17 questions)
- Dry-run: passed — the working tree served as the owner's clone would be after Pull origin, opened in a fresh browser profile, compared screen by screen with the prototype
- 2026-11-03 build-2: lake heights 380 of 380 in 4 calls (Open-Meteo elevation); depth charts 43 of 380 lakes matched to 166 AGS outlines; hot spots 0; live link check 40 links, 0 broken
- 2026-11-03 build-2: Build 1b + Build 2 test classes 61 run → 61 pass locally (PYTHONUTF8=1); 239 tests in the file
- 2026-11-03 build-2 layout check (headless Chrome, fresh profile) at 360×740, 390×844, 768×1024, 1024×768, 1440×900: no lake, lake open, new sections open → 0 problems; winter mode at 390 and 1440 → 0; hot spot section scrolled into view → only "close button covered" (the panel header scrolls away, as in 1b)
- 2026-11-03 build-2 behaviour: 380 of 380 lakes show 5 "estimated" blocks with inputs; 25 bait-ban lakes, 0 with a bait line; ice warning next to every ice date; 0 page errors; weather full load 250 calls in 5 requests
- 2026-11-03 build-2 elevation effect: 181 of 380 lakes move ≥ 1 Bite point on some day; median correction 0.3 °C; largest 10 points (mountain lakes, forecast spot 700 m higher)
- 2026-11-03 build-2 reviewer pass → 12 findings, all fixed; coverage gate 53 of 53
- 2026-11-04 build-3 data: 43 lakes, 40 AGS lakebed grids (50 m, 10TM, elevation m a.s.l.); depth refilled from 728 contour lines; deepest cell within 1.5 m of the deepest contour on 40 of 40; 1.37 MB. Transport Canada TP 15587E: 403 Alberta rows, 33 of 43 lakes with a rule, 5 same-name rows dropped by location (Chin, Cow, Peanut, Spring)
- 2026-11-04 build-3 tests: Build3DepthModelTests 11 pass, test_depth_grids 14 pass; test_regression_checks 230 run, only the 7 known local errors (no openpyxl; Windows text encoding, they pass with PYTHONUTF8=1)
- 2026-11-04 build-3 browser check at 375×812 (Chickakoo, Sylvan, Wabamun): opens in about 0.2 s on PC; turn and glide, Default view, tap marker name and reason, tap depth, time slider, Learn "?" opens its section, under-ice mode; 0 console errors
- 2026-11-04 build-3 reviewer pass → 13 findings, all fixed (ice state now matches Lake info; summer planes out of taps and out of season; old forecast not shown as Now; Escape, focus and Tab trap; 44 px targets; 10 km/h rule cited to s. 2(7); deviations recorded; arrows every 300 m; real reach on coarse grids; materials and failed builds freed; lost-context message; this proof)
- Proof: 2026-11-04 offline at 375×812, server stopped, service worker v6: 40 of 40 lakebed files and three.js in the cache; Chickakoo opens in 0.54 s with no network; turn, wheel zoom, Default view, time slider (Thu 18:00 · 7 km/h from W · Sun down), Play steps the hours, summer layer out-of-season message, WebGL context lost → "3D paused" message → restored → hidden, Escape closes, reopen works, smallest button 44 px; console: only the deliberate network test failed

- 2026-11-04 build-4 feature check on main (d3e3c0d): GitHub checks pass; live site has shell v6 and the 3D view; FEATURES.md items all have code; Build 3 removed no Build 2 feature
- 2026-11-04 build-4 data: build_history.py rebuild changes only data/lake_depth.json (116 published depths unchanged, 18 more from the survey; 3 chain lakes left as they were); data/depth_grids/index.json gains mean_depth_m and water_ha from the saved grids (no grid rebuilt)
- 2026-11-04 build-4 tests: unittest discover 277 run → 277 pass locally (PYTHONUTF8=1, openpyxl installed)
- 2026-11-04 build-4 reviewer pass → 16 findings, all fixed or recorded as differences (shared grids, usual-date ice warning, "?" lands after the sample mounts, one 3D drawing at a time, search Escape, shore-only directions, 44 px targets, page scroll over the sample, river winter wording and life jacket, day water said "today", sample model message, See it in 3D button, tests)
- Proof: 2026-11-04 browser at 390×844 and 1440×900: day bar picks the day (URL day=, week bar follows), Why "Mon is 6 higher than today (70)…", tip "Here on Sat: about 2.5–4 m … lake 5.5 m deep", Beaver Mines banner "Ice usually forms here about Nov 5 … Check the lake before you go", Filters chips and count (0 at start, 2 after 90 days + 3D, ✕ removes), 3D fish depth layer, shore spot Directions 49.36759,-114.30766, Escape one layer at a time (guide, 3D, search), guide "?" lands on its section, sample model on/off note, smallest tap 44 px. Offline (headless Chrome, network off, shell v7): app loads 382 lakes, lake panel 7 day bars, river guide and the sample model build from the cache, 0 page errors

- 2026-11-04 build-5 stage 1 (Edmonton evening): unittest test_regression_checks 272 run → all pass locally (first run) (PYTHONUTF8=1, openpyxl installed) after updating 3 checks to the new wording (shell v8, ⓘ inputs, verdict guard); Build5Stage1Tests 9 pass
- 2026-11-04 build-5 stage 1 word count (Playwright, Beaver Lake wb4014, weather blocked, words of the panel's visible innerText): 390×844 first screen 107 → 59, whole panel with sections closed 246 → 65, height 1519 → 698 px; with made-up weather first screen 174 → 79
- 2026-11-04 build-5 stage 1 layout check (Playwright, made-up weather) at 360×740, 390×844, 834×1194, 1194×834, 1280×800: map, Map menu open, Escape, lake open, tag tapped, all sections open, ⓘ open → 0 faults (before: day bars 40–43 px wide and "Next 6 h / 7 days" 25 px tall at 3 sizes; fixed); 0 page errors
- 2026-11-04 build-5 stage 1 Usually stocked: 382 lakes, 282 with a usual month, 54 with fewer than 3 stocked years, 46 with no month at 60% (the plan's 53 came from a first count keyed by name; 54 keyed by lake id is right)
- 2026-11-04 build-5 stage 1 reviewer pass → 11 findings, all fixed or put to the owner: ice safety line on the first screen; "sun and moon only" words removed; no winter score without a forecast; one wind word (Day out) in panel and list; open tag and ⓘ kept on a redraw, focus kept; menu aria, ⓘ labels, aria-live; water box kept without a forecast; README step 4 uses regs_aliases.csv; tests for taps and exact counts; "Bite by hour" rename and the 87 words with a forecast asked as decisions; this Proof line. Full suite then 275 run → 275 pass
- 2026-11-04 build-5 stage 1 Rev 3 (box open, answer line removed, tags one size): test_regression_checks 274 run → 274 pass; word count 390 px first screen no forecast 76, made-up weather 123; layout 5 sizes 0 faults; main (7f10c2c, to-do update) merged into the branch
- Proof: 2026-11-04 Playwright on the working tree (headless Chromium, fresh profile, weather blocked or made-up): Beaver Lake panel first screen 59 words with no forecast, "Needs a forecast", no bars; Map menu opens, Escape and a pick close it; tag tap shows and hides the full words; ⓘ shows "From: …"; Usually stocked "May (14 of 16 years)"; layout 5 sizes 0 faults; 0 page errors

- 2026-11-05 build-5 stage 2: unittest discover 308 run → 308 pass (PYTHONUTF8=1); build_history.py leaves data/ unchanged; Open-Meteo heights 983 keys (rate limit 429 hit after repeated runs; elevation.py now asks only for new or moved points); reviewer pass 16 findings → all fixed (data side by a helper on separate files, app side in this session) or recorded above
- 2026-11-05 build-5 stage 2 sizes: first visit about 10.4 MB (app 1.7, stocking data 4.3, waters and rivers 0.7, lakebeds 4.0); was about 7.4 MB

## Open questions / blockers
- H4 answered 2026-10-30: Open-Meteo counts per IP; one full load = 250 calls in 5 requests (measured in the browser), 3 h cache.
- Species page facts from general knowledge (Athabasca rainbow at risk, westslope cutthroat Threatened, walleye special licence, bull trout protected): owner to check.
- River guide facts from general knowledge (learn/river.html): water from deep in Gleniffer Reservoir stays cold all summer; brown trout and mountain whitefish the main fish, some rainbow, bull trout pass through; releases can raise the river fast; the dam keeps some water open in winter: owner to check.
- 2026-11-05 Stage 2 zones: lake_zones.py 382 stocked lakes, 366 by the lake layer, 7 by the river layer, the rest by zone outline; build_history.py twice → same md5 for every data/*.json and *.csv; guide rules on 363 stocked lakes (316 before); 312 tests pass; layout at 360, 390, 834, 1194, 1280 for Pine Coulee, Headwall Lakes and the Red Deer River → 0 faults, 0 page errors
- 2026-11-05 Open-Meteo answered "Daily API request limit exceeded" (HTTP 429): the river rebuild is deferred (M16); data/rivers.json is the 24d8cde build the owner saw in the pictures
- 2026-11-05 reviewer pass on the zone change → 8 findings, all fixed: a same-named lake elsewhere no longer confirms a zone (land description within 15 km, or a name in one zone only); zone outlines saved once and read from disk; cut-short map answers stop the script; owner corrections are "settled", and "fill" rows no longer block Alberta's zone; outlines unsimplified, holes per outline, nearest zone within 2 km on a sliver; the new tests run from the file too; heights saved for a .zip input; zone rows match wb ids by id (one lake is renamed during the build). Zones and rules unchanged by the fixes; rebuild twice → same md5; 316 tests pass
- 2026-11-05 phone-check fixes: 322 tests pass; layout at 360, 390, 834, 1194, 1280 for Pine Coulee, Gull, Red Deer River, Beaver Lake and (new) the Filters panel → 0 faults, 0 page errors (the Filters panel had 59 small targets before, never checked until now); tap on the Red Deer River line on a 390 px phone page: before no panel, after "Red Deer River" (both PP2 stretches); 3D tap on Gull: before "Fish depth (estimate) … lake depth unknown", after "Depth here: 7.6 m … Fish depth today (estimate): 1–4 m"
- 2026-11-05 reviewer pass on the phone-check fixes → 9 findings, all fixed: waters not stocked get the build's depth entry with summer layer and winterkill (71 lakes; Cold Lake 99 m was called "shallow" by the first fallback); a pinch only zooms; search turns the water's stocking switch back on; the Rivers switch covers the stocked rivers too (Kananaskis, Medley) and the note counts 84 + 2; the compass follows a moved model; the fish-depth line names the slider's day; empty-state and chip words; 4 labels missed by the text sweep; focus back on Filters after "Show N waters". Also fixed: the slide-over now opens above the top bar (its × was hidden at 360 px). 322 tests pass; rebuild twice → same md5; layout 0 faults at 5 sizes for 5 lakes and the Filters panel
- 2026-11-05 owner on the pictures: "font even bigger, the rest is OK, and Bait Ban instead of Bait ban" → text two more sizes up (labels 14, panel 17, titles 18, rules block 16; Filters 15), "Bait Ban" wherever the app shows it (the guide's stored text stays "Bait ban"); 322 tests pass; layout 0 faults at 5 sizes for 5 lakes and Filters
- 2026-11-05 22:39 UTC Open-Meteo still "Daily API request limit exceeded"; owner: continue without it → pull request opened with the rivers as in Stage 2; before it: 322 tests pass; rebuild twice → same md5, no data change; layout 0 faults, 0 page errors at 5 sizes for 5 waters and Filters
- 2026-11-06 00:10 UTC Open-Meteo answered → river edges: waterbodies.py full run (3 min), elevation.py (88 new heights, 1 call), build_history twice → same md5; 2 tests changed as expected (5 rivers leave the review list; the province-wide cell guard 600 → paced 550 a minute, since 615 cells now); 322 tests pass; layout 0 faults at 5 sizes for Red Deer, Muskwa, North Saskatchewan (PP2) and Beaver Lake; taps on Red Deer (both), Blindman, Sylvan Creek and Muskwa open their panels. depth_charts.py not re-run: it reads lakes only
