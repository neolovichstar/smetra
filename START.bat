@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.11+ is required. & exit /b 1)
if not exist .env copy .env.example .env >nul
python backend\launcher.py
