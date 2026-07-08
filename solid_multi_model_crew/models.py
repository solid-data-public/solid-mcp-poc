"""Pydantic schemas for multi-model query planning and configuration."""

from pydantic import BaseModel, Field


class SemanticModelSpec(BaseModel):
    """One certified semantic layer in a multi-model domain."""

    id: str = Field(description="Semantic layer UUID (36 chars).")
    name: str = Field(description="Short machine name, e.g. paid_media.")
    label: str = Field(description="Human-readable model name.")
    description: str = Field(default="", description="What this model covers.")


class ModelCatalog(BaseModel):
    """Collection of semantic models for a domain (e.g. marketing)."""

    domain: str = Field(default="general", description="Domain label for the catalog.")
    models: list[SemanticModelSpec] = Field(min_length=1)


class ModelQueryPlan(BaseModel):
    """Planned sub-question for one semantic model."""

    model_name: str = Field(description="Machine name from the catalog, e.g. paid_media.")
    semantic_layer_id: str = Field(description="UUID of the semantic layer.")
    sub_question: str = Field(description="Tailored natural-language question for this model.")
    rationale: str = Field(description="Why this model is relevant to the user question.")


class QueryPlan(BaseModel):
    """Structured output from the Marketing Query Planner."""

    user_question: str
    router_candidate: bool = Field(
        description="True if the question could be answered by router mode alone."
    )
    model_queries: list[ModelQueryPlan] = Field(
        description="One sub-question per relevant model; skip irrelevant models."
    )
    cross_model_notes: str = Field(
        default="",
        description="Assumptions or gaps when combining models (no SQL merging).",
    )
