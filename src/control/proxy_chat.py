def parse_preset_path(path):
    parsed = urlsplit(path)
    clean = parsed.path
    suffix = ("?" + parsed.query) if parsed.query else ""
    parts = [p for p in clean.split("/") if p]
    if not parts:
        return path, None, None

    # Supported raw/preset URL forms:
    #   /v1/chat/completions
    #   /chat/completions            (normalize to /v1/chat/completions)
    #   /v1/completions
    #   /completions                 (normalize to /v1/completions)
    #   /v1/models
    #   /models                      (normalize to /v1/models)
    #   /v1/<preset>/chat/completions
    #   /v1/<preset>/v1/chat/completions   (clients that append /v1/...)
    #   /<preset>/chat/completions
    #   /<preset>/v1/chat/completions      (clients with base URL :8009/<preset>)
    # This preserves raw OpenAI paths like /v1/chat/completions.
    if len(parts) >= 3 and parts[0] == "v1" and parts[1] == "chat" and parts[2] == "completions":
        return path, None, None
    if len(parts) >= 2 and parts[0] == "chat" and parts[1] == "completions":
        return "/v1/chat/completions" + (("/" + "/".join(parts[2:])) if len(parts) > 2 else "") + suffix, None, None
    if parts and parts[0] == "completions":
        return "/v1/completions" + (("/" + "/".join(parts[1:])) if len(parts) > 1 else "") + suffix, None, None
    if parts == ["models"]:
        return "/v1/models" + suffix, None, None

    all_presets = get_all_presets()

    def split_candidate(raw):
        cap = None
        candidate = raw
        for prefix, value in LENGTH_PREFIXES.items():
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix):]
                cap = value
                break
        if candidate in all_presets:
            return candidate, cap
        return None, None

    def upstream_from_rest(rest):
        # If a client appended /v1/... to a preset base URL, remove that nested v1.
        if rest and rest[0] == "v1":
            rest = rest[1:]
        if not rest:
            return "/v1"
        if rest == ["models"]:
            return "/v1/models"
        if rest[:2] == ["chat", "completions"]:
            return "/v1/chat/completions" + (("/" + "/".join(rest[2:])) if len(rest) > 2 else "")
        if rest[0] == "completions":
            return "/v1/completions" + (("/" + "/".join(rest[1:])) if len(rest) > 1 else "")
        return "/v1/" + "/".join(rest)

    # Normal current style: /v1/<preset>/...
    if parts[0] == "v1" and len(parts) >= 2:
        candidate, cap = split_candidate(parts[1])
        if candidate:
            return upstream_from_rest(parts[2:]) + suffix, candidate, cap
        return path, None, None

    # Compatibility style: /<preset>/... so clients can safely append /v1/...
    candidate, cap = split_candidate(parts[0])
    if candidate:
        return upstream_from_rest(parts[1:]) + suffix, candidate, cap

    return path, None, None


