def compose_cmd():
    try:
        return shlex.split(COMPOSE_BIN)
    except Exception:
        return ["docker", "compose"]

def detect_gpu_count_runtime(force=False, max_age=15):
    now = time.time()
    with slow_cache_lock:
        cached_value = int(gpu_count_cache.get("value") or 0)
        cached_time = float(gpu_count_cache.get("time") or 0.0)
    if not force and cached_time and now - cached_time < max(1.0, float(max_age or 15)):
        return cached_value
    if not shutil.which("nvidia-smi"):
        return cached_value
    value = cached_value
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=index", "--format=csv,noheader,nounits"], text=True, stderr=subprocess.DEVNULL, timeout=1.5)
        value = sum(1 for line in out.splitlines() if line.strip())
    except Exception:
        try:
            out = subprocess.check_output(["nvidia-smi", "-L"], text=True, stderr=subprocess.DEVNULL, timeout=1.5)
            value = sum(1 for line in out.splitlines() if line.strip().startswith("GPU "))
        except Exception:
            return cached_value
    with slow_cache_lock:
        gpu_count_cache["value"] = int(value)
        gpu_count_cache["time"] = time.time()
    return int(value)

def gpu_pairing_default_enabled(gpu_count=None):
    try:
        count = int(gpu_count if gpu_count is not None else detect_gpu_count_runtime())
    except Exception:
        count = 0
    return count >= 2


def sequential_global_gpu_pairs(gpu_count=None):
    try:
        count = int(gpu_count if gpu_count is not None else detect_gpu_count_runtime())
    except Exception:
        count = 0
    pairs = []
    for first in range(0, max(count - 1, 0), 2):
        second = first + 1
        if second < count:
            pairs.append([first, second])
    return pairs

def default_instances_config():
    load_runtime_inventory()
    count = detect_gpu_count_runtime()
    rows = []
    single_mode = default_single_mode_selector()
    dual_mode = default_dual_mode_selector()
    for gpu_idx in range(count):
        rows.append({
            "id": f"GPU{gpu_idx}",
            "kind": "single",
            "gpu_indices": [gpu_idx],
            "mode": single_mode,
            "enabled": gpu_idx == 0 and single_mode in SINGLE_GPU_MODES,
            "port": INSTANCE_PORT_BASE + gpu_idx,
        })
    if gpu_pairing_default_enabled(gpu_count=count):
        for pair in sequential_global_gpu_pairs(count):
            rows.append({
                "id": pair_instance_id(pair),
                "kind": "dual",
                "gpu_indices": pair,
                "mode": dual_mode,
                "enabled": False,
                "auto_pair": True,
                "port": instance_default_port("dual", pair),
            })
    return rows

def normalize_pair_indices(value):
    if not isinstance(value, (list, tuple)):
        return None
    try:
        items = sorted({int(x) for x in value})
    except Exception:
        return None
    if len(items) != 2 or any(x < 0 for x in items):
        return None
    return items

def pair_instance_id(indices):
    pair = normalize_pair_indices(indices)
    if not pair:
        raise ValueError("Dual preset pairs must contain exactly two distinct GPU indices")
    return f"PAIR{pair[0]}_{pair[1]}"


def is_auto_pair_indices(indices, gpu_count=None):
    pair = normalize_pair_indices(indices)
    if not pair:
        return False
    return pair in sequential_global_gpu_pairs(gpu_count=gpu_count)

def parse_instance_identifier(instance_id):
    raw = str(instance_id or "").strip().upper()
    if re.fullmatch(r"GPU[0-9]+", raw):
        idx = int(raw[3:])
        return {"id": raw, "kind": "single", "gpu_indices": [idx], "gpu_index": idx}
    match = re.fullmatch(r"PAIR([0-9]+)_([0-9]+)", raw)
    if match:
        pair = normalize_pair_indices([int(match.group(1)), int(match.group(2))])
        if not pair:
            return None
        return {"id": pair_instance_id(pair), "kind": "dual", "gpu_indices": pair, "gpu_index": pair[0]}
    return None

def instance_default_port(kind, gpu_indices):
    if kind == "dual":
        pair = normalize_pair_indices(gpu_indices)
        if not pair:
            return PAIR_INSTANCE_PORT_BASE
        return PAIR_INSTANCE_PORT_BASE + (pair[0] * 100) + pair[1]
    idx = int((gpu_indices or [0])[0])
    return INSTANCE_PORT_BASE + idx

def normalize_instance(raw, used_ids=None, used_ports=None, substitutions=None):
    load_runtime_inventory()
    used_ids = used_ids if isinstance(used_ids, set) else set()
    used_ports = used_ports if isinstance(used_ports, set) else set()
    substitutions = substitutions if isinstance(substitutions, list) else None
    if not isinstance(raw, dict):
        return None
    parsed = parse_instance_identifier(raw.get("id"))
    if not parsed:
        gpu_indices = normalize_pair_indices(raw.get("gpu_indices"))
        if gpu_indices:
            parsed = parse_instance_identifier(pair_instance_id(gpu_indices))
        elif raw.get("gpu_index") not in ("", None, False):
            try:
                parsed = parse_instance_identifier(f"GPU{int(raw.get('gpu_index'))}")
            except Exception:
                parsed = None
    if not parsed:
        return None
    instance_id = parsed["id"]
    kind = parsed["kind"]
    gpu_indices = list(parsed["gpu_indices"])
    gpu_index = int(gpu_indices[0])
    raw_mode = str(raw.get("mode") or (default_dual_mode_selector() if kind == "dual" else default_single_mode_selector())).strip()
    mode = canonical_mode_selector(raw_mode)
    valid_modes = DUAL_GPU_MODES if kind == "dual" else SINGLE_GPU_MODES
    if mode not in valid_modes or not resolve_variant_spec(mode):
        preferred_model = ""
        preferred_spec = resolve_variant_spec(raw_mode)
        if preferred_spec:
            preferred_model = str(preferred_spec.get("model_id") or "")
        fallback_variant = _choose_fallback_variant(kind, preferred_model_id=preferred_model, category=("dual" if kind == "dual" else "single"))
        fallback_mode = _mode_selector_for_variant(fallback_variant) if fallback_variant else (default_dual_mode_selector() if kind == "dual" else default_single_mode_selector())
        if substitutions is not None and raw_mode and raw_mode != fallback_mode:
            substitutions.append({
                "instance_id": instance_id,
                "from_mode": raw_mode,
                "to_mode": fallback_mode,
            })
        mode = fallback_mode
    try:
        port = int(raw.get("port"))
    except Exception:
        port = instance_default_port(kind, gpu_indices)
    if port < 1024:
        port = instance_default_port(kind, gpu_indices)
    if instance_id in used_ids:
        return None
    if port in used_ports:
        port = instance_default_port(kind, gpu_indices)
        while port in used_ports:
            port += 1
    used_ids.add(instance_id)
    used_ports.add(port)
    auto_pair = False
    if kind == "dual":
        auto_pair = bool(raw.get("auto_pair")) or is_auto_pair_indices(gpu_indices)
    return {
        "id": instance_id,
        "kind": kind,
        "gpu_indices": gpu_indices,
        "gpu_index": gpu_index,
        "mode": mode,
        "enabled": bool(raw.get("enabled", False)),
        "auto_pair": auto_pair,
        "port": port,
    }

