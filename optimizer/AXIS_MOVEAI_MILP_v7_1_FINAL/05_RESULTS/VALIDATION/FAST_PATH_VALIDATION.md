# AXIS v7.1 final fast-path validation

Date: 2026-08-10 (Asia/Seoul)

The user selected the fast completion path after the canonical and baseline
solves completed. No exhaustive sensitivity, role-tilt, or full verification
rerun is claimed.

## Passed checks

- Python compilation: all six required core/runner/test modules passed.
- Carrier input: 12,096 hourly rows and 72 initial rows accepted.
- Canonical candidate validation: 1,084 trains accepted.
- External KORAIL fixture validation: 2 trains accepted.
- External actual-time preservation: 06:35 departure and 09:40 arrival preserved.
- Canonical solver: 7/7 stages status 0 with requested MIP gap 0.
- Canonical exactness: `EXACT_ALL_STAGES`, strict lexicographic enabled.
- Same-solution totals: recommendation = allocation = served need = train total = 138 TEU.
- Baseline C matches canonical KPIs and uses identical candidate SHA-256 hashes.
- Stale active-package references: 0.
- BAT control characters: 0 files affected.

## Archived incomplete runs

- `08_AUDIT/dev_runs/REGRESSION_TESTS_v7_1_INTERRUPTED.csv`: 107/108 checks
  passed; the fifth resource-heavy determinism subprocess did not complete.
  Four preceding identical repetitions had completed before that failure.
- `08_AUDIT/dev_runs/SENSITIVITY_PARTIAL_FAST_PATH_20260810`: partial results
  stopped at the user's request and not presented as final sensitivity results.

