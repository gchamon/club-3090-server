// Core state and DOM helpers
const searchState = {
  active: false,
  query: "",
  matches: [],
  index: -1,
  prevAutoscroll: true,
};
const currentLocationSearch =
  (typeof window !== "undefined" && window.location && typeof window.location.search === "string"
    ? window.location.search
    : typeof location !== "undefined" && location && typeof location.search === "string"
      ? location.search
      : "");
const urlParams = new URLSearchParams(currentLocationSearch);
const DETACHED_METRICS_MODE = urlParams.get("detached") === "metrics";
const DETACHED_METRICS_INITIAL_PANE = String(urlParams.get("pane") || "").trim();
let lastStatus = null;
let activeTabName = "overview";
let showGlobalLogs = true;
let showGlobalLogSources =
  window.showGlobalLogSources || (window.showGlobalLogSources = Object.create(null));
let currentLogSource = "docker";
const knownLogSources = new Set(["docker", "audit", "debug", "benchmarks"]);
window.logPopupStates = window.logPopupStates || Object.create(null);
var LOG_POPUP_WIDTH = 980;
var LOG_POPUP_HEIGHT = 720;
const DETACHED_LOG_POPUP_CLOSED_POLL_MS = 1000;
let updateMonitor = {
  active: false,
  streamUrl: "",
  statusUrl: "",
  token: "",
  completed: false,
  statusTimer: null,
  startedAt: 0,
  reloadScheduled: false,
  returnTab: "",
  returnScrollTop: 0,
  returnLogSource: "docker",
};
const UPDATE_PENDING_TOKEN_KEY = "club3090-update-pending-token";
const UPDATE_COMPLETED_TOKEN_KEY = "club3090-update-completed-token";
const UPDATE_PENDING_RETURN_KEY = "club3090-update-pending-return";
let updateUiLocked = false;
let updateSignalPollTimer = null;
let updateSignalPollActive = false;
let updateAcknowledgedToken = "";
let lastWindowFocused = typeof document.hasFocus === "function" ? document.hasFocus() : true;
let lastSwitchNotificationKey = "";
let lastBenchmarkNotificationKey = "";
let detachedLogPopupClosedPollTimer = null;
let uiDocumentOverride = null;
let uiWindowOverride = null;
function currentUiDocument() {
  return uiDocumentOverride || document;
}
function currentUiWindow() {
  return uiWindowOverride || currentUiDocument().defaultView || window;
}
function withUiTarget(doc, win, fn) {
  const previousDoc = uiDocumentOverride;
  const previousWin = uiWindowOverride;
  uiDocumentOverride = doc || null;
  uiWindowOverride = win || (doc?.defaultView || null);
  const restore = () => {
    uiDocumentOverride = previousDoc;
    uiWindowOverride = previousWin;
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
function popupLogState(signature) {
  if (!signature) return null;
  if (!window.logPopupStates[signature]) {
    window.logPopupStates[signature] = {
      signature,
      source: "",
      url: "",
      title: "",
      label: "",
      win: null,
      es: null,
      lastActiveAt: 0,
      autoscroll: true,
    };
  }
  return window.logPopupStates[signature];
}
function popupLogWindowOpen(signature = "") {
  if (signature) {
    const state = window.logPopupStates[signature];
    return !!(state?.win && !state.win.closed);
  }
  return Object.values(window.logPopupStates).some((state) => state?.win && !state.win.closed);
}
function popupLogWindowActive(signature = "") {
  const states = signature
    ? [window.logPopupStates[signature]].filter(Boolean)
    : Object.values(window.logPopupStates);
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
function effectiveShowGlobalLogs() {
  return currentLogGlobalEnabled() && !currentLogSourceDetached();
}
function $(id) {
  return currentUiDocument().getElementById(id);
}
function safeInsertBefore(parent, node, reference = null) {
  if (!parent || !node) return;
  const nextReference = reference && reference.parentNode === parent ? reference : null;
  parent.insertBefore(node, nextReference);
}
function setHtmlIfChanged(node, html) {
  if (!node) return false;
  const nextHtml = String(html || "");
  if (node.innerHTML === nextHtml) return false;
  node.innerHTML = nextHtml;
  return true;
}
function setMsg(t) {
  $("msg").textContent = t || "";
}
function updateBannerDismissKey(startedAt, remoteKey = "") {
  return `club3090-update-banner-dismissed:${String(startedAt || "0")}:${String(remoteKey || "")}`;
}
function currentUpdateBannerRemoteKey(status = lastStatus || {}) {
  const remote = status?.remote_update || {};
  return String(remote.commit_sha || remote.script_version || "none").trim() || "none";
}
function readUpdateBannerDismissed(startedAt, remoteKey = "") {
  try {
    return localStorage.getItem(updateBannerDismissKey(startedAt, remoteKey)) === "1";
  } catch (e) {
    return false;
  }
}
function writeUpdateBannerDismissed(startedAt, remoteKey = "") {
  try {
    localStorage.setItem(updateBannerDismissKey(startedAt, remoteKey), "1");
  } catch (e) {}
}
function currentSelfUpdateState(status = lastStatus || {}) {
  const update = status?.self_update;
  return update && typeof update === "object" ? update : {};
}
function selfUpdateActive(status = lastStatus || {}) {
  const update = currentSelfUpdateState(status);
  const token = String(update?.token || "").trim();
  return !!(updateMonitor.active || (update.active && (!token || !updateTokenCompleted(token))));
}
function storedUpdateToken(key) {
  try {
    return String(localStorage.getItem(key) || "").trim();
  } catch (e) {
    return "";
  }
}
function rememberPendingUpdateToken(token) {
  const value = String(token || "").trim();
  if (!value) return;
  try {
    localStorage.setItem(UPDATE_PENDING_TOKEN_KEY, value);
    if (storedUpdateToken(UPDATE_COMPLETED_TOKEN_KEY) === value) {
      localStorage.removeItem(UPDATE_COMPLETED_TOKEN_KEY);
    }
  } catch (e) {}
}
function rememberPendingUpdateReturn(tab = activeTabName, scrollTop = currentPageScrollTop()) {
  try {
    localStorage.setItem(
      UPDATE_PENDING_RETURN_KEY,
      JSON.stringify({
        tab: normalizeTabName(tab || activeTabName || "overview"),
        scrollTop: Math.max(0, Number(scrollTop || 0)),
      }),
    );
  } catch (e) {}
}
function readPendingUpdateReturn() {
  try {
    const parsed = JSON.parse(localStorage.getItem(UPDATE_PENDING_RETURN_KEY) || "null");
    if (!parsed || typeof parsed !== "object") return null;
    return {
      tab: normalizeTabName(parsed.tab || ""),
      scrollTop: Math.max(0, Number(parsed.scrollTop || 0)),
    };
  } catch (e) {}
  return null;
}
function markUpdateTokenCompleted(token) {
  const value = String(token || "").trim();
  if (!value) return;
  try {
    localStorage.setItem(UPDATE_COMPLETED_TOKEN_KEY, value);
    if (storedUpdateToken(UPDATE_PENDING_TOKEN_KEY) === value) {
      localStorage.removeItem(UPDATE_PENDING_TOKEN_KEY);
    }
  } catch (e) {}
}
function updateTokenCompleted(token) {
  const value = String(token || "").trim();
  return !!(value && storedUpdateToken(UPDATE_COMPLETED_TOKEN_KEY) === value);
}
function updateStatusIsTerminal(status) {
  return ["complete", "completed", "success", "failed", "error", "cancelled"].includes(
    String(status || "").trim().toLowerCase(),
  );
}
function completeUpdateMonitorFromStatus(update = {}, options = {}) {
  const updateToken = String(update?.token || "").trim();
  const pendingToken = storedUpdateToken(UPDATE_PENDING_TOKEN_KEY);
  const completedToken = storedUpdateToken(UPDATE_COMPLETED_TOKEN_KEY);
  const terminal = updateStatusIsTerminal(update?.status);
  const updatedVersion = String(update?.script_version || "").trim();
  const pageVersion = String(CLUB3090_SCRIPT_VERSION || "").trim();
  const finishedAtMs = Math.max(0, Number(update?.finished_at || 0)) * 1000;
  const recentlyFinished =
    finishedAtMs > 0 && Date.now() - finishedAtMs < 30 * 60 * 1000;
  const missedExternalUpdate =
    terminal &&
    updateToken &&
    completedToken !== updateToken &&
    recentlyFinished &&
    updatedVersion &&
    pageVersion &&
    updatedVersion !== pageVersion;
  const tokenMatches = updateToken && pendingToken === updateToken && completedToken !== updateToken;
  if (!terminal && !options.force) return false;
  if (!options.force && updateToken && completedToken === updateToken) return false;
  if (
    !options.force &&
    updateToken &&
    !tokenMatches &&
    !missedExternalUpdate &&
    !updateMonitor.active
  ) {
    return false;
  }
  completeUpdateMonitor(update);
  return true;
}
function updateFallbackLogSource(source) {
  const value = String(source || "").trim();
  if (
    value === "audit" ||
    value === "debug" ||
    value === "docker" ||
    value === "benchmarks" ||
    value === "script" ||
    String(value || "").startsWith("service:")
  ) {
    return value;
  }
  return "docker";
}
function pendingUpdateUiCanBeAbandoned(update = {}) {
  if (!updateMonitor.startedAt) return true;
  if (updateStatusIsTerminal(update?.status)) return true;
  return Date.now() - Number(updateMonitor.startedAt || 0) > 3000;
}
function abandonPendingUpdateUi(message = "") {
  if (updateMonitor.statusTimer) {
    clearInterval(updateMonitor.statusTimer);
    updateMonitor.statusTimer = null;
  }
  updateMonitor.active = false;
  updateMonitor.completed = true;
  updateMonitor.streamUrl = "";
  updateMonitor.statusUrl = "";
  updateMonitor.token = "";
  updateAcknowledgedToken = "";
  setUpdateUiLocked(false);
  if (currentLogSource === "update") {
    currentLogSource = updateFallbackLogSource(updateMonitor.returnLogSource);
    if (typeof noteKnownLogSource === "function") noteKnownLogSource(currentLogSource);
    if (typeof applyLogVisibility === "function") applyLogVisibility();
    if (typeof queueUiStateSave === "function") {
      queueUiStateSave({ current_log_source: currentLogSource });
    }
    if (typeof connectLogs === "function") connectLogs(true);
    if (typeof scheduleLogCacheRefresh === "function") {
      scheduleLogCacheRefresh(LOG_CACHE_REFRESH_MS);
    }
  }
  updateLogVisualMode();
  if (message && typeof setAuditMsg === "function") setAuditMsg(message);
}
function reconcileUpdateUiFromStatus(status = lastStatus || {}) {
  const update = currentSelfUpdateState(status);
  const updateToken = String(update.token || "").trim();
  if (!updateMonitor.active && update.active && (!updateToken || !updateTokenCompleted(updateToken))) {
    beginUpdateMonitor(
      {
        ...update,
        stream_url: update.stream_url || "/admin/update-stream",
        status_url: update.status_url || "/admin/update-status",
      },
      update.scope || "controller",
    );
    return;
  }
  if (!updateMonitor.active && update.active && updateToken && updateTokenCompleted(updateToken)) {
    if (updateUiLocked || currentLogSource === "update") {
      abandonPendingUpdateUi(
        "Ignoring stale self-update activity for an already completed update token. Restored normal logs.",
      );
      return;
    }
    setUpdateUiLocked(false);
    return;
  }
  if (!updateMonitor.active && !update.active && updateToken && completeUpdateMonitorFromStatus(update)) {
    return;
  }
  if (!updateMonitor.active && !update.active && (updateUiLocked || currentLogSource === "update")) {
    if (pendingUpdateUiCanBeAbandoned(update)) {
      abandonPendingUpdateUi(
        "No active self-update handoff was found. Restored the admin panel to normal logs.",
      );
      return;
    }
  }
  const pendingToken = storedUpdateToken(UPDATE_PENDING_TOKEN_KEY);
  const completedToken = storedUpdateToken(UPDATE_COMPLETED_TOKEN_KEY);
  if (
    !updateMonitor.active &&
    !update.active &&
    updateToken &&
    pendingToken === updateToken &&
    completedToken !== updateToken &&
    updateStatusIsTerminal(update.status)
  ) {
    completeUpdateMonitorFromStatus(update);
    return;
  }
  if (!updateMonitor.active) setUpdateUiLocked(false);
}
async function acknowledgeRenderedUpdateMode(token = "") {
  const value = String(token || updateMonitor.token || "").trim();
  if (!value || updateAcknowledgedToken === value) return;
  if (
    !updateMonitor.active ||
    !updateUiLocked ||
    currentLogSource !== "update" ||
    activeTabName !== "logs" ||
    !document.body.classList.contains("update-lock-active")
  ) {
    return;
  }
  const response = await fetch("/admin/update-ack", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token: value }),
    cache: "no-store",
  });
  if (!response.ok) return;
  const payload = await response.json().catch(() => ({}));
  if (payload?.ok) updateAcknowledgedToken = value;
}
function scheduleRenderedUpdateAcknowledgement(token = "") {
  const callback = () => acknowledgeRenderedUpdateMode(token).catch(() => {});
  if (typeof window.requestAnimationFrame === "function") {
    window.requestAnimationFrame(() => window.requestAnimationFrame(callback));
    return;
  }
  setTimeout(callback, 0);
}
async function pollExternalUpdateSignal() {
  if (updateSignalPollActive || updateMonitor.active) return;
  updateSignalPollActive = true;
  try {
    const response = await fetch(`/admin/update-signal?_=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) return;
    const payload = await response.json().catch(() => ({}));
    const update = payload?.self_update || {};
    const token = String(update?.token || "").trim();
    if (update?.active && token && storedUpdateToken(UPDATE_COMPLETED_TOKEN_KEY) !== token) {
      beginUpdateMonitor(
        {
          ...update,
          stream_url: update.stream_url || `/admin/update-stream?token=${encodeURIComponent(token)}&tail=4000`,
          status_url: update.status_url || `/admin/update-status?token=${encodeURIComponent(token)}`,
        },
        update.scope || "controller",
      );
    }
  } catch (e) {
  } finally {
    updateSignalPollActive = false;
  }
}
function startExternalUpdateSignalPolling() {
  if (updateSignalPollTimer) clearInterval(updateSignalPollTimer);
  updateSignalPollTimer = setInterval(() => {
    pollExternalUpdateSignal().catch(() => {});
  }, UPDATE_SIGNAL_POLL_MS);
  pollExternalUpdateSignal().catch(() => {});
}
function recoverPendingUpdateMonitor(scope = "controller") {
  if (updateMonitor.active || updateMonitor.completed) return false;
  const token = storedUpdateToken(UPDATE_PENDING_TOKEN_KEY);
  if (!token || storedUpdateToken(UPDATE_COMPLETED_TOKEN_KEY) === token) return false;
  beginUpdateMonitor(
    {
      token,
      stream_url: `/admin/update-stream?token=${encodeURIComponent(token)}&tail=4000`,
      status_url: `/admin/update-status?token=${encodeURIComponent(token)}`,
    },
    scope,
  );
  return true;
}
function minimizeSurfacesForUpdateMode() {
  try {
    if (typeof collapseBenchmarkAllModal === "function" && $("benchmarkAllModal") && !$("benchmarkAllModal").classList.contains("hidden")) {
      collapseBenchmarkAllModal();
    } else {
      $("benchmarkAllModal")?.classList.add("hidden");
    }
  } catch (e) {
    $("benchmarkAllModal")?.classList.add("hidden");
  }
  try {
    if (typeof minimizeStorageEditorModal === "function") minimizeStorageEditorModal();
    else $("storageEditorModal")?.classList.add("hidden");
  } catch (e) {
    $("storageEditorModal")?.classList.add("hidden");
  }
  [
    "presetScoresModal",
    "storageBrowserModal",
    "runScriptModal",
    "presetActionModal",
    "actionChoiceModal",
    "presetLaunchSettingsModal",
    "duplicatePresetModal",
    "customModelModal",
    "chatConversationModal",
    "chatArchivedModal",
  ].forEach((id) => {
    try {
      $(id)?.classList.add("hidden");
    } catch (e) {}
  });
}
function setUpdateUiLocked(locked) {
  updateUiLocked = !!locked;
  if (updateUiLocked) minimizeSurfacesForUpdateMode();
  document.body.classList.toggle("update-lock-active", updateUiLocked);
  document
    .querySelectorAll("button, input, select, textarea")
    .forEach((node) => {
      if (!node || node.id === "log") return;
      if (updateUiLocked) node.setAttribute("disabled", "disabled");
      else if (!node.dataset.scopeDisabled) node.removeAttribute("disabled");
    });
  if ($("log")) $("log").removeAttribute("disabled");
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
function currentClubAlertTitle() {
  const rawVersion = String(lastStatus?.script_version || CLUB3090_SCRIPT_VERSION || "").trim();
  const shortVersionMatch = rawVersion.match(/v\d+\.\d+\.\d+[a-z]*/);
  const shortVersion = shortVersionMatch ? shortVersionMatch[0] : "";
  return shortVersion ? `Club-3090 Server ${shortVersion}` : "Club-3090 Server";
}
function ensureAlertModal() {
  if ($("clubAlertModal")) return;
  const doc = currentUiDocument();
  const modal = doc.createElement("div");
  modal.id = "clubAlertModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card conversation-modal-card" role="dialog" aria-modal="true" aria-labelledby="clubAlertTitle"><div class="panel-head"><h2 id="clubAlertTitle">Club-3090 Server</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeClubAlertModal()">✕</button></div><div class="preset-help" id="clubAlertBody"></div><div class="preset-form-actions"><button class="btn blue" onclick="closeClubAlertModal()">OK</button></div></div>`;
  doc.body.appendChild(modal);
}
function closeClubAlertModal() {
  ensureAlertModal();
  $("clubAlertModal").classList.add("hidden");
}
function openClubAlertModal(message = "", title = "") {
  ensureAlertModal();
  $("clubAlertTitle").textContent = String(title || currentClubAlertTitle());
  $("clubAlertBody").innerHTML = escapeHtml(String(message || "")).replace(/\n/g, "<br>");
  $("clubAlertModal").classList.remove("hidden");
}
window.closeClubAlertModal = closeClubAlertModal;
window.alert = function club3090Alert(message = "") {
  openClubAlertModal(message, currentClubAlertTitle());
};
function ensureClubDecisionModal() {
  if ($("clubDecisionModal")) return;
  const doc = currentUiDocument();
  const modal = doc.createElement("div");
  modal.id = "clubDecisionModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card conversation-modal-card" role="dialog" aria-modal="true" aria-labelledby="clubDecisionTitle"><div class="panel-head"><h2 id="clubDecisionTitle">Club-3090 Server</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="resolveClubDecisionModal('cancel')">✕</button></div><div class="preset-help" id="clubDecisionBody"></div><label class="hidden" id="clubDecisionInputWrap">Value<input id="clubDecisionInput" class="club-text-field club-decision-input" /></label><div class="preset-form-actions"><button class="btn blue" id="clubDecisionCancelBtn" onclick="resolveClubDecisionModal('cancel')">Cancel</button><button class="btn green" id="clubDecisionOkBtn" onclick="resolveClubDecisionModal('ok')">OK</button></div></div>`;
  doc.body.appendChild(modal);
}
let clubDecisionResolver = null;
function resolveClubDecisionModal(action = "cancel") {
  if (!clubDecisionResolver) return;
  const resolver = clubDecisionResolver;
  clubDecisionResolver = null;
  $("clubDecisionModal")?.classList.add("hidden");
  const input = $("clubDecisionInput");
  resolver({
    action,
    value: input ? String(input.value || "") : "",
  });
}
window.resolveClubDecisionModal = resolveClubDecisionModal;
function openClubConfirmModal(message = "", title = "") {
  ensureClubDecisionModal();
  const config =
    message && typeof message === "object" && !Array.isArray(message)
      ? message
      : { message, title };
  $("clubDecisionTitle").textContent = String(config.title || currentClubAlertTitle());
  $("clubDecisionBody").innerHTML =
    config.bodyHtml !== undefined
      ? String(config.bodyHtml || "")
      : escapeHtml(String(config.message || "")).replace(/\n/g, "<br>");
  $("clubDecisionBody").classList.toggle("danger-copy", !!config.dangerBody);
  $("clubDecisionInputWrap").classList.add("hidden");
  $("clubDecisionInput").value = "";
  $("clubDecisionCancelBtn").classList.remove("hidden");
  $("clubDecisionOkBtn").textContent = String(config.confirmLabel || "OK");
  $("clubDecisionOkBtn").classList.remove("blue", "green", "amber", "red");
  $("clubDecisionOkBtn").classList.add(String(config.confirmClass || "green"));
  $("clubDecisionModal").classList.remove("hidden");
  return new Promise((resolve) => {
    clubDecisionResolver = ({ action }) => resolve(action === "ok");
  });
}
function openClubTextInputModal(config = {}) {
  ensureClubDecisionModal();
  const options =
    config && typeof config === "object" && !Array.isArray(config)
      ? config
      : { message: String(config || "") };
  $("clubDecisionTitle").textContent = String(
    options.title || currentClubAlertTitle(),
  );
  $("clubDecisionBody").innerHTML = escapeHtml(
    String(options.message || ""),
  ).replace(/\n/g, "<br>");
  $("clubDecisionBody").classList.remove("danger-copy");
  const inputWrap = $("clubDecisionInputWrap");
  const input = $("clubDecisionInput");
  inputWrap.classList.remove("hidden");
  inputWrap.childNodes[0].textContent = String(options.label || "Value");
  input.value = String(options.value || "");
  $("clubDecisionCancelBtn").classList.remove("hidden");
  $("clubDecisionOkBtn").textContent = String(options.confirmLabel || "Save");
  $("clubDecisionOkBtn").classList.remove("blue", "green", "amber", "red");
  $("clubDecisionOkBtn").classList.add(String(options.confirmClass || "green"));
  $("clubDecisionModal").classList.remove("hidden");
  setTimeout(() => {
    input.focus();
    input.select();
  }, 0);
  return new Promise((resolve) => {
    clubDecisionResolver = ({ action, value }) =>
      resolve(action === "ok" ? value : null);
  });
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
  scheduleStatusPoll(0);
  scheduleLogCacheRefresh(document.hidden && !popupLogWindowOpen() ? LOG_CACHE_REFRESH_MS : 0);
});
