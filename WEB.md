# WEB.md — Static website generator from the LaTeX document

Tool to automatically convert this TFG (Trabajo Fin de Grado) template into a navigable static website.

The process is fully reproducible: a single command transforms the source files (`.tex`) into a website.

Uses Pandoc to convert LaTeX to Markdown and MkDocs to build the Markdown into a website.

## 1. Requirements

The conversion requires the following tools:

| Tool | Min. version | Role |
|---|---|---|
| **Pandoc** | ≥ 3.0 | Converts `.tex` → `.md`; runs Lua filters |
| **pdf2svg** | any | Converts vector PDF images → SVG |
| **Ghostscript** | any | Converts EPS images → PDF (before pdf2svg) |
| **Python** | ≥ 3.8 | MkDocs runtime |

On Ubuntu / Debian:

```bash
sudo apt update
sudo apt install pandoc pdf2svg ghostscript python3
```

On macOS:

```bash
brew install pandoc pdf2svg ghostscript python3
```

## 2. Building the website

### Full build (standard usage)

```bash
./tex2site/build_site.sh
```

The script automates **everything**:
1. Verifies system dependencies are installed (pandoc, pdf2svg, ghostscript, python3)
2. Creates a Python virtual environment at `web/.venv` (if it doesn't exist)
3. Automatically installs all Python dependencies (`mkdocs`, `mkdocs-material`, `mkdocs-bibtex`)
4. Converts `.tex` files to `.md`
5. Converts images (PDF/EPS → SVG)
6. Generates the website at `web/site/`

⏱️ **The first build is slow** (~2-5 minutes) due to the LaTeX → Markdown conversion. Subsequent builds are faster.

### Build + local server (development)

```bash
./tex2site/build_site.sh --serve
``` at `http://127.0.0.1:8000` with live reload.

## 3. Configuration of the generated website

All website configuration files live in `web/`.

### `web/config.yaml` — Colour palette, logo and features

Controls the visual identity of the site: institutional colours (extracted from `config/config.tex`), logo path, fonts and Material theme navigation features.

```yaml
colors:
  primary: "0558AE"     # pblue — primary colour for headers and links
  primary_dark: "0A3069" # pdarkblue — dark variant
  accent: "CF222E"      # pred — accent colour

logo:
  path: "img/logoURJC.svg"   # relative to web/docs/

features:
  - navigation.tabs          # top-level tabs
  - navigation.sections      # sections in sidebar
  - content.code.copy        # copy-code button
  # … see the file for the full list
```

### `web/mkdocs.yml` — MkDocs configuration

Defines the navigation structure (chapters, appendices), active plugins and Markdown extensions. The `site_name`, `site_author` and `site_description` are overwritten automatically on each build from the macros in `tfg.tex`.

Edit the `nav:` section if you want to change page names in the menu or reorder them.

### `web/extra.css` — Additional styles

CSS overrides on the Material theme. Institutional colours are applied here as CSS variables, code highlight styles (Java by default, same as in LaTeX) and table styles.

To change the visual palette, edit the variables in the `:root { ... }` block.

### `web/overrides/main.html` — Jinja2 template

Customises the header and footer of the site. The footer shows the author, year, CC BY-SA 4.0 licence, university and school. Values are injected automatically from `tfg.tex`.

---

## 4. Known limitations

### Sub-figures (`\subfigure`, `\subcaptionbox`)

Pandoc does not assign an anchor to sub-figures. A `\ref{subfig:x}` will generate a link to the file without an anchor (navigates to the top of the page) instead of to the specific sub-figure. Solution: consolidate sub-figures into a single figure with a unified caption, or add logic to the `collect_labels.lua` filter.

### Multi-page PDFs in `img/`

`pdf2svg` converts only the **first page** of a multi-page PDF. If `img/` contains a PDF with several pages of which more than one is needed, extract them beforehand with Ghostscript:

```bash
# Extract page N from a multi-page PDF
gs -dBATCH -dNOPAUSE -dSAFER \
   -sDEVICE=pdfwrite \
   -dFirstPage=N -dLastPage=N \
   -sOutputFile=img/figure-page-N.pdf \
   img/document.pdf
```

### Heavily customised LaTeX environments

Environments defined in `config/config.tex` that have no standard Pandoc equivalent (e.g. `algorithm`, `algorithmic`) may appear as plain text blocks without formatting. To improve their rendering, extend `cleanup.lua` with additional rules.

### Figure/table numbering

Numbering is calculated from the order of appearance in the AST Pandoc generates from `tfg.tex`. If the LaTeX document structure uses custom counters (`\setcounter`), the number on the web may differ from the PDF. The `cleanup.lua` filter removes `\setcounter` to avoid confusing Pandoc.

## 5. Advanced usage

### Commands

#### Server only (without regenerating, requires a prior build)

When you have already run `./tex2site/build_site.sh` and only want to reload the web without regenerating it (e.g. after modifying CSS or HTML only):

```bash
source web/.venv/bin/activate
mkdocs serve --config-file web/mkdocs.yml
```

#### Conversion only (without MkDocs)

Generates the `.md` files in `web/docs/` and converts images, but does not build the HTML site:

```bash
python3 tex2site/tex2md/tex2md.py
```

#### Clean generated artefacts

```bash
rm -rf web/docs/ web/site/ web/.venv/
```

Files in `web/docs/` are auto-generated; it is recommended to add them to `.gitignore`.

---

## 6. How the conversion pipeline works (files involved)

Each run of `./tex2site/build_site.sh` orchestrates the conversion in three phases:

### Phase 1 — Tooling setup
- Script: `tex2site/build_site.sh`
- Checks for: `pandoc`, `pdf2svg`, `gs`, `python3`.
- Creates/activates the Python virtual environment at `web/.venv/`.
- Installs Python dependencies from `web/requirements.txt`.

### Phase 2 — Convert LaTeX → standard Markdown
- Script: `tex2site/tex2md/tex2md.py` (orchestrates the sub-modules below)
- **Metadata extraction** (`tex2site/tex2md/metadata.py`): reads `tfg.tex` and `config/config.tex`; returns a dict with `title`, `author`, `tutor`, `degree`, `academic_year`, `university`, `school`, `year`.
- **Structure parsing** (`tex2site/tex2md/structure.py`): reads `tfg.tex` to discover chapters, appendices, and inline sections; builds the `CHAPTER_MAP` passed to Lua filters.
- **Image conversion** (`tex2site/tex2md/images.py`): converts `img/*`, `config/logos/*`, `config/cc/*` to `web/docs/img/` — PDF/EPS → SVG via `pdf2svg`/`gs`; raster files copied directly.
- **Pandoc pass 1 — label collection** (`tex2site/tex2md/chapters.py` → `tex2site/tex2md/filters/collect_labels.lua`): runs Pandoc over the full `tfg.tex`; produces `web/docs/.labels.json` (mapping `label → {file, anchor, type, number, display}`).
- **Pandoc pass 2 — chapter conversion** (`tex2site/tex2md/chapters.py` ← `tex2site/tex2md/filters/cleanup.lua` + `tex2site/tex2md/filters/resolve_refs.lua`): converts each `pages/*.tex` and `pages/appendixes/*.tex` to `web/docs/*.md` / `web/docs/appendixes/*.md`.
- **Markdown post-processing** (`tex2site/tex2md/process_md.py`): normalises links, image paths, tables, fenced divs, and figure captions in all generated `.md` files.
- **Output**: saves `web/docs/.metadata.json` (metadata + chapter list) for use in phase 3.

### Phase 3 — Generate MkDocs site
- **MkDocs configuration** (`tex2site/md2mkdocs/md2mkdocs.py`): reads `web/docs/.metadata.json`; rewrites `web/mkdocs.yml` (`site_name`, `site_author`, `extra:`, `nav:`).
- **Site build**: `mkdocs build --config-file web/mkdocs.yml` → `web/site/` (complete static site).

Quick reference (main files):

- Orchestrator: `tex2site/build_site.sh` → calls `tex2site/tex2md/tex2md.py` then MkDocs
- Phase 2 entry point: `tex2site/tex2md/tex2md.py` + package `tex2site/tex2md/` (`metadata.py`, `structure.py`, `images.py`, `chapters.py`, `process_md.py`)
- Phase 3 entry point: `tex2site/md2mkdocs/md2mkdocs.py`, `mkdocs build`
- Lua filters: `tex2site/tex2md/filters/collect_labels.lua`, `tex2site/tex2md/filters/resolve_refs.lua`, `tex2site/tex2md/filters/cleanup.lua`
- LaTeX sources: `tfg.tex`, `pages/*.tex`, `pages/appendixes/*.tex`, `config/*.tex`
- Resources: `img/*`, `config/logos/*`, `config/cc/*`, `bibliografia.bib`
- Generated artefacts: `web/docs/*.md`, `web/docs/.labels.json`, `web/docs/.metadata.json`, `web/docs/img/*`, `web/site/`

---

## 7. Troubleshooting

### Build takes a long time

The **first build is slow (~2-5 minutes)** because:
- Pandoc converts the entire LaTeX document to Markdown (intensive process)
- `mkdocs-material` and its dependencies are downloaded and installed
- All images are converted (PDF/EPS → SVG)

Subsequent builds are faster (only regenerates changes).

### `pdf2svg: command not found`

`pdf2svg` is an independent package; it is not included in `poppler-utils` or other tools. Install it explicitly:

**Ubuntu / Debian:**
```bash
apt install pdf2svg
```

**macOS:**
```bash
brew install pdf2svg
```

Verify it works:
```bash
pdf2svg --version
```

### `pandoc: command not found`

Install Pandoc from https://pandoc.org/installing.html or use:

**Ubuntu / Debian:**
```bash
apt install pandoc
```

**macOS:**
```bash
brew install pandoc
```

### `gs: command not found` (Ghostscript)

Install Ghostscript:

**Ubuntu / Debian:**
```bash
apt install ghostscript
```

**macOS:**
```bash
brew install ghostscript
```

### Script failed with a Python error

If `build_site.sh` creates a venv but fails during package installation:

```bash
rm -rf web/.venv
./tex2site/build_site.sh
```

The script will recreate the venv cleanly.


```bash
sudo apt update
sudo apt install pandoc pdf2svg ghostscript python3
```

En macOS:

```bash
brew install pandoc pdf2svg ghostscript python3
```

## 2. Construcción del sitio web

### Build completo (uso habitual)

```bash
./tex2site/build_site.sh
```

El script automatiza **TODO** el proceso:
1. Verifica que las dependencias del sistema estén instaladas (pandoc, pdf2svg, ghostscript, python3)
2. Crea un entorno virtual Python en `web/.venv` (si no existe)
3. Instala automáticamente todas las dependencias Python (`mkdocs`, `mkdocs-material`, `mkdocs-bibtex`)
4. Convierte los ficheros `.tex` a `.md`
5. Convierte las imágenes (PDF/EPS → SVG)
6. Genera el sitio web en `web/site/`

⏱️ **El primer build es lento** (~2-5 minutos) debido a la conversión LaTeX → Markdown. Los builds posteriores son más rápidos.

### Build + servidor local (desarrollo)

```bash
./tex2site/build_site.sh --serve
```

Después de generar el sitio, arranca un servidor local en `http://127.0.0.1:8000` con recarga automática.

## 3. Configuración del sitio web generado

Todos los ficheros de configuración de la web residen en `web/`.

### `web/config.yaml` — Paleta de colores, logo y features

Controla la identidad visual del sitio: colores institucionales (extraídos de `config/config.tex`), ruta del logo, fuentes y features de navegación del tema Material.

```yaml
colors:
  primary: "0558AE"     # pblue — color principal de cabeceras y links
  primary_dark: "0A3069" # pdarkblue — variante oscura
  accent: "CF222E"      # pred — color de énfasis

logo:
  path: "img/logoURJC.svg"   # relativo a web/docs/

features:
  - navigation.tabs          # pestañas superiores
  - navigation.sections      # secciones en sidebar
  - content.code.copy        # botón copiar código
  # … ver el fichero para la lista completa
```

### `web/mkdocs.yml` — Configuración de MkDocs

Define la estructura de navegación (capítulos, anexos), los plugins activos y las extensiones Markdown. El `site_name`, `site_author` y `site_description` se sobreescriben automáticamente en cada build a partir de los macros de `tfg.tex`.

Editar la sección `nav:` si se quieren cambiar los nombres de las páginas en el menú o reordenarlas.

### `web/extra.css` — Estilos adicionales

Overrides CSS sobre el tema Material. Aquí se aplican los colores institucionales como variables CSS, los estilos de resaltado de código (Java por defecto, igual que en LaTeX) y los estilos de tabla.

Para cambiar la paleta visual, editar las variables en el bloque `:root { ... }`.

### `web/overrides/main.html` — Plantilla Jinja2

Personaliza la cabecera y el pie de página del sitio. El pie muestra el autor, año, licencia CC BY-SA 4.0, universidad y escuela. Los valores se inyectan automáticamente desde `tfg.tex`.

---

## 4. Limitaciones conocidas

### Subfiguras (`\subfigure`, `\subcaptionbox`)

Pandoc no asigna identificador de ancla a las subfiguras. Un `\ref{subfig:x}` generará un link al fichero sin ancla (navegará al inicio de la página) en lugar de a la subfigura concreta. Solución: consolidar las subfiguras en una única figura con caption unificado, o añadir lógica al filtro `collect_labels.lua`.

### PDFs multi-página en `img/`

`pdf2svg` convierte solo la **primera página** de un PDF multi-página. Si `img/` contiene un PDF con varias páginas de las cuales se usan varias, extraerlas previamente con Ghostscript:

```bash
# Extraer página N de un PDF multi-página
gs -dBATCH -dNOPAUSE -dSAFER \
   -sDEVICE=pdfwrite \
   -dFirstPage=N -dLastPage=N \
   -sOutputFile=img/figura-pag-N.pdf \
   img/documento.pdf
```

### Entornos LaTeX muy personalizados

Entornos definidos en `config/config.tex` que no tienen equivalente estándar en Pandoc (p.ej., `algorithm`, `algorithmic`) pueden aparecer como bloques de texto plano sin formato. Para mejorar su renderizado, extender `cleanup.lua` con reglas adicionales.

### Numeración de figuras/tablas

La numeración se calcula a partir del orden de aparición en el AST que Pandoc genera desde `tfg.tex`. Si la estructura del documento LaTeX usa contadores personalizados (`\setcounter`), el número en la web puede diferir del PDF. El filtro `cleanup.lua` elimina los `\setcounter` para no confundir a Pandoc.

## 5. Uso avanzado

### Comandos

#### Solo servidor (sin regenerar, requiere build previo)

Cuando ya has ejecutado `./tex2site/build_site.sh` y solo quieres recargar la web sin regenerarla (p. ej., tras modificar solo CSS o HTML):

```bash
source web/.venv/bin/activate
mkdocs serve --config-file web/mkdocs.yml
```

#### Solo conversión (sin MkDocs)

Genera los `.md` en `web/docs/` y convierte las imágenes, pero no construye el sitio HTML:

```bash
python3 tex2site/tex2md/tex2md.py
```

#### Limpiar artefactos generados

```bash
rm -rf web/docs/ web/site/ web/.venv/
```

Los ficheros en `web/docs/` son auto-generados; se recomienda añadirlos a `.gitignore`.

---

## 6. Cómo funciona el pipeline de conversión (ficheros implicados)

Cada ejecución de `./tex2site/build_site.sh` orquesta la conversión en varias fases; a continuación se describen las fases y los ficheros o módulos implicados en cada una:

- 0) Verificación de dependencias
  - Script: `tex2site/build_site.sh`
  - Comprueba la presencia de: `pandoc`, `pdf2svg`, `gs`, `python3`.

