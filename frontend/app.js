"use strict";

const $ = (sel) => document.querySelector(sel);

let results = [];                                  // current grid
let player = { videoId: null, shots: [], idx: 0 }; // player context
let dresLoggedIn = false;                           // DRES session state

// ---------------------------------------------------------------- helpers
function fmtTime(ms) {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
function setStatus(msg) { $("#status-line").textContent = msg; }

// ---------------------------------------------------------------- search
async function doSearch(q, k) {
  setStatus(`Searching "${q}"…`);
  const t0 = performance.now();
  const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&k=${k}`);
  const data = await r.json();
  results = data.results;
  renderGrid(results);
  setStatus(`${results.length} shots for "${q}" — ${Math.round(performance.now() - t0)} ms`);
}

async function findSimilar(shotId, label) {
  setStatus("Finding similar…");
  const r = await fetch(`/api/similar?shot_id=${shotId}&k=${$("#topk").value}`);
  const data = await r.json();
  results = data.results;
  renderGrid(results);
  setStatus(`${results.length} shots similar to ${label}`);
}

// ---------------------------------------------------------------- grid
function renderGrid(items) {
  const grid = $("#grid");
  grid.innerHTML = "";
  const frag = document.createDocumentFragment();
  items.forEach((item) => {
    const cell = document.createElement("div");
    cell.className = "cell";
    cell.tabIndex = 0;
    const score = item.score > 0 ? item.score.toFixed(3) : "";
    cell.innerHTML =
      `<img loading="lazy" src="${item.keyframe_url}" alt="">` +
      `<div class="tag"><span>${item.video_id}·${item.shot_idx}</span>` +
      `<span class="score">${score}</span></div>`;
    cell.addEventListener("click", () => openPlayer(item));
    cell.addEventListener("keydown", (e) => { if (e.key === "Enter") openPlayer(item); });
    frag.appendChild(cell);
  });
  grid.appendChild(frag);
}

// ---------------------------------------------------------------- player
async function openPlayer(shot) {
  // load the whole video's shots so we can step to neighbours
  const r = await fetch(`/api/video/${shot.video_id}/shots`);
  const data = await r.json();
  player.videoId = shot.video_id;
  player.shots = data.results;
  player.idx = Math.max(0, player.shots.findIndex((s) => s.shot_id === shot.shot_id));
  $("#player-overlay").classList.remove("hidden");
  loadShot();
}

function loadShot() {
  const s = player.shots[player.idx];
  const video = $("#video");
  const seek = () => { video.currentTime = s.start_ms / 1000; video.play().catch(() => {}); };
  if (!video.src.endsWith(s.video_url)) {
    video.src = s.video_url;
    video.addEventListener("loadedmetadata", seek, { once: true });
  } else {
    seek();
  }
  $("#player-title").textContent =
    `Video ${s.video_id} — shot ${s.shot_idx} (${player.idx + 1}/${player.shots.length})`;
  $("#player-meta").textContent =
    `frames ${s.start_frame}–${s.end_frame} · ${fmtTime(s.start_ms)}–${fmtTime(s.end_ms)} · ` +
    `${s.start_ms}–${s.end_ms} ms · ${s.fps.toFixed(3)} fps` +
    (s.score > 0 ? ` · score ${s.score.toFixed(3)}` : "");
  const box = $("#submit-result");
  box.textContent = ""; box.className = "submit-result";
}

function stepShot(d) {
  player.idx = Math.max(0, Math.min(player.shots.length - 1, player.idx + d));
  loadShot();
}

function closePlayer() {
  $("#player-overlay").classList.add("hidden");
  $("#video").pause();
}

// ---------------------------------------------------------------- DRES
async function refreshDresStatus() {
  const d = await (await fetch("/api/dres/status")).json();
  const el = $("#dres-status");
  dresLoggedIn = d.logged_in;
  $("#dres-login-btn").textContent = d.logged_in ? "Disconnect" : "Login";
  if (d.logged_in) {
    el.className = "dres-status on";
    el.textContent = d.evaluation_name ? `DRES: ${d.evaluation_name}` : "DRES: connected (no task)";
  } else {
    el.className = "dres-status off";
    el.textContent = "DRES: offline";
  }
}

async function submitToDres() {
  const s = player.shots[player.idx];
  const text = $("#answer-text").value.trim() || null;
  const box = $("#submit-result");
  box.className = "submit-result"; box.textContent = "Submitting…";
  try {
    const r = await fetch("/api/dres/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shot_id: s.shot_id, text }),
    });
    const data = await r.json();
    if (r.ok && data.dres && data.dres.ok) {
      box.classList.add("ok");
      box.textContent =
        `✔ Submitted ${s.video_id} [${s.start_ms}–${s.end_ms} ms] — ` +
        `server: ${JSON.stringify(data.dres.response)}`;
    } else {
      box.classList.add("err");
      box.textContent = `✘ ${data.detail || JSON.stringify(data.dres && data.dres.response || data)}`;
    }
  } catch (e) {
    box.classList.add("err");
    box.textContent = `✘ ${e}`;
  }
}

// ---------------------------------------------------------------- wiring
$("#search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#query").value.trim();
  if (q) doSearch(q, $("#topk").value);
});

$("#player-close").addEventListener("click", closePlayer);
$("#player-overlay").addEventListener("click", (e) => {
  if (e.target.id === "player-overlay") closePlayer();
});
$("#btn-prev").addEventListener("click", () => stepShot(-1));
$("#btn-next").addEventListener("click", () => stepShot(1));
$("#btn-similar").addEventListener("click", () => {
  const s = player.shots[player.idx];
  closePlayer();
  findSimilar(s.shot_id, `${s.video_id}·${s.shot_idx}`);
});
$("#btn-submit").addEventListener("click", submitToDres);

// DRES login / disconnect (the button toggles based on session state)
$("#dres-login-btn").addEventListener("click", async () => {
  if (dresLoggedIn) {
    await fetch("/api/dres/logout", { method: "POST" });
    refreshDresStatus();
  } else {
    $("#login-overlay").classList.remove("hidden");
  }
});
$("#login-cancel").addEventListener("click", () => $("#login-overlay").classList.add("hidden"));
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#login-msg");
  msg.className = "login-msg"; msg.textContent = "Connecting…";
  const r = await fetch("/api/dres/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: $("#dres-user").value, password: $("#dres-pass").value }),
  });
  const data = await r.json();
  if (r.ok && data.ok) {
    msg.classList.add("ok");
    if (data.evaluation_name) {
      msg.textContent = `Connected — active task "${data.evaluation_name}".`;
    } else {
      msg.textContent =
        "Connected — login OK. No task is running yet; it will be picked up " +
        "automatically when the instructor starts one.";
    }
    refreshDresStatus();
    setTimeout(() => $("#login-overlay").classList.add("hidden"),
               data.evaluation_name ? 900 : 2600);
  } else {
    msg.classList.add("err");
    msg.textContent = `Failed: ${data.detail || "unknown error"}`;
  }
});

// keyboard shortcuts
document.addEventListener("keydown", (e) => {
  const playerOpen = !$("#player-overlay").classList.contains("hidden");
  const typing = ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName);
  if (playerOpen) {
    if (e.key === "Escape") closePlayer();
    else if (e.key === "[") stepShot(-1);
    else if (e.key === "]") stepShot(1);
    else if (!typing && (e.key === "s" || e.key === "S")) submitToDres();
    else if (!typing && (e.key === "f" || e.key === "F")) $("#btn-similar").click();
  } else if (e.key === "/" && !typing) {
    e.preventDefault(); $("#query").focus();
  }
});

refreshDresStatus();
setInterval(refreshDresStatus, 10000);   // auto-pick up a task once it starts
