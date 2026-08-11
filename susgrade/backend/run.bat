@echo off
REM ============================================================
REM  susgrade backend launcher (Windows)
REM  Double-click this file, or run it from a terminal.
REM ============================================================
cd /d "%~dp0"

echo Installing dependencies (first run only)...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Could not install dependencies. Is Python installed and on your PATH?
  echo Try: py -m pip install -r requirements.txt
  pause
  exit /b 1
)

echo.
echo ============================================================
echo   susgrade backend is starting on http://127.0.0.1:8000
echo   Keep this window OPEN while you use mutation testing.
echo   Test it: open http://127.0.0.1:8000/health in your browser
echo   Stop it: press Ctrl+C
echo ============================================================
echo.

python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pause
