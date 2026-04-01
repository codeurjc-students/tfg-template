#!/usr/bin/env bash
# =============================================================================
# tex2site.sh — Full pipeline: LaTeX → Markdown → static website
#
# Phases:
#   1. Tooling setup  — verify system deps, create/activate Python venv,
#                       install Python dependencies
#   2. Scaffold       — create the MkDocs project tree (idempotent)
#   3. Convert        — LaTeX → standard Markdown
#   4. Generate site  — configure mkdocs.yml, build or serve HTML
#
# Usage:  ./tex2site/tex2site.sh [build|serve] [options]
#
#   Commands (optional, default: build):
#     build            Build the static site (default)
#     serve            Start a live-reload dev server instead of building
#
#   Options:
#     --tex    <path>  LaTeX project folder          (default: current directory)
#     --mkdocs <path>  MkDocs project output folder  (default: <tex>/mkdocs)
#     --site   <path>  Static site output folder     (default: <tex>/site)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[build]${NC} $*"; }
step()  { echo -e "${CYAN}[build]${NC} $*"; }
warn()  { echo -e "${YELLOW}[build]${NC} $*"; }
error() { echo -e "${RED}[build] ERROR:${NC} $*" >&2; exit 1; }

COMMAND="build"
TEX_DIR=""
MKDOCS_DIR=""
SITE_DIR=""

# Parse optional command (build | serve)
if [[ $# -gt 0 && ( "$1" == "build" || "$1" == "serve" ) ]]; then
  COMMAND="$1"; shift
fi

# Parse options
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tex)    shift; TEX_DIR="$1" ;;
    --mkdocs) shift; MKDOCS_DIR="$1" ;;
    --site)   shift; SITE_DIR="$1" ;;
    *)        warn "Unknown argument: $1" ;;
  esac
  shift
done

# Resolve paths
# TEX2SITE_ROOT overrides default TEX_DIR (used when running inside Docker)
[[ -z "${TEX_DIR}" ]] && TEX_DIR="${TEX2SITE_ROOT:-$(pwd)}"
[[ "${TEX_DIR}"    != /* ]] && TEX_DIR="$(pwd)/${TEX_DIR}"
[[ -z "${MKDOCS_DIR}" ]] && MKDOCS_DIR="${TEX_DIR}/mkdocs"
[[ "${MKDOCS_DIR}" != /* ]] && MKDOCS_DIR="$(pwd)/${MKDOCS_DIR}"
[[ -z "${SITE_DIR}" ]]   && SITE_DIR="${TEX_DIR}/site"
[[ "${SITE_DIR}"   != /* ]] && SITE_DIR="$(pwd)/${SITE_DIR}"

TEX_MAIN="${TEX_DIR}/tfg.tex"
BIB_FILE="${TEX_DIR}/bibliografia.bib"
DOCS_DIR="${MKDOCS_DIR}/docs"
VENV_DIR="${MKDOCS_DIR}/.venv"
VENV_PIP="${VENV_DIR}/bin/pip"

# =========================================================================== #
# PHASE 1 — Tooling setup
# =========================================================================== #
step "Phase 1/4: Tooling setup..."

MISSING_SYSTEM=()
for cmd in pandoc pdf2svg gs; do
  command -v "$cmd" &>/dev/null || MISSING_SYSTEM+=("$cmd")
done
if [[ ${#MISSING_SYSTEM[@]} -gt 0 ]]; then
  error "Missing required system tools: ${MISSING_SYSTEM[*]}

  Install with:
    sudo apt update
    sudo apt install poppler-utils ghostscript pandoc

  On macOS:
    brew install pandoc poppler ghostscript"
fi

info "  pandoc: $(pandoc --version | head -1)"
info "  pdf2svg: ok"
info "  gs: $(gs --version | head -1)"

command -v python3 &>/dev/null || \
  error "python3 not found. Install with: sudo apt install python3"

# =========================================================================== #
# PHASE 2 — Scaffold MkDocs project (idempotent)
# =========================================================================== #
step "Phase 2/4: Scaffolding MkDocs project at ${MKDOCS_DIR}..."
PYTHONPATH="${SCRIPT_DIR}" python3 -m md2mkdocs.md2mkdocs scaffold \
  --output "${MKDOCS_DIR}" \
  --bib    "${BIB_FILE}"

# Set up venv (inside MKDOCS_DIR so it and the project are self-contained)
if [[ ! -d "${VENV_DIR}" ]]; then
  info "Creating Python virtual environment at ${VENV_DIR}..."
  python3 -m venv "${VENV_DIR}"
fi
[[ -f "${VENV_PIP}" ]] || error "Virtual environment not created correctly. Remove ${VENV_DIR} and retry."
info "Installing/updating Python dependencies..."
"${VENV_PIP}" install -q --upgrade pip setuptools wheel
"${VENV_PIP}" install -q -r "${MKDOCS_DIR}/requirements.txt"
export PATH="${VENV_DIR}/bin:${PATH}"

# =========================================================================== #
# PHASE 3 — Convert LaTeX → standard Markdown
# =========================================================================== #
step "Phase 3/4: Converting LaTeX → Markdown..."
python3 "${SCRIPT_DIR}/tex2md/tex2md.py" \
  --tex  "${TEX_MAIN}" \
  --docs "${DOCS_DIR}"

# =========================================================================== #
# PHASE 4 — Configure mkdocs.yml and build or serve
# =========================================================================== #
step "Phase 4/4: Generating website with MkDocs..."

PYTHONPATH="${SCRIPT_DIR}" python3 -m md2mkdocs.md2mkdocs update \
  --metadata "${DOCS_DIR}/.metadata.json" \
  --config   "${MKDOCS_DIR}/mkdocs.yml" \
  --bib      "${BIB_FILE}"

MKDOCS="${VENV_DIR}/bin/mkdocs"

if [[ "${COMMAND}" == "serve" ]]; then
  info "Starting local server at http://0.0.0.0:8000 ..."
  # --livereload must be explicit: mkdocs 1.6.x has a Click flag-value bug
  # where the default resolves to False when neither --livereload nor
  # --no-livereload is passed on the command line.
  "${MKDOCS}" serve \
    --config-file "${MKDOCS_DIR}/mkdocs.yml" \
    --dev-addr 0.0.0.0:8000 \
    --livereload
else
  "${MKDOCS}" build \
    --config-file "${MKDOCS_DIR}/mkdocs.yml" \
    --site-dir    "${SITE_DIR}" \
    --strict 2>&1 || {
    echo ""
    warn "Build had warnings. Retrying without --strict..."
    "${MKDOCS}" build \
      --config-file "${MKDOCS_DIR}/mkdocs.yml" \
      --site-dir    "${SITE_DIR}"
  }
  info "Site generated at ${SITE_DIR}/"
  info "Open ${SITE_DIR}/index.html in your browser, or run:"
  info "  ./tex2site/tex2site.sh serve"
fi

