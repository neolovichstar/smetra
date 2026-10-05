"""Small generated OOXML fixtures, with no proprietary binary test assets."""

import io
import zipfile
import xml.etree.ElementTree as ET

from backend.office_documents import W


def docx(text="Техническое задание", rows=None, paragraphs=1):
    document = ET.Element(W + "document")
    body = ET.SubElement(document, W + "body")
    for index in range(paragraphs):
        p = ET.SubElement(body, W + "p")
        ET.SubElement(ET.SubElement(p, W + "r"), W + "t").text = text + (" " + str(index) if paragraphs > 1 else "")
    if rows:
        table = ET.SubElement(body, W + "tbl")
        for source in rows:
            row = ET.SubElement(table, W + "tr")
            for value in source:
                cell = ET.SubElement(row, W + "tc")
                ET.SubElement(ET.SubElement(ET.SubElement(cell, W + "p"), W + "r"), W + "t").text = str(value)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("word/document.xml", ET.tostring(document, encoding="utf-8"))
        package.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        package.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    return output.getvalue()


def xlsx(rows=3, columns=3):
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Работы"
    sheet.append(["Работа", "Цена", "Количество"])
    sheet.append(["Покраска", 15000, 2])
    sheet.append(["Доставка", 2000, "=SUM(B2:B3)"])
    for index in range(3, rows):
        sheet.append(["Позиция " + str(index), index * 100, 1] + list(range(max(0, columns - 3))))
    other = book.create_sheet("Материалы")
    other.append(["Краска", 900])
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def rewrite(raw, additions):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for entry in source.infolist():
            if entry.filename not in additions:
                target.writestr(entry.filename, source.read(entry))
        for name, value in additions.items():
            target.writestr(name, value)
    return output.getvalue()
