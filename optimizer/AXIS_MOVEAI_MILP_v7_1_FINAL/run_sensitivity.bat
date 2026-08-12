@echo off
REM AXIS v7.1 - Step 4. Earliness / load factor / handling time sensitivity
cd /d "%~dp0"
python 02_CODE\axis_sensitivity_v7_1.py ^
  --hourly 03_INPUT_DATA\AXIS_carrier_hourly_plan_v7_1.csv ^
  --initial 03_INPUT_DATA\carrier_initial_inventory.csv ^
  --params 03_INPUT_DATA\AXIS_rail_OD_parameters_v1.xlsx ^
  --root 05_RESULTS\SENSITIVITY ^
  --base-earliness 72 --base-lf 0.5 --base-handling 3 --time-limit 900
