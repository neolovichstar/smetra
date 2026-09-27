@echo off
setlocal
cd /d "%~dp0"
call scripts\python-env.bat
if errorlevel 1 goto :failed
"%SMETRA_PY%" -m pip install -r requirements-dev.txt
if errorlevel 1 goto :failed
"%SMETRA_PY%" -m ruff check backend tests scripts
if errorlevel 1 goto :failed
"%SMETRA_PY%" -m unittest discover -s tests -v
if errorlevel 1 goto :failed
"%SMETRA_PY%" scripts\build_web.py
if errorlevel 1 goto :failed
echo Tests, lint and web build PASS. Browser E2E is a separate isolated run.
if not defined SMETRA_NO_PAUSE pause
exit /b 0
:failed
echo Tests failed. See the error above.
if not defined SMETRA_NO_PAUSE pause
exit /b 1
