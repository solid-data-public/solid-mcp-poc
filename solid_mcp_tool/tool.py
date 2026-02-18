"""
SolidData MCP text2sql as a CrewAI BaseTool.

Convert natural-language questions into SQL via SolidData's MCP server.
Returns the generated query and explanation only; does not execute SQL.

Environment variables (set in CrewAI Enterprise GUI / AMP):
  SOLIDDATA_MANAGEMENT_KEY  — Required. SolidData management key (MCP-enabled).
  SEMANTIC_LAYER_ID         — Required. Semantic layer ID for text2sql. Must be set in AMP; no fallback.
  AUTH_ENDPOINT            — Optional. Default: production SolidData auth URL.
  MCP_SERVER_URL           — Optional. Default: production SolidData MCP URL.
"""

import asyncio
import os
from typing import Type, Any

try:
    import nest_asyncio
except ImportError:
    nest_asyncio = None

import httpx
from crewai.mcp import MCPClient
from crewai.mcp.transports.http import HTTPTransport
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


DEFAULT_AUTH_ENDPOINT = "https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key"
DEFAULT_MCP_SERVER_URL = "https://mcp.production.soliddata.io/mcp"
MCP_TOOL_TIMEOUT = 30


def _get_semantic_layer_id() -> str:
    """Read SEMANTIC_LAYER_ID from environment (CrewAI AMP). Required; errors if missing."""
    value = os.environ.get("SEMANTIC_LAYER_ID", "").strip()
    if not value:
        raise ValueError(
            "SEMANTIC_LAYER_ID is required. Set it in the CrewAI Enterprise GUI (AMP) tool environment."
        )
    return value


def _get_mcp_token() -> str:
    """Exchange SolidData management key for a bearer token."""
    key = os.environ.get("SOLIDDATA_MANAGEMENT_KEY", "").strip()
    if not key or "your_management_key" in key.lower() or "here" in key.lower():
        raise ValueError(
            "SOLIDDATA_MANAGEMENT_KEY is missing or a placeholder. "
            "Set it in your environment (e.g. .env or CrewAI AMP tool config)."
        )
    auth_url = os.environ.get("AUTH_ENDPOINT", DEFAULT_AUTH_ENDPOINT)
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            auth_url,
            json={"management_key": key},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    if isinstance(data, str):
        token = data.strip()
    elif isinstance(data, dict):
        token = (
            data.get("token")
            or data.get("access_token")
            or data.get("accessToken")
        )
        if not token or not isinstance(token, str):
            raise ValueError("Auth response missing token or access_token.")
    else:
        raise ValueError(f"Unexpected auth response type: {type(data)}")
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def _extract_all_text_from_result(raw: object) -> str:
    """Extract and concatenate text from every content block in an MCP CallToolResult.
    CrewAI's client.call_tool only returns the first block; Solid may return multiple."""
    if hasattr(raw, "content") and raw.content and isinstance(raw.content, list):
        parts = []
        for block in raw.content:
            if hasattr(block, "text") and block.text:
                parts.append(str(block.text).strip())
        if parts:
            return "\n".join(parts)
    return str(raw)


async def _call_solid_text2sql(question: str, semantic_layer_id: str) -> str:
    """Get token, connect to Solid MCP, call text2sql, return result."""
    token = _get_mcp_token()
    mcp_url = os.environ.get("MCP_SERVER_URL", DEFAULT_MCP_SERVER_URL)
    transport = HTTPTransport(
        url=mcp_url,
        headers={"Authorization": f"Bearer {token}"},
        streamable=True,
    )
    client = MCPClient(transport)
    try:
        await client.connect()
        raw = await asyncio.wait_for(
            client.session.call_tool(
                "text2sql",
                {
                    "question": question,
                    "semantic_layer_id": semantic_layer_id,
                },
            ),
            timeout=MCP_TOOL_TIMEOUT,
        )
        return _extract_all_text_from_result(raw)
    finally:
        await client.disconnect()


class SolidText2SQLInput(BaseModel):
    """Input schema for SolidText2SQLTool."""

    question: str = Field(
        ...,
        description="Natural-language question to convert into a SQL query (e.g. 'How many users signed up last month?').",
    )


class SolidText2SQLTool(BaseTool):
    """
    Call SolidData's MCP text2sql tool: convert a natural-language question into SQL.
    Returns the generated SQL and a short explanation. Does not execute the query.
    """

    name: str = "solid_text2sql"
    description: str = (
        "Convert a natural-language data question into a SQL query using SolidData's semantic layer. "
        "Use this when you need to generate SQL from a business question. Returns the SQL and an explanation; does not run the query."
    )
    args_schema: Type[BaseModel] = SolidText2SQLInput

    env_vars: dict = {
        "SOLIDDATA_MANAGEMENT_KEY": "Required. SolidData Management Key.",
        "SEMANTIC_LAYER_ID": "Required. Set in CrewAI Enterprise GUI (AMP); no fallback.",
        "AUTH_ENDPOINT": "Optional. Defaults to production.",
        "MCP_SERVER_URL": "Optional. Defaults to production.",
    }

    def _run(self, question: str = "", **kwargs: Any) -> str:
        """Call Solid MCP text2sql and return the SQL + explanation."""
        if nest_asyncio:
            nest_asyncio.apply()

        q = (question or "").strip() or (kwargs.get("question") and str(kwargs["question"]).strip()) or ""
        if not q:
            return "Error: Input 'question' is missing."

        try:
            layer_id = _get_semantic_layer_id()
        except ValueError as e:
            return str(e)

        try:
            return asyncio.run(_call_solid_text2sql(question=q, semantic_layer_id=layer_id))
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error executing Solid MCP Tool: {str(e)}"


# Alias for CrewAI Enterprise / studio imports that expect this name
SolidMcpTool = SolidText2SQLTool
