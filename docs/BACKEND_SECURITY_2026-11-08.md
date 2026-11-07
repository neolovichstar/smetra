# Backend and upload hardening, 8 November 2026

Based on the actual production commit b0e42a00276e6e3aeb87e0ff9d7557990cd5002f
from fix/assistant-composer-hint-20261031. The repository default branch is
not the deployed release.

## Confirmed fixes

- PDF validation now checks action types stored as values of /S. This closes
  the annotation-action bypass for Launch, SubmitForm, ImportData, remote/embedded
  GoTo and multimedia actions. Escaped names and indirect action names are
  resolved by the parser. URI actions accept HTTP, HTTPS and mailto links.
- OOXML validation rejects DDE/remote-data Word fields, including instructions
  split across runs, dangerous Excel formulas and Excel 4 macro sheets.
  Ordinary Word page fields, Excel arithmetic and non-executing previews remain
  supported.
- AI drafting now sends PDF/DOCX/XLSX through the same credential-free,
  resource-bounded subprocess as file processing. The previous request-thread
  parsers bypassed attachment validation. Capture retains its 12-page PDF limit.
- HTTP request preflight rejects non-decimal Content-Length, GET bodies and
  unsupported nonempty body media types before allocating a database connection.

## Optional antivirus integration

backend.malware.scan_content implements ClamAV's zINSTREAM protocol.
Original uploaded bytes are scanned before image/document parsing, persistence
or transmission to an AI provider.

| Variable | Meaning |
| --- | --- |
| CLAMAV_UNIX_SOCKET | Local clamd Unix socket; mutually exclusive with host |
| CLAMAV_HOST | Scanner host |
| CLAMAV_PORT | Scanner TCP port; default 3310 |
| MALWARE_SCAN_REQUIRED | Set to 1 to require a configured, functioning scanner |

Remote TCP hosts require a TLS gateway with a trusted certificate in front of
clamd. Plain clamd TCP is accepted only on loopback. A configured scanner always
fails closed: detection rejects the file with 400; timeouts, malformed replies,
scanner errors or incomplete responses return 503. Total scanner I/O is bounded
to eight seconds and responses to 1024 bytes.

No external scanner is provisioned by this change. With no scanner configured
and MALWARE_SCAN_REQUIRED=0, scanning reports disabled; format and active-content
checks still apply. Do not set the required flag in production before providing
and testing the scanner. Existing stored files are not retrospectively scanned.

This integration does not replace updating antivirus signatures, operating the
scanner securely or maintaining the document-parsing dependencies.

## Hosting boundary

The domain's Cloudflare A/CNAME records are DNS-only. Changing Cloudflare WAF
settings would not protect current application traffic. Vercel is the live
network/application filtering boundary.

The existing Vercel API/health rate limit of 300 requests per IP per 60 seconds
is preserved. One custom deny rule was added for unsupported
TRACE/CONNECT/PROPFIND methods and conventional probes for .git, .env,
WordPress, CGI, phpunit and actuator paths. It does not challenge normal API
clients or alter OAuth callbacks, payment webhooks or DNS.

Verification on the live domain after the firewall change:

- /, /health, /api/auth/providers: 200.
- /wp-login.php, /.git/config: 403 with Vercel mitigation deny.

Rollback only the added custom rule by its name
"Smetra block unsupported methods and exploit probes"; keep the pre-existing
API burst guard. Code rollback uses the previous deployment; no database
migration is required.

## Checks

- Baseline before changes: 1165 unittest cases, 17 skips, all passing.
- Final full unittest discovery: 1184 cases, all passing, 17 environment-dependent
  skips. Focused HTTP/document/scanner tests, Ruff, Python compilation and the
  production web build also pass.
- pip-audit -r requirements-dev.txt: no known vulnerabilities at audit time.
- Scanner protocol tests use a loopback test daemon. They verify streaming,
  detection handling and fail-closed behavior; they do not claim that a real
  production antivirus engine has been installed.

References:

- https://docs.clamav.net/manual/Usage/ClamdProtocol.html
- https://vercel.com/docs/vercel-firewall/vercel-waf/custom-rules
