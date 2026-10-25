#!/usr/bin/env bash
# Runs inside the Android emulator job: installs the debug APK, measures start-up,
# drives the WebView through its devtools socket and takes device screenshots.
set -euo pipefail
OUT=${SMETRA_SCREENS_DIR:-data/android-screens}
APK=apps/mobile/app/build/outputs/apk/debug/app-debug.apk
PACKAGE=ru.smetra.mobile
mkdir -p "$OUT"
adb wait-for-device
# Keep a device log next to the screenshots; it explains crashes and WebView errors.
adb logcat -c || true
adb logcat -v time > "$OUT/logcat.txt" 2>&1 &
adb install -r "$APK"
adb shell settings put system screen_off_timeout 1800000 || true
# A clean, fixed status bar (demo mode) so screenshots do not show CI noise.
adb shell settings put global sysui_demo_allowed 1 || true
for command in "enter" "clock -e hhmm 0941" "battery -e level 100 -e plugged false" "network -e wifi show -e level 4 -e mobile hide" "notifications -e visible false"; do
  set -- $command
  name=$1; shift
  adb shell am broadcast -a com.android.systemui.demo -e command "$name" "$@" > /dev/null || true
done

start_ms() { adb shell am start -W -n "$PACKAGE/.ShellActivity" | tr -d '\r' | awk -F': ' '/TotalTime/{print $2}'; }
adb shell am force-stop "$PACKAGE"
cold=$(start_ms)
sleep 6
adb shell input keyevent KEYCODE_HOME
sleep 2
warm=$(start_ms)
sleep 3
pid=$(adb shell pidof "$PACKAGE" | tr -d '\r')
adb forward tcp:9222 "localabstract:webview_devtools_remote_$pid"


pss=$(adb shell dumpsys meminfo "$PACKAGE" | tr -d '\r' | awk '/TOTAL PSS:/{print $3; exit} /^ *TOTAL /{print $2; exit}')
cat > "$OUT/metrics-native.json" <<JSON
{
  "device": "$(adb shell getprop ro.product.model | tr -d '\r')",
  "android": "$(adb shell getprop ro.build.version.release | tr -d '\r')",
  "screen": "$(adb shell wm size | tr -d '\r' | awk '{print $NF}')",
  "density": "$(adb shell wm density | tr -d '\r' | awk '{print $NF}')",
  "webview": "$(adb shell dumpsys package com.google.android.webview | tr -d '\r' | awk -F= '/versionName/{print $2; exit}')",
  "cold_start_ms": ${cold:-null},
  "warm_start_ms": ${warm:-null},
  "total_pss_kb": ${pss:-null},
  "apk_bytes": $(stat -c %s "$APK")
}
JSON
cat "$OUT/metrics-native.json"
# Device screenshots are best effort: the CI emulator is short-lived.
SMETRA_CDP=http://127.0.0.1:9222 SMETRA_SCREENCAP=adb SMETRA_SCREENS_DIR="$OUT" node scripts/android_screens.cjs
adb shell am broadcast -a com.android.systemui.demo -e command exit > /dev/null || true
