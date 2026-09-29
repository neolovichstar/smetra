# Подготовка Android-приложения к RuStore

Пакет приложения: `ru.smetra.mobile`. Веб и Android работают через `https://smetra.vercel.app`. Карточка приложения: https://www.rustore.ru/catalog/app/ru.smetra.mobile. Следующее обновление в исходниках — версия `1.3.0` (`versionCode 5`). Тестовый APK подходит для ручной проверки, но не для загрузки в магазин.

1. Подключите сервисы входа и проверьте регистрацию, общую учётную запись, сметы, клиентскую ссылку и удаление профиля на реальном Android-устройстве.
2. Используйте тот же signing keystore, которым подписана уже одобренная версия. Не кладите его и пароль в Git.
3. Установите `SIGNING_STORE_FILE`, `SIGNING_STORE_PASSWORD`, `SIGNING_KEY_ALIAS`, `SIGNING_KEY_PASSWORD` в локальной среде сборки. Для APK выполните `powershell -ExecutionPolicy Bypass -File scripts/build_android_release.ps1`.
4. Проверьте подписанный APK/AAB и установите его поверх магазинной версии на тестовом устройстве. После проверки загрузите обновление в кабинет RuStore.

`RUSTORE_URL` на рабочем сайте уже указывает на карточку приложения. Для дальнейших обновлений менять его не нужно.

## Проверяемая сборка APK для обновления

Перед сборкой сверьте с опубликованной версией в RuStore, что `versionCode 5` больше текущего. Если нет — увеличьте `versionCode` и `versionName` в `apps/mobile/app/build.gradle` и обновите проверку версии в `scripts/build_android_release.ps1`.

На компьютере с Android SDK и исходным ключом подписи задайте четыре переменные `SIGNING_*` из пункта 3. `SIGNING_STORE_FILE` должен указывать на существующий keystore. Также задайте `RUSTORE_CERT_SHA256` — SHA-256 отпечаток сертификата установленной/опубликованной версии (двоеточия допустимы). Затем выполните `powershell -ExecutionPolicy Bypass -File scripts/build_android_release.ps1`. Скрипт запускает `lintRelease`, собирает минифицированный APK, проверяет пакет, версию и подпись через `apksigner`, сверяет сертификат с `RUSTORE_CERT_SHA256` и сохраняет `dist/smetra-mobile-1.3.0-release.apk` с контрольной суммой SHA-256. Без отпечатка или при несовпадении ключа выпуск останавливается.

Без старого keystore можно проверить компиляцию релиза и R8 командой `apps\mobile\gradlew.bat -p apps/mobile assembleRelease lintRelease -PapiBaseUrl=https://smetra.vercel.app -PverifyUnsignedRelease=true`. Результат `app-release-unsigned.apk` предназначен только для проверки сборки; RuStore его не примет. CI выполняет ту же проверку. Не создавайте новый ключ для обычного обновления: Android не установит APK с другой подписью поверх текущего приложения.

Официальные требования и подача: https://www.rustore.ru/help/developers/publishing-and-verifying-apps/app-publication. Сверьте актуальные требования в кабинете перед отправкой.
