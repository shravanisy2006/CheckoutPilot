"""
Tests for the Autonomous LLM Coding Agent and Repo Context Collector.
"""

from pathlib import Path
from typing import Optional

from code_agent.agentic import AutonomousCodingAgent, RepoContextCollector
from code_agent.llm_client import BaseLLMAdapter


class MockLLMAdapter(BaseLLMAdapter):
    """Mock LLM adapter for testing agentic planning and code generation."""

    def __init__(self, plan_to_return=None):
        self.plan_to_return = plan_to_return
        self.prompts_received = []

    def is_available(self) -> bool:
        return True

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        self.prompts_received.append((prompt, system_prompt))
        return "mock text"

    def generate_json(self, prompt: str, system_prompt: Optional[str] = None):
        self.prompts_received.append((prompt, system_prompt))
        return self.plan_to_return


def test_repo_context_collector_demo_store():
    """Verify context collector builds file trees and extracts payment files."""
    collector = RepoContextCollector("demo_stores/legacy_store")
    context = collector.get_full_repo_context()

    assert "repo_path" in context
    assert "stack" in context
    assert context["stack"]["backend"] == "fastapi"
    assert len(context["file_tree"]) >= 5
    assert any("checkout.html" in f for f in context["file_tree"])

    # Verify payment relevant files were identified and extracted
    rel_files = context["relevant_files"]
    assert any("checkout.html" in f for f in rel_files)
    assert any("app.py" in f for f in rel_files)
    assert any("checkout.js" in f for f in rel_files)


def test_autonomous_coding_agent_with_mock_llm():
    """Verify autonomous agent passes full context to LLM and returns structured plan."""
    mock_plan = [
        {
            "gap_id": "sdk_outdated",
            "file": "templates/checkout.html",
            "target_file": "templates/checkout.html",
            "change_summary": "LLM-planned v6 SDK upgrade",
            "line_start": 8,
            "line_end": 10,
            "action": "replace",
            "before_snippet": "<script src=\"https://www.paypal.com/sdk/js\"></script>",
            "after_snippet": "<script src=\"{{PAYPAL_SDK_URL}}\"></script>",
            "rationale": "Migrated to v6 web components as per PayPal v6 handbook.",
            "estimated_impact": "40% reduction in latency.",
            "syntax_type": "html",
            "priority": 1,
        }
    ]

    mock_llm = MockLLMAdapter(plan_to_return=mock_plan)
    agent = AutonomousCodingAgent("demo_stores/legacy_store", llm=mock_llm)

    gaps = [{"gap_id": "sdk_outdated", "title": "Outdated SDK"}]
    plan = agent.plan_upgrades(gaps)

    # Verify LLM was invoked with PayPal knowledge base and repo code
    assert len(mock_llm.prompts_received) == 1
    user_prompt, system_prompt = mock_llm.prompts_received[0]
    assert "OFFICIAL PAYPAL JAVASCRIPT SDK V6 MIGRATION GUIDE" in system_prompt
    assert "FastAPI" in user_prompt or "fastapi" in user_prompt
    assert "checkout.html" in user_prompt

    # Verify plan returned matches LLM generation
    assert len(plan) == 1
    assert plan[0]["change_summary"] == "LLM-planned v6 SDK upgrade"
    assert plan[0]["gap_id"] == "sdk_outdated"


def test_autonomous_coding_agent_end_to_end_upgrade(tmp_path):
    """Verify agent can execute end-to-end upgrade on an arbitrary directory."""
    import shutil

    source_store = Path("demo_stores/legacy_store").resolve()
    target_store = tmp_path / "merchant_store"
    shutil.copytree(source_store, target_store)

    agent = AutonomousCodingAgent(target_store)
    plan = agent.plan_upgrades()
    assert len(plan) >= 1

    result = agent.generate_upgrade(plan)
    assert result["success"] is True
    assert len(result["files_changed"]) >= 4
    assert (target_store / "static" / "paypal.js").exists()

