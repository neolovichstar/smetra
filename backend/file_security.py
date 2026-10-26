"""Upload gates: real file headers, text safety and optional fail-closed ClamAV.

The extension and client-supplied MIME are never trusted. File signatures are
a first gate, not malware detection. Enable CLAMAV_HOST + FILE_AV_REQUIRED=1
in production to require scanning (requests fail closed if scanner is down).
"""
import os
import re
import socket
import struct
from pathlib import Path

from backend.business import DomainError

# Only these types are persisted by the workspace library.
IMAGE_SIGNATURES = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}
OFFICE_SIGNATURES = {".docx", ".xlsx"}
TEXT_EXTENSIONS = {".txt", ".md", ".csv"}
UNSAFE_TEXT_HEADERS = (
    b"MZ", b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf",
    b"\xca\xfe\xba\xbe", b"\xfe\xed\xfe", b"\xce\xfa\xed\xfe",
    b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"%PDF-", b"PK\x03\x04",
    b"PK\x05\x06", b"PK\x07\x08", b"Rar!\x1a\x07", b"7z\xbc\xaf\x27\x1c",
    b"\x1f\x8b\x08", b"\x00asm", b"GIF87a", b"GIF89a",
)


def validate_signature(filename, content):
    """Raise on extension/magic mismatch; ZIP/XML/PDF/image structures are
    subsequently parsed independently by the corresponding safe validators.
    Text has no magic bytes: require real UTF-8 and reject binary/executables.
    """
    ext = Path(str(filename)).suffix.lower()
    if not isinstance(content, bytes) or not content:
        raise DomainError(400, "Файл пустой или повреждён")
    if ext in IMAGE_SIGNATURES:
        if not content.startswith(IMAGE_SIGNATURES[ext]):
            raise DomainError(400, "Сигнатура изображения не соответствует расширению")
        return
    if ext in OFFICE_SIGNATURES:
        if not content.startswith(b"PK\x03\x04"):
            raise DomainError(400, "Сигнатура DOCX/XLSX не соответствует расширению")
        return
    if ext == ".pdf":
        if not re.match(rb"^%PDF-(?:1\.[0-7]|2\.0)(?:\r|\n|[\x00-\x20])", content[:16]):
            raise DomainError(400, "Неверная сигнатура PDF")
        return
    if ext in TEXT_EXTENSIONS:
        raw = content.removeprefix(b"\xef\xbb\xbf")
        if not raw:
            raise DomainError(400, "Пустой текстовый файл")
        if raw.startswith(UNSAFE_TEXT_HEADERS) or raw.startswith((b"#!", b"\xff\xfe", b"\xfe\xff")):
            raise DomainError(400, "Текстовый файл содержит бинарную или исполняемую сигнатуру")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise DomainError(400, "Ожидается текст UTF-8") from None
        if any(ord(char) < 32 and char not in "\t\n\r" for char in text) or "\x7f" in text:
            raise DomainError(400, "Текстовый файл содержит управляющие или бинарные байты")
        if re.match(r"^\s*<(?:!doctype\s+html|html|script|svg)\b", text, re.I):
            raise DomainError(400, "HTML, SVG и исполняемые сценарии не поддерживаются")
        return
    raise DomainError(400, "Неподдерживаемый тип файла")


def scan_upload(content):
    """Scan upload with clamd INSTREAM without writing an untrusted file to disk.

    Fail closed if a scanner is configured but unreachable, or when required.
    Scanner is intentionally not discovered from PATH or a public HTTP API.
    """
    host = os.getenv("CLAMAV_HOST", "").strip()
    required = os.getenv("FILE_AV_REQUIRED", "").strip().lower() in ("1", "true", "yes")
    if not host:
        if required:
            raise DomainError(503, "Антивирусная проверка недоступна. Попробуйте позже")
        return False

    try:
        port = int(os.getenv("CLAMAV_PORT", "3310"))
        timeout = max(1.0, min(15.0, float(os.getenv("CLAMAV_TIMEOUT", "8"))))
        if not 1 <= port <= 65535:
            raise ValueError("port")
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(b"zINSTREAM\x00")
            view = memoryview(content)
            for start in range(0, len(view), 65536):
                chunk = view[start:start + 65536]
                sock.sendall(struct.pack(">I", len(chunk)))
                sock.sendall(chunk)
            sock.sendall(b"\x00\x00\x00\x00")
            reply = sock.recv(4096)
        if b"FOUND" in reply:
            raise DomainError(400, "Файл отклонён антивирусной проверкой")
        if not (reply.strip(b"\x00\r\n ").endswith(b"OK") and reply.startswith(b"stream:")):
            raise OSError("malformed scanner response")
        return True
    except DomainError:
        raise
    except (OSError, ValueError, OverflowError):
        raise DomainError(503, "Антивирусная проверка недоступна. Попробуйте позже") from None
