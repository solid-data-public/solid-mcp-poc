"""Application settings — loaded from environment / .env file."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Auth ─────────────────────────────────────────────
    soliddata_management_key: str = Field(
        description="SolidData management key for MCP auth.",
        alias="SOLIDDATA_MANAGEMENT_KEY",
    )
    auth_endpoint: str = Field(
        default="https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key",
        description="Endpoint to exchange management key for a bearer token.",
        alias="AUTH_ENDPOINT",
    )

    # ── MCP ──────────────────────────────────────────────
    mcp_server_url: str = Field(
        default="https://mcp.production.soliddata.io/mcp",
        description="SolidData MCP server URL.",
        alias="MCP_SERVER_URL",
    )
    semantic_layer_id: str = Field(
        default="851b4156-e0ea-460b-b6f9-cf3f428e95b5",
        description="Semantic layer ID for SolidData text2sql.",
        alias="SEMANTIC_LAYER_ID",
    )

    # ── LLM (Gemini) ──────────────────────────────────────
    gemini_api_key: str = Field(
        description="Google Gemini API key for CrewAI agents.",
        alias="GEMINI_API_KEY",
    )
    model: str = Field(
        default="gemini/gemini-2.0-flash",
        description="LLM model name (e.g. gemini/gemini-2.0-flash).",
        alias="MODEL",
    )

    # ── Snowflake MCP (optional; when set, crew executes SQL and reporter analyzes results) ─
    snowflake_mcp_server_url: str | None = Field(
        default=None,
        description="Snowflake MCP server base URL (e.g. https://your-account.snowflakecomputing.com).",
        alias="SNOWFLAKE_MCP_SERVER_URL",
    )
    snowflake_database: str | None = Field(default=None, description="Snowflake database name.", alias="SNOWFLAKE_DATABASE")
    snowflake_schema: str | None = Field(default=None, description="Snowflake schema name.", alias="SNOWFLAKE_SCHEMA")
    snowflake_mcp_server_name: str | None = Field(
        default=None,
        description="Name of the MCP server object in Snowflake.",
        alias="SNOWFLAKE_MCP_SERVER_NAME",
    )
    snowflake_access_token: str | None = Field(
        default=None,
        description="OAuth access token for Snowflake MCP.",
        alias="SNOWFLAKE_ACCESS_TOKEN",
    )
    snowflake_sql_tool_name: str = Field(
        default="sql_exec_tool",
        description="MCP tool name for SQL execution (e.g. sql_exec_tool).",
        alias="SNOWFLAKE_SQL_TOOL_NAME",
    )


def get_settings() -> Settings:
    """Return validated application settings."""
    return Settings()
