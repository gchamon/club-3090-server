// Audit, instances, preset scopes, and host actions
let accessPolicyDraft = {};
let accessPolicyPersistedConfig = {};
const ACCESS_POLICY_KEYS = [
  "allow_proxy_without_api_key",
  "allow_proxy_with_invalid_api_key",
];

function accessPolicyPersistedValues(cfg = {}) {
  return ACCESS_POLICY_KEYS.reduce((values, key) => {
    values[key] = !!cfg[key];
    return values;
  }, {});
}

function accessPolicyResolvedValue(key, persisted) {
  return Object.prototype.hasOwnProperty.call(accessPolicyDraft, key)
    ? accessPolicyDraft[key]
    : !!persisted[key];
}

function accessPolicyHasDraft() {
  return ACCESS_POLICY_KEYS.some((key) =>
    Object.prototype.hasOwnProperty.call(accessPolicyDraft, key),
  );
}

function renderAccessPolicy(persisted) {
  const allowAnonymous = accessPolicyResolvedValue(
    "allow_proxy_without_api_key",
    persisted,
  );
  const allowDummy = accessPolicyResolvedValue(
    "allow_proxy_with_invalid_api_key",
    persisted,
  );
  const dirty = accessPolicyHasDraft();
  if ($("auditAllowAnonymousProxy"))
    $("auditAllowAnonymousProxy").checked = allowAnonymous;
  if ($("auditAllowDummyProxyKey"))
    $("auditAllowDummyProxyKey").checked = allowDummy;
  if ($("auditPolicyText")) {
    const persistedAnonymous = persisted.allow_proxy_without_api_key;
    const persistedDummy = persisted.allow_proxy_with_invalid_api_key;
    const persistedText = `Requests without an API key are <b>${persistedAnonymous ? "allowed" : "rejected"}</b>; requests with unrecognized API keys (dummy keys) are <b>${persistedDummy ? "allowed" : "rejected"}</b>.`;
    const draftText = dirty
      ? ` Unsaved changes: requests without an API key are <b>${allowAnonymous ? "allowed" : "rejected"}</b>; requests with unrecognized API keys (dummy keys) are <b>${allowDummy ? "allowed" : "rejected"}</b>.`
      : "";
    setHtmlIfChanged(
      $("auditPolicyText"),
      `${dirty ? "Persisted policy: " : ""}${persistedText}${draftText} Admin UI remains under <code>:${(lastStatus && lastStatus.admin_port) || 8008}${(persisted.admin_path || "/admin")}</code>.`,
    );
  }
}

function setAccessPolicyDraft(allowAnonymous, allowDummy) {
  const values = {
    allow_proxy_without_api_key: !!allowAnonymous,
    allow_proxy_with_invalid_api_key: !!allowDummy,
  };
  const persisted = accessPolicyPersistedValues(accessPolicyPersistedConfig);
  ACCESS_POLICY_KEYS.forEach((key) => {
    if (values[key] === persisted[key]) delete accessPolicyDraft[key];
    else accessPolicyDraft[key] = values[key];
  });
  renderAccessPolicy(persisted);
}

