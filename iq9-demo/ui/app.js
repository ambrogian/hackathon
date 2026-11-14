"use strict";
const $ = (id) => document.getElementById(id);
const S = 20;  // canvas pixels per sensor pixel
const TITLES = { panel_fault: "Hot lug + crackle", air_leak: "Air leak", healthy: "Healthy", conflict: "Hot lug, low load", random: "Random scene" };
const MODE_TITLES = { healthy: "Healthy", loose_lug: "Loose lug", air_leak: "Air leak", low_load: "Low load" };
const BOARD_TITLES = { live: "Live board", hot_sim: "Hot (simulated)" };
const LINE_TITLES = { healthy: "Healthy", heater_failed: "Dryer heater failed", screen_torn: "Screen pack torn", die_heater_open: "Die D5 heater open", coupling_wear: "Roll 2 coupling wear" };
const titleOf = (m) => MODE_TITLES[m] || BOARD_TITLES[m] || LINE_TITLES[m] || m;
const LABELS = ["FAULT", "OK", "INCONCLUSIVE"];
const SEV = { OK: 0, INCONCLUSIVE: 1, FAULT: 2 };
let showTruth = false, last = null, plant = null, view = "arch", timers = [], logSeq = 0, logRows = [], logAsset = "", logPaused = false, logRaw = false;
let sandboxInit = false, curAsset = null, inc = null, incTimer = null;

function el(tag, props, ...kids) {
  const e = document.createElement(tag);
  Object.assign(e, props || {});
  for (const k of kids) e.append(k);
  return e;
}
async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}
const fmt = (v, d = 1) => (v == null ? "-" : Number(v).toFixed(d));
const hhmmss = (ts) => (ts || "").slice(11, 19);

/* ---------- thermal / console drawing (unchanged logic) ---------- */
function iron(t) {
  const st = [[0, 0, 0], [40, 0, 90], [160, 20, 110], [230, 70, 30], [250, 180, 30], [255, 255, 210]];
  const x = Math.min(Math.max(t, 0), 1) * (st.length - 1), i = Math.min(Math.floor(x), st.length - 2), f = x - i;
  return st[i].map((v, k) => v + (st[i + 1][k] - v) * f);
}
function layer(grid, colour) {
  const h = grid.length, w = grid[0].length, c = el("canvas", { width: w, height: h });
  const g = c.getContext("2d"), img = g.createImageData(w, h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const [r, gg, b, a] = colour(grid[y][x]), o = (y * w + x) * 4;
    img.data.set([r, gg, b, a], o);
  }
  g.putImageData(img, 0, 0);
  return c;
}
function draw(d) {
  const ctx = $("view").getContext("2d"), f = d.frame, flat = f.flat();
  const lo = Math.min(...flat), hi = Math.max(Math.max(...flat), lo + 10);
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(layer(f, (v) => [...iron((v - lo) / (hi - lo)), 255]), 0, 0, 640, 480);
  const m = d.measure;
  if (m.acoustic_detected) {
    ctx.drawImage(layer(d.acoustic_map, (v) => [134, 182, 240, Math.max(0, (v - 0.8) / 0.2) * 120]), 0, 0, 640, 480);
    const cx = (m.px[0] + 0.5) * S, cy = (m.px[1] + 0.5) * S;
    ctx.strokeStyle = "#6DB3DB"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(cx, cy, 14, 0, 7); ctx.moveTo(cx - 22, cy); ctx.lineTo(cx + 22, cy); ctx.moveTo(cx, cy - 22); ctx.lineTo(cx, cy + 22); ctx.stroke();
  }
  ctx.font = "11px 'JetBrains Mono', ui-monospace, monospace"; ctx.lineWidth = 1; ctx.strokeStyle = "rgba(236,230,216,.5)"; ctx.fillStyle = "#E4EAEE";
  for (const o of d.objects) {
    const x = (o.cx - o.w / 2) * S, y = (o.cy - o.h / 2) * S;
    ctx.strokeRect(x, y, (o.w + 1) * S, (o.h + 1) * S);
    ctx.fillText(o.name.toUpperCase(), x + 2, y - 5);
  }
  $("legend").textContent = `thermal ${lo.toFixed(0)}-${hi.toFixed(0)} °C` + (m.acoustic_detected ? " · blue = sound source (beamformed)" : " · no sound source above threshold");
}
function paintD1(id, d1) {
  const c = $("d1card"); c.hidden = false; c.dataset.key = id + ":" + (d1 && d1.ts); c.replaceChildren(el("h2", {}, "d1-2B second opinion", el("span", { className: "m", textContent: "CPU · no output tokens" })));
  if (d1 && !d1.error) {
    const pct = (x) => (x * 100).toFixed(0) + " %";
    c.append(el("dl", {}, ...[...(d1.vision ? [["Fault, image + text", pct(d1.fused.p_fault)], ["Fault, image only", pct(d1.vision.p_fault)]] : []), ["Fault, text only", pct(d1.p_fault)],
      ...(d1.vision ? [["Severity, image + text", d1.fused.severity], ["Severity, image only", d1.vision.severity]] : []), ["Severity, text only", d1.severity],
      ["Category", `${d1.category} (${pct(d1.category_confidence)})`],
      ...(d1.p_hotspot_image != null ? [["Hotspot in the picture", pct(d1.p_hotspot_image)]] : []), ["Latency", `${d1.ms.state} ms text` + (d1.vision ? ` · ${d1.ms.image} ms image · ${d1.ms.fused || 0} ms fused` : "")], ["Output tokens", d1.output_tokens]]
      .flatMap(([k, v]) => [el("dt", { textContent: k }), el("dd", { textContent: String(v) })])));
    const bars = (title, probs, names) => {
      const entries = Array.isArray(probs) ? probs.map((v, i) => [names ? names[i] : String(i), v]) : Object.entries(probs || {});
      c.append(el("small", { textContent: title }), ...entries.map(([k, v]) => el("div", { className: "pbar" }, el("span", { textContent: k }), el("i", { style: `width:${(v * 100).toFixed(0)}%` }), el("em", { textContent: pct(v) }))));
    };
    if (d1.fused && d1.fused.severity_probs) bars("Severity probabilities (image + text)", d1.fused.severity_probs, ["Low", "Moderate", "Critical"]);
    if (d1.severity_probs) bars("Severity probabilities (text)", d1.severity_probs, ["Low", "Moderate", "Critical"]);
    if (d1.category_probs) bars("Category probabilities", d1.category_probs);
  } else c.append(el("small", { textContent: d1 ? d1.error : "Runs automatically when this asset first leaves OK, or press the button." }));
  c.append(el("button", { type: "button", textContent: "Run d1 on this frame", onclick: async (e) => {
    e.target.disabled = true; e.target.textContent = "running d1...";
    try { paintD1(id, await api("/api/d1", { asset: id })); } catch (err) { paintD1(id, { error: String(err) }); }
  } }));
}

