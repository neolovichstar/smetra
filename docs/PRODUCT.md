# Product decision — Smetra

Research date: 2026-09-27. These are hypotheses for customer interviews, not measured demand or verified ARPU. Official competitors show that commercial proposals exist in large CRMs: Bitrix24 documents this feature at https://helpdesk.bitrix24.ru/open/23285208/ and describes broad CRM capabilities at https://www.bitrix24.ru/features/crm/. This validates the workflow's existence, not market size or willingness to pay for a separate tool.

| Option | Customer and recurrent problem | Competing approach | Differentiation | First customers | Price hypothesis | Retention | Build/risk |
|---|---|---|---|---|---|---|---|
| Smetra: quotes and approvals | Freelancers and service shops send prices in chat and lose the decision | Full CRM or PDF | One concise quote, link, client approval | Direct outreach to local specialists | 490 RUB/month | New client requests | Moderate; approval is not a legal signature |
| Listing margin tracker | Marketplace sellers struggle with unit margin | Spreadsheets and seller analytics | Cost inputs with per-order margin | Seller communities | 790 RUB/month | Daily sales | High; marketplace API and data quality |
| Telegram content calendar | Channel owners miss planned posts | Telegram scheduled posts, bots | Approval and content workflow | Channel owners | 590 RUB/month | Weekly posting | Medium; platform permissions |
| Vehicle service notebook | Small fleets lose service history | Spreadsheets and fleet software | Mobile service log | Local auto shops | 790 RUB/month | Monthly maintenance | High; multi-user ops and acquisition |
| Creator asset organizer | Creators lose versions of files | Cloud drive, project tools | Versioned deliverables with client approval | Freelancers | 490 RUB/month | Repeated projects | High; storage and abuse cost |

Smetra wins the first build because value is available on the first proposal, distribution can start with a handful of service professionals, and the core workflow has no marketplace/network dependency. The narrow product will compete on speed and simplicity, not claim features of a full CRM. The name and trademark availability have **not** been checked; validate before public release.

## Positioning

Name: Сметра / Smetra. Tagline: «От расчёта до согласия клиента». Voice: direct, restrained, practical. SEO title: «Сметра — предложение клиенту за несколько минут». SEO description: «Создайте предложение с ценой, отправьте ссылку клиенту и отслеживайте согласование».

## Business model and targets

Free: 10 total quotes. Pro: 490 RUB for 31 days or 4,900 RUB for 366 days, manual renewal only. There is no auto-renewal or team feature. Trial is the useful free allowance. No enterprise tier until buyer demand exists.

Hypotheses to validate: activation = first sent quote within 24 hours; North Star = customer-approved proposals per active seller per month. D1/D7/D30 retention measured from signup by return to the product; paid conversion target 4%, monthly paid churn target below 7%, first month CAC target below 1,000 RUB. At 490 RUB/month, 7% churn implies naive lifetime revenue near 7,000 RUB before fees and taxes; this is a planning assumption, not a forecast. Test price with at least 20 buyer conversations before paid acquisition. Do not count user-generated quote amount as Smetra revenue.

Events stored: signup_completed, quote_created, quote_sent, quote_accepted, quote_declined, quote_completed, checkout_started, payment_succeeded/canceled. Admin shows aggregate user, paid access, and historical payment amount. A full funnel/retention dashboard is not implemented.

## First customer plan

Interview 15 local repair specialists, developers, and designers. Ask for their most recent five proposals, time to prepare, and actual acceptance path. Onboard 10 manually. Observe creation and link sharing, then ask for payment only when the free limit becomes relevant. No invented testimonials.
