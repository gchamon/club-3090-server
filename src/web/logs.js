function renderLogSourcePanel() {
  const panel = $("logSourcePanel");
  const updateActive = selfUpdateActive(lastStatus);
  if (panel) {
    const services = Array.isArray(lastStatus?.upstream_services)
      ? lastStatus.upstream_services.filter((row) => row && row.running)
      : [];
    const modelSources = modelLogSourceEntries();
    const scriptActive = !!lastStatus?.script_job?.active || currentLogSource === "script";
    panel.className = `panel log-source-panel${updateActive ? " log-source-panel-disabled" : ""}`;
    const disabledAttr = updateActive ? ' disabled aria-disabled="true"' : "";
    panel.innerHTML = `<div class="panel-head"><h2>Log Sources</h2><div class="preset-actions">${renderIconButton({ title: "Export", action: "exportCurrentLog()", icon: "upload", disabled: updateActive })}</div></div><div class="subtabs">${[
      { id: "control", label: "Web UI Server" },
      { id: "audit", label: "Audit" },
      { id: "debug", label: "Debug" },
      ...modelSources,
      { id: "benchmarks", label: "Benchmarks" },
      ...(scriptActive ? [{ id: "script", label: "Script" }] : []),
      ...(updateActive || currentLogSource === "update"
        ? [{ id: "update", label: "Update" }]
        : []),
      ...services.map((row) => ({
        id: `service:${String(row.id || "")}`,
        label: String(row.display_name || row.id || "Service"),
      })),
      { id: "docker", label: "Runtime Docker" },
    ]
      .map(
        (row) =>
          `<button class="subtab${currentLogSource === row.id ? " active" : ""}"${disabledAttr} onclick="setCurrentLogSource('${escapeJs(row.id)}')">${escapeHtml(row.label)}</button>`,
      )
      .join("")}</div><div class="value smallgap" id="logsSourceSummary">-</div>`;
  }
  renderDebugLogCommandUi();
  if (!$("logsSourceSummary")) return;
  if (currentLogSource === "update") {
    $("logsSourceSummary").innerHTML =
      "Update selected. The live viewer follows the separate updater service and keeps the self-update stream visible while the control plane restarts.";
    return;
  }
  if (currentLogSource === "control") {
    $("logsSourceSummary").innerHTML =
      "Web UI Server selected. The live viewer follows <code>/opt/club3090-control/control.log</code>.";
    return;
  }
  if (currentLogSource === "audit") {
    $("logsSourceSummary").innerHTML =
      "Audit selected. The live viewer follows <code>/opt/club3090-control/audit.log</code>.";
    return;
  }
  if (currentLogSource === "debug") {
    $("logsSourceSummary").innerHTML =
      "Debug selected. The live viewer follows <code>/opt/club3090-control/debug.log</code>.";
    return;
  }
  if (currentLogSource === "benchmarks") {
    const current = lastStatus?.benchmarks?.current_log || {};
    const label = current.label || "benchmark script output";
    const progress = Number(current.progress || 0);
    $("logsSourceSummary").innerHTML =
      `Benchmarks selected. Showing <code>${escapeHtml(label)}</code>${Number.isFinite(progress) && progress > 0 ? ` · ${Math.round(progress * 100)}%` : ""}.`;
    return;
  }
  if (currentLogSource === "script") {
    const job = lastStatus?.script_job || {};
    $("logsSourceSummary").innerHTML =
      `Script selected. ${escapeHtml(job.summary || "The live viewer follows the active upstream script output.")}${job.label ? ` <code>${escapeHtml(job.label)}</code>` : ""}`;
    return;
  }
  if (String(currentLogSource || "").startsWith("model:")) {
    const modelSource = modelLogSourceFromSource(currentLogSource);
    $("logsSourceSummary").innerHTML = modelSource
      ? `${escapeHtml(modelSource.label)} selected. The live viewer follows container <code>${escapeHtml(modelSource.container || modelSource.instanceId)}</code>.`
      : "Model service log source selected.";
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
  $("logsSourceSummary").innerHTML = (() => {
    const options = dockerLogInstanceOptions();
    const current = selectedDockerLogInstanceOption();
    if (!options.length) {
      return "Runtime Docker selected. No managed runtime is active yet.";
    }
    if (options.length > 1 && current) {
      return `Runtime Docker selected. The instance selector is focused on <code>${escapeHtml(current.id)}</code> so you can switch between active fanned-out runtimes.`;
    }
    return `Runtime Docker selected. The live viewer follows <code>${escapeHtml(current?.id || "primary")}</code>.`;
  })();
}
function modelLogSourceEntries() {
  const seen = new Set();
  return runtimeStatsRows(lastStatus)
    .filter((row) => row && (row.running || row.booting))
    .map((row) => {
      const instanceId = String(row.id || row.instance_id || "").trim().toUpperCase();
      if (!instanceId || seen.has(instanceId)) return null;
      seen.add(instanceId);
      const selector = String(row.selector || row.mode || "").trim();
      const variant = selector ? variantMapBySelector().get(selector) : null;
      const preset = variant ? variantDisplayLabel(variant) : selector || row.display_name || instanceId;
      const scope = String(row.display_name || instanceId).trim();
      return {
        id: `model:${instanceId}`,
        label: `Model: ${preset}${scope ? ` · ${scope}` : ""}`,
        instanceId,
        selector,
        container: String(row.container || "").trim(),
      };
    })
    .filter(Boolean);
}
function modelLogSourceFromSource(source) {
  const instanceId = String(source || "").startsWith("model:")
    ? String(source).slice("model:".length).trim().toUpperCase()
    : "";
  if (!instanceId) return null;
  return modelLogSourceEntries().find((row) => row.instanceId === instanceId) || {
    id: `model:${instanceId}`,
    label: `Model Service · ${instanceId}`,
    instanceId,
    selector: "",
    container: "",
  };
}
function debugLogCommandEnabled() {
  return currentLogSource === "debug" && !selfUpdateActive(lastStatus);
}
let debugTransferBusy = false;
let debugTransferUploadLongPressTimer = 0;
let debugTransferUploadLongPressConsumed = false;
const DEBUG_LOG_COMMAND_HISTORY_KEY = "club3090.debug-log-command-history.v1";
const DEBUG_LOG_COMMAND_HISTORY_LIMIT = 100;
let debugLogCommandHistory = [];
let debugLogCommandHistoryCursor = -1;
let debugLogCommandHistoryDraft = "";
let debugLogCommandCompletionToken = 0;
let debugLogCommandCompletionTimer = 0;
let debugLogCommandCompletion = {
  candidates: [],
  index: -1,
  fullText: "",
  suffix: "",
  source: "",
  replaceFrom: 0,
};
let debugLogCommandProgrammaticInput = false;
function loadDebugLogCommandHistory() {
  if (debugLogCommandHistory.length) return debugLogCommandHistory;
  try {
    const raw = JSON.parse(localStorage.getItem(DEBUG_LOG_COMMAND_HISTORY_KEY) || "[]");
    if (Array.isArray(raw)) {
      debugLogCommandHistory = raw
        .map((item) => String(item || "").trim())
        .filter(Boolean)
        .slice(-DEBUG_LOG_COMMAND_HISTORY_LIMIT);
    }
  } catch (error) {
    debugLogCommandHistory = [];
  }
  return debugLogCommandHistory;
}
function saveDebugLogCommandHistory() {
  try {
    localStorage.setItem(
      DEBUG_LOG_COMMAND_HISTORY_KEY,
      JSON.stringify(debugLogCommandHistory.slice(-DEBUG_LOG_COMMAND_HISTORY_LIMIT)),
    );
  } catch (error) {}
}
function rememberDebugLogCommand(command) {
  const text = String(command || "").trim();
  if (!text) return;
  loadDebugLogCommandHistory();
  if (debugLogCommandHistory[debugLogCommandHistory.length - 1] === text) {
    resetDebugLogCommandHistoryNav();
    return;
  }
  debugLogCommandHistory.push(text);
  if (debugLogCommandHistory.length > DEBUG_LOG_COMMAND_HISTORY_LIMIT) {
    debugLogCommandHistory = debugLogCommandHistory.slice(-DEBUG_LOG_COMMAND_HISTORY_LIMIT);
  }
  saveDebugLogCommandHistory();
  resetDebugLogCommandHistoryNav();
}
function resetDebugLogCommandHistoryNav() {
  debugLogCommandHistoryCursor = -1;
  debugLogCommandHistoryDraft = "";
}
function setDebugLogCommandValue(value, { keepDraft = false } = {}) {
  const input = $("logCommandInput");
  if (!input) return;
  debugLogCommandProgrammaticInput = true;
  input.value = String(value || "");
  input.selectionStart = input.selectionEnd = input.value.length;
  if (!keepDraft) resetDebugLogCommandHistoryNav();
  syncDebugLogCommandGhostScroll();
  scheduleDebugLogCommandCompletion();
  handleDebugLogCommandChange();
}
function moveDebugLogCommandHistory(direction) {
  const input = $("logCommandInput");
  const history = loadDebugLogCommandHistory();
  if (!input || !history.length) return;
  if (direction > 0 && debugLogCommandHistoryCursor === -1) return;
  if (debugLogCommandHistoryCursor === -1) {
    debugLogCommandHistoryDraft = String(input.value || "");
    debugLogCommandHistoryCursor = history.length;
  }
  const nextCursor = Math.max(0, Math.min(history.length, debugLogCommandHistoryCursor + direction));
  if (nextCursor === history.length) {
    debugLogCommandHistoryCursor = -1;
    setDebugLogCommandValue(debugLogCommandHistoryDraft, { keepDraft: true });
    return;
  }
  debugLogCommandHistoryCursor = nextCursor;
  setDebugLogCommandValue(history[nextCursor], { keepDraft: true });
}
function debugLogCommandCaretAtEnd() {
  const input = $("logCommandInput");
  if (!input) return false;
  return input.selectionStart === input.selectionEnd && input.selectionEnd === String(input.value || "").length;
}
function clearDebugLogCommandCompletion() {
  debugLogCommandCompletion = {
    candidates: [],
    index: -1,
    fullText: "",
    suffix: "",
    source: "",
    replaceFrom: 0,
  };
  renderDebugLogCommandGhost();
}
function renderDebugLogCommandGhost() {
  const input = $("logCommandInput");
  const ghost = $("logCommandGhost");
  if (!input || !ghost) return;
  const value = String(input.value || "");
  const suffix = String(debugLogCommandCompletion.suffix || "");
  const toneClass =
    debugLogCommandCompletion.source === "history"
      ? " log-command-ghost-suggestion-history"
      : debugLogCommandCompletion.source === "path"
        ? " log-command-ghost-suggestion-path"
        : "";
  ghost.innerHTML =
    suffix && debugLogCommandCaretAtEnd()
      ? `<span class="log-command-ghost-prefix">${escapeHtml(value)}</span><span class="log-command-ghost-suggestion${toneClass}">${escapeHtml(suffix)}</span>`
      : "";
  syncDebugLogCommandGhostScroll();
}
function syncDebugLogCommandGhostScroll() {
  const input = $("logCommandInput");
  const ghost = $("logCommandGhost");
  if (!input || !ghost) return;
  ghost.scrollTop = input.scrollTop;
  ghost.scrollLeft = input.scrollLeft;
}
function debugLogHistoryCompletionCandidates(value) {
  const prefix = String(value || "");
  if (!prefix) return [];
  const items = [];
  const seen = new Set();
  const history = loadDebugLogCommandHistory();
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const entry = String(history[index] || "");
    if (!entry || entry === prefix || !entry.startsWith(prefix) || seen.has(entry)) continue;
    seen.add(entry);
    items.push({ fullText: entry, source: "history" });
  }
  return items;
}
function buildDebugLogPathCandidates(payload, value, cursorPos) {
  const replaceFrom = Number(payload?.replace_from ?? value.length);
  const suggestions = [];
  const seen = new Set();
  const items = [];
  if (payload?.suggestion) suggestions.push(String(payload.suggestion || ""));
  for (const match of payload?.matches || []) suggestions.push(String(match || ""));
  for (const item of suggestions) {
    if (!item) continue;
    const fullText = `${value.slice(0, replaceFrom)}${item}${value.slice(cursorPos)}`;
    if (!fullText || fullText === value || !fullText.startsWith(value) || seen.has(fullText)) continue;
    seen.add(fullText);
    items.push({ fullText, source: "path", replaceFrom });
  }
  return items;
}
function applyDebugLogCompletionCandidate(index) {
  const input = $("logCommandInput");
  if (!input) return clearDebugLogCommandCompletion();
  const candidates = Array.isArray(debugLogCommandCompletion.candidates)
    ? debugLogCommandCompletion.candidates
    : [];
  if (!candidates.length) return clearDebugLogCommandCompletion();
  const boundedIndex = ((Number(index || 0) % candidates.length) + candidates.length) % candidates.length;
  const value = String(input.value || "");
  const selected = candidates[boundedIndex];
  if (!selected?.fullText || selected.fullText === value || !selected.fullText.startsWith(value)) {
    return clearDebugLogCommandCompletion();
  }
  debugLogCommandCompletion.index = boundedIndex;
  debugLogCommandCompletion.fullText = selected.fullText;
  debugLogCommandCompletion.suffix = selected.fullText.slice(value.length);
  debugLogCommandCompletion.source = String(selected.source || "");
  debugLogCommandCompletion.replaceFrom = Number(selected.replaceFrom ?? value.length);
  renderDebugLogCommandGhost();
}
function chooseDebugLogCompletion(payload) {
  const input = $("logCommandInput");
  if (!input) return clearDebugLogCommandCompletion();
  const value = String(input.value || "");
  if (!debugLogCommandEnabled() || !debugLogCommandCaretAtEnd()) return clearDebugLogCommandCompletion();
  const linePrefix = value.slice(0, input.selectionStart);
  const pathCandidates = buildDebugLogPathCandidates(payload, value, input.selectionStart);
  const historyCandidates = debugLogHistoryCompletionCandidates(value);
  const preferPath =
    pathCandidates.length &&
    (/\s/.test(linePrefix) || /[./~\\]/.test(String(payload?.fragment || "")) || !historyCandidates.length);
  const candidates = preferPath
    ? [...pathCandidates, ...historyCandidates]
    : [...historyCandidates, ...pathCandidates];
  if (!candidates.length) return clearDebugLogCommandCompletion();
  debugLogCommandCompletion.candidates = candidates;
  applyDebugLogCompletionCandidate(0);
}
async function requestDebugLogCommandCompletion() {
  const input = $("logCommandInput");
  if (!input || !debugLogCommandEnabled() || !debugLogCommandCaretAtEnd()) return clearDebugLogCommandCompletion();
  const token = ++debugLogCommandCompletionToken;
  try {
    const response = await fetch("/admin/debug-log-complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        command: String(input.value || ""),
        cursor: input.selectionEnd,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload?.ok) throw new Error(payload?.error || `Completion failed (${response.status})`);
    if (token !== debugLogCommandCompletionToken) return;
    chooseDebugLogCompletion(payload);
  } catch (error) {
    if (token === debugLogCommandCompletionToken) clearDebugLogCommandCompletion();
  }
}
function scheduleDebugLogCommandCompletion() {
  clearTimeout(debugLogCommandCompletionTimer);
  if (!debugLogCommandEnabled()) return clearDebugLogCommandCompletion();
  debugLogCommandCompletionTimer = window.setTimeout(requestDebugLogCommandCompletion, 90);
}
function acceptDebugLogCommandCompletion() {
  if (!debugLogCommandCompletion.suffix) return false;
  setDebugLogCommandValue(debugLogCommandCompletion.fullText, { keepDraft: true });
  clearDebugLogCommandCompletion();
  return true;
}
function cycleDebugLogCommandCompletion(direction) {
  const candidates = Array.isArray(debugLogCommandCompletion.candidates)
    ? debugLogCommandCompletion.candidates
    : [];
  if (!candidates.length) return false;
  applyDebugLogCompletionCandidate((debugLogCommandCompletion.index < 0 ? 0 : debugLogCommandCompletion.index) + direction);
  return true;
}
function removeDebugLogAutocompletedSection() {
  const input = $("logCommandInput");
  if (!input || !debugLogCommandCompletion.suffix || !debugLogCommandCaretAtEnd()) return false;
  const nextValue = String(input.value || "").slice(0, Math.max(0, Number(debugLogCommandCompletion.replaceFrom || 0)));
  setDebugLogCommandValue(nextValue, { keepDraft: true });
  clearDebugLogCommandCompletion();
  return true;
}
function handleDebugLogCommandChange() {
  const input = $("logCommandInput");
  const button = $("logCommandSendBtn");
  if (!debugLogCommandProgrammaticInput) resetDebugLogCommandHistoryNav();
  debugLogCommandProgrammaticInput = false;
  if (!button) return;
  button.disabled = debugTransferBusy || !debugLogCommandEnabled() || !String(input?.value || "").trim();
  if ($("logTransferUploadBtn")) $("logTransferUploadBtn").disabled = debugTransferBusy || !debugLogCommandEnabled();
  if ($("logTransferDownloadBtn"))
    $("logTransferDownloadBtn").disabled = debugTransferBusy || !debugLogCommandEnabled() || !String(input?.value || "").trim();
  scheduleDebugLogCommandCompletion();
}
function handleDebugLogCommandKeydown(event) {
  if (!event) return;
  if (event.ctrlKey && !event.metaKey && !event.altKey && (event.code === "Space" || event.key === " ")) {
    event.preventDefault();
    if (debugLogCommandCompletion.suffix) {
      acceptDebugLogCommandCompletion();
      return;
    }
    requestDebugLogCommandCompletion()
      .then(() => {
        acceptDebugLogCommandCompletion();
      })
      .catch(() => {});
    return;
  }
  if (event.ctrlKey && event.key === "ArrowLeft") {
    event.preventDefault();
    if (!cycleDebugLogCommandCompletion(-1)) scheduleDebugLogCommandCompletion();
    return;
  }
  if (event.ctrlKey && event.key === "ArrowRight") {
    event.preventDefault();
    if (!cycleDebugLogCommandCompletion(1)) scheduleDebugLogCommandCompletion();
    return;
  }
  if (event.ctrlKey && event.key === "ArrowUp") {
    event.preventDefault();
    moveDebugLogCommandHistory(-1);
    return;
  }
  if (event.ctrlKey && event.key === "ArrowDown") {
    event.preventDefault();
    moveDebugLogCommandHistory(1);
    return;
  }
  if (event.key === "Backspace" && !event.ctrlKey && !event.metaKey && !event.altKey) {
    if (removeDebugLogAutocompletedSection()) {
      event.preventDefault();
      return;
    }
  }
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    sendDebugLogCommand();
  }
}
function ensureDebugLogCommandBindings() {
  const input = $("logCommandInput");
  if (input && !input.__clubKeyBinding) {
    input.__clubKeyBinding = true;
    input.addEventListener("input", handleDebugLogCommandChange);
    input.addEventListener("keydown", handleDebugLogCommandKeydown);
    input.addEventListener("scroll", syncDebugLogCommandGhostScroll);
    input.addEventListener("click", scheduleDebugLogCommandCompletion);
    input.addEventListener("focus", scheduleDebugLogCommandCompletion);
  }
  const uploadButton = $("logTransferUploadBtn");
  if (uploadButton && !uploadButton.__clubUploadLongPressBinding) {
    uploadButton.__clubUploadLongPressBinding = true;
    uploadButton.addEventListener("pointerdown", beginDebugTransferUploadPress);
    uploadButton.addEventListener("pointerup", cancelDebugTransferUploadPress);
    uploadButton.addEventListener("pointerleave", cancelDebugTransferUploadPress);
    uploadButton.addEventListener("pointercancel", cancelDebugTransferUploadPress);
  }
}
function renderDebugLogCommandUi() {
  const wrap = $("logCommandWrap");
  const input = $("logCommandInput");
  if (!wrap || !input) return;
  ensureDebugLogCommandBindings();
  wrap.classList.toggle("hidden", !debugLogCommandEnabled());
  input.disabled = !debugLogCommandEnabled();
  if (!debugLogCommandEnabled()) clearDebugLogCommandCompletion();
  handleDebugLogCommandChange();
}
async function sendDebugLogCommand() {
  const input = $("logCommandInput");
  if (!input || !debugLogCommandEnabled()) return;
  const command = String(input.value || "").trim();
  if (!command) return;
  const button = $("logCommandSendBtn");
  if (button) button.disabled = true;
  try {
    const response = await fetch("/admin/debug-log-command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.error || `Failed to send debug command (${response.status})`);
    }
    rememberDebugLogCommand(command);
    input.value = "";
    clearDebugLogCommandCompletion();
  } catch (error) {
    alert(error?.message || String(error || ""));
  } finally {
    handleDebugLogCommandChange();
  }
}
function setDebugTransferBusy(nextBusy) {
  debugTransferBusy = !!nextBusy;
  handleDebugLogCommandChange();
}
function appendDebugTransferLogLine(text) {
  appendLogToSignature("debug", text);
}
function formatTransferSize(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  if (value >= 1024 * 1024 * 1024) return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GiB`;
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(2)} MiB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${Math.round(value)} B`;
}
function formatTransferMbps(bytes, startedAt) {
  const elapsedSeconds = Math.max((Date.now() - Number(startedAt || Date.now())) / 1000, 0.001);
  return ((Number(bytes || 0) * 8) / 1000000 / elapsedSeconds).toFixed(2);
}
function logTransferProgress(prefix, loaded, total, startedAt, tracker) {
  const totalBytes = Number(total || 0);
  const loadedBytes = Number(loaded || 0);
  if (!totalBytes || !Number.isFinite(totalBytes) || totalBytes <= 0) return;
  const percent = Math.max(0, Math.min(100, Math.floor((loadedBytes / totalBytes) * 100)));
  if (loadedBytes < totalBytes && percent < tracker.nextPercent) return;
  appendDebugTransferLogLine(
    `${prefix} ${percent}% (${formatTransferSize(loadedBytes)} / ${formatTransferSize(totalBytes)}) at ${formatTransferMbps(loadedBytes, startedAt)} Mbit/s`,
  );
  while (tracker.nextPercent <= percent) tracker.nextPercent += 5;
}
async function requestDebugTransferPlan(mode, entries) {
  const response = await fetch("/admin/debug-transfer/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, entries }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload?.ok) {
    throw new Error(payload?.error || `Failed to prepare ${mode} transfer (${response.status})`);
  }
  return payload;
}
function beginDebugTransferUploadPress(event) {
  if (event && event.button !== undefined && event.button !== 0) return;
  cancelDebugTransferUploadPress();
  debugTransferUploadLongPressConsumed = false;
  debugTransferUploadLongPressTimer = setTimeout(() => {
    debugTransferUploadLongPressTimer = 0;
    debugTransferUploadLongPressConsumed = true;
    openDebugTransferUploadPicker({ __longPress: true });
  }, 700);
}
function cancelDebugTransferUploadPress() {
  if (debugTransferUploadLongPressTimer) clearTimeout(debugTransferUploadLongPressTimer);
  debugTransferUploadLongPressTimer = 0;
}
function openDebugTransferUploadPicker(event) {
  if (!debugLogCommandEnabled() || debugTransferBusy) return;
  cancelDebugTransferUploadPress();
  if (debugTransferUploadLongPressConsumed && !event?.__longPress) {
    debugTransferUploadLongPressConsumed = false;
    return;
  }
  if (event?.__longPress) debugTransferUploadLongPressConsumed = false;
  const input = event?.shiftKey || event?.__longPress ? $("logTransferUploadFolderInput") || $("logTransferUploadInput") : $("logTransferUploadInput");
  input?.click();
}
async function handleDebugTransferUploadSelect(event) {
  const input = event?.target;
  const files = [...(input?.files || [])];
  if (input) input.value = "";
  if (!files.length) return;
  try {
    const plan = await requestDebugTransferPlan("upload", files.map((file) => file.name));
    const rows = Array.isArray(plan?.files) ? plan.files : [];
    const body = `<div>Upload ${files.length} file${files.length === 1 ? "" : "s"} into the current debug-shell folder?</div><div class="preset-help"><strong>Current folder:</strong> <code>${escapeHtml(plan.cwd || "")}</code></div><div class="preset-help">${rows
      .map(
        (row) =>
          `${escapeHtml(row.name || "")} -> <code>${escapeHtml(row.resolved_path || "")}</code>${row.exists ? " (overwrite)" : ""}`,
      )
      .join("<br>")}</div>`;
    openPresetActionModal({
      title: "Confirm Upload",
      body,
      confirmLabel: "Upload",
      confirmClass: "green",
      onConfirm: async () => {
        await uploadDebugTransferFiles(files, rows);
      },
    });
  } catch (error) {
    alert(error?.message || String(error || ""));
  }
}
function uploadDebugTransferFile(file, planRow) {
  return new Promise((resolve, reject) => {
    const startedAt = Date.now();
    const tracker = { nextPercent: 5 };
    const xhr = new XMLHttpRequest();
    xhr.open(
      "POST",
      `/admin/debug-transfer/upload?name=${encodeURIComponent(planRow?.name || file?.name || "upload.bin")}`,
    );
    xhr.responseType = "json";
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        logTransferProgress(
          `[debug-transfer upload] ${planRow?.name || file?.name || "file"}`,
          event.loaded,
          event.total,
          startedAt,
          tracker,
        );
      }
    });
    xhr.onerror = () => reject(new Error(`Upload failed for ${file?.name || "file"}.`));
    xhr.onload = () => {
      const payload = xhr.response && typeof xhr.response === "object"
        ? xhr.response
        : JSON.parse(String(xhr.responseText || "{}") || "{}");
      if (xhr.status < 200 || xhr.status >= 300 || !payload?.ok) {
        reject(new Error(payload?.error || `Upload failed for ${file?.name || "file"} (${xhr.status}).`));
        return;
      }
      logTransferProgress(
        `[debug-transfer upload] ${planRow?.name || file?.name || "file"}`,
        Number(file?.size || 0),
        Number(file?.size || 0),
        startedAt,
        tracker,
      );
      appendDebugTransferLogLine(
        `[debug-transfer upload] completed ${planRow?.name || file?.name || "file"} -> ${payload?.resolved_path || planRow?.resolved_path || ""}`,
      );
      resolve(payload);
    };
    xhr.send(file);
  });
}
async function uploadDebugTransferFiles(files, rows) {
  setDebugTransferBusy(true);
  try {
    appendDebugTransferLogLine(
      `[debug-transfer upload] starting ${files.length} file${files.length === 1 ? "" : "s"}`,
    );
    for (let index = 0; index < files.length; index += 1) {
      await uploadDebugTransferFile(files[index], rows[index] || {});
    }
  } finally {
    setDebugTransferBusy(false);
  }
}
function parseDownloadNameFromHeaders(headerValue) {
  const value = String(headerValue || "");
  const starMatch = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (starMatch) return decodeURIComponent(starMatch[1]);
  const plainMatch = value.match(/filename=\"?([^\";]+)\"?/i);
  return plainMatch ? plainMatch[1] : "";
}
function triggerBrowserDownload(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName || "club3090-download.bin";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
function runDebugTransferDownload(plan) {
  return new Promise((resolve, reject) => {
    const startedAt = Date.now();
    const tracker = { nextPercent: 5 };
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/admin/debug-transfer/download");
    xhr.responseType = "blob";
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        logTransferProgress(
          `[debug-transfer download] ${plan?.files?.length === 1 ? plan.files[0]?.download_name || "file" : plan?.archive_name || "archive"}`,
          event.loaded,
          event.total,
          startedAt,
          tracker,
        );
      }
    });
    xhr.onerror = () => reject(new Error("Download failed."));
    xhr.onload = async () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        const text = await xhr.response.text().catch(() => "");
        let payload = {};
        try {
          payload = JSON.parse(text || "{}");
        } catch (error) {}
        reject(new Error(payload?.error || `Download failed (${xhr.status}).`));
        return;
      }
      const fileName =
        parseDownloadNameFromHeaders(xhr.getResponseHeader("Content-Disposition")) ||
        (plan?.files?.length === 1 ? plan.files[0]?.download_name : plan?.archive_name) ||
        "club3090-download.bin";
      const total = Number(xhr.response?.size || 0);
      if (total > 0) {
        logTransferProgress(`[debug-transfer download] ${fileName}`, total, total, startedAt, tracker);
      }
      triggerBrowserDownload(xhr.response, fileName);
      appendDebugTransferLogLine(`[debug-transfer download] completed ${fileName}`);
      resolve();
    };
    xhr.send(
      JSON.stringify({
        paths: (plan?.files || []).map((row) => row?.requested_path || row?.resolved_path || ""),
      }),
    );
  });
}
async function downloadDebugTransferFiles() {
  if (!debugLogCommandEnabled() || debugTransferBusy) return;
  const requested = String($("logCommandInput")?.value || "")
    .replace(/\r/g, "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (!requested.length) return;
  try {
    const plan = await requestDebugTransferPlan("download", requested);
    if (Array.isArray(plan?.missing_paths) && plan.missing_paths.length) {
      throw new Error(`Missing file(s): ${plan.missing_paths.join(", ")}`);
    }
    const rows = Array.isArray(plan?.files) ? plan.files : [];
    const body = `<div>Download ${rows.length} file${rows.length === 1 ? "" : "s"} from the current debug-shell folder context?</div><div class="preset-help"><strong>Current folder:</strong> <code>${escapeHtml(plan.cwd || "")}</code></div><div class="preset-help">${rows
      .map(
        (row) =>
          `${escapeHtml(row.requested_path || "")} -> <code>${escapeHtml(row.resolved_path || "")}</code> (${escapeHtml(formatTransferSize(row.size_bytes || 0))})`,
      )
      .join("<br>")}</div>`;
    openPresetActionModal({
      title: rows.length === 1 ? "Confirm Download" : "Confirm Multi-File Download",
      body,
      confirmLabel: rows.length === 1 ? "Download" : "Download Zip",
      confirmClass: "green",
      onConfirm: async () => {
        setDebugTransferBusy(true);
        try {
          appendDebugTransferLogLine(
            `[debug-transfer download] starting ${rows.length} file${rows.length === 1 ? "" : "s"}`,
          );
          await runDebugTransferDownload(plan);
        } finally {
          setDebugTransferBusy(false);
        }
      },
    });
  } catch (error) {
    alert(error?.message || String(error || ""));
  }
}
currentLogHeading = function () {
  if (currentLogSource === "update") return "Update Logs";
  if (currentLogSource === "control") return "Web UI Server Logs";
  if (currentLogSource === "audit") return "Audit Logs";
  if (currentLogSource === "debug") return "Debug Logs";
  if (currentLogSource === "benchmarks") return "Benchmark Logs";
  if (currentLogSource === "script") return "Script Logs";
  if (String(currentLogSource || "").startsWith("model:")) {
    const modelSource = modelLogSourceFromSource(currentLogSource);
    return `${String(modelSource?.label || "Model Service").replace(/^Model:\s*/, "")} Logs`;
  }
  if (String(currentLogSource || "").startsWith("service:")) {
    const serviceId = String(currentLogSource).split(":", 2)[1] || "";
    const service = (lastStatus?.upstream_services || []).find(
      (row) => String(row?.id || "") === serviceId,
    );
    return `${String(service?.display_name || serviceId || "Service")} Logs`;
  }
  return "Runtime Docker Logs";
};
currentLogLabel = function () {
  if (currentLogSource === "update") return "source: updater";
  if (currentLogSource === "control") return "source: web ui server";
  if (currentLogSource === "audit") return "source: audit";
  if (currentLogSource === "debug") return "source: debug";
  if (currentLogSource === "benchmarks") return "source: benchmarks";
  if (currentLogSource === "script") return "source: script";
  if (String(currentLogSource || "").startsWith("model:")) {
    const modelSource = modelLogSourceFromSource(currentLogSource);
    return `source: ${modelSource?.label || "model service"}`;
  }
  if (String(currentLogSource || "").startsWith("service:")) {
    const serviceId = String(currentLogSource).split(":", 2)[1] || "";
    const service = (lastStatus?.upstream_services || []).find(
      (row) => String(row?.id || "") === serviceId,
    );
    return `source: ${service?.display_name || serviceId || "service"}`;
  }
  const selected = selectedDockerLogInstanceOption();
  if (selected) return "instance: " + selected.label;
  const cur = dockerLogTarget();
  return "instance: " + ((cur && cur.id) || "primary");
};
function renderLogInstanceSelector() {
  const select = $("logInstanceSelect");
  const label = $("logInstanceLabel");
  if (!select || !label) return;
  if (currentLogSource !== "docker") {
    select.innerHTML = "";
    delete select.dataset.renderedOptions;
    select.classList.add("hidden");
    label.classList.remove("hidden");
    label.textContent = currentLogLabel();
    return;
  }
  const options = dockerLogInstanceOptions();
  if (!options.length) {
    select.innerHTML = "";
    delete select.dataset.renderedOptions;
    select.classList.add("hidden");
    label.classList.remove("hidden");
    label.textContent = currentLogLabel();
    return;
  }
  const current = selectedDockerLogInstanceId();
  const html = options
    .map(
      (row) =>
        `<option value="${escapeHtml(row.id)}"${row.id === current ? " selected" : ""}>${escapeHtml(row.label)}</option>`,
    )
    .join("");
  setSelectOptions(select, html);
  if (current && select.value !== current) select.value = current;
  const showSelect = options.length > 1;
  select.classList.toggle("hidden", !showSelect);
  label.classList.toggle("hidden", showSelect);
  label.textContent = currentLogLabel();
}
function trimLogText(text) {
  const value = String(text || "");
  return value.length > 900000 ? value.slice(-750000) : value;
}
function logSourceNameFromSignature(signature = "") {
  const value = String(signature || "").trim().toLowerCase();
  if (!value) return "docker";
  if (value === "audit" || value === "debug") return value;
  if (value === "benchmarks") return "benchmarks";
  if (value.startsWith("script:")) return "script";
  if (value.startsWith("update:")) return "update";
  if (value.startsWith("service:")) return "service";
  if (value.startsWith("docker:")) return "docker";
  return value;
}
function suppressUiLogLine(source, line) {
  const text = String(line || "");
  if (source === "audit" && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[system\] Debug\b/.test(text)) {
    return true;
  }
  return false;
}
function filterUiLogText(signature, text) {
  const source = logSourceNameFromSignature(signature);
  if (!text || (source !== "audit" && source !== "debug")) return String(text || "");
  const raw = String(text || "");
  const hasTrailingNewline = raw.endsWith("\n");
  const filtered = raw
    .split("\n")
    .filter((line) => !suppressUiLogLine(source, line))
    .join("\n");
  if (!filtered) return "";
  return hasTrailingNewline ? `${filtered}\n` : filtered;
}
function currentLogPopupTarget() {
  const cfg = logStreamConfig();
  return {
    signature: cfg.signature,
    url: cfg.url,
    source: String(currentLogSource || "docker"),
    title: currentLogHeading(),
    label: currentLogLabel(),
  };
}
function logPopoutButtonSvg(detached = false) {
  return detached
    ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 19H5v-5m0 5 7-7" fill="none" /><path d="M14 17h3a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H9a2 2 0 0 0-2 2v3" fill="none" /></svg>'
    : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 5h5v5m0-5-7 7" fill="none" /><path d="M10 7H7a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-3" fill="none" /></svg>';
}
function currentLogSettingsKey() {
  return currentLogPopupTarget().signature || String(currentLogSource || "docker");
}
function currentLogGlobalEnabled() {
  const key = currentLogSettingsKey();
  if (Object.prototype.hasOwnProperty.call(showGlobalLogSources, key)) {
    return !!showGlobalLogSources[key];
  }
  return !!showGlobalLogs;
}
function currentLogSourceDetached() {
  return popupLogWindowOpen(currentLogPopupTarget().signature);
}
function logViewerVisible() {
  return !currentLogSourceDetached() && (activeTabName === "logs" || effectiveShowGlobalLogs());
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
  const entry = logCacheEntry(signature);
  const nextValue = entry.loaded ? collapseRepeatedLogText(entry.text) : "Connecting...\n";
  const changed = !!box && box.value !== nextValue;
  if (box) {
    if (changed) box.value = nextValue;
    if (searchState.active) {
      if (changed) recalculateMatches(true);
    } else if (changed && options.follow && $("autoscroll") && $("autoscroll").checked) {
      scrollLogToBottom(box);
    }
  }
  flushPendingLogJump();
  syncDetachedLogPopup(signature);
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
  entry.text = trimLogText(filterUiLogText(signature, text || ""));
  entry.loaded = true;
  if (signature === currentLogSignature) renderCurrentLog(signature, { follow: shouldFollow });
  else syncDetachedLogPopup(signature);
}
function appendLogChunk(signature, text) {
  if (!text) return;
  const entry = logCacheEntry(signature);
  const box = signature === currentLogSignature ? $("log") : null;
  const shouldFollow = !!box && !!$("autoscroll")?.checked && logIsNearBottom(box);
  entry.text = trimLogText((entry.text || "") + filterUiLogText(signature, text));
  entry.loaded = true;
  if (signature === currentLogSignature) renderCurrentLog(signature, { follow: shouldFollow });
  else syncDetachedLogPopup(signature);
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
  document.body.classList.toggle("log-popup-open", popupLogWindowOpen());
  document.body.classList.remove("audit-tab");
  const card = document.querySelector(".logs.panel");
  const currentPopup = currentLogPopupTarget();
  const detached = popupLogWindowOpen(currentPopup.signature);
  if (card)
    card.classList.toggle(
      "log-card-hidden",
      detached || (!isLogs && !effectiveShowGlobalLogs()),
    );
  if (card) card.classList.toggle("log-card-update-mode", currentLogSource === "update");
  if ($("logTitle")) $("logTitle").textContent = currentLogHeading();
  if ($("showGlobalLogs")) {
    $("showGlobalLogs").checked = effectiveShowGlobalLogs();
    $("showGlobalLogs").disabled = currentLogSourceDetached();
  }
  if ($("logPopoutBtn")) {
    const updatePopoutBlocked = updateMonitor.active && currentLogSource === "update";
    $("logPopoutBtn").title = detached ? "Reattach logs" : "Pop out logs";
    $("logPopoutBtn").setAttribute("aria-label", $("logPopoutBtn").title);
    $("logPopoutBtn").classList.toggle("active", detached);
    $("logPopoutBtn").classList.toggle("hidden", updatePopoutBlocked);
    $("logPopoutBtn").disabled = updatePopoutBlocked;
    $("logPopoutBtn").setAttribute("aria-hidden", updatePopoutBlocked ? "true" : "false");
    $("logPopoutBtn").innerHTML = logPopoutButtonSvg(detached);
  }
  renderLogInstanceSelector();
  renderLogSourcePanel();
  renderLogTracker();
  if (currentLogSignature) renderCurrentLog(currentLogSignature);
  if (!logViewerVisible() && logEs) {
    try {
      logEs.close();
    } catch (e) {}
    logEs = null;
  }
  syncAllDetachedLogPopups();
  applyMetricsVisibility();
};
function logStreamConfig() {
  if (currentLogSource === "update") {
    if (!updateMonitor.streamUrl && !updateMonitor.token) {
      return {
        signature: "update:pending",
        url: "",
      };
    }
    return {
      signature: `update:${updateMonitor.token || "active"}`,
      url: updateMonitor.streamUrl || "/admin/update-stream",
    };
  }
  if (currentLogSource === "control")
    return { signature: "control", url: "/admin/control-stream?tail=4000" };
  if (currentLogSource === "audit")
    return { signature: "audit", url: "/admin/audit-stream?tail=4000" };
  if (currentLogSource === "debug")
    return { signature: "debug", url: "/admin/debug-stream?tail=4000" };
  if (currentLogSource === "benchmarks")
    return { signature: "benchmarks", url: "/admin/logs?source=benchmarks&tail=4000" };
  if (currentLogSource === "script")
    return { signature: `script:${lastStatus?.script_job?.job_id || "latest"}`, url: "/admin/logs?source=script&tail=4000" };
  if (String(currentLogSource || "").startsWith("service:")) {
    const serviceId = String(currentLogSource).split(":", 2)[1] || "";
    return {
      signature: `service:${serviceId}`,
      url: `/admin/logs?source=service&service=${encodeURIComponent(serviceId)}`,
    };
  }
  if (String(currentLogSource || "").startsWith("model:")) {
    const modelSource = modelLogSourceFromSource(currentLogSource);
    const instanceId = modelSource?.instanceId || "";
    return {
      signature: `model:${instanceId || "primary"}`,
      url: `/admin/logs${instanceId ? `?instance=${encodeURIComponent(instanceId)}` : ""}`,
    };
  }
  const explicit = selectedDockerLogInstanceId();
  const tracked = explicit
    ? runtimeTrackingItems().find(
        (row) => String(row?.id || row?.instance_id || "").trim().toUpperCase() === explicit,
      )
    : null;
  const target = tracked || dockerLogTarget();
  const instanceId = explicit
    ? explicit
    : tracked && (tracked.id || tracked.instance_id)
      ? tracked.id || tracked.instance_id
      : target && target.id;
  return {
    signature: `docker:${instanceId || "primary"}`,
    url: `/admin/logs${instanceId ? `?instance=${encodeURIComponent(instanceId)}` : ""}`,
  };
}
function noteKnownLogSource(source) {
  const normalized =
    source === "audit" ||
    source === "control" ||
    source === "debug" ||
    source === "benchmarks" ||
    source === "script" ||
    source === "docker" ||
    source === "update" ||
    String(source || "").startsWith("model:") ||
    String(source || "").startsWith("service:")
      ? String(source)
      : "docker";
  knownLogSources.add(normalized);
  return normalized;
}
function logSignatureForSource(source) {
  const previousSource = currentLogSource;
  try {
    currentLogSource = String(source || "docker");
    return logStreamConfig().signature;
  } finally {
    currentLogSource = previousSource;
  }
}
function logBootstrapUrlForSource(source) {
  const normalized = noteKnownLogSource(source);
  if (normalized === "update") return null;
  if (normalized === "audit") return "/admin/log-bootstrap?source=audit&tail=250";
  if (normalized === "control") return "/admin/log-bootstrap?source=control&tail=250";
  if (normalized === "debug") return "/admin/log-bootstrap?source=debug&tail=250";
  if (normalized === "benchmarks") return "/admin/log-bootstrap?source=benchmarks&tail=250";
  if (normalized === "script") return "/admin/log-bootstrap?source=script&tail=250";
  if (String(normalized).startsWith("service:")) {
    const serviceId = String(normalized).split(":", 2)[1] || "";
    return `/admin/log-bootstrap?source=service&service=${encodeURIComponent(serviceId)}&tail=250`;
  }
  if (String(normalized).startsWith("model:")) {
    const modelSource = modelLogSourceFromSource(normalized);
    const instanceId = modelSource?.instanceId || "";
    return `/admin/log-bootstrap${instanceId ? `?instance=${encodeURIComponent(instanceId)}&tail=250` : "?tail=250"}`;
  }
  const explicit = selectedDockerLogInstanceId();
  const tracked = explicit
    ? runtimeTrackingItems().find(
        (row) => String(row?.id || row?.instance_id || "").trim().toUpperCase() === explicit,
      )
    : null;
  const target = tracked || dockerLogTarget();
  const instanceId = explicit
    ? explicit
    : tracked && (tracked.id || tracked.instance_id)
      ? tracked.id || tracked.instance_id
      : target && target.id;
  return `/admin/log-bootstrap${instanceId ? `?instance=${encodeURIComponent(instanceId)}&tail=250` : "?tail=250"}`;
}
async function refreshLogCacheSnapshot(source, options = {}) {
  const url = logBootstrapUrlForSource(source);
  if (!url) return;
  const response = await fetchJsonWithTimeout(
    `${url}${url.includes("?") ? "&" : "?"}_=${Date.now()}`,
    { cache: "no-store" },
    12000,
  );
  if (!response.ok) return;
  const payload = await response.json();
  const signature = payload?.signature || options.signature || logSignatureForSource(source);
  replaceLogBuffer(signature, String(payload?.text || ""));
}
async function refreshBackgroundLogCaches() {
  const currentSource = String(currentLogSource || "docker");
  const ordered = logViewerVisible()
    ? Array.from(knownLogSources).filter((source) => source !== currentSource)
    : [currentSource, ...Array.from(knownLogSources).filter((source) => source !== currentSource)];
  for (const source of ordered) {
    if (source === "update") continue;
    try {
      await refreshLogCacheSnapshot(source, { signature: logSignatureForSource(source) });
    } catch (e) {}
  }
}
function scheduleLogCacheRefresh(delayMs = LOG_CACHE_REFRESH_MS) {
  logCacheRefreshNonce += 1;
  if (logCacheRefreshTimer) clearInterval(logCacheRefreshTimer);
  const delay = Math.max(LOG_CACHE_REFRESH_MS, Number(delayMs || LOG_CACHE_REFRESH_MS));
  logCacheRefreshTimer = setInterval(() => {
    refreshBackgroundLogCaches().catch(() => {});
  }, delay);
  if (delayMs === 0) refreshBackgroundLogCaches().catch(() => {});
}
function scheduleLogStreamReconnect(delayMs = 5000) {
  if (logReconnectTimer) clearTimeout(logReconnectTimer);
  logReconnectTimer = setTimeout(() => {
    logReconnectTimer = null;
    if (logViewerVisible()) connectLogs(false);
  }, Math.max(1000, Number(delayMs || 5000)));
}
function currentLogExportRequest() {
  if (currentLogSource === "update") {
    return { source: "update", instance_id: null };
  }
  if (currentLogSource === "control") {
    return { source: "control", instance_id: null };
  }
  if (currentLogSource === "audit") {
    return { source: "audit", instance_id: null };
  }
  if (currentLogSource === "debug") {
    return { source: "debug", instance_id: null };
  }
  if (String(currentLogSource || "").startsWith("model:")) {
    const modelSource = modelLogSourceFromSource(currentLogSource);
    return { source: "docker", instance_id: modelSource?.instanceId || null };
  }
  if (String(currentLogSource || "").startsWith("service:")) {
    const serviceId = String(currentLogSource).split(":", 2)[1] || "";
    return { source: "service", service_id: serviceId, instance_id: null };
  }
  if (currentLogSignature && currentLogSignature.startsWith("docker:")) {
    const fromSignature = currentLogSignature.slice("docker:".length);
    if (fromSignature && fromSignature !== "primary") {
      return { source: "docker", instance_id: fromSignature };
    }
  }
  const explicit = selectedDockerLogInstanceId();
  if (explicit) return { source: "docker", instance_id: explicit };
  const target = dockerLogTarget();
  const instanceId =
    target && target.id;
  return { source: "docker", instance_id: instanceId || null };
}
function detachedPopupDockerInstanceId(state) {
  const signature = String(state?.signature || "");
  if (!signature.startsWith("docker:")) return "";
  return signature.slice("docker:".length) || "";
}
function detachedPopupDockerOptions(state) {
  return String(state?.source || "") === "docker" ? dockerLogInstanceOptions() : [];
}
function replaceDetachedLogPopupDockerInstance(signature, instanceId) {
  const state = window.logPopupStates[String(signature || "")];
  const nextId = normalizeDockerLogInstanceId(instanceId);
  if (!state || !nextId) return false;
  const keepAutoscroll = state.autoscroll !== false;
  closeDetachedLogPopup(signature);
  setDockerLogInstance(nextId);
  const target = currentLogPopupTarget();
  const nextState = popupLogState(target.signature);
  nextState.autoscroll = keepAutoscroll;
  ensureDetachedLogPopupWindow(nextState);
  nextState.lastActiveAt = Date.now();
  renderDetachedLogPopup(nextState);
  syncDetachedLogPopupStream(nextState);
  applyLogVisibility();
  connectLogs(false);
  return true;
}
function popupWindowNameForLogSignature(signature) {
  const token = String(signature || "log")
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `club3090-log-${token || "viewer"}`;
}
function detachedLogPopupHtml(state) {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>${escapeHtml(state?.title || "Logs")}</title>
    <style>
      :root { color-scheme: dark; --bg:#0b0f14; --panel:#121923; --line:#273243; --text:#e8eef7; --muted:#9dafc3; --field:#030608; }
      * { box-sizing: border-box; }
      html, body { margin:0; min-height:100%; background:var(--bg); color:var(--text); font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif; overflow:hidden; }
      body { padding:12px; }
      .popup-card { height:calc(100vh - 24px); display:flex; flex-direction:column; gap:10px; background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:12px; }
      .popup-head { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; }
      .popup-title-row { display:flex; align-items:center; gap:8px; }
      .popup-title { font-size:20px; font-weight:800; margin:0; }
      .popup-meta { color:var(--muted); font-size:12px; line-height:1.35; }
      .popup-actions { display:flex; align-items:center; gap:8px; }
      .popup-select { min-width:180px; max-width:320px; background:rgba(6,10,16,.98); color:var(--text); border:1px solid var(--line); border-radius:10px; padding:6px 10px; font:600 12px/1.2 system-ui,-apple-system,Segoe UI,Arial,sans-serif; }
      .popup-select.hidden { display:none; }
      .popup-btn { display:inline-flex; align-items:center; justify-content:center; width:20px; height:20px; padding:0; border:0; background:transparent; color:var(--muted); cursor:pointer; }
      .popup-btn:hover, .popup-btn:focus-visible { color:#eef4ff; outline:none; }
      .popup-btn svg { width:18px; height:18px; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; fill:none; }
      .popup-check { display:inline-flex; align-items:center; gap:8px; color:var(--muted); font-size:12px; }
      .popup-check input { margin:0; }
      .popup-log { flex:1 1 auto; width:100%; min-height:180px; resize:none; white-space:pre-wrap; overflow-wrap:anywhere; background:var(--field); color:#a5ffa5; border:1px solid #26313f; border-radius:12px; padding:12px; font:12px/1.35 Consolas,monospace; }
      .popup-log.log-update { color:#ffb347; border-color:#8a652b; box-shadow:inset 0 0 0 1px rgba(255,179,71,.14); }
    </style>
  </head>
  <body>
    <div class="popup-card">
      <div class="popup-head">
        <div>
          <div class="popup-title-row">
            <button class="popup-btn" type="button" id="popupReattachBtn" title="Reattach logs" aria-label="Reattach logs">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M10 19H5v-5m0 5 7-7" />
                <path d="M14 17h3a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H9a2 2 0 0 0-2 2v3" />
              </svg>
            </button>
            <h1 class="popup-title" id="popupLogTitle">Logs</h1>
          </div>
          <div class="popup-meta" id="popupLogLabel"></div>
        </div>
        <div class="popup-actions">
          <select id="popupInstanceSelect" class="popup-select hidden" aria-label="Detached Docker log target"></select>
          <label class="popup-check"><input type="checkbox" id="popupAutoscroll" checked />auto-scroll</label>
        </div>
      </div>
      <textarea class="popup-log" id="popupLogText" readonly wrap="soft">Connecting...</textarea>
    </div>
    <script>
      (() => {
        const signature = ${JSON.stringify(String(state?.signature || ""))};
        const notify = () => {
          try {
            if (window.opener && !window.opener.closed && typeof window.opener.markDetachedLogPopupActive === "function") {
              window.opener.markDetachedLogPopupActive(signature);
            }
          } catch (e) {}
        };
        window.addEventListener("focus", notify);
        window.addEventListener("pointerdown", notify, true);
        window.addEventListener("keydown", notify, true);
        document.addEventListener("visibilitychange", notify);
        document.getElementById("popupReattachBtn")?.addEventListener("click", () => {
          try {
            if (window.opener && !window.opener.closed && typeof window.opener.closeDetachedLogPopup === "function") {
              window.opener.closeDetachedLogPopup(signature);
            } else {
              window.close();
            }
          } catch (e) {
            window.close();
          }
        });
        document.getElementById("popupAutoscroll")?.addEventListener("change", (event) => {
          try {
            if (window.opener && !window.opener.closed && typeof window.opener.setDetachedLogPopupAutoscroll === "function") {
              window.opener.setDetachedLogPopupAutoscroll(signature, !!event.target?.checked);
            }
          } catch (e) {}
          notify();
        });
        document.getElementById("popupInstanceSelect")?.addEventListener("change", (event) => {
          try {
            if (window.opener && !window.opener.closed && typeof window.opener.replaceDetachedLogPopupDockerInstance === "function") {
              const changed = window.opener.replaceDetachedLogPopupDockerInstance(signature, String(event.target?.value || ""));
              if (changed) {
                window.close();
                return;
              }
            }
          } catch (e) {}
          notify();
        });
        window.addEventListener("beforeunload", () => {
          try {
            if (window.opener && !window.opener.closed && typeof window.opener.notifyDetachedLogPopupClosed === "function") {
              window.opener.notifyDetachedLogPopupClosed(signature);
            }
          } catch (e) {}
        });
        notify();
      })();
    <\/script>
  </body>
</html>`;
}
function popupLogDocument(state) {
  const win = state?.win;
  if (!win || win.closed) return null;
  try {
    return win.document || null;
  } catch (e) {
    return null;
  }
}
function ensureDetachedLogPopupWindow(state) {
  if (!state) return null;
  if (state.win && !state.win.closed) return state.win;
  const features = [
    "popup=yes",
    "toolbar=no",
    "location=no",
    "menubar=no",
    "status=no",
    "resizable=yes",
    "scrollbars=no",
    `width=${LOG_POPUP_WIDTH}`,
    `height=${LOG_POPUP_HEIGHT}`,
  ].join(",");
  const win = window.open("", popupWindowNameForLogSignature(state.signature), features);
  if (!win) throw new Error("The browser blocked the log popup window.");
  state.win = win;
  try {
    win.document.open();
    win.document.write(detachedLogPopupHtml(state));
    win.document.close();
  } catch (e) {}
  return win;
}
function renderDetachedLogPopup(state) {
  const doc = popupLogDocument(state);
  if (!doc) return;
  const title = doc.getElementById("popupLogTitle");
  const label = doc.getElementById("popupLogLabel");
  const box = doc.getElementById("popupLogText");
  const autoscroll = doc.getElementById("popupAutoscroll");
  const selector = doc.getElementById("popupInstanceSelect");
  if (doc.title !== String(state.title || "Logs")) doc.title = String(state.title || "Logs");
  if (title && title.textContent !== String(state.title || "Logs")) title.textContent = String(state.title || "Logs");
  if (label && label.textContent !== String(state.label || "")) label.textContent = String(state.label || "");
  if (autoscroll) autoscroll.checked = state.autoscroll !== false;
  if (selector) {
    const options = detachedPopupDockerOptions(state);
    const current = detachedPopupDockerInstanceId(state);
    const html = options
      .map(
        (row) =>
          `<option value="${escapeHtml(row.id)}"${row.id === current ? " selected" : ""}>${escapeHtml(row.label)}</option>`,
      )
      .join("");
    setSelectOptions(selector, html);
    if (current && selector.value !== current) selector.value = current;
    selector.classList.toggle("hidden", !(String(state.source || "") === "docker" && options.length > 1));
  }
  if (!box) return;
  const entry = logCacheEntry(state.signature);
  const nextValue = entry.loaded ? collapseRepeatedLogText(entry.text) : "Connecting...\n";
  const changed = box.value !== nextValue;
  if (changed) box.value = nextValue;
  box.classList.toggle("log-update", String(state.source || "") === "update");
  if ((changed || state.autoscroll) && state.autoscroll !== false) {
    box.scrollTop = box.scrollHeight;
  }
}
function markDetachedLogPopupActive(signature) {
  const state = window.logPopupStates[String(signature || "")];
  if (!state) return;
  state.lastActiveAt = Date.now();
}
function setDetachedLogPopupAutoscroll(signature, enabled) {
  const state = window.logPopupStates[String(signature || "")];
  if (!state) return;
  state.autoscroll = !!enabled;
  renderDetachedLogPopup(state);
}
function notifyDetachedLogPopupClosed(signature) {
  const state = window.logPopupStates[String(signature || "")];
  if (!state) return;
  state.win = null;
  if (state.es) {
    try {
      state.es.close();
    } catch (e) {}
    state.es = null;
  }
  delete window.logPopupStates[String(signature || "")];
  applyLogVisibility();
  connectLogs(false);
}
function pollDetachedLogPopupClosures() {
  Object.keys(window.logPopupStates).forEach((signature) => {
    const state = window.logPopupStates[String(signature || "")];
    if (!state) return;
    if (!state.win || state.win.closed) notifyDetachedLogPopupClosed(signature);
  });
}
function closeDetachedLogPopup(signature) {
  const key = String(signature || "");
  const state = window.logPopupStates[key];
  if (!state) return;
  if (state.es) {
    try {
      state.es.close();
    } catch (e) {}
    state.es = null;
  }
  const win = state.win;
  state.win = null;
  delete window.logPopupStates[key];
  if (win && !win.closed) {
    try {
      win.close();
    } catch (e) {}
  }
  applyLogVisibility();
  connectLogs(false);
}
function syncDetachedLogPopupStream(state) {
  if (!state || !state.win || state.win.closed) return;
  if (state.es && state.url === state._streamUrl) return;
  if (state.es) {
    try {
      state.es.close();
    } catch (e) {}
    state.es = null;
  }
  state._streamUrl = state.url;
  const es = new EventSource(state.url);
  state.es = es;
  const signature = state.signature;
  const handle = (mode, data) => {
    let payload = null;
    try {
      payload = JSON.parse(data || "{}");
    } catch (e) {}
    const text =
      payload && typeof payload.text === "string"
        ? payload.text
        : String(data || "").replaceAll("\\u0000", "\n");
    if (mode === "reset") replaceLogBuffer(signature, text);
    else appendLogChunk(signature, text);
  };
  es.addEventListener("reset", (event) => handle("reset", event.data));
  es.addEventListener("append", (event) => handle("append", event.data));
  es.onmessage = (event) => handle("append", event.data);
  es.onerror = () => {
    if (state.es) {
      try {
        state.es.close();
      } catch (e) {}
      state.es = null;
    }
    if (popupLogWindowOpen(signature)) {
      setTimeout(() => syncDetachedLogPopupStream(state), 5000);
    }
  };
}
function syncDetachedLogPopup(signature) {
  const state = window.logPopupStates[String(signature || "")];
  if (!state) return;
  const currentTarget = currentLogPopupTarget();
  if (currentTarget.signature === state.signature) {
    state.source = currentTarget.source;
    state.url = currentTarget.url;
    state.title = currentTarget.title;
    state.label = currentTarget.label;
  }
  if (!state.win || state.win.closed) {
    notifyDetachedLogPopupClosed(signature);
    return;
  }
  renderDetachedLogPopup(state);
  syncDetachedLogPopupStream(state);
}
function syncAllDetachedLogPopups() {
  Object.keys(window.logPopupStates).forEach((signature) => syncDetachedLogPopup(signature));
}
function toggleLogPopout() {
  if (updateMonitor.active && currentLogSource === "update") return;
  const target = currentLogPopupTarget();
  if (popupLogWindowOpen(target.signature)) {
    closeDetachedLogPopup(target.signature);
    return;
  }
  const state = popupLogState(target.signature);
  state.source = target.source;
  state.url = target.url;
  state.title = target.title;
  state.label = target.label;
  ensureDetachedLogPopupWindow(state);
  state.lastActiveAt = Date.now();
  renderDetachedLogPopup(state);
  syncDetachedLogPopupStream(state);
  applyLogVisibility();
  connectLogs(false);
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
  const visible = logViewerVisible();
  if (!visible && !force) return;
  const cfg = logStreamConfig();
  noteKnownLogSource(currentLogSource);
  if (!force && logEs && cfg.signature === currentLogSignature) {
    renderCurrentLog(cfg.signature);
    return;
  }
  currentLogSignature = cfg.signature;
  if (!cfg.url && cfg.signature === "update:pending") {
    replaceLogBuffer(cfg.signature, "Waiting for updater handoff...\n");
  }
  renderCurrentLog(cfg.signature, { follow: !!$("autoscroll")?.checked });
  updateLogVisualMode();
  renderDebugLogCommandUi();
  refreshLogCacheSnapshot(currentLogSource, { signature: cfg.signature }).catch(() => {});
  if (!cfg.url) {
    if (logEs) {
      try {
        logEs.close();
      } catch (e) {}
      logEs = null;
    }
    return;
  }
  if (!visible) return;
  if (logReconnectTimer) {
    clearTimeout(logReconnectTimer);
    logReconnectTimer = null;
  }
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
  es.addEventListener("status", (e) => {
    if (token !== logConnectToken) return;
    if (currentLogSource === "update") {
      try {
        const payload = JSON.parse(e.data || "{}");
        if (payload && payload.active === false) {
          completeUpdateMonitor(payload);
          return;
        }
      } catch (error) {}
    }
    if (currentLogSource === "update") updateLogVisualMode();
  });
  es.addEventListener("complete", (e) => {
    if (token !== logConnectToken) return;
    try {
      const payload = JSON.parse(e.data || "{}");
      completeUpdateMonitor(payload);
      return;
    } catch (error) {}
    triggerAdminPanelReload("Update completed. Reloading the admin panel...", 400);
  });
  es.onmessage = (e) => {
    if (token !== logConnectToken) return;
    handle("append", e.data);
  };
  es.onerror = () => {
    if (token !== logConnectToken) return;
    try {
      es.close();
    } catch (error) {}
    if (logEs === es) logEs = null;
    scheduleLogStreamReconnect(5000);
  };
};
setCurrentLogSource = function (source) {
  const nextSource =
    source === "audit" ||
    source === "debug" ||
    source === "docker" ||
    source === "benchmarks" ||
    source === "script" ||
    source === "control" ||
    source === "update" ||
    String(source || "").startsWith("model:") ||
    String(source || "").startsWith("service:")
      ? String(source)
      : "docker";
  if (selfUpdateActive(lastStatus) && nextSource !== "update") return;
  currentLogSource = nextSource;
  noteKnownLogSource(currentLogSource);
  applyLogVisibility();
  queueUiStateSave({ current_log_source: currentLogSource });
  connectLogs(true);
  scheduleLogCacheRefresh(LOG_CACHE_REFRESH_MS);
  updateLogVisualMode();
};
setShowGlobalLogs = function (v) {
  showGlobalLogs = !!v;
  showGlobalLogSources[currentLogSettingsKey()] = !!v;
  window.showGlobalLogSources = showGlobalLogSources;
  applyLogVisibility();
  queueUiStateSave({
    show_global_logs: showGlobalLogs,
    show_global_logs_by_source: { ...showGlobalLogSources },
  });
  connectLogs(false);
  scheduleLogCacheRefresh(logViewerVisible() ? LOG_CACHE_REFRESH_MS : 0);
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
function focusBenchmarkLogs() {
  if (currentLogSource !== "benchmarks") setCurrentLogSource("benchmarks");
  activateTab("logs", true);
}
function focusScriptLogs() {
  if (currentLogSource !== "script") setCurrentLogSource("script");
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
    if (runtime) return String(runtime.id || runtime.instance_id || "");
    const singles = singleScopeItems().filter(
      (row) => !selector || String(row?.mode || "") === String(selector),
    );
    return String((singles[0] && singles[0].id) || "");
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
  if (instanceId) selectedLogInstanceId = normalizeDockerLogInstanceId(instanceId);
  activateTab("logs", true);
  $("autoscroll").checked = !query;
  const resolvedId = selectedDockerLogInstanceId() || String(instanceId || "").trim().toUpperCase();
  pendingLogJump = {
    source: "docker",
    signature: `docker:${resolvedId || "primary"}`,
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
post = async function (path, obj, label = "", options = {}) {
  const requestLabel = label || `${path} ${JSON.stringify(obj || {})}`;
  const silentSuccess = !!options.silentSuccess;
  const silentFailure = !!options.silentFailure;
  if (!silentSuccess) syntheticLog(`request sent: ${requestLabel}`);
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
    if (payload && payload.focus_log_source === "audit") focusAuditLogs();
    if (payload && payload.focus_log_source === "benchmarks") focusBenchmarkLogs();
    if (payload && payload.focus_log_source === "script") focusScriptLogs();
    if (payload && payload.focus_log_source === "update") beginUpdateMonitor(payload, obj?.scope);
    if (!silentSuccess) {
      syntheticLog(`request finished: ${requestLabel}`);
      appendLogToSignature(
        "debug",
        `----- admin result -----\n${adminResultText(payload, text)}\n------------------------`,
      );
    }
    if (!(payload && payload.focus_log_source === "update")) refreshStatus().catch(() => {});
    return payload || text;
  } catch (e) {
    if (!silentFailure) {
      syntheticLog(`request failed: ${requestLabel} | ${e.message || e}`);
      appendLogToSignature(
        "debug",
        `----- admin error -----\n${e.message || e}\n-----------------------`,
      );
    }
    refreshStatus().catch(() => {});
    throw e;
  }
};
metricTab = function (e, n) {
  setActiveMetricPaneInDocument(document, n);
  writeCachedUiState(currentUiState());
  queueUiStateSave();
  redrawMetricsSoon();
  refreshStatus({ force: true }).catch(() => {});
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
  const mac = await openWakeOnLanModal();
  if (mac === null) return;
  try {
    await post("/admin/wol", { mac });
  } catch (e) {
    alert(e);
  }
}
function defaultWakeOnLanMac() {
  return String(lastStatus?.power?.wol_default_mac || "").trim();
}
function ensureWakeOnLanModal() {
  if ($("wakeOnLanModal")) return;
  const modal = document.createElement("div");
  modal.id = "wakeOnLanModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card conversation-modal-card wake-on-lan-modal-card" role="dialog" aria-modal="true" aria-labelledby="wakeOnLanTitle"><div class="panel-head"><h2 id="wakeOnLanTitle">Wake-on-LAN</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="cancelWakeOnLanModal()">✕</button></div><div class="preset-help">Send a magic packet to the configured remote machine.</div><div class="formgrid wake-on-lan-form-grid"><label>MAC Address<input id="wakeOnLanMacInput" class="club-text-field" placeholder="AA:BB:CC:DD:EE:FF" inputmode="text" autocomplete="off" spellcheck="false" /></label></div><div class="preset-form-actions"><button class="btn blue" onclick="cancelWakeOnLanModal()">Cancel</button><button class="btn green" onclick="submitWakeOnLanModal()">Wake Machine</button></div><div class="msg" id="wakeOnLanMsg"></div></div>`;
  document.body.appendChild(modal);
}
function normalizeWakeOnLanMac(value) {
  return String(value || "").trim().replace(/-/g, ":").toUpperCase();
}
function closeWakeOnLanModal() {
  $("wakeOnLanModal")?.classList.add("hidden");
}
function cancelWakeOnLanModal() {
  resolveWakeOnLanModal(null);
}
function openWakeOnLanModal() {
  ensureWakeOnLanModal();
  const input = $("wakeOnLanMacInput");
  if (input) input.value = defaultWakeOnLanMac();
  setElementMsg("wakeOnLanMsg", "");
  $("wakeOnLanModal")?.classList.remove("hidden");
  setTimeout(() => {
    input?.focus();
    input?.select();
  }, 0);
  return new Promise((resolve) => {
    window.__clubWakeOnLanResolve = resolve;
  });
}
function resolveWakeOnLanModal(value = null) {
  const resolver = window.__clubWakeOnLanResolve;
  window.__clubWakeOnLanResolve = null;
  closeWakeOnLanModal();
  if (typeof resolver === "function") resolver(value);
}
async function submitWakeOnLanModal() {
  const mac = normalizeWakeOnLanMac($("wakeOnLanMacInput")?.value || "");
  if (!mac) {
    setElementMsg("wakeOnLanMsg", "Enter a MAC address first.", "error");
    return;
  }
  if (!/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/.test(mac)) {
    setElementMsg("wakeOnLanMsg", "Use six hex pairs like AA:BB:CC:DD:EE:FF.", "error");
    return;
  }
  resolveWakeOnLanModal(mac);
}
let machineRestartLongPressTimer = null;
let machineRestartForceArmed = false;
function beginMachineRestartPress(event) {
  if (event?.button !== undefined && event.button !== 0) return;
  machineRestartForceArmed = false;
  if (machineRestartLongPressTimer) clearTimeout(machineRestartLongPressTimer);
  machineRestartLongPressTimer = setTimeout(() => {
    machineRestartForceArmed = true;
    $("restartMachineBtn")?.classList.add("force-armed");
  }, 900);
}
function endMachineRestartPress() {
  if (machineRestartLongPressTimer) clearTimeout(machineRestartLongPressTimer);
  machineRestartLongPressTimer = null;
}
function cancelMachineRestartPress() {
  if (machineRestartLongPressTimer) clearTimeout(machineRestartLongPressTimer);
  machineRestartLongPressTimer = null;
  machineRestartForceArmed = false;
  $("restartMachineBtn")?.classList.remove("force-armed");
}
async function machineAction(action, event = null) {
  const forceRestart = action === "reboot" && (!!event?.shiftKey || machineRestartForceArmed);
  machineRestartForceArmed = false;
  $("restartMachineBtn")?.classList.remove("force-armed");
  const label = forceRestart ? "FORCE RESTART" : action === "reboot" ? "RESTART" : "SHUT DOWN";
  const firstPrompt = forceRestart
    ? "Force restart machine now? This bypasses graceful shutdown and is intended for unrecoverable GPU/driver failures."
    : label + " machine now?";
  const secondPrompt = forceRestart
    ? "Final confirmation: FORCE RESTART now. This is equivalent to pressing the case reset button."
    : "Final confirmation: " + label + " now.";
  if (!(await openClubConfirmModal(firstPrompt))) return;
  if (!(await openClubConfirmModal(secondPrompt))) return;
  try {
    await post("/admin/machine", { action: forceRestart ? "force_reboot" : action });
  } catch (e) {
    alert(e);
  }
}
function syncActiveTabDisplay() {
  applyLocationUiStateOverride();
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
  applyMetricsVisibility();
}
