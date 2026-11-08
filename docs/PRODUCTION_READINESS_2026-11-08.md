# Production hardening, payments and assistant latency — 8 November 2026

This release continues from `3eb4a44` (the previous deployed release), not the
repository's older default branch. No production schema migration, key rotation,
DNS change or payment charge is part of this change.

## Implemented protections

- PostgreSQL acquisition now has a finite queue: 16 waiting requests by default,
  configurable within 1–256. The existing pool size stays 2 by default, capped
  at 4 per process; acquisition remains bounded to five seconds. Saturation
  returns sanitized HTTP 503 with `Retry-After: 2` and `Cache-Control: no-store`.
- An explicit DSN `sslmode=verify-ca` or `verify-full` is preserved. Previously
  the connection kwargs replaced it with `require`. Production connections
  continue to require TLS; loopback-only test connections retain their exemption.
- OAuth cloud tokens support an authenticated MultiFernet decryption key ring.
  New records always use `CLOUD_TOKEN_ENCRYPTION_KEY`; up to four previous keys
  can be supplied in `CLOUD_TOKEN_DECRYPTION_KEYS`. Existing ciphertext remains
  readable. Invalid keys and tampered records fail closed.
- Android session records use a versioned AES-GCM envelope with purpose-bound
  associated data. New Keystore aliases use AES-256 and fresh random nonces.
  Existing AES-GCM session records migrate on a successful read; an existing
  Keystore key is retained rather than silently invalidating sessions.
- Android PKCE verifier and timestamp now use Keystore-backed encrypted storage,
  expire after ten minutes, and are consumed once. Old plaintext verifier
  preferences are removed. Both the current shell and legacy native flow use it.
- The legacy native dashboard, quotes, clients and projects offline cache is
  encrypted and bound to the captured session. Old plaintext copies are removed.
  Records over 64 KiB are deliberately not cached; a cache failure does not fail
  a successful online request. Other app/browser storage is not represented as
  end-to-end encrypted by this change.
- Native authenticated API, streaming and file requests do not follow redirects,
  avoiding accidental forwarding of authorization to another destination.

## Payment experience

A dismissible, keyboard-accessible paywall preserves the working page and draft,
uses server pricing and explains one-time payment. It follows the current theme
and system reduced-motion setting. A confirmed success draws a green check;
a confirmed cancellation draws a red cross. Pending, refunded and network-error
states have distinct wording. A pre-existing paid plan or a URL query parameter
cannot prove success. Outcomes match the exact API-issued payment ID and are
shown once per terminal state. Late responses after navigation or logout are
ignored. A pending payment return no longer recursively calls synchronization.

Payment-provider responses are simulated only in the isolated UI tests. These
checks do not certify a live card purchase, bank rejection, refund settlement,
receipt delivery or webhook delivery through the public payment provider.

## Assistant responsiveness and access from Russia

Interactive requests prefer lower first-token latency for the selected model and
use low reasoning effort by default, configurable to medium/high. The model,
server-side quotas, confirmation rules and domain calculations are preserved.
Automatic semantic chat-title generation is off by default: long first messages
previously incurred another synchronous provider request with a seven-second
timeout after the answer. An extractive title is available immediately. Operators
can opt in with `SMETRA_AI_GENERATE_TITLES=1`.

Durable SSE logs now record first-text and total timings without prompts,
answers or account identifiers. Provider latency itself still requires measuring
real production requests; fixture timings are not a live-model speed claim.

The duplicate job panel no longer appears inside the message input. Recovery
and file tasks live with the transcript; the currently streamed chat does not
add a duplicate task row. The stop button and durable recovery remain available.

Source badges no longer fetch Google favicons. Core application assets, fonts
and browser API calls are same-origin. Chrome checks exercise the paywall and
payment status handlers with external browser requests blocked. This removes a
specific external dependency; it does not prove connectivity from every Russian
ISP, the availability of external OAuth/payment services, browser speech services,
or hosting connectivity during network restrictions. A Russian ISP/mobile-network
probe and provider fallback drills remain operational release checks.

## Verification and capacity boundary

- Chrome: paywall at 320, 390, 768 and 1440 pixels, dark/light themes, Escape,
  focus management, three payment outcomes and reduced motion. Zero JavaScript
  errors and zero external browser dependencies in this flow.
- All 34 DOM suites passed, including delayed payments, stale sessions, failed
  synchronization, preserved drafts and confirmed checkout. The real-API action
  harness exercised 193 buttons/forms without JavaScript errors.
- Final full Python discovery: 1303 cases passed, with 17 environment-dependent
  skips. The PostgreSQL and Android GitHub jobs passed separately. Browser gates
  are checked again after updating their obsolete eager-conversation assumptions.
- Ruff, web build/CSP hash validation, dependency audit and focused security
  regressions passed. The dependency audit found no known advisories at this run.
- Android debug/release assembly and lint passed. JVM cryptography tests passed.
  A separately named QA package on an API-35 emulator passed actual Android
  Keystore storage, nonce freshness, session binding, tamper rejection and
  one-time/expired/future-dated PKCE tests. The user's installed emulator package
  was not removed to run this test.
- A signed release APK was produced as version 2.1.3 / code 45; the existing
  release certificate and manifest identity were verified by the release script.

`python scripts/load_smoke.py` seeds an isolated local SQLite database and blocks
external network access. The repeated run used 1000 accounts, 3000 authenticated
HTTP reads, 32 concurrent workers, and checked the account ID of every response:
150.04 requests/s, p50 183.21 ms, p95 358.64 ms, zero errors. An earlier run had
one non-reproduced connection error. This is local read-path evidence, not a
certification of 1000 simultaneous production users or AI generations. Real
Supabase/Vercel/Redis capacity, mixed writes, provider quotas and long-running
generation load need a controlled staging benchmark. No production stress test
was performed. Review the existing per-IP firewall threshold for shared NAT
before scaling the user population.

## Key-rotation procedure and rollback

1. Keep the old primary key safely available; add it to the decryption-only list
   while introducing a new primary. Never print either key or commit it.
2. Verify old-token reads and new-token writes in staging, then roll out both
   configuration changes atomically. Preserve the old key throughout rollback.
3. Old ciphertext is not bulk-reencrypted by this release. Keep required old
   keys until every record has been refreshed or deliberately re-encrypted and
   verified. Dropping a required key forces those cloud accounts to reconnect.
4. Reverting to code without key-ring support requires restoring the former
   primary or re-encrypting new records first; do not assume arbitrary old code
   can decrypt records written with a new primary.

Code rollback uses the preceding Vercel deployment; no database migration is
needed. Do not rotate production keys or enable an unprovisioned mandatory
antivirus scanner as part of a code-only rollback. Backup restore drills,
independent access-control review and production provider monitoring remain
separate operational work.

References: [Android cryptography](https://developer.android.com/privacy-and-security/cryptography),
[Fernet/MultiFernet](https://cryptography.io/en/latest/fernet/),
[Psycopg pools](https://www.psycopg.org/psycopg3/docs/advanced/pool.html),
[PostgreSQL TLS](https://www.postgresql.org/docs/current/libpq-ssl.html),
[OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection),
[reasoning controls](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).
