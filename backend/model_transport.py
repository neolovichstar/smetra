"""Bounded failover before any response bytes are consumed."""
import json
import logging
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)
FREE_ROUTER = "openrouter/free"


def open_completion(request, timeout):
    """Retry an unavailable free model once; never replay a partial stream.

    Keep tools, images and response schemas intact. The free router filters by
    those capabilities, and cannot silently bill a paid fallback model.
    """
    started = time.monotonic()
    payload = json.loads(request.data)
    model = payload.get("model", "")
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        log.warning("OpenRouter request rejected: status=%s model=%s", error.code, model)
        retry = (model.endswith(":free") and error.code in
                 (400, 404, 408, 429, 500, 502, 503, 504))
        if not retry:
            raise
        error.close()
    payload["model"] = FREE_ROUTER
    # Optional reasoning preferences must not rule out otherwise capable models.
    payload.pop("reasoning", None)
    payload["provider"] = {**payload.get("provider", {}), "require_parameters": True}
    fallback = urllib.request.Request(
        request.full_url, json.dumps(payload).encode(),
        dict(request.header_items()), method=request.get_method(),
    )
    remaining = timeout - (time.monotonic() - started)
    if remaining <= 0:
        raise urllib.error.URLError("Completion deadline exceeded")
    return urllib.request.urlopen(fallback, timeout=remaining)
