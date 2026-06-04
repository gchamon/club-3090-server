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
function cumulativePeak(values = []) {
  let peak = 0;
  return values.map((value) => {
    peak = Math.max(peak, Number(value || 0));
    return peak;
  });
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
    signature: `metrics:${paneId}`,
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
const storageBrowserState = {
  rootPath: "",
  relativePath: "",
  currentPath: "",
  entries: [],
  selected: new Set(),
  devicePath: "",
  title: "",
  openFiles: [],
  activeFilePath: "",
  wrapText: false,
  previewMode: false,
  sizePollTimer: null,
};
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
function storageBrowserSetMsg(text = "", tone = "warning") {
  setElementMsg("storageBrowserMsg", text || "", tone);
}
function ensureStorageBrowserModal() {
  if ($("storageBrowserModal")) return;
  const modal = document.createElement("div");
  modal.id = "storageBrowserModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card storage-browser-modal-card" role="dialog" aria-modal="true" aria-labelledby="storageBrowserTitle"><div class="panel-head"><h2 id="storageBrowserTitle">Storage Browser</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeStorageBrowserModal()">✕</button></div><div class="storage-browser-toolbar"><div class="storage-browser-toolbar-left">${storageBrowserToolbarButton("refreshStorageBrowser()", "reset", "Refresh", "storage-browser-tool")}${storageBrowserToolbarSeparator()}${storageBrowserToolbarButton("downloadStorageBrowserSelection()", "download", "Download", "storage-browser-tool")}${storageBrowserToolbarButton("openStorageBrowserUploadPicker()", "upload", "Upload", "storage-browser-tool")}${storageBrowserToolbarSeparator()}${storageBrowserToolbarButton("openSelectedStorageBrowserFiles()", "edit", "Open selected file(s)", "storage-browser-tool")}${storageBrowserToolbarButton("deleteStorageBrowserSelection()", "delete", "Delete", "storage-browser-tool danger")}${storageBrowserToolbarSeparator()}${storageBrowserToolbarButton("promptCreateStorageBrowserFolder()", "folder", "New folder", "storage-browser-tool")}${storageBrowserToolbarButton("promptCreateStorageBrowserFile()", "file", "New text file", "storage-browser-tool")}</div><div class="storage-browser-paths"><div class="storage-browser-path"><strong>Volume:</strong> <code id="storageBrowserRootPath"></code></div><div class="storage-browser-path"><strong>Folder:</strong> <code id="storageBrowserCurrentPath"></code></div></div></div><input id="storageBrowserUploadInput" type="file" multiple class="hidden" onchange="handleStorageBrowserUpload(event)" /><div class="storage-browser-table-wrap"><table class="storage-browser-table"><colgroup><col class="storage-browser-col-select" /><col class="storage-browser-col-name" /><col class="storage-browser-col-size" /><col class="storage-browser-col-type" /><col class="storage-browser-col-owner" /><col class="storage-browser-col-perms" /><col class="storage-browser-col-attrs" /><col class="storage-browser-col-modified" /></colgroup><thead><tr><th></th><th>Name</th><th>Size</th><th>Type</th><th>Owner</th><th>Permissions</th><th>Attributes</th><th>Modified</th></tr></thead><tbody id="storageBrowserTableBody"></tbody></table></div><div class="msg" id="storageBrowserMsg"></div></div>`;
  document.body.appendChild(modal);
}
function closeStorageBrowserModal() {
  ensureStorageBrowserModal();
  $("storageBrowserModal").classList.add("hidden");
  if (storageBrowserState.sizePollTimer) {
    clearTimeout(storageBrowserState.sizePollTimer);
    storageBrowserState.sizePollTimer = null;
  }
  storageBrowserState.selected.clear();
  storageBrowserState.openFiles = [];
  storageBrowserState.activeFilePath = "";
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
  storageBrowserState.selected = new Set();
  if (storageBrowserState.sizePollTimer) {
    clearTimeout(storageBrowserState.sizePollTimer);
    storageBrowserState.sizePollTimer = null;
  }
  renderStorageBrowser();
  $("storageBrowserModal")?.classList.remove("hidden");
}
function scheduleStorageBrowserSizeRefresh() {
  if (!storageBrowserState.entries.some((entry) => entry?.size_pending)) return;
  if (storageBrowserState.sizePollTimer) return;
  const rootPath = storageBrowserState.rootPath;
  const relativePath = storageBrowserState.relativePath;
  const title = storageBrowserState.title;
  const devicePath = storageBrowserState.devicePath;
  storageBrowserState.sizePollTimer = setTimeout(() => {
    storageBrowserState.sizePollTimer = null;
    if ($("storageBrowserModal")?.classList.contains("hidden")) return;
    if (rootPath !== storageBrowserState.rootPath || relativePath !== storageBrowserState.relativePath) return;
    loadStorageBrowser(rootPath, relativePath, title, devicePath).catch((error) => {
      storageBrowserSetMsg(messageText(error), "error");
    });
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
function renderStorageBrowser() {
  ensureStorageBrowserModal();
  $("storageBrowserTitle").textContent = storageBrowserState.title || "Storage Browser";
  $("storageBrowserRootPath").textContent = storageBrowserState.rootPath || "-";
  $("storageBrowserCurrentPath").textContent = storageBrowserState.currentPath || storageBrowserState.rootPath || "-";
  const body = $("storageBrowserTableBody");
  if (!body) return;
  if (!storageBrowserState.entries.length) {
    body.innerHTML = '<tr><td colspan="8" class="storage-browser-empty">This folder is empty.</td></tr>';
    return;
  }
  body.innerHTML = storageBrowserState.entries
    .map((entry, index) => {
      const rel = String(entry?.relative_path || "");
      const selected = storageBrowserState.selected.has(rel);
      const isFolder = String(entry?.type || "") === "folder";
      const rowAction = isFolder
        ? `openStorageBrowserEntry('${escapeJs(rel)}')`
        : `openStorageBrowserFile('${escapeJs(rel)}')`;
      const displayName = entry?.name === ".." ? "Previous folder" : String(entry?.name || `entry-${index + 1}`);
      if (entry?.name === "..") {
        return `<tr class="storage-browser-parent-row"><td></td><td><button type="button" class="storage-browser-name is-folder storage-browser-parent-link" onclick="${rowAction}"><span class="storage-browser-back-icon">${svgIcon("folder-up")}</span><span class="storage-browser-name-label" title="Previous folder">Previous folder</span></button></td><td colspan="6"></td></tr>`;
      }
      const nameHtml =
        `<button type="button" class="${isFolder ? "storage-browser-name is-folder" : "storage-browser-name is-file"}" onclick="${rowAction}"><span class="storage-browser-entry-icon">${storageBrowserEntryIcon(entry)}</span><span class="storage-browser-name-label" title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</span></button>`;
      return `<tr class="${selected ? "selected" : ""}"><td><input type="checkbox" ${selected ? "checked" : ""} onchange="toggleStorageBrowserSelection('${escapeJs(rel)}', this.checked)" /></td><td class="storage-browser-name-cell">${nameHtml}</td><td>${storageBrowserSizeHtml(entry)}</td><td>${escapeHtml(entry?.type || "")}</td><td>${escapeHtml(entry?.owner || "")}</td><td>${escapeHtml(entry?.permissions || "")}</td><td>${escapeHtml(entry?.attributes || "")}</td><td>${escapeHtml(storageBrowserFormatTimestamp(entry?.modified_at))}</td></tr>`;
    })
    .join("");
  scheduleStorageBrowserSizeRefresh();
}
function openStorageBrowserForVolume(devicePath, rootPath, title) {
  loadStorageBrowser(rootPath, "", title, devicePath).catch((error) => {
    alert(messageText(error));
  });
}
function openStorageBrowserEntry(relativePath) {
  loadStorageBrowser(
    storageBrowserState.rootPath,
    relativePath,
    storageBrowserState.title,
    storageBrowserState.devicePath,
  ).catch((error) => {
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
  loadStorageBrowser(
    storageBrowserState.rootPath,
    storageBrowserState.relativePath,
    storageBrowserState.title,
    storageBrowserState.devicePath,
  ).catch((error) => {
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
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    storageBrowserSetMsg("Download prepared.", "success");
  } catch (error) {
    storageBrowserSetMsg(messageText(error), "error");
  }
}
async function deleteStorageBrowserSelection() {
  const entries = storageBrowserSelectedEntries();
  if (!entries.length) {
    storageBrowserSetMsg("Select at least one file or folder first.", "warning");
    return;
  }
  if (!(await openClubConfirmModal(`Delete ${entries.length} selected file${entries.length === 1 ? "" : "s"} from this volume?`))) {
    return;
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
    refreshStorageBrowser();
  } catch (error) {
    storageBrowserSetMsg(messageText(error), "error");
  }
}
async function toggleStorageMount(devicePath, rootPath, mounted) {
  try {
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
    await refreshStatus({ force: true });
  } catch (error) {
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
  const name = window.prompt("Folder name", "");
  if (!name) return;
  try {
    await storageBrowserPost("create_folder", {
      root_path: storageBrowserState.rootPath,
      relative_path: storageBrowserState.relativePath,
      name,
    });
    refreshStorageBrowser();
  } catch (error) {
    storageBrowserSetMsg(messageText(error), "error");
  }
}
async function promptCreateStorageBrowserFile() {
  const name = window.prompt("Text file name", "notes.txt");
  if (!name) return;
  try {
    const payload = await storageBrowserPost("create_file", {
      root_path: storageBrowserState.rootPath,
      relative_path: storageBrowserState.relativePath,
      name,
    });
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
    original_text: String(fileRow?.text || ""),
    original_hex_text: String(fileRow?.hex_text || storageEditorHexTextFromRows(fileRow?.hex_rows || [])),
    hex_text: String(fileRow?.hex_text || storageEditorHexTextFromRows(fileRow?.hex_rows || [])),
  };
  const next = storageBrowserState.openFiles.filter((row) => String(row?.relative_path || "") !== path);
  next.push(prepared);
  storageBrowserState.openFiles = next;
  storageBrowserState.activeFilePath = path;
}
async function openStorageBrowserFile(relativePath) {
  try {
    const payload = await storageBrowserPost("read_file", {
      root_path: storageBrowserState.rootPath,
      relative_path: relativePath,
    });
    upsertStorageBrowserOpenFile(payload || {});
    openStorageEditorModal();
  } catch (error) {
    storageBrowserSetMsg(messageText(error), "error");
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
  const modal = document.createElement("div");
  modal.id = "storageEditorModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card storage-editor-modal-card" role="dialog" aria-modal="true" aria-labelledby="storageEditorTitle"><div class="panel-head"><h2 id="storageEditorTitle">File Editor</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeStorageEditorModal()">✕</button></div><div id="storageEditorTabs" class="storage-editor-tabs"></div><div id="storageEditorToolbar" class="storage-editor-toolbar"></div><div id="storageEditorBody" class="storage-editor-body"></div><div class="msg" id="storageEditorMsg"></div></div>`;
  document.body.appendChild(modal);
}
function closeStorageEditorModal() {
  ensureStorageEditorModal();
  $("storageEditorModal").classList.add("hidden");
}
function openStorageEditorModal() {
  renderStorageEditorModal();
}
function activeStorageEditorFile() {
  return storageBrowserState.openFiles.find((row) => String(row?.relative_path || "") === String(storageBrowserState.activeFilePath || "")) || storageBrowserState.openFiles[storageBrowserState.openFiles.length - 1] || null;
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
  const lang = storageEditorLanguageTag(file);
  if (lang === "markdown" && typeof cachedMarkdownToHtml === "function") {
    return cachedMarkdownToHtml(text || "");
  }
  if (typeof highlightMarkdownCode === "function") {
    return `<pre class="chat-code storage-editor-preview-code"><div class="chat-code-lang">${escapeHtml(lang || "text")}</div><code>${highlightMarkdownCode(text || "", lang)}</code></pre>`;
  }
  return `<pre class="storage-editor-plain-preview">${escapeHtml(text || "")}</pre>`;
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
  try {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    const computed = probe && window.getComputedStyle ? window.getComputedStyle(probe) : null;
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
  const card = document.querySelector(".storage-editor-modal-card");
  const available = Math.max(
    0,
    Number(body?.clientWidth || 0),
    Number(card?.clientWidth || 0) - 32,
    Number(window.innerWidth || 0) - 96,
  );
  const availableCh = available / storageEditorHexColumnWidthPx();
  const rawBytes = Math.floor((availableCh - 15) / 4);
  const roundedBytes = Math.floor(rawBytes / 8) * 8;
  return Math.max(16, Math.min(96, roundedBytes || 16));
}
function storageEditorHexCurrentBytesPerRow() {
  const value = Number(document.querySelector(".storage-editor-hex-editor")?.dataset?.bytesPerRow || storageEditorHexBytesPerRowValue || 16);
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
  const previewButton = file.is_text
    ? `<button class="iconbtn storage-editor-tool" title="${storageBrowserState.previewMode ? "Return to edit mode" : "Preview rendered output"}" aria-label="${storageBrowserState.previewMode ? "Return to edit mode" : "Preview rendered output"}" onclick="toggleStorageEditorPreview()">${svgIcon(storageBrowserState.previewMode ? "hide" : "preview")}</button>`
    : "";
  toolbar.innerHTML = `${renderIconButton({ title: "Copy", action: "storageEditorCopy()", icon: "copy", className: "storage-editor-tool" })}${renderIconButton({ title: "Cut", action: "storageEditorCut()", icon: "cut", className: "storage-editor-tool" })}${renderIconButton({ title: "Paste", action: "storageEditorPaste()", icon: "paste", className: "storage-editor-tool" })}<span class="storage-editor-toolbar-separator" aria-hidden="true"></span>${renderIconButton({ title: "Undo", action: "storageEditorUndo()", icon: "undo", className: "storage-editor-tool" })}${renderIconButton({ title: "Redo", action: "storageEditorRedo()", icon: "redo", className: "storage-editor-tool" })}<span class="storage-editor-toolbar-separator" aria-hidden="true"></span>${renderIconButton({ title: "Toggle word wrap", action: "toggleStorageEditorWrap()", icon: "wrap", className: "storage-editor-tool" })}${previewButton}<span class="storage-editor-toolbar-separator${file.is_text ? "" : " hidden"}" aria-hidden="true"></span>${renderIconButton({ title: "Discard changes", action: "discardActiveStorageEditorChanges()", icon: "delete", className: "storage-editor-tool" })}${renderIconButton({ title: "Save", action: "saveActiveStorageEditorFile()", icon: "save", className: "storage-editor-tool" })}`;
}
function renderStorageEditorModal() {
  ensureStorageEditorModal();
  const tabs = $("storageEditorTabs");
  const body = $("storageEditorBody");
  const files = storageBrowserState.openFiles || [];
  if (!files.length) return;
  tabs.innerHTML = files.map((file) => `<button class="subtab ${String(file?.relative_path || "") === String(storageBrowserState.activeFilePath || "") ? "active" : ""}" onclick="activateStorageEditorTab('${escapeJs(file.relative_path || "")}')">${escapeHtml(file.name || file.relative_path || "file")}</button>`).join("");
  const file = activeStorageEditorFile();
  if (!file) return;
  renderStorageEditorToolbar(file);
  if (file.is_text) {
    const text = String(file.text || "");
    const lineCount = Math.max(1, text.split("\n").length);
    body.innerHTML = storageBrowserState.previewMode
      ? `<div class="storage-editor-preview-only"><div class="storage-editor-preview-head">Preview</div><div class="chat-message-markdown storage-editor-preview-body">${storageEditorPreviewHtml(file, text)}</div></div>`
      : `<div class="storage-editor-text-shell"><div id="storageEditorLineNumbers" class="storage-editor-line-numbers">${Array.from({ length: lineCount }, (_, index) => `<span>${index + 1}</span>`).join("")}</div><textarea id="storageEditorTextarea" class="storage-editor-textarea${storageBrowserState.wrapText ? " wrap" : ""}" spellcheck="false" oninput="syncStorageEditorLineNumbers()" onscroll="syncStorageEditorLineNumberScroll()">${escapeHtml(text)}</textarea></div>`;
  } else {
    const bytesPerRow = storageEditorHexBytesPerRow();
    storageEditorHexBytesPerRowValue = bytesPerRow;
    const hexText = storageEditorHexText(file);
    file.hex_text = hexText;
    file.hex_rows = storageEditorHexRowsFromText(hexText, bytesPerRow);
    const rows = file.hex_rows || [];
    body.innerHTML = `<div class="storage-editor-hex-wrap"><div class="storage-editor-hex-head">${escapeHtml(file.mime || "binary")} · edit raw bytes below</div><div class="storage-editor-hex-editor${bytesPerRow > 16 ? " is-wide" : ""}" data-bytes-per-row="${bytesPerRow}" style="--storage-editor-ascii-column:${bytesPerRow + 1}ch"><div class="storage-editor-hex-grid-head"><span>Offset</span><span>Hex Bytes</span><span>ASCII</span></div><pre id="storageEditorHexOffsets" class="storage-editor-hex-offsets">${escapeHtml(rows.map((row) => Number(row?.offset || 0).toString(16).padStart(8, "0")).join("\n"))}</pre><textarea id="storageEditorHexTextarea" class="storage-editor-hex-textarea${storageBrowserState.wrapText ? " wrap" : ""}" inputmode="text" spellcheck="false" onbeforeinput="handleStorageEditorHexBeforeInput(event)" oninput="handleStorageEditorHexTextInput(event)" onpaste="handleStorageEditorHexPaste(event)" onscroll="syncStorageEditorHexScroll()">${escapeHtml(storageEditorFormatHexText(hexText, bytesPerRow))}</textarea><pre id="storageEditorHexAscii" class="storage-editor-hex-ascii">${escapeHtml(storageEditorHexColumnText(rows, "ascii"))}</pre></div></div>`;
  }
  $("storageEditorModal").classList.remove("hidden");
  syncStorageEditorLineNumbers();
  syncStorageEditorHexPreview();
}
function activateStorageEditorTab(relativePath) {
  storageBrowserState.activeFilePath = String(relativePath || "");
  storageBrowserState.previewMode = false;
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
    if (file?.is_text && area) {
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
    refreshStorageBrowser();
    renderStorageEditorModal();
  } catch (error) {
    setElementMsg("storageEditorMsg", messageText(error), "error");
  }
}
function storageEditorCopy() {
  const area = $("storageEditorTextarea");
  if (area) {
    area.focus();
    document.execCommand("copy");
    return;
  }
  const hexArea = $("storageEditorHexTextarea");
  if (hexArea) {
    hexArea.focus();
    document.execCommand("copy");
  }
}
function storageEditorCut() {
  const area = $("storageEditorTextarea");
  if (area) {
    area.focus();
    document.execCommand("cut");
    return;
  }
  const hexArea = $("storageEditorHexTextarea");
  if (hexArea) {
    hexArea.focus();
    document.execCommand("cut");
  }
}
async function storageEditorPaste() {
  const area = $("storageEditorTextarea");
  if (area) {
    area.focus();
    document.execCommand("paste");
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
    document.execCommand("undo");
    return;
  }
  const hexArea = $("storageEditorHexTextarea");
  if (hexArea) {
    hexArea.focus();
    document.execCommand("undo");
  }
}
function storageEditorRedo() {
  const area = $("storageEditorTextarea");
  if (area) {
    area.focus();
    document.execCommand("redo");
    return;
  }
  const hexArea = $("storageEditorHexTextarea");
  if (hexArea) {
    hexArea.focus();
    document.execCommand("redo");
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
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>${escapeHtml(state?.title || "Metrics")}</title>
    <style>
      :root { color-scheme: dark; --bg:#0b0f14; --panel:#121923; --line:#273243; --text:#e8eef7; --muted:#9dafc3; --field:#081018; }
      * { box-sizing:border-box; }
      html, body { margin:0; min-height:100%; background:var(--bg); color:var(--text); font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif; overflow:hidden; }
      body { padding:12px; }
      .popup-card { height:calc(100vh - 24px); overflow:auto; background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:12px; }
      .popup-head { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; margin-bottom:10px; }
      .popup-title-row { display:flex; align-items:center; gap:8px; }
      .popup-title { font-size:20px; font-weight:800; margin:0; }
      .popup-meta { color:var(--muted); font-size:12px; line-height:1.35; }
      .popup-actions { display:flex; align-items:center; gap:8px; }
      .popup-btn { display:inline-flex; align-items:center; justify-content:center; width:20px; height:20px; padding:0; border:0; background:transparent; color:var(--muted); cursor:pointer; }
      .popup-btn:hover, .popup-btn:focus-visible { color:#eef4ff; outline:none; }
      .popup-btn svg { width:18px; height:18px; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; fill:none; }
      .subtabs { display:flex; gap:6px; overflow-x:auto; margin-bottom:10px; }
      .subtab { border:1px solid #34445a; background:#1b2635; color:#eef4ff; border-radius:10px; padding:9px 11px; font-size:13px; cursor:pointer; white-space:nowrap; }
      .subtab.active { background:#203149; border-color:#3d6fa3; }
      .metricpane { display:none; }
      .metricpane.active { display:block; }
      .panel { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:12px; box-shadow:0 8px 30px #0004; margin-bottom:10px; }
      .panel h2 { font-size:14px; margin:0 0 10px; }
      .chartgrid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
      .gpu-chartgrid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:10px; }
      .chart { height:145px; background:#081018; border:1px solid #213044; border-radius:12px; padding:8px; }
      .chart.tall { height:220px; }
      canvas { width:100%; height:100%; }
      .value { font-weight:700; font-size:13px; overflow-wrap:anywhere; }
      .smallgap { margin-bottom:5px; }
      .coregrid { display:grid; grid-template-columns:repeat(auto-fill, minmax(90px, 1fr)); gap:6px; }
      .stat { background:#0b1119; border:1px solid #222d3c; border-radius:10px; padding:8px; }
      .label { color:var(--muted); font-size:11px; }
      .storage-list { display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:10px; align-items:start; }
      .storage-section { display:flex; flex-direction:column; gap:10px; }
      .storage-card { background:#0b1119; border:1px solid #243144; border-radius:12px; padding:10px; min-width:0; overflow:hidden; }
      .storage-card.user-facing { background:#10243a; border-color:#2a72a8; }
      .storage-card-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:6px; }
      .storage-title { font-weight:800; color:#d9ecff; overflow-wrap:anywhere; min-width:0; }
      .storage-meta { color:#9dafc3; font-size:12px; margin-bottom:6px; overflow-wrap:anywhere; }
      .storage-sizes { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:6px; margin-bottom:8px; }
      .storage-sizes .stat { padding:6px; min-width:0; }
      .diskbar { height:7px; background:#081018; border-radius:99px; overflow:hidden; margin-top:5px; }
      .diskbar span { display:block; height:100%; background:#2fc46b; }
      .netgrid + .chartgrid { margin-top:10px; }
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
          <div class="popup-meta" id="popupMetricsLabel"></div>
        </div>
        <div class="popup-actions">
          <button class="popup-btn" type="button" id="popupMetricsResetBtn" title="Clear recorded metrics" aria-label="Clear recorded metrics">
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
        document.getElementById("popupMetricsResetBtn")?.addEventListener("click", () => {
          try {
            if (window.opener && !window.opener.closed && typeof window.opener.promptClearRecordedMetrics === "function") {
              window.opener.promptClearRecordedMetrics();
            }
          } catch (e) {}
          notify();
        });
        document.querySelectorAll("[data-metric-pane]")?.forEach((button) => {
          button.addEventListener("click", () => {
            try {
              if (window.opener && !window.opener.closed && typeof window.opener.replaceDetachedMetricsPopupPane === "function") {
                const changed = window.opener.replaceDetachedMetricsPopupPane(signature, String(button.getAttribute("data-metric-pane") || ""));
                if (changed) {
                  window.close();
                  return;
                }
              }
            } catch (e) {}
            notify();
          });
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
  const label = doc.getElementById("popupMetricsLabel");
  if (title && title.textContent !== String(state.title || "Metrics")) title.textContent = String(state.title || "Metrics");
  if (label && label.textContent !== String(state.label || "")) label.textContent = String(state.label || "");
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
  closeDetachedMetricsPopup(signature);
  setActiveMetricPaneInDocument(document, nextPaneId);
  const target = currentMetricsPopupTarget();
  const nextState = popupMetricsState(target.signature);
  nextState.paneId = target.paneId;
  nextState.title = target.title;
  nextState.label = target.label;
  ensureDetachedMetricsPopupWindow(nextState);
  nextState.lastActiveAt = Date.now();
  renderDetachedMetricsPopup(nextState, lastStatus);
  applyMetricsVisibility();
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
  if (section) section.classList.toggle("metrics-card-hidden", isMetrics && detached);
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
  const peaks = options.showPeakLine ? cumulativePeak(values) : [];
  const visiblePeakValue = peaks.length ? peaks[peaks.length - 1] : Math.max(0, ...values);
  const persistentPeakValue = Math.max(0, Number(options.persistentPeakValue || 0));
  const peakValue = Math.max(visiblePeakValue, persistentPeakValue);
  const currentValue = values.length ? values[values.length - 1] : 0;
  const maxValue = Math.max(1, ...values, ...peaks, persistentPeakValue) * 1.1;
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
  if (persistentPeakValue > visiblePeakValue)
    drawHorizontalLine(
      persistentPeakValue,
      options.peakColor || "#b7c0cc",
      1.2,
      0.65,
      true,
    );
  if (peaks.length)
    drawSeries(peaks, options.peakColor || "#b7c0cc", 1.4, 0.9, options.peakDashed !== false);
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
function currentStatusMetricPoint(status = {}) {
  const gpus = (status.gpus || [])
    .filter((gpu) => gpu && !gpu.error)
    .map((gpu) => ({
      index: gpu.index,
      util: Number(gpu.util_pct || 0),
      util_pct: Number(gpu.util_pct || 0),
      mem_pct: Number(gpu.mem_pct || 0),
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
  const cpuPct = Number(cpu.total_pct || 0);
  const gpuUtil = average("util");
  return {
    t: Math.floor(Date.now() / 1000),
    gpu_util: Number(gpuUtil.toFixed(1)),
    mem_pct: Number(average("mem_pct").toFixed(1)),
    temp_c: Number(maximum("temp").toFixed(1)),
    power_w: Number(gpus.reduce((total, gpu) => total + Number(gpu.power || 0), 0).toFixed(1)),
    ram_pct: ramPct,
    cpu_pct: cpuPct,
    system_util_pct: Number(((cpuPct + ramPct + gpuUtil) / 3).toFixed(1)),
    net_rx_mbps: Number(rxMbps.toFixed(2)),
    net_tx_mbps: Number(txMbps.toFixed(2)),
    active_requests: metrics.active_requests || 0,
    latency_s: metrics.last_latency_s || 0,
    ttft_s: metrics.last_ttft_s || 0,
    tps: metrics.last_tokens_per_second || 0,
    gpus,
  };
}
function renderMetrics(j, options = {}) {
  const currentPoint = currentStatusMetricPoint(j);
  const s = (j.series && j.series.length) ? [...j.series, currentPoint] : [currentPoint];
  draw("cGpu", s, "gpu_util", "GPU util %", "#72c7ff", {
    showPeakLine: true,
    showPeakValue: true,
    peakColor: "#b7c0cc",
    persistentPeakValue: persistentMetricPeakValue(j, "gpu_util"),
  });
  draw("cMem", s, "mem_pct", "VRAM %", "#2fc46b", {
    showPeakLine: true,
    showPeakValue: true,
    peakColor: "#b7c0cc",
    persistentPeakValue: persistentMetricPeakValue(j, "mem_pct"),
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
  draw("cRam", s, "ram_pct", "System RAM %", "#2fc46b", {
    showPeakLine: true,
    showPeakValue: true,
    peakColor: "#b7c0cc",
    persistentPeakValue: persistentMetricPeakValue(j, "ram_pct"),
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
        ? `Used ${mibToGiB(j.system.memory.used_mib)} / ${mibToGiB(j.system.memory.total_mib)} GB (${j.system.memory.used_pct}%)`
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
    const volumes = disks
      .filter((d) => !(d.kind === "disk" || d.type === "disk"))
      .sort((a, b) => {
        const aRoot = String(a?.mount || "").trim() === "/" || a?.root_volume;
        const bRoot = String(b?.mount || "").trim() === "/" || b?.root_volume;
        if (aRoot !== bRoot) return aRoot ? -1 : 1;
        return String(a?.path || a?.name || "").localeCompare(String(b?.path || b?.name || ""));
      });
    metricsElement("diskInfo").innerHTML =
      `<div class="storage-section"><div class="panel"><h2>Disks</h2><div class="storage-list">${physical.map(storageCard).join("") || '<div class="value">No physical disks found</div>'}</div></div><div class="panel"><h2>Volumes</h2><div class="storage-list">${volumes.map(storageCard).join("") || '<div class="value">No volumes found</div>'}</div></div></div>`;
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
        label: "VRAM %",
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
        valueColor: (current) => tempColorForValue(current),
        valueFormatterParts: (current, peak) => [
          { text: `${formatChartValue(current, 1)}°C`, color: tempColorForValue(current) },
          { text: " " },
          { text: `(↑ ${formatChartValue(peak, 1)}°C)`, color: tempColorForValue(peak) },
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
              valueColor: (current) => tempColorForValue(current),
              valueFormatterParts: (current, peak) => [
                { text: `${formatChartValue(current, 1)}°C`, color: tempColorForValue(current) },
                { text: " " },
                { text: `(↑ ${formatChartValue(peak, 1)}°C)`, color: tempColorForValue(peak) },
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
              valueColor: (current) => tempColorForValue(current),
              valueFormatterParts: (current, peak) => [
                { text: `${formatChartValue(current, 1)}°C`, color: tempColorForValue(current) },
                { text: " " },
                { text: `(↑ ${formatChartValue(peak, 1)}°C)`, color: tempColorForValue(peak) },
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
        drawGpuSeries(
          `cGpu${g.index}${cat.suffix}`,
          s,
          g.index,
          cat.key,
          label,
          color,
          {
            ...cat,
            persistentPeakValue: persistentGpuMetricPeakValue(j, g.index, cat.key),
          },
        );
      }),
    );
  }
  if (!options.skipPopups) syncAllDetachedMetricsPopups(j);
}
