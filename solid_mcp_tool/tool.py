import os
from typing import Type, Optional, Any

import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# Auth exchange, then bridge calls (Bearer + JSON) for text2sql / glossary.
AUTH_ENDPOINT_DEFAULT = "https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key"
BRIDGE_BASE = "https://solid-mcp-bridge-efeqgrayfnhvbsf0.eastus2-01.azurewebsites.net/api/mcp"
BRIDGE_FUNCTION_KEY_DEFAULT = "DnqGmyuh1gnv_ow4xE5O7sPBO80MXZeUTosP_rIFxIFyAzFu_Y3Xpg=="
TEXT2SQL_URL = f"{BRIDGE_BASE}/text2sql?code={BRIDGE_FUNCTION_KEY_DEFAULT}"
GLOSSARY_URL = f"{BRIDGE_BASE}/glossary?code={BRIDGE_FUNCTION_KEY_DEFAULT}"


def _get_mcp_token(management_key: Optional[str] = None, timeout: float = 30.0) -> str:
    """Same logic as soliddata_mcp_poc.auth.get_mcp_token: exchange management key for bearer token."""
    key = (management_key or "").strip() or (os.environ.get("SOLIDDATA_MANAGEMENT_KEY") or "").strip()
    if not key:
        raise ValueError(
            "SOLIDDATA_MANAGEMENT_KEY is missing or empty. "
            "Set it in your .env file (see .env.example)."
        )
    if "your_management_key" in key.lower() or "here" in key.lower():
        raise ValueError(
            "SOLIDDATA_MANAGEMENT_KEY looks like a placeholder. "
            "Replace it in .env with your real SolidData management key."
        )
    auth_endpoint = os.environ.get("AUTH_ENDPOINT", AUTH_ENDPOINT_DEFAULT)
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            auth_endpoint,
            json={"management_key": key},
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 401:
            raise ValueError(
                "SolidData returned 401 Unauthorized. "
                "Check that SOLIDDATA_MANAGEMENT_KEY in .env is correct, not expired, "
                "and valid for the auth endpoint (e.g. dev vs prod)."
            ) from None
        resp.raise_for_status()
    data = resp.json()
    if not data:
        raise ValueError(f"Auth endpoint returned empty response. Status {resp.status_code}")
    if isinstance(data, str):
        token = data.strip()
    elif isinstance(data, dict):
        token = (
            data.get("token")
            or data.get("access_token")
            or data.get("accessToken")
        )
        if not token or not isinstance(token, str):
            raise ValueError(
                "Auth endpoint returned a JSON object but no 'token' or 'access_token' field."
            )
    else:
        raise ValueError(f"Unexpected auth response type: {type(data)}")
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


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
        "SOLIDDATA_MANAGEMENT_KEY": "Required. SolidData Management Key (exchanged for JWT in step 1).",
        "SEMANTIC_LAYER_ID": "Optional. Fallback for semantic_layer_id if not passed.",
        "AUTH_ENDPOINT": "Optional. Auth exchange URL (default from openapi.yaml).",
        "TEXT2SQL_URL": "Optional. Bridge text2sql URL with ?code= (default BRIDGE_BASE/text2sql?code=...).",
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

        try:
            token = _get_mcp_token()
        except ValueError as e:
            return str(e)

        url = os.environ.get("TEXT2SQL_URL", TEXT2SQL_URL)
        payload = {"question": q, "semantic_layer_ids": [layer_id]}

        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
            if resp.status_code == 401:
                return (
                    "Error: Solid returned 401. Check that SOLIDDATA_MANAGEMENT_KEY "
                    "is correct and not expired."
                )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "message" in data:
                return data["message"]
            return str(data) if data else "Error: Empty response from bridge."
        except httpx.HTTPStatusError as e:
            return f"Error from bridge: {e.response.status_code} {e.response.text}"
        except Exception as e:
            return f"Error executing Solid MCP Tool: {str(e)}"


# Alias for code that imports the descriptive name
SolidText2SQLTool = SolidMcpTool


class SolidGlossarySearchInput(BaseModel):
    """Input for the Solid glossary search tool."""

    query: str = Field(
        ...,
        description="Natural-language question or term to look up in the SolidData glossary.",
    )


class SolidGlossarySearchTool(BaseTool):
    """CrewAI tool that calls SolidData MCP glossary_search via the same bridge + Bearer pattern as text2sql."""

    name: str = "solid_glossary_search"
    description: str = (
        "Look up definitions, acronyms, and business terms in SolidData's glossary. "
        "Use this for 'what does X mean?' or terminology questions — not for generating SQL."
    )
    args_schema: Type[BaseModel] = SolidGlossarySearchInput

    env_vars: dict = {
        "SOLIDDATA_MANAGEMENT_KEY": "Required. SolidData Management Key (exchanged for JWT).",
        "AUTH_ENDPOINT": "Optional. Auth exchange URL (default from openapi.yaml).",
        "GLOSSARY_URL": "Optional. Bridge glossary URL with ?code= (default BRIDGE_BASE/glossary?code=...).",
    }

    def _run(self, query: str = "", **kwargs: Any) -> str:
        q = (query or "").strip() or (kwargs.get("query") and str(kwargs["query"]).strip()) or ""
        if not q:
            return "Error: Input 'query' is missing."

        try:
            token = _get_mcp_token()
        except ValueError as e:
            return str(e)

        url = os.environ.get("GLOSSARY_URL", GLOSSARY_URL)
        payload = {"query": q}

        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
            if resp.status_code == 401:
                return (
                    "Error: Solid returned 401. Check that SOLIDDATA_MANAGEMENT_KEY "
                    "is correct and not expired."
                )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "result" in data:
                inner = data["result"]
                if isinstance(inner, dict):
                    parts = []
                    if inner.get("synthesized_answer"):
                        parts.append(str(inner["synthesized_answer"]))
                    if inner.get("answer_status"):
                        parts.append(f"(status: {inner['answer_status']})")
                    if inner.get("execution_error"):
                        parts.append(f"Error: {inner['execution_error']}")
                    return "\n".join(parts) if parts else str(inner)
                return str(inner) if inner is not None else "Error: Empty glossary result."
            return str(data) if data else "Error: Empty response from bridge."
        except httpx.HTTPStatusError as e:
            return f"Error from bridge: {e.response.status_code} {e.response.text}"
        except Exception as e:
            return f"Error executing Solid glossary tool: {str(e)}"


SolidMcpGlossaryTool = SolidGlossarySearchTool