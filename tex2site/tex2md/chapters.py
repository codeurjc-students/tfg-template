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


def _strip_latex_caption(s: str) -> str:
    """Convert a LaTeX caption string to plain text.

    Strips formatting commands (\\textit, \\textbf, …), removes math-mode
    delimiters while keeping their content, and strips remaining backslash
    commands so the result is usable as a plain-text label in lstlisting
    options.
    """
    # Strip font commands keeping their argument text (up to 4 levels deep)
    for _ in range(4):
        s = re.sub(
            r'\\(?:textit|textbf|text|emph|texttt|textrm|mathrm|mathbf)\{([^{}]*)\}',
            r'\1', s,
        )
    # LaTeX typographic quotes
    s = s.replace('``', '\u201c').replace("''", '\u201d')
    # Remove math-mode delimiters $...$ keeping the math content
    s = re.sub(r'\$([^$]*)\$', r'\1', s)
    # Remove \left, \right (spacing commands without their own arguments)
    s = re.sub(r'\\(?:left|right)\s*', '', s)
    # Strip \cmd{...} keeping argument content
    s = re.sub(r'\\[a-zA-Z]+\{([^{}]*)\}', r'\1', s)
    # Remove remaining \cmd (no braces argument)
    s = re.sub(r'\\[a-zA-Z]+\s*', '', s)
    # Remove any leftover bare braces
    s = s.replace('{', '').replace('}', '')
    # Backslash-space → plain space
    s = s.replace('\\ ', ' ')
    # Normalise whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# ---------------------------------------------------------------------------
# LaTeX tabular helpers (multirow/multicolumn → HTML)
# ---------------------------------------------------------------------------

def _split_tabular_rows(body: str) -> list:
    """Split a tabular body into rows by \\\\ at brace depth 0."""
    rows, current, depth, i = [], [], 0, 0
    while i < len(body):
        c = body[i]
        if c == '{':
            depth += 1; current.append(c)
        elif c == '}':
            depth -= 1; current.append(c)
        elif c == '\\' and i + 1 < len(body) and body[i + 1] == '\\' and depth == 0:
            rows.append(''.join(current))
            current = []
            i += 2
            continue
        else:
            current.append(c)
        i += 1
    tail = ''.join(current).strip()
    if tail:
        rows.append(tail)
    return rows


def _split_tabular_cells(row: str) -> list:
    """Split a row into cells by & at brace depth 0."""
    cells, current, depth = [], [], 0
    for c in row:
        if c == '{':
            depth += 1; current.append(c)
        elif c == '}':
            depth -= 1; current.append(c)
        elif c == '&' and depth == 0:
            cells.append(''.join(current))
            current = []
        else:
            current.append(c)
    cells.append(''.join(current))
    return cells


def _parse_tabular_cell(cell_tex: str) -> dict:
    """Parse a cell, extracting multirow/multicolumn span info and content."""
    cell_tex = cell_tex.strip()
    result = {'content': cell_tex, 'rowspan': 1, 'colspan': 1}
    # \multicolumn{n}{align}{content}
    mc_m = re.match(r'\\multicolumn\{(\d+)\}\{[^}]+\}\{(.*)\}$', cell_tex, re.DOTALL)
    if mc_m:
        result['colspan'] = int(mc_m.group(1))
        cell_tex = mc_m.group(2).strip()
        result['content'] = cell_tex
    # \multirow{n}{width}{content} (may be nested inside multicolumn)
    mr_m = re.match(r'\\multirow\{(\d+)\}\{[^}]*\}\{(.*)\}$', cell_tex, re.DOTALL)
    if mr_m:
        result['rowspan'] = int(mr_m.group(1))
        result['content'] = mr_m.group(2).strip()
    return result


