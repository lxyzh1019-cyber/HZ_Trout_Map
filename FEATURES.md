# FEATURES — HZ_Trout_Map — manifest v9 — Build 5 Stage 2 river edges

Locked features of the current version (branch claude/funny-ritchie-bealq0, from main at 922ddb0). Every edit is checked against this list and ends with a regression table. Update this file in the same change that adds, changes or removes a feature.

## Which lake, which day (Build 1b)
- Week bar over the map: 7 days, each with the top Bite score of the lakes on screen; tap a day and the pins recolour for it. "gusty" marks a day when most lakes on screen gust to 40 km/h or more.
- "Best near you" card (below 1024 px): the top 3 lakes for the picked day within 100 km (widens to 200 km, then all), with "All" to show the rest.
- PC (1024 px and wider): map in the middle, a 380 px lake column on the right with Near me, Saved, Area and Clear in its header, a score list, and "Only lakes on screen". Phone: a bottom bar with the same 4 buttons; "All" opens the full list, with "Only lakes on screen".
- Near me lists by distance from your location (or home). Saved lists saved lakes ranked by best day. Area lists the lakes of one of Alberta's fish management zones. Clear resets the list, the town and the open lake.
- Two scores per lake and day: Bite (unchanged weights: light 40, water temperature 35, pressure trend 15, wind 6, rain 4; moon a capped multiplier; gusts not scored, warning at 40 km/h) and Day out (wind plus half the gust spread, times 0.7 under 10 ha, 1.0 medium, 1.3 over 200 ha; rain amount and chance; air temperature). A lake with no area uses medium and says "size unknown".
- Lake panel: slides up on a phone, fills the right column on a PC; replaces the pin popup, the Conditions panel and the photos panel.
- Best-day box open at the top of the lake panel (owner, Build 5 Rev 3: kept as before, not a one-line answer), with "Why …?" closed under it. "Tip and status" (Build 5, closed): the stocked / open / winterkill line and the daily tip.
- Best-day banner: "Go <day> · <score>", the reason, 7 bars with Best/Good/Fair/Poor, gusty days named "not a boat day"; shut days show no score. No forecast (Build 5): "Needs a forecast", no score and no bars; the Why, "Bite by hour" (it keeps the water temperature box) and the winter list rows show no score either. Each bar is a button: tap it to pick that day for the whole app, as the week bar does; the picked bar is outlined (Build 4).
- Ice forming (Build 4): days on or after an ice-on date the ice estimate works out from this forecast show "Ice forming — no score" and leave Best, gold pins and "Best near you". Near or past the usual ice-on date with no ice in the forecast, the scores stay and the banner says "Ice usually forms here about <date> … Check the lake before you go."
- "Why this score": first the picked day against today ("Mon is 6 higher than today (70): light +8, pressure trend -5."; "This is today."), then the 5 parts that add up to the shown Bite score (moon inside each part), the Day out size factor, and one sentence comparing with the nearest lake that has a different forecast spot or size.
- Pin colour modes: Bite on the day (default), Best this week (gold pins), Species, Change. Score pins carry the number; groups show the best score inside them. Colour-blind-safe score scale: grey, blue, light blue, gold.
- Forecast section: Wind / Weather / Barometer / Solunar tabs, 3 or 7 days, Lines or Grid, today's major and minor feeding times and the moon phase. "Bite by hour" (Build 5; was "Bite by time of day") keeps the 6-hour strip, the 7 x 5 grid, the factor rows and the measured water temperature input.
- A plain daily tip, and a "sun breaking through" reminder labelled as anglers' reports and never scored. The tip gives a depth range for the lake on the picked day, labelled estimated (Build 4, Estimates.fishDepth): under ice 1.5–4 m; water under 10 °C 1–4 m; 10–18 °C 2–6 m; over 18 °C the summer layer, or half the depth to the bottom on a lake that does not layer; rising pressure the deeper half, falling the shallower half; never deeper than the lake.
- Winter: when more than half the lakes on screen have the winter guard on, the week bar shows wind chill, pins show the legal ice season, and the panel says "Ice likely". Frozen lakes are left out of gold pins, "Best near you" and the Saved ranking. The list becomes "This winter" (Build 2).
- Tags, short (Build 5): "Limit n trout" (trout limit 0–2), "Size rule" (the guide's words), "n reports" (Popularity estimate: largest Angler's Atlas report count, labelled estimate), "Aerated", "Ice: <kind>" (winter), "Advisory" (when an Alberta notice names the lake). A tap shows the full words under the tags (an Advisory adds the Alberta notice link); a second tap hides them.
- Stocked size and date shown; "Typical size: not published by Alberta"; growth never guessed.
- Search for towns and lakes: the saved Alberta town list first (works with no signal), then Open-Meteo place search in Canada (Alberta first). Each lake row has distance, Bite and Day out. Picking a town measures from it (lists, distances and the distance filter) and does not change home.
- Messages: forecast progress, "No signal" once per visit (says town search uses the saved Alberta town list), "No lakes in range" with a widen button, and a first-visit walkthrough with install steps.
- Satellite basemap (Esri imagery); Apple Maps and Google Maps links; Alberta rules and licence links; Learn room with 8 guides (Build 4: "Reading a river: the Red Deer River") and species pages (licensed photos only); plain explainers (Reading the barometer).
- Weather for every lake: one request per 50 forecast spots, 250 calls for a full load, saved for 3 hours in IndexedDB (memory if IndexedDB is refused); the data quality panel shows the count.

