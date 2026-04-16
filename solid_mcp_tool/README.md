# Solid MCP Tool (CrewAI Custom Tool)

CrewAI **`BaseTool`** implementations that call SolidData **directly over MCP** (same pattern as the repo demo in `soliddata_mcp_poc`): exchange the management key for a JWT, then use CrewAI’s **`MCPClient`** with **`HTTPTransport`** to Solid’s **`MCP_SERVER_URL`** and invoke MCP tools. **They do not use the Azure REST-to-MCP bridge** (that bridge is for OpenAPI / REST-only integrations only).

Use this package in **CrewAI Enterprise (AMP)** or other crews when you want named tools (**`solid_text2sql`**, **`solid_glossary_search`**) instead of attaching **`MCPServerHTTP`** to an agent.

- **`SolidMcpTool` (`solid_text2sql`)** — natural-language question in → SQL + explanation out. No query execution.
- **`SolidGlossarySearchTool` (`solid_glossary_search`)** — glossary / terminology question in → glossary MCP result out.

## How it works (text2sql — `SolidMcpTool`)

1. Agent sends `{question}` (and optionally `semantic_layer_id` to override the env var).
2. Tool reads `SEMANTIC_LAYER_ID` from the environment (or uses the override).
3. Tool exchanges `SOLIDDATA_MANAGEMENT_KEY` for a JWT (`httpx` to `AUTH_ENDPOINT`).
4. Tool opens an MCP session to `MCP_SERVER_URL` with `Authorization: Bearer …` and calls the **`text2sql`** tool with `question` and `semantic_layer_ids`.
5. Returns the MCP tool result (text).

## How it works (glossary — `SolidGlossarySearchTool`)

1. Agent sends `{query}`.
2. Same auth as text2sql.
3. MCP session calls **`glossary_search`** with `{"query": "..."}`.
4. Returns the MCP tool result (text).

## Environment variables

Set these in `.env` (local) or in **CrewAI Enterprise tool config** (AMP). The tool declares them via `env_vars` so AMP injects them at runtime.

| Variable | Required | Description |
|---|---|---|
| `SOLIDDATA_MANAGEMENT_KEY` | Yes | SolidData management key with MCP access. |
| `SEMANTIC_LAYER_ID` | Yes for **text2sql** | UUID of the semantic layer (MCP `semantic_layer_ids`). Not used by **glossary**. |
| `AUTH_ENDPOINT` | No | Override auth exchange URL. Default: production. |
| `MCP_SERVER_URL` | No | Solid MCP HTTP URL. Default: production. |

## Dependencies

- `crewai` (with MCP + `EnvVar` support)
- `httpx`
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
   - Ensure dependencies include: `crewai`, `httpx`, `pydantic`, `nest-asyncio`.

5. **Commit and publish**
   ```bash
   git add .
   git commit -m "Solid MCP text2sql + glossary_search tools"
   crewai tool publish
   ```
   Use `crewai tool publish --public` for a public tool.

## Using in CrewAI Enterprise (AMP)

After publishing, add one or both tools to your crew in Crew Studio. For **text2sql**, set `SOLIDDATA_MANAGEMENT_KEY` and `SEMANTIC_LAYER_ID`. For **glossary_search**, set `SOLIDDATA_MANAGEMENT_KEY` (and `MCP_SERVER_URL` / `AUTH_ENDPOINT` if not using defaults). AMP reads the `env_vars` declared on each tool class and injects them into `os.environ` before the tool runs.
