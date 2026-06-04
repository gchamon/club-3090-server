// Layout normalization
function ensureV413Layout() {
  const tabs = document.querySelector(".tabs");
  const auditBtn = tabs && tabs.querySelector('.tab[onclick*=\"audit\"]');
  const logsBtn = tabs && tabs.querySelector('.tab[onclick*=\"logs\"]');
  if (auditBtn) auditBtn.remove();
  if (tabs && logsBtn) tabs.appendChild(logsBtn);
  const system = $("system");
  const presets = $("presets");
  const logs = $("logs");
  const audit = $("audit");
  if (system && audit) {
    const accessPolicy = findPanelByHeading("audit", "Access Policy");
    if (accessPolicy && !accessPolicy.dataset.v413Moved) {
      accessPolicy.dataset.v413Moved = "1";
      safeInsertBefore(system, accessPolicy, system.children[1] || null);
    }
    const overview = findPanelByHeading("audit", "Audit Overview");
    if (overview && logs && !overview.dataset.v413Moved) {
      overview.dataset.v413Moved = "1";
      safeInsertBefore(logs, overview, logs.firstChild || null);
    }
    const globalControls = findPanelByHeading("audit", "Global Controls");
    if (globalControls) globalControls.remove();
    const auditStream = findPanelByHeading("audit", "Audit Stream");
    if (auditStream) auditStream.remove();
    if (audit.childElementCount === 0 || !audit.querySelector(".panel"))
      audit.remove();
  }
  const accessCard = findPanelByHeading("system", "Access Policy");
  if (accessCard) {
    const openUsers = [...accessCard.querySelectorAll("button")].find((btn) =>
      (btn.textContent || "").includes("Open Users Management"),
    );
    if (openUsers) openUsers.remove();
  }
  const singleCard = [...document.querySelectorAll("#presets .panel")].find(
    (panel) => {
      const h = panel.querySelector(".panel-head h2,h2");
      return (
        h &&
        ((h.textContent || "").includes("Per-Instance Docker Presets") ||
          (h.textContent || "").includes("Single GPU Docker Presets"))
      );
    },
  );
  if (singleCard) {
    singleCard.id = "singlePresetCard";
    const title = singleCard.querySelector("h2");
    if (title) title.textContent = "Model Presets";
  }
  const customTitle = [
    ...document.querySelectorAll("#presets .panel .panel-head h2"),
  ].find((h) => (h.textContent || "").trim() === "Custom Preset Templates");
  if (customTitle) customTitle.textContent = "Custom Configuration Endpoints";
  if ($("presetScopePanel")) $("presetScopePanel").remove();
  if ($("dualPresetCard")) $("dualPresetCard").remove();
  if (logs && !$("logSourcePanel")) {
    const panel = document.createElement("div");
    panel.className = "panel";
    panel.id = "logSourcePanel";
    panel.innerHTML = `<div class="panel-head"><h2>Log Sources</h2><div class="preset-actions">${renderIconButton({ title: "Export", action: "exportCurrentLog()", icon: "upload" })}</div></div><div class="subtabs"></div><div class="value smallgap" id="logsSourceSummary">-</div>`;
    logs.appendChild(panel);
  }
  const profiles = findPanelByHeading("system", "Power Profiles");
  if (profiles && !$("profileScopeNote")) {
    const note = document.createElement("div");
    note.className = "preset-help";
    note.id = "profileScopeNote";
    safeInsertBefore(
      profiles,
      note,
      profiles.querySelector(".actions") || profiles.firstChild,
    );
  }
  const power = findPanelByHeading("system", "Optimizations + Cooling");
  if (power && !$("powerScopeNote")) {
    const note = document.createElement("div");
    note.className = "preset-help";
    note.id = "powerScopeNote";
    safeInsertBefore(
      power,
      note,
      power.querySelector(".actions") || power.firstChild,
    );
  }
}

