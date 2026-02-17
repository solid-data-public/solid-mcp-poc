"""
SolidData MCP text2sql as a CrewAI BaseTool.

Use this tool in CrewAI agents to convert natural-language questions into SQL
via SolidData's MCP server. No SQL is executed; the tool returns the generated
query and explanation only.

Environment variables (set in .env or CrewAI AMP):
  SOLIDDATA_MANAGEMENT_KEY  — SolidData management key (required, MCP-enabled).
  SEMANTIC_LAYER_ID        — Semantic layer ID for text2sql (required; set in .env).
  AUTH_ENDPOINT            — Optional. Default: production SolidData auth URL.
  MCP_SERVER_URL           — Optional. Default: production SolidData MCP URL.
"""

import asyncio
import os
from typing import Type

import httpx
from crewai.mcp import MCPClient
from crewai.mcp.transports.http import HTTPTransport
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# Default SolidData production endpoints
DEFAULT_AUTH_ENDPOINT = "https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key"
DEFAULT_MCP_SERVER_URL = "https://mcp.production.soliddata.io/mcp"


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


def _get_semantic_layer_id() -> str:
    """Read semantic layer ID from environment; raise if missing."""
    value = os.environ.get("SEMANTIC_LAYER_ID", "").strip()
    if not value:
        raise ValueError(
            "SEMANTIC_LAYER_ID is missing. Set it in your .env (or CrewAI AMP tool config)."
        )
    return value


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

    def _run(self, question: str) -> str:
        """Call Solid MCP text2sql and return the SQL + explanation. Always uses SEMANTIC_LAYER_ID from .env."""
        layer_id = _get_semantic_layer_id()
        return asyncio.run(
            _call_solid_text2sql(question=question, semantic_layer_id=layer_id)
        )


# Alias for CrewAI scaffold / AMP: Studio may reference the default name from tool create.
SolidMcpTool = SolidText2SQLTool


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
        result = await client.call_tool(
            "text2sql",
            arguments={
                "question": question,
                "semantic_layer_id": semantic_layer_id,
            },
        )
        return result if isinstance(result, str) else str(result)
    finally:
        await client.disconnect()
