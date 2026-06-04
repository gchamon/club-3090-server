import os
import sys
import time
import io
import contextlib

try:
    from control.shared import *  # type: ignore
except Exception:
    if "CLUB3090_DIR" not in globals():
        _CONTROL_DIR = os.path.dirname(os.path.abspath(__file__))
        if _CONTROL_DIR not in sys.path:
            sys.path.insert(0, _CONTROL_DIR)
        from shared import *  # type: ignore

def _format_model_display_name(model_id):
    if not model_id:
        return "Unknown Model"
    if model_id == "qwen3.6-27b":
        return "Qwen3.6-27B"
    if model_id == "gemma-4-31b":
        return "Gemma 4 31B"
    if model_id == "qwen3.6-35b-a3b":
        return "Qwen 3.6 35B-A3B"
    if model_id == "gemma-4-26b-a4b":
        return "Gemma 4 26B-A4B"
    return str(model_id).replace("-", " ")


def _selector_token(text):
    token = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "").strip().lower()).strip("-")
    return token or "variant"


def _variant_id_from_rel_path(rel_path):
    rel = str(rel_path or "").replace("\\", "/").strip("/")
    if not rel:
        return "variant-unknown"
    stem = rel[:-4] if rel.endswith(".yml") else rel
    return "variant-" + _selector_token(stem)


def _variant_id_from_selector(selector):
    token = _selector_token(selector)
    return f"variant-{token}"


def _mode_selector_for_variant(variant):
    if not isinstance(variant, dict):
        return ""
    return str(variant.get("upstream_tag") or variant.get("variant_id") or "").strip()


def _variant_rel_compose_path(variant):
    return str((variant or {}).get("compose_rel_path") or "").replace("\\", "/").strip("/")


def _normalize_engine(engine):
    raw = str(engine or "").strip().lower().replace("_", "-")
    if raw == "llama-cpp":
        return "llamacpp"
    return raw


def _normalize_compose_rel_path(path):
    return str(path or "").replace("\\", "/").strip("/")


def _path_is_within(root, candidate):
    root_text = str(root or "").strip()
    candidate_text = str(candidate or "").strip()
    if not root_text or not candidate_text:
        return False
    try:
        root_abs = os.path.normcase(os.path.abspath(root_text))
        candidate_abs = os.path.normcase(os.path.abspath(candidate_text))
        return os.path.commonpath([root_abs, candidate_abs]) == root_abs
    except Exception:
        return False


def _infer_topology_from_compose_path(path, fallback=""):
    rel = _normalize_compose_rel_path(path)
    parts = rel.split("/")
    if "single" in parts:
        return "single"
    if "dual" in parts:
        return "dual"
    for part in parts:
        if part.startswith("multi"):
            return "multi"
    return str(fallback or "").strip() or "single"


def _normalize_status_kind(status_raw):
    text = str(status_raw or "").strip().lower()
    if not text:
        return "unknown"
    if "⭐" in text or "recommended" in text or "pick" in text:
        return "production"
    if "shipped" in text or "stable" in text:
        return "production"
    if "tombstoned" in text or "not shipping" in text:
        return "tombstoned"
    if "ampere-blocked" in text:
        return "blocked"
    if "hardware-blocked" in text or ("blocked" in text and "hardware" in text):
        return "blocked"
    if "production-track blocked" in text:
        return "preview"
    if "deprecated" in text:
        return "deprecated"
    if "upstream" in text and ("blocked" in text or "gated" in text):
        return "upstream_gated"
    if "preview" in text:
        return "preview"
    if "experimental" in text or "community" in text or "parked" in text or "archival" in text:
        return "experimental"
    if "eval only" in text or "evaluation only" in text:
        return "experimental"
    if "primary" in text:
        return "production"
    if "working" in text:
        return "production_caveat"
    if "caveat" in text or "known issue" in text or "warning" in text:
        return "production_caveat"
    if "production" in text or "prod" in text:
        return "production"
    if "blocked" in text:
        return "blocked"
    return "unknown"


def _variant_path_forces_experimental(*parts):
    text = " ".join(str(part or "").strip().lower() for part in parts if str(part or "").strip())
    return "experimental" in text


def _load_upstream_profiles():
    cached = getattr(_load_upstream_profiles, "_cache", None)
    if cached is not None:
        return cached
    os.environ.setdefault("CLUB3090_LOG_LEVEL", "ERROR")
    ensure_upstream_repo_on_sys_path()
    try:
        from scripts.lib.profiles.compat import load_profiles

        value = load_profiles()
    except Exception:
        value = None
    setattr(_load_upstream_profiles, "_cache", value)
    return value


def _load_upstream_weights_reader():
    cached = getattr(_load_upstream_weights_reader, "_cache", None)
    if cached is not None:
        return cached
    os.environ.setdefault("CLUB3090_LOG_LEVEL", "ERROR")
    ensure_upstream_repo_on_sys_path()
    try:
        from scripts.lib.profiles import weights as profile_weights

        value = profile_weights
    except Exception:
        value = None
    setattr(_load_upstream_weights_reader, "_cache", value)
    return value


def _load_upstream_compose_registry():
    cached = getattr(_load_upstream_compose_registry, "_cache", None)
    if cached is not None:
        return dict(cached)
    os.environ.setdefault("CLUB3090_LOG_LEVEL", "ERROR")
    ensure_upstream_repo_on_sys_path()
    try:
        from scripts.lib.profiles.compose_registry import COMPOSE_REGISTRY

        value = {str(key): dict(value or {}) for key, value in dict(COMPOSE_REGISTRY or {}).items()}
    except Exception:
        value = {}
    setattr(_load_upstream_compose_registry, "_cache", dict(value))
    return dict(value)


def _normalize_weight_variant_key(value):
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = text.replace("_", "-")
    alias_map = {
        "gguf-q4km": "unsloth-q4km",
        "gguf-iq4ks": "ubergarm-iq4ks",
        "awq-compressed-tensors": "awq",
        "autoround-int4-mixed": "autoround-int4-mixed",
        "autoround-int4": "autoround-int4",
    }
    lowered = normalized.lower()
    return alias_map.get(lowered, normalized)


def _selector_engine_display(selector="", compose_path=""):
    selector_text = str(selector or "").strip().lower()
    compose_hint = _normalize_compose_rel_path(compose_path).lower()
    if selector_text.startswith("ik-llama/") or "/ik-llama/" in compose_hint:
        return "ik-llama"
    if (
        selector_text.startswith(("llamacpp/", "llama-cpp/"))
        or "/llama-cpp/" in compose_hint
        or "/llamacpp/" in compose_hint
    ):
        return "llamacpp"
    if selector_text.startswith("sglang/") or "/sglang/" in compose_hint:
        return "sglang"
    if selector_text.startswith("vllm/") or "/vllm/" in compose_hint:
        return "vllm"
    return str(selector or "").split("/", 1)[0].strip().lower() or ""


def _weight_recipe_from_model_variant(model_id, weights_variant):
    reader = _load_upstream_weights_reader()
    model_text = str(model_id or "").strip()
    variant_text = _normalize_weight_variant_key(weights_variant)
    if reader is None or not model_text or not variant_text:
        return {}
    candidates = [
        f"{model_text}:{variant_text}",
        f"{model_text}:{variant_text.replace('-', '_')}",
    ]
    for candidate in dict.fromkeys(candidates):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                resolved_model_id, resolved_variant = reader._resolve_key(candidate)
            return dict(reader._recipe(resolved_model_id, resolved_variant))
        except (Exception, SystemExit):
            continue
    return {}


def _weight_recipe_from_subpath(subpath):
    reader = _load_upstream_weights_reader()
    clean = str(subpath or "").replace("\\", "/").strip()
    if reader is None or not clean:
        return {}
    legacy_aliases = {
        "Qwen3.6-27B-DFlash": "qwen3.6-27b-dflash",
        "gemma-4-31B-it-DFlash": "gemma-4-31b-it-dflash",
        "gemma-4-31B-it-assistant": "gemma-4-31b-it-assistant",
        "gemma-4-26B-A4B-it-assistant": "gemma-4-26b-a4b-it-assistant",
    }
    clean_parts = clean.split("/")
    tail = clean_parts[-1] if clean_parts else clean
    if tail in legacy_aliases:
        clean_parts[-1] = legacy_aliases[tail]
        clean = "/".join(clean_parts)
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            model_id, variant = reader._lookup_path(clean)
        return dict(reader._recipe(model_id, variant))
    except (Exception, SystemExit):
        return {}


def _recipe_setup_env_map(recipe):
    env_map = {}
    for token in shlex.split(str((recipe or {}).get("WEIGHT_SETUP_ENV") or "")):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = str(key or "").strip()
        value = str(value or "").strip()
        if key:
            env_map[key] = value
    return env_map


def _recipe_download_command(model_dir_root, recipe):
    recipe_data = dict(recipe or {})
    repo_id = str(recipe_data.get("WEIGHT_REPO") or "").strip()
    repo_candidates = [
        str(item or "").strip()
        for item in (recipe_data.get("WEIGHT_REPO_CANDIDATES") or [])
        if str(item or "").strip()
    ]
    subdir = str(recipe_data.get("WEIGHT_SUBDIR") or "").replace("\\", "/").strip().strip("/")
    if not subdir:
        return ""
    target_dir = os.path.join(model_dir_root, subdir.replace("/", os.sep))
    files = [str(item or "").strip() for item in shlex.split(str(recipe_data.get("WEIGHT_FILES") or "")) if str(item or "").strip()]
    quoted_files = " ".join(shlex.quote(item) for item in files)
    def build_command(candidate_repo):
        base = f'hf download {shlex.quote(candidate_repo)}'
        if quoted_files:
            base += f" {quoted_files}"
        return f'{base} --local-dir "{target_dir}"'
    candidates = [repo_id] if repo_id else []
    candidates.extend(repo_candidates)
    candidates = [item for item in dict.fromkeys(candidates) if item]
    if not candidates:
        return ""
    commands = [build_command(candidate_repo) for candidate_repo in candidates]
    return commands[0] if len(commands) == 1 else "( " + " || ".join(commands) + " )"


def _compose_setup_command(model_id, env_map):
    target = str(model_id or "").strip()
    if not target or not _setup_script_supports_model(target):
        return ""
    prefix = " ".join(
        f"{key}={shlex.quote(str(value or ''))}"
        for key, value in env_map.items()
        if str(key or "").strip()
    )
    command = f"bash scripts/setup.sh {shlex.quote(target)}"
    return f"{prefix} {command}".strip() if prefix else command


def _setup_env_covers_mmproj(model_id, env_map):
    model_text = str(model_id or "").strip()
    weights_value = str((env_map or {}).get("WEIGHTS") or "").strip().lower()
    return model_text == "qwen3.6-27b" and weights_value == "gguf"


def _setup_env_covers_drafter(model_id, drafter_id, env_map):
    model_text = str(model_id or "").strip()
    drafter_text = str(drafter_id or "").strip()
    env = dict(env_map or {})
    if not drafter_text:
        return False
    if model_text == "gemma-4-31b" and drafter_text == "gemma-it-assistant":
        return True
    if model_text == "gemma-4-26b-a4b" and drafter_text == "gemma-26b-it-assistant":
        return str(env.get("WITH_ASSISTANT_DRAFT") or "").strip() == "1"
    if model_text == "qwen3.6-27b" and drafter_text == "zlab-qwen-dflash":
        return str(env.get("WITH_DFLASH_DRAFT") or "").strip() == "1"
    if model_text == "gemma-4-31b" and drafter_text == "gemma-dflash":
        return str(env.get("WITH_DFLASH_DRAFT") or "").strip() == "1"
    return False


def _recipe_subdir_host_path(model_dir_root, recipe):
    subdir = str((recipe or {}).get("WEIGHT_SUBDIR") or "").replace("\\", "/").strip().strip("/")
    if not subdir:
        return ""
    return os.path.join(model_dir_root, subdir.replace("/", os.sep))


def resolve_variant_launch_env(spec):
    variant_spec = spec if isinstance(spec, dict) else {}
    env = {}
    registry_key = str(
        variant_spec.get("registry_key")
        or variant_spec.get("upstream_tag")
        or variant_spec.get("profile_like")
        or ""
    ).strip()
    if registry_key and registry_key.startswith("vllm/"):
        ensure_upstream_repo_on_sys_path()
        try:
            from scripts.lib.profiles.compat import load_profiles
            from scripts.lib.profiles.launch_compat import resolve_variant_pin

            exports = resolve_variant_pin(load_profiles(), registry_key)
            env.update(
                {
                    str(key): str(value)
                    for key, value in dict(exports or {}).items()
                    if str(key or "").strip() and str(value or "").strip()
                }
            )
        except Exception:
            pass
    nightly_sha = str(env.get("VLLM_NIGHTLY_SHA") or "").strip()
    stable_vllm_nightly_fallbacks = {
        "bf610c2f56764e1b30bc6065f4ceace3d6e59036",
        "e47c98ef7a38792996e452ef53914e21e41928e9",
    }
    if nightly_sha in stable_vllm_nightly_fallbacks:
        env.pop("VLLM_NIGHTLY_SHA", None)
        env["VLLM_IMAGE"] = "vllm/vllm-openai:v0.22.0"
    env.update(preset_launch_env_overrides(variant_spec))
    selector = str(
        variant_spec.get("selector")
        or variant_spec.get("upstream_tag")
        or variant_spec.get("registry_key")
        or ""
    ).strip().lower()
    if selector.startswith("ik-llama/apex-") and not str(env.get("REASONING_TOKENS") or "").strip():
        reasoning_raw = str(env.get("REASONING") or "").strip().strip('"').strip("'").lower()
        if reasoning_raw in {"on", "true", "1", "yes", "enabled"}:
            env["REASONING_TOKENS"] = "<think>,</think>"
        elif reasoning_raw in {"off", "false", "0", "no", "disabled", ""}:
            env["REASONING_TOKENS"] = "none"
    return {
        str(key): str(value)
        for key, value in env.items()
        if str(key or "").strip() and str(value or "").strip()
    }


def _read_custom_model_registry():
    payload = read_json_file(CUSTOM_MODELS_FILE, [])
    if not isinstance(payload, list):
        return []
    rows = []
    seen = set()
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        record_id = _selector_token(raw.get("id") or raw.get("model_id") or raw.get("slug") or "")
        if not record_id or record_id in seen:
            continue
        seen.add(record_id)
        compose_path = os.path.normpath(str(raw.get("compose_path") or "").strip())
        selector = str(raw.get("selector") or f"custom/{record_id}").strip()
        rows.append(
            {
                "id": record_id,
                "selector": selector,
                "slug": str(raw.get("slug") or "").strip(),
                "model_id": str(raw.get("model_id") or f"custom-{record_id}").strip(),
                "display_name": str(raw.get("display_name") or raw.get("slug") or record_id).strip(),
                "profile_like": str(raw.get("profile_like") or "").strip(),
                "compose_path": compose_path,
                "compose_rel_path": _normalize_compose_rel_path(raw.get("compose_rel_path")),
                "source_kind": "custom",
                "inventory_origin": str(raw.get("inventory_origin") or "custom_registry").strip() or "custom_registry",
                "registry_key": str(raw.get("registry_key") or selector).strip() or selector,
                "profile_model_id": str(raw.get("profile_model_id") or raw.get("model_id") or "").strip(),
                "profile_engine_id": str(raw.get("profile_engine_id") or "").strip(),
                "profile_workload_id": str(raw.get("profile_workload_id") or "").strip(),
                "profile_drafter_id": str(raw.get("profile_drafter_id") or "").strip(),
                "confidence_tier": str(raw.get("confidence_tier") or "").strip(),
                "gate_terminal": str(raw.get("gate_terminal") or "").strip(),
                "gate_reason": str(raw.get("gate_reason") or "").strip(),
                "compat_status": str(raw.get("compat_status") or "").strip(),
                "compat_reason_summary": str(raw.get("compat_reason_summary") or "").strip(),
                "best_for": str(raw.get("best_for") or "").strip(),
                "quality_summary": str(raw.get("quality_summary") or "").strip(),
                "caveats": str(raw.get("caveats") or "").strip(),
                "created_at": str(raw.get("created_at") or "").strip(),
                "host_model_dir": str(raw.get("host_model_dir") or "").strip(),
                "install_command": str(raw.get("install_command") or "").strip(),
                "install_reason": str(raw.get("install_reason") or "").strip(),
                "compose_meta": dict(raw.get("compose_meta") or {}),
            }
        )
    return rows


def read_custom_model_registry():
    return [dict(row) for row in _read_custom_model_registry()]


