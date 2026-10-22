# Rewarded ads in Smetra (Yandex)

The Android app uses Yandex Mobile Ads SDK 8.6.0. Rewarded ads are requested only when the free assistant quota reaches zero; a completed reward grants three additional assistant requests and expires after 24 hours. The backend allows one grant per account per Moscow calendar day and never accepts a client-supplied ad-unit ID.

## One-time account setup

1. Open https://partner.yandex.ru/apps and register Smetra (Android package: `ru.smetra.mobile`).
2. After the app is moderated, add a **Rewarded** ad unit. For CPM strategy, choose **Maximum revenue** to start; this avoids choosing a manual floor before seeing real data.
3. Add the ad unit ID (format typically `R-M-...`) as the Vercel production environment variable `YANDEX_REWARDED_AD_UNIT_ID`. Do not paste Yandex account credentials into the repository.

Until the production ID exists, the server deliberately returns `enabled: false`; no demo-unit rewards will be granted in production. The same SDK test unit `demo-rewarded-yandex` may be used only in local/debug work.

Yandex Mobile Ads does **not** provide server-side rewarded-event verification. Therefore the app calls the authenticated claim endpoint only in the SDK's `onRewarded` callback, while the server enforces account/day uniqueness and a fixed three-request amount. This prevents duplicate claims across devices but cannot fully stop a modified client from forging its callback; do not use this mechanism for cash-equivalent rewards.

## Test

`python -m unittest tests.test_assistant_ad_rewards -v`

The installable Android APK build remains a separate release artifact; this change does not automatically publish to RuStore.
