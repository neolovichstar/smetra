# Security notes

This is an implementation status, not a security certification.

Current threat model, unresolved risks and verification status: `docs/THREAT_MODEL.md`, `docs/SECURITY_TEST_STATUS.md`. Incident and credential rotation procedure: `docs/INCIDENT_RESPONSE.md`.

## In place

- PostgreSQL stores production data in a private `smetra` schema with row-level security; application queries use bound parameters and ownership checks. Administrator permissions come from the database role.
- Passwords use salted scrypt hashes. Sessions and public estimate links use random tokens. Browser sessions use `HttpOnly`, `Secure`, `SameSite=Lax` cookies; browser login responses omit the bearer token. Android stores its bearer token encrypted with an Android Keystore AES-GCM key.
- State-changing cookie requests check `Origin` or same-origin Fetch Metadata, and reject cross-site/same-site requests. JSON endpoints accept only `application/json` bodies and reject duplicate keys. Ordinary requests are capped at 64 KiB; the AI Capture request is capped at 3 MiB for a file of up to 2 MB. Authentication and sensitive actions have rate limits shared through PostgreSQL in production.
- Production pages and API responses send CSP, frame denial, MIME-sniffing protection, restrictive referrer and browser permissions policies. Vercel serves production over HTTPS with HSTS. User-provided strings are escaped before insertion into HTML.
- Uploads are limited by size and permitted type. Capture checks MIME, extension and content, limits archive expansion, and parses its source in memory without storing it. Payment callbacks verify status and amount with the provider before changing local state; database transactions and idempotency protect payment processing.
- External identity providers use one-time state and PKCE. Provider accounts are not merged solely because email addresses match.
- Vercel's automatic DDoS mitigation protects the public deployment. The Vercel Firewall is enabled, and an enforcing per-IP rate-limit rule covers `/api/` and `/health` at 300 requests per 60 seconds. The managed CRS signatures for SQL injection, XSS and RCE are currently log-only; enabling the OWASP managed ruleset is unavailable on the current Vercel plan, so do not count these signatures as blocking protection. Server-side limits remain in place for account actions, public links, webhooks and AI.
- API request size, encoding and URL length are checked before opening PostgreSQL. Unknown API sections are rejected without a database connection. Duplicate payment notifications avoid unnecessary calls to YooKassa; refund notifications are matched to an existing local payment before querying the provider.
- File and PDF exports have narrower per-account limits, and public-link downloads have a separate per-IP limit, reducing bandwidth and PDF rendering abuse without restricting ordinary API reads.
- The pinned Python dependencies were audited after updating `pypdf` to 6.19.0, which includes fixes for resource-exhaustion issues in malformed PDFs. The audit reported no known vulnerabilities in `requirements.txt` at the time of this check.
- The development requirements no longer override `pypdf` with an older version. Local `pip-audit` checks of both requirement sets found no known advisories on 30 September 2026; CI now runs the audit and emits a CycloneDX Python SBOM. This is a dependency check, not a complete SAST or security review.
- Public intake submission attempts are rate-limited per IP before the token lookup, including requests with invalid tokens.

- GitHub Actions in CI/deployment are pinned to immutable commit SHAs. CodeQL is configured for Python, JavaScript/TypeScript and Java/Kotlin; Dependabot is configured for Actions, Python and Gradle. Review first remote results; configuration alone does not prove scans passed.
- Android CI attaches a versioned debug APK and checksum for QA. A separate manual signed-release workflow uses `android-release`, verifies the known certificate and creates only a draft GitHub Release. The owner must configure required reviewers and signing secrets first.

- Gitleaks v3.0.0 is configured to scan the full Git history on pushes, pull requests, and a weekly schedule, with PR comments and SARIF artifacts disabled to reduce data exposure. The initial scan on the latest branch head is pending; findings must be validated and actual exposed credentials rotated, not merely deleted from the latest file.

## Before a paid release

- Configure and test SMTP delivery, email verification, and password reset. Until then, `ALLOW_UNVERIFIED_SIGNUP=1` allows unverified email accounts so onboarding works; this is a deliberate temporary limitation.
- Configure and test the selected Russian identity providers and payment provider in their real sandboxes. The UI only offers identity providers with server-side credentials.
- Exercise backup restore, dependency and penetration testing, and load/failure behavior. Review payment-history retention and any required deletion policy.
- Review the Vercel Firewall traffic graph after each limit change. During an active attack, use the Vercel dashboard's temporary Attack Challenge Mode; it may challenge legitimate visitors, so do not leave it on indefinitely. Recheck dependency advisories regularly.
- The current Vercel team does not expose Firewall counters through the CLI without Observability Plus. Review the Firewall dashboard for false positives after launch and adjust the 300/min threshold if real users behind a shared IP encounter 429 responses.
- Rotate all secrets previously shared in chat, including database, Vercel, GitHub, OpenRouter, and bot credentials. Keep credentials only in server environment variables or ignored local secret files.
- A read-only production configuration check found no `USAGE` on the private `smetra` schema for `anon`/`authenticated`, and no direct client-readable production tables. The `smetra_app` and inherited `smetra_runtime` roles do not have `BYPASSRLS`; 10 internal tables need a table-by-table review because `FORCE ROW LEVEL SECURITY` is not enabled on them. This snapshot is not proof of complete isolation. Tenant isolation also depends on explicit workspace authorization and scoped runtime transactions; commission an independent database/API isolation review before scale-up.
- Production database URLs, Redis credentials, OpenRouter key and Yandex OAuth secret are now scoped to Production only in Vercel; new Preview deployments do not receive these production credentials. Existing Preview deployments created before the scope change retain their original deployment environment until redeployed or retired, so verify/redeploy older previews. `YANDEX_CLIENT_SECRET` remains a readable Config-type variable in Production and must be rotated/recreated as a Secret through Vercel's dashboard; its value was not retrieved.
