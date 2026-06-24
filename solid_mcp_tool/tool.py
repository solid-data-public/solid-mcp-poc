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

# Long-running MCP tools need generous timeouts vs client defaults.
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
            or (os.environ.get("SEMANTIC_LAYER_ID") or "").strip()
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


class SolidSpecificAssetInformationInput(BaseModel):
    """Input for the Solid specific asset information tool."""

    question: str = Field(
        ...,
        description="Natural-language question about the named table or dashboard.",
    )
    asset_name: str = Field(
        ...,
        description="Exact name of the table or dashboard (e.g. database.schema.table).",
    )
    asset_type: Optional[str] = Field(
        default=None,
        description="Optional asset type hint (e.g. table, dashboard).",
    )


class SolidSpecificAssetInformationTool(BaseTool):
    """CrewAI tool that calls SolidData MCP specific_asset_information_tool."""

    name: str = "solid_specific_asset_information"
    description: str = (
        "Get metadata and natural-language answers about one named table or dashboard. "
        "Use when the user asks about columns, schema, or structure of a specific asset."
    )
    args_schema: Type[BaseModel] = SolidSpecificAssetInformationInput

    env_vars: dict = {
        "SOLIDDATA_MANAGEMENT_KEY": "Required. SolidData Management Key.",
        "MCP_SERVER_URL": "Optional. Solid MCP HTTP URL. Defaults to production.",
        "ASSET_NAME": "Optional. Fallback for asset_name if not passed.",
        "ASSET_TYPE": "Optional. Fallback for asset_type if not passed.",
    }

    def _run(
        self,
        question: str = "",
        asset_name: Optional[str] = None,
        asset_type: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        q = (question or "").strip() or (kwargs.get("question") and str(kwargs["question"]).strip()) or ""
        if not q:
            return "Error: Input 'question' is missing."

        name = (
            (asset_name or "").strip()
            or (kwargs.get("asset_name") or "").strip()
            or (os.environ.get("ASSET_NAME") or "").strip()
        )
        if not name:
            return "Error: asset_name is missing. Pass it as an argument or set ASSET_NAME."

        arguments: dict[str, Any] = {"question": q, "asset_name": name}
        atype = (
            (asset_type or "").strip()
            or (kwargs.get("asset_type") or "").strip()
            or (os.environ.get("ASSET_TYPE") or "").strip()
        )
        if atype:
            arguments["asset_type"] = atype

        return _run_mcp_tool_sync("specific_asset_information_tool", arguments)


SolidMcpAssetTool = SolidSpecificAssetInformationTool


class SolidSemanticModelQAInput(BaseModel):
    """Input for the Solid semantic model Q&A tool."""

    question: str = Field(
        ...,
        description="Natural-language question about the semantic model metadata.",
    )
    semantic_model_id: str = Field(
        ...,
        description="UUID of the SolidData semantic model.",
    )


class SolidSemanticModelQATool(BaseTool):
    """CrewAI tool that calls SolidData MCP semantic_model_qa."""

    name: str = "solid_semantic_model_qa"
    description: str = (
        "Answer questions about a semantic model's metadata — coverage, tables, metrics, and structure. "
        "Use when the user asks what a model contains or how it is organized."
    )
    args_schema: Type[BaseModel] = SolidSemanticModelQAInput

    env_vars: dict = {
        "SOLIDDATA_MANAGEMENT_KEY": "Required. SolidData Management Key.",
        "MCP_SERVER_URL": "Optional. Solid MCP HTTP URL. Defaults to production.",
        "SEMANTIC_MODEL_ID": "Optional. Fallback for semantic_model_id if not passed.",
    }

    def _run(
        self,
        question: str = "",
        semantic_model_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        q = (question or "").strip() or (kwargs.get("question") and str(kwargs["question"]).strip()) or ""
        if not q:
            return "Error: Input 'question' is missing."

        model_id = (
            (semantic_model_id or "").strip()
            or (kwargs.get("semantic_model_id") or "").strip()
            or (os.environ.get("SEMANTIC_MODEL_ID") or "").strip()
        )
        if not model_id:
            return "Error: semantic_model_id is missing. Pass it as an argument or set SEMANTIC_MODEL_ID."

        return _run_mcp_tool_sync(
            "semantic_model_qa",
            {"question": q, "semantic_model_id": model_id},
        )


SolidMcpSemanticModelQATool = SolidSemanticModelQATool
