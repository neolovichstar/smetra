"""Render a disposable multilingual PDF fixture for visual QA."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from backend.documents import pdf
    import pypdfium2
    from pypdf import PdfReader
    from io import BytesIO

    root = Path(__file__).resolve().parents[1] / "data/qa"
    root.mkdir(parents=True, exist_ok=True)
    snapshot = dict(
        company="Студия «Пример»",
        title="Проект для клиента",
        client="Компания «Горизонт»",
        company_details="Контакт: hello@example.test",
        currency="RUB",
        amount_kopecks=7800000,
        description="Проверка многостраничного документа: кириллица, таблицы и переносы.",
        terms="Оплата по этапам. Условия согласуются сторонами.",
        due_date="2026-10-31",
        items=[
            dict(
                name="Подготовка материалов",
                description="Состав работ и ожидаемый результат.",
                quantity="1.5",
                unit="час",
                unit_price=5200000,
                subtotal=7800000,
                included=True,
            )
        ],
    )
    doc = dict(
        name="Коммерческое предложение",
        number=1,
        template="Business",
        kind="proposal",
        snapshot=json.dumps(snapshot, ensure_ascii=False),
    )
    content = pdf(doc)
    (root / "document-example.pdf").write_bytes(content)
    assert "Горизонт" in PdfReader(BytesIO(content)).pages[0].extract_text()
    rendered = pypdfium2.PdfDocument(content)
    for index in range(len(rendered)):
        rendered[index].render(scale=1.5).to_pil().save(
            root / f"document-page-{index + 1}.png"
        )
    # A single large table cell must split rather than crash rendering.
    snapshot["items"][0]["description"] = "Длинное описание работ. " * 130
    doc["snapshot"] = json.dumps(snapshot, ensure_ascii=False)
    assert len(PdfReader(BytesIO(pdf(doc))).pages) > 1
    print("PDF: Cyrillic extraction, visual render and long-row pagination PASS")


if __name__ == "__main__":
    main()
