"""Extract metadata from LaTeX source files."""

import re
from pathlib import Path


def _extract_macro(tex: str, macro: str) -> str:
    """Return the value of \\newcommand{\\macro}{VALUE} or \\renewcommand{...}.

    Handles both \\newcommand and \\renewcommand because some macros (e.g.
    \\titulotrabajo) are first declared in the document class and then
    redefined by the student in tfg.tex. Using \\newcommand alone would
    silently miss those redefinitions and return an empty string.
    """
    pattern = rf'\\(?:new|renew)command\{{\\{re.escape(macro)}\}}\{{([^}}]+)\}}'
    m = re.search(pattern, tex)
    return m.group(1).strip() if m else ""


def _extract_named_command(tex: str, command_name: str) -> str:
    """Return the value of \\newcommand{\\commandname}{VALUE}.

    Uses only \\newcommand (not \\renewcommand) because the institutional
    variables in config.tex (\\universidad, \\escuelalargo) are always fresh
    declarations, not overrides of a definition from the document class.
    """
    pattern = rf'\\newcommand\{{\\{re.escape(command_name)}\}}\{{([^}}]+)\}}'
    m = re.search(pattern, tex)
    return m.group(1).strip() if m else ""


def load(repo_root: Path) -> dict:
    """Return a dict with all TFG metadata extracted from tfg.tex and config/config.tex."""
    tex_main = (repo_root / "tfg.tex").read_text(encoding="utf-8")
    config_tex_path = repo_root / "config" / "config.tex"
    config_tex = config_tex_path.read_text(encoding="utf-8") if config_tex_path.exists() else ""

    title = _extract_macro(tex_main, "titulotrabajo")
    author = _extract_macro(tex_main, "nombreautor")
    tutor = _extract_macro(tex_main, "nombretutor")
    degree = _extract_macro(tex_main, "grado")
    academic_year = _extract_macro(tex_main, "curso")
    university = _extract_named_command(config_tex, "universidad")
    school = _extract_named_command(config_tex, "escuelalargo")

    # Extract the last 4-digit year from the academic-year string.
    # e.g. "Curso 2024-2025" → "2025"
    # The MkDocs template uses 'year' as a standalone integer (e.g. footer
    # copyright), while 'academic_year' carries the full display string.
    years = re.findall(r'\d{4}', academic_year)
    year = years[-1] if years else "2025"

    return {
        "title": title,
        "author": author,
        "tutor": tutor,
        "degree": degree,
        "academic_year": academic_year,
        # Fallback values for university and school guard against config.tex
        # being absent (e.g. a minimal test fixture or a fresh project that
        # hasn't customised config.tex yet). Title, author, and other
        # student-specific fields have no fallback intentionally: a missing
        # value there would produce an obviously broken cover page, making
        # the oversight easy to catch early.
        "university": university or "Universidad Rey Juan Carlos",
        "school": school or "ETSII",
        "year": year,
    }
