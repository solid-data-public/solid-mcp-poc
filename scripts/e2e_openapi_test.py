#!/usr/bin/env python3
"""
Validate the OpenAPI contract only via REST (what Workato would do).

This script makes the same HTTP calls a Workato custom connector would: (1) POST
to the auth endpoint to get a token, (2) POST to the text2sql endpoint with
Bearer token and JSON body. No CrewAI or MCP client. If text2sql returns 404,
the backend may not expose that REST endpoint yet; the OpenAPI spec is still
correct for when it does (or for a REST-to-MCP bridge).

Usage:
  # From .env (script loads .env from repo root when python-dotenv is available):
  python scripts/e2e_openapi_test.py

  # Or export:
  export SOLIDDATA_MANAGEMENT_KEY=<your-key>
  export SEMANTIC_LAYER_ID=<uuid>   # optional; defaults below
  # To test the Azure REST-to-MCP bridge, set BRIDGE_FUNCTION_KEY (and optionally TEXT2SQL_URL).
  # If only BRIDGE_FUNCTION_KEY is set, the script uses the deployed bridge URL automatically.
  python scripts/e2e_openapi_test.py
"""

import os
import sys
import time

import httpx

# Load .env from repo root so BRIDGE_FUNCTION_KEY / TEXT2SQL_URL from .env are used
try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass

AUTH_URL = "https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key"
DEFAULT_SEMANTIC_LAYER_ID = "998b655a-75eb-4873-bb1e-3ddd23164065"
# text2sql via bridge can be slow (bridge → Solid MCP → response). Override with E2E_TIMEOUT (seconds).
TIMEOUT = float(os.environ.get("E2E_TIMEOUT", "120"))

# Default text2sql URL (Solid MCP server — returns 404 for REST; use bridge for Workato)
DEFAULT_TEXT2SQL_URL = "https://mcp.production.soliddata.io/mcp/text2sql"
# Deployed Azure bridge (use when BRIDGE_FUNCTION_KEY is set or TEXT2SQL_URL points here)
BRIDGE_BASE_URL = "https://solid-mcp-bridge-efeqgrayfnhvbsf0.eastus2-01.azurewebsites.net/api/mcp/text2sql"

TEXT2SQL_URL = os.environ.get("TEXT2SQL_URL", "").strip() or DEFAULT_TEXT2SQL_URL
# When testing the deployed bridge with function-level auth, set BRIDGE_FUNCTION_KEY (do not commit)
BRIDGE_FUNCTION_KEY = os.environ.get("BRIDGE_FUNCTION_KEY", "").strip()

# If key is set but URL is still Solid's default, use the bridge URL so the request hits Azure
if BRIDGE_FUNCTION_KEY and TEXT2SQL_URL == DEFAULT_TEXT2SQL_URL:
    TEXT2SQL_URL = BRIDGE_BASE_URL

# Retries for text2sql (Flex Consumption can return 503 / timeout while instances recycle)
E2E_RETRY_ATTEMPTS = int(os.environ.get("E2E_RETRY_ATTEMPTS", "3"))
E2E_RETRY_BACKOFF = [5, 15, 30]  # seconds before retries 1, 2, 3


def main() -> int:
    key = (os.environ.get("SOLIDDATA_MANAGEMENT_KEY") or "").strip()
    if not key or "your-" in key.lower() or "here" in key.lower():
        print("Error: Set SOLIDDATA_MANAGEMENT_KEY in the environment (see .env.example).", file=sys.stderr)
        return 1

    layer_id = (os.environ.get("SEMANTIC_LAYER_ID") or DEFAULT_SEMANTIC_LAYER_ID).strip()
    question = "How much revenue was generated in 2024 by product category?"

    with httpx.Client(timeout=TIMEOUT) as client:
        # 1. Auth exchange (as per OpenAPI: POST auth URL with management_key)
        resp = client.post(
            AUTH_URL,
            json={"management_key": key},
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code != 200:
            print(f"Auth failed: {resp.status_code} {resp.text}", file=sys.stderr)
            return 1
        data = resp.json()
        if isinstance(data, str):
            token = data.strip()
        elif isinstance(data, dict):
            raw = data.get("token") or data.get("access_token") or data.get("accessToken")
            token = (raw.strip() if isinstance(raw, str) else "") or ""
        else:
            print("Auth response was not a string or JSON object.", file=sys.stderr)
            return 1
        if not token:
            print("Auth response missing token/access_token.", file=sys.stderr)
            return 1
        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        # 2. text2sql (as per OpenAPI: POST text2sql URL with Bearer + JSON body)
        # Retry on 503 or ReadTimeout (Flex Consumption can recycle instances mid-request)
        url = TEXT2SQL_URL
        if BRIDGE_FUNCTION_KEY:
            url = f"{url}{'&' if '?' in url else '?'}code={BRIDGE_FUNCTION_KEY}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {"question": question, "semantic_layer_ids": [layer_id]}
        resp = None
        for attempt in range(E2E_RETRY_ATTEMPTS):
            try:
                resp = client.post(url, json=payload, headers=headers)
                if resp.status_code != 503:
                    break
                if attempt < E2E_RETRY_ATTEMPTS - 1:
                    delay = E2E_RETRY_BACKOFF[min(attempt, len(E2E_RETRY_BACKOFF) - 1)]
                    print(f"text2sql returned 503 (service unavailable), retrying in {delay}s...", file=sys.stderr)
                    time.sleep(delay)
            except httpx.ReadTimeout:
                if attempt < E2E_RETRY_ATTEMPTS - 1:
                    delay = E2E_RETRY_BACKOFF[min(attempt, len(E2E_RETRY_BACKOFF) - 1)]
                    print(f"text2sql timed out, retrying in {delay}s...", file=sys.stderr)
                    time.sleep(delay)
                else:
                    print(
                        f"text2sql request timed out after {E2E_RETRY_ATTEMPTS} attempts ({TIMEOUT}s each). "
                        "Flex Consumption may be cold-starting; try E2E_TIMEOUT=180 or E2E_RETRY_ATTEMPTS=5.",
                        file=sys.stderr,
                    )
                    return 1
        if resp is None:
            return 1
        if resp.status_code != 200:
            body = resp.text or resp.content.decode(errors="replace")
            if resp.status_code == 404:
                print(
                    "text2sql returned 404. The OpenAPI spec describes a REST endpoint at "
                    "https://mcp.production.soliddata.io/mcp/text2sql. If Solid's server only "
                    "exposes the MCP protocol (no REST), a REST-to-MCP bridge is required for Workato.",
                    file=sys.stderr,
                )
            else:
                print(f"text2sql failed: {resp.status_code} {body}", file=sys.stderr)
                if resp.status_code == 500 and not body.strip():
                    print("(Empty body — check Azure Function logs: Portal → Function App → Log stream / Monitor)", file=sys.stderr)
            return 1
        try:
            body = resp.json()
        except Exception:
            print("text2sql response was not valid JSON.", file=sys.stderr)
            return 1
        if "message" not in body:
            print("text2sql response missing 'message' field.", file=sys.stderr)
            return 1

    print("OK: Auth and text2sql (REST) succeeded; OpenAPI contract validated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
