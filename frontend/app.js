const $ = (id) => document.getElementById(id);

let ws;

async function refreshStatus() {
  const res = await fetch("/api/status");
  const s = await res.json();
  const g = $("gmail-status");
  if (s.gmail_connected) {
    g.textContent = `Gmail: ${s.gmail_email || "connected"}`;
    g.className = "badge badge-on";
    $("connect-btn").textContent = "Disconnect Gmail";
    $("connect-btn").dataset.mode = "disconnect";
  } else {
    g.textContent = "Gmail: not connected";
    g.className = "badge badge-off";
    $("connect-btn").textContent = "Connect Gmail";
    $("connect-btn").dataset.mode = "connect";
  }
  const h = $("hunter-status");
  if (s.hunter_configured) {
    h.textContent = "Hunter: configured";
    h.className = "badge badge-on";
  } else {
    h.textContent = "Hunter: not configured (scraping fallback)";
    h.className = "badge badge-off";
  }
  $("start-btn").disabled = s.running;
}

async function refreshDrafts() {
  const res = await fetch("/api/drafts");
  const drafts = await res.json();
  const wrap = $("drafts");
  if (!drafts.length) {
    wrap.innerHTML = '<div class="empty">No drafts yet. Start a campaign above.</div>';
    return;
  }
  wrap.innerHTML = drafts.slice().reverse().map((d) => `
    <div class="draft">
      <header>
        <div>
          <div class="meta">${escapeHtml(d.company)} &middot; ${escapeHtml(d.website)}</div>
          <h3>To: ${escapeHtml(d.to_name || d.to_email)} &lt;${escapeHtml(d.to_email)}&gt;</h3>
          <div class="meta">Subject: ${escapeHtml(d.subject)}</div>
        </div>
        <div class="meta">${d.gmail_draft_id ? "saved to Gmail" : "local only"}</div>
      </header>
      <pre>${escapeHtml(d.body)}</pre>
      <div class="actions">
        ${d.gmail_draft_id
          ? `<a href="https://mail.google.com/mail/u/0/#drafts" target="_blank"><button>Open in Gmail</button></a>`
          : ""}
        <button data-del="${d.id}">Delete</button>
      </div>
    </div>
  `).join("");

  wrap.querySelectorAll("[data-del]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetch(`/api/drafts/${btn.dataset.del}`, { method: "DELETE" });
      refreshDrafts();
    });
  });
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/events`);
  ws.addEventListener("message", (evt) => {
    const e = JSON.parse(evt.data);
    appendLog(e);
    if (e.type === "draft_created") refreshDrafts();
    if (e.type === "done") refreshStatus();
  });
  ws.addEventListener("close", () => {
    setTimeout(connectWS, 2000);
  });
}

function appendLog(e) {
  const log = $("log");
  const div = document.createElement("div");
  div.className = `line ${e.type}`;
  const ts = new Date(e.timestamp + "Z").toLocaleTimeString();
  div.innerHTML = `<span class="ts">${ts}</span>${escapeHtml(e.message)}`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

$("connect-btn").addEventListener("click", async () => {
  const mode = $("connect-btn").dataset.mode || "connect";
  $("connect-btn").disabled = true;
  try {
    if (mode === "connect") {
      const res = await fetch("/api/gmail/connect", { method: "POST" });
      if (!res.ok) {
        const err = await res.json();
        alert("Gmail connect failed: " + (err.detail || res.status));
      }
    } else {
      await fetch("/api/gmail/disconnect", { method: "POST" });
    }
  } finally {
    $("connect-btn").disabled = false;
    refreshStatus();
  }
});

$("start-btn").addEventListener("click", async () => {
  const body = {
    query: $("query").value.trim(),
    max_companies: parseInt($("max").value, 10) || 5,
    additional_interests: $("interests").value.trim(),
    create_gmail_drafts: $("create-drafts").checked,
  };
  if (!body.query) {
    alert("Enter who you want to reach.");
    return;
  }
  const res = await fetch("/api/campaign/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json();
    alert("Could not start: " + (err.detail || res.status));
    return;
  }
  $("log").innerHTML = "";
  refreshStatus();
});

connectWS();
refreshStatus();
refreshDrafts();
setInterval(refreshStatus, 5000);
