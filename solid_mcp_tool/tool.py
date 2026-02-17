"""
SolidData MCP text2sql — CrewAI BaseTool.

1. Receive {question} from the CrewAI agent.
2. Read SEMANTIC_LAYER_ID from env (injected by AMP via env_vars).
3. Call Solid MCP text2sql with both arguments.
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
from crewai.tools import BaseTool, EnvVar
from pydantic import BaseModel, Field


DEFAULT_AUTH_ENDPOINT = "https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key"
DEFAULT_MCP_SERVER_URL = "https://mcp.production.soliddata.io/mcp"


class SolidText2SQLInput(BaseModel):
    question: str = Field(..., description="Natural-language data question to convert into SQL.")


class SolidText2SQLTool(BaseTool):
    name: str = "solid_text2sql"
    description: str = "Convert a natural-language data question into SQL using SolidData's semantic layer."
    args_schema: Type[BaseModel] = SolidText2SQLInput

    env_vars: list[EnvVar] = Field(
        default_factory=lambda: [
            EnvVar(name="SOLIDDATA_MANAGEMENT_KEY", description="SolidData management key for auth", required=True),
            EnvVar(name="SEMANTIC_LAYER_ID", description="Semantic layer ID passed to MCP text2sql", required=True),
            EnvVar(name="AUTH_ENDPOINT", description="Auth endpoint override", required=False),
            EnvVar(name="MCP_SERVER_URL", description="MCP server URL override", required=False),
        ]
    )

    def _run(self, question: str, **kwargs: Any) -> str:
        if nest_asyncio:
            nest_asyncio.apply()
        sl_id = os.environ.get("SEMANTIC_LAYER_ID", "").strip()
        return asyncio.run(self._call_mcp(question.strip(), sl_id))

    async def _call_mcp(self, question: str, semantic_layer_id: str) -> str:
        key = os.environ.get("SOLIDDATA_MANAGEMENT_KEY", "").strip()
        auth_url = os.environ.get("AUTH_ENDPOINT", DEFAULT_AUTH_ENDPOINT)
        with httpx.Client(timeout=30.0) as http:
            resp = http.post(auth_url, json={"management_key": key}, headers={"Content-Type": "application/json"})
            resp.raise_for_status()
        data = resp.json()
        token = data if isinstance(data, str) else data.get("token") or data.get("access_token")
        token = token.strip().removeprefix("Bearer ").removeprefix("bearer ").strip()

        mcp_url = os.environ.get("MCP_SERVER_URL", DEFAULT_MCP_SERVER_URL)
        transport = HTTPTransport(url=mcp_url, headers={"Authorization": f"Bearer {token}"}, streamable=True)
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
