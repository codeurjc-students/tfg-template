# tex2site advanced usage and development

tex2file is implemented in python with a basic launch bash script.

It is designed to be executed in linux and mac, but surely it can work in windows with minimal adjustements. 

## 1. Requirements

tex2site requires the following tools:

| Tool | Min. version | Role |
|---|---|---|
| **Pandoc** | ≥ 3.0 | Converts `.tex` → `.md`; runs Lua filters |
| **pdf2svg** | any | Converts vector PDF images → SVG |
| **Ghostscript** | any | Converts EPS images → PDF (before pdf2svg) |
| **Python** | ≥ 3.8 | Postprocessing and MkDocs runtime |

On Ubuntu / Debian:

```bash
sudo apt update
sudo apt install pandoc pdf2svg ghostscript python3
```

On macOS:

```bash
brew install pandoc pdf2svg ghostscript python3
```

## 2. Usage

### Build

```bash
./tex2site/tex2site.sh
```

### Build + local server (development)

```bash
./tex2site/tex2site.sh serve
```
Open site at `http://127.0.0.1:8000` with live reload.

### Server only (without regenerating, requires a prior build)

When you have already run `./tex2site/tex2site.sh` and only want to reload the web without regenerating it (e.g. after modifying CSS or HTML only):

```bash
source mkdocs/.venv/bin/activate
mkdocs serve --config-file mkdocs/mkdocs.yml
```

#### Conversion only (without MkDocs)

Generates the `.md` files in `web/docs/` and converts images, but does not build the HTML site:

```bash
python3 tex2site/tex2md/tex2md.py
```

#### Clean generated artefacts

```bash
rm -rf mkdocs/ site/
```

## 3. Pipeline to generate a site from latex document

tex2site makes the following steps:
1. Verifies system dependencies are installed (pandoc, pdf2svg, ghostscript, python3)
2. Creates a Python virtual environment at `mkdocs/.venv` (if it doesn't exist)
3. Automatically installs all Python dependencies (`mkdocs`, `mkdocs-material`, `mkdocs-bibtex`)
4. Converts `.tex` files to `.md`
5. Converts images (PDF/EPS → SVG)
6. Generates the website at `site/`

⏱️ **The first build is slow** (~2-5 minutes) due to the LaTeX → Markdown conversion. Subsequent builds are faster.

## 4. How the conversion pipeline works (files involved)

Each run of `./tex2site/tex2site.sh` orchestrates the conversion in three phases:

### Phase 1 — Tooling setup
- Script: `tex2site/tex2site.sh`
- Checks for: `pandoc`, `pdf2svg`, `gs`, `python3`.
- Creates/activates the Python virtual environment at `web/.venv/`.
- Installs Python dependencies from `web/requirements.txt`.

### Phase 2 — Convert LaTeX → standard Markdown
- Script: `tex2site/tex2md/tex2md.py` (orchestrates the sub-modules below)
- **Metadata extraction** (`tex2site/tex2md/metadata.py`): reads `tfg.tex` and `config/config.tex`; returns a dict with `title`, `author`, `tutor`, `degree`, `academic_year`, `university`, `school`, `year`.
- **Structure parsing** (`tex2site/tex2md/structure.py`): reads `tfg.tex` to discover chapters, appendices, and inline sections; builds the `CHAPTER_MAP` passed to Lua filters.
- **Image conversion** (`tex2site/tex2md/images.py`): converts `img/*`, `config/logos/*`, `config/cc/*` to `web/docs/img/` — PDF/EPS → SVG via `pdf2svg`/`gs`; raster files copied directly.
- **Pandoc pass 1 — label collection** (`tex2site/tex2md/chapters.py` → `tex2site/tex2md/filters/collect_labels.lua`): runs Pandoc over the full `tfg.tex`; collects all `\label{}` occurrences (mapping `label → {file, anchor, type, number, display}`) into a temporary file consumed by pass 2.
- **Pandoc pass 2 — chapter conversion** (`tex2site/tex2md/chapters.py` ← `tex2site/tex2md/filters/cleanup.lua` + `tex2site/tex2md/filters/resolve_refs.lua`): converts each `pages/*.tex` and `pages/appendixes/*.tex` to `web/docs/*.md` / `web/docs/appendixes/*.md`.
- **Markdown post-processing** (`tex2site/tex2md/process_md.py`): normalises links, image paths, tables, fenced divs, and figure captions in all generated `.md` files.

### Phase 3 — Generate MkDocs site
- **MkDocs configuration** (`tex2site/md2mkdocs/md2mkdocs.py`): uses the metadata produced in phase 2 to rewrite `web/mkdocs.yml` (`site_name`, `site_author`, `extra:`, `nav:`).
- **Site build**: `mkdocs build --config-file web/mkdocs.yml` → `web/site/` (complete static site).

Quick reference (main files):

- Orchestrator: `tex2site/tex2site.sh` → calls `tex2site/tex2md/tex2md.py` then MkDocs
- Phase 2 entry point: `tex2site/tex2md/tex2md.py` + package `tex2site/tex2md/` (`metadata.py`, `structure.py`, `images.py`, `chapters.py`, `process_md.py`)
- Phase 3 entry point: `tex2site/md2mkdocs/md2mkdocs.py`, `mkdocs build`
- Lua filters: `tex2site/tex2md/filters/collect_labels.lua`, `tex2site/tex2md/filters/resolve_refs.lua`, `tex2site/tex2md/filters/cleanup.lua`
- LaTeX sources: `tfg.tex`, `pages/*.tex`, `pages/appendixes/*.tex`, `config/*.tex`
- Resources: `img/*`, `config/logos/*`, `config/cc/*`, `bibliografia.bib`
- Generated artefacts: `web/docs/*.md`, `web/docs/img/*`, `web/site/`