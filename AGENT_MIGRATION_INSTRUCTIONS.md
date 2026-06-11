# Agent Instructions: Migrate to Single-Step Solid MCP Auth

**Audience:** Autonomous coding agents executing changes across any of the listed repositories.  
**Scope:** Auth simplification only — no functional changes to MCP tool behavior or business logic.  
**Status of this document:** Canonical as of Jun 11, 2026. Verified live against `https://mcp.production.soliddata.io/mcp`.

---

## 1. What Changed and Why

### The old pattern (deprecated)

Direct MCP calls (CrewAI, Python) used a two-step flow:

1. `POST https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key` with `{"management_key": "..."}` to receive a short-lived JWT.
2. Call the MCP endpoint with `Authorization: Bearer <jwt>`.

This required `AUTH_ENDPOINT` as an environment variable, a dedicated `auth.py` / `_get_mcp_token` function, and careful management of token lifetime.

### The new pattern (canonical)

Pass the management key directly as a request header on every MCP call. No prior auth exchange, no JWT, no `AUTH_ENDPOINT`:

```
Header: x-solid-management-key: <SOLIDDATA_MANAGEMENT_KEY>
```

This was verified live:
- Connection and tool call succeed with only this header.
- `AUTH_ENDPOINT` and `Authorization: Bearer` are no longer needed for direct MCP callers.

---

## 2. AUTH vs TRANSPORT — A Required Distinction

Auth simplification (the single header) is **universal**. But it does not mean every consumer calls the MCP endpoint directly. The response transport forces a split:

| Consumer type | Transport | Why |
|---|---|---|
| Python / CrewAI / MCP-native | Direct POST to `https://mcp.production.soliddata.io/mcp` | Understands SSE; uses `MCPServerHTTP` or `MCPClient`+`HTTPTransport` |
| Workato / Copilot Studio / REST-only low-code | Must go through the Azure bridge | The MCP endpoint returns `text/event-stream` SSE only (`Accept: application/json` → 406); these platforms expect complete synchronous JSON and cannot consume SSE streaming |

**The Azure bridge is retained for REST/low-code consumers.** Its job changes from exchanging `management_key` for a JWT internally to forwarding `x-solid-management-key` and buffering the SSE response into a single JSON payload. The bridge's caller-facing contract (`management_key` in the request body) does **not** change — callers of the bridge already use single-step auth from the outside.

---

## 3. Canonical Auth Reference

### Single-step header (all direct MCP callers)

The only auth credential needed:

```
x-solid-management-key: <value of SOLIDDATA_MANAGEMENT_KEY>
```

This header replaces the `Authorization: Bearer <jwt>` header. No other headers are required for auth.

### What to delete everywhere

| Old artifact | Status | Replace with |
|---|---|---|
| `AUTH_ENDPOINT` env var | Remove | Nothing — header needs no exchange endpoint |
| `auth_endpoint` config field | Remove | Nothing |
| `auth.py` / `get_mcp_token()` function | Remove or retire | Inline header construction |
| `_get_mcp_token()` in `solid_mcp_tool/tool.py` | Remove | Header auth in `HTTPTransport` |
| `Authorization: Bearer ...` header on MCP transport | Remove | `x-solid-management-key: ...` |
| Two-step auth prose in docs | Remove | Single-step header prose |
| "exchange management key for JWT" language | Remove | "pass management key as header" |
| `crewai.auth` / JWT token variable storage | Remove | Not needed |

### Environment variables — new minimal set

```
# Required
SOLIDDATA_MANAGEMENT_KEY=<your-solid-management-key>
MCP_SERVER_URL=https://mcp.production.soliddata.io/mcp   # optional override; default is production
SEMANTIC_LAYER_ID=<uuid>                                  # required for text2sql

# Removed
# AUTH_ENDPOINT=...  <-- DELETE THIS
```

---

## 4. Transport A — Direct MCP (Python / CrewAI / MCP-native)

### 4a. MCPServerHTTP on a CrewAI agent (crew-level wiring)

**Import note:** In `crewai>=1.9.x`, the correct import is:

```python
from crewai.mcp import MCPServerHTTP   # CORRECT
```

The following import fails at runtime with `ImportError`:

```python
from crewai.tools import MCPServerHTTP  # WRONG — do not use
```

Before making changes, check the installed version:

```bash
uv run python -c "import crewai; print(crewai.__version__)"
```

If `crewai>=1.9`, use `from crewai.mcp import MCPServerHTTP`.

**New wiring pattern:**

```python
import os
from crewai.mcp import MCPServerHTTP

mcp_server = MCPServerHTTP(
    url=os.environ.get("MCP_SERVER_URL", "https://mcp.production.soliddata.io/mcp"),
    headers={"x-solid-management-key": os.environ["SOLIDDATA_MANAGEMENT_KEY"]},
    streamable=True,
    cache_tools_list=True,
)
```

Attach to an agent with `mcps=[mcp_server]`. The `mcp_server` object is passed directly; no token variable, no auth call before crew kickoff.

### 4b. MCPClient + HTTPTransport (publishable BaseTool / solid_mcp_tool)

