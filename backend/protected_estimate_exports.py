"""Exports accept only the already filtered protected-document DTO."""
import io
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from backend.documents import Download


def _columns(document):
    if "sections" in document:
        return ["Раздел", "Стоимость"], [[row["name"], Decimal(row["amount_kopecks"]) / 100] for row in document["sections"]]
    headers = ["Наименование"]
    policy = document["permissions"]
    if policy["show_quantities"]:
        headers.extend(["Количество", "Ед."])
    if policy["show_prices"]:
        if policy["show_quantities"]:
            headers.append("Цена")
        headers.append("Стоимость")
    rows = []
    for item in document.get("items", []):
        row = [item["name"]]
        if policy["show_quantities"]:
            row.extend([item["quantity"], item["unit"]])
        if policy["show_prices"]:
            if policy["show_quantities"]:
                row.append(Decimal(item["unit_price"]) / 100)
            row.append(Decimal(item["subtotal"]) / 100)
        rows.append(row)
    return headers, rows


def export(document, kind):
    if kind == "pdf":
        return Download(pdf(document), "application/pdf", "smetra-protected.pdf")
    return Download(xlsx(document), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "smetra-protected.xlsx")


def pdf(document):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    if "Smetra" not in pdfmetrics.getRegisteredFontNames():
        font = Path(__file__).resolve().parents[1] / "apps/web/assets/fonts/manrope-400.ttf"
        pdfmetrics.registerFont(TTFont("Smetra", str(font)))
    body = ParagraphStyle("ProtectedBody", fontName="Smetra", fontSize=9, leading=15, spaceAfter=10, wordWrap="CJK")
    heading = ParagraphStyle("ProtectedTitle", parent=body, fontSize=23, leading=30, spaceAfter=18)
    small = ParagraphStyle("ProtectedSmall", parent=body, fontSize=8, leading=12, textColor=colors.HexColor("#626266"))

    def p(value, style=body):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)

    stream = io.BytesIO()
    doc = SimpleDocTemplate(stream, leftMargin=42, rightMargin=42, topMargin=42, bottomMargin=45,
                            title=f"{document['number']} · версия {document['version']}", author=document["contractor"])
    from datetime import datetime
    from backend.business import BUSINESS_TIMEZONE
    date = datetime.fromtimestamp(document["created_at"], BUSINESS_TIMEZONE).strftime("%d.%m.%Y")
    story = [p(document["contractor"], small), Spacer(1, 18), p(document["title"], heading),
             p(f"{document['number']} · версия {document['version']} · {date}", small)]
    if document.get("recipient"):
        story.append(p("Для: " + document["recipient"]))
    if document.get("alternative_label"):
        story.append(p("Вариант: " + document["alternative_label"]))
    headers, rows = _columns(document)
    if rows:
        formatted = [[p(value if not isinstance(value, Decimal) else f"{value:,.2f}".replace(",", " "), small)
                      for value in row] for row in [headers, *rows]]
        widths = [doc.width] if len(headers) == 1 else [doc.width * .48, *([doc.width * .52 / (len(headers) - 1)] * (len(headers) - 1))]
        table = Table(formatted, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f1f2")),
            ("LINEBELOW", (0, 0), (-1, -1), .4, colors.HexColor("#dedee1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]))
        story.extend([Spacer(1, 12), table])
    total = f"{Decimal(document['amount_kopecks']) / 100:,.2f}".replace(",", " ") + " " + document["currency"]
    story.extend([Spacer(1, 20), p("Итого: " + total, heading)])
    if document.get("due_date"):
        story.append(p("Срок: " + document["due_date"]))
    from backend.estimate_assemblies import SCOPE_LABELS
    for key, label in SCOPE_LABELS.items():
        if entries := document.get("scope", {}).get(key):
            story.extend([p(label), *[p("• " + entry) for entry in entries]])
    story.extend([p(document.get("terms", "")), p(document.get("notice", ""), small), p(document["decision_notice"], small)])

    def page(canvas, pdfdoc):
        canvas.saveState()
        if document.get("watermark"):
            canvas.setFillColor(colors.HexColor("#777777"))
            canvas.setFillAlpha(.12)
            canvas.setFont("Smetra", 10)
            canvas.translate(298, 420)
            canvas.rotate(30)
            for offset in (-230, -70, 90, 250):
                canvas.drawCentredString(0, offset, document["watermark"])
        canvas.restoreState()
        canvas.saveState()
        canvas.setFont("Smetra", 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(42, 25, document["number"] + " · защищённое предложение")
        canvas.drawRightString(550, 25, str(pdfdoc.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=page, onLaterPages=page)
    return stream.getvalue()


def xlsx(document):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Предложение"
    headers, rows = _columns(document)
    values = [[document["contractor"]], [document["title"]],
              [document["number"], "Версия", document["version"], document.get("alternative_label", "")],
              [document.get("watermark", "")], [], headers, *rows, [],
              ["Итого", Decimal(document["amount_kopecks"]) / 100, document["currency"]],
              [document.get("terms", "")], [document.get("notice", "")], [document["decision_notice"]]]
    for row in values:
        sheet.append(row)
    from backend.estimate_assemblies import SCOPE_LABELS
    for key, label in SCOPE_LABELS.items():
        if entries := document.get("scope", {}).get(key):
            sheet.append([label])
            for entry in entries:
                sheet.append([entry])
    # User-controlled text is always an XLSX string, even if it starts with '='.
    for row in sheet:
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.font = Font(name="Arial", size=11, color="222222")
            if isinstance(cell.value, (int, float, Decimal)):
                cell.number_format = "#,##0.00"
    for cell in sheet[6]:
        cell.font = Font(name="Arial", bold=True, color="222222")
        cell.fill = PatternFill("solid", fgColor="EFEFF1")
    sheet.column_dimensions["A"].width = 58
    for column in ("B", "C", "D", "E"):
        sheet.column_dimensions[column].width = 20
    sheet.freeze_panes = "B7"
    sheet.print_options.horizontalCentered = True
    sheet.print_title_rows = "1:6"
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "portrait"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    if document.get("watermark"):
        sheet.oddHeader.center.text = document["watermark"].replace("&", "&&")
        sheet.oddHeader.center.size = 8
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()
