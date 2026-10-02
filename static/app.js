const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const ts = t => new Date(t * 1000).toISOString().replace("T", " ").slice(0, 19) + "Z";
const dur = s => s < 60 ? Math.round(s) + "s" : s < 3600 ? Math.floor(s / 60) + "m " + Math.round(s % 60) + "s" : Math.floor(s / 3600) + "h " + Math.floor(s % 3600 / 60) + "m";
const api = async (p, o) => { const r = await fetch(p, o); const j = await r.json(); if (!r.ok) throw new Error(j.error || r.status); return j; };
let sel = null;

function spark(h) {
  if (!h.length) return "";
  const max = Math.max(...h.map(x => x.response_ms || 0), 1);
  return `<svg viewBox="0 0 90 18" style="width:90px;height:18px;border:0;background:none">` + h.map((x, i) =>
    x.is_up ? `<rect x="${i * 3}" y="${18 - Math.max(1, 16 * x.response_ms / max)}" width="2" height="${Math.max(1, 16 * x.response_ms / max)}" fill="#4f8a64"/>`
            : `<rect x="${i * 3}" y="0" width="2" height="18" fill="#b8473f"/>`).join("") + `</svg>`;
}
function chart(checks) {
  const c = checks.slice().reverse(), max = Math.max(...c.map(x => x.response_ms || 0), 1), n = Math.max(c.length - 1, 1);
  const pts = c.filter(x => x.is_up).map(x => `${c.indexOf(x) / n * 600},${80 - 70 * x.response_ms / max}`).join(" ");
  const fails = c.map((x, i) => x.is_up ? "" : `<line x1="${i / n * 600}" x2="${i / n * 600}" y1="0" y2="90" stroke="#b8473f"/>`).join("");
  return `<svg viewBox="0 0 600 90" preserveAspectRatio="none">${fails}<polyline points="${pts}" fill="none" stroke="#4f8a64" vector-effect="non-scaling-stroke"/></svg>
  <div class="sub mono">response time, last ${c.length} checks, max ${max.toFixed(0)} ms. red lines = failed checks</div>`;
}
const incLine = i => `<div>${ts(i.started_at)} ${i.name ? esc(i.name) + " " : ""}<span class="down">down</span> ${esc(i.error)} ` +
  (i.open ? `<span class="down">ongoing ${dur(i.duration_s)}</span>` : `<span class="up">recovered</span> after ${dur(i.duration_s)}`) + `</div>`;

async function load() {
  const [sum, list] = await Promise.all([api("/api/summary"), api("/api/services")]);
  $("#summary").innerHTML = `<b>${sum.total}</b> services <span class="up"><b>${sum.up}</b> up</span> <span class="down"><b>${sum.down}</b> down</span>`;
  $("#services").innerHTML = list.length ? `<table><tr><th>service<th>last<th>uptime<th class="hide-m">history<th></tr>` + list.map(s => `
    <tr class="row" data-id="${s.id}"><td><span class="st ${s.status}"></span><span class="name">${esc(s.name)}</span><span class="sub">${esc(s.url)} / ${s.interval_s}s${s.active ? "" : " / paused"}</span>
    <td class="m">${s.last_ms != null ? s.last_ms.toFixed(0) + " ms" : "-"}<td class="m">${s.uptime != null ? s.uptime + "%" : "-"}<td class="hide-m">${spark(s.history)}
    <td class="acts"><button data-a="toggle">${s.active ? "stop" : "start"}</button><button data-a="del">remove</button></tr>`).join("") + `</table>`
    : `<p class="mono">no services yet. add a name and URL above.</p>`;
  $("#incidents").innerHTML = sum.incidents.map(incLine).join("") || "no incidents recorded";
  if (sel) loadDetail(sel);
}
async function loadDetail(id) {
  try {
    const d = await api("/api/services/" + id);
    $("#detail").hidden = false;
    $("#detail").innerHTML = `<h2>${esc(d.service.name)} <span class="mono">uptime ${d.uptime ?? "-"}%</span></h2>${chart(d.checks)}
    <div class="cols"><div><h2>checks</h2><div class="log">${d.checks.map(c => `<div>${ts(c.ts)} <span class="${c.is_up ? "up" : "down"}">${c.is_up ? "up" : "down"}</span> ${c.status_code ?? "-"} ${c.response_ms != null ? c.response_ms.toFixed(0) + "ms" : esc(c.error)}</div>`).join("") || "none yet"}</div></div>
    <div><h2>status changes</h2><div class="log">${d.changes.map(c => `<div>${ts(c.ts)} <span class="${c.to === "UP" ? "up" : "down"}">${c.to.toLowerCase()}</span></div>`).join("") || "none"}</div>
    <h2>incidents</h2><div class="log">${d.incidents.map(incLine).join("") || "none"}</div></div></div>`;
  } catch { sel = null; $("#detail").hidden = true; }
}
$("#services").onclick = async e => {
  const tr = e.target.closest("tr.row"); if (!tr) return;
  const id = tr.dataset.id, a = e.target.dataset.a;
  if (a === "toggle") await api(`/api/services/${id}/toggle`, { method: "POST" });
  else if (a === "del") { if (!confirm("Remove this service and its history?")) return; await api("/api/services/" + id, { method: "DELETE" }); if (sel == id) sel = null; }
  else { sel = id; }
  load();
};
$("#add").onsubmit = async e => {
  e.preventDefault(); $("#err").textContent = "";
  const f = Object.fromEntries(new FormData(e.target));
  try { await api("/api/services", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(f) }); e.target.reset(); e.target.interval.value = 60; load(); }
  catch (x) { $("#err").textContent = x.message; }
};
load(); setInterval(load, 5000);
