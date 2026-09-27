@echo off
setlocal
cd /d "%~dp0"
call scripts\python-env.bat
if errorlevel 1 (
    echo ERROR: Install Python 3.11+ and add it to PATH.
    goto :failed
)
if not exist .env (
    copy .env.example .env >nul
    if errorlevel 1 goto :failed
)
"%SMETRA_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
"%SMETRA_PY%" backend\launcher.py
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Startup failed. See the error above.
echo If the port is busy, change PORT and PUBLIC_ORIGIN in .env to the same free port.
if not defined SMETRA_NO_PAUSE pause
exit /b 1
