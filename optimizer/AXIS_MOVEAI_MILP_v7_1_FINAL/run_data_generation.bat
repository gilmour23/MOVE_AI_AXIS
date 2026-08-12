@echo off
REM AXIS v7.1 - Step 1. Aggregate Master -> Synthetic Carrier-Level Data
cd /d "%~dp0"
python 02_CODE\axis_data_gen_v7_1.py ^
  --master 03_INPUT_DATA\AXIS_hourly_empty_demand_supply_v8_6hubs.xlsx ^
  --snapshot 03_INPUT_DATA\public_snapshot_2026-08-09.csv ^
  --outdir 03_INPUT_DATA
