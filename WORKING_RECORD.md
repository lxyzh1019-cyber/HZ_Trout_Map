# WORKING RECORD — HZ_Trout_Map — rules v2

Single working record for this repository. Updated by the main session at the end of every implementation turn (the record guard hook checks this). Keep it terse; history lives in git.

## Approved baseline
- Plan v1 (plans/first-switch-to-the-purrfect-gizmo.md, Build 1a rest) approved 2026-10-13:
  1. Ice chip also shows early-ice and late-ice lakes
  2. Ice-season line in every popup (fifth line for the three Apr 1–Nov 30 lakes)
  3. Ice wording "Legal is not safe. Ice thickness is never forecast."
  4. Red Bait ban line in the popup for the 25 bait-ban lakes
  5. Bait ban chip, built like the Aerated chip
  6. Popup close button stays clear of the top-right map buttons
  7. README: 35 walleye and pike waters shown, nine species, with a counting test
  8. Slider label for screen readers
  9. Winter guard "Ice likely" (7 past daily means below 0 °C), today and each day of the 7-day view
  Kept: design file features of commit 1798292 (Aerated badge and filter, thin-ice warning Oct–Apr, "Season and ice" filter group, ACA winter angling column, Spring Lake note, split-season fix)

## Pending
- None

## Design decisions
- [agreed] The ice chip "Open for ice fishing" also shows early-ice and late-ice lakes, not only all-winter lakes — search: early-ice and late-ice lakes
- [agreed] Every popup has an ice-season line; the three Apr 1–Nov 30 lakes get the fifth line "Early and late ice — closed Dec 1 to Mar 31" — search: Early and late ice — closed Dec 1 to Mar 31
- [agreed] Ice wording in the popup and the winter guard: "Legal is not safe. Ice thickness is never forecast." — search: Legal is not safe
- [agreed] A red Bait ban line at the top of the popup for the 25 bait-ban lakes — search: red Bait ban line
- [agreed] A Bait ban chip, built like the Aerated chip — search: Bait ban chip
- [agreed] The top-right map buttons never cover the popup close button; the popup close button stays clear — search: popup close button stays clear
- [agreed] README: walleye and pike waters are shown; 35 walleye and pike waters (33 walleye, 1 pike, 1 both) from the data, with a test that counts the data and checks the README number; the species filter has nine species — search: 35 walleye and pike waters
- [agreed] The distance slider gets a slider label for screen readers — search: slider label for screen readers
- [agreed] Winter guard: when every daily mean in the past 7 days before the chosen time is below 0 °C, hide the open-water score and show "Ice likely"; applies to today and to each day of the 7-day view — search: Ice likely
- [agreed] Picture references are made in this session only; the picture tool is not added to the GitHub check — search: picture references
- [agreed] The design file features of commit 1798292 are kept as they are: Aerated badge and filter, thin-ice warning Oct–Apr, "Season and ice" filter group, ACA winter angling column, Spring Lake note, split-season fix — search: design file features kept
- [agreed] One pull request for all of Build 1a, opened ready (not draft) after the reviewer; the owner merges — search: one pull request

## Request ledger
| # | Round/date | Requirement (user's words, short) | Status | Note |
|---|---|---|---|---|
| 1 | Plan v1 / 2026-10-13 | Ice chip includes early-ice and late-ice lakes | open | stage 3 |
| 2 | Plan v1 / 2026-10-13 | Ice-season line in every popup | open | stage 3 |
| 3 | Plan v1 / 2026-10-13 | Ice wording and winter guard text | open | stage 3 |
| 4 | Plan v1 / 2026-10-13 | Red Bait ban line in popup | open | stage 5 |
| 5 | Plan v1 / 2026-10-13 | Bait ban chip | open | stage 5 |
| 6 | Plan v1 / 2026-10-13 | Popup close button clear of top-right buttons | open | stage 5 |
| 7 | Plan v1 / 2026-10-13 | README counts: 35 walleye and pike waters, nine species | open | stage 4 |
| 8 | Plan v1 / 2026-10-13 | Slider label for screen readers | open | stage 5 |
| 9 | Plan v1 / 2026-10-13 | Winter guard Ice likely | open | stage 3 |
| 10 | Plan v1 / 2026-10-13 | Design file features kept | open | kept as they are; stage 5 checks |

## Hotspot counter
| Area / feature | Fix rounds | Recurrences | Regressions caused | Workarounds/exceptions | Last symptom | Rewrite-vs-repair reviewed? |
|---|---|---|---|---|---|---|
| | 0 | 0 | 0 | 0 | | no |
Thresholds: 3 fix rounds, 2 recurrences, 1 regression caused by a fix, or 3 workarounds/exceptions → no further patch until the rewrite-vs-repair comparison is presented; then set the last cell to "yes <date>". The hooks read this table: keep the header words.

## Deliverable ledger
| Deliverable | State | Evidence |
|---|---|---|
| Stage 2 — picture tool and 18 baseline pictures | DONE | tests/pictures.py before then after + compare: 0 of 18 differ; Proof: pictures 6 screens × 3 sizes × 1 looks, 0 changed; popup deep link ?lake=wb6770 (Kerbe's Pond, bait ban, aerated) |
| Stage 3 — ice season logic and winter guard | DONE | iceSeason/iceLikely in js/conditions.js, Ice row + chip predicate in index.html, Ice likely block and grid days in js/conditions-ui.js, 4 new tests; class counts read all-winter 297 / early 1 / late 2 / early-late 3 / closed 6 (plan said 298); unittest discover 175 passed; pictures 7 of 18 differ, all planned (Ice row in popup-ipad and lake-panel-* which show the open popup; Ice likely in conditions-freeze-*) |
| Stage 4 — README counts, counting test, cache name | NOT STARTED | |
| Stage 5 — bait ban, popup close, slider label, pictures | NOT STARTED | |
| Stage 6 — review, full tests, one pull request ready | NOT STARTED | |

## Checks and evidence
- 2026-10-14 stage 2 picture tool: two runs (before, after) compared, 0 of 18 pictures differ; python3 scripts/test_regression_checks.py passed (47 tests)
- 2026-10-14 stage 1 records written (FEATURES.md, WORKING_RECORD.md); no code changed → python3 scripts/test_regression_checks.py passed (47 tests)

## Open questions / blockers
- None

## Where we are
- Stage 1 (records) done. Next: stage 2 (picture tool, opus-worker). Branch test-with-config.
