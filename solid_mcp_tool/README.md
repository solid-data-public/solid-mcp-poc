# Solid MCP Tool (CrewAI Custom Tool)

CrewAI **BaseTool** that calls SolidData's MCP **text2sql**: natural-language question in → SQL + explanation out. No query execution.

Works in both **terminal crews** and **CrewAI Enterprise (AMP / Crew Studio)**. The tool declares its required environment variables via `env_vars` so AMP injects them automatically.

## How it works

1. Agent sends `{question}` (and optionally `semantic_layer_id` to override the env var).
2. Tool reads `SEMANTIC_LAYER_ID` from the environment (or uses the override).
3. Tool authenticates with SolidData using `SOLIDDATA_MANAGEMENT_KEY`.
4. Tool calls MCP `text2sql` with `{"question": ..., "semantic_layer_id": ...}`.
5. Returns the generated SQL and explanation.

## Environment variables

Set these in `.env` (local) or in **CrewAI Enterprise tool config** (AMP). The tool declares them via `env_vars` so AMP injects them at runtime.

| Variable | Required | Description |
|---|---|---|
| `SOLIDDATA_MANAGEMENT_KEY` | Yes | SolidData management key with MCP access. |
| `SEMANTIC_LAYER_ID` | Yes | UUID of the semantic layer (passed as MCP argument). |
| `AUTH_ENDPOINT` | No | Override auth URL. Default: production. |
| `MCP_SERVER_URL` | No | Override MCP URL. Default: production. |

## Dependencies

- `crewai` (with `EnvVar` support)
- `httpx`
- `pydantic`
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
   - Ensure dependencies include: `crewai`, `httpx`, `pydantic`, `nest-asyncio`.

5. **Commit and publish**
   ```bash
   git add .
   git commit -m "Solid MCP text2sql tool"
   crewai tool publish
   ```
   Use `crewai tool publish --public` for a public tool.

## Using in CrewAI Enterprise (AMP)

After publishing, add the tool to your crew in Crew Studio. In the **tool configuration**, set the required env vars (`SOLIDDATA_MANAGEMENT_KEY`, `SEMANTIC_LAYER_ID`). AMP reads the `env_vars` declared on the tool class and injects them into `os.environ` before the tool runs.