// Quota helpers and final users/groups UI
function quotaLimitText(v, suffix = "") {
  return v === null || v === undefined || v === ""
    ? "unlimited"
    : `${v}${suffix}`;
}
function quotaWeightText(v) {
  return v === null || v === undefined || v === ""
    ? "default"
    : trimFormattedNumber(Number(v).toFixed(3));
}
function quotaWindowText(windowData) {
  windowData = windowData || {};
  return `${windowData.requests || 0} msgs · score ${Number(windowData.score || 0).toFixed(1)} · in ${windowData.input_tokens || 0} · out ${windowData.output_tokens || 0} · tools ${windowData.tool_calls || 0} · thinking ${Number(windowData.thinking_seconds || 0).toFixed(1)}s`;
}
function quotaWeightLine(limits) {
  limits = limits || {};
  return `in ${quotaWeightText(limits.input_token_weight)} · out ${quotaWeightText(limits.output_token_weight)} · tools ${quotaWeightText(limits.tool_call_weight)} · thinking ${quotaWeightText(limits.thinking_second_weight)}`;
}
function quotaBudgetLine(limits) {
  limits = limits || {};
  return `5h ${quotaLimitText(limits.score_per_5h)} · week ${quotaLimitText(limits.score_per_week)} · /msg tokens ${quotaLimitText(limits.max_tokens_per_message)} · /msg tools ${quotaLimitText(limits.max_tool_calls_per_message)}`;
}
function parseQuotaNumber(id) {
  const el = $(id);
  if (!el) return null;
  const v = el.value.trim();
  return v === "" ? null : Number(v);
}
function scopeItems() {
  const items = getInstanceList().slice();
  items.sort((a, b) => {
    const ak = a.kind === "dual" ? 1 : 0;
    const bk = b.kind === "dual" ? 1 : 0;
    if (ak !== bk) return ak - bk;
    const ai = (a.gpu_indices || [a.gpu_index])[0] || 0;
    const bi = (b.gpu_indices || [b.gpu_index])[0] || 0;
    return ai - bi || String(a.id).localeCompare(String(b.id));
  });
  return items;
}
function singleScopeItems() {
  return scopeItems().filter((x) => x.kind !== "dual");
}
function pairScopeItems() {
  return gpuCount() >= 2 ? scopeItems().filter((x) => x.kind === "dual") : [];
}
function orderedPairScopeItems() {
  return pairScopeItems().slice().sort((a, b) => {
    const autoDiff = Number(!!b?.auto_pair) - Number(!!a?.auto_pair);
    if (autoDiff) return autoDiff;
    const ai = Array.isArray(a?.gpu_indices) ? a.gpu_indices : [];
    const bi = Array.isArray(b?.gpu_indices) ? b.gpu_indices : [];
    return (
      Number(ai[0] ?? 999) - Number(bi[0] ?? 999) ||
      ai.length - bi.length ||
      String(a?.id || "").localeCompare(String(b?.id || ""))
    );
  });
}
function gpuCount() {
  return Number((lastStatus && lastStatus.gpu_count) || 0);
}
function gpuSnapshotByIndex(index) {
  const target = Number(index);
  return Array.isArray(lastStatus?.gpus)
    ? lastStatus.gpus.find((gpu) => Number(gpu?.index) === target) || null
    : null;
}
function gpuDisplayName(index) {
  const gpu = gpuSnapshotByIndex(index);
  if (!gpu) return `GPU ${index}`;
  const vendor = String(gpu.vendor || "").trim();
  const name = String(gpu.name || "").trim();
  return vendor && name ? `${vendor} - ${name}` : name || vendor || `GPU ${index}`;
}
function gpuOptionLabel(index) {
  return `GPU ${index} - ${gpuDisplayName(index)}`;
}
function canonicalPairId(a, b) {
  const nums = [Number(a), Number(b)]
    .filter((x) => Number.isInteger(x) && x >= 0)
    .sort((x, y) => x - y);
  if (nums.length !== 2 || nums[0] === nums[1]) return "";
  return `PAIR${nums[0]}_${nums[1]}`;
}
function currentScopeInstance(strict = false) {
  if (currentScope() === "GLOBAL") {
    return null;
  }
  return (
    scopeItems().find((x) => x.id === currentScope()) ||
    singleScopeItems()[0] ||
    pairScopeItems()[0] ||
    null
  );
}
function globalDockerLogScopeOptions() {
  const options = [];
  const seen = new Set();
  const scopeById = new Map(
    scopeItems().map((row) => [String(row?.id || "").trim().toUpperCase(), row]),
  );
  const globalLabels = new Map();
  const addOption = (id, label = "") => {
    const normalizedId = String(id || "").trim().toUpperCase();
    if (!normalizedId || seen.has(normalizedId)) return;
    seen.add(normalizedId);
    options.push({
      id: normalizedId,
      label: String(label || normalizedId),
    });
  };
  runtimeTrackingItems().forEach((row) => {
    const runtimeId = String(row?.id || row?.instance_id || "").trim().toUpperCase();
    if (runtimeId && runtimeId !== "GLOBAL") return;
    const gpuIndices = Array.isArray(row?.gpu_indices)
      ? row.gpu_indices
          .map((value) => Number(value))
          .filter((value) => Number.isInteger(value) && value >= 0)
      : [];
    if (gpuIndices.length >= 2) {
      const pairId = canonicalPairId(gpuIndices[0], gpuIndices[1]);
      const pair = scopeById.get(pairId);
      globalLabels.set(
        pairId,
        `${pair ? scopeLabel(pair) : pairId || `Pair ${gpuIndices.slice(0, 2).join(" + ")}` } (Global)`,
      );
      return;
    }
    if (gpuIndices.length === 1) {
      const gpuId = `GPU${gpuIndices[0]}`;
      const scoped = scopeById.get(gpuId);
      globalLabels.set(gpuId, `${scoped ? scopeLabel(scoped) : gpuId} (Global)`);
    }
  });
  runtimeTrackingItems().forEach((row) => {
    const runtimeId = String(row?.id || row?.instance_id || "").trim().toUpperCase();
    if (!runtimeId || runtimeId === "GLOBAL") return;
    const scoped = scopeById.get(runtimeId);
    addOption(
      runtimeId,
      globalLabels.get(runtimeId) ||
        (scoped ? scopeLabel(scoped) : String(row?.display_name || runtimeId)),
    );
  });
  globalLabels.forEach((label, id) => addOption(id, label));
  scopeItems()
    .filter((row) => row && (row.running || row.booting))
    .forEach((row) => addOption(row.id, globalLabels.get(String(row.id || "").trim().toUpperCase()) || scopeLabel(row)));
  return options;
}
function dockerLogTarget() {
  if (currentLogSource === "audit" || currentLogSource === "debug") return null;
  if (scopeIsGlobal()) {
    const globalOptions = globalDockerLogScopeOptions();
    const firstId = String(globalOptions[0]?.id || "").trim().toUpperCase();
    return (
      scopeItems().find((row) => String(row?.id || "").trim().toUpperCase() === firstId) ||
      (firstId ? { id: firstId, kind: firstId.startsWith("PAIR") ? "dual" : "single" } : null)
    );
  }
  return currentScopeInstance(false) || scopeItems()[0] || null;
}
function scopeLabel(inst) {
  if (!inst) return "Global";
  if (inst.id === "GLOBAL") return "Global";
  return inst.kind === "dual"
    ? `Pair ${(inst.gpu_indices || []).join(" + ")}`
    : inst.id;
}
function runtimeTrackingItems() {
  const rows = Object.values(
    (lastStatus && lastStatus.instance_runtime_metrics) || {},
  ).filter((row) => row && row.running);
  rows.sort((a, b) => {
    const ag = Array.isArray(a.gpu_indices) ? a.gpu_indices : [];
    const bg = Array.isArray(b.gpu_indices) ? b.gpu_indices : [];
    return (
      (ag[0] | 999) - (bg[0] | 999) ||
      ag.length - bg.length ||
      String(a.id || a.instance_id || "").localeCompare(
        String(b.id || b.instance_id || ""),
      )
    );
  });
  return rows;
}
function normalizeTrackedRuntimeId(value) {
  const rows = runtimeTrackingItems();
  if (!rows.length) return "";
  const candidate = String(value || "").trim().toUpperCase();
  if (candidate) {
    const exact = rows.find((row) => String(row.id || row.instance_id).toUpperCase() === candidate);
    if (exact) return String(exact.id || exact.instance_id);
  }
  return String(rows[0].id || rows[0].instance_id);
}
function trackedOverviewRuntime() {
  const id = normalizeTrackedRuntimeId(selectedOverviewInstanceId);
  if (!id) return null;
  selectedOverviewInstanceId = id;
  return runtimeTrackingItems().find(
    (row) => String(row.id || row.instance_id) === String(id),
  ) || null;
}
function trackedLogRuntime() {
  const id = normalizeTrackedRuntimeId(selectedLogInstanceId);
  if (!id) return null;
  selectedLogInstanceId = id;
  return runtimeTrackingItems().find(
    (row) => String(row.id || row.instance_id) === String(id),
  ) || null;
}
function setOverviewTrackedInstance(id) {
  selectedOverviewInstanceId = normalizeTrackedRuntimeId(id);
  renderOverviewTracker();
  if (lastStatus) renderOverviewStatus(lastStatus);
}
function dockerLogInstanceOptions() {
  if (scopeIsGlobal()) {
    const globalOptions = globalDockerLogScopeOptions();
    if (globalOptions.length) return globalOptions;
  }
  const options = [];
  const seen = new Set();
  const addOption = (id, label = "") => {
    const normalizedId = String(id || "").trim().toUpperCase();
    if (!normalizedId || seen.has(normalizedId)) return;
    seen.add(normalizedId);
    options.push({
      id: normalizedId,
      label: String(label || normalizedId),
    });
  };
  const scopeById = new Map(
    scopeItems().map((row) => [String(row?.id || "").trim().toUpperCase(), row]),
  );
  const runtimeRows = runtimeTrackingItems();
  if (runtimeRows.length) {
    runtimeRows.forEach((row) => {
      const id = String(row?.id || row?.instance_id || "").trim().toUpperCase();
      const scoped = scopeById.get(id);
      addOption(
        id,
        scoped ? scopeLabel(scoped) : String(row?.display_name || id || "runtime"),
      );
    });
  }
  scopeItems()
    .filter((row) => row && (row.running || row.booting))
    .forEach((row) => addOption(row.id, scopeLabel(row)));
  if (options.length) return options;
  const target = dockerLogTarget();
  if (target && target.id) {
    return [
      {
        id: String(target.id || "").trim().toUpperCase(),
        label: target.id === "GLOBAL" ? "Global" : scopeLabel(target),
      },
    ];
  }
  return [];
}
function normalizeDockerLogInstanceId(value = "") {
  const options = dockerLogInstanceOptions();
  if (!options.length) return "";
  const candidate = String(value || "").trim().toUpperCase();
  const exact = options.find((row) => row.id === candidate);
  return String((exact || options[0]).id || "");
}
function selectedDockerLogInstanceId() {
  const id = normalizeDockerLogInstanceId(selectedLogInstanceId);
  if (id) selectedLogInstanceId = id;
  return id;
}
function selectedDockerLogInstanceOption() {
  const current = selectedDockerLogInstanceId();
  return (
    dockerLogInstanceOptions().find((row) => row.id === current) ||
    dockerLogInstanceOptions()[0] ||
    null
  );
}
function setDockerLogInstance(id) {
  selectedLogInstanceId = normalizeDockerLogInstanceId(id);
  renderLogInstanceSelector();
  applyLogVisibility();
  connectLogs(true);
}
function formatCtxTokens(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num) || num <= 0) return "-";
  return formatGroupedInt(num);
}
function formatNumber(value, digits = 2) {
  const num = Number(value);
  return Number.isFinite(num) ? trimFormattedNumber(num.toFixed(digits)) : "-";
}
function formatExactInt(value) {
  const num = Number(value);
  return Number.isFinite(num) ? String(Math.round(num)) : "-";
}
function formatGroupedInt(value) {
  const exact = formatExactInt(value);
  return exact === "-" ? exact : exact.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}
