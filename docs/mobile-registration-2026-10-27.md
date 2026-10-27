# Mobile email registration — 2026-10-27

## Reproduced behavior

The public production registration page at 390 px displayed both
`email-code-address` and `email` at once, along with duplicate name fields
and an unnecessary password. No console exception was needed to trigger it.

Three pieces of code independently controlled the password disclosure. Its
open/closed state depended on whether the capability response arrived before
or after the auth-mode observer. The hidden disclosure summary prevented a
clear choice of login method.

## Fix

- `app.js` owns one explicit email-method state. Registration uses the code
  flow when available; existing users can explicitly choose password login.
  Inactive inputs are disabled and cannot participate in validation/autofill.
- Switching methods preserves the entered address. The one legal checkbox is
  placed in the active registration form before submission.
- OTP and password requests ignore obsolete replies after changing mode/method.
  Returning to the address step cancels the pending OTP request locally.
- Failed resend preserves the current challenge and entered digits. Repeated
  taps cannot start duplicate requests.
- Six-digit paste/autofill remains supported. Mobile inputs use 16 px text,
  tabs/back controls have 44 px targets, and narrow code rows cannot overflow.
- Password reset hides both email forms and the auth tabs.
- Updated resource versions invalidate cached auth JS/CSS.

## Verification

- Live before-fix observation: two visible enabled email fields, OTP and signup
  capabilities both true, no console errors.
- Chromium with the real isolated API: at 320, 390 and 430 px, exactly one
  address field; registration request -> OTP confirmation -> authenticated
  dashboard; all three users verified and all three legal acceptances stored.
- 420 px viewport-height check for code entry and scrolling with reduced
  visible space. This models available space; it is not a physical iOS/Android
  keyboard test.
- OTP delivery uses a local fixture. No external messages were sent and no real
  production accounts were created. Live SMTP/Yandex OAuth delivery was not
  retested.
- 21 DOM suites passed, including the new auth suite for delayed capability
  responses, duplicate taps, stale start/confirm/password replies, method/back
  navigation, failed resend and reset mode.
- Existing auth-motion Python checks, Ruff, JavaScript syntax, web build and
  `git diff --check` passed.

Native Android sources are unchanged; these fixes affect the shared web auth page.
