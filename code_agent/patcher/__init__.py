"""
Patcher package: applies safe, non-destructive code fixes with AST, syntax,
and LLM-driven contextual synthesis.
"""

from code_agent.patcher.engine import PatchEngine, apply_upgrade
from code_agent.patcher.llm_patcher import synthesize_file_patch
from code_agent.patcher.validators import (
    validate_balanced_brackets,
    validate_business_preservation,
    validate_code_syntax,
    validate_html_syntax_and_ids,
    validate_python_syntax,
)

__all__ = [
    "PatchEngine",
    "apply_upgrade",
    "synthesize_file_patch",
    "validate_code_syntax",
    "validate_python_syntax",
    "validate_balanced_brackets",
    "validate_html_syntax_and_ids",
    "validate_business_preservation",
]
