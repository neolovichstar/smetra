# Этап 1 — карта инженерной реализации backend v2

Статус: спецификация задач, не исполненный релиз. Исходные данные: GitHub + read-only инспекция Supabase 24.10.2026.

## Приоритет P0 — до новых функций

| Задача | Конкретный результат | Критерий приемки |
| --- | --- | --- |
| P0-01 Зафиксировать старую модель | Инвентаризация quotes, quote_items, quote_versions, workspaces, memberships и текущих публичных маршрутов | Все существующие сценарии внесены в контракт совместимости |
| P0-02 Контроль версий | Единый критерий quote_id + published_version + snapshot hash | Любая устаревшая операция получает conflict без побочных эффектов |
| P0-03 Функциональные тесты расчетов | Эталонные тестовые наборы для quantity × unit price, rounding, tax, discount и optional | Отсутствие расхождения в 1 копейку |
| P0-04 Tenant scope | Ролевые и RLS проверки собственного runtime | Попытки cross-workspace доступа и чужого approval отклоняются |
| P0-05 Инвентаризация тарифов | Реестр active entitlement, legacy Pro, seat_limit, 10 free quotes и rewarded-credits | Серверное решение по доступу одинаково во всех маршрутах |

## Приоритет P1 — публикации и приглашения

| Задача | Конкретный результат | Критерий приемки |
| --- | --- | --- |
| P1-01 estimate_shares | Новая запись по конкретной паре quote/version и получателю | Любой share не может открыть другую версию |
| P1-02 Invitation security | Хеш токена, TTL, отзыв, recipient email verification, idempotency | Перехваченный либо истекший токен не расширяет доступ |
| P1-03 Outbox foundation | Событие в той же транзакции, что и share; доставка отдельно | Simulated failure после commit не теряет уведомление |
| P1-04 Email delivery | Resend + подписи webhooks + bounces + suppression + дедупликация | Ретрай не отправляет дублирующих писем |
| P1-05 Compat bridge | Старые /api/public/* живут параллельно новым защищенным маршрутам | Старые RuStore-клиенты не получают 404/500 |

## Приоритет P2 — предложение клиента и согласование

| Задача | Конкретный результат | Критерий приемки |
| --- | --- | --- |
| P2-01 proposal model | estimate_proposals, proposal_items, revision и parent share | Разрешены изменения только optional строк |
| P2-02 Стабильные line_id | Ссылки на line_id из snapshot, а не quote_items.id | Edit/save не ломает связи уже отправленной версии |
| P2-03 Calculation runs | Контроль входного hash, formula_version и rounding policy | Результат повторяется и соответствует backend |
| P2-04 Approval protocol | Неизменяемый approval_event + accepted snapshot | Нельзя утвердить иную/устаревшую версию |
| P2-05 Уведомление исполнителю | outbox → push/email/realtime после commit | Нет уведомлений об откатившихся утверждениях |

## Приоритет P3 — тарификация и нагрузка

| Задача | Конкретный результат | Критерий приемки |
| --- | --- | --- |
| P3-01 Quota ledger | Отдельные grant/consume по workspace и source | Два конкурентных create не обходят лимит |
| P3-02 Active entitlement | Матрица feature/role/status/expiry без доверия клиенту | Переключение workspace мгновенно меняет права |
| P3-03 Очереди задач | Postgres durable job + Redis lease/queue | Повтор выполнения не изменяет результат дважды |
| P3-04 Realtime | Broadcast ID+revision вместо полных snapshots | Клиент восстанавливается после потери событий |
| P3-05 Наблюдаемость | RPS, p95, latency, job retries, dead-letter, cost/workspace | Нагрузка и расходы доступны по tenant/feature |

## Неприкосновенные требования

1. Никакого переименования quotes → estimates в production.
2. Никакого переноса users в отдельную новую таблицу profiles при отсутствии миграционного обоснования.
3. Никаких удалений старых public_token/quote_versions до окончания переходного периода.
4. Никаких клиентских сумм как источника истины.
5. Никаких платежей, email или push до фиксации бизнес-транзакции.
6. Никаких продакшен-миграций до проверки rollback plan и restore.
7. Никаких сервисных секретов и производственных персональных данных в GitHub.

## Проверенные факты / открытые вопросы

**Проверено:** существуют quotes, quote_items, quote_versions, workspace_members, push_outbox, subscriptions, assistant_jobs; у таблиц включен RLS; четыре целевые проверки целостности не обнаружили нарушений; код уже содержит publish, public_view и accept по ссылке.

**Не проверено:** сквозная доставка Resend, юридически значимое согласование, фактическая готовность к 300k MAU, все tenant-политики под нагрузкой, восстановление резервной копии, поведение текущих RuStore APK с новым API.

**Следующее действие разработчика:** начинать с P0-02/P0-03/P0-04, затем проектировать новую передачу share (P1-01). Не включать новую approval-семантику, пока не готова проверка версии и расчетов.


## P0 implementation progress — 24 October 2026 (iteration 1)

Implemented and unit-tested:
- The new quote-integrity backend module calculates a stable SHA-256 fingerprint for the complete published estimate snapshot. This is a version identifier, not an authorization token or evidence of recipient identity.
- Before publication, the server recalculates persisted itemized quotes and checks grand total, internal cost, and line subtotals, tax and cost. On mismatch, it aborts with HTTP 409, without creating an immutable version or changing status.
- The public quote API returns snapshot_sha256, computed from the saved version before private values are removed. A browser submits it when responding; malformed or stale supplied hashes are rejected with HTTP 409. For older RuStore clients this field remains optional.
- Public web client passes the viewed snapshot hash on response and supports a legacy API fallback.
- Regression tests cover money rounding, optional rows, invalid snapshots, foreign workspace access, stale and malformed approvals, and rollback after rejected publication.

Verification: 20 focused quote/version/integrity/API regressions passed; six existing calculation tests passed; web build, Python compilation, and JS syntax checks passed. The entire integration suite was not certified in this sandbox because PDF and PostgreSQL optional dependencies are not installed.

Important limitation: the legacy public approval still relies on the bearer public_token and an unverified name. Snapshot hashes do NOT solve recipient identity. A verified share-recipient model is required before treating approval as authenticated client consent.

No database schema was changed. Backwards compatibility is intentional.
