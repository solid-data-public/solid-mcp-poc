"""CrewAI tools for Solid MCP text2sql — router mode and per-model queries."""

from __future__ import annotations

from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from solid_mcp_tool.tool import run_mcp_tool
from solid_multi_model_crew.models import ModelCatalog, SemanticModelSpec

# Standard question for model-discovery via semantic_model_qa.
COVERAGE_QUESTION_TEMPLATE = (
    "Does this semantic model cover the data needed to answer the following business question? "
    "List relevant metrics, tables, and any gaps.\n\nQuestion: {question}"
)


class RouterText2SQLInput(BaseModel):
    question: str = Field(..., description="Natural-language business question.")


class SolidRouterText2SQLTool(BaseTool):
    """Call text2sql with multiple semantic_layer_ids — Solid router picks the best model."""

    name: str = "solid_router_text2sql"
    description: str = (
        "Convert a natural-language question to SQL using Solid's router mode. "
        "Pass all configured semantic layer IDs; Solid selects the best certified match."
    )
    args_schema: Type[BaseModel] = RouterText2SQLInput
    semantic_layer_ids: list[str]

    def _run(self, question: str = "", **kwargs: Any) -> str:
        q = (question or "").strip() or str(kwargs.get("question", "")).strip()
        if not q:
            return "Error: Input 'question' is missing."
        return run_mcp_tool(
            "text2sql",
            {"question": q, "semantic_layer_ids": self.semantic_layer_ids},
        )


def build_router_text2sql_tool(semantic_layer_ids: list[str]) -> SolidRouterText2SQLTool:
    return SolidRouterText2SQLTool(semantic_layer_ids=semantic_layer_ids)


def build_semantic_model_qa_tool(spec: SemanticModelSpec) -> BaseTool:
    """Factory: semantic_model_qa scoped to one model — for coverage / model selection."""

    class SemanticModelQAInput(BaseModel):
        question: str = Field(
            ...,
            description=(
                f"Natural-language question about {spec.label} model metadata, "
                "coverage, tables, or metrics."
            ),
        )

    tool_name = f"solid_semantic_model_qa__{spec.name}"
    tool_description = (
        f"Ask about the '{spec.label}' semantic model's metadata and coverage "
        f"(ID: {spec.id}). Use BEFORE text2sql when unsure whether this model fits "
        f"the user's question. Covers: {spec.description or 'see model metadata'}."
    )

    class SemanticModelQATool(BaseTool):
        name: str = tool_name
        description: str = tool_description
        args_schema: Type[BaseModel] = SemanticModelQAInput

        def _run(self, question: str = "", **kwargs: Any) -> str:
            q = (question or "").strip() or str(kwargs.get("question", "")).strip()
            if not q:
                return "Error: Input 'question' is missing."
            return run_mcp_tool(
                "semantic_model_qa",
                {"question": q, "semantic_model_id": spec.id},
            )

    return SemanticModelQATool()


def build_model_text2sql_tool(spec: SemanticModelSpec) -> BaseTool:
    """Factory: one tool per semantic model, targeting a single semantic_layer_id."""

    class ModelText2SQLInput(BaseModel):
        question: str = Field(
            ...,
            description=f"Natural-language question for {spec.label}.",
        )

    tool_name = f"solid_model_text2sql__{spec.name}"
    tool_description = (
        f"Generate SQL using the '{spec.label}' semantic model only "
        f"(ID: {spec.id}). Covers: {spec.description or 'see model metadata'}. "
        "Use for questions specific to this model's domain."
    )

    class ModelText2SQLTool(BaseTool):
        name: str = tool_name
        description: str = tool_description
        args_schema: Type[BaseModel] = ModelText2SQLInput

        def _run(self, question: str = "", **kwargs: Any) -> str:
            q = (question or "").strip() or str(kwargs.get("question", "")).strip()
            if not q:
                return "Error: Input 'question' is missing."
            return run_mcp_tool(
                "text2sql",
                {"question": q, "semantic_layer_ids": [spec.id]},
            )

    return ModelText2SQLTool()


def build_catalog_tools(catalog: ModelCatalog) -> tuple[list[BaseTool], list[BaseTool], list[BaseTool]]:
    """Return (qa_tools, text2sql_tools, router_tool as single-element list)."""
    qa_tools = [build_semantic_model_qa_tool(spec) for spec in catalog.models]
    text2sql_tools = [build_model_text2sql_tool(spec) for spec in catalog.models]
    router_tool = build_router_text2sql_tool([spec.id for spec in catalog.models])
    return qa_tools, text2sql_tools, [router_tool]


def format_tool_names(tools: list[BaseTool]) -> str:
    return ", ".join(f"`{t.name}`" for t in tools)
