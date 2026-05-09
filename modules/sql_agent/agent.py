"""
SQL Agent Routes Module

Registers /sql/* Flask routes directly on the app (no Blueprint).
Validates input, calls SQLAgentController, returns JSON with chart.
"""

from flask import request, jsonify
from modules.sql_agent.controller import SQLAgentController
from modules.sql_agent.validator import SQLValidator
from modules.visualizer.chart_generator import ChartGenerator


class SQLRoutes:
    """
    Registers Flask routes for the SQL Agent under /sql/*.

    Routes:
        POST /sql/query     -> NL question -> SQL -> result + chart
        GET  /sql/schema    -> Current database schema
        POST /sql/execute   -> Run raw SQL directly
        POST /sql/load-db   -> Load an existing .db file
    """

    def __init__(self, app, controller: SQLAgentController,
                 validator: SQLValidator, chart_gen: ChartGenerator):
        """
        Args:
            app:        Flask application instance.
            controller: SQLAgentController instance.
            validator:  SQLValidator instance.
            chart_gen:  ChartGenerator instance.
        """
        self.app        = app
        self.controller = controller
        self.validator  = validator
        self.chart_gen  = chart_gen

    def register(self):
        """Binds all SQL routes to the Flask app. Call once at startup."""
        self.app.add_url_rule("/sql/query",         "sql_query",      self.query,       methods=["POST"])
        self.app.add_url_rule("/sql/schema",        "sql_schema",     self.schema,      methods=["GET"])
        self.app.add_url_rule("/sql/execute",       "sql_execute",    self.execute,     methods=["POST"])
        self.app.add_url_rule("/sql/load-db",       "sql_load_db",    self.load_db,     methods=["POST"])
        self.app.add_url_rule("/sql/upload-db",     "sql_upload_db",  self.upload_db,   methods=["POST"])
        self.app.add_url_rule("/sql/databases",     "sql_databases",  self.list_databases, methods=["GET"])
        self.app.add_url_rule("/sql/delete-db/<filename>", "sql_delete_db", self.delete_db, methods=["DELETE"])
        self.app.add_url_rule("/sql/download/<path:filename>", "sql_download_any", self.download_any_db, methods=["GET"])
        self.app.add_url_rule("/sql/download-copy", "sql_download_copy", self.download_copy, methods=["GET"])

    def query(self):
        """
        POST /sql/query

        Accepts a plain English question. Generates SQL, validates safety,
        executes, and returns results with an interactive Plotly chart.

        Request JSON:
            { "question": "How many students scored above 80?", "auto_execute": true }

        Returns:
            JSON: status, question, generated_sql, answer, result, chart
        """
        data = request.get_json()
        if not data or "question" not in data:
            return jsonify({"error": "Provide a 'question' field."}), 400

        question     = data["question"]

        # Run the agent (handles schema fetching, SQL generation, execution, and final answer)
        agent_resp = self.controller.run_agent(question)

        if not agent_resp.get("success"):
            return jsonify({"status": "error", "error": agent_resp.get("error", "Agent failed")}), 500

        answer  = agent_resp.get("answer", "")
        sql     = agent_resp.get("sql")
        db_data = agent_resp.get("data")
        columns = agent_resp.get("columns")

        # Security Check: If SQL was executed, check if it was dangerous
        if sql and self.validator.is_dangerous(sql):
            return jsonify({
                "status":        "blocked",
                "generated_sql": sql,
                "message":       "Dangerous SQL blocked (DROP/DELETE/TRUNCATE)."
            })

        if getattr(self.controller, "custom_chart_b64", None):
            chart = {"type": "image", "src": f"data:image/png;base64,{self.controller.custom_chart_b64}"}
        else:
            chart = self.chart_gen.generate(db_data, sql) if db_data and sql else None

        result_dict = {
            "success": True,
            "data": db_data or [],
            "count": len(db_data) if db_data else 0,
            "columns": columns or []
        }

        return jsonify({
            "status": "success", 
            "question": question,
            "generated_sql": sql or "", 
            "answer": answer,
            "result": result_dict, 
            "chart": chart,
            "active_db_path": getattr(self.controller, 'db_path', None)
        })

    def schema(self):
        """
        GET /sql/schema
        Returns the current database schema string and table list.
        """
        schema_text = self.controller.get_schema()
        if not schema_text:
            return jsonify({"schema": "", "message": "No tables found."})
        return jsonify({"schema": schema_text})

    def execute(self):
        """
        POST /sql/execute
        Runs a raw SQL string directly. Blocked if dangerous.

        Request JSON: { "sql": "SELECT * FROM students LIMIT 10" }
        """
        data = request.get_json()
        if not data or "sql" not in data:
            return jsonify({"error": "Provide an 'sql' field."}), 400

        sql = data["sql"]
        if self.validator.is_dangerous(sql):
            return jsonify({"status": "blocked", "sql": sql, "message": "Dangerous SQL blocked."})

        result = self.controller.execute_sql(sql)
        chart  = self.chart_gen.generate(result.get("data"), sql) if result.get("data") else None
        return jsonify({"status": "success" if result["success"] else "error",
                        "sql": sql, "result": result, "chart": chart})

    def load_db(self):
        """
        POST /sql/load-db
        Loads an existing .db file as the active database.

        Request JSON: { "db_path": "C:/Users/HP/data/mydb.db" }
        """
        data = request.get_json()
        if not data or "db_path" not in data:
            return jsonify({"error": "Provide a 'db_path' field."}), 400
        result = self.controller.load_db_file(data["db_path"])
        return jsonify(result), 200 if result["success"] else 400

    def upload_db(self):
        """
        POST /sql/upload-db
        Accepts a .db or .sqlite file upload and connects to it.
        """
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded."}), 400
            
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected."}), 400
            
        if not (file.filename.endswith(".db") or file.filename.endswith(".sqlite")):
            return jsonify({"error": "Only .db or .sqlite files are accepted."}), 400
            
        import os
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename)
        os.makedirs("database", exist_ok=True)
        filepath = os.path.join("database", filename)
        file.save(filepath)
        
        result = self.controller.load_db_file(filepath)
        return jsonify(result), 200 if result["success"] else 400

    def download_copy(self):
        """
        GET /sql/download-copy
        Downloads the modified copy of the database (created by modify_database tool).
        Returns 404 if no modified copy exists yet.
        """
        import os
        from flask import send_file
        modified_path = getattr(self.controller, "modified_db_path", None)
        if not modified_path or not os.path.exists(modified_path):
            return jsonify({"error": "No modified database found. Use the agent to modify the database first."}), 404
        filename = os.path.basename(modified_path)
        return send_file(
            modified_path,
            as_attachment=True,
            download_name=filename,
            mimetype="application/octet-stream"
        )

    def download_any_db(self, filename):
        """
        GET /sql/download/<filename>
        Downloads any database file from the database/ directory.
        """
        import os
        from flask import send_file
        path = os.path.join("database", filename)
        if not os.path.exists(path):
            return jsonify({"error": "File not found"}), 404
        return send_file(
            path,
            as_attachment=True,
            download_name=filename,
            mimetype="application/octet-stream"
        )

    def list_databases(self):
        """
        GET /sql/databases
        Returns all .db and .sqlite files available to load.
        """
        import os
        roots = ["database", "uploads"]
        dbs = []
        seen = set()
        for db_dir in roots:
            if not os.path.exists(db_dir):
                continue
            for filename in os.listdir(db_dir):
                if not (filename.endswith(".db") or filename.endswith(".sqlite")):
                    continue
                path = os.path.join(db_dir, filename)
                key = os.path.normpath(path)
                if key in seen:
                    continue
                seen.add(key)
                dbs.append({"name": filename, "path": path.replace("\\", "/")})

        active_path = os.path.normpath(self.controller.db_path)
        active_name = os.path.basename(active_path)
        return jsonify({
            "databases": dbs,
            "active": {"name": active_name, "path": self.controller.db_path.replace("\\", "/")}
        })

    def delete_db(self, filename):
        """
        DELETE /sql/delete-db/<filename>
        Deletes a specific database file from uploads or database directories.
        """
        import os
        removed = False
        roots = ["database", "uploads"]
        for db_dir in roots:
            p = os.path.join(db_dir, filename)
            if os.path.exists(p):
                try:
                    os.remove(p)
                    removed = True
                except Exception as e:
                    return jsonify({"success": False, "error": str(e)}), 500
        
        if removed:
            # If we deleted the active DB, we should reset it or handle gracefully
            if os.path.basename(self.controller.db_path) == filename:
                self.controller.db_path = "database/data.db"
            return jsonify({"success": True, "removed": True, "filename": filename})
        else:
            return jsonify({"success": False, "error": "Database not found"}), 404
