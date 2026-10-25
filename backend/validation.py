"""Strict JSON boundaries shared by inbound requests and external providers."""

import json
import math


def load_json(raw, *, object_only=True):
    def reject_constant(value):
        raise ValueError("Non-finite JSON number")

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def validate(value, depth=0):
        if depth > 64:
            raise ValueError("JSON nesting limit")
        if isinstance(value, dict):
            for key, item in value.items():
                validate(key, depth + 1)
                validate(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                validate(item, depth + 1)
        elif isinstance(value, str):
            if "\0" in value:
                raise ValueError("Null character")
            value.encode("utf-8")
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite JSON number")

    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8-sig")
        value = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_keys)
        if object_only and not isinstance(value, dict):
            raise ValueError("Expected object")
        validate(value)
        return value
    except (UnicodeError, RecursionError) as error:
        raise ValueError("Invalid JSON encoding or nesting") from error


def read_json_response(response, limit):
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Response too large")
    return load_json(raw)


def usage_counts(value):
    """Return storable provider token counts, or mark usage as unknown."""
    if not isinstance(value, dict):
        return None
    counts = tuple(value.get(key) for key in ("prompt_tokens", "completion_tokens"))
    if not all(type(count) is int and 0 <= count <= 2_147_483_647 for count in counts):
        return None
    return counts
