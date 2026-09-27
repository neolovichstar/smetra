# RuStore release checklist

No APK/AAB was built in this workspace. The project source is not yet approved for public listing. RuStore publication docs: https://www.rustore.ru/help/developers/publishing-and-verifying-apps/app-publication and https://www.rustore.ru/help/developers/publishing-and-verifying-apps/requirement-apps.

Listing draft: name **Сметра**; category **Бизнес** if available in the actual console; rating choose after answering current questionnaire; short description: «Создавайте предложения, отправляйте ссылку и получайте согласование»; long description: «Сметра помогает специалистам и небольшим сервисным командам составлять предложения на работы. Укажите клиента, стоимость и описание, отправьте ссылку и отслеживайте ответ в личном кабинете. Приложение синхронизируется с веб-сервисом. Первые 10 предложений доступны бесплатно.» Version `1.0.0`, versionCode `1`. No claim about payments inside the Android application.

1. Complete release blockers in README, PAYMENTS and SECURITY; register appropriate developer account and confirm terms with RuStore. Verify the name's availability.
2. Deploy HTTPS backend and functional privacy/support URLs. Replace placeholders in policies and sitemap.
3. Install Android Studio (SDK 35, Build Tools 35) and Gradle 8.9, JDK 17. From project root run `gradle -p apps/mobile assembleDebug -PapiBaseUrl=https://YOUR_DOMAIN`.
4. Generate a private signing keystore and store its password securely. Export `SIGNING_STORE_FILE`, `SIGNING_STORE_PASSWORD`, `SIGNING_KEY_ALIAS`, `SIGNING_KEY_PASSWORD`. Run `gradle -p apps/mobile assembleRelease bundleRelease -PapiBaseUrl=https://YOUR_DOMAIN`. APK/AAB output is under `apps/mobile/app/build/outputs/`. Never commit the key.
5. Verify login, quote creation, sharing, approval in external browser, account deletion, offline/timeout and back navigation on physical devices. Check phone and tablet layouts. No TV support is declared.
6. Prepare icon: `docs/icon-512.png` is 512×512. Capture at least three real phone screenshots (and at least three per other device type if listed). Keep screenshots true to the built app. Enter real contact details and data safety answers.
7. Upload signed APK or AAB. RuStore describes support for both formats, signature, package uniqueness and a higher versionCode on updates. Submit for review, address reviewer feedback, and only then publish.

RuStore currently describes short description limit 80 characters, long description 4000, 512×512 icon up to 3 MB, and mandatory mobile screenshots. Recheck the live console before submission. Source: https://www.rustore.ru/help/developers/publishing-and-verifying-apps/app-publication.
