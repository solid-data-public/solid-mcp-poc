import asyncio
import os
from typing import Type, Optional, Any

try:
    import nest_asyncio
except ImportError:
    nest_asyncio = None

import httpx
from crewai.mcp import MCPClient
from crewai.mcp.transports.http import HTTPTransport
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


def _extract_mcp_text(result: Any) -> str:
    """Extract readable text from MCP tool result."""
    if not result:
        return ""
    if isinstance(result, str):
        return result
    if hasattr(result, "content") and isinstance(result.content, list):
        return "\n".join([getattr(c, "text", str(c)) for c in result.content])
    if isinstance(result, list):
        return "\n".join([str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in result])
    return str(result)


class SolidText2SQLInput(BaseModel):
    """Input for the SolidText2SQL tool."""
    question: str = Field(
        ...,
        description="Natural-language question to convert into a SQL query.",
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
        "SEMANTIC_LAYER_ID": "Required. UUID of the Semantic Layer.",
        "AUTH_ENDPOINT": "Optional. Defaults to production.",
        "MCP_SERVER_URL": "Optional. Defaults to production.",
    }

    def _run(
        self,
        question: str = "",
        semantic_layer_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        if nest_asyncio:
            nest_asyncio.apply()

        q = (question or "").strip() or (kwargs.get("question") and str(kwargs["question"]).strip()) or ""
        if not q:
            return "Error: Input 'question' is missing."

        mgmt_key = os.environ.get("SOLIDDATA_MANAGEMENT_KEY")
        layer_id = semantic_layer_id or os.environ.get("SEMANTIC_LAYER_ID") or os.environ.get("SEMANTIC_MODEL_ID")
        layer_id = (layer_id or "").strip()
        if not layer_id:
            return "Error: SEMANTIC_LAYER_ID is missing. Set it in Tool Configuration or pass semantic_layer_id."

        auth_url = os.environ.get("AUTH_ENDPOINT", "https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key")
        mcp_url = os.environ.get("MCP_SERVER_URL", "https://mcp.production.soliddata.io/mcp")

        if not (mgmt_key and mgmt_key.strip()):
            return "Error: SOLIDDATA_MANAGEMENT_KEY is missing."

        # Exchange token
        try:
            response = httpx.post(auth_url, json={"management_key": mgmt_key}, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            token = data if isinstance(data, str) else (data.get("token") or data.get("access_token"))
            if not token:
                return "Error: No token in auth response."
            token = str(token).strip()
            if token.lower().startswith("bearer "):
                token = token.split(" ", 1)[1]
        except Exception as e:
            return f"Error getting token: {str(e)}"

        async def make_call():
            transport = HTTPTransport(url=mcp_url, headers={"Authorization": f"Bearer {token}"})
            async with MCPClient(transport) as client:
                await client.connect()
                result = await client.call_tool(
                    "text2sql",
                    arguments={"question": q, "semantic_layer_id": layer_id},
                )
                return _extract_mcp_text(result)

        try:
            return str(asyncio.run(make_call()))
        except Exception as e:
            return f"Error executing Solid MCP Tool: {str(e)}"


# Alias for code that imports the descriptive name
SolidText2SQLTool = SolidMcpTool