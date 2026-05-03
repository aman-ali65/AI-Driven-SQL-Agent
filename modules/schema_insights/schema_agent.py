"""
Schema Agent Module

Manages database schema changes (CREATE/ALTER/DROP) using plain English.
Also generates AI-powered data insights with Plotly charts.
"""

import os
import sqlite3
from flask import request, jsonify
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from modules.visualizer.chart_generator import ChartGenerator

load_dotenv()

PRIMARY_MODEL  = "gemini-2.5-flash-lite"
FALLBACK_MODEL = "gemini-1.5-flash"


class SchemaAgent:
    """
    Converts plain English into DDL SQL and executes schema changes.
    Also generates natural language insights from SQL result data.
    """

    def __init__(self, db_path: str, api_key: str):
        """
        Args:
            db_path:  Path to the SQLite database file.
            api_key:  Google Gemini API key.
        """
        self.db_path = db_path
        self.api_key = api_key
        self.llm     = ChatGoogleGenerativeAI(
            model=PRIMARY_MODEL, google_api_key=api_key, temperature=0)
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def generate_schema_sql(self, user_request: str) -> str:
        """
        Converts a plain English request into a DDL SQL statement.

        Args:
            user_request: e.g. "Create a table employees with name, age, salary"

        Returns:
            DDL SQL string (CREATE TABLE / ALTER TABLE / DROP TABLE).
        """
        prompt = f"""You are a SQLite expert. Convert this request into SQLite DDL SQL.

REQUEST: {user_request}

RULES:
- Only output CREATE TABLE, ALTER TABLE, or DROP TABLE
- Use TEXT, INTEGER, or REAL types
- Return ONLY the SQL, no markdown, no explanation

SQL:"""
        try:
            response = self.llm.invoke(prompt)
        except Exception:
            self.llm = ChatGoogleGenerativeAI(
                model=FALLBACK_MODEL, google_api_key=self.api_key, temperature=0)
            response = self.llm.invoke(prompt)
        return response.content.strip().replace("```sql","").replace("```","").strip()

    def is_dangerous(self, sql: str) -> bool:
        """Returns True if SQL contains DROP, DELETE, or TRUNCATE."""
        upper = sql.upper()
        return any(k in upper for k in ["DROP", "DELETE", "TRUNCATE"])

    def execute_ddl(self, sql: str) -> dict:
        """
        Executes a DDL SQL statement on the database.

        Returns:
            Dict: success (bool), message (str) or error (str)
        """
        conn = sqlite3.connect(self.db_path)
        try:
            conn.cursor().execute(sql)
            conn.commit()
            conn.close()
            return {"success": True, "message": "Schema updated successfully."}
        except Exception as e:
            conn.close()
            return {"success": False, "error": str(e)}

    def get_full_schema(self) -> dict:
        """
        Returns full schema for all tables as a dict.

        Returns:
            { table_name: [{column, type, nullable}, ...] }
        """
        if not os.path.exists(self.db_path):
            return {}
        conn   = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        result = {}
        for (t,) in tables:
            cursor.execute(f"PRAGMA table_info({t});")
            result[t] = [{"column": c[1], "type": c[2], "nullable": not c[3]}
                         for c in cursor.fetchall()]
        conn.close()
        return result

    def generate_insights(self, results: list, query: str = "") -> str:
        """
        Generates plain English insights from SQL result rows using Gemini.

        Args:
            results: List of row dicts (first 20 used).
            query:   Original SQL for context.

        Returns:
            Natural language insights string.
        """
        if not results:
            return "No data to analyze."
        cols    = list(results[0].keys())
        preview = "\n".join(str(r) for r in results[:20])
        prompt  = f"""You are a data analyst. Analyze this data concisely.

QUERY: {query}
COLUMNS: {', '.join(cols)}
DATA ({min(20,len(results))} of {len(results)} rows):
{preview}

Give: brief summary, key numbers, interesting patterns.
Be concise and beginner-friendly.

INSIGHTS:"""
        try:
            return self.llm.invoke(prompt).content
        except Exception:
            return "Could not generate insights."


class SchemaRoutes:
    """
    Registers /schema/* Flask routes.

    Routes:
        POST /schema/modify   -> English -> DDL (preview or execute)
        GET  /schema/show     -> Full schema details
        POST /schema/insights -> Results -> AI insights + chart
        POST /schema/drop     -> Drop a table
    """

    def __init__(self, app, agent: SchemaAgent, chart_gen: ChartGenerator):
        self.app       = app
        self.agent     = agent
        self.chart_gen = chart_gen

    def register(self):
        """Binds routes. Call once at startup."""
        self.app.add_url_rule("/schema/modify",   "schema_modify",   self.modify,   methods=["POST"])
        self.app.add_url_rule("/schema/show",     "schema_show",     self.show,     methods=["GET"])
        self.app.add_url_rule("/schema/insights", "schema_insights", self.insights, methods=["POST"])
        self.app.add_url_rule("/schema/drop",     "schema_drop",     self.drop,     methods=["POST"])

    def modify(self):
        """
        POST /schema/modify
        Request: { "request": "Create a table...", "confirm": false }
        confirm=false -> preview SQL only. confirm=true -> execute.
        """
        data = request.get_json()
        if not data or "request" not in data:
            return jsonify({"error": "Provide a 'request' field."}), 400

        sql       = self.agent.generate_schema_sql(data["request"])
        dangerous = self.agent.is_dangerous(sql)
        confirm   = data.get("confirm", False)

        if not confirm:
            return jsonify({
                "generated_sql": sql, "is_dangerous": dangerous,
                "message":       "Send with 'confirm': true to execute.",
                "warning":       "⚠️ Destructive!" if dangerous else None
            })

        result                  = self.agent.execute_ddl(sql)
        result["generated_sql"] = sql
        return jsonify(result)

    def show(self):
        """GET /schema/show — full schema for all tables."""
        schema = self.agent.get_full_schema()
        return jsonify({"tables": schema, "table_count": len(schema)})

    def insights(self):
        """
        POST /schema/insights
        Request: { "results": [{...}, ...], "query": "SELECT ..." }
        Returns AI insights and Plotly chart.
        """
        data = request.get_json()
        if not data or "results" not in data:
            return jsonify({"error": "Provide 'results' list."}), 400

        results  = data["results"]
        query    = data.get("query", "")
        insights = self.agent.generate_insights(results, query)
        chart    = self.chart_gen.generate(results, query)
        return jsonify({"insights": insights, "rows_analyzed": len(results), "chart": chart})

    def drop(self):
        """
        POST /schema/drop
        Request: { "table_name": "old_table", "confirm": true }
        """
        data = request.get_json()
        if not data or "table_name" not in data:
            return jsonify({"error": "Provide 'table_name'."}), 400

        table   = data["table_name"]
        sql     = f"DROP TABLE IF EXISTS {table};"
        confirm = data.get("confirm", False)

        if not confirm:
            return jsonify({
                "generated_sql": sql,
                "warning":       f"⚠️ Permanently deletes '{table}' and all its data!",
                "message":       "Send with 'confirm': true to execute."
            })

        result                  = self.agent.execute_ddl(sql)
        result["generated_sql"] = sql
        result["dropped_table"] = table
        return jsonify(result)
