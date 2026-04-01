"""MkDocs project scaffolding and configuration for TFG sites.

Sub-commands (callable via ``python3 -m md2mkdocs.md2mkdocs <cmd> ...``):

  scaffold  --output <dir> --bib <bib_path>
      Create a new MkDocs project from the built-in scaffold template.
      Static files (mkdocs.yml, extra.css, hooks, overrides, …) are copied
      only when they do not already exist, so user edits are preserved on
      subsequent runs.

  update  --metadata <path> --config <path>
      Rewrite mkdocs.yml with TFG metadata (title, author, nav…) extracted
      from a previously generated .metadata.json.

  clean  --output <dir>
      Remove all LaTeX-derived artefacts from the output directory (generated
      .md files, images, .labels.json, .metadata.json, site/).  Static
      scaffold files and user edits are left untouched.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

# The scaffold/ directory lives next to this module file.
_SCAFFOLD_DIR = Path(__file__).parent / "scaffold"

_GREEN = "\033[0;32m"
_NC = "\033[0m"


def _info(msg: str) -> None:
    print(f"{_GREEN}[md2mkdocs]{_NC} {msg}")


# ---------------------------------------------------------------------------
# Scaffold
# ---------------------------------------------------------------------------

def scaffold(output_dir: Path, bib_path: Path) -> None:
    """Populate *output_dir* with the static MkDocs project template.

    Files that already exist are left untouched so user edits survive
    repeated builds.  *bib_path* must be the absolute path to
    ``bibliografia.bib``; it is written into ``mkdocs.yml`` so the
    project works from any location.
    """
    docs_dir = output_dir / "docs"

    # Ensure required subdirectories exist
    for d in (docs_dir / "appendixes", docs_dir / "img",
              output_dir / "hooks", output_dir / "overrides"):
        d.mkdir(parents=True, exist_ok=True)

    def _copy_if_missing(src: Path, dst: Path) -> None:
        if dst.exists():
            _info(f"  exists   {dst}  (skipped)")
        else:
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            _info(f"  created  {dst}")

    scaffold = _SCAFFOLD_DIR
    _copy_if_missing(scaffold / "requirements.txt",           output_dir / "requirements.txt")
    _copy_if_missing(scaffold / "docs" / "extra.css",         docs_dir / "extra.css")
    _copy_if_missing(scaffold / "docs" / "javascripts",       docs_dir / "javascripts")
    _copy_if_missing(scaffold / "hooks" / "fix_url_latex.py", output_dir / "hooks" / "fix_url_latex.py")
    _copy_if_missing(scaffold / "overrides" / "main.html",    output_dir / "overrides" / "main.html")

    partials_src = scaffold / "overrides" / "partials"
    if partials_src.exists():
        _copy_if_missing(partials_src, output_dir / "overrides" / "partials")

    # mkdocs.yml: copy once, then patch the bib_file path to be absolute so
    # the project works regardless of where output_dir lives.
    yml_dst = output_dir / "mkdocs.yml"
    if yml_dst.exists():
        _info(f"  exists   {yml_dst}  (skipped)")
    else:
        content = (scaffold / "mkdocs.yml").read_text(encoding="utf-8")
        content = re.sub(
            r'bib_file:.*bibliografia\.bib.*',
            f'bib_file: "{bib_path}"',
            content,
        )
        yml_dst.write_text(content, encoding="utf-8")
        _info(f"  created  {yml_dst}")


# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------

def clean(output_dir: Path) -> None:
    """Remove LaTeX-derived artefacts from *output_dir*.

    Deletes generated ``.md`` files, ``docs/img/``, ``.labels.json``,
    ``.metadata.json``, and ``site/``.  Static scaffold files and any
    user edits are preserved.
    """
    docs_dir = output_dir / "docs"

    # Generated Markdown (top-level + appendixes)
    for md in docs_dir.glob("*.md"):
        md.unlink()
        _info(f"  removed  {md}")
    app_dir = docs_dir / "appendixes"
    if app_dir.is_dir():
        for md in app_dir.glob("*.md"):
            md.unlink()
            _info(f"  removed  {md}")

    # Generated images
    img_dir = docs_dir / "img"
    if img_dir.is_dir():
        shutil.rmtree(img_dir)
        _info(f"  removed  {img_dir}")

    # Intermediate artefacts
    for name in (".labels.json", ".metadata.json"):
        f = docs_dir / name
        if f.exists():
            f.unlink()
            _info(f"  removed  {f}")

    # MkDocs HTML output
    site_dir = output_dir / "site"
    if site_dir.is_dir():
        shutil.rmtree(site_dir)
        _info(f"  removed  {site_dir}")


# ---------------------------------------------------------------------------
# Update (metadata → mkdocs.yml)
# ---------------------------------------------------------------------------

def _replace_block(content: str, key: str, new_block: str) -> str:
    """Remove all occurrences of a top-level YAML block, then append one fresh copy."""
    pattern = rf'^{re.escape(key)}:.*?(?=^\S|\Z)'
    stripped = re.sub(pattern, '', content, flags=re.MULTILINE | re.DOTALL)
    # Collapse runs of 3+ blank lines left by the removals
    stripped = re.sub(r'\n{3,}', '\n\n', stripped).rstrip('\n')
    return stripped + '\n\n' + new_block.rstrip('\n') + '\n'


def update(
    yml_path: Path,
    docs_dir: Path,
    meta: dict,
    chapters: list[dict],
    appendixes: list[dict],
    nav_labels: dict | None = None,
) -> None:
    """Rewrite mkdocs.yml with current metadata, extra vars, and nav.

    Each entry in `chapters` and `appendixes` must have keys:
      - ``title``   — display name
      - ``md_file`` — path relative to docs_dir (e.g. ``introduccion.md``)

    ``nav_labels`` is an optional dict with keys ``home``, ``acknowledgements``,
    ``chapters``, and ``appendices`` whose values override the default labels.
    """
    if nav_labels is None:
        nav_labels = {}
    content = yml_path.read_text(encoding="utf-8")

    # ---- Simple top-level keys ----------------------------------------
    content = re.sub(r'^site_name:.*', f'site_name: "{meta["title"]}"', content, flags=re.MULTILINE)
    content = re.sub(r'^site_author:.*', f'site_author: "{meta["author"]}"', content, flags=re.MULTILINE)
    content = re.sub(
        r'^site_description:.*',
        f'site_description: "{meta["degree"]} — {meta["academic_year"]}"',
        content,
        flags=re.MULTILINE,
    )

    # ---- extra: block -------------------------------------------------
    extra_block = (
        "extra:\n"
        f"  tfg_year: {meta['year']}\n"
        f"  tfg_institution: {meta['university']}\n"
        f"  tfg_school: {meta['school']}\n"
        f"  tfg_tutor: {meta['tutor']}\n"
        f"  tfg_degree: {meta['degree']}\n"
        f"  tfg_academic_year: {meta['academic_year']}\n"
    )
    content = _replace_block(content, "extra", extra_block)

    # ---- nav: block ---------------------------------------------------
    home_label = nav_labels.get("home", "Home")
    ack_label = nav_labels.get("acknowledgements", "Acknowledgements")
    chapters_label = nav_labels.get("chapters", "Chapters")
    appendices_label = nav_labels.get("appendices", "Appendices")

    nav_lines = ["nav:"]
    nav_lines.append(f"  - {home_label}: index.md")

    if (docs_dir / "agradecimientos.md").exists():
        nav_lines.append(f"  - {ack_label}: agradecimientos.md")

    if chapters:
        nav_lines.append(f"  - {chapters_label}:")
        for chap in chapters:
            title = chap["title"].replace('"', '\\"')
            nav_lines.append(f'    - "{title}": {chap["md_file"]}')

    if appendixes:
        nav_lines.append(f"  - {appendices_label}:")
        for app in appendixes:
            title = app["title"].replace('"', '\\"')
            nav_lines.append(f'    - "{title}": {app["md_file"]}')

    nav_block = "\n".join(nav_lines) + "\n"
    content = _replace_block(content, "nav", nav_block)

    yml_path.write_text(content, encoding="utf-8")


def main() -> None:
    """Entry point with sub-commands: scaffold, update, clean."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent

    parser = argparse.ArgumentParser(
        description="MkDocs project scaffolding and configuration for TFG sites.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # --- scaffold ----------------------------------------------------------
    p_scaffold = sub.add_parser(
        "scaffold",
        help="Create a MkDocs project from the built-in template (idempotent).",
    )
    p_scaffold.add_argument(
        "--output", type=Path, required=True,
        help="Directory where the MkDocs project will be created.",
    )
    p_scaffold.add_argument(
        "--bib", type=Path, default=repo_root / "bibliografia.bib",
        help="Absolute path to the BibTeX file (default: %(default)s).",
    )

    # --- update ------------------------------------------------------------
    p_update = sub.add_parser(
        "update",
        help="Rewrite mkdocs.yml with TFG metadata and navigation.",
    )
    p_update.add_argument(
        "--metadata", type=Path,
        default=repo_root / "mkdocs" / "docs" / ".metadata.json",
        help="Path to .metadata.json produced by tex2md (default: %(default)s).",
    )
    p_update.add_argument(
        "--config", type=Path,
        default=repo_root / "mkdocs" / "mkdocs.yml",
        help="Path to mkdocs.yml to update (default: %(default)s).",
    )
    p_update.add_argument(
        "--bib", type=Path, default=None,
        help="Path to the BibTeX file; used to re-scaffold mkdocs.yml when it is missing.",
    )

    # --- clean -------------------------------------------------------------
    p_clean = sub.add_parser(
        "clean",
        help="Remove LaTeX-derived artefacts from an output directory.",
    )
    p_clean.add_argument(
        "--output", type=Path, required=True,
        help="Directory containing the MkDocs project to clean.",
    )

    args = parser.parse_args()

    if args.command == "scaffold":
        output_dir = args.output.resolve()
        bib_path = args.bib.resolve()
        _info(f"Scaffolding MkDocs project at {output_dir}...")
        scaffold(output_dir, bib_path)
        _info("Scaffold complete.")

    elif args.command == "update":
        metadata_file = args.metadata.resolve()
        yml_path = args.config.resolve()
        if not metadata_file.exists():
            print(f"[md2mkdocs] ERROR: {metadata_file} not found. Run tex2md first.",
                  file=sys.stderr)
            sys.exit(1)
        if not yml_path.exists():
            _info(f"mkdocs.yml not found at {yml_path} — re-scaffolding...")
            bib_path = args.bib.resolve() if args.bib else (yml_path.parent.parent / "bibliografia.bib").resolve()
            scaffold(yml_path.parent, bib_path)
        data = json.loads(metadata_file.read_text(encoding="utf-8"))
        docs_dir = metadata_file.parent
        update(yml_path, docs_dir, data["meta"], data["chapters"],
               data["appendixes"], data.get("nav_labels", {}))
        metadata_file.unlink()
        _info(f"  removed intermediate {metadata_file.name}")
        _info("mkdocs.yml updated.")

    elif args.command == "clean":
        output_dir = args.output.resolve()
        _info(f"Cleaning auto-generated files in {output_dir}...")
        clean(output_dir)
        _info("Clean complete.")


if __name__ == "__main__":
    main()