def normalize_instances(rows, substitutions=None):
    if not isinstance(rows, list):
        rows = []
    used_ids = set()
    used_ports = set()
    clean = []
    for row in rows:
        inst = normalize_instance(row, used_ids, used_ports, substitutions=substitutions)
        if inst is not None:
            clean.append(inst)
    count = detect_gpu_count_runtime()
    existing_ids = {inst["id"] for inst in clean}
    for gpu_idx in range(count):
        iid = f"GPU{gpu_idx}"
        if iid in existing_ids:
            continue
        inst = normalize_instance({"id": iid, "kind": "single", "gpu_indices": [gpu_idx], "mode": default_single_mode_selector(), "enabled": False, "port": INSTANCE_PORT_BASE + gpu_idx}, used_ids, used_ports, substitutions=substitutions)
        if inst is not None:
            clean.append(inst)
            existing_ids.add(inst["id"])
    if gpu_pairing_default_enabled(gpu_count=count):
        default_dual_mode = default_dual_mode_selector()
        for pair in sequential_global_gpu_pairs(count):
            pair_id = pair_instance_id(pair)
            if pair_id in existing_ids:
                continue
            inst = normalize_instance({
                "id": pair_id,
                "kind": "dual",
                "gpu_indices": pair,
                "mode": default_dual_mode,
                "enabled": False,
                "auto_pair": True,
                "port": instance_default_port("dual", pair),
            }, used_ids, used_ports, substitutions=substitutions)
            if inst is not None:
                clean.append(inst)
                existing_ids.add(inst["id"])
    if not clean:
        clean = default_instances_config()
    clean.sort(key=lambda d: (d.get("gpu_index", 9999), d.get("kind") == "dual", d.get("id", "")))
    return clean

