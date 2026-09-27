# Payments and eligibility

Current design: web checkout only. Android reads server-side access but contains no purchase action. Do not infer that an external checkout inside the RuStore app is allowed. If store review requires a different model, implement the approved store payment SDK and entitlement validation before release. RuStore documents embedded sales for legal entities and individual entrepreneurs: https://www.rustore.ru/help/developers/monetization/enable-monetization. The store's publication and monetization terms must be reviewed separately.

YooKassa states that a registered self-employed person may connect regardless of age: https://yookassa.ru/questions/q250/. It also describes account registration, agreement and tax ID: https://yookassa.ru/platezhi-dlya-samozanyatyh. This does not mean this particular account is approved. The Federal Tax Service FAQ includes age/status nuance: https://npd.nalog.ru/faq/. Check your actual account, agreement, receipt setup and legal capacity with the parties involved.

Server flow: authenticated checkout with idempotency key → provider REST create → redirect URL → provider webhook or user sync → server-side GET of payment ID with Basic auth → compare provider ID, amount, currency, user and plan metadata → atomic one-time entitlement update. Webhook body alone never unlocks access. YooKassa explicitly recommends checking current object status for webhook authenticity: https://yookassa.ru/developers/using-api/webhooks. Amounts are stored as integer kopecks, and the provider API uses decimal strings. Access has a fixed expiry and no automatic renewal.

Before live payments:

- Confirm merchant account, self-employed receipt configuration and exact receipt payload with YooKassa's test/shop setup.
- Run real sandbox checkout, success, cancellation, timeout and duplicate webhook cases.
- Verify full-refund webhook and entitlement reversal with the real sandbox. Full refunds are implemented and idempotent locally; **partial refunds still need an operational process and code support**.
- Decide lawful records retention and deletion; account deletion now pseudonymizes the account and retains the payment record, but the retention period and legal text require review.
- Document support and refund handling with operator details in the terms.

Payment sandbox was not run: no merchant credentials were provided. Tests use an isolated deterministic provider double solely to test local idempotency and access logic.
