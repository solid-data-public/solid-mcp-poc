"""CrewAI crews for Solid MCP multi-model router and per-model aggregation."""

from __future__ import annotations

from typing import Optional

from crewai import Agent, Crew, LLM, Process, Task

from solid_multi_model_crew.models import ModelCatalog, QueryPlan
from solid_multi_model_crew.tools import (
    COVERAGE_QUESTION_TEMPLATE,
    build_catalog_tools,
    format_tool_names,
)


def _build_llm(*, gemini_api_key: str, model: str, temperature: float = 0.3) -> LLM:
    return LLM(
        model=model,
        api_key=gemini_api_key,
        temperature=temperature,
        max_tokens=8192,
    )


def _format_catalog(catalog: ModelCatalog) -> str:
    lines = [f"Domain: {catalog.domain}", "Models:"]
    for spec in catalog.models:
        lines.append(
            f"- name={spec.name!r}, id={spec.id}, label={spec.label!r}, "
            f"description={spec.description!r}"
        )
    return "\n".join(lines)


def build_router_crew(
    user_question: str,
    catalog: ModelCatalog,
    *,
    gemini_api_key: str,
    model: str = "gemini/gemini-2.0-flash-lite",
) -> Crew:
    """Single-agent crew: router text2sql; may use semantic_model_qa if result is unclear."""
    qa_tools, text2sql_tools, router_tools = build_catalog_tools(catalog)
    llm = _build_llm(gemini_api_key=gemini_api_key, model=model)
    coverage_q = COVERAGE_QUESTION_TEMPLATE.format(question=user_question)
    qa_tool_names = format_tool_names(qa_tools)
    text2sql_tool_names = format_tool_names(text2sql_tools)

    analyst = Agent(
        role="Solid Router SQL Analyst",
        goal=(
            "Answer the user's question via text2sql. Prefer router mode first; use "
            "semantic_model_qa only when the router result is missing, errored, or ambiguous."
        ),
        backstory=(
            "You demonstrate Solid MCP router mode. Primary tool is solid_router_text2sql. "
            "If router output lacks SQL or reports an error, call solid_semantic_model_qa__* "
            "on candidate models, pick the best fit, then call solid_model_text2sql__* for that model."
        ),
        llm=llm,
        tools=[*router_tools, *qa_tools, *text2sql_tools],
        verbose=True,
    )

    router_task = Task(
        description=(
            f'User question:\n\n"{user_question}"\n\n'
            f"Configured semantic layers:\n{_format_catalog(catalog)}\n\n"
            "Steps:\n"
            "1. Call **solid_router_text2sql** once with the user's full question.\n"
            "2. If the result includes SQL and a clear explanation, report SQL, "
            "semantic_layer_id (if present), and explanation — done.\n"
            "3. If the router returns an error, no SQL, or you cannot tell which model was used:\n"
            f"   a. Call {qa_tool_names} with this coverage question for each candidate model:\n"
            f'      "{coverage_q}"\n'
            f"   b. Pick the best-matching model and call the matching tool from "
            f"{text2sql_tool_names} with the user's question.\n"
            "4. Never invent SQL — only report MCP tool output."
        ),
        expected_output=(
            "SQL from text2sql, which semantic model was used (router or QA-selected), "
            "and a brief explanation. Note if semantic_model_qa was used for model selection."
        ),
        agent=analyst,
    )

    return Crew(agents=[analyst], tasks=[router_task], process=Process.sequential, verbose=True)


