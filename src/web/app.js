function activateTab(name, firstRender = false) {
  activeTabName = normalizeTabName(name);
  logDebugEvent("tab_activate", { name: activeTabName, firstRender: !!firstRender });
  syncActiveTabDisplay();
  connectLogs(false);
  scheduleLogCacheRefresh(logViewerVisible() ? LOG_CACHE_REFRESH_MS : 0);
  if (activeTabName === "metrics") {
    redrawMetricsSoon();
    refreshStatus({ force: true, includeSeries: true }).catch(() => {});
  }
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
  refreshStatus({ force: true, includeSeries: activeTabName === "metrics" }).catch(() => {});
  scheduleStatusPoll(0);
  queueUiStateSave();
  setTimeout(() => {
    if (!searchState.active && $("autoscroll").checked && $("log"))
      $("log").scrollTop = $("log").scrollHeight;
  }, 0);
}
tab = function (e, n) {
  activateTab(n, false);
};
async function manualRefreshStatus() {
  try {
    await refreshStatus();
  } finally {
    refreshStatus({ force: true }).catch(() => {});
  }
}
function statusRequestProfile(options = {}) {
  const tab = normalizeTabName(activeTabName);
  const includeSeries =
    !!options.includeSeries || tab === "metrics" || popupMetricsWindowActive();
  return {
    tab,
    hidden: document.hidden && !popupLogWindowActive() ? "1" : "0",
    include_series: includeSeries ? "1" : "0",
    include_inventory: tab === "presets" || tab === "chat" ? "1" : "0",
    include_config: "1",
  };
}
function statusPollDelayMs() {
  if (popupMetricsWindowActive()) return STATUS_POLL_FOREGROUND_FAST_MS;
  if (popupLogWindowActive()) return STATUS_POLL_FOREGROUND_FAST_MS;
  if (document.hidden) return STATUS_POLL_BACKGROUND_MS;
  if (Number(lastStatus?.metrics?.active_requests || 0) > 0) {
    return STATUS_POLL_FOREGROUND_FAST_MS;
  }
  if (activeTabName === "metrics" || activeTabName === "logs" || activeTabName === "chat") {
    return STATUS_POLL_FOREGROUND_FAST_MS;
  }
  return STATUS_POLL_FOREGROUND_SLOW_MS;
}
function scheduleStatusPoll(delayMs = null) {
  statusPollNonce += 1;
  if (statusPollTimer) clearInterval(statusPollTimer);
  const pollDelay = Math.max(
    STATUS_POLL_FOREGROUND_FAST_MS,
    delayMs === null ? statusPollDelayMs() : Number(delayMs || statusPollDelayMs()),
  );
  statusPollTimer = setInterval(() => {
    refreshStatus().catch(() => {});
  }, pollDelay);
  if (delayMs === 0) refreshStatus().catch(() => {});
}
refreshStatus = async function (opts = {}) {
  const force = !!(opts && opts.force);
  const includeSeries = !!(opts && opts.includeSeries);
  if (updateMonitor.active) return lastStatus;
  if (adminAuthRefreshBlocked && !force) return lastStatus;
  if (statusRefreshPromise) {
    if (force) {
      pendingForcedStatusRefresh = true;
      pendingForcedStatusRefreshIncludeSeries =
        pendingForcedStatusRefreshIncludeSeries || includeSeries;
    }
    return statusRefreshPromise;
  }
  statusRefreshPromise = (async () => {
    try {
      ensureV414Layout();
      const query = new URLSearchParams(statusRequestProfile({ includeSeries }));
      const statusRequestStartedAt = Date.now();
      query.set("_", String(statusRequestStartedAt));
      if (force) query.set("force", "1");
      const r = await fetchJsonWithTimeout(`/admin/status?${query.toString()}`, { cache: "no-store" }, 12000);
      if (r.status === 401) {
        adminAuthRefreshBlocked = true;
        setMsg("Authentication expired. Reloading the admin panel...");
        setTimeout(() => {
          window.location.href = "/admin";
        }, 400);
        return lastStatus;
      }
      if (!r.ok) throw new Error(`status fetch failed (${r.status})`);
      const payload = await r.json();
      const j = lastStatus ? { ...lastStatus, ...payload } : payload;
      adminAuthRefreshBlocked = false;
      reconcileHiddenPresetSelectorsFromStatus(j, statusRequestStartedAt);
      const metrics = j.metrics || {},
        power = j.power || {};
      const previousStatus = lastStatus;
      lastStatus = j;
      syncPresetSummaryCacheFromStatus(j);
      hydrateUiState(j.ui_config || {});
      ensureChatHydrationForActiveTab();
      hydrateSelectedPresetModel();
      if ($("showGlobalLogs")) {
        $("showGlobalLogs").checked = effectiveShowGlobalLogs();
        $("showGlobalLogs").disabled = currentLogSourceDetached();
      }
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
      safeRenderStep(
        "metrics",
        () => {
          if (activeTabName === "metrics" || popupMetricsWindowOpen()) renderMetrics(j);
        },
        renderErrors,
      );
      safeRenderStep("presets", () => renderPresetCatalog(j.presets), renderErrors);
      safeRenderStep("users", () => renderUsers(j.users || []), renderErrors);
      safeRenderStep("groups", () => renderGroups(j.groups || []), renderErrors);
      safeRenderStep("audit", () => renderAudit(j.server_config || {}), renderErrors);
      safeRenderStep("update notices", () => renderUpdateNotices(j), renderErrors);
      safeRenderStep("update button", () => renderUpdateButton(j), renderErrors);
      safeRenderStep("instances", () => renderInstances(j.instances || []), renderErrors);
      safeRenderStep("preset scopes", () => renderPresetScopeTabs(), renderErrors);
      safeRenderStep("scoped cards", () => updateScopedCards(), renderErrors);
      safeRenderStep("model install status", () => renderModelInstallStatus(), renderErrors);
      safeRenderStep("dynamic preset models", () => renderDynamicPresetModels(), renderErrors);
      scheduleStatusPoll();
      safeRenderStep("chat", () => renderChatUi({ preserveTranscript: true }), renderErrors);
      safeRenderStep("tab sync", () => syncActiveTabDisplay(), renderErrors);
      reconcileUpdateUiFromStatus(j);
      if (activeTabName === "logs" || effectiveShowGlobalLogs()) connectLogs(false);
      handleSwitchJobTransition(previousStatus, j);
      const statusWarnings = [];
      if (j.access_hint?.message) statusWarnings.push(String(j.access_hint.message));
      if (j.status_error) statusWarnings.push(`Status probe fallback: ${j.status_error}`);
      if (renderErrors.length) statusWarnings.push(`Partial UI render: ${renderErrors.join(" | ")}`);
      setMsg(joinMessageParts(statusWarnings));
    } catch (e) {
      setMsg(`Status error: ${messageText(e)}`);
    } finally {
      statusRefreshPromise = null;
      if (pendingForcedStatusRefresh) {
        const nextIncludeSeries = pendingForcedStatusRefreshIncludeSeries;
        pendingForcedStatusRefresh = false;
        pendingForcedStatusRefreshIncludeSeries = false;
        refreshStatus({ force: true, includeSeries: nextIncludeSeries }).catch(() => {});
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
  ensureResizableSurfaces();
  loadCodeSyntaxConfig().catch(() => {});
  hydratePresetSummaryCache();
  resetUserForm(true);
  resetGroupForm(true);
  if (!selectedScope)
    selectedScope =
      singleScopeItems()[0]?.id || pairScopeItems()[0]?.id || "GLOBAL";
  setScope(selectedScope, false);
  refreshStatus({ force: true }).catch(() => {});
  if (!initialMetricsSeriesRequested) {
    initialMetricsSeriesRequested = true;
    refreshStatus({ force: true, includeSeries: true }).catch(() => {});
  }
  scheduleStatusPoll();
  scheduleLogCacheRefresh();
  if (detachedLogPopupClosedPollTimer) clearInterval(detachedLogPopupClosedPollTimer);
  detachedLogPopupClosedPollTimer = setInterval(
    () => {
      pollDetachedLogPopupClosures();
      pollDetachedMetricsPopupClosures();
    },
    DETACHED_LOG_POPUP_CLOSED_POLL_MS,
  );
  syncHeaderChatButtonAlignment();
  window.addEventListener("resize", syncHeaderChatButtonAlignment);
  window.addEventListener("beforeunload", () => {
    if (detachedLogPopupClosedPollTimer) {
      clearInterval(detachedLogPopupClosedPollTimer);
      detachedLogPopupClosedPollTimer = null;
    }
    if (logEs) {
      try {
        logEs.close();
      } catch (e) {}
    }
    Object.keys(window.logPopupStates).forEach((signature) => {
      const state = window.logPopupStates[signature];
      if (state?.es) {
        try {
          state.es.close();
        } catch (e) {}
      }
      if (state?.win && !state.win.closed) {
        try {
          state.win.close();
        } catch (e) {}
      }
    });
    Object.keys(window.metricsPopupStates || {}).forEach((signature) => {
      const state = window.metricsPopupStates[signature];
      if (state?.win && !state.win.closed) {
        try {
          state.win.close();
        } catch (e) {}
      }
    });
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
function inventoryProfileLikes() {
  return runtimeInventory().profile_likes || [];
}
function modelIsCustom(model) {
  return String(model?.source_kind || "").trim().toLowerCase() === "custom" || !!model?.custom_model;
}
function customInventoryModels() {
  return inventoryModels().filter((model) => modelIsCustom(model));
}
function curatedInventoryModels() {
  return inventoryModels().filter((model) => !modelIsCustom(model));
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
  valid.add(RESOURCE_MANAGER_MODEL_ID);
  valid.add(HIDDEN_PRESETS_MODEL_ID);
  const configured = String(lastStatus?.server_config?.selected_preset_model || "").trim();
  if (!selectedPresetModelHydrated) {
    selectedPresetModelId = valid.has(configured) ? configured : "";
    selectedPresetModelHydrated = true;
    return;
  }
  if (!selectedPresetModelId) return;
  if (selectedPresetModelId && valid.has(selectedPresetModelId)) return;
  selectedPresetModelId = valid.has(configured) ? configured : "";
}
function selectPresetModel(modelId = "") {
  selectedPresetModelId = String(modelId || "").trim();
  selectedPresetModelHydrated = true;
  renderPresetModelSelector();
  renderDynamicPresetModels();
  renderModelInstallStatus();
  saveSelectedPresetModel(selectedPresetModelId);
}
function renderPresetModelSelector() {
  const host = $("presetModelSelector");
  if (!host) return;
  const models = inventoryModels();
  if (!models.length) {
    host.classList.remove("hidden");
    host.innerHTML = [
      renderHiddenPresetsTriggerButton(),
      '<span class="scope-strip-separator" aria-hidden="true"></span>',
      renderCustomModelTriggerButton({
        className: "subtab custom-model-trigger",
        label: "Custom Model",
        onClick: "openCustomModelModal()",
      }),
      '<span class="scope-strip-separator" aria-hidden="true"></span>',
      renderResourceManagerTriggerButton(),
    ].join("");
    return;
  }
  host.classList.remove("hidden");
  const curated = curatedInventoryModels();
  const custom = customInventoryModels();
  const renderModelButton = (model) => {
    const modelId = String(model.model_id || "");
    return `<button class="subtab ${modelId === selectedPresetModelId ? "active" : ""}" onclick="selectPresetModel('${escapeJs(modelId)}')">${escapeHtml(model.display_name || modelId)}</button>`;
  };
  const parts = [
    `<button class="subtab ${!selectedPresetModelId ? "active" : ""}" onclick="selectPresetModel('')">Summary</button>`,
    ...curated.map(renderModelButton),
  ];
  if (custom.length || curated.length) {
    parts.push('<span class="scope-strip-separator" aria-hidden="true"></span>');
  }
  if (custom.length) {
    parts.push(...custom.map(renderModelButton));
    parts.push('<span class="scope-strip-separator" aria-hidden="true"></span>');
  }
  parts.push(
    renderHiddenPresetsTriggerButton({
      className: `subtab hidden-presets-trigger ${selectedPresetModelId === HIDDEN_PRESETS_MODEL_ID ? "active" : ""}`,
    }),
  );
  parts.push('<span class="scope-strip-separator" aria-hidden="true"></span>');
  parts.push(
    renderCustomModelTriggerButton({
      className: "subtab custom-model-trigger",
      label: "Custom Model",
      onClick: "openCustomModelModal()",
    }),
  );
  parts.push('<span class="scope-strip-separator" aria-hidden="true"></span>');
  parts.push(
    renderResourceManagerTriggerButton({
      className: `subtab resource-manager-trigger ${selectedPresetModelId === RESOURCE_MANAGER_MODEL_ID ? "active" : ""}`,
    }),
  );
  host.innerHTML = parts.join("");
}
function customModelTriggerContent(label = "Custom Model") {
  return `<span class="custom-model-trigger-content"><span class="custom-model-trigger-icon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><circle cx="12" cy="12" r="11"></circle><path d="M12 7v10M7 12h10"></path></svg></span><span class="custom-model-trigger-label">${escapeHtml(label)}</span></span>`;
}
function renderCustomModelTriggerButton({
  className = "subtab custom-model-trigger",
  label = "Custom Model",
  onClick = "openCustomModelModal()",
} = {}) {
  return `<button class="${className}" onclick="${onClick}">${customModelTriggerContent(label)}</button>`;
}
const RESOURCE_MANAGER_MODEL_ID = "__model_resources__";
const HIDDEN_PRESETS_MODEL_ID = "__hidden_presets__";
let pendingHiddenPresetSelectors = null;
let pendingHiddenPresetConfirmAfter = 0;
function renderHiddenPresetsTriggerButton({
  className = "subtab hidden-presets-trigger",
  label = "Hidden Presets",
  onClick = `selectPresetModel('${HIDDEN_PRESETS_MODEL_ID}')`,
} = {}) {
  return `<button class="${className}" onclick="${onClick}"><span class="custom-model-trigger-content"><span class="custom-model-trigger-icon hidden-presets-trigger-icon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d="M2.5 12s3.6-6 9.5-6 9.5 6 9.5 6-3.6 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="3.25"></circle><path d="M4 20 20 4"></path></svg></span><span class="custom-model-trigger-label">${escapeHtml(label)}</span></span></button>`;
}
function renderResourceManagerTriggerButton({
  className = "subtab resource-manager-trigger",
  label = "Model Manager",
  onClick = `selectPresetModel('${RESOURCE_MANAGER_MODEL_ID}')`,
} = {}) {
  return `<button class="${className}" onclick="${onClick}"><span class="custom-model-trigger-content"><span class="custom-model-trigger-icon resource-manager-trigger-icon" aria-hidden="true">${svgIcon("gear")}</span><span class="custom-model-trigger-label">${escapeHtml(label)}</span></span></button>`;
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
function hiddenPresetSelectors() {
  if (Array.isArray(pendingHiddenPresetSelectors)) {
    return pendingHiddenPresetSelectors.map((row) => String(row || "").trim()).filter(Boolean);
  }
  const rows = lastStatus?.server_config?.hidden_preset_selectors;
  return Array.isArray(rows) ? rows.map((row) => String(row || "").trim()).filter(Boolean) : [];
}
function normalizeHiddenPresetSelectors(rows) {
  return [...new Set((Array.isArray(rows) ? rows : []).map((row) => String(row || "").trim()).filter(Boolean))].sort();
}
function hiddenPresetSelectorListsMatch(left, right) {
  const a = normalizeHiddenPresetSelectors(left);
  const b = normalizeHiddenPresetSelectors(right);
  return a.length === b.length && a.every((value, index) => value === b[index]);
}
function reconcileHiddenPresetSelectorsFromStatus(status, requestStartedAt = 0) {
  if (!Array.isArray(pendingHiddenPresetSelectors)) return;
  const pending = normalizeHiddenPresetSelectors(pendingHiddenPresetSelectors);
  const serverRows = normalizeHiddenPresetSelectors(status?.server_config?.hidden_preset_selectors);
  if (
    Number(requestStartedAt || 0) >= Number(pendingHiddenPresetConfirmAfter || 0) &&
    hiddenPresetSelectorListsMatch(serverRows, pending)
  ) {
    pendingHiddenPresetSelectors = null;
    pendingHiddenPresetConfirmAfter = 0;
    return;
  }
  status.server_config = {
    ...(status.server_config || {}),
    hidden_preset_selectors: pending,
  };
}
function hiddenPresetSelectorSet() {
  return new Set(hiddenPresetSelectors());
}
function presetIsHidden(variant) {
  return hiddenPresetSelectorSet().has(String(variantSelector(variant) || "").trim());
}
async function saveHiddenPresetSelectors(selectors) {
  const next = [...new Set((selectors || []).map((item) => String(item || "").trim()).filter(Boolean))];
  if (!lastStatus) lastStatus = {};
  pendingHiddenPresetSelectors = next;
  lastStatus.server_config = {
    ...(lastStatus.server_config || {}),
    hidden_preset_selectors: next,
  };
  try {
    const payload = await post(
      "/admin/users",
      {
        action: "save_server_config",
        hidden_preset_selectors: next,
      },
      `/admin/users save_server_config hidden_preset_selectors ${next.length}`,
      { silentSuccess: true },
    );
    lastStatus.server_config = {
      ...(lastStatus.server_config || {}),
      ...(payload?.server_config || {}),
      hidden_preset_selectors: next,
    };
    pendingHiddenPresetConfirmAfter = Date.now();
  } catch (error) {
    pendingHiddenPresetSelectors = null;
    pendingHiddenPresetConfirmAfter = 0;
    throw error;
  }
}
async function hidePresetSelector(selector) {
  const key = String(selector || "").trim();
  if (!key) return;
  const hidden = hiddenPresetSelectors();
  if (hidden.includes(key)) return;
  pendingHiddenPresetSelectors = [...hidden, key];
  renderPresetModelSelector();
  renderDynamicPresetModels();
  await saveHiddenPresetSelectors([...hidden, key]);
  refreshStatus({ force: true }).catch(() => {});
  renderPresetModelSelector();
  renderDynamicPresetModels();
}
async function unhidePresetSelector(selector) {
  const key = String(selector || "").trim();
  if (!key) return;
  const next = hiddenPresetSelectors().filter((item) => item !== key);
  pendingHiddenPresetSelectors = next;
  renderPresetModelSelector();
  renderDynamicPresetModels();
  await saveHiddenPresetSelectors(next);
  refreshStatus({ force: true }).catch(() => {});
  renderPresetModelSelector();
  renderDynamicPresetModels();
}
function escapeJs(value) {
  return String(value || "")
    .replaceAll("\\", "\\\\")
    .replaceAll("'", "\\'");
}
function prettyEngineName(engine) {
  if (engine === "ik-llama") return "ik-llama";
  return engine === "llamacpp" ? "llama.cpp" : String(engine || "");
}
function variantDisplayLabel(variant) {
  if (String(variant?.source_kind || "").trim().toLowerCase() === "custom") {
    return String(variant?.model_display_name || variant?.display_name || variant?.upstream_tag || "custom model");
  }
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
function variantProvenanceBadges(variant) {
  const bits = [];
  const sourceKind = String(variant?.source_kind || "").trim().toLowerCase();
  if (sourceKind === "custom") {
    bits.push('<span class="status-badge status-custom">Custom</span>');
  }
  const confidence = String(variant?.confidence_tier || "").trim().toLowerCase();
  if (sourceKind === "custom" && confidence) {
    bits.push(
      `<span class="status-badge status-custom_confidence">${escapeHtml(confidence.replaceAll("-", " "))}</span>`,
    );
  }
  return bits.join("");
}
function variantCapabilityBadges(variant) {
  const bits = [];
  const nvlinkMode = variantNvlinkMode(variant);
  if (nvlinkMode === "required") {
    bits.push('<span class="status-badge status-nvlink">NVLink</span>');
  } else if (nvlinkMode === "capable" && rigHasNvlink()) {
    bits.push('<span class="status-badge status-nvlink_capable">NVLink-capable</span>');
  }
  const provenance = variantProvenanceBadges(variant);
  if (provenance) bits.push(provenance);
  return bits.join("");
}
function installStateLabel(variant) {
  const state = variantEffectiveInstallState(variant);
  if (state === "ready") return "ready";
  if (state === "hardware_blocked") return "hardware blocked";
  if (state === "requires_download") return "needs download";
  if (state === "unavailable") return "unavailable";
  return state;
}
function statusLabel(variant) {
  const kind = variantEffectiveStatusKind(variant);
  if (kind === "production") return "production";
  if (kind === "production_caveat") return "production + caveats";
  if (kind === "preview") return "preview";
  if (kind === "upstream_gated") return "upstream gated";
  if (kind === "blocked" || kind === "hardware_blocked") return "hardware blocked";
  if (kind === "tombstoned") return "tombstoned";
  if (kind === "deprecated") return "deprecated";
  if (kind === "experimental") return "experimental";
  return "unknown";
}
function statusBadgeTokens(variant) {
  const kind = String(variantEffectiveStatusKind(variant) || "unknown").trim();
  if (kind === "production_caveat") {
    return [
      { className: "status-production", label: "production" },
      { className: "status-caveats", label: "caveats" },
    ];
  }
  return [
    {
      className: badgeClass("status", kind),
      label: statusLabel(variant),
    },
  ];
}
function statusBadgeNormalizedText(text) {
  return String(text || "").trim().toLowerCase();
}
function renderStatusBadgesHtml(variant, options = {}) {
  if (options.failed) return "";
  const blockedState = statusBadgeNormalizedText(options.stateLabel || "");
  return statusBadgeTokens(variant)
    .filter((token) => token && token.label)
    .filter((token) => {
      const label = statusBadgeNormalizedText(token.label);
      if (options.rigBlockedReason && label === "hardware blocked") return false;
      return label !== blockedState;
    })
    .map((token) => `<span class="status-badge ${token.className}">${escapeHtml(options.countLabel ? `${token.label} ${options.countLabel}` : token.label)}</span>`)
    .join("");
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
    if (["exited"].includes(text)) return "status-exited";
    if (["inactive", "stopped", "dead", "failed"].includes(text))
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
    status: row?.running ? "running" : String(row?.status || "stopped"),
    health_status: row?.running
      ? String(row?.health_status || "running")
      : String(
          row?.status || row?.health_status || "stopped",
        ) + (row?.status === "exited" && row?.exit_code !== null && row?.exit_code !== undefined ? ` (code ${row.exit_code})` : ""),
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
  setHtmlIfChanged(
    serverHost,
    renderServiceCards(serverCards, {
      emptyText: "No server services found.",
    }),
  );
  setHtmlIfChanged(
    clubHost,
    renderServiceCards(auxCards, {
      showActions: true,
      emptyText: "No additional Club3090 services are currently active.",
    }),
  );
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
function runtimeTargetForSummary(runtime) {
  const targetId = String(runtime?.id || runtime?.instance_id || "").trim();
  if (!targetId) return null;
  if (targetId === "GLOBAL") {
    return { id: "GLOBAL", kind: "global", display_name: "Global" };
  }
  return (
    scopeItems().find((row) => String(row?.id || "") === targetId) || {
      id: targetId,
      kind:
        Array.isArray(runtime?.gpu_indices) && runtime.gpu_indices.length > 1
          ? "dual"
          : "single",
      gpu_indices: Array.isArray(runtime?.gpu_indices) ? runtime.gpu_indices.slice() : [],
      display_name: String(runtime?.display_name || targetId),
    }
  );
}
function resolveVariantActionTarget(variant, explicitTargetId = "") {
  const targetId = String(explicitTargetId || "").trim();
  if (!targetId) return scopeTargetForVariant(variant);
  if (targetId === "GLOBAL") return runtimeTargetForSummary({ id: "GLOBAL" });
  const scoped = scopeItems().find((row) => String(row?.id || "") === targetId);
  if (scoped) return scoped;
  const runtime = runtimeStatsRows(lastStatus).find(
    (row) => String(row?.id || row?.instance_id || "") === targetId,
  );
  return runtime ? runtimeTargetForSummary(runtime) : null;
}
function summaryRuntimeEntriesForModel(modelId, modelVariants) {
  const key = String(modelId || "").trim();
  const bySelector = new Map(
    (modelVariants || []).map((variant) => [variantSelector(variant), variant]),
  );
  return runtimeStatsRows(lastStatus)
    .map((runtime) => {
      const selector = String(runtime?.selector || runtime?.mode || "").trim();
      const variant = bySelector.get(selector);
      if (!variant || String(variant?.model_id || "").trim() !== key) return null;
      const target = runtimeTargetForSummary(runtime);
      const targetId = String(runtime?.id || runtime?.instance_id || "").trim();
      return target && targetId
        ? { selector, target, targetId, runtime, variant }
        : null;
    })
    .filter(Boolean);
}
function runtimeEntryForSelector(selector, options = {}) {
  const normalizedSelector = String(selector || "").trim();
  if (!normalizedSelector) return null;
  const includeRunning = options.includeRunning !== false;
  const includeBooting = options.includeBooting !== false;
  const runtime = runtimeStatsRows(lastStatus).find((row) => {
    if (String(row?.selector || row?.mode || "").trim() !== normalizedSelector) return false;
    if (includeRunning && row?.running) return true;
    if (includeBooting && row?.booting) return true;
    return false;
  });
  if (!runtime) return null;
  const target = runtimeTargetForSummary(runtime);
  return target ? { runtime, target } : null;
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
      return { id: "GLOBAL", kind: "dual", display_name: "Global" };
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
function extractDownloadSources(commandText) {
  const text = String(commandText || "").trim();
  if (!text) return [];
  const values = [];
  const seen = new Set();
  const push = (value) => {
    const normalized = String(value || "").trim();
    if (!normalized) return;
    if (seen.has(normalized)) return;
    seen.add(normalized);
    values.push(normalized);
  };
  for (const match of text.matchAll(/\bhttps?:\/\/[^\s"'`|&;()<>]+/gi)) {
    push(match[0]);
  }
  for (const match of text.matchAll(/\bhf\s+download\s+([^\s"'`|&;()<>]+)/gi)) {
    push(match[1]);
  }
  return values;
}
function downloadButtonTitle(commandText) {
  const sources = extractDownloadSources(commandText);
  if (!sources.length) return "Download required assets";
  return `Download source${sources.length === 1 ? "" : "s"}: ${sources.join(" | ")}`;
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
let setupAssistantAnswers = {
  use_case: "coding",
  context_need: "balanced",
  optimize_for: "reliability",
  rollout_style: "safest",
};
function ensurePresetActionModal() {
  if ($("presetActionModal")) return;
  const modal = document.createElement("div");
  modal.id = "presetActionModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card" role="dialog" aria-modal="true" aria-labelledby="presetActionModalTitle"><div class="panel-head"><h2 id="presetActionModalTitle">Confirm Action</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closePresetActionModal()">✕</button></div><div class="preset-help" id="presetActionModalBody">-</div><textarea id="presetActionModalDetail" class="modal-keybox hidden" readonly wrap="soft" spellcheck="false"></textarea><div class="preset-form-actions"><button class="btn blue" onclick="closePresetActionModal()">Cancel</button><button class="btn green" id="presetActionModalConfirm">Continue</button></div><div class="msg" id="presetActionModalMsg"></div></div>`;
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
  modal.innerHTML = `<div class="club-modal-card" id="actionChoiceModalCard" role="dialog" aria-modal="true" aria-labelledby="actionChoiceModalTitle"><div class="panel-head"><h2 id="actionChoiceModalTitle">Choose Action</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeActionChoiceModal()">✕</button></div><div class="preset-help" id="actionChoiceModalBody">-</div><div class="preset-form-actions" id="actionChoiceModalChoices"></div><div id="actionChoiceModalDetails"></div><div class="msg" id="actionChoiceModalMsg"></div></div>`;
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
  if ($("actionChoiceModalDetails")) $("actionChoiceModalDetails").innerHTML = opts.detailsHtml || "";
  $("actionChoiceModalMsg").textContent = "";
  const host = $("actionChoiceModalChoices");
  host.innerHTML = "";
  (opts.choices || []).forEach((choice) => {
    if (choice.hidden) return;
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
function selectedAdminTaskTargetRuntime() {
  const running = runtimeStatsRows(lastStatus).filter(
    (runtime) => runtime && runtime.running,
  );
  if (scopeIsGlobal()) {
    return running.length === 1 ? running[0] : null;
  }
  const target = currentScopeInstance(false);
  if (!target) return null;
  return (
    running.find(
      (runtime) =>
        String(runtime?.id || runtime?.instance_id || "").trim().toUpperCase() ===
        String(target?.id || "").trim().toUpperCase(),
    ) || null
  );
}
function selectedAdminTaskTargetLabel(runtime = null) {
  const target = runtime || selectedAdminTaskTargetRuntime();
  if (!target) return scopeIsGlobal() ? "Global scope" : "the selected scope";
  const targetId = String(target?.id || target?.instance_id || "").trim().toUpperCase();
  if (targetId === "GLOBAL") return "Global Runtime";
  const scoped = scopeItems().find(
    (row) => String(row?.id || "").trim().toUpperCase() === targetId,
  );
  return scoped ? scopeLabel(scoped) : targetId || "the selected runtime";
}
function requireSelectedAdminTaskTarget(actionLabel = "This task") {
  const target = selectedAdminTaskTargetRuntime();
  if (target) return target;
  const message = scopeIsGlobal()
    ? `${actionLabel} can only run from Global scope when exactly one runtime is active.`
    : `${actionLabel} requires the selected scope to be running. Start that container first.`;
  alert(message);
  return null;
}
function promptBenchmarkRun() {
  const target = requireSelectedAdminTaskTarget("Benchmark");
  if (!target) return;
  const label = selectedAdminTaskTargetLabel(target);
  openPresetActionModal({
    title: "Run Benchmark",
    body: `This runs the upstream <code>bash scripts/bench.sh</code> helper against <strong>${escapeHtml(label)}</strong> and streams the full output into Audit Logs.`,
    confirmLabel: "Run Benchmark",
    confirmClass: "blue",
    onConfirm: async () => {
      const instanceId = String(target?.id || target?.instance_id || "");
      await post("/admin/benchmark", { instance_id: instanceId }, `/admin/benchmark ${instanceId || "GLOBAL"}`);
      setAuditMsg(`Benchmark started for ${label}. Output is streaming to Audit Logs.`);
    },
  });
}
function promptReportRun() {
  const target = requireSelectedAdminTaskTarget("Run Report");
  if (!target) return;
  const label = selectedAdminTaskTargetLabel(target);
  openPresetActionModal({
    title: "Run Report",
    body: `This runs the upstream <code>bash scripts/report.sh</code> helper for <strong>${escapeHtml(label)}</strong> and streams the generated report into Audit Logs.`,
    confirmLabel: "Run Report",
    confirmClass: "blue",
    onConfirm: async () => {
      const instanceId = String(target?.id || target?.instance_id || "");
      await post("/admin/run-report", { instance_id: instanceId }, `/admin/run-report ${instanceId || "GLOBAL"}`);
      setAuditMsg(`Run Report started for ${label}. Output is streaming to Audit Logs.`);
    },
  });
}
function promptRebenchRun() {
  const target = requireSelectedAdminTaskTarget("Rebench");
  if (!target) return;
  const label = selectedAdminTaskTargetLabel(target);
  const instanceId = String(target?.id || target?.instance_id || "");
  openActionChoiceModal({
    title: "Run Rebench",
    body: `Choose which rebench tier to run for <strong>${escapeHtml(label)}</strong>. Both variants stream their output into Audit Logs immediately.`,
    choices: [
      {
        label: "Rebench Runtime",
        className: "blue",
        onClick: async () => {
          await post(
            "/admin/rebench",
            { instance_id: instanceId, variant: "runtime" },
            `/admin/rebench runtime ${instanceId || "GLOBAL"}`,
          );
          setAuditMsg(`Rebench Runtime started for ${label}. Output is streaming to Audit Logs.`);
        },
      },
      {
        label: "Rebench Full",
        className: "green",
        onClick: async () => {
          await post(
            "/admin/rebench",
            { instance_id: instanceId, variant: "full" },
            `/admin/rebench full ${instanceId || "GLOBAL"}`,
          );
          setAuditMsg(`Rebench Full started for ${label}. Output is streaming to Audit Logs.`);
        },
      },
    ],
  });
}
async function startUpdateFlow(scope, targetCommit = "", options = {}) {
  if (!options?.skipVersionGuard) {
    const versionInfo = currentRemoteUpdateVersionInfo();
    if (versionInfo.needsConfirmation) {
      promptStaleUpdateConfirmation(scope, targetCommit);
      return;
    }
  }
  const normalized = scope === "club3090" || scope === "club3090-compatible" ? "club3090" : "controller";
  const payload = { scope: normalized };
  if (normalized === "club3090" && targetCommit) payload.target_commit = targetCommit;
  setUpdateUiLocked(true);
  try {
    await post(
      "/admin/update",
      payload,
      `/admin/update ${normalized}`,
    );
    setAuditMsg(
      normalized === "club3090"
        ? "Club-3090 migration launched. Output is streaming to Audit Logs."
        : "Admin script update launched. Output is streaming to Audit Logs.",
    );
  } catch (error) {
    setUpdateUiLocked(false);
    throw error;
  }
}
function promptUpdateRun() {
  const remote = (lastStatus && lastStatus.remote_update) || {};
  const localMeta = (lastStatus && lastStatus.local_installer_metadata) || {};
  const compat = (lastStatus && lastStatus.club3090_compat) || {};
  const supported = compat.supported || {};
  const runningVersion = String(lastStatus?.script_version || "");
  const remoteVersion = String(remote.script_version || localMeta.script_version || "");
  const latestText = formatChangelogText(
    filterChangelogSinceVersion(
      remote.change_log_latest || localMeta.change_log_latest,
      runningVersion,
      remoteVersion,
    ),
    "• No newer latest-change entries than the currently running script version.",
  );
  const releaseText = formatChangelogText(
    filterChangelogSinceVersion(
      remote.change_log_release || localMeta.change_log_release,
      runningVersion,
    ),
    "• No newer major-improvement entries than the currently running script version.",
  );
  openActionChoiceModal({
    title: "Run Update",
    body: "Choose which update flow to launch. The web-panel option refreshes only the control layer. The Club-3090 option runs the full <code>--migrate</code> pass. Both stream their output into Audit Logs right away.",
    detailsHtml: `<div class="update-changelog-block"><div class="update-changelog-title">Change Log</div><div class="update-changelog-subtitle">Latest Changes</div><div class="update-changelog-list">${latestText}</div><div class="update-changelog-subtitle">Major Improvements</div><div class="update-changelog-list">${releaseText}</div></div>`,
    cardClass: "update-choice-card",
    choices: [
      {
        label: "Update Web Panel",
        className: "blue",
        onClick: async () => {
          await startUpdateFlow("controller");
        },
      },
      {
        label: "Migrate to Compatible Club-3090 Version",
        className: "red",
        hidden: !compat.local_repo_newer_than_supported || !String(supported.commit || "").trim(),
        onClick: async () => {
          await startCompatibleMigration();
        },
      },
      {
        label: "Update Club-3090 + Web Panel",
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
    const key = String(variantEffectiveStatusKind(row) || "").trim();
    if (!key) return;
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return [...counts.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(
      ([status, count]) =>
        renderStatusBadgesHtml({ status_kind: status }, { countLabel: count }),
    )
    .join("");
}
function experimentalVariantRows(rows) {
  return sortInventoryVariants(rows).sort((a, b) => {
    const order = (item) => {
      const key = String(variantEffectiveStatusKind(item) || "");
      if (key === "upstream_gated") return 0;
      if (key === "blocked" || key === "hardware_blocked") return 1;
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
function presetLaunchOverridesMap() {
  const rows = lastStatus?.server_config?.preset_launch_overrides;
  return rows && typeof rows === "object" ? rows : {};
}
function variantLaunchSettings(variant) {
  return Array.isArray(variant?.launch_settings) ? variant.launch_settings : [];
}
function normalizePresetLaunchSettingName(name) {
  const raw = String(name || "").trim().toUpperCase();
  if (!raw) return "";
  if (raw === "TEMP") return "TEMPERATURE";
  if (raw === "REPETITION_PENALTY") return "REPEAT_PENALTY";
  return raw;
}
function variantSavedLaunchEnv(variant) {
  const selector = variantSelector(variant);
  const env = presetLaunchOverridesMap()?.[selector]?.env;
  return env && typeof env === "object" ? env : {};
}
function variantSavedCommandText(variant) {
  const selector = variantSelector(variant);
  return String(presetLaunchOverridesMap()?.[selector]?.command_text || "").trim();
}
function resolvePresetLaunchCommandText(commandText, envDefaults = {}, savedEnv = {}) {
  const defaults = envDefaults && typeof envDefaults === "object" ? envDefaults : {};
  const saved = savedEnv && typeof savedEnv === "object" ? savedEnv : {};
  const lookupValue = (key, fallback = "") => {
    const normalizedKey = normalizePresetLaunchSettingName(key);
    const value = saved[normalizedKey] ?? defaults[normalizedKey] ?? fallback;
    return String(value ?? "").trim();
  };
  return String(commandText || "")
    .replace(/\$\{([A-Z][A-Z0-9_]*)(:-|-)([^}]*)\}/g, (_match, key, _operator, fallback) =>
      lookupValue(key, fallback),
    )
    .replace(/\$\{([A-Z][A-Z0-9_]*)\}/g, (_match, key) => lookupValue(key, ""))
    .replace(/\r/g, "")
    .trim();
}
function parsePresetLaunchCommandOption(commandText, optionNames = []) {
  const wanted = new Set(
    (Array.isArray(optionNames) ? optionNames : [optionNames])
      .map((name) => String(name || "").trim())
      .filter(Boolean),
  );
  if (!wanted.size) return "";
  const lines = String(commandText || "")
    .replace(/\r/g, "")
    .split("\n");
  for (const rawLine of lines) {
    const line = String(rawLine || "").trim();
    if (!line) continue;
    for (const option of wanted) {
      if (line.startsWith(`${option}=`)) return line.slice(option.length + 1).trim();
      if (line.startsWith(`${option} `)) return line.slice(option.length + 1).trim();
    }
  }
  return "";
}
function parsePresetLaunchNumericValue(value) {
  const text = String(value || "").trim();
  if (!text) return 0;
  const match = text.match(/^(-?\d+(?:\.\d+)?)([kKmMgG]?)$/);
  if (!match) return Number.parseInt(text.replace(/[_,]/g, ""), 10) || 0;
  const numeric = Number(match[1] || 0);
  if (!Number.isFinite(numeric)) return 0;
  const suffix = String(match[2] || "").toLowerCase();
  const multiplier = suffix === "k" ? 1000 : suffix === "m" ? 1000000 : suffix === "g" ? 1000000000 : 1;
  return Math.max(0, Math.round(numeric * multiplier));
}
function variantLaunchEnvDefaults(variant) {
  const defaults = {};
  variantLaunchSettings(variant).forEach((row) => {
    const key = normalizePresetLaunchSettingName(row?.name || "");
    const value = String(row?.default || "").trim();
    if (key && value) defaults[key] = value;
  });
  return defaults;
}
function variantResolvedLaunchEnv(variant) {
  return {
    ...variantLaunchEnvDefaults(variant),
    ...variantSavedLaunchEnv(variant),
  };
}
function variantResolvedLaunchCommandText(variant) {
  const defaults = variantLaunchEnvDefaults(variant);
  const savedEnv = variantSavedLaunchEnv(variant);
  return resolvePresetLaunchCommandText(
    variantSavedCommandText(variant) || String(variant?.default_engine_switches || ""),
    defaults,
    savedEnv,
  );
}
function variantEffectiveLaunchMetadata(variant) {
  const env = variantResolvedLaunchEnv(variant);
  const commandText = variantResolvedLaunchCommandText(variant);
  const ctxSizeTokens =
    parsePresetLaunchNumericValue(env.CTX_SIZE || env.MAX_MODEL_LEN) ||
    parsePresetLaunchNumericValue(
      parsePresetLaunchCommandOption(commandText, ["--max-model-len", "--ctx-size", "-c"]),
    ) ||
    parsePresetLaunchNumericValue(variant?.max_model_len);
  const servedModelName = String(
    env.MODEL_NAME || parsePresetLaunchCommandOption(commandText, ["--served-model-name"]) || "",
  ).trim();
  return {
    ctx_size_tokens: ctxSizeTokens > 0 ? ctxSizeTokens : 0,
    served_model_name: servedModelName,
  };
}
function ensurePresetLaunchSettingsModal() {
  if ($("presetLaunchSettingsModal")) return;
  const modal = document.createElement("div");
  modal.id = "presetLaunchSettingsModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card preset-launch-settings-modal-card" role="dialog" aria-modal="true" aria-labelledby="presetLaunchSettingsTitle"><div class="panel-head"><h2 id="presetLaunchSettingsTitle">Preset Launch Settings</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closePresetLaunchSettingsModal()">✕</button></div><div class="preset-help" id="presetLaunchSettingsHint"></div><div id="presetLaunchSettingsGrid" class="preset-launch-settings-grid"></div><label class="preset-launch-settings-raw-label custom-model-engine-switches-label">Custom engine switches<textarea id="presetLaunchCommandText" class="preset-launch-settings-raw" placeholder="One engine argument per line." spellcheck="false"></textarea></label><label class="preset-launch-settings-raw-label">Additional env overrides<textarea id="presetLaunchExtraEnv" class="preset-launch-settings-raw" placeholder="NAME=value&#10;OTHER_FLAG=1"></textarea></label><div class="preset-help preset-launch-settings-note">These values persist globally per preset and are applied automatically when you launch that preset. Host-managed values like <code>PORT</code>, <code>MODEL_DIR</code>, and GPU selectors stay under server control.</div><div class="preset-form-actions"><button class="btn blue" onclick="closePresetLaunchSettingsModal()">Cancel</button><button class="btn red" onclick="resetPresetLaunchSettingsModal()">Reset</button><button class="btn green" onclick="applyPresetLaunchSettingsModal()">Apply</button></div><div class="msg" id="presetLaunchSettingsMsg"></div></div>`;
  document.body.appendChild(modal);
}
function setPresetLaunchSettingsMsg(text, tone = "warning") {
  setElementMsg("presetLaunchSettingsMsg", text || "", tone);
}
function renderPresetLaunchSettingField(row, value, index) {
  const key = normalizePresetLaunchSettingName(row?.name || "");
  const type = String(row?.type || "string").trim().toLowerCase();
  const label = String(row?.label || key || `Setting ${index + 1}`);
  const description = String(row?.description || "").trim();
  const defaultValue = String(row?.default || "").trim();
  const fieldId = `presetLaunchSetting${index}`;
  const note = [description, defaultValue ? `Default: ${defaultValue}` : ""].filter(Boolean).join(" ");
  if (type === "boolean") {
    return `<label class="preset-launch-settings-field"><span>${escapeHtml(label)}</span><select id="${fieldId}" data-setting-name="${escapeHtml(key)}" data-setting-type="${escapeHtml(type)}" data-setting-default="${escapeHtml(defaultValue)}"><option value="">Use compose default</option><option value="true" ${String(value || "").toLowerCase() === "true" || String(value || "").toLowerCase() === "on" ? "selected" : ""}>true</option><option value="false" ${String(value || "").toLowerCase() === "false" || String(value || "").toLowerCase() === "off" ? "selected" : ""}>false</option></select>${note ? `<small>${escapeHtml(note)}</small>` : ""}</label>`;
  }
  const inputType = type === "integer" || type === "number" ? "number" : "text";
  const stepAttr = type === "integer" ? ' step="1"' : type === "number" ? ' step="any"' : "";
  return `<label class="preset-launch-settings-field"><span>${escapeHtml(label)}</span><input id="${fieldId}" type="${inputType}"${stepAttr} data-setting-name="${escapeHtml(key)}" data-setting-type="${escapeHtml(type)}" data-setting-default="${escapeHtml(defaultValue)}" value="${escapeHtml(value || "")}" placeholder="${escapeHtml(defaultValue || "")}" />${note ? `<small>${escapeHtml(note)}</small>` : ""}</label>`;
}
function openPresetLaunchSettingsModal(selector) {
  const variant = inventoryVariants().find(
    (item) => variantSelector(item) === selector || item?.variant_id === selector,
  );
  if (!variant) {
    alert("Preset not found in runtime inventory.");
    return;
  }
  ensurePresetLaunchSettingsModal();
  const settings = variantLaunchSettings(variant);
  const defaults = variantLaunchEnvDefaults(variant);
  const savedEnv = variantSavedLaunchEnv(variant);
  const savedCommandText = variantSavedCommandText(variant);
  const knownKeys = new Set(Object.keys(defaults));
  const grid = $("presetLaunchSettingsGrid");
  const nextHtml = settings.length
    ? settings
        .map((row, index) => {
          const key = normalizePresetLaunchSettingName(row?.name || "");
          const current = savedEnv[key] ?? defaults[key] ?? "";
          return renderPresetLaunchSettingField(row, current, index);
        })
        .join("")
    : `<div class="preset-help">This preset does not advertise structured launch fields in its compose header yet. You can still use the additional env override box below for any supported upstream env variables.</div>`;
  setHtmlIfChanged(grid, nextHtml);
  $("presetLaunchExtraEnv").value = Object.entries(savedEnv)
    .filter(([key]) => !knownKeys.has(String(key || "").trim().toUpperCase()))
    .map(([key, value]) => `${key}=${value}`)
    .join("\n");
  $("presetLaunchCommandText").value =
    savedCommandText ||
    resolvePresetLaunchCommandText(String(variant?.default_engine_switches || ""), defaults, savedEnv);
  $("presetLaunchSettingsModal").dataset.selector = variantSelector(variant);
  $("presetLaunchSettingsHint").innerHTML = `Configure launch-time overrides for <code>${escapeHtml(variantDisplayLabel(variant))}</code>. The saved values are selector-scoped and reused across tabs, scopes, and reloads.`;
  setPresetLaunchSettingsMsg("");
  $("presetLaunchSettingsModal").classList.remove("hidden");
}
function closePresetLaunchSettingsModal() {
  $("presetLaunchSettingsModal")?.classList.add("hidden");
}
function collectPresetLaunchSettingsModalEnv() {
  const env = {};
  document.querySelectorAll("#presetLaunchSettingsGrid [data-setting-name]").forEach((node) => {
    const key = normalizePresetLaunchSettingName(node.getAttribute("data-setting-name") || "");
    const type = String(node.getAttribute("data-setting-type") || "string").trim().toLowerCase();
    const defaultValue = String(node.getAttribute("data-setting-default") || "").trim();
    let value = String(node.value || "").trim();
    if (!key || !value) return;
    let normalizedDefault = defaultValue;
    if (type === "integer") {
      if (!/^-?\d+$/.test(value)) throw new Error(`${key} must be a whole number.`);
      value = String(Number.parseInt(value, 10));
      if (/^-?\d+$/.test(defaultValue)) normalizedDefault = String(Number.parseInt(defaultValue, 10));
    } else if (type === "number") {
      if (!Number.isFinite(Number(value))) throw new Error(`${key} must be a valid number.`);
      value = String(Number(value));
      if (defaultValue !== "" && Number.isFinite(Number(defaultValue))) normalizedDefault = String(Number(defaultValue));
    } else if (type === "boolean") {
      const lowered = value.toLowerCase();
      if (!["true", "false", "on", "off", "1", "0", "yes", "no"].includes(lowered))
        throw new Error(`${key} must be true or false.`);
      value = ["true", "on", "1", "yes"].includes(lowered) ? "true" : "false";
      if (defaultValue) {
        const defaultLowered = defaultValue.toLowerCase();
        normalizedDefault = ["true", "on", "1", "yes"].includes(defaultLowered) ? "true" : "false";
      }
    }
    if (normalizedDefault && value === normalizedDefault) return;
    env[key] = value;
  });
  String($("presetLaunchExtraEnv").value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const idx = line.indexOf("=");
      if (idx <= 0) throw new Error(`Invalid env override: ${line}`);
      const key = normalizePresetLaunchSettingName(line.slice(0, idx));
      const value = line.slice(idx + 1).trim();
      if (!/^[A-Z][A-Z0-9_]*$/.test(key)) throw new Error(`Invalid env name: ${key || line}`);
      if (!value) throw new Error(`Missing value for ${key}.`);
      env[key] = value;
    });
  return {
    env,
    command_text: String($("presetLaunchCommandText")?.value || "").replace(/\r/g, "").trim(),
  };
}
async function savePresetLaunchOverrides(selector, payload) {
  const nextMap = { ...presetLaunchOverridesMap() };
  const env = payload && typeof payload === "object" ? payload.env || {} : {};
  const commandText = payload && typeof payload === "object" ? String(payload.command_text || "").trim() : "";
  if ((env && Object.keys(env).length) || commandText) {
    nextMap[selector] = {};
    if (env && Object.keys(env).length) nextMap[selector].env = env;
    if (commandText) nextMap[selector].command_text = commandText;
  } else delete nextMap[selector];
  const responsePayload = await post(
    "/admin/users",
    {
      action: "save_server_config",
      preset_launch_overrides: nextMap,
    },
    `/admin/users save_server_config preset_launch_overrides ${selector}`,
    { silentSuccess: true },
  );
  if (!lastStatus) lastStatus = {};
  lastStatus.server_config = responsePayload?.server_config || {
    ...(lastStatus.server_config || {}),
    preset_launch_overrides: nextMap,
  };
}
async function applyPresetLaunchSettingsModal() {
  try {
    const selector = String($("presetLaunchSettingsModal")?.dataset?.selector || "").trim();
    if (!selector) throw new Error("Preset selector is missing.");
    await savePresetLaunchOverrides(selector, collectPresetLaunchSettingsModalEnv());
    closePresetLaunchSettingsModal();
    renderDynamicPresetModels();
  } catch (e) {
    setPresetLaunchSettingsMsg(messageText(e), "error");
  }
}
async function resetPresetLaunchSettingsModal() {
  try {
    const selector = String($("presetLaunchSettingsModal")?.dataset?.selector || "").trim();
    if (!selector) throw new Error("Preset selector is missing.");
    await savePresetLaunchOverrides(selector, { env: {}, command_text: "" });
    closePresetLaunchSettingsModal();
    renderDynamicPresetModels();
  } catch (e) {
    setPresetLaunchSettingsMsg(messageText(e), "error");
  }
}
let presetTpsLongPressTimer = null;
let presetTpsLongPressConsumed = false;
function presetTpsStatsMap() {
  const rows = lastStatus?.preset_tps_stats;
  return rows && typeof rows === "object" ? rows : {};
}
function presetTpsStatsForSelector(selector) {
  return presetTpsStatsMap()[String(selector || "").trim()] || {};
}
function formatPresetTpsValue(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) && number > 0 ? formatNumber(number, 2) : "-";
}
function formatDiskBytes(bytes) {
  let value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  const digits = index >= 3 ? 1 : index === 0 ? 0 : 1;
  return `${value.toFixed(digits)} ${units[index]}`;
}
function variantResourceRows(variant) {
  return Array.isArray(variant?.resources)
    ? variant.resources.filter(
        (row) =>
          row &&
          row.exists &&
          !/[/\\]\.cache[/\\]huggingface[/\\]download(?:[/\\]|$)/i.test(String(row.path || "")),
      )
    : [];
}
function variantResourceIdentityKey(row) {
  return String(row?.identity_key || row?.path || "").trim();
}
function presetResourceDisplayLabel(row) {
  return String(row?.display_label || row?.label || row?.path || row?.role || "resource");
}
function presetResourceRowIsProjector(row) {
  const role = String(row?.role || "").trim().toLowerCase();
  const path = String(row?.path || "").replace(/\\/g, "/");
  const name = path.split("/").pop() || String(row?.label || "");
  return role === "projector" || /^mmproj.*\.gguf$/i.test(name);
}
function presetResourceMarkerKind(row) {
  if (presetResourceRowIsProjector(row)) return "projector";
  const role = String(row?.role || "").trim().toLowerCase();
  if (role === "draft") {
    return "speculative";
  }
  return "solid";
}
function hashTextToUint(text) {
  let hash = 2166136261;
  const source = String(text || "");
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}
const RESOURCE_MARKER_BASE_COLORS = [
  "#e6194b", // red
  "#2ca02c", // green
  "#0066ff", // blue
  "#ffe119", // yellow
  "#d100d1", // magenta
  "#00bcd4", // cyan
  "#ff7f00", // orange
  "#6a3d9a", // purple
  "#000000", // black
  "#ffffff", // white
  "#808080", // neutral gray
  "#8b4513", // brown
  "#7fff00", // lime
  "#008080", // teal
  "#800000", // maroon
  "#000075", // navy
  "#ff69b4", // pink
  "#c49a00", // gold
  "#386641", // forest
  "#4cc9f0", // sky
  "#ff5f1f", // vermilion
  "#9d4edd", // violet
  "#d4ff00", // chartreuse
  "#00a86b", // jade
  "#a63a50", // wine
  "#f2e8cf", // cream
  "#36454f", // charcoal
  "#b15928", // umber
  "#1f78b4", // steel blue
  "#fb9a99", // salmon
  "#bcf60c", // neon green
  "#fabebe", // rose
  "#46f0f0", // aqua
  "#f032e6", // hot magenta
  "#e6beff", // lavender
  "#808000", // olive
  "#ffd8b1", // peach
  "#aaffc3", // mint
  "#0d3b66", // deep sea
  "#f4d35e", // mustard
  "#ee964b", // copper
  "#1b998b", // blue green
  "#2d3047", // ink
  "#fffd82", // lemon
  "#57cc99", // seafoam
  "#22577a", // slate blue
  "#7209b7", // royal purple
  "#582f0e", // dark brown
  "#a4ac86", // sage
  "#ced4da", // light gray
  "#495057", // dark gray
  "#d00000", // crimson
  "#3f88c5", // azure
  "#032b43", // midnight
];
const RESOURCE_MARKER_MIN_COLOR_DISTANCE = 0.1;
function parseHexColor(color) {
  const text = String(color || "").trim().replace(/^#/, "");
  if (!/^[0-9a-fA-F]{6}$/.test(text)) return null;
  return {
    r: parseInt(text.slice(0, 2), 16),
    g: parseInt(text.slice(2, 4), 16),
    b: parseInt(text.slice(4, 6), 16),
  };
}
function hslToHex(hue, saturation, lightness) {
  const h = ((((Number(hue) || 0) % 360) + 360) % 360) / 360;
  const s = Math.max(0, Math.min(1, (Number(saturation) || 0) / 100));
  const l = Math.max(0, Math.min(1, (Number(lightness) || 0) / 100));
  const toRgb = (p, q, tValue) => {
    let t = tValue;
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  let r;
  let g;
  let b;
  if (s === 0) {
    r = g = b = l;
  } else {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = toRgb(p, q, h + 1 / 3);
    g = toRgb(p, q, h);
    b = toRgb(p, q, h - 1 / 3);
  }
  return `#${[r, g, b]
    .map((value) => Math.round(value * 255).toString(16).padStart(2, "0"))
    .join("")}`;
}
function colorDistance(left, right) {
  const a = parseHexColor(left);
  const b = parseHexColor(right);
  if (!a || !b) return 1;
  const dr = (a.r - b.r) / 255;
  const dg = (a.g - b.g) / 255;
  const db = (a.b - b.b) / 255;
  return Math.sqrt(dr * dr + dg * dg + db * db) / Math.sqrt(3);
}
function resourceMarkerColorIsDistinct(color, usedColors) {
  return usedColors.every((used) => colorDistance(color, used) >= RESOURCE_MARKER_MIN_COLOR_DISTANCE);
}
function generatedResourceMarkerColor(seed, attempt) {
  const hue = (Number(seed || 0) + attempt * 137.508) % 360;
  const saturationSteps = [92, 74, 58, 38, 18, 100, 48];
  const lightnessSteps = [46, 62, 34, 78, 22, 88, 52];
  const saturation = saturationSteps[attempt % saturationSteps.length];
  const lightness = lightnessSteps[Math.floor(attempt / saturationSteps.length) % lightnessSteps.length];
  return hslToHex(hue, saturation, lightness);
}
function resourceColorKeysSignature() {
  return inventoryVariants()
    .flatMap((variant) => variantResourceRows(variant).map((row) => variantResourceIdentityKey(row)))
    .map((key) => String(key || "").trim())
    .filter(Boolean)
    .sort()
    .join("|");
}
function chooseResourceMarkerColor(key, usedColors, preferredIndex = 0) {
  const seed = hashTextToUint(key);
  const palette = RESOURCE_MARKER_BASE_COLORS;
  for (let offset = 0; offset < palette.length; offset += 1) {
    const color = palette[(Math.max(0, Number(preferredIndex) || 0) + offset) % palette.length];
    if (resourceMarkerColorIsDistinct(color, usedColors)) return color;
  }
  let bestColor = generatedResourceMarkerColor(seed, 0);
  let bestDistance = -1;
  for (let attempt = 0; attempt < 360; attempt += 1) {
    const color = generatedResourceMarkerColor(seed, attempt);
    const nearest = usedColors.length ? Math.min(...usedColors.map((used) => colorDistance(color, used))) : 1;
    if (nearest >= RESOURCE_MARKER_MIN_COLOR_DISTANCE) return color;
    if (nearest > bestDistance) {
      bestDistance = nearest;
      bestColor = color;
    }
  }
  return bestColor;
}
function resourceColorAssignmentMap() {
  const signature = resourceColorKeysSignature();
  const map = new Map();
  const usedColors = [];
  [...new Set(signature.split("|").filter(Boolean))].forEach((key) => {
    const color = chooseResourceMarkerColor(key, usedColors, usedColors.length);
    map.set(key, color);
    usedColors.push(color);
  });
  return map;
}
function resourceColorForKey(key) {
  const cleanKey = String(key || "").trim();
  if (!cleanKey) return "#7aa2c8";
  return resourceColorAssignmentMap().get(cleanKey) || chooseResourceMarkerColor(cleanKey, []);
}
let presetResourceIdentityCacheSignature = "";
let presetResourceIdentityCacheValue = new Map();
function inventoryResourceIdentityMap() {
  const signature = inventoryVariants()
    .map((variant) => {
      const selector = variantSelector(variant) || String(variant?.variant_id || "").trim();
      const resources = variantResourceRows(variant);
      return `${selector}:${resources
        .map((row) => `${variantResourceIdentityKey(row)}:${Number(row?.size_bytes || 0)}`)
        .join("|")}`;
    })
    .join("||");
  if (signature === presetResourceIdentityCacheSignature) {
    return presetResourceIdentityCacheValue;
  }
  const map = new Map();
  inventoryVariants().forEach((variant) => {
    const selector = variantSelector(variant) || String(variant?.variant_id || "").trim();
    variantResourceRows(variant).forEach((row) => {
      const key = variantResourceIdentityKey(row);
      if (!key) return;
      if (!map.has(key)) {
        map.set(key, {
          selectors: new Set(),
          paths: new Set(),
        });
      }
      const entry = map.get(key);
      if (selector) entry.selectors.add(selector);
      if (row?.path) entry.paths.add(String(row.path));
    });
  });
  presetResourceIdentityCacheSignature = signature;
  presetResourceIdentityCacheValue = map;
  return map;
}
function presetResourceMarkerTitle(row, usageEntry) {
  const label = presetResourceDisplayLabel(row);
  const size = formatDiskBytes(row?.size_bytes || 0);
  const sharedCount = usageEntry ? usageEntry.selectors.size : 0;
  return sharedCount > 1
    ? `${label} • ${size} • shared by ${sharedCount} presets`
    : `${label} • ${size}`;
}
function renderPresetDiskResourceMarkers(variant) {
  const resources = variantResourceRows(variant);
  if (!resources.length) return "";
  const usageMap = inventoryResourceIdentityMap();
  const sorted = [...resources].sort((a, b) => {
    const aProjector = presetResourceRowIsProjector(a);
    const bProjector = presetResourceRowIsProjector(b);
    if (aProjector !== bProjector) return aProjector ? 1 : -1;
    return presetResourceDisplayLabel(a).localeCompare(presetResourceDisplayLabel(b));
  });
  return `<span class="preset-disk-markers">${sorted
    .map((row) => {
      const key = variantResourceIdentityKey(row) || `${row?.path || row?.label || ""}`;
      const color = resourceColorForKey(key);
      const usageEntry = usageMap.get(key);
      const markerKind = presetResourceMarkerKind(row);
      const hollow = markerKind !== "solid";
      return `<span class="preset-disk-marker${hollow ? " hollow" : ""}${markerKind === "speculative" ? " diamond" : ""}" title="${escapeHtml(presetResourceMarkerTitle(row, usageEntry))}" style="--preset-resource-color:${escapeHtml(color)}"></span>`;
    })
    .join("")}</span>`;
}
function renderPresetDiskLabel(variant) {
  const size = Number(variant?.resource_size_bytes || 0);
  const cacheSize = Number(variant?.cache_size_bytes || 0);
  const count = Number(variant?.resource_count || 0);
  const cacheCount = Number(variant?.cache_count || 0);
  const title = count
    ? `${count} downloaded resource${count === 1 ? "" : "s"} and ${cacheCount} runtime cache${cacheCount === 1 ? "" : "s"} associated with this preset.`
    : "No downloaded resources are currently associated with this preset.";
  return `<span class="preset-disk-label" title="${escapeHtml(title)}">${renderPresetDiskResourceMarkers(variant)}<span>Disk: ${escapeHtml(formatResourcePlusCacheBytes(size, cacheSize))}</span></span>`;
}
function formatResourcePlusCacheBytes(resourceBytes = 0, cacheBytes = 0) {
  return `${formatDiskBytes(resourceBytes)} + ${formatDiskBytes(cacheBytes)}`;
}
function renderPresetTpsLabel(selector) {
  const key = String(selector || "").trim();
  const stats = presetTpsStatsForSelector(key);
  const maxTps = formatPresetTpsValue(stats.max_tps);
  const avgTps = formatPresetTpsValue(stats.avg_tps);
  const recentCount = Number(stats.recent_sample_count || 0);
  const maxCount = Number(stats.max_sample_count || 0);
  const title = `Max uses the top ${maxCount || 0} saved TPS sample${maxCount === 1 ? "" : "s"}; Avg uses the last ${recentCount || 0} inference${recentCount === 1 ? "" : "s"}. Shift-click or long press to clear.`;
  return `<button type="button" class="preset-tps-label" title="${escapeHtml(title)}" aria-label="TPS history for ${escapeHtml(key)}" onpointerdown="beginPresetTpsLabelPress(event,'${escapeJs(key)}')" onpointerup="cancelPresetTpsLabelPress()" onpointerleave="cancelPresetTpsLabelPress()" onpointercancel="cancelPresetTpsLabelPress()" onclick="handlePresetTpsLabelClick(event,'${escapeJs(key)}')"><span>Max. TPS: ${escapeHtml(maxTps)}</span><span class="preset-tps-separator">·</span><span>Avg. TPS: ${escapeHtml(avgTps)}</span></button>`;
}
function renderPresetCacheClearButton(variant, disabled = false) {
  const selector = variantSelector(variant);
  if (!selector) return "";
  return renderIconButton({
    title: `Clear runtime caches for ${variantDisplayLabel(variant)}`,
    action: `promptClearPresetCaches('${escapeJs(selector)}')`,
    icon: "delete",
    className: "variant-cache-clear-btn",
    disabled,
  });
}
function renderVariantSettingsCluster(variant, disableCacheClear = false) {
  const selector = variantSelector(variant);
  const visibilityButton = renderHiddenPresetToggleIcon(variant, false);
  const cacheButton = renderPresetCacheClearButton(variant, disableCacheClear);
  const settingsButton = renderIconButton({
    title: "Launch settings",
    action: `openPresetLaunchSettingsModal('${escapeJs(selector)}')`,
    icon: "gear",
    className: "variant-settings-btn",
  });
  return `<span class="variant-settings-cluster">${renderPresetDiskLabel(variant)}${renderPresetTpsLabel(selector)}${visibilityButton}${cacheButton}${settingsButton}</span>`;
}
function renderPresetResourceDeleteButton(variant, disabled = false) {
  const selector = variantSelector(variant);
  const hasResources = Number(variant?.resource_size_bytes || 0) > 0;
  if (!selector || !hasResources) return "";
  const title = hasResources
    ? `Clear downloaded resources for ${variantDisplayLabel(variant)}`
    : "No downloaded resources found for this preset";
  return `<button class="btn red preset-resource-delete-btn" ${disabled ? "disabled" : ""} title="${escapeHtml(title)}" onclick="promptDeletePresetResources('${escapeJs(selector)}')">Clear Resources</button>`;
}
async function promptDeletePresetResources(selector) {
  const key = String(selector || "").trim();
  const variant = inventoryVariants().find((item) => variantSelector(item) === key || item?.variant_id === key);
  if (!variant) {
    alert("Preset not found in runtime inventory.");
    return;
  }
  let plan = null;
  try {
    plan = await post(
      "/admin/model-resources/plan",
      { selector: key, variant_id: variant.variant_id },
      `/admin/model-resources/plan ${key}`,
      { silentSuccess: true },
    );
  } catch (error) {
    alert(messageText(error));
    return;
  }
  const resources = (Array.isArray(plan?.resources) ? plan.resources : []).filter((row) => row?.exists);
  if (!resources.length) {
    openPresetActionModal({
      title: "Clear Preset Resources",
      body: `No downloaded resources were found for <code>${escapeHtml(variantDisplayLabel(variant))}</code>.`,
      confirmLabel: "Close",
      confirmClass: "blue",
      onConfirm: async () => {},
    });
    return;
  }
  const total = Number(plan?.resource_size_bytes || 0);
  const cacheTotal = Number(variant?.cache_size_bytes || 0);
  const rowsHtml = resources
    .map(
      (row) =>
        `<div class="resource-delete-row"><code>${escapeHtml(row.path || "")}</code><span>${escapeHtml(formatDiskBytes(row.size_bytes || 0))}</span></div>`,
    )
    .join("");
  openActionChoiceModal({
    title: "Clear Preset Resources",
    body: `<div>Clear downloaded resources for <code>${escapeHtml(variantDisplayLabel(variant))}</code>?</div><div class="preset-help resource-delete-summary">${escapeHtml(formatResourcePlusCacheBytes(total, cacheTotal))} is associated with this preset.</div>`,
    detailsHtml: `<div class="resource-delete-list">${rowsHtml}</div>`,
    choices: [
      {
        label: "Cancel",
        className: "blue",
        onClick: async () => {},
      },
      {
        label: "Delete Caches",
        className: "orange",
        hidden: cacheTotal <= 0,
        onClick: async () => {
          await post(
            "/admin/preset-caches/delete",
            { selector: key, variant_id: variant.variant_id },
            `/admin/preset-caches/delete ${key}`,
          );
          await refreshStatus({ force: true });
          renderDynamicPresetModels();
        },
      },
      {
        label: "Delete Model",
        className: "red",
        onClick: async () => {
      const payload = await post(
        "/admin/model-resources/delete",
        { selector: key, variant_id: variant.variant_id },
        `/admin/model-resources/delete ${key}`,
      );
      if (payload?.runtime_inventory) {
        if (!lastStatus) lastStatus = {};
        lastStatus.runtime_inventory = payload.runtime_inventory;
        lastStatus.models = payload.models || payload.runtime_inventory.models || [];
        lastStatus.variants = payload.variants || payload.runtime_inventory.variants || [];
      }
      await refreshStatus({ force: true });
      renderDynamicPresetModels();
        },
      },
      {
        label: "Delete Model + Caches",
        className: "rose",
        onClick: async () => {
          const payload = await post(
            "/admin/model-resources/delete-with-caches",
            { selector: key, variant_id: variant.variant_id },
            `/admin/model-resources/delete-with-caches ${key}`,
          );
          if (payload?.runtime_inventory) {
            if (!lastStatus) lastStatus = {};
            lastStatus.runtime_inventory = payload.runtime_inventory;
            lastStatus.models = payload.models || payload.runtime_inventory.models || [];
            lastStatus.variants = payload.variants || payload.runtime_inventory.variants || [];
          }
          await refreshStatus({ force: true });
          renderDynamicPresetModels();
        },
      },
    ],
  });
}
async function promptClearPresetCaches(selector) {
  const key = String(selector || "").trim();
  const variant = inventoryVariants().find((item) => variantSelector(item) === key || item?.variant_id === key);
  if (!variant) {
    alert("Preset not found in runtime inventory.");
    return;
  }
  let plan = null;
  try {
    plan = await post(
      "/admin/preset-caches/plan",
      { selector: key, variant_id: variant.variant_id },
      `/admin/preset-caches/plan ${key}`,
      { silentSuccess: true },
    );
  } catch (error) {
    alert(messageText(error));
    return;
  }
  const caches = (Array.isArray(plan?.caches) ? plan.caches : []).filter((row) => row?.exists);
  if (!caches.length) {
    openPresetActionModal({
      title: "Clear Preset Caches",
      body: `No runtime caches were found for <code>${escapeHtml(variantDisplayLabel(variant))}</code>.`,
      confirmLabel: "Close",
      confirmClass: "blue",
      onConfirm: async () => {},
    });
    return;
  }
  const total = Number(plan?.cache_size_bytes || 0);
  const rowsHtml = caches
    .map(
      (row) =>
        `<div class="resource-delete-row"><code>${escapeHtml(row.path || "")}</code><span>${escapeHtml(formatDiskBytes(row.size_bytes || 0))}</span></div>`,
    )
    .join("");
  openPresetActionModal({
    title: "Clear Preset Caches",
    body: `<div>Clear runtime/build caches for <code>${escapeHtml(variantDisplayLabel(variant))}</code>?</div><div class="preset-help resource-delete-summary">${escapeHtml(formatDiskBytes(total))} will be reclaimed and rebuilt on the next launch.</div><div class="resource-delete-list">${rowsHtml}</div>`,
    confirmLabel: "Clear Caches",
    confirmClass: "red",
    onConfirm: async () => {
      await post(
        "/admin/preset-caches/delete",
        { selector: key, variant_id: variant.variant_id },
        `/admin/preset-caches/delete ${key}`,
      );
      await refreshStatus({ force: true });
      renderDynamicPresetModels();
    },
  });
}
async function promptDeleteResourcePaths(paths, label = "resource", selectors = []) {
  const cleanPaths = [...new Set((paths || []).map((path) => String(path || "").trim()).filter(Boolean))];
  const cleanSelectors = [...new Set((selectors || []).map((selector) => String(selector || "").trim()).filter(Boolean))];
  if (!cleanPaths.length) return;
  const matchingRows = inventoryResourceManagerRows()
    .filter((entry) => cleanPaths.includes(String(entry.path || "")) || entry.usages.some(({ resource }) => cleanPaths.includes(String(resource?.path || ""))));
  const total = matchingRows.reduce((sum, entry) => sum + Number(entry.sizeBytes || 0), 0);
  const cacheTotal = matchingRows.reduce((sum, entry) => sum + Number(entry.cacheSizeBytes || 0), 0);
  const rowsHtml = cleanPaths
    .map((path) => `<div class="resource-delete-row"><code>${escapeHtml(path)}</code></div>`)
    .join("");
  openActionChoiceModal({
    title: "Clear Model Resource",
    body: `<div>Clear shared resource <code>${escapeHtml(label || "resource")}</code>?</div><div class="preset-help resource-delete-summary">${escapeHtml(formatResourcePlusCacheBytes(total || 0, cacheTotal || 0))} is associated with this resource.</div>`,
    detailsHtml: `<div class="resource-delete-list">${rowsHtml}</div>`,
    choices: [
      {
        label: "Cancel",
        className: "blue",
        onClick: async () => {},
      },
      {
        label: "Delete Caches",
        className: "orange",
        hidden: cacheTotal <= 0 || !cleanSelectors.length,
        onClick: async () => {
          for (const selector of cleanSelectors) {
            await post(
              "/admin/preset-caches/delete",
              { selector },
              `/admin/preset-caches/delete ${selector}`,
              { silentSuccess: true },
            );
          }
          await refreshStatus({ force: true });
          renderDynamicPresetModels();
        },
      },
      {
        label: "Delete Model",
        className: "red",
        onClick: async () => {
      const payload = await post(
        "/admin/model-resources/delete",
        { paths: cleanPaths },
        `/admin/model-resources/delete ${cleanPaths.length} path(s)`,
      );
      if (payload?.runtime_inventory) {
        if (!lastStatus) lastStatus = {};
        lastStatus.runtime_inventory = payload.runtime_inventory;
        lastStatus.models = payload.models || payload.runtime_inventory.models || [];
        lastStatus.variants = payload.variants || payload.runtime_inventory.variants || [];
      }
      await refreshStatus({ force: true });
      renderDynamicPresetModels();
        },
      },
      {
        label: "Delete Model + Caches",
        className: "rose",
        onClick: async () => {
          const payload = await post(
            "/admin/model-resources/delete-with-caches",
            { paths: cleanPaths, selectors: cleanSelectors },
            `/admin/model-resources/delete-with-caches ${cleanPaths.length} path(s)`,
          );
          if (payload?.runtime_inventory) {
            if (!lastStatus) lastStatus = {};
            lastStatus.runtime_inventory = payload.runtime_inventory;
            lastStatus.models = payload.models || payload.runtime_inventory.models || [];
            lastStatus.variants = payload.variants || payload.runtime_inventory.variants || [];
          }
          await refreshStatus({ force: true });
          renderDynamicPresetModels();
        },
      },
    ],
  });
}
function variantSourceRepoCandidates(variant) {
  const values = [];
  for (const repoId of Array.isArray(variant?.source_repo_ids) ? variant.source_repo_ids : []) {
    values.push(String(repoId || "").trim());
  }
  const installCommand = String(variant?.install_command || "");
  const hfMatches = installCommand.matchAll(/\bhf\s+download\s+([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)/g);
  for (const match of hfMatches) values.push(String(match[1] || "").trim());
  const slug = String(variant?.slug || "").trim();
  if (slug.includes("/")) values.push(slug);
  return [...new Set(values.filter(Boolean))];
}
function variantPrimaryRepoUrl(variant) {
  const repo = variantSourceRepoCandidates(variant)[0];
  return repo ? `https://huggingface.co/${repo}` : "";
}
function huggingFaceLogoSvg() {
  return '<span class="resource-hf-emoji" aria-hidden="true">🤗</span>';
}
function resourceUsageState(variant) {
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
  const installing = (Array.isArray(lastStatus?.model_install_jobs) ? lastStatus.model_install_jobs : []).find(
    (job) =>
      job &&
      job.active &&
      String(job.model_id || "") === String(variant?.model_id || "") &&
      String(job.variant_id || "") === String(variant?.variant_id || ""),
  );
  return { selector, target, targetId, active, switching, failed, installing };
}
function inventoryResourceManagerRows() {
  const map = new Map();
  inventoryVariants().forEach((variant) => {
    variantResourceRows(variant).forEach((resource) => {
      const key = variantResourceIdentityKey(resource);
      if (!key) return;
      if (!map.has(key)) {
        map.set(key, {
          key,
          label: presetResourceDisplayLabel(resource),
          path: String(resource?.path || ""),
          kind: String(resource?.kind || ""),
          role: String(resource?.role || ""),
          sizeBytes: Number(resource?.size_bytes || 0),
          cacheSizeBytes: 0,
          cacheSelectors: new Set(),
          hollow: presetResourceMarkerKind(resource) !== "solid",
          usages: [],
          selectors: new Set(),
          repos: new Set(),
          models: new Set(),
        });
      }
      const entry = map.get(key);
      entry.sizeBytes = Math.max(entry.sizeBytes, Number(resource?.size_bytes || 0));
      if (!entry.path || String(resource?.path || "").length < entry.path.length) {
        entry.path = String(resource?.path || "");
      }
      entry.usages.push({ variant, resource });
      entry.selectors.add(variantSelector(variant));
      const selector = variantSelector(variant);
      if (selector && !entry.cacheSelectors.has(selector)) {
        entry.cacheSelectors.add(selector);
        entry.cacheSizeBytes += Number(variant?.cache_size_bytes || 0);
      }
      entry.models.add(String(variant?.model_display_name || variant?.model_id || ""));
      variantSourceRepoCandidates(variant).forEach((repo) => entry.repos.add(repo));
    });
  });
  return [...map.values()]
    .map((entry) => ({
      ...entry,
      selectors: [...entry.selectors],
      repos: [...entry.repos],
      models: [...entry.models].filter(Boolean),
      usages: entry.usages.sort((left, right) =>
        variantDisplayLabel(left.variant).localeCompare(variantDisplayLabel(right.variant)),
      ),
    }))
    .sort(
      (left, right) =>
        Number(right.sizeBytes || 0) - Number(left.sizeBytes || 0) ||
        String(left.label || "").localeCompare(String(right.label || "")),
    );
}
async function requestStopModelInstall(jobId) {
  const key = String(jobId || "").trim();
  if (!key) return;
  await post(
    "/admin/model-install/stop",
    { job_id: key },
    `/admin/model-install/stop ${key}`,
  );
  await refreshStatus({ force: true });
  renderDynamicPresetModels();
}
function openPresetResourceManager() {
  selectPresetModel(RESOURCE_MANAGER_MODEL_ID);
}
function renderResourceUsageActions(variant) {
  const state = resourceUsageState(variant);
  const selector = state.selector;
  const buttons = [];
  if (state.installing?.job_id) {
    buttons.push(
      `<button class="btn amber" onclick="requestStopModelInstall('${escapeJs(state.installing.job_id)}')">Stop Install</button>`,
    );
  }
  if (state.active) {
    buttons.push(
      `<button class="btn rose" onclick="promptVariantStop('${escapeJs(selector)}', false)">Stop</button>`,
    );
  } else if (state.switching) {
    buttons.push(
      `<button class="btn amber" onclick="promptVariantStop('${escapeJs(selector)}', true)">Stop Boot</button>`,
    );
  } else {
    buttons.push(
      `<button class="btn blue" onclick="switchInventoryVariant('${escapeJs(selector)}')">Launch</button>`,
    );
  }
  buttons.push(
    `<button class="btn red" onclick="promptDeletePresetResources('${escapeJs(selector)}')">Clear Resources</button>`,
  );
  buttons.push(
    `<button class="btn blue" onclick="openPresetLaunchSettingsModal('${escapeJs(selector)}')">Settings</button>`,
  );
  const repoUrl = variantPrimaryRepoUrl(variant);
  if (repoUrl) {
    buttons.push(
      `<a class="btn amber" href="${escapeHtml(repoUrl)}" target="_blank" rel="noopener noreferrer">Hugging Face</a>`,
    );
  }
  return buttons.join("");
}
function renderHiddenPresetToggleIcon(variant, hidden = false) {
  const selector = variantSelector(variant);
  if (!selector) return "";
  const action = hidden
    ? `unhidePresetSelector('${escapeJs(selector)}')`
    : `hidePresetSelector('${escapeJs(selector)}')`;
  return renderIconButton({
    title: hidden ? "Restore preset" : "Hide preset",
    action,
    icon: hidden ? "view" : "hide",
    className: "variant-hide-btn",
  });
}
function renderModelResourceManagerView() {
  const rows = inventoryResourceManagerRows();
  if (!rows.length) {
    return `<div class="model-card"><div class="empty-variant-note">No downloaded model resources are currently present on disk.</div></div>`;
  }
  const totalBytes = rows.reduce((sum, entry) => sum + Number(entry.sizeBytes || 0), 0);
  const totalCacheBytes = rows.reduce((sum, entry) => sum + Number(entry.cacheSizeBytes || 0), 0);
  return `<div class="resource-manager-shell"><div class="resource-manager-intro">Downloaded resources are grouped below by the shared disk asset they point at. This view is only for resource management: inspect which presets use a resource, open the source Hugging Face repo, or delete the shared asset when you no longer need it.</div><div class="resource-manager-total-card"><div class="resource-manager-total-label">Total Downloaded Resource Disk Usage</div><div class="resource-manager-total-value">${escapeHtml(formatResourcePlusCacheBytes(totalBytes, totalCacheBytes))}</div></div><div class="resource-manager-grid">${rows
    .map((entry) => {
      const markerStyle = `--preset-resource-color:${resourceColorForKey(entry.key)};`;
      const modelLabel = entry.models.join(" · ") || "Preset resource";
      const usageCount = entry.selectors.length;
      const usageLabel = `Used by ${usageCount} Preset${usageCount === 1 ? "" : "s"}`;
      const repoUrl = entry.repos[0] ? `https://huggingface.co/${entry.repos[0]}` : "";
      const markerKind = presetResourceMarkerKind(entry.usages[0]?.resource || {});
      const markerClass = `${entry.hollow ? " hollow" : ""}${markerKind === "speculative" ? " diamond" : ""}`;
      return `<div class="resource-manager-card"><div class="resource-manager-card-head"><div class="resource-manager-title-row"><span class="preset-disk-marker${markerClass}" style="${markerStyle}"></span><div class="resource-manager-title">${escapeHtml(entry.label || "Resource")}</div></div><div class="resource-manager-card-subrow"><div class="resource-manager-card-copy"><div class="resource-manager-meta">${escapeHtml(modelLabel)}</div><div class="resource-manager-usage-count">${escapeHtml(usageLabel)}</div></div><div class="resource-manager-card-actions"><span class="resource-size-badge">${escapeHtml(formatResourcePlusCacheBytes(entry.sizeBytes || 0, entry.cacheSizeBytes || 0))}</span>${repoUrl ? `<a class="resource-hf-btn" href="${escapeHtml(repoUrl)}" target="_blank" rel="noopener noreferrer">${huggingFaceLogoSvg()}<span>HF</span></a>` : ""}${renderIconButton({ title: "Clear resource", action: `promptDeleteResourcePaths([${entry.usages.map(({ resource }) => `'${escapeJs(String(resource?.path || ""))}'`).join(",")}], '${escapeJs(entry.label || "resource")}', [${entry.selectors.map((selector) => `'${escapeJs(selector)}'`).join(",")}])`, icon: "delete", className: "resource-manager-delete-btn" })}</div></div></div><div class="resource-manager-path"><code>${escapeHtml(entry.path || "")}</code></div><div class="resource-manager-usage-list">${entry.usages
        .map(({ variant }) => {
          return `<div class="resource-manager-usage-row"><div class="resource-manager-usage-copy"><div class="resource-manager-usage-title">${escapeHtml(variantDisplayLabel(variant))}</div><div class="resource-manager-usage-meta">${escapeHtml(String(variant?.best_for || variant?.quality_summary || "").trim() || "Preset usage")}</div></div></div>`;
        })
        .join("")}</div></div>`;
    })
    .join("")}</div></div>`;
}
function renderHiddenPresetManagerView() {
  const rows = inventoryVariants().filter((variant) => presetIsHidden(variant));
  if (!rows.length) {
    return `<div class="model-card"><div class="empty-variant-note">No presets are hidden right now.</div></div>`;
  }
  return `<div class="variant-group"><div class="variant-group-head"><h4>${escapeHtml(`Hidden Presets (${rows.length} Presets)`)}</h4></div><div class="variant-grid">${sortInventoryVariants(rows)
    .map((variant) => {
      const selector = variantSelector(variant);
      return `<div class="variant-card"><div class="variant-card-head"><div class="variant-card-title">${escapeHtml(variantDisplayLabel(variant))}</div><div class="preset-actions">${renderHiddenPresetToggleIcon(variant, true)}</div></div><div class="variant-meta"><strong>Best for:</strong> ${escapeHtml(variant.best_for || variant.quality_summary || "Hidden preset")}</div><div class="variant-meta"><strong>Max ctx:</strong> ${escapeHtml(variantMaxCtx(variant))} <strong>Engine:</strong> ${escapeHtml(prettyEngineName(variant.engine_display || variant.engine))}</div><div class="variant-actions"><button class="btn green" onclick="switchInventoryVariant('${escapeJs(selector)}')">Launch</button></div></div>`;
    })
    .join("")}</div></div>`;
}
function beginPresetTpsLabelPress(event, selector) {
  if (event && event.button !== undefined && event.button !== 0) return;
  cancelPresetTpsLabelPress();
  presetTpsLongPressConsumed = false;
  presetTpsLongPressTimer = setTimeout(() => {
    presetTpsLongPressTimer = null;
    presetTpsLongPressConsumed = true;
    promptClearPresetTpsStats(selector);
  }, 700);
}
function cancelPresetTpsLabelPress() {
  if (presetTpsLongPressTimer) clearTimeout(presetTpsLongPressTimer);
  presetTpsLongPressTimer = null;
}
function handlePresetTpsLabelClick(event, selector) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  cancelPresetTpsLabelPress();
  if (presetTpsLongPressConsumed) {
    presetTpsLongPressConsumed = false;
    return;
  }
  if (event?.shiftKey) promptClearPresetTpsStats(selector);
}
function promptClearPresetTpsStats(selector) {
  const key = String(selector || "").trim();
  if (!key) return;
  const variant = inventoryVariants().find((item) => variantSelector(item) === key || item?.variant_id === key);
  const label = variantDisplayLabel(variant || { upstream_tag: key });
  openPresetActionModal({
    title: "Clear TPS History",
    body: `Clear saved TPS history for <code>${escapeHtml(label)}</code>?`,
    confirmLabel: "Clear",
    confirmClass: "red",
    onConfirm: async () => {
      const payload = await post(
        "/admin/preset-tps-stats",
        { action: "clear", selector: key },
        `/admin/preset-tps-stats clear ${key}`,
        { silentSuccess: true },
      );
      if (!lastStatus) lastStatus = {};
      lastStatus.preset_tps_stats = payload?.preset_tps_stats || {};
      renderDynamicPresetModels();
    },
  });
}
function promptClearRecordedMetrics() {
  openPresetActionModal({
    title: "Clear Recorded Metrics",
    body: "Clear the saved Metrics-tab history and all persisted peak values? This resets the recorded maxima, including the values that survive control-service restarts.",
    confirmLabel: "Clear Metrics",
    confirmClass: "red",
    onConfirm: async () => {
      const payload = await post(
        "/admin/metrics-history",
        { action: "clear" },
        "/admin/metrics-history clear",
        { silentSuccess: true },
      );
      if (!lastStatus) lastStatus = {};
      lastStatus.series = Array.isArray(payload?.series) ? payload.series : [];
      lastStatus.system_metric_peaks =
        payload?.system_metric_peaks && typeof payload.system_metric_peaks === "object"
          ? payload.system_metric_peaks
          : { charts: {}, gpus: {} };
      renderMetrics(lastStatus);
      setMsg("Recorded metrics cleared.");
      refreshStatus({ force: true }).catch(() => {});
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
function variantRigBlockReason(variant) {
  const rows = Array.isArray(lastStatus?.gpus) ? lastStatus.gpus.filter((row) => row && !row.error) : [];
  const minGpuCount = Number(variant?.requires_min_gpu_count || 0);
  const minVramGb = Number(variant?.requires_min_vram_gb || 0);
  const requiredSm = String(variant?.requires_sm || "").trim().replace(/\+$/, "");
  const requiredSmRank = smToRank(requiredSm);
  const nvlinkMode = variantNvlinkMode(variant);
  if (!rows.length) return "";
  if (nvlinkMode === "required" && !rigHasNvlink()) return "Requires an active NVLink bridge on this host.";
  if (minGpuCount > 0 && rows.length < minGpuCount) return `Requires at least ${minGpuCount} visible GPU${minGpuCount === 1 ? "" : "s"}.`;
  if (minVramGb > 0) {
    const eligibleByVram = rows.filter(
      (row) => Math.ceil(Number(row?.mem_total_mib || 0) / 1024) >= minVramGb,
    );
    if (eligibleByVram.length < Math.max(minGpuCount || 1, 1)) {
      return `Requires ${minGpuCount > 1 ? `${minGpuCount}x ` : ""}${minVramGb} GB GPU memory.`;
    }
  }
  if (requiredSmRank > 0) {
    const eligibleBySm = rows.filter((row) => smToRank(row?.compute_cap) >= requiredSmRank);
    if (eligibleBySm.length < Math.max(minGpuCount || 1, 1)) return `Requires sm_${requiredSm}+ hardware.`;
  }
  return "";
}
function variantEffectiveStatusKind(variant) {
  return variantRigBlockReason(variant) ? "hardware_blocked" : String(variant?.status_kind || "unknown");
}
function variantEffectiveInstallState(variant) {
  return variantRigBlockReason(variant) ? "hardware_blocked" : String(variant?.install_state || "unknown");
}
function variantDisplayGroupKey(variant) {
  const rawCategory = String(variant?.category || "").trim().toLowerCase();
  if (rawCategory === "experimental") {
    const topology = String(variant?.topology || "").trim().toLowerCase();
    if (topology === "dual") return "dual";
    if (topology && topology !== "single") return "multi";
    return "experimental";
  }
  if (rawCategory === "multi") return "multi";
  if (rawCategory === "dual") return "dual";
  if (rawCategory === "single") {
    const topology = String(variant?.topology || "").trim().toLowerCase();
    if (topology === "dual") return "dual";
    if (topology && topology !== "single") return "multi";
    return "single";
  }
  return rawCategory;
}
function isAdvancedPresetVariant(variant) {
  const groupKey = variantDisplayGroupKey(variant);
  if (groupKey === "multi") return true;
  if (groupKey !== "dual") return false;
  return ["required", "capable"].includes(variantNvlinkMode(variant));
}
function assistantTopologyAdvisory() {
  const rows = Array.isArray(lastStatus?.gpus) ? lastStatus.gpus.filter((row) => row && !row.error) : [];
  if (rows.length <= 1) {
    return "This looks like a single-GPU rig, so the safest recommendations favor single-card presets first.";
  }
  if (rigHasNvlink()) {
    return "NVLink is detected, so the assistant can consider dual-card presets when your answers favor throughput or maximum context.";
  }
  const vrams = rows.map((row) => Math.round(Number(row?.mem_total_mib || 0) / 1024)).filter(Boolean);
  const uniform = vrams.length && vrams.every((vram) => vram === vrams[0]);
  if (uniform) {
    return "Multiple similar GPUs are visible; whole-rig recommendations are available, but single-card presets remain the lowest-friction default.";
  }
  return "Your rig mixes VRAM tiers, so single-card presets or carefully chosen custom imports are usually safer than broad Global launches.";
}
function setupAssistantProfileOptionsByWorkload(workloadId = "") {
  const wanted = String(workloadId || "").trim().toLowerCase();
  return inventoryProfileLikes().filter((profile) => {
    if (!profile || profile?.custom_import_supported === false) return false;
    if (!wanted) return true;
    return String(profile?.workload_id || "").trim().toLowerCase() === wanted;
  });
}
function setupAssistantPreferredProfile(workloadId = "") {
  return setupAssistantProfileOptionsByWorkload(workloadId)[0] || inventoryProfileLikes()[0] || null;
}
function setupAssistantQuestions() {
  return [
    {
      key: "use_case",
      title: "What are you trying to do?",
      options: [
        { value: "coding", label: "Coding", workloadId: "tool-heavy", hint: "Tool-calling agents, IDE work, and code-heavy requests." },
        { value: "chat", label: "Chatting", workloadId: "fast-chat", hint: "Low-friction conversation and fast turns." },
        { value: "long_context", label: "Long Context", workloadId: "long-ctx-single", hint: "Big files, long transcripts, or solo agent context safety." },
        { value: "multi_agent", label: "Multi-Agent", workloadId: "multi-stream-tenant", hint: "Several concurrent agents or shared-rig throughput." },
        { value: "vision", label: "Vision", workloadId: "vision-coding", hint: "Image inspection, screenshot debugging, or multimodal work." },
        { value: "reasoning", label: "Deep Reasoning", workloadId: "fast-chat", hint: "Bias toward harder reasoning and higher-answer-quality prompts." },
      ],
    },
    {
      key: "context_need",
      title: "How much context do you need?",
      options: [
        { value: "short", label: "Short", hint: "Keep latency tight and context modest." },
        { value: "balanced", label: "Balanced", hint: "A practical default for most daily work." },
        { value: "long", label: "Long", hint: "Bias toward larger windows when it helps." },
        { value: "maximum", label: "Maximum", hint: "Push the biggest stable context your rig can manage." },
      ],
    },
    {
      key: "optimize_for",
      title: "What matters most?",
      options: [
        { value: "reliability", label: "Reliability", hint: "Prefer stronger production footing and fewer surprises." },
        { value: "speed", label: "Speed", hint: "Favor snappier decode and lighter presets." },
        { value: "throughput", label: "Throughput", hint: "Favor concurrency and shared-rig efficiency." },
        { value: "capability", label: "Capability", hint: "Bias toward richer features and broader headroom." },
      ],
    },
    {
      key: "rollout_style",
      title: "How much do you want to tinker?",
      options: [
        { value: "safest", label: "Safest", hint: "Stay close to the strongest production lane first." },
        { value: "use_rig", label: "Use Whole Rig", hint: "Lean into dual or multi-card fits when they help." },
        { value: "experimental_ok", label: "Experimental OK", hint: "Show previews and sharper-edge options too." },
        { value: "custom_model", label: "I want to use a custom model!", hint: "Unlock the Hugging Face import path and pick your own upstream model." },
      ],
    },
  ];
}
function setupAssistantAnswerValue(key) {
  return String(setupAssistantAnswers?.[key] || "").trim();
}
function setSetupAssistantAnswer(key, value) {
  setupAssistantAnswers = {
    ...(setupAssistantAnswers || {}),
    [String(key || "")]: String(value || ""),
  };
  renderSetupAssistantQuestions();
  renderSetupAssistantResults();
}
function renderSetupAssistantQuestions() {
  const host = $("setupAssistantQuestions");
  if (!host) return;
  host.innerHTML = setupAssistantQuestions().map(setupAssistantQuestionHtml).join("");
}
function setupAssistantQuestionHtml(question) {
  const active = setupAssistantAnswerValue(question.key);
  return `<div class="assistant-question-card"><div class="assistant-question-title">${escapeHtml(question.title || "")}</div><div class="assistant-chip-grid">${(question.options || [])
    .map((option) => {
      const selected = String(option?.value || "") === active;
      return `<button class="assistant-chip${selected ? " active" : ""}" type="button" onclick="setSetupAssistantAnswer('${escapeJs(question.key)}','${escapeJs(option?.value || "")}')"><span class="assistant-chip-label">${escapeHtml(option?.label || option?.value || "")}</span><span class="assistant-chip-hint">${escapeHtml(option?.hint || "")}</span></button>`;
    })
    .join("")}</div></div>`;
}
function setupAssistantUseCaseOption() {
  const useCase = setupAssistantAnswerValue("use_case");
  const question = setupAssistantQuestions().find((item) => item.key === "use_case");
  return (question?.options || []).find((option) => String(option?.value || "") === useCase) || question?.options?.[0] || null;
}
function setupAssistantContextTier() {
  const value = setupAssistantAnswerValue("context_need");
  if (value === "maximum") return 3;
  if (value === "long") return 2;
  if (value === "balanced") return 1;
  return 0;
}
function setupAssistantVariantScore(variant) {
  if (!variantFitsCurrentRig(variant)) return -1e6;
  const statusKind = variantEffectiveStatusKind(variant);
  const installState = variantEffectiveInstallState(variant);
  const workloadId = String(variant?.profile_workload_id || variant?.workload_id || "").trim().toLowerCase();
  const optimizeFor = setupAssistantAnswerValue("optimize_for");
  const rolloutStyle = setupAssistantAnswerValue("rollout_style");
  const contextTier = setupAssistantContextTier();
  const maxCtx = Number(variant?.max_model_len || 0);
  const topology = String(variant?.topology || "").trim().toLowerCase();
  const useCase = setupAssistantUseCaseOption();
  const label = `${variantDisplayLabel(variant)} ${variant.best_for || ""} ${variant.quality_summary || ""}`.toLowerCase();
  let score = 0;
  if (installState === "ready") score += 18;
  else if (installState === "requires_download") score += 10;
  if (statusKind === "production") score += 22;
  else if (statusKind === "production_caveat") score += 16;
  else if (statusKind === "preview") score += 8;
  else if (statusKind === "experimental") score += 4;
  else if (statusKind === "upstream_gated") score -= 10;
  else if (statusKind === "blocked") score -= 18;
  if (String(useCase?.workloadId || "").trim().toLowerCase() === workloadId) score += 28;
  if (useCase?.value === "coding" && /(tool|code|coding|agent)/.test(label)) score += 12;
  if (useCase?.value === "chat" && /(chat|minimal|turbo)/.test(label)) score += 12;
  if (useCase?.value === "long_context" && /(long|ctx|context|bounded)/.test(label)) score += 14;
  if (useCase?.value === "multi_agent" && /(multi|tenant|turbo|concurr)/.test(label)) score += 14;
  if (useCase?.value === "vision" && /(vision|image|multimodal)/.test(label)) score += 16;
  if (useCase?.value === "reasoning" && /(reason|bounded|think|opus|capability|quality)/.test(label)) score += 16;
  if (contextTier >= 2) {
    score += Math.min(18, Math.round(maxCtx / 32000) * 3);
  } else if (contextTier === 1) {
    score += Math.min(10, Math.round(maxCtx / 64000) * 2);
  } else if (maxCtx > 0) {
    score -= Math.min(8, Math.round(maxCtx / 128000) * 2);
  }
  if (optimizeFor === "speed") {
    if (workloadId === "fast-chat") score += 14;
    if (/(minimal|turbo|mtp)/.test(label)) score += 8;
  } else if (optimizeFor === "throughput") {
    if (workloadId === "multi-stream-tenant") score += 16;
    if (topology === "dual" || topology.startsWith("multi")) score += 10;
  } else if (optimizeFor === "capability") {
    if (useCase?.value === "vision" && /(vision|image)/.test(label)) score += 10;
    if (contextTier >= 2) score += 10;
    if (String(variant?.drafter || "").trim()) score += 5;
  } else {
    if (statusKind === "production") score += 10;
    if (String(variant?.caveats || "").trim()) score -= 6;
    if (String(variant?.source_kind || "").trim().toLowerCase() === "custom") score -= 12;
  }
  if (rolloutStyle === "safest") {
    if (topology === "single") score += 6;
    if (statusKind === "preview" || statusKind === "experimental") score -= 12;
  } else if (rolloutStyle === "use_rig") {
    if ((topology === "dual" || topology.startsWith("multi")) && (Array.isArray(lastStatus?.gpus) ? lastStatus.gpus.length : 0) > 1) score += 12;
  } else if (rolloutStyle === "experimental_ok") {
    if (statusKind === "preview") score += 8;
    if (statusKind === "experimental") score += 10;
  } else if (rolloutStyle === "custom_model") {
    if (String(variant?.source_kind || "").trim().toLowerCase() === "custom") score += 24;
    score -= 8;
  }
  return score;
}
function setupAssistantRecommendations() {
  const sorted = inventoryVariants()
    .filter((variant) => variantFitsCurrentRig(variant))
    .map((variant) => ({ variant, score: setupAssistantVariantScore(variant) }))
    .filter((entry) => entry.score > -1000)
    .sort((left, right) => right.score - left.score || variantDisplayLabel(left.variant).localeCompare(variantDisplayLabel(right.variant)));
  const byModel = new Set();
  return sorted.filter((entry) => {
    const key = `${entry.variant?.model_id || ""}::${entry.variant?.topology || ""}`;
    if (byModel.has(key)) return false;
    byModel.add(key);
    return true;
  }).slice(0, 6);
}
function setupAssistantRecommendationReason(variant) {
  const reasons = [];
  const useCase = setupAssistantUseCaseOption();
  const workloadId = String(variant?.profile_workload_id || variant?.workload_id || "").trim().toLowerCase();
  if (String(useCase?.workloadId || "").trim().toLowerCase() === workloadId) {
    reasons.push(`matches upstream ${useCase.label.toLowerCase()} guidance`);
  }
  if (["long", "maximum"].includes(setupAssistantAnswerValue("context_need"))) {
    reasons.push(`leans into ${variantMaxCtx(variant)} context`);
  }
  if (setupAssistantAnswerValue("optimize_for") === "reliability" && ["production", "production_caveat"].includes(String(variantEffectiveStatusKind(variant)))) {
    reasons.push("stays on the production track");
  }
  if (setupAssistantAnswerValue("optimize_for") === "speed" && /(minimal|turbo|mtp)/i.test(variantDisplayLabel(variant))) {
    reasons.push("keeps turn latency snappy");
  }
  if (setupAssistantAnswerValue("optimize_for") === "throughput" && /(dual|multi)/i.test(String(variant?.topology || ""))) {
    reasons.push("uses the full rig for concurrency");
  }
  if (!reasons.length) reasons.push("fits the detected hardware cleanly");
  return reasons.join("; ");
}
function setupAssistantImportSummary() {
  const preferred = setupAssistantPreferredProfile(setupAssistantUseCaseOption()?.workloadId || "");
  return {
    profile: preferred,
    body: preferred
      ? `${customModelProfileOptionLabel(preferred)} is the closest upstream import anchor for these answers.`
      : "No import anchor is available until the runtime inventory finishes loading.",
  };
}
function renderSetupAssistantResults() {
  const summaryHost = $("setupAssistantSummary");
  const recommendationsHost = $("setupAssistantRecommendations");
  const importHost = $("setupAssistantImportLane");
  if (!summaryHost || !recommendationsHost || !importHost) return;
  summaryHost.innerHTML = `<div class="assistant-summary-card"><div class="assistant-summary-title">Detected rig</div><div class="assistant-summary-body">${escapeHtml(rigSummaryText())}</div><div class="assistant-summary-note">${escapeHtml(assistantTopologyAdvisory())}</div></div>`;
  const recommendations = setupAssistantRecommendations();
  recommendationsHost.innerHTML = recommendations.length
    ? recommendations.map(({ variant }) => {
      const ready = variantEffectiveInstallState(variant) === "ready";
      const action = ready
        ? `closeActionChoiceModal(); switchInventoryVariant('${escapeJs(variantSelector(variant))}')`
        : `closeActionChoiceModal(); promptModelInstallById('${escapeJs(variant.variant_id)}')`;
      return `<div class="variant-card assistant-recommendation-card"><div class="variant-card-head"><div class="variant-card-title">${escapeHtml(variantDisplayLabel(variant))}</div><div class="badge-row">${renderStatusBadgesHtml(variant)}${variantCapabilityBadges(variant)}</div></div><div class="variant-meta"><strong>Best for:</strong> ${escapeHtml(variant.best_for || "No summary yet.")}</div><div class="variant-meta"><strong>Why this fits:</strong> ${escapeHtml(setupAssistantRecommendationReason(variant))}</div><div class="variant-meta"><strong>Hardware:</strong> ${escapeHtml(variantHardwareSummary(variant) || "No explicit gate")}</div><div class="variant-actions"><button class="btn ${ready ? "blue" : "green"}" title="${escapeHtml(ready ? "Launch this preset" : downloadButtonTitle(variant?.install_command || ""))}" onclick="${action}">${escapeHtml(ready ? "Launch" : "Download")}</button>${renderPresetResourceDeleteButton(variant, !ready)}</div></div>`;
    }).join("")
    : `<div class="empty-variant-note">No presets match the current answers cleanly. Relax the rollout style or use a custom import path.</div>`;
  const importSummary = setupAssistantImportSummary();
  const importEnabled = setupAssistantAnswerValue("rollout_style") === "custom_model";
  importHost.innerHTML = importEnabled
    ? `<div class="variant-card assistant-import-card"><div class="variant-card-head"><div class="variant-card-title">Import Custom Model from Huggingface</div><div class="badge-row"><span class="status-badge status-custom">Advanced</span></div></div><div class="variant-meta">${escapeHtml(importSummary.body)}</div><div class="variant-meta"><strong>Upstream path:</strong> The import still runs upstream <code>scripts/pull.sh</code> and preserves its gate, confidence, and caveat reporting.</div><div class="variant-actions">${renderCustomModelTriggerButton({ className: "btn green custom-model-trigger assistant-inline-trigger", label: "Import Custom Model from Huggingface", onClick: `closeActionChoiceModal(); openCustomModelModal('${escapeJs(importSummary.profile?.key || "")}')` })}</div></div>`
    : `<div class="empty-variant-note">Pick <strong>I want to use a custom model!</strong> above if you want the Hugging Face import lane instead of a curated preset recommendation.</div>`;
}
function openSetupAssistantModal() {
  const rigAdvice = assistantTopologyAdvisory();
  openActionChoiceModal({
    title: "Setup Assistant",
    body: `<div class="assistant-modal-grid"><div class="assistant-modal-column assistant-quiz-column"><div class="preset-help"><strong>Detected rig:</strong> ${escapeHtml(rigSummaryText())}</div><div class="preset-help">${escapeHtml(rigAdvice)}</div><div class="preset-help">This survey leans on the upstream workload metadata and the same runtime summaries already loaded into the inventory, then keeps the answer in our model-first UI language.</div><div id="setupAssistantSummary"></div><div class="preset-section-label">Preset Recommendation Survey</div><div id="setupAssistantQuestions">${setupAssistantQuestions().map(setupAssistantQuestionHtml).join("")}</div></div><div class="assistant-modal-column"><div class="preset-section-label">Recommended Presets</div><div id="setupAssistantRecommendations" class="variant-grid"></div><div class="preset-section-label">Custom Model Path</div><div id="setupAssistantImportLane"></div></div></div>`,
    choices: [],
    cardClass: "assistant-modal-card",
  });
  renderSetupAssistantQuestions();
  renderSetupAssistantResults();
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
    !(await openClubConfirmModal(
      `Launch ${label} on ${targetLabel}? This will stop any overlapping runtime currently using those GPUs.`,
    ))
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
  return promptScopedVariantStop(selector, "", booting);
}
function promptScopedVariantStop(selector, targetId = "", booting = false) {
  const variant = inventoryVariants().find((item) => variantSelector(item) === selector);
  const label = variantDisplayLabel(variant || { upstream_tag: selector });
  const target = resolveVariantActionTarget(variant || {}, targetId);
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
async function promptRemoveSummaryPreset(modelId, selector) {
  if (!(await openClubConfirmModal(`Remove ${selector} from the cached summary list?`))) return;
  removeSummaryEntry(modelId, selector);
  renderDynamicPresetModels();
}
async function stopAllSummaryPresets() {
  const targets = summaryRunningTargets().filter(
    (item) => item.instance_id && item.mode,
  );
  if (!targets.length) return;
  if (!(await openClubConfirmModal(`Stop all ${targets.length} running preset${targets.length === 1 ? "" : "s"}?`)))
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
function renderSummaryVariantCard(variant, modelId, options = {}) {
  const selector = variantSelector(variant);
  const target = options.target || scopeTargetForVariant(variant);
  const targetId = String(target?.id || "");
  const targetLabel =
    target && targetId !== "GLOBAL" ? scopeLabel(target) : "";
  const hideRemove = !!options.hideRemove;
  const switchJob = currentSwitchJob();
  const switchTarget = String(switchJob.target || "");
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
  const rigBlockedReason = variantRigBlockReason(variant);
  const buttonLabel = rigBlockedReason ? "Blocked" : switching ? "Booting..." : active ? "Stop" : failed ? "Restart" : "Launch";
  const buttonClass = rigBlockedReason ? "amber" : switching ? "amber" : active || failed ? "rose" : "blue";
  const action = active
    ? `promptScopedVariantStop('${escapeJs(selector)}','${escapeJs(targetId)}', false)`
    : switching
      ? `promptScopedVariantStop('${escapeJs(selector)}','${escapeJs(targetId)}', true)`
      : `switchInventoryVariant('${escapeJs(selector)}')`;
  const stateClass = switching
    ? "state-booting"
    : active
      ? "state-active"
      : failed
      ? "state-error"
      : "state-summary-inactive";
  const stateLabel = rigBlockedReason ? "blocked" : switching ? "booting" : active ? "active" : failed ? "error" : "inactive";
  const title = targetLabel
    ? `${variantDisplayLabel(variant)} · ${targetLabel}`
    : variantDisplayLabel(variant);
  const runtimeMeta = targetLabel
    ? `<div class="summary-preset-meta"><strong>Scope:</strong> ${escapeHtml(targetLabel)}</div>`
    : "";
  const removeAction = hideRemove
    ? ""
    : `<div class="preset-actions">${renderIconButton({ title: "Remove from summary", action: `promptRemoveSummaryPreset('${escapeJs(modelId)}','${escapeJs(selector)}')`, icon: "delete" })}</div>`;
  const settingsCluster = renderVariantSettingsCluster(variant, active || switching);
  const deleteButton = renderPresetResourceDeleteButton(variant, active || switching);
  return `<div class="summary-preset-card${active || switching ? "" : " summary-preset-card-inactive"}"><div class="summary-preset-head"><div class="summary-preset-title">${escapeHtml(title)}</div>${removeAction}</div><div class="badge-row"><span class="state-badge ${rigBlockedReason ? "state-hardware_blocked" : stateClass}">${escapeHtml(stateLabel)}</span>${variantStatusBadgeHtml(variant, stateLabel, { failed, rigBlockedReason })}${variantCapabilityBadges(variant)}</div>${runtimeMeta}<div class="summary-preset-meta">${escapeHtml(variant.best_for || variant.quality_summary || "Cached preset")}</div><div class="variant-actions"><button class="btn ${buttonClass}" ${rigBlockedReason ? "disabled" : ""} onclick="${action}">${escapeHtml(buttonLabel)}</button>${deleteButton}${settingsCluster}</div></div>`;
}
function renderSummaryModelBody(model, modelVariants) {
  const entries = summaryEntriesForModel(model.model_id);
  const runtimeEntries = summaryRuntimeEntriesForModel(model.model_id, modelVariants);
  const runtimeSelectors = new Set(runtimeEntries.map((entry) => entry.selector));
  const bySelector = new Map(modelVariants.map((variant) => [variantSelector(variant), variant]));
  const cards = runtimeEntries
    .map((entry) =>
      renderSummaryVariantCard(entry.variant, model.model_id, {
        target: entry.target,
        hideRemove: true,
      }),
    )
    .concat(
      entries
        .filter((entry) => !runtimeSelectors.has(String(entry?.selector || "")))
        .map((entry) => bySelector.get(String(entry.selector || "")))
    .filter(Boolean)
    .slice(0, 5)
    .map((variant) => renderSummaryVariantCard(variant, model.model_id)),
    );
  return cards.length
    ? cards.join("")
    : `<div class="empty-variant-note">No cached presets for this model yet. Active and booting presets will appear here automatically.</div>`;
}
function renderVariantCard(variant) {
  const selector = variantSelector(variant);
  const target = scopeTargetForVariant(variant);
  const runtimeTargetEntry = runtimeEntryForSelector(selector);
  const statusTarget = runtimeTargetEntry?.target || target;
  const installJobs = Array.isArray(lastStatus?.model_install_jobs) ? lastStatus.model_install_jobs : [];
  const switchJob = currentSwitchJob();
  const failure = currentSwitchFailure();
  const switchTarget = String(switchJob.target || "");
  const targetId = String(statusTarget?.id || "");
  const failed =
    String(failure.mode || "") === selector &&
    !runtimeStatsRows(lastStatus).some((row) => String(row?.mode || "") === selector) &&
    (!targetId || !switchTarget || switchTarget === targetId);
  const switching =
    (!!switchJob.active &&
      String(switchJob.mode || "") === selector &&
      (!targetId || !switchTarget || switchTarget === targetId)) ||
    runtimeBootingForVariant(selector, statusTarget);
  const active = runtimeActiveForVariant(selector, statusTarget) && !switching && !failed;
  const ready = variantEffectiveInstallState(variant) === "ready";
  const rigBlockedReason = variantRigBlockReason(variant);
  const installing = installJobs.some(
    (job) =>
      job &&
      job.active &&
      job.model_id === variant.model_id &&
      job.variant_id === variant.variant_id,
  );
  const disabled = ready ? !target || installing || !!rigBlockedReason : installing || !!rigBlockedReason;
  const bootSeconds = switchJobElapsedSeconds(switchJob);
  const buttonLabel = installing
    ? "Stop Install"
    : rigBlockedReason
      ? "Blocked"
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
    ? "amber"
    : rigBlockedReason
      ? "amber"
    : switching
      ? "amber"
    : ready
        ? active || failed
          ? "rose"
          : "blue"
        : "green";
  const launchSeconds = active ? launchSecondsForVariant(selector, statusTarget) : 0;
  const stateClass = switching
    ? "state-booting"
    : active
      ? "state-active"
      : failed
        ? "state-error"
        : badgeClass("state", variantEffectiveInstallState(variant));
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
  const rigBlockedNote = rigBlockedReason
    ? `<div class="variant-install-note error-note"><strong>Blocked on this rig:</strong> ${escapeHtml(rigBlockedReason)}</div>`
    : "";
  const statusBadge = variantStatusBadgeHtml(variant, stateLabel, {
    failed,
    rigBlockedReason,
  });
  const provenanceNote =
    String(variant?.source_kind || "").trim().toLowerCase() === "custom"
      ? `<div class="variant-meta"><strong>Origin:</strong> Custom import from ${escapeHtml(variant?.profile_like || variant?.profile_workload_id || "upstream pull")}</div>`
      : "";
  const gateNote =
    String(variant?.source_kind || "").trim().toLowerCase() === "custom" && variant?.gate_terminal
      ? `<div class="variant-meta"><strong>Upstream gate:</strong> ${escapeHtml(String(variant.gate_terminal || "").replaceAll("→", " -> "))}</div>`
      : "";
  const footer = launchSeconds
    ? `<div class="variant-footer"><span class="variant-launch-time">${escapeHtml(formatElapsedLaunch(launchSeconds))}</span></div>`
    : "";
  const buttonTitle = ready
    ? active
      ? "Stop the running preset"
      : switching
        ? "Interrupt the preset boot"
        : failed
          ? "Retry this preset launch"
          : "Launch this preset"
    : installing?.job_id
      ? "Stop the active model download"
      : downloadButtonTitle(variant?.install_command || "");
  const action = ready
    ? active
      ? `promptVariantStop('${escapeJs(selector)}', false)`
      : switching
        ? `promptVariantStop('${escapeJs(selector)}', true)`
        : failed
          ? `switchInventoryVariant('${escapeJs(selector)}')`
          : `switchInventoryVariant('${escapeJs(selector)}')`
    : installing?.job_id
      ? `requestStopModelInstall('${escapeJs(installing.job_id)}')`
      : `switchInventoryVariant('${escapeJs(selector)}')`;
  const settingsCluster = renderVariantSettingsCluster(variant, active || switching || installing);
  const deleteButton = renderPresetResourceDeleteButton(variant, active || switching || installing);
  const actionDisabled = !!rigBlockedReason || (ready ? !target : !installing);
  return `<div class="variant-card${active ? " active-variant" : ""}"><div class="variant-card-head"><div class="variant-card-title">${escapeHtml(variantDisplayLabel(variant))}</div><div class="badge-row"><span class="state-badge ${stateClass}"${stateAttrs}>${escapeHtml(stateLabel)}</span>${statusBadge}${variantCapabilityBadges(variant)}</div></div><div class="variant-meta"><strong>Best for:</strong> ${escapeHtml(variant.best_for || "No summary yet.")}</div><div class="variant-meta"><strong>Max ctx:</strong> ${escapeHtml(variantMaxCtx(variant))} <strong>Engine:</strong> ${escapeHtml(prettyEngineName(variant.engine_display || variant.engine))} <strong>Drafter:</strong> ${escapeHtml(variant.drafter || "none")} <strong>KV:</strong> ${escapeHtml(variant.kv_format || "n/a")}</div>${provenanceNote}${gateNote}${hardwareNote}${rigBlockedNote}${caveat}${installNote}${failureNote}<div class="variant-actions"><button class="btn ${buttonClass}" title="${escapeHtml(buttonTitle)}" ${actionDisabled ? "disabled" : ""} onclick="${action}">${escapeHtml(buttonLabel)}</button>${deleteButton}${settingsCluster}</div>${footer}</div>`;
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
function renderAdvancedVariantGroup(rows) {
  const advancedRows = sortInventoryVariants(rows);
  const nvlinkRows = advancedRows.filter((row) => variantDisplayGroupKey(row) === "dual");
  const multiRows = advancedRows.filter((row) => variantDisplayGroupKey(row) === "multi");
  const sections = [];
  sections.push(
    `<div class="variant-subgroup"><div class="variant-subgroup-title">NVLink Presets</div>${nvlinkRows.length ? `<div class="variant-grid">${nvlinkRows.map(renderVariantCard).join("")}</div>` : '<div class="empty-variant-note">No NVLink-specific presets discovered for this model.</div>'}</div>`,
  );
  sections.push(
    `<div class="variant-subgroup"><div class="variant-subgroup-title">Multi-GPU Presets</div>${multiRows.length ? `<div class="variant-grid">${multiRows.map(renderVariantCard).join("")}</div>` : '<div class="empty-variant-note">No shared multi-GPU presets discovered for this model.</div>'}</div>`,
  );
  return `<div class="variant-group"><div class="variant-group-head"><h4>${escapeHtml(`Advanced Docker Presets (${advancedRows.length} Presets)`)}</h4></div>${sections.join("")}</div>`;
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
    setHtmlIfChanged(host, `<div class="model-card"><div class="empty-variant-note">No runtime inventory data was found. Rebuild the Model DB to rescan the upstream checkout.</div></div>`);
    return;
  }
  if (selectedPresetModelId === HIDDEN_PRESETS_MODEL_ID) {
    setHtmlIfChanged(host, renderHiddenPresetManagerView());
    return;
  }
  if (selectedPresetModelId === RESOURCE_MANAGER_MODEL_ID) {
    setHtmlIfChanged(host, renderModelResourceManagerView());
    return;
  }
  const visibleModels = selectedPresetModelId
    ? models.filter((model) => String(model.model_id || "") === selectedPresetModelId)
    : models;
  const nextHtml = `${visibleModels
    .map((model) => {
      const modelVariants = variants.filter((row) => row.model_id === model.model_id);
      const visibleModelVariants = modelVariants.filter((row) => !presetIsHidden(row));
      const selected = String(model.model_id || "") === selectedPresetModelId;
      const familyActive = modelFamilyHasActivePreset(modelVariants);
      const presetCount = modelVariants.length;
      const summaryBody = renderSummaryModelBody(model, modelVariants);
      const deprecatedRows = visibleModelVariants.filter((row) => variantEffectiveStatusKind(row) === "deprecated");
      const nonDeprecatedRows = visibleModelVariants.filter((row) => variantEffectiveStatusKind(row) !== "deprecated");
      const singleRows = nonDeprecatedRows.filter((row) => variantDisplayGroupKey(row) === "single");
      const dualRows = nonDeprecatedRows.filter((row) => variantDisplayGroupKey(row) === "dual" && !isAdvancedPresetVariant(row));
      const advancedRows = nonDeprecatedRows.filter((row) => isAdvancedPresetVariant(row));
      const experimentalRows = nonDeprecatedRows.filter((row) => variantDisplayGroupKey(row) === "experimental");
      const customDelete = modelIsCustom(model)
        ? `<span class="model-card-title-action">${renderIconButton({ title: "Remove custom model", action: `promptDeleteCustomModel('${escapeJs(model.model_id)}')`, icon: "delete" })}</span>`
        : "";
      const customBadge = modelIsCustom(model)
        ? '<span class="status-badge status-custom">Custom</span>'
        : "";
      const body = selected
        ? `<div class="variant-groups">${renderVariantGroup("Single GPU Docker Presets", singleRows)}${renderVariantGroup("Dual GPU Docker Presets", dualRows)}${renderAdvancedVariantGroup(advancedRows)}${renderVariantGroup("Experimental Docker Presets", experimentalRows)}${renderVariantGroup("Deprecated Presets", deprecatedRows)}</div>`
        : summaryBody;
      return `<div class="model-card${selected ? " selected-model-card" : " collapsed-model-card"}${familyActive ? " model-card-active-family" : ""}"><div class="model-card-head"><div><div class="model-card-title-row">${customDelete}<h3>${escapeHtml(model.display_name || model.model_id)} (${presetCount} Presets)</h3></div><div class="model-summary">${escapeHtml(model.summary || "No summary available yet.")}</div></div><div class="badge-row"><span class="state-badge ${badgeClass("state", model.installed_state)}">${escapeHtml(String(model.installed_state || "unknown"))}</span>${customBadge}</div></div>${body}</div>`;
    })
    .join("")}${!selectedPresetModelId ? renderSummaryActionBar() : ""}`;
  setHtmlIfChanged(host, nextHtml);
}
function renderModelInstallStatus() {
  const target = $("presetJobSummary");
  if (!target) return;
  target.classList.remove("hidden");
  const jobs = Array.isArray(lastStatus?.model_install_jobs) ? lastStatus.model_install_jobs : [];
  const job = lastStatus?.model_install_job || {};
  const customJob = lastStatus?.custom_model_job || {};
  if (customJob.active) {
    const label = customJob.model_id || customJob.slug || "custom model";
    target.textContent = `Custom model job running for ${label}. Output is streaming to Audit Logs.`;
    return;
  }
  if (customJob.status === "success") {
    target.textContent = `${customJob.summary || "Custom model import completed successfully."}`;
    return;
  }
  if (customJob.status === "failed") {
    target.textContent = `${customJob.summary || "Custom model import failed."}`;
    return;
  }
  const activeJobs = jobs.filter((row) => row && row.active);
  if (activeJobs.length) {
    const labels = activeJobs
      .map((row) => `${row.model_id || "unknown model"} (${row.variant_id || "preset"})`)
      .slice(0, 3);
    const suffix = activeJobs.length > 3 ? `, +${activeJobs.length - 3} more` : "";
    target.textContent = `${activeJobs.length} model download job${activeJobs.length === 1 ? "" : "s"} running: ${labels.join(", ")}${suffix}. Output is streaming to Audit Logs.`;
    return;
  }
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
  if (job.status === "stopped") {
    target.textContent = `${job.summary || "Model install stopped."}`;
    return;
  }
  const showIdleDownloadHint = !!selectedPresetModelId && ![HIDDEN_PRESETS_MODEL_ID, RESOURCE_MANAGER_MODEL_ID].includes(selectedPresetModelId);
  target.textContent = showIdleDownloadHint
    ? "Downloads started from this tab stream into Audit Logs and automatically rebuild the Model DB on success."
    : "";
  target.classList.toggle("hidden", !target.textContent);
}
function customModelProfileOptions() {
  return inventoryProfileLikes().filter(
    (row) =>
      String(row?.key || "").trim() &&
      String(row?.engine_family || "").trim() === "vllm" &&
      row?.custom_import_supported !== false,
  );
}
function customModelProfileOptionLabel(profile) {
  const bits = [
    String(profile?.key || "").trim(),
    String(profile?.model_display_name || profile?.model_id || "").trim(),
    Number(profile?.tp || 1) > 1 ? `TP ${profile?.tp}` : "single-card",
  ].filter(Boolean);
  return bits.join(" | ");
}
function customModelDetectedRigSummary() {
  const rows = Array.isArray(lastStatus?.gpus) ? lastStatus.gpus.filter((row) => row && !row.error) : [];
  if (!rows.length) return "No NVIDIA GPU telemetry is available right now.";
  return rows
    .map(
      (row) =>
        `${Math.round(Number(row?.mem_total_mib || 0) / 1024)} GB ${row?.name || "GPU"} (sm_${String(row?.compute_cap || "").replace(/^sm_/, "") || "?"})`,
    )
    .join(" | ");
}
function selectedCustomModelProfile() {
  const key = String($("customModelProfileLike")?.value || "").trim();
  return customModelProfileOptions().find((profile) => String(profile?.key || "") === key) || null;
}
function customModelDefaultEngineSwitches(profile) {
  return String(profile?.default_engine_switches || "").trim();
}
function syncCustomModelEngineSwitches(force = false) {
  const field = $("customModelEngineSwitches");
  if (!field) return;
  const nextDefault = customModelDefaultEngineSwitches(selectedCustomModelProfile());
  const previousDefault = String(field.dataset.defaultValue || "");
  const currentValue = String(field.value || "");
  if (force || !currentValue || currentValue === previousDefault || field.dataset.dirty !== "1") {
    field.value = nextDefault;
    field.dataset.dirty = "0";
  }
  field.dataset.defaultValue = nextDefault;
}
function ensureCustomModelModal() {
  if ($("customModelModal")) return;
  const modal = document.createElement("div");
  modal.id = "customModelModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card custom-model-modal-card" role="dialog" aria-modal="true" aria-labelledby="customModelTitle"><div class="panel-head"><h2 id="customModelTitle">Custom Model</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeCustomModelModal()">✕</button></div><div class="preset-help">This keeps the panel model-first while delegating the actual evaluation, gating, and compose generation to upstream <code>scripts/pull.sh</code>.</div><div class="custom-model-shell"><div class="custom-model-main"><div class="preset-section-label">Identity</div><div class="formgrid custom-model-form-grid"><label>Display name<input id="customModelDisplayName" class="club-text-field" placeholder="Optional UI label" autocomplete="off" spellcheck="false" /></label><label>HF repo slug<input id="customModelSlug" class="club-text-field" placeholder="org/model-name" autocomplete="off" spellcheck="false" /></label><label class="preset-form-span-2">Reference profile<select id="customModelProfileLike"></select></label></div><div class="preset-section-label">Safety And Overrides</div><div class="custom-model-check-grid"><label class="custom-model-check-card"><input id="customModelAcceptConfirm" type="checkbox" checked /><span><strong>Accept confirm -> proceed</strong><small>Allow upstream <code>--yes</code> when the gate says the fit is acceptable but still needs acknowledgment.</small></span></label><label class="custom-model-check-card"><input id="customModelTrustRemoteCode" type="checkbox" /><span><strong>Trust remote code</strong><small>Use <code>--trust-remote-code</code> only when you explicitly accept the repo's custom model code.</small></span></label><label class="custom-model-check-card"><input id="customModelExperimentalArch" type="checkbox" /><span><strong>Experimental architecture</strong><small>Allow <code>--experimental-arch</code> when the repo architecture is not yet formally mapped upstream.</small></span></label><label class="custom-model-check-card"><input id="customModelForceDownload" type="checkbox" /><span><strong>Force low-confidence path</strong><small>Expose the upstream <code>--force-download</code> override for advisory non-pass paths.</small></span></label></div><div class="preset-section-label">Optional Hardware Hints</div><div class="formgrid custom-model-form-grid"><label>HF_HOME override<input id="customModelHfHome" class="club-text-field" placeholder="Optional cache root" autocomplete="off" spellcheck="false" /></label><label>SM override<input id="customModelHardwareSm" class="club-text-field" placeholder="8.6" autocomplete="off" spellcheck="false" /></label><label class="preset-form-span-2">GPU topology override<input id="customModelHardwareGpus" class="club-text-field" placeholder="24576:RTX 3090,24576:RTX 3090" autocomplete="off" spellcheck="false" /></label></div><label class="preset-launch-settings-raw-label custom-model-engine-switches-label">Custom engine switches<textarea id="customModelEngineSwitches" class="preset-launch-settings-raw" placeholder="Loaded from the selected reference compose profile." spellcheck="false"></textarea></label></div><aside class="custom-model-sidebar"><div class="preset-section-label custom-model-sidebar-header">Rig And Import Notes</div><div class="custom-model-sidecard"><div class="custom-model-sidecard-title">Detected rig</div><div class="custom-model-sidecard-body" id="customModelDetectedRig">${escapeHtml(customModelDetectedRigSummary())}</div></div><div class="custom-model-sidecard"><div class="custom-model-sidecard-title">Reference profile guidance</div><div class="custom-model-sidecard-body">Reference profiles come from the upstream compose registry. Simpler patchless shapes usually import more cleanly; overlay-heavy or drafter-heavy profiles may still refuse upstream, and the exact refusal will stream into Audit Logs.</div></div><div class="custom-model-sidecard"><div class="custom-model-sidecard-title">What gets registered</div><div class="custom-model-sidecard-body">Only successful upstream runs are added to the local custom-model registry. Confidence tier, gate result, caveats, and the generated compose all stay attached to that entry.</div></div></aside></div><div class="preset-form-actions"><button class="btn blue" onclick="closeCustomModelModal()">Cancel</button><button class="btn green" onclick="submitCustomModelModal()">Add</button></div><div class="msg" id="customModelMsg"></div></div>`;
  document.body.appendChild(modal);
  $("customModelProfileLike")?.addEventListener("change", () => syncCustomModelEngineSwitches(false));
  $("customModelEngineSwitches")?.addEventListener("input", () => {
    $("customModelEngineSwitches").dataset.dirty = "1";
  });
}
function populateCustomModelProfiles() {
  const select = $("customModelProfileLike");
  if (!select) return;
  const profiles = customModelProfileOptions();
  const html = profiles
    .map(
      (profile) =>
        `<option value="${escapeHtml(profile.key)}">${escapeHtml(customModelProfileOptionLabel(profile))}</option>`,
    )
    .join("");
  setSelectOptions(select, html);
  if (!select.value && profiles.length) {
    const preferred =
      profiles.find((profile) => String(profile?.key || "") === "vllm/minimal") || profiles[0];
    select.value = String(preferred?.key || "");
  }
  syncCustomModelEngineSwitches(true);
}
function openCustomModelModal(preferredProfileLike = "") {
  ensureCustomModelModal();
  populateCustomModelProfiles();
  if (preferredProfileLike && $("customModelProfileLike")) {
    const preferred = String(preferredProfileLike || "").trim();
    if ([...($("customModelProfileLike").options || [])].some((option) => String(option.value || "") === preferred)) {
      $("customModelProfileLike").value = preferred;
    }
  }
  $("customModelDisplayName").value = "";
  $("customModelSlug").value = "";
  $("customModelAcceptConfirm").checked = true;
  $("customModelTrustRemoteCode").checked = false;
  $("customModelExperimentalArch").checked = false;
  $("customModelForceDownload").checked = false;
  $("customModelHfHome").value = "";
  $("customModelHardwareSm").value = "";
  $("customModelHardwareGpus").value = "";
  $("customModelEngineSwitches").value = "";
  $("customModelEngineSwitches").dataset.dirty = "0";
  if ($("customModelDetectedRig")) {
    $("customModelDetectedRig").textContent = customModelDetectedRigSummary();
  }
  syncCustomModelEngineSwitches(true);
  setElementMsg("customModelMsg", "");
  $("customModelModal")?.classList.remove("hidden");
}
function closeCustomModelModal() {
  $("customModelModal")?.classList.add("hidden");
}
async function submitCustomModelModal() {
  const payload = {
    action: "add",
    display_name: String($("customModelDisplayName")?.value || "").trim(),
    slug: String($("customModelSlug")?.value || "").trim(),
    profile_like: String($("customModelProfileLike")?.value || "").trim(),
    accept_confirm: !!$("customModelAcceptConfirm")?.checked,
    trust_remote_code: !!$("customModelTrustRemoteCode")?.checked,
    experimental_arch: !!$("customModelExperimentalArch")?.checked,
    force_download: !!$("customModelForceDownload")?.checked,
    hf_home: String($("customModelHfHome")?.value || "").trim(),
    hardware_sm: String($("customModelHardwareSm")?.value || "").trim(),
    hardware_gpus: String($("customModelHardwareGpus")?.value || "").trim(),
    engine_switches: String($("customModelEngineSwitches")?.value || "").trim(),
  };
  if (!payload.slug || !payload.profile_like) {
    setElementMsg("customModelMsg", "Enter a Hugging Face repo slug and choose a reference profile first.", "error");
    return;
  }
  try {
    await post("/admin/custom-models", payload, `/admin/custom-models add ${payload.slug}`);
    closeCustomModelModal();
  } catch (e) {
    setElementMsg("customModelMsg", messageText(e), "error");
  }
}
async function promptDeleteCustomModel(modelId) {
  const model = inventoryModels().find((row) => String(row?.model_id || "") === String(modelId || ""));
  if (!model || !modelIsCustom(model)) return;
  if (!(await openClubConfirmModal(`Remove and uninstall custom model ${model.display_name || model.model_id}?`))) return;
  await post(
    "/admin/custom-models",
    {
      action: "delete",
      id: model.model_id,
    },
    `/admin/custom-models delete ${model.model_id}`,
  );
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
  select.disabled = !!chatState.busy || chatHydrationPending() || !chatStateHydrated;
}
async function selectChatConversation(value) {
  const nextId = String(value || "");
  if (!nextId || nextId === chatState.activeConversationId || chatState.busy) return;
  if (chatHydrationPending() || !chatStateHydrated) {
    setChatMsg("Loading conversations...");
    try {
      await hydrateChatState();
    } catch (error) {
      setChatMsg(error?.message || "Failed to load conversations.", "error");
      return;
    }
  }
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
async function createNewConversation() {
  if (chatState.busy) return;
  if (chatHydrationPending() || !chatStateHydrated) {
    setChatMsg("Loading conversations...");
    try {
      await hydrateChatState();
    } catch (error) {
      setChatMsg(error?.message || "Failed to load conversations.", "error");
      return;
    }
  }
  persistChatConversationState();
  const baseConversation = activeChatConversation();
  const conversation = createChatConversation({}, baseConversation);
  const firstRuntime = activeChatPresets()[0] || null;
  conversation.presetId = chatPresetKey(firstRuntime) || "";
  resetConversationRuntimeMetrics(conversation, firstRuntime);
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
  modal.innerHTML = `<div class="club-modal-card conversation-modal-card" role="dialog" aria-modal="true" aria-labelledby="chatConversationTitle"><div class="panel-head"><h2 id="chatConversationTitle">Edit Chat</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeConversationEditorModal()">✕</button></div><div class="formgrid"><label>Conversation Name<input id="chatConversationName" placeholder="${escapeHtml(CHAT_UNTITLED_TITLE)}" /></label><label>Folder<input id="chatConversationFolder" list="chatConversationFolderList" placeholder="optional subfolder" pattern="[A-Za-z0-9 _-]*" /></label></div><datalist id="chatConversationFolderList"></datalist><div class="preset-help">Use only letters, numbers, spaces, <code>-</code>, and <code>_</code>.</div><div class="preset-form-actions conversation-modal-actions"><button class="btn red btn-icon-label" onclick="deleteConversationFromEditorModal()">${svgIcon("delete")}<span>Delete Chat</span></button><button class="btn green btn-icon-label" onclick="saveConversationEditorModal()">${svgIcon("save")}<span>Save</span></button></div><div class="msg" id="chatConversationModalMsg"></div></div>`;
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
function deleteConversationFromEditorModal() {
  closeConversationEditorModal();
  deleteActiveConversation();
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
function updateChatDeleteButtonState() {
  const button = $("chatConversationDeleteBtn");
  if (!button) return;
  const permanent = !!chatDeleteModifierActive;
  const title = permanent ? "Delete conversation permanently" : "Archive conversation";
  button.title = permanent ? `${title} (Shift)` : title;
  button.setAttribute("aria-label", button.title);
  button.innerHTML = svgIcon(permanent ? "delete" : "archive");
}
function clearChatDeleteLongPress() {
  if (chatDeleteLongPressTimer) {
    clearTimeout(chatDeleteLongPressTimer);
    chatDeleteLongPressTimer = null;
  }
}
function ensureChatArchiveLongPressBinding() {
  const button = $("chatConversationDeleteBtn");
  if (!button || button.__clubLongPressBound) return;
  button.__clubLongPressBound = true;
  const cancel = () => clearChatDeleteLongPress();
  const begin = () => {
    clearChatDeleteLongPress();
    if (chatState.busy) return;
    chatDeleteLongPressTriggered = false;
    chatDeleteLongPressTimer = window.setTimeout(() => {
      chatDeleteLongPressTriggered = true;
      deleteActiveConversation();
    }, 550);
  };
  button.addEventListener("pointerdown", begin);
  button.addEventListener("pointerup", cancel);
  button.addEventListener("pointercancel", cancel);
  button.addEventListener("pointerleave", cancel);
  button.addEventListener("touchstart", begin, { passive: true });
  button.addEventListener("touchend", cancel, { passive: true });
  button.addEventListener("touchcancel", cancel, { passive: true });
}
function handleChatDeleteModifierEvent(event) {
  const nextState = !!event?.shiftKey;
  if (chatDeleteModifierActive === nextState) return;
  chatDeleteModifierActive = nextState;
  updateChatDeleteButtonState();
}
window.addEventListener("keydown", handleChatDeleteModifierEvent);
window.addEventListener("keyup", handleChatDeleteModifierEvent);
window.addEventListener("blur", () => {
  if (!chatDeleteModifierActive) return;
  chatDeleteModifierActive = false;
  updateChatDeleteButtonState();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden && chatStateHydrated && !chatState.busy) {
    flushServerChatStateSave(currentChatStatePayload()).catch(() => null);
  }
  if (!document.hidden || !chatDeleteModifierActive) return;
  chatDeleteModifierActive = false;
  updateChatDeleteButtonState();
});
function handleActiveConversationArchiveOrDelete(event) {
  if (chatDeleteLongPressTriggered) {
    chatDeleteLongPressTriggered = false;
    return;
  }
  if ((event?.ctrlKey || event?.metaKey) && (event?.shiftKey || chatDeleteModifierActive)) {
    deleteAllConversations();
    return;
  }
  if ((event?.shiftKey || chatDeleteModifierActive) === true) {
    deleteActiveConversation();
    return;
  }
  archiveActiveConversation();
}
function deleteActiveConversation() {
  runChatConversationAction("delete").catch((e) => {
    setChatMsg(e?.message || "Failed to delete the conversation.", "error");
  });
}
function archiveActiveConversation() {
  runChatConversationAction("archive").catch((e) => {
    setChatMsg(e?.message || "Failed to archive the conversation.", "error");
  });
}
function deleteAllConversations() {
  runChatConversationAction("delete_all").catch((e) => {
    setChatMsg(e?.message || "Failed to delete all conversations.", "error");
  });
}
async function runChatConversationAction(action, conversationId = "") {
  if (chatState.busy) return;
  persistChatConversationState();
  await flushServerChatStateSave(currentChatStatePayload()).catch(() => null);
  const targetId = String(conversationId || "");
  const conversation = targetId
    ? chatArchivedConversations().find((item) => item.id === targetId) ||
      chatConversations().find((item) => item.id === targetId) ||
      null
    : activeChatConversation();
  if (!conversation && action !== "delete_all") return;
  const actionLabels = {
    archive: {
      confirm: `Archive conversation "${chatConversationTitle(conversation)}"?`,
      success: `Archived conversation "${chatConversationTitle(conversation)}".`,
    },
    restore: {
      confirm: `Restore conversation "${chatConversationTitle(conversation)}"?`,
      success: `Restored conversation "${chatConversationTitle(conversation)}".`,
    },
    delete: {
      confirm: `Delete conversation "${chatConversationTitle(conversation)}" permanently?`,
      success: `Deleted conversation "${chatConversationTitle(conversation)}".`,
    },
    delete_all: {
      confirm: "Delete all conversations permanently? This removes both active and archived chats from the browser cache and server storage.",
      success: "Deleted all conversations.",
    },
  };
  const labels = actionLabels[action] || actionLabels.archive;
  if (
    !(await openClubConfirmModal(
      action === "delete_all"
        ? {
            title: currentClubAlertTitle(),
            bodyHtml:
              '<div class="danger-copy">Delete all conversations permanently?</div><div>This removes both active and archived chats from the browser cache and server storage.</div>',
            dangerBody: true,
            confirmClass: "red",
            confirmLabel: "Delete All",
          }
        : labels.confirm,
    ))
  )
    return;
  cancelPendingServerChatStateSave();
  const response = await post(
    "/admin/chat-conversations",
    { action, conversation_id: conversation.id },
    `/admin/chat-conversations ${action} ${conversation.id}`,
    { silentSuccess: true, silentFailure: true },
  );
  const serverState =
    response?.state && typeof response.state === "object" ? response.state : null;
  if (!serverState) {
    throw new Error("Conversation update did not return chat state.");
  }
  applyServerChatState(serverState);
  syncLocalChatStateCache();
  renderChatUi();
  if ($("chatArchivedModal") && !$("chatArchivedModal").classList.contains("hidden")) {
    renderArchivedConversationsModal();
    setElementMsg("chatArchivedMsg", labels.success, "success");
  }
  setChatMsg(labels.success, "success");
}
function ensureArchivedConversationsModal() {
  if ($("chatArchivedModal")) return;
  const modal = document.createElement("div");
  modal.id = "chatArchivedModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card conversation-modal-card" role="dialog" aria-modal="true" aria-labelledby="chatArchivedTitle"><div class="panel-head"><h2 id="chatArchivedTitle">Archived Chats</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeArchivedConversationsModal()">✕</button></div><div class="preset-help">Archived chats stay on the server and can be restored here. Permanent deletion removes them from both the browser cache and server state.</div><div id="chatArchivedList" class="chat-archived-list"></div><div class="msg" id="chatArchivedMsg"></div></div>`;
  document.body.appendChild(modal);
}
function closeArchivedConversationsModal() {
  ensureArchivedConversationsModal();
  $("chatArchivedModal").classList.add("hidden");
}
function renderArchivedConversationsModal() {
  ensureArchivedConversationsModal();
  const host = $("chatArchivedList");
  if (!host) return;
  const rows = [...chatArchivedConversations()].sort(
    (left, right) =>
      Number(right?.archivedAt || right?.updatedAt || 0) -
      Number(left?.archivedAt || left?.updatedAt || 0),
  );
  if (!rows.length) {
    host.innerHTML =
      '<div class="empty-variant-note">No archived chats yet.</div>';
    return;
  }
  host.innerHTML = rows
    .map((conversation) => {
      const title = chatConversationTitle(conversation);
      const meta = [
        conversation.folder ? `folder ${conversation.folder}` : "",
        conversation.archivedAt ? `archived ${formatAbsoluteTimestamp(conversation.archivedAt)}` : "",
        conversation.updatedAt ? `updated ${formatAbsoluteTimestamp(conversation.updatedAt)}` : "",
      ].filter(Boolean);
      return `<div class="storage-card"><div class="panel-head"><div><div class="storage-title">${escapeHtml(title)}</div>${meta.length ? `<div class="storage-meta">${escapeHtml(meta.join(" · "))}</div>` : ""}</div><div class="preset-actions"><button class="iconbtn" title="Restore" aria-label="Restore" onclick="restoreArchivedConversation('${escapeHtml(conversation.id)}')">${svgIcon("restore")}</button><button class="iconbtn" title="Delete permanently" aria-label="Delete permanently" onclick="deleteArchivedConversation('${escapeHtml(conversation.id)}')">${svgIcon("delete")}</button></div></div>${conversation.summary ? `<div class="preset-help">${escapeHtml(conversation.summary)}</div>` : ""}</div>`;
    })
    .join("");
}
function openArchivedConversationsModal() {
  toggleChatOptionsMenu(false);
  renderArchivedConversationsModal();
  setElementMsg("chatArchivedMsg", "");
  $("chatArchivedModal")?.classList.remove("hidden");
}
function restoreArchivedConversation(conversationId) {
  runChatConversationAction("restore", conversationId).catch((e) => {
    setElementMsg("chatArchivedMsg", e?.message || "Failed to restore the conversation.", "error");
  });
}
function deleteArchivedConversation(conversationId) {
  runChatConversationAction("delete", conversationId).catch((e) => {
    setElementMsg("chatArchivedMsg", e?.message || "Failed to delete the conversation.", "error");
  });
}
function fallbackConversationTitle(text, attachments = []) {
  const clean = String(text || "")
    .replace(/\s+/g, " ")
    .trim();
  if (clean) {
    const words = clean.split(/\s+/).slice(0, 10).join(" ");
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
function chatSmartTitlesEnabled(conversation = activeChatConversation()) {
  if (conversation && typeof conversation === "object") {
    return conversation.smartTitleEnabled !== false;
  }
  return chatState.smartTitleEnabled !== false;
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
function parseChatPresetKeyParts(value) {
  const [runtimeId = "", selector = ""] = String(value || "").split("::");
  return {
    runtimeId: String(runtimeId || "").trim(),
    selector: String(selector || "").trim(),
  };
}
function activeChatPresets() {
  return runtimeStatsRows(lastStatus).filter((runtime) => runtime && runtime.running);
}
