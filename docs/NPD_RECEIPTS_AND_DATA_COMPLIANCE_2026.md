# NPD: operational receipt delivery and fiscalization boundaries (2026-10-26)

## Current status

YooKassa confirms payment but **does not register income or issue tax receipts in FNS Мой налог for self-employed merchants**. Never send an HTML order confirmation as though it were a tax receipt.

The SQL table `smetra.npd_receipt_deliveries` is an idempotent tax receipt checklist keyed by a **YooKassa-verified non-test payment**. Upon a successful payment transition, the server creates one `awaiting_tax` record. The operator (or a future authorized FNS NPD partner) must **first create the tax receipt** and verify it matches the payment and actual customer type.

Only an administrator can attach an official FNS link via `POST /api/admin/npd/receipts`, JSON:
`{"payment_id":"<internal payment UUID>","receipt_url":"https://lknpd.nalog.ru/api/v1/receipt/713304603876/<approved receipt id>/print"}`.
The request requires the same authenticated admin session, CSRF / origin checks and rate limits as other admin actions. Successful attachment triggers delivery by configured SMTP, and the authenticated daily maintenance cron attempts remaining queued deliveries. Get the list via `GET /api/admin/npd/receipts` (admin only). Error conditions are visible as `needs_review`; uncertain deliveries remain for manual review instead of blindly resending.

**Do not invent receipt URLs, use private FNS login tokens, reverse-engineered password authentication, or treat a YooKassa payment as fiscalization.** The current integration deliberately does not automatically create a fiscal receipt. This requires approval and merchant authorization in an authorized NPD partner bank/platform, including consent in Мой налог, plus documented credentials and verified API responses. No credentials are present in this repository.

Refunds switch the record to `refunded`, requiring **manual FNS receipt cancellation/adjustment** or a future authorized provider; a payment refund alone does not cancel the tax record.

## Required next steps to complete full automatic FNS issuance

1. Choose an FNS-authorized credit institution/platform offering an API for **incoming subscription payments from another PSP** (not merely payment to a self-employed contractor).
2. Confirm whether the operator's age and merchant classification are supported, and grant authorization in the My Tax application.
3. Specify fiscal buyer category correctly (individual vs legal entity), NPD treatment, callback ID and idempotency keys.
4. Add a signed/authenticated tax-provider adapter returning real FNS receipt IDs; verify receipt amount and tax status before queuing customer email.
5. On a successful refund, call authorized cancellation and reconcile status with FNS.
6. Test live small-payment + duplicate YooKassa webhooks + email retries + refund and tax correction. Never enable an adapter using untested production credentials.

## Personal data audit: urgent architectural issue

Production Supabase project is in eu-central-1 (Germany), and Vercel functions are in fra1. These facts alone mean compliance with personal data collection localization obligations for RF citizens is **not confirmed**. A Russian-resident collection/recording/storage architecture and, where necessary, cross-border processing notices must be assessed and implemented before asserting compliance. Avoid deploying another foreign data copy as a purported remediation; do not change production database hosting without a tested cutover and backups. Audit OpenRouter payloads, Cloudflare, Upstash, Yandex ID, SMTP, Android MyTracker/Ads, log/backup retention and transfer conditions. Verify РКН operator and cross-border notices.

FNS source: https://npd.nalog.ru/
YooKassa source: https://yookassa.ru/developers/payment-acceptance/receipts/basics
