/* ============================================================================
   AutoCast — Cutting Room desk logic.
   Reads the committed spine (manifest.json + per-run run.json + queue) and
   drives the write path (queue edit + render dispatch) with zero server:
   a user-supplied GitHub token (localStorage) → live API, else a copy +
   Edit-on-GitHub deep-link fallback. No secret is ever committed.
   ========================================================================== */
(() => {
  "use strict";

  // ── repo wiring ───────────────────────────────────────────────────────
  const REPO = "veyron007/autocast";
  const BRANCH = "main";
  const WORKFLOW = "daily.yml";
  const RAW = `https://raw.githubusercontent.com/${REPO}/${BRANCH}`;
  const API = `https://api.github.com/repos/${REPO}`;
  const TOKEN_KEY = "autocast_gh_token";

  // Canonical stage order — the spine's backbone (mirrors orchestrator.py).
  const STAGE_ORDER = ["topic","script","direction","images","tts","assets","video","thumbnail","upload"];
  const MOTION_GLYPH = { zoom_in:"⊕", zoom_out:"⊖", pan_right:"→", pan_left:"←", static:"▪", tilt_up:"↑", tilt_down:"↓" };

  // ── tiny DOM + fmt helpers ────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls) => { const n = document.createElement(tag); if (cls) n.className = cls; return n; };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
  const secTC = (s) => {
    if (s == null || isNaN(s)) return "--:--";
    const t = Math.round(s); return `${Math.floor(t/60)}:${String(t%60).padStart(2,"0")}`;
  };
  const bytes = (b) => b == null ? "—" : b > 1e6 ? `${(b/1e6).toFixed(1)} MB` : `${Math.round(b/1e3)} KB`;
  const b64 = (str) => btoa(unescape(encodeURIComponent(str)));

  // ── state ─────────────────────────────────────────────────────────────
  let DATA_BASE = null;         // set to RAW or ".." on first successful fetch
  let manifest = [];            // [{run_id,title,status,...}] newest-first
  let selectedId = null;
  let queueDoc = { _comment: "", queued: [] };  // preserve _comment on save
  let queueDirty = false;

  const token = () => localStorage.getItem(TOKEN_KEY) || "";
  const ghHeaders = () => ({
    "Authorization": `Bearer ${token()}`,
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Content-Type": "application/json",
  });

  // ── data fetch: raw GitHub (CORS-ok, always the committed truth), with a
  //    relative fallback so a locally-served copy from the repo root works. ──
  async function fetchJSON(rel) {
    const bases = DATA_BASE ? [DATA_BASE, RAW, ".."].filter((b,i,a)=>a.indexOf(b)===i)
                            : [RAW, ".."];
    let lastErr;
    for (const base of bases) {
      try {
        const bust = base.startsWith("http") ? `?t=${Date.now()}` : "";
        const r = await fetch(`${base}/${rel}${bust}`, { cache: "no-store" });
        if (r.ok) { DATA_BASE = base; return r.json(); }
        lastErr = new Error(`${r.status} on ${rel}`);
      } catch (e) { lastErr = e; }
    }
    throw lastErr || new Error(`could not load ${rel}`);
  }
  const assetURL = (runId, rel) => `${DATA_BASE || RAW}/runs/${runId}/${rel}`;

  // ── toast ─────────────────────────────────────────────────────────────
  let toastT;
  function toast(msg, kind = "info") {
    const t = $("toast");
    t.textContent = msg; t.dataset.kind = kind; t.hidden = false;
    requestAnimationFrame(() => (t.dataset.show = "1"));
    clearTimeout(toastT);
    toastT = setTimeout(() => { t.dataset.show = "0"; setTimeout(() => (t.hidden = true), 350); }, 4200);
  }

  // ══ BOOT ═══════════════════════════════════════════════════════════════
  async function boot() {
    wireStaticUI();
    try {
      manifest = await fetchJSON("runs/manifest.json");
      manifest = (Array.isArray(manifest) ? manifest : [])
        .slice().sort((a, b) => String(b.run_id).localeCompare(String(a.run_id)));
    } catch (e) {
      $("filmstrip").innerHTML = `<div class="frame--empty">Could not reach the reel (${esc(e.message)}).<br>Is the repo public and pushed?</div>`;
      $("chStatus").textContent = "OFFLINE";
    }

    // data-source lamp
    const live = DATA_BASE === RAW;
    $("srcLamp").className = `lamp ${live ? "lamp--green" : "lamp--amber"}`;
    $("srcText").textContent = live ? "LIVE" : "LOCAL";

    renderReel();
    await computeChannelStatus();
    if (manifest.length) select(manifest[0].run_id);
    await loadQueue();

    document.documentElement.dataset.boot = "ready";
  }

  // ── channel bug: derive live status from the newest run's spine ────────
  async function computeChannelStatus() {
    $("reelCount").textContent = manifest.length
      ? `${manifest.length} run${manifest.length > 1 ? "s" : ""} on file`
      : "no runs yet";
    if (!manifest.length) { $("chStatus").textContent = "STANDBY"; return; }
    const newest = manifest[0];
    $("lastCut").textContent = newest.run_id;
    try {
      const run = await fetchJSON(`runs/${newest.run_id}/run.json`);
      const st = run.stages || [];
      const has = (s) => st.some((x) => x.status === s);
      const rec = $("recLamp"), ch = $("chStatus");
      if (has("running"))       { ch.textContent = "● RENDERING";  ch.style.color = "var(--safelight)"; rec.hidden = false; }
      else if (has("failed"))   { ch.textContent = "CUT · FAILED"; ch.style.color = "var(--cut)";        rec.hidden = true; }
      else {
        const up = st.find((x) => x.name === "upload");
        const onair = up && up.status === "completed";
        ch.textContent = onair ? "ON AIR" : "RENDERED"; ch.style.color = "var(--signal)"; rec.hidden = true;
      }
      const len = run.video && run.video.duration_s;
      if (len) $("lastCut").textContent = `${newest.run_id} · ${secTC(len)}`;
    } catch { $("chStatus").textContent = String(newest.status || "—").toUpperCase(); }
  }

  // ══ THE REEL ═══════════════════════════════════════════════════════════
  function renderReel() {
    const strip = $("filmstrip");
    strip.innerHTML = "";
    if (!manifest.length) {
      strip.innerHTML = `<div class="frame--empty">The reel is empty. The daily cron writes the first frame at 06:00 UTC.</div>`;
      return;
    }
    manifest.forEach((r, i) => {
      const f = el("div", "frame");
      f.style.setProperty("--i", i);
      f.setAttribute("role", "option");
      f.tabIndex = 0;
      f.dataset.id = r.run_id;
      f.setAttribute("aria-selected", "false");

      const thumb = el("div", "frame__thumb");
      if (r.thumb_path) {
        const img = new Image();
        img.loading = "lazy"; img.alt = "";
        img.src = assetURL(r.run_id, r.thumb_path);
        img.onerror = () => { thumb.innerHTML = `<span class="frame__thumb-fallback">▦</span>`; };
        thumb.appendChild(img);
      } else {
        thumb.innerHTML = `<span class="frame__thumb-fallback">▦</span>`;
      }

      const body = el("div", "frame__body");
      const st = String(r.status || "").toLowerCase();
      const lampCls = st === "failed" ? "lamp--red"
        : (st === "rendered" || st === "uploaded" || st === "public") ? "lamp--green" : "lamp--dim";
      body.innerHTML =
        `<span class="frame__date"><span class="lamp ${lampCls}"></span>${esc(r.run_id)} · ${esc(st || "—")}</span>` +
        `<h3 class="frame__title">${esc(r.title || "untitled")}</h3>`;

      f.append(thumb, body);
      f.addEventListener("click", () => select(r.run_id));
      f.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(r.run_id); }
      });
      strip.appendChild(f);
    });
  }

  // ══ SELECT + DETAIL ════════════════════════════════════════════════════
  async function select(runId) {
    selectedId = runId;
    document.querySelectorAll(".frame").forEach((f) =>
      f.setAttribute("aria-selected", String(f.dataset.id === runId)));
    $("controlNote").textContent = `Target: ${runId}. Resumes a failed/partial run in CI; a finished run is a no-op.`;

    let run;
    try { run = await fetchJSON(`runs/${runId}/run.json`); }
    catch (e) { toast(`Couldn't load ${runId}: ${e.message}`, "err"); return; }

    $("detailEmpty").hidden = true;
    $("run").hidden = false;

    $("runDate").textContent = run.run_id;
    const statusPill = $("runStatus");
    const manRun = manifest.find((m) => m.run_id === runId) || {};
    const failed = (run.stages || []).some((s) => s.status === "failed");
    const running = (run.stages || []).some((s) => s.status === "running");
    const sVal = failed ? "failed" : running ? "running" : (manRun.status || "rendered");
    statusPill.textContent = sVal; statusPill.dataset.s = sVal;
    const priv = $("runPrivacy");
    priv.textContent = (run.upload && run.upload.privacy) || manRun.privacy || "private";

    $("runTitle").textContent = run.topic?.title || run.upload?.title || manRun.title || "untitled";
    const wc = run.script?.word_count;
    $("runMeta").innerHTML =
      `source <b style="color:var(--paper)">${esc(run.topic?.source || "—")}</b> · ` +
      `${(run.shots || []).length} shots · ${secTC(run.video?.duration_s)} runtime` +
      (wc ? ` · ${wc} words` : "");

    renderChain(run.stages || []);
    renderBoard(run.shots || []);
    renderScript(run.script || {});
    renderPublish(run);
    renderConfig(run);
  }

  // ── the nine-stage signal chain (hero) ─────────────────────────────────
  function renderChain(stages) {
    const byName = Object.fromEntries(stages.map((s) => [s.name, s]));
    const chain = $("chain");
    chain.innerHTML = "";
    const passed = (s) => s && (s.status === "completed" || s.status === "skipped");
    STAGE_ORDER.forEach((name, i) => {
      const s = byName[name] || { name, status: "pending", provider_used: null };
      const li = el("li", "node");
      li.style.setProperty("--i", i);
      li.dataset.status = s.status;
      li.dataset.flow = passed(byName[STAGE_ORDER[i - 1]]) ? "on" : "off";

      const lamp = s.status === "completed" ? "lamp--green"
        : s.status === "running" ? "lamp--amber"
        : s.status === "failed" ? "lamp--red" : "lamp--dim";
      const prov = s.provider_used
        || (s.status === "skipped" ? "skipped" : s.status === "failed" ? "error" : s.status === "pending" ? "queued" : "—");

      li.innerHTML =
        `<span class="node__wire"></span>` +
        `<span class="node__dot"><span class="lamp node__lamp ${lamp}"></span></span>` +
        `<span class="node__name">${esc(name)}</span>` +
        `<span class="node__prov" title="${esc(s.error || prov)}">${esc(prov)}</span>`;
      chain.appendChild(li);
    });
  }

  // ── storyboard (shots) ─────────────────────────────────────────────────
  function renderBoard(shots) {
    const wrap = $("boardWrap"), grid = $("board");
    if (!shots.length) { wrap.hidden = true; return; }
    wrap.hidden = false;
    $("boardHint").textContent = `${shots.length} frames · storyboard from the spine`;
    grid.innerHTML = "";
    shots.forEach((sh) => {
      const card = el("div", "shot");
      const motion = MOTION_GLYPH[sh.motion] || "▪";
      const tc = secTC(sh.audio_start_s ?? 0);
      card.innerHTML =
        `<div class="shot__cell">` +
          `<span class="shot__idx">SH_${String(sh.idx ?? 0).padStart(3, "0")}</span>` +
          `<span class="shot__motion" title="${esc(sh.motion || "static")}">${motion}</span>` +
          `<span class="shot__cap">${esc(sh.caption || "")}</span>` +
          `<span class="shot__tc">${tc}</span>` +
        `</div>` +
        `<div class="shot__body">` +
          `<p class="shot__narr">${esc(sh.narration || "")}</p>` +
          `<p class="shot__prompt"><b>PROMPT</b> ${esc(sh.image_prompt || "—")}</p>` +
        `</div>`;
      grid.appendChild(card);
    });
  }

  function renderScript(script) {
    const wrap = $("scriptWrap");
    if (!script.full_text) { wrap.hidden = true; return; }
    wrap.hidden = false;
    $("scriptHint").textContent = script.provider ? `via ${script.provider}` : "";
    $("scriptBody").textContent = script.full_text;
  }

  function renderPublish(run) {
    const wrap = $("publishWrap"), kv = $("publishKv");
    const up = run.upload || {};
    const stage = (run.stages || []).find((s) => s.name === "upload") || {};
    wrap.hidden = false;
    const rows = [];
    if (up.youtube_video_id) {
      rows.push(["youtube", `<a href="https://youtu.be/${esc(up.youtube_video_id)}" target="_blank" rel="noopener" class="v--green">${esc(up.youtube_video_id)}</a>`]);
    } else {
      const cls = stage.status === "failed" ? "v--red" : "v--amber";
      rows.push(["publish", `<span class="${cls}">${esc(stage.status || "pending")}</span>`]);
    }
    rows.push(["privacy", esc(up.privacy || "private")]);
    rows.push(["AI disclosure", up.ai_disclosure ? `<span class="v--green">on</span>` : "off"]);
    rows.push(["thumbnail", run.thumbnail?.path ? `${run.thumbnail.width}×${run.thumbnail.height}` : "—"]);
    if (stage.error && !up.youtube_video_id) {
      rows.push(["gate", `<span class="v--amber" title="${esc(stage.error)}">${esc(shortErr(stage.error))}</span>`]);
    }
    kv.innerHTML = rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join("");
  }
  const shortErr = (e) => { const s = String(e).split("—")[0].split("(")[0].trim(); return s.length > 40 ? s.slice(0, 40) + "…" : s; };

  function renderConfig(run) {
    const cfg = run.config_snapshot || {}, v = run.video || {};
    const rows = [
      ["voice", cfg.voice || "—"],
      ["aspect", cfg.aspect || (v.width ? `${v.width}×${v.height}` : "—")],
      ["fps", v.fps || "—"],
      ["target", cfg.target_len_s ? `${cfg.target_len_s}s` : "—"],
      ["render", secTC(v.duration_s)],
      ["size", bytes(v.size_bytes)],
    ];
    $("configKv").innerHTML = rows.map(([k, val]) =>
      `<div><span class="k">${esc(k)}</span><span class="v">${esc(val)}</span></div>`).join("");
  }

  // ══ CUE SHEET (topic queue) ════════════════════════════════════════════
  async function loadQueue() {
    try { queueDoc = await fetchJSON("queue/topics.json"); }
    catch { queueDoc = { _comment: "", queued: [] }; }
    if (!Array.isArray(queueDoc.queued)) queueDoc.queued = [];
    queueDirty = false;
    renderCue();
  }

  function renderCue() {
    const list = $("cueList");
    list.innerHTML = "";
    if (!queueDoc.queued.length) {
      list.innerHTML = `<li class="cue__empty">Empty — the topic stage falls back to Google Trends, then the rotating seeds.</li>`;
    }
    queueDoc.queued.forEach((title, i) => {
      const li = el("li", "cue__item");
      li.style.setProperty("--i", i);
      li.innerHTML =
        `<span class="cue__num">${i + 1}</span>` +
        `<span class="cue__text" title="${esc(title)}">${esc(title)}</span>` +
        `<span class="cue__ctrls">` +
          `<button class="cue__mini" data-act="up" ${i === 0 ? "disabled" : ""} aria-label="Move up">↑</button>` +
          `<button class="cue__mini" data-act="down" ${i === queueDoc.queued.length - 1 ? "disabled" : ""} aria-label="Move down">↓</button>` +
          `<button class="cue__mini cue__mini--del" data-act="del" aria-label="Remove">✕</button>` +
        `</span>`;
      li.querySelectorAll("[data-act]").forEach((btn) =>
        btn.addEventListener("click", () => cueOp(btn.dataset.act, i)));
      list.appendChild(li);
    });
    $("cueDirty").hidden = !queueDirty;
  }

  function cueOp(act, i) {
    const q = queueDoc.queued;
    if (act === "del") q.splice(i, 1);
    else if (act === "up" && i > 0) { [q[i - 1], q[i]] = [q[i], q[i - 1]]; }
    else if (act === "down" && i < q.length - 1) { [q[i + 1], q[i]] = [q[i], q[i + 1]]; }
    queueDirty = true; renderCue();
  }

  function addCue(e) {
    e.preventDefault();
    const inp = $("cueInput");
    const val = inp.value.trim();
    if (!val) return;
    queueDoc.queued.push(val.slice(0, 100));
    inp.value = ""; queueDirty = true; renderCue();
  }

  // ══ WRITE PATH ═════════════════════════════════════════════════════════
  async function saveQueue() {
    const body = JSON.stringify(
      { _comment: queueDoc._comment || "Human-editable topic queue. topic stage reads it; the desk writes it.",
        queued: queueDoc.queued }, null, 2) + "\n";

    if (!token()) {   // fallback: clipboard + Edit-on-GitHub deep link
      try { await navigator.clipboard.writeText(body); } catch {}
      window.open(`https://github.com/${REPO}/edit/${BRANCH}/queue/topics.json`, "_blank", "noopener");
      toast("No token set → JSON copied to clipboard. Paste it on the GitHub editor tab & commit.", "info");
      return;
    }
    const btn = $("saveQueueBtn"); btn.disabled = true; btn.textContent = "Saving…";
    try {
      let sha;
      const g = await fetch(`${API}/contents/queue/topics.json?ref=${BRANCH}`, { headers: ghHeaders() });
      if (g.ok) sha = (await g.json()).sha;
      const p = await fetch(`${API}/contents/queue/topics.json`, {
        method: "PUT", headers: ghHeaders(),
        body: JSON.stringify({ message: "chore(queue): update cue sheet via desk", content: b64(body), sha, branch: BRANCH }),
      });
      if (!p.ok) throw new Error(`${p.status} ${(await p.text()).slice(0, 120)}`);
      queueDirty = false; renderCue();
      toast("Cue sheet committed to the repo. ✓", "ok");
    } catch (e) { toast(`Save failed: ${e.message}`, "err"); }
    finally { btn.disabled = false; btn.textContent = "Save cue sheet →"; }
  }

  async function dispatchRender() {
    const runId = selectedId || "";
    if (!token()) {
      window.open(`https://github.com/${REPO}/actions/workflows/${WORKFLOW}`, "_blank", "noopener");
      toast(`No token → opening Actions. Click "Run workflow"${runId ? ` and set run_id = ${runId}` : ""}.`, "info");
      return;
    }
    const btn = $("renderBtn"); btn.disabled = true; btn.textContent = "Dispatching…";
    try {
      const r = await fetch(`${API}/actions/workflows/${WORKFLOW}/dispatches`, {
        method: "POST", headers: ghHeaders(),
        body: JSON.stringify({ ref: BRANCH, inputs: runId ? { run_id: runId } : {} }),
      });
      if (r.status !== 204) throw new Error(`${r.status} ${(await r.text()).slice(0, 120)}`);
      toast(`Render dispatched for ${runId || "today"}. Watch the Actions tab.`, "ok");
    } catch (e) { toast(`Dispatch failed: ${e.message}`, "err"); }
    finally { btn.disabled = false; btn.textContent = "▶ Render / retry a run"; }
  }

  // ══ ACCESS MODAL ═══════════════════════════════════════════════════════
  function openModal() {
    $("tokenInput").value = token();
    $("modal").hidden = false;
    $("tokenInput").focus();
  }
  const closeModal = () => ($("modal").hidden = true);

  function saveToken() {
    const t = $("tokenInput").value.trim();
    if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY);
    reflectAccess();
    closeModal();
    toast(t ? "Token stored in this browser only. Writes go live." : "Token cleared.", t ? "ok" : "info");
  }
  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
    $("tokenInput").value = "";
    reflectAccess();
    toast("Token cleared. Writes fall back to copy + deep-link.", "info");
  }
  function reflectAccess() {
    const on = !!token();
    $("keyBtn").textContent = on ? "⚿ WRITE ON" : "⚿ ACCESS";
    $("keyBtn").style.color = on ? "var(--signal)" : "";
  }

  // ══ WIRING ═════════════════════════════════════════════════════════════
  function wireStaticUI() {
    $("repoLink").href = `https://github.com/${REPO}`;
    $("refreshBtn").addEventListener("click", async () => {
      toast("Re-pulling committed state…", "info");
      manifest = []; DATA_BASE = null;
      await boot();
    });
    $("keyBtn").addEventListener("click", openModal);
    $("cueForm").addEventListener("submit", addCue);
    $("saveQueueBtn").addEventListener("click", saveQueue);
    $("renderBtn").addEventListener("click", dispatchRender);
    $("saveTokenBtn").addEventListener("click", saveToken);
    $("clearTokenBtn").addEventListener("click", clearToken);
    document.querySelectorAll("[data-close]").forEach((n) => n.addEventListener("click", closeModal));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
    reflectAccess();
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
