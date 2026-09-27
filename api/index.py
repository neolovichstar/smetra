"""Vercel entrypoint; preserve the existing HTTP API and authentication."""

import ipaddress
import os
from backend.app import Handler


class handler(Handler):
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