function panel(d) {
  const dec = d.decision, m = d.measure;
  const card = $("decision"); card.replaceChildren();
  card.append(el("h2", { textContent: `Decision (${dec.decider})` }),
    el("span", { className: "label " + dec.label, textContent: dec.label }),
    el("div", { className: "bar " + dec.label }, el("i", { style: `width:${(dec.p * 100).toFixed(0)}%` })),
    el("small", { textContent: `confidence ${(dec.p * 100).toFixed(0)}% · severity ${dec.severity}` }),
    el("p", { textContent: "Action: " + dec.action }));
  if (showTruth && !d.asset) {
    const t = d.truth;
    card.append(el("p", { textContent: `Truth: ${t.label} (${d.correct ? "match" : "MISS"})`, className: d.correct ? "OK" : "FAULT" }));
  }
  $("report").textContent = d.report;
  $("rsrc").textContent = "text source: " + d.report_source;
  const rows = [["Load", `${m.load_pct.toFixed(0)} %`], ["Ambient", `${m.ambient_c.toFixed(1)} °C`],
    ...m.lug_dt_c.map((v, i) => [`Lug ${"ABC"[i]} vs others`, `${v >= 0 ? "+" : ""}${v.toFixed(1)} °C`]),
    ["Thermal tier", m.tier], ["Sound source", m.acoustic_detected ? (m.impulsive ? "crackle" : "hiss") + " at " + m.target : "none"],
    ["Coherence", m.coherence.toFixed(2)], ["At hottest lug", m.colocated ? "yes" : "no"]];
  const dl = $("meas"); dl.replaceChildren();
  for (const [k, v] of rows) dl.append(el("dt", { textContent: k }), el("dd", { textContent: v }));
}

/* ---------- router ---------- */
function go(target) { location.hash = target; }
function parse() {
  const h = location.hash.slice(1) || "arch";
  const [v, arg] = h.split("/");
  return { v: ["arch", "asset", "console", "log", "incidents", "system", "ask"].includes(v) ? v : "arch", arg };
}
function clearTimers() { timers.forEach(clearInterval); timers = []; }
async function route() {
  const { v, arg } = parse();
  clearTimers();
  view = v;
  const shown = v === "console" ? "asset" : v;
  for (const id of ["arch", "asset", "log", "incidents", "system", "ask"]) $("v-" + id).hidden = id !== shown;
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("on", b.dataset.go === v || (v === "asset" && b.dataset.go === "arch")));
  try {
    if (v === "arch") { await refreshPlant(); timers.push(setInterval(refreshPlant, 1500)); }
    else if (v === "asset") { await openAsset(arg || "sg2"); }
    else if (v === "console") { await openSandbox(); }
    else if (v === "log") { await openLog(); }
    else if (v === "incidents") { await openIncidents(arg); }
    else if (v === "system") { await openSystem(); }
    else if (v === "ask") { await openAsk(); }
  } catch (e) { document.body.append(el("pre", { textContent: String(e) })); }
}
document.addEventListener("click", (e) => { const t = e.target.closest("[data-go]"); if (t) go(t.dataset.go); });
document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const t = e.target.closest && e.target.closest("[role=button][data-go]");
  if (t) { e.preventDefault(); go(t.dataset.go); }
});
addEventListener("hashchange", route);

