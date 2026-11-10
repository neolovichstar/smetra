"""Bounded, non-executing OOXML reader, used only in the isolated parser."""

import io
import csv
import re
import zipfile
import xml.etree.ElementTree as ET

from backend.document_text import MAX_INDEX_CHARS, normalize_text

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIMES = (DOCX, XLSX)
CSV = "text/csv"
VIEWABLE = (*MIMES, CSV)
READABLE = ("text/plain", "application/pdf", *VIEWABLE)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def validate_fields(root, mime):
    """Keep inert maths/page fields, reject DDE, macros and remote data loads."""
    if mime == XLSX:
        for node in root.iter():
            if node.tag.rsplit('}', 1)[-1] not in ('f', 'definedName'):
                continue
            # Quoted Excel string literals are data, not executable tokens.
            formula = re.sub(r'"(?:[^"]|"")*"', '""', node.text or '')
            separator = formula.find('|')
            dde = separator >= 0 and '!' in formula[separator + 1:]
            if dde or re.search(
                r'(?<![\w.])(?:(?:_xlfn|_xlws)\.)*'
                r'(?:WEBSERVICE|RTD|CALL|REGISTER(?:\.ID)?|EXEC|EVALUATE|DDE)\s*\(',
                formula, re.I,
            ):
                raise ValueError('active Excel formula')
        return

    def check(instruction):
        if re.match(r'\s*(?:DDEAUTO|DDE|INCLUDETEXT|INCLUDEPICTURE|LINK|DATABASE)\b', instruction, re.I):
            raise ValueError('active Word field')

    fields = []
    for node in root.iter():
        if node.tag == W + 'fldSimple':
            check(node.get(W + 'instr', ''))
        elif node.tag == W + 'fldChar':
            kind = node.get(W + 'fldCharType')
            if kind == 'begin':
                fields.append([])
            elif kind in ('separate', 'end') and fields:
                if fields[-1] is not None:
                    check(''.join(fields[-1]))
                if kind == 'end':
                    fields.pop()
                else:
                    fields[-1] = None
        elif node.tag == W + 'instrText':
            instruction = node.text or ''
            check(instruction)
            if fields and fields[-1] is not None:
                fields[-1].append(instruction)
    for field in fields:
        if field is not None:
            check(''.join(field))


def archive(content, mime):
    if mime not in MIMES or not 0 < len(content) <= 5_000_000:
        raise ValueError("office bounds")
    result = {}
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        entries = package.infolist()
        if len(entries) > 512 or sum(entry.file_size for entry in entries) > 20_000_000:
            raise ValueError("archive bounds")
        for entry in entries:
            name = entry.filename
            lower = name.lower()
            if (name in result or name.startswith("/") or "\\" in name or
                    ".." in name.split("/") or ":" in name or entry.flag_bits & 1 or
                    entry.file_size > 5_000_000 or
                    entry.file_size > max(entry.compress_size, 1) * 200 or
                    any(part in lower for part in
                        ("vbaproject", "vbadata", "activex/", "embeddings/", "externallinks/", "macrosheets/"))):
                raise ValueError("unsafe archive")
            raw = package.read(entry)
            if lower.endswith((".xml", ".rels")):
                if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", raw, re.I) or b"\x00" in raw:
                    raise ValueError("unsafe XML encoding or declarations")
                root = ET.fromstring(raw)
                if sum(1 for _ in root.iter()) > 100_000:
                    raise ValueError("XML bounds")
                validate_fields(root, mime)
                if lower.endswith(".rels"):
                    for relation in root:
                        if (relation.get("TargetMode", "").strip().lower() == "external" and
                                not relation.get("Type", "").endswith("/hyperlink")):
                            raise ValueError("external content")
                result[name] = root
            else:
                result[name] = None
    main = "word/document.xml" if mime == DOCX else "xl/workbook.xml"
    expected = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
                if mime == DOCX else
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
    types = result.get("[Content_Types].xml")
    if main not in result or result[main] is None or types is None:
        raise ValueError("office structure")
    if not any(node.get("PartName") == "/" + main and node.get("ContentType") == expected for node in types):
        raise ValueError("office type mismatch")
    for node in types:
        if any(token in node.get("ContentType", "").lower() for token in ("macroenabled", "macrosheet", "vba", "oleobject", "activex")):
            raise ValueError("active office content")
    return result


