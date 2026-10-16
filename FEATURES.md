# FEATURES — Alberta Trout Stocking Map — manifest v1 — confirmed 2026-10-16

Locked features of the current version. Every edit is checked against this list and ends with a regression table. Update this file in the same change that alters a feature. Over-list rather than under-list. The numbered list in the `index.html` header comment (M01–M103+) is the detailed version; this file groups it.

## Data
- Reads `data/manifest.json` for the years and the provisional season; fetches every `data/lakes_YYYY.json` in parallel; merges years by stable `lake_id`.
- Startup failure names the real cause; missing vendor libraries are named by file.
- Walleye, pike and grayling are carried like trout; the 35 walleye- and pike-only waters are on the map, not hidden (`data/out_of_scope.csv` is empty).
- Stocked weight from 2021 where Alberta publishes it, blank before — never zero.
- Alberta's own waterbody id is used where its stocking map names the lake.
- Reported species are kept apart from stocked species and from catch-limit species.

## Map
- Leaflet map with topo and street basemaps; draggable home marker.
- Pins sized by fish, coloured by dominant species, second species as a ring, species initial on large pins; clustering; lake labels close in.
- Pin colour mode: dominant species, or year-over-year change (needs two years).
- Zone view: a bubble per fish management zone with a ranked table.
- Popups survive filter changes; lakes with no position are counted, not drawn.
- Popup × stays clear of the top-right buttons: Leaflet autoPan padding is measured from `.map-btns` when a lake or zone popup opens (top below the buttons, right edge left of them).

## Lake popup
- Name, land description, distance, fish shown, years as runs, species, change versus the previous year, stocking table at true date precision, Google Maps link and directions, favourite and copy-link.
- Red **Bait ban** line under the land description when the regulations state a bait ban.
- Verdict line: recency, season, winterkill — one clause fewer rather than an invented one.
- Aerated badge for every lake stated aerated; Oct–Apr it carries the thin-ice warning.
- Catch limits block: guide year, basis pill (this lake / stocked-lake default / zone default / see elsewhere), official link; an unmatched lake shows no limits.
- **Ice season** line under Season on every popup: all winter / early ice only / late ice only / early and late ice / closed / not known — check the regulations (unmatched and cross-reference lakes included).
- Where ice fishing is legal (all, early, late, both): "Legal is not safe. Ice thickness is never forecast."
- Depth, summer layer and winterkill from Alberta's pages; no depth means no depth advice; mean depth published or estimated band.
- Lake panel with Alberta's description and linked (never copied) photographs.

## Filters
- Species (9: Rainbow, Brook, Brown, Tiger, Cutthroat, Westslope, Walleye, Pike, Grayling), distance from home (slider named "Maximum distance from home" for screen readers, value text kept in sync), years, recency, fish size, facilities, search.
- Season and ice group: *Open today*; *Open for ice fishing* hides only lakes whose ice season is "closed" (early, late, both and all stay; unread seasons stay); *Aerated*; *Bait ban* (keeps only lakes with a stated bait ban).
- A lake not matched to the regulations is never hidden by a season filter.
- Every filter goes through `lakePassesFilters`; filters and home are shared through the URL (`open=1`, `ice=1`, `aer=1`, `bait=1`, `lake=`).

## Seasons (js/conditions.js)
- `seasonOpenOn` reads every range, wraps the new year, returns null when unread.
- `seasonOpenAllWinter`: open every day Dec. 15 – Mar. 1; split seasons count.
- `iceSeason`: "all" | "early" (open Nov. 30) | "late" (open Apr. 1) | "both" | "closed" | null.

## Conditions panel
- Score weighted by evidence (light, water temperature, pressure, wind and rain), moon capped multiplier, missing inputs dropped and renormalised.
- Next 6 h strip and 7-day grid from one weather call; sun and moon tracks; solunar periods; advisories.
- A lake whose season is shut is not scored (CLOSED block).
- **Ice likely**: when all 7 forecast daily highs (today onward, `temperature_2m_max`) are below 0 °C and the lake is open, the verdict, strip/grid and factors are hidden; without weather data there is no guard.
- Measured water temperature overrides the model, remembered per lake.
- Evidence page with self-check.

## Charts, list and other
- Charts by species, season, per-species trend, stocking calendar; planning summary; chart scope follows the clicked lake.
- List view, sortable, CSV export; favourites with a driving route.
- Works offline (service worker; shell cache `troutmap-shell-v4`), offline badge, update prompt, installable.
- Phone layout with slide-over sidebar.

## Design file Build 1a (kept as is)
- Aerated badge and filter; thin-ice warning Oct–Apr; "Season and ice" group; ACA winter-angling column in `data/aca_aeration_roster.csv`; Spring Lake note; split-season fix; `seasonOpenOn` / `seasonOpenAllWinter`.

## References
- Tests: run `cd scripts && PYTHONUTF8=1 python -m unittest discover -p "test_*.py"` (5 tests need `openpyxl`).
- Tests: popup autoPan / map buttons → PopupClearOfButtonsTests
- Tests: ice season (js/conditions.js, index.html filter and popup) → IceSeasonTests, WinterSeasonTests, RealJsTests
- Tests: bait ban line, chip, URL → BaitBanTests
- Tests: slider label, service-worker cache → SmallBuildChecks, OfflineAssetTests
- Tests: Ice likely (js/weather.js, js/conditions-ui.js) → IceLikelyTests, RealJsTests
- Tests: README walleye/pike count, species → ReadmeWalleyePikeCountTests, SpeciesBeyondTroutTests, OutOfScopeTests
- Tests: aeration, ACA roster → AerationIsKnownPerLakeTests, AcaRosterTests
- Tests: regulations and limits → RegulationTests, SettledDisagreementTests
- Tests: depth → DepthTests, MeanDepthTests
- Tests: lake profile, photos → LakeProfileTests
- Tests: published data, ids, linking → PublishedDataTests, PublishedWaterbodyIdTests, LinkingAccuracyTests, LinkingCompletenessTests, CoordinateHygieneTests, SharedLandDescriptionTests, ConfirmedFactsSurviveTests
- Tests: report readers, ATS, names → SourceReaderTests, AtsGeometryTests, AtsAccuracyTests, NameMatchingTests
- Tests: stocking map import, weights → ImportedSourceTests, StockingMapAgreementTests, StockedWeightTests
- Tests: reported species → ReportedSpeciesTests

## Regression table format (paste at the end of every edit)
| Feature | v<old> → v<new> | Note |
|---|---|---|
| <feature> | kept / added / intentionally removed / missing | <why, if not kept> |
