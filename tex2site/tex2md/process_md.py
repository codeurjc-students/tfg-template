#!/usr/bin/env python3
"""Post-process generated Markdown files in web/docs/ to produce clean, standard output.

Transformations applied to every .md file:
  - fix_text()                              — normalise {.underline} links; rewrite /img/ paths
                                              to relative; convert Pandoc image attributes to
                                              <figure>/<figcaption> HTML blocks.
  - fix_markdown_widths()                   — convert width="0.5\\linewidth" → width="50%"
  - strip_pandoc_divs()                     — remove ::: fenced-div markers (rendered as literal
                                              text by MkDocs)
  - dedent_pandoc_tables()                  — remove two-space indent Pandoc adds to some tables
  - convert_headerless_two_col_tables_to_list() — flatten headerless two-column Pandoc simple
                                              tables into unordered Markdown lists
  - convert_pandoc_simple_tables()          — convert Pandoc space-aligned tables → Markdown pipe tables
  - convert_pandoc_pipe_grid_tables()       — convert Pandoc +---+ grid tables → pipe tables (simple cells)
                                              or HTML (cells with lists / multi-paragraph content)
  - fix_bold_in_html_cells()                — convert **text** inside <th>/<td> to <strong>
                                              (only affects the HTML tables from complex grid cells)
"""
import argparse
import re
import sys
from pathlib import Path

def fix_text(s: str, img_prefix: str) -> str:
    # Pandoc converts LaTeX \href{url}{\underline{text}} constructs to
    # [[text]{.underline}](url). This syntax is Pandoc-specific and is not
    # valid CommonMark, so MkDocs renders the curly braces as literal text.
    # We strip the {.underline} wrapper and produce plain Markdown links.
    s = re.sub(r"\[\[([^\]]+?)\]\{\.underline\}\[\^([0-9]+)\]\]\((https?://[^)]+)\)", r"[\1](\3)[^\2]", s)
    s = re.sub(r"\[\[([^\]]+?)\]\{\.underline\}\[\^([^\]]+)\]\]\((https?://[^)]+)\)", r"[\1](\3)[^\2]", s)
    s = re.sub(r"\[\[([^\]]+?)\]\{\.underline\}\]\((https?://[^)]+)\)", r"[\1](\2)", s)
    s = re.sub(r"\[\[([^\]]+?)\]\{\.underline\}\]", r"[\1]", s)
    s = re.sub(r"\[\[([^\]]+?)\]\{\.underline\}\]\(([^)]+)\)", r"[\1](\2)", s)

    # chapters.py normalises Pandoc's image paths to absolute /img/ for
    # consistency during the conversion step. Here we convert them back to
    # relative paths because MkDocs serves the site at a configurable base
    # URL (e.g. GitHub Pages at /repo-name/), where absolute /img/ paths
    # would resolve against the server root instead of the site root.
    # Appendix pages sit one level deeper (appendixes/), so their prefix is
    # '../../img/' while top-level pages use '../img/'.
    s = re.sub(r"\]\(/img/([^)\]]+)\)", rf"]({img_prefix}img/\1)", s)
    s = re.sub(r"!\(\/img\/([^)]+)\)", rf"!({img_prefix}img/\1)", s)

    # Pandoc emits images with attributes as ![Caption](src){#id width="50%"}.
    # CommonMark (and MkDocs' Python-Markdown) does not support this attribute
    # syntax — the {#id width="50%"} block is rendered as literal text after
    # the image. Converting to an HTML <figure> block:
    #   - preserves the anchor id so \ref{} cross-references still work
    #   - applies width as an inline CSS style
    #   - adds <figcaption> so captions appear below the image
    def _img_to_figure(m):
        alt = m.group(1) or ''
        src = m.group(2)
        attrs = m.group(3) or ''

        # extract id like #fig:name
        id_match = re.search(r"#([^\s.]+)", attrs)
        fig_id = id_match.group(1) if id_match else None

        # extract width if present
        width_match = re.search(r'width\s*=\s*"([^\"]+)"', attrs)
        style = ''
        if width_match:
            w = width_match.group(1)
            # handle fraction like 0.5\linewidth
            frac = re.match(r"^([0-9.]+)\\\\?\\?\\?(?:linewidth|textwidth)$", w)
            if frac:
                pct = float(frac.group(1)) * 100
                style = f'width:{int(pct) if pct.is_integer() else round(pct,2)}%'
            else:
                style = f'width:{w}'

        parts = []
        if fig_id:
            parts.append(f'id="{fig_id}"')
        if style:
            parts.append(f'style="{style}"')

        attrs_str = (' ' + ' '.join(parts)) if parts else ''

        # sanitize alt for HTML (minimal)
        alt_escaped = alt.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        figure = f'<figure{attrs_str}>\n<img src="{src}" alt="{alt_escaped}"/>\n<figcaption>{alt_escaped}</figcaption>\n</figure>'
        return figure

    s = re.sub(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)\{([^}]*)\}', _img_to_figure, s)

    return s