def write_custom_model_registry(rows):
    clean = []
    seen = set()
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        record_id = _selector_token(raw.get("id") or raw.get("model_id") or raw.get("slug") or "")
        if not record_id or record_id in seen:
            continue
        seen.add(record_id)
        selector = str(raw.get("selector") or f"custom/{record_id}").strip() or f"custom/{record_id}"
        compose_path = os.path.normpath(str(raw.get("compose_path") or "").strip())
        clean.append(
            {
                "id": record_id,
                "selector": selector,
                "slug": str(raw.get("slug") or "").strip(),
                "model_id": str(raw.get("model_id") or f"custom-{record_id}").strip() or f"custom-{record_id}",
                "display_name": str(raw.get("display_name") or raw.get("slug") or record_id).strip() or record_id,
                "profile_like": str(raw.get("profile_like") or "").strip(),
                "compose_path": compose_path,
                "compose_rel_path": _normalize_compose_rel_path(raw.get("compose_rel_path")),
                "inventory_origin": str(raw.get("inventory_origin") or "custom_registry").strip() or "custom_registry",
                "registry_key": str(raw.get("registry_key") or selector).strip() or selector,
                "profile_model_id": str(raw.get("profile_model_id") or "").strip(),
                "profile_engine_id": str(raw.get("profile_engine_id") or "").strip(),
                "profile_workload_id": str(raw.get("profile_workload_id") or "").strip(),
                "profile_drafter_id": str(raw.get("profile_drafter_id") or "").strip(),
                "confidence_tier": str(raw.get("confidence_tier") or "").strip(),
                "gate_terminal": str(raw.get("gate_terminal") or "").strip(),
                "gate_reason": str(raw.get("gate_reason") or "").strip(),
                "compat_status": str(raw.get("compat_status") or "").strip(),
                "compat_reason_summary": str(raw.get("compat_reason_summary") or "").strip(),
                "best_for": str(raw.get("best_for") or "").strip(),
                "quality_summary": str(raw.get("quality_summary") or "").strip(),
                "caveats": str(raw.get("caveats") or "").strip(),
                "created_at": str(raw.get("created_at") or "").strip(),
                "host_model_dir": str(raw.get("host_model_dir") or "").strip(),
                "install_command": str(raw.get("install_command") or "").strip(),
                "install_reason": str(raw.get("install_reason") or "").strip(),
                "compose_meta": dict(raw.get("compose_meta") or {}),
            }
        )
    write_json_atomic_if_changed(CUSTOM_MODELS_FILE, clean, indent=2, sort_keys=True)
    return clean


def _load_repo_env_map():
    env_path = os.path.join(CLUB3090_DIR, ".env")
    result = {}
    try:
        with open(env_path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = str(raw_line or "").strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = str(key or "").strip()
                if not key:
                    continue
                value = str(value or "").strip().strip("'").strip('"')
                result[key] = value
    except Exception:
        return {}
    return result


def _repo_subprocess_env():
    env = os.environ.copy()
    for key, value in _load_repo_env_map().items():
        if key:
            env[str(key)] = str(value)
    return env


def _resolve_variant_model_dir_root(variant=None):
    row = variant if isinstance(variant, dict) else {}
    host_model_dir = str(row.get("host_model_dir") or "").strip()
    if host_model_dir:
        return os.path.normpath(host_model_dir)
    env_map = _load_repo_env_map()
    raw = str(env_map.get("MODEL_DIR") or "").strip()
    if not raw:
        return os.path.join(CLUB3090_DIR, "models-cache")
    if os.path.isabs(raw):
        return raw
    compose_root = str(row.get("compose_project_dir_abs_path") or "").strip()
    if compose_root:
        return os.path.normpath(os.path.join(compose_root, raw))
    return os.path.normpath(os.path.join(CLUB3090_DIR, raw))


def _dir_has_filetype(path, suffixes):
    try:
        if not os.path.isdir(path):
            return False
        for root, _dirs, files in os.walk(path):
            for name in files:
                lower = str(name or "").lower()
                if any(lower.endswith(sfx) for sfx in suffixes):
                    return True
    except Exception:
        return False
    return False


def _gpu_selector_from_env(env_map):
    source = env_map if isinstance(env_map, dict) else {}
    for key in ("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "CLUB3090_GPU"):
        value = str(source.get(key) or "").strip()
        if value and value not in {"all", "void"}:
            return value
    return ""


def _gpu_selector_indices(selector):
    values = []
    for token in str(selector or "").split(","):
        token = token.strip()
        if not token or not token.isdigit():
            continue
        values.append(int(token))
    return values


def _probe_host_gpus(timeout=8):
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.free,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=max(1, int(timeout or 8)),
        )
    except Exception:
        return []
    rows = []
    for raw_line in str(out or "").splitlines():
        parts = [part.strip() for part in raw_line.split(",")]
        if len(parts) < 5:
            continue
        idx_text, name, mem_total_text, mem_free_text, sm = parts[:5]
        if not idx_text.isdigit():
            continue
        try:
            rows.append(
                {
                    "index": int(idx_text),
                    "name": name,
                    "memory_total_mib": int(float(mem_total_text or 0)),
                    "memory_free_mib": int(float(mem_free_text or 0)),
                    "compute_cap": sm,
                }
            )
        except Exception:
            continue
    return rows


def _compute_capability_rank(value):
    text = str(value or "").strip().lower().replace("sm_", "")
    if not text:
        return 0
    if "." in text:
        major, minor = text.split(".", 1)
    else:
        major, minor = text, "0"
    major = re.sub(r"[^0-9]", "", major)
    minor = re.sub(r"[^0-9]", "", minor)
    if not major:
        return 0
    if not minor:
        minor = "0"
    if len(minor) == 1:
        minor = minor + "0"
    return int(major) * 100 + int(minor[:2])


def detect_nvlink_status(force=False, max_age=30):
    now = time.time()
    with slow_cache_lock:
        cached = dict(nvlink_status_cache.get("value") or {})
        cached_time = float(nvlink_status_cache.get("time") or 0.0)
    if cached and not force and cached_time and now - cached_time < max(5.0, float(max_age or 30)):
        return cached

    result = {
        "present": False,
        "active_link_count": 0,
        "gpu_links": {},
        "source": "unavailable",
    }
    if not shutil.which("nvidia-smi"):
        return result

    try:
        out = subprocess.check_output(
            ["nvidia-smi", "nvlink", "--status"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=6,
        )
        current_gpu = None
        gpu_links = {}
        active_links = 0
        for raw_line in str(out or "").splitlines():
            line = str(raw_line or "").strip()
            if not line:
                continue
            gpu_match = re.match(r"^GPU\s+([0-9]+):", line, flags=re.I)
            if gpu_match:
                current_gpu = gpu_match.group(1)
                gpu_links.setdefault(current_gpu, 0)
                continue
            link_match = re.match(r"^Link\s+[0-9]+\s*:\s*(.+)$", line, flags=re.I)
            if not link_match or current_gpu is None:
                continue
            detail = str(link_match.group(1) or "").strip().lower()
            if any(token in detail for token in ("inactive", "not supported", "disabled", "down")):
                continue
            gpu_links[current_gpu] = int(gpu_links.get(current_gpu, 0) or 0) + 1
            active_links += 1
        result = {
            "present": bool(active_links > 0),
            "active_link_count": int(active_links),
            "gpu_links": gpu_links,
            "source": "nvidia-smi-nvlink",
        }
    except Exception:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "topo", "-m"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=6,
            )
            present = bool(re.search(r"\bNV(?:L|[0-9]+)\b", str(out or "")))
            result = {
                "present": present,
                "active_link_count": 0,
                "gpu_links": {},
                "source": "nvidia-smi-topo",
            }
        except Exception:
            result = {
                "present": False,
                "active_link_count": 0,
                "gpu_links": {},
                "source": "unavailable",
            }

    with slow_cache_lock:
        nvlink_status_cache["value"] = dict(result)
        nvlink_status_cache["time"] = time.time()
    return result


def _apply_variant_hardware_guard(spec, env_map):
    spec_map = spec if isinstance(spec, dict) else {}
    env = dict(env_map or {})
    min_vram_gb = int(spec_map.get("requires_min_vram_gb") or 0)
    min_gpu_count = int(spec_map.get("requires_min_gpu_count") or 0)
    tensor_parallel = int(spec_map.get("tensor_parallel") or 0)
    scope_kind = str(spec_map.get("scope_kind") or "").strip().lower()
    required_sm = str(spec_map.get("requires_sm") or "").strip()
    nvlink_mode = str(spec_map.get("nvlink_mode") or "").strip().lower()
    if min_vram_gb <= 0 and min_gpu_count <= 0 and tensor_parallel <= 0 and not required_sm and not nvlink_mode:
        return env

    if nvlink_mode == "required" and not detect_nvlink_status().get("present"):
        raise RuntimeError(
            f"{spec_map.get('selector') or spec_map.get('variant_id') or 'Selected preset'} requires an active NVLink bridge,"
            " but no active NVLink links were detected on this host."
        )

    gpu_rows = _probe_host_gpus(timeout=8)
    if not gpu_rows:
        return env

    selector = _gpu_selector_from_env(env)
    explicit_indices = _gpu_selector_indices(selector)
    selected_rows = [row for row in gpu_rows if not explicit_indices or row["index"] in explicit_indices]
    if explicit_indices and not selected_rows:
        raise RuntimeError(f"GPU selector '{selector}' did not match any detected GPU index.")

    required_sm_rank = _compute_capability_rank(required_sm)
    if tensor_parallel <= 1 and scope_kind not in {"dual", "multi", "global_only"} and not explicit_indices:
        eligible = [
            row for row in gpu_rows
            if int(math.ceil((row.get("memory_total_mib") or 0) / 1024.0)) >= min_vram_gb
            and _compute_capability_rank(row.get("compute_cap")) >= required_sm_rank
        ]
        if not eligible:
            raise RuntimeError(
                f"{spec_map.get('selector') or spec_map.get('variant_id') or 'Selected preset'} requires one GPU with at least {min_vram_gb} GB VRAM"
                + (f" and sm_{required_sm}" if required_sm else "")
                + ", but no eligible GPU was detected."
            )
        best = max(
            eligible,
            key=lambda row: (
                int(row.get("memory_total_mib") or 0),
                _compute_capability_rank(row.get("compute_cap")),
                -int(row.get("index") or 0),
            ),
        )
        chosen = str(int(best["index"]))
        env["CLUB3090_GPU"] = chosen
        env["ESTATE_GPUS"] = chosen
        env["CUDA_VISIBLE_DEVICES"] = "0"
        env["NVIDIA_VISIBLE_DEVICES"] = "0"
        selected_rows = [best]
    elif not selected_rows:
        selected_rows = list(gpu_rows)

    if min_gpu_count > 0 and len(selected_rows) < min_gpu_count:
        raise RuntimeError(
            f"{spec_map.get('selector') or spec_map.get('variant_id') or 'Selected preset'} requires {min_gpu_count} visible GPU(s), but only {len(selected_rows)} matched the current selector."
        )

    too_small = []
    wrong_sm = []
    low_free = []
    for row in selected_rows:
        total_gb = int(math.ceil((row.get("memory_total_mib") or 0) / 1024.0))
        if min_vram_gb > 0 and total_gb < min_vram_gb and tensor_parallel <= 1:
            too_small.append(row)
        if required_sm_rank > 0 and _compute_capability_rank(row.get("compute_cap")) < required_sm_rank:
            wrong_sm.append(row)
        total_mib = int(row.get("memory_total_mib") or 0)
        free_mib = int(row.get("memory_free_mib") or 0)
        if total_mib > 0 and free_mib < int(total_mib * 0.8):
            low_free.append(row)

    if too_small:
        row = too_small[0]
        raise RuntimeError(
            f"{spec_map.get('selector') or spec_map.get('variant_id') or 'Selected preset'} requires at least {min_vram_gb} GB VRAM on the selected GPU,"
            f" but GPU {row['index']} exposes only {int(math.ceil((row.get('memory_total_mib') or 0) / 1024.0))} GB."
        )
    if wrong_sm:
        row = wrong_sm[0]
        raise RuntimeError(
            f"{spec_map.get('selector') or spec_map.get('variant_id') or 'Selected preset'} requires sm_{required_sm}+,"
            f" but GPU {row['index']} reports sm_{row.get('compute_cap') or 'unknown'}."
        )
    if low_free:
        details = ", ".join(
            f"GPU {row['index']} free {int(row.get('memory_free_mib') or 0)} / {int(row.get('memory_total_mib') or 0)} MiB"
            for row in low_free
        )
        raise RuntimeError(
            "GPU memory pre-flight failed before launch. Something is still pinning GPU memory: " + details
        )
    host_visible_devices = ",".join(str(int(row.get("index") or 0)) for row in selected_rows)
    container_visible_devices = _container_local_gpu_ordinals(selected_rows)
    if host_visible_devices:
        env["ESTATE_GPUS"] = host_visible_devices
    if container_visible_devices:
        env["CUDA_VISIBLE_DEVICES"] = container_visible_devices
        env["NVIDIA_VISIBLE_DEVICES"] = container_visible_devices
    return env


def _extract_default_number(raw, minimum_digits=2):
    text = str(raw or "")
    match = re.search(r"\$\{[^}:]+:-([0-9]{%d,})\}" % int(minimum_digits), text)
    if match:
        return int(match.group(1))
    match = re.search(r"([0-9]{%d,})" % int(minimum_digits), text)
    if match:
        return int(match.group(1))
    return None


def _extract_shell_default_value(raw):
    text = str(raw or "").strip().strip('"').strip("'")
    if not text:
        return ""

    def repl(match):
        return str(match.group(1) or "").strip()

    text = re.sub(r"\$\{[^}:]+:-([^}]+)\}", repl, text)
    return text.strip()


def _extract_token_count(raw):
    text = str(raw or "").strip()
    if not text:
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMB])?\b", text, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    suffix = str(match.group(2) or "").upper()
    scale = {"": 1, "K": 1000, "M": 1000 * 1000, "B": 1000 * 1000 * 1000}.get(suffix, 1)
    try:
        return int(value * scale)
    except Exception:
        return None


def _category_for_variant(topology, status_kind):
    topology_text = str(topology or "").strip().lower()
    if status_kind in {"experimental", "preview", "upstream_gated", "deprecated", "tombstoned", "blocked"}:
        return "experimental"
    if topology_text.startswith("single"):
        return "single"
    if topology_text.startswith("dual"):
        return "dual"
    if topology_text.startswith("multi"):
        return "multi"
    return "experimental"


def _scope_kind_for_topology(topology):
    topology_text = str(topology or "").strip().lower()
    if topology_text.startswith("single"):
        return "single"
    if topology_text.startswith("dual"):
        return "dual"
    if topology_text.startswith("multi"):
        return "multi"
    return "global_only"


def _read_compose_profile_header(path):
    profile = {}
    current_key = None
    in_profile = False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = str(raw_line or "").rstrip("\n")
                stripped = line.lstrip()
                if not stripped.startswith("#"):
                    if in_profile and profile:
                        break
                    continue
                comment = stripped[1:]
                if "Profile (at-a-glance)" in comment:
                    in_profile = True
                    current_key = None
                    continue
                if not in_profile:
                    continue
                if profile and re.match(r"^\s*-{8,}\s*$", comment):
                    break
                match = re.match(r"^\s*([A-Za-z][A-Za-z0-9 /-]*):\s*(.*)$", comment)
                if match:
                    current_key = re.sub(r"[^a-z0-9]+", "_", match.group(1).strip().lower()).strip("_")
                    profile[current_key] = match.group(2).strip()
                    continue
                if current_key and re.match(r"^\s{10,}\S", comment):
                    extra = comment.strip()
                    if extra:
                        profile[current_key] = (profile.get(current_key, "") + " " + extra).strip()
                    continue
                if profile:
                    break
    except Exception:
        return {}
    return profile


def _read_compose_status_hints(path, max_lines=160):
    hints = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for idx, raw_line in enumerate(f):
                if idx >= int(max_lines):
                    break
                line = str(raw_line or "").strip()
                if not line.startswith("#"):
                    continue
                match = re.match(r"^#\s*Status:\s*(.+)$", line)
                if match:
                    hints.append(match.group(1).strip())
    except Exception:
        return ""
    return hints[0].strip() if hints else ""


