import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / ".env"
if source.exists():
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def run():
    # Direct execution (`python backend/launcher.py`) puts backend/ rather than
    # the repository root on sys.path. Keep imports identical to Vercel and tests.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from backend.app import main

    main()


if __name__ == "__main__":
    run()
