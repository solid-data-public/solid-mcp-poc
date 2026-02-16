"""
Snowflake Connector Tool for CrewAI — execute SQL via the Snowflake Python connector.

Uses username/password authentication only. No PAT or Snowflake MCP API.
"""

import json
from typing import Any, Optional, Type

import snowflake.connector
from pydantic import BaseModel, Field

from crewai.tools import BaseTool


class SnowflakeConnectorToolInput(BaseModel):
    """Input schema for Snowflake Connector Tool."""

    query: str = Field(..., description="The SQL query to execute (e.g. SELECT ...).")


class SnowflakeConnectorTool(BaseTool):
    """
    Execute SQL in Snowflake using the Python connector with username/password.
    """

    name: str = "snowflake_sql_executor"
    description: str = (
        "Execute a SQL query in Snowflake and return the results. "
        "Provide the exact SQL string in the 'query' argument. "
        "Returns rows as JSON or an error message."
    )
    args_schema: Type[BaseModel] = SnowflakeConnectorToolInput

    account: str = Field(..., description="Snowflake account identifier (e.g. xy12345.us-east-1)")
    user: str = Field(..., description="Snowflake user name")
    password: Optional[str] = Field(None, description="Snowflake password (use with user)")
    database: str = Field(..., description="Database to use")
    schema: str = Field(..., description="Schema to use")
    warehouse: str = Field(..., description="Warehouse to use")
    role: Optional[str] = Field(None, description="Role to use (optional)")
    max_rows: int = Field(1000, description="Maximum rows to return (avoids oversized context).")

    def __init__(
        self,
        account: str,
        user: str,
        password: Optional[str] = None,
        database: str = "",
        schema: str = "",
        warehouse: str = "",
        role: Optional[str] = None,
        max_rows: int = 1000,
        **kwargs: Any,
    ):
        super().__init__(
            account=account,
            user=user,
            password=password,
            database=database,
            schema=schema,
            warehouse=warehouse,
            role=role,
            max_rows=max_rows,
            **kwargs,
        )

    def _run(self, query: str) -> str:
        """Execute the SQL query and return results as a JSON string."""
        if not query or not query.strip():
            return json.dumps({"error": "Empty query"})

        conn = None
        try:
            conn = snowflake.connector.connect(
                account=self.account,
                user=self.user,
                password=self.password,
                database=self.database,
                schema=self.schema,
                warehouse=self.warehouse,
                role=self.role,
            )
            cur = conn.cursor()
            cur.execute(query)
            rows = cur.fetchmany(self.max_rows)
            columns = [d[0] for d in cur.description] if cur.description else []
            cur.close()
            result = [dict(zip(columns, row)) for row in rows]
            out = json.dumps(result, indent=2, default=str)
            if len(rows) == self.max_rows:
                out += f"\n\n[Result truncated at {self.max_rows} rows. Refine the query (e.g. add LIMIT or filters) for full data.]"
            return out
        except snowflake.connector.Error as e:
            return json.dumps({"error": str(e), "errno": getattr(e, "errno", None)}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