def is_supported_proxy_path(upstream_path, method="GET"):
    path = str(upstream_path or "").strip()
    verb = str(method or "GET").upper()
    if not path:
        return False
    if path in {"/v1/models", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc", "/version", "/health", "/metrics", "/load", "/ping"}:
        return True
    if path.startswith("/docs/"):
        return True
    if path.startswith("/v1/"):
        return True
    if verb == "POST" and path in {
        "/tokenize",
        "/detokenize",
        "/invocations",
        "/inference/v1/generate",
        "/scale_elastic_ep",
        "/is_scaling_elastic_ep",
        "/generative_scoring",
    }:
        return True
    return False

def merge_preset_params(payload, preset):
    merged = dict(payload or {})
    for key, value in dict(preset or {}).items():
        if key == "chat_template_kwargs" and isinstance(value, dict):
            current = merged.get("chat_template_kwargs")
            if not isinstance(current, dict):
                current = {}
            merged["chat_template_kwargs"] = {**current, **value}
        else:
            merged[key] = value
    return merged

def merge_system_prompt_text(primary, secondary):
    first = str(primary or "").strip()
    second = str(secondary or "").strip()
    if first and second:
        return first + "\n\n" + second
    return first or second

def inject_system_prompt_into_messages(messages, system_prompt):
    prompt = str(system_prompt or "").strip()
    if not prompt:
        return messages
    rows = list(messages or [])
    for item in rows:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").strip().lower() != "system":
            continue
        content = item.get("content")
        if isinstance(content, str):
            item["content"] = merge_system_prompt_text(prompt, content)
        elif isinstance(content, list):
            parts = [{"type": "text", "text": prompt}]
            parts.extend([part for part in content if isinstance(part, dict)])
            item["content"] = parts
        else:
            item["content"] = prompt
        return rows
    rows.insert(0, {"role": "system", "content": prompt})
    return rows

def inject_system_prompt_into_payload(payload, system_prompt):
    prompt = str(system_prompt or "").strip()
    if not prompt or not isinstance(payload, dict):
        return payload
    updated = dict(payload)
    if isinstance(updated.get("messages"), list):
        updated["messages"] = inject_system_prompt_into_messages(updated.get("messages"), prompt)
        return updated
    if isinstance(updated.get("instructions"), str):
        updated["instructions"] = merge_system_prompt_text(prompt, updated.get("instructions"))
        return updated
    if isinstance(updated.get("prompt"), str):
        updated["prompt"] = merge_system_prompt_text(prompt, updated.get("prompt"))
        return updated
    if isinstance(updated.get("input"), str):
        updated["input"] = merge_system_prompt_text(prompt, updated.get("input"))
        return updated
    return updated


def normalize_reasoning_toggle(value):
    text = str(value or "").strip().strip('"').strip("'").lower()
    if not text:
        return None
    if text in {"on", "true", "1", "yes", "enabled"}:
        return True
    if text in {"off", "false", "0", "no", "disabled"}:
        return False
    match = re.match(r"^\$\{[^}:]+:-([^}]+)\}$", text)
    if match:
        return normalize_reasoning_toggle(match.group(1))
    return None


def runtime_reasoning_enabled(spec):
    row = spec if isinstance(spec, dict) else {}
    env = preset_launch_env_overrides(row)
    env_reasoning = normalize_reasoning_toggle(env.get("REASONING"))
    if env_reasoning is not None:
        return env_reasoning
    command_text = preset_launch_command_override(row) or str(row.get("default_engine_switches") or "").replace("\r", "").strip()
    if not command_text:
        return None
    for raw_line in command_text.splitlines():
        line = str(raw_line or "").strip()
        if not line.startswith("--reasoning"):
            continue
        if "=" in line:
            return normalize_reasoning_toggle(line.split("=", 1)[1])
        parts = line.split(None, 1)
        if len(parts) == 2:
            return normalize_reasoning_toggle(parts[1])
    return None


def preset_requests_enable_thinking(preset_name):
    key = str(preset_name or "").strip()
    if not key:
        return False
    preset = get_all_presets().get(key) or {}
    template = preset.get("chat_template_kwargs") if isinstance(preset, dict) else {}
    if not isinstance(template, dict):
        return False
    return bool(template.get("enable_thinking") or template.get("preserve_thinking"))


def ensure_runtime_thinking_defaults(payload, spec=None, preset_name=""):
    if not isinstance(payload, dict):
        return payload
    current = payload.get("chat_template_kwargs")
    current_map = dict(current) if isinstance(current, dict) else {}
    if "enable_thinking" in current_map:
        return payload
    enable_thinking = True if preset_requests_enable_thinking(preset_name) else runtime_reasoning_enabled(spec)
    if enable_thinking is None:
        enable_thinking = False
    updated = dict(payload)
    updated["chat_template_kwargs"] = {**current_map, "enable_thinking": bool(enable_thinking)}
    return updated


def apply_preset(body, preset_name, max_token_cap, spec=None):
    try:
        data = json.loads(body or b"{}")
    except Exception:
        return body
    preset = get_all_presets().get(preset_name)
    if not preset:
        data = dict(data)
    else:
        data = merge_preset_params(dict(data), preset)
        data = inject_system_prompt_into_payload(data, preset_system_prompt(preset_name))
    data = ensure_runtime_thinking_defaults(data, spec, preset_name)
    if max_token_cap is not None:
        capped_any = False
        for token_key in ("max_tokens", "max_completion_tokens"):
            if token_key in data:
                try:
                    data[token_key] = min(int(data[token_key]), max_token_cap)
                except Exception:
                    data[token_key] = max_token_cap
                capped_any = True
        if not capped_any:
            data["max_tokens"] = max_token_cap
    return json.dumps(data, separators=(",", ":")).encode("utf-8")

def parse_instance_path(path):
    parsed = urlsplit(path)
    parts = [p for p in parsed.path.split("/") if p]
    if parts and parse_instance_identifier(parts[0]):
        instance_id = parse_instance_identifier(parts[0])["id"]
        trimmed = "/" + "/".join(parts[1:]) if len(parts) > 1 else "/"
        if parsed.query:
            trimmed += "?" + parsed.query
        return instance_id, trimmed
    return None, path


def runtime_supports_vision(spec):
    text = str((spec or {}).get("vision") or "").strip().lower()
    return text not in {"", "none", "no", "false", "blocked", "disabled", "n/a"}


def resolve_admin_chat_target(instance_id="", mode=""):
    target_id = str(instance_id or "").strip().upper()
    selector = canonical_mode_selector(mode) if mode else ""
    if target_id and target_id != "GLOBAL":
        instance = get_instance(target_id)
        if instance and instance_running(instance):
            return {
                "id": instance["id"],
                "kind": instance.get("kind", "single"),
                "gpu_index": int(instance.get("gpu_index", 0) or 0),
                "gpu_indices": list(instance.get("gpu_indices") or [instance.get("gpu_index", 0)]),
                "mode": instance_runtime_mode(instance),
                "enabled": bool(instance.get("enabled")),
                "port": instance_runtime_port(instance),
                "container": instance_runtime_container_name(instance),
                "running": True,
                "booting": False,
            }, resolve_variant_spec(instance.get("mode")) or {}
    current_mode = active_mode()
    current_name = current_container()
    current_port = active_port()
    if current_name and port_open(current_port, timeout=0.08):
        if not selector or canonical_mode_selector(current_mode) == selector:
            return {
                "id": "GLOBAL",
                "kind": "global",
                "mode": current_mode,
                "container": current_name,
                "port": current_port,
                "running": True,
                "gpu_indices": mode_gpu_indices(current_mode, gpu_count=detect_gpu_count_runtime()),
            }, resolve_variant_spec(current_mode) or {}
    runtime_rows = running_runtime_rows(instances_snapshot())
    if target_id:
        match = next((dict(row) for row in runtime_rows if str(row.get("id") or "").strip().upper() == target_id), None)
        if match:
            return match, resolve_variant_spec(match.get("mode")) or {}
    if selector:
        match = next((dict(row) for row in runtime_rows if canonical_mode_selector(row.get("mode")) == selector), None)
        if match:
            return match, resolve_variant_spec(match.get("mode")) or {}
        if current_container() and canonical_mode_selector(active_mode()) == selector:
            spec = resolve_variant_spec(selector) or {}
            return {
                "id": "GLOBAL",
                "kind": "global",
                "mode": selector,
                "container": current_container(),
                "port": active_port(),
                "running": True,
                "gpu_indices": mode_gpu_indices(selector, gpu_count=detect_gpu_count_runtime()),
            }, spec
    primary = primary_instance()
    if primary and primary.get("running"):
        return dict(primary), resolve_variant_spec(primary.get("mode")) or {}
    mode_now = active_mode()
    spec = resolve_variant_spec(mode_now) or {}
    container = current_container()
    if container and port_open(active_port(), timeout=0.08):
        return {
            "id": "GLOBAL",
            "kind": "global",
            "mode": mode_now,
            "container": container,
            "port": active_port(),
            "running": True,
            "gpu_indices": mode_gpu_indices(mode_now, gpu_count=detect_gpu_count_runtime()),
        }, spec
    raise RuntimeError("No active runtime is available for chat.")


def normalize_admin_chat_messages(messages, allow_images=False):
    normalized = []
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"system", "user", "assistant"}:
            continue
        content = item.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = str(part.get("type") or "").strip().lower()
                if part_type == "text":
                    text = str(part.get("text") or "")
                    if text:
                        parts.append({"type": "text", "text": text})
                elif allow_images and part_type == "image_url":
                    image_url = part.get("image_url")
                    if isinstance(image_url, dict):
                        url = str(image_url.get("url") or "").strip()
                    else:
                        url = str(image_url or "").strip()
                    if url:
                        parts.append({"type": "image_url", "image_url": {"url": chat_attachment_data_url(url)}})
            reasoning_text = extract_reasoning_text(item)
            if parts or (role == "assistant" and reasoning_text):
                row = {"role": role, "content": parts if parts else ""}
                if role == "assistant" and reasoning_text:
                    row["reasoning_content"] = reasoning_text
                normalized.append(row)
            continue
        text = str(content or "")
        reasoning_text = extract_reasoning_text(item)
        if text or (role == "assistant" and reasoning_text):
            row = {"role": role, "content": text}
            if role == "assistant" and reasoning_text:
                row["reasoning_content"] = reasoning_text
            normalized.append(row)
    if not normalized:
        raise ValueError("At least one chat message is required")
    return normalized


