"""AI engine: turns raw scan data into a list of checkout gaps (rules + vision model)."""

from ai_engine.checkout_analyzer import analyze_checkout

__all__ = ["analyze_checkout"]