- 1) Entorno Python y dependencias
  - Ficheros: `web/.venv/` (virtualenv), `web/requirements.txt`.
  - Script: `tex2site/build_site.sh` crea/activa el venv y ejecuta `pip install -r web/requirements.txt`.

- 2) Extracción de metadatos
  - Fuente: `tfg.tex`, `config/config.tex`, `config/portada.tex`.
  - Módulo: `tex2site/tex2md/metadata.py` (invocado por `tex2site/tex2md/tex2md.py`).
  - Salidas: valores inyectados en `web/mkdocs.yml` (`site_name`, `site_author`, `site_description`) y en el front matter YAML de cada `.md` generado.

- 3) Conversión de imágenes
  - Entradas: `img/*`, `config/logos/*`, `config/cc/*`.
  - Módulo: `tex2site/tex2md/images.py` (llamado por `tex2site/tex2md/tex2md.py`) — usa `pdf2svg` y `gs`.
  - Salida: `web/docs/img/*.svg` (copias o conversiones).

- 4) Pasada 1 — recolección global de etiquetas
  - Entrada: `tfg.tex` (Pandoc resuelve los `\input{}` internamente).
  - Filtro Lua: `tex2site/tex2md/filters/collect_labels.lua` (recorre el AST completo).
  - Producción: `web/docs/.labels.json` (mapa `label → {file, anchor, type, number, display}`).
  - Nota: `tex2site/tex2md/structure.py` construye `CHAPTER_MAP` y se pasa como variable de entorno al filtro.

