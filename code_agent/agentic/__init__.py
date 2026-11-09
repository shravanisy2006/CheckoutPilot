"""
Agentic coding module for arbitrary store repositories.
"""

from code_agent.agentic.coding_agent import AutonomousCodingAgent
from code_agent.agentic.paypal_knowledge import PAYPAL_V6_KNOWLEDGE_BASE
from code_agent.agentic.repo_context import RepoContextCollector

__all__ = ["AutonomousCodingAgent", "RepoContextCollector", "PAYPAL_V6_KNOWLEDGE_BASE"]

