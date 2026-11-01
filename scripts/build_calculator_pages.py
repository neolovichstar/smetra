"""Generate the public calculator pages (apps/web/kalkulyator/*.html).

Field definitions come from apps/web/calculators.js — the same code the cabinet uses —
so the public pages and the app never disagree. Texts for search engines live here.
Run after editing either: python scripts/build_calculator_pages.py
"""
import html
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps/web"
OUT = WEB / "kalkulyator"
SITE = "https://smetra.online"
VERSION = "20261026-r22"

PAGES = [
    {
        "slug": "plitka", "kind": "tile", "name": "плитки",
        "title": "Калькулятор плитки онлайн — сколько плитки нужно на пол и стены | Сметра",
        "h1": "Калькулятор плитки",
        "lead": "Посчитайте площадь облицовки с запасом на подрезку и сколько целых упаковок купить. Подходит для пола, стен, ванной и фартука.",
        "steps": ["Измерьте длину и ширину поверхности в метрах.",
                  "Вычтите участки, которые не облицовываются: дверной проём, место под ванну или шкаф.",
                  "Укажите запас и площадь плитки в одной упаковке — она есть на этикетке.",
                  "Калькулятор покажет площадь с запасом и количество целых упаковок."],
        "faq": [("Какой запас плитки брать?",
                 "При прямой укладке обычно берут 5–10%, при диагональной и сложной раскладке — больше, так как растёт подрезка. Для крупного формата и плитки с рисунком запас тоже увеличивают."),
                ("Как посчитать плитку для ванной комнаты?",
                 "Посчитайте каждую стену отдельно: длина × высота облицовки, затем сложите площади и вычтите дверь и участки за ванной, если там не будет плитки. Пол считается отдельно."),
                ("Почему количество упаковок округляется вверх?",
                 "Магазины продают плитку целыми упаковками, а докупить позже ту же партию по тону бывает сложно, поэтому калькулятор всегда округляет вверх."),
                ("Учитывает ли расчёт клей и затирку?",
                 "Нет, здесь считается только плитка. Расход клея и затирки зависит от смеси и толщины шва — его указывают на упаковке.")],
    },
    {
        "slug": "laminat", "kind": "laminate", "name": "ламината",
        "title": "Калькулятор ламината онлайн — сколько упаковок нужно на комнату | Сметра",
        "h1": "Калькулятор ламината",
        "lead": "Площадь пола с запасом на подрезку и число целых упаковок ламината для комнаты.",
        "steps": ["Измерьте длину и ширину комнаты в метрах.",
                  "Укажите запас: он зависит от способа укладки.",
                  "Введите площадь ламината в одной упаковке с этикетки.",
                  "Получите площадь с запасом и количество целых упаковок."],
        "faq": [("Какой запас нужен для ламината?",
                 "При укладке вдоль комнаты обычно хватает 5–7%, по диагонали — около 10–15%. Для комнат сложной формы запас увеличивают."),
                ("Нужно ли учитывать порожки и ниши?",
                 "Ниши и эркеры посчитайте как отдельные прямоугольники и сложите площади. Порожки и плинтус считаются отдельно."),
                ("Сколько ламината в одной упаковке?",
                 "Площадь упаковки указана на коробке и зависит от размера доски — используйте значение именно вашего ламината.")],
    },
    {
        "slug": "kraska", "kind": "paint", "name": "краски",
        "title": "Калькулятор краски для стен онлайн — расход на м² и количество банок | Сметра",
        "h1": "Калькулятор краски для стен",
        "lead": "Сколько литров краски нужно на стены с учётом проёмов, количества слоёв и укрывистости, и сколько банок купить.",
        "steps": ["Укажите длину и высоту стены — для комнаты сложите периметр всех стен.",
                  "Вычтите площадь окон и дверей.",
                  "Задайте число слоёв и укрывистость одного слоя с этикетки краски.",
                  "Получите объём краски с запасом и количество целых банок."],
        "faq": [("Сколько слоёв краски нужно?",
                 "Обычно стены красят в два слоя. Первый слой на новой или впитывающей поверхности расходуется сильнее — поэтому основание грунтуют заранее."),
                ("Где взять расход краски на квадратный метр?",
                 "Укрывистость (м² на литр на один слой) указывает производитель на банке. Она зависит от основания и способа нанесения, поэтому значение с этикетки важнее средних цифр."),
                ("Как посчитать краску для всей комнаты?",
                 "Сложите длины всех стен — это периметр, — умножьте на высоту и вычтите окна и двери. В калькуляторе введите периметр как длину стены.")],
    },
    {
        "slug": "shtukaturka", "kind": "plaster", "name": "штукатурки",
        "title": "Калькулятор штукатурки онлайн — расход смеси и количество мешков | Сметра",
        "h1": "Калькулятор штукатурки",
        "lead": "Расход сухой смеси по средней толщине слоя и норме с упаковки, количество мешков с запасом.",
        "steps": ["Укажите размеры стены и вычтите проёмы.",
                  "Задайте среднюю толщину слоя: на неровных стенах она больше.",
                  "Введите норму расхода на 10 мм с мешка и вес одного мешка.",
                  "Получите вес смеси с запасом и количество мешков."],
        "faq": [("Как узнать среднюю толщину штукатурки?",
                 "Её определяют по маякам или правилу: измерьте отклонения стены в нескольких точках и возьмите среднее. Реальный расход на кривых стенах заметно выше расчётного."),
                ("Почему расход у разных смесей отличается?",
                 "Гипсовые и цементные смеси имеют разную плотность, поэтому норма на 10 мм у них разная. Используйте значение с мешка вашей смеси."),
                ("Сколько брать запаса?",
                 "Обычно 5–10%: часть смеси теряется при замесе и нанесении, а стены редко бывают ровнее, чем кажется при замере.")],
    },
    {
        "slug": "oboi", "kind": "wallpaper", "name": "обоев",
        "title": "Калькулятор обоев онлайн — сколько рулонов нужно на комнату | Сметра",
        "h1": "Калькулятор обоев",
        "lead": "Сколько рулонов обоев купить на комнату: по периметру, высоте стен, ширине и длине рулона и раппорту рисунка.",
        "steps": ["Измерьте периметр комнаты — сумму длин всех стен.",
                  "Укажите высоту оклейки и общую ширину окон и дверей.",
                  "Введите ширину и длину рулона, а если у обоев есть рисунок — раппорт с этикетки.",
                  "Калькулятор посчитает полосы и целые рулоны."],
        "faq": [("Как посчитать обои на комнату?",
                 "Периметр за вычетом ширины окон и дверей делится на ширину рулона — это число полос. Из одного рулона выходит столько полос, сколько раз высота стены (плюс раппорт) помещается в длину рулона. Рулоны = полосы ÷ полос в рулоне, с округлением вверх."),
                ("Что такое раппорт и зачем его учитывать?",
                 "Раппорт — шаг повторения рисунка. Чтобы рисунок совпал на соседних полосах, каждую полосу приходится отрезать длиннее на величину раппорта, поэтому рулонов нужно больше."),
                ("Нужен ли запас обоев?",
                 "Калькулятор уже считает только целые полосы и не использует обрезки. Если стены сложной формы или есть ниши, возьмите ещё один рулон из той же партии.")],
    },
    {
        "slug": "styazhka", "kind": "screed", "name": "стяжки",
        "title": "Калькулятор стяжки пола онлайн — расход смеси и мешков | Сметра",
        "h1": "Калькулятор стяжки пола",
        "lead": "Сколько сухой смеси нужно на стяжку пола по площади, средней толщине и норме расхода с мешка.",
        "steps": ["Измерьте длину и ширину помещения.",
                  "Определите среднюю толщину стяжки — по маякам или нивелиру.",
                  "Введите норму расхода на 10 мм и вес мешка с упаковки смеси.",
                  "Получите вес смеси с запасом и количество мешков."],
        "faq": [("Как определить толщину стяжки?",
                 "Выставьте маяки по уровню и измерьте расстояние до основания в нескольких точках. Для расчёта нужна средняя толщина: на неровном полу она заметно больше минимальной."),
                ("Где взять расход смеси?",
                 "Производитель указывает расход в кг на 1 м² при толщине 10 мм. У разных смесей он отличается, поэтому значение с мешка точнее средних цифр."),
                ("Подойдёт ли расчёт для бетонной стяжки из миксера?",
                 "Для товарного бетона нужен объём в кубометрах — воспользуйтесь калькулятором бетона.")],
    },
    {
        "slug": "beton", "kind": "concrete", "name": "бетона",
        "title": "Калькулятор бетона онлайн — объём заливки в м³ | Сметра",
        "h1": "Калькулятор бетона",
        "lead": "Объём бетона для плиты, стяжки или площадки по длине, ширине и толщине — с запасом и без.",
        "steps": ["Измерьте длину и ширину участка в метрах.",
                  "Укажите толщину заливки в сантиметрах.",
                  "Задайте запас на неровности основания и потери.",
                  "Получите объём в кубометрах с запасом и без."],
        "faq": [("Как посчитать кубы бетона?",
                 "Объём = длина × ширина × толщина. Толщину переведите в метры: 10 см = 0,1 м. Калькулятор делает это сам."),
                ("Какой запас бетона заказывать?",
                 "Обычно несколько процентов на неровность основания, прогиб опалубки и потери при подаче. Для сложной геометрии считайте участки по отдельности."),
                ("Считает ли калькулятор состав смеси?",
                 "Нет, только геометрический объём. Марку бетона и состав подбирают под задачу и нагрузку.")],
    },
]


