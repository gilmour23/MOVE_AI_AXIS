@echo off
chcp 65001 > nul
setlocal

REM MOVE-AI 선사 UI 개발 서버 실행
REM  - 백엔드: http://127.0.0.1:8000  (FastAPI / uvicorn)
REM  - 프론트: http://localhost:5173   (Vite)
REM 창 두 개가 열립니다. 종료하려면 각 창을 닫으세요.

set ROOT=%~dp0

echo [1/2] 백엔드 실행 중...
start "MOVE-AI backend" cmd /k "cd /d %ROOT%backend && python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload"

echo [2/2] 프론트엔드 실행 중...
start "MOVE-AI frontend" cmd /k "cd /d %ROOT%frontend && npm run dev"

echo.
echo 브라우저에서 http://localhost:5173 을 열어주세요.
echo.
endlocal