def apply_admin_chat_params(payload, params):
    params = params if isinstance(params, dict) else {}
    allowed_scalars = (
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "presence_penalty",
        "frequency_penalty",
        "repetition_penalty",
        "max_tokens",
        "max_completion_tokens",
        "truncate_prompt_tokens",
        "seed",
        "min_tokens",
        "logprobs",
        "top_logprobs",
        "length_penalty",
    )
    allowed_bools = (
        "ignore_eos",
        "skip_special_tokens",
        "include_stop_str_in_output",
    )
    for key in allowed_scalars:
        if params.get(key) not in (None, ""):
            payload[key] = params.get(key)
    for key in allowed_bools:
        if key in params:
            payload[key] = bool(params.get(key))
    stop = params.get("stop")
    if isinstance(stop, list):
        cleaned = [str(item) for item in stop if str(item)]
        if cleaned:
            payload["stop"] = cleaned
    elif isinstance(stop, str) and stop.strip():
        payload["stop"] = stop.strip()
    chat_template_kwargs = {}
    if "enable_thinking" in params:
        chat_template_kwargs["enable_thinking"] = bool(params.get("enable_thinking"))
    if "preserve_thinking" in params:
        chat_template_kwargs["preserve_thinking"] = bool(params.get("preserve_thinking"))
        if chat_template_kwargs["preserve_thinking"]:
            chat_template_kwargs["enable_thinking"] = True
    if chat_template_kwargs:
        payload["chat_template_kwargs"] = {**dict(payload.get("chat_template_kwargs") or {}), **chat_template_kwargs}
    return payload

def build_admin_chat_payload(data, spec, stream=False):
    payload = {
        "messages": normalize_admin_chat_messages(data.get("messages") or [], allow_images=runtime_supports_vision(spec)),
        "stream": bool(stream),
    }
    model_name = str(data.get("model") or spec.get("served_model_name") or spec.get("model_id") or "").strip()
    if model_name:
        payload["model"] = model_name
    preset_name = str(data.get("api_preset") or "").strip()
    if preset_name:
        preset = get_all_presets().get(preset_name)
        if not preset:
            raise ValueError(f"Unknown API preset: {preset_name}")
        payload = merge_preset_params(payload, preset)
        payload = inject_system_prompt_into_payload(payload, preset_system_prompt(preset_name))
    else:
        payload = apply_admin_chat_params(payload, data.get("params"))
        payload = inject_system_prompt_into_payload(payload, (data.get("params") or {}).get("system_prompt"))
    payload = ensure_runtime_thinking_defaults(payload, spec, preset_name)
    if stream:
        payload["stream_options"] = {"include_usage": True}
    return payload


def payload_allows_visible_thinking(payload):
    row = payload if isinstance(payload, dict) else {}
    chat_template_kwargs = (
        row.get("chat_template_kwargs")
        if isinstance(row.get("chat_template_kwargs"), dict)
        else {}
    )
    return bool(
        chat_template_kwargs.get("enable_thinking")
        or chat_template_kwargs.get("preserve_thinking")
    )


def strip_leading_inline_thinking_blocks(text):
    value = str(text or "")
    while True:
        stripped = re.sub(
            r"^\s*<(think|thinking)>\s*[\s\S]*?</\1>\s*",
            "",
            value,
            count=1,
            flags=re.I,
        )
        if stripped == value:
            return value
        value = stripped


def strip_leading_inline_thinking_from_message(message):
    row = dict(message or {}) if isinstance(message, dict) else {}
    if "content" in row:
        row["content"] = strip_leading_inline_thinking_blocks(row.get("content") or "")
    return row


def sanitize_chat_completion_payload(payload, allow_visible_thinking):
    if allow_visible_thinking or not isinstance(payload, dict):
        return payload
    updated = dict(payload)
    choices = []
    for raw_choice in payload.get("choices") or []:
        choice = dict(raw_choice or {}) if isinstance(raw_choice, dict) else {}
        if isinstance(choice.get("message"), dict):
            choice["message"] = strip_leading_inline_thinking_from_message(choice.get("message"))
        if "text" in choice:
            choice["text"] = strip_leading_inline_thinking_blocks(choice.get("text") or "")
        choices.append(choice)
    if choices:
        updated["choices"] = choices
    return updated


def sanitize_chat_completion_response_bytes(payload_bytes, allow_visible_thinking):
    if allow_visible_thinking:
        return payload_bytes
    try:
        payload = json.loads((payload_bytes or b"").decode("utf-8", errors="ignore") or "{}")
    except Exception:
        return payload_bytes
    sanitized = sanitize_chat_completion_payload(payload, allow_visible_thinking)
    try:
        return json.dumps(sanitized, separators=(",", ":")).encode("utf-8")
    except Exception:
        return payload_bytes


def consume_leading_inline_thinking_stream(buffer):
    value = str(buffer or "")
    while True:
        match = re.match(
            r"^\s*<(think|thinking)>\s*[\s\S]*?</\1>\s*",
            value,
            flags=re.I,
        )
        if match:
            value = value[match.end():]
            continue
        if re.match(r"^\s*<(think|thinking)\b", value, flags=re.I) and not re.search(
            r"</(think|thinking)>",
            value,
            flags=re.I,
        ):
            return "", True
        return value, False


def chat_backend_request(port, payload):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=None) as response:
            raw = response.read()
            parsed = json.loads(raw.decode("utf-8", errors="ignore") or "{}")
            return sanitize_chat_completion_payload(
                parsed,
                payload_allows_visible_thinking(payload),
            )
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(body or f"Runtime returned HTTP {e.code}")
    except Exception as e:
        raise RuntimeError(str(e))

