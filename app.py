from flask import Flask
from flask_cors import CORS
# Import all route blueprints
from modules.sql_agent.agent import sql_bp
from modules.file_to_db.uploader import file_bp
from modules.rag_system.rag import rag_bp
from modules.schema_insights.schema_agent import schema_bp
app = Flask(__name__)
CORS(app) # Allow all origins (needed for frontend testing)
# Register all blueprints (modules)
app.register_blueprint(sql_bp, url_prefix='/sql')
app.register_blueprint(file_bp, url_prefix='/file')
app.register_blueprint(rag_bp, url_prefix='/rag')
app.register_blueprint(schema_bp, url_prefix='/schema')
if __name__ == '__main__':
app.run(debug=True, port=5000)