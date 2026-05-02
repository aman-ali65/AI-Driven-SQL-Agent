# controller.py
# =====================================================================
# PURPOSE:
# This file handles the core logic of the SQL Agent module:
#   1. Read the database schema (table names + column names)
#   2. Send the user's question + schema to the AI
#   3. Receive and clean the generated SQL query
#   4. Execute the SQL query on the SQLite database
#
# Supports three AI providers: Gemini (free), OpenAI (GPT), Claude.
# The provider is selected based on the AI_PROVIDER value in .env
# =====================================================================

import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()  # Load API keys from the .env file

DB_PATH = "database/data.db"
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()  # Default: gemini


# ── AI Provider Functions ─────────────────────────────────────────────────────

def _get_sql_from_gemini(prompt):
    """
    Send a prompt to Google Gemini and get a response.
    This is the recommended option — it is FREE.
    Requires: GEMINI_API_KEY in .env
    """
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-pro")
    response = model.generate_content(prompt)
    return response.text


def _get_sql_from_openai(prompt):
    """
    Send a prompt to OpenAI GPT and get a response.
    Requires: OPENAI_API_KEY in .env (billing setup needed)
    """
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0  # 0 = consistent, deterministic output
    )
    return response.choices[0].message.content


def _get_sql_from_claude(prompt):
    """
    Send a prompt to Anthropic Claude and get a response.
    Requires: ANTHROPIC_API_KEY in .env (billing setup needed)
    """
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


def call_ai(prompt):
    """
    Route the prompt to whichever AI provider is set in the .env file.

    Supported values for AI_PROVIDER:
        gemini  -> Google Gemini (free, default)
        openai  -> OpenAI GPT
        claude  -> Anthropic Claude

    Args:
        prompt (str): The full prompt to send to the AI.

    Returns:
        str: The AI's text response (expected to be a SQL query).
    """
    if AI_PROVIDER == "openai":
        return _get_sql_from_openai(prompt)
    elif AI_PROVIDER == "claude":
        return _get_sql_from_claude(prompt)
    else:
        return _get_sql_from_gemini(prompt)  # Default


# ── Database Functions ────────────────────────────────────────────────────────

def get_schema():
    """
    Read all table names and their column names from the SQLite database.
    This schema is sent to the AI so it knows what tables exist.

    Returns:
        str: A formatted schema string. Example:
             Table: students | Columns: id, name, score, grade
             Table: teachers | Columns: id, name, subject

             Returns empty string "" if no tables exist yet.
    """
    if not os.path.exists(DB_PATH):
        return ""  # Database file does not exist yet

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get the names of all tables in the database
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    if not tables:
        conn.close()
        return ""

    schema_text = ""
    for (table_name,) in tables:
        # Get column info for each table
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        col_names = [col[1] for col in columns]  # Extract only the column names
        schema_text += f"Table: {table_name} | Columns: {', '.join(col_names)}\n"

    conn.close()
    return schema_text


def clean_sql(raw_sql):
    """
    Remove any markdown formatting that the AI may have added.

    The AI sometimes wraps SQL in markdown like:
        ```sql
        SELECT * FROM students
        ```

    This function strips that formatting and returns only the raw SQL.

    Args:
        raw_sql (str): The raw text response from the AI.

    Returns:
        str: Clean SQL query with no extra formatting.
    """
    sql = raw_sql.strip()
    sql = sql.replace("```sql", "")
    sql = sql.replace("```", "")
    return sql.strip()


def generate_sql(user_question, schema):
    """
    Send the user's plain English question and the database schema to the AI.
    The AI returns a valid SQLite SQL query.

    Args:
        user_question (str): The user's question in plain English.
                             Example: "Show students with score above 80"
        schema (str):        The current database schema from get_schema().

    Returns:
        str: A clean, ready-to-run SQL query.
             Example: SELECT * FROM students WHERE score > 80
    """
    prompt = f"""You are an expert SQL assistant. Given the database schema below, write a SQL query to answer the user's question.

DATABASE SCHEMA:
{schema}

USER QUESTION:
{user_question}

IMPORTANT RULES:
- Return ONLY the SQL query, nothing else
- Do NOT include any explanation or description
- Do NOT use markdown formatting or backticks
- The SQL must be valid for SQLite specifically

SQL QUERY:
"""
    raw_sql = call_ai(prompt)
    return clean_sql(raw_sql)


def execute_sql(sql_query):
    """
    Run the SQL query on the SQLite database and return the results.

    Args:
        sql_query (str): A clean, validated SQL query to execute.

    Returns:
        dict: On success:
              {
                  "success": True,
                  "data": [{"name": "Ali", "score": 85}, ...],
                  "count": 3
              }

              On failure:
              {
                  "success": False,
                  "error": "Error message here"
              }
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(sql_query)
        rows = cursor.fetchall()

        # Get column names from the cursor description
        col_names = [desc[0] for desc in cursor.description] if cursor.description else []

        # Convert each row tuple into a dictionary
        # Example: ("Ali", 85) -> {"name": "Ali", "score": 85}
        results = [dict(zip(col_names, row)) for row in rows]

        conn.close()
        return {
            "success": True,
            "data": results,
            "count": len(results)
        }

    except Exception as e:
        conn.close()
        return {
            "success": False,
            "error": str(e)
        }
