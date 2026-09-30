"""Private, client-safe field report generated from live construction records."""

import io
from datetime import date
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from backend.attachments import download
from backend.documents import Download


def report(service, obj, snapshot):
    from PIL import Image as PillowImage
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font = Path(__file__).resolve().parents[1] / 'apps/web/assets/fonts/manrope-400.ttf'
    if 'Smetra' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('Smetra', str(font)))
    body = ParagraphStyle('ReportBody', fontName='Smetra', fontSize=9, leading=14,
                          textColor=colors.HexColor('#2f3946'))
    small = ParagraphStyle('ReportSmall', parent=body, fontSize=7.5, leading=11)
    title = ParagraphStyle('ReportTitle', parent=body, fontSize=23, leading=31,
                           textColor=colors.HexColor('#17293c'))

    def text(value, style=body):
        return Paragraph(escape(str(value or '')), style)

    def currency(value):
        return f'{Decimal(value) / 100:,.2f}'.replace(',', ' ') + ' ₽'

    project = service.con.execute(
        'SELECT status,amount_kopecks FROM projects WHERE id=? AND workspace_id=?',
        (obj['project_id'], service.wid),
    ).fetchone() if obj['project_id'] else None
    paid = service.con.execute(
        'SELECT coalesce(sum(amount_kopecks),0) FROM project_payments WHERE project_id=? AND workspace_id=?',
        (obj['project_id'], service.wid),
    ).fetchone()[0] if project else 0
    workspace = service.con.execute('SELECT name FROM workspaces WHERE id=?', (service.wid,)).fetchone()
    client = service.get('clients', obj['client_id']) if obj['client_id'] else None
    stream = io.BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=(595.28, 841.89), leftMargin=44, rightMargin=44,
                            topMargin=45, bottomMargin=45, title='Отчёт по объекту · Сметра')
    story = [text('СМЕТРА / ОТЧЁТ ПО ОБЪЕКТУ', small), Spacer(1, 14),
             text(obj['name'], title), Spacer(1, 8),
             text(f'Сформирован {date.today().strftime("%d.%m.%Y")} · Исполнитель: {workspace["name"]}'),
             text(f'Заказчик: {client["name"] if client else "Не указан"}'),
             text(f'Статус: {project["status"] if project else obj["status"]}'), Spacer(1, 18)]
    work = [item for item in snapshot['quantities'] if item['kind'] == 'work' and Decimal(item['actual_quantity']) > 0]
    story += [text('Выполненные работы', title), Spacer(1, 8)]
    rows = [[text('Работа', small), text('План', small), text('Выполнено', small)]]
    for item in work:
        rows.append([text(item['title'], small), text(item['quantity'] + ' ' + item['unit'], small),
                     text(item['actual_quantity'] + ' ' + item['unit'], small)])
    if len(rows) == 1:
        rows.append([text('Фактические объёмы ещё не записаны', small), text('—', small), text('—', small)])
    table = Table(rows, colWidths=[270, 110, 127], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e9eef4')),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                               ('LINEBELOW', (0, 0), (-1, -1), .4, colors.HexColor('#dce3ec')),
                               ('TOPPADDING', (0, 0), (-1, -1), 8),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    story += [table, Spacer(1, 22), text('Материалы', title), Spacer(1, 8)]
    if snapshot['procurement']:
        material_rows = [[text('Материал', small), text('Нужно', small), text('Получено', small)]]
        for item in snapshot['procurement']:
            material_rows.append([text(item['title'], small),
                                  text(item['required_quantity'] + ' ' + item['unit'], small),
                                  text(item['received_quantity'] + ' ' + item['unit'], small)])
        materials = Table(material_rows, colWidths=[270, 110, 127], repeatRows=1, hAlign='LEFT')
        materials.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e9eef4')),
                                       ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                       ('LINEBELOW', (0, 0), (-1, -1), .4, colors.HexColor('#dce3ec')),
                                       ('TOPPADDING', (0, 0), (-1, -1), 8),
                                       ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
        story.append(materials)
    else:
        story.append(text('Материалы по норме пока не добавлены.'))
    story += [Spacer(1, 22), text('Согласование и оплаты', title), Spacer(1, 8)]
    base = snapshot['scope']['base_quote_kopecks']
    if base is not None:
        story.append(text('Основная смета: ' + currency(base)))
    story.append(text('Согласованные допработы: ' + currency(snapshot['scope']['approved_changes_kopecks'])))
    if project:
        story.append(text('Учтено поступлений: ' + currency(paid)))
    story.append(text('Поступления указаны по записям исполнителя и не являются кассовым чеком.', small))
    photos = service.con.execute(
        'SELECT f.*,l.work_date,l.work_description FROM construction_log_photos p '
        'JOIN construction_daily_logs l ON l.id=p.log_id AND l.workspace_id=p.workspace_id '
        'JOIN files f ON f.id=p.file_id AND f.workspace_id=p.workspace_id '
        'WHERE p.object_id=? AND p.workspace_id=? ORDER BY l.work_date DESC,p.created_at DESC LIMIT 6',
        (obj['id'], service.wid),
    ).fetchall()
    if photos:
        story += [Spacer(1, 22), text('Фото выполненных работ', title), Spacer(1, 8)]
        for row in photos:
            if row['mime'] not in ('image/png', 'image/jpeg'):
                continue
            try:
                raw = download(row, service.con).data
                with PillowImage.open(io.BytesIO(raw)) as original:
                    picture = original.convert('RGB')
                    picture.thumbnail((850, 600))
                    image_bytes = io.BytesIO()
                    picture.save(image_bytes, format='JPEG', quality=75)
                    width, height = picture.size
                image_bytes.seek(0)
                scale = min(235 / width, 160 / height)
                story += [text(row['work_date'] + ' · ' + row['work_description'], small),
                          Image(image_bytes, width=width * scale, height=height * scale), Spacer(1, 12)]
            except (OSError, ValueError):
                continue
    story += [Spacer(1, 18), text('Отчёт сформирован из записей по объекту. Для принятия работ используйте отдельный акт.', small)]
    doc.build(story)
    return Download(stream.getvalue(), 'application/pdf', 'smetra-construction-report.pdf')
