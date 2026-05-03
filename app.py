"""
Main Flask application for QueryMind.

Run:
    python app.py
    http://localhost:5000
"""

from flask import Flask, render_template, jsonify

from modules.api_key_manager import APIKeyManager
from modules.sql_agent.controller import SQLAgentController
from modules.sql_agent.validator import SQLValidator
from modules.sql_agent.agent import SQLRoutes
from modules.file_to_db.uploader import FileUploader, FileRoutes
from modules.rag_system.rag import RAGSystem, RAGRoutes
from modules.schema_insights.schema_agent import SchemaAgent, SchemaRoutes
from modules.visualizer.chart_generator import ChartGenerator
from modules.system_logger import LogsRoutes

GEMINI_API_KEY = APIKeyManager(None).get_key()
DB_PATH = "database/data.db"
UPLOAD_FOLDER = "uploads"
EMBEDDINGS_FOLDER = "embeddings"


def create_app() -> Flask:
    app = Flask(__name__)

    chart_gen = ChartGenerator()
    validator = SQLValidator()

    sql_ctrl = SQLAgentController(db_path=DB_PATH, api_key=GEMINI_API_KEY)
    uploader = FileUploader(upload_folder=UPLOAD_FOLDER, get_db_path=lambda: sql_ctrl.db_path)
    rag_sys = RAGSystem(
        upload_folder=UPLOAD_FOLDER,
        embeddings_folder=EMBEDDINGS_FOLDER,
        api_key=GEMINI_API_KEY,
    )
    schema_agt = SchemaAgent(
        db_path=DB_PATH,
        api_key=GEMINI_API_KEY,
        get_db_path=lambda: sql_ctrl.db_path,
    )

    SQLRoutes(app, sql_ctrl, validator, chart_gen).register()
    FileRoutes(app, uploader).register()
    RAGRoutes(app, rag_sys).register()
    SchemaRoutes(app, schema_agt, chart_gen).register()
    LogsRoutes(app).register()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/health")
    def health():
        return jsonify({
            "status": "running",
            "message": "QueryMind AI SQL Agent is live.",
            "endpoints": {
                "sql": [
                    "/sql/query",
                    "/sql/schema",
                    "/sql/execute",
                    "/sql/load-db",
                    "/sql/upload-db",
                    "/sql/download-copy",
                ],
                "file": ["/file/upload", "/file/tables", "/file/uploads"],
                "rag": ["/rag/upload", "/rag/query", "/rag/documents"],
                "schema": ["/schema/modify", "/schema/show", "/schema/insights", "/schema/drop"],
            },
        })

    return app


if __name__ == "__main__":
    app = create_app()
    print("QueryMind is starting...")
    print("Open in browser: http://localhost:5000")
    app.run(debug=True, use_reloader=False)
