@echo off
REM AXIS v7.1 - optional. Carrier pre-submitted inventory policy input
cd /d "%~dp0"
python 02_CODE\axis_milp_v7_1.py ^
  --hourly 03_INPUT_DATA\AXIS_carrier_hourly_plan_v7_1.csv ^
  --initial 03_INPUT_DATA\carrier_initial_inventory.csv ^
  --params 03_INPUT_DATA\AXIS_rail_OD_parameters_v1.xlsx ^
  --policies 06_POLICY_EXAMPLES\POLICY_MIN_INVENTORY_RANGE.json ^
  --candidates 04_MODEL_INPUTS ^
  --root 05_RESULTS --scenario AXIS_INTEGRATED_WITH_POLICY ^
  --min-load-factor 0.5 --max-earliness 72 --time-limit 900 ^
  --strict-lexicographic
