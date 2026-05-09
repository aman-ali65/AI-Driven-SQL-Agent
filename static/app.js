/**
 * app.js — Main application logic, state, event handlers, init.
 * Depends on: api.js, ui.js (loaded before this file)
 */
const APP = (() => {
  // ── State ──────────────────────────────────────────────────────────────
  let ragMode = false;        // true = RAG query, false = SQL query
  let activeRagDoc = null;    // currently selected RAG document name
  let conversations = [];     // [{id, name, messages:[]}]
  let activeChatId = null;
  let activeDbName = localStorage.getItem("qm_active_db") || "data.db"; // persisted DB name
  let activeDbPath = localStorage.getItem("qm_active_db_path") || `database/${activeDbName}`;

  const pendingFiles  = [];   // files queued in upload modal
  let schemaSQL = null;       // last generated DDL preview

  // ── Toaster ──────────────────────────────────────────────────────────────
  function toast(message, type = "info", duration = 3500) {
    const container = document.getElementById("toasterContainer");
    if (!container) return;
    const icons = { success: "check_circle", error: "error", info: "info", warn: "warning" };
    const colors = { success: "#22c55e", error: "#ef4444", info: "#6366f1", warn: "#f59e0b" };
    const t = document.createElement("div");
    t.style.cssText = `display:flex;align-items:center;gap:10px;background:rgba(15,17,26,0.97);border:1px solid rgba(255,255,255,0.1);color:#e2e8f0;padding:12px 18px;border-radius:12px;font-size:13px;font-family:Inter,sans-serif;box-shadow:0 8px 32px rgba(0,0,0,0.4);pointer-events:auto;cursor:pointer;border-left:3px solid ${colors[type] || colors.info};min-width:260px;max-width:380px;`;
    t.innerHTML = `<span class="material-icons-round" style="font-size:18px;color:${colors[type]}">${icons[type]}</span><span style="flex:1">${message}</span><span class="material-icons-round" style="font-size:16px;color:#64748b">close</span>`;
    t.onclick = () => t.remove();
    container.appendChild(t);
    setTimeout(() => { t.style.opacity="0"; t.style.transition="opacity 0.3s"; setTimeout(() => t.remove(), 300); }, duration);
  }

  // ── Utilities ──────────────────────────────────────────────────────────
  function genId() { return Date.now().toString(36) + Math.random().toString(36).slice(2); }

  function setBusy(busy) {
    const btn = document.getElementById("sendBtn");
    if (btn) { btn.disabled = busy; }
  }

  function updateDbBadge(name, count, path=null) {
    if (name) { activeDbName = name; localStorage.setItem("qm_active_db", name); }
    if (path) { activeDbPath = path; localStorage.setItem("qm_active_db_path", path); }
    const displayName = name || activeDbName;
    const selector = document.getElementById("dbSelector");
    const hc = document.getElementById("headerTableCount");
    if (selector) {
      selector.dataset.activeName = displayName;
      selector.value = activeDbPath;
    }
    if (hc) hc.textContent = count != null ? `${count} tables` : "";
    
    // Auto refresh UI so the new active DB is highlighted in the sidebar
    if (name) {
      setTimeout(refreshKnowledgeBase, 100);
    }
  }

  function renderDbSelector(dbs, active) {
    const selector = document.getElementById("dbSelector");
    if (!selector) return;
    const list = (dbs || []).map(db => typeof db === "string" ? { name: db, path: `database/${db}` } : db);
    if (active?.path) {
      activeDbPath = active.path;
      activeDbName = active.name || active.path.split(/[\\/]/).pop();
      localStorage.setItem("qm_active_db", activeDbName);
      localStorage.setItem("qm_active_db_path", activeDbPath);
    }
    selector.innerHTML = list.map(db =>
      `<option value="${db.path}">${db.name}</option>`
    ).join("");
    if (activeDbPath && !list.find(db => db.path === activeDbPath)) {
      selector.insertAdjacentHTML("afterbegin", `<option value="${activeDbPath}">${activeDbName}</option>`);
    }
    selector.value = activeDbPath;
  }

  // ── Conversations ───────────────────────────────────────────────────────
  function newChat() {
    const id = genId();
    conversations.unshift({ id, name: "New Chat", messages: [] });
    activeChatId = id;
    document.getElementById("chatTitle").textContent = "New Chat";
    document.getElementById("chatMessages").innerHTML =
      `<div class="welcome-state" id="welcomeState">
        <div class="welcome-icon"><span class="material-icons-round">auto_awesome</span></div>
        <h2 class="welcome-title">Ask anything about your data</h2>
        <p class="welcome-sub">Upload a CSV or load a database, then ask in plain English.</p>
        <div class="quick-prompts">
          <button class="quick-prompt-btn" onclick="usePrompt('Show me all records')">Show all records</button>
          <button class="quick-prompt-btn" onclick="usePrompt('What is the average score?')">Average score</button>
          <button class="quick-prompt-btn" onclick="usePrompt('Show top 5 results')">Top 5 results</button>
          <button class="quick-prompt-btn" onclick="usePrompt('Count rows by category')">Count by category</button>
        </div>
      </div>`;
    UI.renderConversations(conversations, activeChatId, switchChat);
    saveConversations();
  }

  function switchChat(id) {
    activeChatId = id;
    const conv = conversations.find(c => c.id === id);
    if (!conv) return;
    document.getElementById("chatTitle").textContent = conv.name;
    document.getElementById("chatMessages").innerHTML = "";
    conv.messages.forEach(m => {
      if (m.role === "user") {
        UI.addUserBubble(m.text);
      } else {
        if (m.data) {
          UI.addTypingCard();
          UI.replaceTypingCard(m.data);
        } else {
          UI.addAITextCard(m.text);
        }
      }
    });
    UI.renderConversations(conversations, activeChatId, switchChat);
  }

  function saveConversationMsg(role, text, data = null) {
    const conv = conversations.find(c => c.id === activeChatId);
    if (conv) {
      conv.messages.push({ role, text, data });
      if (role === "user" && conv.name === "New Chat") {
        conv.name = text.slice(0, 32) + (text.length > 32 ? "…" : "");
        document.getElementById("chatTitle").textContent = conv.name;
        UI.renderConversations(conversations, activeChatId, switchChat);
      }
    }
    saveConversations();
  }

  function saveConversations() {
    try { localStorage.setItem("qm_convs", JSON.stringify(conversations)); } catch {}
  }

  function loadConversations() {
    try {
      const s = localStorage.getItem("qm_convs");
      if (s) { conversations = JSON.parse(s); }
    } catch {}
    if (!conversations.length) newChat();
    else {
      activeChatId = conversations[0].id;
      UI.renderConversations(conversations, activeChatId, switchChat);
    }
  }

  // ── Send Query ─────────────────────────────────────────────────────────
  async function sendQuery() {
    const input = document.getElementById("queryInput");
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    input.style.height = "auto";

    UI.hideWelcome();
    UI.addUserBubble(question);
    saveConversationMsg("user", question);
    UI.addTypingCard();
    setBusy(true);

    try {
      let data;
      if (ragMode && activeRagDoc) {
        data = await API.ragQuery(question, activeRagDoc);
      } else {
        const autoEx = document.getElementById("autoExecToggle")?.checked ?? true;
        data = await API.sqlQuery(question, autoEx);
      }
      UI.replaceTypingCard(data);
      saveConversationMsg("ai", data.answer || data.message || "", data);
      
      // Auto-refresh schema if the AI modified the DB and switched to a copy
      if (data.active_db_path && data.active_db_path !== activeDbPath) {
        const name = data.active_db_path.split(/[\\/]/).pop();
        updateDbBadge(name, null, data.active_db_path);
        await loadSchemaPanel();
        await refreshKnowledgeBase();
      }
    } catch (e) {
      UI.replaceTypingCard({ error: "Network error: " + e.message });
    } finally {
      setBusy(false);
    }
  }

  // ── UI event helpers ───────────────────────────────────────────────────
  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendQuery(); }
  }

  function autoResize(el) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 140) + "px";
  }

  function usePrompt(text) {
    const inp = document.getElementById("queryInput");
    if (inp) { inp.value = text; inp.focus(); }
  }

  function toggleSidebar() {
    const s = document.getElementById("sidebar");
    if (s) s.style.display = s.style.display === "none" ? "" : "none";
  }

  function toggleRagMode() {
    ragMode = !ragMode;
    const pill = document.getElementById("ragTogglePill");
    if (pill) {
      pill.textContent = ragMode ? "Mode: RAG" : "Mode: SQL";
      pill.style.background = ragMode ? "rgba(124,58,237,.2)" : "rgba(255,255,255,.05)";
      pill.style.color = ragMode ? "#a78bfa" : "var(--muted)";
    }
    const inp = document.getElementById("queryInput");
    if (inp) {
      inp.placeholder = ragMode 
        ? `Ask a question from "${activeRagDoc || "a document"}"...` 
        : "Ask anything about your data...";
    }
    toast(`RAG Mode ${ragMode ? "Enabled" : "Disabled"}`, ragMode ? "success" : "info");
  }

  function openModal(id) {
    const m = document.getElementById(id);
    if (m) m.style.display = "flex";
  }

  function closeModal(id) {
    const m = document.getElementById(id);
    if (m) m.style.display = "none";
  }

  function startRagQuery(docName) {
    activeRagDoc = docName;
    ragMode = true;
    const pill = document.getElementById("ragTogglePill");
    if (pill) pill.textContent = "Mode: RAG";
    const inp = document.getElementById("queryInput");
    if (inp) { inp.placeholder = `Ask from "${docName}"...`; inp.focus(); }
  }

  function exportChat(format = 'txt') {
    closeHeaderMenu();
    const msgs = document.getElementById("chatMessages");
    if (!msgs) return;
    
    let out = "";
    let mime = "";
    let filename = "";
    
    if (format === 'json') {
      const chatData = [];
      Array.from(msgs.querySelectorAll(".user-bubble, .ai-text, .sql-code")).forEach(el => {
        if (el.className.includes("user-bubble")) chatData.push({ role: "user", content: el.textContent });
        else if (el.className.includes("sql-code")) chatData.push({ role: "ai_sql", content: el.textContent });
        else chatData.push({ role: "ai", content: el.textContent });
      });
      out = JSON.stringify(chatData, null, 2);
      mime = "application/json";
      filename = "chat-export.json";
    } else {
      out = Array.from(msgs.querySelectorAll(".user-bubble,.ai-text,.sql-code"))
        .map(el => el.className.includes("user-bubble") ? "YOU: "+el.textContent : el.textContent)
        .join("\n\n---\n\n");
      mime = "text/plain";
      filename = "chat-export.txt";
    }
    
    const a = document.createElement("a");
    a.href = `data:${mime};charset=utf-8,` + encodeURIComponent(out);
    a.download = filename;
    a.click();
  }

  function toggleHeaderMenu(e) {
    if(e) e.stopPropagation();
    const menu = document.getElementById("headerDropdown");
    if(menu) menu.style.display = menu.style.display === "none" ? "block" : "none";
  }

  function closeHeaderMenu() {
    const menu = document.getElementById("headerDropdown");
    if(menu) menu.style.display = "none";
  }

  function downloadActiveDatabase() {
    closeHeaderMenu();
    if (!activeDbPath) return;
    const filename = activeDbPath.split(/[\\/]/).pop();
    window.location.href = `/sql/download/${filename}`;
  }

  // Click backdrop to close modals and header menu
  document.addEventListener("click", e => {
    if (e.target.classList.contains("modal-backdrop")) e.target.style.display = "none";
    const menu = document.getElementById("headerDropdown");
    if(menu && e.target.closest(".chat-header-right") == null) menu.style.display = "none";
  });

  // ── File Upload ────────────────────────────────────────────────────────
  function setupDropzone() {
    const dz = document.getElementById("dropzone");
    const fi = document.getElementById("fileInput");
    if (!dz || !fi) return;

    dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("drag-over"); });
    dz.addEventListener("dragleave", () => dz.classList.remove("drag-over"));
    dz.addEventListener("drop", e => {
      e.preventDefault(); dz.classList.remove("drag-over");
      addFilesToQueue([...e.dataTransfer.files]);
    });
    fi.addEventListener("change", () => addFilesToQueue([...fi.files]));
  }

  function addFilesToQueue(files) {
    files.forEach(f => { if (!pendingFiles.find(p => p.name === f.name)) pendingFiles.push(f); });
    renderUploadList();
  }

  function renderUploadList() {
    const list = document.getElementById("uploadFileList");
    if (!list) return;
    if (!pendingFiles.length) { list.style.display = "none"; return; }
    list.style.display = "flex";
    list.innerHTML = pendingFiles.map((f, i) => {
      const ext = f.name.split(".").pop().toLowerCase();
      const isRAG = ["pdf","pptx","ppt"].includes(ext);
      const badge = isRAG
        ? `<span style="font-size:10px;background:rgba(124,58,237,.2);color:#a78bfa;padding:2px 6px;border-radius:8px;flex-shrink:0">RAG</span>`
        : `<span style="font-size:10px;background:rgba(22,163,74,.2);color:#4ade80;padding:2px 6px;border-radius:8px;flex-shrink:0">SQL Table</span>`;
      return `<div class="upload-row" id="urow-${i}">
        <span class="material-icons-round" style="font-size:16px;color:var(--muted)">${isRAG ? "description" : "table_chart"}</span>
        <span class="upload-row-name">${f.name}</span>
        ${badge}
        <span class="upload-row-status" id="ustatus-${i}">Ready</span>
        <button class="icon-btn" onclick="APP._removeFile(${i})"><span class="material-icons-round" style="font-size:14px">close</span></button>
      </div>`;
    }).join("");
  }

  function _removeFile(i) { pendingFiles.splice(i, 1); renderUploadList(); }

  async function uploadSelectedFiles() {
    if (!pendingFiles.length) { toast("No files selected.", "warn"); return; }
    let successCount = 0, failCount = 0;
    for (let i = 0; i < pendingFiles.length; i++) {
      const statusEl = document.getElementById(`ustatus-${i}`);
      if (statusEl) statusEl.innerHTML = `<div class="progress-bar-wrap"><div class="progress-bar-fill" style="width:60%"></div></div>`;
      try {
        const ext = pendingFiles[i].name.split(".").pop().toLowerCase();
        let res;
        if (["pdf","pptx","ppt"].includes(ext)) {
          res = await API.ragUpload(pendingFiles[i]);
          if (res.success || res.chunks_count) {
            if (statusEl) statusEl.textContent = `RAG · ${res.chunks_count || 0} chunks`;
            successCount++;
          } else {
            if (statusEl) statusEl.textContent = "Failed";
            failCount++;
          }
        } else {
          res = await API.uploadFile(pendingFiles[i]);
          if (res.success) {
            if (statusEl) statusEl.textContent = `Saved · click Import to load`;
            successCount++;
          } else {
            if (statusEl) statusEl.textContent = "Failed";
            failCount++;
          }
        }
      } catch(e) {
        if (statusEl) statusEl.textContent = "Error";
        failCount++;
      }
    }
    pendingFiles.length = 0;
    closeModal("uploadModal");

    // Refresh KB — files are now in uploads/ but NOT yet imported
    await refreshKnowledgeBase();
    if (successCount > 0) {
      toast(`✅ ${successCount} file(s) uploaded!`, "success");
      UI.addAITextCard(`✅ **${successCount} file(s)** uploaded.\n\n- 📊 **CSV/Excel** → click **Import** in the sidebar to load into the database\n- 📄 **PDF/PPTX** → indexed for RAG (use "Ask →" in the sidebar)`);
    }
    if (failCount > 0) toast(`❌ ${failCount} file(s) failed to upload.`, "error");
  }

  // ── Upload .db File ────────────────────────────────────────────────────
  async function uploadDatabase() {
    const input = document.getElementById("dbFileInput");
    if (!input || !input.files.length) {
      toast("Please select a .db or .sqlite file first.", "warn"); return;
    }
    const file = input.files[0];
    toast(`Uploading ${file.name}...`, "info", 2000);
    try {
      const res = await API.uploadDb(file);
      closeModal("loadDbModal");
      if (res.success) {
        updateDbBadge(file.name, null, res.db_path || `database/${file.name}`);
        toast(`Database "${file.name}" loaded!`, "success");
        UI.addAITextCard(`✅ Database **${file.name}** is now active. Start asking questions!`);
        await loadSchemaPanel();
      } else {
        toast(`Failed: ${res.error || "Unknown error"}`, "error");
      }
    } catch(e) {
      toast(`Network error: ${e.message}`, "error");
    }
  }

  // ── Load DB by path (kept for programmatic use) ────────────────────────
  async function loadDatabase() {
    const path = document.getElementById("dbPathInput")?.value.trim();
    if (!path) return;
    await switchDatabase(path.split("/").pop(), path);
  }

  async function switchDatabase(filename, fullPath=null) {
    const path = fullPath || `database/${filename}`;
    toast(`Switching to ${filename}...`, "info", 2000);
    const res = await API.loadDb(path);
    closeModal("loadDbModal");
    if (res.success) {
      updateDbBadge(filename, null, res.db_path || path);
      toast(`Database loaded!`, "success");
      UI.addAITextCard(`✅ Active database switched to **${filename}**.`);
      await loadSchemaPanel();
      await refreshKnowledgeBase();
    } else {
      toast(`Failed to load: ${res.error}`, "error");
    }
  }

  async function switchDatabaseFromHeader(path) {
    if (!path) return;
    const filename = path.split(/[\\/]/).pop();
    await switchDatabase(filename, path);
  }

  // ── Schema Modify ──────────────────────────────────────────────────────
  async function previewSchema() {
    const req = document.getElementById("schemaRequestInput")?.value.trim();
    if (!req) return;
    const res = await API.schemaModify(req, false);
    schemaSQL = res.generated_sql;
    const box = document.getElementById("schemaPreviewBox");
    const sqlEl = document.getElementById("schemaPreviewSQL");
    const warnEl = document.getElementById("schemaDangerWarn");
    const execBtn = document.getElementById("schemaExecuteBtn");
    if (box) box.style.display = "block";
    if (sqlEl) sqlEl.textContent = schemaSQL;
    if (warnEl) warnEl.style.display = res.is_dangerous ? "flex" : "none";
    if (execBtn) execBtn.style.display = "inline-flex";
  }

  async function executeSchema() {
    const req = document.getElementById("schemaRequestInput")?.value.trim();
    if (!req) return;
    const res = await API.schemaModify(req, true);
    closeModal("schemaModal");
    schemaSQL = null;
    document.getElementById("schemaPreviewBox").style.display = "none";
    document.getElementById("schemaExecuteBtn").style.display = "none";
    if (res.success) {
      UI.addAITextCard(`✅ Schema updated.\n${res.generated_sql}`);
      await loadSchemaPanel();
    } else {
      UI.addAITextCard(`❌ Schema error: ${res.error}`, true);
    }
  }

  // ── Import CSV/XLSX into DB (explicit, user-triggered) ─────────────────
  async function importFile(filename) {
    toast(`Importing ${filename}…`, "info", 2000);
    try {
      const res = await fetch(`/file/import/${encodeURIComponent(filename)}`, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        toast(`✅ Imported "${data.table_name}" (${data.rows} rows)`, "success");
        UI.addAITextCard(`✅ **${filename}** imported as table \`${data.table_name}\` (${data.rows} rows, ${data.columns.length} columns).\n\nYou can now query it!`);
        try { await API.loadDb(activeDbPath); } catch {}
        await refreshKnowledgeBase();
        await loadSchemaPanel();
      } else {
        toast(`❌ Import failed: ${data.error}`, "error");
      }
    } catch (e) {
      toast(`❌ Import error: ${e.message}`, "error");
    }
  }

  // ── Delete knowledge-base item (file / rag doc / database) ─────────────
  async function deleteItem(type, name) {
    const labels = { file: "file", rag: "RAG document", db: "database" };
    const confirmed = confirm(`Delete ${labels[type] || "item"} "${name}"?\nThis will remove the file, any database table, and all embeddings.`);
    if (!confirmed) return;

    const url = type === "file" ? `/file/delete/${encodeURIComponent(name)}`
              : type === "rag"  ? `/rag/delete/${encodeURIComponent(name)}`
              : `/sql/delete-db/${encodeURIComponent(name)}`;
    try {
      const res = await fetch(url, { method: "DELETE" });
      const data = await res.json();
      if (data.success || data.removed) {
        toast(`🗑️ "${name}" deleted.`, "success");
        await refreshKnowledgeBase();
        await loadSchemaPanel();
      } else {
        toast(`❌ Delete failed: ${JSON.stringify(data)}`, "error");
      }
    } catch (e) {
      toast(`❌ Delete error: ${e.message}`, "error");
    }
  }

  // ── Data Refresh ───────────────────────────────────────────────────────
  async function loadSchemaPanel() {
    try {
      const data = await API.schemaShow();
      UI.renderSchema(data);
      const tableCount = Object.keys(data.tables||{}).length;
      updateDbBadge(null, tableCount);
    } catch {}
  }

  async function refreshKnowledgeBase() {
    try {
      const [tablesRes, docsRes, dbsRes, uploadsRes] = await Promise.all([
        API.listTables(), API.ragDocuments(), API.listDatabases(), API.listUploads()
      ]);
      renderDbSelector(dbsRes.databases, dbsRes.active);
      UI.renderKnowledgeBase(tablesRes.tables, docsRes.documents, dbsRes.databases, uploadsRes.files, activeDbPath);
      UI.renderRagDocs(docsRes.documents, uploadsRes.files);
    } catch {}
  }

  // ── Profile Setup ──────────────────────────────────────────────────────
  function setupUserProfile() {
    const nameEl = document.getElementById("userNameEdit");
    const roleEl = document.getElementById("userRoleEdit");
    const avatarEl = document.getElementById("userAvatarBtn");

    if (nameEl) {
      nameEl.textContent = localStorage.getItem("qm_user_name") || "Hassan";
      nameEl.addEventListener("blur", () => {
        localStorage.setItem("qm_user_name", nameEl.textContent.trim());
        if (avatarEl) avatarEl.textContent = nameEl.textContent.trim().substring(0, 2).toUpperCase();
      });
    }
    if (roleEl) {
      roleEl.textContent = localStorage.getItem("qm_user_role") || "Admin";
      roleEl.addEventListener("blur", () => localStorage.setItem("qm_user_role", roleEl.textContent.trim()));
    }
    if (avatarEl) {
      avatarEl.textContent = (localStorage.getItem("qm_user_name") || "Hassan").substring(0, 2).toUpperCase();
      avatarEl.addEventListener("click", () => {
        const newInitials = prompt("Enter initials (e.g. HP):", avatarEl.textContent);
        if (newInitials) avatarEl.textContent = newInitials.substring(0, 2).toUpperCase();
      });
    }
  }

  // ── Init ───────────────────────────────────────────────────────────────
  async function init() {
    loadConversations();
    setupDropzone();
    setupUserProfile();
    updateDbBadge(activeDbName, null); // restore persisted DB badge
    await refreshKnowledgeBase();
    try { await API.loadDb(activeDbPath); } catch {}
    await loadSchemaPanel();
  }

  window.addEventListener("DOMContentLoaded", init);

  // Expose globals for onclick attributes in HTML
  return {
    newChat, sendQuery, handleKeyDown, autoResize, usePrompt,
    toggleSidebar, toggleRagMode, startRagQuery, exportChat,
    toggleHeaderMenu, downloadActiveDatabase,
    openModal, closeModal, loadDatabase, switchDatabase, switchDatabaseFromHeader, uploadDatabase, previewSchema, executeSchema,
    uploadSelectedFiles, loadSchemaPanel, refreshKnowledgeBase, _removeFile, toast,
    importFile, deleteItem,
  };
})();