/* ---------- plant state (header, alert bar, architecture) ---------- */
async function refreshPlant() {
  plant = await api("/api/plant");
  $("decider").textContent = "decider: " + plant.decider + (plant.llm ? " + LLM text" : "");
  $("tick").textContent = `live · tick ${plant.tick} · ${plant.interval}s`;
  const worst = plant.assets.filter((a) => a.label === "FAULT").sort((a, b) => (b.dt_c || 0) - (a.dt_c || 0))[0];
  const bar = $("alertbar");
  bar.hidden = !worst;
  if (worst) {
    bar.dataset.go = "asset/" + worst.id;
    bar.textContent = worst.headline ? `FAULT · ${worst.name} · ${worst.headline} · OPEN →` : `FAULT · ${worst.name} ${worst.id === "c1" ? "air leak" : worst.worst} ${worst.dt_c >= 1 ? "+" + fmt(worst.dt_c) + " °C · " : ""}${worst.acoustic ? (worst.impulsive ? "crackle" : "hiss") + " detected · " : ""}severity ${worst.severity}. Open →`;
  }
  if (view === "arch") paintArch();
}
function paintArch() {
  const cls = { OK: "ok", INCONCLUSIVE: "warn", FAULT: "bad" };
  for (const a of plant.assets) {
    const eq = $("eq-" + a.id);
    if (eq) eq.setAttribute("class", "eq " + cls[a.label]);
    const st = $("st-" + a.id);
    if (st) st.textContent = a.label === "OK" ? "ok" : a.label === "FAULT" ? "fault" : "check";
    const pu = $("pu-" + a.id), cl = $("cl-" + a.id);
    if (pu) { pu.toggleAttribute("hidden", a.label === "OK"); pu.setAttribute("class", "pulse " + (a.label === "FAULT" ? "crit" : "warn")); }
    if (cl) {
      cl.toggleAttribute("hidden", a.label === "OK");
      if (a.id === "sg2") { $("cl-sg2-a").textContent = `${a.worst} +${fmt(a.dt_c)} °C`; $("cl-sg2-b").textContent = `${a.acoustic ? (a.impulsive ? "crackle" : "hiss") + " · " : ""}${a.severity}`; }
      if (a.id === "c1") $("cl-c1-a").textContent = `${a.acoustic ? (a.impulsive ? "Crackle" : "Hiss") : "Heat"} · ${a.severity}`;
    }
  }
  const box = $("faults"); box.replaceChildren();
  for (const a of [...plant.assets].sort((x, y) => SEV[y.label] - SEV[x.label])) {
    const pill = a.label === "FAULT" ? "crit" : a.label === "INCONCLUSIVE" ? "warn" : "ok";
    const what = a.kind === "line" ? (a.label === "OK" ? "Signals normal" : `${a.part}`) : a.kind === "board" ? (a.temp_c == null ? "no thermal zones on this host" : `SoC ${fmt(a.temp_c)} °C · ${a.source}`) : a.label === "OK" ? "No fault" : `${a.id === "c1" ? "Air leak" : a.worst + " " + (a.dt_c >= 1 ? "+" + fmt(a.dt_c) + " °C" : "")}${a.acoustic ? " · " + (a.impulsive ? "crackle" : "hiss") : ""}`;
    box.append(el("button", { className: "frow", onclick: () => go("asset/" + a.id) },
      el("span", { className: "pill " + pill, textContent: a.label === "OK" ? "Healthy" : a.label === "FAULT" ? a.severity : "Check" }),
      el("b", { textContent: `${a.name} · ${a.room}` }), el("span", { textContent: `${what} · mode ${titleOf(a.mode)}` }),
      ...(a.d1 && !a.d1.error ? [el("span", { className: "d1p", textContent: `d1 fault ${(a.d1.p_fault * 100).toFixed(0)} % · ${a.d1.severity} · ${a.d1.category}` })] : [])));
  }
}
for (const [cb, g] of [["ly-data", "g-data"], ["ly-sens", "g-sens"], ["ly-fault", "g-fault"]]) $(cb).addEventListener("change", (e) => { $(g).style.display = e.target.checked ? "" : "none"; });

