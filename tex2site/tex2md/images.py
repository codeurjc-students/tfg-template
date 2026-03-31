"""Convert source images to web-compatible formats.

Converts PDF → SVG (via pdf2svg) and EPS → SVG (via gs + pdf2svg).
Copies raster images (PNG, JPG, GIF) and SVG directly.

Why SVG for vector graphics?
LaTeX figures are typically included as PDF or EPS (vector formats that
print at any resolution). Browsers cannot display PDF in <img> tags, and
EPS is not a web format at all. SVG is the only vector format that renders
natively in all modern browsers, so we convert both PDF and EPS to SVG to
preserve crispness at any screen size without rasterisation artefacts.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

_RASTER_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".svg"}


def _log(msg: str) -> None:
    print(f"\033[0;32m[convert]\033[0m   {msg}")


def _warn(msg: str) -> None:
    print(f"\033[1;33m[convert]\033[0m   {msg}")


def convert_file(src: Path, dst_dir: Path) -> None:
    """Convert or copy a single image file into dst_dir."""
    suffix = src.suffix.lower()
    dst_dir.mkdir(parents=True, exist_ok=True)

    if suffix == ".pdf":
        # Browsers cannot display PDF in <img> tags. pdf2svg converts a
        # single-page PDF to SVG, preserving all vector paths and text.
        # ':1' selects only the first page (thesis figures are always 1-page).
        dst = dst_dir / (src.stem + ".svg")
        _log(f"PDF → SVG: {src}")
        subprocess.run(["pdf2svg", str(src), str(dst), "1"], check=True)

    elif suffix == ".eps":
        # EPS is a legacy PostScript vector format common in older LaTeX
        # workflows and some drawing tools (e.g. Inkscape exports). pdf2svg
        # only accepts PDF input, so conversion requires two steps:
        #   1. EPS → PDF via GhostScript (-sDEVICE=pdfwrite)
        #   2. PDF → SVG via pdf2svg
        # The intermediate PDF is written to a temp file and deleted after.
        _log(f"EPS → PDF → SVG: {src}")
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_pdf = Path(tmp.name)
        try:
            subprocess.run(
                ["gs", "-q", "-dBATCH", "-dNOPAUSE", "-dSAFER",
                 "-sDEVICE=pdfwrite", f"-sOutputFile={tmp_pdf}", str(src)],
                check=True,
            )
            dst = dst_dir / (src.stem + ".svg")
            subprocess.run(["pdf2svg", str(tmp_pdf), str(dst), "1"], check=True)
        finally:
            tmp_pdf.unlink(missing_ok=True)

    elif suffix in _RASTER_SUFFIXES:
        _log(f"Copying: {src}")
        shutil.copy2(src, dst_dir / src.name)

    else:
        _warn(f"Unrecognised format, copying as-is: {src}")
        shutil.copy2(src, dst_dir / src.name)


def convert_directory(src_dir: Path, dst_dir: Path) -> None:
    """Convert all images in src_dir into dst_dir."""
    if not src_dir.is_dir():
        return
    for f in sorted(src_dir.iterdir()):
        if f.is_file():
            convert_file(f, dst_dir)


def convert_all(repo_root: Path, docs_img_dir: Path) -> None:
    """Convert all images from img/, config/logos/, and config/cc/.

    img/          — thesis figures and diagrams referenced in chapter content.
    config/logos/ — university logo used by the MkDocs template on the cover
                    page and in the header (main.html).
    config/cc/    — Creative Commons licence icons used in the footer of the
                    MkDocs template to display the thesis licence.

    All three directories are flattened into web/docs/img/ so that the
    Jinja2 template and Markdown pages can reference any image with a single
    consistent path prefix, regardless of where the source file lives.
    """
    docs_img_dir.mkdir(parents=True, exist_ok=True)

    convert_directory(repo_root / "img", docs_img_dir)
    convert_directory(repo_root / "config" / "logos", docs_img_dir)
    convert_directory(repo_root / "config" / "cc", docs_img_dir)
