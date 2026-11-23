"use strict";

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const HISTORY_S = 600;

const state = {
  skus: [],
  byId: {},
  after: 0,
  prevSmoothed: null,
  history: [],
  lastMeta: null,
  drawing: false,
};

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", cache: "no-store", ...options });
  if (response.status === 401) {
    location.href = "/login";
    throw new Error("login required");
  }
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response;
}

function sku(id) {
  return state.byId[id || "UNRECOGNIZED"] || { id, short: id, name: id, color: "#8a8f98" };
}

function setChip(id, text, tone) {
  const chip = $(id);
  chip.querySelector("span").textContent = text;
  chip.dataset.tone = tone || "";
}

function buildList() {
  const list = $("sku-list");
  list.innerHTML = "";
  for (const s of state.skus) {
    const li = document.createElement("li");
    li.className = "sku zero";
    li.dataset.sku = s.id;
    li.innerHTML = `<span class="swatch" style="background:${s.color}"></span>
      <span class="name" title="${escapeHtml(s.name)}">${escapeHtml(s.short)}</span>
      <span class="raw" data-raw></span>
      <span class="count" data-count>0</span>`;
    list.appendChild(li);
  }
}

function renderCounts(meta) {
  let total = 0;
  for (const li of document.querySelectorAll("#sku-list .sku")) {
    const id = li.dataset.sku;
    const n = meta.smoothed[id] || 0;
    const raw = meta.counts[id] || 0;
    total += n;
    const countEl = li.querySelector("[data-count]");
    if (countEl.textContent !== String(n)) {
      countEl.textContent = n;
      li.classList.remove("bump");
      void li.offsetWidth; // restart the highlight animation
      li.classList.add("bump");
    }
    li.querySelector("[data-raw]").textContent = raw === n ? "" : `khung này ${raw}`;
    li.classList.toggle("zero", n === 0);
  }
  $("total").textContent = total;
  $("flagged").textContent = meta.flagged_rows
    ? `${meta.flagged_rows} dòng cần người duyệt trong khung này`
    : "Không có dòng nào cần duyệt";
}

function logChanges(meta) {
  const prev = state.prevSmoothed;
  const cur = meta.smoothed;
  if (prev) {
    const ids = new Set([...Object.keys(prev), ...Object.keys(cur)]);
    for (const id of ids) {
      const a = prev[id] || 0;
      const b = cur[id] || 0;
      if (a === b) continue;
      const s = sku(id);
      const li = document.createElement("li");
      li.innerHTML = `<time>${escapeHtml(meta.capture_timestamp.slice(11, 19))}</time>
        <span class="swatch" style="background:${s.color}"></span>
        <span class="what">${escapeHtml(s.short)}</span>
        <b>${a} → ${b}</b>
        <span class="${b < a ? "down" : "up"}">${b < a ? "▼" : "▲"} ${Math.abs(b - a)}</span>`;
      const list = $("events");
      list.prepend(li);
      while (list.children.length > 40) list.lastChild.remove();
    }
  }
  state.prevSmoothed = cur;
}

function drawFrame(meta) {
  if (state.drawing) return; // skip if the previous image is still loading
  state.drawing = true;
  const img = new Image();
  img.onload = () => {
    const canvas = $("frame");
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0);
    const k = img.naturalWidth / meta.frame_w;
    if (meta.roi) {
      const [x, y, w, h] = meta.roi;
      ctx.save();
      ctx.strokeStyle = "rgba(255,255,255,0.85)";
      ctx.setLineDash([14, 10]);
      ctx.lineWidth = 2;
      ctx.strokeRect(x * k, y * k, w * k, h * k);
      ctx.restore();
    }
    ctx.lineWidth = Math.max(2, canvas.width / 700);
    for (const d of meta.detections) {
      const [x, y, w, h] = d.box.map((v) => v * k);
      ctx.setLineDash(d.flagged ? [8, 6] : []);
      ctx.strokeStyle = d.flagged ? "#e5484d" : sku(d.sku_id).color;
      ctx.strokeRect(x, y, w, h);
    }
    ctx.setLineDash([]);
    $("empty").hidden = true;
    state.drawing = false;
  };
  img.onerror = () => { state.drawing = false; };
  img.src = `/api/frame?seq=${meta.seq}`;
}

function drawHistory() {
  const svg = $("history");
  const W = 600, H = 160, pad = 22;
  const now = state.lastMeta ? state.lastMeta.received_at : Date.now() / 1000;
  state.history = state.history.filter((p) => now - p.t <= HISTORY_S);
  const pts = state.history;
  if (pts.length < 2) { svg.innerHTML = ""; return; }
  const maxY = Math.max(5, ...pts.map((p) => p.total));
  const x = (t) => pad + (W - 2 * pad) * (1 - (now - t) / HISTORY_S);
  const y = (v) => H - pad - (H - 2 * pad) * (v / maxY);
  const line = pts.map((p) => `${x(p.t).toFixed(1)},${y(p.total).toFixed(1)}`).join(" ");
  svg.innerHTML = `
    <line class="axis" x1="${pad}" y1="${H - pad}" x2="${W - pad}" y2="${H - pad}"/>
    <line class="grid" x1="${pad}" y1="${y(maxY)}" x2="${W - pad}" y2="${y(maxY)}"/>
    <text class="tick" x="${pad}" y="${y(maxY) - 5}">${maxY}</text>
    <text class="tick" x="${pad}" y="${H - 5}">−10 phút</text>
    <text class="tick" x="${W - pad}" y="${H - 5}" text-anchor="end">mới nhất</text>
    <polyline class="line" points="${line}"/>`;
}

function onMeta(meta) {
  state.lastMeta = meta;
  drawFrame(meta);
  renderCounts(meta);
  logChanges(meta);
  state.history.push({ t: meta.received_at, total: Object.values(meta.smoothed).reduce((a, b) => a + b, 0) });
  drawHistory();
  const latency = (meta.latency_ms / 1000).toFixed(1);
  setChip("chip-latency", `Độ trễ xử lý: ${latency} s`, meta.latency_ms < 15000 ? "ok" : "warn");
  $("caption").textContent =
    `Khung lúc ${meta.capture_timestamp.slice(11, 19)} · đếm ${meta.processing_time_ms} ms · ` +
    `${meta.detections.length} hộp · ${meta.faces_blurred} khuôn mặt đã che · ${meta.capture_id}`;
  $("export-link").href = `/api/export/cv-output.csv?date=${meta.capture_timestamp.slice(0, 10)}`;
}

function renderStatus(status) {
  if (!status) return;
  const worker = status.worker || {};
  if (worker.pipeline) {
    const where = [worker.device, worker.worker].filter(Boolean).join(" · ");
    const model = worker.pipeline === "null" ? "chưa nạp" : worker.pipeline;
    setChip("chip-model", `Model: ${model}${where ? ` (${where})` : ""}`, worker.pipeline === "null" ? "warn" : "ok");
  }
  // The worker may read the stream in windows (MILK_SAMPLE_EVERY_S): between windows it is closed on purpose.
  const sampling = samplingState(status);
  if (sampling && sampling !== "live") {
    const every = worker.sampling.every_s;
    setChip("chip-rate", every >= 60 ? `${Math.round(every / 60)} phút/lượt` : `${every} giây/lượt`, "ok");
  } else if (worker.frames_last_minute !== undefined) {
    setChip("chip-rate", `${worker.frames_last_minute} khung/phút`, worker.frames_last_minute ? "ok" : "warn");
  }
  const next = worker.sampling
    ? new Date(worker.sampling.next_at * 1000).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })
    : "";
  if (!status.worker_ok) {
    setChip("chip-stream", "Bộ đếm không phản hồi", "bad");
  } else if (worker.connected) {
    const st = worker.stream || {};
    setChip("chip-stream", `Đang nhận luồng ${st.codec ? `(${st.codec.toUpperCase()} ${st.width}×${st.height})` : ""}`, "ok");
  } else if (sampling === "connecting") {
    setChip("chip-stream", "Đang mở lượt đếm…", "ok");
  } else if (sampling === "failing") {
    setChip("chip-stream", "Lượt đếm đang mở nhưng không nhận được luồng", "bad");
  } else if (sampling === "missed") {
    setChip("chip-stream", `Lượt trước không nhận được khung nào · lượt kế tiếp ${next}`, "bad");
  } else if (sampling === "waiting") {
    setChip("chip-stream", `Đếm theo nhịp · lượt kế tiếp ${next}`, "ok");
  } else {
    setChip("chip-stream", "Chưa có luồng từ camera", "bad");
  }
}

// null when the worker counts continuously; otherwise where it is in its sampling cycle:
// live (stream open), connecting (window just opened), failing (window open, stream error),
// waiting (between windows, last window got frames) or missed (last window got no frame: an outage).
function samplingState(status) {
  const worker = status.worker || {};
  const sampling = worker.sampling;
  if (!status.worker_ok || !sampling) return null;
  if (worker.connected) return "live";
  if (sampling.open) return worker.last_error ? "failing" : "connecting";
  return sampling.last_window_frames === 0 ? "missed" : "waiting";
}

async function liveLoop() {
  for (;;) {
    try {
      const data = await (await api(`/api/live?after=${state.after}`)).json();
      if (data.meta) onMeta(data.meta);
      state.after = data.seq;
      renderStatus(data.status);
    } catch (err) {
      console.warn(err);
      setChip("chip-stream", "Mất kết nối tới máy chủ", "bad");
      await sleep(2000);
    }
  }
}

async function statusLoop() {
  for (;;) {
    try {
      const s = await (await api("/api/status")).json();
      $("where").textContent = `${s.store_id} · ${s.camera_id}`;
      renderStatus(s);
      // With sampled counting MediaMTX pulls the camera only during a window; renderStatus already judged the
      // stream from the worker's report, so this check is for continuous counting only.
      if (s.ingest && !s.ingest.ready && s.worker_ok && !samplingState(s)) setChip("chip-stream", "Chưa có luồng từ camera", "bad");
    } catch (err) {
      console.warn(err);
    }
    await sleep(5000);
  }
}

async function init() {
  $("logout").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    location.href = "/login";
  });
  state.skus = await (await api("/api/skus")).json();
  state.byId = Object.fromEntries(state.skus.map((s) => [s.id, s]));
  buildList();
  try {
    const past = await (await api("/api/history?minutes=10")).json();
    state.history = past.map((p) => ({ t: p.t, total: p.total }));
  } catch (err) {
    console.warn(err);
  }
  statusLoop();
  liveLoop();
}

init();
