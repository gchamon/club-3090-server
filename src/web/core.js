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
let showGlobalLogSources =
  window.showGlobalLogSources || (window.showGlobalLogSources = Object.create(null));
let currentLogSource = "docker";
const knownLogSources = new Set(["docker", "audit", "debug"]);
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
  reloadScheduled: false,
};
let updateUiLocked = false;
let lastWindowFocused = typeof document.hasFocus === "function" ? document.hasFocus() : true;
let lastSwitchNotificationKey = "";
let detachedLogPopupClosedPollTimer = null;
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
  return document.getElementById(id);
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
  return !!(updateMonitor.active || currentSelfUpdateState(status).active);
}
function reconcileUpdateUiFromStatus(status = lastStatus || {}) {
  const update = currentSelfUpdateState(status);
  if (!updateMonitor.active && update.active) {
    if (update.stream_url && update.status_url) {
      beginUpdateMonitor(update, update.scope || "controller");
      return;
    }
    setUpdateUiLocked(true);
    return;
  }
  if (!updateMonitor.active) setUpdateUiLocked(false);
}
function setUpdateUiLocked(locked) {
  updateUiLocked = !!locked;
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
  const modal = document.createElement("div");
  modal.id = "clubAlertModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card conversation-modal-card" role="dialog" aria-modal="true" aria-labelledby="clubAlertTitle"><div class="panel-head"><h2 id="clubAlertTitle">Club-3090 Server</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeClubAlertModal()">✕</button></div><div class="preset-help" id="clubAlertBody"></div><div class="preset-form-actions"><button class="btn blue" onclick="closeClubAlertModal()">OK</button></div></div>`;
  document.body.appendChild(modal);
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
  const modal = document.createElement("div");
  modal.id = "clubDecisionModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card conversation-modal-card" role="dialog" aria-modal="true" aria-labelledby="clubDecisionTitle"><div class="panel-head"><h2 id="clubDecisionTitle">Club-3090 Server</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="resolveClubDecisionModal('cancel')">✕</button></div><div class="preset-help" id="clubDecisionBody"></div><label class="hidden" id="clubDecisionInputWrap">Value<input id="clubDecisionInput" class="club-text-field club-decision-input" /></label><div class="preset-form-actions"><button class="btn blue" id="clubDecisionCancelBtn" onclick="resolveClubDecisionModal('cancel')">Cancel</button><button class="btn green" id="clubDecisionOkBtn" onclick="resolveClubDecisionModal('ok')">OK</button></div></div>`;
  document.body.appendChild(modal);
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
