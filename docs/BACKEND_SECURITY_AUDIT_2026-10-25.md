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
