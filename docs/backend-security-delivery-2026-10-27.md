# Backend security and chat delivery — 2026-10-27

Base: live production commit e1bb38def14bfa2458db32fcf6042723fef05b73,
branch design/vault-changelog-polish-20261026, schema 66.

## Implemented fixes

- Legacy object chats now require current workspace membership or ownership on reads,
  writes and listings. Historical chat membership alone grants no access.
  Writes recheck the session and membership inside a transaction scoped to user,
  conversation and (for object chats) workspace. Message insertion and conversation
  update commit together before acknowledgement.
- Peer-facing conversation lists omit creator email addresses. The authenticated
  administrator support queue retains the customer email needed for support.
- Completed JSON responses return an explicit handled result. Communication routes
  no longer append a second 404/error response after a successful response.
- Initial chat/support history returns the latest 100 messages, ordered for display.
  Incremental reads retain ascending bounded pages. Support AI sees the most recent
  20 messages. Empty/already-read polls avoid advancing the read marker.
- Support creation endpoints share an account limit. Cost-bearing support AI calls
  fail closed during a configured Redis outage before ticket/message writes.
  Human handoff is still available without a model call.
- YooKassa callbacks validate object identifiers and notification type and use
  per-object plus global provider-verification limits. Refund responses must match
  both the requested refund ID and original payment ID; the payment's shop,
  environment and terms are rechecked with the provider. Existing idempotency and
  provider-side checks for amount, currency, account, plan and paid status remain.
  Unsupported webhook methods are rejected before allocating a DB connection.
- Google Drive callbacks bound header sizes, rate-limit attempts and authenticated
  channels, reject disconnected accounts and coalesce repeated reconciliation
  requests. Channel token, resource ID and expiry checks remain mandatory.
- Password reset consumes all remaining reset links for the account and revokes
  sessions under the user lock. Consumption rechecks token expiry and account
  blocked/deleted state. Two simultaneous links have one winner.
- Excessively nested JSON returns a controlled 400.
- Integrated the backend stability changes from PR #67: reuse the primary request
  connection for PostgreSQL rate-limit fallback, bounded SQL-translation caching,
  commit SSE results before done, and safe disconnect/cleanup handling.

No new production schema migration is required. Frontend and Android sources and
financial arithmetic are unchanged.

## Verification

- Python 3.12.15: full discovery, 992 tests passed in 102.438 seconds, no skips.
- One additional HTTP concurrency test passed after the full run: 12 messages sent
  by four workers were committed before acknowledgements and all visible to the peer.
- Disposable PostgreSQL 17: atomic fallback limit (100 attempts, exactly 10 admitted),
  pool saturation during Redis failure, transaction ownership, SSE visibility from a
  second connection before done, runtime RLS and current-membership chat queries.
- New HTTP cases cover forged payment fields, refund mismatch, callback replay,
  bounded provider requests, revoked object-chat access, peer-email privacy,
  latest history, rollback after insertion failure, single HTTP response,
  support limits/outage handling and concurrent password resets.
- Ruff, compileall and git diff --check passed.
- pip-audit 2.10.1 against requirements-dev.txt reported no known vulnerabilities.
- Targeted tracked-source scan found no matching GitHub token/private-key formats.
  This is not a complete credential/history scan.

The PostgreSQL CI job installs the existing core/runtime migrations and the
communication table/index/grant definitions from migration 51. It deliberately
does not claim to reproduce all hosted Supabase features or the complete live schema.

## Read-only production observations

- 126 tables in the private smetra schema; all have RLS enabled.
- No SELECT privileges on those tables for anon/authenticated.
- smetra_runtime, anon and authenticated are neither superusers nor BYPASSRLS roles.
- Schema version: 66. Storage bucket count: 0.
- Supabase security advisor reported informational RLS-without-policy findings;
  those tables deny client/runtime access by default and use server access.
- Performance advisor still reports unindexed foreign keys and overlapping/RLS
  policy evaluation notices. These are not evidence of a data leak and were not
  changed speculatively.
- Vercel Firewall is enabled; API/health burst guard is active at 300 requests per
  IP per minute. Managed detection groups remain in their existing logging mode.

## Limits and next verification

This is a scoped security improvement, not proof that all leaks or attacks are
impossible. Existing tests do not replace an independent penetration test.

No live payment/refund, provider callback delivery or hosted Realtime test was
performed. Provider verification in automated tests uses controlled responses;
the database/runtime tests use a disposable PostgreSQL instance. Legacy peer and
support chats still use polling, so backend fixes do not make their UI instantaneous.
Historical timestamps retain second precision; this change does not add a new
sequence/cursor protocol or historical pagination UI.

Previously disclosed credential rotation, backup restoration, production-scale load
and broader infrastructure hardening require separate verification. No production
credentials were printed, changed or rotated during this work.

References:
- https://yookassa.ru/developers/using-api/webhooks
- https://supabase.com/docs/guides/api/securing-your-api
- https://supabase.com/docs/guides/database/database-linter
