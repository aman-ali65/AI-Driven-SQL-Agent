"""
File to Database Uploader Module

Handles CSV and Excel file uploads. Converts them into SQLite tables
on explicit user request (import_file). Provides unified deletion.

Flow (upload): Upload -> Save raw file only (no auto-import)
Flow (import): import_file(filename) -> Read -> Clean -> Save to SQLite
Flow (delete): delete_file(filename) -> Remove file + table + RAG embeddings
"""

import os
import sqlite3
import pandas as pd
from flask import request, jsonify
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}
RAG_EXTENSIONS = {"pdf", "pptx", "ppt"}
DB_EXTENSIONS = {"db", "sqlite"}


class FileUploader:
    """
    Manages raw file uploads, explicit imports to SQLite, and deletions.
    Column names are auto-cleaned to be SQL-safe on import.
    """

    def __init__(self, upload_folder: str, get_db_path, embeddings_folder: str = None):
        """
        Args:
            upload_folder:     Directory for uploaded files.
            get_db_path:       Callable returning the current active SQLite database path.
            embeddings_folder: Directory where RAG .npy/.json files are stored.
        """
        self.upload_folder     = upload_folder
        self.get_db_path       = get_db_path
        self.embeddings_folder = embeddings_folder or os.path.join(
            os.path.dirname(upload_folder), "embeddings"
        )
        os.makedirs(upload_folder, exist_ok=True)
        os.makedirs(self.embeddings_folder, exist_ok=True)
        # Ensure parent of active db exists
        parent = os.path.dirname(get_db_path())
        if parent:
            os.makedirs(parent, exist_ok=True)

    # ── helpers ───────────────────────────────────────────────────────────────

    def allowed_file(self, filename: str) -> bool:
        """Returns True if file extension is CSV, XLSX, or XLS."""
        return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

    def table_name_for_file(self, filename: str) -> str:
        """Returns the SQLite table name used for a CSV/Excel upload."""
        return filename.rsplit(".", 1)[0].lower().replace("-", "_").replace(" ", "_")

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
        """
        conn = sqlite3.connect(self.get_db_path())
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        conn.close()

    def list_tables(self) -> list:
        """Returns a list of all tables in the active database."""
        try:
            conn = sqlite3.connect(self.get_db_path())
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall() if not row[0].startswith("sqlite_")]
            conn.close()
            return tables
        except Exception:
            return []

    # ── core actions ──────────────────────────────────────────────────────────

    def list_uploaded_files(self) -> list:
        """
        Returns files present in uploads/ with their import status.
        Does NOT auto-import — import is explicit via import_file().
        """
        tables = set(self.list_tables())
        files = []
        for filename in sorted(os.listdir(self.upload_folder)):
            path = os.path.join(self.upload_folder, filename)
            if not os.path.isfile(path) or "." not in filename:
                continue
            ext = filename.rsplit(".", 1)[1].lower()
            kind = "other"
            table_name = None
            imported = False
            if ext in ALLOWED_EXTENSIONS:
                kind = "table_file"
                table_name = self.table_name_for_file(filename)
                imported = table_name in tables
            elif ext in RAG_EXTENSIONS:
                kind = "rag_file"
            elif ext in DB_EXTENSIONS:
                kind = "database"
            files.append({
                "filename": filename,
                "extension": ext,
                "kind": kind,
                "table_name": table_name,
                "imported": imported,
            })
        return files

    def import_file(self, filename: str) -> dict:
        """
        Explicitly import a raw CSV/XLSX file into the active SQLite database.
        Returns table info or an error dict.
        """
        path = os.path.join(self.upload_folder, filename)
        if not os.path.isfile(path):
            return {"success": False, "error": f"File '{filename}' not found."}
        ext = filename.rsplit(".", 1)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return {"success": False, "error": f"Unsupported extension '.{ext}'."}
        try:
            from modules.system_logger import SystemLogger
            df = self.read_file(path, ext)
            df = self.clean_column_names(df)
            table_name = self.table_name_for_file(filename)
            self.save_to_db(df, table_name)
            SystemLogger.log("SUCCESS", "FileUploader", f"Imported '{filename}' -> table '{table_name}' ({len(df)} rows)")
            return {
                "success":    True,
                "filename":   filename,
                "table_name": table_name,
                "rows":       len(df),
                "columns":    list(df.columns),
                "preview":    df.head(5).fillna("").to_dict(orient="records"),
            }
        except Exception as e:
            try:
                from modules.system_logger import SystemLogger
                SystemLogger.log("ERROR", "FileUploader", f"Import failed for '{filename}': {e}")
            except Exception:
                pass
            return {"success": False, "error": str(e)}

    def delete_file(self, filename: str) -> dict:
        """
        Unified delete: removes raw file, associated SQLite table, and RAG embeddings.
        Returns a summary of what was removed.
        """
        removed = {"file": False, "table": None, "embeddings": []}

        # 1. Delete raw file
        path = os.path.join(self.upload_folder, filename)
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed["file"] = True
            except Exception as e:
                removed["file_error"] = str(e)

        # 2. Drop SQLite table if this was a CSV/XLSX
        ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
        if ext in ALLOWED_EXTENSIONS:
            table_name = self.table_name_for_file(filename)
            existing = self.list_tables()
            if table_name in existing:
                try:
                    conn = sqlite3.connect(self.get_db_path())
                    conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                    conn.commit()
                    conn.close()
                    removed["table"] = table_name
                except Exception as e:
                    removed["table_error"] = str(e)

        # 3. Remove RAG embedding files (.npy and .json) matching base name
        base = os.path.splitext(filename)[0]
        for emb_ext in [".npy", ".json"]:
            emb_path = os.path.join(self.embeddings_folder, base + emb_ext)
            if os.path.isfile(emb_path):
                try:
                    os.remove(emb_path)
                    removed["embeddings"].append(base + emb_ext)
                except Exception:
                    pass

        try:
            from modules.system_logger import SystemLogger
            SystemLogger.log("INFO", "FileUploader", f"Deleted '{filename}': {removed}")
        except Exception:
            pass

        return removed


class FileRoutes:
    """
    Registers /file/* Flask routes on the app.

    Routes:
        POST   /file/upload              -> Save raw file (no auto-import)
        POST   /file/import/<filename>   -> Import CSV/XLSX into SQLite
        DELETE /file/delete/<filename>   -> Remove file + table + embeddings
        GET    /file/tables              -> List all tables in database
        GET    /file/uploads             -> List all raw uploaded files
    """

    def __init__(self, app, uploader: FileUploader):
        self.app      = app
        self.uploader = uploader

    def register(self):
        """Binds all routes. Call once at startup."""
        self.app.add_url_rule("/file/upload",                  "file_upload",  self.upload,      methods=["POST"])
        self.app.add_url_rule("/file/import/<filename>",       "file_import",  self.import_file, methods=["POST"])
        self.app.add_url_rule("/file/delete/<filename>",       "file_delete",  self.delete_file, methods=["DELETE"])
        self.app.add_url_rule("/file/tables",                  "file_tables",  self.tables,      methods=["GET"])
        self.app.add_url_rule("/file/uploads",                 "file_uploads", self.uploads,     methods=["GET"])

    # ── route handlers ────────────────────────────────────────────────────────

    def upload(self):
        """
        POST /file/upload
        Accepts CSV/Excel via multipart/form-data (key: 'file').
        Saves the raw file only — does NOT import to DB automatically.
        """
        if "file" not in request.files:
            return jsonify({"error": "No file. Use key 'file' in form-data."}), 400
        file = request.files["file"]
        if not file.filename:
            return jsonify({"error": "No file selected."}), 400

        filename = secure_filename(file.filename)
        ext      = filename.rsplit(".", 1)[1].lower() if "." in filename else ""

        # Accept CSV/XLSX/XLS plus RAG files (PDF/PPTX)
        allowed_all = ALLOWED_EXTENSIONS | RAG_EXTENSIONS | DB_EXTENSIONS
        if ext not in allowed_all:
            return jsonify({"error": f"File type '.{ext}' not accepted."}), 400

        filepath = os.path.join(self.uploader.upload_folder, filename)
        file.save(filepath)

        try:
            from modules.system_logger import SystemLogger
            SystemLogger.log("INFO", "FileUploader", f"Saved raw file '{filename}'")
        except Exception:
            pass

        return jsonify({
            "success":  True,
            "filename": filename,
            "message":  "File saved. Use the Import button to load it into the database.",
            "imported": False,
        })

    def import_file(self, filename):
        """POST /file/import/<filename> — Explicitly import to SQLite."""
        result = self.uploader.import_file(filename)
        if not result.get("success"):
            return jsonify(result), 400 if "not found" in result.get("error","") else 500
        return jsonify(result)

    def delete_file(self, filename):
        """DELETE /file/delete/<filename> — Unified removal."""
        removed = self.uploader.delete_file(filename)
        return jsonify({"success": True, "removed": removed})

    def tables(self):
        """GET /file/tables — All table names in the active database."""
        tables = self.uploader.list_tables()
        return jsonify({"tables": tables, "count": len(tables)})

    def uploads(self):
        """GET /file/uploads — All raw files in uploads/."""
        files = self.uploader.list_uploaded_files()
        return jsonify({"files": files, "count": len(files)})
