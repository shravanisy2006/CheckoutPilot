"""Code agent: reads a store's repository and writes the PayPal checkout upgrade."""

from code_agent.agentic import AutonomousCodingAgent, RepoContextCollector, PAYPAL_V6_KNOWLEDGE_BASE
from code_agent.analyzer import PaymentContext, analyze_repository
from code_agent.llm_client import get_llm_client
from code_agent.patcher import PatchEngine, apply_upgrade
from code_agent.planner import UpgradePlanner, plan_upgrades
from code_agent.upgrade_agent import create_upgrade_plan, generate_upgrade

__all__ = [
    "AutonomousCodingAgent",
    "RepoContextCollector",
    "PAYPAL_V6_KNOWLEDGE_BASE",
    "create_upgrade_plan",
    "generate_upgrade",
    "analyze_repository",
    "PaymentContext",
    "UpgradePlanner",
    "plan_upgrades",
    "PatchEngine",
    "apply_upgrade",
    "get_llm_client",
]
