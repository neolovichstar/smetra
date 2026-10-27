# Google ID и Google Drive в «сметре.»

## Независимые права

- Google-вход: OAuth 2.0 c PKCE и scopes `openid email profile`; доступ к Google Drive для входа НЕ запрашивается.
- Google Drive: независимый OAuth-поток с `https://www.googleapis.com/auth/drive.readonly`, чтение папок только по запросу пользователя.
- Аккаунты связываются по `(provider, subject)`. Совпадение почты само по себе НЕ объединяет аккаунты.
- Отключение диска очищает токены и останавливает синхронизацию внутри «сметры.», но не удаляет файлы у провайдера.

## Google Cloud Console

Создать OAuth Web application и указать два точных URI (в том же OAuth-клиенте или в отдельных):

1. Для Google-входа: `https://smetra.online/api/auth/oauth/google/callback`.
2. Для Google Drive: `https://smetra.online/api/premium/cloud/oauth/callback`.
3. Authorized JavaScript origin: `https://smetra.online`.
4. Включить Google Drive API для функции Диска; в режиме Testing добавить тестовых пользователей.
5. Для публичного использования restricted scope `drive.readonly` может понадобиться проверка приложения Google, включая независимую оценку безопасности.

## Переменные Vercel (Production, только сервер)

| Название | Назначение |
| --- | --- |
| `GOOGLE_AUTH_CLIENT_ID` | OAuth ID для входа |
| `GOOGLE_AUTH_CLIENT_SECRET` | Закрытый секрет для входа |
| `GOOGLE_DRIVE_CLIENT_ID` | OAuth ID для Google Drive |
| `GOOGLE_DRIVE_CLIENT_SECRET` | Закрытый секрет для Google Drive |
| `GOOGLE_DRIVE_REDIRECT_URI` | `https://smetra.online/api/premium/cloud/oauth/callback` |

При отсутствии пары `GOOGLE_AUTH_*` вход использует пару `GOOGLE_DRIVE_CLIENT_*`.
В таком случае ОБА redirect URI обязательно должны быть зарегистрированы в одном OAuth-клиенте.
Никогда не переносите client secret в JavaScript, APK, GitHub, документацию или переписку.

`PUBLIC_ORIGIN=https://smetra.online` и `CLOUD_TOKEN_ENCRYPTION_KEY` уже настроены в продакшене, не менять и не раскрывать их значения.

## Проверка и ограничения

- После изменения переменных нужна новая сборка Vercel.
- `/api/auth/providers` показывает `google` с `enabled=true` только при наличии и ID, и секрета.
- Google-вход использует только `openid email profile`, Google Drive отдельно требует `drive.readonly`.
- Просмотр папок через `/api/premium/cloud/browse-folders` загружает только подкаталоги — до 100 за страницу. Сам по себе просмотр не импортирует и не скачивает файлы.
- Перед синхронизацией пользователь выбирает нужную папку. Изменения смет требуют самостоятельной проверки и подтверждения.