```python
import os
from crewai.mcp import MCPClient
from crewai.mcp.transports.http import HTTPTransport

transport = HTTPTransport(
    url=os.environ.get("MCP_SERVER_URL", "https://mcp.production.soliddata.io/mcp"),
    headers={"x-solid-management-key": os.environ["SOLIDDATA_MANAGEMENT_KEY"]},
    streamable=True,
)
client = MCPClient(transport, connect_timeout=60, execution_timeout=180)
```

Remove the `_get_mcp_token()` call that previously obtained the Bearer token. The `HTTPTransport` `headers` dict carries the management key directly.

### 4c. Raw JSON-RPC (for MCP Inspector or testing)

The MCP endpoint is a stateless JSON-RPC server. A single `tools/call` POST works without a prior `initialize`:

```bash
curl -sS -m 120 \
  -X POST https://mcp.production.soliddata.io/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "x-solid-management-key: ${SOLIDDATA_MANAGEMENT_KEY}" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "text2sql",
      "arguments": {
        "question": "How many accounts are there?",
        "semantic_layer_ids": ["'"${SEMANTIC_LAYER_ID}"'"]
      }
    }
  }'
```

**Important constraints for raw/direct HTTP callers:**

- `Accept: application/json, text/event-stream` is **required**. `Accept: application/json` alone returns HTTP 406.
- The response body is an SSE stream (`Content-Type: text/event-stream`). Parse lines starting with `data:` to find the JSON-RPC result.
- A missing or invalid key returns HTTP 500 (not a clean 401). Treat HTTP 500 as an auth/key failure when `x-solid-management-key` is involved.
- For MCP Inspector, add header `x-solid-management-key: <key>` in the Inspector's custom headers panel. No Bearer token needed.

---

## 5. Transport B — REST/Low-Code Consumers (Bridge)

### Why the bridge is still needed

Workato and Copilot Studio HTTP actions expect a synchronous, complete JSON response. The Solid MCP endpoint only returns `text/event-stream` SSE. These platforms time out or fail to parse an SSE stream. The Azure bridge buffers the full SSE response and returns plain JSON.

**The bridge's external caller-facing API does not change.** Callers continue to POST `management_key` in the request body alongside tool-specific fields. This is already single-step from the caller's perspective.

### What changes inside the bridge (`function_app.py`)

The bridge's **internal** auth path changes: instead of calling `_exchange_management_key_for_token` and forwarding a `Authorization: Bearer <jwt>` to the MCP endpoint, it should forward `x-solid-management-key: <management_key>` directly. The `_call_mcp_tool` function should use the management key header instead of Bearer.

Specifically in `function_app.py`:

1. In `_call_mcp_tool(mcp_url, token, ...)`, the `token` parameter and `Authorization: Bearer {token}` header should be replaced with a `management_key` parameter and `x-solid-management-key: {management_key}` header.
2. `_exchange_management_key_for_token()` can be removed — no longer needed.
3. `_DEFAULT_AUTH_ENDPOINT` constant and `AUTH_ENDPOINT` env var read can be removed.
4. The `_resolve_token` and `_token_from_required_management_key` helpers simplify: extract `management_key` from the request body and pass it directly to the MCP call (no exchange step).
5. The `Authorization: Bearer` fallback path in `_resolve_token` (for callers who pre-exchange their own token) can be removed or retained at your discretion — the canonical path is always `management_key` in the body.

**The `local.settings.json.example`** — remove the `AUTH_ENDPOINT` entry.

### openapi.yaml (bridge spec — caller-facing contract unchanged)

The bridge's OpenAPI spec continues to describe:
- Server: the Azure bridge base URL (not the raw MCP endpoint)
- Auth: `management_key` in the request body on every call

Update only the description text to remove references to "JWT", "Bearer token", and "bridge handles auth exchange". Replace with: "The bridge forwards your management key directly to Solid's MCP server — no token exchange occurs."

Remove the `AUTH_ENDPOINT` from bridge environment variable documentation.

---

## 6. Global Deprecated-Marker Search Checklist

Run these searches in every target repo before and after making changes. Each match is a file that needs updating.

```bash
# Auth exchange endpoint — must be removed everywhere
rg "exchange_user_access_key" --type-list  # check all file types
rg "exchange_user_access_key"

# AUTH_ENDPOINT env var references
rg "AUTH_ENDPOINT"

# JWT/Bearer header on MCP transport
rg "Authorization.*Bearer"
rg "get_mcp_token"
rg "_get_mcp_token"
rg "mcp_token"

# Wrong CrewAI import
rg "from crewai.tools import MCPServerHTTP"

# Old two-step language in docs and comments
rg -i "exchange.*management.key.*jwt"
rg -i "exchange.*management.key.*bearer"
rg -i "exchange.*management.key.*token"
rg -i "two.step.*auth"
rg -i "jwt.*exchange"

# Azure bridge URL hardcoded in code/config
rg "solid-mcp-bridge-efeqgrayfnhvbsf0"

# Hardcoded Azure Function code key (the one in .env.example)
rg "jRC2j18d2ldwBjq"
```

---

## 7. Verification

After making changes, run these two checks:

### 7a. Direct MCP smoke test (curl)

