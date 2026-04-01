# tex2site — Static website generator from the LaTeX document

tex2site is a tool to create a web site from a LaTex thesis document (in spanish known as "memoria del *Trabajo de Fin de Grado* (TFG)).

It uses  [Pandoc](https://pandoc.org/) to convert LaTeX to Markdown and [MkDocs](https://www.mkdocs.org/) to build the Markdown into a website.

It has custom [transformation steps](#6-how-the-conversion-pipeline-works-files-involved) to improve Pandoc conversion and to customize output for better Mkdocs web site generation.

It also has [some requirements](#8-latex-document-requirements) from the structure and contents of the thesis document to provide a better site for it. 

## 1. Usage

### 1.1 Generate the site

Execute the following command in the folder where `tfg.tex` file is located.

Mac / Linux / Win WSL2
```bash
docker run --rm -u $(id -u):$(id -g) -v $(pwd):/doc codeurjc/tex2site tex2site build
```

Win PowerShell
```bash
docker run --rm -v ${PWD}:/doc codeurjc/tex2site tex2site build
```

The following are generated automatically:

```
<root>/
├── mkdocs/                      # MkDocs project
│   ├── mkdocs.yml               # MkDocs config (customisable)
│   ├── requirements.txt         # Python dependencies for MkDocs
│   ├── docs/                    # Generated Markdown + images (do not edit)
│   └── overrides/               # Jinja2 templates (customisable)
└── site/                        # Final static HTML (do not edit)
```

### 1.2 Custom paths

All paths default to subdirectories of working directory, but can be overridden:

| Option | Default | Description |
|---|---|---|
| `--tex <path>` | current directory | LaTeX project folder |
| `--mkdocs <path>` | `<tex>/mkdocs` | MkDocs project output folder |
| `--site <path>` | `<tex>/site` | Static site output folder |

## 2 Customize the generated site

You can configure how site is generated updating MkDocs project in `mkdocs` folder. 

The following files will be regenerated **always** on each build:
* `mkdocs\docs\**\*.md`
* `mkdocs\docs\img\`

The rest of the files won't be regenerated, so you can customize it.

### `mkdocs/mkdocs.yml` — MkDocs configuration

Defines the navigation structure (chapters, appendices), active plugins and Markdown extensions. 

The `site_name`, `site_author`, `site_description` and `nav:` are created based on document. are  automatically on each build.

Edit the `nav:` section if you want to change page names in the menu or reorder them.

> If you change this information in .tex files and want `mkdocs.yml` just remove it and build the site again.

### `mkdocs/docs/extra.css` — Additional styles

CSS overrides on the Material theme. Institutional colours are applied here as CSS variables, code highlight styles and table styles.

To change the visual palette, edit the variables in the `:root { ... }` block.

### `mkdocs/overrides/main.html` — Jinja2 template

Customises the header and footer of the site. The footer shows the author, year, CC BY-SA 4.0 licence, university and school.

### Start a live reload

To have a preview of the site when you change configuration files you can execute the following command:

Mac / Linux / Win WSL2
```bash
docker run --rm -u $(id -u):$(id -g) -v $(pwd):/doc -p 8000:8000 codeurjc/tex2site tex2site serve
```

Win PowerShell
```bash
docker run --rm -v ${PWD}:/doc -p 8000:8000 codeurjc/tex2site tex2site serve
```

### Execute custom mkdocs commands

For advanced usage you can execute mkdocs commands from tex2site container:

Mac / Linux / Win WSL2
```bash
docker run --rm -u $(id -u):$(id -g) -v $(pwd):/doc -p 8000:8000 codeurjc/tex2site mkdocs ...
```

Win PowerShell
```bash
docker run --rm -v ${PWD}:/doc -p 8000:8000 codeurjc/tex2site mkdocs ...
```

## 3. Document structure and limitations

This section describes what a LaTeX document must satisfy to be correctly processed by `tex2site`. It is based on [template-tfg](https://github.com/codeurjc-students/tfg-template) document to write the final degree thesis document in the [ETSII de la URJC](https://www.urjc.es/etsii).

### 3.1 Required file structure

```
<root>/
├── tfg.tex                      # Main LaTeX file (entry point)
├── config/
│   ├── config.tex               # Global macros: \universidad, \escuelalargo
│   ├── logos/                   # Logo images (must include logoURJC.pdf/.eps/.svg)
│   └── cc/                      # Creative Commons licence icons
├── img/                         # Thesis figures
├── pages/
│   ├── *.tex                    # Chapter files referenced via \input{} in tfg.tex
│   └── appendixes/
│       └── *.tex                # Appendix files (optional)
├── bibliografia.bib             # BibTeX bibliography (required; can be empty)
└── web/
    ├── mkdocs.yml               # MkDocs config (modified in-place on each build)
    └── requirements.txt         # Python dependencies for MkDocs
```

### 3.2 Required metadata macros

The following macros must be defined in `tfg.tex` (via `\newcommand` or `\renewcommand`). If a macro is missing, the corresponding field will appear empty in the generated website.

| Macro | Purpose |
|---|---|
| `\titulotrabajo` | Thesis title (used as `site_name` in MkDocs) |
| `\nombreautor` | Author name |
| `\nombretutor` | Tutor name |
| `\grado` | Degree name |
| `\curso` | Academic year (e.g. `Curso 2024-2025`) |

The following macros must be defined in `config/config.tex` (via `\newcommand`):

| Macro | Purpose | Default if missing |
|---|---|---|
| `\universidad` | University name | `"Universidad Rey Juan Carlos"` |
| `\escuelalargo` | School name (long form) | `"ETSII"` |

### 3.3 Chapter structure in `tfg.tex`

The converter discovers chapters by pairing each `\chapter{}` with the immediately following `\input{}`. Each numbered chapter **must** follow this exact pattern:

```latex
\chapter{Chapter title}
...
\input{pages/filename}
```

A chapter without a matching `\input{}` (or whose content is written inline in `tfg.tex`) will be silently skipped.

**Appendixes** must be preceded by `\appendix`:

```latex
\appendix
\chapter{Appendix title}
\input{pages/appendixes/filename}
```

**Unnumbered front-matter sections** (abstract, acknowledgements) should use `\chapter*{}` before the numbered chapters:

- A `\chapter*{}` whose name contains `agradec` (case-insensitive) → written to `agradecimientos.md`
- Any other `\chapter*{}` (typically `Resumen`) → folded into `index.md`

If no inline `\chapter*{Resumen}` is found, the converter falls back to reading `pages/resumen.tex`.

### 3.4 Images

`\includegraphics` calls in `.tex` files must use paths relative to the chapter file (e.g. `../img/foo.pdf` or `img/foo.pdf`).

### 4. Advanced usage and development

If you want to excute tex2file natively or customize the mkdocs generation from latex, see [development section](DEVELOPMENT.md).

