# Сборка и публикация Android-приложения «Сметра»

## Текущая версия исходников

- Package: `ru.smetra.mobile`
- Версия исходников: **1.7.27**, `versionCode 39` (источник истины — `apps/mobile/app/build.gradle`).
- Production API: `https://smetra.vercel.app`.
- Релизный APK не считается собранным или опубликованным, пока workflow не завершился успешно и файл не прошёл проверку на устройстве.

## Локальная подписанная сборка

На компьютере разработчика, где сохранён релизный ключ:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_android_release.ps1
```

Скрипт читает версию из Gradle, выполняет `lintRelease` и `assembleRelease`, проверяет package/version, подпись APK и совпадение SHA-256 сертификата с `RUSTORE_CERT_SHA256`. Результат именуется `dist/smetra-mobile-<version>-release.apk`; рядом создаётся `.sha256`.

Ключ по прежней конфигурации может находиться в `%USERPROFILE%\.smetra\android\release.p12`, метаданные — в `signing.json`. Проверьте наличие на своей машине. Приватный ключ, пароль, DPAPI-файл и base64 keystore нельзя помещать в Git, issue/PR или чат. Сохраните резервную копию ключа и пароль отдельно в защищённом хранилище. Не генерируйте новый ключ автоматически, если старый недоступен: сначала проверьте сертификат, принятый магазином.

## CI и GitHub Releases

Обычный CI собирает версионированный **debug APK** и публикует его с SHA-256 как артефакт GitHub Actions. Он предназначен для QA и **не является подписанным релизом для RuStore/обновления установленного приложения**.

Ручной workflow `.github/workflows/android-release.yml` выполняется только с `main`, использует окружение `android-release`, сверяет версию, package name и отпечаток сертификата, а затем создаёт **draft/prerelease GitHub Release**. Автоматической публикации в RuStore нет.

Перед запуском настройте GitHub **Settings → Environments → android-release**, required reviewers и разрешённую ветку `main`. Добавьте в secrets окружения `ANDROID_RELEASE_KEYSTORE_BASE64`, `ANDROID_RELEASE_STORE_PASSWORD`, `ANDROID_RELEASE_KEY_ALIAS`, `ANDROID_RELEASE_KEY_PASSWORD`, `RUSTORE_CERT_SHA256`. В base64 должен быть тот же keystore, что соответствует сертификату, принятому магазином. При необходимости `MYTRACKER_SDK_KEY` задаётся как secret, `RUSTORE_PUSH_PROJECT_ID` — как variable. Токен сервиса RuStore Push не помещайте в APK.

После сборки проверьте draft, SHA-256, подпись и установку на тестовом устройстве. Перед загрузкой в RuStore вручную подтвердите правила обновления и сертификат. Публикация в магазине — отдельное действие владельца.

## Чек-лист перед публикацией

- Проверить вход, сессию, восстановление, сметы, PDF, вложения и уведомления на тестовом устройстве.
- Убедиться, что package name — `ru.smetra.mobile`, `versionCode` выше последнего опубликованного, сертификат совпадает.
- Сохранить APK, SHA-256, ID запуска Actions и commit SHA.
- Проверить описание, скриншоты, контакты, политику данных и другие материалы магазина.

SHA-256 подтверждает идентичность файла при передаче, но не доказывает безопасность APK. Draft необходимо протестировать до публикации.
