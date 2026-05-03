/**
 * ui.js — DOM rendering: chat bubbles, charts, schema, sidebar.
 */
const UI = (() => {
  const esc = s => !s ? "" : String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  const msgs = () => document.getElementById("chatMessages");
  const scrollBot = () => { const m=msgs(); if(m) m.scrollTop=m.scrollHeight; };
  const timeNow = () => new Date().toLocaleTimeString([],{hour:"numeric",minute:"2-digit"});
  const uid = () => "id-"+Math.random().toString(36).slice(2);

  function addUserBubble(text) {
    const d = document.createElement("div");
    d.className = "msg-row user";
    d.innerHTML = `<div class="user-bubble">${esc(text)}</div><div class="msg-time">${timeNow()}</div>`;
    msgs().appendChild(d); scrollBot();
  }

  function addTypingCard() {
    const d = document.createElement("div");
    d.className = "msg-row ai"; d.id = "typingCard";
    d.innerHTML = `<div class="msg-label"><span class="ai-dot"></span>QueryMind AI</div>
      <div class="ai-card"><div class="typing-dots"><span></span><span></span><span></span></div></div>`;
    msgs().appendChild(d); scrollBot(); return d;
  }

  function sqlBlock(sql) {
    if (!sql) return "";
    const id = uid();
    return `<div class="sql-block">
      <div class="sql-block-header">
        <span class="sql-label">SQL</span>
        <button class="copy-btn" onclick="navigator.clipboard.writeText(document.getElementById('${id}').textContent)">
          <span class="material-icons-round">content_copy</span>Copy</button>
      </div>
      <pre class="sql-code" id="${id}">${esc(sql)}</pre></div>`;
  }

  function renderChart(elId, chart) {
    const el = document.getElementById(elId);
    if (!el || !chart) return;
    const layout = Object.assign({
      paper_bgcolor:"#0B0D12", plot_bgcolor:"#0B0D12",
      font:{family:"Inter,sans-serif",color:"#94A3B8",size:12},
      xaxis:{gridcolor:"#2A2D3E"}, yaxis:{gridcolor:"#2A2D3E"},
      margin:{t:30,r:16,b:40,l:40}, height:240
    }, chart.layout||{});
    Plotly.newPlot(el, chart.data||[], layout, {responsive:true, displayModeBar:false});
  }

  function replaceTypingCard(data) {
    const card = document.getElementById("typingCard");
    if (!card) return;
    let inner = `<div class="msg-label"><span class="ai-dot"></span>QueryMind AI</div><div class="ai-card">`;

    if (data.error) {
      inner += `<div class="ai-text" style="color:#FCA5A5">${esc(data.error)}</div>`;
    } else if (data.status === "blocked") {
      inner += `<div class="ai-text" style="color:#FCD34D">⚠️ ${esc(data.message)}</div>${sqlBlock(data.generated_sql)}`;
    } else {
      if (data.answer) inner += `<div class="ai-text markdown-body">${window.marked ? marked.parse(data.answer) : esc(data.answer)}</div>`;
      if (data.generated_sql) inner += sqlBlock(data.generated_sql);
      // Single-value stat card
      const rows = data.result?.data || [];
      if (rows.length === 1 && Object.values(rows[0]).length === 1) {
        const [k,v] = Object.entries(rows[0])[0];
        if (typeof v === "number" || !isNaN(v)) {
          inner += `<div class="stat-card"><div class="stat-value">${v}</div><div class="stat-label">${esc(k)}</div></div>`;
        }
      }
      // Chart
      const chartId = uid();
      if (data.chart) {
        inner += `<div class="chart-container"><div id="${chartId}" class="chart-div"></div></div>`;
        setTimeout(() => renderChart(chartId, data.chart), 80);
      }
      // RAG source chunks
      if (data.source_chunks) {
        data.source_chunks.forEach((c,i) => {
          inner += `<details style="margin-bottom:6px">
            <summary style="font-size:11px;color:var(--muted);cursor:pointer">Source ${i+1}</summary>
            <pre style="font-size:11px;color:var(--dim);padding:6px;background:var(--bg);border-radius:6px;margin-top:4px;white-space:pre-wrap">${esc(c)}</pre>
          </details>`;
        });
      }
      const rowCount = data.result?.count ?? rows.length;
      inner += `<div class="ai-card-footer">
        <span class="footer-stat"><span class="material-icons-round">table_rows</span>${rowCount} rows</span>
        ${data.chart ? '<span class="footer-stat"><span class="material-icons-round">bar_chart</span>Chart</span>' : ""}
        ${data.modified_db ? `<button class="action-pill" onclick="window.location.href='/sql/download-copy'" style="margin-left:auto">⬇️ Download Modified DB</button>` : ""}
      </div>`;
    }
    inner += `</div><div class="msg-time">${timeNow()}</div>`;
    card.removeAttribute("id"); // Fix bubble overwriting bug
    card.innerHTML = inner; scrollBot();
  }

  function addAITextCard(text, isError=false) {
    const d = document.createElement("div");
    d.className = "msg-row ai";
    d.innerHTML = `<div class="msg-label"><span class="ai-dot"></span>QueryMind AI</div>
      <div class="ai-card"><div class="ai-text ${isError ? '' : 'markdown-body'}" ${isError?'style="color:#FCA5A5"':''}>${!isError && window.marked ? marked.parse(text) : esc(text)}</div></div>
      <div class="msg-time">${timeNow()}</div>`;
    msgs().appendChild(d); scrollBot();
  }

  function renderSchema(data) {
    const box = document.getElementById("schemaContent");
    if (!box) return;
    const tables = data.tables||{};
    if (!Object.keys(tables).length) { box.innerHTML=`<p class="muted small">No tables found.</p>`; return; }
    let h = "";
    for (const [t, cols] of Object.entries(tables)) {
      const showCount = 5;
      const extra = cols.length - showCount;
      const rowsHtml = cols.slice(0, showCount).map(c =>
        `<div class="schema-col-row"><span class="col-name">${esc(c.column)}</span><span class="col-type">${esc(c.type)}</span></div>`
      ).join("");
      const extraHtml = extra > 0
        ? `<div class="schema-col-row" style="color:var(--dim);font-size:10px;cursor:pointer" onclick="this.previousSibling && this.parentElement.querySelector('.schema-extra').style.display='block'; this.remove()">
            +${extra} more columns (click to expand)
           </div>
           <div class="schema-extra" style="display:none">${cols.slice(showCount).map(c =>
             `<div class="schema-col-row"><span class="col-name">${esc(c.column)}</span><span class="col-type">${esc(c.type)}</span></div>`).join("")}</div>`
        : "";
      h += `<div class="schema-table-name">
        <span class="material-icons-round" style="font-size:14px;color:var(--primary)">table_chart</span>
        ${esc(t)}
        <button style="margin-left:auto;background:none;border:none;color:var(--primary);font-size:11px;cursor:pointer" onclick="APP.usePrompt('Show me the first 10 records from the ${t} table')">
          Query →
        </button>
      </div>${rowsHtml}${extraHtml}`;
    }
    box.innerHTML = h;
  }

  function renderKnowledgeBase(tables, docs, dbs, uploads, activeDbPath) {
    const dbList = document.getElementById("sidebarDbList");
    if (dbList) {
      dbList.innerHTML = (dbs || []).map(db => {
        const item = typeof db === "string" ? { name: db, path: `database/${db}` } : db;
        const isActive = item.path === activeDbPath;
        return `<div class="kb-item" style="border-left:2px solid ${isActive ? "var(--success)" : "var(--primary)"};padding-left:6px;">
          <span class="material-icons-round" style="font-size:13px;color:${isActive ? "var(--success)" : "var(--primary)"}">dns</span>
          <span class="kb-item-name" style="font-weight:${isActive ? "700" : "500"}">${esc(item.name)}</span>
          ${isActive
            ? '<span class="badge-pill" style="background:rgba(5,150,105,0.15);color:var(--success);font-size:9px">ACTIVE</span>'
            : `<button class="rag-query-btn" onclick="APP.switchDatabase('${esc(item.name)}','${esc(item.path)}')" title="Switch">Switch</button>`}
        </div>`;
      }).join("") || `<p class="muted small" style="padding:4px 8px">No databases yet.</p>`;
    }

    const list = document.getElementById("knowledgeBaseList");
    if (!list) return;

    let h = (tables || []).map(t => `<div class="kb-item">
      <span class="material-icons-round" style="font-size:13px;color:var(--success)">storage</span>
      <span class="kb-item-name">${esc(t)}</span>
      <span class="badge-pill badge-table">Table</span>
      <button class="rag-query-btn" onclick="APP.usePrompt('Show me the first 10 rows of the ${esc(t)} table')" title="Query">Query</button>
    </div>`).join("");

    const indexedDocs = new Set(docs || []);
    h += (uploads || []).map(f => {
      if (f.kind === "table_file") {
        return `<div class="kb-item">
          <span class="material-icons-round" style="font-size:13px;color:var(--success)">table_chart</span>
          <span class="kb-item-name">${esc(f.filename)}</span>
          <span class="badge-pill badge-table">${f.imported ? "Table" : "CSV/XLSX"}</span>
          <button class="rag-query-btn" onclick="APP.usePrompt('Show me the first 10 rows of the ${esc(f.table_name)} table')" title="Query">Query</button>
        </div>`;
      }
      if (f.kind === "rag_file") {
        const docName = f.filename.replace(/\.[^.]+$/, "");
        const indexed = indexedDocs.has(docName);
        return `<div class="kb-item">
          <span class="material-icons-round" style="font-size:13px;color:#a78bfa">description</span>
          <span class="kb-item-name">${esc(f.filename)}</span>
          <span class="badge-pill badge-rag">${indexed ? "RAG" : "File"}</span>
          ${indexed
            ? `<button class="rag-query-btn" onclick="APP.startRagQuery('${esc(docName)}')" title="Ask">Ask</button>`
            : `<span class="muted small" style="margin-left:auto">Not indexed</span>`}
        </div>`;
      }
      return "";
    }).join("");

    const uploadedDocNames = new Set((uploads || [])
      .filter(f => f.kind === "rag_file")
      .map(f => f.filename.replace(/\.[^.]+$/, "")));
    h += (docs || []).filter(d => !uploadedDocNames.has(d)).map(d => `<div class="kb-item">
      <span class="material-icons-round" style="font-size:13px;color:#a78bfa">description</span>
      <span class="kb-item-name">${esc(d)}</span>
      <span class="badge-pill badge-rag">RAG</span>
      <button class="rag-query-btn" onclick="APP.startRagQuery('${esc(d)}')" title="Ask">Ask</button>
    </div>`).join("");

    list.innerHTML = h || `<p class="muted small" style="padding:4px 8px">No files yet.</p>`;
  }

  function renderRagDocs(docs, uploads) {
    const box = document.getElementById("ragDocsList");
    if (!box) return;
    const indexedDocs = new Set(docs || []);
    const ragUploads = (uploads || []).filter(f => f.kind === "rag_file");
    let h = ragUploads.map(f => {
      const docName = f.filename.replace(/\.[^.]+$/, "");
      const indexed = indexedDocs.has(docName);
      return `<div class="rag-doc-row">
        <span class="material-icons-round" style="font-size:13px">description</span>
        <span>${esc(f.filename)}</span>
        ${indexed
          ? `<button class="rag-query-btn" onclick="APP.startRagQuery('${esc(docName)}')">Ask</button>`
          : `<span class="muted small" style="margin-left:auto">Not indexed</span>`}
      </div>`;
    }).join("");

    const uploadedDocNames = new Set(ragUploads.map(f => f.filename.replace(/\.[^.]+$/, "")));
    h += (docs || []).filter(d => !uploadedDocNames.has(d)).map(d => `<div class="rag-doc-row">
      <span class="material-icons-round" style="font-size:13px">description</span>
      <span>${esc(d)}</span>
      <button class="rag-query-btn" onclick="APP.startRagQuery('${esc(d)}')">Ask</button>
    </div>`).join("");

    box.innerHTML = h || `<p class="muted small">No documents yet.</p>`;
  }

  function renderConversations(convs, activeId, onClick) {
    const list = document.getElementById("conversationList");
    if (!list) return;
    list.innerHTML = "";
    convs.forEach(c => {
      const d = document.createElement("div");
      d.className = "conv-item"+(c.id===activeId?" active":"");
      d.innerHTML = `<span class="material-icons-round">chat_bubble_outline</span>
        <span class="conv-item-name">${esc(c.name)}</span>`;
      d.onclick = () => onClick(c.id);
      list.appendChild(d);
    });
  }

  function hideWelcome() { const w=document.getElementById("welcomeState"); if(w) w.style.display="none"; }

  return { addUserBubble, addTypingCard, replaceTypingCard, addAITextCard,
           renderChart, renderSchema, renderKnowledgeBase, renderRagDocs,
           renderConversations, hideWelcome, scrollBot };
})();
