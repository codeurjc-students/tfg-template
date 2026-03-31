#!/usr/bin/env bash
# =============================================================================
# build_site.sh — Full pipeline: LaTeX → Markdown → static website
#
# Phases:
#   1. Tooling setup  — verify system deps, create/activate Python venv,
#                       install Python dependencies
#   2. Convert        — LaTeX → standard Markdown + .metadata.json
#                       (images, cross-references, post-processing)
#   3. Generate site  — configure MkDocs (md2mkdocs/), build HTML
#
# Usage:  ./tex2site/build_site.sh [--clean] [--serve]
#   --clean   Remove auto-generated files and exit (preserves manually-edited ones)
#   --serve   Start mkdocs serve after the build (useful for development)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[build]${NC} $*"; }
step()  { echo -e "${CYAN}[build]${NC} $*"; }
warn()  { echo -e "${YELLOW}[build]${NC} $*"; }
error() { echo -e "${RED}[build] ERROR:${NC} $*" >&2; exit 1; }

SERVE=false
CLEAN=false
for arg in "$@"; do
  [[ "$arg" == "--serve" ]] && SERVE=true
  [[ "$arg" == "--clean" ]] && CLEAN=true
done

# =========================================================================== #
# CLEAN — Remove auto-generated files (preserve manually-edited ones)
# =========================================================================== #
if [[ "${CLEAN}" == true ]]; then
  step "Cleaning auto-generated files..."

  # Generated Markdown (chapters + appendixes), but NOT extra.css / javascripts/
  find "${REPO_ROOT}/web/docs" -maxdepth 1 -name "*.md" -delete
  if [[ -d "${REPO_ROOT}/web/docs/appendixes" ]]; then
    find "${REPO_ROOT}/web/docs/appendixes" -name "*.md" -delete
  fi

  # Generated images
  rm -rf "${REPO_ROOT}/web/docs/img"

  # Intermediate artefacts produced by the Pandoc/conversion passes
  rm -f "${REPO_ROOT}/web/docs/.labels.json"
  rm -f "${REPO_ROOT}/web/docs/.metadata.json"

  # MkDocs HTML output
  rm -rf "${REPO_ROOT}/web/site"

  info "Auto-generated files removed."
  exit 0
fi

# =========================================================================== #
# PHASE 1 — Tooling setup
# =========================================================================== #
step "Phase 1/3: Tooling setup..."

# --- Verify required system tools ------------------------------------------
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
  error "python3 not found. Install with:
  sudo apt install python3"

# --- Create / reuse Python virtual environment -----------------------------
VENV_DIR="web/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python3"
VENV_PIP="${VENV_DIR}/bin/pip"

if [[ ! -d "${VENV_DIR}" ]]; then
  info "Creating Python virtual environment at ${VENV_DIR}..."
  python3 -m venv "${VENV_DIR}"
fi

[[ -f "${VENV_PIP}" ]] || \
  error "Virtual environment not created correctly. Try:
  rm -rf ${VENV_DIR}
  and re-run build_site.sh"

info "Python virtual environment ready at ${VENV_DIR}"

# --- Install Python dependencies -------------------------------------------
info "Installing/updating Python dependencies..."
"${VENV_PIP}" install -q --upgrade pip setuptools wheel
"${VENV_PIP}" install -q -r web/requirements.txt

export PATH="${VENV_DIR}/bin:${PATH}"

# =========================================================================== #
# PHASE 2 — Convert LaTeX → standard Markdown
# =========================================================================== #
step "Phase 2/3: Converting LaTeX → Markdown..."
python3 "${SCRIPT_DIR}/tex2md/tex2md.py" --tex "${REPO_ROOT}/tfg.tex" --docs "${REPO_ROOT}/web/docs"

# =========================================================================== #
# PHASE 3 — Generate MkDocs site
# =========================================================================== #
step "Phase 3/3: Generating website with MkDocs..."

MKDOCS="${VENV_DIR}/bin/mkdocs"

# Configure mkdocs.yml from the metadata produced in phase 2
PYTHONPATH="${SCRIPT_DIR}" python3 -m md2mkdocs.md2mkdocs \
  --metadata "${REPO_ROOT}/web/docs/.metadata.json" \
  --config "${REPO_ROOT}/web/mkdocs.yml"

# Build the static site
"${MKDOCS}" build --config-file web/mkdocs.yml --strict 2>&1 || {
  echo ""
  warn "Build had warnings. Retrying without --strict..."
  "${MKDOCS}" build --config-file web/mkdocs.yml
}

info "Site generated at web/site/"
info "Open web/site/index.html in your browser, or run:"
info "  ./tex2site/build_site.sh --serve"

# =========================================================================== #
# (Optional) Development server
# =========================================================================== #
if [[ "${SERVE}" == true ]]; then
  info "Starting local server at http://127.0.0.1:8000 ..."
  "${MKDOCS}" serve --config-file web/mkdocs.yml
fi
