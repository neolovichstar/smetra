# Подключение входа, почты и магазина

Сайт и Android уже используют общий сервер `https://smetra.vercel.app`. Вход по почте доступен; Яндекс ID, VK ID и Mail ID автоматически появятся активными после настройки указанных ниже переменных. Секреты добавляйте только в **Vercel → Project smetra → Settings → Environment Variables**, для Production, затем публикуйте новую сборку. Не вставляйте их в `.env.example`, GitHub или Android APK.

## Яндекс ID

1. Создайте OAuth-приложение в [кабинете Яндекса](https://yandex.ru/dev/id/doc/ru/register-auth), выберите веб-сервис и разрешения на профиль и адрес почты (`login:info`, `login:email`).
2. В Redirect URI укажите **точно** `https://smetra.vercel.app/api/auth/oauth/yandex/callback`.
3. Перенесите ID приложения в `YANDEX_CLIENT_ID`, секрет в `YANDEX_CLIENT_SECRET` в Vercel. Не передавайте секрет Android-приложению.

## VK ID и Mail ID

1. Создайте приложение VK ID с веб-платформой. Нужен его `APP_ID`; запишите его в `VK_CLIENT_ID` в Vercel.
2. Разрешите два адреса возврата: `https://smetra.vercel.app/api/auth/oauth/vk/callback` и `https://smetra.vercel.app/api/auth/oauth/mail/callback`.
3. Включите провайдер Mail.ru в настройках VK ID, если он не доступен по умолчанию. Обе кнопки используют одну VK ID-интеграцию, но отдельные обратные адреса.

Использован официальный [VK ID Web SDK](https://github.com/VKCOM/vkid-web-sdk) как справочник по OAuth 2.1 и PKCE. [Документация Mail.ru](https://api.mail.ru/docs/guides/oauth/) рекомендует VK ID для входа через VK и Mail.ru. Перед запуском проверьте реальные вход и отмену авторизации каждым сервисом; до выдачи APP_ID такие внешние сценарии нельзя проверить полностью.

Android открывает страницу провайдера в системном браузере, получает одноразовый билет по `smetra://auth` и подтверждает его PKCE. Новый пользователь получает один и тот же профиль на сайте и телефоне. Владельцу существующего аккаунта по почте нужно сначала войти на сайте и нажать **Настройки → Способы входа → Привязать**. Совпадение почтовых адресов само по себе не объединяет профили.

## Почта и восстановление доступа

Для писем подтверждения и восстановления добавьте `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`. Проверьте доставку и затем удалите `ALLOW_UNVERIFIED_SIGNUP` из Vercel. Пока SMTP отсутствует, этот временный флаг разрешает регистрацию без подтверждения адреса; оплата неподтверждённому аккаунту недоступна.

## RuStore

После подготовки подписанного релиза `ru.smetra.mobile` опубликуйте приложение в [кабинете RuStore](https://www.rustore.ru/help/developers/publishing-and-verifying-apps/app-publication). Вставьте конечную ссылку карточки приложения в переменную `RUSTORE_URL` в Vercel и разверните сайт заново. Лендинг тогда сам заменит «Скоро в RuStore» на активную кнопку установки. До появления карточки оставьте переменную пустой.

## Платежи и ассистент

YooKassa требует `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` и рабочий webhook `https://smetra.vercel.app/api/webhooks/yookassa`; включайте только после тестового платежа. Ассистент работает с серверным `OPENROUTER_API_KEY` и `OPENROUTER_MODEL=openrouter/free`. Запросы к модели расходуют бесплатную квоту OpenRouter; предложения об изменении данных требуют подтверждения в интерфейсе.
