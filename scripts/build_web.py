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

STYLESHEET_MARKER = '<link rel="stylesheet" href="'


def bundle_app_stylesheets(html, source_dir, output_dir):
    """Bundle the cabinet's ordered CSS cascade to remove many blocking requests."""
    links = []
    offset = 0
    while True:
        start = html.find(STYLESHEET_MARKER, offset)
        if start < 0:
            break
        href_start = start + len(STYLESHEET_MARKER)
        href_end = html.find('"', href_start)
        tag_end = html.find(">", href_end)
        if href_end < 0 or tag_end < 0:
            break
        href = html[href_start:href_end]
        if href.startswith("/") and href.endswith(".css") and not href.startswith("//"):
            links.append((start, tag_end + 1, href))
        offset = tag_end + 1
    if len(links) < 2:
        return html

    newline = chr(10)
    chunks = []
    for _, _, href in links:
        source = source_dir / href.lstrip("/")
        if not source.is_file():
            raise RuntimeError(f"Missing stylesheet for bundle: {href}")
        chunks.append(f"/* {source.name} */{newline}{source.read_text(encoding='utf-8')}")

    bundle = (newline * 2).join(chunks).rstrip() + newline
    digest = hashlib.sha256(bundle.encode("utf-8")).hexdigest()[:16]
    name = f"app.bundle.{digest}.css"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / name
    target.write_text(bundle, encoding="utf-8")
    for stale in output_dir.glob("app.bundle.*.css"):
        if stale != target:
            stale.unlink()

    replacement = f'<link rel="stylesheet" href="/{name}">'
    rendered = []
    cursor = 0
    for index, (start, finish, _) in enumerate(links):
        rendered.append(html[cursor:start])
        if index == 0:
            rendered.append(replacement)
        cursor = finish
    rendered.append(html[cursor:])
    return "".join(rendered)


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
