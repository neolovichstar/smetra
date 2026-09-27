@echo off
setlocal
cd /d "%~dp0"
set "SMETRA_NO_PAUSE=1"
call TEST.bat
if errorlevel 1 goto :failed
if not defined ANDROID_HOME (echo ANDROID_HOME is missing. & goto :failed)
if not defined SMETRA_API_BASE_URL (echo SMETRA_API_BASE_URL is missing. Set the real HTTPS API origin. & goto :failed)
if not defined SIGNING_STORE_FILE (echo Release signing credentials are missing. & goto :failed)
call apps\mobile\gradlew.bat -p apps\mobile assembleRelease bundleRelease "-PapiBaseUrl=%SMETRA_API_BASE_URL%"
if errorlevel 1 goto :failed
echo Release APK and AAB built. Server deployment is a separate operation.
pause
exit /b 0
:failed
echo Production build did not complete. Review the error above.
pause
exit /b 1