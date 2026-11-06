"""
AI code upgrade agent.

Goal: given a store's code repository and the ranked gaps, write the code
changes (e.g. PayPal JS SDK v5 -> v6, add saved PayPal accounts) and open
them as a pull request with an explanation per change.

STATUS: placeholder only. No AI or GitHub calls yet.
"""


def create_upgrade_plan(repo_path: str, gaps: list[dict]) -> list[dict]:
    """
    Decide which files need changing for each gap.

    Args:
        repo_path: Local path (or URL) of the store's code repository.
        gaps: Ranked gaps from impact_ranker.rank_gaps().

    Returns:
        A list of planned changes, each shaped like:
        {"gap_id": str, "file": str, "change_summary": str}
    """
    # TODO: search the repo for where the PayPal SDK is loaded and orders are created.
    # TODO: ask the AI model to propose changes following PayPal's v5 -> v6 guide.
    return []


def generate_upgrade(repo_path: str, plan: list[dict]) -> dict:
    """
    Apply the planned changes and prepare a pull request.

    Returns:
        {"branch": str, "files_changed": list[str], "pull_request_url": str}
    """
    # TODO: create a new git branch, apply the AI-written edits, commit.
    # TODO: open a pull request using the GITHUB_TOKEN from .env.
    return {"branch": "", "files_changed": [], "pull_request_url": ""}
