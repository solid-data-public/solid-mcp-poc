# Solid Multi-Model MCP Crew

CLI demo showing **two Solid MCP multi-model patterns** with CrewAI:

1. **Router mode** — one `text2sql` call with multiple `semantic_layer_ids`; Solid picks the best certified model.
2. **Per-model mode** — a crew decomposes a cross-domain question, queries each semantic model with a tailored sub-question, optionally runs SQL in Snowflake, then aggregates a unified analysis.

Uses the repo root **`.venv`** and **`.env`** (same keys as the main POC).

## Prerequisites

- Python 3.10–3.13
- `SOLIDDATA_MANAGEMENT_KEY`, `GEMINI_API_KEY` in `.env`
- At least **2 certified semantic layer UUIDs** (via YAML or `SEMANTIC_LAYER_IDS`)

## Setup

From the **repo root**:

```bash
cp .env.example .env
# Edit .env — set keys and either MULTI_MODEL_CONFIG or SEMANTIC_LAYER_IDS
uv sync
```

### Model configuration

**Preferred — YAML** (`MULTI_MODEL_CONFIG`):

Copy [`marketing_models.example.yaml`](marketing_models.example.yaml) and replace placeholder UUIDs with certified model IDs from Solid.

```yaml
domain: marketing
models:
  - id: "your-uuid-here"
    name: paid_media
    label: "Paid Media & Ad Spend"
    description: "Campaign spend, ROAS, impressions"
```

**Fallback — env only:**

```bash
SEMANTIC_LAYER_IDS=uuid-1,uuid-2,uuid-3
```

## Run

```bash
# Default: router + multi-model aggregation
uv run solid_multi_model_crew "How did Q1 campaigns perform across paid and organic channels?"

# Router only (Solid picks one model)
uv run solid_multi_model_crew --mode router "Show top campaigns by ROAS"

# Per-model queries + aggregation only
uv run solid_multi_model_crew --mode multi "Compare paid spend vs web conversion last quarter"

# Custom model catalog
uv run solid_multi_model_crew --models-config path/to/models.yaml "Your question"

# Skip Snowflake even when configured
uv run solid_multi_model_crew --no-snowflake "Your question"
```

## Modes compared

| Mode | MCP calls | Best for |
|------|-----------|----------|
| `router` | 1 × text2sql with all IDs | Let Solid route to the best single model |
| `multi` | N × text2sql (one ID each) + aggregation | Cross-domain questions spanning multiple models |
| `both` (default) | Router baseline + multi-model synthesis | Compare router vs explicit multi-model analysis |

## Crew flow (multi mode)

```
User question
     │
     ▼
Marketing Query Planner  →  semantic_model_qa when model fit is unclear
     │                      →  structured sub-questions per model
     ▼
Model Query Specialist   →  solid_model_text2sql__* (primary)
     │                      →  semantic_model_qa retry if text2sql fails
     ▼
Snowflake Executor       →  optional, when Snowflake env vars set
     │
     ▼
Cross-Model Analyst      →  executive report with per-model + cross-model insights
```

## Router fallback

When `--mode router` or `--mode both`:

1. **solid_router_text2sql** runs first (all `semantic_layer_ids`).
2. If output has no SQL or indicates failure, a **semantic_model_qa fallback crew** runs:
   - Queries each candidate model's coverage via `solid_semantic_model_qa__*`
   - Calls `solid_model_text2sql__*` on the best match

The router agent can also invoke `semantic_model_qa` inline when the router result is ambiguous.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SOLIDDATA_MANAGEMENT_KEY` | Yes | Passed as `x-solid-management-key` on MCP transport |
| `GEMINI_API_KEY` | Yes | CrewAI LLM |
| `MODEL` | No | Default `gemini/gemini-2.0-flash-lite` |
| `MCP_SERVER_URL` | No | Default production MCP URL |
| `MULTI_MODEL_CONFIG` | No* | Path to YAML catalog (default: `marketing_models.example.yaml`) |
| `SEMANTIC_LAYER_IDS` | No* | Comma-separated UUIDs if YAML not used |
| Snowflake vars | No | Same as main POC — enables optional SQL execution |

\* At least one of `MULTI_MODEL_CONFIG` (file must exist) or `SEMANTIC_LAYER_IDS` with ≥2 IDs.

## Discovering model IDs

Use Solid MCP **`semantic_model_qa`** (via Cursor MCP or MCP Inspector) to ask what a model covers, or get certified UUIDs from your Solid admin.

## References

- [Solid MCP — Multiple models (router mode)](https://docs.getsolid.ai/docs/getting-started-with-solid-mcp-server#multiple-models-router-mode)
- Main POC: [`../README.md`](../README.md)
- Publishable tools: [`../solid_mcp_tool/`](../solid_mcp_tool/)
