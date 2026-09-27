"""Validate local asset references and create a deployable static bundle."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps/web"
DIST = ROOT / "dist/web"


def build():
    for source in WEB.glob("*.js"):
        subprocess.run(["node", "--check", str(source)], check=True)
    for source in WEB.glob("*.html"):
        html = source.read_text(encoding="utf-8")
        for url in re.findall(r'(?:src|href)="(/[^"?#]+)', html):
            if (
                Path(url).suffix
                and url not in ("/favicon.ico",)
                and not (WEB / url.lstrip("/")).is_file()
            ):
                raise RuntimeError(f"Missing asset: {source.name}: {url}")
    DIST.mkdir(parents=True, exist_ok=True)
    shutil.copytree(WEB, DIST, dirs_exist_ok=True)
    manifest = {
        str(p.relative_to(DIST)).replace("\\", "/"): hashlib.sha256(
            p.read_bytes()
        ).hexdigest()
        for p in sorted(DIST.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    }
    (DIST / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Web build PASS: {len(manifest)} files in {DIST}")


if __name__ == "__main__":
    build()
