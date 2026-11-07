#!/usr/bin/env python3
"""Package the owner's Dial checkout with its existing dependencies for offline use."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
GL_URL = "https://cdn.jsdelivr.net/npm/gl-matrix@3.4.3/gl-matrix-min.js"


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Chrome/130.0.0.0 Safari/537.36"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.read()
    except OSError as exc:
        raise SystemExit(f"Could not download {url}: {exc}") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "local-assets/dial-upstream")
    parser.add_argument("--output", type=Path, default=ROOT / "local-assets/dial-package")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output == source or output in source.parents or source in output.parents:
        raise SystemExit("Source and output must be separate directories.")
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True).strip():
        raise SystemExit("The upstream checkout has local changes; commit or preserve them before packaging.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dial-package-", dir=output.parent) as temp:
        stage = Path(temp) / "site"
        stage.mkdir()
        for name in ["index.html", "DIAL.avif", "DIAL.png", "DIAL_thumb.png"]:
            shutil.copy2(source / name, stage / name)
        shutil.copytree(source / "Dials", stage / "Dials")
        vendor = stage / "vendor"
        vendor.mkdir()
        html = (stage / "index.html").read_text()
        font_match = re.search(r'<link href="(https://fonts.googleapis.com/css2[^\"]+)" rel="stylesheet">', html)
        if not font_match or html.count(GL_URL) != 1:
            raise SystemExit("Upstream dependency layout changed; inspect before packaging.")
        font_url = font_match[1]
        css = download(font_url).decode()
        dependencies = {"fonts.css": font_url, "gl-matrix-min.js": GL_URL}
        for url in sorted(set(re.findall(r"url\((https://fonts.gstatic.com/[^)]+)\)", css))):
            name = hashlib.sha256(url.encode()).hexdigest()[:16] + Path(url).suffix
            (vendor / name).write_bytes(download(url))
            css = css.replace(url, name)
            dependencies[name] = url
        (vendor / "fonts.css").write_text(css)
        (vendor / "gl-matrix-min.js").write_bytes(download(GL_URL))
        # Retain upstream CSS, shaders, clock code, animation code, and image bytes.
        html = html.replace(font_match[0], '<link href="vendor/fonts.css" rel="stylesheet">')
        html = html.replace(GL_URL, "vendor/gl-matrix-min.js")
        html = re.sub(r'<link rel="preconnect"[^>]+>\n?', '', html)
        html = html.replace('</head>', '<link href="/pi-shell.css" rel="stylesheet">\n</head>')
        html = html.replace('</body>', '<script src="/pi-shell.js"></script>\n</body>')
        (stage / "index.html").write_text(html)
        # Carry redistribution notices with the vendored dependencies.
        licenses = {
            "barlow-OFL.txt": "https://raw.githubusercontent.com/google/fonts/main/ofl/barlow/OFL.txt",
            "barlowcondensed-OFL.txt": "https://raw.githubusercontent.com/google/fonts/main/ofl/barlowcondensed/OFL.txt",
            "cormorantgaramond-OFL.txt": "https://raw.githubusercontent.com/google/fonts/main/ofl/cormorantgaramond/OFL.txt",
            "roboto-OFL.txt": "https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/OFL.txt",
        }
        for name, url in licenses.items():
            (vendor / name).write_bytes(download(url))
        manifest = {
            "repository": "https://github.com/SalvSith/dial", "revision": revision,
            "upstream_index_sha256": hashlib.sha256((source / "index.html").read_bytes()).hexdigest(),
            "dependencies": dependencies,
            "files": {str(p.relative_to(stage)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(stage.rglob('*')) if p.is_file()},
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        # Only replace a previously generated package; never an arbitrary directory.
        if output.exists():
            if not (output / "manifest.json").is_file():
                raise SystemExit(f"Refusing to replace an unmanaged directory: {output}")
            shutil.rmtree(output)
        stage.rename(output)
    print(f"Packaged Dial {revision} into {output}")


if __name__ == "__main__":
    main()
