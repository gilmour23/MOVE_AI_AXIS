# AXIS MOVE-AI MILP v7.1 patched final implementation audit

Date: 2026-08-10

## Implemented

- Canonical core module renamed to `02_CODE/axis_milp_v7_1.py`; active imports,
  tests, verification, normalizer, BAT files, and user documentation were updated.
- Canonical runners explicitly use `04_MODEL_INPUTS`; the integrated runner uses
  `--strict-lexicographic` with LF 0.5, 72-hour earliness, and 900-second stage limits.
- Baseline defaults now match 72/900 and validate carrier/candidate inputs before use.
- External candidate directories are validation-only and never regenerated or
  overwritten in either the core or baseline runner.
- Carrier validation requires all six AXIS hubs, both 20FT/40FT sizes, nonblank
  carrier IDs, nonempty files, continuous hourly grids, nonnegative integers,
  matching carrier sets, and complete initial inventory grids.
- `KORAIL_FEASIBLE_PATH` candidates require explicit `work_stops` and preserved
  minute-resolution `actual_*` timestamps.
- `Train` preserves actual load/arrival/departure/available timestamps separately
  from conservative model slots.
- User-facing train, stop, recommendation, and explanation outputs use actual
  timestamps. Audit columns expose `model_*_slot` and model timestamps separately.
- Candidate source metadata is split into `candidate_input_sources` and
  `selected_train_sources`; `candidate_timetable_source` is selected-source based.
- Revenue-facing output is standardized on `estimated_rail_charge_krw` and marked
  as a tariff-based estimate, not profit or operating revenue.
- `FINAL_TRAIN_OPERATION_SUMMARY.csv` was added with train, formation, capacity,
  assignment, load factor, carrier count, and 20FT/40FT box counts.
- `run_role_tilt_sensitivity.bat` was added and wired into `run_all.bat`.
- Policy examples, operations template, legacy audits, and the 48-hour development
  result were separated into their final package locations.

## Static audit

- Active stale references to the patched core name, legacy policy folder,
  result-side model-input folder, v7 core name, and v6.1 operations template: 0.
- Required BAT files and target Python files exist.
- BAT control-character scan: pass.
- Python compilation: pass.

## Scope note

The optimization structure was not changed: carrier ownership, joint capacity,
service needs, formations, segment distances, work/pass-through behavior, source
release, and the seven-stage lexicographic objectives remain intact.

