import sqlite3
import os
from flask import Blueprint, request, jsonify
import google.generativeai as genai
from dotenv import load_dotenv
from modules.visualizer.chart_generator import generate_chart

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-pro")

schema_bp = Blueprint('schema', __name__)
DB_PATH = "database/data.db"
os.makedirs("database", exist_ok=True)

def generate_schema_sql(user_request):
    """
    Send user's plain English schema request to AI.
    AI returns a CREATE TABLE / ALTER TABLE / DROP TABLE SQL.
    """
    prompt = f"""
You are a SQLite database expert. Convert the user's request into a valid SQLite DDL query.

USER REQUEST:
{user_request}

IMPORTANT RULES:
- Only generate CREATE TABLE, ALTER TABLE, or DROP TABLE statements
- Use TEXT, INTEGER, or REAL as column types (SQLite types)
- Return ONLY the SQL, no explanation, no markdown
- Make sure SQL is valid for SQLite

SQL:
"""
    response = model.generate_content(prompt)
    raw = response.text.strip()
    raw = raw.replace("```sql", "").replace("```", "").strip()
    return raw

def detect_dangerous_query(sql):
    upper_sql = sql.upper()
    dangerous_keywords = ["DROP", "DELETE", "TRUNCATE"]
    for keyword in dangerous_keywords:
        if keyword in upper_sql:
            return True
    return False

def execute_schema_sql(sql):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        conn.commit()
        conn.close()
        return {"success": True, "message": "SQL executed successfully"}
    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}

def get_full_schema():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    schema_info = {}
    for (table_name,) in tables:
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        schema_info[table_name] = [
            {"column": col[1], "type": col[2], "nullable": not col[3]}
            for col in columns
        ]
        
    conn.close()
    return schema_info

def generate_insights(results, query=""):
    if not results:
        return "No data to analyze."
        
    if isinstance(results, list) and len(results) > 0:
        columns = list(results[0].keys())
        rows_text = "\n".join([str(row) for row in results[:20]])
        data_summary = f"Columns: {', '.join(columns)}\nData (first {min(20, len(results))} rows):\n{rows_text}"
    else:
        data_summary = str(results)
        
    prompt = f"""
You are a data analyst. Analyze the following data and provide useful insights.

ORIGINAL QUERY (if available): {query}

DATA:
{data_summary}

Provide:
1. A brief summary of what the data shows
2. Key observations (min, max, averages if applicable)
3. Any interesting patterns or anomalies

Keep it short and easy to understand. Speak like a data analyst explaining to a student.

INSIGHTS:
"""
    response = model.generate_content(prompt)
    return response.text

@schema_bp.route('/modify', methods=['POST'])
def modify_schema():
    """
    POST /schema/modify
    Body: {
      "request": "Create a table called employees with name, age, department",
      "confirm": false
    }
    """
    data = request.get_json()
    if not data or 'request' not in data:
        return jsonify({"error": "Provide a 'request' describing what to do"}), 400
        
    user_request = data['request']
    confirm = data.get('confirm', False)
    
    sql = generate_schema_sql(user_request)
    is_dangerous = detect_dangerous_query(sql)
    
    if not confirm:
        return jsonify({
            "generated_sql": sql,
            "is_dangerous": is_dangerous,
            "message": "Review the SQL. Send with 'confirm': true to execute.",
            "warning": "⚠ This is a destructive operation! Be careful." if is_dangerous else None
        })
        
    result = execute_schema_sql(sql)
    result["generated_sql"] = sql
    return jsonify(result)

@schema_bp.route('/show', methods=['GET'])
def show_schema():
    """
    GET /schema/show
    Returns full schema with all tables and column details.
    """
    schema = get_full_schema()
    return jsonify({
        "tables": schema,
        "table_count": len(schema)
    })

@schema_bp.route('/insights', methods=['POST'])
def get_insights():
    """
    POST /schema/insights
    Body: { "results": [...], "query": "original SQL query" }
    Returns AI-generated insights + auto chart.
    """
    data = request.get_json()
    if not data or 'results' not in data:
        return jsonify({"error": "Provide 'results' (list of rows from SQL query)"})
        
    results = data['results']
    query = data.get('query', '')
    
    if not results:
        return jsonify({"insights": "No data provided to analyze."})
        
    insights = generate_insights(results, query)
    
    # Auto-generate chart from the results
    chart_path = generate_chart(
        results=results,
        query=query,
        filename="insights_chart"
    )
    
    return jsonify({
        "insights": insights,
        "rows_analyzed": len(results),
        "chart": chart_path
    })

@schema_bp.route('/drop', methods=['POST'])
def drop_table():
    """
    POST /schema/drop
    Body: { "table_name": "old_table", "confirm": true }
    """
    data = request.get_json()
    if not data or 'table_name' not in data:
        return jsonify({"error": "Provide 'table_name'"}), 400
        
    table_name = data['table_name']
    confirm = data.get('confirm', False)
    
    sql = f"DROP TABLE IF EXISTS {table_name};"
    
    if not confirm:
        return jsonify({
            "generated_sql": sql,
            "message": "Send 'confirm': true to permanently delete this table.",
            "warning": f"⚠ This will permanently delete table '{table_name}' and all its data!"
        })
        
    result = execute_schema_sql(sql)
    result["dropped_table"] = table_name
    return jsonify(result)
