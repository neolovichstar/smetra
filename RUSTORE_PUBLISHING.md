# Подготовка Android-приложения к RuStore

Пакет приложения: `ru.smetra.mobile`. Веб и Android работают через `https://smetra.vercel.app`. Карточка приложения: https://www.rustore.ru/catalog/app/ru.smetra.mobile. Следующее обновление в исходниках — версия `1.3.0` (`versionCode 5`). Тестовый APK подходит для ручной проверки, но не для загрузки в магазин.

1. Подключите сервисы входа и проверьте регистрацию, общую учётную запись, сметы, клиентскую ссылку и удаление профиля на реальном Android-устройстве.
2. Используйте тот же signing keystore, которым подписана уже одобренная версия. Не кладите его и пароль в Git.
3. Установите `SIGNING_STORE_FILE`, `SIGNING_STORE_PASSWORD`, `SIGNING_KEY_ALIAS`, `SIGNING_KEY_PASSWORD` в локальной среде сборки. Выполните `apps\mobile\gradlew.bat -p apps/mobile assembleRelease bundleRelease -PapiBaseUrl=https://smetra.vercel.app`.
4. Проверьте подписанный APK/AAB и установите его поверх магазинной версии на тестовом устройстве. После проверки загрузите обновление в кабинет RuStore.

`RUSTORE_URL` на рабочем сайте уже указывает на карточку приложения. Для дальнейших обновлений менять его не нужно.

Официальные требования и подача: https://www.rustore.ru/help/developers/publishing-and-verifying-apps/app-publication. Сверьте актуальные требования в кабинете перед отправкой.