def read_instances_config():
    load_runtime_inventory()
    substitutions = []
    try:
        with open(INSTANCES_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        rows = normalize_instances(data, substitutions=substitutions)
    except Exception:
        rows = normalize_instances([], substitutions=substitutions)
    changed = bool(substitutions)
    if changed or not os.path.exists(INSTANCES_CONFIG_FILE):
        write_instances_config(rows)
    for item in substitutions:
        log_audit(
            "instance_mode_substituted",
            instance=item.get("instance_id"),
            from_mode=item.get("from_mode"),
            to_mode=item.get("to_mode"),
        )
    return rows

def write_instances_config(rows):
    rows = normalize_instances(rows)
    write_json_atomic_if_changed(INSTANCES_CONFIG_FILE, rows, indent=2)
    return rows

def instance_container_name(instance):
    return f"club3090-{instance['id'].lower()}-{instance['mode'].replace('/', '-')}"

def instance_project_name(instance):
    return f"club3090-{instance['id'].lower()}"

def instance_paths(instance):
    base = os.path.join(INSTANCES_DIR, instance["id"])
    return {
        "dir": base,
        "env": os.path.join(base, ".env"),
        "override": os.path.join(base, "docker-compose.override.generated.yml"),
    }

def get_instance(instance_id):
    iid = str(instance_id or "").strip().upper()
    for inst in read_instances_config():
        if inst["id"] == iid:
            return inst
    return None

def instance_ready_url(instance):
    return f"http://127.0.0.1:{int(instance['port'])}/v1/models"

def instance_variant_spec(instance):
    spec = resolve_variant_spec(instance["mode"])
    if not spec:
        raise ValueError(f"Unsupported instance mode: {instance['mode']}")
    return spec

def pr35936_compat_install_wrapper_path():
    path = os.path.join(CONTROL_DIR, "compat", "install-pr35936-compat.sh")
    text = """#!/usr/bin/env bash
set -euo pipefail
UPSTREAM_INSTALL=/etc/club3090/install-pr35936-upstream.sh
if [ ! -r "$UPSTREAM_INSTALL" ]; then
  echo "[club3090/pr35936] upstream overlay installer absent; skipping" >&2
  exit 0
fi
if /usr/bin/python3 - <<'PY_CHECK'
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("vllm.beam_search") else 1)
PY_CHECK
then
  exec bash "$UPSTREAM_INSTALL" "$@"
else
  echo "[club3090/pr35936] beam_search module absent; overlay already obsolete for this vLLM image, skipping" >&2
  exit 0
fi
"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_text_atomic_if_changed(path, text)
    try:
        os.chmod(path, 0o755)
    except Exception:
        pass
    return path

def instance_patch_bind_overrides(spec):
    runtime_root = variant_runtime_root_dir(spec)
    if not runtime_root:
        return []
    bindings = []
    rel_specs = [
        (
            os.path.join("patches", "genesis", "vllm", "_genesis"),
            "/usr/local/lib/python3.12/dist-packages/vllm/_genesis",
            True,
        ),
        (
            os.path.join("patches", "local", "qwen3coder_tool_parser_deferred_commit.py"),
            "/patches/qwen3coder_tool_parser_deferred_commit.py",
            False,
        ),
        (
            os.path.join("patches", "vllm-pr35936-required-fallback", "vllm", "entrypoints", "openai", "chat_completion", "serving.py"),
            "/etc/club3090/pr35936-chat-completion-serving.py",
            False,
        ),
        (
            os.path.join("patches", "vllm-pr35936-required-fallback", "vllm", "entrypoints", "openai", "engine", "serving.py"),
            "/etc/club3090/pr35936-engine-serving.py",
            False,
        ),
        (
            os.path.join("patches", "vllm-pr35936-required-fallback", "install.sh"),
            "/etc/club3090/install-pr35936-upstream.sh",
            False,
        ),
        (
            os.path.join("patches", "vllm-pr41800-truncate-prompt-tokens", "install.sh"),
            "/etc/club3090/install-pr41800.sh",
            False,
        ),
        (
            os.path.join("patches", "froggeric-chat-template", "chat_template.jinja"),
            "/etc/qwen-froggeric-chat-template.jinja",
            False,
        ),
    ]
    fallback_sources = {
        os.path.join("patches", "froggeric-chat-template", "chat_template.jinja"): os.path.join(
            CLUB3090_DIR,
            "models",
            "qwen3.6-27b",
            "vllm",
            "patches",
            "froggeric-chat-template",
            "chat_template.jinja",
        ),
    }
    for rel_path, target, is_dir in rel_specs:
        source = os.path.normpath(os.path.join(runtime_root, rel_path))
        exists = os.path.isdir(source) if is_dir else os.path.isfile(source)
        if not exists and rel_path in fallback_sources:
            fallback_source = os.path.normpath(fallback_sources[rel_path])
            exists = os.path.isdir(fallback_source) if is_dir else os.path.isfile(fallback_source)
            if exists:
                source = fallback_source
        if exists:
            bindings.append((source, target))
    bindings.append((pr35936_compat_install_wrapper_path(), "/etc/club3090/install-pr35936.sh"))
    return bindings


def instance_host_visible_devices(instance):
    return ",".join(str(int(idx)) for idx in (instance.get("gpu_indices") or [instance["gpu_index"]]))


def instance_container_cuda_visible_devices(instance):
    indices = list(instance.get("gpu_indices") or [instance["gpu_index"]])
    if not indices:
        return "0"
    return ",".join(str(idx) for idx in range(len(indices)))

def write_instance_artifacts(instance):
    spec = instance_variant_spec(instance)
    paths = instance_paths(instance)
    os.makedirs(paths["dir"], exist_ok=True)
    visible_devices = instance_host_visible_devices(instance)
    container_cuda_visible_devices = instance_container_cuda_visible_devices(instance)
    cache_root = os.path.join(paths["dir"], "cache")
    ensure_vllm_runtime_cache_dirs(cache_root)
    patch_bindings = instance_patch_bind_overrides(spec)
    repo_env = _load_repo_env_map()
    launch_env = resolve_variant_launch_env(spec)
    with open(paths["env"], "w", encoding="utf-8") as f:
        for key in sorted(repo_env):
            if key in {"PORT", "CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "MODEL_DIR", "CLUB3090_GPU"}:
                continue
            value = str(repo_env.get(key) or "").replace("\r", " ").replace("\n", " ")
            f.write(f"{key}={value}\n")
        for key in sorted(launch_env):
            value = str(launch_env.get(key) or "").replace("\r", " ").replace("\n", " ")
            f.write(f"{key}={value}\n")
        f.write(f"MODEL_DIR={_resolve_variant_model_dir_root(spec)}\n")
        f.write(f"PORT={int(instance['port'])}\n")
        f.write(f"ESTATE_GPUS={visible_devices}\n")
        f.write(f"CUDA_VISIBLE_DEVICES={visible_devices}\n")
        f.write(f"NVIDIA_VISIBLE_DEVICES={visible_devices}\n")
    override = (
        "services:\n"
        f"  {spec['service_name']}:\n"
        f"    container_name: {instance_container_name(instance)}\n"
        "    environment:\n"
        f"      ESTATE_GPUS: \"{visible_devices}\"\n"
        f"      CUDA_VISIBLE_DEVICES: \"{container_cuda_visible_devices}\"\n"
        f"      NVIDIA_VISIBLE_DEVICES: \"{container_cuda_visible_devices}\"\n"
        f"      VLLM_CACHE_ROOT: {INSTANCE_VLLM_CACHE_CONTAINER_ROOT}/vllm\n"
        f"      TORCHINDUCTOR_CACHE_DIR: {INSTANCE_VLLM_CACHE_CONTAINER_ROOT}/torchinductor\n"
        f"      TRITON_CACHE_DIR: {INSTANCE_VLLM_CACHE_CONTAINER_ROOT}/triton\n"
        "    volumes:\n"
        f"      - {cache_root}:{INSTANCE_VLLM_CACHE_CONTAINER_ROOT}\n"
    )
    for source, target in patch_bindings:
        override += f"      - {source}:{target}:ro\n"
    override += (
        "    labels:\n"
        f"      club3090.instance_id: \"{instance['id']}\"\n"
        f"      club3090.kind: \"{instance['kind']}\"\n"
        f"      club3090.mode: \"{canonical_mode_selector(instance['mode'])}\"\n"
        f"      club3090.mode_selector: \"{canonical_mode_selector(instance['mode'])}\"\n"
        f"      club3090.variant_id: \"{spec['variant_id']}\"\n"
        f"      club3090.model_id: \"{spec['model_id']}\"\n"
        f"      club3090.gpu_indices: \"{','.join(str(int(idx)) for idx in instance.get('gpu_indices') or [instance['gpu_index']])}\"\n"
    )
    with open(paths["override"], "w", encoding="utf-8") as f:
        f.write(override)
    return paths


def ensure_instance_artifacts(instance):
    paths = write_instance_artifacts(instance)
    env_path = paths.get("env") or ""
    override_path = paths.get("override") or ""
    if not env_path or not os.path.exists(env_path):
        raise RuntimeError(f"Instance env file was not created for {instance.get('id')}: {env_path}")
    if not override_path or not os.path.exists(override_path):
        raise RuntimeError(f"Instance override file was not created for {instance.get('id')}: {override_path}")
    return paths

def instance_compose_args(instance):
    spec = instance_variant_spec(instance)
    paths = ensure_instance_artifacts(instance)
    compose_file = str(spec.get("compose_abs_path") or "").strip()
    compose_project_dir = os.path.dirname(compose_file) or str(spec.get("compose_project_dir_abs_path") or "").strip()
    if not os.path.exists(compose_file):
        raise RuntimeError(f"Compose file missing for {instance['mode']}: {compose_file}")
    return compose_cmd() + ["--project-directory", compose_project_dir, "-p", instance_project_name(instance), "--env-file", paths["env"], "-f", compose_file, "-f", paths["override"]]


def instance_compose_project_dir(instance):
    spec = instance_variant_spec(instance)
    compose_file = str(spec.get("compose_abs_path") or "").strip()
    return os.path.dirname(compose_file) or str(spec.get("compose_project_dir_abs_path") or "").strip() or CLUB3090_DIR


def instance_subprocess_env(instance):
    spec = instance_variant_spec(instance)
    ensure_instance_artifacts(instance)
    env = _repo_subprocess_env()
    env.update(resolve_variant_launch_env(spec))
    visible_devices = ",".join(str(int(idx)) for idx in (instance.get("gpu_indices") or [instance["gpu_index"]]))
    env.pop("CLUB3090_GPU", None)
    env["MODEL_DIR"] = _resolve_variant_model_dir_root(spec)
    env["PORT"] = str(int(instance["port"]))
    env["CUDA_VISIBLE_DEVICES"] = visible_devices
    env["NVIDIA_VISIBLE_DEVICES"] = visible_devices
    env["COMPOSE_BIN"] = COMPOSE_BIN
    return _apply_variant_hardware_guard(spec, env)


def instance_stop_subprocess_env():
    env = _repo_subprocess_env()
    env["COMPOSE_BIN"] = COMPOSE_BIN
    return env

def _instance_launch(instance):
    spec = instance_variant_spec(instance)
    ensure_variant_install_ready(spec)
    cmd = instance_compose_args(instance) + ["up", "-d", "--force-recreate"]
    rc, out = run_cmd(
        cmd,
        timeout=1800,
        cwd=instance_compose_project_dir(instance),
        env=instance_subprocess_env(instance),
    )
    log_control(f"INSTANCE start {instance['id']} mode={instance['mode']} rc={rc}: {out[-4000:]}")
    if rc != 0:
        raise RuntimeError(out or f"docker compose up failed for {instance['id']}")
    return {"instance": instance, "output": out[-4000:]}


def _instance_wait_until_ready(instance):
    spec = instance_variant_spec(instance)
    ready_url = instance_ready_url(instance)
    wait_for_runtime_ready(
        instance_container_name(instance),
        ready_url,
        timeout=900,
        engine_family=variant_engine_family(spec),
    )
    warmup = maybe_warmup_variant_runtime(spec, ready_url)
    if warmup.get("skipped"):
        log_control(f"INSTANCE warmup skipped {instance['id']} mode={instance['mode']}: {warmup.get('reason')}")
    elif warmup.get("ok"):
        log_control(
            f"INSTANCE warmup complete {instance['id']} mode={instance['mode']} model={warmup.get('model') or ''} duration={warmup.get('duration_s') or 0}s"
        )
    else:
        log_control(f"INSTANCE warmup failed {instance['id']} mode={instance['mode']}: {warmup.get('reason') or 'unknown'}")
    clear_switch_failure(instance["mode"])


def start_instances_parallel(instances):
    targets = [dict(instance) for instance in (instances or []) if instance]
    if not targets:
        return {"started": [], "failed": []}
    globals().get("ensure_default_runtime_power", lambda *args, **kwargs: None)("start_instances_parallel", force=True)
    started = [None] * len(targets)
    failed = []
    launch_threads = []

    def launch_worker(index, instance):
        try:
            started[index] = _instance_launch(instance)
        except Exception as exc:
            failed.append({"instance": dict(instance), "error": str(exc)})

    for index, instance in enumerate(targets):
        thread = threading.Thread(
            target=launch_worker,
            args=(index, instance),
            name=f"club3090-launch-{str(instance.get('id') or index).lower()}",
            daemon=True,
        )
        launch_threads.append(thread)
        thread.start()
    for thread in launch_threads:
        thread.join()

    ready_threads = []

    def ready_worker(result):
        try:
            _instance_wait_until_ready(result["instance"])
        except Exception as exc:
            failed.append({"instance": dict(result["instance"]), "error": str(exc)})

    for result in [row for row in started if row]:
        thread = threading.Thread(
            target=ready_worker,
            args=(result,),
            name=f"club3090-ready-{str(result['instance'].get('id') or 'instance').lower()}",
            daemon=True,
        )
        ready_threads.append(thread)
        thread.start()
    for thread in ready_threads:
        thread.join()

    failed_ids = {
        str(entry.get("instance", {}).get("id") or "").strip().upper()
        for entry in failed
    }
    successful = [
        row
        for row in started
        if row and str(row["instance"].get("id") or "").strip().upper() not in failed_ids
    ]
    return {"started": successful, "failed": failed}


def start_instance(instance_id, track_switch_job=True):
    instance = get_instance(instance_id)
    if not instance:
        raise ValueError(f"Unknown instance: {instance_id}")
    try:
        if track_switch_job:
            _set_switch_job(
                active=True,
                status="booting",
                mode=str(instance.get("mode") or ""),
                target=str(instance.get("id") or ""),
                started_at=int(time.time()),
                finished_at=0,
                error="",
            )
        globals().get("ensure_default_runtime_power", lambda *args, **kwargs: None)("start_instance", force=True)
        result = _instance_launch(instance)
        _instance_wait_until_ready(instance)
        if track_switch_job:
            _set_switch_job(
                active=False,
                status="success",
                mode=str(instance.get("mode") or ""),
                target=str(instance.get("id") or ""),
                finished_at=int(time.time()),
                error="",
            )
        return result
    except Exception as e:
        write_switch_failure(instance["mode"], e)
        if track_switch_job:
            _set_switch_job(
                active=False,
                status="failed",
                mode=str(instance.get("mode") or ""),
                target=str(instance.get("id") or ""),
                finished_at=int(time.time()),
                error=str(e)[-12000:],
            )
        raise

def stop_instance(instance_id):
    instance = get_instance(instance_id)
    if not instance:
        raise ValueError(f"Unknown instance: {instance_id}")
    cmd = instance_compose_args(instance) + ["down"]
    rc, out = run_cmd(cmd, timeout=600, cwd=instance_compose_project_dir(instance), env=instance_stop_subprocess_env())
    if rc != 0:
        rc2, out2 = run_cmd(["docker", "rm", "-f", instance_container_name(instance)], timeout=120)
        out = (out or "") + f"\nmanual rm rc={rc2} {out2}"
    log_control(f"INSTANCE stop {instance['id']} rc={rc}: {out[-4000:]}")
    return rc, out[-4000:]


def _configured_scope_targets_for_mode(instance_id="", mode=""):
    selector = canonical_mode_selector(mode) if mode else ""
    target_id = str(instance_id or "").strip().upper()
    if not selector or target_id != "GLOBAL":
        return []
    spec = resolve_variant_spec(selector) or {}
    scope_kind = str(spec.get("scope_kind") or "")
    rows = read_instances_config()
    if scope_kind == "single":
        return [dict(row) for row in rows if row.get("kind") == "single" and canonical_mode_selector(row.get("mode")) == selector]
    if scope_kind == "dual":
        return [
            dict(row)
            for row in rows
            if row.get("kind") == "dual"
            and bool(row.get("auto_pair"))
            and canonical_mode_selector(row.get("mode")) == selector
        ]
    if scope_kind in {"multi", "global_only"}:
        return [{"id": "GLOBAL", "kind": "global", "mode": selector}]
    return []


def stop_runtime_scope(instance_id=None, mode=None):
    selector = canonical_mode_selector(mode) if mode else ""
    target_id = str(instance_id or "").strip().upper()
    if target_id and target_id != "GLOBAL":
        return stop_instance(target_id)
    matching = []
    if selector:
        matching = [
            dict(row)
            for row in running_runtime_rows(instances_snapshot())
            if canonical_mode_selector(row.get("mode")) == selector
        ]
    elif target_id == "GLOBAL":
        matching = [dict(row) for row in running_runtime_rows(instances_snapshot())]
    if not matching:
        matching = _configured_scope_targets_for_mode(target_id, selector)
    outputs = []
    rc = 0
    seen = set()
    for row in matching:
        row_id = str(row.get("id") or "").strip().upper()
        if not row_id or row_id in seen:
            continue
        seen.add(row_id)
        if row_id == "GLOBAL":
            item_rc, item_out = stop_global_mode()
        else:
            item_rc, item_out = stop_instance(row_id)
        rc = max(rc, int(item_rc or 0))
        outputs.append(f"{row_id}: {str(item_out or '').strip()}")
    if not outputs:
        return 0, "No matching runtime containers were active."
    return rc, "\n".join([line for line in outputs if line]).strip()[-12000:]

def update_instance(instance_id, mode=None, enabled=None):
    rows = read_instances_config()
    updated = None
    for row in rows:
        if row["id"] != str(instance_id or "").strip().upper():
            continue
        if mode is not None:
            mode = canonical_mode_selector(mode)
            valid_modes = DUAL_GPU_MODES if row.get("kind") == "dual" else SINGLE_GPU_MODES
            if mode not in valid_modes:
                raise ValueError("Selected preset type does not match this instance")
            row["mode"] = mode
        if enabled is not None:
            row["enabled"] = bool(enabled)
        updated = dict(row)
        break
    if updated is None:
        raise ValueError(f"Unknown instance: {instance_id}")
    write_instances_config(rows)
    return get_instance(updated["id"])

def save_pair_instance(gpu_indices, mode=None, enabled=None):
    pair = normalize_pair_indices(gpu_indices)
    if not pair:
        raise ValueError("Select exactly two distinct GPUs for a dual preset pair")
    pair_id = pair_instance_id(pair)
    rows = read_instances_config()
    existing = None
    for row in rows:
        if row["id"] == pair_id:
            existing = row
            break
    if existing is None:
        selected_mode = canonical_mode_selector(mode) if mode else default_dual_mode_selector()
        rows.append({
            "id": pair_id,
            "kind": "dual",
            "gpu_indices": pair,
            "mode": selected_mode if selected_mode in DUAL_GPU_MODES else default_dual_mode_selector(),
            "enabled": bool(enabled),
            "auto_pair": is_auto_pair_indices(pair),
            "port": instance_default_port("dual", pair),
        })
    else:
        if mode is not None:
            mode = canonical_mode_selector(mode)
            if mode not in DUAL_GPU_MODES:
                raise ValueError("Dual GPU pairs must use a dual preset")
            existing["mode"] = mode
        if enabled is not None:
            existing["enabled"] = bool(enabled)
        existing["auto_pair"] = bool(existing.get("auto_pair")) or is_auto_pair_indices(pair)
    write_instances_config(rows)
    return get_instance(pair_id)

def delete_pair_instance(instance_id):
    parsed = parse_instance_identifier(instance_id)
    if not parsed or parsed.get("kind") != "dual":
        raise ValueError("Only dual GPU pair groups can be removed")
    target = get_instance(parsed["id"])
    if target and target.get("auto_pair"):
        raise ValueError("Automatic sequential pair groups are built in and cannot be removed")
    rows = read_instances_config()
    remaining = [row for row in rows if row["id"] != parsed["id"]]
    if len(remaining) == len(rows):
        raise ValueError("Pair group not found")
    try:
        stop_instance(parsed["id"])
    except Exception:
        pass
    write_instances_config(remaining)
    return instances_snapshot()

def mode_default_port(mode, default=0):
    spec = resolve_variant_spec(mode)
    try:
        port = int((spec or {}).get("default_port") or 0)
    except Exception:
        port = 0
    return port or int(default or 0)

def visible_instances(rows=None):
    return list(rows if isinstance(rows, list) else read_instances_config())

def instance_runtime_mode(instance):
    return str((instance or {}).get("mode") or "")

def instance_runtime_port(instance):
    return int((instance or {}).get("port") or 0)

def instance_running(instance):
    return port_open(instance_runtime_port(instance), timeout=0.08)

def instance_runtime_container_name(instance):
    return instance_container_name(instance)

def primary_instance():
    rows = visible_instances(read_instances_config())
    if not rows:
        return None
    running = [inst for inst in rows if instance_running(inst)]
    if running:
        return sorted(running, key=lambda d: (len(d.get("gpu_indices") or [d["gpu_index"]]), d["gpu_index"], d["id"]))[0]
    enabled = [inst for inst in rows if inst.get("enabled")]
    if enabled:
        return sorted(enabled, key=lambda d: (len(d.get("gpu_indices") or [d["gpu_index"]]), d["gpu_index"], d["id"]))[0]
    return None

def boot_enabled_instances():
    outputs = []
    rows = visible_instances(read_instances_config())
    file_mode = read_active_mode_file()
    enabled_rows = [inst for inst in rows if inst.get("enabled")]
    if enabled_rows:
        result = start_instances_parallel(enabled_rows)
        for row in result.get("started") or []:
            inst = row.get("instance") or {}
            outputs.append(f"{inst.get('id') or 'instance'} started: {str(row.get('output') or '')[-800:]}")
        for row in result.get("failed") or []:
            inst = row.get("instance") or {}
            outputs.append(f"{inst.get('id') or 'instance'} failed: {row.get('error')}")
    if not outputs and file_mode:
        spec = resolve_variant_spec(file_mode)
        if spec and str(spec.get("scope_kind") or "") in {"multi", "global_only"}:
            try:
                result = run_switch(file_mode)
                outputs.append(f"global runtime started from active mode {file_mode}: {result[-800:]}")
            except Exception as e:
                outputs.append(f"global runtime failed: {e}")
    log_control("BOOT instances: " + " || ".join(outputs))
    return outputs

def mode_gpu_indices(mode, gpu_count=None):
    if mode not in DUAL_GPU_MODES:
        return []
    try:
        count = int(gpu_count if gpu_count is not None else detect_gpu_count_runtime())
    except Exception:
        count = 0
    return [idx for idx in range(max(count, 0))][:2]

def running_dual_mode():
    rows = running_dual_instances()
    if not rows:
        return None
    rows.sort(key=lambda d: (d["gpu_indices"], d["id"]))
    return rows[0]["mode"]

def running_dual_instances():
    rows = []
    for inst in visible_instances(read_instances_config()):
        if inst.get("kind") != "dual" or not instance_running(inst):
            continue
        row = dict(inst)
        row["mode"] = instance_runtime_mode(inst)
        rows.append(row)
    rows.sort(key=lambda d: (d.get("gpu_indices") or [], d["id"]))
    return rows

def running_dual_instance_snapshots():
    snaps = []
    for inst in running_dual_instances():
        snaps.append(dict(inst) if "proxy_prefix" in inst else instance_snapshot(inst))
    return snaps

def stop_overlapping_instances(indices, exclude_ids=None):
    wanted = {int(idx) for idx in (indices or [])}
    excluded = {str(x or "").strip().upper() for x in (exclude_ids or [])}
    results = []
    for inst in read_instances_config():
        if inst["id"] in excluded:
            continue
        inst_indices = {int(idx) for idx in (inst.get("gpu_indices") or [inst.get("gpu_index", -1)])}
        if not wanted.intersection(inst_indices):
            continue
        if not instance_running(inst):
            continue
        rc, out = stop_instance(inst["id"])
        results.append({"id": inst["id"], "rc": rc, "output": out[-1200:]})
    return results

def stop_global_mode():
    stopped = stop_overlapping_instances([idx for inst in running_dual_instances() for idx in inst.get("gpu_indices") or []])
    return 0, "\n".join((row.get("output") or "") for row in stopped)[-4000:]

def global_scope_power_action(action, enabled=None):
    action_name = str(action or "").strip().lower()
    rows = visible_instances(read_instances_config())
    outputs = []
    changed = []
    if action_name == "toggle_enabled":
        for row in rows:
            updated = update_instance(row["id"], enabled=bool(enabled))
            changed.append(instance_snapshot(updated))
            outputs.append(f"{row['id']}: autoboot {'enabled' if enabled else 'disabled'}")
        return {"instances": changed, "output": "\n".join(outputs)[-12000:]}
    if action_name == "start_instance":
        for row in rows:
            result = start_instance(row["id"], track_switch_job=False)
            changed.append(instance_snapshot(get_instance(row["id"])))
            outputs.append(f"{row['id']}: {str(result.get('output') or '').strip()}")
        return {"instances": changed, "output": "\n".join(outputs)[-12000:]}
    if action_name == "restart_instance":
        for row in rows:
            stop_vllm_container("manual_restart", instance_id=row["id"])
            result = start_instance(row["id"], track_switch_job=False)
            changed.append(instance_snapshot(get_instance(row["id"])))
            outputs.append(f"{row['id']}: {str(result.get('output') or '').strip()}")
        return {"instances": changed, "output": "\n".join(outputs)[-12000:]}
    if action_name == "stop_container":
        rc, output = stop_runtime_scope(instance_id="GLOBAL")
        return {"instances": instances_snapshot(), "output": f"rc={rc}\n{output}"[-12000:]}
    raise ValueError("Invalid global scope action")

def instance_assignment(instance, dual_mode=None):
    gpu_indices = [int(idx) for idx in (instance.get("gpu_indices") or [instance.get("gpu_index", -1)])]
    if instance.get("kind") == "dual":
        runtime_mode = instance_runtime_mode(instance)
        if instance_running(instance):
            return {
                "scope": "pair",
                "mode": runtime_mode,
                "text": f"GPUs {', '.join(str(idx) for idx in gpu_indices)} are running the dual preset {runtime_mode}",
                "override": False,
            }
        return {
            "scope": "pair",
            "mode": runtime_mode,
            "text": f"GPUs {', '.join(str(idx) for idx in gpu_indices)} are reserved for dual preset {runtime_mode}",
            "override": False,
        }
    active_pairs = dual_mode if isinstance(dual_mode, list) else running_dual_instances()
    for pair in active_pairs:
        pair_indices = {int(idx) for idx in pair.get("gpu_indices") or []}
        if set(gpu_indices).intersection(pair_indices):
            return {
                "scope": "pair",
                "mode": pair["mode"],
                "text": f"GPU {gpu_indices[0]} is currently occupied by dual pair {pair['id']} running {pair['mode']}",
                "override": True,
            }
    mode = str(instance.get("mode") or "vllm/default")
    return {
        "scope": "per-gpu",
        "mode": mode,
        "text": f"GPU {gpu_indices[0]} is assigned to the per-GPU preset {mode}",
        "override": False,
    }

def instance_snapshot(instance, dual_mode=None):
    container = instance_runtime_container_name(instance)
    runtime_mode = instance_runtime_mode(instance)
    runtime_port = instance_runtime_port(instance)
    ready_url = f"http://127.0.0.1:{runtime_port}/v1/models"
    spec = instance_variant_spec(instance)
    boot_state = runtime_boot_state(container, ready_url, variant_engine_family(spec))
    assigned = instance_assignment(instance, dual_mode=dual_mode)
    return {
        "id": instance["id"],
        "kind": instance.get("kind", "single"),
        "gpu_index": instance["gpu_index"],
        "gpu_indices": list(instance.get("gpu_indices") or [instance["gpu_index"]]),
        "mode": runtime_mode,
        "enabled": bool(instance.get("enabled")),
        "auto_pair": bool(instance.get("auto_pair")),
        "port": runtime_port,
        "container": container,
        "running": bool(boot_state.get("running")),
        "booting": bool(boot_state.get("booting")),
        "container_state": boot_state.get("status") or "",
        "ready_url": ready_url,
        "proxy_prefix": f"/{instance['id']}",
        "display_name": instance["id"] if instance.get("kind") != "dual" else f"Pair {', '.join(str(idx) for idx in instance.get('gpu_indices') or [])}",
        "assignment_scope": assigned["scope"],
        "assignment_mode": assigned["mode"],
        "assignment_text": assigned["text"],
        "overrides_dual_mode": bool(assigned["override"]),
    }

def instances_snapshot():
    active_pairs = running_dual_instances()
    return [instance_snapshot(inst, dual_mode=active_pairs) for inst in visible_instances(read_instances_config())]

def ready_url_for_mode(mode):
    return f"http://localhost:{mode_default_port(mode, PROXY_PORT)}/v1/models"

def write_active_mode(mode):
    selector = canonical_mode_selector(mode)
    os.makedirs(os.path.dirname(ACTIVE_MODE_FILE), exist_ok=True)
    with open(ACTIVE_MODE_FILE, "w", encoding="utf-8") as f:
        f.write(selector)


def clear_active_mode():
    try:
        os.remove(ACTIVE_MODE_FILE)
    except FileNotFoundError:
        pass
    except Exception:
        pass

def read_active_mode_file():
    try:
        mode = canonical_mode_selector(open(ACTIVE_MODE_FILE, "r", encoding="utf-8").read().strip())
        return mode if resolve_variant_spec(mode) else None
    except Exception:
        return None

def write_last_good_mode(mode):
    selector = canonical_mode_selector(mode)
    if resolve_variant_spec(selector):
        try:
            with open(LAST_GOOD_MODE_FILE, "w", encoding="utf-8") as f:
                f.write(selector)
        except Exception:
            pass

def read_last_good_mode_file():
    try:
        mode = canonical_mode_selector(open(LAST_GOOD_MODE_FILE, "r", encoding="utf-8").read().strip())
        return mode if resolve_variant_spec(mode) else None
    except Exception:
        return None

def port_open(port, timeout=0.25):
    # TCP-only readiness check. Do not call /health here; vLLM logs those.
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def runtime_boot_state(container_name="", ready_url="", engine_family=""):
    name = str(container_name or "").strip()
    target_url = str(ready_url or "").strip()
    engine = str(engine_family or "").strip().lower()
    state = _docker_inspect_state(name) if name else {"exists": False, "running": False, "exit_code": None, "status": ""}
    ready = False
    failure_reason = ""
    try:
        if name:
            failure_reason = _container_boot_failure_reason(name)
            api_ready = _runtime_models_available_once(name, target_url, min_interval=(15 if engine == "vllm" else 2))
            bootstrap_ready = _container_bootstrap_complete(name) if engine == "vllm" else False
            port_ready = _ready_url_port_open(target_url, timeout=0.25) if engine and engine != "vllm" else False
            ready = bool(state.get("running")) and (api_ready or bootstrap_ready or port_ready)
    except Exception:
        ready = False
    booting = bool(name and state.get("running") and not ready and not failure_reason)
    return {
        "exists": bool(state.get("exists")),
        "running": bool(ready),
        "booting": booting,
        "status": "error" if failure_reason and not ready else str(state.get("status") or ""),
        "exit_code": state.get("exit_code"),
    }

def detected_mode():
    load_runtime_inventory()
    primary = primary_instance()
    if primary:
        return primary["mode"]
    # Source of truth is the mode selected by this controller/switch.sh.
    # If the file is stale, use a TCP-only port scan as a fallback. Never call /health.
    file_mode = read_active_mode_file()
    known_modes = list(dict.fromkeys(list(SINGLE_GPU_MODES) + list(DUAL_GPU_MODES)))
    if file_mode and resolve_variant_spec(file_mode):
        if port_open(mode_default_port(file_mode, PROXY_PORT), timeout=0.08):
            return file_mode
        # During startup/switching the port may not be listening yet; keep the
        # intended mode unless another known mode is definitely listening.
        open_modes = [m for m in known_modes if port_open(mode_default_port(m, PROXY_PORT), timeout=0.08)]
        if len(open_modes) == 1:
            write_active_mode(open_modes[0])
            return open_modes[0]
        failed = read_switch_failure()
        if str(failed.get("mode") or "") == file_mode:
            fallback = read_last_good_mode_file()
            if fallback and fallback != file_mode:
                return fallback
        return file_mode
    open_modes = [m for m in known_modes if port_open(mode_default_port(m, PROXY_PORT), timeout=0.08)]
    if len(open_modes) == 1:
        write_active_mode(open_modes[0])
        return open_modes[0]
    fallback = read_last_good_mode_file() or canonical_mode_selector(DEFAULT_MODE)
    if fallback not in known_modes:
        fallback = default_single_mode_selector()
    write_active_mode(fallback)
    return fallback

def active_mode():
    return detected_mode()

def active_port():
    primary = primary_instance()
    if primary:
        return int(primary["port"])
    return mode_default_port(active_mode(), 8020)

def password_ok(username, password):
    if not username or not password or not shutil.which("pamtester"):
        return False
    key = (username, password)
    now = time.time()
    if key in auth_cache and now - auth_cache[key] < AUTH_CACHE_SECONDS:
        return True
    try:
        p = subprocess.run(["pamtester", "login", username, "authenticate"], input=password+"\n", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, timeout=8)
        ok = p.returncode == 0
        if ok:
            auth_cache[key] = now
        return ok
    except Exception:
        return False

def check_basic_auth(header):
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header.split(" ",1)[1], validate=True).decode("utf-8")
        username, password = decoded.split(":", 1)
        return password_ok(username, password)
    except Exception:
        return False


def parse_cookie_header(header):
    values = {}
    for chunk in str(header or "").split(";"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip()
    return values


def _prune_admin_sessions(now=None):
    current = float(now or time.time())
    with admin_session_lock:
        expired = [token for token, info in admin_sessions.items() if float((info or {}).get("expires_at") or 0.0) <= current]
        for token in expired:
            admin_sessions.pop(token, None)


def create_admin_session(client_ip=""):
    now = time.time()
    token = secrets.token_urlsafe(32)
    with admin_session_lock:
        admin_sessions[token] = {
            "client": str(client_ip or ""),
            "expires_at": now + max(300, int(ADMIN_SESSION_TTL_SECONDS or 86400)),
        }
    return token


def request_is_https(headers):
    forwarded = str(headers.get("Forwarded", "") or "")
    if re.search(r"proto=https", forwarded, re.I):
        return True
    return str(headers.get("X-Forwarded-Proto", "") or "").strip().lower() == "https"


def build_admin_session_cookie(token, secure=False):
    ttl = max(300, int(ADMIN_SESSION_TTL_SECONDS or 86400))
    suffix = "; Secure" if secure else ""
    return f"{ADMIN_SESSION_COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={ttl}{suffix}"


def expired_admin_session_cookie(secure=False):
    suffix = "; Secure" if secure else ""
    return f"{ADMIN_SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{suffix}"


def admin_session_ok(headers, client_ip=""):
    _prune_admin_sessions()
    token = parse_cookie_header(headers.get("Cookie", "")).get(ADMIN_SESSION_COOKIE_NAME, "")
    if not token:
        return False
    now = time.time()
    with admin_session_lock:
        info = dict(admin_sessions.get(token) or {})
        if not info:
            return False
        if float(info.get("expires_at") or 0.0) <= now:
            admin_sessions.pop(token, None)
            return False
        bound_client = str(info.get("client") or "")
        if bound_client and client_ip and bound_client != client_ip:
            return False
        info["expires_at"] = now + max(300, int(ADMIN_SESSION_TTL_SECONDS or 86400))
        admin_sessions[token] = info
        return True


def should_log_admin_auth_denial(client_ip, path):
    now = time.time()
    key = (str(client_ip or ""), str(path or ""))
    with admin_auth_denial_lock:
        last = float(admin_auth_denial_state.get(key) or 0.0)
        admin_auth_denial_state[key] = now
        stale_before = now - max(60.0, float(ADMIN_AUTH_DENIAL_LOG_WINDOW_SECONDS or 30) * 4.0)
        for existing_key, existing_time in list(admin_auth_denial_state.items()):
            if float(existing_time or 0.0) < stale_before:
                admin_auth_denial_state.pop(existing_key, None)
    return now - last >= max(1.0, float(ADMIN_AUTH_DENIAL_LOG_WINDOW_SECONDS or 30))

def docker_names(all_containers=False, force=False, max_age=2.0, timeout=1.5):
    cache_key = "all" if all_containers else "running"
    now = time.time()
    with slow_cache_lock:
        cached = dict(docker_names_cache.get(cache_key) or {})
        cached_value = list(cached.get("value") or [])
        cached_time = float(cached.get("time") or 0.0)
    if not force and cached_time and now - cached_time < max(0.5, float(max_age or 2.0)):
        return cached_value
    try:
        args = ["docker", "ps"]
        if all_containers:
            args.append("-a")
        args += ["--format", "{{.Names}}"]
        out = subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=max(0.5, float(timeout or 1.5)))
        names = [x.strip() for x in out.splitlines() if x.strip()]
        with slow_cache_lock:
            docker_names_cache[cache_key] = {"value": list(names), "time": time.time()}
        return names
    except Exception:
        return cached_value

def is_runtime_container_name(name):
    load_runtime_inventory()
    text = str(name or "").strip()
    lowered = text.lower()
    if not text:
        return False
    if lowered.startswith("club3090-"):
        return True
    if lowered.startswith("vllm-") or lowered.startswith("llama-cpp-"):
        return True
    if text in VARIANT_BY_CONTAINER or text in VARIANT_BY_SERVICE:
        return True
    return False

def vllm_container_names(all_containers=False, force=False, max_age=2.0, timeout=1.5):
    return [n for n in docker_names(all_containers=all_containers, force=force, max_age=max_age, timeout=timeout) if is_runtime_container_name(n)]


def _parse_gpu_index_set(value):
    text = str(value or "").strip()
    if not text:
        return set(), False
    lowered = text.lower()
    if lowered in {"all", "*"}:
        return set(), True
    found = set()
    for token in re.split(r"[\s,;]+", text):
        token = str(token or "").strip()
        if token.isdigit():
            found.add(int(token))
    return found, False


def _inspect_container_gpu_targets(name):
    try:
        out = subprocess.check_output(["docker", "inspect", name], text=True, stderr=subprocess.STDOUT, timeout=5)
        rows = json.loads(out)
        data = rows[0] if rows else {}
    except Exception:
        return set(), False
    indices = set()
    all_gpus = False
    labels = ((data.get("Config") or {}).get("Labels") or {}) if isinstance(data, dict) else {}
    for key in ("club3090.gpu_indices", "club3090.gpu_index"):
        parsed, parsed_all = _parse_gpu_index_set(labels.get(key))
        indices.update(parsed)
        all_gpus = all_gpus or parsed_all
    env_map = {}
    for item in ((data.get("Config") or {}).get("Env") or []):
        if "=" in str(item):
            key, value = str(item).split("=", 1)
            env_map[key] = value
    for key in ("ESTATE_GPUS", "NVIDIA_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES"):
        parsed, parsed_all = _parse_gpu_index_set(env_map.get(key))
        indices.update(parsed)
        all_gpus = all_gpus or parsed_all
    for req in ((data.get("HostConfig") or {}).get("DeviceRequests") or []):
        if not isinstance(req, dict):
            continue
        for raw in req.get("DeviceIDs") or []:
            parsed, parsed_all = _parse_gpu_index_set(raw)
            indices.update(parsed)
            all_gpus = all_gpus or parsed_all
    if not indices and not all_gpus and is_runtime_container_name(name):
        # Most direct single-GPU compose launches default to GPU0 when no explicit
        # target is surfaced in inspect metadata.
        indices.add(0)
    return indices, all_gpus


def free_gpu_runtime_resources(gpu_index):
    try:
        target = int(gpu_index)
    except Exception:
        raise ValueError("A GPU index is required")
    names = vllm_container_names(all_containers=False, force=True, max_age=0.0, timeout=8.0)
    killed = []
    skipped = []
    errors = []
    for name in names:
        indices, all_gpus = _inspect_container_gpu_targets(name)
        if not all_gpus and target not in indices:
            skipped.append({"container": name, "gpu_indices": sorted(indices)})
            continue
        rc, out = run_cmd(["docker", "kill", name], timeout=60)
        rm_rc, rm_out = run_cmd(["docker", "rm", "-f", name], timeout=60)
        row = {
            "container": name,
            "gpu_indices": "all" if all_gpus else sorted(indices),
            "kill_rc": rc,
            "rm_rc": rm_rc,
            "output": ((out or "") + "\n" + (rm_out or ""))[-1000:],
        }
        if rc == 0 or rm_rc == 0:
            killed.append(row)
        else:
            errors.append(row)
    result = {"gpu_index": target, "killed": killed, "skipped": skipped, "errors": errors}
    log_control(f"GPU free resources gpu={target}: {summarize_audit_result(result)}")
    log_audit("gpu_resources_freed", target=f"GPU{target}", result_summary=summarize_audit_result(result))
    return result


def current_container():
    primary = primary_instance()
    if primary and instance_running(primary):
        return instance_runtime_container_name(primary)
    names = vllm_container_names(all_containers=False)
    active_spec = resolve_variant_spec(active_mode())
    active_name = str((active_spec or {}).get("container_name") or "")
    if active_name and active_name in names:
        return active_name
    return names[0] if names else ""


def running_runtime_rows(instances=None):
    rows = []
    for row in instances or []:
        if row.get("running") or row.get("booting"):
            rows.append(dict(row))
    rows.sort(key=lambda item: ((item.get("gpu_indices") or [item.get("gpu_index", 9999)]), str(item.get("id") or "")))
    return rows


def runtime_mode_list(rows, fallback_mode=""):
    values = []
    seen = set()
    for row in rows or []:
        mode = str(row.get("mode") or "").strip()
        if mode and mode not in seen:
            seen.add(mode)
            values.append(mode)
    fallback_mode = str(fallback_mode or "").strip()
    if not values and fallback_mode:
        values.append(fallback_mode)
    return values


def runtime_container_list(rows, fallback_container=""):
    values = []
    seen = set()
    for row in rows or []:
        container = str(row.get("container") or "").strip()
        if container and container not in seen:
            seen.add(container)
            values.append(container)
    fallback_container = str(fallback_container or "").strip()
    if not values and fallback_container:
        values.append(fallback_container)
    return values
