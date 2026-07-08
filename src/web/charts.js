// Base chart rendering
function tempColorForValue(value, sensor = "core") {
  const temp = Number(value || 0);
  const kind = String(sensor || "core").toLowerCase();
  if (kind === "junction" || kind === "hotspot" || kind === "vram" || kind === "memory") {
    if (temp < 45) return "#60a5fa";
    if (temp < 65) return "#2fc46b";
    if (temp < 80) return "#ffde59";
    if (temp < 90) return "#ff8a2a";
    if (temp < 95) return "#ff5b6c";
    return "#dc143c";
  }
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
function seriesPeakValue(series = [], key, fallbackKey = "") {
  let peak = 0;
  (series || []).forEach((row) => {
    const direct = Number(row?.[key]);
    const fallback = fallbackKey ? Number(row?.[fallbackKey]) : NaN;
    const value = Number.isFinite(direct)
      ? direct
      : Number.isFinite(fallback)
        ? fallback
        : 0;
    peak = Math.max(peak, value);
  });
  return peak;
}
function formatMbpsValue(value, digits = 2) {
  return `${formatChartValue(value, digits)} Mbps`;
}
function persistentMetricPeakValue(status, key) {
  const peaks = status?.system_metric_peaks;
  const value = Number(peaks?.charts?.[key] || 0);
  return Number.isFinite(value) && value > 0 ? value : 0;
}
function persistentGpuMetricPeakValue(status, index, key) {
  const peaks = status?.system_metric_peaks;
  const row = peaks?.gpus?.[String(index)] || {};
  const value = Number(row?.[key] || 0);
  return Number.isFinite(value) && value > 0 ? value : 0;
}
window.metricsPopupStates = window.metricsPopupStates || Object.create(null);
let detachedMetricsPopupClosedPollTimer = null;
let metricsRenderDocument = null;
let detachedMetricsHostSignature = "";
var METRICS_POPUP_WIDTH = 1280;
var METRICS_POPUP_HEIGHT = 920;
function metricsElement(id) {
  const doc = metricsRenderDocument || document;
  return doc?.getElementById ? doc.getElementById(id) : null;
}
function popupMetricsState(signature) {
  if (!signature) return null;
  if (!window.metricsPopupStates[signature]) {
    window.metricsPopupStates[signature] = {
      signature,
      paneId: "mMain",
      title: "Metrics",
      label: "Main",
      win: null,
      lastActiveAt: 0,
    };
  }
  return window.metricsPopupStates[signature];
}
function popupMetricsWindowOpen(signature = "") {
  if (signature) {
    const state = window.metricsPopupStates[signature];
    return !!(state?.win && !state.win.closed);
  }
  return Object.values(window.metricsPopupStates).some((state) => state?.win && !state.win.closed);
}
function popupMetricsWindowActive(signature = "") {
  const states = signature
    ? [window.metricsPopupStates[signature]].filter(Boolean)
    : Object.values(window.metricsPopupStates);
  return states.some((state) => {
    const win = state?.win;
    if (!win || win.closed) return false;
    try {
      if (win.document?.hidden) return false;
      if (typeof win.document?.hasFocus === "function" && win.document.hasFocus()) return true;
    } catch (e) {}
    return Date.now() - Number(state?.lastActiveAt || 0) < 2000;
  });
}
function metricPaneLabel(paneId = "mMain") {
  return {
    mMain: "Main",
    mGpu: "GPUs",
    mCpuRam: "CPU+RAM",
    mSystem: "System",
    mNetwork: "Network",
  }[String(paneId || "mMain")] || "Main";
}
function normalizeMetricPaneId(paneId = "") {
  const normalized = String(paneId || "").trim();
  return ["mMain", "mGpu", "mCpuRam", "mSystem", "mNetwork"].includes(normalized)
    ? normalized
    : "mMain";
}
function activeMetricPaneId(doc = document) {
  const active = doc?.querySelector?.(".metricpane.active");
  return normalizeMetricPaneId(active?.id || "mMain");
}
function setActiveMetricPaneInDocument(doc, paneId) {
  const nextPaneId = normalizeMetricPaneId(paneId);
  doc?.querySelectorAll?.(".metricpane")?.forEach((node) => {
    node.classList.toggle("active", node.id === nextPaneId);
  });
  doc?.querySelectorAll?.("[data-metric-pane]")?.forEach((node) => {
    node.classList.toggle("active", node.getAttribute("data-metric-pane") === nextPaneId);
  });
  return nextPaneId;
}
function currentMetricsPopupTarget() {
  const paneId = activeMetricPaneId(document);
  return {
    signature: "metrics",
    paneId,
    title: "Metrics",
    label: metricPaneLabel(paneId),
  };
}
function metricsPopoutButtonSvg(detached = false) {
  return detached
    ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 19H5v-5m0 5 7-7" fill="none" /><path d="M14 17h3a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H9a2 2 0 0 0-2 2v3" fill="none" /></svg>'
    : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 5h5v5m0-5-7 7" fill="none" /><path d="M10 7H7a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-3" fill="none" /></svg>';
}
function withMetricsRenderDocument(doc, fn) {
  const previous = metricsRenderDocument;
  metricsRenderDocument = doc || null;
  try {
    return fn();
  } finally {
    metricsRenderDocument = previous;
  }
}
function withDetachedMetricsHost(signature, fn) {
  const previousSignature = detachedMetricsHostSignature;
  detachedMetricsHostSignature = String(signature || "").trim();
  const state = window.metricsPopupStates[detachedMetricsHostSignature];
  const doc = state?.win && !state.win.closed ? state.win.document : null;
  const win = state?.win && !state.win.closed ? state.win : null;
  const restore = () => {
    detachedMetricsHostSignature = previousSignature;
  };
  try {
    const result = withUiTarget(doc, win, fn);
    if (result && typeof result.then === "function") {
      return result.finally(restore);
    }
    restore();
    return result;
  } catch (error) {
    restore();
    throw error;
  }
}
window.withDetachedMetricsHost = withDetachedMetricsHost;
function createStorageBrowserState() {
  return {
    rootPath: "",
    relativePath: "",
    currentPath: "",
    entries: [],
    selected: new Set(),
    devicePath: "",
    title: "",
    hostSignature: "",
    openFiles: [],
    activeFilePath: "",
    wrapText: false,
    previewMode: false,
    subtitleMode: "track",
    subtitleDelaySeconds: 0,
    subtitleFontScale: 1,
    sortColumn: "",
    sortDirection: "",
    sizePollTimer: null,
  };
}
const storageBrowserStateByHost = {
  main: createStorageBrowserState(),
  popup: createStorageBrowserState(),
};
let storageBrowserHostOverride = "";
const STORAGE_BROWSER_SESSION_CACHE_PREFIX = "club3090-storage-browser:";
const storageBrowserSessionHydrated = { main: false, popup: false };
function withStorageBrowserHost(hostKey, fn) {
  const previous = storageBrowserHostOverride;
  storageBrowserHostOverride = String(hostKey || "").trim();
  const restore = () => {
    storageBrowserHostOverride = previous;
  };
  try {
    const result = fn();
    if (result && typeof result.then === "function") {
      return result.finally(restore);
    }
    restore();
    return result;
  } catch (error) {
    restore();
    throw error;
  }
}
function mergeStorageBrowserHostState(fromKey = "popup", intoKey = "main") {
  const source = storageBrowserStateByHost[String(fromKey || "")];
  const target = storageBrowserStateByHost[String(intoKey || "")];
  if (!source || !target || !Array.isArray(source.openFiles) || !source.openFiles.length) return;
  const merged = [...(target.openFiles || [])];
  source.openFiles.forEach((file) => {
    const path = String(file?.relative_path || "");
    if (!path) return;
    const index = merged.findIndex((row) => String(row?.relative_path || "") === path);
    if (index >= 0) merged[index] = file;
    else merged.push(file);
  });
  target.openFiles = merged;
  if (source.activeFilePath) target.activeFilePath = String(source.activeFilePath || "");
  persistStorageBrowserSessionCache(intoKey);
}
let storageVolumesStatusText = "";
function currentStorageBrowserHostKey() {
  if (storageBrowserHostOverride === "main" || storageBrowserHostOverride === "popup") {
    return storageBrowserHostOverride;
  }
  return currentUiDocument() === document ? "main" : "popup";
}
function currentStorageBrowserState() {
  const hostKey = currentStorageBrowserHostKey();
  if (!storageBrowserSessionHydrated[hostKey]) {
    hydrateStorageBrowserSessionCache(hostKey);
    storageBrowserSessionHydrated[hostKey] = true;
  }
  return storageBrowserStateByHost[currentStorageBrowserHostKey()];
}
const storageBrowserState = new Proxy(
  {},
  {
    get(_target, prop) {
      return currentStorageBrowserState()[prop];
    },
    set(_target, prop, value) {
      currentStorageBrowserState()[prop] = value;
      return true;
    },
  },
);
function storageBrowserToolbarButton(action, icon, title, extraClass = "") {
  const className = `iconbtn ${extraClass}`.trim();
  return `<button class="${className}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}" onclick="${action}">${svgIcon(icon)}</button>`;
}
function storageBrowserToolbarSeparator() {
  return '<span class="storage-browser-toolbar-separator" aria-hidden="true"></span>';
}
function storageBrowserFormatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes === 0) return "0 B";
  return formatDiskBytes(bytes);
}
function storageBrowserSizeHtml(entry) {
  if (entry?.size_pending) return '<span class="storage-browser-size-pending">estimating...</span>';
  const text = storageBrowserFormatBytes(entry?.size_bytes);
  if (!text) return "";
  const estimated = entry?.size_estimated ? ' title="Estimated in the background"' : "";
  return `<span class="${entry?.size_estimated ? "storage-browser-size-estimated" : ""}"${estimated}>${escapeHtml(text)}</span>`;
}
function storageBrowserFormatTimestamp(value) {
  const stamp = Number(value || 0);
  if (!Number.isFinite(stamp) || stamp <= 0) return "";
  return new Date(stamp * 1000).toLocaleString();
}
function storageBrowserPreviewUrl(file, kind = "preview") {
  const rootPath = String(storageBrowserState.rootPath || "");
  const relativePath = String(file?.relative_path || "");
  if (!rootPath || !relativePath) return "";
  const query = new URLSearchParams({
    root_path: rootPath,
    relative_path: relativePath,
  });
  if (kind === "preview") {
    const audioIndex = Number(file?.selected_audio_stream_index);
    if (Number.isFinite(audioIndex) && audioIndex >= 0) query.set("audio_stream_index", String(audioIndex));
  }
  if (kind === "subtitle") {
    const subtitle = file?.selectedSubtitle || null;
    if (subtitle?.kind === "embedded" && subtitle?.stream_index !== undefined) {
      query.set("embedded_stream_index", String(subtitle.stream_index));
    } else if (subtitle?.kind === "external" && subtitle?.relative_path) {
      query.set("external_relative_path", String(subtitle.relative_path));
    }
  }
  return kind === "subtitle"
    ? `/admin/storage-browser/subtitle?${query.toString()}`
    : `/admin/storage-browser/preview?${query.toString()}`;
}
function storageBrowserSetMsg(text = "", tone = "warning") {
  setElementMsg("storageBrowserMsg", text || "", tone);
}
function storageBrowserSetActivity(text = "") {
  const node = $("storageBrowserActivity");
  if (node) node.textContent = String(text || "");
}
function storageBrowserSessionCacheKey(hostKey = currentStorageBrowserHostKey()) {
  return `${STORAGE_BROWSER_SESSION_CACHE_PREFIX}${String(hostKey || "main")}`;
}
function serializeStorageBrowserState(state) {
  return {
    rootPath: String(state?.rootPath || ""),
    relativePath: String(state?.relativePath || ""),
    currentPath: String(state?.currentPath || ""),
    devicePath: String(state?.devicePath || ""),
    title: String(state?.title || ""),
    hostSignature: String(state?.hostSignature || ""),
    activeFilePath: String(state?.activeFilePath || ""),
    wrapText: !!state?.wrapText,
    previewMode: !!state?.previewMode,
    subtitleMode: String(state?.subtitleMode || "track"),
    subtitleDelaySeconds: Number(state?.subtitleDelaySeconds || 0) || 0,
    subtitleFontScale: Number(state?.subtitleFontScale || 1) || 1,
    sortColumn: String(state?.sortColumn || ""),
    sortDirection: String(state?.sortDirection || ""),
    openFiles: Array.isArray(state?.openFiles)
      ? state.openFiles.map((file) => ({
          ...file,
          selected: undefined,
          hex_rows: [],
        }))
      : [],
  };
}
function persistStorageBrowserSessionCache(hostKey = currentStorageBrowserHostKey()) {
  try {
    currentUiWindow().sessionStorage.setItem(
      storageBrowserSessionCacheKey(hostKey),
      JSON.stringify(serializeStorageBrowserState(storageBrowserStateByHost[hostKey])),
    );
  } catch (error) {}
}
function hydrateStorageBrowserSessionCache(hostKey = currentStorageBrowserHostKey()) {
  try {
    const raw = currentUiWindow().sessionStorage.getItem(storageBrowserSessionCacheKey(hostKey));
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return;
    const state = storageBrowserStateByHost[hostKey];
    state.rootPath = String(parsed.rootPath || "");
    state.relativePath = String(parsed.relativePath || "");
    state.currentPath = String(parsed.currentPath || "");
    state.devicePath = String(parsed.devicePath || "");
    state.title = String(parsed.title || "");
    state.hostSignature = String(parsed.hostSignature || "");
    state.activeFilePath = String(parsed.activeFilePath || "");
    state.wrapText = !!parsed.wrapText;
    state.previewMode = !!parsed.previewMode;
    state.subtitleMode = String(parsed.subtitleMode || "track");
    state.subtitleDelaySeconds = Number(parsed.subtitleDelaySeconds || 0) || 0;
    state.subtitleFontScale = Number(parsed.subtitleFontScale || 1) || 1;
    state.sortColumn = String(parsed.sortColumn || "");
    state.sortDirection = String(parsed.sortDirection || "");
    state.openFiles = Array.isArray(parsed.openFiles) ? parsed.openFiles : [];
  } catch (error) {}
}
function setStorageVolumesStatus(text = "") {
  storageVolumesStatusText = String(text || "");
  metricsElement("storageVolumesStatus") && (metricsElement("storageVolumesStatus").textContent = storageVolumesStatusText);
}
function storageBrowserFileDirty(file) {
  if (!file) return false;
  if (file.is_text) {
    return String(file.text || "") !== String(file.original_text || "");
  }
  return String(file.hex_text || "") !== String(file.original_hex_text || "");
}
function storageEditorMediaPreviewable(file) {
  return !file?.is_text && /^(image\/|video\/|audio\/)|^application\/pdf$/i.test(String(file?.mime || ""));
}
function storageEditorVideoPreviewable(file) {
  return !file?.is_text && /^video\//i.test(String(file?.mime || ""));
}
async function loadStorageBrowserMediaMetadata(file) {
  if (!file || !storageEditorMediaPreviewable(file)) return null;
  const payload = await storageBrowserPost("media_metadata", {
    root_path: storageBrowserState.rootPath,
    relative_path: file.relative_path,
  });
  file.media_metadata = payload || {};
  file.subtitle_options = Array.isArray(payload?.subtitle_streams) ? payload.subtitle_streams : [];
  file.audio_options = Array.isArray(payload?.audio_streams) ? payload.audio_streams : [];
  file.selectedSubtitle = file.subtitle_options.find((row) => row?.default) || file.subtitle_options[0] || null;
  file.selected_audio_stream_index =
    Number(file.audio_options?.[0]?.stream_index) >= 0 ? Number(file.audio_options[0].stream_index) : -1;
  file.subtitle_text = "";
  file.subtitle_cues = [];
  if (storageEditorVideoPreviewable(file) && file.selectedSubtitle) {
    await loadStorageBrowserSubtitleSelection(file, file.selectedSubtitle);
  }
  return payload;
}
function parseVttTimestamp(text = "") {
  const match = String(text || "").trim().match(/(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})/);
  if (!match) return 0;
  return (Number(match[1] || 0) * 3600) + (Number(match[2] || 0) * 60) + Number(match[3] || 0) + (Number(match[4] || 0) / 1000);
}
function parseVttCues(text = "") {
  const normalized = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const body = normalized.replace(/^WEBVTT[^\n]*\n+/i, "");
  const blocks = body.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
  const cues = [];
  blocks.forEach((block) => {
    const lines = block.split("\n");
    const timingIndex = lines.findIndex((line) => line.includes("-->"));
    if (timingIndex < 0) return;
    const timing = lines[timingIndex].split("-->");
    if (timing.length < 2) return;
    const start = parseVttTimestamp(timing[0]);
    const end = parseVttTimestamp(timing[1]);
    const textLines = lines.slice(timingIndex + 1).filter(Boolean);
    if (!textLines.length) return;
    cues.push({ start, end, text: textLines.join("\n") });
  });
  return cues;
}
function formatVttTimestamp(seconds = 0) {
  const totalMs = Math.max(0, Math.round(Number(seconds || 0) * 1000));
  const hours = Math.floor(totalMs / 3600000);
  const minutes = Math.floor((totalMs % 3600000) / 60000);
  const secs = Math.floor((totalMs % 60000) / 1000);
  const ms = totalMs % 1000;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
}
function storageEditorSubtitleVttText(file) {
  const delay = Number(storageBrowserState.subtitleDelaySeconds || 0);
  const cues = Array.isArray(file?.subtitle_cues) ? file.subtitle_cues : [];
  const rows = ["WEBVTT", ""];
  cues.forEach((cue) => {
    const start = Math.max(0, Number(cue.start || 0) - delay);
    const end = Math.max(start, Number(cue.end || 0) - delay);
    rows.push(`${formatVttTimestamp(start)} --> ${formatVttTimestamp(end)}`);
    rows.push(String(cue.text || ""));
    rows.push("");
  });
  return rows.join("\n");
}
function revokeStorageEditorNativeSubtitleTrackUrl(file) {
  const url = String(file?.nativeSubtitleTrackUrl || "");
  if (!url) return;
  try {
    currentUiWindow().URL?.revokeObjectURL?.(url);
  } catch (error) {}
  file.nativeSubtitleTrackUrl = "";
}
function storageEditorSubtitleTrackUrl(file) {
  if (!file?.selectedSubtitle || !(file.subtitle_cues || []).length) return "";
  revokeStorageEditorNativeSubtitleTrackUrl(file);
  const blob = new Blob([storageEditorSubtitleVttText(file)], { type: "text/vtt" });
  file.nativeSubtitleTrackUrl = currentUiWindow().URL?.createObjectURL ? currentUiWindow().URL.createObjectURL(blob) : "";
  return String(file.nativeSubtitleTrackUrl || "");
}
async function loadStorageBrowserSubtitleSelection(file, subtitleRow) {
  if (!file) return;
  file.selectedSubtitle = subtitleRow || null;
  file.subtitle_text = "";
  file.subtitle_cues = [];
  revokeStorageEditorNativeSubtitleTrackUrl(file);
  if (!subtitleRow) {
    syncStorageEditorNativeSubtitleTrack();
    renderStorageEditorSubtitleOverlay();
    return;
  }
  const response = await fetch(storageBrowserPreviewUrl(file, "subtitle"), { cache: "no-store" });
  if (!response.ok) {
    file.subtitle_text = "";
    file.subtitle_cues = [];
    renderStorageEditorSubtitleOverlay();
    return;
  }
  file.subtitle_text = await response.text();
  file.subtitle_cues = parseVttCues(file.subtitle_text);
  syncStorageEditorNativeSubtitleTrack();
  renderStorageEditorSubtitleOverlay();
}
function renderStorageBrowserOpenFileTabs() {
  const node = $("storageBrowserOpenFileTabs");
  if (!node) return;
  const files = storageBrowserState.openFiles || [];
  if (!files.length) {
    node.innerHTML = "";
    node.classList.add("hidden");
    return;
  }
  node.classList.remove("hidden");
  node.innerHTML = files
    .map((file) => {
      const active = String(file?.relative_path || "") === String(storageBrowserState.activeFilePath || "");
      const dirty = storageBrowserFileDirty(file);
      return `<button class="subtab ${active ? "active" : ""}" onclick="reopenStorageEditorFile('${escapeJs(file.relative_path || "")}')">${escapeHtml(file?.name || file?.relative_path || "file")}${dirty ? " *" : ""}</button>`;
    })
    .join("");
}
function ensureStorageBrowserModal() {
  if ($("storageBrowserModal")) return;
  const doc = currentUiDocument();
  const modal = doc.createElement("div");
  modal.id = "storageBrowserModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card storage-browser-modal-card" role="dialog" aria-modal="true" aria-labelledby="storageBrowserTitle"><div class="panel-head"><h2 id="storageBrowserTitle">Storage Browser</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeStorageBrowserModal()">✕</button></div><div class="storage-browser-toolbar"><div class="storage-browser-toolbar-left">${storageBrowserToolbarButton("refreshStorageBrowser()", "reset", "Refresh", "storage-browser-tool")}${storageBrowserToolbarSeparator()}${storageBrowserToolbarButton("downloadStorageBrowserSelection()", "download", "Download", "storage-browser-tool")}${storageBrowserToolbarButton("openStorageBrowserUploadPicker()", "upload", "Upload", "storage-browser-tool")}<span id="storageBrowserDuplicateWrap" class="hidden">${storageBrowserToolbarSeparator()}${storageBrowserToolbarButton("duplicateStorageBrowserToMainWindow()", "detach", "Duplicate", "storage-browser-tool")}</span>${storageBrowserToolbarSeparator()}${storageBrowserToolbarButton("openSelectedStorageBrowserFiles()", "edit", "Open selected file(s)", "storage-browser-tool")}${storageBrowserToolbarButton("deleteStorageBrowserSelection()", "delete", "Delete", "storage-browser-tool danger")}${storageBrowserToolbarSeparator()}${storageBrowserToolbarButton("promptCreateStorageBrowserFolder()", "folder", "New folder", "storage-browser-tool")}${storageBrowserToolbarButton("promptCreateStorageBrowserFile()", "file", "New text file", "storage-browser-tool")}</div><div class="storage-browser-paths"><div class="storage-browser-path"><strong>Volume:</strong> <code id="storageBrowserRootPath"></code></div><div class="storage-browser-path"><strong>Folder:</strong> <code id="storageBrowserCurrentPath"></code></div></div></div><input id="storageBrowserUploadInput" type="file" multiple class="hidden" onchange="handleStorageBrowserUpload(event)" /><div class="storage-browser-table-wrap"><table class="storage-browser-table"><colgroup><col class="storage-browser-col-select" /><col class="storage-browser-col-name" /><col class="storage-browser-col-size" /><col class="storage-browser-col-type" /><col class="storage-browser-col-owner" /><col class="storage-browser-col-perms" /><col class="storage-browser-col-attrs" /><col class="storage-browser-col-modified" /></colgroup><thead><tr><th></th><th>Name</th><th>Size</th><th>Type</th><th>Owner</th><th>Permissions</th><th>Attributes</th><th>Modified</th></tr></thead><tbody id="storageBrowserTableBody"></tbody></table></div><div class="storage-browser-activity" id="storageBrowserActivity"></div><div id="storageBrowserOpenFileTabs" class="storage-browser-open-file-tabs hidden"></div><div class="msg" id="storageBrowserMsg"></div></div>`;
  doc.body.appendChild(modal);
}
function closeStorageBrowserModal() {
  ensureStorageBrowserModal();
  $("storageBrowserModal").classList.add("hidden");
  if (storageBrowserState.sizePollTimer) {
    clearTimeout(storageBrowserState.sizePollTimer);
    storageBrowserState.sizePollTimer = null;
  }
  storageBrowserState.selected.clear();
  storageBrowserState.hostSignature = "";
  storageBrowserSetActivity("");
  persistStorageBrowserSessionCache();
}
async function loadStorageBrowser(rootPath, relativePath = "", title = "", devicePath = "") {
  ensureStorageBrowserModal();
  const response = await post(
    "/admin/storage-browser",
    {
      action: "list",
      root_path: rootPath,
      relative_path: relativePath,
    },
    `/admin/storage-browser list ${rootPath} ${relativePath}`,
    { silentSuccess: true },
  );
  storageBrowserState.rootPath = String(response?.root_path || rootPath || "");
  storageBrowserState.relativePath = String(response?.relative_path || "");
  storageBrowserState.currentPath = String(response?.current_path || "");
  storageBrowserState.entries = Array.isArray(response?.entries) ? response.entries : [];
  storageBrowserState.devicePath = String(devicePath || storageBrowserState.devicePath || "");
  storageBrowserState.title = String(title || storageBrowserState.title || "Storage Browser");
  storageBrowserState.hostSignature = String(detachedMetricsHostSignature || "");
  storageBrowserState.selected = new Set();
  if (storageBrowserState.sizePollTimer) {
    clearTimeout(storageBrowserState.sizePollTimer);
    storageBrowserState.sizePollTimer = null;
  }
  renderStorageBrowser();
  renderStorageBrowserOpenFileTabs();
  $("storageBrowserModal")?.classList.remove("hidden");
  storageBrowserSetActivity(`Opened ${storageBrowserState.currentPath || storageBrowserState.rootPath || rootPath || "/"}`);
  persistStorageBrowserSessionCache();
}
function scheduleStorageBrowserSizeRefresh() {
  const hostKey = currentStorageBrowserHostKey();
  const state = storageBrowserStateByHost[hostKey];
  if (!state.entries.some((entry) => entry?.size_pending)) return;
  if (state.sizePollTimer) return;
  const rootPath = state.rootPath;
  const relativePath = state.relativePath;
  const title = state.title;
  const devicePath = state.devicePath;
  const hostSignature = state.hostSignature;
  state.sizePollTimer = setTimeout(() => {
    state.sizePollTimer = null;
    const run = () => withStorageBrowserHost(hostSignature ? "popup" : "main", () => {
      const targetDoc =
        hostSignature && popupMetricsState(hostSignature)?.win && !popupMetricsState(hostSignature)?.win.closed
          ? popupMetricsState(hostSignature).win.document
          : document;
      if (targetDoc.getElementById("storageBrowserModal")?.classList.contains("hidden")) return;
      const targetState = storageBrowserStateByHost[hostSignature ? "popup" : "main"];
      if (rootPath !== targetState.rootPath || relativePath !== targetState.relativePath) return;
      return loadStorageBrowser(rootPath, relativePath, title, devicePath).catch((error) => {
        storageBrowserSetMsg(messageText(error), "error");
      });
    });
    if (hostSignature) {
      withDetachedMetricsHost(hostSignature, run);
      return;
    }
    run();
  }, 2500);
}
function storageBrowserEntryIcon(entry) {
  const type = String(entry?.type || "");
  if (type === "folder") return svgIcon("folder");
  if (["txt", "md", "json", "js", "py", "html", "css", "xml", "yaml", "yml", "ts", "log", "conf"].includes(type)) {
    return svgIcon("file");
  }
  return svgIcon("save");
}
function storageBrowserSortableColumns() {
  return new Set(["name", "size_bytes", "type", "owner", "permissions", "attributes", "modified_at"]);
}
function storageBrowserSortValue(entry, column) {
  const key = String(column || "").trim();
  if (key === "size_bytes" || key === "modified_at") {
    const numeric = Number(entry?.[key]);
    return Number.isFinite(numeric) ? numeric : -1;
  }
  return String(entry?.[key] || "").toLocaleLowerCase();
}
function storageBrowserCompareEntries(left, right, column, direction) {
  const a = storageBrowserSortValue(left, column);
  const b = storageBrowserSortValue(right, column);
  let result = 0;
  if (typeof a === "number" && typeof b === "number") result = a - b;
  else result = String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
  if (!result) {
    result =
      String(left?.name || "").localeCompare(String(right?.name || ""), undefined, {
        numeric: true,
        sensitivity: "base",
      }) || 0;
  }
  return direction === "desc" ? -result : result;
}
function storageBrowserSortedEntries(entries = []) {
  const column = String(storageBrowserState.sortColumn || "").trim();
  const direction = String(storageBrowserState.sortDirection || "").trim();
  const rows = [...(entries || [])];
  if (!column || !direction || !storageBrowserSortableColumns().has(column)) return rows;
  return rows.sort((left, right) => storageBrowserCompareEntries(left, right, column, direction));
}
function storageBrowserSortArrow(column) {
  const active = String(storageBrowserState.sortColumn || "") === String(column || "");
  if (!active) return "";
  if (storageBrowserState.sortDirection === "asc") return "▲";
  if (storageBrowserState.sortDirection === "desc") return "▼";
  return "";
}
function storageBrowserHeaderButton(column, label) {
  const arrow = storageBrowserSortArrow(column);
  const active = !!arrow;
  return `<button type="button" class="storage-browser-sort-btn${active ? " active" : ""}" onclick="toggleStorageBrowserSort('${escapeJs(column)}')"><span class="storage-browser-sort-arrow" aria-hidden="true">${arrow || "▲"}</span><span>${escapeHtml(label)}</span></button>`;
}
function toggleStorageBrowserSort(column) {
  const key = String(column || "").trim();
  if (!storageBrowserSortableColumns().has(key)) return;
  if (storageBrowserState.sortColumn !== key) {
    storageBrowserState.sortColumn = key;
    storageBrowserState.sortDirection = "asc";
  } else if (storageBrowserState.sortDirection === "asc") {
    storageBrowserState.sortDirection = "desc";
  } else {
    storageBrowserState.sortColumn = "";
    storageBrowserState.sortDirection = "";
  }
  persistStorageBrowserSessionCache();
  renderStorageBrowser();
}
function renderStorageBrowser() {
  ensureStorageBrowserModal();
  $("storageBrowserTitle").textContent = storageBrowserState.title || "Storage Browser";
  $("storageBrowserRootPath").textContent = storageBrowserState.rootPath || "-";
  $("storageBrowserCurrentPath").textContent = storageBrowserState.currentPath || storageBrowserState.rootPath || "-";
  $("storageBrowserDuplicateWrap")?.classList.toggle("hidden", !storageBrowserState.hostSignature);
  renderStorageBrowserOpenFileTabs();
  const header = currentUiDocument().querySelector("#storageBrowserModal thead tr");
  if (header) {
    header.innerHTML = `<th></th><th>${storageBrowserHeaderButton("name", "Name")}</th><th>${storageBrowserHeaderButton("size_bytes", "Size")}</th><th>${storageBrowserHeaderButton("type", "Type")}</th><th>${storageBrowserHeaderButton("owner", "Owner")}</th><th>${storageBrowserHeaderButton("permissions", "Permissions")}</th><th>${storageBrowserHeaderButton("attributes", "Attributes")}</th><th>${storageBrowserHeaderButton("modified_at", "Modified")}</th>`;
  }
  const body = $("storageBrowserTableBody");
  if (!body) return;
  const parentEntry = storageBrowserState.entries.find((entry) => entry?.name === "..") || null;
  const childEntries = storageBrowserSortedEntries(
    storageBrowserState.entries.filter((entry) => entry?.name !== ".."),
  );
  const rows = parentEntry ? [parentEntry, ...childEntries] : childEntries;
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="8" class="storage-browser-empty">This folder is empty.</td></tr>';
    return;
  }
  body.innerHTML = rows
    .map((entry, index) => {
      const rel = String(entry?.relative_path || "");
      const selected = storageBrowserState.selected.has(rel);
      const isFolder = String(entry?.type || "") === "folder";
      const rowAction = isFolder
        ? `openStorageBrowserEntry('${escapeJs(rel)}')`
        : `openStorageBrowserFile('${escapeJs(rel)}')`;
      const displayName = entry?.name === ".." ? "Previous folder" : String(entry?.name || `entry-${index + 1}`);
      if (entry?.name === "..") {
        return `<tr class="storage-browser-parent-row"><td></td><td><button type="button" class="storage-browser-name is-folder storage-browser-parent-link" onclick="${rowAction}"><span class="storage-browser-back-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h6l2 2h10v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" fill="none"/><path d="M12 16V9m0 0-2.7 2.7M12 9l2.7 2.7" fill="none"/></svg></span><span class="storage-browser-name-label" title="Previous folder">Previous folder</span></button></td><td colspan="6"></td></tr>`;
      }
      const nameHtml =
        `<button type="button" class="${isFolder ? "storage-browser-name is-folder" : "storage-browser-name is-file"}" onclick="${rowAction}"><span class="storage-browser-entry-icon">${storageBrowserEntryIcon(entry)}</span><span class="storage-browser-name-label" title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</span></button>`;
      return `<tr class="${selected ? "selected" : ""}"><td><input type="checkbox" ${selected ? "checked" : ""} onchange="toggleStorageBrowserSelection('${escapeJs(rel)}', this.checked)" /></td><td class="storage-browser-name-cell">${nameHtml}</td><td>${storageBrowserSizeHtml(entry)}</td><td>${escapeHtml(entry?.type || "")}</td><td>${escapeHtml(entry?.owner || "")}</td><td>${escapeHtml(entry?.permissions || "")}</td><td>${escapeHtml(entry?.attributes || "")}</td><td>${escapeHtml(storageBrowserFormatTimestamp(entry?.modified_at))}</td></tr>`;
    })
    .join("");
  scheduleStorageBrowserSizeRefresh();
}
function openStorageBrowserForVolume(devicePath, rootPath, title) {
  storageBrowserSetActivity(`Opening ${rootPath || devicePath || "volume"}...`);
  return withStorageBrowserHost(currentStorageBrowserHostKey(), () => loadStorageBrowser(rootPath, "", title, devicePath)).catch((error) => {
    alert(messageText(error));
  });
}
function duplicateStorageBrowserToMainWindow() {
  const rootPath = storageBrowserState.rootPath;
  if (!rootPath || !storageBrowserState.hostSignature) return;
  storageBrowserSetActivity("Duplicating this browser into the main window...");
  return withUiTarget(document, window, () =>
    withStorageBrowserHost("main", () => loadStorageBrowser(
      rootPath,
      storageBrowserState.relativePath,
      storageBrowserState.title,
      storageBrowserState.devicePath,
    )),
  );
}
function openStorageBrowserEntry(relativePath) {
  storageBrowserSetActivity(`Opening ${relativePath || "."}...`);
  return withStorageBrowserHost(currentStorageBrowserHostKey(), () => loadStorageBrowser(
    storageBrowserState.rootPath,
    relativePath,
    storageBrowserState.title,
    storageBrowserState.devicePath,
  )).catch((error) => {
    storageBrowserSetMsg(messageText(error), "error");
  });
}
function toggleStorageBrowserSelection(relativePath, checked) {
  const key = String(relativePath || "");
  if (!key) return;
  if (checked) storageBrowserState.selected.add(key);
  else storageBrowserState.selected.delete(key);
}
function storageBrowserSelectedEntries() {
  return [...storageBrowserState.selected].filter(Boolean);
}
function refreshStorageBrowser() {
  if (!storageBrowserState.rootPath) return;
  storageBrowserSetActivity("Refreshing folder listing...");
  return withStorageBrowserHost(currentStorageBrowserHostKey(), () => loadStorageBrowser(
    storageBrowserState.rootPath,
    storageBrowserState.relativePath,
    storageBrowserState.title,
    storageBrowserState.devicePath,
  )).catch((error) => {
    storageBrowserSetMsg(messageText(error), "error");
  });
}
function storageBrowserNavigateUp() {
  const current = String(storageBrowserState.relativePath || "");
  const parts = current.split("/").filter(Boolean);
  parts.pop();
  openStorageBrowserEntry(parts.join("/"));
}
function openStorageBrowserUploadPicker() {
  storageBrowserSetActivity("Waiting for file selection...");
  $("storageBrowserUploadInput")?.click();
}
async function handleStorageBrowserUpload(event) {
  const files = Array.from(event?.target?.files || []);
  if (!files.length) return;
  try {
    for (const file of files) {
      const buffer = await file.arrayBuffer();
      const query = new URLSearchParams({
        root: storageBrowserState.rootPath,
        relative_path: storageBrowserState.relativePath,
        name: file.name || "upload.bin",
      });
      const response = await fetch(`/admin/storage-browser/upload?${query.toString()}`, {
        method: "POST",
        headers: {
          "X-Club3090-File-Name": file.name || "upload.bin",
        },
        body: buffer,
      });
      const payload = await response.json();
      if (!response.ok || !payload?.ok) {
        throw new Error(payload?.error || `Failed to upload ${file.name || "file"}.`);
      }
    }
    storageBrowserSetMsg("Upload completed.", "success");
    storageBrowserSetActivity(`Uploaded ${files.length} file${files.length === 1 ? "" : "s"}.`);
    refreshStorageBrowser();
  } catch (error) {
    storageBrowserSetMsg(messageText(error), "error");
  } finally {
    if (event?.target) event.target.value = "";
  }
}
async function downloadStorageBrowserSelection() {
  const entries = storageBrowserSelectedEntries();
  if (!entries.length) {
    storageBrowserSetMsg("Select at least one file or folder first.", "warning");
    return;
  }
  try {
    const plan = await post("/admin/storage-browser/download", {
      action: "plan",
      root_path: storageBrowserState.rootPath,
      entries,
    }, "/admin/storage-browser/download plan", { silentSuccess: true });
    if (plan?.requires_confirmation) {
      const proceed = await openClubConfirmModal({
        title: "Large Zip Download",
        message: `The selected folder download is estimated at ${storageBrowserFormatBytes(plan.total_bytes || 0)} before compression. Continue building the zip in the background?`,
        confirmLabel: "Start Zip",
        confirmClass: "green",
      });
      if (!proceed) return;
    }
    if (plan?.mode === "direct" || !plan?.archive_forced) {
      const response = await fetch("/admin/storage-browser/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          root_path: storageBrowserState.rootPath,
          entries,
        }),
      });
      if (!response.ok) {
        let message = "Download failed.";
        try {
          const payload = await response.json();
          message = payload?.error || message;
        } catch (error) {}
        throw new Error(message);
      }
      const blob = await response.blob();
      const disposition = String(response.headers.get("Content-Disposition") || "");
      const match = disposition.match(/filename=\"([^\"]+)\"/i);
      const name = match?.[1] || (entries.length === 1 ? entries[0].split("/").pop() || "download" : "download.zip");
      const uiWindow = currentUiWindow();
      const uiDocument = currentUiDocument();
      const url = uiWindow.URL.createObjectURL(blob);
      const anchor = uiDocument.createElement("a");
      anchor.href = url;
      anchor.download = name;
      uiDocument.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      uiWindow.URL.revokeObjectURL(url);
      storageBrowserSetMsg("Download prepared.", "success");
      storageBrowserSetActivity(`Prepared download for ${entries.length} selection${entries.length === 1 ? "" : "s"}.`);
      return;
    }
    const started = await post("/admin/storage-browser/download", {
      action: "start",
      root_path: storageBrowserState.rootPath,
      entries,
    }, "/admin/storage-browser/download start", { silentSuccess: true });
    const jobId = String(started?.job?.job_id || "");
    if (!jobId) throw new Error("Download job did not return an id.");
    storageBrowserSetActivity("Zipping selection for download...");
    const pollJob = async () => {
      const status = await post("/admin/storage-browser/download", {
        action: "status",
        job_id: jobId,
      }, "/admin/storage-browser/download status", { silentSuccess: true, silentFailure: true });
      const job = status?.job || {};
      if (job.summary) storageBrowserSetActivity(String(job.summary || ""));
      if (String(job.status || "") === "error") {
        throw new Error(job.error || job.summary || "Zip download failed.");
      }
      if (String(job.status || "") !== "ready") {
        setTimeout(() => {
          pollJob().catch((error) => storageBrowserSetMsg(messageText(error), "error"));
        }, 800);
        return;
      }
      const response = await fetch("/admin/storage-browser/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "fetch_job",
          job_id: jobId,
        }),
      });
      if (!response.ok) throw new Error("Download fetch failed.");
      const blob = await response.blob();
      const name = String(job.archive_name || "download.zip");
      const uiWindow = currentUiWindow();
      const uiDocument = currentUiDocument();
      const url = uiWindow.URL.createObjectURL(blob);
      const anchor = uiDocument.createElement("a");
      anchor.href = url;
      anchor.download = name;
      uiDocument.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      uiWindow.URL.revokeObjectURL(url);
      storageBrowserSetMsg("Download prepared.", "success");
      storageBrowserSetActivity(`Prepared ${name}.`);
    };
    await pollJob();
  } catch (error) {
    storageBrowserSetMsg(messageText(error), "error");
  }
}
async function downloadActiveStorageEditorFile() {
  const file = activeStorageEditorFile();
  const relativePath = String(file?.relative_path || storageBrowserState.activeFilePath || "").trim();
  if (!storageBrowserState.rootPath || !relativePath) {
    setElementMsg("storageEditorMsg", "No active file is available to download.", "warning");
    return;
  }
  try {
    const response = await fetch("/admin/storage-browser/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        root_path: storageBrowserState.rootPath,
        entries: [relativePath],
      }),
    });
    if (!response.ok) {
      let message = "Download failed.";
      try {
        const payload = await response.json();
        message = payload?.error || message;
      } catch (error) {}
      throw new Error(message);
    }
    const blob = await response.blob();
    const disposition = String(response.headers.get("Content-Disposition") || "");
    const match = disposition.match(/filename=\"([^\"]+)\"/i);
    const name = match?.[1] || file?.name || relativePath.split("/").pop() || "download";
    const uiWindow = currentUiWindow();
    const uiDocument = currentUiDocument();
    const url = uiWindow.URL.createObjectURL(blob);
    const anchor = uiDocument.createElement("a");
    anchor.href = url;
    anchor.download = name;
    uiDocument.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    uiWindow.URL.revokeObjectURL(url);
    setElementMsg("storageEditorMsg", "Download prepared.", "success");
  } catch (error) {
    setElementMsg("storageEditorMsg", messageText(error), "error");
  }
}
async function deleteStorageBrowserSelection() {
  const entries = storageBrowserSelectedEntries();
  if (!entries.length) {
    storageBrowserSetMsg("Select at least one file or folder first.", "warning");
    return false;
  }
  if (!(await openClubConfirmModal(`Delete ${entries.length} selected file${entries.length === 1 ? "" : "s"} from this volume?`))) {
    return false;
  }
  try {
    await post(
      "/admin/storage-browser",
      {
        action: "delete",
        root_path: storageBrowserState.rootPath,
        entries,
      },
      `/admin/storage-browser delete ${entries.length}`,
      { silentSuccess: true },
    );
    storageBrowserSetMsg("Deleted selected entries.", "success");
    storageBrowserSetActivity(`Deleted ${entries.length} selection${entries.length === 1 ? "" : "s"}.`);
    await refreshStorageBrowser();
    return true;
  } catch (error) {
    storageBrowserSetMsg(messageText(error), "error");
    return false;
  }
}
async function deleteActiveStorageEditorFile() {
  const file = activeStorageEditorFile();
  const relativePath = String(file?.relative_path || storageBrowserState.activeFilePath || "").trim();
  if (!file || !relativePath) {
    setElementMsg("storageEditorMsg", "No active file is available to delete.", "warning");
    return;
  }
  if (file.read_only || storageBrowserState.previewMode) {
    setElementMsg("storageEditorMsg", "Return to edit mode before deleting this file.", "warning");
    return;
  }
  const previousRoot = storageBrowserState.rootPath;
  const previousSelected = new Set(storageBrowserState.selected);
  let deleted = false;
  try {
    storageBrowserState.rootPath = String(file.root_path || storageBrowserState.rootPath || "");
    storageBrowserState.selected = new Set([relativePath]);
    deleted = await deleteStorageBrowserSelection();
    if (!deleted) return;
    removeStorageEditorFile(relativePath);
    if (storageBrowserState.openFiles.length) openStorageEditorModal();
    else minimizeStorageEditorModal();
  } finally {
    storageBrowserState.rootPath = previousRoot;
    storageBrowserState.selected = deleted ? new Set() : previousSelected;
    renderStorageBrowserOpenFileTabs();
    persistStorageBrowserSessionCache();
  }
}
async function toggleStorageMount(devicePath, rootPath, mounted) {
  try {
    setStorageVolumesStatus(`${mounted ? "Unmounting" : "Mounting"} volume ${rootPath || devicePath || ""}...`);
    await post(
      "/admin/storage-browser",
      mounted
        ? { action: "unmount", root_path: rootPath }
        : { action: "mount", device_path: devicePath },
      mounted
        ? `/admin/storage-browser unmount ${rootPath}`
        : `/admin/storage-browser mount ${devicePath}`,
      { silentSuccess: true },
    );
    if (mounted && storageBrowserState.rootPath === String(rootPath || "")) {
      closeStorageBrowserModal();
    }
    storageBrowserSetActivity(`${mounted ? "Unmounted" : "Mounted"} ${rootPath || devicePath || "volume"}.`);
    setStorageVolumesStatus(`${mounted ? "Unmounted" : "Mounted"} volume ${rootPath || devicePath || ""}.`);
    await refreshStatus({ force: true });
  } catch (error) {
    setStorageVolumesStatus("");
    alert(messageText(error));
  }
}
async function storageBrowserPost(action, payload = {}, options = {}) {
  return post(
    "/admin/storage-browser",
    { action, ...payload },
    `/admin/storage-browser ${action}`,
    { silentSuccess: true, ...options },
  );
}
async function promptCreateStorageBrowserFolder() {
  const name = currentUiWindow().prompt("Folder name", "");
  if (!name) return;
  try {
    await storageBrowserPost("create_folder", {
      root_path: storageBrowserState.rootPath,
      relative_path: storageBrowserState.relativePath,
      name,
    });
    storageBrowserSetActivity(`Created folder ${name}.`);
    refreshStorageBrowser();
  } catch (error) {
    storageBrowserSetMsg(messageText(error), "error");
  }
}
async function promptCreateStorageBrowserFile() {
  const name = currentUiWindow().prompt("Text file name", "notes.txt");
  if (!name) return;
  try {
    const payload = await storageBrowserPost("create_file", {
      root_path: storageBrowserState.rootPath,
      relative_path: storageBrowserState.relativePath,
      name,
    });
    storageBrowserSetActivity(`Created file ${name}.`);
    refreshStorageBrowser();
    if (payload?.relative_path) openStorageBrowserFile(payload.relative_path);
  } catch (error) {
    storageBrowserSetMsg(messageText(error), "error");
  }
}
function upsertStorageBrowserOpenFile(fileRow) {
  const path = String(fileRow?.relative_path || "");
  if (!path) return;
  const prepared = {
    ...fileRow,
    chunk: fileRow?.chunk && typeof fileRow.chunk === "object" ? { ...fileRow.chunk } : null,
    session_id: String(fileRow?.session_id || ""),
    chunked: !!fileRow?.chunked,
    chunk_size: Number(fileRow?.chunk_size || 0),
    loaded_offset: Number(fileRow?.chunk?.offset || 0),
    loaded_length: Number(fileRow?.chunk?.length_bytes || 0),
    original_text: String(fileRow?.text || ""),
    original_hex_text: String(fileRow?.hex_text || storageEditorHexTextFromRows(fileRow?.hex_rows || [])),
    hex_text: String(fileRow?.hex_text || storageEditorHexTextFromRows(fileRow?.hex_rows || [])),
  };
  if (prepared.chunked && prepared.chunk) {
    if (prepared.is_text) {
      prepared.text = String(prepared.chunk.text || "");
      prepared.original_text = prepared.text;
    } else {
      const bytes = prepared.chunk.base64 ? Uint8Array.from(atob(String(prepared.chunk.base64 || "")), (ch) => ch.charCodeAt(0)) : new Uint8Array();
      prepared.binary_base64 = String(prepared.chunk.base64 || "");
      prepared.hex_text = Array.from(bytes).map((byte) => byte.toString(16).padStart(2, "0")).join("");
      prepared.original_hex_text = prepared.hex_text;
      prepared.hex_rows = [];
    }
  }
  const next = storageBrowserState.openFiles.filter((row) => String(row?.relative_path || "") !== path);
  next.push(prepared);
  storageBrowserState.openFiles = next;
  storageBrowserState.activeFilePath = path;
  renderStorageBrowserOpenFileTabs();
  persistStorageBrowserSessionCache();
}
async function openStorageBrowserFile(relativePath) {
  try {
    storageBrowserSetActivity(`Opening file ${relativePath}...`);
    const payload = await storageBrowserPost("read_file", {
      root_path: storageBrowserState.rootPath,
      relative_path: relativePath,
    });
    upsertStorageBrowserOpenFile(payload || {});
    const file = activeStorageEditorFile();
    if (file && storageEditorMediaPreviewable(file)) {
      await loadStorageBrowserMediaMetadata(file).catch(() => null);
    }
    const fileSize = Number(payload?.size_bytes || 0);
    storageBrowserSetActivity(
      fileSize > Number(payload?.chunk_size || 0)
        ? `Opened ${relativePath} in chunked ${payload?.is_text ? "text" : "hex"} mode.`
        : `Opened ${relativePath}.`,
    );
    openStorageEditorModal();
  } catch (error) {
    storageBrowserSetMsg(messageText(error), "error");
  }
}
async function openStorageBrowserFileReadOnly(rootPath, relativePath) {
  try {
    const previousRoot = storageBrowserState.rootPath;
    storageBrowserState.rootPath = String(rootPath || previousRoot || "");
    const payload = await storageBrowserPost("read_file", {
      root_path: storageBrowserState.rootPath,
      relative_path: relativePath,
    });
    const file = { ...(payload || {}), read_only: true };
    upsertStorageBrowserOpenFile(file);
    storageBrowserState.activeFilePath = String(file.relative_path || relativePath || "");
    storageBrowserState.previewMode = true;
    openStorageEditorModal();
  } catch (error) {
    alert(messageText(error));
  }
}
async function openSelectedStorageBrowserFiles() {
  const entries = storageBrowserSelectedEntries();
  if (!entries.length) {
    storageBrowserSetMsg("Select one or more files first.", "warning");
    return;
  }
  for (const entry of entries) {
    const row = storageBrowserState.entries.find((item) => String(item?.relative_path || "") === entry);
    if (row && String(row?.type || "") !== "folder") {
      await openStorageBrowserFile(entry);
    }
  }
}
function ensureStorageEditorModal() {
  if ($("storageEditorModal")) return;
  const doc = currentUiDocument();
  const modal = doc.createElement("div");
  modal.id = "storageEditorModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card storage-editor-modal-card" role="dialog" aria-modal="true" aria-labelledby="storageEditorTitle"><div class="panel-head"><h2 id="storageEditorTitle">File Editor</h2><div class="storage-editor-head-actions"><button class="plain-close-btn storage-editor-window-btn" title="Minimize" aria-label="Minimize" onclick="minimizeStorageEditorModal()">${svgIcon("minimize")}</button><button class="plain-close-btn storage-editor-window-btn" title="Close" aria-label="Close" onclick="closeStorageEditorModal()">${svgIcon("close")}</button></div></div><div id="storageEditorTabs" class="storage-editor-tabs"></div><div id="storageEditorToolbar" class="storage-editor-toolbar"></div><div id="storageEditorBody" class="storage-editor-body"></div><div class="msg" id="storageEditorMsg"></div></div>`;
  doc.body.appendChild(modal);
}
function minimizeStorageEditorModal() {
  ensureStorageEditorModal();
  $("storageEditorModal").classList.add("hidden");
}
async function promptStorageEditorCloseDecision(file) {
  ensureClubDecisionModal();
  $("clubDecisionTitle").textContent = "Unsaved Changes";
  $("clubDecisionBody").innerHTML = `Save changes to <code>${escapeHtml(file?.name || file?.relative_path || "file")}</code> before closing?`;
  $("clubDecisionBody").classList.remove("danger-copy");
  $("clubDecisionInputWrap").classList.add("hidden");
  $("clubDecisionInput").value = "";
  $("clubDecisionCancelBtn").classList.remove("hidden");
  $("clubDecisionCancelBtn").textContent = "Cancel";
  $("clubDecisionOkBtn").textContent = "Save";
  $("clubDecisionOkBtn").classList.remove("blue", "green", "amber", "red");
  $("clubDecisionOkBtn").classList.add("green");
  let discardBtn = $("clubDecisionDiscardBtn");
  if (!discardBtn) {
    discardBtn = currentUiDocument().createElement("button");
    discardBtn.id = "clubDecisionDiscardBtn";
    discardBtn.className = "btn amber";
    discardBtn.textContent = "Discard";
    discardBtn.onclick = () => resolveClubDecisionModal("discard");
    $("clubDecisionOkBtn")?.parentNode?.insertBefore(discardBtn, $("clubDecisionOkBtn"));
  }
  discardBtn.classList.remove("hidden");
  $("clubDecisionModal").classList.remove("hidden");
  return new Promise((resolve) => {
    clubDecisionResolver = ({ action }) => {
      discardBtn?.classList.add("hidden");
      resolve(action || "cancel");
    };
  });
}
function removeStorageEditorFile(filePath = "") {
  const target = String(filePath || storageBrowserState.activeFilePath || "");
  const file = (storageBrowserState.openFiles || []).find((row) => String(row?.relative_path || "") === target);
  if (file?.session_id) {
    storageBrowserPost("close_file_session", { session_id: file.session_id }, { silentFailure: true }).catch(() => {});
  }
  storageBrowserState.openFiles = (storageBrowserState.openFiles || []).filter((row) => String(row?.relative_path || "") !== target);
  storageBrowserState.activeFilePath = String(storageBrowserState.openFiles[storageBrowserState.openFiles.length - 1]?.relative_path || "");
  renderStorageBrowserOpenFileTabs();
  persistStorageBrowserSessionCache();
}
async function closeStorageEditorFile(filePath = "") {
  const target = String(filePath || storageBrowserState.activeFilePath || "");
  if (!target) return;
  const previousActive = String(storageBrowserState.activeFilePath || "");
  const targetFile = (storageBrowserState.openFiles || []).find((row) => String(row?.relative_path || "") === target);
  if (!targetFile) return;
  if (previousActive !== target) {
    storageBrowserState.activeFilePath = target;
    renderStorageEditorModal();
  }
  const file = activeStorageEditorFile();
  if (storageBrowserFileDirty(file)) {
    const action = await promptStorageEditorCloseDecision(file);
    if (action === "cancel") {
      if (previousActive && previousActive !== target) {
        storageBrowserState.activeFilePath = previousActive;
        renderStorageEditorModal();
      }
      return;
    }
    if (action === "ok") {
      await saveActiveStorageEditorFile();
    } else if (action === "discard") {
      discardActiveStorageEditorChanges();
    }
  }
  removeStorageEditorFile(target);
  if (storageBrowserState.openFiles.length) {
    if (previousActive && previousActive !== target && storageBrowserState.openFiles.some((row) => String(row?.relative_path || "") === previousActive)) {
      storageBrowserState.activeFilePath = previousActive;
    }
    openStorageEditorModal();
    return;
  }
  minimizeStorageEditorModal();
}
async function closeStorageEditorModal() {
  const file = activeStorageEditorFile();
  if (!file) {
    minimizeStorageEditorModal();
    return;
  }
  if (storageBrowserFileDirty(file)) {
    const action = await promptStorageEditorCloseDecision(file);
    if (action === "cancel") return;
    if (action === "ok") {
      await saveActiveStorageEditorFile();
    } else if (action === "discard") {
      discardActiveStorageEditorChanges();
    }
  }
  removeStorageEditorFile(file.relative_path || "");
  if (storageBrowserState.openFiles.length) {
    openStorageEditorModal();
    return;
  }
  minimizeStorageEditorModal();
}
function openStorageEditorModal() {
  renderStorageEditorModal();
}
function reopenStorageEditorFile(relativePath) {
  storageBrowserState.activeFilePath = String(relativePath || "");
  persistStorageBrowserSessionCache();
  openStorageEditorModal();
}
function activeStorageEditorFile() {
  return storageBrowserState.openFiles.find((row) => String(row?.relative_path || "") === String(storageBrowserState.activeFilePath || "")) || storageBrowserState.openFiles[storageBrowserState.openFiles.length - 1] || null;
}
function storageEditorChunkRangeLabel(file) {
  const start = Number(file?.loaded_offset || 0);
  const end = Math.min(
    Number(file?.size_bytes || 0),
    start + Number(file?.loaded_length || 0),
  );
  return `${storageBrowserFormatBytes(start)} - ${storageBrowserFormatBytes(end)} of ${storageBrowserFormatBytes(file?.size_bytes || 0)}`;
}
async function loadStorageEditorChunk(file, offset, options = {}) {
  if (!file?.session_id) return;
  const nextOffset = Math.max(0, Math.min(Number(offset || 0), Math.max(0, Number(file.size_bytes || 0) - 1)));
  const payload = await storageBrowserPost("read_file_chunk", {
    session_id: file.session_id,
    offset: nextOffset,
    limit: file.chunk_size || 1024 * 1024,
  });
  file.loaded_offset = Number(payload?.offset || 0);
  file.loaded_length = Number(payload?.length_bytes || 0);
  if (file.is_text) {
    file.text = String(payload?.text || "");
    file.original_text = file.text;
  } else {
    file.binary_base64 = String(payload?.base64 || "");
    const bytes = file.binary_base64 ? Uint8Array.from(atob(file.binary_base64), (ch) => ch.charCodeAt(0)) : new Uint8Array();
    file.hex_text = Array.from(bytes).map((byte) => byte.toString(16).padStart(2, "0")).join("");
    file.original_hex_text = file.hex_text;
    file.hex_rows = [];
  }
  if (!options.silent) {
    storageBrowserSetActivity(`Loaded chunk ${storageEditorChunkRangeLabel(file)}.`);
  }
  persistStorageBrowserSessionCache();
  renderStorageEditorModal();
}
async function loadAdjacentStorageEditorChunk(direction = 1) {
  const file = activeStorageEditorFile();
  if (!file?.chunked) return;
  const step = Math.max(1, Number(file.chunk_size || 1024 * 1024));
  const nextOffset = Number(file.loaded_offset || 0) + (direction < 0 ? -step : step);
  if (nextOffset < 0 || nextOffset >= Number(file.size_bytes || 0)) return;
  await loadStorageEditorChunk(file, nextOffset);
}
function maybeAdvanceChunkedEditorFromScroll(event, directionHint = 0) {
  const target = event?.target;
  const file = activeStorageEditorFile();
  if (!file?.chunked || !target) return;
  const maxScrollTop = Math.max(0, Number(target.scrollHeight || 0) - Number(target.clientHeight || 0));
  if (maxScrollTop <= 0) return;
  const top = Number(target.scrollTop || 0);
  if (top >= maxScrollTop - 24 && Number(file.loaded_offset || 0) + Number(file.loaded_length || 0) < Number(file.size_bytes || 0)) {
    loadAdjacentStorageEditorChunk(1).catch((error) => setElementMsg("storageEditorMsg", messageText(error), "error"));
  } else if ((top <= 8 || directionHint < 0) && Number(file.loaded_offset || 0) > 0) {
    loadAdjacentStorageEditorChunk(-1).catch((error) => setElementMsg("storageEditorMsg", messageText(error), "error"));
  }
}
function storageEditorExtension(file) {
  const name = String(file?.name || file?.relative_path || "").toLowerCase();
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot + 1) : "";
}
function storageEditorLanguageTag(file) {
  const ext = storageEditorExtension(file);
  const map = {
    md: "markdown",
    markdown: "markdown",
    js: "javascript",
    cjs: "javascript",
    mjs: "javascript",
    ts: "typescript",
    jsx: "javascript",
    tsx: "typescript",
    py: "python",
    sh: "bash",
    zsh: "bash",
    yml: "yaml",
    yaml: "yaml",
    html: "html",
    htm: "html",
    css: "css",
    json: "json",
    xml: "xml",
    ini: "ini",
    cfg: "ini",
    conf: "ini",
    log: "text",
    txt: "text",
  };
  return map[ext] || ext || "text";
}
function storageEditorPreviewHtml(file, text) {
  if (file && !file.is_text) {
    const mime = String(file.mime || "").toLowerCase();
    const previewUrl = storageBrowserPreviewUrl(file);
    if (!previewUrl) {
      return `<div class="storage-editor-plain-preview">Preview is only available after the file bytes are loaded.</div>`;
    }
    if (mime.startsWith("image/")) {
      return `<div class="storage-editor-media-preview"><img src="${previewUrl}" alt="${escapeHtml(file.name || "preview")}" /></div>`;
    }
    if (mime.startsWith("video/")) {
      return `<div class="storage-editor-media-preview storage-editor-video-preview"><div class="storage-editor-media-toolbar">${renderStorageEditorVideoControls(file)}</div><div class="storage-editor-video-frame"><video id="storageEditorVideo" src="${previewUrl}" controls preload="metadata" playsinline ontimeupdate="renderStorageEditorSubtitleOverlay()" onseeked="renderStorageEditorSubtitleOverlay()" onloadedmetadata="initializeStorageEditorVideoTracks()"><track id="storageEditorNativeSubtitleTrack" kind="subtitles" default /></video><div id="storageEditorSubtitleOverlay" class="storage-editor-subtitle-overlay"></div></div></div>`;
    }
    if (mime.startsWith("audio/")) {
      return `<div class="storage-editor-media-preview"><audio src="${previewUrl}" controls preload="metadata"></audio></div>`;
    }
    if (mime === "application/pdf") {
      return `<div class="storage-editor-media-preview"><embed src="${previewUrl}" type="application/pdf" title="${escapeHtml(file.name || "preview")}" /></div>`;
    }
  }
  const lang = storageEditorLanguageTag(file);
  if (lang === "markdown" && typeof cachedMarkdownToHtml === "function") {
    return cachedMarkdownToHtml(text || "");
  }
  const wrapClass = storageBrowserState.wrapText ? " wrap" : "";
  if (typeof highlightMarkdownCode === "function") {
    return `<pre class="chat-code storage-editor-preview-code${wrapClass}"><div class="chat-code-lang">${escapeHtml(lang || "text")}</div><code>${highlightMarkdownCode(text || "", lang)}</code></pre>`;
  }
  return `<pre class="storage-editor-plain-preview${wrapClass}">${escapeHtml(text || "")}</pre>`;
}
function renderStorageEditorVideoControls(file) {
  const subtitleOptions = Array.isArray(file?.subtitle_options) ? file.subtitle_options : [];
  const audioOptions = Array.isArray(file?.audio_options) ? file.audio_options : [];
  const selectedSubtitleKey = file?.selectedSubtitle
    ? `${file.selectedSubtitle.kind}:${file.selectedSubtitle.stream_index ?? file.selectedSubtitle.relative_path ?? ""}`
    : "";
  const subtitleSelect = `<select id="storageEditorSubtitleSelect" class="storage-editor-media-select" onchange="handleStorageEditorSubtitleSelect(this.value)"><option value="">No subtitles</option>${subtitleOptions.map((row) => {
    const key = `${row.kind}:${row.stream_index ?? row.relative_path ?? ""}`;
    return `<option value="${escapeHtml(key)}" ${key === selectedSubtitleKey ? "selected" : ""}>${escapeHtml(row.label || row.name || key)}</option>`;
  }).join("")}</select>`;
  const audioSelect = `<select id="storageEditorAudioSelect" class="storage-editor-media-select" onchange="handleStorageEditorAudioSelect(this.value)"><option value="">Default audio</option>${audioOptions.map((row) => {
    const key = String(row.stream_index ?? "");
    return `<option value="${escapeHtml(key)}" ${String(file?.selected_audio_stream_index ?? "") === key ? "selected" : ""}>${escapeHtml(row.label || `Audio ${key}`)}</option>`;
  }).join("")}</select>`;
  const subtitleModeIcon = storageBrowserState.subtitleMode === "track" ? "view" : "hide";
  const subtitleModeTitle = storageBrowserState.subtitleMode === "track" ? "Using native track subtitles" : "Using manual overlay subtitles";
  return `<div class="storage-editor-media-controls">${renderIconButton({ title: "Decrease subtitle size", action: "adjustStorageEditorSubtitleSize(-1)", icon: "minus", className: "storage-editor-tool" })}${renderIconButton({ title: "Increase subtitle size", action: "adjustStorageEditorSubtitleSize(1)", icon: "plus", className: "storage-editor-tool" })}${renderIconButton({ title: "Subtitle delay -0.1s", action: "adjustStorageEditorSubtitleDelay(-0.1)", icon: "chevron-left", className: "storage-editor-tool" })}<span id="storageEditorSubtitleDelayLabel" class="storage-editor-media-delay">${escapeHtml(`${storageBrowserState.subtitleDelaySeconds >= 0 ? "+" : ""}${storageBrowserState.subtitleDelaySeconds.toFixed(1)}s`)}</span>${renderIconButton({ title: "Subtitle delay +0.1s", action: "adjustStorageEditorSubtitleDelay(0.1)", icon: "chevron-right", className: "storage-editor-tool" })}${renderIconButton({ title: subtitleModeTitle, action: "toggleStorageEditorSubtitleMode()", icon: subtitleModeIcon, className: "storage-editor-tool" })}${subtitleSelect}${audioSelect}</div>`;
}
function currentStorageEditorVideo() {
  return $("storageEditorVideo");
}
function renderStorageEditorSubtitleOverlay() {
  const file = activeStorageEditorFile();
  const video = currentStorageEditorVideo();
  const overlay = $("storageEditorSubtitleOverlay");
  if (!file || !video || !overlay) return;
  const cues = Array.isArray(file.subtitle_cues) ? file.subtitle_cues : [];
  const now = Number(video.currentTime || 0) + Number(storageBrowserState.subtitleDelaySeconds || 0);
  const active = cues.filter((cue) => now >= Number(cue.start || 0) && now <= Number(cue.end || 0));
  overlay.style.fontSize = `${Math.round(18 * (Number(storageBrowserState.subtitleFontScale || 1) || 1))}px`;
  const full = !!document.fullscreenElement && (document.fullscreenElement === video || document.fullscreenElement.contains?.(video));
  overlay.style.display = storageBrowserState.subtitleMode === "overlay" && !full ? "" : "none";
  overlay.innerHTML = active.map((cue) => `<div class="storage-editor-subtitle-line">${escapeHtml(String(cue.text || "")).replace(/\n/g, "<br>")}</div>`).join("");
}
function syncStorageEditorNativeSubtitleTrack() {
  const file = activeStorageEditorFile();
  const video = currentStorageEditorVideo();
  const element = $("storageEditorNativeSubtitleTrack");
  if (!file || !video || !element) return;
  const url = storageEditorSubtitleTrackUrl(file);
  if (!url) {
    element.removeAttribute("src");
    if (video.textTracks?.[0]) video.textTracks[0].mode = "disabled";
    return;
  }
  element.src = url;
  element.srclang = String(file?.selectedSubtitle?.language_code || "en") || "en";
  element.label = String(file?.selectedSubtitle?.label || "Subtitles") || "Subtitles";
  element.default = true;
  if (video.textTracks?.[0]) video.textTracks[0].mode = storageBrowserState.subtitleMode === "track" ? "showing" : "disabled";
}
function toggleStorageEditorSubtitleMode() {
  const video = currentStorageEditorVideo();
  const currentTime = Number(video?.currentTime || 0);
  const wasPaused = video ? !!video.paused : true;
  storageBrowserState.subtitleMode = storageBrowserState.subtitleMode === "track" ? "overlay" : "track";
  persistStorageBrowserSessionCache();
  syncStorageEditorNativeSubtitleTrack();
  renderStorageEditorSubtitleOverlay();
  if (video) {
    try {
      video.currentTime = currentTime;
    } catch (error) {}
    if (!wasPaused) {
      const playPromise = video.play?.();
      if (playPromise && typeof playPromise.catch === "function") playPromise.catch(() => {});
    }
  }
}
function handleStorageEditorSubtitleSelect(value) {
  const file = activeStorageEditorFile();
  if (!file) return;
  const key = String(value || "");
  const next = (file.subtitle_options || []).find((row) => `${row.kind}:${row.stream_index ?? row.relative_path ?? ""}` === key) || null;
  loadStorageBrowserSubtitleSelection(file, next).catch((error) => setElementMsg("storageEditorMsg", messageText(error), "error"));
}
function adjustStorageEditorSubtitleDelay(delta) {
  storageBrowserState.subtitleDelaySeconds = Math.round((Number(storageBrowserState.subtitleDelaySeconds || 0) + Number(delta || 0)) * 10) / 10;
  const label = $("storageEditorSubtitleDelayLabel");
  if (label) label.textContent = `${storageBrowserState.subtitleDelaySeconds >= 0 ? "+" : ""}${storageBrowserState.subtitleDelaySeconds.toFixed(1)}s`;
  persistStorageBrowserSessionCache();
  syncStorageEditorNativeSubtitleTrack();
  renderStorageEditorSubtitleOverlay();
}
function adjustStorageEditorSubtitleSize(delta) {
  const current = Number(storageBrowserState.subtitleFontScale || 1) || 1;
  storageBrowserState.subtitleFontScale = Math.max(0.6, Math.min(2.4, Math.round((current + (Number(delta || 0) * 0.1)) * 10) / 10));
  persistStorageBrowserSessionCache();
  renderStorageEditorSubtitleOverlay();
}
function initializeStorageEditorVideoTracks() {
  const file = activeStorageEditorFile();
  const video = currentStorageEditorVideo();
  if (!file || !video) return;
  syncStorageEditorNativeSubtitleTrack();
  renderStorageEditorSubtitleOverlay();
  if (video.audioTracks && video.audioTracks.length) {
    const preferred = String(file.selected_audio_stream_index ?? "");
    for (let index = 0; index < video.audioTracks.length; index += 1) {
      const track = video.audioTracks[index];
      track.enabled = preferred ? String(index) === preferred : index === 0;
    }
  }
}
function handleStorageEditorAudioSelect(value) {
  const file = activeStorageEditorFile();
  const video = currentStorageEditorVideo();
  if (!file) return;
  const normalized = String(value || "");
  file.selected_audio_stream_index = normalized === "" ? -1 : Number(normalized);
  if (video?.audioTracks && video.audioTracks.length) {
    for (let index = 0; index < video.audioTracks.length; index += 1) {
      video.audioTracks[index].enabled = normalized === "" ? index === 0 : String(index) === normalized;
    }
  }
}
function storageEditorHexTextFromRows(rows = []) {
  return (rows || []).map((row) => String(row?.hex || "").trim()).filter(Boolean).join("\n");
}
function storageEditorCleanHexText(text = "") {
  return String(text || "").replace(/[^0-9a-fA-F]/g, "").toLowerCase();
}
function storageEditorHexText(file) {
  return storageEditorCleanHexText(file?.hex_text || storageEditorHexTextFromRows(file?.hex_rows || []));
}
function storageEditorCompleteHexText(text = "") {
  const normalized = storageEditorCleanHexText(text);
  return normalized.length % 2 === 0 ? normalized : normalized.slice(0, -1);
}
let storageEditorHexBytesPerRowValue = 16;
let storageEditorHexResizeTimer = 0;
function storageEditorHexColumnWidthPx() {
  const probe = $("storageEditorHexTextarea") || $("storageEditorBody");
  const uiDocument = currentUiDocument();
  const uiWindow = currentUiWindow();
  try {
    const canvas = uiDocument.createElement("canvas");
    const context = canvas.getContext("2d");
    const computed = probe && uiWindow.getComputedStyle ? uiWindow.getComputedStyle(probe) : null;
    if (context) {
      context.font = computed?.font || "11px Consolas, monospace";
      const measured = Number(context.measureText("0")?.width || 0);
      if (measured > 0) return measured;
    }
  } catch (error) {
    // Fall back to the typical rendered width of 11px Consolas in Chromium.
  }
  return 6.5;
}
function storageEditorHexBytesPerRow() {
  const body = $("storageEditorBody");
  const uiDocument = currentUiDocument();
  const uiWindow = currentUiWindow();
  const card = uiDocument.querySelector(".storage-editor-modal-card");
  const available = Math.max(
    0,
    Number(body?.clientWidth || 0),
    Number(card?.clientWidth || 0) - 32,
    Number(uiWindow.innerWidth || 0) - 96,
  );
  const availableCh = available / storageEditorHexColumnWidthPx();
  const rawBytes = Math.floor((availableCh - 15) / 4);
  const roundedBytes = Math.floor(rawBytes / 8) * 8;
  return Math.max(16, Math.min(96, roundedBytes || 16));
}
function storageEditorHexCurrentBytesPerRow() {
  const value = Number(
    currentUiDocument().querySelector(".storage-editor-hex-editor")?.dataset?.bytesPerRow ||
      storageEditorHexBytesPerRowValue ||
      16,
  );
  return storageEditorNormalizeHexBytesPerRow(value);
}
function storageEditorNormalizeHexBytesPerRow(value) {
  return Math.max(16, Math.min(96, Math.floor(Number(value || 16) / 8) * 8 || 16));
}
function storageEditorFormatHexText(text = "", bytesPerRow = storageEditorHexCurrentBytesPerRow()) {
  const normalized = storageEditorCleanHexText(text);
  const pairs = normalized.match(/.{1,2}/g) || [];
  const rows = [];
  const rowSize = storageEditorNormalizeHexBytesPerRow(bytesPerRow);
  for (let index = 0; index < pairs.length; index += rowSize) {
    rows.push(pairs.slice(index, index + rowSize).join(" "));
  }
  return rows.join("\n");
}
function storageEditorHexCursorForCleanIndex(formatted, cleanIndex) {
  if (cleanIndex <= 0) return 0;
  let seen = 0;
  for (let index = 0; index < formatted.length; index += 1) {
    if (/[0-9a-fA-F]/.test(formatted[index])) {
      seen += 1;
      if (seen >= cleanIndex) return index + 1;
    }
  }
  return formatted.length;
}
function storageEditorCollectHexText({ strict = false } = {}) {
  const area = $("storageEditorHexTextarea");
  const normalized = storageEditorCleanHexText(area ? area.value : storageEditorHexText(activeStorageEditorFile()));
  if (strict && normalized.length % 2 !== 0) {
    throw new Error("Hex data must contain complete byte pairs before saving.");
  }
  return normalized;
}
function storageEditorHexRowsFromText(text = "", bytesPerRow = storageEditorHexCurrentBytesPerRow()) {
  const normalized = storageEditorCompleteHexText(text);
  if (!normalized) return [];
  const rowSize = storageEditorNormalizeHexBytesPerRow(bytesPerRow);
  const bytes = [];
  for (let index = 0; index < normalized.length; index += 2) {
    bytes.push(parseInt(normalized.slice(index, index + 2), 16));
  }
  const rows = [];
  for (let offset = 0; offset < bytes.length; offset += rowSize) {
    const chunk = bytes.slice(offset, offset + rowSize);
    rows.push({
      offset,
      hex: chunk.map((byte) => byte.toString(16).padStart(2, "0")).join(" "),
      ascii: chunk.map((byte) => (byte >= 32 && byte < 127 ? String.fromCharCode(byte) : ".")).join(""),
    });
  }
  return rows;
}
function storageEditorHexColumnText(rows, key) {
  return (rows || []).map((row) => String(row?.[key] || "")).join("\n");
}
function renderStorageEditorToolbar(file) {
  const toolbar = $("storageEditorToolbar");
  if (!toolbar || !file) return;
  const wrapButtonClass = `storage-editor-tool${storageBrowserState.wrapText ? " active" : ""}`;
  const downloadButton = renderIconButton({ title: "Download", action: "downloadActiveStorageEditorFile()", icon: "download", className: "storage-editor-tool" });
  const discardButton = renderIconButton({ title: "Discard changes", action: "discardActiveStorageEditorChanges()", icon: "close", className: "storage-editor-tool", disabled: !!file.read_only });
  const deleteButton = renderIconButton({ title: "Delete file", action: "deleteActiveStorageEditorFile()", icon: "delete", className: "storage-editor-tool danger", disabled: !!file.read_only || !!storageBrowserState.previewMode });
  if (file.read_only) {
    toolbar.innerHTML = `<span class="storage-editor-chunk-label">Read-only preview</span>${renderIconButton({ title: "Copy", action: "storageEditorCopy()", icon: "copy", className: "storage-editor-tool" })}${renderIconButton({ title: "Cut", action: "storageEditorCut()", icon: "cut", className: "storage-editor-tool", disabled: true })}${renderIconButton({ title: "Paste", action: "storageEditorPaste()", icon: "paste", className: "storage-editor-tool", disabled: true })}<span class="storage-editor-toolbar-separator" aria-hidden="true"></span>${renderIconButton({ title: "Undo", action: "storageEditorUndo()", icon: "undo", className: "storage-editor-tool", disabled: true })}${renderIconButton({ title: "Redo", action: "storageEditorRedo()", icon: "redo", className: "storage-editor-tool", disabled: true })}<span class="storage-editor-toolbar-separator" aria-hidden="true"></span>${renderIconButton({ title: storageBrowserState.wrapText ? "Disable word wrap" : "Enable word wrap", action: "toggleStorageEditorWrap()", icon: "wrap", className: wrapButtonClass })}${renderIconButton({ title: "Preview locked", action: "toggleStorageEditorPreview()", icon: "preview", className: "storage-editor-tool", disabled: true })}${downloadButton}<span class="storage-editor-toolbar-separator" aria-hidden="true"></span>${discardButton}${deleteButton}${renderIconButton({ title: "Save", action: "saveActiveStorageEditorFile()", icon: "save", className: "storage-editor-tool", disabled: true })}`;
    return;
  }
  const binaryPreviewable = !file.is_text && /^(image\/|video\/|audio\/)|^application\/pdf$/i.test(String(file.mime || ""));
  const previewButton = (!file.chunked && file.is_text) || binaryPreviewable
    ? `<button class="iconbtn storage-editor-tool" title="${storageBrowserState.previewMode ? "Return to edit mode" : "Preview rendered output"}" aria-label="${storageBrowserState.previewMode ? "Return to edit mode" : "Preview rendered output"}" onclick="toggleStorageEditorPreview()">${svgIcon(storageBrowserState.previewMode ? "hide" : "preview")}</button>`
    : "";
  const chunkButtons = file.chunked
    ? `${renderIconButton({ title: "Previous 1 MB chunk", action: "loadAdjacentStorageEditorChunk(-1)", icon: "chevron-up", className: "storage-editor-tool" })}${renderIconButton({ title: "Next 1 MB chunk", action: "loadAdjacentStorageEditorChunk(1)", icon: "chevron-down", className: "storage-editor-tool" })}<span class="storage-editor-chunk-label">${escapeHtml(storageEditorChunkRangeLabel(file))}</span><span class="storage-editor-toolbar-separator" aria-hidden="true"></span>`
    : "";
  toolbar.innerHTML = `${renderIconButton({ title: "Copy", action: "storageEditorCopy()", icon: "copy", className: "storage-editor-tool" })}${renderIconButton({ title: "Cut", action: "storageEditorCut()", icon: "cut", className: "storage-editor-tool" })}${renderIconButton({ title: "Paste", action: "storageEditorPaste()", icon: "paste", className: "storage-editor-tool" })}<span class="storage-editor-toolbar-separator" aria-hidden="true"></span>${renderIconButton({ title: "Undo", action: "storageEditorUndo()", icon: "undo", className: "storage-editor-tool" })}${renderIconButton({ title: "Redo", action: "storageEditorRedo()", icon: "redo", className: "storage-editor-tool" })}<span class="storage-editor-toolbar-separator" aria-hidden="true"></span>${renderIconButton({ title: storageBrowserState.wrapText ? "Disable word wrap" : "Enable word wrap", action: "toggleStorageEditorWrap()", icon: "wrap", className: wrapButtonClass })}${previewButton}${downloadButton}<span class="storage-editor-toolbar-separator${file.is_text || binaryPreviewable ? "" : " hidden"}" aria-hidden="true"></span>${discardButton}${deleteButton}${renderIconButton({ title: "Save", action: "saveActiveStorageEditorFile()", icon: "save", className: "storage-editor-tool" })}`;
  toolbar.innerHTML = `${chunkButtons}${toolbar.innerHTML}`;
}
function renderStorageEditorModal() {
  ensureStorageEditorModal();
  const tabs = $("storageEditorTabs");
  const body = $("storageEditorBody");
  const files = storageBrowserState.openFiles || [];
  if (!files.length) return;
  tabs.innerHTML = files.map((file) => {
    const path = String(file?.relative_path || "");
    const rootPath = String(file?.root_path || storageBrowserState.rootPath || "").replace(/[\\\/]+$/g, "");
    const hoverPath = rootPath && path ? `${rootPath}/${path}` : path || file?.name || "file";
    const active = path === String(storageBrowserState.activeFilePath || "");
    return `<button class="subtab ${active ? "active" : ""}" title="${escapeHtml(hoverPath)}" onclick="activateStorageEditorTab('${escapeJs(path)}')"><span class="storage-editor-tab-close" role="button" tabindex="0" title="Close file" aria-label="Close ${escapeHtml(file.name || path || "file")}" onclick="event.stopPropagation(); closeStorageEditorFile('${escapeJs(path)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();event.stopPropagation();closeStorageEditorFile('${escapeJs(path)}')}">✕</span><span>${escapeHtml(file.name || path || "file")}</span></button>`;
  }).join("");
  const file = activeStorageEditorFile();
  if (!file) return;
  if (file.read_only) storageBrowserState.previewMode = true;
  renderStorageEditorToolbar(file);
  if (storageBrowserState.previewMode) {
    const previewText = file.is_text ? String(file.text || "") : "";
    body.innerHTML = `<div class="storage-editor-preview-only"><div class="storage-editor-preview-head">Preview</div><div class="chat-message-markdown storage-editor-preview-body">${storageEditorPreviewHtml(file, previewText)}</div></div>`;
  } else if (file.is_text) {
    const text = String(file.text || "");
    const lineCount = Math.max(1, text.split("\n").length);
    body.innerHTML = `<div class="storage-editor-text-shell"><div id="storageEditorLineNumbers" class="storage-editor-line-numbers">${Array.from({ length: lineCount }, (_, index) => `<span>${index + 1}</span>`).join("")}</div><textarea id="storageEditorTextarea" class="storage-editor-textarea${storageBrowserState.wrapText ? " wrap" : ""}" spellcheck="false" oninput="syncStorageEditorLineNumbers()" onscroll="syncStorageEditorLineNumberScroll(); maybeAdvanceChunkedEditorFromScroll(event)">${escapeHtml(text)}</textarea></div>`;
  } else {
    const bytesPerRow = storageEditorHexBytesPerRow();
    storageEditorHexBytesPerRowValue = bytesPerRow;
    const hexText = storageEditorHexText(file);
    file.hex_text = hexText;
    file.hex_rows = storageEditorHexRowsFromText(hexText, bytesPerRow);
    const rows = file.hex_rows || [];
    body.innerHTML = `<div class="storage-editor-hex-wrap"><div class="storage-editor-hex-head">${escapeHtml(file.mime || "binary")} · ${file.chunked ? `streaming chunk ${escapeHtml(storageEditorChunkRangeLabel(file))}` : "edit raw bytes below"}</div><div class="storage-editor-hex-editor${bytesPerRow > 16 ? " is-wide" : ""}" data-bytes-per-row="${bytesPerRow}" style="--storage-editor-ascii-column:${bytesPerRow + 1}ch"><div class="storage-editor-hex-grid-head"><span>Offset</span><span>Hex Bytes</span><span>ASCII</span></div><pre id="storageEditorHexOffsets" class="storage-editor-hex-offsets">${escapeHtml(rows.map((row) => Number((row?.offset || 0) + Number(file.loaded_offset || 0)).toString(16).padStart(8, "0")).join("\n"))}</pre><textarea id="storageEditorHexTextarea" class="storage-editor-hex-textarea${storageBrowserState.wrapText ? " wrap" : ""}" inputmode="text" spellcheck="false" onbeforeinput="handleStorageEditorHexBeforeInput(event)" oninput="handleStorageEditorHexTextInput(event)" onpaste="handleStorageEditorHexPaste(event)" onscroll="syncStorageEditorHexScroll(); maybeAdvanceChunkedEditorFromScroll(event)">${escapeHtml(storageEditorFormatHexText(hexText, bytesPerRow))}</textarea><pre id="storageEditorHexAscii" class="storage-editor-hex-ascii">${escapeHtml(storageEditorHexColumnText(rows, "ascii"))}</pre></div></div>`;
  }
  $("storageEditorModal").classList.remove("hidden");
  syncStorageEditorLineNumbers();
  syncStorageEditorHexPreview();
}
function activateStorageEditorTab(relativePath) {
  storageBrowserState.activeFilePath = String(relativePath || "");
  const file = activeStorageEditorFile();
  storageBrowserState.previewMode = !!file?.read_only;
  renderStorageBrowserOpenFileTabs();
  persistStorageBrowserSessionCache();
  renderStorageEditorModal();
}
function syncStorageEditorLineNumbers() {
  const file = activeStorageEditorFile();
  const area = $("storageEditorTextarea");
  const gutter = $("storageEditorLineNumbers");
  if (file && area) file.text = String(area.value || "");
  if (gutter && area) {
    const lineCount = Math.max(1, String(area.value || "").split("\n").length);
    gutter.innerHTML = Array.from({ length: lineCount }, (_, index) => `<span>${index + 1}</span>`).join("");
  }
  syncStorageEditorLineNumberScroll();
}
function syncStorageEditorLineNumberScroll() {
  const area = $("storageEditorTextarea");
  const gutter = $("storageEditorLineNumbers");
  if (area && gutter) gutter.scrollTop = area.scrollTop;
}
function syncStorageEditorHexPreview() {
  const file = activeStorageEditorFile();
  const area = $("storageEditorHexTextarea");
  if (!file || !area) return;
  try {
    file.hex_text = storageEditorCleanHexText(area.value);
    const bytesPerRow = storageEditorHexCurrentBytesPerRow();
    file.hex_rows = storageEditorHexRowsFromText(file.hex_text, bytesPerRow);
    const rows = file.hex_rows || [];
    const offsets = $("storageEditorHexOffsets");
    const ascii = $("storageEditorHexAscii");
    if (offsets) {
      offsets.textContent = rows.map((row) => Number(row?.offset || 0).toString(16).padStart(8, "0")).join("\n");
    }
    if (ascii) ascii.textContent = rows.map((row) => String(row?.ascii || "")).join("\n");
    syncStorageEditorHexScroll();
    setElementMsg("storageEditorMsg", "");
  } catch (error) {
    setElementMsg("storageEditorMsg", messageText(error), "error");
  }
}
function syncStorageEditorHexScroll() {
  const area = $("storageEditorHexTextarea");
  if (!area) return;
  const offsets = $("storageEditorHexOffsets");
  const ascii = $("storageEditorHexAscii");
  if (offsets) offsets.scrollTop = area.scrollTop;
  if (ascii) ascii.scrollTop = area.scrollTop;
}
function refreshStorageEditorHexLayoutForResize() {
  const modal = $("storageEditorModal");
  const area = $("storageEditorHexTextarea");
  if (!modal || modal.classList.contains("hidden") || !area) return;
  const nextBytesPerRow = storageEditorHexBytesPerRow();
  if (nextBytesPerRow === storageEditorHexCurrentBytesPerRow()) return;
  const file = activeStorageEditorFile();
  if (file) file.hex_text = storageEditorCleanHexText(area.value);
  storageEditorHexBytesPerRowValue = nextBytesPerRow;
  renderStorageEditorModal();
}
function scheduleStorageEditorHexLayoutRefresh() {
  if (storageEditorHexResizeTimer) clearTimeout(storageEditorHexResizeTimer);
  storageEditorHexResizeTimer = setTimeout(refreshStorageEditorHexLayoutForResize, 120);
}
window.addEventListener("resize", scheduleStorageEditorHexLayoutRefresh);
async function saveActiveStorageEditorFile() {
  const file = activeStorageEditorFile();
  const area = $("storageEditorTextarea");
  try {
  if (file?.chunked && file?.session_id) {
      if (file.is_text && area) {
        const text = String(area.value || "");
        const nextBytes = new TextEncoder().encode(text);
        if (nextBytes.length !== Number(file.loaded_length || 0)) {
          throw new Error("Chunked text saves must keep the current 1 MB chunk length unchanged.");
        }
        await storageBrowserPost("save_file_chunk", {
          session_id: file.session_id,
          offset: file.loaded_offset || 0,
          text,
          expected_bytes: file.loaded_length || 0,
        });
        file.text = text;
        file.original_text = text;
      } else {
        const hexText = storageEditorCollectHexText({ strict: true });
        const normalized = storageEditorCleanHexText(hexText);
        if (normalized.length / 2 !== Number(file.loaded_length || 0)) {
          throw new Error("Chunked hex saves must keep the current 1 MB chunk length unchanged.");
        }
        const bytes = normalized.match(/.{1,2}/g) || [];
        const binary = Uint8Array.from(bytes.map((value) => parseInt(value, 16)));
        let binaryText = "";
        binary.forEach((byte) => {
          binaryText += String.fromCharCode(byte);
        });
        await storageBrowserPost("save_file_chunk", {
          session_id: file.session_id,
          offset: file.loaded_offset || 0,
          base64: btoa(binaryText),
          expected_bytes: file.loaded_length || 0,
        });
        file.hex_text = normalized;
        file.original_hex_text = normalized;
      }
    } else if (file?.is_text && area) {
      await storageBrowserPost("save_file", {
        root_path: storageBrowserState.rootPath,
        relative_path: file.relative_path,
        text: String(area.value || ""),
      });
      file.text = String(area.value || "");
      file.original_text = file.text;
    } else {
      const hexText = storageEditorCollectHexText({ strict: true });
      storageEditorHexRowsFromText(hexText);
      await storageBrowserPost("save_binary_file", {
        root_path: storageBrowserState.rootPath,
        relative_path: file.relative_path,
        hex: hexText,
      });
      file.hex_text = hexText;
      file.original_hex_text = hexText;
      file.hex_rows = storageEditorHexRowsFromText(hexText);
    }
    setElementMsg("storageEditorMsg", "Saved file.", "success");
    storageBrowserSetActivity(`Saved ${file?.relative_path || file?.name || "file"}.`);
    refreshStorageBrowser();
    renderStorageBrowserOpenFileTabs();
    renderStorageEditorModal();
  } catch (error) {
    setElementMsg("storageEditorMsg", messageText(error), "error");
  }
}
function storageEditorCopy() {
  const area = $("storageEditorTextarea");
  if (area) {
    area.focus();
    currentUiDocument().execCommand("copy");
    return;
  }
  const hexArea = $("storageEditorHexTextarea");
  if (hexArea) {
    hexArea.focus();
    currentUiDocument().execCommand("copy");
    return;
  }
  const file = activeStorageEditorFile();
  if (!file) return;
  const selection = String(currentUiWindow()?.getSelection?.() || "").trim();
  const text = selection || (file.is_text ? String(file.text || "") : String(file.hex_text || ""));
  if (!text) return;
  navigator.clipboard.writeText(text)
    .then(() => setElementMsg("storageEditorMsg", "Copied preview.", "success"))
    .catch(() => setElementMsg("storageEditorMsg", "Copy failed on this browser.", "error"));
}
function storageEditorCut() {
  const area = $("storageEditorTextarea");
  if (area) {
    area.focus();
    currentUiDocument().execCommand("cut");
    return;
  }
  const hexArea = $("storageEditorHexTextarea");
  if (hexArea) {
    hexArea.focus();
    currentUiDocument().execCommand("cut");
  }
}
async function storageEditorPaste() {
  const area = $("storageEditorTextarea");
  if (area) {
    area.focus();
    currentUiDocument().execCommand("paste");
    return;
  }
  const hexArea = $("storageEditorHexTextarea");
  if (!hexArea) return;
  try {
    const pasted = await navigator.clipboard.readText();
    applyStorageEditorHexPaste(String(pasted || ""), hexArea);
  } catch (error) {
    setElementMsg("storageEditorMsg", "Paste failed on this browser.", "error");
  }
}
function storageEditorUndo() {
  const area = $("storageEditorTextarea");
  if (area) {
    area.focus();
    currentUiDocument().execCommand("undo");
    return;
  }
  const hexArea = $("storageEditorHexTextarea");
  if (hexArea) {
    hexArea.focus();
    currentUiDocument().execCommand("undo");
  }
}
function storageEditorRedo() {
  const area = $("storageEditorTextarea");
  if (area) {
    area.focus();
    currentUiDocument().execCommand("redo");
    return;
  }
  const hexArea = $("storageEditorHexTextarea");
  if (hexArea) {
    hexArea.focus();
    currentUiDocument().execCommand("redo");
  }
}
function metricsPopupPanelHtml() {
  return `<div class="subtabs">
            <button class="subtab active" data-metric-pane="mMain">Main</button>
            <button class="subtab" data-metric-pane="mGpu">GPUs</button>
            <button class="subtab" data-metric-pane="mCpuRam">CPU+RAM</button>
            <button class="subtab" data-metric-pane="mSystem">System</button>
            <button class="subtab" data-metric-pane="mNetwork">Network</button>
          </div>
          <div id="mMain" class="metricpane active">
            <div class="chartgrid">
              <div class="chart"><canvas id="cGpu"></canvas></div>
              <div class="chart"><canvas id="cMem"></canvas></div>
              <div class="chart"><canvas id="cLatency"></canvas></div>
              <div class="chart"><canvas id="cTps"></canvas></div>
            </div>
          </div>
          <div id="mGpu" class="metricpane">
            <div id="gpuMetricCharts" class="gpu-chartgrid"></div>
          </div>
          <div id="mCpuRam" class="metricpane">
            <div id="ramInfo" class="value smallgap"></div>
            <div class="chartgrid">
              <div class="chart tall"><canvas id="cCpu"></canvas></div>
              <div class="chart tall"><canvas id="cRam"></canvas></div>
            </div>
            <div id="cpuCores" class="coregrid"></div>
          </div>
          <div id="mSystem" class="metricpane">
            <div class="chartgrid">
              <div class="chart"><canvas id="cSystemUtil"></canvas></div>
            </div>
            <div class="panel">
              <h2>System Information</h2>
              <div id="systemInfo" class="value"></div>
            </div>
            <div class="panel">
              <h2>Storage</h2>
              <div id="diskInfo"></div>
            </div>
          </div>
          <div id="mNetwork" class="metricpane">
            <div id="netInfo" class="netgrid"></div>
            <div class="chartgrid">
              <div class="chart"><canvas id="cNetDown"></canvas></div>
              <div class="chart"><canvas id="cNetUp"></canvas></div>
            </div>
          </div>`;
}
function popupWindowNameForMetricsSignature(signature) {
  const token = String(signature || "metrics")
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `club3090-metrics-${token || "viewer"}`;
}
function detachedMetricsPopupHtml(state) {
  const sharedCss = String(document.querySelector("style")?.textContent || "");
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>${escapeHtml(state?.title || "Metrics")}</title>
    <style>${sharedCss}</style>
    <style>
      :root { color-scheme: dark; --bg:#0b0f14; --panel:#121923; --line:#273243; --text:#e8eef7; --muted:#9dafc3; --field:#081018; }
      * { box-sizing:border-box; }
      html, body { margin:0; min-height:100%; background:var(--bg); color:var(--text); font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif; overflow:hidden; }
      body { padding:12px; }
      .popup-card { height:calc(100vh - 24px); overflow:auto; background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:12px; }
      .popup-head { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; margin-bottom:10px; }
      .popup-title-row { display:flex; align-items:center; gap:8px; }
      .popup-title { font-size:20px; font-weight:800; margin:0; }
      .popup-actions { display:flex; align-items:center; gap:8px; }
      .popup-btn { display:inline-flex; align-items:center; justify-content:center; width:20px; height:20px; padding:0; border:0; background:transparent; color:var(--muted); cursor:pointer; }
      .popup-btn:hover, .popup-btn:focus-visible { color:#eef4ff; outline:none; }
      .popup-btn svg { width:18px; height:18px; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; fill:none; }
    </style>
  </head>
  <body>
    <div class="popup-card">
      <div class="popup-head">
        <div>
          <div class="popup-title-row">
            <button class="popup-btn" type="button" id="popupMetricsReattachBtn" title="Reattach metrics" aria-label="Reattach metrics">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M10 19H5v-5m0 5 7-7" />
                <path d="M14 17h3a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H9a2 2 0 0 0-2 2v3" />
              </svg>
            </button>
            <h1 class="popup-title" id="popupMetricsTitle">Metrics</h1>
          </div>
        </div>
        <div class="popup-actions">
          <button class="iconbtn popup-metrics-reset-btn" type="button" id="popupMetricsResetBtn" title="Clear recorded metrics" aria-label="Clear recorded metrics">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M5 7h14M9 7V5h6v2m-7 3v7m4-7v7m4-7v7M7 7l1 12h8l1-12" />
            </svg>
          </button>
        </div>
      </div>
      ${metricsPopupPanelHtml()}
    </div>
    <script>
      (() => {
        const signature = ${JSON.stringify(String(state?.signature || ""))};
        const notify = () => {
          try {
            if (window.opener && !window.opener.closed && typeof window.opener.markDetachedMetricsPopupActive === "function") {
              window.opener.markDetachedMetricsPopupActive(signature);
            }
          } catch (e) {}
        };
        window.addEventListener("focus", notify);
        window.addEventListener("pointerdown", notify, true);
        window.addEventListener("keydown", notify, true);
        document.addEventListener("visibilitychange", notify);
        document.getElementById("popupMetricsReattachBtn")?.addEventListener("click", () => {
          try {
            if (window.opener && !window.opener.closed && typeof window.opener.closeDetachedMetricsPopup === "function") {
              window.opener.closeDetachedMetricsPopup(signature);
            } else {
              window.close();
            }
          } catch (e) {
            window.close();
          }
        });
        const invoke = (name, ...args) => {
          if (!window.opener || window.opener.closed || typeof window.opener.withDetachedMetricsHost !== "function") return;
          return window.opener.withDetachedMetricsHost(signature, () => {
            const target = window.opener[name];
            if (typeof target !== "function") throw new Error(name + " is unavailable");
            return target(...args);
          });
        };
        [
          "ensureStorageBrowserModal",
          "loadStorageBrowser",
          "renderStorageBrowser",
          "toggleStorageBrowserSort",
          "closePresetActionModal",
          "closeStorageBrowserModal",
          "refreshStorageBrowser",
          "duplicateStorageBrowserToMainWindow",
          "downloadStorageBrowserSelection",
          "openStorageBrowserUploadPicker",
          "openSelectedStorageBrowserFiles",
          "deleteStorageBrowserSelection",
          "promptCreateStorageBrowserFolder",
          "promptCreateStorageBrowserFile",
          "handleStorageBrowserUpload",
          "openStorageBrowserEntry",
          "toggleStorageBrowserSelection",
          "openStorageBrowserFile",
          "reopenStorageEditorFile",
          "loadAdjacentStorageEditorChunk",
          "activateStorageEditorTab",
          "ensureStorageEditorModal",
          "openStorageEditorModal",
          "renderStorageEditorModal",
          "minimizeStorageEditorModal",
          "closeStorageEditorModal",
          "closeStorageEditorFile",
          "toggleStorageEditorWrap",
          "toggleStorageEditorPreview",
          "discardActiveStorageEditorChanges",
          "deleteActiveStorageEditorFile",
          "syncStorageEditorLineNumbers",
          "syncStorageEditorLineNumberScroll",
          "syncStorageEditorHexPreview",
          "syncStorageEditorHexScroll",
          "storageEditorCopy",
          "storageEditorCut",
          "storageEditorPaste",
          "storageEditorUndo",
          "storageEditorRedo",
          "saveActiveStorageEditorFile",
          "handleStorageEditorHexBeforeInput",
          "handleStorageEditorHexTextInput",
          "handleStorageEditorHexPaste",
          "toggleStorageMount",
          "openStorageBrowserForVolume",
          "closeClubAlertModal",
          "resolveClubDecisionModal",
        ].forEach((name) => {
          window[name] = (...args) => invoke(name, ...args);
        });
        document.getElementById("popupMetricsResetBtn")?.addEventListener("click", async () => {
          notify();
          try {
            await invoke("promptClearRecordedMetrics");
          } catch (e) {
            window.alert(e && e.message ? e.message : String(e || ""));
          }
        });
        document.querySelectorAll("[data-metric-pane]")?.forEach((button) => {
          button.addEventListener("click", () => {
            const paneId = String(button.getAttribute("data-metric-pane") || "");
            document.querySelectorAll("[data-metric-pane]")?.forEach((node) => {
              node.classList.toggle("active", node === button);
            });
            document.querySelectorAll(".metricpane")?.forEach((node) => {
              node.classList.toggle("active", node.id === paneId);
            });
            try {
              if (window.opener && !window.opener.closed && typeof window.opener.updateDetachedMetricsPopupPane === "function") {
                window.opener.updateDetachedMetricsPopupPane(signature, paneId);
              }
            } catch (e) {}
            notify();
          });
        });
        let resizeTimer = 0;
        window.addEventListener("resize", () => {
          notify();
          clearTimeout(resizeTimer);
          resizeTimer = window.setTimeout(() => {
            try {
              if (window.opener && !window.opener.closed && typeof window.opener.syncDetachedMetricsPopup === "function") {
                window.opener.syncDetachedMetricsPopup(signature, window.opener.lastStatus);
              }
            } catch (e) {}
          }, 90);
        });
        window.addEventListener("beforeunload", () => {
          try {
            if (window.opener && !window.opener.closed && typeof window.opener.notifyDetachedMetricsPopupClosed === "function") {
              window.opener.notifyDetachedMetricsPopupClosed(signature);
            }
          } catch (e) {}
        });
        notify();
      })();
    <\/script>
  </body>
</html>`;
}
function popupMetricsDocument(state) {
  const win = state?.win;
  if (!win || win.closed) return null;
  try {
    return win.document || null;
  } catch (e) {
    return null;
  }
}
function ensureDetachedMetricsPopupWindow(state) {
  if (!state) return null;
  if (state.win && !state.win.closed) return state.win;
  const features = [
    "popup=yes",
    "toolbar=no",
    "location=no",
    "menubar=no",
    "status=no",
    "resizable=yes",
    "scrollbars=yes",
    `width=${METRICS_POPUP_WIDTH}`,
    `height=${METRICS_POPUP_HEIGHT}`,
  ].join(",");
  const win = window.open("", popupWindowNameForMetricsSignature(state.signature), features);
  if (!win) throw new Error("The browser blocked the metrics popup window.");
  state.win = win;
  try {
    win.document.open();
    win.document.write(detachedMetricsPopupHtml(state));
    win.document.close();
  } catch (e) {}
  return win;
}
function renderDetachedMetricsPopup(state, status = lastStatus) {
  const doc = popupMetricsDocument(state);
  if (!doc) return;
  if (doc.title !== String(state.title || "Metrics")) doc.title = String(state.title || "Metrics");
  const title = doc.getElementById("popupMetricsTitle");
  if (title && title.textContent !== String(state.title || "Metrics")) title.textContent = String(state.title || "Metrics");
  setActiveMetricPaneInDocument(doc, state.paneId);
  withMetricsRenderDocument(doc, () => renderMetrics(status || lastStatus || {}, { skipPopups: true }));
}
function markDetachedMetricsPopupActive(signature) {
  const state = window.metricsPopupStates[String(signature || "")];
  if (!state) return;
  state.lastActiveAt = Date.now();
}
function notifyDetachedMetricsPopupClosed(signature) {
  const state = window.metricsPopupStates[String(signature || "")];
  if (!state) return;
  mergeStorageBrowserHostState("popup", "main");
  state.win = null;
  delete window.metricsPopupStates[String(signature || "")];
  applyMetricsVisibility();
}
function pollDetachedMetricsPopupClosures() {
  Object.keys(window.metricsPopupStates).forEach((signature) => {
    const state = window.metricsPopupStates[String(signature || "")];
    if (!state) return;
    if (!state.win || state.win.closed) notifyDetachedMetricsPopupClosed(signature);
  });
}
function closeDetachedMetricsPopup(signature) {
  const key = String(signature || "");
  const state = window.metricsPopupStates[key];
  if (!state) return;
  mergeStorageBrowserHostState("popup", "main");
  const win = state.win;
  state.win = null;
  delete window.metricsPopupStates[key];
  if (win && !win.closed) {
    try {
      win.close();
    } catch (e) {}
  }
  applyMetricsVisibility();
}
function replaceDetachedMetricsPopupPane(signature, paneId) {
  const state = window.metricsPopupStates[String(signature || "")];
  const nextPaneId = normalizeMetricPaneId(paneId);
  if (!state || !nextPaneId || nextPaneId === state.paneId) return false;
  updateDetachedMetricsPopupPane(signature, nextPaneId);
  return true;
}
function updateDetachedMetricsPopupPane(signature, paneId) {
  const state = window.metricsPopupStates[String(signature || "")];
  const nextPaneId = normalizeMetricPaneId(paneId);
  if (!state || !nextPaneId) return false;
  state.paneId = nextPaneId;
  state.label = metricPaneLabel(nextPaneId);
  setActiveMetricPaneInDocument(document, nextPaneId);
  renderDetachedMetricsPopup(state, lastStatus);
  refreshStatus({ force: true, includeSeries: true }).catch(() => {});
  return true;
}
function syncDetachedMetricsPopup(signature, status = lastStatus) {
  const state = window.metricsPopupStates[String(signature || "")];
  if (!state) return;
  if (!state.win || state.win.closed) {
    notifyDetachedMetricsPopupClosed(signature);
    return;
  }
  renderDetachedMetricsPopup(state, status);
}
function syncAllDetachedMetricsPopups(status = lastStatus) {
  Object.keys(window.metricsPopupStates).forEach((signature) => syncDetachedMetricsPopup(signature, status));
}
function currentMetricsPaneDetached() {
  return popupMetricsWindowOpen(currentMetricsPopupTarget().signature);
}
function applyMetricsVisibility() {
  const isMetrics = activeTabName === "metrics";
  document.body.classList.toggle("metrics-tab", isMetrics);
  const section = $("metrics");
  const detached = currentMetricsPaneDetached();
  if (section) section.classList.remove("metrics-card-hidden");
  if ($("metricsDetachedNotice")) $("metricsDetachedNotice").classList.toggle("hidden", !(isMetrics && detached));
  const metricsTabs = document.querySelector("#metrics .subtabs");
  if (metricsTabs) metricsTabs.classList.toggle("hidden", isMetrics && detached);
  if ($("metricsResetBtn")) $("metricsResetBtn").classList.toggle("hidden", isMetrics && detached);
  document.querySelectorAll("#metrics .metricpane").forEach((node) => {
    node.classList.toggle("hidden", isMetrics && detached);
  });
  if ($("metricsPopoutBtn")) {
    $("metricsPopoutBtn").title = detached ? "Reattach metrics" : "Pop out metrics";
    $("metricsPopoutBtn").setAttribute("aria-label", $("metricsPopoutBtn").title);
    $("metricsPopoutBtn").classList.toggle("active", detached);
    $("metricsPopoutBtn").innerHTML = metricsPopoutButtonSvg(detached);
  }
  syncAllDetachedMetricsPopups();
}
function toggleMetricsPopout() {
  const target = currentMetricsPopupTarget();
  if (popupMetricsWindowOpen(target.signature)) {
    closeDetachedMetricsPopup(target.signature);
    return;
  }
  const state = popupMetricsState(target.signature);
  state.paneId = target.paneId;
  state.title = target.title;
  state.label = target.label;
  ensureDetachedMetricsPopupWindow(state);
  state.lastActiveAt = Date.now();
  renderDetachedMetricsPopup(state, lastStatus);
  applyMetricsVisibility();
  refreshStatus({ force: true, includeSeries: true }).catch(() => {});
}
function toggleStorageEditorWrap() {
  storageBrowserState.wrapText = !storageBrowserState.wrapText;
  renderStorageEditorModal();
}
function toggleStorageEditorPreview() {
  storageBrowserState.previewMode = !storageBrowserState.previewMode;
  renderStorageEditorModal();
}
function discardActiveStorageEditorChanges() {
  const file = activeStorageEditorFile();
  if (!file) return;
  if (file.is_text) {
    file.text = String(file.original_text ?? file.text ?? "");
  } else {
    file.hex_text = String(file.original_hex_text ?? file.hex_text ?? "");
    file.hex_rows = storageEditorHexRowsFromText(file.hex_text);
  }
  setElementMsg("storageEditorMsg", "Reverted unsaved changes.", "success");
  renderStorageEditorModal();
}
function handleStorageEditorHexBeforeInput(event) {
  if (!event || event.inputType?.startsWith("delete")) return;
  const text = String(event.data || "");
  if (text && !/^[0-9a-fA-F]+$/.test(text)) {
    event.preventDefault();
    setElementMsg("storageEditorMsg", "Hex editor accepts only hexadecimal characters.", "error");
  }
}
function handleStorageEditorHexTextInput(event) {
  const target = event?.target || $("storageEditorHexTextarea");
  if (!target) return;
  const cleanBeforeCursor = storageEditorCleanHexText(String(target.value || "").slice(0, target.selectionStart || 0)).length;
  const formatted = storageEditorFormatHexText(target.value, storageEditorHexCurrentBytesPerRow());
  if (target.value !== formatted) {
    target.value = formatted;
    const cursor = storageEditorHexCursorForCleanIndex(formatted, cleanBeforeCursor);
    target.setSelectionRange(cursor, cursor);
  }
  syncStorageEditorHexPreview();
}
function applyStorageEditorHexPaste(text, targetArea) {
  const cleaned = String(text || "").replace(/[^0-9a-fA-F]/g, "").toLowerCase();
  if (!cleaned) return;
  if (cleaned.length % 2 !== 0) {
    setElementMsg("storageEditorMsg", "Pasted hex must contain complete byte pairs.", "error");
    return;
  }
  const area = targetArea || $("storageEditorHexTextarea");
  if (!area) return;
  const startClean = storageEditorCleanHexText(area.value.slice(0, area.selectionStart || 0)).length;
  const endClean = storageEditorCleanHexText(area.value.slice(0, area.selectionEnd || 0)).length;
  const current = storageEditorCleanHexText(area.value);
  const next = `${current.slice(0, startClean)}${cleaned}${current.slice(endClean)}`;
  const formatted = storageEditorFormatHexText(next, storageEditorHexCurrentBytesPerRow());
  area.value = formatted;
  const cursor = storageEditorHexCursorForCleanIndex(formatted, startClean + cleaned.length);
  area.setSelectionRange(cursor, cursor);
  handleStorageEditorHexTextInput({ target: area });
}
function handleStorageEditorHexPaste(event) {
  event.preventDefault();
  applyStorageEditorHexPaste(event.clipboardData?.getData("text") || "", event.target);
}
function draw(id, data, key, label, color, options = {}) {
  const c = metricsElement(id);
  if (!c) return;
  const ctx = c.getContext("2d"),
    dpr = devicePixelRatio || 1,
    w = (c.width = c.clientWidth * dpr),
    h = (c.height = c.clientHeight * dpr);
  ctx.clearRect(0, 0, w, h);
  const values = data.map((item) => Number(item?.[key] || 0));
  const visiblePeakValue = Math.max(0, ...values);
  const persistentPeakValue = Math.max(0, Number(options.persistentPeakValue || 0));
  const peakValue = Math.max(visiblePeakValue, persistentPeakValue);
  const currentValue = values.length ? values[values.length - 1] : 0;
  const maxValue = Math.max(1, ...values, persistentPeakValue) * 1.1;
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
  const drawHorizontalLine = (value, strokeStyle, width, alpha = 1, dashed = true) => {
    const numeric = Number(value || 0);
    if (!Number.isFinite(numeric) || numeric <= 0) return;
    const y = h - (numeric / maxValue) * chartHeight - chartBottomPad;
    ctx.save();
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = width * dpr;
    ctx.globalAlpha = alpha;
    if (dashed) ctx.setLineDash([5 * dpr, 4 * dpr]);
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
    ctx.restore();
  };
  if (options.showPeakLine)
    drawHorizontalLine(
      peakValue,
      options.peakColor || "#b7c0cc",
      1.2,
      0.65,
      true,
    );
  drawSeries(values, color, 2.2, 1);
}
function drawGpuSeries(id, series, index, key, label, color, options = {}) {
  draw(
    id,
    series.map((point) => {
      const gpu = (point.gpus || []).find((item) => String(item.index) === String(index));
      return { [key]: gpu ? Number(gpu[key] || 0) : 0 };
    }),
    key,
    label,
    color,
    options,
  );
}
function isBenchmarkMetricSample(metrics = {}) {
  const lastPath = String(metrics?.last_path || "");
  return !!metrics?.benchmark_active || lastPath.startsWith("benchmark:");
}
function currentStatusMetricPoint(status = {}) {
  const gpus = (status.gpus || [])
    .filter((gpu) => gpu && !gpu.error)
    .map((gpu) => ({
      index: gpu.index,
      util: Number(gpu.util_pct || 0),
      util_pct: Number(gpu.util_pct || 0),
      mem_pct: Number(gpu.mem_pct || 0),
      mem_used_mib: Number(gpu.mem_used_mib || 0),
      mem_total_mib: Number(gpu.mem_total_mib || 0),
      mem_used_gib: Number(gpu.mem_used_mib || 0) / 1024,
      mem_total_gib: Number(gpu.mem_total_mib || 0) / 1024,
      temp: Number(gpu.temp_c || 0),
      temp_c: Number(gpu.temp_c || 0),
      temp_junction: Number(gpu.temp_junction_c || 0),
      temp_junction_c: Number(gpu.temp_junction_c || 0),
      temp_vram: Number(gpu.temp_vram_c || 0),
      temp_vram_c: Number(gpu.temp_vram_c || 0),
      power: Number(gpu.power_w || 0),
      power_w: Number(gpu.power_w || 0),
      fan: Number(gpu.fan_pct || 0),
      fan_pct: Number(gpu.fan_pct || 0),
    }));
  const average = (key) =>
    gpus.length
      ? gpus.reduce((total, gpu) => total + Number(gpu[key] || 0), 0) / gpus.length
      : 0;
  const maximum = (key) =>
    gpus.length ? Math.max(...gpus.map((gpu) => Number(gpu[key] || 0))) : 0;
  const metrics = status.metrics || {};
  const memory = status.system?.memory || {};
  const cpu = status.system?.cpu || {};
  const network = status.system?.network || {};
  const rxMbps =
    network.rx_mbps !== undefined ? Number(network.rx_mbps || 0) : Number(network.rx_kbps || 0) / 1000;
  const txMbps =
    network.tx_mbps !== undefined ? Number(network.tx_mbps || 0) : Number(network.tx_kbps || 0) / 1000;
  const ramPct = Number(memory.used_pct || 0);
  const ramUsedGib = Number(memory.used_mib || 0) / 1024;
  const ramTotalGib = Number(memory.total_mib || 0) / 1024;
  const vramUsedGib = gpus.reduce((total, gpu) => total + Number(gpu.mem_used_gib || 0), 0);
  const vramTotalGib = gpus.reduce((total, gpu) => total + Number(gpu.mem_total_gib || 0), 0);
  const cpuPct = Number(cpu.total_pct || 0);
  const gpuUtil = average("util");
  const benchmarkMetricSample = isBenchmarkMetricSample(metrics);
  return {
    t: Math.floor(Date.now() / 1000),
    gpu_util: Number(gpuUtil.toFixed(1)),
    mem_pct: Number(average("mem_pct").toFixed(1)),
    mem_used_gib: Number.isFinite(vramUsedGib) ? Number(vramUsedGib.toFixed(3)) : 0,
    mem_total_gib: Number.isFinite(vramTotalGib) ? Number(vramTotalGib.toFixed(3)) : 0,
    temp_c: Number(maximum("temp").toFixed(1)),
    power_w: Number(gpus.reduce((total, gpu) => total + Number(gpu.power || 0), 0).toFixed(1)),
    ram_pct: ramPct,
    ram_used_gib: Number.isFinite(ramUsedGib) ? Number(ramUsedGib.toFixed(3)) : 0,
    ram_total_gib: Number.isFinite(ramTotalGib) ? Number(ramTotalGib.toFixed(3)) : 0,
    cpu_pct: cpuPct,
    system_util_pct: Number(((cpuPct + ramPct + gpuUtil) / 3).toFixed(1)),
    net_rx_mbps: Number(rxMbps.toFixed(2)),
    net_tx_mbps: Number(txMbps.toFixed(2)),
    active_requests: metrics.active_requests || 0,
    latency_s: benchmarkMetricSample ? 0 : metrics.last_latency_s || 0,
    ttft_s: benchmarkMetricSample ? 0 : metrics.last_ttft_s || 0,
    tps: benchmarkMetricSample ? 0 : metrics.last_tokens_per_second || 0,
    gpus,
  };
}
function renderMetrics(j, options = {}) {
  const currentPoint = currentStatusMetricPoint(j);
  const s = (j.series && j.series.length) ? [...j.series, currentPoint] : [currentPoint];
  const systemMemory = j.system?.memory || {};
  const currentRamUsedGib = Number(currentPoint.ram_used_gib || Number(systemMemory.used_mib || 0) / 1024 || 0);
  const currentRamTotalGib = Number(currentPoint.ram_total_gib || Number(systemMemory.total_mib || 0) / 1024 || 0);
  const currentVramUsedGib = Number(currentPoint.mem_used_gib || 0);
  const currentVramTotalGib = Number(currentPoint.mem_total_gib || 0);
  const seriesVramPeakGib = Math.max(
    seriesPeakValue(s, "mem_used_gib"),
    currentVramUsedGib,
  );
  const persistentVramPeakGib = persistentMetricPeakValue(j, "mem_used_gib");
  const safeVramPeakGib = Math.max(
    persistentVramPeakGib,
    seriesVramPeakGib,
    currentVramTotalGib > 0 ? (persistentMetricPeakValue(j, "mem_pct") / 100) * currentVramTotalGib : 0,
  );
  const seriesRamPeakGib = Math.max(
    seriesPeakValue(s, "ram_used_gib"),
    currentRamUsedGib,
  );
  const persistentRamPeakGib = persistentMetricPeakValue(j, "ram_used_gib");
  const safeRamPeakGib = Math.max(
    persistentRamPeakGib,
    seriesRamPeakGib,
    currentRamTotalGib > 0 ? (persistentMetricPeakValue(j, "ram_pct") / 100) * currentRamTotalGib : 0,
  );
  draw("cGpu", s, "gpu_util", "GPU util %", "#72c7ff", {
    showPeakLine: true,
    showPeakValue: true,
    peakColor: "#b7c0cc",
    persistentPeakValue: persistentMetricPeakValue(j, "gpu_util"),
  });
  draw("cMem", s, "mem_pct", "VRAM % / GB", "#2fc46b", {
    showPeakLine: true,
    showPeakValue: true,
    peakColor: "#b7c0cc",
    persistentPeakValue: persistentMetricPeakValue(j, "mem_pct"),
    valueFormatter: (current, peak) =>
      `${formatChartValue(current)}% · ${formatChartValue(currentVramUsedGib, 2)} GB (${UI_ARROW_UP} ${formatChartValue(safeVramPeakGib, 2)} GB)`,
  });
  draw("cLatency", s, "latency_s", "Latency s", "#ffcb6b", {
    showPeakLine: true,
    showPeakValue: true,
    peakColor: "#b7c0cc",
    persistentPeakValue: persistentMetricPeakValue(j, "latency_s"),
  });
  draw("cTps", s, "tps", "TPS est", "#ff5b6c", {
    showPeakValue: true,
    showPeakLine: true,
    peakColor: "#b7c0cc",
    persistentPeakValue: persistentMetricPeakValue(j, "tps"),
    valueFormatter: (current, peak) =>
      `${formatChartValue(current, 2)} (↑ ${formatChartValue(peak, 2)})`,
  });
  draw("cRam", s, "ram_pct", "System RAM % / GB", "#2fc46b", {
    showPeakLine: true,
    showPeakValue: true,
    peakColor: "#b7c0cc",
    persistentPeakValue: persistentMetricPeakValue(j, "ram_pct"),
    valueFormatter: (current, peak) =>
      `${formatChartValue(current)}% · ${formatChartValue(currentRamUsedGib, 2)} GB (${UI_ARROW_UP} ${formatChartValue(safeRamPeakGib, 2)} GB)`,
  });
  draw("cCpu", s, "cpu_pct", "CPU total %", "#72c7ff", {
    showPeakLine: true,
    showPeakValue: true,
    peakColor: "#b7c0cc",
    persistentPeakValue: persistentMetricPeakValue(j, "cpu_pct"),
  });
  draw("cSystemUtil", s, "system_util_pct", "System utilization %", "#a78bfa", {
    showPeakLine: true,
    showPeakValue: true,
    peakColor: "#b7c0cc",
    persistentPeakValue: persistentMetricPeakValue(j, "system_util_pct"),
  });
  draw("cNetDown", s, "net_rx_mbps", "Download Mbps", "#2fc46b", {
    showPeakLine: true,
    showPeakValue: true,
    peakColor: "#b7c0cc",
    persistentPeakValue: persistentMetricPeakValue(j, "net_rx_mbps"),
    valueFormatter: (current, peak) =>
      `${formatChartValue(current, 2)} (${UI_ARROW_UP} ${formatChartValue(peak, 2)})`,
  });
  draw("cNetUp", s, "net_tx_mbps", "Upload Mbps", "#72c7ff", {
    showPeakLine: true,
    showPeakValue: true,
    peakColor: "#b7c0cc",
    persistentPeakValue: persistentMetricPeakValue(j, "net_tx_mbps"),
    valueFormatter: (current, peak) =>
      `${formatChartValue(current, 2)} (${UI_ARROW_UP} ${formatChartValue(peak, 2)})`,
  });
  if (metricsElement("ramInfo"))
    metricsElement("ramInfo").textContent =
      j.system && j.system.memory
        ? `Total RAM Used: ${mibToGiB(j.system.memory.used_mib)} GB (${UI_ARROW_UP}${formatChartValue(safeRamPeakGib, 2)} GB) / ${mibToGiB(j.system.memory.total_mib)} GB (${j.system.memory.used_pct}%)`
        : "";
  const cores = (j.system && j.system.cpu && j.system.cpu.cores) || [];
  if (metricsElement("cpuCores"))
    metricsElement("cpuCores").innerHTML = cores
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
    const devicePath = String(d.path || d.source || "");
    const protectedMount = ["/", "/boot", "/boot/efi", "/efi", "/var", "/usr", "/home"].includes(String(d.mount || "").trim());
    const canMount = String(d.type || "").trim() !== "disk" && !!devicePath && !protectedMount;
    const folderButton = d.mounted
      ? `<button class="iconbtn storage-card-iconbtn" title="Open folder browser" aria-label="Open folder browser" onclick="openStorageBrowserForVolume('${escapeJs(devicePath)}','${escapeJs(d.mount || "/")}','${escapeJs(title)}')">${svgIcon("folder")}</button>`
      : "";
    const mountButton = canMount
      ? `<button class="iconbtn storage-card-iconbtn ${d.mounted ? "amber" : "green"}" title="${d.mounted ? "Unmount volume" : "Mount volume"}" aria-label="${d.mounted ? "Unmount volume" : "Mount volume"}" onclick="toggleStorageMount('${escapeJs(devicePath)}','${escapeJs(d.mount || "")}', ${d.mounted ? "true" : "false"})">${d.mounted ? svgIcon("unmount") : svgIcon("mount")}</button>`
      : "";
    const actionRow = folderButton || mountButton
      ? `<div class="storage-card-actions">${folderButton}${mountButton}</div>`
      : "";
    return `<div class="${cls}"><div class="storage-card-head"><div class="storage-title">${title}</div>${actionRow}</div><div class="storage-meta">${meta}</div><div class="storage-sizes"><div class="stat"><div class="label">Free</div><div class="value">${free}</div></div><div class="stat"><div class="label">Used</div><div class="value">${used}</div></div><div class="stat"><div class="label">Total</div><div class="value">${total}</div></div></div><div class="diskbar"><span style="width:${pct}%"></span></div><div class="label">${pctLabel}</div></div>`;
  }
  if (metricsElement("diskInfo")) {
    const physical = disks.filter(
      (d) => d.kind === "disk" || d.type === "disk",
    );
    const rootBackedPaths = new Set(
      disks
        .filter((d) => !(d.kind === "disk" || d.type === "disk"))
        .filter((d) => String(d?.mount || "").trim() === "/" || d?.root_volume)
        .map((d) => String(d?.path || d?.source || "").trim())
        .filter(Boolean),
    );
    const volumes = disks
      .filter((d) => !(d.kind === "disk" || d.type === "disk"))
      .filter((d) => {
        const devicePath = String(d?.path || d?.source || "").trim();
        const mountPath = String(d?.mount || "").trim();
        if (!devicePath || !rootBackedPaths.has(devicePath)) return true;
        return mountPath === "/" || !!d?.root_volume;
      })
      .sort((a, b) => {
        const aRoot = String(a?.mount || "").trim() === "/" || a?.root_volume;
        const bRoot = String(b?.mount || "").trim() === "/" || b?.root_volume;
        if (aRoot !== bRoot) return aRoot ? -1 : 1;
        return String(a?.path || a?.name || "").localeCompare(String(b?.path || b?.name || ""));
      });
    metricsElement("diskInfo").innerHTML =
      `<div class="storage-section"><div class="panel"><h2>Disks</h2><div class="storage-list">${physical.map(storageCard).join("") || '<div class="value">No physical disks found</div>'}</div></div><div class="panel"><h2>Volumes</h2><div class="storage-list">${volumes.map(storageCard).join("") || '<div class="value">No volumes found</div>'}</div><div id="storageVolumesStatus" class="storage-volumes-status">${escapeHtml(storageVolumesStatusText)}</div></div></div>`;
  }
  const net = (j.system && j.system.network) || {};
  const netDownCurrent = Number(
    net.rx_mbps !== undefined ? net.rx_mbps : Number(net.rx_kbps || 0) / 1000,
  );
  const netUpCurrent = Number(
    net.tx_mbps !== undefined ? net.tx_mbps : Number(net.tx_kbps || 0) / 1000,
  );
  const safeNetDownPeak = Math.max(
    persistentMetricPeakValue(j, "net_rx_mbps"),
    seriesPeakValue(s, "net_rx_mbps"),
    seriesPeakValue(s, "net_rx_kbps") / 1000,
  );
  const safeNetUpPeak = Math.max(
    persistentMetricPeakValue(j, "net_tx_mbps"),
    seriesPeakValue(s, "net_tx_mbps"),
    seriesPeakValue(s, "net_tx_kbps") / 1000,
  );
  if (metricsElement("netInfo"))
    metricsElement("netInfo").innerHTML =
      `<div class="stat"><div class="label">Local IP</div><div class="value">${net.local_ip || "unknown"}</div></div>${net.magic_dns ? `<div class="stat"><div class="label">Tailscale MagicDNS</div><div class="value">${escapeHtml(net.magic_dns)}</div></div>` : ""}<div class="stat"><div class="label">Internet IP</div><div class="value">${net.public_ip || "unknown"}</div></div><div class="stat"><div class="label">Download (${UI_ARROW_UP} max)</div><div class="value">${formatMbpsValue(netDownCurrent)} (${UI_ARROW_UP} ${formatMbpsValue(safeNetDownPeak)} max)</div></div><div class="stat"><div class="label">Upload (${UI_ARROW_UP} max)</div><div class="value">${formatMbpsValue(netUpCurrent)} (${UI_ARROW_UP} ${formatMbpsValue(safeNetUpPeak)} max)</div></div>`;
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
  if (metricsElement("systemInfo"))
    metricsElement("systemInfo").innerHTML =
      `OS: ${info.os || "unknown"}<br>Kernel: ${info.kernel || "unknown"}<br>Host: ${info.hostname || "unknown"}<br>User: ${info.username || "unknown"}<br>Machine: ${info.machine || "unknown"}<br>${cpuPackageText}<br>GPUs: ${info.gpus || "unknown"}<br>${memorySummary}<br>${vramSummary}<br>Board/Product: ${info.board || "-"} / ${info.product || "-"}<br>BIOS: ${info.bios || "-"}`;
  const holder = metricsElement("gpuMetricCharts");
  if (holder && j.gpus) {
    const hasGpuMetric = (key) =>
      (j.gpus || []).some((gpu) => Number(gpu?.[key] || 0) > 0) ||
      s.some((point) =>
        (point.gpus || []).some((gpu) => Number(gpu?.[key] || 0) > 0),
      );
    const cats = [
      {
        key: "util",
        suffix: "Util",
        label: "util %",
        color: "#72c7ff",
        showPeakLine: true,
        peakColor: "#b7c0cc",
        showPeakValue: true,
      },
      {
        key: "mem_pct",
        suffix: "Mem",
        label: "VRAM % / GB",
        color: "#2fc46b",
        showPeakLine: true,
        peakColor: "#b7c0cc",
        showPeakValue: true,
      },
      {
        key: "temp",
        suffix: "Temp",
        label: "core °C",
        color: "#ffde59",
        showPeakLine: true,
        peakColor: "#b7c0cc",
        showPeakValue: true,
        valueColor: (current) => tempColorForValue(current, "core"),
        valueFormatterParts: (current, peak) => [
          { text: `${formatChartValue(current, 1)}°C`, color: tempColorForValue(current, "core") },
          { text: " " },
          { text: `(↑ ${formatChartValue(peak, 1)}°C)`, color: tempColorForValue(peak, "core") },
        ],
      },
      ...(hasGpuMetric("temp_junction_c") || hasGpuMetric("temp_junction")
        ? [
            {
              key: "temp_junction",
              suffix: "JunctionTemp",
              label: "junction °C",
              color: "#f59e0b",
              showPeakLine: true,
              peakColor: "#b7c0cc",
              showPeakValue: true,
              valueColor: (current) => tempColorForValue(current, "junction"),
              valueFormatterParts: (current, peak) => [
                { text: `${formatChartValue(current, 1)}°C`, color: tempColorForValue(current, "junction") },
                { text: " " },
                { text: `(↑ ${formatChartValue(peak, 1)}°C)`, color: tempColorForValue(peak, "junction") },
              ],
            },
          ]
        : []),
      ...(hasGpuMetric("temp_vram_c") || hasGpuMetric("temp_vram")
        ? [
            {
              key: "temp_vram",
              suffix: "VramTemp",
              label: "VRAM °C",
              color: "#fb7185",
              showPeakLine: true,
              peakColor: "#b7c0cc",
              showPeakValue: true,
              valueColor: (current) => tempColorForValue(current, "vram"),
              valueFormatterParts: (current, peak) => [
                { text: `${formatChartValue(current, 1)}°C`, color: tempColorForValue(current, "vram") },
                { text: " " },
                { text: `(↑ ${formatChartValue(peak, 1)}°C)`, color: tempColorForValue(peak, "vram") },
              ],
            },
          ]
        : []),
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
        const optionsForGpu = { ...cat };
        if (cat.key === "mem_pct") {
          const currentGpuPoint = (currentPoint.gpus || []).find((item) => String(item.index) === String(g.index)) || {};
          const currentGpuUsedGib = Number(currentGpuPoint.mem_used_gib || Number(g.mem_used_mib || 0) / 1024 || 0);
          const currentGpuTotalGib = Number(currentGpuPoint.mem_total_gib || Number(g.mem_total_mib || 0) / 1024 || 0);
          optionsForGpu.valueFormatter = (current, peak) =>
            `${formatChartValue(current)}% · ${formatChartValue(currentGpuUsedGib, 2)} GB (${UI_ARROW_UP} ${formatChartValue(currentGpuTotalGib > 0 ? (Number(peak || 0) / 100) * currentGpuTotalGib : currentGpuUsedGib, 2)} GB)`;
        }
        drawGpuSeries(
          `cGpu${g.index}${cat.suffix}`,
          s,
          g.index,
          cat.key,
          label,
          color,
          {
            ...optionsForGpu,
            persistentPeakValue: persistentGpuMetricPeakValue(j, g.index, cat.key),
          },
        );
      }),
    );
  }
  if (!options.skipPopups) syncAllDetachedMetricsPopups(j);
}
