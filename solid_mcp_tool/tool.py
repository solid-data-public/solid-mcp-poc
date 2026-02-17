"""
SolidData MCP text2sql — CrewAI BaseTool.

1. Receive {question} from the CrewAI agent.
2. Read SEMANTIC_LAYER_ID from the environment (injected by AMP via env_vars).
3. Call Solid MCP text2sql with both arguments.
"""

import asyncio
import os
from typing import Type

import httpx
from crewai.mcp import MCPClient
from crewai.mcp.transports.http import HTTPTransport
from crewai.tools import BaseTool, EnvVar
from pydantic import BaseModel, Field


DEFAULT_AUTH_ENDPOINT = "https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key"
DEFAULT_MCP_SERVER_URL = "https://mcp.production.soliddata.io/mcp"


def _get_mcp_token() -> str:
    """Exchange SOLIDDATA_MANAGEMENT_KEY for a bearer token."""
    key = os.environ.get("SOLIDDATA_MANAGEMENT_KEY", "").strip()
    if not key:
        raise ValueError("SOLIDDATA_MANAGEMENT_KEY is not set.")
    auth_url = os.environ.get("AUTH_ENDPOINT", DEFAULT_AUTH_ENDPOINT)
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(auth_url, json={"management_key": key}, headers={"Content-Type": "application/json"})
        resp.raise_for_status()
    data = resp.json()
    if isinstance(data, str):
        token = data.strip()
    elif isinstance(data, dict):
        token = data.get("token") or data.get("access_token") or data.get("accessToken")
        if not token:
            raise ValueError("Auth response missing token field.")
    else:
        raise ValueError(f"Unexpected auth response: {type(data)}")
    if token.lower().startswith("bearer "):
        token = token[7:]
    return token.strip()


def _extract_text(result: object) -> str:
    """Pull plain text out of an MCP tool result."""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        parts = []
        for item in result:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif hasattr(item, "text"):
                parts.append(str(item.text))
        return "\n".join(parts) if parts else str(result)
    if isinstance(result, dict):
        if "content" in result:
            return _extract_text(result["content"])
        if "text" in result:
            return str(result["text"])
    if hasattr(result, "content"):
        return _extract_text(result.content)
    return str(result)


class SolidText2SQLInput(BaseModel):
    question: str = Field(..., description="Natural-language data question to convert into SQL.")


class SolidText2SQLTool(BaseTool):
    """Convert a natural-language question into SQL via SolidData MCP text2sql."""

    name: str = "solid_text2sql"
    description: str = (
        "Convert a natural-language data question into a SQL query using SolidData's semantic layer. "
        "Returns the SQL and an explanation; does not run the query."
    )
    args_schema: Type[BaseModel] = SolidText2SQLInput

    env_vars: list[EnvVar] = Field(
        default_factory=lambda: [
            EnvVar(name="SOLIDDATA_MANAGEMENT_KEY", description="SolidData management key for auth", required=True),
            EnvVar(name="SEMANTIC_LAYER_ID", description="Semantic layer ID passed to MCP text2sql", required=True),
            EnvVar(name="AUTH_ENDPOINT", description="Auth endpoint override", required=False),
            EnvVar(name="MCP_SERVER_URL", description="MCP server URL override", required=False),
        ]
    )

    def _run(self, question: str) -> str:
        semantic_layer_id = os.environ.get("SEMANTIC_LAYER_ID", "").strip()
        if not semantic_layer_id:
            return "Error: SEMANTIC_LAYER_ID not set. Configure it in CrewAI tool env vars."

        management_key = os.environ.get("SOLIDDATA_MANAGEMENT_KEY", "").strip()
        if not management_key:
            return "Error: SOLIDDATA_MANAGEMENT_KEY not set."

        if not question.strip():
            return "Error: Question cannot be empty."

        try:
            return asyncio.run(self._call_mcp(question.strip(), semantic_layer_id))
        except Exception as e:
            return f"Error calling MCP server: {str(e)}"

    async def _call_mcp(self, question: str, semantic_layer_id: str) -> str:
        try:
            token = _get_mcp_token()
        except Exception as e:
            return f"Authentication failed: {str(e)}"

        mcp_url = os.environ.get("MCP_SERVER_URL", DEFAULT_MCP_SERVER_URL)
        transport = HTTPTransport(url=mcp_url, headers={"Authorization": f"Bearer {token}"}, streamable=True)
        client = MCPClient(transport)

        try:
            await client.connect()

            print(f"Calling text2sql with question: '{question}' and semantic_layer_id: '{semantic_layer_id}'")

            result = await client.call_tool(
                "text2sql",
                arguments={"question": question, "semantic_layer_id": semantic_layer_id},
            )

            print(f"MCP result: {result}")

            extracted_text = _extract_text(result)
            print(f"Extracted text: {extracted_text}")

            if not extracted_text or extracted_text.strip().lower() in ["question", "null", ""]:
                return f"Error: MCP server returned unexpected result: {extracted_text}"

            return extracted_text

        except Exception as e:
            return f"MCP call failed: {str(e)}"
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass


SolidMcpTool = SolidText2SQLTool