function formatElapsedLaunch(seconds) {
  const total = Math.max(0, Math.round(Number(seconds || 0)));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return mins > 0 ? `${mins} min, ${secs} s to launch` : `${secs} s to launch`;
}
function formatAbsoluteTimestamp(ts) {
  const num = Number(ts || 0);
  if (!Number.isFinite(num) || num <= 0) return "-";
  try {
    const asMillis = num > 1_000_000_000_000 ? num : num * 1000;
    return new Date(asMillis).toLocaleString([], {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch (e) {
    return "-";
  }
}
function conversationScopedRuntime(runtime, conversation) {
  const snapshot = cloneChatRuntimeSnapshot(conversation?.runtimeSnapshot) || null;
  const base = runtime
    ? { ...runtime }
    : snapshot
      ? { ...snapshot }
      : null;
  if (!base) return null;
  const scoped = base;
  if (!conversation) {
    scoped.max_tokens_per_second = Number(
      runtime?.last_tokens_per_second ||
        runtime?.generation_tps ||
        snapshot?.last_tokens_per_second ||
        0,
    );
    return scoped;
  }
  if (conversation.lastStatus !== undefined) scoped.last_status = conversation.lastStatus;
  if (conversation.lastLatencySeconds !== undefined)
    scoped.last_latency_s = conversation.lastLatencySeconds;
  if (conversation.lastTtftSeconds !== undefined)
    scoped.last_ttft_s = conversation.lastTtftSeconds;
  if (conversation.lastTokensPerSecond !== undefined)
    scoped.last_tokens_per_second = conversation.lastTokensPerSecond;
  if (conversation.lastTokensPerSecond !== undefined)
    scoped.last_generation_tps = conversation.lastTokensPerSecond;
  if (conversation.lastInputTokens !== undefined)
    scoped.last_input_tokens = conversation.lastInputTokens;
  if (conversation.lastOutputTokens !== undefined)
    scoped.last_output_tokens = conversation.lastOutputTokens;
  if (conversation.lastTotalTokens !== undefined)
    scoped.last_total_tokens = conversation.lastTotalTokens;
  if (conversation.totalInputTokens !== undefined)
    scoped.total_input_tokens = conversation.totalInputTokens;
  if (conversation.totalOutputTokens !== undefined)
    scoped.total_output_tokens = conversation.totalOutputTokens;
  if (conversation.totalTokens !== undefined)
    scoped.total_tokens = conversation.totalTokens;
  if (conversation.lastCtxSizeTokens !== undefined)
    scoped.ctx_size_tokens = conversation.lastCtxSizeTokens;
  if (conversation.lastPromptTokensPerSecond !== undefined)
    scoped.prompt_tps = conversation.lastPromptTokensPerSecond;
  if (conversation.lastPromptTokensPerSecond !== undefined)
    scoped.last_prompt_tps = conversation.lastPromptTokensPerSecond;
  if (
    conversation.lastPromptTokensPerSecond === undefined &&
    scoped.prompt_tps === undefined &&
    scoped.last_prompt_tps === undefined
  ) {
    const derivedPromptTps = deriveRuntimePromptTps(scoped);
    if (derivedPromptTps !== null) {
      scoped.prompt_tps = derivedPromptTps;
      scoped.last_prompt_tps = derivedPromptTps;
    }
  }
  if (conversation.lastPromptTokensPerSecondPeak !== undefined)
    scoped.max_prompt_tokens_per_second = conversation.lastPromptTokensPerSecondPeak;
  if (conversation.lastKvCacheUsagePct !== undefined)
    scoped.gpu_kv_cache_usage_pct = conversation.lastKvCacheUsagePct;
  if (conversation.lastCpuKvCacheUsagePct !== undefined)
    scoped.cpu_kv_cache_usage_pct = conversation.lastCpuKvCacheUsagePct;
  if (conversation.lastPrefixCacheHitRatePct !== undefined)
    scoped.prefix_cache_hit_rate_pct = conversation.lastPrefixCacheHitRatePct;
  if (conversation.lastToolCalls !== undefined)
    scoped.last_tool_calls = conversation.lastToolCalls;
  if (conversation.lastRequestPath !== undefined)
    scoped.last_path = conversation.lastRequestPath;
  if (conversation.lastRuntimeRequestAt !== undefined)
    scoped.last_request_at = conversation.lastRuntimeRequestAt;
  scoped.max_tokens_per_second = Math.max(
    Number(conversation.lastTokensPerSecondPeak || 0),
    Number(scoped.last_tokens_per_second || 0),
    Number(runtime?.generation_tps || snapshot?.generation_tps || 0),
  );
  return scoped;
}
function runtimeStatsRows(j) {
  const rows = Array.isArray(j?.running_runtimes) ? j.running_runtimes.filter(Boolean) : [];
  if (!rows.length || typeof variantMapBySelector !== "function" || typeof variantEffectiveLaunchMetadata !== "function") {
    return rows;
  }
  const variants = variantMapBySelector();
  return rows.map((runtime) => {
    const selector = String(runtime?.selector || runtime?.mode || "").trim();
    const variant = selector ? variants.get(selector) : null;
    if (!variant) return runtime;
    const metadata = variantEffectiveLaunchMetadata(variant);
    const nextCtxSize = Number(metadata?.ctx_size_tokens || 0);
    const nextServedModelName = String(metadata?.served_model_name || "").trim();
    if (
      (!nextCtxSize || nextCtxSize === Number(runtime?.ctx_size_tokens || 0)) &&
      (!nextServedModelName || nextServedModelName === String(runtime?.served_model_name || "").trim())
    ) {
      return runtime;
    }
    return {
      ...runtime,
      ctx_size_tokens: nextCtxSize || runtime?.ctx_size_tokens,
      served_model_name: nextServedModelName || runtime?.served_model_name,
    };
  });
}
function formatRuntimeModeValue(j, runtime) {
  if (runtime) return `${runtime.mode || "-"} / ${runtime.port || "-"}`;
  const modes = Array.isArray(j?.active_modes) ? j.active_modes.filter(Boolean) : [];
  const port = j?.active_port || "-";
  return modes.length > 1
    ? `${modes.join(", ")} / multiple`
    : `${modes[0] || j?.active_mode || "-"} / ${port}`;
}
function formatRuntimeContainerValue(j, runtime) {
  if (runtime) return runtime.container || "none";
  const containers = Array.isArray(j?.containers) ? j.containers.filter(Boolean) : [];
  return containers.length ? containers.join(", ") : "none";
}
function formatUsersValue(j) {
  const userCount = Array.isArray(j?.users) ? j.users.length : 0;
  const groupNames = Array.isArray(j?.groups)
    ? j.groups.map((group) => String(group?.name || "").trim()).filter(Boolean)
    : [];
  return `<div>${userCount} registered user${userCount === 1 ? "" : "s"}</div><div class="value-subline">groups: ${groupNames.length ? escapeHtml(groupNames.join(", ")) : "none configured"}</div>`;
}
function formatRuntimeRequestSummaryLine(runtime, statusHistory) {
  const rawStatus = runtime?.last_status;
  const statusNum = Number(rawStatus);
  const requestText = formatAbsoluteTimestamp(runtime?.last_request_at);
  const pathText = String(runtime?.last_path || "");
  return [
    Number.isFinite(statusNum)
      ? `HTTP: ${Math.trunc(statusNum)}`
      : rawStatus !== null && rawStatus !== undefined && rawStatus !== ""
        ? `HTTP: ${String(rawStatus)}`
        : "HTTP: -",
    `last path: ${pathText}`,
    requestText ? `last request: ${requestText}` : "last request: -",
  ].filter(Boolean);
}
function formatGenerationMetaLine(runtime) {
  return [
    runtime.mode || runtime.selector || runtime.engine || "-",
    runtime.served_model_name || runtime.model_id || runtime.container || "no container",
    Array.isArray(runtime.gpu_indices) && runtime.gpu_indices.length
      ? `GPUs ${runtime.gpu_indices.join(", ")}`
      : "GPU mapping unavailable",
  ];
}
function deriveRuntimePromptTps(target = {}) {
  const promptTokens = Number(
    target?.last_input_tokens ?? target?.last_total_tokens ?? 0,
  );
  if (!Number.isFinite(promptTokens) || promptTokens <= 0) return null;
  const ttft = Number(target?.last_ttft_s);
  const latency = Number(target?.last_latency_s);
  const outputTokens = Number(target?.last_output_tokens);
  const generationTps = Number(
    target?.last_generation_tps ??
      target?.last_tokens_per_second ??
      target?.generation_tps,
  );
  let prefillSeconds = null;
  if (Number.isFinite(ttft) && ttft > 0) {
    if (
      Number.isFinite(latency) &&
      latency > 0 &&
      Number.isFinite(generationTps) &&
      generationTps > 0 &&
      Number.isFinite(outputTokens) &&
      outputTokens > 0 &&
      ttft >= latency * 0.8
    ) {
      const bufferedPrefill = latency - outputTokens / Math.max(generationTps, 0.001);
      if (bufferedPrefill > 0.001) prefillSeconds = bufferedPrefill;
    }
    if (
      prefillSeconds === null &&
      Number.isFinite(generationTps) &&
      generationTps > 0
    ) {
      const correctedTtft = ttft - 1 / Math.max(generationTps, 0.001);
      if (correctedTtft > 0.001) prefillSeconds = correctedTtft;
    }
    if (prefillSeconds === null) prefillSeconds = Math.max(ttft, 0.001);
  } else if (
    Number.isFinite(latency) &&
    latency > 0 &&
    Number.isFinite(generationTps) &&
    generationTps > 0 &&
    Number.isFinite(outputTokens) &&
    outputTokens > 0
  ) {
    const estimatedPrefill = latency - outputTokens / Math.max(generationTps, 0.001);
    if (estimatedPrefill > 0.001) prefillSeconds = estimatedPrefill;
  }
  if (!Number.isFinite(prefillSeconds) || prefillSeconds <= 0) return null;
  return Number((promptTokens / Math.max(prefillSeconds, 0.001)).toFixed(2));
}
function deriveRuntimeContextUsage(target = {}) {
  const ctxSize = Number(target?.ctx_size_tokens ?? 0);
  const usedTokens = Number(
    target?.last_total_tokens ??
      (Number(target?.last_input_tokens ?? 0) +
        Number(target?.last_output_tokens ?? 0)) ??
      target?.total_tokens ??
      0,
  );
  if (!Number.isFinite(ctxSize) || ctxSize <= 0) {
    return {
      usedTokens: Number.isFinite(usedTokens) && usedTokens > 0 ? usedTokens : null,
      ctxSize: null,
      pct: null,
    };
  }
  const safeUsed = Number.isFinite(usedTokens) && usedTokens > 0 ? usedTokens : 0;
  return {
    usedTokens: safeUsed,
    ctxSize,
    pct: Math.min(100, Math.max(0, (safeUsed / ctxSize) * 100)),
  };
}
function deriveRuntimeKvUsagePct(target = {}) {
  const reportedKv = Number(
    target?.gpu_kv_cache_usage_pct ?? target?.last_gpu_kv_cache_usage_pct ?? 0,
  );
  if (Number.isFinite(reportedKv) && reportedKv >= 0) return Math.max(0, reportedKv);
  const contextUsage = deriveRuntimeContextUsage(target);
  return Number.isFinite(contextUsage?.pct) ? contextUsage.pct : null;
}
function variantStatusBadgeHtml(variant, stateLabel = "", options = {}) {
  return renderStatusBadgesHtml(variant, {
    ...options,
    stateLabel,
  });
}
function formatLastStatusCard(target, perfHistory = {}, options = {}) {
  const latency = target?.last_latency_s;
  const ttft = target?.last_ttft_s;
  const promptTps = [
    target?.last_prompt_tps,
    target?.prompt_tps,
    deriveRuntimePromptTps(target),
  ].find((value) => Number(value) > 0);
  const generationTps = [
    target?.last_generation_tps,
    target?.generation_tps,
    target?.last_tokens_per_second,
  ].find((value) => Number(value) > 0);
  const peakPromptTps = Math.max(
    Number(target?.max_prompt_tokens_per_second || 0),
    Number(perfHistory?.promptPeak || 0),
    Number(promptTps || 0),
  );
  const peakTps = Math.max(
    Number(target?.max_tokens_per_second || 0),
    Number(perfHistory?.generationPeak || 0),
    Number(generationTps || 0),
  );
  const valueOrDash = (value, digits = 2) =>
    value !== null && value !== undefined && Number.isFinite(Number(value))
      ? formatNumber(value, digits)
      : "-";
  const head = [
    `latency=${valueOrDash(latency, 3)}s`,
    `ttft=${valueOrDash(ttft, 3)}s`,
    `pp tk/s=${valueOrDash(promptTps, 2)} (${UI_ARROW_UP} ${valueOrDash(peakPromptTps || promptTps, 2)})`,
    `gen tk/s=${valueOrDash(generationTps, 2)} (${UI_ARROW_UP} ${valueOrDash(peakTps || generationTps, 2)})`,
  ];
  const detail = [];
  const effectiveKvUsagePct = deriveRuntimeKvUsagePct(target);
  const contextUsage = deriveRuntimeContextUsage(target);
  detail.push(
    effectiveKvUsagePct !== null && Number(effectiveKvUsagePct) > 0
      ? `KV: ${formatNumber(effectiveKvUsagePct, 1)}%`
      : "KV: 0%",
  );
  if (contextUsage.ctxSize !== null) {
    detail.push(
      `context: ${formatGroupedInt(contextUsage.usedTokens || 0)} / ${formatGroupedInt(
        contextUsage.ctxSize,
      )} (${formatNumber(contextUsage.pct, 1)}%)`,
    );
  } else if (contextUsage.usedTokens !== null) {
    detail.push(`context: ${formatGroupedInt(contextUsage.usedTokens)} tokens`);
  } else {
    detail.push("context: -");
  }
  const prefixSupported =
    Number(target?.prefix_cache_hit_rate_pct) > 0 ||
    Number(target?.speculative?.drafted_tokens || target?.speculative?.draft_tokens || 0) > 0;
  if (
    target?.prefix_cache_hit_rate_pct !== null &&
    target?.prefix_cache_hit_rate_pct !== undefined &&
    prefixSupported
  ) {
    detail.push(`prefix hit: ${formatNumber(target.prefix_cache_hit_rate_pct, 1)}%`);
  } else {
    detail.push("prefix hit: -");
  }
  const spec = target?.speculative || {};
  const specBits = [];
  specBits.push(`drafted=${spec.drafted_tokens ?? 0}`);
  specBits.push(
    `accept=${
      spec.accept_rate_pct !== null && spec.accept_rate_pct !== undefined
        ? formatNumber(spec.accept_rate_pct, 1)
        : "0"
    }%`,
  );
  specBits.push(`accepted=${spec.accepted_tokens ?? 0}/${spec.draft_tokens ?? 0}`);
  specBits.push(
    `avg=${
      spec.mean_acceptance_length !== null && spec.mean_acceptance_length !== undefined
        ? formatNumber(spec.mean_acceptance_length, 2)
        : "0"
    }`,
  );
  if (
    spec.system_efficiency_pct !== null &&
    spec.system_efficiency_pct !== undefined
  ) {
    specBits.push(`eff=${formatNumber(spec.system_efficiency_pct, 1)}%`);
  }
  const lines = [`<div>${escapeHtml(head.join(UI_META_SEPARATOR))}</div>`];
  if (detail.length) {
    lines.push(`<div class="value-subline">${escapeHtml(detail.join(UI_META_SEPARATOR))}</div>`);
  }
  if (specBits.length) {
    lines.push(
      `<div class="value-subline">${escapeHtml(`spec ${specBits.join(UI_META_SEPARATOR)}`)}</div>`,
    );
  }
  return lines.join("");
}
function formatFreshConversationRuntimeStats(runtime) {
  const totalInputTokens = Number(
    runtime.total_input_tokens ?? runtime.last_input_tokens ?? 0,
  );
  const totalOutputTokens = Number(
    runtime.total_output_tokens ?? runtime.last_output_tokens ?? 0,
  );
  const totalTokens = Number(
    runtime.total_tokens ??
      runtime.last_total_tokens ??
      totalInputTokens + totalOutputTokens,
  );
  const lines = [
    escapeHtml(formatGenerationMetaLine(runtime).join(UI_META_SEPARATOR)),
    escapeHtml(`latency=0s${UI_META_SEPARATOR}ttft=0s${UI_META_SEPARATOR}pp tk/s=0 (${UI_ARROW_UP} 0)${UI_META_SEPARATOR}gen tk/s=0 (${UI_ARROW_UP} 0)`),
    escapeHtml(`KV: 0%${UI_META_SEPARATOR}context: ${formatCtxTokens(runtime.ctx_size_tokens)}${UI_META_SEPARATOR}prefix hit: 0%`),
    escapeHtml(`spec drafted=0${UI_META_SEPARATOR}accept=0%${UI_META_SEPARATOR}accepted=0/0${UI_META_SEPARATOR}avg=0`),
    escapeHtml(`input: ${formatGroupedInt(totalInputTokens)}${UI_META_SEPARATOR}output: ${formatGroupedInt(totalOutputTokens)}${UI_META_SEPARATOR}total: ${formatGroupedInt(totalTokens)}${UI_META_SEPARATOR}tools: 0`),
    escapeHtml(`HTTP: 0${UI_META_SEPARATOR}last path: N/A${UI_META_SEPARATOR}last request: 0`),
    escapeHtml("status: Idle"),
  ];
  return lines.map((line) => `<div class="value-subline">${line}</div>`).join("");
}
function formatChatRuntimeStatsFlat(runtime, options = {}) {
  if (!runtime)
    return '<div class="empty-variant-note">Start a preset to test it from the local chat interface.</div>';
  if (options.freshConversationStats) return formatFreshConversationRuntimeStats(runtime);
  const useSessionPeaks = options.useSessionPeaks !== false;
  const currentStatus = runtimeActivityStatus(runtime);
  const statusHistory = useSessionPeaks
    ? updateStatusHistory(
        runtimeStatusHistoryById,
        runtime.id || runtime.instance_id,
        currentStatus,
      )
    : { current: currentStatus, previous: "" };
  const queueBits = [];
  if (Number(runtime.waiting_requests || 0) > 0) queueBits.push(`waiting: ${runtime.waiting_requests}`);
  if (Number(runtime.pending_requests || 0) > 0) queueBits.push(`pending: ${runtime.pending_requests}`);
  if (Number(runtime.swapped_requests || 0) > 0) queueBits.push(`swapped: ${runtime.swapped_requests}`);
  const totalInputTokens = Number(
    runtime.total_input_tokens ?? runtime.last_input_tokens ?? 0,
  );
  const totalOutputTokens = Number(
    runtime.total_output_tokens ?? runtime.last_output_tokens ?? 0,
  );
  const totalTokens = Number(
    runtime.total_tokens ??
      runtime.last_total_tokens ??
      totalInputTokens + totalOutputTokens,
  );
  const tokenBits = [
    `input: ${formatGroupedInt(totalInputTokens)}`,
    `output: ${formatGroupedInt(totalOutputTokens)}`,
    `total: ${formatGroupedInt(totalTokens)}`,
    `tools: ${formatGroupedInt(runtime.last_tool_calls || 0)}`,
  ];
  const requestBits = formatRuntimeRequestSummaryLine(runtime, statusHistory);
  return `<div class="value-subline">${escapeHtml(formatGenerationMetaLine(runtime).join(UI_META_SEPARATOR))}</div>${formatLastStatusCard(runtime, {}, { useSessionPeaks })}${tokenBits.length ? `<div class="value-subline">${escapeHtml(tokenBits.join(UI_META_SEPARATOR))}</div>` : ""}<div class="value-subline">${escapeHtml(requestBits.join(UI_META_SEPARATOR))}</div><div class="value-subline">${escapeHtml(`status: ${statusHistory.current}`)}</div>${queueBits.length ? `<div class="value-subline">${escapeHtml(queueBits.join(UI_META_SEPARATOR))}</div>` : ""}`;
}
function formatGenerationRuntimeCard(runtime) {
  if (!runtime) return "";
  const statusHistory = updateStatusHistory(
    runtimeStatusHistoryById,
    runtime.id || runtime.instance_id,
    runtimeActivityStatus(runtime),
  );
  const queueBits = [];
  if (Number(runtime.waiting_requests || 0) > 0) queueBits.push(`waiting: ${runtime.waiting_requests}`);
  if (Number(runtime.pending_requests || 0) > 0) queueBits.push(`pending: ${runtime.pending_requests}`);
  if (Number(runtime.swapped_requests || 0) > 0) queueBits.push(`swapped: ${runtime.swapped_requests}`);
  const totalInputTokens = Number(
    runtime.total_input_tokens ?? runtime.last_input_tokens ?? 0,
  );
  const totalOutputTokens = Number(
    runtime.total_output_tokens ?? runtime.last_output_tokens ?? 0,
  );
  const totalTokens = Number(
    runtime.total_tokens ??
      runtime.last_total_tokens ??
      totalInputTokens + totalOutputTokens,
  );
  const tokenBits = [];
  tokenBits.push(`input: ${formatGroupedInt(totalInputTokens)}`);
  tokenBits.push(`output: ${formatGroupedInt(totalOutputTokens)}`);
  tokenBits.push(`total: ${formatGroupedInt(totalTokens)}`);
  if (runtime.last_tool_calls !== null && runtime.last_tool_calls !== undefined)
    tokenBits.push(`tools: ${formatGroupedInt(runtime.last_tool_calls)}`);
  const meta = [
    runtime.mode || "-",
    runtime.container || "no container",
    Array.isArray(runtime.gpu_indices) && runtime.gpu_indices.length
      ? `GPUs ${runtime.gpu_indices.join(", ")}`
      : "GPU mapping unavailable",
  ];
  const requestBits = formatRuntimeRequestSummaryLine(runtime, statusHistory);
  return `<div class="generation-card"><div class="generation-card-head"><div><h3>${escapeHtml(runtime.display_name || runtime.id || "Runtime")}</h3><div class="generation-card-meta">${escapeHtml(meta.join(UI_META_SEPARATOR))}</div></div></div><div class="generation-card-body">${formatLastStatusCard(runtime, {})}${tokenBits.length ? `<div class="value-subline">${escapeHtml(tokenBits.join(UI_META_SEPARATOR))}</div>` : ""}<div class="value-subline">${escapeHtml(requestBits.join(UI_META_SEPARATOR))}</div><div class="value-subline">${escapeHtml(`status: ${statusHistory.current}`)}</div>${queueBits.length ? `<div class="value-subline">${escapeHtml(queueBits.join(UI_META_SEPARATOR))}</div>` : ""}</div></div>`;
}
function renderGenerationStats(j) {
  const host = $("generationStatsContent");
  if (!host) return;
  const rows = runtimeStatsRows(j);
  const started = rows.filter((row) => {
    const signalFields = [
      row?.last_status,
      row?.last_latency_s,
      row?.last_ttft_s,
      row?.last_tokens_per_second,
      row?.last_total_tokens,
      row?.last_output_tokens,
      row?.last_request_at,
      row?.prompt_tps,
      row?.generation_tps,
      row?.gpu_kv_cache_usage_pct,
    ];
    return signalFields.some(
      (value) => value !== null && value !== undefined && value !== "" && value !== 0,
    );
  });
  const nextHtml = !rows.length
    ? '<div class="empty-variant-note">No runtime containers are active yet. Once a backend is online, this card will summarize live queue pressure, throughput, cache usage, and the latest request details for every running instance in one place.</div>'
    : !started.length
      ? '<div class="empty-variant-note">Runtime containers are online and waiting for inference. The first completed generation will populate per-instance latency, throughput, KV-cache, and token counters here so you can compare all active backends at a glance.</div>'
      : started.map(formatGenerationRuntimeCard).join("");
  if (isSelectionActiveWithin(host) && host.innerHTML === nextHtml) return;
  if (host.innerHTML !== nextHtml) host.innerHTML = nextHtml;
}
function formatRequestCard(runtime, metrics) {
  const base = `total=${metrics.total_requests | 0}, active=${metrics.active_requests | 0}, fail=${metrics.failed_requests | 0}, queue=${metrics.queued_requests | 0}`;
  return base;
}
function renderOverviewTracker() {
  const panel = findPanelByHeading("overview", "Status");
  if (!panel) return;
  let row = $("overviewTrackerRow");
  if (!row) {
    row = document.createElement("div");
    row.id = "overviewTrackerRow";
    row.className = "scope-strip";
    const grid = panel.querySelector(".grid");
    safeInsertBefore(panel, row, grid || panel.querySelector(".msg") || null);
  }
  const rows = runtimeTrackingItems();
  if (rows.length <= 1) {
    row.innerHTML = "";
    row.classList.add("hidden");
    return;
  }
  row.classList.remove("hidden");
  const current = normalizeTrackedRuntimeId(selectedOverviewInstanceId);
  selectedOverviewInstanceId = current;
  row.innerHTML = `<span class="label">Track instance</span><div class="subtabs">${rows
    .map(
      (item) =>
        `<button class="subtab ${String(item.id || item.instance_id) === current ? "active" : ""}" onclick="setOverviewTrackedInstance('${String(item.id || item.instance_id)}')">${escapeHtml(String(item.id || item.instance_id))}</button>`,
    )
    .join("")}</div>`;
}
function renderLogTracker() {
  const card = document.querySelector(".logs.panel");
  if (!card) return;
  let row = $("logTrackerRow");
  if (!row) {
    row = document.createElement("div");
    row.id = "logTrackerRow";
    row.className = "scope-strip";
    safeInsertBefore(card, row, $("log") || card.lastChild || null);
  }
  row.innerHTML = "";
  row.classList.add("hidden");
}
function renderOverviewStatus(j) {
  const metrics = (j && j.metrics) || {};
  const power = (j && j.power) || {};
  const runtime = trackedOverviewRuntime();
  const containers = Array.isArray(j?.containers) ? j.containers.filter(Boolean) : [];
  const modes = Array.isArray(j?.active_modes) ? j.active_modes.filter(Boolean) : [];
  if ($("summary"))
    $("summary").textContent = runtime
      ? `${runtime.id || runtime.instance_id} | ${runtime.mode || j.active_mode} | ${runtime.container || "no container"} | ${power.profile || "balanced"} | GPUs ${j.gpu_count | 0}`
      : `${modes[0] || j.active_mode || "-"} | ${containers[0] || j.container || "no container"} | ${power.profile || "balanced"} | GPUs ${j.gpu_count | 0}`;
  if ($("mode"))
    $("mode").textContent = formatRuntimeModeValue(j, runtime);
  if ($("container"))
    $("container").textContent = formatRuntimeContainerValue(j, runtime);
  if ($("req")) $("req").innerHTML = formatRequestCard(runtime, metrics);
  if ($("last")) $("last").innerHTML = formatUsersValue(j);
  if ($("uptime")) {
    const controlUptime = fmtUptime(j.uptime_seconds);
    const machineUptime = Number(j?.machine_uptime_seconds || 0) > 0
      ? fmtUptime(j.machine_uptime_seconds)
      : "";
    $("uptime").textContent = machineUptime
      ? `${controlUptime} • machine ${machineUptime}`
      : controlUptime;
  }
  if ($("powerbox"))
    $("powerbox").textContent =
      `profile=${power.profile || "-"}, GPU=${power.gpu || "-"}, CPU=${power.cpu || "-"}, fans=${power.fans || "-"}, container=${power.container || "-"}, idle=${power.idle_for_seconds | 0}s`;
  renderGenerationStats(j);
  renderOverviewTracker();
}
async function fetchJsonWithTimeout(url, options = {}, timeoutMs = 12000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), Math.max(1000, Number(timeoutMs || 12000)));
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    return response;
  } catch (e) {
    if (e?.name === "AbortError") {
      throw new Error(`Request timed out after ${Math.round(Math.max(1000, Number(timeoutMs || 12000)) / 1000)}s`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
function safeRenderStep(label, fn, errors) {
  try {
    fn();
  } catch (e) {
    errors.push(`${label}: ${messageText(e)}`);
  }
}
function setEditorState(editorId, introId, open) {
  const ed = $(editorId),
    intro = $(introId);
  if (ed) ed.classList.toggle("open", !!open);
  if (intro) intro.classList.toggle("hidden", !!open);
}
function openUserEditor() {
  ensureUsersUi();
  setEditorState("userEditor", "userIntro", true);
}
function openGroupEditor() {
  ensureGroupUi();
  setEditorState("groupEditor", "groupIntro", true);
}
ensureUsersUi = function () {
  const tabs = document.querySelector(".tabs");
  if (tabs && !document.getElementById("usersTabBtn")) {
    const b = document.createElement("button");
    b.className = "tab";
    b.id = "usersTabBtn";
    b.textContent = "Users";
    b.onclick = (ev) => tab(ev, "users");
    safeInsertBefore(
      tabs,
      b,
      tabs.querySelector('.tab[onclick*="metrics"]') || null,
    );
  }
  const main = document.querySelector("main.container");
  if (!main) return;
  let section = $("users");
  if (!section) {
    section = document.createElement("section");
    section.id = "users";
    section.className = "tabpane content-tab";
    safeInsertBefore(main, section, document.getElementById("metrics"));
  }
  if (section.dataset.v414Users !== "1") {
    section.dataset.v414Users = "1";
    section.innerHTML = `<div class="panel"><div class="panel-head"><h2>User Accounts</h2><button class="add-preset-btn" title="New user" aria-label="New user" onclick="resetUserForm(false)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none"/></svg></button></div><div class="preset-intro" id="userIntro">Manage per-user API keys, access scopes, and Codex-style scored budgets. The configured list stays visible while the editor is collapsed.</div><div class="preset-editor" id="userEditor"><div class="formgrid"><label>User name<input id="userName" placeholder="client_a" /></label><label>Allowed targets<input id="userTargets" placeholder="*, GLOBAL, GPU0, PAIR0_1" /></label><label>Groups<input id="userGroups" placeholder="starter, premium" /></label><label>5h score budget<input id="userScore5h" type="number" step="0.1" placeholder="unlimited" /></label><label>Weekly score budget<input id="userScoreWeek" type="number" step="0.1" placeholder="unlimited" /></label><label>Max tokens / message<input id="userMaxTokensMsg" type="number" step="1" placeholder="unlimited" /></label><label>Max tool calls / message<input id="userMaxToolsMsg" type="number" step="1" placeholder="unlimited" /></label><label>Input token weight<input id="userInputTokenWeight" type="number" step="0.001" placeholder="default" /></label><label>Output token weight<input id="userOutputTokenWeight" type="number" step="0.001" placeholder="default" /></label><label>Tool-call weight<input id="userToolCallWeight" type="number" step="0.001" placeholder="default" /></label><label>Thinking-second weight<input id="userThinkingSecondWeight" type="number" step="0.001" placeholder="default" /></label><label>Enabled<select id="userEnabled"><option value="true">Enabled</option><option value="false">Disabled</option></select></label></div><div class="preset-form-actions"><button class="btn green" onclick="saveUserForm()">Save User</button><button class="btn red" onclick="resetUserForm(true)">Cancel</button></div></div><div class="msg" id="usersMsg"></div><div class="panel" style="margin-top:12px"><h2>Configured Users</h2><div id="usersGrid" class="api-grid"></div></div></div>`;
  }
};
resetUserForm = function (collapse = true) {
  ensureUsersUi();
  selectedUserName = "";
  $("userName").disabled = false;
  $("userName").value = "";
  $("userTargets").value = "*";
  $("userGroups").value = "";
  $("userScore5h").value = "";
  $("userScoreWeek").value = "";
  $("userMaxTokensMsg").value = "";
  $("userMaxToolsMsg").value = "";
  $("userInputTokenWeight").value = "";
  $("userOutputTokenWeight").value = "";
  $("userToolCallWeight").value = "";
  $("userThinkingSecondWeight").value = "";
  $("userEnabled").value = "true";
  setEditorState("userEditor", "userIntro", !collapse);
  setUsersMsg("");
};
collectUserForm = function () {
  function val(id) {
    return (($(id) && $(id).value) || "").trim();
  }
  return {
    name: val("userName"),
    allowed_targets: val("userTargets")
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
    groups: val("userGroups")
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
    enabled: $("userEnabled").value === "true",
    generate_api_key: !selectedUserName,
    limits: {
      score_per_5h: parseQuotaNumber("userScore5h"),
      score_per_week: parseQuotaNumber("userScoreWeek"),
      max_tokens_per_message: parseQuotaNumber("userMaxTokensMsg"),
      max_tool_calls_per_message: parseQuotaNumber("userMaxToolsMsg"),
      input_token_weight: parseQuotaNumber("userInputTokenWeight"),
      output_token_weight: parseQuotaNumber("userOutputTokenWeight"),
      tool_call_weight: parseQuotaNumber("userToolCallWeight"),
      thinking_second_weight: parseQuotaNumber("userThinkingSecondWeight"),
    },
  };
};
editUser = function (name) {
  const user = ((lastStatus && lastStatus.users) || []).find(
    (u) => u.name === name,
  );
  if (!user) return;
  ensureUsersUi();
  selectedUserName = name;
  $("userName").disabled = true;
  $("userName").value = user.name;
  $("userTargets").value = (user.allowed_targets || []).join(", ");
  $("userGroups").value = (user.groups || []).join(", ");
  $("userScore5h").value = user.limits.score_per_5h ?? "";
  $("userScoreWeek").value = user.limits.score_per_week ?? "";
  $("userMaxTokensMsg").value = user.limits.max_tokens_per_message ?? "";
  $("userMaxToolsMsg").value = user.limits.max_tool_calls_per_message ?? "";
  $("userInputTokenWeight").value = user.limits.input_token_weight ?? "";
  $("userOutputTokenWeight").value = user.limits.output_token_weight ?? "";
  $("userToolCallWeight").value = user.limits.tool_call_weight ?? "";
  $("userThinkingSecondWeight").value =
    user.limits.thinking_second_weight ?? "";
  $("userEnabled").value = String(!!user.enabled);
  openUserEditor();
};
renderUsers = function (users) {
  ensureUsersUi();
  const grid = $("usersGrid");
  if (!grid) return;
  users = users || [];
  if (selectedUserName && !users.some((u) => u.name === selectedUserName))
    selectedUserName = "";
  const nextHtml =
    users
      .map((u) => {
        const actions = [
          renderIconButton({
            title: "Edit",
            action: `editUser('${u.name}')`,
            icon: "edit",
          }),
          renderIconButton({
            title: u.api_key_available ? "Show API key" : "Show API key unavailable",
            action: `showUserApiKey('${u.name}')`,
            icon: "key",
          }),
          renderIconButton({
            title: "Reset API key",
            action: `resetUserKey('${u.name}')`,
            icon: "reset",
          }),
          renderIconButton({
            title: "Delete",
            action: `deleteUserByName('${u.name}')`,
            icon: "delete",
          }),
        ].join("");
        return `<div class="api-card"><div class="api-card-head"><h3>${u.name}<br><span class="label">${u.enabled ? "enabled" : "disabled"} &middot; access ${(u.effective_allowed_targets || u.allowed_targets || []).join(", ") || "*"}</span></h3><span class="preset-actions">${actions}</span></div><p>Groups: ${(u.groups || []).join(", ") || "none"}</p><p>API key: ${u.has_api_key ? (u.api_key_available ? "stored and viewable" : "legacy key, reset once to store it") : "not issued yet"}</p><p>Last 5h: ${quotaWindowText((u.usage || {}).window_5h)}</p><p>Last week: ${quotaWindowText((u.usage || {}).window_week)}</p><p class="label">Direct budgets &middot; ${quotaBudgetLine(u.limits || {})}</p><p class="label">Direct weights &middot; ${quotaWeightLine(u.limits || {})}</p><p class="label">Effective budgets &middot; ${quotaBudgetLine(u.effective_limits || {})}</p><p class="label">Effective weights &middot; ${quotaWeightLine(u.effective_limits || {})}</p></div>`;
      })
      .join("") || '<div class="value">No API users configured yet.</div>';
  setHtmlIfChanged(grid, nextHtml);
};
ensureGroupUi = function () {
  ensureUsersUi();
  const users = $("users");
  if (!users) return;
  let panel = $("groupsPanel");
  if (!panel) {
    panel = document.createElement("div");
    panel.className = "panel";
    panel.id = "groupsPanel";
    users.appendChild(panel);
  }
  if (panel.dataset.v414Groups !== "1") {
    panel.dataset.v414Groups = "1";
    panel.innerHTML = `<div class="panel-head"><h2>User Groups / Plans</h2><button class="add-preset-btn" title="New group" aria-label="New group" onclick="resetGroupForm(false)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none"/></svg></button></div><div class="preset-intro" id="groupIntro">Define reusable plans that carry scored budgets, per-message caps, and access scopes. The configured list stays visible while the editor is collapsed.</div><div class="preset-editor" id="groupEditor"><div class="formgrid"><label>Group name<input id="groupName" placeholder="starter" /></label><label>Description<input id="groupDescription" placeholder="Shared plan description" /></label><label>Allowed targets<input id="groupTargets" placeholder="*, GLOBAL, GPU0, PAIR0_1" /></label><label>5h score budget<input id="groupScore5h" type="number" step="0.1" placeholder="unlimited" /></label><label>Weekly score budget<input id="groupScoreWeek" type="number" step="0.1" placeholder="unlimited" /></label><label>Max tokens / message<input id="groupMaxTokensMsg" type="number" step="1" placeholder="unlimited" /></label><label>Max tool calls / message<input id="groupMaxToolsMsg" type="number" step="1" placeholder="unlimited" /></label><label>Input token weight<input id="groupInputTokenWeight" type="number" step="0.001" placeholder="default" /></label><label>Output token weight<input id="groupOutputTokenWeight" type="number" step="0.001" placeholder="default" /></label><label>Tool-call weight<input id="groupToolCallWeight" type="number" step="0.001" placeholder="default" /></label><label>Thinking-second weight<input id="groupThinkingSecondWeight" type="number" step="0.001" placeholder="default" /></label><label>Enabled<select id="groupEnabled"><option value="true">Enabled</option><option value="false">Disabled</option></select></label></div><div class="preset-form-actions"><button class="btn green" onclick="saveGroupForm()">Save Group</button><button class="btn red" onclick="resetGroupForm(true)">Cancel</button></div></div><div class="msg" id="groupsMsg"></div><div class="panel" style="margin-top:12px"><h2>Configured Groups</h2><div id="groupsGrid" class="api-grid"></div></div>`;
  }
};
resetGroupForm = function (collapse = true) {
  ensureGroupUi();
  selectedGroupName = "";
  $("groupName").disabled = false;
  $("groupName").value = "";
  $("groupDescription").value = "";
  $("groupTargets").value = "*";
  $("groupScore5h").value = "";
  $("groupScoreWeek").value = "";
  $("groupMaxTokensMsg").value = "";
  $("groupMaxToolsMsg").value = "";
  $("groupInputTokenWeight").value = "";
  $("groupOutputTokenWeight").value = "";
  $("groupToolCallWeight").value = "";
  $("groupThinkingSecondWeight").value = "";
  $("groupEnabled").value = "true";
  setEditorState("groupEditor", "groupIntro", !collapse);
  setGroupsMsg("");
};
collectGroupForm = function () {
  function val(id) {
    return (($(id) && $(id).value) || "").trim();
  }
  return {
    name: val("groupName"),
    description: val("groupDescription"),
    allowed_targets: val("groupTargets")
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
    enabled: $("groupEnabled").value === "true",
    limits: {
      score_per_5h: parseQuotaNumber("groupScore5h"),
      score_per_week: parseQuotaNumber("groupScoreWeek"),
      max_tokens_per_message: parseQuotaNumber("groupMaxTokensMsg"),
      max_tool_calls_per_message: parseQuotaNumber("groupMaxToolsMsg"),
      input_token_weight: parseQuotaNumber("groupInputTokenWeight"),
      output_token_weight: parseQuotaNumber("groupOutputTokenWeight"),
      tool_call_weight: parseQuotaNumber("groupToolCallWeight"),
      thinking_second_weight: parseQuotaNumber("groupThinkingSecondWeight"),
    },
  };
};
editGroup = function (name) {
  const group = ((lastStatus && lastStatus.groups) || []).find(
    (g) => g.name === name,
  );
  if (!group) return;
  ensureGroupUi();
  selectedGroupName = name;
  $("groupName").disabled = true;
  $("groupName").value = group.name;
  $("groupDescription").value = group.description || "";
  $("groupTargets").value = (group.allowed_targets || []).join(", ");
  $("groupScore5h").value = group.limits.score_per_5h ?? "";
  $("groupScoreWeek").value = group.limits.score_per_week ?? "";
  $("groupMaxTokensMsg").value = group.limits.max_tokens_per_message ?? "";
  $("groupMaxToolsMsg").value = group.limits.max_tool_calls_per_message ?? "";
  $("groupInputTokenWeight").value = group.limits.input_token_weight ?? "";
  $("groupOutputTokenWeight").value = group.limits.output_token_weight ?? "";
  $("groupToolCallWeight").value = group.limits.tool_call_weight ?? "";
  $("groupThinkingSecondWeight").value =
    group.limits.thinking_second_weight ?? "";
  $("groupEnabled").value = String(!!group.enabled);
  openGroupEditor();
};
renderGroups = function (groups) {
  ensureGroupUi();
  const grid = $("groupsGrid");
  if (!grid) return;
  groups = groups || [];
  if (selectedGroupName && !groups.some((g) => g.name === selectedGroupName))
    selectedGroupName = "";
  const nextHtml =
    groups
      .map(
        (g) =>
          `<div class="api-card"><div class="api-card-head"><h3>${g.name}<br><span class="label">${g.enabled ? "enabled" : "disabled"} · access ${(g.allowed_targets || []).join(", ") || "*"}</span></h3><span class="preset-actions"><button class="iconbtn" title="Edit" onclick="editGroup('${g.name}')">${svgIcon("edit")}</button><button class="iconbtn" title="Delete" onclick="deleteGroupByName('${g.name}')">${svgIcon("delete")}</button></span></div><p>${g.description || "No description"}</p><p class="label">Configured budgets · ${quotaBudgetLine(g.limits || {})}</p><p class="label">Configured weights · ${quotaWeightLine(g.limits || {})}</p><p class="label">Resolved budgets · ${quotaBudgetLine(g.resolved_limits || g.limits || {})}</p><p class="label">Resolved weights · ${quotaWeightLine(g.resolved_limits || g.limits || {})}</p></div>`,
      )
      .join("") || '<div class="value">No groups configured yet.</div>';
  setHtmlIfChanged(grid, nextHtml);
};
