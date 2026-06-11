# DEPRECATED: This script tests the Azure bridge (REST adapter for low-code consumers).
# For direct MCP testing, use the curl command in AGENT_MIGRATION_INSTRUCTIONS.md.
"""Azure bridge settings from repo openapi.yaml (single source of truth for E2E)."""

from __future__ import annotations

import os
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def openapi_path() -> Path:
    return Path(os.environ.get("OPENAPI_PATH", _REPO_ROOT / "openapi.yaml"))


def _read_openapi_text() -> str:
    path = openapi_path()
    return path.read_text(encoding="utf-8")


def bridge_base_url_from_openapi() -> str:
    text = _read_openapi_text()
    match = re.search(r"servers:\s*\n\s*-\s*url:\s*(\S+)", text)
    if not match:
        raise ValueError(f"Could not find servers.url in {openapi_path()}")
    return match.group(1).rstrip("/")


def bridge_function_key_from_openapi() -> str:
    text = _read_openapi_text()
    match = re.search(
        r'name:\s*code\s*\n\s*in:\s*query.*?default:\s*"([^"]+)"',
        text,
        re.DOTALL,
    )
    if not match:
        raise ValueError(f"Could not find parameters.code default in {openapi_path()}")
    return match.group(1)


def resolve_bridge_base_url() -> str:
    override = os.environ.get("BRIDGE_BASE_URL", "").strip().rstrip("/")
    if override:
        return override
    return bridge_base_url_from_openapi()


def resolve_bridge_function_key() -> str:
    override = os.environ.get("BRIDGE_FUNCTION_KEY", "").strip().strip('"').strip("'")
    if override:
        return override
    return bridge_function_key_from_openapi()


def append_bridge_code(url: str, function_key: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}code={function_key}"


def url_without_query(url: str) -> str:
    """Path-only URL for logs (never print the code query param)."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
