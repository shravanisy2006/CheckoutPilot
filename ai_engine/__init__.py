"""AI engine: turns raw scan data into a list of checkout issues (rules + vision model)."""

from ai_engine.checkout_analyzer import analyze_checkout, analyze_checkout_detailed
from ai_engine.errors import ModuleError
from ai_engine.mock import analyze_checkout_mock

__all__ = ["analyze_checkout", "analyze_checkout_detailed", "analyze_checkout_mock", "ModuleError"]
