# FEATURES — <app or plan name> — manifest v1 — confirmed <date>

Locked features of the current version. Every edit is checked against this list and ends with a regression table. Update this file in the same change that alters a feature. Over-list rather than under-list.

## <Group, e.g. Data / sync>
- <feature or rule — one line, observable>
- …

## <Group, e.g. Screens / UI>
- …

## <Group, e.g. Rules / special cases>
- …

## Regression table format (paste at the end of every edit)
| Feature | v<old> → v<new> | Note |
|---|---|---|
| <feature> | kept / added / intentionally removed / missing | <why, if not kept> |

## References
- Tests: season reader, ice filter, ice-season line, bait ban, popup padding, slider label, winter guard (index.html, js/conditions.js, js/conditions-ui.js, js/weather.js) → scripts/test_regression_checks.py WinterSeasonTests, IceSeasonTests
- Tests: aeration badge and roster (index.html, data/aca_aeration_roster.csv) → scripts/test_regression_checks.py AcaRosterTests, AerationIsKnownPerLakeTests
- Tests: README counts (README.md, data/lakes_*.json) → scripts/test_regression_checks.py IceSeasonTests.test_readme_counts_match_the_data
- Tests: service-worker precache (sw.js) → scripts/test_regression_checks.py OfflineAssetTests
