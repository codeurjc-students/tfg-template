"""Run pandoc passes to convert LaTeX chapters to Markdown.

Pass 1 (collect_labels): runs pandoc over the full document to populate
    .labels.json via the collect_labels.lua Lua filter.

Pass 2 (per chapter): converts each chapter .tex file to .md, applying
    cleanup.lua and resolve_refs.lua filters, then post-processes the
    Markdown (image paths, heading shift, front-matter).
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .structure import DocStructure, InlineSection, Chapter

_GREEN = "\033[0;32m"
_YELLOW = "\033[1;33m"
_NC = "\033[0m"


def _info(msg: str) -> None:
    print(f"{_GREEN}[convert]{_NC} {msg}")


def _warn(msg: str) -> None:
    print(f"{_YELLOW}[convert]{_NC} {msg}")


# ---------------------------------------------------------------------------
# LaTeX pre-processing
# ---------------------------------------------------------------------------

def _split_minipage_figures(tex: str) -> str:
    """Split \\begin{figure} environments that use \\begin{minipage} for
    side-by-side images into separate \\begin{figure} environments, one
    per minipage.

    Pandoc's LaTeX reader collapses all minipages inside a \\begin{figure}
    into a single Figure AST node and keeps only the *last* \\caption and
    \\label.  Pre-splitting the LaTeX ensures every subfigure gets its own
    anchor, caption, and cross-reference target before Pandoc ever sees it.
    """

    def _find_env_end(text: str, start: int, env: str) -> int:
        """Return the index just after \\end{env} that closes the \\begin{env}
        whose body starts at *start*.  Returns -1 on malformed input."""
        begin_re = re.compile(r'\\begin\{' + re.escape(env) + r'\}')
        end_re   = re.compile(r'\\end\{'   + re.escape(env) + r'\}')
        depth, pos = 1, start
        while pos < len(text) and depth > 0:
            b = begin_re.search(text, pos)
            e = end_re.search(text, pos)
            if e is None:
                return -1
            if b and b.start() < e.start():
                depth += 1
                pos = b.end()
            else:
                depth -= 1
                pos = e.end()
        return pos if depth == 0 else -1

    fig_begin_re = re.compile(r'\\begin\{figure\}(\[[^\]]*\])?')
    result: list[str] = []
    cursor = 0

    for fm in fig_begin_re.finditer(tex):
        if fm.start() < cursor:
            continue  # already consumed by a previous replacement

        fig_opts   = fm.group(1) or ''
        body_start = fm.end()
        fig_end    = _find_env_end(tex, body_start, 'figure')
        if fig_end == -1:
            continue

        # body = content between \begin{figure}[opts] and \end{figure}
        body = tex[body_start : fig_end - len('\\end{figure}')]

        # Collect every minipage inside this figure
        mp_re = re.compile(r'\\begin\{minipage\}(\{[^}]*\})?')
        minipages: list[dict] = []
        for mm in mp_re.finditer(body):
            mp_width      = (mm.group(1) or r'{\linewidth}').strip('{}')
            mp_body_start = mm.end()
            mp_end        = _find_env_end(body, mp_body_start, 'minipage')
            if mp_end == -1:
                break
            mp_body = body[mp_body_start : mp_end - len('\\end{minipage}')]

            # Extract \caption{...} — handles one level of nested braces
            cap_m = re.search(r'\\caption\{((?:[^{}]|\{[^{}]*\})*)\}', mp_body)
            # Extract \label{...}
            lab_m = re.search(r'\\label\{([^}]+)\}', mp_body)
            # Extract \includegraphics[opts]{path}
            img_m = re.search(r'\\includegraphics(\[[^\]]*\])?\{([^}]+)\}', mp_body)

            if img_m:
                img_opts = img_m.group(1) or ''
                img_path = img_m.group(2)
                # Replace width=\linewidth inside includegraphics options with
                # the actual minipage width so Pandoc emits a meaningful
                # width attribute on the generated <figure> element.
                if img_opts:
                    mp_width_repl = mp_width  # closure for lambda below
                    img_opts = re.sub(
                        r'width=\\+(?:linewidth|textwidth)',
                        lambda _: f'width={mp_width_repl}',
                        img_opts,
                    )
                else:
                    img_opts = f'[width={mp_width}]'

                minipages.append({
                    'caption':  cap_m.group(1) if cap_m else '',
                    'label':    lab_m.group(1) if lab_m else '',
                    'img_path': img_path,
                    'img_opts': img_opts,
                })

        if len(minipages) >= 2:
            result.append(tex[cursor : fm.start()])
            for mp in minipages:
                lines = [
                    f'\\begin{{figure}}{fig_opts}',
                    '\\centering',
                    f'\\includegraphics{mp["img_opts"]}{{{mp["img_path"]}}}',
                ]
                if mp['caption']:
                    lines.append(f'\\caption{{{mp["caption"]}}}')
                if mp['label']:
                    lines.append(f'\\label{{{mp["label"]}}}')
                lines.append('\\end{figure}')
                result.append('\n'.join(lines) + '\n')
            cursor = fig_end

    result.append(tex[cursor:])
    return ''.join(result)


# ---------------------------------------------------------------------------
# Post-processing helpers
# ---------------------------------------------------------------------------

# Pandoc resolves image paths relative to the .tex source file, producing
# variants like '../img/foo.pdf', 'img/bar.png', or 'src="../img/baz.eps"'.
# The website needs consistent /img/ absolute paths so links work at any
# URL depth (top-level chapters, appendixes subdirectory, etc.).
# PDF and EPS references must also be rewritten to .svg because images.py
# already converted those formats in Phase 2 — the originals don't exist
# on the web server.
_IMG_SUBS = [
    # PDF/EPS references in Markdown links → /img/*.svg
    (re.compile(r'\]\(\.\./img/([^)]*)\.(pdf|eps)\)'), r'](/img/\1.svg)'),
    (re.compile(r'\]\(img/([^)]*)\.(pdf|eps)\)'), r'](/img/\1.svg)'),
    (re.compile(r'\]\(config/logos/([^)]*)\.(pdf|eps)\)'), r'](/img/\1.svg)'),
    # Relative img/ references → /img/
    (re.compile(r'\]\(\.\./img/'), r'](/img/'),
    (re.compile(r'\]\(img/'), r'](/img/'),
    # Raw HTML src= attributes
    (re.compile(r'src="\.\./img/'), r'src="/img/'),
    (re.compile(r'src="img/'), r'src="/img/'),
    # Unescape pandoc-escaped quotes
    (re.compile(r'\\"'), '"'),
]

_HEADING_RE = re.compile(r'^(#+) ', re.MULTILINE)


def _postprocess(md: str) -> str:
    """Apply image path fixes, unescape quotes, and shift headings down one level."""
    for pattern, replacement in _IMG_SUBS:
        md = pattern.sub(replacement, md)

    # LaTeX compactitem (from the paralist/beamer packages) is a compact
    # bullet list used in thesis templates for 'Palabras clave' (keywords).
    # Pandoc emits it as a raw <div class="compactitem"> with one keyword per
    # line because there is no Markdown equivalent for compactitem. Joining
    # the items with commas produces readable inline text in the abstract.
    compact_re = re.compile(r'<div class="compactitem">\s*(.*?)\s*</div>', re.S)
    def _compact_to_commas(m: re.Match) -> str:
        inner = m.group(1)
        # split into lines, strip, filter empties
        parts = [line.strip() for line in inner.splitlines() if line.strip()]
        return ', '.join(parts)
    md = compact_re.sub(_compact_to_commas, md)

    # Shift all headings down one level (# → ##, ## → ###, …).
    # _write_chapter_md() injects a top-level '# Title' heading for every
    # chapter. If the chapter body also starts at H1 (as Pandoc emits from
    # \chapter{} or from \section at depth 1), the page ends up with multiple
    # H1 elements, breaking accessibility and browser-tab structure. Shifting
    # ensures chapter content always starts at H2 so the injected title is
    # the only H1 on each page.
    md = _HEADING_RE.sub(lambda m: '#' + m.group(1) + ' ', md)
    return md


# ---------------------------------------------------------------------------
# Pass 1 — collect_labels
# ---------------------------------------------------------------------------

def collect_labels(
    repo_root: Path,
    tex_main: Path,
    filters_dir: Path,
    bib_file: Path,
    labels_json: Path,
    chapter_map_env: str,
    chapter_tex_files: Optional[list] = None,
) -> None:
    """Run pandoc over the FULL document to generate .labels.json.

    The full-document pass is required because label numbers depend on
    global counters that span all chapters. For example, the label
    'fig:diagrama' resolves to 'Fig. 3.2' only after pandoc has counted
    every figure in chapters 1 and 2. Running pandoc per-chapter would
    reset counters at each chapter boundary, producing wrong numbering
    (every chapter would start at Fig. 1.1).

    If *chapter_tex_files* is provided, each chapter .tex file is
    pre-processed with _split_minipage_figures() before Pandoc sees it.
    This ensures that minipage-based sub-figures are counted and labelled
    individually so their \\ref{} cross-references resolve correctly.
    """
    _info("Pass 1: collecting labels (\\ref{})...")

    env = {**os.environ, "CHAPTER_MAP": chapter_map_env, "LABELS_JSON": str(labels_json)}

    # -----------------------------------------------------------------
    # Pre-processing: create preprocessed copies of chapter .tex files
    # so that each minipage subfigure gets its own label in the AST.
    # -----------------------------------------------------------------
    tmp_files: list[Path] = []
    pandoc_tex_main = tex_main  # may be replaced with a preprocessed copy

    if chapter_tex_files:
        # Map original relative path (as it appears in \input{}) → preprocessed path
        path_replacements: dict[str, str] = {}

        for chapter_tex in chapter_tex_files:
            try:
                content = chapter_tex.read_text(encoding="utf-8")
            except OSError:
                continue
            preprocessed = _split_minipage_figures(content)
            if preprocessed == content:
                continue  # no minipages to fix in this chapter

            tmp_path = chapter_tex.with_suffix("._pp.tex")
            tmp_path.write_text(preprocessed, encoding="utf-8")
            tmp_files.append(tmp_path)

            # Build the substitution key: relative to repo_root, both with
            # and without the .tex extension (LaTeX allows omitting it).
            try:
                rel = chapter_tex.relative_to(repo_root)
            except ValueError:
                rel = chapter_tex
            rel_str = str(rel).replace("\\", "/")
            rel_no_ext = rel_str[:-4] if rel_str.endswith(".tex") else rel_str

            tmp_rel = str(tmp_path.relative_to(repo_root)).replace("\\", "/")
            tmp_no_ext = tmp_rel[:-4] if tmp_rel.endswith(".tex") else tmp_rel

            path_replacements[rel_str]    = tmp_rel
            path_replacements[rel_no_ext] = tmp_no_ext

        if path_replacements:
            main_content = tex_main.read_text(encoding="utf-8")
            for orig, replacement in path_replacements.items():
                main_content = main_content.replace(
                    f"\\input{{{orig}}}", f"\\input{{{replacement}}}"
                )
            tmp_main = tex_main.with_suffix("._pp.tex")
            tmp_main.write_text(main_content, encoding="utf-8")
            tmp_files.append(tmp_main)
            pandoc_tex_main = tmp_main

    try:
        result = subprocess.run(
            [
                "pandoc", str(pandoc_tex_main),
                "--from=latex",
                "--to=markdown",
                f"--lua-filter={filters_dir / 'collect_labels.lua'}",
                f"--bibliography={bib_file}",
                "--citeproc",
                "--wrap=none",
                "--output=/dev/null",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=repo_root,
        )
    finally:
        for tmp in tmp_files:
            tmp.unlink(missing_ok=True)

    # Show any non-empty stderr lines as warnings
    for line in result.stderr.splitlines():
        if line.strip():
            _warn(f"  pandoc: {line}")

    if not labels_json.exists():
        _warn(".labels.json was not generated. \\ref{} references will not be resolved.")
        labels_json.write_text("{}", encoding="utf-8")


# ---------------------------------------------------------------------------
# Pass 2 — per-chapter conversion
# ---------------------------------------------------------------------------

def _run_pandoc_chapter(
    tex_in: Path,
    filters_dir: Path,
    bib_file: Path,
    labels_json: Path,
    current_doc_file: str,
    repo_root: Path,
) -> Optional[str]:
    """Run pandoc on a single chapter .tex and return the Markdown body, or None on error."""
    env = {
        **os.environ,
        "LABELS_JSON": str(labels_json),
        "CURRENT_DOC_FILE": current_doc_file,
    }

    # Pre-process: split minipage multi-figure constructs so every subfigure
    # gets its own caption and anchor in the output.
    original_content = tex_in.read_text(encoding="utf-8")
    preprocessed = _split_minipage_figures(original_content)
    if preprocessed != original_content:
        # Write the preprocessed content to a sibling temp file so that
        # relative \includegraphics paths stay valid (Pandoc resolves them
        # relative to the input file's directory).
        tmp_tex = tex_in.with_suffix("._pp.tex")
        tmp_tex.write_text(preprocessed, encoding="utf-8")
        pandoc_input = tmp_tex
    else:
        tmp_tex = None
        pandoc_input = tex_in

    try:
        result = subprocess.run(
            [
                "pandoc", str(pandoc_input),
                "--from=latex",
                # Output format extensions:
                #   fenced_code_blocks + backtick_code_blocks: lstlisting environments
                #     become fenced ``` blocks rather than indented blocks, which MkDocs
                #     renders correctly and applies syntax highlighting to.
                #   pipe_tables: use GFM-style pipe tables, which Python-Markdown
                #     (MkDocs) supports natively.
                #   raw_html: pass any literal HTML fragments in the .tex through
                #     to the output unchanged instead of discarding them.
                "--to=markdown+fenced_code_blocks+backtick_code_blocks+pipe_tables+raw_html",
                f"--lua-filter={filters_dir / 'cleanup.lua'}",
                f"--lua-filter={filters_dir / 'resolve_refs.lua'}",
                # --citeproc resolves \cite{} commands so citations appear as
                # formatted references in the text, not raw '\cite{key}' strings.
                f"--bibliography={bib_file}",
                "--citeproc",
                # --mathjax keeps math as LaTeX delimiters ($$...$$) instead of
                # converting to HTML entities. MathJax (configured in mkdocs.yml)
                # renders them in the browser, preserving full LaTeX math quality.
                "--mathjax",
                # --wrap=none prevents pandoc from hard-wrapping long lines at 72
                # characters, which would break inline code, URLs, and table cell
                # content in the generated Markdown.
                "--wrap=none",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=repo_root,
        )

        for line in result.stderr.splitlines():
            if line.strip():
                _warn(f"    pandoc: {line}")

        if result.returncode != 0:
            _warn(f"  Failed to convert {tex_in} (exit code {result.returncode}). Chapter skipped.")
            return None

        return result.stdout
    finally:
        if tmp_tex is not None:
            tmp_tex.unlink(missing_ok=True)


def _write_chapter_md(
    out_path: Path,
    title: str,
    autor: str,
    md_body: str,
) -> None:
    # YAML front-matter is required by MkDocs: 'title' drives the browser-tab
    # title and the sidebar nav label; 'author' is exposed to the Jinja2
    # template via page.meta. Without front-matter, MkDocs falls back to
    # deriving the page title from the first heading, which is less reliable
    # and makes the author field unavailable to the template.
    front_matter = f'---\ntitle: "{title}"\nauthor: "{autor}"\n---\n'
    out_path.write_text(
        f"{front_matter}\n# {title}\n\n{md_body}\n",
        encoding="utf-8",
    )


def convert_chapter(
    tex_in: Path,
    md_out: Path,
    title: str,
    autor: str,
    filters_dir: Path,
    bib_file: Path,
    labels_json: Path,
    repo_root: Path,
) -> None:
    """Convert a single chapter from LaTeX to Markdown."""
    out_file = md_out.name  # filename only, for CURRENT_DOC_FILE
    _info(f"  {tex_in} → {md_out.relative_to(md_out.parents[1])}")

    md_body = _run_pandoc_chapter(
        tex_in=tex_in,
        filters_dir=filters_dir,
        bib_file=bib_file,
        labels_json=labels_json,
        current_doc_file=out_file,
        repo_root=repo_root,
    )
    if md_body is None:
        return

    md_body = _postprocess(md_body)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    _write_chapter_md(md_out, title, autor, md_body)


def convert_inline_section(latex_body: str, label: str, filters_dir: Path, repo_root: Path) -> str:
    """Convert a small inline LaTeX snippet (e.g. resumen body) to Markdown GFM."""
    if not latex_body.strip():
        return ""

    # Pandoc requires a file path as input — it cannot accept LaTeX content
    # via stdin and still resolve relative resource paths correctly (e.g.
    # \includegraphics with paths relative to the .tex file location).
    # Writing the snippet to a NamedTemporaryFile gives pandoc a real
    # filesystem path to work from. The finally block ensures the temp file
    # is deleted even if the subprocess raises an exception.
    with tempfile.NamedTemporaryFile(suffix=".tex", mode="w", delete=False, encoding="utf-8") as f:
        f.write(latex_body)
        tmp_tex = Path(f.name)

    try:
        result = subprocess.run(
            [
                "pandoc", str(tmp_tex),
                "--from=latex",
                "--to=gfm",
                f"--lua-filter={filters_dir / 'cleanup.lua'}",
                "--wrap=none",
            ],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        for line in result.stderr.splitlines():
            if line.strip():
                _warn(f"  pandoc ({label}): {line}")
        out = result.stdout.strip() if result.returncode == 0 else ""
        # Post-process inline snippets (normalize image paths, headings,
        # and compactitem → comma lists)
        return _postprocess(out)
    finally:
        tmp_tex.unlink(missing_ok=True)


def convert_all_chapters(
    repo_root: Path,
    docs_dir: Path,
    struct: DocStructure,
    meta: dict,
    filters_dir: Path,
    bib_file: Path,
    labels_json: Path,
) -> None:
    """Convert all chapters and appendixes to Markdown, and generate index/agradecimientos."""
    _info("Pass 2: converting chapters...")

    # ---- Inline sections (resumen, agradecimientos) --------------------
    resumen_body = ""
    agradec_body = ""

    for sec in struct.inline_sections:
        body = convert_inline_section(sec.latex_body, sec.key, filters_dir, repo_root)
        if "agradec" in sec.key:
            agradec_body = body
        elif "resumen" in sec.key:
            resumen_body = body

    # Fallback: read pages/resumen.tex if not inline
    if not resumen_body:
        resumen_tex = repo_root / "pages" / "resumen.tex"
        if resumen_tex.exists():
            resumen_body = convert_inline_section(
                resumen_tex.read_text(encoding="utf-8"), "resumen", filters_dir, repo_root
            )

    # ---- index.md ------------------------------------------------------
    m = meta
    index_content = (
        f'---\ntitle: "{m["title"]}"\n---\n\n'
        f'<div class="tfg-cover">\n'
        f'  <img src="img/logoURJC.svg" alt="{m["university"]}">\n'
        f'  <h1>{m["title"]}</h1>\n'
        f'  <p class="meta">\n'
        f'    <strong>{m["author"]}</strong><br>\n'
        f'    Tutor: {m["tutor"]}<br>\n'
        f'    {m["degree"]}<br>\n'
        f'    {m["university"]} — {m["school"]}<br>\n'
        f'    {m["academic_year"]}\n'
        f'  </p>\n'
        f'</div>\n\n---\n\n{resumen_body}\n'
    )
    (docs_dir / "index.md").write_text(index_content, encoding="utf-8")

    # ---- agradecimientos.md -------------------------------------------
    if agradec_body:
        agradec_content = (
            '---\ntitle: "Agradecimientos"\n---\n\n'
            f'# Agradecimientos\n\n{agradec_body}\n'
        )
        (docs_dir / "agradecimientos.md").write_text(agradec_content, encoding="utf-8")
        _info("  acknowledgements (inline) → agradecimientos.md")

    # ---- Regular chapters ---------------------------------------------
    for chap in struct.chapters:
        tex_in = repo_root / chap.tex_file
        md_out = docs_dir / (Path(chap.tex_file).stem + ".md")
        convert_chapter(tex_in, md_out, chap.title, m["author"],
                        filters_dir, bib_file, labels_json, repo_root)

    # ---- Appendixes ---------------------------------------------------
    (docs_dir / "appendixes").mkdir(parents=True, exist_ok=True)
    for app in struct.appendixes:
        tex_in = repo_root / app.tex_file
        md_out = docs_dir / "appendixes" / (Path(app.tex_file).stem + ".md")
        convert_chapter(tex_in, md_out, app.title, m["author"],
                        filters_dir, bib_file, labels_json, repo_root)
