# Security rollout — 11 November 2026

Target: Vercel production branch `fix/assistant-estimate-prices-20261111`.
This is an engineering checklist, not a penetration-test certificate.

## Verified at the start of the work

- Vercel firewall active. Custom API/health fixed-window guard: 300 requests/min per IP. Exploit-probe denial rule active.
- Vercel managed CRS: SQLi, XSS, RCE and generic enabled **log-only**, not blocking. Other CRS categories were inactive.
- Vercel SSO protects eligible Vercel deployment hosts, **not** the public custom domain's application admin role.
- Python auth uses salted scrypt password hashes, random opaque bearer/cookie session tokens stored as hashes with 30-day expiration; browser uses HttpOnly/Secure/SameSite cookies. OAuth state/PKCE are present. There is no requirement to substitute JWT for server-side opaque sessions.
- Request bodies and responses use security checks/headers; Vercel sets HSTS, CSP, nosniff, frame denial. No Nginx/Apache instance is required for this serverless application.
- AI work uses per-account and quota limits, concurrency locks, and per-user token accounting, but its previous interactive-chat burst cap was 12/minute.
- Drive OAuth uses Google scope `https://www.googleapis.com/auth/drive.readonly` for listing/selecting arbitrary folders and read-only sync. Google Drive client secret and token exchange are backend-side. Encrypted access/refresh tokens use a server-side key ring. Narrowing to `drive.file` without Google Picker would break access to existing arbitrary folders.
- Client Android release enables R8 shrinking/obfuscation, HTTPS is required; root checks and strict certificate pinning are not implemented. Mandatory root rejection and hard-pinned leaf certificates are not universally recommended.
- ClamAV upload scanning is optional; an actual scanner is NOT provisioned until env/config and service deployment are completed.
- Existing Python CI: Ruff, pip-audit, SBOM, unit/API/PostgreSQL tests. No formal DAST or independent ASVS audit yet.

## Added by this change

- Shared server-side 6/minute, per-account **cost-bearing** limiter across assistant chat, legacy AI draft, and newly enqueued background assistant jobs. Durable idempotent retries are not charged a second shared-limiter slot. Existing per-route limits and token allowances continue to apply.
- Legacy AI draft limit tightened from 5 to 3/minute per account.
- Sensitive long URL path segments are removed from request logs. Payment-provider exception content is no longer printed, only the exception type.
- System instructions explicitly treat documents and search results as untrusted and decline requests for hidden prompts, tool schemas and secrets. These text rules are supplemental: actual protection is enforced by backend authorization and tool validation.
- Separate Bandit SAST workflow checks high-severity, medium-or-higher confidence findings.

## Blockers and remaining release work

1. Attempting to create a dedicated AI route WAF IP rule failed with Vercel HTTP 402: this account plan does not allow adding another rate-limiting rule. Existing firewall configuration was not changed.
2. Before changing the managed SQLi/XSS/RCE rules from **log** to **deny**, verify false positives with actual construction documents, JSON tool input, and prompts containing HTML/SQL examples.
3. MFA/passkeys for admins, full tenant/role matrix and an independent access-control test still require dedicated implementation.
4. Review Google OAuth permission model; introduce Google Picker and `drive.file` only as an explicit end-to-end migration, with consent and existing-connection compatibility.
5. Backups need a recurring restore drill and limited retention; check actual cloud encryption-at-rest and incident alert wiring with their providers.
6. A real antivirus scanner, centralized SIEM/SOC alerts, and DAST checks are separate integrations with external services and must not be claimed deployed.
7. Verify annual data protection and incident obligations. If consent (rather than contract or law) is the relevant basis, collect it **separately** from terms and document its purpose, proof and withdrawal path under Article 9 of Russian 152-FZ. Operator notification status to Roskomnadzor is **not verified**.
8. Live load and payment/OAuth tests remain outstanding. Secure credentials and rotate secrets that may have been disclosed.

## Operational verification

Review workflow `Security SAST` plus existing `CI`; check Vercel production deployment SHA, errors and checkout/account/assistant actions. The SAST workflow does not by itself prevent Vercel Git pushes from deploying unless deployment checks/branch protection are configured.
