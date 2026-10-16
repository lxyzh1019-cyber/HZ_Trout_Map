# Plan v1 — Build 1a rest: ice, bait ban, winter guard — Awaiting approval

**Quick read** · 234 words · about 2 min

**Summary**
- Goal: add the 9 items on top of your Build 1a design file, unchanged. Done when: all 9 show in the app and the full test run passes.
- Stages: 1 · lanes: 1 · stops for you: 1 · pull requests: 1.
- 🟩 **Rev 2** — I need from you: approve.

**What changed since v0**
- First version.
🎨 🟩 **Rev 2** marks 3 changed lines · 🟦 Rev 1

🟩 **Rev 2** — **Decisions:** None open. You chose A for all 3:
1. Three lakes are open Apr 1 to Nov 30. They have early ice and late ice, and are shut mid-winter. **A** Popup says "Early and late ice (shut Dec 1 – Mar 31)" (ends here) · **B** Force them into "early ice only" (brings back: wrong line in spring) · Recommend: A
2. The data has 35 walleye- or pike-only waters, not 36. **A** README says 35, and a test keeps the number equal to the data (ends here) · **B** Write 36 as asked (brings back: a wrong number) · Recommend: A
3. Lakes with no regulation record have no ice season. **A** Popup says "Ice season: not stated — check the Alberta guide" (ends here) · **B** No line for them (brings back: item 2 not on every popup) · Recommend: A

**Stops**
- Round 1: merge the pull request, then check on your phone (one lake popup, the filters, the Conditions panel).

**Limits**
- GitHub run about 3 min · one test run about 20 s · no picture tests (no reference picture given).

Stages to finish
1 stage: 1 build step by Claude, then 1 check (your merge and phone check)
1. Build all 9 items, tests, README, review · Claude · Build · files: index.html, js/conditions.js, js/conditions-ui.js, sw.js, README.md, tests · after: — · level: Routine · size: M · group: A · steps: 60 · proof: full test suite + node check of the season reader
2. 🟩 **Rev 2** — Merge and phone check · You · Check · stop: merge + device read

Technical details:
- Design file (commit 1798292) stays as is; only additions on top.
- Item 1: new `seasonIceKind(text)` in js/conditions.js → "all" (existing `seasonOpenAllWinter`), "early" (open Nov 30), "late" (open Apr 1), "both" (open Nov 30 and Apr 1), "closed", null. `lakePassesFilters`: ice chip keeps all/early/late/both, keeps null (as today), hides closed. Python twin `season_ice_kind` in scripts/test_regression_checks.py. Data: 1 early only (May 8–Nov 30), 2 late only (Apr 1–Oct 31), 3 both (Apr 1–Nov 30).
- Items 2–3: `iceSeasonBlock(lake)` in index.html popup next to `aerationBlock`: "Ice season: all winter / early ice only (to Nov 30) / late ice only (from Apr 1) / closed". When not closed, add "Legal is not safe. Ice thickness is never forecast."
- Item 4: `reg.bait === "Bait ban"` (28 lakes) → red line `Bait ban` first in popup, under the title.
- Item 5: chip `bait-chip` in "Season and ice", state `baitBan`, URL `bb=1`, same toggle loop as the design file.
- Item 6: popups (`bindPopup` lines 2482, 2554) get `autoPanPaddingTopRight` from the measured `.map-btns` width + 20 px, so the × never sits under the buttons.
- Item 7: README "Waters this map does not show" rewritten: walleye- and pike-only waters are shown (35); species list says 9 (line 593). Test counts the data.
- Item 8: `aria-label="Maximum distance from home"` and `aria-valuetext` updated on input.
- Item 9: js/conditions-ui.js `render()`: when all 7 forecast daily means (`dailyT`/`dailyMeanC` after today) are below 0 °C, hide verdict, strip/grid and factors; show "Ice likely. Open-water score hidden. Legal is not safe. Ice thickness is never forecast." Weather line and calendar stay. Pure helper `Conditions.weekBelowFreezing(means)` for the test.
- sw.js cache version bump. FEATURES.md: add test map lines only.
- Checks: `python -m unittest discover -p "test_*.py"` in scripts/; node run of the JS season reader against all 17 season wordings; one reviewer pass before the pull request.
