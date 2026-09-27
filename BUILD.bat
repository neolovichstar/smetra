@echo off
setlocal
cd /d "%~dp0"
set "SMETRA_NO_PAUSE=1"
call TEST.bat
if errorlevel 1 goto :failed
echo Web build: dist\web
if not defined ANDROID_HOME goto :no_android
call apps\mobile\gradlew.bat -p apps\mobile assembleDebug lintDebug
if errorlevel 1 goto :failed
echo Debug APK: apps\mobile\app\build\outputs\apk\debug\app-debug.apk
pause
exit /b 0
:no_android
echo Android NOT BUILT: set ANDROID_HOME to the Android SDK folder.
pause
exit /b 2
:failed
echo Build failed. See the error above.
pause
exit /b 1
