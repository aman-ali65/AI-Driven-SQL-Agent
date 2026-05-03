# validator.py
# =====================================================================
# PURPOSE:
# This file checks whether a SQL query is safe to run.
# It blocks dangerous operations like DROP, DELETE, TRUNCATE, ALTER
# to protect the database from accidental or harmful changes.
# =====================================================================

DANGEROUS_KEYWORDS = ["DROP", "DELETE", "TRUNCATE", "ALTER"]

def is_dangerous(sql):
    """
    Check if the SQL query contains any dangerous keywords.

    Args:
        sql (str): The SQL query string to check.

    Returns:
        bool: True if dangerous (should be blocked), False if safe.

    Examples:
        is_dangerous("DROP TABLE students")       -> True
        is_dangerous("DELETE FROM students")      -> True
        is_dangerous("SELECT * FROM students")    -> False
        is_dangerous("SELECT name FROM students") -> False
    """
    upper_sql = sql.upper()  # Convert to uppercase so comparison is case-insensitive

    for keyword in DANGEROUS_KEYWORDS:
        if keyword in upper_sql:
            return True  # Dangerous keyword found — block this query

    return False  # No dangerous keywords found — query is safe
