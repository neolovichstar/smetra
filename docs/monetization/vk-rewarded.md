# VK Ads rewarded video in Android (block 2106762)

## What is integrated

Android's **actual launcher** is `ShellActivity`, which uses `ShellBridge` and
`ShellAds`; `MainActivity` is a non-launcher fallback for older devices.

The publisher **VK Advertising Network / myTarget** native SDK is included
alongside Yandex Mobile Ads. The VK block ID supplied by the publisher is
**2106762**. This is a public placement ID, **not** an API key or access token.

**Before enabling monetization, verify in the VK publisher console that block
2106762 has format “Rewarded video”.** A banner/native/interstitial slot cannot
be used with `RewardedAd`; an invalid format normally causes no fill.

The backend remains the authority for free-plan eligibility, daily limit,
reward amount, and single-grant wallet credit. A video is presented only at
the user's request and only after consenting to this ad session. The SDK
onReward callback is the only native path that initiates a claim. Closing,
loading and displaying are not reward proofs.

## Production configuration

Set `VK_REWARDED_SLOT_ID=2106762` in the **Vercel production environment**
after the slot format is confirmed. No SDK account credentials belong in Git.
The backend uses VK only when the Android client requests
`X-Smetra-Ad-SDK: vk-v1`; old native builds and browsers continue to use the
existing `YANDEX_REWARDED_AD_UNIT_ID` / existing response format.

This **does not** automatically publish a new Android package to RuStore.
A newly built, signed and reviewed APK with VK SDK is required for the live
placement. The browser version and old installed APKs continue unchanged.

## User experience and privacy

- Show only the existing optional “Посмотреть видео · +3 запроса” offer after
  free monthly assistant quota is exhausted. PRO users get no reward ads.
- Do not pre-load or initialize VK ad SDK until the person explicitly accepts
  the in-app notice for this session.
- Set the SDK's consent flag on opt-in; use conservative age-restricted mode
  pending a first-class age/consent preference system.
- Do **not** send the PDF, construction projects, names, emails, tokens,
  messages or assistant prompts to VK.
- The existing server nonce is **not** provider server-side verification (SSV):
  a modified APK could forge a callback. The existing single reward/day and
  fixed non-monetary bonus are mitigation, not complete fraud protection.
- A cancellation, missing inventory, network error or provider mismatch
  must leave the bonus uncredited and allow the rest of the app to work.

Verify the privacy policy and RuStore data disclosures before releasing the
SDK. Consider a consent/withdrawal preference, diagnostic counters (without
personal data), server-to-server rewards if VK supports verifiable callbacks,
and app-ads.txt authorized sellers. Publisher seller IDs must come from the
actual VK partner account; never invent them.

## Test plan

1. Check the slot format for **2106762** in the VK publisher interface.
2. Build the current Android branch, install on a test device, opt in on the
   free plan only after monthly requests run out.
3. Confirm the backend responds with `provider=vk`, `ad_unit_id=2106762`;
   old clients without the header continue to receive the Yandex placement.
4. In the SDK test device configuration, exercise load, no-fill, close before
   reward, successful onReward, repeated callback and interrupted network.
5. Confirm one wallet credit only and at most one credit per account/day;
   no credits on ad load/display/close.
6. Check compilation via Android GitHub CI and installable release signing
   separately. This repo's Vercel build does **not** ship an Android APK.
