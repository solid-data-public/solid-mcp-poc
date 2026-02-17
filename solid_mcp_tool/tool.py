"""
SolidData MCP text2sql as a CrewAI BaseTool.

The tool accepts only "question" from the agent. semantic_layer_id is read only
from the SEMANTIC_LAYER_ID environment variable in the tool's environment and
passed to the MCP server—never from the agent or tool args (avoids the agent
passing the literal string "SEMANTIC_LAYER_ID"). Set env vars in Crew Studio /
Enterprise tool config.

Environment variables (set in .env or CrewAI Enterprise tool config):
  SOLIDDATA_MANAGEMENT_KEY  — SolidData management key (required, MCP-enabled).
  SEMANTIC_LAYER_ID        — Semantic layer ID for text2sql (required).
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
    """Raw SEMANTIC_LAYER_ID from .env; passed as MCP tool argument semantic_layer_id."""
    value = os.environ.get("SEMANTIC_LAYER_ID", "").strip()
    if not value:
        raise ValueError("SEMANTIC_LAYER_ID is missing. Set it in your .env (or CrewAI tool config).")
    return value


def _normalize_question(question: object, kwargs: object) -> str:
    """Normalize question from _run(question=..., **kwargs). Handles Enterprise passing a single input dict."""
    if question is not None and isinstance(question, str) and question.strip():
        return question.strip()
    if question is not None and isinstance(question, dict):
        q = question.get("question")
        if q is not None and str(q).strip():
            return str(q).strip()
    if isinstance(kwargs, dict):
        q = kwargs.get("question")
        if q is not None and str(q).strip():
            return str(q).strip()
    return ""


class SolidText2SQLInput(BaseModel):
    """Input schema: only question. semantic_layer_id is read from env inside the tool and never from the agent."""

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

    def _run(self, question: str = "", **kwargs: object) -> str:
        """Call Solid MCP text2sql. semantic_layer_id is always read from SEMANTIC_LAYER_ID in the tool's environment."""
        question = _normalize_question(question, kwargs)
        if not (question and str(question).strip()):
            return "Error: missing 'question' input. Call this tool with {\"question\": \"your natural-language data question\"}."
        try:
            layer_id = _get_semantic_layer_id()
        except ValueError as e:
            return f"Error: {e}"
        return asyncio.run(
            _call_solid_text2sql(question=str(question).strip(), semantic_layer_id=layer_id)
        )


# Alias for CrewAI scaffold / AMP: Studio may reference the default name from tool create.
SolidMcpTool = SolidText2SQLTool


def _extract_mcp_tool_text(result: object) -> str:
    """Extract display text from MCP call_tool result (content array or plain string)."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, list):
        parts = []
        for item in result:
            if isinstance(item, dict):
                text = item.get("text")
                if text is not None:
                    parts.append(str(text).strip())
            elif hasattr(item, "text"):
                parts.append(str(getattr(item, "text", "")).strip())
        if parts:
            return "\n".join(parts)
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            return _extract_mcp_tool_text(content)
        text = result.get("text")
        if text is not None:
            return _extract_mcp_tool_text(text)
        inner = result.get("result")
        if isinstance(inner, dict):
            return _extract_mcp_tool_text(inner)
    if hasattr(result, "content"):
        return _extract_mcp_tool_text(getattr(result, "content"))
    return str(result).strip()


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
                "semantic_layer_id": semantic_layer_id,  # raw value from SEMANTIC_LAYER_ID in .env
            },
        )
        return _extract_mcp_tool_text(result)
    finally:
        await client.disconnect()