def _read_compose_hardware_metadata(path, max_lines=120):
    fields = {
        "requires_min_vram_gb": 0,
        "requires_min_gpu_count": 0,
        "tensor_parallel": 0,
        "requires_sm": "",
        "engine_profile": "",
        "nvlink_mode": "",
    }
    key_map = {
        "requires-min-vram-gb": "requires_min_vram_gb",
        "requires-min-gpu-count": "requires_min_gpu_count",
        "tensor-parallel": "tensor_parallel",
        "requires-sm": "requires_sm",
        "engine-profile": "engine_profile",
        "requires-nvlink": "nvlink_mode",
        "nvlink-mode": "nvlink_mode",
        "nvlink": "nvlink_mode",
    }
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for idx, raw_line in enumerate(f):
                if idx >= int(max_lines):
                    break
                line = str(raw_line or "").strip()
                if not line.startswith("#"):
                    continue
                lowered_line = line.lower()
                match = re.match(r"^#\s*([A-Za-z0-9_-]+)\s*:\s*(.+?)\s*$", line)
                if not match:
                    if not fields.get("nvlink_mode") and "nvlink" in lowered_line:
                        if any(token in lowered_line for token in ("no nvlink", "without nvlink", "nvlink disabled", "nvlink off")):
                            fields["nvlink_mode"] = ""
                        elif any(token in lowered_line for token in ("auto-detected", "auto detected", "auto-detect", "automatic", "capable", "optional")):
                            fields["nvlink_mode"] = "capable"
                        elif any(token in lowered_line for token in ("required", "requires", "bridge")):
                            fields["nvlink_mode"] = "required"
                    continue
                target_key = key_map.get(str(match.group(1) or "").strip().lower())
                if not target_key:
                    if not fields.get("nvlink_mode") and "nvlink" in lowered_line:
                        if any(token in lowered_line for token in ("no nvlink", "without nvlink", "nvlink disabled", "nvlink off")):
                            fields["nvlink_mode"] = ""
                        elif any(token in lowered_line for token in ("auto-detected", "auto detected", "auto-detect", "automatic", "capable", "optional")):
                            fields["nvlink_mode"] = "capable"
                        elif any(token in lowered_line for token in ("required", "requires", "bridge")):
                            fields["nvlink_mode"] = "required"
                    continue
                value = str(match.group(2) or "").strip()
                if target_key in {"requires_min_vram_gb", "requires_min_gpu_count", "tensor_parallel"}:
                    fields[target_key] = int(_extract_default_number(value) or 0)
                elif target_key == "nvlink_mode":
                    lowered = value.lower()
                    if any(token in lowered for token in ("required", "requires", "bridge")):
                        fields[target_key] = "required"
                    elif any(token in lowered for token in ("auto", "automatic", "capable", "optional")):
                        fields[target_key] = "capable"
                    elif lowered in {"no", "none", "false", "off"}:
                        fields[target_key] = ""
                    else:
                        fields[target_key] = lowered
                else:
                    fields[target_key] = value
                if target_key != "nvlink_mode" and not fields.get("nvlink_mode") and "nvlink" in lowered_line:
                    if any(token in lowered_line for token in ("no nvlink", "without nvlink", "nvlink disabled", "nvlink off")):
                        fields["nvlink_mode"] = ""
                    elif any(token in lowered_line for token in ("auto-detected", "auto detected", "auto-detect", "automatic", "capable", "optional")):
                        fields["nvlink_mode"] = "capable"
                    elif any(token in lowered_line for token in ("required", "requires", "bridge")):
                        fields["nvlink_mode"] = "required"
    except Exception:
        return dict(fields)
    if not fields.get("nvlink_mode"):
        rel = str(path or "").replace("\\", "/").lower()
        if "/nvlink" in rel or rel.endswith("nvlink.yml") or "nvlink-" in rel:
            fields["nvlink_mode"] = "required"
    return dict(fields)


def _read_compose_runtime_metadata(path):
    service_name = ""
    container_name = ""
    default_port = None
    served_model_name = ""
    max_model_len = None
    model_path = ""
    mmproj_path = ""
    speculative_json = ""
    draft_model_path = ""
    command_items = []
    in_command = False
    in_ports = False
    command_block_mode = ""
    current_indent = 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = str(raw_line or "").rstrip("\n")
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                indent = len(line) - len(line.lstrip(" "))
                stripped = line.strip()
                if stripped == "services:":
                    continue
                if not service_name and indent == 2 and stripped.endswith(":"):
                    service_name = stripped[:-1]
                    continue
                if indent <= 4 and not stripped.startswith("- "):
                    in_command = False
                    in_ports = False
                    command_block_mode = ""
                if stripped.startswith("command:"):
                    command_value = stripped.split(":", 1)[1].strip()
                    in_command = True
                    current_indent = indent
                    command_block_mode = ""
                    if command_value:
                        if command_value.startswith("[") and command_value.endswith("]"):
                            try:
                                inline_items = json.loads(command_value)
                            except Exception:
                                inline_items = []
                            for item in inline_items:
                                text = str(item or "").strip()
                                if text:
                                    command_items.append(text)
                        elif command_value in {"|-", "|", ">-", ">"}:
                            command_block_mode = command_value[0]
                        else:
                            command_items.extend(shlex.split(command_value))
                    continue
                if stripped == "ports:":
                    in_ports = True
                    current_indent = indent
                    continue
                if in_command and indent > current_indent:
                    if stripped.startswith("- "):
                        item = stripped[2:].strip()
                        if len(item) >= 2 and item[0] == item[-1] and item[0] in {"'", '"'}:
                            item = item[1:-1]
                        if item in {"|-", "|", ">-", ">"}:
                            command_block_mode = item[0]
                            continue
                        command_items.append(item)
                        continue
                    if command_block_mode:
                        block_line = stripped[:-1].rstrip() if stripped.endswith("\\") else stripped
                        if block_line:
                            command_items.extend(shlex.split(block_line))
                        continue
                if in_ports and indent > current_indent and stripped.startswith("- "):
                    port_item = stripped[2:].strip().strip('"').strip("'")
                    parsed_port = _extract_default_number(port_item, minimum_digits=2)
                    if parsed_port is not None and default_port is None:
                        default_port = parsed_port
                    continue
                if not container_name:
                    match = re.match(r"^container_name:\s*(.+)$", stripped)
                    if match:
                        container_name = match.group(1).strip().strip('"').strip("'")
                        continue
    except Exception:
        return {}
    for idx, item in enumerate(command_items):
        if item == "--model" and idx + 1 < len(command_items):
            model_path = _extract_shell_default_value(command_items[idx + 1])
        elif item.startswith("--model="):
            model_path = _extract_shell_default_value(item.split("=", 1)[1])
        if item == "--model-path" and idx + 1 < len(command_items):
            model_path = _extract_shell_default_value(command_items[idx + 1])
        elif item.startswith("--model-path="):
            model_path = _extract_shell_default_value(item.split("=", 1)[1])
        if item == "-m" and idx + 1 < len(command_items):
            model_path = _extract_shell_default_value(command_items[idx + 1])
        elif item.startswith("-m="):
            model_path = _extract_shell_default_value(item.split("=", 1)[1])
        if item == "--served-model-name" and idx + 1 < len(command_items):
            served_model_name = command_items[idx + 1]
        elif item.startswith("--served-model-name="):
            served_model_name = item.split("=", 1)[1]
        if item == "--max-model-len" and idx + 1 < len(command_items):
            max_model_len = _extract_default_number(command_items[idx + 1], minimum_digits=4)
        elif item.startswith("--max-model-len="):
            max_model_len = _extract_default_number(item.split("=", 1)[1], minimum_digits=4)
        if item == "--ctx-size" and idx + 1 < len(command_items) and max_model_len is None:
            max_model_len = _extract_default_number(command_items[idx + 1], minimum_digits=4)
        elif item.startswith("--ctx-size=") and max_model_len is None:
            max_model_len = _extract_default_number(item.split("=", 1)[1], minimum_digits=4)
        if item == "-c" and idx + 1 < len(command_items) and max_model_len is None:
            max_model_len = _extract_default_number(command_items[idx + 1], minimum_digits=4)
        elif item.startswith("-c=") and max_model_len is None:
            max_model_len = _extract_default_number(item.split("=", 1)[1], minimum_digits=4)
        if item == "--mmproj" and idx + 1 < len(command_items):
            mmproj_path = _extract_shell_default_value(command_items[idx + 1])
        elif item.startswith("--mmproj="):
            mmproj_path = _extract_shell_default_value(item.split("=", 1)[1])
        if item in {"--spec-draft-model", "--draft-model"} and idx + 1 < len(command_items):
            draft_model_path = _extract_shell_default_value(command_items[idx + 1])
        elif item.startswith("--spec-draft-model=") or item.startswith("--draft-model="):
            draft_model_path = _extract_shell_default_value(item.split("=", 1)[1])
        if item == "--speculative-draft-model-path" and idx + 1 < len(command_items):
            draft_model_path = _extract_shell_default_value(command_items[idx + 1])
        elif item.startswith("--speculative-draft-model-path="):
            draft_model_path = _extract_shell_default_value(item.split("=", 1)[1])
        if item == "--speculative-config" and idx + 1 < len(command_items):
            speculative_json = command_items[idx + 1]
        elif item.startswith("--speculative-config="):
            speculative_json = item.split("=", 1)[1]
    drafted_tokens = None
    speculative_method = None
    if speculative_json:
        try:
            parsed = json.loads(speculative_json)
            speculative_method = str(parsed.get("method") or "").strip() or None
            drafted_tokens = parsed.get("num_speculative_tokens")
            draft_model_path = str(parsed.get("model") or "").strip()
        except Exception:
            speculative_method = None
            drafted_tokens = None
            draft_model_path = ""
    return {
        "service_name": service_name,
        "container_name": container_name,
        "default_port": default_port,
        "served_model_name": served_model_name,
        "max_model_len": max_model_len,
        "model_path": model_path,
        "mmproj_path": mmproj_path,
        "speculative_method": speculative_method,
        "drafted_tokens": drafted_tokens,
        "draft_model_path": draft_model_path,
    }


def _read_compose_command_text(path):
    command_lines = []
    in_command = False
    command_block_mode = ""
    current_indent = 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = str(raw_line or "").rstrip("\n")
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                indent = len(line) - len(line.lstrip(" "))
                stripped = line.strip()
                if indent <= 4 and not stripped.startswith("- "):
                    in_command = False
                    command_block_mode = ""
                if stripped.startswith("command:"):
                    command_value = stripped.split(":", 1)[1].strip()
                    in_command = True
                    current_indent = indent
                    command_block_mode = ""
                    if command_value in {"|-", "|", ">-", ">"}:
                        command_block_mode = command_value[0]
                    elif command_value:
                        command_lines.append(command_value)
                    continue
                if in_command and indent > current_indent:
                    if stripped.startswith("- "):
                        command_lines.append(stripped[2:].strip())
                        continue
                    if command_block_mode:
                        block_line = stripped
                        if block_line:
                            command_lines.append(block_line)
                        continue
    except Exception:
        return ""
    return "\n".join(command_lines).strip()


def _replace_compose_command_text(compose_text, command_text):
    source = str(compose_text or "")
    replacement = str(command_text or "").strip()
    if not source or not replacement:
        return source
    lines = source.splitlines()
    output = []
    idx = 0
    replaced = False
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        if not replaced and stripped.startswith("command:"):
            indent = len(line) - len(line.lstrip(" "))
            base_indent = " " * indent
            output.append(f"{base_indent}command: >-")
            for command_line in replacement.splitlines():
                text = str(command_line or "").rstrip()
                if text:
                    output.append(f"{base_indent}  {text}")
            idx += 1
            while idx < len(lines):
                next_line = lines[idx]
                next_stripped = next_line.strip()
                next_indent = len(next_line) - len(next_line.lstrip(" "))
                if next_stripped and next_indent <= indent:
                    break
                idx += 1
            replaced = True
            continue
        output.append(line)
        idx += 1
    return "\n".join(output) if replaced else source


def _launch_setting_label(name):
    labels = {
        "TEMPERATURE": "Temperature",
        "TEMP": "Temperature",
        "TOP_P": "Top P",
        "TOP_K": "Top K",
        "MIN_P": "Min P",
        "REPEAT_PENALTY": "Repeat Penalty",
        "REPETITION_PENALTY": "Repeat Penalty",
        "PRESENCE_PENALTY": "Presence Penalty",
        "FREQUENCY_PENALTY": "Frequency Penalty",
        "CTX_SIZE": "Max Context",
        "MAX_MODEL_LEN": "Max Context",
        "MAX_NUM_SEQS": "Max Concurrent Seqs",
        "KV_CACHE_DTYPE": "KV Cache DType",
        "KV_TYPE": "KV Type",
        "BATCH_SIZE": "Batch Size",
        "UBATCH_SIZE": "Micro Batch Size",
        "NP": "Parallel Slots",
        "NGRAM_N_MAX": "Ngram Max Draft",
        "NGRAM_N_MIN": "Ngram Min Accept",
        "NGRAM_SIZE_N": "Ngram Size",
        "MTP_DRAFT_N_MAX": "Mtp Draft N Max",
        "MTP_N_MAX": "MTP Max Draft",
        "DRAFT_P_MIN": "Draft P Min",
        "MTP_P_MIN": "MTP Min Accept",
        "REASONING": "Reasoning",
        "REASONING_FORMAT": "Reasoning Format",
        "IMAGE_MAX_TOKENS": "Image Max Tokens",
        "MMPROJ_FILE": "Vision Projector File",
        "GGUF_FILE": "GGUF File",
        "MODEL_NAME": "Served Model Name",
        "MODEL_DIR_NAME": "Model Directory",
        "TRUST_REMOTE_CODE": "Trust Remote Code",
        "GPU_MEMORY_UTILIZATION": "GPU Memory Utilization",
        "VLLM_ENFORCE_EAGER": "Enforce Eager",
        "CUDA_GRAPH_MODE": "CUDA Graph Mode",
        "ENABLE_THINKING": "Enable Thinking",
        "PRESERVE_THINKING": "Preserve Thinking",
    }
    key = str(name or "").strip().upper()
    if key in labels:
        return labels[key]
    return str(key).replace("_", " ").title()


def _launch_setting_type(name, default_value):
    key = str(name or "").strip().upper()
    value = str(default_value or "").strip().lower()
    if key in {"REASONING", "ENABLE_THINKING", "PRESERVE_THINKING", "TRUST_REMOTE_CODE", "VLLM_ENFORCE_EAGER"}:
        if value in {"0", "1", "true", "false", "on", "off", "yes", "no"}:
            return "boolean"
    if re.fullmatch(r"-?[0-9]+", str(default_value or "").strip()):
        return "integer"
    if re.fullmatch(r"-?[0-9]+\.[0-9]+", str(default_value or "").strip()):
        return "number"
    return "string"


def _sanitize_launch_setting_default(default_value):
    text = str(default_value or "").strip()
    if not text:
        return ""
    text = re.split(r"\s+[—-]\s+|\s*;\s*", text, maxsplit=1)[0].strip()
    text = text.rstrip(").,")
    if re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", text):
        return text
    lowered = text.lower()
    if lowered in {"true", "false", "on", "off", "yes", "no", "0", "1"}:
        return lowered
    return text


def _strip_launch_setting_default_note(description):
    text = str(description or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s*\(default:\s*[^)]*\)", "", text, flags=re.I).strip()
    return re.sub(r"\s{2,}", " ", text).strip()


def _extract_compose_env_defaults(path):
    defaults = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return defaults
    for key, _operator, value in re.findall(r"\$\{([A-Z][A-Z0-9_]*)(:-|-)([^}]*)\}", text):
        clean_key = str(key or "").strip().upper()
        if clean_key and clean_key not in defaults:
            defaults[clean_key] = _sanitize_launch_setting_default(value)
    return defaults


def _launch_setting_sort_rank(name):
    order = {
        "CTX_SIZE": 0,
        "MAX_MODEL_LEN": 0,
        "TEMPERATURE": 10,
        "TEMP": 10,
        "TOP_P": 11,
        "TOP_K": 12,
        "MIN_P": 13,
        "REPEAT_PENALTY": 14,
        "REPETITION_PENALTY": 14,
        "PRESENCE_PENALTY": 15,
        "FREQUENCY_PENALTY": 16,
        "REASONING": 20,
        "REASONING_FORMAT": 21,
        "MAX_NUM_SEQS": 30,
        "GPU_MEMORY_UTILIZATION": 31,
        "KV_CACHE_DTYPE": 32,
        "KV_TYPE": 33,
        "BATCH_SIZE": 40,
        "UBATCH_SIZE": 41,
        "NP": 42,
        "NGRAM_N_MAX": 50,
        "NGRAM_N_MIN": 51,
        "NGRAM_SIZE_N": 52,
        "MTP_DRAFT_N_MAX": 53,
        "MTP_N_MAX": 53,
        "DRAFT_P_MIN": 54,
        "MTP_P_MIN": 54,
    }
    return order.get(str(name or "").strip().upper(), 1000)