def _tex_cell_to_html(tex: str) -> str:
    """Convert LaTeX tabular cell content to HTML inline text."""
    tex = tex.strip()
    # Extract \verb|...| first using placeholders so that the subsequent
    # bare-command stripping (\\[a-zA-Z]+) does not eat backslashes inside
    # verbatim content (e.g. \verb|'\n'| → <code>'\n'</code> not <code>''</code>).
    _verb_placeholders: dict = {}
    _verb_counter = [0]
    def _verb_sub(m: re.Match) -> str:
        key = f'\x00VERB{_verb_counter[0]}\x00'
        _verb_counter[0] += 1
        content = (m.group(2)
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        _verb_placeholders[key] = f'<code>{content}</code>'
        return key
    tex = re.sub(r'\verb([^a-zA-Z\s])(.*?)\1', _verb_sub, tex)
    # Protect $...$ math expressions with placeholders so that \alpha etc.
    # inside math are not eaten by the bare-command stripping step below.
    # The $...$ delimiters are preserved verbatim — MathJax will render them.
    _math_placeholders: dict = {}
    _math_counter = [0]
    def _math_sub(m: re.Match) -> str:
        key = f'\x00MATH{_math_counter[0]}\x00'
        _math_counter[0] += 1
        _math_placeholders[key] = m.group(0)
        return key
    tex = re.sub(r'\$[^$]*\$', _math_sub, tex)
    tex = re.sub(r'\\textbf\{([^{}]*)\}', r'<strong>\1</strong>', tex)
    tex = re.sub(r'\\(?:textit|emph)\{([^{}]*)\}', r'<em>\1</em>', tex)
    tex = re.sub(r'\\texttt\{([^{}]*)\}', r'<code>\1</code>', tex)
    # LaTeX typographic shortcuts
    tex = tex.replace("``", '\u201c').replace("''", '\u201d')
    tex = tex.replace('\\&', '&amp;').replace('\\%', '%').replace('\\$', '$')
    # Strip remaining \cmd{...} keeping argument, then bare \cmd
    tex = re.sub(r'\\[a-zA-Z]+\{([^{}]*)\}', r'\1', tex)
    tex = re.sub(r'\\[a-zA-Z]+\s*', '', tex)
    tex = tex.replace('{', '').replace('}', '')
    # Restore \verb placeholders
    for key, val in _verb_placeholders.items():
        tex = tex.replace(key, val)
    # Restore $...$ math placeholders
    for key, val in _math_placeholders.items():
        tex = tex.replace(key, val)
    return tex.strip()


def _convert_tabular_to_html(tabular_body: str, col_spec: str) -> str:
    """Convert a LaTeX tabular body to an HTML <table> with rowspan/colspan."""
    num_cols = len(re.findall(r'[lrcp]', col_spec))
    # Strip LaTeX line comments (%...) before splitting rows so that
    # inline comments after \\ don't bleed into the next row's cell content.
    tabular_body = re.sub(r'(?<!\\)%[^\n]*', '', tabular_body)
    raw_rows = _split_tabular_rows(tabular_body)

    parsed_rows = []
    for row_tex in raw_rows:
        row_tex = re.sub(r'\\hline', '', row_tex)
        row_tex = re.sub(r'\\cline\{[^}]+\}', '', row_tex)
        row_tex = row_tex.strip()
        if not row_tex:
            continue
        cells_tex = _split_tabular_cells(row_tex)
        cells, col_pos = [], 1
        for ct in cells_tex:
            pc = _parse_tabular_cell(ct)
            pc['col_pos'] = col_pos
            cells.append(pc)
            col_pos += pc['colspan']
        parsed_rows.append(cells)

    # row_span_remaining[c] = rows still "occupied" in column c (1-indexed)
    row_span_remaining = [0] * (num_cols + 2)
    html_rows = []

    for cells in parsed_rows:
        cell_by_col = {c['col_pos']: c for c in cells}
        html_cells = []
        col_idx = 1
        while col_idx <= num_cols:
            if row_span_remaining[col_idx] > 0:
                row_span_remaining[col_idx] -= 1
                col_idx += 1
                continue
            if col_idx not in cell_by_col:
                col_idx += 1
                continue
            cell = cell_by_col[col_idx]
            rowspan, colspan = cell['rowspan'], cell['colspan']
            content = _tex_cell_to_html(cell['content'])
            for c in range(col_idx, col_idx + colspan):
                if c <= num_cols:
                    row_span_remaining[c] = rowspan - 1
            attrs = ''
            if rowspan > 1:
                attrs += f' rowspan="{rowspan}"'
            if colspan > 1:
                attrs += f' colspan="{colspan}"'
            html_cells.append(f'<td{attrs}>{content}</td>')
            col_idx += colspan
        if html_cells:
            html_rows.append('<tr>' + ''.join(html_cells) + '</tr>')

    return '<table>\n' + '\n'.join(html_rows) + '\n</table>'


def _preprocess_tex(tex: str) -> str:
    r"""Apply LaTeX-level transformations before passing to Pandoc.

    Transformations:
    1. Strip \\cline{N-M} — Pandoc does not understand partial horizontal
       rules and includes the "N-M" argument text as spurious cell content
       in the generated Markdown table.
    2. Replace \\begin{mypython} / \\end{mypython} with lstlisting — the
       mypython environment is a custom lstnewenvironment alias defined in
       config.tex.  Pandoc does not know about it and emits a raw Div;
       replacing it with lstlisting lets Pandoc convert it to an indented
       code block that fix_code_captions() can then wrap in
       <figure>/<figcaption>.
    3. Convert \\begin{algorithm}…\\end{algorithm} to lstlisting with
       language={pseudocode-js} — preserves the original algorithmic LaTeX
       (\\STATE, \\FOR, \\IF, etc.) verbatim inside a lstlisting block so
       that Pandoc passes the content unchanged, and fix_code_captions()
       then emits a <pre class="pseudocode"> block for rendering by
       pseudocode.js in the browser.
    """
    # 1. Strip \cline{N-M} partial horizontal rules.
    tex = re.sub(r'\\cline\{[^}]+\}', '', tex)

    # 2. Replace mypython with lstlisting.
    tex = re.sub(r'\\begin\{mypython\}', r'\\begin{lstlisting}', tex)
    tex = tex.replace(r'\end{mypython}', r'\end{lstlisting}')

    # 2b. Normalise lstlisting options: strip leading whitespace after '[' so
    # that '\begin{lstlisting}[ caption=...]' becomes '\begin{lstlisting}[caption=...]'.
    # Without this, Pandoc fails to parse the attributes and emits an indented
    # code block with no identifier, causing collect_labels.lua to miss the label
    # and all \ref{} to it to render as unresolved references.
    tex = re.sub(r'(\\begin\{lstlisting\})\[\s+', r'\1[', tex)

    # 3. Convert algorithm environments to lstlisting with language={pseudocode-js}.
    # The original algorithmic LaTeX is preserved verbatim inside the lstlisting
    # so Pandoc passes it through unchanged.  fix_code_captions() then converts
    # the resulting fenced code block into <pre class="pseudocode"> for rendering
    # by pseudocode.js in the browser.
    def _convert_algorithm(m: re.Match) -> str:
        body = m.group(1)

        # Extract label for the lstlisting options (used as the HTML id).
        lab_m = re.search(r'\\label\{([^}]+)\}', body)
        label = lab_m.group(1).strip() if lab_m else ''

        # Strip \label{...} from the body — pseudocode.js does not recognise it
        # and throws a parse error (leaving the source <pre> as display:none).
        # The id is already carried by the lstlisting label= option, which
        # fix_code_captions() maps to the id attribute on the <pre> element.
        body = re.sub(r'\\label\{[^}]+\}', '', body)

        # Strip the optional [N] argument from \begin{algorithmic}[N] — this is
        # a LaTeX line-numbering step option unknown to pseudocode.js.
        # Line numbering is enabled globally via lineNumber:true in pseudocode_init.js.
        body = re.sub(r'(\\begin\{algorithmic\})\[\d+\]', r'\1', body)

        # Replace \ (backslash-space) with a plain space.
        # In LaTeX text mode (e.g. after a $...$ expression) \ is a spacing
        # command that pseudocode.js does not recognise and throws
        # "Unrecognizable atom".  In math mode KaTeX ignores whitespace, so
        # the replacement is harmless there too.
        body = body.replace('\\ ', ' ')

        # pseudocode.js requires \caption to appear BEFORE \begin{algorithmic}.
        # In typical LaTeX, \caption is placed after \end{algorithmic}, so move it.
        algo_start_m = re.search(r'\\begin\{algorithmic\}', body)
        if not algo_start_m:
            return m.group(0)  # leave unchanged if structure not recognised

        cap_m = re.search(r'\\caption\{((?:[^{}]|\{[^{}]*\})*)\}', body)
        if cap_m and cap_m.start() > algo_start_m.start():
            caption_str = cap_m.group(0)
            body = body[:cap_m.start()] + body[cap_m.end():]
            new_algo_m = re.search(r'\\begin\{algorithmic\}', body)
            if new_algo_m:
                body = (
                    body[:new_algo_m.start()]
                    + caption_str + '\n'
                    + body[new_algo_m.start():]
                )

        opts_parts = ['language={pseudocode-js}']
        if label:
            opts_parts.append(f'label={{{label}}}')
        # Add a plain-text caption so collect_labels.lua can use it as the
        # display text for \ref{} cross-references instead of the generic
        # counter ("código N.M").
        if cap_m:
            raw_cap = cap_m.group(1)
            # If the caption opens with an italic phrase (\textit{...}), use
            # only that phrase as the display text — algorithm captions
            # commonly include "input" / "output" metadata after the title,
            # e.g. \caption{\textit{My Algo} \textbf{input}=... \textbf{output}=...}.
            # Using only the italic title gives a clean reference label.
            italic_m = re.match(r'\s*\\textit\{([^{}]*)\}', raw_cap)
            if italic_m:
                plain_cap = italic_m.group(1).strip()
            else:
                plain_cap = _strip_latex_caption(raw_cap)
            if plain_cap:
                opts_parts.append(f'caption={{{plain_cap}}}')
        opts = '[' + ', '.join(opts_parts) + ']'

        content = body.strip()
        return (
            f'\\begin{{lstlisting}}{opts}\n'
            f'\\begin{{algorithm}}\n{content}\n\\end{{algorithm}}\n'
            f'\\end{{lstlisting}}'
        )

    tex = re.sub(
        r'\\begin\{algorithm\}(.*?)\\end\{algorithm\}',
        _convert_algorithm,
        tex,
        flags=re.DOTALL,
    )

    # 4. Convert LaTeX tables that use \multirow / \multicolumn to HTML tables
    # wrapped in lstlisting[language={htmltable}].  Plain tables (no spanning
    # cells) are left untouched and let Pandoc convert them to Markdown pipe
    # tables.  Pandoc passes the lstlisting content verbatim to the Markdown
    # output; fix_code_captions() (Pattern 4) then unwraps it as a raw
    # <figure>/<table> block.
    def _convert_table_to_htmlblock(m: re.Match) -> str:
        body = m.group(1)
        if not re.search(r'\\multirow|\\multicolumn', body):
            return m.group(0)  # plain table — let Pandoc handle it
        cap_m = re.search(r'\\caption\{((?:[^{}]|\{[^{}]*\})*)\}', body)
        lab_m = re.search(r'\\label\{([^}]+)\}', body)
        caption_raw = cap_m.group(1) if cap_m else ''
        label = lab_m.group(1).strip() if lab_m else ''
        caption_plain = _strip_latex_caption(caption_raw)
        tab_m = re.search(
            r'\\begin\{tabular\}\{([^}]+)\}(.*?)\\end\{tabular\}',
            body, re.DOTALL,
        )
        if not tab_m:
            return m.group(0)
        html_table = _convert_tabular_to_html(tab_m.group(2), tab_m.group(1))
        opts_parts = ['language={htmltable}']
        if caption_plain:
            opts_parts.append(f'caption={{{caption_plain}}}')
        if label:
            opts_parts.append(f'label={{{label}}}')
        opts = '[' + ', '.join(opts_parts) + ']'
        return f'\\begin{{lstlisting}}{opts}\n{html_table}\n\\end{{lstlisting}}'

    tex = re.sub(
        r'\\begin\{table\}(.*?)\\end\{table\}',
        _convert_table_to_htmlblock,
        tex,
        flags=re.DOTALL,
    )
    tex = re.sub(
        r'\\begin\{sidewaystable\}(.*?)\\end\{sidewaystable\}',
        _convert_table_to_htmlblock,
        tex,
        flags=re.DOTALL,
    )

    return tex


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

        # Only split when at least one minipage has its own \label so that
        # cross-references to individual subfigures can be resolved.  When
        # no minipage has a label the outer \caption and any extra images
        # outside the minipages (e.g. a third sub-figure (c)) would be
        # silently discarded by the splitting logic.  In that case, Pandoc
        # processes the full figure and emits a proper <figure>/<figcaption>
        # HTML block with all images and the combined caption intact.
        if len(minipages) >= 2 and any(mp['label'] for mp in minipages):
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
    # LaTeX \logoUniversidad macro → resolved URJC logo SVG path.
    # Pandoc does not expand cross-file \newcommand definitions so
    # \logoUniversidad passes through verbatim as the image path.  We
    # intercept it here and point it at the logo SVG produced by images.py.
    (re.compile(r'\]\(\\logoUniversidad\)'), r'](/img/logoURJC.svg)'),
    # HTML <embed> elements emitted by Pandoc for PDF/EPS images inside raw
    # HTML <figure> blocks (e.g. multi-subfigure environments that were NOT
    # split by _split_minipage_figures).  These rules run BEFORE the plain
    # src="img/" → src="/img/" substitution below so that the patterns still
    # match the original relative paths in the Pandoc HTML output.
    # The \3 back-reference preserves any style="…" or other attributes.
    (re.compile(r'<embed\s+src="img/([^"]+)\.(pdf|eps)"([^/]*)/>'), r'<img src="/img/\1.svg"\3/>'),
    (re.compile(r'<embed\s+src="\.\./img/([^"]+)\.(pdf|eps)"([^/]*)/>'), r'<img src="/img/\1.svg"\3/>'),
    (re.compile(r'<embed\s+src="config/logos/([^"]+)\.(pdf|eps)"([^/]*)/>'), r'<img src="/img/\1.svg"\3/>'),
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
            preprocessed = _preprocess_tex(content)
            preprocessed = _split_minipage_figures(preprocessed)
            if preprocessed == content:
                continue  # no changes needed for this chapter

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

    # Pre-process: apply LaTeX-level fixes then split minipage multi-figure
    # constructs so every subfigure gets its own caption and anchor.
    original_content = tex_in.read_text(encoding="utf-8")
    preprocessed = _preprocess_tex(original_content)
    preprocessed = _split_minipage_figures(preprocessed)
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
    docs_dir: Path | None = None,
) -> None:
    """Convert a single chapter from LaTeX to Markdown."""
    # CURRENT_DOC_FILE must match the path stored by collect_labels.lua in
    # .labels.json (e.g. "appendixes/anexo-4.md" for appendix files).  Using
    # md_out.name alone would give just "anexo-4.md", causing the same-page
    # anchor check in resolve_refs.lua to fail for every appendix label.
    if docs_dir is not None:
        out_file = str(md_out.relative_to(docs_dir))
    else:
        out_file = md_out.name  # fallback: filename only
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
                        filters_dir, bib_file, labels_json, repo_root, docs_dir)

    # ---- Appendixes ---------------------------------------------------
    (docs_dir / "appendixes").mkdir(parents=True, exist_ok=True)
    for app in struct.appendixes:
        tex_in = repo_root / app.tex_file
        md_out = docs_dir / "appendixes" / (Path(app.tex_file).stem + ".md")
        convert_chapter(tex_in, md_out, app.title, m["author"],
                        filters_dir, bib_file, labels_json, repo_root, docs_dir)
