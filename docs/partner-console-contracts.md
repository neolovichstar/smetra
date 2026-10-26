# Partner console: server contracts still needed

The console (`apps/web/partner-console.js`) uses only the existing
`/api/partners/v1/console/*` routes. Where a screen needs data the server does
not return yet, the page says so and draws nothing. This file describes the
missing contracts, so each can be built as a separate, tested change.

All routes below follow the existing rules: `Authorization: Partner …` or
`PartnerSession …`, partner id taken only from the credential (never from the
request), JSON errors `{"error": "…"}`, `Cache-Control: no-store`, a per-partner
throttle, and no customer personal data in any response.

## 1. Activity journal — `GET /console/activity?limit=50&cursor=`

Screen: «История операций». Today the page builds a timeline from domain
status, product `updated_at` and commission rows.

Response:

```json
{"items": [{"id": "uuid", "at": 1793000000, "category": "domain|catalog|settings|keys|money",
            "action": "partner.domain_check", "detail": "verified", "actor": "partner|admin|system"}],
 "next_cursor": "1793000000:uuid"}
```

Source: the existing `audit` table rows whose subject is the partner id
(`partner.created`, `partner.key_rotated`, `partner.state_changed`,
`partner.catalog_updated`, `partner.domain_challenge_created`,
`partner.domain_check`). Admin identities are reduced to `"admin"`.

Security: filter by `subject = partner.id` in SQL; keyset pagination like
`commission_page`; never return admin user ids, IPs or request bodies.

Tests: two partners, each sees only its own rows; admin id never present;
cursor tampering returns 400.

## 2. Catalog search — `GET /console/products?q=&available=&limit=&cursor=`

Screen: catalog search currently filters only the loaded page.

`q`: 2–80 characters, matched against `search_name` with the escaped `LIKE`
already used by `offers()`. `available`: `true|false`. Cursor stays the SKU.

Tests: Cyrillic case-insensitive search; LIKE metacharacters escaped; other
partner's products never returned.

## 3. Remove products — `POST /console/catalog/delete` `{"skus": [...]}`

Today a partner can only set `available: false`. 1–100 SKUs, deletes only rows
with `partner_id = credential partner`, keeps `partner_outbound_clicks` history
(set `product_id` to NULL or keep a tombstone, matching the retention rules in
`maintenance.py`). Audit `partner.catalog_deleted`.

## 4. Key rotation request — `POST /console/key/rotation-request`

The console must not issue keys. This route only records a request that an
admin completes with the existing `/admin/accounts/{id}/rotate-key`. Response
`202 {"requested_at": …}`; one open request per partner; audit
`partner.key_rotation_requested`. Optional: `GET /console/key` returning
`{"created_at": …}` of the active key so the overview can say "key older than
180 days" (the prompt's «ключ нуждается в ротации»).

## 5. Campaign links (UTM)

Screen: «Партнёрские ссылки» shows campaigns as planned. Needs
`partner_campaigns(id, partner_id, slug, label, created_at)`, the redirect
`/api/partners/r/{code}/{campaign}` storing `campaign_id` on `partner_clicks`,
and `campaign` breakdown in `/console/analytics`. Until then the console must not
append parameters the server ignores.

## 6. Assistant offer statistics

The assistant now offers partner products (`backend/partner_matching.py`).
Showing «показы в ассистенте» needs `partner_offer_impressions(partner_id,
product_id, day, count)` written when the offer tool returns a product, and a
field in `/console/analytics`. Count per day only, no user ids.

## 7. Team access, roles, MFA, notifications

Needs partner user accounts separate from customer accounts
(`partner_members`, invitation tokens, roles `owner|analyst|catalog`), server
checks on every route by role, and TOTP for owners. Not to be simulated in the
browser.

## 8. Payouts

Requires the signed agreement, counterparty verification, reconciliation acts
and a separate payout service with its own audit. The console shows the pilot
state only and has no withdraw action. Nothing in the console may change a
commission status.
