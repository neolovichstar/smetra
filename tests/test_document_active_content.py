"""Executable document features must never pass as ordinary attachments."""

import base64
import io
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject, TextStringObject

from backend.ai import capture_file
from backend.business import DomainError
from backend.file_extractor import validate_pdf
from backend.office_documents import DOCX, XLSX, W, archive, preview
from tests import office_fixtures


def action_pdf(action, *, indirect=False, **values):
    writer = PdfWriter()
    page = writer.add_blank_page(width=72, height=72)
    font = DictionaryObject({
        NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica'),
    })
    page[NameObject('/Resources')] = DictionaryObject({
        NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)}),
    })
    content = DecodedStreamObject()
    content.set_data(b'BT /F1 12 Tf 5 30 Td (Estimate) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(content)
    action = action if isinstance(action, NameObject) else NameObject(action)
    action = writer._add_object(action) if indirect else action
    annotation = DictionaryObject({
        NameObject('/Type'): NameObject('/Annot'),
        NameObject('/Subtype'): NameObject('/Link'),
        NameObject('/Rect'): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(30), NumberObject(30)]),
        NameObject('/A'): DictionaryObject({NameObject('/S'): action, **{
            NameObject('/' + key): writer._add_object(TextStringObject(value)) if indirect else TextStringObject(value)
            for key, value in values.items()
        }}),
    })
    page[NameObject('/Annots')] = ArrayObject([writer._add_object(annotation)])
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def field_docx(command, split=False):
    root = ET.Element(W + 'document')
    paragraph = ET.SubElement(ET.SubElement(root, W + 'body'), W + 'p')
    ET.SubElement(ET.SubElement(paragraph, W + 'r'), W + 't').text = 'Работы по договору'
    ET.SubElement(ET.SubElement(paragraph, W + 'r'), W + 'fldChar', {W + 'fldCharType': 'begin'})
    for part in ([command[:2], command[2:]] if split else [command]):
        ET.SubElement(ET.SubElement(paragraph, W + 'r'), W + 'instrText').text = part
    ET.SubElement(ET.SubElement(paragraph, W + 'r'), W + 'fldChar', {W + 'fldCharType': 'end'})
    return office_fixtures.rewrite(office_fixtures.docx(), {
        'word/document.xml': ET.tostring(root, encoding='utf-8'),
    })


class DocumentActiveContentTests(unittest.TestCase):
    def test_escaped_and_indirect_pdf_actions_cannot_bypass_validation(self):
        class EscapedLaunch(NameObject):
            def write_to_stream(self, stream, encryption_key=None):
                stream.write(b'/La#75nch')

        escaped = action_pdf(EscapedLaunch('/Launch'), F='document')
        self.assertNotIn(b'/Launch', escaped)
        for raw in (escaped, action_pdf('/Launch', indirect=True, F='document')):
            with self.subTest(indirect=b'/La#75nch' not in raw), self.assertRaises(ValueError):
                validate_pdf(raw)
        validate_pdf(action_pdf('/URI', indirect=True, URI='https://example.invalid'))

    def test_pdf_remote_and_launch_actions_are_rejected(self):
        for action in ('/Launch', '/SubmitForm', '/ImportData', '/GoToR', '/GoToE', '/Rendition'):
            with self.subTest(action=action), self.assertRaises(ValueError):
                validate_pdf(action_pdf(action, F='https://example.invalid/document'))

    def test_pdf_web_link_remains_usable_but_executable_scheme_is_rejected(self):
        validate_pdf(action_pdf('/URI', URI='https://example.invalid/estimate'))
        for uri in ('file:///private/document', 'javascript:void(0)', 'data:text/html,test'):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                validate_pdf(action_pdf('/URI', URI=uri))

    def test_word_dde_and_remote_fields_are_rejected_even_when_split(self):
        for command in ('DDEAUTO server topic item', 'DDE server topic item',
                        'INCLUDETEXT "https://example.invalid/source"', 'LINK server topic item'):
            for split in (False, True):
                with self.subTest(command=command, split=split), self.assertRaises(ValueError):
                    archive(field_docx(command, split), DOCX)

    def test_ordinary_word_fields_and_excel_math_remain_usable(self):
        self.assertEqual(preview(field_docx('PAGE'), DOCX)['blocks'][0]['text'], 'Работы по договору')
        self.assertEqual(preview(office_fixtures.xlsx(), XLSX)['format'], 'xlsx')

    def test_excel_dde_network_and_macro_formulas_are_rejected(self):
        for formula in ('server|topic!A1', 'WEBSERVICE("https://example.invalid")',
                        '_xlfn.RTD("server",,"topic")', 'CALL("library","entry","J")'):
            document = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                        '<sheetData><row r="1"><c r="A1"><f>' + formula + '</f></c></row></sheetData></worksheet>')
            raw = office_fixtures.rewrite(office_fixtures.xlsx(), {'xl/worksheets/sheet1.xml': document})
            with self.subTest(formula=formula), self.assertRaises(ValueError):
                archive(raw, XLSX)

    def test_capture_rejects_office_content_that_attachment_validation_rejects(self):
        raw = office_fixtures.rewrite(office_fixtures.docx('Работы'), {'word/vbaProject.bin': b'not-executed'})
        with self.assertRaises(DomainError):
            capture_file({'name': 'brief.docx', 'mime': DOCX, 'content': base64.b64encode(raw).decode()})

    def test_capture_rejects_active_pdf_before_extraction(self):
        raw = action_pdf('/SubmitForm', F='https://example.invalid/submit')
        with self.assertRaises(DomainError):
            capture_file({'name': 'brief.pdf', 'mime': 'application/pdf', 'content': base64.b64encode(raw).decode()})

    def test_capture_keeps_ordinary_documents_readable(self):
        for name, mime, raw, expected in (
            ('brief.docx', DOCX, office_fixtures.docx('Paint walls'), 'Paint walls'),
            ('prices.xlsx', XLSX, office_fixtures.xlsx(), 'Покраска'),
            ('estimate.pdf', 'application/pdf', action_pdf('/URI', URI='https://example.invalid'), 'Estimate'),
        ):
            with self.subTest(name=name):
                text, image = capture_file({'name': name, 'mime': mime, 'content': base64.b64encode(raw).decode()})
                self.assertIn(expected, text)
                self.assertEqual(image, '')

    def test_capture_scanner_failure_prevents_parsing(self):
        raw = office_fixtures.docx()
        with patch('backend.malware.scan_content', side_effect=DomainError(503, 'scanner unavailable')):
            with patch('backend.file_processing.isolated_extract') as parser:
                with self.assertRaises(DomainError) as error:
                    capture_file({'name': 'brief.docx', 'mime': DOCX, 'content': base64.b64encode(raw).decode()})
        self.assertEqual(error.exception.status, 503)
        parser.assert_not_called()

    def test_capture_pdf_page_limit_is_preserved(self):
        writer = PdfWriter()
        for _ in range(13):
            writer.add_blank_page(width=72, height=72)
        output = io.BytesIO()
        writer.write(output)
        with self.assertRaises(DomainError):
            capture_file({'name': 'long.pdf', 'mime': 'application/pdf',
                          'content': base64.b64encode(output.getvalue()).decode()})


if __name__ == '__main__':
    unittest.main()
