# SolidData MCP POC — CrewAI + Solid MCP (Query-Only Demo)

Minimal **demonstration** of [Solid](https://getsolid.ai)'s MCP server with [CrewAI](https://crewai.com):

- **What it does:** You ask a natural-language question → the crew calls Solid’s MCP **text2sql** tool → Solid returns the generated SQL. Optionally that SQL is executed in Snowflake via the **Snowflake Python connector** (username/password); the Reporter then analyzes the actual query results. Otherwise the Reporter explains what the SQL does. All output is **printed in the terminal**.
- **Snowflake (optional):** When Snowflake connector env vars are set, the flow runs the generated SQL in Snowflake using the connector (no PAT, no MCP API, no network policy); the Reporter analyzes the **data** returned.

Use this repo to see the end-to-end flow (auth → MCP → SQL + analysis) and to publish the **Solid MCP tool** as a CrewAI custom tool so any agent can use it.

---

## Table of Contents

- [Architecture](#architecture)
- [Testing MCP Connection without Crew](#testing-mcp-connection-without-crew)
  - [Dependencies](#dependencies)
  - [Run the Inspector](#run-the-inspector)
- [Part 1: Run the Demo (Terminal Only)](#part-1-run-the-demo-terminal-only)
  - [How It Works](#how-it-works)
  - [1.1 Prerequisites](#11-prerequisites)
  - [1.2 Setup](#12-setup)
  - [1.3 Run](#13-run)
  - [1.4 What You See](#14-what-you-see)
- [Part 2: Solid MCP as a CrewAI Custom Tool](#part-2-solid-mcp-as-a-crewai-custom-tool)
  - [2.1 What's in `solid_mcp_tool/`](#21-whats-in-solid_mcp_tool)
  - [2.2 How it works (tool flow)](#22-how-it-works-tool-flow)
  - [2.3 Environment variables (tool)](#23-environment-variables-tool)
  - [2.4 Publish the Tool to CrewAI (CLI)](#24-publish-the-tool-to-crewai-cli)
- [Project Structure](#project-structure)
- [Snowflake setup](#snowflake-setup)
- [Troubleshooting](#troubleshooting)
- [References](#references)

---

## Architecture

### Crew flow (with optional Snowflake execution)

1. **SQL Analyst** — Uses Solid MCP **text2sql** to turn the user question into a SQL query and a short explanation.
2. **Snowflake SQL Executor** *(only when Snowflake is configured)* — Takes the SQL from step 1, runs it in Snowflake via the **Snowflake Python connector** (username/password), and returns the raw query results.
3. **Reporter** — If step 2 ran: summarizes the **query results** and writes a stakeholder report. If step 2 was skipped: explains what the SQL does in plain language.

```
Question (natural language)
        │
        ▼
┌──────────────────┐   MCP (text2sql)    ┌─────────────────────┐
│  SQL Analyst     │ ──────────────────► │  SolidData MCP       │
│  (Agent 1)       │ ◄────────────────── │  Server             │
└────────┬─────────┘   SQL + explanation └─────────────────────┘
         │
         ▼
┌──────────────────┐   (optional)        ┌─────────────────────┐
│  SQL Executor    │ ──────────────────► │  Snowflake          │
│  (Agent 2)       │   execute SQL       │  Python connector   │
└────────┬─────────┘ ◄────────────────── └─────────────────────┘
         │             query results
         ▼
┌──────────────────┐
│  Reporter        │  → Report on results (or explain the SQL if no Snowflake)
│  (Agent 3)       │
└────────┬─────────┘
         │
         ▼
   Result printed in terminal only
```

- The **SQL Analyst** connects to SolidData’s MCP server via **MCPServerHTTP** in `crew.py` (using the token from `auth.py`) and uses the **text2sql** tool from that server. The **`solid_mcp_tool/`** folder is a separate, publishable CrewAI custom tool for use in other crews or **CrewAI Enterprise (AMP)**; this demo does not use it directly.
- **Snowflake** is used only via the **Snowflake Python connector** (`snowflake_connector_tool.py`) with username/password; no Snowflake MCP or PAT. Query results are capped at 1000 rows (configurable on the tool) to keep context manageable.

---

## Testing MCP Connection without Crew

You can test the SolidData MCP connection and credentials in a browser using the official **MCP Inspector**. No Python or CrewAI required—useful for quick credential and connection checks.

### Dependencies

- **Node.js** (includes `npm` and `npx`). Not included in this repo.
  - Install from [nodejs.org](https://nodejs.org/) or your package manager (e.g. `brew install node` on macOS).

### Run the Inspector

From any directory (no need to be in this repo):

```bash
npx --clear-npx-cache && npx @modelcontextprotocol/inspector@latest
```

A browser window opens. Add an MCP server:

- **Transport:** choose the option that matches Solid’s MCP (e.g. **Streamable HTTP** if available, or the HTTP/URL option).
- **URL:** your SolidData MCP URL (e.g. `https://mcp.production.soliddata.io/mcp`; for dev use the dev MCP URL).
- **Headers:** add `Authorization: Bearer <token>`. Get the token by exchanging your `SOLIDDATA_MANAGEMENT_KEY` at the SolidData auth endpoint (same as in `.env.example`), or use a small script/curl as in this repo’s auth flow.

Then use the Inspector UI to list tools and call **text2sql** to confirm the connection works before running the full crew.

---

## Part 1: Run the Demo (Terminal Only)

Simplest path: **ask a question → see the SQL response from Solid and the agent’s analysis** in the terminal.


### How It Works

1. **Auth** — `auth.py` exchanges `SOLIDDATA_MANAGEMENT_KEY` for a bearer token (SolidData auth API).
2. **MCP** — `crew.py` creates an `MCPServerHTTP` client for the SolidData MCP server with that token and attaches it to the SQL Analyst agent.
3. **SQL Analyst** — Uses the MCP **text2sql** tool (from that server) to get a SQL query + short explanation.
4. **Snowflake Executor** *(optional)* — If Snowflake connector is configured, runs that SQL in Snowflake and returns query results.
5. **Reporter** — If Snowflake ran: summarizes the **query results** and writes a stakeholder report. Otherwise: explains in plain language what the query does.
6. **Output** — Result is **printed in the terminal only**.

### 1.1 Prerequisites

- Python 3.10–3.13 (see `pyproject.toml` for the exact supported range)
- **SolidData management key** (MCP-enabled)
- **Google Gemini API key** (e.g. [Google AI Studio](https://aistudio.google.com/apikey))
- Optional: [uv](https://docs.astral.sh/uv/)

### 1.2 Setup

From the **project root** (where `pyproject.toml` and `.env` live):

```bash
cp .env.example .env
# Edit .env: set SOLIDDATA_MANAGEMENT_KEY and GEMINI_API_KEY (required)
```

Also set in `.env`: `SEMANTIC_LAYER_ID` (required — UUID from the Solid platform). Optional: `MODEL`, `AUTH_ENDPOINT`, `MCP_SERVER_URL` (for SolidData **dev**; defaults are production).

**Snowflake (optional):** To run the generated SQL in Snowflake and have the Reporter analyze the data, set in `.env`: `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`, and `SNOWFLAKE_SCHEMA` (and optionally `SNOWFLAKE_ROLE`). The app uses the **Snowflake Python connector** with username/password only—no PAT, no MCP API, no network policy or IP whitelisting. See [Snowflake setup](#snowflake-setup).

### 1.3 Run

**With uv:**

```bash
uv sync
uv run soliddata_mcp_poc "How many users signed up last month?"
# Or: uv run run_crew "Your question here"
# Interactive (prompt for question):
uv run soliddata_mcp_poc
```

**With pip:**

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
soliddata_mcp_poc "How many users signed up last month?"
# Or: run_crew "Your question here"
```

### 1.4 What You See

1. “Authenticating with SolidData…” then “Authentication successful.”
2. Crew runs: SQL Analyst calls Solid MCP **text2sql**; if Snowflake connector is configured, the executor runs the SQL in Snowflake and the Reporter summarizes the results; otherwise the Reporter explains what the query does.
3. **Result is printed in the terminal only** (no file output).


---

## Part 2: Solid MCP as a CrewAI Custom Tool

The **`solid_mcp_tool`** folder contains a standalone CrewAI **custom tool** (no crew/agents): it connects to Solid’s MCP and exposes **text2sql** so any CrewAI agent can use it. You can publish this to the CrewAI Tool Repository and use it in crews/flows or in **CrewAI Enterprise (AMP / Crew Studio)**.

### 2.1 What’s in `solid_mcp_tool/`

- **`tool.py`** — Self-contained: auth + MCP call. Declares `env_vars` via `EnvVar` so CrewAI Enterprise (AMP) injects required secrets (`SOLIDDATA_MANAGEMENT_KEY`, `SEMANTIC_LAYER_ID`) at runtime.
- **`README.md`** — Usage, env vars, publish instructions, and AMP deployment notes.

### 2.2 How it works (tool flow)

1. Agent sends `{question}` to the tool.
2. Tool reads `SEMANTIC_LAYER_ID` from environment (injected by AMP via `env_vars` or from `.env` locally).
3. Tool authenticates with SolidData using `SOLIDDATA_MANAGEMENT_KEY`.
4. Tool calls MCP `text2sql` with `{"question": ..., "semantic_layer_id": ...}`.
5. Returns the generated SQL and explanation.

### 2.3 Environment variables (tool)

| Variable | Required | Description |
|---|---|---|
| `SOLIDDATA_MANAGEMENT_KEY` | Yes | SolidData management key with MCP access. |
| `SEMANTIC_LAYER_ID` | Yes | UUID of the semantic layer (passed as MCP argument). |
| `AUTH_ENDPOINT` | No | Override auth URL. Default: production. |
| `MCP_SERVER_URL` | No | Override MCP URL. Default: production. |

In **CrewAI Enterprise**, set these in the **tool configuration** in Crew Studio. The tool class declares them via `env_vars` so AMP injects them into `os.environ` before `_run` executes.

### 2.4 Publish the Tool to CrewAI (CLI)

Do these steps in a **normal terminal**, in a new directory.

1. **Log in to CrewAI**
   ```bash
   crewai login
   ```

2. **Create the tool project**
   ```bash
   crewai tool create solid_mcp_tool
   ```

3. **Replace the scaffold `tool.py`**  
   Copy the entire contents of this repo's `solid_mcp_tool/tool.py` into the new project's `tool.py`.

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

After publishing, install with `crewai tool install <tool-name>`. Set `SOLIDDATA_MANAGEMENT_KEY` and `SEMANTIC_LAYER_ID` in the project or in CrewAI AMP tool config.

---

## Project Structure

```
solid-mcp-poc/                  # Repo root
├── .env.example
├── pyproject.toml
├── README.md
├── uv.lock
├── solid_mcp_tool/             # Standalone CrewAI custom tool (publish separately; not used by this demo’s crew)
│   ├── __init__.py
│   ├── tool.py                 # Self-contained: auth + MCP call + env_vars for AMP injection
│   └── README.md
└── src/
    └── soliddata_mcp_poc/      # Demo app: auth → MCP crew → terminal output
        ├── __init__.py
        ├── main.py             # Entry: auth → crew → print result
        ├── auth.py             # SolidData management key → bearer token
        ├── config.py           # Settings from .env
        ├── crew.py             # Crew: SQL Analyst (MCP text2sql) → [Snowflake Executor] → Reporter
        └── snowflake_connector_tool.py  # Snowflake SQL via connector (username/password; max 1000 rows)
```

No file output; no `config/` YAML (agents/tasks are in code). Entry points: `soliddata_mcp_poc` and `run_crew` (see `pyproject.toml`).


---

## Snowflake setup

Snowflake is used only via the **Snowflake Python connector** with **username and password**. No PAT, no Snowflake MCP API, and no network policy or IP whitelisting is required.

In `.env` set:

- `SNOWFLAKE_ACCOUNT` — e.g. `xy12345.us-east-1` (see [Account identifiers](https://docs.snowflake.com/en/user-guide/admin-account-identifier))
- `SNOWFLAKE_USER` — your Snowflake user
- `SNOWFLAKE_PASSWORD` — your password
- `SNOWFLAKE_WAREHOUSE` — warehouse to use
- `SNOWFLAKE_DATABASE` — database to use
- `SNOWFLAKE_SCHEMA` — schema to use
- `SNOWFLAKE_ROLE` — (optional) role to use

When all of the required vars are set, the crew runs the generated SQL in Snowflake and the Reporter analyzes the results. If any are missing, the crew skips the Snowflake step and the Reporter only explains what the SQL does. The Snowflake tool returns at most 1000 rows per query (configurable via the tool’s `max_rows` when instantiating it in code).

---

## Troubleshooting

- **Auth OK but MCP 401 / connection cancelled**  
  Use the same environment for auth and MCP: both production or both dev. Confirm your management key has MCP access with SolidData.

- **Missing or placeholder key**  
  Set real `SOLIDDATA_MANAGEMENT_KEY`, `GEMINI_API_KEY`, and `SEMANTIC_LAYER_ID` in `.env`.

- **Tool returns `'question'` or empty result in AMP**  
  The tool's `env_vars` must be configured in **CrewAI Enterprise tool config** so AMP injects `SOLIDDATA_MANAGEMENT_KEY` and `SEMANTIC_LAYER_ID` into `os.environ`. Without this, the tool can't authenticate or pass the semantic layer ID. After changing tool config, **republish** the tool so AMP picks up the latest version.

- **`ImportError: cannot import name 'SolidMcpTool'`**  
  The deployed package on AMP is stale. Republish the tool with an incremented version.

- **Snowflake step not running**  
  Snowflake runs only when all of these are set in `.env`: `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA`. If any are missing, the crew uses the two-task flow (SQL + report on the query only).

- **"Invalid response from LLM call - None or empty"**  
  This can occur when the LLM (e.g. Gemini) returns an empty response after a tool run. The crew retries the task automatically. To reduce how often it happens, the Snowflake SQL Executor uses a lower temperature and explicit `max_tokens`; the Snowflake tool also caps results at 1000 rows so context stays manageable. If it persists, check API rate limits and try again.

---

## References

- [CrewAI — Create Custom Tools](https://docs.crewai.com/en/learn/create-custom-tools)
- [CrewAI — Tool Repository (publish / install)](https://docs.crewai.com/en/enterprise/guides/tool-repository)
- [Crew AI AMP](https://app.crewai.com)
