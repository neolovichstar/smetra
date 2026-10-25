# Android: native shell + secure WebView

The Android app (`apps/mobile`, `applicationId ru.smetra.mobile`) is a thin native
shell around the production web cabinet `https://smetra.online/app`. The interface
and business logic ship with the website and update without an APK release; the
APK only adds what a browser cannot do well: system sign-in, camera, microphone,
files, share sheet, push, rewarded video and ARCore measurements.

## Components

| Class | Role |
| --- | --- |
| `ShellActivity` | Launcher activity. Hardened `WebView`, navigation policy, offline/error cover, file chooser and camera, insets, theme, deep links, Back. |
| `ShellBridge` | Handles bridge operations from the page and posts replies/events back. |
| `BridgeProtocol` | Pure-Java wire format and validators (unit-tested on the JVM). |
| `ShellSession` | The session lives only in the HttpOnly `session` cookie of the WebView cookie store. Native HTTP calls read it from `CookieManager`; it is never sent to JavaScript. Migrates the legacy `TokenVault` bearer token once. |
| `ShellAuth` | Yandex ID / VK sign-in in Custom Tabs with PKCE, `smetra://auth` return, `/api/auth/native/exchange` → `Set-Cookie` adopted into the WebView. |
| `ShellAds` | Rewarded video: server attempt → Yandex Ads → server claim with nonce. The page only learns the granted amount. |
| `ShellUpdates` | `GET /api/mobile/compat` → `app.update` event; opens RuStore. |
| `ShellSupport` | WebView availability and ARCore status. |
| `ArMeasureActivity` | ARCore point measurement (length, width, height) with manual input fallback. |
| `MainActivity` | Previous fully native UI, kept as a non-exported fallback when the system WebView is missing or too old. |

## WebView security

- JavaScript and DOM storage on; file and content access, file-URL access, universal
  access, mixed content, multiple windows and geolocation are off. Safe Browsing on.
- No `addJavascriptInterface`. The bridge is `WebViewCompat.addWebMessageListener`
  named `SmetraNative`, registered for exactly one origin (`BuildConfig.API_BASE_URL`).
  Iframes and other origins never see it; the native side also checks the origin
  of every message and that it comes from the main frame.
- Navigation: same-origin stays in the app; everything else opens in the browser.
  `smetra://` links are handled natively; OAuth starts are intercepted into Custom Tabs.
- Push and deep links can only open relative in-app paths (`/app`, `/app#…`,
  `/app?…`, `/?quote=…`), see `BridgeProtocol.safeAppPath`.
- Release builds require HTTPS; cleartext is allowed only for `127.0.0.1` and
  `10.0.2.2` in the debug network security config (emulator fixtures).
- WebView debugging is enabled only in debug builds.

## Bridge protocol v1

Page → native (string): `{"v":1,"id":"r1","op":"file.save","args":{…}}`
Native → page: `{"v":1,"id":"r1","ok":true,"result":{…}}` or
`{"v":1,"id":"r1","ok":false,"error":{"code":"…","message":"…"}}`.
Events: `{"v":1,"event":"app.update","data":{…}}`.

The web client is `apps/web/ui/native.js` (`window.SmetraShell`): `available`,
`ready`, `call(op, args, {timeout})`, `on(event, fn)`, `has(feature)`,
`handleBack()`. In a normal browser `available` is false and every feature keeps
its web behaviour.

| Operation | Purpose |
| --- | --- |
| `app.hello`, `app.capabilities` | Protocol, app version, available operations and features (`files`, `camera`, `speech`, `share`, `push`, `ads`, `ar`). |
| `app.setTheme` | System bar colours follow the page theme. |
| `app.openStore`, `app.openExternal` | RuStore page; external https links. |
| `auth.start` | System-browser sign-in (provider, intent, legal acceptance). |
| `speech.recognize` | Android speech recognizer → text. |
| `ads.rewarded.show` | Rewarded video for AI tokens (server-verified). |
| `push.status`, `push.enable`, `push.disable` | RuStore Push registration with the current session. |
| `file.save`, `file.share`, `file.open` | Files made in the page (≤ 10 MB, safe names and MIME types). |
| `ar.status`, `ar.measure` | ARCore support; measured rooms `{name, unit, length, width, height, source}`. |
| `request.cancel` | Reserved for cancellable long operations. |

Events: `auth.returned`, `auth.error`, `share.received`, `app.update`.

AR measurements are never imported directly: the page sends them to
`/api/construction/objects/{id}/scan/preview`, shows the result for review and only
then calls `scan/import` with `review_confirmed`. Without ARCore the same flow
works with manual dimensions.

## Versions and updates

`versionCode 41`, `versionName 2.0.0`. `GET /api/mobile/compat` (public, no DB)
returns `min_version_code`, `latest_version_code`, `bridge_protocol`, `store_url`
and an optional `message`, configured by `ANDROID_MIN_VERSION_CODE`,
`ANDROID_LATEST_VERSION_CODE`, `ANDROID_UPDATE_MESSAGE`. Below the minimum the page
shows a blocking update banner; below the latest a dismissible one. New web
features must check `SmetraShell.has()` / `capabilities.operations` and degrade
gracefully on older shells.

## Builds, tests and screenshots

- `CI / android`: JVM tests (`NativeSessionWorkTest`, `NativeImageSizeTest`,
  `BridgeProtocolTest`), `assembleDebug lintDebug`, unsigned `assembleRelease
  lintRelease`, installable debug APK artifact.
- `CI / web-backend`: `tests/dom_native_bridge.cjs` (web bridge client) and the
  compat endpoint test.
- `Android screens` workflow: builds a debug APK for `http://10.0.2.2:8090`, starts
  `scripts/android_ui_fixture.py` with `SMETRA_PROMO_QA=1` (isolated SQLite, no
  production data), boots a Pixel 6 emulator (API 34), measures cold/warm start,
  memory and APK size, drives the WebView over its devtools socket
  (`scripts/android_screens.cjs`) and captures device screenshots with
  `adb screencap`. `scripts/rustore_promo.py` then frames them into 10 promo
  images 1080×1920 and writes `manifest.json` (hashes of every source and promo)
  and `ui-critic.md` (Smetra UI Critic: overflow, tap targets, contrast, empty or
  error screens, console errors, promo layout checks). Results are uploaded as an
  artifact and pushed to the `android-screens` branch.

Regenerate locally (browser capture, not device):

```bash
SMETRA_PROMO_QA=1 SMETRA_FIXTURE_PORT=8097 SMETRA_FIXTURE_SESSION_FILE=/tmp/s python scripts/android_ui_fixture.py &
chrome --headless=new --remote-debugging-port=9230 about:blank &
SMETRA_CDP=http://127.0.0.1:9230 SMETRA_ORIGIN=http://localhost:8097 SMETRA_SESSION=$(cat /tmp/s) node scripts/android_screens.cjs
python scripts/rustore_promo.py data/android-screens
```

The AR promo image is intentionally replaced by AI tokens until AR is verified on
a physical ARCore device.

## Release rules

- Signing keys are never changed or generated by CI; release signing uses the
  existing `SIGNING_*` secrets.
- Nothing is uploaded to RuStore automatically. Publishing a release requires the
  owner's explicit confirmation.
