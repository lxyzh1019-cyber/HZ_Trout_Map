# Build 5 — to-do list for Claude Code (HZ_Trout_Map)

Owner: Master H. Written 2026-11-04 from the chat review of the live app (main at 922ddb0).
Work through the stages in order, one PR per stage, each opened only when ready. Stop only for the owner's merge and for the owner questions marked ASK.

## Every stage
- All tests pass; layout check at 5 sizes (phone 360 and 390, iPad 834 and 1194, PC 1280) with no faults.
- Any change to what the owner sees: show before and after screenshots side by side and get the owner's OK before the PR is marked ready.
- Update FEATURES.md (with a regression table) and WORKING_RECORD.md (request ledger, checks).
- Windows line endings (CRLF) for files the owner may edit.
- Final report: what was done, decisions, deviations, results with counts, slowest or unneeded steps, and the updated BC Trout Finder comparison table.

## Stage 1 — Fewer words, one misleading screen (PR 1)
Measured on the live app, Beaver Lake panel at 390 px with no forecast: 254 words visible, 853 with sections open, 9 sections, 1475 px tall.
- [ ] W1 No forecast: show no scores and no 7-day bars; say "Needs a forecast". Today the banner says "No forecast yet" but the bars show 96–98 "Best".
- [ ] W2 Aeration: keep the Aerated tag and the red thin-ice warning; remove the extra "AERATED kept aerated so trout survive the winter" row.
- [ ] W3 Map buttons: replace the 5 large buttons (Topo, Street, Satellite, Zoom to results, Copy link) with one "Map" button that opens them as a small menu.
- [ ] W4 One answer line at the top of the lake panel, for example "Go Thu 82 · calm · 07:40–09:40 · leech, 3 m"; everything else stays folded.
- [ ] W5 Short tags ("8 reports" instead of "Popularity estimate: 8 angler reports"); full wording on tap.
- [ ] W6 Move each estimate's "From: …" list behind a small ⓘ.
- [ ] Target: at most 60 words on the panel's first phone screen; report the before and after counts with the same method (visible innerText words of the panel at 390 px).
- [ ] Rules year check: data/lake_regulations.json has guide_year 2026, valid to 31 Mar 2027. From 1 Apr 2027 show a banner "Rules shown are from the 2026 guide; check the 2027 guide" until the data is refreshed. Add the refresh steps to the README.
- [ ] "Usually stocked" line in Fish and stocking, from the 2011–2026 reports: months used in at least 60% of the lake's stocked years, with counts, for example "Usually stocked: May (14 of 16 years) · Sep (7)". Lakes with fewer than 3 stocked years say "Too few years to tell". Expected about 282 of 382 lakes with a usual month.

## Stage 2 — Score all lakes, not only stocked ones (PR 2)
- [ ] Add the waterbodies named in the 2026 regulation tables (data/raw/alberta-sportfishing-regulations-2026-tables.pdf; a rough count found about 470 lakes, reservoirs and ponds). Must include Gull Lake, Pigeon Lake and Sylvan Lake. Glennifer did not match by that name; find how the guide lists it.
- [ ] Rivers (owner's decision D30 A): add every river the 2026 guide tables name (a rough count found 79 rivers, for example Red Deer, Bow, Oldman, North Saskatchewan, Battle, Athabasca). Split each river into the stretches the guide uses (its own "from … to …" limits), each with its own rules. Must include the Red Deer River below the Dickson Dam.
- [ ] River lines from Canada's official water data (National Hydro Network or CanVec, Natural Resources Canada); confirm the licence and add a credit line. Each stretch gets a forecast spot about every 25 km (at least one per stretch), Bite and Day out scores, ice estimates and its rules; no 3D for rivers.
- [ ] Spot matching for rivers: a spot within 300 m of a river line belongs to that stretch. Report how many of the owner's 218 pins match a lake, a river stretch, or nothing. ASK the owner for the file's path outside the repo; read it only, never copy it into the repo.
- [ ] Coordinates from Canada's official geographical names data (CGNDB, Natural Resources Canada). Confirm its licence and add a credit line. Label any estimated position, as today.
- [ ] Each new lake gets: Bite and Day out scores, forecast, winter guard, ice estimates, its own rules from the guide, the lake height, and 3D where Alberta has a depth chart. Stocking sections say "Not stocked" instead of being empty.
- [ ] Weather budget (lakes and river spots together): today 380 lakes use 250 calls per full load (free limit 600 a minute, 10,000 a day). Score lakes on screen or within 200 km first, and the rest when the owner pans to them. Measure and report calls per load.
- [ ] Filters: add "Stocked / Not stocked"; existing filters keep working; a lake without rules is never hidden.

## Stage 3 — My spots and species mode (PR 3)
- [ ] "Import my spots": the owner picks a file on each device; the spots are kept only in that browser (IndexedDB). Never write them into the repo, which is public.
- [ ] Accept Google Takeout "Saved Places.json", Takeout "Saved" list CSVs, Google My Maps KMZ (zipped KML), GeoJSON and KML. A CSV row with a "?q=lat,lon" link uses those coordinates; a row with only a place name is matched by name to a lake, else listed as "not placed".
- [ ] Leave out places in towns: a saved place with a street address that is more than 1 km from any lake is skipped (restaurants, shops). Show the count skipped.
- [ ] Match each spot to a lake by the lake's shoreline, not its centre point: inside the outline, or within 500 m of the shore. Where only a centre point exists, use a circle sized from the lake's area plus 1 km. Test case: the owner's Sylvan Lake spot (52.3321, -114.1462) is 5.5 km from the centre point and must still match Sylvan Lake.
- [ ] Keep each spot's note and tags. The owner's Google list names become tags (Walleye, Whitefish, Perch, Pike, Carp, Sturgeon, Trout, Big Rainbow and others); his list "Fishing spot (need to validate)" becomes the tag "Unconfirmed" and shows as a hollow marker.
- [ ] Named places without a pin (340 in his file, for example "Strubel Lake", "Hasse Lake") are matched to a lake by name and show as "Saved lake" on that lake; names with no Alberta match (many are in BC) are listed as "not placed".
- [ ] Show each spot in the lake panel ("My spots") and as a marker in 3D. A spot that matches no lake is listed under "Spots not on a lake".
- [ ] Test file: the owner's private file my-spots-private.geojson (558 places: 218 pins, 340 named places) is NOT in the repo; use a made-up sample with the same shape for the tests.
- [ ] Species mode: a switch for trout (today's model), walleye, burbot and whitefish. Each changes the Bite weights and the "How to fish" text: walleye favour low light and dusk; burbot favour night and winter under ice; whitefish favour winter in shallow water over mud. Every species score says "estimated" and lists what it used.

## Stage 4 — Saved lakes on every device, weekly email (PR 4)
- [ ] ASK the owner which Firebase project to use before creating anything. Sign-in, then saved lakes and imported spots sync privately across his devices.
- [ ] Weekly email (at most once a week) when a saved lake has a top day in the next 7 days, or a new stocking report lists a saved lake. ASK the owner which email service and address to use; keep any key out of the repo (GitHub secret).
- [ ] Without sign-in the app works exactly as today.
