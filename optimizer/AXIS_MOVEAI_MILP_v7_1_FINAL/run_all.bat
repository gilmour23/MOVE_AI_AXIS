@echo off
REM ===================================================================
REM AXIS v7.1 - full pipeline (data -> joint MILP -> baselines
REM              -> sensitivity -> regression -> verification)
REM ===================================================================
cd /d "%~dp0"
call run_data_generation.bat || goto :err
call run_axis_integrated.bat || goto :err
call run_baselines.bat       || goto :err
call run_sensitivity.bat     || goto :err
call run_role_tilt_sensitivity.bat || goto :err
call run_tests.bat           || goto :err
call run_verification.bat    || goto :err
echo.
echo AXIS v7.1 pipeline finished.
goto :eof
:err
echo.
echo AXIS v7.1 pipeline FAILED.
exit /b 1
