# Redis coordination in Сметра

PostgreSQL remains the source of truth for accounts, sessions, workspaces, quotes, projects, payments, subscriptions, files, assistant messages and monthly AI usage. Redis can be emptied without deleting those records. This integration uses the official `upstash-redis` Python HTTP client from Vercel Functions; web and Android clients never receive Redis credentials.

## Runtime and configuration

`api/index.py` runs Python functions on Vercel. The project currently targets `fra1`; PostgreSQL is in EU Central. The Upstash REST URL and write token are provided only as `REDIS_KV_REST_API_URL` and `REDIS_KV_REST_API_TOKEN` in Vercel environment variables. `REDIS_URL` and the read-only token are intentionally unused. `REDIS_ENABLED=auto` enables Redis when the REST pair exists; `false` disables it locally. `REDIS_ENV` defaults to Vercel's `VERCEL_ENV`, separating `production` and `preview` even if they share an Upstash database. Local development works without Redis.

`backend/redis_infra.py` owns the provider boundary. The SDK client is reused in a warm function instance, has one-second connect and two-second I/O timeouts, no automatic retries, and a ten-second per-instance circuit breaker after a command failure. URLs must use HTTPS. Keys have the form `smetra:{environment}:{purpose}:{sha256(dimensions)}`. IDs, IPs and email addresses are hashed before they reach a Redis key. No `KEYS` or global flush is used.

## Active uses

| Purpose | Operation | TTL | Failure behavior |
|---|---|---:|---|
| Distributed request limit | Atomic Lua GCRA, using Redis server time | Window plus one interval | PostgreSQL's existing distributed limiter for ordinary routes; AI fails closed |
| Assistant chat run | `SET NX EX` owner-token lease | 120 s | New AI run fails closed |
| AI draft | `SET NX EX` owner-token lease | 90 s | New AI run fails closed |
| Apply assistant action | `SET NX EX` owner-token lease | 30 s | PostgreSQL action status and transaction remain authoritative |

Lock release is an atomic compare-and-delete Lua script; a delayed request cannot release another owner's lease. A conflict returns a retryable response. Locks add coordination and never replace authorization, PostgreSQL constraints, or transactions.

The assistant's three free messages per month and paid allowance remain in PostgreSQL. AI draft's daily usage remains in PostgreSQL. YooKassa checkout/provider idempotency, payment records, webhooks, and subscription entitlement remain authoritative in PostgreSQL and YooKassa. A Redis flush may reset temporary rate counters and locks; it must not grant paid access or duplicate a completed financial transition.

File uploads, document generation, imports and search use route-specific Redis rate limits. Login uses both IP and hashed account dimensions. All existing auth, origin, RLS and workspace checks still run. Rate-limit responses use HTTP 429, `Retry-After`, `code=rate_limited`, and `retryAfter` seconds without exposing the internal key.

## Deliberately deferred

There is no persistent worker in this Vercel deployment. Redis job state, queues, progress streams and pub/sub are not implemented: a Redis queue without a consumer would strand work. OAuth state remains a single-use, expiring PostgreSQL record. Dashboard/catalog caching is not enabled without query profiling, because stale tenant or financial data is costlier than the current reads. No Redis key is used as a source of business truth.

## Verification

Run `python -m unittest discover -s tests -p 'test_*.py' -q` and `python scripts/build_web.py`. A separate ignored QA script exercises an integration namespace against a real Upstash instance: ping, rate-limit saturation, lock conflict, wrong-owner unlock and reacquisition. Do not run `FLUSHDB` on a shared instance. Load testing belongs in staging, never production.
