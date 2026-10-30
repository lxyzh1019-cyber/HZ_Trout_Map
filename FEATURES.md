# FEATURES — HZ_Trout_Map — manifest v2 — Build 1b

Locked features of the current version (branch build-1b, from main at 243d3a2). Every edit is checked against this list and ends with a regression table. Update this file in the same change that adds, changes or removes a feature.

## Which lake, which day (Build 1b)
- Week bar over the map: 7 days, each with the top Bite score of the lakes on screen; tap a day and the pins recolour for it. "gusty" marks a day when most lakes on screen gust to 40 km/h or more.
- "Best near you" card (below 1024 px): the top 3 lakes for the picked day within 100 km (widens to 200 km, then all), with "All" to show the rest.
- PC (1024 px and wider): map in the middle, a 380 px lake column on the right with Near me, Saved, Area and Clear in its header, a score list, and "Only lakes on screen". Phone: a bottom bar with the same 4 buttons; "All" opens the full list, with "Only lakes on screen".
- Near me lists by distance from your location (or home). Saved lists saved lakes ranked by best day. Area lists the lakes of one of Alberta's fish management zones. Clear resets the list, the town and the open lake.
- Two scores per lake and day: Bite (unchanged weights: light 40, water temperature 35, pressure trend 15, wind 6, rain 4; moon a capped multiplier; gusts not scored, warning at 40 km/h) and Day out (wind plus half the gust spread, times 0.7 under 10 ha, 1.0 medium, 1.3 over 200 ha; rain amount and chance; air temperature). A lake with no area uses medium and says "size unknown".
- Lake panel: slides up on a phone, fills the right column on a PC; replaces the pin popup, the Conditions panel and the photos panel.
- Best-day banner: "Go <day> · <score>", the reason, 7 bars with Best/Good/Fair/Poor, gusty days named "not a boat day"; shut days show no score.
- "Why this score": the 5 parts that add up to the shown Bite score (moon inside each part), the Day out size factor, and one sentence comparing with the nearest lake that has a different forecast spot or size.
- Pin colour modes: Bite on the day (default), Best this week (gold pins), Species, Change. Score pins carry the number; groups show the best score inside them. Colour-blind-safe score scale: grey, blue, light blue, gold.
- Forecast section: Wind / Weather / Barometer / Solunar tabs, 3 or 7 days, Lines or Grid, today's major and minor feeding times and the moon phase. "Bite by time of day" keeps the 6-hour strip, the 7 x 5 grid, the factor rows and the measured water temperature input.
- A plain daily tip, and a "sun breaking through" reminder labelled as anglers' reports and never scored.
- Winter: when more than half the lakes on screen have the winter guard on, the week bar shows wind chill, pins show the legal ice season, and the panel says "Ice likely". Frozen lakes are left out of gold pins, "Best near you" and the Saved ranking.
- Tags: Low harvest limit (trout limit 0–2), Trophy size rule (the guide's words), Popularity estimate (largest Angler's Atlas report count, labelled estimate), Aerated, Ice season (winter), Advisory (when an Alberta notice names the lake).
- Stocked size and date shown; "Typical size: not published by Alberta"; growth never guessed.
- Search for towns and lakes: the saved Alberta town list first (works with no signal), then Open-Meteo place search in Canada (Alberta first). Each lake row has distance, Bite and Day out. Picking a town measures from it (lists, distances and the distance filter) and does not change home.
- Messages: forecast progress, "No signal" once per visit (says town search uses the saved Alberta town list), "No lakes in range" with a widen button, and a first-visit walkthrough with install steps.
- Satellite basemap (Esri imagery); Apple Maps and Google Maps links; Alberta rules and licence links; Learn room with 6 guides and species pages (licensed photos only); plain explainers (Reading the barometer).
- Weather for every lake: one request per 50 forecast spots, 250 calls for a full load, saved for 3 hours in IndexedDB (memory if IndexedDB is refused); the data quality panel shows the count.

## Map and finding a lake
- Pins cluster when zoomed out and split as you zoom in; hover shows name, score, distance, fish in view and last stocking date.
- "Zoom to results" fits the lakes the filters leave; "Copy link" copies a URL that reproduces every filter, home, the picked day, the town and the list.
- Zone view ranks Alberta's ten fish management zones by fish stocked.
- Basemaps: Topo, Street, Satellite.

## Filters (Filters button; a column on a wide PC, a slide-over below 1024 px)
- Stocked recently: 30, 60, 90 days, or this season.
- Species: nine (rainbow, brook, brown, tiger, cutthroat, westslope cutthroat, walleye, northern pike, Arctic grayling).
- Fish size: under 15 cm, 15 to 20 cm, catchable 20 cm and over.
- Distance from home (or the picked town): your location, a picked point or Red Deer; slider 0 to 1000 km with a screen-reader label.
- Years 2011 to 2026 with All / None / Last 5 / Latest; a year marked * is in progress.
- Season and ice: Open today; Open for ice fishing (open all winter, early ice, late ice: 303 lakes); Aerated; Bait ban.
- A lake not matched to the regulations is never hidden by a season or bait filter.
- Advisory count on the Filters button.

