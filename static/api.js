/**
 * api.js — All Flask API calls in one place.
 * Base URL auto-detects the backend host.
 */

const API = (() => {
  const BASE = window.location.origin;

  async function request(method, path, body = null, isForm = false) {
    const opts = { method, headers: {} };
    if (body) {
      if (isForm) {
        opts.body = body;
      } else {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
      }
    }
    const res = await fetch(BASE + path, opts);
    return res.json();
  }

  return {
    /** POST /sql/query — natural language question */
    sqlQuery(question, autoExecute = true) {
      return request("POST", "/sql/query", { question, auto_execute: autoExecute });
    },

    /** GET /sql/schema — raw schema string */
    sqlSchema() {
      return request("GET", "/sql/schema");
    },

    /** POST /sql/execute — run raw SQL */
    sqlExecute(sql) {
      return request("POST", "/sql/execute", { sql });
    },

    /** POST /sql/load-db — load existing .db file by path */
    loadDb(dbPath) {
      return request("POST", "/sql/load-db", { db_path: dbPath });
    },

    /** POST /sql/upload-db — upload a .db file */
    uploadDb(file) {
      const form = new FormData();
      form.append("file", file);
      return request("POST", "/sql/upload-db", form, true);
    },

    /** POST /file/upload — upload CSV / Excel */
    uploadFile(file) {
      const form = new FormData();
      form.append("file", file);
      return request("POST", "/file/upload", form, true);
    },

    /** GET /file/tables — list all SQLite tables */
    listTables() {
      return request("GET", "/file/tables");
    },

    /** GET /sql/databases — list all database files */
    listDatabases() {
      return request("GET", "/sql/databases");
    },

    /** POST /rag/upload — index PDF / PPTX */
    ragUpload(file) {
      const form = new FormData();
      form.append("file", file);
      return request("POST", "/rag/upload", form, true);
    },

    /** POST /rag/query — ask question from document */
    ragQuery(question, document) {
      return request("POST", "/rag/query", { question, document });
    },

    /** GET /rag/documents — list indexed docs */
    ragDocuments() {
      return request("GET", "/rag/documents");
    },

    /** GET /schema/show — full schema per table */
    schemaShow() {
      return request("GET", "/schema/show");
    },

    /** POST /schema/modify — preview or execute DDL */
    schemaModify(userRequest, confirm = false) {
      return request("POST", "/schema/modify", { request: userRequest, confirm });
    },

    /** POST /schema/insights — AI insights from result rows */
    schemaInsights(results, query = "") {
      return request("POST", "/schema/insights", { results, query });
    },

    /** POST /schema/drop — drop a table */
    schemaDrop(tableName, confirm = false) {
      return request("POST", "/schema/drop", { table_name: tableName, confirm });
    },
  };
})();
