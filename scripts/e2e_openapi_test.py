#!/usr/bin/env python3
"""
Validate the OpenAPI contract via a single REST call (what Workato would do).

One POST per bridge operation with management_key and tool fields in the body.
No separate auth step and no Bearer header—the bridge exchanges the key for a JWT.
No CrewAI or MCP client.

Usage:
  python scripts/e2e_openapi_test.py
  BRIDGE_TOOL=glossary_search python scripts/e2e_openapi_test.py
  BRIDGE_TOOL=semantic_model_qa SEMANTIC_MODEL_ID=<uuid> python scripts/e2e_openapi_test.py

Environment (see .env.example):
  SOLIDDATA_MANAGEMENT_KEY  — required
  BRIDGE_TOOL               — text2sql (default), glossary_search,
                              specific_asset_information_tool, semantic_model_qa
  BRIDGE_BASE_URL           — optional; defaults to servers.url in openapi.yaml
  BRIDGE_FUNCTION_KEY       — optional; defaults to parameters.code in openapi.yaml
  SEMANTIC_LAYER_ID         — for text2sql
  SEMANTIC_MODEL_ID         — for semantic_model_qa
  E2E_TIMEOUT, E2E_RETRY_ATTEMPTS — retries for cold starts / 503
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

import httpx

try:
    from dotenv import load_dotenv

    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if _root not in sys.path:
    sys.path.insert(0, _root)

from scripts.bridge_openapi import (  # noqa: E402
    append_bridge_code,
    resolve_bridge_base_url,
    resolve_bridge_function_key,
    url_without_query,
)

DEFAULT_SEMANTIC_LAYER_ID = "998b655a-75eb-4873-bb1e-3ddd23164065"
DEFAULT_SEMANTIC_MODEL_ID = "00000000-0000-0000-0000-000000000000"
DEFAULT_ASSET_NAME = "SUN_SPECTRA.PUBLIC.ORDERS"

BRIDGE_TOOLS: dict[str, dict[str, Any]] = {
    "text2sql": {
        "path": "/text2sql",
        "success_field": "message",
        "default_question": "How much revenue was generated in 2024 by product category?",
    },
    "glossary_search": {
        "path": "/glossary_search",
        "success_field": "result",
        "default_question": "What does LLS mean?",
    },
    "specific_asset_information_tool": {
        "path": "/specific_asset_information_tool",
        "success_field": "result",
        "default_question": "What column includes information about when an order was delivered?",
    },
    "semantic_model_qa": {
        "path": "/semantic_model_qa",
        "success_field": "result",
        "default_question": "What does this model cover?",
    },
}

TIMEOUT = float(os.environ.get("E2E_TIMEOUT", "120"))
E2E_RETRY_ATTEMPTS = int(os.environ.get("E2E_RETRY_ATTEMPTS", "3"))
E2E_RETRY_BACKOFF = [5, 15, 30]


def _build_payload(tool: str, management_key: str, question: str) -> dict[str, Any]:
    if tool == "text2sql":
        layer_id = (os.environ.get("SEMANTIC_LAYER_ID") or DEFAULT_SEMANTIC_LAYER_ID).strip()
        return {
            "management_key": management_key,
            "question": question,
            "semantic_layer_ids": [layer_id],
        }
    if tool == "glossary_search":
        return {"management_key": management_key, "query": question}
    if tool == "specific_asset_information_tool":
        asset_name = (os.environ.get("ASSET_NAME") or DEFAULT_ASSET_NAME).strip()
        payload: dict[str, Any] = {
            "management_key": management_key,
            "question": question,
            "asset_name": asset_name,
        }
        asset_type = (os.environ.get("ASSET_TYPE") or "").strip()
        if asset_type:
            payload["asset_type"] = asset_type
        return payload
    if tool == "semantic_model_qa":
        model_id = (os.environ.get("SEMANTIC_MODEL_ID") or DEFAULT_SEMANTIC_MODEL_ID).strip()
        return {
            "management_key": management_key,
            "semantic_model_id": model_id,
            "question": question,
        }
    raise ValueError(f"Unknown BRIDGE_TOOL: {tool}")


def _bridge_url(tool: str) -> str:
    base = resolve_bridge_base_url()
    path = BRIDGE_TOOLS[tool]["path"]
    function_key = resolve_bridge_function_key()
    return append_bridge_code(f"{base}{path}", function_key)


def _post_with_retries(client: httpx.Client, url: str, payload: dict[str, Any]) -> httpx.Response | None:
    headers = {"Content-Type": "application/json"}
    resp: httpx.Response | None = None
    for attempt in range(E2E_RETRY_ATTEMPTS):
        try:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code != 503:
                return resp
            if attempt < E2E_RETRY_ATTEMPTS - 1:
                delay = E2E_RETRY_BACKOFF[min(attempt, len(E2E_RETRY_BACKOFF) - 1)]
                print(f"{url_without_query(url)} returned 503, retrying in {delay}s...", file=sys.stderr)
                time.sleep(delay)
        except httpx.ReadTimeout:
            if attempt < E2E_RETRY_ATTEMPTS - 1:
                delay = E2E_RETRY_BACKOFF[min(attempt, len(E2E_RETRY_BACKOFF) - 1)]
                print(f"Request timed out, retrying in {delay}s...", file=sys.stderr)
                time.sleep(delay)
            else:
                print(
                    f"Request timed out after {E2E_RETRY_ATTEMPTS} attempts ({TIMEOUT}s each). "
                    "Try E2E_TIMEOUT=180 or E2E_RETRY_ATTEMPTS=5.",
                    file=sys.stderr,
                )
                return None
    return resp


def main() -> int:
    tool = (os.environ.get("BRIDGE_TOOL") or "text2sql").strip()
    if tool not in BRIDGE_TOOLS:
        print(
            f"Error: BRIDGE_TOOL must be one of: {', '.join(BRIDGE_TOOLS)}",
            file=sys.stderr,
        )
        return 1

    key = (os.environ.get("SOLIDDATA_MANAGEMENT_KEY") or "").strip()
    if not key or "your-" in key.lower() or "here" in key.lower():
        print("Error: Set SOLIDDATA_MANAGEMENT_KEY in the environment (see .env.example).", file=sys.stderr)
        return 1

    meta = BRIDGE_TOOLS[tool]
    default_question = meta["default_question"]
    success_field = meta["success_field"]

    try:
        q_in = input(f"Question/query [{default_question}]: ").strip()
        question = q_in if q_in else default_question
    except EOFError:
        question = default_question

    if tool == "text2sql":
        try:
            default_layer = (os.environ.get("SEMANTIC_LAYER_ID") or DEFAULT_SEMANTIC_LAYER_ID).strip()
            ids_in = input(f"Semantic layer ID(s), comma-separated [{default_layer}]: ").strip()
            if ids_in:
                layer_ids = [x.strip() for x in ids_in.split(",") if x.strip()]
            else:
                layer_ids = [default_layer]
        except EOFError:
            layer_ids = [(os.environ.get("SEMANTIC_LAYER_ID") or DEFAULT_SEMANTIC_LAYER_ID).strip()]
        payload = {
            "management_key": key,
            "question": question,
            "semantic_layer_ids": layer_ids,
        }
    else:
        payload = _build_payload(tool, key, question)

    url = _bridge_url(tool)
    print(f"Calling {tool} (single-call): {url_without_query(url)}")
    print(f"Payload keys: {list(payload.keys())}")

    with httpx.Client(timeout=TIMEOUT) as client:
        resp = _post_with_retries(client, url, payload)

    if resp is None:
        return 1
    if resp.status_code != 200:
        body = resp.text or resp.content.decode(errors="replace")
        if resp.status_code == 404:
            print("404 — check BRIDGE_BASE_URL and that the bridge is deployed.", file=sys.stderr)
        elif resp.status_code == 401:
            print(
                "401 — check SOLIDDATA_MANAGEMENT_KEY or BRIDGE_FUNCTION_KEY "
                "(host key; must match openapi.yaml).",
                file=sys.stderr,
            )
        else:
            print(f"{tool} failed: {resp.status_code} {body}", file=sys.stderr)
        return 1

    try:
        body = resp.json()
    except Exception:
        print("Response was not valid JSON.", file=sys.stderr)
        return 1

    if success_field not in body:
        print(f"Response missing '{success_field}' field.", file=sys.stderr)
        return 1

    print(f"OK: Single-call {tool} (OpenAPI contract) succeeded.")
    print(f"Response {success_field}:", body.get(success_field))
    return 0


if __name__ == "__main__":
    sys.exit(main())