def build_router_fallback_crew(
    user_question: str,
    catalog: ModelCatalog,
    *,
    gemini_api_key: str,
    model: str = "gemini/gemini-2.0-flash-lite",
    router_failure_context: str = "",
) -> Crew:
    """Fallback when router mode failed: semantic_model_qa discovery then targeted text2sql."""
    qa_tools, text2sql_tools, _ = build_catalog_tools(catalog)
    llm = _build_llm(gemini_api_key=gemini_api_key, model=model, temperature=0.2)
    coverage_q = COVERAGE_QUESTION_TEMPLATE.format(question=user_question)
    failure_block = ""
    if router_failure_context.strip():
        failure_block = f"\nRouter attempt output (failed):\n{router_failure_context}\n"

    analyst = Agent(
        role="Semantic Model Discovery Analyst",
        goal=(
            "Select the best semantic model using semantic_model_qa, then generate SQL "
            "via the matching per-model text2sql tool."
        ),
        backstory=(
            "Router mode did not produce SQL. You discover model fit using "
            "solid_semantic_model_qa__* before calling solid_model_text2sql__*. "
            "You never guess schema or SQL."
        ),
        llm=llm,
        tools=[*qa_tools, *text2sql_tools],
        verbose=True,
    )

    fallback_task = Task(
        description=(
            f'User question:\n\n"{user_question}"\n\n'
            f"{failure_block}"
            f"Model catalog:\n{_format_catalog(catalog)}\n\n"
            "Router mode failed or returned no SQL. Recover using semantic_model_qa:\n"
            "1. For each relevant model, call solid_semantic_model_qa__<name> with:\n"
            f'   "{coverage_q}"\n'
            "2. Compare coverage answers and pick the best model(s).\n"
            "3. Call solid_model_text2sql__<name> with the user's question for each selected model.\n"
            "4. Return SQL, model label/ID, explanation, and which QA answers drove your choice."
        ),
        expected_output=(
            "Selected model(s), semantic_model_qa summaries, SQL from text2sql, and explanation."
        ),
        agent=analyst,
    )

    return Crew(agents=[analyst], tasks=[fallback_task], process=Process.sequential, verbose=True)


