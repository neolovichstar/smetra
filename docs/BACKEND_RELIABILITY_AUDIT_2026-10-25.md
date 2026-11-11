# Backend reliability audit — 2026-10-25

This iteration extends the security and performance work in PR #64. It concentrates on external-provider trust boundaries, chat completion semantics, import isolation, monetary accuracy, and outage behavior. Frontend source and browser assertions are unchanged. This is a source audit with regression tests, not a certification that every possible defect or attack has been eliminated.

## Confirmed defects and changes

| Area | Previous behavior | Result |
| --- | --- | --- |
| Payment API | Unbounded JSON reads; duplicate keys, arrays, overflow floats accepted; raw upstream exceptions logged | 100 KB response bound, strict object parser, required nested payment/refund structures and checkout redirect validation, sanitized error type and request ID; invalid responses become 502 |
| JSON boundaries | Request validation and provider validation differed; several clients accepted ambiguous or non-object JSON | Shared UTF-8 parser rejects duplicate keys, non-finite numbers, invalid Unicode/NUL, excessive nesting and non-object roots |
| Chat completion | Empty model output became “Данные проверены”, was saved in history, and consumed quota | Empty, refused, truncated and malformed answers fail with 502; synchronous failure refunds the reservation and saves no fake history |
| Tool calls | Malformed functions, duplicate IDs, non-object/ambiguous arguments could reach execution or crash | Validate complete calls and arguments before tool execution; at most four calls, bounded names/IDs/arguments |
| Streaming | Non-object events crashed; line iteration could allocate an unbounded line; content size was recomputed quadratically | Bound each line to 64 KiB and total stream to 300 KB, validate chunk shapes/indices, count output incrementally, require DONE, reject empty/truncated output |
| Proposal persistence | Synchronous proposals could be written before the answer's final access/commit fence | Persist proposals with history in the final transaction; restore per-answer deferral state on success or failure |
| XLSX import | Parser ran in the API process; missing dimensions caused TypeError/500; dimensions could hide out-of-range rows | Existing credential-free subprocess now handles imports; actual XML row/cell positions are checked before bounded workbook iteration, independent of dimensions |
| Tabular headers | Duplicate headers overwrote values; unnamed or surplus columns could disappear silently | Reject duplicate/empty headers, values below unnamed XLSX columns and surplus CSV fields |
| Imported money | int(value) silently truncated fractional Excel prices and converted True into 1 | Reject fractional kopecks, booleans and unsupported types; retain integral Excel values and integer strings; failed imports roll back all rows |
| Draft success | Activity/usage could say success before client/description/terms validation | Validate the entire returned draft before success metadata or activity |
| Provider usage | Huge or negative token counts could overflow DB columns or create misleading usage records | Accept only non-negative 32-bit integer counts; otherwise explicitly record usage_unknown with zero stored counters |
| Database outages | Pool exhaustion/operational failure was indistinguishable from a programming error | Return sanitized 503/database_unavailable with Retry-After: 5; syntax/programming errors remain 500; no automatic replay |
| Request timeouts | A body-read timeout became 500 and could leave the connection reusable | Return 408 and close the connection |
| Redis configuration | Preferred URL and legacy token could be mixed; a production lock could silently become a no-op | Credential pairs are selected atomically; incomplete pairs fail; missing/disabled production coordination fails closed for lock users |

Shared JSON validation is used by inbound bodies, payments, OAuth, synchronous AI drafts, chat/SSE, both OCR clients and isolated parser results. Provider byte limits remain specific to each client. OCR explicitly rejects truncation/refusal; omission of finish_reason remains accepted for existing compatible provider envelopes.

## Resource and transaction properties

- XLSX import retains its existing 45 KB input, 100-entry, 5 MB expanded archive, 200 data-row and 30-column limits. The child additionally uses existing XML/active-content checks and parser constraints: 384 MiB address-space limit and 15 CPU seconds on supported Unix hosts, plus the parent-enforced 25-second timeout and bounded output.
- The child receives Python/OS essentials, not application database, payment or model credentials. Spreadsheet formulas are not evaluated.
- Imports still use the existing write transaction. A later invalid price or row rolls back earlier valid rows. The isolated interpreter adds process-start overhead; no import-speed improvement is claimed.
- Chat quota is still read fresh from the database. Unknown provider token metadata is not presented as measured zero usage or as a successfully measured response.
- Production must have a complete, enabled Redis configuration for model/file coordination locks. Development/test without Redis remains supported.
- Provider failures are not retried automatically by the synchronous API. Durable jobs retain their existing bounded retry, cancellation, lease and refund logic.

## Intentional fallbacks retained

| Fallback/recovery | Why retained |
| --- | --- |
| Local SQLite when no cloud database is configured | Explicit local runtime, not a silent switch after a PostgreSQL failure |
| Direct PostgreSQL connection when optional pool package is unavailable | Same configured database and permissions; does not substitute data or skip authorization |
| Database rate limiting when Redis is not selected | Atomic database enforcement remains authoritative |
| Confirmation without Redis after a Redis failure | Transaction/action-row state still prevents duplicate application; no unguarded model call |
| usage_unknown when provider accounting is missing/invalid | Explicit uncertainty; valid business output need not fail because optional accounting metadata is broken |
| Redis lease-release recovery through TTL | The owner token and expiry preserve lock ownership; cleanup failure does not fabricate business success |
| Optional analytics/push delivery failure paths | No replacement of authoritative payment, identity, business data or access checks |
| Rollback/resource-cleanup exception handling | Necessary cleanup, not a replacement result |

Broad exception handlers were examined by their effect. Cleanup, sanitized job failure handling and optional delivery recovery were retained rather than mechanically deleted.

## Audit coverage and evidence

| Surface | Focus in this iteration |
| --- | --- |
| HTTP/auth/billing | JSON parsing, timeouts, payment response bounds, OAuth response shape, sanitized errors |
| Assistant/drafts/tools | Provider finish states, malformed tool payloads, fake success, usage bounds, transactional proposals |
| SSE and durable work | Fragment reassembly/bounds, disconnect/error paths, existing worker commit/cancellation/lease boundaries |
| Files/import/export | Existing parser isolation and archive checks, XLSX import isolation/dimensions, CSV/XLSX ambiguity, integer prices |
| Database/Redis | Pool/driver outage classification, production lock fallback, credential precedence; existing transaction/scope cleanup reviewed |
| Team/business/construction | Full existing calculation, permissions, privacy, quote/version and construction regressions retained |
| Push/analytics | Bounded optional delivery and sanitized failure behavior reviewed; prior recipient-access fix retained |

29 new regression methods in tests/test_backend_reliability.py include adversarial subcases. The existing fragmented-tool SSE fixture now implements the real bounded readline interface using BytesIO.

Validation of the final tree:

- Python unittest discovery: **438 cases, 437 passed, one optional disposable-PostgreSQL/RLS test skipped**.
- Focused boundary/import/draft regressions passed after final cleanup.
- Repository-wide Ruff, Python compileall and git diff --check passed.
- No frontend edits and no assertions weakened to hide the known browser failure.

The first six reproductions were run against the preceding code and exposed 11 failed assertions and one uncaught AttributeError across subcases before the fixes. New tests also prove full import rollback, absence of fake chat history/quota consumption, rejection before proposal commit, and sanitized outage payloads.

## Remaining limits and release state

- The optional test requiring a disposable PostgreSQL database was not run here. Earlier live RLS role-assumption checks were blocked by the connector principal; permissions were not widened.
- External providers are mocked for malformed/time-out/stream scenarios; this does not establish production latency, provider availability, or all proxy behavior.
- HTTP timeouts bound individual I/O operations. A provider sending a long slow stream does not yet have a separate absolute wall-clock deadline.
- Legacy synchronous draft/receipt OCR and import routes still operate within request transaction architecture. Moving all remote I/O outside transaction lifetimes is a separate architectural change requiring PostgreSQL concurrency testing.
- The backend still has large HTTP/service modules and a SQLite-to-PostgreSQL compatibility layer. This iteration removes concrete unsafe behavior and duplication; it does not claim a complete framework rewrite or proof of race freedom.
- The preceding GitHub CI head passed Python/backend checks but failed the existing mobile navigation geometry assertion at tests/browser_flows.cjs:85. This iteration does not alter that frontend test.
- Python changes remain on the PR branch and require merge/release. No Python production deployment, new live database migration, or frontend change was performed in this iteration. Earlier performance indexes/RLS optimizations remain live as described in SERVER_PERFORMANCE_2026-10-25.md.
