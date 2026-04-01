#!/usr/bin/env bash
# =============================================================================
# entrypoint.sh — Docker entry point for tex2site
#
# Routes the Docker command to the appropriate tool:
#
#   tex2site.sh [build|serve] [options]  →  tex2site.sh (full pipeline)
#   tex2site    [build|serve] [options]  →  tex2site.sh (full pipeline)
#   mkdocs      <subcommand>  [options]  →  mkdocs from the project venv
#   (no arguments)                       →  tex2site.sh build (default)
# =============================================================================

set -euo pipefail

MKDOCS_DIR="${TEX2SITE_ROOT:-/doc}/mkdocs"
VENV_MKDOCS="${MKDOCS_DIR}/.venv/bin/mkdocs"

case "${1:-}" in
  tex2site)
    shift
    exec /opt/tex2site/tex2site.sh "$@"
    ;;
  mkdocs)
    shift
    if [[ -x "${VENV_MKDOCS}" ]]; then
      exec "${VENV_MKDOCS}" "$@"
    else
      echo "ERROR: mkdocs not found at ${VENV_MKDOCS}" >&2
      echo "Run 'tex2site.sh build' first to set up the environment." >&2
      exit 1
    fi
    ;;
  *)
    exec /opt/tex2site/tex2site.sh "$@"
    ;;
esac
