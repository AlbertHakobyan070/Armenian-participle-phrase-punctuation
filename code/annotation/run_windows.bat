@echo off
REM ============================================================
REM Windows Launcher: Runs 3 workers (chunks 3, 4, 5) in parallel
REM Place this file in A:\armenian_annotation\
REM ============================================================

REM Force all Python cache to A: drive
set PYTHONDONTWRITEBYTECODE=1
set TMPDIR=A:\armenian_annotation\tmp
set TEMP=A:\armenian_annotation\tmp
set TMP=A:\armenian_annotation\tmp
set PIP_CACHE_DIR=A:\armenian_annotation\pip_cache

if not exist "%TMPDIR%" mkdir "%TMPDIR%"
if not exist "%PIP_CACHE_DIR%" mkdir "%PIP_CACHE_DIR%"

echo ============================================================
echo Starting 3 annotation workers on Windows (chunks 3, 4, 5)
echo All data stored on A: drive
echo ============================================================
echo.

REM Start workers in separate windows
start "Worker 3" cmd /k "cd /d A:\armenian_annotation && python worker.py 3"
timeout /t 5
start "Worker 4" cmd /k "cd /d A:\armenian_annotation && python worker.py 4"
timeout /t 5
start "Worker 5" cmd /k "cd /d A:\armenian_annotation && python worker.py 5"

echo.
echo All 3 workers started! Check the separate windows for progress.
echo Each worker checkpoints after every sentence - safe to close and restart.
pause
