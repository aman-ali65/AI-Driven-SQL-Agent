import os
import sqlite3
import pandas as pd
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

file_bp = Blueprint('file', __name__)

UPLOAD_FOLDER = "uploads"
DB_PATH = "database/data.db"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("database", exist_ok=True)

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clean_column_names(df):
    """
    Clean column names so they work in SQL.
    Example: "Student Name" → "student_name"
    """
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(' ', '_')
        .str.replace(r'[^\w]', '_', regex=True)
    )
    return df

def read_file(filepath, extension):
    if extension == 'csv':
        df = pd.read_csv(filepath)
    elif extension in ['xlsx', 'xls']:
        df = pd.read_excel(filepath)
    else:
        raise ValueError(f"Unsupported file type: {extension}")
    return df

def save_to_db(df, table_name):
    conn = sqlite3.connect(DB_PATH)
    df.to_sql(table_name, conn, if_exists='replace', index=False)
    conn.close()

@file_bp.route('/upload', methods=['POST'])
def upload_file():
    """
    Upload CSV or Excel and save to SQLite
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file found. Use key 'file'."}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Only CSV, XLSX, or XLS files are allowed"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    extension = filename.rsplit('.', 1)[1].lower()

    try:
        df = read_file(filepath, extension)
        df = clean_column_names(df)

        table_name = filename.rsplit('.', 1)[0].lower().replace('-', '_').replace(' ', '_')

        save_to_db(df, table_name)

        preview = df.head(5).to_dict(orient='records')

        return jsonify({
            "success": True,
            "message": f"File uploaded and saved as table '{table_name}'",
            "table_name": table_name,
            "columns": list(df.columns),
            "total_rows": len(df),
            "preview": preview
        })

    except Exception as e:
        return jsonify({"error": f"Failed to process file: {str(e)}"}), 500


@file_bp.route('/tables', methods=['GET'])
def list_tables():
    """
    List all tables in database
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        conn.close()

        return jsonify({"tables": tables})

    except Exception as e:
        return jsonify({"error": str(e)}), 500