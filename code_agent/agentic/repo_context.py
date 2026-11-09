"""
Repo Context Collector: scans any merchant repository, builds file trees,
identifies the tech stack, and extracts payment-relevant files for the LLM.
"""

import json
from pathlib import Path
from typing import Any, Optional

IGNORED_DIRS = {
    ".git",
    "venv",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "outputs",
    "screenshots",
}

CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".htm",
    ".jinja",
    ".jinja2",
    ".css",
    ".json",
    ".php",
}

MAX_FILE_SIZE = 100_000  # 100 KB limit per file to preserve token budget


class RepoContextCollector:
    """Collects repository structure and code files for LLM ingestion."""

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).resolve()

    def detect_stack(self) -> dict[str, Any]:
        """Detect the primary framework and technologies used by the store."""
        stack = {
            "backend": "unknown",
            "frontend": "unknown",
            "package_manager": "unknown",
        }

        if (self.repo_path / "package.json").exists():
            stack["package_manager"] = "npm"
            try:
                pkg = json.loads((self.repo_path / "package.json").read_text(encoding="utf-8"))
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "next" in deps:
                    stack["backend"] = "nextjs"
                    stack["frontend"] = "react"
                elif "express" in deps:
                    stack["backend"] = "express"
                elif "react" in deps:
                    stack["frontend"] = "react"
            except Exception:
                pass

        # Check Python frameworks
        for p in self.repo_path.rglob("*.py"):
            if any(x in p.parts for x in IGNORED_DIRS):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                if "FastAPI" in text or "from fastapi" in text:
                    stack["backend"] = "fastapi"
                    stack["package_manager"] = "pip"
                    break
                elif "Flask" in text or "from flask" in text:
                    stack["backend"] = "flask"
                    stack["package_manager"] = "pip"
                    break
                elif "django" in text.lower():
                    stack["backend"] = "django"
                    stack["package_manager"] = "pip"
                    break
            except Exception:
                continue

        if (self.repo_path / "requirements.txt").exists() or (self.repo_path / "Pipfile").exists():
            stack["package_manager"] = "pip"

        return stack

    def build_file_tree(self) -> list[str]:
        """Generate a relative list of all project files, skipping noise."""
        tree = []
        for p in self.repo_path.rglob("*"):
            if p.is_dir():
                continue
            if any(part in p.parts for part in IGNORED_DIRS):
                continue
            try:
                rel = str(p.relative_to(self.repo_path)).replace("\\", "/")
                tree.append(rel)
            except ValueError:
                continue
        return sorted(tree)

    def extract_payment_relevant_files(self) -> dict[str, str]:
        """
        Identify and extract code content for files relevant to payments:
        checkout templates, carts, server routes, client scripts, and stylesheets.
        """
        relevant_files: dict[str, str] = {}

        for p in self.repo_path.rglob("*"):
            if p.is_dir() or p.suffix.lower() not in CODE_EXTENSIONS:
                continue
            if any(part in p.parts for part in IGNORED_DIRS):
                continue
            if p.stat().st_size > MAX_FILE_SIZE:
                continue

            rel = str(p.relative_to(self.repo_path)).replace("\\", "/")
            name_lower = p.name.lower()

            is_relevant = False
            # Check by filename
            if any(k in name_lower for k in ("checkout", "cart", "pay", "order", "product", "style", "server", "app", "main", "api")):
                is_relevant = True

            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            # Check by content keywords
            if not is_relevant:
                keywords = ("paypal", "sdk", "checkout", "order", "cart", "total", "payment")
                if any(k in content.lower() for k in keywords):
                    is_relevant = True

            if is_relevant:
                relevant_files[rel] = content

        return relevant_files

    def get_full_repo_context(self) -> dict[str, Any]:
        """Produce the complete repository summary for the LLM agent."""
        return {
            "repo_path": str(self.repo_path),
            "stack": self.detect_stack(),
            "file_tree": self.build_file_tree(),
            "relevant_files": self.extract_payment_relevant_files(),
        }