def specs():
    """Ask calculators.js for its field definitions (single source of truth)."""
    script = (
        "const fs=require('fs');const window={};global.window=window;"
        "eval(fs.readFileSync(process.argv[1],'utf8'));"
        "const out={};for(const k of window.SmetraCalculators.kinds)out[k]=window.SmetraCalculators.spec(k);"
        "process.stdout.write(JSON.stringify(out));"
    )
    raw = subprocess.run(["node", "-e", script, str(WEB / "calculators.js")], check=True, capture_output=True, text=True).stdout
    return json.loads(raw)


def e(text):
    return html.escape(str(text), quote=True)


def head(title, description, url, ld):
    return f"""<!doctype html>
<html lang="ru" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0a0a0b">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{url}">
<link rel="icon" href="/favicon.ico">
<link rel="apple-touch-icon" href="/assets/pwa/apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Сметра">
<meta property="og:locale" content="ru_RU">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:image" content="{SITE}/assets/og/smetra-og.jpg">
<meta name="twitter:card" content="summary_large_image">
<link rel="preload" href="/assets/fonts/onest-variable.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/ui/tokens.css?v={VERSION}">
<link rel="stylesheet" href="/ui/base.css?v={VERSION}">
<link rel="stylesheet" href="/ui/components.css?v={VERSION}">
<link rel="stylesheet" href="/ui/site.css?v={VERSION}">
<link rel="stylesheet" href="/ui/calc-page.css?v={VERSION}">
<script src="/error-report.js?v={VERSION}" defer></script>
<script src="/attribution.js?v={VERSION}" defer></script>
<script src="/calculators.js?v={VERSION}" defer></script>
<script src="/calc-page.js?v={VERSION}" defer></script>
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False, separators=(',', ':')).replace('</', '<' + chr(92) + '/')}</script>
</head>
"""


