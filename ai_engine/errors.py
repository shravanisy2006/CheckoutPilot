"""
Error type used by the AI engine and impact ranker.

The team contract says every module raises ModuleError(code, message) for
expected failures. Member 2 defines the shared class in
backend/schemas/models.py. Until that file exists, we use an identical local
copy so this module works on its own.
"""

try:  # Use the shared class once Member 2 has added it.
    from backend.schemas.models import ModuleError  # type: ignore
except ImportError:  # pragma: no cover - fallback until models.py exists

    class ModuleError(Exception):
        """An expected, user-explainable failure inside a module."""

        def __init__(self, code: str, message: str) -> None:
            super().__init__(f"{code}: {message}")
            self.code = code
            self.message = message


# Error codes this module can raise (subset of the team's shared list).
AI_UNAVAILABLE = "AI_UNAVAILABLE"
AI_BAD_OUTPUT = "AI_BAD_OUTPUT"

__all__ = ["ModuleError", "AI_UNAVAILABLE", "AI_BAD_OUTPUT"]