def build_multi_model_crew(
    user_question: str,
    catalog: ModelCatalog,
    *,
    gemini_api_key: str,
    model: str = "gemini/gemini-2.0-flash-lite",
    router_context: Optional[str] = None,
    use_snowflake: bool = False,
    snowflake_account: Optional[str] = None,
    snowflake_user: Optional[str] = None,
    snowflake_password: Optional[str] = None,
    snowflake_database: Optional[str] = None,
    snowflake_schema: Optional[str] = None,
    snowflake_warehouse: Optional[str] = None,
    snowflake_role: Optional[str] = None,
) -> Crew:
    """Three-agent crew: plan sub-questions, query each model, aggregate cross-model analysis."""
    llm = _build_llm(gemini_api_key=gemini_api_key, model=model)
    planner_llm = _build_llm(gemini_api_key=gemini_api_key, model=model, temperature=0.2)

    qa_tools, model_tools, _ = build_catalog_tools(catalog)
    tool_list = format_tool_names(model_tools)
    qa_tool_list = format_tool_names(qa_tools)
    coverage_q = COVERAGE_QUESTION_TEMPLATE.format(question=user_question)

    planner = Agent(
        role="Marketing Query Planner",
        goal=(
            "Decompose cross-domain marketing questions into targeted sub-questions "
            "for each relevant semantic model. Use semantic_model_qa when model fit is unclear."
        ),
        backstory=(
            "You understand marketing analytics domains. When catalog descriptions are not "
            "enough to assign a sub-question, you call solid_semantic_model_qa__* to verify "
            "coverage before planning. You never invent metrics or SQL."
        ),
        llm=planner_llm,
        tools=qa_tools,
        verbose=True,
    )

    specialist = Agent(
        role="Model Query Specialist",
        goal=(
            "Execute each planned sub-question by calling the matching per-model text2sql tool."
        ),
        backstory=(
            "You call exactly one text2sql tool per sub-question (solid_model_text2sql__*). "
            "If text2sql fails for a model, you may call solid_semantic_model_qa__* to refine "
            "the sub-question once, then retry text2sql. Return full MCP output for each call."
        ),
        llm=llm,
        tools=[*model_tools, *qa_tools],
        verbose=True,
    )

    aggregator = Agent(
        role="Cross-Model Marketing Analyst",
        goal=(
            "Synthesize per-model SQL and explanations into a unified stakeholder analysis."
        ),
        backstory=(
            "You produce executive-ready reports from multiple semantic models. "
            "You cite each model by label, highlight cross-model insights and gaps, "
            "and never invent query results or warehouse data."
        ),
        llm=llm,
        verbose=True,
    )

    plan_task = Task(
        description=(
            f'User question:\n\n"{user_question}"\n\n'
            f"Model catalog:\n{_format_catalog(catalog)}\n\n"
            "Before finalizing the plan:\n"
            "- If any model's relevance is unclear, call the matching tool from "
            f"{qa_tool_list} with:\n"
            f'  "{coverage_q}"\n'
            "- Skip models whose QA answers show they cannot help.\n\n"
            "Produce a structured plan:\n"
            "1. Set router_candidate true if one model could answer alone; false if cross-model.\n"
            "2. For each relevant model, output model_name, semantic_layer_id, sub_question, rationale.\n"
            "3. Skip models clearly irrelevant (including after semantic_model_qa checks).\n"
            "4. In cross_model_notes, note assumptions, QA findings, and gaps (text only — no SQL)."
        ),
        expected_output=(
            "Structured QueryPlan with user_question, router_candidate, model_queries, cross_model_notes."
        ),
        agent=planner,
        output_pydantic=QueryPlan,
    )

    query_task = Task(
        description=(
            "Using the query plan from the previous task:\n"
            f"text2sql tools: {tool_list}\n"
            f"semantic_model_qa tools (if needed): {qa_tool_list}\n\n"
            "For each entry in model_queries:\n"
            "1. Call solid_model_text2sql__<model_name> with sub_question as the question.\n"
            "2. If text2sql errors or looks mismatched, call solid_semantic_model_qa__<model_name> "
            "to refine understanding, adjust the question if needed, and retry text2sql once.\n"
            "3. Record model label, sub-question, full MCP response (SQL + explanation).\n"
            "4. If a tool returns an error after retry, include it verbatim — do not invent SQL.\n"
            "Return a clear section per model."
        ),
        expected_output=(
            "One section per model with: model name/label, sub-question, MCP text2sql output "
            "(SQL and explanation), or error message."
        ),
        agent=specialist,
        context=[plan_task],
    )

    router_section = ""
    if router_context:
        router_section = (
            f"\n\nRouter mode baseline (for comparison):\n{router_context}\n"
        )

    aggregate_context: list[Task] = [plan_task, query_task]
    agents = [planner, specialist, aggregator]
    tasks: list[Task] = [plan_task, query_task]

    if use_snowflake:
        from soliddata_mcp_poc.snowflake_connector_tool import SnowflakeConnectorTool

        snowflake_tool = SnowflakeConnectorTool(
            account=snowflake_account,
            user=snowflake_user,
            password=snowflake_password,
            database=snowflake_database,
            schema=snowflake_schema,
            warehouse=snowflake_warehouse,
            role=snowflake_role,
        )
        executor_llm = _build_llm(gemini_api_key=gemini_api_key, model=model, temperature=0.1)
        sql_executor = Agent(
            role="Snowflake SQL Executor",
            goal=(
                "Run executable SQL from per-model text2sql outputs in Snowflake and return raw results."
            ),
            backstory=(
                "Extract exact SELECT statements from the Model Query Specialist output and "
                "run each via snowflake_sql_executor. Skip non-SQL or glossary-only outputs."
            ),
            llm=executor_llm,
            tools=[snowflake_tool],
            verbose=True,
        )
        execute_task = Task(
            description=(
                "Using the Model Query Specialist output:\n"
                "1. Extract each executable SQL statement (SELECT only, no markdown).\n"
                "2. Call snowflake_sql_executor with argument 'query' for each SQL.\n"
                "3. Label each result with the model name/label from the prior step.\n"
                "4. If no SQL was produced, say Snowflake execution was skipped."
            ),
            expected_output=(
                "Raw Snowflake results per model, or a note that execution was skipped."
            ),
            agent=sql_executor,
            context=[query_task],
        )
        agents.insert(2, sql_executor)
        tasks.append(execute_task)
        aggregate_context.append(execute_task)

    aggregate_task = Task(
        description=(
            f'Original user question:\n\n"{user_question}"\n'
            f"{router_section}\n"
            "Using the query plan and per-model MCP results from prior tasks, write a report with:\n"
            "1. **Executive summary** (2-3 sentences)\n"
            "2. **Per-model findings** — cite model label and summarize SQL intent\n"
            "3. **Cross-model insights** — connections, conflicts, or gaps between models\n"
            "4. **Recommended follow-up questions**\n\n"
            "If Snowflake ran, summarize actual query results. If only SQL was returned, "
            "state that warehouse execution was not performed. Never invent numeric results."
        ),
        expected_output=(
            "Markdown report with Executive summary, Per-model findings, "
            "Cross-model insights, and Recommended follow-up questions."
        ),
        agent=aggregator,
        context=aggregate_context,
    )
    tasks.append(aggregate_task)

    return Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )
