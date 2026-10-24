# Backend hardening — 24 October 2026

Environment: feat/ecosystem-release-20261024, Vercel Production, PostgreSQL smetra and Upstash Redis.

## Fixed bugs
- Email OTP previously revoked the earlier still-valid code before it knew whether VK WorkSpace SMTP had accepted a replacement message. A transient SMTP error left users without a usable code. Now older codes are invalidated only after successfully delivering the new message. On failure, the new challenge is deleted and older codes stay valid.
- PostgreSQL accumulated expired email codes, OAuth states/tickets, sessions, password-reset tokens, and old rate-limit keys. Added authenticated bounded daily maintenance to remove only expired transient records.
- Scheduled product-monitor and cloud-sync jobs existed without CRON_SECRET; configured a strong production-only secret (not in source or logs).
- Invalid cron credentials are rejected before allocating database connections.

## Retention table

| Table | Retention after expiry or last usage | Daily limit |
| --- | --- | --- |
| email_login_challenges | 2 days | 4,000 |
| email_tokens | 7 days | 4,000 |
| oauth_states | 2 days | 4,000 |
| oauth_tickets | 2 days | 4,000 |
| sessions | 7 days | 4,000 |
| rate_limits | 120 days | 4,000 |

The rate_limits table also carries monthly AI counters, so it is retained far beyond the monthly billing window. Review this rule if annual quota counters are introduced. The cleaner does not touch estimates, user accounts, payments, audit records, jobs, or outbox events.

## Database and operations
Migration 54 adds indexes for expiry columns of sessions, email_tokens, oauth_states, oauth_tickets, and started for rate_limits. Existing rows and policies were preserved.

Vercel invokes /api/cron/maintenance once daily at 04:10 UTC. Production CRON_SECRET is required through a server-only Authorization bearer token. The job is repeatable and bounded to 4,000 deletes per table.

Confirm first execution with Vercel Runtime Logs; check route HTTP 200 and removed counts. To disable the cleaner, remove its Vercel cron entry without destroying data.

## Verification
52 focused tests passed. Web build passed. The 84-test backend suite was also run, but eight scenarios depended on missing optional PDF/PostgreSQL packages in the sandbox and were not certified. Real-world 300k-MAU readiness requires production-shaped staging load tests; not yet established.