- 5) Pasada 2 — conversión por capítulo y resolución de referencias
  - Entradas: los ficheros de capítulo listados por `tex2site/tex2md/structure.py`, típicamente `pages/*.tex` y `pages/appendixes/*.tex`.
  - Filtros Lua ejecutados por capítulo: `tex2site/tex2md/filters/cleanup.lua` y `tex2site/tex2md/filters/resolve_refs.lua`.
    - `cleanup.lua` limpia entornos LaTeX no aplicables en la web.
    - `resolve_refs.lua` carga `web/docs/.labels.json` y reemplaza `\ref{...}` por enlaces Markdown `[...] (fichero.md#ancla)`.
  - Módulo orchestration: `tex2site/tex2md/chapters.py` (invocado por `tex2site/tex2md/tex2md.py`) crea los `.md` en `web/docs/`.
  - Salidas por capítulo: `web/docs/<capitulo>.md`, `web/docs/appendixes/<anexo>.md`.

- 6) Actualizar `mkdocs.yml` / navegación
  - Módulo: `tex2site/md2mkdocs/md2mkdocs.py` (invocado por `tex2site/build_site.sh`).
  - Ficheros afectados: `web/mkdocs.yml` (bloque `site_name`, `site_author`, `extra:` y `nav:`).

- 7) Generación del sitio HTML con MkDocs
  - Comando: `${VENV_DIR}/bin/mkdocs build --config-file web/mkdocs.yml`
  - Entrada: `web/docs/` (Markdown generados) + `web/mkdocs.yml` + `web/overrides/` + `web/extra.css`.
  - Salida: `web/site/` (sitio estático completo).