def nav():
    return """<body class="site-page calc-site dark">
<a class="skip-link" href="#main">К содержимому</a>
<header class="site-nav" id="site-nav">
  <div class="site-nav-inner">
    <a href="/" class="brand" aria-label="Сметра — на главную">сметра<span class="brand-mark">.</span></a>
    <nav class="site-links" aria-label="Разделы">
      <a href="/kalkulyator">Калькуляторы</a>
      <a href="/#features">Возможности</a>
      <a href="/#pricing">Тарифы</a>
    </nav>
    <div class="site-nav-actions">
      <a class="btn small ghost" href="/app">Войти</a>
      <a class="btn small primary" href="/app?register=1">Начать бесплатно</a>
    </div>
  </div>
</header>
"""


def footer(pages):
    links = "".join(f'<a href="/kalkulyator/{p["slug"]}">Калькулятор {p["name"]}</a>' for p in pages)
    return f"""<footer class="calc-footer">
  <nav aria-label="Все калькуляторы">{links}</nav>
  <p><a href="/">Сметра</a> — сметы, согласование с клиентом и оплата в одном месте. <a href="/privacy">Конфиденциальность</a> · <a href="/terms">Условия</a> · <a href="/contacts">Контакты</a></p>
</footer>
</body>
</html>
"""


def field_html(field):
    key, label, unit, value, low, high = field
    return (f'<label class="calc-field"><span>{e(label)}<small>{e(unit)}</small></span>'
            f'<input name="{e(key)}" inputmode="decimal" autocomplete="off" spellcheck="false" value="{e(value)}" '
            f'aria-label="{e(label)}, {e(unit)}" data-min="{low}" data-max="{high}"></label>')