def _launch_setting_ignored(name):
    key = str(name or "").strip().upper()
    return key in {
        "MODEL_DIR",
        "PORT",
        "BIND_HOST",
        "ESTATE_PORT",
        "ESTATE_GPUS",
        "ESTATE_CONTAINER",
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "CLUB3090_GPU",
        "IK_LLAMA_IMAGE",
        "LLAMACPP_IMAGE",
        "VLLM_IMAGE",
        "HF_HOME",
        "MODEL",
    }


def _read_compose_launch_settings(path):
    settings = {}
    in_override_block = False
    env_defaults = _extract_compose_env_defaults(path)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for idx, raw_line in enumerate(f):
                if idx > 280:
                    break
                stripped = str(raw_line or "").rstrip("\n")
                comment = stripped.lstrip()
                if "Override defaults via .env or shell:" in comment:
                    in_override_block = True
                    continue
                if not comment.startswith("#"):
                    if in_override_block:
                        break
                    continue
                body = comment[1:].rstrip()
                match = re.match(r"^\s{2,}([A-Z][A-Z0-9_]+)\s+(.+?)$", body)
                if in_override_block and match:
                    key = str(match.group(1) or "").strip().upper()
                    if _launch_setting_ignored(key):
                        continue
                    description = str(match.group(2) or "").strip()
                    default_match = re.search(r"\(default:\s*([^)]+)\)", description, flags=re.I)
                    comment_default = str(default_match.group(1) or "").strip() if default_match else ""
                    default_value = env_defaults.get(key) or _sanitize_launch_setting_default(comment_default)
                    clean_description = _strip_launch_setting_default_note(description).lstrip("-–— ").strip()
                    row = settings.get(key) or {
                        "name": key,
                        "label": _launch_setting_label(key),
                        "type": _launch_setting_type(key, default_value),
                        "default": default_value,
                        "description": clean_description,
                    }
                    if default_value and not row.get("default"):
                        row["default"] = default_value
                        row["type"] = _launch_setting_type(key, default_value)
                    if description and not row.get("description"):
                        row["description"] = clean_description
                    settings[key] = row
                    continue
                if in_override_block and settings:
                    break
    except Exception:
        return []
    rows = sorted(settings.values(), key=lambda row: (_launch_setting_sort_rank(row.get("name")), row.get("label") or row.get("name") or ""))
    return rows


def _parse_switch_variants():
    tag_by_compose = {}
    for key, entry in _load_upstream_compose_registry().items():
        rel_path = _normalize_compose_rel_path((entry or {}).get("compose_path"))
        if key and rel_path:
            tag_by_compose.setdefault(rel_path, key)
    for rel_path, tag in {
        "models/qwen3.6-27b/ik-llama/compose/single/iq4ks-two-stage.yml": "ik-llama/iq4ks-two-stage",
    }.items():
        tag_by_compose.setdefault(rel_path, tag)
    return tag_by_compose


def _qwen_ik_llama_install_state(variant, model_dir_root):
    spec = variant if isinstance(variant, dict) else {}
    compose_abs_path = str(spec.get("compose_abs_path") or "").strip()
    model_subpath = _container_model_subpath(spec.get("model_path"))
    mmproj_subpath = _container_model_subpath(spec.get("mmproj_path"))
    gguf_target_dir = os.path.join(
        model_dir_root,
        os.path.dirname(model_subpath).replace("/", os.sep),
    ) if model_subpath else os.path.join(model_dir_root, "qwen3.6-27b-gguf", "ubergarm-mtp-iq4ks")
    gguf_file_name = os.path.basename(model_subpath) if model_subpath else "Qwen3.6-27B-MTP-IQ4_KS.gguf"
    mmproj_target_dir = os.path.join(
        model_dir_root,
        os.path.dirname(mmproj_subpath).replace("/", os.sep),
    ) if mmproj_subpath else os.path.join(model_dir_root, "qwen3.6-27b-gguf")
    mmproj_file_name = os.path.basename(mmproj_subpath) if mmproj_subpath else "mmproj-F16.gguf"
    gguf_host_path = os.path.join(gguf_target_dir, gguf_file_name)
    mmproj_host_path = os.path.join(mmproj_target_dir, mmproj_file_name)
    needs_mmproj = bool(mmproj_subpath)
    ready = os.path.isfile(gguf_host_path) and (os.path.isfile(mmproj_host_path) if needs_mmproj else True)
    repo_hints = _read_compose_repo_hints(compose_abs_path) if compose_abs_path else {"target": [], "draft": [], "generic": []}
    target_repo = next(
        (repo for repo in repo_hints.get("target") or [] if str(repo or "").strip()),
        next((repo for repo in repo_hints.get("generic") or [] if str(repo or "").strip()), "ubergarm/Qwen3.6-27B-GGUF"),
    )
    commands = [
        f'hf download {target_repo} {shlex.quote(gguf_file_name)} --local-dir "{gguf_target_dir}"',
    ]
    if needs_mmproj:
        mmproj_repo = next(
            (
                repo
                for repo in (repo_hints.get("generic") or [])
                if str(repo or "").strip() and str(repo).strip() != target_repo
            ),
            "unsloth/Qwen3.6-27B-GGUF",
        )
        commands.append(
            f'hf download {mmproj_repo} {shlex.quote(mmproj_file_name)} --local-dir "{mmproj_target_dir}"'
        )
    reason_bits = [model_subpath] if model_subpath else ["qwen3.6-27b-gguf/ubergarm-mtp-iq4ks"]
    if needs_mmproj:
        reason_bits.append(mmproj_subpath or "qwen3.6-27b-gguf/mmproj-F16.gguf")
    return {
        "install_state": "ready" if ready else "requires_download",
        "install_command": " && ".join(commands),
        "install_reason": "" if ready else f"This preset needs model assets under {', '.join(reason_bits)}.",
    }


def _known_hf_download_command(model_dir_root, repo_id, subdir):
    target_dir = os.path.join(model_dir_root, subdir)
    return f'hf download {repo_id} --local-dir "{target_dir}"'


def _preferred_weight_repo_candidates(model_id, weights_variant, repos=None):
    candidates = []
    normalized_variant = _normalize_weight_variant_key(weights_variant)
    key = (str(model_id or "").strip(), normalized_variant)
    if key == ("qwen3.6-35b-a3b", "autoround-int4"):
        candidates.extend(
            [
                "Intel/Qwen3.6-35B-A3B-int4-mixed-AutoRound",
                "Intel/Qwen3.6-35B-A3B-int4-AutoRound",
            ]
        )
    for repo_id in repos or []:
        repo_text = str(repo_id or "").strip()
        if repo_text:
            candidates.append(repo_text)
    return list(dict.fromkeys(candidates))


def _path_has_model_assets(path):
    text = str(path or "").strip()
    if not text:
        return False
    if os.path.isfile(text):
        return True
    return _dir_has_filetype(text, {".safetensors", ".gguf", ".bin", ".pt", ".pth", ".model"})