Resumen rápido (ficheros principales):

- Orquestador: `tex2site/build_site.sh` → invoca `tex2site/tex2md/tex2md.py`.
- Conversión/logic Python: `tex2site/tex2md/tex2md.py` y paquete `tex2site/tex2md/` (`metadata.py`, `structure.py`, `images.py`, `chapters.py`, `process_md.py`).
- Filtros Lua: `tex2site/tex2md/filters/collect_labels.lua`, `tex2site/tex2md/filters/resolve_refs.lua`, `tex2site/tex2md/filters/cleanup.lua`.
- Fuentes LaTeX: `tfg.tex`, `pages/*.tex`, `pages/appendixes/*.tex`, `config/*.tex`.
- Recursos: `img/*`, `config/logos/*`, `config/cc/*`, `bibliografia.bib`.
- Artefactos generados: `web/docs/*.md`, `web/docs/.labels.json`, `web/docs/img/*`, `web/site/`.

Esta estructura permite que la numeración y las referencias sean coherentes (pasada 1), y que cada capítulo se convierta y postprocese de forma independiente (pasada 2), mientras que la generación final del sitio la realiza MkDocs a partir de `web/docs/`.

---

## 7. Troubleshooting

### El build toma mucho tiempo

El **primer build es lento (~2-5 minutos)** porque:
- Pandoc convierte todo el documento LaTeX a Markdown (proceso intensivo)
- Se descarga e instala `mkdocs-material` y sus dependencias
- Se convierten todas las imágenes (PDF/EPS → SVG)

Los builds posteriores son más rápidos (solo regenera cambios).

### `pdf2svg: command not found`

`pdf2svg` es un paquete independiente; no viene incluido en `poppler-utils` ni en otras herramientas. Instálalo explícitamente:

**Ubuntu / Debian:**
```bash
apt install pdf2svg
```

**macOS:**
```bash
brew install pdf2svg
```

Verifica después que funciona:
```bash
pdf2svg --version
```

### `pandoc: command not found`

Instala Pandoc desde https://pandoc.org/installing.html o usa:

**Ubuntu / Debian:**
```bash
apt install pandoc
```

**macOS:**
```bash
brew install pandoc
```

### `gs: command not found` (Ghostscript)

Instala Ghostscript:

**Ubuntu / Debian:**
```bash
apt install ghostscript
```

**macOS:**
```bash
brew install ghostscript
```

### El script falló con error de Python

Si `build_site.sh` crea un venv pero falla en la instalación de paquetes:

```bash
rm -rf web/.venv
./tex2site/build_site.sh
```

El script recreará el venv limpio.