```bash
# From the repo root; requires .env to be sourced or variables set
set -a && . ./.env && set +a

curl -sS -m 120 \
  -X POST "${MCP_SERVER_URL:-https://mcp.production.soliddata.io/mcp}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "x-solid-management-key: ${SOLIDDATA_MANAGEMENT_KEY}" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"text2sql\",\"arguments\":{\"question\":\"how many accounts are there\",\"semantic_layer_ids\":[\"${SEMANTIC_LAYER_ID}\"]}}}"
```

**Expected:** HTTP 200, `Content-Type: text/event-stream`, an SSE `data:` line containing a JSON-RPC result with `"result": {"content": [...]}` and `sql_query` present in the content text. No auth errors.

**Failure indicators:** HTTP 406 means `Accept` header is wrong. HTTP 500 means the key is missing, invalid, or the wrong format.

### 7b. CrewAI MCPClient smoke test (Python)

```python
import asyncio, json, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(".env"))

from crewai.mcp import MCPClient
from crewai.mcp.transports.http import HTTPTransport

async def main():
    transport = HTTPTransport(
        url=os.environ.get("MCP_SERVER_URL", "https://mcp.production.soliddata.io/mcp"),
        headers={"x-solid-management-key": os.environ["SOLIDDATA_MANAGEMENT_KEY"]},
        streamable=True,
    )
    client = MCPClient(transport, connect_timeout=60, execution_timeout=180)
    await client.connect()
    print("Connected OK")
    result = await client.call_tool(
        "text2sql",
        {"question": "how many accounts are there", "semantic_layer_ids": [os.environ["SEMANTIC_LAYER_ID"]]},
    )
    print("Result:", json.dumps(result, indent=2, default=str)[:1000])
    await client.disconnect()

asyncio.run(main())
```

**Expected:** "Connected OK" then a result dict with `sql_query` non-null. No `get_mcp_token` call, no JWT, no Bearer header.

---

## 8. Per-Repo Migration Instructions

---

### Repo: `solid-mcp-poc` (local: `/Users/zackm/Repos/solid-mcp-poc`)

This is the canonical reference implementation. Changes here propagate to downstream copies.

**Files to change:**

#### `src/soliddata_mcp_poc/crew.py`

- In `build_crew(...)`, remove the `mcp_token: str` parameter.
- Change the `MCPServerHTTP` instantiation from:
  ```python
  mcp = MCPServerHTTP(
      url=mcp_server_url,
      headers={"Authorization": f"Bearer {mcp_token}"},
      streamable=True,
      cache_tools_list=True,
  )
  ```
  to:
  ```python
  mcp = MCPServerHTTP(
      url=mcp_server_url,
      headers={"x-solid-management-key": os.environ["SOLIDDATA_MANAGEMENT_KEY"]},
      streamable=True,
      cache_tools_list=True,
  )
  ```
  Add `import os` at the top if not already present. Remove `mcp_token` from all `build_crew` call sites.

#### `src/soliddata_mcp_poc/main.py`

- Remove `from soliddata_mcp_poc.auth import get_mcp_token`.
- Remove the lines:
  ```python
  print("Authenticating with SolidData...")
  token = get_mcp_token()
  print("Authentication successful.\n")
  ```
- Remove `mcp_token=token` from the `build_crew(...)` call.
- Remove the MCP 401 error message that references `AUTH_ENDPOINT` (the catch block in the `try`/`except RuntimeError`). Simplify the error message to not reference `AUTH_ENDPOINT` or auth exchange.

#### `src/soliddata_mcp_poc/auth.py`

- This file can be deleted entirely. It only contains `get_mcp_token()` and the `__main__` block for testing the auth exchange. Both are obsolete.
- If you prefer to keep the file for reference, mark it with a deprecation notice and do not import it.

#### `src/soliddata_mcp_poc/config.py`

- Remove the `auth_endpoint` field:
  ```python
  # DELETE this field:
  auth_endpoint: str = Field(
      default="https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key",
      description="Endpoint to exchange management key for a bearer token.",
      alias="AUTH_ENDPOINT",
  )
  ```

#### `.env.example`

- Remove the `AUTH_ENDPOINT` line and the dev override comment about it.
- Remove the Azure bridge section at the bottom (the entire `# --- Azure REST bridge E2E only ...` block including `BRIDGE_BASE_URL`, `BRIDGE_FUNCTION_KEY`, `BRIDGE_TOOL`, `SEMANTIC_MODEL_ID`, `ASSET_NAME`, `ASSET_TYPE`).

#### `.env`

- Remove the `AUTH_ENDPOINT=...` line if present.
- Remove any `BRIDGE_*` vars if present.

#### `scripts/e2e_openapi_test.py` and `scripts/bridge_openapi.py`

- These scripts test the Azure bridge. They are no longer primary. Add a header comment:
  ```python
  # DEPRECATED: This script tests the Azure bridge (REST adapter for low-code consumers).
  # For direct MCP testing, use the curl command in AGENT_MIGRATION_INSTRUCTIONS.md.
  ```
  Do not delete them — they may still be useful for bridge regression testing.

#### `solid_mcp_tool/tool.py`

- See the `solid_mcp_tool` section below — this file is in this repo but maintained separately.