def _setup_script_supports_model(model_id):
    target = str(model_id or "").strip()
    if not target:
        return False
    setup_path = os.path.join(CLUB3090_DIR, "scripts", "setup.sh")
    try:
        with open(setup_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        return re.search(rf'(?m)^\s*{re.escape(target)}\)\s*$', text) is not None
    except Exception:
        return False


def _profile_weight_meta(model_profiles, model_id, weights_variant):
    models = getattr(model_profiles, "models", {}) if model_profiles is not None else {}
    model = models.get(str(model_id or "").strip()) if isinstance(models, dict) else None
    weights = dict(getattr(model, "weights", {}) or {}) if model is not None else {}
    raw_variant = str(weights_variant or "").strip()
    normalized_variant = _normalize_weight_variant_key(raw_variant)
    meta = dict(weights.get(raw_variant) or {})
    if not meta and normalized_variant:
        meta = dict(weights.get(normalized_variant) or {})
    if not meta and raw_variant:
        underscore_variant = raw_variant.replace("-", "_")
        meta = dict(weights.get(underscore_variant) or {})
    if not meta and normalized_variant:
        underscore_variant = normalized_variant.replace("-", "_")
        meta = dict(weights.get(underscore_variant) or {})
    return model, meta


def _drafter_download_meta(model_profiles, drafter_id):
    drafters = getattr(model_profiles, "drafters", {}) if model_profiles is not None else {}
    drafter = drafters.get(str(drafter_id or "").strip()) if isinstance(drafters, dict) else None
    if drafter is None:
        return {}
    download = getattr(drafter, "download", None)
    if isinstance(download, dict):
        return dict(download)
    return {}


def _drafter_host_subdir(model_profiles, drafter_id):
    drafters = getattr(model_profiles, "drafters", {}) if model_profiles is not None else {}
    drafter = drafters.get(str(drafter_id or "").strip()) if isinstance(drafters, dict) else None
    if drafter is None:
        return ""
    local_model_path = str(getattr(drafter, "local_model_path", None) or "").replace("\\", "/").strip("/")
    if local_model_path:
        return os.path.basename(local_model_path)
    download = _drafter_download_meta(model_profiles, drafter_id)
    repo = str(download.get("hf_repo") or "").strip()
    if repo:
        return repo.rsplit("/", 1)[-1]
    return ""


def _profile_guided_install_state_for_variant(variant, model_dir_root, model_profiles):
    spec = variant if isinstance(variant, dict) else {}
    model_id = str(spec.get("model_id") or "").strip()
    drafter_id = str(spec.get("profile_drafter_id") or spec.get("drafter_profile") or "").strip()
    weights_variant = _normalize_weight_variant_key(spec.get("weights_variant"))
    model, weight_meta = _profile_weight_meta(model_profiles, model_id, weights_variant)
    if model is None and not model_id:
        return None
    target_repos = _preferred_weight_repo_candidates(model_id, weights_variant, (weight_meta or {}).get("hf_repos") or [])

    assets = []
    seen_paths = set()

    def add_asset(role, rel_path, recipe=None, *, fallback_recipe=None, label="", role_drafter_id=""):
        rel_text = str(rel_path or "").replace("\\", "/").strip().strip("/")
        recipe_data = dict(recipe or {})
        if not recipe_data and fallback_recipe:
            recipe_data = dict(fallback_recipe or {})
        if not rel_text and recipe_data:
            subdir = str(recipe_data.get("WEIGHT_SUBDIR") or "").replace("\\", "/").strip().strip("/")
            files = [str(item or "").strip() for item in shlex.split(str(recipe_data.get("WEIGHT_FILES") or "")) if str(item or "").strip()]
            rel_text = f"{subdir}/{files[0]}".strip("/") if files else subdir
        if not rel_text and not recipe_data:
            return
        dedupe_key = f"{role}:{rel_text or str(recipe_data.get('WEIGHT_KEY') or '')}"
        if dedupe_key in seen_paths:
            return
        seen_paths.add(dedupe_key)
        host_path = os.path.join(model_dir_root, rel_text.replace("/", os.sep)) if rel_text else _recipe_subdir_host_path(model_dir_root, recipe_data)
        assets.append(
            {
                "role": role,
                "rel_path": rel_text,
                "host_path": host_path,
                "recipe": recipe_data,
                "ready": _path_has_model_assets(host_path) if host_path else False,
                "label": label or rel_text or str(recipe_data.get("WEIGHT_SUBDIR") or "").strip(),
                "drafter_id": str(role_drafter_id or "").strip(),
            }
        )

    model_subpath = _container_model_subpath(spec.get("model_path"))
    model_recipe = _weight_recipe_from_subpath(model_subpath) or _weight_recipe_from_model_variant(model_id, weights_variant)
    if model_recipe:
        meta_text = " ".join(
            str(value or "").strip().lower()
            for value in (
                (weight_meta or {}).get("force_direct_download"),
                (weight_meta or {}).get("kind"),
                (weight_meta or {}).get("format"),
                (weight_meta or {}).get("verify_glob"),
                model_recipe.get("WEIGHT_KIND"),
                model_recipe.get("WEIGHT_FORMAT"),
                model_recipe.get("WEIGHT_VERIFY_GLOB"),
                model_recipe.get("WEIGHT_FILES"),
            )
        )
        if bool((weight_meta or {}).get("force_direct_download")) or "gguf" in meta_text:
            model_recipe["FORCE_DIRECT_DOWNLOAD"] = True
    if model_recipe and target_repos:
        model_recipe["WEIGHT_REPO_CANDIDATES"] = list(target_repos)
        recipe_repo = str(model_recipe.get("WEIGHT_REPO") or "").strip()
        if not recipe_repo or target_repos[0] != recipe_repo:
            model_recipe["FORCE_DIRECT_DOWNLOAD"] = True
    add_asset(
        "model",
        model_subpath,
        recipe=model_recipe,
        label=model_subpath or str((weight_meta or {}).get("path") or "").strip(),
    )

    draft_subpath = _container_model_subpath(spec.get("draft_model_path"))
    draft_recipe = _weight_recipe_from_subpath(draft_subpath)
    draft_fallback_subdir = _drafter_host_subdir(model_profiles, drafter_id)
    if not draft_recipe and draft_fallback_subdir:
        draft_recipe = _weight_recipe_from_subpath(f"/root/.cache/huggingface/{draft_fallback_subdir}")
    add_asset(
        "draft",
        draft_subpath or draft_fallback_subdir,
        recipe=draft_recipe,
        label=draft_subpath or draft_fallback_subdir,
        role_drafter_id=drafter_id,
    )

    mmproj_subpath = _container_model_subpath(spec.get("mmproj_path"))
    add_asset(
        "mmproj",
        mmproj_subpath,
        recipe=_weight_recipe_from_subpath(mmproj_subpath),
        label=mmproj_subpath,
    )

    if not assets:
        return None

    setup_env = {}
    allow_base_setup = False
    default_weight_variant = _normalize_weight_variant_key(getattr(model, "default_weight_variant", "") if model is not None else "")
    for asset in assets:
        recipe = dict(asset.get("recipe") or {})
        if not recipe:
            if asset["role"] == "model":
                allow_base_setup = True
            continue
        recipe_env = _recipe_setup_env_map(recipe)
        force_direct_download = bool(recipe.get("FORCE_DIRECT_DOWNLOAD"))
        if asset["role"] == "model":
            if not force_direct_download:
                for key, value in recipe_env.items():
                    setup_env[key] = value
            if recipe_env and not force_direct_download:
                allow_base_setup = True
            elif not force_direct_download and default_weight_variant and _normalize_weight_variant_key(recipe.get("WEIGHT_VARIANT")) == default_weight_variant:
                allow_base_setup = True
            continue
        if asset["role"] == "draft":
            for key, value in recipe_env.items():
                if str(key or "").strip().startswith("WITH_"):
                    setup_env[key] = value

    setup_command = _compose_setup_command(model_id, setup_env) if (allow_base_setup or setup_env) else ""
    commands = [setup_command] if setup_command else []
    missing_paths = []

    for asset in assets:
        if not asset.get("ready"):
            missing_paths.append(str(asset.get("label") or asset.get("rel_path") or asset.get("role") or "asset"))
        role = str(asset.get("role") or "").strip()
        recipe = dict(asset.get("recipe") or {})
        if role == "model" and setup_command and not bool(recipe.get("FORCE_DIRECT_DOWNLOAD")):
            continue
        if role == "draft" and _setup_env_covers_drafter(model_id, asset.get("drafter_id"), setup_env):
            continue
        if role == "mmproj" and _setup_env_covers_mmproj(model_id, setup_env):
            continue
        direct_command = _recipe_download_command(model_dir_root, recipe)
        if direct_command and direct_command not in commands:
            commands.append(direct_command)

    if not commands and _setup_script_supports_model(model_id):
        commands.append(f"bash scripts/setup.sh {shlex.quote(model_id)}")

    install_command = " && ".join([cmd for cmd in commands if str(cmd or "").strip()])
    if not install_command and not missing_paths:
        return {
            "install_state": "ready",
            "install_command": "",
            "install_reason": "",
        }
    if not install_command:
        install_reason = (
            f"This preset needs model assets under {', '.join(missing_paths)}."
            if missing_paths
            else f"No install workflow is defined for model {model_id}."
        )
        return {
            "install_state": "unavailable",
            "install_command": "",
            "install_reason": install_reason,
        }
    return {
        "install_state": "ready" if not missing_paths else "requires_download",
        "install_command": install_command,
        "install_reason": "" if not missing_paths else f"This preset needs model assets under {', '.join(missing_paths)}.",
    }


def _read_compose_repo_hints(path, max_lines=220):
    hints = {"target": [], "draft": [], "generic": []}
    repo_pattern = r"([A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]+)"
    seen = {"target": set(), "draft": set(), "generic": set()}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for idx, raw_line in enumerate(f):
                if idx >= int(max_lines):
                    break
                line = str(raw_line or "").strip()
                if not line:
                    continue
                for match in re.finditer(rf"\bhf\s+download\s+{repo_pattern}", line):
                    repo = str(match.group(1) or "").strip()
                    if repo and repo not in seen["generic"]:
                        seen["generic"].add(repo)
                        hints["generic"].append(repo)
                for match in re.finditer(rf"https?://huggingface\.co/{repo_pattern}", line, flags=re.I):
                    repo = str(match.group(1) or "").strip()
                    if repo and repo not in seen["generic"]:
                        seen["generic"].add(repo)
                        hints["generic"].append(repo)
                hf_match = re.search(rf"(?i)\bhf\s*:\s*{repo_pattern}", line)
                if hf_match:
                    repo = str(hf_match.group(1) or "").strip()
                    if repo and repo not in seen["generic"]:
                        seen["generic"].add(repo)
                        hints["generic"].append(repo)
                target_match = re.search(rf"(?i)\btarget\s*:?\s*{repo_pattern}", line)
                if target_match:
                    repo = str(target_match.group(1) or "").strip()
                    if repo and repo not in seen["target"]:
                        seen["target"].add(repo)
                        hints["target"].append(repo)
                    if repo and repo not in seen["generic"]:
                        seen["generic"].add(repo)
                        hints["generic"].append(repo)
                draft_match = re.search(rf"(?i)\bdraft\s*:?\s*{repo_pattern}", line)
                if draft_match:
                    repo = str(draft_match.group(1) or "").strip()
                    if repo and repo not in seen["draft"]:
                        seen["draft"].add(repo)
                        hints["draft"].append(repo)
                    if repo and repo not in seen["generic"]:
                        seen["generic"].add(repo)
                        hints["generic"].append(repo)
    except Exception:
        return hints
    return hints


def _generic_install_state_for_variant(variant, model_dir_root):
    spec = variant if isinstance(variant, dict) else {}
    compose_abs_path = str(spec.get("compose_abs_path") or "").strip()
    model_id = str(spec.get("model_id") or "").strip()
    model_subpath = _container_model_subpath(spec.get("model_path"))
    mmproj_subpath = _container_model_subpath(spec.get("mmproj_path"))
    draft_subpath = _container_model_subpath(spec.get("draft_model_path"))
    required_paths = []
    if model_subpath:
        required_paths.append(("model", model_subpath))
    if draft_subpath:
        required_paths.append(("draft", draft_subpath))
    if mmproj_subpath:
        required_paths.append(("mmproj", mmproj_subpath))
    if not required_paths:
        return {
            "install_state": "unavailable",
            "install_command": "",
            "install_reason": f"No install workflow is defined for model {model_id}.",
        }

    missing_paths = []
    for _label, subpath in required_paths:
        host_path = os.path.join(model_dir_root, subpath.replace("/", os.sep))
        if not _path_has_model_assets(host_path):
            missing_paths.append(subpath)
    if not missing_paths:
        return {
            "install_state": "ready",
            "install_command": "",
            "install_reason": "",
        }

    repo_hints = _read_compose_repo_hints(compose_abs_path) if compose_abs_path else {"target": [], "draft": [], "generic": []}
    commands = []
    target_subdir = _hf_cache_subdir_from_model_path(spec.get("model_path"))
    draft_subdir = _hf_cache_subdir_from_model_path(spec.get("draft_model_path"))
    mmproj_subdir = _hf_cache_subdir_from_model_path(spec.get("mmproj_path"))
    if target_subdir and repo_hints.get("target"):
        commands.append(_known_hf_download_command(model_dir_root, repo_hints["target"][0], target_subdir))
    elif target_subdir and repo_hints.get("generic"):
        commands.append(_known_hf_download_command(model_dir_root, repo_hints["generic"][0], target_subdir))
    if draft_subdir and repo_hints.get("draft"):
        commands.append(_known_hf_download_command(model_dir_root, repo_hints["draft"][0], draft_subdir))
    elif draft_subdir:
        generic_draft = next((repo for repo in repo_hints.get("generic") or [] if repo not in repo_hints.get("target", [])), "")
        if generic_draft:
            commands.append(_known_hf_download_command(model_dir_root, generic_draft, draft_subdir))
    if mmproj_subdir and repo_hints.get("generic"):
        mmproj_repo = next(
            (
                repo for repo in repo_hints.get("generic") or []
                if repo != (repo_hints.get("target") or [""])[0]
            ),
            (repo_hints.get("generic") or [""])[0],
        )
        if mmproj_repo:
            commands.append(_known_hf_download_command(model_dir_root, mmproj_repo, mmproj_subdir))
    install_command = " && ".join(dict.fromkeys([cmd for cmd in commands if cmd]))
    if not install_command and _setup_script_supports_model(model_id):
        install_command = f"bash scripts/setup.sh {shlex.quote(model_id)}"
    if not install_command:
        return {
            "install_state": "unavailable",
            "install_command": "",
            "install_reason": f"This preset needs assets under {', '.join(missing_paths)}, but no generic install recipe could be derived from the upstream compose yet.",
        }
    return {
        "install_state": "requires_download",
        "install_command": install_command,
        "install_reason": f"This preset needs model assets under {', '.join(missing_paths)}.",
    }


def _container_local_gpu_ordinals(indices):
    values = list(indices or [])
    if not values:
        return ""
    return ",".join(str(idx) for idx in range(len(values)))


def _hf_cache_subdir_from_model_path(model_path):
    path = str(model_path or "").replace("\\", "/").strip()
    marker = "/root/.cache/huggingface/"
    if marker in path:
        tail = path.split(marker, 1)[1].strip("/")
        if tail:
            return tail
    return ""


def _container_model_subpath(model_path):
    path = str(model_path or "").replace("\\", "/").strip()
    if not path:
        return ""
    for marker in ("/root/.cache/huggingface/", "/models/"):
        if marker in path:
            tail = path.split(marker, 1)[1].strip("/")
            if tail:
                return tail
    return path.strip("/")


def _detect_variant_install_state(variant, model_dir_root):
    model_id = str((variant or {}).get("model_id") or "").strip()
    if str((variant or {}).get("source_kind") or "").strip().lower() == "custom":
        host_model_dir = str((variant or {}).get("host_model_dir") or "").strip()
        ready = _path_has_model_assets(host_model_dir)
        return {
            "install_state": "ready" if ready else "requires_download",
            "install_command": "",
            "install_reason": "" if ready else (f"Expected imported model assets under {host_model_dir}." if host_model_dir else "Custom model assets are missing from disk."),
        }
    model_profiles = _load_upstream_profiles()
    guided = _profile_guided_install_state_for_variant(variant, model_dir_root, model_profiles)
    if guided:
        return guided

    engine = str((variant or {}).get("engine") or "").strip()
    selector = _mode_selector_for_variant(variant)
    rel_path = _variant_rel_compose_path(variant).lower()
    compose_model_subdir = _hf_cache_subdir_from_model_path((variant or {}).get("model_path"))
    draft_model_subdir = _hf_cache_subdir_from_model_path((variant or {}).get("draft_model_path"))
    base_ready = False
    ready = False
    install_command = ""
    install_reason = ""
    if model_id == "qwen3.6-27b":
        if "/ik-llama/" in rel_path or selector.lower().startswith("ik-llama/"):
            return _qwen_ik_llama_install_state(variant, model_dir_root)
        base_subdir = compose_model_subdir or "qwen3.6-27b-autoround-int4"
        draft_subdir = draft_model_subdir or "qwen3.6-27b-dflash"
        base_ready = _dir_has_filetype(os.path.join(model_dir_root, base_subdir), {".safetensors"})
        dflash_ready = _dir_has_filetype(os.path.join(model_dir_root, draft_subdir), {".safetensors"})
        gguf_roots = [
            os.path.join(model_dir_root, "qwen3.6-27b-gguf"),
            os.path.join(model_dir_root, "qwen3.6-27b"),
        ]
        gguf_file = ""
        mmproj_file = ""
        mmproj_sidecar = ""
        for gguf_root in gguf_roots:
            candidate = os.path.join(gguf_root, "unsloth-mtp-q4km", "Qwen3.6-27B-Q4_K_M.gguf")
            if not os.path.isfile(candidate):
                candidate = os.path.join(gguf_root, "unsloth-q3kxl", "Qwen3.6-27B-UD-Q3_K_XL.gguf")
            sidecar = os.path.join(gguf_root, "unsloth-mtp-q4km", "mmproj-F16.gguf")
            if not os.path.isfile(sidecar):
                sidecar = os.path.join(gguf_root, "unsloth-q3kxl", "mmproj-F16.gguf")
            root_mmproj = os.path.join(gguf_root, "mmproj-F16.gguf")
            if os.path.isfile(candidate):
                gguf_file = candidate
                mmproj_file = root_mmproj
                mmproj_sidecar = sidecar
                break
        llama_ready = os.path.isfile(gguf_file) and (os.path.isfile(mmproj_file) or os.path.isfile(mmproj_sidecar))
        if engine == "llamacpp":
            ready = llama_ready
            install_command = "WEIGHTS=gguf bash scripts/setup.sh qwen3.6-27b"
            install_reason = "GGUF and mmproj assets are required for Qwen llama.cpp variants."
        elif compose_model_subdir and compose_model_subdir != "qwen3.6-27b-autoround-int4":
            return _generic_install_state_for_variant(variant, model_dir_root)
        elif "dflash" in selector.lower() or "dflash" in rel_path:
            ready = base_ready and dflash_ready
            install_command = "WITH_DFLASH_DRAFT=1 bash scripts/setup.sh qwen3.6-27b"
            install_reason = "This preset needs the base Qwen weights plus the Qwen DFlash draft model."
        else:
            ready = base_ready
            install_command = "bash scripts/setup.sh qwen3.6-27b"
            install_reason = "This preset needs the base Qwen vLLM weights."
    elif model_id == "gemma-4-31b":
        base_subdir = compose_model_subdir or "gemma-4-31b-autoround-int4"
        draft_subdir = draft_model_subdir or "gemma-4-31b-it-dflash"
        base_ready = _dir_has_filetype(os.path.join(model_dir_root, base_subdir), {".safetensors"})
        assistant_ready = _dir_has_filetype(os.path.join(model_dir_root, "gemma-4-31b-it-assistant"), {".safetensors"})
        dflash_ready = _dir_has_filetype(os.path.join(model_dir_root, draft_subdir), {".safetensors"})
        if compose_model_subdir == "gemma-4-31b-it-AWQ-4bit":
            awq_ready = _dir_has_filetype(os.path.join(model_dir_root, compose_model_subdir), {".safetensors"})
            ready = awq_ready and assistant_ready
            install_command = (
                _known_hf_download_command(model_dir_root, "cyankiwi/gemma-4-31B-it-AWQ-4bit", compose_model_subdir)
                + f' && {_known_hf_download_command(model_dir_root, "google/gemma-4-31B-it-assistant", "gemma-4-31b-it-assistant")}'
            )
            install_reason = "This preset needs the Gemma AWQ weights plus the official Gemma assistant drafter."
        elif "dflash" in selector.lower() or "dflash" in rel_path:
            ready = base_ready and dflash_ready
            install_command = "WITH_DFLASH_DRAFT=1 bash scripts/setup.sh gemma-4-31b"
            install_reason = "This preset needs the base Gemma weights plus the Gemma DFlash drafter."
        elif compose_model_subdir and compose_model_subdir != "gemma-4-31b-autoround-int4":
            return _generic_install_state_for_variant(variant, model_dir_root)
        else:
            ready = base_ready and assistant_ready
            install_command = "bash scripts/setup.sh gemma-4-31b"
            install_reason = "This preset needs the base Gemma weights plus the official Gemma assistant drafter."
    else:
        return _generic_install_state_for_variant(variant, model_dir_root)
    return {
        "install_state": "ready" if ready else "requires_download",
        "install_command": install_command,
        "install_reason": "" if ready else install_reason,
    }


def ensure_variant_install_ready(variant):
    spec = variant if isinstance(variant, dict) else {}
    model_dir_root = _resolve_variant_model_dir_root(spec)
    state = _detect_variant_install_state(spec, model_dir_root)
    install_state = str(state.get("install_state") or "").strip().lower()
    if install_state == "ready":
        return
    selector = canonical_mode_selector(_mode_selector_for_variant(spec) or spec.get("selector") or spec.get("upstream_tag") or spec.get("variant_id"))
    reason = str(state.get("install_reason") or "").strip()
    install_command = str(state.get("install_command") or "").strip()
    details = [f"Required model assets for {selector or 'this preset'} are not ready under {model_dir_root}."]
    if reason:
        details.append(reason)
    if install_command:
        details.append(f"Run from {CLUB3090_DIR}: {install_command}")
    raise RuntimeError("\n".join(details))


def _install_state_satisfied_by_resource_roles(entry):
    variant = entry if isinstance(entry, dict) else {}
    resources = [dict(row or {}) for row in (variant.get("resources") or []) if isinstance(row, dict)]
    if not resources:
        return False
    required_roles = []
    if _container_model_subpath(variant.get("model_path")):
        required_roles.append("model")
    if _container_model_subpath(variant.get("draft_model_path")):
        required_roles.append("draft")
    if _container_model_subpath(variant.get("mmproj_path")):
        required_roles.append("projector")
    if not required_roles:
        return False
    present_roles = {
        ("projector" if str(row.get("role") or "").strip().lower() == "projector" else str(row.get("role") or "").strip().lower())
        for row in resources
        if row.get("exists")
    }
    return all(role in present_roles for role in required_roles)


def _choose_fallback_variant(kind, preferred_model_id="", category=""):
    inventory = load_runtime_inventory()
    variants = list(inventory.get("variants") or [])
    preferred_statuses = {"production", "production_caveat"}
    wanted_model = str(preferred_model_id or "").strip()
    wanted_category = str(category or "").strip()
    candidates = []
    for variant in variants:
        if str(variant.get("scope_kind") or "") != str(kind or ""):
            continue
        status_kind = str(variant.get("status_kind") or "")
        rank = 0 if status_kind in preferred_statuses else 1
        if wanted_category and str(variant.get("category") or "") == wanted_category:
            rank -= 1
        if wanted_model and str(variant.get("model_id") or "") == wanted_model:
            rank -= 2
        candidates.append((rank, _mode_selector_for_variant(variant), variant))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2] if candidates else None


def _profile_weight_status_text(model_profiles, model_id, weights_variant):
    _model, weight_meta = _profile_weight_meta(model_profiles, model_id, weights_variant)
    return str(weight_meta.get("status") or "").strip()


def _variant_status_text(profile, status_hints, registry_key, registry_entry, model_profiles):
    status_text = str((profile or {}).get("status") or "").strip() or str(status_hints or "").strip()
    key_text = " ".join(
        [
            str(registry_key or "").strip().lower(),
            str((registry_entry or {}).get("compose_path") or "").strip().lower(),
            str((registry_entry or {}).get("compose_rel_path") or "").strip().lower(),
        ]
    )
    if _variant_path_forces_experimental(key_text):
        normalized_status = _normalize_status_kind(status_text)
        if normalized_status not in {"blocked", "deprecated", "tombstoned", "upstream_gated"}:
            return "experimental"
    if status_text:
        return status_text
    if "preview" in key_text:
        return "preview"
    if "experimental" in key_text:
        return "experimental"
    if "blocked" in key_text:
        return "hardware-blocked"
    weights_variant = str((registry_entry or {}).get("weights_variant") or "").strip()
    weight_status = _profile_weight_status_text(model_profiles, (registry_entry or {}).get("model"), weights_variant)
    if weight_status:
        return weight_status
    if registry_entry:
        return "production"
    return ""


def _variant_best_for(profile, registry_entry, model_profiles):
    best_for = str((profile or {}).get("best_for") or "").strip()
    if best_for:
        return best_for
    workload_id = str((registry_entry or {}).get("workload") or "").strip()
    workloads = getattr(model_profiles, "workloads", {}) if model_profiles is not None else {}
    workload = workloads.get(workload_id) if isinstance(workloads, dict) else None
    if workload is not None:
        return str(getattr(workload, "display_name", "") or getattr(workload, "description", "") or "").strip()
    return ""


