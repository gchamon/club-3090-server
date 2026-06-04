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
function handleChatInputChange() {
  handleChatInputResize();
  const hasSelectableRuntime = activeChatPresets().length > 0 || chatSelectedRuntimeIsUnavailable();
  const chatControlsDisabled = chatState.busy || chatHydrationPending() || !chatStateHydrated;
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
  const chatControlsDisabled = chatState.busy || chatHydrationPending() || !chatStateHydrated;
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
      const label = `${variantDisplayLabel({ upstream_tag: runtime.selector || runtime.mode })} | ${runtime.id || runtime.instance_id}`;
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
  const chatControlsDisabled = chatState.busy || chatHydrationPending() || !chatStateHydrated;
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
function chatAttachmentId() {
  return `chat-att-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
function chatAttachmentKindClass(attachment) {
  return attachment?.kind === "image" ? "chat-attachment-image" : "chat-attachment-text";
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
  const parts = [conversationId, String(visibleTurns), String(chatMarkdownRenderEpoch)];
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
        message?.tokensPerSecond ?? "",
      ].join(":"),
    );
  });
  return parts.join("|");
}
function renderChatMessageMeta(message = {}) {
  const bits = [];
  if (message.role === "user") {
    const inputTokens = message.inputTokens ?? message.inputTokensEstimate;
    if (inputTokens !== null && inputTokens !== undefined)
      bits.push(`input: ${formatGroupedInt(inputTokens)} tokens`);
  } else if (message.role === "assistant") {
    if (message.outputTokens !== null && message.outputTokens !== undefined)
      bits.push(`output: ${formatGroupedInt(message.outputTokens)} tokens`);
    if (message.ttftSeconds !== null && message.ttftSeconds !== undefined)
      bits.push(`TTFT: ${formatNumber(message.ttftSeconds, 3)}s`);
    if (message.tokensPerSecond !== null && message.tokensPerSecond !== undefined) {
      bits.push(`tk/s: ${formatNumber(message.tokensPerSecond, 2)}`);
    }
  }
  return bits.length
    ? `<div class="chat-message-meta">${escapeHtml(bits.join(" · "))}</div>`
    : "";
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
  const thinkingTitle = thinkingDuration
    ? `${thinkingActive ? "Thinking" : "Thought"} for ${thinkingDuration}`
    : thinkingView.reasoningText
      ? `${thinkingActive ? "Thinking" : "Thought"} for <1 second`
      : thinkingActive
        ? "Thinking"
        : "Thought";
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
function renderChatMessageBodyContent(message = {}, messageIndex = -1) {
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
  const meta = renderChatMessageMeta(message);
  const markdownBody = renderChatMessageMarkdownHtml(
    message,
    thinkingView.contentText || "",
    {
      streaming: message.role === "assistant" && !!chatState.busy,
    },
  );
  return `${thinkingCard}${markdownBody}${files}${images}${meta}`;
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
      const shouldHighlightStable =
        chatHtmlNeedsCodeSyntaxHighlight(state?.stableHtml || "") ||
        chatHtmlNeedsCodeSyntaxHighlight(state?.appendedStableHtml || "") ||
        chatHtmlNeedsCodeSyntaxHighlight(state?.liveHtml || "");
      if ((stableChanged || !chatState.busy) && shouldHighlightStable) {
        scheduleCodeSyntaxHighlight(stableHost);
      }
    }
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
  renderChatAttachments();
  if ($("chatAutoscroll")) {
    $("chatAutoscroll").checked = chatTranscriptAutoscrollEnabled();
  }
  if (!preserveTranscript) renderChatTranscript(false, { reason: "ui" });
  renderChatRuntimeStats();
  handleChatInputResize();
  const runtime = activeChatRuntime();
  const chatControlsDisabled = chatState.busy || chatHydrationPending() || !chatStateHydrated;
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
    $("chatSendBtn").disabled =
      chatControlsDisabled || !(activeChatPresets().length > 0 || chatSelectedRuntimeIsUnavailable()) || (!chatState.busy && !hasDraft);
    $("chatSendBtn").classList.toggle("is-stop", !!chatState.busy);
    $("chatSendBtn").innerHTML = svgIcon(chatState.busy ? "stop" : "send");
  }
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
async function uploadChatImageAttachment(file, source = "file") {
  const response = await fetch("/admin/chat-attachments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      kind: "image",
      name: file?.name || "image",
      mime: file?.type || "image/*",
      source,
      data_url: await readFileAsDataUrl(file),
    }),
  });
  const payload = await response.json();
  if (!response.ok || !payload?.ok || !payload?.attachment) {
    throw new Error(payload?.error || `Failed to upload ${file?.name || "image"}.`);
  }
  return cloneChatAttachment(payload.attachment);
}
async function buildChatAttachmentsFromFiles(files, source = "file") {
  const additions = [];
  for (const file of files || []) {
    if (!file) continue;
    if (String(file.type || "").toLowerCase().startsWith("image/")) {
      additions.push(await uploadChatImageAttachment(file, source));
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
    throw new Error(`Unsupported attachment type: ${file.name || "file"}. Attach text files or images only.`);
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
  return `Attached file: ${attachment?.name || "attachment"}\n\n${attachment?.text || ""}`;
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
  const titleStripped = extractChatTitleMarker(message?.text || "");
  const sourceText = titleStripped.title ? titleStripped.text : String(message?.text || "");
  const inline = splitThinkingBlocks(sourceText);
  const direct = chatMessageReasoningText(message).trim();
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
    .then(() => {
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
async function sendChatMessage() {
  if (chatState.busy) {
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
  const runtime = activeChatRuntime();
  const input = $("chatInput");
  const text = String(input?.value || "").trim();
  const pendingAttachments = [...(chatState.attachments || [])];
  if (!runtime) {
    if (chatSelectedRuntimeIsUnavailable()) {
      promptUnavailableChatRuntimeSelection();
      return;
    }
    return setChatMsg("Start a preset before using local chat.");
  }
  if (!text && !pendingAttachments.length) return;
  if (!chatRuntimeSupportsVision(runtime) && pendingAttachments.some((attachment) => attachment?.kind === "image")) {
    return setChatMsg("The selected container does not advertise vision support, so image attachments are disabled for this request.");
  }
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
          chatState.messages[assistantIndex].text += String(event.payload?.text || "");
          persistStreamingChatState();
          scheduleLiveChatMessageDomUpdate(assistantIndex, false, "stream");
        } else if (event.eventName === "reasoning") {
          const assistant = chatState.messages[assistantIndex];
          if (!assistant.thinkingStartedAt) assistant.thinkingStartedAt = Date.now();
          assistant.thinkingLive = true;
          assistant.thinkingDone = false;
          assistant.thinkingExpanded = true;
          assistant.reasoningText += String(event.payload?.text || "");
          assistant.thinkingDurationMs = clampChatThinkingDurationMs(
            Date.now() - Number(assistant.thinkingStartedAt || Date.now()),
          );
          persistStreamingChatState();
          scheduleLiveChatMessageDomUpdate(assistantIndex, false, "stream");
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
        chatState.messages[assistantIndex].text += String(event.payload?.text || "");
        persistStreamingChatState();
        scheduleLiveChatMessageDomUpdate(assistantIndex, false, "stream");
      } else if (event?.eventName === "reasoning") {
        const assistant = chatState.messages[assistantIndex];
        if (!assistant.thinkingStartedAt) assistant.thinkingStartedAt = Date.now();
        assistant.thinkingLive = true;
        assistant.thinkingDone = false;
        assistant.thinkingExpanded = true;
        assistant.reasoningText += String(event.payload?.text || "");
        assistant.thinkingDurationMs = clampChatThinkingDurationMs(
          Date.now() - Number(assistant.thinkingStartedAt || Date.now()),
        );
        persistStreamingChatState();
        scheduleLiveChatMessageDomUpdate(assistantIndex, false, "stream");
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
ensureDynamicPresetLayout();
ensurePresetActionModal();
renderPresetScopeTabs();
renderModelInstallStatus();
renderDynamicPresetModels();
refreshStatus({ force: true }).catch(() => {});
