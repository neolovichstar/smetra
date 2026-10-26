# Рекламный ролик Сметры

3D-iPhone с реальным интерфейсом Сметры на чёрном фоне, 20 секунд, 1920×1080, 30 кадров/с.
Сцена — `promo.js` (three.js из `apps/web/vendor`), кадры рендерит Chromium через Playwright,
склейка — ffmpeg.

## Как собрать на своём компьютере

Нужны Node.js, Playwright (`npm i -D playwright && npx playwright install chromium`) и ffmpeg.

```bash
# из корня репозитория
python -m http.server 8000          # отдельный терминал

node tools/promo/render.cjs frames 60 250 440        # пробные кадры → tools/promo/test/
node tools/promo/render.cjs all                      # все 600 кадров → tools/promo/frames/
#   быстрее в 4 потока: node tools/promo/render.cjs all 0 150   (и 150 300, 300 450, 450 600)

ffmpeg -y -framerate 30 -i tools/promo/frames/%04d.jpg \
  -c:v libx264 -preset slow -crf 16 -pix_fmt yuv420p -movflags +faststart tools/promo/smetra-promo.mp4
```

На машине без видеокарты добавьте `SOFTWARE_GL=1` перед `node` — работает, но медленно.

## Что где менять

- Сцены, тайминг, движение камеры, подписи — массив `SHOTS` в `promo.js`.
- Финальный логотип — функция `logo()`.
- Экраны — PNG в `scr/` (390×800 при плотности 3). Переснять с данными демо-фикстуры:
  запустить `scripts/android_ui_fixture.py` (SMETRA_PROMO_QA=1, порт 8097) и `node tools/promo/cap.cjs`
  с `TOKEN_FILE=<файл сессии фикстуры>`. Скрипт делает фон чисто чёрным, как на OLED.
