# Test status (2026-09-27)

- Python compile: PASS
- JavaScript syntax: PASS
- Unit/integration API tests: PASS (5 tests; local isolated DB; provider double in tests; full refund, IDOR, email verification and password reset covered with local doubles)
- Web visual browser E2E: NOT VERIFIED (cloud browser cannot access localhost; no local Chromium installed)
- Web production build: static source, no build stage; HTTP page delivery to verify separately
- Android debug/release APK/AAB: NOT VERIFIED; Android SDK and Gradle unavailable in workspace
- Actual YooKassa sandbox: NOT VERIFIED; credentials absent
- Production deployment: NOT VERIFIED; no host or domain
- SQLite initial schema and idempotent startup: PASS
- GitHub Actions: written, not run remotely

Never interpret the local provider double as a payment sandbox test.
