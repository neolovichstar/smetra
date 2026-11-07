"""Isolated bounded text extraction. Called by a subprocess, never by a request."""

import io
import json
import sys
import base64
import math
import urllib.parse


def render_scans(content):
    """Render bounded page images in the credential-free subprocess."""
    validate_pdf(content)
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(content)
    try:
        total = len(document)
        if not 1 <= total <= 100:
            raise ValueError('pages')
        pages = []
        for number in range(min(2, total)):
            page = document[number]
            try:
                width, height = page.get_size()
                if not all(math.isfinite(value) and 1 <= value <= 10000 for value in (width, height)):
                    raise ValueError('dimensions')
                bitmap = page.render(scale=1600 / max(width, height))
                try:
                    image = bitmap.to_pil().convert('RGB')
                    try:
                        output = io.BytesIO()
                        image.save(output, format='JPEG', quality=82, optimize=True)
                        raw = output.getvalue()
                        if len(raw) > 1_500_000:
                            raise ValueError('image size')
                        pages.append([number + 1, base64.b64encode(raw).decode()])
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
        return {'pages': pages, 'truncated': total > 2, 'total_pages': total}
    finally:
        document.close()


def validate_pdf(content):
    from pypdf import PdfReader
    from pypdf.generic import DictionaryObject, ArrayObject, IndirectObject

    reader = PdfReader(io.BytesIO(content), strict=True)
    if reader.is_encrypted or len(reader.pages) > 300:
        raise ValueError("pdf bounds")
    seen = set()
    forbidden = {
        "/JavaScript",
        "/JS",
        "/Launch",
        "/EmbeddedFiles",
        "/EmbeddedFile",
        "/OpenAction",
        "/AA",
        "/RichMedia",
        "/XFA",
    }
    forbidden_actions = {
        '/JavaScript', '/Launch', '/SubmitForm', '/ImportData', '/GoToR',
        '/GoToE', '/Rendition', '/Movie', '/Sound', '/RichMediaExecute',
    }

    def resolve(value):
        references = set()
        while isinstance(value, IndirectObject):
            key = (value.idnum, value.generation)
            if key in references or len(references) >= 50:
                raise ValueError('cyclic action')
            references.add(key)
            value = value.get_object()
        return value

    def inspect(value, depth=0):
        if depth > 50 or len(seen) > 20000:
            raise ValueError("object limits")
        if isinstance(value, IndirectObject):
            key = (value.idnum, value.generation)
            if key in seen:
                return
            seen.add(key)
            value = value.get_object()
        if isinstance(value, DictionaryObject):
            if forbidden.intersection(value.keys()):
                raise ValueError("active content")
            # Action types are NameObject VALUES of /S, not dictionary keys.
            # Parsed names also cover escaped names and compressed objects.
            action = resolve(value.get('/S'))
            if isinstance(action, str) and action in forbidden_actions:
                raise ValueError('active PDF action')
            if action == '/URI':
                uri = resolve(value.get('/URI'))
                if (not isinstance(uri, str) or any(ord(char) < 32 or ord(char) == 127 for char in uri)
                        or urllib.parse.urlsplit(uri.strip()).scheme.lower() not in ('http', 'https', 'mailto')):
                    raise ValueError('unsafe PDF link')
            for child in value.values():
                inspect(child, depth + 1)
        elif isinstance(value, ArrayObject):
            for child in value:
                inspect(child, depth + 1)

    inspect(reader.trailer)


def extract(content, mime, *, max_pdf_pages=100):
    if not 0 < len(content) <= 5_000_000:
        raise ValueError("size")
    pages = []
    from backend.office_documents import VIEWABLE, preview, text_sections

    if mime in VIEWABLE:
        result = preview(content, mime)
        return text_sections(result), result["truncated"]
    if mime == "text/plain":
        text = content.decode("utf-8-sig")
        # Bounded index, rather than claiming to index an unlimited document.
        normalized = " ".join(text[:160_000].split())
        return [(1, normalized[:120_000])], len(text) > 160_000 or len(normalized) > 120_000
    if mime != "application/pdf":
        raise ValueError("mime")
    validate_pdf(content)
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content), strict=True)
    if reader.is_encrypted or len(reader.pages) > max_pdf_pages:
        raise ValueError("pdf")
    truncated = len(reader.pages) > 12
    for number, page in enumerate(reader.pages[:12], 1):
        if (
            page.get_contents() is not None
            and len(page.get_contents().get_data()) > 8_000_000
        ):
            raise ValueError("page stream")
        text = page.extract_text() or ""
        truncated |= len(text) > 10_000
        pages.append((number, " ".join(text[:10_000].split())))
    return pages, truncated


def main():
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    except ImportError:
        pass  # Windows QA: parent still enforces input/output/time bounds.
    content = sys.stdin.buffer.read(5_000_001)
    if sys.argv[1].startswith(("validate-office:", "preview:")):
        from backend.office_documents import CSV, archive, preview

        mode, mime = sys.argv[1].split(":", 1)
        if mode == "validate-office":
            preview(content, mime) if mime == CSV else archive(content, mime)
            result = {"valid": True}
        else:
            result = preview(content, mime)
        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        return
    if sys.argv[1] == 'render-pdf':
        if not 0 < len(content) <= 5_000_000:
            raise ValueError('size')
        sys.stdout.buffer.write(json.dumps(render_scans(content)).encode())
        return
    if sys.argv[1] == "validate-pdf":
        if not 0 < len(content) <= 5_000_000:
            raise ValueError("size")
        validate_pdf(content)
        sys.stdout.buffer.write(b'{"valid":true}')
        return
    capture = sys.argv[1].startswith('capture:')
    mime = sys.argv[1].removeprefix('capture:')
    pages, truncated = extract(content, mime, max_pdf_pages=12 if capture else 100)
    sys.stdout.buffer.write(
        json.dumps({"pages": pages, "truncated": truncated}, ensure_ascii=False).encode(
            "utf-8"
        )
    )


if __name__ == "__main__":
    main()
