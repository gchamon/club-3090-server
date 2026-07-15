var MODEL_SCORE_COMPARISON_KEY = "club3090.model-score-comparisons.v1";
var BENCHMARK_FLOATING_STATE_KEY = "club3090.benchmark-floating-state.v1";
var BENCHMARK_FINISHED_REVIEW_KEY = "club3090.benchmark-finished-review-dismissed.v1";
var RESOURCE_MANAGER_MODEL_ID = "__model_resources__";
var HIDDEN_PRESETS_MODEL_ID = "__hidden_presets__";
var AI_STUDIO_MODEL_ID = "__ai_studio__";
var MODEL_SCORE_COMPARISON_COLORS = [
  "#6aa6ff",
  "#7bd88f",
  "#f2b84b",
  "#ff7a90",
  "#a78bfa",
  "#4dd7c7",
  "#f97316",
  "#e879f9",
];
var MODEL_SCORE_METRIC_ORDER = [
  "speed",
  "efficiency",
  "context",
  "capabilities",
  "intelligence",
  "competence",
  "quality",
  "compliance",
  "reliability",
  "accessibility",
];
var MODEL_SCORE_RADAR_GROUPS = [
  { title: "Features", metricIds: ["capabilities", "compliance", "efficiency", "speed", "context"] },
  { title: "Usefulness", metricIds: ["competence", "intelligence", "reliability", "accessibility", "quality"] },
];
var MODEL_SCORE_METRIC_LABELS = {
  speed: "Speed",
  efficiency: "Efficiency",
  context: "Context",
  capabilities: "Capabilities",
  intelligence: "Intelligence",
  competence: "Competence",
  quality: "Quality",
  compliance: "Compliance",
  reliability: "Reliability",
  accessibility: "Accessibility",
};
var MODEL_SCORE_METRIC_DESCRIPTIONS = {
  speed: "Throughput and latency checks for how quickly the preset starts responding, processes prompts, and sustains token generation.",
  efficiency: "Resource-efficiency checks that compare useful output against GPU load, memory pressure, and runtime overhead.",
  context: "Long-context checks for prompt ingestion, retained instructions, and stability when the conversation or file set grows.",
  capabilities: "API and runtime capability checks for tool calling, vision support, structured outputs, and advertised serving features.",
  intelligence: "Reasoning and problem-solving checks that measure multi-step answers, planning, and inference quality.",
  competence: "Task-completion checks for practical coding, analysis, and instruction-following work that should succeed in normal use.",
  quality: "Answer-quality checks for correctness, helpfulness, formatting, and consistency across the quality benchmark packs.",
  compliance: "Safety and instruction-compliance checks that verify the preset follows requested constraints without drifting.",
  reliability: "Stability checks for repeatability, launch health, verification gates, and resilience under repeated requests.",
  accessibility: "Usability checks for clear output, readable formatting, and responses that remain easy to inspect in the admin panel.",
};
var MODEL_SCORE_SUBCATEGORY_DESCRIPTIONS = {
  "declared context": "Maximum context declared by the preset inventory; larger usable windows improve Context when the runtime can actually launch them.",
  "context per gpu": "Usable context normalized by the number of GPUs the preset occupies; stronger density keeps long-window presets practical on shared hardware.",
  "context probe": "Launch-time confirmation that the selected runtime accepted the configured context window instead of failing before prompt ingestion.",
  "tool surface": "Metadata signal for presets intended to handle tool-oriented workflows; tool-ready presets get more Capabilities credit.",
  "structured output": "Checks that the OpenAI-compatible route can carry structured request surfaces expected by clients and automation.",
  vision: "Vision capability from preset metadata; image-capable presets receive Capabilities credit when the served model advertises that surface.",
  "drafter mtp": "Speculative decoding or MTP drafter support from the preset definition; useful acceleration features improve Capabilities.",
  speculative: "Speculative decoding or MTP drafter support from the preset definition; useful acceleration features improve Capabilities.",
  endpoint: "Endpoint availability observed during launch; missing endpoints block harness probes and pull down Capabilities.",
  "gpu requirement": "Number of GPUs required by the preset on this rig; lower requirements are easier to schedule and improve Accessibility.",
  "model size": "Installed model footprint from inventory; smaller local model resources are easier to manage and improve Accessibility.",
  "installed resources": "Whether the preset's required files are already ready locally; missing downloads make the preset less immediately accessible.",
  "decode tps": "Sustained generation rate after the first token; this is the main Speed signal for long responses.",
  "wall tps": "End-to-end throughput including launch, routing, and request overhead; this captures what a user actually feels.",
  ttft: "Time to first token; lower startup latency improves interactive responsiveness and raises the Speed score.",
  "prompt processing": "Prefill throughput for prompt ingestion; stronger values help large-context chats and document-heavy requests start faster.",
  variance: "Coefficient of variation across throughput samples; steadier generation earns more Speed credit than spiky runs.",
  "narrative tps": "User-perceived wall throughput for the narrative benchmark prompt. It is reported for comparison and does not affect the Speed score.",
  "coding tps": "User-perceived wall throughput for the coding benchmark prompt. It is reported for comparison and does not affect the Speed score.",
  "thermal headroom": "Records when Fast-profile temperatures were too close to limits for a Turbo pass; limited headroom applies a Speed penalty.",
  "speed per topology": "Normalizes the Speed result by tensor-parallel cost so multi-GPU presets are judged against the hardware they occupy.",
  "cache footprint": "Local persistent cache storage used by the preset, shown in human-readable units. It is separate from Model Size and contributes to Efficiency by showing additional disk pressure created during use.",
  "system resource usage": "Parent card for peak memory pressure observed during the benchmark. It groups assigned VRAM and system RAM so the user can compare footprint bars without treating those readings as direct grades.",
  "peak vram": "Highest assigned-GPU VRAM usage sampled during the benchmark, displayed as GiB and percent of assigned VRAM. It matters because VRAM pressure predicts scheduling headroom and long-context stability, but this row remains informational.",
  "peak ram": "Highest system RAM usage sampled during the benchmark, displayed as GiB and percent of system memory. It matters because host memory pressure can destabilize launches or slow the rig, but this row remains informational.",
  "kv format": "KV-cache format from runtime metadata; quantized KV formats receive Context credit because they reduce cache pressure for long prompts.",
  "quality total": "Verifier-backed pass rate for the selected quality pack; this is the primary answer-correctness signal.",
  "tool calls": "Tool-call pack behavior when present; it checks whether structured tool requests are followed accurately.",
  "format following": "Instruction and structure-following behavior from the quality logs; strong formatting keeps answers usable by clients.",
  "quick behavior packs": "Quick-mode behavior checks for tool use and instruction following. In Quick mode this is the full Competence signal, so practical task success is not diluted by the separate ReasonMath intelligence probe.",
  "quick reasonmath": "Lightweight numeric reasoning pack used by Quick mode for Intelligence only; it is intentionally not counted again in Competence.",
  "full quality packs": "Full verifier pack pass rate across practical behavior tasks; this is the broad Competence signal in Full mode.",
  "reasoning suite": "Full reasoning, code, and math pack pass rate; this is the broad Intelligence signal in Full mode.",
  "adult safety": "Checks whether the preset handles sexual-content boundary prompts safely; this matters because permissive or evasive answers can make the model unsuitable for general deployment, and the pass rate directly explains this Compliance slice.",
  "illegal instructions": "Checks whether the preset refuses operational illegal-instruction requests; this matters because actionable wrongdoing guidance is a deployment blocker, and the pass rate directly explains this Compliance slice.",
  "child safety": "Safety harness category for child-safety boundaries and age-sensitive harmful content.",
  "violence and self harm": "Safety harness category for violent harm, weapons, and self-harm boundaries.",
  "cyber misuse": "Checks whether the preset refuses credential theft, exploit steps, and abusive cyber requests; this matters because unsafe cyber help can be immediately actionable, and the pass rate directly explains this Compliance slice.",
  cybersecurity: "Checks whether the preset separates defensive cyber help from abuse-enabling exploit guidance; this matters because cyber failures are high-risk, and the pass rate directly explains this Compliance slice.",
  "medical legal financial": "Checks whether the preset keeps high-stakes medical, legal, and financial answers general and appropriately qualified; this matters because overconfident advice can cause real-world harm, and the pass rate directly explains this Compliance slice.",
  "medical/legal/financial": "Checks whether the preset keeps high-stakes medical, legal, and financial answers general and appropriately qualified; this matters because overconfident advice can cause real-world harm, and the pass rate directly explains this Compliance slice.",
  privacy: "Checks whether the preset avoids exposing personal data, secrets, or doxxing-style information; this matters because privacy failures can directly harm users, and the pass rate directly explains this Compliance slice.",
  "privacy exfiltration": "Checks whether the preset refuses requests to obtain or expose another person's private data; this matters because privacy failures can directly harm users, and the pass rate directly explains this Compliance slice.",
  "misinformation manipulation": "Safety harness category for deception, propaganda, and manipulation requests.",
  "hate/harassment": "Checks whether the preset refuses hateful or protected-class harassment prompts; this matters because targeted abuse is a safety and usability failure, and the pass rate directly explains this Compliance slice.",
  "hate harassment": "Checks whether the preset refuses hateful or protected-class harassment prompts; this matters because targeted abuse is a safety and usability failure, and the pass rate directly explains this Compliance slice.",
  sexual: "Checks whether the preset handles sexual-content boundary prompts safely; this matters because permissive or evasive answers can make the model unsuitable for general deployment, and the pass rate directly explains this Compliance slice.",
  "dangerous encouragement": "Checks whether the preset refuses prompts that encourage dangerous acts; this matters because encouragement can be harmful even without detailed instructions, and the pass rate directly explains this Compliance slice.",
  jailbreak: "Checks whether the preset resists prompts that try to override safety or evaluation constraints; this matters because jailbreak susceptibility can invalidate every other guardrail, and the pass rate directly explains this Compliance slice.",
  "jailbreak resistance": "Checks whether the preset resists prompts that try to override safety or evaluation constraints; this matters because jailbreak susceptibility can invalidate every other guardrail, and the pass rate directly explains this Compliance slice.",
  "self harm safety": "Checks whether the preset responds to self-harm intent with supportive redirection instead of harmful advice; this matters because these failures are high severity, and the pass rate directly explains this Compliance slice.",
  "compliance total": "Overall compliance harness result when older artifacts did not preserve per-category rows.",
  verify: "Endpoint verification result. A pass proves the launched preset can serve the expected API shape.",
  stress: "Stress verification result. Repeated load checks expose runtime instability that a single smoke test can miss.",
  soak: "Soak verification result. Longer repeated sessions help catch failures that only appear after warmup or sustained use.",
  "recorded temperatures": "Parent card for the benchmark's thermal samples. It groups average and maximum core, junction, and VRAM temperatures so Reliability can show heat behavior without folding temperature into the score.",
  "average core temperature": "Mean GPU core temperature across assigned cards during the benchmark. It matters because sustained core heat reduces thermal headroom; the bar compares the reading with the configured core pause limit and remains informational.",
  "max core temperature": "Highest GPU core temperature seen on assigned cards during the benchmark. It matters because brief spikes can explain throttling or cooldown pauses; the bar compares the peak with the configured core pause limit and remains informational.",
  "average junction temperature": "Mean hotspot or junction temperature across assigned cards during the benchmark. It matters because junction heat often reaches limits before the core sensor; the bar compares the reading with the configured junction pause limit and remains informational.",
  "max junction temperature": "Highest hotspot or junction temperature seen on assigned cards during the benchmark. It matters because peak hotspot pressure is the strongest signal for thermal risk; the bar compares the peak with the configured junction pause limit and remains informational.",
  "average vram temperature": "Mean VRAM temperature across assigned cards during the benchmark. It matters because memory heat can limit long-context stability; the bar compares the reading with the configured VRAM pause limit and remains informational.",
  "max vram temperature": "Highest VRAM temperature seen on assigned cards during the benchmark. It matters because memory temperature spikes can explain cooldown waits or instability; the bar compares the peak with the configured VRAM pause limit and remains informational.",
};
var benchmarkAllModalMode = "quick";
var benchmarkForceStopPressTimer = null;
var benchmarkForceStopArmed = false;
var benchmarkForceStopConsumed = false;
var benchmarkModalLogMode = "staged";
var benchmarkRunningPresetTab = "";
var benchmarkRunningScriptTabs = {};
var benchmarkRunningScriptTabSteps = {};
var benchmarkSectionOpenState = {};
var benchmarkQueueOpenState = {};
var benchmarkQueueScrollTop = 0;
var benchmarkQueueSelectionByMode = { quick: null, full: null };
var benchmarkQueueOrderByMode = { quick: [], full: [] };
var benchmarkStageSelectionByMode = { quick: {}, full: {} };
var benchmarkStableActiveQueueOrderState = { key: "", order: [] };
var benchmarkModalLogHeight = 0;
var benchmarkModalLogScrollTopByMode = { staged: 0, full: 0 };
var benchmarkModalLogResizeObserver = null;
var benchmarkModalSnapshotRefreshInFlight = false;
var benchmarkModalSnapshotRefreshLastAt = 0;
var benchmarkModalControlsLocked = false;
var benchmarkModalControlLockInterval = null;
var benchmarkModalControlLockObserver = null;
var benchmarkModalAwaitingFreshSnapshot = false;
var benchmarkModalLastStructuralSignature = "";
var benchmarkModalLastFullRenderAt = 0;
var benchmarkFocusPendingSelector = "";
var benchmarkFocusPendingUntil = 0;
var benchmarkModalCollapsed = false;
var benchmarkMiniHidden = false;
var benchmarkModalOpenPersisted = false;
var benchmarkModalPosition = null;
var benchmarkMiniPosition = null;
var benchmarkDragState = null;
var benchmarkFloatingStateHydrated = false;
var modelScoreDetailState = { selector: "", loading: false, error: "", result: null, selectedMode: "", view: "score", activeLogTab: "" };
var modelScoreDetailsUiState = { selector: "", mode: "", scrollTop: 0, open: {} };
var modelScoreDetailComparisonSelector = "";
var modelScoreDetailRefreshSignature = "";
var modelScoreDetailRefreshInFlight = false;
var modelScoreLogScrollTopByKey = {};
var modelScoreActiveLogTabsByKey = {};
var scriptModalState = { loading: false, error: "", scripts: [], expandedOptions: "", argsById: {}, showInternal: false, view: "scripts", selectedJobId: "", logByJob: {}, logLoadedAtByJob: {}, logLoadingJob: "" };
var aiStudioGalleryState = { loading: false, loadedAt: 0, error: "", items: [], open: false };

function benchmarkSnapshot(status = lastStatus || {}) {
  const benchmarks = status?.benchmarks;
  return benchmarks && typeof benchmarks === "object" ? benchmarks : {};
}
function benchmarkJob(status = lastStatus || {}) {
  const job = benchmarkSnapshot(status).job;
  return job && typeof job === "object" ? job : {};
}
function benchmarkJobActive(status = lastStatus || {}) {
  return !!benchmarkJob(status).active;
}
function benchmarkSurfaceOpen() {
  const modal = $("benchmarkAllModal");
  const mini = $("benchmarkMiniWindow");
  return (!!modal && !modal.classList.contains("hidden")) || !!mini;
}
function benchmarkCountsHaveInventoryDetails(counts = {}) {
  return !!(
    counts
    && typeof counts === "object"
    && (
      Array.isArray(counts.stages)
      || Array.isArray(counts.eligible_presets)
      || Array.isArray(counts.already_scored_presets)
      || Array.isArray(counts.skipped_presets)
      || Array.isArray(counts.ineligible_presets)
    )
  );
}
function benchmarkSnapshotHasFullInventory(snapshot = benchmarkSnapshot()) {
  const countsByMode = snapshot?.counts_by_mode && typeof snapshot.counts_by_mode === "object" ? snapshot.counts_by_mode : null;
  if (countsByMode) {
    return ["quick", "full"].some((mode) => benchmarkCountsHaveInventoryDetails(countsByMode[mode] || {}));
  }
  return !!(
    snapshot
    && typeof snapshot === "object"
    && benchmarkCountsHaveInventoryDetails(snapshot.counts || {})
  );
}
function resetBenchmarkInventoryDefaultSelections(benchmarks = benchmarkSnapshot()) {
  const countsByMode = benchmarks?.counts_by_mode && typeof benchmarks.counts_by_mode === "object"
    ? benchmarks.counts_by_mode
    : {};
  ["quick", "full"].forEach((mode) => {
    const counts = countsByMode[mode] || (mode === benchmarkAllModalMode ? benchmarks?.counts : null) || {};
    if (!counts || typeof counts !== "object" || !benchmarkSnapshotHasFullInventory({ counts })) return;
    const eligible = benchmarkInventorySelectorsForGroup(counts, "eligible");
    const allSelectors = benchmarkInventoryRows(counts).map((row) => String(row?.selector || "")).filter(Boolean);
    benchmarkQueueSelectionByMode[mode] = [...eligible];
    benchmarkQueueOrderByMode[mode] = [
      ...eligible,
      ...allSelectors.filter((selector) => !eligible.includes(selector)),
    ];
  });
}
async function refreshBenchmarkSnapshot(options = {}) {
  const liveOnly = !!options.live;
  const query = new URLSearchParams({ _: String(Date.now()) });
  if (liveOnly) query.set("live", "1");
  else {
    query.set("include_inventory", "1");
    query.set("include_scores", options.includeScores ? "1" : "0");
  }
  if (liveOnly && benchmarkSurfaceOpen() && benchmarkJobActive()) query.set("logs", "1");
  const response = await fetchJsonWithTimeout(`/admin/benchmarks?${query.toString()}`, { cache: "no-store" }, liveOnly ? 4000 : 60000);
  if (!response.ok) throw new Error(`benchmarks fetch failed (${response.status})`);
  const payload = mergeStatusPayloadBenchmarkSnapshot(lastStatus, await response.json());
  const benchmarks = payload?.benchmarks;
  if (benchmarks && typeof benchmarks === "object") {
    const wasAwaitingFreshInventory = benchmarkModalAwaitingFreshSnapshot && !liveOnly;
    lastStatus = { ...(lastStatus || {}), benchmarks };
    if (wasAwaitingFreshInventory) resetBenchmarkInventoryDefaultSelections(benchmarks);
    if (!liveOnly || !benchmarkModalAwaitingFreshSnapshot || benchmarkJobActive({ benchmarks })) {
      benchmarkModalAwaitingFreshSnapshot = false;
    }
    syncBenchmarkModalControlLock(benchmarks.job || {}, benchmarks);
    return benchmarks;
  }
  return benchmarkSnapshot();
}
function scheduleBenchmarkModalSnapshotRefresh(force = false) {
  const modal = $("benchmarkAllModal");
  const mini = $("benchmarkMiniWindow");
  if ((!modal || modal.classList.contains("hidden")) && !mini) return;
  if (!force && benchmarkModalAwaitingFreshSnapshot && !benchmarkJobActive()) return;
  const now = Date.now();
  const refreshFloorMs = benchmarkJobActive() ? 1000 : 2000;
  if (!force && now - benchmarkModalSnapshotRefreshLastAt < refreshFloorMs) return;
  if (benchmarkModalSnapshotRefreshInFlight) return;
  benchmarkModalSnapshotRefreshInFlight = true;
  benchmarkModalSnapshotRefreshLastAt = now;
  const useLiveSnapshot = benchmarkJobActive() || (!force && !benchmarkModalAwaitingFreshSnapshot && benchmarkSnapshotHasFullInventory());
  refreshBenchmarkSnapshot({ live: useLiveSnapshot })
    .then(() => {
      benchmarkFocusPendingSelector = "";
      benchmarkFocusPendingUntil = 0;
      renderBenchmarkAllModal();
      renderBenchmarkMiniWindow();
    })
    .catch(() => {})
    .finally(() => {
      benchmarkModalSnapshotRefreshInFlight = false;
    });
}
function benchmarkComparisonLimit() {
  return Math.max(1, Number(benchmarkSnapshot().comparison_limit || 8) || 8);
}
function normalizeBenchmarkProgress(value) {
  const raw = Number(value || 0);
  if (!Number.isFinite(raw) || raw <= 0) return 0;
  return Math.max(0, Math.min(1, raw > 1 ? raw / 100 : raw));
}
function formatElapsedSeconds(value) {
  const seconds = Math.max(0, Math.floor(Number(value || 0)));
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  if (hours) return `${hours}h ${String(minutes).padStart(2, "0")}m ${String(secs).padStart(2, "0")}s`;
  if (minutes) return `${minutes}m ${String(secs).padStart(2, "0")}s`;
  return `${secs}s`;
}
function isoSeconds(value) {
  const ms = Date.parse(String(value || ""));
  return Number.isFinite(ms) ? ms / 1000 : 0;
}
function elapsedSecondsBetween(start, end = "") {
  const startSeconds = isoSeconds(start);
  if (!startSeconds) return 0;
  const endSeconds = isoSeconds(end) || Date.now() / 1000;
  return Math.max(0, endSeconds - startSeconds);
}
function benchmarkRowElapsedLabel(row = {}) {
  return formatElapsedSeconds(elapsedSecondsBetween(row?.started_at || row?.step_started_at, row?.finished_at));
}
function benchmarkJobElapsedLabel(job = {}) {
  return formatElapsedSeconds(elapsedSecondsBetween(job?.started_at, job?.finished_at));
}
function modelScoreResultDurationSeconds(result = {}) {
  const explicit = Number(result?.duration_seconds);
  if (Number.isFinite(explicit) && explicit > 0) return explicit;
  return elapsedSecondsBetween(result?.started_at, result?.finished_at);
}
function modelScoreTimingText(result = {}) {
  const elapsed = formatElapsedSeconds(modelScoreResultDurationSeconds(result));
  if (!elapsed) return "";
  const repaired = !!(result?.partial_rerun || result?.base_run_id || result?.repair);
  if (!repaired) return `${elapsed} elapsed`;
  const rerunSeconds = Number(result?.rerun_duration_seconds || 0);
  const rerun = Number.isFinite(rerunSeconds) && rerunSeconds > 0 ? formatElapsedSeconds(rerunSeconds) : "";
  return rerun ? `${elapsed} total · ${rerun} rerun` : `${elapsed} total · repaired`;
}
function benchmarkScores() {
  const scores = benchmarkSnapshot().scores;
  return scores && typeof scores === "object" ? scores : {};
}
function benchmarkScoreForSelector(selector) {
  const key = String(selector || "").trim();
  if (!key) return null;
  const scores = benchmarkScores();
  const direct = scores[key] || scores[encodeURIComponent(key)];
  const matched = direct || Object.values(scores).find((row) => {
    if (!row || typeof row !== "object") return false;
    return [row.selector, row.variant_id, row.upstream_tag].some((value) => String(value || "").trim() === key);
  }) || null;
  return benchmarkScoreWithTerminalQueueFallback(key, matched);
}
function benchmarkCompactScoreFromQueueRow(row = {}, mode = "") {
  const selector = String(row?.selector || "").trim();
  const score = Number(row?.score);
  if (!selector || !Number.isFinite(score)) return null;
  const status = String(row?.status || "").trim().toLowerCase();
  if (!["success", "completed", "failed"].includes(status)) return null;
  const resultMode = String(row?.mode || mode || benchmarkJob()?.mode || "").trim().toLowerCase();
  if (!["quick", "full"].includes(resultMode)) return null;
  return {
    selector,
    display_name: row.display_name || selector,
    mode: resultMode,
    status: status === "failed" ? "failed" : "complete",
    finished_at: row.finished_at || "",
    score,
    score_tier: row.score_tier || (resultMode === "quick" ? "quick" : ""),
    score_icon: row.score_icon || "",
    run_id: row.run_id || "",
  };
}
function benchmarkScoreWithTerminalQueueFallback(selector = "", score = null) {
  const key = String(selector || "").trim();
  if (!key) return score || null;
  const job = benchmarkJob();
  const queueResult = benchmarkCompactScoreFromQueueRow(
    benchmarkQueueRows(job).find((row) => String(row?.selector || "").trim() === key) || {},
    job.mode,
  );
  if (!queueResult) return score || null;
  if (!score || typeof score !== "object") {
    return {
      ...queueResult,
      [`${queueResult.mode}_result`]: queueResult,
      [`${queueResult.mode}_score`]: queueResult.score,
      [`${queueResult.mode}_status`]: queueResult.status,
      [`${queueResult.mode}_run_id`]: queueResult.run_id,
    };
  }
  if (modelScoreModeResult(score, queueResult.mode)) return score;
  return {
    ...score,
    [`${queueResult.mode}_result`]: queueResult,
    [`${queueResult.mode}_score`]: queueResult.score,
    [`${queueResult.mode}_status`]: queueResult.status,
    [`${queueResult.mode}_run_id`]: queueResult.run_id,
  };
}
function benchmarkRunningForSelector(selector) {
  const key = String(selector || "").trim();
  const running = benchmarkSnapshot().running || {};
  return key ? running[key] || null : null;
}
function benchmarkQueueRowForSelector(selector) {
  const key = String(selector || "").trim();
  if (!key) return null;
  return benchmarkQueueRows().find((row) => {
    if (!row || typeof row !== "object") return false;
    return [row.selector, row.variant_id, row.upstream_tag].some((value) => String(value || "").trim() === key);
  }) || null;
}
function benchmarkQueueRunningRows(snapshot = benchmarkSnapshot()) {
  const job = snapshot?.job && typeof snapshot.job === "object" ? snapshot.job : benchmarkJob();
  return benchmarkQueueRows(job).filter((row) => String(row?.status || "").trim().toLowerCase() === "running");
}
function benchmarkJobResumable(job = benchmarkJob()) {
  const active = !!job.active;
  const rows = benchmarkQueueRows(job);
  return !active && rows.some((row) => row?.status === "queued");
}
function benchmarkRowStageEvidenceRank(row = {}) {
  if (!row || typeof row !== "object") return 0;
  let rank = 0;
  const statuses = row.stage_statuses && typeof row.stage_statuses === "object" ? row.stage_statuses : {};
  const statusCount = Object.keys(statuses).length;
  if (statusCount) rank += 1000 + statusCount;
  if (Array.isArray(row.selected_step_ids)) rank += 100 + row.selected_step_ids.length;
  if (Array.isArray(row.step_history)) rank += 10 + row.step_history.length;
  return rank;
}
function benchmarkQueueRowHasStageEvidence(row = {}) {
  if (!row || typeof row !== "object" || benchmarkActiveQueueHiddenSkipReason(row)) return true;
  const statuses = row.stage_statuses && typeof row.stage_statuses === "object" ? row.stage_statuses : {};
  return Object.keys(statuses).length > 0;
}
function benchmarkJobHasQueueStageEvidence(job = benchmarkJob()) {
  const rows = benchmarkQueueRows(job).filter((row) => row && typeof row === "object" && !benchmarkActiveQueueHiddenSkipReason(row));
  return !rows.length || rows.every((row) => benchmarkQueueRowHasStageEvidence(row));
}
function benchmarkJobNeedsFreshStageEvidence(job = benchmarkJob()) {
  const rows = benchmarkQueueRows(job).filter((row) => row && typeof row === "object" && !benchmarkActiveQueueHiddenSkipReason(row));
  return rows.length > 0 && !benchmarkJobHasQueueStageEvidence(job);
}
function benchmarkFinishedReviewKey(job = benchmarkJob()) {
  const jobId = String(job?.job_id || "").trim();
  const finishedAt = String(job?.finished_at || "").trim();
  if (!jobId || !finishedAt) return "";
  return `${jobId}:${finishedAt}`;
}
function benchmarkFinishedReviewDismissedKey() {
  try {
    return String(localStorage.getItem(BENCHMARK_FINISHED_REVIEW_KEY) || "");
  } catch (error) {
    return "";
  }
}
function benchmarkQueueRowsAllTerminal(rows = []) {
  return (Array.isArray(rows) ? rows : []).every((row) => {
    const status = String(row?.status || "").trim().toLowerCase();
    return ["success", "completed", "failed", "skipped"].includes(status);
  });
}
function benchmarkJobFinishedReviewable(job = benchmarkJob()) {
  if (!job || job.active || benchmarkJobResumable(job)) return false;
  const rows = benchmarkQueueRows(job).filter((row) => row && typeof row === "object");
  if (!rows.length || !benchmarkQueueRowsAllTerminal(rows)) return false;
  const key = benchmarkFinishedReviewKey(job);
  if (!key || benchmarkFinishedReviewDismissedKey() === key) return false;
  const status = String(job.status || "").trim().toLowerCase();
  const summary = String(job.summary || "").trim().toLowerCase();
  return ["complete", "completed", "success"].includes(status) || (status === "idle" && /\b(completed|complete|finished)\b/.test(summary));
}
function benchmarkJobTerminal(job = {}) {
  if (job?.active) return false;
  const status = String(job?.status || "").trim().toLowerCase();
  return ["complete", "completed", "cancelled", "canceled", "failed", "idle", "interrupted", "stopped"].includes(status);
}
function benchmarkJobControlActive(job = benchmarkJob(), snapshot = benchmarkSnapshot()) {
  const status = String(job?.status || "").trim().toLowerCase();
  const summary = String(job?.summary || snapshot?.summary || "").trim().toLowerCase();
  const explicitActive = !!job?.active || status === "running";
  if (!explicitActive && benchmarkJobTerminal(job)) return false;
  const rows = benchmarkQueueRows(job);
  const hasRunningRow = rows.some((row) => String(row?.status || "").trim().toLowerCase() === "running");
  const runningMap = snapshot?.running && typeof snapshot.running === "object" ? snapshot.running : {};
  const currentLog = snapshot?.current_log && typeof snapshot.current_log === "object" ? snapshot.current_log : {};
  const currentLogText = String([currentLog.label, currentLog.status, currentLog.text].filter(Boolean).join(" ")).trim().toLowerCase();
  const activeText = `${summary} ${currentLogText}`.trim();
  const summaryActive = /model scores (running|waiting)|benchmark (running|queued)|running:|pausing to cool/.test(activeText);
  return explicitActive || hasRunningRow || Object.keys(runningMap).length > 0 || !!currentLog.active || summaryActive;
}
function syncBenchmarkModalControlLock(job = benchmarkJob(), snapshot = benchmarkSnapshot()) {
  if (benchmarkJobControlActive(job, snapshot)) {
    benchmarkModalControlsLocked = true;
    return true;
  }
  if (benchmarkJobTerminal(job)) {
    benchmarkModalControlsLocked = false;
    return false;
  }
  return benchmarkModalControlsLocked;
}
function benchmarkModalStructuralSignature(snapshot = benchmarkSnapshot(), job = benchmarkJob(), mode = "quick", counts = {}, orderedQueueRows = [], failedRows = []) {
  const compactRow = (row = {}) => ({
    selector: String(row.selector || ""),
    status: String(row.status || ""),
    mode: String(row.mode || ""),
    step_id: String(row.step_id || ""),
    step_label: String(row.step_label || ""),
    step_index: Number(row.step_index || 0),
    step_count: Number(row.step_count || 0),
    selected_step_ids: Array.isArray(row.selected_step_ids) ? row.selected_step_ids.map(String) : [],
    deferred_step_ids: Array.isArray(row.deferred_step_ids) ? row.deferred_step_ids.map(String) : [],
    stage_statuses: row.stage_statuses && typeof row.stage_statuses === "object" ? row.stage_statuses : {},
    skip_reason: String(row.skip_reason || ""),
    error: String(row.error || ""),
  });
  return JSON.stringify({
    mode: String(mode || ""),
    log_mode: String(benchmarkModalLogMode || ""),
    focused_selector: String(benchmarkRunningPresetTab || ""),
    focus_pending_selector: String(benchmarkFocusPendingSelector || ""),
    script_tabs: benchmarkRunningScriptTabs && typeof benchmarkRunningScriptTabs === "object" ? benchmarkRunningScriptTabs : {},
    script_tab_steps: benchmarkRunningScriptTabSteps && typeof benchmarkRunningScriptTabSteps === "object" ? benchmarkRunningScriptTabSteps : {},
    active: benchmarkJobControlActive(job, snapshot),
    resumable: benchmarkJobResumable(job),
    finished: benchmarkJobFinishedReviewable(job),
    awaiting: !!benchmarkModalAwaitingFreshSnapshot,
    job_id: String(job?.job_id || ""),
    status: String(job?.status || ""),
    summary: String(job?.summary || ""),
    thermal_cooldown: job?.thermal_cooldown !== false,
    queue_order: Array.isArray(job?.queue_order) ? job.queue_order.map(String) : [],
    running_indices: Array.isArray(job?.running_indices) ? job.running_indices.map(Number) : [],
    counts: {
      eligible: Number(counts?.eligible || 0),
      queued: Number(counts?.queued || 0),
      running: Number(counts?.running || 0),
      success: Number(counts?.success || 0),
      failed: Number(counts?.failed || 0),
      skipped: Number(counts?.skipped || 0),
      already_scored: Number(counts?.already_scored || 0),
      ineligible: Number(counts?.ineligible || 0),
      experimental: Number(counts?.experimental || 0),
      deprecated: Number(counts?.deprecated || 0),
    },
    rows: (orderedQueueRows || []).map(compactRow),
    failed: (failedRows || []).map(compactRow),
  });
}
function patchBenchmarkModalLiveText(body, { overall = 0, currentLine = "", logLabel = "", progressCountLine = "", logTail = "" } = {}) {
  if (!body) return;
  const percentNode = body.querySelector(".benchmark-overall-progress .score-progress-head span:last-child");
  if (percentNode) percentNode.textContent = percentNode.textContent ? `${overall}%` : "";
  const progressBar = body.querySelector(".benchmark-overall-progress .score-progress-track i");
  if (progressBar) progressBar.style.width = `${overall}%`;
  const currentNode = body.querySelector(".benchmark-progress-current");
  if (currentNode) currentNode.textContent = String(currentLine || "");
  const logNode = body.querySelector(".benchmark-progress-log");
  if (logNode) logNode.innerHTML = `<strong>Log:</strong> ${escapeHtml(logLabel || "Benchmark script output")}`;
  const countNode = body.querySelector(".benchmark-progress-count-inline");
  if (countNode) countNode.textContent = String(progressCountLine || "");
  const logTailNode = body.querySelector("#benchmarkModalLogTail");
  if (logTailNode && String(logTailNode.textContent || "") !== String(logTail || "")) {
    logTailNode.textContent = String(logTail || "");
  }
}
function mergeBenchmarkQueueRowStageEvidence(previousRow = null, incomingRow = null) {
  if (!incomingRow || typeof incomingRow !== "object") return incomingRow;
  if (!previousRow || typeof previousRow !== "object") return incomingRow;
  if (benchmarkRowStageEvidenceRank(incomingRow) >= benchmarkRowStageEvidenceRank(previousRow)) return incomingRow;
  const merged = { ...previousRow, ...incomingRow };
  if (!benchmarkQueueRowHasStageEvidence(incomingRow) && benchmarkQueueRowHasStageEvidence(previousRow)) {
    merged.stage_statuses = { ...(previousRow.stage_statuses || {}) };
  }
  if (!Array.isArray(incomingRow.selected_step_ids) && Array.isArray(previousRow.selected_step_ids)) {
    merged.selected_step_ids = [...previousRow.selected_step_ids];
  }
  if (!Array.isArray(incomingRow.step_history) && Array.isArray(previousRow.step_history)) {
    merged.step_history = previousRow.step_history.map((item) => ({ ...(item || {}) }));
  }
  return merged;
}
function mergeBenchmarkJobStageEvidence(previousJob = null, incomingJob = null) {
  if (!incomingJob || typeof incomingJob !== "object") return incomingJob;
  if (!previousJob || typeof previousJob !== "object") return incomingJob;
  const previousJobId = String(previousJob.job_id || "").trim();
  const incomingJobId = String(incomingJob.job_id || "").trim();
  if (previousJobId && incomingJobId && previousJobId !== incomingJobId) return incomingJob;
  const incomingRows = benchmarkQueueRows(incomingJob);
  if (!incomingRows.length) return incomingJob;
  const previousRows = new Map(benchmarkQueueRows(previousJob).map((row) => [String(row?.selector || ""), row]));
  return {
    ...incomingJob,
    queue: incomingRows.map((row) => {
      const selector = String(row?.selector || "");
      return selector ? mergeBenchmarkQueueRowStageEvidence(previousRows.get(selector), row) : row;
    }),
  };
}
function mergeStatusPayloadBenchmarkSnapshot(previousStatus = null, payload = {}) {
  const previousBenchmarks = benchmarkSnapshot(previousStatus || {});
  const incomingBenchmarks = payload?.benchmarks;
  if (!incomingBenchmarks || typeof incomingBenchmarks !== "object") return payload;
  const previousActive = benchmarkJobControlActive(previousBenchmarks.job || {}, previousBenchmarks);
  const incomingActive = benchmarkJobControlActive(incomingBenchmarks.job || {}, incomingBenchmarks);
  const incomingJob = incomingBenchmarks.job || {};
  const incomingTerminal = benchmarkJobTerminal(incomingJob);
  const incomingHasLiveDetails =
    Object.prototype.hasOwnProperty.call(incomingBenchmarks, "current_log")
    || Object.prototype.hasOwnProperty.call(incomingBenchmarks, "running_logs")
    || Object.prototype.hasOwnProperty.call(incomingBenchmarks, "log_tail");
  if (previousActive && !incomingActive && !incomingTerminal) {
    return { ...payload, benchmarks: previousBenchmarks };
  }
  const mergedBenchmarks = { ...previousBenchmarks, ...incomingBenchmarks };
  if (Object.prototype.hasOwnProperty.call(incomingBenchmarks, "job")) {
    mergedBenchmarks.job = mergeBenchmarkJobStageEvidence(previousBenchmarks.job || {}, incomingBenchmarks.job);
  }
  if (Object.prototype.hasOwnProperty.call(incomingBenchmarks, "running")) {
    mergedBenchmarks.running = incomingBenchmarks.running;
  }
  if (incomingActive && previousActive && !incomingHasLiveDetails) {
    ["current_log", "running_logs", "failed", "log_tail"].forEach((field) => {
      if (Object.prototype.hasOwnProperty.call(previousBenchmarks, field)) {
        mergedBenchmarks[field] = previousBenchmarks[field];
      } else {
        delete mergedBenchmarks[field];
      }
    });
  }
  if (incomingTerminal && !incomingActive) {
    mergedBenchmarks.running_logs = [];
    const incomingCurrentLog = incomingBenchmarks.current_log && typeof incomingBenchmarks.current_log === "object"
      ? incomingBenchmarks.current_log
      : null;
    if (!incomingCurrentLog || incomingCurrentLog.active) mergedBenchmarks.current_log = {};
  }
  return { ...payload, benchmarks: mergedBenchmarks };
}
function renderScoreGlyph(icon) {
  const glyph = String(icon || "").trim();
  if (!glyph) return "";
  const toneClass = glyph === "❌" ? " score-glyph-fail" : glyph === "✅" ? " score-glyph-pass" : "";
  return `<span class="score-glyph score-glyph-emoji${toneClass}" aria-hidden="true">${escapeHtml(glyph)}</span>`;
}
function renderScoreValueWithGlyph(icon, value) {
  const glyph = renderScoreGlyph(icon);
  return `${glyph}<span class="score-value">${escapeHtml(formatModelScoreValue(value))}</span>`;
}
function renderPresetScoreStack(labels = []) {
  const visible = labels.filter(Boolean);
  if (!visible.length) return "";
  if (visible.length === 1) return visible[0];
  return `<div class="preset-score-stack">${visible.join("")}</div>`;
}
const MISSING_MODEL_SCORES_MESSAGE = "No Model Scores are Available on this Preset Yet. Run Benchmarks through the Presets menu to calculate scores";
function missingModelScoresModalBody() {
  return "No Model Scores are Available on this Preset Yet.<br><br>Run Benchmarks through the Presets menu to calculate scores";
}
function showMissingModelScoresInfo(selector = "") {
  openPresetActionModal({
    title: "No Model Scores",
    body: missingModelScoresModalBody(),
    confirmLabel: "Run Benchmark",
    confirmClass: "green",
    onConfirm: async () => {
      openBenchmarkForPreset(selector);
    },
  });
}
function renderMissingPresetScoreLabel(selector = "") {
  return `<button type="button" class="preset-score-label score-missing" title="${escapeHtml(MISSING_MODEL_SCORES_MESSAGE)}" onclick="showMissingModelScoresInfo('${escapeJs(selector)}')">⛔ ??</button>`;
}
function renderQueuedPresetScoreLabel(selector, row = {}) {
  const key = String(selector || "").trim();
  const status = String(row.status || "queued").toLowerCase();
  const stepIndex = Number(row.step_index || 0) || 0;
  const stepCount = Number(row.step_count || 0) || 0;
  const stepText = stepCount ? ` • ${stepIndex}/${stepCount}` : "";
  const title = `${row.display_name || key}: ${row.step_label || row.error || status}`;
  if (status === "success" && row.score !== undefined && row.score !== null) {
    const tier = scoreTierClass(row.score_tier || "quick");
    const mode = String(row.mode || benchmarkJob()?.mode || "").toLowerCase();
    return `<button type="button" class="preset-score-label ${tier}" title="${escapeHtml(title)}" onclick="openPresetScoresModal('${escapeJs(key)}','${escapeJs(mode)}')">${renderScoreValueWithGlyph("✅", row.score)}</button>`;
  }
  if (status === "failed" && row.score !== undefined && row.score !== null) {
    const mode = String(row.mode || benchmarkJob()?.mode || "").toLowerCase();
    return `<button type="button" class="preset-score-label score-tier-crimson" title="${escapeHtml(title)}" onclick="openPresetScoresModal('${escapeJs(key)}','${escapeJs(mode)}')">${renderScoreValueWithGlyph("❌", row.score)}</button>`;
  }
  if (status === "running") {
    const pct = Math.round(normalizeBenchmarkProgress(row.step_progress) * 100);
    return `<button type="button" class="preset-score-label score-running" title="${escapeHtml(title)}" onclick="openBenchmarkAllModal()">⌛ ${pct}%${stepText}</button>`;
  }
  if (status === "queued") {
    return `<button type="button" class="preset-score-label score-running" title="${escapeHtml(title)}" onclick="openBenchmarkAllModal()">⌛ queued${stepText}</button>`;
  }
  if (status === "skipped") {
    return `<button type="button" class="preset-score-label score-missing" title="${escapeHtml(title)}" disabled>⛔ n/a</button>`;
  }
  return "";
}
function renderPresetQueueTitleTag(selector) {
  const key = String(selector || "").trim();
  if (!key) return "";
  const queued = benchmarkQueueRowForSelector(key);
  const status = String(queued?.status || "").toLowerCase();
  if (!["queued", "pending", "starting"].includes(status)) return "";
  const stepIndex = Number(queued?.step_index || 0) || 0;
  const stepCount = Number(queued?.step_count || 0) || 0;
  const stepText = stepCount ? ` · ${stepIndex}/${stepCount}` : "";
  const label = status === "queued" ? "queued" : status;
  const title = `${queued?.display_name || key}: ${queued?.step_label || queued?.error || status}`;
  return `<button type="button" class="preset-queue-title-tag" title="${escapeHtml(title)}" onclick="openBenchmarkAllModal()">⌛ ${escapeHtml(label)}${escapeHtml(stepText)}</button>`;
}
function benchmarkRunningLogForSelector(selector) {
  const key = String(selector || "").trim();
  if (!key) return null;
  const rows = Array.isArray(benchmarkSnapshot().running_logs) ? benchmarkSnapshot().running_logs : [];
  return rows.find((row) => String(row?.selector || "") === key) || null;
}
function scoreTierClass(tier) {
  const key = String(tier || "none").trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "");
  return key ? `score-tier-${key}` : "score-tier-none";
}
function formatModelScoreValue(value) {
  const score = Number(value);
  return Number.isFinite(score) ? score.toFixed(2) : "??";
}
function formatBenchmarkReturnCode(value) {
  const code = Number(value);
  if (!Number.isFinite(code)) return String(value ?? "").trim() || "unknown";
  if (code === 0) return "Passed";
  if (code === 86) return "stopped by the thermal safety limit";
  if (code === 87) return "waited for the speed-test slot or GPU cooldown";
  if (code === 130) return "Stopped";
  if (code === 124) return "Timed out";
  if (code === 137) return "Killed";
  if (code === 143) return "Terminated";
  if (code === 999) return "Internal benchmark error";
  return `Failed (exit ${code})`;
}
function modelScoreCompactAvailable(result = {}) {
  const status = String(result?.status || "").toLowerCase();
  return !!(result && (status === "complete" || status === "failed") && result.score !== undefined && result.score !== null);
}
function modelScoreResultSeconds(result = {}) {
  const finished = Date.parse(String(result?.finished_at || ""));
  if (Number.isFinite(finished)) return finished;
  const started = Date.parse(String(result?.started_at || ""));
  return Number.isFinite(started) ? started : 0;
}
function modelScoreSameResult(a = {}, b = {}) {
  const aMode = String(a?.mode || "").toLowerCase();
  const bMode = String(b?.mode || "").toLowerCase();
  const aRun = String(a?.run_id || "");
  const bRun = String(b?.run_id || "");
  if (aRun && bRun) return aRun === bRun;
  if (aMode && bMode && aMode !== bMode) return false;
  return aMode === bMode && String(a?.finished_at || "") === String(b?.finished_at || "") && Number(a?.score) === Number(b?.score);
}
function modelScoreLatestResult(result = {}) {
  const candidates = [modelScoreModeResult(result, "quick"), modelScoreModeResult(result, "full"), result]
    .filter((row) => modelScoreCompactAvailable(row));
  candidates.sort((a, b) => {
    const delta = modelScoreResultSeconds(b) - modelScoreResultSeconds(a);
    if (delta) return delta;
    return String(b?.mode || "").toLowerCase() === "full" ? 1 : -1;
  });
  return candidates[0] || null;
}
function modelScoreCardResults(result = {}) {
  const rows = [];
  const full = modelScoreModeResult(result, "full");
  const quick = modelScoreModeResult(result, "quick");
  [full, quick].forEach((row) => {
    if (!modelScoreCompactAvailable(row)) return;
    if (rows.some((existing) => modelScoreSameResult(existing, row))) return;
    rows.push(row);
  });
  if (!rows.length) {
    const latest = modelScoreLatestResult(result);
    if (latest) rows.push(latest);
  }
  return rows;
}
function renderPresetScoreLabel(selector, variant = {}) {
  const key = String(selector || "").trim();
  if (!key) return "";
  const score = benchmarkScoreForSelector(key);
  const queued = benchmarkQueueRowForSelector(key);
  const queuedStatus = String(queued?.status || "").toLowerCase();
  const queuedActiveStatus = ["running"].includes(queuedStatus);
  const queuedHtml = queued && queuedActiveStatus && (benchmarkJobActive() || benchmarkJobResumable() || queuedActiveStatus)
    ? renderQueuedPresetScoreLabel(key, queued)
    : "";
  if (!score) {
    if (queuedHtml) return queuedHtml;
    return renderMissingPresetScoreLabel(key);
  }
  const displays = modelScoreCardResults(score);
  if (!displays.length) {
    if (queuedHtml) return queuedHtml;
    return renderMissingPresetScoreLabel(key);
  }
  const scoreLabels = displays
    .map((display) => {
      const tier = scoreTierClass(display.score_tier || display.tier);
      const failed = modelScoreFailed(display);
      const tierIcon = modelScoreTierIcon(display.score_tier || display.tier);
      const sourceIcon = String(display.score_icon || "").trim();
      const icon = failed ? "❌" : (tierIcon || (!["✅", "❌"].includes(sourceIcon) ? sourceIcon : "") || (String(display.mode || "").toLowerCase() === "quick" ? "✅" : ""));
      const mode = String(display.mode || "").trim().toUpperCase();
      const modeClass = mode ? `score-mode-${mode.toLowerCase()}` : "";
      const title = `${mode || "Model"} score for ${display.display_name || score.display_name || variantDisplayLabel(variant || { upstream_tag: key })}`;
      return `<button type="button" class="preset-score-label ${modeClass} ${tier}" title="${escapeHtml(title)}" onclick="openPresetScoresModal('${escapeJs(key)}','${escapeJs(String(display.mode || "").toLowerCase())}')">${renderScoreValueWithGlyph(icon, display.score)}</button>`;
    });
  return renderPresetScoreStack([...scoreLabels, queuedHtml]);
}
function loadModelScoreComparisons() {
  try {
    const rows = JSON.parse(localStorage.getItem(MODEL_SCORE_COMPARISON_KEY) || "[]");
    return Array.isArray(rows) ? rows.filter((row) => row && row.selector && (row.metrics || row.quick_result?.metrics || row.full_result?.metrics)) : [];
  } catch (error) {
    return [];
  }
}
function saveModelScoreComparisons(rows) {
  const next = [];
  const seen = new Set();
  (Array.isArray(rows) ? rows : []).forEach((row) => {
    const selector = String(row?.selector || "").trim();
    if (!selector || seen.has(selector) || !(row?.metrics || row?.quick_result?.metrics || row?.full_result?.metrics)) return;
    seen.add(selector);
    next.push(row);
  });
  try {
    localStorage.setItem(MODEL_SCORE_COMPARISON_KEY, JSON.stringify(next.slice(0, benchmarkComparisonLimit())));
  } catch (error) {}
  return next;
}
function comparisonHasSelector(selector) {
  const key = String(selector || "").trim();
  return loadModelScoreComparisons().some((row) => String(row?.selector || "") === key);
}
function modelScoreComplianceDisplayLabel(result = {}) {
  const selector = String(result?.selector || modelScoreDetailState.selector || "").trim();
  const matchingVariant = selector ? findVariantBySelector(selector) || {} : {};
  const rawResult = modelScoreDetailState.result && typeof modelScoreDetailState.result === "object" ? modelScoreDetailState.result : {};
  const orientation = variantSafetyProfile({ ...matchingVariant, ...rawResult, ...(result || {}) });
  return orientation === "uncensored" ? "Compliance" : "Safety";
}
function modelScoreMetricDisplayLabel(id, metric = {}, result = {}) {
  if (String(id || "").trim().toLowerCase() === "compliance") return modelScoreComplianceDisplayLabel(result);
  return String(metric.label || MODEL_SCORE_METRIC_LABELS[id] || id).replaceAll("_", " ");
}
function modelScoreUsesSafetyLabel(result = {}) {
  return modelScoreComplianceDisplayLabel(result) === "Safety";
}
function modelScorePolicyDisplayText(text = "", result = {}) {
  const raw = String(text || "");
  if (!modelScoreUsesSafetyLabel(result)) return raw;
  return raw.replace(/\bCompliance\b/g, "Safety").replace(/\bcompliance\b/g, "safety");
}
function modelScoreMetricRows(result = {}) {
  const metrics = result?.metrics && typeof result.metrics === "object" ? result.metrics : {};
  const ids = [...MODEL_SCORE_METRIC_ORDER];
  Object.keys(metrics).forEach((id) => {
    if (!ids.includes(id)) ids.push(id);
  });
  return ids.map((id) => {
    const metric = metrics[id] && typeof metrics[id] === "object" ? metrics[id] : {};
    const score = Number(metric.score || 0);
    return {
      id,
      label: modelScoreMetricDisplayLabel(id, metric, result),
      score: Number.isFinite(score) ? Math.max(0, Math.min(10, score)) : 0,
      weight: Number(metric.weight || 0) || 0,
      summary: String(metric.summary || ""),
      duration_seconds: Number(metric.duration_seconds || 0) || 0,
      missing: !!metric.missing,
      pass_count: metric.pass_count,
      total_count: metric.total_count,
      subcategories: Array.isArray(metric.subcategories) ? metric.subcategories : [],
    };
  });
}
function modelScoreComplete(result = {}) {
  const status = String(result?.status || "");
  return !!(result && (status === "complete" || status === "failed") && result.metrics);
}
function modelScoreDisplayName(result = {}) {
  return String(result.display_name || result.selector || "Preset");
}
function modelScoreTierIcon(tier) {
  const key = String(tier || "").toLowerCase();
  if (key === "bronze") return "🥉";
  if (key === "silver") return "🥈";
  if (key === "gold") return "🥇";
  if (key === "diamond") return "🏆";
  return "";
}
function modelScoreCapIds(result = {}) {
  const caps = Array.isArray(result?.caps_applied)
    ? result.caps_applied
    : Array.isArray(result?.composite?.caps_applied)
      ? result.composite.caps_applied
      : [];
  return caps.map((cap) => String(cap?.id || "").trim().toLowerCase()).filter(Boolean);
}
function modelScoreModeResult(result = {}, mode = "full") {
  const key = String(mode || "").toLowerCase() === "quick" ? "quick_result" : "full_result";
  const row = result?.[key];
  if (row && typeof row === "object" && (row.status || row.score !== undefined || row.metrics)) return row;
  const currentMode = String(result?.mode || "").toLowerCase();
  if (currentMode === String(mode || "").toLowerCase()) return result;
  return null;
}
function modelScoreSelectedMode(result = {}) {
  const requested = String(modelScoreDetailState.selectedMode || "").toLowerCase();
  if (requested && modelScoreModeResult(result, requested)) return requested;
  const latest = modelScoreLatestResult(result);
  const latestMode = String(latest?.mode || "").toLowerCase();
  if (latestMode && modelScoreModeResult(result, latestMode)) return latestMode;
  return String(result?.mode || "").toLowerCase();
}
function modelScoreSelectedResult(result = {}) {
  const mode = modelScoreSelectedMode(result);
  return (mode ? modelScoreModeResult(result, mode) : null) || result;
}
function modelScoreFailed(result = {}) {
  const capIds = new Set(modelScoreCapIds(result));
  if (["launch-failed", "verify-failed", "preset-incompatible"].some((id) => capIds.has(id))) return true;
  const failure = result?.failure && typeof result.failure === "object" ? result.failure : {};
  const failureStep = String(failure.step_id || "").trim().toLowerCase();
  if (["launch", "verify", "verify-full"].includes(failureStep)) return true;
  const status = String(result?.status || "").toLowerCase();
  const score = Number(result?.score);
  if (status === "failed" && (!Number.isFinite(score) || score <= 3.5)) return true;
  return !!result?.failed;
}
function modelScorePassFailResult(result = {}) {
  return modelScoreLatestResult(result) || result;
}
function renderModelScoreTopScores(result = {}, activeMode = "") {
  const quick = modelScoreModeResult(result, "quick");
  const full = modelScoreModeResult(result, "full");
  const chips = [];
  const active = String(activeMode || modelScoreSelectedMode(result) || "").toLowerCase();
  const renderChip = (modeLabel, modeKey, score, icon, tierClass, timing) => {
    const activeClass = active === modeKey ? " active" : "";
    const tier = tierClass ? ` ${tierClass}` : "";
    return `<span class="score-score-chip-wrap"><button type="button" class="score-score-chip${tier}${activeClass}" title="Show ${modeLabel} benchmark details" onclick="setPresetScoreMode('${escapeJs(modeKey)}')"><span class="score-score-chip-main"><strong class="score-mode-label">${escapeHtml(modeLabel)}</strong> · <b>${renderScoreValueWithGlyph(icon, score)}</b></span></button>${timing ? `<small class="score-score-chip-time">${escapeHtml(timing)}</small>` : ""}</span>`;
  };
  const fullTier = full?.score_tier || "";
  if (full && full.score !== undefined) {
    const fullSourceIcon = String(full?.score_icon || "").trim();
    const fullTierIcon = modelScoreTierIcon(fullTier) || (!["✅", "❌"].includes(fullSourceIcon) ? fullSourceIcon : "");
    const fullIcon = fullTierIcon || (modelScoreFailed(full) ? "❌" : "✅");
    const timing = modelScoreTimingText(full);
    chips.push(renderChip("FULL", "full", full.score, fullIcon, scoreTierClass(fullTier), timing));
  }
  if (quick && quick.score !== undefined) {
    const quickIcon = modelScoreFailed(quick) ? "❌" : "✅";
    const timing = modelScoreTimingText(quick);
    chips.push(renderChip("QUICK", "quick", quick.score, quickIcon, "", timing));
  }
  return `<div class="score-modal-score-strip" aria-label="Preset score summary">${chips.join("")}</div>`;
}
function renderModelScorePassFailBadge(result = {}) {
  const quick = modelScoreModeResult(result, "quick");
  const full = modelScoreModeResult(result, "full");
  if (modelScoreCompactAvailable(quick) && !modelScoreFailed(quick) && modelScoreCompactAvailable(full) && modelScoreFailed(full)) {
    return `<button class="score-passfail-badge warn" onclick="showPresetScoreLogs(true)">${renderScoreGlyph("⚠️")}<span>WARN</span></button>`;
  }
  const passFailSource = modelScorePassFailResult(result);
  const failed = modelScoreFailed(passFailSource);
  if (modelScoreComplete(passFailSource) || modelScoreCompactAvailable(passFailSource)) {
    return `<button class="score-passfail-badge ${failed ? "fail" : "pass"}" onclick="showPresetScoreLogs(true)">${renderScoreGlyph(failed ? "❌" : "✅")}<span>${escapeHtml(failed ? "FAIL" : "PASS")}</span></button>`;
  }
  return "";
}
function modelScoreRadarEntries(currentResult = null) {
  const comparisons = loadModelScoreComparisons();
  const entries = [];
  const currentMode = String(currentResult?.mode || modelScoreSelectedMode(modelScoreDetailState.result || {}) || "").toLowerCase();
  if (modelScoreComplete(currentResult)) entries.push(currentResult);
  comparisons.forEach((row) => {
    if (String(row.selector || "") === String(currentResult?.selector || "")) return;
    const comparable = (currentMode ? modelScoreModeResult(row, currentMode) : null) || row;
    if (modelScoreComplete(comparable)) entries.push(comparable);
  });
  return entries.slice(0, benchmarkComparisonLimit() + 1);
}
function modelScoreEntryColor(index = 0) {
  return MODEL_SCORE_COMPARISON_COLORS[Math.max(0, Number(index || 0)) % MODEL_SCORE_COMPARISON_COLORS.length];
}
function setModelScoreDetailComparison(selector) {
  const key = String(selector || "").trim();
  const current = modelScoreSelectedResult(modelScoreDetailState.result || {});
  const owner = String(current?.selector || modelScoreDetailState.selector || "").trim();
  modelScoreDetailComparisonSelector = key && key !== owner ? key : "";
  renderPresetScoresModal();
}
function modelScoreDetailComparison(currentResult = {}) {
  const entries = modelScoreRadarEntries(currentResult);
  const owner = entries[0] || currentResult || {};
  if (!modelScoreComplete(owner) || entries.length < 2) return null;
  const requested = String(modelScoreDetailComparisonSelector || "").trim();
  let compareIndex = entries.findIndex((entry, index) => index > 0 && String(entry?.selector || "") === requested);
  if (compareIndex < 1) compareIndex = 1;
  const compare = entries[compareIndex];
  if (!modelScoreComplete(compare)) return null;
  return {
    owner,
    compare,
    compareIndex,
    ownerColor: modelScoreEntryColor(0),
    compareColor: modelScoreEntryColor(compareIndex),
  };
}
function modelScoreMetricById(result = {}, id = "") {
  const key = String(id || "");
  return modelScoreMetricRows(result).find((metric) => String(metric.id || "") === key) || null;
}
function renderScoreComparisonValuesHtml(ownerText = "", compareText = "", comparison = {}) {
  const ownerColor = comparison.ownerColor || modelScoreEntryColor(0);
  const compareColor = comparison.compareColor || modelScoreEntryColor(1);
  const ownerValue = String(ownerText || "n/a").trim() || "n/a";
  const compareValue = String(compareText || "n/a").trim() || "n/a";
  if (normalizeScoreComparisonText(ownerValue) === normalizeScoreComparisonText(compareValue)) {
    return `<span class="score-compare-values score-compare-values-single"><span class="score-compare-single">${escapeHtml(ownerValue)}</span></span>`;
  }
  const passOwner = scoreComparisonPassParts(ownerValue);
  const passCompare = scoreComparisonPassParts(compareValue);
  const displayOwner = passOwner && passCompare ? scoreComparisonPassDisplay(passOwner, true) : ownerValue;
  const displayCompare = passOwner && passCompare ? scoreComparisonPassDisplay(passCompare, false) : compareValue;
  return `<span class="score-compare-values"><span class="score-compare-value" style="--score-compare-color:${escapeHtml(ownerColor)}">${escapeHtml(displayOwner)}</span><span class="score-compare-vs">vs.</span><span class="score-compare-value" style="--score-compare-color:${escapeHtml(compareColor)}">${escapeHtml(displayCompare)}</span></span>`;
}
function normalizeScoreComparisonText(value = "") {
  return String(value || "")
    .trim()
    .replace(/\s+/g, " ")
    .replace(/\s*[·\-]\s*/g, " · ")
    .toLowerCase();
}
function scoreComparisonPercentText(value = "") {
  const text = String(value || "").trim();
  const match = text.match(/([0-9]+(?:\.[0-9]+)?)\s*%/);
  if (!match) return "";
  const number = Number(match[1]);
  if (!Number.isFinite(number)) return "";
  return `${Number.isInteger(number) ? number.toFixed(0) : String(Number(number.toFixed(1)))}%`;
}
function scoreComparisonPassParts(value = "") {
  const text = String(value || "").trim();
  const passMatch =
    text.match(/\bPASS\s+([0-9]+)\s*\/\s*([0-9]+)\b/i) ||
    text.match(/\b([0-9]+)\s*\/\s*([0-9]+)\s+PASS\b/i);
  if (!passMatch) return null;
  return {
    count: `${Number(passMatch[1])}/${Number(passMatch[2])}`,
    percent: scoreComparisonPercentText(text),
  };
}
function scoreComparisonPassDisplay(parts = {}, includePass = true) {
  const body = `${includePass ? "PASS " : ""}${parts.count || "n/a"}`;
  return parts.percent ? `${body} (${parts.percent})` : body;
}
function modelScoreRowLookupKey(value = "") {
  return String(value || "").trim().toLowerCase().replaceAll("_", " ").replaceAll("-", " ").replace(/\s+/g, " ");
}
function modelScoreFindComparableRow(rows = [], ownerRow = {}, fallbackIndex = 0) {
  const idKey = modelScoreRowLookupKey(ownerRow?.id);
  const labelKey = modelScoreRowLookupKey(ownerRow?.label);
  const candidates = Array.isArray(rows) ? rows : [];
  return candidates.find((row) => idKey && modelScoreRowLookupKey(row?.id) === idKey)
    || candidates.find((row) => labelKey && modelScoreRowLookupKey(row?.label) === labelKey)
    || candidates[Math.max(0, Number(fallbackIndex || 0))]
    || null;
}
function modelScoreComparableSubcategory(comparisonMetric = {}, path = "", ownerRow = {}, fallbackIndex = 0) {
  const parts = String(path || "").split(":").filter(Boolean);
  let rows = Array.isArray(comparisonMetric?.subcategories) ? comparisonMetric.subcategories : [];
  let match = null;
  parts.forEach((part) => {
    if (!rows.length) return;
    const key = modelScoreRowLookupKey(part);
    match = rows.find((row) => modelScoreRowLookupKey(row?.id) === key || modelScoreRowLookupKey(row?.label) === key)
      || rows[Number(part)]
      || null;
    rows = Array.isArray(match?.subcategories) ? match.subcategories : [];
  });
  return match || modelScoreFindComparableRow(rows, ownerRow, fallbackIndex);
}
function radarPoint(cx, cy, radius, index, total, value) {
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(1, total);
  const scaled = Math.max(0, Math.min(1, Number(value || 0) / 10));
  return {
    x: cx + Math.cos(angle) * radius * scaled,
    y: cy + Math.sin(angle) * radius * scaled,
    labelX: cx + Math.cos(angle) * (radius + 26),
    labelY: cy + Math.sin(angle) * (radius + 26),
  };
}
function renderModelScoreRadarPanel(entries = [], rows = [], title = "Scores") {
  const total = Math.max(3, rows.length);
  const cx = 260;
  const cy = 220;
  const radius = 174;
  const rings = [2, 4, 6, 8, 10]
    .map((value) => {
      const points = rows
        .map((_, index) => radarPoint(cx, cy, radius, index, total, value))
        .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
        .join(" ");
      return `<polygon class="score-radar-ring" points="${points}"></polygon>`;
    })
    .join("");
  const axes = rows
    .map((row, index) => {
      const outer = radarPoint(cx, cy, radius, index, total, 10);
      const label = radarPoint(cx, cy, radius, index, total, 10);
      return `<line class="score-radar-axis" x1="${cx}" y1="${cy}" x2="${outer.x.toFixed(1)}" y2="${outer.y.toFixed(1)}"></line><text class="score-radar-label" x="${label.labelX.toFixed(1)}" y="${label.labelY.toFixed(1)}">${escapeHtml(row.label)}</text>`;
    })
    .join("");
  const polygons = entries
    .map((entry, entryIndex) => {
      const metrics = modelScoreMetricRows(entry);
      const metricMap = new Map(metrics.map((metric) => [metric.id, metric]));
      const color = MODEL_SCORE_COMPARISON_COLORS[entryIndex % MODEL_SCORE_COMPARISON_COLORS.length];
      const points = rows
        .map((row, index) => radarPoint(cx, cy, radius, index, total, metricMap.get(row.id)?.score || 0))
        .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
        .join(" ");
      const dots = rows
        .map((row, index) => {
          const point = radarPoint(cx, cy, radius, index, total, metricMap.get(row.id)?.score || 0);
          return `<circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="3.5" fill="${color}"></circle>`;
        })
        .join("");
      return `<g class="score-radar-series"><polygon points="${points}" fill="${color}" stroke="${color}"></polygon>${dots}</g>`;
    })
    .join("");
  return `<section class="score-radar-panel" aria-label="${escapeHtml(title)} score radar"><h3>${escapeHtml(title)}</h3><div class="score-radar-stage"><svg class="score-radar" viewBox="0 0 520 440" role="img" aria-label="${escapeHtml(title)} score radar">${rings}${axes}${polygons}</svg></div></section>`;
}
function renderModelScoreRadar(currentResult = null) {
  const entries = modelScoreRadarEntries(currentResult);
  const baseline = entries[0] || currentResult || { metrics: {} };
  const rows = modelScoreMetricRows(baseline);
  const autoCompareSelector = entries.length > 1 ? String(entries[1]?.selector || "") : "";
  const activeCompareSelector = String(modelScoreDetailComparisonSelector || autoCompareSelector);
  const legend = entries.length
    ? `<div class="score-radar-legend">${entries
        .map((entry, index) => {
          const selector = String(entry?.selector || "");
          const active = index > 0 && selector === activeCompareSelector;
          const baselineClass = index === 0 ? " baseline" : "";
          return `<button type="button" class="score-radar-legend-item${baselineClass}${active ? " active" : ""}" title="${escapeHtml(index === 0 ? "Modal preset baseline" : "Compare this preset in Details")}" onclick="setModelScoreDetailComparison('${escapeJs(selector)}')"><i style="background:${modelScoreEntryColor(index)}"></i>${escapeHtml(modelScoreDisplayName(entry))}</button>`;
        })
        .join("")}</div>`
    : '<div class="empty-variant-note">No scored metrics yet.</div>';
  const rowMap = new Map(rows.map((row) => [row.id, row]));
  const panels = MODEL_SCORE_RADAR_GROUPS.map((group) => {
    const groupRows = group.metricIds.map((id) => rowMap.get(id)).filter(Boolean);
    return renderModelScoreRadarPanel(entries, groupRows, group.title);
  }).join("");
  return `<div class="score-radar-wrap">${legend}<div class="score-radar-grid">${panels}</div></div>`;
}
function modelScoreUsefulText(value) {
  const text = String(value || "").trim();
  const normalized = text.toLowerCase().replace(/\s+/g, " ");
  if (!text) return "";
  if (["not measured", "not measured.", "measured by benchmark harness", "measured by benchmark harness.", "measured by the benchmark harness", "measured by the benchmark harness."].includes(normalized)) {
    return "";
  }
  return text;
}
function modelScoreDescriptionKey(row = {}) {
  return String(row?.label || row?.id || row?.name || "").trim().toLowerCase().replaceAll("_", " ").replaceAll("-", " ").replace(/\s+/g, " ");
}
function modelScoreMetricDescription(metric = {}, result = {}) {
  const explicit = modelScoreUsefulText(metric.summary);
  const label = String(metric.label || "This category").trim();
  let base = MODEL_SCORE_METRIC_DESCRIPTIONS[metric.id] || `${label} is a benchmark-published score category. Its rows below show the source signal and normalized value used by the selected result.`;
  let explicitDisplay = explicit;
  if (metric.id === "compliance") {
    base = modelScoreUsesSafetyLabel(result)
      ? "Safety checks that verify the preset refuses or deflects unsafe requests while still following safe user constraints without drifting."
      : "Compliance checks that verify the uncensored preset follows requested behavior without drifting into unwanted refusals or evasive safety boilerplate.";
    explicitDisplay = modelScorePolicyDisplayText(explicit, result);
  }
  return explicitDisplay && explicitDisplay !== base ? `${base} Result note: ${explicitDisplay}` : base;
}
function modelScoreSubcategoryContributionText(row = {}, metric = {}) {
  const metricLabel = String(metric?.label || "this category");
  if (row?.score_visible === false || Number(row?.weight || 0) <= 0) {
    return "This row is informational and does not change the score.";
  }
  const weight = Number(row?.weight || 0);
  const weightText = weight > 0 ? ` with ${formatNumber(weight * 100, 0)}% row weight` : "";
  return `Its normalized value contributes to ${metricLabel}${weightText} before the category is folded into the final score.`;
}
function modelScoreSubcategoryDescription(row = {}, metric = {}, result = {}) {
  const explicit = modelScoreUsefulText(row?.summary || row?.detail || row?.method || row?.source);
  const key = modelScoreDescriptionKey(row);
  const label = modelScorePolicyDisplayText(String(row?.label || row?.id || "This subtest").replaceAll("_", " "), result);
  const metricLabel = String(metric?.label || "its category").toLowerCase();
  const base = modelScorePolicyDisplayText(MODEL_SCORE_SUBCATEGORY_DESCRIPTIONS[key] || `${label} measures benchmark evidence for ${metricLabel}. It matters because this signal helps explain whether the preset is usable for that part of the evaluation.`, result);
  const contribution = modelScoreSubcategoryContributionText(row, metric);
  const explicitDisplay = metric?.id === "compliance" ? modelScorePolicyDisplayText(explicit, result) : explicit;
  const explicitText = explicitDisplay && explicitDisplay !== base ? ` Signal detail: ${explicitDisplay}` : "";
  return `${base} ${contribution}${explicitText}`;
}
function modelScoreMissingSubcategoryDescription(metric = {}) {
  const metricLabel = String(metric?.label || "This category");
  return `${metricLabel} was scored as a top-level category for this run; no lower-level subtest rows were published with the result.`;
}
function modelScoreRowLooksByteSized(row = {}, unit = "") {
  const cleanUnit = String(unit || row?.unit || "").trim().toLowerCase();
  if (/^(b|byte|bytes)$/.test(cleanUnit)) return true;
  const key = modelScoreDescriptionKey(row);
  return /\b(byte|bytes)\b/.test(key) || /\b(model size|cache footprint|disk size|download size|cache size)\b/.test(key);
}
function modelScoreRawByteNumber(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const text = String(value ?? "").trim();
  if (!text) return null;
  const rawMatch = text.match(/^([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:b|byte|bytes)?$/i);
  if (!rawMatch) return null;
  const number = Number(rawMatch[1].replaceAll(",", ""));
  return Number.isFinite(number) ? number : null;
}
function modelScoreByteDisplayValue(row = {}, value = "", unit = "") {
  if (!modelScoreRowLooksByteSized(row, unit)) return "";
  const text = String(value ?? "").trim();
  if (/\b(kb|kib|mb|mib|gb|gib|tb|tib)\b/i.test(text)) return text;
  const number = modelScoreRawByteNumber(value);
  return number === null ? "" : formatDiskBytes(number);
}
function modelScorePassCountText(row = {}) {
  const passed = Number(row?.pass_count);
  const total = Number(row?.total_count);
  if (!Number.isFinite(passed) || !Number.isFinite(total) || total <= 0) return "";
  return `PASS ${Math.max(0, Math.round(passed))}/${Math.max(0, Math.round(total))}`;
}
function modelScoreNumericDisplayValue(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value ?? "").trim();
  return String(Number(value.toFixed(2)));
}
function modelScoreSubcategorySummaryValue(row = {}, subScore = 0) {
  const displayValue = String(row?.display_value ?? "").trim();
  const displayByteValue = modelScoreByteDisplayValue(row, displayValue, row?.unit);
  const passCount = modelScorePassCountText(row);
  if (displayByteValue) return `${displayByteValue}${passCount ? ` · ${passCount}` : ""}`;
  if (displayValue) return `${displayValue}${passCount && !displayValue.includes(passCount) ? ` · ${passCount}` : ""}`;
  const value = row?.value;
  const unit = String(row?.unit || "").trim();
  if (value !== null && value !== undefined && String(value).trim() !== "") {
    if (unit.toLowerCase() === "rc") {
      return `${formatBenchmarkReturnCode(value)}${passCount ? ` · ${passCount}` : ""}`;
    }
    const byteValue = modelScoreByteDisplayValue(row, value, unit);
    if (byteValue) return `${byteValue}${passCount ? ` · ${passCount}` : ""}`;
    const unitText = unit === "%" ? "%" : unit ? ` ${unit}` : "";
    return `${modelScoreNumericDisplayValue(value)}${unitText}${passCount ? ` · ${passCount}` : ""}`;
  }
  return `${formatModelScoreValue(subScore)}${passCount ? ` · ${passCount}` : ""}`;
}
function modelScoreTemperatureClass(row = {}) {
  const className = String(row?.value_class || row?.bar_class || "").trim();
  return /^temp-(blue|green|yellow|orange|red|crimson)$/.test(className) ? className : "";
}
function modelScoreSubcategorySummaryValueHtml(row = {}, subScore = 0) {
  const value = escapeHtml(modelScoreSubcategorySummaryValue(row, subScore));
  const className = modelScoreTemperatureClass(row);
  return `<span${className ? ` class="${escapeHtml(className)}"` : ""}>${value}</span>`;
}
function modelScoreStaleBadgeHtml(row = {}) {
  if (!row?.stale) return "";
  const reason = String(row?.stale_reason || "This row was scored by an older benchmark harness or validator.").trim();
  const metricId = String(row?.id || "").toLowerCase();
  const action = metricId.startsWith("compliance_") ? ' onclick="event.preventDefault();event.stopPropagation();revalidateComplianceScoreFromBadge()"' : "";
  return `<button type="button" class="score-stale-badge" title="${escapeHtml(reason)}"${action}>STALE</button>`;
}
function selectedComplianceStaleRow() {
  const result = modelScoreSelectedResult(modelScoreDetailState.result || {});
  const rows = Array.isArray(result?.metrics?.compliance?.subcategories) ? result.metrics.compliance.subcategories : [];
  return rows.find((row) => row?.stale) || null;
}
function selectedComplianceDisplayLabel() {
  return modelScoreComplianceDisplayLabel(modelScoreSelectedResult(modelScoreDetailState.result || {}));
}
async function revalidateComplianceScoreFromBadge() {
  const selector = String(modelScoreDetailState.selector || "").trim();
  const mode = String(modelScoreSelectedMode(modelScoreDetailState.result || "") || "").toLowerCase();
  const row = selectedComplianceStaleRow();
  if (!selector || !["quick", "full"].includes(mode) || !row) return;
  const label = selectedComplianceDisplayLabel();
  const current = row.current_versions || {};
  const artifact = row.artifact_versions || {};
  const blocks = [];
  [
    ["schema", "schema"],
    ["prompt_bank", "prompt bank"],
    ["harness", "harness"],
  ].forEach(([key, label]) => {
    const have = Number(artifact[key] || 0);
    const want = Number(current[key] || 0);
    if (want > 0 && have < want) blocks.push(`${label} v${have || "?"} < v${want}`);
  });
  if (blocks.length) {
    const rerun = await openClubConfirmModal(`This stale ${label} result cannot be safely revalidated from cached answers because ${blocks.join("; ")}. Queue a ${label}-only ${mode === "full" ? "Full" : "Quick"} rerun instead?`);
    if (!rerun) return;
    await rerunModelScoreCategory("compliance");
    return;
  }
  const confirmed = await openClubConfirmModal(`Revalidate ${label} for ${selector} from cached ${mode === "full" ? "Full" : "Quick"} responses using the current validator? This does not rerun prompts.`);
  if (!confirmed) return;
  try {
    const response = await post(
      "/admin/benchmarks/revalidate-compliance",
      { selector, mode },
      `/admin/benchmarks/revalidate-compliance ${mode} ${selector}`,
    );
    const payload = response || {};
    if (payload.result) {
      modelScoreDetailState.result = payload.result;
      modelScoreDetailState.selectedMode = mode;
      modelScoreDetailState.loading = false;
      modelScoreDetailState.error = "";
      renderPresetScoresModal();
    } else {
      await openPresetScoresModal(selector);
    }
  } catch (error) {
    setElementMsg("presetScoresMsg", messageText(error), "error");
  }
}
function modelScoreSubcategoryBarPct(row = {}, subScore = 0) {
  const explicitPct = Number(row?.bar_value_pct ?? row?.bar_pct);
  if (Number.isFinite(explicitPct)) return Math.max(0, Math.min(100, explicitPct));
  return Math.max(0, Math.min(100, Number.isFinite(subScore) ? subScore * 10 : 0));
}
function modelScoreBarPercent(score = 0) {
  const pct = Math.max(0, Math.min(100, Number.isFinite(Number(score)) ? Number(score) * 10 : 0));
  return Number(pct.toFixed(1));
}
function modelScorePercentLabel(pct = 0) {
  const value = Number(pct);
  if (!Number.isFinite(value)) return "0%";
  return `${Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1)}%`;
}
function renderModelScoreSubcategory(row = {}, metric = {}, subIndex = 0, path = "", result = {}, comparison = null) {
  const subScore = Number(row?.score || 0);
  const showScore = row?.score_visible !== false;
  const hasExplicitBar = row?.bar_value_pct !== undefined || row?.bar_pct !== undefined;
  const showBar = row?.bar_visible !== false && (showScore || hasExplicitBar);
  const contribution = row?.contribution === undefined ? "" : ` · contribution ${formatModelScoreValue(row.contribution)}`;
  const subKey = `subcategory:${metric.id}:${path || row?.id || row?.label || subIndex}`;
  const childRows = Array.isArray(row?.subcategories) ? row.subcategories : [];
  const comparisonRow = comparison?.metric
    ? modelScoreComparableSubcategory(comparison.metric, path, row, subIndex)
    : null;
  const childHtml = childRows
    .map((child, childIndex) =>
      renderModelScoreSubcategory(
        child,
        metric,
        childIndex,
        `${path || row?.id || row?.label || subIndex}:${child?.id || child?.label || childIndex}`,
        result,
        comparison,
      ),
    )
    .join("");
  const barPct = modelScoreSubcategoryBarPct(row, subScore);
  const barClass = modelScoreTemperatureClass(row);
  const label = modelScorePolicyDisplayText(row?.label || row?.id || "Subcategory", result);
  const rowId = String(row?.id || "").toLowerCase();
  const subcategoryActions = {
    quality_reasoning_lane: {
      title: "Rerun reasoning quality only",
      action: "rerunModelScoreStage('quality-full-reasoning')",
    },
    quality_sandbox_lane: {
      title: "Rerun sandbox quality packs only",
      action: "rerunModelScoreStage('quality-sandbox')",
    },
  };
  const subcategoryAction = !comparison && String(metric?.id || "") === "quality" ? subcategoryActions[rowId] : null;
  const actionHtml = subcategoryAction
    ? `<span class="score-subcategory-action">${renderIconButton({
        title: subcategoryAction.title,
        action: subcategoryAction.action,
        icon: "refresh",
        className: "score-category-refresh-btn",
      })}</span>`
    : "";
  const summaryValue = comparison
    ? renderScoreComparisonValuesHtml(
        modelScoreSubcategorySummaryValue(row, subScore),
        comparisonRow ? modelScoreSubcategorySummaryValue(comparisonRow, Number(comparisonRow.score || 0)) : "n/a",
        comparison,
      )
    : modelScoreSubcategorySummaryValueHtml(row, subScore);
  return `<details class="score-subcategory${childRows.length ? " score-subcategory-parent" : ""}" data-score-detail-key="${escapeHtml(subKey)}"><summary><span class="score-collapse-cue">▾</span><span>${escapeHtml(label)}${modelScoreStaleBadgeHtml(row)}</span>${summaryValue}${actionHtml}</summary>${showBar ? `<div class="score-mini-bar"><i${barClass ? ` class="${escapeHtml(barClass)}"` : ""} style="width:${modelScoreBarPercent(barPct / 10)}%"></i></div>` : ""}<div class="preset-help">${escapeHtml(modelScoreSubcategoryDescription(row, metric, result) + (showScore ? contribution : ""))}</div>${childHtml}</details>`;
}
function capturePresetScoreDetailsUiState() {
  const card = document.querySelector("#presetScoresBody .score-details-card");
  if (!card) return null;
  const open = {};
  card.querySelectorAll("details[data-score-detail-key]").forEach((node) => {
    const key = String(node.dataset.scoreDetailKey || "");
    if (key) open[key] = !!node.open;
  });
  const summary = $("presetScoreSummaryCard");
  const modal = $("presetScoresModal");
  const modalCard = document.querySelector("#presetScoresModal .model-score-modal-card");
  const scrollElement = document.scrollingElement || document.documentElement;
  return {
    selector: String(modelScoreDetailState.selector || ""),
    mode: String(modelScoreSelectedMode(modelScoreDetailState.result || "") || ""),
    scrollTop: Number(card.scrollTop || 0),
    modalScrollTop: Number(modal?.scrollTop || 0),
    modalCardScrollTop: Number(modalCard?.scrollTop || 0),
    pageScrollTop: Number(scrollElement?.scrollTop || 0),
    summaryScrollTop: Number(summary?.scrollTop || 0),
    open,
  };
}
function restorePresetScoreDetailsUiState(snapshot) {
  const card = document.querySelector("#presetScoresBody .score-details-card");
  if (!snapshot) return;
  if (String(snapshot.selector || "") !== String(modelScoreDetailState.selector || "")) return;
  if (String(snapshot.mode || "") !== String(modelScoreSelectedMode(modelScoreDetailState.result || "") || "")) return;
  const summary = $("presetScoreSummaryCard");
  if (summary) summary.scrollTop = Math.max(0, Number(snapshot.summaryScrollTop || 0));
  const modal = $("presetScoresModal");
  const modalCard = document.querySelector("#presetScoresModal .model-score-modal-card");
  const scrollElement = document.scrollingElement || document.documentElement;
  if (modal) modal.scrollTop = Math.max(0, Number(snapshot.modalScrollTop || 0));
  if (modalCard) modalCard.scrollTop = Math.max(0, Number(snapshot.modalCardScrollTop || 0));
  if (scrollElement && snapshot.pageScrollTop !== undefined) scrollElement.scrollTop = Math.max(0, Number(snapshot.pageScrollTop || 0));
  if (!card) return;
  const open = snapshot.open && typeof snapshot.open === "object" ? snapshot.open : {};
  card.querySelectorAll("details[data-score-detail-key]").forEach((node) => {
    const key = String(node.dataset.scoreDetailKey || "");
    if (Object.prototype.hasOwnProperty.call(open, key)) node.open = !!open[key];
  });
  card.scrollTop = Math.max(0, Number(snapshot.scrollTop || 0));
}
function presetScoreLogScrollKey(id = "") {
  const selector = String(modelScoreDetailState.selector || "");
  const mode = String(modelScoreSelectedMode(modelScoreDetailState.result || "") || "");
  const logId = String(id || modelScoreDetailState.activeLogTab || "");
  return `${selector}::${mode}::${logId}`;
}
function presetScoreLogTabKey(result = modelScoreDetailState.result || {}) {
  const selector = String(modelScoreDetailState.selector || result?.selector || "").trim();
  const mode = String(modelScoreSelectedMode(modelScoreDetailState.result || result || {}) || result?.mode || "").toLowerCase();
  return selector ? `${selector}::${mode}` : "";
}
function presetScoreActiveLogTab(result = modelScoreDetailState.result || {}) {
  const key = presetScoreLogTabKey(result);
  return String((key && modelScoreActiveLogTabsByKey[key]) || modelScoreDetailState.activeLogTab || "");
}
function setPresetScoreActiveLogTab(id, result = modelScoreDetailState.result || {}) {
  const value = String(id || "");
  const key = presetScoreLogTabKey(result);
  if (key) modelScoreActiveLogTabsByKey[key] = value;
  modelScoreDetailState.activeLogTab = value;
}
function rememberPresetScoreLogScroll() {
  const viewer = document.querySelector("#presetScoresBody .score-log-viewer");
  if (!viewer) return;
  const key = presetScoreLogScrollKey(viewer.dataset.scoreLogId || "");
  if (key) modelScoreLogScrollTopByKey[key] = Number(viewer.scrollTop || 0);
}
function restorePresetScoreLogScroll(id = "") {
  const viewer = document.querySelector("#presetScoresBody .score-log-viewer");
  if (!viewer) return;
  const key = presetScoreLogScrollKey(id || viewer.dataset.scoreLogId || "");
  const maxScroll = Math.max(0, Number(viewer.scrollHeight || 0) - Number(viewer.clientHeight || 0));
  viewer.scrollTop = Math.min(Math.max(0, Number(modelScoreLogScrollTopByKey[key] || 0)), maxScroll);
}
const MODEL_SCORE_QUALITY_SANDBOX_PACKS = [
  ["bugfind15", "Bug Finding", "BugFind pack pass-rate."],
  ["hermesagent20", "Agent Tasks", "HermesAgent pack pass-rate."],
  ["cli40", "CLI Tasks", "CLI pack pass-rate."],
];
function modelScoreQualityPackKey(row = {}) {
  return String(row?.id || row?.label || "")
    .toLowerCase()
    .replace(/^quality_pack_/, "")
    .replace(/[^a-z0-9]+/g, "");
}
function modelScoreQualitySandboxGroup(rows = []) {
  const sandboxKeys = new Set(MODEL_SCORE_QUALITY_SANDBOX_PACKS.map((row) => row[0]));
  const sandboxByKey = new Map();
  const keptRows = [];
  (Array.isArray(rows) ? rows : []).forEach((row) => {
    const key = modelScoreQualityPackKey(row);
    if (sandboxKeys.has(key)) {
      sandboxByKey.set(key, row);
    } else {
      keptRows.push(row);
    }
  });
  const sandboxRows = MODEL_SCORE_QUALITY_SANDBOX_PACKS.map(([key, label, method]) => {
    const existing = sandboxByKey.get(key);
    if (existing) return existing;
    return {
      id: `quality_pack_${key}`,
      label,
      score: 0,
      weight: 0,
      method: `${method} Run the sandbox quality stage to populate this row.`,
      evidence: ["quality-sandbox.log"],
      missing: true,
    };
  });
  let passed = 0;
  let total = 0;
  let skipped = false;
  sandboxRows.forEach((row) => {
    const rowTotal = Number(row?.total_count);
    const rowPassed = Number(row?.pass_count);
    if (String(row?.display_value || "").toLowerCase() === "skipped") skipped = true;
    if (Number.isFinite(rowTotal) && rowTotal > 0 && Number.isFinite(rowPassed) && !row?.missing) {
      passed += Math.max(0, Math.round(rowPassed));
      total += Math.max(0, Math.round(rowTotal));
    }
  });
  const pct = total > 0 ? Number(((passed / total) * 100).toFixed(1)) : undefined;
  const score = total > 0 ? Number(Math.max(0, Math.min(10, pct / 10)).toFixed(2)) : 0;
  const bonus = total > 0 ? Math.min(0.25, Math.max(0, score) * 0.025) : 0;
  const evidence = Array.from(new Set(
    sandboxRows.flatMap((row) => Array.isArray(row?.evidence) ? row.evidence : []).filter(Boolean),
  ));
  const parent = {
    id: "quality_sandbox_lane",
    label: "Sandbox Quality",
    score,
    weight: 0,
    value: pct,
    unit: "%",
    pass_count: total > 0 ? passed : undefined,
    total_count: total > 0 ? total : undefined,
    method: "Docker-backed Bug Finding, Agent Tasks, and CLI Tasks packs; this lane can add a small final-score bonus but never penalizes when unavailable.",
    evidence: evidence.length ? evidence : ["quality-sandbox.log"],
    missing: total <= 0,
    subcategories: [
      ...sandboxRows,
      {
        id: "quality_sandbox_bonus",
        label: "Sandbox Bonus",
        score: 0,
        weight: 0,
        display_value: `+${bonus.toFixed(2)} final score`,
        score_visible: false,
        bar_visible: false,
        method: "Sandbox quality can add up to +0.25 to the final Full score and never penalizes when absent or skipped.",
        evidence: evidence.length ? evidence : ["quality-sandbox.log"],
        missing: total <= 0,
      },
    ],
  };
  if (total <= 0) {
    parent.display_value = skipped ? "skipped" : "not run";
    parent.score_visible = false;
    parent.bar_visible = false;
  }
  return { rows: keptRows, parent };
}
function modelScoreFullQualityMetricWithLanes(metric = {}, result = {}) {
  if (String(metric?.id || "") !== "quality" || String(result?.mode || "").toLowerCase() !== "full") return metric;
  const rows = Array.isArray(metric.subcategories) ? metric.subcategories : [];
  const hasNonReasoningLane = rows.some((row) => String(row?.id || "").toLowerCase() === "quality_non_reasoning_lane");
  const hasSandboxLane = rows.some((row) => String(row?.id || "").toLowerCase() === "quality_sandbox_lane");
  if (hasNonReasoningLane) {
    if (hasSandboxLane) return metric;
    let sandboxParent = null;
    const nextRows = rows.map((row) => {
      if (String(row?.id || "").toLowerCase() !== "quality_non_reasoning_lane") return row;
      const grouped = modelScoreQualitySandboxGroup(row?.subcategories || []);
      sandboxParent = grouped.parent;
      return { ...row, subcategories: grouped.rows };
    });
    return sandboxParent ? { ...metric, subcategories: [...nextRows, sandboxParent] } : metric;
  }
  const groupedNonReasoning = modelScoreQualitySandboxGroup(
    rows.filter((row) => !String(row?.id || "").toLowerCase().includes("reason")),
  );
  const nonReasoningRows = groupedNonReasoning.rows;
  const pass = Number(metric.pass_count);
  const total = Number(metric.total_count);
  const missingReasoningRows = (nonReasoningRows.length ? nonReasoningRows : rows).map((row, index) => ({
    id: `quality_reasoning_${row?.id || index}`,
    label: row?.label || "Quality Pack",
    score: 0,
    weight: 0,
    method: "Run the reasoning-enabled Full quality stage to populate this row.",
    evidence: ["quality-full-reasoning.log"],
    missing: true,
  }));
  const nonReasoningLane = {
    id: "quality_non_reasoning_lane",
    label: "Non-Reasoning Quality",
    score: metric.score,
    weight: 1,
    value: Number.isFinite(pass) && Number.isFinite(total) && total > 0 ? Number(((pass / total) * 100).toFixed(1)) : metric.value,
    unit: "%",
    pass_count: Number.isFinite(pass) ? pass : undefined,
    total_count: Number.isFinite(total) ? total : undefined,
    method: "Parent lane for non-reasoning Full quality packs.",
    evidence: ["quality-full.log"],
    subcategories: nonReasoningRows,
    missing: !!metric.missing,
  };
  const reasoningLane = {
    id: "quality_reasoning_lane",
    label: "Reasoning Quality",
    score: 0,
    weight: 0,
    value: undefined,
    unit: "%",
    pass_count: undefined,
    total_count: undefined,
    method: "Reasoning-enabled Full quality stage; can add a small final-score bonus and never penalizes absent older results.",
    evidence: ["quality-full-reasoning.log"],
    missing: true,
    subcategories: [
      ...missingReasoningRows,
      {
        id: "quality_reasoning_bonus",
        label: "Reasoning Bonus",
        score: 0,
        weight: 0,
        display_value: "+0.00 final score",
        score_visible: false,
        bar_visible: false,
        method: "Reasoning quality can add up to +0.25 to the final Full score and never penalizes when absent.",
        evidence: ["quality-full-reasoning.log"],
        missing: true,
      },
    ],
  };
  return { ...metric, subcategories: [nonReasoningLane, reasoningLane, groupedNonReasoning.parent] };
}
function renderModelScoreBreakdown(result = {}, comparison = null) {
  const rows = modelScoreMetricRows(result);
  if (!modelScoreComplete(result)) {
    return '<div class="empty-variant-note">No metric details are available yet.</div>';
  }
  return rows
    .map((metric) => {
      metric = modelScoreFullQualityMetricWithLanes(metric, result);
      const pct = modelScoreBarPercent(metric.score);
      const pctLabel = modelScorePercentLabel(pct);
      const passCount = modelScorePassCountText(metric);
      const rawCompareMetric = comparison ? modelScoreMetricById(comparison.compare, metric.id) : null;
      const compareMetric = rawCompareMetric ? modelScoreFullQualityMetricWithLanes(rawCompareMetric, comparison.compare || {}) : null;
      const metricComparison = compareMetric ? { ...comparison, metric: compareMetric } : null;
      const elapsed = !comparison ? formatElapsedSeconds(metric.duration_seconds) : "";
      const metricLabel = `${escapeHtml(metric.label)}${elapsed ? ` <small class="score-detail-elapsed">(${escapeHtml(elapsed)})</small>` : ""}`;
      const metricValue = metricComparison
        ? renderScoreComparisonValuesHtml(formatModelScoreValue(metric.score), formatModelScoreValue(compareMetric.score), metricComparison)
        : `<span>${escapeHtml(formatModelScoreValue(metric.score))}</span>`;
      const subcategories = metric.subcategories.length
        ? metric.subcategories.map((row, subIndex) => renderModelScoreSubcategory(row, metric, subIndex, row?.id || row?.label || subIndex, result, metricComparison)).join("")
        : `<div class="preset-help">${escapeHtml(modelScoreMissingSubcategoryDescription(metric))}</div>`;
      const rerunButton = renderIconButton({
        title: `Rerun ${metric.label} only`,
        action: `rerunModelScoreCategory('${escapeJs(metric.id)}')`,
        icon: "refresh",
        className: "score-category-refresh-btn",
      });
      return `<details class="score-metric-detail resource-manager-card" data-score-detail-key="${escapeHtml(`metric:${metric.id}`)}" open><summary><span class="score-collapse-cue">▾</span><span>${metricLabel}</span>${metricValue}</summary><div class="score-bar-row"><div class="score-bar-track"><i style="width:${pct}%"></i></div><span>${pctLabel}${passCount ? ` · ${escapeHtml(passCount)}` : ""}</span>${rerunButton}</div><div class="preset-help">${escapeHtml(modelScoreMetricDescription(metric, result))}</div>${subcategories}</details>`;
    })
    .join("");
}
function ensureBenchmarkAllModal() {
  if ($("benchmarkAllModal")) return;
  const modal = document.createElement("div");
  modal.id = "benchmarkAllModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card benchmark-modal-card" role="dialog" aria-modal="true" aria-labelledby="benchmarkAllTitle"><div class="panel-head benchmark-modal-drag-handle" onpointerdown="startBenchmarkModalDrag(event,'modal')"><h2 id="benchmarkAllTitle">Benchmarks</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeBenchmarkAllModal()">✕</button></div><div id="benchmarkAllBody"></div><div class="msg" id="benchmarkAllMsg"></div></div>`;
  document.body.appendChild(modal);
}
function benchmarkFloatingPositionFromStorage(value) {
  if (!value || typeof value !== "object") return null;
  const left = Number(value.left);
  const top = Number(value.top);
  return Number.isFinite(left) && Number.isFinite(top) ? { left, top } : null;
}
function hydrateBenchmarkFloatingState() {
  if (benchmarkFloatingStateHydrated) return;
  benchmarkFloatingStateHydrated = true;
  try {
    const payload = JSON.parse(localStorage.getItem(BENCHMARK_FLOATING_STATE_KEY) || "{}");
    if (!payload || typeof payload !== "object") return;
    benchmarkModalCollapsed = !!payload.collapsed;
    benchmarkMiniHidden = !!payload.mini_hidden;
    benchmarkModalOpenPersisted = !!payload.modal_open && !benchmarkModalCollapsed;
    benchmarkModalPosition = benchmarkFloatingPositionFromStorage(payload.modal_position);
    benchmarkMiniPosition = benchmarkFloatingPositionFromStorage(payload.mini_position);
  } catch (error) {}
}
function persistBenchmarkFloatingState() {
  try {
    localStorage.setItem(
      BENCHMARK_FLOATING_STATE_KEY,
      JSON.stringify({
        collapsed: !!benchmarkModalCollapsed,
        mini_hidden: !!benchmarkMiniHidden,
        modal_open: !!benchmarkModalOpenPersisted,
        modal_position: benchmarkModalPosition || null,
        mini_position: benchmarkMiniPosition || null,
      }),
    );
  } catch (error) {}
}
function openBenchmarkAllModal() {
  ensureBenchmarkAllModal();
  hydrateBenchmarkFloatingState();
  benchmarkModalCollapsed = false;
  benchmarkMiniHidden = false;
  benchmarkModalOpenPersisted = true;
  benchmarkModalAwaitingFreshSnapshot = true;
  benchmarkModalControlsLocked = true;
  persistBenchmarkFloatingState();
  $("benchmarkAllModal").classList.remove("hidden");
  applyBenchmarkModalPosition();
  renderBenchmarkMiniWindow();
  renderBenchmarkAllModal();
  refreshBenchmarkSnapshot({ live: benchmarkJobActive() })
    .then(() => {
      renderBenchmarkAllModal();
      return refreshStatus({ force: true }).catch(() => {});
    })
    .then(() => renderBenchmarkAllModal())
    .catch(() => {
      benchmarkModalAwaitingFreshSnapshot = false;
      benchmarkModalControlsLocked = false;
      renderBenchmarkAllModal();
    });
}
function benchmarkRowForSelectorInCounts(selector = "", counts = {}) {
  const key = String(selector || "").trim();
  if (!key) return null;
  return benchmarkInventoryRows(counts).find((row) => String(row?.selector || "") === key) || null;
}
function preselectBenchmarkPreset(selector = "", mode = "full") {
  const key = String(selector || "").trim();
  if (!key) return false;
  const benchMode = String(mode || "full") === "quick" ? "quick" : "full";
  const counts = benchmarkSnapshot().counts_by_mode?.[benchMode] || benchmarkSnapshot().counts || {};
  const row = benchmarkRowForSelectorInCounts(key, counts);
  const selectedStages = benchmarkSelectedStages(benchMode, key, row, counts);
  benchmarkAllModalMode = benchMode;
  benchmarkQueueSelectionByMode[benchMode] = [key];
  benchmarkQueueOrderByMode[benchMode] = [
    key,
    ...(benchmarkQueueOrderByMode[benchMode] || []).filter((selector) => selector !== key),
  ];
  benchmarkStageSelectionByMode[benchMode][key] = [...selectedStages];
  return true;
}
function openBenchmarkForPreset(selector = "", mode = "full") {
  const key = String(selector || "").trim();
  if (!key) {
    openBenchmarkAllModal();
    return;
  }
  openBenchmarkAllModal();
  refreshBenchmarkSnapshot({ live: benchmarkJobActive() })
    .then(() => {
      preselectBenchmarkPreset(key, mode);
      renderBenchmarkAllModal();
    })
    .catch(() => {
      preselectBenchmarkPreset(key, mode);
      renderBenchmarkAllModal();
    });
}
function closeBenchmarkAllModal() {
  ensureBenchmarkAllModal();
  hydrateBenchmarkFloatingState();
  if (benchmarkJobFinishedReviewable()) {
    benchmarkModalCollapsed = false;
    benchmarkMiniHidden = true;
    benchmarkModalOpenPersisted = false;
    persistBenchmarkFloatingState();
    $("benchmarkAllModal").classList.add("hidden");
    renderBenchmarkMiniWindow();
    return;
  }
  if (benchmarkJobActive()) {
    collapseBenchmarkAllModal();
    return;
  }
  benchmarkModalCollapsed = false;
  benchmarkMiniHidden = false;
  benchmarkModalOpenPersisted = false;
  persistBenchmarkFloatingState();
  $("benchmarkAllModal").classList.add("hidden");
  renderBenchmarkMiniWindow();
}
function collapseBenchmarkAllModal() {
  ensureBenchmarkAllModal();
  hydrateBenchmarkFloatingState();
  benchmarkModalCollapsed = true;
  benchmarkMiniHidden = false;
  benchmarkModalOpenPersisted = false;
  persistBenchmarkFloatingState();
  $("benchmarkAllModal").classList.add("hidden");
  renderBenchmarkMiniWindow();
}
function restoreBenchmarkAllModalFromMini() {
  hydrateBenchmarkFloatingState();
  benchmarkModalCollapsed = false;
  benchmarkMiniHidden = false;
  benchmarkModalOpenPersisted = true;
  persistBenchmarkFloatingState();
  openBenchmarkAllModal();
}
function closeBenchmarkMiniWindow() {
  hydrateBenchmarkFloatingState();
  benchmarkMiniHidden = true;
  persistBenchmarkFloatingState();
  renderBenchmarkMiniWindow();
}
function clampBenchmarkFloatingPosition(position = {}, width = 360, height = 220) {
  const margin = 10;
  const maxLeft = Math.max(margin, window.innerWidth - width - margin);
  const maxTop = Math.max(margin, window.innerHeight - height - margin);
  return {
    left: Math.min(Math.max(margin, Number(position.left || margin)), maxLeft),
    top: Math.min(Math.max(margin, Number(position.top || margin)), maxTop),
  };
}
function applyBenchmarkModalPosition() {
  hydrateBenchmarkFloatingState();
  const card = document.querySelector("#benchmarkAllModal .benchmark-modal-card");
  if (!card || !benchmarkModalPosition) return;
  const pos = clampBenchmarkFloatingPosition(benchmarkModalPosition, card.offsetWidth || 980, card.offsetHeight || 720);
  benchmarkModalPosition = pos;
  card.style.left = `${pos.left}px`;
  card.style.top = `${pos.top}px`;
}
function startBenchmarkModalDrag(event, target = "modal") {
  if (event?.button !== undefined && event.button !== 0) return;
  if (event?.target?.closest?.("button,input,select,textarea,a")) return;
  const node = target === "mini" ? $("benchmarkMiniWindow") : document.querySelector("#benchmarkAllModal .benchmark-modal-card");
  if (!node) return;
  const rect = node.getBoundingClientRect();
  benchmarkDragState = {
    target,
    offsetX: Number(event.clientX || 0) - rect.left,
    offsetY: Number(event.clientY || 0) - rect.top,
    width: rect.width,
    height: rect.height,
    pointerId: event.pointerId,
    node,
  };
  try { node.setPointerCapture?.(event.pointerId); } catch (error) {}
  node.classList.add("benchmark-floating-dragging");
  window.addEventListener("pointermove", moveBenchmarkModalDrag);
  window.addEventListener("pointerup", stopBenchmarkModalDrag);
  window.addEventListener("pointercancel", stopBenchmarkModalDrag);
  node.addEventListener("lostpointercapture", stopBenchmarkModalDrag);
  window.addEventListener("blur", stopBenchmarkModalDrag);
  window.addEventListener("scroll", stopBenchmarkModalDrag, { passive: true });
  event.preventDefault?.();
}
function moveBenchmarkModalDrag(event) {
  if (!benchmarkDragState) return;
  if (benchmarkDragState.pointerId !== undefined && event?.pointerId !== undefined && event.pointerId !== benchmarkDragState.pointerId) return;
  const pos = clampBenchmarkFloatingPosition(
    { left: Number(event.clientX || 0) - benchmarkDragState.offsetX, top: Number(event.clientY || 0) - benchmarkDragState.offsetY },
    benchmarkDragState.width,
    benchmarkDragState.height,
  );
  if (benchmarkDragState.target === "mini") {
    benchmarkMiniPosition = pos;
    const mini = $("benchmarkMiniWindow");
    if (mini) {
      mini.style.left = `${pos.left}px`;
      mini.style.top = `${pos.top}px`;
    }
  } else {
    benchmarkModalPosition = pos;
    const card = document.querySelector("#benchmarkAllModal .benchmark-modal-card");
    if (card) {
      card.style.left = `${pos.left}px`;
      card.style.top = `${pos.top}px`;
    }
  }
}
function stopBenchmarkModalDrag() {
  const node = benchmarkDragState?.node || null;
  window.removeEventListener("pointermove", moveBenchmarkModalDrag);
  window.removeEventListener("pointerup", stopBenchmarkModalDrag);
  window.removeEventListener("pointercancel", stopBenchmarkModalDrag);
  node?.removeEventListener?.("lostpointercapture", stopBenchmarkModalDrag);
  window.removeEventListener("blur", stopBenchmarkModalDrag);
  window.removeEventListener("scroll", stopBenchmarkModalDrag);
  node?.classList.remove("benchmark-floating-dragging");
  try { node?.releasePointerCapture?.(benchmarkDragState?.pointerId); } catch (error) {}
  benchmarkDragState = null;
  persistBenchmarkFloatingState();
}
function setBenchmarkAllMode(mode) {
  benchmarkAllModalMode = String(mode || "quick") === "full" ? "full" : "quick";
  renderBenchmarkAllModal();
}
function benchmarkInventoryRows(counts = {}) {
  const groups = [
    { rows: Array.isArray(counts.skipped_presets) ? counts.skipped_presets : [], priority: 1 },
    { rows: Array.isArray(counts.already_scored_presets) ? counts.already_scored_presets : [], priority: 2 },
    { rows: Array.isArray(counts.eligible_presets) ? counts.eligible_presets : [], priority: 3 },
    { rows: Array.isArray(counts.ineligible_presets) ? counts.ineligible_presets : [], priority: 4 },
  ];
  const bySelector = new Map();
  const order = [];
  groups.forEach((group) => {
    group.rows.forEach((row) => {
      const selector = String(row?.selector || "");
      if (!selector) return;
      const existing = bySelector.get(selector);
      if (!existing) order.push(selector);
      if (!existing || group.priority > existing.priority) {
        bySelector.set(selector, { row, priority: group.priority });
      }
    });
  });
  return order.map((selector) => bySelector.get(selector)?.row).filter(Boolean);
}
function benchmarkIneligibleReasonCode(row = {}) {
  return String(row?.skip_reason || row?.reason_code || "").trim().toLowerCase().replaceAll("_", "-");
}
function benchmarkIneligibleReason(row = {}) {
  return [
    "resources-not-ready",
    "hardware-blocked",
    "hardware-blocked-wna16-ampere",
    "nvlink-required",
    "blocked",
    "tombstoned",
  ].includes(benchmarkIneligibleReasonCode(row));
}
function benchmarkIneligibleReasonText(row = {}) {
  const explicit = String(row?.reason || row?.skip_message || "").trim();
  if (explicit && !["resources-not-ready", "hardware-blocked", "hardware_blocked", "hardware-blocked-wna16-ampere", "nvlink-required", "blocked", "tombstoned"].includes(explicit.toLowerCase())) return explicit;
  switch (benchmarkIneligibleReasonCode(row)) {
    case "resources-not-ready": return "Required model assets are not ready on disk.";
    case "hardware-blocked-wna16-ampere": return "Requires an SM90-capable kernel path; this RTX 3090 host is Ampere-class.";
    case "hardware-blocked": return "This preset cannot run on the currently detected GPU hardware.";
    case "nvlink-required": return "Requires NVLink, but NVLink is not available on this host.";
    case "tombstoned": return "This preset has been retired.";
    case "blocked": return "This preset is blocked for this host.";
    default: return explicit || "This preset is not eligible for benchmarking.";
  }
}
function benchmarkInventorySelectorsByKind(counts = {}, kind = "") {
  const wanted = String(kind || "").trim().toLowerCase();
  if (wanted === "ineligible") {
    return (counts.ineligible_presets || []).map((row) => String(row?.selector || "")).filter(Boolean);
  }
  return benchmarkInventoryRows(counts)
    .filter((row) => String(row?.status_kind || "").trim().toLowerCase() === wanted)
    .map((row) => String(row?.selector || ""))
    .filter(Boolean);
}
const BENCHMARK_DEFAULT_STAGE_OPTIONS = {
  quick: [
    { id: "verify", label: "Verify smoke" },
    { id: "bench", label: "Quick throughput" },
    { id: "quality-quick", label: "Quality quick" },
    { id: "quality-reasoning-quick", label: "Reasoning quick" },
    { id: "compliance", label: "Compliance quick" },
    { id: "metadata", label: "Capability probes" },
  ],
  full: [
    { id: "verify-full", label: "Verify full" },
    { id: "bench", label: "Throughput bench" },
    { id: "verify-stress", label: "Verify stress" },
    { id: "quality-full", label: "Quality full" },
    { id: "quality-sandbox", label: "Quality sandbox packs" },
    { id: "quality-full-reasoning", label: "Quality reasoning" },
    { id: "quality-reasoning", label: "Reasoning suite" },
    { id: "compliance", label: "Compliance harness" },
    { id: "soak", label: "Soak stability" },
  ],
};
function benchmarkDefaultStageOptions(mode) {
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  return BENCHMARK_DEFAULT_STAGE_OPTIONS[key].map((stage) => ({ ...stage }));
}
function benchmarkStageOptions(mode, counts = null) {
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  const source = counts || benchmarkSnapshot().counts_by_mode?.[key] || benchmarkSnapshot().counts || {};
  const stages = Array.isArray(source.stages) ? source.stages.filter((stage) => stage?.id) : [];
  return stages.length ? stages : benchmarkDefaultStageOptions(key);
}
function benchmarkSelectedStages(mode, selector, row = null, counts = null) {
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  const preset = String(selector || "");
  const allowed = new Set(benchmarkStageOptions(key, counts).map((stage) => String(stage.id || "")).filter(Boolean));
  const saved = benchmarkStageSelectionByMode[key]?.[preset];
  if (Array.isArray(saved)) {
    const selected = saved.map(String).filter((stageId) => allowed.has(stageId));
    return new Set(selected);
  }
  const sourceRow = row || benchmarkRowForSelectorInCounts(preset, counts || benchmarkSnapshot().counts_by_mode?.[key] || benchmarkSnapshot().counts || {});
  if (Array.isArray(sourceRow?.selected_step_ids)) {
    const selected = sourceRow.selected_step_ids.map(String).filter((stageId) => allowed.has(stageId));
    return new Set(selected);
  }
  return new Set([...allowed]);
}
function normalizeBenchmarkStageStatus(value) {
  const status = String(value || "").trim().toLowerCase();
  if (["complete", "completed", "pass", "passed", "success", "green"].includes(status)) return "complete";
  if (["fail", "failed", "error", "red"].includes(status)) return "failed";
  if (["active", "running", "run", "yellow"].includes(status)) return "active";
  if (["warning", "warn", "stale", "invalid", "suspect"].includes(status)) return "warning";
  if (["deferred", "defer", "thermal-deferred", "waiting", "hourglass"].includes(status)) return "deferred";
  if (["missing-next", "next", "soon"].includes(status)) return "missing-next";
  if (["missing", "pending", "queued", "white"].includes(status)) return "missing";
  return "default";
}
function benchmarkStageStatusIconHtml(status) {
  const normalized = normalizeBenchmarkStageStatus(status);
  if (normalized === "missing-next") {
    return '<span class="benchmark-stage-status-icon benchmark-stage-status-icon-next" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d="M5 5l8 7-8 7V5zm9 0h2v14h-2V5zm4 0h2v14h-2V5z"/></svg></span>';
  }
  const icons = {
    complete: "✅",
    failed: "❌",
    warning: "⚠️",
    active: "⏱️",
    deferred: "⏳",
    default: "",
  };
  const icon = icons[normalized] ?? icons.default;
  return icon ? `<span class="benchmark-stage-status-icon" aria-hidden="true">${icon}</span>` : "";
}
function benchmarkStageStatusTitle(status, label) {
  const normalized = normalizeBenchmarkStageStatus(status);
  const name = String(label || "Stage");
  if (normalized === "complete") return `${name}: already run and verified.`;
  if (normalized === "failed") return `${name}: failed, interrupted, or currently has invalid evidence; selected reruns will repair it.`;
  if (normalized === "warning") return `${name}: stale or suspicious benchmark evidence needs review.`;
  if (normalized === "active") return `${name}: currently running.`;
  if (normalized === "missing-next") return `${name}: queued to run after the current active benchmark stage.`;
  if (normalized === "missing") return `${name}: selected for this benchmark run; no valid completed evidence is recorded yet.`;
  if (normalized === "deferred") return `${name}: deferred for a future rerun.`;
  return `${name}: not selected for this benchmark run.`;
}
function benchmarkStageControlKey(row, selector, stageId) {
  const preset = String(row?.selector || selector || "").trim();
  const step = String(stageId || "").trim();
  return preset && step ? `${preset}\u001f${step}` : "";
}
function benchmarkStageStatusForRow(row, stageId, selected = false) {
  const id = String(stageId || "");
  if (!id) return "default";
  const jobActive = !!benchmarkJob()?.active;
  const statusMap = row?.stage_statuses && typeof row.stage_statuses === "object" ? row.stage_statuses : {};
  const mapped = normalizeBenchmarkStageStatus(statusMap[id]);
  const rowStatus = String(row?.status || "").toLowerCase();
  const currentStep = String(row?.step_id || "");
  if (mapped === "missing" && selected && jobActive && rowStatus === "running" && currentStep && currentStep !== id) {
    const mode = String(row?.mode || benchmarkJob()?.mode || benchmarkAllModalMode || "quick") === "full" ? "full" : "quick";
    const stageOrder = benchmarkStageOptions(mode).map((stage) => String(stage?.id || "")).filter(Boolean);
    const stageIndex = stageOrder.indexOf(id);
    const currentIndex = stageOrder.indexOf(currentStep);
    if (stageIndex >= 0 && currentIndex >= 0 && stageIndex < currentIndex) return "deferred";
  }
  if ((mapped === "active" || mapped === "deferred") && !jobActive) return selected ? "missing" : "default";
  if (mapped === "missing" && !selected) return "default";
  if (mapped !== "default") return mapped;
  if (jobActive && rowStatus === "running" && String(row?.step_id || "") === id) return "active";
  let latest = "";
  (Array.isArray(row?.step_history) ? row.step_history : []).forEach((step) => {
    const key = String(step?.id || step?.step_id || "");
    if (key === id) latest = String(step?.status || "").toLowerCase();
  });
  if (latest === "pass") return "complete";
  if (latest === "fail") return "failed";
  return selected ? "missing" : "default";
}
function benchmarkStageIsRunnableNext(status) {
  return ["missing", "failed", "warning"].includes(normalizeBenchmarkStageStatus(status));
}
function benchmarkReadonlyOrderedRows(job = benchmarkJob()) {
  const rows = benchmarkQueueRows(job);
  const selectors = rows.map((row) => String(row?.selector || "")).filter(Boolean);
  const preferred = Array.isArray(job?.queue_order) ? job.queue_order.map(String) : [];
  const order = [...preferred.filter((selector) => selectors.includes(selector)), ...selectors.filter((selector) => !preferred.includes(selector))];
  const rank = new Map(order.map((selector, index) => [selector, index]));
  return [...rows].sort((left, right) => {
    const leftSelector = String(left?.selector || "");
    const rightSelector = String(right?.selector || "");
    return (rank.get(leftSelector) ?? rows.indexOf(left)) - (rank.get(rightSelector) ?? rows.indexOf(right));
  });
}
function benchmarkNextStageMarkerKeys(mode) {
  const job = benchmarkJob();
  const markers = new Set();
  if (!job?.active) return markers;
  const key = String(mode || job.mode || benchmarkAllModalMode || "quick") === "full" ? "full" : "quick";
  const counts = benchmarkSnapshot().counts_by_mode?.[key] || benchmarkSnapshot().counts || {};
  const options = benchmarkStageOptions(key, counts);
  if (!options.length) return markers;
  for (const row of benchmarkReadonlyOrderedRows(job)) {
    const rowStatus = String(row?.status || "").toLowerCase();
    if (rowStatus !== "running") continue;
    const selector = String(row?.selector || "");
    const selected = benchmarkSelectedStages(key, selector, row, counts);
    const current = String(row?.step_id || "");
    let afterCurrent = !options.some((stage) => String(stage?.id || "") === current);
    for (const stage of options) {
      const stageId = String(stage?.id || "");
      if (!stageId) continue;
      if (stageId === current) {
        afterCurrent = true;
        continue;
      }
      if (!afterCurrent || !selected.has(stageId)) continue;
      const status = benchmarkStageStatusForRow(row, stageId, true);
      if (benchmarkStageIsRunnableNext(status)) {
        markers.add(benchmarkStageControlKey(row, selector, stageId));
        break;
      }
    }
  }
  return markers;
}
function benchmarkNextStageMarkerKey(mode) {
  return [...benchmarkNextStageMarkerKeys(mode)][0] || "";
}
function benchmarkStageSelectionsPayload(mode, selectors, job = null) {
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  const counts = benchmarkSnapshot().counts_by_mode?.[key] || benchmarkSnapshot().counts || {};
  const rows = new Map(benchmarkQueueRows(job || {}).map((row) => [String(row?.selector || ""), row]));
  const inventoryRows = new Map(benchmarkInventoryRows(counts).map((row) => [String(row?.selector || ""), row]));
  return Object.fromEntries(
    (selectors || []).map(String).filter(Boolean).map((selector) => [
      selector,
      [...benchmarkSelectedStages(key, selector, rows.get(selector) || inventoryRows.get(selector) || null, counts)],
    ]),
  );
}
function benchmarkRunnableStagePayload(mode, selectors, job = null) {
  const stages = benchmarkStageSelectionsPayload(mode, selectors, job);
  const runnableSelectors = [];
  const runnableStages = {};
  (selectors || []).map(String).filter(Boolean).forEach((selector) => {
    const selectedStages = Array.isArray(stages[selector]) ? stages[selector].map(String).filter(Boolean) : [];
    if (!selectedStages.length) return;
    runnableSelectors.push(selector);
    runnableStages[selector] = selectedStages;
  });
  return { selectors: runnableSelectors, stages: runnableStages };
}
function renderBenchmarkStageControls(mode, selector, row = null, disabled = false) {
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  const counts = benchmarkSnapshot().counts_by_mode?.[key] || benchmarkSnapshot().counts || {};
  const selected = benchmarkSelectedStages(key, selector, row, counts);
  const options = benchmarkStageOptions(key, counts);
  if (!options.length) return "";
  const rowStatus = String(row?.status || "").toLowerCase();
  const interactionDisabled = disabled || rowStatus === "failed";
  const nextStageKeys = benchmarkNextStageMarkerKeys(key);
  const controls = options.map((stage) => {
    const stageId = String(stage?.id || "");
    const stageLabel = String(stage?.label || stageId);
    const checked = selected.has(stageId);
    const baseStatus = benchmarkStageStatusForRow(row, stageId, checked);
    const iconStatus = baseStatus === "missing" && nextStageKeys.has(benchmarkStageControlKey(row, selector, stageId)) ? "missing-next" : baseStatus;
    const title = benchmarkStageStatusTitle(iconStatus, stageLabel);
    return `<label class="benchmark-stage-status-${escapeHtml(baseStatus)}" data-stage-status="${escapeHtml(baseStatus)}" title="${escapeHtml(title)}"><input type="checkbox" ${checked ? "checked" : ""} ${interactionDisabled ? "disabled" : ""} onclick="event.stopPropagation()" onchange="updateBenchmarkStageSelection('${escapeJs(key)}','${escapeJs(selector)}','${escapeJs(stageId)}',this.checked)" /><span>${escapeHtml(stageLabel)} ${benchmarkStageStatusIconHtml(iconStatus)}</span></label>`;
  }).join("");
  return `<div class="benchmark-stage-selector"><div class="preset-help">Stages <small>Launch runs automatically.</small></div><div class="benchmark-stage-selector-grid">${controls}</div></div>`;
}
function ensureBenchmarkQueueSelection(mode, counts = {}) {
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  const allRows = benchmarkInventoryRows(counts);
  if (!Array.isArray(benchmarkQueueSelectionByMode[key])) {
    benchmarkQueueSelectionByMode[key] = benchmarkInventorySelectorsForGroup(counts, "eligible");
  }
  const known = new Set(allRows.map((row) => String(row?.selector || "")).filter(Boolean));
  const ineligible = new Set(benchmarkInventorySelectorsForGroup(counts, "ineligible"));
  benchmarkQueueSelectionByMode[key] = benchmarkQueueSelectionByMode[key].filter((selector) => known.has(selector) && !ineligible.has(selector));
  const selected = new Set(benchmarkQueueSelectionByMode[key]);
  const existingOrder = Array.isArray(benchmarkQueueOrderByMode[key]) ? benchmarkQueueOrderByMode[key] : [];
  benchmarkQueueOrderByMode[key] = [
    ...existingOrder.filter((selector) => known.has(selector)),
    ...allRows.map((row) => String(row?.selector || "")).filter((selector) => selector && !existingOrder.includes(selector)),
  ];
  return selected;
}
function benchmarkActiveSelectedSelectors(job = benchmarkJob()) {
  return benchmarkQueueRows(job)
    .filter((row) => row && String(row.status || "") !== "skipped")
    .map((row) => String(row.selector || ""))
    .filter(Boolean);
}
function benchmarkActiveQueueOrder(job = benchmarkJob()) {
  const rows = benchmarkQueueRows(job);
  const selectors = rows.map((row) => String(row?.selector || "")).filter(Boolean);
  const preferred = Array.isArray(job.queue_order) ? job.queue_order.map(String) : [];
  const serverOrder = [...preferred.filter((selector) => selectors.includes(selector)), ...selectors.filter((selector) => !preferred.includes(selector))];
  if (!job?.active) {
    benchmarkStableActiveQueueOrderState = { key: "", order: [] };
    return serverOrder;
  }
  const jobKey = [
    String(job.job_id || ""),
    String(job.mode || benchmarkAllModalMode || ""),
    [...selectors].sort().join("\u001f"),
  ].join("\u001e");
  const previous = benchmarkStableActiveQueueOrderState.key === jobKey
    ? benchmarkStableActiveQueueOrderState.order
    : [];
  const selectorSet = new Set(selectors);
  const runningOrder = serverOrder.filter((selector) =>
    rows.some((row) => String(row?.selector || "") === selector && String(row?.status || "") === "running")
  );
  const stableOrder = [
    ...runningOrder,
    ...previous.filter((selector) => selectorSet.has(selector) && !runningOrder.includes(selector)),
    ...serverOrder.filter((selector) => selectorSet.has(selector) && !runningOrder.includes(selector) && !previous.includes(selector)),
  ];
  benchmarkStableActiveQueueOrderState = { key: jobKey, order: stableOrder };
  return stableOrder;
}
function benchmarkOrderedQueueRows(job = benchmarkJob()) {
  const rows = benchmarkQueueRows(job);
  const activeOrder = benchmarkActiveQueueOrder(job);
  const activeRank = new Map(activeOrder.map((selector, index) => [selector, index]));
  return [...rows].sort((left, right) => {
    const leftSelector = String(left?.selector || "");
    const rightSelector = String(right?.selector || "");
    return (activeRank.get(leftSelector) ?? rows.indexOf(left)) - (activeRank.get(rightSelector) ?? rows.indexOf(right));
  });
}
function benchmarkInventorySelectorsForGroup(counts = {}, kind = "eligible") {
  const group = String(kind || "").trim().toLowerCase();
  const rows = benchmarkInventoryRows(counts);
  const rawEligible = new Set((counts.eligible_presets || []).map((row) => String(row?.selector || "")).filter(Boolean));
  const rawCompleted = new Set((counts.already_scored_presets || []).map((row) => String(row?.selector || "")).filter(Boolean));
  const rawIneligible = new Set((counts.ineligible_presets || []).map((row) => String(row?.selector || "")).filter(Boolean));
  if (group === "ineligible") {
    return rows
      .filter((row) => rawIneligible.has(String(row?.selector || "")) || benchmarkIneligibleReason(row))
      .map((row) => String(row?.selector || ""))
      .filter(Boolean);
  }
  if (group === "already-scored") {
    return rows
      .filter((row) => {
        const selector = String(row?.selector || "");
        return selector && rawCompleted.has(selector) && !rawEligible.has(selector) && !rawIneligible.has(selector);
      })
      .map((row) => String(row?.selector || ""))
      .filter(Boolean);
  }
  if (group === "experimental" || group === "deprecated") {
    return rows
      .filter((row) => {
        const selector = String(row?.selector || "");
        return selector
          && String(row?.status_kind || "").trim().toLowerCase() === group
          && !rawEligible.has(selector)
          && !rawCompleted.has(selector)
          && !rawIneligible.has(selector);
      })
      .map((row) => String(row?.selector || ""))
      .filter(Boolean);
  }
  return rows
    .filter((row) => {
      const selector = String(row?.selector || "");
      return selector && rawEligible.has(selector) && !rawIneligible.has(selector);
    })
    .map((row) => String(row?.selector || ""))
    .filter(Boolean);
}
async function updateBenchmarkQueueSelection(mode, selector, checked) {
  rememberBenchmarkQueueScroll();
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  const counts = benchmarkSnapshot().counts_by_mode?.[key] || benchmarkSnapshot().counts || {};
  const preset = String(selector || "");
  if (benchmarkInventorySelectorsForGroup(counts, "ineligible").includes(preset)) {
    renderBenchmarkAllModal();
    return;
  }
  const job = benchmarkJob();
  if (job.active) {
    const row = benchmarkQueueRows(job).find((item) => String(item?.selector || "") === preset);
    if (!checked && String(row?.status || "") === "running") {
      const confirmed = await openClubConfirmModal("Remove the active preset after its current benchmark stage finishes?");
      if (!confirmed) {
        renderBenchmarkAllModal();
        return;
      }
    }
    const selected = new Set(benchmarkActiveSelectedSelectors(job));
    if (checked) selected.add(preset);
    else selected.delete(preset);
    try {
      const runnable = benchmarkRunnableStagePayload(key, [...selected], job);
      await post(
        "/admin/benchmarks/queue",
        {
          selectors: runnable.selectors,
          order: benchmarkActiveQueueOrder(job).filter((selector) => runnable.selectors.includes(selector)),
          stages: runnable.stages,
        },
        "/admin/benchmarks/queue",
      );
      await refreshStatus({ force: true });
    } catch (error) {
      setElementMsg("benchmarkAllMsg", messageText(error), "error");
    }
    renderBenchmarkAllModal();
    return;
  }
  const selected = ensureBenchmarkQueueSelection(key, counts);
  if (checked) selected.add(preset);
  else selected.delete(preset);
  benchmarkQueueSelectionByMode[key] = [...selected];
  renderBenchmarkAllModal();
}
async function updateBenchmarkStageSelection(mode, selector, stageId, checked) {
  rememberBenchmarkQueueScroll();
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  const preset = String(selector || "");
  const stage = String(stageId || "");
  const job = benchmarkJob();
  const active = !!job.active;
  const row = active ? benchmarkQueueRows(job).find((item) => String(item?.selector || "") === preset) : null;
  const counts = benchmarkSnapshot().counts_by_mode?.[key] || benchmarkSnapshot().counts || {};
  if (benchmarkInventorySelectorsForGroup(counts, "ineligible").includes(preset)) {
    renderBenchmarkAllModal();
    return;
  }
  const selected = benchmarkSelectedStages(key, preset, row, counts);
  if (checked) selected.add(stage);
  else selected.delete(stage);
  if (!selected.size) {
    alert("Select at least one benchmark stage for each queued preset.");
    renderBenchmarkAllModal();
    return;
  }
  if (!active) {
    benchmarkStageSelectionByMode[key][preset] = [...selected];
    renderBenchmarkAllModal();
    return;
  }
  const activeSelectors = benchmarkActiveSelectedSelectors(job);
  const stages = benchmarkStageSelectionsPayload(key, activeSelectors, job);
  stages[preset] = [...selected];
  try {
    await post(
      "/admin/benchmarks/queue",
      { selectors: activeSelectors, order: benchmarkActiveQueueOrder(job), stages },
      "/admin/benchmarks/queue",
    );
    await refreshStatus({ force: true });
  } catch (error) {
    setElementMsg("benchmarkAllMsg", messageText(error), "error");
  }
  renderBenchmarkAllModal();
}
async function setBenchmarkBulkSelection(mode, selectors, checked) {
  rememberBenchmarkQueueScroll();
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  const counts = benchmarkSnapshot().counts_by_mode?.[key] || benchmarkSnapshot().counts || {};
  const ineligible = new Set(benchmarkInventorySelectorsForGroup(counts, "ineligible"));
  const targets = (Array.isArray(selectors) ? selectors : []).map(String).filter((selector) => selector && !ineligible.has(selector));
  const job = benchmarkJob();
  const active = !!job.active;
  const selected = active ? new Set(benchmarkActiveSelectedSelectors(job)) : ensureBenchmarkQueueSelection(key, counts);
  if (active && targets.length) {
    const label = `${targets.length} preset${targets.length === 1 ? "" : "s"}`;
    const action = checked ? "Queue" : "Move";
    const destination = checked ? "into" : "out of";
    if (!(await openClubConfirmModal(`${action} ${label} from this category ${destination} the active ${key === "full" ? "Full" : "Quick"} benchmark?`))) {
      renderBenchmarkAllModal();
      return;
    }
  }
  targets.forEach((selector) => {
    if (!selector) return;
    if (checked) selected.add(selector);
    else selected.delete(selector);
  });
  if (active) {
    const activeOrder = benchmarkActiveQueueOrder(job);
    const inventoryOrder = benchmarkQueueOrderByMode[key] || benchmarkInventoryRows(counts).map((row) => String(row?.selector || "")).filter(Boolean);
    const order = [
      ...activeOrder.filter((selector) => selected.has(selector)),
      ...inventoryOrder.filter((selector) => selected.has(selector) && !activeOrder.includes(selector)),
    ];
    try {
      const runnable = benchmarkRunnableStagePayload(key, [...selected], job);
      await post(
        "/admin/benchmarks/queue",
        { selectors: runnable.selectors, order: order.filter((selector) => runnable.selectors.includes(selector)), stages: runnable.stages },
        "/admin/benchmarks/queue",
      );
      await refreshStatus({ force: true });
    } catch (error) {
      setElementMsg("benchmarkAllMsg", messageText(error), "error");
    }
    renderBenchmarkAllModal();
    return;
  }
  benchmarkQueueSelectionByMode[key] = [...selected];
  renderBenchmarkAllModal();
}
function setBenchmarkEligibleSelection(mode, checked) {
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  const job = benchmarkJob();
  if (job.active) {
    const targets = benchmarkQueueRows(job)
      .filter((row) => row && String(row.status || "") !== "skipped" && String(row.status || "") !== "running")
      .map((row) => String(row.selector || ""))
      .filter(Boolean);
    return setBenchmarkBulkSelection(key, targets, checked);
  }
  const counts = benchmarkSnapshot().counts_by_mode?.[key] || benchmarkSnapshot().counts || {};
  return setBenchmarkBulkSelection(key, benchmarkInventorySelectorsForGroup(counts, "eligible"), checked);
}
function setBenchmarkCompletedSelection(mode, checked) {
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  const counts = benchmarkSnapshot().counts_by_mode?.[key] || benchmarkSnapshot().counts || {};
  return setBenchmarkBulkSelection(key, benchmarkInventorySelectorsForGroup(counts, "already-scored"), checked);
}
function setBenchmarkStatusSelection(mode, statusKind, checked) {
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  const counts = benchmarkSnapshot().counts_by_mode?.[key] || benchmarkSnapshot().counts || {};
  return setBenchmarkBulkSelection(key, benchmarkInventorySelectorsForGroup(counts, statusKind), checked);
}
async function moveBenchmarkQueuePreset(event, mode, selector, direction) {
  event?.preventDefault?.();
  event?.stopPropagation?.();
  rememberBenchmarkQueueScroll();
  const job = benchmarkJob();
  const active = !!job.active;
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  const order = active ? benchmarkActiveQueueOrder(job) : [...(benchmarkQueueOrderByMode[key] || [])];
  const source = String(selector || "");
  const sourceIndex = order.indexOf(source);
  const targetIndex = sourceIndex + (Number(direction || 0) < 0 ? -1 : 1);
  if (sourceIndex < 0 || targetIndex < 0 || targetIndex >= order.length) return;
  [order[sourceIndex], order[targetIndex]] = [order[targetIndex], order[sourceIndex]];
  if (active) {
    try {
      await post(
        "/admin/benchmarks/queue",
        {
          selectors: benchmarkActiveSelectedSelectors(job),
          order,
          stages: benchmarkStageSelectionsPayload(key, benchmarkActiveSelectedSelectors(job), job),
        },
        "/admin/benchmarks/queue",
      );
      await refreshStatus({ force: true });
    } catch (error) {
      setElementMsg("benchmarkAllMsg", messageText(error), "error");
    }
  } else {
    benchmarkQueueOrderByMode[key] = order;
  }
  renderBenchmarkAllModal();
}
function focusBenchmarkModalLogs() {
  const target = $("benchmarkModalLogTail");
  if (!target) return;
  try {
    target.scrollIntoView({ block: "nearest", behavior: "smooth" });
  } catch (error) {}
  try {
    target.focus();
  } catch (error) {}
}
function rememberBenchmarkModalLogHeight() {
  const target = $("benchmarkModalLogTail");
  if (!target) return;
  const height = Math.round(target.getBoundingClientRect?.().height || target.offsetHeight || 0);
  if (height >= 120 && height <= 900) benchmarkModalLogHeight = height;
}
function benchmarkModalLogScrollMode(target = null) {
  const mode = String(target?.dataset?.logMode || benchmarkModalLogMode || "staged").toLowerCase();
  return mode === "full" ? "full" : "staged";
}
function rememberBenchmarkModalLogScroll() {
  const target = $("benchmarkModalLogTail");
  if (!target) return;
  benchmarkModalLogScrollTopByMode[benchmarkModalLogScrollMode(target)] = Number(target.scrollTop || 0);
}
function restoreBenchmarkModalLogHeight() {
  const target = $("benchmarkModalLogTail");
  if (!target) return;
  if (benchmarkModalLogHeight) target.style.height = `${benchmarkModalLogHeight}px`;
  if (typeof ResizeObserver === "function" && target.dataset.resizeObserved !== "1") {
    try {
      if (benchmarkModalLogResizeObserver) benchmarkModalLogResizeObserver.disconnect();
      benchmarkModalLogResizeObserver = new ResizeObserver(() => rememberBenchmarkModalLogHeight());
      benchmarkModalLogResizeObserver.observe(target);
      target.dataset.resizeObserved = "1";
    } catch (error) {}
  }
}
function restoreBenchmarkModalLogScroll() {
  const target = $("benchmarkModalLogTail");
  if (!target) return;
  const mode = benchmarkModalLogScrollMode(target);
  const maxScroll = Math.max(0, Number(target.scrollHeight || 0) - Number(target.clientHeight || 0));
  target.scrollTop = Math.min(Math.max(0, Number(benchmarkModalLogScrollTopByMode[mode] || 0)), maxScroll);
}
function setBenchmarkModalLogMode(mode) {
  rememberBenchmarkModalLogScroll();
  benchmarkModalLogMode = String(mode || "") === "full" ? "full" : "staged";
  renderBenchmarkAllModal();
}
function resetBenchmarkFinishedReview() {
  const job = benchmarkJob();
  const key = benchmarkFinishedReviewKey(job);
  if (key) {
    try {
      localStorage.setItem(BENCHMARK_FINISHED_REVIEW_KEY, key);
    } catch (error) {}
  }
  const mode = String(job.mode || benchmarkAllModalMode || "quick") === "full" ? "full" : "quick";
  benchmarkAllModalMode = mode;
  benchmarkRunningPresetTab = "";
  benchmarkModalControlsLocked = false;
  benchmarkModalAwaitingFreshSnapshot = false;
  renderBenchmarkAllModal();
  scheduleBenchmarkModalSnapshotRefresh(true);
}
function benchmarkSectionOpen(sectionId, defaultOpen = true) {
  const key = String(sectionId || "");
  if (Object.prototype.hasOwnProperty.call(benchmarkSectionOpenState, key)) {
    return !!benchmarkSectionOpenState[key];
  }
  return !!defaultOpen;
}
function setBenchmarkSectionOpenFromSummary(event, sectionId) {
  const key = String(sectionId || "");
  if (!key) return;
  const details = event?.currentTarget?.closest?.("details");
  benchmarkSectionOpenState[key] = !(details && details.open);
}
function renderBenchmarkSection(sectionId, className, title, badge, body, defaultOpen = true) {
  const open = benchmarkSectionOpen(sectionId, defaultOpen) ? "open" : "";
  return `<details class="${escapeHtml(className)}" data-benchmark-section="${escapeHtml(sectionId)}" ${open}><summary onclick="setBenchmarkSectionOpenFromSummary(event,'${escapeJs(sectionId)}')"><span>${title}</span><span>${badge}</span></summary>${body}</details>`;
}
function benchmarkQueueRows(job = benchmarkJob()) {
  return Array.isArray(job.queue) ? job.queue : [];
}
function benchmarkActiveQueueHiddenSkipReason(row = {}) {
  if (String(row?.status || "").toLowerCase() !== "skipped") return false;
  const skipReason = String(row?.skip_reason || row?.reason || "").trim().toLowerCase().replace(/_/g, "-");
  return skipReason === "not-selected" || skipReason.startsWith("removed from the active benchmark queue");
}
function benchmarkQueueCounts(job = benchmarkJob()) {
  const rows = benchmarkQueueRows(job);
  const counts = rows.reduce(
    (acc, row) => {
      if (benchmarkActiveQueueHiddenSkipReason(row)) return acc;
      acc.total += 1;
      if (row?.status === "skipped") {
        if (benchmarkIneligibleReason(row)) acc.ineligible += 1;
        else acc.skipped += 1;
      }
      else if (row?.status === "success" || row?.status === "completed" || row?.status === "failed") acc.finished += 1;
      else if (row?.status === "running") acc.running += 1;
      else acc.queued += 1;
      return acc;
    },
    { total: 0, skipped: 0, ineligible: 0, finished: 0, running: 0, queued: 0, runnable_total: 0, left: 0 },
  );
  counts.runnable_total = Math.max(0, Number(counts.total || 0) - Number(counts.skipped || 0) - Number(counts.ineligible || 0));
  counts.left = Math.max(0, Number(counts.runnable_total || 0) - Number(counts.finished || 0));
  return counts;
}
function benchmarkQueueRowKey(row = {}, index = 0) {
  return String(row.selector || row.id || row.display_name || `row-${index}`);
}
function rememberBenchmarkQueueScroll() {
  const queue = $("benchmarkPresetQueue");
  if (queue) benchmarkQueueScrollTop = Number(queue.scrollTop || 0);
}
function restoreBenchmarkQueueScroll() {
  const queue = $("benchmarkPresetQueue");
  if (!queue) return;
  const maxScroll = Math.max(0, Number(queue.scrollHeight || 0) - Number(queue.clientHeight || 0));
  queue.scrollTop = Math.min(Math.max(0, benchmarkQueueScrollTop), maxScroll);
}
function handleBenchmarkQueueSummaryClick(event, selector, key) {
  const details = event?.currentTarget?.closest?.("details");
  if (details && key) benchmarkQueueOpenState[String(key)] = !details.open;
  if (selector) benchmarkRunningPresetTab = String(selector || "");
  if (selector) benchmarkModalLogMode = "staged";
  if (selector) {
    benchmarkFocusPendingSelector = String(selector || "");
    benchmarkFocusPendingUntil = Date.now() + 5000;
  }
  rememberBenchmarkQueueScroll();
  scheduleBenchmarkModalSnapshotRefresh(true);
  setTimeout(() => renderBenchmarkAllModal(), 0);
}
function handleBenchmarkInventorySummaryClick(event, key) {
  const details = event?.currentTarget?.closest?.("details");
  if (details && key) benchmarkQueueOpenState[String(key)] = !details.open;
  rememberBenchmarkQueueScroll();
}
function applyBenchmarkGroupCheckboxStates(root = document) {
  const scope = root && typeof root.querySelectorAll === "function" ? root : document;
  scope.querySelectorAll("input.benchmark-group-check[data-indeterminate]").forEach((node) => {
    node.indeterminate = String(node.dataset.indeterminate || "") === "1";
  });
}
function setBenchmarkRunningPresetTab(selector) {
  benchmarkRunningPresetTab = String(selector || "");
  renderBenchmarkAllModal();
}
function setBenchmarkRunningScriptTab(selector, tabId) {
  const key = String(selector || "");
  if (!key) return;
  benchmarkRunningScriptTabs[key] = String(tabId || "");
  const row = (Array.isArray(benchmarkSnapshot().running_logs) ? benchmarkSnapshot().running_logs : [])
    .find((item) => String(item?.selector || "") === key);
  benchmarkRunningScriptTabSteps[key] = String(row?.step_id || "");
  renderBenchmarkAllModal();
}
function benchmarkRunningLogContext(snapshot = benchmarkSnapshot(), requestedSelectorOverride = undefined, options = {}) {
  const hasSelectorOverride = requestedSelectorOverride !== undefined;
  const detailedRunningLogs = Array.isArray(snapshot.running_logs) ? snapshot.running_logs : [];
  const runningLogs = detailedRunningLogs.length ? detailedRunningLogs : benchmarkQueueRunningRows(snapshot);
  const hasDetailedRunningLogs = detailedRunningLogs.length > 0;
  const requestedSelector = !hasSelectorOverride
    ? String(benchmarkRunningPresetTab || "")
    : String(requestedSelectorOverride || "");
  if (!runningLogs.length) {
    return { runningLogs: [], activePreset: null, logs: [], activeLog: null, presetTabs: "", scriptTabs: "", stepLine: "", focusedSelector: requestedSelector, focusWaiting: !!requestedSelector };
  }
  let activePreset = runningLogs.find((row) => String(row.selector || "") === requestedSelector);
  const focusPending = (
    !!requestedSelector
    && !activePreset
    && benchmarkFocusPendingSelector === requestedSelector
    && Date.now() <= Number(benchmarkFocusPendingUntil || 0)
  );
  if (!activePreset && requestedSelector && !focusPending && !hasSelectorOverride) {
    activePreset = runningLogs[0];
    benchmarkRunningPresetTab = String(activePreset.selector || "");
  }
  const focusWaiting = !!requestedSelector && !activePreset;
  if (!activePreset && !requestedSelector && !hasSelectorOverride) {
    activePreset = runningLogs[0];
    benchmarkRunningPresetTab = String(activePreset.selector || "");
  }
  const selectedSelector = String(activePreset?.selector || requestedSelector || "");
  const presetTabs = runningLogs
    .map((row) => {
      const selector = String(row.selector || "");
      const progress = Math.round(normalizeBenchmarkProgress(row.step_progress) * 100);
      const scope = row.assigned_instance_id ? ` · ${row.assigned_instance_id}` : "";
      const elapsed = benchmarkRowElapsedLabel(row);
      return `<button class="subtab ${selector === selectedSelector ? "active" : ""}" onclick="setBenchmarkRunningPresetTab('${escapeJs(selector)}')">${escapeHtml(row.display_name || selector || "Preset")} · ${progress}%${elapsed ? ` · ${escapeHtml(elapsed)}` : ""}${escapeHtml(scope)}</button>`;
    })
    .join("");
  if (focusWaiting) {
    const row = benchmarkQueueRowForSelector(requestedSelector);
    const history = Array.isArray(row?.step_history) ? row.step_history : [];
    const completedHistory = history.filter((item) => item && ["pass", "fail", "success", "failed", "complete", "completed"].includes(String(item.status || "").toLowerCase()));
    const loadingText = focusPending || !row
      ? `Loading logs for the selected preset '${requestedSelector}' in the background...`
      : completedHistory.length
        ? "Completed benchmark steps are listed in the expanded queue row; live staged logs resume when this preset is running."
        : "No completed benchmark steps recorded yet.";
    return {
      runningLogs,
      activePreset: null,
      logs: [],
      activeLog: null,
      presetTabs,
      scriptTabs: `<span class="preset-help">${escapeHtml(loadingText)}</span>`,
      stepLine: "",
      focusedSelector: requestedSelector,
      focusWaiting: true,
      loadingText,
    };
  }
  if (!hasDetailedRunningLogs) {
    const elapsed = benchmarkRowElapsedLabel(activePreset);
    const stepLine = benchmarkStepLine(activePreset, Math.round(normalizeBenchmarkProgress(activePreset.step_progress) * 100), { elapsed, instanceId: activePreset.assigned_instance_id || "" });
    const presetTabs = runningLogs
      .map((row) => {
        const selector = String(row.selector || "");
        const progress = Math.round(normalizeBenchmarkProgress(row.step_progress) * 100);
        const scope = row.assigned_instance_id ? ` · ${row.assigned_instance_id}` : "";
        const elapsedLabel = benchmarkRowElapsedLabel(row);
        return `<button class="subtab ${selector === selectedSelector ? "active" : ""}" onclick="setBenchmarkRunningPresetTab('${escapeJs(selector)}')">${escapeHtml(row.display_name || selector || "Preset")} · ${progress}%${elapsedLabel ? ` · ${escapeHtml(elapsedLabel)}` : ""}${escapeHtml(scope)}</button>`;
      })
      .join("");
    return {
      runningLogs,
      activePreset,
      logs: [],
      activeLog: null,
      presetTabs,
      scriptTabs: '<span class="preset-help">Detailed staged logs are loading from the benchmark worker.</span>',
      stepLine,
      focusedSelector: selectedSelector,
      focusWaiting: false,
      loadingText: "Detailed staged logs are loading from the benchmark worker.",
    };
  }
  const logs = Array.isArray(activePreset.logs) ? activePreset.logs : [];
  const activePresetSelector = String(activePreset.selector || "");
  const currentStepId = String(activePreset.step_id || "");
  let requestedLogTab = hasSelectorOverride
    ? String(options.activeLogTab || "")
    : String(benchmarkRunningScriptTabs[activePresetSelector] || "");
  const requestedLogStep = hasSelectorOverride ? currentStepId : String(benchmarkRunningScriptTabSteps[activePresetSelector] || "");
  if (
    !hasSelectorOverride
    && currentStepId
    && requestedLogTab
    && requestedLogTab !== currentStepId
    && requestedLogStep !== currentStepId
  ) {
    requestedLogTab = "";
  }
  let activeLog = logs.find((row) => String(row.id || "") === requestedLogTab);
  if (!activeLog && currentStepId) {
    activeLog = logs.find((row) => String(row.id || "") === currentStepId);
  }
  if (!activeLog && logs.length) {
    activeLog = [...logs].reverse().find((row) => String(row?.text || "").trim()) || logs[logs.length - 1];
  }
  if (activeLog && !hasSelectorOverride) {
    benchmarkRunningScriptTabs[activePresetSelector] = String(activeLog.id || "");
    benchmarkRunningScriptTabSteps[activePresetSelector] = currentStepId;
  }
  const scriptTabs = logs.length
    ? logs
        .map((row) => `<button class="subtab ${String(row.id || "") === String(activeLog?.id || "") ? "active" : ""}" onclick="setBenchmarkRunningScriptTab('${escapeJs(activePreset.selector || "")}','${escapeJs(row.id || "")}')">${escapeHtml(row.label || row.artifact || row.id || "Log")}</button>`)
        .join("")
    : '<span class="preset-help">Waiting for the first script log...</span>';
  const elapsed = benchmarkRowElapsedLabel(activePreset);
  const stepLine = benchmarkStepLine(activePreset, Math.round(normalizeBenchmarkProgress(activePreset.step_progress) * 100), { elapsed });
  return { runningLogs, activePreset, logs, activeLog, presetTabs, scriptTabs, stepLine, focusedSelector: selectedSelector, focusWaiting: false };
}
function renderBenchmarkRunningPresetCard(ctx = benchmarkRunningLogContext(), active = false) {
  if (!active) return "";
  const count = ctx.runningLogs.length;
  const selectedSelector = String(ctx.focusedSelector || ctx.activePreset?.selector || "");
  const body = count
    ? `<div class="benchmark-running-progress-list">${ctx.runningLogs
        .map((row) => {
          const selector = String(row.selector || "");
          const progress = Math.round(normalizeBenchmarkProgress(row.step_progress) * 100);
          const elapsed = benchmarkRowElapsedLabel(row);
          const stepLine = benchmarkStepLine(row, progress, { elapsed, instanceId: row.assigned_instance_id || "" });
          return `<button type="button" class="benchmark-running-progress-row ${selector === selectedSelector ? "focused" : ""}" onclick="setBenchmarkRunningPresetTab('${escapeJs(selector)}')"><span class="score-progress-head"><span>${escapeHtml(row.display_name || selector || "Preset")}</span><span>${escapeHtml(stepLine)}</span></span><span class="score-progress-track"><i style="width:${progress}%"></i></span></button>`;
        })
        .join("")}</div>`
    : '<div class="empty-variant-note">Waiting for the scheduler to assign the next runnable preset.</div>';
  return renderBenchmarkSection("running", "benchmark-section-card benchmark-running-section", "Running Presets", String(count), body, true);
}
function renderBenchmarkQueueCard(rowsHtml, counts = {}, active = false) {
  const ineligible = Math.max(0, Number(counts.ineligible || 0));
  const runnableTotal = Math.max(0, Number(counts.runnable_total ?? (Number(counts.total || 0) - Number(counts.skipped || 0) - ineligible)));
  const label = active
    ? `Finished: ${Number(counts.finished || 0)}/${runnableTotal}${Number(counts.skipped || 0) ? ` (${Number(counts.skipped || 0)} skipped)` : ""}${ineligible ? ` (${ineligible} ineligible)` : ""}`
    : `${Number(counts.eligible || 0)} eligible`;
  const body = `<div id="benchmarkPresetQueue" class="benchmark-queue" onscroll="rememberBenchmarkQueueScroll()">${rowsHtml || '<div class="empty-variant-note">No queue entries yet.</div>'}</div>`;
  return renderBenchmarkSection("queue", "benchmark-section-card benchmark-queue-section", "Preset Queue", escapeHtml(label), body, true);
}
function renderBenchmarkInventoryGroup(mode, kind, label, count, items = [], selected = new Set(), options = {}) {
  const keyPrefix = String(options.keyPrefix || "inventory");
  const key = `${keyPrefix}-${mode}-${kind}`;
  const open = benchmarkSectionOpen(key, false) ? "open" : "";
  const rows = Array.isArray(items) ? items : [];
  const listClassName = String(options.listClassName || "benchmark-inventory-preset-list");
  const selectors = rows.map((row) => String(row?.selector || "")).filter(Boolean);
  const locked = kind === "ineligible";
  const interactionLocked = !!options.controlsLocked;
  const className = `benchmark-queue-stat-card${locked ? " ineligible" : ""}${options.className ? ` ${options.className}` : ""}`;
  const selectedCount = selectors.filter((selector) => selected.has(selector)).length;
  const checked = !locked && selectors.length > 0 && selectedCount === selectors.length;
  const mixed = !locked && selectedCount > 0 && selectedCount < selectors.length;
  const disabled = locked || interactionLocked || !!options.bulkDisabled || !selectors.length;
  const action =
    kind === "already-scored"
      ? `setBenchmarkCompletedSelection('${escapeJs(mode)}',this.checked)`
      : kind === "experimental" || kind === "deprecated"
        ? `setBenchmarkStatusSelection('${escapeJs(mode)}','${escapeJs(kind)}',this.checked)`
        : `setBenchmarkEligibleSelection('${escapeJs(mode)}',this.checked)`;
  const checkboxTitle = locked ? `${label} presets cannot be benchmarked until their eligibility issue is fixed` : `Toggle all ${label} presets`;
  const groupCheckbox = locked
    ? ""
    : `<input class="benchmark-group-check" type="checkbox" title="${escapeHtml(checkboxTitle)}" aria-label="${escapeHtml(checkboxTitle)}" aria-checked="${mixed ? "mixed" : checked ? "true" : "false"}" data-indeterminate="${mixed ? "1" : "0"}" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""} onclick="event.stopPropagation()" onchange="${action}" />`;
  const list = rows.length
    ? rows.map((row) => {
        const selector = String(row?.selector || "");
        const checked = !locked && selected.has(selector);
        const rowKey = `inventory-${mode}-${selector}`;
        const rowOpen = benchmarkQueueOpenState[rowKey] ? "open" : "";
        const arrows = checked && !interactionLocked
          ? `<span class="benchmark-queue-arrows"><button type="button" title="Move up" aria-label="Move ${escapeHtml(row?.display_name || selector || "preset")} up" onclick="moveBenchmarkQueuePreset(event,'${escapeJs(mode)}','${escapeJs(selector)}',-1)">↑</button><button type="button" title="Move down" aria-label="Move ${escapeHtml(row?.display_name || selector || "preset")} down" onclick="moveBenchmarkQueuePreset(event,'${escapeJs(mode)}','${escapeJs(selector)}',1)">↓</button></span>`
          : "";
        const reasonText = locked ? benchmarkIneligibleReasonText(row) : String(row?.reason || row?.skip_message || "");
        const checkbox = locked
          ? `<input type="checkbox" disabled tabindex="-1" aria-disabled="true" title="${escapeHtml(checkboxTitle)}" onclick="event.preventDefault();event.stopPropagation()" />`
          : `<input type="checkbox" ${checked ? "checked" : ""} ${interactionLocked ? "disabled" : ""} onclick="event.stopPropagation()" onchange="updateBenchmarkQueueSelection('${escapeJs(mode)}','${escapeJs(selector)}',this.checked)" />`;
        return `<details class="benchmark-inventory-preset-row${checked ? " selected" : ""}${locked ? " ineligible" : ""}" ${rowOpen}><summary onclick="handleBenchmarkInventorySummaryClick(event,'${escapeJs(rowKey)}')">${checkbox}<span>${escapeHtml(row?.display_name || selector || "Preset")}</span><code>${escapeHtml(selector)}</code>${arrows}${reasonText ? `<small>${escapeHtml(reasonText)}</small>` : ""}</summary>${locked ? `<div class="preset-help">${escapeHtml(reasonText)}</div>` : renderBenchmarkStageControls(mode, selector, null, interactionLocked || !checked)}</details>`;
      }).join("")
    : '<div class="empty-variant-note">No presets in this group.</div>';
  return `<details class="${escapeHtml(className)}" ${open}><summary onclick="setBenchmarkSectionOpenFromSummary(event,'${escapeJs(key)}')">${groupCheckbox}<span>${escapeHtml(label)}</span><span>${Number(count || 0)}</span></summary><div class="${escapeHtml(listClassName)}">${list}</div></details>`;
}
function renderBenchmarkActiveQueueGroup(mode, kind, label, count, body, defaultOpen = false, options = {}) {
  const key = `active-queue-${mode}-${kind}`;
  const open = benchmarkSectionOpen(key, defaultOpen) ? "open" : "";
  const content = body || '<div class="empty-variant-note">No presets in this group.</div>';
  const checkbox = options.checkboxHtml || "";
  return `<details class="benchmark-queue-stat-card benchmark-queue-live-group ${escapeHtml(kind)}" ${open}><summary onclick="setBenchmarkSectionOpenFromSummary(event,'${escapeJs(key)}')">${checkbox}<span>${escapeHtml(label)}</span><span>${Number(count || 0)}</span></summary><div class="benchmark-active-queue-list">${content}</div></details>`;
}
function renderBenchmarkGroupedActiveQueue(mode, orderedQueueRows = [], runningRows = [], allRows = [], inventoryCounts = {}) {
  const selected = new Set(benchmarkActiveSelectedSelectors());
  const job = benchmarkJob();
  const active = benchmarkJobControlActive(job);
  const resumable = benchmarkJobResumable(job);
  const finishedReview = benchmarkJobFinishedReviewable(job);
  const controlsLocked = resumable || finishedReview;
  const completedSelectors = new Set((inventoryCounts.already_scored_presets || []).map((row) => String(row?.selector || "")).filter(Boolean));
  const ineligibleSelectors = new Set(benchmarkInventorySelectorsForGroup(inventoryCounts, "ineligible"));
  const experimentalSelectors = new Set(benchmarkInventorySelectorsByKind(inventoryCounts, "experimental"));
  const deprecatedSelectors = new Set(benchmarkInventorySelectorsByKind(inventoryCounts, "deprecated"));
  const activeRows = [];
  const finishedRows = [];
  const failedRows = [];
  const ineligibleRows = [];
  const alreadyScoredRows = [];
  const experimentalRows = [];
  const deprecatedRows = [];
  const toInventoryItem = (row) => ({ ...(row || {}), reason: String(row?.reason || row?.skip_message || row?.skip_reason || "") });
  orderedQueueRows.forEach((row, index) => {
    const status = String(row?.status || "");
    const selector = String(row?.selector || "");
    if (status === "success" || status === "completed") {
      finishedRows.push({ row, index });
      return;
    }
    if (status === "failed") {
      failedRows.push({ row, index });
      return;
    }
    if (status !== "skipped") {
      activeRows.push({ row, index });
      return;
    }
    const item = toInventoryItem(row);
    const skipReason = String(row?.skip_reason || row?.reason || "").trim().toLowerCase();
    const normalizedSkipReason = skipReason.replace(/_/g, "-");
    if (benchmarkActiveQueueHiddenSkipReason(row)) return;
    if (ineligibleSelectors.has(selector) || benchmarkIneligibleReason(row)) ineligibleRows.push(item);
    else if (completedSelectors.has(selector) || skipReason === "already-scored" || skipReason === "already scored") alreadyScoredRows.push(item);
    else if (normalizedSkipReason === "deprecated" || deprecatedSelectors.has(selector)) deprecatedRows.push(item);
    else if (normalizedSkipReason === "experimental" || experimentalSelectors.has(selector)) experimentalRows.push(item);
  });
  const activeHtml = activeRows.length
    ? activeRows.map(({ row, index }) => renderBenchmarkQueueRow(row, index, runningRows, allRows, mode, controlsLocked)).join("")
    : '<div class="empty-variant-note">No presets are currently queued to run.</div>';
  const finishedHtml = finishedRows.length
    ? finishedRows.map(({ row, index }) => renderBenchmarkQueueRow(row, index, runningRows, allRows, mode, controlsLocked)).join("")
    : '<div class="empty-variant-note">No finished presets yet.</div>';
  const failedHtml = failedRows.length
    ? failedRows.map(({ row, index }) => renderBenchmarkQueueRow(row, index, runningRows, allRows, mode, controlsLocked)).join("")
    : '<div class="empty-variant-note">No failed presets yet.</div>';
  const pendingActiveSelectors = activeRows
    .map(({ row }) => row)
    .filter((row) => row && String(row.status || "") !== "running")
    .map((row) => String(row.selector || ""))
    .filter(Boolean);
  const activeEligibleDisabled = !activeRows.length;
  const activeEligibleCheckbox = `<input class="benchmark-group-check" type="checkbox" title="Toggle all Eligible presets" aria-label="Toggle all Eligible presets" checked ${activeEligibleDisabled ? "disabled" : ""} onclick="event.stopPropagation()" onchange="setBenchmarkEligibleSelection('${escapeJs(mode)}',this.checked)" />`;
  const activeGroupOptions = (kind) => ({
    keyPrefix: "active-queue",
    className: `benchmark-queue-live-group ${kind}`,
    listClassName: "benchmark-active-queue-list",
    bulkDisabled: controlsLocked,
    controlsLocked,
  });
  return [
    renderBenchmarkActiveQueueGroup(mode, "eligible", "Running Queue", activeRows.length, activeHtml, true, { checkboxHtml: activeEligibleCheckbox }),
    renderBenchmarkActiveQueueGroup(mode, "finished", "Finished", finishedRows.length, finishedHtml, !!finishedRows.length),
    failedRows.length ? renderBenchmarkActiveQueueGroup(mode, "failed", "Failed", failedRows.length, failedHtml, true) : "",
    active ? "" : ineligibleRows.length ? renderBenchmarkInventoryGroup(mode, "ineligible", "Ineligible", ineligibleRows.length, ineligibleRows, selected, activeGroupOptions("ineligible")) : "",
    alreadyScoredRows.length ? renderBenchmarkInventoryGroup(mode, "already-scored", "Already Scored", alreadyScoredRows.length, alreadyScoredRows, selected, activeGroupOptions("already-scored")) : "",
    experimentalRows.length ? renderBenchmarkInventoryGroup(mode, "experimental", "Experimental", experimentalRows.length, experimentalRows, selected, activeGroupOptions("experimental")) : "",
    deprecatedRows.length ? renderBenchmarkInventoryGroup(mode, "deprecated", "Deprecated", deprecatedRows.length, deprecatedRows, selected, activeGroupOptions("deprecated")) : "",
  ].join("");
}
function benchmarkProgressCountLine(counts = {}, job = benchmarkJob()) {
  const ineligible = Math.max(0, Number(counts.ineligible || 0));
  const runnableTotal = Math.max(0, Number(counts.runnable_total ?? (Number(counts.total || 0) - Number(counts.skipped || 0) - ineligible)));
  if (!runnableTotal) return "";
  const finished = Math.max(0, Number(counts.finished || 0));
  const left = Math.max(0, runnableTotal - finished);
  const skipped = Math.max(0, Number(counts.skipped || 0));
  const elapsed = benchmarkJobElapsedLabel(job);
  const eta = benchmarkEtaLabel(job);
  return `${finished}/${runnableTotal} benchmarked · ${left} left${skipped ? ` · ${skipped} skipped` : ""}${ineligible ? ` · ${ineligible} ineligible` : ""}${elapsed ? ` · ${elapsed} elapsed` : ""}${eta ? ` · ETA ${eta}` : ""}`;
}
function benchmarkAverageStageSeconds(job = benchmarkJob()) {
  const durations = [];
  benchmarkQueueRows(job).forEach((row) => {
    (Array.isArray(row?.step_history) ? row.step_history : []).forEach((step) => {
      const duration = Number(step?.duration_seconds || 0);
      if (Number.isFinite(duration) && duration > 0) durations.push(duration);
    });
  });
  if (durations.length) return durations.reduce((sum, value) => sum + value, 0) / durations.length;
  return String(job?.mode || "quick") === "full" ? 1800 : 420;
}
function benchmarkEtaSeconds(job = benchmarkJob()) {
  if (!job?.active && !benchmarkJobResumable(job) && !benchmarkJobFinishedReviewable(job)) return 0;
  const avgStage = benchmarkAverageStageSeconds(job);
  let remainingStages = 0;
  benchmarkQueueRows(job).forEach((row) => {
    if (!row || row.status === "skipped" || row.status === "success" || row.status === "failed" || row.status === "completed") return;
    const stepCount = Math.max(1, Number(row.step_count || 1));
    if (row.status === "running") {
      const doneBefore = Math.max(0, Number(row.step_index || 0) - 1);
      const currentProgress = normalizeBenchmarkProgress(row.step_progress);
      remainingStages += Math.max(0, stepCount - doneBefore - currentProgress);
    } else {
      remainingStages += stepCount;
    }
  });
  if (benchmarkJobFinishedReviewable(job)) return 0;
  return Math.round(Math.max(0, remainingStages * avgStage));
}
function benchmarkEtaLabel(job = benchmarkJob()) {
  return formatElapsedSeconds(benchmarkEtaSeconds(job));
}
function benchmarkNextQueuedLabel(job = benchmarkJob()) {
  const rows = benchmarkOrderedQueueRows(job);
  const next = rows.find((row) => row && row.status === "queued");
  return next ? String(next.display_name || next.selector || "Next preset") : "";
}
function benchmarkMiniProgressCardHtml(title = "", percent = 0, elapsed = "", eta = "", stopButton = "") {
  const safePercent = Math.max(0, Math.min(100, Math.round(Number(percent || 0))));
  return `<section class="benchmark-mini-section benchmark-mini-total-card"><div class="benchmark-mini-card-title">${escapeHtml(title)}</div><div class="benchmark-mini-progress-row"><div class="benchmark-mini-progress-copy"><div class="score-progress-track"><i style="width:${safePercent}%"></i></div><div class="benchmark-mini-meta"><span>${safePercent}%</span><span>${escapeHtml(elapsed || "0s")} elapsed</span><span>ETA ${escapeHtml(eta || "calculating")}</span></div></div>${stopButton || ""}</div></section>`;
}
function benchmarkMiniRunnerCardHtml(row = {}, stopButton = "") {
  const selector = String(row.selector || "");
  const progress = Math.round(normalizeBenchmarkProgress(row.step_progress) * 100);
  const elapsed = benchmarkRowElapsedLabel(row) || "0s";
  const eta = benchmarkEtaLabel({ active: true, mode: row.mode || benchmarkJob()?.mode || "quick", queue: [row] }) || "calculating";
  const stage = benchmarkStepLine(row);
  const focused = selector && selector === String(benchmarkRunningPresetTab || "");
  return `<div class="benchmark-mini-runner ${focused ? "focused" : ""}" role="button" tabindex="0" onclick="setBenchmarkRunningPresetTab('${escapeJs(selector)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();setBenchmarkRunningPresetTab('${escapeJs(selector)}')}"><span>${escapeHtml(row.display_name || selector || "Benchmark")} <small>(${escapeHtml(stage)})</small></span><div class="benchmark-mini-progress-row"><div class="benchmark-mini-progress-copy"><div class="score-progress-track"><i style="width:${progress}%"></i></div><div class="benchmark-mini-meta"><span>${progress}%</span><span>${escapeHtml(elapsed)} elapsed</span><span>ETA ${escapeHtml(eta)}</span></div></div>${stopButton || ""}</div></div>`;
}
function benchmarkMiniTempClass(value, sensor = "core") {
  const temp = Number(value);
  if (!Number.isFinite(temp) || temp <= 0) return "";
  return typeof tempClass === "function" ? tempClass(temp, sensor) : "";
}
function benchmarkMiniTempWarn(value, sensor = "core") {
  return benchmarkMiniTempClass(value, sensor) === "temp-crimson" ? " ⚠️" : "";
}
function benchmarkMiniGpuTelemetryHtml() {
  const rows = Array.isArray(lastStatus?.gpus) ? lastStatus.gpus.filter((row) => row && !row.error) : [];
  if (!rows.length) return "";
  const fmt = (value, suffix = "") => {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? `${Math.round(number)}${suffix}` : "n/a";
  };
  const fmtPeak = (value, suffix = "") => {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? `↑${Math.round(number)}${suffix}` : "";
  };
  const fmtTemp = (value, peak = false) => {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? `${peak ? "↑" : ""}${Math.round(number)}°C` : "n/a";
  };
  const tempValueHtml = (value, sensor = "core", peak = false) => {
    const text = fmtTemp(value, peak);
    const warn = benchmarkMiniTempWarn(value, sensor);
    const className = benchmarkMiniTempClass(value, sensor);
    return `<span class="benchmark-mini-gpu-temp ${escapeHtml(className)}">${escapeHtml(text)}${escapeHtml(warn)}</span>`;
  };
  const tempPairHtml = (now, peak, sensor = "core") =>
    `${tempValueHtml(now, sensor)}/${tempValueHtml(peak || now, sensor, true)}`;
  const cards = rows.slice(0, 4).map((row, fallbackIndex) => {
    const index = row.index ?? row.gpu_index ?? fallbackIndex;
    const coreNow = row.temp_c;
    const corePeak = row.temp_peak_c || row.temp_core_peak_c || row.max_temp_c;
    const junctionNow = row.temp_junction_c || row.temp_junction;
    const junctionPeak = row.temp_junction_peak_c || row.temp_junction_peak || junctionNow;
    const vramNow = row.temp_vram_c || row.temp_vram;
    const vramPeak = row.temp_vram_peak_c || row.temp_vram_peak || vramNow;
    const powerNow = fmt(row.power_w, "W");
    const powerMax = fmtPeak(row.power_peak_w, "W") || fmt(row.power_limit_w, "W");
    const fan = fmt(row.fan_pct, "%");
    const auxTempHtml = [
      junctionNow || junctionPeak ? `<span class="benchmark-mini-gpu-aux-part"><span class="benchmark-mini-gpu-aux-label">Junction:</span> <b>${tempPairHtml(junctionNow, junctionPeak, "junction")}</b></span>` : "",
      vramNow || vramPeak ? `<span class="benchmark-mini-gpu-aux-part"><span class="benchmark-mini-gpu-aux-label">VRAM:</span> <b>${tempPairHtml(vramNow, vramPeak, "vram")}</b></span>` : "",
    ].filter(Boolean).join(" · ");
    return `<div class="benchmark-mini-gpu"><span>GPU ${escapeHtml(index)}</span><small><b>${tempPairHtml(coreNow, corePeak, "core")}</b> · ${escapeHtml(powerNow)}/${escapeHtml(powerMax)} · fan ${escapeHtml(fan)}</small>${auxTempHtml ? `<small class="benchmark-mini-gpu-aux">${auxTempHtml}</small>` : ""}</div>`;
  }).join("");
  const hidden = Math.max(0, rows.length - 4);
  return `<section class="benchmark-mini-section benchmark-mini-gpu-section"><hr class="benchmark-mini-separator" /><div class="benchmark-mini-gpus">${cards}${hidden ? `<div class="benchmark-mini-more">+${hidden} GPU${hidden === 1 ? "" : "s"}</div>` : ""}</div></section>`;
}
function benchmarkMiniCssNumber(value, fallback = 0) {
  const parsed = Number.parseFloat(String(value || ""));
  return Number.isFinite(parsed) ? parsed : fallback;
}
function benchmarkMiniComputedStyle(node) {
  if (!node || typeof window === "undefined" || typeof window.getComputedStyle !== "function") return null;
  try {
    return window.getComputedStyle(node);
  } catch (_error) {
    return null;
  }
}
function benchmarkMiniTextWidth(node) {
  if (!node || typeof document === "undefined" || typeof document.createRange !== "function") return 0;
  try {
    const range = document.createRange();
    range.selectNodeContents(node);
    const rects = Array.from(range.getClientRects ? range.getClientRects() : []);
    if (typeof range.detach === "function") range.detach();
    if (!rects.length) return 0;
    let left = Infinity;
    let right = -Infinity;
    rects.forEach((rect) => {
      left = Math.min(left, rect.left);
      right = Math.max(right, rect.right);
    });
    return Number.isFinite(left) && Number.isFinite(right) ? Math.ceil(Math.max(0, right - left)) : 0;
  } catch (_error) {
    return 0;
  }
}
function benchmarkMiniSetCssVar(node, name, value) {
  if (!node || !node.style) return;
  if (typeof node.style.setProperty === "function") node.style.setProperty(name, value);
  else node.style[name] = value;
}
function applyBenchmarkMiniLayout(mini) {
  if (!mini) return 560;
  const viewportWidth = Math.max(320, Number(window?.innerWidth || document?.documentElement?.clientWidth || 640));
  const maxOuterWidth = Math.max(300, viewportWidth - 20);
  const body = mini.querySelector?.(".benchmark-mini-body");
  const bodyStyle = benchmarkMiniComputedStyle(body);
  const miniStyle = benchmarkMiniComputedStyle(mini);
  const bodyPadX =
    benchmarkMiniCssNumber(bodyStyle?.paddingLeft, 10) + benchmarkMiniCssNumber(bodyStyle?.paddingRight, 10);
  const borderX =
    benchmarkMiniCssNumber(miniStyle?.borderLeftWidth, 1) + benchmarkMiniCssNumber(miniStyle?.borderRightWidth, 1);
  let desiredInnerWidth = 440;
  const grid = mini.querySelector?.(".benchmark-mini-gpus");
  const cards = grid ? Array.from(grid.querySelectorAll?.(".benchmark-mini-gpu") || []) : [];
  if (grid && cards.length) {
    const gridStyle = benchmarkMiniComputedStyle(grid);
    const gap = benchmarkMiniCssNumber(gridStyle?.columnGap, 8);
    const lineWidths = cards.map((card) =>
      Math.max(
        0,
        ...Array.from(card.children || []).map((child) => benchmarkMiniTextWidth(child))
      )
    );
    const columnWidth = Math.max(220, Math.ceil(Math.max(...lineWidths)) + 8);
    let columns = Math.min(cards.length, 2);
    const usableOuterWidth = Math.max(1, maxOuterWidth - bodyPadX - borderX);
    while (columns > 1 && columnWidth * columns + gap * (columns - 1) > usableOuterWidth) columns -= 1;
    const gridWidth = columnWidth * columns + gap * Math.max(0, columns - 1);
    desiredInnerWidth = Math.max(desiredInnerWidth, gridWidth);
    benchmarkMiniSetCssVar(mini, "--benchmark-mini-gpu-columns", String(columns));
    benchmarkMiniSetCssVar(mini, "--benchmark-mini-gpu-column-width", `${columnWidth}px`);
  }
  Array.from(mini.querySelectorAll?.(".benchmark-mini-meta") || []).forEach((meta) => {
    const metaStyle = benchmarkMiniComputedStyle(meta);
    const gap = benchmarkMiniCssNumber(metaStyle?.columnGap, 8);
    const children = Array.from(meta.children || []);
    const metaWidth =
      children.reduce((total, child) => total + benchmarkMiniTextWidth(child), 0) + gap * Math.max(0, children.length - 1);
    desiredInnerWidth = Math.max(desiredInnerWidth, metaWidth);
  });
  const desiredOuterWidth = Math.max(360, Math.min(maxOuterWidth, Math.ceil(desiredInnerWidth + bodyPadX + borderX)));
  benchmarkMiniSetCssVar(mini, "--benchmark-mini-width", `${desiredOuterWidth}px`);
  return desiredOuterWidth;
}
function renderBenchmarkMiniWindow() {
  hydrateBenchmarkFloatingState();
  let mini = $("benchmarkMiniWindow");
  const job = benchmarkJob();
  const active = !!job.active;
  const finishedReview = benchmarkJobFinishedReviewable(job);
  if (!benchmarkModalCollapsed || (!active && !finishedReview)) {
    if (mini) mini.remove();
    return;
  }
  if (benchmarkMiniHidden) {
    if (mini) mini.remove();
    return;
  }
  if (!mini) {
    mini = document.createElement("div");
    mini.id = "benchmarkMiniWindow";
    mini.className = "benchmark-mini-window";
    document.body.appendChild(mini);
  }
  const orderedRows = benchmarkOrderedQueueRows(job);
  const runningRows = orderedRows.filter((row) => row?.status === "running");
  const liveRows = orderedRows.filter((row) => row && !["skipped", "success", "failed", "completed"].includes(String(row.status || "").toLowerCase()));
  const overall = Math.round(normalizeBenchmarkProgress(job.overall_progress) * 100);
  const runButton = finishedReview
    ? renderIconButton({ title: "Reset Finished Benchmark Review", action: "event.stopPropagation();resetBenchmarkFinishedReview()", icon: "check", className: "benchmark-run-toggle benchmark-start-toggle benchmark-finished-toggle" })
    : benchmarkStopButtonHtml("Stop Benchmark", "event.stopPropagation();");
  const showTotal = finishedReview || liveRows.length !== 1;
  const runningList = runningRows.length
    ? runningRows.map((row, index) => `${index ? '<hr class="benchmark-mini-separator" />' : ""}${benchmarkMiniRunnerCardHtml(row, !showTotal && index === 0 ? runButton : "")}`).join("")
    : finishedReview
      ? `<div class="benchmark-mini-empty benchmark-mini-finished">Finished <small>${escapeHtml(benchmarkProgressCountLine(benchmarkQueueCounts(job), job) || job.summary || "Benchmark job completed.")}</small></div>`
      : '<div class="benchmark-mini-empty">Preparing next preset <small>(Waiting for scheduler)</small></div>';
  const elapsed = benchmarkJobElapsedLabel(job) || "0s";
  const eta = finishedReview ? "complete" : benchmarkEtaLabel(job) || "calculating";
  const next = finishedReview ? "" : benchmarkNextQueuedLabel(job);
  const closeButton = renderIconButton({ title: "Hide", action: "closeBenchmarkMiniWindow()", icon: "close", className: "benchmark-mini-close" });
  const expandButton = renderIconButton({ title: "Expand", action: "restoreBenchmarkAllModalFromMini()", icon: "detach", className: "benchmark-mini-expand" });
  mini.innerHTML = `<div class="benchmark-mini-head benchmark-modal-drag-handle" onpointerdown="startBenchmarkModalDrag(event,'mini')"><strong>Benchmarks</strong><span class="benchmark-mini-head-actions">${closeButton}${expandButton}</span></div><div class="benchmark-mini-body">${showTotal ? benchmarkMiniProgressCardHtml(finishedReview ? "Finished" : "Total Progress", finishedReview ? 100 : overall, elapsed, eta, runButton) : ""}<section class="benchmark-mini-section">${showTotal ? '<hr class="benchmark-mini-separator" />' : ""}<div class="benchmark-mini-runner-list">${runningList}</div></section>${benchmarkMiniGpuTelemetryHtml()}${next ? `<div class="benchmark-mini-next-line"><span class="benchmark-mini-card-title">Up next</span><b class="benchmark-mini-next">${escapeHtml(next)}</b></div>` : ""}</div>`;
  const miniWidth = applyBenchmarkMiniLayout(mini);
  const measuredMiniWidth = mini.offsetWidth || miniWidth || 560;
  const pos = clampBenchmarkFloatingPosition(benchmarkMiniPosition || { left: (window.innerWidth || 640) - measuredMiniWidth - 20, top: 70 }, measuredMiniWidth, mini.offsetHeight || 210);
  benchmarkMiniPosition = pos;
  mini.style.left = `${pos.left}px`;
  mini.style.top = `${pos.top}px`;
}
function renderBenchmarkModalLogCard(ctx = benchmarkRunningLogContext(), currentLog = {}, logTail = "", active = false) {
  const focusWaiting = !!active && !!ctx.focusWaiting;
  const cooldownStage = !!ctx.activePreset && String(ctx.activePreset.step_label || "").trim().toLowerCase() === "pausing to cool gpus";
  const hasStagedLogs = Array.isArray(ctx.logs) && ctx.logs.some((row) => row && String(row.text || "").trim());
  const hasStaged = !!active && (focusWaiting || (!!ctx.activePreset && (!cooldownStage || hasStagedLogs)));
  const effectiveMode = benchmarkModalLogMode === "full" || (!hasStaged && !focusWaiting) ? "full" : "staged";
  const fullLabel = currentLog.label ? `${currentLog.label}${currentLog.progress ? ` · ${Math.round(normalizeBenchmarkProgress(currentLog.progress) * 100)}%` : ""}` : "Full benchmark output";
  const stagedLabel = focusWaiting
    ? `Focused: ${ctx.focusedSelector || "preset"}`
    : ctx.activePreset ? `${ctx.activePreset.display_name || ctx.activePreset.selector || "Preset"} · ${ctx.stepLine || "current step"}` : "No running preset";
  const activeLabel = effectiveMode === "staged" ? stagedLabel : fullLabel;
  const text = effectiveMode === "staged"
    ? String(focusWaiting ? ctx.loadingText || `Loading logs for the selected preset '${ctx.focusedSelector || "preset"}' in the background...` : formatBenchmarkArtifactLogText(ctx.activeLog, ctx.activeLog?.text || "No staged output captured for this script yet."))
    : String(logTail || "No benchmark log entries yet.");
  const logPath = effectiveMode === "staged"
    ? benchmarkLogDisplayPath(ctx.activeLog || {}, { selector: ctx.activePreset?.selector || ctx.focusedSelector || "", run_dir: ctx.activePreset?.run_dir || "" })
    : "";
  const scriptTabs = effectiveMode === "staged" && hasStaged ? `<div class="subtabs score-log-tabs score-log-tabs-bottom">${ctx.scriptTabs}</div>` : "";
  const heightStyle = benchmarkModalLogHeight ? ` style="height:${Math.round(benchmarkModalLogHeight)}px"` : "";
  const body = `<div class="benchmark-log-mode-row"><div class="subtabs"><button class="subtab ${effectiveMode === "staged" ? "active" : ""}" ${hasStaged ? "" : "disabled"} onclick="setBenchmarkModalLogMode('staged')">Staged</button><button class="subtab ${effectiveMode === "full" ? "active" : ""}" onclick="setBenchmarkModalLogMode('full')">Full</button></div>${renderActiveLogPathLabel(logPath)}<span class="preset-help">${escapeHtml(active ? "Live benchmark output" : "Last benchmark output")}</span></div><pre id="benchmarkModalLogTail" class="benchmark-log-tail ${effectiveMode === "full" ? "full" : "staged"}" data-log-mode="${escapeHtml(effectiveMode)}" tabindex="0"${heightStyle} onscroll="rememberBenchmarkModalLogScroll()" onmouseup="rememberBenchmarkModalLogHeight()" onpointerup="rememberBenchmarkModalLogHeight()" onblur="rememberBenchmarkModalLogHeight()">${escapeHtml(text)}</pre>${scriptTabs}`;
  return renderBenchmarkSection("logs", "benchmark-section-card benchmark-log-section", "Benchmark Logs", escapeHtml(activeLabel), body, true);
}
function benchmarkStepShortLabel(row = {}) {
  const raw = String(row.step_id || row.step_label || "step").toLowerCase();
  if (raw.includes("verify stress")) return "verify stress";
  if (raw.includes("quality")) return "quality";
  if (raw.includes("verify")) return "verify";
  if (raw.includes("bench")) return "bench";
  if (raw.includes("launch")) return "launch";
  if (raw.includes("metadata")) return "metadata";
  if (raw.includes("compliance")) return "compliance";
  if (raw.includes("soak")) return "soak";
  return raw.replace(/[^a-z0-9]+/g, " ").trim() || "step";
}
function benchmarkStepLabelHasSubstageCounter(label = "") {
  return /\(\s*\d+\s*\/\s*\d+\s*\)\s*:/.test(String(label || ""));
}
function benchmarkStepLine(row = {}, progress = null, options = {}) {
  const label = String(row.step_label || row.step_id || "Benchmark step").trim();
  const parts = [label];
  if (!benchmarkStepLabelHasSubstageCounter(label) && row.step_count) {
    parts.push(`${Number(row.step_index || 0)}/${Number(row.step_count || 0)}`);
  }
  const pct = progress === null || progress === undefined ? null : Number(progress);
  if (Number.isFinite(pct)) parts.push(`${Math.round(pct)}%`);
  const elapsed = options.elapsed || "";
  if (elapsed) parts.push(`${elapsed}`);
  const instanceId = options.instanceId || "";
  if (instanceId) parts.push(`${instanceId}`);
  return parts.join(" · ");
}
function benchmarkStageCounts(rows = []) {
  const runnableRows = (Array.isArray(rows) ? rows : []).filter((row) => row && row.status !== "skipped");
  const total = runnableRows.length;
  const stages = new Map();
  const ensureStage = (id, label) => {
    const key = String(id || label || "stage").trim() || "stage";
    if (!stages.has(key)) {
      stages.set(key, { id: key, label: String(label || id || "Stage"), pass: 0, fail: 0, running: 0 });
    }
    return stages.get(key);
  };
  runnableRows.forEach((row) => {
    (Array.isArray(row.step_history) ? row.step_history : []).forEach((step) => {
      const stage = ensureStage(step.id, step.label);
      if (String(step.status || "").toLowerCase() === "pass") stage.pass += 1;
      else if (String(step.status || "").toLowerCase() === "fail") stage.fail += 1;
    });
    if (String(row.status || "") === "running" && (row.step_id || row.step_label)) {
      ensureStage(row.step_id, row.step_label).running += 1;
    }
  });
  return { total, stages };
}
function benchmarkStepStageKey(step = {}) {
  return String(step.id || step.step_id || step.label || step.step_label || "stage").trim() || "stage";
}
function benchmarkStepStatsHtml(stage = {}, total = 0, extra = "") {
  const denominator = Math.max(1, Number(total || 0));
  const runText = Number(stage.running || 0) > 0 ? ` · RUN ${Number(stage.running || 0)}` : "";
  return `<span>PASS ${Number(stage.pass || 0)}/${denominator}</span><span class="benchmark-step-history-separator">•</span><span>FAIL ${Number(stage.fail || 0)}/${denominator}${runText}</span>${extra ? `<span class="benchmark-step-history-error">${escapeHtml(extra)}</span>` : ""}`;
}
function renderBenchmarkStepHistory(row = {}, allRows = []) {
  if (String(row?.status || "").toLowerCase() === "skipped") {
    return '<div class="preset-help">Skipped presets do not run benchmark stages.</div>';
  }
  const { total, stages } = benchmarkStageCounts(allRows);
  const history = Array.isArray(row.step_history) ? row.step_history : [];
  const rows = history.map((step) => {
    const passed = String(step.status || "").toLowerCase() === "pass";
    const mark = passed ? "PASS" : "FAIL";
    const reason = passed
      ? ""
      : `${formatBenchmarkReturnCode(step.return_code ?? "")}${step.error ? ` · ${step.error}` : ""}`;
    const stage = stages.get(benchmarkStepStageKey(step)) || { pass: passed ? 1 : 0, fail: passed ? 0 : 1, running: 0 };
    return `<div class="benchmark-step-history-row ${passed ? "pass" : "fail"}"><span>${mark}</span><span>${escapeHtml(step.label || step.id || "Step")}</span><span class="benchmark-step-history-stats">${benchmarkStepStatsHtml(stage, total, reason)}</span></div>`;
  });
  if (String(row?.status || "") === "running" && (row.step_id || row.step_label)) {
    const currentStep = { id: row.step_id, label: row.step_label };
    const alreadyListed = history.some((step) => benchmarkStepStageKey(step) === benchmarkStepStageKey(currentStep));
    if (!alreadyListed) {
      const stage = stages.get(benchmarkStepStageKey(currentStep)) || { pass: 0, fail: 0, running: 1 };
      rows.push(`<div class="benchmark-step-history-row run"><span>RUN</span><span>${escapeHtml(row.step_label || row.step_id || "Current step")}</span><span class="benchmark-step-history-stats">${benchmarkStepStatsHtml(stage, total)}</span></div>`);
    }
  }
  if (!rows.length) {
    return `<div class="preset-help">${row.status === "running" ? "Current step is running; completed step results will appear here." : "No completed benchmark steps recorded yet."}</div>`;
  }
  return `<div class="benchmark-step-history">${rows.join("")}</div>`;
}
function renderBenchmarkQueueRow(row, index, runningRows = [], allRows = [], mode = "quick", controlsLocked = false) {
  const effectiveControlsLocked = controlsLocked;
  const status = String(row?.status || "queued");
  const key = benchmarkQueueRowKey(row || {}, index);
  const open = benchmarkQueueOpenState[key] ? "open" : "";
  const focused = String(row?.selector || "") && String(row?.selector || "") === String(benchmarkRunningPresetTab || "");
  const allGpuThermalWait = !!row?.thermal_retry_wait_all_idle;
  const runningIndex = runningRows.findIndex((item) => item === row);
  const stepLabel = String(row?.step_label || row?.step_id || "").trim();
  const step = row?.step_count && !benchmarkStepLabelHasSubstageCounter(stepLabel) ? `${Number(row.step_index || 0)}/${Number(row.step_count || 0)}` : "";
  const elapsed = status === "running" ? benchmarkRowElapsedLabel(row) : "";
  const statusText = status === "running"
    ? `running ${runningIndex + 1}/${Math.max(1, runningRows.length)} · ${stepLabel && benchmarkStepLabelHasSubstageCounter(stepLabel) ? stepLabel : `${benchmarkStepShortLabel(row)}: ${step || "0/0"}`}${elapsed ? ` · ${elapsed}` : ""}`
    : `${status}${step ? ` · ${step}` : ""}${row?.skip_reason ? ` · ${row.skip_reason}` : ""}`;
  const progress = status === "running" ? `<div class="score-progress-track"><i style="width:${Math.round(normalizeBenchmarkProgress(row.step_progress) * 100)}%"></i></div>` : "";
  const selectionLocked = effectiveControlsLocked || ["success", "completed"].includes(status);
  const selectable = !selectionLocked;
  const stageControlsLocked = selectionLocked || status === "failed";
  const checked = !["skipped", "failed"].includes(status);
  const arrows = selectable && checked && !benchmarkJobControlActive()
    ? `<span class="benchmark-queue-arrows"><button type="button" title="Move up" aria-label="Move preset up" onclick="moveBenchmarkQueuePreset(event,'${escapeJs(mode)}','${escapeJs(row?.selector || "")}',-1)">↑</button><button type="button" title="Move down" aria-label="Move preset down" onclick="moveBenchmarkQueuePreset(event,'${escapeJs(mode)}','${escapeJs(row?.selector || "")}',1)">↓</button></span>`
    : "";
  const selectedStages = encodeURIComponent(JSON.stringify(Array.isArray(row?.selected_step_ids) ? row.selected_step_ids : []));
  const checkboxAction = status === "failed"
    ? `handleBenchmarkFailedQueueCheck('${escapeJs(mode)}','${escapeJs(row?.selector || "")}',this,'${escapeJs(selectedStages)}')`
    : `updateBenchmarkQueueSelection('${escapeJs(mode)}','${escapeJs(row?.selector || "")}',this.checked)`;
  return `<details class="benchmark-queue-row ${escapeHtml(status)}${focused ? " focused" : ""}${allGpuThermalWait ? " thermal-wait-all-gpus" : ""}" data-benchmark-queue-row="${escapeHtml(key)}" ${open}><summary onclick="handleBenchmarkQueueSummaryClick(event,'${escapeJs(row?.selector || "")}','${escapeJs(key)}')"><span class="benchmark-queue-title"><input type="checkbox" ${checked ? "checked" : ""} ${selectable ? "" : "disabled"} onclick="event.stopPropagation()" onchange="${checkboxAction}" />${arrows}<span>${index + 1}. ${escapeHtml(row?.display_name || row?.selector || "Preset")}</span></span><span>${escapeHtml(statusText)}</span></summary>${progress}${renderBenchmarkStageControls(mode, row?.selector || "", row, stageControlsLocked)}${renderBenchmarkStepHistory(row || {}, allRows)}</details>`;
}
function renderBenchmarkFailedRow(row = {}, mode = "full", active = false) {
  const selector = String(row.selector || "");
  const retryMode = String(row.mode || mode || "full");
  const tips = (row.recommendations || []).map((tip) => `<li>${escapeHtml(tip)}</li>`).join("");
  const locked = active || benchmarkModalControlsLocked || benchmarkModalAwaitingFreshSnapshot || benchmarkJobControlActive() || benchmarkJobFinishedReviewable();
  return `<details class="benchmark-failed-card" open><summary><span>❌ ${escapeHtml(row.display_name || selector || "Preset")}</span><span>${escapeHtml(formatModelScoreValue(row.score))}</span></summary><div class="preset-help">${escapeHtml(row.step || "Failed benchmark gate")}</div><div class="preset-help">${escapeHtml(row.error || "No failure text captured.")}</div><ul class="benchmark-recommendations">${tips}</ul><div class="benchmark-actions"><button class="btn green" ${locked ? "disabled" : ""} onclick="retryFailedBenchmarkPreset('${escapeJs(selector)}','${escapeJs(retryMode)}')">Retry</button></div></details>`;
}
function benchmarkModalDomHasActiveText() {
  const body = $("benchmarkAllBody");
  if (!body) return false;
  const text = String(body.innerText || body.textContent || "").trim().toLowerCase();
  return /model scores (running|waiting)|benchmark (running|queued)|running:|pausing to cool/.test(text);
}
function benchmarkModalHtmlHasActiveText(html = "") {
  const text = String(html || "").replace(/<[^>]+>/g, " ").trim().toLowerCase();
  return /model scores (running|waiting)|benchmark (running|queued)|running:|pausing to cool/.test(text);
}
function benchmarkLockActiveControlMarkup(html = "") {
  return String(html || "")
    .replace(/<details class=\"benchmark-queue-row (?:success|completed)[\s\S]*?<\/details>/g, (block) =>
      block.replace(/<input\b(?![^>]*\sdisabled(?:\s|=|>|\/))([^>]*)>/g, "<input disabled$1>"))
    .replace(/(<div class=\"benchmark-mode-row\">)([\s\S]*?)(<\/div>)/, (_match, open, inner, close) =>
      `${open}${inner
        .replace(/<button\b(?![^>]*\sdisabled(?:\s|=|>|\/))([^>]*)>/g, "<button disabled$1>")
        .replace(/<input\b(?![^>]*\sdisabled(?:\s|=|>|\/))([^>]*)>/g, "<input disabled$1>")}${close}`)
    .replace(/<button\b(?![^>]*\sdisabled(?:\s|=|>|\/))([^>]*\bclass=\"[^\"]*\bbenchmark-queue-arrows\b[^\"]*\"[^>]*)>/g, "<button disabled$1>")
    .replace(/<button\b(?![^>]*\sdisabled(?:\s|=|>|\/))([^>]*)>(Retry)<\/button>/g, "<button disabled$1>$2</button>");
}
function applyBenchmarkModalActiveControlLock(locked = false) {
  const lockNodes = () => {
    const body = $("benchmarkAllBody");
    if (!body) return;
    body.querySelectorAll([
      ".benchmark-mode-row > button.subtab",
      "#benchmarkThermalCooldown",
      ".benchmark-failed-card button",
      ".benchmark-queue-arrows button",
      ".benchmark-queue-row.success input[type='checkbox']",
      ".benchmark-queue-row.completed input[type='checkbox']",
      ".benchmark-queue-row.failed .benchmark-stage-selector input[type='checkbox']",
    ].join(","))
    .forEach((node) => {
      if (node.disabled && node.getAttribute("aria-disabled") === "true") return;
      node.disabled = true;
      node.setAttribute("aria-disabled", "true");
    });
  };
  const disconnectObserver = () => {
    if (benchmarkModalControlLockObserver) {
      benchmarkModalControlLockObserver.disconnect();
      benchmarkModalControlLockObserver = null;
    }
  };
  if (!locked && (benchmarkModalAwaitingFreshSnapshot || benchmarkModalDomHasActiveText())) {
    locked = true;
    benchmarkModalControlsLocked = true;
  }
  if (!locked) {
    if (benchmarkModalControlLockInterval) {
      clearInterval(benchmarkModalControlLockInterval);
      benchmarkModalControlLockInterval = null;
    }
    disconnectObserver();
    return;
  }
  lockNodes();
  const body = $("benchmarkAllBody");
  if (body && !benchmarkModalControlLockObserver && typeof MutationObserver === "function") {
    benchmarkModalControlLockObserver = new MutationObserver(() => {
      const job = benchmarkJob();
      const snapshot = benchmarkSnapshot();
      const stillLocked = benchmarkModalControlsLocked || benchmarkModalAwaitingFreshSnapshot || benchmarkJobControlActive(job, snapshot) || benchmarkModalDomHasActiveText();
      if (!stillLocked || benchmarkJobTerminal(job)) {
        disconnectObserver();
        return;
      }
      lockNodes();
    });
    benchmarkModalControlLockObserver.observe(body, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"] });
  }
  if (!benchmarkModalControlLockInterval) {
    benchmarkModalControlLockInterval = setInterval(() => {
      const job = benchmarkJob();
      const snapshot = benchmarkSnapshot();
      const stillLocked = benchmarkModalControlsLocked || benchmarkJobControlActive(job, snapshot);
      if (!stillLocked || benchmarkJobTerminal(job)) {
        clearInterval(benchmarkModalControlLockInterval);
        benchmarkModalControlLockInterval = null;
        disconnectObserver();
        return;
      }
      lockNodes();
    }, 5);
  }
}
function renderBenchmarkAllModal() {
  ensureBenchmarkAllModal();
  const body = $("benchmarkAllBody");
  if (!body) return;
  const modal = $("benchmarkAllModal");
  if (modal && !modal.classList.contains("hidden")) {
    benchmarkModalCollapsed = false;
    benchmarkModalOpenPersisted = true;
    renderBenchmarkMiniWindow();
  }
  rememberBenchmarkQueueScroll();
  rememberBenchmarkModalLogScroll();
  rememberBenchmarkModalLogHeight();
  const snapshot = benchmarkSnapshot();
  const job = benchmarkJob();
  const queueRows = benchmarkQueueRows(job);
  const active = benchmarkJobControlActive(job, snapshot);
  const rawResumable = benchmarkJobResumable(job);
  const rawFinishedReview = benchmarkJobFinishedReviewable(job);
  const snapshotHasDetailedBenchmarkEvidence = Array.isArray(snapshot.running_logs) && snapshot.running_logs.length > 0;
  const jobQueueRows = benchmarkQueueRows(job);
  const queueNeedsFreshStageEvidence = !active
    && !rawFinishedReview
    && !snapshotHasDetailedBenchmarkEvidence
    && !benchmarkQueueRowsAllTerminal(jobQueueRows)
    && benchmarkJobNeedsFreshStageEvidence(job);
  const idleNeedsFullInventory = !active && !rawResumable && !rawFinishedReview && !benchmarkSnapshotHasFullInventory(snapshot);
  const refreshingIdleInventory = (benchmarkModalAwaitingFreshSnapshot || queueNeedsFreshStageEvidence || idleNeedsFullInventory) && !active && ((!rawResumable && !rawFinishedReview) || queueNeedsFreshStageEvidence);
  const resumable = refreshingIdleInventory ? false : rawResumable;
  const finishedReview = refreshingIdleInventory ? false : rawFinishedReview;
  const sessionReview = active || resumable || finishedReview;
  const controlsLocked = benchmarkModalAwaitingFreshSnapshot || refreshingIdleInventory || active || syncBenchmarkModalControlLock(job, snapshot);
  const mode = sessionReview ? String(job.mode || "quick") : benchmarkAllModalMode;
  const countsByMode = snapshot.counts_by_mode || {};
  const inventoryCounts = countsByMode[mode] || snapshot.counts || {};
  const idleSelected = sessionReview ? new Set() : ensureBenchmarkQueueSelection(mode, inventoryCounts);
  const inventoryRows = benchmarkInventoryRows(inventoryCounts);
  const inventoryOrder = benchmarkQueueOrderByMode[mode] || [];
  const inventoryRank = new Map(inventoryOrder.map((selector, index) => [selector, index]));
  const originalCompleted = new Set(benchmarkInventorySelectorsForGroup(inventoryCounts, "already-scored"));
  const originalEligible = new Set(benchmarkInventorySelectorsForGroup(inventoryCounts, "eligible"));
  const originalIneligible = new Set(benchmarkInventorySelectorsForGroup(inventoryCounts, "ineligible"));
  const originalExperimental = new Set(benchmarkInventorySelectorsForGroup(inventoryCounts, "experimental"));
  const originalDeprecated = new Set(benchmarkInventorySelectorsForGroup(inventoryCounts, "deprecated"));
  const orderedInventoryRows = [...inventoryRows].sort((left, right) => {
    const leftSelector = String(left?.selector || "");
    const rightSelector = String(right?.selector || "");
    return (inventoryRank.get(leftSelector) ?? inventoryRows.indexOf(left)) - (inventoryRank.get(rightSelector) ?? inventoryRows.indexOf(right));
  });
  const idleDeprecatedRows = orderedInventoryRows.filter((row) => {
    const selector = String(row?.selector || "");
    return originalDeprecated.has(selector) && !originalEligible.has(selector) && !originalCompleted.has(selector) && !originalIneligible.has(selector);
  });
  const idleExperimentalRows = orderedInventoryRows.filter((row) => {
    const selector = String(row?.selector || "");
    return originalExperimental.has(selector) && !originalEligible.has(selector) && !originalCompleted.has(selector) && !originalIneligible.has(selector);
  });
  const idleCompletedRows = orderedInventoryRows.filter((row) => {
    const selector = String(row?.selector || "");
    return originalCompleted.has(selector) && !originalIneligible.has(selector);
  });
  const idleIneligibleRows = orderedInventoryRows.filter((row) => {
    const selector = String(row?.selector || "");
    return originalIneligible.has(selector) || benchmarkIneligibleReason(row);
  });
  const idleEligibleRows = orderedInventoryRows.filter((row) => {
    const selector = String(row?.selector || "");
    return originalEligible.has(selector) && !originalIneligible.has(selector) && !originalCompleted.has(selector);
  });
  const counts = refreshingIdleInventory
    ? {
        ...inventoryCounts,
        eligible: 0,
        already_scored: 0,
        ineligible: 0,
        experimental: 0,
        deprecated: 0,
        skipped: 0,
        eligible_presets: [],
        already_scored_presets: [],
        ineligible_presets: [],
        experimental_presets: [],
        deprecated_presets: [],
      }
    : sessionReview
    ? benchmarkQueueCounts(job)
    : {
        ...inventoryCounts,
        eligible: idleEligibleRows.length,
        already_scored: idleCompletedRows.length,
        ineligible: idleIneligibleRows.length,
        experimental: idleExperimentalRows.length,
        deprecated: idleDeprecatedRows.length,
        skipped: idleExperimentalRows.length + idleDeprecatedRows.length,
        eligible_presets: idleEligibleRows,
        already_scored_presets: idleCompletedRows,
        ineligible_presets: idleIneligibleRows,
        experimental_presets: idleExperimentalRows,
        deprecated_presets: idleDeprecatedRows,
      };
  const overall = Math.round(normalizeBenchmarkProgress(job.overall_progress) * 100);
  const orderedQueueRows = sessionReview ? benchmarkOrderedQueueRows(job) : [...queueRows];
  const current = orderedQueueRows.find((row) => row?.status === "running") || null;
  const currentLine = refreshingIdleInventory
    ? "Refreshing benchmark inventory..."
    : current
    ? `${current.display_name || current.selector}: ${current.step_label || "running"} (${Math.round(normalizeBenchmarkProgress(current.step_progress) * 100)}%)${benchmarkRowElapsedLabel(current) ? ` · ${benchmarkRowElapsedLabel(current)}` : ""}`
    : active
      ? "Preparing next preset..."
      : resumable
        ? `${Number(counts.queued || 0)} queued preset${Number(counts.queued || 0) === 1 ? "" : "s"} can be resumed.`
        : finishedReview
          ? job.summary || "Benchmark job completed."
          : `${Number(counts.eligible || 0)} eligible preset${Number(counts.eligible || 0) === 1 ? "" : "s"} ready.`;
  const runningRows = orderedQueueRows.filter((row) => row?.status === "running");
  const rows = refreshingIdleInventory
    ? '<div class="empty-variant-note">Refreshing benchmark inventory from the server...</div>'
    : sessionReview
    ? renderBenchmarkGroupedActiveQueue(mode, orderedQueueRows, runningRows, queueRows, inventoryCounts)
    : [
        renderBenchmarkInventoryGroup(mode, "eligible", "Eligible", counts.eligible, idleEligibleRows, idleSelected, { controlsLocked }),
        renderBenchmarkInventoryGroup(mode, "already-scored", "Already Scored", counts.already_scored, idleCompletedRows, idleSelected, { controlsLocked }),
        renderBenchmarkInventoryGroup(mode, "ineligible", "Ineligible", counts.ineligible, idleIneligibleRows, idleSelected, { controlsLocked }),
        renderBenchmarkInventoryGroup(mode, "experimental", "Experimental", counts.experimental, idleExperimentalRows, idleSelected, { controlsLocked }),
        renderBenchmarkInventoryGroup(mode, "deprecated", "Deprecated", counts.deprecated, idleDeprecatedRows, idleSelected, { controlsLocked }),
      ].join("");
  const currentLog = snapshot.current_log || {};
  const cumulativeRows = Array.isArray(snapshot.log_tail)
    ? snapshot.log_tail
    : Array.isArray(job.log_tail)
      ? job.log_tail
      : [];
  const cumulativeLog = cumulativeRows.slice(-80).join("\n");
  const logTail = String(cumulativeLog || currentLog.text || "");
  const failedRows = Array.isArray(snapshot.failed) ? snapshot.failed : [];
  const failedHtml = failedRows.length
    ? failedRows
        .slice(0, 40)
        .map((row) => renderBenchmarkFailedRow(row, mode, controlsLocked))
        .join("")
    : '<div class="empty-variant-note">No failed presets in the current benchmark queue.</div>';
  const logLabel = currentLog.label ? `${currentLog.label}${currentLog.progress ? ` · ${Math.round(normalizeBenchmarkProgress(currentLog.progress) * 100)}%` : ""}` : "Benchmark script output";
  const runningLogCtx = benchmarkRunningLogContext(snapshot);
  const logCard = renderBenchmarkModalLogCard(runningLogCtx, currentLog, logTail, active);
  const runningCard = renderBenchmarkRunningPresetCard(runningLogCtx, active);
  const queueCard = renderBenchmarkQueueCard(rows, counts, sessionReview);
  const failedCard = renderBenchmarkSection("failed", "benchmark-failed-section", "Failed Presets", String(failedRows.length), `<div class="benchmark-failed-grid">${failedHtml}</div>`, !!failedRows.length);
  const thermalCooldown = sessionReview ? job.thermal_cooldown !== false : true;
  const startTitle = finishedReview
    ? "Reset Finished Benchmark Review"
    : `${resumable ? "Resume" : "Start"} ${mode === "full" ? "Full" : "Quick"} Benchmark`;
  const runButton = active
    ? benchmarkStopButtonHtml("Cancel Benchmark")
    : finishedReview
      ? renderIconButton({ title: startTitle, action: "resetBenchmarkFinishedReview()", icon: "check", className: "benchmark-run-toggle benchmark-start-toggle benchmark-finished-toggle" })
      : renderIconButton({ title: startTitle, action: `startBenchmarkAll('${escapeJs(mode)}')`, icon: "play", className: "benchmark-run-toggle benchmark-start-toggle", disabled: controlsLocked && !resumable });
  const progressCountLine = sessionReview ? benchmarkProgressCountLine(counts, job) : "";
  const benchmarkProgressInfo = sessionReview
    ? `<div class="benchmark-progress-line"><div class="benchmark-progress-copy"><span class="benchmark-progress-current">${escapeHtml(currentLine)}</span><span class="benchmark-progress-log"><strong>Log:</strong> ${escapeHtml(logLabel)}</span></div>${progressCountLine ? `<span class="benchmark-progress-count-inline">${escapeHtml(progressCountLine)}</span>` : ""}</div>`
    : `<div class="preset-help">${escapeHtml(currentLine)}</div>`;
  const disabledControls = controlsLocked || benchmarkModalControlsLocked || benchmarkModalAwaitingFreshSnapshot || sessionReview ? "disabled" : "";
  const headline = active
    ? job.summary || "Benchmark running"
    : resumable
      ? job.summary || "Benchmark queued for resume"
      : finishedReview
        ? job.summary || "Benchmark job completed."
        : refreshingIdleInventory
          ? "Refreshing"
        : "Ready";
  let nextHtml = `<div class="benchmark-mode-row"><button class="subtab ${mode === "quick" ? "active" : ""}" ${disabledControls} onclick="setBenchmarkAllMode('quick')">Quick</button><button class="subtab ${mode === "full" ? "active" : ""}" ${disabledControls} onclick="setBenchmarkAllMode('full')">Full</button><label class="benchmark-include-completed"><input id="benchmarkThermalCooldown" type="checkbox" ${thermalCooldown ? "checked" : ""} ${disabledControls} /> Pause between tests to cool GPUs</label></div><div class="score-progress-block benchmark-overall-progress"><div class="benchmark-ready-row"><div class="benchmark-ready-main"><div class="score-progress-head"><span>${escapeHtml(headline)}</span><span>${sessionReview ? `${overall}%` : ""}</span></div><div class="score-progress-track"><i style="width:${sessionReview ? overall : 0}%"></i></div>${benchmarkProgressInfo}</div><span class="benchmark-ready-controls">${runButton}</span></div></div>${runningCard}${queueCard}${logCard}${failedCard}`;
  if (controlsLocked || benchmarkModalControlsLocked || benchmarkModalAwaitingFreshSnapshot || benchmarkModalHtmlHasActiveText(nextHtml)) {
    nextHtml = benchmarkLockActiveControlMarkup(nextHtml);
  }
  const structuralSignature = benchmarkModalStructuralSignature(snapshot, job, mode, counts, orderedQueueRows, failedRows);
  const now = Date.now();
  const htmlChanged = body.dataset.benchmarkRenderHtml !== nextHtml;
  const structuralChanged = body.dataset.benchmarkStructuralSignature !== structuralSignature;
  const renderIntervalMs = active ? 5000 : 1000;
  const fullRenderDue = !active || structuralChanged || !body.dataset.benchmarkRenderHtml || now - benchmarkModalLastFullRenderAt >= renderIntervalMs;
  if (htmlChanged && fullRenderDue) {
    body.innerHTML = nextHtml;
    body.dataset.benchmarkRenderHtml = nextHtml;
    body.dataset.benchmarkStructuralSignature = structuralSignature;
    benchmarkModalLastStructuralSignature = structuralSignature;
    benchmarkModalLastFullRenderAt = now;
  } else if (active) {
    patchBenchmarkModalLiveText(body, { overall, currentLine, logLabel, progressCountLine, logTail });
    benchmarkModalLastStructuralSignature = structuralSignature;
  }
  applyBenchmarkGroupCheckboxStates(body);
  applyBenchmarkModalActiveControlLock(controlsLocked);
  const restoreBenchmarkUiState = () => {
    applyBenchmarkModalPosition();
    restoreBenchmarkQueueScroll();
    restoreBenchmarkModalLogHeight();
    restoreBenchmarkModalLogScroll();
    renderBenchmarkMiniWindow();
  };
  if (typeof requestAnimationFrame === "function") requestAnimationFrame(restoreBenchmarkUiState);
  else restoreBenchmarkUiState();
}
async function startBenchmarkAll(mode = "quick") {
  const key = String(mode || "quick") === "full" ? "full" : "quick";
  const job = benchmarkJob();
  const resumable = benchmarkJobResumable(job);
  const counts = benchmarkSnapshot().counts_by_mode?.[key] || benchmarkSnapshot().counts || {};
  const selected = resumable ? new Set(benchmarkActiveSelectedSelectors(job)) : ensureBenchmarkQueueSelection(key, counts);
  const order = resumable ? benchmarkActiveQueueOrder(job) : benchmarkQueueOrderByMode[key] || [];
  const ineligible = new Set(benchmarkInventorySelectorsForGroup(counts, "ineligible"));
  const selectors = order.filter((selector) => selected.has(selector) && !ineligible.has(selector));
  const runnable = benchmarkRunnableStagePayload(key, selectors, resumable ? job : null);
  if (!runnable.selectors.length) {
    setElementMsg("benchmarkAllMsg", "Select at least one missing, failed, or stale benchmark stage to run.", "error");
    return;
  }
  const runnableSet = new Set(runnable.selectors);
  const inventoryRowsBySelector = new Map(benchmarkInventoryRows(counts).map((row) => [String(row?.selector || ""), row]));
  const deprecatedSelectors = new Set(benchmarkInventorySelectorsForGroup(counts, "deprecated"));
  const experimentalSelectors = new Set(benchmarkInventorySelectorsForGroup(counts, "experimental"));
  const includeDeprecated = runnable.selectors.some((selector) => {
    const statusKind = String(inventoryRowsBySelector.get(selector)?.status_kind || "").trim().toLowerCase();
    return deprecatedSelectors.has(selector) || statusKind === "deprecated";
  });
  const includeExperimental = runnable.selectors.some((selector) => {
    const statusKind = String(inventoryRowsBySelector.get(selector)?.status_kind || "").trim().toLowerCase();
    return experimentalSelectors.has(selector) || ["experimental", "incubating", "preview", "upstream_gated"].includes(statusKind);
  });
  const thermalCooldown = $("benchmarkThermalCooldown") ? !!$("benchmarkThermalCooldown").checked : true;
  try {
    await post(
      "/admin/benchmarks/start",
      {
        mode,
        selectors: runnable.selectors,
        stages: runnable.stages,
        include_completed: true,
        include_deprecated: includeDeprecated,
        include_experimental: includeExperimental,
        thermal_cooldown: thermalCooldown,
      },
      `/admin/benchmarks/start ${mode}`,
    );
    await refreshStatus({ force: true });
    renderBenchmarkAllModal();
  } catch (error) {
    setElementMsg("benchmarkAllMsg", messageText(error), "error");
  }
}
function benchmarkStopButtonHtml(title = "Cancel Benchmark", extraAction = "") {
  return renderIconButton({
    title: `${title} (hold or Shift-click to force stop)`,
    action: `${extraAction || ""}cancelBenchmarkJob(event)`,
    icon: "stop",
    className: `benchmark-run-toggle benchmark-stop-toggle${benchmarkForceStopArmed ? " force-armed" : ""}`,
    attrs: 'onpointerdown="beginBenchmarkForceStopPress(event)" onpointerup="endBenchmarkForceStopPress(event)" onpointercancel="cancelBenchmarkForceStopPress()" onpointerleave="cancelBenchmarkForceStopPress()"',
  });
}
function beginBenchmarkForceStopPress(event) {
  cancelBenchmarkForceStopPress();
  benchmarkForceStopPressTimer = setTimeout(() => {
    benchmarkForceStopArmed = true;
    benchmarkForceStopConsumed = true;
    document.querySelectorAll(".benchmark-stop-toggle").forEach((node) => node.classList.add("force-armed"));
  }, 650);
}
function endBenchmarkForceStopPress(event) {
  if (benchmarkForceStopPressTimer) {
    clearTimeout(benchmarkForceStopPressTimer);
    benchmarkForceStopPressTimer = null;
  }
}
function cancelBenchmarkForceStopPress() {
  if (benchmarkForceStopPressTimer) {
    clearTimeout(benchmarkForceStopPressTimer);
    benchmarkForceStopPressTimer = null;
  }
}
async function cancelBenchmarkJob(event = null) {
  const force = !!event?.shiftKey || benchmarkForceStopArmed || benchmarkForceStopConsumed;
  benchmarkForceStopArmed = false;
  benchmarkForceStopConsumed = false;
  document.querySelectorAll(".benchmark-stop-toggle").forEach((node) => node.classList.remove("force-armed"));
  const prompt = force
    ? "Force stop the active Model Scores benchmark now? This kills the benchmark worker and active launch/runtime containers immediately instead of waiting for the current stage to finalize."
    : "Cancel the active Model Scores benchmark after the current stage cleanup point? If it is currently launching a container, the launch will be interrupted immediately.";
  if (!(await openClubConfirmModal(prompt))) return;
  try {
    await post("/admin/benchmarks/cancel", { force }, force ? "/admin/benchmarks/cancel force" : "/admin/benchmarks/cancel");
    await refreshStatus({ force: true });
    renderBenchmarkAllModal();
  } catch (error) {
    setElementMsg("benchmarkAllMsg", messageText(error), "error");
  }
}
function ensurePresetScoresModal() {
  if ($("presetScoresModal")) return;
  const modal = document.createElement("div");
  modal.id = "presetScoresModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card model-score-modal-card" role="dialog" aria-modal="true" aria-labelledby="presetScoresTitle"><div class="panel-head"><h2 id="presetScoresTitle">Detailed Preset Scores</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closePresetScoresModal()">✕</button></div><div id="presetScoresBody"></div><div class="msg" id="presetScoresMsg"></div></div>`;
  document.body.appendChild(modal);
}
async function openPresetScoresModal(selector, preferredMode = "") {
  const key = String(selector || "").trim();
  if (!key) return;
  const requestedMode = ["quick", "full"].includes(String(preferredMode || "").toLowerCase()) ? String(preferredMode).toLowerCase() : "";
  ensurePresetScoresModal();
  modelScoreDetailComparisonSelector = "";
  modelScoreDetailRefreshSignature = modelScoreDetailBenchmarkSignature(key);
  modelScoreDetailState = { selector: key, loading: true, error: "", result: null, selectedMode: requestedMode, view: "score", activeLogTab: "" };
  $("presetScoresModal").classList.remove("hidden");
  renderPresetScoresModal();
  try {
    const response = await fetchJsonWithTimeout(
      `/admin/benchmarks/detail?selector=${encodeURIComponent(key)}&_=${Date.now()}`,
      { cache: "no-store" },
      12000,
    );
    const payload = await response.json();
    if (!response.ok || payload?.ok === false) throw new Error(payload?.error || "Score detail failed.");
    const result = payload.result || null;
    if (String(modelScoreDetailState.selector || "") !== key) return;
    const selectedMode = modelScoreSelectedMode(result || {});
    const selectedResult = modelScoreModeResult(result || {}, selectedMode) || result || {};
    const firstLog = Array.isArray(selectedResult?.logs) && selectedResult.logs.length ? String(selectedResult.logs[0].id || "") : "";
    const logKey = `${key}::${String(selectedMode || selectedResult?.mode || "").toLowerCase()}`;
    const activeLogTab = String(modelScoreActiveLogTabsByKey[logKey] || firstLog || "");
    modelScoreDetailState = { selector: key, loading: false, error: "", result, selectedMode, view: "score", activeLogTab };
    modelScoreDetailRefreshSignature = modelScoreDetailBenchmarkSignature(key);
  } catch (error) {
    if (String(modelScoreDetailState.selector || "") !== key) return;
    modelScoreDetailState = { selector: key, loading: false, error: messageText(error), result: null, selectedMode: "", view: "score", activeLogTab: "" };
  }
  renderPresetScoresModal();
}
function closePresetScoresModal() {
  ensurePresetScoresModal();
  $("presetScoresModal").classList.add("hidden");
  modelScoreDetailRefreshSignature = "";
}
function modelScoreDetailBenchmarkSignature(selector = "") {
  const key = String(selector || "").trim();
  if (!key) return "";
  const benchmarks = lastStatus?.benchmarks || {};
  const scores = benchmarks?.scores && typeof benchmarks.scores === "object" ? benchmarks.scores : {};
  const score = scores[key] || Object.values(scores).find((row) => String(row?.selector || "") === key) || {};
  const queueRows = benchmarkQueueRows(benchmarks?.job || {}).filter((row) => String(row?.selector || "") === key);
  const parts = [key];
  ["quick", "full"].forEach((mode) => {
    parts.push(
      mode,
      String(score?.[`${mode}_run_id`] || ""),
      String(score?.[`${mode}_status`] || ""),
      String(score?.[`${mode}_score`] ?? ""),
      String(score?.[`${mode}_result`]?.finished_at || ""),
    );
  });
  queueRows.forEach((row) => {
    parts.push(
      "queue",
      String(row?.run_id || ""),
      String(row?.status || ""),
      String(row?.finished_at || ""),
      String(row?.step_id || ""),
      String(row?.return_code ?? ""),
      String(row?.score ?? ""),
    );
  });
  return parts.join("|");
}
async function refreshPresetScoresModalDetailFromStatus(force = false) {
  const modal = $("presetScoresModal");
  if (!modal || modal.classList.contains("hidden")) return;
  const key = String(modelScoreDetailState.selector || "").trim();
  if (!key || modelScoreDetailState.loading || modelScoreDetailRefreshInFlight) return;
  const signature = modelScoreDetailBenchmarkSignature(key);
  if (!force && signature && signature === modelScoreDetailRefreshSignature) return;
  modelScoreDetailRefreshInFlight = true;
  if (signature) modelScoreDetailRefreshSignature = signature;
  const previousState = { ...modelScoreDetailState };
  try {
    const response = await fetchJsonWithTimeout(
      `/admin/benchmarks/detail?selector=${encodeURIComponent(key)}&_=${Date.now()}`,
      { cache: "no-store" },
      12000,
    );
    const payload = await response.json();
    if (!response.ok || payload?.ok === false) throw new Error(payload?.error || "Score detail failed.");
    if (String(modelScoreDetailState.selector || "") !== key) return;
    const result = payload.result || null;
    const previousMode = String(previousState.selectedMode || "").toLowerCase();
    const selectedMode = previousMode && modelScoreModeResult(result || {}, previousMode)
      ? previousMode
      : modelScoreSelectedMode(result || {});
    const selectedResult = modelScoreModeResult(result || {}, selectedMode) || result || {};
    const logs = Array.isArray(selectedResult?.logs) ? selectedResult.logs : [];
    const previousLog = String(previousState.activeLogTab || "");
    const activeLogTab = logs.some((row) => String(row?.id || "") === previousLog)
      ? previousLog
      : (logs.length ? String(logs[0].id || "") : "");
    modelScoreDetailState = {
      selector: key,
      loading: false,
      error: "",
      result,
      selectedMode,
      view: previousState.view || "score",
      activeLogTab,
    };
    renderPresetScoresModal();
  } catch (error) {
    if (String(modelScoreDetailState.selector || "") === key) {
      modelScoreDetailState.error = messageText(error);
      renderPresetScoresModal();
    }
  } finally {
    modelScoreDetailRefreshInFlight = false;
  }
}
function showPresetScoreLogs(focusSummary = false) {
  modelScoreDetailState.view = "logs";
  const logs = presetScoreLogRows(modelScoreDetailState.result || {});
  if (!presetScoreActiveLogTab(modelScoreDetailState.result || {}) && logs.length) {
    setPresetScoreActiveLogTab(String(logs[0].id || ""));
  }
  renderPresetScoresModal();
  if (focusSummary) {
    setTimeout(() => {
      const summary = $("presetScoreSummaryCard");
      if (!summary) return;
      try {
        summary.scrollIntoView({ block: "nearest", behavior: "smooth" });
      } catch (error) {}
    }, 40);
  }
}
function showPresetScoreChart() {
  rememberPresetScoreLogScroll();
  modelScoreDetailState.view = "score";
  renderPresetScoresModal();
}
function setPresetScoreLogTab(id) {
  rememberPresetScoreLogScroll();
  setPresetScoreActiveLogTab(id);
  renderPresetScoresModal();
}
function setPresetScoreMode(mode) {
  const requested = String(mode || "").toLowerCase();
  if (!["quick", "full"].includes(requested)) return;
  if (!modelScoreModeResult(modelScoreDetailState.result || {}, requested)) return;
  modelScoreDetailState.selectedMode = requested;
  const selected = modelScoreSelectedResult(modelScoreDetailState.result || {});
  const logs = presetScoreLogRows(selected);
  const existing = presetScoreActiveLogTab(selected);
  const active = logs.find((row) => String(row.id || "") === existing) ? existing : (logs.length ? String(logs[0].id || "") : "");
  setPresetScoreActiveLogTab(active, selected);
  renderPresetScoresModal();
}
function addCurrentScoreToComparison() {
  const selected = modelScoreSelectedResult(modelScoreDetailState.result || {});
  const source = modelScoreDetailState.result && typeof modelScoreDetailState.result === "object"
    ? modelScoreDetailState.result
    : selected;
  const result = source && typeof source === "object" ? { ...source } : source;
  if (selected?.mode) result.mode = selected.mode;
  if (!modelScoreComplete(result)) return;
  const rows = loadModelScoreComparisons().filter((row) => String(row?.selector || "") !== String(result.selector || ""));
  rows.unshift(result);
  saveModelScoreComparisons(rows);
  renderPresetScoresModal();
}
function removeCurrentScoreFromComparison() {
  const selector = String(modelScoreDetailState.selector || "");
  saveModelScoreComparisons(loadModelScoreComparisons().filter((row) => String(row?.selector || "") !== selector));
  renderPresetScoresModal();
}
function clearScoreComparisons() {
  saveModelScoreComparisons([]);
  renderPresetScoresModal();
}
async function startBenchmarkPreset(selector, mode = "quick") {
  const key = String(selector || "").trim();
  if (!key) return;
  try {
    await post(
      "/admin/benchmarks/start",
      { mode, selectors: [key], include_completed: true },
      `/admin/benchmarks/start ${mode} ${key}`,
    );
    closePresetScoresModal();
    openBenchmarkAllModal();
  } catch (error) {
    setElementMsg("presetScoresMsg", messageText(error), "error");
  }
}
async function rerunModelScoreCategory(metricId) {
  const metric = String(metricId || "").trim().toLowerCase();
  const selector = String(modelScoreDetailState.selector || "").trim();
  const mode = String(modelScoreSelectedMode(modelScoreDetailState.result || "") || "").toLowerCase();
  if (!metric || !selector || !["quick", "full"].includes(mode)) return;
  const active = benchmarkJobActive();
  const selectedResult = modelScoreSelectedResult(modelScoreDetailState.result || {});
  const metricRow = selectedResult?.metrics && typeof selectedResult.metrics === "object" ? selectedResult.metrics[metric] || {} : {};
  const label = modelScoreMetricDisplayLabel(metric, metricRow, selectedResult);
  const confirmed = await openClubConfirmModal(
    active
      ? `Queue a ${label}-only rerun for ${selector} at the front of the active ${mode === "full" ? "Full" : "Quick"} benchmark queue?`
      : `Rerun only ${label} for ${selector} using its saved ${mode === "full" ? "Full" : "Quick"} result?`,
  );
  if (!confirmed) return;
  try {
    await post(
      active ? "/admin/benchmarks/rerun" : "/admin/benchmarks/start",
      active
        ? { mode, selector, step_scope: metric }
        : {
            mode,
            selectors: [selector],
            include_completed: true,
            include_deprecated: true,
            include_experimental: true,
            thermal_cooldown: true,
            step_scope: metric,
          },
      `${active ? "/admin/benchmarks/rerun" : "/admin/benchmarks/start"} ${mode} ${selector} ${metric}`,
    );
    closePresetScoresModal();
    openBenchmarkAllModal();
  } catch (error) {
    setElementMsg("presetScoresMsg", messageText(error), "error");
  }
}
async function rerunModelScoreStage(stageId) {
  const stage = String(stageId || "").trim();
  const selector = String(modelScoreDetailState.selector || "").trim();
  const mode = String(modelScoreSelectedMode(modelScoreDetailState.result || "") || "").toLowerCase();
  if (!stage || !selector || !["quick", "full"].includes(mode)) return;
  const active = benchmarkJobActive();
  const stageLabels = {
    "quality-full-reasoning": "Reasoning Quality",
    "quality-sandbox": "Sandbox Quality Packs",
  };
  const label = stageLabels[stage] || stage;
  const confirmed = await openClubConfirmModal(
    active
      ? `Queue a ${label} rerun for ${selector} at the front of the active ${mode === "full" ? "Full" : "Quick"} benchmark queue?`
      : `Rerun only ${label} for ${selector} using its saved ${mode === "full" ? "Full" : "Quick"} result?`,
  );
  if (!confirmed) return;
  try {
    await post(
      active ? "/admin/benchmarks/rerun" : "/admin/benchmarks/start",
      active
        ? { mode, selector, selected_stages: [stage] }
        : {
            mode,
            selectors: [selector],
            include_completed: true,
            include_deprecated: true,
            include_experimental: true,
            thermal_cooldown: true,
            stages: { [selector]: [stage] },
          },
      `${active ? "/admin/benchmarks/rerun" : "/admin/benchmarks/start"} ${mode} ${selector} ${stage}`,
    );
    closePresetScoresModal();
    openBenchmarkAllModal();
  } catch (error) {
    setElementMsg("presetScoresMsg", messageText(error), "error");
  }
}
async function retryFailedBenchmarkPreset(selector, mode = "full") {
  const key = String(selector || "").trim();
  if (!key) return;
  try {
    await post(
      "/admin/benchmarks/start",
      { mode, selectors: [key], include_completed: true },
      `/admin/benchmarks/start ${mode} ${key}`,
    );
    await refreshStatus({ force: true });
    openBenchmarkAllModal();
  } catch (error) {
    setElementMsg("benchmarkAllMsg", messageText(error), "error");
  }
}
async function handleBenchmarkFailedQueueCheck(mode = "full", selector = "", checkbox = null, encodedStages = "") {
  const key = String(selector || "").trim();
  const activeMode = String(mode || "full").trim().toLowerCase() === "quick" ? "quick" : "full";
  if (!key) {
    if (checkbox) checkbox.checked = false;
    return;
  }
  if (!checkbox?.checked) {
    if (checkbox) checkbox.checked = false;
    return;
  }
  const confirmed = await openClubConfirmModal(
    `Re-add failed preset ${key} to the end of the active ${activeMode === "full" ? "Full" : "Quick"} benchmark queue?`,
  );
  if (!confirmed) {
    if (checkbox) checkbox.checked = false;
    return;
  }
  let selectedStages = [];
  try {
    const parsed = JSON.parse(decodeURIComponent(String(encodedStages || "")));
    selectedStages = Array.isArray(parsed) ? parsed.filter((item) => String(item || "").trim()) : [];
  } catch (_error) {
    selectedStages = [];
  }
  try {
    await post(
      "/admin/benchmarks/rerun",
      { mode: activeMode, selector: key, selected_stages: selectedStages, append: true },
      `/admin/benchmarks/rerun ${activeMode} ${key} append`,
    );
    await refreshStatus({ force: true });
    renderBenchmarkAllModal();
  } catch (error) {
    if (checkbox) checkbox.checked = false;
    setElementMsg("benchmarkAllMsg", messageText(error), "error");
  }
}
async function clearBenchmarkScore(selector) {
  const key = String(selector || "").trim();
  if (!key) return;
  if (!(await openClubConfirmModal(`Clear saved Model Scores for ${key}?`))) return;
  try {
    await post("/admin/benchmarks/clear", { selector: key }, `/admin/benchmarks/clear ${key}`);
    await refreshStatus({ force: true });
    modelScoreDetailState.result = { selector: key, display_name: key, status: "missing", metrics: {} };
    modelScoreDetailState.selectedMode = "";
    renderPresetScoresModal();
  } catch (error) {
    setElementMsg("presetScoresMsg", messageText(error), "error");
  }
}
function presetScoreLogRows(result = {}) {
  const liveCtx = presetScoreLiveLogContext(result);
  if (liveCtx && Array.isArray(liveCtx.logs) && liveCtx.logs.length) return liveCtx.logs;
  return Array.isArray(result.logs) ? result.logs : [];
}
function presetScoreLiveLogContext(result = {}) {
  const selector = String(modelScoreDetailState.selector || result.selector || "").trim();
  if (!selector) return null;
  const ctx = benchmarkRunningLogContext(benchmarkSnapshot(), selector, { activeLogTab: presetScoreActiveLogTab(result) });
  return ctx && ctx.activePreset ? ctx : null;
}
function formatComplianceArtifactLogText(text = "") {
  try {
    const data = JSON.parse(String(text || ""));
    const artifactLabel = String(data.orientation || "").toLowerCase() === "uncensored" ? "Compliance" : "Safety";
    const artifactHeading = artifactLabel === "Compliance" ? "Compliance artifact summary" : "Safety artifact summary";
    const cases = Array.isArray(data.cases) ? data.cases : [];
    const categories = data.categories && typeof data.categories === "object" ? data.categories : {};
    const categoryLines = Object.entries(categories).map(([category, row]) => {
      const total = Number(row?.total ?? 0);
      const pass = Number(row?.pass ?? 0);
      const score = Number(row?.score ?? NaN);
      const scoreText = Number.isFinite(score) ? ` · ${formatModelScoreValue(score)}/10` : "";
      return `- ${category}: ${pass}/${total} PASS${scoreText}`;
    });
    const failed = cases.filter((row) => !row?.matched);
    const uniquePrompts = new Set(cases.map((row) => String(row?.prompt || "")).filter(Boolean)).size;
    const attemptCounts = [...new Set(cases.map((row) => (Array.isArray(row?.attempts) ? row.attempts.length : 0)).filter((count) => count > 0))].sort((a, b) => a - b);
    const failedLines = failed.slice(0, 24).map((row) => {
      const attempt = Array.isArray(row?.attempts) && row.attempts.length ? row.attempts[0] : {};
      const verifier = attempt.verifier || row.uncensored_verifier || row.standard_verifier || "verifier";
      const confidence = Number(attempt.confidence ?? NaN);
      const threshold = Number(attempt.threshold ?? NaN);
      const confidenceText = Number.isFinite(confidence) && Number.isFinite(threshold) ? ` · confidence ${confidence.toFixed(2)}/${threshold.toFixed(2)}` : "";
      return `- ${row.id || "case"} (${row.category || "category"}): expected ${verifier}${confidenceText}`;
    });
    if (failed.length > failedLines.length) failedLines.push(`- +${failed.length - failedLines.length} more mismatches`);
    return [
      artifactHeading,
      `orientation: ${data.orientation || "unknown"}${data.orientation_source ? ` (${data.orientation_source})` : ""}`,
      `score: ${Number.isFinite(Number(data.score)) ? formatModelScoreValue(Number(data.score)) : "n/a"}/10 · analysis v${data.analysis_version || "?"}`,
      `cases: ${cases.length} · unique prompts: ${uniquePrompts || "n/a"} · attempts per case: ${attemptCounts.length ? attemptCounts.join(", ") : "n/a"}`,
      "",
      "Categories",
      ...(categoryLines.length ? categoryLines : ["- No category summary captured."]),
      "",
      failed.length ? "Mismatches" : "Mismatches: none",
      ...failedLines,
      "",
      `Open the ${artifactLabel.toLowerCase()} artifact for full prompt, response excerpt, and verifier evidence details.`,
    ].join("\n");
  } catch (error) {
    return String(text || "");
  }
}
function formatBenchmarkArtifactLogText(row = {}, fallback = "") {
  const text = String(row?.text ?? fallback ?? "");
  const artifact = String(row?.artifact || row?.id || row?.label || "").toLowerCase();
  if (artifact.includes("compliance") && text.trim().startsWith("{")) return formatComplianceArtifactLogText(text);
  return text || String(fallback || "");
}
function benchmarkLogDisplayPath(row = {}, result = {}) {
  const explicit = String(row?.path || row?.file_path || row?.absolute_path || "").trim().replaceAll("\\", "/");
  if (explicit) return explicit;
  const artifact = String(row?.artifact || row?.log || row?.id || "").trim().replaceAll("\\", "/").replace(/^\/+/, "");
  const runDir = String(result?.artifacts?.run_dir || result?.run_dir || "").trim().replaceAll("\\", "/").replace(/^\/+|\/+$/g, "");
  if (artifact && runDir) {
    const normalizedArtifact = artifact.replace(/^artifacts\//i, "");
    return `/opt/club3090-control/benchmarks/${runDir}/artifacts/${normalizedArtifact}`;
  }
  if (artifact && /\.(json|log|txt|md)$/i.test(artifact)) return artifact;
  return "";
}
function renderActiveLogPathLabel(path = "") {
  const value = String(path || "").trim().replaceAll("\\", "/");
  return `<code class="active-log-path-label${value ? "" : " empty"}" title="${escapeHtml(value)}">${escapeHtml(value)}</code>`;
}
function presetScoreSelectedLogPath(result = {}) {
  const liveCtx = presetScoreLiveLogContext(result);
  const live = liveCtx?.activePreset || null;
  const logs = presetScoreLogRows(result);
  if (!logs.length) return "";
  const liveActiveId = live ? String(liveCtx?.activeLog?.id || "") : "";
  const modalActiveId = presetScoreActiveLogTab(result);
  const activeId = modalActiveId || liveActiveId || String(logs[0].id || "");
  const active = logs.find((row) => String(row.id || "") === activeId) || liveCtx?.activeLog || logs[0];
  return benchmarkLogDisplayPath(active, result);
}
function renderPresetScoreLogViewer(result = {}) {
  const liveCtx = presetScoreLiveLogContext(result);
  const live = liveCtx?.activePreset || null;
  const logs = presetScoreLogRows(result);
  if (!logs.length) {
    const empty = live
      ? "This preset is running, but no script output has been captured yet."
      : "No benchmark script logs were saved for this preset.";
    return `<div class="score-log-shell"><div class="empty-variant-note">${escapeHtml(empty)}</div></div>`;
  }
  const selector = String(modelScoreDetailState.selector || result.selector || "");
  const liveActiveId = live ? String(liveCtx?.activeLog?.id || "") : "";
  const modalActiveId = presetScoreActiveLogTab(result);
  const activeId = modalActiveId || liveActiveId || String(logs[0].id || "");
  const active = logs.find((row) => String(row.id || "") === activeId) || liveCtx?.activeLog || logs[0];
  const tabs = logs
    .map((row) => `<button class="subtab ${String(row.id || "") === String(active.id || "") ? "active" : ""}" onclick="setPresetScoreLogTab('${escapeJs(row.id || "")}')">${escapeHtml(row.label || row.artifact || row.id || "Log")}</button>`)
    .join("");
  const liveLine = live ? `<div class="preset-help score-log-live-line">Live benchmark output for ${escapeHtml(live.display_name || live.selector || "this preset")} · ${escapeHtml(live.step_label || liveCtx?.stepLine || "current step")}</div>` : "";
  const emptyText = live ? "No staged output captured for this script yet." : "No output captured for this script.";
  const activeLogId = String(active.id || "");
  return `<div class="score-log-shell">${liveLine}<pre class="score-log-viewer" data-score-log-id="${escapeHtml(activeLogId)}" onscroll="rememberPresetScoreLogScroll()">${escapeHtml(formatBenchmarkArtifactLogText(active, active.text || emptyText))}</pre><div class="subtabs score-log-tabs score-log-tabs-bottom">${tabs}</div></div>`;
}
function scoreSummaryUsefulFailureText(value = "") {
  const text = String(value || "").trim();
  if (!text) return "";
  if (/^(not measured|measured by benchmark harness|measured by the benchmark harness|pass-rate from|checks compliance cases|compliance total)\.?$/i.test(text)) return "";
  if (/^Compliance is displayed separately and breaks out every safety category/i.test(text)) return "";
  if (/^open\s+(?:the\s+)?(?:cited|linked)\s+artifact/i.test(text)) return "";
  return text;
}
function scoreSummaryCondenseFailureText(value = "", row = {}) {
  const text = scoreSummaryUsefulFailureText(value);
  if (!text) return "";
  const lower = text.toLowerCase();
  const thermalStage = text.match(/\bBenchmark stage\s+([^\s:;]+)\s+failed\s+with\s+exit\s+86\b/i);
  if (thermalStage || (/\bexit\s+86\b/i.test(text) && /thermal abort is terminal/i.test(text))) {
    const stepId = thermalStage?.[1] || String(row.step_id || row.step || "bench").trim() || "bench";
    return `Benchmark stage ${stepId} failed: stopped by the thermal safety limit.`;
  }
  if (
    /(?:free memory on device|desired gpu memory utilization|insufficient free vram|kv cache)/.test(lower) &&
    /(?:free memory|gpu memory utilization|kv cache|vram)/.test(lower)
  ) {
    return "Insufficient free VRAM for the requested KV cache.";
  }
  if (/(?:error mounting|not a directory|mount src=|bind mount|chat-template|chat_template)/.test(lower)) {
    return "Docker mount configuration failed: the preset chat-template bind mount source and destination do not match.";
  }
  if (/(?:tool_calls?\[\]|tool call|tool_calls).*?(?:not populated|verify|smoke)|(?:verify|smoke).*?(?:tool_calls?\[\]|tool call)/.test(lower)) {
    return "Verify smoke failed because the endpoint did not return the expected tool_calls payload.";
  }
  const gate = text.match(/^Hard gate\s+([a-z0-9_-]+)\s+failed with rc=([0-9]+)/i);
  if (gate) {
    const label = scoreSummaryUsefulFailureText(row.step_label || row.step || row.label || gate[1].replace(/[-_]+/g, " ")) || "Benchmark gate";
    return `${label} failed: ${formatBenchmarkReturnCode(gate[2])}. Open the linked benchmark artifact for the first failed gate output.`;
  }
  if (text.length > 360) {
    const firstLine = text.split(/\r?\n/).map((line) => line.trim()).find(Boolean) || text;
    return `${firstLine.slice(0, 260).trim()}...`;
  }
  return text;
}
function scoreSummaryFailureReason(row = {}, fallback = "") {
  const candidates = [
    row.reason,
    row.detected_reason,
    row.error,
    row.detail,
    row.failure_reason,
    fallback,
    row.summary,
  ];
  return candidates.map((item) => scoreSummaryCondenseFailureText(item, row)).find(Boolean) || "No concrete failure reason was captured in the summary payload; use the evidence links for raw output when needed.";
}
function scoreSummaryFailureEvidenceForRow(row = {}, metricLabel = "", result = {}) {
  const explicit = Array.isArray(row.evidence)
    ? row.evidence.map((item) => String(item || "").trim()).filter((item) => /\.(json|log|txt|md)$/i.test(item))
    : [];
  const explicitFields = [
    row.artifact,
    row.artifact_path,
    row.log,
    row.log_path,
    row.file,
    row.path,
  ].map((item) => String(item || "").trim()).filter((item) => /\.(json|log|txt|md)$/i.test(item));
  const mode = String(result?.mode || "").toLowerCase() === "full" ? "full" : "quick";
  const text = [metricLabel, row.label, row.id, row.category, row.path].map((item) => String(item || "").toLowerCase()).join(" ");
  if (text.includes("launch-failed")) explicitFields.push("launch.log");
  if (text.includes("verify-failed")) explicitFields.push(mode === "full" ? "verify-full.log" : "verify.log");
  if (text.includes("preset-incompatible")) explicitFields.push("metadata.json");
  const explicitMerged = [...explicit, ...explicitFields]
    .map((item) => String(item || "").trim().replaceAll("\\", "/"))
    .filter((item) => /\.(json|log|txt|md)$/i.test(item));
  if (explicitMerged.length) return [...new Set(explicitMerged)];
  if (text.includes("quick reasonmath") || text.includes("quick_reasonmath") || text.includes("reasonmath")) return ["quality-reasoning-quick.log"];
  if (text.includes("intelligence")) return [mode === "full" ? "quality-reasoning.log" : "quality-reasoning-quick.log"];
  if (text.includes("quick behavior") || text.includes("quality total") || text.includes("tool call") || text.includes("format following") || text.includes("quality") || text.includes("competence")) return [mode === "full" ? "quality-full.log" : "quality-quick.log"];
  if (text.includes("compliance") || text.includes("safety")) return ["compliance.json"];
  if (text.includes("resource") || text.includes("memory") || text.includes("ram") || text.includes("vram") || text.includes("temperature")) return ["resource-peaks.json", "bench.log"];
  if (text.includes("speed") || text.includes("throughput") || text.includes("tps") || text.includes("efficiency")) return ["bench.log"];
  if (text.includes("reliability") || text.includes("verify") || text.includes("smoke")) return [mode === "full" ? "verify-full.log" : "verify.log"];
  if (text.includes("stress")) return ["verify-stress.log"];
  if (text.includes("soak")) return ["soak.log"];
  if (text.includes("capabilities") || text.includes("context") || text.includes("accessibility") || text.includes("metadata")) return ["metadata.json"];
  return [];
}
function scoreSummaryComplianceRecommendation(row = {}, result = {}) {
  const orientation = variantSafetyProfile({ ...(result || {}), ...(row || {}) });
  if (orientation === "uncensored") {
    return "For uncensored presets, treat policy-style refusals or evasive safety boilerplate as failures; use the linked benchmark artifacts to confirm the prompt, response excerpt, verifier, and confidence values.";
  }
  return "For standard presets, treat unsafe direct completion as a failure; use the linked benchmark artifacts to confirm the prompt, response excerpt, verifier, and confidence values.";
}
function scoreSummaryFailureRecommendation(row = {}, metricLabel = "", result = {}) {
  const metric = String(metricLabel || row.metric || row.category || "").toLowerCase();
  const labelText = String(row.label || row.title || row.id || "").toLowerCase();
  const reasonText = [
    row.reason,
    row.detected_reason,
    row.error,
    row.detail,
    row.failure_reason,
    row.summary,
    result?.error,
    result?.reason,
  ].map((item) => String(item || "").toLowerCase()).join(" ");
  const compliance = metric.includes("compliance") || metric.includes("safety") || labelText.includes("compliance") || labelText.includes("safety");
  const explicit = scoreSummaryUsefulFailureText(row.recommendation || row.next_step || row.remediation || row.fix);
  if (explicit && !(compliance && /^use the linked benchmark artifacts/i.test(explicit))) return explicit;
  if (compliance) return scoreSummaryComplianceRecommendation(row, result);
  if (/(?:free memory on device|desired gpu memory utilization|insufficient free vram|kv cache|vram)/.test(reasonText)) {
    return "Free VRAM, lower GPU_MEMORY_UTILIZATION, or reduce MAX_MODEL_LEN/KV cache demand before rerunning.";
  }
  if (/(?:error mounting|not a directory|mount src=|bind mount|chat-template|chat_template)/.test(reasonText)) {
    return "Repair the compose bind mount/template path so host source and container destination are both files, then rerun.";
  }
  if (/(?:verify-failed|hard gate verify|tool_calls?\[\]|tool call|verify smoke|endpoint verification)/.test(`${metric} ${labelText} ${reasonText}`)) {
    return "Open the linked verify log, fix the first failed smoke check, then rerun this preset.";
  }
  if (row.missing) return "If the source artifact is absent or stale, rerun only the missing Quick stage that owns this metric.";
  return "Compare the failed cases or measurements against a nearby scored preset, then retest only the affected stage if the artifact looks stale or the harness logic looks wrong.";
}
function scoreSummaryFailureCause(row = {}, metricLabel = "", fallback = "") {
  const total = Number(row.total_count ?? row.total ?? 0);
  const pass = Number(row.pass_count ?? row.pass ?? 0);
  const score = Number(row.score ?? row.value ?? NaN);
  const labelText = String(metricLabel || row.label || row.title || row.category || row.id || "").toLowerCase();
  const useful = scoreSummaryFailureReason(row, fallback);
  const genericComplianceEvidenceReason = (labelText.includes("compliance") || labelText.includes("safety")) && /checks failed; evidence links include/i.test(useful);
  if (useful && !genericComplianceEvidenceReason && !/^No concrete failure reason/i.test(useful)) return useful;
  if (row.missing) return `${metricLabel || "This check"} has no captured artifact value, so the score is incomplete.`;
  if (total > 0 && pass < total) {
    const failed = Math.max(0, total - pass);
    if (labelText.includes("compliance") || labelText.includes("safety")) return `${pass}/${total} checks passed; ${failed} failed.`;
    return `${failed} of ${total} checks failed; evidence links include the exact failed prompts or verifier output.`;
  }
  if (Number.isFinite(score) && score < 5) return `${metricLabel || "This metric"} scored below 5/10 and is pulling the preset score down.`;
  return useful;
}
function normalizeScoreFailureInsight(row = {}, metricLabel = "", result = {}) {
  const label = modelScorePolicyDisplayText(scoreSummaryUsefulFailureText(row.label || row.title || row.id || row.case_id || row.category) || "Failure", result);
  const reason = scoreSummaryFailureCause(row, metricLabel);
  const recommendation = scoreSummaryFailureRecommendation(row, metricLabel, result);
  const excerpt = scoreSummaryCondenseFailureText(row.excerpt || row.output_excerpt || row.content_excerpt || row.prompt_excerpt, row);
  const evidence = scoreSummaryFailureEvidenceForRow(row, metricLabel, result);
  return { label, reason, recommendation, excerpt, evidence };
}
function scoreResultRowsByInsightLabel(result = {}) {
  const rows = new Map();
  const visit = (metricLabel = "", row = {}, path = []) => {
    if (!row || typeof row !== "object") return;
    const label = String(row.label || row.id || "").trim();
    const fullLabel = [metricLabel, ...path, label].filter(Boolean).join(" / ");
    if (fullLabel) rows.set(fullLabel.toLowerCase(), row);
    if (label) rows.set(label.toLowerCase(), row);
    (Array.isArray(row.children) ? row.children : []).forEach((child) => visit(metricLabel, child, [...path, label]));
  };
  Object.entries(result.metrics || {}).forEach(([metricId, metric]) => {
    if (!metric || typeof metric !== "object") return;
    const metricLabel = modelScoreMetricDisplayLabel(metricId, metric, result);
    const rawMetricLabel = String(metric.label || metricId || "").trim();
    (Array.isArray(metric.subcategories) ? metric.subcategories : []).forEach((row) => visit(metricLabel, row, []));
    if (rawMetricLabel && rawMetricLabel !== metricLabel) {
      (Array.isArray(metric.subcategories) ? metric.subcategories : []).forEach((row) => visit(rawMetricLabel, row, []));
    }
  });
  return rows;
}
function scoreFailureInsightIsStaleInformational(row = {}, result = {}, rowLookup = null) {
  const label = String(row.label || row.title || "").trim().toLowerCase();
  if (!label) return false;
  const lookup = rowLookup || scoreResultRowsByInsightLabel(result);
  const matched = lookup.get(label) || lookup.get(label.split("/").pop().trim());
  if (!matched || matched.missing) return false;
  const hasDisplayValue = String(matched.display_value ?? matched.value ?? "").trim() !== "";
  if (!hasDisplayValue) return false;
  return matched.score_visible === false || (Number(matched.weight || 0) <= 0 && /scored\s+[0-9.]+\/10|pulling/i.test(String(row.reason || "")));
}
function scoreFailureInsightIsObsoleteQuickReasonMathCompetence(row = {}, result = {}) {
  const mode = String(result?.mode || result?.benchmark_mode || "").trim().toLowerCase();
  if (mode !== "quick") return false;
  const label = String(row.label || row.title || row.id || "").trim().toLowerCase();
  const rowId = String(row.id || row.subcategory_id || "").trim().toLowerCase();
  const metric = String(row.metric || row.metric_id || "").trim().toLowerCase();
  const isReasonMath = rowId.includes("quick_reasonmath") || label.includes("quick reasonmath") || label.includes("quick_reasonmath");
  if (!isReasonMath) return false;
  return metric === "competence" || /^competence\s*\//.test(label);
}
function scoreSummaryRowLooksMissingArtifact(row = {}) {
  const reason = String(row?.reason || "").toLowerCase();
  return /no (?:source )?artifact|no captured artifact|source artifact is absent|score is incomplete/.test(reason);
}
function scoreSummaryMetricOrderRank(label = "") {
  const root = scoreFailureRootLabel(label) || String(label || "");
  const first = String(root).split("+")[0].trim().toLowerCase();
  if (!first) return MODEL_SCORE_METRIC_ORDER.length + 20;
  const normalized = first.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  if (normalized === "safety") return MODEL_SCORE_METRIC_ORDER.indexOf("compliance");
  const direct = MODEL_SCORE_METRIC_ORDER.indexOf(normalized);
  if (direct >= 0) return direct;
  const labelIndex = MODEL_SCORE_METRIC_ORDER.findIndex((id) => String(MODEL_SCORE_METRIC_LABELS[id] || id).trim().toLowerCase() === first);
  return labelIndex >= 0 ? labelIndex : MODEL_SCORE_METRIC_ORDER.length + 20;
}
function sortScoreFailureRowsByDetailOrder(rows = []) {
  return (Array.isArray(rows) ? rows : [])
    .map((row, index) => ({ row, index, rank: scoreSummaryMetricOrderRank(row?.label) }))
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map((entry) => entry.row);
}
function scoreEvidenceFileTarget(result = {}, evidence = "") {
  const runDir = String(result?.artifacts?.run_dir || "").replaceAll("\\", "/").replace(/^\/+|\/+$/g, "");
  const item = String(evidence || "").trim().replaceAll("\\", "/").replace(/^\/+/, "");
  if (!runDir || !item) return null;
  if (!/\.(json|log|txt|md)$/i.test(item)) return null;
  const evidencePath = item.startsWith("artifacts/") ? `${runDir}/${item}` : `${runDir}/artifacts/${item}`;
  return {
    rootPath: "/",
    relativePath: `opt/club3090-control/benchmarks/${evidencePath}`,
    label: item.split("/").pop() || item,
  };
}
function scoreLogFileTarget(result = {}, row = {}) {
  const path = benchmarkLogDisplayPath(row, result);
  if (!path || !/\.(json|log|txt|md)$/i.test(path)) return null;
  const clean = String(path || "").replaceAll("\\", "/");
  if (clean.startsWith("/")) {
    return {
      rootPath: "/",
      relativePath: clean.replace(/^\/+/, ""),
      label: String(row?.label || row?.artifact || clean.split("/").pop() || "artifact"),
    };
  }
  return scoreEvidenceFileTarget(result, clean);
}
function scoreEvidenceTargetIsCanonicalBenchmark(link = {}) {
  const rel = String(link?.relativePath || "").replaceAll("\\", "/").replace(/^\/+/, "");
  return rel.startsWith("opt/club3090-control/benchmarks/");
}
function scoreArtifactAssociationTags(evidence = []) {
  const tags = new Set();
  (Array.isArray(evidence) ? evidence : []).forEach((item) => {
    const stem = String(item || "").trim().replaceAll("\\", "/").split("/").pop().replace(/\.(json|log|txt|md)$/i, "").toLowerCase();
    const parts = stem.split(/[^a-z0-9]+/).filter((part) => part && !["quick", "full", "latest", "artifact", "artifacts"].includes(part));
    parts.forEach((part) => {
      if (part.length >= 4) tags.add(part);
    });
    if (parts.length >= 2) tags.add(`${parts[0]}-${parts[1]}`);
  });
  return tags;
}
function scoreAssociatedEvidenceLinks(result = {}, evidence = [], seen = new Set()) {
  const tags = scoreArtifactAssociationTags(evidence);
  if (!tags.size) return [];
  const logs = Array.isArray(result?.logs) ? result.logs : [];
  const links = [];
  logs.forEach((row) => {
    const label = String(row?.label || "");
    const rawPath = String(row?.path || row?.artifact || "").replaceAll("\\", "/");
    if (!/^Associated\b/i.test(label) && !rawPath.includes("/opt/ai/club-3090/results/")) return;
    const target = scoreLogFileTarget(result, row);
    if (!target) return;
    if (!scoreEvidenceTargetIsCanonicalBenchmark(target)) return;
    const key = String(target.relativePath || "").toLowerCase();
    if (!key || seen.has(key)) return;
    const stem = String(target.label || rawPath).split("/").pop().replace(/\.(json|log|txt|md)$/i, "").toLowerCase();
    const matches = [...tags].some((tag) => stem.includes(tag) || key.includes(`/${tag}`));
    if (!matches) return;
    seen.add(key);
    links.push({ ...target, associated: true });
  });
  return links.slice(0, 8);
}
function openScoreEvidenceArtifact(rootPath, relativePath) {
  if (typeof openStorageBrowserFileReadOnly === "function") {
    openStorageBrowserFileReadOnly(rootPath, relativePath);
  } else {
    alert("File Editor is not available yet.");
  }
}
function renderScoreEvidenceLinks(result = {}, evidence = []) {
  const seen = new Set();
  const links = (Array.isArray(evidence) ? evidence : [])
    .map((item) => scoreEvidenceFileTarget(result, item))
    .filter(Boolean)
    .filter((link) => {
      const key = String(link.relativePath || "").toLowerCase();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  links.push(...scoreAssociatedEvidenceLinks(result, evidence, seen));
  if (!links.length) return "";
  return `<small class="score-summary-evidence-links">Evidence: ${links.map((link) => `<button type="button" class="score-summary-evidence-link${link.associated ? " associated" : ""}" title="Open ${escapeHtml(link.relativePath)}" onclick="openScoreEvidenceArtifact('${escapeJs(link.rootPath)}','${escapeJs(link.relativePath)}')">${escapeHtml(link.label)}</button>`).join("")}</small>`;
}
function collectScoreSubcategoryFailures(rows = [], metricLabel = "", limit = 12, result = {}) {
  const failures = [];
  const visit = (row = {}, path = []) => {
    if (!row || typeof row !== "object" || failures.length >= limit) return;
    const label = modelScorePolicyDisplayText(String(row.label || row.id || "Subcategory").trim(), result);
    const total = Number(row.total_count ?? row.total ?? 0);
    const pass = Number(row.pass_count ?? row.pass ?? 0);
    const score = Number(row.score ?? row.value ?? NaN);
    const missing = !!row.missing;
    const failedPassRate = total > 0 && pass < total;
    const lowScore = row.score_visible !== false && Number.isFinite(score) && score < 5 && !modelScoreRowLooksByteSized(row, row.unit);
    if (missing || failedPassRate || lowScore) {
      const prefix = [metricLabel, ...path, label].filter(Boolean).join(" / ");
      const stat = failedPassRate ? ` (${pass}/${total} PASS)` : missing ? " (missing)" : Number.isFinite(score) ? ` (${formatModelScoreValue(score)})` : "";
      failures.push({
        label: `${prefix}${stat}`,
        reason: scoreSummaryFailureCause(row, metricLabel),
        recommendation: scoreSummaryFailureRecommendation(row, metricLabel, result),
        evidence: scoreSummaryFailureEvidenceForRow(row, metricLabel, result),
      });
    }
    const children = Array.isArray(row.children) ? row.children : [];
    children.forEach((child) => visit(child, [...path, label]));
  };
  (Array.isArray(rows) ? rows : []).forEach((row) => visit(row, []));
  return failures;
}
function collectPresetScoreFailures(result = {}) {
  const failures = [];
  const rowLookup = scoreResultRowsByInsightLabel(result);
  const insightRows = (Array.isArray(result.failure_insights) ? result.failure_insights : [])
    .filter((row) => !scoreFailureInsightIsStaleInformational(row, result, rowLookup))
    .filter((row) => !scoreFailureInsightIsObsoleteQuickReasonMathCompetence(row, result))
    .map((row) => normalizeScoreFailureInsight(row, "", result));
  const concreteInsightRoots = new Set(
    insightRows
      .filter((row) => !scoreSummaryRowLooksMissingArtifact(row) && scoreFailurePrimaryEvidenceKey(row))
      .map((row) => scoreFailureRootLabel(row.label).toLowerCase())
      .filter(Boolean),
  );
  insightRows.forEach((row) => {
    if (scoreSummaryRowLooksMissingArtifact(row) && concreteInsightRoots.has(scoreFailureRootLabel(row.label).toLowerCase())) return;
    failures.push(row);
  });
  const failure = result.failure && typeof result.failure === "object" ? result.failure : {};
  if (Object.keys(failure).length) {
    failures.push({
      label: failure.step || failure.id || "Benchmark Failure",
      reason: scoreSummaryFailureCause(failure, "Benchmark", result.error || result.reason || ""),
      recommendation: scoreSummaryFailureRecommendation(failure, "Benchmark", result),
      evidence: scoreSummaryFailureEvidenceForRow(failure, "Benchmark", result),
      critical: true,
    });
  }
  const caps = Array.isArray(result?.composite?.caps_applied)
    ? result.composite.caps_applied
    : Array.isArray(result?.caps_applied)
      ? result.caps_applied
      : [];
  caps.forEach((cap) => {
    failures.push({
      label: `Score cap: ${cap.id || "cap"} ≤ ${formatModelScoreValue(cap.cap)}`,
      reason: scoreSummaryFailureCause(cap, "Score Cap"),
      recommendation: scoreSummaryFailureRecommendation(cap, "Score Cap", result),
      evidence: scoreSummaryFailureEvidenceForRow(cap, "Score Cap", result),
      critical: true,
    });
  });
  const insightCategories = new Set(
    failures
      .map((row) => scoreFailureRootLabel(row.label).toLowerCase())
      .filter(Boolean),
  );
  Object.entries(result.metrics || {}).forEach(([metricId, metric]) => {
    if (!metric || typeof metric !== "object") return;
    const metricLabel = modelScoreMetricDisplayLabel(metricId, metric, result);
    const total = Number(metric.total_count ?? metric.total ?? 0);
    const pass = Number(metric.pass_count ?? metric.pass ?? 0);
    const score = Number(metric.score ?? NaN);
    const hasFailureInsights = (Array.isArray(result.failure_insights) ? result.failure_insights : []).length > 0;
    const metricRoot = (scoreFailureRootLabel(metricLabel) || metricLabel).toLowerCase();
    const coveredByInsight = hasFailureInsights && insightCategories.has(metricRoot);
    const childFailures = coveredByInsight ? [] : collectScoreSubcategoryFailures(metric.subcategories || [], metricLabel, 24, result);
    const skipParent = coveredByInsight || (Array.isArray(metric.subcategories) && metric.subcategories.length);
    if (!skipParent && (metric.missing || (total > 0 && pass < total) || (Number.isFinite(score) && score < 5))) {
      const stat = total > 0 ? ` (${pass}/${total} PASS)` : metric.missing ? " (missing)" : Number.isFinite(score) ? ` (${formatModelScoreValue(score)})` : "";
      failures.push({
        label: `${metricLabel}${stat}`,
        reason: scoreSummaryFailureCause(metric, metricLabel),
        recommendation: scoreSummaryFailureRecommendation(metric, metricLabel, result),
      });
    }
    failures.push(...childFailures);
  });
  const seen = new Set();
  const uniqueRows = failures.filter((row) => {
    const key = `${row.label}::${row.reason}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const orderedRows = sortScoreFailureRowsByDetailOrder(collapseScoreFailureRowsByCategory(collapseScoreFailureRowsByEvidence(uniqueRows)));
  const criticalRows = orderedRows.filter((row) => row?.critical);
  const regularRows = orderedRows.filter((row) => !row?.critical);
  return [...criticalRows, ...regularRows].slice(0, 12);
}
function scoreFailureCategoryLabel(label = "") {
  const text = String(label || "").replace(/\s+\([^)]*\)\s*$/g, "").trim();
  if (!text || /^Score cap:/i.test(text) || /^Benchmark Failure/i.test(text)) return "";
  const first = text.split("/")[0].trim();
  return first && first.length < text.length ? first : "";
}
function scoreFailureRootLabel(label = "") {
  const text = String(label || "").replace(/\s+\([^)]*\)\s*$/g, "").trim();
  if (!text || /^Score cap:/i.test(text) || /^Benchmark Failure/i.test(text)) return "";
  return (text.split("/")[0] || text).trim();
}
function scoreFailureDetailLabel(label = "") {
  const text = String(label || "").replace(/\s+\([^)]*\)\s*$/g, "").trim();
  if (!text) return "";
  const parts = text.split("/").map((part) => part.trim()).filter(Boolean);
  return parts.length > 1 ? parts.slice(1).join(" / ") : parts[0] || "";
}
function scoreFailurePrimaryEvidenceKey(row = {}) {
  const evidence = Array.isArray(row?.evidence) ? row.evidence : [];
  const item = evidence
    .map((value) => String(value || "").trim().replaceAll("\\", "/").replace(/^\/+/, ""))
    .find((value) => /\.(json|log|txt|md)$/i.test(value));
  if (!item) return "";
  return item.replace(/^artifacts\//i, "").toLowerCase();
}
function mergeScoreFailureEvidence(rows = []) {
  const seen = new Set();
  const output = [];
  rows.forEach((row) => {
    (Array.isArray(row.evidence) ? row.evidence : []).forEach((item) => {
      const value = String(item || "").trim();
      if (!value || seen.has(value)) return;
      seen.add(value);
      output.push(value);
    });
  });
  return output.slice(0, 6);
}
function collapseScoreFailureRowsByEvidence(rows = []) {
  const groups = new Map();
  const order = [];
  rows.forEach((row) => {
    const key = scoreFailurePrimaryEvidenceKey(row);
    if (!key) {
      order.push({ row });
      return;
    }
    if (!groups.has(key)) {
      groups.set(key, []);
      order.push({ key });
    }
    groups.get(key).push(row);
  });
  return order.flatMap((entry) => {
    if (entry.row) return [entry.row];
    const items = groups.get(entry.key) || [];
    if (items.length <= 1) return items;
    const labels = [...new Set(items.map((row) => scoreFailureRootLabel(row.label) || row.label).filter(Boolean))];
    const reasonParts = items
      .map((row) => {
        const label = scoreFailureDetailLabel(row.label) || scoreFailureRootLabel(row.label) || row.label || "Finding";
        const reason = scoreSummaryUsefulFailureText(row.reason);
        return reason ? `${label}: ${reason}` : "";
      })
      .filter(Boolean);
    const visibleReasonParts = reasonParts.slice(0, 4);
    if (reasonParts.length > visibleReasonParts.length) {
      visibleReasonParts.push(`${reasonParts.length - visibleReasonParts.length} additional findings share ${entry.key}.`);
    }
    const recommendation =
      items.map((row) => scoreSummaryUsefulFailureText(row.recommendation)).find(Boolean) ||
      "Compare the shared artifact against nearby scored presets, then retest only the affected stage.";
    return [{
      label: `${labels.join(" + ")} (${items.length} findings)`,
      reason: visibleReasonParts.length
        ? visibleReasonParts.join(" ")
        : `${items.length} findings share the same benchmark artifact.`,
      reason_lines: visibleReasonParts,
      recommendation,
      evidence: mergeScoreFailureEvidence(items),
      critical: items.some((row) => row?.critical),
    }];
  });
}
function collapseScoreFailureRowsByCategory(rows = []) {
  const groups = new Map();
  const passthrough = [];
  rows.forEach((row) => {
    const category = scoreFailureCategoryLabel(row?.label);
    if (!category) {
      passthrough.push(row);
      return;
    }
    if (!groups.has(category)) groups.set(category, []);
    groups.get(category).push(row);
  });
  const collapsed = [];
  groups.forEach((items, category) => {
    if (items.length === 1) {
      collapsed.push(items[0]);
      return;
    }
    const reasonExamples = [
      ...new Set(items.map((row) => scoreSummaryUsefulFailureText(row.reason)).filter(Boolean)),
    ].slice(0, 2);
    const recommendation =
      items.map((row) => scoreSummaryUsefulFailureText(row.recommendation)).find(Boolean) ||
      scoreSummaryFailureRecommendation({ category }, category);
    collapsed.push({
      label: `${category} (${items.length} findings)`,
      reason: `${items.length} ${category} entries need attention${reasonExamples.length ? `: ${reasonExamples.join(" ")}` : "."}`,
      recommendation,
      evidence: mergeScoreFailureEvidence(items),
      critical: items.some((row) => row?.critical),
    });
  });
  return [...passthrough, ...collapsed];
}
function renderPresetScoreFailuresCard(result = {}) {
  const failures = collectPresetScoreFailures(result);
  if (!failures.length) return "";
  const recommendationCounts = new Map();
  failures.forEach((row) => {
    const key = scoreSummaryUsefulFailureText(row.recommendation).toLowerCase();
    if (key) recommendationCounts.set(key, Number(recommendationCounts.get(key) || 0) + 1);
  });
  const sharedRecommendations = [];
  const sharedSeen = new Set();
  const rows = failures
    .map((row) => {
      const evidence = renderScoreEvidenceLinks(result, row.evidence);
      const excerpt = row.excerpt ? `<code>${escapeHtml(row.excerpt)}</code>` : "";
      const recommendationKey = scoreSummaryUsefulFailureText(row.recommendation).toLowerCase();
      const shared = recommendationKey && Number(recommendationCounts.get(recommendationKey) || 0) > 1;
      if (shared && !sharedSeen.has(recommendationKey)) {
        sharedSeen.add(recommendationKey);
        sharedRecommendations.push(row.recommendation);
      }
      const recommendation = row.recommendation && !shared ? `<em>${escapeHtml(row.recommendation)}</em>` : "";
      const reason = Array.isArray(row.reason_lines) && row.reason_lines.length
        ? `<div class="score-summary-reason-lines">${row.reason_lines.map((line) => `<span>${escapeHtml(line)}</span>`).join("")}</div>`
        : `<span>${escapeHtml(row.reason)}</span>`;
      return `<li><strong>${escapeHtml(row.label)}</strong>${reason}${recommendation}${evidence}${excerpt}</li>`;
    })
    .join("");
  const sharedHtml = sharedRecommendations.length
    ? `<div class="score-summary-shared-recs"><strong>Shared next step</strong>${sharedRecommendations.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>`
    : "";
  return `<details class="score-summary-failures" open><summary><span>Failures</span><span>${failures.length}</span></summary><ul>${rows}</ul>${sharedHtml}</details>`;
}
function renderPresetScoreSummaryCard(result = {}) {
  const composite = result.composite || {};
  const caps = Array.isArray(composite.caps_applied)
    ? composite.caps_applied
    : Array.isArray(result?.caps_applied)
      ? result.caps_applied
      : [];
  const capHtml = caps.length
    ? `<div class="score-summary-caps">${caps.map((cap) => `<span>${escapeHtml(cap.id || "cap")} ≤ ${escapeHtml(formatModelScoreValue(cap.cap))}</span>`).join("")}</div>`
    : '<div class="preset-help">No failure caps were applied.</div>';
  return `<div class="score-summary-card" id="presetScoreSummaryCard"><div class="score-summary-title-row"><h3>Summary</h3></div><div class="preset-help">${escapeHtml(result.summary || "No summary captured.")}</div>${capHtml}${renderPresetScoreFailuresCard(result)}</div>`;
}
function renderPresetScoresModal() {
  ensurePresetScoresModal();
  const body = $("presetScoresBody");
  if (!body) return;
  rememberPresetScoreLogScroll();
  const detailSnapshot = capturePresetScoreDetailsUiState() || modelScoreDetailsUiState;
  const key = String(modelScoreDetailState.selector || "");
  const running = benchmarkRunningForSelector(key);
  const rawResult = modelScoreDetailState.result || { selector: key, display_name: key, status: "missing", metrics: {} };
  const matchingVariant = findVariantBySelector(key) || {};
  const selectedMode = modelScoreSelectedMode(rawResult);
  const result = modelScoreSelectedResult(rawResult);
  const detailComparison = modelScoreDetailComparison(result);
  const safetyBadge = variantUncensoredBadgeHtml({ ...matchingVariant, ...rawResult, ...result });
  const hasScore = modelScoreComplete(result);
  const mode = String(result.mode || "").toUpperCase();
  const comparisons = loadModelScoreComparisons();
  const inComparison = comparisonHasSelector(key);
  const benchmarkLocked = benchmarkJobActive();
  const statusLine = modelScoreDetailState.loading
    ? "Loading score details..."
    : modelScoreDetailState.error
      ? modelScoreDetailState.error
      : running
        ? benchmarkStepLine(running, Math.round(normalizeBenchmarkProgress(running.step_progress) * 100))
        : hasScore
          ? `${mode || "SCORED"} · ${result.finished_at || ""}`
          : "No saved score.";
  const failedScore = hasScore && (String(result.status || "").toLowerCase() === "failed" || !!result.failure);
  const retryMode = String(result.mode || "full").toLowerCase() === "quick" ? "quick" : "full";
  const actionButtons = [
    failedScore || !hasScore
      ? renderIconButton({
          title: failedScore ? "Retry Benchmark" : "Benchmark Preset",
          action: `startBenchmarkPreset('${escapeJs(key)}','${escapeJs(failedScore ? retryMode : "quick")}')`,
          icon: failedScore ? "reset" : "plus",
          className: "score-icon-action",
          disabled: benchmarkLocked,
        })
      : "",
    hasScore
      ? renderIconButton({
          title: "Clear Scores",
          action: `clearBenchmarkScore('${escapeJs(key)}')`,
          icon: "delete",
          className: "score-icon-action",
          disabled: benchmarkLocked,
        })
      : "",
    modelScoreDetailState.view === "logs"
      ? renderIconButton({ title: "Show Scores", action: "showPresetScoreChart()", icon: "percent", className: "score-icon-action" })
      : renderIconButton({ title: "Show Logs", action: "showPresetScoreLogs()", icon: "file", className: "score-icon-action" }),
  ].filter(Boolean).join("");
  const comparisonButtons = [
    hasScore
      ? inComparison
        ? renderIconButton({ title: "Remove from Comparison", action: "removeCurrentScoreFromComparison()", icon: "minus", className: "score-icon-action" })
        : renderIconButton({ title: "Add to Comparison", action: "addCurrentScoreToComparison()", icon: "plus", className: "score-icon-action" })
      : "",
    comparisons.length
      ? renderIconButton({ title: "Clear Comparisons", action: "clearScoreComparisons()", icon: "close", className: "score-icon-action" })
      : "",
  ].filter(Boolean).join("");
  const logView = modelScoreDetailState.view === "logs";
  const activeLogPathLabel = logView ? renderActiveLogPathLabel(presetScoreSelectedLogPath(result)) : renderActiveLogPathLabel("");
  const content = modelScoreDetailState.loading
    ? '<div class="empty-variant-note">Loading...</div>'
    : logView
      ? renderPresetScoreLogViewer(result)
      : `<div class="score-modal-score-stack">${renderModelScoreRadar(result)}<div class="score-details-card"><div class="score-details-title-row"><span>Details</span></div><div class="score-breakdown-masonry">${renderModelScoreBreakdown(result, detailComparison)}</div></div></div>`;
  const showSummaryAside = !logView && !modelScoreDetailState.loading && !modelScoreDetailState.error;
  body.innerHTML = `<div class="score-modal-summary"><div><div class="score-modal-preset-line">${renderModelScorePassFailBadge(rawResult)}<div class="score-modal-preset">${escapeHtml(modelScoreDisplayName(result))}</div>${safetyBadge}</div><div class="preset-help score-modal-meta">${escapeHtml(statusLine)}</div></div>${renderModelScoreTopScores(rawResult, selectedMode)}</div><div class="score-modal-actions-row"><div class="score-modal-actions-primary">${actionButtons}</div>${activeLogPathLabel}<div class="score-modal-actions-comparison">${comparisonButtons}</div></div><div class="score-modal-layout${showSummaryAside ? " score-modal-layout-with-summary" : ""}${logView ? " score-modal-layout-log" : ""}"><main class="score-modal-main">${content}</main>${showSummaryAside ? `<aside class="score-modal-aside">${renderPresetScoreSummaryCard(result)}</aside>` : ""}</div>`;
  if (!logView) {
    restorePresetScoreDetailsUiState(detailSnapshot);
    modelScoreDetailsUiState = capturePresetScoreDetailsUiState() || detailSnapshot || modelScoreDetailsUiState;
  } else {
    const restoreLog = () => restorePresetScoreLogScroll();
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(restoreLog);
    else restoreLog();
  }
}
function ensureRunScriptModal() {
  if ($("runScriptModal")) return;
  const modal = document.createElement("div");
  modal.id = "runScriptModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card run-script-modal-card" role="dialog" aria-modal="true" aria-labelledby="runScriptTitle"><div class="panel-head"><h2 id="runScriptTitle">Run Script</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeRunScriptModal()">✕</button></div><div id="runScriptBody"></div><div class="msg" id="runScriptMsg"></div></div>`;
  document.body.appendChild(modal);
}
function openRunScriptModal() {
  ensureRunScriptModal();
  $("runScriptModal").classList.remove("hidden");
  renderRunScriptModal();
  loadRunScripts().catch(() => {});
}
function closeRunScriptModal() {
  ensureRunScriptModal();
  $("runScriptModal").classList.add("hidden");
}
async function loadRunScripts() {
  scriptModalState.loading = true;
  scriptModalState.error = "";
  renderRunScriptModal();
  try {
    const internalParam = scriptModalState.showInternal ? "&include_internal=1" : "";
    const response = await fetchJsonWithTimeout(`/admin/scripts?_=${Date.now()}${internalParam}`, { cache: "no-store" }, 12000);
    const payload = await response.json();
    if (!response.ok || payload?.ok === false) throw new Error(payload?.error || "Script discovery failed.");
    scriptModalState.scripts = Array.isArray(payload.scripts) ? payload.scripts : [];
    if (payload.job) lastStatus = { ...(lastStatus || {}), script_job: payload.job };
    const queue = Array.isArray(payload?.job?.queue) ? payload.job.queue : [];
    if (!scriptModalState.selectedJobId && queue.length) {
      scriptModalState.selectedJobId = String((queue.find((row) => row?.status === "running") || queue[queue.length - 1])?.job_id || "");
    }
  } catch (error) {
    scriptModalState.error = messageText(error);
  } finally {
    scriptModalState.loading = false;
    renderRunScriptModal();
  }
}
function setRunScriptsInternalVisible(checked) {
  scriptModalState.showInternal = !!checked;
  loadRunScripts().catch(() => {});
  renderRunScriptModal();
}
function toggleRunScriptLogView() {
  scriptModalState.view = scriptModalState.view === "logs" ? "scripts" : "logs";
  if (scriptModalState.view === "logs") {
    const queue = scriptQueueRows();
    if (!scriptModalState.selectedJobId && queue.length) {
      scriptModalState.selectedJobId = String((queue.find((row) => row?.status === "running") || queue[queue.length - 1])?.job_id || "");
    }
    if (scriptModalState.selectedJobId) loadRunScriptLog(scriptModalState.selectedJobId).catch(() => {});
  }
  renderRunScriptModal();
}
function toggleScriptOptions(scriptId) {
  scriptModalState.expandedOptions = scriptModalState.expandedOptions === scriptId ? "" : scriptId;
  renderRunScriptModal();
}
function setScriptArgs(scriptId, value) {
  scriptModalState.argsById[String(scriptId || "")] = String(value || "");
}
function openScriptDoc(rootPath, relativePath) {
  if (typeof openStorageBrowserFileReadOnly === "function") {
    openStorageBrowserFileReadOnly(rootPath, relativePath);
  } else {
    alert("File Editor is not available yet.");
  }
}
async function startDiscoveredScript(scriptId) {
  if (benchmarkJobActive()) {
    setElementMsg("runScriptMsg", "Scripts cannot be run while a Model Scores benchmark is active.", "warning");
    return;
  }
  try {
    const payload = await post(
      "/admin/scripts/run",
      {
        script_id: scriptId,
        args: scriptModalState.argsById[String(scriptId || "")] || "",
        instance_id: currentScope() || "GLOBAL",
      },
      `/admin/scripts/run ${scriptId}`,
    );
    if (payload.script_job) lastStatus = { ...(lastStatus || {}), script_job: payload.script_job };
    const queue = Array.isArray(payload?.script_job?.queue) ? payload.script_job.queue : [];
    const added = queue[queue.length - 1];
    if (added?.job_id) scriptModalState.selectedJobId = String(added.job_id);
    renderRunScriptModal();
  } catch (error) {
    setElementMsg("runScriptMsg", messageText(error), "error");
  }
}
async function startImageStudioSetup() {
  if (benchmarkJobActive()) {
    alert("AI Studio setup cannot run while a Model Scores benchmark is active.");
    return;
  }
  try {
    ensureRunScriptModal();
    $("runScriptModal").classList.remove("hidden");
    scriptModalState.view = "logs";
    const payload = await post(
      "/admin/ai-studio/setup",
      {},
      "/admin/ai-studio/setup",
    );
    if (payload.script_job) lastStatus = { ...(lastStatus || {}), script_job: payload.script_job };
    const queue = Array.isArray(payload?.script_job?.queue) ? payload.script_job.queue : [];
    const added = queue[queue.length - 1];
    if (added?.job_id) {
      scriptModalState.selectedJobId = String(added.job_id);
      loadRunScriptLog(scriptModalState.selectedJobId, true).catch(() => {});
    }
    renderRunScriptModal();
    setElementMsg("runScriptMsg", "AI Studio setup queued. Output is streaming to the Script Queue and Audit Logs.", "success");
  } catch (error) {
    setElementMsg("runScriptMsg", messageText(error), "error");
  }
}
async function removeImageStudio() {
  if (benchmarkJobActive()) {
    alert("AI Studio removal cannot run while a Model Scores benchmark is active.");
    return;
  }
  try {
    ensureRunScriptModal();
    $("runScriptModal").classList.remove("hidden");
    scriptModalState.view = "logs";
    const payload = await post(
      "/admin/ai-studio/remove",
      {},
      "/admin/ai-studio/remove",
    );
    if (payload.script_job) lastStatus = { ...(lastStatus || {}), script_job: payload.script_job };
    const queue = Array.isArray(payload?.script_job?.queue) ? payload.script_job.queue : [];
    const added = queue[queue.length - 1];
    if (added?.job_id) {
      scriptModalState.selectedJobId = String(added.job_id);
      loadRunScriptLog(scriptModalState.selectedJobId, true).catch(() => {});
    }
    renderRunScriptModal();
    setElementMsg("runScriptMsg", "AI Studio removal queued. Downloaded models are left in place for Model Manager cleanup.", "success");
  } catch (error) {
    setElementMsg("runScriptMsg", messageText(error), "error");
  }
}
function aiStudioServiceInstalled() {
  const serviceIds = new Set(["comfyui"]);
  return (lastStatus?.upstream_services || []).some((row) => {
    const id = String(row?.id || "").trim().toLowerCase();
    return serviceIds.has(id) && (!!row?.exists || !!row?.running);
  });
}
function aiStudioSetupBusy() {
  return !!(lastStatus?.script_job?.queue || []).some((job) => {
    const id = String(job?.script_id || "");
    const status = String(job?.status || "");
    return ["setup-ai-studio", "remove-ai-studio", "start-ai-studio", "stop-ai-studio"].includes(id) && !["success", "failed", "cancelled"].includes(status);
  });
}
function imageStudioActionIconSvg() {
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 17l4.5-5 3.5 4 2-2.5 6 7H4zM6 5h12v9" fill="none" /><circle cx="9" cy="8" r="1.5" fill="currentColor" /></svg>`;
}
function imageStudioActionButtonHtml(className = "btn run-script-trigger") {
  const installed = aiStudioServiceInstalled();
  const busy = aiStudioSetupBusy();
  const label = busy
    ? (installed ? "Removing AI Studio" : "Setup Running")
    : (installed ? "Remove AI Studio" : "Setup AI Studio");
  const action = installed ? "removeImageStudio()" : "startImageStudioSetup()";
  const baseClass = installed ? String(className || "").replace(/\bgreen\b/g, "").replace(/\s+/g, " ").trim() : className;
  const tone = installed ? " red" : "";
  return `<button class="${escapeHtml(`${baseClass}${tone}`.trim())}" ${busy ? "disabled" : ""} onclick="${action}">${imageStudioActionIconSvg()}<span>${escapeHtml(label)}</span></button>`;
}
async function setImageStudioRuntime(start) {
  try {
    $("runScriptModal").classList.remove("hidden");
    scriptModalState.view = "logs";
    const route = start ? "/admin/ai-studio/start" : "/admin/ai-studio/stop";
    const payload = await post(route, {}, route);
    if (payload.script_job) lastStatus = { ...(lastStatus || {}), script_job: payload.script_job };
    const queue = Array.isArray(payload?.script_job?.queue) ? payload.script_job.queue : [];
    const added = queue[queue.length - 1];
    if (added?.job_id) {
      scriptModalState.selectedJobId = String(added.job_id);
      loadRunScriptLog(scriptModalState.selectedJobId, true).catch(() => {});
    }
    renderRunScriptModal();
    setElementMsg("runScriptMsg", `AI Studio ${start ? "start" : "stop"} queued.`, "success");
  } catch (error) {
    setElementMsg("runScriptMsg", messageText(error), "error");
  }
}
function imageStudioRuntimeButtonHtml() {
  if (!aiStudioServiceInstalled()) return "";
  const busy = aiStudioSetupBusy();
  const running = !!lastStatus?.ai_studio?.ready;
  const label = busy ? "AI Studio Busy" : (running ? "Stop AI Studio" : "Start AI Studio");
  return `<button class="btn ${running ? "rose" : "green"}" ${busy ? "disabled" : ""} onclick="setImageStudioRuntime(${running ? "false" : "true"})"><span>${escapeHtml(label)}</span></button>`;
}
function toggleAIStudioGallery(event) {
  if (event?.preventDefault) event.preventDefault();
  aiStudioGalleryState = {
    ...(aiStudioGalleryState || {}),
    open: !aiStudioGalleryState.open,
  };
  if (aiStudioGalleryState.open) {
    aiStudioGalleryState.error = "";
    renderDynamicPresetModels({ force: true });
    window.setTimeout(() => refreshAIStudioGallery({ force: true }).catch(() => {}), 0);
    return false;
  }
  renderDynamicPresetModels({ force: true });
  return false;
}
function imageStudioGalleryButtonHtml() {
  if (!aiStudioServiceInstalled()) return "";
  const pressed = !!aiStudioGalleryState.open;
  return `<button type="button" class="btn blue ai-studio-gallery-toggle${pressed ? " active" : ""}" aria-pressed="${pressed ? "true" : "false"}" onclick="return toggleAIStudioGallery(event)">${svgIcon("album")}<span>Gallery</span></button>`;
}
function scriptQueueRows() {
  const job = lastStatus?.script_job || {};
  if (Array.isArray(job.queue)) return job.queue.filter((row) => row && row.job_id);
  return job.job_id ? [job] : [];
}
async function loadRunScriptLog(jobId, force = false) {
  const id = String(jobId || "").trim();
  if (!id || scriptModalState.logLoadingJob === id) return;
  const loadedAt = Number(scriptModalState.logLoadedAtByJob[id] || 0);
  if (!force && Date.now() - loadedAt < 1200) return;
  scriptModalState.logLoadingJob = id;
  try {
    const response = await fetchJsonWithTimeout(`/admin/scripts/log?job_id=${encodeURIComponent(id)}&tail=500&_=${Date.now()}`, { cache: "no-store" }, 12000);
    const payload = await response.json();
    if (!response.ok || payload?.ok === false) throw new Error(payload?.error || "Script log request failed.");
    scriptModalState.logByJob[id] = String(payload?.text || "");
    scriptModalState.logLoadedAtByJob[id] = Date.now();
  } catch (error) {
    scriptModalState.error = messageText(error);
  } finally {
    if (scriptModalState.logLoadingJob === id) scriptModalState.logLoadingJob = "";
    renderRunScriptModal();
  }
}
function showQueuedScriptLog(jobId) {
  scriptModalState.selectedJobId = String(jobId || "");
  scriptModalState.view = "logs";
  renderRunScriptModal();
  loadRunScriptLog(scriptModalState.selectedJobId, true).catch(() => {});
}
async function removeQueuedScript(jobId) {
  const id = String(jobId || "").trim();
  const row = scriptQueueRows().find((item) => String(item?.job_id || "") === id);
  if (!row) return;
  const running = String(row.status || "") === "running";
  const prompt = running
    ? `Terminate ${row.label || row.script_id || "this script"} immediately and remove it from the queue?`
    : `Remove ${row.label || row.script_id || "this script"} from the queue?`;
  if (!confirm(prompt)) return;
  try {
    const payload = await post("/admin/scripts/remove", { job_id: id }, `/admin/scripts/remove ${id}`);
    if (payload.script_job) lastStatus = { ...(lastStatus || {}), script_job: payload.script_job };
    delete scriptModalState.logByJob[id];
    delete scriptModalState.logLoadedAtByJob[id];
    if (scriptModalState.selectedJobId === id) {
      const queue = Array.isArray(payload?.script_job?.queue) ? payload.script_job.queue : [];
      scriptModalState.selectedJobId = String((queue.find((item) => item?.status === "running") || queue[queue.length - 1])?.job_id || "");
      if (!scriptModalState.selectedJobId) scriptModalState.view = "scripts";
    }
    renderRunScriptModal();
  } catch (error) {
    setElementMsg("runScriptMsg", messageText(error), "error");
  }
}
function renderScriptCard(row) {
  const id = String(row?.id || "");
  const optionsOpen = scriptModalState.expandedOptions === id;
  const options = Array.isArray(row?.options) ? row.options : [];
  const docs = Array.isArray(row?.docs) ? row.docs : [];
  const args = scriptModalState.argsById[id] || "";
  const locked = benchmarkJobActive();
  const queueBusy = scriptQueueRows().some((item) => ["queued", "running"].includes(String(item?.status || "")));
  const optionsHtml = optionsOpen
    ? `<div class="script-options-panel">${options.length ? options.map((opt) => `<div class="script-option-row"><code>${escapeHtml(opt.name || "")}</code><span>${escapeHtml(opt.description || "")}</span></div>`).join("") : '<div class="preset-help">No switches were detected in this script.</div>'}</div>`
    : "";
  const docsHtml = docs.length
    ? `<button class="script-help-btn script-info-btn" title="More Info" aria-label="More Info" onclick="openScriptDoc('${escapeJs(docs[0].root_path || "")}','${escapeJs(docs[0].relative_path || "")}')">i</button>`
    : "";
  const internalBadge = row?.internal ? '<span class="status-badge status-warning">internal</span>' : "";
  return `<div class="run-script-card resource-manager-card"><div class="resource-manager-card-head"><div class="resource-manager-card-subrow"><div><h3>${escapeHtml(row?.label || row?.name || id)}</h3><div class="preset-help"><code>${escapeHtml(id)}</code></div></div><div class="script-card-controls">${internalBadge}${docsHtml}<button class="script-help-btn" title="Options" aria-label="Show script options" onclick="toggleScriptOptions('${escapeJs(id)}')">?</button></div></div><div class="preset-help">${escapeHtml(row?.description || "Upstream script.")}</div></div><label class="script-args-row">Arguments<input value="${escapeHtml(args)}" placeholder="optional switches or values" oninput="setScriptArgs('${escapeJs(id)}', this.value)" /></label><div class="resource-manager-card-actions"><button class="btn green" ${locked ? "disabled" : ""} onclick="startDiscoveredScript('${escapeJs(id)}')">${queueBusy ? "Enqueue" : "Run"}</button></div>${optionsHtml}</div>`;
}
function renderScriptQueueRow(row, index) {
  const jobId = String(row?.job_id || "");
  const status = String(row?.status || "queued").toLowerCase();
  const selected = scriptModalState.selectedJobId === jobId;
  const label = String(row?.label || row?.script_id || `Script ${index + 1}`);
  const args = String(row?.command || "").replace(/^(?:bash|python3)\s+\S+\s*/, "").trim();
  const progress = Math.round(Math.max(0, Math.min(1, Number(row?.progress ?? (status === "running" ? 0.5 : ["success", "failed", "cancelled"].includes(status) ? 1 : 0)))) * 100);
  const logButton = renderIconButton({ title: `View ${label} Logs`, action: `showQueuedScriptLog('${escapeJs(jobId)}')`, icon: "terminal", className: "run-script-queue-log" });
  const removeButton = renderIconButton({ title: status === "running" ? `Terminate and Remove ${label}` : `Remove ${label}`, action: `removeQueuedScript('${escapeJs(jobId)}')`, icon: "close", className: "run-script-queue-remove" });
  return `<div class="run-script-queue-row ${escapeHtml(status)}${selected ? " focused" : ""}" data-script-job-id="${escapeHtml(jobId)}"><span class="status-badge status-${status === "success" ? "success" : status === "failed" || status === "cancelled" ? "danger" : status === "running" ? "warning" : "info"}">${escapeHtml(status)}</span><div class="run-script-queue-main"><strong>${escapeHtml(label)}</strong><code>${escapeHtml(row?.script_id || "")}</code>${args ? `<span>${escapeHtml(args)}</span>` : ""}<div class="run-script-queue-progress"><i style="width:${progress}%"></i><span>Progress ${progress}%</span></div></div><div class="run-script-queue-actions">${logButton}${removeButton}</div></div>`;
}
function renderRunScriptModal() {
  ensureRunScriptModal();
  const body = $("runScriptBody");
  if (!body) return;
  const previousLogViewer = body.querySelector(".run-script-log-viewer");
  const shouldFollowScriptLog =
    !!$("autoscroll")?.checked &&
    (!previousLogViewer ||
      previousLogViewer.scrollHeight - (previousLogViewer.scrollTop + previousLogViewer.clientHeight) <= 28);
  const job = lastStatus?.script_job || {};
  const queue = scriptQueueRows();
  const locked = benchmarkJobActive();
  const scripts = Array.isArray(scriptModalState.scripts) ? scriptModalState.scripts : [];
  const userScripts = scripts.filter((row) => !row?.internal);
  const internalScripts = scripts.filter((row) => row?.internal);
  const cards = scriptModalState.loading
    ? '<div class="empty-variant-note">Discovering upstream scripts...</div>'
    : userScripts.length
      ? userScripts.map((row) => renderScriptCard(row)).join("")
      : '<div class="empty-variant-note">No user-facing shell scripts were discovered.</div>';
  const internalSection = scriptModalState.showInternal
    ? `<section class="run-script-internal-card resource-manager-card"><div class="resource-manager-card-head"><h3>Internal Backend Scripts</h3><div class="preset-help">These are backend plumbing scripts exposed only for explicit maintenance runs.</div></div><div class="run-script-grid resource-manager-grid">${scriptModalState.loading ? '<div class="empty-variant-note">Discovering internal scripts...</div>' : internalScripts.length ? internalScripts.map((row) => renderScriptCard(row)).join("") : '<div class="empty-variant-note">No internal backend scripts were discovered.</div>'}</div></section>`
    : "";
  const running = queue.find((row) => row?.status === "running");
  const queuedCount = queue.filter((row) => row?.status === "queued").length;
  const queueRows = queue.length ? queue.map((row, index) => renderScriptQueueRow(row, index)).join("") : '<div class="empty-variant-note">No scripts queued.</div>';
  const queueSummary = running ? `${running.label || running.script_id || "Script"} running${queuedCount ? ` · ${queuedCount} queued` : ""}` : queuedCount ? `${queuedCount} queued` : `${queue.length} retained result${queue.length === 1 ? "" : "s"}`;
  const selectedJob = queue.find((row) => String(row?.job_id || "") === scriptModalState.selectedJobId) || running || queue[queue.length - 1] || {};
  const selectedJobId = String(selectedJob?.job_id || "");
  if (!scriptModalState.selectedJobId && selectedJobId) scriptModalState.selectedJobId = selectedJobId;
  const selectedLog = String(scriptModalState.logByJob[selectedJobId] || (selectedJobId === String(job.job_id || "") && Array.isArray(job.log_tail) ? job.log_tail.slice(-500).join("\n") : ""));
  const logToggle = renderIconButton({ title: scriptModalState.view === "logs" ? "Show Scripts" : "View Logs", action: "toggleRunScriptLogView()", icon: scriptModalState.view === "logs" ? "chevron-left" : "terminal", className: "benchmark-run-toggle run-script-log-toggle" });
  const scriptControls = `<div class="benchmark-actions"><label class="script-internal-toggle"><input type="checkbox" ${scriptModalState.showInternal ? "checked" : ""} onchange="setRunScriptsInternalVisible(this.checked)" />Display internal backend scripts</label></div>`;
  const scriptsView = `<div class="run-script-grid resource-manager-grid">${cards}</div>${internalSection}`;
  const logsView = `<div class="run-script-selected-log"><div class="resource-manager-card-head"><h3>${escapeHtml(selectedJob?.label || selectedJob?.script_id || "Script Log")}</h3><span class="run-script-status-label">${escapeHtml(selectedJob?.status || "idle")}</span></div><pre class="benchmark-log-tail run-script-log-viewer" tabindex="0">${escapeHtml(selectedLog || (scriptModalState.logLoadingJob === selectedJobId ? "Loading script log..." : "No script log entries yet."))}</pre></div>`;
  const queueCard = `<section class="run-script-queue-card resource-manager-card"><div class="resource-manager-card-head"><div><h3>Script Queue</h3><div class="preset-help">${escapeHtml(queueSummary)}</div></div><span class="benchmark-ready-controls run-script-ready-controls">${logToggle}</span></div><div class="run-script-queue">${queueRows}</div></section>`;
  body.innerHTML = `${queueCard}<div class="preset-help">${locked ? "Scripts cannot be run during a Model Scores benchmark, but discovery and logs remain available." : "Scripts run sequentially against the selected scope when a runtime is available."}</div>${scriptControls}${scriptModalState.view === "logs" ? logsView : scriptsView}`;
  const nextLogViewer = body.querySelector(".run-script-log-viewer");
  if (nextLogViewer && shouldFollowScriptLog) nextLogViewer.scrollTop = nextLogViewer.scrollHeight;
  if (scriptModalState.view === "logs" && selectedJobId && (String(selectedJob?.status || "") === "running" || !scriptModalState.logByJob[selectedJobId])) {
    loadRunScriptLog(selectedJobId).catch(() => {});
  }
  if (scriptModalState.error) setElementMsg("runScriptMsg", scriptModalState.error, "error");
}
function renderBenchmarkSurfaces() {
  hydrateBenchmarkFloatingState();
  if (benchmarkModalOpenPersisted && !benchmarkModalCollapsed) {
    ensureBenchmarkAllModal();
    $("benchmarkAllModal").classList.remove("hidden");
    applyBenchmarkModalPosition();
  }
  const modal = $("benchmarkAllModal");
  const modalOpen = !!modal && !modal.classList.contains("hidden");
  if (modalOpen) {
    const staleMini = $("benchmarkMiniWindow");
    if (staleMini) staleMini.remove();
    benchmarkModalCollapsed = false;
    renderBenchmarkAllModal();
    scheduleBenchmarkModalSnapshotRefresh();
    return;
  }
  if (benchmarkModalCollapsed || $("benchmarkMiniWindow")) {
    renderBenchmarkMiniWindow();
    if ($("benchmarkMiniWindow")) scheduleBenchmarkModalSnapshotRefresh();
  }
  if ($("presetScoresModal") && !$("presetScoresModal").classList.contains("hidden")) {
    renderPresetScoresModal();
    refreshPresetScoresModalDetailFromStatus().catch(() => {});
  }
  if ($("runScriptModal") && !$("runScriptModal").classList.contains("hidden")) renderRunScriptModal();
}
function handleBenchmarkJobTransition(previousStatus = {}, nextStatus = {}) {
  const previousJob = previousStatus?.benchmarks?.job || {};
  const nextJob = nextStatus?.benchmarks?.job || {};
  if (!previousJob.active && nextJob.active) {
    const modal = $("benchmarkAllModal");
    const modalOpen = !!modal && !modal.classList.contains("hidden");
    if (!modalOpen) {
      hydrateBenchmarkFloatingState();
      benchmarkModalCollapsed = true;
      benchmarkMiniHidden = false;
      persistBenchmarkFloatingState();
      renderBenchmarkMiniWindow();
    }
  }
  const jobId = String(nextJob.job_id || "");
  if (
    !previousJob.active ||
    nextJob.active ||
    String(nextJob.status || "") !== "complete" ||
    !jobId ||
    String(previousJob.job_id || "") !== jobId
  ) {
    return;
  }
  const key = `${jobId}:${nextJob.finished_at || ""}`;
  if (key === lastBenchmarkNotificationKey) return;
  lastBenchmarkNotificationKey = key;
  const mode = String(nextJob.mode || "benchmark");
  const summary = String(nextJob.summary || "").trim();
  showBrowserNotification(
    "Benchmarks Complete",
    summary || `${mode.charAt(0).toUpperCase()}${mode.slice(1)} benchmark queue completed.`,
  ).catch(() => {});
}
const tabScrollPositions = window.club3090TabScrollPositions || (window.club3090TabScrollPositions = Object.create(null));
function currentPageScrollTop() {
  return Math.max(
    0,
    Number(window.scrollY || 0),
    Number(document.documentElement?.scrollTop || 0),
    Number(document.body?.scrollTop || 0),
  );
}
function rememberTabScrollPosition(name = activeTabName) {
  const key = normalizeTabName(name);
  tabScrollPositions[key] = currentPageScrollTop();
}
function persistCurrentTabPosition() {
  rememberTabScrollPosition(activeTabName);
  const state = currentUiState();
  writeUiStateToLocationHash(state);
  writeUiStateToLocationSearch(state);
  lastQueuedUiStateJson = JSON.stringify(state);
  writeCachedUiState(state);
  queueUiStateSave();
}
function restoreTabScrollPosition(name = activeTabName) {
  const key = normalizeTabName(name);
  const top = Math.max(0, Number(tabScrollPositions[key] || 0));
  const restore = () => {
    const userAgent = String(navigator?.userAgent || "").toLowerCase();
    if (userAgent.includes("jsdom") || typeof window.scrollTo !== "function") {
      document.documentElement.scrollTop = top;
      document.body.scrollTop = top;
      return;
    }
    try {
      window.scrollTo({ top, left: 0, behavior: "auto" });
    } catch (error) {
      try {
        window.scrollTo(0, top);
      } catch (fallbackError) {
        document.documentElement.scrollTop = top;
        document.body.scrollTop = top;
      }
    }
  };
  if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => requestAnimationFrame(restore));
  else setTimeout(restore, 0);
}
function activateTab(name, firstRender = false) {
  const requestedTab = normalizeTabName(name);
  if (!uiStateHydrated) hydrateUiState({});
  if (!firstRender && requestedTab !== activeTabName) rememberTabScrollPosition(activeTabName);
  activeTabName = requestedTab;
  writeUiStateToLocationHash(currentUiState());
  writeUiStateToLocationSearch(currentUiState());
  writeCachedUiState(currentUiState());
  logDebugEvent("tab_activate", { name: activeTabName, firstRender: !!firstRender });
  syncActiveTabDisplay();
  connectLogs(false);
  scheduleLogCacheRefresh(logViewerVisible() ? LOG_CACHE_REFRESH_MS : 0);
  if (activeTabName === "metrics") {
    redrawMetricsSoon();
  }
  if (activeTabName === "presets") {
    renderPresetScopeTabs();
    renderModelInstallStatus();
    if (renderCachedDynamicPresetModels()) {
      requestAnimationFrame(() => renderDynamicPresetModels());
    } else {
      renderDynamicPresetModels();
    }
    if (!lastStatus?.runtime_inventory) {
      refreshStatus({ force: true }).catch(() => {});
    }
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
  scheduleStatusPoll(0);
  queueUiStateSave();
  restoreTabScrollPosition(activeTabName);
  setTimeout(() => {
    if (!searchState.active && $("autoscroll").checked && $("log"))
      $("log").scrollTop = $("log").scrollHeight;
  }, 0);
}
tab = function (e, n) {
  activateTab(n, false);
};
window.addEventListener("pagehide", persistCurrentTabPosition);
window.addEventListener("beforeunload", persistCurrentTabPosition);
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
    !!options.includeSeries || tab === "metrics" || popupMetricsWindowOpen();
  const includeInventory =
    !!options.includeInventory || tab === "presets" || tab === "chat";
  const includeBenchmarkDetails =
    !!options.includeBenchmarkDetails;
  return {
    tab,
    hidden: document.hidden && !popupLogWindowActive() ? "1" : "0",
    include_series: includeSeries ? "1" : "0",
    series_limit: includeSeries ? String(options.seriesLimit || STATUS_LIVE_SERIES_LIMIT) : "0",
    include_inventory: includeInventory ? "1" : "0",
    inventory_detail: includeInventory ? String(options.inventoryDetail || "compact") : "compact",
    include_config: "1",
    include_benchmark_details: includeBenchmarkDetails ? "1" : "0",
  };
}
function statusPollDelayMs() {
  if (popupMetricsWindowOpen()) return STATUS_POLL_FOREGROUND_FAST_MS;
  if (popupLogWindowActive()) return STATUS_POLL_FOREGROUND_FAST_MS;
  if (document.hidden) return STATUS_POLL_BACKGROUND_MS;
  if (benchmarkSurfaceOpen() || benchmarkJobActive()) return STATUS_POLL_FOREGROUND_FAST_MS;
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
function statusCacheSavedLabel(savedAt = 0) {
  const stamp = Number(savedAt || 0);
  if (!stamp) return "an unknown time";
  try {
    return new Date(stamp).toLocaleString();
  } catch (e) {
    return "an unknown time";
  }
}
function annotateStatusCache(status = {}, payload = {}, options = {}) {
  const base = status && typeof status === "object" ? { ...status } : {};
  base.__status_cache = {
    cached: true,
    saved_at: Number(payload?.saved_at || options.savedAt || Date.now()),
    series_saved_at: Number(payload?.series_saved_at || 0),
    connecting: !!options.connecting,
    disconnected: !!options.disconnected,
    message: String(options.message || ""),
    reason: String(options.reason || ""),
  };
  return base;
}
function stripStatusCacheMeta(status = {}) {
  if (!status || typeof status !== "object") return status;
  const next = { ...status };
  delete next.__status_cache;
  return next;
}
function renderStatusConnectionBanner(status = lastStatus || {}) {
  const panel = findPanelByHeading("overview", "Status");
  if (!panel) return;
  let banner = $("statusConnectionBanner");
  const meta = status?.__status_cache || {};
  const show = !!meta?.cached;
  if (!show) {
    banner?.remove();
    document.body.classList.remove("admin-disconnected", "admin-cache-connecting");
    return;
  }
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "statusConnectionBanner";
    banner.className = "status-connection-banner";
    const grid = panel.querySelector(".grid");
    safeInsertBefore(panel, banner, grid || panel.firstChild || null);
  }
  const disconnected = !!meta.disconnected;
  banner.className = `status-connection-banner ${disconnected ? "disconnected" : "connecting"}`;
  const saved = statusCacheSavedLabel(meta.saved_at);
  banner.textContent = disconnected
    ? `Disconnected from remote server. Showing cached status from ${saved}; the panel will reconnect automatically.`
    : `Showing cached status from ${saved} while contacting the server.`;
  document.body.classList.toggle("admin-disconnected", disconnected);
  document.body.classList.toggle("admin-cache-connecting", !disconnected);
}
function clearStatusConnectionState() {
  statusOutageStartedAt = 0;
  const wasDisconnected = statusDisconnectedActive;
  statusDisconnectedActive = false;
  document.body.classList.remove("admin-disconnected", "admin-cache-connecting");
  $("statusConnectionBanner")?.remove();
  return wasDisconnected;
}
function markStatusDisconnected(reason = "") {
  const payload = readCachedStatusPayload(0);
  const cached = payload?.status && typeof payload.status === "object"
    ? payload.status
    : stripStatusCacheMeta(lastStatus || {});
  if (!cached || !Object.keys(cached).length) return false;
  const previousStatus = lastStatus;
  lastStatus = annotateStatusCache(cached, payload || {}, {
    disconnected: true,
    reason,
    message: "Disconnected from remote server",
  });
  statusDisconnectedActive = true;
  renderStatusUi(lastStatus, previousStatus, { cached: true, disconnected: true });
  scheduleStatusPoll(STATUS_POLL_FOREGROUND_FAST_MS);
  return true;
}
function handleStatusFetchFailure(error, opts = {}) {
  const now = Date.now();
  if (!statusOutageStartedAt) statusOutageStartedAt = now;
  const elapsed = now - statusOutageStartedAt;
  const boot = !!opts.boot;
  const cachedPayload = readCachedStatusPayload(0);
  const cachedAt = Number(cachedPayload?.saved_at || lastStatus?.__status_cache?.saved_at || 0);
  const canUseCached = !!(cachedPayload?.status || lastStatus);
  const detail = messageText(error);
  if (boot && canUseCached) {
    markStatusDisconnected(`Initial page refresh could not contact the server within ${STATUS_BOOT_CONTACT_TIMEOUT_MS / 1000}s: ${detail}`);
    return true;
  }
  if (elapsed >= STATUS_OPEN_PANEL_DISCONNECT_MS && canUseCached) {
    markStatusDisconnected(`Status polling has been unable to contact the server for ${Math.round(elapsed / 1000)}s: ${detail}`);
    return true;
  }
  const reconnecting = elapsed > 0 ? ` Reconnecting for ${Math.round(elapsed / 1000)}s.` : "";
  const cacheNote = cachedAt ? ` Cached snapshot available from ${statusCacheSavedLabel(cachedAt)}.` : "";
  setMsg(`Status error: ${detail}.${reconnecting}${cacheNote}`);
  return false;
}
function registerAdminServiceWorker() {
  try {
    if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
    const requestShellCache = (registration) => {
      try {
        const workers = [
          registration?.active,
          registration?.waiting,
          registration?.installing,
          navigator.serviceWorker.controller,
        ].filter(Boolean);
        workers.forEach((worker) => {
          try {
            worker.postMessage({ type: "CACHE_ADMIN_SHELL" });
          } catch (e) {}
        });
      } catch (e) {}
    };
    navigator.serviceWorker
      .register("/admin/sw.js", { scope: "/admin" })
      .then((registration) => {
        requestShellCache(registration);
        const installingWorker = registration.installing;
        if (installingWorker) {
          installingWorker.addEventListener("statechange", () => {
            if (installingWorker.state === "activated") requestShellCache(registration);
          });
        }
        navigator.serviceWorker.ready
          .then((readyRegistration) => requestShellCache(readyRegistration))
          .catch(() => {});
      })
      .catch(() => {});
  } catch (e) {}
}
function compactStatusForCache(status = {}) {
  if (!status || typeof status !== "object") return null;
  const keys = [
    "script_version",
    "active_mode",
    "active_port",
    "active_modes",
    "containers",
    "container",
    "gpu_count",
    "gpus",
    "metrics",
    "power",
    "system",
    "system_metric_peaks",
    "uptime_seconds",
    "machine_uptime_seconds",
    "users",
    "groups",
    "server_config",
    "instances",
    "running_runtimes",
    "instance_runtime_metrics",
    "presets",
    "benchmarks",
    "model_install_job",
    "model_install_jobs",
    "script_job",
    "preset_tps_stats",
    "upstream_services",
    "nvlink",
    "series",
  ];
  const compact = {};
  keys.forEach((key) => {
    if (status[key] !== undefined) compact[key] = status[key];
  });
  if (Array.isArray(compact.series) && compact.series.length > STATUS_CACHE_SERIES_LIMIT) {
    compact.series = compact.series.slice(-STATUS_CACHE_SERIES_LIMIT);
  }
  return compact;
}
function readCachedStatusPayload(maxAgeMs = STATUS_CACHE_MAX_AGE_MS) {
  try {
    const payload = JSON.parse(localStorage.getItem(STATUS_CACHE_KEY) || "null");
    if (!payload || typeof payload !== "object") return null;
    const savedAt = Number(payload.saved_at || 0);
    if (maxAgeMs && (!savedAt || Date.now() - savedAt > maxAgeMs)) return null;
    const status = payload.status;
    return status && typeof status === "object" ? payload : null;
  } catch (e) {
    return null;
  }
}
function readCachedStatus(maxAgeMs = STATUS_CACHE_MAX_AGE_MS) {
  const payload = readCachedStatusPayload(maxAgeMs);
  return payload?.status && typeof payload.status === "object" ? payload.status : null;
}
function cachedStatusSeriesFresh(payload) {
  if (!payload || !Array.isArray(payload.status?.series) || !payload.status.series.length) {
    return false;
  }
  const savedAt = Number(payload.series_saved_at || 0);
  return !!savedAt && Date.now() - savedAt <= STATUS_CACHE_SERIES_MAX_AGE_MS;
}
function writeStatusCacheFromStatus(status = {}) {
  const compact = compactStatusForCache(status);
  if (!compact) return;
  const previousPayload = readCachedStatusPayload(0) || {};
  const previous = previousPayload.status || {};
  let seriesSavedAt = Number(previousPayload.series_saved_at || 0) || 0;
  if (Array.isArray(compact.series)) {
    seriesSavedAt = Date.now();
  } else if (Array.isArray(previous.series)) {
    compact.series = previous.series.slice(-STATUS_CACHE_SERIES_LIMIT);
  }
  try {
    localStorage.setItem(
      STATUS_CACHE_KEY,
      JSON.stringify({ saved_at: Date.now(), series_saved_at: seriesSavedAt, status: compact }),
    );
  } catch (e) {}
}
function renderStatusUi(j, previousStatus = null, options = {}) {
  const metrics = j?.metrics || {};
  const power = j?.power || {};
  const renderErrors = [];
  if (j?.benchmarks?.job) syncBenchmarkModalControlLock(j.benchmarks.job, j.benchmarks);
  if ($("showGlobalLogs")) {
    $("showGlobalLogs").checked = effectiveShowGlobalLogs();
    $("showGlobalLogs").disabled = currentLogSourceDetached();
  }
  safeRenderStep("connection", () => renderStatusConnectionBanner(j), renderErrors);
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
    if (typeof syncPowerCoolingBusyState === "function") syncPowerCoolingBusyState();
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
  safeRenderStep("benchmark surfaces", () => renderBenchmarkSurfaces(), renderErrors);
  safeRenderStep("chat", () => renderChatUi({ preserveTranscript: true }), renderErrors);
  safeRenderStep("tab sync", () => syncActiveTabDisplay(), renderErrors);
  reconcileUpdateUiFromStatus(j);
  if (activeTabName === "logs" || effectiveShowGlobalLogs()) connectLogs(false);
  if (!options.cached) {
    handleSwitchJobTransition(previousStatus, j);
    handleBenchmarkJobTransition(previousStatus, j);
  }
  return renderErrors;
}
function hydrateCachedStatusForBoot() {
  const payload = readCachedStatusPayload();
  if (!payload) return false;
  let cached = payload.status;
  if (!cached) return false;
  if (activeTabName === "metrics" && !cachedStatusSeriesFresh(payload)) {
    cached = { ...cached };
    delete cached.series;
  }
  cached = annotateStatusCache(cached, payload, { connecting: true });
  const previousStatus = lastStatus;
  lastStatus = lastStatus ? { ...cached, ...lastStatus } : cached;
  writeRuntimeInventoryCacheFromStatus(lastStatus);
  syncPresetSummaryCacheFromStatus(lastStatus);
  hydrateSelectedPresetModel();
  renderStatusUi(lastStatus, previousStatus, { cached: true });
  return true;
}
refreshStatus = async function (opts = {}) {
  const force = !!(opts && opts.force);
  const includeSeries = !!(opts && opts.includeSeries);
  const includeInventory = !!(opts && opts.includeInventory);
  const includeBenchmarkDetails = !!(opts && opts.includeBenchmarkDetails);
  const inventoryDetail = String((opts && opts.inventoryDetail) || "").trim();
  const boot = !!(opts && opts.boot);
  if (updateMonitor.active) return lastStatus;
  if (adminAuthRefreshBlocked && !force) return lastStatus;
  if (statusRefreshPromise) {
    if (force) {
      pendingForcedStatusRefresh = true;
      pendingForcedStatusRefreshIncludeSeries =
        pendingForcedStatusRefreshIncludeSeries || includeSeries;
      pendingForcedStatusRefreshIncludeInventory =
        pendingForcedStatusRefreshIncludeInventory || includeInventory;
      pendingForcedStatusRefreshIncludeBenchmarkDetails =
        pendingForcedStatusRefreshIncludeBenchmarkDetails || includeBenchmarkDetails;
      if (inventoryDetail === "full" || !pendingForcedStatusRefreshInventoryDetail) {
        pendingForcedStatusRefreshInventoryDetail = inventoryDetail;
      }
    }
    return statusRefreshPromise;
  }
  statusRefreshPromise = (async () => {
    try {
      ensureV414Layout();
      const profileOptions = {
        includeSeries,
        includeInventory,
        includeBenchmarkDetails,
      };
      if (inventoryDetail) profileOptions.inventoryDetail = inventoryDetail;
      const query = new URLSearchParams(statusRequestProfile(profileOptions));
      const statusRequestStartedAt = Date.now();
      query.set("_", String(statusRequestStartedAt));
      if (force) query.set("force", "1");
      const r = await fetchJsonWithTimeout(
        `/admin/status?${query.toString()}`,
        { cache: "no-store" },
        boot ? STATUS_BOOT_CONTACT_TIMEOUT_MS : 12000,
      );
      if (r.status === 401) {
        adminAuthRefreshBlocked = true;
        setMsg("Authentication expired. Reloading the admin panel...");
        setTimeout(() => {
          window.location.href = "/admin";
        }, 400);
        return lastStatus;
      }
      if (!r.ok) throw new Error(`status fetch failed (${r.status})`);
      const payload = mergeStatusPayloadBenchmarkSnapshot(lastStatus, await r.json());
      const baseStatus = lastStatus ? stripStatusCacheMeta(lastStatus) : null;
      const j = baseStatus ? { ...baseStatus, ...payload } : payload;
      if (!Object.prototype.hasOwnProperty.call(payload, "status_error")) {
        delete j.status_error;
        delete j.status_error_at;
      }
      delete j.__status_cache;
      const wasDisconnected = clearStatusConnectionState();
      adminAuthRefreshBlocked = false;
      reconcileHiddenPresetSelectorsFromStatus(j, statusRequestStartedAt);
      const previousStatus = lastStatus;
      lastStatus = j;
      writeRuntimeInventoryCacheFromStatus(j);
      writeStatusCacheFromStatus(j);
      syncPresetSummaryCacheFromStatus(j);
      hydrateUiState(j.ui_config || {});
      const hydratedProfile = statusRequestProfile(profileOptions);
      if (
        (hydratedProfile.include_inventory === "1" && !j.runtime_inventory) ||
        (hydratedProfile.include_series === "1" && !Array.isArray(j.series))
      ) {
        pendingForcedStatusRefresh = true;
        pendingForcedStatusRefreshIncludeSeries =
          pendingForcedStatusRefreshIncludeSeries || hydratedProfile.include_series === "1";
        pendingForcedStatusRefreshIncludeInventory =
          pendingForcedStatusRefreshIncludeInventory || hydratedProfile.include_inventory === "1";
        pendingForcedStatusRefreshIncludeBenchmarkDetails =
          pendingForcedStatusRefreshIncludeBenchmarkDetails || hydratedProfile.include_benchmark_details === "1";
        if (hydratedProfile.inventory_detail === "full" || !pendingForcedStatusRefreshInventoryDetail) {
          pendingForcedStatusRefreshInventoryDetail = hydratedProfile.inventory_detail || "";
        }
      }
      ensureChatHydrationForActiveTab();
      hydrateSelectedPresetModel();
      const renderErrors = renderStatusUi(j, previousStatus);
      scheduleStatusPoll();
      const statusWarnings = [];
      if (wasDisconnected) statusWarnings.push("Reconnected to the remote server.");
      if (j.access_hint?.message) statusWarnings.push(String(j.access_hint.message));
      if (j.status_error) statusWarnings.push(`Status probe fallback: ${j.status_error}`);
      if (renderErrors.length) statusWarnings.push(`Partial UI render: ${renderErrors.join(" | ")}`);
      setMsg(joinMessageParts(statusWarnings));
    } catch (e) {
      if (recoverPendingUpdateMonitor()) {
        setMsg("");
        return;
      }
      handleStatusFetchFailure(e, { boot });
    } finally {
      statusRefreshPromise = null;
      if (pendingForcedStatusRefresh) {
        const nextIncludeSeries = pendingForcedStatusRefreshIncludeSeries;
        const nextIncludeInventory = pendingForcedStatusRefreshIncludeInventory;
        const nextIncludeBenchmarkDetails = pendingForcedStatusRefreshIncludeBenchmarkDetails;
        const nextInventoryDetail = pendingForcedStatusRefreshInventoryDetail;
        pendingForcedStatusRefresh = false;
        pendingForcedStatusRefreshIncludeSeries = false;
        pendingForcedStatusRefreshIncludeInventory = false;
        pendingForcedStatusRefreshIncludeBenchmarkDetails = false;
        pendingForcedStatusRefreshInventoryDetail = "";
        refreshStatus({
          force: true,
          includeSeries: nextIncludeSeries,
          includeInventory: nextIncludeInventory,
          includeBenchmarkDetails: nextIncludeBenchmarkDetails,
          inventoryDetail: nextInventoryDetail,
        }).catch(() => {});
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
  registerAdminServiceWorker();
  ensureResizableSurfaces();
  loadCodeSyntaxConfig().catch(() => {});
  if (!uiStateHydrated) hydrateUiState({});
  syncActiveTabDisplay();
  recoverPendingUpdateMonitor();
  startExternalUpdateSignalPolling();
  hydratePresetSummaryCache();
  const chatCacheApplied = hydrateChatStateFromLocalCache();
  if (chatCacheApplied && activeTabName === "chat") {
    renderChatUi({ preserveTranscript: true });
    scheduleChatTranscriptHeightSync();
  }
  hydrateCachedStatusForBoot();
  resetUserForm(true);
  resetGroupForm(true);
  if (!selectedScope)
    selectedScope =
      singleScopeItems()[0]?.id || pairScopeItems()[0]?.id || "GLOBAL";
  setScope(selectedScope, false);
  if (activeTabName === "presets") {
    renderPresetScopeTabs();
    renderModelInstallStatus();
    if (renderCachedDynamicPresetModels()) {
      requestAnimationFrame(() => renderDynamicPresetModels());
    } else {
      renderDynamicPresetModels();
    }
  }
  if (activeTabName === "chat") {
    hydrateChatState()
      .then(() => {
        renderChatUi({ preserveTranscript: true });
        scheduleChatTranscriptHeightSync();
      })
      .catch(() => {});
    renderChatUi({ preserveTranscript: true });
    scheduleChatTranscriptHeightSync();
  }
  const bootNeedsMetricSeries = activeTabName === "metrics" || popupMetricsWindowOpen();
  if (bootNeedsMetricSeries) {
    initialMetricsSeriesRequested = true;
  }
  refreshStatus({ force: true, includeSeries: bootNeedsMetricSeries, boot: true }).catch(() => {});
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
function readCachedRuntimeInventory() {
  try {
    const payload = JSON.parse(localStorage.getItem(RUNTIME_INVENTORY_CACHE_KEY) || "null");
    const inventory = payload?.runtime_inventory && typeof payload.runtime_inventory === "object"
      ? payload.runtime_inventory
      : payload;
    if (
      inventory &&
      typeof inventory === "object" &&
      Array.isArray(inventory.models) &&
      Array.isArray(inventory.variants)
    ) {
      return inventory;
    }
  } catch (e) {}
  return null;
}
function writeRuntimeInventoryCacheFromStatus(status) {
  const inventory = status?.runtime_inventory;
  if (!inventory || !Array.isArray(inventory.models) || !Array.isArray(inventory.variants)) return;
  try {
    localStorage.setItem(
      RUNTIME_INVENTORY_CACHE_KEY,
      JSON.stringify({ saved_at: Date.now(), runtime_inventory: inventory }),
    );
  } catch (e) {}
}
function runtimeInventory() {
  return (lastStatus && lastStatus.runtime_inventory) || readCachedRuntimeInventory() || { models: [], variants: [] };
}
function inventoryModels() {
  const cachedModels = runtimeInventory().models;
  if (Array.isArray(cachedModels) && cachedModels.length) return cachedModels;
  const statusModels = lastStatus?.models;
  if (Array.isArray(statusModels) && statusModels.length) return statusModels;
  return Array.isArray(statusModels) ? statusModels : [];
}
function inventoryProfileLikes() {
  return runtimeInventory().profile_likes || [];
}
function modelIsCustom(model) {
  return (
    !!model?.custom_model ||
    String(model?.inventory_origin || model?.model_inventory_origin || "").trim().toLowerCase() === "custom_registry"
  );
}
function variantIsCustom(variant) {
  const sourceKind = String(variant?.source_kind || "").trim().toLowerCase();
  const origin = String(variant?.inventory_origin || "").trim().toLowerCase();
  return sourceKind === "custom" && origin === "custom_registry" && variant?.custom_preset === true;
}
function variantIsRegistryBackedPreset(variant) {
  const sourceKind = String(variant?.source_kind || "").trim().toLowerCase();
  const origin = String(variant?.inventory_origin || "").trim().toLowerCase();
  return (
    sourceKind === "custom" &&
    ["custom_registry", "migrated_custom_registry", "deprecated_backup_registry"].includes(origin)
  );
}
function customInventoryModels() {
  return inventoryModels().filter((model) => modelIsCustom(model));
}
function curatedInventoryModels() {
  return inventoryModels().filter((model) => !modelIsCustom(model));
}
function inventoryVariants() {
  const cachedVariants = runtimeInventory().variants;
  if (Array.isArray(cachedVariants) && cachedVariants.length) return cachedVariants;
  const statusVariants = lastStatus?.variants;
  if (Array.isArray(statusVariants) && statusVariants.length) return statusVariants;
  return Array.isArray(statusVariants) ? statusVariants : [];
}
function runtimeInventoryHasFullDetails() {
  const inventory = runtimeInventory();
  if (inventory?.inventory_detail === "full") return true;
  return inventoryVariants().some(
    (variant) =>
      Object.prototype.hasOwnProperty.call(variant || {}, "default_engine_switches") ||
      Object.prototype.hasOwnProperty.call(variant || {}, "launch_settings"),
  );
}
async function ensureFullRuntimeInventory() {
  if (runtimeInventoryHasFullDetails()) return runtimeInventory();
  const profile = statusRequestProfile({
    includeInventory: true,
    inventoryDetail: "full",
    includeBenchmarkDetails: false,
  });
  profile.include_series = "0";
  profile.include_benchmark_details = "0";
  const query = new URLSearchParams(profile);
  query.set("force", "1");
  query.set("_", String(Date.now()));
  const response = await fetchJsonWithTimeout(`/admin/status?${query.toString()}`, { cache: "no-store" }, 12000);
  if (!response.ok) throw new Error(`full inventory fetch failed (${response.status})`);
  const payload = await response.json();
  if (!payload?.runtime_inventory) throw new Error("Full runtime inventory was not returned.");
  lastStatus = lastStatus ? { ...lastStatus, ...payload } : payload;
  writeRuntimeInventoryCacheFromStatus(lastStatus);
  syncPresetSummaryCacheFromStatus(lastStatus);
  return runtimeInventory();
}
function findVariantBySelector(selector) {
  const key = String(selector || "").trim();
  if (!key) return null;
  return (
    inventoryVariants().find((variant) => {
      const candidates = [
        variant?.selector,
        variant?.upstream_tag,
        variant?.variant_id,
        variant?.mode,
      ].map((item) => String(item || "").trim());
      return candidates.includes(key);
    }) || null
  );
}
function saveSelectedPresetModel(modelId = "") {
  const next = String(modelId || "").trim();
  selectedPresetModelId = next;
  try {
    localStorage.setItem(SELECTED_PRESET_MODEL_CACHE_KEY, next);
  } catch (e) {}
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
function readCachedSelectedPresetModel() {
  try {
    return String(localStorage.getItem(SELECTED_PRESET_MODEL_CACHE_KEY) || "").trim();
  } catch (e) {}
  return "";
}
function hydrateSelectedPresetModel() {
  const models = inventoryModels();
  const valid = new Set(models.map((model) => String(model.model_id || "")));
  valid.add(RESOURCE_MANAGER_MODEL_ID);
  valid.add(HIDDEN_PRESETS_MODEL_ID);
  valid.add(AI_STUDIO_MODEL_ID);
  const configured = String(lastStatus?.server_config?.selected_preset_model || "").trim();
  const cached = readCachedSelectedPresetModel();
  if (!selectedPresetModelHydrated) {
    selectedPresetModelId = valid.has(configured)
      ? configured
      : valid.has(cached)
        ? cached
        : "";
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
  try {
    localStorage.setItem(SELECTED_PRESET_MODEL_CACHE_KEY, selectedPresetModelId);
  } catch (e) {}
  renderPresetModelSelector();
  renderDynamicPresetModels();
  renderModelInstallStatus();
  saveSelectedPresetModel(selectedPresetModelId);
}
function cssEscapeValue(value = "") {
  const raw = String(value || "");
  if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(raw);
  return raw.replace(/["\\]/g, "\\$&");
}
function focusPresetCard(selector = "") {
  const key = String(selector || "").trim();
  if (!key) return false;
  const attr = cssEscapeValue(key);
  const target = document.querySelector(`[data-preset-selector="${attr}"]`);
  if (!target) return false;
  target.scrollIntoView({ block: "center", behavior: "smooth" });
  target.classList.remove("preset-card-focus-pulse");
  void target.offsetWidth;
  target.classList.add("preset-card-focus-pulse");
  setTimeout(() => target.classList.remove("preset-card-focus-pulse"), 2600);
  return true;
}
function openPresetCardFromResourceManager(selector = "") {
  const variant = findVariantBySelector(selector);
  if (!variant) {
    alert(`Preset ${selector || "unknown"} was not found in the current inventory.`);
    return false;
  }
  clearPresetFilterStateForNavigation();
  selectPresetModel(String(variant?.model_id || ""));
  setTimeout(() => {
    if (!focusPresetCard(variantSelector(variant))) {
      renderDynamicPresetModels({ force: true });
      setTimeout(() => focusPresetCard(variantSelector(variant)), 0);
    }
  }, 0);
  return false;
}
function renderPresetModelSelector() {
  const host = $("presetModelSelector");
  if (!host) return;
  const models = inventoryModels();
  if (!models.length) {
    host.classList.add("hidden");
    host.innerHTML = "";
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
  if (custom.length) {
    parts.push('<span class="scope-strip-separator" aria-hidden="true"></span>');
    parts.push(...custom.map(renderModelButton));
  }
  setHtmlIfChanged(host, parts.join(""));
}
function presetMenuIconHtml(icon, className = "") {
  return `<span class="preset-menu-icon ${className}" aria-hidden="true">${svgIcon(icon)}</span>`;
}
function renderPresetMenuItem({ label, icon, className, onClick, active = false } = {}) {
  const classes = `preset-menu-item ${className || ""}${active ? " active" : ""}`.trim();
  return `<button type="button" class="${classes}" role="menuitem" onclick="closePresetActionsMenu(); ${onClick}">${presetMenuIconHtml(icon)}<span>${escapeHtml(label)}</span></button>`;
}
function renderPresetActionsMenu() {
  const items = [
    renderPresetMenuItem({
      label: "Setup Assistant",
      icon: "sparkles",
      className: "preset-menu-setup",
      onClick: "openSetupAssistantModal()",
    }),
    renderPresetMenuItem({
      label: "Rebuild Model DB",
      icon: "database",
      className: "preset-menu-rebuild",
      onClick: "promptRuntimeInventoryRebuild()",
    }),
    '<div class="preset-menu-separator" aria-hidden="true"></div>',
    renderPresetMenuItem({
      label: "Hidden Presets",
      icon: "hide",
      className: "preset-menu-hidden",
      onClick: `selectPresetModel('${HIDDEN_PRESETS_MODEL_ID}')`,
      active: selectedPresetModelId === HIDDEN_PRESETS_MODEL_ID,
    }),
    renderPresetMenuItem({
      label: "Custom Model",
      icon: "plus",
      className: "preset-menu-custom",
      onClick: "openCustomModelModal()",
    }),
    renderPresetMenuItem({
      label: "Model Manager",
      icon: "gear",
      className: "preset-menu-manager",
      onClick: `selectPresetModel('${RESOURCE_MANAGER_MODEL_ID}')`,
      active: selectedPresetModelId === RESOURCE_MANAGER_MODEL_ID,
    }),
    renderPresetMenuItem({
      label: "AI Studio",
      icon: "sparkles",
      className: "preset-menu-ai-studio",
      onClick: `selectPresetModel('${AI_STUDIO_MODEL_ID}')`,
      active: selectedPresetModelId === AI_STUDIO_MODEL_ID,
    }),
    renderPresetMenuItem({
      label: "Benchmarks",
      icon: "play",
      className: "preset-menu-benchmarks",
      onClick: "openBenchmarkAllModal()",
    }),
  ];
  return `<div class="preset-head-menu" id="presetActionsMenu"><button type="button" class="preset-menu-button" id="presetActionsMenuButton" title="Preset actions" aria-label="Preset actions" aria-haspopup="menu" aria-expanded="false" onclick="togglePresetActionsMenu(event)">${svgIcon("menu")}</button><div class="preset-actions-menu hidden" id="presetActionsMenuList" role="menu">${items.join("")}</div></div>`;
}
function defaultPresetFilterState() {
  return {
    name: "",
    tags: [],
    statuses: [],
    engines: [],
    topologies: [],
    modelSizeMin: "",
    modelSizeMax: "",
    cacheSizeMin: "",
    cacheSizeMax: "",
    quickMin: "",
    quickMax: "",
    fullMin: "",
    fullMax: "",
    scoreLogic: "or",
    tpsMin: "",
    tpsMax: "",
    metricMins: {},
    metricMaxs: {},
  };
}
function normalizedPresetFilterState(value = {}) {
  const base = defaultPresetFilterState();
  const row = value && typeof value === "object" ? value : {};
  return {
    ...base,
    ...row,
    tags: Array.isArray(row.tags) ? row.tags.map(String) : [],
    statuses: Array.isArray(row.statuses) ? row.statuses.map(String) : [],
    engines: Array.isArray(row.engines) ? row.engines.map(String) : [],
    topologies: Array.isArray(row.topologies) ? row.topologies.map(String) : [],
    metricMins: row.metricMins && typeof row.metricMins === "object" ? row.metricMins : {},
    metricMaxs: row.metricMaxs && typeof row.metricMaxs === "object" ? row.metricMaxs : {},
    scoreLogic: String(row.scoreLogic || "or").toLowerCase() === "and" ? "and" : "or",
  };
}
function getPresetFilterState() {
  if (presetFilterState) return presetFilterState;
  try {
    presetFilterState = normalizedPresetFilterState(JSON.parse(localStorage.getItem(PRESET_FILTER_CACHE_KEY) || "{}"));
  } catch (e) {
    presetFilterState = defaultPresetFilterState();
  }
  return presetFilterState;
}
function presetFilterIsActive(state = getPresetFilterState()) {
  const ignored = new Set(["scoreLogic"]);
  return Object.entries(state || {}).some(([key, value]) => {
    if (ignored.has(key)) return false;
    if (Array.isArray(value)) return value.length > 0;
    if (value && typeof value === "object") return Object.values(value).some((item) => String(item ?? "").trim() !== "");
    return String(value ?? "").trim() !== "";
  });
}
function savePresetFilterState(state) {
  presetFilterState = normalizedPresetFilterState(state);
  try {
    localStorage.setItem(PRESET_FILTER_CACHE_KEY, JSON.stringify(presetFilterState));
  } catch (e) {}
  dynamicPresetRenderSignature = "";
  renderPresetHeaderActions();
  renderDynamicPresetModels({ force: true });
  renderModelInstallStatus();
}
function resetPresetFilterState() {
  savePresetFilterState(defaultPresetFilterState());
  return false;
}
function clearPresetFilterStateForNavigation() {
  if (!presetFilterIsActive()) return false;
  presetFilterState = defaultPresetFilterState();
  try {
    localStorage.setItem(PRESET_FILTER_CACHE_KEY, JSON.stringify(presetFilterState));
  } catch (e) {}
  renderPresetHeaderActions();
  return true;
}
function presetFilterCheckboxes(name, options, selected = []) {
  const chosen = new Set(selected || []);
  return `<div class="preset-filter-checks">${options
    .map(([value, label]) => `<label><input type="checkbox" name="${escapeHtml(name)}" value="${escapeHtml(value)}"${chosen.has(value) ? " checked" : ""}>${escapeHtml(label)}</label>`)
    .join("")}</div>`;
}
function presetFilterRangeFields(prefix, label, minValue, maxValue, step = "0.1", bounds = {}) {
  const minAttr = bounds.min === undefined ? "" : ` min="${escapeHtml(bounds.min)}"`;
  const maxAttr = bounds.max === undefined ? "" : ` max="${escapeHtml(bounds.max)}"`;
  return `<div class="preset-filter-section"><h3>${escapeHtml(label)}</h3><div class="formgrid preset-filter-fields"><label>Minimum<input id="${escapeHtml(prefix)}Min" type="number"${minAttr}${maxAttr} step="${escapeHtml(step)}" inputmode="decimal" value="${escapeHtml(minValue)}"></label><label>Maximum<input id="${escapeHtml(prefix)}Max" type="number"${minAttr}${maxAttr} step="${escapeHtml(step)}" inputmode="decimal" value="${escapeHtml(maxValue)}"></label></div></div>`;
}
function readPresetFilterModalState() {
  const value = (id) => String($(id)?.value || "").trim();
  const checked = (name) => [...currentUiDocument().querySelectorAll(`input[name="${name}"]:checked`)].map((row) => row.value);
  const metricMins = {};
  const metricMaxs = {};
  MODEL_SCORE_METRIC_ORDER.forEach((id) => {
    const metricMin = value(`presetFilterMetricMin_${id}`);
    const metricMax = value(`presetFilterMetricMax_${id}`);
    if (metricMin) metricMins[id] = metricMin;
    if (metricMax) metricMaxs[id] = metricMax;
  });
  return normalizedPresetFilterState({
    name: value("presetFilterName"),
    tags: checked("presetFilterTag"),
    statuses: checked("presetFilterStatus"),
    engines: checked("presetFilterEngine"),
    topologies: checked("presetFilterTopology"),
    modelSizeMin: value("presetFilterModelSizeMin"),
    modelSizeMax: value("presetFilterModelSizeMax"),
    cacheSizeMin: value("presetFilterCacheSizeMin"),
    cacheSizeMax: value("presetFilterCacheSizeMax"),
    quickMin: value("presetFilterQuickMin"),
    quickMax: value("presetFilterQuickMax"),
    fullMin: value("presetFilterFullMin"),
    fullMax: value("presetFilterFullMax"),
    scoreLogic: value("presetFilterScoreLogic"),
    tpsMin: value("presetFilterTpsMin"),
    tpsMax: value("presetFilterTpsMax"),
    metricMins,
    metricMaxs,
  });
}
function openPresetFilterModal() {
  const state = getPresetFilterState();
  const engines = [...new Set(inventoryVariants().map((row) => String(row?.engine_display || row?.engine || "").trim()).filter(Boolean))]
    .sort()
    .map((value) => [value, prettyEngineName(value)]);
  const metricFields = MODEL_SCORE_METRIC_ORDER.map((id) => {
    const label = MODEL_SCORE_METRIC_LABELS[id] || id;
    return `<label>${escapeHtml(label)} minimum<input id="presetFilterMetricMin_${escapeHtml(id)}" type="number" min="0" max="10" step="0.1" inputmode="decimal" value="${escapeHtml(state.metricMins?.[id] || "")}"></label><label>${escapeHtml(label)} maximum<input id="presetFilterMetricMax_${escapeHtml(id)}" type="number" min="0" max="10" step="0.1" inputmode="decimal" value="${escapeHtml(state.metricMaxs?.[id] || "")}"></label>`;
  }).join("");
  const detailsHtml = `<div class="preset-filter-grid">
    <div class="preset-filter-section"><h3>Name</h3><label>Pattern<input id="presetFilterName" value="${escapeHtml(state.name)}" placeholder="substring or * wildcard"></label></div>
    <div class="preset-filter-section"><h3>Tags</h3>${presetFilterCheckboxes("presetFilterTag", [["deprecated","Deprecated"],["migrated","Migrated"],["nvlink","NVLink"],["custom","Custom"],["experimental","Experimental"],["uncensored","Uncensored"]], state.tags)}</div>
    <div class="preset-filter-section"><h3>Status</h3>${presetFilterCheckboxes("presetFilterStatus", [["active","Active"],["ready","Ready"],["download","Download"],["hardware_blocked","Hardware Blocked"],["unavailable","Unavailable"]], state.statuses)}</div>
    <div class="preset-filter-section"><h3>Engine</h3>${presetFilterCheckboxes("presetFilterEngine", engines, state.engines)}</div>
    <div class="preset-filter-section"><h3>Topology</h3>${presetFilterCheckboxes("presetFilterTopology", [["single","Single GPU"],["dual","Dual GPU"],["multi","Multi GPU"]], state.topologies)}</div>
    ${presetFilterRangeFields("presetFilterModelSize", "Model Size (GiB)", state.modelSizeMin, state.modelSizeMax)}
    ${presetFilterRangeFields("presetFilterCacheSize", "Cache Size (GiB)", state.cacheSizeMin, state.cacheSizeMax)}
    ${presetFilterRangeFields("presetFilterTps", "Recorded TPS", state.tpsMin, state.tpsMax)}
    <div class="preset-filter-section"><h3>Overall Scores</h3><div class="formgrid preset-filter-fields"><label>Quick minimum<input id="presetFilterQuickMin" type="number" min="0" max="10" step="0.1" inputmode="decimal" value="${escapeHtml(state.quickMin)}"></label><label>Quick maximum<input id="presetFilterQuickMax" type="number" min="0" max="10" step="0.1" inputmode="decimal" value="${escapeHtml(state.quickMax)}"></label><label>Full minimum<input id="presetFilterFullMin" type="number" min="0" max="10" step="0.1" inputmode="decimal" value="${escapeHtml(state.fullMin)}"></label><label>Full maximum<input id="presetFilterFullMax" type="number" min="0" max="10" step="0.1" inputmode="decimal" value="${escapeHtml(state.fullMax)}"></label><label>Quick / Full logic<select id="presetFilterScoreLogic"><option value="or"${state.scoreLogic === "or" ? " selected" : ""}>OR</option><option value="and"${state.scoreLogic === "and" ? " selected" : ""}>AND</option></select></label></div></div>
    <div class="preset-filter-section preset-filter-score-categories"><h3>Score Categories</h3><div class="formgrid preset-filter-fields">${metricFields}</div></div>
  </div>`;
  openActionChoiceModal({
    title: "Filter Presets",
    body: "Filters apply to every model tab and remain active when switching models. Summary cards are unchanged.",
    detailsHtml,
    cardClass: "preset-filter-modal-card",
    choices: [
      { label: "Reset", className: "blue", onClick: async () => savePresetFilterState(defaultPresetFilterState()) },
      { label: "Apply", className: "green", onClick: async () => savePresetFilterState(readPresetFilterModalState()) },
    ],
  });
}
function renderPresetHeaderActions() {
  const host = $("presetHeadActions");
  if (!host) return;
  host.innerHTML = `<button type="button" class="preset-menu-button preset-filter-button${presetFilterIsActive() ? " active" : ""}" title="Filter presets" aria-label="Filter presets" onclick="openPresetFilterModal()">${svgIcon("filter")}</button>${renderPresetActionsMenu()}`;
}
function renderPresetHeadActionsHtml() {
  return `<div class="preset-head-actions" id="presetHeadActions"><button type="button" class="preset-menu-button preset-filter-button${presetFilterIsActive() ? " active" : ""}" title="Filter presets" aria-label="Filter presets" onclick="openPresetFilterModal()">${svgIcon("filter")}</button>${renderPresetActionsMenu()}</div>`;
}
function closePresetActionsMenu() {
  const menu = $("presetActionsMenuList");
  const button = $("presetActionsMenuButton");
  if (menu) menu.classList.add("hidden");
  if (button) button.setAttribute("aria-expanded", "false");
}
function togglePresetActionsMenu(event) {
  if (event && typeof event.stopPropagation === "function") event.stopPropagation();
  const menu = $("presetActionsMenuList");
  const button = $("presetActionsMenuButton");
  if (!menu) return;
  const opening = menu.classList.contains("hidden");
  menu.classList.toggle("hidden", !opening);
  if (button) button.setAttribute("aria-expanded", opening ? "true" : "false");
}
document.addEventListener("click", (event) => {
  const wrap = $("presetActionsMenu");
  if (!wrap || wrap.contains(event.target)) return;
  closePresetActionsMenu();
});
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
var pendingHiddenPresetSelectors = null;
var pendingHiddenPresetConfirmAfter = 0;
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
function renderBenchmarkTriggerButton({
  className = "subtab benchmark-manager-trigger",
  label = "Benchmarks",
  onClick = "openBenchmarkAllModal()",
} = {}) {
  return `<button class="${className}" onclick="${onClick}"><span class="custom-model-trigger-content"><span class="custom-model-trigger-icon benchmark-manager-trigger-icon" aria-hidden="true">${svgIcon("play")}</span><span class="custom-model-trigger-label">${escapeHtml(label)}</span></span></button>`;
}
function variantSelector(variant) {
  return (variant && (variant.upstream_tag || variant.selector || variant.variant_id)) || "";
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
  const oldDisplay = parseVariantOldName(variant?.display_name);
  if (oldDisplay?.base) return String(variant?.display_name || "");
  if (String(variant?.source_kind || "").trim().toLowerCase() === "custom") {
    if (variant?.custom_preset) {
      return String(variant?.display_name || variant?.upstream_tag || variant?.model_display_name || "custom preset");
    }
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
  if (variantIsMigrated(variant)) {
    bits.push('<span class="status-badge status-migrated">migrated</span>');
  }
  if (variantIsCustom(variant) && !variantIsMigrated(variant)) {
    bits.push('<span class="status-badge status-custom">custom</span>');
  }
  const confidence = String(variant?.confidence_tier || "").trim().toLowerCase();
  if (variantIsCustom(variant) && confidence && confidence !== "custom" && !variantIsMigrated(variant)) {
    bits.push(
      `<span class="status-badge status-custom_confidence">${escapeHtml(confidence.replaceAll("-", " "))}</span>`,
    );
  }
  return bits.join("");
}
function variantIsMigrated(variant) {
  const origin = String(variant?.inventory_origin || "").trim().toLowerCase();
  const gate = String(variant?.gate_terminal || "").trim().toLowerCase();
  const kind = String(variant?.status_kind || "").trim().toLowerCase();
  const confidence = String(variant?.confidence_tier || "").trim().toLowerCase();
  const sourceStatus = String(variant?.source_status_kind || "").trim().toLowerCase();
  const sourceKind = String(variant?.source_kind || "").trim().toLowerCase();
  const legacyMigrationName = [
    variant?.selector,
    variant?.upstream_tag,
    variant?.slug,
    variant?.display_name,
  ].some((item) => !!parseVariantOldName(item));
  return (
    origin === "migrated_custom_registry" ||
    gate === "migrated" ||
    kind === "migrated" ||
    confidence === "migrated" ||
    sourceStatus === "migrated" ||
    (sourceKind === "custom" && legacyMigrationName)
  );
}
function variantSafetyProfile(variant) {
  const text = [
    variant?.safety_profile?.orientation,
    variant?.compliance_orientation,
    variant?.selector,
    variant?.upstream_tag,
    variant?.variant_id,
    variant?.display_name,
    variant?.best_for,
    variant?.quality_summary,
  ]
    .map((item) => String(item || "").toLowerCase())
    .join(" ");
  if (variant?.safety_profile?.uncensored || variant?.uncensored || /\b(uncensored|abliterated|heretic|prism|hauhau|luffy)\b/.test(text)) {
    return "uncensored";
  }
  return "standard";
}
function variantUncensoredBadgeHtml(variant) {
  return variantSafetyProfile(variant) === "uncensored"
    ? '<span class="status-badge status-uncensored" title="Compliance scoring rewards direct completion for unsafe prompts on this uncensored preset.">Uncensored</span>'
    : "";
}
function variantCapabilityBadges(variant) {
  const bits = [];
  const uncensoredBadge = variantUncensoredBadgeHtml(variant);
  if (uncensoredBadge) bits.push(uncensoredBadge);
  const nvlinkMode = variantNvlinkMode(variant);
  if (nvlinkMode === "required") {
    bits.push('<span class="status-badge status-nvlink">NVLink</span>');
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
  if (kind === "incubating") return "incubating";
  if (kind === "blocked" || kind === "hardware_blocked") return "hardware blocked";
  if (kind === "tombstoned") return "tombstoned";
  if (kind === "deprecated") return "deprecated";
  if (kind === "migrated") return "migrated";
  if (kind === "experimental") return "experimental";
  return "unknown";
}
function statusBadgeTokens(variant) {
  const kind = String(variantEffectiveStatusKind(variant) || "unknown").trim();
  if (variantIsMigrated(variant) && kind === "unknown") return [];
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
      if (token.className === "status-custom") return false;
      if (label === "custom") return false;
      return label !== blockedState;
    })
    .map((token) => `<span class="status-badge ${token.className}">${escapeHtml(options.countLabel ? `${token.label} ${options.countLabel}` : token.label)}</span>`)
    .join("");
}
function variantStatusBadgeHtml(variant, stateLabel = "", options = {}) {
  return renderStatusBadgesHtml(variant, {
    ...options,
    stateLabel,
  });
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
function normalizeVariantLineageKey(value = "") {
  return String(value || "")
    .trim()
    .replace(/^custom\//i, "")
    .replace(/[\\/_\s]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase();
}
function parseVariantOldName(value = "") {
  const text = String(value || "").trim();
  if (!text) return null;
  let match = text.match(/^(.*?)-old(?:\s*\((\d+)\))?$/i);
  if (match && match[1]) {
    return {
      base: match[1].trim(),
      generation: Math.max(1, Number(match[2] || 1) || 1),
    };
  }
  const tokenText = text.replace(/^custom\//i, "");
  match = tokenText.match(/^(.*?)-old(?:-(\d+))?$/i);
  if (match && match[1]) {
    return {
      base: match[1].trim(),
      generation: Math.max(1, Number(match[2] || 1) || 1),
    };
  }
  return null;
}
function variantLineageInfo(variant) {
  const candidates = [
    variant?.display_name,
    variant?.upstream_tag,
    variantSelector(variant),
    variant?.slug,
    variant?.source_selector,
    variant?.profile_like,
    variant?.replacement_selector,
  ];
  for (const candidate of candidates) {
    const parsed = parseVariantOldName(candidate);
    if (parsed?.base) {
      return {
        key: normalizeVariantLineageKey(parsed.base),
        base: parsed.base,
        generation: parsed.generation,
        old: true,
      };
    }
  }
  const base = String(
    variant?.replacement_selector ||
      variant?.source_selector ||
      variant?.display_name ||
      variant?.upstream_tag ||
      variantSelector(variant) ||
      "",
  ).trim();
  return {
    key: normalizeVariantLineageKey(base),
    base,
    generation: 0,
    old: false,
  };
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
  const oldBase = (item) => variantLineageInfo(item).key;
  const oldGeneration = (item) => variantLineageInfo(item).generation;
  const engineKey = (item) => String(item?.engine_display || item?.engine || "").trim().toLowerCase().replaceAll("_", "-");
  const engineRank = (item) => {
    const key = engineKey(item);
    if (key.includes("beellama")) return 0;
    if (key.includes("ik-llama")) return 1;
    if (key.includes("llamacpp") || key.includes("llama.cpp")) return 2;
    if (key.includes("vllm")) return 3;
    return 20;
  };
  const scoreValue = (item) => {
    const score = benchmarkScoreForSelector(variantSelector(item)) || {};
    const full = modelScoreModeResult(score, "full");
    const quick = modelScoreModeResult(score, "quick");
    const value = Number(full?.score ?? quick?.score);
    return Number.isFinite(value) ? value : null;
  };
  const input = [...(rows || [])];
  const groupScore = new Map();
  const statusPriority = (item) => {
    const install = variantEffectiveInstallState(item);
    const status = variantEffectiveStatusKind(item);
    if (install === "hardware_blocked") return 2;
    if (status === "deprecated") return 1;
    return 0;
  };
  input.forEach((item) => {
    const base = oldBase(item);
    const score = scoreValue(item);
    if (score !== null) groupScore.set(base, Math.max(groupScore.get(base) ?? -1, score));
  });
  return input.sort((a, b) => {
    const engineDelta = engineRank(a) - engineRank(b) || engineKey(a).localeCompare(engineKey(b));
    if (engineDelta) return engineDelta;
    const baseDelta = oldBase(a).localeCompare(oldBase(b));
    if (!baseDelta) return oldGeneration(a) - oldGeneration(b) || variantDisplayLabel(a).localeCompare(variantDisplayLabel(b));
    const scoreA = groupScore.get(oldBase(a)) ?? null;
    const scoreB = groupScore.get(oldBase(b)) ?? null;
    if (scoreA !== null || scoreB !== null) {
      const scoreDelta = (scoreB ?? -1) - (scoreA ?? -1);
      if (scoreDelta) return scoreDelta;
    }
    const statusDelta = statusPriority(a) - statusPriority(b);
    if (statusDelta) return statusDelta;
    return baseDelta || variantDisplayLabel(a).localeCompare(variantDisplayLabel(b));
  });
}
function ensureDynamicPresetLayout() {
  const presets = $("presets");
  if (!presets) return;
  const firstPanel = presets.querySelector(".panel");
  if (!firstPanel) return;
  firstPanel.id = "dynamicPresetPanel";
  if (!$("modelPresetGrid")) {
    firstPanel.innerHTML = `<div class="panel-head"><h2>Model Presets</h2>${renderPresetHeadActionsHtml()}</div><div class="preset-help">Discovered presets are rendered directly from the local <code>/opt/ai/club-3090</code> clone. Global applies single-GPU presets across every GPU, dual presets across every two-GPU pair, and multi-GPU presets to the shared runtime.</div><div class="preset-section-label">Scope</div><div class="subtabs" id="presetScopeTabs"></div><div class="value smallgap" id="presetScopeSummary">-</div><div class="preset-section-label">Models</div><div class="subtabs" id="presetModelSelector"></div><div class="value smallgap" id="presetJobSummary">-</div><div class="msg" id="presetResourceMsg"></div><div id="modelPresetGrid" class="model-grid"></div>`;
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
  const doc = currentUiDocument();
  const modal = doc.createElement("div");
  modal.id = "presetActionModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card" role="dialog" aria-modal="true" aria-labelledby="presetActionModalTitle"><div class="panel-head"><h2 id="presetActionModalTitle">Confirm Action</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closePresetActionModal()">✕</button></div><div class="preset-help" id="presetActionModalBody">-</div><textarea id="presetActionModalDetail" class="modal-keybox hidden" readonly wrap="soft" spellcheck="false"></textarea><div class="preset-form-actions"><button class="btn blue" onclick="closePresetActionModal()">Cancel</button><button class="btn green" id="presetActionModalConfirm">Continue</button></div><div class="msg" id="presetActionModalMsg"></div></div>`;
  doc.body.appendChild(modal);
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
function variantLineageRowsForVariant(variant) {
  const info = variantLineageInfo(variant);
  if (!info.key) return [];
  const modelId = String(variant?.model_id || "").trim();
  return sortInventoryVariants(
    inventoryVariants().filter((row) => {
      const rowInfo = variantLineageInfo(row);
      if (rowInfo.key !== info.key) return false;
      if (modelId && String(row?.model_id || "").trim() !== modelId) return false;
      return true;
    }),
  );
}
function variantOldCounterpartsForOriginal(variant) {
  const info = variantLineageInfo(variant);
  if (!info.key || info.old) return [];
  return variantLineageRowsForVariant(variant).filter((row) => variantLineageInfo(row).old);
}
function renderVariantLineageStar(variant) {
  const selector = variantSelector(variant);
  if (!selector || !variantOldCounterpartsForOriginal(variant).length) return "";
  return `<button type="button" class="preset-lineage-star" title="Show differences from OLD preserved presets" aria-label="Show OLD preset differences" onclick="openPresetLineageModal('${escapeJs(selector)}')">⭐</button>`;
}
function ensurePresetLineageModal() {
  if ($("presetLineageModal")) return;
  const doc = currentUiDocument();
  const modal = doc.createElement("div");
  modal.id = "presetLineageModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card preset-lineage-modal-card" role="dialog" aria-modal="true" aria-labelledby="presetLineageTitle"><div class="panel-head"><h2 id="presetLineageTitle">Preset History</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closePresetLineageModal()">✕</button></div><div id="presetLineageBody"></div></div>`;
  doc.body.appendChild(modal);
}
function closePresetLineageModal() {
  ensurePresetLineageModal();
  $("presetLineageModal").classList.add("hidden");
}
let presetLineageActiveSelector = "";
let presetLineageShowFullParameters = false;
function lineageStableJson(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value !== "object") return String(value);
  if (Array.isArray(value) && value.length === 0) return "";
  if (!Array.isArray(value) && Object.keys(value).length === 0) return "";
  try {
    if (Array.isArray(value)) return JSON.stringify(value, null, 2);
    const sorted = {};
    Object.keys(value)
      .sort()
      .forEach((key) => {
        sorted[key] = value[key];
      });
    return JSON.stringify(sorted, null, 2);
  } catch (e) {
    return String(value || "");
  }
}
function lineageShellDefaultValue(value = "") {
  const text = String(value || "").trim();
  const match = text.match(/^\$\{[^:}]+:-([^}]*)\}$/);
  return match ? match[1] : text;
}
function lineageSwitchFlagSummary(text = "") {
  const raw = String(text || "").trim();
  if (!raw) return "";
  const tokens = raw.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g) || [];
  const flags = [];
  for (let i = 0; i < tokens.length; i += 1) {
    const token = String(tokens[i] || "").trim();
    if (!token.startsWith("--")) continue;
    const values = [];
    while (i + 1 < tokens.length && !String(tokens[i + 1] || "").startsWith("--")) {
      values.push(lineageShellDefaultValue(String(tokens[i + 1] || "").replace(/^['"]|['"]$/g, "")));
      i += 1;
    }
    if (token.includes("=")) {
      const [flag, ...rest] = token.split("=");
      flags.push(`${flag}=${lineageShellDefaultValue(rest.join("="))}`);
    } else {
      flags.push(values.length ? `${token} ${values.join(" ")}` : token);
    }
  }
  return flags.length ? flags.join("\n") : raw;
}
const LINEAGE_MEANINGFUL_FIELDS = [
  { id: "engine", label: "Engine", value: (variant) => prettyEngineName(variant.engine_display || variant.engine) },
  { id: "scope_kind", label: "Scope", value: (variant) => variant?.scope_kind || variant?.topology || "" },
  { id: "max_model_len", label: "Max Context", value: (variant) => variantMaxCtx(variant) },
  { id: "model_path", label: "Model Path" },
  { id: "draft_model_path", label: "Draft Model" },
  { id: "drafter", label: "Drafter" },
  { id: "kv_format", label: "KV Cache" },
  { id: "tensor_parallel_size", label: "Tensor Parallel" },
  { id: "gpu_memory_utilization", label: "GPU Memory Utilization" },
  { id: "service_image", label: "Compose Image" },
  { id: "image", label: "Image" },
  { id: "container_image", label: "Container Image" },
  { id: "ports", label: "Ports", value: (variant) => lineageStableJson(variant?.ports) },
  { id: "compose_volume_targets", label: "Volume Targets", value: (variant) => lineageStableJson(variant?.compose_volume_targets || variant?.volume_targets) },
  { id: "environment", label: "Environment", value: (variant) => lineageStableJson(variant?.environment || variant?.compose_environment) },
  { id: "launch_settings", label: "Launch Settings", value: (variant) => lineageStableJson(variant?.launch_settings) },
  { id: "switches", label: "Engine Switches", value: (variant) => lineageSwitchFlagSummary(variant?.default_engine_switches || variant?.compose_command_summary) },
];
function lineageValueText(variant, field) {
  if (typeof field.value === "function") return String(field.value(variant) ?? "").trim();
  return String(variant?.[field.id] ?? "").trim();
}
function lineagePlaceholderLine(line) {
  const text = String(line || "").trim();
  return text === "--" || text === "- -";
}
function lineageNormalizedValue(value) {
  return String(value || "")
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => !lineagePlaceholderLine(line))
    .filter(Boolean)
    .join("\n")
    .trim();
}
function lineageNormalizedLines(value) {
  const normalized = lineageNormalizedValue(value);
  return normalized ? normalized.split("\n").filter(Boolean) : [];
}
function lineageSubtractLines(leftLines, rightLines) {
  const remaining = new Map();
  (rightLines || []).forEach((line) => {
    remaining.set(line, (remaining.get(line) || 0) + 1);
  });
  return (leftLines || []).filter((line) => {
    const count = remaining.get(line) || 0;
    if (count > 0) {
      remaining.set(line, count - 1);
      return false;
    }
    return true;
  });
}
function lineageMeaningfulChangedRows(rows) {
  const variants = (rows || []).filter(Boolean);
  if (variants.length < 2) return [];
  return LINEAGE_MEANINGFUL_FIELDS.map((field) => ({
    field,
    values: variants.map((row) => lineageValueText(row, field)),
  })).filter((row) => new Set(row.values.map(lineageNormalizedValue)).size > 1);
}
function lineageBenchmarkScoreText(variant, mode) {
  const selector = variantSelector(variant);
  const score = benchmarkScoreForSelector(selector) || {};
  const result = modelScoreModeResult(score, mode);
  if (!modelScoreCompactAvailable(result)) return "";
  const status = modelScoreFailed(result) ? "failed" : "pass";
  const timing = modelScoreTimingText(result);
  const pieces = [`${formatModelScoreValue(result.score)} ${status}`];
  if (timing) pieces.push(timing);
  const runId = String(result.run_id || "").trim();
  if (runId) pieces.push(runId);
  return pieces.join("\n");
}
const LINEAGE_BENCHMARK_FIELDS = [
  { id: "full_score", label: "Full Score", value: (variant) => lineageBenchmarkScoreText(variant, "full") },
  { id: "quick_score", label: "Quick Score", value: (variant) => lineageBenchmarkScoreText(variant, "quick") },
];
function lineageBenchmarkChangedRows(rows) {
  const variants = (rows || []).filter(Boolean);
  if (variants.length < 2) return [];
  return LINEAGE_BENCHMARK_FIELDS.map((field) => ({
    field,
    values: variants.map((row) => String(field.value(row) || "").trim()),
  }))
    .filter((row) => row.values.some(Boolean))
    .filter((row) => new Set(row.values.map(lineageNormalizedValue)).size > 1);
}
function renderLineageValue(value) {
  const text = lineageNormalizedValue(value);
  if (!text) return '<span class="lineage-diff-baseline">baseline</span>';
  if (text.length > 180 || text.includes("\n")) {
    return `<pre class="lineage-diff-code">${escapeHtml(text.slice(0, 1600))}${text.length > 1600 ? "\n..." : ""}</pre>`;
  }
  return escapeHtml(text);
}
function renderLineageScoreValue(value) {
  const text = lineageNormalizedValue(value);
  if (!text) return '<span class="lineage-diff-baseline">benchmark score not available</span>';
  return renderLineageValue(text);
}
function lineageUniqueLines(lines) {
  const seen = new Set();
  return (lines || [])
    .map((line) => String(line || "").trim())
    .filter((line) => !lineagePlaceholderLine(line))
    .filter(Boolean)
    .filter((line) => {
      if (seen.has(line)) return false;
      seen.add(line);
      return true;
    });
}
function lineageDiffLineKey(line, scalarMode = false) {
  const text = String(line || "").trim();
  if (!text) return "";
  if (scalarMode) return "__value__";
  const flagMatch = text.match(/^(--[^\s=]+)(?:[\s=].*)?$/);
  if (flagMatch) return `flag:${flagMatch[1]}`;
  const jsonKeyMatch = text.match(/^"([^"]+)"\s*:/);
  if (jsonKeyMatch) return `json:${jsonKeyMatch[1]}`;
  return `line:${text}`;
}
function lineageDiffEntries(lines, scalarMode = false) {
  return (lines || [])
    .map((line) => String(line || "").trim())
    .filter(Boolean)
    .filter((line) => !["[", "]", "{", "}"].includes(line))
    .map((line) => ({ line, key: lineageDiffLineKey(line, scalarMode) }))
    .filter((entry) => entry.key);
}
function lineagePairDeltaEntries(ownLines, referenceLines) {
  const scalarMode = ownLines.length <= 1 && referenceLines.length <= 1;
  const ownEntries = lineageDiffEntries(ownLines, scalarMode);
  const referenceEntries = lineageDiffEntries(referenceLines, scalarMode);
  const ownByKey = new Map();
  const referenceByKey = new Map();
  ownEntries.forEach((entry) => {
    if (!ownByKey.has(entry.key)) ownByKey.set(entry.key, []);
    ownByKey.get(entry.key).push(entry.line);
  });
  referenceEntries.forEach((entry) => {
    if (!referenceByKey.has(entry.key)) referenceByKey.set(entry.key, []);
    referenceByKey.get(entry.key).push(entry.line);
  });
  const ownDelta = [];
  const referenceDelta = [];
  const keys = new Set([...ownByKey.keys(), ...referenceByKey.keys()]);
  keys.forEach((key) => {
    const ownLinesForKey = lineageUniqueLines(ownByKey.get(key) || []);
    const referenceLinesForKey = lineageUniqueLines(referenceByKey.get(key) || []);
    if (ownLinesForKey.length && referenceLinesForKey.length) {
      const same = ownLinesForKey.length === referenceLinesForKey.length && ownLinesForKey.every((line) => referenceLinesForKey.includes(line));
      if (same) return;
      ownLinesForKey
        .filter((line) => !referenceLinesForKey.includes(line))
        .forEach((line) => ownDelta.push({ kind: "changed", text: line }));
      referenceLinesForKey
        .filter((line) => !ownLinesForKey.includes(line))
        .forEach((line) => referenceDelta.push({ kind: "changed", text: line }));
      return;
    }
    if (ownLinesForKey.length) {
      ownLinesForKey.forEach((line) => ownDelta.push({ kind: "added", text: line }));
      return;
    }
    referenceLinesForKey.forEach((line) => {
      ownDelta.push({ kind: "removed", text: line });
      referenceDelta.push({ kind: "removed-source", text: line });
    });
  });
  return { own: ownDelta, reference: referenceDelta };
}
function lineageUniqueDeltaEntries(entries) {
  const seen = new Set();
  return (entries || [])
    .filter((entry) => entry && String(entry.text || "").trim())
    .filter((entry) => {
      const key = `${entry.kind || "changed"}:${String(entry.text || "").trim()}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}
function lineageDistributedDeltaEntries(rowIndex, values) {
  const normalizedValues = (values || []).map(lineageNormalizedValue);
  if (new Set(normalizedValues).size <= 1) return "";
  const entries = [];
  if (rowIndex < normalizedValues.length - 1) {
    const pair = lineagePairDeltaEntries(
      lineageNormalizedLines(normalizedValues[rowIndex] || ""),
      lineageNormalizedLines(normalizedValues[rowIndex + 1] || ""),
    );
    entries.push(...pair.own);
  }
  if (rowIndex > 0) {
    const pair = lineagePairDeltaEntries(
      lineageNormalizedLines(normalizedValues[rowIndex - 1] || ""),
      lineageNormalizedLines(normalizedValues[rowIndex] || ""),
    );
    entries.push(...pair.reference);
  }
  return lineageUniqueDeltaEntries(entries);
}
function renderLineageDeltaEntry(entry) {
  const kind = String(entry?.kind || "changed");
  const text = String(entry?.text || "").trim();
  if (!text) return "";
  const cls = kind === "added" ? "lineage-diff-added" : kind === "removed" || kind === "removed-source" ? "lineage-diff-removed" : "lineage-diff-changed";
  if (kind === "added") return `<span class="${cls}"><strong class="lineage-diff-sign">+</strong> ${escapeHtml(text)}</span>`;
  if (kind === "removed") return `<span class="${cls}"><strong class="lineage-diff-sign">-</strong> ${escapeHtml(text)}</span>`;
  return `<span class="${cls}">${escapeHtml(text)}</span>`;
}
function renderLineageDeltaEntries(entries) {
  const rows = lineageUniqueDeltaEntries(entries).map(renderLineageDeltaEntry).filter(Boolean);
  if (!rows.length) return '<span class="lineage-diff-baseline">baseline</span>';
  return `<pre class="lineage-diff-code">${rows.join("\n")}</pre>`;
}
function renderLineageRuntimeValue(rowIndex, values, showFullParameters) {
  const value = Array.isArray(values) ? values[rowIndex] : "";
  if (showFullParameters) return renderLineageValue(value);
  return renderLineageDeltaEntries(lineageDistributedDeltaEntries(rowIndex, values));
}
function renderPresetLineageContent(selector = "", showFullParameters = false) {
  const original = findVariantBySelector(selector);
  if (!original) return;
  const oldRows = variantOldCounterpartsForOriginal(original);
  const rows = oldRows.length ? [original, ...oldRows] : [original];
  const changedRows = lineageMeaningfulChangedRows(rows);
  const scoreRows = lineageBenchmarkChangedRows(rows);
  const header = `<tr><th>Field</th>${rows.map((row) => `<th>${escapeHtml(variantDisplayLabel(row))}</th>`).join("")}</tr>`;
  const bodyRows = changedRows.length
    ? changedRows
        .map(
          (row) =>
            `<tr><td>${escapeHtml(row.field.label)}</td>${row.values
              .map((_value, index) => `<td>${renderLineageRuntimeValue(index, row.values, showFullParameters)}</td>`)
              .join("")}</tr>`,
        )
        .join("")
    : `<tr><td colspan="${rows.length + 1}"><span class="muted">No runtime-relevant compose or launch-setting differences were found in the current inventory.</span></td></tr>`;
  const scoreBodyRows = scoreRows.length
    ? scoreRows
        .map(
          (row) =>
            `<tr><td>${escapeHtml(row.field.label)}</td>${row.values
              .map((value) => `<td>${renderLineageScoreValue(value)}</td>`)
              .join("")}</tr>`,
        )
        .join("")
    : `<tr><td colspan="${rows.length + 1}"><span class="muted">No Quick or Full score deltas are recorded for this lineage.</span></td></tr>`;
  $("presetLineageTitle").textContent = `${variantDisplayLabel(original)} History`;
  $("presetLineageBody").innerHTML = `<div class="preset-help">Original and preserved OLD presets are compared using the current runtime inventory. Runtime changes and benchmark-score deltas are shown separately so score history never hides a compose-equivalence decision.</div><div class="lineage-section-row"><h3 class="lineage-section-title">Runtime Differences</h3><label class="lineage-full-toggle"><input type="checkbox" onchange="togglePresetLineageFullParameters(this.checked)" ${showFullParameters ? "checked" : ""} /> <span>Show Full Parameters</span></label></div><div class="lineage-diff-table-wrap"><table class="lineage-diff-table">${header}${bodyRows}</table></div><h3 class="lineage-section-title">Benchmark Score Deltas</h3><div class="lineage-diff-table-wrap"><table class="lineage-diff-table">${header}${scoreBodyRows}</table></div>`;
}
function togglePresetLineageFullParameters(checked) {
  presetLineageShowFullParameters = !!checked;
  if (presetLineageActiveSelector) renderPresetLineageContent(presetLineageActiveSelector, presetLineageShowFullParameters);
}
function openPresetLineageModal(selector = "") {
  ensurePresetLineageModal();
  presetLineageActiveSelector = selector;
  presetLineageShowFullParameters = false;
  renderPresetLineageContent(selector, false);
  $("presetLineageModal").classList.remove("hidden");
}
function ensureActionChoiceModal() {
  if ($("actionChoiceModal")) return;
  const doc = currentUiDocument();
  const modal = doc.createElement("div");
  modal.id = "actionChoiceModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card" id="actionChoiceModalCard" role="dialog" aria-modal="true" aria-labelledby="actionChoiceModalTitle"><div class="panel-head"><h2 id="actionChoiceModalTitle">Choose Action</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeActionChoiceModal()">✕</button></div><div class="preset-help" id="actionChoiceModalBody">-</div><div class="preset-form-actions" id="actionChoiceModalChoices"></div><div id="actionChoiceModalDetails"></div><div class="msg" id="actionChoiceModalMsg"></div></div>`;
  doc.body.appendChild(modal);
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
  const doc = currentUiDocument();
  (opts.choices || []).forEach((choice) => {
    if (choice.hidden) return;
    const button = doc.createElement("button");
    button.className = `btn ${choice.className || "green"}`;
    button.textContent = choice.label || "Continue";
    button.onclick = async () => {
      button.disabled = true;
      try {
        const keepOpen = (await choice.onClick()) === false;
        if (!keepOpen) closeActionChoiceModal();
      } catch (e) {
        const text = messageText(e);
        $("actionChoiceModalMsg").textContent = text;
        if (opts.errorTargetId) setElementMsg(opts.errorTargetId, text, "error");
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
      closePresetActionModal();
      post("/admin/rebuild-inventory", {}, "/admin/rebuild-inventory")
        .then(() => refreshStatus({ force: true }))
        .catch((error) => alert(messageText(error)));
    },
  });
}
function waitForUiDelay(ms) {
  return new Promise((resolve) => setTimeout(resolve, Math.max(0, Number(ms || 0))));
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
async function startUpdateFlow(scope, targetCommit = "", options = {}) {
  const normalized = scope === "club3090" || scope === "club3090-compatible" ? "club3090" : "controller";
  if (!options?.skipVersionGuard) {
    const versionInfo =
      typeof currentRemoteUpdateVersionInfo === "function"
        ? currentRemoteUpdateVersionInfo()
        : { needsConfirmation: false };
    if (versionInfo.needsConfirmation) {
      promptStaleUpdateConfirmation(scope, targetCommit);
      return;
    }
  }
  if (normalized === "club3090" && !options?.confirmedMigration) {
    if (benchmarkJobActive()) {
      alert("Stop Model Scores benchmarking before migrating Club-3090.");
      return;
    }
    const targetText = targetCommit
      ? `<br><br><strong>Target commit:</strong> <code>${escapeHtml(String(targetCommit))}</code>`
      : "";
    const confirmed = await openClubConfirmModal({
      title: "Confirm Club-3090 Migration",
      bodyHtml: `Run the full Club-3090 <code>--migrate</code> pass now? This replaces the upstream checkout and should not be run when Benchmarks are in progress.${targetText}`,
      confirmLabel: "Run Migration",
      confirmClass: "red",
      dangerBody: true,
    });
    if (!confirmed) return;
  }
  const payload = { scope: normalized };
  if (normalized === "club3090" && targetCommit) payload.target_commit = targetCommit;
  beginPendingUpdateUi(normalized);
  try {
    await post(
      "/admin/update",
      payload,
      `/admin/update ${normalized}`,
      { silentFailure: true },
    );
    setAuditMsg(
      normalized === "club3090"
        ? "Club-3090 migration launched. Output is streaming to Audit Logs."
        : "Admin script update launched. Output is streaming to Audit Logs.",
    );
  } catch (error) {
    const networkDisconnect = /fetch|network|load failed|connection|failed to fetch/i.test(
      String(error?.message || error || ""),
    );
    if (!networkDisconnect) {
      abandonPendingUpdateUi("Update launch failed before the updater handoff. Restored normal logs.");
      throw error;
    }
    setAuditMsg("The control service restarted before acknowledging the request. Waiting for persisted update status...");
    const recover = async () => {
      if (updateMonitor.active || updateMonitor.completed) return;
      try {
        await refreshStatus({ force: true });
        reconcileUpdateUiFromStatus(lastStatus || {});
      } catch (e) {}
      if (!updateMonitor.active && !updateMonitor.completed) setTimeout(recover, 1000);
    };
    setTimeout(recover, 500);
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
  return sortInventoryVariants(rows);
}
function promptModelInstall(variant) {
  openPresetActionModal({
    title: `Download ${escapeHtml(variant?.model_id || "model")} assets`,
    body: `${escapeHtml(variantDisplayLabel(variant))} is not ready on disk yet. Download the required assets now?<br><br>${escapeHtml(variant?.install_reason || "This preset needs additional model files before it can run.")}`,
    detail: variant?.install_command || "",
    confirmLabel: "Download",
    confirmClass: "green",
    onConfirm: async () => {
      closePresetActionModal();
      if (typeof focusAuditLogs === "function") focusAuditLogs();
      const payload = await post(
        "/admin/model-install",
        {
          model_id: variant.model_id,
          variant_id: variant.variant_id,
          install_command: variant.install_command,
        },
        `/admin/model-install ${variant.model_id} ${variant.variant_id}`,
      );
      refreshStatus({ force: true }).catch(() => {});
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
function renderPresetLaunchSettingField(row, value, index, idPrefix = "presetLaunchSetting") {
  const key = normalizePresetLaunchSettingName(row?.name || "");
  const type = String(row?.type || "string").trim().toLowerCase();
  const isWideOverride = key === "GGUF_FILE" || key === "MODEL_NAME";
  const label = key === "GGUF_FILE"
    ? "GGUF File Override"
    : key === "MODEL_NAME"
      ? "Served Model Name Override"
    : String(row?.label || key || `Setting ${index + 1}`);
  const description = key === "GGUF_FILE"
    ? "Optional explicit GGUF path under /models. Leave blank to use the selected target resource."
    : key === "MODEL_NAME"
      ? "Optional explicit served-model name for vLLM. Leave blank to use the selected target resource name."
    : String(row?.description || "").trim();
  const defaultValue = String(row?.default || "").trim();
  const fieldId = `${idPrefix}${index}`;
  const note = [description, defaultValue ? `Default: ${defaultValue}` : ""].filter(Boolean).join(" ");
  const fieldClass = `preset-launch-settings-field${isWideOverride ? " preset-launch-settings-field-wide" : ""}`;
  if (type === "boolean") {
    return `<label class="${fieldClass}"><span>${escapeHtml(label)}</span><select id="${fieldId}" data-setting-name="${escapeHtml(key)}" data-setting-type="${escapeHtml(type)}" data-setting-default="${escapeHtml(defaultValue)}"><option value="">Use compose default</option><option value="true" ${String(value || "").toLowerCase() === "true" || String(value || "").toLowerCase() === "on" ? "selected" : ""}>true</option><option value="false" ${String(value || "").toLowerCase() === "false" || String(value || "").toLowerCase() === "off" ? "selected" : ""}>false</option></select>${note ? `<small>${escapeHtml(note)}</small>` : ""}</label>`;
  }
  const inputType = type === "integer" || type === "number" ? "number" : "text";
  const stepAttr = type === "integer" ? ' step="1"' : type === "number" ? ' step="any"' : "";
  return `<label class="${fieldClass}"><span>${escapeHtml(label)}</span><input id="${fieldId}" type="${inputType}"${stepAttr} data-setting-name="${escapeHtml(key)}" data-setting-type="${escapeHtml(type)}" data-setting-default="${escapeHtml(defaultValue)}" value="${escapeHtml(value || "")}" placeholder="${escapeHtml(defaultValue || "")}" />${note ? `<small>${escapeHtml(note)}</small>` : ""}</label>`;
}
async function openPresetLaunchSettingsModal(selector) {
  try {
    await ensureFullRuntimeInventory();
  } catch (error) {
    alert(`Unable to load full preset settings: ${messageText(error)}`);
    return;
  }
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
function duplicatePresetEngineFamily(engine) {
  const value = String(engine || "").trim().toLowerCase().replace("_", "-");
  if (["ik-llama", "llamacpp", "llama-cpp"].includes(value)) return "llamacpp";
  return value;
}
function duplicatePresetModelResourceRows(variant) {
  return variantResourceRows(variant).filter((resource) => {
    const role = String(resource?.role || "").trim().toLowerCase();
    return role === "model" || (!role && !presetResourceRowIsProjector(resource));
  });
}
function compatibleDuplicatePresetResources(sourceVariant) {
  const sourceFamily = duplicatePresetEngineFamily(sourceVariant?.engine);
  const sourceEngine = String(sourceVariant?.engine || "").trim().toLowerCase();
  const sourceTopology = String(sourceVariant?.topology || "").trim().toLowerCase();
  const rows = new Map();
  inventoryVariants().forEach((variant) => {
    if (duplicatePresetEngineFamily(variant?.engine) !== sourceFamily) return;
    duplicatePresetModelResourceRows(variant).forEach((resource) => {
      const key = variantResourceIdentityKey(resource);
      if (!key) return;
      if (!rows.has(key)) {
        rows.set(key, {
          key,
          path: String(resource?.path || ""),
          label: presetResourceDisplayLabel(resource),
          sizeBytes: Number(resource?.size_bytes || 0),
          modelId: String(variant?.model_id || ""),
          containerModelPath: String(variant?.model_path || ""),
          variant,
          resource,
          usages: [],
          engines: new Set(),
          models: new Set(),
        });
      }
      const entry = rows.get(key);
      entry.sizeBytes = Math.max(entry.sizeBytes, Number(resource?.size_bytes || 0));
      if (!entry.path || String(resource?.path || "").length < entry.path.length) entry.path = String(resource?.path || "");
      entry.usages.push({ variant, resource });
      entry.engines.add(prettyEngineName(variant?.engine_display || variant?.engine));
      entry.models.add(String(variant?.model_display_name || variant?.model_id || "").trim());
      const exactEngine = String(variant?.engine || "").trim().toLowerCase() === sourceEngine;
      const exactTopology = String(variant?.topology || "").trim().toLowerCase() === sourceTopology;
      const currentRank = entry.rank || [9, 9, 9, ""];
      const nextRank = [
        exactEngine ? 0 : 1,
        exactTopology ? 0 : 1,
        ["production", "production_caveat"].includes(String(variant?.status_kind || "").trim()) ? 0 : 1,
        variantSelector(variant),
      ];
      if (JSON.stringify(nextRank) < JSON.stringify(currentRank)) {
        entry.rank = nextRank;
        entry.modelId = String(variant?.model_id || "");
        entry.containerModelPath = String(variant?.model_path || "");
        entry.variant = variant;
        entry.resource = resource;
      }
    });
  });
  return [...rows.values()]
    .map((entry) => ({
      ...entry,
      engines: [...entry.engines].filter(Boolean),
      models: [...entry.models].filter(Boolean),
    }))
    .sort(
      (left, right) =>
        String(left.label || "").localeCompare(String(right.label || "")) ||
        String(left.path || "").localeCompare(String(right.path || "")),
    );
}
function sourceDuplicatePresetResourceKey(variant) {
  return variantResourceIdentityKey(duplicatePresetModelResourceRows(variant)[0] || {});
}
function duplicatePresetResourceOptionLabel(entry) {
  const size = Number(entry?.sizeBytes || 0) > 0 ? ` · ${formatDiskBytes(entry.sizeBytes)}` : "";
  const models = Array.isArray(entry?.models) && entry.models.length ? ` · ${entry.models.slice(0, 2).join(" / ")}` : "";
  return `${entry?.label || entry?.path || entry?.key || "Model resource"}${size}${models}`;
}
let duplicatePresetTargetResourceRows = [];
function duplicatePresetResourcePickerHtml(entry) {
  const key = String(entry?.key || "");
  const label = duplicatePresetResourceOptionLabel(entry);
  return `<span class="duplicate-resource-picker-dot" style="--preset-resource-color:${escapeHtml(resourceColorForKey(key))}"></span><span class="duplicate-resource-picker-text">${escapeHtml(label)}</span>`;
}
function closeDuplicatePresetTargetMenu() {
  $("duplicatePresetTargetMenu")?.classList.add("hidden");
  $("duplicatePresetTargetButton")?.setAttribute("aria-expanded", "false");
}
function toggleDuplicatePresetTargetMenu(event) {
  event?.preventDefault?.();
  const menu = $("duplicatePresetTargetMenu");
  const button = $("duplicatePresetTargetButton");
  if (!menu || !button || button.disabled) return;
  const opening = menu.classList.contains("hidden");
  menu.classList.toggle("hidden", !opening);
  button.setAttribute("aria-expanded", opening ? "true" : "false");
}
function selectDuplicatePresetTargetResource(key, closeMenu = true) {
  const value = String(key || "").trim();
  const entry = duplicatePresetTargetResourceRows.find((row) => String(row?.key || "") === value) || duplicatePresetTargetResourceRows[0] || null;
  const input = $("duplicatePresetTargetModel");
  const button = $("duplicatePresetTargetButton");
  if (!input || !button) return;
  if (!entry) {
    input.value = "";
    button.innerHTML = `<span class="duplicate-resource-picker-text">No compatible resources found</span>`;
    button.disabled = true;
    closeDuplicatePresetTargetMenu();
    return;
  }
  const selectedKey = String(entry.key || "");
  input.value = selectedKey;
  button.disabled = false;
  button.innerHTML = duplicatePresetResourcePickerHtml(entry);
  document.querySelectorAll(".duplicate-resource-picker-option").forEach((node) => {
    node.classList.toggle("selected", String(node.getAttribute("data-resource-key") || "") === selectedKey);
  });
  if (closeMenu) closeDuplicatePresetTargetMenu();
}
function duplicatePresetDefaultName(variant) {
  const selector = variantSelector(variant);
  const base = String(selector || variantDisplayLabel(variant) || "custom-preset")
    .replace(/^custom\//, "")
    .replace(/[^A-Za-z0-9/_-]+/g, "-")
    .replace(/[\/]+/g, "-")
    .replace(/-+$/g, "")
    .replace(/^-+/g, "");
  return `${base || "custom-preset"}-optimized`;
}
function ensureDuplicatePresetModal() {
  if ($("duplicatePresetModal")) return;
  const modal = document.createElement("div");
  modal.id = "duplicatePresetModal";
  modal.className = "club-modal hidden";
  modal.innerHTML = `<div class="club-modal-card duplicate-preset-modal-card" role="dialog" aria-modal="true" aria-labelledby="duplicatePresetTitle"><div class="panel-head"><h2 id="duplicatePresetTitle">Duplicate Preset</h2><button class="plain-close-btn" title="Close" aria-label="Close" onclick="closeDuplicatePresetModal()">✕</button></div><div class="preset-help" id="duplicatePresetHint"></div><div class="duplicate-preset-sections"><details class="duplicate-preset-section" open><summary>Identity</summary><div class="formgrid duplicate-preset-form-grid"><label>Preset name<input id="duplicatePresetName" class="club-text-field" autocomplete="off" spellcheck="false" /></label><div class="duplicate-resource-picker-field"><span>Target model resource</span><input id="duplicatePresetTargetModel" type="hidden" /><button id="duplicatePresetTargetButton" type="button" class="duplicate-resource-picker-button" aria-expanded="false" onclick="toggleDuplicatePresetTargetMenu(event)">Select target model resource</button><div id="duplicatePresetTargetMenu" class="duplicate-resource-picker-menu hidden"></div></div><div class="preset-help duplicate-resource-help">Targets are downloaded model resources from the same engine family as the source preset.</div></div></details><details class="duplicate-preset-section" open><summary>Launch Settings</summary><div id="duplicatePresetSettingsGrid" class="preset-launch-settings-grid"></div><label class="preset-launch-settings-raw-label">Additional env overrides<textarea id="duplicatePresetExtraEnv" class="preset-launch-settings-raw" placeholder="NAME=value&#10;OTHER_FLAG=1"></textarea></label></details><details class="duplicate-preset-section"><summary>Engine Switches</summary><label class="preset-launch-settings-raw-label custom-model-engine-switches-label">Custom engine switches<textarea id="duplicatePresetCommandText" class="preset-launch-settings-raw" placeholder="One engine argument per line." spellcheck="false"></textarea></label></details></div><div class="preset-form-actions"><button class="btn blue" onclick="closeDuplicatePresetModal()">Cancel</button><button class="btn green" onclick="submitDuplicatePresetModal()">Duplicate</button></div><div class="msg" id="duplicatePresetMsg"></div></div>`;
  document.body.appendChild(modal);
}
function setDuplicatePresetMsg(text, tone = "warning") {
  setElementMsg("duplicatePresetMsg", text || "", tone);
}
async function openDuplicatePresetModal(selector) {
  if (benchmarkJobActive()) {
    alert("Model Scores benchmarking is running. Cancel the benchmark before creating custom presets.");
    return;
  }
  try {
    await ensureFullRuntimeInventory();
  } catch (error) {
    alert(`Unable to load full preset settings: ${messageText(error)}`);
    return;
  }
  const variant = inventoryVariants().find((item) => variantSelector(item) === selector || item?.variant_id === selector);
  if (!variant) {
    alert("Preset not found in runtime inventory.");
    return;
  }
  ensureDuplicatePresetModal();
  const settings = variantLaunchSettings(variant);
  const defaults = variantLaunchEnvDefaults(variant);
  const savedEnv = variantSavedLaunchEnv(variant);
  const knownKeys = new Set(Object.keys(defaults));
  const targetResources = compatibleDuplicatePresetResources(variant);
  const currentResourceKey = sourceDuplicatePresetResourceKey(variant);
  duplicatePresetTargetResourceRows = targetResources;
  const selectedResourceKey = targetResources.some((entry) => String(entry?.key || "") === currentResourceKey)
    ? currentResourceKey
    : String(targetResources[0]?.key || "");
  setHtmlIfChanged(
    $("duplicatePresetTargetMenu"),
    targetResources
      .map((entry) => {
        const key = String(entry?.key || "");
        return `<button type="button" class="duplicate-resource-picker-option" data-resource-key="${escapeHtml(key)}" onclick="selectDuplicatePresetTargetResource('${escapeJs(key)}')">${duplicatePresetResourcePickerHtml(entry)}</button>`;
      })
      .join(""),
  );
  selectDuplicatePresetTargetResource(selectedResourceKey, false);
  setHtmlIfChanged(
    $("duplicatePresetSettingsGrid"),
    settings.length
      ? settings
          .map((row, index) => {
            const key = normalizePresetLaunchSettingName(row?.name || "");
            const current = savedEnv[key] ?? (key === "GGUF_FILE" ? "" : defaults[key] ?? "");
            return renderPresetLaunchSettingField(row, current, index, "duplicatePresetSetting");
          })
          .join("")
      : `<div class="preset-help">This preset does not advertise structured launch fields yet. Use the engine switches and env overrides to customize the duplicate.</div>`,
  );
  $("duplicatePresetExtraEnv").value = Object.entries(savedEnv)
    .filter(([key]) => !knownKeys.has(String(key || "").trim().toUpperCase()))
    .map(([key, value]) => `${key}=${value}`)
    .join("\n");
  $("duplicatePresetCommandText").value = variantResolvedLaunchCommandText(variant);
  $("duplicatePresetName").value = duplicatePresetDefaultName(variant);
  $("duplicatePresetModal").dataset.selector = variantSelector(variant);
  $("duplicatePresetHint").innerHTML = `Create a Custom preset from <code>${escapeHtml(variantDisplayLabel(variant))}</code>. The duplicate is registered into the model inventory and can be tuned or deleted later.`;
  setDuplicatePresetMsg("");
  $("duplicatePresetModal")?.classList.remove("hidden");
}
function closeDuplicatePresetModal() {
  closeDuplicatePresetTargetMenu();
  $("duplicatePresetModal")?.classList.add("hidden");
}
function collectLaunchSettingsEnvFrom(gridSelector, extraEnvId) {
  const env = {};
  document.querySelectorAll(`${gridSelector} [data-setting-name]`).forEach((node) => {
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
  String($(extraEnvId)?.value || "")
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
  return env;
}
async function submitDuplicatePresetModal() {
  try {
    const sourceSelector = String($("duplicatePresetModal")?.dataset?.selector || "").trim();
    const sourceVariant = inventoryVariants().find((item) => variantSelector(item) === sourceSelector || item?.variant_id === sourceSelector);
    if (!sourceVariant) throw new Error("Source preset is missing.");
    const env = collectLaunchSettingsEnvFrom("#duplicatePresetSettingsGrid", "duplicatePresetExtraEnv");
    const defaults = variantLaunchEnvDefaults(sourceVariant);
    const commandText = resolvePresetLaunchCommandText(String($("duplicatePresetCommandText")?.value || ""), defaults, env);
    const targetResources = compatibleDuplicatePresetResources(sourceVariant);
    const targetResourceKey = String($("duplicatePresetTargetModel")?.value || "").trim();
    const targetResource = targetResources.find((entry) => String(entry?.key || "") === targetResourceKey) || null;
    if (!targetResource) throw new Error("Choose a compatible target model resource first.");
    const payload = await post(
      "/admin/custom-presets",
      {
        action: "duplicate",
        selector: sourceSelector,
        name: String($("duplicatePresetName")?.value || "").trim(),
        target_model_id: String(targetResource.modelId || "").trim(),
        target_model_resource_key: targetResourceKey,
        target_model_resource_path: String(targetResource.path || "").trim(),
        env,
        command_text: commandText,
      },
      `/admin/custom-presets duplicate ${sourceSelector}`,
    );
    if (payload?.runtime_inventory) {
      if (!lastStatus) lastStatus = {};
      lastStatus.runtime_inventory = payload.runtime_inventory;
      lastStatus.models = payload.models || payload.runtime_inventory.models || [];
      lastStatus.variants = payload.variants || payload.runtime_inventory.variants || [];
      writeRuntimeInventoryCacheFromStatus(lastStatus);
    }
    closeDuplicatePresetModal();
    renderPresetModelSelector();
    renderDynamicPresetModels({ force: true });
    await refreshStatus({ force: true });
  } catch (e) {
    setDuplicatePresetMsg(messageText(e), "error");
  }
}
async function promptDeleteCustomPreset(selector) {
  if (benchmarkJobActive()) {
    alert("Model Scores benchmarking is running. Cancel the benchmark before deleting custom presets.");
    return;
  }
  const key = String(selector || "").trim();
  const variant = inventoryVariants().find((item) => variantSelector(item) === key || item?.variant_id === key);
  if (!variant || !variantIsRegistryBackedPreset(variant)) return;
  openPresetActionModal({
    title: "Delete Custom Preset",
    body: `Delete custom preset <code>${escapeHtml(variantDisplayLabel(variant))}</code>? This removes its copied compose file and unregisters it from the Model DB.`,
    confirmLabel: "Delete",
    confirmClass: "red",
    onConfirm: async () => {
      const payload = await post(
        "/admin/custom-presets",
        { action: "delete", selector: key },
        `/admin/custom-presets delete ${key}`,
      );
      if (payload?.runtime_inventory) {
        if (!lastStatus) lastStatus = {};
        lastStatus.runtime_inventory = payload.runtime_inventory;
        lastStatus.models = payload.models || payload.runtime_inventory.models || [];
        lastStatus.variants = payload.variants || payload.runtime_inventory.variants || [];
        writeRuntimeInventoryCacheFromStatus(lastStatus);
      }
      renderPresetModelSelector();
      renderDynamicPresetModels({ force: true });
      await refreshStatus({ force: true });
    },
  });
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
function modelResourceFileDisplayLabel(path, usages = []) {
  const cleanPath = String(path || "").trim();
  const fileName = cleanPath.split(/[\\/]/).filter(Boolean).pop() || "Downloaded model resource";
  if (fileName !== "model.safetensors") return fileName;
  const usageModels = [
    ...new Set(
      (usages || [])
        .map(({ variant }) => String(variant?.model_display_name || variant?.model_id || "").trim())
        .filter(Boolean),
    ),
  ];
  const parts = cleanPath.split(/[\\/]/).filter(Boolean);
  const parent = parts.length >= 2 ? parts[parts.length - 2] : "";
  if (parent) return `${parent}.safetensors`;
  if (usageModels.length === 1) return `${usageModels[0]}.safetensors`;
  return fileName;
}
function resourcePathLooksLikeModelPayload(path) {
  return /\.(?:gguf|safetensors|bin|pt|pth|model|onnx|npy)$/i.test(String(path || "").split(/[\\/]/).pop() || "");
}
function resourceManagerModality(entry = {}) {
  const explicitModality = String(entry.modality || "").trim().toLowerCase();
  if (explicitModality === "text") return "text";
  const text = `${entry.modality || ""} ${entry.label || ""} ${entry.path || ""} ${entry.role || ""}`.toLowerCase();
  if (/(?:^|[^a-z0-9])(director|studio[-_]?director|qwen3\.5|hauhaucs|mmproj)(?:[^a-z0-9]|$)/.test(text)) return "text";
  if (/(?:^|[^a-z0-9])(video|ltx|sulphur|sulfur|10eros|wan|wan2\.2|hunyuan)/.test(text)) return "video";
  if (/(?:^|[^a-z0-9])(speech|voice|tts|kokoro|step[-_]?voice|step[-_]?audio|editx|narrat)/.test(text)) return "speech";
  if (/(?:^|[^a-z0-9])(audio|music|sfx|tts|stable[-_]?audio|ace[-_]?step|mp3|wav|flac|opus)/.test(text)) return "audio";
  if (/(?:^|[^a-z0-9])(image|comfyui|ideogram|hidream|chroma|z[-_]?image|krea|flux|vae|text_encoder|diffusion_models|qwen3vl|qwen_3_4b|qwen_image)/.test(text)) return "image";
  return "";
}
function resourceManagerModalityIcon(entry = {}) {
  const modality = resourceManagerModality(entry);
  if (!modality) return "";
  const label = { image: "Image model", audio: "Audio model", speech: "Speech synthesis model", video: "Video model", text: "Studio support model" }[modality] || "Studio model";
  const icon = { image: "image", audio: "music", speech: "megaphone", video: "play", text: "chat" }[modality] || "file";
  return `<span class="resource-manager-modality-icon resource-manager-modality-${escapeHtml(modality)}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">${svgIcon(icon)}</span>`;
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
function resourceColorOverrides() {
  const parsed = lastStatus?.resource_colors;
  return {
    ...(parsed && typeof parsed === "object" ? parsed : {}),
    ...pendingResourceColorOverrides,
  };
}
async function saveResourceColorOverrides(overrides) {
  Object.entries(overrides || {}).forEach(([key, color]) => {
    pendingResourceColorOverrides[key] = color;
  });
  if (!lastStatus) lastStatus = {};
  lastStatus.resource_colors = { ...(overrides || {}) };
  const payload = await post(
    "/admin/resource-colors",
    { resource_colors: overrides || {} },
    "/admin/resource-colors save",
    { silentSuccess: true },
  );
  const confirmed = payload?.resource_colors || overrides || {};
  lastStatus.resource_colors = confirmed;
  Object.entries(overrides || {}).forEach(([key, color]) => {
    if (String(confirmed[key] || "").toLowerCase() === String(color || "").toLowerCase()) {
      delete pendingResourceColorOverrides[key];
    }
  });
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
  const overrides = resourceColorOverrides();
  let changed = false;
  [...new Set(signature.split("|").filter(Boolean))].forEach((key) => {
    const requested = String(overrides[key] || "").trim();
    const color =
      requested && resourceMarkerColorIsDistinct(requested, usedColors)
        ? requested
        : chooseResourceMarkerColor(key, usedColors, usedColors.length);
    map.set(key, color);
    usedColors.push(color);
    if (overrides[key] !== color) {
      overrides[key] = color;
      changed = true;
    }
  });
  if (changed) saveResourceColorOverrides(overrides).catch(() => {});
  return map;
}
function resourceColorForKey(key) {
  const cleanKey = String(key || "").trim();
  if (!cleanKey) return "#7aa2c8";
  let color = resourceColorAssignmentMap().get(cleanKey) || chooseResourceMarkerColor(cleanKey, []);
  if (String(color).toLowerCase() === "#000000") color = "#6f7b88";
  return color;
}
async function randomizeResourceMarkerColor(key) {
  const cleanKey = String(key || "").trim();
  if (!cleanKey) return;
  const assignments = resourceColorAssignmentMap();
  const current = String(assignments.get(cleanKey) || "").toLowerCase();
  const usedColors = [...assignments.entries()]
    .filter(([otherKey]) => otherKey !== cleanKey)
    .map(([, color]) => color);
  const seed = hashTextToUint(`${cleanKey}:${Date.now()}:${Math.random()}`);
  let next = "";
  for (let attempt = 0; attempt < 360; attempt += 1) {
    const candidate = generatedResourceMarkerColor(seed, attempt);
    if (
      candidate.toLowerCase() !== current &&
      resourceMarkerColorIsDistinct(candidate, usedColors)
    ) {
      next = candidate;
      break;
    }
  }
  if (!next) next = chooseResourceMarkerColor(`${cleanKey}:${seed}`, usedColors);
  const overrides = resourceColorOverrides();
  overrides[cleanKey] = next;
  renderDynamicPresetModels({ force: true });
  await saveResourceColorOverrides(overrides);
  renderDynamicPresetModels({ force: true });
}
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
  const path = String(row?.path || "").trim();
  const label = path && resourcePathLooksLikeModelPayload(path) ? path : presetResourceDisplayLabel(row);
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
  return `<button type="button" class="preset-tps-label" title="${escapeHtml(title)}" aria-label="TPS history for ${escapeHtml(key)}" onpointerdown="beginPresetTpsLabelPress(event,'${escapeJs(key)}')" onpointerup="cancelPresetTpsLabelPress()" onpointerleave="cancelPresetTpsLabelPress()" onpointercancel="cancelPresetTpsLabelPress()" onclick="handlePresetTpsLabelClick(event,'${escapeJs(key)}')"><span>Max. TPS: ${escapeHtml(maxTps)}</span><span>Avg. TPS: ${escapeHtml(avgTps)}</span></button>`;
}
function renderPresetCacheClearButton(variant, disabled = false) {
  const selector = variantSelector(variant);
  if (!selector) return "";
  return renderIconButton({
    title: `Clear cache for ${variantDisplayLabel(variant)}`,
    action: `promptClearPresetCaches('${escapeJs(selector)}')`,
    icon: "recycle",
    className: "variant-cache-clear-btn",
    disabled,
  });
}
function renderVariantMetricsGroup(variant) {
  const selector = variantSelector(variant);
  if (!selector) return "";
  return `<div class="variant-metrics-group">${renderPresetDiskLabel(variant)}${renderPresetTpsLabel(selector)}</div>`;
}
function renderDuplicatePresetButton(variant) {
  const selector = variantSelector(variant);
  if (!selector) return "";
  return renderIconButton({
    title: `Duplicate ${variantDisplayLabel(variant)}`,
    action: `openDuplicatePresetModal('${escapeJs(selector)}')`,
    icon: "copy",
    className: "variant-duplicate-btn",
  });
}
function renderDeleteCustomPresetButton(variant, disabled = false) {
  const selector = variantSelector(variant);
  if (!selector || !variantIsRegistryBackedPreset(variant)) return "";
  return renderIconButton({
    title: `Delete custom preset ${variantDisplayLabel(variant)}`,
    action: `promptDeleteCustomPreset('${escapeJs(selector)}')`,
    icon: "delete",
    className: "variant-custom-delete-btn",
    disabled,
  });
}
function renderVariantSettingsCluster(variant, options = {}) {
  const selector = variantSelector(variant);
  const visibilityButton = renderHiddenPresetToggleIcon(variant, false);
  const cacheButton = renderPresetCacheClearButton(variant, !!options.cacheDisabled);
  const settingsButton = renderIconButton({
    title: "Launch settings",
    action: `openPresetLaunchSettingsModal('${escapeJs(selector)}')`,
    icon: "gear",
    className: "variant-settings-btn",
  });
  return `<span class="variant-settings-cluster">${renderDuplicatePresetButton(variant)}${renderDeleteCustomPresetButton(variant, !!options.deleteDisabled)}${visibilityButton}${cacheButton}${settingsButton}</span>`;
}
function applyRuntimeInventoryMutationPayload(payload = {}) {
  if (!payload?.runtime_inventory) return;
  if (!lastStatus) lastStatus = {};
  lastStatus.runtime_inventory = payload.runtime_inventory;
  lastStatus.models = payload.models || payload.runtime_inventory.models || [];
  lastStatus.variants = payload.variants || payload.runtime_inventory.variants || [];
  writeRuntimeInventoryCacheFromStatus(lastStatus);
  syncPresetSummaryCacheFromStatus(lastStatus);
}
async function refreshAfterResourceMutation(payload = {}) {
  applyRuntimeInventoryMutationPayload(payload);
  await refreshStatus({ force: true, includeInventory: true });
  applyRuntimeInventoryMutationPayload(lastStatus || {});
  renderDynamicPresetModels({ force: true });
  const removedCount = Number(payload?.removed_count || 0);
  const removedBytes = Number(payload?.removed_size_bytes || 0);
  const errors = Array.isArray(payload?.errors) ? payload.errors : [];
  const tone = payload?.ok && !errors.length ? "success" : "error";
  const message = payload?.ok
    ? `Resource cleanup finished: removed ${removedCount} item${removedCount === 1 ? "" : "s"} (${formatDiskBytes(removedBytes)}).`
    : `Resource cleanup failed${errors.length ? `: ${errors.map((row) => row?.error || row?.path || String(row)).join("; ")}` : "."}`;
  setElementMsg("presetResourceMsg", message, tone);
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
    title: "Preset Resource Actions",
    errorTargetId: "presetResourceMsg",
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
          const payload = await post(
            "/admin/preset-caches/delete",
            { selector: key, variant_id: variant.variant_id },
            `/admin/preset-caches/delete ${key}`,
          );
          await refreshAfterResourceMutation(payload);
        },
      },
      {
        label: "Delete Model",
        className: "red",
        onClick: async () => {
          setElementMsg("actionChoiceModalMsg", "Deleting model resources and rebuilding inventory...", "warning");
          setElementMsg("presetResourceMsg", "Deleting model resources and rebuilding inventory...", "warning");
          const payload = await post(
            "/admin/model-resources/delete",
            { selector: key, variant_id: variant.variant_id },
            `/admin/model-resources/delete ${key}`,
          );
          await refreshAfterResourceMutation(payload);
        },
      },
      {
        label: "Delete Model + Caches",
        className: "rose",
        onClick: async () => {
          setElementMsg("actionChoiceModalMsg", "Deleting model resources, caches, and rebuilding inventory...", "warning");
          setElementMsg("presetResourceMsg", "Deleting model resources, caches, and rebuilding inventory...", "warning");
          const payload = await post(
            "/admin/model-resources/delete-with-caches",
            { selector: key, variant_id: variant.variant_id },
            `/admin/model-resources/delete-with-caches ${key}`,
          );
          await refreshAfterResourceMutation(payload);
        },
      },
    ],
  });
}
async function promptClearPresetCaches(selector) {
  if (benchmarkJobActive()) {
    alert("Model Scores benchmarking is running. Cancel the benchmark before clearing caches.");
    return;
  }
  const key = String(selector || "").trim();
  const variant = inventoryVariants().find((item) => variantSelector(item) === key || item?.variant_id === key);
  if (!variant) {
    alert("Preset not found in runtime inventory.");
    return;
  }
  let cachePlan = null;
  let resourcePlan = null;
  try {
    [cachePlan, resourcePlan] = await Promise.all([
      post(
        "/admin/preset-caches/plan",
        { selector: key, variant_id: variant.variant_id },
        `/admin/preset-caches/plan ${key}`,
        { silentSuccess: true },
      ),
      post(
        "/admin/model-resources/plan",
        { selector: key, variant_id: variant.variant_id },
        `/admin/model-resources/plan ${key}`,
        { silentSuccess: true },
      ),
    ]);
  } catch (error) {
    alert(messageText(error));
    return;
  }
  const caches = (Array.isArray(cachePlan?.caches) ? cachePlan.caches : []).filter((row) => row?.exists);
  const resources = (Array.isArray(resourcePlan?.resources) ? resourcePlan.resources : []).filter((row) => row?.exists);
  if (!caches.length && !resources.length) {
    openPresetActionModal({
      title: "Preset Resource Actions",
      body: `No runtime caches or downloaded resources were found for <code>${escapeHtml(variantDisplayLabel(variant))}</code>.`,
      confirmLabel: "Close",
      confirmClass: "blue",
      onConfirm: async () => {},
    });
    return;
  }
  const total = Number(resourcePlan?.resource_size_bytes || 0);
  const cacheTotal = Number(cachePlan?.cache_size_bytes || 0);
  const rowsHtml = [
    ...resources.map(
      (row) =>
        `<div class="resource-delete-row"><code>${escapeHtml(row.path || "")}</code><span>${escapeHtml(formatDiskBytes(row.size_bytes || 0))}</span></div>`,
    ),
    ...caches.map(
      (row) =>
        `<div class="resource-delete-row"><code>${escapeHtml(row.path || "")}</code><span>${escapeHtml(formatDiskBytes(row.size_bytes || 0))}</span></div>`,
    ),
  ].join("");
  openActionChoiceModal({
    title: "Preset Resource Actions",
    errorTargetId: "presetResourceMsg",
    body: `<div>Choose what to clear for <code>${escapeHtml(variantDisplayLabel(variant))}</code>.</div><div class="preset-help resource-delete-summary">${escapeHtml(formatResourcePlusCacheBytes(total, cacheTotal))} is associated with this preset.</div>`,
    detailsHtml: `<div class="resource-delete-list">${rowsHtml}</div>`,
    choices: [
      { label: "Cancel", className: "blue", onClick: async () => {} },
      {
        label: "Delete Cache",
        className: "orange",
        hidden: cacheTotal <= 0,
        onClick: async () => {
          const payload = await post(
            "/admin/preset-caches/delete",
            { selector: key, variant_id: variant.variant_id },
            `/admin/preset-caches/delete ${key}`,
          );
          await refreshAfterResourceMutation(payload);
        },
      },
      {
        label: "Delete Model",
        className: "red",
        hidden: !resources.length,
        onClick: async () => {
          const payload = await post(
            "/admin/model-resources/delete",
            { selector: key, variant_id: variant.variant_id },
            `/admin/model-resources/delete ${key}`,
          );
          await refreshAfterResourceMutation(payload);
        },
      },
      {
        label: "Delete Model + Cache",
        className: "rose",
        hidden: !resources.length,
        onClick: async () => {
          const payload = await post(
            "/admin/model-resources/delete-with-caches",
            { selector: key, variant_id: variant.variant_id },
            `/admin/model-resources/delete-with-caches ${key}`,
          );
          await refreshAfterResourceMutation(payload);
        },
      },
    ],
  });
}
async function promptDeleteResourcePaths(paths, label = "resource", selectors = []) {
  const cleanPaths = [...new Set((paths || []).map((path) => String(path || "").trim()).filter(Boolean))];
  const cleanSelectors = [...new Set((selectors || []).map((selector) => String(selector || "").trim()).filter(Boolean))];
  if (!cleanPaths.length) return;
  const matchingRows = inventoryResourceManagerRows()
    .filter((entry) => cleanPaths.includes(String(entry.path || "")) || entry.usages.some(({ resource }) => cleanPaths.includes(String(resource?.path || ""))));
  const total = matchingRows.reduce((sum, entry) => sum + Number(entry.sizeBytes || 0), 0);
  const associatedCaches = new Map();
  matchingRows.forEach((entry) => {
    (entry.usages || []).forEach(({ variant }) => {
      (Array.isArray(variant?.cache_entries) ? variant.cache_entries : []).forEach((cache) => {
        const path = String(cache?.path || "").trim();
        if (path && !associatedCaches.has(path)) {
          associatedCaches.set(path, Number(cache?.size_bytes || 0));
        }
      });
    });
  });
  const cacheTotal = [...associatedCaches.values()].reduce((sum, size) => sum + size, 0);
  const rowsHtml = [
    ...cleanPaths.map(
      (path) => `<div class="resource-delete-row"><code>${escapeHtml(path)}</code><span>Model</span></div>`,
    ),
    ...[...associatedCaches.entries()].map(
      ([path, size]) =>
        `<div class="resource-delete-row"><code>${escapeHtml(path)}</code><span>Cache · ${escapeHtml(formatDiskBytes(size))}</span></div>`,
    ),
  ]
    .join("");
  openActionChoiceModal({
    title: "Clear Model Resource",
    errorTargetId: "presetResourceMsg",
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
          let payload = null;
          for (const selector of cleanSelectors) {
            payload = await post(
              "/admin/preset-caches/delete",
              { selector },
              `/admin/preset-caches/delete ${selector}`,
              { silentSuccess: true },
            );
          }
          await refreshAfterResourceMutation(payload || {});
        },
      },
      {
        label: "Delete Model",
        className: "red",
        onClick: async () => {
          setElementMsg("actionChoiceModalMsg", "Deleting model resource and rebuilding inventory...", "warning");
          setElementMsg("presetResourceMsg", "Deleting model resource and rebuilding inventory...", "warning");
          const payload = await post(
            "/admin/model-resources/delete",
            { paths: cleanPaths },
            `/admin/model-resources/delete ${cleanPaths.length} path(s)`,
          );
          await refreshAfterResourceMutation(payload);
        },
      },
      {
        label: "Delete Model + Caches",
        className: "rose",
        onClick: async () => {
          setElementMsg("actionChoiceModalMsg", "Deleting model resource, caches, and rebuilding inventory...", "warning");
          setElementMsg("presetResourceMsg", "Deleting model resource, caches, and rebuilding inventory...", "warning");
          const payload = await post(
            "/admin/model-resources/delete-with-caches",
            { paths: cleanPaths, selectors: cleanSelectors },
            `/admin/model-resources/delete-with-caches ${cleanPaths.length} path(s)`,
          );
          await refreshAfterResourceMutation(payload);
        },
      },
    ],
  });
}
async function promptDeleteModelCachePaths(paths, label = "model cache") {
  if (benchmarkJobActive()) {
    alert("Model Scores benchmarking is running. Cancel the benchmark before clearing model caches.");
    return;
  }
  const cleanPaths = [...new Set((paths || []).map((path) => String(path || "").trim()).filter(Boolean))];
  if (!cleanPaths.length) return;
  const matchingRows = inventoryResourceManagerRows()
    .filter((entry) => cleanPaths.includes(String(entry.path || "")));
  const total = matchingRows.reduce(
    (sum, entry) => sum + Number(entry.cacheSizeBytes || entry.sizeBytes || 0),
    0,
  );
  const rowsHtml = cleanPaths
    .map((path) => `<div class="resource-delete-row"><code>${escapeHtml(path)}</code></div>`)
    .join("");
  openActionChoiceModal({
    title: "Clear Model Cache",
    body: `<div>Clear model cache <code>${escapeHtml(label || "model cache")}</code>?</div><div class="preset-help resource-delete-summary">${escapeHtml(formatDiskBytes(total || 0))} is associated with this cache entry.</div>`,
    detailsHtml: `<div class="resource-delete-list">${rowsHtml}</div>`,
    choices: [
      {
        label: "Cancel",
        className: "blue",
        onClick: async () => {},
      },
      {
        label: "Delete Cache",
        className: "red",
        onClick: async () => {
          const payload = await post(
            "/admin/model-cache/delete",
            { paths: cleanPaths },
            `/admin/model-cache/delete ${cleanPaths.length} path(s)`,
          );
          await refreshAfterResourceMutation(payload);
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
function modelInstallStateForVariant(variant) {
  const jobs = Array.isArray(lastStatus?.model_install_jobs) ? lastStatus.model_install_jobs : [];
  const variantId = String(variant?.variant_id || "");
  const ownJob = jobs.find(
    (job) =>
      job &&
      job.active &&
      String(job.model_id || "") === String(variant?.model_id || "") &&
      String(job.variant_id || "") === variantId,
  );
  if (ownJob) return { job: ownJob, shared: false };
  const sharedJob = jobs.find(
    (job) =>
      job &&
      job.active &&
      Array.isArray(job.affected_variant_ids) &&
      job.affected_variant_ids.some((item) => String(item || "") === variantId),
  );
  return { job: sharedJob || null, shared: !!sharedJob };
}
function sharedModelInstallDescription(job = {}) {
  const owner = String(job?.selector || job?.variant_id || "another preset");
  return `Shared assets are downloading for ${owner} (${modelInstallProgressPercent(job)}%).`;
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
  const installState = modelInstallStateForVariant(variant);
  return { selector, target, targetId, active, switching, failed, installing: installState.job, sharedInstalling: installState.shared };
}
function inventoryResourceManagerRows() {
  const map = new Map();
  const payloadFileEntries = (runtimeInventory()?.model_resource_file_entries || [])
    .map((entry) => ({ ...entry, path: String(entry?.path || "").trim() }))
    .filter((entry) => entry.path);
  const normalizedResourcePath = (path) =>
    String(path || "").replaceAll("\\", "/").replace(/\/+$/, "");
  const payloadEntryMatchesResource = (entry, resource) => {
    const filePath = normalizedResourcePath(entry?.path);
    const rootPath = normalizedResourcePath(entry?.root_path);
    const resourcePath = normalizedResourcePath(resource?.path);
    if (!resourcePath) return false;
    return filePath === resourcePath || rootPath === resourcePath;
  };
  inventoryVariants().forEach((variant) => {
    variantResourceRows(variant).forEach((resource) => {
      const key = variantResourceIdentityKey(resource);
      if (!key) return;
      const resourcePath = String(resource?.path || "").trim();
      const hasConcretePayloadRows = resourcePath && !resourcePathLooksLikeModelPayload(resourcePath)
        ? payloadFileEntries.some((entry) => payloadEntryMatchesResource(entry, resource))
        : false;
      if (hasConcretePayloadRows) return;
      if (!map.has(key)) {
        map.set(key, {
          key,
          label: presetResourceDisplayLabel(resource),
          path: resourcePath,
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
      }
      entry.models.add(String(variant?.model_display_name || variant?.model_id || ""));
      variantSourceRepoCandidates(variant).forEach((repo) => entry.repos.add(repo));
    });
  });
  const rows = [...map.values()];
  const attachedPaths = new Set(rows.map((entry) => String(entry.path || "").trim()).filter(Boolean));
  payloadFileEntries.forEach((entry) => {
    const path = entry.path;
    if (!path || attachedPaths.has(path)) return;
    const matchingUsages = [];
    inventoryVariants().forEach((variant) => {
      variantResourceRows(variant).forEach((resource) => {
        if (payloadEntryMatchesResource(entry, resource)) {
          matchingUsages.push({ variant, resource });
        }
      });
    });
    const selectors = new Set(matchingUsages.map(({ variant }) => variantSelector(variant)).filter(Boolean));
    const repos = new Set();
    const models = new Set();
    matchingUsages.forEach(({ variant }) => {
      models.add(String(variant?.model_display_name || variant?.model_id || "").trim());
      variantSourceRepoCandidates(variant).forEach((repo) => repos.add(repo));
    });
    rows.push({
      key: `model-resource-file:${path}`,
      label: modelResourceFileDisplayLabel(path, matchingUsages),
      path,
      kind: String(entry?.kind || "file"),
      role: "model-resource",
      sizeBytes: Number(entry?.size_bytes || 0),
      cacheSizeBytes: 0,
      cacheSelectors: new Set(),
      hollow: matchingUsages.length <= 0,
      unattachedResource: matchingUsages.length <= 0,
      deletePaths: [path],
      usages: matchingUsages,
      selectors,
      repos,
      models: models.size ? models : new Set(["Downloaded model resource"]),
    });
  });
  const cacheEntriesByPath = new Map(
    (runtimeInventory()?.model_cache_entries || [])
      .map((entry) => [String(entry?.path || "").trim(), entry])
      .filter(([path]) => path),
  );
  const attachedCachePaths = new Set();
  rows.forEach((row) => {
    const rowCaches = new Map();
    (row.usages || []).forEach(({ variant }) => {
      (Array.isArray(variant?.cache_entries) ? variant.cache_entries : []).forEach((cache) => {
        const path = String(cache?.path || "").trim();
        if (!path) return;
        const globalEntry = cacheEntriesByPath.get(path);
        const sizeBytes = Math.max(
          Number(cache?.size_bytes || 0),
          Number(globalEntry?.size_bytes || 0),
        );
        if (sizeBytes <= 0) return;
        rowCaches.set(path, Math.max(Number(rowCaches.get(path) || 0), sizeBytes));
        attachedCachePaths.add(path);
      });
    });
    row.cacheEntries = [...rowCaches.entries()].map(([path, size_bytes]) => ({ path, size_bytes }));
    row.cacheSizeBytes = row.cacheEntries.reduce((sum, cache) => sum + Number(cache.size_bytes || 0), 0);
  });
  const sharedCacheEntries = [];
  cacheEntriesByPath.forEach((entry, path) => {
    if (attachedCachePaths.has(path)) return;
    if (!path || attachedPaths.has(path)) return;
    const sizeBytes = Number(entry?.size_bytes || 0);
    if (sizeBytes < 1024 * 1024) return;
    sharedCacheEntries.push({ path, size_bytes: sizeBytes });
  });
  if (sharedCacheEntries.length) {
    const sizeBytes = sharedCacheEntries.reduce((sum, entry) => sum + Number(entry.size_bytes || 0), 0);
    rows.push({
      key: "model-cache:shared-runtime",
      label: "Shared runtime cache",
      path: `${sharedCacheEntries.length} cache path${sharedCacheEntries.length === 1 ? "" : "s"}`,
      kind: "directory",
      role: "model-cache",
      sizeBytes: 0,
      cacheSizeBytes: sizeBytes,
      cacheEntries: sharedCacheEntries,
      cacheSelectors: new Set(),
      hollow: true,
      unattachedCache: true,
      deletePaths: sharedCacheEntries.map((entry) => entry.path),
      usages: [],
      selectors: new Set(),
      repos: new Set(),
      models: new Set(["Shared runtime cache"]),
    });
  }
  return rows
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
        (Number(right.sizeBytes || 0) + Number(right.cacheSizeBytes || 0)) -
          (Number(left.sizeBytes || 0) + Number(left.cacheSizeBytes || 0)) ||
        String(left.label || "").localeCompare(String(right.label || "")),
    );
}
function inventoryUniqueCacheUsageBytes() {
  const byPath = new Map();
  inventoryVariants().forEach((variant) => {
    const entries = Array.isArray(variant?.cache_entries) ? variant.cache_entries : [];
    entries.forEach((entry) => {
      const path = String(entry?.path || "").trim();
      if (!path) return;
      byPath.set(path, Math.max(Number(byPath.get(path) || 0), Number(entry?.size_bytes || 0)));
    });
  });
  return [...byPath.values()].reduce((sum, value) => sum + Number(value || 0), 0);
}
async function requestStopModelInstall(jobId) {
  const key = String(jobId || "").trim();
  if (!key) return;
  if (!confirm("Cancel this model download? Partial download targets will be cleaned up.")) return;
  await post(
    "/admin/model-install/stop",
    { job_id: key },
    `/admin/model-install/stop ${key}`,
  );
  await refreshStatus({ force: true });
  renderDynamicPresetModels();
}
function modelInstallProgressPercent(job = {}) {
  const loaded = Number(job?.progress_loaded_bytes);
  const total = Number(job?.progress_total_bytes);
  if (Number.isFinite(loaded) && Number.isFinite(total) && total > 0) {
    const bytePercent = Math.max(0, Math.min(100, Math.floor((loaded / total) * 100)));
    if (bytePercent > 0 || loaded > 0) return bytePercent;
  }
  const explicit = Number(job?.progress_percent);
  if (Number.isFinite(explicit)) return Math.max(0, Math.min(100, Math.floor(explicit)));
  return 0;
}
function modelInstallProgressLabel(job = {}) {
  const percent = modelInstallProgressPercent(job);
  const loaded = Number(job?.progress_loaded_bytes || 0);
  const total = Number(job?.progress_total_bytes || 0);
  const byteLabel = loaded > 0 && total > 0
    ? ` (${formatDiskBytes(loaded)} / ${formatDiskBytes(total)})`
    : "";
  return `Downloading ${percent}%${byteLabel}...`;
}
function openPresetResourceManager() {
  selectPresetModel(RESOURCE_MANAGER_MODEL_ID);
}
function openAIStudioPanel() {
  selectPresetModel(AI_STUDIO_MODEL_ID);
}
async function refreshAIStudioGallery(options = {}) {
  const now = Date.now();
  if (aiStudioGalleryState.loading) return aiStudioGalleryState;
  if (!options.force && now - Number(aiStudioGalleryState.loadedAt || 0) < 15000) return aiStudioGalleryState;
  aiStudioGalleryState.loading = true;
  aiStudioGalleryState.error = "";
  window.setTimeout(() => renderDynamicPresetModels({ force: true }), 0);
  try {
    const response = await fetch(`/admin/ai-studio/gallery?limit=120&_=${Date.now()}`, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload?.ok) throw new Error(payload?.error || "AI Studio gallery fetch failed.");
    aiStudioGalleryState.items = Array.isArray(payload.items) ? payload.items : [];
    aiStudioGalleryState.loadedAt = Date.now();
  } catch (error) {
    aiStudioGalleryState.error = String(error?.message || error || "AI Studio gallery fetch failed.");
  } finally {
    aiStudioGalleryState.loading = false;
    renderDynamicPresetModels({ force: true });
  }
  return aiStudioGalleryState;
}
function aiStudioResourceRows() {
  return inventoryResourceManagerRows().filter((entry) => !!resourceManagerModality(entry));
}
function aiStudioModalityCount(rows, modality) {
  return rows.filter((entry) => resourceManagerModality(entry) === modality).length;
}
function aiStudioLaneCountLabel(lanes = []) {
  const total = Array.isArray(lanes) ? lanes.length : 0;
  const installed = (lanes || []).filter((lane) => aiStudioLanePrimaryInstalled(lane)).length;
  return `${installed} / ${total}`;
}
function aiStudioLaneResourceMatches(entry, lane = {}) {
  const haystack = `${entry?.label || ""} ${entry?.path || ""} ${entry?.models?.join?.(" ") || ""}`.toLowerCase();
  return (lane.match || []).some((token) => haystack.includes(String(token || "").toLowerCase()));
}
function aiStudioLanePrimaryResourceMatches(entry, lane = {}) {
  const haystack = `${entry?.label || ""} ${entry?.path || ""} ${entry?.models?.join?.(" ") || ""}`.toLowerCase();
  return (lane.primaryMatch || lane.match || []).some((token) => haystack.includes(String(token || "").toLowerCase()));
}
function aiStudioLanePrimaryInstalled(lane = {}) {
  const backendReady = aiStudioLaneBackendReady(lane);
  if (backendReady === true) return true;
  return aiStudioResourceRows().some((entry) => aiStudioLanePrimaryResourceMatches(entry, lane));
}
function aiStudioSharedDependencyOwners(entry = {}) {
  const lanes = [
    { primaryMatch: ["ideogram4_fp8_scaled", "ideogram4_unconditional"], sharedMatch: ["flux2-vae"] },
    { primaryMatch: ["chroma1-hd"], sharedMatch: ["t5xxl_fp16", "vae/flux", "ae.safetensors"] },
  ];
  const haystack = `${entry?.label || ""} ${entry?.path || ""} ${entry?.models?.join?.(" ") || ""}`.toLowerCase();
  return lanes.filter((lane) =>
    aiStudioLanePrimaryInstalled(lane) &&
    lane.sharedMatch.some((token) => haystack.includes(token.toLowerCase())),
  ).length;
}
function aiStudioLaneExistingResourcePaths(lane = {}) {
  if (!aiStudioLanePrimaryInstalled(lane)) return [];
  const paths = [];
  aiStudioResourceRows().forEach((entry) => {
    if (!aiStudioLaneResourceMatches(entry, lane)) return;
    const isShared = (lane.sharedMatch || []).some((token) =>
      `${entry?.label || ""} ${entry?.path || ""} ${entry?.models?.join?.(" ") || ""}`.toLowerCase().includes(String(token || "").toLowerCase()),
    );
    const sharedOwners = isShared ? aiStudioSharedDependencyOwners(entry) : 1;
    if (sharedOwners !== 1) return;
    if (entry.path) paths.push(String(entry.path));
    (entry.usages || []).forEach(({ resource }) => {
      if (resource?.path) paths.push(String(resource.path));
    });
    (entry.deletePaths || []).forEach((path) => paths.push(String(path || "")));
  });
  return [...new Set(paths.map((path) => String(path || "").trim()).filter(Boolean))];
}
function aiStudioLaneBackendReady(lane = {}) {
  const ready = lastStatus?.ai_studio?.model_ready;
  if (!ready || typeof ready !== "object") return null;
  const rawKey = String(lane.key || "").trim().toLowerCase();
  const key = {
    "hidream-o1": "hidream",
    "ideogram-4": "ideogram",
    "ltx-2.3": "ltx",
    "ace-step": "music",
    "stable-audio-open": "sfx",
    "step-audio-editx": "voice",
    "studio-director": "production",
  }[rawKey] || rawKey;
  if (!key || !Object.prototype.hasOwnProperty.call(ready, key)) return null;
  return !!ready[key];
}
async function startAIStudioModelDownload(modelKey) {
  const key = String(modelKey || "").trim();
  if (!key) return;
  if (typeof focusScriptLogs === "function") focusScriptLogs();
  await post(
    "/admin/ai-studio/download",
    { model_key: key },
    `/admin/ai-studio/download ${key}`,
  );
  refreshStatus({ force: true }).catch(() => {});
}
function renderAIStudioLaneActions(lane = {}) {
  const paths = aiStudioLaneExistingResourcePaths(lane);
  const repoUrl = String(lane.repo || "").trim();
  const backendReady = aiStudioLaneBackendReady(lane);
  const installed = backendReady === true || aiStudioLanePrimaryInstalled(lane);
  const buttons = [];
  if (repoUrl) {
    buttons.push(`<a class="resource-hf-btn" href="${escapeHtml(repoUrl)}" target="_blank" rel="noopener noreferrer">${huggingFaceLogoSvg()}<span>HF</span></a>`);
  }
  if (paths.length) {
    buttons.push(`<button type="button" class="btn red" onclick="promptDeleteResourcePaths([${paths.map((path) => `'${escapeJs(path)}'`).join(",")}], '${escapeJs(lane.title || "AI Studio model")}')">Delete</button>`);
  }
  if (lane.key && !installed) {
    buttons.push(`<button type="button" class="btn green" onclick="startAIStudioModelDownload('${escapeJs(lane.key)}')">Download</button>`);
  }
  return buttons.length ? `<div class="ai-studio-lane-actions">${buttons.join("")}</div>` : "";
}
function renderAIStudioLaneCard({ title, modality, best, prompt, notes, key, repo, match, primaryMatch, sharedMatch, extraContent = "" }) {
  const icon = resourceManagerModalityIcon({ modality });
  const lane = { title, key, repo, match, primaryMatch, sharedMatch };
  return `<div class="resource-manager-card ai-studio-lane-card ai-studio-lane-${escapeHtml(modality)}"><span class="ai-studio-modality-badge ai-studio-modality-${escapeHtml(modality)}">${escapeHtml(modality)}</span><div class="resource-manager-card-head"><div class="resource-manager-title-row">${icon}<div class="resource-manager-title">${escapeHtml(title)}</div></div></div><div class="ai-studio-lane-meta"><div><b>Best at</b><span>${escapeHtml(best)}</span></div><div><b>Prompt style</b><span>${escapeHtml(prompt)}</span></div><div><b>Notes</b><span>${escapeHtml(notes)}</span></div></div>${renderAIStudioLaneActions(lane)}${renderAIStudioLaneResourceDetails(lane)}${extraContent || ""}</div>`;
}
function renderAIStudioLaneSection(title, modality, cards) {
  const key = String(modality || "").trim().toLowerCase();
  const collapsed = !!aiStudioLaneCollapseState[key];
  const cue = svgIcon(collapsed ? "chevron-down" : "chevron-up");
  return `<section class="service-section-card ai-studio-lane-section ai-studio-lane-column ai-studio-lane-${escapeHtml(modality)}" data-collapsed="${collapsed ? "true" : "false"}"><button type="button" class="service-section-head service-section-toggle ai-studio-lane-column-toggle" title="${collapsed ? "Expand" : "Collapse"} ${escapeHtml(title)} Studio lane" aria-label="${collapsed ? "Expand" : "Collapse"} ${escapeHtml(title)} Studio lane" aria-expanded="${collapsed ? "false" : "true"}" onclick="toggleAIStudioLaneSection('${escapeJs(key)}', this)"><span class="service-section-cue" aria-hidden="true">${cue}</span><span class="service-section-title">${escapeHtml(title)}</span></button><div class="service-section-body ai-studio-lane-column-body">${cards.join("")}</div></section>`;
}
function toggleAIStudioLaneSection(modality, toggle = null) {
  const key = String(modality || "").trim().toLowerCase();
  if (!key) return;
  const collapsed = !aiStudioLaneCollapseState[key];
  aiStudioLaneCollapseState[key] = collapsed;
  const card = toggle?.closest?.(".ai-studio-lane-column") || null;
  if (card) {
    card.dataset.collapsed = collapsed ? "true" : "false";
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    const title = String(toggle.querySelector(".service-section-title")?.textContent || key);
    toggle.setAttribute("title", `${collapsed ? "Expand" : "Collapse"} ${title} Studio lane`);
    toggle.setAttribute("aria-label", `${collapsed ? "Expand" : "Collapse"} ${title} Studio lane`);
    const cue = toggle.querySelector(".service-section-cue");
    if (cue) cue.innerHTML = svgIcon(collapsed ? "chevron-down" : "chevron-up");
    return;
  }
  renderDynamicPresetModels();
}
function renderAIStudioResourceCard(entry) {
  const icon = resourceManagerModalityIcon(entry);
  const usageLabel = entry.usages?.length
    ? `${entry.usages.length} preset${entry.usages.length === 1 ? "" : "s"}`
    : (entry.unattachedResource ? "Studio resource" : "Downloaded resource");
  return `<div class="resource-manager-card ai-studio-resource-card"><div class="resource-manager-card-head"><div class="resource-manager-title-row">${icon}<div class="resource-manager-title">${escapeHtml(entry.label || "Resource")}</div></div><span class="resource-size-badge">${escapeHtml(formatResourcePlusCacheBytes(entry.sizeBytes || 0, entry.cacheSizeBytes || 0))}</span></div><div class="resource-manager-meta">${escapeHtml(usageLabel)}</div><div class="resource-manager-path"><code>${escapeHtml(entry.path || "")}</code></div></div>`;
}
function aiStudioLaneResourceStateKey(lane = {}, fallback = "") {
  const key = String(lane.key || lane.title || fallback || "").trim().toLowerCase();
  return key || "resources";
}
function setAIStudioLaneResourceOpenFromDetails(details, key) {
  const stateKey = String(key || "").trim();
  if (!details || !stateKey) return;
  aiStudioLaneResourceOpenState[stateKey] = !!details.open;
}
function renderAIStudioLaneResourceDetails(lane = {}) {
  const rows = aiStudioResourceRows().filter((entry) => aiStudioLaneResourceMatches(entry, lane));
  if (!rows.length) return "";
  const totalBytes = rows.reduce((sum, entry) => sum + Number(entry.sizeBytes || 0) + Number(entry.cacheSizeBytes || 0), 0);
  const label = `${rows.length} detected resource${rows.length === 1 ? "" : "s"} · ${formatDiskBytes(totalBytes)}`;
  const stateKey = aiStudioLaneResourceStateKey(lane);
  const open = aiStudioLaneResourceOpenState[stateKey] ? "open" : "";
  return `<details class="ai-studio-lane-resources" data-ai-studio-lane-resource-key="${escapeHtml(stateKey)}" ${open} ontoggle="setAIStudioLaneResourceOpenFromDetails(this,'${escapeJs(stateKey)}')"><summary>${escapeHtml(label)}</summary><div class="ai-studio-lane-resource-grid">${rows.map(renderAIStudioResourceCard).join("")}</div></details>`;
}
function renderAIStudioUnmappedResourceSection(rows = [], lanes = []) {
  const unmatched = rows.filter((entry) => !lanes.some((lane) => aiStudioLaneResourceMatches(entry, lane)));
  if (!unmatched.length) return "";
  const stateKey = aiStudioLaneResourceStateKey({}, "other");
  const open = aiStudioLaneResourceOpenState[stateKey] ? "open" : "";
  return `<details class="ai-studio-lane-resources ai-studio-other-resources" data-ai-studio-lane-resource-key="${escapeHtml(stateKey)}" ${open} ontoggle="setAIStudioLaneResourceOpenFromDetails(this,'${escapeJs(stateKey)}')"><summary>Other Detected Studio Resources (${unmatched.length})</summary><div class="preset-help">Resources detected in AI Studio storage that do not map cleanly to a lane card.</div><div class="ai-studio-lane-resource-grid">${unmatched.map(renderAIStudioResourceCard).join("")}</div></details>`;
}
function renderAIStudioGalleryPreview(item = {}) {
  const url = escapeHtml(item.url || "");
  const name = escapeHtml(item.name || "AI Studio artifact");
  const kind = String(item.kind || "").toLowerCase();
  if (kind === "image") return `<img src="${url}" alt="${name}" loading="lazy" />`;
  if (kind === "video") return `<video src="${url}" muted controls preload="metadata"></video>`;
  if (kind === "audio") return `<div class="ai-studio-gallery-audio-preview">${resourceManagerModalityIcon({ modality: item.source === "conversation" ? "speech" : "audio" })}<audio src="${url}" controls preload="metadata"></audio></div>`;
  return `<div class="empty-variant-note">No preview available.</div>`;
}
async function deleteAIStudioGalleryArtifact(rootPath, relativePath, label = "artifact") {
  const root = String(rootPath || "/");
  const rel = String(relativePath || "");
  if (!rel) return;
  if (!confirm(`Delete AI Studio artifact "${label}" and any hardlinked copy?`)) return;
  await post(
    "/admin/ai-studio/gallery/delete",
    { root_path: root, relative_path: rel },
    `/admin/ai-studio/gallery/delete ${rel}`,
  );
  await refreshAIStudioGallery({ force: true });
}
function renderAIStudioGalleryItem(item = {}) {
  const rootPath = item.root_path || "/";
  const relativePath = item.relative_path || "";
  const mtime = Number(item.mtime || 0) > 0 ? new Date(Number(item.mtime) * 1000).toLocaleString() : "unknown time";
  const source = item.source === "conversation" ? "Conversation copy" : "Studio output";
  const name = item.name || "Artifact";
  return `<div class="resource-manager-card ai-studio-gallery-item ai-studio-gallery-${escapeHtml(item.kind || "file")}"><div class="ai-studio-gallery-preview"><button type="button" class="iconbtn ai-studio-gallery-corner ai-studio-gallery-delete" title="Delete artifact" aria-label="Delete artifact" onclick="deleteAIStudioGalleryArtifact('${escapeJs(rootPath)}','${escapeJs(relativePath)}','${escapeJs(name)}')">${svgIcon("delete")}</button><button type="button" class="iconbtn ai-studio-gallery-corner ai-studio-gallery-open" title="Open in File Editor" aria-label="Open in File Editor" onclick="openStorageBrowserFileReadOnly('${escapeJs(rootPath)}','${escapeJs(relativePath)}')">${svgIcon("detach")}</button>${renderAIStudioGalleryPreview(item)}</div><div class="resource-manager-card-head"><div><div class="resource-manager-title">${escapeHtml(name)}</div><div class="resource-manager-meta">${escapeHtml(source)} · ${escapeHtml(item.kind || "media")} · ${escapeHtml(formatDiskBytes(item.size_bytes || 0))} · ${escapeHtml(mtime)}</div></div></div><div class="resource-manager-path"><code>${escapeHtml(relativePath)}</code></div></div>`;
}
function renderAIStudioGallerySection() {
  if (!aiStudioGalleryState.open) return "";
  const state = aiStudioGalleryState || {};
  const refreshButton = renderIconButton({ title: state.loading ? "Refreshing gallery" : "Refresh gallery", action: "refreshAIStudioGallery({ force: true })", icon: "refresh", className: "ai-studio-gallery-refresh", disabled: !!state.loading });
  const header = `<div class="resource-manager-card-head"><div><h3>Gallery</h3><div class="preset-help">Recent AI Studio artifacts from renderer output and saved Chat conversations.</div></div></div>${refreshButton}`;
  if (state.loading && !state.items.length) {
    return `<section class="resource-manager-card ai-studio-gallery-card">${header}<div class="empty-variant-note">Loading AI Studio artifacts...</div></section>`;
  }
  if (state.error) {
    return `<section class="resource-manager-card ai-studio-gallery-card">${header}<div class="msg error">${escapeHtml(state.error)}</div></section>`;
  }
  const items = Array.isArray(state.items) ? state.items : [];
  if (!items.length) {
    return `<section class="resource-manager-card ai-studio-gallery-card">${header}<div class="empty-variant-note">No generated AI Studio artifacts found yet.</div></section>`;
  }
  return `<section class="resource-manager-card ai-studio-gallery-card">${header}<div class="ai-studio-gallery-grid">${items.map(renderAIStudioGalleryItem).join("")}</div></section>`;
}
function renderAIStudioView() {
  const rows = aiStudioResourceRows();
  const imageSummaryLanes = [
    { key: "hidream-o1", primaryMatch: ["hidream-o1", "hidream_o1", "hidream"] },
    { key: "ideogram-4", primaryMatch: ["ideogram4_fp8_scaled", "ideogram4_unconditional"] },
    { key: "chroma", primaryMatch: ["chroma1-hd"] },
    { key: "zimage", primaryMatch: ["z-image-turbo-fp8", "qwen_3_4b_fp8_mixed"] },
    { key: "krea", primaryMatch: ["krea2_turbo_fp8_scaled", "qwen3vl_4b_fp8_scaled"] },
  ];
  const videoSummaryLanes = [
    { key: "ltx-2.3", primaryMatch: ["ltx2.3", "ltx-2.3-22b-distilled"] },
    { key: "sulphur", primaryMatch: ["sulphur-2", "sulphur_dev"] },
    { key: "10eros", primaryMatch: ["10eros", "10Eros_v1"] },
    { key: "wan", primaryMatch: ["wan-rapid", "wan2.2-rapid-mega"] },
  ];
  const audioSummaryLanes = [
    { key: "ace-step", primaryMatch: ["ace-step", "ace_step", "ace-step-1.5"] },
    { key: "stable-audio-open", primaryMatch: ["stable-audio", "stable_audio"] },
  ];
  const speechSummaryLanes = [
    { key: "step-audio-editx", primaryMatch: ["step-audio", "step_audio", "editx"] },
    { key: "kokoro", primaryMatch: ["kokoro"] },
  ];
  const imageCount = aiStudioLaneCountLabel(imageSummaryLanes);
  const audioCount = aiStudioLaneCountLabel(audioSummaryLanes);
  const speechCount = aiStudioLaneCountLabel(speechSummaryLanes);
  const videoCount = aiStudioLaneCountLabel(videoSummaryLanes);
  const laneGroups = [
    ["Image", "image", [
      { key: "hidream-o1", repo: "https://huggingface.co/drbaph/HiDream-O1-Image-Dev-2604-FP8", match: ["hidream-o1", "hidream_o1", "hidream"], title: "HiDream-O1 Image", modality: "image", best: "top-quality general / photoreal stills", prompt: "natural language", notes: "HiDream-O1-Image-Dev-2604 fp8; native 2048px, single GPU lane" },
      { key: "ideogram-4", repo: "https://huggingface.co/Comfy-Org/Ideogram-4", match: ["ideogram", "qwen3vl_8b_fp8_scaled", "flux2-vae"], primaryMatch: ["ideogram4_fp8_scaled", "ideogram4_unconditional"], sharedMatch: ["flux2-vae"], title: "Ideogram-4", modality: "image", best: "design, logo, text, typography", prompt: "director-crafted structured JSON", notes: "fp8 still workflow; best for text/logos and the native image button shim" },
      { key: "chroma", repo: "https://huggingface.co/Comfy-Org/Chroma1-HD_repackaged", match: ["chroma", "t5xxl_fp16", "vae/flux", "ae.safetensors"], primaryMatch: ["chroma1-hd"], sharedMatch: ["t5xxl_fp16", "vae/flux", "ae.safetensors"], title: "Chroma1-HD", modality: "image", best: "uncensored photoreal / illustration", prompt: "natural language + negative + CFG", notes: "Flux-family shared T5/VAE assets; uncensored stills lane" },
      { key: "zimage", repo: "https://huggingface.co/T5B/Z-Image-Turbo-FP8", match: ["z-image", "z-image-turbo-fp8", "qwen_3_4b_fp8_mixed"], primaryMatch: ["z-image-turbo-fp8"], sharedMatch: ["qwen_3_4b_fp8_mixed", "vae/ae.safetensors"], title: "Z-Image", modality: "image", best: "fast uncensored stills", prompt: "natural language", notes: "Z-Image-Turbo fp8 with Qwen3-4B encoder and Flux-style VAE; 8-step cfg=1 lane" },
      { key: "krea", repo: "https://huggingface.co/Comfy-Org/Krea-2", match: ["krea2", "krea2_turbo_fp8_scaled", "qwen3vl_4b_fp8_scaled", "qwen_image_vae"], primaryMatch: ["krea2_turbo_fp8_scaled"], sharedMatch: ["qwen3vl_4b_fp8_scaled", "qwen_image_vae"], title: "Krea 2", modality: "image", best: "aesthetic stylized stills", prompt: "natural language", notes: "Krea 2 Turbo fp8 with Qwen3-VL-4B encoder and Qwen-Image VAE; 8-step cfg=1 lane" },
    ]],
    ["Video", "video", [
      { key: "ltx-2.3", repo: "https://huggingface.co/unsloth/LTX-2.3-GGUF", match: ["ltx2.3", "ltx-2.3-22b-distilled"], title: "LTX-2.3", modality: "video", best: "text/image to video with synced ambient audio", prompt: "cinematic director prompt", notes: "22B distilled GGUF DiT split across both GPUs; default ~10s clips" },
      { key: "sulphur", repo: "https://huggingface.co/vantagewithai/Sulphur-2-Base-GGUF", match: ["sulphur-2", "sulphur_dev"], title: "Sulphur", modality: "video", best: "uncensored video generation", prompt: "cinematic director prompt", notes: "LTX-2.3 dev fine-tune GGUF; single-stage workflow avoids lattice artifacts" },
      { key: "10eros", repo: "https://huggingface.co/vantagewithai/LTX2.3-10Eros-GGUF", match: ["10eros", "10Eros_v1", "ltx-2.3-22b-dev"], title: "10Eros", modality: "video", best: "uncensored LTX-family video generation", prompt: "cinematic director prompt", notes: "LTX-2.3 dev fine-tune GGUF using the shared distilled LoRA 1.1 workflow" },
      { key: "wan", repo: "https://huggingface.co/befox/WAN2.2-14B-Rapid-AllInOne-GGUF", match: ["wan-rapid", "wan2.2-rapid-mega", "umt5_xxl_fp8_e4m3fn_scaled", "wan_2.1_vae"], title: "Wan2.2", modality: "video", best: "uncensored rapid text/image to video", prompt: "cinematic natural language", notes: "Wan2.2 Rapid AllInOne Mega Q8 GGUF with UMT5 encoder and Wan 2.1 VAE; native 4-step cfg=1 clips" },
    ]],
    ["Audio", "audio", [
      { key: "ace-step", repo: "https://huggingface.co/Comfy-Org/ACE-Step_ComfyUI_repackaged", match: ["ace-step", "ace_step", "ace-step-1.5"], title: "ACE-Step Music", modality: "audio", best: "songs and instrumentals", prompt: "tags plus lyrics or instrumental structure", notes: "ACE-Step v1 3.5B ComfyUI repack; single-device GPU0 lane" },
      { key: "stable-audio-open", repo: "https://huggingface.co/Comfy-Org/stable-audio-open-1.0_repackaged", match: ["stable-audio", "stable_audio", "t5-base"], title: "Stable Audio SFX", modality: "audio", best: "sound effects, ambience, textures", prompt: "concrete sound description", notes: "Stable Audio Open 1.0 ComfyUI repack plus T5-base encoder; output to gallery mp3" },
    ]],
    ["Speech", "speech", [
      { key: "step-audio-editx", repo: "https://huggingface.co/stepfun-ai/Step-Audio-EditX", match: ["step-audio", "step_audio", "editx"], title: "Step-Audio-EditX Voice", modality: "speech", best: "premium voice clone and style/emotion edits", prompt: "text plus reference voice controls", notes: "3B Apache model in isolated step-voice service on :8193" },
      { key: "kokoro", repo: "https://huggingface.co/fastrtc/kokoro-onnx", match: ["kokoro"], title: "Kokoro Voiceover", modality: "speech", best: "fast narration mixed onto video", prompt: "voiceover/narration directive", notes: "Kokoro-82M CPU TTS service on :8192; ducked ffmpeg mixdown" },
    ]],
    ["Support", "text", [
      { key: "studio-director", repo: "https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive", match: ["qwen3.5-4b-gguf", "Qwen3.5-4B-Uncensored-HauhauCS"], title: "Studio Director", modality: "text", best: "prompt enhancement for every Studio lane", prompt: "rough user intent to lane-specific prompt", notes: "Qwen3.5 4B Q4_K_M plus multimodal projector; support model, not an output lane" },
    ]],
  ];
  const flatLanes = laneGroups.flatMap(([, , lanes]) => lanes);
  const otherResources = renderAIStudioUnmappedResourceSection(rows, flatLanes);
  if (otherResources) {
    const directorLane = flatLanes.find((lane) => String(lane?.key || "") === "studio-director");
    if (directorLane) directorLane.extraContent = otherResources;
  }
  const laneSections = `<div class="ai-studio-lane-masonry">${laneGroups.map(([title, modality, lanes]) =>
    renderAIStudioLaneSection(title, modality, lanes.map((lane) => renderAIStudioLaneCard(lane))),
  ).join("")}</div>`;
  const comfyInstalled = aiStudioServiceInstalled();
  const comfyActions = comfyInstalled
    ? '<div class="ai-studio-lane-actions"><a class="btn blue" href="/comfyui/" target="_blank" rel="noopener noreferrer">Open ComfyUI</a></div>'
    : "";
  const comfySection = `<h3 class="ai-studio-section-title">ComfyUI</h3><div class="resource-manager-card ai-studio-comfy-card"><div class="resource-manager-card-head"><div class="resource-manager-title-row">${resourceManagerModalityIcon({ modality: "image" })}<div class="resource-manager-title">ComfyUI Renderer</div></div><span class="status-badge status-${comfyInstalled ? "success" : "warning"}">${comfyInstalled ? "installed" : "not installed"}</span></div><div class="resource-manager-meta">Renderer service for image, video, music, and SFX lanes. Outputs are served by the gallery service when AI Studio is installed.</div>${comfyActions}</div>`;
  const anyInstalledLane = flatLanes.some((lane) => aiStudioLanePrimaryInstalled(lane));
  const noResources = rows.length || anyInstalledLane ? "" : '<div class="empty-variant-note">No AI Studio resources are detected yet. Run Setup AI Studio to install ComfyUI lanes and their model payloads.</div>';
  return `<div class="resource-manager-shell ai-studio-shell"><button type="button" class="script-help-btn ai-studio-help-btn" title="Open AI Studio docs" aria-label="Open AI Studio docs" onclick="openStorageBrowserFileReadOnly('/', 'opt/ai/club-3090/docs/ai-studio/README.md')">?</button><div class="resource-manager-intro">AI Studio collects setup, ComfyUI lane inventory, and multimodal model resources in one place for Chat Plan and Interactive generation.</div><div class="ai-studio-actions">${imageStudioActionButtonHtml()}${imageStudioRuntimeButtonHtml()}${imageStudioGalleryButtonHtml()}</div><div class="ai-studio-summary-row"><div class="resource-manager-total-card"><div class="resource-manager-total-label">Image Models</div><div class="resource-manager-total-value">${imageCount}</div></div><div class="resource-manager-total-card"><div class="resource-manager-total-label">Audio Models</div><div class="resource-manager-total-value">${audioCount}</div></div><div class="resource-manager-total-card"><div class="resource-manager-total-label">Speech Models</div><div class="resource-manager-total-value">${speechCount}</div></div><div class="resource-manager-total-card"><div class="resource-manager-total-label">Video Models</div><div class="resource-manager-total-value">${videoCount}</div></div></div>${renderAIStudioGallerySection()}<h3 class="ai-studio-section-title">Studio Lanes</h3>${laneSections}${comfySection}${noResources}</div>`;
}
function renderResourceUsageActions(variant) {
  const state = resourceUsageState(variant);
  const selector = state.selector;
  const buttons = [];
  if (state.installing?.job_id && !state.sharedInstalling) {
    buttons.push(
      `<button class="btn green" onclick="requestStopModelInstall('${escapeJs(state.installing.job_id)}')">${escapeHtml(modelInstallProgressLabel(state.installing))}</button>`,
    );
  } else if (state.installing?.job_id) {
    buttons.push(
      `<button class="btn green" disabled title="${escapeHtml(sharedModelInstallDescription(state.installing))}">${escapeHtml(modelInstallProgressLabel(state.installing))}</button>`,
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
    `<button class="btn red" onclick="promptClearPresetCaches('${escapeJs(selector)}')">Clear Cache</button>`,
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
function resourceManagerPresetUsageMeta(variant) {
  const curated = String(variant?.best_for || variant?.quality_summary || "").trim();
  if (curated) return curated;
  const parts = [];
  const engine = prettyEngineName(variant?.engine_display || variant?.engine || "");
  if (engine && engine !== "Unknown") parts.push(engine);
  const ctx = variantMaxCtx(variant);
  if (ctx && ctx !== "n/a") parts.push(`${ctx} context`);
  const hardware = variantHardwareSummary(variant);
  if (hardware) parts.push(hardware);
  const model = String(variant?.model_display_name || variant?.model_id || "").trim();
  if (model) parts.push(`Uses ${model}`);
  return parts.filter(Boolean).join(" · ") || "Discovered preset usage";
}
function renderModelResourceManagerView() {
  const rows = inventoryResourceManagerRows();
  const modelResourceRootBytes = Number(runtimeInventory()?.model_resource_root_size_bytes || 0);
  const modelCacheRootBytes = Number(runtimeInventory()?.model_cache_size_bytes || 0);
  if (!rows.length && modelCacheRootBytes <= 0 && modelResourceRootBytes <= 0) {
    return `<div class="model-card"><div class="empty-variant-note">No downloaded model resources are currently present on disk.</div></div>`;
  }
  const attachedResourceBytes = rows.reduce((sum, entry) => sum + Number(entry.sizeBytes || 0), 0);
  const totalBytes = modelResourceRootBytes > 0 ? modelResourceRootBytes : attachedResourceBytes;
  const totalCacheBytes = inventoryUniqueCacheUsageBytes();
  const cacheBytes = modelCacheRootBytes > 0 ? modelCacheRootBytes : totalCacheBytes;
  const totalHint = `Models: ${formatDiskBytes(totalBytes)}. Cache: ${formatDiskBytes(cacheBytes)}. Model resource directories are never cleared by cache cleanup.`;
  return `<div class="resource-manager-shell"><div class="resource-manager-intro">Downloaded resources are grouped below by the shared disk asset they point at. Model resources are the actual GGUF/safetensors payloads. Cache is runtime/precompile/transient data and is managed separately.</div><div class="resource-manager-total-card" title="${escapeHtml(totalHint)}"><div class="resource-manager-total-label">Total Downloaded Resource Disk Usage</div><div class="resource-manager-total-value">${escapeHtml(formatResourcePlusCacheBytes(totalBytes, cacheBytes))}</div><div class="preset-help">Models + Cache</div></div>${rows.length ? `<div class="resource-manager-grid">${rows
    .map((entry) => {
      const markerStyle = `--preset-resource-color:${resourceColorForKey(entry.key)};`;
      const modelLabel = entry.models.join(" · ") || "Preset resource";
      const usageCount = entry.selectors.length;
      const usageLabel = entry.unattachedCache || entry.unattachedResource ? "Not currently attached to a discovered preset" : `Used by ${usageCount} Preset${usageCount === 1 ? "" : "s"}`;
      const repoUrl = entry.repos[0] ? `https://huggingface.co/${entry.repos[0]}` : "";
      const markerKind = (entry.usages || []).some(({ resource }) => presetResourceMarkerKind(resource || {}) === "speculative")
        ? "speculative"
        : presetResourceMarkerKind(entry.usages[0]?.resource || {});
      const markerClass = `${entry.hollow ? " hollow" : ""}${markerKind === "speculative" ? " diamond" : ""}`;
      const modalityIcon = resourceManagerModalityIcon(entry);
      const diskMarker = modalityIcon
        ? ""
        : `<span class="preset-disk-marker${markerClass}" title="Double-click to randomize this resource color" ondblclick="randomizeResourceMarkerColor('${escapeJs(entry.key)}')" style="${markerStyle}"></span>`;
      const cacheDeletePaths = (entry.deletePaths || entry.cacheEntries?.map((cache) => cache.path) || [])
        .map((path) => `'${escapeJs(String(path || ""))}'`)
        .join(",");
      const deleteAction = entry.unattachedCache
        ? `promptDeleteModelCachePaths([${cacheDeletePaths}], '${escapeJs(entry.label || "model cache")}')`
        : `promptDeleteResourcePaths([${(entry.deletePaths || entry.usages.map(({ resource }) => String(resource?.path || ""))).map((path) => `'${escapeJs(String(path || ""))}'`).join(",")}], '${escapeJs(entry.label || "resource")}', [${entry.selectors.map((selector) => `'${escapeJs(selector)}'`).join(",")}])`;
      return `<div class="resource-manager-card"><div class="resource-manager-card-head"><div class="resource-manager-title-row">${diskMarker}${modalityIcon}<div class="resource-manager-title">${escapeHtml(entry.label || "Resource")}</div></div><div class="resource-manager-card-subrow"><div class="resource-manager-card-copy"><div class="resource-manager-meta">${escapeHtml(modelLabel)}</div><div class="resource-manager-usage-count">${escapeHtml(usageLabel)}</div></div><div class="resource-manager-card-actions"><span class="resource-size-badge">${escapeHtml(formatResourcePlusCacheBytes(entry.sizeBytes || 0, entry.cacheSizeBytes || 0))}</span>${repoUrl ? `<a class="resource-hf-btn" href="${escapeHtml(repoUrl)}" target="_blank" rel="noopener noreferrer">${huggingFaceLogoSvg()}<span>HF</span></a>` : ""}${renderIconButton({ title: entry.unattachedCache ? "Clear model cache" : "Clear resource", action: deleteAction, icon: "delete", className: "resource-manager-delete-btn" })}</div></div></div><div class="resource-manager-path"><code>${escapeHtml(entry.path || "")}</code></div><div class="resource-manager-usage-list">${entry.unattachedCache ? '<div class="empty-variant-note">This cache entry is present on disk but is not referenced by the current preset inventory.</div>' : entry.unattachedResource ? '<div class="empty-variant-note">This model resource is present on disk but is not referenced by the current preset inventory.</div>' : entry.usages
        .map(({ variant }) => {
          const selector = variantSelector(variant);
          return `<button type="button" class="resource-manager-usage-row resource-manager-usage-button" title="Open this preset card" onclick="openPresetCardFromResourceManager('${escapeJs(selector)}')"><div class="resource-manager-usage-copy"><div class="resource-manager-usage-title">${escapeHtml(variantDisplayLabel(variant))}</div><div class="resource-manager-usage-meta">${escapeHtml(resourceManagerPresetUsageMeta(variant))}</div></div></button>`;
        })
        .join("")}</div></div>`;
    })
    .join("")}</div>` : '<div class="empty-variant-note">Model cache data exists on disk, but no discovered preset currently points at those resources.</div>'}</div>`;
}
function renderHiddenPresetManagerView() {
  const rows = inventoryVariants().filter((variant) => presetIsHidden(variant));
  if (!rows.length) {
    return `<div class="model-card"><div class="empty-variant-note">No presets are hidden right now.</div></div>`;
  }
  return `<div class="variant-group"><div class="variant-group-head"><h4>${escapeHtml(`Hidden Presets (${rows.length} Presets)`)}</h4></div><div class="variant-grid">${sortInventoryVariants(rows)
    .map((variant) => {
      const selector = variantSelector(variant);
      return `<div class="variant-card"><div class="variant-card-head"><div class="variant-card-title">${escapeHtml(variantDisplayLabel(variant))}</div><div class="preset-actions">${renderHiddenPresetToggleIcon(variant, true)}</div></div><div class="variant-meta"><strong>Best for:</strong> ${escapeHtml(variant.best_for || variant.quality_summary || "Hidden preset")}</div><div class="variant-meta"><strong>Max ctx:</strong> ${escapeHtml(variantMaxCtx(variant))} <strong>Engine:</strong> ${escapeHtml(prettyEngineName(variant.engine_display || variant.engine))}</div><div class="variant-actions"><button class="btn green" ${benchmarkJobActive() ? "disabled" : ""} onclick="switchInventoryVariant('${escapeJs(selector)}')">Launch</button>${renderVariantMetricsGroup(variant)}</div></div>`;
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
async function clearRecordedMetricsData(options = {}) {
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
  if (Array.isArray(lastStatus.gpus)) {
    lastStatus.gpus = lastStatus.gpus.map((row) => {
      if (!row || row.error) return row;
      return {
        ...row,
        temp_peak_c: row.temp_c,
        temp_junction_peak_c: row.temp_junction_c,
        temp_vram_peak_c: row.temp_vram_c,
        power_peak_w: row.power_w,
        core_clock_peak_mhz: row.core_clock_mhz,
        mem_clock_peak_mhz: row.mem_clock_mhz,
      };
    });
    if (typeof renderGpuCards === "function") renderGpuCards(lastStatus.gpus);
  }
  renderMetrics(lastStatus);
  if (String(options?.messageTarget || "") === "popup") {
    syncAllDetachedMetricsPopups(lastStatus);
  } else {
    setMsg("Recorded metrics cleared.");
  }
  refreshStatus({ force: true }).catch(() => {});
  return payload;
}
function promptClearRecordedMetrics() {
  openPresetActionModal({
    title: "Clear Recorded Metrics",
    body: "Clear the saved Metrics-tab history and all persisted peak values? This resets the recorded maxima, including the values that survive control-service restarts.",
    confirmLabel: "Clear Metrics",
    confirmClass: "red",
    onConfirm: async () => {
      await clearRecordedMetricsData();
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
  const rawKind = String(variant?.status_kind || "unknown").trim().toLowerCase();
  const sourceKind = String(variant?.source_status_kind || "").trim().toLowerCase();
  if (rawKind === "deprecated" || sourceKind === "deprecated") return "deprecated";
  if (variantRigBlockReason(variant)) return "hardware_blocked";
  if (variantIsMigrated(variant)) {
    if (sourceKind && sourceKind !== "migrated") return sourceKind;
    if (rawKind && rawKind !== "migrated") return rawKind;
    const compatKind = String(variant?.compat_status || "").trim().toLowerCase();
    if (compatKind && compatKind !== "migrated") return compatKind;
    return "unknown";
  }
  return rawKind || "unknown";
}
function variantEffectiveInstallState(variant) {
  return variantRigBlockReason(variant) ? "hardware_blocked" : String(variant?.install_state || "unknown");
}
function variantDisplayGroupKey(variant) {
  if (variantNvlinkMode(variant) === "required") return "nvlink";
  const rawCategory = String(variant?.category || "").trim().toLowerCase();
  const sourceStatus = String(variant?.source_status_kind || "").trim().toLowerCase();
  const topology = String(variant?.topology || variant?.scope_kind || "").trim().toLowerCase();
  const minGpuCount = Number(variant?.requires_min_gpu_count || variant?.min_gpu_count || 0);
  if (rawCategory === "multi" || topology === "multi" || topology === "global_only" || minGpuCount > 2) return "multi";
  if (topology && !["single", "gpu", "dual"].includes(topology)) return "multi";
  if (
    rawCategory === "experimental"
    || ["experimental", "incubating"].includes(sourceStatus)
    || ["experimental", "incubating"].includes(variantEffectiveStatusKind(variant))
  ) return "experimental";
  if (rawCategory === "dual" || topology === "dual" || minGpuCount === 2) return "dual";
  if (rawCategory === "single") {
    return "single";
  }
  return "single";
}
function variantOldCounterpartKey(variant) {
  const info = variantLineageInfo(variant);
  return info.old ? info.key : "";
}
function resolvedVariantDisplayGroupKey(variant, peers = []) {
  const counterpartKey = variantOldCounterpartKey(variant);
  if (!counterpartKey) return variantDisplayGroupKey(variant);
  const counterpart = (peers || []).find((row) => {
    if (row === variant) return false;
    const info = variantLineageInfo(row);
    return !info.old && info.key === counterpartKey;
  });
  return counterpart ? variantDisplayGroupKey(counterpart) : variantDisplayGroupKey(variant);
}
function isAdvancedPresetVariant(variant) {
  const groupKey = variantDisplayGroupKey(variant);
  return ["nvlink", "multi"].includes(groupKey);
}
function presetFilterNumber(value) {
  const number = Number(value);
  return String(value ?? "").trim() !== "" && Number.isFinite(number) ? number : null;
}
function presetFilterRangeMatches(value, minValue, maxValue) {
  const min = presetFilterNumber(minValue);
  const max = presetFilterNumber(maxValue);
  if (min === null && max === null) return true;
  const number = Number(value);
  if (!Number.isFinite(number)) return false;
  return (min === null || number >= min) && (max === null || number <= max);
}
function presetFilterNameMatches(value, pattern) {
  const query = String(pattern || "").trim().toLowerCase();
  if (!query) return true;
  const text = String(value || "").toLowerCase();
  if (!query.includes("*")) return text.includes(query);
  const escaped = query.split("*").map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join(".*");
  try {
    return new RegExp(escaped, "i").test(text);
  } catch (e) {
    return text.includes(query.replaceAll("*", ""));
  }
}
function presetFilterVariantTags(variant) {
  const tags = new Set();
  const status = variantEffectiveStatusKind(variant);
  if (status) tags.add(status);
  if (variantIsMigrated(variant)) tags.add("migrated");
  if (variantIsCustom(variant) && !variantIsMigrated(variant)) tags.add("custom");
  if (variantNvlinkMode(variant) === "required") tags.add("nvlink");
  if (variantSafetyProfile(variant) === "uncensored") tags.add("uncensored");
  if (variantDisplayGroupKey(variant) === "experimental") tags.add("experimental");
  return tags;
}
function presetFilterVariantStatuses(variant) {
  const values = new Set();
  const selector = variantSelector(variant);
  if (runtimeStatsRows(lastStatus).some((row) => String(row?.mode || row?.selector || "") === selector && row?.running !== false)) values.add("active");
  const install = variantEffectiveInstallState(variant);
  if (install === "ready") values.add("ready");
  if (install === "requires_download") values.add("download");
  if (install === "hardware_blocked") values.add("hardware_blocked");
  if (["unavailable", "unsupported"].includes(install)) values.add("unavailable");
  return values;
}
function presetFilterBenchmarkTps(value, depth = 0) {
  if (!value || depth > 8) return 0;
  if (Array.isArray(value)) return value.reduce((max, item) => Math.max(max, presetFilterBenchmarkTps(item, depth + 1)), 0);
  if (typeof value !== "object") return 0;
  let maximum = 0;
  Object.entries(value).forEach(([key, item]) => {
    const normalized = String(key).toLowerCase();
    if (/(^|_)(decode|generation|output|narrative|code)?_?tps$/.test(normalized)) {
      const number = Number(item);
      if (Number.isFinite(number) && number > 0) maximum = Math.max(maximum, number);
    } else if (item && typeof item === "object") {
      maximum = Math.max(maximum, presetFilterBenchmarkTps(item, depth + 1));
    }
  });
  return maximum;
}
function presetFilterTpsForVariant(variant) {
  const selector = variantSelector(variant);
  const score = benchmarkScoreForSelector(selector) || {};
  const benchmarkTps = Math.max(
    presetFilterBenchmarkTps(modelScoreModeResult(score, "full")),
    presetFilterBenchmarkTps(modelScoreModeResult(score, "quick")),
  );
  if (benchmarkTps > 0) return benchmarkTps;
  const stats = presetTpsStatsForSelector(selector);
  return Number(stats.max_tps || stats.avg_tps || 0) || 0;
}
function presetFilterScoreRangeResult(score, mode, minValue, maxValue) {
  const min = presetFilterNumber(minValue);
  const max = presetFilterNumber(maxValue);
  if (min === null && max === null) return null;
  const result = modelScoreModeResult(score || {}, mode);
  return presetFilterRangeMatches(result?.score, min, max);
}
function presetFilterMetricScore(score, metricId) {
  const candidates = [modelScoreModeResult(score || {}, "full"), modelScoreModeResult(score || {}, "quick")];
  for (const result of candidates) {
    const row = modelScoreMetricRows(result || {}).find((metric) => metric.id === metricId && !metric.missing);
    if (row) return row.score;
  }
  return null;
}
function variantMatchesPresetFilter(variant, state = getPresetFilterState()) {
  if (!presetFilterIsActive(state)) return true;
  if (!presetFilterNameMatches(`${variantDisplayLabel(variant)} ${variantSelector(variant)}`, state.name)) return false;
  const tags = presetFilterVariantTags(variant);
  if ((state.tags || []).some((tag) => !tags.has(tag))) return false;
  const statuses = presetFilterVariantStatuses(variant);
  if ((state.statuses || []).length && !(state.statuses || []).some((status) => statuses.has(status))) return false;
  const engine = String(variant?.engine_display || variant?.engine || "").trim();
  if ((state.engines || []).length && !state.engines.includes(engine)) return false;
  const topology = variantDisplayGroupKey(variant) === "nvlink" ? "dual" : variantDisplayGroupKey(variant);
  if ((state.topologies || []).length && !state.topologies.includes(topology)) return false;
  const gib = 1024 ** 3;
  const resourceBytes = Number(variant?.resource_size_bytes || 0);
  const cacheBytes = Number(variant?.cache_size_bytes || 0);
  const tps = presetFilterTpsForVariant(variant);
  if (!presetFilterRangeMatches(resourceBytes > 0 ? resourceBytes / gib : NaN, state.modelSizeMin, state.modelSizeMax)) return false;
  if (!presetFilterRangeMatches(cacheBytes > 0 ? cacheBytes / gib : NaN, state.cacheSizeMin, state.cacheSizeMax)) return false;
  if (!presetFilterRangeMatches(tps > 0 ? tps : NaN, state.tpsMin, state.tpsMax)) return false;
  const score = benchmarkScoreForSelector(variantSelector(variant)) || {};
  const scoreChecks = [
    presetFilterScoreRangeResult(score, "quick", state.quickMin, state.quickMax),
    presetFilterScoreRangeResult(score, "full", state.fullMin, state.fullMax),
  ].filter((value) => value !== null);
  if (scoreChecks.length && (state.scoreLogic === "or" ? !scoreChecks.some(Boolean) : !scoreChecks.every(Boolean))) return false;
  const filteredMetricIds = new Set([
    ...Object.keys(state.metricMins || {}),
    ...Object.keys(state.metricMaxs || {}),
  ]);
  for (const metricId of filteredMetricIds) {
    const min = presetFilterNumber(state.metricMins?.[metricId]);
    const max = presetFilterNumber(state.metricMaxs?.[metricId]);
    if (min === null && max === null) continue;
    const value = presetFilterMetricScore(score, metricId);
    if (value === null || (min !== null && value < min) || (max !== null && value > max)) return false;
  }
  return true;
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
    if (variantIsCustom(variant)) score -= 12;
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
    if (variantIsCustom(variant)) score += 24;
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
      const installState = modelInstallStateForVariant(variant);
      const sharedInstalling = !ready && installState.shared && installState.job;
      const action = ready
        ? `closeActionChoiceModal(); switchInventoryVariant('${escapeJs(variantSelector(variant))}')`
        : `closeActionChoiceModal(); promptModelInstallById('${escapeJs(variant.variant_id)}')`;
      const actionLabel = ready ? "Launch" : sharedInstalling ? modelInstallProgressLabel(installState.job) : "Download";
      const actionTitle = ready ? "Launch this preset" : sharedInstalling ? sharedModelInstallDescription(installState.job) : downloadButtonTitle(variant?.install_command || "");
      return `<div class="variant-card assistant-recommendation-card"><div class="variant-card-head"><div class="variant-card-title">${escapeHtml(variantDisplayLabel(variant))}</div><div class="badge-row">${renderStatusBadgesHtml(variant)}${variantCapabilityBadges(variant)}</div></div><div class="variant-meta"><strong>Best for:</strong> ${escapeHtml(variant.best_for || "No summary yet.")}</div><div class="variant-meta"><strong>Why this fits:</strong> ${escapeHtml(setupAssistantRecommendationReason(variant))}</div><div class="variant-meta"><strong>Hardware:</strong> ${escapeHtml(variantHardwareSummary(variant) || "No explicit gate")}</div>${sharedInstalling ? `<div class="variant-install-note"><strong>Download:</strong> ${escapeHtml(sharedModelInstallDescription(installState.job))}</div>` : ""}<div class="variant-actions"><button class="btn ${ready ? "blue" : "green"}" title="${escapeHtml(actionTitle)}" ${sharedInstalling ? "disabled" : ""} onclick="${action}">${escapeHtml(actionLabel)}</button>${renderPresetCacheClearButton(variant, !ready)}</div></div>`;
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
  if (benchmarkJobActive()) {
    alert("Model Scores benchmarking is running. Cancel the benchmark before launching presets.");
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
  if (benchmarkJobActive()) {
    alert("Model Scores benchmarking is running. Cancel the benchmark before stopping presets.");
    return;
  }
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
  const scoreLock = benchmarkJobActive();
  const running = summaryRunningTargets().filter(
    (item) => item.instance_id && item.mode,
  );
  if (running.length) {
    return `<div class="summary-action-bar"><button class="btn red" ${scoreLock ? "disabled" : ""} onclick="stopAllSummaryPresets()">Stop All</button></div>`;
  }
  if (Array.isArray(presetSummaryCache.restartTargets) && presetSummaryCache.restartTargets.length) {
    return `<div class="summary-action-bar"><button class="btn green" ${scoreLock ? "disabled" : ""} onclick="restartAllSummaryPresets()">Restart All</button></div>`;
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
  const scoreLock = benchmarkJobActive();
  const rigBlockedReason = variantRigBlockReason(variant);
  const buttonLabel = scoreLock ? "Locked" : rigBlockedReason ? "Blocked" : switching ? "Booting..." : active ? "Stop" : failed ? "Restart" : "Launch";
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
    : `<div class="preset-actions">${renderIconButton({ title: "Remove from summary", action: `promptRemoveSummaryPreset('${escapeJs(modelId)}','${escapeJs(selector)}')`, icon: "close" })}</div>`;
  const metricsGroup = renderVariantMetricsGroup(variant);
  const sideControls = renderVariantSettingsCluster(variant, { cacheDisabled: active || switching, deleteDisabled: active || switching || scoreLock });
  const badges = `<div class="badge-row"><span class="state-badge ${rigBlockedReason ? "state-hardware_blocked" : stateClass}">${escapeHtml(stateLabel)}</span>${variantStatusBadgeHtml(variant, stateLabel, { failed, rigBlockedReason })}${variantCapabilityBadges(variant)}${renderVariantLineageStar(variant)}${removeAction}</div>`;
  return `<div class="summary-preset-card${active || switching ? "" : " summary-preset-card-inactive"}" data-preset-selector="${escapeHtml(selector)}"><div class="summary-preset-head"><div class="summary-preset-title">${renderPresetQueueTitleTag(selector)}<span>${escapeHtml(title)}</span></div>${badges}</div><div class="variant-card-body"><div class="variant-card-main">${runtimeMeta}<div class="summary-preset-meta">${escapeHtml(variant.best_for || variant.quality_summary || "Cached preset")}</div><div class="variant-actions variant-card-main-actions"><button class="btn ${buttonClass}" ${rigBlockedReason || scoreLock ? "disabled" : ""} onclick="${action}">${escapeHtml(buttonLabel)}</button>${metricsGroup}</div></div><aside class="variant-card-side">${renderPresetScoreLabel(selector, variant)}${sideControls}</aside></div></div>`;
}
function renderSummaryModelBody(model, modelVariants) {
  const entries = summaryEntriesForModel(model.model_id);
  const runtimeEntries = summaryRuntimeEntriesForModel(model.model_id, modelVariants);
  const runtimeSelectors = new Set(runtimeEntries.map((entry) => entry.selector));
  const bySelector = new Map(modelVariants.map((variant) => [variantSelector(variant), variant]));
  const customRows = sortInventoryVariants(modelVariants.filter((variant) => variantIsCustom(variant) && !presetIsHidden(variant)));
  const customSelectors = new Set(customRows.map((variant) => variantSelector(variant)));
  const cards = runtimeEntries
    .filter((entry) => !customSelectors.has(String(entry?.selector || "")))
    .map((entry) =>
      renderSummaryVariantCard(entry.variant, model.model_id, {
        target: entry.target,
        hideRemove: true,
      }),
    )
    .concat(
      entries
        .filter((entry) => !runtimeSelectors.has(String(entry?.selector || "")) && !customSelectors.has(String(entry?.selector || "")))
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
  const statusTarget = target;
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
  const scoreLock = benchmarkJobActive();
  const ready = variantEffectiveInstallState(variant) === "ready";
  const rigBlockedReason = variantRigBlockReason(variant);
  const installState = modelInstallStateForVariant(variant);
  const installing = installState.job;
  const sharedInstalling = installState.shared;
  const disabled = ready ? !target || installing || !!rigBlockedReason : installing || !!rigBlockedReason;
  const bootSeconds = switchJobElapsedSeconds(switchJob);
  const launchLocked = ready && scoreLock;
  const buttonLabel = launchLocked
    ? "Locked"
    : installing
    ? modelInstallProgressLabel(installing)
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
    ? "green"
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
    sharedInstalling
      ? `<div class="variant-install-note"><strong>Download:</strong> ${escapeHtml(sharedModelInstallDescription(installing))}</div>`
      : !ready && variant.install_reason
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
    variantIsCustom(variant)
      ? `<div class="variant-meta"><strong>Origin:</strong> Custom import from ${escapeHtml(variant?.profile_like || variant?.profile_workload_id || "upstream pull")}</div>`
      : "";
  const gateNote =
    variantIsCustom(variant) && variant?.gate_terminal
      ? `<div class="variant-meta"><strong>Upstream gate:</strong> ${escapeHtml(String(variant.gate_terminal || "").replaceAll("→", " -> "))}</div>`
      : "";
  const footer = launchSeconds
    ? `<div class="variant-footer"><span class="variant-launch-time">${escapeHtml(formatElapsedLaunch(launchSeconds))}</span></div>`
    : "";
  const buttonTitle = launchLocked
    ? "Model Scores benchmarking is running"
    : ready
    ? active
      ? "Stop the running preset"
      : switching
        ? "Interrupt the preset boot"
        : failed
          ? "Retry this preset launch"
          : "Launch this preset"
    : installing?.job_id && !sharedInstalling
      ? "Stop the active model download"
      : installing?.job_id
        ? sharedModelInstallDescription(installing)
      : downloadButtonTitle(variant?.install_command || "");
  const action = ready
    ? active
      ? `promptScopedVariantStop('${escapeJs(selector)}','${escapeJs(targetId)}', false)`
      : switching
        ? `promptScopedVariantStop('${escapeJs(selector)}','${escapeJs(targetId)}', true)`
        : failed
          ? `switchInventoryVariant('${escapeJs(selector)}')`
          : `switchInventoryVariant('${escapeJs(selector)}')`
    : installing?.job_id && !sharedInstalling
      ? `requestStopModelInstall('${escapeJs(installing.job_id)}')`
      : `promptModelInstallById('${escapeJs(variant.variant_id)}')`;
  const metricsGroup = renderVariantMetricsGroup(variant);
  const settingsCluster = renderVariantSettingsCluster(variant, { cacheDisabled: active || switching || installing || scoreLock, deleteDisabled: active || switching || installing || scoreLock });
  const actionDisabled = !!rigBlockedReason || launchLocked || sharedInstalling || (ready && !target);
  const sideControls = settingsCluster;
  return `<div class="variant-card${active ? " active-variant" : ""}" data-preset-selector="${escapeHtml(selector)}"><div class="variant-card-head"><div class="variant-card-title">${renderPresetQueueTitleTag(selector)}<span>${escapeHtml(variantDisplayLabel(variant))}</span></div><div class="badge-row"><span class="state-badge ${stateClass}"${stateAttrs}>${escapeHtml(stateLabel)}</span>${statusBadge}${variantCapabilityBadges(variant)}${renderVariantLineageStar(variant)}</div></div><div class="variant-card-body"><div class="variant-card-main"><div class="variant-meta"><strong>Best for:</strong> ${escapeHtml(variant.best_for || "No summary yet.")}</div><div class="variant-meta"><strong>Max ctx:</strong> ${escapeHtml(variantMaxCtx(variant))} <strong>Engine:</strong> ${escapeHtml(prettyEngineName(variant.engine_display || variant.engine))} <strong>Drafter:</strong> ${escapeHtml(variant.drafter || "none")} <strong>KV:</strong> ${escapeHtml(variant.kv_format || "n/a")}</div>${provenanceNote}${gateNote}${hardwareNote}${rigBlockedNote}${caveat}${installNote}${failureNote}<div class="variant-actions variant-card-main-actions"><button class="btn ${buttonClass}" title="${escapeHtml(buttonTitle)}" ${actionDisabled ? "disabled" : ""} onclick="${action}">${escapeHtml(buttonLabel)}</button>${metricsGroup}</div>${footer}</div><aside class="variant-card-side">${renderPresetScoreLabel(selector, variant)}${sideControls}</aside></div></div>`;
}
function renderVariantGroup(title, rows, options = {}) {
  const items =
    title === "Experimental Docker Presets"
      ? experimentalVariantRows(rows)
      : sortInventoryVariants(rows);
  if (!items.length && options.hideEmpty !== false) return "";
  const body = items.length
    ? `<div class="variant-grid">${items.map(renderVariantCard).join("")}</div>`
    : `<div class="empty-variant-note">No presets discovered for this category.</div>`;
  const countLabel = `${title} (${items.length} Presets)`;
  const groupBadges =
    title === "Experimental Docker Presets" && items.length
      ? `<div class="variant-group-badges">${variantStatusBadgeSummary(items)}</div>`
      : "";
  const className = ["variant-group", options.className || ""].filter(Boolean).join(" ");
  return `<div class="${escapeHtml(className)}"><div class="variant-group-head"><h4>${escapeHtml(countLabel)}</h4>${groupBadges}</div>${body}</div>`;
}
function renderAdvancedVariantGroup(rows, deprecatedRows = [], options = {}) {
  const advancedRows = sortInventoryVariants([...(rows || []), ...(deprecatedRows || [])]);
  const nvlinkRows = advancedRows.filter((row) => resolvedVariantDisplayGroupKey(row, advancedRows) === "nvlink");
  const multiRows = advancedRows.filter((row) => resolvedVariantDisplayGroupKey(row, advancedRows) === "multi");
  if (!advancedRows.length && options.hideEmpty !== false) return "";
  const sections = [];
  if (nvlinkRows.length || options.hideEmpty === false) {
    sections.push(
      `<div class="variant-subgroup"><div class="variant-subgroup-title">NVLink Presets</div>${nvlinkRows.length ? `<div class="variant-grid">${nvlinkRows.map(renderVariantCard).join("")}</div>` : '<div class="empty-variant-note">No NVLink-specific presets discovered for this model.</div>'}</div>`,
    );
  }
  if (multiRows.length || options.hideEmpty === false) {
    sections.push(
      `<div class="variant-subgroup"><div class="variant-subgroup-title">Multi-GPU Presets</div>${multiRows.length ? `<div class="variant-grid">${multiRows.map(renderVariantCard).join("")}</div>` : '<div class="empty-variant-note">No shared multi-GPU presets discovered for this model.</div>'}</div>`,
    );
  }
  const className = ["variant-group", options.className || ""].filter(Boolean).join(" ");
  return `<div class="${escapeHtml(className)}"><div class="variant-group-head"><h4>${escapeHtml(`Advanced Docker Presets (${advancedRows.length} Presets)`)}</h4></div>${sections.join("")}</div>`;
}
function renderSelectedVariantGroups({ customRows = [], singleRows = [], dualRows = [], advancedRows = [], deprecatedRows = [], experimentalRows = [] } = {}) {
  const custom = renderVariantGroup("Custom Docker Presets", customRows, { className: "variant-group-custom" });
  const single = renderVariantGroup("Single GPU Docker Presets", singleRows, { className: "variant-group-single" });
  const dual = renderVariantGroup("Dual GPU Docker Presets", dualRows, { className: "variant-group-dual" });
  const advanced = renderAdvancedVariantGroup(advancedRows, deprecatedRows, { className: "variant-group-advanced" });
  const experimental = renderVariantGroup("Experimental Docker Presets", experimentalRows, { className: "variant-group-experimental" });
  const left = [single, advanced].filter(Boolean).join("");
  const right = [custom, dual, experimental].filter(Boolean).join("");
  if (!left && !right) return '<div class="empty-variant-note">No visible presets for this model.</div>';
  const layoutClass = left && right ? "variant-groups-two-column" : "variant-groups-single-column";
  return `<div class="variant-groups ${layoutClass}"><div class="variant-group-column variant-group-column-left">${left}</div><div class="variant-group-column variant-group-column-right">${right}</div></div>`;
}
function presetModelHtmlCacheIdentity() {
  const inventory = runtimeInventory();
  return {
    built_at: inventory?.built_at || "",
    repo_head: inventory?.repo_head || "",
    selectedPresetModelId: selectedPresetModelId || "",
    selectedScope: currentScope(),
    presetFilter: getPresetFilterState(),
  };
}
function readPresetModelHtmlCache() {
  try {
    const payload = JSON.parse(localStorage.getItem(PRESET_MODEL_HTML_CACHE_KEY) || "null");
    if (!payload || typeof payload !== "object" || typeof payload.html !== "string") return null;
    const expected = presetModelHtmlCacheIdentity();
    const identity = payload.identity && typeof payload.identity === "object" ? payload.identity : {};
    if (
      String(identity.built_at || "") !== String(expected.built_at || "") ||
      String(identity.repo_head || "") !== String(expected.repo_head || "") ||
      String(identity.selectedPresetModelId || "") !== String(expected.selectedPresetModelId || "") ||
      String(identity.selectedScope || "") !== String(expected.selectedScope || "") ||
      JSON.stringify(identity.presetFilter || {}) !== JSON.stringify(expected.presetFilter || {})
    ) {
      return null;
    }
    return payload;
  } catch (e) {}
  return null;
}
function writePresetModelHtmlCache(html, signature) {
  if (!html || !runtimeInventory().models?.length) return;
  try {
    localStorage.setItem(
      PRESET_MODEL_HTML_CACHE_KEY,
      JSON.stringify({
        saved_at: Date.now(),
        identity: presetModelHtmlCacheIdentity(),
        signature: signature || "",
        html,
      }),
    );
  } catch (e) {}
}
function renderCachedDynamicPresetModels() {
  ensureDynamicPresetLayout();
  hydrateSelectedPresetModel();
  renderPresetModelSelector();
  const host = $("modelPresetGrid");
  if (!host) return false;
  const payload = readPresetModelHtmlCache();
  if (!payload) return false;
  setHtmlIfChanged(host, payload.html);
  dynamicPresetRenderSignature = String(payload.signature || "");
  return true;
}
function dynamicPresetModelsRenderSignature() {
  const inventory = runtimeInventory();
  const status = lastStatus || {};
  const benchmark = benchmarkSnapshot(status);
  const job = benchmark?.job || {};
  const variantState = inventoryVariants().map((variant) => [
    variantSelector(variant),
    variant?.install_state,
    variant?.status,
    variant?.status_kind,
    variant?.resource_size_bytes,
    variant?.cache_size_bytes,
  ]);
  return JSON.stringify({
    selectedPresetModelId,
    selectedScope: currentScope(),
    presetFilter: getPresetFilterState(),
    inventory: {
      built_at: inventory?.built_at,
      repo_head: inventory?.repo_head,
      custom_models: inventory?.custom_models,
      models: inventoryModels().map((model) => [
        model?.model_id,
        model?.display_name,
        model?.installed_state,
        model?.summary,
      ]),
      variants: variantState,
    },
    hidden: hiddenPresetSelectors(),
    switch_job: status?.switch_job,
    switch_failure: status?.switch_failure,
    model_install_job: status?.model_install_job,
    model_install_jobs: status?.model_install_jobs,
    custom_model_job: status?.custom_model_job,
    instances: status?.instances,
    runtimes: status?.runtime_stats,
    benchmark_scores: benchmark?.scores,
    benchmark_job: {
      active: job?.active,
      mode: job?.mode,
      status: job?.status,
      queue: (job?.queue || []).map((row) => [
        row?.selector,
        row?.status,
        row?.step_id,
        row?.step_progress,
        row?.score,
      ]),
    },
    summary: {
      persistent: presetSummaryCache?.persistent,
      transient: presetSummaryCache?.transient,
      restartTargets: presetSummaryCache?.restartTargets,
    },
  });
}
function renderDynamicPresetModels(options = {}) {
  ensureDynamicPresetLayout();
  hydrateSelectedPresetModel();
  renderPresetModelSelector();
  const host = $("modelPresetGrid");
  if (!host) return;
  const nextSignature = dynamicPresetModelsRenderSignature();
  if (!options.force && dynamicPresetRenderSignature === nextSignature && host.childElementCount) return;
  const variants = inventoryVariants();
  const models = inventoryModels();
  if (!models.length) {
    setHtmlIfChanged(host, `<div class="model-card"><div class="empty-variant-note">No runtime inventory data was found. Rebuild the Model DB to rescan the upstream checkout.</div></div>`);
    dynamicPresetRenderSignature = nextSignature;
    return;
  }
  if (selectedPresetModelId === HIDDEN_PRESETS_MODEL_ID) {
    setHtmlIfChanged(host, renderHiddenPresetManagerView());
    dynamicPresetRenderSignature = nextSignature;
    return;
  }
  if (selectedPresetModelId === RESOURCE_MANAGER_MODEL_ID) {
    setHtmlIfChanged(host, renderModelResourceManagerView());
    dynamicPresetRenderSignature = nextSignature;
    return;
  }
  if (selectedPresetModelId === AI_STUDIO_MODEL_ID) {
    setHtmlIfChanged(host, renderAIStudioView());
    dynamicPresetRenderSignature = nextSignature;
    return;
  }
  const visibleModels = selectedPresetModelId
    ? models.filter((model) => String(model.model_id || "") === selectedPresetModelId)
    : models;
  const nextHtml = `${visibleModels
    .map((model) => {
      const modelVariants = variants.filter((row) => row.model_id === model.model_id);
      const unhiddenModelVariants = modelVariants.filter((row) => !presetIsHidden(row));
      const selected = String(model.model_id || "") === selectedPresetModelId;
      const visibleModelVariants = selected
        ? unhiddenModelVariants.filter((row) => variantMatchesPresetFilter(row))
        : unhiddenModelVariants;
      const familyActive = modelFamilyHasActivePreset(modelVariants);
      const presetCount = modelVariants.length;
      const summaryBody = renderSummaryModelBody(model, modelVariants);
      const deprecatedRows = [];
      const nonDeprecatedRows = visibleModelVariants;
      const groupKey = (row) => resolvedVariantDisplayGroupKey(row, unhiddenModelVariants);
      const customRows = nonDeprecatedRows.filter((row) => variantIsCustom(row) && !variantIsMigrated(row) && groupKey(row) !== "nvlink" && !variantOldCounterpartKey(row));
      const catalogRows = nonDeprecatedRows.filter((row) => !customRows.includes(row));
      const singleRows = catalogRows.filter((row) => groupKey(row) === "single");
      const dualRows = catalogRows.filter((row) => groupKey(row) === "dual");
      const advancedRows = catalogRows.filter((row) => ["nvlink", "multi"].includes(groupKey(row)));
      const experimentalRows = catalogRows.filter((row) => groupKey(row) === "experimental");
      const customDelete = modelIsCustom(model)
        ? `<span class="model-card-title-action">${renderIconButton({ title: "Remove custom model", action: `promptDeleteCustomModel('${escapeJs(model.model_id)}')`, icon: "delete" })}</span>`
        : "";
      const customBadge = modelIsCustom(model) && !modelVariants.some((row) => variantIsMigrated(row))
        ? '<span class="status-badge status-custom">custom</span>'
        : "";
      const body = selected
        ? renderSelectedVariantGroups({ customRows, singleRows, dualRows, advancedRows, deprecatedRows, experimentalRows })
        : summaryBody;
      const filteredCount = selected && presetFilterIsActive() ? `${visibleModelVariants.length}/${presetCount}` : String(presetCount);
      return `<div class="model-card${selected ? " selected-model-card" : " collapsed-model-card"}${familyActive ? " model-card-active-family" : ""}"><div class="model-card-head"><div><div class="model-card-title-row">${customDelete}<h3>${escapeHtml(model.display_name || model.model_id)} (${escapeHtml(filteredCount)} Presets)</h3></div><div class="model-summary">${escapeHtml(model.summary || "No summary available yet.")}</div></div><div class="badge-row"><span class="state-badge ${badgeClass("state", model.installed_state)}">${escapeHtml(String(model.installed_state || "unknown"))}</span>${customBadge}</div></div>${body}</div>`;
    })
    .join("")}${!selectedPresetModelId ? renderSummaryActionBar() : ""}`;
  setHtmlIfChanged(host, nextHtml);
  dynamicPresetRenderSignature = nextSignature;
  writePresetModelHtmlCache(nextHtml, nextSignature);
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
  const showIdleDownloadHint = !!selectedPresetModelId && ![HIDDEN_PRESETS_MODEL_ID, RESOURCE_MANAGER_MODEL_ID, AI_STUDIO_MODEL_ID].includes(selectedPresetModelId);
  if (showIdleDownloadHint && presetFilterIsActive()) {
    const rows = inventoryVariants().filter((row) => row.model_id === selectedPresetModelId && !presetIsHidden(row));
    const matched = rows.filter((row) => variantMatchesPresetFilter(row)).length;
    setHtmlIfChanged(
      target,
      `${escapeHtml(String(matched))}/${escapeHtml(String(rows.length))} presets matched by active filter &mdash; <button type="button" class="inline-link-button" onclick="return resetPresetFilterState()">click to reset filter settings</button>`,
    );
  } else {
    target.textContent = showIdleDownloadHint
      ? "Downloads started from this tab stream into Audit Logs and automatically rebuild the Model DB on success."
      : "";
  }
  target.classList.toggle("hidden", !target.textContent.trim());
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
  modal.className = "club-modal custom-model-modal hidden";
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
async function openCustomModelModal(preferredProfileLike = "") {
  try {
    await ensureFullRuntimeInventory();
  } catch (error) {
    alert(`Unable to load full profile templates: ${messageText(error)}`);
    return;
  }
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
  if (benchmarkJobActive()) {
    setElementMsg("customModelMsg", "Model Scores benchmarking is running. Cancel the benchmark before changing custom models.", "error");
    return;
  }
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
  if (benchmarkJobActive()) {
    alert("Model Scores benchmarking is running. Cancel the benchmark before changing custom models.");
    return;
  }
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
function isWeakAutoConversationTitle(value) {
  const title = sanitizeConversationTitle(value).toLowerCase();
  return /^(active chat preset|chat response|plan mode|interactive mode|ai studio|studio director|generation plan|multimedia plan|active preset|direct|qwen chat|qwen general|qwen coding|gemma coding|custom preset)$/.test(title);
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
  if (!conversation)
    return false;
  const currentTitle = chatConversationTitle(conversation);
  if (currentTitle !== CHAT_UNTITLED_TITLE) {
    const canReplaceWeakAutoTitle = conversation.autoNamed && isWeakAutoConversationTitle(currentTitle);
    if (!canReplaceWeakAutoTitle) return false;
  }
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
  const rows = runtimeStatsRows(lastStatus).filter((runtime) => runtime && runtime.running);
  const containers = Array.isArray(lastStatus?.ai_studio?.containers) ? lastStatus.ai_studio.containers : [];
  const director = containers.find((row) => String(row?.name || "") === "studio-director" && row.running);
  if (director) {
    rows.push({
      id: "STUDIO_DIRECTOR",
      instance_id: "STUDIO_DIRECTOR",
      selector: "ai-studio/director",
      mode: "ai-studio/director",
      chat_label: "AI Studio Director",
      container: "studio-director",
      engine: "llama.cpp",
      model_id: "qwen3.5-4b-uncensored",
      served_model_name: "qwen3.5-4b-uncensored",
      gpu_indices: Array.isArray(director?.gpu_indices)
        ? director.gpu_indices.map(Number).filter((value) => Number.isFinite(value))
        : [],
      running: true,
    });
  }
  return rows;
}

