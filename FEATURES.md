<!-- feature-list: by-screen -->
# FEATURES — HZ Trout Map — manifest v1 — confirmed 2026-10-13

Locked features of the current version, one section per screen. Each line says what you see or what it does, then its proof: a test name or a reference picture (`tests/reference/<screen>-<phone|ipad|pc>.png`). Every edit is checked against this list and ends with a regression table whose Kept row names its proof. Update this file in the same change that alters a feature. History stays in git and `docs/archive/`, not here. Pictures are made by the Build 1a stage 2 tool; until then picture proofs are planned (marked by the path) and the named tests are the live proof.

## Map and pins
- Pins group together when zoomed out and separate when zoomed in — Proof: picture tests/reference/map-phone.png
- Hover a pin for name, distance, fish in view and last stocking date — Proof: picture tests/reference/map-pc.png
- Pin colour is the main species or year-over-year change (needs two selected years) — Proof: picture tests/reference/map-ipad.png
- Search by name with distance shown, jumping to the lake — Proof: picture tests/reference/map-phone.png
- Every species on the map has a colour and a band — Proof: test_every_species_on_the_map_has_a_band
- The app can draw every species it holds (nine species in the species filter) — Proof: test_the_app_can_draw_every_species_it_holds
- Home location is yours to set (location, pick on map, drag marker, Red Deer) and is remembered — Proof: picture tests/reference/map-pc.png

## Filter panel
- Stocked recently (30, 60, 90 days, this season), species, fish size, distance from home, years — Proof: picture tests/reference/filters-phone.png
- Years 2011 to 2026 with All / None / Last 5 / Latest; a year marked `*` is in progress — Proof: test_the_current_season_is_marked_provisional
- Group "Season and ice" (design file, kept): Open today, Open for ice fishing, Aerated — Proof: picture tests/reference/filters-ipad.png
- Open for ice fishing keeps lakes open on every day from Dec 15 to Mar 1, including split seasons (design file, kept) — Proof: test_a_split_season_is_open_in_january
- Open through winter but shut in April still counts as ice-open (design file, kept: split-season fix) — Proof: test_open_through_winter_but_shut_in_april_counts
- Open for ice fishing also shows early-ice and late-ice lakes; only "closed" ice-season lakes are hidden (Build 1a stage 3) — Proof: test_the_ice_season_reaches_the_page
- A lake not matched to the regulations is never hidden by a season filter — Proof: picture tests/reference/filters-pc.png
- Filters and home location live in the URL; `?lake=wb6051` opens one lake — Proof: picture tests/reference/popup-phone.png
- Filter panel is a slide-over at phone width — Proof: picture tests/reference/filters-phone.png

## Lake popup
- Opens with a verdict line: stocked how recently, season open or not, winterkill risk; one clause fewer rather than an invented one — Proof: picture tests/reference/popup-phone.png
- Aerated badge for every lake stated as aerated, with or without a depth (design file, kept) — Proof: test_aeration_shows_without_a_depth
- Aerated badge carries the thin-ice warning Oct to Apr (design file, kept) — Proof: picture tests/reference/popup-ipad.png
- A lake off the aeration list is never told it is unaerated — Proof: test_a_lake_off_the_list_is_not_told_it_is_unaerated
- Depth line; unknown depth produces no advice at all — Proof: test_unknown_depth_produces_no_advice_at_all
- Regulation block with Season row and Bait row — Proof: picture tests/reference/popup-pc.png
- Ice row under the Season row: Open all winter · Early ice only — open to Nov 30 · Late ice only — open from Apr 1 · Early and late ice — closed Dec 1 to Mar 31 · Closed — no ice fishing; Oct–Apr every class but closed adds "Legal is not safe. Ice thickness is never forecast." (Build 1a stage 3) — Proof: test_each_ice_class, picture tests/reference/popup-ipad.png
- Season and limits come from the regulations; unlisted lakes take the zone default — Proof: test_unlisted_waterbody_takes_the_zone_default
- Position is marked as estimated when taken from the land description — Proof: test_a_position_taken_from_the_map_says_so
- Photos and long description go to the lake panel, not the popup — Proof: picture tests/reference/lake-panel-phone.png
- Actions: Google Maps directions from home, favourite, copy link — Proof: picture tests/reference/popup-phone.png