/* ---------- asset + scenarios ---------- */
function setConsoleMode(mode) {
  const live = mode === "asset";
  $("assethead").hidden = false; $("inject").hidden = !live; $("scenes").hidden = live; $("valcard").hidden = live;
  $("assetlog").hidden = !live;
  $("assettitle").textContent = live ? "" : "Scenario sandbox (fixed scenes, no plant)";
}
async function openAsset(id) {
  curAsset = id;
  setConsoleMode("asset");
  const tick = async () => {
    const d = await api("/api/asset?asset=" + id);
    last = d;
    if (d.line) { drawLine(d); panelLine(d); if ($("d1card").dataset.key !== id + ":" + (d.d1 && d.d1.ts)) paintD1(id, d.d1); } else if (d.board) { drawBoard(d); panelBoard(d); $("d1card").hidden = true; } else { draw(d); panel(d); if ($("d1card").dataset.key !== id + ":" + (d.d1 && d.d1.ts)) paintD1(id, d.d1); }
    $("assettitle").textContent = `${d.asset.name} · ${d.asset.room} · age ${d.asset.age} ticks`;
    const box = $("inject"); box.replaceChildren(el("span", { className: "m", textContent: "Inject" }));
    const titles = d.line ? Object.fromEntries(d.asset.modes.map((m) => [m, LINE_TITLES[m]])) : d.board ? BOARD_TITLES : MODE_TITLES;
    for (const m of Object.keys(titles)) {
      box.append(el("button", { textContent: titles[m], className: d.asset.mode === m ? "on" : "", onclick: async () => { await api("/api/inject", { asset: id, mode: m }); tick(); } }));
    }
    const lg = await api(`/api/log?asset=${id}&n=7`);
    $("assetlogpre").textContent = lg.rows.slice().reverse().map(lineOf).join("\n");
  };
  await tick();
  timers.push(setInterval(() => tick().catch(() => {}), 2000));
  refreshPlant().catch(() => {});
}
function drawLine(d) {
  const cv = $("view"), g = cv.getContext("2d"), W = cv.width, H = cv.height, h = d.line.history, P = d.line.panels;
  g.clearRect(0, 0, W, H); g.fillStyle = "#050505"; g.fillRect(0, 0, W, H);
  g.font = "11px 'JetBrains Mono', ui-monospace, monospace";
  const hh = (H - 60) / P.length;
  P.forEach((pn, k) => {
    const y0 = 20 + k * (hh + 20), y1 = y0 + hh - 20, X = (i) => 50 + (i / Math.max(1, h.length - 1)) * (W - 70), Y = (v) => y1 - ((v - pn.lo) / (pn.hi - pn.lo)) * (y1 - y0);
    g.strokeStyle = "#2B3842"; g.strokeRect(50, y0, W - 70, y1 - y0); g.fillStyle = "#93A2AC"; g.fillText(pn.name, 56, y0 + 14);
    if (pn.limit != null) { g.setLineDash([3, 4]); g.strokeStyle = "#F06A5E"; g.beginPath(); g.moveTo(50, Y(pn.limit)); g.lineTo(W - 20, Y(pn.limit)); g.stroke(); g.setLineDash([]); }
    pn.keys.forEach(([key, label, col], n) => {
      g.strokeStyle = col; g.lineWidth = 1.6; g.beginPath(); let first = true;
      h.forEach((r, i) => { const v = r[key]; if (v == null) return; first ? g.moveTo(X(i), Y(v)) : g.lineTo(X(i), Y(v)); first = false; }); g.stroke(); g.lineWidth = 1;
      g.fillStyle = col; g.fillText(label, W - 110, y0 + 14 + n * 13);
    });
  });
  $("legend").textContent = `extrusion line telemetry · ${d.asset.room} · last ${h.length} samples · simulated signals`;
}
function panelLine(d) {
  const dec = d.decision, m = d.measure, kb = d.line.kb, card = $("decision"); card.replaceChildren();
  card.append(el("h2", { textContent: `Decision (${dec.decider})` }), el("span", { className: "label " + dec.label, textContent: dec.label }),
    el("div", { className: "bar " + dec.label }, el("i", { style: `width:${(dec.p * 100).toFixed(0)}%` })), el("small", { textContent: `severity ${dec.severity}` }),
    el("p", { textContent: kb ? "Part: " + kb.part : "All signals in range" }));
  $("report").textContent = d.report; $("rsrc").textContent = "text source: template";
  const dl = $("meas"); dl.replaceChildren();
  const rows = Object.entries(m.signals).map(([k, v]) => [k.replaceAll("_", " "), String(v)]);
  if (kb) rows.push(["Next step", kb.steps[0]], ["Then", kb.steps[1]], ["Verify", kb.steps[2]], ["Time to resume", kb.resume_min + " min"], ["Warning lead", kb.lead], ["Sheet defect", kb.defect]);
  for (const [k, v] of rows) dl.append(el("dt", { textContent: k }), el("dd", { textContent: v }));
}
function drawBoard(d) {
  const cv = $("view"), g = cv.getContext("2d"), W = cv.width, H = cv.height, h = d.board.history;
  g.clearRect(0, 0, W, H); g.fillStyle = "#050505"; g.fillRect(0, 0, W, H);
  g.font = "11px 'JetBrains Mono', ui-monospace, monospace";
  const have = h.some((r) => r.temp_c != null);
  const panelDraw = (y0, y1, key, lo, hi, col, name, limit) => {
    g.strokeStyle = "#2B3842"; g.strokeRect(50, y0, W - 70, y1 - y0); g.fillStyle = "#93A2AC"; g.fillText(name, 56, y0 + 14);
    const Y = (v) => y1 - ((v - lo) / (hi - lo)) * (y1 - y0), X = (i) => 50 + (i / Math.max(1, h.length - 1)) * (W - 70);
    if (limit) { g.setLineDash([3, 4]); g.strokeStyle = "#F06A5E"; g.beginPath(); g.moveTo(50, Y(limit)); g.lineTo(W - 20, Y(limit)); g.stroke(); g.setLineDash([]); g.fillStyle = "#F06A5E"; g.fillText(limit + " °C limit", W - 120, Y(limit) - 4); }
    g.strokeStyle = col; g.lineWidth = 1.6; g.beginPath(); let first = true;
    h.forEach((r, i) => { const v = r[key]; if (v == null) return; first ? g.moveTo(X(i), Y(v)) : g.lineTo(X(i), Y(v)); first = false; }); g.stroke(); g.lineWidth = 1;
  };
  if (have) panelDraw(20, 230, "temp_c", 20, 100, "#F06A5E", "SOC TEMPERATURE (°C)", 70);
  else { g.fillStyle = "#93A2AC"; g.fillText("NO THERMAL ZONES ON THIS HOST (they exist on the IQ-9075 board)", 56, 40); g.fillText("USE 'HOT (SIMULATED)' TO SEE THE ALERT PATH", 56, 60); }
  panelDraw(260, 450, "load_pct", 0, 100, "#6DB3DB", "CPU LOAD (% OF CORES)", 0);
  $("legend").textContent = `real board telemetry · last ${h.length} loops · source ${d.measure.source}`;
}
function panelBoard(d) {
  const dec = d.decision, m = d.measure, card = $("decision"); card.replaceChildren();
  card.append(el("h2", { textContent: `Decision (${dec.decider})` }), el("span", { className: "label " + dec.label, textContent: dec.label }),
    el("div", { className: "bar " + dec.label }, el("i", { style: `width:${(dec.p * 100).toFixed(0)}%` })), el("small", { textContent: `severity ${dec.severity}` }));
  $("report").textContent = d.report; $("rsrc").textContent = "text source: template";
  const rows = [["SoC temperature", m.temp_c == null ? "-" : fmt(m.temp_c) + " °C"], ["Rise in 60 s", fmt(m.dt_c) + " °C"], ["CPU load", fmt(m.load_pct, 0) + " %"], ["Thermal zones", m.zones], ["Source", m.source], ["Limits", "70 °C or +8 °C per minute"]];
  const dl = $("meas"); dl.replaceChildren(); for (const [k, v] of rows) dl.append(el("dt", { textContent: k }), el("dd", { textContent: String(v) }));
}
function lineOf(r) {
  const d = r.decision || {}, m = r.measure || {};
  return `${hhmmss(r.ts)} ${(r.asset || "").padEnd(3)} ${(d.label || "ERROR").padEnd(12)} ${((r.action || {}).name || "-").padEnd(20)} ${r.kind === "line" ? (m.headline || "signals normal").slice(0, 60).padEnd(60) : `dT ${fmt(m.dt_c).padStart(5)} coh ${fmt(m.coherence, 2)}`} ${r.ms_total} ms${r.error ? " ERR " + r.error : ""}`;
}
async function openSandbox() {
  setConsoleMode("sandbox");
  $("inject").replaceChildren();
  const info = await api("/api/scenes");
  await document.fonts.load("11px 'JetBrains Mono'");
  if (!sandboxInit) {
    sandboxInit = true;
    const box = $("scenes");
    for (const n of [...info.scenes, "random"]) {
      box.append(el("button", { textContent: TITLES[n] || n, onclick: () => load(n, n === "random" ? Math.floor(Math.random() * 1e6) : 1) }, ""));
      box.lastChild.dataset.name = n;
    }
    box.append(el("button", { textContent: "Reveal truth", onclick: (e) => { showTruth = !showTruth; e.target.classList.toggle("on", showTruth); if (last) panel(last); } }));
    $("vrun").onclick = validate;
  }
  await load(info.scenes[0], 1);
  refreshPlant().catch(() => {});
}
async function load(name, seed) {
  const d = await api(`/api/scene?name=${name}&seed=${seed}`);
  last = d; draw(d); panel(d);
  document.querySelectorAll("#scenes button").forEach((b) => b.classList.toggle("on", b.dataset.name === name));
}
function table(head, rows) {
  return el("table", {}, el("tr", {}, ...head.map((h) => el("th", { textContent: h }))),
    ...rows.map((r) => el("tr", {}, ...r.map((c) => el("td", { textContent: c })))));
}
async function validate() {
  $("vrun").disabled = true; $("vout").replaceChildren();
  await api(`/api/validate_start?n=${$("vn").value}&seed=1000`);
  for (;;) {
    const j = await api("/api/validate_status");
    $("vprog").textContent = j.state === "running" ? `${j.done}/${j.total}` : "";
    if (j.state === "done") {
      const r = j.result;
      $("vout").append(
        el("p", { textContent: `${r.n} scenes · accuracy ${(r.accuracy * 100).toFixed(1)}% · calibration error ${r.ece.toFixed(3)} · Brier ${r.brier.toFixed(3)} · ${r.seconds}s` }),
        table(["truth \\ predicted", ...LABELS], LABELS.map((t) => [t, ...LABELS.map((p) => r.confusion[t][p])])),
        table(["confidence", "n", "mean conf.", "accuracy"], r.bins.map((b) => [`${b.lo.toFixed(1)}-${b.hi.toFixed(1)}`, b.n, b.mean_conf.toFixed(2), b.accuracy.toFixed(2)])));
      break;
    }
    if (j.state === "error") { $("vout").append(el("p", { textContent: j.error })); break; }
    await new Promise((r) => setTimeout(r, 500));
  }
  $("vrun").disabled = false;
}

