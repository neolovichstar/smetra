"""Disposable local HTTP read benchmark. Never targets a deployment or real data."""
import argparse
import concurrent.futures
import contextlib
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--requests", type=int, default=3000)
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()
    if not (1 <= args.users <= 10000 and 1 <= args.requests <= 30000 and 1 <= args.workers <= 128):
        parser.error("Use 1-10000 users, 1-30000 requests and 1-128 workers")
    if any(os.getenv(name) for name in ("DATABASE_URL", "RUNTIME_DATABASE_URL", "VERCEL")):
        raise RuntimeError("This benchmark requires a disposable local environment")
    from scripts.fixture_network import restrict_to_loopback
    restrict_to_loopback()
    from tests.test_business import BusinessFlows

    # Avoid measuring the test server's default five-connection accept backlog.
    # Production admission is covered separately by the PostgreSQL pool gate.
    http.server.ThreadingHTTPServer.request_queue_size = 128
    BusinessFlows.setUpClass()
    fixture, credentials = BusinessFlows(), []
    try:
        with fixture.mod.db() as con:
            for index in range(args.users):
                token, user_id = secrets.token_urlsafe(32), fixture.mod.uid()
                con.execute("INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES(?,?,?,?,?,?)",
                            (user_id, f"load-{index}@example.invalid", "login-disabled-fixture", "Load fixture", fixture.mod.now(), fixture.mod.now()))
                con.execute("INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)",
                            (fixture.mod.uid(), user_id, hashlib.sha256(token.encode()).hexdigest(), fixture.mod.now()+3600))
                credentials.append((token, user_id))

        def read(index):
            token, expected = credentials[index % len(credentials)]
            request = urllib.request.Request(fixture.base+"/api/me", headers={"Authorization": "Bearer "+token})
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    payload = json.load(response)
                    if response.status != 200 or payload["user"]["id"] != expected:
                        return (time.perf_counter()-started)*1000, "identity_mismatch"
                return (time.perf_counter()-started)*1000, None
            except Exception as error:
                reason = getattr(error, "reason", error)
                return (time.perf_counter()-started)*1000, type(error).__name__+": "+str(reason)[:120]

        with (Path(fixture.temp.name)/"requests.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log):
            started = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
                results = list(pool.map(read, range(args.requests)))
            elapsed = time.perf_counter()-started
        latencies = sorted(row[0] for row in results)
        errors = {}
        for _, error in results:
            if error:
                errors[error] = errors.get(error, 0)+1
        report = {"scope": "local SQLite /api/me reads; not a production capacity certification",
                  "users": args.users, "requests": args.requests, "concurrency": args.workers,
                  "elapsed_seconds": round(elapsed, 2), "requests_per_second": round(args.requests/elapsed, 2),
                  "p50_ms": round(latencies[len(latencies)//2], 2),
                  "p95_ms": round(latencies[min(len(latencies)-1, int(len(latencies)*.95))], 2),
                  "errors": errors, "every_response_identity_checked": True}
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 1 if errors else 0
    finally:
        BusinessFlows.tearDownClass()


if __name__ == "__main__":
    raise SystemExit(main())
