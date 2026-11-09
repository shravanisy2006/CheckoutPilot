"""
LLM-Driven Code Synthesizer: contextually patches any file across any tech stack
(Node.js/Express, Next.js/React, Django, Flask, PHP, HTML) while enforcing syntax
and business logic preservation.
"""

from pathlib import Path
from typing import Optional

from code_agent.agentic.paypal_knowledge import PAYPAL_V6_KNOWLEDGE_BASE
from code_agent.llm_client import BaseLLMAdapter, get_llm_client
from code_agent.patcher.validators import (
    validate_business_preservation,
    validate_code_syntax,
)


def synthesize_file_patch(
    file_path: str | Path,
    original_content: str,
    change_description: str,
    llm: Optional[BaseLLMAdapter] = None,
) -> Optional[str]:
    """
    Use the LLM to contextually apply PayPal v6 modernization to a file
    in any programming language or framework.
    """
    client = llm or get_llm_client()
    if not client or not client.is_available() or type(client).__name__ == "DeterministicFallbackAdapter":
        return None

    system_prompt = (
        "You are an expert full-stack software engineer specializing in payment integrations.\n"
        "Your task: Update the provided file to modern PayPal JavaScript SDK v6 standards according to the handbook.\n\n"
        f"{PAYPAL_V6_KNOWLEDGE_BASE}\n\n"
        "STRICT CONSTRAINTS:\n"
        "1. Implement the requested payment modernization cleanly in the file's native language/framework.\n"
        "2. PRESERVE all existing non-payment business code: product catalogs, pricing calculation, database models, shipping inputs, other gateways.\n"
        "3. PRESERVE all existing stable element IDs and form attributes.\n"
        "4. Return ONLY the complete updated file content wrapped in a single ```code block. No conversational text."
    )

    user_prompt = (
        f"File Path: {file_path}\n"
        f"Requested Upgrade: {change_description}\n\n"
        f"Original File Content:\n"
        f"```\n{original_content}\n```\n\n"
        "Generate the complete modernized file:"
    )

    generated = client.generate_text(user_prompt, system_prompt=system_prompt)
    if not generated:
        return None

    # Strip code fences
    cleaned = generated.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        if len(parts) >= 2:
            cleaned = parts[1]
            # Strip language specifier (e.g. ```javascript, ```python)
            lines = cleaned.splitlines()
            if lines and lines[0].strip().isalpha():
                cleaned = "\n".join(lines[1:])

    code = cleaned.strip()

    # Safety validation 1: Syntax
    valid_syntax, syn_err = validate_code_syntax(code, file_path)
    if not valid_syntax:
        return None

    # Safety validation 2: Business preservation
    preserved, pres_err = validate_business_preservation(original_content, code)
    if not preserved:
        return None

    return code