## Lake panel
- Description and photographs in a panel; photos never leave Alberta's server — Proof: test_no_photo_leaves_the_published_host
- A photo count is never published without the photos — Proof: test_a_photo_count_is_never_published_without_the_photos
- Panel shows the lake's stocking history and charts scoped to the lake — Proof: picture tests/reference/lake-panel-ipad.png
- Panel layout at phone, iPad and PC widths — Proof: picture tests/reference/lake-panel-pc.png

## Conditions panel
- Next 6 hours strip — Proof: picture tests/reference/conditions-phone.png
- 7-day grid of daily scores — Proof: picture tests/reference/conditions-ipad.png
- CLOSED today block when the season is shut — Proof: test_blank_season_on_a_listed_waterbody_means_closed
- Winter guard: when every daily mean in the past 7 days is below 0 °C, the score is hidden and an "Ice likely" block shows; in the 7-day grid a day whose own past 7 means are all below 0 shows "Ice likely" (Build 1a stage 3) — Proof: test_ice_likely_needs_seven_days_below_zero, picture tests/reference/conditions-freeze-phone.png
- Water temperature input — Proof: picture tests/reference/conditions-pc.png
- Solunar times — Proof: picture tests/reference/conditions-phone.png
- Weather is fetched from Open-Meteo with 7 past and 7 forecast days — Proof: picture tests/reference/conditions-freeze-phone.png
- Winterkill band is never below the bottom and aeration cuts both ways — Proof: test_aeration_cuts_both_ways

## Offline
- Service worker precaches every data file the page fetches — Proof: test_every_data_file_the_page_fetches_is_precached
- Service worker precaches every JS file and every script tag — Proof: test_every_js_file_is_precached
- Every script tag points at a real file and the missing-library check names every script — Proof: test_missing_library_check_names_every_script
- Offline notice and reload offer when a newer version has been fetched — Proof: test_every_script_tag_is_precached

## Data and rules
- Season parsing reads every range, including a split season (design file, kept) — Proof: test_the_js_parser_reads_every_range
- Ice-season classes from the season text: all-winter 297, early 1, late 2, early-late 3, closed 6 of 309 regulation entries (Build 1a stage 3) — Proof: test_the_data_ice_class_counts
- ACA winter angling column agrees with the regulations (design file, kept) — Proof: test_aca_winter_angling_agrees_with_the_regulations
- Aerated roster is keyed on an id and reaches the aerated list — Proof: test_the_roster_reaches_the_aerated_list
- Spring Lake note (design file, kept) — Proof: test_every_roster_row_names_a_lake_on_the_map
- Aeration only lowers a band on a measured depth — Proof: test_aeration_still_only_lowers_a_band_on_a_measured_depth
- Regulation basis kinds: published per lake, zone default, or none for an unmatched lake — Proof: test_an_unmatched_lake_gets_no_limits_rather_than_the_default
- Published per-lake regulations are consistent — Proof: test_published_per_lake_regulations_are_consistent
- Every zone in the published data has a default — Proof: test_every_zone_in_the_published_data_has_a_default
- Bait legend marker is expanded — Proof: test_the_bait_legend_marker_is_expanded
- Walleye and pike waters are on the map and linked — Proof: test_every_walleye_row_in_the_reports_is_linked
- Nothing Alberta stocks is quietly dropped — Proof: test_nothing_alberta_stocks_is_quietly_dropped
- Coordinates are inside Alberta; nearly every lake can be placed — Proof: test_coordinates_are_inside_alberta
- Stocking totals agree with Alberta's stocking map — Proof: test_the_two_publications_agree_on_almost_every_lake_year
- Confirmed facts survive a rebuild — Proof: test_a_confirmed_fact_survives_a_rebuild

## References
- Sizes: phone 390×844, ipad 820×1180, pc 1440×900 · Looks: one look
- Rule document: README.md (Features, Waters this map does not show, Tests) and plans/first-switch-to-the-purrfect-gizmo.md
- Tests: index.html, js/*.js, data/*, scripts/* → cd scripts && python3 -m unittest discover -p "test_*.py"
- Tests: README.md counts → scripts/test_readme_counts.py
- Tests: screens → python3 tests/pictures.py compare
- Tools: tests/pictures.py — makes and compares the reference pictures

## Regression table (paste at the end of every edit)
| Regression table | Result |
|---|---|
| Kept | <n> features · Proof: pictures <n> screens × <sizes> sizes, <k> changed (all planned) · tests <passed>/<total> |
| Added | … |
| Intentionally removed | … |
| Missing | … |
