# TFG-Template – Copilot Instructions

## What this project is

A **LaTeX → MkDocs static website generator** for URJC (Universidad Rey Juan Carlos) undergraduate theses (TFG). The pipeline takes a LaTeX document and produces a fully-rendered website. The PDF is compiled separately with a standard LaTeX compiler.

**Student-facing source lives in LaTeX** (`tfg.tex`, `pages/*.tex`, `img/`).  
**Everything under `web/docs/` and `web/site/` is auto-generated — never edit it by hand.**

---

## Repository layout

```
tfg.tex               # Main LaTeX document (metadata + \input{pages/*})
pages/                # LaTeX chapters (edit content here)
  appendixes/         # Appendix chapters
img/                  # Source images (.pdf, .eps, .png, .svg)
config/               # LaTeX configuration, logos, macros
bibliografia.bib      # BibTeX bibliography

tex2site/
  build_site.sh       # End-to-end build (one command: ./tex2site/build_site.sh)
  tex2md/      # Phase 2 modules
    convert.py        # Phase 2 entry point: LaTeX → standard Markdown
    metadata.py       # Extracts title, author, tutor from tfg.tex
    structure.py      # Parses \chapter / \appendix order
    chapters.py       # Runs Pandoc per chapter, then post-processes Markdown
    images.py         # Converts PDF/EPS → SVG, copies raster images
    process_md.py  # Post-processes .md: links, image paths, tables,
                             #   figure captions, fenced-div removal
  md2mkdocs/           # Phase 3 modules
    md2mkdocs.py     # Reads .metadata.json, writes metadata + nav
                      #   into web/mkdocs.yml
  filters/            # Pandoc Lua filters
    collect_labels.lua   # Pass 1: collects \label{} into .labels.json
    resolve_refs.lua     # Pass 2: replaces \ref{} with MD links
    cleanup.lua          # Removes non-web LaTeX environments

web/
  mkdocs.yml          # MkDocs config (plugins, nav, theme) – auto-updated at build
  requirements.txt    # Python deps (mkdocs, mkdocs-material, mkdocs-bibtex)
  extra.css           # Theme overrides (URJC colors, tables, code)
  overrides/
    main.html         # Custom Jinja2 template (header/footer)
  docs/               # AUTO-GENERATED Markdown (do not edit)
  site/               # AUTO-GENERATED HTML (do not edit)
```

---

## Build commands

```bash
# Full build (LaTeX → MD → HTML)
./tex2site/build_site.sh

# Full build + local dev server (auto-reload)
./tex2site/build_site.sh --serve

# Only conversion step (no MkDocs build)
python3 tex2site/tex2md/tex2md.py

# Only Markdown post-processing
python3 tex2site/tex2md/process_md.py
```

The build script runs three phases:
1. **Tooling setup** — verifies system deps (`pandoc ≥ 3.0`, `pdf2svg`, `gs`, `python3`), creates `web/.venv/`, installs `web/requirements.txt`
2. **Convert** — runs `tex2site/tex2md/tex2md.py` (metadata → structure → images → Pandoc passes → Markdown post-processing → saves `web/docs/.metadata.json`)
3. **Generate site** — runs `md2mkdocs/md2mkdocs.py` (configures `web/mkdocs.yml`), then `mkdocs build`

---

## Conversion pipeline (Phase 2)

**Two-pass Pandoc approach** (required for cross-references):

| Pass | Input | Filter | Output |
|------|-------|--------|--------|
| 1 (collect) | `tfg.tex` (full doc) | `collect_labels.lua` | `web/docs/.labels.json` |
| 2 (convert) | each `pages/*.tex` | `cleanup.lua` + `resolve_refs.lua` | `web/docs/*.md` |

The `CHAPTER_MAP` env var (`"0:index,1:introduccion,..."`) is passed to Lua filters so they know which chapter maps to which output file.

After Pandoc, `process_md.py` runs on every generated `.md`.

---

## Metadata dictionary

`metadata.py` → `load()` returns a dict with these English keys:

| Key | LaTeX macro |
|-----|-------------|
| `title` | `\titulotrabajo` |
| `author` | `\nombreautor` |
| `tutor` | `\nombretutor` |
| `degree` | `\grado` |
| `academic_year` | `\curso` |
| `university` | `\universidad` (config.tex) |
| `school` | `\escuelalargo` (config.tex) |
| `year` | last 4-digit year in `academic_year` |

---

## Markdown post-processor (`process_md.py`)

Runs on every generated `web/docs/*.md` after Pandoc. Key transformations:

- **`fix_text()`** – Normalises `[text]{.underline}` links; rewrites `/img/` paths to relative `../img/`; converts Pandoc image attribute blocks to `<figure>/<figcaption>`
- **`fix_markdown_widths()`** – Converts `width="0.5\linewidth"` → `width="50%"`
- **`strip_pandoc_divs()`** – Removes `::: {#id}`, `::: multicols`, `:::` fence lines (MkDocs renders them as literal text)
- **`dedent_pandoc_tables()`** – Removes two-space indent Pandoc puts on tables
- **`convert_pandoc_grid_tables()`** – Converts aligned-column tables → HTML `<table>` blocks
- **`fix_bold_in_html_cells()`** – Converts `**text**` inside `<th>`/`<td>` to `<strong>` (MkDocs doesn't process Markdown inside raw HTML)

---

## Key conventions

- **LaTeX source** is the single source of truth. All Markdown and HTML is derived.
- **Image conversion**: PDF/EPS are converted to SVG via `pdf2svg`. Output goes to `web/docs/img/`.
- **Bibliography**: uses `mkdocs-bibtex` plugin with `bibliografia.bib`. Citation keys in Markdown are `[@key]`; missing keys produce `WARNING: Citing unknown reference key` — these are non-fatal.
- **Cross-references**: `\ref{fig:name}` becomes `[Fig 3.2](chapter.md#fig-name)` via the Lua filters. Unresolved refs are marked with class `ref-unresolved`.
- **Math**: MathJax is enabled. LaTeX math environments pass through Pandoc and render in browser.
- **Code blocks**: rendered with superfences + highlight.js.
- **Do not** add features to `web/docs/` or `web/site/`—changes will be overwritten on next build. Put logic in `tex2site/tex2md/`.
- **Language**: all code, comments and pipeline messages are in English.

---

## MkDocs configuration

- **Theme**: Material for MkDocs (`material`)  
- **Plugins**: `search` (lang: es), `bibtex`  
- **Features**: `navigation.expand`, `navigation.top`, `toc.integrate`, `search.highlight`, `content.code.copy`  
- **Extra CSS**: `web/extra.css` — URJC brand colours, table styles, figure captions  
- **Custom template**: `web/overrides/main.html` — injects tutor/institution in header/footer; uses `config.extra.tfg_year`, `config.extra.tfg_institution`, `config.extra.tfg_school`
- **Config file auto-updated** at build time by `tex2site/md2mkdocs/md2mkdocs.py` (site_name, author, nav, extra vars)

---

## Customising a thesis

1. Edit metadata in `tfg.tex` (`\nombreautor`, `\titulotrabajo`, `\nombretutor`, etc.)
2. Write content in `pages/*.tex` and `pages/appendixes/*.tex`
3. Add images to `img/`
4. Update `bibliografia.bib`
5. Run `./tex2site/build_site.sh` — the entire website regenerates automatically
