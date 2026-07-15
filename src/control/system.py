def _normalize_ratio_percent(value):
    number = safe_float(value)
    if number <= 1.0:
        number *= 100.0
    return round(number, 2)


def _log_metric_present(value):
    return value not in (None, "")


def _positive_float(value):
    try:
        number = float(value)
    except Exception:
        return None
    return number if number > 0 else None


def _peak_metric_value(*values):
    peak = None
    for value in values:
        number = _positive_float(value)
        if number is None:
            continue
        if peak is None or number > peak:
            peak = number
    return peak


def _speculative_metric_score(spec):
    row = spec if isinstance(spec, dict) else {}
    score = 0
    for key in (
        "drafted_tokens",
        "draft_tokens",
        "accepted_tokens",
        "accept_rate_pct",
        "mean_acceptance_length",
        "system_efficiency_pct",
    ):
        if row.get(key) in (None, ""):
            continue
        score += 1
        if safe_float(row.get(key)) > 0:
            score += 2
    return score


def _merge_speculative_metric_row(target, updates):
    row = dict(target or {})
    changed = False
    for key, value in dict(updates or {}).items():
        if value in (None, ""):
            continue
        if row.get(key) == value:
            continue
        row[key] = value
        changed = True
    return row, changed


def _parse_speculative_metric_line(line):
    text = str(line or "").strip()
    if not text:
        return {}
    spec = {}
    drafted_match = re.search(r"Number of speculative tokens:\s*([0-9]+)", text)
    accepted_match = re.search(r"(?:Number of accepted tokens|Accepted):\s*([0-9]+)", text)
    draft_tokens_match = re.search(r"(?:Number of draft tokens|Drafted):\s*([0-9]+)", text)
    emitted_match = re.search(r"Number of emitted tokens:\s*([0-9]+)", text)
    accept_rate_match = re.search(r"(?:Draft acceptance rate|Avg Draft acceptance rate):\s*([0-9.]+)%?", text)
    efficiency_match = re.search(r"System efficiency:\s*([0-9.]+)", text)
    mean_accept_match = re.search(r"Mean acceptance length:\s*([0-9.]+)", text)
    if drafted_match:
        spec["drafted_tokens"] = int(drafted_match.group(1))
    if accepted_match:
        spec["accepted_tokens"] = int(accepted_match.group(1))
    if draft_tokens_match:
        spec["draft_tokens"] = int(draft_tokens_match.group(1))
    if emitted_match:
        spec["emitted_tokens"] = int(emitted_match.group(1))
    if accept_rate_match:
        spec["accept_rate_pct"] = _normalize_ratio_percent(accept_rate_match.group(1))
    if efficiency_match:
        spec["system_efficiency_pct"] = _normalize_ratio_percent(efficiency_match.group(1))
    if mean_accept_match:
        spec["mean_acceptance_length"] = round(safe_float(mean_accept_match.group(1)), 2)
    ik_accept_match = re.search(
        r"draft acceptance rate\s*=\s*([0-9.]+)\s*\(\s*([0-9]+)\s+accepted\s*/\s*([0-9]+)\s+generated\s*\)",
        text,
        flags=re.I,
    )
    if ik_accept_match:
        spec["accept_rate_pct"] = _normalize_ratio_percent(ik_accept_match.group(1))
        spec["accepted_tokens"] = int(ik_accept_match.group(2))
        spec["draft_tokens"] = int(ik_accept_match.group(3))
    mtp_match = re.search(
        r"statistics\s+mtp:\s*#calls\(b,g,a\)\s*=\s*[0-9]+\s+[0-9]+\s+[0-9]+,\s*#gen drafts\s*=\s*([0-9]+),\s*#acc drafts\s*=\s*([0-9]+),\s*#gen tokens\s*=\s*([0-9]+),\s*#acc tokens\s*=\s*([0-9]+)",
        text,
        flags=re.I,
    )
    if mtp_match:
        generated_drafts = int(mtp_match.group(1))
        accepted_drafts = int(mtp_match.group(2))
        generated_tokens = int(mtp_match.group(3))
        accepted_tokens = int(mtp_match.group(4))
        spec["drafted_tokens"] = generated_drafts
        spec["accepted_drafts"] = accepted_drafts
        spec["draft_tokens"] = generated_tokens
        spec["accepted_tokens"] = accepted_tokens
        if generated_tokens > 0:
            spec["accept_rate_pct"] = _normalize_ratio_percent(
                accepted_tokens / max(generated_tokens, 1)
            )
        if accepted_drafts > 0:
            spec["mean_acceptance_length"] = round(
                accepted_tokens / max(accepted_drafts, 1),
                2,
            )
    return spec


def benchmark_job_active_from_state_file():
    try:
        state = read_json_file(os.path.join(CONTROL_DIR, "benchmarks", "state.json"), {})
    except Exception:
        return False
    if not isinstance(state, dict):
        return False
    status = str(state.get("status") or "").strip().lower()
    if bool(state.get("active")) or status == "running":
        return True
    for row in state.get("queue") or []:
        if isinstance(row, dict) and str(row.get("status") or "").strip().lower() == "running":
            return True
    return False


def benchmark_power_status_overlay_from_state_file():
    try:
        state = read_json_file(os.path.join(CONTROL_DIR, "benchmarks", "state.json"), {})
    except Exception:
        return {}
    if not isinstance(state, dict):
        return {}
    status = str(state.get("status") or "").strip().lower()
    rows = [row for row in (state.get("queue") or []) if isinstance(row, dict)]
    running = [row for row in rows if str(row.get("status") or "").strip().lower() == "running"]
    if not (bool(state.get("active")) or status == "running" or running):
        return {}
    row = running[0] if running else {}
    step_id = str(row.get("step_id") or "").strip().lower()
    label = str(row.get("step_label") or "").strip()
    label_lower = label.lower()
    profile = "benchmark-ready"
    gpu_state = "benchmark-ready"
    if step_id == "bench" or "throughput" in label_lower:
        if "turbo" in label_lower:
            profile = "turbo"
            gpu_state = "benchmark-turbo"
        elif "fast" in label_lower:
            profile = "fast"
            gpu_state = "benchmark-fast"
        else:
            gpu_state = "benchmark-throughput"
    elif "safe" in label_lower:
        profile = "benchmark-safe"
        gpu_state = "benchmark-safe"
    display = str(row.get("display_name") or row.get("selector") or "").strip()
    return {
        "profile": profile,
        "gpu": gpu_state,
        "cpu": "benchmark",
        "container": f"benchmarking {display}" if display else "benchmarking",
        "last_action": "benchmark_active",
        "benchmark_step_label": label,
    }


def estimate_request_prefill_seconds(prompt_tokens, output_tokens, ttft_s, latency_s, generation_tps):
    prompt_count = _positive_float(prompt_tokens)
    if prompt_count is None:
        return None
    ttft = _positive_float(ttft_s)
    latency = _positive_float(latency_s)
    generation = _positive_float(generation_tps)
    output_count = _positive_float(output_tokens)
    if ttft is not None:
        if (
            latency is not None
            and generation is not None
            and output_count is not None
            and ttft >= latency * 0.8
        ):
            buffered_prefill = latency - (output_count / max(generation, 0.001))
            if buffered_prefill > 0.001:
                return round(buffered_prefill, 3)
        if generation is not None:
            corrected_ttft = ttft - (1.0 / max(generation, 0.001))
            if corrected_ttft > 0.001:
                return round(corrected_ttft, 3)
        return round(max(ttft, 0.001), 3)
    if latency is not None and generation is not None and output_count is not None:
        estimated_prefill = latency - (output_count / max(generation, 0.001))
        if estimated_prefill > 0.001:
            return round(estimated_prefill, 3)
    return None


def derive_request_prompt_tps(prompt_tokens, output_tokens, ttft_s, latency_s, generation_tps, *fallback_values):
    prefill_s = estimate_request_prefill_seconds(
        prompt_tokens,
        output_tokens,
        ttft_s,
        latency_s,
        generation_tps,
    )
    derived = None
    prompt_count = _positive_float(prompt_tokens)
    if prefill_s is not None and prompt_count is not None:
        derived = prompt_count / max(prefill_s, 0.001)
    peak = _peak_metric_value(derived, *fallback_values)
    return round(peak, 2) if peak is not None else None


def estimate_generation_tps_from_stream(output_tokens, first_token_at, last_token_at, min_elapsed_s=0.25):
    tokens = _positive_float(output_tokens)
    first_seen = _positive_float(first_token_at)
    last_seen = _positive_float(last_token_at)
    if tokens is None or first_seen is None or last_seen is None or last_seen <= first_seen:
        return None
    elapsed = last_seen - first_seen
    if elapsed < max(0.0, float(min_elapsed_s or 0.0)):
        return None
    return round(tokens / elapsed, 2)


def authoritative_output_tokens_from_usage(usage):
    if not isinstance(usage, dict):
        return None
    output_tokens = int(first_defined(usage.get("completion_tokens"), usage.get("output_tokens"), 0) or 0)
    return output_tokens if output_tokens > 0 else None


def resolve_best_generation_tps(log_candidate, authoritative_tokens, fallback_tokens, first_token_at, last_token_at):
    authoritative_estimate = estimate_generation_tps_from_stream(
        authoritative_tokens,
        first_token_at,
        last_token_at,
        min_elapsed_s=0.05,
    )
    heuristic_estimate = None
    if authoritative_estimate is None:
        heuristic_estimate = estimate_generation_tps_from_stream(
            fallback_tokens,
            first_token_at,
            last_token_at,
            min_elapsed_s=0.25,
        )
    peak = _peak_metric_value(
        log_candidate,
        authoritative_estimate,
        heuristic_estimate,
    )
    return round(peak, 2) if peak is not None else None


def _runtime_log_metrics_score(metrics_row):
    row = metrics_row if isinstance(metrics_row, dict) else {}
    score = 0
    for key in ("prompt_tps", "generation_tps", "gpu_kv_cache_usage_pct", "cpu_kv_cache_usage_pct", "prefix_cache_hit_rate_pct"):
        value = row.get(key)
        if not _log_metric_present(value):
            continue
        score += 1
        if safe_float(value) > 0:
            score += 2
    for key in ("running_requests", "waiting_requests", "pending_requests", "swapped_requests"):
        if _log_metric_present(row.get(key)):
            score += 1
    if row.get("speculative"):
        score += 1
    if not any(int(row.get(key) or 0) > 0 for key in ("running_requests", "waiting_requests", "pending_requests", "swapped_requests")):
        score += 1
    return score


def clear_gpu_session_peaks():
    with metrics_lock:
        gpu_session_peaks.clear()
    log_control("GPU session peaks reset")
    return {"cleared": True}


def update_system_metric_peaks(point, *, persist=True):
    global system_metric_peaks_cache
    row = point if isinstance(point, dict) else {}
    with system_metric_peaks_lock:
        peaks = _read_system_metric_peaks_unlocked()
        changed = False
        charts = dict(peaks.get("charts") or {})
        for key in SYSTEM_METRIC_PEAK_CHART_KEYS:
            next_value = _sanitize_metric_peak_number(row.get(key))
            if next_value is None:
                continue
            current_value = _sanitize_metric_peak_number(charts.get(key))
            if current_value is None or next_value > current_value:
                charts[key] = next_value
                changed = True
        gpu_rows = {
            str(key): dict(value)
            for key, value in (peaks.get("gpus") or {}).items()
            if isinstance(value, dict)
        }
        for gpu_row in row.get("gpus") or []:
            gpu_key = re.sub(r"[^0-9]+", "", str(gpu_row.get("index") or "").strip())
            if not gpu_key:
                continue
            current_gpu = dict(gpu_rows.get(gpu_key) or {})
            next_gpu = dict(current_gpu)
            for key in SYSTEM_METRIC_PEAK_GPU_KEYS:
                next_value = _sanitize_metric_peak_number(gpu_row.get(key))
                if next_value is None:
                    continue
                current_value = _sanitize_metric_peak_number(current_gpu.get(key))
                if current_value is None or next_value > current_value:
                    next_gpu[key] = next_value
            if next_gpu != current_gpu:
                gpu_rows[gpu_key] = next_gpu
                changed = True
        next_peaks = sanitize_system_metric_peaks(
            {
                "charts": charts,
                "gpus": gpu_rows,
            }
        )
        if changed and persist:
            return _write_system_metric_peaks_unlocked(next_peaks)
        if isinstance(next_peaks, dict):
            system_metric_peaks_cache = next_peaks
        return next_peaks


METRICS_HISTORY_POINT_KEYS = (
    "t",
    "gpu_util",
    "mem_pct",
    "mem_used_gib",
    "mem_total_gib",
    "temp_c",
    "power_w",
    "ram_pct",
    "ram_used_gib",
    "ram_total_gib",
    "cpu_pct",
    "disk_pct",
    "system_util_pct",
    "net_rx_mbps",
    "net_tx_mbps",
    "net_rx_kbps",
    "net_tx_kbps",
    "active_requests",
    "latency_s",
    "ttft_s",
    "tps",
)

METRICS_HISTORY_GPU_KEYS = (
    "index",
    "util",
    "mem_pct",
    "temp",
    "temp_junction",
    "temp_junction_c",
    "temp_vram",
    "temp_vram_c",
    "power",
    "fan",
    "failed",
    "frozen",
    "failure_mode",
)


def sanitize_metrics_history_point(point):
    data = point if isinstance(point, dict) else {}
    try:
        ts = int(float(data.get("t") or 0))
    except Exception:
        ts = 0
    if ts <= 0:
        return None
    clean = {"t": ts}
    for key in METRICS_HISTORY_POINT_KEYS:
        if key == "t":
            continue
        value = data.get(key)
        upper_bound = SYSTEM_METRIC_PEAK_CHART_LIMITS.get(key)
        if isinstance(value, bool):
            clean[key] = int(value)
        elif isinstance(value, (int, float)):
            numeric = float(value)
            if upper_bound is not None and numeric > float(upper_bound):
                continue
            clean[key] = round(numeric, 3)
        elif isinstance(value, str) and value.strip():
            numeric = safe_float(value)
            if upper_bound is not None and numeric > float(upper_bound):
                continue
            clean[key] = round(float(numeric), 3)
    gpu_rows = []
    for gpu in data.get("gpus") or []:
        if not isinstance(gpu, dict):
            continue
        gpu_row = {}
        for key in METRICS_HISTORY_GPU_KEYS:
            value = gpu.get(key)
            if isinstance(value, bool):
                gpu_row[key] = bool(value)
            elif isinstance(value, (int, float)):
                gpu_row[key] = round(float(value), 3)
            elif isinstance(value, str):
                gpu_row[key] = value[:200]
        if gpu_row.get("index") is not None:
            gpu_rows.append(gpu_row)
    clean["gpus"] = gpu_rows
    return clean


def prune_metrics_history_points(points):
    cutoff = int(time.time() - METRICS_HISTORY_RETENTION_SECONDS)
    seen = {}
    for point in points or []:
        clean = sanitize_metrics_history_point(point)
        if not clean or int(clean.get("t") or 0) < cutoff:
            continue
        seen[int(clean["t"])] = clean
    ordered = [seen[key] for key in sorted(seen.keys())]
    return ordered[-int(METRICS_HISTORY_MAX_POINTS):]


def ensure_metrics_history_loaded():
    with metrics_history_lock:
        if metrics_history_cache.get("loaded"):
            return
        raw = read_json_file(METRICS_HISTORY_FILE, {})
        raw_points = raw.get("series") if isinstance(raw, dict) else []
        points = prune_metrics_history_points(raw_points if isinstance(raw_points, list) else [])
        metrics_history_cache["loaded"] = True
        metrics_history_cache["write_time"] = time.time()
    with metrics_lock:
        if not series_points:
            for point in points:
                series_points.append(point)
    if points:
        log_control(f"Loaded {len(points)} persisted metric history points")


def persist_metrics_history_if_due(force=False):
    now = time.time()
    with metrics_lock:
        points = prune_metrics_history_points(list(series_points))
    with metrics_history_lock:
        if not force and now - safe_float(metrics_history_cache.get("write_time")) < METRICS_HISTORY_PERSIST_INTERVAL_SECONDS:
            return False
        payload = {
            "schema_version": 1,
            "updated_at": int(now),
            "retention_seconds": int(METRICS_HISTORY_RETENTION_SECONDS),
            "series": points,
        }
        write_json_atomic_if_changed(METRICS_HISTORY_FILE, payload, separators=(",", ":"))
        metrics_history_cache["loaded"] = True
        metrics_history_cache["write_time"] = now
        return True


def normalize_status_series_limit(value, default=METRICS_HISTORY_STATUS_MAX_POINTS):
    try:
        limit = int(float(str(value).strip()))
    except Exception:
        limit = int(default or METRICS_HISTORY_STATUS_MAX_POINTS)
    return max(1, min(int(METRICS_HISTORY_STATUS_MAX_POINTS), limit))


def metric_series_status_snapshot_unlocked(max_points=None):
    limit = normalize_status_series_limit(max_points)
    total = len(series_points)
    if total <= limit:
        return list(series_points)
    step = max(1, int(math.ceil(total / max(1, limit))))
    sampled = [point for index, point in enumerate(series_points) if index % step == 0]
    if series_points:
        sampled.append(series_points[-1])
    return sampled[-limit:]


def clear_recorded_metrics_history():
    global latest_gpu_rows, latest_system_snapshot, latest_metrics_collected_at, system_metric_peaks_cache
    with metrics_lock:
        series_points.clear()
        gpu_session_peaks.clear()
        latest_gpu_rows = []
        latest_system_snapshot = {}
        latest_metrics_collected_at = 0.0
    with system_metric_peaks_lock:
        system_metric_peaks_cache = {"charts": {}, "gpus": {}}
        write_json_atomic_if_changed(
            SYSTEM_METRIC_PEAKS_FILE,
            system_metric_peaks_cache,
            indent=2,
            sort_keys=True,
        )
    with metrics_history_lock:
        write_json_atomic_if_changed(
            METRICS_HISTORY_FILE,
            {
                "schema_version": 1,
                "updated_at": int(time.time()),
                "retention_seconds": int(METRICS_HISTORY_RETENTION_SECONDS),
                "series": [],
            },
            separators=(",", ":"),
        )
        metrics_history_cache["loaded"] = True
        metrics_history_cache["write_time"] = time.time()
    log_audit("admin_metrics_history_cleared")
    return {
        "ok": True,
        "series": [],
        "system_metric_peaks": system_metric_peaks_snapshot(),
    }


