from __future__ import annotations

import base64
import math
import re
import shutil
import zipfile
from pathlib import Path

from weasyprint import HTML

REPO = Path.cwd()
BUILD = REPO / ".campaign-repair"
SITE = BUILD / "site"
ARCHIVE = BUILD / "campaign.zip"

DOCUMENT_PDFS = {
    "resume.html": "docs/Russell-Dudek-GoDaddy-Resume.pdf",
    "cover-letter.html": "docs/Russell-Dudek-GoDaddy-Cover-Letter.pdf",
    "interview-brief.html": "docs/Russell-Dudek-GoDaddy-Interview-Thesis-Brief.pdf",
    "120-day-plan.html": "docs/Russell-Dudek-GoDaddy-First-120-Days.pdf",
    "hard-objection.html": "docs/Russell-Dudek-GoDaddy-Hard-Objection-Analysis.pdf",
    "outcome-resolver.html": "docs/Russell-Dudek-GoDaddy-Entrepreneur-Outcome-Resolver.pdf",
    "executive-questions.html": "docs/Russell-Dudek-GoDaddy-Executive-Interview-Questions.pdf",
}

PUBLIC_FILES = {
    "index.html",
    "styles.css",
    "brand-tokens.css",
    "contrast-overrides.css",
    "app.js",
    "resume.html",
    "cover-letter.html",
    "interview-brief.html",
    "120-day-plan.html",
    "hard-objection.html",
    "outcome-resolver.html",
    "executive-questions.html",
    "README.md",
    "brand-intelligence.md",
    "source-notes.md",
    "campaign-audit.md",
    ".nojekyll",
}


def reconstruct_source() -> None:
    chunks = sorted((REPO / ".publish").glob("source-*"))
    if len(chunks) != 5:
        raise RuntimeError(f"Expected five source chunks; found {len(chunks)}")
    encoded = "".join(path.read_text(encoding="utf-8").strip() for path in chunks)
    payload = base64.b64decode(encoded)
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE.write_bytes(payload)
    SITE.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARCHIVE) as source_zip:
        source_zip.extractall(SITE)


def repair_styles() -> None:
    styles_path = SITE / "styles.css"
    override_path = REPO / "contrast-overrides.css"
    styles = styles_path.read_text(encoding="utf-8")
    marker = "/* 2026-07-15 visual integrity system */"
    if marker in styles:
        styles = styles.split(marker, 1)[0].rstrip()
    override = override_path.read_text(encoding="utf-8").strip()
    styles_path.write_text(f"{styles}\n\n{override}\n", encoding="utf-8")
    shutil.copy2(override_path, SITE / "contrast-overrides.css")


def repair_homepage() -> None:
    path = SITE / "index.html"
    html = path.read_text(encoding="utf-8")
    html = html.replace(' style="color:#bfe9e4"', "")
    html = html.replace(' style="color:#dff7ee"', "")
    path.write_text(html, encoding="utf-8")


def repair_document_links() -> None:
    for route, pdf_path in DOCUMENT_PDFS.items():
        path = SITE / route
        html = path.read_text(encoding="utf-8")
        if pdf_path not in html:
            link = f'<a href="{pdf_path}" download>Download PDF</a>'
            html = html.replace('<div class="doc-actions">', f'<div class="doc-actions">{link}', 1)
        html = html.replace(
            '<button onclick="window.print()">Print / Save PDF</button>',
            '<button class="light" onclick="window.print()">Print</button>',
        )
        path.write_text(html, encoding="utf-8")


def regenerate_pdfs() -> None:
    for route, pdf_path in DOCUMENT_PDFS.items():
        output = SITE / pdf_path
        output.parent.mkdir(parents=True, exist_ok=True)
        HTML(filename=str(SITE / route), base_url=str(SITE)).write_pdf(str(output))
        if not output.exists() or output.stat().st_size < 1_000:
            raise RuntimeError(f"Failed to generate {output}")


def publish_direct_files() -> None:
    for name in PUBLIC_FILES:
        source = SITE / name
        if source.exists():
            target = REPO / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    for directory in ("assets", "docs", "research"):
        source_dir = SITE / directory
        target_dir = REPO / directory
        if target_dir.exists():
            shutil.rmtree(target_dir)
        if source_dir.exists():
            shutil.copytree(source_dir, target_dir)


def rebuild_source_chunks() -> None:
    if ARCHIVE.exists():
        ARCHIVE.unlink()
    excluded_parts = {".github", ".campaign-repair", ".publish"}
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output_zip:
        for path in sorted(SITE.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(SITE)
            if relative.parts and relative.parts[0] in excluded_parts:
                continue
            output_zip.write(path, relative.as_posix())

    encoded = base64.b64encode(ARCHIVE.read_bytes()).decode("ascii")
    size = math.ceil(len(encoded) / 5)
    publish_dir = REPO / ".publish"
    publish_dir.mkdir(exist_ok=True)
    for index in range(5):
        chunk = encoded[index * size : (index + 1) * size]
        (publish_dir / f"source-{index:02d}").write_text(chunk, encoding="utf-8")


def verify() -> None:
    required = [REPO / "index.html", REPO / "styles.css", REPO / "brand-tokens.css"]
    required.extend(REPO / path for path in DOCUMENT_PDFS.values())
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing published files: {missing}")

    home = (REPO / "index.html").read_text(encoding="utf-8")
    if "Resolving the campaign." in home or "JSZip" in home:
        raise RuntimeError("Loader shell remains in the published homepage")

    styles = (REPO / "styles.css").read_text(encoding="utf-8")
    for token in ("--ui-resolver-row", ".dark .contract-field", ".teal .evidence p"):
        if token not in styles:
            raise RuntimeError(f"Missing visual integrity rule: {token}")

    for route, pdf_path in DOCUMENT_PDFS.items():
        html = (REPO / route).read_text(encoding="utf-8")
        if pdf_path not in html:
            raise RuntimeError(f"Missing PDF link in {route}")


def main() -> None:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    reconstruct_source()
    repair_styles()
    repair_homepage()
    repair_document_links()
    regenerate_pdfs()
    publish_direct_files()
    rebuild_source_chunks()
    verify()
    print("Campaign source, visual system, and PDFs rebuilt successfully.")


if __name__ == "__main__":
    main()