def _variant_quality_summary(profile):
    return str((profile or {}).get("quality") or "").strip()


def _model_summary_from_variants(model_row, variants):
    rows = [row for row in (variants or []) if isinstance(row, dict)]
    if not rows:
        return str((model_row or {}).get("summary") or "").strip()
    topology_labels = []
    if any(str(row.get("topology") or "").strip().lower() == "single" for row in rows):
        topology_labels.append("single-GPU")
    if any(str(row.get("topology") or "").strip().lower() == "dual" for row in rows):
        topology_labels.append("dual-GPU")
    if any(str(row.get("topology") or "").strip().lower() == "multi" for row in rows):
        topology_labels.append("advanced multi-GPU")
    if any(str(row.get("status_kind") or "").strip().lower() == "experimental" for row in rows):
        topology_labels.append("experimental")
    topology_text = ", ".join(topology_labels[:4]) if topology_labels else "preset"
    ctx_values = sorted(
        {
            int(row.get("max_model_len") or 0)
            for row in rows
            if int(row.get("max_model_len") or 0) > 0
        }
    )
    ctx_text = ""
    if ctx_values:
      ctx_text = f" up to {ctx_values[-1] // 1000 if ctx_values[-1] >= 1000 else ctx_values[-1]}K ctx"
      if ctx_values[-1] < 1000:
          ctx_text = f" up to {ctx_values[-1]} ctx"
    best_for_values = []
    for row in rows:
        text = str(row.get("best_for") or "").strip().rstrip(".; ")
        if text and text not in best_for_values:
            best_for_values.append(text)
    description = best_for_values[0] if best_for_values else "curated runtime modes"
    display_name = str((model_row or {}).get("display_name") or (model_row or {}).get("model_id") or "This family").strip()
    return f"{display_name} with {topology_text} presets for {description}{ctx_text}."


def _variant_caveats(profile, registry_entry, model_profiles):
    caveats = str((profile or {}).get("caveats") or "").strip()
    if caveats:
        return caveats
    weight_status = _profile_weight_status_text(
        model_profiles,
        (registry_entry or {}).get("model"),
        (registry_entry or {}).get("weights_variant"),
    )
    if weight_status in {"preview", "experimental", "ampere-blocked"}:
        return weight_status.replace("-", " ")
    return ""


def _model_display_name_from_profiles(model_profiles, model_id):
    models = getattr(model_profiles, "models", {}) if model_profiles is not None else {}
    model = models.get(str(model_id or "").strip()) if isinstance(models, dict) else None
    display_name = str(getattr(model, "display_name", "") or "").strip()
    return display_name or _format_model_display_name(model_id)


def _model_order_rank(model_id, source_kind=""):
    custom = str(source_kind or "").strip().lower() == "custom"
    curated_order = {
        "qwen3.6-27b": 0,
        "gemma-4-31b": 1,
        "qwen3.6-35b-a3b": 2,
        "gemma-4-26b-a4b": 3,
    }
    base_rank = curated_order.get(str(model_id or "").strip(), 90)
    if custom:
        return 200 + base_rank
    return base_rank


def _rebuild_runtime_mode_tables(inventory):
    global MODES, SINGLE_GPU_MODES, DUAL_GPU_MODES, VARIANT_SPECS
    global VARIANT_BY_ID, VARIANT_BY_TAG, VARIANT_BY_CONTAINER, VARIANT_BY_SERVICE, VARIANT_BY_COMPOSE, MODEL_INDEX
    modes = {}
    single_modes = []
    dual_modes = []
    variant_specs = {}
    by_id = {}
    by_tag = {}
    by_container = {}
    by_service = {}
    by_compose = {}
    model_index = {}
    for model in inventory.get("models") or []:
        model_index[str(model.get("model_id") or "")] = dict(model)
    for variant in inventory.get("variants") or []:
        entry = dict(variant)
        selector = _mode_selector_for_variant(entry)
        variant_id = str(entry.get("variant_id") or "").strip()
        compose_rel = _variant_rel_compose_path(entry)
        spec = {
            "variant_id": variant_id,
            "selector": selector,
            "upstream_tag": str(entry.get("upstream_tag") or "").strip() or None,
            "registry_key": str(entry.get("registry_key") or "").strip(),
            "model_id": str(entry.get("model_id") or "").strip(),
            "model_display_name": str(entry.get("model_display_name") or "").strip(),
            "engine": str(entry.get("engine") or "").strip(),
            "engine_display": str(entry.get("engine_display") or entry.get("engine") or "").strip(),
            "engine_profile": str(entry.get("engine_profile") or "").strip(),
            "topology": str(entry.get("topology") or "").strip(),
            "category": str(entry.get("category") or "").strip(),
            "scope_kind": str(entry.get("scope_kind") or "").strip(),
            "compose_rel_path": compose_rel,
            "compose_abs_path": str(entry.get("compose_abs_path") or "").strip(),
            "compose_dir_abs_path": str(entry.get("compose_dir_abs_path") or "").strip(),
            "compose_project_dir_abs_path": str(entry.get("compose_project_dir_abs_path") or "").strip(),
            "service": str(entry.get("service_name") or entry.get("service") or "").strip(),
            "service_name": str(entry.get("service_name") or entry.get("service") or "").strip(),
            "container_name": str(entry.get("container_name") or "").strip(),
            "default_port": int(entry.get("default_port") or 0),
            "served_model_name": str(entry.get("served_model_name") or "").strip(),
            "model_path": str(entry.get("model_path") or "").strip(),
            "draft_model_path": str(entry.get("draft_model_path") or "").strip(),
            "mmproj_path": str(entry.get("mmproj_path") or "").strip(),
            "max_model_len": entry.get("max_model_len"),
            "max_num_seqs": int(entry.get("max_num_seqs") or 0),
            "mem_util": entry.get("mem_util"),
            "drafter": str(entry.get("drafter") or "").strip(),
            "drafter_profile": str(entry.get("drafter_profile") or "").strip(),
            "weights_variant": str(entry.get("weights_variant") or "").strip(),
            "workload_id": str(entry.get("workload_id") or "").strip(),
            "profile_like": str(entry.get("profile_like") or entry.get("registry_key") or "").strip(),
            "kv_format": str(entry.get("kv_format") or "").strip(),
            "vision": str(entry.get("vision") or "").strip(),
            "genesis": str(entry.get("genesis") or "").strip(),
            "status_kind": str(entry.get("status_kind") or "").strip(),
            "status_raw": str(entry.get("status_raw") or "").strip(),
            "quality_summary": str(entry.get("quality_summary") or "").strip(),
            "best_for": str(entry.get("best_for") or "").strip(),
            "caveats": str(entry.get("caveats") or "").strip(),
            "install_state": str(entry.get("install_state") or "").strip(),
            "install_command": str(entry.get("install_command") or "").strip(),
            "install_reason": str(entry.get("install_reason") or "").strip(),
            "speculative_method": entry.get("speculative_method"),
            "drafted_tokens": entry.get("drafted_tokens"),
            "requires_min_vram_gb": int(entry.get("requires_min_vram_gb") or 0),
            "requires_min_gpu_count": int(entry.get("requires_min_gpu_count") or 0),
            "tensor_parallel": int(entry.get("tensor_parallel") or 0),
            "requires_sm": str(entry.get("requires_sm") or "").strip(),
            "nvlink_mode": str(entry.get("nvlink_mode") or "").strip(),
            "host_model_dir": str(entry.get("host_model_dir") or "").strip(),
            "resources": list(entry.get("resources") or []),
            "resource_paths": list(entry.get("resource_paths") or []),
            "resource_size_bytes": int(entry.get("resource_size_bytes") or 0),
            "resource_count": int(entry.get("resource_count") or 0),
            "source_kind": str(entry.get("source_kind") or "").strip() or "curated",
            "inventory_origin": str(entry.get("inventory_origin") or "").strip(),
            "profile_model_id": str(entry.get("profile_model_id") or "").strip(),
            "profile_engine_id": str(entry.get("profile_engine_id") or "").strip(),
            "profile_workload_id": str(entry.get("profile_workload_id") or "").strip(),
            "profile_drafter_id": str(entry.get("profile_drafter_id") or "").strip(),
            "confidence_tier": str(entry.get("confidence_tier") or "").strip(),
            "gate_terminal": str(entry.get("gate_terminal") or "").strip(),
            "gate_reason": str(entry.get("gate_reason") or "").strip(),
            "derived_compose_path": str(entry.get("derived_compose_path") or "").strip(),
            "compat_status": str(entry.get("compat_status") or "").strip(),
            "compat_reason_summary": str(entry.get("compat_reason_summary") or "").strip(),
            "default_engine_switches": str(entry.get("default_engine_switches") or "").strip(),
        }
        for key in {variant_id, selector, compose_rel}:
            if key:
                variant_specs[key] = spec
                if spec["default_port"]:
                    modes[key] = int(spec["default_port"])
        if variant_id:
            by_id[variant_id] = spec
        if spec.get("upstream_tag"):
            by_tag[spec["upstream_tag"]] = spec
        if spec.get("container_name"):
            by_container[spec["container_name"]] = spec
        if spec.get("service_name"):
            by_service[spec["service_name"]] = spec
        if compose_rel:
            by_compose[compose_rel] = spec
        canonical = selector or variant_id
        if spec["scope_kind"] == "single" and canonical:
            single_modes.append(canonical)
        elif spec["scope_kind"] == "dual" and canonical:
            dual_modes.append(canonical)
    MODES = modes
    SINGLE_GPU_MODES = tuple(dict.fromkeys(single_modes))
    DUAL_GPU_MODES = tuple(dict.fromkeys(dual_modes))
    VARIANT_SPECS = variant_specs
    VARIANT_BY_ID = by_id
    VARIANT_BY_TAG = by_tag
    VARIANT_BY_CONTAINER = by_container
    VARIANT_BY_SERVICE = by_service
    VARIANT_BY_COMPOSE = by_compose
    MODEL_INDEX = model_index


def canonical_mode_selector(mode):
    selector = str(mode or "").strip()
    spec = VARIANT_SPECS.get(selector) or VARIANT_BY_TAG.get(selector)
    return str((spec or {}).get("selector") or mode or "").strip()


def resolve_variant_spec(mode):
    selector = str(mode or "").strip()
    if not selector:
        return None
    if not VARIANT_SPECS:
        load_runtime_inventory()
    return (
        VARIANT_SPECS.get(selector)
        or VARIANT_BY_TAG.get(selector)
        or VARIANT_BY_ID.get(selector)
        or VARIANT_BY_COMPOSE.get(selector.replace("\\", "/"))
    )


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


