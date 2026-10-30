# FEATURES — HZ_Trout_Map — manifest v1 — confirmed 2026-10-29

Locked features of the current version (main at 4c94d0a, Build 1a live). Every edit is checked against this list and ends with a regression table. Update this file in the same change that adds, changes or removes a feature.

## Map and finding a lake
- Search by name shows the distance and jumps to the lake.
- Pins cluster when zoomed out and split as you zoom in; hover shows name, distance, fish in view and last stocking date.
- "Zoom to results" fits the lakes the filters leave; "Copy link" copies a URL that reproduces every filter and home.
- Pin colour: main species, or year-over-year change.
- Zone view ranks Alberta's ten fish management zones by fish stocked.
- Basemaps: Topo and Street.

## Filters
- Stocked recently: 30, 60, 90 days, or this season.
- Species: nine (rainbow, brook, brown, tiger, cutthroat, westslope cutthroat, walleye, northern pike, Arctic grayling).
- Fish size: under 15 cm, 15 to 20 cm, catchable 20 cm and over.
- Distance from home: your location, a picked point or Red Deer; slider 0 to 1000 km with a screen-reader label.
- Years 2011 to 2026 with All / None / Last 5 / Latest; a year marked * is in progress.
- Season and ice: Open today; Open for ice fishing (open all winter, early ice, late ice: 303 lakes); Aerated; Bait ban.
- A lake not matched to the regulations is never hidden by a season or bait filter.

## Lake popup
- Bait ban: filled red badge at the top when the guide lists a bait ban.
- Ice season line: all winter / early ice only / late ice only / closed, with "Legal is not safe. Ice thickness is never forecast."
- Aerated badge on every stated-aerated lake (24), with or without a known depth; red thin-ice warning October to April.
- Stocking summary, last stocked, years, species, change versus last year.
- Zone, area, reported species (Anglers Atlas, with agree / disagree counts), on-site facilities and facility chips.
- Max depth, mean depth, summer layer, winterkill risk band with its reasons.
- Regulations: season, open today, bait, catch limits, where the rule comes from, link to the official zone tables.
- Photos, Google Maps directions from home, favourite star.
- The top-right buttons move down while a popup is open, so its close button stays clickable.

## Conditions
- Bite score now with evidence tiers; 6-hour strip with the best time named; 7 days x 5 day-parts grid.
- Weights: light 40, water temperature 35, pressure trend 15, wind 6, rain 4; moon applied after as a capped multiplier; gusts shown, warning at 40 km/h, not scored.
- Sun and moon tracks with major and minor periods; your own measured water temperature can replace the estimate.
- Winter guard: when every day of the past 7 days had a mean air temperature below freezing, the open-water score is hidden and the panel says "Ice likely".

## History and charts
- Charts by species, by season, per-species trend and a stocking calendar; a pin click scopes them to that lake.
- Planning summary with year-over-year totals and direction.

## Taking it with you
- List view sortable on any column, with CSV download.
- Favourites in the browser and a one-click multi-stop driving route through them.
- Works offline after the first visit (service worker, shell cache v3); works at phone width with a slide-over filter panel.

## Data and honesty
- Estimated positions are labelled; data quality panel; evidence page (evidence.html).
- Alberta advisories (closures, consumption) collected daily and shown in the sidebar.
- ACA aeration roster with ACA's Winter Angling column; a test fails if it disagrees with the regulations.
- Colour-blind-safe pin palette.

## Regression table format (paste at the end of every edit)
| Feature | v<old> → v<new> | Note |
|---|---|---|
| <feature> | kept / added / intentionally removed / missing | <why, if not kept> |
