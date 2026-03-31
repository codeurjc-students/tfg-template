"""Update web/mkdocs.yml with TFG metadata and nav structure."""

import argparse
import json
import re
import sys
from pathlib import Path


def _replace_block(content: str, key: str, new_block: str) -> str:
    """Remove all occurrences of a top-level YAML block, then append one fresh copy."""
    pattern = rf'^{re.escape(key)}:.*?(?=^\S|\Z)'
    stripped = re.sub(pattern, '', content, flags=re.MULTILINE | re.DOTALL)
    # Collapse runs of 3+ blank lines left by the removals
    stripped = re.sub(r'\n{3,}', '\n\n', stripped).rstrip('\n')
    return stripped + '\n\n' + new_block.rstrip('\n') + '\n'


def update(
    repo_root: Path,
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
    yml_path = repo_root / "web" / "mkdocs.yml"
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
    """Standalone entry point: load .metadata.json and update mkdocs.yml."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent

    parser = argparse.ArgumentParser(
        description="Configure web/mkdocs.yml from TFG metadata."
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=repo_root / "web" / "docs" / ".metadata.json",
        help="Path to .metadata.json (default: %(default)s)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=repo_root / "web" / "mkdocs.yml",
        help="Path to mkdocs.yml to update (default: %(default)s)",
    )
    args = parser.parse_args()
    metadata_file = args.metadata.resolve()
    yml_path = args.config.resolve()

    if not metadata_file.exists():
        print(f"[md2mkdocs] ERROR: {metadata_file} not found. Run tex2md.py first.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(metadata_file.read_text(encoding="utf-8"))
    docs_dir = metadata_file.parent
    # repo_root is two levels above the mkdocs.yml parent (web/)
    mkdocs_repo_root = yml_path.parent.parent

    update(mkdocs_repo_root, docs_dir, data["meta"], data["chapters"], data["appendixes"], data.get("nav_labels", {}))
    print("[md2mkdocs] mkdocs.yml updated.")


if __name__ == "__main__":
    main()
