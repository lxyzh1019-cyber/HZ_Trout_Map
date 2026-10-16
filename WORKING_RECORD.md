# WORKING RECORD — HZ_Trout_Map — rules v2

Single working record for this repository. Updated by the main session at the end of every implementation turn (the record guard hook checks this). Keep it terse; history lives in git.

## Approved baseline
- Plan v1 Rev 2 approved 2026-10-16 (Build 1a rest, all decisions option A), on top of the design file commit 1798292:
  1. Ice filter keeps early, late and both; hides only "closed"; unread stays.
  2. Ice season line on every popup (incl. "not known — check the regulations").
  3. "Legal is not safe. Ice thickness is never forecast." where ice fishing is legal.
  4. Red "Bait ban" line in the popup.
  5. "Bait ban" chip in the Season and ice row, URL `bait=1`.
  6. Popup × clear of the top-right buttons (built first).
  7. README: walleye/pike-only waters shown, count from data (35), 9 species, test.
  8. Distance slider aria-label "Maximum distance from home".
  9. "Ice likely" when all 7 forecast daily highs are below 0 °C.

## Pending
- None.

## Request ledger
| # | Round/date | Requirement (user's words, short) | Status | Note |
|---|---|---|---|---|
| 1 | 2026-10-16 | Build 1a rest, 9 items, Plan v1 Rev 2 | done | commit on test-333-local, not pushed |

## Hotspot counter
| Area / feature | Fix rounds | Recurrences | Regressions caused | Workarounds/exceptions | Last symptom | Rewrite-vs-repair reviewed? |
|---|---|---|---|---|---|---|
| | 0 | 0 | 0 | 0 | | no |
Thresholds: 3 fix rounds, 2 recurrences, 1 regression caused by a fix, or 3 workarounds/exceptions → no further patch until the rewrite-vs-repair comparison is presented; then set the last cell to "yes <date>". The hooks read this table: keep the header words.

## Deliverable ledger
| Deliverable | State | Evidence |
|---|---|---|
| 6 Popup clear of buttons | COMPLETE | PopupClearOfButtonsTests; not checked in a browser |
| 1 Ice filter (iceSeason) | COMPLETE | IceSeasonTests, RealJsTests |
| 2 Ice season line | COMPLETE | IceSeasonTests |
| 3 Legal-is-not-safe line | COMPLETE | IceSeasonTests |
| 4 Bait ban popup line | COMPLETE | BaitBanTests |
| 5 Bait ban chip + URL | COMPLETE | BaitBanTests |
| 7 README count + species | COMPLETE | ReadmeWalleyePikeCountTests |
| 8 Slider aria-label | COMPLETE | SmallBuildChecks |
| 9 Ice likely | COMPLETE | IceLikelyTests, RealJsTests |
| sw.js shell cache v4 | COMPLETE | SmallBuildChecks |
| FEATURES.md, WORKING_RECORD.md | COMPLETE | files filled |

## Checks and evidence
- 2026-10-16 local unittest discover → see commit report (openpyxl tests error locally: environment); node --check on js/*.js, sw.js and the inline script of index.html → passed. GitHub run and device check: untested.

## Open questions / blockers
- None. Merge and device check are the user's stops.
