"""CrewAI crew that uses the SolidData MCP server for text2sql and Snowflake connector for execution."""

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
    """Build the crew: SQL Analyst (Solid MCP text2sql) -> [optional: Snowflake Executor] -> Reporter.

    Flow:
    1. SQL Analyst uses Solid MCP text2sql to generate SQL from the user question.
    2. If Snowflake connector config is provided: an executor runs that SQL via the Snowflake Python connector and returns results.
    3. Reporter explains the query and, when Snowflake was used, analyzes the actual query results; otherwise explains what the SQL does.
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
            goal="Execute the SQL from the previous step in Snowflake and return the raw tool output in full.",
            backstory=(
                "You run SQL in Snowflake via the snowflake_sql_executor tool. You receive the exact SQL "
                "from the SQL Analyst. You call the tool with the single argument 'query' set to the exact SQL string. "
                "You must return the complete tool response (JSON rows or error) in your final answer — never summarize, "
                "truncate, or return an empty response."
            ),
            llm=executor_llm,
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
                "2. Call the snowflake_sql_executor tool with argument \"query\" set to the exact SQL string.\n"
                "3. In your final answer, return the complete tool output (full JSON or error). "
                "Your response must not be empty — include the entire tool result."
            ),
            expected_output=(
                "The complete raw result from snowflake_sql_executor (full JSON array of rows or error object). "
                "Never an empty or truncated response."
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
            "what the query does (tables, filters, purpose) and write a short stakeholder report."
        ),
        expected_output=(
            "A concise stakeholder report. When results were provided, base it on the data; "
            "otherwise explain what the SQL retrieves."
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
