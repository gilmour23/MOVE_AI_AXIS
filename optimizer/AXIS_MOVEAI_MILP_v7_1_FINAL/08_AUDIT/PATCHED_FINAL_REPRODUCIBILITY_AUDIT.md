# AXIS MOVE-AI MILP v7.1 patched final reproducibility audit

Date: 2026-08-10 (Asia/Seoul)

## Completed reruns

1. Static compilation of core, baseline, sensitivity, role-tilt, test, and
   verification modules: pass.
2. Canonical 72-hour AXIS Integrated solve using `04_MODEL_INPUTS`, LF 0.5,
   900 seconds per stage, and strict lexicographic mode: completed.
3. Canonical solver audit: 7/7 stages status 0 and requested gap 0.
4. A/B/C baseline suite using the same carrier data, candidate directory,
   parameters, LF, earliness, and handling assumptions: completed.
5. External candidate core run and baseline run: completed; candidate file hashes
   remained unchanged before and after both runs.
6. Fast final assertions for input validation, candidate validation, actual-time
   preservation, view consistency, KPI consistency, and input hashes: pass.

## Canonical evidence

- Service need: 180 TEU.
- Rail served: 138 TEU.
- Selected trains: 3.
- Exactness: `EXACT_ALL_STAGES`.
- Same-solution check: 138 = 138 = 138 = 138 TEU across recommendation,
  allocation, service-need result, and train-plan totals.
- Candidate input sources: `PROTOTYPE_SYNTHETIC`.
- Carrier data source: synthetic carrier-level data.

## Input fingerprints

Baseline metadata records the absolute candidate directory, 1,084 candidate trains,
SHA-256 for all four candidate CSVs, and SHA-256 for the parameter workbook.
The baseline-C and canonical KPI sets match.

## Fast-path limitation

At the user's request, the long-running exhaustive sensitivity, role-tilt, and
full verification reruns were stopped after canonical and baseline completion.
Partial outputs are archived under `08_AUDIT/dev_runs` and are not presented as
final results. The interrupted broad regression record is also archived; its
107/108 result is not claimed as a full pass. See
`05_RESULTS/VALIDATION/FAST_PATH_VALIDATION.md`.

