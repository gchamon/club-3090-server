def _service_display_name(service_id):
    mapping = {
        "openwebui": "Open WebUI",
        "litellm": "LiteLLM",
        "ollama": "Ollama",
        "qdrant": "Qdrant",
        "searxng": "SearxNG",
        "comfyui": "ComfyUI",
    }
    text = str(service_id or "").strip().lower()
    return mapping.get(text, str(service_id or "").replace("-", " ") or "Service")


def discover_upstream_services(force=False, max_age=30.0):
    now = time.time()
    with slow_cache_lock:
        cached = upstream_services_cache.get("value") or []
        cached_at = float(upstream_services_cache.get("time") or 0.0)
    if cached and not force and now - cached_at < max(5.0, float(max_age or 30.0)):
        return [dict(item) for item in cached]

    services_root = os.path.join(CLUB3090_DIR, "services")
    compose_paths = sorted(glob.glob(os.path.join(services_root, "*", "docker-compose.yml")))
    running_names = set(docker_names(all_containers=False, force=force, max_age=2.0, timeout=3))
    all_names = set(docker_names(all_containers=True, force=force, max_age=2.0, timeout=3))
    rows = []
    for compose_abs_path in compose_paths:
        service_id = os.path.basename(os.path.dirname(compose_abs_path))
        runtime_meta = _read_compose_runtime_metadata(compose_abs_path)
        container_name = str(runtime_meta.get("container_name") or service_id).strip()
        service_name = str(runtime_meta.get("service_name") or service_id).strip()
        default_port = int(runtime_meta.get("default_port") or 0)
        inspect_name = container_name if container_name in all_names else (service_name if service_name in all_names else "")
        state = _docker_inspect_state(inspect_name) if inspect_name else {"exists": False, "running": False, "exit_code": None, "status": ""}
        is_running = bool(state.get("running")) or container_name in running_names or service_name in running_names
        if is_running:
            if default_port > 0:
                health_status = "healthy" if port_open(default_port, timeout=0.3) else "unreachable"
            else:
                health_status = "running"
        else:
            health_status = "stopped"
        rows.append(
            {
                "id": service_id,
                "display_name": _service_display_name(service_id),
                "compose_abs_path": compose_abs_path,
                "compose_rel_path": os.path.relpath(compose_abs_path, CLUB3090_DIR).replace("\\", "/"),
                "service_name": service_name,
                "container_name": container_name,
                "default_port": default_port,
                "exists": bool(state.get("exists")),
                "running": is_running,
                "status": str(state.get("status") or ("running" if is_running else "stopped")),
                "health_status": health_status,
                "exit_code": state.get("exit_code"),
                "kind": "aux_service",
            }
        )
    with slow_cache_lock:
        upstream_services_cache["value"] = [dict(item) for item in rows]
        upstream_services_cache["time"] = time.time()
    return rows


def invalidate_upstream_services_cache():
    with slow_cache_lock:
        upstream_services_cache["value"] = []
        upstream_services_cache["time"] = 0.0


def resolve_upstream_service(service_id, force=False):
    wanted = str(service_id or "").strip().lower()
    if not wanted:
        return {}
    for row in discover_upstream_services(force=force, max_age=0.0 if force else 30.0):
        if str(row.get("id") or "").strip().lower() == wanted:
            return dict(row)
    return {}


def run_upstream_service_action(service_id, action):
    service = resolve_upstream_service(service_id, force=True)
    if not service:
        raise ValueError(f"Unknown upstream service: {service_id}")
    action_name = str(action or "").strip().lower()
    if action_name not in {"start", "stop", "restart"}:
        raise ValueError("Invalid upstream service action")
    compose_file = str(service.get("compose_abs_path") or "").strip()
    service_name = str(service.get("service_name") or "").strip() or str(service.get("id") or "").strip()
    compose_dir = os.path.dirname(compose_file) or CLUB3090_DIR
    args = compose_cmd() + ["--project-directory", compose_dir, "-f", compose_file]
    if action_name == "start":
        cmd = args + ["up", "-d", service_name]
        timeout = 1800
    elif action_name == "stop":
        cmd = args + ["stop", service_name]
        timeout = 600
    else:
        cmd = args + ["restart", service_name]
        timeout = 900
    env = _repo_subprocess_env()
    env["COMPOSE_BIN"] = COMPOSE_BIN
    rc, out = run_cmd(cmd, timeout=timeout, cwd=compose_dir, env=env)
    invalidate_upstream_services_cache()
    refreshed = resolve_upstream_service(service_id, force=True)
    if rc != 0:
        raise RuntimeError((out or f"{action_name} failed for {service_name}")[-12000:])
    log_audit(
        "admin_upstream_service",
        service=service_id,
        action=action_name,
        compose=str(service.get("compose_rel_path") or ""),
        port=int(service.get("default_port") or 0),
    )
    return {
        "service": refreshed or service,
        "action": action_name,
        "output": str(out or "")[-12000:],
    }


