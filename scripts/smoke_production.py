"""Read-only Smetra release smoke checks.

Run against a staged production deployment BEFORE assigning smetra.online.
No credentials, account mutations, trial estimates, or payment requests.
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def inspect(base_url):
    parsed = urllib.parse.urlsplit(base_url)
    if (parsed.scheme != "https" and
            not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"))):
        raise ValueError("Smoke checks require HTTPS or local test HTTP")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Use only the bare origin; do not pass credentials or query parameters")
    origin = base_url.rstrip("/")
    probes = [
        ("/api/me", 401, "application/json", "database-backed session check"),
        ("/api/auth/providers", 200, "application/json", "sign-in configuration"),
        ("/api/billing/catalog", 200, "application/json", "public tariff catalog"),
        ("/app", 200, "text/html", "cabinet shell"),
        ("/terms", 200, "text/html", "terms of use"),
        ("/privacy", 200, "text/html", "personal data policy"),
    ]
    for path, expected, content_type, label in probes:
        request = urllib.request.Request(
            origin + path, headers={"Accept": "application/json, text/html"},
            method="GET",
        )
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        try:
            code = response.status
            media = response.headers.get("Content-Type", "")
            data = response.read(256 * 1024)
            if code != expected or content_type not in media:
                raise RuntimeError(
                    f"{path}: expected {expected} {content_type}, got {code} {media}"
                )
            if content_type == "application/json":
                parsed_body = json.loads(data)
                if not isinstance(parsed_body, dict):
                    raise RuntimeError(f"{path}: expected a JSON object")
                if path == "/api/auth/providers" and "providers" not in parsed_body:
                    raise RuntimeError("Provider configuration is incomplete")
                if path == "/api/billing/catalog" and not isinstance(parsed_body.get("plans"), list):
                    raise RuntimeError("Tariff catalog is malformed")
            if path == "/api/me" and response.headers.get("Cache-Control", "").lower() != "no-store":
                raise RuntimeError("Session endpoint must not be cached")
            print(f"PASS {label}: {path} -> {code}")
        finally:
            response.close()
    print("Release smoke checks passed: no authenticated or paid operations were invoked.")


def main():
    parser = argparse.ArgumentParser(description="Smetra read-only go/no-go smoke test")
    parser.add_argument("--base-url", default="https://smetra.online")
    arguments = parser.parse_args()
    try:
        inspect(arguments.base_url)
    except (ValueError, RuntimeError, OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        print(f"SMOKE FAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
