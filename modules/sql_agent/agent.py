# agent.py
# =====================================================================
# PURPOSE:
# This file defines the Flask API routes for the SQL Agent module.
# All incoming HTTP requests to /sql/* are handled here.
#
# Routes:
#   POST /sql/query   -> Accept user question, generate SQL, run it
#   GET  /sql/schema  -> Show all current database tables and columns
# =====================================================================

from flask import Blueprint, request, jsonify
from modules.sql_agent.controller import get_schema, generate_sql, execute_sql
from modules.sql_agent.validator import is_dangerous
from modules.visualizer.chart_generator import generate_chart

# Create a Blueprint — this is a mini Flask app for the SQL module
sql_bp = Blueprint('sql', __name__)


# ── Route 1: Main Query Endpoint ──────────────────────────────────────────────

@sql_bp.route('/query', methods=['POST'])
def query():
    """
    POST /sql/query

    Accepts a plain English question, generates a SQL query using AI,
    validates it for safety, and optionally executes it.

    Request Body (JSON):
    {
        "question": "Show students with marks above 80",
        "auto_execute": false
    }

    auto_execute options:
        false  ->  Only generate and return the SQL (for human review). DEFAULT.
        true   ->  Generate the SQL and immediately run it on the database.

    Possible Responses:

    1. Missing question field:
       { "error": "Please provide a 'question'..." }

    2. No tables in database yet:
       { "error": "No tables found. Please upload a file first." }

    3. Dangerous query detected (DROP/DELETE/etc):
       { "status": "blocked", "generated_sql": "...", "explanation": "..." }

    4. auto_execute = false (approval required):
       { "status": "approval_required", "generated_sql": "...", "explanation": "..." }

    5. auto_execute = true — query executed successfully:
       { "status": "success", "generated_sql": "...", "result": {...}, "chart": "..." }
    """

    # Step 1: Parse the incoming request body
    data = request.get_json()

    if not data or 'question' not in data:
        return jsonify({
            "error": "Please provide a 'question' in the request body.",
            "example": {"question": "Show all students", "auto_execute": False}
        }), 400

    user_question = data['question']
    auto_execute = data.get('auto_execute', False)  # Default: False (safe mode)

    # Step 2: Read the current database schema
    schema = get_schema()

    if not schema:
        return jsonify({
            "error": "No tables found in the database.",
            "tip": "Please upload a CSV or Excel file first using POST /file/upload"
        }), 404

    # Step 3: Generate SQL using the AI
    try:
        generated_sql = generate_sql(user_question, schema)
    except Exception as e:
        return jsonify({
            "error": f"Failed to generate SQL from AI: {str(e)}",
            "tip": "Check that your API key is correct in the .env file and AI_PROVIDER is set."
        }), 500

    # Step 4: Safety check — block dangerous operations
    if is_dangerous(generated_sql):
        return jsonify({
            "status": "blocked",
            "generated_sql": generated_sql,
            "explanation": (
                "This query contains a dangerous operation (DROP / DELETE / TRUNCATE / ALTER) "
                "and has been blocked for safety. "
                "If you intended this, use POST /schema/modify with 'confirm': true instead."
            )
        })

    # Step 5: If auto_execute is false, return SQL for human review
    if not auto_execute:
        return jsonify({
            "status": "approval_required",
            "generated_sql": generated_sql,
            "explanation": (
                "The SQL query has been generated. Please review it. "
                "To run it, send the same request again with 'auto_execute': true."
            )
        })

    # Step 6: Execute the SQL on the database
    result = execute_sql(generated_sql)

    if not result["success"]:
        return jsonify({
            "status": "error",
            "generated_sql": generated_sql,
            "error": result["error"],
            "tip": "Use GET /sql/schema to verify the table and column names are correct."
        }), 500

    # Step 7: Auto-generate a chart if the result contains data
    chart_path = None
    if result["data"]:
        try:
            chart_path = generate_chart(
                results=result["data"],
                query=generated_sql,
                filename="sql_result"
            )
        except Exception:
            chart_path = None  # Chart failure should not break the response

    # Step 8: Return the full response
    return jsonify({
        "status": "success",
        "generated_sql": generated_sql,
        "result": result,
        "chart": chart_path  # Path to chart image, or None if no chart was made
    })


# ── Route 2: Schema Viewer ────────────────────────────────────────────────────

@sql_bp.route('/schema', methods=['GET'])
def show_schema():
    """
    GET /sql/schema

    Returns all current tables and their columns from the database.
    Useful for verifying what data has been uploaded.

    Response (when tables exist):
    {
        "schema": "Table: students | Columns: name, age, score\n..."
    }

    Response (when no tables exist):
    {
        "schema": "",
        "message": "No tables found in the database.",
        "tip": "Upload a CSV or Excel file using POST /file/upload first."
    }
    """
    schema = get_schema()

    if not schema:
        return jsonify({
            "schema": "",
            "message": "No tables found in the database.",
            "tip": "Upload a CSV or Excel file using POST /file/upload first."
        })

    return jsonify({"schema": schema})
