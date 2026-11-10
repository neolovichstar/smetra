"""Shared bounds and text normalization for isolated document readers."""

import re

MAX_INDEX_CHARS = 120_000
MAX_SOURCES = 100
PARSER_VERSION = 2


def normalize_text(value):
    """Preserve rows, paragraphs and tabs; remove inert control characters."""
    value = value.replace('\r\n', '\n').replace('\r', '\n')
    value = ''.join(char for char in value if char in '\n\t' or ord(char) >= 32)
    lines = [re.sub(r'[ \u00a0\u202f]+', ' ', line).rstrip() for line in value.split('\n')]
    return re.sub(r'\n{4,}', '\n\n\n', '\n'.join(lines)).strip()
