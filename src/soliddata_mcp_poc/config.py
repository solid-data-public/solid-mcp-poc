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

    # ── Snowflake (connector only; username/password) ─────
    snowflake_account: str | None = Field(
        default=None,
        description="Snowflake account id (e.g. xy12345.us-east-1).",
        alias="SNOWFLAKE_ACCOUNT",
    )
    snowflake_user: str | None = Field(default=None, description="Snowflake user.", alias="SNOWFLAKE_USER")
    snowflake_password: str | None = Field(default=None, description="Snowflake password.", alias="SNOWFLAKE_PASSWORD")
    snowflake_database: str | None = Field(default=None, description="Snowflake database.", alias="SNOWFLAKE_DATABASE")
    snowflake_schema: str | None = Field(default=None, description="Snowflake schema.", alias="SNOWFLAKE_SCHEMA")
    snowflake_warehouse: str | None = Field(default=None, description="Snowflake warehouse.", alias="SNOWFLAKE_WAREHOUSE")
    snowflake_role: str | None = Field(default=None, description="Snowflake role (optional).", alias="SNOWFLAKE_ROLE")

    def use_snowflake(self) -> bool:
        """True when Snowflake connector is fully configured."""
        return bool(
            self.snowflake_account
            and self.snowflake_user
            and self.snowflake_password
            and self.snowflake_database
            and self.snowflake_schema
            and self.snowflake_warehouse
        )


def get_settings() -> Settings:
    """Return validated application settings."""
    return Settings()
