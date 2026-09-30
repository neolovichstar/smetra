# Redis operations runbook

## Unavailable or slow Redis

Check the Upstash service and the Vercel Function region, then verify `REDIS_KV_REST_API_URL` and `REDIS_KV_REST_API_TOKEN` are scoped to the intended environment. Never paste values into logs or support tickets. Ordinary requests continue through PostgreSQL's distributed limiter; new AI requests return 503 to avoid uncontrolled provider spending. A warm instance stops retrying Redis for ten seconds after a command failure. PostgreSQL business records and YooKassa payment state remain available.

For emergency isolation, set `REDIS_ENABLED=false` in Vercel and redeploy. This disables Redis coordination; the existing PostgreSQL limits remain, but the AI concurrency guard is absent. Prefer restoring Redis promptly. Re-enable after checking latency and a few real API requests. Avoid disabling PostgreSQL quotas or webhook validation.

## Excess 429 responses

Inspect route, account/IP dimension, `Retry-After`, and recent traffic. A 429 is per window and expires automatically. Do not delete all rate keys or flush a shared database. If a policy is wrong, adjust the code and redeploy. Login uses a five-minute IP/account cooldown, not a permanent account block.

## Memory pressure or unexpected command volume

Check Upstash usage and Vercel function request counts. All active keys carry an expiry. Search for keys only with a narrow `smetra:{environment}:...` prefix and bounded `SCAN`; never use `KEYS *` in production. The limiter costs one atomic Redis command per dimension. No cache or job queue is currently enabled, so growing memory indicates abnormal traffic or a missing TTL.

## Credential exposure and rotation

Treat any token pasted into chat, a ticket, log or Git as compromised. Rotate the Upstash REST write token in Upstash, replace `REDIS_KV_REST_API_TOKEN` in Vercel Production and Preview, then redeploy both. Keep the old token active only during the brief transition if the provider supports overlap; revoke it immediately afterward. Verify a read-only health probe or a temporary namespaced smoke test, then check ordinary and AI requests. Do not commit a token to `.env.example` or Android code. Rotate the TCP password too if it shared the exposed value, even though this application uses REST.

## Accidental flush or provider outage

Do not restore business data from Redis. It contains only expiring coordination keys; the next requests rebuild them. Confirm that accounts, quotes, files, payments, and subscriptions still read from PostgreSQL. Some in-flight AI leases can vanish and allow a second run, but monthly and daily PostgreSQL usage limits remain active. Provider and database idempotency continue protecting payments and applied assistant actions.

## Jobs and cache

There is no Redis-backed worker or cache to restart. Do not enqueue background work until a durable PostgreSQL job record and a real consumer exist. Profile PostgreSQL before proposing any dashboard or search cache.
