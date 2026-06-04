// Shared runtime/UI state
let selectedInstance = "GPU0";
let logEs = null;
let logCacheRefreshTimer = null;
let logCacheRefreshNonce = 0;
let statusPollTimer = null;
let initialMetricsSeriesRequested = false;
let selectedUserName = "";
let selectedOverviewInstanceId = "";
let selectedLogInstanceId = "";
let selectedPresetModelId = "";
let selectedPresetModelHydrated = false;
let pendingLogJump = null;
let adminAuthRefreshBlocked = false;
let pendingForcedStatusRefreshIncludeSeries = false;
const SUMMARY_CACHE_KEY = "club3090-preset-summary-v520";
const CHAT_STATE_KEY = "club3090-chat-state-v642";
const LEGACY_CHAT_STATE_KEY = "club3090-chat-state-v520";
const LEGACY_CHAT_STATE_KEY_V516 = "club3090-chat-state-v516";
const CHAT_STATE_KEEPALIVE_MAX_BYTES = 60 * 1024;
const CLUB3090_SCRIPT_VERSION = "__SCRIPT_VERSION__";
const DEBUG_LOGS = !/v\d+\.\d+\.0(?:\D|$)/.test(String(CLUB3090_SCRIPT_VERSION || ""));
const UI_META_SEPARATOR = " \u00B7 ";
const UI_ARROW_UP = "\u2191";
const CHAT_UNTITLED_TITLE = "Untitled conversation";
const CHAT_MIN_COMPACTION_THRESHOLD = 25;
const CHAT_MAX_COMPACTION_THRESHOLD = 95;
const CHAT_AUTO_COMPACT_THRESHOLD_DEFAULT = CHAT_MAX_COMPACTION_THRESHOLD;
const CHAT_THINKING_RENDER_INTERVAL_MS = 250;
const CHAT_STREAM_RENDER_MIN_INTERVAL_MS = 24;
const CHAT_STREAM_MARKDOWN_TAIL_SOFT_LIMIT = 1800;
const CHAT_STREAM_MARKDOWN_TAIL_HARD_LIMIT = 3600;
const CHAT_STREAM_MARKDOWN_RESCAN_APPEND_THRESHOLD = 48;
const CHAT_STREAM_MARKDOWN_RESCAN_TAIL_THRESHOLD = 960;
const CHAT_CONVERSATION_FOLDER_RE = /^[A-Za-z0-9 _-]*$/;
const CHAT_TRANSCRIPT_INITIAL_TURNS = 12;
const CHAT_TRANSCRIPT_EXPAND_STEP = 12;
const STATUS_POLL_FOREGROUND_FAST_MS = 2000;
const STATUS_POLL_FOREGROUND_SLOW_MS = 5000;
const STATUS_POLL_BACKGROUND_MS = 15000;
const LOG_CACHE_REFRESH_MS = 15000;
const CHAT_TRANSCRIPT_NEAR_BOTTOM_PX = 36;
const CHAT_TRANSCRIPT_DETACH_SCROLL_PX = 18;
const CHAT_TRANSCRIPT_REATTACH_SCROLL_PX = 160;
const CHAT_RUNTIME_SNAPSHOT_FIELDS = [
  "id",
  "instance_id",
  "selector",
  "mode",
  "engine",
  "display_name",
  "container",
  "served_model_name",
  "model_id",
  "gpu_indices",
  "port",
  "waiting_requests",
  "pending_requests",
  "swapped_requests",
  "running_requests",
  "last_status",
  "last_latency_s",
  "last_ttft_s",
  "last_tokens_per_second",
  "last_input_tokens",
  "last_output_tokens",
  "last_total_tokens",
  "last_tool_calls",
  "last_path",
  "last_request_at",
  "prompt_tps",
  "generation_tps",
  "ctx_size_tokens",
  "gpu_kv_cache_usage_pct",
  "cpu_kv_cache_usage_pct",
  "prefix_cache_hit_rate_pct",
  "max_prompt_tokens_per_second",
  "max_tokens_per_second",
  "speculative",
];
let presetSummaryCache = { persistent: {}, transient: {}, restartTargets: [], lastSeenUptime: 0 };
let chatStateServerReady = false;
let chatStateSaveTimer = null;
let lastQueuedChatStateJson = "";
let chatStateSaveController = null;
let chatStateSavePromise = null;
let chatStateHydrated = false;
let chatStateHydratingPromise = null;
let chatHydratedServerConversationCount = 0;
let chatHydratedServerRevision = 0;
let chatTranscriptVisibleTurns = CHAT_TRANSCRIPT_INITIAL_TURNS;
let chatTranscriptLastSignature = "";
let chatMarkdownRenderEpoch = 0;
const chatMarkdownRenderCache = new Map();
let chatTranscriptAutoFollow = true;
let chatTranscriptScrollTop = 0;
let chatTranscriptUserDetached = false;
let chatTranscriptReattachTravelPx = 0;
let chatTranscriptProgrammaticScroll = false;
let chatLiveMessageRenderScheduled = false;
let chatLiveMessageRenderPendingIndex = -1;
let chatLiveMessageRenderPendingForceFollow = false;
let chatLiveMessageRenderPendingReason = "stream";
let chatLiveMessageRenderLastAt = 0;
let chatLocalRequestActive = false;
let chatStreamResumePollTimer = null;
let chatStreamResumePollNonce = 0;
let chatStreamingPersistTimer = null;
let chatTranscriptStreamingHeightLock = 0;
let chatTranscriptStreamingHeightLockActive = false;
const CODE_SYNTAX_CONFIG = null; // injected by build.py from code_syntax.json
const CODE_SYNTAX_CONFIG_URL = "/admin/code-syntax";
let codeSyntaxConfigPromise = null;
let codeSyntaxThemeApplied = false;
let codeSyntaxThemeTokenNames = new Set();
const codeSyntaxHighlightQueue = new Set();
let codeSyntaxHighlightScheduled = false;
let activeResizeSession = null;
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
  const row =
    message && typeof message === "object" ? { ...message } : {};
  delete row.__clubMarkdownStream;
  return {
    ...row,
    role: String(row?.role || "user"),
    text: String(row?.text || ""),
    attachments: Array.isArray(row?.attachments)
      ? row.attachments.map(cloneChatAttachment)
      : [],
    reasoningText: String(row?.reasoningText || ""),
    reasoning_content: String(row?.reasoning_content || ""),
    reasoning: String(row?.reasoning || ""),
    modelLabel: String(row?.modelLabel || ""),
    inputTokens:
      row?.inputTokens !== undefined ? Number(row.inputTokens || 0) : undefined,
    inputTokensEstimate:
      row?.inputTokensEstimate !== undefined
        ? Number(row.inputTokensEstimate || 0)
        : undefined,
    inputTokensApprox:
      row?.inputTokensApprox !== undefined ? !!row.inputTokensApprox : undefined,
    outputTokens:
      row?.outputTokens !== undefined ? Number(row.outputTokens || 0) : undefined,
    ttftSeconds:
      row?.ttftSeconds !== undefined ? Number(row.ttftSeconds || 0) : undefined,
    tokensPerSecond:
      row?.tokensPerSecond !== undefined
        ? Number(row.tokensPerSecond || 0)
        : undefined,
    maxTokensPerSecond:
      row?.maxTokensPerSecond !== undefined
        ? Number(row.maxTokensPerSecond || 0)
        : undefined,
  };
}
function cloneChatMessages(messages = []) {
  return Array.isArray(messages) ? messages.map(cloneChatMessage) : [];
}
function cloneChatRuntimeSnapshot(snapshot = null) {
  if (!snapshot || typeof snapshot !== "object") return undefined;
  const next = {};
  CHAT_RUNTIME_SNAPSHOT_FIELDS.forEach((field) => {
    if (snapshot[field] === undefined) return;
    if (field === "gpu_indices") {
      next.gpu_indices = Array.isArray(snapshot.gpu_indices)
        ? snapshot.gpu_indices
            .map((value) => Number(value))
            .filter((value) => Number.isFinite(value))
        : [];
      return;
    }
    if (field === "speculative") {
      const speculative = snapshot.speculative;
      if (!speculative || typeof speculative !== "object") return;
      next.speculative = {
        drafted_tokens:
          speculative.drafted_tokens !== undefined
            ? Number(speculative.drafted_tokens || 0)
            : undefined,
        draft_tokens:
          speculative.draft_tokens !== undefined
            ? Number(speculative.draft_tokens || 0)
            : undefined,
        accepted_tokens:
          speculative.accepted_tokens !== undefined
            ? Number(speculative.accepted_tokens || 0)
            : undefined,
        accept_rate_pct:
          speculative.accept_rate_pct !== undefined
            ? Number(speculative.accept_rate_pct || 0)
            : undefined,
        mean_acceptance_length:
          speculative.mean_acceptance_length !== undefined
            ? Number(speculative.mean_acceptance_length || 0)
            : undefined,
        system_efficiency_pct:
          speculative.system_efficiency_pct !== undefined
            ? Number(speculative.system_efficiency_pct || 0)
            : undefined,
      };
      return;
    }
    next[field] = snapshot[field];
  });
  return Object.keys(next).length ? next : undefined;
}
function buildConversationRuntimeSnapshot(runtime = null, conversation = null) {
  const base = cloneChatRuntimeSnapshot(runtime) || {};
  if (conversation) {
    if (conversation.lastStatus !== undefined) base.last_status = conversation.lastStatus;
    if (conversation.lastLatencySeconds !== undefined)
      base.last_latency_s = conversation.lastLatencySeconds;
    if (conversation.lastTtftSeconds !== undefined)
      base.last_ttft_s = conversation.lastTtftSeconds;
    if (conversation.lastTokensPerSecond !== undefined)
      base.last_tokens_per_second = conversation.lastTokensPerSecond;
    if (conversation.lastInputTokens !== undefined)
      base.last_input_tokens = conversation.lastInputTokens;
    if (conversation.lastOutputTokens !== undefined)
      base.last_output_tokens = conversation.lastOutputTokens;
    if (conversation.lastTotalTokens !== undefined)
      base.last_total_tokens = conversation.lastTotalTokens;
    if (conversation.totalInputTokens !== undefined)
      base.total_input_tokens = conversation.totalInputTokens;
    if (conversation.totalOutputTokens !== undefined)
      base.total_output_tokens = conversation.totalOutputTokens;
    if (conversation.totalTokens !== undefined)
      base.total_tokens = conversation.totalTokens;
    if (conversation.lastCtxSizeTokens !== undefined)
      base.ctx_size_tokens = conversation.lastCtxSizeTokens;
    if (conversation.lastPromptTokensPerSecond !== undefined) {
      base.prompt_tps = conversation.lastPromptTokensPerSecond;
      base.last_prompt_tps = conversation.lastPromptTokensPerSecond;
    } else if (base.prompt_tps === undefined && base.last_prompt_tps === undefined) {
      const derivedPromptTps = deriveRuntimePromptTps({
        ...base,
        last_input_tokens: conversation.lastInputTokens,
        last_output_tokens: conversation.lastOutputTokens,
        last_ttft_s: conversation.lastTtftSeconds,
        last_latency_s: conversation.lastLatencySeconds,
        last_tokens_per_second: conversation.lastTokensPerSecond,
      });
      if (derivedPromptTps !== null) {
        base.prompt_tps = derivedPromptTps;
        base.last_prompt_tps = derivedPromptTps;
      }
    }
    if (conversation.lastPromptTokensPerSecondPeak !== undefined)
      base.max_prompt_tokens_per_second = conversation.lastPromptTokensPerSecondPeak;
    if (conversation.lastKvCacheUsagePct !== undefined)
      base.gpu_kv_cache_usage_pct = conversation.lastKvCacheUsagePct;
    if (conversation.lastCpuKvCacheUsagePct !== undefined)
      base.cpu_kv_cache_usage_pct = conversation.lastCpuKvCacheUsagePct;
    if (conversation.lastPrefixCacheHitRatePct !== undefined)
      base.prefix_cache_hit_rate_pct = conversation.lastPrefixCacheHitRatePct;
    if (conversation.lastToolCalls !== undefined)
      base.last_tool_calls = conversation.lastToolCalls;
    if (conversation.lastRequestPath !== undefined)
      base.last_path = conversation.lastRequestPath;
    if (conversation.lastRuntimeRequestAt !== undefined)
      base.last_request_at = conversation.lastRuntimeRequestAt;
    base.max_tokens_per_second = Math.max(
      Number(conversation.lastTokensPerSecondPeak || 0),
      Number(base.last_tokens_per_second || 0),
      Number(base.generation_tps || 0),
    );
  }
  return Object.keys(base).length ? base : null;
}
function clearChatMarkdownRenderCache() {
  chatMarkdownRenderCache.clear();
  clearAllChatStreamingMarkdownState();
  chatMarkdownRenderEpoch += 1;
}
function clearChatStreamingMarkdownState(message) {
  if (message && typeof message === "object" && message.__clubMarkdownStream) {
    delete message.__clubMarkdownStream;
  }
}
function clearAllChatStreamingMarkdownState() {
  (chatState.messages || []).forEach((message) =>
    clearChatStreamingMarkdownState(message),
  );
}
function chatConversationSummaryPayload(conversation) {
  return {
    id: String(conversation?.id || chatConversationId()),
    title:
      String(conversation?.title || "").trim() || CHAT_UNTITLED_TITLE,
    folder: normalizeConversationFolder(conversation?.folder || ""),
    updatedAt: Number(conversation?.updatedAt || Date.now()),
    lastUsedAt: Number(conversation?.lastUsedAt || Date.now()),
    createdAt: Number(conversation?.createdAt || Date.now()),
    summary: String(conversation?.summary || ""),
    autoNamed: !!conversation?.autoNamed,
    smartTitleEnabled: conversation?.smartTitleEnabled !== false,
    archivedAt:
      conversation?.archivedAt !== undefined
        ? Number(conversation.archivedAt || 0)
        : undefined,
    messagesLoaded: false,
  };
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
                smartTitleEnabled: conversation?.smartTitleEnabled !== false,
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
                lastCpuKvCacheUsagePct:
                  conversation?.lastCpuKvCacheUsagePct !== undefined
                    ? conversation.lastCpuKvCacheUsagePct
                    : undefined,
                lastPrefixCacheHitRatePct:
                  conversation?.lastPrefixCacheHitRatePct !== undefined
                    ? conversation.lastPrefixCacheHitRatePct
                    : undefined,
                lastPromptTokensPerSecond:
                  conversation?.lastPromptTokensPerSecond !== undefined
                    ? conversation.lastPromptTokensPerSecond
                    : undefined,
                lastPromptTokensPerSecondPeak:
                  conversation?.lastPromptTokensPerSecondPeak !== undefined
                    ? conversation.lastPromptTokensPerSecondPeak
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
                runtimeSnapshot: cloneChatRuntimeSnapshot(conversation?.runtimeSnapshot),
                transcriptHeightPx:
                  conversation?.transcriptHeightPx !== undefined
                    ? Number(conversation.transcriptHeightPx || 0)
                    : undefined,
                archivedAt:
                  conversation?.archivedAt !== undefined
                    ? Number(conversation.archivedAt || 0)
                    : undefined,
                messagesLoaded: true,
              }
            : chatConversationSummaryPayload(conversation)),
          folder: normalizeConversationFolder(conversation?.folder || ""),
          title:
            String(conversation?.title || "").trim() || CHAT_UNTITLED_TITLE,
        }))
      : [],
    archivedConversations: Array.isArray(chatState.archivedConversations)
      ? chatState.archivedConversations.map((conversation) =>
          chatConversationSummaryPayload(conversation),
        )
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
function chatConversationCountFromState(stateLike) {
  const activeCount = Array.isArray(stateLike?.conversations) ? stateLike.conversations.length : 0;
  const archivedCount = Array.isArray(stateLike?.archivedConversations)
    ? stateLike.archivedConversations.length
    : 0;
  return activeCount + archivedCount;
}
function clearLegacyChatStateCaches() {
  try {
    localStorage.removeItem(LEGACY_CHAT_STATE_KEY);
    localStorage.removeItem(LEGACY_CHAT_STATE_KEY_V516);
  } catch (e) {}
}
function syncLocalChatStateCache() {
  try {
    localStorage.setItem(CHAT_STATE_KEY, JSON.stringify(currentChatStatePayload()));
    clearLegacyChatStateCaches();
  } catch (e) {}
}
function suspiciousConversationDrop(payload, options = {}) {
  if (options.allowConversationLoss) return false;
  if (!chatStateHydrated || chatHydrationPending()) return true;
  const nextCount = chatConversationCountFromState(payload);
  if (chatHydratedServerConversationCount >= 3 && nextCount + 1 < chatHydratedServerConversationCount) {
    return true;
  }
  return false;
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
function noteConfirmedServerChatState(stateLike) {
  chatHydratedServerConversationCount = chatConversationCountFromState(stateLike);
  chatHydratedServerRevision = Math.max(
    0,
    Number(stateLike?.revision || chatHydratedServerRevision || 0) || 0,
  );
  chatStateServerReady = true;
}
function chatStatePayloadByteLength(nextJson) {
  const text = String(nextJson || "");
  try {
    if (typeof TextEncoder !== "undefined") return new TextEncoder().encode(text).length;
  } catch (e) {}
  try {
    if (typeof Blob !== "undefined") return new Blob([text]).size;
  } catch (e) {}
  return text.length;
}
async function postChatStateToServer(nextJson, controller) {
  const requestOptions = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: nextJson,
    signal: controller.signal,
  };
  if (chatStatePayloadByteLength(nextJson) <= CHAT_STATE_KEEPALIVE_MAX_BYTES) {
    requestOptions.keepalive = true;
  }
  const response = await fetch("/admin/chat-state", requestOptions);
  let payload = null;
  try {
    payload = await response.json();
  } catch (e) {}
  if (!response.ok || payload?.ok === false || !payload?.state) {
    throw new Error(payload?.error || `Failed to save chat state (${response.status}).`);
  }
  noteConfirmedServerChatState(payload.state);
  return payload.state;
}
async function flushServerChatStateSave(payload = currentChatStatePayload()) {
  if (!chatStateServerReady) return null;
  if (suspiciousConversationDrop(payload, { allowConversationLoss: false })) {
    logDebugEvent("chat_state_flush_blocked", {
      reason: "suspicious_drop",
      hydratedConversationCount: chatHydratedServerConversationCount,
      nextConversationCount: chatConversationCountFromState(payload),
      revision: Number(payload?.revision || 0),
    });
    return null;
  }
  cancelPendingServerChatStateSave();
  const nextJson = JSON.stringify(payload || {});
  lastQueuedChatStateJson = nextJson;
  const controller = new AbortController();
  chatStateSaveController = controller;
  const savePromise = postChatStateToServer(nextJson, controller)
    .catch((error) => {
      lastQueuedChatStateJson = "";
      logDebugEvent("chat_state_save_error", {
        error: error?.message || String(error || ""),
        revision: Number(payload?.revision || 0),
        conversationCount: chatConversationCountFromState(payload),
      });
      throw error;
    })
    .finally(() => {
      if (chatStateSaveController === controller) chatStateSaveController = null;
      if (chatStateSavePromise === savePromise) chatStateSavePromise = null;
    });
  chatStateSavePromise = savePromise;
  return savePromise;
}
function queueServerChatStateSave(payload = currentChatStatePayload()) {
  if (!chatStateServerReady) return;
  if (suspiciousConversationDrop(payload)) {
    logDebugEvent("chat_state_save_blocked", {
      reason: "suspicious_drop",
      hydratedConversationCount: chatHydratedServerConversationCount,
      nextConversationCount: chatConversationCountFromState(payload),
      revision: Number(payload?.revision || 0),
    });
    return;
  }
  const nextJson = JSON.stringify(payload || {});
  if (nextJson === lastQueuedChatStateJson) return;
  lastQueuedChatStateJson = nextJson;
  if (chatStateSaveTimer) clearTimeout(chatStateSaveTimer);
  chatStateSaveTimer = setTimeout(() => {
    const controller = new AbortController();
    if (chatStateSaveController) {
      try {
        chatStateSaveController.abort();
      } catch (e) {}
    }
    chatStateSaveController = controller;
    const savePromise = postChatStateToServer(nextJson, controller)
      .catch((error) => {
        if (error?.name === "AbortError") return null;
        lastQueuedChatStateJson = "";
        logDebugEvent("chat_state_save_error", {
          error: error?.message || String(error || ""),
          revision: Number(payload?.revision || 0),
          conversationCount: chatConversationCountFromState(payload),
        });
        return null;
      })
      .finally(() => {
        if (chatStateSaveController === controller) chatStateSaveController = null;
        if (chatStateSavePromise === savePromise) chatStateSavePromise = null;
      });
    chatStateSavePromise = savePromise;
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
  const archivedAt =
    seed.archivedAt !== undefined && seed.archivedAt !== null && seed.archivedAt !== ""
      ? Number(seed.archivedAt || 0)
      : undefined;
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
    smartTitleEnabled:
      seed.smartTitleEnabled !== undefined
        ? !!seed.smartTitleEnabled
        : base.smartTitleEnabled !== false,
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
    lastCpuKvCacheUsagePct:
      seed.lastCpuKvCacheUsagePct !== undefined
        ? Number(seed.lastCpuKvCacheUsagePct || 0)
        : undefined,
    lastPrefixCacheHitRatePct:
      seed.lastPrefixCacheHitRatePct !== undefined
        ? Number(seed.lastPrefixCacheHitRatePct || 0)
        : undefined,
    lastPromptTokensPerSecond:
      seed.lastPromptTokensPerSecond !== undefined
        ? Number(seed.lastPromptTokensPerSecond || 0)
        : undefined,
    lastPromptTokensPerSecondPeak:
      seed.lastPromptTokensPerSecondPeak !== undefined
        ? Number(seed.lastPromptTokensPerSecondPeak || 0)
        : undefined,
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
    totalInputTokens:
      seed.totalInputTokens !== undefined ? Number(seed.totalInputTokens || 0) : undefined,
    totalOutputTokens:
      seed.totalOutputTokens !== undefined ? Number(seed.totalOutputTokens || 0) : undefined,
    totalTokens:
      seed.totalTokens !== undefined ? Number(seed.totalTokens || 0) : undefined,
    runtimeSnapshot: cloneChatRuntimeSnapshot(seed.runtimeSnapshot),
    generationActive: !!seed.generationActive,
    transcriptHeightPx:
      seed.transcriptHeightPx !== undefined
        ? Number(seed.transcriptHeightPx || 0)
        : undefined,
    transcriptAutoscroll:
      seed.transcriptAutoscroll !== undefined
        ? !!seed.transcriptAutoscroll
        : base.transcriptAutoscroll !== false,
    archivedAt,
    messagesLoaded: seed.messagesLoaded === false ? false : true,
  };
}
let chatState = {
  revision: 0,
  activeConversationId: "",
  conversations: [],
   archivedConversations: [],
  presetId: "",
  apiPresetName: "",
  messages: [],
  attachments: [],
  busy: false,
  params: defaultChatParams(),
  systemPrompt: "",
  smartTitleEnabled: true,
  autoCompactEnabled: true,
  autoCompactThresholdPct: CHAT_MAX_COMPACTION_THRESHOLD,
  statsCollapsed: false,
  transcriptHeightPx: 0,
  promptTemplates: [],
};
let chatOptionsMenuOpen = false;
let chatDeleteModifierActive = false;
let chatDeleteLongPressTimer = null;
let chatDeleteLongPressTriggered = false;
let mcpManagerState = { servers: [], editingId: "" };
let chatSettingsDraft = null;
let chatRecognition = null;
let chatRequestController = null;
let chatRuntimeStatsRenderTimer = null;
let chatRuntimeStatsRenderLastAt = 0;
let chatAutoTitleGenerationId = 0;
let chatThinkingTicker = null;
let chatTranscriptRenderScheduled = false;
let chatTranscriptRenderPending = false;
let chatTranscriptRenderPendingForceFollow = false;
let chatTranscriptRenderPendingReason = "update";
let chatTranscriptRenderLastAt = 0;
let statusPollNonce = 0;
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
  if (name === "restore")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 7H5v4m0-4 4 4m-4-4a8 8 0 1 1-1 9" fill="none"/></svg>';
  if (name === "delete")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M9 7V5h6v2m-7 3v7m4-7v7m4-7v7M7 7l1 12h8l1-12" fill="none"/></svg>';
  if (name === "archive")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16v3H4zm2 3h12v9H6zm4 3h4" fill="none"/></svg>';
  if (name === "copy")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 9h10v10H9zM5 15H4V5h10v1" fill="none"/></svg>';
  if (name === "cut")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="6" cy="18" r="2.5" fill="none"/><circle cx="6" cy="6" r="2.5" fill="none"/><path d="M8.5 7.5 20 18M8.5 16.5 13 12l7-6" fill="none"/></svg>';
  if (name === "file")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h7l5 5v13H7zM14 3v5h5" fill="none"/></svg>';
  if (name === "folder")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h6l2 2h10v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" fill="none"/></svg>';
  if (name === "folder-up")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 8h5.7l2.6 2.8h8.7v7.4h-4.1M3.5 8v9.2c0 .7.6 1.3 1.3 1.3h5.1" fill="none" stroke-linejoin="round"/><path d="M13.2 18.8v-7m0 0-3.1 3.1m3.1-3.1 3.1 3.1" fill="none" stroke-linecap="square" stroke-linejoin="miter"/></svg>';
  if (name === "mount")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v10m0 0-4-4m4 4 4-4M5 20h14" fill="none"/></svg>';
  if (name === "unmount")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 20h14M8 8l8 8M16 8l-8 8" fill="none"/></svg>';
  if (name === "upload")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4m0 0l-4 4m4-4l4 4M5 20h14" fill="none"/></svg>';
  if (name === "download")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v12m0 0l-4-4m4 4l4-4M5 20h14" fill="none"/></svg>';
  if (name === "paste")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4h6v3H9zM7 7h10v13H7zM9 11h6M9 15h4" fill="none"/></svg>';
  if (name === "save")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h11l3 3v11H5zm3 0v5h8V6.5M9 19v-5h6v5" fill="none"/></svg>';
  if (name === "undo")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 9H5v4m0-4 4 4m-4-4c1.8-2 4.2-3 7-3c4.8 0 8 3 8 8" fill="none"/></svg>';
  if (name === "redo")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 9h4v4m0-4-4 4m4-4c-1.8-2-4.2-3-7-3c-4.8 0-8 3-8 8" fill="none"/></svg>';
  if (name === "wrap")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h12a4 4 0 1 1 0 8H9m0 0 3-3m-3 3 3 3M4 11h8M4 15h5" fill="none"/></svg>';
  if (name === "hex")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h6v10H4zM14 7h6v10h-6zM10 12h4" fill="none"/></svg>';
  if (name === "vector")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 17 7M7 17h10V7" fill="none"/><circle cx="7" cy="17" r="2" fill="currentColor" stroke="none"/><circle cx="17" cy="7" r="2" fill="currentColor" stroke="none"/><circle cx="17" cy="17" r="2" fill="currentColor" stroke="none"/></svg>';
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
  if (name === "view")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.6-6 9.5-6 9.5 6 9.5 6-3.6 6-9.5 6-9.5-6-9.5-6Z" fill="none"/><circle cx="12" cy="12" r="3.25" fill="none"/></svg>';
  if (name === "preview")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.6-6 9.5-6 9.5 6 9.5 6-3.6 6-9.5 6-9.5-6-9.5-6Z" fill="none"/><circle cx="12" cy="12" r="3.25" fill="none"/></svg>';
  if (name === "hide")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.6-6 9.5-6 9.5 6 9.5 6-3.6 6-9.5 6-9.5-6-9.5-6Z" fill="none"/><circle cx="12" cy="12" r="3.25" fill="none"/><path d="M4 20 20 4" fill="none"/></svg>';
  if (name === "chevron-up")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 15 6-6 6 6" fill="none"/></svg>';
  if (name === "chevron-down")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" fill="none"/></svg>';
  if (name === "chevron-right")
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6" fill="none"/></svg>';
  return "";
}
function renderIconButton({ title, action, icon, className = "", disabled = false }) {
  const classes = `iconbtn ${className}`.trim();
  const disabledAttr = disabled ? ' disabled aria-disabled="true"' : "";
  const onclickAttr = disabled ? "" : ` onclick="${action}"`;
  return `<button class="${classes}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}"${disabledAttr}${onclickAttr}>${svgIcon(icon)}</button>`;
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
  modal.innerHTML = `<div class="club-modal-card" role="dialog" aria-modal="true" aria-labelledby="apiKeyModalTitle"><div class="panel-head"><h2 id="apiKeyModalTitle">API Key</h2><button class="plain-close-btn" id="apiKeyModalTopClose" title="Close" aria-label="Close" onclick="closeApiKeyModal()">✕</button></div><div class="preset-help" id="apiKeyModalHint">Use Copy to place the key on the clipboard.</div><textarea id="apiKeyModalValue" class="modal-keybox" readonly wrap="off"></textarea><div class="preset-form-actions"><button class="btn amber" onclick="copyApiKeyModalValue()">Copy</button><button class="btn blue" onclick="closeApiKeyModal()">Close</button></div><div class="msg" id="apiKeyModalMsg"></div></div>`;
  document.body.appendChild(modal);
}
let apiKeyModalOptions = {
  copySuccessText: "Copied API key to clipboard.",
  showTopClose: true,
};
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
  modal.innerHTML = `<div class="club-modal-card" role="dialog" aria-modal="true" aria-labelledby="externalLinkTitle"><div class="panel-head"><h2 id="externalLinkTitle">Open Link</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeExternalLinkModal()">✕</button></div><div class="preset-help">Detected external link. Open it in a new browser tab?</div><textarea id="externalLinkValue" class="modal-keybox" readonly wrap="off"></textarea><div class="preset-form-actions"><button class="btn blue" onclick="closeExternalLinkModal()">Cancel</button><button class="btn green" onclick="confirmExternalLinkVisit()">Visit</button></div></div>`;
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
    if (typeof applyDirectoryPayload === "function") applyDirectoryPayload(j);
    resetUserForm(true);
    setUsersMsg("Saved user " + j.user.name);
    refreshStatus({ force: true }).catch(() => {});
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
  if (!(await openClubConfirmModal("Reset API key for " + name + "?"))) return;
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
    if (typeof applyDirectoryPayload === "function") applyDirectoryPayload(j);
    setUsersMsg("Reset API key for " + name);
    refreshStatus({ force: true }).catch(() => {});
  } catch (e) {
    alert("API key reset failed: " + e);
  }
}
async function deleteUserByName(name) {
  if (!(await openClubConfirmModal("Delete user " + name + "?"))) return;
  try {
    const r = await fetch("/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "delete", name }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "delete failed");
    if (typeof applyDirectoryPayload === "function") applyDirectoryPayload(j);
    if (selectedUserName === name) resetUserForm();
    setUsersMsg("Deleted user " + name);
    refreshStatus({ force: true }).catch(() => {});
  } catch (e) {
    alert("User delete failed: " + e);
  }
}
function setAuditMsg(t) {
  if ($("auditMsg")) $("auditMsg").textContent = t || "";
}
function renderUpdateNotices(status = {}) {
  const host = $("updateNoticeHost");
  if (!host) return;
  const remote = status.remote_update || {};
  const compat = status.club3090_compat || {};
  const supported = compat.supported || {};
  const updateActive = selfUpdateActive(status);
  const startedAt = Number(status.control_started_at || 0);
  const remoteKey = currentUpdateBannerRemoteKey(status);
  const hasUpdate = !!remote.update_available && remote.script_version;
  const dismissed = readUpdateBannerDismissed(startedAt, remoteKey);
  const greenBar =
    hasUpdate && !dismissed && !updateActive
      ? `<div class="update-notice-bar update-notice-bar-green"><button class="update-notice-dismiss" onclick="dismissUpdateNotice()" aria-label="Dismiss update notice">✕</button><button class="update-notice-message" onclick="openUpdateNoticeModal()">${escapeHtml(`A new update is Available (${remote.script_version})!`)} — Click here to update now</button><span class="update-notice-spacer"></span></div>`
      : "";
  const compatButton = updateActive
    ? '<button class="update-notice-link" type="button" disabled aria-disabled="true">Compatible migration unavailable while an update is running.</button>'
    : '<button class="update-notice-link" onclick="startCompatibleMigration()">Click here to migrate to a compatible version!</button>';
  const redBar = compat.local_repo_newer_than_supported
    ? `<div class="update-notice-bar update-notice-bar-red"><span class="update-notice-spacer"></span><div class="update-notice-message">The local Club-3090 commit is newer than supported by this script and may cause unforeseen issues. ${compatButton}</div><span class="update-notice-spacer"></span></div>`
    : "";
  host.innerHTML = `${greenBar}${redBar}`;
}
function dismissUpdateNotice() {
  if (!lastStatus) return;
  writeUpdateBannerDismissed(lastStatus.control_started_at, currentUpdateBannerRemoteKey(lastStatus));
  renderUpdateNotices(lastStatus);
}
function openUpdateNoticeModal() {
  const host = $("updateNoticeHost");
  if (host) host.innerHTML = "";
  promptUpdateRun();
}
function renderUpdateButton(status = {}) {
  const button = $("systemUpdateBtn");
  if (!button) return;
  const updateActive = selfUpdateActive(status);
  const hasUpdate = !!(status.remote_update && status.remote_update.update_available);
  button.textContent = updateActive ? "Update Running..." : hasUpdate ? "⚠️ UPDATE AVAILABLE!" : "Update";
  button.className = hasUpdate ? "btn blue btn-update-available" : "btn blue";
  button.disabled = updateActive;
}
function parseClientScriptVersionTuple(value) {
  const match = String(value || "")
    .trim()
    .match(/v?(\d+)\.(\d+)\.(\d+)([a-z]*)\s*$/);
  if (!match) return null;
  const suffix = String(match[4] || "");
  const suffixRank = suffix
    .split("")
    .reduce((total, char) => total * 26 + (char.charCodeAt(0) - 96), 0);
  return [Number(match[1]), Number(match[2]), Number(match[3]), suffixRank];
}
function compareClientScriptVersions(left, right) {
  const leftTuple = parseClientScriptVersionTuple(left);
  const rightTuple = parseClientScriptVersionTuple(right);
  if (!leftTuple || !rightTuple) return 0;
  for (let index = 0; index < 4; index += 1) {
    if (leftTuple[index] === rightTuple[index]) continue;
    return leftTuple[index] > rightTuple[index] ? 1 : -1;
  }
  return 0;
}
function normalizeChangelogBulletText(text) {
  return String(text || "")
    .trim()
    .replace(/^[-•]\s+/, "")
    .trim();
}
function filterChangelogSinceVersion(text, currentVersion, sectionVersion = "") {
  const content = String(text || "").trim();
  if (!content) return "";
  const runningVersion = String(currentVersion || "").trim();
  const latestVersion = String(sectionVersion || "").trim();
  if (latestVersion && runningVersion && compareClientScriptVersions(latestVersion, runningVersion) <= 0) {
    return "";
  }
  const lines = content.split(/\r?\n/);
  const filtered = [];
  let currentSection = latestVersion;
  let includeSection =
    !runningVersion ||
    !currentSection ||
    compareClientScriptVersions(currentSection, runningVersion) > 0;
  lines.forEach((line) => {
    const trimmed = String(line || "").trim();
    if (/^v\d+\.\d+\.\d+[a-z]*$/.test(trimmed)) {
      currentSection = trimmed;
      includeSection =
        !runningVersion || compareClientScriptVersions(currentSection, runningVersion) > 0;
      if (includeSection) filtered.push(trimmed);
      return;
    }
    if (!includeSection) return;
    if (!trimmed) {
      if (filtered.length && filtered[filtered.length - 1] !== "") filtered.push("");
      return;
    }
    filtered.push(
      trimmed.startsWith("- ") || trimmed.startsWith("• ")
        ? `• ${normalizeChangelogBulletText(trimmed)}`
        : trimmed,
    );
  });
  return filtered.join("\n").trim();
}
function formatChangelogText(text, fallback) {
  const value = String(text || "").trim();
  const content = String(value || fallback || "").trim();
  if (!content) return "";
  const lines = content.split(/\r?\n/);
  const parts = [];
  let list = [];
  const flushList = () => {
    if (!list.length) return;
    parts.push(`<ul class="update-changelog-bullets">${list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`);
    list = [];
  };
  lines.forEach((line) => {
    const trimmed = String(line || "").trim();
    if (!trimmed) {
      flushList();
      return;
    }
    if (/^v\d+\.\d+\.\d+[a-z]*$/.test(trimmed)) {
      flushList();
      parts.push(`<div class="update-changelog-version">${escapeHtml(trimmed)}</div>`);
      return;
    }
    if (trimmed.startsWith("- ") || trimmed.startsWith("• ")) {
      list.push(normalizeChangelogBulletText(trimmed));
      return;
    }
    flushList();
    parts.push(`<div>${escapeHtml(trimmed)}</div>`);
  });
  flushList();
  return parts.join("");
}
function triggerAdminPanelReload(message = "Reloading the admin panel...", delayMs = 250) {
  if (updateMonitor.reloadScheduled) return;
  updateMonitor.reloadScheduled = true;
  setAuditMsg(message);
  const startedAt = Date.now();
  const navigate = () => {
    const target = `/admin?_=${Date.now()}`;
    window.location.href = target;
  };
  const tryReload = async () => {
    if (Date.now() - startedAt > 30000) {
      navigate();
      return;
    }
    try {
      const response = await fetch(`/admin/status?force=1&_=${Date.now()}`, {
        cache: "no-store",
      });
      if (response.ok || response.status === 401 || response.status === 403) {
        navigate();
        return;
      }
    } catch (e) {}
    window.setTimeout(tryReload, 900);
  };
  window.setTimeout(tryReload, Math.max(0, Number(delayMs || 0)));
}
function currentRemoteUpdateVersionInfo() {
  const remote = (lastStatus && lastStatus.remote_update) || {};
  const runningVersion = String(lastStatus?.script_version || "").trim();
  const remoteVersion = String(remote.script_version || "").trim();
  const comparable =
    !!runningVersion &&
    !!remoteVersion &&
    !!parseClientScriptVersionTuple(runningVersion) &&
    !!parseClientScriptVersionTuple(remoteVersion);
  const comparison = comparable
    ? compareClientScriptVersions(remoteVersion, runningVersion)
    : null;
  return {
    runningVersion,
    remoteVersion,
    comparable,
    comparison,
    needsConfirmation: comparable && comparison !== null && comparison <= 0,
  };
}
function promptStaleUpdateConfirmation(scope, targetCommit = "") {
  const versionInfo = currentRemoteUpdateVersionInfo();
  const remoteVersion = versionInfo.remoteVersion || "unknown";
  const runningVersion = versionInfo.runningVersion || "unknown";
  const sameVersion = Number(versionInfo.comparison || 0) === 0;
  openPresetActionModal({
    title: sameVersion ? "Confirm Same-Version Update" : "Confirm Downgrade",
    body: sameVersion
      ? `The remote installer currently resolves to <code>${escapeHtml(remoteVersion)}</code>, which matches the running admin script version <code>${escapeHtml(runningVersion)}</code>. This usually means the remote cache is still stale. Continue anyway?`
      : `The remote installer currently resolves to <code>${escapeHtml(remoteVersion)}</code>, which is older than the running admin script version <code>${escapeHtml(runningVersion)}</code>. Continue only if you intentionally want to downgrade or test a stale remote copy.`,
    confirmLabel: sameVersion ? "Continue Anyway" : "Downgrade Anyway",
    confirmClass: "orange",
    onConfirm: async () => {
      await startUpdateFlow(scope, targetCommit, { skipVersionGuard: true });
    },
  });
}
function completeUpdateMonitor(payload = {}) {
  endUpdateMonitor();
  const returnCode = Number(payload?.return_code || 0);
  triggerAdminPanelReload(
    returnCode === 0
      ? "Update completed. Reloading the admin panel..."
      : `Update finished with status ${payload?.status || "failed"}. Reloading the admin panel...`,
    400,
  );
}
async function startCompatibleMigration() {
  const compat = (lastStatus && lastStatus.club3090_compat) || {};
  const supported = compat.supported || {};
  const targetCommit = String(supported.commit || "").trim();
  if (!targetCommit) throw new Error("No compatible Club-3090 commit is recorded in this script.");
  await startUpdateFlow("club3090-compatible", targetCommit);
}
function updateLogVisualMode() {
  const box = $("log");
  if (!box) return;
  box.classList.toggle("log-update", currentLogSource === "update");
}
function endUpdateMonitor() {
  updateMonitor.active = false;
  updateMonitor.completed = true;
  setUpdateUiLocked(false);
  if (updateMonitor.statusTimer) {
    clearInterval(updateMonitor.statusTimer);
    updateMonitor.statusTimer = null;
  }
  updateLogVisualMode();
}
async function pollUpdateMonitorStatus() {
  if (!updateMonitor.active || !updateMonitor.statusUrl) return;
  try {
    const response = await fetch(updateMonitor.statusUrl, { cache: "no-store" });
    if (!response.ok) return;
    const payload = await response.json();
    if (!payload || payload.ok === false) return;
    if (!payload.active) {
      completeUpdateMonitor(payload);
    }
  } catch (e) {}
}
function beginUpdateMonitor(payload, scope) {
  updateMonitor.active = true;
  updateMonitor.completed = false;
  updateMonitor.streamUrl = String(payload?.stream_url || "").trim();
  updateMonitor.statusUrl = String(payload?.status_url || "").trim();
  updateMonitor.token = String(payload?.update_token || payload?.token || "").trim();
  updateMonitor.reloadScheduled = false;
  if (updateMonitor.statusTimer) clearInterval(updateMonitor.statusTimer);
  updateMonitor.statusTimer = setInterval(() => {
    pollUpdateMonitorStatus().catch(() => {});
  }, 2000);
  currentLogSource = "update";
  setUpdateUiLocked(true);
  activateTab("logs", true);
  connectLogs(true);
  updateLogVisualMode();
  setAuditMsg(
    scope === "club3090"
      ? "Club-3090 migration is running through the separate updater service. The orange log stream will stay live while the control plane restarts."
      : "Admin script update is running through the separate updater service. The orange log stream will stay live while the control plane restarts.",
  );
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
function setInstanceScopeDisabled(el, disabled) {
  if (!el) return;
  if (disabled) el.dataset.scopeDisabled = "1";
  else delete el.dataset.scopeDisabled;
  if (!instanceBusyState.active) el.disabled = !!disabled;
}
