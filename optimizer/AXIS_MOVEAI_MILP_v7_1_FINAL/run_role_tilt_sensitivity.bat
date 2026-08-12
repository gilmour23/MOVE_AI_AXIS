@echo off
REM AXIS v7.1 - Step 5. Synthetic carrier role-tilt sensitivity
cd /d "%~dp0"
python 02_CODE\axis_role_tilt_sensitivity_v7_1.py ^
  --master 03_INPUT_DATA\AXIS_hourly_empty_demand_supply_v8_6hubs.xlsx ^
  --snapshot 03_INPUT_DATA\public_snapshot_2026-08-09.csv ^
  --params 03_INPUT_DATA\AXIS_rail_OD_parameters_v1.xlsx ^
  --candidates 04_MODEL_INPUTS ^
  --out 05_RESULTS\SENSITIVITY\ROLE_TILT_SENSITIVITY.csv ^
  --tilts 0.55,1.10,1.65 ^
  --min-load-factor 0.5 ^
  --max-earliness 72 ^
  --time-limit 900
