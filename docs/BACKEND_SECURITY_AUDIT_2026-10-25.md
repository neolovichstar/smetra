# Backend security audit — 25 October 2026

Scope: backend request validation, cookie/Bearer authentication, password reset, transient AI document capture, and Python dependencies. No frontend files or database migrations were changed.

## Confirmed findings and changes

1. **Ambiguous authentication and origin-check bypass.** An empty `Authorization: Bearer ` header suppressed the cookie-origin guard, while authentication fell back to the session cookie. A request to logout with a valid cookie and that empty header succeeded without Origin/Fetch Metadata. Explicit malformed credentials now return 401 instead of using cookies. Authentication, origin checks and logout share one case-insensitive Bearer parser. This is a trust-boundary defect; the test uses a client able to set Authorization, and does not establish a general browser CSRF exploit.

2. **Outstanding password-reset links remained usable after a successful reset.** With two live reset links, either could change the password after the other had been used. Password reset now consumes every outstanding reset token for that user and revokes sessions in the same user-scoped transaction. The second link is rejected and the new password remains valid.

3. **Transient AI capture bypassed the isolated document parser.** PDF and Office documents were parsed directly in the API process, without the extraction worker's CPU, memory, wall-time and credential isolation. Capture now sends documents to that existing worker, retains the 2 MB source / 12-page PDF / 300-entry and 10 MB expanded archive limits, and applies the shared active-PDF and safe-Office validation. Real PDF, DOCX, XLSX and CSV fixtures are covered, along with active PDF, macros, XML declarations, oversized archives and timeouts. Image capture retains its existing pixel/input limits and implementation.

4. **Malformed JSON could reach application/storage code or fail with 500.** Validation now rejects float overflow, unpaired Unicode surrogates, NUL characters, excessive nesting, parser recursion and truncated bodies as 400. Empty requests with Content-Length zero still mean an empty object; ordinary Unicode and decimal numbers remain accepted. The validation walk uses bounded recursion rather than allocating another stack proportional to the number of JSON fields.

5. **Three published pypdf resource-exhaustion vulnerabilities.** Updated the exact pin from 6.21.1 to 6.21.2:
   - CVE-2026-115572 / https://github.com/py-pdf/pypdf/security/advisories/GHSA-6c7f-9265-g8fw
   - CVE-2026-115585 / https://github.com/py-pdf/pypdf/security/advisories/GHSA-jr96-gvgh-j3r4
   - CVE-2026-115580 / https://github.com/py-pdf/pypdf/security/advisories/GHSA-gmh7-3g9r-mjh5

## Verification

- Before changes: 380 tests, one skipped; the new regression checks reproduced the credential, reset and JSON problems.
- Added 13 regression tests in `tests/test_backend_audit.py`.
- `python3 -m unittest discover -s tests`: 393 tests; one skipped (requires disposable PostgreSQL admin/runtime URLs).
- `python3 -m ruff check backend tests scripts`: passed.
- `python3 -m compileall -q backend` and `git diff --check`: passed.
- `python3 -m pip_audit -r requirements-dev.txt`: no known vulnerabilities after the upgrade; the same check found the three pypdf advisories before the upgrade.

The isolated environment uses Python 3.13.16. Repository CI is configured for Python 3.12. No production database, payment provider or real model call was used for these tests. Live PostgreSQL/RLS verification and a production deployment are not implied by the local test results. This is a targeted audit and repair, not a claim that every possible vulnerability has been eliminated.


## Second pass — lifecycle, privacy and cloud query defects

Four additional defects were confirmed and repaired:

