"""
Autonomous LLM Coding Agent for CheckoutPilot.

Takes ANY store repository, extracts context, understands the tech stack,
plans PayPal v6 upgrades using an LLM, and applies safe, non-destructive
code patches with syntax validation.
"""

import json
from pathlib import Path
from typing import Any, Optional

from code_agent.agentic.paypal_knowledge import PAYPAL_V6_KNOWLEDGE_BASE
from code_agent.agentic.repo_context import RepoContextCollector
from code_agent.llm_client import BaseLLMAdapter, get_llm_client
from code_agent.patcher import PatchEngine
from code_agent.patcher.validators import (
    validate_business_preservation,
    validate_html_syntax_and_ids,
    validate_python_syntax,
)
from code_agent.planner import plan_upgrades as deterministic_plan_upgrades


class AutonomousCodingAgent:
    """LLM-driven coding agent that plans and writes payment modernizations for any repo."""

    def __init__(self, repo_path: str | Path, llm: Optional[BaseLLMAdapter] = None):
        self.repo_path = Path(repo_path).resolve()
        self.collector = RepoContextCollector(self.repo_path)
        self.llm = llm or get_llm_client()
        self.last_plan_source = ""  # "ai" (planned by the LLM) or "template" (built-in planner)

    def plan_upgrades(self, gaps: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
        """
        Analyze the complete repository context and generate a tailored,
        line-by-line upgrade plan using the LLM.
        """
        if gaps is not None and len(gaps) == 0:
            return []

        # 1. Collect full repo context
        repo_context = self.collector.get_full_repo_context()

        # 2. If an active LLM is available (Gemini / NVIDIA / Ollama), use it to reason over the repo
        if self.llm and self.llm.is_available() and type(self.llm).__name__ != "DeterministicFallbackAdapter":
            system_prompt = (
                "You are an expert full-stack coding agent specializing in eCommerce payment modernizations.\n"
                "Your mission: Analyze the provided merchant repository code, identify all payment integration flaws "
                "based on the audit gaps and official PayPal v6 standards, and output a structured list of planned file changes.\n\n"
                f"{PAYPAL_V6_KNOWLEDGE_BASE}\n\n"
                "Output STRICTLY a JSON array of change objects with keys:\n"
                "  gap_id, file, target_file, change_summary, line_start, line_end, action, "
                "before_snippet, after_snippet, rationale, estimated_impact, syntax_type, priority.\n"
                "Do NOT wrap in markdown or prose outside the JSON."
            )

            user_prompt = (
                f"Repository Tech Stack: {json.dumps(repo_context['stack'])}\n"
                f"Project File Tree: {json.dumps(repo_context['file_tree'][:50])}\n"
                f"Audit Gaps Found: {json.dumps(gaps or [])}\n\n"
                "Relevant Code Snippets in Merchant Repository:\n"
            )
            for fname, fcontent in list(repo_context["relevant_files"].items())[:6]:
                user_prompt += f"\n--- File: {fname} ---\n{fcontent[:2000]}\n"

            user_prompt += "\nPlan the PayPal v6 upgrades for this specific codebase:"

            plan_json = self.llm.generate_json(user_prompt, system_prompt=system_prompt)
            if isinstance(plan_json, list) and len(plan_json) > 0:
                # Ensure each plan item has required fields
                cleaned_plan = []
                for item in plan_json:
                    if isinstance(item, dict) and "file" in item:
                        item.setdefault("target_file", item["file"])
                        item.setdefault("priority", 1)
                        cleaned_plan.append(item)
                if cleaned_plan:
                    self.last_plan_source = "ai"
                    return cleaned_plan

        # 3. Graceful deterministic fallback: guarantees 100% reliability offline
        self.last_plan_source = "template"
        return deterministic_plan_upgrades(self.repo_path, gaps)

    def generate_upgrade(self, plan: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        """
        Apply planned upgrades safely to the merchant repository with syntax checking.
        """
        if not self.repo_path.exists() or not self.repo_path.is_dir():
            return {
                "success": False,
                "branch": "",
                "files_changed": [],
                "pull_request_url": "",
                "summary": "Repository path does not exist.",
                "errors": [f"Path not found: {self.repo_path}"],
            }

        # Safety: never patch the CheckoutPilot project itself (patch a copy of a store instead).
        if (self.repo_path / "code_agent").is_dir() and (self.repo_path / "demo_stores").is_dir():
            return {
                "success": False,
                "branch": "",
                "files_changed": [],
                "pull_request_url": "",
                "summary": "Refused: this is the CheckoutPilot project, not a store. Patch a copy of a store.",
                "errors": ["Refusing to patch the CheckoutPilot project folder."],
                "generated_by": "",
            }

        # An empty plan means there is nothing to change.
        if plan is not None and len(plan) == 0:
            return {"success": True, "branch": "", "files_changed": [], "pull_request_url": "",
                    "summary": "No files modified.", "errors": [], "generated_by": ""}

        # If no plan provided, generate it first
        active_plan = plan if plan is not None else self.plan_upgrades()

        # 1. Apply plan using PatchEngine (handles AST/HTML validation, LLM synthesis, and preservation checks)
        engine = PatchEngine(self.repo_path, llm=self.llm)
        result = engine.apply_upgrade(active_plan)

        files = result.get("files_changed", [])
        success = result.get("success", False)

        return {
            "success": success,
            "branch": "feature/paypal-checkout-upgrade" if files else "",
            "files_changed": files,
            "pull_request_url": "",  # set only when a real pull request is opened
            "summary": (
                f"Successfully modernized PayPal checkout across {len(files)} files: " + ", ".join(files)
                if files
                else "No files modified."
            ),
            "errors": result.get("errors", []),
            "generated_by": self.last_plan_source or "template",
        }