## Estimates and winter (Build 2)
- Lake height for every placed lake (380, Open-Meteo elevation, Copernicus DEM). It corrects the forecast air to the lake's own height (6.5 °C per km) for the water temperature estimate and the ice estimate only.
- "Ice, hatches and tackle" section in the lake panel. Each block says "estimated"; what it used ("From: …") opens with the ⓘ button next to it (Build 5).
  - Ice cover: ice-on and ice-off dates from freezing and thawing degree-days over 14 days of air (7 past, 7 forecast), by latitude, height and depth; beyond the forecast the trend, then the usual dates. Dates only, with "Legal is not safe. Ice thickness is never forecast." next to them.
  - Insect hatches on the water estimate: chironomids 10 °C, mayflies 14 °C, damselflies 16 °C, sedges 17 °C (likely / soon / not yet / done for the year / under ice).
  - Turnover from the summer layer: spring after ice-off; fall when the surface is 4–10 °C on a lake that layers; "too shallow to layer" and "no depth survey" said plainly.
  - Flies and lures by season, water temperature and bait rule. A bait-ban lake gets no bait line, only "Bait ban: flies and lures only, no bait, not even on a jig." A lake with no bait rule on record gets no bait line either, and "Bait rule not found". The regulations stay the only legal source.
- "How to fish this lake" section: from area, depth and summer layer, facilities, aeration, bait rule, ice season and trout limit. On a surveyed lake with its own lakebed file, a line names the lakebed shapes and where they are ("a hump, 3.1 m under the surface in the north part"), with a "See it in 3D" button (Build 4).
- Winter score for frozen lakes: light, pressure trend and moon only, renormalised; shown in the "Ice likely" banner with a cold comfort note from Environment Canada's wind chill bands, and in the list rows in winter.
- "This winter" list: lakes open in the ice season and aerated lakes first, then the lower winterkill band, then the better winter score, then the nearer; rows say "aerated" and the winterkill band.
- Survey depths (Build 4): where MyWildAlberta publishes no maximum depth, the Alberta lakebed survey gives it (18 lakes), and its measured mean replaces an estimated one; labelled "measured by the Alberta lakebed survey, at the survey water level". A file shared by a chain of lakes (Pierre Greys, Wildhorse) gives none of them its depth. These depths feed the summer layer, winterkill band and fish depth.
- Depth chart link in Lake info for 43 of the 380 lakes, matched by name and position to the Alberta Geological Survey bathymetry layer (166 surveyed lakes); other lakes say "No match found in Alberta's depth chart list" with a link to that list.
- Hot spots section, shown only when data/hot_spots.json has spots for the lake; each spot shows its note, source site and date, a Source button and an On the map button. Every spot needs an https source link and an ISO date (tested), and scripts/check_links.py checks the links live. The file starts empty.

