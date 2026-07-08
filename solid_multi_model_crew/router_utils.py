"""Heuristics for detecting router / text2sql failures."""

from __future__ import annotations


def router_output_indicates_failure(output: str) -> bool:
    """True when router mode did not produce usable SQL."""
    text = (output or "").strip()
    if not text:
        return True

    lower = text.lower()

    hard_failures = (
        "error executing solid mcp",
        '"status": "error"',
        "'status': 'error'",
        "status=error",
        "no certified",
        "could not route",
        "unauthorized",
        "failed to generate",
        "validation_errors",
        "execution_error",
        "input 'question' is missing",
        "solidmanagement_key is missing",
    )
    if any(phrase in lower for phrase in hard_failures):
        return True

    has_select = "select" in lower
    has_sql_field = "sql_query" in lower or "generated_sql" in lower

    if has_select and (has_sql_field or "```sql" in lower):
        return False

    soft_failures = (
        "no sql",
        "did not return",
        "unable to",
        "cannot answer",
        "no model",
        "not confident",
    )
    if any(phrase in lower for phrase in soft_failures):
        return True

    return not has_select
