#!/usr/bin/env python3
"""
Validate the OpenAPI contract only via REST (what Workato would do).

This script makes the same HTTP calls a Workato custom connector would: (1) POST
to the auth endpoint to get a token, (2) POST to the text2sql endpoint with
Bearer token and JSON body. No CrewAI or MCP client. If text2sql returns 404,
the backend may not expose that REST endpoint yet; the OpenAPI spec is still
correct for when it does (or for a REST-to-MCP bridge).

Usage:
  export SOLIDDATA_MANAGEMENT_KEY=<your-key>
  export SEMANTIC_LAYER_ID=<uuid>   # optional; defaults below
  python scripts/e2e_openapi_test.py
"""

import os
import sys

import httpx

AUTH_URL = "https://backend.production.soliddata.io/api/v1/auth/exchange_user_access_key"
TEXT2SQL_URL = "https://mcp.production.soliddata.io/mcp/text2sql"
DEFAULT_SEMANTIC_LAYER_ID = "998b655a-75eb-4873-bb1e-3ddd23164065"
TIMEOUT = 30.0


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
        resp = client.post(
            TEXT2SQL_URL,
            json={
                "question": question,
                "semantic_layer_ids": [layer_id],
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        if resp.status_code != 200:
            if resp.status_code == 404:
                print(
                    "text2sql returned 404. The OpenAPI spec describes a REST endpoint at "
                    "https://mcp.production.soliddata.io/mcp/text2sql. If Solid's server only "
                    "exposes the MCP protocol (no REST), a REST-to-MCP bridge is required for Workato.",
                    file=sys.stderr,
                )
            else:
                print(f"text2sql failed: {resp.status_code} {resp.text}", file=sys.stderr)
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