## Lake panel (was the lake popup)
- Bait ban: filled red badge at the top when the guide lists a bait ban.
- Ice season line: all winter / early ice only / late ice only / closed, with "Legal is not safe. Ice thickness is never forecast."
- Aerated badge on every stated-aerated lake (24), with or without a known depth; red thin-ice warning October to April.
- Stocking summary, last stocked with size, years, species, change versus last year, the stocking table.
- Zone, area, reported species (Anglers Atlas, with agree / disagree counts), on-site facilities and facility chips.
- Max depth, mean depth, summer layer, winterkill risk band with its reasons.
- Regulations: season, open today, bait, catch limits, where the rule comes from, link to the official zone tables.
- Photos and Alberta's description (inside Lake info), Google Maps directions, Apple Maps, copy link, save star, close button.

## Conditions
- Bite score with evidence tiers; 6-hour strip with the best time named; 7 days x 5 day-parts grid.
- Sun and moon tracks with major and minor periods; your own measured water temperature replaces the estimate and feeds that lake's daily scores.
- Winter guard: when every day of the past 7 days had a mean air temperature below freezing, the open-water score is hidden and the panel says "Ice likely".

## History and charts
- Charts by species, by season, per-species trend and a stocking calendar (Charts button in the header); opening a lake scopes them to that lake.
- Planning summary with year-over-year totals and direction.

## Taking it with you
- List view sortable on any column, including Bite and Day out for the picked day, with CSV download.
- Saved lakes in the browser and a one-click multi-stop driving route through them.
- Works offline after the first visit (service worker, shell cache v4, saved town list, saved forecasts).

## Data and honesty
- Estimated positions are labelled; data quality panel; evidence page (evidence.html).
- Alberta advisories (closures, consumption) collected daily and shown in Filters.
- ACA aeration roster with ACA's Winter Angling column; a test fails if it disagrees with the regulations.
- Colour-blind-safe pin palettes; every score pin carries its number.
- Credit lines: Open-Meteo (CC BY 4.0), town list licence, GeoNames via Open-Meteo, Esri imagery, photo credits.

## Regression table — manifest v1 → v2 (Build 1b)
| Feature | v1 → v2 | Note |
|---|---|---|
| Search by name, distance, jump to lake | kept | now also towns, with scores |
| Clusters and hover card | kept | hover adds the Bite score |
| Zoom to results; Copy link | kept | link adds day, town, list |
| Pin colour: species or change | kept | plus Bite on the day (default) and Best this week |
| Zone view | kept | |
| Basemaps Topo and Street | kept | plus Satellite; buttons moved onto the map |
| Filters: stocked recently, species, size, distance, years, season and ice | kept | in the Filters panel; distance measures from a picked town |
| Unmatched lake never hidden by season or bait filter | kept | |
| Bait ban red badge first | kept | in the lake panel |
| Ice season line with "Legal is not safe" | kept | in the lake panel |
| Aerated badge and thin-ice warning | kept | |
| Stocking summary, change, stocking table | kept | in Fish and stocking |
| Zone, area, reported species, facilities | kept | in Lake info |
| Depth, summer layer, winterkill | kept | in Lake info |
| Regulations block and official link | kept | in Rules, plus rules and licence links |
| Photos, directions, favourite star | kept | photos inside Lake info |
| Top-right buttons move down while a popup is open | intentionally removed | decision 13: no pin popup any more; panel has its own close button |
| Separate Conditions panel and button | intentionally removed | decision 13: its content is in the lake panel |
| Bite score, tiers, 6-hour strip, 7 x 5 grid | kept | in "Bite by time of day" |
| Weights and gust rule | kept | tested unchanged |
| Sun and moon tracks; measured water temperature | kept | |
| Winter guard "Ice likely" | kept | also drives the week bar and pins |
| Charts and planning summary | kept | Charts button in the header (decision 12) |
| List view, CSV | kept | plus Bite and Day out columns |
| Favourites and route | kept | route also in Saved |
| Offline | kept | shell cache v4 |
| Phone slide-over filters | kept | also below 1024 px |
| Estimated positions, data quality, evidence page | kept | weather call count added |
| Advisories | kept | count badge on Filters |
| ACA roster test | kept | |
| Colour-blind-safe palette | kept | score pins use a blue–gold scale with numbers (decision 14) |

## Regression table format (paste at the end of every edit)
| Feature | v<old> → v<new> | Note |
|---|---|---|
| <feature> | kept / added / intentionally removed / missing | <why, if not kept> |