## 3D depth model (Build 3)
- "Show 3D depth model" button at the top of the lake panel (Build 4) and in the Depth chart row of Lake info, for the 43 lakes with an Alberta depth chart (40 lakebed files; the Pierre Greys and Wildhorse chains share one). The Alberta depth chart link stays next to it.
- Opens full screen over the map: Close, Default view (glides back to the first position and zoom) and an "i" button that opens the Learn guide.
- Lakebed from the Alberta Geological Survey: outline for the shore, contour lines for the depth (the AGS grid alone reads too shallow on small lakes), AGS grid for land height; up to 160 cells on the long side; deepest cell within 1.5 m of the deepest contour on all 40 (tested). Depth at the survey water level, said in the key.
- One finger or the left mouse button moves the model; two fingers or the right mouse button turn it (it glides after you let go); pinch or scroll to zoom; Default view resets the place, the turn and the zoom; Height slider (starts at a lake-by-lake value, 1–200×). In the Learn guide one finger still turns, so the page can scroll (phone check after Stage 2).
- Tap the lakebed: "Depth here: x m", with today's fish depth after it when that layer is on. A marker answers a tap only within 16 px of it on the screen and in front of the lakebed (before, the fish-depth dots caught every tap, even on the bank).
- Colours by metres, the same for every lake: lightest at 0 m, darkest at 20 m or deeper; the legend says "20 m or deeper" and "deepest here x m".
- A water that is not stocked takes its max and mean depth from its lakebed survey (Gull Lake 7.6 m), so its fish-depth tip no longer says "lake depth unknown".
- Names hidden until you point at a marker (PC) or tap it (phone); one name at a time, with its reason under the model.
- Wind: small arrows about every 300 m of water (fewer on the biggest lakes, at most about 160) and a wind sign (compass that turns with the model, wind arrow, speed, from, sun position). Time slider and Play over the saved forecast hours. Wind direction comes from the forecast (new field, Build 3).
- Fish depth today layer (Build 4, on at the start): the tip's depth range on the lakebed, for the time slider's day.
- Tapping a shore spot adds "Directions to the shore near this spot" (Google Maps) (Build 4).
- Possible spots (estimates) by access: up to 3 shore spots (3 m water within a 30 m cast, facing the wind's push, more open water behind it scores higher), one trolling route (5 m line, or less on a shallow lake, on the downwind half; faded without a boat launch; with the boating rules), and under ice up to 3 ice spots (1.5–4 m within about 60 m of a drop-off). Under 8 km/h the spots use the drop-offs only. On big lakes (cells over 30 m) the reasons give the real distance instead of "30 m".
- Structure markers: island, point, hump, basin, drop-off, flat. Drop-off dots.
- Layers you turn on: weed line (4 m, estimate), summer layer (the lake's layer band, June to September, not under ice), deep within a cast, calm shore, sun and shade shore, reported spots, under-ice band (any time of year). 5 are on at the start (fish depth, wind, spots, structure, drop-offs). Aerated lakes show the aerator warning October to April.
- Boating rules on the trolling route: Transport Canada TP 15587E (2nd edition, April 2026; name AND township-range must match) and MyWildAlberta wording; 33 of 43 lakes have a rule; Transport Canada wins and both are named (Victor Lake); the 10 km/h within 30 m of shore rule on every lake (Vessel Operation Restriction Regulations, s. 2(7)).
- Learn guide "Reading a lake in 3D: layers and spots" with one section per layer, spot rule and message; each layer row's "?" opens its section. Build 4: a sample 3D model at the top (Lower Kananaskis Lake, fixed west wind 20 km/h) and a "Show on the model" button per section that sets its layers, wind, ice and message. Off, with a line, while a lake's 3D view is open (one 3D drawing at a time). In the guide a sideways drag turns it and the page still scrolls; Ctrl or ⌘ with the wheel zooms.
- Boating rule also in the Rules section of the lake panel (Build 4).
- Messages: 3D add-on not saved, lakebed not saved, no wind direction saved, no forecast saved, saved forecast old, phone cannot show 3D, 3D paused by the phone, under ice, wind too light, summer layer out of season.
- Dialog: Escape closes only the top layer (Build 4: the Learn guide, the 3D view, the search box, then the lake), Tab stays inside, buttons and layer rows at least 44 px; closing frees the 3D memory.
- Works with no signal: the add-on, the 40 lakebed files (1.37 MB) and the boating rules are saved on the first visit.

## All the guide's waters (Build 5 Stage 2)
- 286 lakes, reservoirs and ponds the 2026 guide's tables name that the stocking reports never list (data/waters_unstocked.json, built by scripts/waterbodies.py), each with its own rule row from the guide, its height, Bite and Day out, forecast, winter guard and ice estimates. Positions: the guide's land location (61), a lake outline in Canada's CanVec 1:50,000 water data (169, which also gives the size), or Canada's place names (56). Names that could not be placed with confidence (42 lakes, 10 rivers) are listed in data/waters_review.csv, not on the map. A guide lake that is already on the map as a stocked lake (same water, same or close name) is left as it is; its guide row is attached through data/regs_aliases.csv where the stocked lake has a zone.
- Fish and stocking says "Not stocked. Alberta's stocking reports 2011–2026 do not list this water."
- 91 river and creek stretches on 85 named waters (data/rivers.json), drawn as thin blue lines (wider when open), with every guide row for the stretch ("See each part below" when the parts have different seasons). Each stretch is cut at its zone's edge from Alberta's zone outlines (decision 18 A). A forecast spot about every 25 km (351 spots), each with its own height; the spot with the best day of the week stands for the stretch and the panel names it. Limits: "found" (Red Deer River from the Dickson Dam to the Tolman Bridge), "approximate" (by a named place), "unit" (the river in that part of the guide, edges estimated), "estimated" (a road or park limit the maps could not place). No 3D on rivers. "River stretch" section with the guide's words and a "Reading a river" link; list and search rows say "river: <start of the guide's words>". Kananaskis and Medley Rivers keep their stocked pin, with the line added.
- 3D depth model on 114 lakes (71 of them new), all lakebed files saved on the first visit (4.0 MB, was 1.37 MB).
- Filters: "Stocking" with Stocked and Not stocked (both on at the start). A water that is not stocked passes years and size, and is left out only for a species choice or a recent-stocking filter. A water without rules is never hidden by a season or bait filter. Zone view counts stocked lakes only and hides river lines.
- Distance to a river stretch is to its nearest forecast spot.
- Weather: spots within 200 km of you load first (fewer than 250 calls from Red Deer; the whole province is under 600); a new home or a picked town loads the spots near it; spots on screen load when the map is zoomed in to about 200 km across; a lake panel loads its own forecast; the data quality line counts the calls.
- Credits: Natural Resources Canada place names (CGNDB) and CanVec 1:50,000 Hydro, Open Government Licence – Canada, in the data quality panel and in both data files.
- Fishing zones of stocked lakes (owner's request, 2026-11-05): from Alberta's sportfishing regulations map (scripts/lake_zones.py → data/lake_zones.csv: the lake by its Alberta waterbody number, else the zone outline at its position). A lake takes that zone where it had none (58 lakes, e.g. Headwall, Memorial, Running Rain, Wabamun, Lower Kananaskis) or where the guide names it in that zone against its profile (14, e.g. Pine Coulee Reservoir PP2 → ES1, Lake Newell and Brooks Aquaduct Pond → PP1). A zone answered in data/lake_facts.csv is never replaced (Emerald (Hart) Lake ES1 and Dormer Lake ES2 corrected there by the owner). Stocked lakes with guide rules: 316 → 363; without: 69 → 19 (Morinville Lake and Niton Pond have no position or number).
- The guide's put-and-take list is read with each entry's watershed unit, and one printed line is read left to right, so two columns no longer merge (Kramer Pond, Innisfree Trout Pond, Jack Fish Lake, Michichi Reservoir now carry the put-and-take rules).

## Map and finding a lake
- Every river stretch is drawn (phone check after Stage 2: 15 stretches drawn as one long line, both Red Deer River stretches below the Dickson Dam among them, were skipped), with an invisible 20 px tap line on top of the 3 px line.
- The picked day on the week bar is white with dark text; home is a house in a white ring. Neither is orange any more, so neither reads as a gold "Best" pin.
- Pins cluster when zoomed out and split as you zoom in; hover shows name, score, distance, fish in view and last stocking date.
- One "Map ▾" button on the map (Build 5) opens a small menu: Topo, Street, Satellite, Zoom to results, Copy link. A pick, a tap outside or Escape closes it.
- "Zoom to results" fits the lakes the filters leave; "Copy link" copies a URL that reproduces every filter, home, the picked day, the town and the list.
- Zone view ranks Alberta's ten fish management zones by fish stocked.
- Basemaps: Topo, Street, Satellite.

## Filters (Filters button; a column on a wide PC, a slide-over below 1024 px)
- Stocking: Stocked, Not stocked (lakes) and Rivers, each its own switch (URL st, ns, rv). Rivers ignore the species and "stocked recently" filters. Below 1024 px a "Show N waters" button at the bottom closes the panel. Every control is at least 44 px; text two sizes up (phone check after Stage 2).
- Stocked recently: 30, 60, 90 days, or this season.
- Species: nine (rainbow, brook, brown, tiger, cutthroat, westslope cutthroat, walleye, northern pike, Arctic grayling).
- Fish size: under 15 cm, 15 to 20 cm, catchable 20 cm and over.
- Distance from home (or the picked town): your location, a picked point or Red Deer; slider 0 to 1000 km with a screen-reader label.
- Years 2011 to 2026 with All / None / Last 5 / Latest; a year marked * is in progress.
- Season and ice: Open today; Open for ice fishing (open all winter, early ice, late ice: 303 lakes); Aerated; Bait ban.
- A lake not matched to the regulations is never hidden by a season or bait filter.
- Filters button (Build 4): the number counts only the filters you changed; the default years are listed but not counted. A row of chips at the top of Filters names every filter that narrows the map, with ✕ to remove it. The Alberta notices have their own ⚠ count.
- "Has a 3D depth model" filter (Build 4, 43 lakes); list rows and the hover card show a "3D" mark.
- Learn links (Build 4): small "?" links in the lake panel open the guide for the term (scores, barometer, ice safety, stocked sizes, species, winterkill, 3D model, boating rules).

## Lake panel (was the lake popup)
- Bait ban: filled red badge at the top when the guide lists a bait ban.
- Ice season line: all winter / early ice only / late ice only / closed, with "Legal is not safe. Ice thickness is never forecast."
- Aerated tag on every stated-aerated lake (24), with or without a known depth; red thin-ice warning October to April, at the top of the panel. The extra "kept aerated so trout survive the winter" row is gone (Build 5).
- Rules-year warning (Build 5): from 1 April after the guide year, "Rules shown are from the 2026 guide; check the 2027 guide" at the top of the panel and in Rules, until the data is refreshed (README steps).
- Sections start closed (Build 5), in the owner's order (phone check after Stage 2): Rules, Fish and stocking, Lake info, How to fish (River stretch and Hot spots after it), Ice hatches and tackle, Tip and status, Forecast, Bite by hour, Getting there. "Bait Ban" (owner's spelling) is red in the Rules title and in the Rules block's Bait row; the badge, the filter chip and the list rows say "Bait Ban" too.
- Stocking summary, last stocked with size, years, "Usually stocked" (Build 5: months used in at least 60% of the stocked years 2011–2026, with counts, e.g. "May (14 of 16 years)"; under 3 stocked years "Too few years to tell"; 282 of 382 lakes have a usual month), species, change versus last year, the stocking table.
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
- Works offline after the first visit (service worker, shell cache v9, the guide's waters and rivers, saved town list, saved forecasts, lake heights, depth chart links, hot spots, the 3D depth model with its lakebed files and boating rules).

## Data and honesty
- Estimated positions are labelled; data quality panel; evidence page (evidence.html).
- Alberta advisories (closures, consumption) collected daily and shown in Filters.
- ACA aeration roster with ACA's Winter Angling column; a test fails if it disagrees with the regulations.
- Colour-blind-safe pin palettes; every score pin carries its number.
- Credit lines: Open-Meteo (CC BY 4.0), town list licence, GeoNames via Open-Meteo, Esri imagery, photo credits, Alberta Geological Survey (depth charts), Open-Meteo elevation with Copernicus DEM (in the ice inputs). The 3D view footer and its Learn guide carry the Open Government Licence – Alberta line, Transport Canada TP 15587E (not the official version), MyWildAlberta, Open-Meteo and three.js (MIT).

## Regression table — manifest v8 → v9 (Build 5 Stage 2 river edges)
| Feature | v8 → v9 | Note |
|---|---|---|
| River stretches | changed | cut at Alberta's zone outlines, not the nearest stocked lakes: 86 → 91 stretches (Redwater, Muskwa, Nipisi Rivers, Birch and Sunday Creeks added), 24 change length; Red Deer River below the Dickson Dam keeps "found" |
| River forecast spots | changed | 318 → 351, each with its own height; near Red Deer 161 → 164 weather cells |
| Weather calls | kept | still near home or on screen, paced at 550 a minute; the whole province is 615 cells (two minutes if panned over all of it) |
| Review file | changed | 5 rivers leave it (now placed) |
| Lakes, rules, stocking, panel, 3D, filters | kept | |
| Offline | kept | shell cache v10 (data files only) |

## Regression table — manifest v7 → v8 (Build 5 Stage 2 phone-check fixes)
| Feature | v7 → v8 | Note |
|---|---|---|
| River lines | changed | all 86 stretches drawn (71 before); 20 px tap line (91 after the river edges, v9) |
| Stocking filter | changed | plus Rivers; rivers no longer hidden by Not stocked, species or recency |
| Lake panel sections | changed | owner's order, Rules first; red "Bait Ban" wherever the app shows it |
| 3D tap | changed | depth under the finger; markers only within 16 px |
| 3D colours | changed | by metres, 0–20 m, same on every lake |
| 3D drag | changed | one finger moves, two fingers turn; Learn guide unchanged |
| Depth of waters not stocked | added | from their lakebed survey |
| Picked day, home marker | changed | white day, house symbol |
| Filters | changed | Show N waters button; 44 px controls; text a size up |
| Text sizes | changed | owner asked twice for bigger: labels at least 14 px; panel text 17 px; section titles 18 px; rules block 16 px |
| Bite and Day out, forecast, rules data, stocking data | kept | |
| Offline | kept | shell cache v9 → v10 |
| River edges (decision 18 A) | follow-up | not in this change: Open-Meteo refused heights all day 11-05 (daily limit); done in v9 |

## Regression table — manifest v6 → v7 (Build 5 Stage 2)
| Feature | v6 → v7 | Note |
|---|---|---|
| Stocked lakes, pins, clusters, hover | kept | 382 lakes unchanged; plus waters not stocked and river lines |
| Bite and Day out, banner, Why, tip | kept | same engine for every water; rivers use their best spot |
| Best near you | kept | 100 / 200 km / all steps unchanged (checked after a name clash was fixed) |
| Filters | kept | plus Stocking: Stocked / Not stocked |
| Rules | kept | waters not stocked carry the guide's row; 47 more stocked lakes carry theirs (zones from Alberta's regulations map) |
| Fishing zone of a stocked lake | changed | 58 filled, 14 corrected where the guide agrees; owner's saved answers win |
| 3D depth model | kept | 43 → 114 lakes; offline lakebeds 1.37 → 4.0 MB |
| Weather calls per load | changed | near you first, on screen when zoomed in; a new home loads near it |
| Zone view | kept | counts stocked lakes only; river lines hidden there |
| Lake heights | kept | plus new lakes and river spots |
| Offline | kept | shell cache v8 → v9, two new data files |

## Regression table — manifest v5 → v6 (Build 5 Stage 1)
| Feature | v5 → v6 | Note |
|---|---|---|
| Week bar, Best near you, PC column, nav | kept | |
| Bite and Day out scores, weights | kept | unchanged; no score without a forecast (list, pins and hover already had none) |
| Best-day banner, 7 bars, Why | kept | open at the top as before (owner's choice); no forecast shows "Needs a forecast" and no bars |
| Daily tip and stocked / open / winterkill line | kept | in the "Tip and status" fold |
| Tags | changed | short words, all one size; full words on tap |
| Aerated badge row | intentionally removed | W2: the Aerated tag and the thin-ice warning stay |
| Thin-ice warning | kept | |
| Estimates "From: …" | kept | behind ⓘ |
| Bite by time of day | kept | renamed "Bite by hour"; no score without a forecast |
| Forecast and Rules sections open at the start | changed | closed; the bait ban badge stays at the top |
| Map buttons Topo, Street, Satellite, Zoom to results, Copy link | kept | in the Map menu |
| Usually stocked | added | Fish and stocking |
| Rules-year warning | added | from 1 April 2027 |
| Day bars and "Next 6 h / 7 days" tap size | changed | 44 px (were 40–43 px and 25 px) |
| Offline | kept | shell cache v7 → v8 |
| Charts, list view and CSV, favourites, search, towns, 3D, Learn | kept | |

## Regression table — manifest v4 → v5 (Build 4)
| Feature | v4 → v5 | Note |
|---|---|---|
| Week bar, Best near you, PC column, nav | kept | the week bar and the panel's day bars share one day setter |
| Bite and Day out scores, weights | kept | unchanged; ice-forming days get no score |
| Best-day banner, 7 bars | kept | bars are now buttons; ice-forming and usual-ice lines |
| Why this score | kept | plus the day-against-today line |
| Daily tip | changed | "normal depths" replaced by the lake's depth range |
| Estimates, How to fish | kept | plus lakebed shapes on surveyed lakes |
| Lake info depth rows | changed | 18 lakes gain a survey max depth; survey mean replaces estimates on surveyed lakes |
| Filters | kept | plus chips, changed-filter count, ⚠ notices, 3D filter |
| Advisory count on Filters | changed | now its own ⚠ sign, no longer the plain number |
| 3D view | kept | plus fish depth layer, shore directions, credit line no longer repeats the survey name |
| Escape | changed | closes one layer at a time (bug fix) |
| Learn room | kept | 3D guide rewritten with the sample model; river guide added |
| Offline | kept | shell cache v6 → v7 |
| Charts, list view and CSV, favourites, search, towns | kept | |

## Regression table — manifest v3 → v4 (Build 3)
| Feature | v3 → v4 | Note |
|---|---|---|
| Week bar, Best near you, PC column, nav, Only lakes on screen | kept | |
| Bite and Day out scores, banner, Why this score | kept | forecast gains wind direction only; scores do not use it |
| Pin colour modes, score scale | kept | |
| Forecast tabs, feeding times, tip | kept | |
| Winter guard, winter list, winter score | kept | |
| Estimates (ice, hatches, turnover, tackle, how to fish) | kept | the ice state is reused by the 3D view |
| Depth chart row | kept | plus "Show 3D depth model" on the 43 lakes |
| Hot spots section | kept | its spots also show as pins in 3D |
| Learn room | kept | plus the 3D depth model guide; a topic can open at a section |
| Search, towns, messages, satellite, links | kept | |
| Filters, charts, list view and CSV, favourites, advisories | kept | |
| Offline | kept | shell cache v5 → v6, forecast copies v1 → v2 |
| Weather calls per full load | kept | 10 variables per call (Open-Meteo's limit), so a call still counts once |
| 3D depth model | added | Build 3 |

## Regression table — manifest v2 → v3 (Build 2)
| Feature | v2 → v3 | Note |
|---|---|---|
| Week bar, Best near you, PC column, nav, Only lakes on screen | kept | |
| Bite weights and gust rule | kept | tested unchanged |
| Bite score values | kept, moved a little | water estimate now uses the lake's height; see the table below |
| Day out, best-day banner, Why this score | kept | |
| Pin colour modes, score scale | kept | |
| Forecast tabs, feeding times, tip, clearing reminder | kept | |
| Winter guard, wind-chill week bar, ice pins, "Ice likely" | kept | banner adds the winter score and a cold note |
| Winter list "Ice season lakes near …" | changed | now "This winter near …": ice-season and aerated lakes first, winterkill band, winter score (D14) |
| Winter list rows showed "ice" | changed | show the winter score; "ice" only when there is none |
| Tags, stocked size, typical size not guessed | kept | |
| Search, towns, messages, Learn room, satellite, links | kept | |
| Lake panel sections | kept | plus "Ice, hatches and tackle", "How to fish this lake", Depth chart row, Hot spots (only with spots) |
| Filters, charts, list view and CSV, favourites, advisories | kept | |
| Offline | kept | shell cache v4 → v5 |
| Weather calls per full load | kept | 250 calls in 5 requests (measured again) |

Bite score before and after the lake height (measured 2026-11-03 evening, Edmonton time; the 5 lakes that moved most; 181 of 380 lakes moved at least 1 point on some day of the week; the median air correction is 0.3 °C, the largest 5.7 °C):

| Lake | Forecast spot / lake height | Air correction | Water before → after | Bite today before → after |
|---|---|---|---|---|
| Upper Kananaskis Lake | 2436 m / 1702 m | +4.8 °C | 2.2 → 3.8 °C | 58 → 67 |
| Crowsnest Lake | 2028 m / 1347 m | +4.4 °C | 2.5 → 4.2 °C | 59 → 68 |
| Island Lake | 2028 m / 1353 m | +4.4 °C | 2.5 → 4.1 °C | 59 → 68 |
| Sparrows Egg Lake | 2202 m / 1641 m | +3.6 °C | 2.9 → 4.3 °C | 61 → 69 |
| Grotto Mountain Pond | 1730 m / 1290 m | +2.9 °C | 3.6 → 4.9 °C | 61 → 68 |

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
