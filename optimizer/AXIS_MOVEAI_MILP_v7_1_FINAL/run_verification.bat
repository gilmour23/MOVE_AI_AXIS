@echo off
REM AXIS v7.1 - Step 6. Full verification (re-executes code, not only stored CSVs)
cd /d "%~dp0"
python 02_CODE\verify_v7_1.py .