def parse_runtime_log_metrics(text):
    metrics_out = {
        "prompt_tps": None,
        "generation_tps": None,
        "running_requests": None,
        "waiting_requests": None,
        "pending_requests": None,
        "swapped_requests": None,
        "gpu_kv_cache_usage_pct": None,
        "cpu_kv_cache_usage_pct": None,
        "prefix_cache_hit_rate_pct": None,
        "speculative": {},
    }
    lines = [str(line or "").strip() for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    for line in reversed(lines):
        lower_line = line.lower()
        release_ctx_match = re.search(r"\bn_ctx\s*=\s*([0-9]+)\b", line)
        release_used_match = re.search(r"\bn_past\s*=\s*([0-9]+)\b", line)
        if (
            "Avg prompt throughput:" in line
            or "Avg generation throughput:" in line
            or "Running:" in line
            or "Waiting:" in line
            or "Pending:" in line
            or "Swapped:" in line
            or "GPU KV cache usage:" in line
            or "CPU KV cache usage:" in line
            or "Prefix cache hit rate:" in line
            or "prompt cache:" in lower_line
        ):
            prompt_match = re.search(r"Avg prompt throughput:\s*([0-9.]+)\s*tokens/s", line)
            gen_match = re.search(r"Avg generation throughput:\s*([0-9.]+)\s*tokens/s", line)
            running_match = re.search(r"Running:\s*([0-9]+)\s*reqs", line)
            waiting_match = re.search(r"Waiting:\s*([0-9]+)\s*reqs", line)
            pending_match = re.search(r"Pending:\s*([0-9]+)\s*reqs", line)
            swapped_match = re.search(r"Swapped:\s*([0-9]+)\s*reqs", line)
            gpu_kv_match = re.search(r"GPU KV cache usage:\s*([0-9.]+)\s*%?", line)
            cpu_kv_match = re.search(r"CPU KV cache usage:\s*([0-9.]+)\s*%?", line)
            prefix_match = re.search(r"Prefix cache hit rate:\s*(?:GPU:\s*)?([0-9.]+)\s*%?", line)
            prompt_cache_keep_match = re.search(r"\bf_keep[:=]\s*([0-9.]+)", line, flags=re.I)
            if metrics_out["prompt_tps"] is None and prompt_match:
                metrics_out["prompt_tps"] = round(safe_float(prompt_match.group(1)), 2)
            if metrics_out["generation_tps"] is None and gen_match:
                metrics_out["generation_tps"] = round(safe_float(gen_match.group(1)), 2)
            if metrics_out["running_requests"] is None and running_match:
                metrics_out["running_requests"] = int(running_match.group(1))
            if metrics_out["waiting_requests"] is None and waiting_match:
                metrics_out["waiting_requests"] = int(waiting_match.group(1))
            if metrics_out["pending_requests"] is None and pending_match:
                metrics_out["pending_requests"] = int(pending_match.group(1))
            if metrics_out["swapped_requests"] is None and swapped_match:
                metrics_out["swapped_requests"] = int(swapped_match.group(1))
            if metrics_out["gpu_kv_cache_usage_pct"] is None and gpu_kv_match:
                metrics_out["gpu_kv_cache_usage_pct"] = _normalize_ratio_percent(gpu_kv_match.group(1))
            if metrics_out["cpu_kv_cache_usage_pct"] is None and cpu_kv_match:
                metrics_out["cpu_kv_cache_usage_pct"] = _normalize_ratio_percent(cpu_kv_match.group(1))
            if metrics_out["prefix_cache_hit_rate_pct"] is None and prefix_match:
                metrics_out["prefix_cache_hit_rate_pct"] = _normalize_ratio_percent(prefix_match.group(1))
            elif metrics_out["prefix_cache_hit_rate_pct"] is None and prompt_cache_keep_match:
                metrics_out["prefix_cache_hit_rate_pct"] = _normalize_ratio_percent(
                    prompt_cache_keep_match.group(1)
                )
        if (
            metrics_out["gpu_kv_cache_usage_pct"] is None
            and release_ctx_match
            and release_used_match
        ):
            ctx_size = safe_float(release_ctx_match.group(1))
            used_tokens = safe_float(release_used_match.group(1))
            if ctx_size > 0 and used_tokens >= 0:
                metrics_out["gpu_kv_cache_usage_pct"] = round(
                    max(0.0, min(100.0, (used_tokens / ctx_size) * 100.0)),
                    2,
                )
        spec_updates = _parse_speculative_metric_line(line)
        if spec_updates:
            metrics_out["speculative"], _ = _merge_speculative_metric_row(
                metrics_out.get("speculative"),
                spec_updates,
            )
        if metrics_out["prompt_tps"] is not None and metrics_out["speculative"]:
            break
    return metrics_out


def parse_runtime_log_metric_peaks(text):
    peaks = {
        "prompt_tps": None,
        "generation_tps": None,
        "running_requests": None,
        "waiting_requests": None,
        "pending_requests": None,
        "swapped_requests": None,
        "gpu_kv_cache_usage_pct": None,
        "cpu_kv_cache_usage_pct": None,
        "prefix_cache_hit_rate_pct": None,
        "speculative": {},
    }
    for raw_line in str(text or "").splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        lower_line = line.lower()
        release_ctx_match = re.search(r"\bn_ctx\s*=\s*([0-9]+)\b", line)
        release_used_match = re.search(r"\bn_past\s*=\s*([0-9]+)\b", line)
        prompt_match = re.search(r"Avg prompt throughput:\s*([0-9.]+)\s*tokens/s", line)
        gen_match = re.search(r"Avg generation throughput:\s*([0-9.]+)\s*tokens/s", line)
        running_match = re.search(r"Running:\s*([0-9]+)\s*reqs", line)
        waiting_match = re.search(r"Waiting:\s*([0-9]+)\s*reqs", line)
        pending_match = re.search(r"Pending:\s*([0-9]+)\s*reqs", line)
        swapped_match = re.search(r"Swapped:\s*([0-9]+)\s*reqs", line)
        gpu_kv_match = re.search(r"GPU KV cache usage:\s*([0-9.]+)\s*%?", line)
        cpu_kv_match = re.search(r"CPU KV cache usage:\s*([0-9.]+)\s*%?", line)
        prefix_match = re.search(r"Prefix cache hit rate:\s*(?:GPU:\s*)?([0-9.]+)\s*%?", line)
        prompt_cache_keep_match = re.search(r"\bf_keep[:=]\s*([0-9.]+)", line, flags=re.I)
        if prompt_match:
            value = round(safe_float(prompt_match.group(1)), 2)
            if peaks["prompt_tps"] is None or value > safe_float(peaks["prompt_tps"]):
                peaks["prompt_tps"] = value
        if gen_match:
            value = round(safe_float(gen_match.group(1)), 2)
            if peaks["generation_tps"] is None or value > safe_float(peaks["generation_tps"]):
                peaks["generation_tps"] = value
        if running_match:
            value = int(running_match.group(1))
            if peaks["running_requests"] is None or value > int(peaks["running_requests"] or 0):
                peaks["running_requests"] = value
        if waiting_match:
            value = int(waiting_match.group(1))
            if peaks["waiting_requests"] is None or value > int(peaks["waiting_requests"] or 0):
                peaks["waiting_requests"] = value
        if pending_match:
            value = int(pending_match.group(1))
            if peaks["pending_requests"] is None or value > int(peaks["pending_requests"] or 0):
                peaks["pending_requests"] = value
        if swapped_match:
            value = int(swapped_match.group(1))
            if peaks["swapped_requests"] is None or value > int(peaks["swapped_requests"] or 0):
                peaks["swapped_requests"] = value
        if gpu_kv_match:
            value = _normalize_ratio_percent(gpu_kv_match.group(1))
            if peaks["gpu_kv_cache_usage_pct"] is None or value > safe_float(peaks["gpu_kv_cache_usage_pct"]):
                peaks["gpu_kv_cache_usage_pct"] = value
        if cpu_kv_match:
            value = _normalize_ratio_percent(cpu_kv_match.group(1))
            if peaks["cpu_kv_cache_usage_pct"] is None or value > safe_float(peaks["cpu_kv_cache_usage_pct"]):
                peaks["cpu_kv_cache_usage_pct"] = value
        if prefix_match:
            value = _normalize_ratio_percent(prefix_match.group(1))
            if peaks["prefix_cache_hit_rate_pct"] is None or value > safe_float(peaks["prefix_cache_hit_rate_pct"]):
                peaks["prefix_cache_hit_rate_pct"] = value
        elif "prompt cache:" in lower_line and prompt_cache_keep_match:
            value = _normalize_ratio_percent(prompt_cache_keep_match.group(1))
            if peaks["prefix_cache_hit_rate_pct"] is None or value > safe_float(peaks["prefix_cache_hit_rate_pct"]):
                peaks["prefix_cache_hit_rate_pct"] = value
        if release_ctx_match and release_used_match:
            ctx_size = safe_float(release_ctx_match.group(1))
            used_tokens = safe_float(release_used_match.group(1))
            if ctx_size > 0 and used_tokens >= 0:
                value = round(max(0.0, min(100.0, (used_tokens / ctx_size) * 100.0)), 2)
                if peaks["gpu_kv_cache_usage_pct"] is None or value > safe_float(peaks["gpu_kv_cache_usage_pct"]):
                    peaks["gpu_kv_cache_usage_pct"] = value
        spec_updates = _parse_speculative_metric_line(line)
        if spec_updates and _speculative_metric_score(spec_updates) >= _speculative_metric_score(peaks.get("speculative")):
            peaks["speculative"] = dict(spec_updates)
    return peaks


def runtime_log_metrics_for_container(container_name, force=False, max_age=1.0):
    cache_key = str(container_name or "").strip()
    if not cache_key:
        return {}
    now = time.time()
    with slow_cache_lock:
        cached = dict(runtime_log_metrics_cache.get(cache_key) or {})
        cached_value = dict(cached.get("value") or {})
        cached_time = float(cached.get("time") or 0.0)
    if not force and cached_time and now - cached_time < max(0.5, float(max_age or 1.0)):
        return cached_value
    watcher = get_runtime_log_watcher(cache_key)
    if watcher is None:
        return cached_value
    snapshot = watcher.snapshot()
    parsed = parse_runtime_log_metrics(snapshot.get("text") or "")
    active_now = any(int(parsed.get(key) or 0) > 0 for key in ("running_requests", "waiting_requests", "pending_requests", "swapped_requests"))
    with slow_cache_lock:
        remembered = dict(runtime_log_metric_memory.get(cache_key) or {})
    if _log_metric_present(parsed.get("gpu_kv_cache_usage_pct")):
        remembered["gpu_kv_cache_usage_pct"] = parsed.get("gpu_kv_cache_usage_pct")
    elif not active_now and remembered.get("gpu_kv_cache_usage_pct") not in (None, ""):
        parsed["gpu_kv_cache_usage_pct"] = remembered.get("gpu_kv_cache_usage_pct")
    if _log_metric_present(parsed.get("cpu_kv_cache_usage_pct")):
        remembered["cpu_kv_cache_usage_pct"] = parsed.get("cpu_kv_cache_usage_pct")
    elif not active_now and remembered.get("cpu_kv_cache_usage_pct") not in (None, ""):
        parsed["cpu_kv_cache_usage_pct"] = remembered.get("cpu_kv_cache_usage_pct")
    if _log_metric_present(parsed.get("prefix_cache_hit_rate_pct")):
        remembered["prefix_cache_hit_rate_pct"] = parsed.get("prefix_cache_hit_rate_pct")
    elif not active_now and remembered.get("prefix_cache_hit_rate_pct") not in (None, ""):
        parsed["prefix_cache_hit_rate_pct"] = remembered.get("prefix_cache_hit_rate_pct")
    if parsed.get("speculative"):
        remembered["speculative"] = dict(parsed.get("speculative") or {})
    elif not active_now and remembered.get("speculative"):
        parsed["speculative"] = dict(remembered.get("speculative") or {})
    with slow_cache_lock:
        runtime_log_metric_memory[cache_key] = dict(remembered)
    with slow_cache_lock:
        runtime_log_metrics_cache[cache_key] = {"value": dict(parsed), "time": time.time()}
    return parsed


def settle_runtime_log_metrics_for_container(container_name, max_wait=0.45, interval=0.09):
    cache_key = str(container_name or "").strip()
    if not cache_key:
        return {}
    best = runtime_log_metrics_for_container(cache_key, force=True, max_age=0.0)
    best_score = _runtime_log_metrics_score(best)
    idle_snapshots = 0
    deadline = time.time() + max(0.0, float(max_wait or 0.0))
    while time.time() < deadline:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(max(0.02, float(interval or 0.09)), remaining))
        current = runtime_log_metrics_for_container(cache_key, force=True, max_age=0.0)
        current_score = _runtime_log_metrics_score(current)
        if current_score >= best_score:
            best = current
            best_score = current_score
        active_now = any(int(current.get(key) or 0) > 0 for key in ("running_requests", "waiting_requests", "pending_requests", "swapped_requests"))
        if active_now:
            idle_snapshots = 0
            continue
        idle_snapshots += 1
        if idle_snapshots >= 2 and any(_log_metric_present(best.get(key)) for key in ("prompt_tps", "generation_tps", "gpu_kv_cache_usage_pct", "prefix_cache_hit_rate_pct")):
            break
    return best


def merge_runtime_metric_peaks(base_metrics, peak_metrics):
    merged = dict(base_metrics or {})
    peaks = peak_metrics if isinstance(peak_metrics, dict) else {}
    for key in ("prompt_tps", "generation_tps"):
        base_value = safe_float(merged.get(key))
        peak_value = safe_float(peaks.get(key))
        if peak_value > base_value:
            merged[key] = round(peak_value, 2)
    for key in ("gpu_kv_cache_usage_pct", "cpu_kv_cache_usage_pct", "prefix_cache_hit_rate_pct"):
        if merged.get(key) in (None, "") and peaks.get(key) not in (None, ""):
            merged[key] = round(safe_float(peaks.get(key)), 2)
    if not merged.get("speculative") and peaks.get("speculative"):
        merged["speculative"] = dict(peaks.get("speculative") or {})
    return merged


def resolve_request_generation_tps(*metric_rows):
    peak = None
    for row in metric_rows:
        if not isinstance(row, dict):
            continue
        peak = _peak_metric_value(
            peak,
            row.get("generation_tps"),
            row.get("last_tokens_per_second"),
        )
    return round(peak, 2) if peak is not None else None


def collect_request_window_log_metric_peaks(log_watcher, start_generation, start_seq):
    if log_watcher is None:
        return {}
    try:
        request_log_update = log_watcher.collect_updates_since(
            start_generation,
            start_seq,
        )
    except Exception:
        return {}
    return parse_runtime_log_metric_peaks(request_log_update.get("text") or "")


def gpu_vendors_by_index():
    vendors = []
    try:
        out = subprocess.check_output(["lspci", "-v", "-m"], text=True, stderr=subprocess.DEVNULL, timeout=4)
        block = []
        for line in out.splitlines() + [""]:
            if line.strip():
                block.append(line)
                continue
            if not block:
                continue
            rec = {}
            for b in block:
                if ":" in b:
                    k, v = b.split(":", 1)
                    rec[k.strip()] = v.strip().strip('"')
            cls = rec.get("Class", "")
            vendor = rec.get("SVendor", "")
            if ("VGA" in cls or "3D" in cls) and vendor:
                first = vendor.split()[0]
                if first and first.lower() not in ("nvidia", "corporation"):
                    vendors.append(first)
            block = []
    except Exception:
        pass
    return {str(i): v for i, v in enumerate(vendors)}

gpu_extra_temps_cache = {"ts": 0.0, "rows": {}, "error": ""}

