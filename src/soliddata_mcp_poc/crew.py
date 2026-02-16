"""CrewAI crew that uses the SolidData MCP server for text2sql and Snowflake for execution."""

from typing import Optional

from crewai import Agent, Crew, LLM, Process, Task
from crewai.mcp import MCPServerHTTP

from soliddata_mcp_poc.snowflake_mcp_tool import SnowflakeMCPTool


def build_crew(
    mcp_token: str,
    mcp_server_url: str,
    user_question: str,
    *,
    gemini_api_key: str,
    semantic_layer_id: str,
    model: str = "gemini/gemini-2.0-flash",
    # Optional Snowflake MCP: when set, crew runs SQL in Snowflake and reporter analyzes results.
    snowflake_mcp_server_url: Optional[str] = None,
    snowflake_database: Optional[str] = None,
    snowflake_schema: Optional[str] = None,
    snowflake_mcp_server_name: Optional[str] = None,
    snowflake_access_token: Optional[str] = None,
    snowflake_sql_tool_name: str = "sql_exec_tool",
) -> Crew:
    """Build the crew: SQL Analyst (Solid MCP text2sql) -> [optional: Snowflake Executor] -> Reporter.

    Flow:
    1. SQL Analyst uses Solid MCP text2sql to generate SQL from the user question.
    2. If Snowflake config is provided: an executor agent runs that SQL in Snowflake and returns results.
    3. Reporter explains the query and, when Snowflake was used, analyzes the actual query results
       for the stakeholder; otherwise explains what the SQL does.

    Args:
        mcp_token: Bearer token obtained from SolidData auth.
        mcp_server_url: SolidData MCP server URL.
        user_question: The natural-language question to convert to SQL.
        snowflake_*: When all are set, adds a step to execute the generated SQL in Snowflake.

    Returns:
        A ready-to-kickoff Crew instance.
    """
    llm = LLM(
        model=model,
        api_key=gemini_api_key,
        temperature=0.3,
    )

    # ── MCP connection ───────────────────────────────────
    # MCP requires "Bearer {token}". mcp_token is the raw token from the auth exchange (management key → token); we always send it as Bearer {mcp_token}.
    mcp = MCPServerHTTP(
        url=mcp_server_url,
        headers={"Authorization": f"Bearer {mcp_token}"},
        streamable=True,
        cache_tools_list=True,
    )

    # ── Agents ───────────────────────────────────────────
    sql_analyst = Agent(
        role="SQL Data Analyst",
        goal=(
            "Convert the user's natural-language question into an accurate SQL query "
            "using the text2sql MCP tool provided by SolidData."
        ),
        backstory=(
            "You are a senior data analyst who turns business questions into "
            "precise SQL queries. You always use the text2sql tool — never guess "
            "the schema or make up table names."
        ),
        llm=llm,
        mcps=[mcp],
        verbose=True,
    )

    use_snowflake = all(
        [
            snowflake_mcp_server_url,
            snowflake_database,
            snowflake_schema,
            snowflake_mcp_server_name,
        ]
    )

    if use_snowflake:
        snowflake_tool = SnowflakeMCPTool(
            mcp_server_url=snowflake_mcp_server_url,
            database=snowflake_database,
            schema=snowflake_schema,
            server_name=snowflake_mcp_server_name,
            access_token=snowflake_access_token,
        )
        sql_executor = Agent(
            role="Snowflake SQL Executor",
            goal="Execute the SQL query from the previous step in Snowflake and return the raw results.",
            backstory=(
                "You run SQL in Snowflake via the snowflake_mcp_tool. You receive the exact SQL "
                "from the SQL Analyst. You call the tool with tool_name "
                f"'{snowflake_sql_tool_name}' and arguments {{'query': '<the SQL>}}. "
                "You return the full tool response without summarizing."
            ),
            llm=llm,
            tools=[snowflake_tool],
            verbose=True,
        )

    reporter = Agent(
        role="Report Writer",
        goal=(
            "Produce a clear, stakeholder-friendly summary. When query results are available, "
            "analyze those results; otherwise explain what the SQL does."
        ),
        backstory=(
            "You are an expert at explaining data and queries in plain language. "
            "When you receive actual query results from Snowflake, you summarize the data, "
            "highlight key numbers or trends, and write a concise report. When you only "
            "receive a SQL query, you explain what the query does in business terms."
        ),
        llm=llm,
        verbose=True,
    )

    # ── Tasks ────────────────────────────────────────────
    generate_sql = Task(
        description=(
            f'Use the text2sql MCP tool to generate sql query using the following user question as input.'
            f' The question is: \n\n"{user_question}"\n\n'
            f'The semantic layer id: {semantic_layer_id}\n\n'
            f'Return the SQL query and a one-sentence explanation of what it does.'
        ),
        expected_output="The SQL query and a brief explanation of what it retrieves.",
        agent=sql_analyst,
    )

    if use_snowflake:
        execute_sql = Task(
            description=(
                "Using the SQL query from the previous task output:\n"
                "1. Extract the exact SQL statement (only the SQL, no markdown or explanation).\n"
                f"2. Call the snowflake_mcp_tool with tool_name '{snowflake_sql_tool_name}' "
                "and arguments {\"query\": \"<the exact SQL>\"}.\n"
                "3. Return the full result returned by the tool (do not summarize or truncate)."
            ),
            expected_output="The raw result from executing the SQL in Snowflake (rows/data or error message).",
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
            "what the query does (tables, filters, purpose) and write a short stakeholder report."
        ),
        expected_output=(
            "A concise stakeholder report. When results were provided, base it on the data; "
            "otherwise explain what the SQL retrieves."
        ),
        agent=reporter,
        context=[generate_sql, execute_sql] if use_snowflake else [generate_sql],
    )

    # ── Crew ─────────────────────────────────────────────
    agents = [sql_analyst, sql_executor, reporter] if use_snowflake else [sql_analyst, reporter]
    tasks = [generate_sql, execute_sql, explain_and_report] if use_snowflake else [generate_sql, explain_and_report]
    return Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )
