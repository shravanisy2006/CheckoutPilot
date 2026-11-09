"""
Multi-language syntax and preservation validators for Code Patcher.
Ensures zero disruption to non-payment business code and stable DOM IDs
across Python, JavaScript, TypeScript, HTML, CSS, and JSON.
"""

import ast
import json
from html.parser import HTMLParser
from pathlib import Path
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


def validate_balanced_brackets(code: str) -> tuple[bool, Optional[str]]:
    """Check balanced braces, brackets, and parentheses in JS/TS/CSS/JSON."""
    stack = []
    pairs = {")": "(", "}": "{", "]": "["}
    in_single_quote = False
    in_double_quote = False
    in_backtick = False
    escaped = False

    for idx, char in enumerate(code):
        if escaped:
            escaped = False
            continue

        if char == "\\":
            escaped = True
            continue

        if char == "'" and not in_double_quote and not in_backtick:
            in_single_quote = not in_single_quote
            continue
        if char == '"' and not in_single_quote and not in_backtick:
            in_double_quote = not in_double_quote
            continue
        if char == "`" and not in_single_quote and not in_double_quote:
            in_backtick = not in_backtick
            continue

        if in_single_quote or in_double_quote or in_backtick:
            continue

        if char in "({[":
            stack.append((char, idx))
        elif char in ")}]":
            if not stack:
                return False, f"Unmatched closing bracket '{char}' at character {idx}"
            last, last_idx = stack.pop()
            if pairs[char] != last:
                return False, f"Mismatched bracket: expected '{last}' matching pos {last_idx}, got '{char}' at pos {idx}"

    if stack:
        last, last_idx = stack[-1]
        return False, f"Unclosed bracket '{last}' opened at character {last_idx}"

    return True, None


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


def validate_code_syntax(code: str, file_path: str | Path) -> tuple[bool, Optional[str]]:
    """Validate syntax based on file extension."""
    suffix = Path(file_path).suffix.lower()

    if suffix == ".py":
        return validate_python_syntax(code)

    if suffix == ".json":
        try:
            json.loads(code)
            return True, None
        except Exception as e:
            return False, f"Invalid JSON: {e}"

    if suffix in (".html", ".htm", ".jinja", ".jinja2"):
        return validate_html_syntax_and_ids(code)

    if suffix in (".js", ".jsx", ".ts", ".tsx", ".css"):
        return validate_balanced_brackets(code)

    return True, None


def validate_business_preservation(
    original_code: str, patched_code: str, required_symbols: Optional[list[str]] = None
) -> tuple[bool, Optional[str]]:
    """
    Ensure that essential business logic symbols or variables are preserved.
    Automatically extracts product and pricing keywords if no specific list is passed.
    """
    symbols = required_symbols or []

    # If no specific symbols provided, auto-detect critical variable keywords in the original code
    if not symbols:
        for keyword in ("PRODUCTS", "products", "calculate_total", "calcTotal", "total_price", "pricing", "catalog", "items"):
            if keyword in original_code:
                symbols.append(keyword)

    missing = [sym for sym in symbols if sym in original_code and sym not in patched_code]
    if missing:
        return False, f"Critical business code was removed: {missing}"

    return True, None
