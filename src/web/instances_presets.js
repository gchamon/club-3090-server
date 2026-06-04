// Audit, instances, preset scopes, and host actions
renderAudit = function (cfg) {
  cfg = cfg || {};
  ensureV414Layout();
  const adminPort = (lastStatus && lastStatus.admin_port) || 8008;
  const proxyPort = (lastStatus && lastStatus.proxy_port) || 8009;
  const adminPath = cfg.admin_path || "/admin";
  const online = !!cfg.online_enabled;
  const authOptional = !!cfg.allow_proxy_without_api_key;
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
  if ($("auditPolicyText"))
    setHtmlIfChanged(
      $("auditPolicyText"),
      `Proxy API keys are currently <b>${authOptional ? "optional" : "required"}</b>. Admin UI remains under <code>:${adminPort}${adminPath}</code>.`,
    );
  mirrorAuthToggles(authOptional);
};
saveAuthSettings = async function () {
  const allow = !!(
    $("auditAllowAnonymousProxy") && $("auditAllowAnonymousProxy").checked
  );
  mirrorAuthToggles(allow);
  try {
    const r = await fetch("/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "save_server_config",
        allow_proxy_without_api_key: allow,
      }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || "config failed");
    if (j.server_config) renderAudit(j.server_config);
    setAuditMsg("Saved access policy");
    await refreshStatus();
  } catch (e) {
    alert("Access policy failed: " + e);
  }
};
function syncInstanceUtilityButtons(target) {
  const utilityButtons = [$("instanceBenchmarkBtn"), $("instanceReportBtn"), $("instanceRebenchBtn")];
  const separator = $("instanceUtilitySeparator");
  const visible = !scopeIsGlobal() && !!target;
  const enabled = visible && !!target?.running;
  if (separator) separator.classList.toggle("hidden", !visible);
  utilityButtons.forEach((button) => {
    if (!button) return;
    button.classList.toggle("hidden", !visible);
    setInstanceScopeDisabled(button, !enabled);
  });
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
  const anyRunning = scopeItems().some((item) => !!item.running);
  const targetRunning = !!(target && target.running);
  const allEnabled = scopeItems().length > 0 && scopeItems().every((item) => !!item.enabled);
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
    actionButtons.forEach((x) => setInstanceScopeDisabled(x, false));
  } else if (target) {
    setHtmlIfChanged(summary, `${scopeLabel(target)} · ${target.assignment_text} · port ${target.port} · ${target.running ? "running" : "stopped"} · proxy <code>${target.proxy_prefix}/</code> · ${target.enabled ? "autostart enabled" : "autostart disabled"}`);
    if (btn) {
      setInstanceScopeDisabled(btn, false);
      btn.textContent = target.enabled
        ? "Disable Boot Autostart"
        : "Enable Boot Autostart";
    }
    actionButtons.forEach((x) => setInstanceScopeDisabled(x, false));
  } else {
    summary.textContent = "No GPU instances configured";
    if (btn) {
      setInstanceScopeDisabled(btn, true);
      btn.textContent = "Boot autostart unavailable";
    }
    actionButtons.forEach((x) => setInstanceScopeDisabled(x, true));
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
  if ($("profileScopeNote"))
    $("profileScopeNote").innerHTML = `${scopeIsGlobal() ? "Global" : scopeLabel(target)} scope: applying a power profile resets the recorded GPU peak values and starts a fresh measurement session.`;
  if ($("powerScopeNote"))
    $("powerScopeNote").innerHTML = `${scopeIsGlobal() ? "Global" : scopeLabel(target)} scope: optimization and cooling actions use the selected runtime context while keeping host-level power state in sync.`;
  renderLogSourcePanel();
};
powerAction = async function (a) {
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
    eco: "Eco profile: lower GPU power limits, lower idle clocks, powersave CPU governor, faster idle/container stop timers.",
    balanced:
      "Balanced profile: normal server profile with 280W active GPU cap, idle downclocking after 10 minutes, and container stop after 1 hour.",
    default:
      "Default profile: keeps the 280W safety GPU cap but removes idle clock locking, uses schedutil CPU while active, and keeps standard idle timers.",
    turbo:
      "Turbo profile: higher GPU power allowance, performance CPU governor, relaxed idle timers, and minimal downclocking. Use when performance matters more than power.",
  };
  return d[p] || "Apply profile?";
}
profile = async function (p) {
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