/* ---------- log ---------- */
async function openLog() {
  logSeq = 0; logRows = [];
  const bar = $("logbar"); bar.replaceChildren();
  const chips = ["", ...plant.assets.map((a) => a.id)];  // every asset: switchgear, compressor, extrusion zones, edge board
  for (const c of chips) bar.append(el("button", { textContent: c ? c.toUpperCase() : "All", className: logAsset === c ? "on" : "", onclick: () => { logAsset = c; openLog(); } }));
  bar.append(el("span", { className: "spacer" }),
    el("button", { textContent: logPaused ? "Resume" : "Pause", className: logPaused ? "on" : "", onclick: (e) => { logPaused = !logPaused; e.target.textContent = logPaused ? "Resume" : "Pause"; e.target.classList.toggle("on", logPaused); } }),
    el("button", { textContent: "Raw JSONL", className: logRaw ? "on" : "", onclick: (e) => { logRaw = !logRaw; e.target.classList.toggle("on", logRaw); paintLog(); } }));
  const sys = await api("/api/system");
  $("logfile").textContent = sys.log_path.replace(/^.*\/out\//, "out/") + " · flushed per loop";
  await pollLog();
  timers.push(setInterval(() => pollLog().catch(() => {}), 1500));
}
async function pollLog() {
  if (logPaused) return;
  const j = await api(`/api/log?after=${logSeq}&n=200${logAsset ? "&asset=" + logAsset : ""}`);
  if (j.rows.length) { logSeq = j.rows[j.rows.length - 1].seq; logRows = logRows.concat(j.rows).slice(-300); }
  paintLog();
}
function paintLog() {
  $("logtable").hidden = logRaw; $("lograw").hidden = !logRaw;
  const rows = logRows.slice().reverse().slice(0, 80);
  if (logRaw) { $("lograw").textContent = rows.map((r) => JSON.stringify(r)).join("\n"); return; }
  const tb = $("logtable").tBodies[0]; tb.replaceChildren();
  for (const r of rows) {
    const d = r.decision || {}, m = r.measure || {};
    const tr = el("tr", { className: "L-" + (d.label || "ERR"), onclick: () => go("asset/" + r.asset) },
      el("td", { textContent: hhmmss(r.ts) }), el("td", { textContent: (r.asset || "").toUpperCase() }), el("td", { textContent: d.label || "ERROR" }),
      el("td", { textContent: `${(r.action || {}).name || "-"}${(r.action || {}).status && r.action.status !== "executed" ? " (" + r.action.status + ")" : ""}` }),
      el("td", { textContent: r.kind === "line" ? "-" : fmt(m.dt_c) }), el("td", { textContent: r.kind === "line" || r.kind === "board" ? "-" : fmt(m.coherence, 2) }), el("td", { textContent: r.ms_total }),
      el("td", { className: "txt", textContent: r.error || r.report || "" }));
    tb.append(tr);
  }
}

/* ---------- incidents + replay ---------- */
async function openIncidents(arg) {
  const refresh = async () => {
    const j = await api("/api/incidents");
    const box = $("inclist"); box.replaceChildren();
    if (!j.incidents.length) box.append(el("div", { className: "note", textContent: "No FAULT incident yet. The default plant raises one on SG-2 within about 20 seconds." }));
    for (const c of j.incidents) {
      box.append(el("button", { className: "frow" + (arg === c.id ? " sel" : ""), onclick: () => go("incidents/" + c.id) },
        el("span", { className: "pill " + (c.open ? "crit" : "ok"), textContent: c.open ? "Open" : "Closed" }),
        el("b", { textContent: `${c.name} · ${c.worst}` }), el("span", { textContent: `${hhmmss(c.ts)} · peak ΔT ${fmt(c.peak_dt_c)} °C` })));
    }
  };
  await refresh();
  timers.push(setInterval(() => refresh().catch(() => {}), 3000));
  $("incempty").hidden = !!arg; $("incbody").hidden = !arg;
  if (arg) await loadIncident(arg);
}
async function loadIncident(id) {
  inc = await api("/api/incident?id=" + encodeURIComponent(id));
  const n = inc.series.length, c = inc.incident;
  const sc = $("incscrub"); sc.max = n - 1; sc.value = inc.start_index; sc.oninput = () => paintInc(+sc.value);
  const firstTier = inc.series.findIndex((r) => r.tier !== "none");
  const lead = firstTier >= 0 && firstTier < inc.start_index ? inc.start_index - firstTier : 0;
  $("incnotice").textContent = `NOTICE OF FAILURE · ${c.name} · ${c.worst} · first FAULT at ${hhmmss(c.ts)}` + (lead ? ` · warming visible ${lead} loops (${lead * (plant ? plant.interval : 2)} s) earlier` : "");
  $("inclabel").textContent = `${c.name} · ${n} loops`;
  let playing = false, pt = null;
  $("incplay").onclick = () => {
    playing = !playing; $("incplay").textContent = playing ? "Pause" : "Play";
    clearInterval(pt);
    if (playing) pt = setInterval(() => { if (+sc.value >= n - 1) { playing = false; $("incplay").textContent = "Play"; clearInterval(pt); return; } sc.value = +sc.value + 1; paintInc(+sc.value); }, 250);
  };
  paintInc(inc.start_index);
}
function paintInc(k) {
  const cv = $("inccanvas"), g = cv.getContext("2d"), W = cv.width, H = cv.height, s = inc.series, n = s.length;
  g.clearRect(0, 0, W, H);
  const X = (i) => 50 + (i / Math.max(1, n - 1)) * (W - 70);
  const panelsDef = [{ y0: 10, y1: 150, key: "dt_c", max: Math.max(22, ...s.map((r) => r.dt_c)), col: "#F06A5E", name: "DEVIATION / ΔT vs others (°C)", lines: [[4, "fault ≥4"], [15, "critical ≥15"]] },
    { y0: 180, y1: 300, key: "coherence", max: 1, col: "#6DB3DB", name: "Acoustic coherence", lines: [[0.04, "detect 0.04"]] }];
  g.font = "10px 'JetBrains Mono', monospace";
  for (const p of panelsDef) {
    const Y = (v) => p.y1 - (v / p.max) * (p.y1 - p.y0);
    g.strokeStyle = "#2B3842"; g.strokeRect(50, p.y0, W - 70, p.y1 - p.y0);
    g.fillStyle = "#93A2AC"; g.fillText(p.name.toUpperCase(), 54, p.y0 + 12);
    for (const [v, t] of p.lines) { g.setLineDash([3, 4]); g.strokeStyle = "#4d4126"; g.beginPath(); g.moveTo(50, Y(v)); g.lineTo(W - 20, Y(v)); g.stroke(); g.setLineDash([]); g.fillStyle = "#93A2AC"; g.fillText(t, W - 110, Y(v) - 3); }
    g.strokeStyle = p.col; g.lineWidth = 1.6; g.beginPath();
    s.forEach((r, i) => (i ? g.lineTo(X(i), Y(r[p.key])) : g.moveTo(X(i), Y(r[p.key])))); g.stroke(); g.lineWidth = 1;
  }
  g.strokeStyle = "#F06A5E"; g.beginPath(); g.moveTo(X(inc.start_index), 10); g.lineTo(X(inc.start_index), 300); g.stroke();
  g.fillStyle = "#F06A5E"; g.fillText("FAULT", X(inc.start_index) + 4, 24);
  g.strokeStyle = "#E4EAEE"; g.beginPath(); g.moveTo(X(k), 10); g.lineTo(X(k), 300); g.stroke();
  g.fillStyle = "#93A2AC"; g.fillText(hhmmss(s[0].ts), 50, 314); g.fillText(hhmmss(s[n - 1].ts), W - 70, 314);
  const r = s[k];
  $("incpos").textContent = `${hhmmss(r.ts)} · loop ${k + 1}/${n}`;
  const d = $("incdetail"); d.replaceChildren();
  const evidence = [];
  const isLine = /^Z\d/.test(r.worst || "");
  if (isLine) evidence.push(r.report.replace(/^FAULT\. /, ""));
  else if (r.dt_c >= 1) evidence.push(`${r.worst} is ${fmt(r.dt_c)} °C above the other lugs (tier ${r.tier})`);
  if (!isLine) evidence.push(r.load_pct >= 40 ? `load ${fmt(r.load_pct, 0)} % is at least 40 %, so the thermal reading is valid` : `load ${fmt(r.load_pct, 0)} % is below 40 %, thermal reading not valid`);
  if (!isLine) evidence.push(r.coherence >= 0.04 ? `sound source at ${r.target}, coherence ${fmt(r.coherence, 2)}` : "no sound source above threshold");
  d.append(el("h2", { textContent: "At this moment" }),
    el("span", { className: "label " + r.label, textContent: r.label }),
    el("p", { textContent: `Action: ${r.action.name} (${r.action.status}) · confidence ${(r.p * 100).toFixed(0)} % · loop ${r.ms_total} ms` }),
    el("p", { textContent: r.report }), el("small", { textContent: `text source: ${r.report_source}` }),
    el("h2", { textContent: "Evidence from code", style: "margin-top:14px" }),
    el("ul", {}, ...evidence.map((t) => el("li", { textContent: t }))));
}

/* ---------- ask the plant ---------- */
async function openAsk() {
  const sys = await api("/api/system");
  $("askmode").textContent = sys.llm ? "LFM tool calling via " + sys.llm : "no local LLM configured: rule planner calls the same tools";
  const chips = $("askchips"); chips.replaceChildren();
  for (const q of ["Which assets need attention?", "Why is SG-2 flagged?", "Open a work order for SG-1", "Open a work order for SG-2", "Confirm SG-2 with d1", "How is the board doing?"]) {
    chips.append(el("button", { textContent: q, type: "button", onclick: () => { $("askq").value = q; ask(q); } }));
  }
  $("askform").onsubmit = (e) => { e.preventDefault(); ask($("askq").value); };
}
async function ask(q) {
  if (!q.trim()) return;
  $("askgo").disabled = true;
  const out = $("askout"); out.replaceChildren(el("p", { className: "m", textContent: "asking..." }));
  try {
    const r = await api("/api/ask", { q });
    out.replaceChildren(el("p", { className: "m", textContent: `${r.mode} · ${r.ms} ms${r.error ? " · note: " + r.error : ""}` }),
      el("h2", { textContent: "Tool calls (checked by code)" }),
      ...(r.steps.length ? r.steps.map((s) => el("div", { className: "step " + (s.ok ? "okstep" : "badstep") },
        el("b", { textContent: `${s.tool}(${s.args === "{}" ? "" : s.args})` }), el("span", { textContent: s.ok ? " ran" : " refused" }), el("pre", { className: "logpre", textContent: JSON.stringify(s.result) }))) : [el("p", { className: "m", textContent: "none" })]),
      el("h2", { textContent: "Answer", style: "margin-top:14px" }), el("p", { textContent: r.answer, className: "answer" }));
  } catch (e) { out.replaceChildren(el("p", { textContent: String(e) })); }
  $("askgo").disabled = false;
}

/* ---------- edge stack ---------- */
async function openSystem() {
  const draw = async () => {
    const s = await api("/api/system"), g = $("sysgrid"); g.replaceChildren();
    const kv = (title, note, rows) => el("div", { className: "card" }, el("h2", {}, title, el("span", { className: "m", textContent: note })),
      el("dl", {}, ...rows.flatMap(([k, v]) => [el("dt", { textContent: k }), el("dd", { textContent: String(v) })])));
    const l = s.loop, h = s.host;
    g.append(
      kv("Target board", "what the demo runs on", [["Board", "Dragonwing IQ-9075 EVK"], ["OS", "Ubuntu 24.04 · aarch64"], ["NPU", "Hexagon v73 (generator)"],
        ["Generator", "LFM3-1.7B QAD-Q4_0 via GenieX, 127.0.0.1:18181"], ["Decision gate", "rule; optional d1-2B on CPU (pin 10e7671d44e4)"], ["Console", "this UI, loopback only"]]),
      kv("This host", "live, where the server runs now", [["Machine", h.machine], ["System", h.system], ["OS", h.os], ["Python", h.python], ["Load (1 min)", fmt(h.load, 2)], ["Peak RSS", h.peak_rss_mib + " MiB"], ["Uptime", h.uptime_s + " s"]]),
      kv("Loop", "live, last 300 records", [["Tick / interval", `${l.tick} / ${l.interval_s} s`], ["Records", l.records], ["Errors", l.errors],
        ["observe (median)", l.median_ms.observe + " ms"], ["rule gate", l.median_ms.decide + " ms"], ["explain", l.median_ms.explain + " ms"], ["loop total", l.median_total_ms + " ms"],
        ["Decider", s.decider], ["LLM text", s.llm || "off (template)"],
        ["d1-2B", s.d1 ? `${s.d1.state}${s.d1.load_s ? " · loaded in " + s.d1.load_s + " s" : ""} · ${s.d1.calls} calls${s.d1.error ? " · " + s.d1.error : ""}` : "off (start with --d1)"]]),
      kv("Pipeline", "observe, decide, act, explain, log", [["1 Sense", "thermal 32×24 · RGB · 4×4 mic array · load"], ["2 Analyse", "ΔT · beamformer 2-6 kHz · coherence · kurtosis"],
        ["3 Decide", "rule → d1 (optional) → allowlist"], ["4 Act", "no_op · flag_for_repair · request_reinspection"], ["5 Explain", "local LFM only on a new FAULT; numbers checked"], ["6 Log", "flushed JSONL, one line per loop"]]),
      kv("Offline design", "guarantees in code", [["UI assets", "local only, CSP default-src 'self'"], ["Server bind", "127.0.0.1 by default"], ["Model loads", "local files only"], ["Runtime installs", "none"], ["Test", "tests/test_core.py checks no external URLs"]]),
      kv("Files", "written by this run", [["Decision log", s.log_path.replace(/^.*\/out\//, "out/")], ["Work orders", s.orders_path.replace(/^.*\/out\//, "out/")]]));
  };
  await draw();
  timers.push(setInterval(() => draw().catch(() => {}), 3000));
  refreshPlant().catch(() => {});
}

/* ---------- boot ---------- */
refreshPlant().then(route).catch((e) => document.body.append(el("pre", { textContent: String(e) })));
