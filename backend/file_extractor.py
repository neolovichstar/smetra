"""Isolated bounded text extraction. Called by a subprocess, never by a request."""

import io
import json
import sys
import base64
import math
import urllib.parse

from backend.document_text import MAX_INDEX_CHARS, normalize_text


def render_scans(content, selection=None):
    """Render bounded page images in the credential-free subprocess."""
    validate_pdf(content)
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(content)
    try:
        total = len(document)
        if not 1 <= total <= 100:
            raise ValueError('pages')
        requested = (selection or {}).get('pages', list(range(1, min(2, total) + 1)))
        region = (selection or {}).get('region')
        if (not isinstance(requested, list) or not 1 <= len(requested) <= 2
                or any(type(number) is not int or not 1 <= number <= total for number in requested)
                or len(set(requested)) != len(requested)):
            raise ValueError('page selection')
        if region is not None and (not isinstance(region, list) or len(region) != 4
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in region)
                or not (0 <= region[0] < 1 and 0 <= region[1] < 1
                        and .15 <= region[2] <= 1 and .15 <= region[3] <= 1
                        and region[0] + region[2] <= 1.000001 and region[1] + region[3] <= 1.000001)):
            raise ValueError('region')
        pages = []
        for number in requested:
            page = document[number - 1]
            try:
                width, height = page.get_size()
                if not all(math.isfinite(value) and 1 <= value <= 10000 for value in (width, height)):
                    raise ValueError('dimensions')
                if region is None:
                    crop = (0, 0, 0, 0)
                    scale = min(2400 / max(width, height),
                                (6_000_000 / (width * height)) ** .5)
                else:
                    x, y, view_width, view_height = region
                    crop = (x * width, (1 - y - view_height) * height,
                            (1 - x - view_width) * width, y * height)
                    crop_width, crop_height = width * view_width, height * view_height
                    scale = min(2700 / max(crop_width, crop_height),
                                (6_000_000 / (crop_width * crop_height)) ** .5)
                bitmap = page.render(scale=scale, crop=tuple(max(0, value) for value in crop))
                try:
                    image = bitmap.to_pil().convert('RGB')
                    try:
                        output = io.BytesIO()
                        for quality in (86, 76, 66):
                            output = io.BytesIO()
                            image.save(output, format='JPEG', quality=quality, optimize=True)
                            raw = output.getvalue()
                            if len(raw) <= 1_500_000:
                                break
                        if len(raw) > 1_500_000:
                            raise ValueError('image size')
                        pages.append([number, base64.b64encode(raw).decode()])
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
        return {'pages': pages, 'truncated': len(requested) < total or region is not None,
                'total_pages': total, 'region': region}
    finally:
        document.close()


def cloud_pdf_preflight(content):
    """Fast bounded preflight for externally stored large PDFs.

    The regular small-file validator recursively inspects all PDF objects and
    actions. For image-heavy 50-100 MB plans that traversal can exceed request
    resources before even opening the first page. Cloud reads instead use
    PDFium in an isolated, memory/CPU-limited process: no scripts, launch
    actions, form submissions, attachments or external links are executed.
    """
    if not 0 < len(content) <= 100_000_000 or b"%PDF-" not in content[:1024]:
        raise ValueError("cloud pdf header/size")


def extract_cloud_pdf(content, start_page=1, full_document=False):
    """Extract every text layer (up to 100 pages), or a 12-page window.

    All PDF bytes stay in the isolated extractor and are discarded afterwards.
    Graphic-only pages are explicitly reported as missing text.
    """
    cloud_pdf_preflight(content)
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(content)
    try:
        total = len(document)
        if not 1 <= total <= 300 or not 1 <= start_page <= total:
            raise ValueError("cloud pdf pages")
        if full_document and (total > 100 or start_page != 1):
            raise ValueError("full pdf bounds")
        pages = []
        truncated = not full_document and (total > 12 or start_page > 1)
        end = total if full_document else min(total, start_page + 11)
        for number in range(start_page, end + 1):
            page = document[number - 1]
            try:
                textpage = page.get_textpage()
                try:
                    cap = 6000 if full_document else 12000
                    count = min(textpage.count_chars(), cap)
                    raw_text = textpage.get_text_range(0, count)
                    truncated |= textpage.count_chars() > cap
                    # Keep row breaks: flattening the entire page destroys tables and
                    # makes numbers appear beside the wrong line descriptions.
                    normalized = "\n".join(" ".join(line.split())
                        for line in raw_text[:cap].splitlines() if line.strip())
                    pages.append([number, normalized])
                finally:
                    textpage.close()
            finally:
                page.close()
        next_page = end + 1 if end < total else None
        return {
            "pages": pages, "truncated": truncated,
            "total_pages": total, "next_page": next_page,
        }
    finally:
        document.close()


