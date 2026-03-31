"""Parse the structure of tfg.tex: inline sections, chapters, appendixes."""

import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InlineSection:
    name: str           # e.g. "Agradecimientos"
    key: str            # lowercase key e.g. "agradecimientos"
    latex_body: str     # raw LaTeX content
    md_file: str        # target .md stem e.g. "agradecimientos" or "index"


@dataclass
class Chapter:
    title: str
    tex_file: str       # relative path from repo root e.g. "pages/introduccion.tex"
    is_appendix: bool = False


@dataclass
class DocStructure:
    inline_sections: list[InlineSection] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)
    appendixes: list[Chapter] = field(default_factory=list)
    appendices_label: str = "Appendices"

    def nav_labels(self) -> dict:
        """Return navigation section labels derived from the LaTeX structure."""
        home = "Inicio"
        ack = next(
            (s.name for s in self.inline_sections if "agradec" in s.key),
            "Acknowledgements",
        )
        return {
            "home": home,
            "acknowledgements": ack,
            "chapters": "Capítulos",
            "appendices": self.appendices_label,
        }

    def chapter_map(self) -> dict[int, str]:
        """Build the index → md_stem mapping used by collect_labels.lua.

        The collect_labels Lua filter processes the entire document as a
        single AST stream. CHAPTER_MAP tells it which output .md file each
        chapter belongs to so that every label is stored with the correct
        target filename.

        Index 0 is a sentinel for the document preamble — content that
        appears before the first \\chapter{} (cover page, list of figures,
        etc.). There is no chapter 0 in the LaTeX source, but labels defined
        in preamble environments still need a valid output file to reference.

        Inline sections (Resumen, Agradecimientos) occupy positions 1…n in
        the same sequence they appear in tfg.tex so that heading counters in
        the Lua filter stay in sync with the LaTeX source order.
        """
        mapping: dict[int, str] = {0: "index"}
        pos = 1
        for sec in self.inline_sections:
            mapping[pos] = sec.md_file
            pos += 1
        for chap in self.chapters:
            mapping[pos] = Path(chap.tex_file).stem
            pos += 1
        for app in self.appendixes:
            mapping[pos] = "appendixes/" + Path(app.tex_file).stem
            pos += 1
        return mapping

    def chapter_map_env(self) -> str:
        """Return the CHAPTER_MAP string for the Lua filter env var."""
        return ",".join(f"{k}:{v}" for k, v in self.chapter_map().items())


def parse(repo_root: Path) -> DocStructure:
    """Parse tfg.tex and return the full document structure."""
    tex_main = (repo_root / "tfg.tex").read_text(encoding="utf-8")

    # Match unnumbered chapters (\chapter*{}): abstract (Resumen),
    # acknowledgements (Agradecimientos), and similar front-matter sections.
    # These are special in the URJC template: they appear in the document but
    # don't increment chapter counters and don't show in \tableofcontents.
    # They must be handled separately because they contain thesis content that
    # belongs on the website, but shouldn't be numbered or filed under a chapter.
    inline_re = re.compile(
        r'\\chapter\*\{([^}]+)\}(.*?)(?=\\chapter(?:[^*\w]|\*)|\Z)',
        re.DOTALL,
    )
    inline_sections: list[InlineSection] = []
    for m in inline_re.finditer(tex_main):
        name = m.group(1).strip()
        body = m.group(2).strip()
        # Strip PDF-only layout commands that survive the regex extraction
        # but have no web equivalent. \afterpage{} defers content to the next
        # PDF page break; \mbox{}\bigskip adds vertical whitespace. Without
        # stripping them they would appear as orphaned LaTeX command strings
        # when the inline body is later passed through pandoc.
        body = re.sub(r'\\afterpage\{[^}]*\}', '', body)
        body = re.sub(r'\\mbox\{\}\s*\\bigskip', '', body)
        body = re.sub(r'\\mbox\{\}', '', body)
        body = body.strip()
        key = name.lower()
        # Acknowledgements get their own dedicated page (agradecimientos.md).
        # All other inline sections — typically only the abstract (Resumen)
        # — are folded into index.md alongside the cover metadata block. This
        # mirrors the URJC template layout where the first web page shows
        # title, author info, and abstract together.
        md_file = "agradecimientos" if "agradec" in key else "index"
        inline_sections.append(InlineSection(name=name, key=key, latex_body=body, md_file=md_file))

    # ---- Chapters and appendixes (\chapter{} + \input{}) ---------------
    appendix_pos = tex_main.find(r'\appendix')
    main_content = tex_main[:appendix_pos] if appendix_pos >= 0 else tex_main
    appendix_content = tex_main[appendix_pos:] if appendix_pos >= 0 else ""

    chapter_re = re.compile(r'\\chapter\{([^}]+)\}.*?\\input\{([^}]+)\}', re.DOTALL)

    def _parse_chapters(content: str, is_appendix: bool) -> list[Chapter]:
        chapters = []
        for m in chapter_re.finditer(content):
            title = m.group(1).strip()
            tex_file = m.group(2).strip()
            # LaTeX \input{} accepts paths with or without the .tex extension.
            # We normalise to always include it so downstream code can use
            # tex_file directly as a filesystem path without guessing.
            if not tex_file.endswith('.tex'):
                tex_file += '.tex'
            chapters.append(Chapter(title=title, tex_file=tex_file, is_appendix=is_appendix))
        return chapters

    chapters = _parse_chapters(main_content, is_appendix=False)
    appendixes = _parse_chapters(appendix_content, is_appendix=True)

    # Extract the display label the student chose for the appendices section
    # in the LaTeX ToC. \addcontentsline{toc}{chapter}{Anexos} is the standard
    # way to add a custom entry to the Table of Contents in the URJC template.
    # We reuse this string as the MkDocs nav section label so the website
    # navigation matches the PDF chapter list exactly instead of using a
    # hardcoded English 'Appendices'.
    appendices_label = "Appendices"
    if appendix_content:
        m = re.search(r'\\addcontentsline\{toc\}\{chapter\}\{([^}]+)\}', appendix_content)
        if m:
            appendices_label = m.group(1).strip()

    return DocStructure(
        inline_sections=inline_sections,
        chapters=chapters,
        appendixes=appendixes,
        appendices_label=appendices_label,
    )
