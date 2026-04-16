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

If your agent or platform only supports **HTTP/REST with a Swagger or OpenAPI spec** (no native MCP or Python SDK), use the root **`openapi.yaml`** to connect to Solid’s MCP **text2sql** and **glossary** search via the **Azure REST-to-MCP bridge**. **CrewAI with MCP** (this repo’s [Part 1](#part-1-run-the-demo-terminal-only)) usually skips the bridge: exchange the management key for a JWT, then call Solid’s **MCP URL** with **`Authorization: Bearer …`** (native MCP tools). The bridge is for REST/OpenAPI-only stacks.

This OpenAPI path applies to:

- **Workato** (custom connector)
- **Microsoft Power Platform / Copilot Studio** (custom connector or HTTP action)
- **Logic Apps**, **n8n**, or other automation tools that consume OpenAPI
- **API testers** (e.g. apinotes.io, Postman) to validate the contract

### What’s in the spec

The spec defines **one server** (the Azure bridge) and **REST operations** for Solid MCP tools:

- **POST /text2sql** — unchanged: send `management_key`, `question`, and `semantic_layer_ids` in the body.
- **POST /glossary** (and **POST /glossary_search**, an alias with the same behavior) — glossary search: send `management_key` and `query` in the body.

For both bridge paths, the service exchanges the management key for a JWT internally on every call—**no separate auth step**. The Azure Function host key is included in the spec as the default for the `code` query parameter, so you do not need to set `BRIDGE_FUNCTION_KEY` in env for connector setups.

### Flow for each request

**Text2SQL (unchanged)**

1. Send **one POST** to the bridge `/text2sql` URL with a JSON body containing `management_key`, `question`, and `semantic_layer_ids`.
2. Optionally include the `code` query parameter if your connector does not use the spec's default (e.g. for a different deployment or key).

**Glossary search (bridge — management key in body)**

1. Send **one POST** to the bridge **`/glossary`** or **`/glossary_search`** URL with a JSON body containing **`management_key`** and **`query`** (same single-call pattern as text2sql: the bridge obtains the JWT; you do not send a Bearer token to the bridge).
2. Optionally include the `code` query parameter like text2sql.

No auth endpoint call and no Bearer token handling for the bridge—the bridge does that for you when you include `management_key` in the body.

### Example request body

The following JSON payload works with the bridge. Replace the `management_key` with your own Solid management key (and redact it in production); use your semantic layer UUID(s) in `semantic_layer_ids`.

```json
{
  "management_key": "YOUR-SOLID-MGMT-KEY-HERE",
  "question": "What were the top 5 products in terms of revenue",
  "semantic_layer_ids": [
    "998b655a-75eb-4873-bb1e-3ddd23164065"
  ]
}
```

**Glossary search (bridge — same base URL as text2sql)**  
Full URL examples (append path to the bridge base in `servers`, e.g. `https://…azurewebsites.net/api/mcp/glossary` or `…/api/mcp/glossary_search`). Request body:

```json
{
  "management_key": "YOUR-SOLID-MGMT-KEY-HERE",
  "query": "What does LLS mean?"
}
```

**Glossary search (Solid MCP directly — already authenticated with Bearer)**  
If you call Solid’s MCP **glossary_search** tool over HTTP with **`Authorization: Bearer <token>`** (token from the auth exchange, same as for **text2sql** in the Inspector or SDK), the tool argument shape is only the search string—**no `management_key` in the tool payload** (the key was used earlier to get the token). Example argument / body shape:

```json
{
  "query": "What does LLS mean?"
}
```

### OpenAPI YAML spec walkthrough

This section walks through [openapi.yaml](openapi.yaml) section by section so you can explain it to a team or use it confidently in an automation provider like Workato.

- **`openapi` and `info`**  
  The file declares OpenAPI version **3.0.3** and a title **"Solid MCP Bridge"**. The `info.description` focuses on the **text2sql** single-call flow (`management_key`, `question`, `semantic_layer_ids`); the same bridge also documents **glossary** routes that use **`management_key` + `query`** in the body. In all cases the bridge exchanges the management key for a JWT internally (tokens expire; the bridge handles renewal). **No two-step auth on the bridge**—callers never manage Bearer tokens to the bridge; the credential in the body is `management_key`. The `code` query parameter (Azure Function key) is described and has a default value in the spec.

- **`servers`**  
  There is a single server: the Azure bridge base URL (e.g. `https://...azurewebsites.net/api/mcp`). All paths in the spec are relative to this URL, so full URLs include `.../api/mcp/text2sql`, `.../api/mcp/glossary`, and `.../api/mcp/glossary_search`.

- **`paths` / `/text2sql`**  
  Text2SQL operation (unchanged from prior versions of this doc):
  - **Method:** POST only (no GET).
  - **`operationId: text2sql`** — Automation tools (e.g. Workato) use this as the operation name when you import the spec.
  - **`parameters`** — The `code` query parameter is the Azure Function host key. It is optional and has a default in the spec so connectors can work without extra config.
  - **`requestBody`** — Required; content type `application/json`; schema is `Text2SqlRequest`. The spec includes examples (e.g. basic single-layer and multi-layer).
  - **`responses`** — **200**: success; response body has a `message` field with the generated SQL and explanation (often markdown). **400**: bad request (missing or invalid body). **401**: auth failed (management_key missing, invalid, or expired). **405**: method not allowed (use POST). **502**: upstream Solid/MCP error.

- **`paths` / `/glossary` and `/glossary_search`**  
  Glossary search via the same bridge pattern as text2sql:
  - **Method:** POST only. **`/glossary_search`** is an alias of **`/glossary`** with identical request/response.
  - **`operationId`:** `glossarySearch` / `glossarySearchAlias`.
  - **`requestBody`** — Schema **GlossarySearchRequest**: required **`management_key`** and **`query`** (natural-language glossary question or term).
  - **`responses`** — **200**: body includes **`result`** (glossary MCP output: e.g. `synthesized_answer`, `answer_status`, optional `execution_error`). Same **400**, **401**, **405**, **502** semantics as text2sql.

- **`components/schemas`**  
  Includes at least:
  - **Text2SqlRequest** / **Text2SqlResponse** — As above; text2sql unchanged.
  - **GlossarySearchRequest** — Required: `management_key`, `query`.
  - **GlossarySearchResponse** / **GlossarySearchResult** — Success shape for glossary (nested `result`).
  - **ErrorResponse** — Required field: `error` (string), a human-readable error message.

**How Workato (or any automation provider) uses this:** Import the OpenAPI spec → the connector gets the **text2sql** and **glossary** (and alias) operations → configure the connection with your Solid management key (stored as a secret) → in a recipe or flow, send one HTTP POST per operation: for text2sql, `management_key`, `question`, and `semantic_layer_ids`; for glossary, `management_key` and `query`. No token handling on the bridge.

### How to use it

- **Workato:** Create a custom connector and import the OpenAPI spec (paste the contents of `openapi.yaml` or point to its URL). Configure the connection with your Solid **management key**. In the recipe, call **text2sql** or **glossary** / **glossary_search**: map the management key from the connection (or include it in the body as in the spec); for text2sql pass `question` and `semantic_layer_ids`; for glossary pass `query`. No auth step on the bridge.
- **Power Platform / Copilot Studio:** Import the spec as a custom connector or use an HTTP action pointing at the bridge's **text2sql** or **glossary** URL. Store the management key in a flow variable or connection; send one POST with the appropriate body (`management_key` + text2sql fields, or `management_key` + `query` for glossary). No prior auth call for the bridge.
- **API testers:** Import `openapi.yaml`, set the request body to the example shape for the operation you are testing, and send one POST to the **text2sql** or **glossary** URL (with `code` if needed). No Bearer header on the bridge.

The **Azure bridge** that exposes MCP as REST is deployed and documented in [solid-mcp-bridge/README.md](solid-mcp-bridge/README.md). The root `openapi.yaml` is the single source of truth for the **bridge URL and function key** when using REST/OpenAPI clients.

---

## Project Structure

```
solid-mcp-poc/                  # Repo root
├── .env.example
├── pyproject.toml
├── README.md
├── uv.lock
├── openapi.yaml                # OpenAPI 3.0 single-call bridge (POST /text2sql, POST /glossary); see "Using the OpenAPI spec" above
├── scripts/e2e_openapi_test.py # E2E test: single POST with management_key in body to bridge; TEXT2SQL_URL + BRIDGE_FUNCTION_KEY for local/CI
├── solid-mcp-bridge/           # Azure Function App: REST-to-MCP bridge (see solid-mcp-bridge/README.md)
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

**REST bridge (Workato, Copilot Studio, other agents):** The **solid-mcp-bridge/** directory (when present in your checkout) is an Azure Function App that exposes Solid's MCP tools as REST endpoints, including **text2sql** and **glossary** search. Use it when the consumer only supports HTTP/OpenAPI (e.g. Workato custom connector, Copilot Studio HTTP action). The root **openapi.yaml** lists the bridge as the server for these operations and includes the bridge function key in the spec (no env var needed for connector setups). See [Using the OpenAPI spec](#using-the-openapi-spec-workato-power-platform-etc) for step-by-step usage.


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