def canonical_mode_selector(mode):
    spec = VARIANT_SPECS.get(str(mode or "").strip()) or VARIANT_BY_TAG.get(str(mode or "").strip())
    return str((spec or {}).get("selector") or mode or "").strip()


def resolve_variant_spec(mode):
    selector = str(mode or "").strip()
    if not selector:
        return None
    if not VARIANT_SPECS:
        load_runtime_inventory()
    return VARIANT_SPECS.get(selector) or VARIANT_BY_TAG.get(selector) or VARIANT_BY_ID.get(selector) or VARIANT_BY_COMPOSE.get(selector.replace("\\", "/"))


def default_single_mode_selector():
    load_runtime_inventory()
    if DEFAULT_MODE in SINGLE_GPU_MODES:
        return canonical_mode_selector(DEFAULT_MODE)
    variant = _choose_fallback_variant("single", preferred_model_id="qwen3.6-27b", category="single")
    if variant:
        return _mode_selector_for_variant(variant)
    return SINGLE_GPU_MODES[0] if SINGLE_GPU_MODES else canonical_mode_selector(DEFAULT_MODE or "vllm/default")


def default_dual_mode_selector():
    load_runtime_inventory()
    if DEFAULT_MODE in DUAL_GPU_MODES:
        return canonical_mode_selector(DEFAULT_MODE)
    for candidate in ("vllm/dual-dflash", "vllm/dual"):
        selector = canonical_mode_selector(candidate)
        if resolve_variant_spec(selector):
            return selector
    variant = _choose_fallback_variant("dual", preferred_model_id="qwen3.6-27b", category="dual")
    if variant:
        return _mode_selector_for_variant(variant)
    return DUAL_GPU_MODES[0] if DUAL_GPU_MODES else canonical_mode_selector(DEFAULT_MODE or "vllm/dual")


def default_server_config():
    return {
        "allow_proxy_without_api_key": True,
        "online_enabled": False,
        "upnp_enabled": False,
        "https_enabled": False,
        "https_cert_file": HTTPS_CERT_FILE,
        "https_key_file": HTTPS_KEY_FILE,
        "admin_path": "/admin",
        "local_api_enabled": False,
        "local_api_port": LOCAL_API_PORT,
        "selected_preset_model": "",
        "hidden_preset_selectors": [],
        "active_power_profile": current_profile,
        "preset_launch_overrides": {},
        "mcp_servers": [],
    }


def sanitize_preset_launch_overrides(rows):
    clean = {}
    if not isinstance(rows, dict):
        return clean
    protected = {
        "MODEL_DIR",
        "PORT",
        "BIND_HOST",
        "ESTATE_PORT",
        "ESTATE_GPUS",
        "ESTATE_CONTAINER",
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "CLUB3090_GPU",
    }
    for selector, raw_entry in rows.items():
        selector_text = str(selector or "").strip()
        if not selector_text or not isinstance(raw_entry, dict):
            continue
        env = {}
        for key, value in (raw_entry.get("env") or {}).items():
            env_key = str(key or "").strip().upper()
            if not env_key or not re.fullmatch(r"[A-Z][A-Z0-9_]*", env_key):
                continue
            if env_key in protected:
                continue
            env_value = str(value or "").strip()
            if not env_value:
                continue
            env[env_key] = env_value
        entry = {"env": env}
        command_text = str(raw_entry.get("command_text") or "").replace("\r", "").strip()
        if command_text:
            entry["command_text"] = command_text
        clean[selector_text] = entry
    return clean


def sanitize_mcp_servers(rows):
    normalized = []
    seen = set()
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        server_id = str(raw.get("id") or "").strip() or secrets.token_hex(6)
        if server_id in seen:
            continue
        seen.add(server_id)
        command = str(raw.get("command") or "").strip()
        if not command:
            continue
        normalized.append({
            "id": server_id,
            "name": str(raw.get("name") or server_id).strip() or server_id,
            "command": command,
            "enabled": bool(raw.get("enabled", True)),
        })
    return normalized


def sanitize_hidden_preset_selectors(rows):
    clean = []
    seen = set()
    for raw in rows if isinstance(rows, list) else []:
        selector = str(raw or "").strip()
        if not selector or selector in seen:
            continue
        seen.add(selector)
        clean.append(selector)
    return clean


