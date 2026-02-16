"""
Snowflake MCP Tool for CrewAI integration.

This tool provides access to Snowflake's Model Context Protocol (MCP) server,
allowing agents to interact with Snowflake data repositories, Cortex Search,
Cortex Analyst, SQL execution, and Cortex Agents.
"""

import json
from typing import Any, Dict, List, Optional, Type

import requests
from pydantic import BaseModel, Field, PrivateAttr

from crewai.tools import BaseTool


class SnowflakeMCPToolInput(BaseModel):
    """Input schema for Snowflake MCP Tool."""

    tool_name: str = Field(
        ...,
        description="The name of the MCP tool to invoke (e.g., 'product-search', 'revenue-semantic-view', 'sql_exec_tool')."
    )
    arguments: Dict[str, Any] = Field(
        ...,
        description="Arguments to pass to the MCP tool. For search: {'query': '...', 'limit': 10}. For analyst: {'message': '...'}. For SQL: {'query': 'SELECT ...'}."
    )


class SnowflakeMCPTool(BaseTool):
    """
    Tool for interacting with Snowflake MCP server.

    This tool allows CrewAI agents to:
    - Query Cortex Search services
    - Interact with Cortex Analyst semantic views
    - Execute SQL queries
    - Run Cortex Agents
    - Invoke custom UDFs and stored procedures
    """

    name: str = "snowflake_mcp_tool"
    description: str = (
        "Tool for interacting with Snowflake MCP server. "
        "Use this to query data repositories, execute SQL, use Cortex Search, "
        "Cortex Analyst, or Cortex Agents. "
        "Available tools can be discovered using list_tools method. "
        "For search tools, provide: {'query': 'your search query', 'limit': 10}. "
        "For analyst tools, provide: {'message': 'your question'}. "
        "For SQL tools, provide: {'query': 'SELECT ...'}. "
        "For agent tools, provide: {'message': 'your message to the agent'}."
    )
    args_schema: Type[BaseModel] = SnowflakeMCPToolInput
    mcp_server_url: str = Field(..., description="Base URL for Snowflake MCP server")
    database: str = Field(..., description="Database name where MCP server is located")
    schema: str = Field(..., description="Schema name where MCP server is located")
    server_name: str = Field(..., description="Name of the MCP server object")
    access_token: Optional[str] = Field(None, description="OAuth access token for authentication")
    _initialized: bool = PrivateAttr(default=False)
    _protocol_version: str = PrivateAttr(default="2025-06-18")

    def __init__(
        self,
        mcp_server_url: str,
        database: str,
        schema: str,
        server_name: str,
        access_token: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize Snowflake MCP Tool.

        Args:
            mcp_server_url: Base URL for Snowflake MCP server (e.g., 'https://your-account.snowflakecomputing.com')
            database: Database name where MCP server is located
            schema: Schema name where MCP server is located
            server_name: Name of the MCP server object
            access_token: OAuth access token for authentication
        """
        super().__init__(
            mcp_server_url=mcp_server_url.rstrip('/'),
            database=database,
            schema=schema,
            server_name=server_name,
            access_token=access_token,
            **kwargs
        )
        self._initialized = False
        self._protocol_version = "2025-06-18"

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        headers = {
            "Content-Type": "application/json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _get_endpoint(self) -> str:
        """Get the MCP server endpoint URL."""
        return (
            f"{self.mcp_server_url}/api/v2/databases/{self.database}/"
            f"schemas/{self.schema}/mcp-servers/{self.server_name}"
        )

    def _initialize(self) -> bool:
        """Initialize the MCP server connection."""
        if self._initialized:
            return True

        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": self._protocol_version}
            }

            response = requests.post(
                self._get_endpoint(),
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            if "result" in result:
                self._initialized = True
                return True
            else:
                print(f"Failed to initialize MCP server: {result}")
                return False
        except Exception as e:
            print(f"Error initializing MCP server: {e}")
            return False

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List all available tools from the MCP server.

        Returns:
            List of available tools with their schemas
        """
        if not self._initialize():
            return []

        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            }

            response = requests.post(
                self._get_endpoint(),
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            if "result" in result and "tools" in result["result"]:
                return result["result"]["tools"]
            else:
                print(f"Unexpected response format: {result}")
                return []
        except Exception as e:
            print(f"Error listing tools: {e}")
            return []

    def _run(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Execute an MCP tool call.

        Args:
            tool_name: Name of the tool to invoke
            arguments: Arguments to pass to the tool

        Returns:
            Tool execution result as JSON string
        """
        if not self._initialize():
            return json.dumps({"error": "Failed to initialize MCP server"})

        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }

            response = requests.post(
                self._get_endpoint(),
                json=payload,
                headers=self._get_headers(),
                timeout=60
            )
            response.raise_for_status()
            result = response.json()

            if "result" in result:
                # Format the result for better readability
                if "content" in result["result"]:
                    # Analyst tool response
                    content = result["result"]["content"]
                    if isinstance(content, list) and len(content) > 0:
                        if "text" in content[0]:
                            return content[0]["text"]
                elif "results" in result["result"]:
                    # Search tool response
                    return json.dumps(result["result"], indent=2)
                else:
                    return json.dumps(result["result"], indent=2)
            elif "error" in result:
                return json.dumps({"error": result["error"]}, indent=2)
            else:
                return json.dumps(result, indent=2)
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg += f" - {json.dumps(error_detail, indent=2)}"
                except:
                    error_msg += f" - Status: {e.response.status_code}"
            return json.dumps({"error": error_msg}, indent=2)
        except Exception as e:
            return json.dumps({"error": f"Unexpected error: {str(e)}"}, indent=2)
