# SolidData MCP POC — CrewAI + Solid MCP (Query-Only Demo)

Minimal **demonstration** of [Solid](https://getsolid.ai)'s MCP server with [CrewAI](https://crewai.com):

- **What it does:** You ask a natural-language question → the crew calls Solid’s MCP **text2sql** tool → Solid returns the generated SQL and a short explanation → an agent analyzes what the query does. All output is **printed in the terminal**.
- **What it does not do:** It does **not** execute any SQL. No database connectivity and no query results.

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
- [Troubleshooting](#troubleshooting)
- [References](#references)

---

## Architecture

```
Question (natural language)
        │
        ▼
┌──────────────────┐   MCP (text2sql)    ┌─────────────────────┐
│  SQL Analyst     │ ──────────────────► │  SolidData MCP      │
│  (Agent 1)       │ ◄────────────────── │  Server             │
└────────┬─────────┘   SQL + explanation └─────────────────────┘
         │             (no execution)
         ▼
┌──────────────────┐
│  Reporter        │  → Plain-language analysis of what the query does
│  (Agent 2)       │
└────────┬─────────┘
         │
         ▼
   Result printed in terminal only
```

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
3. **SQL Analyst** — Uses the MCP **text2sql** tool to get a SQL query + short explanation (no execution).
4. **Reporter** — Explains in plain language what the query does.
5. **Output** — Result is **printed in the terminal only**.

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
2. Crew runs: SQL Analyst calls Solid MCP **text2sql** (SQL + explanation only), Reporter explains what the query does.
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
        ├── main.py           # Entry: auth → crew → print result
        ├── auth.py           # SolidData management key → bearer token
        ├── config.py         # Settings from .env
        └── crew.py           # Crew: SQL Analyst (MCP) → Reporter
```

No file output; no `config/` YAML (agents/tasks are in code).


---

## Troubleshooting

- **Auth OK but MCP 401 / connection cancelled**  
  Use the same environment for auth and MCP: both production or both dev. Confirm your management key has MCP access with SolidData.

- **Missing or placeholder key**  
  Set real `SOLIDDATA_MANAGEMENT_KEY` and `GEMINI_API_KEY` in `.env`.

---

## References

- [CrewAI — Create Custom Tools](https://docs.crewai.com/en/learn/create-custom-tools)
- [CrewAI — Tool Repository (publish / install)](https://docs.crewai.com/en/enterprise/guides/tool-repository)
- [Crew AI AMP](https://app.crewai.com)
