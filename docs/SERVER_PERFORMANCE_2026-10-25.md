# Server and chat performance — 25 October 2026

## Implemented code changes

- Monthly AI quota is read in one fresh SQL statement, including the base counter, referral reward total and eligible purchase-credit counters. Paid quota previously required four sequential database queries; free quota required two. No cross-request quota cache was added, and reservation/refund transactions remain authoritative.
- Chat completion returns the quota/result already built in its final transaction instead of immediately calculating the same quota a second time.
- Dashboard action-center counts/settings are batched. Card queries stop once the existing eight-card response is full, preserving group priority and response shape.
- Warm PostgreSQL client connections may remain idle for 60 seconds instead of five seconds. The default maximum remains two connections per process, with the same maximum lifetime, transaction-local scope, return/rollback handling and authentication checks.

## Applied to the connected production database

Two additive migrations were applied:

1. chat_read_indexes: four tenant-scoped indexes for ordered message history, pinned thread lists, pending proposals and recent applied actions.
2. runtime_context_read_performance: hoists the row-independent current_setting workspace value into a scalar subquery for 14 existing policies, including object chats and cloud files. The exact transformation is reversible and keeps role lists, commands, USING/WITH CHECK and row-dependent membership predicates.

Post-apply metadata checks confirmed all four indexes and all 14 policy read/write guards and runtime role restrictions. Supabase Performance Advisor's 14 auth_rls_initplan warnings disappeared. The four pre-existing multiple_permissive_policies warnings on rate_limits remain; they were not changed in this task. Guidance: https://supabase.com/docs/guides/database/database-linter?lint=0006_multiple_permissive_policies

A role-switched live RLS check was attempted, but MCP's database principal is not allowed to SET ROLE smetra_runtime. No extra privileges were granted to bypass that restriction. Policy verification therefore covers metadata and exact predicate preservation, not a complete live end-to-end RLS test.

## Measured query budgets

These are controlled test-fixture results, not claimed production page-load timings.

| Operation | Before | After |
| --- | ---: | ---: |
| Paid AI quota | 4 queries | 1 query |
| Empty dashboard action center | 13 queries | 10 queries |
| Action center filled by its first two groups | 13 queries | 4 queries |
| Chat's duplicate quota read after final persistence | 1 additional quota calculation | 0 |

A 2,000-message fixture verifies general and selected-thread history reads use idx_assistant_history_scope without a temporary ordering B-tree. Quota tests update the underlying counter between calls and verify the next result immediately reflects the change.

Production query statistics showed approximately 1.5–2.1 ms mean execution time for sampled assistant history/list queries; current assistant tables are small. Reducing round-trips addresses network overhead, while the new ordered indexes primarily protect behavior as history grows. No end-to-end latency or model time-to-first-token improvement was measured, so no production speedup percentage is claimed.

## Verification and release state

409 Python unittest cases: 408 passed, one optional disposable-PostgreSQL/RLS test skipped. Repository-wide Ruff, compileall and git diff checks passed. The prior security tests remain included. Four performance regression tests were added.

The database indexes and policy optimization are live. Python code changes are saved on PR #64 and need release before they affect API responses. Frontend source was not modified. The existing mobile navigation geometry CI failure is separate from these backend changes.
