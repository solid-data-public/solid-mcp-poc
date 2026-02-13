"""CrewAI crew that uses the SolidData MCP server for text2sql."""

from crewai import Agent, Crew, LLM, Process, Task
from crewai.mcp import MCPServerHTTP


def build_crew(
    mcp_token: str,
    mcp_server_url: str,
    user_question: str,
    *,
    gemini_api_key: str,
    model: str = "gemini/gemini-2.0-flash",
) -> Crew:
    """Build a two-agent crew: SQL Analyst (with MCP text2sql) -> Reporter.

    Args:
        mcp_token: Bearer token obtained from SolidData auth.
        mcp_server_url: SolidData MCP server URL.
        user_question: The natural-language question to convert to SQL.

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

    reporter = Agent(
        role="Report Writer",
        goal=(
            "Take the SQL output from the analyst and produce a clear, "
            "stakeholder-friendly summary."
        ),
        backstory=(
            "You are an expert at explaining technical database queries in "
            "plain language. You distill results into concise, actionable "
            "reports that any business user can understand."
        ),
        llm=llm,
        verbose=True,
    )

    # ── Tasks ────────────────────────────────────────────
    generate_sql = Task(
        description=(
            f'Use the text2sql MCP tool to generate sql query using the following user question as input.'
            f' The question is: \n\n"{user_question}"\n\n'
            f'The semantic layer id: 851b4156-e0ea-460b-b6f9-cf3f428e95b5' # TODO: Make this dynamic
            f'Return the SQL query and a one-sentence explanation of what it does.'
        ),
        expected_output="The SQL query and a brief explanation of what it retrieves.",
        agent=sql_analyst,
    )

    explain_and_report = Task(
        description=(
            "Using the SQL query and explanation from the previous step:\n"
            "1. Explain in plain language what the query does (tables, filters, purpose).\n"
            "2. Write a short report (2-3 sentences) suitable for a business stakeholder."
        ),
        expected_output="A clear explanation of the SQL query followed by a concise stakeholder report.",
        agent=reporter,
        context=[generate_sql],
    )

    # ── Crew ─────────────────────────────────────────────
    return Crew(
        agents=[sql_analyst, reporter],
        tasks=[generate_sql, explain_and_report],
        process=Process.sequential,
        verbose=True,
    )