// Global shims for inline onclick handlers in HTML
function newChat()              { APP.newChat(); }
function sendQuery()            { APP.sendQuery(); }
function handleKeyDown(e)       { APP.handleKeyDown(e); }
function autoResize(el)         { APP.autoResize(el); }
function usePrompt(t)           { APP.usePrompt(t); }
function toggleSidebar()        { APP.toggleSidebar(); }
function toggleRagMode()        { APP.toggleRagMode(); }
function exportChat(f)          { APP.exportChat(f); }
function toggleHeaderMenu(e)    { APP.toggleHeaderMenu(e); }
function downloadActiveDatabase(){ APP.downloadActiveDatabase(); }
function openModal(id)          { APP.openModal(id); }
function closeModal(id)         { APP.closeModal(id); }
function loadDatabase()         { APP.loadDatabase(); }
function switchDatabaseFromHeader(path) { APP.switchDatabaseFromHeader(path); }
function uploadDatabase()       { APP.uploadDatabase(); }
function previewSchema()        { APP.previewSchema(); }
function executeSchema()        { APP.executeSchema(); }
function uploadSelectedFiles()  { APP.uploadSelectedFiles(); }
function loadSchemaPanel()      { APP.loadSchemaPanel(); }
function importFile(f)          { APP.importFile(f); }
function deleteItem(t, n)       { APP.deleteItem(t, n); }
