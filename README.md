# Сметра

Сервис для составления предложений на работы и согласования по ссылке. Русский адаптивный веб-интерфейс, JSON API, SQLite, нативный Android-клиент на Java. Это работоспособная исходная база, **не подтверждённый коммерческий релиз**. До запуска обязательны задачи в разделе Known limitations.

## Requirements

Python 3.11+, Node.js only for JavaScript syntax check, Android Studio / SDK 35 + Gradle 8.9 + JDK 17 for Android. Backend uses Python standard library only. HTTPS-capable VPS and persistent disk are needed for public deployment. SQLite on a stateless Vercel function is unsupported here.

## Installation and development

1. Unzip the project and copy `.env.example` to `.env`.
2. Set `PUBLIC_ORIGIN` to the exact public HTTPS origin before deploying. For local use keep `http://localhost:8080`.
3. Windows: double-click `START.bat`. It creates `.env` when missing, initializes the DB, and starts at `http://localhost:8080`.
4. Other systems: `python3 backend/launcher.py`.
5. Open `/app`, register, create a quote, click **Отправить**, copy its link and approve it in a separate browser session.

No dependency installation is needed for the web/backend. The server creates the SQLite schema from `backend/schema.sql` on boot. Existing v1 databases receive additive columns on boot; back up first. This is not a general versioned migration system for future schema changes.

## Environment variables

| Name | Use |
|---|---|
| `PORT` | HTTP port, default 8080 |
| `PUBLIC_ORIGIN` | Absolute origin for links, cookies and CSRF check |
| `DB_PATH` | Persistent SQLite DB path; use an absolute path on VPS |
| `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` | Enables real web checkout; no test credentials included |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | STARTTLS SMTP for verification and recovery; required on public origin |

Registration on a public HTTPS origin requires SMTP; verification links expire after one day. Password reset links expire after 30 minutes and revoke existing sessions. Local `http://localhost` without SMTP marks test accounts verified. Real SMTP delivery is NOT VERIFIED. **Do not accept payments until the provider sandbox and legal documents are completed.**

## Web build and API

Static HTML/CSS/JS is served directly by Python. There is no bundler. `node --check apps/web/app.js` verifies JavaScript syntax. Public page `/`, account `/app`, admin `/admin` (redirects to protected admin view), privacy `/privacy`, terms `/terms`, health `/health`.

| Endpoint | Method | Function |
|---|---|---|
| `/api/auth/register`, `/api/auth/login`, `/api/auth/logout` | POST | Create account, log in, revoke session |
| `/api/auth/verify`, `/api/auth/verify/resend`, `/api/auth/reset/request`, `/api/auth/reset/confirm` | POST | Email verification and password recovery |
| `/api/me` | GET, DELETE | Profile and deletion |
| `/api/quotes`, `/api/quotes/{id}` | GET/POST, PATCH/DELETE | Search/list/create and status/remove |
| `/api/public/quote`, `/api/public/accept` | GET, POST | Open and approve by secret URL token |
| `/api/billing`, `/api/billing/checkout`, `/api/billing/sync` | GET, POST, POST | Payments, web checkout, verified sync |
| `/api/webhooks/yookassa` | POST | Provider notification with server-side GET verification |
| `/api/support`, `/api/admin/overview`, `/api/admin/users/{id}` | POST, GET, PATCH | Tickets and RBAC administration |

Cookie sessions use HttpOnly and SameSite=Lax. Android uses Bearer tokens. Sessions have 30-day expiry. Passwords use scrypt. IDs and public tokens use UUID/random bytes. All SQL parameters are bound. The Android token is currently stored in app-private preferences and should be moved to Keystore-backed storage before release.

## Database setup and backup

Fresh install: `python3 backend/admin.py <registered-email>` after registering an administrator. This command grants the admin role and records an audit entry. Back up SQLite with `sqlite3 /path/database.sqlite3 '.backup /secure/backup.sqlite3'`, test restore periodically, encrypt and restrict backups. Run a single server instance against one local persistent disk; do not put SQLite on shared network storage.

Tables: users, sessions, email_tokens, quotes, payments, refunds, events, support, audit. Foreign keys and indexes are in `backend/schema.sql`. Money is stored in integer kopecks; timestamps are UTC Unix seconds.

## Testing and production build

`python3 -m compileall -q backend`

`python3 -m unittest discover -s tests -v`

`node --check apps/web/app.js`

On Windows `BUILD_PRODUCTION.bat` runs these gates, then attempts Android debug and signed release builds. Missing Android tools/signing credentials cause a nonzero exit. GitHub Actions run the source tests and Android debug build, but the remote CI has not been executed here.

## Android build

See `RUSTORE_PUBLISHING.md`. Native Android source is in `apps/mobile`. Configure `-PapiBaseUrl=https://YOUR_DOMAIN`, then run `gradle -p apps/mobile assembleDebug`. For release set `SIGNING_STORE_FILE`, `SIGNING_STORE_PASSWORD`, `SIGNING_KEY_ALIAS`, `SIGNING_KEY_PASSWORD`, then run `gradle -p apps/mobile assembleRelease bundleRelease -PapiBaseUrl=https://YOUR_DOMAIN`. Use the same keystore for updates. Android contains registration, login, quote creation/list/status, share sheet, support, access status and deletion. No in-app checkout.

## Production deployment

Read `DEPLOYMENT.md` and `PAYMENTS.md`. A real domain, TLS, SMTP email flows, legal identity and provider agreement are prerequisites. Do not treat the example origin, legal text or unbuilt Android project as publication-ready.

## Troubleshooting

- `503 Оплата пока недоступна`: set valid YooKassa credentials and restart.
- `403 Неверный источник`: set `PUBLIC_ORIGIN` exactly to the browser origin including scheme.
- `401 Сессия истекла`: log in again.
- `Gradle is missing`: install Android Studio, SDK 35 and Gradle 8.9.
- Android cannot connect: supply a reachable HTTPS URL; `localhost` on the phone is the phone itself.

## Known limitations

No verified production payment, partial-refund handling, real email delivery, mobile secure token storage, push, full event analytics dashboard, versioned migrations, automated cleanup or deployment. The product and name have not been validated with paying customers or trademark search. The **entire** release should be reviewed for Russian personal-data and consumer-law requirements by a qualified specialist. Full-refund accounting still requires a real provider sandbox test; partial refunds need a supported workflow before taking money. See `SECURITY.md`.
