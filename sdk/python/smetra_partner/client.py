"""Minimal server-only Python SDK for Smetra Partner API."""
import json
import urllib.error
import urllib.parse
import urllib.request


class PartnerAPIError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class PartnerClient:
    def __init__(self, api_key, *, base_url="https://console.smetra.online", timeout=8):
        if not isinstance(api_key, str) or not api_key.startswith("smp_live_"):
            raise ValueError("Invalid partner API key")
        if base_url.rstrip("/") != "https://console.smetra.online":
            raise ValueError("Partner API host must be https://console.smetra.online")
        self._token = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = max(1, min(int(timeout), 30))

    def _request(self, path, data=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
        headers = {"Authorization": "Partner " + self._token,
                   "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=body,
                                     headers=headers, method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read(2_000_000))
        except urllib.error.HTTPError as exc:
            try:
                message = json.loads(exc.read(4096)).get("error", "Partner API error")
            except (ValueError, UnicodeError):
                message = "Partner API error"
            raise PartnerAPIError(exc.code, message) from None

    def summary(self):
        return self._request("/api/partners/console/summary")

    def analytics(self, days=30):
        if days not in (7, 30, 90):
            raise ValueError("days must be 7, 30 or 90")
        return self._request("/api/partners/console/analytics?days=" + str(days))

    def domain(self):
        return self._request("/api/partners/console/domain")

    def begin_verification(self, method="dns"):
        return self._request("/api/partners/console/domain", {"method": method})

    def verify_domain(self):
        return self._request("/api/partners/console/domain/verify", {})

    def update_catalog(self, products):
        return self._request("/api/partners/console/catalog", {"products": products})

    def report_event(self, *, event_key, event_type, amount_kopecks=0):
        return self._request("/api/partners/console/events", {
            "event_key": event_key, "event_type": event_type,
            "amount_kopecks": amount_kopecks,
        })
