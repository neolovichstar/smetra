"""Vercel entrypoint; preserve the existing HTTP API and authentication."""

import ipaddress
import os
from backend.app import Handler, WEB


class handler(Handler):
    def api(self, method, path, query, con):
        from backend.community import handles, route

        if handles(path):
            result = route(self, method, path, query, con)
            if result is not None:
                return result
            return self.send_json(404, {"error": "Не найдено"})
        return super().api(method, path, query, con)

    def static(self, path):
        if path == "/communication-center.js":
            data = (WEB / "communication-center.js").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)
            return
        return super().static(path)

    def dispatch(self, method):
        if os.getenv("VERCEL"):
            # Vercel overwrites X-Forwarded-For with the client IP. Do not
            # prefer an arbitrary client-supplied header for rate limiting.
            forwarded = self.headers.get("x-forwarded-for", "")
            try:
                address = str(ipaddress.ip_address(forwarded.split(",")[0].strip()))
                self.client_address = (address, 0)
            except ValueError:
                pass
        super().dispatch(method)