def rebuild_runtime_inventory():
    global runtime_inventory_cache, runtime_inventory_built_at
    repo_root = os.path.abspath(CLUB3090_DIR)
    setattr(_load_upstream_profiles, "_cache", None)
    setattr(_load_upstream_compose_registry, "_cache", None)
    setattr(_load_upstream_weights_reader, "_cache", None)
    tag_by_compose = _parse_switch_variants()
    model_profiles = _load_upstream_profiles()
    compose_registry = _load_upstream_compose_registry()
    try:
        repo_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except Exception:
        repo_head = ""
    try:
        repo_describe = subprocess.check_output(
            ["git", "describe", "--tags", "--dirty", "--always"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except Exception:
        repo_describe = ""
    inventory = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo_root": repo_root,
        "repo_head": repo_head,
        "repo_describe": repo_describe,
        "switch_script_present": os.path.exists(os.path.join(repo_root, "scripts", "switch.sh")),
        "setup_script_present": os.path.exists(os.path.join(repo_root, "scripts", "setup.sh")),
        "launch_script_present": os.path.exists(os.path.join(repo_root, "scripts", "launch.sh")),
        "update_script_present": os.path.exists(os.path.join(repo_root, "scripts", "update.sh")),
        "models": [],
        "variants": [],
        "profile_likes": [],
        "custom_models": read_custom_model_registry(),
    }
    model_rows = {}
    registry_variant_keys = set()

    def ensure_model_row(model_id, display_name="", source_kind="curated", inventory_origin="compose_registry"):
        row = model_rows.setdefault(
            model_id,
            {
                "model_id": model_id,
                "display_name": display_name or _format_model_display_name(model_id),
                "engine_groups": [],
                "installed_state": "missing",
                "setup_supported": False,
                "default_install_command": "",
                "default_install_reason": "",
                "default_install_variant_id": "",
                "categories": {
                    "single": [],
                    "dual": [],
                    "multi": [],
                    "experimental": [],
                },
                "summary": "",
                "source_kind": source_kind,
                "inventory_origin": inventory_origin,
                "custom_model": str(source_kind or "").strip().lower() == "custom",
            },
        )
        if display_name:
            row["display_name"] = display_name
        if str(source_kind or "").strip().lower() == "custom":
            row["source_kind"] = "custom"
            row["inventory_origin"] = inventory_origin or row.get("inventory_origin") or "custom_registry"
            row["custom_model"] = True
        return row

    def append_variant(variant, force_install_state=None):
        entry = dict(variant or {})
        selector = _mode_selector_for_variant(entry)
        variant_id = str(entry.get("variant_id") or "").strip()
        if not selector and not variant_id:
            return
        if selector and not str(entry.get("selector") or "").strip():
            entry["selector"] = selector
        model_id = str(entry.get("model_id") or "").strip()
        if not model_id:
            return
        if force_install_state is None:
            entry.update(_detect_variant_install_state(entry, _resolve_variant_model_dir_root(entry)))
        else:
            entry.update(force_install_state)
        try:
            entry.update(variant_resource_plan_from_row(entry, include_missing=False))
        except Exception:
            entry.setdefault("resources", [])
            entry.setdefault("resource_paths", [])
            entry.setdefault("resource_size_bytes", 0)
            entry.setdefault("resource_count", 0)
        if (
            str(entry.get("install_state") or "").strip() == "requires_download"
            and _install_state_satisfied_by_resource_roles(entry)
        ):
            entry["install_state"] = "ready"
            entry["install_reason"] = ""
        try:
            plan = _monitor_plan_from_variant_install(entry, str(entry.get("install_command") or "").strip())
            entry["source_repo_ids"] = [
                repo_id
                for step in (plan or [])
                for repo_id in (step.get("repo_ids") or [])
                if str(repo_id or "").strip()
            ]
            entry["source_repo_ids"] = list(dict.fromkeys(entry["source_repo_ids"]))
        except Exception:
            entry.setdefault("source_repo_ids", [])
        inventory["variants"].append(entry)
        model_row = ensure_model_row(
            model_id,
            display_name=str(entry.get("model_display_name") or entry.get("display_name") or _model_display_name_from_profiles(model_profiles, model_id)),
            source_kind=entry.get("source_kind") or "curated",
            inventory_origin=entry.get("inventory_origin") or "compose_registry",
        )
        engine = str(entry.get("engine") or "").strip()
        if engine and engine not in model_row["engine_groups"]:
            model_row["engine_groups"].append(engine)
        category = str(entry.get("category") or "").strip()
        if category in model_row["categories"]:
            model_row["categories"][category].append(variant_id)
        if not model_row["summary"]:
            model_row["summary"] = str(entry.get("best_for") or entry.get("quality_summary") or "").strip()

    for registry_key, registry_entry in compose_registry.items():
        compose_rel_path = _normalize_compose_rel_path(registry_entry.get("compose_path"))
        if not compose_rel_path:
            continue
        registry_variant_keys.add(compose_rel_path)
        compose_abs_path = os.path.join(repo_root, compose_rel_path.replace("/", os.sep))
        profile = _read_compose_profile_header(compose_abs_path)
        status_hints = _read_compose_status_hints(compose_abs_path)
        hardware_meta = _read_compose_hardware_metadata(compose_abs_path)
        runtime_meta = _read_compose_runtime_metadata(compose_abs_path)
        model_id = str(registry_entry.get("model") or "").strip()
        engine_family = "vllm" if str(registry_key).startswith("vllm/") else "llamacpp"
        engine_display = _selector_engine_display(registry_key, compose_rel_path)
        topology = _infer_topology_from_compose_path(
            compose_rel_path,
            "multi" if int(registry_entry.get("tp") or 1) > 2 else ("dual" if int(registry_entry.get("tp") or 1) > 1 else "single"),
        )
        status_text = _variant_status_text(profile, status_hints, registry_key, registry_entry, model_profiles)
        if engine_family == "llamacpp":
            max_model_len = int(runtime_meta.get("max_model_len") or _extract_token_count(profile.get("max_ctx") or profile.get("default_ctx")) or registry_entry.get("max_ctx") or 0)
        else:
            max_model_len = int(registry_entry.get("max_ctx") or runtime_meta.get("max_model_len") or _extract_token_count(profile.get("max_ctx") or profile.get("default_ctx")) or 0)
        variant = {
            "variant_id": _variant_id_from_selector(registry_key),
            "upstream_tag": registry_key,
            "registry_key": registry_key,
            "model_id": model_id,
            "model_display_name": _model_display_name_from_profiles(model_profiles, model_id),
            "engine": _normalize_engine(engine_family),
            "engine_display": engine_display,
            "engine_profile": str(registry_entry.get("engine") or hardware_meta.get("engine_profile") or "").strip(),
            "topology": topology,
            "compose_rel_path": compose_rel_path,
            "compose_abs_path": compose_abs_path,
            "compose_dir_abs_path": os.path.dirname(compose_abs_path),
            "compose_project_dir_abs_path": os.path.dirname(compose_abs_path),
            "service_name": runtime_meta.get("service_name") or "",
            "container_name": runtime_meta.get("container_name") or "",
            "default_port": int(registry_entry.get("default_port") or runtime_meta.get("default_port") or 0),
            "served_model_name": runtime_meta.get("served_model_name") or "",
            "max_model_len": max_model_len,
            "max_num_seqs": int(registry_entry.get("max_num_seqs") or 0),
            "mem_util": registry_entry.get("mem_util"),
            "model_path": runtime_meta.get("model_path") or "",
            "mmproj_path": runtime_meta.get("mmproj_path") or "",
            "draft_model_path": runtime_meta.get("draft_model_path") or "",
            "drafter": str(registry_entry.get("drafter") or runtime_meta.get("speculative_method") or profile.get("drafter") or "").strip(),
            "drafter_profile": str(registry_entry.get("drafter") or "").strip(),
            "weights_variant": str(registry_entry.get("weights_variant") or "").strip(),
            "workload_id": str(registry_entry.get("workload") or "").strip(),
            "profile_like": registry_key,
            "kv_format": str(registry_entry.get("kv_format") or profile.get("kv") or "").strip(),
            "vision": str(profile.get("vision") or "").strip(),
            "genesis": str(profile.get("genesis") or "").strip(),
            "status_raw": status_text,
            "status_kind": _normalize_status_kind(status_text),
            "caveats": _variant_caveats(profile, registry_entry, model_profiles),
            "best_for": _variant_best_for(profile, registry_entry, model_profiles),
            "quality_summary": _variant_quality_summary(profile),
            "speculative_method": runtime_meta.get("speculative_method"),
            "drafted_tokens": runtime_meta.get("drafted_tokens"),
            "requires_min_vram_gb": int(hardware_meta.get("requires_min_vram_gb") or 0),
            "requires_min_gpu_count": int(hardware_meta.get("requires_min_gpu_count") or (2 if topology == "dual" else (max(1, int(registry_entry.get("tp") or 1)) if topology == "multi" else 1))),
            "tensor_parallel": int(registry_entry.get("tp") or hardware_meta.get("tensor_parallel") or 0),
            "requires_sm": str(registry_entry.get("required_sm") or hardware_meta.get("requires_sm") or "").strip(),
            "nvlink_mode": ("required" if registry_entry.get("requires_nvlink") else str(hardware_meta.get("nvlink_mode") or "").strip()),
            "source_kind": "curated",
            "inventory_origin": "compose_registry",
            "profile_model_id": model_id,
            "profile_engine_id": str(registry_entry.get("engine") or "").strip(),
            "profile_workload_id": str(registry_entry.get("workload") or "").strip(),
            "profile_drafter_id": str(registry_entry.get("drafter") or "").strip(),
            "confidence_tier": "exact",
            "gate_terminal": "",
            "gate_reason": "",
            "derived_compose_path": "",
            "compat_status": _normalize_status_kind(status_text),
            "compat_reason_summary": str(status_text or "").strip(),
            "launch_settings": _read_compose_launch_settings(compose_abs_path),
            "default_engine_switches": _read_compose_command_text(compose_abs_path),
        }
        if variant["status_kind"] == "unknown" and variant["caveats"]:
            variant["status_kind"] = "production_caveat"
        variant["category"] = _category_for_variant(variant["topology"], variant["status_kind"])
        variant["scope_kind"] = _scope_kind_for_topology(variant["topology"])
        append_variant(variant)

    pattern = os.path.join(repo_root, "models", "*", "*", "compose", "**", "*.yml")
    compose_paths = sorted(glob.glob(pattern, recursive=True))
    for compose_abs_path in compose_paths:
        rel_path = os.path.relpath(compose_abs_path, repo_root).replace("\\", "/")
        if rel_path in registry_variant_keys:
            continue
        parts = rel_path.split("/")
        if len(parts) < 6 or parts[0] != "models":
            continue
        model_id = parts[1]
        engine = _normalize_engine("llama-cpp" if parts[2] == "llama-cpp" else parts[2])
        engine_display = _selector_engine_display(tag_by_compose.get(rel_path) or "", rel_path)
        topology = parts[4]
        profile = _read_compose_profile_header(compose_abs_path)
        status_hints = _read_compose_status_hints(compose_abs_path)
        hardware_meta = _read_compose_hardware_metadata(compose_abs_path)
        runtime_meta = _read_compose_runtime_metadata(compose_abs_path)
        status_text = _variant_status_text(profile, status_hints, tag_by_compose.get(rel_path), {}, model_profiles)
        variant = {
            "variant_id": _variant_id_from_rel_path(rel_path),
            "upstream_tag": tag_by_compose.get(rel_path),
            "registry_key": "",
            "model_id": model_id,
            "model_display_name": _model_display_name_from_profiles(model_profiles, model_id),
            "engine": engine,
            "engine_display": engine_display or engine,
            "topology": topology,
            "compose_rel_path": rel_path,
            "compose_abs_path": compose_abs_path,
            "compose_dir_abs_path": os.path.dirname(compose_abs_path),
            "compose_project_dir_abs_path": os.path.dirname(compose_abs_path),
            "service_name": runtime_meta.get("service_name") or "",
            "container_name": runtime_meta.get("container_name") or "",
            "default_port": runtime_meta.get("default_port") or 0,
            "served_model_name": runtime_meta.get("served_model_name") or "",
            "max_model_len": runtime_meta.get("max_model_len") or _extract_token_count(profile.get("max_ctx") or profile.get("default_ctx")),
            "model_path": runtime_meta.get("model_path") or "",
            "mmproj_path": runtime_meta.get("mmproj_path") or "",
            "draft_model_path": runtime_meta.get("draft_model_path") or "",
            "drafter": str(profile.get("drafter") or "").strip(),
            "drafter_profile": "",
            "weights_variant": "",
            "workload_id": "",
            "profile_like": "",
            "kv_format": str(profile.get("kv") or "").strip(),
            "vision": str(profile.get("vision") or "").strip(),
            "genesis": str(profile.get("genesis") or "").strip(),
            "status_raw": status_text,
            "status_kind": _normalize_status_kind(status_text),
            "caveats": str(profile.get("caveats") or "").strip(),
            "best_for": str(profile.get("best_for") or "").strip(),
            "quality_summary": str(profile.get("quality") or "").strip(),
            "speculative_method": runtime_meta.get("speculative_method"),
            "drafted_tokens": runtime_meta.get("drafted_tokens"),
            "requires_min_vram_gb": int(hardware_meta.get("requires_min_vram_gb") or 0),
            "requires_min_gpu_count": int(hardware_meta.get("requires_min_gpu_count") or 0),
            "tensor_parallel": int(hardware_meta.get("tensor_parallel") or 0),
            "requires_sm": str(hardware_meta.get("requires_sm") or "").strip(),
            "engine_profile": str(hardware_meta.get("engine_profile") or "").strip(),
            "nvlink_mode": str(hardware_meta.get("nvlink_mode") or "").strip(),
            "source_kind": "curated",
            "inventory_origin": "compose_scan",
            "profile_model_id": model_id,
            "profile_engine_id": "",
            "profile_workload_id": "",
            "profile_drafter_id": "",
            "confidence_tier": "exact",
            "gate_terminal": "",
            "gate_reason": "",
            "derived_compose_path": "",
            "compat_status": _normalize_status_kind(status_text),
            "compat_reason_summary": str(status_text or "").strip(),
            "launch_settings": _read_compose_launch_settings(compose_abs_path),
            "default_engine_switches": _read_compose_command_text(compose_abs_path),
        }
        if variant["status_kind"] == "unknown" and variant["caveats"]:
            variant["status_kind"] = "production_caveat"
        variant["category"] = _category_for_variant(variant["topology"], variant["status_kind"])
        variant["scope_kind"] = _scope_kind_for_topology(variant["topology"])
        append_variant(variant)

    for row in read_custom_model_registry():
        compose_abs_path = os.path.normpath(str(row.get("compose_path") or "").strip())
        compose_rel_path = _normalize_compose_rel_path(
            row.get("compose_rel_path")
            or (
                os.path.relpath(compose_abs_path, repo_root).replace("\\", "/")
                if compose_abs_path and os.path.isabs(compose_abs_path) and os.path.exists(compose_abs_path) and _path_is_within(repo_root, compose_abs_path)
                else os.path.join("custom-models", str(row.get("id") or ""), "docker-compose.yml").replace("\\", "/")
            )
        )
        runtime_meta = dict(row.get("compose_meta") or {})
        if compose_abs_path and (not runtime_meta or not runtime_meta.get("service_name")):
            parsed_runtime = _read_compose_runtime_metadata(compose_abs_path)
            for key, value in parsed_runtime.items():
                if value not in (None, "", 0):
                    runtime_meta[key] = value
        profile_like = str(row.get("profile_like") or "").strip()
        registry_entry = compose_registry.get(profile_like) or {}
        profile_engine = str(row.get("profile_engine_id") or registry_entry.get("engine") or "").strip()
        engine_family = _normalize_engine("vllm")
        profile_like_lower = profile_like.lower()
        compose_hint = str(registry_entry.get("compose_path") or compose_rel_path).replace("\\", "/").lower()
        if (
            profile_like_lower.startswith(("llamacpp/", "llama-cpp/", "ik-llama/"))
            or profile_engine == "llama-cpp-local"
            or "/llama-cpp/" in compose_hint
            or "/ik-llama/" in compose_hint
        ):
            engine_family = "llamacpp"
        engine_display = _selector_engine_display(profile_like or str(row.get("selector") or ""), compose_rel_path or compose_hint)
        topology = _infer_topology_from_compose_path(
            str(registry_entry.get("compose_path") or compose_rel_path),
            "multi" if int((runtime_meta.get("tp") or registry_entry.get("tp") or 1)) > 2 else ("dual" if int((runtime_meta.get("tp") or registry_entry.get("tp") or 1)) > 1 else "single"),
        )
        gate_terminal = str(row.get("gate_terminal") or "").strip()
        if gate_terminal == "override-accepted":
            status_text = "experimental"
        elif gate_terminal == "confirm→proceed":
            status_text = "production caveat"
        else:
            status_text = "production"
        variant = {
            "variant_id": _variant_id_from_selector(row.get("selector")),
            "upstream_tag": str(row.get("selector") or "").strip(),
            "registry_key": str(row.get("registry_key") or row.get("selector") or "").strip(),
            "model_id": str(row.get("model_id") or "").strip(),
            "model_display_name": str(row.get("display_name") or row.get("slug") or row.get("model_id") or "").strip(),
            "engine": engine_family,
            "engine_display": engine_display or engine_family,
            "engine_profile": str(row.get("profile_engine_id") or registry_entry.get("engine") or "vllm-nightly-clean").strip(),
            "topology": topology,
            "compose_rel_path": compose_rel_path,
            "compose_abs_path": compose_abs_path,
            "compose_dir_abs_path": os.path.dirname(compose_abs_path) if compose_abs_path else "",
            "compose_project_dir_abs_path": os.path.dirname(compose_abs_path) if compose_abs_path else "",
            "service_name": runtime_meta.get("service_name") or "",
            "container_name": runtime_meta.get("container_name") or "",
            "default_port": int(runtime_meta.get("port") or runtime_meta.get("default_port") or registry_entry.get("default_port") or 0),
            "served_model_name": runtime_meta.get("served_model_name") or str((row.get("compose_meta") or {}).get("served_model_name") or "").strip(),
            "max_model_len": int((runtime_meta.get("max_model_len") or (row.get("compose_meta") or {}).get("max_model_len") or registry_entry.get("max_ctx") or 0) or 0),
            "max_num_seqs": int((row.get("compose_meta") or {}).get("max_num_seqs") or registry_entry.get("max_num_seqs") or 0),
            "mem_util": (row.get("compose_meta") or {}).get("gpu_memory_utilization") or registry_entry.get("mem_util"),
            "model_path": runtime_meta.get("model_path") or str((row.get("compose_meta") or {}).get("container_model_dir") or "").strip(),
            "mmproj_path": runtime_meta.get("mmproj_path") or "",
            "draft_model_path": runtime_meta.get("draft_model_path") or "",
            "drafter": str(registry_entry.get("drafter") or "").strip(),
            "drafter_profile": str(row.get("profile_drafter_id") or registry_entry.get("drafter") or "").strip(),
            "weights_variant": str(registry_entry.get("weights_variant") or "").strip(),
            "workload_id": str(row.get("profile_workload_id") or registry_entry.get("workload") or "").strip(),
            "profile_like": str(row.get("profile_like") or "").strip(),
            "kv_format": str((row.get("compose_meta") or {}).get("kv_format") or registry_entry.get("kv_format") or "").strip(),
            "vision": "",
            "genesis": "",
            "status_raw": status_text,
            "status_kind": _normalize_status_kind(status_text),
            "caveats": str(row.get("caveats") or row.get("gate_reason") or row.get("compat_reason_summary") or "").strip(),
            "best_for": str(row.get("best_for") or f"Imported from {row.get('slug') or 'Hugging Face'} using {row.get('profile_like') or 'a custom runtime shape'}.").strip(),
            "quality_summary": str(row.get("quality_summary") or "").strip(),
            "speculative_method": runtime_meta.get("speculative_method"),
            "drafted_tokens": runtime_meta.get("drafted_tokens"),
            "requires_min_vram_gb": 0,
            "requires_min_gpu_count": 2 if topology == "dual" else (max(1, int(registry_entry.get("tp") or 1)) if topology == "multi" else 1),
            "tensor_parallel": int((row.get("compose_meta") or {}).get("tp") or registry_entry.get("tp") or 1),
            "requires_sm": str(registry_entry.get("required_sm") or "").strip(),
            "nvlink_mode": "required" if registry_entry.get("requires_nvlink") else "",
            "source_kind": "custom",
            "inventory_origin": str(row.get("inventory_origin") or "custom_registry").strip() or "custom_registry",
            "profile_model_id": str(row.get("profile_model_id") or "").strip(),
            "profile_engine_id": str(row.get("profile_engine_id") or registry_entry.get("engine") or "").strip(),
            "profile_workload_id": str(row.get("profile_workload_id") or registry_entry.get("workload") or "").strip(),
            "profile_drafter_id": str(row.get("profile_drafter_id") or registry_entry.get("drafter") or "").strip(),
            "confidence_tier": str(row.get("confidence_tier") or "").strip(),
            "gate_terminal": gate_terminal,
            "gate_reason": str(row.get("gate_reason") or "").strip(),
            "derived_compose_path": compose_abs_path,
            "compat_status": str(row.get("compat_status") or gate_terminal or "").strip(),
            "compat_reason_summary": str(row.get("compat_reason_summary") or "").strip(),
            "launch_settings": _read_compose_launch_settings(compose_abs_path) if compose_abs_path and os.path.exists(compose_abs_path) else [],
            "default_engine_switches": str((row.get("compose_meta") or {}).get("command_text") or _read_compose_command_text(compose_abs_path) if compose_abs_path and os.path.exists(compose_abs_path) else "").strip(),
        }
        variant["category"] = _category_for_variant(topology, variant["status_kind"])
        variant["scope_kind"] = _scope_kind_for_topology(topology)
        host_model_dir = str(row.get("host_model_dir") or (row.get("compose_meta") or {}).get("host_model_dir") or "").strip()
        variant["host_model_dir"] = host_model_dir
        ready = _path_has_model_assets(host_model_dir)
        append_variant(
            variant,
            force_install_state={
                "install_state": "ready" if ready else "requires_download",
                "install_command": "" if ready else str(row.get("install_command") or "").strip(),
                "install_reason": "" if ready else (
                    str(row.get("install_reason") or "").strip()
                    or (f"Expected imported model assets under {host_model_dir}." if host_model_dir else "Custom model assets are missing from disk.")
                ),
            },
        )
    for model_id, model_row in model_rows.items():
        variants = [row for row in inventory["variants"] if row.get("model_id") == model_id]
        safe_variants = [row for row in variants if row.get("status_kind") in {"production", "production_caveat"}]
        any_ready = any(row.get("install_state") == "ready" for row in safe_variants)
        any_known = any(row.get("install_state") in {"ready", "requires_download"} for row in variants)
        any_partial = any(row.get("install_state") == "ready" for row in variants)
        any_downloadable = any(row.get("install_state") == "requires_download" for row in variants)
        model_meta = getattr(model_profiles, "models", {}).get(model_id) if model_profiles is not None else None
        preferred_weight_variant = str(getattr(model_meta, "default_weight_variant", "") or "").strip()
        model_row["summary"] = _model_summary_from_variants(model_row, safe_variants or variants)
        default_install_candidates = [
            row
            for row in variants
            if row.get("install_command")
            and str(row.get("engine") or "") == "vllm"
            and "WITH_DFLASH_DRAFT=1" not in str(row.get("install_command") or "")
        ]
        prioritized_install_candidates = [
            row for row in default_install_candidates if preferred_weight_variant and str(row.get("weights_variant") or "") == preferred_weight_variant
        ]
        if not prioritized_install_candidates:
            prioritized_install_candidates = [
                row for row in default_install_candidates if str(row.get("status_kind") or "") in {"production", "production_caveat", "preview"}
            ]
        if not prioritized_install_candidates:
            prioritized_install_candidates = list(default_install_candidates)
        model_row["default_install_command"] = str((prioritized_install_candidates[0] or {}).get("install_command") or "") if prioritized_install_candidates else ""
        if not model_row["default_install_command"]:
            model_row["default_install_command"] = next(
                (
                    str(row.get("install_command") or "")
                    for row in variants
                    if row.get("install_command") and "WITH_DFLASH_DRAFT=1" not in str(row.get("install_command") or "")
                ),
                "",
            )
        if not model_row["default_install_command"]:
            model_row["default_install_command"] = next((str(row.get("install_command") or "") for row in variants if row.get("install_command")), "")
        if model_row["default_install_command"]:
            chosen = next(
                (row for row in variants if str(row.get("install_command") or "") == str(model_row["default_install_command"] or "")),
                None,
            )
            if chosen:
                model_row["default_install_reason"] = str(chosen.get("install_reason") or "")
                model_row["default_install_variant_id"] = str(chosen.get("variant_id") or "")
        model_row["setup_supported"] = bool(model_row["default_install_command"])
        if any_ready:
            model_row["installed_state"] = "ready" if not any_downloadable else "partial"
        elif any_partial or any_downloadable:
            model_row["installed_state"] = "partial" if any_partial else "missing"
        elif any_known:
            model_row["installed_state"] = "missing"
        else:
            model_row["installed_state"] = "unsupported"
        model_row["engine_groups"].sort()
        inventory["models"].append(model_row)
    inventory["profile_likes"] = [
        {
            "key": key,
            "model_id": str(entry.get("model") or "").strip(),
            "model_display_name": _model_display_name_from_profiles(model_profiles, entry.get("model")),
            "engine_family": _normalize_engine("llama-cpp" if str(key or "").startswith(("llamacpp/", "ik-llama/")) else ("vllm" if str(key or "").startswith("vllm/") else "")),
            "engine_display": _selector_engine_display(key, str(entry.get("compose_path") or "")),
            "engine_profile": str(entry.get("engine") or "").strip(),
            "weights_variant": str(entry.get("weights_variant") or "").strip(),
            "workload_id": str(entry.get("workload") or "").strip(),
            "drafter_profile": str(entry.get("drafter") or "").strip(),
            "kv_format": str(entry.get("kv_format") or "").strip(),
            "tp": int(entry.get("tp") or 1),
            "max_ctx": int(entry.get("max_ctx") or 0),
            "max_num_seqs": int(entry.get("max_num_seqs") or 0),
            "mem_util": entry.get("mem_util"),
            "default_port": int(entry.get("default_port") or 0),
            "compose_rel_path": _normalize_compose_rel_path(entry.get("compose_path")),
            "default_engine_switches": _read_compose_command_text(os.path.join(repo_root, _normalize_compose_rel_path(entry.get("compose_path")))),
            "requires_nvlink": bool(entry.get("requires_nvlink")),
            "required_sm": entry.get("required_sm"),
            "required_engine_features": list(entry.get("required_engine_features") or []),
            "custom_import_supported": str(key or "").startswith("vllm/"),
        }
        for key, entry in sorted(compose_registry.items())
        if str(key or "").strip()
    ]
    inventory["models"].sort(
        key=lambda row: (
            _model_order_rank(row.get("model_id"), row.get("source_kind")),
            row.get("display_name") or row.get("model_id") or "",
        )
    )
    inventory["variants"].sort(
        key=lambda row: (
            _model_order_rank(row.get("model_id"), row.get("source_kind")),
            row.get("model_display_name") or row.get("model_id") or "",
            row.get("category") or "",
            _mode_selector_for_variant(row),
        )
    )
    write_json_file(RUNTIME_INVENTORY_FILE, inventory)
    _rebuild_runtime_mode_tables(inventory)
    with runtime_inventory_lock:
        runtime_inventory_cache = dict(inventory)
        runtime_inventory_built_at = time.time()
    return inventory


def load_runtime_inventory(force=False, rebuild_if_missing=True):
    global runtime_inventory_cache, runtime_inventory_built_at
    now = time.time()
    with runtime_inventory_lock:
        cached = dict(runtime_inventory_cache) if runtime_inventory_cache else {}
        cached_at = float(runtime_inventory_built_at or 0.0)
    if cached and not force and cached_at and (now - cached_at) < 10.0:
        return cached
    if not force:
        data = read_json_file(RUNTIME_INVENTORY_FILE, {})
        if isinstance(data, dict) and data.get("variants"):
            _rebuild_runtime_mode_tables(data)
            with runtime_inventory_lock:
                runtime_inventory_cache = dict(data)
                runtime_inventory_built_at = time.time()
            return data
    if rebuild_if_missing:
        return rebuild_runtime_inventory()
    return {}


def _custom_model_display_name(slug, preferred=""):
    explicit = str(preferred or "").strip()
    if explicit:
        return explicit
    tail = str(slug or "").strip().split("/")[-1]
    if not tail:
        return "Custom Model"
    text = re.sub(r"[-_]+", " ", tail).strip()
    return re.sub(r"\s+", " ", text) or tail


def _parse_hardware_gpus_override(raw):
    text = str(raw or "").strip()
    if not text:
        return None
    vram = []
    names = []
    for token in text.split(","):
        item = token.strip()
        if not item:
            continue
        if ":" in item:
            mem_text, name = item.split(":", 1)
        else:
            mem_text, name = item, "GPU"
        try:
            vram.append(int(float(mem_text.strip())))
        except Exception:
            raise ValueError("Custom model GPU override must use VRAM_MIB:NAME items, for example 24576:RTX 3090")
        names.append(name.strip() or "GPU")
    if not vram:
        return None
    return (len(vram), vram, names)


def _build_custom_model_pull_plan(
    slug,
    profile_like,
    *,
    display_name="",
    accept_confirm=False,
    force_download=False,
    trust_remote_code=False,
    experimental_arch=False,
    hf_home="",
    hardware_sm=None,
    hardware_gpus="",
    engine_switches="",
):
    slug = str(slug or "").strip()
    profile_key = str(profile_like or "").strip()
    if not slug or "/" not in slug:
        raise ValueError("Custom model slug must be a Hugging Face repo like org/model-name")
    compose_registry = _load_upstream_compose_registry()
    registry_entry = dict(compose_registry.get(profile_key) or {})
    if not registry_entry:
        raise ValueError("Choose a valid reference profile before importing a custom model")
    if not str(profile_key).startswith("vllm/"):
        raise ValueError("Custom model import currently supports upstream vLLM reference profiles only")
    profile_display = _custom_model_display_name(slug, preferred=display_name)
    record_id = _selector_token(profile_display)
    for row in read_custom_model_registry():
        if str(row.get("id") or "") == record_id:
            raise ValueError(f"A custom model named {profile_display!r} is already registered")
        if str(row.get("slug") or "").strip().lower() == slug.lower():
            raise ValueError("That Hugging Face repo is already registered as a custom model")

    ensure_upstream_repo_on_sys_path()
    from scripts.lib import generate_compose as upstream_generate_compose
    from scripts.lib.profiles import pull as upstream_pull

    captured = {}

    def emit_fn(root, ei):
        ei.diagnostics = dict(getattr(ei, "diagnostics", {}) or {})
        if trust_remote_code:
            ei.diagnostics["trc_permitted"] = True
        compose_text, compose_meta = upstream_generate_compose.generate_from_profile(root, ei)
        replacement_command = str(engine_switches or "").strip()
        if replacement_command:
            compose_text = _replace_compose_command_text(compose_text, replacement_command)
            compose_meta = dict(compose_meta or {})
            compose_meta["command_text"] = replacement_command
        captured["einput"] = ei
        captured["compose_text"] = compose_text
        captured["compose_meta"] = dict(compose_meta or {})
        return compose_text, compose_meta

    def download_fn(_ei, fetcher=None):
        return SimpleNamespace(ok=True, files=[], bytes=0, sha_verified=True, failure=None)

    class _NullBootContext:
        def __enter__(self):
            return SimpleNamespace(ok=True, seconds=0.0, endpoint="", failure=None)

        def __exit__(self, exc_type, exc, tb):
            return False

    def boot_cm(_ei, compose_text, runner=None):
        _ = compose_text
        _ = runner
        return _NullBootContext()

    def smoke_fn(_ei, endpoint):
        _ = endpoint
        return SimpleNamespace(smoke_capability_set=[], results={}, partial=False, results_detail={})

    def capture_fn(*args, **kwargs):
        _ = args
        _ = kwargs
        return {"paths": {}, "dir": "", "manifest": {}}

    def override_capture_fn(*args, **kwargs):
        _ = args
        _ = kwargs
        return ""

    gpu_topology = _parse_hardware_gpus_override(hardware_gpus)
    repo_root = Path(ensure_upstream_repo_on_sys_path())
    if hasattr(os, "statvfs"):
        statvfs_fn = os.statvfs
    else:
        def statvfs_fn(path):
            usage = shutil.disk_usage(str(path or "."))
            frsize = 4096
            return SimpleNamespace(f_frsize=frsize, f_bavail=max(0, int(usage.free // frsize)))
    result = upstream_pull.run_pull(
        slug,
        profile_key,
        dry_run=False,
        yes=bool(accept_confirm),
        force_download=bool(force_download),
        experimental_arch=bool(experimental_arch),
        trust_remote_code=bool(trust_remote_code),
        hf_home=(str(hf_home or "").strip() or None),
        hardware_sm=(float(hardware_sm) if hardware_sm not in (None, "") else None),
        gpu_topology=gpu_topology,
        root=repo_root,
        statvfs=statvfs_fn,
        emit_fn=emit_fn,
        download_fn=download_fn,
        boot_cm=boot_cm,
        smoke_fn=smoke_fn,
        capture_fn=capture_fn,
        override_capture_fn=override_capture_fn,
        gate_capture_fn=lambda *args, **kwargs: None,
    )
    if not result.ok or not captured.get("compose_text"):
        summary = str(result.detail or result.abort_reason or "Upstream pull validation failed.").strip()
        if result.terminal and not result.ok:
            summary = f"{summary} Terminal: {result.terminal}."
        raise RuntimeError(summary)

    compose_abs_path = os.path.join(CUSTOM_MODELS_DIR, record_id, "docker-compose.yml")
    compose_profile = _read_compose_profile_header(os.path.join(CLUB3090_DIR, _normalize_compose_rel_path(registry_entry.get("compose_path")).replace("/", os.sep)))
    record = {
        "id": record_id,
        "selector": f"custom/{record_id}",
        "slug": slug,
        "model_id": f"custom-{record_id}",
        "display_name": profile_display,
        "profile_like": profile_key,
        "compose_path": compose_abs_path,
        "compose_rel_path": _normalize_compose_rel_path(os.path.join("custom-models", record_id, "docker-compose.yml")),
        "inventory_origin": "custom_registry",
        "registry_key": f"custom/{record_id}",
        "profile_model_id": str(registry_entry.get("model") or "").strip(),
        "profile_engine_id": str(registry_entry.get("engine") or "").strip(),
        "profile_workload_id": str(registry_entry.get("workload") or "").strip(),
        "profile_drafter_id": str(registry_entry.get("drafter") or "").strip(),
        "confidence_tier": str(result.confidence or "").strip(),
        "gate_terminal": str(result.terminal or "").strip(),
        "gate_reason": str(result.detail or "").strip(),
        "compat_status": str(result.terminal or result.abort_reason or "").strip(),
        "compat_reason_summary": str(result.detail or "").strip(),
        "best_for": _variant_best_for(compose_profile, registry_entry, _load_upstream_profiles()) or f"Imported from {slug}.",
        "quality_summary": _variant_quality_summary(compose_profile),
        "caveats": str("; ".join([note for note in (result.notices or []) if note]) or _variant_caveats(compose_profile, registry_entry, _load_upstream_profiles()) or "").strip(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host_model_dir": str((captured.get("compose_meta") or {}).get("host_model_dir") or "").strip(),
        "compose_text": str(captured.get("compose_text") or ""),
        "compose_meta": dict(captured.get("compose_meta") or {}),
        "command": " ".join(
            [
                "bash",
                "scripts/pull.sh",
                shlex.quote(slug),
                "--profile-like",
                shlex.quote(profile_key),
                "--recommend",
            ]
            + (["--yes"] if accept_confirm else [])
            + (["--force-download"] if force_download else [])
            + (["--experimental-arch"] if experimental_arch else [])
            + (["--trust-remote-code"] if trust_remote_code else [])
            + ((["--hf-home", shlex.quote(str(hf_home).strip())]) if str(hf_home or "").strip() else [])
            + ((["--hardware", shlex.quote(str(hardware_sm).strip())]) if hardware_sm not in (None, "") else [])
            + ((["--hardware-gpus", shlex.quote(str(hardware_gpus).strip())]) if str(hardware_gpus or "").strip() else [])
        ),
    }
    return record


def delete_custom_model_record(record_id):
    wanted = _selector_token(record_id)
    rows = read_custom_model_registry()
    target = next((row for row in rows if _selector_token(row.get("id") or "") == wanted or _selector_token(row.get("model_id") or "") == wanted or _selector_token(row.get("selector") or "") == wanted), None)
    if not target:
        raise ValueError("Custom model not found")
    selector = str(target.get("selector") or "").strip()
    if selector:
        try:
            stop_runtime_scope(instance_id="GLOBAL", mode=selector)
        except Exception:
            pass
    compose_path = str(target.get("compose_path") or "").strip()
    if compose_path and os.path.exists(compose_path):
        try:
            compose_dir = os.path.dirname(compose_path) or CONTROL_DIR
            env = _repo_subprocess_env()
            env["COMPOSE_BIN"] = COMPOSE_BIN
            run_cmd(compose_cmd() + ["--project-directory", compose_dir, "-f", compose_path, "down"], timeout=300, cwd=compose_dir, env=env)
        except Exception:
            pass
    remaining = [row for row in rows if str(row.get("id") or "") != str(target.get("id") or "")]
    write_custom_model_registry(remaining)
    compose_dir = os.path.dirname(compose_path)
    if compose_dir and os.path.isdir(compose_dir):
        custom_root = os.path.abspath(CUSTOM_MODELS_DIR)
        if _path_is_within(custom_root, compose_dir):
            shutil.rmtree(compose_dir, ignore_errors=True)
    host_model_dir = str(target.get("host_model_dir") or "").strip()
    if host_model_dir and os.path.isdir(host_model_dir):
        normalized_host = os.path.normcase(os.path.abspath(host_model_dir))
        shared_host = any(
            os.path.normcase(os.path.abspath(str(row.get("host_model_dir") or "").strip())) == normalized_host
            for row in remaining
            if str(row.get("host_model_dir") or "").strip()
        )
        if not shared_host and "/club3090/pulls/" in host_model_dir.replace("\\", "/").lower():
            shutil.rmtree(host_model_dir, ignore_errors=True)
    rebuild_runtime_inventory()
    return target
