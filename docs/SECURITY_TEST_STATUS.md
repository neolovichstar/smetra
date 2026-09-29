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
