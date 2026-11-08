# сметра. — UI motion (30.5 s)

Изолированная демосцена с синтетическими данными. Аккаунт и платные API не нужны.
Стили, токены, иконки и шрифт Onest взяты из продакшен-коммита `b0e42a0`
(ветка `fix/assistant-composer-hint-20261031`, текущий production-деплой на Vercel).

## Файлы
- `index.html`: композиция (inline SVG, стили продукта).
- `timeline.js`: детерминированный таймлайн: `window.seek(t)`, аналитические пружины, камера, курсор, события звука.
- `render.mjs`: Playwright: `stills` / `frames` / `events`.
- `render_frames.sh`: рендер подкадров 240/с с дорендером после сбоя браузера.
- `audio.py`: собственная подложка 120 BPM, SFX по событиям, ducking под голос, SRT.
- `encode.sh`: FFmpeg: tmix из 4 непересекающихся подкадров → 60 fps, H.264 yuv420p, AAC, faststart.
- `check_seek.mjs`: проверка, что кадр не зависит от порядка seek.
- `assets/voice.mp3`: финальная дорожка речи (ElevenLabs, голос Pavel — Warm Conversational Narrator).
- `assets/words.raw.json`: тайминги слов (faster-whisper small, word timestamps).

## Повторный запуск
```bash
node render.mjs events
python -I audio.py ffmpeg
./render_frames.sh h && ./encode.sh h
./render_frames.sh v && ./encode.sh v
```
Если поменялся только звук: `python -I audio.py ffmpeg && ./remux_audio.sh` (видео копируется без перекодирования).
Chromium: `chromium-1234` из `%LOCALAPPDATA%/ms-playwright` (переопределяется переменной `CHROME`).
Превью в браузере: `index.html?fmt=h` (луп) или `index.html?fmt=v&t=14.5` (один кадр).

## Музыка и лицензия
Сторонней музыки нет. Подложка (пэд Fmaj7–Am7–Cmaj7–G6, мягкий кик, хэты, арпеджио, 120 BPM)
и все SFX синтезируются кодом в `audio.py`. SFX сделаны в мягком ASMR-стиле: тактильные «thock»-клавиши, бархатные тапы, тихий воздух на переходах, пузырёк, деревянные тики, шелест бумаги, калимба, стереопанорама и короткая «комната». Это собственная работа, ограничений на публикацию нет.
Голос сгенерирован в ElevenLabs пользователем. Условия использования определяет тариф его аккаунта ElevenLabs.
Шрифт Onest распространяется по лицензии SIL OFL 1.1 (`assets/Onest-OFL.txt`).

## Данные
Комната 18 м², только работы. Расценки демонстрационные (это не рыночные цены):
- покраска стен 42 м² × 350 ₽ = 14 700 ₽;
- ламинат 18 м² × 550 → 650 ₽ = 9 900 → 11 700 ₽;
- плинтус 17 м × 250 ₽ = 4 250 ₽.

Итого: 28 850 → 30 650 ₽.