def preview(content, mime, *, for_assistant=False):
    row_limit, column_limit, sheet_limit = (1000, 40, 12) if for_assistant else (100, 20, 6)
    if mime == CSV:
        if not 0 < len(content) <= 5_000_000:
            raise ValueError("CSV bounds")
        text = content.decode("utf-8-sig")
        if "\0" in text:
            raise ValueError("CSV text")
        try:
            dialect = csv.Sniffer().sniff(text[:10000], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows, truncated = [], False
        budget = 120_000
        for number, row in enumerate(csv.reader(io.StringIO(text), dialect=dialect, strict=True), 1):
            if number > row_limit or budget <= 0:
                truncated = True
                break
            values = []
            truncated |= len(row) > column_limit
            for value in row[:column_limit]:
                length = min(1000, budget)
                truncated |= len(value) > length
                values.append(value[:length])
                budget -= len(values[-1])
            rows.append({"number": number, "cells": values})
        return {"format": "csv", "sheets": [{"name": "CSV", "rows": rows}], "truncated": truncated,
                "note": "До 100 строк и 20 столбцов. Ячейки показаны как текст. Оригинал сохраняется без изменений."}
    package = archive(content, mime)
    remaining = MAX_INDEX_CHARS
    truncated = False

    def bounded(value, limit=1000):
        nonlocal remaining, truncated
        value = str(value) if value is not None else ""
        size = min(limit, remaining)
        truncated |= len(value) > size
        result = value[:size]
        remaining -= len(result)
        return result

    if mime == DOCX:
        def paragraph_text(node):
            return ''.join(part.text or '' if part.tag == W + 't' else
                           '\t' if part.tag == W + 'tab' else '\n' if part.tag in (W + 'br', W + 'cr') else ''
                           for part in node.iter())

        body = package["word/document.xml"].find(W + "body")
        if body is None:
            raise ValueError("document body")
        blocks = []
        for index, node in enumerate(body):
            if index >= (1200 if for_assistant else 400) or remaining <= 0:
                truncated = True
                break
            if node.tag == W + "p":
                value = bounded(paragraph_text(node), 10000)
                style = node.find(W + "pPr/" + W + "pStyle")
                heading = style is not None and (style.get(W + "val", "").lower().startswith("heading") or style.get(W + "val", "") == "Title")
                if value:
                    blocks.append({"type": "heading" if heading else "paragraph", "text": value})
            elif node.tag == W + "tbl":
                source_rows = node.findall(W + "tr")
                rows = []
                truncated |= len(source_rows) > row_limit
                for row in source_rows[:row_limit]:
                    cells = row.findall(W + "tc")
                    truncated |= len(cells) > column_limit
                    rows.append([bounded("\n".join(paragraph_text(p)
                        for p in cell.findall(W + "p"))) for cell in cells[:column_limit]])
                blocks.append({"type": "table", "rows": rows})
        return {"format": "docx", "blocks": blocks, "truncated": truncated,
                "note": "Текст и таблицы документа. Изображения, колонтитулы и исходная вёрстка доступны в скачанном оригинале."}

    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
    cached_book = None
    try:
        if for_assistant:
            cached_book = load_workbook(io.BytesIO(content), read_only=True, data_only=True, keep_links=False)
        sheets = []
        truncated |= len(book.worksheets) > sheet_limit
        for sheet in book.worksheets[:sheet_limit]:
            # The stored dimensions are untrusted. Explicit bounds also handle
            # missing dimensions, giant sparse ranges and malicious row indexes.
            rows = []
            truncated |= bool((sheet.max_row or 0) > row_limit or (sheet.max_column or 0) > column_limit)
            bounds = dict(min_row=1, max_row=row_limit, min_col=1, max_col=column_limit)
            cached_rows = iter(cached_book[sheet.title].iter_rows(**bounds)) if cached_book else None
            for number, cells in enumerate(sheet.iter_rows(**bounds), 1):
                cached_cells = next(cached_rows) if cached_rows is not None else None
                values = []
                for column, cell in enumerate(cells):
                    value = cell.value
                    if cell.data_type == "f":
                        value = "Формула (не рассчитана): " + str(value)
                        if cached_cells is not None:
                            cached = cached_cells[column].value
                            value += ("; сохранённый результат (может быть устаревшим): " + str(cached)
                                      if cached is not None else "; сохранённого результата нет")
                    elif hasattr(value, "isoformat"):
                        value = value.isoformat()
                    elif for_assistant and isinstance(value, (int, float)) and cell.number_format != 'General':
                        value = str(value) + ' [формат Excel: ' + str(cell.number_format)[:80] + ']'
                    values.append(bounded(value))
                while values and not values[-1]:
                    values.pop()
                if any(values):
                    rows.append({"number": number, "cells": values})
                if remaining <= 0:
                    truncated = True
                    break
            sheets.append({"name": sheet.title, "rows": rows, **({"visibility": sheet.sheet_state} if for_assistant else {})})
            if remaining <= 0:
                break
        return {"format": "xlsx", "sheets": sheets, "truncated": truncated,
                "note": "До 6 листов, 100 строк и 20 столбцов на лист. Формулы показаны как текст и не вычисляются. Оригинал сохраняется без изменений."}
    finally:
        book.close()
        if cached_book is not None:
            cached_book.close()


def text_sections(result):
    import json
    from openpyxl.utils import get_column_letter

    def cells(values):
        return ' | '.join(get_column_letter(index) + '=' + json.dumps(value, ensure_ascii=False)
                          for index, value in enumerate(values, 1))

    def bounded_sections(sections):
        remaining, output = MAX_INDEX_CHARS, []
        for number, value in sections:
            result['truncated'] |= len(value) > remaining
            output.append((number, value[:remaining]))
            remaining = max(0, remaining - len(output[-1][1]))
        return output

    if result["format"] in ("xlsx", "csv"):
        return bounded_sections((number, "Лист: " + sheet["name"]
            + (' [скрыт в книге]' if sheet.get('visibility', 'visible') != 'visible' else '') + "\n" + "\n".join(
            "Строка " + str(row["number"]) + ": " + cells(row["cells"])
            for row in sheet["rows"])) for number, sheet in enumerate(result["sheets"], 1))
    blocks, table_number = [], 0
    for block in result['blocks']:
        if 'text' in block:
            blocks.append(('Заголовок: ' if block['type'] == 'heading' else '') + block['text'])
        else:
            table_number += 1
            blocks.extend(f'Таблица {table_number}, строка {number}: ' + cells(row)
                          for number, row in enumerate(block['rows'], 1))
    text = normalize_text('\n\n'.join(blocks))
    result['truncated'] |= len(text) > MAX_INDEX_CHARS
    text = text[:MAX_INDEX_CHARS]
    return [(number // 10000 + 1, text[number:number + 10000]) for number in range(0, len(text), 10000)]
