# Solid MCP Tool (CrewAI Custom Tool)

CrewAI **BaseTool** implementations that call SolidData via the Azure MCP bridge (same pattern as the demo’s MCP session):

- **`SolidMcpTool` (`solid_text2sql`)** — natural-language question in → SQL + explanation out. No query execution.
- **`SolidGlossarySearchTool` (`solid_glossary_search`)** — glossary / terminology question in → synthesized glossary answer out.

Works in both **terminal crews** and **CrewAI Enterprise (AMP / Crew Studio)**. Each tool declares environment variables via `env_vars` so AMP injects them automatically.

## How it works (text2sql — `SolidMcpTool`)

1. Agent sends `{question}` (and optionally `semantic_layer_id` to override the env var).
2. Tool reads `SEMANTIC_LAYER_ID` from the environment (or uses the override).
3. Tool exchanges `SOLIDDATA_MANAGEMENT_KEY` for a JWT.
4. Tool POSTs to the bridge **text2sql** URL with `Authorization: Bearer …` and JSON `question` + `semantic_layer_ids`.
5. Returns the generated SQL and explanation (from the bridge `message` field).

## How it works (glossary — `SolidGlossarySearchTool`)

1. Agent sends `{query}` (natural-language term or “what does X mean?” style question).
2. Tool exchanges `SOLIDDATA_MANAGEMENT_KEY` for a JWT (same as text2sql).
3. Tool POSTs to the bridge **glossary** URL with `Authorization: Bearer …` and JSON `{"query": "..."}` only (no semantic layer in the body).
4. Returns the glossary result (synthesized answer / status from the bridge `result` object).

## Environment variables

Set these in `.env` (local) or in **CrewAI Enterprise tool config** (AMP). The tool declares them via `env_vars` so AMP injects them at runtime.

| Variable | Required | Description |
|---|---|---|
| `SOLIDDATA_MANAGEMENT_KEY` | Yes | SolidData management key with MCP access. |
| `SEMANTIC_LAYER_ID` | Yes for **text2sql** | UUID of the semantic layer (passed to the bridge as `semantic_layer_ids`). Not used by **glossary**. |
| `AUTH_ENDPOINT` | No | Override auth exchange URL. Default: production. |
| `TEXT2SQL_URL` | No | Override bridge text2sql URL (includes `?code=` function key if required). |
| `GLOSSARY_URL` | No | Override bridge glossary URL (includes `?code=` if required). |

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

After publishing, add one or both tools to your crew in Crew Studio. For **text2sql**, set `SOLIDDATA_MANAGEMENT_KEY` and `SEMANTIC_LAYER_ID`. For **glossary_search**, only `SOLIDDATA_MANAGEMENT_KEY` is required. AMP reads the `env_vars` declared on each tool class and injects them into `os.environ` before the tool runs.