def fix_markdown_widths(s: str) -> str:
    # LaTeX \linewidth and \textwidth express widths as fractions of the
    # text column (e.g. width="0.8\linewidth"). These units are PDF-specific
    # and have no meaning in HTML. We convert them to percentage values
    # (0.8 → 80%) so images scale proportionally to their container on the
    # web page, matching the intended size from the original PDF layout.
    def repl(m):
        val = float(m.group(1))
        pct = f"{int(val*100)}%" if val*100 == int(val*100) else f"{val*100:.2f}%"
        return f'width="{pct}"'

    # patterns like width="0.5\linewidth" or width="0.75\\textwidth"
    s = re.sub(r'width=["\']([0-9.]+)\\\\?\\?(?:linewidth|textwidth)["\']', repl, s)
    # patterns like width="\\linewidth" -> 100%
    s = re.sub(r'width=["\']\\\\?\\?(?:linewidth|textwidth)["\']', 'width="100%"', s)
    return s


def dedent_pandoc_tables(s: str) -> str:
    """Dedent Pandoc-produced table blocks that are indented by two spaces.

    Pandoc sometimes emits tables with a two-space indentation. In CommonMark,
    a block indented by two or more spaces inside a list is parsed as a
    continuation of that list item, not as a standalone table. The result is
    that the table disappears or gets swallowed into a list item. We detect
    the indented header+separator pattern and strip the leading two spaces
    from the entire contiguous block so the table is parsed correctly.
    """
    lines = s.splitlines()
    out_lines = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        # detect potential table header: indented and starts with bold header
        if line.startswith('  ') and line.lstrip().startswith('**') and i+1 < n:
            next_line = lines[i+1]
            if next_line.startswith('  ') and set(next_line.strip()) <= set('- :') and ('-' in next_line):
                # start dedenting contiguous indented block
                j = i
                while j < n and lines[j].startswith('  '):
                    out_lines.append(lines[j][2:])
                    j += 1
                i = j
                continue
        out_lines.append(line)
        i += 1
    return '\n'.join(out_lines) + ('\n' if s.endswith('\n') else '')