def open_chat_backend_stream(port, payload):
    attempts = []
    primary = dict(payload or {})
    attempts.append(primary)
    if "stream_options" in primary:
        fallback = dict(primary)
        fallback.pop("stream_options", None)
        attempts.append(fallback)
    last_error = None
    for index, attempt in enumerate(attempts):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=json.dumps(attempt, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            return urllib.request.urlopen(req, timeout=None), attempt
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            last_error = RuntimeError(body or f"Runtime returned HTTP {e.code}")
            if index == 0 and "stream_options" in attempt and ("stream_options" in body.lower() or "include_usage" in body.lower()):
                continue
            raise last_error
        except Exception as e:
            last_error = RuntimeError(str(e))
            raise last_error
    raise last_error or RuntimeError("Unable to open chat stream")

def iter_sse_events(response):
    buffer = ""
    decoder = codecs.getincrementaldecoder("utf-8")()
    while True:
        chunk = response.read1(8192) if hasattr(response, "read1") else response.read(8192)
        if not chunk:
            break
        text = decoder.decode(chunk).replace("\r\n", "\n").replace("\r", "\n")
        buffer += text
        while "\n\n" in buffer:
            raw_event, buffer = buffer.split("\n\n", 1)
            yield raw_event
    tail = decoder.decode(b"", final=True).replace("\r\n", "\n").replace("\r", "\n")
    buffer += tail
    if buffer.strip():
        yield buffer

def merge_stream_tool_call_delta(store, delta_list):
    for item in delta_list or []:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index") or 0)
        except Exception:
            index = 0
        current = dict(store.get(index) or {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
        if item.get("id"):
            current["id"] = str(item.get("id"))
        if item.get("type"):
            current["type"] = str(item.get("type"))
        function = item.get("function") if isinstance(item.get("function"), dict) else {}
        current_function = dict(current.get("function") or {"name": "", "arguments": ""})
        if function.get("name"):
            current_function["name"] = str(function.get("name"))
        if function.get("arguments") not in (None, ""):
            current_function["arguments"] = str(current_function.get("arguments") or "") + str(function.get("arguments") or "")
        current["function"] = current_function
        store[index] = current

def finalize_stream_tool_calls(store):
    rows = []
    for index in sorted(store.keys()):
        item = dict(store.get(index) or {})
        function = dict(item.get("function") or {})
        rows.append({
            "id": str(item.get("id") or secrets.token_hex(6)),
            "type": str(item.get("type") or "function"),
            "function": {
                "name": str(function.get("name") or ""),
                "arguments": str(function.get("arguments") or ""),
            },
        })
    return rows

def extract_reasoning_text(payload):
    if not isinstance(payload, dict):
        return ""
    for key in ("reasoning_content", "reasoning"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""

def stream_admin_chat_request(handler, data):
    global last_request_finished_at
    data = data if isinstance(data, dict) else {}
    target = None
    target_id = "GLOBAL"
    target_key = "GLOBAL"
    preset_name = str(data.get("api_preset") or "").strip() or "direct"
    start = time.time()
    first_chunk_at = None
    last_chunk_at = None
    first_output_at = None
    last_output_at = None
    status_code = 200
    metrics_started = False
    stream_opened = False
    final_log_metrics = {}
    request_log_metric_peaks = {}
    prompt_tps = None
    response_usage = {"tokens": 0, "input_tokens": 0, "output_tokens": 0, "tool_calls": 0}
    authoritative_output_tokens = None
    request_usage = {}
    log_watcher = None
    log_stream_start_generation = -1
    log_stream_start_seq = 0
    assistant_text = ""
    reasoning_text = ""
    conversation_id = str((data or {}).get("conversation_id") or "").strip()
    client_connected = True
    last_metrics_emit_at = 0.0
    backend_stream_opened_at = None
    aborted_by_user = False

    def ensure_stream_not_stopped():
        nonlocal aborted_by_user
        if conversation_id and admin_chat_stream_stop_requested(conversation_id):
            aborted_by_user = True
            raise RuntimeError("Generation aborted.")

    def request_latency_seconds(ttft_value=None, prompt_tokens_value=None, prompt_tps_value=None):
        ttft_number = safe_float(ttft_value)
        prompt_tokens_number = safe_float(prompt_tokens_value)
        prompt_tps_number = safe_float(prompt_tps_value)
        if ttft_number and prompt_tokens_number and prompt_tps_number:
            prefill_seconds = prompt_tokens_number / max(prompt_tps_number, 0.001)
            latency_guess = ttft_number - prefill_seconds
            if latency_guess >= 0:
                return round(max(0.0, latency_guess), 3)
        if backend_stream_opened_at is not None:
            return round(max(0.0, float(backend_stream_opened_at) - float(start)), 3)
        return None

    def emit_sse(event_name, payload):
        nonlocal client_connected
        if not client_connected:
            return False
        try:
            handler.send_sse_event(event_name, payload)
            return True
        except Exception:
            client_connected = False
            return False

    def emit_live_metrics(force=False, extra=None):
        nonlocal last_metrics_emit_at
        if not conversation_id:
            return None
        now = time.time()
        if not force and now - float(last_metrics_emit_at or 0.0) < 2.0:
            return None
        log_metrics_live = (
            runtime_log_metrics_for_container(target.get("container"), force=True, max_age=0.0)
            if target and target.get("container")
            else {}
        )
        first_response_at = first_output_at or first_chunk_at
        ttft_live = round(first_response_at - start, 3) if first_response_at else None
        output_tokens_live = int(response_usage.get("output_tokens") or 0)
        if output_tokens_live <= 0 and assistant_text.strip():
            output_tokens_live = estimate_text_tokens(assistant_text)
        prompt_tokens_live = int(response_usage.get("input_tokens") or request_usage.get("input_tokens") or 0)
        total_tokens_live = int(response_usage.get("tokens") or 0)
        if total_tokens_live <= 0:
            total_tokens_live = prompt_tokens_live + output_tokens_live
        generation_tps_live = resolve_best_generation_tps(
            resolve_request_generation_tps(log_metrics_live),
            authoritative_output_tokens,
            output_tokens_live,
            first_output_at or first_chunk_at,
            last_output_at or last_chunk_at,
        )
        prompt_tps_live = derive_request_prompt_tps(
            prompt_tokens_live,
            output_tokens_live,
            ttft_live,
            round(now - start, 3),
            generation_tps_live,
            log_metrics_live.get("prompt_tps"),
        )
        live_latency = request_latency_seconds(
            ttft_live,
            prompt_tokens_live,
            prompt_tps_live,
        )
        payload = {
            "ok": True,
            "instance_id": target_id,
            "mode": str(target.get("mode") or ""),
            "model": str(current_payload.get("model") or ""),
            "usage": {
                "input_tokens": prompt_tokens_live,
                "output_tokens": output_tokens_live,
                "tokens": total_tokens_live,
                "tool_calls": int(response_usage.get("tool_calls") or 0),
            },
            "generation_tps": generation_tps_live,
            "prompt_tps": prompt_tps_live,
            "gpu_kv_cache_usage_pct": log_metrics_live.get("gpu_kv_cache_usage_pct"),
            "cpu_kv_cache_usage_pct": log_metrics_live.get("cpu_kv_cache_usage_pct"),
            "prefix_cache_hit_rate_pct": log_metrics_live.get("prefix_cache_hit_rate_pct"),
            "speculative": dict(log_metrics_live.get("speculative") or {}),
            "ttft_s": ttft_live,
            "latency_s": live_latency,
            "status": 200,
            "path": "/admin/chat-stream",
        }
        preview_update_target_request_metrics(
            target_key,
            preset_name,
            "/admin/chat-stream",
            200,
            live_latency,
            ttft_live,
            prompt_tps_live,
            generation_tps_live,
            prompt_tokens_live,
            output_tokens_live,
            total_tokens_live,
            int(response_usage.get("tool_calls") or 0),
            log_metrics_live,
        )
        if isinstance(extra, dict):
            payload.update(extra)
        update_admin_chat_stream_state(
            conversation_id,
            status="streaming",
            instance_id=target_id,
            mode=str(target.get("mode") or ""),
            model=str(current_payload.get("model") or ""),
            assistant_text=assistant_text,
            reasoning_text=reasoning_text,
            usage=payload["usage"],
            generation_tps=generation_tps_live,
            prompt_tps=prompt_tps_live,
            gpu_kv_cache_usage_pct=payload.get("gpu_kv_cache_usage_pct"),
            cpu_kv_cache_usage_pct=payload.get("cpu_kv_cache_usage_pct"),
            prefix_cache_hit_rate_pct=payload.get("prefix_cache_hit_rate_pct"),
            speculative=payload.get("speculative"),
            ttft_s=ttft_live,
            latency_s=live_latency,
            message="Generating message...",
        )
        emit_sse("metrics", payload)
        last_metrics_emit_at = now
        return payload
    try:
        debug_audit(
            "chat_stream_request",
            incoming_instance_id=str((data or {}).get("instance_id") or ""),
            incoming_mode=str((data or {}).get("mode") or ""),
            incoming_message_count=len((data or {}).get("messages") or []) if isinstance(data, dict) else 0,
            incoming_api_preset=str((data or {}).get("api_preset") or ""),
        )
        target, spec = resolve_admin_chat_target(
            instance_id=data.get("instance_id") or "",
            mode=data.get("mode") or "",
        )
        target_id = str(target.get("id") or "GLOBAL")
        target_key = str(target_id or "").strip().upper() or "GLOBAL"
        port = int(target.get("port") or active_port() or 0)
        if port <= 0:
            raise RuntimeError("The selected runtime does not expose a valid port.")
        payload = build_admin_chat_payload(data, spec, stream=True)
        if target and target.get("container"):
            log_watcher = get_runtime_log_watcher(target.get("container"))
            if log_watcher is not None:
                log_snapshot = log_watcher.snapshot()
                log_stream_start_generation = int(log_snapshot.get("generation") or 0)
                log_stream_start_seq = int(log_snapshot.get("seq") or 0)
        tools, tool_map = build_enabled_mcp_tools()
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if conversation_id:
            begin_admin_chat_stream_control(conversation_id)
        request_seed = {
            "messages": payload.get("messages") or [],
            "max_tokens": payload.get("max_tokens"),
            "max_completion_tokens": payload.get("max_completion_tokens"),
            "tool_choice": payload.get("tool_choice"),
            "max_tool_calls": payload.get("max_tool_calls"),
            "max_parallel_tool_calls": payload.get("max_parallel_tool_calls"),
        }
        request_usage = extract_request_usage(
            json.dumps(request_seed, separators=(",", ":")).encode("utf-8")
        )
        if conversation_id:
            begin_admin_chat_stream_state(
                conversation_id,
                instance_id=target_id,
                mode=str(target.get("mode") or ""),
                model=str(payload.get("model") or ""),
                assistant_text="",
                reasoning_text="",
                usage={
                    "input_tokens": int(request_usage.get("input_tokens") or 0),
                    "output_tokens": 0,
                    "tokens": int(request_usage.get("input_tokens") or 0),
                    "tool_calls": 0,
                },
                message="Generating message...",
            )
        with metrics_lock:
            metrics["total_requests"] += 1
            metrics["active_requests"] += 1
            metrics["last_preset"] = preset_name
            metrics["last_path"] = "/admin/chat-stream"
            target_request_metrics.setdefault(target_key, default_target_request_metrics())
        metrics_started = True
        ensure_vllm_running_for_request(target.get("id") if target else None)

        handler.close_connection = False
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "keep-alive")
        handler.emit_pending_headers()
        handler.end_headers()
        stream_opened = True
        current_payload = dict(payload)
        for _ in range(6):
            stream_response, current_payload = open_chat_backend_stream(port, current_payload)
            if backend_stream_opened_at is None:
                backend_stream_opened_at = time.time()
            pass_text_parts = []
            pass_reasoning_parts = []
            tool_delta_store = {}
            inline_thinking_buffer = ""
            inline_thinking_pending = not payload_allows_visible_thinking(current_payload)
            ensure_stream_not_stopped()
            with stream_response as response:
                register_admin_chat_stream_cancel(conversation_id, response.close)
                for raw_event in iter_sse_events(response):
                    ensure_stream_not_stopped()
                    data_lines = []
                    for raw_line in str(raw_event or "").split("\n"):
                        if raw_line.startswith("data:"):
                            data_lines.append(raw_line[5:].lstrip())
                    if not data_lines:
                        continue
                    data_text = "\n".join(data_lines).strip()
                    if not data_text or data_text == "[DONE]":
                        continue
                    try:
                        event_obj = json.loads(data_text)
                    except Exception:
                        continue
                    event_at = time.time()
                    if first_chunk_at is None:
                        first_chunk_at = event_at
                    last_chunk_at = event_at
                    usage_block = event_obj.get("usage") if isinstance(event_obj.get("usage"), dict) else {}
                    if usage_block:
                        authoritative_output_tokens = max(
                            int(authoritative_output_tokens or 0),
                            int(authoritative_output_tokens_from_usage(usage_block) or 0),
                        ) or authoritative_output_tokens
                        response_usage["input_tokens"] = max(
                            int(response_usage.get("input_tokens") or 0),
                            int(first_defined(usage_block.get("prompt_tokens"), usage_block.get("input_tokens"), 0) or 0),
                        )
                        response_usage["output_tokens"] = max(
                            int(response_usage.get("output_tokens") or 0),
                            int(first_defined(usage_block.get("completion_tokens"), usage_block.get("output_tokens"), 0) or 0),
                        )
                        response_usage["tokens"] = max(
                            int(response_usage.get("tokens") or 0),
                            int(usage_block.get("total_tokens") or 0),
                        )
                    for choice in event_obj.get("choices") or []:
                        if not isinstance(choice, dict):
                            continue
                        delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
                        reasoning_chunk = extract_reasoning_text(delta) or extract_reasoning_text(choice)
                        output_emitted = False
                        if reasoning_chunk:
                            reasoning_text += reasoning_chunk
                            pass_reasoning_parts.append(reasoning_chunk)
                            emit_sse("reasoning", {"text": reasoning_chunk})
                            output_emitted = True
                        content_chunk = str(delta.get("content") or choice.get("text") or "")
                        if inline_thinking_pending and content_chunk:
                            inline_thinking_buffer += content_chunk
                            content_chunk, inline_thinking_pending = consume_leading_inline_thinking_stream(
                                inline_thinking_buffer
                            )
                            if inline_thinking_pending:
                                continue
                            inline_thinking_buffer = ""
                        if content_chunk:
                            assistant_text += content_chunk
                            pass_text_parts.append(content_chunk)
                            emit_sse("delta", {"text": content_chunk})
                            output_emitted = True
                        if delta.get("tool_calls"):
                            output_emitted = True
                        if output_emitted:
                            if first_output_at is None:
                                first_output_at = event_at
                            last_output_at = event_at
                            emit_live_metrics()
                        merge_stream_tool_call_delta(tool_delta_store, delta.get("tool_calls") or [])
            tool_calls = finalize_stream_tool_calls(tool_delta_store)
            register_admin_chat_stream_cancel(conversation_id, None)
            ensure_stream_not_stopped()
            if not tool_calls:
                break
            payload_messages = list(current_payload.get("messages") or [])
            assistant_message = {
                "role": "assistant",
                "content": "".join(pass_text_parts),
                "tool_calls": tool_calls,
            }
            pass_reasoning_text = "".join(pass_reasoning_parts)
            if pass_reasoning_text:
                assistant_message["reasoning_content"] = pass_reasoning_text
            payload_messages.append(assistant_message)
            for tool_call in tool_calls:
                ensure_stream_not_stopped()
                call_id = str(tool_call.get("id") or secrets.token_hex(6))
                function = dict(tool_call.get("function") or {})
                tool_name = str(function.get("name") or "")
                emit_sse("tool", {"name": tool_name, "message": f"Running tool {tool_name}..."})
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except Exception:
                    arguments = {}
                tool_result = call_enabled_mcp_tool(tool_name, arguments, tool_map)
                payload_messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": tool_result,
                })
                response_usage["tool_calls"] = int(response_usage.get("tool_calls") or 0) + 1
            current_payload["messages"] = payload_messages

        if int(response_usage.get("output_tokens") or 0) <= 0 and assistant_text.strip():
            response_usage["output_tokens"] = estimate_text_tokens(assistant_text)
        if int(response_usage.get("input_tokens") or 0) <= 0:
            response_usage["input_tokens"] = int(request_usage.get("input_tokens") or 0)
        if int(response_usage.get("tokens") or 0) <= 0:
            response_usage["tokens"] = int(response_usage.get("input_tokens") or 0) + int(response_usage.get("output_tokens") or 0)

        request_log_metric_peaks = collect_request_window_log_metric_peaks(
            log_watcher,
            log_stream_start_generation,
            log_stream_start_seq,
        )
        final_log_metrics = settle_runtime_log_metrics_for_container(target.get("container")) if target and target.get("container") else {}
        log_metrics = merge_runtime_metric_peaks(final_log_metrics, request_log_metric_peaks)
        ttft = round(first_chunk_at - start, 3) if first_chunk_at else None
        generation_tps = resolve_best_generation_tps(
            resolve_request_generation_tps(
                request_log_metric_peaks,
                final_log_metrics,
                log_metrics,
            ),
            authoritative_output_tokens,
            response_usage.get("output_tokens"),
            first_output_at or first_chunk_at,
            last_output_at or last_chunk_at,
        )
        first_response_at = first_output_at or first_chunk_at
        latency_preview = request_latency_seconds(
            round((first_output_at or first_chunk_at) - start, 3) if (first_output_at or first_chunk_at) else None,
            response_usage.get("input_tokens") or request_usage.get("input_tokens"),
            prompt_tps,
        )
        prompt_tps = derive_request_prompt_tps(
            response_usage.get("input_tokens") or request_usage.get("input_tokens"),
            response_usage.get("output_tokens"),
            round((first_output_at or first_chunk_at) - start, 3) if (first_output_at or first_chunk_at) else None,
            latency_preview,
            generation_tps,
            request_log_metric_peaks.get("prompt_tps"),
            final_log_metrics.get("prompt_tps"),
            log_metrics.get("prompt_tps"),
        )
        preview_update_target_request_metrics(
            target_key,
            preset_name,
            "/admin/chat-stream",
            200,
            latency_preview,
            round((first_output_at or first_chunk_at) - start, 3) if (first_output_at or first_chunk_at) else None,
            prompt_tps,
            generation_tps,
            int(response_usage.get("input_tokens") or request_usage.get("input_tokens") or 0),
            int(response_usage.get("output_tokens") or 0),
            int(response_usage.get("tokens") or 0),
            int(response_usage.get("tool_calls") or 0),
            log_metrics,
        )
        if generation_tps not in (None, "", 0, 0.0):
            record_preset_tps_sample(str(target.get("mode") or ""), generation_tps)

        done_payload = {
            "ok": True,
            "instance_id": target_id,
            "mode": str(target.get("mode") or ""),
            "model": str(current_payload.get("model") or ""),
            "usage": response_usage,
            "generation_tps": generation_tps,
            "prompt_tps": prompt_tps,
            "gpu_kv_cache_usage_pct": log_metrics.get("gpu_kv_cache_usage_pct"),
            "cpu_kv_cache_usage_pct": log_metrics.get("cpu_kv_cache_usage_pct"),
            "prefix_cache_hit_rate_pct": log_metrics.get("prefix_cache_hit_rate_pct"),
            "speculative": dict(log_metrics.get("speculative") or {}),
            "ttft_s": round((first_output_at or first_chunk_at) - start, 3) if (first_output_at or first_chunk_at) else None,
            "latency_s": latency_preview,
            "status": 200,
            "path": "/admin/chat-stream",
        }
        update_admin_chat_stream_state(
            conversation_id,
            status="done",
            instance_id=target_id,
            mode=str(target.get("mode") or ""),
            model=str(current_payload.get("model") or ""),
            assistant_text=assistant_text,
            reasoning_text=reasoning_text,
            usage=response_usage,
            generation_tps=generation_tps,
            prompt_tps=prompt_tps,
            gpu_kv_cache_usage_pct=log_metrics.get("gpu_kv_cache_usage_pct"),
            cpu_kv_cache_usage_pct=log_metrics.get("cpu_kv_cache_usage_pct"),
            prefix_cache_hit_rate_pct=log_metrics.get("prefix_cache_hit_rate_pct"),
            speculative=done_payload.get("speculative"),
            ttft_s=done_payload.get("ttft_s"),
            latency_s=latency_preview,
            message="Generation finished.",
        )
        emit_sse("done", done_payload)
        handler.close_connection = True
    except Exception as e:
        aborted_by_user = aborted_by_user or bool(re.search(r"aborted|abort", str(e), re.I))
        status_code = 499 if aborted_by_user else 500
        debug_audit(
            "chat_stream_request_error",
            incoming_instance_id=str((data or {}).get("instance_id") or ""),
            incoming_mode=str((data or {}).get("mode") or ""),
            incoming_message_count=len((data or {}).get("messages") or []) if isinstance(data, dict) else 0,
            error=str(e),
            stream_opened=bool(stream_opened),
            aborted=aborted_by_user,
        )
        update_admin_chat_stream_state(
            conversation_id,
            status="aborted" if aborted_by_user else "error",
            error=str(e) if not aborted_by_user else "",
            assistant_text=assistant_text,
            reasoning_text=locals().get("reasoning_text", ""),
            usage=response_usage,
            message="Generation aborted." if aborted_by_user else str(e),
        )
        if stream_opened:
            try:
                emit_sse("error", {"error": "Generation aborted." if aborted_by_user else str(e)})
            except Exception:
                pass
            handler.close_connection = True
        else:
            handler.send_json({"ok": False, "error": "Generation aborted." if aborted_by_user else str(e)}, 499 if aborted_by_user else 500)
    finally:
        clear_admin_chat_stream_control(conversation_id)
        if metrics_started:
            first_response_at = first_output_at or first_chunk_at
            prompt_tokens = int(response_usage.get("input_tokens") or 0) or int(request_usage.get("input_tokens") or 0)
            output_tokens = int(response_usage.get("output_tokens") or 0)
            if output_tokens <= 0:
                output_tokens = max(0, int(response_usage.get("tokens") or 0) - int(prompt_tokens))
            total_tokens = int(response_usage.get("tokens") or 0)
            if total_tokens <= 0:
                total_tokens = int(prompt_tokens) + int(output_tokens)
            request_log_metric_peaks = collect_request_window_log_metric_peaks(
                log_watcher,
                log_stream_start_generation,
                log_stream_start_seq,
            )
            log_metrics = merge_runtime_metric_peaks(final_log_metrics, request_log_metric_peaks)
            if not log_metrics and target and target.get("container"):
                log_metrics = merge_runtime_metric_peaks(
                    settle_runtime_log_metrics_for_container(target.get("container")),
                    request_log_metric_peaks,
                )
            ttft = round((first_output_at or first_chunk_at) - start, 3) if (first_output_at or first_chunk_at) else None
            estimated_generation_tps = (
                estimate_generation_tps_from_stream(
                    authoritative_output_tokens or output_tokens,
                    first_output_at or first_chunk_at,
                    last_output_at or last_chunk_at,
                )
                if authoritative_output_tokens
                else None
            )
            display_tps = resolve_best_generation_tps(
                resolve_request_generation_tps(
                    request_log_metric_peaks,
                    final_log_metrics,
                    log_metrics,
                ),
                authoritative_output_tokens,
                output_tokens,
                first_output_at or first_chunk_at,
                last_output_at or last_chunk_at,
            )
            prompt_tps_final = derive_request_prompt_tps(
                prompt_tokens,
                output_tokens,
                ttft,
                round(max(0.0, float(backend_stream_opened_at) - float(start)), 3)
                if backend_stream_opened_at is not None
                else None,
                display_tps,
                request_log_metric_peaks.get("prompt_tps"),
                final_log_metrics.get("prompt_tps"),
                log_metrics.get("prompt_tps"),
            )
            latency = request_latency_seconds(
                ttft,
                prompt_tokens,
                prompt_tps_final,
            )
            with metrics_lock:
                metrics["active_requests"] = max(0, metrics["active_requests"] - 1)
                if metrics["active_requests"] <= 0:
                    last_request_finished_at = time.time()
                metrics["completed_requests"] += 1
                if status_code >= 400:
                    metrics["failed_requests"] += 1
                metrics["last_latency_s"] = latency
                metrics["last_status"] = status_code
                if ttft is not None:
                    metrics["last_ttft_s"] = ttft
                if display_tps not in (None, "", 0, 0.0):
                    metrics["last_tokens_per_second"] = display_tps
                metrics["last_estimated_tokens"] = output_tokens or None
                recent_requests.appendleft({
                    "time": time.strftime("%H:%M:%S"),
                    "status": status_code,
                    "latency_s": latency,
                    "preset": preset_name,
                    "path": "/admin/chat-stream",
                    "upstream": "/v1/chat/completions",
                    "instance": target_id,
                    "user": "admin",
                })
                target_row = dict(target_request_metrics.get(target_key) or default_target_request_metrics())
                target_row["last_status"] = status_code
                target_row["last_latency_s"] = latency
                if ttft is not None:
                    target_row["last_ttft_s"] = ttft
                target_row["last_prompt_tps"] = prompt_tps_final
                if display_tps not in (None, "", 0, 0.0):
                    target_row["last_tokens_per_second"] = display_tps
                target_row["last_gpu_kv_cache_usage_pct"] = log_metrics.get("gpu_kv_cache_usage_pct")
                target_row["last_cpu_kv_cache_usage_pct"] = log_metrics.get("cpu_kv_cache_usage_pct")
                target_row["last_prefix_cache_hit_rate_pct"] = log_metrics.get("prefix_cache_hit_rate_pct")
                target_row["last_estimated_tokens"] = output_tokens or None
                target_row["last_input_tokens"] = prompt_tokens
                target_row["last_output_tokens"] = output_tokens
                target_row["last_total_tokens"] = total_tokens
                target_row["last_tool_calls"] = int(response_usage.get("tool_calls") or 0)
                target_row["last_preset"] = preset_name
                target_row["last_path"] = "/admin/chat-stream"
                target_row["last_request_at"] = int(time.time())
                target_request_metrics[target_key] = target_row


def run_admin_chat_request(data):
    data = data if isinstance(data, dict) else {}
    target, spec = resolve_admin_chat_target(
        instance_id=data.get("instance_id") or "",
        mode=data.get("mode") or "",
    )
    ensure_vllm_running_for_request(target.get("id") if target else None)
    port = int(target.get("port") or active_port() or 0)
    if port <= 0:
        raise RuntimeError("The selected runtime does not expose a valid port.")
    payload = build_admin_chat_payload(data, spec)
    tools, tool_map = build_enabled_mcp_tools()
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    parsed = {}
    for _ in range(6):
        parsed = chat_backend_request(port, payload)
        choice = (parsed.get("choices") or [{}])[0] if isinstance(parsed, dict) else {}
        message = choice.get("message") if isinstance(choice, dict) else {}
        tool_calls = list(message.get("tool_calls") or []) if isinstance(message, dict) else []
        if not tool_calls:
            break
        payload_messages = list(payload.get("messages") or [])
        assistant_message = {
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": tool_calls,
        }
        reasoning_text = extract_reasoning_text(message)
        if reasoning_text:
            assistant_message["reasoning_content"] = reasoning_text
        payload_messages.append(assistant_message)
        for tool_call in tool_calls:
            call_id = str(tool_call.get("id") or secrets.token_hex(6))
            function = dict(tool_call.get("function") or {})
            tool_name = str(function.get("name") or "")
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except Exception:
                arguments = {}
            tool_result = call_enabled_mcp_tool(tool_name, arguments, tool_map)
            payload_messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": tool_result,
            })
        payload["messages"] = payload_messages
    usage = extract_response_usage(json.dumps(parsed, separators=(",", ":")).encode("utf-8"))
    return {
        "ok": True,
        "instance_id": str(target.get("id") or ""),
        "mode": str(target.get("mode") or ""),
        "model": str(payload.get("model") or ""),
        "engine": str(spec.get("engine") or ""),
        "supports_vision": runtime_supports_vision(spec),
        "tools_enabled": len(tools),
        "response": parsed,
        "usage": usage,
    }


