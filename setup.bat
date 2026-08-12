@echo off
chcp 65001 > nul
setlocal

REM 최초 1회 의존성 설치

set ROOT=%~dp0

echo [1/2] 백엔드 의존성 설치...
cd /d %ROOT%backend
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo [2/2] 프론트엔드 의존성 설치...
cd /d %ROOT%frontend
call npm install
if errorlevel 1 goto :error

echo.
echo 설치 완료. run_dev.bat 으로 실행하세요.
goto :end

:error
echo.
echo 설치 중 오류가 발생했습니다.

:end
endlocal
pause