def convert_pandoc_pipe_grid_tables(s: str) -> str:
    """Convert Pandoc pipe-grid tables (+---+---+ format) to HTML <table> blocks.

    Pandoc emits this border-separated format when any cell contains
    multi-paragraph content (e.g. a cell with a nested list). MkDocs'
    Python-Markdown cannot render this format and displays the raw text.

    Format recognised::

        +-----------+-----------+---------+
        | **Header**| **Col 2** | **Col3**|
        +:==========+:==========+:========+
        | REQ-1     | 0         | Simple  |
        +-----------+-----------+---------+
        | REQ-7     | 0         | Text:   |
        |           |           |         |
        |           |           | - item1 |
        |           |           |         |
        |           |           | - item2 |
        +-----------+-----------+---------+
    """
    _sep_re = re.compile(r'^\+([-=:]+\+)+\s*$')
    _row_re = re.compile(r'^\|.*\|\s*$')

    def is_sep(line):
        return bool(_sep_re.match(line.rstrip()))

    def is_row(line):
        return bool(_row_re.match(line.rstrip()))

    def col_bounds(sep_line):
        """Return list of (start, end) column positions from a separator line."""
        positions = [m.start() for m in re.finditer(r'\+', sep_line.rstrip())]
        return list(zip(positions, positions[1:]))

    def extract_row_cells(content_lines, bounds):
        """Return per-column paragraph lists from the content lines of one row.

        Within a row block, lines where all cells are blank act as intra-cell
        paragraph separators. The returned value is a list (one per column) of
        lists of paragraph strings.
        """
        ncols = len(bounds)
        # Accumulate raw per-column lines
        col_lines = [[] for _ in range(ncols)]
        for line in content_lines:
            padded = line.rstrip().ljust(bounds[-1][1] + 1)
            for ci, (start, end) in enumerate(bounds):
                col_lines[ci].append(padded[start + 1:end].strip())

        # Split each column into paragraphs on blank separators
        def to_paragraphs(lines):
            paras, current = [], []
            for ln in lines:
                if ln:
                    current.append(ln)
                else:
                    if current:
                        paras.append(' '.join(current))
                        current = []
            if current:
                paras.append(' '.join(current))
            return paras

        return [to_paragraphs(col) for col in col_lines]

    def md_inline_to_html(text):
        """Convert basic inline Markdown to HTML."""
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*([^*]+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`([^`]+?)`', r'<code>\1</code>', text)
        return text

    def paras_to_html(paras):
        """Convert a paragraph list (cell content) to an HTML string."""
        if not paras:
            return ''
        if len(paras) == 1:
            p = paras[0]
            if re.match(r'^-\s+', p):
                item = re.sub(r'^-\s+', '', p)
                return f'<ul><li>{md_inline_to_html(item)}</li></ul>'
            return md_inline_to_html(p)

        html_parts, list_items = [], []

        def flush_list():
            if list_items:
                items_html = ''.join(
                    f'<li>{md_inline_to_html(it)}</li>' for it in list_items
                )
                html_parts.append(f'<ul>{items_html}</ul>')
                list_items.clear()

        for para in paras:
            if re.match(r'^-\s+', para):
                list_items.append(re.sub(r'^-\s+', '', para))
            else:
                flush_list()
                html_parts.append(f'<p>{md_inline_to_html(para)}</p>')
        flush_list()
        return ''.join(html_parts)

    lines = s.splitlines(keepends=False)
    out = []
    i = 0
    n = len(lines)

    while i < n:
        if not is_sep(lines[i]):
            out.append(lines[i])
            i += 1
            continue

        # Verify next line is a cell row (otherwise not a grid table)
        if i + 1 >= n or not is_row(lines[i + 1]):
            out.append(lines[i])
            i += 1
            continue

        # Collect the whole grid table block
        j = i
        table_lines = []
        while j < n and (is_sep(lines[j]) or is_row(lines[j])):
            table_lines.append(lines[j])
            j += 1

        bounds = col_bounds(table_lines[0])

        # Split table into header and data row blocks
        header_content = []
        row_blocks = []
        found_header_sep = False
        current = []

        for tl in table_lines:
            if is_sep(tl):
                if not found_header_sep and '=' in tl:
                    # This separator ends the header
                    header_content = current
                    current = []
                    found_header_sep = True
                else:
                    if found_header_sep and current:
                        row_blocks.append(current)
                    current = []
            else:
                current.append(tl)
        if current and found_header_sep:
            row_blocks.append(current)

        def _block_is_simple(block):
            """Return True if every cell in a row block is a single plain-text paragraph.

            A block is complex if it contains intra-cell blank lines (multi-paragraph)
            or any cell that starts a Markdown list item with '- '.
            """
            for line in block:
                padded = line.rstrip().ljust(bounds[-1][1] + 1)
                cells = [padded[s + 1:e].strip() for s, e in bounds]
                # All-empty line = paragraph separator within a cell → complex
                if all(c == '' for c in cells):
                    return False
                # List item in any cell → complex
                if any(re.match(r'^-\s+', c) for c in cells):
                    return False
            return True

        def _simple_cell_texts(block):
            """Concatenate token lines of each cell in a simple row block."""
            texts = [[] for _ in range(len(bounds))]
            for line in block:
                padded = line.rstrip().ljust(bounds[-1][1] + 1)
                for ci, (start, end) in enumerate(bounds):
                    cell_text = padded[start + 1:end].strip()
                    if cell_text:
                        texts[ci].append(cell_text)
            return [' '.join(parts) for parts in texts]

        def _escape_pipe(text):
            return text.replace('|', '\\|')

        if _block_is_simple(header_content) and all(_block_is_simple(b) for b in row_blocks):
            # All cells contain plain text → emit a native Markdown pipe table.
            header_cells = _simple_cell_texts(header_content)
            pipe_lines = [
                '| ' + ' | '.join(_escape_pipe(h) for h in header_cells) + ' |',
                '| ' + ' | '.join('---' for _ in header_cells) + ' |',
            ]
            for block in row_blocks:
                cells = _simple_cell_texts(block)
                while len(cells) < len(header_cells):
                    cells.append('')
                pipe_lines.append('| ' + ' | '.join(_escape_pipe(c) for c in cells) + ' |')
            out.extend(pipe_lines)
        else:
            # Complex cells (lists, multi-paragraph) → fall back to HTML.
            html = ['<table>', '<thead>', '<tr>']
            for col_paras in extract_row_cells(header_content, bounds):
                html.append(f'<th>{paras_to_html(col_paras)}</th>')
            html += ['</tr>', '</thead>', '<tbody>']
            for block in row_blocks:
                html.append('<tr>')
                for col_paras in extract_row_cells(block, bounds):
                    html.append(f'<td>{paras_to_html(col_paras)}</td>')
                html.append('</tr>')
            html += ['</tbody>', '</table>']
            out.extend(html)

        i = j

    return '\n'.join(out) + ('\n' if s.endswith('\n') else '')


def convert_pandoc_simple_tables(s: str) -> str:
    """Convert Pandoc simple tables (space-aligned column format) to Markdown pipe tables.

    Pandoc emits this indented-and-space-padded format for LaTeX tabular/tabularx
    environments whose cells contain only plain text.  MkDocs' Python-Markdown does
    not understand this format and renders it as ordinary paragraphs.  Converting to
    GFM pipe tables produces native Markdown that renders correctly and stays readable
    in the source .md files.

    Detected pattern (lines may have leading whitespace from dedenting)::

        **Col 1**  **Col 2**  **Col 3**
        ---------  ---------  ---------
        value 1    value 2    value 3
        : Optional caption

    Produces::

        | **Col 1** | **Col 2** | **Col 3** |
        | --- | --- | --- |
        | value 1 | value 2 | value 3 |

        : Optional caption
    """
    lines = s.splitlines()
    out = []
    i = 0
    n = len(lines)
    while i < n:
        # Detect header + separator: header has 2+ spaces separating tokens; next
        # line is all dashes/spaces (the column-width ruler).
        if (i + 1 < n
                and '  ' in lines[i]
                and re.search(r'^\s*-{3,}[\s-]*$', lines[i + 1])):
            header = lines[i].strip()
            j = i + 2
            rows = []
            caption = None
            while j < n:
                lj = lines[j]
                if lj.strip() == '':
                    break
                if lj.lstrip().startswith(':::'):
                    break
                # Caption line like ': Caption text'
                if lj.lstrip().startswith(':'):
                    caption = lj.lstrip().lstrip(':').strip()
                    j += 1
                    break
                if '  ' in lj:
                    rows.append(lj.strip())
                    j += 1
                    continue
                break

            if rows:
                def split_cols(line):
                    return [c.strip() for c in re.split(r'\s{2,}', line)]

                def escape_pipe(text):
                    return text.replace('|', '\\|')

                headers = split_cols(header)
                pipe_table = [
                    '| ' + ' | '.join(escape_pipe(h) for h in headers) + ' |',
                    '| ' + ' | '.join('---' for _ in headers) + ' |',
                ]
                for r in rows:
                    cols = split_cols(r)
                    while len(cols) < len(headers):
                        cols.append('')
                    pipe_table.append('| ' + ' | '.join(escape_pipe(c) for c in cols) + ' |')
                out.extend(pipe_table)
                if caption:
                    out.append('')
                    out.append(f': {caption}')
                i = j
                continue
        out.append(lines[i])
        i += 1
    return '\n'.join(out) + ('\n' if s.endswith('\n') else '')

def fix_lstlisting_captions(s: str) -> str:
    """Convert lstlisting optional-argument lines into <figure>/<figcaption> HTML.

    When Pandoc processes \\begin{lstlisting}[caption={...}, label={...}], it
    treats lstlisting as a verbatim environment and includes the optional-
    argument line as the first line of the resulting indented code block.
    This function detects that pattern, extracts caption and label, removes
    the argument line, and wraps the code in <figure>/<figcaption>.
    """
    _opt_re = re.compile(r'^    \[.*?caption=\{([^}]+)\}.*?\]\s*$')
    _lbl_re = re.compile(r'label=\{([^}]+)\}')
    lines = s.splitlines(keepends=True)
    out = []
    i = 0
    n = len(lines)
    while i < n:
        m = _opt_re.match(lines[i])
        if m:
            caption = m.group(1).strip()
            lm = _lbl_re.search(lines[i])
            label = lm.group(1).strip() if lm else ''
            # Accumulate code-block lines (4-space indented), including blank
            # lines that appear inside the block (e.g. between method bodies).
            j = i + 1
            code_lines = []
            while j < n:
                nxt = lines[j]
                if nxt.startswith('    '):
                    code_lines.append(nxt)
                    j += 1
                elif nxt.strip() == '':
                    # include blank line only if more indented lines follow
                    k = j + 1
                    while k < n and lines[k].strip() == '':
                        k += 1
                    if k < n and lines[k].startswith('    '):
                        code_lines.append(nxt)
                        j += 1
                    else:
                        break
                else:
                    break
            # Strip trailing blank lines
            while code_lines and code_lines[-1].strip() == '':
                code_lines.pop()
            # Dedent 4 spaces (the code-block indent) from every line
            code = ''.join(
                l[4:] if l.startswith('    ') else l
                for l in code_lines
            ).rstrip('\n')
            # Escape HTML special chars in the code text
            code_esc = (code.replace('&', '&amp;')
                            .replace('<', '&lt;')
                            .replace('>', '&gt;'))
            id_attr = f' id="{label}"' if label else ''
            out.append(
                f'<figure{id_attr}>\n'
                f'<pre><code>{code_esc}</code></pre>\n'
                f'<figcaption>{caption}</figcaption>\n'
                f'</figure>\n'
            )
            i = j
        else:
            out.append(lines[i])
            i += 1
    return ''.join(out)


def strip_pandoc_divs(s: str) -> str:
    """Remove Pandoc fenced-div markers that MkDocs renders as literal text.

    Pandoc uses ::: {#id .class} fenced divs for LaTeX environments that
    have no direct Markdown equivalent (e.g. multicols, custom divs). MkDocs'
    Python-Markdown parser does not support the fenced-div extension, so the
    ::: markers appear verbatim as triple-colon artefacts in the rendered
    page. The content between the fences is valid Markdown and is kept;
    only the fence lines themselves are removed.

    Also removes the column-count argument paragraph that Pandoc emits as
    the first block inside a multicols fenced div (e.g. a lone "2" from
    \\begin{multicols}{2}). The cleanup.lua Lua filter handles this for
    Pandoc Div nodes, but this is a safety net for any that slip through.
    """
    # Remove lone column-count paragraph immediately following a multicols
    # fenced-div opening (e.g. "::: {.multicols}\n\n2\n" → removed).
    s = re.sub(
        r'^:::\s*\{[^}]*\bmulticols\b[^}]*\}\s*\n+\d+\s*\n',
        '',
        s,
        flags=re.MULTILINE,
    )
    return re.sub(r'^:::.*$\n?', '', s, flags=re.MULTILINE)


def strip_multicols_html(s: str) -> str:
    """Remove raw HTML <div class="multicols"> wrappers and column-count lines.

    When the content inside \\begin{multicols}{N} cannot be converted to
    Markdown (e.g. compactitem lists), Pandoc emits a raw HTML div. The
    first text node inside the div is the column-count argument (e.g. "2").
    We strip the wrapper tags and that leading number.
    """
    def _repl(m: re.Match) -> str:
        content = m.group(1)
        # Drop a leading line that is just the column-count number.
        content = re.sub(r'^\s*\d+\s*\n+', '', content)
        return content.strip()

    return re.sub(
        r'<div class="multicols">\s*(.*?)\s*</div>',
        _repl,
        s,
        flags=re.DOTALL,
    )


def convert_headerless_two_col_tables_to_list(s: str) -> str:
    """Flatten headerless two-column Pandoc simple tables into Markdown lists.

    Pandoc renders LaTeX tabularx/tabular tables with no header row as
    simple tables with leading/trailing dash-separator lines and 2-space
    indentation. These tables are typically used in LaTeX to distribute
    bullet-point items in two columns to save vertical space. On the web,
    the compact column layout is unnecessary and the table format is not
    parsed by MkDocs. We flatten them into a plain Markdown unordered list
    so the content is readable and correctly rendered.

    Detected pattern (all lines indented by 2 spaces)::

        (blank line)
          ---...  ---...     <- opening separator
          item1   item2      <- data row(s)
          item3              <- data row with single item
          ---...  ---...     <- closing separator
        (blank line)
    """
    lines = s.splitlines()
    out = []
    i = 0
    n = len(lines)
    _sep_re = re.compile(r'^  -{3,}[\s-]*$')
    while i < n:
        line = lines[i]
        if _sep_re.match(line):
            # Collect data rows until a matching closing separator is found.
            j = i + 1
            rows = []
            found_close = False
            while j < n:
                lj = lines[j]
                if _sep_re.match(lj):
                    j += 1
                    found_close = True
                    break
                rows.append(lj)
                j += 1
            if found_close and rows:
                items = []
                for row in rows:
                    row_s = row.strip()
                    if not row_s:
                        continue
                    # Split the two (or more) columns by two-or-more spaces.
                    cols = [c.strip() for c in re.split(r'\s{2,}', row_s)]
                    items.extend(c for c in cols if c)
                if items:
                    out.extend(f'- {item}' for item in items)
                    out.append('')
                    i = j
                    continue
        out.append(line)
        i += 1
    return '\n'.join(out) + ('\n' if s.endswith('\n') else '')


def fix_bold_in_html_cells(s: str) -> str:
    """Convert **text** Markdown bold inside HTML <th>/<td> tags to <strong>.

    MkDocs (Python-Markdown) does not process inline Markdown syntax inside
    raw HTML blocks — this is by design per the CommonMark spec. So **bold**
    markers inside a <td> or <th> (emitted by convert_pandoc_pipe_grid_tables()
    for complex cells) appear as literal asterisks in the browser. We post-process the HTML
    cells explicitly to replace **...** with <strong>...</strong>.
    """
    def repl_cell(m):
        tag = m.group(1)   # 'th' or 'td'
        inner = m.group(2)
        # replace **...** with <strong>...</strong>
        inner = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', inner)
        return f'<{tag}>{inner}</{tag}>'
    return re.sub(r'<(th|td)>(.*?)</\1>', repl_cell, s, flags=re.DOTALL)


def process_file(p: Path, docs: Path):
    text = p.read_text(encoding='utf-8')
    # Compute the relative depth of this file within docs/ to build the
    # correct image path prefix. Top-level files (e.g. introduccion.md)
    # need '../img/', while appendix files (appendixes/anexo-1.md) need
    # '../../img/'. depth=0 means the file is directly inside docs/.
    rel = p.relative_to(docs)
    depth = len(rel.parent.parts)  # 0 for top-level files
    prefix = "../" * (depth + 1)
    new = fix_lstlisting_captions(text)
    new = fix_text(new, prefix)
    new = fix_markdown_widths(new)
    new = strip_pandoc_divs(new)
    new = strip_multicols_html(new)
    new = dedent_pandoc_tables(new)
    new = convert_headerless_two_col_tables_to_list(new)
    new = convert_pandoc_pipe_grid_tables(new)
    new = convert_pandoc_simple_tables(new)
    new = fix_bold_in_html_cells(new)
    if new != text:
        p.write_text(new, encoding='utf-8')
        print(f'Updated: {p} (img_prefix={prefix})')

def main():
    parser = argparse.ArgumentParser(
        description="Post-process generated Markdown files."
    )
    parser.add_argument(
        "--docs",
        type=Path,
        default=Path("web/docs"),
        help="Directory containing generated .md files (default: %(default)s)",
    )
    args = parser.parse_args()
    docs = args.docs.resolve()

    if not docs.exists():
        print(f'Directory {docs} not found, aborting.', file=sys.stderr)
        sys.exit(1)
    md_files = list(docs.rglob('*.md'))
    for f in md_files:
        process_file(f, docs)

if __name__ == '__main__':
    main()
