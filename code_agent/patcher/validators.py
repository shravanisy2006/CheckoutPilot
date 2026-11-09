"""
Syntax and preservation validators for Code Patcher.
Ensures zero disruption to non-payment business code and stable DOM IDs.
"""

import ast
from html.parser import HTMLParser
from typing import Optional


class ElementIdExtractor(HTMLParser):
    """Extracts all id attributes from an HTML document."""

    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        for attr, value in attrs:
            if attr.lower() == "id" and value:
                self.ids.add(value)


def validate_python_syntax(code: str) -> tuple[bool, Optional[str]]:
    """Validate Python code using AST parsing."""
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, f"Python SyntaxError at line {e.lineno}: {e.msg}"


def validate_html_syntax_and_ids(
    html_content: str, required_ids: Optional[list[str]] = None
) -> tuple[bool, Optional[str]]:
    """Verify HTML parses cleanly and retains required stable element IDs."""
    parser = ElementIdExtractor()
    try:
        parser.feed(html_content)
    except Exception as e:
        return False, f"HTML parsing error: {e}"

    if required_ids:
        missing = [elem_id for elem_id in required_ids if elem_id not in parser.ids]
        if missing:
            return False, f"Missing required stable DOM IDs: {missing}"

    return True, None


def validate_business_preservation(
    original_code: str, patched_code: str, required_symbols: list[str]
) -> tuple[bool, Optional[str]]:
    """Ensure that essential business logic symbols or variables are preserved."""
    missing = [sym for sym in required_symbols if sym in original_code and sym not in patched_code]
    if missing:
        return False, f"Non-payment business code was removed: {missing}"
    return True, None

