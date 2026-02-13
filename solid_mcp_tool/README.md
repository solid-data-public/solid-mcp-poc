# Solid MCP Tool (CrewAI custom tool)

Minimal CrewAI **BaseTool** that connects to SolidData’s MCP server and calls **text2sql**: natural-language question in → SQL + explanation out. No query execution.

Use this in CrewAI agents or publish it to the CrewAI Tool Repository so any crew/flow can use it.

## Contents

- **`tool.py`** — Single file to copy into your `crewai tool create` project’s `tool.py`. Self-contained: auth + MCP call.

## Env vars

- **`SOLIDDATA_MANAGEMENT_KEY`** (required) — SolidData management key with MCP access.
- **`AUTH_ENDPOINT`** (optional) — Default: production SolidData auth URL.
- **`MCP_SERVER_URL`** (optional) — Default: production SolidData MCP URL.

## How to publish to CrewAI (CLI)

Do this in a **normal terminal** (not the IDE terminal), in a new folder.

1. **Login**
   ```bash
   crewai login
   ```

2. **Create tool project**
   ```bash
   crewai tool create solid_mcp_tool
   ```
   This creates a new directory (e.g. `solid_mcp_tool/`) with a scaffolded `tool.py` and `pyproject.toml`.

3. **Replace `tool.py`**  
   Copy the **entire contents** of this repo’s `solid_mcp_tool/tool.py` into the new project’s `tool.py` (overwrite the scaffold).

4. **Update `pyproject.toml`**
   - Set `name`, `version`, `description` as needed.
   - **Increment `version`** for every publish (e.g. `0.1.0` → `0.1.1`).
   - Ensure dependencies include at least: `crewai`, `httpx`, `pydantic`. Add `httpx` if the scaffold doesn’t list it.

5. **Commit and publish**
   ```bash
   git add .
   git commit -m "Solid MCP text2sql tool"
   crewai tool publish
   ```
   Use `crewai tool publish --public` for a public tool.

After publishing, install the tool in other projects with `crewai tool install <tool-name>` and set the env vars in that project (or in CrewAI AMP for the tool).
