# Test status (2026-09-27)

- Python compile: PASS
- JavaScript syntax: PASS
- Unit/integration API tests: PASS (local isolated DB; provider double in tests)
- Web visual browser E2E: NOT VERIFIED
- Web production build: static source, no build stage; HTTP page delivery to verify separately
- Android debug/release APK/AAB: NOT VERIFIED; Android SDK and Gradle unavailable in workspace
- Actual YooKassa sandbox: NOT VERIFIED; credentials absent
- Production deployment: NOT VERIFIED; no host or domain
- SQLite initial schema and idempotent startup: PASS
- GitHub Actions: written, not run remotely

Never interpret the local provider double as a payment sandbox test.