def gpu_extra_temperature_cmd():
    configured = str(os.environ.get("CLUB3090_GPUTEMPS_CMD") or "").strip()
    candidates = [
        configured,
        os.path.join(CONTROL_DIR, "bin", "gputemps"),
        shutil.which("gputemps") or "",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return ""

def gpu_extra_temperature_rows(max_age=2.0):
    now = time.time()
    cached_rows = gpu_extra_temps_cache.get("rows") if isinstance(gpu_extra_temps_cache, dict) else {}
    cached_error = str(gpu_extra_temps_cache.get("error") or "") if isinstance(gpu_extra_temps_cache, dict) else ""
    cached_ts = safe_float(gpu_extra_temps_cache.get("ts") if isinstance(gpu_extra_temps_cache, dict) else 0)
    if cached_ts and now - cached_ts < (30.0 if cached_error and not cached_rows else max_age):
        return cached_rows if isinstance(cached_rows, dict) else {}
    cmd = gpu_extra_temperature_cmd()
    if not cmd:
        gpu_extra_temps_cache.update({"ts": now, "rows": {}, "error": "gputemps helper not installed"})
        return {}
    try:
        out = subprocess.check_output(
            [cmd, "--json", "--once"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=2.5,
        )
        first_line = next((line.strip() for line in out.splitlines() if line.strip().startswith("{")), "")
        payload = json.loads(first_line) if first_line else {}
        rows = {}
        for item in payload.get("gpus") or []:
            if not isinstance(item, dict):
                continue
            idx = str(item.get("index") if item.get("index") is not None else "").strip()
            if not idx:
                continue
            rows[idx] = {
                "core": _positive_float(item.get("core")),
                "junction": _positive_float(item.get("junction")),
                "vram": _positive_float(item.get("vram")),
                "timestamp": payload.get("timestamp"),
            }
        gpu_extra_temps_cache.update({"ts": now, "rows": rows, "error": ""})
        return rows
    except Exception as e:
        gpu_extra_temps_cache.update({"ts": now, "rows": {}, "error": str(e)[-500:]})
        return {}

GPU_LAST_SEEN_ROW_KEYS = (
    "index",
    "name",
    "vendor",
    "temp_c",
    "temp_peak_c",
    "temp_junction_c",
    "temp_junction_peak_c",
    "temp_vram_c",
    "temp_vram_peak_c",
    "temp_aux_source",
    "util_pct",
    "mem_used_mib",
    "mem_total_mib",
    "mem_free_mib",
    "mem_pct",
    "power_w",
    "power_peak_w",
    "power_limit_w",
    "fan_pct",
    "core_clock_mhz",
    "core_clock_peak_mhz",
    "mem_clock_mhz",
    "mem_clock_peak_mhz",
    "compute_cap",
)


def gpu_last_seen_key(value):
    return re.sub(r"[^0-9]+", "", str(value or "").strip())


def sanitize_gpu_last_seen_snapshot(payload):
    data = payload if isinstance(payload, dict) else {}
    gpus = data.get("gpus") if isinstance(data.get("gpus"), dict) else {}
    clean = {"schema_version": 1, "updated_at": safe_float(data.get("updated_at")), "gpus": {}}
    for key, row in gpus.items():
        gpu_key = gpu_last_seen_key(key)
        source = row if isinstance(row, dict) else {}
        gpu_key = gpu_key or gpu_last_seen_key(source.get("index"))
        if not gpu_key:
            continue
        clean_row = {}
        for row_key in GPU_LAST_SEEN_ROW_KEYS:
            value = source.get(row_key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                clean_row[row_key] = value
        clean_row["index"] = clean_row.get("index") if str(clean_row.get("index") or "").strip() else gpu_key
        clean_row["last_seen_at"] = safe_float(source.get("last_seen_at") or data.get("updated_at"))
        if source.get("last_seen_iso"):
            clean_row["last_seen_iso"] = str(source.get("last_seen_iso"))[:80]
        clean["gpus"][gpu_key] = clean_row
    return clean


def _read_gpu_last_seen_unlocked():
    cached = gpu_last_seen_cache.get("value") if isinstance(gpu_last_seen_cache, dict) else None
    if isinstance(cached, dict):
        return sanitize_gpu_last_seen_snapshot(cached)
    raw = read_json_file(GPU_LAST_SEEN_FILE, {})
    clean = sanitize_gpu_last_seen_snapshot(raw)
    gpu_last_seen_cache["value"] = clean
    gpu_last_seen_cache["time"] = time.time()
    return clean


def gpu_last_seen_snapshot():
    with gpu_last_seen_lock:
        return _read_gpu_last_seen_unlocked()


def persist_gpu_last_seen_rows(rows):
    healthy = [
        row
        for row in (rows or [])
        if isinstance(row, dict)
        and not row.get("error")
        and not row.get("failed")
        and gpu_last_seen_key(row.get("index"))
    ]
    if not healthy:
        return gpu_last_seen_snapshot()
    now = time.time()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    with gpu_last_seen_lock:
        snapshot = _read_gpu_last_seen_unlocked()
        next_rows = dict(snapshot.get("gpus") or {})
        for row in healthy:
            gpu_key = gpu_last_seen_key(row.get("index"))
            clean_row = {
                key: row.get(key)
                for key in GPU_LAST_SEEN_ROW_KEYS
                if isinstance(row.get(key), (str, int, float, bool)) or row.get(key) is None
            }
            clean_row["index"] = str(row.get("index") or gpu_key)
            clean_row["last_seen_at"] = now
            clean_row["last_seen_iso"] = now_iso
            next_rows[gpu_key] = clean_row
        next_snapshot = sanitize_gpu_last_seen_snapshot({"schema_version": 1, "updated_at": now, "gpus": next_rows})
        gpu_last_seen_cache["value"] = next_snapshot
        gpu_last_seen_cache["time"] = now
        if now - safe_float(gpu_last_seen_cache.get("write_time")) >= 10:
            write_json_atomic_if_changed(GPU_LAST_SEEN_FILE, next_snapshot, indent=2, sort_keys=True)
            gpu_last_seen_cache["write_time"] = now
        return next_snapshot


def gpu_failure_mode_from_errors(errors):
    text = " | ".join(str(item or "").strip() for item in (errors or []) if str(item or "").strip())
    lower = text.lower()
    if "unable to determine the device handle" in lower:
        return "Device handle unavailable"
    if "unknown error" in lower:
        return "NVIDIA driver unknown error"
    if "query failed" in lower:
        return "NVIDIA telemetry unavailable"
    return "Missing from NVIDIA telemetry"


def failed_gpu_row_from_last_seen(index_key, last_row, peak_row, errors):
    now = time.time()
    row = dict(last_row or {})
    row["index"] = str(row.get("index") or index_key)
    row["name"] = str(row.get("name") or f"GPU {index_key}")
    row["failed"] = True
    row["frozen"] = True
    row["status"] = "Failure"
    row["failure_mode"] = gpu_failure_mode_from_errors(errors)
    row["failure_detail"] = " | ".join(str(item or "").strip() for item in (errors or []) if str(item or "").strip())[-2000:]
    last_seen_at = safe_float(row.get("last_seen_at"))
    row["stale_seconds"] = round(max(0.0, now - last_seen_at), 1) if last_seen_at else None
    peak = peak_row if isinstance(peak_row, dict) else {}
    peak_map = {
        "temp_peak_c": "temp",
        "temp_junction_peak_c": "temp_junction",
        "temp_vram_peak_c": "temp_vram",
        "power_peak_w": "power",
        "fan_pct": "fan",
    }
    for target_key, peak_key in peak_map.items():
        if row.get(target_key) in (None, "", "N/A") and peak.get(peak_key) is not None:
            row[target_key] = peak.get(peak_key)
    if row.get("temp_c") in (None, "", "N/A") and peak.get("temp") is not None:
        row["temp_c"] = peak.get("temp")
    if row.get("temp_junction_c") in (None, "", "N/A") and peak.get("temp_junction") is not None:
        row["temp_junction_c"] = peak.get("temp_junction")
    if row.get("temp_vram_c") in (None, "", "N/A") and peak.get("temp_vram") is not None:
        row["temp_vram_c"] = peak.get("temp_vram")
    if row.get("power_w") in (None, "", "N/A") and peak.get("power") is not None:
        row["power_w"] = peak.get("power")
    return row


def merge_failed_gpu_rows(rows, errors=None):
    rows = [dict(row) for row in (rows or []) if isinstance(row, dict)]
    current_keys = {gpu_last_seen_key(row.get("index")) for row in rows if gpu_last_seen_key(row.get("index"))}
    snapshot = gpu_last_seen_snapshot()
    peaks = system_metric_peaks_snapshot()
    last_rows = snapshot.get("gpus") if isinstance(snapshot.get("gpus"), dict) else {}
    peak_rows = peaks.get("gpus") if isinstance(peaks.get("gpus"), dict) else {}
    for key in sorted(set(last_rows.keys()) | set(peak_rows.keys()), key=lambda item: int(item) if str(item).isdigit() else 9999):
        if key in current_keys:
            continue
        rows.append(failed_gpu_row_from_last_seen(key, last_rows.get(key), peak_rows.get(key), errors or []))
    rows.sort(key=lambda row: int(gpu_last_seen_key(row.get("index")) or "9999") if gpu_last_seen_key(row.get("index") or "") else 9999)
    return rows


def gpu_stats():
    if not shutil.which("nvidia-smi"):
        return []
    vendor_map = gpu_vendors_by_index()
    extra_temps = gpu_extra_temperature_rows()
    try:
        persisted_peak_rows = (system_metric_peaks_snapshot().get("gpus") or {})
    except Exception:
        persisted_peak_rows = {}
    field_sets = [
        "index,name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,power.limit,fan.speed,clocks.current.graphics,clocks.current.memory,compute_cap",
        "index,name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,power.limit,fan.speed,clocks.current.graphics,clocks.current.memory",
    ]
    out = ""
    last_error = None
    query_errors = []
    for fields in field_sets:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=4,
            )
            break
        except Exception as e:
            last_error = e
    if not out:
        merged = merge_failed_gpu_rows([], [str(last_error or "nvidia-smi query failed")])
        return merged or [{"error": str(last_error or "nvidia-smi query failed")}]
    rows = []
    for line in out.splitlines():
        line_text = str(line or "").strip()
        if not line_text:
            continue
        if "unable to determine" in line_text.lower() or "unknown error" in line_text.lower():
            query_errors.append(line_text)
            continue
        parts = [x.strip() for x in line.split(",")]
        try:
            compute_cap = ""
            if len(parts) >= 12:
                idx,name,temp_core,util,mem_used,mem_total,power,power_limit,fan,gfx_clk,mem_clk,compute_cap = parts[:12]
            elif len(parts) >= 11:
                idx,name,temp_core,util,mem_used,mem_total,power,power_limit,fan,gfx_clk,mem_clk = parts[:11]
            elif len(parts) >= 9:
                idx,name,temp_core,util,mem_used,mem_total,power,power_limit,fan = parts[:9]
                gfx_clk = mem_clk = "N/A"
                compute_cap = ""
            else:
                continue
            used = safe_float(mem_used); total = safe_float(mem_total)
            temp_now = None if str(temp_core).strip() in {"", "N/A", "[Not Supported]"} else safe_float(temp_core)
            power_now = None if str(power).strip() in {"", "N/A", "[Not Supported]"} else safe_float(power)
            core_clock_now = None if str(gfx_clk).strip() in {"", "N/A", "[Not Supported]"} else safe_float(gfx_clk)
            mem_clock_now = None if str(mem_clk).strip() in {"", "N/A", "[Not Supported]"} else safe_float(mem_clk)
            extra = extra_temps.get(str(idx)) if isinstance(extra_temps, dict) else {}
            junction_now = (extra or {}).get("junction")
            vram_temp_now = (extra or {}).get("vram")
            peak_key = str(idx)
            with metrics_lock:
                peak_row = gpu_session_peaks.setdefault(peak_key, {})
                persisted_peak = persisted_peak_rows.get(peak_key) if isinstance(persisted_peak_rows, dict) else {}
                if isinstance(persisted_peak, dict):
                    for persisted_key, session_key in (
                        ("temp", "temp_c"),
                        ("temp_junction", "temp_junction_c"),
                        ("temp_vram", "temp_vram_c"),
                        ("power", "power_w"),
                    ):
                        persisted_value = _positive_float(persisted_peak.get(persisted_key))
                        if persisted_value is not None:
                            peak_row[session_key] = round(max(persisted_value, safe_float(peak_row.get(session_key))), 2)
                if temp_now is not None:
                    peak_row["temp_c"] = round(max(temp_now, safe_float(peak_row.get("temp_c"))), 2)
                if junction_now is not None:
                    peak_row["temp_junction_c"] = round(max(junction_now, safe_float(peak_row.get("temp_junction_c"))), 2)
                if vram_temp_now is not None:
                    peak_row["temp_vram_c"] = round(max(vram_temp_now, safe_float(peak_row.get("temp_vram_c"))), 2)
                if power_now is not None:
                    peak_row["power_w"] = round(max(power_now, safe_float(peak_row.get("power_w"))), 2)
                if core_clock_now is not None:
                    peak_row["core_clock_mhz"] = round(max(core_clock_now, safe_float(peak_row.get("core_clock_mhz"))), 2)
                if mem_clock_now is not None:
                    peak_row["mem_clock_mhz"] = round(max(mem_clock_now, safe_float(peak_row.get("mem_clock_mhz"))), 2)
                peak_temp = peak_row.get("temp_c")
                peak_junction = peak_row.get("temp_junction_c")
                peak_vram_temp = peak_row.get("temp_vram_c")
                peak_power = peak_row.get("power_w")
                peak_core = peak_row.get("core_clock_mhz")
                peak_mem = peak_row.get("mem_clock_mhz")
            row = {
                "index":idx,
                "name":name,
                "vendor":vendor_map.get(str(idx), ""),
                "temp_c":temp_core,
                "temp_peak_c":peak_temp,
                "util_pct":util,
                "mem_used_mib":mem_used,
                "mem_total_mib":mem_total,
                "mem_free_mib":round(max(total-used,0),1) if total else 0,
                "mem_pct":round((used/total*100),1) if total else 0,
                "power_w":power,
                "power_peak_w":peak_power,
                "power_limit_w":power_limit,
                "fan_pct":fan,
                "core_clock_mhz":gfx_clk,
                "core_clock_peak_mhz":peak_core,
                "mem_clock_mhz":mem_clk,
                "mem_clock_peak_mhz":peak_mem,
                "compute_cap": str(compute_cap or "").strip(),
            }
            if junction_now is not None:
                row["temp_junction_c"] = round(junction_now, 1)
                row["temp_junction_peak_c"] = peak_junction
            if vram_temp_now is not None:
                row["temp_vram_c"] = round(vram_temp_now, 1)
                row["temp_vram_peak_c"] = peak_vram_temp
            if junction_now is not None or vram_temp_now is not None:
                row["temp_aux_source"] = "gputemps"
            rows.append(row)
        except Exception as e:
            rows.append({"error": f"parse gpu stat failed: {e}"})
    persist_gpu_last_seen_rows(rows)
    return merge_failed_gpu_rows(rows, query_errors)

def safe_float(value):
    try:
        return float(str(value).replace("N/A", "0").replace("[Not Supported]", "0").strip())
    except Exception:
        return 0.0

_cpu_prev = None

def memory_stats():
    data = {}
    try:
        with open('/proc/meminfo', 'r', encoding='utf-8') as f:
            for line in f:
                k, v = line.split(':', 1)
                data[k] = safe_float(v.split()[0]) / 1024.0
        total = data.get('MemTotal', 0); avail = data.get('MemAvailable', 0); used = max(total-avail,0)
        return {"total_mib":round(total,1),"used_mib":round(used,1),"free_mib":round(avail,1),"used_pct":round((used/total*100),1) if total else 0}
    except Exception as e:
        return {"error": str(e)}


def machine_uptime_seconds():
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as handle:
            return int(float((handle.read().split() or ["0"])[0]))
    except Exception:
        return 0

def _read_cpu_times():
    rows=[]
    try:
        with open('/proc/stat','r',encoding='utf-8') as f:
            for line in f:
                if not line.startswith('cpu'):
                    break
                parts=line.split()
                if parts[0]=='cpu': name='total'
                elif parts[0][3:].isdigit(): name=parts[0][3:]
                else: continue
                vals=[int(x) for x in parts[1:]]; idle=vals[3]+(vals[4] if len(vals)>4 else 0); total=sum(vals)
                rows.append((name,idle,total))
    except Exception:
        pass
    return rows

def cpu_stats():
    global _cpu_prev
    cur=_read_cpu_times()
    if not cur: return {"total_pct":0,"cores":[]}
    prev=_cpu_prev; _cpu_prev={n:(i,t) for n,i,t in cur}
    cores=[]; total_pct=0
    for name,idle,total in cur:
        pct=0.0
        if prev and name in prev:
            pi,pt=prev[name]; dt=max(total-pt,1); di=max(idle-pi,0); pct=max(0.0,min(100.0,(1-di/dt)*100))
        if name=='total': total_pct=round(pct,1)
        else: cores.append({"core":name,"usage_pct":round(pct,1)})
    return {"total_pct":total_pct,"cores":cores}

def _fmt_gib(num_bytes):
    try:
        return round(float(num_bytes) / (1024**3), 2)
    except Exception:
        return 0.0



def disk_stats():
    """Return physical disks and volumes with best-effort real filesystem
    usage. Mounted filesystems use shutil.disk_usage; unmounted ext* filesystems
    use dumpe2fs when available; lsblk FSUSED/FSAVAIL is used when populated.
    Physical disks aggregate child volume usage where real usage is known, and
    otherwise fall back to partition allocation without pretending it is FS free.
    """
    def norm_mounts(val):
        if isinstance(val, list):
            return [m for m in val if m and m != '[SWAP]']
        return [m for m in str(val or '').replace('\\x0a','\n').splitlines() if m and m != '[SWAP]']

    def walk(nodes, parent=''):
        out=[]
        for n in nodes or []:
            n=dict(n)
            n['_parent']=parent
            out.append(n)
            out.extend(walk(n.get('children') or [], n.get('name') or parent))
        return out

    def findmnt_value(column, mountpoint='/'):
        if not shutil.which('findmnt'):
            return ''
        try:
            p=subprocess.run(['findmnt','-n','-o',column,mountpoint], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=4)
            if p.returncode == 0:
                return (p.stdout or '').strip().splitlines()[0].strip()
        except Exception:
            pass
        return ''

    def synthetic_root_volume(root_row_present):
        if root_row_present:
            return None
        try:
            usage=shutil.disk_usage(os.sep)
        except Exception:
            return None
        source=findmnt_value('SOURCE', os.sep) or os.sep
        clean_source=str(source or os.sep).split('[',1)[0]
        path=clean_source if clean_source.startswith('/dev/') else source
        name=(clean_source.rsplit('/',1)[-1] if clean_source.startswith('/dev/') else 'root') or 'root'
        fs=(findmnt_value('FSTYPE', os.sep) or 'unknown').strip()
        total=usage.total; used=usage.used; free=usage.free
        used_pct=round((used/total*100),1) if total else 0.0
        return {
            'name': name, 'path': path, 'source': source, 'type': 'part',
            'kind': 'volume', 'partition_type': 'root filesystem',
            'fs': fs, 'label': 'root', 'mount': os.sep, 'mounted': True,
            'model': '', 'transport': '',
            'total_gib': _fmt_gib(total), 'used_gib': _fmt_gib(used), 'free_gib': _fmt_gib(free),
            'size': f"{_fmt_gib(total)}G", 'used': f"{_fmt_gib(used)}G", 'avail': f"{_fmt_gib(free)}G",
            'used_pct': used_pct, 'user_facing': True, 'usage_basis': 'mounted root filesystem',
            'root_volume': True
        }

    def ext_usage(path):
        """Best-effort usage for unmounted ext filesystems via dumpe2fs."""
        if not path or not shutil.which('dumpe2fs'):
            return None
        try:
            p=subprocess.run(['dumpe2fs','-h',path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=8)
            if p.returncode != 0:
                return None
            vals={}
            for line in p.stdout.splitlines():
                if ':' in line:
                    k,v=line.split(':',1)
                    vals[k.strip().lower()]=v.strip().split()[0]
            block_count=int(float(vals.get('block count','0')))
            free_blocks=int(float(vals.get('free blocks','0')))
            block_size=int(float(vals.get('block size','0')))
            if block_count > 0 and block_size > 0:
                total=block_count*block_size
                free=max(0, free_blocks*block_size)
                used=max(0, total-free)
                return total, used, free, 'ext filesystem'
        except Exception:
            return None
        return None

    def _first_number(text):
        import re
        m=re.search(r'([0-9][0-9,]*)', str(text or ''))
        return int(m.group(1).replace(',','')) if m else None

    def ntfs_usage(path):
        """Best-effort usage for unmounted NTFS via ntfsinfo. If the
        installed ntfsinfo does not expose free clusters/bytes, return None so
        the UI shows Unknown instead of fake Free=0/Used=Total.
        """
        if not path or not shutil.which('ntfsinfo'):
            return None
        text_parts=[]
        for args in (['ntfsinfo','-m',path], ['ntfsinfo',path]):
            try:
                p=subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10)
                if p.stdout:
                    text_parts.append(p.stdout)
            except Exception:
                pass
        text='\n'.join(text_parts)
        if not text:
            return None
        vals={}
        for line in text.splitlines():
            if ':' in line:
                k,v=line.split(':',1)
                vals[k.strip().lower()]=v.strip()
        def get(*keys):
            for k in keys:
                if k in vals:
                    n=_first_number(vals[k])
                    if n is not None:
                        return n
            return None
        cluster=get('cluster size','bytes per cluster','bytes/cluster')
        total_clusters=get('volume size in clusters','number of clusters','total clusters','clusters')
        free_clusters=get('free clusters')
        total_bytes=get('volume size','current volume size')
        free_bytes=get('free space','free bytes')
        if total_bytes and free_bytes is not None:
            total=total_bytes; free=max(0, free_bytes); used=max(0, total-free)
            return total, used, free, 'ntfs filesystem'
        if cluster and total_clusters and free_clusters is not None:
            total=cluster*total_clusters; free=max(0, cluster*free_clusters); used=max(0, total-free)
            return total, used, free, 'ntfs filesystem'
        return None

    rows=[]
    try:
        out=subprocess.check_output([
            'lsblk','-b','-J','-a','-o',
            'NAME,PATH,PKNAME,TYPE,FSTYPE,LABEL,PARTLABEL,PARTTYPENAME,PARTTYPE,MOUNTPOINTS,SIZE,MODEL,TRAN,FSUSED,FSAVAIL,FSSIZE'
        ], text=True, stderr=subprocess.DEVNULL, timeout=8)
        data=json.loads(out or '{}')
        flat=walk(data.get('blockdevices') or [])
        by_parent={}
        for rec in flat:
            parent=rec.get('pkname') or rec.get('_parent') or ''
            by_parent.setdefault(parent,[]).append(rec)

        usage_by_name={}
        pending_disks=[]
        for rec in flat:
            typ=(rec.get('type') or '').strip()
            if typ not in ('disk','part','crypt','lvm','raid0','raid1','raid5','raid6','raid10','md'):
                continue
            path=rec.get('path') or ('/dev/'+rec.get('name',''))
            name=rec.get('name') or path
            size=int(safe_float(rec.get('size')))
            mounts=norm_mounts(rec.get('mountpoints'))
            mount=mounts[0] if mounts else ''
            mounted=bool(mount)
            total=size; used=0; free=0; used_pct=0.0
            real_usage=False; usage_basis='allocation'

            if typ == 'disk':
                pending_disks.append(rec)
                continue

            if mounted:
                try:
                    usage=shutil.disk_usage(mount)
                    total=usage.total; used=usage.used; free=usage.free
                    used_pct=round((used/total*100),1) if total else 0.0
                    real_usage=True; usage_basis='mounted filesystem'
                except Exception:
                    mounted=False
            if not real_usage:
                fsused=int(safe_float(rec.get('fsused')))
                fsavail=int(safe_float(rec.get('fsavail')))
                fssize=int(safe_float(rec.get('fssize')))
                if fssize > 0 and (fsused > 0 or fsavail > 0):
                    total=fssize; used=fsused; free=fsavail
                    used_pct=round((used/total*100),1) if total else 0.0
                    real_usage=True; usage_basis='lsblk filesystem'
            fstype_lower=(rec.get('fstype') or '').lower()
            if not real_usage and fstype_lower.startswith('ext'):
                ext=ext_usage(path)
                if ext:
                    total, used, free, usage_basis = ext
                    used_pct=round((used/total*100),1) if total else 0.0
                    real_usage=True
            if not real_usage and fstype_lower in ('ntfs','ntfs3'):
                ntfs=ntfs_usage(path)
                if ntfs:
                    total, used, free, usage_basis = ntfs
                    used_pct=round((used/total*100),1) if total else 0.0
                    real_usage=True
                else:
                    usage_basis='ntfs unmounted; free/used unknown'
            if not real_usage:
                total=size; used=None; free=None; used_pct=None
                if usage_basis == 'allocation':
                    usage_basis='unknown filesystem usage'

            usage_by_name[name]={'total':total,'used':used,'free':free,'real':real_usage,'size':size}
            label=rec.get('label') or rec.get('partlabel') or ''
            part_type=(rec.get('parttypename') or rec.get('parttype') or typ or '').strip()
            fs=(rec.get('fstype') or 'unknown').strip()
            user_facing = bool(
                typ in ('part','crypt','lvm','md') and
                fs.lower() not in ('swap',) and
                not any(x in (mount or '').lower() for x in ('/boot', '/efi')) and
                not any(x in (label or '').lower() for x in ('recovery','reserved','swap','efi','boot')) and
                not any(x in part_type.lower() for x in ('efi','reserved','recovery','bios boot','swap'))
            )
            rows.append({
                'name': name, 'path': path, 'source': path, 'type': typ,
                'kind': 'volume', 'partition_type': part_type or typ,
                'fs': fs, 'label': label, 'mount': mount, 'mounted': mounted,
                'model': (rec.get('model') or '').strip(), 'transport': rec.get('tran') or '',
                'total_gib': _fmt_gib(total) if total is not None else None, 'used_gib': _fmt_gib(used) if used is not None else None, 'free_gib': _fmt_gib(free) if free is not None else None,
                'size': f"{_fmt_gib(total)}G" if total is not None else 'unknown', 'used': f"{_fmt_gib(used)}G" if used is not None else 'unknown', 'avail': f"{_fmt_gib(free)}G" if free is not None else 'unknown',
                'used_pct': used_pct, 'user_facing': user_facing,
                'usage_basis': usage_basis
            })

        root_row=synthetic_root_volume(any(row.get('mount') == os.sep for row in rows if isinstance(row, dict)))
        if root_row:
            rows.append(root_row)

        for rec in pending_disks:
            name=rec.get('name') or rec.get('path') or ''
            path=rec.get('path') or ('/dev/'+name)
            size=int(safe_float(rec.get('size')))
            children=by_parent.get(name, [])
            allocated=sum(int(safe_float(c.get('size'))) for c in children if (c.get('type') or '') in ('part','crypt','lvm','md','raid0','raid1','raid5','raid6','raid10'))
            real_children=[]
            for c in children:
                u=usage_by_name.get(c.get('name') or '')
                if u and u.get('real'):
                    real_children.append(u)
            if real_children:
                used=sum(int(u.get('used',0)) for u in real_children)
                free=sum(int(u.get('free',0)) for u in real_children)
                total=sum(int(u.get('total',0)) for u in real_children) or size
                basis='child filesystems'
            else:
                used=max(0, min(size, allocated)); free=max(0, size-used); total=size
                basis='partition allocation'
            used_pct=round((used/total*100),1) if total else 0.0
            rows.append({
                'name': name, 'path': path, 'source': path, 'type': 'disk', 'kind': 'disk',
                'partition_type': 'disk', 'fs': 'disk', 'label': '', 'mount': '', 'mounted': False,
                'model': (rec.get('model') or '').strip(), 'transport': rec.get('tran') or '',
                'total_gib': _fmt_gib(total) if total is not None else None, 'used_gib': _fmt_gib(used) if used is not None else None, 'free_gib': _fmt_gib(free) if free is not None else None,
                'size': f"{_fmt_gib(total)}G" if total is not None else 'unknown', 'used': f"{_fmt_gib(used)}G" if used is not None else 'unknown', 'avail': f"{_fmt_gib(free)}G" if free is not None else 'unknown',
                'used_pct': used_pct, 'user_facing': False, 'usage_basis': basis
            })

        order={'disk':0,'part':1,'crypt':2,'lvm':3,'md':4,'raid0':4,'raid1':4,'raid5':4,'raid6':4,'raid10':4}
        rows.sort(key=lambda d:(order.get(d.get('type'),9), d.get('path') or d.get('name') or ''))
    except Exception as e:
        rows.append({'error':str(e)})
    return rows[:128]


def cpu_package_inventory():
    packages = {}
    try:
        block = {}

        def commit(record):
            if not record:
                return
            raw_package = record.get("physical id")
            try:
                package_id = int(str(raw_package).strip()) if raw_package not in (None, "") else len(packages)
            except Exception:
                package_id = len(packages)
            package = packages.setdefault(
                package_id,
                {
                    "package": package_id,
                    "model": str(record.get("model name") or record.get("Processor") or "unknown").strip() or "unknown",
                    "cores": 0,
                    "threads": 0,
                    "numa_node": str(record.get("numa node(s)") or "").strip(),
                },
            )
            package["threads"] += 1
            try:
                package["cores"] = max(package["cores"], int(str(record.get("cpu cores") or 0).strip() or 0))
            except Exception:
                pass

        with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                line = raw_line.rstrip("\n")
                if not line.strip():
                    commit(block)
                    block = {}
                    continue
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                block[key.strip().lower()] = value.strip()
        commit(block)
    except Exception:
        return []
    rows = [packages[key] for key in sorted(packages)]
    for row in rows:
        if row.get("cores", 0) <= 0:
            row["cores"] = row.get("threads", 0)
    return rows


def vram_totals(gpu_rows=None):
    total_mib = 0.0
    free_mib = 0.0
    for row in gpu_rows if isinstance(gpu_rows, list) else gpu_stats():
        if not isinstance(row, dict) or row.get("error"):
            continue
        total_mib += safe_float(row.get("mem_total_mib"))
        free_mib += safe_float(row.get("mem_free_mib"))
    return {
        "total_mib": round(total_mib, 1),
        "free_mib": round(free_mib, 1),
        "used_mib": round(max(total_mib - free_mib, 0.0), 1),
    }


def system_info(gpu_rows=None):
    def read_first(path):
        try:
            return open(path, 'r', encoding='utf-8', errors='ignore').read().strip()
        except Exception:
            return ''
    os_name='unknown'
    try:
        vals={}
        with open('/etc/os-release','r',encoding='utf-8',errors='ignore') as f:
            for line in f:
                if '=' in line:
                    k,v=line.rstrip().split('=',1); vals[k]=v.strip('"')
        os_name=vals.get('PRETTY_NAME') or vals.get('NAME') or os_name
    except Exception:
        pass
    cpu_model='unknown'
    try:
        out=subprocess.check_output(['lscpu'], text=True, stderr=subprocess.DEVNULL, timeout=3)
        for line in out.splitlines():
            if line.startswith('Model name:'):
                cpu_model=line.split(':',1)[1].strip(); break
    except Exception:
        pass
    gpu_names=[]
    source_rows = gpu_rows if isinstance(gpu_rows, list) else []
    try:
        source_rows = gpu_rows if gpu_rows is not None else gpu_stats()
        gpu_names=[g.get('name') for g in source_rows if isinstance(g,dict) and g.get('name')]
    except Exception:
        pass
    memory = memory_stats()
    vram = vram_totals(source_rows)
    return {
        'os': os_name,
        'kernel': platform.release(),
        'hostname': socket.gethostname(),
        'username': os.environ.get('USER') or os.environ.get('LOGNAME') or 'unknown',
        'machine': platform.machine(),
        'cpu_model': cpu_model,
        'cpu_packages': cpu_package_inventory(),
        'board': read_first('/sys/devices/virtual/dmi/id/board_name'),
        'product': read_first('/sys/devices/virtual/dmi/id/product_name'),
        'bios': read_first('/sys/devices/virtual/dmi/id/bios_version'),
        'gpus': ', '.join(gpu_names) if gpu_names else 'unknown',
        'memory_total_mib': memory.get('total_mib'),
        'memory_free_mib': memory.get('free_mib'),
        'vram_total_mib': vram.get('total_mib'),
        'vram_free_mib': vram.get('free_mib'),
    }

_net_prev = None
_public_ip_cache = {'value':'unknown','time':0}


def _read_net_bytes():
    rows={}
    try:
        with open('/proc/net/dev','r',encoding='utf-8') as f:
            for line in f.readlines()[2:]:
                if ':' not in line:
                    continue
                iface, rest = line.split(':',1)
                iface=iface.strip()
                if iface == 'lo':
                    continue
                vals=rest.split()
                if len(vals) >= 16:
                    rows[iface]={'rx':int(vals[0]),'tx':int(vals[8])}
    except Exception:
        pass
    return rows


def local_ip():
    try:
        s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(('8.8.8.8',80))
        ip=s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return 'unknown'


def public_ip():
    now=time.time()
    # Avoid blocking the status endpoint every few seconds if public IP lookup
    # is unavailable. Successful lookups are cached longer than failures.
    cache_age = now - _public_ip_cache.get('time', 0)
    if _public_ip_cache.get('value') != 'unknown' and cache_age < 900:
        return _public_ip_cache['value']
    if _public_ip_cache.get('value') == 'unknown' and cache_age < 120:
        return 'unknown'
    for url in ('https://ifconfig.me/ip','https://api.ipify.org'):
        try:
            req=urllib.request.Request(url, headers={'User-Agent':'club3090-control'})
            with urllib.request.urlopen(req, timeout=1.5) as r:
                val=r.read(80).decode('utf-8','ignore').strip()
                if val:
                    _public_ip_cache.update({'value':val,'time':now})
                    return val
        except Exception:
            pass
    _public_ip_cache.update({'value':'unknown','time':now})
    return 'unknown'


def network_stats():
    global _net_prev
    now=time.time(); cur=_read_net_bytes(); prev=_net_prev; _net_prev=(now,cur)
    ifaces=[]; total_rx=total_tx=0.0
    for iface, vals in cur.items():
        rx_mbps=tx_mbps=0.0
        if prev and iface in prev[1]:
            dt=max(now-prev[0],0.001)
            rx_mbps=max(0.0,(vals['rx']-prev[1][iface]['rx'])*8/1000/1000/dt)
            tx_mbps=max(0.0,(vals['tx']-prev[1][iface]['tx'])*8/1000/1000/dt)
        total_rx += rx_mbps; total_tx += tx_mbps
        ifaces.append({
            'iface':iface,
            'rx_mbps':round(rx_mbps,2),
            'tx_mbps':round(tx_mbps,2),
            'rx_kbps':round(rx_mbps*1000,1),
            'tx_kbps':round(tx_mbps*1000,1),
            'rx_mb':round(vals['rx']/1024/1024,1),
            'tx_mb':round(vals['tx']/1024/1024,1),
        })
    endpoints = discover_access_endpoints(max_age=60.0)
    return {
        'local_ip':endpoints.get('lan_ip') or local_ip(),
        'tailscale_ip':endpoints.get('tailscale_ip') or '',
        'magic_dns':endpoints.get('magic_dns') or '',
        'public_ip':public_ip(),
        'rx_mbps':round(total_rx,2),
        'tx_mbps':round(total_tx,2),
        'rx_kbps':round(total_rx*1000,1),
        'tx_kbps':round(total_tx*1000,1),
        'interfaces':ifaces,
    }


def cached_disk_stats(max_age=15):
    now = time.time()
    cached = disk_stats_cache
    if cached.get("value") and now - float(cached.get("time", 0) or 0) < max(1.0, float(max_age or 15)):
        return cached.get("value") or []
    value = disk_stats()
    disk_stats_cache["value"] = value
    disk_stats_cache["time"] = now
    return value


def cached_system_info(gpu_rows=None, max_age=30):
    now = time.time()
    cached = system_info_cache
    cached_value = cached.get("value") if isinstance(cached.get("value"), dict) else {}
    gpu_names = ", ".join([g.get("name") for g in (gpu_rows or []) if isinstance(g, dict) and g.get("name")])
    if cached_value and now - float(cached.get("time", 0) or 0) < max(1.0, float(max_age or 30)):
        return {**cached_value, "gpus": gpu_names or cached_value.get("gpus", "unknown")}
    value = system_info(gpu_rows=gpu_rows)
    system_info_cache["value"] = value
    system_info_cache["time"] = now
    return value


def system_stats(gpu_rows=None):
    return {'memory':memory_stats(),'cpu':cpu_stats(),'disks':cached_disk_stats(),'network':network_stats(),'info':cached_system_info(gpu_rows)}

def estimate_tokens_from_stream_bytes(raw):
    text = raw.decode("utf-8", errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
    chars = 0
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
            for choice in obj.get("choices", []):
                delta = choice.get("delta") or {}
                chars += len(delta.get("content") or choice.get("text") or "")
        except Exception:
            pass
    return max(0, int(chars / 4)) if chars else (max(1, len(text)//4) if text else 0)

def build_series_point():
    global latest_gpu_rows, latest_system_snapshot, latest_metrics_collected_at
    gpus = gpu_stats(); sysinfo = system_stats(gpu_rows=gpus)
    util=[]; mem=[]; mem_used=[]; mem_total=[]; temps=[]; watts=[]; gpu_points=[]
    for g in gpus:
        if "error" in g: continue
        util_v=safe_float(g.get("util_pct")); mem_v=safe_float(g.get("mem_pct")); mem_used_v=safe_float(g.get("mem_used_mib")); mem_total_v=safe_float(g.get("mem_total_mib")); temp_v=safe_float(g.get("temp_c")); watt_v=safe_float(g.get("power_w")); fan_v=safe_float(g.get("fan_pct"))
        junction_v=safe_float(g.get("temp_junction_c")); vram_temp_v=safe_float(g.get("temp_vram_c"))
        failed_gpu = bool(g.get("failed") or g.get("frozen"))
        if not failed_gpu:
            util.append(util_v); mem.append(mem_v); mem_used.append(mem_used_v); mem_total.append(mem_total_v); temps.append(temp_v); watts.append(watt_v)
        gpu_points.append({"index":g.get("index"),"util":util_v,"mem_pct":mem_v,"mem_used_gib":round(mem_used_v/1024.0,3) if mem_used_v > 0 else 0,"mem_total_gib":round(mem_total_v/1024.0,3) if mem_total_v > 0 else 0,"temp":temp_v,"temp_junction":junction_v,"temp_junction_c":junction_v,"temp_vram":vram_temp_v,"temp_vram_c":vram_temp_v,"power":watt_v,"fan":fan_v,"failed":failed_gpu,"frozen":bool(g.get("frozen")),"failure_mode":str(g.get("failure_mode") or "")})
    memory_row = sysinfo.get('memory') or {}
    ram_pct=safe_float(memory_row.get('used_pct')); cpu_pct=safe_float((sysinfo.get('cpu') or {}).get('total_pct'))
    ram_used_gib=round(safe_float(memory_row.get('used_mib'))/1024.0, 3) if safe_float(memory_row.get('used_mib')) > 0 else 0
    ram_total_gib=round(safe_float(memory_row.get('total_mib'))/1024.0, 3) if safe_float(memory_row.get('total_mib')) > 0 else 0
    disks=sysinfo.get('disks') or []; disk_pct=max([safe_float(d.get('used_pct')) for d in disks if isinstance(d,dict)] or [0])
    net=sysinfo.get('network') or {}; rx_mbps=safe_float(net.get('rx_mbps')); tx_mbps=safe_float(net.get('tx_mbps'))
    try:
        studio_active = bool(globals().get("image_studio_activity_active", lambda **kwargs: False)(max_age=2.0))
    except Exception:
        studio_active = False
    with metrics_lock:
        benchmark_active = bool(metrics.get("benchmark_active")) or benchmark_job_active_from_state_file() or any(bool((row or {}).get("benchmark_active")) for row in (target_request_metrics or {}).values() if isinstance(row, dict))
        last_path = str(metrics.get("last_path") or "")
        benchmark_metric_sample = benchmark_active or last_path.startswith("benchmark:")
        vram_used_gib=round(sum(mem_used)/1024.0,3) if mem_used else 0
        vram_total_gib=round(sum(mem_total)/1024.0,3) if mem_total else 0
        point={"t":int(time.time()),"gpu_util":round(sum(util)/len(util),1) if util else 0,"mem_pct":round(sum(mem)/len(mem),1) if mem else 0,"mem_used_gib":vram_used_gib,"mem_total_gib":vram_total_gib,"temp_c":round(max(temps),1) if temps else 0,"power_w":round(sum(watts),1) if watts else 0,"ram_pct":round(ram_pct,1),"ram_used_gib":ram_used_gib,"ram_total_gib":ram_total_gib,"cpu_pct":round(cpu_pct,1),"disk_pct":round(disk_pct,1),"system_util_pct":round((cpu_pct+ram_pct+(sum(util)/len(util) if util else 0))/3,1),"net_rx_mbps":round(rx_mbps,2),"net_tx_mbps":round(tx_mbps,2),"net_rx_kbps":round(rx_mbps*1000,1),"net_tx_kbps":round(tx_mbps*1000,1),"gpus":gpu_points,"active_requests":max(int(metrics.get("active_requests",0) or 0), 1 if benchmark_active or studio_active else 0),"latency_s":0 if benchmark_metric_sample else metrics.get("last_latency_s") or 0,"ttft_s":0 if benchmark_metric_sample else metrics.get("last_ttft_s") or 0,"tps":0 if benchmark_metric_sample else metrics.get("last_tokens_per_second") or 0}
        series_points.append(point)
        cutoff = int(time.time() - METRICS_HISTORY_RETENTION_SECONDS)
        while series_points and int(safe_float((series_points[0] or {}).get("t"))) < cutoff:
            series_points.popleft()
        latest_gpu_rows = gpus
        latest_system_snapshot = sysinfo
        latest_metrics_collected_at = time.time()
    update_system_metric_peaks(point)
    persist_metrics_history_if_due()
    return point

def metrics_collector():
    while True:
        try:
            build_series_point()
        except Exception as e:
            log_control(f"metrics collector error: {e}")
        time.sleep(1)


def get_latest_runtime_snapshot(force_refresh=False):
    with metrics_lock:
        gpus = latest_gpu_rows
        system = latest_system_snapshot
        collected_at = latest_metrics_collected_at
    if force_refresh or not collected_at:
        build_series_point()
        with metrics_lock:
            gpus = latest_gpu_rows
            system = latest_system_snapshot
            collected_at = latest_metrics_collected_at
    return gpus, system, collected_at


def build_instance_runtime_metrics_entry(instance, target_metrics_snapshot=None):
    row = dict(instance or {})
    target_metrics_snapshot = target_metrics_snapshot if isinstance(target_metrics_snapshot, dict) else {}
    request_key = str(row.get("id") or "").strip().upper()
    request_metrics = dict(target_metrics_snapshot.get(request_key) or default_target_request_metrics())
    spec = resolve_variant_spec(row.get("mode")) or {}
    runtime_meta = compose_variant_metadata(row.get("mode"))
    log_metrics = runtime_log_metrics_for_container(row.get("container")) if row.get("running") and row.get("container") else {}
    speculative = dict(request_metrics.get("last_speculative") or log_metrics.get("speculative") or {})
    if speculative.get("drafted_tokens") in (None, "") and runtime_meta.get("drafted_tokens") not in (None, ""):
        speculative["drafted_tokens"] = runtime_meta.get("drafted_tokens")
    prompt_tps = request_metrics.get("last_prompt_tps")
    input_tokens = first_defined(request_metrics.get("last_input_tokens"), request_metrics.get("last_total_tokens"))
    generation_tps = first_defined(
        request_metrics.get("last_tokens_per_second"),
        log_metrics.get("generation_tps"),
    )
    if prompt_tps in (None, ""):
        prompt_tps = derive_request_prompt_tps(
            input_tokens,
            request_metrics.get("last_output_tokens"),
            request_metrics.get("last_ttft_s"),
            request_metrics.get("last_latency_s"),
            generation_tps,
            log_metrics.get("prompt_tps"),
        )
    if prompt_tps in (None, ""):
        prompt_tps = log_metrics.get("prompt_tps")
    estimated_prefill_s = None
    try:
        if prompt_tps not in (None, "", 0, 0.0) and input_tokens not in (None, "", 0, 0.0):
            estimated_prefill_s = round(float(input_tokens) / max(float(prompt_tps), 0.001), 3)
    except Exception:
        estimated_prefill_s = None
    return {
        "id": row.get("id"),
        "instance_id": row.get("id"),
        "display_name": row.get("display_name") or row.get("id"),
        "kind": row.get("kind"),
        "mode": row.get("mode"),
        "selector": str(spec.get("selector") or row.get("mode") or ""),
        "model_id": str(spec.get("model_id") or ""),
        "engine": str(spec.get("engine") or ""),
        "engine_display": str(spec.get("engine_display") or spec.get("engine") or ""),
        "served_model_name": str(spec.get("served_model_name") or ""),
        "vision": str(spec.get("vision") or ""),
        "container": row.get("container") or "",
        "port": row.get("port"),
        "running": bool(row.get("running")),
        "booting": bool(row.get("booting")),
        "container_state": row.get("container_state") or "",
        "gpu_indices": list(row.get("gpu_indices") or []),
        "ctx_size_tokens": runtime_meta.get("ctx_size_tokens"),
        "speculative_method": runtime_meta.get("speculative_method"),
        "prompt_tps": prompt_tps,
        "generation_tps": generation_tps,
        "running_requests": first_defined(log_metrics.get("running_requests"), 1 if request_metrics.get("benchmark_active") else None),
        "waiting_requests": first_defined(log_metrics.get("waiting_requests"), log_metrics.get("pending_requests")),
        "pending_requests": log_metrics.get("pending_requests"),
        "swapped_requests": log_metrics.get("swapped_requests"),
        "gpu_kv_cache_usage_pct": request_metrics.get("last_gpu_kv_cache_usage_pct") if request_metrics.get("last_gpu_kv_cache_usage_pct") not in (None, "") else log_metrics.get("gpu_kv_cache_usage_pct"),
        "cpu_kv_cache_usage_pct": request_metrics.get("last_cpu_kv_cache_usage_pct") if request_metrics.get("last_cpu_kv_cache_usage_pct") not in (None, "") else log_metrics.get("cpu_kv_cache_usage_pct"),
        "prefix_cache_hit_rate_pct": request_metrics.get("last_prefix_cache_hit_rate_pct") if request_metrics.get("last_prefix_cache_hit_rate_pct") not in (None, "") else log_metrics.get("prefix_cache_hit_rate_pct"),
        "speculative": speculative,
        "last_status": request_metrics.get("last_status"),
        "last_latency_s": request_metrics.get("last_latency_s"),
        "last_ttft_s": request_metrics.get("last_ttft_s"),
        "last_prefill_s": estimated_prefill_s,
        "last_tokens_per_second": request_metrics.get("last_tokens_per_second"),
        "last_estimated_tokens": request_metrics.get("last_estimated_tokens"),
        "last_input_tokens": request_metrics.get("last_input_tokens"),
        "last_output_tokens": request_metrics.get("last_output_tokens"),
        "last_total_tokens": request_metrics.get("last_total_tokens"),
        "last_tool_calls": request_metrics.get("last_tool_calls"),
        "last_preset": request_metrics.get("last_preset"),
        "last_path": request_metrics.get("last_path"),
        "last_request_at": request_metrics.get("last_request_at"),
        "benchmark_active": bool(request_metrics.get("benchmark_active")),
        "benchmark_mode": request_metrics.get("benchmark_mode") or "",
        "benchmark_step": request_metrics.get("benchmark_step") or "",
        "benchmark_step_index": request_metrics.get("benchmark_step_index") or 0,
        "benchmark_step_count": request_metrics.get("benchmark_step_count") or 0,
        "benchmark_step_progress": request_metrics.get("benchmark_step_progress") or 0.0,
    }


def build_instance_runtime_metrics_snapshot(instances, target_metrics_snapshot=None):
    rows = {}
    for instance in instances or []:
        rows[str(instance.get("id") or "").strip().upper()] = build_instance_runtime_metrics_entry(instance, target_metrics_snapshot)
    return rows


def build_global_runtime_metrics_entry(mode, port, container, metrics_snapshot, gpu_count=None):
    selector = canonical_mode_selector(mode)
    spec = resolve_variant_spec(selector) or {}
    resolved_gpu_count = int(gpu_count if gpu_count is not None else detect_gpu_count_runtime() or 0)
    scope_kind = str(spec.get("scope_kind") or "")
    runtime_gpu_indices = (
        list(range(max(resolved_gpu_count, 0)))
        if scope_kind in {"multi", "global_only"}
        else mode_gpu_indices(selector, gpu_count=resolved_gpu_count)
    )
    log_metrics = runtime_log_metrics_for_container(container) if container else {}
    speculative = dict(metrics_snapshot.get("last_speculative") or log_metrics.get("speculative") or {})
    if speculative.get("drafted_tokens") in (None, "") and spec.get("drafted_tokens") not in (None, ""):
        speculative["drafted_tokens"] = spec.get("drafted_tokens")
    prompt_tps = metrics_snapshot.get("last_prompt_tps")
    input_tokens = first_defined(metrics_snapshot.get("last_input_tokens"), metrics_snapshot.get("last_total_tokens"))
    generation_tps = first_defined(
        metrics_snapshot.get("last_tokens_per_second"),
        log_metrics.get("generation_tps"),
    )
    if prompt_tps in (None, ""):
        prompt_tps = derive_request_prompt_tps(
            input_tokens,
            metrics_snapshot.get("last_output_tokens"),
            metrics_snapshot.get("last_ttft_s"),
            metrics_snapshot.get("last_latency_s"),
            generation_tps,
            log_metrics.get("prompt_tps"),
        )
    if prompt_tps in (None, ""):
        prompt_tps = log_metrics.get("prompt_tps")
    estimated_prefill_s = None
    try:
        if prompt_tps not in (None, "", 0, 0.0) and input_tokens not in (None, "", 0, 0.0):
            estimated_prefill_s = round(float(input_tokens) / max(float(prompt_tps), 0.001), 3)
    except Exception:
        estimated_prefill_s = None
    return {
        "id": "GLOBAL",
        "instance_id": "GLOBAL",
        "display_name": "Global Runtime",
        "kind": "global",
        "mode": selector,
        "selector": str(spec.get("selector") or selector or ""),
        "model_id": str(spec.get("model_id") or ""),
        "engine": str(spec.get("engine") or ""),
        "engine_display": str(spec.get("engine_display") or spec.get("engine") or ""),
        "served_model_name": str(spec.get("served_model_name") or ""),
        "vision": str(spec.get("vision") or ""),
        "container": str(container or ""),
        "port": int(port or 0),
        "running": True,
        "booting": False,
        "container_state": "",
        "gpu_indices": runtime_gpu_indices,
        "ctx_size_tokens": spec.get("ctx_size_tokens"),
        "speculative_method": spec.get("speculative_method"),
        "prompt_tps": prompt_tps,
        "generation_tps": generation_tps,
        "running_requests": first_defined(log_metrics.get("running_requests"), 1 if metrics_snapshot.get("benchmark_active") else None),
        "waiting_requests": first_defined(log_metrics.get("waiting_requests"), log_metrics.get("pending_requests")),
        "pending_requests": log_metrics.get("pending_requests"),
        "swapped_requests": log_metrics.get("swapped_requests"),
        "gpu_kv_cache_usage_pct": metrics_snapshot.get("last_gpu_kv_cache_usage_pct") if metrics_snapshot.get("last_gpu_kv_cache_usage_pct") not in (None, "") else log_metrics.get("gpu_kv_cache_usage_pct"),
        "cpu_kv_cache_usage_pct": metrics_snapshot.get("last_cpu_kv_cache_usage_pct") if metrics_snapshot.get("last_cpu_kv_cache_usage_pct") not in (None, "") else log_metrics.get("cpu_kv_cache_usage_pct"),
        "prefix_cache_hit_rate_pct": metrics_snapshot.get("last_prefix_cache_hit_rate_pct") if metrics_snapshot.get("last_prefix_cache_hit_rate_pct") not in (None, "") else log_metrics.get("prefix_cache_hit_rate_pct"),
        "speculative": speculative,
        "last_status": metrics_snapshot.get("last_status"),
        "last_latency_s": metrics_snapshot.get("last_latency_s"),
        "last_ttft_s": metrics_snapshot.get("last_ttft_s"),
        "last_prefill_s": estimated_prefill_s,
        "last_tokens_per_second": metrics_snapshot.get("last_tokens_per_second"),
        "last_estimated_tokens": metrics_snapshot.get("last_estimated_tokens"),
        "last_input_tokens": metrics_snapshot.get("last_input_tokens"),
        "last_output_tokens": metrics_snapshot.get("last_output_tokens"),
        "last_total_tokens": metrics_snapshot.get("last_total_tokens"),
        "last_tool_calls": metrics_snapshot.get("last_tool_calls"),
        "last_preset": metrics_snapshot.get("last_preset"),
        "last_path": metrics_snapshot.get("last_path"),
        "last_request_at": metrics_snapshot.get("last_request_at"),
        "benchmark_active": bool(metrics_snapshot.get("benchmark_active")),
        "benchmark_mode": metrics_snapshot.get("benchmark_mode") or "",
        "benchmark_step": metrics_snapshot.get("benchmark_step") or "",
        "benchmark_step_index": metrics_snapshot.get("benchmark_step_index") or 0,
        "benchmark_step_count": metrics_snapshot.get("benchmark_step_count") or 0,
        "benchmark_step_progress": metrics_snapshot.get("benchmark_step_progress") or 0.0,
    }


def build_status_snapshot(refresh_remote_metadata=False):
    with metrics_lock:
        m = dict(metrics)
        recent = list(recent_requests)
        series = metric_series_status_snapshot_unlocked()
    runtime_inventory = enrich_inventory_model_update_state(load_runtime_inventory())
    local_installer_metadata = read_local_installer_metadata()
    self_update_state = read_self_update_state()
    remote_update_metadata = cached_remote_script_metadata(refresh=refresh_remote_metadata)
    upstream_services = discover_upstream_services(force=False, max_age=30.0)
    current_mode = active_mode()
    ap = active_port()
    current_container_name = current_container()
    cfg = read_server_config()
    gpu_count = detect_gpu_count_runtime()
    instances = instances_snapshot()
    target_metrics_snapshot = snapshot_target_request_metrics()
    instance_runtime_metrics = build_instance_runtime_metrics_snapshot(instances, target_metrics_snapshot=target_metrics_snapshot)
    runtime_rows = running_runtime_rows(instances)
    scope_kind = str((resolve_variant_spec(current_mode) or {}).get("scope_kind") or "")
    if not runtime_rows and current_container_name and scope_kind in {"multi", "global_only"}:
        global_boot = runtime_boot_state(current_container_name, ready_url_for_mode(current_mode))
        if global_boot.get("running") or global_boot.get("booting"):
            instance_runtime_metrics["GLOBAL"] = build_global_runtime_metrics_entry(
                current_mode,
                ap,
                current_container_name,
                m,
                gpu_count=gpu_count,
            )
            instance_runtime_metrics["GLOBAL"]["running"] = bool(global_boot.get("running"))
            instance_runtime_metrics["GLOBAL"]["booting"] = bool(global_boot.get("booting"))
            instance_runtime_metrics["GLOBAL"]["container_state"] = global_boot.get("status") or ""
            runtime_rows = [{
                "id": "GLOBAL",
                "kind": "global",
                "gpu_indices": list(range(max(gpu_count, 0))),
                "mode": current_mode,
                "container": current_container_name,
                "port": ap,
                "running": bool(global_boot.get("running")),
                "booting": bool(global_boot.get("booting")),
                "container_state": global_boot.get("status") or "",
            }]
    dual_rows = [dict(row) for row in runtime_rows if row.get("kind") == "dual"]
    dual_rows.sort(key=lambda d: (d.get("gpu_indices") or [], d.get("id") or ""))
    failed_mode = str(read_switch_failure().get("mode") or "")
    active_modes = [mode for mode in runtime_mode_list(runtime_rows, "") if mode and mode != failed_mode]
    containers = runtime_container_list(runtime_rows, "")
    studio_runtime = image_studio_runtime_snapshot()
    with metrics_lock:
        m = dict(metrics)
    studio_queue_depth = int(studio_runtime.get("queue_running") or 0) + int(studio_runtime.get("queue_pending") or 0)
    if studio_queue_depth:
        m["active_requests"] = max(int(m.get("active_requests") or 0), studio_queue_depth)
    reported_active_mode = ""
    if current_mode in active_modes:
        reported_active_mode = current_mode
    elif len(active_modes) == 1:
        reported_active_mode = active_modes[0]
    reported_active_port = 0
    if runtime_rows:
        if reported_active_mode:
            matching_row = next((row for row in runtime_rows if str(row.get("mode") or "") == reported_active_mode), None)
            if matching_row:
                reported_active_port = int(matching_row.get("port") or 0)
        if reported_active_port <= 0 and len(runtime_rows) == 1:
            reported_active_port = int(runtime_rows[0].get("port") or 0)
    elif studio_runtime.get("active"):
        reported_active_mode = str(studio_runtime.get("mode") or "ai-studio")
        active_modes = [reported_active_mode]
        reported_active_port = int(studio_runtime.get("port") or 8188)
        containers = list(studio_runtime.get("running_containers") or [])
    gpus_snapshot, system_snapshot, _ = get_latest_runtime_snapshot()
    supported_club_version = (
        dict(SCRIPT_CLUB3090_COMPAT)
        if isinstance(SCRIPT_CLUB3090_COMPAT, dict) and SCRIPT_CLUB3090_COMPAT
        else (
            remote_update_metadata.get("club_3090_version")
            if isinstance(remote_update_metadata.get("club_3090_version"), dict)
            else {}
        )
    )
    supported_commit = str(supported_club_version.get("commit") or "").strip()
    repo_head = str(runtime_inventory.get("repo_head") or "").strip()
    repo_describe = str(runtime_inventory.get("repo_describe") or "").strip()
    compatible_commit_prefixes = [
        str(item or "").strip()
        for item in (supported_club_version.get("compatible_commit_prefixes") or [])
        if str(item or "").strip()
    ]
    compatible_release_patterns = [
        str(item or "").strip()
        for item in (supported_club_version.get("compatible_release_patterns") or supported_club_version.get("compatible_releases") or [])
        if str(item or "").strip()
    ]
    supported_commit_is_ancestor = bool(supported_commit and repo_head and git_is_ancestor(CLUB3090_DIR, supported_commit, repo_head))
    local_commit_is_ancestor = bool(supported_commit and repo_head and git_is_ancestor(CLUB3090_DIR, repo_head, supported_commit))
    repo_commit_marked_compatible = bool(
        (repo_head and supported_commit and repo_head == supported_commit)
        or any(repo_head.startswith(prefix) for prefix in compatible_commit_prefixes if repo_head)
    )
    repo_release_marked_compatible = bool(
        any(fnmatch.fnmatch(repo_describe, pattern) for pattern in compatible_release_patterns if repo_describe)
    )
    repo_marked_compatible = bool(repo_commit_marked_compatible or repo_release_marked_compatible)
    club3090_compat = {
        "supported": supported_club_version,
        "local_repo_head": repo_head,
        "local_repo_describe": repo_describe,
        "local_repo_marked_compatible": repo_marked_compatible,
        "local_repo_commit_marked_compatible": repo_commit_marked_compatible,
        "local_repo_release_marked_compatible": repo_release_marked_compatible,
        "local_repo_newer_than_supported": bool(not repo_marked_compatible and repo_head and supported_commit and repo_head != supported_commit and supported_commit_is_ancestor),
        "local_repo_older_than_supported": bool(not repo_marked_compatible and repo_head and supported_commit and repo_head != supported_commit and local_commit_is_ancestor),
    }
    return {
        "active_mode": reported_active_mode,
        "active_modes": active_modes,
        "active_port": reported_active_port,
        "container": (containers[0] if containers else ""),
        "containers": containers,
        "ai_studio": studio_runtime,
        "club3090_dir": CLUB3090_DIR,
        "script_version": SCRIPT_VERSION,
        "control_started_at": int(startup_time),
        "local_installer_metadata": local_installer_metadata,
        "self_update": self_update_state,
        "remote_update": remote_update_metadata,
        "club3090_compat": club3090_compat,
        "uptime_seconds": int(time.time() - startup_time),
        "machine_uptime_seconds": machine_uptime_seconds(),
        "vllm_service": service_status("club3090-vllm.service"),
        "control_service": service_status("club3090-control.service"),
        "updater_service": service_status("club3090-updater.service"),
        "caddy_service": service_status("club3090-caddy.service") if cfg.get("https_enabled", False) else "disabled",
        "console_service": service_status("club3090-console-log.service"),
        "metrics": m,
        "recent_requests": recent,
        "gpus": gpus_snapshot,
        "power": power_status(),
        "system": system_snapshot,
        "series": series,
        "system_metric_peaks": system_metric_peaks_snapshot(),
        "ui_config": read_ui_config(),
        "resource_colors": resource_color_config(),
        "preset_tps_stats": preset_tps_stats_snapshot(),
        "presets": preset_catalog(),
        "gpu_count": gpu_count,
        "instances": instances,
        "runtime_inventory": runtime_inventory,
        "model_updates": model_update_state_snapshot(),
        "models": list(runtime_inventory.get("models") or []),
        "variants": list(runtime_inventory.get("variants") or []),
        "nvlink": detect_nvlink_status(),
        "upstream_services": upstream_services,
        "model_install_job": model_install_job_snapshot(),
        "model_install_jobs": model_install_jobs_snapshot(),
        "custom_model_job": custom_model_job_snapshot(),
        "script_job": script_job_snapshot(),
        "benchmarks": benchmarks_status_snapshot(include_scores=True),
        "single_gpu_modes": list(SINGLE_GPU_MODES),
        "dual_gpu_modes": list(DUAL_GPU_MODES),
        "running_dual_mode": (dual_rows[0]["mode"] if dual_rows else None),
        "running_dual_gpu_indices": (dual_rows[0]["gpu_indices"] if dual_rows else []),
        "running_dual_instances": dual_rows,
        "running_runtimes": [instance_runtime_metrics.get(str(row.get("id") or "").strip().upper()) for row in runtime_rows if instance_runtime_metrics.get(str(row.get("id") or "").strip().upper())],
        "instance_runtime_metrics": instance_runtime_metrics,
        "switch_failure": read_switch_failure(),
        "switch_job": switch_job_snapshot(),
        "users": list_users_public(),
        "groups": list_groups_public(),
        "server_config": cfg,
        "local_api": {"enabled": cfg.get("local_api_enabled", False), "port": cfg.get("local_api_port", LOCAL_API_PORT)},
        "admin_port": ADMIN_PORT,
        "proxy_port": PROXY_PORT,
    }


def refresh_status_snapshot(refresh_remote_metadata=False):
    global status_snapshot_cache, status_snapshot_updated_at, status_snapshot_refresh_started_at
    with status_snapshot_refresh_lock:
        status_snapshot_refresh_started_at = time.time()
        try:
            snapshot = build_status_snapshot(refresh_remote_metadata=refresh_remote_metadata)
            with status_snapshot_lock:
                status_snapshot_cache = snapshot
                status_snapshot_updated_at = time.time()
            return snapshot
        finally:
            status_snapshot_refresh_started_at = 0.0


def start_status_snapshot_refresh(refresh_remote_metadata=False):
    if not status_snapshot_refresh_lock.acquire(blocking=False):
        return False
    globals()["status_snapshot_refresh_started_at"] = time.time()

    def worker():
        global status_snapshot_cache, status_snapshot_updated_at, status_snapshot_refresh_started_at
        try:
            snapshot = build_status_snapshot(refresh_remote_metadata=refresh_remote_metadata)
            with status_snapshot_lock:
                status_snapshot_cache = snapshot
                status_snapshot_updated_at = time.time()
        except Exception as exc:
            log_control(f"background status snapshot refresh error: {exc}")
        finally:
            status_snapshot_refresh_started_at = 0.0
            try:
                status_snapshot_refresh_lock.release()
            except Exception:
                pass

    threading.Thread(
        target=worker,
        name="status-snapshot-refresh",
        daemon=True,
    ).start()
    return True


def build_status_error_snapshot(error, previous=None):
    previous = dict(previous) if isinstance(previous, dict) else {}
    cfg = previous.get("server_config") if isinstance(previous.get("server_config"), dict) else read_server_config()
    ui_cfg = previous.get("ui_config") if isinstance(previous.get("ui_config"), dict) else read_ui_config()
    runtime_inventory = previous.get("runtime_inventory") if isinstance(previous.get("runtime_inventory"), dict) else {"models": [], "variants": []}
    snapshot = {
        "active_mode": str(previous.get("active_mode") or ""),
        "active_modes": list(previous.get("active_modes") or []),
        "active_port": int(previous.get("active_port") or 0),
        "container": str(previous.get("container") or ""),
        "containers": list(previous.get("containers") or []),
        "ai_studio": dict(previous.get("ai_studio") or {}),
        "club3090_dir": CLUB3090_DIR,
        "script_version": SCRIPT_VERSION,
        "control_started_at": int(previous.get("control_started_at") or startup_time),
        "local_installer_metadata": previous.get("local_installer_metadata") if isinstance(previous.get("local_installer_metadata"), dict) else read_local_installer_metadata(),
        "remote_update": previous.get("remote_update") if isinstance(previous.get("remote_update"), dict) else cached_remote_script_metadata(refresh=False),
        "club3090_compat": previous.get("club3090_compat") if isinstance(previous.get("club3090_compat"), dict) else {},
        "uptime_seconds": int(time.time() - startup_time),
        "machine_uptime_seconds": int(previous.get("machine_uptime_seconds") or machine_uptime_seconds()),
        "vllm_service": str(previous.get("vllm_service") or "unknown"),
        "control_service": str(previous.get("control_service") or "unknown"),
        "caddy_service": str(previous.get("caddy_service") or "unknown"),
        "console_service": str(previous.get("console_service") or "unknown"),
        "metrics": dict(previous.get("metrics") or {}),
        "recent_requests": list(previous.get("recent_requests") or []),
        "gpus": list(previous.get("gpus") or []),
        "power": dict(previous.get("power") or {}),
        "system": dict(previous.get("system") or {}),
        "series": list(previous.get("series") or []),
        "system_metric_peaks": previous.get("system_metric_peaks") if isinstance(previous.get("system_metric_peaks"), dict) else system_metric_peaks_snapshot(),
        "ui_config": ui_cfg,
        "preset_tps_stats": previous.get("preset_tps_stats") if isinstance(previous.get("preset_tps_stats"), dict) else preset_tps_stats_snapshot(),
        "presets": previous.get("presets") if isinstance(previous.get("presets"), dict) else preset_catalog(),
        "gpu_count": int(previous.get("gpu_count") or 0),
        "instances": list(previous.get("instances") or []),
        "runtime_inventory": runtime_inventory,
        "models": list(runtime_inventory.get("models") or previous.get("models") or []),
        "variants": list(runtime_inventory.get("variants") or previous.get("variants") or []),
        "nvlink": dict(previous.get("nvlink") or {}),
        "upstream_services": list(previous.get("upstream_services") or []),
        "model_install_job": previous.get("model_install_job") if isinstance(previous.get("model_install_job"), dict) else model_install_job_snapshot(),
        "model_install_jobs": list(previous.get("model_install_jobs") or model_install_jobs_snapshot()),
        "custom_model_job": previous.get("custom_model_job") if isinstance(previous.get("custom_model_job"), dict) else custom_model_job_snapshot(),
        "script_job": previous.get("script_job") if isinstance(previous.get("script_job"), dict) else script_job_snapshot(),
        "benchmarks": ensure_benchmark_scores_for_status(previous.get("benchmarks")) if isinstance(previous.get("benchmarks"), dict) else benchmarks_status_snapshot(include_scores=True),
        "single_gpu_modes": list(previous.get("single_gpu_modes") or SINGLE_GPU_MODES),
        "dual_gpu_modes": list(previous.get("dual_gpu_modes") or DUAL_GPU_MODES),
        "running_dual_mode": previous.get("running_dual_mode"),
        "running_dual_gpu_indices": list(previous.get("running_dual_gpu_indices") or []),
        "running_dual_instances": list(previous.get("running_dual_instances") or []),
        "running_runtimes": list(previous.get("running_runtimes") or []),
        "instance_runtime_metrics": dict(previous.get("instance_runtime_metrics") or {}),
        "switch_failure": previous.get("switch_failure") if isinstance(previous.get("switch_failure"), dict) else read_switch_failure(),
        "switch_job": previous.get("switch_job") if isinstance(previous.get("switch_job"), dict) else switch_job_snapshot(),
        "users": list(previous.get("users") or []),
        "groups": list(previous.get("groups") or []),
        "server_config": cfg,
        "local_api": previous.get("local_api") if isinstance(previous.get("local_api"), dict) else {"enabled": cfg.get("local_api_enabled", False), "port": cfg.get("local_api_port", LOCAL_API_PORT)},
        "admin_port": int(previous.get("admin_port") or ADMIN_PORT),
        "proxy_port": int(previous.get("proxy_port") or PROXY_PORT),
        "status_error": str(error or "").strip()[-1200:],
        "status_error_at": int(time.time()),
    }
    return snapshot


def build_status_lightweight_snapshot(previous=None, reason="", series_limit=None):
    global status_lightweight_cache, status_lightweight_updated_at
    series_limit = normalize_status_series_limit(series_limit)
    previous = dict(previous) if isinstance(previous, dict) else {}
    snapshot = dict(previous)
    acquired = False
    try:
        acquired = metrics_lock.acquire(timeout=1.0)
    except TypeError:
        acquired = metrics_lock.acquire(False)
    if acquired:
        try:
            snapshot["metrics"] = dict(metrics)
            snapshot["recent_requests"] = list(recent_requests)
            snapshot["series"] = metric_series_status_snapshot_unlocked(max_points=series_limit)
            snapshot["gpus"] = list(latest_gpu_rows or snapshot.get("gpus") or [])
            snapshot["system"] = dict(latest_system_snapshot or snapshot.get("system") or {})
            status_lightweight_cache = dict(snapshot)
            status_lightweight_updated_at = time.time()
        finally:
            try:
                metrics_lock.release()
            except Exception:
                pass
    snapshot.setdefault("active_mode", str(previous.get("active_mode") or ""))
    snapshot.setdefault("active_modes", list(previous.get("active_modes") or []))
    snapshot.setdefault("active_port", int(previous.get("active_port") or 0))
    snapshot.setdefault("container", str(previous.get("container") or ""))
    snapshot.setdefault("containers", list(previous.get("containers") or []))
    snapshot.setdefault("ai_studio", dict(previous.get("ai_studio") or {}))
    snapshot.setdefault("club3090_dir", CLUB3090_DIR)
    snapshot["script_version"] = SCRIPT_VERSION
    snapshot["control_started_at"] = int(startup_time)
    snapshot["uptime_seconds"] = int(time.time() - startup_time)
    snapshot["machine_uptime_seconds"] = machine_uptime_seconds()
    snapshot["system_metric_peaks"] = system_metric_peaks_snapshot()
    snapshot.setdefault("local_installer_metadata", previous.get("local_installer_metadata") if isinstance(previous.get("local_installer_metadata"), dict) else {})
    snapshot.setdefault("remote_update", previous.get("remote_update") if isinstance(previous.get("remote_update"), dict) else {})
    snapshot.setdefault("club3090_compat", previous.get("club3090_compat") if isinstance(previous.get("club3090_compat"), dict) else {})
    snapshot.setdefault("vllm_service", str(previous.get("vllm_service") or "unknown"))
    snapshot.setdefault("control_service", str(previous.get("control_service") or "unknown"))
    snapshot.setdefault("updater_service", str(previous.get("updater_service") or "unknown"))
    snapshot.setdefault("caddy_service", str(previous.get("caddy_service") or "unknown"))
    snapshot.setdefault("console_service", str(previous.get("console_service") or "unknown"))
    snapshot.setdefault("power", previous.get("power") if isinstance(previous.get("power"), dict) else {})
    snapshot.setdefault("ui_config", previous.get("ui_config") if isinstance(previous.get("ui_config"), dict) else {})
    snapshot.setdefault("resource_colors", previous.get("resource_colors") if isinstance(previous.get("resource_colors"), dict) else {})
    snapshot.setdefault("preset_tps_stats", previous.get("preset_tps_stats") if isinstance(previous.get("preset_tps_stats"), dict) else {})
    snapshot.setdefault("presets", previous.get("presets") if isinstance(previous.get("presets"), dict) else {})
    snapshot.setdefault("gpu_count", int(previous.get("gpu_count") or len(snapshot.get("gpus") or []) or 0))
    snapshot.setdefault("instances", list(previous.get("instances") or []))
    snapshot.setdefault("runtime_inventory", previous.get("runtime_inventory") if isinstance(previous.get("runtime_inventory"), dict) else {"models": [], "variants": []})
    snapshot.setdefault("models", list((snapshot.get("runtime_inventory") or {}).get("models") or previous.get("models") or []))
    snapshot.setdefault("variants", list((snapshot.get("runtime_inventory") or {}).get("variants") or previous.get("variants") or []))
    snapshot.setdefault("nvlink", previous.get("nvlink") if isinstance(previous.get("nvlink"), dict) else {})
    snapshot.setdefault("upstream_services", list(previous.get("upstream_services") or []))
    snapshot.setdefault("model_install_job", previous.get("model_install_job") if isinstance(previous.get("model_install_job"), dict) else {})
    snapshot.setdefault("model_install_jobs", list(previous.get("model_install_jobs") or []))
    snapshot.setdefault("custom_model_job", previous.get("custom_model_job") if isinstance(previous.get("custom_model_job"), dict) else {})
    snapshot.setdefault("script_job", previous.get("script_job") if isinstance(previous.get("script_job"), dict) else {})
    snapshot.setdefault("benchmarks", previous.get("benchmarks") if isinstance(previous.get("benchmarks"), dict) else {})
    snapshot["benchmarks"] = ensure_benchmark_scores_for_status(snapshot.get("benchmarks"))
    snapshot.setdefault("single_gpu_modes", list(previous.get("single_gpu_modes") or SINGLE_GPU_MODES))
    snapshot.setdefault("dual_gpu_modes", list(previous.get("dual_gpu_modes") or DUAL_GPU_MODES))
    snapshot.setdefault("running_dual_mode", previous.get("running_dual_mode"))
    snapshot.setdefault("running_dual_gpu_indices", list(previous.get("running_dual_gpu_indices") or []))
    snapshot.setdefault("running_dual_instances", list(previous.get("running_dual_instances") or []))
    snapshot.setdefault("running_runtimes", list(previous.get("running_runtimes") or []))
    snapshot.setdefault("instance_runtime_metrics", dict(previous.get("instance_runtime_metrics") or {}))
    snapshot.setdefault("switch_failure", previous.get("switch_failure") if isinstance(previous.get("switch_failure"), dict) else {})
    snapshot.setdefault("switch_job", previous.get("switch_job") if isinstance(previous.get("switch_job"), dict) else {})
    snapshot.setdefault("users", list(previous.get("users") or []))
    snapshot.setdefault("groups", list(previous.get("groups") or []))
    snapshot.setdefault("server_config", previous.get("server_config") if isinstance(previous.get("server_config"), dict) else {})
    snapshot.setdefault("local_api", previous.get("local_api") if isinstance(previous.get("local_api"), dict) else {"enabled": False, "port": LOCAL_API_PORT})
    snapshot.setdefault("admin_port", ADMIN_PORT)
    snapshot.setdefault("proxy_port", PROXY_PORT)
    if reason:
        snapshot["status_error"] = str(reason or "").strip()[-1200:]
        snapshot["status_error_at"] = int(time.time())
    else:
        snapshot.pop("status_error", None)
        snapshot.pop("status_error_at", None)
    status_lightweight_cache = dict(snapshot)
    status_lightweight_updated_at = time.time()
    return snapshot


def build_status_stale_overlay_snapshot(previous=None, reason="", series_limit=None):
    return build_status_lightweight_snapshot(previous, reason or "status snapshot refresh is stale", series_limit=series_limit)


def get_lightweight_status_snapshot(series_limit=None):
    with status_snapshot_lock:
        previous_lightweight = dict(status_lightweight_cache or {})
    with status_snapshot_lock:
        snapshot = dict(status_snapshot_cache or {})
    if previous_lightweight:
        snapshot.update(previous_lightweight)
    return build_status_lightweight_snapshot(snapshot, series_limit=series_limit)


def get_status_snapshot(force=False, refresh_remote_metadata=False):
    global status_snapshot_cache, status_snapshot_updated_at, status_snapshot_refresh_started_at
    with status_snapshot_lock:
        snapshot = status_snapshot_cache
        updated_at = status_snapshot_updated_at
    try:
        if not snapshot or not updated_at:
            started = start_status_snapshot_refresh(refresh_remote_metadata=refresh_remote_metadata)
            if started:
                log_control("status snapshot cold cache; started background refresh and serving lightweight overlay")
            else:
                started_at = float(globals().get("status_snapshot_refresh_started_at") or 0.0)
                busy_for = max(0.0, time.time() - started_at) if started_at else 0.0
                log_control(f"status snapshot cold cache; refresh already running for {round(busy_for, 1)}s; serving lightweight overlay")
            return build_status_stale_overlay_snapshot({}, "status snapshot is warming up")
        if force and snapshot and updated_at:
            now = time.time()
            age = max(0.0, now - float(updated_at or 0.0))
            if age >= 10.0:
                started = start_status_snapshot_refresh(refresh_remote_metadata=refresh_remote_metadata)
                if not started:
                    started_at = float(globals().get("status_snapshot_refresh_started_at") or 0.0)
                    busy_for = max(0.0, now - started_at) if started_at else age
                    log_control(f"status snapshot stale age={round(age, 1)}s refresh_busy_for={round(busy_for, 1)}s; serving lightweight overlay")
                return build_status_stale_overlay_snapshot(snapshot, f"status snapshot refresh is stale ({round(age, 1)}s old)")
            start_status_snapshot_refresh(refresh_remote_metadata=refresh_remote_metadata)
            return snapshot
        return snapshot
    except Exception as e:
        log_control(f"status snapshot fallback: {e}")
        return build_status_error_snapshot(e, snapshot)


def parse_status_request_options(params):
    params = params if isinstance(params, dict) else {}
    tab = str(params.get("tab") or "").strip().lower()
    inventory_detail = str(params.get("inventory_detail") or "").strip().lower()
    if inventory_detail not in {"full", "compact"}:
        inventory_detail = "compact"
    series_limit = normalize_status_series_limit(params.get("series_limit"))
    return {
        "tab": tab,
        "include_series": str(params.get("include_series") or "").strip().lower() in {"1", "true", "yes", "on"},
        "series_limit": series_limit,
        "include_inventory": str(params.get("include_inventory") or "").strip().lower() in {"1", "true", "yes", "on"},
        "inventory_detail": inventory_detail,
        "include_config": str(params.get("include_config") or "").strip().lower() in {"1", "true", "yes", "on"},
        "include_remote_update": str(params.get("include_remote_update") or "").strip().lower() in {"1", "true", "yes", "on"},
        "include_benchmark_details": str(params.get("include_benchmark_details") or "").strip().lower() in {"1", "true", "yes", "on"},
    }


STATUS_COMPACT_VARIANT_DROP_FIELDS = {
    "compose_abs_path",
    "compose_dir_abs_path",
    "compose_project_dir_abs_path",
    "default_engine_switches",
    "derived_compose_path",
    "launch_settings",
    "resource_paths",
    "status_raw",
}

STATUS_COMPACT_PROFILE_LIKE_DROP_FIELDS = {
    "default_engine_switches",
}


def compact_runtime_inventory_for_status(inventory):
    if not isinstance(inventory, dict):
        return inventory
    compact = dict(inventory)
    compact["inventory_detail"] = "compact"
    compact["variants"] = [
        {
            key: value
            for key, value in dict(row).items()
            if key not in STATUS_COMPACT_VARIANT_DROP_FIELDS
        }
        for row in (inventory.get("variants") or [])
        if isinstance(row, dict)
    ]
    compact["profile_likes"] = [
        {
            key: value
            for key, value in dict(row).items()
            if key not in STATUS_COMPACT_PROFILE_LIKE_DROP_FIELDS
        }
        for row in (inventory.get("profile_likes") or [])
        if isinstance(row, dict)
    ]
    return compact


def compact_benchmark_job_for_status(job):
    if not isinstance(job, dict):
        return job
    keep = {
        "active",
        "cancel_requested",
        "current_index",
        "current_selector",
        "finished_at",
        "job_id",
        "mode",
        "overall_progress",
        "progress",
        "running_indices",
        "started_at",
        "status",
        "step_id",
        "step_label",
        "summary",
    }
    row_keep = {
        "assigned_gpu_indices",
        "assigned_instance_id",
        "display_name",
        "error",
        "finished_at",
        "mode",
        "run_id",
        "score",
        "score_icon",
        "score_tier",
        "selector",
        "skip_reason",
        "started_at",
        "status",
        "step_count",
        "step_id",
        "step_index",
        "step_label",
        "step_progress",
        "step_started_at",
    }
    compact = {key: value for key, value in job.items() if key in keep}
    if isinstance(job.get("queue"), list):
        compact["queue"] = [
            {key: value for key, value in dict(row).items() if key in row_keep}
            for row in (job.get("queue") or [])
            if isinstance(row, dict)
        ]
    return compact


def compact_benchmarks_for_status(benchmarks):
    if not isinstance(benchmarks, dict):
        return benchmarks
    compact = dict(benchmarks)
    compact["job"] = compact_benchmark_job_for_status(compact.get("job"))
    compact.pop("current_log", None)
    compact.pop("running_logs", None)
    return compact


def ensure_benchmark_scores_for_status(benchmarks):
    base = dict(benchmarks or {}) if isinstance(benchmarks, dict) else {}
    scores = base.get("scores")
    if isinstance(scores, dict) and scores:
        return base
    try:
        return benchmarks_status_snapshot(base, include_scores=True)
    except Exception as exc:
        log_control(f"benchmark status score summary refresh failed: {exc}")
        base.setdefault("scores", {})
        return base


def shape_status_snapshot(snapshot, options=None):
    options = options if isinstance(options, dict) else {}
    shaped = dict(snapshot or {})
    if benchmark_job_active_from_state_file():
        shaped["benchmarks"] = benchmarks_live_status_overlay(
            shaped.get("benchmarks"),
            include_logs=False,
        )
    shaped["benchmarks"] = ensure_benchmark_scores_for_status(shaped.get("benchmarks"))
    if not options.get("include_series"):
        shaped.pop("series", None)
    elif isinstance(shaped.get("series"), list) and len(shaped.get("series") or []) > normalize_status_series_limit(options.get("series_limit")):
        series = shaped.get("series") or []
        series_limit = normalize_status_series_limit(options.get("series_limit"))
        step = max(1, int(math.ceil(len(series) / max(1, series_limit))))
        shaped["series"] = ([point for index, point in enumerate(series) if index % step == 0] + series[-1:])[-series_limit:]
    if not options.get("include_inventory"):
        shaped.pop("runtime_inventory", None)
        shaped.pop("models", None)
        shaped.pop("variants", None)
    else:
        if isinstance(shaped.get("runtime_inventory"), dict):
            try:
                shaped["runtime_inventory"] = enrich_runtime_inventory_cache_sizes(shaped.get("runtime_inventory"))
            except Exception as exc:
                log_control(f"runtime inventory resource enrichment failed: {exc}")
        if options.get("inventory_detail") != "full":
            shaped["runtime_inventory"] = compact_runtime_inventory_for_status(shaped.get("runtime_inventory"))
        elif isinstance(shaped.get("runtime_inventory"), dict):
            shaped["runtime_inventory"] = dict(shaped.get("runtime_inventory") or {})
            shaped["runtime_inventory"]["inventory_detail"] = "full"
        shaped.pop("models", None)
        shaped.pop("variants", None)
    if not options.get("include_benchmark_details"):
        shaped["benchmarks"] = compact_benchmarks_for_status(shaped.get("benchmarks"))
    if not options.get("include_config"):
        shaped.pop("server_config", None)
    if not options.get("include_remote_update"):
        shaped.pop("remote_update", None)
    shaped.pop("recent_requests", None)
    return shaped


def is_tailscale_client_ip(value):
    try:
        ip_obj = ipaddress.ip_address(str(value or "").strip())
    except Exception:
        return False
    return ip_obj.version == 4 and ip_obj in ipaddress.ip_network("100.64.0.0/10")


def discover_access_endpoints(max_age=60.0):
    now = time.time()
    cached = dict(tailscale_access_hint_cache.get("value") or {})
    cached_time = float(tailscale_access_hint_cache.get("time") or 0.0)
    if cached and cached_time and now - cached_time < max(10.0, float(max_age or 60.0)):
        return cached
    result = {"lan_ip": "", "tailscale_ip": "", "magic_dns": ""}
    try:
        output = subprocess.check_output(
            ["ip", "-brief", "addr"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        for raw_line in str(output or "").splitlines():
            parts = raw_line.split()
            if len(parts) < 3:
                continue
            iface = str(parts[0] or "").strip()
            addresses = [part for part in parts[2:] if "/" in part]
            ipv4_values = [part.split("/", 1)[0] for part in addresses if re.match(r"^\d+\.\d+\.\d+\.\d+/\d+$", part)]
            if iface == "tailscale0" and not result["tailscale_ip"] and ipv4_values:
                result["tailscale_ip"] = ipv4_values[0]
            if iface not in {"lo", "tailscale0"} and not result["lan_ip"] and ipv4_values:
                result["lan_ip"] = ipv4_values[0]
    except Exception:
        pass
    try:
        output = subprocess.check_output(
            ["tailscale", "status", "--json"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=4,
        )
        payload = json.loads(str(output or "") or "{}")
        dns_name = str(((payload.get("Self") or {}).get("DNSName")) or "").strip().rstrip(".")
        if dns_name:
            result["magic_dns"] = dns_name
    except Exception:
        pass
    tailscale_access_hint_cache["value"] = dict(result)
    tailscale_access_hint_cache["time"] = now
    return result


def tailscale_access_hint_for_client(client_ip):
    client_text = str(client_ip or "").strip()
    if not is_tailscale_client_ip(client_text):
        return {}
    cached = dict(tailscale_access_hint_cache.get("hint") or {})
    cached_time = float(tailscale_access_hint_cache.get("hint_time") or 0.0)
    if cached.get("client_ip") == client_text and cached_time and (time.time() - cached_time) < 15.0:
        return cached
    try:
        output = subprocess.check_output(
            ["tailscale", "status"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=4,
        )
    except Exception:
        return {}
    matched_line = ""
    for raw_line in str(output or "").splitlines():
        line = str(raw_line or "").strip()
        if not line or client_text not in line:
            continue
        matched_line = line
        break
    if not matched_line or 'relay "' not in matched_line.lower():
        return {}
    relay_match = re.search(r'relay\s+"([^"]+)"', matched_line, flags=re.I)
    relay_name = relay_match.group(1) if relay_match else "DERP"
    endpoints = discover_access_endpoints()
    links = []
    if endpoints.get("lan_ip"):
        links.append(f"https://{endpoints['lan_ip']}:{ADMIN_PORT}/admin")
    if endpoints.get("tailscale_ip"):
        links.append(f"https://{endpoints['tailscale_ip']}:{ADMIN_PORT}/admin")
    message = (
        f"Tailscale relay path detected for this admin session ({relay_name}). "
        f"For lower bandwidth and latency, prefer direct access when possible"
    )
    if links:
        message += f": {', '.join(links)}"
    message += "."
    hint = {
        "transport": "tailscale",
        "client_ip": client_text,
        "relay": relay_name,
        "message": message,
        "direct_urls": links,
    }
    tailscale_access_hint_cache["hint"] = dict(hint)
    tailscale_access_hint_cache["hint_time"] = time.time()
    return hint


def _tail_text_lines(path, max_lines=4000):
    try:
        max_lines = max(1, int(max_lines or 4000))
    except Exception:
        max_lines = 4000
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return "".join(f.readlines()[-max_lines:])
    except Exception:
        return ""


def query_text_log_file(path, tail_lines=300, match_text="", case_sensitive=False):
    raw_text = _tail_text_lines(path, max_lines=tail_lines)
    if not raw_text:
        return ""
    lines = raw_text.splitlines()
    needle = str(match_text or "")
    if not needle:
        return raw_text
    if case_sensitive:
        filtered = [line for line in lines if needle in line]
    else:
        lowered = needle.lower()
        filtered = [line for line in lines if lowered in line.lower()]
    if not filtered:
        return ""
    return "\n".join(filtered) + "\n"


def parse_cli_log_query(argv):
    tail_lines = 300
    match_text = ""
    case_sensitive = False
    args = list(argv or [])
    index = 0
    while index < len(args):
        token = str(args[index] or "").strip()
        if token == "--tail" and index + 1 < len(args):
            try:
                tail_lines = max(1, int(args[index + 1]))
            except Exception:
                tail_lines = 300
            index += 2
            continue
        if token == "--match" and index + 1 < len(args):
            match_text = str(args[index + 1] or "")
            index += 2
            continue
        if token == "--case-sensitive":
            case_sensitive = True
            index += 1
            continue
        index += 1
    return {
        "tail_lines": tail_lines,
        "match_text": match_text,
        "case_sensitive": case_sensitive,
    }


def emit_cli_log_query(path, argv):
    query = parse_cli_log_query(argv)
    text = query_text_log_file(
        path,
        tail_lines=query["tail_lines"],
        match_text=query["match_text"],
        case_sensitive=query["case_sensitive"],
    )
    sys.stdout.write(text or "")


def docker_log_path(container_name):
    name = str(container_name or "").strip()
    if not name:
        return ""
    try:
        payload = subprocess.check_output(
            ["docker", "inspect", "--format", "{{.LogPath}}", name],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except Exception:
        return ""
    return payload if payload.endswith(".log") else ""


def managed_container_names_for_logrotate():
    names = set(vllm_container_names(all_containers=True, force=True, timeout=5))
    try:
        for row in discover_upstream_services(force=True, max_age=0.0):
            container_name = str(row.get("container_name") or "").strip()
            if container_name:
                names.add(container_name)
    except Exception:
        pass
    current = str(current_container() or "").strip()
    if current:
        names.add(current)
    return sorted(name for name in names if name)


def managed_docker_log_paths():
    paths = []
    seen = set()
    for name in managed_container_names_for_logrotate():
        path = docker_log_path(name)
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def render_docker_logrotate_config(paths):
    unique_paths = [str(path).strip() for path in (paths or []) if str(path).strip()]
    if not unique_paths:
        return "# club-3090 docker logrotate config\n# no managed docker json logs detected\n"
    quoted_paths = " ".join(f'"{path}"' for path in unique_paths)
    rotate_days = max(1, int(DOCKER_LOG_RETENTION_DAYS or 7))
    return (
        "# club-3090 docker logrotate config\n"
        f"{quoted_paths} {{\n"
        "  daily\n"
        f"  rotate {rotate_days}\n"
        "  missingok\n"
        "  notifempty\n"
        "  compress\n"
        "  delaycompress\n"
        "  copytruncate\n"
        "}\n"
    )


def refresh_docker_logrotate_config():
    try:
        config_text = render_docker_logrotate_config(managed_docker_log_paths())
        changed = write_text_atomic_if_changed(DOCKER_LOGROTATE_FILE, config_text)
        if changed:
            log_control(f"docker logrotate config refreshed at {DOCKER_LOGROTATE_FILE}")
        return True
    except Exception as e:
        log_control(f"docker logrotate refresh error: {e}")
        return False


def docker_logrotate_refresher():
    while True:
        try:
            refresh_docker_logrotate_config()
        except Exception as e:
            log_control(f"docker logrotate refresher error: {e}")
        time.sleep(max(300, int(DOCKER_LOGROTATE_REFRESH_SECONDS or 21600)))


def _upload_multipart_text(url, text, filename="club3090-log.txt", field_name="file", extra_fields=None):
    payload = str(text or "")
    if not payload.strip():
        raise ValueError("No log text available to export")
    body_bytes = payload.encode("utf-8", errors="replace")
    boundary = "----club3090" + secrets.token_hex(12)
    parts = []

    def add_field(name, value):
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        parts.append(str(value).encode("utf-8"))
        parts.append(b"\r\n")

    def add_file(name, upload_name, data, content_type="text/plain; charset=utf-8"):
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{upload_name}"\r\n'.encode("utf-8")
        )
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        parts.append(data)
        parts.append(b"\r\n")

    for key, value in (extra_fields or {}).items():
        add_field(key, value)
    add_file(field_name, filename, body_bytes)
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    request = urllib.request.Request(
        url,
        data=b"".join(parts),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "text/plain, application/json",
            "User-Agent": script_user_agent(),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8", errors="replace").strip()
    if not body:
        raise RuntimeError("Empty upload response")
    if body.startswith("{"):
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            for key in ("url", "link"):
                candidate = str(parsed.get(key) or "").strip()
                if re.match(r"^https?://\S+$", candidate):
                    return candidate
    match = re.search(r"https?://[^\s\"'<>]+", body)
    if not match:
        raise RuntimeError(f"Unexpected upload response: {body[:300]}")
    return match.group(0)


def upload_text_to_share_host(text, filename="club3090-log.txt"):
    attempts = []
    providers = [
        {
            "name": "temp.sh",
            "url": "https://temp.sh/upload",
            "field_name": "file",
            "extra_fields": {},
        },
        {
            "name": "1c3.ir",
            "url": "https://1c3.ir",
            "field_name": "file",
            "extra_fields": {},
        },
    ]
    for provider in providers:
        try:
            url = _upload_multipart_text(
                provider["url"],
                text,
                filename=filename,
                field_name=provider.get("field_name") or "file",
                extra_fields=provider.get("extra_fields") or {},
            )
            return {"provider": provider["name"], "url": url}
        except Exception as e:
            attempts.append(f"{provider['name']}: {e}")
    raise RuntimeError("Log upload failed: " + " | ".join(attempts))


def _docker_logs_text(container_name, tail_lines=4000):
    key = str(container_name or "").strip()
    if not key:
        return ""
    try:
        p = subprocess.run(
            ["docker", "logs", "--timestamps", "--tail", str(max(1, int(tail_lines or 4000))), key],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
        )
        return str(p.stdout or "")
    except Exception:
        return ""


def _runtime_log_export_candidates(instance_id=""):
    requested = str(instance_id or "").strip().upper()
    seen = set()
    candidates = []

    def add(instance, container):
        key = str(container or "").strip()
        if not key or key in seen:
            return
        seen.add(key)
        candidates.append((instance, key))

    resolved_instance, resolved_container = resolve_runtime_log_container(requested)
    add(resolved_instance, resolved_container)
    primary = primary_instance()
    if primary and instance_running(primary):
        add(instance_snapshot(primary), instance_runtime_container_name(primary))
    for row in running_dual_instance_snapshots():
        add(row, row.get("container"))
    current = current_container()
    add(None, current)
    for name in vllm_container_names(all_containers=False, force=True, timeout=3):
        add(None, name)
    return candidates


def export_selected_log(source="docker", instance_id="", service_id=""):
    source_name = str(source or "docker").strip().lower()
    if source_name.startswith("service:"):
        service_id = source_name.split(":", 1)[1]
        source_name = "service"
    exported_at = time.strftime("%Y-%m-%d %H:%M:%S")
    if source_name == "control":
        raw_text = _tail_text_lines(CONTROL_LOG_FILE, max_lines=4000)
        if not raw_text.strip():
            raise ValueError("Web UI server log is empty")
        file_name = f"club3090-web-ui-server-{time.strftime('%Y%m%d-%H%M%S')}.log"
        header = (
            "# club-3090 log export\n"
            f"source: web-ui-server\n"
            f"exported_at: {exported_at}\n"
            f"script_version: {SCRIPT_VERSION}\n"
            f"path: {CONTROL_LOG_FILE}\n\n"
        )
        return {
            "source": "control",
            "instance_id": None,
            "container": "",
            "file_name": file_name,
            "text": header + raw_text,
        }
    if source_name == "audit":
        raw_text = _tail_text_lines(AUDIT_LOG_FILE, max_lines=4000)
        if not raw_text.strip():
            raise ValueError("Audit log is empty")
        file_name = f"club3090-audit-{time.strftime('%Y%m%d-%H%M%S')}.log"
        header = (
            "# club-3090 log export\n"
            f"source: audit\n"
            f"exported_at: {exported_at}\n"
            f"script_version: {SCRIPT_VERSION}\n"
            f"path: {AUDIT_LOG_FILE}\n\n"
        )
        return {
            "source": "audit",
            "instance_id": None,
            "container": "",
            "file_name": file_name,
            "text": header + raw_text,
        }
    if source_name == "debug":
        raw_text = _tail_text_lines(DEBUG_LOG_FILE, max_lines=4000)
        if not raw_text.strip():
            raise ValueError("Debug log is empty")
        file_name = f"club3090-debug-{time.strftime('%Y%m%d-%H%M%S')}.log"
        header = (
            "# club-3090 log export\n"
            f"source: debug\n"
            f"exported_at: {exported_at}\n"
            f"script_version: {SCRIPT_VERSION}\n"
            f"path: {DEBUG_LOG_FILE}\n\n"
        )
        return {
            "source": "debug",
            "instance_id": None,
            "container": "",
            "file_name": file_name,
            "text": header + raw_text,
        }
    if source_name == "update":
        raw_text = _tail_text_lines(UPDATE_LOG_FILE, max_lines=4000)
        if not raw_text.strip():
            raise ValueError("Update log is empty")
        file_name = f"club3090-update-{time.strftime('%Y%m%d-%H%M%S')}.log"
        header = (
            "# club-3090 log export\n"
            f"source: update\n"
            f"exported_at: {exported_at}\n"
            f"script_version: {SCRIPT_VERSION}\n"
            f"path: {UPDATE_LOG_FILE}\n\n"
        )
        return {
            "source": "update",
            "instance_id": None,
            "container": "",
            "file_name": file_name,
            "text": header + raw_text,
        }
    selected_instance = None
    container = ""
    raw_text = ""
    label = ""
    if source_name == "service":
        resolved = resolve_log_source("service", "", service_id)
        service = resolved.get("service") or {}
        container = str(resolved.get("container") or "").strip()
        if not container:
            raise ValueError("Selected service log source is unavailable")
        raw_text = _docker_logs_text(container, tail_lines=4000)
        if not raw_text.strip():
            raise ValueError("Selected service log is empty")
        label = str(service.get("id") or service_id or "service").strip().lower()
        file_name = f"club3090-{label}-{time.strftime('%Y%m%d-%H%M%S')}.log"
        header = (
            "# club-3090 log export\n"
            f"source: service\n"
            f"service: {service.get('display_name') or service_id}\n"
            f"container: {container}\n"
            f"exported_at: {exported_at}\n"
            f"script_version: {SCRIPT_VERSION}\n\n"
        )
        return {
            "source": "service",
            "instance_id": None,
            "container": container,
            "service_id": str(service.get("id") or service_id),
            "file_name": file_name,
            "text": header + raw_text,
        }
    for candidate_instance, candidate_container in _runtime_log_export_candidates(instance_id):
        candidate_text = _docker_logs_text(candidate_container, tail_lines=4000)
        if candidate_text.strip():
            selected_instance = candidate_instance
            container = candidate_container
            raw_text = candidate_text
            break
    if not container:
        raise ValueError("No runtime log source selected")
    if not raw_text.strip():
        raise ValueError("Selected runtime log is empty")
    label = (selected_instance.get("id") if selected_instance else (str(instance_id or "").strip().upper() or "primary"))
    file_name = f"club3090-{label.lower()}-{time.strftime('%Y%m%d-%H%M%S')}.log"
    header = (
        "# club-3090 log export\n"
        f"source: docker\n"
        f"instance: {label}\n"
        f"container: {container}\n"
        f"exported_at: {exported_at}\n"
        f"script_version: {SCRIPT_VERSION}\n\n"
    )
    return {
        "source": "docker",
        "instance_id": label,
        "container": container,
        "file_name": file_name,
        "text": header + raw_text,
    }


def export_chat_conversation(conversation_id=""):
    conversation_id = str(conversation_id or "").strip()
    state = read_chat_state()
    conversations = list(state.get("conversations") or [])
    conversation = next((row for row in conversations if str(row.get("id") or "") == conversation_id), None)
    if not conversation:
        raise ValueError("Conversation not found")
    title = str(conversation.get("title") or "Untitled conversation").strip() or "Untitled conversation"
    exported_at = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# {title}",
        "",
        f"- exported_at: {exported_at}",
        f"- script_version: {SCRIPT_VERSION}",
    ]
    folder = str(conversation.get("folder") or "").strip()
    if folder:
        lines.append(f"- folder: {folder}")
    lines.append("")
    for message in list(conversation.get("messages") or []):
        role = str(message.get("role") or "message").strip().lower() or "message"
        heading = {
            "user": "User",
            "assistant": str(message.get("modelLabel") or "Assistant").strip() or "Assistant",
            "system": "System",
        }.get(role, role.title())
        lines.append(f"## {heading}")
        if role == "user" and message.get("inputTokens") not in (None, ""):
            lines.append(f"_input tokens: {int(message.get('inputTokens') or 0)}_")
            lines.append("")
        if role == "assistant":
            meta = []
            if message.get("outputTokens") not in (None, ""):
                meta.append(f"output tokens: {int(message.get('outputTokens') or 0)}")
            if message.get("ttftSeconds") not in (None, ""):
                meta.append(f"ttft: {message.get('ttftSeconds')}s")
            if message.get("tokensPerSecond") not in (None, ""):
                peak = message.get("maxTokensPerSecond")
                tps_text = f"{message.get('tokensPerSecond')} tk/s"
                if peak not in (None, ""):
                    tps_text += f" (↑ {peak})"
                meta.append(tps_text)
            if meta:
                lines.append(f"_{' | '.join(meta)}_")
                lines.append("")
        text = str(message.get("text") or "")
        if text:
            lines.append(text)
            lines.append("")
        attachments = list(message.get("attachments") or [])
        for attachment in attachments:
            if str(attachment.get("kind") or "") == "image":
                url = str(attachment.get("url") or "").strip()
                if url:
                    lines.append(f"![{attachment.get('name') or 'image'}]({url})")
                else:
                    lines.append(f"![{attachment.get('name') or 'image'}](image unavailable)")
            else:
                attachment_name = str(attachment.get("name") or "attachment").strip() or "attachment"
                attachment_text = str(attachment.get("text") or "")
                lines.append(f"### Attachment: {attachment_name}")
                lines.append("")
                lines.append("```text")
                lines.append(attachment_text.rstrip("\n"))
                lines.append("```")
            lines.append("")
    safe_title = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-").lower() or "conversation"
    file_name = f"club3090-chat-{safe_title}-{time.strftime('%Y%m%d-%H%M%S')}.md"
    return {
        "conversation_id": conversation_id,
        "file_name": file_name,
        "text": "\n".join(lines).rstrip() + "\n",
    }


def status_snapshot_collector():
    while True:
        try:
            refresh_status_snapshot()
        except Exception as e:
            log_control(f"status snapshot error: {e}")
        time.sleep(1)

def wake_on_lan(mac=None, broadcast=None):
    mac = (mac or WOL_MAC or "").replace("-", ":").strip()
    broadcast = broadcast or WOL_BROADCAST
    if not mac:
        raise ValueError("No MAC address configured or provided")
    hexmac = mac.replace(":", "")
    if len(hexmac) != 12:
        raise ValueError("Invalid MAC address")
    packet = bytes.fromhex("FF" * 6 + hexmac * 16)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.sendto(packet, (broadcast, 9))
    finally:
        sock.close()
    log_control(f"WOL sent mac={mac} broadcast={broadcast}")
    return {"mac": mac, "broadcast": broadcast}

def apply_performance_profile(name):
    profile_name = _apply_profile_globals(name)
    log_control(f"PROFILE requested name={name}")
    write_server_config({"active_power_profile": profile_name})
    clear_gpu_session_peaks()
    result = {"cpu": apply_cpu_active_power(), "gpu": apply_gpu_active_power(force=True), "profile": profile_name}
    log_control(f"PROFILE applied name={profile_name} cpu={result.get('cpu')} gpu={result.get('gpu')}")
    return result


def restore_persisted_performance_profile(apply_now=False):
    cfg = read_server_config()
    profile_name = str(cfg.get("active_power_profile") or current_profile or "balanced").strip().lower()
    if profile_name not in PERFORMANCE_PROFILES:
        profile_name = "balanced"
    _apply_profile_globals(profile_name)
    if apply_now:
        clear_gpu_session_peaks()
        return {"cpu": apply_cpu_active_power(), "gpu": apply_gpu_active_power(force=True), "profile": profile_name}
    return {"profile": profile_name}


def persist_fan_manual_override_state():
    try:
        write_server_config({
            "fan_manual_override": fan_manual_override,
            "fan_override_instance_id": cooling_scope_instance_id,
        })
    except Exception as exc:
        log_control(f"FAN persist state warning: {exc}")


def restore_persisted_fan_state(apply_now=False):
    global fan_manual_override, fan_curve_pause_until, cooling_scope_instance_id
    cfg = read_server_config()
    fan_manual_override = bool(cfg.get("fan_manual_override", False))
    cooling_scope_instance_id = str(cfg.get("fan_override_instance_id") or "GLOBAL").strip().upper() or "GLOBAL"
    if fan_manual_override:
        fan_curve_pause_until = 0.0
        power_state["fans"] = "manual_max"
        if apply_now:
            return set_gpu_fans(
                speed=FAN_MAX_SPEED,
                auto=False,
                indices=fan_target_gpu_indices(cooling_scope_instance_id),
            )
        return {"fans": "manual_max", "scope": cooling_scope_instance_id}
    power_state["fans"] = "auto"
    fan_curve_pause_until = time.time() + (1 if power_optimizations_enabled else 0)
    return {"fans": "auto", "scope": cooling_scope_instance_id}


runtime_default_power_last = 0.0
ai_studio_power_prep_last = 0.0


def benchmark_power_actions_owned():
    checker = globals().get("benchmark_worker_service_active")
    thread_checker = globals().get("benchmark_worker_thread_active")
    state_reader = globals().get("read_benchmark_state")
    try:
        if callable(checker) and checker():
            return True
    except Exception:
        pass
    try:
        if callable(thread_checker) and thread_checker():
            return True
    except Exception:
        pass
    try:
        if callable(state_reader) and bool((state_reader() or {}).get("active")):
            return True
    except Exception:
        pass
    return False


def ensure_default_runtime_power(reason="runtime_activity", force=False):
    global runtime_default_power_last
    if benchmark_power_actions_owned():
        return {"skipped": True, "profile": current_profile, "reason": "benchmark_active"}
    now = time.time()
    current = str(current_profile or "").strip().lower()
    with metrics_lock:
        gpu_state = str(power_state.get("gpu") or "").strip().lower()
    if current in {"fast", "turbo"}:
        if not force and gpu_state == "active" and now - runtime_default_power_last < 10:
            return {"skipped": True, "profile": current, "reason": reason}
        out = {
            "cpu": apply_cpu_active_power(),
            "gpu": apply_gpu_active_power(skip_fans=True),
            "profile": current,
            "reason": str(reason or ""),
            "preserved": True,
        }
        runtime_default_power_last = now
        log_control(
            f"PROFILE runtime wake reason={reason} profile={current} preserved=true"
        )
        return out
    if not force and current == "balanced" and gpu_state == "active" and now - runtime_default_power_last < 10:
        return {"skipped": True, "profile": "balanced", "reason": reason}
    reset_peaks = force or current != "balanced" or gpu_state != "active"
    _apply_profile_globals("balanced")
    write_server_config({"active_power_profile": "balanced"})
    if reset_peaks:
        clear_gpu_session_peaks()
    out = {
        "cpu": apply_cpu_active_power(),
        "gpu": apply_gpu_active_power(skip_fans=True),
        "profile": "balanced",
        "reason": str(reason or ""),
    }
    runtime_default_power_last = now
    log_control(f"PROFILE runtime wake reason={reason} profile=balanced")
    return out


def ensure_ai_studio_runtime_power(reason="ai_studio_generation", force=False):
    global ai_studio_power_prep_last
    out = ensure_default_runtime_power(reason, force=force)
    if benchmark_power_actions_owned():
        return {**(out if isinstance(out, dict) else {"power": out}), "fans": ["benchmark active; AI Studio fan prep skipped"]}
    now = time.time()
    with metrics_lock:
        fan_state = str(power_state.get("fans") or "").strip().lower()
    if not force and fan_state == "manual_max" and now - ai_studio_power_prep_last < 60:
        return {**(out if isinstance(out, dict) else {"power": out}), "fans": ["manual max fans already active"]}
    fan_results = set_fan_max_toggle(True, instance_id="GLOBAL")
    ai_studio_power_prep_last = now
    log_control(f"PROFILE AI Studio prep reason={reason} fans=manual_max")
    return {**(out if isinstance(out, dict) else {"power": out}), "fans": fan_results}



def nvidia_settings_available():
    return shutil.which("nvidia-settings") is not None


def parse_gpu_temps():
    temps = []
    if not shutil.which("nvidia-smi"):
        return temps
    rc, out = run_cmd(["nvidia-smi", "--query-gpu=index,temperature.gpu", "--format=csv,noheader,nounits"], timeout=6)
    if rc != 0:
        return temps
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            try:
                temps.append((int(parts[0]), int(float(parts[1]))))
            except Exception:
                pass
    return temps


def gpu_indices():
    vals = [idx for idx, _ in parse_gpu_temps()]
    if vals:
        return vals
    if not shutil.which("nvidia-smi"):
        return [0, 1]
    rc, out = run_cmd(["nvidia-smi", "--query-gpu=index", "--format=csv,noheader,nounits"], timeout=6)
    if rc == 0:
        found = []
        for line in out.splitlines():
            try:
                found.append(int(line.strip()))
            except Exception:
                pass
        if found:
            return found
    return [0, 1]


def parse_gpu_fan_speeds():
    speeds = {}
    if not shutil.which("nvidia-smi"):
        return speeds
    rc, out = run_cmd(["nvidia-smi", "--query-gpu=index,fan.speed", "--format=csv,noheader,nounits"], timeout=6)
    if rc != 0:
        return speeds
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            idx = int(parts[0])
        except Exception:
            continue
        raw_speed = parts[1].split()[0]
        if not raw_speed or raw_speed.upper() == "N/A":
            continue
        try:
            speeds[idx] = int(float(raw_speed))
        except Exception:
            continue
    return speeds


def fan_speed_for_temp(temp_c):
    for threshold, speed in FAN_CURVE:
        if temp_c < threshold:
            return max(FAN_MIN_SAFE_SPEED, int(speed))
    return max(FAN_MIN_SAFE_SPEED, 100)


def fan_targets_from_temps_for_indices(indices=None):
    available_indices = gpu_indices()
    if indices is None:
        target_indices = list(available_indices)
    else:
        target_indices = []
        for idx in indices:
            try:
                target_indices.append(int(idx))
            except Exception:
                pass
        target_indices = [idx for idx in target_indices if idx in available_indices]
    if not target_indices:
        return {}
    wanted = set(target_indices)
    temps = [(idx, temp) for idx, temp in parse_gpu_temps() if idx in wanted]
    if not temps:
        return {idx: 70 for idx in target_indices}
    return {idx: fan_speed_for_temp(temp) for idx, temp in temps}


def wait_for_nvidia_display(display=":99", timeout=10, explicit_display=True):
    deadline = time.time() + timeout
    env = os.environ.copy()
    env["DISPLAY"] = display
    env.pop("XAUTHORITY", None)
    last = "display not ready"
    while time.time() < deadline:
        try:
            cmd = ["nvidia-settings"]
            if explicit_display:
                cmd += ["-c", display]
            cmd += ["-q", "gpus"]
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=3, env=env)
            last = (p.stdout or "").strip()
            if p.returncode == 0:
                return True, last
        except Exception as e:
            last = str(e)
        time.sleep(0.5)
    return False, last


def tail_text_file(path, max_lines=40):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:]).strip()
    except Exception:
        return ""


def start_headless_x_direct(display=":99"):
    display_num = str(display).lstrip(":") or "99"
    log_file = "/var/log/club3090-headless-xorg.log"
    config_file = "/etc/X11/club3090-headless-xorg.conf"
    run_cmd(["systemctl", "stop", "club3090-headless-x.service"], timeout=10)
    try:
        subprocess.Popen(
            [
                "/usr/bin/Xorg",
                f":{display_num}",
                "-config", config_file,
                "-noreset",
                "-nolisten", "tcp",
                "-ac",
                "-novtswitch",
                "-sharevts",
                "+extension", "GLX",
                "+extension", "RANDR",
                "+extension", "RENDER",
                "-logfile", log_file,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )
        return True, f"started direct Xorg on :{display_num}"
    except Exception as e:
        return False, str(e)


def ensure_headless_x_running(explicit_display=True):
    # Manual NVIDIA fan control needs an NVIDIA X control display. This service
    # starts a private headless Xorg on :99 with CoolBits enabled and no TCP listener.
    if not nvidia_settings_available():
        return False, "nvidia-settings not found"
    display = os.environ.get("CLUB3090_FAN_DISPLAY", ":99")
    ok, msg = wait_for_nvidia_display(display, timeout=1, explicit_display=explicit_display)
    if ok:
        return True, "headless X already ready"
    if shutil.which("systemctl"):
        rc, out = run_cmd(["systemctl", "start", "club3090-headless-x.service"], timeout=20)
        ok, msg = wait_for_nvidia_display(display, timeout=12, explicit_display=explicit_display)
        if ok:
            return True, "started club3090-headless-x.service"
        direct_ok, direct_msg = start_headless_x_direct(display)
        if direct_ok:
            ok, msg = wait_for_nvidia_display(display, timeout=12, explicit_display=explicit_display)
            if ok:
                return True, "started direct Xorg fallback after systemd path failed"
        xlog = tail_text_file("/var/log/club3090-headless-xorg.log", max_lines=60)
        return False, f"headless X not ready after start rc={rc}: {out[-800:]} / {msg} / direct={direct_msg} / xlog={xlog[-2000:]}"
    return False, "systemctl unavailable; cannot start headless X"


def run_nvidia_settings(args, explicit_display=True):
    if not nvidia_settings_available():
        return 127, "nvidia-settings not found"
    display = os.environ.get("CLUB3090_FAN_DISPLAY", ":99")
    ok, msg = ensure_headless_x_running(explicit_display=explicit_display)
    if not ok:
        return 126, msg
    env = os.environ.copy()
    env["DISPLAY"] = display
    # Xorg is started with -ac by our private service, so no XAUTHORITY is needed.
    env.pop("XAUTHORITY", None)
    try:
        cmd = ["nvidia-settings"]
        if explicit_display:
            cmd += ["-c", display]
        p = subprocess.run(cmd + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15, env=env)
        return p.returncode, (p.stdout or "").strip()
    except Exception as e:
        return 999, str(e)


def discover_nvidia_fan_indices():
    if not nvidia_settings_available():
        return []
    rc, out = run_nvidia_settings(["-q", "fans"])
    if rc != 0:
        return []
    found = []
    for match in re.finditer(r"\[fan:(\d+)\]", out or "", re.IGNORECASE):
        idx = int(match.group(1))
        if idx not in found:
            found.append(idx)
    return found


def fan_indices_for_gpu_targets(target_gpu_indices, available_gpu_indices=None, fan_indices=None):
    fan_list = sorted({int(idx) for idx in (fan_indices or [])})
    if not fan_list:
        return []
    gpu_list = [int(idx) for idx in (available_gpu_indices or gpu_indices())]
    if not gpu_list:
        return fan_list
    target_list = [int(idx) for idx in (target_gpu_indices or []) if int(idx) in gpu_list]
    if not target_list or len(target_list) >= len(gpu_list):
        return fan_list
    chunk = max(1, (len(fan_list) + len(gpu_list) - 1) // len(gpu_list))
    mapping = {}
    cursor = 0
    for pos, gpu_idx in enumerate(gpu_list):
        remaining_gpus = len(gpu_list) - pos
        remaining_fans = len(fan_list) - cursor
        if remaining_fans <= 0:
            mapping[gpu_idx] = []
            continue
        take = remaining_fans if remaining_gpus == 1 else min(chunk, remaining_fans)
        mapping[gpu_idx] = fan_list[cursor:cursor + take]
        cursor += take
    selected = []
    for gpu_idx in target_list:
        selected.extend(mapping.get(gpu_idx, []))
    return selected


def run_nvidia_assignments(assignments):
    results = []
    success = 0
    for assignment in assignments:
        rc, out = run_nvidia_settings(["-a", assignment])
        text = (out or "").strip()
        if rc == 0:
            success += 1
        results.append(f"{assignment}: rc={rc} {text[-500:]}")
    return success, results


def run_nvidia_assignment_batch(assignments):
    if not assignments:
        return 0, []
    args = []
    for assignment in assignments:
        args += ["-a", assignment]
    rc, out = run_nvidia_settings(args)
    text = (out or "").strip()
    return rc, [f"batch rc={rc} assignments={assignments}: {text[-1500:]}"]


def restore_gpu_fans_auto(indices=None):
    available_indices = gpu_indices()
    if indices is None:
        indices = list(available_indices)
    else:
        indices = [int(idx) for idx in indices if int(idx) in available_indices]
    if not indices:
        return ["no GPU targets selected for auto restore"]
    assignments = [f"[gpu:{gpu_idx}]/GPUFanControlState=0" for gpu_idx in indices]
    batch_rc, batch_results = run_nvidia_assignment_batch(assignments)
    if batch_rc == 0:
        return batch_results
    success, retry_results = run_nvidia_assignments(assignments)
    return batch_results + retry_results + [f"auto restore success={success}/{len(assignments)}"]


def verify_manual_fan_target(target_gpu_indices, target_speed, timeout=3.0):
    if target_speed is None:
        return False, {}
    wanted = {int(idx) for idx in (target_gpu_indices or [])}
    if not wanted:
        return False, {}
    deadline = time.time() + float(timeout)
    last = {}
    threshold = max(0, int(target_speed) - 15)
    while time.time() < deadline:
        speeds = parse_gpu_fan_speeds()
        last = {idx: speeds.get(idx) for idx in wanted if idx in speeds}
        if last and all(speed is not None and int(speed) >= threshold for speed in last.values()):
            return True, last
        time.sleep(0.4)
    return False, last


def set_gpu_fans(speed=None, auto=False, indices=None):
    # Canonical scoped fan-control path using the working private headless-X / nvidia-settings flow.
    results = []
    available_indices = gpu_indices()
    if indices is None:
        indices = list(available_indices)
    else:
        clean = []
        for idx in indices:
            try:
                clean.append(int(idx))
            except Exception:
                pass
        indices = [idx for idx in clean if idx in available_indices]
    if not indices:
        return ["no GPU targets selected"]
    fan_objects = discover_nvidia_fan_indices()
    if auto:
        assignments = [f"[gpu:{gpu_idx}]/GPUFanControlState=0" for gpu_idx in indices]
        batch_rc, batch_results = run_nvidia_assignment_batch(assignments)
        results.extend(batch_results)
        success, retry_results = run_nvidia_assignments(assignments) if batch_rc != 0 else (len(assignments), [])
        results.extend(retry_results)
        ok = (batch_rc == 0) or (success == len(assignments))
        with metrics_lock:
            power_state["fans"] = "auto" if ok else "auto_failed"
            power_state["last_action"] = "fans_auto"
            power_state["last_error"] = "" if ok else " | ".join([r for r in results if "rc=0" not in r])[-1000:]
        log_control("FANS auto: " + " || ".join(results))
        return results

    if speed is None:
        targets = fan_targets_from_temps_for_indices(indices)
        # Be deliberately aggressive: use the hottest-card target for all detected
        # fan controllers. This avoids ambiguous fan<->GPU mapping issues on dual
        # 3090 cards and matches the cooling priority.
        target = max(targets.values()) if targets else 70
        mode_label = "manual_curve"
    else:
        targets = {idx: int(speed) for idx in indices}
        target = int(speed)
        mode_label = "manual_max" if target >= FAN_MAX_SPEED else "manual_fixed"

    target = max(FAN_MIN_SAFE_SPEED, min(100, int(target)))
    mapped_fans = fan_indices_for_gpu_targets(indices, available_gpu_indices=available_indices, fan_indices=fan_objects)
    if not mapped_fans:
        guessed_fans = fan_objects or list(range(0, max(2, min(8, len(available_indices) * 2))))
        mapped_fans = fan_indices_for_gpu_targets(indices, available_gpu_indices=available_indices, fan_indices=guessed_fans)
        if not mapped_fans and len(indices) >= len(available_indices):
            mapped_fans = guessed_fans
    enable_assignments = [f"[gpu:{gpu_idx}]/GPUFanControlState=1" for gpu_idx in indices]
    direct_assignments = [f"[gpu:{gpu_idx}]/GPUTargetFanSpeed={target}" for gpu_idx in indices]
    fan_assignments = [f"[fan:{fan_idx}]/GPUTargetFanSpeed={target}" for fan_idx in mapped_fans]
    batch_assignments = list(enable_assignments)
    if direct_assignments:
        batch_assignments.extend(direct_assignments)
    if fan_assignments:
        batch_assignments.extend(fan_assignments)
    batch_rc, batch_results = run_nvidia_assignment_batch(batch_assignments)
    results.extend(batch_results)

    enable_success, enable_results = run_nvidia_assignments(enable_assignments) if batch_rc != 0 else (len(enable_assignments), [])
    results.extend(enable_results)

    direct_success, direct_results = run_nvidia_assignments(direct_assignments) if batch_rc != 0 else (len(direct_assignments), [])
    results.extend(direct_results)

    fan_success = 0
    if fan_assignments and batch_rc != 0:
        fan_success, fan_results = run_nvidia_assignments(fan_assignments)
        results.extend(fan_results)
    elif fan_assignments:
        fan_success = len(fan_assignments)

    verified, observed = verify_manual_fan_target(indices, target)
    results.append(f"fan verify target={target} observed={observed}: rc={0 if verified else 1}")
    ok = (batch_rc == 0 or enable_success == len(enable_assignments)) and (direct_success > 0 or fan_success > 0 or verified)
    if not ok:
        legacy_fan_assignments = [f"[fan:{fan_idx}]/GPUTargetFanSpeed={target}" for fan_idx in range(0, 8)]
        legacy_batch_assignments = list(enable_assignments) + legacy_fan_assignments
        legacy_batch_rc, legacy_batch_results = run_nvidia_assignment_batch(legacy_batch_assignments)
        results.extend(legacy_batch_results)
        legacy_fan_success = 0
        if legacy_batch_rc != 0:
            legacy_fan_success, legacy_fan_results = run_nvidia_assignments(legacy_fan_assignments)
            results.extend(legacy_fan_results)
        else:
            legacy_fan_success = len(legacy_fan_assignments)
        legacy_verified, legacy_observed = verify_manual_fan_target(indices, target, timeout=4.0)
        results.append(f"fan legacy verify target={target} observed={legacy_observed}: rc={0 if legacy_verified else 1}")
        ok = (legacy_batch_rc == 0 or legacy_fan_success > 0 or legacy_verified)
    if not ok:
        failover_results = restore_gpu_fans_auto(indices)
        results.extend([f"manual failover -> {line}" for line in failover_results])
    with metrics_lock:
        power_state["fans"] = mode_label if ok else "manual_failed"
        power_state["last_action"] = "fans_set"
        power_state["last_error"] = "" if ok else " | ".join([r for r in results if "rc=0" not in r])[-1200:]
    log_control("FANS set: " + " || ".join(results))
    return results

def apply_fan_curve_once():
    if benchmark_power_actions_owned():
        return ["benchmark active; fan curve deferred"]
    if fan_manual_override or not power_optimizations_enabled:
        return []
    if time.time() < fan_curve_pause_until:
        return [f"fan curve paused for {int(fan_curve_pause_until-time.time())}s"]
    target_indices = fan_target_gpu_indices(cooling_scope_instance_id)
    if not target_indices:
        return ["no GPU targets selected for fan curve"]
    return set_gpu_fans(speed=None, auto=False, indices=target_indices)

def run_cmd(cmd, timeout=15, cwd=None, env=None):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, cwd=cwd, env=env)
        return p.returncode, (p.stdout or "").strip()
    except Exception as e:
        return 999, str(e)


def set_cpu_governor(governor):
    if not governor:
        return []
    results = []
    if shutil.which("cpupower"):
        rc, out = run_cmd(["cpupower", "frequency-set", "-g", governor], timeout=20)
        results.append(f"cpupower governor {governor}: rc={rc} {out[-500:]}")
        if rc == 0:
            return results
    base = "/sys/devices/system/cpu"
    try:
        for name in os.listdir(base):
            if not name.startswith("cpu") or not name[3:].isdigit():
                continue
            path = os.path.join(base, name, "cpufreq", "scaling_governor")
            if os.path.exists(path):
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(governor)
                except Exception as e:
                    results.append(f"{path}: {e}")
    except Exception as e:
        results.append(str(e))
    return results


def apply_gpu_idle_power(skip_fans=False):
    if benchmark_power_actions_owned():
        return ["benchmark active; gpu idle power deferred"]
    if not power_optimizations_enabled:
        return ["power optimizations disabled"]
    results = []
    if not shutil.which("nvidia-smi"):
        return ["nvidia-smi not found"]
    for cmd in (["nvidia-smi", "-pm", "1"], ["nvidia-smi", "-pl", str(GPU_IDLE_POWER_LIMIT_W)], ["nvidia-smi", "-lgc", GPU_IDLE_LOCK_CLOCKS]):
        rc, out = run_cmd(cmd, timeout=20)
        results.append(f"{' '.join(cmd)}: rc={rc} {out[-500:]}")
    if not skip_fans:
        results += apply_fan_curve_once()
    with metrics_lock:
        power_state["gpu"] = "idle"
        power_state["last_action"] = "gpu_idle"
        power_state["last_error"] = " | ".join([r for r in results if "rc=0" not in r and "disabled" not in r])[-1000:]
    log_control("POWER gpu idle: " + " || ".join(results))
    return results


def apply_gpu_active_power(skip_fans=False, force=False):
    if not power_optimizations_enabled and not force:
        return ["power optimizations disabled"]
    results = []
    if not shutil.which("nvidia-smi"):
        return ["nvidia-smi not found"]
    cmds = [["nvidia-smi", "-pm", "1"], ["nvidia-smi", "-rgc"], ["nvidia-smi", "-pl", str(GPU_ACTIVE_POWER_LIMIT_W)]]
    if GPU_ACTIVE_LOCK_CLOCKS:
        cmds.append(["nvidia-smi", "-lgc", GPU_ACTIVE_LOCK_CLOCKS])
    for cmd in cmds:
        rc, out = run_cmd(cmd, timeout=20)
        results.append(f"{' '.join(cmd)}: rc={rc} {out[-500:]}")
    if not skip_fans:
        results += apply_fan_curve_once()
    with metrics_lock:
        power_state["gpu"] = "active"
        power_state["last_action"] = "gpu_active"
        power_state["last_error"] = " | ".join([r for r in results if "rc=0" not in r and "disabled" not in r])[-1000:]
    log_control("POWER gpu active: " + " || ".join(results))
    return results


def apply_cpu_idle_power():
    if benchmark_power_actions_owned():
        return ["benchmark active; cpu idle power deferred"]
    results = set_cpu_governor(CPU_IDLE_GOVERNOR)
    with metrics_lock:
        power_state["cpu"] = "idle"
        power_state["last_action"] = "cpu_idle"
    log_control("POWER cpu idle: " + " || ".join(results))
    return results


def apply_cpu_active_power():
    results = set_cpu_governor(CPU_ACTIVE_GOVERNOR)
    with metrics_lock:
        power_state["cpu"] = "active"
        power_state["last_action"] = "cpu_active"
    log_control("POWER cpu active: " + " || ".join(results))
    return results


def stop_vllm_container(reason="idle", instance_id=None):
    with switch_lock:
        target = get_instance(instance_id) if instance_id else primary_instance()
        if target is None:
            log_control(f"POWER global stop requested reason={reason}")
            out = cleanup_vllm_containers()
            return 0, str(out or "")[-4000:]
        log_control(f"POWER stop container requested reason={reason} instance={target['id']}")
        rc, out = stop_instance(target["id"])
        with metrics_lock:
            power_state["container"] = "stopped" if rc == 0 else "stop_failed"
            power_state["last_action"] = "container_stop"
            power_state["last_error"] = out if rc != 0 else ""
        log_control(f"POWER stop container rc={rc}: {out}")
        return rc, out


def ensure_vllm_running_for_request(instance_id=None):
    global last_inference_time
    with metrics_lock:
        last_inference_time = time.time()
    ensure_default_runtime_power("proxy_or_local_api_request")
    target = get_instance(instance_id) if instance_id else primary_instance()
    if target is None:
        mode = active_mode()
        port = mode_default_port(mode, 8020)
        if port_open(port, timeout=0.25):
            with metrics_lock:
                power_state["container"] = "running"
            return
        log_control(f"POWER auto-starting global default mode={mode}")
        run_switch(mode)
        with metrics_lock:
            power_state["container"] = "running"
        return
    port = int(target["port"])
    if port_open(port, timeout=0.25):
        with metrics_lock:
            power_state["container"] = "running"
        return
    log_control(f"POWER auto-starting container for request instance={target['id']} mode={target['mode']}")
    start_instance(target["id"])
    with metrics_lock:
        power_state["container"] = "running"


def idle_watchdog():
    idle_power_applied = False
    while True:
        try:
            if benchmark_power_actions_owned():
                idle_power_applied = False
                time.sleep(15)
                continue
            now = time.time()
            studio_active = bool(globals().get("image_studio_activity_active", lambda: False)())
            if studio_active:
                ensure_default_runtime_power("ai_studio_queue")
            with metrics_lock:
                active = metrics.get("active_requests", 0)
                booting = switch_job_active()
                idle_for = 0 if active > 0 or booting or studio_active else max(0.0, now - last_request_finished_at)
            if active == 0 and not booting and not studio_active and idle_for >= POWER_IDLE_AFTER_SECONDS and not idle_power_applied:
                apply_cpu_idle_power()
                apply_gpu_idle_power()
                idle_power_applied = True
            if active > 0 or booting or studio_active or idle_for < POWER_IDLE_AFTER_SECONDS:
                idle_power_applied = False
            if power_optimizations_enabled and not fan_manual_override:
                # Refresh manual fan curve periodically even while idle; Linux/NVIDIA
                # auto fan behavior can leave 3090 fans off until temps are too high.
                apply_fan_curve_once()
        except Exception as e:
            log_control(f"POWER watchdog error: {e}")
        time.sleep(15)


def image_studio_power_watchdog():
    while True:
        try:
            if not benchmark_power_actions_owned():
                checker = globals().get("image_studio_activity_active")
                if callable(checker) and checker(max_age=0):
                    ensure_default_runtime_power("ai_studio_queue")
        except Exception as e:
            log_control(f"POWER AI Studio queue watchdog error: {e}")
        time.sleep(0.1)



def reset_gpu_power_defaults():
    results = []
    if not shutil.which("nvidia-smi"):
        return ["nvidia-smi not found"]
    for cmd in (["nvidia-smi", "-rgc"], ["nvidia-smi", "-pm", "0"]):
        rc, out = run_cmd(cmd, timeout=20)
        results.append(f"{' '.join(cmd)}: rc={rc} {out[-700:]}")
    # Reset fans to automatic too; disabling optimizations should put the system
    # back under default NVIDIA control as much as Linux allows.
    results += set_gpu_fans(auto=True)
    with metrics_lock:
        power_state["gpu"] = "balanced"
        power_state["fans"] = "auto"
        power_state["last_action"] = "power_defaults"
        power_state["last_error"] = " | ".join([r for r in results if "rc=0" not in r])[-1000:]
    log_control("POWER defaults: " + " || ".join(results))
    return results


def cancel_pending_fan_curve_resume():
    global fan_curve_resume_token
    fan_curve_resume_token += 1
    return fan_curve_resume_token


def schedule_fan_curve_resume(indices=None, delay=1.0):
    target_indices = [int(idx) for idx in (indices or [])]
    token = cancel_pending_fan_curve_resume()
    def worker():
        global fan_curve_pause_until
        time.sleep(max(0.0, float(delay or 0.0)))
        if token != fan_curve_resume_token:
            return
        if fan_manual_override or not power_optimizations_enabled:
            return
        fan_curve_pause_until = 0.0
        resume_targets = target_indices or fan_target_gpu_indices(cooling_scope_instance_id)
        if not resume_targets:
            log_control("FANS auto-resume skipped: no GPU targets selected")
            return
        results = set_gpu_fans(speed=None, auto=False, indices=resume_targets)
        log_control("FANS auto-resume: " + " || ".join(results))
    threading.Thread(target=worker, name="club3090-fan-resume", daemon=True).start()


def set_power_optimizations(enabled, instance_id=None):
    global power_optimizations_enabled, fan_curve_pause_until, cooling_scope_instance_id
    if instance_id is not None:
        cooling_scope_instance_id = str(instance_id or "GLOBAL").strip().upper() or "GLOBAL"
    cancel_pending_fan_curve_resume()
    power_optimizations_enabled = bool(enabled)
    with metrics_lock:
        power_state["power_optimizations"] = "enabled" if power_optimizations_enabled else "disabled"
    if power_optimizations_enabled:
        fan_curve_pause_until = 0.0
        return {"cpu": apply_cpu_active_power(), "gpu": apply_gpu_active_power(skip_fans=True), "fans": apply_fan_curve_once()}
    fan_curve_pause_until = time.time() + 10**9
    return {"cpu": set_cpu_governor("performance"), "gpu": reset_gpu_power_defaults()}


def fan_target_gpu_indices(instance_id=None):
    raw = str(instance_id or "").strip().upper()
    if raw in ("", "GLOBAL"):
        return gpu_indices()
    instance = get_instance(raw)
    if instance:
        return [int(idx) for idx in (instance.get("gpu_indices") or [instance.get("gpu_index", 0)])]
    parsed = parse_instance_identifier(raw)
    if parsed:
        return [int(idx) for idx in (parsed.get("gpu_indices") or [])]
    return gpu_indices()

def set_fan_max_toggle(enable, instance_id=None):
    global fan_manual_override, fan_curve_pause_until, cooling_scope_instance_id
    if instance_id is not None:
        cooling_scope_instance_id = str(instance_id or "GLOBAL").strip().upper() or "GLOBAL"
    target_indices = fan_target_gpu_indices(instance_id)
    cancel_pending_fan_curve_resume()
    fan_manual_override = bool(enable)
    if fan_manual_override:
        fan_curve_pause_until = 0.0
        results = set_gpu_fans(speed=FAN_MAX_SPEED, auto=False, indices=target_indices)
        persist_fan_manual_override_state()
        return results
    fan_curve_pause_until = time.time() + (1 if power_optimizations_enabled else 0)
    results = set_gpu_fans(auto=True, indices=target_indices)
    if power_optimizations_enabled:
        schedule_fan_curve_resume(indices=target_indices, delay=1.0)
    else:
        fan_curve_pause_until = 0.0
    persist_fan_manual_override_state()
    return results

def power_status():
    refresh_power_config_globals()
    try:
        studio_active = bool(globals().get("image_studio_activity_active", lambda **kwargs: False)(max_age=2.0))
    except Exception:
        studio_active = False
    with metrics_lock:
        active = int(metrics.get("active_requests", 0) or 0)
        benchmark_active = bool(metrics.get("benchmark_active")) or benchmark_job_active_from_state_file() or any(
            bool((row or {}).get("benchmark_active"))
            for row in (target_request_metrics or {}).values()
            if isinstance(row, dict)
        )
        booting = switch_job_active()
        idle_for = 0 if active > 0 or benchmark_active or booting or studio_active else int(max(0.0, time.time() - last_request_finished_at))
        fan_curve_text = ", ".join([f"<{temp}C={speed}%" for temp, speed in FAN_CURVE]) + ", >=65C=100%"
        status = {**power_state, "profile": current_profile, "idle_for_seconds": idle_for, "benchmark_active": benchmark_active, "ai_studio_active": studio_active, "idle_power_after_seconds": POWER_IDLE_AFTER_SECONDS, "container_stop_after_seconds": 0, "container_auto_stop_enabled": CONTAINER_AUTO_STOP_ENABLED, "gpu_active_power_limit_w": GPU_ACTIVE_POWER_LIMIT_W, "gpu_idle_power_limit_w": GPU_IDLE_POWER_LIMIT_W, "gpu_idle_lock_clocks": GPU_IDLE_LOCK_CLOCKS, "cpu_active_governor": CPU_ACTIVE_GOVERNOR, "cpu_idle_governor": CPU_IDLE_GOVERNOR, "optimizations_enabled": power_optimizations_enabled, "fan_manual_override": fan_manual_override, "fan_curve": fan_curve_text, "fan_min_safe_speed": FAN_MIN_SAFE_SPEED, "wol_default_mac": str(WOL_MAC or "").replace("-", ":").strip().upper()}
    if benchmark_active:
        status.update(benchmark_power_status_overlay_from_state_file())
    return status

def _docker_inspect_state(container_name):
    name = str(container_name or "").strip()
    if not name:
        return {"exists": False, "running": False, "exit_code": None, "status": ""}
    try:
        payload = subprocess.check_output(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Status}}|{{.State.Running}}|{{.State.ExitCode}}",
                name,
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except Exception:
        return {"exists": False, "running": False, "exit_code": None, "status": ""}
    parts = payload.split("|")
    status = str(parts[0] if len(parts) > 0 else "").strip().lower()
    running = str(parts[1] if len(parts) > 1 else "").strip().lower() == "true"
    try:
        exit_code = int(str(parts[2] if len(parts) > 2 else "").strip())
    except Exception:
        exit_code = None
    return {
        "exists": True,
        "running": running,
        "exit_code": exit_code,
        "status": status,
    }


def _docker_log_path(container_name):
    name = str(container_name or "").strip()
    if not name:
        return ""
    cached = str(docker_log_path_cache.get(name) or "").strip()
    if cached:
        return cached
    try:
        log_path = subprocess.check_output(
            ["docker", "inspect", "--format", "{{.LogPath}}", name],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=4,
        ).strip()
    except Exception:
        return ""
    if log_path:
        docker_log_path_cache[name] = log_path
    return log_path


def _docker_logs_tail_via_log_path(container_name, lines=80, include_timestamps=False):
    log_path = _docker_log_path(container_name)
    if not log_path or not os.path.exists(log_path):
        return ""
    try:
        raw = subprocess.check_output(
            ["tail", "-n", str(max(1, int(lines))), log_path],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        return ""
    rendered = []
    for entry in raw.splitlines():
        try:
            payload = json.loads(entry)
        except Exception:
            continue
        text = str(payload.get("log") or "").rstrip("\n")
        if not text:
            continue
        if include_timestamps:
            stamp = str(payload.get("time") or "").strip()
            rendered.append(f"{stamp} {text}".strip())
        else:
            rendered.append(text)
    return ("\n".join(rendered) + ("\n" if rendered else ""))


def _docker_logs_tail_snapshot(container_name, lines=80, include_timestamps=False, timeout=10):
    name = str(container_name or "").strip()
    if not name:
        return "", ""
    fallback = _docker_logs_tail_via_log_path(name, lines=lines, include_timestamps=include_timestamps)
    if fallback:
        return fallback, ""
    cmd = ["docker", "logs"]
    if include_timestamps:
        cmd.append("--timestamps")
    cmd += ["--tail", str(max(1, int(lines))), name]
    try:
        output = subprocess.check_output(
            cmd,
            text=True,
            stderr=subprocess.STDOUT,
            timeout=max(1.0, float(timeout or 10)),
        )
        return output, ""
    except Exception as exc:
        fallback = _docker_logs_tail_via_log_path(name, lines=lines, include_timestamps=include_timestamps)
        if fallback:
            return fallback, ""
        return "", str(exc)


def _docker_logs_tail(container_name, lines=80, include_timestamps=False, timeout=10):
    output, _error = _docker_logs_tail_snapshot(
        container_name,
        lines=lines,
        include_timestamps=include_timestamps,
        timeout=timeout,
    )
    return output


def _container_bootstrap_complete(container_name):
    name = str(container_name or "").strip()
    if not name:
        return False
    if runtime_bootstrap_marker_cache.get(name):
        return True
    logs = _docker_logs_tail(name, lines=200, timeout=3)
    if not logs:
        return False
    marker = str(LOG_BOOTSTRAP_MARKER or "").strip()
    if marker and marker in logs:
        runtime_bootstrap_marker_cache[name] = True
        return True
    ready = "Application startup complete" in logs
    if ready:
        runtime_bootstrap_marker_cache[name] = True
    return ready


def _container_boot_failure_reason(container_name):
    name = str(container_name or "").strip()
    if not name:
        return ""
    logs = _docker_logs_tail(name, lines=160, timeout=3)
    if not logs:
        return ""
    patterns = [
        r"unable to load model",
        r"error loading model",
        r"failed to load model",
        r"failed to open .*no such file or directory",
        r"no such file or directory",
        r"error:\s*failed to load model",
        r"\berr \[.*load_model",
    ]
    matches = []
    for raw_line in str(logs or "").splitlines():
        line = str(raw_line or "").strip()
        lowered = line.lower()
        if any(re.search(pattern, lowered) for pattern in patterns):
            matches.append(line)
    if not matches:
        return ""
    unique = []
    seen = set()
    for line in matches[-6:]:
        if line in seen:
            continue
        seen.add(line)
        unique.append(line)
    return "\n".join(unique[-4:])


def _runtime_models_available_once(container_name, ready_url, min_interval=15):
    target_url = str(ready_url or "").strip()
    if not target_url:
        return False
    cache_key = str(container_name or target_url or "").strip() or target_url
    now = time.time()
    cached = runtime_ready_probe_cache.get(cache_key) or {}
    if cached.get("ready"):
        return True
    last_checked = float(cached.get("checked_at") or 0.0)
    if last_checked and now - last_checked < max(1, float(min_interval or 1)):
        return False
    runtime_ready_probe_cache[cache_key] = {"ready": False, "checked_at": now}
    try:
        req = urllib.request.Request(
            target_url,
            headers={"Accept": "application/json", "User-Agent": "club3090-control/ready-probe"},
        )
        with urllib.request.urlopen(req, timeout=1.5) as response:
            if 200 <= int(getattr(response, "status", 0) or 0) < 300:
                runtime_ready_probe_cache[cache_key] = {"ready": True, "checked_at": now}
                return True
    except Exception:
        pass
    return False


def _ready_url_port_open(ready_url, timeout=0.5):
    target_url = str(ready_url or "").strip()
    if not target_url:
        return False
    try:
        parsed = urlsplit(target_url)
        port = int(parsed.port or 0)
    except Exception:
        return False
    if port <= 0:
        return False
    return port_open(port, timeout=timeout)


def wait_for_runtime_ready(container_name, ready_url, timeout=900, engine_family=""):
    name = str(container_name or "").strip()
    target_url = str(ready_url or "").strip()
    engine = str(engine_family or "").strip().lower()
    deadline = time.time() + max(5, int(timeout))
    seen_container = False
    while time.time() < deadline:
        state = _docker_inspect_state(name) if name else {"exists": False, "running": False, "exit_code": None, "status": ""}
        if state.get("exists"):
            seen_container = True
            if not state.get("running"):
                logs = _docker_logs_tail(name, lines=80)
                raise RuntimeError(
                    f"Container {name} stopped during boot "
                    f"(status={state.get('status') or 'unknown'}, exit={state.get('exit_code')}).\n"
                    + (logs[-12000:] if logs else "No docker logs were captured before exit.")
                )
            boot_failure = _container_boot_failure_reason(name)
            if boot_failure:
                raise RuntimeError(
                    f"Container {name} reported a startup failure before becoming ready.\n{boot_failure[-12000:]}"
                )
        elif seen_container:
            raise RuntimeError(f"Container {name} disappeared before reaching ready state.")
        api_ready = _runtime_models_available_once(name, target_url, min_interval=(15 if engine == "vllm" else 2))
        bootstrap_ready = _container_bootstrap_complete(name) if engine == "vllm" else False
        port_ready = _ready_url_port_open(target_url, timeout=0.4) if engine and engine != "vllm" else False
        if not name or api_ready or bootstrap_ready or port_ready:
            return True
        time.sleep(1)
    if name and not seen_container:
        raise RuntimeError(f"Container {name} never appeared after compose launch.")
    logs = _docker_logs_tail(name, lines=120) if name else ""
    if logs:
        raise RuntimeError(
            f"Timed out waiting for runtime readiness at {target_url}.\n{logs[-12000:]}"
        )
    raise RuntimeError(f"Timed out waiting for runtime readiness at {target_url}.")

def run_switch(mode):
    selector = canonical_mode_selector(mode)
    spec = resolve_variant_spec(selector)
    if not spec:
        raise ValueError(f"Invalid mode: {mode}")

    def attempt(target_mode, label):
        target_spec = resolve_variant_spec(target_mode)
        if not target_spec:
            raise RuntimeError(f"Unknown target mode: {target_mode}")
        ensure_variant_install_ready(target_spec)
        target_port = mode_default_port(target_mode, 8020)
        ready_url = ready_url_for_mode(target_mode)
        env = _repo_subprocess_env()
        env.pop("CLUB3090_GPU", None)
        env["READY_URL"] = ready_url
        env["PORT"] = str(int(target_port))
        env["MODEL_DIR"] = _resolve_variant_model_dir_root(target_spec)
        env["COMPOSE_BIN"] = COMPOSE_BIN
        env.update(resolve_variant_launch_env(target_spec))
        env.update(preset_launch_env_overrides(target_spec))
        scope_kind = str(target_spec.get("scope_kind") or "").strip().lower()
        try:
            gpu_count = int(detect_gpu_count_runtime() or 0)
        except Exception:
            gpu_count = 0
        selected_indices = []
        if scope_kind == "dual":
            selected_indices = mode_gpu_indices(target_mode, gpu_count=gpu_count)
        elif scope_kind in {"multi", "global_only"}:
            selected_indices = list(range(max(gpu_count, 0)))
        if selected_indices:
            visible_devices = ",".join(str(int(idx)) for idx in selected_indices)
            env["ESTATE_GPUS"] = visible_devices
            env["CUDA_VISIBLE_DEVICES"] = visible_devices
            env["NVIDIA_VISIBLE_DEVICES"] = visible_devices
        cleanup_msg = ""
        ensure_default_runtime_power("switch_launch", force=True)
        log_control(f"SWITCH {label} cleanup before mode={target_mode}")
        cleanup_msg = cleanup_vllm_containers()
        env = _apply_variant_hardware_guard(target_spec, env)
        log_control(f"SWITCH {label} start mode={target_mode} port={env['PORT']} ready_url={ready_url}")
        output = ""
        compose_file = str(target_spec.get("compose_abs_path") or "").strip()
        compose_project_dir = str(target_spec.get("compose_project_dir_abs_path") or "").strip() or os.path.dirname(compose_file) or CLUB3090_DIR
        override_file = refresh_variant_cache_override(target_spec)
        cmd = compose_cmd() + ["--project-directory", compose_project_dir, "-f", compose_file]
        if override_file:
            cmd.extend(["-f", override_file])
        cmd.extend(["up", "-d"])
        p = subprocess.run(
            cmd,
            cwd=compose_project_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=1800,
        )
        rc = int(p.returncode)
        output = p.stdout or ""
        if rc != 0:
            log_control(f"SWITCH {label} failed mode={target_mode} rc={rc}")
            cleanup_vllm_containers()
            raise RuntimeError((output[-12000:] or f"launch exited with {rc}") + f"\ncleanup={cleanup_msg}")
        wait_for_runtime_ready(
            str(target_spec.get("container_name") or ""),
            ready_url,
            timeout=900,
            engine_family=variant_engine_family(target_spec),
        )
        warmup = maybe_warmup_variant_runtime(target_spec, ready_url)
        if warmup.get("skipped"):
            log_control(f"SWITCH {label} warmup skipped mode={target_mode}: {warmup.get('reason')}")
        elif warmup.get("ok"):
            log_control(
                f"SWITCH {label} warmup complete mode={target_mode} model={warmup.get('model') or ''} duration={warmup.get('duration_s') or 0}s"
            )
        else:
            log_control(f"SWITCH {label} warmup failed mode={target_mode}: {warmup.get('reason') or 'unknown'}")
        write_active_mode(target_mode)
        write_last_good_mode(target_mode)
        clear_switch_failure(target_mode)
        _set_switch_job(
            active=False,
            status="success",
            mode=target_mode,
            target="GLOBAL",
            finished_at=int(time.time()),
            error="",
        )
        with metrics_lock:
            power_state["container"] = "running"
            power_state["last_action"] = f"switch_{target_mode}"
            power_state["last_error"] = ""
        log_control(f"SWITCH {label} complete mode={target_mode}")
        return output[-12000:]

    with switch_lock:
        _set_switch_job(
            active=True,
            status="booting",
            mode=selector,
            target="GLOBAL",
            started_at=int(time.time()),
            finished_at=0,
            error="",
        )
        try:
            return attempt(selector, "primary")
        except Exception as first_error:
            if read_active_mode_file() == selector:
                clear_active_mode()
            current_job = switch_job_snapshot()
            stopped_by_user = (
                str(current_job.get("status") or "") == "stopped"
                and str(current_job.get("mode") or "") == selector
                and str(current_job.get("target") or "").upper() == "GLOBAL"
            )
            if not stopped_by_user:
                write_switch_failure(selector, first_error)
                _set_switch_job(
                    active=False,
                    status="failed",
                    mode=selector,
                    target="GLOBAL",
                    finished_at=int(time.time()),
                    error=str(first_error)[-12000:],
                )
            with metrics_lock:
                power_state["container"] = "stopped"
                power_state["last_action"] = f"switch_failed_{selector}"
                power_state["last_error"] = str(first_error)[-1000:]
            raise