- **Unpublished document disclosure.** A document generated from private draft A remained linked to the quote after the draft was changed to public version B. The public listing and direct PDF endpoint exposed the A snapshot. Both endpoints now require a positive published version in the server-generated document snapshot, bounded by the quote's published version. Documents generated from drafts remain available to authenticated workspace users; generate a document from the published snapshot to share it. Existing published documents carry this version marker already, so no schema migration is required.
- **Revoked purchase credits could be restored.** After a full refund zeroed a gift grant, a late synchronous failure or queued cancellation restored one credit. Refunds now also expire the grant; both cancellation paths restore only unexpired grants and always undo their bonus-usage reservation. Queue refunds remain idempotent. Read-only verification found zero currently unexpired grants linked to successful refunds in the connected production database; no business-data repair was necessary.
- **In-flight background chat ignored access revocation.** Logout or changing a team member to viewer while the model was running did not stop tool execution or completion. The worker now rechecks the original live session and membership before generation, after model responses, before tools, and inside the final commit transaction. Revocation ends the job, prevents new proposals/history and refunds its quota reservation. Regressions exercise actual logout/team-role API calls during the mocked provider response. This change concerns durable background jobs; it does not claim to cancel an already-issued external provider request.
- **Purchase-bonus queries were not schema-qualified in PostgreSQL.** The adapter omitted assistant_bonus_grants and assistant_bonus_usage from its private-table registry. They are now translated to the selected smetra schema, including custom QA schemas. Read-only Supabase verification confirmed both real tables exist in smetra, the runtime role has the needed SELECT/UPDATE access, and qualified no-user test queries execute successfully. Whether an unqualified query happened to work depended on connection search_path; no live failed checkout was inferred from source alone.

Validation after the second pass: 398 Python unittest cases (397 passed, one optional disposable-PostgreSQL/RLS case skipped); repository-wide Ruff, compileall and diff checks passed. Five regression test methods were added in this pass, with multiple lifecycle scenarios.

The prior commit's GitHub CI passed Python 3.12 unit tests, dependency audit, DOM checks, web build and Android build. It failed the existing mobile navigation geometry assertion at tests/browser_flows.cjs:85. That frontend/browser-layout failure is recorded rather than bypassed; frontend source and browser assertions were not changed in this backend task.

Supabase checks in this pass were read-only. Security Advisor returned informational private-schema RLS-without-policy findings, which were not treated as proof of public access. No database schema, privileges, user records or production deployment were changed.


## Third pass — synchronous requests, retry recipients and erasure

Additional reproductions and repairs:

- Synchronous assistant requests now use the same live-session/membership validation boundaries as background chat. Streaming validates before the first content chunk, periodically while streaming (at most one-second intervals), after the provider returns, before tools and at final persistence. This prevents subsequent reads/proposals/history after detected revocation; already transmitted content cannot be recalled and an external provider call already in flight is not cancelled by this patch.
- Workspace writes refresh the actor's session and actual team role after body parsing and again inside the ordinary write transaction. Action confirmation and reversal also revalidate within their own transactions. A deterministic API regression demotes the writer after initial authentication but before the client mutation and verifies that no record is created.
- Administrative user/support mutations now reauthenticate the administrator inside a transaction after the request body has arrived. A revoked administrator can no longer grant access through a request that passed an earlier role check. The grant timestamp expression also uses a portable CASE rather than SQLite-only two-argument max.
- Push retries are no longer authorized solely by an old device snapshot. Each retry requires the current session and workspace membership; ineligible deliveries are closed, including before the no-recipient early return. A failed delivery followed by removal from the team no longer sends the next notification to that recipient. Notifications already handed to the external provider remain outside this guarantee.
- Account erasure now removes private assistant jobs, general messages, conversations, proposals, external identity bindings, OAuth handoff tickets/link states and push registrations across shared workspaces. Team-owned clients, quotes and attachments remain intact. Financial records retain the existing pseudonymous retention behavior.
- Public construction-change links now check the workspace owner's active account both before and inside the public transaction. A blocked or deleted owner cannot continue exposing or collecting approvals through this previously unguarded path.

All attack reproductions use isolated test accounts; no production account was deleted, blocked or granted access. Seven regression test methods were added in this pass, including actual logout and team-role operations, first-chunk streaming revocation, delayed administrator requests, private-state erasure and push retry exclusion.

Verification: 405 unittest cases (404 passed, one optional disposable-PostgreSQL/RLS case skipped); repository-wide Ruff, compileall and diff checks passed. The audit remains targeted: it does not establish the absence of every possible attack. No frontend files, live business data or database schema were changed. The changes are on PR #64 and require release before they protect production.

Read-only cloud metadata review also checked effective SELECT/INSERT/UPDATE/DELETE privileges (including inherited/public grants) for anon/authenticated across smetra tables and views: no effective relation privileges were found. The one authenticated SECURITY DEFINER helper, object_chat_realtime_allowed, was inspected: it checks signed JWT subject/session claims, an active stored session, current membership and workspace entitlement, and returns only a boolean. These are metadata/definition checks, not a replacement for the skipped disposable-database API/RLS integration test.
