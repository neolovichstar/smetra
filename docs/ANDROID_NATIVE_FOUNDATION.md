# Android Native Foundation 2.1.0

Target `ru.smetra.mobile`, `minSdk 26`, `targetSdk 35`, `versionCode 42`.
The website remains the UI and most features can be shipped from Vercel without republishing APK. This is a **native capability foundation**, not a promise that every capability has a polished web screen.

## Bundled stable libraries

| Area | Pinned dependency | Purpose |
| --- | --- | --- |
| AR | `com.google.ar:core:1.46.0` | Existing optional AR measurements |
| Web | `androidx.webkit:webkit:1.12.1`, `androidx.browser:browser:1.8.0` | Exact-origin bridge and browser OAuth |
| Camera | `androidx.camera:camera-{core,camera2,lifecycle,view}:1.5.3` | Future first-party camera/preview |
| Offline recognition | ML Kit `barcode-scanning:17.3.0`, `text-recognition:16.0.1` | Local QR/barcode and Latin OCR for selected image bytes |
| Background | `androidx.work:work-runtime:2.10.1` | Future bounded deferred work, no jobs scheduled yet |
| Biometrics | `androidx.biometric:biometric:1.1.0` | Current availability check, no login-bypass |
| Files | `androidx.documentfile:documentfile:1.1.0` | Future SAF document providers |
| Photos | `androidx.exifinterface:exifinterface:1.4.2` | Future image metadata safety |
| Production | RuStore Push 7.5.0, Yandex Mobile Ads 8.6.0, MyTracker 3.6.0 | Existing integrations |

Not bundled: every SDK on Maven, Firebase when RuStore Push already exists, heavy 3D runtimes, unrelated trackers, and unused native AI models. They consume storage/permissions and create update liability; add them when a specific feature needs them.

## Versioned web-to-native bridge

`window.SmetraShell.call(op, args)` is available **only to the exact `https://smetra.online` top-level WebView origin**. New v1 operations:

- `device.haptic`: optional `{style:"selection"|"strong"}`; native UI haptic without vibration permission.
- `device.copyText`: `{text:"..." }`, nonempty up to 8000 characters, writes system clipboard. Does **not** read clipboard.
- `device.shareText`: `{text:"..."}`, up to 8000 characters, user-visible Android Sharesheet.
- `device.biometric.status`: returns `{available:boolean,status:"available"|"not_enrolled"|"unavailable"}`. This **does not** authenticate anyone.
- `vision.image.scan`: `{mode:"barcode"|"text",base64:"<base64 JPEG/PNG>"}`; JPEG/PNG signature check, <=3 MB encoded image, <=24 MP before sampling. `barcode` returns up to 20 entries `{format,text}`; `text` returns `{text,language:"latin"}` (not guaranteed to recognize Cyrillic). Processing is on device and **does not upload pictures**. Input is user-supplied; no silent access to camera or gallery. Never auto-open QR results.

`app.capabilities.features` now also reports `barcodeImage`, `textImageLatin`, `biometric`, `haptics`, `clipboardWrite`, `shareText`, and `nativeFoundation:2`. Do not use `cameraX`/background work as active features until implemented and tested. Check `app.capabilities.operations` before calling optional actions on older APKs.

## Release safety

- Keep `WebView` debugging disabled in release, `Content-Security-Policy` on the site, explicit runtime permissions, `https`-only backend, signed OAuth session handoff, FileProvider grant scope.
- Validate that minification/proguard keeps vendor integrations functional.
- `assembleRelease -PverifyUnsignedRelease=true` is a **CI validation artifact**, not a distribution APK. **Only** build/sign with the existing local RuStore release keystore before publishing.
- CI uploads an **installable debug-signed** `smetra-android-apk` to Actions for testers, not for the RuStore production channel.