renderAudit = function (cfg) {
  cfg = cfg || {};
  accessPolicyPersistedConfig = {
    ...accessPolicyPersistedConfig,
    ...cfg,
  };
  const persisted = accessPolicyPersistedValues(accessPolicyPersistedConfig);
  const adminPort = (lastStatus && lastStatus.admin_port) || 8008;
  const proxyPort = (lastStatus && lastStatus.proxy_port) || 8009;
  const adminPath = cfg.admin_path || "/admin";
  const online = !!cfg.online_enabled;
  const localEnabled = !!cfg.local_api_enabled;
  const localPort = cfg.local_api_port || 10881;
  if ($("auditAdminEndpoint"))
    setHtmlIfChanged($("auditAdminEndpoint"), `:${adminPort}${adminPath}`);
  if ($("auditProxyEndpoint"))
    setHtmlIfChanged($("auditProxyEndpoint"), `:${proxyPort}`);
  if ($("auditExposure"))
    $("auditExposure").textContent = online
      ? "online through proxy/admin only"
      : "local/private only";
  if ($("auditLocalApi"))
    $("auditLocalApi").textContent = localEnabled
      ? `127.0.0.1:${localPort}`
      : "disabled";
  if ($("auditSummary"))
    setHtmlIfChanged(
      $("auditSummary"),
      "Audit entries capture admin actions, proxy authentication outcomes, quota denials, API usage, group changes, and user-management events. Use the shared log viewer below to inspect either Docker runtime logs or the audit log stream.",
    );
  renderAccessPolicy(persisted);
};
saveAuthSettings = async function () {
  const allowAnonymous = !!(
    $("auditAllowAnonymousProxy") && $("auditAllowAnonymousProxy").checked
  );
  const allowDummy = !!(
    $("auditAllowDummyProxyKey") && $("auditAllowDummyProxyKey").checked
  );
  try {
    const r = await fetch("/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "save_server_config",
        allow_proxy_without_api_key: allowAnonymous,
        allow_proxy_with_invalid_api_key: allowDummy,
      }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "config failed");
    accessPolicyPersistedConfig = { ...j.server_config };
    accessPolicyDraft = {};
    renderAudit(j.server_config);
    setAuditMsg("Saved access policy");
    await refreshStatus({ force: true });
  } catch (e) {
    alert("Access policy failed: " + e);
  }
};
function syncInstanceUtilityButtons(target) {
  const runScriptButton = $("instanceRunScriptBtn");
  const imageStudioButton = $("instanceSetupImageStudioBtn");
  const separator = $("instanceUtilitySeparator");
  const visible = scopeIsGlobal() || !!target;
  if (separator) separator.classList.toggle("hidden", !visible);
  if (runScriptButton) {
    runScriptButton.classList.toggle("hidden", !visible);
    setInstanceScopeDisabled(runScriptButton, false);
  }
  if (imageStudioButton) {
    imageStudioButton.classList.toggle("hidden", !visible);
    const installed = aiStudioServiceInstalled();
    const busy = aiStudioSetupBusy();
    imageStudioButton.classList.toggle("red", installed);
    imageStudioButton.setAttribute("onclick", installed ? "removeImageStudio()" : "startImageStudioSetup()");
    imageStudioButton.innerHTML = `${imageStudioActionIconSvg()}<span>${escapeHtml(
      busy ? (installed ? "Removing AI Studio" : "Setup Running") : (installed ? "Remove AI Studio" : "Setup AI Studio"),
    )}</span>`;
    setInstanceScopeDisabled(imageStudioButton, false);
    imageStudioButton.disabled = !!busy;
  }
}
renderInstances = function (instances) {
  ensureV414Layout();
  const tabs = $("instanceTabs");
  const summary = $("instanceSummary");
  const btn = $("instanceEnableBtn");
  const panel = findPanelByHeading("system", "Instances");
  if (!tabs || !summary || !panel) return;
  instances = scopeItems();
  if (
    !selectedScope ||
    !(
      selectedScope === "GLOBAL" ||
      instances.some((x) => x.id === selectedScope)
    )
  )
    selectedScope =
      singleScopeItems()[0]?.id || pairScopeItems()[0]?.id || "GLOBAL";
  tabs.classList.add("scope-tabs");
  const singles = singleScopeItems();
  const pairs = orderedPairScopeItems();
  const tabParts = [
    `<button class="subtab ${scopeIsGlobal() ? "active" : ""}" onclick="setScope('GLOBAL')">Global</button>`,
  ];
  if (singles.length) {
    tabParts.push('<span class="scope-strip-separator" aria-hidden="true"></span>');
    tabParts.push(
      ...singles.map(
        (x) =>
          `<button class="subtab ${x.id === currentScope() ? "active" : ""}" onclick="setScope('${x.id}')">${x.id}${x.running ? " • on" : " • off"}</button>`,
      ),
    );
  }
  if (pairs.length) {
    tabParts.push('<span class="scope-strip-separator" aria-hidden="true"></span>');
    tabParts.push(
      ...pairs.map(
        (x) =>
          `<button class="subtab ${x.id === currentScope() ? "active" : ""}" onclick="setScope('${x.id}')">Pair ${(x.gpu_indices || []).join("+")}${x.running ? " • on" : " • off"}</button>`,
      ),
    );
  }
  if (gpuCount() >= 2) {
    tabParts.push('<span class="scope-strip-separator" aria-hidden="true"></span>');
    tabParts.push(
      `<button class="subtab scope-row-action" onclick="createPairGroup()">Create Custom Pair</button>`,
    );
  }
  const tabsHtml = tabParts.join("");
  setHtmlIfChanged(tabs, tabsHtml);
  ensurePairManager();
  const target = currentScopeInstance(false);
  const actionButtons = [...(panel.querySelectorAll("#instanceActionRow .btn") || [])];
  const startBtn = actionButtons[0] || null;
  const restartBtn = actionButtons[1] || null;
  const stopBtn = actionButtons[2] || null;
  const controlButtons = [startBtn, restartBtn, stopBtn, btn].filter(Boolean);
  const anyRunning = scopeItems().some((item) => !!item.running);
  const targetRunning = !!(target && target.running);
  const allEnabled = scopeItems().length > 0 && scopeItems().every((item) => !!item.enabled);
  const scoreLock = typeof benchmarkJobActive === "function" && benchmarkJobActive();
  if (scopeIsGlobal()) {
    setHtmlIfChanged(
      summary,
      `Global scope controls every configured runtime at once. ${anyRunning ? "Use Stop or Restart to manage all active instances together." : "Use Start to bring up every configured instance together."} ${allEnabled ? "Autoboot is enabled for all configured scopes." : "Autoboot is not enabled for every configured scope."}`,
    );
    if (btn) {
      setInstanceScopeDisabled(btn, false);
      btn.textContent = allEnabled
        ? "Disable Boot Autostart"
        : "Enable Boot Autostart";
    }
    controlButtons.forEach((x) => setInstanceScopeDisabled(x, scoreLock));
  } else if (target) {
    setHtmlIfChanged(summary, `${scopeLabel(target)} · ${target.assignment_text} · port ${target.port} · ${target.running ? "running" : "stopped"} · proxy <code>${target.proxy_prefix}/</code> · ${target.enabled ? "autostart enabled" : "autostart disabled"}`);
    if (btn) {
      setInstanceScopeDisabled(btn, false);
      btn.textContent = target.enabled
        ? "Disable Boot Autostart"
        : "Enable Boot Autostart";
    }
    controlButtons.forEach((x) => setInstanceScopeDisabled(x, scoreLock));
  } else {
    summary.textContent = "No GPU instances configured";
    if (btn) {
      setInstanceScopeDisabled(btn, true);
      btn.textContent = "Boot autostart unavailable";
    }
    controlButtons.forEach((x) => setInstanceScopeDisabled(x, true));
  }
  if (scopeIsGlobal()) {
    if (startBtn) startBtn.textContent = anyRunning ? "Stop" : "Start";
    if (startBtn) startBtn.setAttribute("onclick", anyRunning ? "instanceAction('stop_container')" : "instanceAction('start_instance')");
    if (restartBtn) restartBtn.style.display = anyRunning ? "" : "none";
    if (stopBtn) stopBtn.style.display = "none";
  } else {
    if (startBtn) startBtn.textContent = targetRunning ? "Stop" : "Start";
    if (startBtn) startBtn.setAttribute("onclick", targetRunning ? "instanceAction('stop_container')" : "instanceAction('start_instance')");
    if (restartBtn) restartBtn.style.display = targetRunning ? "" : "none";
    if (stopBtn) stopBtn.style.display = "none";
  }
  syncInstanceUtilityButtons(target);
  renderLogInstanceSelector();
};
renderPresetScopeTabs = function () {
  ensureDynamicPresetLayout();
  const tabs = $("presetScopeTabs");
  const summary = $("presetScopeSummary");
  if (!tabs || !summary) return;
  const scopes = [{ id: "GLOBAL", display_name: "Global" }, ...scopeItems()];
  const tabsHtml = scopes
    .map(
      (item) =>
        `<button class="subtab${selectedScope === item.id ? " active" : ""}" onclick="setScope('${escapeJs(item.id)}', true)">${escapeHtml(item.id === "GLOBAL" ? "Global" : scopeLabel(item))}</button>`,
    )
    .join("");
  setHtmlIfChanged(tabs, tabsHtml);
  if (scopeIsGlobal()) {
    summary.textContent =
      "Global scope fans single-GPU presets out across every GPU, dual presets across every two-GPU pair, and multi-GPU presets into the shared runtime.";
  } else {
    const current = currentScopeInstance(true) || currentScopeInstance(false);
    summary.textContent = current
      ? `${scopeLabel(current)} selected. Matching ${current.kind === "dual" ? "dual" : "single"} presets below will apply to this scope.`
      : "Select a scope to apply discovered presets.";
  }
};
updateScopedCards = function () {
  const target = currentScopeInstance(false);
  const scoreLock = typeof benchmarkJobActive === "function" && benchmarkJobActive();
  const profileNote = scoreLock
    ? "Power profiles cannot be managed during a Model Scores benchmark."
    : `${scopeIsGlobal() ? "Global" : scopeLabel(target)} scope: applying a power profile resets the recorded GPU peak values and starts a fresh measurement session.`;
  const powerNote = scoreLock
    ? "Optimizations and cooling cannot be managed during a Model Scores benchmark."
    : `${scopeIsGlobal() ? "Global" : scopeLabel(target)} scope: optimization and cooling actions use the selected runtime context while keeping host-level power state in sync.`;
  if ($("profileScopeNote"))
    $("profileScopeNote").innerHTML = profileNote;
  if ($("powerScopeNote"))
    $("powerScopeNote").innerHTML = powerNote;
  [...(document.querySelectorAll("#systemConfigPanel button, #systemConfigPanel select") || [])].forEach((button) =>
    setInstanceScopeDisabled(button, scoreLock),
  );
  if (typeof renderSystemConfiguration === "function") renderSystemConfiguration(lastStatus);
  renderLogSourcePanel();
};
powerAction = async function (a) {
  if (typeof benchmarkJobActive === "function" && benchmarkJobActive()) {
    alert("Model Scores benchmarking is running. Cancel the benchmark before changing runtime state.");
    return;
  }
  const cur = scopeIsGlobal() ? { id: "GLOBAL", enabled: scopeItems().length > 0 && scopeItems().every((item) => !!item.enabled) } : currentScopeInstance(false);
  const needsTarget = [
    "stop_container",
    "start_instance",
    "restart_instance",
    "toggle_enabled",
  ].includes(a);
  if (needsTarget && !cur) {
    alert("Select a GPU or Pair scope first.");
    return;
  }
  if (a === "stop_container" && !(await openClubConfirmModal(`Stop ${scopeLabel(cur)} now?`)))
    return;
  try {
    await post("/admin/power", {
      action: a,
      instance_id: cur ? cur.id : null,
      enabled: cur ? !cur.enabled : undefined,
    });
  } catch (e) {
    alert(e);
  }
};
instanceAction = async function (a) {
  await powerAction(a);
};
toggleInstanceEnabled = async function () {
  if (typeof benchmarkJobActive === "function" && benchmarkJobActive()) {
    alert("Model Scores benchmarking is running. Cancel the benchmark before changing boot autostart.");
    return;
  }
  const cur = scopeIsGlobal() ? { id: "GLOBAL", enabled: scopeItems().length > 0 && scopeItems().every((item) => !!item.enabled) } : currentScopeInstance(false);
  if (!cur) {
    alert("Select a GPU or Pair scope first.");
    return;
  }
  try {
    await post("/admin/power", {
      action: "toggle_enabled",
      instance_id: cur.id,
      enabled: !cur.enabled,
    });
  } catch (e) {
    alert(e);
  }
};
async function createPairGroup(first = null, second = null) {
  if (gpuCount() < 2) {
    alert("At least two GPUs are required to create a dual pair.");
    return false;
  }
  if (first === null || second === null) {
    openCreateCustomPairModal();
    return false;
  }
  const a = Number(first);
  const b = Number(second);
  const id = canonicalPairId(a, b);
  if (!id) {
    alert("Select two distinct GPU indices.");
    return false;
  }
  if (scopeItems().some((item) => String(item?.id || "") === id)) {
    alert(`Pair ${id} already exists.`);
    return false;
  }
  try {
    const r = await fetch("/admin/instances", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "save_pair",
        gpu_indices: [Number(a), Number(b)],
        mode: "vllm/dual",
        enabled: false,
      }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "pair save failed");
    setInstanceMsg(`Saved pair group ${id}`);
    await refreshStatus();
    setScope(id, false);
    return true;
  } catch (e) {
    alert("Pair group failed: " + e);
    return false;
  }
}
function nextAvailableCustomPairSelection() {
  const existing = new Set(scopeItems().map((item) => String(item?.id || "")));
  const pair = allPairChoices().find(
    ([a, b]) => !existing.has(canonicalPairId(a, b)),
  );
  return pair || [];
}
function ensureCreateCustomPairModal() {
  if ($("createCustomPairModal")) return;
  const modal = document.createElement("div");
  modal.id = "createCustomPairModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card conversation-modal-card custom-pair-modal-card" role="dialog" aria-modal="true" aria-labelledby="createCustomPairTitle"><div class="panel-head"><h2 id="createCustomPairTitle">Create Custom Pair</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeCreateCustomPairModal()">✕</button></div><div class="preset-help">Choose two GPUs to create a persistent custom dual-GPU scope for non-default layouts.</div><div class="formgrid custom-pair-form-grid"><label>First GPU<select id="createCustomPairFirst"></select></label><label>Second GPU<select id="createCustomPairSecond"></select></label></div><div class="preset-form-actions"><button class="btn blue" onclick="closeCreateCustomPairModal()">Cancel</button><button class="btn green" onclick="submitCreateCustomPairModal()">Create Pair</button></div><div class="msg" id="createCustomPairMsg"></div></div>`;
  document.body.appendChild(modal);
}
function populateCreateCustomPairSelects(firstValue = "", secondValue = "") {
  const firstSelect = $("createCustomPairFirst");
  const secondSelect = $("createCustomPairSecond");
  if (!firstSelect || !secondSelect) return;
  const options = Array.from({ length: gpuCount() }, (_, index) => index)
    .map(
      (index) =>
        `<option value="${index}">${escapeHtml(gpuOptionLabel(index))}</option>`,
    )
    .join("");
  setSelectOptions(firstSelect, options);
  setSelectOptions(secondSelect, options);
  const defaultFirst = firstValue !== "" ? String(firstValue) : String(nextAvailableCustomPairSelection()[0] ?? 0);
  const defaultSecond =
    secondValue !== ""
      ? String(secondValue)
      : String(
          nextAvailableCustomPairSelection()[1] ??
            Math.min(1, Math.max(0, gpuCount() - 1)),
        );
  firstSelect.value = defaultFirst;
  secondSelect.value = defaultSecond === defaultFirst && gpuCount() > 1 ? String((Number(defaultFirst) + 1) % gpuCount()) : defaultSecond;
}
function openCreateCustomPairModal() {
  if (gpuCount() < 2) {
    alert("At least two GPUs are required to create a dual pair.");
    return;
  }
  if (!nextAvailableCustomPairSelection().length) {
    alert("All available GPU pair combinations already exist.");
    return;
  }
  ensureCreateCustomPairModal();
  populateCreateCustomPairSelects();
  setElementMsg("createCustomPairMsg", "");
  $("createCustomPairModal")?.classList.remove("hidden");
}
function closeCreateCustomPairModal() {
  $("createCustomPairModal")?.classList.add("hidden");
}
async function submitCreateCustomPairModal() {
  const first = Number($("createCustomPairFirst")?.value ?? -1);
  const second = Number($("createCustomPairSecond")?.value ?? -1);
  if (!Number.isInteger(first) || !Number.isInteger(second)) {
    setElementMsg("createCustomPairMsg", "Choose two GPUs first.", "error");
    return;
  }
  if (first === second) {
    setElementMsg("createCustomPairMsg", "Choose two different GPUs.", "error");
    return;
  }
  const id = canonicalPairId(first, second);
  if (!id) {
    setElementMsg("createCustomPairMsg", "Choose a valid GPU pair.", "error");
    return;
  }
  if (scopeItems().some((item) => String(item?.id || "") === id)) {
    setElementMsg("createCustomPairMsg", `${id} already exists.`, "error");
    return;
  }
  setElementMsg("createCustomPairMsg", "");
  if (await createPairGroup(first, second)) closeCreateCustomPairModal();
}
async function deleteCurrentPairGroup() {
  const cur = currentScopeInstance(true);
  if (!cur || cur.kind !== "dual") {
    alert("Select a dual pair scope first.");
    return;
  }
  if (cur.auto_pair) {
    alert("Built-in sequential pair groups cannot be deleted.");
    return;
  }
  if (!(await openClubConfirmModal(`Delete pair group ${cur.id}?`))) return;
  try {
    const r = await fetch("/admin/instances", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "delete_pair", instance_id: cur.id }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "pair delete failed");
    setInstanceMsg(`Deleted pair group ${cur.id}`);
    await refreshStatus();
    setScope("GLOBAL", false);
  } catch (e) {
    alert("Pair delete failed: " + e);
  }
}
switchMode = async function (m) {
  if (typeof benchmarkJobActive === "function" && benchmarkJobActive()) {
    alert("Model Scores benchmarking is running. Cancel the benchmark before launching presets.");
    return;
  }
  const cur = currentScopeInstance(true);
  if (!cur || cur.kind === "dual") {
    alert("Select a single GPU tab to apply a single-GPU preset.");
    return;
  }
  const blockingPair = pairScopeItems().find(
    (x) => x.running && (x.gpu_indices || []).includes(Number(cur.gpu_index)),
  );
  const warning = blockingPair
    ? `\n\nWarning: GPU ${cur.gpu_index} is currently occupied by ${blockingPair.id} running ${blockingPair.mode}. Continuing will stop that pair and replace it with ${m} on ${cur.id}.`
    : "";
  if (await openClubConfirmModal(`Assign ${m} to ${cur.id} and start it?${warning}`))
    try {
      await post("/admin/switch", { instance_id: cur.id, mode: m });
    } catch (e) {
      alert(e);
    }
};
async function switchDualMode(m) {
  if (typeof benchmarkJobActive === "function" && benchmarkJobActive()) {
    alert("Model Scores benchmarking is running. Cancel the benchmark before launching presets.");
    return;
  }
  const cur = currentScopeInstance(false);
  if (!cur || cur.kind !== "dual") {
    alert("Choose a dual pair tab before applying a dual preset.");
    return;
  }
  if (
    await openClubConfirmModal(
      `Apply dual preset ${m} to ${cur.id} on GPUs ${(cur.gpu_indices || []).join(", ")}? This will stop overlapping runtimes that already use those GPUs.`,
    )
  )
    try {
      await post("/admin/switch", { instance_id: cur.id, mode: m });
    } catch (e) {
      alert(e);
    }
}
function profileDescription(p) {
  const d = {
    eco: "Eco profile: 240W active GPU cap, lower idle clocks, powersave CPU governor, faster idle/container stop timers.",
    balanced:
      "Balanced profile: default server profile with 280W active GPU cap, idle downclocking after 10 minutes, and container stop after 1 hour.",
    "benchmark-ready":
      "Benchmark Ready profile: caps active GPU power at 220W, disables idle downclocking, keeps fans available for the benchmark lock, and uses longer idle timers for validation runs.",
    fast:
      "Fast profile: 300W active GPU cap for the first speed benchmark pass, no idle clock locking, schedutil CPU while active, and standard idle timers.",
    turbo:
      "Turbo profile: 350W active GPU allowance, performance CPU governor, relaxed idle timers, and minimal downclocking. Use when performance matters more than power.",
  };
  return d[p] || "Apply profile?";
}
const SYSTEM_POWER_PROFILE_OPTIONS = [
  ["benchmark-ready", "Benchmark Ready (220W)"],
  ["eco", "Eco (240W)"],
  ["balanced", "Balanced (280W)"],
  ["fast", "Fast (300W)"],
  ["turbo", "Turbo (350W)"],
];
const SYSTEM_GPU_PROFILE_OPTIONS = SYSTEM_POWER_PROFILE_OPTIONS;
const SYSTEM_CPU_PROFILE_OPTIONS = [
  ["adaptive", "Adaptive (schedutil)"],
  ["performance", "Performance"],
];
let systemConfigDraft = {};
function systemConfigCurrent(status = lastStatus) {
  const power = status?.power || {};
  const cfg = status?.server_config || {};
  return {
    gpu_profile: String(power.gpu_profile || cfg.active_gpu_power_profile || power.profile || cfg.active_power_profile || "balanced").trim().toLowerCase(),
    cpu_profile: String(power.cpu_profile || cfg.active_cpu_power_profile || "performance").trim().toLowerCase(),
    optimizations: power.optimizations_enabled === false ? "disabled" : "enabled",
    fan_mode: power.fan_manual_override ? "manual_max" : "auto",
    fan_scope: String(cfg.fan_override_instance_id || currentScope() || "GLOBAL").trim().toUpperCase() || "GLOBAL",
  };
}
function systemConfigValue(key, current) {
  return Object.prototype.hasOwnProperty.call(systemConfigDraft, key)
    ? String(systemConfigDraft[key] || "")
    : String(current[key] || "");
}
function systemConfigScopeOptions(currentValue) {
  const rows = [{ id: "GLOBAL", label: "Global" }, ...scopeItems().map((row) => ({ id: row.id, label: scopeLabel(row) }))];
  const seen = new Set();
  return rows
    .filter((row) => {
      const id = String(row.id || "").trim().toUpperCase();
      if (!id || seen.has(id)) return false;
      seen.add(id);
      return true;
    })
    .map((row) => {
      const id = String(row.id || "").trim().toUpperCase();
      return `<option value="${escapeHtml(id)}"${id === String(currentValue || "").toUpperCase() ? " selected" : ""}>${escapeHtml(row.label || id)}</option>`;
    })
    .join("");
}
function systemConfigSelectOptions(options, currentValue) {
  const selected = String(currentValue || "");
  return options
    .map(([value, label]) => `<option value="${escapeHtml(value)}"${String(value) === selected ? " selected" : ""}>${escapeHtml(label)}</option>`)
    .join("");
}
function systemConfigPrettyValue(key, value) {
  const raw = String(value || "");
  if (key === "gpu_profile") return (SYSTEM_GPU_PROFILE_OPTIONS.find(([id]) => id === raw) || [raw, raw])[1] || raw;
  if (key === "cpu_profile") return (SYSTEM_CPU_PROFILE_OPTIONS.find(([id]) => id === raw) || [raw, raw])[1] || raw;
  if (key === "optimizations") return raw === "enabled" ? "Enabled" : "Disabled";
  if (key === "fan_mode") return raw === "manual_max" ? "Fans Max" : "Automatic Fans";
  if (key === "fan_scope") {
    if (raw === "GLOBAL") return "Global";
    return scopeLabel(scopeItems().find((row) => String(row?.id || "").toUpperCase() === raw) || { id: raw });
  }
  return raw;
}
function systemConfigRowHtml({ key, title, detail, current, controlHtml, applyAction }) {
  const currentValue = String(current[key] || "");
  const draftValue = systemConfigValue(key, current);
  const dirty = draftValue !== currentValue;
  const locked = typeof benchmarkJobActive === "function" && benchmarkJobActive();
  return `<div class="system-config-row${dirty ? " system-config-row-dirty" : ""}" data-system-config-key="${escapeHtml(key)}"><div class="system-config-copy"><div class="system-config-title-row"><span class="system-config-title">${escapeHtml(title)}</span>${dirty ? '<span class="status-badge status-warning">changed</span>' : '<span class="status-badge status-production">saved</span>'}</div><div class="system-config-current">Current: <strong>${escapeHtml(systemConfigPrettyValue(key, currentValue))}</strong></div><div class="preset-help">${escapeHtml(detail)}</div></div><div class="system-config-control">${controlHtml}</div><button class="btn green system-config-apply-btn" ${dirty && !locked ? "" : "disabled"} onclick="${escapeHtml(applyAction)}">Apply</button></div>`;
}
function renderSystemConfiguration(status = lastStatus) {
  const grid = $("systemConfigGrid");
  if (!grid) return;
  const current = systemConfigCurrent(status);
  const gpuProfileValue = systemConfigValue("gpu_profile", current);
  const cpuProfileValue = systemConfigValue("cpu_profile", current);
  const optimizationsValue = systemConfigValue("optimizations", current);
  const fanModeValue = systemConfigValue("fan_mode", current);
  const fanScopeValue = systemConfigValue("fan_scope", current);
  const dirtyKeys = ["gpu_profile", "cpu_profile", "optimizations", "fan_mode", "fan_scope"].filter((key) => systemConfigValue(key, current) !== String(current[key] || ""));
  if ($("systemConfigCurrentBadge")) {
    $("systemConfigCurrentBadge").textContent = dirtyKeys.length ? `${dirtyKeys.length} unsaved` : "current";
    $("systemConfigCurrentBadge").className = `status-badge ${dirtyKeys.length ? "status-warning" : "status-production"}`;
  }
  if (!["gpu_profile", "cpu_profile", "optimizations", "cooling"].every((key) => grid.querySelector(`[data-system-config-key="${key}"]`))) {
    grid.innerHTML = [
      systemConfigRowHtml({
        key: "gpu_profile",
        title: "GPU Power Profile",
        detail: "Sets active and idle GPU power limits, idle clocks, and idle timers.",
        current,
        controlHtml: `<select class="system-config-select" id="systemConfigGpuProfile" onchange="setSystemConfigDraft('gpu_profile', this.value)">${systemConfigSelectOptions(SYSTEM_GPU_PROFILE_OPTIONS, gpuProfileValue)}</select>`,
        applyAction: "applySystemConfigGpuProfile()",
      }),
      systemConfigRowHtml({
        key: "cpu_profile",
        title: "CPU Power Profile",
        detail: "Selects the active CPU governor. Idle operation uses powersave in both modes.",
        current,
        controlHtml: `<select class="system-config-select" id="systemConfigCpuProfile" onchange="setSystemConfigDraft('cpu_profile', this.value)">${systemConfigSelectOptions(SYSTEM_CPU_PROFILE_OPTIONS, cpuProfileValue)}</select>`,
        applyAction: "applySystemConfigCpuProfile()",
      }),
      systemConfigRowHtml({
        key: "optimizations",
        title: "Power Optimizations",
        detail: "Controls active power management and idle power behavior for the selected scope.",
        current,
        controlHtml: `<select class="system-config-select" id="systemConfigOptimizations" onchange="setSystemConfigDraft('optimizations', this.value)">${systemConfigSelectOptions([["enabled", "Enabled"], ["disabled", "Disabled"]], optimizationsValue)}</select>`,
        applyAction: "applySystemConfigOptimizations()",
      }),
      `<div class="system-config-row" data-system-config-key="cooling"><div class="system-config-copy"><div class="system-config-title-row"><span class="system-config-title">Cooling</span><span class="status-badge status-production">saved</span></div><div class="system-config-current">Current: <strong></strong> · <strong></strong></div><div class="preset-help">Sets fans to automatic control or manual max for the selected GPU scope.</div></div><div class="system-config-control system-config-control-pair"><select class="system-config-select" id="systemConfigFanMode" onchange="setSystemConfigDraft('fan_mode', this.value)"></select><select class="system-config-select" id="systemConfigFanScope" onchange="setSystemConfigDraft('fan_scope', this.value)"></select></div><button class="btn green system-config-apply-btn" disabled onclick="applySystemConfigCooling()">Apply</button></div>`,
    ].join("");
  }
  const rows = {
    gpu_profile: grid.querySelector('[data-system-config-key="gpu_profile"]'),
    cpu_profile: grid.querySelector('[data-system-config-key="cpu_profile"]'),
    optimizations: grid.querySelector('[data-system-config-key="optimizations"]'),
    cooling: grid.querySelector('[data-system-config-key="cooling"]'),
  };
  const selectSpecs = [
    [rows.gpu_profile, "systemConfigGpuProfile", "gpu_profile", SYSTEM_GPU_PROFILE_OPTIONS],
    [rows.cpu_profile, "systemConfigCpuProfile", "cpu_profile", SYSTEM_CPU_PROFILE_OPTIONS],
    [rows.optimizations, "systemConfigOptimizations", "optimizations", [["enabled", "Enabled"], ["disabled", "Disabled"]]],
    [rows.cooling, "systemConfigFanMode", "fan_mode", [["auto", "Automatic Fans"], ["manual_max", "Fans Max"]]],
    [rows.cooling, "systemConfigFanScope", "fan_scope", null],
  ];
  selectSpecs.forEach(([row, id, key, options]) => {
    const select = $(id);
    if (!select || !row) return;
    const value = systemConfigValue(key, current);
    const html = options ? systemConfigSelectOptions(options, value) : systemConfigScopeOptions(value);
    if (select.innerHTML !== html) select.innerHTML = html;
    if (select.value !== value) select.value = value;
  });
  const locked = typeof benchmarkJobActive === "function" && benchmarkJobActive();
  Object.entries(rows).forEach(([key, row]) => {
    if (!row) return;
    const dirty = key === "cooling"
      ? fanModeValue !== current.fan_mode || fanScopeValue !== current.fan_scope
      : systemConfigValue(key, current) !== String(current[key] || "");
    row.classList.toggle("system-config-row-dirty", dirty);
    const badge = row.querySelector(".status-badge");
    if (badge) {
      badge.textContent = dirty ? "changed" : "saved";
      badge.className = `status-badge ${dirty ? "status-warning" : "status-production"}`;
    }
    const currentLabel = row.querySelector(".system-config-current");
    if (currentLabel) {
      currentLabel.innerHTML = key === "cooling"
        ? `Current: <strong>${escapeHtml(systemConfigPrettyValue("fan_mode", current.fan_mode))}</strong> · <strong>${escapeHtml(systemConfigPrettyValue("fan_scope", current.fan_scope))}</strong>`
        : `Current: <strong>${escapeHtml(systemConfigPrettyValue(key, current[key]))}</strong>`;
    }
    const apply = row.querySelector(".system-config-apply-btn");
    if (apply) apply.disabled = !dirty || locked;
  });
  syncPowerCoolingBusyState();
}
async function applySystemConfigGpuProfile() {
  const current = systemConfigCurrent(lastStatus);
  const next = systemConfigValue("gpu_profile", current);
  if (!next || next === current.gpu_profile) return;
  try {
    await withPowerCoolingBusy("Applying GPU power profile...", async () => {
      await post("/admin/profile", { gpu_profile: next, instance_id: currentScope() || "GLOBAL" }, `/admin/profile gpu=${next}`);
    });
    delete systemConfigDraft.gpu_profile;
    await refreshStatus({ force: true });
  } catch (e) {
    setMsg(`GPU power profile failed: ${messageText(e)}`);
  }
}
async function applySystemConfigCpuProfile() {
  const current = systemConfigCurrent(lastStatus);
  const next = systemConfigValue("cpu_profile", current);
  if (!next || next === current.cpu_profile) return;
  try {
    await withPowerCoolingBusy("Applying CPU power profile...", async () => {
      await post("/admin/profile", { cpu_profile: next, instance_id: currentScope() || "GLOBAL" }, `/admin/profile cpu=${next}`);
    });
    delete systemConfigDraft.cpu_profile;
    await refreshStatus({ force: true });
  } catch (e) {
    setMsg(`CPU power profile failed: ${messageText(e)}`);
  }
}
async function applySystemConfigOptimizations() {
  const current = systemConfigCurrent(lastStatus);
  const next = systemConfigValue("optimizations", current);
  if (!next || next === current.optimizations) return;
  try {
    await withPowerCoolingBusy(`${next === "enabled" ? "Enabling" : "Disabling"} power optimizations...`, async () => {
      await post(
        "/admin/power",
        { action: next === "enabled" ? "enable_optimizations" : "disable_optimizations", instance_id: currentScope() || "GLOBAL" },
        `/admin/power ${next}`,
      );
    });
    delete systemConfigDraft.optimizations;
    await refreshStatus({ force: true });
  } catch (e) {
    setMsg(`Power optimizations failed: ${messageText(e)}`);
  }
}
async function applySystemConfigCooling() {
  const current = systemConfigCurrent(lastStatus);
  const mode = systemConfigValue("fan_mode", current);
  const scope = systemConfigValue("fan_scope", current) || "GLOBAL";
  if (mode === current.fan_mode && scope === current.fan_scope) return;
  try {
    await withPowerCoolingBusy(mode === "manual_max" ? "Setting fans to max..." : "Resetting fans to automatic...", async () => {
      await post(
        "/admin/power",
        { action: mode === "manual_max" ? "fans_max" : "fans_auto", instance_id: scope },
        `/admin/power ${mode} ${scope}`,
      );
    });
    delete systemConfigDraft.fan_mode;
    delete systemConfigDraft.fan_scope;
    await refreshStatus({ force: true });
  } catch (e) {
    setMsg(`Cooling configuration failed: ${messageText(e)}`);
  }
}
profile = async function (p) {
  if (typeof benchmarkJobActive === "function" && benchmarkJobActive()) {
    alert("Model Scores benchmarking is running. Cancel the benchmark before changing power profiles.");
    return;
  }
  const cur = currentScopeInstance(false);
  const instanceId = scopeIsGlobal() ? cur?.id || "GLOBAL" : cur?.id || null;
  const scopeText = scopeIsGlobal() ? "Global" : scopeLabel(cur);
  if (
    !(await openClubConfirmModal(
      profileDescription(p) +
        `\n\nApply this profile now to ${scopeText} scope and reset the recorded GPU peaks?`,
    ))
  )
    return;
  try {
    await post(
      "/admin/profile",
      { profile: p, instance_id: instanceId },
      `/admin/profile ${p} ${instanceId || "GLOBAL"}`,
    );
  } catch (e) {
    alert(e);
  }
};
function applyDirectoryPayload(j) {
  if (!lastStatus) lastStatus = {};
  if (Array.isArray(j.users)) {
    lastStatus.users = j.users;
    renderUsers(j.users);
  }
  if (Array.isArray(j.groups)) {
    lastStatus.groups = j.groups;
    renderGroups(j.groups);
  }
  if (j.server_config) {
    lastStatus.server_config = j.server_config;
    renderAudit(j.server_config);
  }
}
saveGroupForm = async function () {
  try {
    const r = await fetch("/admin/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "save", group: collectGroupForm() }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "group save failed");
    applyDirectoryPayload(j);
    resetGroupForm(true);
    setGroupsMsg("Saved group " + j.group.name);
    refreshStatus().catch(() => {});
  } catch (e) {
    alert("Group save failed: " + e);
  }
};
deleteGroupByName = async function (name) {
  if (!(await openClubConfirmModal("Delete group " + name + "?"))) return;
  try {
    const r = await fetch("/admin/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "delete", name }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "group delete failed");
    applyDirectoryPayload(j);
    if (selectedGroupName === name) resetGroupForm(true);
    setGroupsMsg("Deleted group " + name);
    refreshStatus().catch(() => {});
  } catch (e) {
    alert("Group delete failed: " + e);
  }
};
pairingEnabled = function () {
  return gpuCount() >= 2;
};
