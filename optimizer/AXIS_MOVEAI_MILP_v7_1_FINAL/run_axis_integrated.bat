@echo off
REM AXIS v7.1 - Step 2. Joint Multi-Carrier MILP (one-shot)
REM   -> Carrier Recommendation + KORAIL Integrated Train Operation Plan
REM Scenario assumption, NOT a KORAIL official standard:
REM   min-load-factor 0.5 / max-earliness 72h / time-limit 900s
cd /d "%~dp0"
python 02_CODE\axis_milp_v7_1.py ^
  --hourly 03_INPUT_DATA\AXIS_carrier_hourly_plan_v7_1.csv ^
  --initial 03_INPUT_DATA\carrier_initial_inventory.csv ^
  --params 03_INPUT_DATA\AXIS_rail_OD_parameters_v1.xlsx ^
  --candidates 04_MODEL_INPUTS ^
  --root 05_RESULTS --scenario AXIS_INTEGRATED ^
  --min-load-factor 0.5 --max-earliness 72 --time-limit 900 ^
  --strict-lexicographic
