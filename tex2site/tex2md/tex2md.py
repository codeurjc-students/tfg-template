#!/usr/bin/env python3
"""
tex2md.py — Phase 2: Convert a LaTeX thesis project to standard Markdown.

Steps:
  1. Verify dependencies (pandoc, pdf2svg, gs)
  2. Extract metadata from tfg.tex
  3. Parse document structure (chapters, appendices, inline sections)
  4. Convert images (PDF→SVG, EPS→SVG, copy raster)
  5. Pandoc pass 1: collect_labels → .labels.json
  6. Pandoc pass 2: convert each chapter to .md
  7. Post-process Markdown (standard fixes: links, tables, image figures)
  8. Save .metadata.json for the site-generation phase

Usage:
  python3 tex2site/tex2md/tex2md.py [--tex tfg.tex] [--docs web/docs]
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Allow running from any directory by locating the repo root relative to this file
SCRIPT_DIR = Path(__file__).parent    # tex2site/tex2md/
REPO_ROOT = SCRIPT_DIR.parent.parent  # repo root (default base for --tex / --docs)

# Add tex2site/ to sys.path so the `tex2md` package is importable
sys.path.insert(0, str(SCRIPT_DIR.parent))

from tex2md import metadata, structure, images, chapters

# Lua filters live next to this package
FILTERS_DIR = SCRIPT_DIR / "filters"

_GREEN = "\033[0;32m"
_RED = "\033[0;31m"
_NC = "\033[0m"


def _info(msg: str) -> None:
    print(f"{_GREEN}[tex2md]{_NC} {msg}")


def _error(msg: str) -> None:
    print(f"{_RED}[tex2md] ERROR:{_NC} {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Step 1: Verify system dependencies
# ---------------------------------------------------------------------------
def check_dependencies() -> None:
    _info("Checking dependencies...")
    missing = [cmd for cmd in ("pandoc", "pdf2svg", "gs") if not shutil.which(cmd)]
    if missing:
        _error(
            f"Missing required dependencies: {', '.join(missing)}\n"
            "  Install with:\n"
            "    sudo apt install poppler-utils ghostscript\n"
            "    # pandoc: https://pandoc.org/installing.html"
        )
    result = subprocess.run(["pandoc", "--version"], capture_output=True, text=True)
    _info(f"  pandoc: {result.stdout.splitlines()[0]}")
    _info("  pdf2svg: ok")
    gs_ver = subprocess.run(["gs", "--version"], capture_output=True, text=True).stdout.strip()
    _info(f"  gs: {gs_ver}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a LaTeX thesis project to standard Markdown."
    )
    parser.add_argument(
        "--tex",
        type=Path,
        default=REPO_ROOT / "tfg.tex",
        help="Path to the main LaTeX file (default: %(default)s)",
    )
    parser.add_argument(
        "--docs",
        type=Path,
        default=REPO_ROOT / "web" / "docs",
        help="Output directory for generated Markdown files (default: %(default)s)",
    )
    args = parser.parse_args()

    tex_main = args.tex.resolve()
    docs_dir = args.docs.resolve()
    repo_root = tex_main.parent
    bib_file = repo_root / "bibliografia.bib"
    labels_json = docs_dir / ".labels.json"
    metadata_json = docs_dir / ".metadata.json"

    check_dependencies()

    # Step 2: Extract metadata
    _info(f"Extracting metadata from {tex_main.name}...")
    meta = metadata.load(repo_root)
    _info(f"  Title:         {meta['title']}")
    _info(f"  Author:        {meta['author']}")
    _info(f"  Degree:        {meta['degree']}")
    _info(f"  Academic year: {meta['academic_year']}")

    # Step 3: Parse document structure
    _info(f"Parsing structure of {tex_main.name}...")
    struct = structure.parse(repo_root)
    chapter_map_env = struct.chapter_map_env()
    _info(f"  CHAPTER_MAP: {chapter_map_env}")

    # Step 4: Prepare output directories
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "img").mkdir(parents=True, exist_ok=True)
    (docs_dir / "appendixes").mkdir(parents=True, exist_ok=True)

    # Step 5: Convert images
    _info("Converting images...")
    images.convert_all(repo_root, docs_dir / "img")

    # Step 6: Pass 1 — collect_labels
    # Gather all chapter/appendix .tex paths so collect_labels can pre-process
    # minipage figures before Pandoc counts and records every label.
    all_chapter_tex = [
        repo_root / c.tex_file
        for c in (struct.chapters + struct.appendixes)
        if c.tex_file
    ]
    chapters.collect_labels(
        repo_root=repo_root,
        tex_main=tex_main,
        filters_dir=FILTERS_DIR,
        bib_file=bib_file,
        labels_json=labels_json,
        chapter_map_env=chapter_map_env,
        chapter_tex_files=all_chapter_tex,
    )

    # Step 7: Pass 2 — convert all chapters to Markdown
    chapters.convert_all_chapters(
        repo_root=repo_root,
        docs_dir=docs_dir,
        struct=struct,
        meta=meta,
        filters_dir=FILTERS_DIR,
        bib_file=bib_file,
        labels_json=labels_json,
    )
    labels_json.unlink(missing_ok=True)
    _info(f"  removed intermediate {labels_json.name}")

    # Step 8: Post-process generated Markdown to standard format
    # Step 8: Post-process generated Markdown to standard format.
    # Import and call process_md directly (rather than via subprocess) so that
    # the current in-memory module code is always used, avoiding stale .pyc
    # bytecode that a subprocess might pick up.
    try:
        _info("Post-processing Markdown...")
        from tex2md import process_md as _process_md
        md_files = list(docs_dir.rglob('*.md'))
        for f in md_files:
            _process_md.process_file(f, docs_dir)
    except Exception as e:
        _info(f"Markdown post-processing failed (non-fatal): {e}")

    # Step 9: Save metadata + structure for the site-generation phase
    _info(f"Saving metadata to {metadata_json.name}...")
    metadata_out = {
        "meta": meta,
        "nav_labels": struct.nav_labels(),
        "chapters": [
            {"title": c.title, "md_file": Path(c.tex_file).stem + ".md"}
            for c in struct.chapters
        ],
        "appendixes": [
            {"title": a.title, "md_file": "appendixes/" + Path(a.tex_file).stem + ".md"}
            for a in struct.appendixes
        ],
    }
    metadata_json.write_text(json.dumps(metadata_out, ensure_ascii=False, indent=2), encoding="utf-8")

    _info(f"Conversion complete. Files written to {docs_dir}/")


if __name__ == "__main__":
    main()
