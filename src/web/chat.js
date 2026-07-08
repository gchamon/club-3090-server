function activeChatRuntime() {
  const rows = activeChatPresets();
  if (!rows.length) return null;
  if (!chatState.presetId) {
    chatState.presetId = chatPresetKey(rows[0]);
    return rows[0];
  }
  return rows.find((runtime) => chatPresetKey(runtime) === chatState.presetId) || null;
}
function chatUnavailableRuntimeLabel(conversation = activeChatConversation()) {
  const presetKey = String(chatState.presetId || conversation?.presetId || "").trim();
  const keyParts = parseChatPresetKeyParts(presetKey);
  const snapshot = conversation?.runtimeSnapshot || {};
  const runtimeId = keyParts.runtimeId || String(snapshot.id || snapshot.instance_id || "").trim();
  const selector =
    keyParts.selector || String(snapshot.selector || snapshot.mode || "").trim();
  const selectorLabel = selector
    ? variantDisplayLabel({ upstream_tag: selector })
    : "Saved preset";
  const runtimeLabel = runtimeId || "saved runtime";
  return `${selectorLabel} | ${runtimeLabel} (unavailable)`;
}
function chatSelectedRuntimeIsUnavailable() {
  return !!chatState.presetId && !activeChatRuntime();
}
function chatUnavailableRuntimeTarget(conversation = activeChatConversation()) {
  const presetKey = String(chatState.presetId || conversation?.presetId || "").trim();
  const keyParts = parseChatPresetKeyParts(presetKey);
  return {
    runtimeId: String(keyParts.runtimeId || "").trim(),
    selector: String(keyParts.selector || "").trim(),
  };
}
function chatDelay(ms) {
  return new Promise((resolve) => setTimeout(resolve, Math.max(0, Number(ms || 0) || 0)));
}
async function waitForUnavailableChatRuntime(target, { timeoutMs = 10 * 60 * 1000, intervalMs = 2500 } = {}) {
  const runtimeId = String(target?.runtimeId || "").trim();
  const selector = String(target?.selector || "").trim();
  const expectedKey = `${runtimeId}::${selector}`;
  const startedAt = Date.now();
  while (Date.now() - startedAt <= timeoutMs) {
    await refreshStatus({ force: true });
    const runtime = activeChatPresets().find((row) => chatPresetKey(row) === expectedKey);
    if (runtime) return runtime;
    const elapsedSeconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
    setChatMsg(`Loading ${selector} on ${runtimeId}... (${elapsedSeconds}s)`);
    await chatDelay(intervalMs);
  }
  throw new Error(`Timed out waiting for ${selector} on ${runtimeId} to appear in the runtime list.`);
}
async function loadUnavailableChatRuntimeAndSend() {
  const target = chatUnavailableRuntimeTarget();
  if (!target.runtimeId || !target.selector) {
    throw new Error("The saved preset could not be resolved into a loadable runtime target.");
  }
  closeActionChoiceModal();
  const queuedText = String($("chatInput")?.value || "");
  const queuedAttachments = Array.isArray(chatState.attachments) ? chatState.attachments.map(cloneChatAttachment) : [];
  try {
    setChatMsg(`Loading ${target.selector} on ${target.runtimeId}...`);
    await post(
      "/admin/switch",
      { instance_id: target.runtimeId, mode: target.selector },
      `/admin/switch ${target.runtimeId} ${target.selector}`,
    );
    const expectedKey = `${target.runtimeId}::${target.selector}`;
    chatState.presetId = expectedKey;
    persistChatConversationState();
    renderChatUi();
    await waitForUnavailableChatRuntime(target);
    chatState.presetId = expectedKey;
    persistChatConversationState();
    renderChatUi();
    setChatMsg(`Loaded ${target.selector}. Sending queued message...`);
    const input = $("chatInput");
    if (input) input.value = queuedText;
    chatState.attachments = queuedAttachments;
    await sendChatMessage();
  } catch (error) {
    setChatMsg(messageText(error), "error");
    throw error;
  }
}
function promptUnavailableChatRuntimeSelection() {
  const target = chatUnavailableRuntimeTarget();
  const canReloadSavedPreset = !!target.runtimeId && !!target.selector;
  openActionChoiceModal({
    title: "Container Unavailable",
    body: canReloadSavedPreset
      ? `The saved container for this chat is not currently running. You can load the original preset and queue this message to send as soon as boot finishes, or choose a different running instance from <code>Container</code>.<br><br><strong>${escapeHtml(chatUnavailableRuntimeLabel())}</strong>`
      : `The saved container for this chat is not currently running. Select a running instance from <code>Container</code> before sending your message.<br><br><strong>${escapeHtml(chatUnavailableRuntimeLabel())}</strong>`,
    choices: [
      {
        label: "Load Saved Preset",
        className: "green",
        hidden: !canReloadSavedPreset,
        onClick: async () => {
          await loadUnavailableChatRuntimeAndSend();
        },
      },
      {
        label: "Choose Running Instance",
        className: "blue",
        onClick: async () => {
          const rows = activeChatPresets();
          if (!rows.length) throw new Error("No running instances are available yet.");
          chatState.presetId = chatPresetKey(rows[0]);
          persistChatConversationState();
          renderChatUi();
          $("chatPresetSelect")?.focus();
        },
      },
    ],
  });
}
function runtimeMatchesConversation(runtime, conversation) {
  if (!runtime || !conversation) return false;
  if (
    conversation.presetId &&
    chatPresetKey(runtime) === String(conversation.presetId || "")
  ) {
    return true;
  }
  const snapshot = conversation.runtimeSnapshot || {};
  const runtimeId = String(runtime.id || runtime.instance_id || "");
  const snapshotId = String(snapshot.id || snapshot.instance_id || "");
  const runtimeSelector = String(runtime.selector || runtime.mode || "");
  const snapshotSelector = String(snapshot.selector || snapshot.mode || "");
  return !!(
    runtimeId &&
    snapshotId &&
    runtimeSelector &&
    snapshotSelector &&
    runtimeId === snapshotId &&
    runtimeSelector === snapshotSelector
  );
}
function conversationLiveRuntime(conversation) {
  const rows = activeChatPresets();
  if (!rows.length) return null;
  return rows.find((runtime) => runtimeMatchesConversation(runtime, conversation)) || null;
}
function syncConversationRuntimeFromLiveRuntime(conversation, runtime) {
  if (!conversation || !runtime) return false;
  let changed = false;
  const mappings = [
    ["last_status", "lastStatus"],
    ["last_latency_s", "lastLatencySeconds"],
    ["last_ttft_s", "lastTtftSeconds"],
    ["last_tokens_per_second", "lastTokensPerSecond"],
    ["prompt_tps", "lastPromptTokensPerSecond"],
    ["last_input_tokens", "lastInputTokens"],
    ["last_output_tokens", "lastOutputTokens"],
    ["last_total_tokens", "lastTotalTokens"],
    ["last_tool_calls", "lastToolCalls"],
    ["last_path", "lastRequestPath"],
    ["last_request_at", "lastRuntimeRequestAt"],
    ["gpu_kv_cache_usage_pct", "lastKvCacheUsagePct"],
    ["cpu_kv_cache_usage_pct", "lastCpuKvCacheUsagePct"],
    ["prefix_cache_hit_rate_pct", "lastPrefixCacheHitRatePct"],
    ["ctx_size_tokens", "lastCtxSizeTokens"],
  ];
  mappings.forEach(([runtimeKey, conversationKey]) => {
    const nextValue = runtime?.[runtimeKey];
    if (nextValue === undefined || nextValue === null || nextValue === "") return;
    if (
      (conversationKey === "lastTokensPerSecond" ||
        conversationKey === "lastPromptTokensPerSecond") &&
      Number(nextValue) > 0
    ) {
      conversation[conversationKey] = Math.max(
        Number(conversation[conversationKey] || 0),
        Number(nextValue),
      );
    } else {
      conversation[conversationKey] = nextValue;
    }
    changed = true;
  });
  const promptPeak = Number(runtime?.max_prompt_tokens_per_second || runtime?.prompt_tps || 0);
  if (promptPeak > 0) {
    conversation.lastPromptTokensPerSecondPeak = Math.max(
      Number(conversation.lastPromptTokensPerSecondPeak || 0),
      promptPeak,
    );
    changed = true;
  }
  const generationPeak = Number(
    runtime?.max_tokens_per_second ||
      runtime?.last_tokens_per_second ||
      runtime?.generation_tps ||
      0,
  );
  if (generationPeak > 0) {
    conversation.lastTokensPerSecondPeak = Math.max(
      Number(conversation.lastTokensPerSecondPeak || 0),
      generationPeak,
    );
    changed = true;
  }
  if (runtime?.speculative && typeof runtime.speculative === "object") {
    const nextSnapshot = buildConversationRuntimeSnapshot(runtime, conversation);
    if (nextSnapshot) {
      conversation.runtimeSnapshot = nextSnapshot;
      conversation.freshConversationStats = false;
      changed = true;
    }
  } else if (changed) {
    conversation.runtimeSnapshot = buildConversationRuntimeSnapshot(runtime, conversation);
    conversation.freshConversationStats = false;
  }
  return changed;
}
function syncActiveConversationRuntimeFromLiveRuntime() {
  const conversation = activeChatConversation();
  const runtime = conversationLiveRuntime(conversation);
  if (!conversation || !runtime) return false;
  const changed = syncConversationRuntimeFromLiveRuntime(conversation, runtime);
  if (!changed) return false;
  if (conversation.id === chatState.activeConversationId) syncChatStateFromActiveConversation();
  if (!chatState.busy) saveChatState();
  renderChatRuntimeStats();
  return true;
}
function updateConversationRuntimeMetrics(
  conversation,
  runtime,
  payload = {},
  options = {},
) {
  if (!conversation) return;
  conversation.freshConversationStats = false;
  const usage = payload?.usage || {};
  const inputTokens =
    usage.input_tokens !== undefined ? Number(usage.input_tokens || 0) : null;
  const outputTokens =
    usage.output_tokens !== undefined ? Number(usage.output_tokens || 0) : null;
  const totalTokens =
    usage.tokens !== undefined ? Number(usage.tokens || 0) : null;
  const toolCalls =
    usage.tool_calls !== undefined ? Number(usage.tool_calls || 0) : null;
  const lastTps =
    payload?.generation_tps !== undefined &&
    Number.isFinite(Number(payload.generation_tps)) &&
    Number(payload.generation_tps) > 0
      ? Number(payload.generation_tps)
      : null;
  const promptTps =
    payload?.prompt_tps !== undefined &&
    Number.isFinite(Number(payload.prompt_tps)) &&
    Number(payload.prompt_tps) > 0
      ? Number(payload.prompt_tps)
      : null;
  const lastTtft =
    payload?.ttft_s !== undefined ? Number(payload.ttft_s || 0) : null;
  const lastLatency =
    payload?.latency_s !== undefined ? Number(payload.latency_s || 0) : null;
  const ctxSizeTokens =
    payload?.ctx_size_tokens !== undefined
      ? Number(payload.ctx_size_tokens || 0)
      : runtime?.ctx_size_tokens !== undefined
        ? Number(runtime.ctx_size_tokens || 0)
        : null;
  const kvCacheUsagePct =
    payload?.gpu_kv_cache_usage_pct !== undefined
      ? Number(payload.gpu_kv_cache_usage_pct || 0)
      : runtime?.gpu_kv_cache_usage_pct !== undefined
        ? Number(runtime.gpu_kv_cache_usage_pct || 0)
        : null;
  const cpuKvCacheUsagePct =
    payload?.cpu_kv_cache_usage_pct !== undefined
      ? Number(payload.cpu_kv_cache_usage_pct || 0)
      : runtime?.cpu_kv_cache_usage_pct !== undefined
        ? Number(runtime.cpu_kv_cache_usage_pct || 0)
        : null;
  const prefixCacheHitRatePct =
    payload?.prefix_cache_hit_rate_pct !== undefined
      ? Number(payload.prefix_cache_hit_rate_pct || 0)
      : runtime?.prefix_cache_hit_rate_pct !== undefined
        ? Number(runtime.prefix_cache_hit_rate_pct || 0)
        : null;
  const speculativeSource =
    payload?.speculative && typeof payload.speculative === "object"
      ? payload.speculative
      : runtime?.speculative && typeof runtime.speculative === "object"
        ? runtime.speculative
        : null;
  const lastStatus =
    payload?.status !== undefined ? Number(payload.status || 0) : 200;
  const lastPath = String(payload?.path || "/admin/chat-stream");
  const messages = Array.isArray(conversation.messages) ? conversation.messages : [];
  const assistantMessage = [...messages]
    .reverse()
    .find((message) => String(message?.role || "") === "assistant");
  const userMessage = [...messages]
    .reverse()
    .find((message) => String(message?.role || "") === "user");
  const visibleInputTokens = userMessage
    ? Math.max(
        0,
        Number(
          userMessage?.inputTokens ??
            userMessage?.inputTokensEstimate ??
            estimateVisibleMessageInputTokens(userMessage),
        ),
      )
    : inputTokens;
  if (visibleInputTokens !== null && visibleInputTokens !== undefined)
    conversation.lastInputTokens = visibleInputTokens;
  if (outputTokens !== null) conversation.lastOutputTokens = outputTokens;
  if (totalTokens !== null) conversation.lastTotalTokens = totalTokens;
  if (ctxSizeTokens !== null) conversation.lastCtxSizeTokens = ctxSizeTokens;
  if (promptTps !== null) {
    conversation.lastPromptTokensPerSecond = promptTps;
    conversation.lastPromptTokensPerSecondPeak = Math.max(
      Number(conversation.lastPromptTokensPerSecondPeak || 0),
      promptTps,
    );
  }
  if (kvCacheUsagePct !== null) conversation.lastKvCacheUsagePct = kvCacheUsagePct;
  if (cpuKvCacheUsagePct !== null)
    conversation.lastCpuKvCacheUsagePct = cpuKvCacheUsagePct;
  if (prefixCacheHitRatePct !== null)
    conversation.lastPrefixCacheHitRatePct = prefixCacheHitRatePct;
  if (lastStatus !== null) conversation.lastStatus = lastStatus;
  if (lastLatency !== null) conversation.lastLatencySeconds = lastLatency;
  if (lastTtft !== null) conversation.lastTtftSeconds = lastTtft;
  if (lastTps !== null) {
    conversation.lastTokensPerSecond = lastTps;
    conversation.lastTokensPerSecondPeak = Math.max(
      Number(conversation.lastTokensPerSecondPeak || 0),
      lastTps,
    );
  }
  if (toolCalls !== null) conversation.lastToolCalls = toolCalls;
  conversation.lastRequestPath = lastPath;
  conversation.lastRuntimeRequestAt = Date.now();
  if (options.streaming === true) conversation.generationActive = true;
  else conversation.generationActive = false;
  if (assistantMessage) {
    if (outputTokens !== null) assistantMessage.outputTokens = outputTokens;
    if (lastTtft !== null) assistantMessage.ttftSeconds = lastTtft;
    if (lastTps !== null) {
      assistantMessage.tokensPerSecond = lastTps;
      assistantMessage.maxTokensPerSecond = Math.max(
        Number(assistantMessage.maxTokensPerSecond || 0),
        lastTps,
      );
    }
  }
  if (userMessage && visibleInputTokens !== null && visibleInputTokens !== undefined) {
    userMessage.inputTokens = visibleInputTokens;
    delete userMessage.inputTokensEstimate;
    delete userMessage.inputTokensApprox;
  }
  conversation.totalInputTokens = (messages || [])
    .filter((message) => String(message?.role || "") === "user")
    .reduce(
      (sum, message) =>
        sum +
        Math.max(
          0,
          Number(
            message?.inputTokens ??
              message?.inputTokensEstimate ??
              estimateVisibleMessageInputTokens(message),
          ),
        ),
      0,
    );
  conversation.totalOutputTokens = (messages || [])
    .filter((message) => String(message?.role || "") === "assistant")
    .reduce((sum, message) => sum + Math.max(0, Number(message?.outputTokens || 0)), 0);
  conversation.totalTokens =
    Number(conversation.totalInputTokens || 0) +
    Number(conversation.totalOutputTokens || 0);
  conversation.runtimeSnapshot = buildConversationRuntimeSnapshot(runtime, conversation);
  if (conversation.runtimeSnapshot && speculativeSource) {
    conversation.runtimeSnapshot.speculative = cloneChatRuntimeSnapshot({
      speculative: speculativeSource,
    })?.speculative;
  }
  if (conversation?.id === chatState.activeConversationId) {
    const activeMessages = Array.isArray(chatState.messages) ? chatState.messages : [];
    const activeAssistantMessage = [...activeMessages]
      .reverse()
      .find((message) => String(message?.role || "") === "assistant");
    const activeUserMessage = [...activeMessages]
      .reverse()
      .find((message) => String(message?.role || "") === "user");
    if (activeAssistantMessage) {
      if (outputTokens !== null) activeAssistantMessage.outputTokens = outputTokens;
      if (lastTtft !== null) activeAssistantMessage.ttftSeconds = lastTtft;
      if (lastTps !== null) {
        activeAssistantMessage.tokensPerSecond = lastTps;
        activeAssistantMessage.maxTokensPerSecond = Math.max(
          Number(activeAssistantMessage.maxTokensPerSecond || 0),
          lastTps,
        );
      }
    }
    if (activeUserMessage && visibleInputTokens !== null && visibleInputTokens !== undefined) {
      activeUserMessage.inputTokens = visibleInputTokens;
      delete activeUserMessage.inputTokensEstimate;
      delete activeUserMessage.inputTokensApprox;
    }
    syncActiveConversationFromChatState();
    if (options.persist !== false) saveChatState();
  }
}
function setChatMsg(text, tone = "warning") {
  setElementMsg("chatMsg", text || "", tone);
}
function toggleChatOptionsMenu(force = null) {
  chatOptionsMenuOpen = force === null ? !chatOptionsMenuOpen : !!force;
  if ($("chatOptionsMenu"))
    $("chatOptionsMenu").classList.toggle("hidden", !chatOptionsMenuOpen);
}
function openChatSettingsPanel() {
  toggleChatOptionsMenu(false);
  openChatSettingsModal();
}
function chatTemplateId() {
  return `chat-template-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
function normalizePresetParamsForChat(params = {}) {
  const normalized = {
    ...defaultChatParams(),
    temperature:
      params.temperature !== undefined ? String(params.temperature) : "",
    top_p: params.top_p !== undefined ? String(params.top_p) : "",
    top_k: params.top_k !== undefined ? String(params.top_k) : "",
    min_p: params.min_p !== undefined ? String(params.min_p) : "",
    repetition_penalty:
      params.repetition_penalty !== undefined
        ? String(params.repetition_penalty)
        : "",
    presence_penalty:
      params.presence_penalty !== undefined
        ? String(params.presence_penalty)
        : "",
    frequency_penalty:
      params.frequency_penalty !== undefined
        ? String(params.frequency_penalty)
        : "",
    max_tokens:
      params.max_tokens !== undefined
        ? String(params.max_tokens)
        : params.max_completion_tokens !== undefined
          ? String(params.max_completion_tokens)
          : "",
    seed: params.seed !== undefined ? String(params.seed) : "",
  };
  const template = params.chat_template_kwargs || {};
  normalized.enable_thinking = !!template.enable_thinking;
  normalized.preserve_thinking = !!template.preserve_thinking;
  return normalized;
}
function ensureChatSettingsModal() {
  if ($("chatSettingsModal")) return;
  const modal = document.createElement("div");
  modal.id = "chatSettingsModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card chat-settings-modal-card" role="dialog" aria-modal="true" aria-labelledby="chatSettingsTitle"><div class="panel-head"><h2 id="chatSettingsTitle">Chat Settings</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeChatSettingsModal()">✕</button></div><div class="preset-help" id="chatSettingsPresetHint"></div><div class="chat-settings-grid"><div class="chat-settings-span-2 chat-settings-toggle-block"><div class="chat-settings-toggle-row"><label class="toggle-switch"><input id="chatSmartTitleEnabled" type="checkbox" /><span class="toggle-switch-track"></span></label><span class="chat-settings-toggle-copy"><span class="chat-settings-compact-title">Generate smart chat titles</span></span></div><div class="chat-settings-note">When disabled, new chats use the first 10 words of your first prompt as the title.</div><hr class="chat-settings-rule" /></div><label class="chat-settings-span-2">System Prompt<textarea id="chatSystemPrompt" placeholder="Optional system prompt for this conversation"></textarea></label><div class="chat-settings-span-2"><div class="chat-settings-template-row"><input id="chatPromptTemplateName" class="chat-settings-template-name" placeholder="Template name" /><select id="chatPromptTemplateSelect" class="chat-settings-template-select" aria-label="Choose template"></select><div class="chat-settings-template-actions"><button class="btn blue" onclick="loadChatPromptTemplate()">Load</button><button class="btn green" onclick="saveChatPromptTemplate()">Save Template</button><button class="btn red" onclick="deleteChatPromptTemplate()">Delete</button></div></div><div class="chat-settings-note chat-settings-template-note">Templates are stored locally in this browser so you can save and reuse system prompts.</div><hr class="chat-settings-rule" /></div><label>Temperature<input id="chatTemperature" type="number" step="0.01" min="0" max="2" /></label><label>Top P<input id="chatTopP" type="number" step="0.01" min="0" max="1" /></label><label>Top K<input id="chatTopK" type="number" step="1" min="0" /></label><label>Min P<input id="chatMinP" type="number" step="0.01" min="0" max="1" /></label><label>Repeat Penalty<input id="chatRepetitionPenalty" type="number" step="0.01" min="0" max="4" /></label><label>Presence Penalty<input id="chatPresencePenalty" type="number" step="0.01" min="-2" max="2" /></label><label>Frequency Penalty<input id="chatFrequencyPenalty" type="number" step="0.01" min="-2" max="2" /></label><label>Max Tokens<input id="chatMaxTokens" type="number" step="1" min="1" /></label><label>Enable Thinking<select id="chatEnableThinking"><option value="false">Off</option><option value="true">On</option></select></label><label>Preserve Thinking<select id="chatPreserveThinking"><option value="false">Off</option><option value="true">On</option></select></label><div class="chat-settings-span-2"><hr class="chat-settings-rule" /><div class="chat-settings-compact-block"><div class="chat-settings-toggle-row"><label class="toggle-switch"><input id="chatAutoCompactEnabled" type="checkbox" onchange="updateChatCompactionThresholdLabel()" /><span class="toggle-switch-track"></span></label><span class="chat-settings-toggle-copy"><span class="chat-settings-compact-title">Automatically compact context when nearing max</span></span></div><div class="chat-threshold-row"><span class="chat-settings-compact-threshold-label">Threshold:</span><input id="chatAutoCompactThreshold" type="range" min="${CHAT_MIN_COMPACTION_THRESHOLD}" max="${CHAT_MAX_COMPACTION_THRESHOLD}" step="1" value="${CHAT_MAX_COMPACTION_THRESHOLD}" oninput="updateChatCompactionThresholdLabel()" /><output id="chatAutoCompactThresholdValue">${CHAT_MAX_COMPACTION_THRESHOLD}%</output></div><div class="chat-settings-note chat-settings-compact-description">If about to run out of context, summarize the current chat and automatically recall the summary in a new conversation.</div></div></div></div><div class="preset-form-actions"><button class="btn blue" onclick="closeChatSettingsModal()">Cancel</button><button class="btn green" onclick="applyChatSettingsModal()">Apply</button></div><div class="msg" id="chatSettingsMsg"></div></div>`;
  document.body.appendChild(modal);
}
function setChatSettingsMsg(text, tone = "warning") {
  setElementMsg("chatSettingsMsg", text || "", tone);
}
function renderChatPromptTemplateOptions(selectedId = "") {
  const select = $("chatPromptTemplateSelect");
  if (!select) return;
  const rows = Array.isArray(chatState.promptTemplates)
    ? [...chatState.promptTemplates].sort((left, right) =>
        String(left?.name || "").localeCompare(String(right?.name || "")),
      )
    : [];
  select.innerHTML = `<option value="">Choose Template</option>${rows
    .map(
      (template) =>
        `<option value="${escapeHtml(template.id)}" ${
          template.id === selectedId ? "selected" : ""
        }>${escapeHtml(template.name || "Template")}</option>`,
    )
    .join("")}`;
}
function updateChatCompactionThresholdLabel() {
  const slider = $("chatAutoCompactThreshold");
  const output = $("chatAutoCompactThresholdValue");
  const enabled = !!$("chatAutoCompactEnabled")?.checked;
  if (slider) slider.disabled = !enabled;
  if (output && slider)
    output.value = `${clampChatCompactionThreshold(slider.value)}%`;
}
function loadChatPromptTemplate() {
  const template = (chatState.promptTemplates || []).find(
    (item) => item.id === $("chatPromptTemplateSelect")?.value,
  );
  if (!template) return setChatSettingsMsg("Select a prompt template first.");
  $("chatPromptTemplateName").value = template.name || "";
  $("chatSystemPrompt").value = template.text || "";
  setChatSettingsMsg(`Loaded template "${template.name}".`);
}
function saveChatPromptTemplate() {
  const name = String($("chatPromptTemplateName")?.value || "").trim();
  const text = String($("chatSystemPrompt")?.value || "");
  if (!name) return setChatSettingsMsg("Template name is required.", "error");
  if (!text.trim())
    return setChatSettingsMsg(
      "Template text cannot be empty.",
      "error",
    );
  const existing = (chatState.promptTemplates || []).find(
    (item) => String(item.name || "").toLowerCase() === name.toLowerCase(),
  );
  if (existing) {
    existing.name = name;
    existing.text = text;
    renderChatPromptTemplateOptions(existing.id);
  } else {
    const template = { id: chatTemplateId(), name, text };
    chatState.promptTemplates = [...(chatState.promptTemplates || []), template];
    renderChatPromptTemplateOptions(template.id);
  }
  saveChatState();
  setChatSettingsMsg(`Saved template "${name}".`);
}
async function deleteChatPromptTemplate() {
  const template = (chatState.promptTemplates || []).find(
    (item) => item.id === $("chatPromptTemplateSelect")?.value,
  );
  if (!template) return setChatSettingsMsg("Select a template to delete.");
  if (!(await openClubConfirmModal(`Delete prompt template "${template.name}"?`))) return;
  chatState.promptTemplates = (chatState.promptTemplates || []).filter(
    (item) => item.id !== template.id,
  );
  saveChatState();
  renderChatPromptTemplateOptions();
  $("chatPromptTemplateName").value = "";
  setChatSettingsMsg(`Deleted template "${template.name}".`);
}
function populateChatSettingsInputs(values = chatState.params) {
  ensureChatSettingsModal();
  const preset = chatApiPresetOptions().find(
    (item) => String(item?.name || "") === String(chatState.apiPresetName || ""),
  );
  const sourceParams = preset
    ? {
        ...defaultChatParams(),
        ...normalizePresetParamsForChat(preset.params || {}),
      }
    : { ...defaultChatParams(), ...(values || {}) };
  chatSettingsDraft = { usingPreset: !!preset };
  $("chatSettingsPresetHint").innerHTML = preset
    ? `Showing settings from API Preset <code>${escapeHtml(preset.name || "Preset")}</code>. Applying saves a Direct copy for this conversation and switches the selector to <code>Direct</code>.`
    : `These Direct settings are stored locally with this conversation.`;
  $("chatSystemPrompt").value = preset
    ? String(preset.system_prompt || "")
    : String(chatState.systemPrompt || "");
  $("chatSmartTitleEnabled").checked = chatSmartTitlesEnabled();
  $("chatTemperature").value = sourceParams.temperature || "";
  $("chatTopP").value = sourceParams.top_p || "";
  $("chatTopK").value = sourceParams.top_k || "";
  $("chatMinP").value = sourceParams.min_p || "";
  $("chatRepetitionPenalty").value = sourceParams.repetition_penalty || "";
  $("chatPresencePenalty").value = sourceParams.presence_penalty || "";
  $("chatFrequencyPenalty").value = sourceParams.frequency_penalty || "";
  $("chatMaxTokens").value = sourceParams.max_tokens || "";
  $("chatEnableThinking").value = sourceParams.enable_thinking
    ? "true"
    : "false";
  $("chatPreserveThinking").value = sourceParams.preserve_thinking
    ? "true"
    : "false";
  $("chatAutoCompactEnabled").checked = chatState.autoCompactEnabled !== false;
  $("chatAutoCompactThreshold").value = clampChatCompactionThreshold(
    chatState.autoCompactThresholdPct,
  );
  $("chatPromptTemplateName").value = "";
  renderChatPromptTemplateOptions();
  updateChatCompactionThresholdLabel();
}
function openChatSettingsModal() {
  populateChatSettingsInputs(chatState.params);
  setChatSettingsMsg("");
  $("chatSettingsModal").classList.remove("hidden");
}
function closeChatSettingsModal() {
  ensureChatSettingsModal();
  $("chatSettingsModal").classList.add("hidden");
  chatSettingsDraft = null;
}
function validateChatSettingNumber(label, raw, { min = null, max = null, integer = false } = {}) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const value = integer ? Number.parseInt(text, 10) : Number(text);
  if (!Number.isFinite(value)) throw new Error(`${label} must be a valid number.`);
  if (integer && !Number.isInteger(value)) throw new Error(`${label} must be a whole number.`);
  if (min !== null && value < min) throw new Error(`${label} must be at least ${min}.`);
  if (max !== null && value > max) throw new Error(`${label} must be at most ${max}.`);
  return integer ? String(value) : String(value);
}
function applyChatSettingsModal() {
  try {
    chatState.params = {
      ...chatState.params,
      temperature: validateChatSettingNumber("Temperature", $("chatTemperature").value, { min: 0, max: 2 }),
      top_p: validateChatSettingNumber("Top P", $("chatTopP").value, { min: 0, max: 1 }),
      top_k: validateChatSettingNumber("Top K", $("chatTopK").value, { min: 0, integer: true }),
      min_p: validateChatSettingNumber("Min P", $("chatMinP").value, { min: 0, max: 1 }),
      repetition_penalty: validateChatSettingNumber("Repeat Penalty", $("chatRepetitionPenalty").value, { min: 0, max: 4 }),
      presence_penalty: validateChatSettingNumber("Presence Penalty", $("chatPresencePenalty").value, { min: -2, max: 2 }),
      frequency_penalty: validateChatSettingNumber("Frequency Penalty", $("chatFrequencyPenalty").value, { min: -2, max: 2 }),
      max_tokens: validateChatSettingNumber("Max Tokens", $("chatMaxTokens").value, { min: 1, integer: true }),
      enable_thinking: $("chatEnableThinking").value === "true",
      preserve_thinking: $("chatPreserveThinking").value === "true",
    };
    chatState.systemPrompt = String($("chatSystemPrompt").value || "");
    chatState.smartTitleEnabled = !!$("chatSmartTitleEnabled").checked;
    chatState.autoCompactEnabled = !!$("chatAutoCompactEnabled").checked;
    chatState.autoCompactThresholdPct = clampChatCompactionThreshold(
      $("chatAutoCompactThreshold").value,
    );
    if (chatSettingsDraft?.usingPreset) chatState.apiPresetName = "";
    persistChatConversationState();
    setChatSettingsMsg("");
    closeChatSettingsModal();
    renderChatUi();
  } catch (e) {
    setChatSettingsMsg(String(e || ""), "error");
  }
}
function ensureMcpManagerModal() {
  if ($("mcpManagerModal")) return;
  const modal = document.createElement("div");
  modal.id = "mcpManagerModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card" role="dialog" aria-modal="true" aria-labelledby="mcpManagerTitle"><div class="panel-head"><h2 id="mcpManagerTitle">MCP Servers</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeMcpManagerModal()">✕</button></div><div class="preset-help">Add either a local stdio command or a remote MCP URL here. Commands launch a server on this machine; URLs connect to an already-running MCP endpoint such as <code>https://example.com/mcp</code>. New servers are only saved after the control layer can initialize and list their tools.</div><div class="formgrid"><label>Server Name<input id="mcpServerName" placeholder="filesystem" /></label><label>STDIO Command/URL<div class="form-inline-row"><input id="mcpServerCommand" placeholder="npx -y @modelcontextprotocol/server-filesystem /path or https://host/mcp" /><button class="btn green btn-icon-only mcp-save-inline-btn" title="Save Server" aria-label="Save Server" onclick="saveMcpServerFromForm()">💾</button></div></label></div><div class="msg" id="mcpManagerMsg"></div><div class="panel" style="margin-top:12px"><h2>Configured MCP Servers</h2><div id="mcpServerList" class="api-grid"></div></div></div>`;
  document.body.appendChild(modal);
}
function setMcpManagerMsg(text, tone = "warning") {
  setElementMsg("mcpManagerMsg", text || "", tone);
}
function resetMcpServerForm() {
  mcpManagerState.editingId = "";
  if ($("mcpServerName")) $("mcpServerName").value = "";
  if ($("mcpServerCommand")) $("mcpServerCommand").value = "";
  setMcpManagerMsg("");
}
function renderMcpServerList() {
  const host = $("mcpServerList");
  if (!host) return;
  const rows = Array.isArray(mcpManagerState.servers) ? mcpManagerState.servers : [];
  host.innerHTML =
    rows
      .map((server) => {
        const tools = Array.isArray(server.tools) ? server.tools : [];
        const toolText = tools.length
          ? tools.map((tool) => tool.name).join(", ")
          : server.status === "connected"
            ? "no tools reported"
            : server.error || "not connected";
        return `<div class="api-card"><div class="api-card-head"><h3>${escapeHtml(server.name || server.id)}<br><span class="label">${escapeHtml(server.status || "unknown")} · ${escapeHtml(server.transport || "stdio")} · ${server.enabled ? "enabled" : "disabled"}</span></h3><span class="preset-actions"><button class="iconbtn" title="Edit" onclick="editMcpServer('${escapeJs(server.id)}')">${svgIcon("edit")}</button><button class="iconbtn" title="Delete" onclick="deleteMcpServer('${escapeJs(server.id)}')">${svgIcon("delete")}</button></span></div><p>${escapeHtml(server.command || "")}</p><p class="label">tools: ${escapeHtml(toolText)}</p>${server.error ? `<p class="label">${escapeHtml(server.error)}</p>` : ""}<div class="variant-actions"><button class="btn ${server.enabled ? "amber" : "green"}" onclick="toggleMcpServer('${escapeJs(server.id)}', ${server.enabled ? "false" : "true"})">${server.enabled ? "Disable" : "Enable"}</button></div></div>`;
      })
      .join("") || '<div class="value">No MCP servers configured yet.</div>';
}
async function loadMcpServers() {
  ensureMcpManagerModal();
  const response = await fetch("/admin/mcp");
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || "Failed to load MCP servers");
  mcpManagerState.servers = Array.isArray(payload.servers) ? payload.servers : [];
  renderMcpServerList();
}
function editMcpServer(serverId) {
  const row = (mcpManagerState.servers || []).find((server) => server.id === serverId);
  if (!row) return;
  mcpManagerState.editingId = serverId;
  $("mcpServerName").value = row.name || "";
  $("mcpServerCommand").value = row.command || "";
  setMcpManagerMsg(`Editing MCP server "${row.name || row.id}".`);
}
async function saveMcpServerFromForm() {
  try {
    const response = await fetch("/admin/mcp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "save",
        id: mcpManagerState.editingId || "",
        name: $("mcpServerName")?.value || "",
        command: $("mcpServerCommand")?.value || "",
        enabled: true,
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || "Failed to save MCP server");
    mcpManagerState.servers = Array.isArray(payload.servers) ? payload.servers : [];
    resetMcpServerForm();
    renderMcpServerList();
    setMcpManagerMsg("Saved MCP server.");
  } catch (e) {
    setMcpManagerMsg(String(e || ""), "error");
  }
}
async function deleteMcpServer(serverId) {
  if (!(await openClubConfirmModal(`Delete MCP server ${serverId}?`))) return;
  const response = await fetch("/admin/mcp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "delete", id: serverId }),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) return setMcpManagerMsg(payload.error || "Failed to delete MCP server");
  mcpManagerState.servers = Array.isArray(payload.servers) ? payload.servers : [];
  renderMcpServerList();
}
async function toggleMcpServer(serverId, enabled) {
  const response = await fetch("/admin/mcp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "toggle", id: serverId, enabled: !!enabled }),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok)
    return setMcpManagerMsg(payload.error || "Failed to toggle MCP server", "error");
  mcpManagerState.servers = Array.isArray(payload.servers) ? payload.servers : [];
  renderMcpServerList();
  setMcpManagerMsg(enabled ? "Enabled MCP server." : "Disabled MCP server.");
}
async function openMcpManagerModal() {
  toggleChatOptionsMenu(false);
  ensureMcpManagerModal();
  $("mcpManagerModal").classList.remove("hidden");
  resetMcpServerForm();
  setMcpManagerMsg("Loading MCP servers...");
  try {
    await loadMcpServers();
    setMcpManagerMsg("");
  } catch (e) {
    setMcpManagerMsg(String(e || ""), "error");
  }
}
function closeMcpManagerModal() {
  ensureMcpManagerModal();
  $("mcpManagerModal").classList.add("hidden");
}
function openChatTab() {
  activateTab("chat", false);
}
function selectChatPreset(value) {
  chatState.presetId = String(value || "");
  persistChatConversationState();
  renderChatUi();
}
function selectChatApiPreset(value) {
  chatState.apiPresetName = String(value || "");
  persistChatConversationState();
  renderChatUi();
}
function handleChatInputResize() {
  const box = $("chatInput");
  if (!box) return;
  box.style.height = "auto";
  const lineHeight = 22;
  const minHeight = lineHeight * 4;
  const maxHeight = lineHeight * 8;
  box.style.height = `${Math.max(minHeight, Math.min(maxHeight, box.scrollHeight))}px`;
}
function clampResizableSurfaceHeight(target, nextHeight) {
  if (!target) return 0;
  const options =
    (activeResizeSession &&
      activeResizeSession.target === target &&
      activeResizeSession.options &&
      typeof activeResizeSession.options === "object")
      ? activeResizeSession.options
      : {};
  const styles = window.getComputedStyle ? window.getComputedStyle(target) : null;
  const minHeight = Math.max(120, Math.round(parseFloat(styles?.minHeight || "0") || 0));
  const rect = target.getBoundingClientRect();
  const scrollTop =
    window.scrollY ||
    window.pageYOffset ||
    document.documentElement?.scrollTop ||
    document.body?.scrollTop ||
    0;
  const documentHeight = Math.max(
    document.documentElement?.scrollHeight || 0,
    document.body?.scrollHeight || 0,
    document.documentElement?.clientHeight || 0,
    document.body?.clientHeight || 0,
  );
  const viewport = Math.max(
    320,
    window.innerHeight || document.documentElement?.clientHeight || 0,
  );
  const targetTopInDocument = Math.max(0, Math.round(rect.top + scrollTop));
  const viewportLimitedMax = Math.max(minHeight, Math.round(viewport - rect.top - 28));
  const documentLimitedMax = Math.max(
    minHeight,
    Math.round(documentHeight - targetTopInDocument - 28),
  );
  let maxHeight = Math.max(minHeight, Math.max(viewportLimitedMax, documentLimitedMax) * 3);
  if (typeof options.maxHeightResolver === "function") {
    const resolvedMax = Math.round(
      Number(
        options.maxHeightResolver(target, {
          minHeight,
          viewportLimitedMax,
          documentLimitedMax,
          documentHeight,
          targetTopInDocument,
        }),
      ) || 0,
    );
    if (resolvedMax > 0) maxHeight = Math.max(minHeight, Math.min(maxHeight, resolvedMax));
  }
  return Math.max(minHeight, Math.min(maxHeight, Math.round(Number(nextHeight || 0) || minHeight)));
}
function applyResizableSurfaceHeight(target, nextHeight) {
  if (!target) return 0;
  const clamped = clampResizableSurfaceHeight(target, nextHeight);
  if (clamped > 0) {
    target.style.height = `${clamped}px`;
    target.style.maxHeight = `${clamped}px`;
  }
  return clamped;
}
function persistChatTranscriptHeight(heightPx) {
  const clamped = Math.max(0, Math.round(Number(heightPx || 0) || 0));
  chatState.transcriptHeightPx = clamped;
  const conversation = activeChatConversation();
  if (conversation) conversation.transcriptHeightPx = clamped;
}
function ensureResizableSurfaceDocumentRoom(target, nextHeight, event = null, options = {}) {
  if (!target) return;
  const scrollTop =
    window.scrollY ||
    window.pageYOffset ||
    document.documentElement?.scrollTop ||
    document.body?.scrollTop ||
    0;
  const rect = target.getBoundingClientRect();
  const targetTopInDocument = Math.max(0, Math.round(rect.top + scrollTop));
  const pagePadding = Math.max(48, Math.round(Number(options.pagePadding || 0) || 72));
  const desiredDocumentBottom = Math.round(
    targetTopInDocument + Math.max(0, Number(nextHeight || 0)) + pagePadding,
  );
  const root = document.documentElement;
  const body = document.body;
  const currentDocumentHeight = Math.max(
    root?.scrollHeight || 0,
    body?.scrollHeight || 0,
    root?.clientHeight || 0,
    body?.clientHeight || 0,
  );
  if (desiredDocumentBottom > currentDocumentHeight && body) {
    const desiredMinHeight = desiredDocumentBottom + pagePadding;
    const currentMinHeight = parseFloat(body.style.minHeight || "0") || 0;
    if (desiredMinHeight > currentMinHeight) body.style.minHeight = `${Math.round(desiredMinHeight)}px`;
  }
  const pointerY = Number(event?.clientY || 0);
  const viewportHeight = Math.max(320, window.innerHeight || root?.clientHeight || 0);
  const nearViewportBottom = pointerY >= viewportHeight - 56;
  const viewerBottom = rect.top + Math.max(0, Number(nextHeight || 0));
  if (nearViewportBottom || viewerBottom >= viewportHeight - 20) {
    const desiredScrollTop = Math.max(
      scrollTop,
      Math.round(
        targetTopInDocument + Math.max(0, Number(nextHeight || 0)) - viewportHeight + pagePadding,
      ),
    );
    if (desiredScrollTop > scrollTop) window.scrollTo(window.scrollX || 0, desiredScrollTop);
  }
}
function bindResizableSurface(handleId, targetId, options = {}) {
  const handle = $(handleId);
  const target = $(targetId);
  if (!handle || !target || handle.dataset.resizeBound === "1") return;
  handle.dataset.resizeBound = "1";
  const autoGrowHoldDelayMs = Math.max(150, Math.round(Number(options.autoGrowHoldDelayMs || 0) || 500));
  const autoGrowStepMs = Math.max(10, Math.round(Number(options.autoGrowStepMs || 0) || 20));
  const autoGrowStepPx = Math.max(2, Math.round(Number(options.autoGrowStepPx || 0) || 10));
  const autoGrowBottomThresholdPx = Math.max(
    24,
    Math.round(Number(options.autoGrowBottomThresholdPx || 0) || 28),
  );
  const clearAutoGrowTimers = (session) => {
    const state = session || activeResizeSession;
    if (!state) return;
    if (state.autoGrowHoldTimer) {
      clearTimeout(state.autoGrowHoldTimer);
      state.autoGrowHoldTimer = null;
    }
    if (state.autoGrowStepTimer) {
      clearInterval(state.autoGrowStepTimer);
      state.autoGrowStepTimer = null;
    }
    state.autoGrowArmed = false;
  };
  const runAutoGrowStep = (session) => {
    if (!session || activeResizeSession !== session || session.handle !== handle) return;
    const lastClientY = Number(session.lastClientY || 0);
    const viewportHeight = Math.max(
      320,
      window.innerHeight || document.documentElement?.clientHeight || 0,
    );
    if (lastClientY < viewportHeight - autoGrowBottomThresholdPx) {
      clearAutoGrowTimers(session);
      return;
    }
    const currentHeight = Math.round(target.getBoundingClientRect().height || target.offsetHeight || 0);
    const nextHeight = currentHeight + autoGrowStepPx;
    const syntheticEvent = { clientY: viewportHeight - 1 };
    ensureResizableSurfaceDocumentRoom(target, nextHeight, syntheticEvent, options);
    const applied = applyResizableSurfaceHeight(target, nextHeight);
    if (applied <= currentHeight) {
      clearAutoGrowTimers(session);
      return;
    }
    session.lastAppliedHeight = applied;
    session.startHeight = applied;
    session.startY = lastClientY;
    if (typeof options.onResize === "function") options.onResize(applied, target);
  };
  const scheduleAutoGrow = (session) => {
    if (!session || activeResizeSession !== session || session.handle !== handle) return;
    if (session.autoGrowArmed || session.autoGrowHoldTimer || session.autoGrowStepTimer) return;
    session.autoGrowHoldTimer = setTimeout(() => {
      if (!activeResizeSession || activeResizeSession !== session || session.handle !== handle) return;
      session.autoGrowHoldTimer = null;
      session.autoGrowArmed = true;
      session.autoGrowStepTimer = setInterval(() => runAutoGrowStep(session), autoGrowStepMs);
    }, autoGrowHoldDelayMs);
  };
  const onPointerMove = (event) => {
    if (!activeResizeSession || activeResizeSession.handle !== handle) return;
    activeResizeSession.lastClientY = Number(event?.clientY || 0);
    const viewportHeight = Math.max(
      320,
      window.innerHeight || document.documentElement?.clientHeight || 0,
    );
    const nearBottom = activeResizeSession.lastClientY >= viewportHeight - autoGrowBottomThresholdPx;
    if (nearBottom) scheduleAutoGrow(activeResizeSession);
    else clearAutoGrowTimers(activeResizeSession);
    const nextHeight =
      Number(activeResizeSession.startHeight || target.offsetHeight || 0) +
      (Number(event?.clientY || 0) - Number(activeResizeSession.startY || 0));
    ensureResizableSurfaceDocumentRoom(target, nextHeight, event, options);
    const applied = applyResizableSurfaceHeight(target, nextHeight);
    if (applied <= 0) return;
    activeResizeSession.lastAppliedHeight = applied;
    if (typeof options.onResize === "function") options.onResize(applied, target);
  };
  const finishResize = () => {
    if (!activeResizeSession || activeResizeSession.handle !== handle) return;
    clearAutoGrowTimers(activeResizeSession);
    const finalHeight = Math.round(target.getBoundingClientRect().height || target.offsetHeight || 0);
    if (typeof options.onCommit === "function") options.onCommit(finalHeight, target);
    if (handle.releasePointerCapture && activeResizeSession.pointerId !== null) {
      try {
        handle.releasePointerCapture(activeResizeSession.pointerId);
      } catch (e) {}
    }
    activeResizeSession = null;
    document.body.classList.remove("resize-active");
  };
  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== undefined && event.button !== 0) return;
    event.preventDefault();
    const pointerId = event.pointerId ?? null;
    activeResizeSession = {
      handle,
      target,
      options,
      pointerId,
      startY: Number(event.clientY || 0),
      startHeight: Math.round(target.getBoundingClientRect().height || target.offsetHeight || 0),
      lastClientY: Number(event.clientY || 0),
      lastAppliedHeight: Math.round(target.getBoundingClientRect().height || target.offsetHeight || 0),
      autoGrowHoldTimer: null,
      autoGrowStepTimer: null,
      autoGrowArmed: false,
    };
    document.body.classList.add("resize-active");
    if (handle.setPointerCapture && pointerId !== null) {
      try {
        handle.setPointerCapture(pointerId);
      } catch (e) {}
    }
  });
  handle.addEventListener("pointermove", onPointerMove);
  handle.addEventListener("pointerup", finishResize);
  handle.addEventListener("pointercancel", finishResize);
  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", finishResize);
  window.addEventListener("pointercancel", finishResize);
}
function ensureResizableSurfaces() {
  bindResizableSurface("chatTranscriptResizeHandle", "chatTranscript", {
    maxHeightResolver(target, context) {
      return Math.max(
        context.minHeight,
        Math.ceil(Number(target.scrollHeight || 0) || context.minHeight),
      );
    },
    onResize(heightPx) {
      persistChatTranscriptHeight(heightPx);
    },
    onCommit(heightPx) {
      persistChatTranscriptHeight(heightPx);
      saveChatState();
    },
  });
  bindResizableSurface("logResizeHandle", "log");
}
function syncChatTranscriptHeight() {
  const transcript = $("chatTranscript");
  if (!transcript) return;
  const preferredHeight = Number(chatState.transcriptHeightPx || 0) || 0;
  if (preferredHeight > 0) {
    applyResizableSurfaceHeight(transcript, preferredHeight);
    return;
  }
  transcript.style.height = "";
  transcript.style.maxHeight = "";
}
function scheduleChatTranscriptHeightSync() {
  window.requestAnimationFrame(() => syncChatTranscriptHeight());
}
window.addEventListener("resize", scheduleChatTranscriptHeightSync);
function chatBenchmarkLocked() {
  return typeof benchmarkJobActive === "function" && benchmarkJobActive();
}
function handleChatInputChange() {
  handleChatInputResize();
  const hasSelectableRuntime = activeChatPresets().length > 0 || chatSelectedRuntimeIsUnavailable();
  const chatControlsDisabled = chatState.busy || chatHydrationPending() || !chatStateHydrated || chatBenchmarkLocked();
  const hasDraft =
    !!String($("chatInput")?.value || "").trim() ||
    !!(chatState.attachments || []).length;
  if ($("chatSendBtn"))
    $("chatSendBtn").disabled =
      chatControlsDisabled || !hasSelectableRuntime || (!chatState.busy && !hasDraft);
}
function handleChatInputKeydown(event) {
  if (!event || event.key !== "Enter" || !(event.ctrlKey || event.metaKey)) return;
  event.preventDefault();
  sendChatMessage();
}
function ensureChatInputBindings() {
  const input = $("chatInput");
  if (!input || input.__clubKeyBinding) return;
  input.__clubKeyBinding = true;
  input.addEventListener("keydown", handleChatInputKeydown);
}
function renderChatPresetSelector() {
  const select = $("chatPresetSelect");
  if (!select) return;
  const chatControlsDisabled = chatState.busy || chatHydrationPending() || !chatStateHydrated || chatBenchmarkLocked();
  const rows = activeChatPresets();
  const conversation = activeChatConversation();
  const savedPresetKey = String(chatState.presetId || conversation?.presetId || "").trim();
  if (!rows.length) {
    if (savedPresetKey) {
      select.innerHTML = `<option value="${escapeHtml(savedPresetKey)}" selected>${escapeHtml(chatUnavailableRuntimeLabel(conversation))}</option>`;
      select.disabled = chatControlsDisabled;
      chatState.presetId = savedPresetKey;
    } else {
      select.innerHTML = `<option value="">No active presets</option>`;
      select.disabled = true;
    }
    return;
  }
  const hasExactPreset = rows.some(
    (runtime) => chatPresetKey(runtime) === chatState.presetId,
  );
  if (!chatState.presetId) {
    chatState.presetId = chatPresetKey(rows[0]);
  }
  select.disabled = chatControlsDisabled;
  const staleOption =
    !hasExactPreset && chatState.presetId
      ? `<option value="${escapeHtml(chatState.presetId)}" selected>${escapeHtml(chatUnavailableRuntimeLabel())}</option>`
      : "";
  const html = `${staleOption}${rows
    .map((runtime) => {
      const key = chatPresetKey(runtime);
      const displayName = String(runtime.chat_label || "").trim()
        || variantDisplayLabel({ upstream_tag: runtime.selector || runtime.mode });
      const label = `${displayName} | ${runtime.id || runtime.instance_id}`;
      return `<option value="${escapeHtml(key)}" ${key === chatState.presetId ? "selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("")}`;
  setSelectOptions(select, html);
  if (chatState.presetId && [...select.options].some((option) => option.value === chatState.presetId)) {
    select.value = chatState.presetId;
  }
}
function chatApiPresetOptions() {
  const presetCatalog = lastStatus?.presets || {};
  return [...(presetCatalog.defaults || []), ...(presetCatalog.custom || [])];
}
function renderChatApiPresetSelector() {
  const select = $("chatApiPresetSelect");
  if (!select) return;
  const chatControlsDisabled = chatState.busy || chatHydrationPending() || !chatStateHydrated || chatBenchmarkLocked();
  const presets = chatApiPresetOptions();
  const valid = new Set(presets.map((preset) => String(preset?.name || "")));
  if (chatState.apiPresetName && !valid.has(chatState.apiPresetName)) {
    chatState.apiPresetName = "";
  }
  const html = `<option value="" ${!chatState.apiPresetName ? "selected" : ""}>Direct</option>${presets
    .map((preset) => {
      const name = String(preset?.name || "");
      return `<option value="${escapeHtml(name)}" ${name === chatState.apiPresetName ? "selected" : ""}>${escapeHtml(name)}</option>`;
    })
    .join("")}`;
  setSelectOptions(select, html);
  select.value = chatState.apiPresetName || "";
  select.disabled = chatControlsDisabled;
}
function chatRuntimeSupportsVision(runtime) {
  return !!runtime && !!String(runtime.vision || "").trim();
}
function chatRuntimeSupportsMedia(runtime, kind = "image") {
  if (kind === "text") return true;
  const row = runtime || {};
  const haystack = [
    row.vision,
    row.modality,
    row.selector,
    row.mode,
    row.model,
    row.model_id,
    row.served_model_name,
    row.label,
  ]
    .map((value) => String(value || "").toLowerCase())
    .join(" ");
  if (kind === "image") {
    return chatRuntimeSupportsVision(row) || /\b(vision|vl|omni|gemma|multimodal)\b/.test(haystack);
  }
  if (kind === "audio" || kind === "video") {
    return (
      /\b(omni|audio|video|speech|voice|gemma|multimodal)\b/.test(haystack) ||
      (chatRuntimeSupportsVision(row) && /\b(gemma|omni)\b/.test(haystack))
    );
  }
  return false;
}
function chatAttachmentId() {
  return `chat-att-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
function chatAttachmentKindClass(attachment) {
  const kind = String(attachment?.kind || "text").toLowerCase();
  return ["image", "audio", "video"].includes(kind) ? `chat-attachment-${kind}` : "chat-attachment-text";
}
function chatAttachmentTextPreview(text) {
  const normalized = String(text || "").replace(/\r/g, "").trim();
  if (!normalized) return "";
  const paragraph = normalized.split(/\n\s*\n/, 1)[0] || normalized;
  return paragraph.replace(/\s+/g, " ").trim().slice(0, 180);
}
function renderChatAttachmentPreview(attachment, options = {}) {
  const compact = !!options.compact;
  const name = escapeHtml(attachment?.name || "attachment");
  if (attachment?.kind === "image") {
    return `<div class="chat-attachment-preview ${compact ? "compact" : ""} ${chatAttachmentKindClass(attachment)}"><div class="chat-attachment-preview-thumb"><img src="${attachment.url}" alt="${name}" /></div>${compact ? `<div class="chat-attachment-preview-copy"><span class="chat-attachment-name">${name}</span></div>` : ""}</div>`;
  }
  if (attachment?.kind === "audio") {
    return `<div class="chat-attachment-preview ${compact ? "compact" : ""} ${chatAttachmentKindClass(attachment)}"><div class="chat-attachment-preview-thumb audio-thumb"><span>${svgIcon("waveform")}</span></div><div class="chat-attachment-preview-copy"><span class="chat-attachment-name">${name}</span>${compact ? "" : `<audio controls preload="metadata" src="${escapeHtml(attachment.url || "")}"></audio>`}</div></div>`;
  }
  if (attachment?.kind === "video") {
    const thumbnail = attachment.thumbnail_url || attachment.thumbnailUrl || "";
    const thumb = thumbnail
      ? `<img src="${escapeHtml(thumbnail)}" alt="${name}" />`
      : `<video src="${escapeHtml(attachment.url || "")}" preload="metadata" muted playsinline></video>`;
    return `<div class="chat-attachment-preview ${compact ? "compact" : ""} ${chatAttachmentKindClass(attachment)}"><div class="chat-attachment-preview-thumb video-thumb">${thumb}<span class="chat-video-play-mark">${svgIcon("play")}</span></div><div class="chat-attachment-preview-copy"><span class="chat-attachment-name">${name}</span>${compact ? "" : `<video controls preload="metadata" src="${escapeHtml(attachment.url || "")}"></video>`}</div></div>`;
  }
  const preview = escapeHtml(chatAttachmentTextPreview(attachment?.text || "")) || "Empty text attachment";
  return `<div class="chat-attachment-preview ${compact ? "compact" : ""} ${chatAttachmentKindClass(attachment)}"><div class="chat-attachment-preview-thumb text-thumb"><span>TXT</span></div><div class="chat-attachment-preview-copy"><span class="chat-attachment-name">${name}</span><span class="chat-attachment-preview-text">${preview}</span></div></div>`;
}
function renderChatAttachments() {
  const host = $("chatAttachmentRow");
  if (!host) return;
  const nextHtml = (chatState.attachments || [])
    .map(
      (attachment, index) =>
        `<div class="chat-attachment-pill ${chatAttachmentKindClass(attachment)}"><button class="chat-attachment-remove" title="Remove attachment" aria-label="Remove attachment" onclick="removeChatAttachment(${index})">x</button>${renderChatAttachmentPreview(attachment, { compact: true })}</div>`,
    )
    .join("");
  if (host.innerHTML !== nextHtml) host.innerHTML = nextHtml;
}
function removeChatAttachment(index) {
  chatState.attachments = (chatState.attachments || []).filter((_, itemIndex) => itemIndex !== index);
  persistChatConversationState();
  renderChatAttachments();
}
function chatTranscriptIsNearBottom(host = $("chatTranscript")) {
  if (!host) return true;
  return (
    host.scrollHeight - (host.scrollTop + host.clientHeight) <=
    CHAT_TRANSCRIPT_NEAR_BOTTOM_PX
  );
}
function setChatTranscriptAutoFollow(nextValue) {
  chatTranscriptAutoFollow = !!nextValue;
  if (chatTranscriptAutoFollow) {
    chatTranscriptUserDetached = false;
    chatTranscriptReattachTravelPx = 0;
  }
  syncChatTranscriptFollowClasses();
}
function chatTranscriptAutoscrollEnabled() {
  const conversation = activeChatConversation();
  if (conversation?.transcriptAutoscroll !== undefined) {
    return conversation.transcriptAutoscroll !== false;
  }
  return true;
}
function setChatTranscriptAutoscroll(nextValue) {
  setChatTranscriptAutoFollow(nextValue);
  const conversation = activeChatConversation();
  if (conversation) {
    conversation.transcriptAutoscroll = !!nextValue;
    if (conversation.id === chatState.activeConversationId) {
      syncActiveConversationFromChatState();
    }
  }
  if ($("chatAutoscroll")) $("chatAutoscroll").checked = !!nextValue;
  persistChatConversationState();
  renderChatTranscript(!!nextValue, { reason: "user" });
}
function syncChatTranscriptFollowClasses(host = $("chatTranscript")) {
  if (!host) return;
  host.classList.toggle("chat-transcript-autofollow", !!chatTranscriptAutoFollow);
  host.classList.toggle(
    "chat-transcript-streaming-follow",
    !!chatTranscriptAutoFollow && !!chatState?.busy,
  );
}
function scrollChatTranscriptToBottom(host = $("chatTranscript")) {
  if (!host) return;
  chatTranscriptProgrammaticScroll = true;
  host.scrollTop = host.scrollHeight;
  chatTranscriptScrollTop = host.scrollTop;
  setChatTranscriptAutoFollow(true);
  setTimeout(() => {
    chatTranscriptProgrammaticScroll = false;
  }, 0);
}
function lockChatTranscriptStreamingHeight() {
  const host = $("chatTranscript");
  if (!host) return;
  const nextHeight = Math.max(
    240,
    Math.round(host.getBoundingClientRect().height || host.clientHeight || 0),
  );
  if (!nextHeight) return;
  chatTranscriptStreamingHeightLock = nextHeight;
  chatTranscriptStreamingHeightLockActive = true;
  host.style.minHeight = `${nextHeight}px`;
  host.style.maxHeight = `${nextHeight}px`;
}
function unlockChatTranscriptStreamingHeight() {
  const host = $("chatTranscript");
  chatTranscriptStreamingHeightLock = 0;
  chatTranscriptStreamingHeightLockActive = false;
  if (!host) return;
  host.style.minHeight = "";
  host.style.maxHeight = "";
}
function finalizeChatTranscriptBottomFollow(host = $("chatTranscript")) {
  if (!host) return;
  if (chatTranscriptAutoFollow || chatTranscriptIsNearBottom(host)) {
    scrollChatTranscriptToBottom(host);
  }
}
function ensureChatTranscriptBehavior() {
  const host = $("chatTranscript");
  if (!host || host.dataset.followBound === "1") return;
  host.dataset.followBound = "1";
  chatTranscriptScrollTop = host.scrollTop;
  host.addEventListener("scroll", () => {
    if (chatTranscriptProgrammaticScroll) {
      chatTranscriptScrollTop = host.scrollTop;
      return;
    }
    const nextTop = host.scrollTop;
    const delta = nextTop - chatTranscriptScrollTop;
    chatTranscriptScrollTop = nextTop;
    const nearBottom = chatTranscriptIsNearBottom(host);
    if (nearBottom) {
      setChatTranscriptAutoFollow(true);
      return;
    }
    if (chatState.busy && delta <= -CHAT_TRANSCRIPT_DETACH_SCROLL_PX) {
      chatTranscriptUserDetached = true;
      chatTranscriptReattachTravelPx = 0;
      chatTranscriptAutoFollow = false;
      return;
    }
    if (chatTranscriptUserDetached && delta > 0) {
      chatTranscriptReattachTravelPx += delta;
      if (
        nearBottom ||
        chatTranscriptReattachTravelPx >= CHAT_TRANSCRIPT_REATTACH_SCROLL_PX
      ) {
        setChatTranscriptAutoFollow(true);
        return;
      }
    } else if (!chatTranscriptUserDetached) {
      chatTranscriptAutoFollow = false;
    }
  });
  host.addEventListener("click", (event) => {
    const link = event.target?.closest?.("a[data-chat-external-link]");
    if (!link) return;
    event.preventDefault();
    openExternalLinkModal(link.getAttribute("data-chat-external-link") || link.href || "");
  });
  document.addEventListener("selectionchange", () => {
    if (isChatTranscriptSelectionActive(host)) return;
    if (chatTranscriptRenderPending) scheduleChatTranscriptRender();
  });
}
function handleChatMarkdownImageError(img) {
  if (!img || img.dataset.broken === "1") return;
  img.dataset.broken = "1";
  const src = img.getAttribute("src") || "";
  if (src && !brokenMarkdownImageUrls.has(src)) {
    brokenMarkdownImageUrls.add(src);
    clearChatMarkdownRenderCache();
  }
  const wrapper = document.createElement("template");
  wrapper.innerHTML = markdownImageFailureNote(src, img.getAttribute("alt") || "image");
  img.replaceWith(wrapper.content.firstElementChild || document.createTextNode(""));
}
function chatMessageAttachments(message) {
  if (Array.isArray(message?.attachments)) return message.attachments;
  if (Array.isArray(message?.images)) {
    return message.images.map((image) => ({
      kind: "image",
      name: image?.name || "image",
      url: image?.url || "",
    }));
  }
  return [];
}
function normalizeMarkdownUrl(url, { allowDataImage = true } = {}) {
  const raw = String(url || "").trim();
  if (!raw) return "";
  if (allowDataImage && /^data:image\//i.test(raw)) return raw;
  if (/^mailto:/i.test(raw)) return raw;
  if (/^[/?#]/.test(raw)) return raw;
  if (/^www\./i.test(raw)) return normalizeMarkdownUrl(`https://${raw}`, { allowDataImage });
  try {
    const parsed = new URL(raw, window.location.origin);
    if (!/^https?:$/i.test(parsed.protocol) && !/^blob:$/i.test(parsed.protocol))
      return "";
    return parsed.href;
  } catch (e) {
    return "";
  }
}
function markdownUrlParts(candidate) {
  let url = String(candidate || "");
  let trailing = "";
  while (url && /[),.;!?]$/.test(url) && !/\([^)]+\)$/.test(url)) {
    trailing = url.slice(-1) + trailing;
    url = url.slice(0, -1);
  }
  return { url, trailing };
}
function urlLooksLikeImage(url) {
  return /^data:image\//i.test(url) || /\.(avif|gif|jpe?g|png|svg|webp)$/i.test(url.split("?")[0]);
}
function urlLooksLikeVideo(url) {
  return /\.(mp4|m4v|mov|webm|ogv)$/i.test(url.split("?")[0]);
}
function urlLooksLikeAudio(url) {
  return /\.(mp3|wav|ogg|m4a|flac)$/i.test(url.split("?")[0]);
}
function youtubeEmbedUrl(url) {
  try {
    const parsed = new URL(url);
    if (/youtube\.com$/i.test(parsed.hostname) || /www\.youtube\.com$/i.test(parsed.hostname)) {
      const videoId = parsed.searchParams.get("v");
      if (videoId) return `https://www.youtube.com/embed/${encodeURIComponent(videoId)}`;
    }
    if (/youtu\.be$/i.test(parsed.hostname)) {
      const videoId = parsed.pathname.replace(/\//g, "").trim();
      if (videoId) return `https://www.youtube.com/embed/${encodeURIComponent(videoId)}`;
    }
  } catch (e) {}
  return "";
}
function richEmbedForUrl(url, altText = "") {
  const safeUrl = normalizeMarkdownUrl(url);
  if (!safeUrl) return "";
  if (urlLooksLikeImage(safeUrl))
    return `<div class="chat-rich-embed">${markdownImageHtml(safeUrl, altText || "image")}</div>`;
  if (urlLooksLikeVideo(safeUrl))
    return `<div class="chat-rich-embed"><video class="chat-markdown-media" controls preload="metadata" src="${escapeHtml(safeUrl)}"></video></div>`;
  if (urlLooksLikeAudio(safeUrl))
    return `<div class="chat-rich-embed"><audio class="chat-markdown-media" controls preload="metadata" src="${escapeHtml(safeUrl)}"></audio></div>`;
  const youtubeUrl = youtubeEmbedUrl(safeUrl);
  if (youtubeUrl)
    return `<div class="chat-rich-embed"><iframe class="chat-markdown-media" src="${escapeHtml(youtubeUrl)}" title="${escapeHtml(altText || "embedded media")}" loading="lazy" allowfullscreen></iframe></div>`;
  return "";
}
function openChatLocalMedia(rootPath, relativePath) {
  if (typeof openStorageBrowserFileReadOnly === "function") {
    openStorageBrowserFileReadOnly(String(rootPath || "/"), String(relativePath || ""));
  }
}
function markChatGeneratedMediaBroken(media) {
  const host = media?.closest?.(".chat-generated-media");
  if (!host) return;
  host.classList.add("chat-generated-media-broken");
  host.querySelector(".chat-local-media-open")?.remove();
}
function renderChatGeneratedMedia(output = {}) {
  if (Array.isArray(output)) {
    return output.map((item) => renderChatGeneratedMedia(item)).join("");
  }
  const url = String(output?.url || "");
  const rootPath = String(output?.root_path || "/");
  const relativePath = String(output?.relative_path || "");
  const name = String(output?.name || relativePath.split("/").pop() || "generated media");
  const open = `openChatLocalMedia(${JSON.stringify(rootPath)},${JSON.stringify(relativePath)})`;
  const canOpen = !!relativePath && !!url;
  const popoutIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 5h5v5m0-5-7 7" fill="none" /><path d="M10 7H7a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-3" fill="none" /></svg>';
  let media = "";
  if (output?.kind === "image")
    media = `<img class="chat-markdown-image chat-local-media" src="${escapeHtml(url)}" alt="${escapeHtml(name)}" loading="lazy" onerror="markChatGeneratedMediaBroken(this)" />`;
  else if (output?.kind === "video")
    media = `<video class="chat-markdown-media chat-local-media" controls preload="metadata" src="${escapeHtml(url)}" onerror="markChatGeneratedMediaBroken(this)"></video>`;
  else
    media = `<audio class="chat-markdown-media chat-local-media" controls preload="metadata" src="${escapeHtml(url)}" onerror="markChatGeneratedMediaBroken(this)"></audio>`;
  const openButton = canOpen
    ? `<button type="button" class="chat-local-media-open" title="Open in File Editor" aria-label="Open generated media in File Editor" onclick='${escapeHtml(open)}'>${popoutIcon}</button>`
    : "";
  return `<div class="chat-rich-embed chat-generated-media">${media}${openButton}</div>`;
}
function renderStudioPlanResults(results = []) {
  if (!Array.isArray(results) || !results.length) return "";
  const textResult = results.find((result) => result?.kind === "text" && Array.isArray(result?.items));
  const items = textResult?.items || [];
  const batchResults = results.filter((result) => result?.kind === "media" && result?.batch);
  const standalone = results
    .filter((result) => result?.kind === "media" && !result?.batch)
    .flatMap((result) => result?.outputs || []);
  const rows = items.map((item, itemIndex) => {
    const media = batchResults.flatMap((result) =>
      (result.outputs || [])
        .filter((entry, index) => index === itemIndex || entry?.item === item)
        .map((entry) => entry?.output)
        .filter(Boolean),
    );
    const image = media.find((output) => output?.kind === "image");
    const audio = media.find((output) => output?.kind === "audio");
    const heading = [item?.name, item?.dates].filter(Boolean).join(" · ");
    const copy = String(item?.text || item?.paragraph || item?.description || "").trim();
    return `<section class="chat-studio-result-row">${
      image ? `<div class="chat-studio-result-portrait">${renderChatGeneratedMedia(image)}</div>` : ""
    }<div class="chat-studio-result-copy">${heading ? `<h4>${escapeHtml(heading)}</h4>` : ""}${
      copy ? `<div class="chat-message-markdown">${cachedMarkdownToHtml(copy)}</div>` : ""
    }${audio ? `<div class="chat-studio-result-audio">${renderChatGeneratedMedia(audio)}</div>` : ""}</div></section>`;
  }).join("");
  const tail = standalone.length
    ? `<div class="chat-studio-result-tail">${standalone.map((entry) => renderChatGeneratedMedia(entry?.output || entry)).join("")}</div>`
    : "";
  return rows || tail ? `<div class="chat-studio-plan-results">${rows}${tail}</div>` : "";
}
function applyBalancedUnderscoreFormatting(text) {
  return String(text || "")
    .replace(
      /(^|[^A-Za-z0-9])___([^\s_](?:.*?[^\s_])?)___(?=[^A-Za-z0-9]|$)/g,
      (_, prefix, body) => `${prefix}<strong><em>${body}</em></strong>`,
    )
    .replace(
      /(^|[^A-Za-z0-9])__([^\s_](?:.*?[^\s_])?)__(?=[^A-Za-z0-9]|$)/g,
      (_, prefix, body) => `${prefix}<strong>${body}</strong>`,
    )
    .replace(
      /(^|[^A-Za-z0-9])_([^\s_](?:.*?[^\s_])?)_(?=[^A-Za-z0-9]|$)/g,
      (_, prefix, body) => `${prefix}<em>${body}</em>`,
    );
}
const CLUB_LATEX_SYMBOLS = {
  alpha: "\u03b1",
  beta: "\u03b2",
  gamma: "\u03b3",
  delta: "\u03b4",
  epsilon: "\u03b5",
  varepsilon: "\u03f5",
  zeta: "\u03b6",
  eta: "\u03b7",
  theta: "\u03b8",
  vartheta: "\u03d1",
  iota: "\u03b9",
  kappa: "\u03ba",
  lambda: "\u03bb",
  mu: "\u03bc",
  nu: "\u03bd",
  xi: "\u03be",
  pi: "\u03c0",
  rho: "\u03c1",
  sigma: "\u03c3",
  tau: "\u03c4",
  upsilon: "\u03c5",
  phi: "\u03c6",
  chi: "\u03c7",
  psi: "\u03c8",
  omega: "\u03c9",
  Gamma: "\u0393",
  Delta: "\u0394",
  Alpha: "\u0391",
  Beta: "\u0392",
  Epsilon: "\u0395",
  Zeta: "\u0396",
  Eta: "\u0397",
  Theta: "\u0398",
  Iota: "\u0399",
  Kappa: "\u039a",
  Lambda: "\u039b",
  Mu: "\u039c",
  Nu: "\u039d",
  Rho: "\u03a1",
  Xi: "\u039e",
  Pi: "\u03a0",
  Sigma: "\u03a3",
  Tau: "\u03a4",
  Upsilon: "\u03a5",
  Phi: "\u03a6",
  Chi: "\u03a7",
  Psi: "\u03a8",
  Omega: "\u03a9",
  times: "\u00d7",
  otimes: "\u2297",
  cdot: "\u00b7",
  div: "\u00f7",
  pm: "\u00b1",
  mp: "\u2213",
  le: "\u2264",
  leq: "\u2264",
  ge: "\u2265",
  geq: "\u2265",
  neq: "\u2260",
  approx: "\u2248",
  sim: "\u223c",
  equiv: "\u2261",
  infty: "\u221e",
  partial: "\u2202",
  nabla: "\u2207",
  int: "\u222b",
  iint: "\u222c",
  oint: "\u222e",
  oiint: "\u222f",
  oiiint: "\u2230",
  intop: "\u222b",
  sum: "\u2211",
  prod: "\u220f",
  coprod: "\u2210",
  bigoplus: "\u2a01",
  bigotimes: "\u2a02",
  bigodot: "\u2a00",
  biguplus: "\u2a04",
  bigsqcup: "\u2a06",
  to: "\u2192",
  rightarrow: "\u2192",
  leftarrow: "\u2190",
  implies: "\u21d2",
  iff: "\u21d4",
  in: "\u2208",
  notin: "\u2209",
  subset: "\u2282",
  subseteq: "\u2286",
  varsubsetneq: "\u228a",
  varsupseteq: "\u2287",
  sqsubset: "\u228f",
  sqsupset: "\u2290",
  setminus: "\u2216",
  cup: "\u222a",
  cap: "\u2229",
  oplus: "\u2295",
  pitchfork: "\u22d4",
  varpi: "\u03d6",
  aleph: "\u2135",
  beth: "\u2136",
  gimel: "\u2137",
  daleth: "\u2138",
  wp: "\u2118",
  Finv: "\u2132",
  amalg: "\u2a3f",
  dagger: "\u2020",
  ddagger: "\u2021",
  angle: "\u2220",
  sphericalangle: "\u2222",
  measuredangle: "\u2221",
  varnothing: "\u2205",
  complement: "\u2201",
  forall: "\u2200",
  exists: "\u2203",
  emptyset: "\u2205",
  neg: "\u00ac",
  land: "\u2227",
  lor: "\u2228",
  mid: "\u2223",
  langle: "\u27e8",
  rangle: "\u27e9",
  lvert: "|",
  rvert: "|",
  lim: "lim",
  sin: "sin",
  cos: "cos",
  tan: "tan",
  log: "log",
  ln: "ln",
  exp: "exp",
};
const CLUB_LATEX_FONT_COMMANDS = {
  mathbf: "chat-latex-font-bold",
  mathit: "chat-latex-font-italic",
  mathcal: "chat-latex-font-cal",
  mathfrak: "chat-latex-font-frak",
  mathbb: "chat-latex-font-bb",
  mathsf: "chat-latex-font-sans",
  mathtt: "chat-latex-font-mono",
  boldsymbol: "chat-latex-font-bold",
};
const CLUB_LATEX_ACCENT_COMMANDS = {
  vec: "chat-latex-accent-vec",
  overrightarrow: "chat-latex-accent-overrightarrow",
  overleftarrow: "chat-latex-accent-overleftarrow",
  overleftrightarrow: "chat-latex-accent-overleftrightarrow",
  hat: "chat-latex-accent-hat",
  widehat: "chat-latex-accent-widehat",
  widetilde: "chat-latex-accent-widetilde",
  bar: "chat-latex-accent-bar",
  breve: "chat-latex-accent-breve",
  check: "chat-latex-accent-check",
  dot: "chat-latex-accent-dot",
  ddot: "chat-latex-accent-ddot",
  dddot: "chat-latex-accent-dddot",
};
const CLUB_LATEX_PREFIX_COMMANDS = [
  "overleftrightarrow",
  "overleftarrow",
  "overrightarrow",
  "boldsymbol",
  "widetilde",
  "widehat",
  "mathfrak",
  "mathcal",
  "mathbb",
  "mathbf",
  "mathit",
  "mathsf",
  "mathtt",
  "DeclarePairedDelimiter",
  "longrightarrow",
  "xleftarrow",
  "xrightarrow",
  "overbrace",
  "underbrace",
  "stackrel",
  "substack",
  "braket",
  "inner",
  "abs",
  "binom",
  "tbinom",
  "dbinom",
  "mathrm",
  "color",
  "dva",
  "dv",
  "underset",
  "overset",
  "sqrt",
  "text",
  "ce",
  "vec",
  "hat",
  "bar",
  "breve",
  "check",
  "dot",
  "ddot",
  "dddot",
].sort((a, b) => b.length - a.length);
const CLUB_LATEX_DELIMITERS = {
  ".": "",
  "(": "(",
  ")": ")",
  "[": "[",
  "]": "]",
  "{": "{",
  "}": "}",
  "|": "|",
  "\\{": "{",
  "\\}": "}",
  "\\langle": "\u27e8",
  "\\rangle": "\u27e9",
};
function clubSplitKnownLatexPrefix(name) {
  const source = String(name || "");
  for (const prefix of CLUB_LATEX_PREFIX_COMMANDS) {
    if (source.startsWith(prefix) && source.length > prefix.length) {
      return { command: prefix, remainder: source.slice(prefix.length) };
    }
  }
  return null;
}
function findLatexGroupEnd(text, start) {
  let depth = 0;
  for (let index = start; index < text.length; index += 1) {
    const char = text[index];
    if (char === "\\") {
      index += 1;
      continue;
    }
    if (char === "{") depth += 1;
    if (char === "}") {
      depth -= 1;
      if (depth === 0) return index;
    }
  }
  return -1;
}
function clubFindLatexEnvironmentEnd(text, envName, start) {
  const beginToken = `\\begin{${envName}}`;
  const endToken = `\\end{${envName}}`;
  let depth = 1;
  for (let index = start; index < text.length; index += 1) {
    if (text.startsWith(beginToken, index)) {
      depth += 1;
      index += beginToken.length - 1;
      continue;
    }
    if (text.startsWith(endToken, index)) {
      depth -= 1;
      if (depth === 0) return index;
      index += endToken.length - 1;
    }
  }
  return -1;
}
function clubSplitLatexTopLevel(text, separator) {
  const parts = [];
  const source = String(text || "");
  let depth = 0;
  let current = "";
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (char === "\\") {
      if (separator === "\\\\" && source[index + 1] === "\\" && depth === 0) {
        parts.push(current);
        current = "";
        index += 1;
        continue;
      }
      current += char;
      if (index + 1 < source.length) {
        current += source[index + 1];
        index += 1;
      }
      continue;
    }
    if (char === "{") depth += 1;
    if (char === "}" && depth > 0) depth -= 1;
    if (separator === "&" && char === "&" && depth === 0) {
      parts.push(current);
      current = "";
      continue;
    }
    current += char;
  }
  parts.push(current);
  return parts;
}
function readLatexArgument(text, start) {
  let index = start;
  while (/\s/.test(text[index] || "")) index += 1;
  if (text[index] === "{") {
    const end = findLatexGroupEnd(text, index);
    if (end >= 0) return { body: text.slice(index + 1, end), end: end + 1 };
  }
  const command = text.slice(index).match(/^\\[A-Za-z]+/);
  if (command) {
    const split = clubSplitKnownLatexPrefix(command[0].slice(1));
    if (split) return { body: `\\${split.command}{${split.remainder}}`, end: index + command[0].length };
    return { body: command[0], end: index + command[0].length };
  }
  const simple = text.slice(index).match(/^[^\s{}[\]^_\\&]+/);
  return simple ? { body: simple[0], end: index + simple[0].length } : { body: "", end: index };
}
function clubReadLatexDelimiter(text, start) {
  let index = start;
  while (/\s/.test(text[index] || "")) index += 1;
  if (text[index] === "\\") {
    const command = text.slice(index).match(/^\\[A-Za-z]+|^\\./);
    if (command) return { token: command[0], end: index + command[0].length };
  }
  return { token: text[index] || "", end: index + (text[index] ? 1 : 0) };
}
function clubReadLooseLatexTextRun(text, start) {
  let index = start;
  let body = "";
  while (index < text.length) {
    if (text[index] === "\n") break;
    if (text[index] === "\\" && /^(?:[A-Za-z]+|.)/.test(text.slice(index + 1))) break;
    if (text[index] === "^" || text[index] === "_") break;
    body += text[index];
    index += 1;
  }
  return { body: body.trim(), end: index };
}
function clubInferCompactLatexArgs(remainder) {
  const text = String(remainder || "").trim();
  if (!text) return ["", ""];
  if (text.includes(",")) {
    const parts = text.split(",");
    return [parts[0] || "", parts.slice(1).join(",") || ""];
  }
  if (text.length <= 2) return [text.slice(0, 1), text.slice(1)];
  return [text.slice(0, Math.ceil(text.length / 2)), text.slice(Math.ceil(text.length / 2))];
}
function clubRenderBinomFromArgs(top, bottom) {
  return `<span class="chat-latex-binom"><span class="chat-latex-delim">(</span><span class="chat-latex-binom-body"><span>${renderLatexFragment(top)}</span><span>${renderLatexFragment(bottom)}</span></span><span class="chat-latex-delim">)</span></span>`;
}
function clubRenderArrowWithOptionalLabel(body, arrow) {
  return `<span class="chat-latex-arrow-wrap">${body ? `<span class="chat-latex-arrow-label">${renderLatexFragment(body)}</span>` : ""}<span class="chat-latex-op">${escapeHtml(arrow)}</span></span>`;
}
function clubRenderBrace(command, body) {
  const brace = command === "overbrace" ? "\u23de" : "\u23df";
  return `<span class="chat-latex-brace ${command === "overbrace" ? "chat-latex-overbrace" : "chat-latex-underbrace"}"><span class="chat-latex-brace-mark">${brace}</span><span class="chat-latex-brace-body">${renderLatexFragment(body)}</span></span>`;
}
function clubRenderLatexTextLiteral(source) {
  return escapeHtml(String(source || "")).replace(/ {2}/g, " &nbsp;");
}
function clubRenderLatexAccent(command, body) {
  return `<span class="chat-latex-accent ${CLUB_LATEX_ACCENT_COMMANDS[command] || ""}"><span class="chat-latex-accent-body">${renderLatexFragment(body)}</span></span>`;
}
function clubRenderLatexFont(command, body) {
  return `<span class="${CLUB_LATEX_FONT_COMMANDS[command] || ""}">${renderLatexFragment(body)}</span>`;
}
function clubRenderLatexChemical(source) {
  const text = String(source || "");
  let html = "";
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (/\d/.test(char) && index > 0 && /[A-Za-z)\]]/.test(text[index - 1] || "")) {
      html += `<sub>${char}</sub>`;
      continue;
    }
    if ((char === "+" || char === "-") && /[A-Za-z0-9)\]]/.test(text[index - 1] || "")) {
      html += `<sup>${escapeHtml(char)}</sup>`;
      continue;
    }
    html += escapeHtml(char);
  }
  return `<span class="chat-latex-chem">${html}</span>`;
}
function clubRenderLatexRowsTable(rows, tableClass = "") {
  return `<table class="${tableClass}">${rows.map((cells) => `<tr>${cells.map((cell) => `<td>${renderLatexFragment(cell)}</td>`).join("")}</tr>`).join("")}</table>`;
}
function clubRenderLatexEnvironment(name, body) {
  const env = String(name || "").trim();
  const rows = clubSplitLatexTopLevel(body, "\\\\")
    .map((row) => clubSplitLatexTopLevel(row, "&").map((cell) => String(cell || "").trim()))
    .filter((cells) => cells.some((cell) => cell));
  if (["pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix", "matrix"].includes(env)) {
    const delimiters = {
      pmatrix: ["(", ")"],
      bmatrix: ["[", "]"],
      Bmatrix: ["{", "}"],
      vmatrix: ["|", "|"],
      Vmatrix: ["||", "||"],
      matrix: ["", ""],
    };
    const [left, right] = delimiters[env] || ["", ""];
    return `<span class="chat-latex-matrix-wrap">${left ? `<span class="chat-latex-delim">${escapeHtml(left)}</span>` : ""}${clubRenderLatexRowsTable(rows, "chat-latex-matrix")}${right ? `<span class="chat-latex-delim">${escapeHtml(right)}</span>` : ""}</span>`;
  }
  if (env === "cases") {
    return `<span class="chat-latex-matrix-wrap"><span class="chat-latex-delim">{</span>${clubRenderLatexRowsTable(rows, "chat-latex-cases")}</span>`;
  }
  if (env === "align" || env === "aligned" || env === "array") {
    return clubRenderLatexRowsTable(rows, "chat-latex-aligned");
  }
  return `<span class="chat-latex-env">${renderLatexFragment(body)}</span>`;
}
function renderLatexFragment(source) {
  const text = String(source || "");
  let html = "";
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === "\\") {
      if (text[index + 1] === "\\") {
        html += `<span class="chat-latex-rowbreak"></span>`;
        index += 1;
        continue;
      }
      const command = text.slice(index + 1).match(/^[A-Za-z]+/);
      if (command) {
        let name = command[0];
        let remainder = "";
        const split = clubSplitKnownLatexPrefix(name);
        if (split && !CLUB_LATEX_SYMBOLS[name] && !CLUB_LATEX_FONT_COMMANDS[name] && !CLUB_LATEX_ACCENT_COMMANDS[name]) {
          name = split.command;
          remainder = split.remainder;
        }
        index += command[0].length;
        if (name === "begin") {
          const envArg = readLatexArgument(text, index + 1);
          const envName = String(envArg.body || "").trim();
          const bodyStart = envArg.end;
          const endStart = clubFindLatexEnvironmentEnd(text, envName, bodyStart);
          if (envName && endStart >= 0) {
            html += clubRenderLatexEnvironment(envName, text.slice(bodyStart, endStart));
            index = endStart + `\\end{${envName}}`.length - 1;
            continue;
          }
        }
        if (name === "frac" || name === "dfrac" || name === "tfrac") {
          const numerator = readLatexArgument(text, index + 1);
          const denominator = readLatexArgument(text, numerator.end);
          html += `<span class="chat-latex-frac"><span>${renderLatexFragment(numerator.body)}</span><span>${renderLatexFragment(denominator.body)}</span></span>`;
          index = denominator.end - 1;
          continue;
        }
        if (name === "sqrt") {
          let rootIndex = "";
          let cursor = index + 1;
          while (/\s/.test(text[cursor] || "")) cursor += 1;
          if (text[cursor] === "[") {
            const close = text.indexOf("]", cursor + 1);
            if (close >= 0) {
              rootIndex = text.slice(cursor + 1, close);
              cursor = close + 1;
            }
          }
          const radicand = readLatexArgument(text, cursor);
          html += `<span class="chat-latex-root">${rootIndex ? `<span class="chat-latex-root-index">${renderLatexFragment(rootIndex)}</span>` : ""}<span class="chat-latex-root-symbol">\u221a</span><span class="chat-latex-root-body">${renderLatexFragment(radicand.body)}</span></span>`;
          index = radicand.end - 1;
          continue;
        }
        if (name === "left" || name === "right") {
          const delimiter = clubReadLatexDelimiter(text, index + 1);
          const symbol = CLUB_LATEX_DELIMITERS[delimiter.token] !== undefined ? CLUB_LATEX_DELIMITERS[delimiter.token] : delimiter.token.replace(/^\\/, "");
          if (symbol) html += `<span class="chat-latex-delim">${escapeHtml(symbol)}</span>`;
          index = delimiter.end - 1;
          continue;
        }
        if (name === "quad" || name === "qquad") {
          html += `<span class="${name === "qquad" ? "chat-latex-space-wide" : "chat-latex-space"}"></span>`;
          continue;
        }
        if (name === "text") {
          const arg = remainder
            ? { body: remainder }
            : text[index + 1] === "{"
              ? readLatexArgument(text, index + 1)
              : clubReadLooseLatexTextRun(text, index + 1);
          html += `<span class="chat-latex-text">${clubRenderLatexTextLiteral(arg.body)}</span>`;
          if (!remainder && arg.end !== undefined) index = arg.end - 1;
          continue;
        }
        if (name === "ce") {
          const arg = remainder
            ? { body: remainder }
            : text[index + 1] === "{"
              ? readLatexArgument(text, index + 1)
              : clubReadLooseLatexTextRun(text, index + 1);
          html += clubRenderLatexChemical(arg.body);
          if (!remainder && arg.end !== undefined) index = arg.end - 1;
          continue;
        }
        if (name === "overset" || name === "underset") {
          const top = readLatexArgument(text, index + 1);
          const body = readLatexArgument(text, top.end);
          html += `<span class="chat-latex-stack ${name === "overset" ? "chat-latex-overset" : "chat-latex-underset"}"><span class="chat-latex-stack-script">${renderLatexFragment(top.body)}</span><span class="chat-latex-stack-body">${renderLatexFragment(body.body)}</span></span>`;
          index = body.end - 1;
          continue;
        }
        if (name === "stackrel") {
          const top = readLatexArgument(text, index + 1);
          const body = readLatexArgument(text, top.end);
          html += `<span class="chat-latex-stack chat-latex-overset"><span class="chat-latex-stack-script">${renderLatexFragment(top.body)}</span><span class="chat-latex-stack-body">${renderLatexFragment(body.body)}</span></span>`;
          index = body.end - 1;
          continue;
        }
        if (name === "binom" || name === "tbinom" || name === "dbinom") {
          let top;
          let bottom;
          if (remainder) {
            [top, bottom] = clubInferCompactLatexArgs(remainder);
          } else {
            top = readLatexArgument(text, index + 1);
            bottom = readLatexArgument(text, top.end);
            index = bottom.end - 1;
            top = top.body;
            bottom = bottom.body;
          }
          html += clubRenderBinomFromArgs(top, bottom);
          continue;
        }
        if (name === "abs") {
          const arg = remainder ? { body: remainder } : readLatexArgument(text, index + 1);
          html += `<span class="chat-latex-delim">|</span>${renderLatexFragment(arg.body)}<span class="chat-latex-delim">|</span>`;
          if (!remainder) index = arg.end - 1;
          continue;
        }
        if (name === "substack") {
          const arg = remainder ? { body: remainder } : readLatexArgument(text, index + 1);
          const rows = clubSplitLatexTopLevel(arg.body, "\\\\").filter(Boolean).map((row) => [row]);
          html += clubRenderLatexRowsTable(rows, "chat-latex-substack");
          if (!remainder) index = arg.end - 1;
          continue;
        }
        if (name === "braket") {
          const arg = remainder ? { body: remainder } : readLatexArgument(text, index + 1);
          const body = String(arg.body || "");
          const rendered = body.includes("|")
            ? body.split("|").map((part) => renderLatexFragment(part)).join(`<span class="chat-latex-delim">|</span>`)
            : renderLatexFragment(body);
          html += `<span class="chat-latex-delim">\u27e8</span>${rendered}<span class="chat-latex-delim">\u27e9</span>`;
          if (!remainder) index = arg.end - 1;
          continue;
        }
        if (name === "inner") {
          const [left, right] = clubInferCompactLatexArgs(remainder);
          html += `<span class="chat-latex-delim">\u27e8</span>${renderLatexFragment(left)}<span class="chat-latex-op">,</span>${renderLatexFragment(right)}<span class="chat-latex-delim">\u27e9</span>`;
          continue;
        }
        if (name === "xleftarrow" || name === "xrightarrow" || name === "longrightarrow") {
          const arg = remainder ? { body: remainder } : (text[index + 1] === "{" ? readLatexArgument(text, index + 1) : { body: "" });
          html += clubRenderArrowWithOptionalLabel(arg.body, name === "xleftarrow" ? "\u27f5" : "\u27f6");
          if (!remainder && arg.end !== undefined) index = arg.end - 1;
          continue;
        }
        if (name === "overbrace" || name === "underbrace") {
          const arg = remainder ? { body: remainder } : readLatexArgument(text, index + 1);
          html += clubRenderBrace(name, arg.body);
          if (!remainder) index = arg.end - 1;
          continue;
        }
        if (name === "dva") {
          const body = readLatexArgument(text, index + 1);
          const variable = readLatexArgument(text, body.end);
          html += `<span class="chat-latex-frac"><span>d${renderLatexFragment(body.body)}</span><span>d${renderLatexFragment(variable.body)}</span></span>`;
          index = variable.end - 1;
          continue;
        }
        if (name === "dv") {
          if (remainder) {
            html += `<span class="chat-latex-frac"><span>d</span><span>d${renderLatexFragment(remainder)}</span></span>`;
            continue;
          }
          if (text[index + 1] === "{") {
            const variable = readLatexArgument(text, index + 1);
            html += `<span class="chat-latex-frac"><span>d</span><span>d${renderLatexFragment(variable.body)}</span></span>`;
            index = variable.end - 1;
          } else {
            html += `<span class="chat-latex-frac"><span>d</span><span>dt</span></span>`;
          }
          continue;
        }
        if (name === "DeclarePairedDelimiter") {
          continue;
        }
        if (name === "hline") {
          html += `<span class="chat-latex-hline"></span>`;
          continue;
        }
        if (name === "mathrm") {
          const arg = remainder ? { body: remainder } : readLatexArgument(text, index + 1);
          html += `<span class="chat-latex-text">${renderLatexFragment(arg.body)}</span>`;
          if (!remainder) index = arg.end - 1;
          continue;
        }
        if (name === "color") {
          const colorName = String(remainder || "inherit").toLowerCase();
          html += `<span class="chat-latex-color chat-latex-color-${escapeHtml(colorName)}">${escapeHtml(colorName)}</span>`;
          continue;
        }
        if (CLUB_LATEX_FONT_COMMANDS[name]) {
          const arg = remainder ? { body: remainder } : readLatexArgument(text, index + 1);
          html += clubRenderLatexFont(name, arg.body);
          if (!remainder) index = arg.end - 1;
          continue;
        }
        if (CLUB_LATEX_ACCENT_COMMANDS[name]) {
          const arg = remainder ? { body: remainder } : readLatexArgument(text, index + 1);
          html += clubRenderLatexAccent(name, arg.body);
          if (!remainder) index = arg.end - 1;
          continue;
        }
        html += CLUB_LATEX_SYMBOLS[name]
          ? `<span class="chat-latex-op">${escapeHtml(CLUB_LATEX_SYMBOLS[name])}</span>`
          : escapeHtml(`\\${name}`);
        continue;
      }
      const delimiter = text.slice(index, index + 2);
      if (CLUB_LATEX_DELIMITERS[delimiter] !== undefined) {
        const symbol = CLUB_LATEX_DELIMITERS[delimiter];
        if (symbol) html += `<span class="chat-latex-delim">${escapeHtml(symbol)}</span>`;
        index += 1;
        continue;
      }
      html += escapeHtml(text[index + 1] || "\\");
      index += 1;
      continue;
    }
    if (char === "^" || char === "_") {
      const arg = readLatexArgument(text, index + 1);
      html += char === "^" ? `<sup>${renderLatexFragment(arg.body)}</sup>` : `<sub>${renderLatexFragment(arg.body)}</sub>`;
      index = arg.end - 1;
      continue;
    }
    if (char === "{") {
      const end = findLatexGroupEnd(text, index);
      if (end >= 0) {
        html += renderLatexFragment(text.slice(index + 1, end));
        index = end;
        continue;
      }
    }
    if (char === "&") {
      html += `<span class="chat-latex-align-gap"></span>`;
      continue;
    }
    if (char === "~") {
      html += "&nbsp;";
      continue;
    }
    html += escapeHtml(char);
  }
  return html.replace(/[ \t]{2,}/g, " ");
}
function renderMarkdownMathToken(body, block = false) {
  let source = String(body || "").trim();
  if (source.startsWith("\\[") && source.endsWith("\\]")) source = source.slice(2, -2).trim();
  if (source.startsWith("\\(") && source.endsWith("\\)")) source = source.slice(2, -2).trim();
  if (source.startsWith("$$") && source.endsWith("$$")) source = source.slice(2, -2).trim();
  const text = renderLatexFragment(source);
  return block
    ? `<span class="chat-math chat-math-block">${text}</span>`
    : `<span class="chat-math">${text}</span>`;
}
function clubReplaceMarkdownMathTokens(text, stash) {
  const source = String(text || "");
  let out = "";
  for (let index = 0; index < source.length; index += 1) {
    if (source[index] === "\\") {
      if (source.startsWith("\\[", index)) {
        const end = source.indexOf("\\]", index + 2);
        if (end >= 0) {
          out += stash(renderMarkdownMathToken(source.slice(index, end + 2), true));
          index = end + 1;
          continue;
        }
      }
      if (source.startsWith("\\(", index)) {
        const end = source.indexOf("\\)", index + 2);
        if (end >= 0) {
          out += stash(renderMarkdownMathToken(source.slice(index, end + 2), false));
          index = end + 1;
          continue;
        }
      }
      const envMatch = source.slice(index).match(/^\\begin\{([A-Za-z*]+)\}/);
      if (envMatch) {
        const envName = envMatch[1];
        const bodyStart = index + envMatch[0].length;
        const endStart = clubFindLatexEnvironmentEnd(source, envName, bodyStart);
        if (endStart >= 0) {
          const endToken = `\\end{${envName}}`;
          out += stash(renderMarkdownMathToken(source.slice(index, endStart + endToken.length), true));
          index = endStart + endToken.length - 1;
          continue;
        }
      }
    }
    if (source[index] === "$" && source[index - 1] !== "\\") {
      if (source[index + 1] === "$") {
        const end = source.indexOf("$$", index + 2);
        if (end >= 0) {
          out += stash(renderMarkdownMathToken(source.slice(index, end + 2), true));
          index = end + 1;
          continue;
        }
      } else {
        let end = index + 1;
        while (end < source.length) {
          if (source[end] === "$" && source[end - 1] !== "\\") break;
          if (source[end] === "\n") {
            end = -1;
            break;
          }
          end += 1;
        }
        if (end > index && end < source.length && source[end] === "$") {
          out += stash(renderMarkdownMathToken(source.slice(index + 1, end), false));
          index = end;
          continue;
        }
      }
    }
    out += source[index];
  }
  return out;
}
function renderMarkdownInline(text, references = {}) {
  const tokens = [];
  const stash = (html) => {
    const token = `\uE000CHATMDTOKEN${tokens.length}\uE000`;
    tokens.push(html);
    return token;
  };
  let value = String(normalizeSoftWrappedMarkdown(text) || "");
  value = value.replace(/`([^`]+)`/g, (_, code) => stash(`<code>${escapeHtml(code)}</code>`));
  value = value.replace(/<kbd>([\s\S]*?)<\/kbd>/gi, (_, keys) => stash(`<kbd>${escapeHtml(keys)}</kbd>`));
  value = value.replace(/<(u|sub|sup)>([\s\S]*?)<\/\1>/gi, (_, tag, body) => stash(`<${tag.toLowerCase()}>${escapeHtml(body)}</${tag.toLowerCase()}>`));
  value = clubReplaceMarkdownMathTokens(value, stash);
  value = value.replace(/\\([\\`*_{}\[\]()#+\-.!|>~$])/g, (_, char) => stash(escapeHtml(char)));
  value = value.replace(
    /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g,
    (_, altText, url) => stash(markdownImageHtml(url, altText || "image")),
  );
  value = value.replace(
    /\[([^\]]+)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g,
    (_, label, url) => {
      const safeUrl = normalizeMarkdownUrl(url, { allowDataImage: false });
      if (!safeUrl) return escapeHtml(label);
      const externalAttrs = isInternalMarkdownLink(safeUrl)
        ? ""
        : ` target="_blank" rel="noreferrer noopener" data-chat-external-link="${escapeHtml(safeUrl)}"`;
      return stash(`<a href="${escapeHtml(safeUrl)}"${externalAttrs}>${escapeHtml(label)}</a>${richEmbedForUrl(safeUrl, label)}`);
    },
  );
  value = value.replace(/\[([^\]]+)\]\[([^\]]*)\]/g, (_, label, refName) => {
    const key = normalizeReferenceKey(refName || label);
    const target = references[key];
    if (!target) return escapeHtml(label);
    const safeUrl = normalizeMarkdownUrl(target.url, { allowDataImage: false });
    if (!safeUrl) return escapeHtml(label);
    const externalAttrs = isInternalMarkdownLink(safeUrl)
      ? ""
      : ` target="_blank" rel="noreferrer noopener" data-chat-external-link="${escapeHtml(safeUrl)}"`;
    return stash(`<a href="${escapeHtml(safeUrl)}"${externalAttrs}>${escapeHtml(label)}</a>${richEmbedForUrl(safeUrl, label)}`);
  });
  value = value.replace(/\[\^([^\]]+)\]/g, (_, refName) => {
    const key = normalizeReferenceKey(refName);
    const label = escapeHtml(refName);
    return stash(`<sup class="chat-footnote-ref"><a href="#chat-footnote-${escapeHtml(key)}">[${label}]</a></sup>`);
  });
  value = value.replace(
    /(^|[\s(])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?=$|[\s).,;!?])/gi,
    (_, prefix, email) => {
      const safeUrl = normalizeMarkdownUrl(`mailto:${email}`, { allowDataImage: false });
      return `${prefix}${stash(`<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noreferrer noopener" data-chat-external-link="${escapeHtml(safeUrl)}">${escapeHtml(email)}</a>`)}`;
    },
  );
  value = value.replace(/((?:https?:\/\/|mailto:|www\.)[^\s<]+)/g, (candidate) => {
    const { url, trailing } = markdownUrlParts(candidate);
    const safeUrl = normalizeMarkdownUrl(url, { allowDataImage: false });
    if (!safeUrl) return escapeHtml(candidate);
    const externalAttrs = isInternalMarkdownLink(safeUrl)
      ? ""
      : ` target="_blank" rel="noreferrer noopener" data-chat-external-link="${escapeHtml(safeUrl)}"`;
    return `${stash(`<a href="${escapeHtml(safeUrl)}"${externalAttrs}>${escapeHtml(url)}</a>${richEmbedForUrl(safeUrl, url)}`)}${escapeHtml(trailing)}`;
  });
  let html = applyBalancedUnderscoreFormatting(
    escapeHtml(value)
      .replace(/~~([^~]+)~~/g, "<del>$1</del>")
      .replace(/==([^=\n]+)==/g, "<mark>$1</mark>")
      .replace(/(^|[^*])\*\*\*([^*\n]+)\*\*\*(?=[^*]|$)/g, "$1<strong><em>$2</em></strong>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*\n]+)\*/g, "<em>$1</em>"),
  );
  html = html.replace(/\n/g, "<br />");
  html = html.replace(/\uE000CHATMDTOKEN(\d+)\uE000/g, (_, index) => tokens[Number(index)] || "");
  html = html.replace(/[\uE000\uE001]?CHATMDTOKEN\d+[\uE000\uE001]?/g, "");
  return html;
}
const brokenMarkdownImageUrls = new Set();
function markdownImageFailureNote(src, altText = "") {
  const label = src || altText || "image";
  return `<div class="chat-broken-media-note"><span class="chat-broken-media-icon" aria-hidden="true">!</span><span>Image failed to load: ${escapeHtml(label)}</span></div>`;
}
function markdownImageHtml(url, altText = "") {
  const safeUrl = normalizeMarkdownUrl(url) || "";
  if (!safeUrl || brokenMarkdownImageUrls.has(safeUrl))
    return markdownImageFailureNote(safeUrl, altText);
  return `<img class="chat-markdown-image" src="${escapeHtml(safeUrl)}" alt="${escapeHtml(altText || "image")}" loading="lazy" onerror="window.handleChatMarkdownImageError&&window.handleChatMarkdownImageError(this)" />`;
}
function normalizeCodeLanguageTag(value = "") {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/^language-/, "")
    .replace(/^lang-/, "")
    .replace(/^source\./, "")
    .replace(/[^\w#+.-]+/g, "");
}
async function loadCodeSyntaxConfig() {
  const force = !!arguments[0]?.force;
  if (codeSyntaxConfigPromise && !force) return codeSyntaxConfigPromise;
  codeSyntaxConfigPromise = (async () => {
    let config = force ? null : CODE_SYNTAX_CONFIG;
    if (!config || typeof config !== "object") {
      try {
        const response = await fetch(`${CODE_SYNTAX_CONFIG_URL}?_=${Date.now()}`, {
          cache: "no-store",
        });
        if (response.ok) config = await response.json();
      } catch (error) {}
    }
    if ((!config || typeof config !== "object") && CODE_SYNTAX_CONFIG && typeof CODE_SYNTAX_CONFIG === "object") {
      config = CODE_SYNTAX_CONFIG;
    }
    if (!config || typeof config !== "object") {
      config = {
        aliases: {},
        fallback_family: "clike",
        theme: { tokens: {} },
        families: {},
      };
    }
    applyCodeSyntaxTheme(config);
    if (force) {
      await rehighlightExistingCodeBlocks(config);
    }
    return config;
  })();
  return codeSyntaxConfigPromise;
}
async function rehighlightExistingCodeBlocks(config, root = document) {
  if (!root || typeof root.querySelectorAll !== "function") return;
  const nodes = Array.from(
    root.querySelectorAll("pre.chat-code code[data-code-block='1']"),
  );
  for (const node of nodes) {
    delete node.dataset.syntaxHighlighted;
    delete node.dataset.syntaxPending;
    const lang = normalizeCodeLanguageTag(node.dataset.codeLang || "");
    if (!lang || lang === "text" || lang === "plaintext") {
      node.dataset.syntaxHighlighted = "1";
      continue;
    }
    const rendered = renderSyntaxHighlightedHtml(node.textContent || "", lang, config);
    if (rendered) node.innerHTML = rendered;
    node.dataset.syntaxHighlighted = "1";
  }
}
function applyCodeSyntaxTheme(config) {
  if (!config || typeof config !== "object") return;
  const root = document.documentElement;
  const tokens = config.theme?.tokens && typeof config.theme.tokens === "object"
    ? config.theme.tokens
    : {};
  const nextNames = new Set(
    Object.keys(tokens)
      .map((name) => String(name || "").trim())
      .filter(Boolean),
  );
  (codeSyntaxThemeTokenNames || new Set()).forEach((name) => {
    if (!nextNames.has(name)) {
      root.style.removeProperty(`--chat-syntax-${String(name).replace(/[^a-z0-9_-]/gi, "-")}`);
    }
  });
  Object.entries(tokens).forEach(([name, color]) => {
    if (!name || !color) return;
    root.style.setProperty(`--chat-syntax-${String(name).replace(/[^a-z0-9_-]/gi, "-")}`, String(color));
  });
  codeSyntaxThemeTokenNames = nextNames;
  codeSyntaxThemeApplied = nextNames.size > 0;
}
function syntaxTokenSpan(kind, innerHtml) {
  return `<span class="chat-syntax-token chat-syntax-${escapeHtml(kind)}">${String(innerHtml || "")}</span>`;
}
function syntaxTokenEscapedHtml(kind, escapedText) {
  return syntaxTokenSpan(kind, String(escapedText || ""));
}
function syntaxTokenHtml(kind, text) {
  return syntaxTokenSpan(kind, escapeHtml(text));
}
function stashCodeSyntaxToken(tokens, html) {
  const marker = `\uE100${String.fromCharCode(0xE200 + tokens.length)}\uE101`;
  tokens.push(String(html || ""));
  return marker;
}
function restoreCodeSyntaxTokens(text, tokens) {
  return String(text || "").replace(/\uE100([\uE200-\uF8FF])\uE101/g, (_, encoded) => {
    const index = String(encoded || "").charCodeAt(0) - 0xE200;
    return tokens[index] || "";
  });
}
function replaceCodeSyntaxWithTokens(text, regex, tokens, handler) {
  return String(text || "").replace(regex, (...args) =>
    stashCodeSyntaxToken(tokens, handler(...args)),
  );
}
function finalizeSyntaxHtml(text, tokens) {
  return restoreCodeSyntaxTokens(escapeHtml(String(text || "")), tokens);
}
const CHAT_SYNTAX_NUMBER_RE = /\b(?:0[xX][0-9a-fA-F](?:_?[0-9a-fA-F])*|0[bB][01](?:_?[01])*|0[oO][0-7](?:_?[0-7])*|\d(?:_?\d)*(?:\.\d(?:_?\d)*)?(?:[eE][+-]?\d(?:_?\d)*)?)\b/g;
const CHAT_SYNTAX_OPERATOR_RE = /(\.\.\.?|=>|->|<-|::|:=|<>|\?\?=?|\?\.|\+\+|--|\+=|-=|\*=|\/=|%=|&&|\|\||<<=?|>>=?|<=|>=|==|!=|===|!==|<=>|=~|!~|\/\/=?|\*\*=?|&=|\|=|\^=|[=<>!*+\-/%&|^?~@])/g;
const CHAT_SYNTAX_SEPARATOR_RE = /([()[\]{}.,;:])/g;
function compileWordRegex(words = [], flags = "g") {
  const values = Array.from(
    new Set(
      (Array.isArray(words) ? words : [])
        .map((value) => String(value || "").trim())
        .filter(Boolean),
    ),
  ).sort((left, right) => right.length - left.length);
  if (!values.length) return null;
  return new RegExp(
    `\\b(${values.map((value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})\\b`,
    flags,
  );
}
function definitionArray(definition, key) {
  return Array.isArray(definition?.[key]) ? definition[key] : [];
}
function definitionFlags(definition, baseFlags = "g") {
  return definition?.case_insensitive && !baseFlags.includes("i") ? `${baseFlags}i` : baseFlags;
}
function compileDefinitionWordRegex(definition, key, baseFlags = "g") {
  return compileWordRegex(definitionArray(definition, key), definitionFlags(definition, baseFlags));
}
function definitionHasWord(definition, keys, candidate) {
  const target = String(candidate || "");
  if (!target) return false;
  const normalized = definition?.case_insensitive ? target.toLowerCase() : target;
  return (Array.isArray(keys) ? keys : [keys]).some((key) =>
    definitionArray(definition, key).some((value) =>
      (definition?.case_insensitive ? String(value || "").toLowerCase() : String(value || "")) === normalized,
    ),
  );
}
function replaceDefinitionPatterns(text, patterns, definition, tokens, renderer) {
  let html = String(text || "");
  definitionArray({ patterns }, "patterns").forEach((pattern) => {
    try {
      const flags = definitionFlags(definition, pattern.includes("[\\s\\S]") ? "g" : "gm");
      html = html.replace(new RegExp(`(${pattern})`, flags), (match) =>
        stashCodeSyntaxToken(tokens, renderer(match)),
      );
    } catch (error) {}
  });
  return html;
}
function renderEscapedLiteral(kind, text) {
  const escaped = escapeHtml(String(text || ""));
  const inner = escaped.replace(
    /(\\(?:x[0-9A-Fa-f]{2}|u\{[0-9A-Fa-f]+\}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|[0-7]{1,3}|.))/g,
    (match) => syntaxTokenSpan("escape", match),
  );
  return syntaxTokenSpan(kind, inner);
}
function highlightMarkupCode(raw, definition, config) {
  const tokens = [];
  let html = escapeHtml(raw);
  html = replaceCodeSyntaxWithTokens(html, /(&lt;!--[\s\S]*?--&gt;)/g, tokens, (match) => syntaxTokenEscapedHtml("comment", match));
  html = replaceCodeSyntaxWithTokens(
    html,
    /(&lt;!(?:DOCTYPE|doctype)[\s\S]*?&gt;|&lt;\?[\s\S]*?\?&gt;)/g,
    tokens,
    (match) => syntaxTokenEscapedHtml("preprocessor", match),
  );
  html = replaceCodeSyntaxWithTokens(html, /(&lt;\/?)([A-Za-z][\w:-]*)([\s\S]*?)(\/?&gt;)/g, tokens, (_, open, tag, attrs, close) => {
    let renderedAttrs = String(attrs || "");
    renderedAttrs = renderedAttrs.replace(
      /([A-Za-z_:][\w:.-]*)(\s*=\s*)(".*?"|'.*?'|[^\s"'=<>`]+)/g,
      (match, name, equals, value) =>
        `${syntaxTokenHtml("attribute", name)}${syntaxTokenHtml("operator", equals)}${renderEscapedLiteral("string", value)}`,
    );
    renderedAttrs = renderedAttrs.replace(/(&amp;[#A-Za-z0-9]+;)/g, (match) => syntaxTokenEscapedHtml("escape", match));
    return `${syntaxTokenEscapedHtml("separator", open)}${syntaxTokenHtml("tag", tag)}${renderedAttrs}${syntaxTokenEscapedHtml("separator", close)}`;
  });
  return `${restoreCodeSyntaxTokens(html, tokens)}<span class="chat-syntax-rawcopy" hidden>${escapeHtml(raw)}</span>`;
}
function highlightDataCode(raw, definition, config, lang) {
  const tokens = [];
  let html = String(raw || "");
  html = replaceDefinitionPatterns(html, definition?.comment_patterns || ["#.*$"], definition, tokens, (match) => syntaxTokenHtml("comment", match));
  html = html.replace(/("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')/g, (match) =>
    stashCodeSyntaxToken(tokens, renderEscapedLiteral("string", match)),
  );
  html = html.replace(
    /(^|\n)(\s*)("(?:(?:\\.|[^"\\])*)"|'(?:(?:\\.|[^'\\])*)')(\s*)(:)/g,
    (match, prefix, indent, key, gap, colon) =>
      `${prefix}${indent}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("property", key))}${gap}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("separator", colon))}`,
  );
  html = html.replace(/(^|\n)(\s*)([^:\n=#][^:\n=]*?)(\s*)(:)(?=\s|$)/g, (match, prefix, indent, key, gap, colon) =>
    `${prefix}${indent}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("property", key))}${gap}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("separator", colon))}`,
  );
  html = html.replace(/(^|\n)(\s*)([A-Za-z0-9_.-]+)(\s*)(=)/g, (match, prefix, indent, key, gap, equals) =>
    `${prefix}${indent}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("property", key))}${gap}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("operator", equals))}`,
  );
  html = replaceCodeSyntaxWithTokens(html, /\b(true|false|null|yes|no|on|off)\b/gi, tokens, (match) => syntaxTokenHtml("literal", match));
  html = replaceCodeSyntaxWithTokens(html, /([&*][A-Za-z_][\w-]*)/g, tokens, (match) => syntaxTokenHtml("variable", match));
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_NUMBER_RE, tokens, (match) => syntaxTokenHtml("number", match));
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_OPERATOR_RE, tokens, (match) => syntaxTokenHtml("operator", match));
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_SEPARATOR_RE, tokens, (match) => syntaxTokenHtml("separator", match));
  return finalizeSyntaxHtml(html, tokens);
}
function highlightStyleCode(raw, definition, config, lang) {
  const tokens = [];
  let html = String(raw || "");
  html = replaceDefinitionPatterns(html, definition?.comment_patterns || ["/\\*[\\s\\S]*?\\*/"], definition, tokens, (match) => syntaxTokenHtml("comment", match));
  html = html.replace(/("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')/g, (match) =>
    stashCodeSyntaxToken(tokens, renderEscapedLiteral("string", match)),
  );
  html = html.replace(/(@[A-Za-z-]+)/g, (match) => stashCodeSyntaxToken(tokens, syntaxTokenHtml("keyword", match)));
  html = html.replace(/(^|\}|\n)(\s*)([^@\n][^{]*?)(\s*)(?=\{)/g, (match, prefix, indent, selector, gap) =>
    `${prefix}${indent}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("selector", selector.trimEnd()))}${gap}`,
  );
  html = html.replace(/(^|\{|;|\n)(\s*)((?:--)?[A-Za-z_][\w-]*)(\s*)(:)/g, (match, prefix, indent, property, gap, colon) =>
    `${prefix}${indent}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("property", property))}${gap}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("separator", colon))}`,
  );
  html = html.replace(/\b([A-Za-z-]+)(?=\s*\()/g, (match) =>
    stashCodeSyntaxToken(tokens, syntaxTokenHtml("function", match)),
  );
  html = replaceCodeSyntaxWithTokens(html, /(#[0-9a-fA-F]{3,8}\b)/g, tokens, (match) => syntaxTokenHtml("constant", match));
  html = html.replace(/(-?(?:\d(?:_?\d)*(?:\.\d(?:_?\d)*)?))(px|rem|em|ch|vw|vh|dvw|dvh|svw|svh|lvw|lvh|%|ms|s|deg|rad|turn|fr)\b/g, (match, numberValue, unitValue) =>
    `${stashCodeSyntaxToken(tokens, syntaxTokenHtml("number", numberValue))}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("unit", unitValue))}`,
  );
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_NUMBER_RE, tokens, (match) => syntaxTokenHtml("number", match));
  html = replaceCodeSyntaxWithTokens(html, /\b(px|rem|em|ch|vw|vh|dvw|dvh|svw|svh|lvw|lvh|%|ms|s|deg|rad|turn|fr)\b/g, tokens, (match) =>
    syntaxTokenHtml("unit", match),
  );
  const literalRe = compileDefinitionWordRegex(definition, "literals");
  if (literalRe) html = replaceCodeSyntaxWithTokens(html, literalRe, tokens, (match) => syntaxTokenHtml("literal", match));
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_OPERATOR_RE, tokens, (match) => syntaxTokenHtml("operator", match));
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_SEPARATOR_RE, tokens, (match) => syntaxTokenHtml("separator", match));
  return finalizeSyntaxHtml(html, tokens);
}
function highlightSqlCode(raw, definition, config) {
  const tokens = [];
  let html = String(raw || "");
  html = replaceDefinitionPatterns(html, definition?.comment_patterns || ["--.*$", "/\\*[\\s\\S]*?\\*/"], definition, tokens, (match) => syntaxTokenHtml("comment", match));
  html = html.replace(/("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`[^`]*`)/g, (match) =>
    stashCodeSyntaxToken(tokens, renderEscapedLiteral("string", match)),
  );
  html = replaceCodeSyntaxWithTokens(html, /([@:$][A-Za-z_][\w$]*)/g, tokens, (match) => syntaxTokenHtml("variable", match));
  const functionDeclRe = compileDefinitionWordRegex(definition, "function_declaration_keywords");
  if (functionDeclRe) {
    html = html.replace(new RegExp(`(^|\\n)(\\s*)(${definitionArray(definition, "function_declaration_keywords").join("|")})(\\s+)([A-Za-z_][\\w$]*)`, "gi"), (match, prefix, indent, keyword, gap, name) =>
      `${prefix}${indent}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("keyword", keyword))}${gap}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("function", name))}`,
    );
  }
  const keywordRe = compileDefinitionWordRegex(definition, "keywords", "g");
  if (keywordRe) html = replaceCodeSyntaxWithTokens(html, keywordRe, tokens, (match) => syntaxTokenHtml("keyword", match));
  const typeRe = compileDefinitionWordRegex(definition, "types", "g");
  if (typeRe) html = replaceCodeSyntaxWithTokens(html, typeRe, tokens, (match) => syntaxTokenHtml("type", match));
  const builtinRe = compileDefinitionWordRegex(definition, "builtins", "g");
  if (builtinRe) html = replaceCodeSyntaxWithTokens(html, builtinRe, tokens, (match) => syntaxTokenHtml("builtin", match));
  const literalRe = compileDefinitionWordRegex(definition, "literals", "g");
  if (literalRe) html = replaceCodeSyntaxWithTokens(html, literalRe, tokens, (match) => syntaxTokenHtml("literal", match));
  html = replaceCodeSyntaxWithTokens(html, /\b([A-Za-z_][\w$]*)(?=\s*\()/g, tokens, (match) => syntaxTokenHtml("function", match));
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_NUMBER_RE, tokens, (match) => syntaxTokenHtml("number", match));
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_OPERATOR_RE, tokens, (match) => syntaxTokenHtml("operator", match));
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_SEPARATOR_RE, tokens, (match) => syntaxTokenHtml("separator", match));
  return finalizeSyntaxHtml(html, tokens);
}
function highlightShellCode(raw, definition, config, family) {
  const tokens = [];
  let html = String(raw || "");
  html = replaceDefinitionPatterns(html, definition?.comment_patterns || ["#.*$"], definition, tokens, (match) => syntaxTokenHtml("comment", match));
  html = replaceDefinitionPatterns(html, definition?.verbatim_string_patterns || [], definition, tokens, (match) => renderEscapedLiteral("string", match));
  html = html.replace(/("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)/g, (match) =>
    stashCodeSyntaxToken(tokens, renderEscapedLiteral("string", match)),
  );
  html = replaceDefinitionPatterns(
    html,
    definition?.variable_patterns || ["\\$\\{?[A-Za-z_][A-Za-z0-9_]*\\}?", "\\$[0-9@*#?!$-]"],
    definition,
    tokens,
    (match) => syntaxTokenHtml(match.startsWith("$") && /\$[0-9@*#?!$-]/.test(match) ? "parameter" : "variable", match),
  );
  html = replaceDefinitionPatterns(html, definition?.operator_patterns || [], definition, tokens, (match) => syntaxTokenHtml("operator", match));
  const keywordRe = compileDefinitionWordRegex(definition, "keywords");
  if (keywordRe) html = replaceCodeSyntaxWithTokens(html, keywordRe, tokens, (match) => syntaxTokenHtml("keyword", match));
  const builtinRe = compileDefinitionWordRegex(definition, "builtins");
  if (builtinRe) html = replaceCodeSyntaxWithTokens(html, builtinRe, tokens, (match) => syntaxTokenHtml("builtin", match));
  const literalRe = compileDefinitionWordRegex(definition, "literals");
  if (literalRe) html = replaceCodeSyntaxWithTokens(html, literalRe, tokens, (match) => syntaxTokenHtml("literal", match));
  html = html.replace(/(^|\n|\|\s*|&&\s*|\|\|\s*|;\s*)([A-Za-z_./-][A-Za-z0-9_./:-]*)(?=\s|$)/g, (match, prefix, command) =>
    `${prefix}${stashCodeSyntaxToken(tokens, syntaxTokenHtml(family === "powershell" && /^[A-Z][a-z]+-[A-Z]/.test(command) ? "builtin" : "function", command))}`,
  );
  html = html.replace(/(^|\s)(--?[A-Za-z0-9][A-Za-z0-9-]*)/g, (match, prefix, flag) =>
    `${prefix}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("property", flag))}`,
  );
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_NUMBER_RE, tokens, (match) => syntaxTokenHtml("number", match));
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_OPERATOR_RE, tokens, (match) => syntaxTokenHtml("operator", match));
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_SEPARATOR_RE, tokens, (match) => syntaxTokenHtml("separator", match));
  return finalizeSyntaxHtml(html, tokens);
}
function highlightDiffCode(raw, definition, config) {
  const tokens = [];
  let html = String(raw || "");
  html = html.replace(/(^|\n)(@@.*$)/gm, (match, prefix, line) =>
    `${prefix}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("preprocessor", line))}`,
  );
  html = html.replace(/(^|\n)(\+.*$)/gm, (match, prefix, line) =>
    `${prefix}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("inserted", line))}`,
  );
  html = html.replace(/(^|\n)(-.*$)/gm, (match, prefix, line) =>
    `${prefix}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("deleted", line))}`,
  );
  html = html.replace(/(^|\n)(diff .*|index .*|--- .*|\+\+\+ .*)$/gm, (match, prefix, line) =>
    `${prefix}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("meta", line))}`,
  );
  return finalizeSyntaxHtml(html, tokens);
}
function highlightGenericCode(raw, definition, config, family) {
  const tokens = [];
  let html = String(raw || "");
  const commentPatterns =
    definition?.comment_patterns && Array.isArray(definition.comment_patterns)
      ? definition.comment_patterns
      : family === "python"
        ? ["#.*$"]
        : family === "basic"
          ? ["'.*$", "\\bREM\\b.*$"]
          : family === "lisp"
            ? [";.*$"]
            : ["//.*$", "/\\*[\\s\\S]*?\\*/"];
  html = replaceDefinitionPatterns(html, definition?.doc_comment_patterns || [], definition, tokens, (match) => syntaxTokenHtml("doc", match));
  html = replaceDefinitionPatterns(html, commentPatterns, definition, tokens, (match) => syntaxTokenHtml("comment", match));
  html = replaceDefinitionPatterns(html, definition?.preprocessor_patterns || [], definition, tokens, (match) => syntaxTokenHtml("preprocessor", match));
  html = replaceDefinitionPatterns(html, definition?.regex_patterns || [], definition, tokens, (match) => renderEscapedLiteral("regex", match));
  if (definition?.regex_literals) {
    html = html.replace(
      /(^|[=(,:;!?[\]{}]\s*|\b(?:return|case|throw|yield|when)\s+)(\/(?![/*])(?:\\.|[^/\\\n]|\[(?:\\.|[^\]\\\n])*\])+\/[dgimsuvy]*)/gm,
      (match, prefix, literal) => `${prefix}${stashCodeSyntaxToken(tokens, renderEscapedLiteral("regex", literal))}`,
    );
  }
  html = replaceDefinitionPatterns(html, definition?.verbatim_string_patterns || [], definition, tokens, (match) => renderEscapedLiteral("string", match));
  if (definition?.character_literals) {
    html = html.replace(/(?:L|u8|u|U|b|B)?'(?:\\.|[^'\\\r\n]){1,4}'/g, (match) =>
      stashCodeSyntaxToken(tokens, renderEscapedLiteral("character", match)),
    );
  }
  html = html.replace(
    /(?:[rRuUbBfF]{0,3})(?:"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)/g,
    (match) => stashCodeSyntaxToken(tokens, renderEscapedLiteral("string", match)),
  );
  html = replaceDefinitionPatterns(html, definition?.variable_patterns || [], definition, tokens, (match) => syntaxTokenHtml("variable", match));
  html = replaceDefinitionPatterns(html, definition?.symbol_patterns || [], definition, tokens, (match) => syntaxTokenHtml("symbol", match));
  html = html.replace(/(@[A-Za-z_][\w.]*)/g, (match) =>
    stashCodeSyntaxToken(tokens, syntaxTokenHtml(definition?.annotation_token || "decorator", match)),
  );
  const typeDeclKeywords = definitionArray(definition, "type_declaration_keywords");
  if (typeDeclKeywords.length) {
    const typeDeclRe = new RegExp(
      `(^|\\n)(\\s*)(${typeDeclKeywords.map((value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})(\\s+)([A-Za-z_][A-Za-z0-9_]*)`,
      definitionFlags(definition, "g"),
    );
    html = html.replace(typeDeclRe, (match, prefix, indent, keyword, gap, name) =>
      `${prefix}${indent}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("keyword", keyword))}${gap}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("type", name))}`,
    );
  }
  const namespaceDeclKeywords = definitionArray(definition, "namespace_declaration_keywords");
  if (namespaceDeclKeywords.length) {
    const namespaceDeclRe = new RegExp(
      `(^|\\n)(\\s*)(${namespaceDeclKeywords.map((value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})(\\s+)([A-Za-z_][A-Za-z0-9_.:]*)`,
      definitionFlags(definition, "g"),
    );
    html = html.replace(namespaceDeclRe, (match, prefix, indent, keyword, gap, name) =>
      `${prefix}${indent}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("keyword", keyword))}${gap}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("namespace", name))}`,
    );
  }
  const functionDeclKeywords = definitionArray(definition, "function_declaration_keywords");
  if (functionDeclKeywords.length) {
    const functionDeclRe = new RegExp(
      `(^|\\n)(\\s*)(${functionDeclKeywords.map((value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})(\\s+)([A-Za-z_][A-Za-z0-9_]*)`,
      definitionFlags(definition, "g"),
    );
    html = html.replace(functionDeclRe, (match, prefix, indent, keyword, gap, name) =>
      `${prefix}${indent}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("keyword", keyword))}${gap}${stashCodeSyntaxToken(tokens, syntaxTokenHtml("function", name))}`,
    );
  }
  const keywordRe = compileDefinitionWordRegex(definition, "keywords");
  if (keywordRe) html = replaceCodeSyntaxWithTokens(html, keywordRe, tokens, (match) => syntaxTokenHtml("keyword", match));
  const storageRe = compileDefinitionWordRegex(definition, "storage");
  if (storageRe) html = replaceCodeSyntaxWithTokens(html, storageRe, tokens, (match) => syntaxTokenHtml("storage", match));
  const typeRe = compileDefinitionWordRegex(definition, "types");
  if (typeRe) html = replaceCodeSyntaxWithTokens(html, typeRe, tokens, (match) => syntaxTokenHtml("type", match));
  const builtinRe = compileDefinitionWordRegex(definition, "builtins");
  if (builtinRe) html = replaceCodeSyntaxWithTokens(html, builtinRe, tokens, (match) => syntaxTokenHtml("builtin", match));
  const constantRe = compileDefinitionWordRegex(definition, "constants");
  if (constantRe) html = replaceCodeSyntaxWithTokens(html, constantRe, tokens, (match) => syntaxTokenHtml("constant", match));
  const literalRe = compileDefinitionWordRegex(definition, "literals");
  if (literalRe) html = replaceCodeSyntaxWithTokens(html, literalRe, tokens, (match) => syntaxTokenHtml("literal", match));
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_NUMBER_RE, tokens, (match) => syntaxTokenHtml("number", match));
  html = replaceDefinitionPatterns(html, definition?.macro_patterns || [], definition, tokens, (match) => syntaxTokenHtml("function", match));
  html = html.replace(/\b([A-Za-z_][A-Za-z0-9_]*)\b(?=\s*\()/g, (match) => {
    if (definitionHasWord(definition, ["keywords", "storage", "types", "literals"], match)) return match;
    return stashCodeSyntaxToken(
      tokens,
      syntaxTokenHtml(definitionHasWord(definition, "builtins", match) ? "builtin" : "function", match),
    );
  });
  html = replaceCodeSyntaxWithTokens(html, /\b([A-Z][A-Z0-9_]{2,})\b/g, tokens, (match) => syntaxTokenHtml("constant", match));
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_OPERATOR_RE, tokens, (match) => syntaxTokenHtml("operator", match));
  html = replaceCodeSyntaxWithTokens(html, CHAT_SYNTAX_SEPARATOR_RE, tokens, (match) => syntaxTokenHtml("separator", match));
  return finalizeSyntaxHtml(html, tokens);
}
function resolveCodeSyntaxFamily(lang, config) {
  const normalized = normalizeCodeLanguageTag(lang);
  const aliasMap = config?.aliases && typeof config.aliases === "object" ? config.aliases : {};
  if (normalized && aliasMap[normalized]) return String(aliasMap[normalized]);
  if (normalized.includes("html") || normalized.includes("xml") || normalized.includes("svg") || normalized.includes("vue") || normalized.includes("svelte")) return "markup";
  if (normalized.includes("json") || normalized.includes("yaml") || normalized.includes("toml") || normalized.includes("ini")) return "data";
  if (normalized.includes("css") || normalized.includes("scss") || normalized.includes("sass") || normalized.includes("less") || normalized.includes("styl")) return "styles";
  if (normalized.includes("sql")) return "sql";
  if (normalized.includes("diff") || normalized.includes("patch")) return "diff";
  if (normalized.includes("graphql") || normalized === "gql") return "graphql";
  if (normalized.includes("powershell") || normalized === "pwsh" || normalized === "ps1") return "powershell";
  if (normalized.includes("bash") || normalized.includes("shell") || normalized.includes("zsh") || normalized.includes("fish") || normalized.includes("docker")) return "shell";
  if (normalized.includes("typescript") || normalized === "ts" || normalized === "tsx") return "typescript";
  if (normalized.includes("javascript") || normalized === "js" || normalized === "jsx" || normalized === "mjs" || normalized === "cjs") return "javascript";
  if (normalized.includes("rust")) return "rust";
  if (normalized === "go" || normalized.includes("golang")) return "go";
  if (normalized.includes("java")) return "java";
  if (normalized.includes("csharp") || normalized === "cs") return "csharp";
  if (normalized.includes("kotlin") || normalized === "kt" || normalized === "kts") return "kotlin";
  if (normalized.includes("swift")) return "swift";
  if (normalized.includes("php")) return "php";
  if (normalized.includes("ruby") || normalized === "rb") return "ruby";
  if (normalized.includes("perl") || normalized === "pl" || normalized === "pm") return "perl";
  if (normalized.includes("python") || normalized === "py") return "python";
  if (normalized.includes("lua")) return "lua";
  if (normalized === "r" || normalized.includes("rscript")) return "r";
  if (normalized.includes("asm") || normalized.includes("nasm") || normalized.includes("masm")) return "asm";
  if (normalized.includes("vb") || normalized.includes("basic") || normalized.includes("pascal")) return "basic";
  if (normalized.includes("lisp") || normalized.includes("clojure") || normalized.includes("scheme") || normalized.includes("racket") || normalized.includes("elisp") || normalized.includes("hy")) return "lisp";
  return String(config?.fallback_family || "clike");
}
function renderSyntaxHighlightedHtml(raw, lang, config) {
  const normalized = normalizeCodeLanguageTag(lang);
  if (!raw) return "";
  const family = resolveCodeSyntaxFamily(normalized, config);
  const definition = config?.families?.[family] || {};
  if (family === "markup") return highlightMarkupCode(raw, definition, config);
  if (family === "data") return highlightDataCode(raw, definition, config, normalized);
  if (family === "styles") return highlightStyleCode(raw, definition, config, normalized);
  if (family === "sql") return highlightSqlCode(raw, definition, config);
  if (family === "shell" || family === "powershell") return highlightShellCode(raw, definition, config, family);
  if (family === "diff") return highlightDiffCode(raw, definition, config);
  return highlightGenericCode(raw, definition, config, family);
}
async function highlightCodeElement(node) {
  if (!node || node.dataset.syntaxHighlighted === "1" || node.dataset.syntaxPending === "1") return;
  node.dataset.syntaxPending = "1";
  try {
    const config = await loadCodeSyntaxConfig();
    const lang = normalizeCodeLanguageTag(node.dataset.codeLang || "");
    if (!lang || lang === "text" || lang === "plaintext") {
      node.dataset.syntaxHighlighted = "1";
      return;
    }
    const rendered = renderSyntaxHighlightedHtml(node.textContent || "", lang, config);
    if (rendered) node.innerHTML = rendered;
    node.dataset.syntaxHighlighted = "1";
  } catch (error) {
    node.dataset.syntaxHighlighted = "1";
  } finally {
    delete node.dataset.syntaxPending;
  }
}
function flushCodeSyntaxHighlightQueue() {
  codeSyntaxHighlightScheduled = false;
  const nextNodes = Array.from(codeSyntaxHighlightQueue).slice(0, 3);
  nextNodes.forEach((node) => codeSyntaxHighlightQueue.delete(node));
  Promise.all(nextNodes.map((node) => highlightCodeElement(node))).finally(() => {
    if (codeSyntaxHighlightQueue.size) scheduleCodeSyntaxHighlightFlush();
  });
}
function scheduleCodeSyntaxHighlightFlush() {
  if (codeSyntaxHighlightScheduled) return;
  codeSyntaxHighlightScheduled = true;
  const runner = () => flushCodeSyntaxHighlightQueue();
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(runner, { timeout: 180 });
    return;
  }
  setTimeout(runner, 32);
}
function scheduleCodeSyntaxHighlight(root) {
  if (!root || typeof root.querySelectorAll !== "function") return;
  root.querySelectorAll("pre.chat-code code[data-code-block='1']").forEach((node) => {
    if (node.dataset.syntaxHighlighted === "1" || node.dataset.syntaxPending === "1") return;
    codeSyntaxHighlightQueue.add(node);
  });
  if (codeSyntaxHighlightQueue.size) scheduleCodeSyntaxHighlightFlush();
}
function chatHtmlNeedsCodeSyntaxHighlight(html = "") {
  const text = String(html || "");
  return text.includes('data-code-block="1"') || text.includes("data-code-block='1'");
}
function chatStreamingMarkdownShouldUsePlainPreview(text = "") {
  const source = String(text || "");
  if (!source) return false;
  const dollarBlocks = source.match(/(^|\n)\s*\$\$\s*($|\n)/g) || [];
  if (dollarBlocks.length % 2 === 1) return true;
  const openDisplayMath = source.lastIndexOf("\\[");
  const closeDisplayMath = source.lastIndexOf("\\]");
  if (openDisplayMath > closeDisplayMath) return true;
  const beginMatches = Array.from(source.matchAll(/\\begin\{([A-Za-z*]+)\}/g));
  if (beginMatches.length) {
    const lastBegin = beginMatches[beginMatches.length - 1];
    const envName = lastBegin?.[1] || "";
    if (envName && source.lastIndexOf(`\\end{${envName}}`) < Number(lastBegin.index || 0)) {
      return true;
    }
  }
  return false;
}
function renderStreamingInlineFallback(text) {
  let rendered = escapeHtml(normalizeSoftWrappedMarkdown(text))
    .replace(/`([\s\S]+?)`/g, (_, body) => {
      const inlineBody = String(body || "").replace(/\s*\n\s*/g, " ").trim();
      return `<code>${inlineBody}</code>`;
    })
    .replace(/\*\*([\s\S]+?)\*\*/g, (_, body) => {
      const inlineBody = String(body || "").replace(/\s*\n\s*/g, " ").trim();
      return `<strong>${inlineBody}</strong>`;
    })
    .replace(/\*([\s\S]+?)\*/g, (_, body) => {
      const inlineBody = String(body || "").replace(/\s*\n\s*/g, " ").trim();
      return `<em>${inlineBody}</em>`;
    });
  if (rendered.startsWith("**") && !/<strong>/.test(rendered)) {
    const remainder = rendered.slice(2);
    const newlineIndex = remainder.indexOf("\n");
    if (newlineIndex >= 0) {
      rendered = `<strong>${remainder.slice(0, newlineIndex)}</strong>${remainder.slice(newlineIndex)}`;
    } else {
      rendered = `<strong>${remainder}</strong>`;
    }
  }
  return rendered;
}
function renderStreamingOpenFencePreview(text) {
  const source = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  if (!source || !source.includes("\n")) return "";
  const lines = source.split("\n");
  const openIndex = lines.findIndex((line) =>
    /^(```|~~~)(?:\s*(.*?))?\s*$/.test(String(line || "").trim()),
  );
  if (openIndex < 0) return "";
  const fenceMatch = String(lines[openIndex] || "")
    .trim()
    .match(/^(```|~~~)(?:\s*(.*?))?\s*$/);
  if (!fenceMatch) return "";
  const fence = fenceMatch[1];
  for (let index = openIndex + 1; index < lines.length; index += 1) {
    if (String(lines[index] || "").trim().startsWith(fence)) {
      return "";
    }
  }
  const prefix = lines.slice(0, openIndex).join("\n").trim();
  const codeBody = lines.slice(openIndex + 1).join("\n");
  const lang = String(fenceMatch[2] || "").trim() || "text";
  const prefixHtml = prefix
    ? `<div class="chat-live-markdown-prefix">${renderMarkdownInline(prefix)}</div>`
    : "";
  return `${prefixHtml}<pre class="chat-code chat-live-code-preview"><div class="chat-code-lang">${escapeHtml(lang)}</div><code>${escapeHtml(codeBody)}</code></pre>`;
}
function streamingMarkdownLiveCanUseBlockRenderer(text) {
  const source = normalizeSplitMarkdownListMarkers(text);
  if (!source || source.length > CHAT_STREAM_MARKDOWN_TAIL_SOFT_LIMIT) return false;
  if (chatStreamingMarkdownShouldUsePlainPreview(source)) return false;
  return /(^|\n)\s{0,3}(?:[-+*]|\d+\.)\s+\S/.test(source);
}
function renderStreamingMarkdownLiveHtml(text) {
  const source = normalizeSplitMarkdownListMarkers(text);
  if (!source) return "";
  const openFencePreview = renderStreamingOpenFencePreview(source);
  if (openFencePreview) return `<div class="chat-live-markdown chat-live-preview">${openFencePreview}</div>`;
  if (streamingMarkdownLiveCanUseBlockRenderer(source)) {
    try {
      return `<div class="chat-live-markdown chat-live-preview">${markdownToHtml(source)}</div>`;
    } catch (error) {}
  }
  try {
    let rendered = renderMarkdownInline(source);
    if ((source.includes("`") && !/<code>/.test(rendered)) || (source.includes("**") && !/<strong>/.test(rendered))) {
      rendered = renderStreamingInlineFallback(source);
    }
    return `<div class="chat-live-markdown chat-live-preview">${rendered}</div>`;
  } catch (error) {
    return `<div class="chat-live-markdown chat-live-preview">${renderStreamingInlineFallback(source) || renderPlainChatText(source)}</div>`;
  }
}
function highlightMarkdownCode(code, lang = "") {
  return escapeHtml(code);
}
function isInternalMarkdownLink(url) {
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.origin === window.location.origin;
  } catch (e) {
    return false;
  }
}
function splitMarkdownTableRow(line) {
  let text = String(line || "").trim();
  if (text.startsWith("|")) text = text.slice(1);
  if (text.endsWith("|")) text = text.slice(0, -1);
  const cells = [];
  let current = "";
  let escaped = false;
  for (const char of text) {
    if (escaped) {
      current += char;
      escaped = false;
      continue;
    }
    if (char === "\\") {
      escaped = true;
      continue;
    }
    if (char === "|") {
      cells.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  if (escaped) current += "\\";
  cells.push(current.trim());
  return cells;
}
function markdownTableAlignments(separatorLine) {
  return splitMarkdownTableRow(separatorLine).map((cell) => {
    const text = String(cell || "").trim();
    if (/^:-{3,}:$/.test(text)) return "center";
    if (/^-{3,}:$/.test(text)) return "right";
    return "";
  });
}
function markdownCellAttrs(alignments, index) {
  const align = alignments[index] || "";
  return align ? ` style="text-align:${align}"` : "";
}
function normalizeReferenceKey(value) {
  return String(value || "").trim().replace(/\s+/g, " ").toLowerCase();
}
function extractMarkdownReferences(lines) {
  const references = {};
  const footnotes = {};
  const body = [];
  (lines || []).forEach((line) => {
    const footnoteMatch = String(line || "").match(/^\s{0,3}\[\^([^\]]+)\]:\s*(.*)$/);
    if (footnoteMatch) {
      footnotes[normalizeReferenceKey(footnoteMatch[1])] = footnoteMatch[2] || "";
      return;
    }
    const match = String(line || "").match(/^\s{0,3}\[([^\]]+)\]:\s+(\S+)(?:\s+["'(]([^"')]+)["')])?\s*$/);
    if (match) {
      references[normalizeReferenceKey(match[1])] = { url: match[2], title: match[3] || "" };
      return;
    }
    body.push(line);
  });
  return { references, footnotes, lines: body };
}
function clubRenderMermaidSvgLabel(text, x, y, className = "") {
  return `<text x="${x}" y="${y}" class="${className}">${escapeHtml(text)}</text>`;
}
function clubWrapMermaidTitle(text, maxChars = 38) {
  const words = String(text || "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return ["Mermaid"];
  const lines = [];
  let current = words.shift();
  words.forEach((word) => {
    if ((current + " " + word).length <= maxChars) {
      current += " " + word;
    } else {
      lines.push(current);
      current = word;
    }
  });
  if (current) lines.push(current);
  return lines.slice(0, 3);
}
function clubRenderMermaidTitle(text, x = 18, y = 28, maxChars = 38, className = "chat-mermaid-label") {
  const lines = clubWrapMermaidTitle(text, maxChars);
  if (lines.length <= 1) {
    return `<text x="${x}" y="${y}" class="${className}" style="text-anchor:start">${escapeHtml(lines[0] || "")}</text>`;
  }
  return `<text x="${x}" y="${y}" class="${className}" style="text-anchor:start">${lines.map((line, index) => `<tspan x="${x}" dy="${index === 0 ? 0 : 16}">${escapeHtml(line)}</tspan>`).join("")}</text>`;
}
function clubMermaidTitleHeight(text, maxChars = 38) {
  return clubWrapMermaidTitle(text, maxChars).length * 16;
}
function clubRenderMermaidGraph(source) {
  const lines = String(source || "").split("\n").map((line) => line.trim()).filter(Boolean);
  const nodes = new Map();
  const edges = [];
  function parseEndpoint(raw) {
    const match = String(raw || "").trim().match(/^([A-Za-z0-9_]+)(?:\[(.*?)\]|\((.*?)\)|\{(.*?)\})?$/);
    if (!match) return { id: String(raw || "").trim(), label: String(raw || "").trim(), shape: "rect" };
    return {
      id: match[1],
      label: match[2] || match[3] || match[4] || match[1],
      shape: match[2] !== undefined ? "rect" : match[3] !== undefined ? "round" : match[4] !== undefined ? "diamond" : "rect",
    };
  }
  lines.slice(1).forEach((line) => {
    const match = line.match(/^(.*?)\s*(--\s*([^>-][^-]*?)\s*-->|-->|==>|-.->|->)\s*(.*?)$/);
    if (!match) return;
    const from = parseEndpoint(match[1]);
    const to = parseEndpoint(match[4]);
    if (!nodes.has(from.id)) nodes.set(from.id, from);
    if (!nodes.has(to.id)) nodes.set(to.id, to);
    edges.push({ from: from.id, to: to.id, label: String(match[3] || "").trim() });
  });
  const levels = new Map();
  const depth = new Map();
  edges.forEach(({ from, to }) => {
    const next = (depth.get(from) || 0) + 1;
    if (!depth.has(to) || depth.get(to) < next) depth.set(to, next);
    if (!depth.has(from)) depth.set(from, 0);
  });
  Array.from(nodes.values()).forEach((node) => {
    const level = depth.get(node.id) || 0;
    if (!levels.has(level)) levels.set(level, []);
    levels.get(level).push(node);
  });
  const width = 720;
  const height = Math.max(180, 120 * Math.max(1, levels.size));
  const boxWidth = 150;
  const boxHeight = 48;
  const positions = new Map();
  Array.from(levels.entries()).forEach(([level, items]) => {
    const gap = width / (items.length + 1);
    items.forEach((node, idx) => positions.set(node.id, { x: gap * (idx + 1), y: 48 + level * 118 }));
  });
  const defs = `<defs><marker id="chatMermaidArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8fd8ff" /></marker></defs>`;
  const edgeSvg = edges.map(({ from, to, label }) => {
    const a = positions.get(from);
    const b = positions.get(to);
    if (!a || !b) return "";
    const midY = (a.y + b.y) / 2;
    return `<path d="M ${a.x} ${a.y + boxHeight / 2} C ${a.x} ${midY}, ${b.x} ${midY}, ${b.x} ${b.y - boxHeight / 2}" class="chat-mermaid-edge" marker-end="url(#chatMermaidArrow)" />${label ? clubRenderMermaidSvgLabel(label, (a.x + b.x) / 2, midY - 6, "chat-mermaid-edge-label") : ""}`;
  }).join("");
  const nodeSvg = Array.from(nodes.values()).map((node) => {
    const pos = positions.get(node.id);
    if (!pos) return "";
    if (node.shape === "diamond") {
      const points = `${pos.x},${pos.y - 34} ${pos.x + 72},${pos.y} ${pos.x},${pos.y + 34} ${pos.x - 72},${pos.y}`;
      return `<polygon points="${points}" class="chat-mermaid-node" />${clubRenderMermaidSvgLabel(node.label, pos.x, pos.y + 5, "chat-mermaid-label")}`;
    }
    const rx = node.shape === "round" ? 24 : 12;
    return `<rect x="${pos.x - boxWidth / 2}" y="${pos.y - boxHeight / 2}" width="${boxWidth}" height="${boxHeight}" rx="${rx}" ry="${rx}" class="chat-mermaid-node" />${clubRenderMermaidSvgLabel(node.label, pos.x, pos.y + 5, "chat-mermaid-label")}`;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" class="chat-mermaid-svg" role="img" aria-label="Mermaid flowchart">${defs}${edgeSvg}${nodeSvg}</svg>`;
}
function clubRenderMermaidSequence(source) {
  const lines = String(source || "").split("\n").map((line) => line.trim()).filter(Boolean);
  const participants = [];
  const messages = [];
  lines.slice(1).forEach((line) => {
    const participantMatch = line.match(/^participant\s+(.+)$/);
    if (participantMatch) {
      const name = participantMatch[1].trim();
      if (!participants.includes(name)) participants.push(name);
      return;
    }
    const messageMatch = line.match(/^(.+?)-+>>(.+?):\s*(.+)$/);
    if (messageMatch) {
      const from = messageMatch[1].trim();
      const to = messageMatch[2].trim();
      const label = messageMatch[3].trim();
      if (!participants.includes(from)) participants.push(from);
      if (!participants.includes(to)) participants.push(to);
      messages.push({ from, to, label });
    }
  });
  const width = Math.max(520, participants.length * 180);
  const headerHeight = 56;
  const rowHeight = 52;
  const height = headerHeight + messages.length * rowHeight + 42;
  const laneGap = width / Math.max(2, participants.length + 1);
  const xMap = new Map(participants.map((name, index) => [name, laneGap * (index + 1)]));
  const defs = `<defs><marker id="chatMermaidSeqArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8fd8ff" /></marker></defs>`;
  const lanes = participants.map((name) => {
    const x = xMap.get(name);
    return `<rect x="${x - 56}" y="14" width="112" height="28" rx="10" ry="10" class="chat-mermaid-node" />${clubRenderMermaidSvgLabel(name, x, 33, "chat-mermaid-label")}<line x1="${x}" y1="${headerHeight}" x2="${x}" y2="${height - 18}" class="chat-mermaid-lifeline" />`;
  }).join("");
  const arrows = messages.map((message, index) => {
    const y = headerHeight + 28 + index * rowHeight;
    const x1 = xMap.get(message.from);
    const x2 = xMap.get(message.to);
    return `<line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" class="chat-mermaid-edge" marker-end="url(#chatMermaidSeqArrow)" />${clubRenderMermaidSvgLabel(message.label, (x1 + x2) / 2, y - 10, "chat-mermaid-edge-label")}`;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" class="chat-mermaid-svg" role="img" aria-label="Mermaid sequence diagram">${defs}${lanes}${arrows}</svg>`;
}
function clubRenderMermaidClass(source) {
  const lines = String(source || "").split("\n").map((line) => line.trim()).filter(Boolean);
  const classes = new Map();
  const links = [];
  function ensureClass(name) {
    if (!classes.has(name)) classes.set(name, { name, members: [] });
    return classes.get(name);
  }
  let currentClass = null;
  lines.slice(1).forEach((line) => {
    const linkMatch = line.match(/^([A-Za-z0-9_]+)\s+<\|--\s+([A-Za-z0-9_]+)$/);
    if (linkMatch) {
      ensureClass(linkMatch[1]);
      ensureClass(linkMatch[2]);
      links.push({ from: linkMatch[1], to: linkMatch[2] });
      return;
    }
    const classStart = line.match(/^class\s+([A-Za-z0-9_]+)\s*\{$/);
    if (classStart) {
      currentClass = ensureClass(classStart[1]);
      return;
    }
    if (line === "}") {
      currentClass = null;
      return;
    }
    const memberMatch = line.match(/^([A-Za-z0-9_]+)\s*:\s*(.+)$/);
    if (memberMatch) {
      ensureClass(memberMatch[1]).members.push(memberMatch[2]);
      return;
    }
    if (currentClass) currentClass.members.push(line);
  });
  const rootName = links[0]?.from || Array.from(classes.keys())[0] || "Class";
  const children = links.filter((link) => link.from === rootName).map((link) => link.to);
  const ordered = [rootName, ...children, ...Array.from(classes.keys()).filter((name) => name !== rootName && !children.includes(name))];
  const width = Math.max(620, ordered.length * 190);
  const height = children.length ? 360 : 220;
  const positions = new Map();
  ordered.forEach((name) => {
    const isRoot = name === rootName;
    const idx = Math.max(0, children.indexOf(name));
    positions.set(name, {
      x: isRoot ? width / 2 : width / (Math.max(1, children.length) + 1) * (idx + 1),
      y: isRoot ? 70 : 240,
    });
  });
  const defs = `<defs><marker id="chatMermaidClassArrow" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="10" markerHeight="10" orient="auto"><path d="M 0 6 L 10 0 L 10 12 z" fill="none" stroke="#8fd8ff" stroke-width="1.4" /></marker></defs>`;
  const linkSvg = links.map((link) => {
    const from = positions.get(link.from);
    const to = positions.get(link.to);
    if (!from || !to) return "";
    return `<line x1="${to.x}" y1="${to.y - 60}" x2="${from.x}" y2="${from.y + 46}" class="chat-mermaid-edge" marker-end="url(#chatMermaidClassArrow)" />`;
  }).join("");
  const classSvg = ordered.map((name) => {
    const klass = classes.get(name);
    const pos = positions.get(name);
    if (!klass || !pos) return "";
    const bodyLines = klass.members.length ? klass.members : [];
    const lineHeight = 18;
    const cardHeight = 44 + Math.max(1, bodyLines.length) * lineHeight;
    const top = pos.y - cardHeight / 2;
    return `<g><rect x="${pos.x - 86}" y="${top}" width="172" height="${cardHeight}" rx="12" ry="12" class="chat-mermaid-node" /><line x1="${pos.x - 86}" y1="${top + 34}" x2="${pos.x + 86}" y2="${top + 34}" class="chat-mermaid-divider" />${clubRenderMermaidSvgLabel(klass.name, pos.x, top + 22, "chat-mermaid-label")}${bodyLines.map((line, index) => clubRenderMermaidSvgLabel(line, pos.x - 74, top + 54 + index * lineHeight, "chat-mermaid-classline")).join("")}</g>`;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" class="chat-mermaid-svg" role="img" aria-label="Mermaid class diagram">${defs}${linkSvg}${classSvg}</svg>`;
}
function clubRenderMermaidState(source) {
  const lines = String(source || "").split("\n").map((line) => line.trim()).filter(Boolean);
  const nodes = new Map();
  const edges = [];
  const styles = {};
  const START_NODE_ID = "__state_start__";
  const END_NODE_ID = "__state_end__";
  function normalizeStateEndpoint(raw, role) {
    const value = String(raw || "").trim();
    if (value === "[*]") return role === "from" ? START_NODE_ID : END_NODE_ID;
    return value;
  }
  lines.slice(1).forEach((line) => {
    const styleMatch = line.match(/^style\s+([^\s]+)\s+(.+)$/);
    if (styleMatch) {
      styles[styleMatch[1]] = styleMatch[2];
      return;
    }
    const edgeMatch = line.match(/^(.+?)\s*-->\s*([^:]+?)(?::\s*(.+))?$/);
    if (edgeMatch) {
      const from = normalizeStateEndpoint(edgeMatch[1], "from");
      const to = normalizeStateEndpoint(edgeMatch[2], "to");
      if (!nodes.has(from))
        nodes.set(from, {
          id: from,
          label: from === START_NODE_ID || from === END_NODE_ID ? "[*]" : from,
          kind: from === START_NODE_ID || from === END_NODE_ID ? "terminal" : "state",
        });
      if (!nodes.has(to))
        nodes.set(to, {
          id: to,
          label: to === START_NODE_ID || to === END_NODE_ID ? "[*]" : to,
          kind: to === START_NODE_ID || to === END_NODE_ID ? "terminal" : "state",
        });
      edges.push({ from, to, label: String(edgeMatch[3] || "").trim() });
    }
  });
  const ordered = Array.from(nodes.values());
  const incoming = new Map();
  const outgoing = new Map();
  ordered.forEach((node) => {
    incoming.set(node.id, []);
    outgoing.set(node.id, []);
  });
  edges.forEach((edge) => {
    outgoing.get(edge.from)?.push(edge.to);
    incoming.get(edge.to)?.push(edge.from);
  });
  const depth = new Map();
  const queue = [START_NODE_ID];
  depth.set(START_NODE_ID, 0);
  while (queue.length) {
    const current = queue.shift();
    const currentDepth = depth.get(current) || 0;
    (outgoing.get(current) || []).forEach((next) => {
      if (depth.has(next)) return;
      depth.set(next, currentDepth + 1);
      queue.push(next);
    });
  }
  ordered.forEach((node) => {
    if (!depth.has(node.id)) depth.set(node.id, node.id === START_NODE_ID ? 0 : 1);
  });
  const levels = new Map();
  ordered.forEach((node) => {
    const level = depth.get(node.id) || 0;
    if (!levels.has(level)) levels.set(level, []);
    levels.get(level).push(node);
  });
  const maxLevel = Math.max(...Array.from(levels.keys()));
  const columnWidth = 190;
  const leftPad = 80;
  const topPad = 84;
  const laneHeight = 96;
  const width = Math.max(620, leftPad * 2 + (maxLevel + 1) * columnWidth);
  const height = Math.max(
    240,
    topPad + Math.max(1, ...Array.from(levels.values()).map((items) => items.length)) * laneHeight + 96,
  );
  const positions = new Map();
  Array.from(levels.entries()).forEach(([level, items]) => {
    const x = leftPad + level * columnWidth;
    const totalColumnHeight = Math.max(1, items.length - 1) * laneHeight;
    const startY = topPad + (height - topPad - 72 - totalColumnHeight) / 2;
    items.forEach((node, index) => {
      let y = startY + index * laneHeight;
      if (node.id === START_NODE_ID) y = topPad;
      if (node.id === END_NODE_ID) y = height - 64;
      positions.set(node.id, { x, y });
    });
  });
  const defs = `<defs><marker id="chatMermaidStateArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8fd8ff" /></marker></defs>`;
  const loopbackCounts = new Map();
  const edgeSvg = edges.map((edge) => {
    const from = positions.get(edge.from);
    const to = positions.get(edge.to);
    if (!from || !to) return "";
    const fromDepth = depth.get(edge.from) || 0;
    const toDepth = depth.get(edge.to) || 0;
    if (toDepth > fromDepth) {
      const startX = edge.from === START_NODE_ID ? from.x + 12 : from.x + 58;
      const startY = from.y;
      const endX = edge.to === END_NODE_ID ? to.x - 12 : to.x - 58;
      const endY = to.y;
      const midX = (startX + endX) / 2;
      return `<path d="M ${startX} ${startY} C ${midX} ${startY}, ${midX} ${endY}, ${endX} ${endY}" class="chat-mermaid-edge" marker-end="url(#chatMermaidStateArrow)" />${edge.label ? clubRenderMermaidSvgLabel(edge.label, midX, Math.min(startY, endY) - 10, "chat-mermaid-edge-label") : ""}`;
    }
    const loopKey = `${edge.from}->${edge.to}`;
    const loopIndex = (loopbackCounts.get(loopKey) || 0) + 1;
    loopbackCounts.set(loopKey, loopIndex);
    const laneOffset = 44 + (loopIndex - 1) * 28;
    const startX = edge.from === START_NODE_ID ? from.x : from.x - 58;
    const startY = edge.from === START_NODE_ID ? from.y - 12 : from.y - 22;
    const endX = edge.to === END_NODE_ID ? to.x : to.x + 58;
    const endY = edge.to === END_NODE_ID ? to.y - 12 : to.y - 22;
    const topY = Math.max(26, Math.min(startY, endY) - laneOffset);
    const midX = (startX + endX) / 2;
    return `<path d="M ${startX} ${startY} C ${startX - 40} ${topY}, ${endX + 40} ${topY}, ${endX} ${endY}" class="chat-mermaid-edge" marker-end="url(#chatMermaidStateArrow)" />${edge.label ? clubRenderMermaidSvgLabel(edge.label, midX, topY - 8, "chat-mermaid-edge-label") : ""}`;
  }).join("");
  const nodeSvg = ordered.map((node) => {
    const pos = positions.get(node.id);
    const style = styles[node.id] || "";
    const fill = /fill:([^,]+)/.exec(style)?.[1]?.trim() || "";
    const stroke = /stroke:([^,]+)/.exec(style)?.[1]?.trim() || "";
    if (node.kind === "terminal") return `<circle cx="${pos.x}" cy="${pos.y}" r="12" class="chat-mermaid-node" style="${fill ? `fill:${fill};` : ""}${stroke ? `stroke:${stroke};` : ""}" />`;
    return `<rect x="${pos.x - 58}" y="${pos.y - 20}" width="116" height="40" rx="12" ry="12" class="chat-mermaid-node" style="${fill ? `fill:${fill};` : ""}${stroke ? `stroke:${stroke};` : ""}" />${clubRenderMermaidSvgLabel(node.label, pos.x, pos.y + 5, "chat-mermaid-label")}`;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" class="chat-mermaid-svg" role="img" aria-label="Mermaid state diagram">${defs}${edgeSvg}${nodeSvg}</svg>`;
}
function clubParseMermaidDate(text) {
  const value = String(text || "").trim();
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  return Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}
function clubMermaidDateDiffDays(startUtc, endUtc) {
  const DAY_MS = 24 * 60 * 60 * 1000;
  return Math.max(1, Math.round((endUtc - startUtc) / DAY_MS) + 1);
}
function clubParseMermaidDurationDays(text) {
  const value = String(text || "").trim();
  const match = value.match(/^(\d+)([dhmw])$/i);
  if (!match) return Math.max(1, Number(value) || 1);
  const amount = Number(match[1] || 0);
  const unit = String(match[2] || "").toLowerCase();
  if (unit === "w") return amount * 7;
  if (unit === "m") return Math.max(1, amount);
  if (unit === "h") return Math.max(1, Math.ceil(amount / 24));
  return Math.max(1, amount);
}
function clubRenderMermaidGantt(source) {
  const lines = String(source || "").split("\n").map((line) => line.trim()).filter(Boolean);
  let title = "Gantt";
  let dateFormat = "YYYY-MM-DD";
  const rows = [];
  let section = "";
  let fallbackStartDay = 0;
  lines.slice(1).forEach((line) => {
    if (/^title\s+/i.test(line)) {
      title = line.replace(/^title\s+/i, "").trim();
      return;
    }
    if (/^dateFormat\s+/i.test(line)) {
      dateFormat = line.replace(/^dateFormat\s+/i, "").trim() || dateFormat;
      return;
    }
    if (/^section\s+/i.test(line)) {
      section = line.replace(/^section\s+/i, "").trim();
      return;
    }
    const taskMatch = line.match(/^(.+?)\s*:\s*(.+)$/);
    if (!taskMatch) return;
    const label = taskMatch[1].trim();
    const tokens = taskMatch[2].split(",").map((part) => part.trim()).filter(Boolean);
    const state = /^(done|active|crit|milestone)$/i.test(tokens[0] || "") ? tokens.shift() || "" : "";
    const dateTokenIndex = tokens.findIndex((token) => clubParseMermaidDate(token) !== null);
    const startUtc = dateTokenIndex >= 0 ? clubParseMermaidDate(tokens[dateTokenIndex]) : null;
    let startDay = fallbackStartDay;
    let durationDays = 1;
    if (startUtc !== null) {
      const nextToken = tokens[dateTokenIndex + 1] || "";
      const nextUtc = clubParseMermaidDate(nextToken);
      durationDays = nextUtc !== null
        ? clubMermaidDateDiffDays(startUtc, nextUtc)
        : clubParseMermaidDurationDays(nextToken);
      rows.push({ section, label, state, startUtc, durationDays });
    } else {
      durationDays = clubParseMermaidDurationDays(tokens[tokens.length - 1]);
      rows.push({ section, label, state, startDay, durationDays });
    }
    fallbackStartDay = Math.max(fallbackStartDay, startDay + durationDays);
  });
  const datedStarts = rows.filter((row) => row.startUtc !== null && row.startUtc !== undefined).map((row) => row.startUtc);
  const minUtc = datedStarts.length ? Math.min(...datedStarts) : null;
  rows.forEach((row) => {
    if (row.startUtc !== null && row.startUtc !== undefined && minUtc !== null) {
      row.startDay = Math.round((row.startUtc - minUtc) / (24 * 60 * 60 * 1000));
    }
  });
  const width = 980;
  const titleHeight = clubMermaidTitleHeight(title, 52);
  const headerHeight = titleHeight + 58;
  const labelColumnWidth = Math.max(190, Math.min(330, ...rows.map((row) => 64 + row.label.length * 7)));
  const chartLeft = labelColumnWidth + 46;
  const totalDays = Math.max(1, ...rows.map((row) => (row.startDay || 0) + Math.max(1, row.durationDays || 1)));
  const dayWidth = 28;
  const chartRight = chartLeft + totalDays * dayWidth;
  const svgWidth = Math.max(width, chartRight + 26);
  const pxPerDay = dayWidth;
  const rowHeight = 44;
  const barHeight = 20;
  const sectionGap = 18;
  let currentY = headerHeight;
  let lastSection = "";
  const rowSvg = [];
  rows.forEach((row) => {
    if (row.section && row.section !== lastSection) {
      rowSvg.push(`<text x="18" y="${currentY - 10}" class="chat-mermaid-classline">${escapeHtml(row.section)}</text>`);
      currentY += sectionGap;
      lastSection = row.section;
    }
    const y = currentY;
    const barX = chartLeft + (row.startDay || 0) * pxPerDay;
    const barWidth = Math.max(20, Math.max(1, row.durationDays || 1) * pxPerDay - 6);
    const fill = /done/i.test(row.state) ? "#2fc46b" : /active/i.test(row.state) ? "#72c7ff" : /crit/i.test(row.state) ? "#ff8a2a" : "#59728c";
    rowSvg.push(`<text x="${labelColumnWidth}" y="${y + 5}" class="chat-mermaid-classline" text-anchor="end">${escapeHtml(row.label)}</text>`);
    rowSvg.push(`<line x1="${chartLeft}" y1="${y + barHeight / 2}" x2="${chartRight}" y2="${y + barHeight / 2}" class="chat-mermaid-lifeline" />`);
    rowSvg.push(`<rect x="${barX}" y="${y - barHeight / 2}" width="${barWidth}" height="${barHeight}" rx="10" ry="10" fill="${fill}" opacity="0.95" />`);
    currentY += rowHeight;
  });
  const height = Math.max(140, currentY + 18);
  const axisSvg = Array.from({ length: totalDays + 1 }, (_, index) => {
    const x = chartLeft + index * pxPerDay;
    return `<line x1="${x}" y1="${headerHeight - 18}" x2="${x}" y2="${height - 18}" class="chat-mermaid-divider" opacity="0.18" />`;
  }).join("");
  const axisLabels = Array.from({ length: totalDays }, (_, index) => {
    const x = chartLeft + index * pxPerDay + pxPerDay / 2;
    return `<text x="${x}" y="${headerHeight - 26}" class="chat-mermaid-classline" text-anchor="middle">${index + 1}</text>`;
  }).join("");
  return `<svg viewBox="0 0 ${svgWidth} ${height}" class="chat-mermaid-svg" role="img" aria-label="Mermaid gantt chart">${clubRenderMermaidTitle(title, 18, 28, 52)}<text x="18" y="${titleHeight + 42}" class="chat-mermaid-classline">${escapeHtml(dateFormat)}</text>${axisSvg}${axisLabels}${rowSvg.join("")}</svg>`;
}
function clubRenderMermaidPie(source) {
  const lines = String(source || "").split("\n").map((line) => line.trim()).filter(Boolean);
  let title = "Pie";
  const slices = [];
  lines.slice(1).forEach((line) => {
    if (/^title\s+/i.test(line)) {
      title = line.replace(/^title\s+/i, "").trim();
      return;
    }
    const match = line.match(/^"?(.+?)"?\s*:\s*([0-9.]+)$/);
    if (match) slices.push({ label: match[1].trim(), value: Number(match[2]) || 0 });
  });
  const total = Math.max(1, slices.reduce((sum, slice) => sum + slice.value, 0));
  const colors = ["#72c7ff", "#2fc46b", "#ffcb6b", "#ff8a2a", "#c7a2ff", "#ff7b7b"];
  const titleHeight = clubMermaidTitleHeight(title, 34);
  let angle = -Math.PI / 2;
  const cx = 160;
  const cy = 138 + titleHeight;
  const radius = 92;
  const paths = slices.map((slice, index) => {
    const sweep = (slice.value / total) * Math.PI * 2;
    const x1 = cx + radius * Math.cos(angle);
    const y1 = cy + radius * Math.sin(angle);
    angle += sweep;
    const x2 = cx + radius * Math.cos(angle);
    const y2 = cy + radius * Math.sin(angle);
    const large = sweep > Math.PI ? 1 : 0;
    return `<path d="M ${cx} ${cy} L ${x1} ${y1} A ${radius} ${radius} 0 ${large} 1 ${x2} ${y2} Z" fill="${colors[index % colors.length]}" />`;
  }).join("");
  const legendStartY = 54 + titleHeight;
  const legend = slices.map((slice, index) => `<rect x="354" y="${legendStartY + index * 26}" width="12" height="12" fill="${colors[index % colors.length]}" /><text x="374" y="${legendStartY + 10 + index * 26}" class="chat-mermaid-classline">${escapeHtml(slice.label)} (${slice.value})</text>`).join("");
  return `<svg viewBox="0 0 660 ${Math.max(340, 272 + titleHeight)}" class="chat-mermaid-svg" role="img" aria-label="Mermaid pie chart">${clubRenderMermaidTitle(title, 30, 30, 34)}${paths}${legend}</svg>`;
}
function clubRenderMermaidGitGraph(source) {
  const lines = String(source || "").split("\n").map((line) => line.trim()).filter(Boolean);
  const branches = ["main"];
  let active = "main";
  const events = [];
  lines.slice(1).forEach((line) => {
    if (line === "commit") events.push({ type: "commit", branch: active });
    else if (/^branch\s+/.test(line)) {
      active = line.replace(/^branch\s+/, "").trim();
      if (!branches.includes(active)) branches.push(active);
    } else if (/^checkout\s+/.test(line)) active = line.replace(/^checkout\s+/, "").trim();
    else if (/^merge\s+/.test(line)) events.push({ type: "merge", branch: active, from: line.replace(/^merge\s+/, "").trim() });
  });
  const width = Math.max(620, events.length * 70 + 120);
  const height = Math.max(180, branches.length * 54 + 44);
  const yMap = new Map(branches.map((name, index) => [name, 46 + index * 52]));
  const lanes = branches.map((name) => `<text x="18" y="${yMap.get(name) + 5}" class="chat-mermaid-classline">${escapeHtml(name)}</text><line x1="90" y1="${yMap.get(name)}" x2="${width - 24}" y2="${yMap.get(name)}" class="chat-mermaid-lifeline" />`).join("");
  const nodes = events.map((event, index) => {
    const x = 120 + index * 64;
    const y = yMap.get(event.branch) || 46;
    if (event.type === "merge") {
      const fy = yMap.get(event.from) || y;
      return `<line x1="${x}" y1="${fy}" x2="${x}" y2="${y}" class="chat-mermaid-edge" /><circle cx="${x}" cy="${y}" r="8" fill="#ffcb6b" stroke="#243144" stroke-width="1.4" />`;
    }
    return `<circle cx="${x}" cy="${y}" r="8" fill="#72c7ff" stroke="#243144" stroke-width="1.4" />`;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" class="chat-mermaid-svg" role="img" aria-label="Mermaid git graph">${lanes}${nodes}</svg>`;
}
function clubRenderMermaidJourney(source) {
  const lines = String(source || "").split("\n").filter((line) => String(line || "").trim());
  let title = "Journey";
  const rows = [];
  let section = "";
  lines.slice(1).forEach((line) => {
    const trimmed = line.trim();
    if (/^title\s+/i.test(trimmed)) {
      title = trimmed.replace(/^title\s+/i, "").trim();
      return;
    }
    if (/^section\s+/i.test(trimmed)) {
      section = trimmed.replace(/^section\s+/i, "").trim();
      return;
    }
    const match = trimmed.match(/^(.+?):\s*(\d+)\s*:/);
    if (match) rows.push({ section, label: match[1].trim(), score: Number(match[2]) || 0 });
  });
  const width = 700;
  const titleHeight = clubMermaidTitleHeight(title, 42);
  const rowHeight = 30;
  const height = 76 + titleHeight + rows.length * rowHeight;
  const svg = rows.map((row, index) => {
    const y = 52 + titleHeight + index * rowHeight;
    return `<text x="20" y="${y + 6}" class="chat-mermaid-classline">${escapeHtml(row.section)}</text><text x="180" y="${y + 6}" class="chat-mermaid-classline">${escapeHtml(row.label)}</text><rect x="300" y="${y - 10}" width="${row.score * 38}" height="16" rx="8" ry="8" fill="#72c7ff" /><text x="${310 + row.score * 38}" y="${y + 6}" class="chat-mermaid-classline">${row.score}</text>`;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" class="chat-mermaid-svg" role="img" aria-label="Mermaid journey diagram">${clubRenderMermaidTitle(title, 20, 28, 42)}${svg}</svg>`;
}
function clubRenderMermaidMindmap(source) {
  const lines = String(source || "").split("\n").filter((line) => String(line || "").trim());
  const items = lines.slice(1).map((line) => ({ indent: /^\s*/.exec(line)?.[0]?.length || 0, text: line.trim().replace(/^root\(\((.*?)\)\)/, "$1") }));
  const width = 760;
  const rowHeight = 34;
  const height = 50 + items.length * rowHeight;
  const svg = items.map((item, index) => {
    const y = 34 + index * rowHeight;
    const x = 80 + item.indent * 16;
    return `${index ? `<line x1="${x - 18}" y1="${y}" x2="${x}" y2="${y}" class="chat-mermaid-edge" />` : ""}<rect x="${x}" y="${y - 14}" width="${Math.max(90, item.text.length * 8)}" height="26" rx="13" ry="13" class="chat-mermaid-node" /><text x="${x + 12}" y="${y + 4}" class="chat-mermaid-classline">${escapeHtml(item.text)}</text>`;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" class="chat-mermaid-svg" role="img" aria-label="Mermaid mindmap">${svg}</svg>`;
}
function clubRenderMermaidTimeline(source) {
  const lines = String(source || "").split("\n").map((line) => line.trim()).filter(Boolean);
  let title = "Timeline";
  const entries = [];
  lines.slice(1).forEach((line) => {
    if (/^title\s+/i.test(line)) {
      title = line.replace(/^title\s+/i, "").trim();
      return;
    }
    const match = line.match(/^(.+?)\s*:\s*(.+)$/);
    if (match) entries.push({ year: match[1].trim(), label: match[2].trim() });
  });
  const width = 720;
  const titleHeight = clubMermaidTitleHeight(title, 46);
  const rowHeight = 48;
  const height = 78 + titleHeight + entries.length * rowHeight;
  const spine = `<line x1="140" y1="${50 + titleHeight}" x2="140" y2="${height - 18}" class="chat-mermaid-edge" />`;
  const svg = entries.map((entry, index) => {
    const y = 58 + titleHeight + index * rowHeight;
    return `<circle cx="140" cy="${y - 6}" r="6" fill="#72c7ff" /><text x="120" y="${y - 2}" class="chat-mermaid-classline" text-anchor="end">${escapeHtml(entry.year)}</text><text x="162" y="${y - 2}" class="chat-mermaid-classline">${escapeHtml(entry.label)}</text>`;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" class="chat-mermaid-svg" role="img" aria-label="Mermaid timeline">${clubRenderMermaidTitle(title, 20, 28, 46)}${spine}${svg}</svg>`;
}
function clubRenderMermaidQuadrant(source) {
  const lines = String(source || "").split("\n").map((line) => line.trim()).filter(Boolean);
  let title = "Quadrant";
  let xAxis = ["Low", "High"];
  let yAxis = ["Low", "High"];
  const points = [];
  const quadrants = {};
  lines.slice(1).forEach((line) => {
    if (/^title\s+/i.test(line)) title = line.replace(/^title\s+/i, "").trim();
    else if (/^x-axis\s+/i.test(line)) xAxis = line.replace(/^x-axis\s+/i, "").split("-->").map((part) => part.trim());
    else if (/^y-axis\s+/i.test(line)) yAxis = line.replace(/^y-axis\s+/i, "").split("-->").map((part) => part.trim());
    else if (/^quadrant-\d+\s+/.test(line)) quadrants[line.split(/\s+/)[0]] = line.replace(/^quadrant-\d+\s+/i, "").trim();
    else {
      const match = line.match(/^(.+?):\s*\[([0-9.]+)\s*,\s*([0-9.]+)\]$/);
      if (match) points.push({ label: match[1].trim(), x: Number(match[2]), y: Number(match[3]) });
    }
  });
  const width = 760;
  const titleHeight = clubMermaidTitleHeight(title, 42);
  const height = 480 + titleHeight;
  const left = 120;
  const top = 82 + titleHeight;
  const size = 280;
  const pointSvg = points.map((point) => {
    const x = left + point.x * size;
    const y = top + (1 - point.y) * size;
    return `<circle cx="${x}" cy="${y}" r="7" fill="#72c7ff" /><text x="${x + 10}" y="${y - 8}" class="chat-mermaid-classline">${escapeHtml(point.label)}</text>`;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" class="chat-mermaid-svg" role="img" aria-label="Mermaid quadrant chart">${clubRenderMermaidTitle(title, 20, 28, 42)}<rect x="${left}" y="${top}" width="${size}" height="${size}" fill="rgba(12,19,29,0.7)" stroke="#4f7398" stroke-width="1.4" /><line x1="${left + size / 2}" y1="${top}" x2="${left + size / 2}" y2="${top + size}" class="chat-mermaid-edge" /><line x1="${left}" y1="${top + size / 2}" x2="${left + size}" y2="${top + size / 2}" class="chat-mermaid-edge" /><text x="${left}" y="${top + size + 28}" class="chat-mermaid-classline">${escapeHtml(xAxis[0] || "Low")}</text><text x="${left + size - 20}" y="${top + size + 28}" class="chat-mermaid-classline">${escapeHtml(xAxis[1] || "High")}</text><text x="${left - 12}" y="${top + size}" class="chat-mermaid-classline" text-anchor="end">${escapeHtml(yAxis[0] || "Low")}</text><text x="${left - 12}" y="${top + 12}" class="chat-mermaid-classline" text-anchor="end">${escapeHtml(yAxis[1] || "High")}</text><text x="${left + 20}" y="${top + 24}" class="chat-mermaid-classline">${escapeHtml(quadrants["quadrant-2"] || "")}</text><text x="${left + size / 2 + 16}" y="${top + 24}" class="chat-mermaid-classline">${escapeHtml(quadrants["quadrant-1"] || "")}</text><text x="${left + 20}" y="${top + size - 12}" class="chat-mermaid-classline">${escapeHtml(quadrants["quadrant-3"] || "")}</text><text x="${left + size / 2 + 16}" y="${top + size - 12}" class="chat-mermaid-classline">${escapeHtml(quadrants["quadrant-4"] || "")}</text>${pointSvg}</svg>`;
}
async function downloadMermaidFigure(button, format = "svg") {
  const figure = button?.closest?.(".chat-mermaid-block");
  const svg = figure?.querySelector?.("svg");
  if (!svg) return;
  const serializer = new XMLSerializer();
  const markup = serializer.serializeToString(svg);
  const blob = new Blob([markup], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const title = (figure.getAttribute("data-mermaid-kind") || "diagram").replace(/[^a-z0-9_-]+/gi, "-").toLowerCase();
  if (format === "svg") {
    const link = document.createElement("a");
    link.href = url;
    link.download = `${title || "diagram"}.svg`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    return;
  }
  const image = new Image();
  image.onload = () => {
    const viewBox = svg.viewBox?.baseVal;
    const logicalWidth = Math.max(
      1,
      Math.round(viewBox?.width || svg.getBoundingClientRect().width || image.width || 1),
    );
    const logicalHeight = Math.max(
      1,
      Math.round(viewBox?.height || svg.getBoundingClientRect().height || image.height || 1),
    );
    const scale = Math.max(1, window.devicePixelRatio || 1);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(logicalWidth * scale));
    canvas.height = Math.max(1, Math.round(logicalHeight * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      URL.revokeObjectURL(url);
      return;
    }
    ctx.scale(scale, scale);
    ctx.fillStyle = "#0b0f14";
    ctx.fillRect(0, 0, logicalWidth, logicalHeight);
    ctx.drawImage(image, 0, 0, logicalWidth, logicalHeight);
    const pngUrl = canvas.toDataURL("image/png");
    const link = document.createElement("a");
    link.href = pngUrl;
    link.download = `${title || "diagram"}.png`;
    link.click();
    URL.revokeObjectURL(url);
  };
  image.src = url;
}
function renderMermaidBlock(source) {
  const lines = String(source || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const first = String(lines.find((line) => String(line || "").trim()) || "").trim();
  let svg = "";
  if (/^(graph|flowchart)\b/i.test(first)) svg = clubRenderMermaidGraph(lines.join("\n"));
  else if (/^sequenceDiagram\b/i.test(first)) svg = clubRenderMermaidSequence(lines.join("\n"));
  else if (/^classDiagram\b/i.test(first)) svg = clubRenderMermaidClass(lines.join("\n"));
  else if (/^stateDiagram-v2\b/i.test(first)) svg = clubRenderMermaidState(lines.join("\n"));
  else if (/^gantt\b/i.test(first)) svg = clubRenderMermaidGantt(lines.join("\n"));
  else if (/^pie\b/i.test(first)) svg = clubRenderMermaidPie(lines.join("\n"));
  else if (/^gitGraph\b/i.test(first)) svg = clubRenderMermaidGitGraph(lines.join("\n"));
  else if (/^journey\b/i.test(first)) svg = clubRenderMermaidJourney(lines.join("\n"));
  else if (/^mindmap\b/i.test(first)) svg = clubRenderMermaidMindmap(lines.join("\n"));
  else if (/^timeline\b/i.test(first)) svg = clubRenderMermaidTimeline(lines.join("\n"));
  else if (/^quadrantChart\b/i.test(first)) svg = clubRenderMermaidQuadrant(lines.join("\n"));
  const kind = (first.split(/\s+/)[0] || "mermaid").replace(/[^A-Za-z0-9_-]+/g, "");
  return `<figure class="chat-mermaid-block" data-mermaid-kind="${escapeHtml(kind)}"><div class="chat-mermaid-actions"><button type="button" class="chat-mermaid-action-btn" onclick="downloadMermaidFigure(this,'svg')" title="Save as SVG" aria-label="Save as SVG">${svgIcon("vector")}</button><button type="button" class="chat-mermaid-action-btn" onclick="downloadMermaidFigure(this,'png')" title="Save as PNG" aria-label="Save as PNG">${svgIcon("save")}</button></div>${svg || `<pre class="chat-code"><div class="chat-code-lang">mermaid</div><code>${escapeHtml(lines.join("\n"))}</code></pre>`}<figcaption>mermaid</figcaption></figure>`;
}
function clubReadDisplayMathBlock(lines, startIndex, openToken, closeToken) {
  const mathLines = [];
  let index = startIndex;
  const firstLine = String(lines[index] || "");
  const openAt = firstLine.indexOf(openToken);
  const sameLineClose = firstLine.indexOf(closeToken, openAt + openToken.length);
  if (sameLineClose >= 0) {
    return {
      html: renderMarkdownMathToken(firstLine.slice(openAt, sameLineClose + closeToken.length), true),
      nextIndex: index + 1,
    };
  }
  mathLines.push(firstLine.slice(openAt));
  index += 1;
  while (index < lines.length) {
    mathLines.push(String(lines[index] || ""));
    if (String(lines[index] || "").includes(closeToken)) {
      index += 1;
      break;
    }
    index += 1;
  }
  return { html: renderMarkdownMathToken(mathLines.join("\n"), true), nextIndex: index };
}
function clubReadDisplayEnvironmentBlock(lines, startIndex) {
  const line = String(lines[startIndex] || "");
  const match = line.trim().match(/^\\begin\{([A-Za-z*]+)\}/);
  if (!match) return null;
  const envName = match[1];
  const bodyLines = [line];
  let index = startIndex + 1;
  let depth = 1;
  while (index < lines.length) {
    const current = String(lines[index] || "");
    bodyLines.push(current);
    if (current.includes(`\\begin{${envName}}`)) depth += 1;
    if (current.includes(`\\end{${envName}}`)) {
      depth -= 1;
      if (depth <= 0) {
        index += 1;
        break;
      }
    }
    index += 1;
  }
  return { html: renderMarkdownMathToken(bodyLines.join("\n"), true), nextIndex: index };
}
function clubReadDetailsBlock(lines, startIndex) {
  const bodyLines = [];
  let index = startIndex;
  while (index < lines.length) {
    const current = String(lines[index] || "");
    bodyLines.push(current);
    if (/<\/details>/i.test(current)) {
      index += 1;
      break;
    }
    index += 1;
  }
  return { html: renderDetailsBlock(bodyLines.join("\n")), nextIndex: index };
}
function renderDetailsBlock(source) {
  const text = String(source || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const summaryMatch = text.match(/<summary>([\s\S]*?)<\/summary>/i);
  const summaryHtml = summaryMatch ? renderMarkdownInline(summaryMatch[1].trim()) : "Details";
  let body = text
    .replace(/^\s*<details>\s*/i, "")
    .replace(/\s*<\/details>\s*$/i, "")
    .replace(/<summary>[\s\S]*?<\/summary>/i, "")
    .trim();
  const contentHtml = body ? markdownToHtml(body) : "";
  return `<details class="chat-markdown-details"><summary>${summaryHtml}</summary>${contentHtml}</details>`;
}
function renderCalloutBlock(lines, references = {}) {
  const rawLines = Array.isArray(lines) ? lines : [];
  const first = String(rawLines[0] || "").trim();
  const match = first.match(/^\[!([A-Za-z]+)\]\s*(.*)$/);
  if (!match) return `<blockquote>${markdownToHtml(rawLines.join("\n"))}</blockquote>`;
  const kind = String(match[1] || "note").toLowerCase();
  const title = String(match[2] || kind).trim();
  const bodyLines = rawLines.slice(1);
  const body = bodyLines.join("\n").trim();
  const titleHtml = title ? `<div class="chat-callout-title">${renderMarkdownInline(title, references)}</div>` : "";
  const bodyHtml = body ? markdownToHtml(body) : "";
  return `<blockquote class="chat-callout chat-callout-${escapeHtml(kind)}">${titleHtml}${bodyHtml}</blockquote>`;
}
function renderMarkdownList(lines, startIndex, ordered, baseIndent = null, references = {}) {
  const tag = ordered ? "ol" : "ul";
  const items = [];
  let index = startIndex;
  let startNumber = null;
  while (index < lines.length) {
    const line = String(lines[index] || "");
    const match = line.match(/^(\s*)([-+*]|\d+\.)\s+(.*)$/);
    if (!match || /^\d+\.$/.test(match[2]) !== ordered) break;
    if (ordered && startNumber === null) {
      startNumber = Math.max(1, Number(String(match[2] || "").replace(/\.$/, "")) || 1);
    }
    const indent = match[1].replace(/\t/g, "    ").length;
    if (baseIndent === null) baseIndent = indent;
    if (indent < baseIndent) break;
    if (indent > baseIndent) {
      const nested = renderMarkdownList(
        lines,
        index,
        /^\d+\.$/.test(match[2]),
        indent,
        references,
      );
      if (items.length) items[items.length - 1] = items[items.length - 1].replace(/<\/li>$/, `${nested.html}</li>`);
      index = nested.index;
      continue;
    }
    const itemLines = [match[3]];
    const nestedHtml = [];
    index += 1;
    while (index < lines.length) {
      const nextLine = String(lines[index] || "");
      if (!nextLine.trim()) {
        index += 1;
        break;
      }
      const nestedMatch = nextLine.match(/^(\s*)([-+*]|\d+\.)\s+(.*)$/);
      if (nestedMatch) {
        const nestedIndent = nestedMatch[1].replace(/\t/g, "    ").length;
        if (nestedIndent > baseIndent) {
          const nested = renderMarkdownList(
            lines,
            index,
            /^\d+\.$/.test(nestedMatch[2]),
            nestedIndent,
            references,
          );
          nestedHtml.push(nested.html);
          index = nested.index;
          continue;
        }
        break;
      }
      if (/^\s{2,}\S/.test(nextLine)) {
        itemLines.push(nextLine.trim());
        index += 1;
        continue;
      }
      break;
    }
    const item = itemLines.join("\n");
    const taskMatch = item.match(/^\[([ xX-])\]\s+(.*)$/);
    if (taskMatch) {
      const checked = taskMatch[1].toLowerCase() === "x";
      const indeterminate = taskMatch[1] === "-";
      const marker = indeterminate
        ? '<span class="chat-task-checkbox chat-task-indeterminate" aria-hidden="true"></span>'
        : `<input type="checkbox" disabled${checked ? " checked" : ""} />`;
      items.push(`<li class="chat-task-item">${marker} ${renderMarkdownInline(taskMatch[2], references)}${nestedHtml.join("")}</li>`);
    } else {
      items.push(`<li>${renderMarkdownInline(item, references)}${nestedHtml.join("")}</li>`);
    }
  }
  const startAttr = ordered && startNumber && startNumber > 1 ? ` start="${startNumber}"` : "";
  return { html: `<${tag}${startAttr}>${items.join("")}</${tag}>`, index };
}
function isMarkdownBlockStart(lines, index) {
  const line = String(lines[index] || "");
  const trimmed = line.trim();
  if (!trimmed) return false;
  if (/^<details>/i.test(trimmed)) return true;
  if (/^\\\[/.test(trimmed)) return true;
  if (/^\\begin\{[A-Za-z*]+\}/.test(trimmed)) return true;
  if (/^(```|~~~)/.test(trimmed)) return true;
  if (/^\$\$\s*$/.test(trimmed)) return true;
  if (/^(#{1,6})\s+/.test(trimmed)) return true;
  if (/^([-*_]\s*){3,}$/.test(trimmed)) return true;
  if (/^>\s?/.test(trimmed)) return true;
  if (/^(\s*)([-+*]|\d+\.)\s+/.test(line)) return true;
  if (
    index + 1 < lines.length &&
    /^(\s*)(?:[*_~]{0,3})?\d+\s*$/.test(line) &&
    /^[ \t]*\.\s+\S/.test(String(lines[index + 1] || ""))
  ) {
    return true;
  }
  if (
    index + 1 < lines.length &&
    /^(\s*)(?:[*_~]{0,3})?\d+\.\s*$/.test(line) &&
    splitListMarkerBodyLineIsSafe(String(lines[index + 1] || ""))
  ) {
    return true;
  }
  if (
    index + 1 < lines.length &&
    /^(\s*)[-+*]\s*$/.test(line) &&
    splitListMarkerBodyLineIsSafe(String(lines[index + 1] || ""))
  ) {
    return true;
  }
  if (/^( {4}|\t)/.test(line)) return true;
  return (
    index + 1 < lines.length &&
    line.includes("|") &&
    String(lines[index + 1] || "").includes("|") &&
    splitMarkdownTableRow(lines[index + 1]).every((cell) => /^:?-{2,}:?$/.test(cell))
  );
}
function splitListMarkerBodyLineIsSafe(line) {
  const trimmed = String(line || "").trim();
  if (!trimmed) return false;
  if (/^(```|~~~)/.test(trimmed)) return false;
  if (/^\$\$\s*$/.test(trimmed)) return false;
  if (/^\\\[/.test(trimmed)) return false;
  if (/^\\begin\{[A-Za-z*]+\}/.test(trimmed)) return false;
  if (/^<details>/i.test(trimmed)) return false;
  if (/^(#{1,6})\s+/.test(trimmed)) return false;
  if (/^([-*_]\s*){3,}$/.test(trimmed)) return false;
  if (/^>\s?/.test(trimmed)) return false;
  if (/^\s{0,3}(?:[-+*]|\d+\.)\s+/.test(line)) return false;
  return true;
}
function normalizeSplitMarkdownListMarkers(text) {
  const source = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  if (!source || !source.includes("\n")) return source;
  const lines = source.split("\n");
  const normalized = [];
  let fence = "";
  let displayMath = false;
  let bracketMath = false;
  let mathEnv = "";
  for (let index = 0; index < lines.length; index += 1) {
    const line = String(lines[index] || "");
    const trimmed = line.trim();
    if (fence) {
      normalized.push(line);
      if (trimmed.startsWith(fence)) fence = "";
      continue;
    }
    if (bracketMath) {
      normalized.push(line);
      if (trimmed.includes("\\]")) bracketMath = false;
      continue;
    }
    if (mathEnv) {
      normalized.push(line);
      if (trimmed.includes(`\\end{${mathEnv}}`)) mathEnv = "";
      continue;
    }
    const fenceMatch = trimmed.match(/^(```|~~~)/);
    if (fenceMatch) {
      fence = fenceMatch[1];
      normalized.push(line);
      continue;
    }
    if (/^\$\$\s*$/.test(trimmed)) {
      displayMath = !displayMath;
      normalized.push(line);
      continue;
    }
    if (displayMath) {
      normalized.push(line);
      continue;
    }
    if (/^\\\[/.test(trimmed)) {
      bracketMath = !trimmed.includes("\\]");
      normalized.push(line);
      continue;
    }
    const mathEnvMatch = trimmed.match(/^\\begin\{([A-Za-z*]+)\}/);
    if (mathEnvMatch) {
      mathEnv = trimmed.includes(`\\end{${mathEnvMatch[1]}}`) ? "" : mathEnvMatch[1];
      normalized.push(line);
      continue;
    }
    const next = index + 1 < lines.length ? String(lines[index + 1] || "") : "";
    const orderedNumber = line.match(/^([ \t]{0,3})([*_~]{0,3})(\d{1,9})\s*$/);
    const orderedDotNext = next.match(/^[ \t]*\.\s+(\S[\s\S]*)$/);
    if (orderedNumber && orderedDotNext) {
      normalized.push(`${orderedNumber[1]}${orderedNumber[2]}${orderedNumber[3]}. ${orderedDotNext[1]}`);
      index += 1;
      continue;
    }
    const orderedDot = line.match(/^([ \t]{0,3})([*_~]{0,3})(\d{1,9})\.\s*$/);
    if (orderedDot && splitListMarkerBodyLineIsSafe(next)) {
      normalized.push(`${orderedDot[1]}${orderedDot[2]}${orderedDot[3]}. ${next.trimStart()}`);
      index += 1;
      continue;
    }
    const unorderedMarker = line.match(/^([ \t]{0,3})([-+*])\s*$/);
    if (unorderedMarker && splitListMarkerBodyLineIsSafe(next)) {
      normalized.push(`${unorderedMarker[1]}${unorderedMarker[2]} ${next.trimStart()}`);
      index += 1;
      continue;
    }
    normalized.push(line);
  }
  return normalized.join("\n");
}
function normalizeSoftWrappedMarkdown(text) {
  const source = normalizeSplitMarkdownListMarkers(text);
  if (!source) return "";
  const lines = source.split("\n");
  const shouldJoinInline = (current, next) => {
    const currentTrim = String(current || "").trim();
    const nextTrim = String(next || "").trim();
    if (!currentTrim || !nextTrim) return false;
    if (/^(\s*)([-+*]|\d+\.)\s+/.test(current)) return false;
    const markers = ["**", "__", "~~", "==", "`"];
    if (
      !/^(\s*)([-+*]|\d+\.)\s+/.test(current) &&
      !/^(\s*)([-+*]|\d+\.)\s+/.test(next) &&
      !/^#{1,6}\s+/.test(nextTrim)
    ) {
      markers.push("*", "_");
    }
    return markers.some((marker) => {
      const count = current.split(marker).length - 1;
      return count % 2 === 1;
    });
  };
  const shouldJoinListContinuation = (current, next) => {
    const currentTrim = String(current || "").trim();
    const nextTrim = String(next || "").trim();
    if (!/^(\s*)([-+*]|\d+\.)\s+/.test(current)) return false;
    if (!nextTrim) return false;
    if (/^(\s*)([-+*]|\d+\.)\s+/.test(next)) return false;
    if (/^#{1,6}\s+/.test(nextTrim)) return false;
    if (/^(```|~~~)/.test(nextTrim)) return false;
    if (/^\$\$\s*$/.test(nextTrim)) return false;
    if (/^>\s?/.test(nextTrim)) return false;
    return true;
  };
  const shouldJoinSplitOrderedMarker = (current, next) => {
    const currentTrim = String(current || "").trim();
    const nextTrim = String(next || "").trim();
    return /^(?:[*_~]{0,3})?\d+$/.test(currentTrim) && /^\.\s+\S+/.test(nextTrim);
  };
  const normalized = [];
  for (let index = 0; index < lines.length; index += 1) {
    let current = String(lines[index] || "");
    while (index + 1 < lines.length) {
      const next = String(lines[index + 1] || "");
      if (!next.trim()) break;
      if (
        shouldJoinInline(current, next) ||
        shouldJoinListContinuation(current, next)
      ) {
        current = `${current.replace(/\s+$/, "")} ${next.trimStart()}`;
        index += 1;
        continue;
      }
      if (shouldJoinSplitOrderedMarker(current, next)) {
        current = `${current.replace(/\s+$/, "")}${next.trimStart()}`;
        index += 1;
        continue;
      }
      break;
    }
    normalized.push(current);
  }
  return normalized.join("\n");
}
function markdownToHtml(text) {
  const source = normalizeSplitMarkdownListMarkers(text);
  if (!source) return "";
  const extracted = extractMarkdownReferences(source.split("\n"));
  const lines = extracted.lines;
  const references = extracted.references;
  const footnotes = extracted.footnotes || {};
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    const line = String(lines[index] || "");
    const trimmed = line.trim();
    if (!trimmed) {
      index += 1;
      continue;
    }
    if (/^<details>/i.test(trimmed)) {
      const rendered = clubReadDetailsBlock(lines, index);
      blocks.push(rendered.html);
      index = rendered.nextIndex;
      continue;
    }
    if (/^\\\[/.test(trimmed)) {
      const rendered = clubReadDisplayMathBlock(lines, index, "\\[", "\\]");
      blocks.push(rendered.html);
      index = rendered.nextIndex;
      continue;
    }
    if (/^\\begin\{[A-Za-z*]+\}/.test(trimmed)) {
      const rendered = clubReadDisplayEnvironmentBlock(lines, index);
      if (rendered) {
        blocks.push(rendered.html);
        index = rendered.nextIndex;
        continue;
      }
    }
    if (/^\$\$\s*$/.test(trimmed)) {
      const mathLines = [];
      index += 1;
      while (index < lines.length && !/^\$\$\s*$/.test(String(lines[index] || "").trim())) {
        mathLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push(renderMarkdownMathToken(mathLines.join("\n"), true));
      continue;
    }
    const fenceMatch = trimmed.match(/^(```|~~~)(?:\s*(.*?))?\s*$/);
    if (fenceMatch) {
      const fence = fenceMatch[1];
      const inlineTitle = String(fenceMatch[2] || "").trim();
      const rawCodeLines = [];
      index += 1;
      while (index < lines.length && !String(lines[index] || "").trim().startsWith(fence)) {
        rawCodeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      if (inlineTitle.toLowerCase() === "mermaid") {
        blocks.push(renderMermaidBlock(rawCodeLines.join("\n")));
      } else {
        const title = inlineTitle || "text";
        blocks.push(`<pre class="chat-code"><div class="chat-code-lang">${escapeHtml(title)}</div><code data-code-block="1" data-code-lang="${escapeHtml(normalizeCodeLanguageTag(title) || "text")}">${highlightMarkdownCode(rawCodeLines.join("\n"), title)}</code></pre>`);
      }
      continue;
    }
    if (/^( {4}|\t)/.test(line)) {
      const codeLines = [];
      while (index < lines.length && (/^( {4}|\t)/.test(String(lines[index] || "")) || !String(lines[index] || "").trim())) {
        codeLines.push(String(lines[index] || "").replace(/^( {4}|\t)/, ""));
        index += 1;
      }
      blocks.push(`<pre class="chat-code"><div class="chat-code-lang">text</div><code data-code-block="1" data-code-lang="text">${escapeHtml(codeLines.join("\n").replace(/\n+$/, ""))}</code></pre>`);
      continue;
    }
    if (
      index + 1 < lines.length &&
      line.includes("|") &&
      lines[index + 1].includes("|") &&
      splitMarkdownTableRow(lines[index + 1]).every((cell) => /^:?-{2,}:?$/.test(cell))
    ) {
      const headerCells = splitMarkdownTableRow(line);
      const alignments = markdownTableAlignments(lines[index + 1]);
      const rows = [];
      index += 2;
      while (index < lines.length && String(lines[index] || "").includes("|")) {
        rows.push(splitMarkdownTableRow(lines[index]));
        index += 1;
      }
      blocks.push(`<table><thead><tr>${headerCells.map((cell, cellIndex) => `<th${markdownCellAttrs(alignments, cellIndex)}>${renderMarkdownInline(cell, references)}</th>`).join("")}</tr></thead><tbody>${rows.map((cells) => `<tr>${cells.map((cell, cellIndex) => `<td${markdownCellAttrs(alignments, cellIndex)}>${renderMarkdownInline(cell, references)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
      continue;
    }
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      blocks.push(`<h${headingMatch[1].length}>${renderMarkdownInline(headingMatch[2], references)}</h${headingMatch[1].length}>`);
      index += 1;
      continue;
    }
    if (index + 1 < lines.length && /^:\s+/.test(String(lines[index + 1] || "").trim())) {
      const term = trimmed;
      const defs = [];
      index += 1;
      while (index < lines.length && /^:\s+/.test(String(lines[index] || "").trim())) {
        defs.push(String(lines[index] || "").trim().replace(/^:\s+/, ""));
        index += 1;
      }
      blocks.push(`<dl><dt>${renderMarkdownInline(term, references)}</dt>${defs.map((item) => `<dd>${renderMarkdownInline(item, references)}</dd>`).join("")}</dl>`);
      continue;
    }
    if (/^([-*_]\s*){3,}$/.test(trimmed)) {
      blocks.push("<hr />");
      index += 1;
      continue;
    }
    if (/^>\s?/.test(trimmed)) {
      const quoteLines = [];
      while (index < lines.length && /^>\s?/.test(String(lines[index] || "").trim())) {
        quoteLines.push(String(lines[index] || "").replace(/^\s*>\s?/, ""));
        index += 1;
      }
      blocks.push(renderCalloutBlock(quoteLines, references));
      continue;
    }
    if (/^(\s*)([-+*]|\d+\.)\s+/.test(line)) {
      const ordered = /^(\s*)\d+\.\s+/.test(line);
      const rendered = renderMarkdownList(lines, index, ordered, null, references);
      blocks.push(rendered.html);
      index = rendered.index;
      continue;
    }
    const paragraphLines = [];
    while (index < lines.length && String(lines[index] || "").trim()) {
      if (paragraphLines.length && isMarkdownBlockStart(lines, index)) break;
      paragraphLines.push(lines[index]);
      index += 1;
    }
    blocks.push(`<p>${renderMarkdownInline(paragraphLines.join("\n"), references)}</p>`);
  }
  const footnoteKeys = Object.keys(footnotes);
  if (footnoteKeys.length) {
    blocks.push(`<section class="chat-footnotes"><ol>${footnoteKeys.map((key) => `<li id="chat-footnote-${escapeHtml(key)}">${renderMarkdownInline(footnotes[key], references)}</li>`).join("")}</ol></section>`);
  }
  return blocks.join("");
}
function cachedMarkdownToHtml(text) {
  const source = String(text || "");
  if (!source) return "";
  const cached = chatMarkdownRenderCache.get(source);
  if (cached !== undefined) return cached;
  let rendered = "";
  try {
    rendered = markdownToHtml(source);
  } catch (error) {
    logDebugEvent("chat_markdown_render_error", {
      textLength: source.length,
      error: error?.message || String(error || ""),
    });
    rendered = `<div class="chat-plain-markdown">${renderPlainChatText(source)}</div>`;
  }
  chatMarkdownRenderCache.set(source, rendered);
  if (chatMarkdownRenderCache.size > 256) {
    const firstKey = chatMarkdownRenderCache.keys().next();
    if (!firstKey.done) chatMarkdownRenderCache.delete(firstKey.value);
  }
  return rendered;
}
function chatStreamingMarkdownState(message) {
  if (!message || typeof message !== "object") return null;
  if (!message.__clubMarkdownStream || typeof message.__clubMarkdownStream !== "object") {
    message.__clubMarkdownStream = {
      source: "",
      splitIndex: 0,
      stableHtml: "",
      liveSource: "",
      liveHtml: "",
      epoch: chatMarkdownRenderEpoch,
    };
  }
  return message.__clubMarkdownStream;
}
function chatStreamingMarkdownLineEnds(lines) {
  const ends = [];
  let cursor = 0;
  (lines || []).forEach((line, index) => {
    cursor += String(line || "").length;
    if (index < lines.length - 1) cursor += 1;
    ends.push(cursor);
  });
  return ends;
}
function chatStreamingMarkdownBlockEnd(lineEnds, indexExclusive) {
  if (!Array.isArray(lineEnds) || indexExclusive <= 0) return 0;
  return Number(lineEnds[indexExclusive - 1] || 0) || 0;
}
function readStreamingMarkdownListMarker(lines, index) {
  const line = String(lines[index] || "");
  const normal = line.match(/^(\s*)([-+*]|\d+\.)\s+(.*)$/);
  if (normal) {
    return {
      ordered: /^\d+\.$/.test(normal[2]),
      indent: normal[1].replace(/\t/g, "    ").length,
      nextIndex: index + 1,
    };
  }
  const next = index + 1 < lines.length ? String(lines[index + 1] || "") : "";
  const orderedNumber = line.match(/^(\s*)(?:[*_~]{0,3})?\d+\s*$/);
  if (orderedNumber && /^[ \t]*\.\s+\S/.test(next)) {
    return {
      ordered: true,
      indent: orderedNumber[1].replace(/\t/g, "    ").length,
      nextIndex: index + 2,
    };
  }
  const orderedDot = line.match(/^(\s*)(?:[*_~]{0,3})?\d+\.\s*$/);
  if (orderedDot && splitListMarkerBodyLineIsSafe(next)) {
    return {
      ordered: true,
      indent: orderedDot[1].replace(/\t/g, "    ").length,
      nextIndex: index + 2,
    };
  }
  const unorderedMarker = line.match(/^(\s*)([-+*])\s*$/);
  if (unorderedMarker && splitListMarkerBodyLineIsSafe(next)) {
    return {
      ordered: false,
      indent: unorderedMarker[1].replace(/\t/g, "    ").length,
      nextIndex: index + 2,
    };
  }
  return null;
}
function consumeStreamingMarkdownList(lines, startIndex, ordered, baseIndent = null) {
  let index = startIndex;
  while (index < lines.length) {
    const marker = readStreamingMarkdownListMarker(lines, index);
    if (!marker || marker.ordered !== ordered) break;
    const indent = marker.indent;
    if (baseIndent === null) baseIndent = indent;
    if (indent < baseIndent) break;
    if (indent > baseIndent) {
      index = consumeStreamingMarkdownList(
        lines,
        index,
        marker.ordered,
        indent,
      ).index;
      continue;
    }
    index = marker.nextIndex;
    while (index < lines.length) {
      const nextLine = String(lines[index] || "");
      if (!nextLine.trim()) {
        index += 1;
        break;
      }
      const nestedMatch = readStreamingMarkdownListMarker(lines, index);
      if (nestedMatch) {
        const nestedIndent = nestedMatch.indent;
        if (nestedIndent > baseIndent) {
          index = consumeStreamingMarkdownList(
            lines,
            index,
            nestedMatch.ordered,
            nestedIndent,
          ).index;
          continue;
        }
        break;
      }
      if (/^\s{2,}\S/.test(nextLine)) {
        index += 1;
        continue;
      }
      break;
    }
  }
  return { index };
}
function findChatStreamingMarkdownSoftSplit(source, minimumIndex = 0) {
  const normalized = String(source || "");
  if (!normalized) return 0;
  const floor = Math.max(0, Number(minimumIndex || 0) || 0);
  if (normalized.length - floor <= CHAT_STREAM_MARKDOWN_TAIL_SOFT_LIMIT) return floor;
  const ceiling = Math.max(
    floor,
    normalized.length - CHAT_STREAM_MARKDOWN_TAIL_SOFT_LIMIT,
  );
  const lowerBound = Math.max(
    floor,
    normalized.length - CHAT_STREAM_MARKDOWN_TAIL_HARD_LIMIT,
  );
  const separators = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " "];
  for (const separator of separators) {
    const index = normalized.lastIndexOf(separator, ceiling);
    if (index >= lowerBound) return index + separator.length;
  }
  return ceiling > lowerBound ? ceiling : floor;
}
function findChatStreamingMarkdownStableBoundary(text) {
  const source = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  if (!source) return 0;
  const lines = source.split("\n");
  const lineEnds = chatStreamingMarkdownLineEnds(lines);
  let index = 0;
  let lastStable = 0;
  let allowSoftSplit = false;
  while (index < lines.length) {
    const line = String(lines[index] || "");
    const trimmed = line.trim();
    if (!trimmed) {
      lastStable = chatStreamingMarkdownBlockEnd(lineEnds, index + 1);
      index += 1;
      continue;
    }
    if (
      /^\s{0,3}\[\^([^\]]+)\]:\s*(.*)$/.test(line) ||
      /^\s{0,3}\[([^\]]+)\]:\s+\S+(?:\s+["'(]([^"')]+)["')])?\s*$/.test(line)
    ) {
      lastStable = chatStreamingMarkdownBlockEnd(lineEnds, index + 1);
      index += 1;
      continue;
    }
    if (/^\$\$\s*$/.test(trimmed)) {
      index += 1;
      while (
        index < lines.length &&
        !/^\$\$\s*$/.test(String(lines[index] || "").trim())
      ) {
        index += 1;
      }
      if (index >= lines.length) {
        allowSoftSplit = false;
        break;
      }
      index += 1;
      lastStable = chatStreamingMarkdownBlockEnd(lineEnds, index);
      continue;
    }
    const fenceMatch = trimmed.match(/^(```|~~~)(?:\s*(.*?))?\s*$/);
    if (fenceMatch) {
      const fence = fenceMatch[1];
      index += 1;
      while (
        index < lines.length &&
        !String(lines[index] || "").trim().startsWith(fence)
      ) {
        index += 1;
      }
      if (index >= lines.length) {
        allowSoftSplit = false;
        break;
      }
      index += 1;
      lastStable = chatStreamingMarkdownBlockEnd(lineEnds, index);
      continue;
    }
    if (/^(#{1,6})\s+/.test(trimmed) || /^([-*_]\s*){3,}$/.test(trimmed)) {
      lastStable = chatStreamingMarkdownBlockEnd(lineEnds, index + 1);
      index += 1;
      continue;
    }
    if (/^( {4}|\t)/.test(line)) {
      index += 1;
      while (
        index < lines.length &&
        (/^( {4}|\t)/.test(String(lines[index] || "")) ||
          !String(lines[index] || "").trim())
      ) {
        index += 1;
      }
      if (index >= lines.length) {
        allowSoftSplit = false;
        break;
      }
      lastStable = chatStreamingMarkdownBlockEnd(lineEnds, index);
      continue;
    }
    if (
      index + 1 < lines.length &&
      line.includes("|") &&
      String(lines[index + 1] || "").includes("|") &&
      splitMarkdownTableRow(lines[index + 1]).every((cell) =>
        /^:?-{2,}:?$/.test(cell),
      )
    ) {
      index += 2;
      while (index < lines.length && String(lines[index] || "").includes("|")) {
        index += 1;
      }
      if (index >= lines.length) {
        allowSoftSplit = true;
        break;
      }
      lastStable = chatStreamingMarkdownBlockEnd(lineEnds, index);
      continue;
    }
    if (
      index + 1 < lines.length &&
      /^:\s+/.test(String(lines[index + 1] || "").trim())
    ) {
      index += 1;
      while (
        index < lines.length &&
        /^:\s+/.test(String(lines[index] || "").trim())
      ) {
        index += 1;
      }
      if (index >= lines.length) {
        allowSoftSplit = true;
        break;
      }
      lastStable = chatStreamingMarkdownBlockEnd(lineEnds, index);
      continue;
    }
    if (/^>\s?/.test(trimmed)) {
      while (
        index < lines.length &&
        /^>\s?/.test(String(lines[index] || "").trim())
      ) {
        index += 1;
      }
      if (index >= lines.length) {
        allowSoftSplit = true;
        break;
      }
      lastStable = chatStreamingMarkdownBlockEnd(lineEnds, index);
      continue;
    }
    const listMarker = readStreamingMarkdownListMarker(lines, index);
    if (listMarker) {
      index = consumeStreamingMarkdownList(
        lines,
        index,
        listMarker.ordered,
      ).index;
      if (index >= lines.length) {
        allowSoftSplit = true;
        break;
      }
      lastStable = chatStreamingMarkdownBlockEnd(lineEnds, index);
      continue;
    }
    index += 1;
    while (index < lines.length && String(lines[index] || "").trim()) {
      if (isMarkdownBlockStart(lines, index)) break;
      index += 1;
    }
    if (index >= lines.length) {
      allowSoftSplit = true;
      break;
    }
    lastStable = chatStreamingMarkdownBlockEnd(lineEnds, index);
  }
  return allowSoftSplit
    ? findChatStreamingMarkdownSoftSplit(source, lastStable)
    : lastStable;
}
function hasChatStreamingReferenceDefinition(text) {
  return /^\s{0,3}(?:\[[^\]]+\]|\[\^[^\]]+\]):\s+/m.test(String(text || ""));
}
function shouldRecomputeChatStreamingStableBoundary(state, normalized, appendedText) {
  const appended = String(appendedText || "");
  if (!state || !appended) return false;
  if (appended.includes("\n")) return true;
  if (/[`~$|>]/.test(appended)) return true;
  if (appended.length >= CHAT_STREAM_MARKDOWN_RESCAN_APPEND_THRESHOLD) return true;
  return normalized.length - Number(state.splitIndex || 0) >= CHAT_STREAM_MARKDOWN_RESCAN_TAIL_THRESHOLD;
}
function resetChatStreamingMarkdownState(message, source) {
  const state = chatStreamingMarkdownState(message);
  if (!state) return null;
  const splitIndex = findChatStreamingMarkdownStableBoundary(source);
  const stableSource = source.slice(0, splitIndex);
  const liveSource = source.slice(splitIndex);
  state.source = source;
  state.splitIndex = splitIndex;
  state.stableSource = stableSource;
  state.stableHtml = stableSource ? cachedMarkdownToHtml(stableSource) : "";
  state.appendedStableHtml = state.stableHtml;
  state.stableReset = true;
  state.liveSource = liveSource;
  state.liveHtml = renderStreamingMarkdownLiveHtml(liveSource);
  state.epoch = chatMarkdownRenderEpoch;
  return state;
}
function getChatStreamingMarkdownRenderState(message, source) {
  const normalized = String(source || "");
  const state = chatStreamingMarkdownState(message);
  if (!state) {
    return {
      stableHtml: normalized ? cachedMarkdownToHtml(normalized) : "",
      liveHtml: "",
    };
  }
  if (!normalized) {
    state.source = "";
    state.splitIndex = 0;
    state.stableSource = "";
    state.stableHtml = "";
    state.appendedStableHtml = "";
    state.stableReset = true;
    state.liveSource = "";
    state.liveHtml = "";
    state.epoch = chatMarkdownRenderEpoch;
    return state;
  }
  if (
    state.epoch !== chatMarkdownRenderEpoch ||
    !state.source ||
    !normalized.startsWith(state.source) ||
    hasChatStreamingReferenceDefinition(normalized.slice(state.source.length))
  ) {
    return resetChatStreamingMarkdownState(message, normalized);
  }
  const appendedText = normalized.slice(state.source.length);
  const splitIndex = shouldRecomputeChatStreamingStableBoundary(
    state,
    normalized,
    appendedText,
  )
    ? findChatStreamingMarkdownStableBoundary(normalized)
    : Number(state.splitIndex || 0);
  if (splitIndex < state.splitIndex) {
    return resetChatStreamingMarkdownState(message, normalized);
  }
  if (splitIndex > state.splitIndex) {
    const previousSplitIndex = Number(state.splitIndex || 0);
    const appendedStableSource = normalized.slice(previousSplitIndex, splitIndex);
    state.stableSource = normalized.slice(0, splitIndex);
    state.appendedStableHtml = appendedStableSource
      ? cachedMarkdownToHtml(appendedStableSource)
      : "";
    state.stableHtml = `${state.stableHtml || ""}${state.appendedStableHtml || ""}`;
    state.stableReset = false;
  } else {
    state.appendedStableHtml = "";
    state.stableReset = false;
  }
  const liveSource = normalized.slice(splitIndex);
  state.source = normalized;
  state.splitIndex = splitIndex;
  if (state.liveSource !== liveSource) {
    state.liveSource = liveSource;
    state.liveHtml = renderStreamingMarkdownLiveHtml(liveSource);
  }
  state.epoch = chatMarkdownRenderEpoch;
  return state;
}
function renderPlainChatText(text) {
  return escapeHtml(String(text || "")).replace(/\n/g, "<br />");
}
function estimateVisibleMessageInputTokens(message) {
  let total = estimateTextTokenCount(message?.text || "");
  chatMessageAttachments(message).forEach((attachment) => {
    total += estimateAttachmentTokenCost(attachment);
  });
  return Math.max(0, total);
}
function chatTranscriptSignature() {
  const conversationId = String(chatState.activeConversationId || "");
  const visibleTurns = Math.max(
    CHAT_TRANSCRIPT_INITIAL_TURNS,
    Number(chatTranscriptVisibleTurns || 0) || CHAT_TRANSCRIPT_INITIAL_TURNS,
  );
  const parts = [conversationId, String(visibleTurns), String(chatMarkdownRenderEpoch), String(chatEditingMessageIndex)];
  (chatState.messages || []).forEach((message, index) => {
    const attachments = chatMessageAttachments(message);
    parts.push(
      [
        index,
        message?.role || "",
        String(message?.text || "").length,
        String(message?.reasoningText || message?.reasoning_content || message?.reasoning || "").length,
        attachments.length,
        message?.thinkingExpanded ? 1 : 0,
        message?.thinkingDone ? 1 : 0,
        message?.thinkingLive ? 1 : 0,
        message?.modelLabel || "",
        message?.inputTokens ?? "",
        message?.inputTokensEstimate ?? "",
        message?.inputTokensApprox ? 1 : 0,
        message?.outputTokens ?? "",
        message?.ttftSeconds ?? "",
        message?.tokensPerSecond ?? "",
      ].join(":"),
    );
  });
  return parts.join("|");
}
let chatEditingMessageIndex = -1;
function renderChatInlineMessageEditor(message = {}, messageIndex = -1) {
  return `<div class="chat-message-inline-editor"><textarea id="chatMessageEditTextarea-${Number(messageIndex)}" class="chat-message-edit-textarea" spellcheck="true" onkeydown="handleChatInlineEditKeydown(event, ${Number(messageIndex)})">${escapeHtml(String(message?.text || ""))}</textarea><div class="chat-message-edit-actions"><button type="button" class="btn green" onclick="saveChatMessageInlineEdit(${Number(messageIndex)})">Save</button><button type="button" class="btn blue" onclick="cancelChatMessageInlineEdit()">Cancel</button></div><div class="chat-settings-note">Editing plaintext here will re-render Markdown after saving.</div></div>`;
}
function focusChatInlineEditor(messageIndex) {
  requestAnimationFrame(() => {
    const textarea = $(`chatMessageEditTextarea-${Number(messageIndex)}`);
    if (!textarea) return;
    textarea.focus();
    textarea.selectionStart = textarea.selectionEnd = String(textarea.value || "").length;
  });
}
async function editChatMessage(messageIndex) {
  if (chatState.busy) {
    openClubAlertModal("Stop the active generation before editing a message.");
    return;
  }
  const index = Number(messageIndex);
  const message = (chatState.messages || [])[index];
  if (!message) return;
  chatEditingMessageIndex = chatEditingMessageIndex === index ? -1 : index;
  chatTranscriptLastSignature = "";
  renderChatTranscript(false, { reason: "edit-start" });
  if (chatEditingMessageIndex === index) focusChatInlineEditor(index);
}
function cancelChatMessageInlineEdit() {
  chatEditingMessageIndex = -1;
  chatTranscriptLastSignature = "";
  renderChatTranscript(false, { reason: "edit-cancel" });
}
function handleChatInlineEditKeydown(event, messageIndex) {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    saveChatMessageInlineEdit(messageIndex);
  } else if (event.key === "Escape") {
    event.preventDefault();
    cancelChatMessageInlineEdit();
  }
}
function saveChatMessageInlineEdit(messageIndex) {
  const index = Number(messageIndex);
  const message = (chatState.messages || [])[index];
  const textarea = $(`chatMessageEditTextarea-${index}`);
  if (!message || !textarea) {
    cancelChatMessageInlineEdit();
    return;
  }
  const nextText = String(textarea.value || "");
  chatEditingMessageIndex = -1;
  if (nextText === String(message.text || "")) {
    chatTranscriptLastSignature = "";
    renderChatTranscript(false, { reason: "edit-cancel" });
    return;
  }
  message.text = nextText;
  delete message.streamingVisibleText;
  delete message.streamingVisibleReasoningText;
  delete message.streamingVisibleActive;
  chatTranscriptLastSignature = "";
  persistChatConversationState();
  renderChatTranscript(false, { reason: "edit" });
}
async function deleteChatMessage(messageIndex) {
  if (chatState.busy) {
    openClubAlertModal("Stop the active generation before deleting a message.");
    return;
  }
  const index = Number(messageIndex);
  const message = (chatState.messages || [])[index];
  if (!message) return;
  const label = message.role === "user" ? "user" : "assistant";
  if (!(await openClubConfirmModal(`Delete this ${label} message from the conversation?`))) return;
  chatState.messages.splice(index, 1);
  if (chatEditingMessageIndex === index) chatEditingMessageIndex = -1;
  else if (chatEditingMessageIndex > index) chatEditingMessageIndex -= 1;
  chatTranscriptLastSignature = "";
  persistChatConversationState();
  renderChatTranscript(false, { reason: "delete" });
}
function applyAssistantGenerationMetrics(message = {}, metrics = {}) {
  if (!message || message.role !== "assistant" || !metrics || typeof metrics !== "object") return message;
  const metricSource =
    metrics.generation_metrics && typeof metrics.generation_metrics === "object"
      ? metrics.generation_metrics
      : metrics;
  const usage =
    metricSource.usage && typeof metricSource.usage === "object"
      ? metricSource.usage
      : metricSource;
  const outputTokens = Number(
    usage.output_tokens ??
      usage.completion_tokens ??
      metricSource.output_tokens ??
      metricSource.completion_tokens,
  );
  const ttftSeconds = Number(metricSource.ttft_s ?? metricSource.ttftSeconds);
  const tokensPerSecond = Number(metricSource.generation_tps ?? metricSource.tokensPerSecond);
  if (Number.isFinite(outputTokens) && outputTokens >= 0) message.outputTokens = outputTokens;
  if (Number.isFinite(ttftSeconds) && ttftSeconds >= 0) message.ttftSeconds = ttftSeconds;
  if (Number.isFinite(tokensPerSecond) && tokensPerSecond > 0) {
    message.tokensPerSecond = tokensPerSecond;
    message.maxTokensPerSecond = Math.max(Number(message.maxTokensPerSecond || 0), tokensPerSecond);
  }
  return message;
}
function chatMessageTimestampIso(message = {}) {
  const value = Number(message?.createdAt || message?.timestamp || 0);
  if (!Number.isFinite(value) || value <= 0) return "";
  try {
    return new Date(value).toISOString();
  } catch (error) {
    return "";
  }
}
function chatMessageGenerationDurationSeconds(message = {}) {
  const explicit = Number(message?.generationDurationSeconds);
  if (Number.isFinite(explicit) && explicit >= 0) return explicit;
  const started = Number(message?.generationStartedAt || 0);
  const finished = Number(message?.generationFinishedAt || 0);
  if (Number.isFinite(started) && started > 0 && Number.isFinite(finished) && finished >= started) {
    return (finished - started) / 1000;
  }
  return null;
}
function markAssistantGenerationFinished(message = {}) {
  if (!message || message.role !== "assistant") return message;
  const finishedAt = Date.now();
  message.generationFinishedAt = finishedAt;
  const startedAt = Number(message.generationStartedAt || message.createdAt || 0);
  if (Number.isFinite(startedAt) && startedAt > 0 && finishedAt >= startedAt) {
    message.generationDurationSeconds = (finishedAt - startedAt) / 1000;
  }
  return message;
}
async function flushChatConversationStateNow() {
  syncActiveConversationFromChatState();
  persistChatConversationState();
  try {
    await flushServerChatStateSave(currentChatStatePayload());
  } catch (error) {
    logDebugEvent("chat_state_final_flush_error", {
      error: error?.message || String(error || ""),
      activeConversationId: String(chatState.activeConversationId || ""),
    });
  }
}
function commitStudioPlanProgress(assistantIndex, options = {}) {
  syncActiveConversationFromChatState();
  if (options?.render) {
    renderChatTranscript(true, { reason: options.reason || "studio-progress" });
  } else {
    updateLiveChatMessageDom(assistantIndex, true);
  }
  persistChatConversationState();
}
function renderChatMessageMeta(message = {}, messageIndex = -1) {
  const bits = [];
  const timestamp = chatMessageTimestampIso(message);
  if (timestamp) bits.push(timestamp);
  if (message.role === "user") {
    const inputTokens = message.inputTokens ?? message.inputTokensEstimate;
    if (inputTokens !== null && inputTokens !== undefined)
      bits.push(`input: ${formatGroupedInt(inputTokens)} tokens`);
  } else if (message.role === "assistant") {
    const durationSeconds = chatMessageGenerationDurationSeconds(message);
    if (durationSeconds !== null) bits.push(`${formatElapsedSeconds(durationSeconds)} generation`);
    if (message.outputTokens !== null && message.outputTokens !== undefined)
      bits.push(`output: ${formatGroupedInt(message.outputTokens)} tokens`);
    if (message.ttftSeconds !== null && message.ttftSeconds !== undefined)
      bits.push(`TTFT: ${formatNumber(message.ttftSeconds, 3)}s`);
    if (message.tokensPerSecond !== null && message.tokensPerSecond !== undefined) {
      bits.push(`tk/s: ${formatNumber(message.tokensPerSecond, 2)}`);
    }
  }
  const actions =
    Number.isInteger(Number(messageIndex)) && Number(messageIndex) >= 0
      ? `<span class="chat-message-actions"><button type="button" class="chat-message-action" title="Edit message" aria-label="Edit message" onclick="editChatMessage(${Number(messageIndex)})">${svgIcon("edit")}</button><button type="button" class="chat-message-action danger" title="Delete message" aria-label="Delete message" onclick="deleteChatMessage(${Number(messageIndex)})">${svgIcon("delete")}</button></span>`
      : "";
  return bits.length || actions
    ? `<div class="chat-message-meta"><span class="chat-message-metrics">${escapeHtml(bits.join(" · "))}</span>${actions}</div>`
    : "";
}
function syncChatMessageMetaDom(bodyHost, message, messageIndex) {
  if (!bodyHost) return;
  const nextHtml = renderChatMessageMeta(message, messageIndex);
  const current = bodyHost.querySelector(".chat-message-meta");
  if (!nextHtml) {
    if (current) current.remove();
    return;
  }
  if (current && current.outerHTML === nextHtml) return;
  const template = document.createElement("template");
  template.innerHTML = nextHtml;
  const nextNode = template.content.firstElementChild;
  if (!nextNode) return;
  if (current) {
    current.replaceWith(nextNode);
  } else {
    bodyHost.appendChild(nextNode);
  }
}
function renderChatMessageTitle(message = {}) {
  if (message.role === "assistant") return `${message.modelLabel || "Model"}:`;
  if (message.role === "user") return "User:";
  return "System:";
}
function renderChatThinkingCardHtml(message = {}, messageIndex = -1) {
  const thinkingView =
    message.role === "assistant"
      ? chatMessageThinkingView(message)
      : { reasoningText: "", contentText: String(message?.text || "") };
  const thinkingActive = chatMessageThinkingActive(message);
  const thinkingExpanded =
    message.thinkingExpanded !== undefined
      ? !!message.thinkingExpanded
      : thinkingActive;
  const thinkingDuration = formatChatThinkingDuration(
    thinkingActive
      ? Date.now() - Number(message.thinkingStartedAt || Date.now())
      : message.thinkingDurationMs,
  );
  const thinkingLabel = String(message?.reasoningLabel || "").trim() || (thinkingActive ? "Thinking" : "Thought");
  const thinkingTitle = thinkingDuration
    ? `${thinkingLabel} for ${thinkingDuration}`
    : thinkingView.reasoningText
      ? `${thinkingLabel} for <1 second`
      : thinkingActive
        ? "Thinking"
        : thinkingLabel;
  const thinkingSubtitle = thinkingActive
    ? "Reasoning is streaming live."
    : thinkingExpanded
      ? "Tap to collapse."
      : "Tap to expand.";
  const thinkingBody = thinkingExpanded
    ? `<div class="chat-thinking-body"><div class="chat-message-markdown"><div class="chat-message-markdown-stable">${thinkingView.reasoningText ? cachedMarkdownToHtml(thinkingView.reasoningText) : ""}</div><div class="chat-message-markdown-live"></div></div></div>`
    : "";
  return thinkingView.reasoningText
    ? `<div class="chat-thinking-card ${thinkingActive ? "thinking-live" : "thinking-done"} ${thinkingExpanded ? "expanded" : "collapsed"}"><button type="button" class="chat-thinking-toggle" onclick="toggleChatReasoning(${messageIndex})" aria-expanded="${thinkingExpanded ? "true" : "false"}"><span class="chat-thinking-copy"><span class="chat-thinking-title">${escapeHtml(thinkingTitle)}</span><span class="chat-thinking-subtitle">${escapeHtml(thinkingSubtitle)}</span></span><span class="chat-thinking-chevron">${svgIcon(thinkingExpanded ? "chevron-up" : "chevron-right")}</span></button><span class="chat-thinking-textcache" hidden>${escapeHtml(thinkingView.reasoningText)}</span>${thinkingBody}</div>`
    : "";
}
function renderChatMessageMarkdownHtml(
  message = {},
  contentText = "",
  options = {},
) {
  const streaming = !!options.streaming;
  const forcePlainStreaming = streaming && chatStreamingMarkdownShouldUsePlainPreview(contentText);
  if (forcePlainStreaming) {
    return `<div class="chat-message-markdown chat-live-preview"><div class="chat-message-markdown-stable">${renderPlainChatText(contentText)}</div><div class="chat-message-markdown-live"></div></div>`;
  }
  const state = streaming
    ? getChatStreamingMarkdownRenderState(message, contentText)
    : null;
  const stableHtml = state
    ? state.stableHtml
    : contentText
      ? cachedMarkdownToHtml(contentText)
      : "";
  const previewSource = state ? state.liveSource : contentText;
  let liveHtml = state ? state.liveHtml : "";
  if (streaming && previewSource) {
    const needsInlineRecovery =
      (previewSource.includes("`") && !/<code>/.test(liveHtml)) ||
      (previewSource.includes("**") && !/<strong>/.test(liveHtml));
    if (!liveHtml || needsInlineRecovery) {
      liveHtml = renderStreamingMarkdownLiveHtml(previewSource);
    }
  }
  let hiddenInlinePreview = "";
  if (streaming && contentText) {
    try {
      hiddenInlinePreview = `<div class="chat-live-preview-cache" hidden>${renderStreamingInlineFallback(contentText)}</div>`;
    } catch (error) {
      hiddenInlinePreview = "";
    }
  }
  return `<div class="chat-message-markdown${streaming ? " chat-live-preview" : ""}"><div class="chat-message-markdown-stable">${stableHtml}</div><div class="chat-message-markdown-live">${liveHtml}</div>${hiddenInlinePreview}</div>`;
}
function renderStudioProgressMessageHtml(message = {}, contentText = "", options = {}) {
  const lines = String(contentText || "").split(/\n+/);
  const headline = String(lines[0] || "").trim();
  const subline = String(lines[1] || "").trim();
  if (!/^Generating Assets \d+\/\d+ · \d+% Done$/i.test(headline) || !/^Now:/i.test(subline)) {
    return "";
  }
  const rest = lines.slice(2).join("\n").trim();
  const restHtml = rest ? renderChatMessageMarkdownHtml(message, rest, options) : "";
  return `<div class="chat-studio-progress"><div class="chat-studio-progress-head">${escapeHtml(headline)}</div><div class="chat-studio-progress-sub">${escapeHtml(subline)}</div>${restHtml}</div>`;
}
function renderChatMessageBodyContent(message = {}, messageIndex = -1) {
  if (Number(messageIndex) === Number(chatEditingMessageIndex)) {
    return renderChatInlineMessageEditor(message, messageIndex);
  }
  const thinkingView =
    message.role === "assistant"
      ? chatMessageThinkingView(message)
      : { reasoningText: "", contentText: String(message?.text || "") };
  const thinkingCard = renderChatThinkingCardHtml(message, messageIndex);
  const attachments = chatMessageAttachments(message);
  const imageAttachments = attachments.filter(
    (attachment) => attachment?.kind === "image",
  );
  const fileAttachments = attachments.filter(
    (attachment) => attachment?.kind !== "image",
  );
  const files = fileAttachments.length
    ? `<div class="chat-message-attachments">${fileAttachments
        .map(
          (attachment) =>
            `<div class="chat-message-attachment ${chatAttachmentKindClass(attachment)}">${renderChatAttachmentPreview(attachment)}</div>`,
        )
        .join("")}</div>`
    : "";
  const images = imageAttachments.length
    ? `<div class="chat-inline-images">${imageAttachments
        .map(
          (image) =>
            `<img src="${image.url}" alt="${escapeHtml(image.name || "image")}" />`,
        )
        .join("")}</div>`
    : "";
  const meta = renderChatMessageMeta(message, messageIndex);
  const progressBody = renderStudioProgressMessageHtml(
    message,
    thinkingView.contentText || "",
    {
      streaming: message.role === "assistant" && !!chatState.busy,
    },
  );
  const markdownBody = progressBody || renderChatMessageMarkdownHtml(
    message,
    thinkingView.contentText || "",
    {
      streaming: message.role === "assistant" && !!chatState.busy,
    },
  );
  const planResults = message?.studioPlanResults ? renderStudioPlanResults(message.studioPlanResults) : "";
  const generatedMedia = planResults
    ? ""
    : message?.generatedMedia
      ? renderChatGeneratedMedia(message.generatedMedia)
      : "";
  return `${thinkingCard}${markdownBody}${planResults}${generatedMedia}${files}${images}${meta}`;
}
function syncLiveChatThinkingDom(bodyHost, message, messageIndex, markdownHost) {
  if (!bodyHost || !markdownHost) return;
  const nextHtml = renderChatThinkingCardHtml(message, messageIndex);
  const current = bodyHost.querySelector(".chat-thinking-card");
  if (!nextHtml) {
    if (current) current.remove();
    return;
  }
  if (current && current.outerHTML === nextHtml) return;
  const template = document.createElement("template");
  template.innerHTML = nextHtml;
  const nextNode = template.content.firstElementChild;
  if (!nextNode) return;
  if (current) {
    if (current.parentNode === bodyHost) current.replaceWith(nextNode);
    return;
  }
  if (markdownHost && markdownHost.parentNode === bodyHost) {
    safeInsertBefore(bodyHost, nextNode, markdownHost);
    return;
  }
  bodyHost.prepend(nextNode);
}
function updateLiveChatMessageDom(messageIndex, forceFollow = false) {
  try {
    const host = $("chatTranscript");
    if (!host) return false;
    const message = (chatState.messages || [])[messageIndex];
    if (!message) return false;
    const shell = host.querySelector(`[data-chat-message-index="${messageIndex}"]`);
    if (!shell) return false;
    const titleHost = shell.querySelector(".chat-message-title");
    const bodyHost = shell.querySelector(".chat-message-body");
    if (!bodyHost) return false;
    if (titleHost) titleHost.textContent = renderChatMessageTitle(message);
    const markdownHost = bodyHost.querySelector(".chat-message-markdown");
    const stableHost = bodyHost.querySelector(".chat-message-markdown-stable");
    const liveHost = bodyHost.querySelector(".chat-message-markdown-live");
    if (!markdownHost || !stableHost || !liveHost) {
      const bodyHtml = renderChatMessageBodyContent(message, messageIndex);
      bodyHost.innerHTML = bodyHtml;
      if (chatHtmlNeedsCodeSyntaxHighlight(bodyHtml)) {
        scheduleCodeSyntaxHighlight(bodyHost);
      }
    } else {
      syncLiveChatThinkingDom(bodyHost, message, messageIndex, markdownHost);
      const thinkingView =
        message.role === "assistant"
          ? chatMessageThinkingView(message)
          : { reasoningText: "", contentText: String(message?.text || "") };
      if (
        message.role === "assistant" &&
        chatState.busy &&
        chatStreamingMarkdownShouldUsePlainPreview(thinkingView.contentText || "")
      ) {
        const plainHtml = renderPlainChatText(thinkingView.contentText || "");
        if (stableHost.innerHTML !== plainHtml) stableHost.innerHTML = plainHtml;
        if (liveHost.innerHTML) liveHost.innerHTML = "";
        delete stableHost.dataset.stableSourceLength;
        chatTranscriptRenderLastAt = Date.now();
        chatLiveMessageRenderLastAt = chatTranscriptRenderLastAt;
        chatTranscriptLastSignature = "";
        if (forceFollow || chatTranscriptAutoFollow || chatTranscriptIsNearBottom(host)) {
          scrollChatTranscriptToBottom(host);
        }
        syncChatThinkingTicker();
        return true;
      }
      const state =
        message.role === "assistant" && chatState.busy
          ? getChatStreamingMarkdownRenderState(
              message,
              thinkingView.contentText || "",
            )
          : {
              stableHtml: thinkingView.contentText
                ? cachedMarkdownToHtml(thinkingView.contentText)
                : "",
              liveHtml: "",
      };
      const stableTargetLength = Number(state?.splitIndex || 0);
      const renderedStableLength = Number(stableHost.dataset.stableSourceLength || 0);
      let stableChanged = false;
      if (
        chatState.busy &&
        state &&
        typeof state === "object" &&
        stableTargetLength > 0
      ) {
        if (state.stableReset || renderedStableLength > stableTargetLength) {
          if (stableHost.innerHTML !== state.stableHtml) {
            stableHost.innerHTML = state.stableHtml;
            stableChanged = true;
          }
          stableHost.dataset.stableSourceLength = String(stableTargetLength);
        } else if (stableTargetLength > renderedStableLength) {
          const appendedStableHtml = String(state.appendedStableHtml || "");
          if (appendedStableHtml) {
            stableHost.insertAdjacentHTML("beforeend", appendedStableHtml);
            stableChanged = true;
          }
          stableHost.dataset.stableSourceLength = String(stableTargetLength);
        }
      } else {
        if (stableHost.innerHTML !== state.stableHtml) {
          stableHost.innerHTML = state.stableHtml;
          stableChanged = true;
        }
        delete stableHost.dataset.stableSourceLength;
      }
      if (liveHost.innerHTML !== state.liveHtml) liveHost.innerHTML = state.liveHtml;
      if (
        chatState.busy &&
        message.role === "assistant" &&
        thinkingView.contentText &&
        !String(stableHost.textContent || "").trim() &&
        !String(liveHost.textContent || "").trim()
      ) {
        liveHost.textContent = thinkingView.contentText;
      }
      const shouldHighlightStable =
        chatHtmlNeedsCodeSyntaxHighlight(state?.stableHtml || "") ||
        chatHtmlNeedsCodeSyntaxHighlight(state?.appendedStableHtml || "") ||
        chatHtmlNeedsCodeSyntaxHighlight(state?.liveHtml || "");
      if ((stableChanged || !chatState.busy) && shouldHighlightStable) {
        scheduleCodeSyntaxHighlight(stableHost);
      }
    }
    syncChatMessageMetaDom(bodyHost, message, messageIndex);
    chatTranscriptRenderLastAt = Date.now();
    chatLiveMessageRenderLastAt = chatTranscriptRenderLastAt;
    chatTranscriptLastSignature = "";
    if (forceFollow || chatTranscriptAutoFollow || chatTranscriptIsNearBottom(host)) {
      scrollChatTranscriptToBottom(host);
    }
    syncChatThinkingTicker();
    return true;
  } catch (error) {
    logDebugEvent("chat_live_dom_update_error", {
      messageIndex,
      error: error?.message || String(error || ""),
    });
    return false;
  }
}
function isSelectionActiveWithin(host) {
  const selection = window.getSelection ? window.getSelection() : null;
  if (!selection || selection.isCollapsed || selection.rangeCount < 1) return false;
  const anchor = selection.anchorNode;
  const focus = selection.focusNode;
  return !!(
    host &&
    ((anchor && host.contains(anchor)) || (focus && host.contains(focus)))
  );
}
function isChatTranscriptSelectionActive(host) {
  return isSelectionActiveWithin(host);
}
function scheduleLiveChatMessageDomUpdate(
  messageIndex,
  forceFollow = false,
  reason = "stream",
) {
  const nextIndex = Number(messageIndex);
  if (!Number.isInteger(nextIndex) || nextIndex < 0) return;
  chatLiveMessageRenderPendingIndex = nextIndex;
  chatLiveMessageRenderPendingForceFollow =
    chatLiveMessageRenderPendingForceFollow || !!forceFollow;
  chatLiveMessageRenderPendingReason =
    reason || chatLiveMessageRenderPendingReason || "stream";
  if (chatLiveMessageRenderScheduled) return;
  chatLiveMessageRenderScheduled = true;
  const flush = () => {
    chatLiveMessageRenderScheduled = false;
    const pendingIndex = chatLiveMessageRenderPendingIndex;
    const pendingFollow = !!chatLiveMessageRenderPendingForceFollow;
    const pendingReason = chatLiveMessageRenderPendingReason || "stream";
    chatLiveMessageRenderPendingIndex = -1;
    chatLiveMessageRenderPendingForceFollow = false;
    chatLiveMessageRenderPendingReason = "stream";
    const host = $("chatTranscript");
    if (host && shouldDeferChatTranscriptRender(host, pendingReason)) {
      setTimeout(
        () =>
          scheduleLiveChatMessageDomUpdate(
            pendingIndex,
            pendingFollow,
            pendingReason,
          ),
        CHAT_STREAM_RENDER_MIN_INTERVAL_MS,
      );
      return;
    }
    if (!updateLiveChatMessageDom(pendingIndex, pendingFollow)) {
      scheduleChatTranscriptRender(pendingFollow, pendingReason);
    }
  };
  const elapsed = Date.now() - Number(chatLiveMessageRenderLastAt || 0);
  const delay = Math.max(0, CHAT_STREAM_RENDER_MIN_INTERVAL_MS - elapsed);
  if (delay > 0) {
    setTimeout(flush, delay);
    return;
  }
  if (typeof window.requestAnimationFrame === "function") {
    window.requestAnimationFrame(() => flush());
    return;
  }
  setTimeout(flush, 0);
}
function shouldDeferChatTranscriptRender(host, reason = "update") {
  if (!isChatTranscriptSelectionActive(host)) return false;
  return reason !== "user";
}
function scheduleChatTranscriptRender(forceFollow = false, reason = "update") {
  chatTranscriptRenderPending = true;
  chatTranscriptRenderPendingForceFollow =
    chatTranscriptRenderPendingForceFollow || !!forceFollow;
  chatTranscriptRenderPendingReason = reason || chatTranscriptRenderPendingReason || "update";
  if (chatTranscriptRenderScheduled) return;
  chatTranscriptRenderScheduled = true;
  const flush = () => {
    chatTranscriptRenderScheduled = false;
    if (!chatTranscriptRenderPending) return;
    const force = !!chatTranscriptRenderPendingForceFollow;
    const nextReason = chatTranscriptRenderPendingReason || "update";
    chatTranscriptRenderPending = false;
    chatTranscriptRenderPendingForceFollow = false;
    chatTranscriptRenderPendingReason = "update";
    renderChatTranscript(force, { reason: nextReason });
  };
  const elapsed = Date.now() - Number(chatTranscriptRenderLastAt || 0);
  const delay =
    reason === "stream"
      ? Math.max(0, CHAT_STREAM_RENDER_MIN_INTERVAL_MS - elapsed)
      : 0;
  if (delay > 0) {
    setTimeout(flush, delay);
    return;
  }
  if (typeof window.requestAnimationFrame === "function") {
    window.requestAnimationFrame(() => flush());
    return;
  }
  setTimeout(flush, 0);
}
function renderChatTranscript(forceFollow = false, options = {}) {
  const host = $("chatTranscript");
  if (!host) return;
  const reason = String(options?.reason || "update");
  ensureChatTranscriptBehavior();
  if (chatHydrationPending() || (!chatStateHydrated && !chatConversations().length)) {
    host.innerHTML = '<div class="empty-variant-note">Loading conversations...</div><div class="chat-transcript-anchor" aria-hidden="true"></div>';
    syncChatTranscriptFollowClasses(host);
    syncChatThinkingTicker();
    return;
  }
  if (activeChatConversation()?.messagesLoaded === false) {
    host.innerHTML = '<div class="empty-variant-note">Loading conversation...</div><div class="chat-transcript-anchor" aria-hidden="true"></div>';
    syncChatTranscriptFollowClasses(host);
    syncChatThinkingTicker();
    return;
  }
  const allowAutoscroll = chatTranscriptAutoscrollEnabled();
  const shouldFollow =
    allowAutoscroll &&
    (forceFollow || chatTranscriptAutoFollow || chatTranscriptIsNearBottom(host));
  const hasLiveThinking = (chatState.messages || []).some((message) =>
    chatMessageThinkingActive(message),
  );
  const signature = hasLiveThinking ? "" : chatTranscriptSignature();
  if (!forceFollow && signature && signature === chatTranscriptLastSignature) {
    syncChatThinkingTicker();
    return;
  }
  const turns = [];
  let currentTurn = null;
  (chatState.messages || []).forEach((message, messageIndex) => {
    const entry = { message, messageIndex };
    if (message.role === "user" || !currentTurn) {
      currentTurn = { number: turns.length + 1, messages: [entry] };
      turns.push(currentTurn);
      return;
    }
    currentTurn.messages.push(entry);
  });
  const hiddenTurns = Math.max(0, turns.length - Math.max(CHAT_TRANSCRIPT_INITIAL_TURNS, Number(chatTranscriptVisibleTurns || 0) || CHAT_TRANSCRIPT_INITIAL_TURNS));
  const visibleTurns = hiddenTurns > 0 ? turns.slice(hiddenTurns) : turns;
  let nextHtml = "";
  try {
    nextHtml = `${hiddenTurns > 0 ? `<div class="chat-history-banner"><div class="chat-history-copy">${escapeHtml(`${hiddenTurns} earlier turn${hiddenTurns === 1 ? "" : "s"} hidden to keep the tab responsive.`)}</div><button type="button" class="btn blue" onclick="expandChatTranscriptWindow()">Show ${escapeHtml(String(Math.min(hiddenTurns, CHAT_TRANSCRIPT_EXPAND_STEP)))} Older</button></div>` : ""}${visibleTurns
      .map((turn) => {
        const turnMessages = turn.messages
          .map(({ message, messageIndex }) => {
            try {
          return `<div class="chat-message chat-${message.role}" data-chat-message-index="${messageIndex}"><div class="chat-message-title">${escapeHtml(renderChatMessageTitle(message))}</div><div class="chat-message-body">${renderChatMessageBodyContent(message, messageIndex)}</div></div>`;
            } catch (error) {
              logDebugEvent("chat_transcript_message_render_error", {
                messageIndex,
                role: String(message?.role || ""),
                textLength: String(message?.text || "").length,
                reasoningLength: String(
                  message?.reasoningText || message?.reasoning_content || message?.reasoning || "",
                ).length,
                error: error?.message || String(error || ""),
              });
              const title =
                message.role === "assistant"
                  ? `${message.modelLabel || "Model"}:`
                  : message.role === "user"
                    ? "User:"
                    : "System:";
              return `<div class="chat-message chat-${escapeHtml(String(message?.role || "assistant"))}"><div class="chat-message-title">${escapeHtml(title)}</div><div class="chat-message-body"><pre class="chat-code"><code>${escapeHtml(String(message?.text || ""))}</code></pre></div></div>`;
            }
          })
          .join("");
        return `<div class="chat-turn"><div class="chat-turn-divider"><span class="chat-turn-label">Turn #${turn.number}</span></div>${turnMessages}</div>`;
      })
      .join("")}`;
  } catch (error) {
    logDebugEvent("chat_transcript_render_error", {
      conversationId: String(chatState.activeConversationId || ""),
      turnCount: turns.length,
      visibleTurns: Number(chatTranscriptVisibleTurns || 0),
      error: error?.message || String(error || ""),
    });
    nextHtml = `<div class="empty-variant-note">Conversation loaded, but rich transcript rendering failed. Showing plain-text fallback.</div>${(chatState.messages || [])
      .map(
        (message) =>
          `<pre class="chat-code"><code>${escapeHtml(`[${String(message?.role || "message")}]\n${String(message?.text || "")}`)}</code></pre>`,
      )
      .join("")}`;
  }
  if (shouldDeferChatTranscriptRender(host, reason)) {
    chatTranscriptRenderPending = true;
    chatTranscriptRenderPendingForceFollow =
      chatTranscriptRenderPendingForceFollow || !!forceFollow;
    chatTranscriptRenderPendingReason = reason;
    syncChatThinkingTicker();
    return;
  }
  if (
    !forceFollow &&
    !chatState.busy &&
    isChatTranscriptSelectionActive(host) &&
    host.innerHTML === nextHtml
  ) {
    syncChatThinkingTicker();
    return;
  }
  host.innerHTML = `${nextHtml}<div class="chat-transcript-anchor" aria-hidden="true"></div>`;
  syncChatTranscriptFollowClasses(host);
  if (!chatState.busy && chatHtmlNeedsCodeSyntaxHighlight(nextHtml)) {
    scheduleCodeSyntaxHighlight(host);
  }
  chatTranscriptRenderLastAt = Date.now();
  if (signature) {
    chatTranscriptLastSignature = signature;
  } else {
    chatTranscriptLastSignature = "";
  }
  if (shouldFollow) scrollChatTranscriptToBottom(host);
  syncChatThinkingTicker();
}
function renderChatRuntimeStats() {
  const host = $("chatRuntimeStats");
  const title = $("chatStatsTitle");
  if (!host) return;
  const conversation = activeChatConversation();
  const conversationIsFresh =
    conversation &&
    (!Array.isArray(conversation.messages) || conversation.messages.length === 0) &&
    !conversationHasRuntimeMetrics(conversation);
  const runtime = conversation?.runtimeSnapshot
    ? null
    : conversationLiveRuntime(conversation) || activeChatRuntime();
  const scopedRuntime = conversationIsFresh
    ? blankChatRuntimeStats(runtime)
    : conversationScopedRuntime(runtime, conversation);
  if (scopedRuntime) scopedRuntime.__disableSessionPeaks = true;
  const nextTitle = scopedRuntime
    ? `Generation Stats (${scopedRuntime.display_name || scopedRuntime.id || "Runtime"})`
    : "Generation Stats";
  if (title && title.textContent !== nextTitle) title.textContent = nextTitle;
  const nextHtml = !scopedRuntime
    ? '<div class="empty-variant-note">Start a preset to test it from the local chat interface.</div>'
    : conversation?.freshConversationStats
      ? formatFreshConversationRuntimeStats(scopedRuntime)
      : formatChatRuntimeStatsFlat(scopedRuntime, { useSessionPeaks: false, freshConversationStats: false });
  if (host.innerHTML !== nextHtml) host.innerHTML = nextHtml;
}
function toggleChatStatsCollapsed() {
  chatState.statsCollapsed = !chatState.statsCollapsed;
  persistChatConversationState();
  renderChatUi();
}
function renderChatStudioLaneSelector() {
  const select = $("chatStudioLane");
  if (!select) return;
  const previous = String(select.value || "");
  const rows = typeof aiStudioResourceRows === "function" ? aiStudioResourceRows() : [];
  const liveReady = lastStatus?.ai_studio?.model_ready;
  if (liveReady && typeof liveReady === "object") {
    try {
      localStorage.setItem("club3090_chat_studio_models", JSON.stringify(liveReady));
    } catch (error) {}
  }
  let cachedReady = {};
  try {
    cachedReady = JSON.parse(localStorage.getItem("club3090_chat_studio_models") || "{}");
  } catch (error) {}
  const backendReady = liveReady && typeof liveReady === "object" ? liveReady : cachedReady;
  let cachedStudioActive = true;
  try {
    const stored = localStorage.getItem("club3090_chat_studio_active");
    if (stored !== null) cachedStudioActive = stored === "1";
  } catch (error) {}
  const studioReadyForPlanning = lastStatus && Object.prototype.hasOwnProperty.call(lastStatus, "ai_studio")
    ? !!(lastStatus?.ai_studio?.ready || lastStatus?.ai_studio?.active)
    : !!(window.__club3090ChatStudioActive ?? cachedStudioActive);
  const backendPlanReady = lastStatus && Object.prototype.hasOwnProperty.call(lastStatus, "ai_studio")
    ? !!(lastStatus?.ai_studio?.backend_plan_ready || lastStatus?.ai_studio?.production?.ready || lastStatus?.ai_studio?.model_ready?.production)
    : false;
  const hasAny = (tokens) => rows.some((entry) => {
    const text = `${entry?.label || ""} ${entry?.path || ""} ${entry?.models?.join?.(" ") || ""}`.toLowerCase();
    return tokens.some((token) => text.includes(token));
  });
  const hasAll = (groups) => groups.every((tokens) => hasAny(tokens));
  const laneReady = (lane, groups) =>
    Object.prototype.hasOwnProperty.call(backendReady, lane)
      ? !!backendReady[lane]
      : hasAll(groups);
  const lanes = [
    ["ideogram", "Image · Ideogram-4", laneReady("ideogram", [["ideogram4_fp8_scaled"], ["ideogram4_unconditional"], ["qwen3vl_8b_fp8_scaled"], ["flux2-vae"]])],
    ["hidream", "Image · HiDream-O1", laneReady("hidream", [["hidream-o1-image-dev-2604-fp8", "hidream-o1-image-dev-2604", "hidream_o1"]])],
    ["chroma", "Image · Chroma", laneReady("chroma", [["chroma1-hd"], ["t5xxl_fp16"], ["vae/flux/ae.safetensors", "flux/ae.safetensors"]])],
    ["zimage", "Image · Z-Image", laneReady("zimage", [["z-image-turbo-fp8"], ["qwen_3_4b_fp8_mixed"], ["vae/ae.safetensors", "ae.safetensors"]])],
    ["krea", "Image · Krea 2", laneReady("krea", [["krea2_turbo_fp8_scaled"], ["qwen3vl_4b_fp8_scaled"], ["qwen_image_vae"]])],
    ["music", "Music · ACE-Step", laneReady("music", [["ace_step_v1_3.5b", "ace-step-1.5"]])],
    ["sfx", "Sound · Stable Audio", laneReady("sfx", [["stable-audio-open-1.0.safetensors"], ["t5-base.safetensors"]])],
    ["ltx", "Video · LTX-2.3", laneReady("ltx", [
      ["ltx-2.3-22b-distilled-1.1-q8_0"],
      ["ltx-2.3-22b-distilled_audio_vae"],
      ["ltx-2.3-22b-distilled_video_vae"],
      ["ltx-2.3-22b-distilled_embeddings_connectors"],
      ["gemma_3_12b_it_fp8_scaled"],
    ])],
    ["sulphur", "Video · Sulphur", laneReady("sulphur", [
      ["sulphur_dev-q8_0"],
      ["ltx-2.3-22b-dev_audio_vae"],
      ["ltx-2.3-22b-dev_video_vae"],
      ["ltx-2.3-22b-dev_embeddings_connectors"],
      ["ltx-2.3-22b-distilled-lora-384-1.1"],
      ["gemma_3_12b_it_fp8_scaled"],
    ])],
    ["10eros", "Video · 10Eros", laneReady("10eros", [
      ["10eros_v1-q8_0", "10eros_v1"],
      ["ltx-2.3-22b-dev_audio_vae"],
      ["ltx-2.3-22b-dev_video_vae"],
      ["ltx-2.3-22b-dev_embeddings_connectors"],
      ["ltx-2.3-22b-distilled-lora-384-1.1"],
      ["gemma_3_12b_it_fp8_scaled"],
    ])],
    ["wan", "Video · Wan2.2", laneReady("wan", [
      ["wan2.2-rapid-mega-aio-nsfw-v10-q8_0", "wan2.2-rapid-mega"],
      ["umt5_xxl_fp8_e4m3fn_scaled"],
      ["wan_2.1_vae"],
    ])],
    ["voice", "Speech · Step-Audio-EditX", laneReady("voice", [["step-audio-editx"], ["step-audio-tokenizer"]])],
    ["kokoro", "Speech · Kokoro Voiceover", laneReady("kokoro", [["kokoro-v1.0.onnx"], ["voices-v1.0.bin"]])],
  ];
  const anyReadyLane = lanes.some(([, , ready]) => !!ready) || studioReadyForPlanning;
  const html = `<option value="">Chat response</option><option value="plan" ${anyReadyLane ? "" : "disabled"}>Plan Mode${anyReadyLane ? "" : " (Missing Model)"}</option><option value="plan-backend" ${backendPlanReady ? "" : "disabled"}>Plan Mode (Backend)</option><option value="interactive" ${anyReadyLane ? "" : "disabled"}>Interactive Mode${anyReadyLane ? "" : " (Missing Model)"}</option>${lanes.map(([value, label, ready]) =>
    `<option value="${value}" ${ready ? "" : "disabled"}>${escapeHtml(label)}${ready ? "" : " (Missing Model)"}</option>`
  ).join("")}`;
  if (select.innerHTML !== html) select.innerHTML = html;
  if (["plan", "interactive"].includes(previous) && anyReadyLane) select.value = previous;
  else if (previous === "plan-backend" && backendPlanReady) select.value = previous;
  else if (previous && lanes.some(([value, , ready]) => value === previous && ready)) select.value = previous;
}
function renderChatUi(options = {}) {
  const preserveTranscript = !!options.preserveTranscript;
  const toggle = $("chatSettingsToggle");
  if (toggle) toggle.innerHTML = svgIcon("gear");
  if ($("chatConversationShareBtn"))
    $("chatConversationShareBtn").innerHTML = svgIcon("share");
  updateChatDeleteButtonState();
  if ($("chatOptionsMenu"))
    $("chatOptionsMenu").classList.toggle("hidden", !chatOptionsMenuOpen);
  ensureChatInputBindings();
  renderConversationSelector();
  renderChatPresetSelector();
  renderChatApiPresetSelector();
  renderChatStudioLaneSelector();
  renderChatAttachments();
  if ($("chatAutoscroll")) {
    $("chatAutoscroll").checked = chatTranscriptAutoscrollEnabled();
  }
  if (!preserveTranscript) renderChatTranscript(false, { reason: "ui" });
  renderChatRuntimeStats();
  handleChatInputResize();
  const runtime = activeChatRuntime();
  const chatControlsDisabled = chatState.busy || chatHydrationPending() || !chatStateHydrated || chatBenchmarkLocked();
  const studioStatus = lastStatus?.ai_studio || {};
  const hasStudioStatus = !!(lastStatus && Object.prototype.hasOwnProperty.call(lastStatus, "ai_studio"));
  if (hasStudioStatus) {
    window.__club3090ChatStudioActive = !!(studioStatus.ready || studioStatus.active);
    try {
      localStorage.setItem("club3090_chat_studio_active", window.__club3090ChatStudioActive ? "1" : "0");
    } catch (error) {}
  }
  let cachedStudioActive = true;
  try {
    const stored = localStorage.getItem("club3090_chat_studio_active");
    if (stored !== null) cachedStudioActive = stored === "1";
  } catch (error) {}
  const studioReady = hasStudioStatus
    ? !!(studioStatus.ready || studioStatus.active)
    : !!(window.__club3090ChatStudioActive ?? cachedStudioActive);
  if ($("chatStudioRow")) $("chatStudioRow").classList.toggle("hidden", !studioReady);
  if (!studioReady && $("chatStudioLane")) $("chatStudioLane").value = "";
  if ($("chatStatsCard"))
    $("chatStatsCard").classList.toggle("collapsed", !!chatState.statsCollapsed);
  if ($("chatStatsToggleBtn")) {
    $("chatStatsToggleBtn").innerHTML = svgIcon(
      chatState.statsCollapsed ? "chevron-down" : "chevron-up",
    );
  }
  if ($("chatSendBtn")) {
    const hasDraft =
      !!String($("chatInput")?.value || "").trim() ||
      !!(chatState.attachments || []).length;
    const studioLaneSelected = !!String($("chatStudioLane")?.value || "");
    $("chatSendBtn").disabled =
      chatControlsDisabled ||
      !(studioLaneSelected || activeChatPresets().length > 0 || chatSelectedRuntimeIsUnavailable()) ||
      (!chatState.busy && !hasDraft);
    $("chatSendBtn").classList.toggle("is-stop", !!chatState.busy);
    $("chatSendBtn").innerHTML = svgIcon(chatState.busy ? "stop" : "send");
  }
  if ($("chatStudioLane")) $("chatStudioLane").disabled = chatControlsDisabled || !studioReady;
  if ($("chatAttachBtn")) $("chatAttachBtn").disabled = chatControlsDisabled;
  if ($("chatMicBtn")) {
    $("chatMicBtn").disabled = chatControlsDisabled;
    $("chatMicBtn").classList.toggle("recording", !!chatRecognition?.__active);
  }
  if ($("chatConversationNewBtn"))
    $("chatConversationNewBtn").disabled = chatControlsDisabled;
  if ($("chatConversationEditBtn"))
    $("chatConversationEditBtn").disabled = chatControlsDisabled;
  if ($("chatConversationShareBtn"))
    $("chatConversationShareBtn").disabled = chatControlsDisabled;
  if ($("chatConversationDeleteBtn"))
    $("chatConversationDeleteBtn").disabled = chatControlsDisabled;
  ensureChatArchiveLongPressBinding();
  syncHeaderChatButtonAlignment();
  if (
    activeChatConversation()?.generationActive &&
    !chatState.busy &&
    !chatLocalRequestActive &&
    !chatRequestController
  ) {
    chatState.busy = true;
    scheduleChatStreamResumePolling(120);
  }
}
function chatTextAttachmentName(prefix = "pasted") {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  return `${prefix}-${stamp}.md`;
}
function isTextAttachmentFile(file) {
  const type = String(file?.type || "").toLowerCase();
  const name = String(file?.name || "").toLowerCase();
  return (
    type.startsWith("text/") ||
    /(json|javascript|typescript|yaml|xml|csv|x-sh)/.test(type) ||
    /\.(txt|md|markdown|json|jsonl|csv|tsv|ya?ml|xml|html?|css|jsx?|tsx?|mjs|cjs|py|sh|bash|zsh|log|ini|cfg|conf)$/i.test(name)
  );
}
function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error(`Failed to read ${file?.name || "file"}.`));
    reader.readAsDataURL(file);
  });
}
function captureVideoAttachmentThumbnail(file) {
  return new Promise((resolve) => {
    if (!file || !String(file.type || "").toLowerCase().startsWith("video/")) return resolve("");
    const video = document.createElement("video");
    const url = URL.createObjectURL(file);
    let settled = false;
    const finish = (value = "") => {
      if (settled) return;
      settled = true;
      URL.revokeObjectURL(url);
      resolve(value);
    };
    video.preload = "metadata";
    video.muted = true;
    video.playsInline = true;
    video.addEventListener("loadeddata", () => {
      try {
        const canvas = document.createElement("canvas");
        const width = Math.max(1, Math.min(480, Number(video.videoWidth || 320)));
        const height = Math.max(1, Math.round(width * (Number(video.videoHeight || 180) / Math.max(1, Number(video.videoWidth || 320)))));
        canvas.width = width;
        canvas.height = height;
        canvas.getContext("2d")?.drawImage(video, 0, 0, width, height);
        finish(canvas.toDataURL("image/jpeg", 0.72));
      } catch (error) {
        finish("");
      }
    }, { once: true });
    video.addEventListener("error", () => finish(""), { once: true });
    setTimeout(() => finish(""), 4500);
    video.src = url;
    try {
      video.currentTime = 0.1;
    } catch (error) {}
  });
}
async function uploadChatMediaAttachment(file, kind, source = "file") {
  const cleanKind = String(kind || "").toLowerCase();
  const thumbnailUrl = cleanKind === "video" ? await captureVideoAttachmentThumbnail(file) : "";
  const response = await fetch("/admin/chat-attachments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      kind: cleanKind,
      name: file?.name || cleanKind || "media",
      mime: file?.type || `${cleanKind}/*`,
      source,
      thumbnail_url: thumbnailUrl,
      data_url: await readFileAsDataUrl(file),
    }),
  });
  const payload = await response.json();
  if (!response.ok || !payload?.ok || !payload?.attachment) {
    throw new Error(payload?.error || `Failed to upload ${file?.name || cleanKind || "media"}.`);
  }
  return cloneChatAttachment(payload.attachment);
}
async function buildChatAttachmentsFromFiles(files, source = "file") {
  const additions = [];
  for (const file of files || []) {
    if (!file) continue;
    const fileType = String(file.type || "").toLowerCase();
    if (fileType.startsWith("image/")) {
      additions.push(await uploadChatMediaAttachment(file, "image", source));
      continue;
    }
    if (fileType.startsWith("audio/")) {
      additions.push(await uploadChatMediaAttachment(file, "audio", source));
      continue;
    }
    if (fileType.startsWith("video/")) {
      additions.push(await uploadChatMediaAttachment(file, "video", source));
      continue;
    }
    if (isTextAttachmentFile(file)) {
      additions.push({
        id: chatAttachmentId(),
        kind: "text",
        name: file.name || `attachment-${additions.length + 1}.txt`,
        mime: file.type || "text/plain",
        text: await file.text(),
        source,
      });
      continue;
    }
    throw new Error(`Unsupported attachment type: ${file.name || "file"}. Attach text, image, audio, or video files only.`);
  }
  return additions;
}
function addChatAttachments(additions) {
  if (!Array.isArray(additions) || !additions.length) return;
  chatState.attachments = [...(chatState.attachments || []), ...additions];
  persistChatConversationState();
  renderChatAttachments();
}
function openChatAttachmentPicker() {
  if (chatState.busy) return;
  $("chatAttachmentInput")?.click();
}
async function handleChatAttachmentSelect(event) {
  const files = Array.from(event?.target?.files || []);
  if (!files.length) return;
  try {
    addChatAttachments(await buildChatAttachmentsFromFiles(files));
    setChatMsg("");
  } catch (e) {
    setChatMsg(String(e || ""));
  } finally {
    if (event?.target) event.target.value = "";
  }
}
async function handleChatPaste(event) {
  const clipboard = event?.clipboardData;
  if (!clipboard) return;
  const files = Array.from(clipboard.files || []).filter(Boolean);
  if (files.length) {
    event.preventDefault();
    try {
      addChatAttachments(await buildChatAttachmentsFromFiles(files, "paste"));
      setChatMsg("");
    } catch (e) {
      setChatMsg(String(e || ""));
    }
    return;
  }
  const text = String(clipboard.getData("text/plain") || "");
  if (text.length < 1024) return;
  event.preventDefault();
  addChatAttachments([
    {
      id: chatAttachmentId(),
      kind: "text",
      name: chatTextAttachmentName(),
      mime: "text/markdown",
      text,
      source: "paste",
    },
  ]);
  setChatMsg("Attached the pasted text as a Markdown file.");
}
function speechRecognitionCtor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}
function appendChatInputText(text) {
  const input = $("chatInput");
  if (!input) return;
  const current = String(input.value || "");
  input.value = current ? `${current}${/\s$/.test(current) ? "" : " "}${text}` : text;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}
function ensureChatRecognition() {
  if (chatRecognition) return chatRecognition;
  const Ctor = speechRecognitionCtor();
  if (!Ctor) return null;
  const recognition = new Ctor();
  recognition.continuous = true;
  recognition.interimResults = false;
  recognition.lang = navigator.language || "en-US";
  recognition.onstart = () => {
    recognition.__active = true;
    setChatMsg("Listening for dictation...");
    renderChatUi();
  };
  recognition.onend = () => {
    recognition.__active = false;
    if (!chatState.busy) setChatMsg("");
    renderChatUi();
  };
  recognition.onerror = (event) => {
    recognition.__active = false;
    setChatMsg(`Voice dictation error: ${event?.error || "unknown error"}`);
    renderChatUi();
  };
  recognition.onresult = (event) => {
    const chunks = [];
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      if (result?.isFinal) chunks.push(String(result[0]?.transcript || "").trim());
    }
    const text = chunks.filter(Boolean).join(" ");
    if (text) appendChatInputText(text);
  };
  chatRecognition = recognition;
  return recognition;
}
function toggleChatDictation() {
  const recognition = ensureChatRecognition();
  if (!recognition) {
    setChatMsg("Voice dictation is not available in this browser.");
    return;
  }
  try {
    if (recognition.__active) recognition.stop();
    else recognition.start();
  } catch (e) {
    setChatMsg(String(e || "Unable to toggle voice dictation."));
  }
}
function chatAttachmentTextBlock(attachment) {
  const name = attachment?.name || "attachment";
  const kind = String(attachment?.kind || "text").toLowerCase();
  if (kind === "audio" || kind === "video") {
    const mime = attachment?.mime ? ` · ${attachment.mime}` : "";
    return `${kind === "audio" ? "Audio" : "Video"} attachment: ${name}${mime}`;
  }
  return `Attached file: ${name}\n\n${attachment?.text || ""}`;
}
function activeChatRequestParams() {
  const preset = chatApiPresetOptions().find(
    (item) => String(item?.name || "") === String(chatState.apiPresetName || ""),
  );
  return preset
    ? {
        ...defaultChatParams(),
        ...normalizePresetParamsForChat(preset.params || {}),
      }
    : cloneChatParams(chatState.params);
}
function chatMessageReasoningText(message) {
  return String(
    message?.reasoningText || message?.reasoning_content || message?.reasoning || "",
  );
}
function splitThinkingBlocks(text) {
  const blocks = [];
  const content = String(text || "").replace(
    /<(think|thinking)>([\s\S]*?)<\/\1>/gi,
    (_, _tag, body) => {
      const clean = String(body || "").trim();
      if (clean) blocks.push(clean);
      return "\n\n";
    },
  );
  return {
    reasoningText: blocks.join("\n\n").trim(),
    contentText: content.replace(/\n{3,}/g, "\n\n").trim(),
  };
}
function chatMessageThinkingView(message) {
  const visibleText =
    message?.streamingVisibleActive && typeof message?.streamingVisibleText === "string"
      ? message.streamingVisibleText
      : undefined;
  const titleStripped = extractChatTitleMarker(visibleText ?? message?.text ?? "");
  const sourceText = titleStripped.title ? titleStripped.text : String(visibleText ?? message?.text ?? "");
  const inline = splitThinkingBlocks(sourceText);
  const direct =
    message?.streamingVisibleActive && typeof message?.streamingVisibleReasoningText === "string"
      ? String(message.streamingVisibleReasoningText || "").trim()
      : chatMessageReasoningText(message).trim();
  const parts = [];
  if (direct) parts.push(direct);
  if (inline.reasoningText && !parts.includes(inline.reasoningText))
    parts.push(inline.reasoningText);
  return {
    reasoningText: parts.join("\n\n").trim(),
    contentText: inline.reasoningText ? inline.contentText : sourceText,
  };
}
function clampChatThinkingDurationMs(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) return 0;
  return Math.round(numeric);
}
function formatChatThinkingDuration(value) {
  const ms = clampChatThinkingDurationMs(value);
  if (!ms) return "";
  const seconds = ms / 1000;
  const digits = seconds >= 10 ? 0 : 1;
  const formatted = trimFormattedNumber(seconds.toFixed(digits));
  return `${formatted} second${formatted === "1" ? "" : "s"}`;
}
function chatMessageThinkingActive(message) {
  return !!message?.thinkingLive;
}
function finalizeChatThinkingState(message, collapse = true) {
  if (!message) return;
  if (message.thinkingStartedAt) {
    message.thinkingDurationMs = clampChatThinkingDurationMs(
      Date.now() - Number(message.thinkingStartedAt || 0),
    );
  } else {
    message.thinkingDurationMs = clampChatThinkingDurationMs(
      message.thinkingDurationMs,
    );
  }
  message.thinkingLive = false;
  message.thinkingDone = !!chatMessageThinkingView(message).reasoningText;
  if (collapse && message.thinkingDone) message.thinkingExpanded = false;
}
function syncChatThinkingTicker() {
  const activeThinkingIndex = (chatState.messages || []).findIndex((message) =>
    chatMessageThinkingActive(message),
  );
  const needsTicker = !!chatState.busy && activeThinkingIndex >= 0;
  if (needsTicker && !chatThinkingTicker) {
    chatThinkingTicker = setInterval(() => {
      const liveThinkingIndex = (chatState.messages || []).findIndex((message) =>
        chatMessageThinkingActive(message),
      );
      if (liveThinkingIndex >= 0) {
        scheduleLiveChatMessageDomUpdate(liveThinkingIndex, false, "ticker");
      }
    }, CHAT_THINKING_RENDER_INTERVAL_MS);
  } else if (!needsTicker && chatThinkingTicker) {
    clearInterval(chatThinkingTicker);
    chatThinkingTicker = null;
  }
}
function toggleChatReasoning(messageIndex) {
  const idx = Number(messageIndex);
  if (!Number.isInteger(idx) || idx < 0) return;
  const message = (chatState.messages || [])[idx];
  if (!message || !chatMessageThinkingView(message).reasoningText) return;
  const expanded =
    message.thinkingExpanded !== undefined
      ? !!message.thinkingExpanded
      : chatMessageThinkingActive(message);
  message.thinkingExpanded = !expanded;
  persistChatConversationState();
  renderChatTranscript(false, { reason: "user" });
}
function buildChatRequestMessages(messages = chatState.messages || []) {
  const preserveThinking = !!activeChatRequestParams().preserve_thinking;
  return (messages || [])
    .map((message) => {
      if (message.role !== "user") {
        const view =
          message.role === "assistant"
            ? chatMessageThinkingView(message)
            : { reasoningText: "", contentText: String(message?.text || "") };
        const payload = { role: message.role, content: view.contentText || "" };
        if (
          message.role === "assistant" &&
          preserveThinking &&
          view.reasoningText
        ) {
          payload.reasoning_content = view.reasoningText;
        }
        return payload;
      }
      const attachments = chatMessageAttachments(message);
      const content = [];
      if (message.text) content.push({ type: "text", text: message.text });
      attachments.forEach((attachment) => {
        if (attachment?.kind === "image" && attachment?.url) {
          content.push({ type: "image_url", image_url: { url: attachment.url } });
        } else if (attachment?.kind === "audio" && attachment?.url) {
          content.push({ type: "audio_url", audio_url: { url: attachment.url } });
          content.push({ type: "text", text: chatAttachmentTextBlock(attachment) });
        } else if (attachment?.kind === "video" && attachment?.url) {
          content.push({ type: "video_url", video_url: { url: attachment.url } });
          content.push({ type: "text", text: chatAttachmentTextBlock(attachment) });
        } else if (attachment?.kind === "text" && attachment?.text) {
          content.push({ type: "text", text: chatAttachmentTextBlock(attachment) });
        }
      });
      if (!content.length) return null;
      if (content.length === 1 && content[0].type === "text") {
        return { role: message.role, content: content[0].text };
      }
      return { role: message.role, content };
    })
    .filter(Boolean);
}
function parseChatStreamFrame(frame) {
  const lines = String(frame || "").split(/\r?\n/);
  let eventName = "message";
  const payloadLines = [];
  for (const line of lines) {
    if (!line) continue;
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) payloadLines.push(line.slice(5).trimStart());
  }
  if (!payloadLines.length) return null;
  const raw = payloadLines.join("\n");
  if (raw === "[DONE]") return null;
  try {
    return { eventName, payload: JSON.parse(raw) };
  } catch (e) {
    return { eventName, payload: { text: raw } };
  }
}
async function requestServerStopForConversation(conversationId) {
  const id = String(conversationId || "").trim();
  if (!id) throw new Error("Conversation id is required.");
  const response = await fetch("/admin/chat-stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: id }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload?.ok) {
    throw new Error(payload?.error || "Failed to stop the running reply.");
  }
  return payload;
}
function stopChatGeneration() {
  const activeConversation = activeChatConversation();
  const activeConversationId = String(
    activeConversation?.id || chatState.activeConversationId || "",
  ).trim();
  if (chatRequestController) {
    setChatMsg("Stopping generation...");
    if (activeConversationId) {
      requestServerStopForConversation(activeConversationId).catch(() => {});
    }
    try {
      chatRequestController.abort();
    } catch (e) {}
    return;
  }
  if (!activeConversation?.generationActive || !activeConversationId) return;
  setChatMsg("Stopping generation...");
  requestServerStopForConversation(activeConversationId)
    .then((payload) => {
      const status = String(payload?.stream?.status || "").toLowerCase();
      if (["done", "error", "aborted", "cancelled", "stopped"].includes(status)) {
        activeConversation.generationActive = false;
        chatState.busy = false;
        stopChatStreamResumePolling();
        persistChatConversationState();
        setChatMsg("");
        renderChatUi();
        return;
      }
      scheduleChatStreamResumePolling(120);
    })
    .catch((error) => {
      setChatMsg(String(error || "Failed to stop the running reply."), "error");
    });
}
function scheduleChatRuntimeStatsRender(force = false) {
  const minIntervalMs = 2000;
  if (force) {
    if (chatRuntimeStatsRenderTimer) {
      clearTimeout(chatRuntimeStatsRenderTimer);
      chatRuntimeStatsRenderTimer = null;
    }
    chatRuntimeStatsRenderLastAt = Date.now();
    renderChatRuntimeStats();
    return;
  }
  const elapsed = Date.now() - Number(chatRuntimeStatsRenderLastAt || 0);
  if (elapsed >= minIntervalMs) {
    chatRuntimeStatsRenderLastAt = Date.now();
    renderChatRuntimeStats();
    return;
  }
  if (chatRuntimeStatsRenderTimer) return;
  chatRuntimeStatsRenderTimer = setTimeout(() => {
    chatRuntimeStatsRenderTimer = null;
    chatRuntimeStatsRenderLastAt = Date.now();
    renderChatRuntimeStats();
  }, Math.max(40, minIntervalMs - elapsed));
}
function persistStreamingChatState(force = false) {
  if (!chatStateHydrated) return;
  if (force) {
    if (chatStreamingPersistTimer) {
      clearTimeout(chatStreamingPersistTimer);
      chatStreamingPersistTimer = null;
    }
  } else if (chatStreamingPersistTimer) {
    return;
  }
  const run = () => {
    chatStreamingPersistTimer = null;
    try {
      if (activeChatConversation()?.messagesLoaded === false) return;
      syncActiveConversationFromChatState();
      localStorage.setItem(
        CHAT_STATE_KEY,
        JSON.stringify(currentChatStatePayload()),
      );
    } catch (e) {}
  };
  if (force) {
    run();
    return;
  }
  chatStreamingPersistTimer = setTimeout(run, 450);
}
function stopChatStreamResumePolling() {
  if (chatStreamResumePollTimer) {
    clearTimeout(chatStreamResumePollTimer);
    chatStreamResumePollTimer = null;
  }
  chatStreamResumePollNonce += 1;
}
function scheduleChatStreamResumePolling(delayMs = 450) {
  if (chatLocalRequestActive || chatRequestController) return;
  stopChatStreamResumePolling();
  const nonce = ++chatStreamResumePollNonce;
  chatStreamResumePollTimer = setTimeout(async () => {
    if (nonce !== chatStreamResumePollNonce) return;
    if (chatLocalRequestActive || chatRequestController) return;
    const conversation = activeChatConversation();
    if (!conversation?.generationActive) return;
    const conversationId = String(conversation.id || "").trim();
    if (!conversationId) return;
    try {
      const response = await fetch(
        `/admin/chat-stream-state?conversation_id=${encodeURIComponent(conversationId)}&_=${Date.now()}`,
        { cache: "no-store" },
      );
      const payload = await response.json();
      const stream =
        payload?.stream && typeof payload.stream === "object"
          ? payload.stream
          : null;
      if (!response.ok || !payload?.ok) {
        throw new Error(payload?.error || "Failed to resume chat stream.");
      }
      if (!stream || !Object.keys(stream).length) {
        conversation.generationActive = false;
        chatState.busy = false;
        syncActiveConversationFromChatState();
        saveChatState();
        renderChatUi();
        finalizeChatTranscriptBottomFollow($("chatTranscript"));
        setChatMsg(
          "The previous reply lost its live stream connection. You can send another message now.",
          "warning",
        );
        stopChatStreamResumePolling();
        return;
      }
      const assistant = [...(chatState.messages || [])]
        .reverse()
        .find((message) => String(message?.role || "") === "assistant");
      if (assistant) {
        const nextAssistantText = String(stream.assistant_text || "");
        const nextReasoningText = String(stream.reasoning_text || "");
        if (nextAssistantText.length >= String(assistant.text || "").length) {
          assistant.text = nextAssistantText;
        }
        if (
          nextReasoningText.length >= String(assistant.reasoningText || "").length
        ) {
          assistant.reasoningText = nextReasoningText;
        }
        assistant.thinkingLive =
          String(stream.status || "") === "streaming" && !!assistant.reasoningText;
        if (String(stream.status || "") !== "streaming") {
          finalizeChatThinkingState(assistant, true);
        }
      }
      updateConversationRuntimeMetrics(
        conversation,
        activeChatRuntime(),
        stream,
        { persist: false, streaming: String(stream.status || "") === "streaming" },
      );
      if (["done", "error", "aborted"].includes(String(stream.status || ""))) {
        conversation.generationActive = false;
        chatState.busy = false;
        if (String(stream.status || "") === "error" && stream.error) {
          setChatMsg(String(stream.error), "error");
        } else {
          setChatMsg("");
        }
        persistChatConversationState();
        renderChatUi();
        finalizeChatTranscriptBottomFollow($("chatTranscript"));
        stopChatStreamResumePolling();
        return;
      }
      chatState.busy = true;
      scheduleChatRuntimeStatsRender();
      scheduleLiveChatMessageDomUpdate(
        Math.max(0, (chatState.messages || []).length - 1),
        false,
        "stream",
      );
      persistStreamingChatState();
      scheduleChatStreamResumePolling(450);
    } catch (error) {
      scheduleChatStreamResumePolling(900);
    }
  }, Math.max(150, Number(delayMs || 0) || 0));
}
function scheduleConversationRuntimeMetricRefresh(attempts = 2, delayMs = 250) {
  let remaining = Math.max(0, Number(attempts || 0) || 0);
  const run = () => {
    if (remaining <= 0) return;
    remaining -= 1;
    refreshStatus({ force: true })
      .then(() => {
        syncActiveConversationRuntimeFromLiveRuntime();
      })
      .catch(() => {})
      .finally(() => {
        if (remaining > 0) setTimeout(run, delayMs);
      });
  };
  run();
}
let activeImageStudioJobId = "";
function formatInteractiveStudioPlanText(plan = {}) {
  const action = String(plan.action || "").toLowerCase();
  const rationale = String(plan.rationale || "").trim();
  if (action !== "generate") return String(plan.prompt || "Tell me what you'd like to create.");
  const steps = Array.isArray(plan.steps) && plan.steps.length
    ? plan.steps
    : [{ label: plan.label, lane: plan.lane, prompt: plan.prompt }];
  const body = steps.map((step, index) => {
    const label = String(step?.label || step?.lane || "AI Studio");
    const purpose = String(step?.purpose || "").trim();
    const prompt = String(step?.prompt || "").trim();
    const batch = step?.batch && typeof step.batch === "object"
      ? Object.entries(step.batch)
          .filter(([, value]) => value !== null && value !== undefined && String(value).trim())
          .map(([key, value]) => `${key.replaceAll("_", " ")}: ${value}`)
          .join(", ")
      : "";
    const dependencies = Array.isArray(step?.depends_on) && step.depends_on.length
      ? `\n   Depends on: ${step.depends_on.join(", ")}`
      : "";
    return `${index + 1}. ${label}${purpose ? ` — ${purpose}` : ""}${batch ? `\n   Batch: ${batch}` : ""}${dependencies}${prompt ? `\n   Prompt: ${prompt}` : ""}`;
  }).join("\n");
  return `Plan${rationale ? ` — ${rationale}` : ""}\n${body}`;
}
function planExecutionUnitTotal(steps = []) {
  return Math.max(1, steps.reduce((total, step) => {
    const batchCount = Math.max(1, Number(step?.batch?.count || 0) || 1);
    return total + (step?.batch ? batchCount : 1);
  }, 0));
}
function planExecutionCompletedUnits(steps = [], stepResults = [], stepIndex = 0, itemIndex = 0) {
  let completed = 0;
  for (let index = 0; index < stepIndex; index += 1) {
    const step = steps[index] || {};
    if (step?.batch) {
      const outputs = Array.isArray(stepResults[index]?.outputs) ? stepResults[index].outputs.length : 0;
      const batchCount = Math.max(1, Number(step?.batch?.count || 0) || 1);
      completed += outputs > 0 ? outputs : batchCount;
    } else {
      completed += 1;
    }
  }
  return completed + Math.max(0, itemIndex);
}
function planExecutionPhaseWeight(status = "") {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "success") return 1;
  if (normalized === "running") return 0.55;
  if (normalized === "uploading") return 0.25;
  if (normalized === "preparing") return 0.15;
  if (normalized === "submitting") return 0.08;
  if (normalized === "queued") return 0.02;
  return 0.05;
}
function planExecutionProgressText(plan = {}, steps = [], stepResults = [], stepIndex = 0, itemIndex = 0, batchItems = [], generation = {}) {
  const step = steps[stepIndex] || {};
  const stepLabel = String(step?.label || step?.lane || "AI Studio");
  const totalSteps = Math.max(1, steps.length);
  const totalUnits = planExecutionUnitTotal(steps);
  const completedUnits = planExecutionCompletedUnits(steps, stepResults, stepIndex, itemIndex);
  const stepTotal = step?.batch ? Math.max(1, batchItems.length || Number(step?.batch?.count || 0) || 1) : 1;
  const phaseWeight = planExecutionPhaseWeight(generation?.status);
  const currentUnits = step?.batch
    ? Math.max(phaseWeight, Math.min(stepTotal, Math.max(1, itemIndex + phaseWeight)))
    : Math.max(phaseWeight, 0.05);
  const percent = Math.max(0, Math.min(100, Math.round(((completedUnits + currentUnits) / totalUnits) * 100)));
  const currentProgress = step?.batch ? `${itemIndex + 1}/${stepTotal}` : "1/1";
  const nextStep = steps[stepIndex + 1] || null;
  const nextLabel = nextStep
    ? String(nextStep?.label || nextStep?.lane || "AI Studio")
    : "Complete";
  return [
    `Generating Assets ${stepIndex + 1}/${totalSteps} · ${percent}% Done`,
    `Now: ${stepLabel} ${currentProgress} · Next: ${nextLabel}`,
  ].join("\n");
}
function planExecutionProgressHeadline(text = "") {
  return String(text || "").split(/\n/, 1)[0] || "";
}
function latestPendingStudioPlan() {
  return [...(chatState.messages || [])].reverse().find((message) =>
    message?.role === "assistant" &&
    message?.studioLane === "plan" &&
    message?.interactivePlan &&
    String(message.interactivePlan.action || "").toLowerCase() === "generate" &&
    !message.generatedMedia
  )?.interactivePlan || null;
}
function chatTextConfirmsPlan(text) {
  const normalized = String(text || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized || normalized.length > 220) return false;
  if (/\b(?:cancel|stop|wait|hold|change|revise|revision|instead|not|don t|dont|do not|no)\b/.test(normalized)) return false;
  return /\b(?:confirm|confirmed|approve|approved|execute|run|proceed|go ahead|looks good|do it|yes|ok|okay)\b/.test(normalized);
}
function latestResumableStudioExecution(plan = {}) {
  const signature = JSON.stringify(plan?.steps || []);
  return [...(chatState.messages || [])].reverse().find((message) =>
    message?.role === "assistant" &&
    ["plan-execution", "interactive-execution"].includes(String(message?.studioLane || "")) &&
    Array.isArray(message?.studioPlanResults) &&
    JSON.stringify(message?.interactivePlan?.steps || []) === signature
  ) || null;
}
function parsePlanBatchItems(text) {
  let source = String(text || "").trim();
  source = source
    .replace(/^\uFEFF/, "")
    .replace(/^`{2,}\s*(?:json|javascript|js)?\s*/i, "")
    .replace(/\s*`{2,}\s*$/i, "")
    .trim();
  const fenced = source.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenced) source = fenced[1].trim();
  const start = source.indexOf("[");
  const end = source.lastIndexOf("]");
  if (start >= 0 && end > start) source = source.slice(start, end + 1);
  const parsed = JSON.parse(source);
  if (!Array.isArray(parsed)) throw new Error("The text step did not return the JSON array required by its batch plan.");
  return parsed.filter((item) => item && typeof item === "object");
}
function planBatchScalar(value) {
  if (Array.isArray(value)) return value.map((row) => planBatchScalar(row)).filter(Boolean).join("; ");
  if (value && typeof value === "object") {
    for (const key of ["text", "summary", "description", "body", "copy", "copy_block", "paragraph", "positioning", "script", "value"]) {
      const nested = planBatchScalar(value[key]);
      if (nested) return nested;
    }
    return Object.entries(value)
      .map(([key, row]) => `${key}: ${planBatchScalar(row)}`.trim())
      .filter((row) => !/:$/.test(row))
      .join("; ");
  }
  return String(value ?? "").trim();
}
function firstPlanBatchValue(item = {}, keys = []) {
  for (const key of keys) {
    const value = planBatchScalar(item?.[key]);
    if (value) return value;
  }
  return "";
}
function planPromptWantsNarrationCopy(...parts) {
  const text = parts.map((part) => String(part || "")).join(" ").toLowerCase();
  return (
    /\b(?:read|narrat\w*|voiceover|speak|speech|tts|audio)\b[\s\S]{0,120}\b(?:paragraph|text|body|copy|description|summary|profile|script)\b/.test(text) ||
    /\b(?:paragraph|text|body|copy|description|summary|profile|script)\b[\s\S]{0,120}\b(?:read|narrat\w*|voiceover|speak|speech|tts|audio)\b/.test(text)
  );
}
function normalizePlanBatchItem(item = {}, sourcePrompt = "", originalRequest = "") {
  const normalized = { ...(item && typeof item === "object" ? item : {}) };
  normalized.name = firstPlanBatchValue(normalized, ["name", "title", "subject", "label", "person", "character", "topic"]) || normalized.name || "";
  normalized.dates = firstPlanBatchValue(normalized, ["dates", "date", "dates_served", "served", "term", "years", "period", "era"]) || normalized.dates || "";
  normalized.text = firstPlanBatchValue(normalized, ["text", "paragraph", "body", "copy", "copy_block", "description", "summary", "profile", "positioning", "tagline", "accomplishments", "bio", "script", "narration"]) || normalized.text || "";
  const explicitSpeechText = firstPlanBatchValue(normalized, ["speech_text", "narration_text", "narration_script", "voiceover_text", "voiceover_script", "tts_text", "audio_text", "script"]);
  const looseSpeechText = firstPlanBatchValue(normalized, ["speech", "narration", "voiceover"]);
  normalized.speech_text = explicitSpeechText || looseSpeechText || normalized.speech_text || "";
  normalized.image_prompt = firstPlanBatchValue(normalized, ["image_prompt", "visual_prompt", "image", "illustration_prompt", "art_prompt", "prompt"]) || normalized.image_prompt || "";
  if (!explicitSpeechText && planPromptWantsNarrationCopy(sourcePrompt, originalRequest) && normalized.text) {
    normalized.speech_text = normalized.text;
  } else if (!normalized.speech_text && normalized.text) {
    normalized.speech_text = normalized.text;
  }
  if (!normalized.image_prompt) {
    const identity = [normalized.name, normalized.dates].filter(Boolean).join(" ");
    normalized.image_prompt = [
      identity ? `Create a faithful image for ${identity}.` : "Create a faithful image for this source item.",
      normalized.text ? `Use this item context: ${normalized.text}` : "",
      "Make the composition specific, visually clear, and distinct from neighboring batch items.",
    ].filter(Boolean).join(" ");
  }
  return normalized;
}
function normalizePlanBatchItems(items = [], sourcePrompt = "", originalRequest = "") {
  return (Array.isArray(items) ? items : [])
    .filter((item) => item && typeof item === "object")
    .map((item) => normalizePlanBatchItem(item, sourcePrompt, originalRequest));
}
function planSourceExecutionPrompt(prompt, expectedBatchCount = 0) {
  const expected = Number(expectedBatchCount || 0);
  return [
    String(prompt || "").trim(),
    "Output only one complete strict JSON array. Do not wrap it in Markdown fences, commentary, headings, or prose.",
    "Use valid JSON strings with double quotes for every key and string value. Do not include trailing commas.",
    "If the request names or implies multiple subjects, entries, scenes, sections, products, people, places, or assets, create one separate object for each one. Never combine multiple requested items inside one wrapper object.",
    "Preserve requested ordinal ranges, counts, order, duplicates, editions, and exact membership. For first/last/next/every/all requests, do not skip intermediate entries or substitute better-known adjacent items.",
    "The source prompt's required field names are authoritative. If it asks for fields such as text, image_prompt, or speech_text, use those exact keys and do not substitute synonyms such as accomplishments, paragraph, narration, image, or speech.",
    "When speech_text is requested for reading/narrating/speaking paragraph, text, body, copy, profile, summary, or script content, speech_text must match that generated copy exactly enough for the audio to read it. Do not replace it with famous quotes, oaths, excerpts, slogans, or unrelated speeches.",
    "Honor exact word-count constraints for generated script fields; for example, a 20-word voiceover script must contain exactly 20 spoken words.",
    "For factual or real-world subjects, use conservative widely established facts. Do not invent events, dates, roles, names, achievements, causal links, attributions, or quotations; if uncertain, use broader accurate wording instead of a specific claim.",
    "For fictional products, brands, worlds, facilities, or scenarios, stay inside the user's stated premise. Do not add unrelated elements, audiences, claims, technologies, names, locations, objectives, story details, or worldbuilding that the user did not request.",
    "When image_prompt is requested, make each image_prompt a self-contained prompt with distinct pose, viewpoint, setting/scenery, crop, lighting, action, composition, and contextual details appropriate to that object.",
    expected > 0 ? `The array must contain exactly ${expected} objects/items.` : "",
    expected > 1 ? `No object may contain a nested list that represents the ${expected} requested objects/items; split those into top-level array objects instead.` : "",
    expected >= 20
      ? "Keep every generated field compact enough to fit the full array in one response: text fields should be concise short paragraphs, speech_text should mirror text, and image_prompt should be one detailed but compact sentence."
      : "",
  ].filter(Boolean).join("\n\n");
}
function expandPlanBatchPrompt(template, item = {}) {
  return String(template || "").replace(/\{\{([a-zA-Z0-9_]+)\}\}/g, (_match, key) =>
    String(item?.[key] ?? ""),
  );
}
function planBatchExpectedCountForSource(steps = [], sourceStepNumber = 0, prompt = "") {
  const dependentCounts = (Array.isArray(steps) ? steps : [])
    .filter((step) => Number(step?.batch?.source_step || 0) === Number(sourceStepNumber || 0))
    .map((step) => Number(step?.batch?.count || 0))
    .filter((count) => Number.isFinite(count) && count > 0);
  const promptText = String(prompt || "");
  const topLevelMatches = Array.from(promptText.matchAll(
    /\b(?:output|return|array\s+must\s+contain)\s+exactly\s+(\d{1,4})\s+(?:top[-\s]+level\s+)?(?:objects?|object\(s\)(?:\/item\(s\))?|items?|item\(s\))(?=$|\s|[.,;:])/gi,
  ));
  if (topLevelMatches.length) {
    return Number(topLevelMatches[topLevelMatches.length - 1][1] || 0);
  }
  if (dependentCounts.length) return Math.max(...dependentCounts);
  const promptMatches = Array.from(promptText.matchAll(
    /\bexactly\s+(\d{1,4})\s+(?:objects?|object\(s\)(?:\/item\(s\))?|items?|item\(s\)|entries|records?|artifacts?|rows?|clips?|images?|audios?)(?=$|\s|[.,;:])/gi,
  ));
  const promptCount = promptMatches.length ? Number(promptMatches[promptMatches.length - 1][1] || 0) : 0;
  return Math.max(promptCount, 0);
}
function planIdeogramRequestsSingleRender(...parts) {
  const text = parts.map((part) => String(part || "")).join(" ").toLowerCase();
  return /\b(?:single|one)\s+(?:final\s+)?(?:image|render|picture|photo|photograph|poster|logo|illustration)\b/.test(text) ||
    /\b(?:exactly\s+)?(?:one|single|1)\s+(?:(?:[a-z0-9-]+)\s+){0,6}(?:image|render|picture|photo|photograph|poster|logo|illustration)\b/.test(text) ||
    /\b(?:no|not|without)\s+(?:a\s+)?(?:grid|contact\s+sheet|candidate\s+sheet|2x2|two[-\s]+by[-\s]+two|four[-\s]+panel)\b/.test(text) ||
    /\b(?:high[-\s]+resolution|high[-\s]+quality|hi[-\s]*res|full[-\s]+resolution)\b/.test(text) ||
    /\b(?:1080p|1440p|2160p|4k|8k|uhd|qhd|hd)\b/.test(text) ||
    /\b\d{3,5}\s*[x×]\s*\d{3,5}\b/.test(text);
}
function planBatchSubjectName(item = {}, fallback = "") {
  for (const key of ["name", "title", "subject", "label", "person", "character", "topic"]) {
    const value = String(item?.[key] ?? "").trim();
    if (value) return value;
  }
  return String(fallback || "").trim();
}
function planBatchSubjectContext(item = {}) {
  return ["dates", "date", "term", "served", "era", "period", "role", "location", "style"]
    .map((key) => String(item?.[key] ?? "").trim())
    .filter(Boolean)
    .slice(0, 4)
    .join(" · ");
}
function planBatchItemsForStepDescriptor(step = {}, sourceItems = []) {
  const items = Array.isArray(sourceItems) ? sourceItems.filter((item) => item && typeof item === "object") : [];
  if (!items.length) return [];
  const descriptor = String(step?.batch?.items || "").trim();
  let selected = items;
  const nameMatch = descriptor.match(/\bname\s*=\s*["']?([a-z0-9][a-z0-9 _-]{0,80})["']?/i);
  if (nameMatch) {
    const target = String(nameMatch[1] || "")
      .replace(/[^a-z0-9 _-].*$/i, "")
      .trim()
      .toLowerCase();
    if (target) {
      const normalizedTarget = target.replace(/[_-]+/g, " ");
      const matched = items.filter((item) => {
        const name = planBatchSubjectName(item || {}, "")
          .toLowerCase()
          .replace(/[_-]+/g, " ");
        return name === normalizedTarget || name.includes(normalizedTarget);
      });
      if (matched.length) selected = matched;
    }
  }
  const count = Number(step?.batch?.count || 0);
  if (Number.isFinite(count) && count > 0 && selected.length > count) {
    selected = selected.slice(0, count);
  }
  return selected;
}
function planKokoroVoiceForItem(item = {}, index = 0, contextText = "") {
  const text = [
    planBatchSubjectName(item || {}, ""),
    planBatchScalar(item?.gender),
    planBatchScalar(item?.voice),
    planBatchScalar(item?.voice_hint),
    planBatchScalar(item?.role),
    planBatchScalar(item?.title),
    planBatchScalar(item?.text),
    planBatchScalar(item?.speech_text),
    contextText,
  ].join(" ").toLowerCase();
  const femaleVoices = ["af_heart", "af_bella", "af_nicole"];
  const maleVoices = ["am_adam", "am_michael", "bm_george", "am_echo"];
  if (/\b(?:she|her|hers|woman|female|girl|mother|queen|actress|soprano|alto)\b/.test(text)) {
    return femaleVoices[index % femaleVoices.length];
  }
  if (/\b(?:he|him|his|man|male|boy|father|king|president|actor|baritone|tenor|bass)\b/.test(text)) {
    return maleVoices[index % maleVoices.length];
  }
  if (/\bmale voices?\b|\bmen's voices?\b|\bmasculine voices?\b/.test(text)) {
    return maleVoices[index % maleVoices.length];
  }
  return femaleVoices[index % femaleVoices.length];
}
function planLanePromptNeedsEnhancement(lane) {
  return ["ideogram", "hidream", "chroma", "zimage", "krea", "ltx", "sulphur", "10eros", "wan", "music", "sfx"].includes(
    String(lane || "").trim().toLowerCase(),
  );
}
function planLaneSpeaksPrompt(lane) {
  return ["kokoro", "voice"].includes(String(lane || "").trim().toLowerCase());
}
function planWordTokens(text) {
  return String(text || "").match(/[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*/g) || [];
}
function planWordKey(word) {
  return String(word || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
}
function planTrimRepeatedLeadTail(text) {
  const words = planWordTokens(text);
  const maxRepeat = Math.min(4, Math.floor(words.length / 2));
  for (let count = maxRepeat; count >= 1; count -= 1) {
    const head = words.slice(0, count).map(planWordKey).join(" ");
    const tail = words.slice(words.length - count).map(planWordKey).join(" ");
    if (head && head === tail) {
      return `${words.slice(0, words.length - count).join(" ")}.`;
    }
  }
  return String(text || "").trim();
}
function planExactWordCountRequirements(...parts) {
  const text = parts.map((part) => String(part || "")).join(" ");
  const requirements = [];
  const seen = new Set();
  const addRequirement = (count, label = "") => {
    const expected = Number(count || 0);
    if (!Number.isFinite(expected) || expected <= 0) return;
    const normalizedLabel = String(label || "script").toLowerCase().replace(/\s+/g, "_");
    const keys = /(?:voiceover|narration|speech|tts|audio|script)/.test(normalizedLabel)
      ? ["voiceover_script", "narration_script", "narration_text", "speech_text", "voiceover_text", "tts_text", "audio_text", "script"]
      : ["text"];
    const signature = `${expected}:${keys.join(",")}`;
    if (seen.has(signature)) return;
    seen.add(signature);
    requirements.push({ count: expected, keys, label: label || "script" });
  };
  const leadingPatterns = [
    /\b(?:exactly\s+)?(\d{1,3})[-\s]+word\s+(voiceover[_\s]+script|voiceover[_\s]+text|narration[_\s]+script|narration[_\s]+text|speech[_\s]+script|speech[_\s]+text|tts[_\s]+script|tts[_\s]+text|audio[_\s]+script|audio[_\s]+text|script)\b/gi,
    /\b(?:exactly\s+)?(\d{1,3})\s+words?\s+(?:long\s+)?(?:for\s+)?(voiceover[_\s]+script|voiceover[_\s]+text|narration[_\s]+script|narration[_\s]+text|speech_text|speech\s+text|tts\s+text|audio\s+text|script)\b/gi,
  ];
  const trailingPatterns = [
    /\b(voiceover[_\s]+script|voiceover[_\s]+text|narration[_\s]+script|narration[_\s]+text|speech_text|speech\s+text|tts\s+text|audio\s+text|script)\b[^.\n;]{0,80}?\b(?:exactly\s+)?(\d{1,3})\s+words?\b/gi,
  ];
  for (const pattern of leadingPatterns) {
    for (const match of text.matchAll(pattern)) addRequirement(match[1], match[2]);
  }
  for (const pattern of trailingPatterns) {
    for (const match of text.matchAll(pattern)) addRequirement(match[2], match[1]);
  }
  return requirements.slice(0, 6);
}
function planBatchWordCountError(items = [], sourcePrompt = "", originalRequest = "") {
  const requirements = planExactWordCountRequirements(sourcePrompt, originalRequest);
  if (!requirements.length) return "";
  const rows = Array.isArray(items) ? items : [];
  for (let itemIndex = 0; itemIndex < rows.length; itemIndex += 1) {
    const item = rows[itemIndex] || {};
    for (const requirement of requirements) {
      const value = firstPlanBatchValue(item, requirement.keys);
      if (!value) continue;
      const actual = planWordTokens(value).length;
      if (actual !== requirement.count) {
        return `Item ${itemIndex + 1} ${requirement.label || "script"} has ${actual}/${requirement.count} words.`;
      }
    }
  }
  return "";
}
function planRepairTextToWordCount(value, expectedCount = 0, item = {}, originalRequest = "") {
  const expected = Number(expectedCount || 0);
  if (!Number.isFinite(expected) || expected <= 0) return String(value || "").trim();
  const baseWords = planWordTokens(planTrimRepeatedLeadTail(value));
  if (baseWords.length >= expected) return `${baseWords.slice(0, expected).join(" ")}.`;
  const used = new Set(baseWords.map(planWordKey).filter(Boolean));
  const pool = planWordTokens([
    planBatchScalar(item?.image_prompt),
    planBatchScalar(item?.visual_prompt),
    planBatchScalar(item?.scene_name),
    planBatchScalar(item?.name),
    planBatchScalar(item?.title),
    planBatchScalar(item?.location),
    planBatchScalar(item?.setting),
    planBatchScalar(item?.tagline),
    planBatchScalar(item?.positioning),
    planBatchScalar(item?.summary),
    planBatchScalar(item?.description),
    originalRequest,
  ].filter(Boolean).join(" ")).filter((word) => {
    const key = planWordKey(word);
    if (!key || used.has(key)) return false;
    used.add(key);
    return true;
  });
  const repaired = [...baseWords];
  for (const word of pool) {
    if (repaired.length >= expected) break;
    repaired.push(word);
  }
  const fallback = ["clear", "compact", "future", "growth", "designed", "for", "daily", "use"];
  for (let index = 0; repaired.length < expected; index += 1) {
    repaired.push(fallback[index % fallback.length]);
  }
  return `${repaired.slice(0, expected).join(" ")}.`;
}
function repairPlanBatchWordCounts(items = [], sourcePrompt = "", originalRequest = "") {
  const requirements = planExactWordCountRequirements(sourcePrompt, originalRequest);
  if (!requirements.length) return { items, repaired: false, notes: [] };
  const rows = (Array.isArray(items) ? items : []).map((item) => ({ ...(item || {}) }));
  const notes = [];
  for (let itemIndex = 0; itemIndex < rows.length; itemIndex += 1) {
    const item = rows[itemIndex] || {};
    for (const requirement of requirements) {
      const value = firstPlanBatchValue(item, requirement.keys);
      if (!value) continue;
      const actual = planWordTokens(value).length;
      if (actual === requirement.count) continue;
      const repaired = planRepairTextToWordCount(value, requirement.count, item, originalRequest);
      const updatedKeys = requirement.keys.filter((key) => Object.prototype.hasOwnProperty.call(item, key));
      if (!updatedKeys.length) updatedKeys.push("speech_text");
      if (requirement.keys.includes("voiceover_script") && !updatedKeys.includes("voiceover_script")) {
        updatedKeys.push("voiceover_script");
      }
      if (requirement.keys.includes("speech_text") && !updatedKeys.includes("speech_text")) {
        updatedKeys.push("speech_text");
      }
      for (const key of updatedKeys) item[key] = repaired;
      notes.push(`Item ${itemIndex + 1} ${requirement.label || "script"} repaired from ${actual} to ${requirement.count} words.`);
    }
    rows[itemIndex] = item;
  }
  return { items: rows, repaired: notes.length > 0, notes };
}
function planExactSecondsFromText(...parts) {
  const text = parts.map((part) => String(part || "")).join(" ");
  const exact = text.match(/\b(?:exactly\s*)?(\d{1,4})\s*(?:second|seconds|sec|secs|s)\b/i);
  return exact ? Number(exact[1] || 0) : 0;
}
function clipPlanPromptText(text, maxChars = 900) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  if (!value || value.length <= maxChars) return value;
  return `${value.slice(0, Math.max(0, maxChars - 1)).trim()}...`;
}
function planVideoVisualBriefText(...parts) {
  return parts
    .map((part) => String(part || ""))
    .filter(Boolean)
    .join(" ")
    .replace(/\s+/g, " ")
    .replace(/\b(?:Original request|Source content|Plan anchors|Concrete subject and scene content to render|Generator task|Visual contract|Production detail|Text policy|Timeline)\s*:\s*/gi, " ")
    .replace(/\b(?:strict\s+)?JSON\b/gi, " ")
    .replace(/\b(?:array|object|objects|field|fields|keys|top-level|metadata|schema|record|records)\b/gi, " ")
    .replace(/\b(?:scene_name|narration_text|image_prompt|speech_text|generatedMedia)\b/gi, " ")
    .replace(/\b(?:caption|captions|subtitle|subtitles|title card|readable words|visible text|lettering|typography)\b/gi, " ")
    .replace(/[{}\[\]"`]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}
function planVideoTimelinePrompt(base, seconds = 0, originalRequest = "") {
  const requestText = [base, originalRequest].map((part) => String(part || "")).filter(Boolean).join(" ");
  const lowered = requestText.toLowerCase();
  const hasHistoryShape = /\b(history|historical|timeline|evolution|origin|legacy|through the years)\b/.test(lowered)
    || /\bfrom\s+(?:the\s+)?(?:\d{3,4}s?|\w+\s+era|ancient|past|present|today)\s+to\s+(?:today|present|the\s+\w+\s+era|\d{3,4}s?)\b/.test(lowered);
  const hasLaunchShape = /\b(brand\s+(?:launch|story|campaign|film|video|spot)|launch|product\s+(?:launch|demo|commercial|spot|showcase|film|video)|commercial|advertisement|campaign|promo|showcase|kit)\b/.test(lowered);
  const hasDocumentaryShape = /\b(documentary|micro[- ]documentary|scene[- ]by[- ]scene|episode|reportage|educational)\b/.test(lowered);
  const asksForSequence = /\b(?:timeline|sequence|storyboard|montage|multi[-\s]?shot|(?:\d+|two|three|four|five|several|multiple|many)\s+(?:shots?|scenes?|segments?|beats?)|shots|scenes|segments|beats|chapters?|cut(?:s|ting)?|transition(?:s)?)\b/.test(lowered);
  const asksForSingleScene = /\b(?:(?:single|one)[-\s]+(?:shot|scene|take)|one continuous|continuous shot|unbroken|minimal|simple|plain|locked[-\s]?off|static|no cuts?|without cuts?|no transitions?|without transitions?)\b/.test(lowered);
  if ((asksForSingleScene && !asksForSequence) || (!hasHistoryShape && !hasLaunchShape && !hasDocumentaryShape && !asksForSequence)) {
    return "Continuity: follow the prompt explicitly as one continuous requested scene; do not add unrequested objects, characters, readable text, effects, cuts, transitions, or story beats.";
  }
  const subjectHint = hasHistoryShape
    ? "Move chronologically from the earliest requested period to the latest, using era-appropriate locations, clothing, tools, architecture, and symbolic objects."
    : hasLaunchShape
      ? "Build a coherent product or brand story with hero object shots, human-scale usage context, material details, and a clean final reveal."
      : hasDocumentaryShape
        ? "Treat the request as a documentary sequence with observational details, environmental context, and purposeful scene transitions."
        : "Keep every shot anchored to the same requested subject, place, style, and action instead of drifting into unrelated stock footage.";
  if (!seconds) {
    return [
      subjectHint,
      "Shot sequence: establish the setting, introduce the subject, show the requested action or transformation, add one close contextual detail, then resolve on a clear final image.",
    ].join(" ");
  }
  const beatCount = Math.max(1, Math.min(seconds <= 12 ? seconds : Math.ceil(seconds / 2), 12));
  const labels = [
    "wide establishing shot with exact setting and era/style cues",
    "clear reveal of the main subject and its relationship to the request",
    "medium shot of the primary action, process, or transformation",
    "close detail shot of meaningful objects, materials, symbols, or environment",
    "second angle that adds context without changing topic",
    "motion beat with camera movement following the subject or action",
    "human or environmental reaction that clarifies scale and mood",
    "visual contrast beat that shows change, stakes, or progression",
    "polished hero shot with strong composition and clean lighting",
    "contextual insert that reinforces the requested facts or theme without text",
    "build toward resolution with coherent movement and stable continuity",
    "final resolved shot that clearly satisfies the request",
  ];
  const beats = [];
  for (let index = 0; index < beatCount; index += 1) {
    const start = Math.round((seconds * index) / beatCount);
    const end = Math.round((seconds * (index + 1)) / beatCount);
    beats.push(`${start}-${end}s: ${labels[index] || labels[labels.length - 1]}.`);
  }
  return [subjectHint, `Timeline: ${beats.join(" ")}`].join("\n");
}
function enhancePlanMediaPrompt({ lane, prompt, item, itemIndex = 0, batchTotal = 0, step, contextText = "", originalRequest = "" } = {}) {
  const normalizedLane = String(lane || "").trim().toLowerCase();
  const base = String(prompt || "").trim();
  if (!planLanePromptNeedsEnhancement(normalizedLane)) return base;
  const subject = planBatchSubjectName(item || {}, batchTotal ? `Item ${itemIndex + 1}` : "");
  const subjectContext = planBatchSubjectContext(item || {});
  const sourceText = clipPlanPromptText(planBatchScalar(item?.text), 900);
  const purpose = String(step?.purpose || "").trim();
  if (["ltx", "sulphur", "10eros", "wan"].includes(normalizedLane)) {
    const seconds = planExactSecondsFromText(base, purpose, originalRequest);
    const visualContext = clipPlanPromptText(
      planVideoVisualBriefText(sourceText, contextText, originalRequest),
      seconds ? 1300 : 1800,
    );
    return [
      `Cinematic visual brief: ${visualContext || planVideoVisualBriefText(base) || base}.`,
      `Render ${seconds ? `exactly ${seconds} seconds of ` : ""}image-only moving footage as one coherent scene unless the prompt explicitly asks for a sequence.`,
      `Creative task: ${planVideoVisualBriefText(base) || base}.`,
      subject ? `Primary subject: ${subject}${subjectContext ? ` (${subjectContext})` : ""}.` : "",
      "Follow the prompt explicitly without adding other elements; preserve requested inclusions, omissions, duration, subject attributes, camera style, and setting.",
      "Image-only camera footage: stable subject identity, intentional camera motion, grounded lighting, clear foreground/background, no graphic design layer, no UI layer, and no split-screen or contact-sheet layout.",
      "Avoid generated on-screen text unless the request explicitly needs readable writing: do not add readable overlays, logos, watermarks, credits, lower thirds, signs, labels, or random writing-like marks.",
      "Show prompt-relevant visible details first: setting, era/style, lighting, materials, foreground/background elements, lens feel, shot scale, motion path, subject action, and final resolved image.",
      planVideoTimelinePrompt(base, seconds, originalRequest),
    ].filter(Boolean).join("\n\n");
  }
  if (["ideogram", "hidream", "chroma", "zimage", "krea"].includes(normalizedLane)) {
    const contextAnchor = clipPlanPromptText(contextText, 700);
    return [
      base,
      subject ? `Subject anchor: ${subject}${subjectContext ? ` (${subjectContext})` : ""}.` : "",
      sourceText ? `Source context: ${sourceText}` : "",
      contextAnchor ? `Plan anchors: ${contextAnchor}` : "",
      batchTotal > 1
        ? `Batch variation requirement: this is item ${itemIndex + 1} of ${batchTotal}; make it materially different from the others through at least three simultaneous changes across pose/object arrangement, camera angle, crop, setting/scenery, lighting, action/mood, foreground/background depth, color emphasis, contextual props, and composition while preserving the requested style and identity.`
        : "Composition requirement: make the image specific, polished, and visually inspectable with a clear focal subject, intentional framing, and grounded contextual details.",
    ].filter(Boolean).join("\n\n");
  }
  if (normalizedLane === "music") {
    const contextAnchor = clipPlanPromptText(contextText, 650);
    return [
      base,
      contextAnchor ? `Plan anchors: ${contextAnchor}` : "",
      "Arrange as a complete production cue with clear genre, tempo feel, instrumentation, intro/development/ending, mix texture, and emotional arc. Avoid vocals unless explicitly requested.",
    ].filter(Boolean).join("\n\n");
  }
  if (normalizedLane === "sfx") {
    const contextAnchor = clipPlanPromptText(contextText, 650);
    return [
      base,
      contextAnchor ? `Plan anchors: ${contextAnchor}` : "",
      "Design as a layered sound cue with foreground action, background ambience, spatial distance, dynamics, timing, texture, and a clean beginning and ending.",
    ].filter(Boolean).join("\n\n");
  }
  return base;
}
function appendStudioExecutorNote(assistantMessage, title, details = {}) {
  if (!assistantMessage) return;
  assistantMessage.reasoningLabel = "Executor notes";
  assistantMessage.thinkingExpanded = false;
  assistantMessage.thinkingLive = false;
  assistantMessage.thinkingDone = true;
  const lines = [`### ${title}`];
  for (const [key, value] of Object.entries(details || {})) {
    const text = typeof value === "string" ? value.trim() : JSON.stringify(value, null, 2);
    if (!text) continue;
    lines.push(`**${key}:**\n${text}`);
  }
  const block = lines.join("\n\n");
  assistantMessage.reasoningText = [String(assistantMessage.reasoningText || "").trim(), block]
    .filter(Boolean)
    .join("\n\n");
}
function imageStudioOutputNames(output) {
  const rows = Array.isArray(output)
    ? output
    : output && typeof output === "object"
      ? [output]
      : [];
  return rows
    .map((item) => String(item?.name || item?.filename || item?.relative_path || item?.url || "").trim())
    .filter(Boolean);
}
function backendPlanCompletionText(generation = {}) {
  const detail = String(generation?.detail || "Backend Plan Mode production complete.").trim();
  const names = imageStudioOutputNames(generation?.output || null);
  const outputLine = names.length
    ? `Output: ${names.slice(0, 3).join(", ")}${names.length > 3 ? ` and ${names.length - 3} more` : ""}.`
    : "";
  return [detail, outputLine].filter(Boolean).join("\n\n");
}
function studioConversationTitleFromPlan(plan = {}, fallbackText = "") {
  const title = sanitizeConversationTitle(plan?.title || "");
  if (!title || isWeakAutoConversationTitle(title)) return "";
  const titleWords = new Set(
    title
      .toLowerCase()
      .split(/[^a-z0-9]+/i)
      .filter((word) => word.length >= 4),
  );
  if (!titleWords.size) return "";
  const promptWords = new Set(
    String(fallbackText || "")
      .toLowerCase()
      .split(/[^a-z0-9]+/i)
      .filter((word) => word.length >= 4),
  );
  for (const word of titleWords) {
    if (promptWords.has(word)) return title;
  }
  return "";
}
function shouldAutoNameStudioConversation() {
  if (!(chatState.messages || []).length) return true;
  const conversation = activeChatConversation();
  return Boolean(
    conversation?.autoNamed &&
      isWeakAutoConversationTitle(chatConversationTitle(conversation)),
  );
}
async function sendImageStudioMessage(lane, text, attachments = []) {
  if (!text) return setChatMsg("Enter a generation prompt.");
  const backendPlanMode = lane === "plan-backend";
  const input = $("chatInput");
  const shouldAutoNameConversation = shouldAutoNameStudioConversation();
  const messageCreatedAt = Date.now();
  const userMessage = {
    role: "user",
    text,
    attachments,
    inputTokensEstimate: estimateTextTokenCount(text),
    inputTokensApprox: true,
    createdAt: messageCreatedAt,
  };
  const assistantMessage = {
    role: "assistant",
    text: backendPlanMode ? "Starting backend Plan Mode..." : "Preparing AI Studio generation...",
    modelLabel: $("chatStudioLane")?.selectedOptions?.[0]?.textContent || "AI Studio",
    studioLane: lane,
    studioPrompt: text,
    createdAt: messageCreatedAt,
    generationStartedAt: messageCreatedAt,
  };
  chatState.messages = [...(chatState.messages || []), userMessage, assistantMessage];
  chatState.busy = true;
  if (input) input.value = "";
  persistChatConversationState();
  if (shouldAutoNameConversation) {
    applyConversationTitle(chatState.activeConversationId, "", text, attachments);
  }
  renderChatUi();
  renderChatTranscript(true, { reason: "user" });
  const assistantIndex = chatState.messages.length - 1;
  try {
    const priorPrompt = [...(chatState.messages || [])]
      .slice(0, Math.max(0, assistantIndex - 1))
      .reverse()
      .find(
        (message) =>
          message?.role === "assistant" &&
          message?.studioLane === lane &&
          message?.studioPrompt &&
          message?.generatedMedia,
      )?.studioPrompt || "";
    const generationPrompt = backendPlanMode ? text : enhancePlanMediaPrompt({
      lane,
      prompt: text,
      originalRequest: text,
    });
    appendStudioExecutorNote(assistantMessage, backendPlanMode ? "Backend Plan Mode submission" : "Direct generation submission", {
      Lane: lane,
      "Original prompt": text,
      "Enhanced prompt sent": generationPrompt,
      Attachments: attachments.length
        ? attachments.map((row) => `${row.kind || "file"}:${row.name || "attachment"}`).join(", ")
        : "none",
    });
    updateLiveChatMessageDom(assistantIndex, true);
    persistChatConversationState();
    const response = await fetch(backendPlanMode ? "/admin/ai-studio/backend-plan" : "/admin/ai-studio/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: backendPlanMode
        ? JSON.stringify({ prompt: text, attachments })
        : JSON.stringify({ lane, prompt: generationPrompt, prior_prompt: priorPrompt, attachments }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload?.ok) throw new Error(payload?.error || "AI Studio generation failed to start.");
    activeImageStudioJobId = String(payload?.generation?.id || "");
    while (activeImageStudioJobId) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      const statusResponse = await fetch(
        `/admin/ai-studio/generation?job_id=${encodeURIComponent(activeImageStudioJobId)}&_=${Date.now()}`,
        { cache: "no-store" },
      );
      const statusPayload = await statusResponse.json().catch(() => ({}));
      if (!statusResponse.ok || !statusPayload?.ok)
        throw new Error(statusPayload?.error || "AI Studio status check failed.");
      const generation = statusPayload.generation || {};
      assistantMessage.text = String(generation.detail || "Generating...");
      if (generation.status === "success") {
        assistantMessage.text = backendPlanMode ? backendPlanCompletionText(generation) : "";
        assistantMessage.studioPrompt = priorPrompt
          ? `${priorPrompt}\n\nRequested refinement: ${text}`
          : text;
        assistantMessage.generatedMedia = generation.output || null;
        appendStudioExecutorNote(assistantMessage, backendPlanMode ? "Backend Plan Mode output" : "Direct generation output", {
          Lane: lane,
          Output: JSON.stringify(generation.output || null, null, 2),
        });
        activeImageStudioJobId = "";
        break;
      }
      if (generation.status === "failed")
        throw new Error(generation.error || generation.detail || "AI Studio generation failed.");
      if (generation.status === "cancelled") {
        assistantMessage.text = "Generation cancelled.";
        activeImageStudioJobId = "";
        break;
      }
      updateLiveChatMessageDom(assistantIndex, true);
      setChatMsg(generation.detail || "AI Studio is generating...");
    }
    persistChatConversationState();
    renderChatTranscript(true, { reason: "complete" });
    setChatMsg(assistantMessage.generatedMedia ? (backendPlanMode ? "Backend Plan Mode complete." : "AI Studio generation complete.") : assistantMessage.text);
  } catch (error) {
    assistantMessage.text = `AI Studio error: ${String(error?.message || error)}`;
    activeImageStudioJobId = "";
    persistChatConversationState();
    renderChatTranscript(true, { reason: "error" });
    setChatMsg(assistantMessage.text, "error");
  } finally {
    markAssistantGenerationFinished(assistantMessage);
    chatState.busy = false;
    await flushChatConversationStateNow();
    renderChatUi();
  }
}
async function executePlannedStudioMessage(confirmText, plan, attachments = [], execution = {}) {
  const steps = Array.isArray(plan?.steps) && plan.steps.length
    ? plan.steps
    : [{ lane: plan?.lane, label: plan?.label, prompt: plan?.prompt }];
  if (!steps.length) return setChatMsg("No executable Plan Mode plan is available.", "error");
  if (execution.assistantMessage && !Array.isArray(execution.assistantMessage.generatedMedia)) {
    execution.assistantMessage.generatedMedia = [];
  }
  const input = $("chatInput");
  const messageCreatedAt = Date.now();
  const userMessage = {
    role: "user",
    text: confirmText || "Confirm plan",
    attachments,
    inputTokensEstimate: estimateTextTokenCount(confirmText || "Confirm plan"),
    inputTokensApprox: true,
    createdAt: messageCreatedAt,
  };
  const resumable = execution.assistantMessage ? null : latestResumableStudioExecution(plan);
  const resumedResults = Array.isArray(resumable?.studioPlanResults)
    ? structuredClone(resumable.studioPlanResults)
    : [];
  const resumedMedia = Array.isArray(resumable?.generatedMedia)
    ? structuredClone(resumable.generatedMedia)
    : [];
  const assistantMessage = execution.assistantMessage || {
    role: "assistant",
    text: "Acknowledged, executing plan mode...",
    modelLabel: "Plan Mode",
    studioLane: "plan-execution",
    studioPrompt: steps.map((step) => step?.prompt || "").join("\n\n"),
    interactivePlan: plan,
    generatedMedia: resumedMedia,
    studioPlanResults: resumedResults,
    createdAt: messageCreatedAt,
    generationStartedAt: messageCreatedAt,
  };
  if (!execution.assistantMessage) {
    chatState.messages = [...(chatState.messages || []), userMessage, assistantMessage];
  }
  chatState.busy = true;
  if (input) input.value = "";
  persistChatConversationState();
  renderChatUi();
  renderChatTranscript(true, { reason: "user" });
  const assistantIndex = execution.assistantIndex ?? (chatState.messages.length - 1);
  const stepResults = resumedResults;
  const originalRequestText = String(plan?.original_request || plan?.request || plan?.prompt || assistantMessage.studioPrompt || "").trim();
  const planStepExpectedUnits = (step, index) => {
    if (!step?.batch) return 1;
    const sourceStep = Math.max(0, Number(step?.batch?.source_step || 0) - 1);
    const sourceItems = Array.isArray(stepResults[sourceStep]?.items) ? stepResults[sourceStep].items : [];
    const selectedItems = planBatchItemsForStepDescriptor(step, sourceItems);
    const batchCount = Number(step?.batch?.count || 0) || 0;
    return Math.max(1, selectedItems.length || batchCount || 1);
  };
  const planStepIsComplete = (step, index) => {
    const result = stepResults[index];
    if (!result) return false;
    if (String(step?.lane || "").trim().toLowerCase() === "text") {
      const text = String(result.text || "").trim();
      if (!text || result.kind !== "text") return false;
      if (step?.batch) {
        const items = Array.isArray(result.items) ? result.items : [];
        return items.length >= planStepExpectedUnits(step, index);
      }
      return true;
    }
    if (result.kind !== "media") return false;
    const outputs = Array.isArray(result.outputs) ? result.outputs : [];
    return outputs.length >= planStepExpectedUnits(step, index);
  };
  const planStepContextText = (stepIndex, options = {}) => {
    const compact = !!options.compact;
    const maxResultChars = Math.max(400, Number(options.maxResultChars || (compact ? 1800 : 4000)));
    const maxItemChars = Math.max(120, Number(options.maxItemChars || 260));
    const contextParts = [];
    const originalRequest = String(plan?.original_request || "").trim();
    if (originalRequest) contextParts.push(`Original request:\n${originalRequest}`);
    const priorStepSummaries = stepResults
      .slice(0, Math.max(0, stepIndex))
      .map((result, priorIndex) => {
        const priorStep = steps[priorIndex] || {};
        const priorHeading = `Step ${priorIndex + 1} (${String(priorStep?.label || priorStep?.lane || "step")})`;
        const priorPrompt = String(priorStep?.prompt || "").trim();
        if (!result) return "";
        if (result.kind === "text" && result.text) {
          if (compact && Array.isArray(result.items) && result.items.length) {
            const compactItems = result.items.slice(0, 12).map((item, itemIndex) => {
              const name = planBatchSubjectName(item || {}, `Item ${itemIndex + 1}`);
              const dates = planBatchSubjectContext(item || {});
              const copy = planBatchScalar(item?.text || item?.speech_text || item?.summary || item?.description).slice(0, maxItemChars);
              const visual = planBatchScalar(item?.image_prompt || item?.visual_prompt || item?.prompt).slice(0, maxItemChars);
              return [
                name,
                dates ? `(${dates})` : "",
                copy ? `- narration/content: ${copy}` : "",
                visual ? `visual: ${visual}` : "",
              ].filter(Boolean).join(" ");
            });
            return `${priorHeading} source items:\n${compactItems.join("\n")}`;
          }
          return `${priorHeading} prompt:\n${priorPrompt}\nResult:\n${String(result.text || "").trim().slice(0, maxResultChars)}`;
        }
        const outputs = Array.isArray(result.outputs) ? result.outputs : [];
        if (!outputs.length) return "";
        const labels = outputs
          .map(({ item, output } = {}) =>
            planBatchSubjectName(item || {}, "") ||
            String(output?.name || output?.filename || output?.path || "").trim(),
          )
          .filter(Boolean)
          .slice(0, 16);
        const outputText = labels.length ? `\nOutputs: ${labels.join(", ")}` : "";
        return compact
          ? `${priorHeading}${outputText}`
          : `${priorHeading} prompt:\n${priorPrompt}${outputText}`;
      })
      .filter(Boolean);
    if (priorStepSummaries.length) {
      contextParts.push(`Completed earlier steps:\n${priorStepSummaries.join("\n")}`);
    }
    return contextParts.join("\n\n").trim();
  };
  const planStepAttachmentKinds = (lane) => {
    const normalizedLane = String(lane || "").trim().toLowerCase();
    if (normalizedLane === "voice") return new Set(["audio"]);
    if (["ltx", "sulphur", "10eros", "wan"].includes(normalizedLane)) return new Set(["image"]);
    return new Set();
  };
  const blobToDataUrl = (blob) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Failed to read generated media."));
    reader.readAsDataURL(blob);
  });
  const planStepAttachmentFromOutput = async (output, lane) => {
    const allowedKinds = planStepAttachmentKinds(lane);
    if (!allowedKinds.size) return null;
    const kind = String(output?.kind || "").trim().toLowerCase();
    if (!allowedKinds.has(kind)) return null;
    const url = String(output?.url || "").trim();
    if (!url) return null;
    try {
      if (/^data:/i.test(url)) {
        return {
          kind,
          name: String(output?.name || "").trim() || `${kind}-attachment`,
          url,
        };
      }
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) return null;
      const blob = await response.blob();
      const dataUrl = await blobToDataUrl(blob);
      if (!/^data:/i.test(dataUrl)) return null;
      return {
        kind,
        name: String(output?.name || "").trim() || `${kind}-attachment`,
        url: dataUrl,
      };
    } catch (error) {
      return null;
    }
  };
  const planStepAttachments = async (step, stepIndex, itemIndex, batchItems = []) => {
    const allowedKinds = planStepAttachmentKinds(step?.lane);
    if (!allowedKinds.size) return [];
    const collected = [];
    const seen = new Set();
    const addAttachment = (attachment) => {
      const row = attachment && typeof attachment === "object" ? attachment : null;
      if (!row) return;
      const kind = String(row.kind || "").trim().toLowerCase();
      const url = String(row.url || "").trim();
      if (!kind || !url || !allowedKinds.has(kind)) return;
      const key = `${kind}\u0000${url}`;
      if (seen.has(key)) return;
      seen.add(key);
      collected.push({
        ...row,
        kind,
        url,
      });
    };
    const dependencyIndexes = Array.isArray(step?.depends_on) ? step.depends_on : [];
    for (const dependencyIndex of dependencyIndexes) {
      const dependencyResult = stepResults[Math.max(0, Number(dependencyIndex || 0) - 1)] || null;
      const dependencyOutputs = Array.isArray(dependencyResult?.outputs) ? dependencyResult.outputs : [];
      if (!dependencyOutputs.length) continue;
      let selectedOutputs = [];
      if (step?.batch && batchItems.length) {
        const matching = dependencyOutputs.find((entry, depIndex) =>
          depIndex === itemIndex || entry?.item === batchItems[itemIndex],
        );
        if (matching?.output) selectedOutputs = [matching.output];
      }
      if (!selectedOutputs.length) {
        const usableDependencyOutputs = dependencyOutputs
          .map((entry) => entry?.output)
          .filter((output) =>
            output &&
            allowedKinds.has(String(output?.kind || "").trim().toLowerCase())
          );
        if (usableDependencyOutputs.length === 1) {
          selectedOutputs = [usableDependencyOutputs[0]];
        }
      }
      for (const output of selectedOutputs) {
        const attachment = await planStepAttachmentFromOutput(output, step?.lane);
        if (attachment) addAttachment(attachment);
      }
    }
    for (const attachment of attachments) {
      addAttachment(attachment);
    }
    return collected;
  };
  try {
    for (let stepIndex = 0; stepIndex < steps.length; stepIndex += 1) {
      const step = steps[stepIndex] || {};
      const lane = String(step.lane || "").trim().toLowerCase();
      const plannedPrompt = String(step.prompt || "").trim();
      if (!lane || !plannedPrompt) throw new Error(`Plan step ${stepIndex + 1} is incomplete.`);
      assistantMessage.text = planExecutionProgressText(plan, steps, stepResults, stepIndex, 0, [], { status: "submitting" });
      commitStudioPlanProgress(assistantIndex);
      if (lane === "text") {
        if (stepResults[stepIndex]?.kind === "text" && stepResults[stepIndex]?.text) {
          assistantMessage.studioPlanResults = stepResults;
          commitStudioPlanProgress(assistantIndex, { render: true });
          continue;
        }
        const isDirectorRuntime = (row) =>
          String(row?.id || row?.instance_id || "").toUpperCase() === "STUDIO_DIRECTOR" ||
          String(row?.selector || row?.mode || "") === "ai-studio/director";
        const selectedRuntime = activeChatRuntime();
        const nonDirectorRuntime = activeChatPresets().find((row) => !isDirectorRuntime(row)) || null;
        const directorRuntime = activeChatPresets().find((row) => isDirectorRuntime(row)) || null;
        const runtime =
          selectedRuntime && !isDirectorRuntime(selectedRuntime)
            ? selectedRuntime
            : nonDirectorRuntime || selectedRuntime || directorRuntime || null;
        const requestBody = {
          conversation_id: String(chatState.activeConversationId || ""),
          instance_id: runtime?.id || runtime?.instance_id || "STUDIO_DIRECTOR",
          mode: runtime?.selector || runtime?.mode || "ai-studio/director",
          model: runtime?.served_model_name || runtime?.model_id || "qwen3.5-4b-uncensored",
          messages: [{ role: "user", content: plannedPrompt }],
          params: {
            ...chatState.params,
            max_tokens: Math.max(12000, Number(chatState.params?.max_tokens || 0)),
          },
          api_preset: chatState.apiPresetName || "",
        };
        let textResult = "";
        let items = [];
        let sourceRepairNote = "";
        const feedsBatch = steps.some((candidate) => Number(candidate?.batch?.source_step || 0) === stepIndex + 1);
        const expectedBatchCount = feedsBatch
          ? planBatchExpectedCountForSource(steps, stepIndex + 1, plannedPrompt)
          : 0;
        requestBody.messages = [{
          role: "user",
          content: feedsBatch
            ? planSourceExecutionPrompt(plannedPrompt, expectedBatchCount)
            : plannedPrompt,
        }];
        requestBody.params.max_tokens = Math.max(
          expectedBatchCount >= 20 ? 20000 : 12000,
          Number(chatState.params?.max_tokens || 0),
        );
        for (let textAttempt = 0; textAttempt < 3; textAttempt += 1) {
          const textResponse = await fetch("/admin/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestBody),
          });
          const textPayload = await textResponse.json().catch(() => ({}));
          if (!textResponse.ok || !textPayload?.ok)
            throw new Error(textPayload?.error || `Plan text step ${stepIndex + 1} failed.`);
          textResult = String(
            textPayload?.response?.choices?.[0]?.message?.content ||
            textPayload?.response?.choices?.[0]?.text ||
            "",
          ).trim();
          applyAssistantGenerationMetrics(assistantMessage, textPayload);
          if (!textResult) throw new Error(`Plan text step ${stepIndex + 1} returned no content.`);
          let parseError = null;
          let validationError = "";
          try {
            items = feedsBatch ? parsePlanBatchItems(textResult) : [];
            if (feedsBatch) items = normalizePlanBatchItems(items, plannedPrompt, originalRequestText);
          } catch (error) {
            items = [];
            parseError = error;
          }
          if (!parseError && feedsBatch) {
            validationError = planBatchWordCountError(items, plannedPrompt, originalRequestText);
          }
          if (parseError && textAttempt < 2) {
            assistantMessage.text = `${planExecutionProgressText(plan, steps, stepResults, stepIndex, 0, [], { status: "preparing" })}\nThe source returned unparsable batch JSON. Retrying the structured text step before media generation...`;
            commitStudioPlanProgress(assistantIndex);
            requestBody.messages = [{
              role: "user",
              content: `${planSourceExecutionPrompt(plannedPrompt, expectedBatchCount)}\n\nCORRECTION: The previous response could not be parsed as one complete strict JSON array (${String(parseError?.message || parseError)}). Return the complete array again, with no Markdown fences, no leading language tag, no prose, and no truncation.`,
            }];
            continue;
          }
          if (parseError) throw parseError;
          if (validationError && textAttempt < 2) {
            assistantMessage.text = `${planExecutionProgressText(plan, steps, stepResults, stepIndex, 0, [], { status: "preparing" })}\nThe source missed an exact script word-count constraint. Retrying the structured text step before media generation...`;
            commitStudioPlanProgress(assistantIndex);
            requestBody.messages = [{
              role: "user",
              content: `${planSourceExecutionPrompt(plannedPrompt, expectedBatchCount)}\n\nCORRECTION: The previous response violated an exact word-count constraint (${validationError}). Rewrite the affected generated script fields so they contain exactly the requested number of spoken words while preserving the requested objects, order, field names, image prompts, and factual constraints. Output only the corrected strict JSON array.`,
            }];
            continue;
          }
          if (validationError) {
            const repairResult = repairPlanBatchWordCounts(items, plannedPrompt, originalRequestText);
            if (repairResult.repaired) {
              items = repairResult.items;
              textResult = JSON.stringify(items);
              sourceRepairNote = repairResult.notes.join("\n");
              validationError = planBatchWordCountError(items, plannedPrompt, originalRequestText);
            }
          }
          if (validationError) throw new Error(`Plan text step ${stepIndex + 1} returned invalid source content: ${validationError}`);
          if (!expectedBatchCount || items.length === expectedBatchCount || textAttempt > 0) break;
          assistantMessage.text = `${planExecutionProgressText(plan, steps, stepResults, stepIndex, 0, [], { status: "preparing" })}\nThe source returned ${items.length}/${expectedBatchCount} batch items. Retrying the structured text step before media generation...`;
          commitStudioPlanProgress(assistantIndex);
          requestBody.messages = [{
            role: "user",
            content: `${planSourceExecutionPrompt(plannedPrompt, expectedBatchCount)}\n\nCORRECTION: The previous response contained ${items.length}/${expectedBatchCount} objects. Return exactly ${expectedBatchCount} objects that satisfy the original request. Preserve required duplicates, separate terms, separate editions, ordered entries, and distinct identities whenever the request implies them. Do not merge, omit, summarize, or add unrelated entries. Output only the corrected strict JSON array.`,
          }];
        }
        if (feedsBatch && !items.length) throw new Error(`Plan text step ${stepIndex + 1} returned no batch items.`);
        if (expectedBatchCount && items.length !== expectedBatchCount) {
          throw new Error(`Plan text step ${stepIndex + 1} returned ${items.length}/${expectedBatchCount} batch items after retry.`);
        }
        stepResults[stepIndex] = { kind: "text", text: textResult, items };
        assistantMessage.studioPlanResults = stepResults;
        appendStudioExecutorNote(assistantMessage, `Step ${stepIndex + 1} source output`, {
          Lane: "text",
          Prompt: requestBody.messages?.[0]?.content || plannedPrompt,
          Repair: sourceRepairNote,
          Output: textResult,
        });
        assistantMessage.text = `${planExecutionProgressText(plan, steps, stepResults, stepIndex, 0, [], { status: "success" })}\n${textResult}`;
        commitStudioPlanProgress(assistantIndex, { render: true });
        continue;
      }
      const sourceStep = Math.max(0, Number(step?.batch?.source_step || 0) - 1);
      const sourceBatchItems = Array.isArray(stepResults[sourceStep]?.items) ? stepResults[sourceStep].items : [];
      const batchItems = step?.batch ? planBatchItemsForStepDescriptor(step, sourceBatchItems) : [null];
      if (step?.batch && !batchItems.length) throw new Error(`Plan step ${stepIndex + 1} has no batch items from step ${sourceStep + 1}.`);
      const outputs = Array.isArray(stepResults[stepIndex]?.outputs)
        ? stepResults[stepIndex].outputs
        : [];
      if (outputs.length >= batchItems.length) {
        assistantMessage.studioPlanResults = stepResults;
        commitStudioPlanProgress(assistantIndex, { render: true });
        continue;
      }
      for (let itemIndex = outputs.length; itemIndex < batchItems.length;) {
        const useIdeogramCandidateSheet =
          lane === "ideogram" &&
          step?.batch &&
          batchItems.length >= 10;
        const workItems = [batchItems[itemIndex]];
        const item = workItems[0];
        let resolvedPrompt = expandPlanBatchPrompt(plannedPrompt, item || {});
        if (lane === "ideogram" && step?.batch) {
          const identity = planBatchSubjectName(item || {}, `Subject ${itemIndex + 1}`);
          const context = planBatchSubjectContext(item || {});
          const direction = expandPlanBatchPrompt(plannedPrompt, item || {});
          resolvedPrompt = [
            `Create the requested image for "${identity}"${context ? ` (${context})` : ""}.`,
            "Make this item visually and semantically distinct from every other item in the same batch; change at least three major axes at once, such as pose, viewpoint, crop, setting/scenery, lighting, action, foreground/background depth, color emphasis, contextual props, or composition, while preserving the requested style.",
            "If this item names a real public or historical subject, use recognizable public-reference likenesses and distinctive attributes instead of a generic substitute.",
            "Use a neutral educational/editorial framing where relevant, with no advocacy or unsafe content unless explicitly requested and allowed.",
            direction,
          ].join(" ");
        }
        resolvedPrompt = resolvedPrompt.replace(
          /\[Insert text from Step (\d+) here\]/gi,
          (_match, value) => String(stepResults[Math.max(0, Number(value) - 1)]?.text || ""),
        );
        const isVideoLane = ["ltx", "sulphur", "10eros", "wan"].includes(lane);
        const isEnhancedMediaLane = planLanePromptNeedsEnhancement(lane);
        const contextText = planStepContextText(stepIndex, {
          compact: isEnhancedMediaLane,
          maxResultChars: isVideoLane ? 1200 : isEnhancedMediaLane ? 900 : 4000,
          maxItemChars: isVideoLane ? 180 : isEnhancedMediaLane ? 160 : 320,
        });
        if (contextText && !planLaneSpeaksPrompt(lane) && !isEnhancedMediaLane && (stepIndex > 0 || (Array.isArray(step?.depends_on) && step.depends_on.length))) {
          resolvedPrompt = [
            resolvedPrompt,
            "Use the completed plan context exactly and keep the same named subjects, dates, visible labels, ordering, and requested duration.",
            contextText,
          ].join("\n\n");
        }
        const batchProgress = step?.batch ? ` item ${itemIndex + 1}/${batchItems.length}` : "";
        const expandedPrompt = resolvedPrompt;
        resolvedPrompt = enhancePlanMediaPrompt({
          lane,
          prompt: resolvedPrompt,
          item: item || {},
          itemIndex,
          batchTotal: batchItems.length,
          step,
          contextText,
          originalRequest: originalRequestText,
        });
        const generationOptions =
          useIdeogramCandidateSheet
            ? {
                width: 1024,
                height: 1024,
                steps: 8,
                candidate_identity: planBatchSubjectName(item || "", ""),
              }
            : step?.batch &&
              batchItems.length >= 10 &&
            ["ideogram", "chroma", "zimage", "krea"].includes(lane)
            ? { width: 512, height: 512, steps: 6 }
            : {};
        if (
          lane === "ideogram" &&
          !useIdeogramCandidateSheet &&
          planIdeogramRequestsSingleRender(resolvedPrompt, plannedPrompt, originalRequestText)
        ) {
          generationOptions.candidate_grid = false;
          generationOptions.single_image = true;
        }
        if (lane === "kokoro" && step?.batch) {
          generationOptions.voice = planKokoroVoiceForItem(item || {}, itemIndex, originalRequestText);
        }
        const stepAttachments = await planStepAttachments(step, stepIndex, itemIndex, batchItems);
        appendStudioExecutorNote(assistantMessage, `Step ${stepIndex + 1}${batchProgress || ""} submission`, {
          Lane: lane,
          "Plan prompt": plannedPrompt,
          "Expanded prompt": expandedPrompt,
          "Enhanced prompt sent": resolvedPrompt,
          Options: JSON.stringify(generationOptions, null, 2),
          Attachments: stepAttachments.length
            ? stepAttachments.map((row) => `${row.kind || "file"}:${row.name || "attachment"}`).join(", ")
            : "none",
        });
        commitStudioPlanProgress(assistantIndex, { render: true });
        const response = await fetch("/admin/ai-studio/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            lane,
            prompt: resolvedPrompt,
            options: generationOptions,
            attachments: stepAttachments,
          }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload?.ok) throw new Error(payload?.error || `Plan step ${stepIndex + 1}${batchProgress} failed to start.`);
        activeImageStudioJobId = String(payload?.generation?.id || "");
        assistantMessage.text = planExecutionProgressText(plan, steps, stepResults, stepIndex, itemIndex, batchItems, { status: "running" });
        commitStudioPlanProgress(assistantIndex);
        while (activeImageStudioJobId) {
          await new Promise((resolve) => setTimeout(resolve, 1500));
          const statusResponse = await fetch(
            `/admin/ai-studio/generation?job_id=${encodeURIComponent(activeImageStudioJobId)}&_=${Date.now()}`,
            { cache: "no-store" },
          );
          const statusPayload = await statusResponse.json().catch(() => ({}));
          if (!statusResponse.ok || !statusPayload?.ok)
            throw new Error(statusPayload?.error || "AI Studio status check failed.");
          const generation = statusPayload.generation || {};
          const progressText = planExecutionProgressText(plan, steps, stepResults, stepIndex, itemIndex, batchItems, generation);
          assistantMessage.text = progressText;
          if (generation.status === "success") {
            if (generation.output) {
              const generatedOutputs = Array.isArray(generation.output?.items)
                ? generation.output.items
                : [generation.output];
              if (useIdeogramCandidateSheet && generatedOutputs.length !== 1) {
                throw new Error(
                  `Ideogram candidate sheet returned ${generatedOutputs.length}/1 selected image.`,
                );
              }
              generatedOutputs.forEach((output, offset) => {
                assistantMessage.generatedMedia.push(output);
                outputs.push({ item: workItems[offset] || item, output });
              });
              appendStudioExecutorNote(assistantMessage, `Step ${stepIndex + 1}${batchProgress || ""} output`, {
                Lane: lane,
                Output: JSON.stringify(generatedOutputs, null, 2),
              });
              stepResults[stepIndex] = { kind: "media", batch: !!step?.batch, outputs };
              assistantMessage.studioPlanResults = stepResults;
              commitStudioPlanProgress(assistantIndex, { render: true });
            }
            activeImageStudioJobId = "";
            break;
          }
          if (generation.status === "failed")
            throw new Error(generation.error || generation.detail || `Plan step ${stepIndex + 1}${batchProgress} failed.`);
          if (generation.status === "cancelled") {
            assistantMessage.text = "Plan execution cancelled.";
            commitStudioPlanProgress(assistantIndex);
            activeImageStudioJobId = "";
            break;
          }
          commitStudioPlanProgress(assistantIndex);
          const progressHeadline = planExecutionProgressHeadline(progressText);
          setChatMsg(generation.detail ? `${progressHeadline} · ${generation.detail}` : progressHeadline, "warning");
        }
        if (/cancelled/i.test(assistantMessage.text)) break;
        itemIndex += 1;
      }
      stepResults[stepIndex] = { kind: "media", batch: !!step?.batch, outputs };
      assistantMessage.studioPlanResults = stepResults;
      commitStudioPlanProgress(assistantIndex, { render: true });
      if (/cancelled/i.test(assistantMessage.text)) break;
    }
    const incompleteStepIndex = steps.findIndex((step, index) => !planStepIsComplete(step, index));
    if (incompleteStepIndex >= 0) {
      const missingStep = steps[incompleteStepIndex] || {};
      throw new Error(
        `Plan execution stopped before step ${incompleteStepIndex + 1} (${String(missingStep.label || missingStep.lane || "step")}) completed.`,
      );
    }
    const planCancelled = /cancelled/i.test(assistantMessage.text);
    if (!planCancelled) assistantMessage.text = "Approved plan executed.";
    await flushChatConversationStateNow();
    renderChatTranscript(true, { reason: "complete" });
    setChatMsg(
      planCancelled
        ? "Plan execution cancelled."
        : assistantMessage.generatedMedia.length
          ? "Approved plan executed."
          : assistantMessage.text,
    );
  } catch (error) {
    assistantMessage.text = `Plan execution error: ${String(error?.message || error)}`;
    activeImageStudioJobId = "";
    await flushChatConversationStateNow();
    renderChatTranscript(true, { reason: "error" });
    setChatMsg(assistantMessage.text, "error");
  } finally {
    markAssistantGenerationFinished(assistantMessage);
    await flushChatConversationStateNow();
    chatState.busy = false;
    renderChatUi();
  }
}
async function sendPlanStudioMessage(text, attachments = []) {
  if (!text) return setChatMsg("Enter a prompt for Plan Mode.");
  const input = $("chatInput");
  const shouldAutoNameConversation = shouldAutoNameStudioConversation();
  const messageCreatedAt = Date.now();
  const userMessage = {
    role: "user",
    text,
    attachments,
    inputTokensEstimate: estimateTextTokenCount(text),
    inputTokensApprox: true,
    createdAt: messageCreatedAt,
  };
  const assistantMessage = {
    role: "assistant",
    text: "Planning AI Studio route...",
    modelLabel: "Plan Mode",
    studioLane: "plan",
    studioPrompt: text,
    createdAt: messageCreatedAt,
    generationStartedAt: messageCreatedAt,
  };
  chatState.messages = [...(chatState.messages || []), userMessage, assistantMessage];
  chatState.busy = true;
  if (input) input.value = "";
  persistChatConversationState();
  renderChatUi();
  renderChatTranscript(true, { reason: "user" });
  const assistantIndex = chatState.messages.length - 1;
  try {
    const previousPlan = [...(chatState.messages || [])]
      .slice(0, Math.max(0, assistantIndex - 1))
      .reverse()
      .find((message) => message?.role === "assistant" && message?.studioLane === "plan" && message?.interactivePlan)
      ?.interactivePlan || null;
    const planResponse = await fetch("/admin/ai-studio/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: text, attachments, previous_plan: previousPlan }),
    });
    const planPayload = await planResponse.json().catch(() => ({}));
    if (!planResponse.ok || !planPayload?.ok) throw new Error(planPayload?.error || "Interactive planner failed.");
    const plan = planPayload.plan || {};
    assistantMessage.interactivePlan = plan;
    applyAssistantGenerationMetrics(assistantMessage, plan.generation_metrics || {});
    assistantMessage.text = formatInteractiveStudioPlanText(plan);
    if (shouldAutoNameConversation) {
      applyConversationTitle(
        chatState.activeConversationId,
        studioConversationTitleFromPlan(plan, text),
        text,
        attachments,
      );
    }
    updateLiveChatMessageDom(assistantIndex, true);
    persistChatConversationState();
    chatState.busy = false;
    persistChatConversationState();
    renderChatTranscript(true, { reason: "complete" });
    setChatMsg(String(plan.action || "").toLowerCase() === "generate" ? "Plan ready. Reply with changes or confirmation to execute in a follow-up." : "Plan Mode returned a chat response.");
    return;
  } catch (error) {
    assistantMessage.text = `Plan Mode error: ${String(error?.message || error)}`;
    activeImageStudioJobId = "";
    if (shouldAutoNameConversation) {
      applyConversationTitle(chatState.activeConversationId, "", text, attachments);
    }
    persistChatConversationState();
    renderChatTranscript(true, { reason: "error" });
    setChatMsg(assistantMessage.text, "error");
  } finally {
    markAssistantGenerationFinished(assistantMessage);
    persistChatConversationState();
    chatState.busy = false;
    renderChatUi();
  }
}
async function sendInteractiveStudioMessage(text, attachments = []) {
  if (!text) return setChatMsg("Enter a prompt for Interactive Mode.");
  const input = $("chatInput");
  const shouldAutoNameConversation = shouldAutoNameStudioConversation();
  const messageCreatedAt = Date.now();
  const userMessage = {
    role: "user",
    text,
    attachments,
    inputTokensEstimate: estimateTextTokenCount(text),
    inputTokensApprox: true,
    createdAt: messageCreatedAt,
  };
  const assistantMessage = {
    role: "assistant",
    text: "Planning Interactive Mode route...",
    modelLabel: "Interactive Mode",
    studioLane: "interactive",
    studioPrompt: text,
    createdAt: messageCreatedAt,
    generationStartedAt: messageCreatedAt,
  };
  chatState.messages = [...(chatState.messages || []), userMessage, assistantMessage];
  chatState.busy = true;
  if (input) input.value = "";
  persistChatConversationState();
  renderChatUi();
  renderChatTranscript(true, { reason: "user" });
  const assistantIndex = chatState.messages.length - 1;
  try {
    const planResponse = await fetch("/admin/ai-studio/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: text, attachments }),
    });
    const planPayload = await planResponse.json().catch(() => ({}));
    if (!planResponse.ok || !planPayload?.ok) throw new Error(planPayload?.error || "Interactive planner failed.");
    const plan = planPayload.plan || {};
    assistantMessage.interactivePlan = plan;
    applyAssistantGenerationMetrics(assistantMessage, plan.generation_metrics || {});
    assistantMessage.text = formatInteractiveStudioPlanText(plan);
    if (shouldAutoNameConversation) {
      applyConversationTitle(
        chatState.activeConversationId,
        studioConversationTitleFromPlan(plan, text),
        text,
        attachments,
      );
    }
    updateLiveChatMessageDom(assistantIndex, true);
    persistChatConversationState();
    if (String(plan.action || "").toLowerCase() !== "generate") {
      setChatMsg("Interactive Mode returned a chat response.");
      return;
    }
    assistantMessage.studioLane = "interactive-execution";
    assistantMessage.modelLabel = "Interactive Mode";
    await executePlannedStudioMessage("", plan, attachments, { assistantMessage, assistantIndex });
    return;
  } catch (error) {
    assistantMessage.text = `Interactive Mode error: ${String(error?.message || error)}`;
    activeImageStudioJobId = "";
    if (shouldAutoNameConversation) {
      applyConversationTitle(chatState.activeConversationId, "", text, attachments);
    }
    persistChatConversationState();
    renderChatTranscript(true, { reason: "error" });
    setChatMsg(assistantMessage.text, "error");
  } finally {
    markAssistantGenerationFinished(assistantMessage);
    persistChatConversationState();
    chatState.busy = false;
    renderChatUi();
  }
}
async function sendChatMessage() {
  if (chatState.busy) {
    if (activeImageStudioJobId) {
      fetch("/admin/ai-studio/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: activeImageStudioJobId }),
      }).catch(() => {});
      setChatMsg("Cancelling AI Studio generation...");
      return;
    }
    stopChatGeneration();
    return;
  }
  if (chatHydrationPending() || !chatStateHydrated) {
    setChatMsg("Loading conversations...");
    try {
      await hydrateChatState();
    } catch (error) {
      setChatMsg(error?.message || "Failed to load conversations.", "error");
      return;
    }
  }
  if (chatBenchmarkLocked()) {
    return setChatMsg("Model Scores benchmarking is running. Cancel the benchmark before sending chat messages.", "error");
  }
  const runtime = activeChatRuntime();
  const input = $("chatInput");
  const text = String(input?.value || "").trim();
  const pendingAttachments = [...(chatState.attachments || [])];
  const studioLane = String($("chatStudioLane")?.value || "");
  if (studioLane) {
    if (studioLane === "plan") {
      if (!text) return setChatMsg("Enter a prompt for Plan Mode.");
      chatState.attachments = [];
      if (chatTextConfirmsPlan(text)) {
        const plan = latestPendingStudioPlan();
        if (plan) return executePlannedStudioMessage(text, plan, pendingAttachments);
      }
      return sendPlanStudioMessage(text, pendingAttachments);
    }
    if (studioLane === "interactive") {
      if (!text) return setChatMsg("Enter a prompt for Interactive Mode.");
      chatState.attachments = [];
      return sendInteractiveStudioMessage(text, pendingAttachments);
    }
    if (studioLane === "plan-backend") {
      if (!text) return setChatMsg("Enter a prompt for backend Plan Mode.");
      if (pendingAttachments.length) return setChatMsg("Backend Plan Mode does not use attachments yet.", "error");
      chatState.attachments = [];
      return sendImageStudioMessage(studioLane, text, []);
    }
    const allowedKind = ["ltx", "sulphur", "10eros", "wan"].includes(studioLane)
      ? "image"
      : studioLane === "voice"
        ? "audio"
        : "";
    if (pendingAttachments.length && (!allowedKind || pendingAttachments.some((row) => String(row?.kind || "") !== allowedKind))) {
      return setChatMsg(
        allowedKind
          ? `${$("chatStudioLane")?.selectedOptions?.[0]?.textContent || "This Studio lane"} accepts only one ${allowedKind} attachment.`
          : "This Studio lane does not use attachments.",
        "error",
      );
    }
    if (!text) return setChatMsg("Enter a generation prompt.");
    chatState.attachments = [];
    return sendImageStudioMessage(studioLane, text, pendingAttachments.slice(0, 1));
  }
  if (!runtime) {
    if (chatSelectedRuntimeIsUnavailable()) {
      promptUnavailableChatRuntimeSelection();
      return;
    }
    return setChatMsg("Start a preset before using local chat.");
  }
  if (!text && !pendingAttachments.length) return;
  const unsupportedMedia = pendingAttachments.filter((attachment) => {
    const kind = String(attachment?.kind || "text").toLowerCase();
    return ["image", "audio", "video"].includes(kind) && !chatRuntimeSupportsMedia(runtime, kind);
  });
  if (unsupportedMedia.length) {
    const kinds = Array.from(new Set(unsupportedMedia.map((attachment) => String(attachment?.kind || "media")))).join(", ");
    return setChatMsg(`The selected container does not advertise ${kinds} support, so those attachments are disabled for this request.`);
  }
  const messageCreatedAt = Date.now();
  const userMessage = {
    role: "user",
    text,
    attachments: pendingAttachments,
    inputTokensEstimate: estimateVisibleMessageInputTokens({
      role: "user",
      text,
      attachments: pendingAttachments,
    }),
    inputTokensApprox: true,
    createdAt: messageCreatedAt,
  };
  try {
    await maybeCompactChatConversation(runtime, userMessage);
  } catch (e) {
    return setChatMsg(String(e || ""), "error");
  }
  const assistantMessage = {
    role: "assistant",
    text: "",
    reasoningText: "",
    thinkingStartedAt: 0,
    thinkingDurationMs: 0,
    thinkingLive: false,
    thinkingDone: false,
    thinkingExpanded: true,
    modelLabel: runtime.served_model_name || runtime.model_id || runtime.mode || "Model",
    createdAt: messageCreatedAt,
    generationStartedAt: messageCreatedAt,
  };
  const shouldAutoNameConversation = (chatState.messages || []).length === 0;
  const shouldGenerateSmartTitle = shouldAutoNameConversation && chatSmartTitlesEnabled();
  const requestHistory = [...(chatState.messages || []), userMessage];
  chatState.messages = [...requestHistory, assistantMessage];
  const activeConversation = activeChatConversation();
  if (activeConversation) {
    activeConversation.generationActive = true;
    activeConversation.lastLatencySeconds = undefined;
    activeConversation.runtimeSnapshot = buildConversationRuntimeSnapshot(
      runtime,
      activeConversation,
    );
  }
  chatLocalRequestActive = true;
  stopChatStreamResumePolling();
  chatState.attachments = [];
  chatState.busy = true;
  setChatTranscriptAutoFollow(true);
  if (input) input.value = "";
  persistChatConversationState();
  renderChatUi();
  renderChatTranscript(true, { reason: "user" });
  lockChatTranscriptStreamingHeight();
  setChatMsg("Generating message...");
  const assistantIndex = chatState.messages.length - 1;
  let firstVisibleStreamRenderDone = false;
  let visibleTextQueue = "";
  let visibleReasoningQueue = "";
  let visibleRevealScheduled = false;
  let visibleRevealDrainResolver = null;
  const assistantLiveMessage = () => chatState.messages[assistantIndex] || null;
  const visibleRevealQueueLength = () =>
    String(visibleTextQueue || "").length + String(visibleReasoningQueue || "").length;
  const visibleRevealChunkSize = () => {
    const queued = visibleRevealQueueLength();
    if (queued > 5200) return CHAT_STREAM_VISIBLE_REVEAL_BURST_MAX_CHARS;
    if (queued > 2400) return Math.min(128, CHAT_STREAM_VISIBLE_REVEAL_BURST_MAX_CHARS);
    if (queued > 900) return Math.min(96, CHAT_STREAM_VISIBLE_REVEAL_BURST_MAX_CHARS);
    if (queued > 240) return Math.min(64, CHAT_STREAM_VISIBLE_REVEAL_BURST_MAX_CHARS);
    return CHAT_STREAM_VISIBLE_REVEAL_TARGET_CHARS;
  };
  const resolveVisibleRevealDrain = () => {
    if (visibleRevealDrainResolver && !visibleRevealQueueLength()) {
      const resolve = visibleRevealDrainResolver;
      visibleRevealDrainResolver = null;
      resolve();
    }
  };
  const revealQueuedChatText = () => {
    visibleRevealScheduled = false;
    const startedAt = Date.now();
    let rendered = false;
    const assistant = assistantLiveMessage();
    if (!assistant || !assistant.streamingVisibleActive) {
      visibleTextQueue = "";
      visibleReasoningQueue = "";
      resolveVisibleRevealDrain();
      return;
    }
    do {
      let budget = Math.max(
        CHAT_STREAM_VISIBLE_REVEAL_MIN_CHARS,
        Math.min(CHAT_STREAM_VISIBLE_REVEAL_BURST_MAX_CHARS, visibleRevealChunkSize()),
      );
      if (visibleReasoningQueue) {
        const chunk = visibleReasoningQueue.slice(0, budget);
        visibleReasoningQueue = visibleReasoningQueue.slice(chunk.length);
        assistant.streamingVisibleReasoningText =
          String(assistant.streamingVisibleReasoningText || "") + chunk;
        budget -= chunk.length;
      }
      if (budget > 0 && visibleTextQueue) {
        const chunk = visibleTextQueue.slice(0, budget);
        visibleTextQueue = visibleTextQueue.slice(chunk.length);
        assistant.streamingVisibleText = String(assistant.streamingVisibleText || "") + chunk;
      }
      rendered = true;
    } while (
      visibleRevealQueueLength() > CHAT_STREAM_VISIBLE_REVEAL_BACKLOG_CHARS &&
      Date.now() - startedAt < CHAT_STREAM_VISIBLE_REVEAL_FRAME_BUDGET_MS
    );
    if (rendered) {
      if (!firstVisibleStreamRenderDone) {
        firstVisibleStreamRenderDone = updateLiveChatMessageDom(assistantIndex, false);
      } else {
        updateLiveChatMessageDom(assistantIndex, false);
      }
    }
    if (visibleRevealQueueLength()) {
      scheduleVisibleReveal();
    } else {
      resolveVisibleRevealDrain();
    }
  };
  const scheduleVisibleReveal = () => {
    if (visibleRevealScheduled) return;
    visibleRevealScheduled = true;
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(() => revealQueuedChatText());
      return;
    }
    setTimeout(revealQueuedChatText, CHAT_STREAM_VISIBLE_REVEAL_FAST_INTERVAL_MS);
  };
  const enqueueVisibleStreamChunk = async (addedText = "", kind = "text") => {
    const assistant = assistantLiveMessage();
    if (!assistant) return;
    assistant.streamingVisibleActive = true;
    if (typeof assistant.streamingVisibleText !== "string") assistant.streamingVisibleText = "";
    if (typeof assistant.streamingVisibleReasoningText !== "string") {
      assistant.streamingVisibleReasoningText = "";
    }
    if (kind === "reasoning") visibleReasoningQueue += String(addedText || "");
    else visibleTextQueue += String(addedText || "");
    scheduleVisibleReveal();
    if (visibleRevealQueueLength() > 3600) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  };
  const drainVisibleStreamQueue = async () => {
    if (!visibleRevealQueueLength()) return;
    await new Promise((resolve) => {
      visibleRevealDrainResolver = resolve;
      scheduleVisibleReveal();
    });
  };
  const finishVisibleStream = async () => {
    await drainVisibleStreamQueue();
    const assistant = assistantLiveMessage();
    if (!assistant) return;
    assistant.streamingVisibleText = assistant.text || "";
    assistant.streamingVisibleReasoningText = assistant.reasoningText || "";
    updateLiveChatMessageDom(assistantIndex, false);
    delete assistant.streamingVisibleActive;
    delete assistant.streamingVisibleText;
    delete assistant.streamingVisibleReasoningText;
  };
  try {
    const requestMessages = buildChatRequestMessages(requestHistory);
    logDebugEvent("chat_request_prepare", {
      activeConversationId: String(chatState.activeConversationId || ""),
      runtimeId: String(runtime.id || runtime.instance_id || ""),
      requestHistoryCount: requestHistory.length,
      requestMessageCount: requestMessages.length,
      userTextLength: text.length,
      attachmentCount: pendingAttachments.length,
    });
    if (!requestMessages.length) {
      throw new Error("Chat request was empty before send. The request was blocked to avoid a broken stream call.");
    }
    if (shouldGenerateSmartTitle)
      requestMessages.unshift({ role: "system", content: chatTitleInstruction() });
    const requestBody = {
      conversation_id: String(chatState.activeConversationId || ""),
      instance_id: runtime.id || runtime.instance_id,
      mode: runtime.selector || runtime.mode,
      model: runtime.served_model_name || runtime.model_id,
      messages: requestMessages,
      params: { ...chatState.params },
      api_preset: chatState.apiPresetName || "",
    };
    chatRequestController = new AbortController();
    const raw = await fetch("/admin/chat-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
      signal: chatRequestController.signal,
    });
    if (!raw.ok || !raw.body) {
      let errorText = "Chat request failed";
      try {
        const payload = await raw.json();
        errorText = payload.error || errorText;
      } catch (e) {}
      throw new Error(errorText);
    }
    const reader = raw.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let streamFinished = false;
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      for (const frame of frames) {
        const event = parseChatStreamFrame(frame);
        if (!event) continue;
        if (event.eventName === "delta") {
          if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
            finalizeChatThinkingState(chatState.messages[assistantIndex]);
          }
          const textDelta = String(event.payload?.text || "");
          chatState.messages[assistantIndex].text += textDelta;
          persistStreamingChatState();
          await enqueueVisibleStreamChunk(textDelta, "text");
        } else if (event.eventName === "reasoning") {
          const assistant = chatState.messages[assistantIndex];
          if (!assistant.thinkingStartedAt) assistant.thinkingStartedAt = Date.now();
          assistant.thinkingLive = true;
          assistant.thinkingDone = false;
          assistant.thinkingExpanded = true;
          const reasoningDelta = String(event.payload?.text || "");
          assistant.reasoningText += reasoningDelta;
          assistant.thinkingDurationMs = clampChatThinkingDurationMs(
            Date.now() - Number(assistant.thinkingStartedAt || Date.now()),
          );
          persistStreamingChatState();
          await enqueueVisibleStreamChunk(reasoningDelta, "reasoning");
        } else if (event.eventName === "tool") {
          if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
            finalizeChatThinkingState(chatState.messages[assistantIndex]);
          }
          setChatMsg(event.payload?.message || `Running tool ${event.payload?.name || ""}...`);
        } else if (event.eventName === "status") {
          setChatMsg(String(event.payload?.message || ""));
        } else if (event.eventName === "metrics") {
          updateConversationRuntimeMetrics(
            activeChatConversation(),
            runtime,
            event.payload || {},
            { persist: false },
          );
          persistStreamingChatState();
          scheduleChatRuntimeStatsRender();
        } else if (event.eventName === "error") {
          throw new Error(event.payload?.error || event.payload?.message || "Chat stream failed.");
        } else if (event.eventName === "done") {
          if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
            finalizeChatThinkingState(chatState.messages[assistantIndex]);
          }
          updateConversationRuntimeMetrics(
            activeChatConversation(),
            runtime,
            event.payload || {},
            { persist: false },
          );
          streamFinished = true;
          setChatMsg("");
          break;
        }
      }
      if (done || streamFinished) break;
    }
    if (!streamFinished && buffer.trim()) {
      const event = parseChatStreamFrame(buffer);
      if (event?.eventName === "delta") {
        if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
          finalizeChatThinkingState(chatState.messages[assistantIndex]);
        }
        const textDelta = String(event.payload?.text || "");
        chatState.messages[assistantIndex].text += textDelta;
        persistStreamingChatState();
        await enqueueVisibleStreamChunk(textDelta, "text");
      } else if (event?.eventName === "reasoning") {
        const assistant = chatState.messages[assistantIndex];
        if (!assistant.thinkingStartedAt) assistant.thinkingStartedAt = Date.now();
        assistant.thinkingLive = true;
        assistant.thinkingDone = false;
        assistant.thinkingExpanded = true;
        const reasoningDelta = String(event.payload?.text || "");
        assistant.reasoningText += reasoningDelta;
        assistant.thinkingDurationMs = clampChatThinkingDurationMs(
          Date.now() - Number(assistant.thinkingStartedAt || Date.now()),
        );
        persistStreamingChatState();
        await enqueueVisibleStreamChunk(reasoningDelta, "reasoning");
      } else if (event?.eventName === "tool") {
        if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
          finalizeChatThinkingState(chatState.messages[assistantIndex]);
        }
        setChatMsg(event.payload?.message || `Running tool ${event.payload?.name || ""}...`);
      } else if (event?.eventName === "status") {
        setChatMsg(String(event.payload?.message || ""));
      } else if (event?.eventName === "metrics") {
        updateConversationRuntimeMetrics(
          activeChatConversation(),
          runtime,
          event.payload || {},
          { persist: false },
        );
        persistStreamingChatState();
        scheduleChatRuntimeStatsRender();
      } else if (event?.eventName === "error") {
        throw new Error(event.payload?.error || event.payload?.message || "Chat stream failed.");
      } else if (event?.eventName === "done") {
        if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
          finalizeChatThinkingState(chatState.messages[assistantIndex]);
        }
        updateConversationRuntimeMetrics(
          activeChatConversation(),
          runtime,
          event.payload || {},
          { persist: false },
        );
        persistStreamingChatState(true);
        setChatMsg("");
      }
    }
    if (
      chatMessageThinkingActive(chatState.messages[assistantIndex]) ||
      chatState.messages[assistantIndex].reasoningText
    ) {
      finalizeChatThinkingState(chatState.messages[assistantIndex]);
    }
    await finishVisibleStream();
    renderChatTranscript(false, { reason: "stream" });
    if (shouldGenerateSmartTitle) {
      const extractedTitle = extractChatTitleMarker(chatState.messages[assistantIndex].text);
      if (extractedTitle.title) {
        chatState.messages[assistantIndex].text = extractedTitle.text;
        syncActiveConversationFromChatState();
        applyConversationTitle(
          chatState.activeConversationId,
          extractedTitle.title,
          userMessage.text || "",
          pendingAttachments,
        );
      }
    }
    if (
      !chatState.messages[assistantIndex].text.trim() &&
      !chatMessageThinkingView(chatState.messages[assistantIndex]).reasoningText
    ) {
      chatState.messages[assistantIndex].text = "[No text returned]";
    }
    setChatMsg("");
    scheduleChatRuntimeStatsRender(true);
    scheduleConversationRuntimeMetricRefresh(1, 0);
    if (shouldAutoNameConversation) {
      applyConversationTitle(
        chatState.activeConversationId,
        "",
        userMessage.text || "",
        pendingAttachments,
      );
    }
    stopChatStreamResumePolling();
  } catch (e) {
    const aborted =
      e?.name === "AbortError" ||
      /aborted|abort/i.test(String(e?.message || e || ""));
    logDebugEvent("chat_request_failed", {
      activeConversationId: String(chatState.activeConversationId || ""),
      aborted,
      error: e?.message || String(e || ""),
    });
    if (chatMessageThinkingActive(chatState.messages[assistantIndex])) {
      finalizeChatThinkingState(chatState.messages[assistantIndex], !aborted);
    }
    if (
      !String(chatState.messages[assistantIndex]?.text || "").trim() &&
      !chatMessageThinkingView(chatState.messages[assistantIndex] || {}).reasoningText
    ) {
      chatState.messages = chatState.messages.filter((_, index) => index !== assistantIndex);
    }
    setChatMsg(
      aborted ? "Generation stopped." : String(e || ""),
      aborted ? "warning" : "error",
    );
    if (aborted) scheduleConversationRuntimeMetricRefresh(3, 300);
    stopChatStreamResumePolling();
  } finally {
    markAssistantGenerationFinished(chatState.messages[assistantIndex]);
    if (chatStreamingPersistTimer) {
      clearTimeout(chatStreamingPersistTimer);
      chatStreamingPersistTimer = null;
    }
    chatLocalRequestActive = false;
    chatState.busy = false;
    const activeConversationNow = activeChatConversation();
    if (activeConversationNow) activeConversationNow.generationActive = false;
    chatRequestController = null;
    chatTranscriptLastSignature = "";
    unlockChatTranscriptStreamingHeight();
    persistChatConversationState();
    renderChatUi();
    finalizeChatTranscriptBottomFollow($("chatTranscript"));
    const transcriptHost = $("chatTranscript");
    if (chatHtmlNeedsCodeSyntaxHighlight(transcriptHost?.innerHTML || "")) {
      scheduleCodeSyntaxHighlight(transcriptHost);
    }
  }
}
if (
  typeof window !== "undefined" &&
  window.location?.protocol === "file:" &&
  /web-ui\.test\.html$/i.test(String(window.location?.pathname || ""))
) {
  window.__club3090SetChatMessagesForSmoke = function setChatMessagesForSmoke(messages) {
    chatState.messages = Array.isArray(messages) ? messages : [];
    chatTranscriptLastSignature = "";
  };
}
ensureDynamicPresetLayout();
ensurePresetActionModal();
renderPresetScopeTabs();
renderModelInstallStatus();
renderDynamicPresetModels();
refreshStatus({ force: true }).catch(() => {});
