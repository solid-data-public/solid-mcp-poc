#!/usr/bin/env python
"""Entry point — run the MCP crew."""

import sys
import warnings

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

from soliddata_mcp_poc.config import get_settings
from soliddata_mcp_poc.crew import build_crew


def run() -> None:
    """Build the crew and kick it off."""
    settings = get_settings()

    print("\n=== SolidData MCP POC ===\n")

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = input("Enter your data question: ").strip()

    if not question:
        print("No question provided. Exiting.")
        return

    print(f'\nQuestion: "{question}"\n')
    print("Starting crew...\n")

    crew = build_crew(
        mcp_server_url=settings.mcp_server_url,
        user_question=question,
        gemini_api_key=settings.gemini_api_key,
        semantic_layer_id=settings.semantic_layer_id,
        model=settings.model,
        snowflake_account=settings.snowflake_account,
        snowflake_user=settings.snowflake_user,
        snowflake_password=settings.snowflake_password,
        snowflake_database=settings.snowflake_database,
        snowflake_schema=settings.snowflake_schema,
        snowflake_warehouse=settings.snowflake_warehouse,
        snowflake_role=settings.snowflake_role,
    )
    try:
        result = crew.kickoff()
    except RuntimeError as e:
        err_msg = str(e).lower()
        if "mcp" in err_msg and ("401" in err_msg or "unauthorized" in err_msg or "cancelled" in err_msg or "authentication" in err_msg or "500" in err_msg):
            raise RuntimeError(
                "MCP server rejected the connection. "
                "Verify SOLIDDATA_MANAGEMENT_KEY is set correctly and has MCP access. "
                "A missing or invalid key often returns HTTP 500 from the MCP endpoint."
            ) from e
        raise

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(result.raw if hasattr(result, "raw") else result)
    print()


if __name__ == "__main__":
    run()