def render_cloud_page(content, page_number, region=None):
    """Render a bounded high-resolution cloud PDF page, optionally cropped.

    Coordinates are normalized [x, y, width, height] from the top-left.
    Cropping the source before rasterizing makes dimension lines legible
    without exposing the whole private document at excessive resolution.
    """
    if type(page_number) is not int or not 1 <= page_number <= 300:
        raise ValueError("page number")
    if region is not None and (not isinstance(region, list) or len(region) != 4
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in region)
            or not (0 <= region[0] < 1 and 0 <= region[1] < 1
                    and .15 <= region[2] <= 1 and .15 <= region[3] <= 1
                    and region[0] + region[2] <= 1.000001
                    and region[1] + region[3] <= 1.000001)):
        raise ValueError("region")
    cloud_pdf_preflight(content)
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(content)
    try:
        total = len(document)
        if not 1 <= total <= 300 or page_number > total:
            raise ValueError("page outside PDF")
        page = document[page_number - 1]
        try:
            width, height = page.get_size()
            if not all(math.isfinite(value) and 1 <= value <= 10000 for value in (width, height)):
                raise ValueError("dimensions")
            if region is None:
                crop = (0, 0, 0, 0)
                view_width, view_height = width, height
                target = 2300
            else:
                x, y, w, h = region
                crop = (x * width, (1 - y - h) * height,
                        (1 - x - w) * width, y * height)
                view_width, view_height = width * w, height * h
                target = 2600
            # Hard pixel cap includes source pages with unusual aspect ratios.
            scale = min(target / max(view_width, view_height),
                        (6_000_000 / (view_width * view_height)) ** .5)
            bitmap = page.render(scale=scale, crop=tuple(max(0, value) for value in crop))
            try:
                picture = bitmap.to_pil().convert("RGB")
                try:
                    if picture.width * picture.height > 6_200_000:
                        raise ValueError("render size")
                    for quality in (86, 77, 67):
                        out = io.BytesIO()
                        picture.save(out, format="JPEG", quality=quality, optimize=True)
                        encoded = out.getvalue()
                        if len(encoded) <= 1_500_000:
                            break
                    if len(encoded) > 1_500_000:
                        raise ValueError("render bytes")
                    return {
                        "pages": [[page_number, base64.b64encode(encoded).decode("ascii")]],
                        "total_pages": total,
                        "truncated": total > 1 or region is not None,
                        "region": region,
                    }
                finally:
                    picture.close()
            finally:
                bitmap.close()
        finally:
            page.close()
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


def extract(content, mime, *, max_pdf_pages=100, max_content_bytes=5_000_000, start_page=1, include_total=False):
    if not 0 < len(content) <= max_content_bytes:
        raise ValueError("size")
    pages = []
    from backend.office_documents import VIEWABLE, preview, text_sections

    if mime in VIEWABLE:
        result = preview(content, mime, for_assistant=True)
        return text_sections(result), result["truncated"]
    if mime == "text/plain":
        text = content.decode("utf-8-sig")
        # Bounded index, rather than claiming to index an unlimited document.
        normalized = normalize_text(text[:160_000])
        return [(1, normalized[:MAX_INDEX_CHARS])], len(text) > 160_000 or len(normalized) > MAX_INDEX_CHARS
    if mime != "application/pdf":
        raise ValueError("mime")
    validate_pdf(content)
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content), strict=True)
    total_pages = len(reader.pages)
    if reader.is_encrypted or total_pages > max_pdf_pages or not 1 <= start_page <= total_pages:
        raise ValueError("pdf")
    truncated = False
    remaining = MAX_INDEX_CHARS
    for number, page in enumerate(reader.pages, 1):
        if remaining <= 0:
            pages.append((number, ''))
            truncated = True
            continue
        if (
            page.get_contents() is not None
            and len(page.get_contents().get_data()) > 8_000_000
        ):
            raise ValueError("page stream")
        text = normalize_text(page.extract_text() or "")
        length = min(60_000, remaining)
        truncated |= len(text) > length
        pages.append((number, text[:length]))
        remaining -= len(pages[-1][1])
    return (pages, truncated, total_pages) if include_total else (pages, truncated)


def main():
    # Only the explicit cloud PDF mode may use a larger transient input.
    # Standard uploads keep their existing strict 5 MB parser limit.
    cloud_pdf = len(sys.argv) > 1 and sys.argv[1].startswith(("cloud:application/pdf", "cloud-render-pdf:"))
    try:
        import resource

        memory = (768 if cloud_pdf else 384) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (25 if cloud_pdf else 15, 25 if cloud_pdf else 15))
    except ImportError:
        pass  # Windows QA: parent still enforces input/output/time bounds.
    content = sys.stdin.buffer.read(100_000_001 if cloud_pdf else 5_000_001)
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
    if sys.argv[1] == 'render-pdf' or sys.argv[1].startswith('render-pdf:'):
        if not 0 < len(content) <= 5_000_000:
            raise ValueError('size')
        selection = json.loads(sys.argv[1].split(':', 1)[1]) if ':' in sys.argv[1] else None
        if selection is not None and (not isinstance(selection, dict) or set(selection) - {'pages', 'region'}):
            raise ValueError('selection')
        sys.stdout.buffer.write(json.dumps(render_scans(content, selection)).encode())
        return
    if sys.argv[1].startswith("cloud-render-pdf:"):
        value = sys.argv[1].split(":", 1)[1]
        if value.isascii() and value.isdecimal():
            requested_page, region = int(value), None
        else:
            selection = json.loads(value)
            if (not isinstance(selection, dict) or set(selection) != {"page", "region"}):
                raise ValueError("render mode")
            requested_page, region = selection["page"], selection["region"]
        result = render_cloud_page(content, requested_page, region)
        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        return
    if sys.argv[1] == "validate-pdf":
        if not 0 < len(content) <= 5_000_000:
            raise ValueError("size")
        validate_pdf(content)
        sys.stdout.buffer.write(b'{"valid":true}')
        return
    if cloud_pdf:
        parts = sys.argv[1].split(":")
        if len(parts) not in (2, 3) or parts[:2] != ["cloud", "application/pdf"]:
            raise ValueError("cloud mode")
        full_document = len(parts) == 3 and parts[2] == "full"
        start_page = 1 if full_document or len(parts) == 2 else int(parts[2])
        if not 1 <= start_page <= 300:
            raise ValueError("page bounds")
        result = extract_cloud_pdf(content, start_page, full_document=full_document)
        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
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
