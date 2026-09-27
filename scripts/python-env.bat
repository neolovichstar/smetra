@echo off
rem Called from project root. Prefer a standard Windows virtual environment.
set "SMETRA_PY="
if exist .venv-win\Scripts\python.exe set "SMETRA_PY=%CD%\.venv-win\Scripts\python.exe"
if not defined SMETRA_PY if exist .venv\Scripts\python.exe set "SMETRA_PY=%CD%\.venv\Scripts\python.exe"
if defined SMETRA_PY exit /b 0
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 exit /b 1
if not exist .venv\Scripts\python.exe (
    echo ERROR: Use standard Windows Python 3.11+, not an MSYS Python installation.
    exit /b 1
)
set "SMETRA_PY=%CD%\.venv\Scripts\python.exe"
exit /b 0
