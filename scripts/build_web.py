"""Validate local asset references and create a deployable static bundle."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps/web"
DIST = ROOT / "dist/web"



# Only the public landing is self-contained. The cabinet and source CSS files
# stay byte-for-byte unchanged; the browser receives the same rules in the same
# order, without relying on separate stylesheet requests during review.
PUBLIC_CSS = ("tokens.css", "base.css", "components.css", "site.css")


def embed_public_styles():
    import base64

    css = "\n" + "\n".join(
        (WEB / "ui" / name).read_text(encoding="utf-8")
        for name in PUBLIC_CSS
    ) + "\n"
    if "</style" in css.lower():
        raise RuntimeError("A closing style tag in CSS would break inline delivery")
    digest = base64.b64encode(hashlib.sha256(css.encode("utf-8")).digest()).decode("ascii")
    csp_hash = f"'sha256-{digest}'"
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    policies = [
        header["value"]
        for block in config["headers"]
        for header in block["headers"]
        if header["key"].lower() == "content-security-policy"
    ]
    if len(policies) != 1 or csp_hash not in policies[0]:
        raise RuntimeError(
            f"Landing CSP hash does not match CSS. Add {csp_hash} to style-src in vercel.json"
        )

    # The source HTML deliberately keeps normal links for local development.
    # Only dist/web/index.html is transformed for the production deployment.
    page = DIST / "index.html"
    html = page.read_text(encoding="utf-8")
    pattern = "\n".join(
        rf'<link rel="stylesheet" href="/ui/{re.escape(name)}\?v=[^"]+">'
        for name in PUBLIC_CSS
    )
    if len(re.findall(pattern, html)) != 1:
        raise RuntimeError("Landing stylesheet links changed; refusing an unsafe build")
    html = re.sub(
        pattern,
        lambda _: '<style data-smetra-public-css="inlined">' + css + '</style>',
        html,
        count=1,
    )
    page.write_text(html, encoding="utf-8")
    print(f"Public landing CSS: {len(css.encode('utf-8'))} bytes in HTML, CSP hash verified")


PARTNER_SITE_BRANCH = "feat/partner-platform-foundation-20261026"
PARTNER_STATIC_FILES = frozenset({
    "index.html", "app.html", "docs.html",
    "partner-console.html", "partner-landing.html", "partner-docs.html",
    "partner-console.js", "partner-docs.md", "partner-sdk.js",
    "ui/partner-console.css", "ui/partner-landing.css",
    "favicon.ico", "favicon.png",
})


def build_partner_bundle():
    """Physically isolate the feature-branch partner host from consumer static pages.

    Host rewrites by themselves are insufficient: Vercel may resolve index.html
    before a conditional route. Remove the product's static files entirely.
    """
    if os.environ.get("VERCEL_GIT_COMMIT_REF") != PARTNER_SITE_BRANCH:
        raise RuntimeError("Refusing partner bundle on an unintended Git branch")
    (DIST / "index.html").write_bytes((WEB / "partner-landing.html").read_bytes())
    (DIST / "app.html").write_bytes((WEB / "partner-console.html").read_bytes())
    (DIST / "docs.html").write_bytes((WEB / "partner-docs.html").read_bytes())
    for asset in list(DIST.rglob("*")):
        if asset.is_file() and asset.relative_to(DIST).as_posix() not in PARTNER_STATIC_FILES:
            asset.unlink()
    for folder in sorted((p for p in DIST.rglob("*") if p.is_dir()), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()
    print("Partner-only build: landing at /, partner login at /app, API docs at /docs")


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
    # Start from an empty bundle so deleted sources never linger in a deploy.
    shutil.rmtree(DIST, ignore_errors=True)
    shutil.copytree(WEB, DIST)
    embed_public_styles()
    if os.environ.get("SMETRA_PARTNER_SITE") == "1":
        build_partner_bundle()
        subprocess.run(["node", str(ROOT / "scripts" / "render_partner_docs.js")], check=True, timeout=20)
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
