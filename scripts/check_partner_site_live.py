"""Verify the live partner hostname serves a DIFFERENT site than smetra.online.

Runs on GitHub Actions after a feature-branch deployment. No credentials.
"""
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request


def fetch(path, *, timeout=12):
    request = urllib.request.Request(
        path, headers={"Accept": "text/html", "User-Agent": "SmetraPartnerSiteSmoke/1"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise AssertionError(f"{path}: HTTP {response.status}")
        text = response.read(150_000).decode("utf-8", "replace")
        return text


def check_once():
    landing = fetch("https://console.smetra.online/")
    if "Сметра для партнёров" not in landing or "Больше продаж." not in landing:
        raise AssertionError("Console root is not the partner-specific marketing landing")
    if 'href="/app"' not in landing or 'href="/docs"' not in landing:
        raise AssertionError("Partner navigation to /app and /docs missing")

    cabinet = fetch("https://console.smetra.online/app")
    if 'id="connect"' not in cabinet or 'id="dashboard"' not in cabinet:
        raise AssertionError("Partner console app is not available at /app")
    if "Больше продаж." in cabinet:
        raise AssertionError("Cabinet returned the partner marketing landing")

    docs = fetch("https://console.smetra.online/docs")
    if ("Developer Docs" not in docs or "<h1>Smetra Partner API</h1>" not in docs
            or "partner-docs.js" in docs or "Загрузка документации" in docs):
        raise AssertionError("Documentation must be static pre-rendered HTML without fetch")

    source = fetch("https://console.smetra.online/partner-docs.md")
    if not source.lstrip().startswith("# Smetra Partner API"):
        raise AssertionError("Markdown API source is missing")

    sdk = fetch("https://console.smetra.online/partner-sdk.js")
    if "SmetraPartner" not in sdk:
        raise AssertionError("Partner JavaScript SDK is missing")

    openapi = fetch("https://console.smetra.online/partner-openapi.json")
    if '"openapi": "3.1.0"' not in openapi:
        raise AssertionError("Partner OpenAPI 3.1 contract missing")

    customer = fetch("https://smetra.online/")
    if "Сметра для партнёров" in customer:
        raise AssertionError("Consumer main hostname incorrectly serves partner landing")
    print("PASS: separate partner landing, cabinet, docs, SDK; product root remains distinct")


def main():
    attempts = 8
    for attempt in range(attempts):
        try:
            check_once()
            return 0
        except (AssertionError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"Attempt {attempt + 1}/{attempts}: {exc}", flush=True)
            if attempt < attempts - 1:
                time.sleep(9)
    return 1


if __name__ == "__main__":
    sys.exit(main())
