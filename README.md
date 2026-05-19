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
- [Using the OpenAPI spec (Workato, Power Platform, etc.)](#using-the-openapi-spec-workato-power-platform-etc)
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

- The **SQL Analyst** connects **directly** to SolidData’s MCP server via **MCPServerHTTP** in `crew.py`: `auth.py` exchanges the management key for a **Bearer** token, then the client calls Solid’s MCP URL with that header (**not** through the Azure REST bridge). The **`solid_mcp_tool/`** folder is the same integration pattern for **publishable `BaseTool`s**: management key → JWT → **CrewAI `MCPClient` + `HTTPTransport`** to Solid’s MCP URL (see Part 2). Use it in AMP or other crews when you want explicit tools instead of attaching `MCPServerHTTP` to an agent. This demo does not import `solid_mcp_tool` directly.
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
  Example standalone token exchange:

  ```bash
  curl --location 'https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key' \
    --header 'Content-Type: application/json' \
    --data '{"management_key": "YOUR-SOLID-MGMT-KEY-HERE"}'
  ```

Then use the Inspector UI to list tools and call **text2sql** (or **glossary_search** with a Bearer-authenticated MCP client) to confirm the connection works before running the full crew.

---

## Part 1: Run the Demo (Terminal Only)

Simplest path: **ask a question → see the SQL response from Solid and the agent’s analysis** in the terminal.


### How It Works

1. **Auth** — `auth.py` exchanges `SOLIDDATA_MANAGEMENT_KEY` for a bearer token (SolidData auth API).
2. **MCP** — `crew.py` creates an `MCPServerHTTP` client for the SolidData MCP server with that token and attaches it to the SQL Analyst agent (Solid exposes **text2sql** and **glossary_search**; the task text tells the agent when to use each).
3. **SQL Analyst** — Uses MCP **text2sql** for data questions or **glossary_search** for definitions / terminology.
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

**CrewAI + Solid (this repo):** exchange the management key for a JWT, then connect **directly** to Solid’s MCP HTTP endpoint with **`Authorization: Bearer …`**. Part 1 does that with **`MCPServerHTTP`** on an agent; **`solid_mcp_tool`** does the same with **`MCPClient`** + **`HTTPTransport`** inside **`BaseTool`** implementations — **no Azure REST-to-MCP bridge**. The bridge is only for REST/OpenAPI consumers ([Using the OpenAPI spec](#using-the-openapi-spec-workato-power-platform-etc)).

The **`solid_mcp_tool`** folder is optional **publishable** tools for **CrewAI Enterprise (AMP)** or other crews: use them when you want **`solid_text2sql`** / **`solid_glossary_search`** as explicit tools instead of wiring `MCPServerHTTP` on an agent.

### 2.1 What’s in `solid_mcp_tool/`

- **`tool.py`** — Self-contained: auth exchange + **direct** Solid MCP (`MCPClient` / `HTTPTransport`, same idea as Part 1). Defines **`SolidMcpTool`** (text2sql) and **`SolidGlossarySearchTool`** (glossary_search). Declares `env_vars` so CrewAI Enterprise (AMP) injects secrets at runtime.
- **`README.md`** — Usage, env vars, publish instructions, and AMP deployment notes.

### 2.2 How it works (tool flow — direct MCP `BaseTool`s)

1. Agent sends arguments to **solid_text2sql** (`question`, optional `semantic_layer_id`) or **solid_glossary_search** (`query` only).
2. Text2sql: tool reads `SEMANTIC_LAYER_ID` from the environment when not passed. Glossary: MCP tool **`glossary_search`** with **`query`** only.
3. Tool exchanges `SOLIDDATA_MANAGEMENT_KEY` for a JWT, opens a short-lived MCP session to **`MCP_SERVER_URL`** with **`Authorization: Bearer …`**, calls **`text2sql`** or **`glossary_search`**, then disconnects.
4. Returns the tool result text from the MCP server.

### 2.3 Environment variables (tool)

| Variable | Required | Description |
|---|---|---|
| `SOLIDDATA_MANAGEMENT_KEY` | Yes | SolidData management key with MCP access. |
| `SEMANTIC_LAYER_ID` | Yes for text2sql | UUID of the semantic layer (passed to MCP as `semantic_layer_ids`). Not required for glossary. |
| `AUTH_ENDPOINT` | No | Override auth URL. Default: production. |
| `MCP_SERVER_URL` | No | Solid MCP HTTP URL. Default: production (same as Part 1 `MCP_SERVER_URL`). |

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

## Using the OpenAPI spec (Workato, Power Platform, etc.)

If your agent or platform only supports **HTTP/REST with a Swagger or OpenAPI spec** (no native MCP or Python SDK), use the root **`openapi.yaml`** to call Solid MCP tools through the **Azure REST-to-MCP bridge**.

**CrewAI and direct MCP** (this repo’s [Part 1](#part-1-run-the-demo-terminal-only) and [Part 2](#part-2-solid-mcp-as-a-crewai-custom-tool)) do **not** use this spec: they exchange the management key for a JWT, then call Solid’s **MCP URL** with **`Authorization: Bearer …`**. The OpenAPI file is only for REST/OpenAPI consumers (Workato, Copilot Studio, Logic Apps, Postman, etc.).

This OpenAPI path applies to:

- **Workato** (custom connector)
- **Microsoft Power Platform / Copilot Studio** (custom connector or HTTP action)
- **Logic Apps**, **n8n**, or other automation tools that consume OpenAPI
- **API testers** (e.g. apinotes.io, Postman) to validate the contract

### What’s in the spec (v2.0.0)

The spec defines **one server** (the Azure bridge base URL) and **four POST operations**. Every operation uses the same pattern: **`management_key` plus tool-specific fields in the JSON body**—no separate auth call and no Bearer token on the bridge.

| Path | MCP tool | Success response field |
|------|----------|-------------------------|
| **POST /text2sql** | `text2sql` | `message` (SQL + explanation, often markdown) |
| **POST /glossary_search** | `glossary_search` | `result` (e.g. `synthesized_answer`, `answer_status`) |
| **POST /specific_asset_information_tool** | `specific_asset_information_tool` | `result` (asset metadata + natural-language answer) |
| **POST /semantic_model_qa** | `semantic_model_qa` | `result` (semantic model Q&A payload) |

On every call the bridge exchanges `management_key` for a short-lived JWT internally (tokens expire; renewal is automatic). Callers only store the Solid **management key**—never a Bearer token.

The **`code` query parameter** is the Azure Function **host** key (Portal → Function App → App keys → `_master` or **default**). The same host key applies to every path (pre-filled in `openapi.yaml`). Function-specific keys only work on one route and return **401** on others. For local E2E, set `BRIDGE_FUNCTION_KEY` in `.env` or let `scripts/e2e_openapi_test.py` read the default from `openapi.yaml` via `scripts/bridge_openapi.py`.

### Flow for each request

For **every** bridge operation:

1. Send **one POST** to `{bridge_base}/{path}` (e.g. `…/api/mcp/text2sql`) with JSON containing **`management_key`** and the fields required for that tool.
2. Include the **`code`** query parameter (importing `openapi.yaml` into Workato/Copilot Studio applies the spec default automatically).

No auth endpoint call and no `Authorization: Bearer` header to the bridge.

### Example request bodies

Replace `management_key` with your Solid key. Use your own UUIDs for semantic layers and models where applicable.

**text2sql**

```json
{
  "management_key": "YOUR-SOLID-MGMT-KEY-HERE",
  "question": "What were the top 5 products in terms of revenue?",
  "semantic_layer_ids": ["998b655a-75eb-4873-bb1e-3ddd23164065"]
}
```

**glossary_search**

```json
{
  "management_key": "YOUR-SOLID-MGMT-KEY-HERE",
  "query": "What does LLS mean?"
}
```

**specific_asset_information_tool**

```json
{
  "management_key": "YOUR-SOLID-MGMT-KEY-HERE",
  "question": "What column includes information about when an order was delivered?",
  "asset_name": "SUN_SPECTRA.PUBLIC.ORDERS"
}
```

Optional: `"asset_type": "table"` (or `dashboard`).

**semantic_model_qa**

```json
{
  "management_key": "YOUR-SOLID-MGMT-KEY-HERE",
  "semantic_model_id": "00000000-0000-0000-0000-000000000000",
  "question": "What does this model cover?"
}
```

**Direct MCP (CrewAI / Inspector — not the bridge)**  
After exchanging the management key for a Bearer token, MCP tool calls use tool arguments only—**no `management_key` in the tool payload**. Example for glossary:

```json
{
  "query": "What does LLS mean?"
}
```

### OpenAPI YAML spec walkthrough

This section walks through [openapi.yaml](openapi.yaml) so you can use it in Workato, Copilot Studio, or similar.

- **`openapi` and `info`** — OpenAPI **3.0.3**, title **Solid MCP Bridge**, version **2.0.0**. `info.description` lists all four supported tools and the single-call model (`management_key` in body; bridge handles JWT). **No two-step auth** for bridge callers.
- **`servers`** — Single bridge base (e.g. `https://…azurewebsites.net/api/mcp`). Paths are relative: `…/text2sql`, `…/glossary_search`, `…/specific_asset_information_tool`, `…/semantic_model_qa`.
- **`paths`** — Each operation is **POST only**, `security: []`, optional **`code`** query param (same host key default on every path), required **`application/json`** body with **`management_key`**, and shared error responses **400**, **401**, **405**, **502**.
- **`components/schemas`** — Request/response types per tool (`Text2SqlRequest` → `message`; others → `result`). **ErrorResponse** has required `error` string.

**How Workato (or similar) uses this:** Import `openapi.yaml` → four operations appear → store **management_key** as a connection secret → one POST per action with `management_key` plus the fields for that operation. No token handling on the bridge.

### How to use it

- **Workato:** Import the spec; map **management_key** from the connection into each action body; pass tool-specific fields (`question` / `semantic_layer_ids`, `query`, `asset_name`, `semantic_model_id`, etc.).
- **Power Platform / Copilot Studio:** Custom connector or HTTP action per path; same single POST body shape.
- **API testers / CI:** Import `openapi.yaml` or run `python scripts/e2e_openapi_test.py` (defaults to **text2sql**; set `BRIDGE_TOOL=glossary_search` etc.). Bridge URL and `code` resolve from `.env` or from `openapi.yaml` (see `scripts/bridge_openapi.py`).

The root **`openapi.yaml`** is the source of truth for bridge URLs, request/response shapes, and the Azure host `code` default for REST/OpenAPI clients.

---

## Project Structure

```
solid-mcp-poc/                  # Repo root
├── .env.example
├── pyproject.toml
├── README.md
├── uv.lock
├── openapi.yaml                # OpenAPI 3.0 Azure bridge (4 tools, single-call auth); see "Using the OpenAPI spec" above
├── scripts/
│   ├── bridge_openapi.py       # Read bridge base URL / code default from openapi.yaml
│   └── e2e_openapi_test.py     # E2E: single POST per bridge tool
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

**REST bridge (Workato, Copilot Studio, other agents):** An Azure Function App exposes Solid MCP tools as REST (**text2sql**, **glossary_search**, **specific_asset_information_tool**, **semantic_model_qa**). Use it when the consumer only supports HTTP/OpenAPI. The root **openapi.yaml** documents the bridge base URL, paths, bodies, and the shared host `code` default. See [Using the OpenAPI spec](#using-the-openapi-spec-workato-power-platform-etc).


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
