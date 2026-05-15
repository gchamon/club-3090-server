// Core state and DOM helpers
const searchState = {
  active: false,
  query: "",
  matches: [],
  index: -1,
  prevAutoscroll: true,
};
let lastStatus = null;
let activeTabName = "overview";
let showGlobalLogs = true;
let currentLogSource = "docker";
let lastWindowFocused = typeof document.hasFocus === "function" ? document.hasFocus() : true;
let lastSwitchNotificationKey = "";
function $(id) {
  return document.getElementById(id);
}
function setMsg(t) {
  $("msg").textContent = t || "";
}
function messageText(value) {
  const raw = String(value || "").trim();
  return raw.startsWith("Error: ") ? raw.slice(7) : raw;
}
function joinMessageParts(parts = []) {
  return parts
    .map((part) => messageText(part))
    .filter(Boolean)
    .join(" | ");
}
function setElementMsg(id, text, tone = "warning") {
  const node = $(id);
  if (!node) return;
  const nextText = String(text || "");
  node.textContent = nextText;
  node.classList.remove("msg-error", "msg-warning", "msg-success");
  if (!nextText) return;
  const nextTone = String(tone || "warning").trim().toLowerCase();
  if (nextTone === "error" || nextTone === "success" || nextTone === "warning") {
    node.classList.add(`msg-${nextTone}`);
  }
}
function windowIsFocused() {
  return !!lastWindowFocused && !document.hidden;
}
async function ensureNotificationPermission() {
  if (typeof Notification === "undefined") return "unsupported";
  if (Notification.permission === "granted") return "granted";
  if (Notification.permission === "denied") return "denied";
  try {
    return await Notification.requestPermission();
  } catch (e) {
    return "error";
  }
}
async function showBrowserNotification(title, body) {
  const heading = String(title || "Club-3090");
  const message = String(body || "").trim();
  const permission = await ensureNotificationPermission();
  if (permission === "granted" && typeof Notification !== "undefined") {
    try {
      new Notification(heading, { body: message, tag: "club3090-runtime" });
      return;
    } catch (e) {}
  }
  if (permission === "unsupported") {
    window.alert(`${heading}\n\n${message}`);
  }
}
window.addEventListener("focus", () => {
  lastWindowFocused = true;
});
window.addEventListener("blur", () => {
  lastWindowFocused = false;
});
document.addEventListener("visibilitychange", () => {
  lastWindowFocused = typeof document.hasFocus === "function" ? document.hasFocus() : !document.hidden;
});

// Log search, formatting, and GPU cards
function clearLog() {
  const signature = currentLogSignature || logStreamConfig().signature;
  const entry = logCacheEntry(signature);
  entry.text = "";
  entry.loaded = true;
  renderCurrentLog(signature);
}
function appendLog(t) {
  const signature = currentLogSignature || logStreamConfig().signature;
  appendLogChunk(signature, `${t}\n`);
}
function clearOrCancelLog() {
  if (searchState.active) cancelSearch();
  else clearLog();
}
function recalculateMatches(keepIndex = true) {
  const q = $("searchQuery").value;
  if (!searchState.active || !q) return;
  const text = $("log").value.toLowerCase(),
    needle = q.toLowerCase();
  let pos = 0,
    m = [];
  while (needle && true) {
    const i = text.indexOf(needle, pos);
    if (i < 0) break;
    m.push(i);
    pos = i + needle.length;
  }
  searchState.matches = m;
  if (!m.length) {
    searchState.index = -1;
  } else if (keepIndex) {
    searchState.index = Math.min(Math.max(searchState.index, 0), m.length - 1);
  } else {
    searchState.index = 0;
  }
  updateSearchUI(false);
}
function runSearchOrNext() {
  if (searchState.active && searchState.matches.length) {
    nextMatch();
    return;
  }
  const q = $("searchQuery").value;
  if (!q) return;
  searchState.prevAutoscroll = $("autoscroll").checked;
  searchState.active = true;
  $("autoscroll").checked = false;
  $("autoscroll").disabled = true;
  recalculateMatches(false);
  if (searchState.matches.length) gotoMatch(0);
  else updateSearchUI(false);
}
function gotoMatch(i) {
  if (!searchState.matches.length) return;
  searchState.index =
    (i + searchState.matches.length) % searchState.matches.length;
  const start = searchState.matches[searchState.index],
    end = start + searchState.query.length;
  const log = $("log");
  log.focus();
  log.setSelectionRange(start, end);
  const lineHeight = 16;
  const before = log.value.slice(0, start).split("\n").length - 1;
  log.scrollTop = Math.max(0, before * lineHeight - log.clientHeight / 2);
  updateSearchUI(false);
}
function nextMatch() {
  if (!searchState.active || !searchState.matches.length) return;
  gotoMatch(searchState.index + 1);
}
function previousMatch() {
  if (!searchState.active || !searchState.matches.length) return;
  gotoMatch(searchState.index - 1);
}
function cancelSearch() {
  searchState.active = false;
  searchState.query = "";
  searchState.matches = [];
  searchState.index = -1;
  $("searchQuery").value = "";
  $("autoscroll").disabled = false;
  $("autoscroll").checked = searchState.prevAutoscroll;
  $("log").setSelectionRange($("log").selectionStart, $("log").selectionStart);
  updateSearchUI(true);
}
function updateSearchUI(reset) {
  if (searchState.active) {
    searchState.query = $("searchQuery").value;
    $("searchPrev").disabled = searchState.matches.length < 2;
    $("searchNext").textContent = searchState.matches.length > 1 ? "⏩" : "🔍";
    $("refreshBtn").disabled = true;
    $("refreshBtn").textContent = searchState.matches.length
      ? `${searchState.index + 1}/${searchState.matches.length}`
      : "0/0";
    $("clearBtn").textContent = "❌";
  } else {
    $("searchPrev").disabled = true;
    $("searchNext").textContent = "🔍";
    $("refreshBtn").disabled = false;
    $("refreshBtn").textContent = "♻️";
    $("clearBtn").textContent = "🗑️";
  }
}
function fmtUptime(s) {
  s = Number(s || 0);
  return Math.floor(s / 3600) + "h " + Math.floor((s % 3600) / 60) + "m";
}
function mibToGiB(v) {
  return (Number(v || 0) / 1024).toFixed(2);
}
function inferGpuStatus(g) {
  const u = Number(g.util_pct || 0);
  if (
    lastStatus &&
    lastStatus.metrics &&
    lastStatus.metrics.active_requests > 0
  ) {
    return u > 20 ? "Token Generation" : "Prompt Processing";
  }
  return u > 5 ? "Active" : "Idle";
}
function tempClass(t) {
  t = Number(t || 0);
  if (t < 35) return "temp-blue";
  if (t < 50) return "temp-green";
  if (t < 60) return "temp-yellow";
  if (t < 70) return "temp-orange";
  if (t < 80) return "temp-red";
  return "temp-crimson";
}
function trimFormattedNumber(text) {
  return String(text || "").replace(/(\.\d*?[1-9])0+$|\.0+$/, "$1");
}
function formatTempWithPeak(current, peak) {
  const currentText = formatMaybeNumber(current, 0);
  if (!currentText) return "N/A";
  const currentWarn = Number(current || 0) >= 80 ? " ⚠️" : "";
  const peakText = formatMaybeNumber(peak, 0);
  if (!peakText)
    return `<span class="${tempClass(current)}">${currentText}°C${currentWarn}</span>`;
  const peakWarn = Number(peak || 0) >= 80 ? " ⚠️" : "";
  return `<span class="${tempClass(current)}">${currentText}°C${currentWarn}</span> <span class="${tempClass(peak)}">( ${peakText}°↑ C${peakWarn})</span>`;
}
const gpuStatusHistoryByIndex = {};
const runtimeStatusHistoryById = {};
const runtimePerfHistoryById = {};
function formatMaybeNumber(value, digits = 2) {
  const num = Number(value);
  if (Number.isFinite(num)) return trimFormattedNumber(num.toFixed(digits));
  const raw = String(value || "").trim();
  return raw && raw !== "N/A" && raw !== "[Not Supported]" ? raw : "";
}
function formatGpuMetricWithPeak(current, peak, unit, digits = 2) {
  const currentText = formatMaybeNumber(current, digits);
  if (!currentText) return "N/A";
  const peakText = formatMaybeNumber(peak, digits);
  return `${currentText} ${unit}${peakText ? ` ( ${peakText}&uarr; ${unit})` : ""}`;
}
function updateStatusHistory(store, key, nextStatus) {
  const normalizedKey = String(key || "").trim();
  const status = String(nextStatus || "").trim();
  if (!normalizedKey || !status) return { current: status, previous: "" };
  const existing = store[normalizedKey] || { current: "", previous: "" };
  if (existing.current && existing.current !== status) {
    store[normalizedKey] = { current: status, previous: existing.current };
  } else if (!existing.current) {
    store[normalizedKey] = { current: status, previous: existing.previous || "" };
  }
  const resolved = store[normalizedKey] || { current: status, previous: "" };
  return {
    current: status,
    previous:
      resolved.previous && resolved.previous !== status ? resolved.previous : "",
  };
}
function runtimePerfHistoryKey(runtime) {
  return `${String(runtime?.id || runtime?.instance_id || runtime?.container || "").trim()}::${String(runtime?.selector || runtime?.mode || "").trim()}`;
}
function updateRuntimePerfHistory(runtime) {
  const key = runtimePerfHistoryKey(runtime);
  if (!key || key === "::") return { promptPeak: 0, generationPeak: 0 };
  const existing = runtimePerfHistoryById[key] || { promptPeak: 0, generationPeak: 0 };
  const promptTps = Number(runtime?.prompt_tps || 0);
  const generationTps = Number(
    runtime?.generation_tps ?? runtime?.last_tokens_per_second ?? 0,
  );
  if (promptTps > 0) existing.promptPeak = Math.max(Number(existing.promptPeak || 0), promptTps);
  if (generationTps > 0)
    existing.generationPeak = Math.max(
      Number(existing.generationPeak || 0),
      generationTps,
    );
  runtimePerfHistoryById[key] = existing;
  return existing;
}
function runtimeActivityStatus(runtime) {
  const running = Number(runtime?.running_requests || 0);
  const waiting = Number(runtime?.waiting_requests || 0);
  const pending = Number(runtime?.pending_requests || 0);
  const swapped = Number(runtime?.swapped_requests || 0);
  const generationTps = Number(runtime?.generation_tps || 0);
  const lastTps = Number(runtime?.last_tokens_per_second || 0);
  if ((running > 0 || waiting > 0 || pending > 0 || swapped > 0) && (generationTps > 0.1 || lastTps > 0.1))
    return "Generation";
  if (running > 0 || waiting > 0 || pending > 0 || swapped > 0)
    return "Prompt Processing";
  return "Idle";
}
function renderGpuCards(gs) {
  if (!gs || !gs.length) {
    $("gpuCards").innerHTML = '<div class="panel">No GPU data</div>';
    return;
  }
  $("gpuCards").innerHTML = gs
    .map((g) =>
      g.error
        ? `<div class="gpu-card">${g.error}</div>`
        : (() => {
            const statusHistory = updateStatusHistory(
              gpuStatusHistoryByIndex,
              g.index,
              inferGpuStatus(g),
            );
            const currentStatus = statusHistory.current;
            const previousStatus = statusHistory.previous;
            return `<div class="gpu-card"><div class="gpu-title">GPU ${g.index} - ${g.name || "RTX 3090"}${g.vendor ? " (" + g.vendor + ")" : ""}</div><div class="gpu-grid"><div><div class="gpu-section-title">Temperature</div><div class="gpu-line"><span>Core</span><b>${formatTempWithPeak(g.temp_c, g.temp_peak_c)}</b></div></div><div><div class="gpu-section-title">VRAM</div><div class="gpu-line"><span>Free</span><b>${mibToGiB(g.mem_free_mib)} GB</b></div><div class="gpu-line"><span>Used</span><b>${mibToGiB(g.mem_used_mib)} GB</b></div><div class="gpu-line"><span>Max</span><b>${mibToGiB(g.mem_total_mib)} GB</b></div><div class="meter"><span style="width:${Number(g.mem_pct || 0)}%"></span></div></div><div><div class="gpu-section-title">Power</div><div class="gpu-line"><span>Draw</span><b>${formatGpuMetricWithPeak(g.power_w, g.power_peak_w, "W", 2)}</b></div><div class="gpu-line"><span>Max Power</span><b>${g.power_limit_w || "N/A"} W</b></div></div><div><div class="gpu-section-title">Fans</div><div class="gpu-line"><span>Speed</span><b>${g.fan_pct || "N/A"}%</b></div></div><div><div class="gpu-section-title">Clocks</div><div class="gpu-line"><span>Core</span><b>${formatGpuMetricWithPeak(g.core_clock_mhz, g.core_clock_peak_mhz, "MHz", 0)}</b></div><div class="gpu-line"><span>Mem</span><b>${formatGpuMetricWithPeak(g.mem_clock_mhz, g.mem_clock_peak_mhz, "MHz", 0)}</b></div></div><div><div class="gpu-section-title">Usage</div><div class="gpu-line"><span>Load</span><b>${g.util_pct || "N/A"}%</b></div><div class="gpu-line"><span>Status</span><b>${currentStatus}${previousStatus ? ` (Previous: ${previousStatus})` : ""}</b></div></div></div></div>`;
          })(),
    )
    .join("");
}
let editingPresetName = null;
function presetParamSummary(params) {
  params = params || {};
  const bits = [];
  [
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "presence_penalty",
    "frequency_penalty",
    "repetition_penalty",
    "length_penalty",
    "max_tokens",
    "max_completion_tokens",
    "min_tokens",
    "truncate_prompt_tokens",
    "logprobs",
    "top_logprobs",
  ].forEach((k) => {
    if (params[k] !== undefined && params[k] !== null && params[k] !== "")
      bits.push(`${k}: ${params[k]}`);
  });
  if (params.ignore_eos !== undefined)
    bits.push(`ignore_eos: ${params.ignore_eos ? "on" : "off"}`);
  if (params.skip_special_tokens !== undefined)
    bits.push(`skip special: ${params.skip_special_tokens ? "on" : "off"}`);
  if (params.include_stop_str_in_output !== undefined)
    bits.push(
      `include stop: ${params.include_stop_str_in_output ? "on" : "off"}`,
    );
  if (params.stop !== undefined)
    bits.push(
      `stop: ${Array.isArray(params.stop) ? params.stop.join("|") : params.stop}`,
    );
  if (params.chat_template_kwargs) {
    const c = params.chat_template_kwargs;
    if (c.enable_thinking !== undefined)
      bits.push(`thinking: ${c.enable_thinking ? "on" : "off"}`);
    if (c.preserve_thinking) bits.push("preserve thinking: on");
  }
  return bits.join(", ") || "No explicit parameters";
}
function renderPresetCatalog(catalog) {
  const grid = $("apiPresetGrid");
  if (!grid || !catalog) return;
  const items = [...(catalog.defaults || []), ...(catalog.custom || [])];
  grid.innerHTML =
    items
      .map((p) => {
        const locked = p.locked;
        return `<div class="api-card"><div class="api-card-head"><h3>${p.endpoint}<br><span class="label">${p.endpoint_alt || "/" + p.name}</span></h3>${locked ? '<span class="label">default</span>' : `<span class="preset-actions"><button class="iconbtn" title="Edit" onclick="editPreset('${p.name}')">✏️</button><button class="iconbtn" title="Delete" onclick="deletePreset('${p.name}')">❌</button></span>`}</div><p>${p.description || ""}</p><p class="label">${presetParamSummary(p.params)}</p></div>`;
      })
      .join("") +
    `<div class="api-card"><h3>/v1/short-* / /short-* and /v1/concise-* / /concise-*</h3><p>Prefix any default or custom preset to cap replies: short = 4096 tokens, concise = 512 tokens. Presets work both under /v1/name and /name for clients that append /v1 automatically.</p></div>`;
}
function openPresetEditor(data) {
  editingPresetName = data && data.name ? data.name : null;
  $("presetEditor").classList.add("open");
  if ($("presetIntro")) $("presetIntro").classList.add("hidden");
  $("presetSaveBtn").textContent = editingPresetName
    ? "💾 Save changes"
    : "💾 Save";
  $("presetName").disabled = !!editingPresetName;
  $("presetName").value = data?.name || "";
  $("presetDescription").value = data?.description || "";
  $("presetSystemPrompt").value = data?.system_prompt || "";
  const p = data?.params || {};
  const c = p.chat_template_kwargs || {};
  $("presetTemperature").value = p.temperature ?? "";
  $("presetTopP").value = p.top_p ?? "";
  $("presetTopK").value = p.top_k ?? "";
  $("presetMinP").value = p.min_p ?? "";
  $("presetThinking").value = String(!!c.enable_thinking);
  $("presetPreserveThinking").value = String(!!c.preserve_thinking);
  $("presetRepetitionPenalty").value = p.repetition_penalty ?? "";
  $("presetPresencePenalty").value = p.presence_penalty ?? "";
  $("presetFrequencyPenalty").value = p.frequency_penalty ?? "";
  $("presetMaxCtx").value = p.truncate_prompt_tokens ?? "";
  $("presetMaxTokens").value = p.max_tokens ?? "";
  $("presetMinTokens").value = p.min_tokens ?? "";
  $("presetLogprobs").value = p.logprobs ?? "";
  $("presetTopLogprobs").value = p.top_logprobs ?? "";
  $("presetLengthPenalty").value = p.length_penalty ?? "";
  $("presetIgnoreEos").value =
    p.ignore_eos === undefined ? "" : String(!!p.ignore_eos);
  $("presetSkipSpecial").value =
    p.skip_special_tokens === undefined ? "" : String(!!p.skip_special_tokens);
  $("presetIncludeStop").value =
    p.include_stop_str_in_output === undefined
      ? ""
      : String(!!p.include_stop_str_in_output);
  $("presetStop").value = Array.isArray(p.stop)
    ? p.stop.join("\n")
    : (p.stop ?? "");
  $("presetEditor").scrollIntoView({ behavior: "smooth", block: "center" });
}
function closePresetEditor() {
  editingPresetName = null;
  $("presetEditor").classList.remove("open");
  if ($("presetIntro")) $("presetIntro").classList.remove("hidden");
}
function collectPresetForm() {
  function val(id) {
    return $(id).value.trim();
  }
  function num(id) {
    const v = val(id);
    return v === "" ? undefined : Number(v);
  }
  const preset = {
    description: val("presetDescription"),
    system_prompt: $("presetSystemPrompt").value,
    enable_thinking: $("presetThinking").value === "true",
    preserve_thinking: $("presetPreserveThinking").value === "true",
  };
  [
    ["temperature", "presetTemperature"],
    ["top_p", "presetTopP"],
    ["top_k", "presetTopK"],
    ["min_p", "presetMinP"],
    ["repetition_penalty", "presetRepetitionPenalty"],
    ["presence_penalty", "presetPresencePenalty"],
    ["frequency_penalty", "presetFrequencyPenalty"],
    ["truncate_prompt_tokens", "presetMaxCtx"],
    ["max_tokens", "presetMaxTokens"],
    ["min_tokens", "presetMinTokens"],
    ["logprobs", "presetLogprobs"],
    ["top_logprobs", "presetTopLogprobs"],
    ["length_penalty", "presetLengthPenalty"],
  ].forEach(([k, id]) => {
    const n = num(id);
    if (Number.isFinite(n)) preset[k] = n;
  });
  [
    ["ignore_eos", "presetIgnoreEos"],
    ["skip_special_tokens", "presetSkipSpecial"],
    ["include_stop_str_in_output", "presetIncludeStop"],
  ].forEach(([k, id]) => {
    const v = val(id);
    if (v !== "") preset[k] = v === "true";
  });
  const stop = val("presetStop");
  if (stop) preset.stop = stop;
  return preset;
}
async function savePresetFromForm() {
  const name = editingPresetName || $("presetName").value.trim();
  try {
    const r = await fetch("/admin/presets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "save",
        name,
        preset: collectPresetForm(),
      }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "save failed");
    renderPresetCatalog(j.presets);
    closePresetEditor();
    setMsg("Saved preset " + name);
    await refreshStatus();
  } catch (e) {
    alert("Preset save failed: " + e);
  }
}
function editPreset(name) {
  const p = (lastStatus?.presets?.custom || []).find((x) => x.name === name);
  if (p) openPresetEditor(p);
}
async function deletePreset(name) {
  if (!confirm("Delete custom preset " + name + "?")) return;
  try {
    const r = await fetch("/admin/presets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "delete", name }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "delete failed");
    renderPresetCatalog(j.presets);
    setMsg("Deleted preset " + name);
    await refreshStatus();
  } catch (e) {
    alert("Preset delete failed: " + e);
  }
}

// Base chart rendering
function tempColorForValue(value) {
  const temp = Number(value || 0);
  if (temp < 35) return "#60a5fa";
  if (temp < 50) return "#2fc46b";
  if (temp < 60) return "#ffde59";
  if (temp < 70) return "#ff8a2a";
  if (temp < 80) return "#ff5b6c";
  return "#dc143c";
}
function formatChartValue(value, digits = 1) {
  const numeric = Number(value || 0);
  return Number.isFinite(numeric)
    ? trimFormattedNumber(numeric.toFixed(digits))
    : "0";
}
function cumulativePeak(values = []) {
  let peak = 0;
  return values.map((value) => {
    peak = Math.max(peak, Number(value || 0));
    return peak;
  });
}
function draw(id, data, key, label, color, options = {}) {
  const c = $(id);
  if (!c) return;
  const ctx = c.getContext("2d"),
    dpr = devicePixelRatio || 1,
    w = (c.width = c.clientWidth * dpr),
    h = (c.height = c.clientHeight * dpr);
  ctx.clearRect(0, 0, w, h);
  const values = data.map((item) => Number(item?.[key] || 0));
  const peaks = options.showPeakLine ? cumulativePeak(values) : [];
  const peakValue = peaks.length ? peaks[peaks.length - 1] : Math.max(0, ...values);
  const currentValue = values.length ? values[values.length - 1] : 0;
  const maxValue = Math.max(1, ...values, ...peaks) * 1.1;
  const chartTop = 26 * dpr;
  const chartBottomPad = 8 * dpr;
  const chartHeight = Math.max(1, h - chartTop - chartBottomPad);
  ctx.fillStyle = "#9dafc3";
  ctx.font = `${11 * dpr}px system-ui`;
  ctx.fillText(label, 8 * dpr, 14 * dpr);
  const valueColor = options.valueColor
    ? options.valueColor(currentValue, peakValue)
    : color || "#e8eef7";
  const valueText = options.valueFormatter
    ? options.valueFormatter(currentValue, peakValue)
    : options.showPeakValue
      ? `${formatChartValue(currentValue)} (↑ ${formatChartValue(peakValue)})`
      : formatChartValue(currentValue);
  ctx.textAlign = "right";
  if (options.valueFormatterParts) {
    let x = w - 8 * dpr;
    [...options.valueFormatterParts(currentValue, peakValue)].reverse().forEach((part) => {
      const text = String(part?.text || "");
      if (!text) return;
      ctx.fillStyle = part.color || valueColor;
      ctx.fillText(text, x, 14 * dpr);
      x -= ctx.measureText(text).width;
    });
  } else {
    ctx.fillStyle = valueColor;
    ctx.fillText(valueText, w - 8 * dpr, 14 * dpr);
  }
  ctx.textAlign = "left";
  if (!values.length) return;
  const drawSeries = (seriesValues, strokeStyle, width, alpha = 1, dashed = false) => {
    ctx.save();
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = width * dpr;
    ctx.globalAlpha = alpha;
    if (dashed) ctx.setLineDash([5 * dpr, 4 * dpr]);
    ctx.beginPath();
    seriesValues.forEach((value, index) => {
      const x = (index / (seriesValues.length - 1 || 1)) * (w - 2 * dpr);
      const y = h - (Number(value || 0) / maxValue) * chartHeight - chartBottomPad;
      index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.stroke();
    ctx.restore();
  };
  if (peaks.length)
    drawSeries(peaks, options.peakColor || "#b7c0cc", 1.4, 0.9, options.peakDashed !== false);
  drawSeries(values, color, 2.2, 1);
}
function drawGpuSeries(id, series, index, key, label, color, options = {}) {
  const data = series.map((point) => {
    const gpu = (point.gpus || []).find((item) => String(item.index) === String(index));
    return { [key]: gpu ? Number(gpu[key] || 0) : 0 };
  });
  draw(id, data, key, label, color, options);
}
function renderMetrics(j) {
  const s = j.series || [];
  draw("cGpu", s, "gpu_util", "GPU util %", "#72c7ff");
  draw("cMem", s, "mem_pct", "VRAM %", "#2fc46b");
  draw("cLatency", s, "latency_s", "Latency s", "#ffcb6b");
  draw("cTps", s, "tps", "TPS est", "#ff5b6c", {
    showPeakValue: true,
    showPeakLine: true,
    peakColor: "#b7c0cc",
    valueFormatter: (current, peak) =>
      `${formatChartValue(current, 2)} (↑ ${formatChartValue(peak, 2)})`,
  });
  draw("cRam", s, "ram_pct", "System RAM %", "#2fc46b");
  draw("cCpu", s, "cpu_pct", "CPU total %", "#72c7ff");
  draw("cSystemUtil", s, "system_util_pct", "System utilization %", "#a78bfa");
  draw("cNetDown", s, "net_rx_kbps", "Download kbps", "#2fc46b");
  draw("cNetUp", s, "net_tx_kbps", "Upload kbps", "#72c7ff");
  if ($("ramInfo"))
    $("ramInfo").textContent =
      j.system && j.system.memory
        ? `Used ${mibToGiB(j.system.memory.used_mib)} / ${mibToGiB(j.system.memory.total_mib)} GB (${j.system.memory.used_pct}%)`
        : "";
  const cores = (j.system && j.system.cpu && j.system.cpu.cores) || [];
  if ($("cpuCores"))
    $("cpuCores").innerHTML = cores
      .map(
        (c) =>
          `<div class="stat"><div class="label">Core ${c.core}</div><div class="value">${c.usage_pct}%</div><div class="meter"><span style="width:${c.usage_pct}%"></span></div></div>`,
      )
      .join("");
  const disks = (j.system && j.system.disks) || [];
  function storageCard(d) {
    if (d.error)
      return `<div class="storage-card"><div class="storage-title">Error</div><div class="value">${d.error}</div></div>`;
    const title = `${d.path || d.source || d.name || "disk"}${d.label ? " — " + d.label : ""}`;
    const meta = `${d.model || ""} ${d.transport ? "· " + d.transport : ""} · ${d.type || "-"} / ${d.partition_type || "-"} · ${d.fs || "-"} · ${d.mount || "not mounted"}${d.usage_basis ? " · " + d.usage_basis : ""}`;
    const sizeText = (v) =>
      v === null || v === undefined ? "Unknown" : `${v} GB`;
    const free = sizeText(d.free_gib);
    const used = sizeText(d.used_gib);
    const total = sizeText(d.total_gib);
    const pct =
      d.used_pct === null || d.used_pct === undefined
        ? 0
        : Number(d.used_pct || 0);
    const pctLabel =
      d.used_pct === null || d.used_pct === undefined
        ? "usage unknown"
        : `${pct}% used`;
    const cls = d.user_facing ? "storage-card user-facing" : "storage-card";
    return `<div class="${cls}"><div class="storage-title">${title}</div><div class="storage-meta">${meta}</div><div class="storage-sizes"><div class="stat"><div class="label">Free</div><div class="value">${free}</div></div><div class="stat"><div class="label">Used</div><div class="value">${used}</div></div><div class="stat"><div class="label">Total</div><div class="value">${total}</div></div></div><div class="diskbar"><span style="width:${pct}%"></span></div><div class="label">${pctLabel}</div></div>`;
  }
  if ($("diskInfo")) {
    const physical = disks.filter(
      (d) => d.kind === "disk" || d.type === "disk",
    );
    const volumes = disks.filter(
      (d) => !(d.kind === "disk" || d.type === "disk"),
    );
    $("diskInfo").innerHTML =
      `<div class="storage-section"><div class="panel"><h2>Disks</h2><div class="storage-list">${physical.map(storageCard).join("") || '<div class="value">No physical disks found</div>'}</div></div><div class="panel"><h2>Volumes</h2><div class="storage-list">${volumes.map(storageCard).join("") || '<div class="value">No volumes found</div>'}</div></div></div>`;
  }
  const net = (j.system && j.system.network) || {};
  if ($("netInfo"))
    $("netInfo").innerHTML =
      `<div class="stat"><div class="label">Local IP</div><div class="value">${net.local_ip || "unknown"}</div></div><div class="stat"><div class="label">Internet IP</div><div class="value">${net.public_ip || "unknown"}</div></div><div class="stat"><div class="label">Download</div><div class="value">${net.rx_kbps || 0} kbps</div></div><div class="stat"><div class="label">Upload</div><div class="value">${net.tx_kbps || 0} kbps</div></div>`;
  const info = (j.system && j.system.info) || {};
  const cpuPackages = Array.isArray(info.cpu_packages) ? info.cpu_packages : [];
  const cpuPackageText = cpuPackages.length
    ? cpuPackages
        .map((pkg) => {
          const details = [];
          if (Number(pkg.cores || 0) > 0) details.push(`${pkg.cores} cores`);
          if (Number(pkg.threads || 0) > 0)
            details.push(`${pkg.threads} threads`);
          return `CPU${pkg.package}: ${pkg.model || "unknown"}${details.length ? ` (${details.join(", ")})` : ""}`;
        })
        .join("<br>")
    : `CPU: ${info.cpu_model || "unknown"}`;
  const memorySummary =
    info.memory_total_mib !== undefined
      ? `Installed RAM: ${mibToGiB(info.memory_total_mib)} GB`
      : "Installed RAM: unknown";
  const vramSummary =
    info.vram_total_mib !== undefined
      ? `Available VRAM: ${mibToGiB(info.vram_free_mib || 0)} / ${mibToGiB(info.vram_total_mib)} GB`
      : "Available VRAM: unknown";
  if ($("systemInfo"))
    $("systemInfo").innerHTML =
      `OS: ${info.os || "unknown"}<br>Kernel: ${info.kernel || "unknown"}<br>Host: ${info.hostname || "unknown"}<br>User: ${info.username || "unknown"}<br>Machine: ${info.machine || "unknown"}<br>${cpuPackageText}<br>GPUs: ${info.gpus || "unknown"}<br>${memorySummary}<br>${vramSummary}<br>Board/Product: ${info.board || "-"} / ${info.product || "-"}<br>BIOS: ${info.bios || "-"}`;
  const holder = $("gpuMetricCharts");
  if (holder && j.gpus) {
    const cats = [
      { key: "util", suffix: "Util", label: "util %", color: "#72c7ff" },
      { key: "mem_pct", suffix: "Mem", label: "VRAM %", color: "#2fc46b" },
      { key: "temp", suffix: "Temp", label: "core temp °C", color: "#ffde59" },
      { key: "power", suffix: "Power", label: "power W", color: "#ff5b6c" },
    ];
    Object.assign(
      cats.find((cat) => cat.key === "temp") || {},
      {
        showPeakLine: true,
        peakColor: "#b7c0cc",
        showPeakValue: true,
        valueColor: (current) => tempColorForValue(current),
        valueFormatterParts: (current, peak) => [
          { text: `${formatChartValue(current, 1)}°C`, color: tempColorForValue(current) },
          { text: " " },
          { text: `(↑ ${formatChartValue(peak, 1)}°C)`, color: tempColorForValue(peak) },
        ],
      },
    );
    Object.assign(
      cats.find((cat) => cat.key === "power") || {},
      {
        showPeakLine: true,
        peakColor: "#b7c0cc",
        showPeakValue: true,
        valueFormatter: (current, peak) =>
          `${formatChartValue(current, 1)} (↑ ${formatChartValue(peak, 1)})`,
      },
    );
    holder.innerHTML = cats
      .map((cat) =>
        j.gpus
          .map(
            (g) =>
              `<div class="chart"><canvas id="cGpu${g.index}${cat.suffix}"></canvas></div>`,
          )
          .join(""),
      )
      .join("");
    cats.forEach((cat) =>
      j.gpus.forEach((g) => {
        const color = cat.color;
        const label = `GPU${g.index} ${cat.label}`;
        drawGpuSeries(
          `cGpu${g.index}${cat.suffix}`,
          s,
          g.index,
          cat.key,
          label,
          color,
          cat,
        );
      }),
    );
  }
}

// Shared runtime/UI state
let selectedInstance = "GPU0";
let logEs = null;
let selectedUserName = "";
let selectedOverviewInstanceId = "";
let selectedLogInstanceId = "";
let selectedPresetModelId = "";
let selectedPresetModelHydrated = false;
let pendingLogJump = null;
let adminAuthRefreshBlocked = false;
const SUMMARY_CACHE_KEY = "club3090-preset-summary-v520";
const CHAT_STATE_KEY = "club3090-chat-state-v528";
const LEGACY_CHAT_STATE_KEY = "club3090-chat-state-v520";
const LEGACY_CHAT_STATE_KEY_V516 = "club3090-chat-state-v516";
const CLUB3090_SCRIPT_VERSION = "__SCRIPT_VERSION__";
const DEBUG_LOGS = !/v\d+\.\d+\.0(?:\D|$)/.test(String(CLUB3090_SCRIPT_VERSION || ""));
const CHAT_UNTITLED_TITLE = "Untitled conversation";
const CHAT_MIN_COMPACTION_THRESHOLD = 50;
const CHAT_MAX_COMPACTION_THRESHOLD = 95;
const CHAT_THINKING_RENDER_INTERVAL_MS = 250;
const CHAT_CONVERSATION_FOLDER_RE = /^[A-Za-z0-9 _-]*$/;
const CHAT_TRANSCRIPT_INITIAL_TURNS = 12;
const CHAT_TRANSCRIPT_EXPAND_STEP = 12;
let presetSummaryCache = { persistent: {}, transient: {}, restartTargets: [], lastSeenUptime: 0 };
let chatStateServerReady = false;
let chatStateSaveTimer = null;
let lastQueuedChatStateJson = "";
let chatStateSaveController = null;
let chatStateHydrated = false;
let chatStateHydratingPromise = null;
let chatTranscriptVisibleTurns = CHAT_TRANSCRIPT_INITIAL_TURNS;
let chatTranscriptLastSignature = "";
let chatTranscriptLastHtml = "";
const chatMarkdownRenderCache = new Map();
const chatConversationDetailLoadPromises = new Map();
let chatConversationLoadNonce = 0;
function defaultChatParams() {
  return {
    temperature: "",
    top_p: "",
    top_k: "",
    min_p: "",
    repetition_penalty: "",
    presence_penalty: "",
    frequency_penalty: "",
    max_tokens: "",
    seed: "",
    enable_thinking: false,
    preserve_thinking: false,
  };
}
function clampChatCompactionThreshold(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return CHAT_MAX_COMPACTION_THRESHOLD;
  return Math.max(
    CHAT_MIN_COMPACTION_THRESHOLD,
    Math.min(CHAT_MAX_COMPACTION_THRESHOLD, Math.round(numeric)),
  );
}
function normalizeConversationFolder(value) {
  return String(value || "")
    .replace(/[^A-Za-z0-9 _-]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
function isValidConversationFolder(value) {
  return CHAT_CONVERSATION_FOLDER_RE.test(String(value || ""));
}
function cloneChatParams(params = {}) {
  return {
    ...defaultChatParams(),
    ...(params && typeof params === "object" ? params : {}),
    enable_thinking: !!params?.enable_thinking,
    preserve_thinking: !!params?.preserve_thinking,
  };
}
function cloneChatAttachment(attachment = {}) {
  const kind = attachment?.kind === "image" ? "image" : "text";
  const row = {
    id: String(attachment?.id || ""),
    kind,
    name: String(attachment?.name || (kind === "image" ? "image" : "attachment")),
    mime: String(attachment?.mime || ""),
    source: String(attachment?.source || ""),
  };
  if (kind === "image") {
    row.url = String(attachment?.url || "");
    if (attachment?.size_bytes !== undefined) row.size_bytes = attachment.size_bytes;
  } else {
    row.text = String(attachment?.text || "");
  }
  return row;
}
function cloneChatMessage(message = {}) {
  return {
    ...message,
    role: String(message?.role || "user"),
    text: String(message?.text || ""),
    attachments: Array.isArray(message?.attachments)
      ? message.attachments.map(cloneChatAttachment)
      : [],
    reasoningText: String(message?.reasoningText || ""),
    reasoning_content: String(message?.reasoning_content || ""),
    reasoning: String(message?.reasoning || ""),
    modelLabel: String(message?.modelLabel || ""),
    inputTokens:
      message?.inputTokens !== undefined ? Number(message.inputTokens || 0) : undefined,
    outputTokens:
      message?.outputTokens !== undefined ? Number(message.outputTokens || 0) : undefined,
    ttftSeconds:
      message?.ttftSeconds !== undefined ? Number(message.ttftSeconds || 0) : undefined,
    tokensPerSecond:
      message?.tokensPerSecond !== undefined
        ? Number(message.tokensPerSecond || 0)
        : undefined,
    maxTokensPerSecond:
      message?.maxTokensPerSecond !== undefined
        ? Number(message.maxTokensPerSecond || 0)
        : undefined,
  };
}
function cloneChatMessages(messages = []) {
  return Array.isArray(messages) ? messages.map(cloneChatMessage) : [];
}
function currentChatStatePayload() {
  const activeId = String(chatState.activeConversationId || "");
  return {
    revision: Math.max(0, Number(chatState.revision || 0) || 0),
    activeConversationId: chatState.activeConversationId,
    conversations: Array.isArray(chatState.conversations)
      ? chatState.conversations.map((conversation) => ({
          ...(String(conversation?.id || "") === activeId &&
          conversation?.messagesLoaded !== false
            ? {
                ...conversation,
                summary: String(conversation?.summary || ""),
                presetId: String(conversation?.presetId || ""),
                apiPresetName: String(conversation?.apiPresetName || ""),
                params: cloneChatParams(conversation?.params),
                systemPrompt: String(conversation?.systemPrompt || ""),
                autoCompactEnabled: conversation?.autoCompactEnabled !== false,
                autoCompactThresholdPct: clampChatCompactionThreshold(
                  conversation?.autoCompactThresholdPct,
                ),
                messages: cloneChatMessages(conversation?.messages),
                attachments: Array.isArray(conversation?.attachments)
                  ? conversation.attachments.map(cloneChatAttachment)
                  : [],
                draftText: String(conversation?.draftText || ""),
                compactedFromId: String(conversation?.compactedFromId || ""),
                compactionSequence: Math.max(
                  1,
                  Number(conversation?.compactionSequence || 1) || 1,
                ),
                lastInputTokens:
                  conversation?.lastInputTokens !== undefined
                    ? conversation.lastInputTokens
                    : undefined,
                lastOutputTokens:
                  conversation?.lastOutputTokens !== undefined
                    ? conversation.lastOutputTokens
                    : undefined,
                lastTotalTokens:
                  conversation?.lastTotalTokens !== undefined
                    ? conversation.lastTotalTokens
                    : undefined,
                lastCtxSizeTokens:
                  conversation?.lastCtxSizeTokens !== undefined
                    ? conversation.lastCtxSizeTokens
                    : undefined,
                lastKvCacheUsagePct:
                  conversation?.lastKvCacheUsagePct !== undefined
                    ? conversation.lastKvCacheUsagePct
                    : undefined,
                lastRuntimeRequestAt:
                  conversation?.lastRuntimeRequestAt !== undefined
                    ? conversation.lastRuntimeRequestAt
                    : undefined,
                lastStatus:
                  conversation?.lastStatus !== undefined
                    ? conversation.lastStatus
                    : undefined,
                lastLatencySeconds:
                  conversation?.lastLatencySeconds !== undefined
                    ? conversation.lastLatencySeconds
                    : undefined,
                lastTtftSeconds:
                  conversation?.lastTtftSeconds !== undefined
                    ? conversation.lastTtftSeconds
                    : undefined,
                lastTokensPerSecond:
                  conversation?.lastTokensPerSecond !== undefined
                    ? conversation.lastTokensPerSecond
                    : undefined,
                lastTokensPerSecondPeak:
                  conversation?.lastTokensPerSecondPeak !== undefined
                    ? conversation.lastTokensPerSecondPeak
                    : undefined,
                lastToolCalls:
                  conversation?.lastToolCalls !== undefined
                    ? conversation.lastToolCalls
                    : undefined,
                lastRequestPath:
                  conversation?.lastRequestPath !== undefined
                    ? String(conversation.lastRequestPath || "")
                    : undefined,
                transcriptHeightPx:
                  conversation?.transcriptHeightPx !== undefined
                    ? Number(conversation.transcriptHeightPx || 0)
                    : undefined,
                messagesLoaded: true,
              }
            : {
                id: String(conversation?.id || chatConversationId()),
                title:
                  String(conversation?.title || "").trim() || CHAT_UNTITLED_TITLE,
                folder: normalizeConversationFolder(conversation?.folder || ""),
                updatedAt: Number(conversation?.updatedAt || Date.now()),
                lastUsedAt: Number(conversation?.lastUsedAt || Date.now()),
                messagesLoaded: false,
              }),
          folder: normalizeConversationFolder(conversation?.folder || ""),
          title:
            String(conversation?.title || "").trim() || CHAT_UNTITLED_TITLE,
        }))
      : [],
    promptTemplates: Array.isArray(chatState.promptTemplates)
      ? chatState.promptTemplates.map((template) => ({
          id: String(template?.id || chatConversationId()),
          name: String(template?.name || "").trim(),
          text: String(template?.text || ""),
        }))
      : [],
  };
}
function cancelPendingServerChatStateSave() {
  if (chatStateSaveTimer) {
    clearTimeout(chatStateSaveTimer);
    chatStateSaveTimer = null;
  }
  if (chatStateSaveController) {
    try {
      chatStateSaveController.abort();
    } catch (e) {}
    chatStateSaveController = null;
  }
}
function queueServerChatStateSave(payload = currentChatStatePayload()) {
  if (!chatStateServerReady) return;
  const nextJson = JSON.stringify(payload || {});
  if (nextJson === lastQueuedChatStateJson) return;
  lastQueuedChatStateJson = nextJson;
  if (chatStateSaveTimer) clearTimeout(chatStateSaveTimer);
  chatStateSaveTimer = setTimeout(async () => {
    const controller = new AbortController();
    if (chatStateSaveController) {
      try {
        chatStateSaveController.abort();
      } catch (e) {}
    }
    chatStateSaveController = controller;
    try {
      await fetch("/admin/chat-state", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: nextJson,
        signal: controller.signal,
      });
    } catch (e) {
      if (e?.name !== "AbortError") return;
    } finally {
      if (chatStateSaveController === controller) chatStateSaveController = null;
    }
  }, 120);
}
function logDebugEvent(event, fields = {}) {
  if (!DEBUG_LOGS) return;
  const payload = {
    event: String(event || "").trim() || "event",
    source: "web-ui",
    fields: fields && typeof fields === "object" ? fields : {},
  };
  fetch("/admin/debug-log", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    keepalive: true,
  }).catch(() => {});
}
function chatConversationId() {
  return `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
function isUntitledConversationTitle(title) {
  return !String(title || "").trim() || String(title || "").trim() === CHAT_UNTITLED_TITLE;
}
function createChatConversation(seed = {}, inheritFrom = null) {
  const base = inheritFrom && typeof inheritFrom === "object" ? inheritFrom : {};
  const createdAt = Number(seed.createdAt || Date.now());
  return {
    id: String(seed.id || chatConversationId()),
    title: String(seed.title || CHAT_UNTITLED_TITLE).trim() || CHAT_UNTITLED_TITLE,
    folder:
      seed.folder !== undefined
        ? normalizeConversationFolder(seed.folder)
        : normalizeConversationFolder(base.folder || ""),
    summary: String(seed.summary || ""),
    autoNamed:
      seed.autoNamed !== undefined
        ? !!seed.autoNamed
        : !isUntitledConversationTitle(seed.title || ""),
    createdAt,
    updatedAt: Number(seed.updatedAt || createdAt),
    lastUsedAt: Number(seed.lastUsedAt || seed.updatedAt || createdAt),
    statsCollapsed:
      seed.statsCollapsed !== undefined
        ? !!seed.statsCollapsed
        : !!base.statsCollapsed,
    presetId:
      seed.presetId !== undefined
        ? String(seed.presetId || "")
        : String(base.presetId || ""),
    apiPresetName:
      seed.apiPresetName !== undefined
        ? String(seed.apiPresetName || "")
        : String(base.apiPresetName || ""),
    params:
      seed.params !== undefined
        ? cloneChatParams(seed.params)
        : cloneChatParams(base.params),
    systemPrompt:
      seed.systemPrompt !== undefined
        ? String(seed.systemPrompt || "")
        : String(base.systemPrompt || ""),
    autoCompactEnabled:
      seed.autoCompactEnabled !== undefined
        ? !!seed.autoCompactEnabled
        : base.autoCompactEnabled !== false,
    autoCompactThresholdPct: clampChatCompactionThreshold(
      seed.autoCompactThresholdPct !== undefined
        ? seed.autoCompactThresholdPct
        : base.autoCompactThresholdPct,
    ),
    messages: cloneChatMessages(seed.messages),
    attachments: Array.isArray(seed.attachments)
      ? seed.attachments.map(cloneChatAttachment)
      : [],
    draftText: String(seed.draftText || ""),
    compactedFromId: String(seed.compactedFromId || ""),
    compactionSequence: Math.max(
      1,
      Number(
        seed.compactionSequence !== undefined
          ? seed.compactionSequence
          : base.compactionSequence || 1,
      ) || 1,
    ),
    lastInputTokens:
      seed.lastInputTokens !== undefined ? Number(seed.lastInputTokens || 0) : undefined,
    lastOutputTokens:
      seed.lastOutputTokens !== undefined ? Number(seed.lastOutputTokens || 0) : undefined,
    lastTotalTokens:
      seed.lastTotalTokens !== undefined ? Number(seed.lastTotalTokens || 0) : undefined,
    lastCtxSizeTokens:
      seed.lastCtxSizeTokens !== undefined ? Number(seed.lastCtxSizeTokens || 0) : undefined,
    lastKvCacheUsagePct:
      seed.lastKvCacheUsagePct !== undefined ? Number(seed.lastKvCacheUsagePct || 0) : undefined,
    lastRuntimeRequestAt:
      seed.lastRuntimeRequestAt !== undefined ? Number(seed.lastRuntimeRequestAt || 0) : undefined,
    lastStatus:
      seed.lastStatus !== undefined ? Number(seed.lastStatus || 0) : undefined,
    lastLatencySeconds:
      seed.lastLatencySeconds !== undefined
        ? Number(seed.lastLatencySeconds || 0)
        : undefined,
    lastTtftSeconds:
      seed.lastTtftSeconds !== undefined ? Number(seed.lastTtftSeconds || 0) : undefined,
    lastTokensPerSecond:
      seed.lastTokensPerSecond !== undefined
        ? Number(seed.lastTokensPerSecond || 0)
        : undefined,
    lastTokensPerSecondPeak:
      seed.lastTokensPerSecondPeak !== undefined
        ? Number(seed.lastTokensPerSecondPeak || 0)
        : undefined,
    lastToolCalls:
      seed.lastToolCalls !== undefined ? Number(seed.lastToolCalls || 0) : undefined,
    lastRequestPath:
      seed.lastRequestPath !== undefined ? String(seed.lastRequestPath || "") : undefined,
    transcriptHeightPx:
      seed.transcriptHeightPx !== undefined
        ? Number(seed.transcriptHeightPx || 0)
        : undefined,
    messagesLoaded: seed.messagesLoaded === false ? false : true,
  };
}
let chatState = {
  revision: 0,
  activeConversationId: "",
  conversations: [],
  presetId: "",
  apiPresetName: "",
  messages: [],
  attachments: [],
  busy: false,
  params: defaultChatParams(),
  systemPrompt: "",
  autoCompactEnabled: true,
  autoCompactThresholdPct: CHAT_MAX_COMPACTION_THRESHOLD,
  statsCollapsed: false,
  transcriptHeightPx: 0,
  promptTemplates: [],
};
let chatOptionsMenuOpen = false;
let mcpManagerState = { servers: [], editingId: "" };
let chatSettingsDraft = null;
let chatRecognition = null;
let chatTranscriptAutoFollow = true;
let chatRequestController = null;
let chatAutoTitleGenerationId = 0;
let chatThinkingTicker = null;
function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
function svgIcon(name) {
  if (name === "edit")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l10-10-4-4L4 16v4zM14 6l4 4" fill="none"/></svg>';
  if (name === "key")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 7a4 4 0 1 0 0 8a4 4 0 0 0 0-8Zm0 0h6m-2 0v3m-3 0h6" fill="none"/></svg>';
  if (name === "reset")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v6h-6" fill="none"/></svg>';
  if (name === "delete")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M9 7V5h6v2m-7 3v7m4-7v7m4-7v7M7 7l1 12h8l1-12" fill="none"/></svg>';
  if (name === "copy")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 9h10v10H9zM5 15H4V5h10v1" fill="none"/></svg>';
  if (name === "upload")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4m0 0l-4 4m4-4l4 4M5 20h14" fill="none"/></svg>';
  if (name === "send")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12 19 5l-3.8 5.4L19 12l-3.8 1.6L19 19 4 12Z" fill="currentColor" stroke="none"/></svg>';
  if (name === "stop")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7h10v10H7z" fill="currentColor" stroke="none"/></svg>';
  if (name === "close")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" fill="none"/></svg>';
  if (name === "plus")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none"/></svg>';
  if (name === "chat")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 18V6h14v9H8l-3 3Zm3-7h8m-8 3h5" fill="none"/></svg>';
  if (name === "share")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 12.5 15.5 7M8 12.5l7.5 4.5" fill="none"/><circle cx="6" cy="12.5" r="3" fill="currentColor" stroke="none"/><circle cx="18" cy="5.5" r="3" fill="currentColor" stroke="none"/><circle cx="18" cy="18.5" r="3" fill="currentColor" stroke="none"/></svg>';
  if (name === "gear")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8.5a3.5 3.5 0 1 0 0 7a3.5 3.5 0 0 0 0-7Zm8 3.5l-2.1.8a6.9 6.9 0 0 1-.6 1.4l.9 2l-2.1 2.1l-2-.9a6.9 6.9 0 0 1-1.4.6L12 20l-1.1-2.1a6.9 6.9 0 0 1-1.4-.6l-2 .9l-2.1-2.1l.9-2a6.9 6.9 0 0 1-.6-1.4L4 12l2.1-1.1a6.9 6.9 0 0 1 .6-1.4l-.9-2l2.1-2.1l2 .9a6.9 6.9 0 0 1 1.4-.6L12 4l1.1 2.1a6.9 6.9 0 0 1 1.4.6l2-.9l2.1 2.1l-.9 2a6.9 6.9 0 0 1 .6 1.4L20 12Z" fill="none"/></svg>';
  if (name === "chevron-up")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 15 6-6 6 6" fill="none"/></svg>';
  if (name === "chevron-down")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" fill="none"/></svg>';
  if (name === "chevron-right")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6" fill="none"/></svg>';
  return "";
}
function renderIconButton({ title, action, icon, className = "" }) {
  const classes = `iconbtn ${className}`.trim();
  return `<button class="${classes}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}" onclick="${action}">${svgIcon(icon)}</button>`;
}
async function copyTextValue(value) {
  const text = String(value || "");
  if (!text) return false;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {}
  }
  const temp = document.createElement("textarea");
  temp.value = text;
  temp.setAttribute("readonly", "readonly");
  temp.style.position = "fixed";
  temp.style.opacity = "0";
  document.body.appendChild(temp);
  temp.focus();
  temp.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch (e) {
    copied = false;
  }
  temp.remove();
  return copied;
}
function ensureApiKeyModal() {
  if ($("apiKeyModal")) return;
  const modal = document.createElement("div");
  modal.id = "apiKeyModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card" role="dialog" aria-modal="true" aria-labelledby="apiKeyModalTitle"><div class="panel-head"><h2 id="apiKeyModalTitle">API Key</h2><button class="iconbtn" id="apiKeyModalTopClose" title="Close" aria-label="Close" onclick="closeApiKeyModal()">${svgIcon("delete")}</button></div><div class="preset-help" id="apiKeyModalHint">Use Copy to place the key on the clipboard.</div><textarea id="apiKeyModalValue" class="modal-keybox" readonly wrap="off"></textarea><div class="preset-form-actions"><button class="btn amber" onclick="copyApiKeyModalValue()">Copy</button><button class="btn blue" onclick="closeApiKeyModal()">Close</button></div><div class="msg" id="apiKeyModalMsg"></div></div>`;
  modal.addEventListener("mousedown", (event) => {
    apiKeyModalOverlayMouseDown = event.target === modal;
  });
  modal.addEventListener("click", (event) => {
    const selectionText = String(window.getSelection?.()?.toString?.() || "").trim();
    if (apiKeyModalOverlayMouseDown && event.target === modal && !selectionText)
      closeApiKeyModal();
    apiKeyModalOverlayMouseDown = false;
  });
  document.body.appendChild(modal);
}
let apiKeyModalOptions = {
  copySuccessText: "Copied API key to clipboard.",
  showTopClose: true,
};
let apiKeyModalOverlayMouseDown = false;
function openApiKeyModal(title, value, hint = "", options = {}) {
  ensureApiKeyModal();
  apiKeyModalOptions = {
    copySuccessText: "Copied API key to clipboard.",
    showTopClose: true,
    ...options,
  };
  $("apiKeyModalTitle").textContent = title || "API Key";
  $("apiKeyModalHint").textContent =
    hint || "Use Copy to place the key on the clipboard.";
  $("apiKeyModalValue").value = value || "";
  $("apiKeyModalMsg").textContent = "";
  if ($("apiKeyModalTopClose"))
    $("apiKeyModalTopClose").classList.toggle(
      "hidden",
      !apiKeyModalOptions.showTopClose,
    );
  $("apiKeyModal").classList.remove("hidden");
}
function closeApiKeyModal() {
  ensureApiKeyModal();
  $("apiKeyModal").classList.add("hidden");
}
async function copyApiKeyModalValue() {
  ensureApiKeyModal();
  const ok = await copyTextValue($("apiKeyModalValue").value || "");
  $("apiKeyModalMsg").textContent = ok
    ? apiKeyModalOptions.copySuccessText || "Copied API key to clipboard."
    : "Copy failed on this browser.";
}
function ensureExternalLinkModal() {
  if ($("externalLinkModal")) return;
  const modal = document.createElement("div");
  modal.id = "externalLinkModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card" role="dialog" aria-modal="true" aria-labelledby="externalLinkTitle"><div class="panel-head"><h2 id="externalLinkTitle">Open Link</h2><button class="iconbtn" title="Close" aria-label="Close" onclick="closeExternalLinkModal()">${svgIcon("close")}</button></div><div class="preset-help">Detected external link. Open it in a new browser tab?</div><textarea id="externalLinkValue" class="modal-keybox" readonly wrap="off"></textarea><div class="preset-form-actions"><button class="btn blue" onclick="closeExternalLinkModal()">Cancel</button><button class="btn green" onclick="confirmExternalLinkVisit()">Visit</button></div></div>`;
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeExternalLinkModal();
  });
  document.body.appendChild(modal);
}
let pendingExternalLinkUrl = "";
function openExternalLinkModal(url) {
  ensureExternalLinkModal();
  pendingExternalLinkUrl = String(url || "");
  $("externalLinkValue").value = pendingExternalLinkUrl;
  $("externalLinkModal").classList.remove("hidden");
}
function closeExternalLinkModal() {
  ensureExternalLinkModal();
  pendingExternalLinkUrl = "";
  $("externalLinkModal").classList.add("hidden");
}
function confirmExternalLinkVisit() {
  const url = pendingExternalLinkUrl;
  closeExternalLinkModal();
  if (url) window.open(url, "_blank", "noopener,noreferrer");
}
function setInstanceMsg(t) {
  if ($("instanceMsg")) $("instanceMsg").textContent = t || "";
}
function getInstanceList() {
  return (lastStatus && lastStatus.instances) || [];
}
function setUsersMsg(t) {
  if ($("usersMsg")) $("usersMsg").textContent = t || "";
}
async function saveUserForm() {
  try {
    const r = await fetch("/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "save", user: collectUserForm() }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "save failed");
    if (j.api_key)
      openApiKeyModal(
        "API key for " + j.user.name,
        j.api_key,
        "This key is now stored so it can be viewed again from the user card.",
      );
    resetUserForm();
    setUsersMsg("Saved user " + j.user.name);
    await refreshStatus();
  } catch (e) {
    alert("User save failed: " + e);
  }
}
async function showUserApiKey(name) {
  try {
    const r = await fetch("/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "show_key", name }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "show failed");
    openApiKeyModal(
      "API key for " + name,
      j.api_key,
      "Use Copy to place the current key on the clipboard.",
    );
  } catch (e) {
    alert("API key lookup failed: " + e);
  }
}
async function resetUserKey(name) {
  if (!confirm("Reset API key for " + name + "?")) return;
  try {
    const r = await fetch("/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "reset_key", name }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "reset failed");
    openApiKeyModal(
      "New API key for " + name,
      j.api_key,
      "The previous key is no longer valid. Use Copy if you need to share the replacement key.",
    );
    setUsersMsg("Reset API key for " + name);
    await refreshStatus();
  } catch (e) {
    alert("API key reset failed: " + e);
  }
}
async function deleteUserByName(name) {
  if (!confirm("Delete user " + name + "?")) return;
  try {
    const r = await fetch("/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "delete", name }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "delete failed");
    if (selectedUserName === name) resetUserForm();
    setUsersMsg("Deleted user " + name);
    await refreshStatus();
  } catch (e) {
    alert("User delete failed: " + e);
  }
}
function setAuditMsg(t) {
  if ($("auditMsg")) $("auditMsg").textContent = t || "";
}
function mirrorAuthToggles(v) {
  if ($("auditAllowAnonymousProxy"))
    $("auditAllowAnonymousProxy").checked = !!v;
}
let selectedGroupName = "";
function setGroupsMsg(t) {
  if ($("groupsMsg")) $("groupsMsg").textContent = t || "";
}
function findPanelByHeading(sectionId, heading) {
  return (
    [...document.querySelectorAll(`#${sectionId} .panel`)].find((panel) => {
      const title = panel.querySelector(".panel-head h2,h2");
      return ((title && title.textContent) || "").trim() === heading;
    }) || null
  );
}
let selectedScope = "GPU0";
function currentScope() {
  return selectedScope || selectedInstance || "GPU0";
}
function scopeIsGlobal() {
  return currentScope() === "GLOBAL";
}

// Layout normalization
function ensureV413Layout() {
  const tabs = document.querySelector(".tabs");
  const auditBtn = tabs && tabs.querySelector('.tab[onclick*=\"audit\"]');
  const logsBtn = tabs && tabs.querySelector('.tab[onclick*=\"logs\"]');
  if (auditBtn) auditBtn.remove();
  if (tabs && logsBtn) tabs.appendChild(logsBtn);
  const system = $("system");
  const presets = $("presets");
  const logs = $("logs");
  const audit = $("audit");
  if (system && audit) {
    const accessPolicy = findPanelByHeading("audit", "Access Policy");
    if (accessPolicy && !accessPolicy.dataset.v413Moved) {
      accessPolicy.dataset.v413Moved = "1";
      system.insertBefore(accessPolicy, system.children[1] || null);
    }
    const overview = findPanelByHeading("audit", "Audit Overview");
    if (overview && logs && !overview.dataset.v413Moved) {
      overview.dataset.v413Moved = "1";
      logs.insertBefore(overview, logs.firstChild || null);
    }
    const globalControls = findPanelByHeading("audit", "Global Controls");
    if (globalControls) globalControls.remove();
    const auditStream = findPanelByHeading("audit", "Audit Stream");
    if (auditStream) auditStream.remove();
    if (audit.childElementCount === 0 || !audit.querySelector(".panel"))
      audit.remove();
  }
  const accessCard = findPanelByHeading("system", "Access Policy");
  if (accessCard) {
    const openUsers = [...accessCard.querySelectorAll("button")].find((btn) =>
      (btn.textContent || "").includes("Open Users Management"),
    );
    if (openUsers) openUsers.remove();
  }
  const singleCard = [...document.querySelectorAll("#presets .panel")].find(
    (panel) => {
      const h = panel.querySelector(".panel-head h2,h2");
      return (
        h &&
        ((h.textContent || "").includes("Per-Instance Docker Presets") ||
          (h.textContent || "").includes("Single GPU Docker Presets"))
      );
    },
  );
  if (singleCard) {
    singleCard.id = "singlePresetCard";
    const title = singleCard.querySelector("h2");
    if (title) title.textContent = "Model Presets";
  }
  const customTitle = [
    ...document.querySelectorAll("#presets .panel .panel-head h2"),
  ].find((h) => (h.textContent || "").trim() === "Custom Preset Templates");
  if (customTitle) customTitle.textContent = "Custom Configuration Endpoints";
  if ($("presetScopePanel")) $("presetScopePanel").remove();
  if ($("dualPresetCard")) $("dualPresetCard").remove();
  if (logs && !$("logSourcePanel")) {
    const panel = document.createElement("div");
    panel.className = "panel";
    panel.id = "logSourcePanel";
    panel.innerHTML = `<div class="panel-head"><h2>Log Sources</h2><div class="preset-actions">${renderIconButton({ title: "Export", action: "exportCurrentLog()", icon: "upload" })}</div></div><div class="subtabs"></div><div class="value smallgap" id="logsSourceSummary">-</div>`;
    logs.appendChild(panel);
  }
  const profiles = findPanelByHeading("system", "Power Profiles");
  if (profiles && !$("profileScopeNote")) {
    const note = document.createElement("div");
    note.className = "preset-help";
    note.id = "profileScopeNote";
    profiles.insertBefore(
      note,
      profiles.querySelector(".actions") || profiles.firstChild,
    );
  }
  const power = findPanelByHeading("system", "Optimizations + Cooling");
  if (power && !$("powerScopeNote")) {
    const note = document.createElement("div");
    note.className = "preset-help";
    note.id = "powerScopeNote";
    power.insertBefore(
      note,
      power.querySelector(".actions") || power.firstChild,
    );
  }
}

// Quota helpers and final users/groups UI
function quotaLimitText(v, suffix = "") {
  return v === null || v === undefined || v === ""
    ? "unlimited"
    : `${v}${suffix}`;
}
function quotaWeightText(v) {
  return v === null || v === undefined || v === ""
    ? "default"
    : trimFormattedNumber(Number(v).toFixed(3));
}
function quotaWindowText(windowData) {
  windowData = windowData || {};
  return `${windowData.requests || 0} msgs · score ${Number(windowData.score || 0).toFixed(1)} · in ${windowData.input_tokens || 0} · out ${windowData.output_tokens || 0} · tools ${windowData.tool_calls || 0} · thinking ${Number(windowData.thinking_seconds || 0).toFixed(1)}s`;
}
function quotaWeightLine(limits) {
  limits = limits || {};
  return `in ${quotaWeightText(limits.input_token_weight)} · out ${quotaWeightText(limits.output_token_weight)} · tools ${quotaWeightText(limits.tool_call_weight)} · thinking ${quotaWeightText(limits.thinking_second_weight)}`;
}
function quotaBudgetLine(limits) {
  limits = limits || {};
  return `5h ${quotaLimitText(limits.score_per_5h)} · week ${quotaLimitText(limits.score_per_week)} · /msg tokens ${quotaLimitText(limits.max_tokens_per_message)} · /msg tools ${quotaLimitText(limits.max_tool_calls_per_message)}`;
}
function parseQuotaNumber(id) {
  const el = $(id);
  if (!el) return null;
  const v = el.value.trim();
  return v === "" ? null : Number(v);
}
function scopeItems() {
  const items = getInstanceList().slice();
  items.sort((a, b) => {
    const ak = a.kind === "dual" ? 1 : 0;
    const bk = b.kind === "dual" ? 1 : 0;
    if (ak !== bk) return ak - bk;
    const ai = (a.gpu_indices || [a.gpu_index])[0] || 0;
    const bi = (b.gpu_indices || [b.gpu_index])[0] || 0;
    return ai - bi || String(a.id).localeCompare(String(b.id));
  });
  return items;
}
function singleScopeItems() {
  return scopeItems().filter((x) => x.kind !== "dual");
}
function pairScopeItems() {
  return pairingEnabled() ? scopeItems().filter((x) => x.kind === "dual") : [];
}
function gpuCount() {
  return Number((lastStatus && lastStatus.gpu_count) || 0);
}
function canonicalPairId(a, b) {
  const nums = [Number(a), Number(b)]
    .filter((x) => Number.isInteger(x) && x >= 0)
    .sort((x, y) => x - y);
  if (nums.length !== 2 || nums[0] === nums[1]) return "";
  return `PAIR${nums[0]}_${nums[1]}`;
}
function exactTwoPairTarget() {
  return gpuCount() === 2
    ? scopeItems().find((x) => x.id === "PAIR0_1") || null
    : null;
}
function currentScopeInstance(strict = false) {
  if (currentScope() === "GLOBAL") {
    if (legacyGlobalDualScope()) return strict ? null : legacyGlobalPair();
    if (pairingEnabled() && gpuCount() === 2)
      return strict ? null : exactTwoPairTarget();
    return null;
  }
  return (
    scopeItems().find((x) => x.id === currentScope()) ||
    singleScopeItems()[0] ||
    pairScopeItems()[0] ||
    null
  );
}
function dockerLogTarget() {
  if (currentLogSource === "audit") return null;
  const legacy = legacyGlobalPair();
  const cur = currentScopeInstance(false) || scopeItems()[0] || null;
  if (scopeIsGlobal() && legacyGlobalDualScope()) return null;
  if (
    legacyGlobalDualScope() &&
    legacy &&
    legacy.running &&
    cur &&
    cur.kind !== "dual" &&
    (cur.assignment_scope === "pair" || cur.overrides_dual_mode || !cur.running)
  )
    return null;
  return cur;
}
function scopeLabel(inst) {
  if (!inst) return legacyGlobalDualScope() ? "Global Dual" : "Global";
  if (inst.id === "GLOBAL") return "Global Dual";
  return inst.kind === "dual"
    ? `Pair ${(inst.gpu_indices || []).join(" + ")}`
    : inst.id;
}
function runtimeTrackingItems() {
  const rows = Object.values(
    (lastStatus && lastStatus.instance_runtime_metrics) || {},
  ).filter((row) => row && row.running);
  rows.sort((a, b) => {
    const ag = Array.isArray(a.gpu_indices) ? a.gpu_indices : [];
    const bg = Array.isArray(b.gpu_indices) ? b.gpu_indices : [];
    return (
      (ag[0] | 999) - (bg[0] | 999) ||
      ag.length - bg.length ||
      String(a.id || a.instance_id || "").localeCompare(
        String(b.id || b.instance_id || ""),
      )
    );
  });
  return rows;
}
function normalizeTrackedRuntimeId(value) {
  const rows = runtimeTrackingItems();
  if (!rows.length) return "";
  const candidate = String(value || "").trim().toUpperCase();
  if (candidate) {
    const exact = rows.find((row) => String(row.id || row.instance_id).toUpperCase() === candidate);
    if (exact) return String(exact.id || exact.instance_id);
  }
  return String(rows[0].id || rows[0].instance_id);
}
function trackedOverviewRuntime() {
  const id = normalizeTrackedRuntimeId(selectedOverviewInstanceId);
  if (!id) return null;
  selectedOverviewInstanceId = id;
  return runtimeTrackingItems().find(
    (row) => String(row.id || row.instance_id) === String(id),
  ) || null;
}
function trackedLogRuntime() {
  const id = normalizeTrackedRuntimeId(selectedLogInstanceId);
  if (!id) return null;
  selectedLogInstanceId = id;
  return runtimeTrackingItems().find(
    (row) => String(row.id || row.instance_id) === String(id),
  ) || null;
}
function setOverviewTrackedInstance(id) {
  selectedOverviewInstanceId = normalizeTrackedRuntimeId(id);
  renderOverviewTracker();
  if (lastStatus) renderOverviewStatus(lastStatus);
}
function setLogTrackedInstance(id) {
  selectedLogInstanceId = normalizeTrackedRuntimeId(id);
  renderLogTracker();
  applyLogVisibility();
  connectLogs(true);
}
function formatCtxTokens(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num) || num <= 0) return "-";
  return formatGroupedInt(num);
}
function formatNumber(value, digits = 2) {
  const num = Number(value);
  return Number.isFinite(num) ? trimFormattedNumber(num.toFixed(digits)) : "-";
}
function formatCompactInt(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "-";
  const abs = Math.abs(num);
  if (abs >= 1000000000)
    return `${trimFormattedNumber((num / 1000000000).toFixed(abs >= 10000000000 ? 0 : 1))}B`;
  if (abs >= 1000000)
    return `${trimFormattedNumber((num / 1000000).toFixed(abs >= 10000000 ? 0 : 1))}M`;
  if (abs >= 1000)
    return `${trimFormattedNumber((num / 1000).toFixed(abs >= 100000 ? 0 : 1))}K`;
  return String(Math.round(num));
}
function formatExactInt(value) {
  const num = Number(value);
  return Number.isFinite(num) ? String(Math.round(num)) : "-";
}
function formatGroupedInt(value) {
  const exact = formatExactInt(value);
  return exact === "-" ? exact : exact.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}
function formatElapsedLaunch(seconds) {
  const total = Math.max(0, Math.round(Number(seconds || 0)));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return mins > 0 ? `${mins} min, ${secs} s to launch` : `${secs} s to launch`;
}
function formatAbsoluteTimestamp(ts) {
  const num = Number(ts || 0);
  if (!Number.isFinite(num) || num <= 0) return "-";
  try {
    const asMillis = num > 1_000_000_000_000 ? num : num * 1000;
    return new Date(asMillis).toLocaleString([], {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch (e) {
    return "-";
  }
}
function conversationScopedRuntime(runtime, conversation) {
  if (!runtime) return null;
  const scoped = { ...runtime };
  if (!conversation) {
    scoped.max_tokens_per_second = Number(runtime?.last_tokens_per_second || runtime?.generation_tps || 0);
    return scoped;
  }
  if (conversation.lastStatus !== undefined) scoped.last_status = conversation.lastStatus;
  if (conversation.lastLatencySeconds !== undefined)
    scoped.last_latency_s = conversation.lastLatencySeconds;
  if (conversation.lastTtftSeconds !== undefined)
    scoped.last_ttft_s = conversation.lastTtftSeconds;
  if (conversation.lastTokensPerSecond !== undefined)
    scoped.last_tokens_per_second = conversation.lastTokensPerSecond;
  if (conversation.lastInputTokens !== undefined)
    scoped.last_input_tokens = conversation.lastInputTokens;
  if (conversation.lastOutputTokens !== undefined)
    scoped.last_output_tokens = conversation.lastOutputTokens;
  if (conversation.lastTotalTokens !== undefined)
    scoped.last_total_tokens = conversation.lastTotalTokens;
  if (conversation.lastToolCalls !== undefined)
    scoped.last_tool_calls = conversation.lastToolCalls;
  if (conversation.lastRequestPath !== undefined)
    scoped.last_path = conversation.lastRequestPath;
  if (conversation.lastRuntimeRequestAt !== undefined)
    scoped.last_request_at = conversation.lastRuntimeRequestAt;
  scoped.max_tokens_per_second = Math.max(
    Number(conversation.lastTokensPerSecondPeak || 0),
    Number(scoped.last_tokens_per_second || 0),
    Number(runtime?.generation_tps || 0),
  );
  return scoped;
}
function runtimeStatsRows(j) {
  return Array.isArray(j?.running_runtimes)
    ? j.running_runtimes.filter(Boolean)
    : [];
}
function formatRuntimeModeValue(j, runtime) {
  if (runtime) return `${runtime.mode || "-"} / ${runtime.port || "-"}`;
  const modes = Array.isArray(j?.active_modes) ? j.active_modes.filter(Boolean) : [];
  const port = j?.active_port || "-";
  return modes.length > 1
    ? `${modes.join(", ")} / multiple`
    : `${modes[0] || j?.active_mode || "-"} / ${port}`;
}
function formatRuntimeContainerValue(j, runtime) {
  if (runtime) return runtime.container || "none";
  const containers = Array.isArray(j?.containers) ? j.containers.filter(Boolean) : [];
  return containers.length ? containers.join(", ") : "none";
}
function formatUsersValue(j) {
  const userCount = Array.isArray(j?.users) ? j.users.length : 0;
  const groupNames = Array.isArray(j?.groups)
    ? j.groups.map((group) => String(group?.name || "").trim()).filter(Boolean)
    : [];
  return `<div>${userCount} registered user${userCount === 1 ? "" : "s"}</div><div class="value-subline">groups: ${groupNames.length ? escapeHtml(groupNames.join(", ")) : "none configured"}</div>`;
}
function formatLastStatusCard(runtime, metrics) {
  const target = runtime || {};
  const latency =
    target.last_latency_s !== undefined && target.last_latency_s !== null
      ? target.last_latency_s
      : metrics.last_latency_s;
  const ttft =
    target.last_ttft_s !== undefined && target.last_ttft_s !== null
      ? target.last_ttft_s
      : metrics.last_ttft_s;
  const promptTps =
    target.prompt_tps !== undefined && target.prompt_tps !== null
      ? target.prompt_tps
      : metrics.prompt_tps;
  const generationTps = [
    target.last_tokens_per_second,
    target.generation_tps,
    metrics.last_tokens_per_second,
    metrics.generation_tps,
  ].find((value) => Number(value) > 0);
  const perfHistory = updateRuntimePerfHistory({
    ...target,
    prompt_tps: promptTps,
    generation_tps: generationTps,
  });
  const tps = generationTps;
  const peakTps = perfHistory.generationPeak || generationTps;
  const valueOrDash = (value, digits = 2) =>
    value !== null && value !== undefined && Number.isFinite(Number(value))
      ? formatNumber(value, digits)
      : "-";
  const head = [
    `latency=${valueOrDash(latency, 3)}s`,
    `ttft=${valueOrDash(ttft, 3)}s`,
    `tk/s=${valueOrDash(tps, 2)} / ↑${valueOrDash(peakTps || tps, 2)}`,
  ];
  const detail = [];
  if (
    target.gpu_kv_cache_usage_pct !== null &&
    target.gpu_kv_cache_usage_pct !== undefined
  ) {
    const ctxText = formatCtxTokens(target.ctx_size_tokens);
    detail.push(
      ctxText !== "-"
        ? `KV ${formatNumber(target.gpu_kv_cache_usage_pct, 1)}% | ${ctxText} ctx`
        : `KV ${formatNumber(target.gpu_kv_cache_usage_pct, 1)}%`,
    );
  } else if (target.ctx_size_tokens) {
    detail.push(`${formatCtxTokens(target.ctx_size_tokens)} ctx`);
  } else {
    detail.push("KV - | - ctx");
  }
  if (
    target.prefix_cache_hit_rate_pct !== null &&
    target.prefix_cache_hit_rate_pct !== undefined
  )
    detail.push(`prefix hit ${formatNumber(target.prefix_cache_hit_rate_pct, 1)}%`);
  else detail.push("prefix hit 0%");
  if (
    target.cpu_kv_cache_usage_pct !== null &&
    target.cpu_kv_cache_usage_pct !== undefined
  )
    detail.push(`CPU KV ${formatNumber(target.cpu_kv_cache_usage_pct, 1)}%`);
  const spec = target.speculative || {};
  const specBits = [];
  specBits.push(`drafted=${spec.drafted_tokens ?? 0}`);
  specBits.push(
    `accept=${
      spec.accept_rate_pct !== null && spec.accept_rate_pct !== undefined
        ? formatNumber(spec.accept_rate_pct, 1)
        : "0"
    }%`,
  );
  specBits.push(`accepted=${spec.accepted_tokens ?? 0}/${spec.draft_tokens ?? 0}`);
  specBits.push(
    `avg=${
      spec.mean_acceptance_length !== null && spec.mean_acceptance_length !== undefined
        ? formatNumber(spec.mean_acceptance_length, 2)
        : "0"
    }`,
  );
  if (
    spec.system_efficiency_pct !== null &&
    spec.system_efficiency_pct !== undefined
  )
    specBits.push(`eff=${formatNumber(spec.system_efficiency_pct, 1)}%`);
  head.length = 0;
  head.push(
    `latency=${valueOrDash(latency, 3)}s`,
    `ttft=${valueOrDash(ttft, 3)}s`,
    `pp tk/s=${valueOrDash(promptTps, 2)} (\u2191 ${valueOrDash(perfHistory.promptPeak || promptTps, 2)})`,
    `gen tk/s=${valueOrDash(generationTps, 2)} (\u2191 ${valueOrDash(perfHistory.generationPeak || generationTps, 2)})`,
  );
  const lines = [`<div>${escapeHtml(head.join(" · "))}</div>`];
  if (detail.length)
    lines.push(`<div class="value-subline">${escapeHtml(detail.join(" · "))}</div>`);
  if (specBits.length)
    lines.push(
      `<div class="value-subline">${escapeHtml(`spec ${specBits.join(" · ")}`)}</div>`,
    );
  return lines.join("");
}
function formatRuntimeRequestSummaryLine(runtime, statusHistory) {
  const rawStatus = runtime?.last_status;
  const statusNum = Number(rawStatus);
  const requestText = formatAbsoluteTimestamp(runtime?.last_request_at);
  const pathText = String(runtime?.last_path || "");
  return [
    Number.isFinite(statusNum)
      ? `HTTP ${Math.trunc(statusNum)}`
      : rawStatus !== null && rawStatus !== undefined && rawStatus !== ""
        ? String(rawStatus)
        : "HTTP -",
    `last path: ${pathText}`,
    requestText ? `last request: ${requestText}` : "last request: -",
  ].filter(Boolean);
}
function formatGenerationMetaLine(runtime) {
  return [
    runtime.mode || runtime.selector || runtime.engine || "-",
    runtime.served_model_name || runtime.model_id || runtime.container || "no container",
    Array.isArray(runtime.gpu_indices) && runtime.gpu_indices.length
      ? `GPUs ${runtime.gpu_indices.join(", ")}`
      : "GPU mapping unavailable",
  ];
}
function formatChatRuntimeStatsFlat(runtime) {
  if (!runtime)
    return '<div class="empty-variant-note">Start a preset to test it from the local chat interface.</div>';
  const statusHistory = updateStatusHistory(
    runtimeStatusHistoryById,
    runtime.id || runtime.instance_id,
    runtimeActivityStatus(runtime),
  );
  const queueBits = [];
  if (Number(runtime.waiting_requests || 0) > 0)
    queueBits.push(`waiting ${runtime.waiting_requests}`);
  if (Number(runtime.pending_requests || 0) > 0)
    queueBits.push(`pending ${runtime.pending_requests}`);
  if (Number(runtime.swapped_requests || 0) > 0)
    queueBits.push(`swapped ${runtime.swapped_requests}`);
  const tokenBits = [
    `input ${formatGroupedInt(runtime.last_input_tokens || 0)}`,
    `output ${formatGroupedInt(runtime.last_output_tokens || 0)}`,
    `total ${formatGroupedInt(runtime.last_total_tokens || 0)}`,
    `tools ${formatGroupedInt(runtime.last_tool_calls || 0)}`,
  ];
  const requestBits = formatRuntimeRequestSummaryLine(runtime, statusHistory);
  return `<div class="value-subline">${escapeHtml(formatGenerationMetaLine(runtime).join(" · "))}</div>${formatLastStatusCard(runtime, {})}${tokenBits.length ? `<div class="value-subline">${escapeHtml(tokenBits.join(" · "))}</div>` : ""}<div class="value-subline">${escapeHtml(requestBits.join(" · "))}</div><div class="value-subline">${escapeHtml(`status ${statusHistory.current}`)}</div>${queueBits.length ? `<div class="value-subline">${escapeHtml(queueBits.join(" · "))}</div>` : ""}`;
}
function formatGenerationRuntimeCard(runtime) {
  if (!runtime) return "";
  const statusHistory = updateStatusHistory(
    runtimeStatusHistoryById,
    runtime.id || runtime.instance_id,
    runtimeActivityStatus(runtime),
  );
  const queueBits = [];
  if (Number(runtime.waiting_requests || 0) > 0)
    queueBits.push(`waiting ${runtime.waiting_requests}`);
  if (Number(runtime.pending_requests || 0) > 0)
    queueBits.push(`pending ${runtime.pending_requests}`);
  if (Number(runtime.swapped_requests || 0) > 0)
    queueBits.push(`swapped ${runtime.swapped_requests}`);
  const tokenBits = [];
  if (runtime.last_input_tokens !== null && runtime.last_input_tokens !== undefined)
    tokenBits.push(`input ${formatGroupedInt(runtime.last_input_tokens)}`);
  if (runtime.last_output_tokens !== null && runtime.last_output_tokens !== undefined)
    tokenBits.push(`output ${formatGroupedInt(runtime.last_output_tokens)}`);
  if (runtime.last_total_tokens !== null && runtime.last_total_tokens !== undefined)
    tokenBits.push(`total ${formatGroupedInt(runtime.last_total_tokens)}`);
  if (runtime.last_tool_calls !== null && runtime.last_tool_calls !== undefined)
    tokenBits.push(`tools ${formatGroupedInt(runtime.last_tool_calls)}`);
  const meta = [
    runtime.mode || "-",
    runtime.container || "no container",
    Array.isArray(runtime.gpu_indices) && runtime.gpu_indices.length
      ? `GPUs ${runtime.gpu_indices.join(", ")}`
      : "GPU mapping unavailable",
  ];
  const requestBits = formatRuntimeRequestSummaryLine(runtime, statusHistory);
  return `<div class="generation-card"><div class="generation-card-head"><div><h3>${escapeHtml(runtime.display_name || runtime.id || "Runtime")}</h3><div class="generation-card-meta">${escapeHtml(meta.join(" · "))}</div></div></div><div class="generation-card-body">${formatLastStatusCard(runtime, {})}${tokenBits.length ? `<div class="value-subline">${escapeHtml(tokenBits.join(" · "))}</div>` : ""}<div class="value-subline">${escapeHtml(requestBits.join(" · "))}</div><div class="value-subline">${escapeHtml(`status ${statusHistory.current}`)}</div>${queueBits.length ? `<div class="value-subline">${escapeHtml(queueBits.join(" · "))}</div>` : ""}</div></div>`;
}
function renderGenerationStats(j) {
  const host = $("generationStatsContent");
  if (!host) return;
  const rows = runtimeStatsRows(j);
  const started = rows.filter((row) => {
    const signalFields = [
      row?.last_status,
      row?.last_latency_s,
      row?.last_ttft_s,
      row?.last_tokens_per_second,
      row?.last_total_tokens,
      row?.last_output_tokens,
      row?.last_request_at,
      row?.prompt_tps,
      row?.generation_tps,
      row?.gpu_kv_cache_usage_pct,
    ];
    return signalFields.some(
      (value) => value !== null && value !== undefined && value !== "" && value !== 0,
    );
  });
  const nextHtml = !rows.length
    ? '<div class="empty-variant-note">No runtime containers are active yet. Once a backend is online, this card will summarize live queue pressure, throughput, cache usage, and the latest request details for every running instance in one place.</div>'
    : !started.length
      ? '<div class="empty-variant-note">Runtime containers are online and waiting for inference. The first completed generation will populate per-instance latency, throughput, KV-cache, and token counters here so you can compare all active backends at a glance.</div>'
      : started.map(formatGenerationRuntimeCard).join("");
  if (isSelectionActiveWithin(host) && host.innerHTML === nextHtml) return;
  if (host.innerHTML !== nextHtml) host.innerHTML = nextHtml;
}
function formatRequestCard(runtime, metrics) {
  const base = `total=${metrics.total_requests | 0}, active=${metrics.active_requests | 0}, fail=${metrics.failed_requests | 0}, queue=${metrics.queued_requests | 0}`;
  return base;
}
function renderOverviewTracker() {
  const panel = findPanelByHeading("overview", "Status");
  if (!panel) return;
  let row = $("overviewTrackerRow");
  if (!row) {
    row = document.createElement("div");
    row.id = "overviewTrackerRow";
    row.className = "scope-strip";
    const grid = panel.querySelector(".grid");
    panel.insertBefore(row, grid || panel.querySelector(".msg") || null);
  }
  const rows = runtimeTrackingItems();
  if (rows.length <= 1) {
    row.innerHTML = "";
    row.classList.add("hidden");
    return;
  }
  row.classList.remove("hidden");
  const current = normalizeTrackedRuntimeId(selectedOverviewInstanceId);
  selectedOverviewInstanceId = current;
  row.innerHTML = `<span class="label">Track instance</span><div class="subtabs">${rows
    .map(
      (item) =>
        `<button class="subtab ${String(item.id || item.instance_id) === current ? "active" : ""}" onclick="setOverviewTrackedInstance('${String(item.id || item.instance_id)}')">${escapeHtml(String(item.id || item.instance_id))}</button>`,
    )
    .join("")}</div>`;
}
function renderLogTracker() {
  const card = document.querySelector(".logs.panel");
  if (!card) return;
  let row = $("logTrackerRow");
  if (!row) {
    row = document.createElement("div");
    row.id = "logTrackerRow";
    row.className = "scope-strip";
    card.insertBefore(row, $("log") || card.lastChild || null);
  }
  const rows = runtimeTrackingItems();
  if (currentLogSource === "audit" || rows.length <= 1) {
    row.innerHTML = "";
    row.classList.add("hidden");
    return;
  }
  row.classList.remove("hidden");
  const current = normalizeTrackedRuntimeId(selectedLogInstanceId);
  selectedLogInstanceId = current;
  row.innerHTML = `<span class="label">Track instance</span><div class="subtabs">${rows
    .map(
      (item) =>
        `<button class="subtab ${String(item.id || item.instance_id) === current ? "active" : ""}" onclick="setLogTrackedInstance('${String(item.id || item.instance_id)}')">${escapeHtml(String(item.id || item.instance_id))}</button>`,
    )
    .join("")}</div>`;
}
function renderOverviewStatus(j) {
  const metrics = (j && j.metrics) || {};
  const power = (j && j.power) || {};
  const runtime = trackedOverviewRuntime();
  const containers = Array.isArray(j?.containers) ? j.containers.filter(Boolean) : [];
  const modes = Array.isArray(j?.active_modes) ? j.active_modes.filter(Boolean) : [];
  if ($("summary"))
    $("summary").textContent = runtime
      ? `${runtime.id || runtime.instance_id} | ${runtime.mode || j.active_mode} | ${runtime.container || "no container"} | ${power.profile || "balanced"} | GPUs ${j.gpu_count | 0}`
      : `${modes[0] || j.active_mode || "-"} | ${containers[0] || j.container || "no container"} | ${power.profile || "balanced"} | GPUs ${j.gpu_count | 0}`;
  if ($("mode"))
    $("mode").textContent = formatRuntimeModeValue(j, runtime);
  if ($("container"))
    $("container").textContent = formatRuntimeContainerValue(j, runtime);
  if ($("req")) $("req").innerHTML = formatRequestCard(runtime, metrics);
  if ($("last")) $("last").innerHTML = formatUsersValue(j);
  if ($("uptime")) $("uptime").textContent = fmtUptime(j.uptime_seconds);
  if ($("powerbox"))
    $("powerbox").textContent =
      `profile=${power.profile || "-"}, GPU=${power.gpu || "-"}, CPU=${power.cpu || "-"}, fans=${power.fans || "-"}, container=${power.container || "-"}, idle=${power.idle_for_seconds | 0}s`;
  renderGenerationStats(j);
  renderOverviewTracker();
}
async function fetchJsonWithTimeout(url, options = {}, timeoutMs = 12000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), Math.max(1000, Number(timeoutMs || 12000)));
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    return response;
  } catch (e) {
    if (e?.name === "AbortError") {
      throw new Error(`Request timed out after ${Math.round(Math.max(1000, Number(timeoutMs || 12000)) / 1000)}s`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
function safeRenderStep(label, fn, errors) {
  try {
    fn();
  } catch (e) {
    errors.push(`${label}: ${messageText(e)}`);
  }
}
function setEditorState(editorId, introId, open) {
  const ed = $(editorId),
    intro = $(introId);
  if (ed) ed.classList.toggle("open", !!open);
  if (intro) intro.classList.toggle("hidden", !!open);
}
function openUserEditor() {
  ensureUsersUi();
  setEditorState("userEditor", "userIntro", true);
}
function openGroupEditor() {
  ensureGroupUi();
  setEditorState("groupEditor", "groupIntro", true);
}
ensureUsersUi = function () {
  const tabs = document.querySelector(".tabs");
  if (tabs && !document.getElementById("usersTabBtn")) {
    const b = document.createElement("button");
    b.className = "tab";
    b.id = "usersTabBtn";
    b.textContent = "Users";
    b.onclick = (ev) => tab(ev, "users");
    tabs.insertBefore(
      b,
      tabs.querySelector('.tab[onclick*="metrics"]') || null,
    );
  }
  const main = document.querySelector("main.container");
  if (!main) return;
  let section = $("users");
  if (!section) {
    section = document.createElement("section");
    section.id = "users";
    section.className = "tabpane content-tab";
    main.insertBefore(section, document.getElementById("metrics"));
  }
  if (section.dataset.v414Users !== "1") {
    section.dataset.v414Users = "1";
    section.innerHTML = `<div class="panel"><div class="panel-head"><h2>User Accounts</h2><button class="add-preset-btn" title="New user" aria-label="New user" onclick="resetUserForm(false)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none"/></svg></button></div><div class="preset-intro" id="userIntro">Manage per-user API keys, access scopes, and Codex-style scored budgets. The configured list stays visible while the editor is collapsed.</div><div class="preset-editor" id="userEditor"><div class="formgrid"><label>User name<input id="userName" placeholder="client_a" /></label><label>Allowed targets<input id="userTargets" placeholder="*, legacy, GPU0, GPU1" /></label><label>Groups<input id="userGroups" placeholder="starter, premium" /></label><label>5h score budget<input id="userScore5h" type="number" step="0.1" placeholder="unlimited" /></label><label>Weekly score budget<input id="userScoreWeek" type="number" step="0.1" placeholder="unlimited" /></label><label>Max tokens / message<input id="userMaxTokensMsg" type="number" step="1" placeholder="unlimited" /></label><label>Max tool calls / message<input id="userMaxToolsMsg" type="number" step="1" placeholder="unlimited" /></label><label>Input token weight<input id="userInputTokenWeight" type="number" step="0.001" placeholder="default" /></label><label>Output token weight<input id="userOutputTokenWeight" type="number" step="0.001" placeholder="default" /></label><label>Tool-call weight<input id="userToolCallWeight" type="number" step="0.001" placeholder="default" /></label><label>Thinking-second weight<input id="userThinkingSecondWeight" type="number" step="0.001" placeholder="default" /></label><label>Enabled<select id="userEnabled"><option value="true">Enabled</option><option value="false">Disabled</option></select></label></div><div class="preset-form-actions"><button class="btn green" onclick="saveUserForm()">Save User</button><button class="btn red" onclick="resetUserForm(true)">Cancel</button></div></div><div class="msg" id="usersMsg"></div><div class="panel" style="margin-top:12px"><h2>Configured Users</h2><div id="usersGrid" class="api-grid"></div></div></div>`;
  }
};
resetUserForm = function (collapse = true) {
  ensureUsersUi();
  selectedUserName = "";
  $("userName").disabled = false;
  $("userName").value = "";
  $("userTargets").value = "*";
  $("userGroups").value = "";
  $("userScore5h").value = "";
  $("userScoreWeek").value = "";
  $("userMaxTokensMsg").value = "";
  $("userMaxToolsMsg").value = "";
  $("userInputTokenWeight").value = "";
  $("userOutputTokenWeight").value = "";
  $("userToolCallWeight").value = "";
  $("userThinkingSecondWeight").value = "";
  $("userEnabled").value = "true";
  setEditorState("userEditor", "userIntro", !collapse);
  setUsersMsg("");
};
collectUserForm = function () {
  function val(id) {
    return (($(id) && $(id).value) || "").trim();
  }
  return {
    name: val("userName"),
    allowed_targets: val("userTargets")
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
    groups: val("userGroups")
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
    enabled: $("userEnabled").value === "true",
    generate_api_key: !selectedUserName,
    limits: {
      score_per_5h: parseQuotaNumber("userScore5h"),
      score_per_week: parseQuotaNumber("userScoreWeek"),
      max_tokens_per_message: parseQuotaNumber("userMaxTokensMsg"),
      max_tool_calls_per_message: parseQuotaNumber("userMaxToolsMsg"),
      input_token_weight: parseQuotaNumber("userInputTokenWeight"),
      output_token_weight: parseQuotaNumber("userOutputTokenWeight"),
      tool_call_weight: parseQuotaNumber("userToolCallWeight"),
      thinking_second_weight: parseQuotaNumber("userThinkingSecondWeight"),
    },
  };
};
editUser = function (name) {
  const user = ((lastStatus && lastStatus.users) || []).find(
    (u) => u.name === name,
  );
  if (!user) return;
  ensureUsersUi();
  selectedUserName = name;
  $("userName").disabled = true;
  $("userName").value = user.name;
  $("userTargets").value = (user.allowed_targets || []).join(", ");
  $("userGroups").value = (user.groups || []).join(", ");
  $("userScore5h").value = user.limits.score_per_5h ?? "";
  $("userScoreWeek").value = user.limits.score_per_week ?? "";
  $("userMaxTokensMsg").value = user.limits.max_tokens_per_message ?? "";
  $("userMaxToolsMsg").value = user.limits.max_tool_calls_per_message ?? "";
  $("userInputTokenWeight").value = user.limits.input_token_weight ?? "";
  $("userOutputTokenWeight").value = user.limits.output_token_weight ?? "";
  $("userToolCallWeight").value = user.limits.tool_call_weight ?? "";
  $("userThinkingSecondWeight").value =
    user.limits.thinking_second_weight ?? "";
  $("userEnabled").value = String(!!user.enabled);
  openUserEditor();
};
renderUsers = function (users) {
  ensureUsersUi();
  const grid = $("usersGrid");
  if (!grid) return;
  users = users || [];
  if (selectedUserName && !users.some((u) => u.name === selectedUserName))
    selectedUserName = "";
  grid.innerHTML =
    users
      .map((u) => {
        const actions = [
          renderIconButton({
            title: "Edit",
            action: `editUser('${u.name}')`,
            icon: "edit",
          }),
          renderIconButton({
            title: u.api_key_available ? "Show API key" : "Show API key unavailable",
            action: `showUserApiKey('${u.name}')`,
            icon: "key",
          }),
          renderIconButton({
            title: "Reset API key",
            action: `resetUserKey('${u.name}')`,
            icon: "reset",
          }),
          renderIconButton({
            title: "Delete",
            action: `deleteUserByName('${u.name}')`,
            icon: "delete",
          }),
        ].join("");
        return `<div class="api-card"><div class="api-card-head"><h3>${u.name}<br><span class="label">${u.enabled ? "enabled" : "disabled"} &middot; access ${(u.effective_allowed_targets || u.allowed_targets || []).join(", ") || "*"}</span></h3><span class="preset-actions">${actions}</span></div><p>Groups: ${(u.groups || []).join(", ") || "none"}</p><p>API key: ${u.has_api_key ? (u.api_key_available ? "stored and viewable" : "legacy key, reset once to store it") : "not issued yet"}</p><p>Last 5h: ${quotaWindowText((u.usage || {}).window_5h)}</p><p>Last week: ${quotaWindowText((u.usage || {}).window_week)}</p><p class="label">Direct budgets &middot; ${quotaBudgetLine(u.limits || {})}</p><p class="label">Direct weights &middot; ${quotaWeightLine(u.limits || {})}</p><p class="label">Effective budgets &middot; ${quotaBudgetLine(u.effective_limits || {})}</p><p class="label">Effective weights &middot; ${quotaWeightLine(u.effective_limits || {})}</p></div>`;
      })
      .join("") || '<div class="value">No API users configured yet.</div>';
};
ensureGroupUi = function () {
  ensureUsersUi();
  const users = $("users");
  if (!users) return;
  let panel = $("groupsPanel");
  if (!panel) {
    panel = document.createElement("div");
    panel.className = "panel";
    panel.id = "groupsPanel";
    users.appendChild(panel);
  }
  if (panel.dataset.v414Groups !== "1") {
    panel.dataset.v414Groups = "1";
    panel.innerHTML = `<div class="panel-head"><h2>User Groups / Plans</h2><button class="add-preset-btn" title="New group" aria-label="New group" onclick="resetGroupForm(false)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none"/></svg></button></div><div class="preset-intro" id="groupIntro">Define reusable plans that carry scored budgets, per-message caps, and access scopes. The configured list stays visible while the editor is collapsed.</div><div class="preset-editor" id="groupEditor"><div class="formgrid"><label>Group name<input id="groupName" placeholder="starter" /></label><label>Description<input id="groupDescription" placeholder="Shared plan description" /></label><label>Allowed targets<input id="groupTargets" placeholder="*, legacy, GPU0, GPU1" /></label><label>5h score budget<input id="groupScore5h" type="number" step="0.1" placeholder="unlimited" /></label><label>Weekly score budget<input id="groupScoreWeek" type="number" step="0.1" placeholder="unlimited" /></label><label>Max tokens / message<input id="groupMaxTokensMsg" type="number" step="1" placeholder="unlimited" /></label><label>Max tool calls / message<input id="groupMaxToolsMsg" type="number" step="1" placeholder="unlimited" /></label><label>Input token weight<input id="groupInputTokenWeight" type="number" step="0.001" placeholder="default" /></label><label>Output token weight<input id="groupOutputTokenWeight" type="number" step="0.001" placeholder="default" /></label><label>Tool-call weight<input id="groupToolCallWeight" type="number" step="0.001" placeholder="default" /></label><label>Thinking-second weight<input id="groupThinkingSecondWeight" type="number" step="0.001" placeholder="default" /></label><label>Enabled<select id="groupEnabled"><option value="true">Enabled</option><option value="false">Disabled</option></select></label></div><div class="preset-form-actions"><button class="btn green" onclick="saveGroupForm()">Save Group</button><button class="btn red" onclick="resetGroupForm(true)">Cancel</button></div></div><div class="msg" id="groupsMsg"></div><div class="panel" style="margin-top:12px"><h2>Configured Groups</h2><div id="groupsGrid" class="api-grid"></div></div>`;
  }
};
resetGroupForm = function (collapse = true) {
  ensureGroupUi();
  selectedGroupName = "";
  $("groupName").disabled = false;
  $("groupName").value = "";
  $("groupDescription").value = "";
  $("groupTargets").value = "*";
  $("groupScore5h").value = "";
  $("groupScoreWeek").value = "";
  $("groupMaxTokensMsg").value = "";
  $("groupMaxToolsMsg").value = "";
  $("groupInputTokenWeight").value = "";
  $("groupOutputTokenWeight").value = "";
  $("groupToolCallWeight").value = "";
  $("groupThinkingSecondWeight").value = "";
  $("groupEnabled").value = "true";
  setEditorState("groupEditor", "groupIntro", !collapse);
  setGroupsMsg("");
};
collectGroupForm = function () {
  function val(id) {
    return (($(id) && $(id).value) || "").trim();
  }
  return {
    name: val("groupName"),
    description: val("groupDescription"),
    allowed_targets: val("groupTargets")
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
    enabled: $("groupEnabled").value === "true",
    limits: {
      score_per_5h: parseQuotaNumber("groupScore5h"),
      score_per_week: parseQuotaNumber("groupScoreWeek"),
      max_tokens_per_message: parseQuotaNumber("groupMaxTokensMsg"),
      max_tool_calls_per_message: parseQuotaNumber("groupMaxToolsMsg"),
      input_token_weight: parseQuotaNumber("groupInputTokenWeight"),
      output_token_weight: parseQuotaNumber("groupOutputTokenWeight"),
      tool_call_weight: parseQuotaNumber("groupToolCallWeight"),
      thinking_second_weight: parseQuotaNumber("groupThinkingSecondWeight"),
    },
  };
};
editGroup = function (name) {
  const group = ((lastStatus && lastStatus.groups) || []).find(
    (g) => g.name === name,
  );
  if (!group) return;
  ensureGroupUi();
  selectedGroupName = name;
  $("groupName").disabled = true;
  $("groupName").value = group.name;
  $("groupDescription").value = group.description || "";
  $("groupTargets").value = (group.allowed_targets || []).join(", ");
  $("groupScore5h").value = group.limits.score_per_5h ?? "";
  $("groupScoreWeek").value = group.limits.score_per_week ?? "";
  $("groupMaxTokensMsg").value = group.limits.max_tokens_per_message ?? "";
  $("groupMaxToolsMsg").value = group.limits.max_tool_calls_per_message ?? "";
  $("groupInputTokenWeight").value = group.limits.input_token_weight ?? "";
  $("groupOutputTokenWeight").value = group.limits.output_token_weight ?? "";
  $("groupToolCallWeight").value = group.limits.tool_call_weight ?? "";
  $("groupThinkingSecondWeight").value =
    group.limits.thinking_second_weight ?? "";
  $("groupEnabled").value = String(!!group.enabled);
  openGroupEditor();
};
renderGroups = function (groups) {
  ensureGroupUi();
  const grid = $("groupsGrid");
  if (!grid) return;
  groups = groups || [];
  if (selectedGroupName && !groups.some((g) => g.name === selectedGroupName))
    selectedGroupName = "";
  grid.innerHTML =
    groups
      .map(
        (g) =>
          `<div class="api-card"><div class="api-card-head"><h3>${g.name}<br><span class="label">${g.enabled ? "enabled" : "disabled"} · access ${(g.allowed_targets || []).join(", ") || "*"}</span></h3><span class="preset-actions"><button class="iconbtn" title="Edit" onclick="editGroup('${g.name}')">✏️</button><button class="iconbtn" title="Delete" onclick="deleteGroupByName('${g.name}')">❌</button></span></div><p>${g.description || "No description"}</p><p class="label">Configured budgets · ${quotaBudgetLine(g.limits || {})}</p><p class="label">Configured weights · ${quotaWeightLine(g.limits || {})}</p><p class="label">Resolved budgets · ${quotaBudgetLine(g.resolved_limits || g.limits || {})}</p><p class="label">Resolved weights · ${quotaWeightLine(g.resolved_limits || g.limits || {})}</p></div>`,
      )
      .join("") || '<div class="value">No groups configured yet.</div>';
};

// Audit, instances, preset scopes, and host actions
renderAudit = function (cfg) {
  cfg = cfg || {};
  ensureV414Layout();
  const adminPort = (lastStatus && lastStatus.admin_port) || 8008;
  const proxyPort = (lastStatus && lastStatus.proxy_port) || 8009;
  const adminPath = cfg.admin_path || "/admin";
  const online = !!cfg.online_enabled;
  const authOptional = !!cfg.allow_proxy_without_api_key;
  const localEnabled = !!cfg.local_api_enabled;
  const localPort = cfg.local_api_port || 10881;
  if ($("auditAdminEndpoint"))
    $("auditAdminEndpoint").innerHTML = `:${adminPort}${adminPath}`;
  if ($("auditProxyEndpoint"))
    $("auditProxyEndpoint").innerHTML = `:${proxyPort}`;
  if ($("auditExposure"))
    $("auditExposure").textContent = online
      ? "online through proxy/admin only"
      : "local/private only";
  if ($("auditLocalApi"))
    $("auditLocalApi").textContent = localEnabled
      ? `127.0.0.1:${localPort}`
      : "disabled";
  if ($("auditSummary"))
    $("auditSummary").innerHTML =
      "Audit entries capture admin actions, proxy authentication outcomes, quota denials, API usage, group changes, and user-management events. Use the shared log viewer below to inspect either Docker runtime logs or the audit log stream.";
  if ($("auditPolicyText"))
    $("auditPolicyText").innerHTML =
      `Proxy API keys are currently <b>${authOptional ? "optional" : "required"}</b>. Admin UI remains under <code>:${adminPort}${adminPath}</code>.`;
  mirrorAuthToggles(authOptional);
};
saveAuthSettings = async function () {
  const allow = !!(
    $("auditAllowAnonymousProxy") && $("auditAllowAnonymousProxy").checked
  );
  mirrorAuthToggles(allow);
  try {
    const r = await fetch("/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "save_server_config",
        allow_proxy_without_api_key: allow,
      }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "config failed");
    if (j.server_config) renderAudit(j.server_config);
    setAuditMsg("Saved access policy");
    await refreshStatus();
  } catch (e) {
    alert("Access policy failed: " + e);
  }
};
renderInstances = function (instances) {
  ensureV414Layout();
  const tabs = $("instanceTabs");
  const summary = $("instanceSummary");
  const btn = $("instanceEnableBtn");
  const panel = findPanelByHeading("system", "Instances");
  if (!tabs || !summary || !panel) return;
  instances = scopeItems();
  if (
    !selectedScope ||
    !(
      selectedScope === "GLOBAL" ||
      instances.some((x) => x.id === selectedScope)
    )
  )
    selectedScope =
      singleScopeItems()[0]?.id || pairScopeItems()[0]?.id || "GLOBAL";
  const tabsHtml =
    singleScopeItems()
      .map(
        (x) =>
          `<button class="subtab ${x.id === currentScope() ? "active" : ""}" onclick="setScope('${x.id}')">${x.id}${x.running ? " • on" : " • off"}</button>`,
      )
      .join("") +
    pairScopeItems()
      .map(
        (x) =>
          `<button class="subtab ${x.id === currentScope() ? "active" : ""}" onclick="setScope('${x.id}')">Pair ${(x.gpu_indices || []).join("+")}${x.running ? " • on" : " • off"}</button>`,
      )
      .join("") +
    `<button class="subtab ${scopeIsGlobal() ? "active" : ""}" onclick="setScope('GLOBAL')">Global</button>`;
  tabs.innerHTML = tabsHtml;
  ensurePairManager();
  const target = currentScopeInstance(false);
  const actionButtons = [...(panel.querySelectorAll("#instanceActionRow .btn") || [])];
  if (scopeIsGlobal() && target && gpuCount() === 2) {
    summary.innerHTML = `Global scope controls the only dual pair <code>${target.id}</code> on GPUs ${(target.gpu_indices || []).join(", ")} · mode ${target.mode} · port ${target.port} · proxy <code>${target.proxy_prefix}/</code>`;
    if (btn) {
      btn.disabled = false;
      btn.textContent = target.enabled
        ? "Disable Boot Autostart"
        : "Enable Boot Autostart";
    }
    actionButtons.forEach((x) => (x.disabled = false));
  } else if (scopeIsGlobal()) {
    summary.innerHTML =
      "Global scope selected. Create or choose a dual pair tab to manage arbitrary two-GPU dual presets. The profile and optimization controls below still apply against the active global context.";
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Select a GPU or Pair Scope";
    }
    actionButtons.forEach((x) => (x.disabled = true));
  } else if (target) {
    summary.innerHTML = `${scopeLabel(target)} · ${target.assignment_text} · port ${target.port} · ${target.running ? "running" : "stopped"} · proxy <code>${target.proxy_prefix}/</code> · ${target.enabled ? "autostart enabled" : "autostart disabled"}`;
    if (btn) {
      btn.disabled = false;
      btn.textContent = target.enabled
        ? "Disable Boot Autostart"
        : "Enable Boot Autostart";
    }
    actionButtons.forEach((x) => (x.disabled = false));
  } else {
    summary.textContent = "No GPU instances configured";
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Boot autostart unavailable";
    }
    actionButtons.forEach((x) => (x.disabled = true));
  }
  if ($("logInstanceLabel"))
    $("logInstanceLabel").textContent = currentLogLabel();
};
renderPresetScopeTabs = function () {
  ensureDynamicPresetLayout();
  const tabs = $("presetScopeTabs");
  const summary = $("presetScopeSummary");
  if (!tabs || !summary) return;
  tabs.innerHTML = "";
  const scopes = [{ id: "GLOBAL", display_name: "Global" }, ...scopeItems()];
  scopes.forEach((item) => {
    const btn = document.createElement("button");
    btn.className = `subtab${selectedScope === item.id ? " active" : ""}`;
    btn.textContent = item.id === "GLOBAL" ? "Global" : scopeLabel(item);
    btn.onclick = () => setScope(item.id, true);
    tabs.appendChild(btn);
  });
  if (scopeIsGlobal()) {
    summary.textContent =
      "Global scope fans single-GPU presets out across every GPU, dual presets across every two-GPU pair, and multi-GPU presets into the shared runtime.";
  } else {
    const current = currentScopeInstance(true) || currentScopeInstance(false);
    summary.textContent = current
      ? `${scopeLabel(current)} selected. Matching ${current.kind === "dual" ? "dual" : "single"} presets below will apply to this scope.`
      : "Select a scope to apply discovered presets.";
  }
};
updateScopedCards = function () {
  const target = currentScopeInstance(false);
  if ($("profileScopeNote"))
    $("profileScopeNote").innerHTML = `${scopeIsGlobal() ? "Global" : scopeLabel(target)} scope: applying a power profile resets the recorded GPU peak values and starts a fresh measurement session.`;
  if ($("powerScopeNote"))
    $("powerScopeNote").innerHTML = `${scopeIsGlobal() ? "Global" : scopeLabel(target)} scope: optimization and cooling actions use the selected runtime context while keeping host-level power state in sync.`;
  renderLogSourcePanel();
};
powerAction = async function (a) {
  const cur = currentScopeInstance(false);
  const needsTarget = [
    "stop_container",
    "start_instance",
    "restart_instance",
    "toggle_enabled",
  ].includes(a);
  if (needsTarget && !cur) {
    alert("Select a GPU or Pair scope first.");
    return;
  }
  if (a === "stop_container" && !confirm(`Stop ${scopeLabel(cur)} now?`))
    return;
  try {
    await post("/admin/power", {
      action: a,
      instance_id: cur ? cur.id : null,
      enabled: cur ? !cur.enabled : undefined,
    });
  } catch (e) {
    alert(e);
  }
};
instanceAction = async function (a) {
  await powerAction(a);
};
toggleInstanceEnabled = async function () {
  const cur = currentScopeInstance(false);
  if (!cur) {
    alert("Select a GPU or Pair scope first.");
    return;
  }
  try {
    await post("/admin/power", {
      action: "toggle_enabled",
      instance_id: cur.id,
      enabled: !cur.enabled,
    });
  } catch (e) {
    alert(e);
  }
};
async function createPairGroup(first = null, second = null) {
  if (gpuCount() < 2) {
    alert("At least two GPUs are required to create a dual pair.");
    return;
  }
  let a = first,
    b = second;
  if (a === null || b === null) {
    a = prompt(`First GPU index (0-${Math.max(gpuCount() - 1, 0)}):`, "0");
    if (a === null) return;
    b = prompt(`Second GPU index (0-${Math.max(gpuCount() - 1, 0)}):`, "1");
    if (b === null) return;
  }
  const id = canonicalPairId(a, b);
  if (!id) {
    alert("Select two distinct GPU indices.");
    return;
  }
  try {
    const r = await fetch("/admin/instances", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "save_pair",
        gpu_indices: [Number(a), Number(b)],
        mode: "vllm/dual",
        enabled: false,
      }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "pair save failed");
    setInstanceMsg(`Saved pair group ${id}`);
    await refreshStatus();
    setScope(id, false);
  } catch (e) {
    alert("Pair group failed: " + e);
  }
}
async function deleteCurrentPairGroup() {
  const cur = currentScopeInstance(true);
  if (!cur || cur.kind !== "dual") {
    alert("Select a dual pair scope first.");
    return;
  }
  if (!confirm(`Delete pair group ${cur.id}?`)) return;
  try {
    const r = await fetch("/admin/instances", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "delete_pair", instance_id: cur.id }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "pair delete failed");
    setInstanceMsg(`Deleted pair group ${cur.id}`);
    await refreshStatus();
    setScope("GLOBAL", false);
  } catch (e) {
    alert("Pair delete failed: " + e);
  }
}
switchMode = async function (m) {
  const cur = currentScopeInstance(true);
  if (!cur || cur.kind === "dual") {
    alert("Select a single GPU tab to apply a single-GPU preset.");
    return;
  }
  const blockingPair = pairScopeItems().find(
    (x) => x.running && (x.gpu_indices || []).includes(Number(cur.gpu_index)),
  );
  const warning = blockingPair
    ? `\n\nWarning: GPU ${cur.gpu_index} is currently occupied by ${blockingPair.id} running ${blockingPair.mode}. Continuing will stop that pair and replace it with ${m} on ${cur.id}.`
    : "";
  if (confirm(`Assign ${m} to ${cur.id} and start it?${warning}`))
    try {
      await post("/admin/switch", { instance_id: cur.id, mode: m });
    } catch (e) {
      alert(e);
    }
};
async function switchDualMode(m) {
  const cur = currentScopeInstance(false);
  if (!cur || cur.kind !== "dual") {
    alert(
      "Choose a dual pair tab, or use Global on an exactly-two-GPU server, before applying a dual preset.",
    );
    return;
  }
  if (
    confirm(
      `Apply dual preset ${m} to ${cur.id} on GPUs ${(cur.gpu_indices || []).join(", ")}? This will stop overlapping runtimes that already use those GPUs.`,
    )
  )
    try {
      await post("/admin/switch", { instance_id: cur.id, mode: m });
    } catch (e) {
      alert(e);
    }
}
function profileDescription(p) {
  const d = {
    eco: "Eco profile: lower GPU power limits, lower idle clocks, powersave CPU governor, faster idle/container stop timers.",
    balanced:
      "Balanced profile: normal server profile with 280W active GPU cap, idle downclocking after 10 minutes, and container stop after 1 hour.",
    default:
      "Default profile: keeps the 280W safety GPU cap but removes idle clock locking, uses schedutil CPU while active, and keeps standard idle timers.",
    turbo:
      "Turbo profile: higher GPU power allowance, performance CPU governor, relaxed idle timers, and minimal downclocking. Use when performance matters more than power.",
  };
  return d[p] || "Apply profile?";
}
profile = async function (p) {
  const cur = currentScopeInstance(false);
  const instanceId = scopeIsGlobal()
    ? legacyGlobalDualScope()
      ? "GLOBAL"
      : cur?.id || "GLOBAL"
    : cur?.id || null;
  const scopeText = scopeIsGlobal() ? "Global" : scopeLabel(cur);
  if (
    !confirm(
      profileDescription(p) +
        `\n\nApply this profile now to ${scopeText} scope and reset the recorded GPU peaks?`,
    )
  )
    return;
  try {
    await post(
      "/admin/profile",
      { profile: p, instance_id: instanceId },
      `/admin/profile ${p} ${instanceId || "GLOBAL"}`,
    );
  } catch (e) {
    alert(e);
  }
};
function applyDirectoryPayload(j) {
  if (!lastStatus) lastStatus = {};
  if (Array.isArray(j.users)) {
    lastStatus.users = j.users;
    renderUsers(j.users);
  }
  if (Array.isArray(j.groups)) {
    lastStatus.groups = j.groups;
    renderGroups(j.groups);
  }
  if (j.server_config) {
    lastStatus.server_config = j.server_config;
    renderAudit(j.server_config);
  }
}
saveGroupForm = async function () {
  try {
    const r = await fetch("/admin/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "save", group: collectGroupForm() }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "group save failed");
    applyDirectoryPayload(j);
    resetGroupForm(true);
    setGroupsMsg("Saved group " + j.group.name);
    refreshStatus().catch(() => {});
  } catch (e) {
    alert("Group save failed: " + e);
  }
};
deleteGroupByName = async function (name) {
  if (!confirm("Delete group " + name + "?")) return;
  try {
    const r = await fetch("/admin/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "delete", name }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "group delete failed");
    applyDirectoryPayload(j);
    if (selectedGroupName === name) resetGroupForm(true);
    setGroupsMsg("Deleted group " + name);
    refreshStatus().catch(() => {});
  } catch (e) {
    alert("Group delete failed: " + e);
  }
};
pairingEnabled = function () {
  return !!(
    lastStatus &&
    lastStatus.server_config &&
    lastStatus.server_config.gpu_pairing_enabled
  );
};
legacyGlobalDualScope = function () {
  return gpuCount() === 2 && !pairingEnabled();
};
// Canonical runtime UI path
const UI_STATE_KEY = "club3090-ui-state";
let uiStateHydrated = false;
let uiStateSaveTimer = null;
let lastQueuedUiStateJson = "";
let instanceBusyState = { active: false, message: "" };
let currentLogSignature = "";
let statusPollTimer = null;
function readCachedUiState() {
  try {
    return JSON.parse(localStorage.getItem(UI_STATE_KEY) || "{}") || {};
  } catch (e) {
    return {};
  }
}
function writeCachedUiState(data) {
  try {
    localStorage.setItem(UI_STATE_KEY, JSON.stringify(data || {}));
  } catch (e) {}
}
function readJsonCache(key, fallback) {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || "null");
    return parsed && typeof parsed === "object" ? parsed : fallback;
  } catch (e) {
    return fallback;
  }
}
function savePresetSummaryCache() {
  try {
    localStorage.setItem(SUMMARY_CACHE_KEY, JSON.stringify(presetSummaryCache));
  } catch (e) {}
}
function hydratePresetSummaryCache() {
  const cached = readJsonCache(SUMMARY_CACHE_KEY, null);
  if (!cached) return;
  presetSummaryCache = {
    persistent: cached.persistent && typeof cached.persistent === "object" ? cached.persistent : {},
    transient: cached.transient && typeof cached.transient === "object" ? cached.transient : {},
    restartTargets: Array.isArray(cached.restartTargets) ? cached.restartTargets : [],
    lastSeenUptime: Number(cached.lastSeenUptime || 0),
  };
}
function saveChatState() {
  try {
    const nextRevision = Math.max(0, Number(chatState.revision || 0) || 0) + 1;
    chatState.revision = nextRevision;
    const safe = { ...currentChatStatePayload(), revision: nextRevision };
    localStorage.setItem(CHAT_STATE_KEY, JSON.stringify(safe));
    queueServerChatStateSave(safe);
  } catch (e) {}
}
function chatHydrationPending() {
  return !chatStateHydrated && !!chatStateHydratingPromise;
}
function ensureChatSeedConversation() {
  if (Array.isArray(chatState.conversations) && chatState.conversations.length) {
    if (
      chatState.activeConversationId &&
      chatState.conversations.some(
        (conversation) => conversation.id === chatState.activeConversationId,
      )
    ) {
      return;
    }
    chatState.activeConversationId = chatState.conversations[0].id;
    return;
  }
  const firstConversation = createChatConversation();
  chatState.conversations = [firstConversation];
  chatState.activeConversationId = firstConversation.id;
  syncChatStateFromActiveConversation();
}
async function hydrateChatState() {
  if (chatStateHydrated) return chatState;
  if (chatStateHydratingPromise) return chatStateHydratingPromise;
  chatStateHydratingPromise = (async () => {
    logDebugEvent("chat_hydrate_start", {
      activeConversationId: String(chatState.activeConversationId || ""),
      localConversationCount: chatConversations().length,
    });
    let cached = null;
    let migratedFromLocalCache = false;
    try {
      const response = await fetchJsonWithTimeout(
        `/admin/chat-state?titles=1&_=${Date.now()}`,
        { cache: "no-store" },
        5000,
      );
      const payload = await response.json();
      if (response.ok && payload?.ok && payload?.state) cached = payload.state;
    } catch (e) {}
    if (!cached) {
      cached =
        readJsonCache(CHAT_STATE_KEY, null) ||
        readJsonCache(LEGACY_CHAT_STATE_KEY, null) ||
        readJsonCache(LEGACY_CHAT_STATE_KEY_V516, null);
      migratedFromLocalCache = !!cached;
    }
    if (cached && Array.isArray(cached.conversations)) {
      const conversations = cached.conversations
        .map((conversation) => createChatConversation(conversation))
        .filter(Boolean);
      if (conversations.length) {
        chatState = {
          ...chatState,
          revision: Math.max(0, Number(cached.revision || 0) || 0),
          activeConversationId: String(
            cached.activeConversationId || conversations[0].id,
          ),
          conversations,
          promptTemplates: Array.isArray(cached.promptTemplates)
            ? cached.promptTemplates
                .map((template) => ({
                  id: String(template?.id || chatConversationId()),
                  name: String(template?.name || "").trim(),
                  text: String(template?.text || ""),
                }))
                .filter((template) => template.name || template.text)
            : [],
        };
      }
    } else if (cached) {
      const imported = createChatConversation({
        title: CHAT_UNTITLED_TITLE,
        presetId: String(cached.presetId || ""),
        apiPresetName: String(cached.apiPresetName || ""),
        params: cached.params && typeof cached.params === "object" ? cached.params : {},
        systemPrompt: String(cached.systemPrompt || ""),
        messages: Array.isArray(cached.messages) ? cached.messages : [],
        attachments: Array.isArray(cached.attachments) ? cached.attachments : [],
        autoCompactEnabled: cached.autoCompactEnabled !== false,
        autoCompactThresholdPct: cached.autoCompactThresholdPct,
      });
      chatState = {
        ...chatState,
        revision: Math.max(0, Number(cached.revision || 0) || 0),
        activeConversationId: imported.id,
        conversations: [imported],
      };
    }
    ensureChatSeedConversation();
    syncChatStateFromActiveConversation();
    chatStateServerReady = true;
    chatStateHydrated = true;
    logDebugEvent("chat_hydrate_ready", {
      revision: Number(chatState.revision || 0),
      activeConversationId: String(chatState.activeConversationId || ""),
      conversationCount: chatConversations().length,
      migratedFromLocalCache,
    });
    if (migratedFromLocalCache) saveChatState();
    if (chatState.activeConversationId) {
      loadChatConversationDetail(chatState.activeConversationId, { silent: true }).catch(() => {});
    }
    return chatState;
  })().catch((error) => {
    logDebugEvent("chat_hydrate_error", {
      error: error?.message || String(error || ""),
    });
    throw error;
  })()
    .finally(() => {
      chatStateHydratingPromise = null;
    });
  return chatStateHydratingPromise;
}
async function loadChatConversationDetail(conversationId, options = {}) {
  const targetId = String(conversationId || "").trim();
  if (!targetId) return null;
  const current = chatConversations().find((conversation) => conversation.id === targetId);
  if (current?.messagesLoaded && !options.force) return current;
  if (chatConversationDetailLoadPromises.has(targetId) && !options.force) {
    return chatConversationDetailLoadPromises.get(targetId);
  }
  const loadNonce = ++chatConversationLoadNonce;
  logDebugEvent("chat_detail_load_start", {
    conversationId: targetId,
    activeConversationId: String(chatState.activeConversationId || ""),
    force: !!options.force,
    nonce: loadNonce,
  });
  const loadPromise = (async () => {
    const response = await fetchJsonWithTimeout(
      `/admin/chat-conversation?conversation_id=${encodeURIComponent(targetId)}&_=${Date.now()}`,
      { cache: "no-store" },
      5000,
    );
    const payload = await response.json();
    if (!response.ok || !payload?.ok || !payload?.conversation) {
      throw new Error(payload?.error || "Failed to load conversation.");
    }
    const detail = createChatConversation({ ...payload.conversation, messagesLoaded: true });
    chatState.revision = Math.max(0, Number(payload.revision || chatState.revision || 0) || 0);
    chatState.conversations = chatConversations().map((conversation) =>
      conversation.id === targetId ? detail : conversation,
    );
    logDebugEvent("chat_detail_load_success", {
      conversationId: targetId,
      activeConversationId: String(chatState.activeConversationId || ""),
      revision: Number(chatState.revision || 0),
      messageCount: Array.isArray(detail.messages) ? detail.messages.length : 0,
      nonce: loadNonce,
    });
    if (chatState.activeConversationId === targetId) {
      syncChatStateFromConversation(detail);
      renderChatUi();
    } else {
      logDebugEvent("chat_detail_load_stale", {
        conversationId: targetId,
        activeConversationId: String(chatState.activeConversationId || ""),
        nonce: loadNonce,
      });
    }
    return detail;
  })().catch((error) => {
    logDebugEvent("chat_detail_load_error", {
      conversationId: targetId,
      activeConversationId: String(chatState.activeConversationId || ""),
      error: error?.message || String(error || ""),
      nonce: loadNonce,
    });
    throw error;
  }).finally(() => {
    if (chatConversationDetailLoadPromises.get(targetId) === loadPromise) {
      chatConversationDetailLoadPromises.delete(targetId);
    }
  });
  chatConversationDetailLoadPromises.set(targetId, loadPromise);
  return loadPromise;
}
function chatConversations() {
  return Array.isArray(chatState.conversations) ? chatState.conversations : [];
}
function activeChatConversation() {
  const rows = chatConversations();
  return (
    rows.find((conversation) => conversation.id === chatState.activeConversationId) ||
    rows[0] ||
    null
  );
}
function resetChatTranscriptWindow() {
  chatTranscriptVisibleTurns = CHAT_TRANSCRIPT_INITIAL_TURNS;
  chatTranscriptLastSignature = "";
  chatTranscriptLastHtml = "";
}
function expandChatTranscriptWindow() {
  chatTranscriptVisibleTurns += CHAT_TRANSCRIPT_EXPAND_STEP;
  renderChatTranscript(false);
}
function syncChatStateFromConversation(conversation) {
  const source =
    conversation && typeof conversation === "object"
      ? conversation
      : {
          presetId: "",
          apiPresetName: "",
          messages: [],
          attachments: [],
          params: cloneChatParams(),
          systemPrompt: "",
          autoCompactEnabled: true,
          autoCompactThresholdPct: CHAT_AUTO_COMPACT_THRESHOLD_DEFAULT,
          statsCollapsed: false,
          transcriptHeightPx: 0,
        };
  chatState.presetId = String(source.presetId || "");
  chatState.apiPresetName = String(source.apiPresetName || "");
  chatState.messages = cloneChatMessages(source.messages);
  chatState.attachments = Array.isArray(source.attachments)
    ? source.attachments.map(cloneChatAttachment)
    : [];
  chatState.params = cloneChatParams(source.params);
  chatState.systemPrompt = String(source.systemPrompt || "");
  chatState.autoCompactEnabled = source.autoCompactEnabled !== false;
  chatState.autoCompactThresholdPct = clampChatCompactionThreshold(
    source.autoCompactThresholdPct,
  );
  chatState.statsCollapsed = !!source.statsCollapsed;
  chatState.transcriptHeightPx = Number(source.transcriptHeightPx || 0) || 0;
}
function syncChatStateFromActiveConversation() {
  syncChatStateFromConversation(activeChatConversation());
}
function syncActiveConversationFromChatState() {
  const conversation = activeChatConversation();
  if (!conversation || conversation.messagesLoaded === false) return null;
  conversation.presetId = String(chatState.presetId || "");
  conversation.apiPresetName = String(chatState.apiPresetName || "");
  conversation.messages = cloneChatMessages(chatState.messages);
  conversation.attachments = Array.isArray(chatState.attachments)
    ? chatState.attachments.map(cloneChatAttachment)
    : [];
  conversation.params = cloneChatParams(chatState.params);
  conversation.systemPrompt = String(chatState.systemPrompt || "");
  conversation.autoCompactEnabled = chatState.autoCompactEnabled !== false;
  conversation.autoCompactThresholdPct = clampChatCompactionThreshold(
    chatState.autoCompactThresholdPct,
  );
  conversation.statsCollapsed = !!chatState.statsCollapsed;
  conversation.transcriptHeightPx = Number(chatState.transcriptHeightPx || 0) || 0;
  conversation.updatedAt = Date.now();
  conversation.lastUsedAt = conversation.updatedAt;
  return conversation;
}
function persistChatConversationState() {
  if (activeChatConversation()?.messagesLoaded === false) return;
  syncActiveConversationFromChatState();
  saveChatState();
}
function normalizeTabName(name) {
  if (name === "audit") return "logs";
  return ["overview", "system", "presets", "metrics", "users", "logs", "chat"].includes(
    name,
  )
    ? name
    : "overview";
}
function currentUiState() {
  return {
    active_tab: normalizeTabName(activeTabName),
    selected_scope: selectedScope || "GLOBAL",
    current_log_source:
      currentLogSource === "audit" ||
      currentLogSource === "docker" ||
      String(currentLogSource || "").startsWith("service:")
        ? currentLogSource
        : "docker",
    show_global_logs: !!showGlobalLogs,
  };
}
function queueUiStateSave(extra = {}) {
  const state = { ...currentUiState(), ...extra };
  const nextJson = JSON.stringify(state);
  if (nextJson === lastQueuedUiStateJson) return;
  lastQueuedUiStateJson = nextJson;
  writeCachedUiState(state);
  if (uiStateSaveTimer) clearTimeout(uiStateSaveTimer);
  uiStateSaveTimer = setTimeout(async () => {
    try {
      await fetch("/admin/ui-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: nextJson,
      });
    } catch (e) {}
  }, 120);
}
function activeTabButton(name) {
  if (name === "chat") return $("chatLaunchBtn") || null;
  return (
    [...document.querySelectorAll(".tab")].find(
      (btn) =>
        (btn.getAttribute("onclick") || "").includes(`'${name}'`) ||
        btn.id === `${name}TabBtn`,
      ) || null
  );
}
function syncHeaderChatButtonAlignment() {
  const button = $("chatLaunchBtn");
  const row = button && typeof button.closest === "function" ? button.closest(".header-row") : null;
  const logsButton = activeTabButton("logs");
  if (!button || !row || !logsButton) return;
  const rowRect = row.getBoundingClientRect();
  const logsRect = logsButton.getBoundingClientRect();
  const marginRight = Math.max(0, Math.round(rowRect.right - logsRect.right));
  button.style.marginRight = `${marginRight}px`;
}
function hydrateUiState(cfg) {
  if (uiStateHydrated) return;
  const cached = readCachedUiState(),
    state = { ...cached, ...(cfg || {}) };
  activeTabName = normalizeTabName(state.active_tab || activeTabName);
  currentLogSource =
    state.current_log_source === "audit" ||
    state.current_log_source === "docker" ||
    String(state.current_log_source || "").startsWith("service:")
      ? String(state.current_log_source)
      : "docker";
  showGlobalLogs =
    typeof state.show_global_logs === "boolean"
      ? state.show_global_logs
      : showGlobalLogs;
  const ids = new Set(scopeItems().map((x) => x.id));
  const candidate = state.selected_scope || selectedScope || "GLOBAL";
  selectedScope =
    candidate === "GLOBAL"
      ? "GLOBAL"
      : ids.has(candidate)
        ? candidate
        : singleScopeItems()[0]?.id || pairScopeItems()[0]?.id || "GLOBAL";
  if (selectedScope !== "GLOBAL") selectedInstance = selectedScope;
  lastQueuedUiStateJson = JSON.stringify(currentUiState());
  uiStateHydrated = true;
}
function ensureChatHydrationForActiveTab() {
  if (activeTabName !== "chat" || chatStateHydrated || chatStateHydratingPromise) return;
  (async () => {
    try {
      await hydrateChatState();
      renderChatUi();
      scheduleChatTranscriptHeightSync();
    } catch (error) {
      logDebugEvent("chat_hydrate_active_tab_error", {
        error: error?.message || String(error || ""),
      });
    }
  })();
}
legacyGlobalPair = function () {
  return (lastStatus && lastStatus.legacy_global_instance) || null;
};
let powerCoolingBusyState = { active: false, message: "" };
const STATUS_POLL_MS = 1000;
function syncPowerCoolingBusyState() {
  const panel = findPanelByHeading("system", "Optimizations + Cooling");
  if (!panel) return;
  panel.classList.toggle("instance-panel-busy", !!powerCoolingBusyState.active);
  [...panel.querySelectorAll("button,input,select,textarea")].forEach((el) => {
    if (powerCoolingBusyState.active) el.setAttribute("disabled", "disabled");
    else el.removeAttribute("disabled");
  });
}
function setPowerCoolingBusy(active, message = "") {
  powerCoolingBusyState = { active: !!active, message: message || "" };
  syncPowerCoolingBusyState();
}
async function withPowerCoolingBusy(message, fn) {
  setPowerCoolingBusy(true, message);
  try {
    return await fn();
  } finally {
    setPowerCoolingBusy(false);
  }
}
function redrawMetricsSoon() {
  if (!lastStatus) return;
  renderMetrics(lastStatus);
  requestAnimationFrame(() => {
    if (lastStatus) renderMetrics(lastStatus);
  });
}
function syncInstancesBusyState() {
  const panel = findPanelByHeading("system", "Instances");
  if (!panel) return;
  panel.classList.toggle("instance-panel-busy", !!instanceBusyState.active);
  [...panel.querySelectorAll("button,input,select,textarea")].forEach((el) => {
    if (instanceBusyState.active) el.setAttribute("disabled", "disabled");
    else if (el.id !== "gpuPairingEnabled" || gpuCount() >= 2)
      el.removeAttribute("disabled");
  });
  const note = $("pairingBusyNote");
  if (note) {
    const msg =
      instanceBusyState.message ||
      (gpuCount() === 2
        ? "Keep disabled if you want Global to keep behaving like the shared two-GPU runtime."
        : "Enable this to manage arbitrary dual-GPU pair groups.");
    note.innerHTML = instanceBusyState.active
      ? `<span class="spinner" aria-hidden="true"></span>${msg}`
      : msg;
  }
}
function setInstancesBusy(active, message = "") {
  instanceBusyState = { active: !!active, message: message || "" };
  syncInstancesBusyState();
}

async function saveGpuPairingSetting(enabled) {
  setInstancesBusy(true, "Applying GPU pairing setting...");
  try {
    const r = await fetch("/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "save_server_config",
        gpu_pairing_enabled: !!enabled,
      }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "GPU pairing update failed");
    if (j.server_config) {
      if (!lastStatus) lastStatus = {};
      lastStatus.server_config = j.server_config;
    }
    await refreshStatus();
    if (!enabled) setScope("GLOBAL", false);
  } catch (e) {
    alert("GPU pairing update failed: " + e);
  } finally {
    setInstancesBusy(false);
  }
}
ensureAccessPolicyCard = function () {
  const card = findPanelByHeading("system", "Access Policy");
  if (!card) return;
  if (card.dataset.v414Policy !== "1") {
    card.dataset.v414Policy = "1";
    card.innerHTML = `<h2>Access Policy</h2><div class="actions" id="accessPolicyRow"><label class="label"><input type="checkbox" id="auditAllowAnonymousProxy" onchange="mirrorAuthToggles(this.checked)"> allow requests without per-user API keys</label><button class="btn blue" onclick="saveAuthSettings()">Save Policy</button></div><div class="value smallgap" style="margin-top:10px" id="auditPolicyText">-</div>`;
  }
};
function ensureAuditOverviewCard() {
  const system = $("system");
  const overview =
    findPanelByHeading("logs", "Audit Overview") ||
    findPanelByHeading("audit", "Audit Overview") ||
    findPanelByHeading("system", "Audit Overview");
  if (system && overview) {
    const accessPolicy = findPanelByHeading("system", "Access Policy");
    if (accessPolicy) accessPolicy.insertAdjacentElement("afterend", overview);
    else system.insertBefore(overview, system.children[1] || null);
  }
}
ensureMachineButtons = function () {
  const systemCard = findPanelByHeading("system", "System");
  if (!systemCard) return;
  let utilityRow = $("systemUtilityRow");
  if (!utilityRow) {
    utilityRow = document.createElement("div");
    utilityRow.id = "systemUtilityRow";
    utilityRow.className = "actions";
    systemCard.insertBefore(
      utilityRow,
      systemCard.querySelector(".machine-row") || null,
    );
  }
  const machineRow = systemCard.querySelector(".machine-row");
  const buttonDefs = [
    {
      label: "Benchmark",
      className: "btn blue",
      action: "promptBenchmarkRun()",
    },
    {
      label: "Run Report",
      className: "btn blue",
      action: "promptReportRun()",
    },
    {
      label: "Update",
      className: "btn blue",
      action: "promptUpdateRun()",
    },
  ];
  buttonDefs.forEach((def) => {
    let button = [...systemCard.querySelectorAll("button")].find(
      (item) => (item.textContent || "").trim() === def.label,
    );
    if (!button) {
      button = document.createElement("button");
      button.textContent = def.label;
    }
    button.className = def.className;
    button.setAttribute("onclick", def.action);
    if (!utilityRow.contains(button)) utilityRow.appendChild(button);
    else utilityRow.appendChild(button);
  });
  [...utilityRow.querySelectorAll("button")].forEach((button) => {
    const label = (button.textContent || "").trim();
    if (!buttonDefs.some((def) => def.label === label)) button.remove();
  });
  if (machineRow) {
    let wolButton = [...systemCard.querySelectorAll("button")].find(
      (item) => (item.textContent || "").trim() === "Wake-on-LAN",
    );
    if (!wolButton) {
      wolButton = document.createElement("button");
      wolButton.textContent = "Wake-on-LAN";
    }
    wolButton.className = "btn amber";
    wolButton.setAttribute("onclick", "wol()");
    const firstMachineButton = machineRow.querySelector("button");
    if (firstMachineButton && firstMachineButton !== wolButton)
      machineRow.insertBefore(wolButton, firstMachineButton);
    else if (!machineRow.contains(wolButton)) machineRow.appendChild(wolButton);
  }
  [...systemCard.querySelectorAll(".actions")].forEach((actions) => {
    if (actions !== utilityRow && actions !== machineRow && !actions.querySelector("button")) {
      actions.remove();
    }
  });
};
allPairChoices = function () {
  const count = gpuCount(),
    pairs = [];
  for (let a = 0; a < count; a += 1) {
    for (let b = a + 1; b < count; b += 1) pairs.push([a, b]);
  }
  return pairs;
};
function ensurePairingToggle() {
  const panel = findPanelByHeading("system", "Instances");
  if (!panel) return;
  let row = $("pairingToggleRow");
  if (!row) {
    row = document.createElement("div");
    row.id = "pairingToggleRow";
    row.className = "actions";
    const tabs = $("instanceTabs");
    if (tabs && tabs.parentNode === panel)
      tabs.insertAdjacentElement("beforebegin", row);
  }
  const count = gpuCount();
  const enabled = pairingEnabled();
  const busy = !!instanceBusyState.active;
  const hint = busy
    ? instanceBusyState.message || "Applying GPU pairing setting..."
    : count === 2
      ? "Keep disabled if you want Global to keep behaving like the shared two-GPU runtime."
      : "Enable this to manage arbitrary dual-GPU pair groups.";
  row.innerHTML = `<label class="label"><input type="checkbox" id="gpuPairingEnabled" ${enabled ? "checked" : ""} ${count < 2 || busy ? "disabled" : ""} onchange="saveGpuPairingSetting(this.checked)"> Enable GPU Pairing</label><span class="label busy-note" id="pairingBusyNote">${busy ? `<span class="spinner" aria-hidden="true"></span>${hint}` : hint}</span>`;
}
ensurePairManager = function () {
  const panel = findPanelByHeading("system", "Instances");
  if (!panel) return;
  let bar = $("pairManagerBar");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "pairManagerBar";
    bar.className = "actions";
    const summary = $("instanceSummary");
    if (summary && summary.parentNode === panel)
      summary.insertAdjacentElement("afterend", bar);
  }
  if (!pairingEnabled() || gpuCount() < 2) {
    bar.innerHTML = "";
    return;
  }
  const pair = currentScopeInstance(true);
  const showDelete = !!pair && pair.kind === "dual";
  const existing = new Set(pairScopeItems().map((x) => x.id));
  const quickAdds = allPairChoices()
    .filter(([a, b]) => !existing.has(canonicalPairId(a, b)))
    .map(
      ([a, b]) =>
        `<button class="btn blue" onclick="createPairGroup(${a},${b})">Add Pair ${a}+${b}</button>`,
    )
    .join("");
  bar.style.margin = "8px 0 10px";
  bar.innerHTML = `${quickAdds || ""}<button class="btn purple" onclick="createPairGroup()">Custom Pair Group</button>${showDelete ? `<button class="btn red" onclick="deleteCurrentPairGroup()">Delete ${scopeLabel(pair)}</button>` : ""}`;
};
function ensureSystemServicesPanel() {
  const system = $("system");
  if (!system) return;
  let panel = $("systemServicesPanel");
  const legacyPanel = findPanelByHeading("system", "Services");
  if (!panel && legacyPanel) panel = legacyPanel;
  if (!panel) return;
  panel.id = "systemServicesPanel";
  panel.innerHTML = `<h2>Services</h2><div class="system-service-sections" id="services"><div class="service-section-card" id="serverServicesCard" data-collapsed="false"><div class="service-section-head"><div class="service-section-title">Server Services</div><button type="button" class="iconbtn service-section-toggle" id="serverServicesToggle" title="Collapse server services" aria-label="Collapse server services" aria-expanded="true" onclick="toggleSystemServiceSection('server')">${svgIcon("chevron-up")}</button></div><div class="service-section-body" id="serverServices">-</div></div><div class="service-section-card" id="club3090ServicesCard" data-collapsed="false"><div class="service-section-head"><div class="service-section-title">Club3090 Services</div><button type="button" class="iconbtn service-section-toggle" id="club3090ServicesToggle" title="Collapse Club3090 services" aria-label="Collapse Club3090 services" aria-expanded="true" onclick="toggleSystemServiceSection('club3090')">${svgIcon("chevron-up")}</button></div><div class="service-section-body" id="club3090Services">-</div></div></div><div class="msg" id="servicesMsg"></div>`;
  const instancesPanel = findPanelByHeading("system", "Instances");
  if (instancesPanel && panel.previousElementSibling !== instancesPanel) {
    instancesPanel.insertAdjacentElement("afterend", panel);
  }
  SYSTEM_SERVICE_SECTION_KEYS.forEach(applySystemServiceSectionState);
  if (lastStatus) renderSystemServices(lastStatus);
}
ensureV414Layout = function () {
  ensureV413Layout();
  ensureUsersUi();
  ensureGroupUi();
  ensureAccessPolicyCard();
  ensureAuditOverviewCard();
  ensureMachineButtons();
  ensureSystemServicesPanel();
  ensurePairingToggle();
  ensurePairManager();
  syncInstancesBusyState();
  syncPowerCoolingBusyState();
  ensureDynamicPresetLayout();
  ensurePresetActionModal();
};
const logCache = Object.create(null);
let statusRefreshPromise = null;
let pendingForcedStatusRefresh = false;
let logConnectToken = 0;
let logExportBusy = false;
const SYSTEM_SERVICE_SECTION_KEYS = ["server", "club3090"];
const systemServiceCollapseState = {
  server: false,
  club3090: false,
};
function systemServiceElements(section) {
  if (section === "server") {
    return {
      card: $("serverServicesCard"),
      body: $("serverServices"),
      toggle: $("serverServicesToggle"),
      title: "Server Services",
    };
  }
  if (section === "club3090") {
    return {
      card: $("club3090ServicesCard"),
      body: $("club3090Services"),
      toggle: $("club3090ServicesToggle"),
      title: "Club3090 Services",
    };
  }
  return null;
}
function applySystemServiceSectionState(section) {
  const elements = systemServiceElements(section);
  if (!elements?.card || !elements?.toggle) return;
  const collapsed = !!systemServiceCollapseState[section];
  elements.card.dataset.collapsed = collapsed ? "true" : "false";
  elements.toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  elements.toggle.setAttribute(
    "title",
    `${collapsed ? "Expand" : "Collapse"} ${elements.title.toLowerCase()}`,
  );
  elements.toggle.setAttribute(
    "aria-label",
    `${collapsed ? "Expand" : "Collapse"} ${elements.title.toLowerCase()}`,
  );
  elements.toggle.innerHTML = svgIcon(collapsed ? "chevron-right" : "chevron-up");
}
function toggleSystemServiceSection(section) {
  if (!Object.prototype.hasOwnProperty.call(systemServiceCollapseState, section)) return;
  systemServiceCollapseState[section] = !systemServiceCollapseState[section];
  applySystemServiceSectionState(section);
}
function renderSystemServiceSection(section, title, bodyHtml) {
  const elements = systemServiceElements(section) || {};
  const collapsed = !!systemServiceCollapseState[section];
  return `<div class="service-section-card" id="${section === "server" ? "serverServicesCard" : "club3090ServicesCard"}" data-collapsed="${collapsed ? "true" : "false"}"><div class="service-section-head"><div class="service-section-title">${escapeHtml(title)}</div><button type="button" class="iconbtn service-section-toggle" id="${section === "server" ? "serverServicesToggle" : "club3090ServicesToggle"}" title="${collapsed ? "Expand" : "Collapse"} ${escapeHtml(title.toLowerCase())}" aria-label="${collapsed ? "Expand" : "Collapse"} ${escapeHtml(title.toLowerCase())}" aria-expanded="${collapsed ? "false" : "true"}" onclick="toggleSystemServiceSection('${escapeJs(section)}')">${svgIcon(collapsed ? "chevron-right" : "chevron-up")}</button></div><div class="service-section-body" id="${section === "server" ? "serverServices" : "club3090Services"}">${bodyHtml}</div></div>`;
}
function renderServiceCards(rows = [], options = {}) {
  if (!rows.length) {
    return `<div class="value">${escapeHtml(options.emptyText || "No services available.")}</div>`;
  }
  const servicePrimaryAction = (row) =>
    row?.ready
      ? `<button class="btn amber" onclick="promptUpstreamServiceAction('${escapeJs(row.id)}','restart')">Restart</button>`
      : `<button class="btn green" onclick="promptUpstreamServiceAction('${escapeJs(row.id)}','start')">Start</button>`;
  const serviceStopAction = (row) =>
    row?.ready
      ? `<button class="btn red" onclick="promptUpstreamServiceAction('${escapeJs(row.id)}','stop')">Stop</button>`
      : "";
  return `<div class="api-grid">${rows
    .map(
      (row) =>
        `<div class="api-card"><div class="api-card-head"><h3>${escapeHtml(row.display_name)}</h3><span class="status-badge ${escapeHtml(row.stateClass)}">${escapeHtml(row.status)}</span></div><p>${escapeHtml(row.detail || "No details")}</p>${row.health_status ? `<p class="label">Status: ${escapeHtml(row.health_status)}</p>` : ""}${options.showActions && row.id ? `<div class="variant-actions"><button class="btn blue" onclick="openServiceLogSource('${escapeJs(row.id)}')">View Log</button>${servicePrimaryAction(row)}${serviceStopAction(row)}</div>` : ""}</div>`,
    )
    .join("")}</div>`;
}
function renderLogSourcePanel() {
  const panel = $("logSourcePanel");
  if (panel) {
    const services = Array.isArray(lastStatus?.upstream_services)
      ? lastStatus.upstream_services.filter((row) => row && row.running)
      : [];
    panel.innerHTML = `<div class="panel-head"><h2>Log Sources</h2><div class="preset-actions">${renderIconButton({ title: "Export", action: "exportCurrentLog()", icon: "upload" })}</div></div><div class="subtabs">${[
      { id: "docker", label: "Docker" },
      { id: "audit", label: "Audit" },
      ...services.map((row) => ({
        id: `service:${String(row.id || "")}`,
        label: String(row.display_name || row.id || "Service"),
      })),
    ]
      .map(
        (row) =>
          `<button class="subtab${currentLogSource === row.id ? " active" : ""}" onclick="setCurrentLogSource('${escapeJs(row.id)}')">${escapeHtml(row.label)}</button>`,
      )
      .join("")}</div><div class="value smallgap" id="logsSourceSummary">-</div>`;
  }
  if (!$("logsSourceSummary")) return;
  if (currentLogSource === "audit") {
    $("logsSourceSummary").innerHTML =
      "Audit selected. The live viewer follows <code>/opt/club3090-control/audit.log</code>.";
    return;
  }
  if (String(currentLogSource || "").startsWith("service:")) {
    const serviceId = String(currentLogSource).split(":", 2)[1] || "";
    const service = (lastStatus?.upstream_services || []).find(
      (row) => String(row?.id || "") === serviceId,
    );
    $("logsSourceSummary").innerHTML = service
      ? `${escapeHtml(service.display_name || service.id)} selected. The live viewer follows container <code>${escapeHtml(service.container_name || service.service_name || service.id)}</code>.`
      : "Service log source selected.";
    return;
  }
  $("logsSourceSummary").innerHTML =
    scopeIsGlobal() && legacyGlobalDualScope()
      ? "Docker selected. The live viewer follows the active global dual runtime."
      : "Docker selected. The live viewer follows the currently selected tracked instance.";
}
currentLogHeading = function () {
  if (currentLogSource === "audit") return "Audit";
  if (String(currentLogSource || "").startsWith("service:")) {
    const serviceId = String(currentLogSource).split(":", 2)[1] || "";
    const service = (lastStatus?.upstream_services || []).find(
      (row) => String(row?.id || "") === serviceId,
    );
    return String(service?.display_name || serviceId || "Service");
  }
  return "Docker";
};
currentLogLabel = function () {
  if (currentLogSource === "audit") return "source: audit";
  if (String(currentLogSource || "").startsWith("service:")) {
    const serviceId = String(currentLogSource).split(":", 2)[1] || "";
    const service = (lastStatus?.upstream_services || []).find(
      (row) => String(row?.id || "") === serviceId,
    );
    return `source: ${service?.display_name || serviceId || "service"}`;
  }
  const explicit = String(selectedLogInstanceId || "").trim().toUpperCase();
  if (explicit) return "instance: " + explicit;
  const tracked = trackedLogRuntime();
  if (tracked) return "instance: " + (tracked.id || tracked.instance_id || "primary");
  if (scopeIsGlobal() && legacyGlobalDualScope())
    return "instance: Global dual";
  const cur = dockerLogTarget();
  return "instance: " + ((cur && cur.id) || "primary");
};
function trimLogText(text) {
  const value = String(text || "");
  return value.length > 900000 ? value.slice(-750000) : value;
}
function logIsNearBottom(box = $("log")) {
  if (!box) return true;
  return box.scrollHeight - (box.scrollTop + box.clientHeight) <= 28;
}
function scrollLogToBottom(box = $("log")) {
  if (!box) return;
  box.scrollTop = box.scrollHeight;
}
function logCacheEntry(signature) {
  if (!logCache[signature]) logCache[signature] = { text: "", loaded: false };
  return logCache[signature];
}
function renderCurrentLog(signature, options = {}) {
  const box = $("log");
  if (!box) return;
  const entry = logCacheEntry(signature);
  const nextValue = entry.loaded ? collapseRepeatedLogText(entry.text) : "Connecting...\n";
  const changed = box.value !== nextValue;
  if (changed) box.value = nextValue;
  if (searchState.active) {
    if (changed) recalculateMatches(true);
  } else if (changed && options.follow && $("autoscroll") && $("autoscroll").checked) {
    scrollLogToBottom(box);
  }
  flushPendingLogJump();
}
function collapseRepeatedLogText(text) {
  const source = String(text || "");
  if (!source) return "";
  const hasTrailingNewline = source.endsWith("\n");
  const lines = source.split("\n");
  if (hasTrailingNewline) lines.pop();
  const collapsed = [];
  for (const line of lines) {
    const previous = collapsed[collapsed.length - 1];
    if (previous && previous.raw === line) previous.count += 1;
    else collapsed.push({ raw: line, count: 1 });
  }
  const rendered = collapsed.map((entry) =>
    entry.count > 1 ? `${entry.raw} (${entry.count})` : entry.raw,
  );
  return rendered.join("\n") + (hasTrailingNewline ? "\n" : "");
}
function replaceLogBuffer(signature, text) {
  const entry = logCacheEntry(signature);
  const box = signature === currentLogSignature ? $("log") : null;
  const shouldFollow =
    !!box &&
    !!$("autoscroll")?.checked &&
    (!entry.loaded || box.value === "Connecting...\n" || logIsNearBottom(box));
  entry.text = trimLogText(text || "");
  entry.loaded = true;
  if (signature === currentLogSignature) renderCurrentLog(signature, { follow: shouldFollow });
}
function appendLogChunk(signature, text) {
  if (!text) return;
  const entry = logCacheEntry(signature);
  const box = signature === currentLogSignature ? $("log") : null;
  const shouldFollow = !!box && !!$("autoscroll")?.checked && logIsNearBottom(box);
  entry.text = trimLogText((entry.text || "") + text);
  entry.loaded = true;
  if (signature === currentLogSignature) renderCurrentLog(signature, { follow: shouldFollow });
}
function syntheticLog(message) {
  appendLog(`[admin-ui ${new Date().toLocaleTimeString()}] ${message}`);
}
function adminResultText(payload, rawText) {
  let text = "";
  if (payload && typeof payload === "object") {
    try {
      text = JSON.stringify(payload, null, 2);
    } catch (e) {
      text = "";
    }
  }
  if (!text) text = String(rawText || "").trim();
  if (text.length > 5000) text = text.slice(0, 5000) + "\n...<truncated>...";
  return text;
}
applyLogVisibility = function () {
  const isLogs = activeTabName === "logs";
  document.body.classList.toggle("logs-tab", isLogs);
  document.body.classList.remove("audit-tab");
  const card = document.querySelector(".logs.panel");
  if (card)
    card.classList.toggle("log-card-hidden", !isLogs && !showGlobalLogs);
  if ($("logTitle")) $("logTitle").textContent = currentLogHeading();
  if ($("logInstanceLabel"))
    $("logInstanceLabel").textContent = currentLogLabel();
  renderLogSourcePanel();
  renderLogTracker();
  if (currentLogSignature) renderCurrentLog(currentLogSignature);
};
function logStreamConfig() {
  if (currentLogSource === "audit")
    return { signature: "audit", url: "/admin/audit-stream?tail=4000" };
  if (String(currentLogSource || "").startsWith("service:")) {
    const serviceId = String(currentLogSource).split(":", 2)[1] || "";
    return {
      signature: `service:${serviceId}`,
      url: `/admin/logs?source=service&service=${encodeURIComponent(serviceId)}`,
    };
  }
  const tracked = trackedLogRuntime();
  const target = tracked || dockerLogTarget();
  const explicit = String(selectedLogInstanceId || "").trim().toUpperCase();
  const instanceId = explicit
    ? explicit
    : tracked && (tracked.id || tracked.instance_id)
      ? tracked.id || tracked.instance_id
      : scopeIsGlobal() && legacyGlobalDualScope()
        ? "GLOBAL"
        : target && target.id;
  return {
    signature: `docker:${instanceId || "primary"}`,
    url: `/admin/logs${instanceId ? `?instance=${encodeURIComponent(instanceId)}` : ""}`,
  };
}
function currentLogExportRequest() {
  if (currentLogSource === "audit") {
    return { source: "audit", instance_id: null };
  }
  if (String(currentLogSource || "").startsWith("service:")) {
    return { source: String(currentLogSource), instance_id: null };
  }
  if (currentLogSignature && currentLogSignature.startsWith("docker:")) {
    const fromSignature = currentLogSignature.slice("docker:".length);
    if (fromSignature && fromSignature !== "primary") {
      return { source: "docker", instance_id: fromSignature };
    }
  }
  const explicit = String(selectedLogInstanceId || "").trim().toUpperCase();
  if (explicit) return { source: "docker", instance_id: explicit };
  const tracked = trackedLogRuntime();
  const target = tracked || dockerLogTarget();
  const instanceId =
    tracked && (tracked.id || tracked.instance_id)
      ? tracked.id || tracked.instance_id
      : scopeIsGlobal() && legacyGlobalDualScope()
        ? "GLOBAL"
        : target && target.id;
  return { source: "docker", instance_id: instanceId || null };
}
async function exportCurrentLog() {
  if (logExportBusy) return;
  logExportBusy = true;
  try {
    const req = currentLogExportRequest();
    const payload = await post(
      "/admin/log-export",
      req,
      `/admin/log-export ${req.source} ${req.instance_id || "host"}`,
    );
    openApiKeyModal(
      "Log Export Link",
      payload.url || "",
      "Share this link directly for debugging. It points to the currently selected log export.",
      {
        copySuccessText: "Copied exported log URL to the clipboard.",
        showTopClose: false,
      },
    );
  } catch (e) {
    alert(e);
  } finally {
    logExportBusy = false;
  }
}
async function shareActiveConversation() {
  const conversation = activeChatConversation();
  if (!conversation) return;
  try {
    const payload = await post(
      "/admin/chat-export",
      { conversation_id: conversation.id },
      `/admin/chat-export ${conversation.id}`,
    );
    openApiKeyModal(
      "Shared Chat Link",
      payload.url || "",
      "Share this link directly. It points to the exported Markdown conversation.",
      {
        copySuccessText: "Copied shared chat URL to the clipboard.",
        showTopClose: false,
      },
    );
  } catch (e) {
    alert(e);
  }
}
connectLogs = function (force = false) {
  const visible = activeTabName === "logs" || showGlobalLogs;
  if (!visible && !force) return;
  const cfg = logStreamConfig();
  if (!force && logEs && cfg.signature === currentLogSignature) {
    renderCurrentLog(cfg.signature);
    return;
  }
  currentLogSignature = cfg.signature;
  renderCurrentLog(cfg.signature, { follow: !!$("autoscroll")?.checked });
  const token = ++logConnectToken;
  if (logEs) {
    try {
      logEs.close();
    } catch (e) {}
    logEs = null;
  }
  const es = new EventSource(cfg.url);
  logEs = es;
  const handle = (mode, data) => {
    let payload = null;
    try {
      payload = JSON.parse(data || "{}");
    } catch (e) {}
    const text =
      payload && typeof payload.text === "string"
        ? payload.text
        : String(data || "").replaceAll("\\u0000", "\n");
    if (mode === "reset") replaceLogBuffer(cfg.signature, text);
    else appendLogChunk(cfg.signature, text);
    flushPendingLogJump();
  };
  es.addEventListener("reset", (e) => {
    if (token !== logConnectToken) return;
    handle("reset", e.data);
  });
  es.addEventListener("append", (e) => {
    if (token !== logConnectToken) return;
    handle("append", e.data);
  });
  es.onmessage = (e) => {
    if (token !== logConnectToken) return;
    handle("append", e.data);
  };
  es.onerror = () => {
    if (token !== logConnectToken) return;
  };
};
setCurrentLogSource = function (source) {
  currentLogSource =
    source === "audit" || source === "docker" || String(source || "").startsWith("service:")
      ? String(source)
      : "docker";
  applyLogVisibility();
  queueUiStateSave({ current_log_source: currentLogSource });
  connectLogs(true);
};
setShowGlobalLogs = function (v) {
  showGlobalLogs = !!v;
  applyLogVisibility();
  queueUiStateSave({ show_global_logs: showGlobalLogs });
  connectLogs(false);
};
setScope = function (scope, reconnect = true) {
  const ids = new Set(scopeItems().map((x) => x.id));
  selectedScope =
    scope === "GLOBAL"
      ? "GLOBAL"
      : ids.has(scope)
        ? scope
        : singleScopeItems()[0]?.id || pairScopeItems()[0]?.id || "GLOBAL";
  if (selectedScope !== "GLOBAL") selectedInstance = selectedScope;
  renderInstances(getInstanceList());
  renderPresetScopeTabs();
  renderDynamicPresetModels();
  updateScopedCards();
  applyLogVisibility();
  queueUiStateSave();
  if (reconnect) connectLogs(true);
};
function focusAuditLogs() {
  if (currentLogSource !== "audit") setCurrentLogSource("audit");
  activateTab("logs", true);
}
function clearActiveLogJump() {
  pendingLogJump = null;
}
function flushPendingLogJump() {
  if (!pendingLogJump || !$("log")) return;
  const cfg = logStreamConfig();
  if (pendingLogJump.signature && pendingLogJump.signature !== cfg.signature) return;
  if (pendingLogJump.source === "audit" && currentLogSource !== "audit") return;
  if (pendingLogJump.query) {
    const box = $("log");
    if (!box.value || !box.value.toLowerCase().includes(pendingLogJump.query.toLowerCase()))
      return;
    if (!searchState.active || $("searchQuery").value !== pendingLogJump.query) {
      $("searchQuery").value = pendingLogJump.query;
      runSearchOrNext();
    } else if (searchState.matches.length) {
      gotoMatch(searchState.index >= 0 ? searchState.index : 0);
    }
  } else if ($("autoscroll").checked) {
    $("log").scrollTop = $("log").scrollHeight;
  }
  pendingLogJump = null;
}
function chooseVariantLogInstanceId(target, selector = "") {
  const targetId = String(target?.id || "").trim().toUpperCase();
  if (targetId && targetId !== "GLOBAL") return targetId;
  if (targetId === "GLOBAL" && legacyGlobalDualScope()) return "GLOBAL";
  const scopeKind = String(target?.kind || "");
  if (scopeKind === "dual") {
    const pairs = pairScopeItems().filter(
      (row) => !selector || String(row?.mode || "") === String(selector),
    );
    return String((pairs[0] && pairs[0].id) || "");
  }
  if (scopeKind === "global") {
    const runtime = runtimeStatsRows(lastStatus).find(
      (row) => !selector || String(row?.mode || "") === String(selector),
    );
    return String((runtime && (runtime.id || runtime.instance_id)) || "");
  }
  const singles = singleScopeItems().filter(
    (row) => !selector || String(row?.mode || "") === String(selector),
  );
  return String((singles[0] && singles[0].id) || "");
}
function openRuntimeLogsAtPoint(instanceId = "", query = "") {
  clearActiveLogJump();
  if (searchState.active) cancelSearch();
  if (currentLogSource !== "docker") setCurrentLogSource("docker");
  if (instanceId) selectedLogInstanceId = String(instanceId).trim().toUpperCase();
  activateTab("logs", true);
  $("autoscroll").checked = !query;
  pendingLogJump = {
    source: "docker",
    signature: `docker:${instanceId || "primary"}`,
    query: String(query || "").trim(),
  };
  connectLogs(true);
  setTimeout(() => flushPendingLogJump(), 60);
}
function bestFailureLogQuery(failure) {
  const lines = String(failure?.error || "")
    .replace(/\r/g, "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i];
    if (
      !/^timed out waiting/i.test(line) &&
      !/^container .* stopped during boot/i.test(line) &&
      !/^no docker logs/i.test(line)
    ) {
      return line;
    }
  }
  return lines[0] || "";
}
post = async function (path, obj, label = "") {
  const requestLabel = label || `${path} ${JSON.stringify(obj || {})}`;
  syntheticLog(`request sent: ${requestLabel}`);
  try {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(obj || {}),
    });
    const text = await r.text();
    let payload = null;
    try {
      payload = JSON.parse(text);
    } catch (e) {}
    if (!r.ok || (payload && payload.ok === false))
      throw new Error((payload && payload.error) || text || `${path} failed`);
    syntheticLog(`request finished: ${requestLabel}`);
    appendLog(
      `----- admin result -----\n${adminResultText(payload, text)}\n------------------------`,
    );
    if (payload && payload.focus_log_source === "audit") focusAuditLogs();
    refreshStatus().catch(() => {});
    return payload || text;
  } catch (e) {
    syntheticLog(`request failed: ${requestLabel} | ${e.message || e}`);
    appendLog(
      `----- admin error -----\n${e.message || e}\n-----------------------`,
    );
    refreshStatus().catch(() => {});
    throw e;
  }
};
function renderEnhancedGpuMetricCharts(j) {
  const holder = $("gpuMetricCharts");
  if (!holder || !j.gpus) return;
  const series = j.series || [];
  const charts = [
    { key: "util", suffix: "Util", label: "util %", color: "#72c7ff" },
    { key: "mem_pct", suffix: "Mem", label: "VRAM %", color: "#2fc46b" },
    {
      key: "temp",
      suffix: "Temp",
      label: "core temp \u00B0C",
      color: "#ffde59",
      showPeakLine: true,
      peakColor: "#b7c0cc",
      showPeakValue: true,
      valueColor: (current) => tempColorForValue(current),
      valueFormatterParts: (current, peak) => [
        { text: `${formatChartValue(current, 1)}°C`, color: tempColorForValue(current) },
        { text: " " },
        { text: `(↑ ${formatChartValue(peak, 1)}°C)`, color: tempColorForValue(peak) },
      ],
    },
    { key: "fan", suffix: "Fan", label: "fan %", color: "#a855f7" },
    {
      key: "power",
      suffix: "Power",
      label: "power W",
      color: "#ff5b6c",
      showPeakLine: true,
      peakColor: "#b7c0cc",
      showPeakValue: true,
    },
  ];
  holder.innerHTML = charts
    .map((cat) =>
      j.gpus
        .map(
          (g) =>
            `<div class="chart"><canvas id="cGpu${g.index}${cat.suffix}"></canvas></div>`,
        )
        .join(""),
    )
    .join("");
  charts.forEach((cat) =>
    j.gpus.forEach((g) =>
      drawGpuSeries(
        `cGpu${g.index}${cat.suffix}`,
        series,
        g.index,
        cat.key,
        `GPU${g.index} ${cat.label}`,
        cat.color,
        cat,
      ),
    ),
  );
}
metricTab = function (e, n) {
  document
    .querySelectorAll(".metricpane")
    .forEach((x) => x.classList.remove("active"));
  document
    .querySelectorAll(".subtab")
    .forEach((x) => x.classList.remove("active"));
  const pane = $(n);
  if (pane) pane.classList.add("active");
  if (e && e.target) e.target.classList.add("active");
  redrawMetricsSoon();
  refreshStatus().catch(() => {});
};
togglePowerOptimizations = async function () {
  const enable =
    $("optToggle") && $("optToggle").textContent.includes("Enable");
  const instanceId = scopeIsGlobal()
    ? "GLOBAL"
    : (currentScopeInstance(false) && currentScopeInstance(false).id) || null;
  try {
    await withPowerCoolingBusy(
      enable
        ? "Applying power optimizations..."
        : "Disabling power optimizations...",
      () =>
        post(
          "/admin/power",
          {
            action: enable ? "enable_optimizations" : "disable_optimizations",
            instance_id: instanceId,
          },
          `/admin/power ${enable ? "enable_optimizations" : "disable_optimizations"}`,
        ),
    );
  } catch (e) {
    alert(e);
  }
};
toggleFansMax = async function () {
  const reset = $("fanToggle") && $("fanToggle").textContent.includes("Reset");
  const cur = currentScopeInstance(false);
  const instanceId = scopeIsGlobal() ? "GLOBAL" : (cur && cur.id) || null;
  try {
    await withPowerCoolingBusy(
      reset ? "Resetting fans to default..." : "Setting fans to max...",
      () =>
        post(
          "/admin/power",
          { action: reset ? "fans_auto" : "fans_max", instance_id: instanceId },
          `/admin/power ${reset ? "fans_auto" : "fans_max"} ${instanceId || "host"}`,
        ),
    );
  } catch (e) {
    alert(e);
  }
};
async function wol() {
  const mac = prompt(
    "MAC address to wake (blank = configured default):",
    "",
  );
  if (mac === null) return;
  try {
    await post("/admin/wol", { mac });
  } catch (e) {
    alert(e);
  }
}
async function machineAction(action) {
  const label = action === "reboot" ? "RESTART" : "SHUT DOWN";
  if (!confirm(label + " machine now?")) return;
  if (!confirm("Final confirmation: " + label + " now.")) return;
  try {
    await post("/admin/machine", { action });
  } catch (e) {
    alert(e);
  }
}
function syncActiveTabDisplay() {
  document
    .querySelectorAll(".tabpane")
    .forEach((x) => x.classList.remove("active"));
  document
    .querySelectorAll(".tab")
    .forEach((x) => x.classList.remove("active"));
  if ($("chatLaunchBtn")) $("chatLaunchBtn").classList.remove("active");
  const pane = $(activeTabName);
  if (pane) pane.classList.add("active");
  const btn = activeTabButton(activeTabName);
  if (btn) btn.classList.add("active");
  applyLogVisibility();
}
function activateTab(name, firstRender = false) {
  activeTabName = normalizeTabName(name);
  logDebugEvent("tab_activate", { name: activeTabName, firstRender: !!firstRender });
  syncActiveTabDisplay();
  if (activeTabName === "logs" || showGlobalLogs || firstRender)
    connectLogs(false);
  if (activeTabName === "metrics") redrawMetricsSoon();
  if (activeTabName === "chat") {
    hydrateChatState()
      .then(() => {
        renderChatUi();
        scheduleChatTranscriptHeightSync();
      })
      .catch(() => {});
    renderChatUi();
    scheduleChatTranscriptHeightSync();
  }
  refreshStatus({ force: true }).catch(() => {});
  queueUiStateSave();
  setTimeout(() => {
    if (!searchState.active && $("autoscroll").checked && $("log"))
      $("log").scrollTop = $("log").scrollHeight;
  }, 0);
}
tab = function (e, n) {
  activateTab(n, false);
};
refreshStatus = async function (opts = {}) {
  const force = !!(opts && opts.force);
  if (adminAuthRefreshBlocked && !force) return lastStatus;
  if (statusRefreshPromise) {
    if (force) pendingForcedStatusRefresh = true;
    return statusRefreshPromise;
  }
  statusRefreshPromise = (async () => {
    try {
      ensureV414Layout();
      const suffix = force ? `?force=1&_=${Date.now()}` : "";
      const r = await fetchJsonWithTimeout(`/admin/status${suffix}`, { cache: "no-store" }, 12000);
      if (r.status === 401) {
        adminAuthRefreshBlocked = true;
        setMsg("Authentication expired. Reloading the admin panel...");
        setTimeout(() => {
          window.location.href = "/admin";
        }, 400);
        return lastStatus;
      }
      if (!r.ok) throw new Error(`status fetch failed (${r.status})`);
      const j = await r.json();
      adminAuthRefreshBlocked = false;
      const metrics = j.metrics || {},
        power = j.power || {};
      const previousStatus = lastStatus;
      lastStatus = j;
      syncPresetSummaryCacheFromStatus(j);
      hydrateUiState(j.ui_config || {});
      ensureChatHydrationForActiveTab();
      hydrateSelectedPresetModel();
      if ($("showGlobalLogs")) $("showGlobalLogs").checked = !!showGlobalLogs;
      const renderErrors = [];
      safeRenderStep("overview", () => renderOverviewStatus(j), renderErrors);
      safeRenderStep("gpu", () => renderGpuCards(j.gpus), renderErrors);
      safeRenderStep("services", () => renderSystemServices(j), renderErrors);
      safeRenderStep("power controls", () => {
        if ($("optToggle"))
          $("optToggle").textContent = power.optimizations_enabled
            ? "Disable Power Optimizations"
            : "Enable Power Optimizations";
        if ($("fanToggle"))
          $("fanToggle").textContent = power.fan_manual_override
            ? "Reset Fans to Default"
            : "Set Fans to Max";
      }, renderErrors);
      safeRenderStep("metrics", () => renderMetrics(j), renderErrors);
      safeRenderStep("presets", () => renderPresetCatalog(j.presets), renderErrors);
      safeRenderStep("users", () => renderUsers(j.users || []), renderErrors);
      safeRenderStep("groups", () => renderGroups(j.groups || []), renderErrors);
      safeRenderStep("audit", () => renderAudit(j.server_config || {}), renderErrors);
      safeRenderStep("instances", () => renderInstances(j.instances || []), renderErrors);
      safeRenderStep("preset scopes", () => renderPresetScopeTabs(), renderErrors);
      safeRenderStep("scoped cards", () => updateScopedCards(), renderErrors);
      safeRenderStep("model install status", () => renderModelInstallStatus(), renderErrors);
      safeRenderStep("dynamic preset models", () => renderDynamicPresetModels(), renderErrors);
      safeRenderStep("chat", () => renderChatUi(), renderErrors);
      safeRenderStep("tab sync", () => syncActiveTabDisplay(), renderErrors);
      if (activeTabName === "logs" || showGlobalLogs) connectLogs(false);
      handleSwitchJobTransition(previousStatus, j);
      const statusWarnings = [];
      if (j.status_error) statusWarnings.push(`Status probe fallback: ${j.status_error}`);
      if (renderErrors.length) statusWarnings.push(`Partial UI render: ${renderErrors.join(" | ")}`);
      setMsg(joinMessageParts(statusWarnings));
    } catch (e) {
      setMsg(`Status error: ${messageText(e)}`);
    } finally {
      statusRefreshPromise = null;
      if (pendingForcedStatusRefresh) {
        pendingForcedStatusRefresh = false;
        refreshStatus({ force: true }).catch(() => {});
      }
    }
  })();
  return statusRefreshPromise;
};
function clearLegacyPollers() {
  const marker = window.setInterval(() => {}, 60000);
  window.clearInterval(marker);
  for (let id = 1; id < marker; id += 1) window.clearInterval(id);
}
async function bootAdminUi() {
  clearLegacyPollers();
  ensureV414Layout();
  hydratePresetSummaryCache();
  resetUserForm(true);
  resetGroupForm(true);
  if (!selectedScope)
    selectedScope =
      singleScopeItems()[0]?.id || pairScopeItems()[0]?.id || "GLOBAL";
  setScope(selectedScope, false);
  refreshStatus().catch(() => {});
  if (statusPollTimer) clearInterval(statusPollTimer);
  statusPollTimer = setInterval(() => {
    refreshStatus();
  }, STATUS_POLL_MS);
  syncHeaderChatButtonAlignment();
  window.addEventListener("resize", syncHeaderChatButtonAlignment);
  window.addEventListener("beforeunload", () => {
    if (logEs) {
      try {
        logEs.close();
      } catch (e) {}
    }
  });
}
bootAdminUi().catch((e) => {
  setMsg("Boot error: " + e);
});
function runtimeInventory() {
  return (lastStatus && lastStatus.runtime_inventory) || { models: [], variants: [] };
}
function inventoryModels() {
  return (lastStatus && lastStatus.models) || runtimeInventory().models || [];
}
function inventoryVariants() {
  return (lastStatus && lastStatus.variants) || runtimeInventory().variants || [];
}
function saveSelectedPresetModel(modelId = "") {
  const next = String(modelId || "").trim();
  selectedPresetModelId = next;
  if (!lastStatus) lastStatus = {};
  lastStatus.server_config = {
    ...(lastStatus.server_config || {}),
    selected_preset_model: next,
  };
  fetch("/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "save_server_config",
      selected_preset_model: next,
    }),
  })
    .then((r) => r.json())
    .then((j) => {
      if (j && j.ok && j.server_config) {
        if (!lastStatus) lastStatus = {};
        lastStatus.server_config = j.server_config;
      }
    })
    .catch(() => {});
}
function hydrateSelectedPresetModel() {
  const models = inventoryModels();
  const valid = new Set(models.map((model) => String(model.model_id || "")));
  const configured = String(lastStatus?.server_config?.selected_preset_model || "").trim();
  if (!selectedPresetModelHydrated) {
    selectedPresetModelId = valid.has(configured) ? configured : "";
    selectedPresetModelHydrated = true;
    return;
  }
  if (selectedPresetModelId && valid.has(selectedPresetModelId)) return;
  selectedPresetModelId = valid.has(configured) ? configured : "";
}
function selectPresetModel(modelId = "") {
  selectedPresetModelId = String(modelId || "").trim();
  selectedPresetModelHydrated = true;
  renderPresetModelSelector();
  renderDynamicPresetModels();
  saveSelectedPresetModel(selectedPresetModelId);
}
function renderPresetModelSelector() {
  const host = $("presetModelSelector");
  if (!host) return;
  const models = inventoryModels();
  if (!models.length) {
    host.innerHTML = "";
    host.classList.add("hidden");
    return;
  }
  host.classList.remove("hidden");
  host.innerHTML = `<button class="subtab ${!selectedPresetModelId ? "active" : ""}" onclick="selectPresetModel('')">Summary</button>${models
    .map((model) => {
      const modelId = String(model.model_id || "");
      return `<button class="subtab ${modelId === selectedPresetModelId ? "active" : ""}" onclick="selectPresetModel('${escapeJs(modelId)}')">${escapeHtml(model.display_name || modelId)}</button>`;
    })
    .join("")}`;
}
function variantSelector(variant) {
  return (variant && (variant.upstream_tag || variant.variant_id)) || "";
}
function variantMapBySelector() {
  const map = new Map();
  inventoryVariants().forEach((variant) => {
    const selector = variantSelector(variant);
    if (selector) map.set(selector, variant);
  });
  return map;
}
function escapeJs(value) {
  return String(value || "")
    .replaceAll("\\", "\\\\")
    .replaceAll("'", "\\'");
}
function prettyEngineName(engine) {
  return engine === "llamacpp" ? "llama.cpp" : String(engine || "");
}
function variantDisplayLabel(variant) {
  if (variant && variant.upstream_tag) return variant.upstream_tag;
  const bits = String(variant?.compose_rel_path || "").split("/");
  const raw = (bits[bits.length - 1] || "").replace(/\.yml$/i, "");
  const stem = raw === "docker-compose" ? "default" : raw || "preset";
  return `${variant?.topology || "global"}/${stem}`;
}
function variantMaxCtx(variant) {
  const value = Number(variant?.max_model_len || 0);
  if (!Number.isFinite(value) || value <= 0) return "n/a";
  if (value >= 1000) return `${Math.round(value / 1000)}K`;
  return String(value);
}
function badgeClass(prefix, value) {
  return `${prefix}-${String(value || "unknown").replaceAll(" ", "_").replaceAll("/", "_")}`;
}
function smToRank(value) {
  const raw = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/^sm_/, "")
    .replace(/\+$/, "");
  if (!raw) return 0;
  const parts = raw.split(".", 2);
  const major = String(parts[0] || "").replace(/[^0-9]/g, "");
  let minor = String(parts[1] || "0").replace(/[^0-9]/g, "");
  if (!major) return 0;
  if (!minor) minor = "0";
  if (minor.length === 1) minor += "0";
  return Number(major) * 100 + Number(minor.slice(0, 2));
}
function rigNvlinkInfo() {
  return lastStatus?.nvlink || {};
}
function rigHasNvlink() {
  return !!rigNvlinkInfo().present;
}
function variantNvlinkMode(variant) {
  return String(variant?.nvlink_mode || "").trim().toLowerCase();
}
function variantCapabilityBadges(variant) {
  const bits = [];
  const nvlinkMode = variantNvlinkMode(variant);
  if (nvlinkMode === "required") {
    bits.push('<span class="status-badge status-nvlink">NVLink</span>');
  } else if (nvlinkMode === "capable" && rigHasNvlink()) {
    bits.push('<span class="status-badge status-nvlink_capable">NVLink-capable</span>');
  }
  return bits.join("");
}
function installStateLabel(variant) {
  const state = String(variant?.install_state || "unknown");
  if (state === "ready") return "ready";
  if (state === "requires_download") return "needs download";
  if (state === "unavailable") return "unavailable";
  return state;
}
function statusLabel(variant) {
  const kind = String(variant?.status_kind || "unknown");
  if (kind === "production") return "production";
  if (kind === "production_caveat") return "production + caveats";
  if (kind === "preview") return "preview";
  if (kind === "upstream_gated") return "upstream gated";
  if (kind === "blocked") return "hardware blocked";
  if (kind === "tombstoned") return "tombstoned";
  if (kind === "deprecated") return "deprecated";
  if (kind === "experimental") return "experimental";
  return "unknown";
}
function variantHardwareSummary(variant) {
  const minVram = Number(variant?.requires_min_vram_gb || 0);
  const minGpuCount = Number(variant?.requires_min_gpu_count || 0);
  const requiresSm = String(variant?.requires_sm || "").trim();
  const engineProfile = String(variant?.engine_profile || "").trim();
  const nvlinkMode = variantNvlinkMode(variant);
  const parts = [];
  if (minVram > 0) {
    parts.push(
      minGpuCount > 1 ? `${minGpuCount}x ${minVram} GB minimum` : `${minVram} GB minimum`,
    );
  } else if (minGpuCount > 1) {
    parts.push(`${minGpuCount} GPU minimum`);
  }
  if (requiresSm) parts.push(`sm_${requiresSm.replace(/\+$/, "")}+`);
  if (engineProfile) parts.push(engineProfile);
  if (nvlinkMode === "required") parts.push("NVLink required");
  else if (nvlinkMode === "capable" && rigHasNvlink()) parts.push("NVLink-capable");
  return parts.join(" | ");
}
function renderSystemServices(status) {
  const host = $("services");
  const serverHost = $("serverServices");
  const clubHost = $("club3090Services");
  if (!host || !serverHost || !clubHost) return;
  const rows = Array.isArray(status?.upstream_services) ? status.upstream_services : [];
  const proxyStatusRaw =
    status?.caddy_service && String(status.caddy_service).trim().toLowerCase() !== "disabled"
      ? status.caddy_service
      : status?.vllm_service || status?.caddy_service || "unknown";
  const serviceBadgeClass = (raw) => {
    const text = String(raw || "").trim().toLowerCase();
    if (["active", "running", "connected", "healthy"].includes(text))
      return "status-production";
    if (["disabled"].includes(text)) return "status-preview";
    if (["inactive", "stopped", "exited", "dead", "failed"].includes(text))
      return "status-unknown";
    return badgeClass("status", text || "unknown");
  };
  const serverCards = [
    {
      display_name: "Control Pane",
      status: String(status?.control_service || "unknown"),
      detail: `admin service | port ${status?.admin_port || "-"}`,
      stateClass: serviceBadgeClass(status?.control_service || "unknown"),
      health_status: String(status?.control_service || "unknown"),
    },
    {
      display_name: "Proxy",
      status: String(proxyStatusRaw || "unknown"),
      detail: `proxy service | port ${status?.proxy_port || "-"}`,
      stateClass: serviceBadgeClass(proxyStatusRaw || "unknown"),
      health_status: String(proxyStatusRaw || "unknown"),
    },
    {
      display_name: "Logging",
      status: String(status?.console_service || "unknown"),
      detail: "console log collector service",
      stateClass: serviceBadgeClass(status?.console_service || "unknown"),
      health_status: String(status?.console_service || "unknown"),
    },
  ];
  const auxCards = rows.map((row) => ({
    display_name: row?.display_name || row?.id || "Service",
    status: row?.running ? "running" : row?.status || "stopped",
    health_status: String(row?.health_status || (row?.running ? "running" : "stopped")),
    detail: [row?.container_name || row?.service_name || "", row?.default_port ? `port ${row.default_port}` : ""]
      .filter(Boolean)
      .join(" | "),
    stateClass: serviceBadgeClass(row?.running ? "running" : row?.status || "unknown"),
    id: String(row?.id || ""),
    running: !!row?.running,
    ready:
      !!row?.running &&
      String(row?.status || "").trim().toLowerCase() === "running" &&
      !["unreachable", "stopped", "starting"].includes(
        String(row?.health_status || "").trim().toLowerCase(),
      ),
  }));
  serverHost.innerHTML = renderServiceCards(serverCards, {
    emptyText: "No server services found.",
  });
  clubHost.innerHTML = renderServiceCards(auxCards, {
    showActions: true,
    emptyText: "No additional Club3090 services are currently active.",
  });
  SYSTEM_SERVICE_SECTION_KEYS.forEach(applySystemServiceSectionState);
}
function upstreamServiceActionLabel(action) {
  const key = String(action || "").trim().toLowerCase();
  if (key === "start") return "Start";
  if (key === "restart") return "Restart";
  if (key === "stop") return "Stop";
  return "Run";
}
async function runUpstreamServiceAction(serviceId, action) {
  const label = upstreamServiceActionLabel(action);
  const response = await post(
    "/admin/services",
    { service_id: serviceId, action },
    `/admin/services ${serviceId} ${action}`,
  );
  if (response?.upstream_services && lastStatus) {
    lastStatus.upstream_services = response.upstream_services;
  }
  setElementMsg("servicesMsg", `${label} requested for ${serviceId}.`, "success");
  await refreshStatus({ force: true });
}
function promptUpstreamServiceAction(serviceId, action) {
  const rows = Array.isArray(lastStatus?.upstream_services) ? lastStatus.upstream_services : [];
  const service = rows.find((row) => String(row?.id || "") === String(serviceId || ""));
  const display = service?.display_name || serviceId || "service";
  const label = upstreamServiceActionLabel(action);
  openPresetActionModal({
    title: `${label} ${escapeHtml(display)}`,
    body: `${label} the upstream auxiliary service <code>${escapeHtml(display)}</code>?`,
    confirmLabel: label,
    confirmClass: action === "stop" ? "red" : action === "restart" ? "amber" : "green",
    onConfirm: async () => {
      await runUpstreamServiceAction(serviceId, action);
    },
  });
}
function openServiceLogSource(serviceId) {
  setCurrentLogSource(`service:${String(serviceId || "")}`);
  activateTab("logs", false);
}
function currentSwitchFailure() {
  return lastStatus?.switch_failure || {};
}
function currentSwitchJob() {
  return lastStatus?.switch_job || {};
}
function switchJobElapsedSeconds(job) {
  const started = Number(job?.started_at || 0);
  if (!Number.isFinite(started) || started <= 0) return 0;
  const finished = Number(job?.finished_at || 0);
  const end = Number.isFinite(finished) && finished > 0 ? finished : Date.now() / 1000;
  return Math.max(0, Math.floor(end - started));
}
function launchSecondsForVariant(selector, target) {
  const job = currentSwitchJob();
  if (job.status !== "success" || !job.mode) return 0;
  const jobMode = String(job.mode || "");
  const jobTarget = String(job.target || "");
  const targetId = String(target?.id || "");
  if (jobMode !== String(selector || "")) return 0;
  if (jobTarget && targetId && jobTarget !== targetId) return 0;
  return switchJobElapsedSeconds(job);
}
function trimSummaryEntries(entries = []) {
  const seen = new Set();
  const out = [];
  entries.forEach((entry) => {
    const selector = String(entry?.selector || "").trim();
    if (!selector || seen.has(selector)) return;
    seen.add(selector);
    out.push({ selector, ts: Number(entry?.ts || Date.now() / 1000) });
  });
  return out.slice(0, 5);
}
function upsertSummaryEntry(storeKey, modelId, selector) {
  const key = String(modelId || "").trim();
  const mode = String(selector || "").trim();
  if (!key || !mode) return;
  const current = Array.isArray(presetSummaryCache[storeKey]?.[key])
    ? presetSummaryCache[storeKey][key]
    : [];
  presetSummaryCache[storeKey][key] = trimSummaryEntries([
    { selector: mode, ts: Date.now() / 1000 },
    ...current.filter((entry) => String(entry?.selector || "") !== mode),
  ]);
}
function removeSummaryEntry(modelId, selector) {
  const key = String(modelId || "").trim();
  const mode = String(selector || "").trim();
  ["persistent", "transient"].forEach((storeKey) => {
    const current = Array.isArray(presetSummaryCache[storeKey]?.[key])
      ? presetSummaryCache[storeKey][key]
      : [];
    presetSummaryCache[storeKey][key] = current.filter(
      (entry) => String(entry?.selector || "") !== mode,
    );
    if (!presetSummaryCache[storeKey][key].length) delete presetSummaryCache[storeKey][key];
  });
  savePresetSummaryCache();
}
function syncPresetSummaryCacheFromStatus(j) {
  const uptime = Number(j?.uptime_seconds || 0);
  if (
    Number.isFinite(presetSummaryCache.lastSeenUptime) &&
    presetSummaryCache.lastSeenUptime > 0 &&
    uptime > 0 &&
    uptime + 5 < presetSummaryCache.lastSeenUptime
  ) {
    presetSummaryCache.transient = {};
    presetSummaryCache.restartTargets = [];
  }
  presetSummaryCache.lastSeenUptime = uptime;
  const variants = variantMapBySelector();
  runtimeStatsRows(j).forEach((runtime) => {
    const selector = String(runtime?.selector || runtime?.mode || "").trim();
    const variant = variants.get(selector);
    if (variant) {
      upsertSummaryEntry("persistent", variant.model_id, selector);
      removeSummaryEntry(variant.model_id, selector);
      upsertSummaryEntry("persistent", variant.model_id, selector);
    }
  });
  const switchJob = j?.switch_job || {};
  const switchMode = String(switchJob.mode || "").trim();
  const switchVariant = variants.get(switchMode);
  if (switchVariant && switchMode) {
    if (switchJob.active || switchJob.status === "failed") {
      upsertSummaryEntry("transient", switchVariant.model_id, switchMode);
    }
    if (switchJob.status === "success") {
      upsertSummaryEntry("persistent", switchVariant.model_id, switchMode);
      const currentTransient = Array.isArray(presetSummaryCache.transient[switchVariant.model_id])
        ? presetSummaryCache.transient[switchVariant.model_id]
        : [];
      presetSummaryCache.transient[switchVariant.model_id] = currentTransient.filter(
        (entry) => String(entry?.selector || "") !== switchMode,
      );
    }
  }
  savePresetSummaryCache();
}
function summaryEntriesForModel(modelId) {
  const key = String(modelId || "").trim();
  const persistent = Array.isArray(presetSummaryCache.persistent[key])
    ? presetSummaryCache.persistent[key]
    : [];
  const transient = Array.isArray(presetSummaryCache.transient[key])
    ? presetSummaryCache.transient[key]
    : [];
  return trimSummaryEntries([...transient, ...persistent]);
}
function summaryRunningTargets() {
  return runtimeStatsRows(lastStatus).map((runtime) => ({
    instance_id: String(runtime?.id || runtime?.instance_id || ""),
    mode: String(runtime?.selector || runtime?.mode || ""),
  }));
}
function runtimeActiveForVariant(selector, target) {
  const normalizedSelector = String(selector || "");
  if (!normalizedSelector || !target) return false;
  if (target.id === "GLOBAL") {
    if (target.kind === "global")
      return runtimeStatsRows(lastStatus).some(
        (row) =>
          String(row?.mode || "") === normalizedSelector &&
          String(row?.id || "") === "GLOBAL",
      );
    if (target.kind === "dual") {
      if (legacyGlobalDualScope()) {
        const legacy = legacyGlobalPair();
        return !!legacy?.running && String(legacy?.mode || "") === normalizedSelector;
      }
      const pairs = pairScopeItems();
      return !!pairs.length && pairs.every(
        (row) => !!row?.running && String(row?.mode || "") === normalizedSelector,
      );
    }
    const singles = singleScopeItems();
    return !!singles.length && singles.every(
      (row) => !!row?.running && String(row?.mode || "") === normalizedSelector,
    );
  }
  const scoped = scopeItems().find((row) => String(row?.id || "") === String(target.id || ""));
  return !!scoped?.running && String(scoped?.mode || "") === normalizedSelector;
}
function runtimeBootingForVariant(selector, target) {
  const normalizedSelector = String(selector || "");
  if (!normalizedSelector || !target) return false;
  if (target.id === "GLOBAL") {
    if (target.kind === "global")
      return runtimeStatsRows(lastStatus).some(
        (row) =>
          !!row?.booting &&
          String(row?.mode || "") === normalizedSelector &&
          String(row?.id || "") === "GLOBAL",
      );
    if (target.kind === "dual") {
      if (legacyGlobalDualScope()) {
        const legacy = legacyGlobalPair();
        return !!legacy?.booting && String(legacy?.mode || "") === normalizedSelector;
      }
      const pairs = pairScopeItems();
      return (
        !!pairs.length &&
        pairs.every(
          (row) =>
            String(row?.mode || "") === normalizedSelector &&
            (!!row?.running || !!row?.booting),
        ) &&
        pairs.some((row) => !!row?.booting)
      );
    }
    const singles = singleScopeItems();
    return (
      !!singles.length &&
      singles.every(
        (row) =>
          String(row?.mode || "") === normalizedSelector &&
          (!!row?.running || !!row?.booting),
      ) &&
      singles.some((row) => !!row?.booting)
    );
  }
  const scoped = scopeItems().find(
    (row) => String(row?.id || "") === String(target.id || ""),
  );
  return !!scoped?.booting && String(scoped?.mode || "") === normalizedSelector;
}
function handleSwitchJobTransition(previousStatus, currentStatus) {
  const prevJob = previousStatus?.switch_job || {};
  const nextJob = currentStatus?.switch_job || {};
  const prevFailure = previousStatus?.switch_failure || {};
  const nextFailure = currentStatus?.switch_failure || {};
  const successTransition =
    prevJob.status !== "success" &&
    nextJob.status === "success" &&
    !nextJob.active &&
    nextJob.mode;
  const failureTransition =
    (prevJob.status !== "failed" && nextJob.status === "failed" && nextJob.mode) ||
    (Number(prevFailure.ts || 0) !== Number(nextFailure.ts || 0) && nextFailure.mode);
  if (successTransition) {
    const key = `success:${nextJob.mode}:${nextJob.target}:${nextJob.finished_at}`;
    if (key !== lastSwitchNotificationKey) {
      lastSwitchNotificationKey = key;
      if (!windowIsFocused()) {
        const seconds = switchJobElapsedSeconds(nextJob);
        showBrowserNotification(
          "Preset Active",
          `${nextJob.mode} reached Active in ${seconds}s.`,
        ).catch(() => {});
      }
    }
  } else if (failureTransition) {
    const mode = String(nextFailure.mode || nextJob.mode || "unknown preset");
    const ts = Number(nextFailure.ts || nextJob.finished_at || Date.now());
    const key = `failed:${mode}:${ts}`;
    if (key !== lastSwitchNotificationKey) {
      lastSwitchNotificationKey = key;
      const summary =
        String(nextFailure.error || nextJob.error || "Preset launch failed.")
          .split("\n")[0]
          .trim() || "Preset launch failed.";
      showBrowserNotification("Preset Error", `${mode}: ${summary}`).catch(() => {});
    }
  }
}
function scopeTargetForVariant(variant) {
  const scope = String(variant?.scope_kind || "");
  if (scope === "single") {
    if (scopeIsGlobal())
      return { id: "GLOBAL", kind: "global", display_name: "Global" };
    const current = currentScopeInstance(true);
    return current && current.kind !== "dual" ? current : null;
  }
  if (scope === "dual") {
    if (scopeIsGlobal()) {
      if (gpuCount() < 2) return null;
      return { id: "GLOBAL", kind: "dual", display_name: "Global Dual" };
    }
    const current = currentScopeInstance(false);
    if (current && current.kind === "dual") return current;
    return null;
  }
  if (scope === "multi" || scope === "global_only") {
    return scopeIsGlobal() ? { id: "GLOBAL", kind: "global", display_name: "Global" } : null;
  }
  return null;
}
function scopeBlockReason(variant) {
  const scope = String(variant?.scope_kind || "");
  if (scope === "single")
    return "Select a GPU scope, or Global to apply this single-GPU preset across every available GPU.";
  if (scope === "dual")
    return "Select a dual pair scope, or Global to apply this dual preset across every available GPU pair.";
  if (scope === "multi" || scope === "global_only")
    return "Select Global scope before applying this multi-GPU preset.";
  return "This preset cannot be applied from the current scope.";
}
function sortInventoryVariants(rows) {
  return [...(rows || [])].sort((a, b) => {
    const activeA = runtimeStatsRows(lastStatus).some(
      (row) => String(row?.mode || "") === variantSelector(a),
    )
      ? -1
      : 0;
    const activeB = runtimeStatsRows(lastStatus).some(
      (row) => String(row?.mode || "") === variantSelector(b),
    )
      ? -1
      : 0;
    if (activeA !== activeB) return activeA - activeB;
    const readyRank = (item) =>
      item?.install_state === "ready" ? 0 : item?.install_state === "requires_download" ? 1 : 2;
    const statusRank = (item) =>
      item?.status_kind === "production"
        ? 0
        : item?.status_kind === "production_caveat"
          ? 1
          : item?.status_kind === "experimental"
            ? 2
            : 3;
    return (
      readyRank(a) - readyRank(b) ||
      statusRank(a) - statusRank(b) ||
      variantDisplayLabel(a).localeCompare(variantDisplayLabel(b))
    );
  });
}
function ensureDynamicPresetLayout() {
  const presets = $("presets");
  if (!presets) return;
  const firstPanel = presets.querySelector(".panel");
  if (!firstPanel) return;
  firstPanel.id = "dynamicPresetPanel";
  if (!$("modelPresetGrid")) {
    firstPanel.innerHTML = `<div class="panel-head"><h2>Model Presets</h2><div class="actions"><button class="btn blue" onclick="openSetupAssistantModal()">Setup Assistant</button><button class="btn green" onclick="promptRuntimeInventoryRebuild()">Rebuild Model DB</button></div></div><div class="preset-help">Discovered presets are rendered directly from the local <code>/opt/ai/club-3090</code> clone. Global applies single-GPU presets across every GPU, dual presets across every two-GPU pair, and multi-GPU presets to the shared runtime.</div><div class="preset-section-label">Scope</div><div class="subtabs" id="presetScopeTabs"></div><div class="value smallgap" id="presetScopeSummary">-</div><div class="preset-section-label">Models</div><div class="subtabs" id="presetModelSelector"></div><div class="value smallgap" id="presetJobSummary">-</div><div id="modelPresetGrid" class="model-grid"></div>`;
  }
  if ($("singlePresetCard")) $("singlePresetCard").removeAttribute("id");
  if ($("dualPresetCard")) $("dualPresetCard").remove();
  if ($("presetScopePanel")) $("presetScopePanel").remove();
}
let presetActionHandler = null;
function ensurePresetActionModal() {
  if ($("presetActionModal")) return;
  const modal = document.createElement("div");
  modal.id = "presetActionModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card" role="dialog" aria-modal="true" aria-labelledby="presetActionModalTitle"><div class="panel-head"><h2 id="presetActionModalTitle">Confirm Action</h2><button class="iconbtn" title="Close" aria-label="Close" onclick="closePresetActionModal()">${svgIcon("delete")}</button></div><div class="preset-help" id="presetActionModalBody">-</div><textarea id="presetActionModalDetail" class="modal-keybox hidden" readonly wrap="soft" spellcheck="false"></textarea><div class="preset-form-actions"><button class="btn blue" onclick="closePresetActionModal()">Cancel</button><button class="btn green" id="presetActionModalConfirm">Continue</button></div><div class="msg" id="presetActionModalMsg"></div></div>`;
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closePresetActionModal();
  });
  document.body.appendChild(modal);
}
function openPresetActionModal(opts = {}) {
  ensurePresetActionModal();
  presetActionHandler = typeof opts.onConfirm === "function" ? opts.onConfirm : null;
  $("presetActionModalTitle").textContent = opts.title || "Confirm Action";
  $("presetActionModalBody").innerHTML = opts.body || "";
  $("presetActionModalMsg").textContent = "";
  const detail = $("presetActionModalDetail");
  if (opts.detail) {
    detail.value = String(opts.detail);
    detail.scrollTop = 0;
    detail.classList.remove("hidden");
  } else {
    detail.value = "";
    detail.classList.add("hidden");
  }
  const confirmBtn = $("presetActionModalConfirm");
  confirmBtn.textContent = opts.confirmLabel || "Continue";
  confirmBtn.className = `btn ${opts.confirmClass || "green"}`;
  confirmBtn.onclick = async () => {
    if (!presetActionHandler) return closePresetActionModal();
    confirmBtn.disabled = true;
    try {
      await presetActionHandler();
      closePresetActionModal();
    } catch (e) {
      $("presetActionModalMsg").textContent = String(e || "");
    } finally {
      confirmBtn.disabled = false;
    }
  };
  $("presetActionModal").classList.remove("hidden");
}
function closePresetActionModal() {
  ensurePresetActionModal();
  $("presetActionModal").classList.add("hidden");
  presetActionHandler = null;
}
function ensureActionChoiceModal() {
  if ($("actionChoiceModal")) return;
  const modal = document.createElement("div");
  modal.id = "actionChoiceModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card" id="actionChoiceModalCard" role="dialog" aria-modal="true" aria-labelledby="actionChoiceModalTitle"><div class="panel-head"><h2 id="actionChoiceModalTitle">Choose Action</h2><button class="iconbtn" title="Close" aria-label="Close" onclick="closeActionChoiceModal()">${svgIcon("delete")}</button></div><div class="preset-help" id="actionChoiceModalBody">-</div><div class="preset-form-actions" id="actionChoiceModalChoices"></div><div class="preset-form-actions"><button class="btn blue" onclick="closeActionChoiceModal()">Cancel</button></div><div class="msg" id="actionChoiceModalMsg"></div></div>`;
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeActionChoiceModal();
  });
  document.body.appendChild(modal);
}
function closeActionChoiceModal() {
  ensureActionChoiceModal();
  $("actionChoiceModal").classList.add("hidden");
}
function openActionChoiceModal(opts = {}) {
  ensureActionChoiceModal();
  $("actionChoiceModalCard").className = `club-modal-card${opts.cardClass ? ` ${opts.cardClass}` : ""}`;
  $("actionChoiceModalTitle").textContent = opts.title || "Choose Action";
  $("actionChoiceModalBody").innerHTML = opts.body || "";
  $("actionChoiceModalMsg").textContent = "";
  const host = $("actionChoiceModalChoices");
  host.innerHTML = "";
  (opts.choices || []).forEach((choice) => {
    const button = document.createElement("button");
    button.className = `btn ${choice.className || "green"}`;
    button.textContent = choice.label || "Continue";
    button.onclick = async () => {
      button.disabled = true;
      try {
        await choice.onClick();
        closeActionChoiceModal();
      } catch (e) {
        $("actionChoiceModalMsg").textContent = String(e || "");
      } finally {
        button.disabled = false;
      }
    };
    host.appendChild(button);
  });
  $("actionChoiceModal").classList.remove("hidden");
}
function promptRuntimeInventoryRebuild() {
  openPresetActionModal({
    title: "Rebuild Model DB",
    body: "This rescans the upstream <code>club-3090</code> checkout, rebuilds the runtime inventory, and refreshes model/preset metadata without touching your downloaded model assets.",
    confirmLabel: "Rebuild",
    confirmClass: "green",
    onConfirm: async () => {
      await post("/admin/rebuild-inventory", {}, "/admin/rebuild-inventory");
      await refreshStatus({ force: true });
    },
  });
}
function promptBenchmarkRun() {
  openPresetActionModal({
    title: "Run Benchmark",
    body: "This runs the upstream <code>bash scripts/bench.sh</code> helper against the currently active backend and streams the full output into Audit Logs.",
    confirmLabel: "Run Benchmark",
    confirmClass: "blue",
    onConfirm: async () => {
      await post("/admin/benchmark", {}, "/admin/benchmark");
      setAuditMsg("Benchmark started. Output is streaming to Audit Logs.");
    },
  });
}
function promptReportRun() {
  openPresetActionModal({
    title: "Run Report",
    body: "This runs the upstream <code>bash scripts/report.sh</code> helper for the current runtime and streams the generated report into Audit Logs.",
    confirmLabel: "Run Report",
    confirmClass: "blue",
    onConfirm: async () => {
      await post("/admin/run-report", {}, "/admin/run-report");
      setAuditMsg("Run Report started. Output is streaming to Audit Logs.");
    },
  });
}
async function startUpdateFlow(scope) {
  const normalized = scope === "club3090" ? "club3090" : "controller";
  await post(
    "/admin/update",
    { scope: normalized },
    `/admin/update ${normalized}`,
  );
  setAuditMsg(
    normalized === "club3090"
      ? "Club-3090 migration launched. Output is streaming to Audit Logs."
      : "Admin script update launched. Output is streaming to Audit Logs.",
  );
}
function promptUpdateRun() {
  openActionChoiceModal({
    title: "Run Update",
    body: "Choose which update flow to launch. The admin-script option refreshes only the control layer. The Club-3090 option runs the full <code>--migrate</code> pass. Both stream their output into Audit Logs right away.",
    choices: [
      {
        label: "Update Admin Script",
        className: "blue",
        onClick: async () => {
          await startUpdateFlow("controller");
        },
      },
      {
        label: "Migrate Club-3090",
        className: "orange",
        onClick: async () => {
          await startUpdateFlow("club3090");
        },
      },
    ],
  });
}
function variantStatusBadgeSummary(rows) {
  const counts = new Map();
  (rows || []).forEach((row) => {
    const key = String(row?.status_kind || "").trim();
    if (!key) return;
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return [...counts.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(
      ([status, count]) =>
        `<span class="status-badge ${badgeClass("status", status)}">${escapeHtml(statusLabel({ status_kind: status }))} ${count}</span>`,
    )
    .join("");
}
function experimentalVariantRows(rows) {
  return sortInventoryVariants(rows).sort((a, b) => {
    const order = (item) => {
      const key = String(item?.status_kind || "");
      if (key === "upstream_gated") return 0;
      if (key === "blocked") return 1;
      if (key === "experimental") return 2;
      if (key === "preview") return 3;
      if (key === "deprecated") return 4;
      if (key === "tombstoned") return 5;
      return 6;
    };
    return order(a) - order(b) || variantDisplayLabel(a).localeCompare(variantDisplayLabel(b));
  });
}
function promptModelInstall(variant) {
  openPresetActionModal({
    title: `Download ${escapeHtml(variant?.model_id || "model")} assets`,
    body: `${escapeHtml(variantDisplayLabel(variant))} is not ready on disk yet. Download the required assets now?<br><br>${escapeHtml(variant?.install_reason || "This preset needs additional model files before it can run.")}`,
    detail: variant?.install_command || "",
    confirmLabel: "Download",
    confirmClass: "green",
    onConfirm: async () => {
      await post(
        "/admin/model-install",
        {
          model_id: variant.model_id,
          variant_id: variant.variant_id,
          install_command: variant.install_command,
        },
        `/admin/model-install ${variant.model_id} ${variant.variant_id}`,
      );
      await refreshStatus({ force: true });
    },
  });
}
function promptModelInstallById(variantId) {
  const variant = inventoryVariants().find((row) => String(row?.variant_id || "") === String(variantId || ""));
  if (!variant) throw new Error("Preset not found in runtime inventory.");
  return promptModelInstall(variant);
}
async function promptModelFamilyInstall(modelId) {
  const model = inventoryModels().find((row) => String(row?.model_id || "") === String(modelId || ""));
  if (!model || !model.default_install_command || !model.default_install_variant_id) {
    throw new Error("No generic install flow is available for this model family yet.");
  }
  openPresetActionModal({
    title: `Download ${escapeHtml(model.display_name || model.model_id || "model")} assets`,
    body: `${escapeHtml(model.display_name || model.model_id || "This model family")} is not fully ready on disk yet.<br><br>${escapeHtml(model.default_install_reason || "Download the default required assets now?")}`,
    detail: model.default_install_command || "",
    confirmLabel: "Download",
    confirmClass: "green",
    onConfirm: async () => {
      await post(
        "/admin/model-install",
        {
          model_id: model.model_id,
          variant_id: model.default_install_variant_id,
          install_command: model.default_install_command,
        },
        `/admin/model-install ${model.model_id} ${model.default_install_variant_id}`,
      );
      await refreshStatus({ force: true });
    },
  });
}
function rigSummaryText() {
  const rows = Array.isArray(lastStatus?.gpus) ? lastStatus.gpus.filter((row) => row && !row.error) : [];
  const base = !rows.length
    ? "No NVIDIA GPU telemetry detected."
    : rows
    .map((row) => `${row.name || `GPU ${row.index}`}${row.mem_total_mib ? ` (${Math.round(Number(row.mem_total_mib || 0) / 1024)} GB)` : ""}`)
    .join(" | ");
  const nvlink = rigNvlinkInfo();
  if (nvlink.source === "unavailable") return base;
  return `${base} | ${nvlink.present ? "NVLink active" : "NVLink inactive"}`;
}
function variantFitsCurrentRig(variant) {
  const rows = Array.isArray(lastStatus?.gpus) ? lastStatus.gpus.filter((row) => row && !row.error) : [];
  if (!rows.length) return true;
  const minGpuCount = Number(variant?.requires_min_gpu_count || 0);
  const minVramGb = Number(variant?.requires_min_vram_gb || 0);
  const requiredSmRank = smToRank(variant?.requires_sm);
  const nvlinkMode = variantNvlinkMode(variant);
  if (minGpuCount > 0 && rows.length < minGpuCount) return false;
  if (nvlinkMode === "required" && !rigHasNvlink()) return false;
  if (minVramGb > 0) {
    const eligible = rows.filter(
      (row) => Math.ceil(Number(row?.mem_total_mib || 0) / 1024) >= minVramGb,
    );
    if (eligible.length < Math.max(minGpuCount || 1, 1)) return false;
  }
  if (requiredSmRank > 0) {
    const eligible = rows.filter((row) => smToRank(row?.compute_cap) >= requiredSmRank);
    if (eligible.length < Math.max(minGpuCount || 1, 1)) return false;
  }
  return true;
}
function assistantRecommendedVariants() {
  const preferred = inventoryVariants().filter(
    (row) =>
      ["production", "production_caveat"].includes(String(row?.status_kind || "")) &&
      variantFitsCurrentRig(row),
  );
  const byModel = new Set();
  return sortInventoryVariants(preferred).filter((row) => {
    const key = `${row?.model_id || ""}::${row?.category || ""}`;
    if (byModel.has(key)) return false;
    byModel.add(key);
    return true;
  }).slice(0, 8);
}
function openSetupAssistantModal() {
  const models = inventoryModels();
  const recommendations = assistantRecommendedVariants();
  openActionChoiceModal({
    title: "Setup Assistant",
    body: `<div class="assistant-modal-grid"><div class="assistant-modal-column"><div class="preset-help">Detected rig: ${escapeHtml(rigSummaryText())}</div><div class="preset-help">Use this assistant to download the default assets for each model family and launch a safe preset that fits the detected hardware.</div><div class="preset-section-label">Model Families</div><div class="variant-grid">${models
      .map((model) => `<div class="variant-card"><div class="variant-card-head"><div class="variant-card-title">${escapeHtml(model.display_name || model.model_id)}</div><div class="badge-row"><span class="state-badge ${badgeClass("state", model.installed_state)}">${escapeHtml(String(model.installed_state || "unknown"))}</span></div></div><div class="variant-meta"><strong>Summary:</strong> ${escapeHtml(model.summary || "No summary available yet.")}</div><div class="variant-actions">${model.default_install_command ? `<button class="btn green" onclick="promptModelFamilyInstall('${escapeJs(model.model_id)}')">Download Core Assets</button>` : `<button class="btn amber" disabled>Manual setup required</button>`}</div></div>`)
      .join("")}</div></div><div class="assistant-modal-column"><div class="preset-section-label">Recommended Presets For This Rig</div><div class="variant-grid">${recommendations
      .map((variant) => `<div class="variant-card"><div class="variant-card-head"><div class="variant-card-title">${escapeHtml(variantDisplayLabel(variant))}</div><div class="badge-row"><span class="status-badge ${badgeClass("status", variant.status_kind)}">${escapeHtml(statusLabel(variant))}</span>${variantCapabilityBadges(variant)}</div></div><div class="variant-meta"><strong>Model:</strong> ${escapeHtml((inventoryModels().find((row) => row.model_id === variant.model_id) || {}).display_name || variant.model_id || "-")}</div><div class="variant-meta"><strong>Hardware:</strong> ${escapeHtml(variantHardwareSummary(variant) || "No explicit gate")}</div><div class="variant-meta"><strong>Best for:</strong> ${escapeHtml(variant.best_for || variant.quality_summary || "No summary yet.")}</div><div class="variant-actions">${variant.install_state === "ready" ? `<button class="btn blue" onclick="switchInventoryVariant('${escapeJs(variantSelector(variant))}')">Launch</button>` : variant.install_command ? `<button class="btn green" onclick="promptModelInstallById('${escapeJs(variant.variant_id)}')">Download</button>` : `<button class="btn amber" disabled>Unavailable</button>`}</div></div>`)
      .join("") || `<div class="empty-variant-note">No production-ready presets match the currently detected hardware yet.</div>`}</div></div></div>`,
    choices: [],
    cardClass: "assistant-modal-card",
  });
}
async function switchInventoryVariant(selector) {
  const variant = inventoryVariants().find(
    (item) => variantSelector(item) === selector || item.variant_id === selector,
  );
  if (!variant) {
    alert("Preset not found in runtime inventory.");
    return;
  }
  if (variant.install_state !== "ready") {
    promptModelInstall(variant);
    return;
  }
  const target = scopeTargetForVariant(variant);
  if (!target) {
    alert(scopeBlockReason(variant));
    return;
  }
  const label = variantDisplayLabel(variant);
  const targetLabel =
    target.id === "GLOBAL"
      ? variant.scope_kind === "single"
        ? "Global scope across every available GPU"
        : variant.scope_kind === "dual"
          ? "Global scope across every available GPU pair"
          : "Global scope"
      : `${target.id}${target.gpu_indices ? ` on GPUs ${(target.gpu_indices || []).join(", ")}` : ""}`;
  if (
    !confirm(
      `Launch ${label} on ${targetLabel}? This will stop any overlapping runtime currently using those GPUs.`,
    )
  ) {
    return;
  }
  openRuntimeLogsAtPoint(chooseVariantLogInstanceId(target, selector), "");
  await post("/admin/switch", { instance_id: target.id, mode: selector }, `/admin/switch ${target.id} ${label}`);
  await refreshStatus({ force: true });
}
switchMode = function (mode) {
  return switchInventoryVariant(mode);
};
switchDualMode = function (mode) {
  return switchInventoryVariant(mode);
};
function focusVariantFailure(selector) {
  const variant = inventoryVariants().find((item) => variantSelector(item) === selector);
  const target = scopeTargetForVariant(variant || {});
  openRuntimeLogsAtPoint(
    chooseVariantLogInstanceId(target, selector),
    bestFailureLogQuery(currentSwitchFailure()),
  );
}
function promptVariantStop(selector, booting = false) {
  const variant = inventoryVariants().find((item) => variantSelector(item) === selector);
  const label = variantDisplayLabel(variant || { upstream_tag: selector });
  const target = scopeTargetForVariant(variant || {});
  openPresetActionModal({
    title: booting ? "Interrupt Preset Boot" : "Stop Active Preset",
    body: booting
      ? `Interrupt <code>${escapeHtml(label)}</code> before it reaches Active and kill the container${target?.id === "GLOBAL" ? "s" : ""}?`
      : `Stop <code>${escapeHtml(label)}</code> and kill the running container${target?.id === "GLOBAL" ? "s" : ""}?`,
    confirmLabel: booting ? "Interrupt" : "Stop",
    confirmClass: "rose",
    onConfirm: async () => {
      openRuntimeLogsAtPoint(chooseVariantLogInstanceId(target, selector), "");
      await post(
        "/admin/power",
        {
          action: "stop_container",
          instance_id: target?.id || null,
          mode: selector,
        },
        `/admin/power stop_container ${(target && target.id) || "GLOBAL"} ${label}`,
      );
      await refreshStatus({ force: true });
    },
  });
}
function promptRemoveSummaryPreset(modelId, selector) {
  if (!confirm(`Remove ${selector} from the cached summary list?`)) return;
  removeSummaryEntry(modelId, selector);
  renderDynamicPresetModels();
}
async function stopAllSummaryPresets() {
  const targets = summaryRunningTargets().filter(
    (item) => item.instance_id && item.mode,
  );
  if (!targets.length) return;
  if (!confirm(`Stop all ${targets.length} running preset${targets.length === 1 ? "" : "s"}?`))
    return;
  presetSummaryCache.restartTargets = targets;
  savePresetSummaryCache();
  for (const target of targets) {
    await post(
      "/admin/power",
      {
        action: "stop_container",
        instance_id: target.instance_id,
        mode: target.mode,
      },
      `/admin/power stop_container ${target.instance_id} ${target.mode}`,
    );
  }
  await refreshStatus({ force: true });
}
async function restartAllSummaryPresets() {
  const targets = Array.isArray(presetSummaryCache.restartTargets)
    ? presetSummaryCache.restartTargets
    : [];
  if (!targets.length) return;
  for (const target of targets) {
    await post(
      "/admin/switch",
      {
        instance_id: target.instance_id,
        mode: target.mode,
      },
      `/admin/switch ${target.instance_id} ${target.mode}`,
    );
  }
  presetSummaryCache.restartTargets = [];
  savePresetSummaryCache();
  await refreshStatus({ force: true });
}
function renderSummaryActionBar() {
  const running = summaryRunningTargets().filter(
    (item) => item.instance_id && item.mode,
  );
  if (running.length) {
    return `<div class="summary-action-bar"><button class="btn red" onclick="stopAllSummaryPresets()">Stop All</button></div>`;
  }
  if (Array.isArray(presetSummaryCache.restartTargets) && presetSummaryCache.restartTargets.length) {
    return `<div class="summary-action-bar"><button class="btn green" onclick="restartAllSummaryPresets()">Restart All</button></div>`;
  }
  return "";
}
function modelFamilyHasActivePreset(modelVariants) {
  const activeSelectors = new Set(
    runtimeStatsRows(lastStatus)
      .filter((row) => row && row.running)
      .map((row) => String(row?.selector || row?.mode || "")),
  );
  return (modelVariants || []).some((variant) =>
    activeSelectors.has(String(variantSelector(variant) || "")),
  );
}
function renderSummaryVariantCard(variant, modelId) {
  const selector = variantSelector(variant);
  const target = scopeTargetForVariant(variant);
  const switchJob = currentSwitchJob();
  const switchTarget = String(switchJob.target || "");
  const targetId = String(target?.id || "");
  const failed =
    String(currentSwitchFailure().mode || "") === selector &&
    !runtimeStatsRows(lastStatus).some((row) => String(row?.mode || "") === selector) &&
    (!targetId || !switchTarget || switchTarget === targetId);
  const switching =
    (!!switchJob.active &&
      String(switchJob.mode || "") === selector &&
      (!targetId || !switchTarget || switchTarget === targetId)) ||
    runtimeBootingForVariant(selector, target);
  const active = runtimeActiveForVariant(selector, target) && !switching && !failed;
  const buttonLabel = switching ? "Booting..." : active ? "Stop" : failed ? "Restart" : "Launch";
  const buttonClass = switching ? "amber" : active || failed ? "rose" : "blue";
  const action = active
    ? `promptVariantStop('${escapeJs(selector)}', false)`
    : switching
      ? `promptVariantStop('${escapeJs(selector)}', true)`
      : `switchInventoryVariant('${escapeJs(selector)}')`;
  const stateClass = switching
    ? "state-booting"
    : active
      ? "state-active"
      : failed
        ? "state-error"
        : "state-summary-inactive";
  const stateLabel = switching ? "booting" : active ? "active" : failed ? "error" : "inactive";
  return `<div class="summary-preset-card${active || switching ? "" : " summary-preset-card-inactive"}"><div class="summary-preset-head"><div class="summary-preset-title">${escapeHtml(variantDisplayLabel(variant))}</div><div class="preset-actions">${renderIconButton({ title: "Remove from summary", action: `promptRemoveSummaryPreset('${escapeJs(modelId)}','${escapeJs(selector)}')`, icon: "delete" })}</div></div><div class="badge-row"><span class="state-badge ${stateClass}">${escapeHtml(stateLabel)}</span>${failed ? "" : `<span class="status-badge ${badgeClass("status", variant.status_kind)}">${escapeHtml(statusLabel(variant))}</span>`}${variantCapabilityBadges(variant)}</div><div class="summary-preset-meta">${escapeHtml(variant.best_for || variant.quality_summary || "Cached preset")}</div><div class="variant-actions"><button class="btn ${buttonClass}" onclick="${action}">${escapeHtml(buttonLabel)}</button></div></div>`;
}
function renderSummaryModelBody(model, modelVariants) {
  const entries = summaryEntriesForModel(model.model_id);
  const bySelector = new Map(
    modelVariants.map((variant) => [variantSelector(variant), variant]),
  );
  const cards = entries
    .map((entry) => bySelector.get(String(entry.selector || "")))
    .filter(Boolean)
    .slice(0, 5)
    .map((variant) => renderSummaryVariantCard(variant, model.model_id));
  return cards.length
    ? cards.join("")
    : `<div class="empty-variant-note">No cached presets for this model yet. Active and booting presets will appear here automatically.</div>`;
}
function renderVariantCard(variant) {
  const selector = variantSelector(variant);
  const target = scopeTargetForVariant(variant);
  const installJob = lastStatus?.model_install_job || {};
  const switchJob = currentSwitchJob();
  const failure = currentSwitchFailure();
  const switchTarget = String(switchJob.target || "");
  const targetId = String(target?.id || "");
  const failed =
    String(failure.mode || "") === selector &&
    !runtimeStatsRows(lastStatus).some((row) => String(row?.mode || "") === selector) &&
    (!targetId || !switchTarget || switchTarget === targetId);
  const switching =
    (!!switchJob.active &&
      String(switchJob.mode || "") === selector &&
      (!targetId || !switchTarget || switchTarget === targetId)) ||
    runtimeBootingForVariant(selector, target);
  const active = runtimeActiveForVariant(selector, target) && !switching && !failed;
  const ready = variant.install_state === "ready";
  const installing =
    !!installJob.active &&
    installJob.model_id === variant.model_id &&
    installJob.variant_id === variant.variant_id;
  const disabled = ready ? !target || installing : installing;
  const bootSeconds = switchJobElapsedSeconds(switchJob);
  const buttonLabel = installing
    ? "Installing..."
    : switching
      ? `Booting for ${bootSeconds}s...`
    : ready
      ? active
        ? "Stop"
        : failed
          ? "Restart"
          : "Launch"
      : "Download";
  const buttonClass = installing
    ? "green"
    : switching
      ? "amber"
      : ready
        ? active || failed
          ? "rose"
          : "blue"
        : "green";
  const launchSeconds = active ? launchSecondsForVariant(selector, target) : 0;
  const stateClass = switching
    ? "state-booting"
    : active
      ? "state-active"
      : failed
        ? "state-error"
        : badgeClass("state", variant.install_state);
  const stateLabel = switching
    ? "booting"
    : active
      ? "active"
      : failed
        ? "error"
        : installStateLabel(variant);
  const stateAttrs = failed
    ? ` role="button" tabindex="0" title="Open the relevant runtime log lines" onclick="focusVariantFailure('${escapeJs(selector)}')"`
    : "";
  const caveat = variant.caveats
    ? `<div class="variant-caveat"><strong>Caveats:</strong> ${escapeHtml(variant.caveats)}</div>`
    : "";
  const installNote =
    !ready && variant.install_reason
      ? `<div class="variant-install-note"><strong>Install:</strong> ${escapeHtml(variant.install_reason)}</div>`
      : "";
  const failureNote = failed
    ? `<div class="variant-install-note error-note"><strong>Last error:</strong> ${escapeHtml(String(failure.error || "").split("\n")[0] || "Preset launch failed.")}</div>`
    : "";
  const hardwareNote = variantHardwareSummary(variant)
    ? `<div class="variant-meta"><strong>Hardware:</strong> ${escapeHtml(variantHardwareSummary(variant))}</div>`
    : "";
  const statusBadge = failed
    ? ""
    : `<span class="status-badge ${badgeClass("status", variant.status_kind)}">${escapeHtml(statusLabel(variant))}</span>`;
  const footer = launchSeconds
    ? `<div class="variant-footer"><span class="variant-launch-time">${escapeHtml(formatElapsedLaunch(launchSeconds))}</span></div>`
    : "";
  const action = ready
    ? active
      ? `promptVariantStop('${escapeJs(selector)}', false)`
      : switching
        ? `promptVariantStop('${escapeJs(selector)}', true)`
        : failed
          ? `switchInventoryVariant('${escapeJs(selector)}')`
          : `switchInventoryVariant('${escapeJs(selector)}')`
    : `switchInventoryVariant('${escapeJs(selector)}')`;
  return `<div class="variant-card${active ? " active-variant" : ""}"><div class="variant-card-head"><div class="variant-card-title">${escapeHtml(variantDisplayLabel(variant))}</div><div class="badge-row"><span class="state-badge ${stateClass}"${stateAttrs}>${escapeHtml(stateLabel)}</span>${statusBadge}${variantCapabilityBadges(variant)}</div></div><div class="variant-meta"><strong>Best for:</strong> ${escapeHtml(variant.best_for || "No summary yet.")}</div><div class="variant-meta"><strong>Max ctx:</strong> ${escapeHtml(variantMaxCtx(variant))} <strong>Engine:</strong> ${escapeHtml(prettyEngineName(variant.engine))} <strong>Drafter:</strong> ${escapeHtml(variant.drafter || "none")} <strong>KV:</strong> ${escapeHtml(variant.kv_format || "n/a")}</div>${hardwareNote}${caveat}${installNote}${failureNote}<div class="variant-actions"><button class="btn ${buttonClass}" ${disabled ? "disabled" : ""} onclick="${action}">${escapeHtml(buttonLabel)}</button></div>${footer}</div>`;
}
function renderVariantGroup(title, rows) {
  const items =
    title === "Experimental Docker Presets"
      ? experimentalVariantRows(rows)
      : sortInventoryVariants(rows);
  const body = items.length
    ? `<div class="variant-grid">${items.map(renderVariantCard).join("")}</div>`
    : `<div class="empty-variant-note">No presets discovered for this category.</div>`;
  const countLabel = `${title} (${items.length} Presets)`;
  const groupBadges =
    title === "Experimental Docker Presets" && items.length
      ? `<div class="variant-group-badges">${variantStatusBadgeSummary(items)}</div>`
      : "";
  return `<div class="variant-group"><div class="variant-group-head"><h4>${escapeHtml(countLabel)}</h4>${groupBadges}</div>${body}</div>`;
}
function renderDynamicPresetModels() {
  ensureDynamicPresetLayout();
  hydrateSelectedPresetModel();
  renderPresetModelSelector();
  const host = $("modelPresetGrid");
  if (!host) return;
  const variants = inventoryVariants();
  const models = inventoryModels();
  if (!models.length) {
    host.innerHTML = `<div class="model-card"><div class="empty-variant-note">No runtime inventory data was found. Rebuild the Model DB to rescan the upstream checkout.</div></div>`;
    return;
  }
  const visibleModels = selectedPresetModelId
    ? models.filter((model) => String(model.model_id || "") === selectedPresetModelId)
    : models;
  host.innerHTML = `${visibleModels
    .map((model) => {
      const modelVariants = variants.filter((row) => row.model_id === model.model_id);
      const selected = String(model.model_id || "") === selectedPresetModelId;
      const familyActive = modelFamilyHasActivePreset(modelVariants);
      const presetCount = modelVariants.length;
      const summaryBody = renderSummaryModelBody(model, modelVariants);
      const body = selected
        ? `<div class="variant-groups">${renderVariantGroup("Single GPU Docker Presets", modelVariants.filter((row) => row.category === "single"))}${renderVariantGroup("Dual GPU Docker Presets", modelVariants.filter((row) => row.category === "dual"))}${renderVariantGroup("Multi GPU Docker Presets", modelVariants.filter((row) => row.category === "multi"))}${renderVariantGroup("Experimental Docker Presets", modelVariants.filter((row) => row.category === "experimental"))}</div>`
        : summaryBody;
      return `<div class="model-card${selected ? " selected-model-card" : " collapsed-model-card"}${familyActive ? " model-card-active-family" : ""}"><div class="model-card-head"><div><h3>${escapeHtml(model.display_name || model.model_id)} (${presetCount} Presets)</h3><div class="model-summary">${escapeHtml(model.summary || "No summary available yet.")}</div></div><div class="badge-row"><span class="state-badge ${badgeClass("state", model.installed_state)}">${escapeHtml(String(model.installed_state || "unknown"))}</span></div></div>${body}</div>`;
    })
    .join("")}${!selectedPresetModelId ? renderSummaryActionBar() : ""}`;
}
function renderModelInstallStatus() {
  const target = $("presetJobSummary");
  if (!target) return;
  const job = lastStatus?.model_install_job || {};
  if (job.active) {
    target.textContent = `Model install running for ${job.model_id || "unknown model"} (${job.variant_id || "preset"}). Output is streaming to Audit Logs.`;
    return;
  }
  if (job.status === "success") {
    target.textContent = `${job.summary || "Model install completed successfully."}`;
    return;
  }
  if (job.status === "failed") {
    target.textContent = `${job.summary || "Model install failed."}`;
    return;
  }
  target.textContent =
    "Downloads started from this tab stream into Audit Logs and automatically rebuild the Model DB on success.";
}
function chatConversationTitle(conversation) {
  return String(conversation?.title || "").trim() || CHAT_UNTITLED_TITLE;
}
function setSelectOptions(select, html) {
  if (!select) return false;
  const nextHtml = String(html || "");
  if (select.dataset.renderedOptions === nextHtml) return false;
  const currentValue = String(select.value || "");
  select.innerHTML = nextHtml;
  select.dataset.renderedOptions = nextHtml;
  if (currentValue && [...select.options].some((option) => option.value === currentValue)) {
    select.value = currentValue;
  }
  return true;
}
function chatConversationFolders() {
  return [...new Set(chatConversations().map((conversation) => normalizeConversationFolder(conversation.folder)).filter(Boolean))].sort(
    (left, right) => left.localeCompare(right),
  );
}
function renderConversationSelector() {
  const select = $("chatConversationSelect");
  if (!select) return;
  if (chatHydrationPending() || (!chatStateHydrated && !chatConversations().length)) {
    setSelectOptions(
      select,
      '<option value="" selected>Loading conversations...</option>',
    );
    select.disabled = true;
    return;
  }
  const rows = chatConversations();
  const rootRows = rows.filter((conversation) => !conversation.folder);
  const grouped = chatConversationFolders()
    .map((folder) => ({
      folder,
      rows: rows.filter(
        (conversation) => normalizeConversationFolder(conversation.folder) === folder,
      ),
    }))
    .filter((group) => group.rows.length);
  const html = [];
  rootRows.forEach((conversation) => {
    html.push(
      `<option value="${escapeHtml(conversation.id)}" ${
        conversation.id === chatState.activeConversationId ? "selected" : ""
      }>${escapeHtml(chatConversationTitle(conversation))}</option>`,
    );
  });
  grouped.forEach((group) => {
    html.push(
      `<optgroup label="${escapeHtml(group.folder)}">${group.rows
        .map(
          (conversation) =>
            `<option value="${escapeHtml(conversation.id)}" ${
              conversation.id === chatState.activeConversationId
                ? "selected"
                : ""
            }>${escapeHtml(chatConversationTitle(conversation))}</option>`,
        )
        .join("")}</optgroup>`,
    );
  });
  setSelectOptions(select, html.join(""));
  if (
    chatState.activeConversationId &&
    [...select.options].some((option) => option.value === chatState.activeConversationId)
  ) {
    select.value = chatState.activeConversationId;
  }
  select.disabled = !!chatState.busy;
}
function selectChatConversation(value) {
  const nextId = String(value || "");
  if (!nextId || nextId === chatState.activeConversationId || chatState.busy) return;
  const previousId = String(chatState.activeConversationId || "");
  persistChatConversationState();
  chatState.activeConversationId = nextId;
  resetChatTranscriptWindow();
  syncChatStateFromActiveConversation();
  saveChatState();
  setChatMsg("");
  logDebugEvent("chat_conversation_select", {
    previousConversationId: previousId,
    nextConversationId: nextId,
    messagesLoaded: activeChatConversation()?.messagesLoaded !== false,
  });
  renderChatUi();
  loadChatConversationDetail(nextId).catch((e) => {
    setChatMsg(e?.message || "Failed to load conversation.", "error");
  });
}
function createNewConversation() {
  if (chatState.busy) return;
  persistChatConversationState();
  const baseConversation = activeChatConversation();
  const conversation = createChatConversation({}, baseConversation);
  conversation.title = CHAT_UNTITLED_TITLE;
  conversation.autoNamed = false;
  conversation.compactionSequence = 1;
  conversation.compactedFromId = "";
  chatState.conversations = [...chatConversations(), conversation];
  chatState.activeConversationId = conversation.id;
  resetChatTranscriptWindow();
  syncChatStateFromActiveConversation();
  saveChatState();
  renderChatUi();
  setTimeout(() => $("chatInput")?.focus(), 0);
}
function ensureConversationEditorModal() {
  if ($("chatConversationModal")) return;
  const modal = document.createElement("div");
  modal.id = "chatConversationModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card conversation-modal-card" role="dialog" aria-modal="true" aria-labelledby="chatConversationTitle"><div class="panel-head"><h2 id="chatConversationTitle">Edit Conversation</h2><button class="iconbtn danger-iconbtn" title="Close" aria-label="Close" onclick="closeConversationEditorModal()">${svgIcon("close")}</button></div><div class="formgrid"><label>Conversation Name<input id="chatConversationName" placeholder="${escapeHtml(CHAT_UNTITLED_TITLE)}" /></label><label>Folder<input id="chatConversationFolder" list="chatConversationFolderList" placeholder="optional subfolder" pattern="[A-Za-z0-9 _-]*" /></label></div><datalist id="chatConversationFolderList"></datalist><div class="preset-help">Use only letters, numbers, spaces, <code>-</code>, and <code>_</code>.</div><div class="preset-form-actions"><button class="btn blue" onclick="closeConversationEditorModal()">Cancel</button><button class="btn green" onclick="saveConversationEditorModal()">OK</button></div><div class="msg" id="chatConversationModalMsg"></div></div>`;
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeConversationEditorModal();
  });
  document.body.appendChild(modal);
}
function openConversationEditorModal() {
  if (chatState.busy) return;
  ensureConversationEditorModal();
  const conversation = activeChatConversation();
  if (!conversation) return;
  $("chatConversationName").value = chatConversationTitle(conversation);
  $("chatConversationFolder").value = normalizeConversationFolder(
    conversation.folder,
  );
  $("chatConversationFolderList").innerHTML = chatConversationFolders()
    .map((folder) => `<option value="${escapeHtml(folder)}"></option>`)
    .join("");
  setElementMsg("chatConversationModalMsg", "");
  $("chatConversationModal").classList.remove("hidden");
}
function closeConversationEditorModal() {
  ensureConversationEditorModal();
  $("chatConversationModal").classList.add("hidden");
}
function saveConversationEditorModal() {
  const conversation = activeChatConversation();
  if (!conversation) return;
  const folderValue = String($("chatConversationFolder")?.value || "").trim();
  if (!isValidConversationFolder(folderValue)) {
    return setElementMsg(
      "chatConversationModalMsg",
      "Folder names may only use letters, numbers, spaces, - and _.",
      "error",
    );
  }
  conversation.title =
    String($("chatConversationName")?.value || "").trim() || CHAT_UNTITLED_TITLE;
  conversation.folder = normalizeConversationFolder(folderValue);
  conversation.autoNamed = !isUntitledConversationTitle(conversation.title);
  conversation.updatedAt = Date.now();
  conversation.lastUsedAt = conversation.updatedAt;
  saveChatState();
  renderChatUi();
  closeConversationEditorModal();
}
function deleteActiveConversation() {
  deleteActiveConversationAsync().catch((e) => {
    setChatMsg(e?.message || "Failed to delete the conversation.");
  });
}
async function deleteActiveConversationAsync() {
  if (chatState.busy) return;
  persistChatConversationState();
  const conversation = activeChatConversation();
  if (!conversation) return;
  if (!confirm(`Delete conversation "${chatConversationTitle(conversation)}"?`))
    return;
  cancelPendingServerChatStateSave();
  const response = await post(
    "/admin/chat-conversations",
    { action: "delete", conversation_id: conversation.id },
    `/admin/chat-conversations delete ${conversation.id}`,
  );
  const serverState =
    response?.state && typeof response.state === "object" ? response.state : null;
  const nextRows = Array.isArray(serverState?.conversations)
    ? serverState.conversations.map((row) => createChatConversation(row)).filter(Boolean)
    : [];
  chatState.revision = Math.max(0, Number(serverState?.revision || chatState.revision || 0) || 0);
  chatState.promptTemplates = Array.isArray(serverState?.promptTemplates)
    ? serverState.promptTemplates
        .map((template) => ({
          id: String(template?.id || chatConversationId()),
          name: String(template?.name || "").trim(),
          text: String(template?.text || ""),
        }))
        .filter((template) => template.name || template.text)
    : chatState.promptTemplates;
  if (nextRows.length) {
    chatState.conversations = nextRows;
    chatState.activeConversationId = String(
      serverState?.activeConversationId || nextRows[0].id,
    );
    resetChatTranscriptWindow();
  } else {
    const replacement = createChatConversation();
    chatState.conversations = [replacement];
    chatState.activeConversationId = replacement.id;
    resetChatTranscriptWindow();
    saveChatState();
  }
  syncChatStateFromActiveConversation();
  localStorage.setItem(CHAT_STATE_KEY, JSON.stringify(currentChatStatePayload()));
  renderChatUi();
  setChatMsg(`Deleted conversation "${chatConversationTitle(conversation)}".`);
}
function fallbackConversationTitle(text, attachments = []) {
  const clean = String(text || "")
    .replace(/\s+/g, " ")
    .trim();
  if (clean) {
    const words = clean.split(/\s+/).slice(0, 16).join(" ");
    return words.slice(0, 120);
  }
  if (attachments.length)
    return `Files: ${attachments[0]?.name || "attachment"}`.slice(0, 120);
  return CHAT_UNTITLED_TITLE;
}
function sanitizeConversationTitle(value) {
  return String(value || "")
    .replace(/<[^>]*>/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120);
}
function chatTitleInstruction() {
  return [
    "Answer the user's message normally first. Do not shorten, replace, or omit the answer.",
    "After the complete answer, append one final separate line in exactly this form: <title>Short descriptive title</title>.",
    "The title line is metadata only. Never return only the title line. Keep the title under 10 words.",
  ].join(" ");
}
function extractChatTitleMarker(text) {
  const raw = String(text || "");
  const match = raw.match(/(?:\r?\n)?[ \t]*<title>([^<\r\n]{1,160})<\/title>[ \t\r\n]*$/i);
  if (!match) return { text: raw, title: "" };
  const stripped = raw.slice(0, match.index).trimEnd();
  return {
    text: stripped,
    title: sanitizeConversationTitle(match[1]),
  };
}
function applyConversationTitle(conversationId, title, fallbackText = "", attachments = []) {
  const conversation = chatConversations().find((item) => item.id === conversationId);
  if (!conversation || conversation.autoNamed || chatConversationTitle(conversation) !== CHAT_UNTITLED_TITLE)
    return false;
  const resolved = sanitizeConversationTitle(title) || fallbackConversationTitle(fallbackText, attachments);
  conversation.title = resolved || CHAT_UNTITLED_TITLE;
  conversation.autoNamed = chatConversationTitle(conversation) !== CHAT_UNTITLED_TITLE;
  conversation.updatedAt = Date.now();
  conversation.lastUsedAt = conversation.updatedAt;
  saveChatState();
  renderChatUi();
  return conversation.autoNamed;
}
function extractAdminChatText(payload) {
  const response = payload?.response || {};
  const choice = Array.isArray(response.choices) ? response.choices[0] : null;
  if (choice?.message?.content) return String(choice.message.content);
  if (choice?.text) return String(choice.text);
  return "";
}
function parseConversationMetadataResult(text, fallbackTitleText, attachments = []) {
  const raw = String(text || "").trim();
  if (!raw)
    return {
      title: fallbackConversationTitle(fallbackTitleText, attachments),
      summary: "",
    };
  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidate = fenced ? fenced[1] : raw;
  try {
    const parsed = JSON.parse(candidate);
    return {
      title:
        String(parsed.title || "").trim() ||
        fallbackConversationTitle(fallbackTitleText, attachments),
      summary: String(parsed.summary || "").trim(),
    };
  } catch (e) {
    return {
      title:
        raw
          .replace(/\s+/g, " ")
          .split(/[.\n]/)[0]
          .trim()
          .slice(0, 48) || fallbackConversationTitle(fallbackTitleText, attachments),
      summary: raw.replace(/\s+/g, " ").trim().slice(0, 220),
    };
  }
}
async function maybeAutoNameConversation(conversationId) {
  const conversation = chatConversations().find((item) => item.id === conversationId);
  const runtime = activeChatRuntime();
  if (
    !conversation ||
    !runtime ||
    conversation.autoNamed ||
    chatConversationTitle(conversation) !== CHAT_UNTITLED_TITLE
  )
    return;
  const firstUser = (conversation.messages || []).find((item) => item.role === "user");
  const firstAssistant = (conversation.messages || []).find(
    (item) => item.role === "assistant",
  );
  if (!firstUser || !firstAssistant) return;
  try {
    const response = await fetch("/admin/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        instance_id: runtime.id || runtime.instance_id,
        mode: runtime.selector || runtime.mode,
        model: runtime.served_model_name || runtime.model_id,
        api_preset: "",
        params: { temperature: 0.2, top_p: 0.8, max_tokens: 220 },
        messages: [
          {
            role: "system",
            content:
              'Return only JSON with keys "title" and "summary". The title must stay under 8 words. The summary must be one short sentence describing the conversation purpose.',
          },
          {
            role: "user",
            content: `User message:\n${firstUser.text || ""}\n\nAssistant reply:\n${firstAssistant.text || ""}`,
          },
        ],
      }),
    });
    const payload = await response.json();
    const parsed = parseConversationMetadataResult(
      response.ok && payload.ok ? extractAdminChatText(payload) : "",
      firstUser.text || "",
      chatMessageAttachments(firstUser),
    );
    conversation.title = parsed.title;
    conversation.summary = parsed.summary || conversation.summary || "";
  } catch (e) {
    conversation.title = fallbackConversationTitle(
      firstUser.text || "",
      chatMessageAttachments(firstUser),
    );
  }
  conversation.autoNamed = chatConversationTitle(conversation) !== CHAT_UNTITLED_TITLE;
  conversation.updatedAt = Date.now();
  conversation.lastUsedAt = conversation.updatedAt;
  if (conversation.id === chatState.activeConversationId)
    syncChatStateFromConversation(conversation);
  saveChatState();
  renderChatUi();
}
function parseContinuedConversationInfo(title) {
  const text = chatConversationTitle({ title });
  const match = text.match(/^(.*?)(?:\s+\(continued(?:\s+(\d+))?\))$/i);
  if (!match)
    return {
      baseTitle: text,
      sequence: 1,
    };
  return {
    baseTitle: String(match[1] || "").trim() || CHAT_UNTITLED_TITLE,
    sequence: Math.max(1, Number(match[2] || 2) || 2),
  };
}
function continuedConversationTitle(conversation) {
  const info = parseContinuedConversationInfo(chatConversationTitle(conversation));
  const nextSequence = Math.max(
    2,
    Number(conversation?.compactionSequence || info.sequence || 1) + 1,
  );
  return `${info.baseTitle} (continued ${nextSequence})`;
}
function currentChatContextLimit(runtime) {
  const preset = chatApiPresetOptions().find(
    (item) => String(item?.name || "") === String(chatState.apiPresetName || ""),
  );
  const runtimeLimit = Number(runtime?.ctx_size_tokens || 0);
  const presetLimit = Number(preset?.params?.truncate_prompt_tokens || 0);
  const limits = [runtimeLimit, presetLimit].filter(
    (value) => Number.isFinite(value) && value > 0,
  );
  return limits.length ? Math.min(...limits) : 0;
}
function estimateTextTokenCount(text) {
  const clean = String(text || "").trim();
  if (!clean) return 0;
  return Math.max(1, Math.ceil(clean.length / 4));
}
function estimateAttachmentTokenCost(attachment) {
  if (!attachment) return 0;
  if (attachment.kind === "image") return 256;
  return estimateTextTokenCount(chatAttachmentTextBlock(attachment)) + 8;
}
function estimateMessageTokenCost(message) {
  let total = estimateTextTokenCount(message?.text || "") + 12;
  chatMessageAttachments(message).forEach((attachment) => {
    total += estimateAttachmentTokenCost(attachment);
  });
  if (message?.role === "assistant") {
    total += estimateTextTokenCount(chatMessageThinkingView(message).reasoningText);
  }
  return total;
}
function estimatedConversationTokenBaseline(messages = []) {
  return (messages || []).reduce(
    (sum, message) => sum + estimateMessageTokenCost(message),
    0,
  );
}
function measuredConversationTokenBaseline(runtime, conversation) {
  const limit = currentChatContextLimit(runtime);
  const measuredInput = Number(
    conversation?.lastInputTokens ??
      runtime?.last_input_tokens ??
      runtime?.last_total_tokens ??
      0,
  );
  const measuredOutput = Number(
    conversation?.lastOutputTokens ??
      runtime?.last_output_tokens ??
      0,
  );
  const measuredTotal = Number(
    conversation?.lastTotalTokens ??
      runtime?.last_total_tokens ??
      0,
  );
  const estimatedBaseline = estimatedConversationTokenBaseline(
    conversation?.messages || chatState.messages || [],
  );
  const baselineTokens = Math.max(
    measuredTotal || 0,
    measuredInput + measuredOutput,
    estimatedBaseline,
  );
  const kvUsage = Number(
    conversation?.lastKvCacheUsagePct ??
      runtime?.gpu_kv_cache_usage_pct ??
      0,
  );
  const tokenPct =
    limit > 0 && baselineTokens > 0 ? (baselineTokens / limit) * 100 : 0;
  return {
    baselineTokens,
    measuredPct: Math.max(
      Number.isFinite(kvUsage) && kvUsage > 0 ? kvUsage : 0,
      tokenPct,
    ),
  };
}
function buildCompactedSystemPrompt(summary, originalPrompt) {
  const parts = [
    "Context from an earlier conversation was automatically compacted. Continue seamlessly without asking the user to repeat prior details unless something is genuinely ambiguous.",
    `Compacted conversation summary:\n${String(summary || "").trim()}`,
  ];
  if (String(originalPrompt || "").trim()) {
    parts.push(`Original system prompt:\n${String(originalPrompt).trim()}`);
  }
  return parts.join("\n\n");
}
async function maybeCompactChatConversation(runtime, userMessage) {
  if (!chatState.autoCompactEnabled || !(chatState.messages || []).length) return;
  const limit = currentChatContextLimit(runtime);
  if (!limit) return;
  const baseConversation = activeChatConversation();
  const thresholdPct = clampChatCompactionThreshold(
    chatState.autoCompactThresholdPct,
  );
  const measured = measuredConversationTokenBaseline(runtime, baseConversation);
  const projectedTokens =
    measured.baselineTokens + estimateMessageTokenCost(userMessage);
  const projectedPct = Math.max(
    measured.measuredPct,
    (projectedTokens / limit) * 100,
  );
  if (projectedPct < thresholdPct) return;
  setChatMsg("Compacting conversation context before sending...");
  const summaryResponse = await fetch("/admin/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      instance_id: runtime.id || runtime.instance_id,
      mode: runtime.selector || runtime.mode,
      model: runtime.served_model_name || runtime.model_id,
      api_preset: "",
      params: { temperature: 0.2, top_p: 0.8, max_tokens: 1200 },
      messages: [
        {
          role: "system",
          content:
            "Summarize the conversation so another assistant can continue it after a context compaction. Preserve the goal, key facts, decisions, code, unresolved work, and any exact strings that must be kept.",
        },
        {
          role: "user",
          content: (chatState.messages || [])
            .map((message) => {
              const attachmentSummary = chatMessageAttachments(message)
                .map((attachment) =>
                  attachment?.kind === "image"
                    ? `[image: ${attachment?.name || "image"}]`
                    : `[file: ${attachment?.name || "attachment"}]`,
                )
                .join(" ");
              return `${String(message.role || "message").toUpperCase()}: ${message.text || ""}${attachmentSummary ? ` ${attachmentSummary}` : ""}`;
            })
            .join("\n\n"),
        },
      ],
    }),
  });
  const payload = await summaryResponse.json();
  const summary = extractAdminChatText(payload) || "Conversation summary unavailable.";
  persistChatConversationState();
  const preset = chatApiPresetOptions().find(
    (item) => String(item?.name || "") === String(chatState.apiPresetName || ""),
  );
  const nextConversation = createChatConversation({}, baseConversation);
  nextConversation.compactedFromId = String(baseConversation?.id || "");
  nextConversation.compactionSequence = Math.max(
    2,
    Number(baseConversation?.compactionSequence || 1) + 1,
  );
  nextConversation.title = continuedConversationTitle(baseConversation);
  nextConversation.autoNamed = true;
  nextConversation.summary = String(summary || "").trim();
  nextConversation.apiPresetName = "";
  nextConversation.params = preset
    ? normalizePresetParamsForChat(preset.params || {})
    : cloneChatParams(chatState.params);
  nextConversation.systemPrompt = buildCompactedSystemPrompt(
    summary,
    preset ? String(preset.system_prompt || "") : String(chatState.systemPrompt || ""),
  );
  nextConversation.messages = [];
  nextConversation.attachments = [];
  chatState.conversations = [...chatConversations(), nextConversation];
  chatState.activeConversationId = nextConversation.id;
  syncChatStateFromActiveConversation();
  saveChatState();
  renderChatUi();
}
function chatPresetKey(runtime) {
  return `${String(runtime?.id || runtime?.instance_id || "")}::${String(runtime?.selector || runtime?.mode || "")}`;
}
function activeChatPresets() {
  return runtimeStatsRows(lastStatus).filter((runtime) => runtime && runtime.running);
}
function activeChatRuntime() {
  const rows = activeChatPresets();
  if (!rows.length) return null;
  const exact = rows.find((runtime) => chatPresetKey(runtime) === chatState.presetId);
  return exact || rows[0];
}
function updateConversationRuntimeMetrics(conversation, runtime, payload = {}) {
  if (!conversation) return;
  const usage = payload?.usage || {};
  const inputTokens =
    usage.input_tokens !== undefined ? Number(usage.input_tokens || 0) : null;
  const outputTokens =
    usage.output_tokens !== undefined ? Number(usage.output_tokens || 0) : null;
  const totalTokens =
    usage.tokens !== undefined ? Number(usage.tokens || 0) : null;
  const toolCalls =
    usage.tool_calls !== undefined ? Number(usage.tool_calls || 0) : null;
  const lastTps =
    payload?.generation_tps !== undefined
      ? Number(payload.generation_tps || 0)
      : null;
  const lastTtft =
    payload?.ttft_s !== undefined ? Number(payload.ttft_s || 0) : null;
  const lastLatency =
    payload?.latency_s !== undefined ? Number(payload.latency_s || 0) : null;
  const lastStatus =
    payload?.status !== undefined ? Number(payload.status || 0) : 200;
  const lastPath = String(payload?.path || "/admin/chat-stream");
  if (inputTokens !== null) conversation.lastInputTokens = inputTokens;
  if (outputTokens !== null) conversation.lastOutputTokens = outputTokens;
  if (totalTokens !== null) conversation.lastTotalTokens = totalTokens;
  if (runtime?.ctx_size_tokens !== undefined)
    conversation.lastCtxSizeTokens = Number(runtime.ctx_size_tokens || 0);
  if (runtime?.gpu_kv_cache_usage_pct !== undefined)
    conversation.lastKvCacheUsagePct = Number(runtime.gpu_kv_cache_usage_pct || 0);
  if (lastStatus !== null) conversation.lastStatus = lastStatus;
  if (lastLatency !== null) conversation.lastLatencySeconds = lastLatency;
  if (lastTtft !== null) conversation.lastTtftSeconds = lastTtft;
  if (lastTps !== null) {
    conversation.lastTokensPerSecond = lastTps;
    conversation.lastTokensPerSecondPeak = Math.max(
      Number(conversation.lastTokensPerSecondPeak || 0),
      lastTps,
    );
  }
  if (toolCalls !== null) conversation.lastToolCalls = toolCalls;
  conversation.lastRequestPath = lastPath;
  conversation.lastRuntimeRequestAt = Date.now();
  const messages = Array.isArray(conversation.messages) ? conversation.messages : [];
  const assistantIndex = [...messages]
    .reverse()
    .findIndex((message) => String(message?.role || "") === "assistant");
  const userIndex = [...messages]
    .reverse()
    .findIndex((message) => String(message?.role || "") === "user");
  if (userIndex >= 0 && inputTokens !== null) {
    const target = messages[messages.length - 1 - userIndex];
    target.inputTokens = inputTokens;
  }
  if (assistantIndex >= 0) {
    const target = messages[messages.length - 1 - assistantIndex];
    if (outputTokens !== null) target.outputTokens = outputTokens;
    if (lastTtft !== null) target.ttftSeconds = lastTtft;
    if (lastTps !== null) {
      target.tokensPerSecond = lastTps;
      target.maxTokensPerSecond = Math.max(
        Number(target.maxTokensPerSecond || 0),
        lastTps,
      );
    }
  }
  if (conversation?.id === chatState.activeConversationId) {
    const activeMessages = Array.isArray(chatState.messages) ? chatState.messages : [];
    const activeAssistantIndex = [...activeMessages]
      .reverse()
      .findIndex((message) => String(message?.role || "") === "assistant");
    const activeUserIndex = [...activeMessages]
      .reverse()
      .findIndex((message) => String(message?.role || "") === "user");
    if (activeUserIndex >= 0 && inputTokens !== null) {
      activeMessages[activeMessages.length - 1 - activeUserIndex].inputTokens = inputTokens;
    }
    if (activeAssistantIndex >= 0) {
      const target = activeMessages[activeMessages.length - 1 - activeAssistantIndex];
      if (outputTokens !== null) target.outputTokens = outputTokens;
      if (lastTtft !== null) target.ttftSeconds = lastTtft;
      if (lastTps !== null) {
        target.tokensPerSecond = lastTps;
        target.maxTokensPerSecond = Math.max(
          Number(target.maxTokensPerSecond || 0),
          lastTps,
        );
      }
    }
    syncActiveConversationFromChatState();
    saveChatState();
  }
}
function setChatMsg(text, tone = "warning") {
  setElementMsg("chatMsg", text || "", tone);
}
function toggleChatOptionsMenu(force = null) {
  chatOptionsMenuOpen = force === null ? !chatOptionsMenuOpen : !!force;
  if ($("chatOptionsMenu"))
    $("chatOptionsMenu").classList.toggle("hidden", !chatOptionsMenuOpen);
}
function openChatSettingsPanel() {
  toggleChatOptionsMenu(false);
  openChatSettingsModal();
}
function chatTemplateId() {
  return `chat-template-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
function normalizePresetParamsForChat(params = {}) {
  const normalized = {
    ...defaultChatParams(),
    temperature:
      params.temperature !== undefined ? String(params.temperature) : "",
    top_p: params.top_p !== undefined ? String(params.top_p) : "",
    top_k: params.top_k !== undefined ? String(params.top_k) : "",
    min_p: params.min_p !== undefined ? String(params.min_p) : "",
    repetition_penalty:
      params.repetition_penalty !== undefined
        ? String(params.repetition_penalty)
        : "",
    presence_penalty:
      params.presence_penalty !== undefined
        ? String(params.presence_penalty)
        : "",
    frequency_penalty:
      params.frequency_penalty !== undefined
        ? String(params.frequency_penalty)
        : "",
    max_tokens:
      params.max_tokens !== undefined
        ? String(params.max_tokens)
        : params.max_completion_tokens !== undefined
          ? String(params.max_completion_tokens)
          : "",
    seed: params.seed !== undefined ? String(params.seed) : "",
  };
  const template = params.chat_template_kwargs || {};
  normalized.enable_thinking = !!template.enable_thinking;
  normalized.preserve_thinking = !!template.preserve_thinking;
  return normalized;
}
function ensureChatSettingsModal() {
  if ($("chatSettingsModal")) return;
  const modal = document.createElement("div");
  modal.id = "chatSettingsModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card chat-settings-modal-card" role="dialog" aria-modal="true" aria-labelledby="chatSettingsTitle"><div class="panel-head"><h2 id="chatSettingsTitle">Chat Settings</h2><button class="iconbtn danger-iconbtn" title="Close" aria-label="Close" onclick="closeChatSettingsModal()">${svgIcon("close")}</button></div><div class="preset-help" id="chatSettingsPresetHint"></div><div class="chat-settings-grid"><label class="chat-settings-span-2">System Prompt<textarea id="chatSystemPrompt" placeholder="Optional system prompt for this conversation"></textarea></label><div class="chat-settings-span-2"><div class="chat-settings-template-row"><input id="chatPromptTemplateName" class="chat-settings-template-name" placeholder="Template name" /><select id="chatPromptTemplateSelect" class="chat-settings-template-select" aria-label="Choose template"></select><div class="chat-settings-template-actions"><button class="btn blue" onclick="loadChatPromptTemplate()">Load</button><button class="btn green" onclick="saveChatPromptTemplate()">Save Template</button><button class="btn red" onclick="deleteChatPromptTemplate()">Delete</button></div></div><div class="chat-settings-note chat-settings-template-note">Templates are stored locally in this browser so you can save and reuse system prompts.</div><hr class="chat-settings-rule" /></div><label>Temperature<input id="chatTemperature" type="number" step="0.01" min="0" max="2" /></label><label>Top P<input id="chatTopP" type="number" step="0.01" min="0" max="1" /></label><label>Top K<input id="chatTopK" type="number" step="1" min="0" /></label><label>Min P<input id="chatMinP" type="number" step="0.01" min="0" max="1" /></label><label>Repeat Penalty<input id="chatRepetitionPenalty" type="number" step="0.01" min="0" max="4" /></label><label>Presence Penalty<input id="chatPresencePenalty" type="number" step="0.01" min="-2" max="2" /></label><label>Frequency Penalty<input id="chatFrequencyPenalty" type="number" step="0.01" min="-2" max="2" /></label><label>Max Tokens<input id="chatMaxTokens" type="number" step="1" min="1" /></label><label>Enable Thinking<select id="chatEnableThinking"><option value="false">Off</option><option value="true">On</option></select></label><label>Preserve Thinking<select id="chatPreserveThinking"><option value="false">Off</option><option value="true">On</option></select></label><div class="chat-settings-span-2"><hr class="chat-settings-rule" /><div class="chat-settings-compact-block"><div class="chat-settings-toggle-row"><label class="toggle-switch"><input id="chatAutoCompactEnabled" type="checkbox" onchange="updateChatCompactionThresholdLabel()" /><span class="toggle-switch-track"></span></label><span class="chat-settings-compact-title">Automatically compact context when nearing max</span></div><div class="chat-threshold-row"><span class="chat-settings-compact-threshold-label">Threshold:</span><input id="chatAutoCompactThreshold" type="range" min="${CHAT_MIN_COMPACTION_THRESHOLD}" max="${CHAT_MAX_COMPACTION_THRESHOLD}" step="1" value="${CHAT_MAX_COMPACTION_THRESHOLD}" oninput="updateChatCompactionThresholdLabel()" /><output id="chatAutoCompactThresholdValue">${CHAT_MAX_COMPACTION_THRESHOLD}%</output></div><div class="chat-settings-note chat-settings-compact-description">If about to run out of context, summarize the current chat and automatically recall the summary in a new conversation.</div></div></div></div><div class="preset-form-actions"><button class="btn blue" onclick="closeChatSettingsModal()">Cancel</button><button class="btn green" onclick="applyChatSettingsModal()">Apply</button></div><div class="msg" id="chatSettingsMsg"></div></div>`;
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeChatSettingsModal();
  });
  document.body.appendChild(modal);
}
function setChatSettingsMsg(text, tone = "warning") {
  setElementMsg("chatSettingsMsg", text || "", tone);
}
function renderChatPromptTemplateOptions(selectedId = "") {
  const select = $("chatPromptTemplateSelect");
  if (!select) return;
  const rows = Array.isArray(chatState.promptTemplates)
    ? [...chatState.promptTemplates].sort((left, right) =>
        String(left?.name || "").localeCompare(String(right?.name || "")),
      )
    : [];
  select.innerHTML = `<option value="">Choose Template</option>${rows
    .map(
      (template) =>
        `<option value="${escapeHtml(template.id)}" ${
          template.id === selectedId ? "selected" : ""
        }>${escapeHtml(template.name || "Template")}</option>`,
    )
    .join("")}`;
}
function updateChatCompactionThresholdLabel() {
  const slider = $("chatAutoCompactThreshold");
  const output = $("chatAutoCompactThresholdValue");
  const enabled = !!$("chatAutoCompactEnabled")?.checked;
  if (slider) slider.disabled = !enabled;
  if (output && slider)
    output.value = `${clampChatCompactionThreshold(slider.value)}%`;
}
function loadChatPromptTemplate() {
  const template = (chatState.promptTemplates || []).find(
    (item) => item.id === $("chatPromptTemplateSelect")?.value,
  );
  if (!template) return setChatSettingsMsg("Select a prompt template first.");
  $("chatPromptTemplateName").value = template.name || "";
  $("chatSystemPrompt").value = template.text || "";
  setChatSettingsMsg(`Loaded template "${template.name}".`);
}
function saveChatPromptTemplate() {
  const name = String($("chatPromptTemplateName")?.value || "").trim();
  const text = String($("chatSystemPrompt")?.value || "");
  if (!name) return setChatSettingsMsg("Template name is required.", "error");
  if (!text.trim())
    return setChatSettingsMsg(
      "Template text cannot be empty.",
      "error",
    );
  const existing = (chatState.promptTemplates || []).find(
    (item) => String(item.name || "").toLowerCase() === name.toLowerCase(),
  );
  if (existing) {
    existing.name = name;
    existing.text = text;
    renderChatPromptTemplateOptions(existing.id);
  } else {
    const template = { id: chatTemplateId(), name, text };
    chatState.promptTemplates = [...(chatState.promptTemplates || []), template];
    renderChatPromptTemplateOptions(template.id);
  }
  saveChatState();
  setChatSettingsMsg(`Saved template "${name}".`);
}
function deleteChatPromptTemplate() {
  const template = (chatState.promptTemplates || []).find(
    (item) => item.id === $("chatPromptTemplateSelect")?.value,
  );
  if (!template) return setChatSettingsMsg("Select a template to delete.");
  if (!confirm(`Delete prompt template "${template.name}"?`)) return;
  chatState.promptTemplates = (chatState.promptTemplates || []).filter(
    (item) => item.id !== template.id,
  );
  saveChatState();
  renderChatPromptTemplateOptions();
  $("chatPromptTemplateName").value = "";
  setChatSettingsMsg(`Deleted template "${template.name}".`);
}
function populateChatSettingsInputs(values = chatState.params) {
  ensureChatSettingsModal();
  const preset = chatApiPresetOptions().find(
    (item) => String(item?.name || "") === String(chatState.apiPresetName || ""),
  );
  const sourceParams = preset
    ? {
        ...defaultChatParams(),
        ...normalizePresetParamsForChat(preset.params || {}),
      }
    : { ...defaultChatParams(), ...(values || {}) };
  chatSettingsDraft = { usingPreset: !!preset };
  $("chatSettingsPresetHint").innerHTML = preset
    ? `Showing settings from API Preset <code>${escapeHtml(preset.name || "Preset")}</code>. Applying saves a Direct copy for this conversation and switches the selector to <code>Direct</code>.`
    : `These Direct settings are stored locally with this conversation.`;
  $("chatSystemPrompt").value = preset
    ? String(preset.system_prompt || "")
    : String(chatState.systemPrompt || "");
  $("chatTemperature").value = sourceParams.temperature || "";
  $("chatTopP").value = sourceParams.top_p || "";
  $("chatTopK").value = sourceParams.top_k || "";
  $("chatMinP").value = sourceParams.min_p || "";
  $("chatRepetitionPenalty").value = sourceParams.repetition_penalty || "";
  $("chatPresencePenalty").value = sourceParams.presence_penalty || "";
  $("chatFrequencyPenalty").value = sourceParams.frequency_penalty || "";
  $("chatMaxTokens").value = sourceParams.max_tokens || "";
  $("chatEnableThinking").value = sourceParams.enable_thinking
    ? "true"
    : "false";
  $("chatPreserveThinking").value = sourceParams.preserve_thinking
    ? "true"
    : "false";
  $("chatAutoCompactEnabled").checked = chatState.autoCompactEnabled !== false;
  $("chatAutoCompactThreshold").value = clampChatCompactionThreshold(
    chatState.autoCompactThresholdPct,
  );
  $("chatPromptTemplateName").value = "";
  renderChatPromptTemplateOptions();
  updateChatCompactionThresholdLabel();
}
function openChatSettingsModal() {
  populateChatSettingsInputs(chatState.params);
  setChatSettingsMsg("");
  $("chatSettingsModal").classList.remove("hidden");
}
function closeChatSettingsModal() {
  ensureChatSettingsModal();
  $("chatSettingsModal").classList.add("hidden");
  chatSettingsDraft = null;
}
function validateChatSettingNumber(label, raw, { min = null, max = null, integer = false } = {}) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const value = integer ? Number.parseInt(text, 10) : Number(text);
  if (!Number.isFinite(value)) throw new Error(`${label} must be a valid number.`);
  if (integer && !Number.isInteger(value)) throw new Error(`${label} must be a whole number.`);
  if (min !== null && value < min) throw new Error(`${label} must be at least ${min}.`);
  if (max !== null && value > max) throw new Error(`${label} must be at most ${max}.`);
  return integer ? String(value) : String(value);
}
function applyChatSettingsModal() {
  try {
    chatState.params = {
      ...chatState.params,
      temperature: validateChatSettingNumber("Temperature", $("chatTemperature").value, { min: 0, max: 2 }),
      top_p: validateChatSettingNumber("Top P", $("chatTopP").value, { min: 0, max: 1 }),
      top_k: validateChatSettingNumber("Top K", $("chatTopK").value, { min: 0, integer: true }),
      min_p: validateChatSettingNumber("Min P", $("chatMinP").value, { min: 0, max: 1 }),
      repetition_penalty: validateChatSettingNumber("Repeat Penalty", $("chatRepetitionPenalty").value, { min: 0, max: 4 }),
      presence_penalty: validateChatSettingNumber("Presence Penalty", $("chatPresencePenalty").value, { min: -2, max: 2 }),
      frequency_penalty: validateChatSettingNumber("Frequency Penalty", $("chatFrequencyPenalty").value, { min: -2, max: 2 }),
      max_tokens: validateChatSettingNumber("Max Tokens", $("chatMaxTokens").value, { min: 1, integer: true }),
      enable_thinking: $("chatEnableThinking").value === "true",
      preserve_thinking: $("chatPreserveThinking").value === "true",
    };
    chatState.systemPrompt = String($("chatSystemPrompt").value || "");
    chatState.autoCompactEnabled = !!$("chatAutoCompactEnabled").checked;
    chatState.autoCompactThresholdPct = clampChatCompactionThreshold(
      $("chatAutoCompactThreshold").value,
    );
    if (chatSettingsDraft?.usingPreset) chatState.apiPresetName = "";
    persistChatConversationState();
    setChatSettingsMsg("");
    closeChatSettingsModal();
    renderChatUi();
  } catch (e) {
    setChatSettingsMsg(String(e || ""), "error");
  }
}
function ensureMcpManagerModal() {
  if ($("mcpManagerModal")) return;
  const modal = document.createElement("div");
  modal.id = "mcpManagerModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card" role="dialog" aria-modal="true" aria-labelledby="mcpManagerTitle"><div class="panel-head"><h2 id="mcpManagerTitle">MCP Servers</h2><button class="iconbtn danger-iconbtn" title="Close" aria-label="Close" onclick="closeMcpManagerModal()">${svgIcon("close")}</button></div><div class="preset-help">Add either a local stdio command or a remote MCP URL here. Commands launch a server on this machine; URLs connect to an already-running MCP endpoint such as <code>https://example.com/mcp</code>. New servers are only saved after the control layer can initialize and list their tools.</div><div class="formgrid"><label>Server Name<input id="mcpServerName" placeholder="filesystem" /></label><label>Command or URL<input id="mcpServerCommand" placeholder="npx -y @modelcontextprotocol/server-filesystem /path or https://host/mcp" /></label></div><div class="preset-form-actions"><button class="btn green" onclick="saveMcpServerFromForm()">Save Server</button></div><div class="msg" id="mcpManagerMsg"></div><div class="panel" style="margin-top:12px"><h2>Configured MCP Servers</h2><div id="mcpServerList" class="api-grid"></div></div></div>`;
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeMcpManagerModal();
  });
  document.body.appendChild(modal);
}
function setMcpManagerMsg(text, tone = "warning") {
  setElementMsg("mcpManagerMsg", text || "", tone);
}
function resetMcpServerForm() {
  mcpManagerState.editingId = "";
  if ($("mcpServerName")) $("mcpServerName").value = "";
  if ($("mcpServerCommand")) $("mcpServerCommand").value = "";
  setMcpManagerMsg("");
}
function renderMcpServerList() {
  const host = $("mcpServerList");
  if (!host) return;
  const rows = Array.isArray(mcpManagerState.servers) ? mcpManagerState.servers : [];
  host.innerHTML =
    rows
      .map((server) => {
        const tools = Array.isArray(server.tools) ? server.tools : [];
        const toolText = tools.length
          ? tools.map((tool) => tool.name).join(", ")
          : server.status === "connected"
            ? "no tools reported"
            : server.error || "not connected";
        return `<div class="api-card"><div class="api-card-head"><h3>${escapeHtml(server.name || server.id)}<br><span class="label">${escapeHtml(server.status || "unknown")} · ${escapeHtml(server.transport || "stdio")} · ${server.enabled ? "enabled" : "disabled"}</span></h3><span class="preset-actions"><button class="iconbtn" title="Edit" onclick="editMcpServer('${escapeJs(server.id)}')">${svgIcon("edit")}</button><button class="iconbtn" title="Delete" onclick="deleteMcpServer('${escapeJs(server.id)}')">${svgIcon("delete")}</button></span></div><p>${escapeHtml(server.command || "")}</p><p class="label">tools: ${escapeHtml(toolText)}</p>${server.error ? `<p class="label">${escapeHtml(server.error)}</p>` : ""}<div class="variant-actions"><button class="btn ${server.enabled ? "amber" : "green"}" onclick="toggleMcpServer('${escapeJs(server.id)}', ${server.enabled ? "false" : "true"})">${server.enabled ? "Disable" : "Enable"}</button></div></div>`;
      })
      .join("") || '<div class="value">No MCP servers configured yet.</div>';
}
async function loadMcpServers() {
  ensureMcpManagerModal();
  const response = await fetch("/admin/mcp");
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || "Failed to load MCP servers");
  mcpManagerState.servers = Array.isArray(payload.servers) ? payload.servers : [];
  renderMcpServerList();
}
function editMcpServer(serverId) {
  const row = (mcpManagerState.servers || []).find((server) => server.id === serverId);
  if (!row) return;
  mcpManagerState.editingId = serverId;
  $("mcpServerName").value = row.name || "";
  $("mcpServerCommand").value = row.command || "";
  setMcpManagerMsg(`Editing MCP server "${row.name || row.id}".`);
}
async function saveMcpServerFromForm() {
  try {
    const response = await fetch("/admin/mcp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "save",
        id: mcpManagerState.editingId || "",
        name: $("mcpServerName")?.value || "",
        command: $("mcpServerCommand")?.value || "",
        enabled: true,
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || "Failed to save MCP server");
    mcpManagerState.servers = Array.isArray(payload.servers) ? payload.servers : [];
    resetMcpServerForm();
    renderMcpServerList();
    setMcpManagerMsg("Saved MCP server.");
  } catch (e) {
    setMcpManagerMsg(String(e || ""), "error");
  }
}
async function deleteMcpServer(serverId) {
  if (!confirm(`Delete MCP server ${serverId}?`)) return;
  const response = await fetch("/admin/mcp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "delete", id: serverId }),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) return setMcpManagerMsg(payload.error || "Failed to delete MCP server");
  mcpManagerState.servers = Array.isArray(payload.servers) ? payload.servers : [];
  renderMcpServerList();
}
async function toggleMcpServer(serverId, enabled) {
  const response = await fetch("/admin/mcp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "toggle", id: serverId, enabled: !!enabled }),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok)
    return setMcpManagerMsg(payload.error || "Failed to toggle MCP server", "error");
  mcpManagerState.servers = Array.isArray(payload.servers) ? payload.servers : [];
  renderMcpServerList();
  setMcpManagerMsg(enabled ? "Enabled MCP server." : "Disabled MCP server.");
}
async function openMcpManagerModal() {
  toggleChatOptionsMenu(false);
  ensureMcpManagerModal();
  $("mcpManagerModal").classList.remove("hidden");
  resetMcpServerForm();
  setMcpManagerMsg("Loading MCP servers...");
  try {
    await loadMcpServers();
    setMcpManagerMsg("");
  } catch (e) {
    setMcpManagerMsg(String(e || ""), "error");
  }
}
function closeMcpManagerModal() {
  ensureMcpManagerModal();
  $("mcpManagerModal").classList.add("hidden");
}
function openChatTab() {
  activateTab("chat", false);
}
function selectChatPreset(value) {
  chatState.presetId = String(value || "");
  persistChatConversationState();
  renderChatUi();
}
function selectChatApiPreset(value) {
  chatState.apiPresetName = String(value || "");
  persistChatConversationState();
  renderChatUi();
}
function handleChatInputResize() {
  const box = $("chatInput");
  if (!box) return;
  box.style.height = "auto";
  const lineHeight = 22;
  const minHeight = lineHeight * 4;
  const maxHeight = lineHeight * 8;
  box.style.height = `${Math.max(minHeight, Math.min(maxHeight, box.scrollHeight))}px`;
}
function syncChatTranscriptHeight() {
  const transcript = $("chatTranscript");
  const composer = document.querySelector(".chat-input-wrap");
  const statsCard = $("chatStatsCard");
  if (!transcript || !composer || !statsCard) return;
  const customHeight = Number(chatState.transcriptHeightPx || 0);
  if (customHeight >= 260) {
    transcript.style.height = `${customHeight}px`;
    transcript.style.maxHeight = "none";
    return;
  }
  const top = transcript.getBoundingClientRect().top;
  const composerHeight = composer.getBoundingClientRect().height;
  const statsPreviewHeight = Math.min(statsCard.getBoundingClientRect().height || 0, 48);
  const viewportPadding = window.innerWidth <= 720 ? 16 : 12;
  const available = Math.max(
    260,
    Math.floor(window.innerHeight - top - composerHeight - statsPreviewHeight - viewportPadding),
  );
  transcript.style.height = `${available}px`;
  transcript.style.maxHeight = "none";
}
function persistChatTranscriptHeightFromDom() {
  const transcript = $("chatTranscript");
  if (!transcript) return;
  const height = Math.round(transcript.getBoundingClientRect().height || 0);
  if (height < 260) return;
  if (Math.abs(height - Number(chatState.transcriptHeightPx || 0)) < 2) return;
  chatState.transcriptHeightPx = height;
  persistChatConversationState();
}
function ensureChatTranscriptResizePersistence() {
  const transcript = $("chatTranscript");
  if (!transcript || transcript.__clubResizePersistence) return;
  transcript.__clubResizePersistence = true;
  transcript.addEventListener("mouseup", persistChatTranscriptHeightFromDom);
  transcript.addEventListener("touchend", persistChatTranscriptHeightFromDom);
}
function scheduleChatTranscriptHeightSync() {
  window.requestAnimationFrame(() => {
    ensureChatTranscriptResizePersistence();
    syncChatTranscriptHeight();
  });
}
window.addEventListener("resize", scheduleChatTranscriptHeightSync);
function handleChatInputChange() {
  handleChatInputResize();
  const runtime = activeChatRuntime();
  const hasDraft =
    !!String($("chatInput")?.value || "").trim() ||
    !!(chatState.attachments || []).length;
  if ($("chatSendBtn"))
    $("chatSendBtn").disabled = !runtime || (!chatState.busy && !hasDraft);
}
function handleChatInputKeydown(event) {
  if (!event || event.key !== "Enter" || !(event.ctrlKey || event.metaKey)) return;
  event.preventDefault();
  sendChatMessage();
}
function ensureChatInputBindings() {
  const input = $("chatInput");
  if (!input || input.__clubKeyBinding) return;
  input.__clubKeyBinding = true;
  input.addEventListener("keydown", handleChatInputKeydown);
}
function renderChatPresetSelector() {
  const select = $("chatPresetSelect");
  if (!select) return;
  const rows = activeChatPresets();
  if (!rows.length) {
    select.innerHTML = `<option value="">No active presets</option>`;
    select.disabled = true;
    chatState.presetId = "";
    return;
  }
  if (!rows.some((runtime) => chatPresetKey(runtime) === chatState.presetId)) {
    chatState.presetId = chatPresetKey(rows[0]);
  }
  select.disabled = false;
  const html = rows
    .map((runtime) => {
      const key = chatPresetKey(runtime);
      const label = `${variantDisplayLabel({ upstream_tag: runtime.selector || runtime.mode })} | ${runtime.id || runtime.instance_id}`;
      return `<option value="${escapeHtml(key)}" ${key === chatState.presetId ? "selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
  setSelectOptions(select, html);
  if (chatState.presetId && [...select.options].some((option) => option.value === chatState.presetId)) {
    select.value = chatState.presetId;
  }
}
function chatApiPresetOptions() {
  const presetCatalog = lastStatus?.presets || {};
  return [...(presetCatalog.defaults || []), ...(presetCatalog.custom || [])];
}
function renderChatApiPresetSelector() {
  const select = $("chatApiPresetSelect");
  if (!select) return;
  const presets = chatApiPresetOptions();
  const valid = new Set(presets.map((preset) => String(preset?.name || "")));
  if (chatState.apiPresetName && !valid.has(chatState.apiPresetName)) {
    chatState.apiPresetName = "";
  }
  const html = `<option value="" ${!chatState.apiPresetName ? "selected" : ""}>Direct</option>${presets
    .map((preset) => {
      const name = String(preset?.name || "");
      const label = `${name}${preset?.locked ? " - default" : ""}`;
      return `<option value="${escapeHtml(name)}" ${name === chatState.apiPresetName ? "selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("")}`;
  setSelectOptions(select, html);
  select.value = chatState.apiPresetName || "";
}
function chatRuntimeSupportsVision(runtime) {
  return !!runtime && !!String(runtime.vision || "").trim();
}
function chatAttachmentId() {
  return `chat-att-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
function chatAttachmentKindClass(attachment) {
  return attachment?.kind === "image" ? "chat-attachment-image" : "chat-attachment-text";
}
function renderChatAttachments() {
  const host = $("chatAttachmentRow");
  if (!host) return;
  host.innerHTML = (chatState.attachments || [])
    .map(
      (attachment, index) =>
        `<div class="chat-attachment-pill ${chatAttachmentKindClass(attachment)}"><button class="chat-attachment-remove" title="Remove attachment" aria-label="Remove attachment" onclick="removeChatAttachment(${index})">x</button><span class="chat-attachment-name">${escapeHtml(attachment?.name || `attachment-${index + 1}`)}</span></div>`,
    )
    .join("");
}
function removeChatAttachment(index) {
  chatState.attachments = (chatState.attachments || []).filter((_, itemIndex) => itemIndex !== index);
  persistChatConversationState();
  renderChatAttachments();
}
function chatTranscriptIsNearBottom(host = $("chatTranscript")) {
  if (!host) return true;
  return host.scrollHeight - (host.scrollTop + host.clientHeight) <= 36;
}
function ensureChatTranscriptBehavior() {
  const host = $("chatTranscript");
  if (!host || host.dataset.followBound === "1") return;
  host.dataset.followBound = "1";
  host.addEventListener("scroll", () => {
    chatTranscriptAutoFollow = chatTranscriptIsNearBottom(host);
  });
  host.addEventListener("click", (event) => {
    const link = event.target?.closest?.("a[data-chat-external-link]");
    if (!link) return;
    event.preventDefault();
    openExternalLinkModal(link.getAttribute("data-chat-external-link") || link.href || "");
  });
}
function handleChatMarkdownImageError(img) {
  if (!img || img.dataset.broken === "1") return;
  img.dataset.broken = "1";
  const src = img.getAttribute("src") || "";
  if (src) brokenMarkdownImageUrls.add(src);
  const wrapper = document.createElement("template");
  wrapper.innerHTML = markdownImageFailureNote(src, img.getAttribute("alt") || "image");
  img.replaceWith(wrapper.content.firstElementChild || document.createTextNode(""));
}
function chatMessageAttachments(message) {
  if (Array.isArray(message?.attachments)) return message.attachments;
  if (Array.isArray(message?.images)) {
    return message.images.map((image) => ({
      kind: "image",
      name: image?.name || "image",
      url: image?.url || "",
    }));
  }
  return [];
}
function normalizeMarkdownUrl(url, { allowDataImage = true } = {}) {
  const raw = String(url || "").trim();
  if (!raw) return "";
  if (allowDataImage && /^data:image\//i.test(raw)) return raw;
  if (/^mailto:/i.test(raw)) return raw;
  if (/^[/?#]/.test(raw)) return raw;
  if (/^www\./i.test(raw)) return normalizeMarkdownUrl(`https://${raw}`, { allowDataImage });
  try {
    const parsed = new URL(raw, window.location.origin);
    if (!/^https?:$/i.test(parsed.protocol) && !/^blob:$/i.test(parsed.protocol))
      return "";
    return parsed.href;
  } catch (e) {
    return "";
  }
}
function markdownUrlParts(candidate) {
  let url = String(candidate || "");
  let trailing = "";
  while (url && /[),.;!?]$/.test(url) && !/\([^)]+\)$/.test(url)) {
    trailing = url.slice(-1) + trailing;
    url = url.slice(0, -1);
  }
  return { url, trailing };
}
function urlLooksLikeImage(url) {
  return /^data:image\//i.test(url) || /\.(avif|gif|jpe?g|png|svg|webp)$/i.test(url.split("?")[0]);
}
function urlLooksLikeVideo(url) {
  return /\.(mp4|m4v|mov|webm|ogv)$/i.test(url.split("?")[0]);
}
function urlLooksLikeAudio(url) {
  return /\.(mp3|wav|ogg|m4a|flac)$/i.test(url.split("?")[0]);
}
function youtubeEmbedUrl(url) {
  try {
    const parsed = new URL(url);
    if (/youtube\.com$/i.test(parsed.hostname) || /www\.youtube\.com$/i.test(parsed.hostname)) {
      const videoId = parsed.searchParams.get("v");
      if (videoId) return `https://www.youtube.com/embed/${encodeURIComponent(videoId)}`;
    }
    if (/youtu\.be$/i.test(parsed.hostname)) {
      const videoId = parsed.pathname.replace(/\//g, "").trim();
      if (videoId) return `https://www.youtube.com/embed/${encodeURIComponent(videoId)}`;
    }
  } catch (e) {}
  return "";
}
function richEmbedForUrl(url, altText = "") {
  const safeUrl = normalizeMarkdownUrl(url);
  if (!safeUrl) return "";
  if (urlLooksLikeImage(safeUrl))
    return `<div class="chat-rich-embed">${markdownImageHtml(safeUrl, altText || "image")}</div>`;
  if (urlLooksLikeVideo(safeUrl))
    return `<div class="chat-rich-embed"><video class="chat-markdown-media" controls preload="metadata" src="${escapeHtml(safeUrl)}"></video></div>`;
  if (urlLooksLikeAudio(safeUrl))
    return `<div class="chat-rich-embed"><audio class="chat-markdown-media" controls preload="metadata" src="${escapeHtml(safeUrl)}"></audio></div>`;
  const youtubeUrl = youtubeEmbedUrl(safeUrl);
  if (youtubeUrl)
    return `<div class="chat-rich-embed"><iframe class="chat-markdown-media" src="${escapeHtml(youtubeUrl)}" title="${escapeHtml(altText || "embedded media")}" loading="lazy" allowfullscreen></iframe></div>`;
  return "";
}
function applyBalancedUnderscoreFormatting(text) {
  return String(text || "")
    .replace(
      /(^|[^A-Za-z0-9])___([^\s_](?:.*?[^\s_])?)___(?=[^A-Za-z0-9]|$)/g,
      (_, prefix, body) => `${prefix}<strong><em>${body}</em></strong>`,
    )
    .replace(
      /(^|[^A-Za-z0-9])__([^\s_](?:.*?[^\s_])?)__(?=[^A-Za-z0-9]|$)/g,
      (_, prefix, body) => `${prefix}<strong>${body}</strong>`,
    )
    .replace(
      /(^|[^A-Za-z0-9])_([^\s_]+)_(?=[^A-Za-z0-9]|$)/g,
      (_, prefix, body) => `${prefix}<em>${body}</em>`,
    );
}
const latexSymbolMap = {
  alpha: "α",
  beta: "β",
  gamma: "γ",
  delta: "δ",
  epsilon: "ε",
  zeta: "ζ",
  eta: "η",
  theta: "θ",
  iota: "ι",
  kappa: "κ",
  lambda: "λ",
  mu: "μ",
  nu: "ν",
  xi: "ξ",
  pi: "π",
  rho: "ρ",
  sigma: "σ",
  tau: "τ",
  phi: "φ",
  chi: "χ",
  psi: "ψ",
  omega: "ω",
  Gamma: "Γ",
  Delta: "Δ",
  Theta: "Θ",
  Lambda: "Λ",
  Xi: "Ξ",
  Pi: "Π",
  Sigma: "Σ",
  Phi: "Φ",
  Psi: "Ψ",
  Omega: "Ω",
  times: "×",
  cdot: "·",
  div: "÷",
  pm: "±",
  mp: "∓",
  le: "≤",
  leq: "≤",
  ge: "≥",
  geq: "≥",
  neq: "≠",
  approx: "≈",
  sim: "∼",
  equiv: "≡",
  infty: "∞",
  partial: "∂",
  nabla: "∇",
  int: "∫",
  sum: "∑",
  prod: "∏",
  lim: "lim",
  sin: "sin",
  cos: "cos",
  tan: "tan",
  log: "log",
  ln: "ln",
  exp: "exp",
  to: "→",
  rightarrow: "→",
  leftarrow: "←",
  in: "∈",
  notin: "∉",
  subset: "⊂",
  subseteq: "⊆",
  cup: "∪",
  cap: "∩",
};
function findLatexGroupEnd(text, start) {
  let depth = 0;
  for (let index = start; index < text.length; index += 1) {
    const char = text[index];
    if (char === "\\") {
      index += 1;
      continue;
    }
    if (char === "{") depth += 1;
    if (char === "}") {
      depth -= 1;
      if (depth === 0) return index;
    }
  }
  return -1;
}
function readLatexArgument(text, start) {
  let index = start;
  while (/\s/.test(text[index] || "")) index += 1;
  if (text[index] === "{") {
    const end = findLatexGroupEnd(text, index);
    if (end >= 0) return { body: text.slice(index + 1, end), end: end + 1 };
  }
  const command = text.slice(index).match(/^\\[A-Za-z]+/);
  if (command) return { body: command[0], end: index + command[0].length };
  const simple = text.slice(index).match(/^[A-Za-z0-9+\-=().,]+/);
  return simple ? { body: simple[0], end: index + simple[0].length } : { body: "", end: index };
}
function renderLatexFragment(source) {
  const text = String(source || "");
  let html = "";
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === "\\") {
      const command = text.slice(index + 1).match(/^[A-Za-z]+/);
      if (command) {
        const name = command[0];
        index += name.length;
        if (name === "frac" || name === "dfrac" || name === "tfrac") {
          const numerator = readLatexArgument(text, index + 1);
          const denominator = readLatexArgument(text, numerator.end);
          html += `<span class="chat-latex-frac"><span>${renderLatexFragment(numerator.body)}</span><span>${renderLatexFragment(denominator.body)}</span></span>`;
          index = denominator.end - 1;
          continue;
        }
        if (name === "sqrt") {
          const radicand = readLatexArgument(text, index + 1);
          html += `<span class="chat-latex-root"><span class="chat-latex-root-symbol">√</span><span class="chat-latex-root-body">${renderLatexFragment(radicand.body)}</span></span>`;
          index = radicand.end - 1;
          continue;
        }
        html += latexSymbolMap[name]
          ? `<span class="chat-latex-op">${escapeHtml(latexSymbolMap[name])}</span>`
          : escapeHtml(`\\${name}`);
        continue;
      }
      html += escapeHtml(text[index + 1] || "\\");
      index += 1;
      continue;
    }
    if (char === "^" || char === "_") {
      const arg = readLatexArgument(text, index + 1);
      html += char === "^" ? `<sup>${renderLatexFragment(arg.body)}</sup>` : `<sub>${renderLatexFragment(arg.body)}</sub>`;
      index = arg.end - 1;
      continue;
    }
    if (char === "{") {
      const end = findLatexGroupEnd(text, index);
      if (end >= 0) {
        html += renderLatexFragment(text.slice(index + 1, end));
        index = end;
        continue;
      }
    }
    html += escapeHtml(char);
  }
  return html.replace(/\s+/g, " ");
}
function renderMarkdownMathToken(body, block = false) {
  const source = String(body || "").trim();
  const text = renderLatexFragment(source);
  return block
    ? `<span class="chat-math chat-math-block">${text}</span>`
    : `<span class="chat-math">${text}</span>`;
}
function renderMarkdownInline(text, references = {}) {
  const tokens = [];
  const stash = (html) => {
    const token = `\uE000CHATMDTOKEN${tokens.length}\uE000`;
    tokens.push(html);
    return token;
  };
  let value = String(text || "");
  value = value.replace(/\\([\\`*_{}\[\]()#+\-.!|>~$])/g, (_, char) =>
    stash(escapeHtml(char)),
  );
  value = value.replace(/\$\$([\s\S]+?)\$\$/g, (_, body) =>
    stash(renderMarkdownMathToken(body, true)),
  );
  value = value.replace(/(^|[^\\$])\$([^\n$]+?)\$/g, (_, prefix, body) =>
    `${prefix}${stash(renderMarkdownMathToken(body))}`,
  );
  value = value.replace(/`([^`]+)`/g, (_, code) =>
    stash(`<code>${escapeHtml(code)}</code>`),
  );
  value = value.replace(/<kbd>([\s\S]*?)<\/kbd>/gi, (_, keys) =>
    stash(`<kbd>${escapeHtml(keys)}</kbd>`),
  );
  value = value.replace(/<(u|sub|sup)>([\s\S]*?)<\/\1>/gi, (_, tag, body) =>
    stash(`<${tag.toLowerCase()}>${escapeHtml(body)}</${tag.toLowerCase()}>`),
  );
  value = value.replace(
    /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g,
    (_, altText, url) =>
      stash(markdownImageHtml(url, altText || "image")),
  );
  value = value.replace(
    /\[([^\]]+)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g,
    (_, label, url) => {
      const safeUrl = normalizeMarkdownUrl(url, { allowDataImage: false });
      if (!safeUrl) return escapeHtml(label);
      const externalAttrs = isInternalMarkdownLink(safeUrl)
        ? ""
        : ` target="_blank" rel="noreferrer noopener" data-chat-external-link="${escapeHtml(safeUrl)}"`;
      return stash(
        `<a href="${escapeHtml(safeUrl)}"${externalAttrs}>${escapeHtml(label)}</a>${richEmbedForUrl(
          safeUrl,
          label,
        )}`,
      );
    },
  );
  value = value.replace(/\[([^\]]+)\]\[([^\]]*)\]/g, (_, label, refName) => {
    const key = normalizeReferenceKey(refName || label);
    const target = references[key];
    if (!target) return escapeHtml(label);
    const safeUrl = normalizeMarkdownUrl(target.url, { allowDataImage: false });
    if (!safeUrl) return escapeHtml(label);
    const externalAttrs = isInternalMarkdownLink(safeUrl)
      ? ""
      : ` target="_blank" rel="noreferrer noopener" data-chat-external-link="${escapeHtml(safeUrl)}"`;
    return stash(`<a href="${escapeHtml(safeUrl)}"${externalAttrs}>${escapeHtml(label)}</a>${richEmbedForUrl(safeUrl, label)}`);
  });
  value = value.replace(/\[\^([^\]]+)\]/g, (_, refName) => {
    const key = normalizeReferenceKey(refName);
    const label = escapeHtml(refName);
    return stash(
      `<sup class="chat-footnote-ref"><a href="#chat-footnote-${escapeHtml(key)}">[${label}]</a></sup>`,
    );
  });
  value = value.replace(
    /(^|[\s(])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?=$|[\s).,;!?])/gi,
    (_, prefix, email) => {
      const safeUrl = normalizeMarkdownUrl(`mailto:${email}`, { allowDataImage: false });
      return `${prefix}${stash(
        `<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noreferrer noopener" data-chat-external-link="${escapeHtml(safeUrl)}">${escapeHtml(email)}</a>`,
      )}`;
    },
  );
  value = value.replace(/((?:https?:\/\/|mailto:|www\.)[^\s<]+)/g, (candidate) => {
    const { url, trailing } = markdownUrlParts(candidate);
    const safeUrl = normalizeMarkdownUrl(url, { allowDataImage: false });
    if (!safeUrl) return escapeHtml(candidate);
    const externalAttrs = isInternalMarkdownLink(safeUrl)
      ? ""
      : ` target="_blank" rel="noreferrer noopener" data-chat-external-link="${escapeHtml(safeUrl)}"`;
    return `${stash(
      `<a href="${escapeHtml(safeUrl)}"${externalAttrs}>${escapeHtml(url)}</a>${richEmbedForUrl(
        safeUrl,
        url,
      )}`,
    )}${escapeHtml(trailing)}`;
  });
  let html = applyBalancedUnderscoreFormatting(
    escapeHtml(value)
      .replace(/~~([^~]+)~~/g, "<del>$1</del>")
      .replace(/==([^=\n]+)==/g, "<mark>$1</mark>")
      .replace(/(^|[^*])\*\*\*([^*\n]+)\*\*\*(?=[^*]|$)/g, "$1<strong><em>$2</em></strong>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*\n]+)\*/g, "<em>$1</em>"),
  );
  html = html.replace(/\n/g, "<br />");
  html = html.replace(/\uE000CHATMDTOKEN(\d+)\uE000/g, (_, index) => tokens[Number(index)] || "");
  html = html.replace(/[\uE000\uE001]?CHATMDTOKEN\d+[\uE000\uE001]?/g, "");
  return html;
}
let clubMarkdownRenderer = null;
const brokenMarkdownImageUrls = new Set();
function markdownImageFailureNote(src, altText = "") {
  const label = src || altText || "image";
  return `<div class="chat-broken-media-note"><span class="chat-broken-media-icon" aria-hidden="true">!</span><span>Image failed to load: ${escapeHtml(label)}</span></div>`;
}
function markdownImageHtml(url, altText = "") {
  const safeUrl = normalizeMarkdownUrl(url) || "";
  if (!safeUrl || brokenMarkdownImageUrls.has(safeUrl))
    return markdownImageFailureNote(safeUrl, altText);
  return `<img class="chat-markdown-image" src="${escapeHtml(safeUrl)}" alt="${escapeHtml(altText || "image")}" loading="lazy" onerror="window.handleChatMarkdownImageError&&window.handleChatMarkdownImageError(this)" />`;
}
function highlightMarkdownCode(code, lang = "") {
  return escapeHtml(code);
}
function isInternalMarkdownLink(url) {
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.origin === window.location.origin;
  } catch (e) {
    return false;
  }
}
function splitMarkdownTableRow(line) {
  let text = String(line || "").trim();
  if (text.startsWith("|")) text = text.slice(1);
  if (text.endsWith("|")) text = text.slice(0, -1);
  const cells = [];
  let current = "";
  let escaped = false;
  for (const char of text) {
    if (escaped) {
      current += char;
      escaped = false;
      continue;
    }
    if (char === "\\") {
      escaped = true;
      continue;
    }
    if (char === "|") {
      cells.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  if (escaped) current += "\\";
  cells.push(current.trim());
  return cells;
}
function markdownTableAlignments(separatorLine) {
  return splitMarkdownTableRow(separatorLine).map((cell) => {
    const text = String(cell || "").trim();
    if (/^:-{3,}:$/.test(text)) return "center";
    if (/^-{3,}:$/.test(text)) return "right";
    return "";
  });
}
function markdownCellAttrs(alignments, index) {
  const align = alignments[index] || "";
  return align ? ` style="text-align:${align}"` : "";
}
function normalizeReferenceKey(value) {
  return String(value || "").trim().replace(/\s+/g, " ").toLowerCase();
}
function extractMarkdownReferences(lines) {
  const references = {};
  const footnotes = {};
  const body = [];
  (lines || []).forEach((line) => {
    const footnoteMatch = String(line || "").match(/^\s{0,3}\[\^([^\]]+)\]:\s*(.*)$/);
    if (footnoteMatch) {
      footnotes[normalizeReferenceKey(footnoteMatch[1])] = footnoteMatch[2] || "";
      return;
    }
    const match = String(line || "").match(/^\s{0,3}\[([^\]]+)\]:\s+(\S+)(?:\s+["'(]([^"')]+)["')])?\s*$/);
    if (match) {
      references[normalizeReferenceKey(match[1])] = { url: match[2], title: match[3] || "" };
      return;
    }
    body.push(line);
  });
  return { references, footnotes, lines: body };
}
function isMarkdownBlockStart(lines, index) {
  const line = String(lines[index] || "");
  const trimmed = line.trim();
  if (!trimmed) return false;
  if (/^(```|~~~)/.test(trimmed)) return true;
  if (/^\$\$\s*$/.test(trimmed)) return true;
  if (/^(#{1,6})\s+/.test(trimmed)) return true;
  if (/^([-*_]\s*){3,}$/.test(trimmed)) return true;
  if (/^>\s?/.test(trimmed)) return true;
  if (/^(\s*)([-+*]|\d+\.)\s+/.test(line)) return true;
  if (/^( {4}|\t)/.test(line)) return true;
  return (
    index + 1 < lines.length &&
    line.includes("|") &&
    String(lines[index + 1] || "").includes("|") &&
    splitMarkdownTableRow(lines[index + 1]).every((cell) => /^:?-{2,}:?$/.test(cell))
  );
}
function renderMarkdownList(lines, startIndex, ordered, baseIndent = null, references = {}) {
  const tag = ordered ? "ol" : "ul";
  const items = [];
  let index = startIndex;
  while (index < lines.length) {
    const line = String(lines[index] || "");
    const match = line.match(/^(\s*)([-+*]|\d+\.)\s+(.*)$/);
    if (!match || /\d+\./.test(match[2]) !== ordered) break;
    const indent = match[1].replace(/\t/g, "    ").length;
    if (baseIndent === null) baseIndent = indent;
    if (indent < baseIndent) break;
    if (indent > baseIndent) {
      const nested = renderMarkdownList(lines, index, /\d+\./.test(match[2]), indent, references);
      if (items.length) items[items.length - 1] = items[items.length - 1].replace(/<\/li>$/, `${nested.html}</li>`);
      index = nested.index;
      continue;
    }
    const itemLines = [match[3]];
    const nestedHtml = [];
    index += 1;
    while (index < lines.length) {
      const nextLine = String(lines[index] || "");
      if (!nextLine.trim()) {
        index += 1;
        break;
      }
      const nestedMatch = nextLine.match(/^(\s*)([-+*]|\d+\.)\s+(.*)$/);
      if (nestedMatch) {
        const nestedIndent = nestedMatch[1].replace(/\t/g, "    ").length;
        if (nestedIndent > baseIndent) {
          const nested = renderMarkdownList(lines, index, /\d+\./.test(nestedMatch[2]), nestedIndent, references);
          nestedHtml.push(nested.html);
          index = nested.index;
          continue;
        }
        break;
      }
      if (/^\s{2,}\S/.test(nextLine)) {
        itemLines.push(nextLine.trim());
        index += 1;
        continue;
      }
      break;
    }
    let item = itemLines.join("\n");
    const taskMatch = item.match(/^\[([ xX-])\]\s+(.*)$/);
    if (taskMatch) {
      const checked = taskMatch[1].toLowerCase() === "x";
      const indeterminate = taskMatch[1] === "-";
      const marker = indeterminate
        ? '<span class="chat-task-checkbox chat-task-indeterminate" aria-hidden="true"></span>'
        : `<input type="checkbox" disabled${checked ? " checked" : ""} />`;
      items.push(`<li class="chat-task-item">${marker} ${renderMarkdownInline(taskMatch[2], references)}${nestedHtml.join("")}</li>`);
    } else {
      items.push(`<li>${renderMarkdownInline(item, references)}${nestedHtml.join("")}</li>`);
    }
  }
  return { html: `<${tag}>${items.join("")}</${tag}>`, index };
}
function markdownToHtml(text) {
  const source = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  if (!source) return "";
  const extracted = extractMarkdownReferences(source.split("\n"));
  const lines = extracted.lines;
  const references = extracted.references;
  const footnotes = extracted.footnotes || {};
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    const line = String(lines[index] || "");
    const trimmed = line.trim();
    if (!trimmed) {
      index += 1;
      continue;
    }
    if (/^\$\$\s*$/.test(trimmed)) {
      const mathLines = [];
      index += 1;
      while (index < lines.length && !/^\$\$\s*$/.test(String(lines[index] || "").trim())) {
        mathLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push(renderMarkdownMathToken(mathLines.join("\n"), true));
      continue;
    }
    const fenceMatch = trimmed.match(/^(```|~~~)(?:\s*(.*?))?\s*$/);
    if (fenceMatch) {
      const fence = fenceMatch[1];
      const inlineTitle = String(fenceMatch[2] || "").trim();
      const rawCodeLines = [];
      index += 1;
      while (index < lines.length && !String(lines[index] || "").trim().startsWith(fence)) {
        rawCodeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      let title = inlineTitle;
      let codeLines = rawCodeLines;
      if (!title) title = "text";
      blocks.push(
        `<pre class="chat-code"><div class="chat-code-lang">${escapeHtml(title)}</div><code>${highlightMarkdownCode(codeLines.join("\n"), title)}</code></pre>`,
      );
      continue;
    }
    if (/^( {4}|\t)/.test(line)) {
      const codeLines = [];
      while (index < lines.length && (/^( {4}|\t)/.test(String(lines[index] || "")) || !String(lines[index] || "").trim())) {
        codeLines.push(String(lines[index] || "").replace(/^( {4}|\t)/, ""));
        index += 1;
      }
      blocks.push(`<pre class="chat-code"><div class="chat-code-lang">text</div><code>${escapeHtml(codeLines.join("\n").replace(/\n+$/, ""))}</code></pre>`);
      continue;
    }
    if (
      index + 1 < lines.length &&
      line.includes("|") &&
      lines[index + 1].includes("|") &&
      splitMarkdownTableRow(lines[index + 1]).every((cell) =>
        /^:?-{2,}:?$/.test(cell),
      )
    ) {
      const headerCells = splitMarkdownTableRow(line);
      const alignments = markdownTableAlignments(lines[index + 1]);
      const rows = [];
      index += 2;
      while (index < lines.length && String(lines[index] || "").includes("|")) {
        rows.push(splitMarkdownTableRow(lines[index]));
        index += 1;
      }
      blocks.push(
        `<table><thead><tr>${headerCells
          .map((cell, cellIndex) => `<th${markdownCellAttrs(alignments, cellIndex)}>${renderMarkdownInline(cell, references)}</th>`)
          .join("")}</tr></thead><tbody>${rows
          .map(
            (cells) =>
              `<tr>${cells
                .map((cell, cellIndex) => `<td${markdownCellAttrs(alignments, cellIndex)}>${renderMarkdownInline(cell, references)}</td>`)
                .join("")}</tr>`,
          )
          .join("")}</tbody></table>`,
      );
      continue;
    }
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      blocks.push(
        `<h${level}>${renderMarkdownInline(headingMatch[2], references)}</h${level}>`,
      );
      index += 1;
      continue;
    }
    if (index + 1 < lines.length && /^:\s+/.test(String(lines[index + 1] || "").trim())) {
      const term = trimmed;
      const defs = [];
      index += 1;
      while (index < lines.length && /^:\s+/.test(String(lines[index] || "").trim())) {
        defs.push(String(lines[index] || "").trim().replace(/^:\s+/, ""));
        index += 1;
      }
      blocks.push(`<dl><dt>${renderMarkdownInline(term, references)}</dt>${defs.map((item) => `<dd>${renderMarkdownInline(item, references)}</dd>`).join("")}</dl>`);
      continue;
    }
    if (/^([-*_]\s*){3,}$/.test(trimmed)) {
      blocks.push("<hr />");
      index += 1;
      continue;
    }
    if (/^>\s?/.test(trimmed)) {
      const quoteLines = [];
      while (index < lines.length && /^>\s?/.test(String(lines[index] || "").trim())) {
        quoteLines.push(String(lines[index] || "").replace(/^\s*>\s?/, ""));
        index += 1;
      }
      blocks.push(`<blockquote>${markdownToHtml(quoteLines.join("\n"))}</blockquote>`);
      continue;
    }
    if (/^(\s*)([-+*]|\d+\.)\s+/.test(line)) {
      const ordered = /\d+\./.test(trimmed);
      const rendered = renderMarkdownList(lines, index, ordered, null, references);
      blocks.push(rendered.html);
      index = rendered.index;
      continue;
    }
    const paragraphLines = [];
    while (index < lines.length && String(lines[index] || "").trim()) {
      if (paragraphLines.length && isMarkdownBlockStart(lines, index)) break;
      paragraphLines.push(lines[index]);
      index += 1;
    }
    blocks.push(`<p>${renderMarkdownInline(paragraphLines.join("\n"), references)}</p>`);
  }
  const footnoteKeys = Object.keys(footnotes);
  if (footnoteKeys.length) {
    blocks.push(
      `<section class="chat-footnotes"><ol>${footnoteKeys
        .map(
          (key) =>
            `<li id="chat-footnote-${escapeHtml(key)}">${renderMarkdownInline(
              footnotes[key],
              references,
            )}</li>`,
        )
        .join("")}</ol></section>`,
    );
  }
  return blocks.join("");
}
function cachedMarkdownToHtml(text) {
  const source = String(text || "");
  if (!source) return "";
  const cached = chatMarkdownRenderCache.get(source);
  if (cached !== undefined) return cached;
  let rendered = "";
  try {
    rendered = markdownToHtml(source);
  } catch (error) {
    logDebugEvent("chat_markdown_render_error", {
      textLength: source.length,
      error: error?.message || String(error || ""),
    });
    rendered = `<div class="chat-plain-markdown">${renderPlainChatText(source)}</div>`;
  }
  chatMarkdownRenderCache.set(source, rendered);
  if (chatMarkdownRenderCache.size > 256) {
    const firstKey = chatMarkdownRenderCache.keys().next();
    if (!firstKey.done) chatMarkdownRenderCache.delete(firstKey.value);
  }
  return rendered;
}
function renderPlainChatText(text) {
  return escapeHtml(String(text || "")).replace(/\n/g, "<br />");
}
function chatTranscriptSignature() {
  const conversationId = String(chatState.activeConversationId || "");
  const visibleTurns = Math.max(
    CHAT_TRANSCRIPT_INITIAL_TURNS,
    Number(chatTranscriptVisibleTurns || 0) || CHAT_TRANSCRIPT_INITIAL_TURNS,
  );
  const parts = [conversationId, String(visibleTurns)];
  (chatState.messages || []).forEach((message, index) => {
    const attachments = chatMessageAttachments(message);
    parts.push(
      [
        index,
        message?.role || "",
        String(message?.text || "").length,
        String(message?.reasoningText || message?.reasoning_content || message?.reasoning || "").length,
        attachments.length,
        message?.thinkingExpanded ? 1 : 0,
        message?.thinkingDone ? 1 : 0,
        message?.thinkingLive ? 1 : 0,
        message?.modelLabel || "",
        message?.inputTokens ?? "",
        message?.outputTokens ?? "",
        message?.tokensPerSecond ?? "",
      ].join(":"),
    );
  });
  return parts.join("|");
}
function renderChatMessageMeta(message = {}) {
  const bits = [];
  if (message.role === "user") {
    if (message.inputTokens !== null && message.inputTokens !== undefined)
      bits.push(`input ${formatGroupedInt(message.inputTokens)} tokens`);
  } else if (message.role === "assistant") {
    if (message.outputTokens !== null && message.outputTokens !== undefined)
      bits.push(`output ${formatGroupedInt(message.outputTokens)} tokens`);
    if (message.ttftSeconds !== null && message.ttftSeconds !== undefined)
      bits.push(`TTFT ${formatNumber(message.ttftSeconds, 3)}s`);
    if (message.tokensPerSecond !== null && message.tokensPerSecond !== undefined) {
      bits.push(`tk/s ${formatNumber(message.tokensPerSecond, 2)}`);
    }
  }
  return bits.length
    ? `<div class="chat-message-meta">${escapeHtml(bits.join(" · "))}</div>`
    : "";
}
function isSelectionActiveWithin(host) {
  const selection = window.getSelection ? window.getSelection() : null;
  if (!selection || selection.isCollapsed || selection.rangeCount < 1) return false;
  const anchor = selection.anchorNode;
  const focus = selection.focusNode;
  return !!(
    host &&
    ((anchor && host.contains(anchor)) || (focus && host.contains(focus)))
  );
}
function isChatTranscriptSelectionActive(host) {
  return isSelectionActiveWithin(host);
}
function renderChatTranscript(forceFollow = false) {
  const host = $("chatTranscript");
  if (!host) return;
  ensureChatTranscriptBehavior();
  if (chatHydrationPending() || (!chatStateHydrated && !chatConversations().length)) {
    host.innerHTML = '<div class="empty-variant-note">Loading conversations...</div>';
    syncChatThinkingTicker();
    return;
  }
  if (activeChatConversation()?.messagesLoaded === false) {
    host.innerHTML = '<div class="empty-variant-note">Loading conversation...</div>';
    syncChatThinkingTicker();
    return;
  }
  const shouldFollow = forceFollow || chatTranscriptAutoFollow || chatTranscriptIsNearBottom(host);
  const hasLiveThinking = (chatState.messages || []).some((message) =>
    chatMessageThinkingActive(message),
  );
  const signature = hasLiveThinking ? "" : chatTranscriptSignature();
  if (
    !forceFollow &&
    signature &&
    signature === chatTranscriptLastSignature &&
    host.innerHTML === chatTranscriptLastHtml
  ) {
    syncChatThinkingTicker();
    return;
  }
  const turns = [];
  let currentTurn = null;
  (chatState.messages || []).forEach((message, messageIndex) => {
    const entry = { message, messageIndex };
    if (message.role === "user" || !currentTurn) {
      currentTurn = { number: turns.length + 1, messages: [entry] };
      turns.push(currentTurn);
      return;
    }
    currentTurn.messages.push(entry);
  });
  const hiddenTurns = Math.max(0, turns.length - Math.max(CHAT_TRANSCRIPT_INITIAL_TURNS, Number(chatTranscriptVisibleTurns || 0) || CHAT_TRANSCRIPT_INITIAL_TURNS));
  const visibleTurns = hiddenTurns > 0 ? turns.slice(hiddenTurns) : turns;
  let nextHtml = "";
  try {
    nextHtml = `${hiddenTurns > 0 ? `<div class="chat-history-banner"><div class="chat-history-copy">${escapeHtml(`${hiddenTurns} earlier turn${hiddenTurns === 1 ? "" : "s"} hidden to keep the tab responsive.`)}</div><button type="button" class="btn blue" onclick="expandChatTranscriptWindow()">Show ${escapeHtml(String(Math.min(hiddenTurns, CHAT_TRANSCRIPT_EXPAND_STEP)))} Older</button></div>` : ""}${visibleTurns
      .map((turn) => {
        const turnMessages = turn.messages
          .map(({ message, messageIndex }) => {
            try {
          const title =
            message.role === "assistant"
              ? `${message.modelLabel || "Model"}:`
              : message.role === "user"
                ? "User:"
                : "System:";
          const thinkingView =
            message.role === "assistant"
              ? chatMessageThinkingView(message)
              : { reasoningText: "", contentText: String(message?.text || "") };
          const body = cachedMarkdownToHtml(thinkingView.contentText || "");
          const thinkingActive = chatMessageThinkingActive(message);
          const thinkingExpanded =
            message.thinkingExpanded !== undefined
              ? !!message.thinkingExpanded
              : thinkingActive;
          const thinkingDuration = formatChatThinkingDuration(
            thinkingActive
              ? Date.now() - Number(message.thinkingStartedAt || Date.now())
              : message.thinkingDurationMs,
          );
          const thinkingTitle = thinkingDuration
            ? `${thinkingActive ? "Thinking" : "Thought"} for ${thinkingDuration}`
            : thinkingView.reasoningText
              ? `${thinkingActive ? "Thinking" : "Thought"} for <1 second`
              : thinkingActive
                ? "Thinking"
                : "Thought";
          const thinkingSubtitle = thinkingActive
            ? "Reasoning is streaming live."
            : thinkingExpanded
              ? "Tap to collapse."
              : "Tap to expand.";
          const thinkingBody = thinkingExpanded
            ? `<div class="chat-thinking-body"><div class="chat-plain-markdown">${renderPlainChatText(thinkingView.reasoningText)}</div></div>`
            : "";
          const thinkingCard = thinkingView.reasoningText
            ? `<div class="chat-thinking-card ${thinkingActive ? "thinking-live" : "thinking-done"} ${thinkingExpanded ? "expanded" : "collapsed"}"><button type="button" class="chat-thinking-toggle" onclick="toggleChatReasoning(${messageIndex})" aria-expanded="${thinkingExpanded ? "true" : "false"}"><span class="chat-thinking-copy"><span class="chat-thinking-title">${escapeHtml(thinkingTitle)}</span><span class="chat-thinking-subtitle">${escapeHtml(thinkingSubtitle)}</span></span><span class="chat-thinking-chevron">${svgIcon(thinkingExpanded ? "chevron-up" : "chevron-right")}</span></button><span class="chat-thinking-textcache" hidden>${escapeHtml(thinkingView.reasoningText)}</span>${thinkingBody}</div>`
            : "";
          const attachments = chatMessageAttachments(message);
          const imageAttachments = attachments.filter(
            (attachment) => attachment?.kind === "image",
          );
          const fileAttachments = attachments.filter(
            (attachment) => attachment?.kind !== "image",
          );
          const files = fileAttachments.length
            ? `<div class="chat-message-attachments">${fileAttachments
                .map(
                  (attachment) =>
                    `<div class="chat-message-attachment ${chatAttachmentKindClass(attachment)}"><span class="chat-attachment-name">${escapeHtml(attachment?.name || "file")}</span></div>`,
                )
                .join("")}</div>`
            : "";
          const images = imageAttachments.length
            ? `<div class="chat-inline-images">${imageAttachments.map((image) => `<img src="${image.url}" alt="${escapeHtml(image.name || "image")}" />`).join("")}</div>`
            : "";
          const meta = renderChatMessageMeta(message);
          return `<div class="chat-message chat-${message.role}"><div class="chat-message-title">${escapeHtml(title)}</div><div class="chat-message-body">${thinkingCard}${body}${files}${images}${meta}</div></div>`;
            } catch (error) {
              logDebugEvent("chat_transcript_message_render_error", {
                messageIndex,
                role: String(message?.role || ""),
                textLength: String(message?.text || "").length,
                reasoningLength: String(
                  message?.reasoningText || message?.reasoning_content || message?.reasoning || "",
                ).length,
                error: error?.message || String(error || ""),
              });
              const title =
                message.role === "assistant"
                  ? `${message.modelLabel || "Model"}:`
                  : message.role === "user"
                    ? "User:"
                    : "System:";
              return `<div class="chat-message chat-${escapeHtml(String(message?.role || "assistant"))}"><div class="chat-message-title">${escapeHtml(title)}</div><div class="chat-message-body"><pre class="chat-code"><code>${escapeHtml(String(message?.text || ""))}</code></pre></div></div>`;
            }
          })
          .join("");
        return `<div class="chat-turn"><div class="chat-turn-divider"><span class="chat-turn-label">Turn #${turn.number}</span></div>${turnMessages}</div>`;
      })
      .join("")}`;
  } catch (error) {
    logDebugEvent("chat_transcript_render_error", {
      conversationId: String(chatState.activeConversationId || ""),
      turnCount: turns.length,
      visibleTurns: Number(chatTranscriptVisibleTurns || 0),
      error: error?.message || String(error || ""),
    });
    nextHtml = `<div class="empty-variant-note">Conversation loaded, but rich transcript rendering failed. Showing plain-text fallback.</div>${(chatState.messages || [])
      .map(
        (message) =>
          `<pre class="chat-code"><code>${escapeHtml(`[${String(message?.role || "message")}]\n${String(message?.text || "")}`)}</code></pre>`,
      )
      .join("")}`;
  }
  if (
    !forceFollow &&
    !chatState.busy &&
    isChatTranscriptSelectionActive(host) &&
    host.innerHTML === nextHtml
  ) {
    syncChatThinkingTicker();
    return;
  }
  if (host.innerHTML !== nextHtml) host.innerHTML = nextHtml;
  if (signature) {
    chatTranscriptLastSignature = signature;
    chatTranscriptLastHtml = nextHtml;
  } else {
    chatTranscriptLastSignature = "";
    chatTranscriptLastHtml = nextHtml;
  }
  if (shouldFollow) host.scrollTop = host.scrollHeight;
  syncChatThinkingTicker();
}
function renderChatRuntimeStatsLegacy() {
  const host = $("chatRuntimeStats");
  if (!host) return;
  const runtime = activeChatRuntime();
  host.innerHTML = runtime
    ? `<div class="value">${escapeHtml(runtime.display_name || runtime.id || "Runtime")}</div><div class="value-subline">${escapeHtml(
        [
          runtime.mode || "-",
          runtime.container || "no container",
          Array.isArray(runtime.gpu_indices) && runtime.gpu_indices.length
            ? `GPUs ${runtime.gpu_indices.join(", ")}`
            : "GPU mapping unavailable",
        ].join(" · "),
      )}</div><div class="value-subline">${formatLastStatusCard(runtime, {}).replace(/<[^>]+>/g, " ")}</div>${runtime.prompt_tps !== null && runtime.prompt_tps !== undefined ? `<div class="value-subline">${escapeHtml(`prompt ${formatNumber(runtime.prompt_tps, 2)} tk/s`)}</div>` : ""}${runtime.generation_tps !== null && runtime.generation_tps !== undefined ? `<div class="value-subline">${escapeHtml(`generation ${formatNumber(runtime.generation_tps, 2)} tk/s`)}</div>` : ""}${runtime.last_total_tokens !== null && runtime.last_total_tokens !== undefined ? `<div class="value-subline">${escapeHtml(`last total ${formatCompactInt(runtime.last_total_tokens)} tokens`)}</div>` : ""}`
    : '<div class="empty-variant-note">Start a preset to test it from the local chat interface.</div>';
}
function renderChatRuntimeStats() {
  const host = $("chatRuntimeStats");
  const title = $("chatStatsTitle");
  if (!host) return;
  const runtime = activeChatRuntime();
  const scopedRuntime = conversationScopedRuntime(runtime, activeChatConversation());
  if (title) {
    title.textContent = scopedRuntime
      ? `Generation Stats (${scopedRuntime.display_name || scopedRuntime.id || "Runtime"})`
      : "Generation Stats";
  }
  host.innerHTML = scopedRuntime
    ? formatChatRuntimeStatsFlat(scopedRuntime)
    : '<div class="empty-variant-note">Start a preset to test it from the local chat interface.</div>';
}
function toggleChatStatsCollapsed() {
  chatState.statsCollapsed = !chatState.statsCollapsed;
  persistChatConversationState();
  renderChatUi();
}
function renderChatUi() {
  const toggle = $("chatSettingsToggle");
  if (toggle) toggle.innerHTML = svgIcon("gear");
  if ($("chatConversationShareBtn"))
    $("chatConversationShareBtn").innerHTML = svgIcon("share");
  if ($("chatOptionsMenu"))
    $("chatOptionsMenu").classList.toggle("hidden", !chatOptionsMenuOpen);
  ensureChatInputBindings();
  renderConversationSelector();
  renderChatPresetSelector();
  renderChatApiPresetSelector();
  renderChatAttachments();
  renderChatTranscript();
  renderChatRuntimeStats();
  handleChatInputResize();
  const runtime = activeChatRuntime();
  if ($("chatStatsCard"))
    $("chatStatsCard").classList.toggle("collapsed", !!chatState.statsCollapsed);
  if ($("chatStatsToggleBtn")) {
    $("chatStatsToggleBtn").innerHTML = svgIcon(
      chatState.statsCollapsed ? "chevron-down" : "chevron-up",
    );
  }
  if ($("chatSendBtn")) {
    const hasDraft =
      !!String($("chatInput")?.value || "").trim() ||
      !!(chatState.attachments || []).length;
    $("chatSendBtn").disabled = !runtime || (!chatState.busy && !hasDraft);
    $("chatSendBtn").classList.toggle("is-stop", !!chatState.busy);
    $("chatSendBtn").innerHTML = svgIcon(chatState.busy ? "stop" : "send");
  }
  if ($("chatAttachBtn")) $("chatAttachBtn").disabled = chatState.busy;
  if ($("chatMicBtn")) {
    $("chatMicBtn").disabled = chatState.busy;
    $("chatMicBtn").classList.toggle("recording", !!chatRecognition?.__active);
  }
  if ($("chatConversationNewBtn"))
    $("chatConversationNewBtn").disabled = chatState.busy;
  if ($("chatConversationEditBtn"))
    $("chatConversationEditBtn").disabled = chatState.busy;
  if ($("chatConversationShareBtn"))
    $("chatConversationShareBtn").disabled = chatState.busy;
  if ($("chatConversationDeleteBtn"))
    $("chatConversationDeleteBtn").disabled = chatState.busy;
  syncHeaderChatButtonAlignment();
}
function chatTextAttachmentName(prefix = "pasted") {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  return `${prefix}-${stamp}.md`;
}
function isTextAttachmentFile(file) {
  const type = String(file?.type || "").toLowerCase();
  const name = String(file?.name || "").toLowerCase();
  return (
    type.startsWith("text/") ||
    /(json|javascript|typescript|yaml|xml|csv|x-sh)/.test(type) ||
    /\.(txt|md|markdown|json|jsonl|csv|tsv|ya?ml|xml|html?|css|jsx?|tsx?|mjs|cjs|py|sh|bash|zsh|log|ini|cfg|conf)$/i.test(name)
  );
}
function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error(`Failed to read ${file?.name || "file"}.`));
    reader.readAsDataURL(file);
  });
}
async function uploadChatImageAttachment(file, source = "file") {
  const response = await fetch("/admin/chat-attachments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      kind: "image",
      name: file?.name || "image",
      mime: file?.type || "image/*",
      source,
      data_url: await readFileAsDataUrl(file),
    }),
  });
  const payload = await response.json();
  if (!response.ok || !payload?.ok || !payload?.attachment) {
    throw new Error(payload?.error || `Failed to upload ${file?.name || "image"}.`);
  }
  return cloneChatAttachment(payload.attachment);
}
async function buildChatAttachmentsFromFiles(files, source = "file") {
  const additions = [];
  for (const file of files || []) {
    if (!file) continue;
    if (String(file.type || "").toLowerCase().startsWith("image/")) {
      additions.push(await uploadChatImageAttachment(file, source));
      continue;
    }
    if (isTextAttachmentFile(file)) {
      additions.push({
        id: chatAttachmentId(),
        kind: "text",
        name: file.name || `attachment-${additions.length + 1}.txt`,
        mime: file.type || "text/plain",
        text: await file.text(),
        source,
      });
      continue;
    }
    throw new Error(`Unsupported attachment type: ${file.name || "file"}. Attach text files or images only.`);
  }
  return additions;
}
function addChatAttachments(additions) {
  if (!Array.isArray(additions) || !additions.length) return;
  chatState.attachments = [...(chatState.attachments || []), ...additions];
  persistChatConversationState();
  renderChatAttachments();
}
function openChatAttachmentPicker() {
  if (chatState.busy) return;
  $("chatAttachmentInput")?.click();
}
async function handleChatAttachmentSelect(event) {
  const files = Array.from(event?.target?.files || []);
  if (!files.length) return;
  try {
    addChatAttachments(await buildChatAttachmentsFromFiles(files));
    setChatMsg("");
  } catch (e) {
    setChatMsg(String(e || ""));
  } finally {
    if (event?.target) event.target.value = "";
  }
}
async function handleChatPaste(event) {
  const clipboard = event?.clipboardData;
  if (!clipboard) return;
  const files = Array.from(clipboard.files || []).filter(Boolean);
  if (files.length) {
    event.preventDefault();
    try {
      addChatAttachments(await buildChatAttachmentsFromFiles(files, "paste"));
      setChatMsg("");
    } catch (e) {
      setChatMsg(String(e || ""));
    }
    return;
  }
  const text = String(clipboard.getData("text/plain") || "");
  if (text.length < 1024) return;
  event.preventDefault();
  addChatAttachments([
    {
      id: chatAttachmentId(),
      kind: "text",
      name: chatTextAttachmentName(),
      mime: "text/markdown",
      text,
      source: "paste",
    },
  ]);
  setChatMsg("Attached the pasted text as a Markdown file.");
}
function speechRecognitionCtor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}
function appendChatInputText(text) {
  const input = $("chatInput");
  if (!input) return;
  const current = String(input.value || "");
  input.value = current ? `${current}${/\s$/.test(current) ? "" : " "}${text}` : text;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}
function ensureChatRecognition() {
  if (chatRecognition) return chatRecognition;
  const Ctor = speechRecognitionCtor();
  if (!Ctor) return null;
  const recognition = new Ctor();
  recognition.continuous = true;
  recognition.interimResults = false;
  recognition.lang = navigator.language || "en-US";
  recognition.onstart = () => {
    recognition.__active = true;
    setChatMsg("Listening for dictation...");
    renderChatUi();
  };
  recognition.onend = () => {
    recognition.__active = false;
    if (!chatState.busy) setChatMsg("");
    renderChatUi();
  };
  recognition.onerror = (event) => {
    recognition.__active = false;
    setChatMsg(`Voice dictation error: ${event?.error || "unknown error"}`);
    renderChatUi();
  };
  recognition.onresult = (event) => {
    const chunks = [];
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      if (result?.isFinal) chunks.push(String(result[0]?.transcript || "").trim());
    }
    const text = chunks.filter(Boolean).join(" ");
    if (text) appendChatInputText(text);
  };
  chatRecognition = recognition;
  return recognition;
}
function toggleChatDictation() {
  const recognition = ensureChatRecognition();
  if (!recognition) {
    setChatMsg("Voice dictation is not available in this browser.");
    return;
  }
  try {
    if (recognition.__active) recognition.stop();
    else recognition.start();
  } catch (e) {
    setChatMsg(String(e || "Unable to toggle voice dictation."));
  }
}
function chatAttachmentTextBlock(attachment) {
  return `Attached file: ${attachment?.name || "attachment"}\n\n${attachment?.text || ""}`;
}
function activeChatRequestParams() {
  const preset = chatApiPresetOptions().find(
    (item) => String(item?.name || "") === String(chatState.apiPresetName || ""),
  );
  return preset
    ? {
        ...defaultChatParams(),
        ...normalizePresetParamsForChat(preset.params || {}),
      }
    : cloneChatParams(chatState.params);
}
function chatMessageReasoningText(message) {
  return String(
    message?.reasoningText || message?.reasoning_content || message?.reasoning || "",
  );
}
function splitThinkingBlocks(text) {
  const blocks = [];
  const content = String(text || "").replace(
    /<(think|thinking)>([\s\S]*?)<\/\1>/gi,
    (_, _tag, body) => {
      const clean = String(body || "").trim();
      if (clean) blocks.push(clean);
      return "\n\n";
    },
  );
  return {
    reasoningText: blocks.join("\n\n").trim(),
    contentText: content.replace(/\n{3,}/g, "\n\n").trim(),
  };
}
function chatMessageThinkingView(message) {
  const titleStripped = extractChatTitleMarker(message?.text || "");
  const sourceText = titleStripped.title ? titleStripped.text : String(message?.text || "");
  const inline = splitThinkingBlocks(sourceText);
  const direct = chatMessageReasoningText(message).trim();
  const parts = [];
  if (direct) parts.push(direct);
  if (inline.reasoningText && !parts.includes(inline.reasoningText))
    parts.push(inline.reasoningText);
  return {
    reasoningText: parts.join("\n\n").trim(),
    contentText: inline.reasoningText ? inline.contentText : sourceText,
  };
}
function clampChatThinkingDurationMs(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) return 0;
  return Math.round(numeric);
}
function formatChatThinkingDuration(value) {
  const ms = clampChatThinkingDurationMs(value);
  if (!ms) return "";
  const seconds = ms / 1000;
  const digits = seconds >= 10 ? 0 : 1;
  const formatted = trimFormattedNumber(seconds.toFixed(digits));
  return `${formatted} second${formatted === "1" ? "" : "s"}`;
}
function chatMessageThinkingActive(message) {
  return !!message?.thinkingLive;
}
function finalizeChatThinkingState(message, collapse = true) {
  if (!message) return;
  if (message.thinkingStartedAt) {
    message.thinkingDurationMs = clampChatThinkingDurationMs(
      Date.now() - Number(message.thinkingStartedAt || 0),
    );
  } else {
    message.thinkingDurationMs = clampChatThinkingDurationMs(
      message.thinkingDurationMs,
    );
  }
  message.thinkingLive = false;
  message.thinkingDone = !!chatMessageThinkingView(message).reasoningText;
  if (collapse && message.thinkingDone) message.thinkingExpanded = false;
}
function syncChatThinkingTicker() {
  const needsTicker =
    !!chatState.busy &&
    (chatState.messages || []).some((message) => chatMessageThinkingActive(message));
  if (needsTicker && !chatThinkingTicker) {
    chatThinkingTicker = setInterval(() => {
      renderChatTranscript();
    }, CHAT_THINKING_RENDER_INTERVAL_MS);
  } else if (!needsTicker && chatThinkingTicker) {
    clearInterval(chatThinkingTicker);
    chatThinkingTicker = null;
  }
}
function toggleChatReasoning(messageIndex) {
  const idx = Number(messageIndex);
  if (!Number.isInteger(idx) || idx < 0) return;
  const message = (chatState.messages || [])[idx];
  if (!message || !chatMessageThinkingView(message).reasoningText) return;
  const expanded =
    message.thinkingExpanded !== undefined
      ? !!message.thinkingExpanded
      : chatMessageThinkingActive(message);
  message.thinkingExpanded = !expanded;
  persistChatConversationState();
  renderChatTranscript();
}
function buildChatRequestMessages(messages = chatState.messages || []) {
  const preserveThinking = !!activeChatRequestParams().preserve_thinking;
  return (messages || [])
    .map((message) => {
      if (message.role !== "user") {
        const view =
          message.role === "assistant"
            ? chatMessageThinkingView(message)
            : { reasoningText: "", contentText: String(message?.text || "") };
        const payload = { role: message.role, content: view.contentText || "" };
        if (
          message.role === "assistant" &&
          preserveThinking &&
          view.reasoningText
        ) {
          payload.reasoning_content = view.reasoningText;
        }
        return payload;
      }
      const attachments = chatMessageAttachments(message);
      const content = [];
      if (message.text) content.push({ type: "text", text: message.text });
      attachments.forEach((attachment) => {
        if (attachment?.kind === "image" && attachment?.url) {
          content.push({ type: "image_url", image_url: { url: attachment.url } });
        } else if (attachment?.kind === "text" && attachment?.text) {
          content.push({ type: "text", text: chatAttachmentTextBlock(attachment) });
        }
      });
      if (!content.length) return null;
      if (content.length === 1 && content[0].type === "text") {
        return { role: message.role, content: content[0].text };
      }
      return { role: message.role, content };
    })
    .filter(Boolean);
}
function parseChatStreamFrame(frame) {
  const lines = String(frame || "").split(/\r?\n/);
  let eventName = "message";
  const payloadLines = [];
  for (const line of lines) {
    if (!line) continue;
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) payloadLines.push(line.slice(5).trimStart());
  }
  if (!payloadLines.length) return null;
  const raw = payloadLines.join("\n");
  if (raw === "[DONE]") return null;
  try {
    return { eventName, payload: JSON.parse(raw) };
  } catch (e) {
    return { eventName, payload: { text: raw } };
  }
}
function stopChatGeneration() {
  if (!chatRequestController) return;
  setChatMsg("Stopping generation...");
  try {
    chatRequestController.abort();
  } catch (e) {}
}
async function sendChatMessage() {
  if (chatState.busy) {
    stopChatGeneration();
    return;
  }
  const runtime = activeChatRuntime();
  const input = $("chatInput");
  const text = String(input?.value || "").trim();
  const pendingAttachments = [...(chatState.attachments || [])];
  if (!runtime) return setChatMsg("Start a preset before using local chat.");
  if (!text && !pendingAttachments.length) return;
  if (!chatRuntimeSupportsVision(runtime) && pendingAttachments.some((attachment) => attachment?.kind === "image")) {
    return setChatMsg("The selected container does not advertise vision support, so image attachments are disabled for this request.");
  }
  const userMessage = {
    role: "user",
    text,
    attachments: pendingAttachments,
  };
  try {
    await maybeCompactChatConversation(runtime, userMessage);
  } catch (e) {
    return setChatMsg(String(e || ""), "error");
  }
  const assistantMessage = {
    role: "assistant",
    text: "",
    reasoningText: "",
    thinkingStartedAt: 0,
    thinkingDurationMs: 0,
    thinkingLive: false,
    thinkingDone: false,
    thinkingExpanded: true,
    modelLabel: runtime.served_model_name || runtime.model_id || runtime.mode || "Model",
  };
  const shouldAutoNameConversation = (chatState.messages || []).length === 0;
  const requestHistory = [...(chatState.messages || []), userMessage];
  chatState.messages = [...requestHistory, assistantMessage];
  chatState.attachments = [];
  chatState.busy = true;
  chatTranscriptAutoFollow = true;
  if (input) input.value = "";
  persistChatConversationState();
  renderChatUi();
  renderChatTranscript(true);
  setChatMsg("Generating message...");
  const assistantIndex = chatState.messages.length - 1;
  try {
    const requestMessages = buildChatRequestMessages(requestHistory);
    if (shouldAutoNameConversation)
      requestMessages.unshift({ role: "system", content: chatTitleInstruction() });
    const requestBody = {
      instance_id: runtime.id || runtime.instance_id,
      mode: runtime.selector || runtime.mode,
      model: runtime.served_model_name || runtime.model_id,
      messages: requestMessages,
      params: { ...chatState.params },
      api_preset: chatState.apiPresetName || "",
    };
    chatRequestController = new AbortController();
    const raw = await fetch("/admin/chat-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
      signal: chatRequestController.signal,
    });
    if (!raw.ok || !raw.body) {
      let errorText = "Chat request failed";
      try {
        const payload = await raw.json();
        errorText = payload.error || errorText;
      } catch (e) {}
      throw new Error(errorText);
    }
    const reader = raw.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let streamFinished = false;
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      for (const frame of frames) {
        const event = parseChatStreamFrame(frame);
        if (!event) continue;
        if (event.eventName === "delta") {
          if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
            finalizeChatThinkingState(chatState.messages[assistantIndex]);
          }
          chatState.messages[assistantIndex].text += String(event.payload?.text || "");
          renderChatTranscript(true);
        } else if (event.eventName === "reasoning") {
          const assistant = chatState.messages[assistantIndex];
          if (!assistant.thinkingStartedAt) assistant.thinkingStartedAt = Date.now();
          assistant.thinkingLive = true;
          assistant.thinkingDone = false;
          assistant.thinkingExpanded = true;
          assistant.reasoningText += String(event.payload?.text || "");
          assistant.thinkingDurationMs = clampChatThinkingDurationMs(
            Date.now() - Number(assistant.thinkingStartedAt || Date.now()),
          );
          renderChatTranscript(true);
        } else if (event.eventName === "tool") {
          if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
            finalizeChatThinkingState(chatState.messages[assistantIndex]);
          }
          setChatMsg(event.payload?.message || `Running tool ${event.payload?.name || ""}...`);
        } else if (event.eventName === "status") {
          setChatMsg(String(event.payload?.message || ""));
        } else if (event.eventName === "error") {
          throw new Error(event.payload?.error || event.payload?.message || "Chat stream failed.");
        } else if (event.eventName === "done") {
          if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
            finalizeChatThinkingState(chatState.messages[assistantIndex]);
          }
          updateConversationRuntimeMetrics(
            activeChatConversation(),
            runtime,
            event.payload || {},
          );
          streamFinished = true;
          setChatMsg("");
          break;
        }
      }
      if (done || streamFinished) break;
    }
    if (!streamFinished && buffer.trim()) {
      const event = parseChatStreamFrame(buffer);
      if (event?.eventName === "delta") {
        if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
          finalizeChatThinkingState(chatState.messages[assistantIndex]);
        }
        chatState.messages[assistantIndex].text += String(event.payload?.text || "");
        renderChatTranscript(true);
      } else if (event?.eventName === "reasoning") {
        const assistant = chatState.messages[assistantIndex];
        if (!assistant.thinkingStartedAt) assistant.thinkingStartedAt = Date.now();
        assistant.thinkingLive = true;
        assistant.thinkingDone = false;
        assistant.thinkingExpanded = true;
        assistant.reasoningText += String(event.payload?.text || "");
        assistant.thinkingDurationMs = clampChatThinkingDurationMs(
          Date.now() - Number(assistant.thinkingStartedAt || Date.now()),
        );
        renderChatTranscript(true);
      } else if (event?.eventName === "tool") {
        if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
          finalizeChatThinkingState(chatState.messages[assistantIndex]);
        }
        setChatMsg(event.payload?.message || `Running tool ${event.payload?.name || ""}...`);
      } else if (event?.eventName === "status") {
        setChatMsg(String(event.payload?.message || ""));
      } else if (event?.eventName === "error") {
        throw new Error(event.payload?.error || event.payload?.message || "Chat stream failed.");
      } else if (event?.eventName === "done") {
        if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
          finalizeChatThinkingState(chatState.messages[assistantIndex]);
        }
        updateConversationRuntimeMetrics(
          activeChatConversation(),
          runtime,
          event.payload || {},
        );
        setChatMsg("");
      }
    }
    if (
      chatMessageThinkingActive(chatState.messages[assistantIndex]) ||
      chatState.messages[assistantIndex].reasoningText
    ) {
      finalizeChatThinkingState(chatState.messages[assistantIndex]);
    }
    if (shouldAutoNameConversation) {
      const extractedTitle = extractChatTitleMarker(chatState.messages[assistantIndex].text);
      if (extractedTitle.title) {
        chatState.messages[assistantIndex].text = extractedTitle.text;
        syncActiveConversationFromChatState();
        applyConversationTitle(
          chatState.activeConversationId,
          extractedTitle.title,
          userMessage.text || "",
          pendingAttachments,
        );
      }
    }
    if (
      !chatState.messages[assistantIndex].text.trim() &&
      !chatMessageThinkingView(chatState.messages[assistantIndex]).reasoningText
    ) {
      chatState.messages[assistantIndex].text = "[No text returned]";
    }
    setChatMsg("");
    refreshStatus({ force: true }).catch(() => {});
    if (shouldAutoNameConversation) {
      applyConversationTitle(
        chatState.activeConversationId,
        "",
        userMessage.text || "",
        pendingAttachments,
      );
    }
  } catch (e) {
    const aborted =
      e?.name === "AbortError" ||
      /aborted|abort/i.test(String(e?.message || e || ""));
    if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
      finalizeChatThinkingState(chatState.messages[assistantIndex], !aborted);
    }
    if (
      !String(chatState.messages[assistantIndex]?.text || "").trim() &&
      !chatMessageThinkingView(chatState.messages[assistantIndex] || {}).reasoningText
    ) {
      chatState.messages = chatState.messages.filter((_, index) => index !== assistantIndex);
    }
    setChatMsg(
      aborted ? "Generation stopped." : String(e || ""),
      aborted ? "warning" : "error",
    );
  } finally {
    chatState.busy = false;
    chatRequestController = null;
    persistChatConversationState();
    renderChatUi();
  }
}
ensureDynamicPresetLayout();
ensurePresetActionModal();
renderPresetScopeTabs();
renderModelInstallStatus();
renderDynamicPresetModels();
refreshStatus({ force: true }).catch(() => {});
