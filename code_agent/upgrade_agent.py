"""
AI code upgrade agent.

Exposes the public entrypoints adhering to docs/architecture.md:
- create_upgrade_plan(repo_path, gaps): analyzes any store repository and uses
  an autonomous LLM agent to generate a traceable line-by-line upgrade plan.
- generate_upgrade(repo_path, plan): safely applies the patches with syntax checking and
  non-payment business logic preservation, returning upgrade results and PR info.
"""

from typing import Any, Optional

from code_agent.agentic import AutonomousCodingAgent


def create_upgrade_plan(repo_path: str, gaps: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """
    Decide which files need changing for each gap with traceable reasoning.

    Args:
        repo_path: Local path (or URL) of the store's code repository.
        gaps: Ranked gaps from impact_ranker.rank_gaps() or checkout issues.

    Returns:
        A list of planned changes with full line-by-line rationale.
    """
    agent = AutonomousCodingAgent(repo_path)
    return agent.plan_upgrades(gaps)


def generate_upgrade(repo_path: str, plan: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """
    Apply the planned changes safely and prepare the upgrade outcome.

    Args:
        repo_path: Local path of the store repository.
        plan: List of planned changes from create_upgrade_plan.

    Returns:
        {
            "success": bool,
            "branch": str,
            "files_changed": list[str],
            "pull_request_url": str,
            "summary": str,
            "errors": list[str],
        }
    """
    agent = AutonomousCodingAgent(repo_path)
    return agent.generate_upgrade(plan)
