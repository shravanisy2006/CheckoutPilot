"""
Build a fix the way the dashboard and backend expect it (docs/sample_result.json -> "fix").

    from code_agent.fix_builder import build_fix
    fix = build_fix("demo_stores/legacy_store", ["sdk_outdated", "no_paypal_on_cart"], fix_id="fix_123")

Safety rule: the store passed in is NEVER edited. It is copied to outputs/patched/<fix_id>/
and only the copy is patched. The result says whether the plan came from the AI model
("ai+template": AI edits, then the template upgrade) or only from the template planner ("template"), so we never overclaim.
"""

import difflib
import errno
import os
import re
import shutil
import stat
import uuid
from pathlib import Path
from typing import Any, Optional

from code_agent.agentic import AutonomousCodingAgent
from code_agent.llm_client import DeterministicFallbackAdapter
from code_agent.self_test import browser_check

PATCHED_ROOT = Path("outputs/patched")
BRANCH = "feature/paypal-checkout-upgrade"
SKIP_DIRS = ("__pycache__", ".git", "venv", ".venv", "node_modules", "outputs", ".pytest_cache")
TEXT_SUFFIXES = {".py", ".html", ".htm", ".js", ".ts", ".css", ".json", ".txt", ".md", ".jinja", ".j2"}

V6_MARKERS = ("web-sdk/v6", "createInstance", "<paypal-button")
V5_MARKERS = ("paypal.com/sdk/js",)
# v6 rejects v5 component names: "unrecognized component in createInstance: buttons"
PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
V5_COMPONENT = re.compile(r"""components\s*:\s*\[[^\]]*["']buttons["']""")


def _text_files(root: Path) -> dict[str, str]:
    files = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)  # only look at folders INSIDE the store
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and not any(p in SKIP_DIRS for p in relative.parts):
            files[relative.as_posix()] = path.read_text(encoding="utf-8", errors="replace")
    return files


def _diff_files(before: dict[str, str], after: dict[str, str]) -> list[dict[str, Any]]:
    changes = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old == new:
            continue
        change_type = "added" if old is None else "deleted" if new is None else "modified"
        diff_lines = list(difflib.unified_diff(
            (old or "").splitlines(keepends=True), (new or "").splitlines(keepends=True),
            fromfile=f"a/{path}", tofile=f"b/{path}"))
        changes.append({
            "path": path,
            "change_type": change_type,
            "diff": "".join(diff_lines),
            "lines_added": sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++")),
            "lines_removed": sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---")),
        })
    return changes


ID_PATTERN = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""")


def _check_upgrade(before: dict[str, str], after: dict[str, str], issue_ids: list[str]) -> list[str]:
    """Problems with the patched copy (empty list = looks like a valid v6 upgrade).

    Besides "v6 is in, v5 is out", every element id a page had before must still be there:
    the store's own scripts and tests rely on them, and an AI rewrite can silently drop them.
    """
    problems = []
    pages = {p: t for p, t in after.items() if p.endswith((".html", ".htm", ".py"))}
    if not any(marker in text for text in after.values() for marker in V6_MARKERS):
        problems.append("No PayPal SDK v6 code found in the patched store.")
    still_v5 = [p for p, t in pages.items() if any(m in t for m in V5_MARKERS)]
    if still_v5:
        problems.append("Pages still load the v5 SDK: " + ", ".join(still_v5))
    for path, old in before.items():
        if not path.endswith((".html", ".htm")):
            continue
        new = after.get(path)
        if new is None:
            problems.append(f"{path} was deleted.")
            continue
        lost = sorted(set(ID_PATTERN.findall(old)) - set(ID_PATTERN.findall(new)))
        if lost:
            problems.append(f"{path} lost element ids: " + ", ".join(lost))
    for path, text in after.items():
        if path.endswith((".js", ".html", ".ts")) and V5_COMPONENT.search(text):
            problems.append(f'{path} asks the v6 SDK for the v5 component "buttons" (v6 needs "paypal-payments").')
    for path, text in after.items():
        if path.endswith(".html") and "<paypal-button" in text and "onPayPalWebSdkLoaded" not in text \
                and "createInstance" not in text:
            problems.append(f"{path} has a <paypal-button> but never loads and starts the v6 SDK.")
    server_code = "\n".join(t for p, t in after.items() if p.endswith(".py"))
    for path, text in after.items():
        if not path.endswith(".html") or not server_code:
            continue
        for name in sorted(set(PLACEHOLDER.findall(text))):
            if "{{" + name + "}}" not in server_code:
                problems.append(f"{path} uses {{{{{name}}}}} but the server never fills it in.")
    if "no_paypal_on_cart" in issue_ids:
        carts = [t for p, t in after.items() if p.endswith(".html") and "cart" in Path(p).name.lower()]
        if carts and not any("<paypal-button" in t and "paypal-button-container" in t for t in carts):
            problems.append("The cart page has no PayPal button.")
    return problems


def build_fix(store_dir: str | Path, issue_ids: list[str], fix_id: Optional[str] = None,
              scan_id: str = "", out_root: Path = PATCHED_ROOT) -> dict[str, Any]:
    """Copy the store, let the code agent upgrade the copy, and describe the change."""
    source = Path(store_dir).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Store folder not found: {source}")
    fix_id = fix_id or f"fix_{uuid.uuid4().hex[:10]}"
    target = (out_root / fix_id).resolve()
    if target == source or source in target.parents:
        raise ValueError("The patched copy must be outside the original store folder.")
    gaps = [{"gap_id": i, "issue_id": i} for i in issue_ids]
    before = _text_files(source)

    def _rmtree_onerror(func, path, exc_info):
        """Error handler for shutil.rmtree on Windows read-only files.

        Windows Error 5 (Access is denied) / errno.EACCES occurs when trying
        to delete read-only files.  We make the file writable and retry.
        """
        exc_val = exc_info[1]
        win_err = getattr(exc_val, "winerror", None)
        errno_val = getattr(exc_val, "errno", None)
        if win_err == 5 or errno_val in (errno.EACCES, errno.EPERM):
            try:
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            except Exception:
                pass
            func(path)
        else:
            raise

    def attempt(llm=None):
        if target.exists():
            shutil.rmtree(target, onerror=_rmtree_onerror)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(*SKIP_DIRS))
        agent = AutonomousCodingAgent(target, llm=llm)
        plan = agent.plan_upgrades(gaps)
        result = agent.generate_upgrade(plan)
        after = _text_files(target)
        files = _diff_files(before, after)
        problems = list(result.get("errors") or []) + _check_upgrade(before, after, issue_ids)
        if files and not problems:
            # Text checks passed: now really use the patched store in a browser (fake PayPal, no network).
            problems = browser_check(target)
            checks["browser"] = "skipped" if os.getenv("CODE_AGENT_BROWSER_CHECK", "true").lower() in (
                "0", "false", "no") else ("failed" if problems else "passed")
        return agent, plan, files, problems

    warnings = []
    checks = {"browser": "not run"}
    agent, plan, files, problems = attempt()
    if agent.last_plan_source == "ai" and (problems or not files):
        # The AI's plan did not pass the checks: redo it with the built-in template planner.
        warnings.append("AI plan did not pass the checks (" + ("; ".join(problems) or "no changes")
                        + "); used the template plan instead.")
        agent, plan, files, problems = attempt(llm=DeterministicFallbackAdapter())

    explanation = []
    for issue_id in issue_ids:
        items = [p for p in plan if p.get("gap_id") == issue_id]
        if not items:
            continue
        summaries = list(dict.fromkeys(p.get("change_summary", "") for p in items if p.get("change_summary")))
        touched = list(dict.fromkeys(p.get("target_file") or p.get("file") for p in items))
        explanation.append({"issue_id": issue_id, "what_changed": " ".join(summaries), "files": touched})

    # The engine always finishes with its template upgrade, so an AI plan is "ai+template".
    generated_by = "ai+template" if agent.last_plan_source == "ai" else "template"
    ok = bool(files) and not problems
    return {
        "fix_id": fix_id,
        "scan_id": scan_id,
        "status": "proposed" if ok else "failed",
        "issue_ids": issue_ids,
        "summary": (f"Upgraded the PayPal checkout across {len(files)} file(s) "
                    f"({'AI plan + template' if generated_by == 'ai+template' else 'template plan'}): "
                    + ", ".join(f["path"] for f in files)
                    + (". Test purchase in a browser passed (simulated PayPal); next, prove it with a real "
                       "Sandbox payment." if checks["browser"] == "passed" else "")) if files
                   else "No changes were needed or made.",
        "explanation": explanation,
        "files": files,
        "branch": BRANCH,
        "pr_url": "",  # filled in only when a real pull request is opened
        "patched_store_dir": target.relative_to(Path.cwd().resolve()).as_posix()
        if Path.cwd().resolve() in target.parents else str(target),
        "generated_by": generated_by,
        "errors": problems,
        "warnings": warnings,
        # "passed" = a purchase on the patched copy worked in a browser (fake PayPal SDK, no network).
        "browser_check": checks["browser"],
    }
