// Log search, formatting, and GPU cards
function clearLog() {
  const signature = currentLogSignature || logStreamConfig().signature;
  const entry = logCacheEntry(signature);
  entry.text = "";
  entry.loaded = true;
  renderCurrentLog(signature);
}
function appendLogToSignature(signature, t) {
  const targetSignature = String(signature || currentLogSignature || logStreamConfig().signature || "").trim();
  if (!targetSignature) return;
  appendLogChunk(targetSignature, `${t}\n`);
}
function appendLog(t) {
  const signature = currentLogSignature || logStreamConfig().signature;
  appendLogToSignature(signature, t);
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
            const gpuIndex = Number(g.index || 0);
            const title = `GPU ${g.index} - ${g.name || "RTX 3090"}${g.vendor ? " (" + g.vendor + ")" : ""}`;
            const freeButton = renderIconButton({
              title: `Free resources using GPU ${gpuIndex}`,
              action: `promptFreeGpuResources(${gpuIndex})`,
              icon: "delete",
              className: "gpu-free-btn",
            });
            const tempRows = [
              `<div class="gpu-line"><span>Core</span><b>${formatTempWithPeak(g.temp_c, g.temp_peak_c)}</b></div>`,
            ];
            if (formatMaybeNumber(g.temp_junction_c, 0)) {
              tempRows.push(
                `<div class="gpu-line"><span>Junction</span><b>${formatTempWithPeak(g.temp_junction_c, g.temp_junction_peak_c)}</b></div>`,
              );
            }
            if (formatMaybeNumber(g.temp_vram_c, 0)) {
              tempRows.push(
                `<div class="gpu-line"><span>VRAM</span><b>${formatTempWithPeak(g.temp_vram_c, g.temp_vram_peak_c)}</b></div>`,
              );
            }
            return `<div class="gpu-card"><div class="gpu-title"><span class="gpu-title-text">${escapeHtml(title)}</span>${freeButton}</div><div class="gpu-grid"><div><div class="gpu-section-title">Temperature</div>${tempRows.join("")}</div><div><div class="gpu-section-title">VRAM</div><div class="gpu-line"><span>Free</span><b>${mibToGiB(g.mem_free_mib)} GB</b></div><div class="gpu-line"><span>Used</span><b>${mibToGiB(g.mem_used_mib)} GB</b></div><div class="gpu-line"><span>Max</span><b>${mibToGiB(g.mem_total_mib)} GB</b></div><div class="meter"><span style="width:${Number(g.mem_pct || 0)}%"></span></div></div><div><div class="gpu-section-title">Power</div><div class="gpu-line"><span>Draw</span><b>${formatGpuMetricWithPeak(g.power_w, g.power_peak_w, "W", 2)}</b></div><div class="gpu-line"><span>Max Power</span><b>${g.power_limit_w || "N/A"} W</b></div></div><div><div class="gpu-section-title">Fans</div><div class="gpu-line"><span>Speed</span><b>${g.fan_pct || "N/A"}%</b></div></div><div><div class="gpu-section-title">Clocks</div><div class="gpu-line"><span>Core</span><b>${formatGpuMetricWithPeak(g.core_clock_mhz, g.core_clock_peak_mhz, "MHz", 0)}</b></div><div class="gpu-line"><span>Mem</span><b>${formatGpuMetricWithPeak(g.mem_clock_mhz, g.mem_clock_peak_mhz, "MHz", 0)}</b></div></div><div><div class="gpu-section-title">Usage</div><div class="gpu-line"><span>Load</span><b>${g.util_pct || "N/A"}%</b></div><div class="gpu-line"><span>Status</span><b>${currentStatus}${previousStatus ? ` (Previous: ${previousStatus})` : ""}</b></div></div></div></div>`;
          })(),
    )
    .join("");
}
function promptFreeGpuResources(gpuIndex) {
  const index = Number(gpuIndex || 0);
  openPresetActionModal({
    title: "Free GPU Resources",
    body: `Stop and remove runtime containers currently using <code>GPU ${escapeHtml(String(index))}</code>? This frees VRAM and then returns the machine to idle power handling.`,
    confirmLabel: "Free GPU",
    confirmClass: "red",
    onConfirm: async () => {
      await post("/admin/power", { action: "free_gpu", gpu_index: index }, `/admin/power free_gpu GPU${index}`);
      await refreshStatus({ force: true });
    },
  });
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
  const nextHtml =
    items
      .map((p) => {
        const locked = p.locked;
        return `<div class="api-card"><div class="api-card-head"><h3>${p.endpoint}<br><span class="label">${p.endpoint_alt || "/" + p.name}</span></h3>${locked ? '<span class="label">default</span>' : `<span class="preset-actions"><button class="iconbtn" title="Edit" onclick="editPreset('${p.name}')">${svgIcon("edit")}</button><button class="iconbtn" title="Delete" onclick="deletePreset('${p.name}')">${svgIcon("delete")}</button></span>`}</div><p>${p.description || ""}</p><p class="label">${presetParamSummary(p.params)}</p></div>`;
      })
      .join("") +
    `<div class="api-card"><h3>/v1/short-* / /short-* and /v1/concise-* / /concise-*</h3><p>Prefix any default or custom preset to cap replies: short = 4096 tokens, concise = 512 tokens. Presets work both under /v1/name and /name for clients that append /v1 automatically.</p></div>`;
  setHtmlIfChanged(grid, nextHtml);
}
function applyPresetCatalogPayload(catalog) {
  if (!catalog || typeof catalog !== "object") return;
  if (!lastStatus) lastStatus = {};
  lastStatus.presets = catalog;
  renderPresetCatalog(catalog);
  if (typeof renderChatApiPresetSelector === "function")
    renderChatApiPresetSelector();
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
    applyPresetCatalogPayload(j.presets);
    closePresetEditor();
    setMsg("Saved preset " + name);
    refreshStatus({ force: true }).catch(() => {});
  } catch (e) {
    alert("Preset save failed: " + e);
  }
}
function editPreset(name) {
  const p = (lastStatus?.presets?.custom || []).find((x) => x.name === name);
  if (p) openPresetEditor(p);
}
async function deletePreset(name) {
  if (!(await openClubConfirmModal("Delete custom preset " + name + "?"))) return;
  try {
    const r = await fetch("/admin/presets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "delete", name }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "delete failed");
    applyPresetCatalogPayload(j.presets);
    if (editingPresetName === name) closePresetEditor();
    setMsg("Deleted preset " + name);
    refreshStatus({ force: true }).catch(() => {});
  } catch (e) {
    alert("Preset delete failed: " + e);
  }
}
