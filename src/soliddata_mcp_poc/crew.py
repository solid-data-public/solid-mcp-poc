"""CrewAI crew that uses the SolidData MCP server (text2sql, glossary_search) and Snowflake connector."""

from typing import Optional

from crewai import Agent, Crew, LLM, Process, Task
from crewai.mcp import MCPServerHTTP

from soliddata_mcp_poc.snowflake_connector_tool import SnowflakeConnectorTool


def build_crew(
    mcp_token: str,
    mcp_server_url: str,
    user_question: str,
    *,
    gemini_api_key: str,
    semantic_layer_id: str,
    model: str = "gemini/gemini-2.0-flash",
    # Optional Snowflake (connector with username/password only)
    snowflake_account: Optional[str] = None,
    snowflake_user: Optional[str] = None,
    snowflake_password: Optional[str] = None,
    snowflake_database: Optional[str] = None,
    snowflake_schema: Optional[str] = None,
    snowflake_warehouse: Optional[str] = None,
    snowflake_role: Optional[str] = None,
) -> Crew:
    """Build the crew: SQL Analyst (Solid MCP text2sql / glossary_search) -> [optional: Snowflake Executor] -> Reporter.

    Flow:
    1. SQL Analyst uses Solid MCP **text2sql** for data questions, or **glossary_search** for definitions / acronyms / terminology.
    2. If Snowflake connector config is provided: an executor runs that SQL via the Snowflake Python connector and returns results.
    3. Reporter explains the query and, when Snowflake was used, analyzes the actual query results; otherwise explains what the SQL does or summarizes glossary output.
    """
    # Shared LLM with enough output space to avoid truncation/empty responses (e.g. Snowflake result passthrough).
    llm = LLM(
        model=model,
        api_key=gemini_api_key,
        temperature=0.3,
        max_tokens=8192,
    )

    mcp = MCPServerHTTP(
        url=mcp_server_url,
        headers={"Authorization": f"Bearer {mcp_token}"},
        streamable=True,
        cache_tools_list=True,
    )

    sql_analyst = Agent(
        role="SQL Data Analyst",
        goal=(
            "Answer the user's question using SolidData MCP tools: use **glossary_search** for "
            "terminology, definitions, and acronyms; use **text2sql** when the user needs a query "
            "against the semantic layer / warehouse."
        ),
        backstory=(
            "You are a senior data analyst. For data and metrics questions you use the **text2sql** "
            "tool and never guess schema or table names. For 'what does X mean?' or glossary-style "
            "questions you use **glossary_search** with a clear `query` string instead of inventing definitions."
        ),
        llm=llm,
        mcps=[mcp],
        verbose=True,
    )

    use_snowflake = bool(
        snowflake_account
        and snowflake_user
        and snowflake_password
        and snowflake_database
        and snowflake_schema
        and snowflake_warehouse
    )

    if use_snowflake:
        snowflake_tool = SnowflakeConnectorTool(
            account=snowflake_account,
            user=snowflake_user,
            password=snowflake_password,
            database=snowflake_database,
            schema=snowflake_schema,
            warehouse=snowflake_warehouse,
            role=snowflake_role,
        )
        # Lower temperature for deterministic passthrough of tool output (reduces empty LLM responses).
        executor_llm = LLM(
            model=model,
            api_key=gemini_api_key,
            temperature=0.1,
            max_tokens=8192,
        )
        sql_executor = Agent(
            role="Snowflake SQL Executor",
            goal=(
                "When the prior step produced executable SQL from text2sql, run it in Snowflake and return "
                "the raw tool output. When the prior step was glossary-only, skip execution and say so."
            ),
            backstory=(
                "You run SQL in Snowflake via the snowflake_sql_executor tool only when you have a real "
                "SELECT (or other warehouse) statement from text2sql. If the SQL Analyst used glossary_search "
                "and there is no SQL to run, do not call the tool — explain that Snowflake was skipped. "
                "When you do run SQL, call the tool with argument 'query' set to the exact SQL string and "
                "return the complete tool response in full."
            ),
            llm=executor_llm,
            tools=[snowflake_tool],
            verbose=True,
        )

    reporter = Agent(
        role="Report Writer",
        goal=(
            "Produce a clear, stakeholder-friendly summary: from Snowflake results, from SQL alone, "
            "or from glossary / terminology answers when no SQL was involved."
        ),
        backstory=(
            "You are an expert at explaining data and queries in plain language. "
            "When you receive actual query results from Snowflake, you summarize the data, "
            "highlight key numbers or trends, and write a concise report. When you only "
            "receive a SQL query, you explain what the query does in business terms. "
            "When the prior steps are glossary-focused, summarize the definitions clearly for stakeholders."
        ),
        llm=llm,
        verbose=True,
    )

    generate_sql = Task(
        description=(
            f'User question:\n\n"{user_question}"\n\n'
            f'Semantic layer id (required only for **text2sql**): {semantic_layer_id}\n\n'
            "1. If the user is asking what a term, acronym, or field **means**, or wants a **definition** "
            "from the business glossary (not warehouse data): call the MCP tool **glossary_search** "
            "with `query` set to the user's question (or the specific term).\n"
            "2. Otherwise, for questions that need **SQL or data from tables**: call **text2sql** with "
            "the user question and the semantic layer id above.\n"
            "3. Return either the glossary result in plain language, or the SQL plus a one-sentence "
            "explanation of what the query retrieves."
        ),
        expected_output=(
            "Either a glossary-style answer from glossary_search, or the SQL query from text2sql "
            "with a brief explanation of what it retrieves."
        ),
        agent=sql_analyst,
    )

    if use_snowflake:
        execute_sql = Task(
            description=(
                "Using the previous task output:\n"
                "1. If there is **no** executable SQL (e.g. the analyst answered with **glossary_search** only): "
                "do **not** call snowflake_sql_executor. Reply that Snowflake execution was skipped because "
                "no SQL was generated.\n"
                "2. If there **is** SQL from text2sql: extract the exact SQL statement (only the SQL, no markdown).\n"
                "3. Call snowflake_sql_executor with argument \"query\" set to that SQL string.\n"
                "4. Return the complete tool output (full JSON or error), or the skip message from step 1."
            ),
            expected_output=(
                "Either the complete raw result from snowflake_sql_executor, or an explicit note that "
                "execution was skipped because no SQL was produced."
            ),
            agent=sql_executor,
            context=[generate_sql],
        )

    explain_and_report = Task(
        description=(
            "Using the context from the previous step(s):\n"
            "1. If you have actual query results from Snowflake: summarize the data, "
            "highlight key numbers or findings, and write a short report (2-4 sentences) "
            "suitable for a business stakeholder.\n"
            "2. If you only have a SQL query and explanation: explain in plain language "
            "what the query does (tables, filters, purpose) and write a short stakeholder report.\n"
            "3. If the flow was glossary-only (definitions / acronyms, no SQL): write a short, clear "
            "report from the glossary content — do not invent SQL or metrics."
        ),
        expected_output=(
            "A concise stakeholder report: data-driven when Snowflake ran, SQL-explained when only "
            "text2sql ran, or terminology-focused when glossary_search was used."
        ),
        agent=reporter,
        context=[generate_sql, execute_sql] if use_snowflake else [generate_sql],
    )

    agents = [sql_analyst, sql_executor, reporter] if use_snowflake else [sql_analyst, reporter]
    tasks = [generate_sql, execute_sql, explain_and_report] if use_snowflake else [generate_sql, explain_and_report]
    return Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )
