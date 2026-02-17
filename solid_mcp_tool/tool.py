"""
SolidData MCP text2sql — CrewAI BaseTool.
"""

import asyncio
import os
from typing import Any, Type

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


class SolidText2SQLInput(BaseModel):
    question: str = Field(..., description="Natural-language data question to convert into SQL.")


class SolidText2SQLTool(BaseTool):
    name: str = "solid_text2sql"
    description: str = (
        "Convert a natural-language data question into SQL using SolidData's semantic layer. "
        "Returns the SQL query."
    )
    args_schema: Type[BaseModel] = SolidText2SQLInput

    env_vars: dict = {
        "SOLIDDATA_MANAGEMENT_KEY": "Required. SolidData Management Key.",
        "SEMANTIC_LAYER_ID": "Required. UUID of the Semantic Layer.",
        "AUTH_ENDPOINT": "Optional. Defaults to production.",
        "MCP_SERVER_URL": "Optional. Defaults to production.",
    }

    def _run(self, question: str, **kwargs: Any) -> str:
        if nest_asyncio:
            nest_asyncio.apply()
        q = (question or "").strip()
        if not q and kwargs.get("question"):
            q = str(kwargs.get("question")).strip()
        sl_id = os.environ.get("SEMANTIC_LAYER_ID", "").strip()
        if not sl_id:
            return (
                "Error: SEMANTIC_LAYER_ID environment variable is missing. "
                "Please check the Tool Configuration in CrewAI Enterprise."
            )
        try:
            return asyncio.run(self._call_mcp(q, sl_id))
        except Exception as e:
            return f"Error executing Solid MCP Tool: {str(e)}"

    async def _call_mcp(self, question: str, semantic_layer_id: str) -> str:
        key = os.environ.get("SOLIDDATA_MANAGEMENT_KEY", "").strip()
        if not key:
            raise ValueError("SOLIDDATA_MANAGEMENT_KEY is missing.")
        auth_url = os.environ.get("AUTH_ENDPOINT", DEFAULT_AUTH_ENDPOINT)
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(
                auth_url,
                json={"management_key": key},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        token = data if isinstance(data, str) else data.get("token") or data.get("access_token")
        if not token:
            raise ValueError("Authentication failed: No token returned.")
        token = token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        mcp_url = os.environ.get("MCP_SERVER_URL", DEFAULT_MCP_SERVER_URL)
        transport = HTTPTransport(
            url=mcp_url,
            headers={"Authorization": f"Bearer {token}"},
            streamable=True,
        )
        async with MCPClient(transport) as client:
            await client.connect()
            result = await client.call_tool(
                "text2sql",
                arguments={"question": question, "semantic_layer_id": semantic_layer_id},
            )
        if isinstance(result, str):
            return result
        if hasattr(result, "content") and isinstance(result.content, list):
            return "\n".join(getattr(c, "text", str(c)) for c in result.content)
        if isinstance(result, list):
            return "\n".join(str(i.get("text", "")) if isinstance(i, dict) else str(i) for i in result)
        return str(result)


SolidMcpTool = SolidText2SQLTool