#### `README.md`

- In the "How It Works" section, replace step 1 ("Auth — `auth.py` exchanges `SOLIDDATA_MANAGEMENT_KEY` for a bearer token") with: "Auth — `crew.py` passes `SOLIDDATA_MANAGEMENT_KEY` directly to the MCP transport via the `x-solid-management-key` header. No token exchange step."
- Remove or retitle the "Testing MCP Connection without Crew" section that instructs users to exchange a token for the MCP Inspector. Replace with: add `x-solid-management-key: <your-key>` as a custom header in the Inspector. No prior Bearer token needed.
- In the environment variables table, remove `AUTH_ENDPOINT`.
- In the "Using the OpenAPI spec" section, keep it but update the description: the bridge spec is for REST/low-code consumers that cannot consume SSE; the bridge itself has been updated to use single-step header auth internally.
- Remove all prose that explains the two-step management-key-to-JWT exchange as something the user or agent must perform.
- Remove references to `auth.py` as a required component of the demo flow.
- The `MODEL=gemini/gemini-2.0-flash` default in `.env.example` should be updated — this model is no longer available in the Gemini API as of Jun 2026. Update to `gemini/gemini-2.0-flash-lite` or `gemini/gemini-1.5-flash` (verify current availability at [ai.google.dev](https://ai.google.dev)). Document this change in the README.

#### `openapi.yaml`

- Keep the file. Update `info.description` to remove "The bridge exchanges the management key for a JWT internally" — replace with: "The bridge forwards your management key directly to Solid's MCP server as a header. No separate auth exchange occurs."
- Keep all paths, request/response schemas, and server URL unchanged.

---

### Repo: `solid_mcp_tool` (part of `solid-mcp-poc`; also vendored and published)

This tool is used by customers. It exists in three places that must stay in sync:
1. `solid_mcp_tool/tool.py` in this repo (`solid-mcp-poc`)
2. `vendor/solid_mcp_tool/` in `zackm-solid/slack-embeddings-demo`
3. The published CrewAI tool (requires re-publish after changes)

**Changes to `solid_mcp_tool/tool.py`:**

#### Remove `_get_mcp_token()`

Delete the entire `_get_mcp_token()` function (lines roughly 25–71). It performs the old management-key-to-JWT exchange.

#### Update `_run_mcp_tool_sync()`

Replace the `_call()` inner async function from:
```python
transport = HTTPTransport(
    url=mcp_url,
    headers={"Authorization": f"Bearer {token}"},
    streamable=True,
)
```
to:
```python
mgmt_key = (os.environ.get("SOLIDDATA_MANAGEMENT_KEY") or "").strip()
if not mgmt_key:
    raise ValueError("SOLIDDATA_MANAGEMENT_KEY is missing or empty.")
transport = HTTPTransport(
    url=mcp_url,
    headers={"x-solid-management-key": mgmt_key},
    streamable=True,
)
```
Remove the `token = _get_mcp_token()` call and the `try/except ValueError` block that handles it.

#### Update `SolidMcpTool.env_vars`

Remove `AUTH_ENDPOINT` from the `env_vars` dict:
```python
env_vars: dict = {
    "SOLIDDATA_MANAGEMENT_KEY": "Required. SolidData Management Key.",
    "SEMANTIC_LAYER_ID": "Optional. Fallback for semantic_layer_id if not passed.",
    # AUTH_ENDPOINT removed — no longer needed
    "MCP_SERVER_URL": "Optional. Solid MCP HTTP URL. Defaults to production.",
}
```

#### Update `SolidGlossarySearchTool.env_vars`

Same — remove `AUTH_ENDPOINT`.

#### Remove constants

Remove `_DEFAULT_AUTH_ENDPOINT` constant at the top of the file.

#### After making changes

1. Bump the version in `pyproject.toml` for the published tool.
2. Run the CrewAI smoke test (section 7b) using this tool's code path.
3. Re-publish to CrewAI tool repository: `crewai tool publish`.
4. Copy the updated `tool.py` to `vendor/solid_mcp_tool/tool.py` in `slack-embeddings-demo` (or coordinate that repo's update separately per its section below).

---

### Repo: `zackm-solid/solid-mcp-bridge`

This is the Azure Functions REST adapter. Its external caller-facing API does not change. Only its internal auth path and documentation change.

**Files to change:**

#### `function_app.py`

The key change: replace the internal `management_key` → JWT exchange with direct header forwarding.

1. **Remove `_DEFAULT_AUTH_ENDPOINT`** constant and the `AUTH_ENDPOINT` env var read.

2. **Remove `_exchange_management_key_for_token()`** function entirely.

3. **Update `_call_mcp_tool()`**: change its signature from `_call_mcp_tool(mcp_url, token, tool_name, arguments)` to `_call_mcp_tool(mcp_url, management_key, tool_name, arguments)`. Replace the `Authorization` header:
   ```python
   # OLD:
   headers = {
       "Authorization": f"Bearer {token}",
       ...
   }
   # NEW:
   headers = {
       "x-solid-management-key": management_key,
       ...
   }
   ```

4. **Simplify `_resolve_token()`**: rename to `_extract_management_key()`. Remove the Bearer fallback path. Only extract `management_key` from the request body:
   ```python
   def _extract_management_key(body: dict) -> tuple[str | None, func.HttpResponse | None]:
       key = (body.get("management_key") or "").strip()
       if not key:
           return None, func.HttpResponse(
               json.dumps({"error": "Body must include 'management_key'."}),
               status_code=401,
               mimetype="application/json",
           )
       return key, None
   ```

5. **Simplify `_token_from_required_management_key()`**: rename to `_extract_required_management_key()` and remove the exchange call — just return the raw key.

6. **Update all tool handler functions**: replace `token, token_error = _resolve_token(body, req)` with `management_key, key_error = _extract_management_key(body)`, and pass `management_key=management_key` (not `token=token`) to `_execute_tool` and then `_call_mcp_tool`.

7. **Remove the MCP `initialize` step** if desired (the Solid MCP server accepts stateless `tools/call` without a prior `initialize`). This simplifies the bridge and removes one round-trip. If keeping `initialize` for compatibility, ensure it also uses `x-solid-management-key` instead of Bearer.

8. Update the module docstring to remove references to "Bearer token" and "management key in body, bridge exchanges it for a Bearer token." Replace with: "Management key is passed as `x-solid-management-key` header directly to Solid MCP. No token exchange step."

#### `README.md`

- Under "Auth (two options)", remove Option 2 (Authorization: Bearer) or mark it as unsupported. Replace with a single auth option: `management_key` in the request body; the bridge forwards it as `x-solid-management-key` to Solid's MCP endpoint.
- Remove references to "Bearer token", "JWT", "token exchange", and "auth exchange".
- Remove `AUTH_ENDPOINT` from the environment variables table.
- Update the architecture diagram text — the inner arrow from bridge to Solid now shows `x-solid-management-key` instead of `Authorization: Bearer`.
- Under "Configuring the flow (Copilot Studio)" — Option B (Flow does auth, bridge gets Bearer) should be removed. Only Option A applies.
- Keep all endpoint documentation, cURL examples, and OpenAPI reference. Only auth description changes.

#### `openapi.yaml`

Same as in `solid-mcp-poc`: update description text only. Remove "JWT", "Bearer token", and "auth exchange" language. The caller-facing request bodies (with `management_key`) and response schemas are unchanged.

#### `local.settings.json.example`

Remove `AUTH_ENDPOINT` from the JSON object if it is present.

---

### Repo: `zackm-solid/solid-mcp-sandbox`

This repo's `sandbox.py` calls the Azure bridge (not direct MCP). From the caller's perspective, it already uses single-step auth (`management_key` in the body). No code changes are required to `sandbox.py` or `mcp_test_script.py`.

**Files to change:**

#### `.env.example`

- Remove the `BRIDGE_FUNCTION_KEY` line and comment if you want to remove bridge-specific vars. **Note:** the bridge still requires this Azure Function host key for authentication; keep it if the sandbox is expected to run against the bridge. Consider whether to keep it as an optional override.
- Remove `AUTH_ENDPOINT` if present (it is not in the current `.env.example`, so verify before touching).

#### `README.md`

- Under "Authentication", update the description. Remove references to "bridge exchanges it for a JWT internally". Replace with: "The bridge forwards your management key directly to Solid's MCP server. No token exchange occurs."
- Optionally add a note in "API Notes" linking to `AGENT_MIGRATION_INSTRUCTIONS.md` in `solid-mcp-poc` as the canonical auth reference.
- Keep all tool documentation, request body examples, and endpoint references unchanged — the bridge's external API has not changed.

---

### Repo: `zackm-solid/slack-embeddings-demo`

This repo vendors `solid_mcp_tool` under `vendor/solid_mcp_tool/`. It uses the tool for optional validation patterns, not in the primary ingestion path.

**Files to change:**

#### `vendor/solid_mcp_tool/tool.py`

Copy the updated `solid_mcp_tool/tool.py` from `solid-mcp-poc` (after that repo's changes are complete) into this path verbatim. This is a direct file copy — do not modify the logic separately.

After copying, verify the file version comment or docstring matches the updated upstream, and check `vendor/README.md` for refresh instructions.

#### `.env.example`

The `AUTH_ENDPOINT` line is currently commented out:
```
# AUTH_ENDPOINT=https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key
```
Delete this commented-out line entirely. It should no longer appear even as an optional override, since it is no longer a valid configuration option.

#### `docs/solid-semantic-model.md`

Search for any references to the two-step auth pattern or `AUTH_ENDPOINT`. If found, update to describe single-step header auth. If the document only describes Solid MCP tool usage (not auth mechanics), no change is needed.

---

### Repo: `zackm-solid/agent-knowledge`

This is the canonical knowledge base. It has the most documentation to update and several files contain explicit two-step auth descriptions that would mislead agents reading them.

**Files to change:**

#### `docs/solid-architecture/SOLID-MCP-INTEGRATION.md`

This file has the most critical changes. The current "Direct MCP" section describes the old two-step flow explicitly.

**Section "1) Direct MCP" — replace entirely:**

Remove:
> Two-step flow: exchange management key → call MCP tool.
> **Step A — exchange management key for Bearer token**
> `POST https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key`
> ...
> **Step B — call Solid MCP with Bearer token**
> Header: `Authorization: Bearer <token>`

Replace with:
> Single-step auth: pass your management key as a request header on every MCP call. No prior exchange required.
>
> **Call Solid MCP directly**
>
> `POST https://mcp.production.soliddata.io/mcp`
> Header: `x-solid-management-key: <your-solid-management-key>`
> Header: `Accept: application/json, text/event-stream`
>
> The endpoint requires both Accept values; `Accept: application/json` alone returns 406.

Update the JSON-RPC `text2sql` and `glossary_search` examples to show `x-solid-management-key` in the header, not Bearer.

**"CrewAI wiring" line — update:**
```python
# OLD:
MCPServerHTTP(url=MCP_SERVER_URL, headers={"Authorization": f"Bearer {token}"}, ...)

# NEW:
MCPServerHTTP(url=MCP_SERVER_URL, headers={"x-solid-management-key": os.environ["SOLIDDATA_MANAGEMENT_KEY"]}, ...)
```
Note the import: `from crewai.mcp import MCPServerHTTP` (not `crewai.tools`).

**Section "2) REST-to-MCP bridge" — update description only:**
- Remove "Include `management_key` in the JSON body on every call. The bridge exchanges it for a JWT internally."
- Replace with: "Include `management_key` in the JSON body on every call. The bridge forwards it as `x-solid-management-key` to Solid's MCP server directly. No JWT exchange occurs."
- Keep the table of routes, all JSON body examples, and response shape docs unchanged.
- Add a note explaining **why** the bridge exists: Solid's MCP endpoint returns SSE (`text/event-stream`). Workato, Copilot Studio, and similar low-code platforms cannot consume SSE natively. The bridge buffers the stream and returns a complete JSON response.

**Remove from "Dev environment" note:** the instruction to "Replace both URLs with `backend.dev.soliddata.io`..." should be updated to only mention `mcp.dev.soliddata.io` (no `backend.dev` since the auth endpoint is gone).

#### `docs/pilot-poc/solid-auth-and-security-runbook.md`

This file defines "Model A" (direct MCP) and "Model B" (bridge) with explicit auth steps.

**Terms table:** Remove the `JWT / Bearer token` row. Add a new row: `x-solid-management-key` — "Request header passed directly to Solid's MCP endpoint. Replaces the JWT Bearer token; no exchange step required."

**Model A — Direct MCP:** Replace the three-step flow with:
> 1. Set the `x-solid-management-key` header to your management key value.
> 2. Call MCP directly with this header. No prior auth exchange.
>
> Do not exchange the key for a JWT. Do not use `Authorization: Bearer`.

Remove `AUTH_ENDPOINT` from the "Default endpoints" list.

**Model B — Azure REST bridge:** Update "Single-step auth" description: "Include `management_key` in the JSON body. The bridge forwards it as a header to Solid's MCP server — no JWT exchange on the bridge." Remove "tokens expire; the bridge handles renewal" since this is no longer the mechanism.

**Common failures table:** Update the "MCP 401 after 'successful' auth" row — this failure mode is eliminated since there is no longer a separate auth exchange step. Remove "Prod/dev mismatch" referring to `AUTH_ENDPOINT`. Add: "`x-solid-management-key` missing or invalid → HTTP 500 from MCP endpoint (not 401). Verify key is present and correct."

**Starter prompt for LLM:** Remove the line about checking `AUTH_ENDPOINT` alignment.

#### `docs/pilot-poc/solid-crewai-direct-mcp-pattern.md`

**Architecture section:** Replace the flow diagram text:
```
management_key  --(HTTPS)-->  auth exchange  -->  Bearer JWT
                                                      |
                                                      v
                                            Solid MCP HTTP (streamable)
```
with:
```
management_key (as x-solid-management-key header)
                    |
                    v
           Solid MCP HTTP (streamable)
```

**Implementation notes:** Remove "Do not send `management_key` inside MCP `tools/call` arguments — exchange first, then Bearer on the transport." Replace with: "Pass `SOLIDDATA_MANAGEMENT_KEY` as `x-solid-management-key` in the transport headers. Do not put the key inside `tools/call` arguments."

**Known risks:** Remove "Dev vs prod mismatch: `AUTH_ENDPOINT` and `MCP_SERVER_URL` must both target the same environment." Replace with: "Use the correct `MCP_SERVER_URL` (prod vs dev). No `AUTH_ENDPOINT` is needed."

**Minimal checklist:** Remove `AUTH_ENDPOINT / MCP_SERVER_URL aligned (prod or dev)` and simplify to just `MCP_SERVER_URL` pointing to the correct environment.

**Purpose/When to use sections:** Remove "Python-based crews ... or any client that can attach an MCP HTTP transport with `Authorization: Bearer <token>`." Replace with: `Authorization: Bearer` → `x-solid-management-key`.

**Starter prompt for LLM:** Update: "exchange management key for JWT, then `MCPServerHTTP` or `MCPClient`/`HTTPTransport`" → "pass `SOLIDDATA_MANAGEMENT_KEY` as `x-solid-management-key` header in `MCPServerHTTP` or `MCPClient`/`HTTPTransport`."

#### `docs/pilot-poc/solid-azure-bridge-rest-pattern.md`

**Architecture diagram:** Replace "body.management_key (bridge exchanges for JWT internally)" with "body.management_key (bridge forwards as x-solid-management-key header)".

**Auth paragraph:** "Include Solid `management_key` in the JSON body. The bridge exchanges it for a short-lived JWT on each request — callers never manage Bearer tokens." → "Include Solid `management_key` in the JSON body. The bridge forwards it directly to Solid's MCP server as `x-solid-management-key`. No token exchange occurs; callers never manage tokens."

**Implementation notes (Copilot Studio):** Remove any reference to "do not perform a separate auth exchange in the flow — the bridge handles JWT renewal." Replace with: "The bridge handles all MCP transport details. Store the management key as a connection secret; the bridge forwards it on every call."

Keep all endpoint, body, and response documentation unchanged.

#### `docs/solid-architecture/solid-mcp-crewai-poc.md`

This file is the CrewAI runbook. It contains multiple references to the two-step auth flow.

**"How It Works" step 1:** "Auth — `auth.py` exchanges `SOLIDDATA_MANAGEMENT_KEY` for a bearer token (SolidData auth API)." → "Auth — `crew.py` passes `SOLIDDATA_MANAGEMENT_KEY` directly as `x-solid-management-key` on the MCP transport. No auth exchange step."

**Architecture note:** "The **SQL Analyst** connects to SolidData's MCP server via **MCPServerHTTP** in `crew.py` (using the token from `auth.py`)" → remove "(using the token from `auth.py`)" — `auth.py` no longer exists.

**MCP Inspector instructions:** Update "Headers: add `Authorization: Bearer <token>`. Get the token by exchanging your `SOLIDDATA_MANAGEMENT_KEY` at the SolidData auth endpoint..." → "Headers: add `x-solid-management-key: <your-soliddata-management-key>`. No token exchange needed."

**Setup step:** Remove `AUTH_ENDPOINT` from the optional env vars mention.

**Required env vars table:** Remove `AUTH_ENDPOINT` row.

**Troubleshooting:** Remove "Auth OK but MCP 401 / connection cancelled — Use the same environment for auth and MCP: both production or both dev." This failure mode no longer applies. Replace with a note about `x-solid-management-key` being invalid (HTTP 500 from MCP endpoint).

**`solid_mcp_tool` tool interface table (`AUTH_ENDPOINT` row):** Remove this row.

#### `README.md` (agent-knowledge repo root)

**"Current documentation posture" section:** The bullet "MCP is the default for all net-new agent/chat integrations. Any host that can speak MCP with a Bearer header should use direct MCP (management-key exchange)." → Update: "Any host that can speak MCP with a `x-solid-management-key` header should use direct MCP (no token exchange required)." Remove "management-key exchange."

Add a bullet noting the auth migration: "As of Jun 2026, direct MCP authentication uses `x-solid-management-key` header only. The two-step management-key-to-JWT exchange is deprecated."

---

### Repo: `solid-demo` (local: `/Users/zackm/Repos/solid-demo`)

This repo contains only `.cursor/solid-sql-mcp/SKILL.md` — a Cursor IDE skill file that routes natural-language questions to Solid MCP. There is no Python auth code in this repo.

**File to check:**

#### `.cursor/solid-sql-mcp/SKILL.md`

This skill file does not contain auth code. The Solid MCP connection is managed by Cursor's MCP server configuration (the `user-solid-mcp` server entry), not by this skill.

**Action:** Verify that the Cursor MCP server configuration for `user-solid-mcp` (in your Cursor settings or `.cursor/mcp.json`) uses `x-solid-management-key` as the header, not `Authorization: Bearer`. If the Cursor MCP configuration supports custom headers, set:
```json
{
  "headers": {
    "x-solid-management-key": "<SOLIDDATA_MANAGEMENT_KEY>"
  }
}
```

The SKILL.md content itself does not reference auth and does not need editing. No auth-related prose appears in the skill.

---

## 9. Per-Repo Instructions: Inaccessible SolidDataDev Repos

> **Note:** The GitHub token available at the time this document was written does not have read access to the `SolidDataDev` organization. The instructions below are pattern-based, derived from each repo's name and known purpose. **Before applying changes, an agent with access must:**
> 1. Read the repo root listing and key files.
> 2. Run the global deprecated-marker searches from section 6.
> 3. Apply the pattern instructions below, adjusted for any files actually found.

---

### Repo: `SolidDataDev/solid-crewai-poc`

**Expected stack:** Python / CrewAI. Likely mirrors or extends the `solid-mcp-poc` pattern.

**Pattern to apply:** Transport A (direct MCP). Follow the same changes as `solid-mcp-poc`:

1. Find any file that creates `MCPServerHTTP` or `MCPClient`/`HTTPTransport` and replaces `Authorization: Bearer {token}` with `x-solid-management-key: {management_key}`.
2. Find any file that calls an auth exchange endpoint (`exchange_user_access_key`) and remove that call.
3. Find any `config.py` or settings file with `AUTH_ENDPOINT` and remove the field.
4. Remove `AUTH_ENDPOINT` from `.env`, `.env.example`, and any `env_vars` dicts on `BaseTool` subclasses.
5. Verify the CrewAI import: `from crewai.mcp import MCPServerHTTP` (not `crewai.tools`).
6. Update README to remove two-step auth description.
7. Run the verification smoke test (section 7a or 7b).

**Specific search targets:**
```bash
rg "exchange_user_access_key"  # Find auth exchange calls
rg "AUTH_ENDPOINT"             # Find env var references
rg "Authorization.*Bearer"     # Find Bearer header on MCP transport
rg "from crewai.tools import MCPServerHTTP"  # Check import path
```

---

### Repo: `SolidDataDev/CoPilot-Studio-POC`

**Expected stack:** REST/low-code integration for Microsoft Copilot Studio. Likely contains Power Automate flow definitions, a custom connector spec, or OpenAPI import files. May reference the Azure bridge.

**Pattern to apply:** Transport B (bridge). The bridge's external API does not change. Update only documentation.

1. Find any OpenAPI or connector spec file. Update description text only: remove "JWT", "Bearer token", "auth exchange" references. The caller-facing body (`management_key` in JSON) and the response schemas are unchanged.
2. Find any README or setup guide that describes an auth exchange step. Remove those steps. Replace with: "Include `management_key` in the request body. No separate auth exchange is required."
3. Find any flow variable or environment setting named `AUTH_ENDPOINT` or pointing to `exchange_user_access_key`. Remove it — the bridge no longer uses this endpoint.
4. If the repo contains a custom connector definition (`.yaml`, `.json`, or Power Platform format), verify that no separate OAuth 2.0 or pre-authorization step is configured for the Solid connection. The only credential should be `management_key` stored as a connector secret.
5. If there is a flow that separately calls the auth exchange endpoint and stores a Bearer token before calling the bridge — remove that entire auth step. The bridge handles transport internally.

**Specific search targets:**
```bash
rg -i "exchange_user_access_key"
rg -i "auth_endpoint"
rg -i "bearer"
rg -i "jwt"
```

---

### Repo: `SolidDataDev/Data-Observability-POC`

**Expected stack:** Unknown — could be Python, Jupyter notebooks, or a mixed stack. The name suggests data quality / observability tooling that may call Solid MCP for metadata queries.

**Pattern to apply:** Inspect the repo first, then apply either Transport A or B:

1. Run the global searches from section 6 to identify which files contain auth patterns.
2. If Python files call `MCPServerHTTP` or `MCPClient`/`HTTPTransport` directly: apply Transport A changes (section 4).
3. If the repo calls the Azure bridge via HTTP POST: apply Transport B changes (documentation only; section 5).
4. If the repo calls the old auth exchange endpoint directly and then uses the JWT for some non-MCP purpose: consult the team — this document covers only the MCP auth migration.
5. Remove `AUTH_ENDPOINT` from all env files, config classes, and documentation regardless of transport type.

**Specific search targets (run first):**
```bash
rg "exchange_user_access_key"  # Scope of auth exchange usage
rg "AUTH_ENDPOINT"
rg "MCPServerHTTP\|MCPClient\|HTTPTransport"  # Python MCP usage
rg "solid-mcp-bridge.*azurewebsites"           # Bridge URL usage
```

Based on results, apply the corresponding section (4a/4b for direct MCP, or documentation-only changes for bridge callers).

---

## 10. Summary Table

| Repo | Transport | Auth change | Code change | Doc change | Priority |
|---|---|---|---|---|---|
| `solid-mcp-poc` | A (direct) | Remove JWT exchange + `auth.py`; header on transport | `crew.py`, `main.py`, `config.py`, `auth.py` (delete), `solid_mcp_tool/tool.py` | `README.md`, `.env.example`, `openapi.yaml` description | High — canonical reference |
| `solid_mcp_tool` (published tool) | A (direct) | Remove `_get_mcp_token`; header on transport | `tool.py` | `README.md`, `env_vars` dict | High — customer-facing |
| `solid-mcp-bridge` | B (bridge internal) | Remove JWT exchange; forward key as header | `function_app.py` | `README.md`, `openapi.yaml` description | High — REST adapter |
| `solid-mcp-sandbox` | B (bridge caller) | No code change | None | `README.md` description only | Medium |
| `slack-embeddings-demo` | A (vendored tool) | Vendor copy update | `vendor/solid_mcp_tool/tool.py` (copy from updated upstream) | `.env.example` (remove commented `AUTH_ENDPOINT`) | Medium |
| `agent-knowledge` | N/A (docs only) | N/A | None | 6 files — extensive doc updates | High — read by agents |
| `solid-demo` | A (Cursor MCP) | Cursor MCP config check only | None | None | Low |
| `SolidDataDev/solid-crewai-poc` | A (direct) | Inspect, then apply Transport A | Likely `crew.py` / auth file | README | High (verify on access) |
| `SolidDataDev/CoPilot-Studio-POC` | B (bridge/connector) | No code change | None | Connector spec / README | Medium (verify on access) |
| `SolidDataDev/Data-Observability-POC` | Unknown | Inspect first | TBD | TBD | Medium (verify on access) |
