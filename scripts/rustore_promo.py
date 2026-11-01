"""Builds the 10 RuStore promo images (1080x1920) from real app screenshots.

Input is the folder written by scripts/android_screens.cjs (raw/*.png, screens.json,
ui-critic.json). Nothing is drawn into the screenshot itself: it is scaled into a
device frame under a headline, so every promo shows the app exactly as captured.

    python scripts/rustore_promo.py data/android-screens

Writes promo/NN-*.png, manifest.json (sources, hashes, copy, checks) and
ui-critic.md (the screen review plus checks of the promo layouts).
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "apps/web/assets/fonts"
WIDTH, HEIGHT = 1080, 1920
MARGIN = 84
BG = (10, 10, 11)
TEXT = (237, 237, 239)
TEXT_2 = (167, 167, 176)
ACCENT = (110, 168, 255)
FRAME = (42, 42, 46)

# Benefit first, one idea per image. AR is not advertised until it is verified on
# a real ARCore device, so the tenth image shows the AI token packs instead.
COPY = {
    "01-dashboard": ("Сметы и деньги на одном экране", "Проекты, оплаты и задачи — всегда под рукой"),
    "02-quotes": ("Сметы, которые клиент согласует", "Ссылка для клиента, версии и статусы"),
    "03-assistant": ("ИИ-ассистент считает за вас", "Спросите голосом — получите объёмы и цены"),
    "04-construction": ("Объекты и замеры в телефоне", "Помещения, площади и объёмы работ"),
    "05-object": ("Размеры комнат — готовая смета", "Формулы сами считают площади и материалы"),
    "06-calculators": ("Калькуляторы материалов", "Плитка, ламинат, краска — сразу с запасом"),
    "07-projects": ("Заказы по этапам", "Согласованная смета становится проектом"),
    "08-clients": ("Клиенты и вся история работ", "Контакты, сметы и файлы в одной карточке"),
    "09-finance": ("Деньги под контролем", "Поступления, расходы и ожидаемые оплаты"),
    "10-tokens": ("Токены для ИИ без подписки", "Пакеты и своё количество — не сгорают"),
}


def font(weight, size):
    return ImageFont.truetype(str(FONTS / f"manrope-{weight}.ttf"), size)


def wrap(draw, text, face, width):
    lines, line = [], ""
    for word in text.split():
        probe = (line + " " + word).strip()
        if draw.textlength(probe, font=face) <= width or not line:
            line = probe
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def contrast(a, b):
    def lum(rgb):
        channels = [c / 255 for c in rgb]
        channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compose(raw, headline, subline):
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BG)
    glow = Image.new("RGB", (WIDTH, HEIGHT), BG)
    ImageDraw.Draw(glow).ellipse((-260, 980, WIDTH + 260, 2500), fill=(28, 44, 74))
    canvas = Image.blend(canvas, glow.filter(ImageFilter.GaussianBlur(160)), 0.9)
    draw = ImageDraw.Draw(canvas)
    checks = []

    title_face, sub_face = font(800, 74), font(500, 38)
    title = wrap(draw, headline, title_face, WIDTH - 2 * MARGIN)
    sub = wrap(draw, subline, sub_face, WIDTH - 2 * MARGIN)
    y = 132
    draw.rounded_rectangle((MARGIN, y, MARGIN + 64, y + 8), 4, fill=ACCENT)
    y += 44
    for line in title:
        draw.text((MARGIN, y), line, font=title_face, fill=TEXT)
        y += 90
    y += 14
    for line in sub:
        draw.text((MARGIN, y), line, font=sub_face, fill=TEXT_2)
        y += 52
    if len(title) > 2:
        checks.append("headline wraps to %d lines" % len(title))
    if len(sub) > 2:
        checks.append("subline wraps to %d lines" % len(sub))

    # The real screenshot, scaled into a device frame that runs off the bottom edge.
    shot = Image.open(raw).convert("RGB")
    inner = 780
    scaled = shot.resize((inner, round(shot.height * inner / shot.width)), Image.LANCZOS)
    top = max(y + 56, 560)
    left = (WIDTH - inner) // 2
    bezel = 14
    frame = (left - bezel, top - bezel, left + inner + bezel, HEIGHT + 120)
    shadow = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((frame[0] + 10, frame[1] + 24, frame[2] - 10, frame[3]), 72, fill=170)
    canvas.paste((0, 0, 0), (0, 0), shadow.filter(ImageFilter.GaussianBlur(40)))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(frame, 70, fill=(22, 22, 25), outline=FRAME, width=3)
    visible = scaled.crop((0, 0, inner, min(scaled.height, HEIGHT - top)))
    mask = Image.new("L", visible.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, visible.width, visible.height + 80), 56, fill=255)
    canvas.paste(visible, (left, top), mask)
    shown = visible.height / scaled.height
    if shown < 0.55:
        checks.append("only %d%% of the screen is visible" % round(shown * 100))
    return canvas, checks, {"title_lines": len(title), "sub_lines": len(sub), "screen_visible": round(shown, 2)}


def main():
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "data/android-screens").resolve()
    screens = json.loads((folder / "screens.json").read_text(encoding="utf-8"))
    review = json.loads((folder / "ui-critic.json").read_text(encoding="utf-8")) if (folder / "ui-critic.json").exists() else {"screens": []}
    metrics = {}
    for name in ("metrics-web.json", "metrics-native.json"):
        if (folder / name).exists():
            metrics[name[:-5]] = json.loads((folder / name).read_text(encoding="utf-8"))
    out = folder / "promo"
    out.mkdir(exist_ok=True)
    items, notes = [], []
    for screen in screens:
        raw = folder / screen["file"]
        headline, subline = COPY[screen["id"]]
        image, checks, layout = compose(raw, headline, subline)
        source = Image.open(raw)
        stat = ImageStat.Stat(source.convert("L"))
        if stat.stddev[0] < 12:
            checks.append("screenshot looks blank (stddev %.1f)" % stat.stddev[0])
        if source.width < 1080:
            checks.append("source is %dpx wide; RuStore needs device captures of at least 1080px" % source.width)
        target = out / (screen["id"] + ".png")
        image.save(target, optimize=True)
        screen_issues = next((entry["issues"] for entry in review["screens"] if entry["screen"] == screen["id"]), [])
        items.append({
            "id": screen["id"], "route": screen["route"], "headline": headline, "subline": subline,
            "source": screen["file"], "source_sha256": sha256(raw), "source_size": list(source.size),
            "promo": "promo/" + target.name, "promo_sha256": sha256(target), "size": [WIDTH, HEIGHT],
            "layout": layout, "promo_checks": checks, "screen_issues": screen_issues,
        })
        notes.append((screen, checks, screen_issues))
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "scripts/rustore_promo.py",
        "capture": metrics.get("metrics-web", {}).get("capture", "unknown"),
        "rule": "Screens are unedited captures of the debug APK against the isolated fixture; promos only scale and frame them.",
        "text_contrast": {"headline": round(contrast(TEXT, BG), 2), "subline": round(contrast(TEXT_2, BG), 2)},
        "metrics": metrics,
        "images": items,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Smetra UI Critic", "", f"Generated {manifest['generated_at']} · capture: {manifest['capture']}", "",
             f"Headline contrast {manifest['text_contrast']['headline']}:1, subline {manifest['text_contrast']['subline']}:1 (AA needs 4.5).", ""]
    for screen, checks, issues in notes:
        lines.append(f"## {screen['id']} — {screen['title']}")
        if not checks and not issues:
            lines.append("- ok")
        for issue in issues:
            lines.append(f"- screen: {issue['rule']}" + (f" ({issue.get('count')})" if issue.get("count") else "") + (f" — {issue['detail']}" if issue.get("detail") else ""))
        for check in checks:
            lines.append(f"- promo: {check}")
        lines.append("")
    if review.get("console_errors"):
        lines += ["## Console errors", *[f"- {error}" for error in review["console_errors"]], ""]
    (folder / "ui-critic.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(items)} promo images in {out}")


if __name__ == "__main__":
    main()
