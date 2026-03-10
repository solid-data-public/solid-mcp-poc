#!/usr/bin/env python3
"""
Validate the OpenAPI contract via a single REST call (what Workato would do).

This script makes the same HTTP call a Workato custom connector would: one POST
to the bridge /text2sql endpoint with management_key, question, and
semantic_layer_ids in the body. No separate auth step—the bridge exchanges the
management key for a JWT internally. No CrewAI or MCP client.

Usage:
  # From .env (script loads .env from repo root when python-dotenv is available):
  python scripts/e2e_openapi_test.py

  # Interactive: you are prompted for question and semantic_layer_ids (comma-separated UUIDs).
  # Press Enter to use defaults: question = "How much revenue was generated in 2024 by product category?"
  # and semantic_layer_ids = [SEMANTIC_LAYER_ID] or the built-in default.

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

DEFAULT_SEMANTIC_LAYER_ID = "998b655a-75eb-4873-bb1e-3ddd23164065"
# text2sql via bridge can be slow (bridge → Solid MCP → response). Override with E2E_TIMEOUT (seconds).
TIMEOUT = float(os.environ.get("E2E_TIMEOUT", "120"))

# Default: Azure bridge (single-call; management_key in body). Override with TEXT2SQL_URL for local/CI.
BRIDGE_BASE_URL = "https://solid-mcp-bridge-efeqgrayfnhvbsf0.eastus2-01.azurewebsites.net/api/mcp/text2sql"

TEXT2SQL_URL = os.environ.get("TEXT2SQL_URL", "").strip() or BRIDGE_BASE_URL
# When testing with function-level auth, set BRIDGE_FUNCTION_KEY (do not commit)
BRIDGE_FUNCTION_KEY = os.environ.get("BRIDGE_FUNCTION_KEY", "").strip()

# Retries for text2sql (Flex Consumption can return 503 / timeout while instances recycle)
E2E_RETRY_ATTEMPTS = int(os.environ.get("E2E_RETRY_ATTEMPTS", "3"))
E2E_RETRY_BACKOFF = [5, 15, 30]  # seconds before retries 1, 2, 3


def main() -> int:
    key = (os.environ.get("SOLIDDATA_MANAGEMENT_KEY") or "").strip()
    if not key or "your-" in key.lower() or "here" in key.lower():
        print("Error: Set SOLIDDATA_MANAGEMENT_KEY in the environment (see .env.example).", file=sys.stderr)
        return 1

    default_layer_id = (os.environ.get("SEMANTIC_LAYER_ID") or DEFAULT_SEMANTIC_LAYER_ID).strip()
    default_question = "How much revenue was generated in 2024 by product category?"

    # Prompt for question and semantic_layer_ids (Enter = use defaults)
    try:
        q_in = input(f"Question [{default_question}]: ").strip()
        question = q_in if q_in else default_question
        ids_in = input(f"Semantic layer ID(s), comma-separated [{default_layer_id}]: ").strip()
        if ids_in:
            semantic_layer_ids = [x.strip() for x in ids_in.split(",") if x.strip()]
        else:
            semantic_layer_ids = [default_layer_id]
    except EOFError:
        question = default_question
        semantic_layer_ids = [default_layer_id]

    print(f"Calling text2sql (single-call): question={question!r}, semantic_layer_ids={semantic_layer_ids}")

    # Single POST to bridge: management_key + question + semantic_layer_ids in body (no Bearer header)
    url = TEXT2SQL_URL
    if BRIDGE_FUNCTION_KEY:
        url = f"{url}{'&' if '?' in url else '?'}code={BRIDGE_FUNCTION_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "management_key": key,
        "question": question,
        "semantic_layer_ids": semantic_layer_ids,
    }

    with httpx.Client(timeout=TIMEOUT) as client:
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
                    "text2sql returned 404. Check TEXT2SQL_URL and that the bridge is deployed.",
                    file=sys.stderr,
                )
            elif resp.status_code == 401:
                print(
                    "text2sql returned 401. Check SOLIDDATA_MANAGEMENT_KEY (missing, invalid, or expired).",
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

    print("OK: Single-call text2sql (OpenAPI contract) succeeded.")
    print("Response message:", body.get("message", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
