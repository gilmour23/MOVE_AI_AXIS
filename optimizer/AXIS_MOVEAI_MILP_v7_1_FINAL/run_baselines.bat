@echo off
REM AXIS v7.1 - Step 3. Research baselines
REM   A No Repositioning / B Carrier Separate / C AXIS Integrated
cd /d "%~dp0"
python 02_CODE\axis_baselines_v7_1.py ^
  --hourly 03_INPUT_DATA\AXIS_carrier_hourly_plan_v7_1.csv ^
  --initial 03_INPUT_DATA\carrier_initial_inventory.csv ^
  --params 03_INPUT_DATA\AXIS_rail_OD_parameters_v1.xlsx ^
  --root 05_RESULTS\BASELINES ^
  --candidates 04_MODEL_INPUTS ^
  --min-load-factor 0.5 --max-earliness 72 --time-limit 900
