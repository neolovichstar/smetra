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

STYLESHEET_LINK = re.compile(r'<link\\s+rel=["\\']stylesheet["\\']\\s+href=["\\'](/[^"\\']+\\.css)["\\']\\s*/?>')


def bundle_app_stylesheets(html, source_dir, output_dir):
    """Bundle the cabinet's ordered CSS cascade to remove many blocking requests."""
    links = list(STYLESHEET_LINK.finditer(html))
    if len(links) < 2:
        return html

    chunks = []
    for match in links:
        href = match.group(1)
        source = source_dir / href.lstrip("/")
        if not source.is_file():
            raise RuntimeError(f"Missing stylesheet for bundle: {href}")
        chunks.append(f"/* {source.name} */\\n{source.read_text(encoding='utf-8')}")

    bundle = "\\n\\n".join(chunks).rstrip() + "\\n"
    digest = hashlib.sha256(bundle.encode("utf-8")).hexdigest()[:16]
    name = f"app.bundle.{digest}.css"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / name
    target.write_text(bundle, encoding="utf-8")
    for stale in output_dir.glob("app.bundle.*.css"):
        if stale != target:
            stale.unlink()

    replacement = f'<link rel="stylesheet" href="/{name}">'
    inserted = False

    def replace_link(_match):
        nonlocal inserted
        if inserted:
            return ""
        inserted = True
        return replacement

    rendered = STYLESHEET_LINK.sub(replace_link, html)
    if not inserted:
        raise RuntimeError("Could not attach cabinet stylesheet bundle")
    return rendered


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
    app_html = DIST / "app.html"
    app_html.write_text(
        bundle_app_stylesheets(app_html.read_text(encoding="utf-8"), WEB, DIST),
        encoding="utf-8",
    )
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
