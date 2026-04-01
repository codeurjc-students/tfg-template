# =============================================================================
# tex2site — Docker image
#
# Builds an image with all system dependencies needed to run tex2site.sh
# (pandoc ≥ 3.0, pdf2svg, Ghostscript, Python 3 + venv).
#
# Build (from workspace root):
#   docker build -t codeurjc/tex2site tex2site/
#
# Usage (run from your LaTeX project root):
#   docker run --rm -u $(id -u):$(id -g) -v $(pwd):/doc codeurjc/tex2site tex2site.sh build
#   docker run --rm -u $(id -u):$(id -g) -v $(pwd):/doc codeurjc/tex2site tex2site serve
#   docker run --rm -u $(id -u):$(id -g) -v $(pwd):/doc codeurjc/tex2site mkdocs ...
#
# The LaTeX project must be mounted at /doc via -v "$(pwd)":/doc.
# The generated MkDocs site is written to /doc/site/ by default.
# =============================================================================

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# ── System dependencies ──────────────────────────────────────────────────────
# pandoc    ≥ 3.0  – LaTeX → Markdown conversion + Lua filters
# pdf2svg          – convert vector PDF images to SVG
# ghostscript      – convert EPS images to PDF (before pdf2svg)
# python3 + venv   – post-processing scripts and MkDocs runtime
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      pandoc \
      pdf2svg \
      ghostscript \
      python3 \
      python3-venv \
 && rm -rf /var/lib/apt/lists/*

# ── Copy the tex2site tool ───────────────────────────────────────────────────
# The build context must be the tex2site/ directory:
#   docker build -t codeurjc/tex2site tex2site/
COPY . /opt/tex2site

# ── Runtime configuration ────────────────────────────────────────────────────
# TEX2SITE_ROOT tells tex2site.sh where the LaTeX project root is.
# Users mount their project at /doc via -v "$(pwd)":/doc.
ENV TEX2SITE_ROOT=/doc

# Expose the MkDocs development server port (used with tex2site serve)
EXPOSE 8000

WORKDIR /doc

# Routes: tex2site.sh/tex2site → tex2site.sh, mkdocs → project venv mkdocs
ENTRYPOINT ["/opt/tex2site/entrypoint.sh"]
CMD []
