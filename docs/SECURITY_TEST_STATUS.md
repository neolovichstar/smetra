# Статус безопасности — 30 сентября 2026

`PASS` означает проверку конкретного механизма указанным тестом, а не всего класса уязвимостей. `PARTIAL` — есть защита и тесты, но существенная часть не проверена. `NOT VERIFIED` — независимой проверки нет.

| Область | Статус | Основание / пробел |
| --- | --- | --- |
| Threat model | PARTIAL | `docs/THREAT_MODEL.md` охватывает основные границы; независимый review не проведён |
| ASVS L2 | NOT VERIFIED | Формальная проверка требований по пунктам не проведена |
| Authentication | PARTIAL | Unit/API тесты сессий и cookie; реальные OAuth/SMTP/MFA не проверены |
| Authorization | PARTIAL | RBAC и workspace-тесты; полной матрицы endpoint × role × tenant нет |
| RLS | PARTIAL | Рабочие запросы используют отдельную роль без BYPASSRLS; локальный тест PostgreSQL проверил пустую область без сессии и запрет чужих строк. Продакшен-подключение роли и API smoke прошли; полная матрица таблиц не проверена |
| Cross-tenant isolation | PARTIAL | API-тесты и локальный PostgreSQL-тест для чужих клиентов и пользователей прошли; все ресурсы и сценарии приглашений не покрыты |
| Public links | PARTIAL | Тесты публикации, private file, отключения intake; полный аудит отзывов ссылок не выполнен |
| CSRF | PASS (cookie writes) | `test_browser_cookie_session_requires_same_origin_for_writes` |
| XSS | PARTIAL | Экранирование UI и CSP есть; DAST и покрытие всех DOM sink не выполнены |
| SSRF | PARTIAL | Исходящие адреса ограничены кодом провайдеров; динамические URL и DNS rebinding не тестировались отдельно |
| SQL injection | PARTIAL | Bound parameters и ограниченный SQL bridge; SAST/динамический анализ не выполнены |
| Mass assignment | PARTIAL | Ручной выбор полей в основных маршрутах; все endpoint не проверены |
| File upload | PARTIAL | Проверка размера/формата, PDF active content; malware scan не подключён |
| Payment security | PARTIAL | Поддельные/дублирующие уведомления тестируются локально; реальный sandbox/live webhook не проверен |
| AI security | PARTIAL | Лимиты и серверная авторизация инструментов; полный adversarial тест не проведён |
| Rate limits | PARTIAL | Локальные тесты, PostgreSQL atomic counter; staging load test не проведён |
| Secret rotation | NOT VERIFIED | Ключи из чата должны быть перевыпущены владельцем |
| Backups/restore | PARTIAL | Перед миграциями 6–7 сделан зашифрованный локальный снимок production БД; восстановление в отдельную временную PostgreSQL БД проверено. Регулярное резервирование и восстановление в боевой среде не проверены |
| SCA/SBOM | PARTIAL | Локально `pip-audit 2.10.1` не нашёл известных уязвимостей в `requirements-dev.txt`; CycloneDX JSON создан (12 компонентов). CI workflow добавлен, но удалённый run ещё не проверен |
| SAST | NOT VERIFIED | Ruff проверяет качество кода, но не заменяет security SAST |

Миграции 6–7 применены, production deployment `dpl_96wgPh43MjnMSjztYSNcCTniuTsx` опубликован. Одноразовый аккаунт прошёл регистрацию, чтение кабинета через ограниченную роль и удаление. Production security gate остаётся открытым: раскрытые ранее ключи ещё требуют ротации, а реальная платёжная/OAuth интеграция, нагрузка и независимая проверка безопасности не подтверждены.


## Снимок конфигурации Supabase — 19 октября 2026

Проведена read-only проверка активного проекта; схема и данные не изменялись:

- В приватной production-схеме `smetra` обнаружено 73 таблицы с включённым RLS; у 63 также включён `FORCE ROW LEVEL SECURITY`. Десять внутренних таблиц требуют отдельной проверки на необходимость `FORCE RLS`.
- У ролей `smetra_app` и `smetra_runtime` не обнаружены атрибуты суперпользователя или `BYPASSRLS`; `smetra_runtime` не имеет права входа и наследуется прикладной ролью.
- Роли Supabase API `anon` и `authenticated` не имеют `USAGE` на закрытую схему `smetra`; прямой `SELECT` по production-таблицам для них не предоставлен.
- Advisor сообщает о RLS без политик на части внутренних и QA-таблиц. Это не доказательство публичной утечки: проверяйте предупреждения вместе с грантами схемы/таблиц и фактическими путями доступа. Не добавляйте политики публичным ролям автоматически.
- Снимок конфигурации не заменяет аудит изоляции всех API-маршрутов. Остаются независимый аудит BOLA/tenant isolation, проверка десяти таблиц без FORCE RLS и внутренних привилегированных путей, ротация ранее раскрытых секретов, перевод `YANDEX_CLIENT_SECRET` в Secret, production payment/OAuth-проверки и повторные тесты после изменения ролей/грантов.