def page(item, spec, pages):
    url = f"{SITE}/kalkulyator/{item['slug']}"
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": url, "url": url, "name": item["title"], "description": item["lead"], "inLanguage": "ru",
         "isPartOf": {"@type": "WebSite", "url": SITE + "/", "name": "Сметра"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Сметра", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Калькуляторы", "item": SITE + "/kalkulyator"},
            {"@type": "ListItem", "position": 3, "name": item["h1"], "item": url}]},
        {"@type": "HowTo", "name": "Как посчитать количество " + item["name"],
         "step": [{"@type": "HowToStep", "position": i + 1, "text": step} for i, step in enumerate(item["steps"])]},
        {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                                             for q, a in item["faq"]]},
    ]}
    others = "".join(f'<a class="calc-chip" href="/kalkulyator/{p["slug"]}">{e(p["h1"].replace("Калькулятор ", "").capitalize())}</a>'
                     for p in pages if p is not item)
    return head(item["title"], item["lead"], url, ld) + nav() + f"""<main id="main" class="calc-page" data-calc-kind="{e(item['kind'])}">
  <nav class="calc-crumbs" aria-label="Навигация"><a href="/">Сметра</a><span aria-hidden="true">/</span><a href="/kalkulyator">Калькуляторы</a><span aria-hidden="true">/</span><span aria-current="page">{e(item['h1'])}</span></nav>
  <header class="calc-hero"><h1>{e(item['h1'])}</h1><p>{e(item['lead'])}</p></header>
  <section class="calc-tool" aria-label="Расчёт">
    <form class="calc-form" id="calc-form" novalidate>
      <div class="calc-fields">{''.join(field_html(f) for f in spec['fields'])}</div>
    </form>
    <aside class="calc-result" aria-live="polite">
      <div class="calc-error" id="calc-error" role="alert" hidden></div>
      <div class="calc-values" id="calc-values">
        <div class="calc-metric"><span id="calc-primary-label">Результат</span><strong><span id="calc-primary">—</span> <small id="calc-primary-unit"></small></strong></div>
        <div class="calc-metric is-secondary"><span id="calc-secondary-label"></span><strong><span id="calc-secondary"></span> <small id="calc-secondary-unit"></small></strong></div>
      </div>
      <p class="calc-formula" id="calc-formula"></p>
      <div class="calc-cta">
        <div class="calc-cta-buttons"><a class="btn primary" id="calc-to-estimate" href="/app?register=1#calculators">Перенести в смету</a><button class="btn" type="button" id="calc-share">Поделиться расчётом</button></div>
        <p>Сметра соберёт смету с этой позицией: добавьте работы и цены, отправьте клиенту ссылку на согласование. 10 смет бесплатно.</p>
      </div>
    </aside>
  </section>
  <section class="calc-text" aria-labelledby="how-title">
    <h2 id="how-title">Как пользоваться</h2>
    <ol>{''.join(f'<li>{e(step)}</li>' for step in item['steps'])}</ol>
    <p class="calc-note">{e(spec['note'])}</p>
  </section>
  <section class="calc-text" aria-labelledby="faq-title">
    <h2 id="faq-title">Вопросы</h2>
    <div class="faq-list">{''.join(f'<details><summary>{e(q)}</summary><p>{e(a)}</p></details>' for q, a in item['faq'])}</div>
  </section>
  <section class="calc-more" aria-label="Другие калькуляторы"><h2>Другие калькуляторы</h2><div>{others}</div></section>
</main>
""" + footer(pages)


def index(pages, all_specs):
    url = f"{SITE}/kalkulyator"
    title = "Строительные калькуляторы онлайн: плитка, ламинат, краска, штукатурка, бетон | Сметра"
    lead = "Бесплатные калькуляторы материалов для ремонта: площадь с запасом, количество упаковок, банок и мешков. Результат можно перенести в смету."
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "url": url, "name": title, "description": lead, "inLanguage": "ru",
          "hasPart": [{"@type": "WebPage", "url": f"{SITE}/kalkulyator/{p['slug']}", "name": p["h1"]} for p in pages]}
    cards = "".join(f'<a class="calc-card" href="/kalkulyator/{p["slug"]}"><strong>{e(p["h1"])}</strong><span>{e(all_specs[p["kind"]]["description"])}</span></a>'
                    for p in pages)
    return head(title, lead, url, ld) + nav() + f"""<main id="main" class="calc-page">
  <header class="calc-hero"><h1>Калькуляторы материалов</h1><p>{e(lead)}</p></header>
  <div class="calc-cards">{cards}</div>
  <section class="calc-text"><h2>Расчёт — это половина сметы</h2><p>В Сметре материалы из калькулятора становятся позициями сметы: добавьте работы и цены, отправьте клиенту ссылку и получите согласование без созвонов. Итоги считает сервер, а не ИИ, поэтому суммы всегда сходятся.</p>
  <p><a class="btn primary" href="/app?register=1">Начать бесплатно</a></p></section>
</main>
""" + footer(pages)


def main():
    all_specs = specs()
    OUT.mkdir(exist_ok=True)
    for item in PAGES:
        (OUT / f"{item['slug']}.html").write_text(page(item, all_specs[item["kind"]], PAGES), encoding="utf-8")
    (OUT / "index.html").write_text(index(PAGES, all_specs), encoding="utf-8")
    print(f"Calculator pages: {len(PAGES) + 1} in {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
