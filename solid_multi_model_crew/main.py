#!/usr/bin/env python
"""CLI entry point for multi-model Solid MCP CrewAI demo."""

from __future__ import annotations

import argparse
import sys
import warnings

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

from solid_multi_model_crew.config import (
    apply_mcp_env,
    get_settings,
    load_model_catalog,
    validate_multi_model_catalog,
)
from solid_multi_model_crew.crew import (
    build_multi_model_crew,
    build_router_crew,
    build_router_fallback_crew,
)
from solid_multi_model_crew.router_utils import router_output_indicates_failure


def _kickoff_crew(crew) -> str:
    try:
        result = crew.kickoff()
    except RuntimeError as exc:
        err_msg = str(exc).lower()
        if "mcp" in err_msg and any(
            token in err_msg for token in ("401", "unauthorized", "authentication", "500")
        ):
            raise RuntimeError(
                "MCP server rejected the connection. "
                "Verify SOLIDDATA_MANAGEMENT_KEY is set correctly and has MCP access."
            ) from exc
        raise
    return result.raw if hasattr(result, "raw") else str(result)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Solid MCP multi-model CrewAI demo — router mode and/or per-model aggregation."
        ),
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="Natural-language question (or omit for interactive prompt).",
    )
    parser.add_argument(
        "--mode",
        choices=["router", "multi", "both"],
        default="both",
        help="Query mode: router (single routed call), multi (per-model + aggregate), or both (default).",
    )
    parser.add_argument(
        "--models-config",
        metavar="PATH",
        help="YAML model catalog (overrides MULTI_MODEL_CONFIG env var).",
    )
    parser.add_argument(
        "--no-snowflake",
        action="store_true",
        help="Skip optional Snowflake SQL execution even when credentials are configured.",
    )
    return parser


def run(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    question = " ".join(args.question).strip()
    if not question:
        question = input("Enter your marketing / cross-domain question: ").strip()
    if not question:
        print("No question provided. Exiting.")
        return

    settings = get_settings()
    catalog = load_model_catalog(settings, models_config=args.models_config)
    validate_multi_model_catalog(catalog)
    apply_mcp_env(settings, mode=args.mode)

    print("\n=== Solid Multi-Model MCP Crew ===\n")
    print(f'Question: "{question}"')
    print(f"Mode: {args.mode}")
    print(f"Models ({catalog.domain}): {', '.join(spec.label for spec in catalog.models)}\n")

    router_output: str | None = None
    use_snowflake = settings.use_snowflake() and not args.no_snowflake

    if args.mode in ("router", "both"):
        print("=" * 60)
        print("ROUTER MODE")
        print("=" * 60)
        router_crew = build_router_crew(
            user_question=question,
            catalog=catalog,
            gemini_api_key=settings.gemini_api_key,
            model=settings.model,
        )
        router_output = _kickoff_crew(router_crew)
        if router_output_indicates_failure(router_output):
            print("\n--- Router did not return usable SQL; falling back to semantic_model_qa ---\n")
            fallback_crew = build_router_fallback_crew(
                user_question=question,
                catalog=catalog,
                gemini_api_key=settings.gemini_api_key,
                model=settings.model,
                router_failure_context=router_output,
            )
            fallback_output = _kickoff_crew(fallback_crew)
            router_output = (
                f"{router_output}\n\n"
                f"--- semantic_model_qa fallback ---\n{fallback_output}"
            )
        print(router_output)
        print()

    if args.mode in ("multi", "both"):
        print("=" * 60)
        print("MULTI-MODEL ANALYSIS")
        print("=" * 60)

        multi_crew = build_multi_model_crew(
            user_question=question,
            catalog=catalog,
            gemini_api_key=settings.gemini_api_key,
            model=settings.model,
            router_context=router_output if args.mode == "both" else None,
            use_snowflake=use_snowflake,
            snowflake_account=settings.snowflake_account,
            snowflake_user=settings.snowflake_user,
            snowflake_password=settings.snowflake_password,
            snowflake_database=settings.snowflake_database,
            snowflake_schema=settings.snowflake_schema,
            snowflake_warehouse=settings.snowflake_warehouse,
            snowflake_role=settings.snowflake_role,
        )
        multi_output = _kickoff_crew(multi_crew)
        print(multi_output)
        print()

    print("=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    run(sys.argv[1:])