def preview_update_target_request_metrics(target_key, preset_name, path, status_code, latency, ttft, prompt_tps, generation_tps, prompt_tokens, output_tokens, total_tokens, tool_calls, log_metrics):
    with metrics_lock:
        metrics["last_latency_s"] = latency
        metrics["last_status"] = status_code
        if ttft is not None:
            metrics["last_ttft_s"] = ttft
        if generation_tps not in (None, "", 0, 0.0):
            metrics["last_tokens_per_second"] = generation_tps
        metrics["last_estimated_tokens"] = output_tokens or None
        target_row = dict(target_request_metrics.get(target_key) or default_target_request_metrics())
        target_row["last_status"] = status_code
        target_row["last_latency_s"] = latency
        if ttft is not None:
            target_row["last_ttft_s"] = ttft
        target_row["last_prompt_tps"] = prompt_tps
        if generation_tps not in (None, "", 0, 0.0):
            target_row["last_tokens_per_second"] = generation_tps
        target_row["last_gpu_kv_cache_usage_pct"] = log_metrics.get("gpu_kv_cache_usage_pct")
        target_row["last_cpu_kv_cache_usage_pct"] = log_metrics.get("cpu_kv_cache_usage_pct")
        target_row["last_prefix_cache_hit_rate_pct"] = log_metrics.get("prefix_cache_hit_rate_pct")
        target_row["last_speculative"] = dict(log_metrics.get("speculative") or {})
        target_row["last_estimated_tokens"] = output_tokens or None
        target_row["last_input_tokens"] = prompt_tokens
        target_row["last_output_tokens"] = output_tokens
        target_row["last_total_tokens"] = total_tokens
        target_row["last_tool_calls"] = tool_calls
        target_row["last_preset"] = preset_name
        target_row["last_path"] = path
        target_row["last_request_at"] = int(time.time())
        target_request_metrics[target_key] = target_row

HTML_GZIP_BASE64 = ""  # Injected by build.py for shipped outputs.
_admin_html_cache = None


def get_admin_html_template():
    global _admin_html_cache
    if _admin_html_cache is not None:
        return _admin_html_cache
    payload = str(HTML_GZIP_BASE64 or "").strip()
    if payload:
        try:
            _admin_html_cache = gzip.decompress(base64.b64decode(payload.encode("ascii"))).decode("utf-8")
            return _admin_html_cache
        except Exception:
            pass
    _admin_html_cache = ""
    return _admin_html_cache
