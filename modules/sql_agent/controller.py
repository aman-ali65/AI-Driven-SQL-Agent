import os
import sqlite3
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain.agents import create_sql_agent

load_dotenv()

DB_PATH = "database/data.db"


def get_llm():
    return ChatGoogleGenerativeAI(
        model="gemini-pro",
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0
    )


def get_schema():
    if not os.path.exists(DB_PATH):
        return ""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    if not tables:
        conn.close()
        return ""
    schema_text = ""
    for (table_name,) in tables:
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        col_names = [col[1] for col in columns]
        schema_text += f"Table: {table_name} | Columns: {', '.join(col_names)}\n"
    conn.close()
    return schema_text


def clean_sql(raw_sql):
    sql = raw_sql.strip()
    sql = sql.replace("```sql", "").replace("```", "")
    return sql.strip()


def generate_sql(user_question, schema):
    try:
        if os.path.exists(DB_PATH):
            db = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}")
            llm = get_llm()
            toolkit = SQLDatabaseToolkit(db=db, llm=llm)
            agent = create_sql_agent(
                llm=llm,
                toolkit=toolkit,
                verbose=False,
                handle_parsing_errors=True
            )
            result = agent.run(user_question)
            if "SELECT" in result.upper():
                for line in result.split("\n"):
                    if "SELECT" in line.upper():
                        return clean_sql(line)
        return _generate_sql_direct(user_question, schema)
    except Exception:
        return _generate_sql_direct(user_question, schema)


def _generate_sql_direct(user_question, schema):
    llm = get_llm()
    prompt = f"""You are an expert SQL assistant. Given the database schema below, write a SQL query to answer the user question.

DATABASE SCHEMA:
{schema}

USER QUESTION:
{user_question}

IMPORTANT RULES:
- Return ONLY the SQL query nothing else
- Do NOT include any explanation
- Do NOT use markdown formatting or backticks
- The SQL must be valid for SQLite

SQL QUERY:"""
    response = llm.invoke(prompt)
    return clean_sql(response.content)


def execute_sql(sql_query):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description] if cursor.description else []
        results = [dict(zip(col_names, row)) for row in rows]
        conn.close()
        return {"success": True, "data": results, "count": len(results)}
    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}
