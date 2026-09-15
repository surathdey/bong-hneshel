#!/usr/bin/env python3
"""
build_docs.py — Convert Markdown ops docs into polished PDFs.

Renders every `.md` file under /app/docs/ops/ into a matching `.pdf`
under /app/docs/ops/pdf/. Adds a Suparna Dey title header, a footer with
page numbers, and readable typography.

Usage:
    python scripts/build_docs.py                # build all
    python scripts/build_docs.py --file NAME.md # build one

Deps (already installed on the container):
    - markdown          → md → HTML (with fenced_code + tables extensions)
    - weasyprint        → HTML → PDF (respects CSS @page for headers/footers)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import markdown as md
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR  = REPO_ROOT / "docs" / "ops"
PDF_DIR   = DOCS_DIR / "pdf"

# ─── Styling ────────────────────────────────────────────────────────────
# Kept in this file so ops can tweak fonts / colors without touching CSS
# files. Aim: clean, print-friendly, brand-neutral (this doc travels
# between different tenants so we avoid tenant-specific colors).
CSS_TEMPLATE = """
@page {
    size: Letter;
    margin: 0.85in 0.75in 1in 0.75in;

    @top-left {
        content: "Suparna Dey Platform";
        font-family: "Helvetica", "Arial", sans-serif;
        font-size: 9pt;
        color: #6b7280;
    }
    @top-right {
        content: string(doctitle);
        font-family: "Helvetica", "Arial", sans-serif;
        font-size: 9pt;
        color: #6b7280;
    }
    @bottom-center {
        content: "Page " counter(page) " of " counter(pages);
        font-family: "Helvetica", "Arial", sans-serif;
        font-size: 9pt;
        color: #6b7280;
    }
    @bottom-right {
        content: "%GENERATED_AT%";
        font-family: "Helvetica", "Arial", sans-serif;
        font-size: 8pt;
        color: #9ca3af;
    }
}

body {
    font-family: "Helvetica", "Arial", sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #1f2937;
}

h1 {
    string-set: doctitle content();
    font-size: 22pt;
    color: #8F3E29;
    border-bottom: 3px solid #B14F36;
    padding-bottom: 8px;
    margin-top: 0;
    page-break-before: auto;
}
h2 {
    font-size: 15pt;
    color: #2F4F4F;
    margin-top: 26px;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 4px;
}
h3 {
    font-size: 12.5pt;
    color: #374151;
    margin-top: 20px;
}
h4 { font-size: 11pt; color: #374151; }

p, li { orphans: 3; widows: 3; }

blockquote {
    background: #FFF7E6;
    border-left: 4px solid #E2A323;
    padding: 10px 14px;
    color: #7C4A03;
    margin: 12px 0;
    border-radius: 3px;
}

code {
    background: #f3f4f6;
    padding: 1px 5px;
    border-radius: 3px;
    font-family: "Menlo", "Consolas", monospace;
    font-size: 9.5pt;
    color: #B14F36;
}
pre {
    background: #1f2937;
    color: #f9fafb;
    padding: 12px 14px;
    border-radius: 5px;
    /* DejaVu Sans Mono has full Unicode box-drawing coverage; Menlo/Consolas
       do NOT. Order matters — the first font Wesayprint can find wins. */
    font-family: "DejaVu Sans Mono", "Liberation Mono", "Menlo", "Consolas", monospace;
    font-size: 8pt;
    line-height: 1.35;
    page-break-inside: avoid;
    /* Strict pre = no wrapping. Preserves ASCII diagrams intact.
       Long one-liners must be manually split in the source. */
    white-space: pre;
}
pre code {
    background: transparent;
    color: inherit;
    padding: 0;
    font-family: inherit;
}
pre code { background: transparent; color: inherit; padding: 0; }

table {
    border-collapse: collapse;
    width: 100%;
    margin: 14px 0;
    page-break-inside: avoid;
}
th, td {
    border: 1px solid #e5e7eb;
    padding: 7px 10px;
    text-align: left;
    vertical-align: top;
    font-size: 10pt;
}
th {
    background: #f9fafb;
    font-weight: 700;
    color: #111827;
}

hr {
    border: none;
    border-top: 1px solid #e5e7eb;
    margin: 26px 0;
}

a { color: #B14F36; text-decoration: none; }
a:hover { text-decoration: underline; }

ul, ol { padding-left: 22px; }

/* Compact checklists */
li input[type="checkbox"] { margin-right: 6px; }
"""


def _render_html(md_text: str, title: str) -> str:
    """Convert Markdown to a full HTML document ready for WeasyPrint."""
    body_html = md.markdown(
        md_text,
        extensions=[
            "fenced_code",
            "tables",
            "sane_lists",
            "toc",
        ],
    )
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body>{body_html}</body>
</html>"""


def build_one(md_path: Path, out_dir: Path) -> Path:
    if not md_path.exists():
        raise FileNotFoundError(md_path)
    md_text = md_path.read_text(encoding="utf-8")

    # First H1 in the doc becomes the browser tab title (and the page-header
    # string via CSS string-set).
    title = md_path.stem.replace("_", " ").title()
    for line in md_text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            title = s[2:].strip()
            break

    html_str = _render_html(md_text, title)

    stamp = datetime.utcnow().strftime("%Y-%m-%d")
    css_str = CSS_TEMPLATE.replace("%GENERATED_AT%", f"Generated {stamp}")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_pdf = out_dir / (md_path.stem + ".pdf")

    font_config = FontConfiguration()
    HTML(string=html_str, base_url=str(md_path.parent)).write_pdf(
        target=str(out_pdf),
        stylesheets=[CSS(string=css_str, font_config=font_config)],
        font_config=font_config,
    )
    return out_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description="Render ops Markdown docs to PDF.")
    parser.add_argument("--file", help="Build a single .md file (relative to docs/ops).")
    args = parser.parse_args()

    if args.file:
        md_files = [DOCS_DIR / args.file]
    else:
        # Skip the folder README — it's meta-doc for humans browsing the
        # repo, not a client-facing PDF deliverable.
        md_files = sorted(p for p in DOCS_DIR.glob("*.md") if p.name.lower() != "readme.md")

    if not md_files:
        print(f"No markdown files found in {DOCS_DIR}")
        return 1

    print(f"Rendering {len(md_files)} doc(s) → {PDF_DIR}\n")
    for md_path in md_files:
        try:
            out = build_one(md_path, PDF_DIR)
            size_kb = out.stat().st_size / 1024
            print(f"  ✓ {md_path.name:40s} → {out.relative_to(REPO_ROOT)} ({size_kb:.1f} KB)")
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {md_path.name} FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
