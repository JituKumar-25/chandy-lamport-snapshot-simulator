// Frontend: talks to the Flask REST API and draws the network with SVG.
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const NS = "http://www.w3.org/2000/svg";
const COLOR = {"NOT RECORDED": "#22d3ee", "RECORDING": "#fb923c", "COMPLETE": "#4ade80"};
let S = null, running = false;

function toast(msg, err) {
  const t = $("toast"); t.textContent = msg; t.className = "toast show " + (err ? "err" : "");
  clearTimeout(toast.h); toast.h = setTimeout(() => t.className = "toast", 3500);
}
async function api(path, method = "GET", body) {
  const r = await fetch("/api" + path, {method, headers: {"Content-Type": "application/json"},
                                         body: body ? JSON.stringify(body) : undefined});
  const d = await r.json();
  if (d.state) S = d.state;
  if (!r.ok) { toast(d.error || "Request failed", true); const e = new Error(d.error); e.handled = true; throw e; }
  return d;
}
async function act(fn) { try { await fn(); } catch (e) { if (!e.handled) toast(e.message, true); } render(); }

// ---------- user actions
const addProcess = () => act(async () => { await api("/processes", "POST", {process_id: $("p-id").value, initial_state: $("p-state").value}); $("p-id").value = ""; });
const addChannel = () => act(() => api("/channels", "POST", {source: $("c-src").value, destination: $("c-dst").value}));
const sendMessage = () => act(() => api("/messages", "POST", {sender: $("m-from").value, receiver: $("m-to").value, content: $("m-text").value}));
const startSnapshot = () => act(() => api("/snapshot/start", "POST", {initiator: $("snap-init").value}));
const loadDemo = () => act(() => api("/demo", "POST"));
const resetSnapshot = () => act(async () => { running = false; await api("/snapshot/reset", "POST", {full: false}); });
const resetAll = () => act(async () => {
  if (!confirm("Delete all processes, channels and messages? Saved snapshot history is kept.")) return;
  running = false; await api("/snapshot/reset", "POST", {full: true});
});
async function doStep() { const d = await api("/snapshot/step", "POST"); await animate(d.delivered); render(); return d; }
const nextStep = () => act(doStep);
async function autoRun() {
  if (running) return;
  running = true; $("btn-auto").textContent = "Running…";
  try { await api("/snapshot/auto", "POST");
    while (running) {
      await doStep();
      if (S.snapshot && S.snapshot.status !== "RUNNING") break;   // snapshot finished
      await sleep(350);
    }
  } catch (e) { if (!e.handled) toast(e.message, true); }
  running = false; $("btn-auto").textContent = "Auto run"; try { await api("/snapshot/pause", "POST"); } catch (e) {}
  render();
}
const pauseRun = () => { running = false; };

// ---------- geometry
function layout() {
  const n = S.processes.length, pos = {}, r = n <= 1 ? 0 : Math.min(175, 60 + n * 30);
  S.processes.forEach((p, i) => { const a = -Math.PI / 2 + 2 * Math.PI * i / n;
    pos[p.id] = {x: 380 + r * Math.cos(a) * 1.25, y: 235 + r * Math.sin(a)}; });
  return pos;
}
// Curved edge (bend direction depends on direction, so P1->P2 and P2->P1 do not overlap). Clipped at node boxes.
function edgePts(a, b) {
  const dx = b.x - a.x, dy = b.y - a.y, L = Math.hypot(dx, dy) || 1, off = 38;
  const cx = (a.x + b.x) / 2 - dy / L * off, cy = (a.y + b.y) / 2 + dx / L * off, pts = [];
  for (let i = 0; i <= 60; i++) {
    const t = i / 60, u = 1 - t, x = u*u*a.x + 2*u*t*cx + t*t*b.x, y = u*u*a.y + 2*u*t*cy + t*t*b.y;
    const outA = Math.abs(x - a.x) > 68 || Math.abs(y - a.y) > 42, outB = Math.abs(x - b.x) > 74 || Math.abs(y - b.y) > 48;
    if (outA && outB) pts.push([x, y]);
  }
  return pts;
}
const pt = (pts, f) => pts.length ? pts[Math.round(f * (pts.length - 1))] : [0, 0];
const packet = type => type === "MARKER"
  ? '<rect x="-8" y="-8" width="16" height="16" transform="rotate(45)" fill="#fb923c" stroke="#fff" stroke-width="1.5"/>'
  : '<circle r="7" fill="#22d3ee" stroke="#fff" stroke-width="1.5"/>';

function animate(d) {
  return new Promise(res => {
    if (!d) return res();
    const pos = layout(), pts = edgePts(pos[d.source], pos[d.target]);
    if (!pts.length) return res();
    const g = document.createElementNS(NS, "g"); g.innerHTML = packet(d.type); $("viz").appendChild(g);
    const t0 = performance.now(), dur = 700;
    (function frame(t) {
      const k = Math.min(1, (t - t0) / dur), [x, y] = pt(pts, k);
      g.setAttribute("transform", `translate(${x},${y})`);
      k < 1 ? requestAnimationFrame(frame) : (g.remove(), res());
    })(t0);
  });
}

// ---------- rendering
const esc = s => String(s).replace(/[&<>]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[c]));
function fill(id, values) {
  const el = $(id), old = el.value;
  el.innerHTML = values.map(v => `<option>${esc(v)}</option>`).join("");
  if (values.includes(old)) el.value = old;
}
function render() {
  if (!S) return;
  const ids = S.processes.map(p => p.id);
  $("st-p").textContent = S.stats.processes; $("st-c").textContent = S.stats.channels;
  $("st-m").textContent = S.stats.messages;  $("st-s").textContent = S.stats.snapshot;
  ["c-src", "c-dst", "m-from", "m-to", "snap-init"].forEach(id => fill(id, ids));
  if (ids.length > 1 && $("c-dst").value === $("c-src").value) $("c-dst").value = ids[1];
  if (ids.length > 1 && $("m-to").value === $("m-from").value) $("m-to").selectedIndex = 1;
  renderViz(); renderCards(); renderSnap(); renderLog(); renderStep();
}
function renderViz() {
  const pos = layout();
  let h = `<defs><marker id="a1" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0L10,5L0,10z" fill="#7aa2ff"/></marker>
           <marker id="a2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0L10,5L0,10z" fill="#fb923c"/></marker>
           <filter id="glow"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>`;
  let packets = "";
  S.channels.forEach(c => {
    const pts = edgePts(pos[c.source], pos[c.target]);
    h += `<polyline points="${pts.map(p => p.join(",")).join(" ")}" fill="none" stroke="${c.recording ? "#fb923c" : "#7aa2ff"}"
          stroke-width="2" ${c.recording ? 'stroke-dasharray="6 4"' : ""} marker-end="url(#${c.recording ? "a2" : "a1"})" opacity=".85"/>`;
    c.queue.forEach((m, i) => {   // head of the FIFO queue sits closest to the destination
      const [x, y] = pt(pts, Math.max(0.15, 0.88 - i * 0.13));
      packets += `<g transform="translate(${x},${y})"><title>${m.id} ${m.type} ${esc(m.content)}</title>${packet(m.type)}</g>`;
    });
  });
  S.processes.forEach(p => {
    const {x, y} = pos[p.id], col = COLOR[p.snapshot];
    h += `<g filter="url(#glow)"><rect x="${x-60}" y="${y-36}" width="120" height="72" rx="14" fill="${col}22" stroke="${col}" stroke-width="2"/></g>
      <text x="${x}" y="${y-12}" text-anchor="middle" fill="#fff" font-size="17" font-weight="700">${esc(p.id)}</text>
      <text x="${x}" y="${y+6}" text-anchor="middle" fill="#cfe0ff" font-size="12">Counter: ${p.counter}</text>
      <text x="${x}" y="${y+24}" text-anchor="middle" fill="${col}" font-size="11">${p.snapshot === "NOT RECORDED" ? "Snapshot: –" : "Snapshot: ✓ " + p.recorded_state}</text>`;
  });
  $("viz").innerHTML = h + packets;
}
function renderCards() {
  $("cards").innerHTML = S.processes.map(p => `<div class="card"><b>${esc(p.id)}</b> <span class="badge ${p.snapshot.split(" ")[0]}">${p.snapshot}</span>
    <small>Counter ${p.counter} · sent ${p.sent} · received ${p.received}</small><small>Status ${p.status}</small></div>`).join("")
    || "<p class='muted'>No processes yet. Add one or load the demo.</p>";
}
function renderSnap() {
  const s = S.snapshot;
  if (!s) { $("snap-panel").innerHTML = "<p class='muted'>No snapshot running. Pick an initiator and start one.</p>"; return; }
  const ps = S.processes.map(p => `<li>${esc(p.id)} → Counter = ${p.recorded_state ?? "–"}</li>`).join("");
  const cs = S.channels.map(c => `<li>${esc(c.source)} → ${esc(c.target)} → ${c.recorded ? "[" + esc(c.recorded.join(", ")) + "]" : "–"}${c.recording ? " (recording)" : ""}</li>`).join("");
  $("snap-panel").innerHTML = `<p><b>${s.snapshot_id}</b> <span class="badge ${s.status}">${s.status}</span><br>Initiator: ${esc(s.initiator)}<br>
    Start: ${s.start_time}<br>Completion: ${s.completion_time || "–"}</p><b>Process states</b><ul>${ps}</ul><b>Channel states</b><ul>${cs}</ul>`;
}
function renderLog() {
  const learn = $("learn").checked;
  $("log").innerHTML = S.events.slice().reverse().map(e => `<div class="ev ${e.type}"><time>${e.time}</time>${esc(e.description)}${learn && e.explanation ? `<i>${esc(e.explanation)}</i>` : ""}</div>`).join("");
}
function renderStep() {
  const c = S.current_step, learn = $("learn").checked;
  $("step").innerHTML = `<b>${S.snapshot ? "Current step: " + c.step : "No snapshot running"}</b> · ${S.pending} message(s) in transit<br>${esc(c.text)}${learn && c.why ? `<em>${esc(c.why)}</em>` : ""}`;
}
api("/state").then(d => { S = d; render(); });
