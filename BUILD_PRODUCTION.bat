@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Python is missing & exit /b 1)
python -m compileall -q backend || exit /b 1
python -m unittest discover -s tests -v || exit /b 1
where node >nul 2>nul || (echo Node is missing & exit /b 1)
node --check apps\web\app.js || exit /b 1
where gradle >nul 2>nul || (echo Gradle is missing; Android build was NOT VERIFIED & exit /b 2)
pushd apps\mobile
gradle assembleDebug || (popd & exit /b 1)
if "%SIGNING_STORE_FILE%"=="" (echo Signing credentials missing; release APK/AAB NOT VERIFIED & popd & exit /b 2)
gradle assembleRelease bundleRelease || (popd & exit /b 1)
popd
echo Checks and Android builds completed.
