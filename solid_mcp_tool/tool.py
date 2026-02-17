import os
import asyncio
import httpx
from crewai.tools import BaseTool
from crewai.mcp import MCPClient
from crewai.mcp.transports.http import HTTPTransport
from pydantic import BaseModel, Field

class SolidText2SQLInput(BaseModel):
    question: str = Field(..., description="The natural language data question.")

class SolidText2SQLTool(BaseTool):
    name: str = "solid_text2sql"
    description: str = "Converts question to SQL using SolidData Semantic Layer."
    args_schema: type[BaseModel] = SolidText2SQLInput

    def _run(self, question: str) -> str:
        # 1. Env (same as soliddata_mcp_poc config)
        mgmt_key = os.environ.get("SOLIDDATA_MANAGEMENT_KEY")
        layer_id = os.environ.get("SEMANTIC_LAYER_ID")
        auth_url = os.environ.get("AUTH_ENDPOINT", "https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key")
        mcp_url = os.environ.get("MCP_SERVER_URL", "https://mcp.production.soliddata.io/mcp")

        if not mgmt_key or not mgmt_key.strip():
            raise ValueError("SOLIDDATA_MANAGEMENT_KEY is missing or empty. Set it in .env (see .env.example).")
        if not layer_id or not layer_id.strip():
            raise ValueError("SEMANTIC_LAYER_ID is missing or empty. Set it in .env.")

        # 2. Exchange token (same as soliddata_mcp_poc auth.py)
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                auth_url,
                json={"management_key": mgmt_key},
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 401:
                raise ValueError(
                    "SolidData returned 401 Unauthorized. Check SOLIDDATA_MANAGEMENT_KEY and auth endpoint (e.g. dev vs prod)."
                )
            resp.raise_for_status()
        data = resp.json()
        if not data:
            raise ValueError("Auth endpoint returned empty response.")
        if isinstance(data, str):
            token = data.strip()
        else:
            token = data.get("token") or data.get("access_token") or data.get("accessToken")
            if not token or not isinstance(token, str):
                raise ValueError("Auth response has no 'token' or 'access_token' field.")
        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        # 3. Call MCP (same URL + Bearer as crew’s MCPServerHTTP; same tool/args as crew task)
        async def make_call():
            transport = HTTPTransport(url=mcp_url, headers={"Authorization": f"Bearer {token}"})
            async with MCPClient(transport) as client:
                await client.connect()
                result = await client.call_tool(
                    "text2sql",
                    arguments={"question": question, "semantic_layer_id": layer_id},
                )
                return result

        raw = asyncio.run(make_call())
        # MCP call_tool returns an object with .content (list of items with .text)
        if hasattr(raw, "content") and isinstance(raw.content, list):
            return "\n".join(getattr(c, "text", str(c)) for c in raw.content)
        return str(raw)
    
SolidMcpTool = SolidText2SQLTool