"""
Patcher package: applies safe, non-destructive code fixes with AST and syntax validation.
"""

from code_agent.patcher.engine import PatchEngine, apply_upgrade
from code_agent.patcher.validators import (
    validate_business_preservation,
    validate_html_syntax_and_ids,
    validate_python_syntax,
)

__all__ = [
    "PatchEngine",
    "apply_upgrade",
    "validate_python_syntax",
    "validate_html_syntax_and_ids",
    "validate_business_preservation",
]

