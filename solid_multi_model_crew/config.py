"""Settings and model catalog loading for the multi-model crew."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from solid_multi_model_crew.models import ModelCatalog, SemanticModelSpec

_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _repo_root() -> Path:
    """Walk up from this file to find the repo root (contains pyproject.toml)."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return current.parent


def _resolve_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return _repo_root() / p


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_repo_root() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    soliddata_management_key: str = Field(alias="SOLIDDATA_MANAGEMENT_KEY")
    mcp_server_url: str = Field(
        default="https://mcp.production.soliddata.io/mcp",
        alias="MCP_SERVER_URL",
    )
    gemini_api_key: str = Field(alias="GEMINI_API_KEY")
    model: str = Field(default="gemini/gemini-2.5-flash", alias="MODEL")
    semantic_layer_ids: str | None = Field(default=None, alias="SEMANTIC_LAYER_IDS")
    multi_model_config: str | None = Field(
        default="solid_multi_model_crew/marketing_models.example.yaml",
        alias="MULTI_MODEL_CONFIG",
    )

    snowflake_account: str | None = Field(default=None, alias="SNOWFLAKE_ACCOUNT")
    snowflake_user: str | None = Field(default=None, alias="SNOWFLAKE_USER")
    snowflake_password: str | None = Field(default=None, alias="SNOWFLAKE_PASSWORD")
    snowflake_database: str | None = Field(default=None, alias="SNOWFLAKE_DATABASE")
    snowflake_schema: str | None = Field(default=None, alias="SNOWFLAKE_SCHEMA")
    snowflake_warehouse: str | None = Field(default=None, alias="SNOWFLAKE_WAREHOUSE")
    snowflake_role: str | None = Field(default=None, alias="SNOWFLAKE_ROLE")

    @field_validator("soliddata_management_key", "gemini_api_key")
    @classmethod
    def _strip_required(cls, v: str) -> str:
        return v.strip()

    def use_snowflake(self) -> bool:
        return bool(
            self.snowflake_account
            and self.snowflake_user
            and self.snowflake_password
            and self.snowflake_database
            and self.snowflake_schema
            and self.snowflake_warehouse
        )


def _parse_env_model_ids(raw: str) -> list[str]:
    ids = [part.strip() for part in raw.split(",") if part.strip()]
    for model_id in ids:
        if not _UUID_PATTERN.match(model_id):
            raise ValueError(f"Invalid semantic layer UUID in SEMANTIC_LAYER_IDS: {model_id!r}")
    return ids


def _catalog_from_env_ids(ids: list[str]) -> ModelCatalog:
    models = [
        SemanticModelSpec(
            id=model_id,
            name=f"model_{index}",
            label=f"Semantic Model {index}",
            description="Configured via SEMANTIC_LAYER_IDS (no YAML metadata).",
        )
        for index, model_id in enumerate(ids, start=1)
    ]
    return ModelCatalog(domain="env", models=models)


def load_model_catalog(settings: Settings, models_config: str | Path | None = None) -> ModelCatalog:
    """Load model catalog from YAML (preferred) or SEMANTIC_LAYER_IDS fallback."""
    config_path = models_config or settings.multi_model_config
    if config_path:
        path = _resolve_path(config_path)
        if path.is_file():
            with path.open(encoding="utf-8") as handle:
                data = yaml.safe_load(handle)
            catalog = ModelCatalog.model_validate(data)
            for spec in catalog.models:
                if not _UUID_PATTERN.match(spec.id):
                    raise ValueError(f"Invalid UUID in model catalog ({spec.name}): {spec.id!r}")
            return catalog

    if settings.semantic_layer_ids:
        ids = _parse_env_model_ids(settings.semantic_layer_ids)
        return _catalog_from_env_ids(ids)

    raise ValueError(
        "No model catalog found. Set MULTI_MODEL_CONFIG to a YAML file or "
        "SEMANTIC_LAYER_IDS to a comma-separated list of at least 2 UUIDs."
    )


def validate_multi_model_catalog(catalog: ModelCatalog) -> None:
    """Ensure at least two models for the multi-model demo."""
    if len(catalog.models) < 2:
        raise ValueError(
            f"Multi-model crew requires at least 2 semantic models; got {len(catalog.models)}."
        )


def apply_mcp_env(settings: Settings, *, mode: str) -> None:
    """Ensure MCP-related env vars are set for solid_mcp_tool.run_mcp_tool."""
    os.environ["SOLIDDATA_MANAGEMENT_KEY"] = settings.soliddata_management_key
    os.environ["MCP_SERVER_URL"] = settings.mcp_server_url
    os.environ.setdefault("X_SOLID_CLIENT", "solid_multi_model_crew")
    os.environ.setdefault("X_SOLID_LABELS", f"workflow=multi_model,mode={mode}")


def get_settings() -> Settings:
    return Settings()
