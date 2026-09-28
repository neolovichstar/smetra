# Security notes

This is an implementation status, not a security certification.

## In place

- PostgreSQL stores production data in a private `smetra` schema with row-level security; application queries use bound parameters and ownership checks. Administrator permissions come from the database role.
- Passwords use salted scrypt hashes. Sessions and public estimate links use random tokens. Browser sessions use `HttpOnly`, `Secure`, `SameSite=Lax` cookies; browser login responses omit the bearer token. Android stores its bearer token encrypted with an Android Keystore AES-GCM key.
- State-changing cookie requests check `Origin` or same-origin Fetch Metadata, and reject cross-site/same-site requests. JSON endpoints accept only `application/json` bodies and reject duplicate keys. Ordinary requests are capped at 64 KiB; the AI Capture request is capped at 3 MiB for a file of up to 2 MB. Authentication and sensitive actions have rate limits shared through PostgreSQL in production.
- Production pages and API responses send CSP, frame denial, MIME-sniffing protection, restrictive referrer and browser permissions policies. Vercel serves production over HTTPS with HSTS. User-provided strings are escaped before insertion into HTML.
- Uploads are limited by size and permitted type. Capture checks MIME, extension and content, limits archive expansion, and parses its source in memory without storing it. Payment callbacks verify status and amount with the provider before changing local state; database transactions and idempotency protect payment processing.
- External identity providers use one-time state and PKCE. Provider accounts are not merged solely because email addresses match.

## Before a paid release

- Configure and test SMTP delivery, email verification, and password reset. Until then, `ALLOW_UNVERIFIED_SIGNUP=1` allows unverified email accounts so onboarding works; this is a deliberate temporary limitation.
- Configure and test the selected Russian identity providers and payment provider in their real sandboxes. The UI only offers identity providers with server-side credentials.
- Exercise backup restore, dependency and penetration testing, and load/failure behavior. Review payment-history retention and any required deletion policy.
- Rotate all secrets previously shared in chat, including database, Vercel, GitHub, OpenRouter, and bot credentials. Keep credentials only in server environment variables or ignored local secret files.
- The private PostgreSQL schema has RLS enabled and public/client roles revoked, but the server uses a privileged connection. Tenant isolation therefore also depends on application `workspace_id` checks; commission an independent database/API isolation review before scale-up.
