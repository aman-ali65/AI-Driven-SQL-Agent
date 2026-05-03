"""
SQL Agent Controller Module

Core intelligence layer — generates SQL from plain English using
LangChain's SQLDatabaseToolkit + Gemini LLM, then executes on SQLite.

Allows loading external .db files at runtime.
"""

import os
import sqlite3

from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool
from langchain.agents import create_agent
from modules.api_key_manager import APIKeyManager

load_dotenv()

PRIMARY_MODEL  = "gemini-3.1-flash-lite-preview"
FALLBACK_MODEL = "gemini-2.5-flash"


class SQLAgentController:
    """
    Manages SQL generation, validation, and execution against a SQLite database.

    Responsibilities:
        - Maintain an active SQLDatabase connection
        - Generate SQL from natural language via Gemini LLM
        - Execute SQL and return structured results
        - Allow hot-swapping the active database file
        - Generate plain English answers from query results
    """

    def __init__(self, db_path: str, api_key: str):
        """
        Args:
            db_path:  Path to the SQLite database file.
            api_key:  Google Gemini API key.
        """
        self.db_path = db_path
        self.key_manager = APIKeyManager(api_key)
        self.api_key = self.key_manager.get_key()
        self.llm     = self._init_llm(PRIMARY_MODEL)
        self.db      = None
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._connect_db(db_path)

        # Agent State for Frontend Integration
        self.last_sql = None
        self.last_data = None
        self.last_columns = None

        # Setup Tools
        @tool
        def query_database(query: str) -> str:
            """Execute a SQL SELECT query against the SQLite database and return the results."""
            from modules.system_logger import SystemLogger
            SystemLogger.log("SQL", "Tool:query_database", f"Executing:\n{query}")
            
            if not self.db_path or not os.path.exists(self.db_path):
                return "Error: No database connected."
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query)
                rows = cursor.fetchall()
                columns = [d[0] for d in cursor.description] if cursor.description else []
                data = [dict(row) for row in rows]
                conn.close()
                
                # Save to controller state for frontend chart rendering
                self.last_sql = query
                self.last_data = data
                self.last_columns = columns
                
                # Return string representation for the LLM
                return str(data[:20]) # Limit to 20 rows to avoid token overflow
            except Exception as e:
                return f"Error executing query: {str(e)}"
                
        @tool
        def get_schema() -> str:
            """Get the complete schema of the database: all tables, columns and data types."""
            return self.get_schema()

        @tool
        def modify_database(sql: str) -> str:
            """Execute a DDL or DML statement (CREATE TABLE, ALTER TABLE, INSERT, UPDATE, DELETE, DROP)
            against a COPY of the active database. The original database is NEVER modified.
            Use this when the user wants to add columns, create tables, insert data, or restructure data.
            Always call get_schema first to know the current structure.
            Returns the result of the operation."""
            from modules.system_logger import SystemLogger
            SystemLogger.log("MODIFY", "Tool:modify_database", f"Statement:\n{sql}")
            if not self.db_path or not os.path.exists(self.db_path):
                return "Error: No database connected."
            try:
                import shutil
                # Work on the copy (create it if it doesn't exist)
                copy_path = self.db_path.replace(".db", "_modified.db").replace(".sqlite", "_modified.sqlite")
                if not os.path.exists(copy_path):
                    shutil.copy2(self.db_path, copy_path)
                self.modified_db_path = copy_path
                conn = sqlite3.connect(copy_path)
                cursor = conn.cursor()
                cursor.execute(sql)
                conn.commit()
                affected = cursor.rowcount
                conn.close()
                return f"Success! Statement executed on the working copy. Rows affected: {affected}. The modified database can be downloaded via the Download button."
            except Exception as e:
                return f"Error modifying database: {str(e)}"

        self.tools = [query_database, get_schema, modify_database]
        system_message = """You are **QueryMind** — an elite AI SQL Data Engineer. You work like a senior data engineer who talks naturally while doing the work for the user. The user should feel like they're having a conversation with a brilliant colleague who understands data deeply.

## 🔧 Tools Available

1. **`get_schema`** — Get ALL tables, columns, and data types. Call this FIRST before any query or modification. Required to know what exists.

2. **`query_database`** — Execute a SELECT query to read and analyze data. Use for questions, stats, filtering, aggregations, top-N, averages, counts, joins.

3. **`modify_database`** — Execute DDL or DML (ALTER TABLE, CREATE TABLE, ADD COLUMN, INSERT, UPDATE, DELETE) on a **COPY** of the database. The original is NEVER touched. After modifying, always confirm what was done.

## 🧠 Reasoning Flow

**For data questions:**
1. Call `get_schema` → understand the structure
2. Write precise SQLite SQL → execute with `query_database`
3. Give a clear, insightful, conversational answer

**For schema/modification requests** ("add a column", "create a table", "update rows"):
1. Call `get_schema` first to confirm current structure
2. Use `modify_database` with the appropriate DDL/DML
3. Confirm what was done and tell the user they can download the modified DB

**For general conversation:** Reply naturally without using any tools.

## 📋 SQL Rules
- SELECT queries only via `query_database`. Never modify with it.
- Modifications only via `modify_database`.
- Use only columns/tables confirmed by `get_schema`.
- Default `LIMIT 50` for SELECT unless user specifies otherwise.
- Use proper SQLite syntax — no MySQL/PostgreSQL specific functions.

## 💬 Communication Style
- Talk like a colleague: "Sure, let me check the schema first..." → then do it
- Lead with the **answer**, then explain the data
- Use **markdown**: bold numbers, bullet lists, tables for comparisons
- Never dump raw SQL unless user asks
- After any modification: always say "✅ Done! I've made that change to your working copy. You can **download it** using the Download button."
"""
        try:
            self.agent = create_agent(model=self.llm, tools=self.tools, system_prompt=system_message)
        except Exception:
            self.agent = None

    def _init_llm(self, model: str) -> ChatGoogleGenerativeAI:
        """
        Creates a Gemini LLM instance.

        Args:
            model: Gemini model name string.

        Returns:
            ChatGoogleGenerativeAI instance.
        """
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=self.api_key,
            temperature=0
        )

    def _connect_db(self, db_path: str):
        """
        Connects to a SQLite database file and initialises the LangChain SQLDatabase.

        If the file does not exist yet, SQLite creates it on connect.

        Args:
            db_path: Path to the .db file.
        """
        try:
            self.db      = SQLDatabase.from_uri(f"sqlite:///{db_path}")
            toolkit      = SQLDatabaseToolkit(db=self.db, llm=self.llm)
            self.tools   = toolkit.get_tools()
            self.db_path = db_path
        except Exception as e:
            self.db    = None
            self.tools = []

    def load_db_file(self, db_path: str) -> dict:
        """
        Hot-swaps the active database to a different .db file.

        Args:
            db_path: Full path to the new SQLite database file.

        Returns:
            Dict with keys: success (bool), db_path (str), error (str on failure)
        """
        if not os.path.exists(db_path):
            return {"success": False, "error": f"File not found: {db_path}"}
        try:
            self._connect_db(db_path)
            schema = self.get_schema()
            return {"success": True, "db_path": db_path, "schema": schema}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_schema(self) -> str:
        """
        Returns the schema string from the active database.

        Returns:
            Schema as a text string, or empty string if no DB connected.
        """
        if not self.db:
            return ""
        try:
            return self.db.get_table_info()
        except Exception:
            return ""

    def run_agent(self, user_query: str) -> dict:
        """
        Runs the true Langchain Tool-Calling Agent to process the user's input.
        Returns the final answer and any SQL/data generated during the process.
        """
        from modules.system_logger import SystemLogger
        SystemLogger.log("INFO", "SQLAgentController", f"Agent invoked with: {user_query}")
        
        self.last_sql = None
        self.last_data = None
        self.last_columns = None
        
        if not self.agent:
            return {"success": False, "error": "Agent is not configured properly."}
            
        max_retries = len(self.key_manager.keys) if self.key_manager.keys else 1
        for attempt in range(max_retries):
            try:
                result = self.agent.invoke(
                    {"messages": [HumanMessage(content=user_query)]},
                    config={"recursion_limit": 10}
                )
                raw_answer = result["messages"][-1].content
                break
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "quota" in err_str.lower() or "exhausted" in err_str.lower():
                    SystemLogger.log("WARNING", "SQLAgentController", f"API Error (429). Rotating key... (Attempt {attempt+1}/{max_retries})")
                    if self.key_manager.rotate():
                        self.api_key = self.key_manager.get_key()
                        self.llm = self._init_llm(PRIMARY_MODEL)
                        self._connect_db(self.db_path) # re-init toolkit
                        continue
                SystemLogger.log("ERROR", "SQLAgentController", err_str)
                return {"success": False, "error": err_str}
        else:
            return {"success": False, "error": "All API keys exhausted or failed."}

        # Fix: newer Gemini models return a list of content blocks instead of plain string
        if isinstance(raw_answer, list):
            answer = "\n".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in raw_answer
            ).strip()
        else:
            answer = raw_answer
        SystemLogger.log("LLM_RESPONSE", "SQLAgentController", answer)
        return {
            "success": True,
            "answer": answer,
            "sql": self.last_sql,
            "data": self.last_data,
            "columns": self.last_columns,
            "modified_db": getattr(self, "modified_db_path", None)
        }

    def validate_sql(self, sql: str) -> str:
        """
        Strips markdown code fences from LLM output.
        """
        return sql.replace("```sql", "").replace("```", "").strip() if sql else ""
