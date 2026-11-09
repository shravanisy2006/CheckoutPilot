"""
CSS analyzer: checks style sheets for responsive layout rules (e.g. grid, flex)
affecting checkout summary and payment button visibility on mobile.
"""

import re
from pathlib import Path


def analyze_css_file(file_path: Path, repo_root: Path) -> dict:
    """Analyze a CSS file for checkout responsive grid or ordering rules."""
    rel_path = str(file_path.relative_to(repo_root)).replace("\\", "/")
    content = file_path.read_text(encoding="utf-8", errors="replace")

    has_checkout_class = ".checkout" in content
    has_media_query = bool(re.search(r'@media\s*\([^)]*max-width[^)]*\)', content, re.IGNORECASE))
    has_upgraded_grid_areas = "grid-template-areas" in content

    return {
        "file_path": rel_path,
        "has_checkout_styling": has_checkout_class,
        "has_mobile_media_query": has_media_query,
        "has_responsive_reordering": has_upgraded_grid_areas,
    }


def scan_css(repo_root: Path) -> list[dict]:
    """Scan all CSS files in the repository."""
    css_files: list[Path] = []
    candidates = list(repo_root.rglob("*.css"))
    for file_path in candidates:
        parts = file_path.parts
        if any(ignored in parts for ignored in ("venv", ".venv", "node_modules", "outputs", ".git")):
            continue
        css_files.append(file_path)

    return [analyze_css_file(p, repo_root) for p in css_files]