## Проверка Vercel — 20 октября 2026

Read-only проверка и безопасные изменения конфигурации:

- Firewall включён. Правило `Smetra API burst guard` активно и ограничивает `/api/` и `/health` до 300 запросов на IP за 60 секунд.
- Встроенные CRS-подписи SQLi, XSS и RCE остаются в режиме `log`; попытка включить блокировку отклонена, так как OWASP Core Ruleset недоступен на текущем тарифе Vercel. В этой конфигурации нельзя утверждать, что WAF блокирует такие атаки. За последние 7 дней панель active-attack не вернула аномалий, но это не доказывает отсутствия атак.
- `DATABASE_URL`, `RUNTIME_DATABASE_URL`, `OPENROUTER_API_KEY`, `YANDEX_CLIENT_SECRET` и переменные общего Redis-интеграционного подключения теперь назначены только Production. Новые Preview-деплои больше не получают рабочие подключения/ключи. Значения секретов не считывались.
- `DATABASE_URL`, `RUNTIME_DATABASE_URL`, `OPENROUTER_API_KEY`, `ASSISTANT_WORKER_SECRET` и Redis-переменные хранятся как Vercel Sensitive/Secret. У `YANDEX_CLIENT_SECRET` остаётся `readable-secret` (тип `encrypted` / видимость Config): безопасно переклассифицировать его через доступный API не удалось без повторной передачи значения. Владелец должен перевыпустить/повторно ввести секрет из консоли Yandex OAuth и сохранить его в Vercel как Secret.
- Переменные окружения применяются к новым деплоям. Preview-деплои, созданные до изменения, могут содержать старый снимок переменных и должны быть обновлены или выведены из эксплуатации. Защита Vercel SSO для preview включена; она снижает доступ извне, но не заменяет redeploy.


## Сканирование секретов в Git

- Добавлен отдельный workflow `.github/workflows/gitleaks.yml` с закреплённым SHA Gitleaks Action v3.0.0 и `fetch-depth: 0`, чтобы анализировать историю Git, а не только текущие файлы.
- Комментарии к PR и выгрузка SARIF/artifact отключены; job summary остаётся включённым. Первый полный удалённый проход ожидает завершения.
- Отсутствие результата в индексированном поиске GitHub не заменяет полное сканирование истории. Если Gitleaks обнаружит настоящий секрет, его нужно отозвать/перевыпустить у провайдера и затем оценить очистку истории.


## Preview/Production boundary — application-level regression guard

- `backend/postgres.py::schema_name()` теперь запрещает Preview-процессу использовать production schema `smetra`, даже если кто-то по ошибке добавит `DATABASE_URL` или `RUNTIME_DATABASE_URL` обратно в Preview. Ошибка происходит до открытия соединения с Postgres.
- Для Preview допускается явно указанная изолированная схема вида `smetra_qa_20260928`. Добавлены unit-тесты для запрета production-схемы в Preview, разрешения QA-схемы и нормальной production-конфигурации.
- Статус удалённого CI для текущего коммита будет указан только после завершения GitHub Actions.


## Управление review для защищённой ветки

- Добавлен `.github/CODEOWNERS` с владельцем проекта для исходников, миграций, mobile-кода и CI/CD.
- API GitHub вернул пустой список repository rulesets; классическую branch protection подключение прочитать не смогло (403). Поэтому обязательный review владельца, запрет прямых push в `main` и required checks пока **не подтверждены**. В настройках GitHub нужно включить protection/ruleset для `main`: required PR review, Require review from Code Owners, запрет force-push/deletion и обязательные CI, CodeQL, Secret scanning checks.

 
## 20 October 2026 — performance branch and newly found RLS issue

- Draft PR #12 adds bounded PostgreSQL connection pooling, query-hot-path indexes, RLS init-plan rewrites, short-lived isolated GET caching, compact UI and a motion-designed landing. The PostgreSQL migration has explicit 5-second lock and 30-second statement timeouts; the SQLite migration is idempotent.
- A live read-only query confirmed `smetra.file_text_chunks` currently has `f.workspace_id = f.workspace_id` in the parent-file EXISTS condition. The migration now corrects it to compare with `file_text_chunks.workspace_id`. Until that migration is reviewed/applied and the live policy is re-verified, this remains an **open production tenant-isolation finding**.
- Preview `/health` returned 500 because the endpoint opened the database even where Preview deliberately has no database credentials. Code now makes `/health` a lightweight liveness probe and `/ready` a database readiness check. The current preview confirmed `/health` returns HTTP 200. The current commit’s full CI/CodeQL is not yet green; check linked Actions before merge.
- No measured p95 / throughput benchmark has been run yet, so do not claim a numeric speedup. Production DDL and production deployments remain unchanged.
