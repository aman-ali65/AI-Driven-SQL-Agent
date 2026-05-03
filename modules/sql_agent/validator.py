"""
SQL Validator Module

Blocks dangerous SQL operations (DROP, DELETE, TRUNCATE, ALTER)
before they reach the database. Used by SQLRoutes as a safety layer.
"""

BLOCKED_KEYWORDS = ["DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE"]


class SQLValidator:
    """
    Checks SQL strings for destructive or mutating operations.

    Only read-only SELECT queries pass validation by default.
    Schema changes go through SchemaAgent which has its own confirm flow.
    """

    def is_dangerous(self, sql: str) -> bool:
        """
        Returns True if the SQL contains any blocked keyword.

        Args:
            sql: SQL string to inspect.

        Returns:
            True if blocked, False if safe to execute.
        """
        upper = sql.upper()
        return any(kw in upper for kw in BLOCKED_KEYWORDS)

    def clean(self, sql: str) -> str:
        """
        Strips markdown code fences from LLM-generated SQL.

        Args:
            sql: Raw SQL string possibly wrapped in ```sql ... ```

        Returns:
            Cleaned SQL string.
        """
        return sql.replace("```sql", "").replace("```", "").strip()
