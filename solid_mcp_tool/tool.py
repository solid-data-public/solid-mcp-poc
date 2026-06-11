import asyncio
import os
from typing import Any, Optional, Type

try:
    import nest_asyncio
except ImportError:
    nest_asyncio = None

from crewai.mcp import MCPClient
from crewai.mcp.transports.http import HTTPTransport
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# Same defaults as soliddata_mcp_poc.config.Settings (crew flow)
_DEFAULT_MCP_SERVER_URL = "https://mcp.production.soliddata.io/mcp"

# Long-running MCP tools (text2sql / glossary) need generous timeouts vs client defaults.
_MCP_CONNECT_TIMEOUT = 60
_MCP_TOOL_TIMEOUT = 120


def _run_mcp_tool_sync(tool_name: str, arguments: dict[str, Any]) -> str:
    """Connect to Solid MCP over HTTP (streamable), call one tool, disconnect."""
    if nest_asyncio:
        nest_asyncio.apply()

    mcp_url = os.environ.get("MCP_SERVER_URL", _DEFAULT_MCP_SERVER_URL)
    mgmt_key = (os.environ.get("SOLIDDATA_MANAGEMENT_KEY") or "").strip()
    if not mgmt_key:
        return "SOLIDDATA_MANAGEMENT_KEY is missing or empty."

    async def _call() -> str:
        transport = HTTPTransport(
            url=mcp_url,
            headers={"x-solid-management-key": mgmt_key},
            streamable=True,
        )
        client = MCPClient(
            transport,
            connect_timeout=_MCP_CONNECT_TIMEOUT,
            execution_timeout=_MCP_TOOL_TIMEOUT,
        )
        try:
            await client.connect()
            result = await client.call_tool(tool_name, arguments)
            return result if isinstance(result, str) else str(result)
        finally:
            await client.disconnect()

    try:
        return asyncio.run(_call())
    except Exception as e:
        return f"Error executing Solid MCP tool ({tool_name}): {str(e)}"


class SolidText2SQLInput(BaseModel):
    """Input for the SolidText2SQL tool."""

    question: str = Field(
        ...,
        description="Natural-language question to convert into a SQL query.",
    )
    semantic_layer_id: str = Field(
        ...,
        description="UUID of the SolidData semantic layer. Passed to the MCP as semantic_layer_ids.",
    )


class SolidMcpTool(BaseTool):
    """CrewAI tool that calls SolidData MCP text2sql. Use this name for CrewAI Studio/Enterprise imports."""

    name: str = "solid_text2sql"
    description: str = (
        "Convert a natural-language data question into a SQL query using SolidData's semantic layer. "
        "Returns the generated SQL and a short explanation."
    )
    args_schema: Type[BaseModel] = SolidText2SQLInput

    env_vars: dict = {
        "SOLIDDATA_MANAGEMENT_KEY": "Required. SolidData Management Key.",
        "SEMANTIC_LAYER_ID": "Optional. Fallback for semantic_layer_id if not passed.",
        "MCP_SERVER_URL": "Optional. Solid MCP HTTP URL. Defaults to production.",
    }

    def _run(
        self,
        question: str = "",
        semantic_layer_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        q = (question or "").strip() or (kwargs.get("question") and str(kwargs["question"]).strip()) or ""
        if not q:
            return "Error: Input 'question' is missing."

        layer_id = (
            (semantic_layer_id or "").strip()
            or (kwargs.get("semantic_layer_id") or "").strip()
            or (os.environ.get("SEMANTIC_LAYER_ID") or os.environ.get("SEMANTIC_MODEL_ID") or "").strip()
        )
        if not layer_id:
            return "Error: semantic_layer_id is missing. Pass it as an argument or set SEMANTIC_LAYER_ID."

        return _run_mcp_tool_sync(
            "text2sql",
            {"question": q, "semantic_layer_ids": [layer_id]},
        )


SolidText2SQLTool = SolidMcpTool


class SolidGlossarySearchInput(BaseModel):
    """Input for the Solid glossary search tool."""

    query: str = Field(
        ...,
        description="Natural-language question or term to look up in the SolidData glossary.",
    )


class SolidGlossarySearchTool(BaseTool):
    """CrewAI tool that calls SolidData MCP glossary_search (same transport as SolidMcpTool)."""

    name: str = "solid_glossary_search"
    description: str = (
        "Look up definitions, acronyms, and business terms in SolidData's glossary. "
        "Use this for 'what does X mean?' or terminology questions — not for generating SQL."
    )
    args_schema: Type[BaseModel] = SolidGlossarySearchInput

    env_vars: dict = {
        "SOLIDDATA_MANAGEMENT_KEY": "Required. SolidData Management Key.",
        "MCP_SERVER_URL": "Optional. Solid MCP HTTP URL. Defaults to production.",
    }

    def _run(self, query: str = "", **kwargs: Any) -> str:
        q = (query or "").strip() or (kwargs.get("query") and str(kwargs["query"]).strip()) or ""
        if not q:
            return "Error: Input 'query' is missing."

        return _run_mcp_tool_sync("glossary_search", {"query": q})


SolidMcpGlossaryTool = SolidGlossarySearchTool