def mcp_server_transport(server_row):
    command = str((server_row or {}).get("command") or "").strip()
    return "http" if re.match(r"^https?://", command, re.I) else "stdio"


def mcp_server_endpoint(server_row):
    command = str((server_row or {}).get("command") or "").strip()
    return command if mcp_server_transport(server_row) == "http" else ""


def read_server_config():
    data = read_json_file(SERVER_CONFIG_FILE, {})
    if not isinstance(data, dict):
        data = {}
    merged = default_server_config()
    for key in merged:
        if key in data:
            merged[key] = data[key]
    merged["allow_proxy_without_api_key"] = bool(merged.get("allow_proxy_without_api_key", True))
    merged["online_enabled"] = bool(merged.get("online_enabled", False))
    merged["upnp_enabled"] = bool(merged.get("upnp_enabled", False))
    merged["https_enabled"] = bool(merged.get("https_enabled", False))
    merged["local_api_enabled"] = bool(merged.get("local_api_enabled", False))
    try:
        merged["local_api_port"] = int(merged.get("local_api_port", LOCAL_API_PORT))
    except Exception:
        merged["local_api_port"] = LOCAL_API_PORT
    merged["https_cert_file"] = str(merged.get("https_cert_file") or HTTPS_CERT_FILE)
    merged["https_key_file"] = str(merged.get("https_key_file") or HTTPS_KEY_FILE)
    merged["admin_path"] = "/admin"
    merged["selected_preset_model"] = str(data.get("selected_preset_model") or "").strip()
    merged["hidden_preset_selectors"] = sanitize_hidden_preset_selectors(data.get("hidden_preset_selectors") or [])
    merged["active_power_profile"] = str(data.get("active_power_profile") or current_profile or "balanced").strip().lower()
    if merged["active_power_profile"] not in PERFORMANCE_PROFILES:
        merged["active_power_profile"] = "balanced"
    merged["preset_launch_overrides"] = sanitize_preset_launch_overrides(data.get("preset_launch_overrides") or {})
    merged["mcp_servers"] = sanitize_mcp_servers(data.get("mcp_servers") or [])
    return merged


def write_server_config(data):
    current = read_server_config()
    original = dict(current)
    for key in ("allow_proxy_without_api_key", "online_enabled", "upnp_enabled", "https_enabled", "local_api_enabled"):
        if key in data:
            current[key] = bool(data[key])
    if "local_api_port" in data:
        try:
            current["local_api_port"] = int(data["local_api_port"])
        except Exception:
            pass
    for key in ("https_cert_file", "https_key_file"):
        if key in data and data[key]:
            current[key] = str(data[key])
    if "selected_preset_model" in data:
        current["selected_preset_model"] = str(data.get("selected_preset_model") or "").strip()
    if "hidden_preset_selectors" in data:
        current["hidden_preset_selectors"] = sanitize_hidden_preset_selectors(data.get("hidden_preset_selectors") or [])
    if "active_power_profile" in data:
        next_profile = str(data.get("active_power_profile") or "").strip().lower()
        if next_profile in PERFORMANCE_PROFILES:
            current["active_power_profile"] = next_profile
    if "preset_launch_overrides" in data:
        current["preset_launch_overrides"] = sanitize_preset_launch_overrides(data.get("preset_launch_overrides") or {})
    if "mcp_servers" in data:
        current["mcp_servers"] = sanitize_mcp_servers(data.get("mcp_servers") or [])
    current["admin_path"] = "/admin"
    if current != original:
        write_json_file(SERVER_CONFIG_FILE, current)
    return current


def preset_launch_env_overrides(spec):
    row = spec if isinstance(spec, dict) else {}
    selector = str(
        row.get("selector")
        or row.get("upstream_tag")
        or row.get("registry_key")
        or row.get("variant_id")
        or ""
    ).strip()
    if not selector:
        return {}
    overrides = read_server_config().get("preset_launch_overrides") or {}
    env = dict((overrides.get(selector) or {}).get("env") or {})
    return {
        str(key): str(value)
        for key, value in env.items()
        if str(key or "").strip() and str(value or "").strip()
    }


def preset_launch_command_override(spec):
    row = spec if isinstance(spec, dict) else {}
    selector = str(
        row.get("selector")
        or row.get("upstream_tag")
        or row.get("registry_key")
        or row.get("variant_id")
        or ""
    ).strip()
    if not selector:
        return ""
    overrides = read_server_config().get("preset_launch_overrides") or {}
    command_text = str((overrides.get(selector) or {}).get("command_text") or "").replace("\r", "").strip()
    return command_text
