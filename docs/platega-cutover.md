# Platega payment cutover

Production is intentionally **not** switched on by committing these files.
The currently deployed YooKassa integration keeps running until the operator
configures Platega and explicitly changes the checkout provider.

1. In Platega Settings, obtain the merchant UUID (Merchant ID). Store it as
   `PLATEGA_MERCHANT_ID` in Vercel **Production** environment variables.
2. Set the Platega secret as `PLATEGA_API_KEY` using a sensitive server-only
   variable, never in source, frontend assets or logs. Rotate any key that
   has been pasted into chat or another persistent channel.
3. Configure Platega Settings → Callback URLs to
   `https://smetra.online/api/webhooks/platega`. The URL must be public HTTPS.
4. Test payment creation, the actual payment URL, a live (smallest product)
   confirmed payment, a canceled payment, the authenticated callback and the
   user's upgraded entitlement. Confirm that transaction status API returns
   the original `payload` and correct `paymentDetails` fields.
5. When verified, set `PAYMENT_PROVIDER=platega` and `PLATEGA_MODE=live` for
   Vercel Production, then redeploy the verified code to production.
6. Keep old `YOOKASSA_*` credentials available server-side until any pending
   transactions, refunds and disputes have settled. They are never used to
   create new transactions while `PAYMENT_PROVIDER=platega`.

For a controlled emergency pause, set `PAYMENT_PROVIDER=off` and redeploy.
Checkout will fail closed (503), but existing payment records remain intact.

Platega's `/v2/transaction/process` documentation does not promise a provider-
side idempotency key. Retried create operations after ambiguous network timeouts
can open multiple unpaid transaction sessions. Do not enable automatic checkout
retry or claim exactly-once remote transaction creation without verifying the
provider's idempotency guarantees. Already persisted checkouts are idempotent
per user and request key.

Platega subscription contracts/automatic debits are **not** enabled by this
one-time checkout migration. Provider-verified full chargebacks and full
refunds revoke entitlements; partial refunds and disputes are flagged for
manual review.
