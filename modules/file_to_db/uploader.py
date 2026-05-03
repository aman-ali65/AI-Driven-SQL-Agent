"""
File to Database Uploader Module

Handles CSV and Excel file uploads. Converts them into SQLite tables
so the SQL Agent can query them immediately.

Flow: Upload -> Read with pandas -> Clean column names -> Save to SQLite
"""

import os
import sqlite3
import pandas as pd
from flask import request, jsonify
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}


class FileUploader:
    """
    Reads CSV/Excel files and saves them as SQLite tables.
    Column names are auto-cleaned to be SQL-safe.
    """

    def __init__(self, upload_folder: str, get_db_path):
        """
        Args:
            upload_folder: Directory for uploaded files.
            get_db_path:   Callable returning the current active SQLite database path.
        """
        self.upload_folder = upload_folder
        self.get_db_path   = get_db_path
        os.makedirs(upload_folder, exist_ok=True)
        # Ensure parent of active db exists
        parent = os.path.dirname(get_db_path())
        if parent:
            os.makedirs(parent, exist_ok=True)

    def allowed_file(self, filename: str) -> bool:
        """Returns True if file extension is CSV, XLSX, or XLS."""
        return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

    def clean_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalizes column names to SQL-safe format.
        Example: "Student Name" -> "student_name"
        """
        df.columns = (
            df.columns.str.strip().str.lower()
            .str.replace(r"[^\w]", "_", regex=True)
        )
        return df

    def read_file(self, filepath: str, extension: str) -> pd.DataFrame:
        """
        Reads CSV or Excel into a DataFrame.
        - CSV  : tries multiple encodings automatically.
        - XLSX : uses openpyxl directly (bypasses pandas version check).
        - XLS  : uses xlrd engine via pandas.
        """
        if extension == "csv":
            for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
                try:
                    return pd.read_csv(filepath, encoding=enc)
                except UnicodeDecodeError:
                    continue
            return pd.read_csv(filepath, encoding="utf-8", errors="replace")

        elif extension == "xlsx":
            # Use openpyxl directly to bypass pandas' strict version check
            try:
                import openpyxl
                wb = openpyxl.load_workbook(filepath, data_only=True)
                ws = wb.active
                data = list(ws.values)
                if not data:
                    return pd.DataFrame()
                headers = [str(c) if c is not None else f"col_{i}" for i, c in enumerate(data[0])]
                return pd.DataFrame(data[1:], columns=headers)
            except Exception as e:
                raise ValueError(f"Cannot read .xlsx with openpyxl: {e}")

        elif extension == "xls":
            try:
                return pd.read_excel(filepath, engine="xlrd")
            except Exception as e:
                raise ValueError(f"Cannot read .xls with xlrd: {e}")

        raise ValueError(f"Unsupported file type: .{extension}")


    def save_to_db(self, df: pd.DataFrame, table_name: str):
        """
        Saves a DataFrame as a SQLite table. Replaces existing table.

        Args:
            df:         DataFrame to save.
            table_name: Name of the SQLite table.
        """
        conn = sqlite3.connect(self.get_db_path())
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        conn.close()

    def list_tables(self) -> list:
        """
        Returns a list of all tables in the active database.
        """
        try:
            conn = sqlite3.connect(self.get_db_path())
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall() if not row[0].startswith("sqlite_")]
            conn.close()
            return tables
        except Exception:
            return []


class FileRoutes:
    """
    Registers /file/* Flask routes on the app.

    Routes:
        POST /file/upload  -> Upload CSV/Excel -> SQLite table
        GET  /file/tables  -> List all tables in database
    """

    def __init__(self, app, uploader: FileUploader):
        """
        Args:
            app:      Flask application instance.
            uploader: FileUploader instance.
        """
        self.app      = app
        self.uploader = uploader

    def register(self):
        """Binds routes. Call once at startup."""
        self.app.add_url_rule("/file/upload", "file_upload", self.upload, methods=["POST"])
        self.app.add_url_rule("/file/tables", "file_tables", self.tables, methods=["GET"])

    def upload(self):
        """
        POST /file/upload

        Accepts CSV or Excel file via multipart/form-data (key: 'file').
        Saves it as a SQLite table named after the filename.

        Returns:
            JSON: success, table_name, columns, total_rows, preview (5 rows)
        """
        if "file" not in request.files:
            return jsonify({"error": "No file. Use key 'file' in form-data."}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected."}), 400
        if not self.uploader.allowed_file(file.filename):
            return jsonify({"error": "Only CSV, XLSX, XLS accepted."}), 400

        filename   = secure_filename(file.filename)
        filepath   = os.path.join(self.uploader.upload_folder, filename)
        file.save(filepath)

        extension  = filename.rsplit(".", 1)[1].lower()
        table_name = filename.rsplit(".", 1)[0].lower().replace("-", "_").replace(" ", "_")

        try:
            from modules.system_logger import SystemLogger
            SystemLogger.log("INFO", "FileUploader", f"Processing '{filename}' -> table '{table_name}'")
            df      = self.uploader.read_file(filepath, extension)
            df      = self.uploader.clean_column_names(df)
            self.uploader.save_to_db(df, table_name)
            SystemLogger.log("SUCCESS", "FileUploader", f"Saved '{table_name}' ({len(df)} rows, {len(df.columns)} cols)")
            return jsonify({
                "success":    True,
                "message":    f"Saved as table '{table_name}'.",
                "table_name": table_name,
                "columns":    list(df.columns),
                "total_rows": len(df),
                "preview":    df.head(5).to_dict(orient="records")
            })
        except Exception as e:
            from modules.system_logger import SystemLogger
            SystemLogger.log("ERROR", "FileUploader", f"Failed to process '{filename}': {e}")
            return jsonify({"error": str(e)}), 500

    def tables(self):
        """
        GET /file/tables
        Returns all table names in the database.
        """
        tables = self.uploader.list_tables()
        return jsonify({"tables": tables, "count": len(tables)})