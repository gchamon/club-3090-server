allPairChoices = function () {
  const count = gpuCount(),
    pairs = [];
  for (let a = 0; a < count; a += 1) {
    for (let b = a + 1; b < count; b += 1) pairs.push([a, b]);
  }
  return pairs;
};
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
    bar.classList.add("hidden");
    return;
  }
  const pair = currentScopeInstance(true);
  const showDelete = !!pair && pair.kind === "dual" && !pair.auto_pair;
  bar.style.margin = "8px 0 10px";
  if (!showDelete && !instanceBusyState.active) {
    bar.innerHTML = "";
    bar.classList.add("hidden");
    return;
  }
  bar.classList.remove("hidden");
  bar.innerHTML = `${showDelete ? `<button class="btn red" onclick="deleteCurrentPairGroup()">Delete ${scopeLabel(pair)}</button>` : ""}${instanceBusyState.active ? `<span class="label busy-note"><span class="spinner" aria-hidden="true"></span>${escapeHtml(instanceBusyState.message || "Updating custom pair...")}</span>` : ""}`;
};
function ensureSystemServicesPanel() {
  const panel = $("systemServicesPanel") || findPanelByHeading("system", "Services");
  if (!panel) return;
  panel.id = "systemServicesPanel";
  const instancesPanel = findPanelByHeading("system", "Instances");
  if (instancesPanel && panel.previousElementSibling !== instancesPanel) {
    instancesPanel.insertAdjacentElement("afterend", panel);
  }
  if (!$("serverServices") || !$("club3090Services")) return;
  SYSTEM_SERVICE_SECTION_KEYS.forEach(applySystemServiceSectionState);
  if (lastStatus) renderSystemServices(lastStatus);
}
ensureV414Layout = function () {
  ensureV413Layout();
  ensureUsersUi();
  ensureGroupUi();
  ensureAccessPolicyCard();
  ensureAuditOverviewCard();
  ensureSystemServicesPanel();
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
