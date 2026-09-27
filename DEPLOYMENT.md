# Deployment runbook

This build is designed for a single persistent Linux VPS, not a serverless runtime. Use a host and storage arrangement appropriate for Russian personal data after professional review. No deployment was performed in this task.

1. Provision a host, Python 3.11+, a domain and TLS reverse proxy (for example Caddy or nginx). Limit inbound traffic to 80/443 and SSH for administrators.
2. Extract the ZIP to `/srv/smetra`; use a dedicated OS user. Copy `.env.example` to `.env`, set `PUBLIC_ORIGIN=https://your-domain`, `DB_PATH=/srv/smetra/data/smetra.sqlite3`, `PORT=8080`. Set `chmod 600 .env`.
3. Run `python3 backend/launcher.py` locally once to initialize the schema. Register your admin and run `python3 backend/admin.py admin@example.com`.
4. Create a systemd service with `WorkingDirectory=/srv/smetra`, `ExecStart=/usr/bin/python3 /srv/smetra/backend/launcher.py`, `User=smetra`, `Restart=on-failure`, `EnvironmentFile=/srv/smetra/.env`. Note: the launcher also reads `.env`.
5. Reverse proxy the HTTPS domain to `127.0.0.1:8080`. The Python server binds on all interfaces, so restrict port 8080 at firewall level.
6. Verify `/health`, the complete quote flow and the real provider sandbox. Configure webhook URL `https://your-domain/api/webhooks/yookassa` in the provider account.
7. Set a daily encrypted SQLite backup using the online `.backup` command, retain copies off host and run a restore drill. For upgrades, snapshot DB and code first. Roll back both code and DB together after schema changes.
8. Replace `YOUR_DOMAIN` in `apps/web/sitemap.xml`, set real operator details in policies, support address and store listing. Run mobile build with that same HTTPS origin.

Staging must use a separate database, domain and provider test credentials. Do not copy real customers into staging. Structured HTTP/error logs go to the service journal. Connect external uptime/error monitoring after consent and retention review; no monitoring service is provisioned.
