"""Minimal server-side MyTracker event bridge.

This module is intentionally best-effort: analytics must never make a confirmed
payment fail. It sends only the internal Smetra user UUID plus bounded event
metadata; no email, phone, client data, estimate text, or payment credentials.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

_ENDPOINT = "https://tracker-s2s.my.com/v1/customEvent/"
_TIMEOUT_SECONDS = 2.5


def configured():
    return bool(os.getenv("MYTRACKER_S2S_APP_ID", "").strip() and os.getenv("MYTRACKER_S2S_KEY", "").strip())


def _bounded(value, maximum=255):
    return str(value)[:maximum]


def track_custom_event(user_id, name, params=None):
    """Send a custom event to MyTracker S2S without ever raising to callers.

    Returns True only after MyTracker answers with a 2xx response. A failure is
    logged without secrets and does not affect the business transaction.
    """
    app_id = os.getenv("MYTRACKER_S2S_APP_ID", "").strip()
    api_key = os.getenv("MYTRACKER_S2S_KEY", "").strip()
    if not app_id or not api_key or not user_id or not name:
        return False

    safe_params = {}
    for key, value in (params or {}).items():
        if value is None:
            continue
        safe_params[_bounded(key)] = _bounded(value)

    payload = {
        "customUserId": _bounded(user_id, 1024),
        "customEventName": _bounded(name),
        "eventTimestamp": int(time.time()),
    }
    if safe_params:
        payload["customEventParams"] = safe_params

    url = _ENDPOINT + "?" + urllib.parse.urlencode({"idApp": app_id})
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "smetra-backend/1.6.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            response.read(4096)
            return 200 <= int(response.status) < 300
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        # Do not log payload, user identifier, or credentials.
        print(json.dumps({"mytracker_s2s_error": type(error).__name__}), flush=True)
        return False
