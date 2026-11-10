"""Disposable, loopback-only real API server for protected-estimate browser tests."""
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT))
    from scripts.fixture_network import restrict_to_loopback
    restrict_to_loopback()
    if any(os.getenv(name) for name in ("DATABASE_URL", "RUNTIME_DATABASE_URL", "VERCEL")):
        raise RuntimeError("This fixture requires a disposable local SQLite database")
    os.environ["ALLOW_UNVERIFIED_SIGNUP"] = "1"
    from tests.test_protected_estimates import ProtectedEstimateTests
    ProtectedEstimateTests.setUpClass()
    fixture = ProtectedEstimateTests()
    fixture.mod.ORIGIN = fixture.base
    fixture.mod.BROWSER_ORIGINS = frozenset((fixture.base,))
    fixture.setUp()
    link, token = fixture.link()
    data = {
        "base": fixture.base, "quote": fixture.quote,
        "owner": {"token": fixture.owner, "id": fixture.owner_id,
                  "email": fixture.recipient_email.replace("-client@", "@")},
        "recipient": {"token": fixture.recipient, "id": fixture.recipient_id, "email": fixture.recipient_email},
        "link": link, "url": fixture.base + "/protected-estimate#" + token,
    }
    (ROOT / "data/protected-estimates-fixture.json").write_text(json.dumps(data), encoding="utf-8")
    print("PROTECTED_ESTIMATES_FIXTURE_READY " + fixture.base, flush=True)
    try:
        threading.Event().wait()
    finally:
        fixture.tearDownClass()


if __name__ == "__main__":
    main()
