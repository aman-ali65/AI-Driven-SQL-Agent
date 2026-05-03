"""
System Logger Module

Manages application-wide logging to a text file.
Used for debugging LLM inputs, generated SQL, and system errors.
"""

import os
import datetime
from flask import render_template , jsonify

LOG_FILE = "app_logs.txt"

class SystemLogger:
    @staticmethod
    def log(level: str, module: str, message: str):
        """
        Appends a log entry to app_logs.txt.
        
        Args:
            level: 'INFO', 'ERROR', 'WARNING', 'LLM_PROMPT', 'LLM_RESPONSE', 'SQL'
            module: The name of the module/component logging this.
            message: The log message.
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] [{module}]\n{message}\n" + ("-" * 60) + "\n"
        
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Failed to write log: {e}")

    @staticmethod
    def read_logs() -> str:
        """Reads all logs from the text file."""
        if not os.path.exists(LOG_FILE):
            return "No logs available yet."
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading logs: {e}"

    @staticmethod
    def clear_logs():
        """Clears the log file."""
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass


class LogsRoutes:
    """Registers /logs routes to view system logs via an API and a frontend page."""
    
    def __init__(self, app):
        self.app = app

    def register(self):
        self.app.add_url_rule("/logs/api", "logs_api", self.api, methods=["GET"])
        self.app.add_url_rule("/logs/clear", "logs_clear", self.clear, methods=["POST"])
        self.app.add_url_rule("/logs", "logs_page", self.page, methods=["GET"])

    def api(self):
        return jsonify({"logs": SystemLogger.read_logs()})

    def clear(self):
        SystemLogger.clear_logs()
        return jsonify({"success": True})

    def page(self):
        
        return render_template("logs.html")
