#!/usr/bin/env python
"""Entry point — authenticate with SolidData, then run the MCP crew."""

import sys
import warnings

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

from soliddata_mcp_poc.auth import get_mcp_token
from soliddata_mcp_poc.config import get_settings
from soliddata_mcp_poc.crew import build_crew


def run() -> None:
    """Authenticate, build the crew, and kick it off."""
    settings = get_settings()

    # 1. Authenticate with SolidData to get an MCP bearer token
    print("\n=== SolidData MCP POC ===\n")
    print("Authenticating with SolidData...")
    token = get_mcp_token()
    print("Authentication successful.\n")

    # 2. Get the user's question (CLI arg or interactive prompt)
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = input("Enter your data question: ").strip()

    if not question:
        print("No question provided. Exiting.")
        return

    print(f'\nQuestion: "{question}"\n')
    print("Starting crew...\n")

    # 3. Build and run the crew
    crew = build_crew(
        mcp_token=token,
        mcp_server_url=settings.mcp_server_url,
        user_question=question,
        gemini_api_key=settings.gemini_api_key,
        semantic_layer_id=settings.semantic_layer_id,
        model=settings.model,
    )
    try:
        result = crew.kickoff()
    except RuntimeError as e:
        err_msg = str(e).lower()
        if "mcp" in err_msg and ("401" in err_msg or "unauthorized" in err_msg or "cancelled" in err_msg or "authentication" in err_msg):
            raise RuntimeError(
                "MCP server rejected the connection (often 401 Unauthorized). "
                "Auth succeeded but the token was not accepted by the MCP server. "
                "Ensure AUTH_ENDPOINT and MCP_SERVER_URL in .env both point to the same environment "
                "(e.g. both production). Confirm with SolidData that your management key has MCP access."
            ) from e
        raise

    # 4. Print results
    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(result.raw if hasattr(result, "raw") else result)
    print()


if __name__ == "__main__":
    run()
