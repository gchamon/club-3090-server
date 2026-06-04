// Canonical runtime UI path
const UI_STATE_KEY = "club3090-ui-state";
let uiStateHydrated = false;
let uiStateSaveTimer = null;
let lastQueuedUiStateJson = "";
let instanceBusyState = { active: false, message: "" };
let currentLogSignature = "";
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
    const safe = { ...currentChatStatePayload(), revision: nextRevision };
    if (suspiciousConversationDrop(safe)) {
      logDebugEvent("chat_state_save_skipped", {
        reason: "suspicious_drop",
        hydratedConversationCount: chatHydratedServerConversationCount,
        nextConversationCount: chatConversationCountFromState(safe),
        revision: nextRevision,
      });
      return;
    }
    chatState.revision = nextRevision;
    localStorage.setItem(CHAT_STATE_KEY, JSON.stringify(safe));
    clearLegacyChatStateCaches();
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
    try {
      const response = await fetchJsonWithTimeout(
        `/admin/chat-state?titles=1&_=${Date.now()}`,
        { cache: "no-store" },
        5000,
      );
      const payload = await response.json();
      if (response.ok && payload?.ok && payload?.state) cached = payload.state;
    } catch (e) {}
    if (cached && Array.isArray(cached.conversations)) {
      const conversations = cached.conversations
        .map((conversation) => createChatConversation(conversation))
        .filter(Boolean);
      const archivedConversations = Array.isArray(cached.archivedConversations)
        ? cached.archivedConversations
            .map((conversation) => createChatConversation(conversation))
            .filter(Boolean)
        : [];
      if (conversations.length) {
        chatState = {
          ...chatState,
          revision: Math.max(0, Number(cached.revision || 0) || 0),
          activeConversationId: String(
            cached.activeConversationId || conversations[0].id,
          ),
          conversations,
          archivedConversations,
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
      } else if (archivedConversations.length) {
        chatState = {
          ...chatState,
          revision: Math.max(0, Number(cached.revision || 0) || 0),
          archivedConversations,
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
        smartTitleEnabled: cached.smartTitleEnabled !== false,
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
    noteConfirmedServerChatState(currentChatStatePayload());
    chatStateHydrated = true;
    logDebugEvent("chat_hydrate_ready", {
      revision: Number(chatState.revision || 0),
      activeConversationId: String(chatState.activeConversationId || ""),
      conversationCount: chatConversations().length,
      archivedConversationCount: Array.isArray(chatState.archivedConversations)
        ? chatState.archivedConversations.length
        : 0,
    });
    clearLegacyChatStateCaches();
    if (chatState.activeConversationId) {
      loadChatConversationDetail(chatState.activeConversationId, { silent: true }).catch(() => {});
    }
    return chatState;
  })().catch((error) => {
    logDebugEvent("chat_hydrate_error", {
      error: error?.message || String(error || ""),
    });
    throw error;
  })
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
function chatArchivedConversations() {
  return Array.isArray(chatState.archivedConversations)
    ? chatState.archivedConversations
    : [];
}
function activeChatConversation() {
  const rows = chatConversations();
  return (
    rows.find((conversation) => conversation.id === chatState.activeConversationId) ||
    rows[0] ||
    null
  );
}
function applyServerChatState(serverState, options = {}) {
  const preserveSelection = !!options.preserveSelection;
  const nextRows = Array.isArray(serverState?.conversations)
    ? serverState.conversations.map((row) => createChatConversation(row)).filter(Boolean)
    : [];
  const archivedRows = Array.isArray(serverState?.archivedConversations)
    ? serverState.archivedConversations
        .map((row) => createChatConversation(row))
        .filter(Boolean)
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
  chatState.archivedConversations = archivedRows;
  if (nextRows.length) {
    chatState.conversations = nextRows;
    const preferredActiveId = String(serverState?.activeConversationId || "");
    chatState.activeConversationId =
      preferredActiveId && nextRows.some((row) => row.id === preferredActiveId)
        ? preferredActiveId
        : String(nextRows[0].id || "");
    if (!preserveSelection) resetChatTranscriptWindow();
  } else {
    const replacement = createChatConversation();
    chatState.conversations = [replacement];
    chatState.activeConversationId = replacement.id;
    if (!preserveSelection) resetChatTranscriptWindow();
  }
  syncChatStateFromActiveConversation();
  noteConfirmedServerChatState(serverState || currentChatStatePayload());
}
function resetChatTranscriptWindow() {
  chatTranscriptVisibleTurns = CHAT_TRANSCRIPT_INITIAL_TURNS;
  chatTranscriptLastSignature = "";
}
function expandChatTranscriptWindow() {
  chatTranscriptVisibleTurns += CHAT_TRANSCRIPT_EXPAND_STEP;
  renderChatTranscript(false, { reason: "user" });
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
          smartTitleEnabled: true,
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
  chatState.smartTitleEnabled = source.smartTitleEnabled !== false;
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
function conversationHasRuntimeMetrics(conversation) {
  if (!conversation || typeof conversation !== "object") return false;
  return [
    conversation.lastInputTokens,
    conversation.lastOutputTokens,
    conversation.lastTotalTokens,
    conversation.lastPromptTokensPerSecond,
    conversation.lastPromptTokensPerSecondPeak,
    conversation.lastTokensPerSecond,
    conversation.lastTokensPerSecondPeak,
    conversation.lastLatencySeconds,
    conversation.lastTtftSeconds,
    conversation.lastStatus,
    conversation.runtimeSnapshot,
  ].some((value) => value !== undefined && value !== null && value !== "");
}
function blankChatRuntimeStats(runtime) {
  if (!runtime) return null;
  return {
    ...runtime,
    __freshConversationStats: true,
    last_status: undefined,
    last_latency_s: undefined,
    last_ttft_s: undefined,
    last_tokens_per_second: undefined,
    last_input_tokens: 0,
    last_output_tokens: 0,
    last_total_tokens: 0,
    last_tool_calls: 0,
    last_path: "",
    last_request_at: 0,
    prompt_tps: undefined,
    generation_tps: undefined,
    max_prompt_tokens_per_second: undefined,
    max_tokens_per_second: undefined,
    running_requests: 0,
    waiting_requests: 0,
    pending_requests: 0,
    swapped_requests: 0,
    gpu_kv_cache_usage_pct: undefined,
    cpu_kv_cache_usage_pct: undefined,
    prefix_cache_hit_rate_pct: undefined,
    ctx_size_tokens: undefined,
    speculative: undefined,
  };
}
function resetConversationRuntimeMetrics(conversation, runtime = null) {
  if (!conversation || typeof conversation !== "object") return conversation;
  conversation.freshConversationStats = true;
  conversation.lastInputTokens = undefined;
  conversation.lastOutputTokens = undefined;
  conversation.lastTotalTokens = undefined;
  conversation.lastCtxSizeTokens = undefined;
  conversation.lastKvCacheUsagePct = undefined;
  conversation.lastCpuKvCacheUsagePct = undefined;
  conversation.lastPrefixCacheHitRatePct = undefined;
  conversation.lastPromptTokensPerSecond = undefined;
  conversation.lastPromptTokensPerSecondPeak = undefined;
  conversation.lastRuntimeRequestAt = undefined;
  conversation.lastStatus = undefined;
  conversation.lastLatencySeconds = undefined;
  conversation.lastTtftSeconds = undefined;
  conversation.lastTokensPerSecond = undefined;
  conversation.lastTokensPerSecondPeak = undefined;
  conversation.lastToolCalls = undefined;
  conversation.lastRequestPath = undefined;
  conversation.runtimeSnapshot = cloneChatRuntimeSnapshot(
    blankChatRuntimeStats(runtime || activeChatRuntime()),
  );
  return conversation;
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
  conversation.smartTitleEnabled = chatState.smartTitleEnabled !== false;
  conversation.autoCompactEnabled = chatState.autoCompactEnabled !== false;
  conversation.autoCompactThresholdPct = clampChatCompactionThreshold(
    chatState.autoCompactThresholdPct,
  );
  conversation.statsCollapsed = !!chatState.statsCollapsed;
  conversation.transcriptHeightPx = Number(chatState.transcriptHeightPx || 0) || 0;
  conversation.runtimeSnapshot = cloneChatRuntimeSnapshot(conversation.runtimeSnapshot);
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
      currentLogSource === "debug" ||
      currentLogSource === "docker" ||
      String(currentLogSource || "").startsWith("service:")
        ? currentLogSource
        : "docker",
    show_global_logs: !!showGlobalLogs,
    show_global_logs_by_source: { ...showGlobalLogSources },
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
    state.current_log_source === "debug" ||
    state.current_log_source === "docker" ||
    String(state.current_log_source || "").startsWith("service:")
      ? String(state.current_log_source)
      : "docker";
  showGlobalLogs =
    typeof state.show_global_logs === "boolean"
      ? state.show_global_logs
      : showGlobalLogs;
  showGlobalLogSources =
    state.show_global_logs_by_source &&
    typeof state.show_global_logs_by_source === "object"
      ? { ...state.show_global_logs_by_source }
      : showGlobalLogSources;
  window.showGlobalLogSources = showGlobalLogSources;
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
let powerCoolingBusyState = { active: false, message: "" };
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
    if (instanceBusyState.active) {
      if (!el.disabled) el.dataset.busyDisabled = "1";
      el.setAttribute("disabled", "disabled");
      return;
    }
    const keepDisabled = el.dataset.scopeDisabled === "1";
    if (el.dataset.busyDisabled === "1" && !keepDisabled)
      el.removeAttribute("disabled");
    else if (keepDisabled)
      el.setAttribute("disabled", "disabled");
    delete el.dataset.busyDisabled;
  });
  ensurePairManager();
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
    else safeInsertBefore(system, overview, system.children[1] || null);
  }
}
