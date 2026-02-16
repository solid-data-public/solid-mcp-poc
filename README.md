# SolidData MCP POC — CrewAI + Solid MCP (Query-Only Demo)

Minimal **demonstration** of [Solid](https://getsolid.ai)'s MCP server with [CrewAI](https://crewai.com):

- **What it does:** You ask a natural-language question → the crew calls Solid’s MCP **text2sql** tool → Solid returns the generated SQL. Optionally that SQL is executed in Snowflake (when configured), and the Reporter analyzes the actual query results; otherwise the Reporter explains what the SQL does. All output is **printed in the terminal**.
- **Snowflake (optional):** When Snowflake MCP env vars are set, the flow adds a step to run the generated SQL in Snowflake; the Reporter then analyzes the **data** returned, not just the query.

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
  - [2.2 Publish the Tool to CrewAI (CLI)](#22-publish-the-tool-to-crewai-cli)
- [Project Structure](#project-structure)
- [Snowflake MCP setup](#snowflake-mcp-setup)
- [Troubleshooting](#troubleshooting)
- [References](#references)

---

## Architecture

### Crew flow (with optional Snowflake execution)

1. **SQL Analyst** — Uses Solid MCP **text2sql** to turn the user question into a SQL query and a short explanation.
2. **Snowflake SQL Executor** *(only when Snowflake MCP is configured)* — Takes the SQL from step 1, runs it in Snowflake via the Snowflake MCP tool, and returns the raw query results.
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
│  SQL Executor    │ ──────────────────► │  Snowflake MCP       │
│  (Agent 2)       │   execute SQL       │  (sql_exec_tool)     │
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

- The **Solid MCP tool** (`solid_mcp_tool/`) is used only by the SQL Analyst to call Solid's text2sql; it is not modified by the crew flow.
- The **Snowflake MCP tool** (`src/soliddata_mcp_poc/snowflake_mcp_tool.py`) is used only in the crew flow to execute the generated SQL and return results to the Reporter.

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
2. **MCP** — `crew.py` creates an `MCPServerHTTP` client for the SolidData MCP server with that token.
3. **SQL Analyst** — Uses the MCP **text2sql** tool to get a SQL query + short explanation.
4. **Snowflake Executor** *(optional)* — If Snowflake MCP is configured, runs that SQL in Snowflake and returns query results.
5. **Reporter** — If Snowflake ran: summarizes the **query results** and writes a stakeholder report. Otherwise: explains in plain language what the query does.
6. **Output** — Result is **printed in the terminal only**.

### 1.1 Prerequisites

- Python 3.10–3.13
- **SolidData management key** (MCP-enabled)
- **Google Gemini API key** (e.g. [Google AI Studio](https://aistudio.google.com/apikey))
- Optional: [uv](https://docs.astral.sh/uv/)

### 1.2 Setup

From the **project root** (where `pyproject.toml` and `.env` live):

```bash
cp .env.example .env
# Edit .env: set SOLIDDATA_MANAGEMENT_KEY and GEMINI_API_KEY
```

Optional: `AUTH_ENDPOINT` and `MCP_SERVER_URL` for SolidData **dev** (defaults are production).

**Snowflake (optional, for executing SQL and reporting on results):**  
To run the generated SQL in Snowflake and have the Reporter analyze the data, set in `.env`:

- `SNOWFLAKE_MCP_SERVER_URL` — e.g. `https://your-account.snowflakecomputing.com`
- `SNOWFLAKE_DATABASE` — database where the MCP server is located
- `SNOWFLAKE_SCHEMA` — schema name
- `SNOWFLAKE_MCP_SERVER_NAME` — name of the MCP server object
- `SNOWFLAKE_ACCESS_TOKEN` — OAuth access token or Programmatic Access Token (PAT) for Snowflake MCP
- `SNOWFLAKE_SQL_TOOL_NAME` — (optional) MCP tool name for SQL execution; default `sql_exec_tool`

If any of the first four are missing, the crew runs without the Snowflake step (SQL only, Reporter explains the query).

See [Snowflake MCP setup](#snowflake-mcp-setup) below for how to create the MCP server and access token in Snowflake.

### 1.3 Run

**With uv:**

```bash
uv sync
uv run soliddata_mcp_poc "How many users signed up last month?"
# Or interactive:
uv run soliddata_mcp_poc
```

**With pip:**

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
soliddata_mcp_poc "How many users signed up last month?"
```

### 1.4 What You See

1. “Authenticating with SolidData…” then “Authentication successful.”
2. Crew runs: SQL Analyst calls Solid MCP **text2sql**; if Snowflake is configured, the executor runs the SQL in Snowflake and the Reporter summarizes the results; otherwise the Reporter explains what the query does.
3. **Result is printed in the terminal only** (no file output).


---

## Part 2: Solid MCP as a CrewAI Custom Tool

The **`solid_mcp_tool`** folder contains a single-component CrewAI **custom tool** (no crew/agents): it connects to Solid’s MCP and exposes **text2sql** so any CrewAI agent can use it. You can publish this to the CrewAI Tool Repository and use it in crews/flows or in CrewAI AMP.

### 2.1 What’s in `solid_mcp_tool/`

- **`tool.py`** — One file: SolidData auth + MCP call. This is the code you paste into a `crewai tool create` project.
- **`README.md`** — Short usage and env vars.

This is the **standard CrewAI Enterprise custom tool** pattern (one tool, no crew flow).

### 2.2 Publish the Tool to CrewAI (CLI)

Do these steps in a **normal terminal** (not the IDE), in a new directory (e.g. your home or a tools folder).

1. **Log in to CrewAI**
   ```bash
   crewai login
   ```
   Complete the browser device confirmation.

2. **Create the tool project**
   ```bash
   crewai tool create solid_mcp_tool
   ```
   This creates a new folder (e.g. `solid_mcp_tool/`) with a scaffolded `tool.py` and `pyproject.toml`.

3. **Replace the scaffold `tool.py`**  
   Copy the **entire contents** of this repo’s **`solid_mcp_tool/tool.py`** into the new project’s `tool.py` (overwrite the scaffold).

4. **Update `pyproject.toml`**
   - Set `name`, `version`, and `description` as you want.
   - **Increment the `version`** for every publish (e.g. `0.1.0` → `0.1.1`).
   - Ensure dependencies include at least `crewai` and `httpx` (add `httpx` if the scaffold doesn’t list it).

5. **Commit and publish**
   ```bash
   git add .
   git commit -m "Solid MCP text2sql tool"
   crewai tool publish
   ```
   Use `crewai tool publish --public` to publish as a public tool.

After publishing, other projects can install it with `crewai tool install <tool-name>`. Set `SOLIDDATA_MANAGEMENT_KEY` (and optionally `AUTH_ENDPOINT`, `MCP_SERVER_URL`) in that project or in CrewAI AMP for the tool.

---

## Project Structure

```
soliddata_mcp_poc/
├── .env.example
├── pyproject.toml
├── README.md
├── uv.lock
├── solid_mcp_tool/           # CrewAI custom tool (publish separately)
│   ├── __init__.py
│   ├── tool.py               # Copy this into crewai tool create project
│   └── README.md
└── src/
    └── soliddata_mcp_poc/    # Tools to Demonstrate MCP with CrewAI in a Terminal
        ├── __init__.py
        ├── main.py              # Entry: auth → crew → print result
        ├── auth.py              # SolidData management key → bearer token
        ├── config.py            # Settings from .env
        ├── crew.py              # Crew: SQL Analyst → [Snowflake Executor] → Reporter
        └── snowflake_mcp_tool.py # Snowflake MCP tool (used in crew flow only)
```

No file output; no `config/` YAML (agents/tasks are in code).


---

## Snowflake MCP setup

If you have your **database**, **schema**, and desired **SQL tool name** but need to create the MCP server and access token in Snowflake, follow these steps. Reference: [Snowflake-managed MCP server](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp) and [Getting Started with Managed Snowflake MCP Server](https://quickstarts.snowflake.com/guide/getting-started-with-snowflake-mcp-server/index.html).

### 1. Create the MCP server object (SQL only)

In Snowsight, open a SQL worksheet in the **database and schema** where you want the MCP server. Run (replace placeholders with your values):

```sql
CREATE OR REPLACE MCP SERVER <server_name>
  FROM SPECIFICATION $$
tools:
  - name: "<sql_tool_name>"
    type: "SYSTEM_EXECUTE_SQL"
    title: "SQL Execution Tool"
    description: "A tool to execute SQL queries against the connected Snowflake database."
$$
```

- **`<server_name>`** — e.g. `MY_MCP_SERVER`. Use this as `SNOWFLAKE_MCP_SERVER_NAME` in `.env`. Use hyphens in hostnames, not underscores.
- **`<sql_tool_name>`** — e.g. `sql_exec_tool`. Use this as `SNOWFLAKE_SQL_TOOL_NAME` in `.env`.

Example:

```sql
CREATE OR REPLACE MCP SERVER MY_MCP_SERVER
  FROM SPECIFICATION $$
tools:
  - name: "sql_exec_tool"
    type: "SYSTEM_EXECUTE_SQL"
    title: "SQL Execution Tool"
    description: "A tool to execute SQL queries against the connected Snowflake database."
$$
```

Verify:

```sql
SHOW MCP SERVERS IN SCHEMA;
DESCRIBE MCP SERVER <server_name>;
```

### 2. Grant permissions

The role that will call the MCP server needs:

- **USAGE** on the MCP server (to connect and list tools).
- **MODIFY** on the MCP server (to use `tools/list` and `tools/call`).

Example (replace role and server name):

```sql
GRANT USAGE ON MCP SERVER <server_name> TO ROLE <your_role>;
GRANT MODIFY ON MCP SERVER <server_name> TO ROLE <your_role>;
```

### 3. Create a Programmatic Access Token (PAT) — simplest for this app

Your app uses **Bearer token** auth. The easiest way is a [Programmatic Access Token (PAT)](https://docs.snowflake.com/en/user-guide/programmatic-access-tokens):

1. In Snowsight: **Governance & security** → **Users & roles** → select your user.
2. Under **Programmatic access tokens**, click **Generate new token**.
3. **Name** (e.g. `mcp_poc_token`), optional **Comment**, **Expires in** (e.g. 15 days).
4. Under scope: choose **One specific role** and select a role that has USAGE/MODIFY on the MCP server (least privilege).
5. **Generate**, then **copy** the token immediately (it is shown only once).
6. Put that value in `.env` as `SNOWFLAKE_ACCESS_TOKEN`.

**Note:** By default, PATs require the user to be under a [network policy](https://docs.snowflake.com/en/user-guide/network-policies). If you hit auth errors, your admin may need to attach a network policy that allows your IP, or use an [authentication policy](https://docs.snowflake.com/en/user-guide/programmatic-access-tokens#prerequisites) to relax the requirement.

### 4. (Optional) OAuth instead of PAT

For production, Snowflake recommends OAuth. High-level steps:

1. Create an OAuth security integration (see [CREATE SECURITY INTEGRATION (Snowflake OAuth)](https://docs.snowflake.com/en/sql-reference/sql/create-security-integration-oauth-snowflake)).
2. Get client id and secret: `SELECT SYSTEM$SHOW_OAUTH_CLIENT_SECRETS('<INTEGRATION_NAME>');`
3. Implement an OAuth flow in your app to obtain an access token and pass it as `SNOWFLAKE_ACCESS_TOKEN` (Bearer). The MCP server accepts the same Bearer token for OAuth.

### 5. Set your account URL and `.env`

- **Account URL:** `https://<account_locator>.snowflakecomputing.com`  
  Format depends on your cloud and account; see [Account identifiers](https://docs.snowflake.com/en/user-guide/admin-account-identifier). Example: `https://xy12345.us-east-1.snowflakecomputing.com`.
- In `.env` set:
  - `SNOWFLAKE_MCP_SERVER_URL` = that base URL (no path).
  - `SNOWFLAKE_DATABASE` = database where you created the MCP server.
  - `SNOWFLAKE_SCHEMA` = schema where you created the MCP server.
  - `SNOWFLAKE_MCP_SERVER_NAME` = `<server_name>` from step 1.
  - `SNOWFLAKE_ACCESS_TOKEN` = PAT (or OAuth access token).
  - `SNOWFLAKE_SQL_TOOL_NAME` = `<sql_tool_name>` from step 1 (e.g. `sql_exec_tool`).

### 6. Test the connection

From a terminal (replace account, database, schema, server name, and token):

```bash
curl -X POST "https://<account>.snowflakecomputing.com/api/v2/databases/<database>/schemas/<schema>/mcp-servers/<server_name>" \
  --header 'Content-Type: application/json' \
  --header "Authorization: Bearer <your_token>" \
  --data '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

You should get a JSON response with a `result.tools` array. If you see your SQL tool, the crew can use it.

**SQL tool argument:** This app calls the SQL tool with `arguments: {"query": "<SQL>"}`. Some Snowflake MCP SQL tools expect `"sql"` instead of `"query"`. If execution fails, check the tool’s `inputSchema` from `tools/list` and use the parameter name it expects (you may need to adjust the executor task in `crew.py` to pass `sql` instead of `query`).

---

## Troubleshooting

- **Auth OK but MCP 401 / connection cancelled**  
  Use the same environment for auth and MCP: both production or both dev. Confirm your management key has MCP access with SolidData.

- **Missing or placeholder key**  
  Set real `SOLIDDATA_MANAGEMENT_KEY` and `GEMINI_API_KEY` in `.env`.

- **Snowflake step not running**  
  The Snowflake executor only runs when all of `SNOWFLAKE_MCP_SERVER_URL`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA`, and `SNOWFLAKE_MCP_SERVER_NAME` are set in `.env`. If any are missing, the crew uses the two-task flow (SQL + report on the query only).

---

## References

- [CrewAI — Create Custom Tools](https://docs.crewai.com/en/learn/create-custom-tools)
- [CrewAI — Tool Repository (publish / install)](https://docs.crewai.com/en/enterprise/guides/tool-repository)
- [Crew AI AMP](https://app.crewai.com)
