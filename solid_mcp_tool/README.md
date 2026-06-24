# Solid MCP Tool (CrewAI Custom Tool)

CrewAI **`BaseTool`** implementations that call SolidData **directly over streamable HTTP MCP** (same pattern as the repo demo in `soliddata_mcp_poc`): pass `SOLIDDATA_MANAGEMENT_KEY` as the **`x-solid-management-key`** header via CrewAI's **`MCPClient`** with **`HTTPTransport`** to Solid's **`MCP_SERVER_URL`**.

**This package does not use the Azure REST-to-MCP bridge or `openapi.yaml` endpoints.** Those are for REST-only integrations (Workato, Copilot Studio, etc.). CrewAI tools always connect to Solid's MCP URL with header auth.

Use this package in **CrewAI Enterprise (AMP)** or other crews when you want named tools instead of attaching **`MCPServerHTTP`** to an agent.

## Tools

| CrewAI tool name | Class | MCP tool | When to use |
|------------------|-------|----------|-------------|
| `solid_text2sql` | `SolidMcpTool` | `text2sql` | Generate SQL from a natural-language data question |
| `solid_glossary_search` | `SolidGlossarySearchTool` | `glossary_search` | Look up definitions, acronyms, and business terms |
| `solid_specific_asset_information` | `SolidSpecificAssetInformationTool` | `specific_asset_information_tool` | Metadata Q&A about one named table or dashboard |
| `solid_semantic_model_qa` | `SolidSemanticModelQATool` | `semantic_model_qa` | Q&A about semantic model metadata (coverage, tables, metrics) |

## How it works (text2sql — `SolidMcpTool`)

1. Agent sends `{question}` (and optionally `semantic_layer_id` to override the env var).
2. Tool reads `SEMANTIC_LAYER_ID` from the environment (or uses the override).
3. Tool opens an MCP session to `MCP_SERVER_URL` with `x-solid-management-key` and calls **`text2sql`** with `question` and `semantic_layer_ids`.
4. Returns the MCP tool result (text).

## How it works (glossary — `SolidGlossarySearchTool`)

1. Agent sends `{query}`.
2. Same header auth as text2sql.
3. MCP session calls **`glossary_search`** with `{"query": "..."}`.
4. Returns the MCP tool result (text).

## How it works (specific asset — `SolidSpecificAssetInformationTool`)

1. Agent sends `{question, asset_name}` (and optionally `asset_type`).
2. Tool reads `ASSET_NAME` / `ASSET_TYPE` from the environment when not passed.
3. MCP session calls **`specific_asset_information_tool`** with `question`, `asset_name`, and optional `asset_type`.
4. Returns the MCP tool result (text).

## How it works (semantic model Q&A — `SolidSemanticModelQATool`)

1. Agent sends `{question, semantic_model_id}`.
2. Tool reads `SEMANTIC_MODEL_ID` from the environment when not passed.
3. MCP session calls **`semantic_model_qa`** with `question` and `semantic_model_id`.
4. Returns the MCP tool result (text).

## Environment variables

Set these in `.env` (local) or in **CrewAI Enterprise tool config** (AMP). Each tool class declares them via `env_vars` so AMP injects them at runtime.

| Variable | Required | Used by |
|---|---|---|
| `SOLIDDATA_MANAGEMENT_KEY` | Yes (all tools) | Passed as `x-solid-management-key` header |
| `MCP_SERVER_URL` | No | Solid MCP HTTP URL. Default: production |
| `SEMANTIC_LAYER_ID` | Yes for **text2sql** | UUID of the semantic layer (`semantic_layer_ids`) |
| `SEMANTIC_MODEL_ID` | Yes for **semantic_model_qa** (unless passed as arg) | UUID of the semantic model |
| `ASSET_NAME` | Yes for **specific_asset_information** (unless passed as arg) | Default table or dashboard name |
| `ASSET_TYPE` | No | Optional asset type hint (e.g. `table`, `dashboard`) |

## Dependencies

- `crewai` (with MCP + `EnvVar` support)
- `pydantic`
- `mcp` (pulled in with CrewAI MCP support)
- `nest_asyncio` (fixes "event loop already running" in AMP)

## How to publish to CrewAI (CLI)

Do this in a **normal terminal**, in a new folder.

1. **Login**
   ```bash
   crewai login
   ```

2. **Create tool project**
   ```bash
   crewai tool create solid_mcp_tool
   ```

3. **Replace `tool.py`**
   Copy the entire contents of this repo's `solid_mcp_tool/tool.py` into the new project's `tool.py` (overwrite the scaffold).

4. **Update `pyproject.toml`**
   - Set `name`, `version`, `description`.
   - **Increment `version`** for every publish.
   - Ensure dependencies include: `crewai`, `pydantic`, `nest-asyncio`.

5. **Commit and publish**
   ```bash
   git add .
   git commit -m "Solid MCP tools (text2sql, glossary, asset info, semantic model QA)"
   crewai tool publish
   ```
   Use `crewai tool publish --public` for a public tool.

## Using in CrewAI Enterprise (AMP)

After publishing, add the tools you need to your crew in Crew Studio. Set `SOLIDDATA_MANAGEMENT_KEY` for all tools. Additionally:

- **text2sql:** `SEMANTIC_LAYER_ID`
- **glossary_search:** no extra required vars
- **specific_asset_information:** `ASSET_NAME` (or pass `asset_name` per call)
- **semantic_model_qa:** `SEMANTIC_MODEL_ID` (or pass `semantic_model_id` per call)

AMP reads the `env_vars` declared on each tool class and injects them into `os.environ` before the tool runs.
