import os
import sys
import time
import io
import contextlib
import glob
import importlib.util
import subprocess
from types import ModuleType

try:
    from control.shared import *  # type: ignore
    import control.shared as _club3090_shared_module  # type: ignore
except Exception:
    if "CLUB3090_DIR" not in globals():
        _CONTROL_DIR = os.path.dirname(os.path.abspath(__file__))
        if _CONTROL_DIR not in sys.path:
            sys.path.insert(0, _CONTROL_DIR)
        from shared import *  # type: ignore
        import shared as _club3090_shared_module  # type: ignore

try:
    _preset_tps_selector_key
    _read_preset_tps_stats_unlocked
    _sanitize_preset_tps_row
    _write_preset_tps_stats_unlocked
    _monitor_plan_from_variant_install
except NameError:
    try:
        from control.shared import (  # type: ignore
            _monitor_plan_from_variant_install,
            _preset_tps_selector_key,
            _read_preset_tps_stats_unlocked,
            _sanitize_preset_tps_row,
            _write_preset_tps_stats_unlocked,
        )
    except Exception:
        from shared import (  # type: ignore
            _monitor_plan_from_variant_install,
            _preset_tps_selector_key,
            _read_preset_tps_stats_unlocked,
            _sanitize_preset_tps_row,
            _write_preset_tps_stats_unlocked,
        )

try:
    preset_builtin_launch_env_overrides
    preset_launch_env_overrides
    read_server_config
    write_server_config
except NameError:
    try:
        if globals().get("__package__"):
            from control.services_config import (  # type: ignore
                preset_builtin_launch_env_overrides,
                preset_launch_env_overrides,
                read_server_config,
                write_server_config,
            )
        else:
            from services_config import (  # type: ignore
                preset_builtin_launch_env_overrides,
                preset_launch_env_overrides,
                read_server_config,
                write_server_config,
            )
    except Exception:
        pass

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


def _compose_rel_path_is_archived(path):
    rel = _normalize_compose_rel_path(path).lower()
    return "/compose/_archive/" in f"/{rel}/"


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
        lowered = part.lower()
        dual_count_match = re.search(r"(?:^|[-_])dual([0-9]+)(?:$|[-_])", lowered)
        if dual_count_match:
            try:
                return "multi" if int(dual_count_match.group(1) or "0") > 2 else "dual"
            except Exception:
                return "dual"
        if re.search(r"(?:^|[-_])dual(?:$|[-_])", lowered):
            return "dual"
        if part.startswith("multi"):
            return "multi"
    return str(fallback or "").strip() or "single"


def _topology_from_gpu_count(gpu_count, fallback="single"):
    try:
        count = int(gpu_count or 0)
    except Exception:
        count = 0
    if count > 2:
        return "multi"
    if count > 1:
        return "dual"
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
    if "migrated" in text:
        return "migrated"
    if "upstream" in text and ("blocked" in text or "gated" in text):
        return "upstream_gated"
    if "incubating" in text:
        return "incubating"
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


def _upstream_repo_cache_root():
    return os.path.abspath(str(CLUB3090_DIR or "").strip() or ".")


def _upstream_cache_ready(func, root):
    return bool(
        getattr(func, "_cache_ready", False)
        and getattr(func, "_cache_root", "") == root
    )


def _store_upstream_cache(func, root, value):
    setattr(func, "_cache", value)
    setattr(func, "_cache_root", root)
    setattr(func, "_cache_ready", True)
    return value


def _clear_root_aware_cache(func):
    setattr(func, "_cache", None)
    setattr(func, "_cache_root", "")
    setattr(func, "_cache_ready", False)


def _ensure_runtime_upstream_repo_on_sys_path():
    repo_root = _upstream_repo_cache_root()
    if repo_root and os.path.isdir(repo_root) and repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    scripts_dir = os.path.join(repo_root, "scripts")
    for name, module in list(sys.modules.items()):
        if name != "scripts" and not name.startswith("scripts."):
            continue
        candidates = list(getattr(module, "__path__", []) or [])
        module_file = str(getattr(module, "__file__", "") or "")
        if module_file:
            candidates.append(module_file)
        rooted = False
        for candidate in candidates:
            try:
                rooted = os.path.commonpath([
                    os.path.normcase(repo_root),
                    os.path.normcase(os.path.abspath(str(candidate))),
                ]) == os.path.normcase(repo_root)
            except Exception:
                rooted = False
            if rooted:
                break
        if not rooted:
            sys.modules.pop(name, None)
    if "scripts" not in sys.modules and os.path.isdir(scripts_dir):
        upstream_scripts = ModuleType("scripts")
        upstream_scripts.__path__ = [scripts_dir]
        upstream_scripts.__package__ = "scripts"
        upstream_scripts.__file__ = os.path.join(scripts_dir, "__init__.py")
        sys.modules["scripts"] = upstream_scripts
    return repo_root


def _load_upstream_profiles():
    root = _upstream_repo_cache_root()
    cached = getattr(_load_upstream_profiles, "_cache", None)
    if _upstream_cache_ready(_load_upstream_profiles, root):
        return cached
    os.environ.setdefault("CLUB3090_LOG_LEVEL", "ERROR")
    _ensure_runtime_upstream_repo_on_sys_path()
    try:
        from scripts.lib.profiles.compat import load_profiles

        value = load_profiles()
    except Exception:
        value = None
    return _store_upstream_cache(_load_upstream_profiles, root, value)


def _load_upstream_weights_reader():
    root = _upstream_repo_cache_root()
    cached = getattr(_load_upstream_weights_reader, "_cache", None)
    if _upstream_cache_ready(_load_upstream_weights_reader, root):
        return cached
    os.environ.setdefault("CLUB3090_LOG_LEVEL", "ERROR")
    _ensure_runtime_upstream_repo_on_sys_path()
    try:
        from scripts.lib.profiles import weights as profile_weights

        if hasattr(profile_weights, "_load_models"):
            original_loader = getattr(profile_weights, "_club3090_original_load_models", None)
            if original_loader is None:
                original_loader = profile_weights._load_models
                setattr(profile_weights, "_club3090_original_load_models", original_loader)

            def _club3090_cached_load_models():
                return _load_upstream_weight_models()

            profile_weights._load_models = _club3090_cached_load_models
        value = profile_weights
    except Exception:
        value = None
    return _store_upstream_cache(_load_upstream_weights_reader, root, value)


def _load_upstream_weight_models():
    root = _upstream_repo_cache_root()
    cached = getattr(_load_upstream_weight_models, "_cache", None)
    if _upstream_cache_ready(_load_upstream_weight_models, root) and isinstance(cached, dict):
        return cached
    reader = _load_upstream_weights_reader()
    if reader is None:
        value = {}
    else:
        try:
            loader = getattr(reader, "_club3090_original_load_models", None) or getattr(reader, "_load_models")
            with contextlib.redirect_stderr(io.StringIO()):
                value = dict(loader() or {})
        except (Exception, SystemExit):
            value = {}
    return _store_upstream_cache(_load_upstream_weight_models, root, value)


def _load_upstream_compose_registry():
    root = _upstream_repo_cache_root()
    cached = getattr(_load_upstream_compose_registry, "_cache", None)
    if _upstream_cache_ready(_load_upstream_compose_registry, root) and cached is not None:
        return dict(cached)
    os.environ.setdefault("CLUB3090_LOG_LEVEL", "ERROR")
    value = {}
    registry_path = os.path.join(root, "scripts", "lib", "profiles", "compose_registry.py")
    try:
        if os.path.exists(registry_path):
            module_name = f"club3090_compose_registry_{_selector_token(root)}"
            spec = importlib.util.spec_from_file_location(module_name, registry_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            registry = getattr(module, "COMPOSE_REGISTRY", {})
        else:
            _ensure_runtime_upstream_repo_on_sys_path()
            from scripts.lib.profiles.compose_registry import COMPOSE_REGISTRY as registry
        value = {str(key): dict(row or {}) for key, row in dict(registry or {}).items()}
    except Exception:
        value = {}
    _store_upstream_cache(_load_upstream_compose_registry, root, dict(value))
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
    if selector_text.startswith("vllm-omni/") or "/vllm-omni/" in compose_hint:
        return "vllm-omni"
    if selector_text.startswith("vllm-lmcache/") or "/vllm-lmcache/" in compose_hint:
        return "vllm-lmcache"
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
    cache = getattr(_weight_recipe_from_model_variant, "_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(_weight_recipe_from_model_variant, "_cache", cache)
    cache_key = (model_text, variant_text)
    if cache_key in cache:
        return dict(cache.get(cache_key) or {})
    candidates = [
        f"{model_text}:{variant_text}",
        f"{model_text}:{variant_text.replace('-', '_')}",
    ]
    recipe = {}
    for candidate in dict.fromkeys(candidates):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                resolved_model_id, resolved_variant = reader._resolve_key(candidate)
            recipe = dict(reader._recipe(resolved_model_id, resolved_variant) or {})
            break
        except (Exception, SystemExit):
            continue
    cache[cache_key] = dict(recipe)
    return dict(recipe)


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
    cache = getattr(_weight_recipe_from_subpath, "_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(_weight_recipe_from_subpath, "_cache", cache)
    if clean in cache:
        return dict(cache.get(clean) or {})
    recipe = {}
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            model_id, variant = reader._lookup_path(clean)
        recipe = dict(reader._recipe(model_id, variant) or {})
    except (Exception, SystemExit):
        recipe = {}
    cache[clean] = dict(recipe)
    return dict(recipe)


def _bind_runtime_weight_recipe_helpers():
    shared_module = globals().get("_club3090_shared_module")
    if shared_module is None:
        return
    try:
        setattr(shared_module, "_weight_recipe_from_model_variant", _weight_recipe_from_model_variant)
        setattr(shared_module, "_weight_recipe_from_subpath", _weight_recipe_from_subpath)
        setattr(shared_module, "_recipe_subdir_host_path", _recipe_subdir_host_path)
    except Exception:
        pass


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
    weight_key = str((recipe or {}).get("WEIGHT_KEY") or "").strip()
    weight_model = str((recipe or {}).get("WEIGHT_MODEL") or "").strip()
    if weight_key and weight_model == "diffusiongemma-26b-a4b" and str(env_map.get("WEIGHTS") or "").strip().lower() == "fp8":
        # Upstream v0.10's setup.sh only wires WEIGHTS=fp8 for Qwen. DiffusionGemma
        # must use the exact catalog key or migration setup replay aborts.
        env_map.pop("WEIGHTS", None)
        env_map["WEIGHT_KEY"] = weight_key
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


_bind_runtime_weight_recipe_helpers()


def resolve_variant_launch_env(spec):
    variant_spec = spec if isinstance(spec, dict) else {}
    env = {}
    selector = str(
        variant_spec.get("selector")
        or variant_spec.get("upstream_tag")
        or variant_spec.get("registry_key")
        or ""
    ).strip().lower()
    registry_key = str(
        variant_spec.get("registry_key")
        or variant_spec.get("upstream_tag")
        or variant_spec.get("profile_like")
        or ""
    ).strip()
    if registry_key and registry_key.startswith("vllm/"):
        _ensure_runtime_upstream_repo_on_sys_path()
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
        "01d4d1ad375dc5854779c593eee093bcebb0cada",
        "bf610c2f56764e1b30bc6065f4ceace3d6e59036",
        "e47c98ef7a38792996e452ef53914e21e41928e9",
    }
    if nightly_sha in stable_vllm_nightly_fallbacks:
        env.pop("VLLM_NIGHTLY_SHA", None)
        env["VLLM_IMAGE"] = "vllm/vllm-openai:v0.22.0"
    profile_engine_id = str(variant_spec.get("profile_engine_id") or variant_spec.get("engine_id") or "").strip()
    if (
        not str(env.get("VLLM_IMAGE") or "").strip()
        and not str(env.get("VLLM_NIGHTLY_SHA") or "").strip()
        and profile_engine_id in {"vllm-nightly-clean", "vllm-nightly-mtp"}
    ):
        env["VLLM_IMAGE"] = "vllm/vllm-openai:v0.22.0"
    if (
        not str(env.get("VLLM_IMAGE") or "").strip()
        and not str(env.get("VLLM_NIGHTLY_SHA") or "").strip()
        and str(variant_spec.get("engine") or variant_spec.get("engine_family") or "").strip().lower().startswith("vllm")
    ):
        compose_path = str(variant_spec.get("compose_abs_path") or "").strip()
        try:
            compose_text = open(compose_path, "r", encoding="utf-8", errors="replace").read(20000) if compose_path else ""
        except Exception:
            compose_text = ""
        if "vllm/vllm-openai:nightly-${VLLM_NIGHTLY_SHA" in compose_text:
            env["VLLM_IMAGE"] = "vllm/vllm-openai:v0.22.0"
    env.update(preset_builtin_launch_env_overrides(variant_spec, selector))
    env.update(preset_launch_env_overrides(variant_spec))
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


def _custom_registry_row_is_preset(row):
    data = row if isinstance(row, dict) else {}
    if data.get("custom_preset") is True:
        return True
    origin = str(data.get("inventory_origin") or "").strip().lower()
    if origin == "migrated_custom_registry":
        return True
    text = " ".join(
        str(data.get(key) or "")
        for key in ("gate_reason", "compat_reason_summary", "best_for")
    ).lower()
    return (
        "duplicated from " in text
        or "custom duplicate of " in text
        or "custom optimized duplicate of " in text
    )


def _custom_registry_parent_model_id(raw, record_id=""):
    data = raw if isinstance(raw, dict) else {}
    model_id = str(data.get("model_id") or "").strip()
    profile_model_id = str(data.get("profile_model_id") or "").strip()
    if _custom_registry_row_is_preset(data) and profile_model_id:
        return profile_model_id
    return model_id or f"custom-{record_id}"


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
        custom_preset = _custom_registry_row_is_preset(raw)
        model_id = _custom_registry_parent_model_id(raw, record_id)
        profile_model_id = str(raw.get("profile_model_id") or (model_id if custom_preset else "") or "").strip()
        rows.append(
            {
                "id": record_id,
                "selector": selector,
                "slug": str(raw.get("slug") or "").strip(),
                "source_selector": str(raw.get("source_selector") or "").strip(),
                "replacement_selector": str(raw.get("replacement_selector") or "").strip(),
                "source_compose_rel_path": _normalize_compose_rel_path(raw.get("source_compose_rel_path")),
                "source_compose_sha256": str(raw.get("source_compose_sha256") or "").strip(),
                "source_status_kind": str(raw.get("source_status_kind") or "").strip(),
                "model_id": model_id,
                "model_display_name": str(raw.get("model_display_name") or "").strip(),
                "display_name": str(raw.get("display_name") or raw.get("slug") or record_id).strip(),
                "custom_preset": bool(custom_preset),
                "profile_like": str(raw.get("profile_like") or "").strip(),
                "compose_path": compose_path,
                "compose_rel_path": _normalize_compose_rel_path(raw.get("compose_rel_path")),
                "source_kind": "custom",
                "inventory_origin": str(raw.get("inventory_origin") or "custom_registry").strip() or "custom_registry",
                "registry_key": str(raw.get("registry_key") or selector).strip() or selector,
                "profile_model_id": profile_model_id,
                "profile_engine_id": str(raw.get("profile_engine_id") or "").strip(),
                "profile_workload_id": str(raw.get("profile_workload_id") or "").strip(),
                "profile_drafter_id": str(raw.get("profile_drafter_id") or "").strip(),
                "target_resource_key": str(raw.get("target_resource_key") or "").strip(),
                "target_resource_path": str(raw.get("target_resource_path") or "").strip(),
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
        custom_preset = _custom_registry_row_is_preset(raw)
        model_id = _custom_registry_parent_model_id(raw, record_id)
        profile_model_id = str(raw.get("profile_model_id") or (model_id if custom_preset else "") or "").strip()
        clean.append(
            {
                "id": record_id,
                "selector": selector,
                "slug": str(raw.get("slug") or "").strip(),
                "source_selector": str(raw.get("source_selector") or "").strip(),
                "replacement_selector": str(raw.get("replacement_selector") or "").strip(),
                "source_compose_rel_path": _normalize_compose_rel_path(raw.get("source_compose_rel_path")),
                "source_compose_sha256": str(raw.get("source_compose_sha256") or "").strip(),
                "source_status_kind": str(raw.get("source_status_kind") or "").strip(),
                "model_id": model_id,
                "model_display_name": str(raw.get("model_display_name") or "").strip(),
                "display_name": str(raw.get("display_name") or raw.get("slug") or record_id).strip() or record_id,
                "custom_preset": bool(custom_preset),
                "profile_like": str(raw.get("profile_like") or "").strip(),
                "compose_path": compose_path,
                "compose_rel_path": _normalize_compose_rel_path(raw.get("compose_rel_path")),
                "inventory_origin": str(raw.get("inventory_origin") or "custom_registry").strip() or "custom_registry",
                "registry_key": str(raw.get("registry_key") or selector).strip() or selector,
                "profile_model_id": profile_model_id,
                "profile_engine_id": str(raw.get("profile_engine_id") or "").strip(),
                "profile_workload_id": str(raw.get("profile_workload_id") or "").strip(),
                "profile_drafter_id": str(raw.get("profile_drafter_id") or "").strip(),
                "target_resource_key": str(raw.get("target_resource_key") or "").strip(),
                "target_resource_path": str(raw.get("target_resource_path") or "").strip(),
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


def _looks_like_runtime_compose_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(256 * 1024)
    except Exception:
        return False
    lowered = text.lower()
    return "services:" in lowered and ("command:" in lowered or "image:" in lowered or "container_name:" in lowered)


def _normalize_migrated_ik_llama_compose(compose_text):
    text = str(compose_text or "")
    if "ik-llama" not in text.lower() and "ikawrakow/ik-llama" not in text.lower():
        return text
    text = re.sub(
        r"--multi-token-prediction\s*\n(\s*)--draft-max\s+([^\s]+)\s*\n\1--draft-p-min\s+([^\s]+)",
        r"--spec-type mtp:n_max=\2,p_min=\3",
        text,
    )
    text = re.sub(
        r"--spec-stage\s+ngram-mod:([^\n]*?)(?:spec-ngram-size-n|ngram-size-n)=([^\s,]+)",
        r"--spec-type ngram-mod:\1ngram_size_n=\2",
        text,
    )
    text = re.sub(
        r"--spec-stage\s+mtp:n_max=([^,\s]+),(?:draft-p-min|p_min)=([^\s]+)",
        r"--spec-type mtp:n_max=\1,p_min=\2",
        text,
    )
    return text


def _copy_migrated_compose_file(source_path, record_id, backup_root=""):
    source_abs = os.path.abspath(str(source_path or "").strip())
    if not os.path.exists(source_abs):
        raise ValueError(f"Migration source compose is missing: {source_path}")
    with open(source_abs, "r", encoding="utf-8", errors="replace") as handle:
        compose_text = handle.read()
    target_dir = os.path.join(CUSTOM_MODELS_DIR, record_id)
    compose_text = _rewrite_compose_relative_volume_sources(compose_text, os.path.dirname(source_abs))
    compose_text = _vendor_migrated_compose_file_volume_sources(
        compose_text,
        os.path.dirname(source_abs),
        target_dir,
        backup_root=backup_root,
    )
    compose_text = _rename_compose_service_identity(compose_text, record_id)
    compose_text = _normalize_migrated_ik_llama_compose(compose_text)
    target_path = os.path.join(target_dir, "docker-compose.yml")
    write_text_atomic_if_changed(target_path, compose_text)
    return target_path


def _migration_compose_candidates(backup_dir):
    root = os.path.abspath(str(backup_dir or "").strip())
    if not root or not os.path.isdir(root):
        return []
    patterns = [
        os.path.join(root, "models", "*", "*", "compose", "**", "*.yml"),
        os.path.join(root, "models", "*", "*", "compose", "**", "*.yaml"),
        os.path.join(root, "custom-models", "**", "*.yml"),
        os.path.join(root, "custom-models", "**", "*.yaml"),
    ]
    candidates = []
    seen = set()
    for pattern in patterns:
        for path in glob.glob(pattern, recursive=True):
            abs_path = os.path.abspath(path)
            if abs_path in seen or not os.path.isfile(abs_path):
                continue
            try:
                rel_path = os.path.relpath(abs_path, root).replace("\\", "/")
            except Exception:
                rel_path = ""
            if _compose_rel_path_is_archived(rel_path):
                continue
            seen.add(abs_path)
            if _looks_like_runtime_compose_file(abs_path):
                candidates.append(abs_path)
    return sorted(candidates)


def _current_compose_rel_paths():
    repo_root = os.path.abspath(CLUB3090_DIR)
    rels = {
        _normalize_compose_rel_path((entry or {}).get("compose_path"))
        for entry in _load_upstream_compose_registry().values()
        if _normalize_compose_rel_path((entry or {}).get("compose_path"))
        and not _compose_rel_path_is_archived((entry or {}).get("compose_path"))
    }
    for path in glob.glob(os.path.join(repo_root, "models", "*", "*", "compose", "**", "*.yml"), recursive=True):
        try:
            rel = os.path.relpath(path, repo_root).replace("\\", "/")
            if not _compose_rel_path_is_archived(rel):
                rels.add(rel)
        except Exception:
            continue
    for path in glob.glob(os.path.join(repo_root, "models", "*", "*", "compose", "**", "*.yaml"), recursive=True):
        try:
            rel = os.path.relpath(path, repo_root).replace("\\", "/")
            if not _compose_rel_path_is_archived(rel):
                rels.add(rel)
        except Exception:
            continue
    return {rel for rel in rels if rel}


def _current_compose_matches_source(rel_path, source_path):
    rel = _normalize_compose_rel_path(rel_path)
    current_path = os.path.join(os.path.abspath(CLUB3090_DIR), rel.replace("/", os.sep))
    if not rel or not os.path.isfile(current_path) or not os.path.isfile(source_path):
        return False
    try:
        with open(current_path, "rb") as left, open(source_path, "rb") as right:
            return hashlib.sha256(left.read()).hexdigest() == hashlib.sha256(right.read()).hexdigest()
    except Exception:
        return False


def _load_compose_registry_from_root(root):
    registry_path = os.path.join(os.path.abspath(str(root or "")), "scripts", "lib", "profiles", "compose_registry.py")
    if not os.path.isfile(registry_path):
        return {}
    try:
        module_name = f"club3090_backup_compose_registry_{_selector_token(root)}_{int(time.time() * 1000)}"
        spec = importlib.util.spec_from_file_location(module_name, registry_path)
        if spec is None or spec.loader is None:
            return {}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {str(key): dict(value or {}) for key, value in dict(getattr(module, "COMPOSE_REGISTRY", {}) or {}).items()}
    except Exception as exc:
        log_control(f"WARN failed to read backup compose registry {registry_path}: {exc}")
        return {}


def _migration_source_metadata(source_path, backup_dir, rel_path_override=""):
    backup_root = os.path.abspath(str(backup_dir or "").strip())
    rel_path = _normalize_compose_rel_path(rel_path_override) or os.path.relpath(source_path, backup_root).replace("\\", "/")
    registry = _load_compose_registry_from_root(backup_root)
    for selector, entry in registry.items():
        if _normalize_compose_rel_path(entry.get("compose_path")) == rel_path:
            status_kind = _normalize_status_kind(entry.get("status") or "")
            return {
                "selector": selector,
                "entry": entry,
                "status_kind": status_kind if status_kind != "unknown" else "experimental",
                "rel_path": rel_path,
            }
    parts = rel_path.split("/")
    selector = ""
    entry = {}
    if len(parts) >= 7 and parts[0] == "models" and parts[3] == "compose":
        engine = parts[2]
        topology = parts[4]
        stem = os.path.splitext(parts[-1])[0]
        if engine and topology and stem and stem not in {"docker-compose", "compose"}:
            selector = f"{engine}/{topology}-{stem}"
            entry = {
                "model": parts[1],
                "engine": engine,
                "compose_path": rel_path,
            }
    return {"selector": selector, "entry": entry, "status_kind": "experimental", "rel_path": rel_path}


def _migration_git_show_text(repo_root, object_spec):
    root = os.path.abspath(str(repo_root or "").strip())
    spec = str(object_spec or "").strip()
    if not root or not spec:
        return ""
    try:
        proc = subprocess.run(
            ["git", "-C", root, "show", spec],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            check=False,
        )
    except Exception:
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def _migration_git_deleted_nvlink_sources(backup_dir):
    backup_root = os.path.abspath(str(backup_dir or "").strip())
    if not backup_root or not os.path.isdir(os.path.join(backup_root, ".git")):
        return []
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                backup_root,
                "log",
                "--all",
                "--diff-filter=D",
                "--name-only",
                "--pretty=format:COMMIT %H",
                "--",
                "models/*/*/compose/**/*nvlink*.yml",
                "models/*/*/compose/**/*nvlink*.yaml",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    seen = set()
    rows = []
    current_commit = ""
    for raw_line in str(proc.stdout or "").splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        if line.startswith("COMMIT "):
            current_commit = line.split(None, 1)[1].strip()
            continue
        rel_path = _normalize_compose_rel_path(line)
        if not rel_path or not rel_path.lower().endswith((".yml", ".yaml")):
            continue
        if _compose_rel_path_is_archived(rel_path):
            continue
        if "nvlink" not in rel_path.lower() or rel_path in seen or not current_commit:
            continue
        text = _migration_git_show_text(backup_root, f"{current_commit}^:{rel_path}")
        if not text.strip() or "NVLINK_MODE=force_on" not in text:
            continue
        registry_text = _migration_git_show_text(backup_root, f"{current_commit}^:scripts/lib/profiles/compose_registry.py")
        source_selector = ""
        source_entry = {}
        if registry_text:
            try:
                module_name = f"club3090_legacy_nvlink_registry_{_selector_token(current_commit)}_{len(rows)}"
                spec = importlib.util.spec_from_loader(module_name, loader=None)
                module = importlib.util.module_from_spec(spec)
                exec(compile(registry_text, f"{module_name}.py", "exec"), module.__dict__)
                for selector, entry in dict(getattr(module, "COMPOSE_REGISTRY", {}) or {}).items():
                    if _normalize_compose_rel_path((entry or {}).get("compose_path")) == rel_path:
                        source_selector = str(selector or "").strip()
                        source_entry = dict(entry or {})
                        break
            except Exception:
                source_selector = ""
                source_entry = {}
        if not source_selector:
            stem = os.path.splitext(os.path.basename(rel_path))[0]
            stem = re.sub(r"^nvlink-fp8-mtp$", "dual-nvlink", stem)
            stem = re.sub(r"^nvlink-", "dual-nvlink-", stem)
            source_selector = f"vllm/{stem}"
        source_entry.setdefault("compose_path", rel_path)
        source_entry["requires_nvlink"] = True
        scratch_root = os.path.join(CONTROL_DIR, "migration-recovered", _selector_token(os.path.basename(backup_root) or "backup"))
        recovered_path = os.path.join(scratch_root, rel_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(recovered_path), exist_ok=True)
        try:
            with open(recovered_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text.rstrip() + "\n")
        except Exception:
            continue
        seen.add(rel_path)
        rows.append({
            "path": recovered_path,
            "rel_path": rel_path,
            "source_meta": {
                "selector": source_selector,
                "entry": source_entry,
                "status_kind": "deprecated",
                "target_status_kind": "deprecated",
                "inventory_origin": "deprecated_backup_registry",
                "rel_path": rel_path,
                "legacy_deleted_commit": current_commit,
            },
            "force_import": True,
        })
    return rows


def _migration_deprecated_registry_sources(backup_dir, current_registry=None):
    backup_root = os.path.abspath(str(backup_dir or "").strip())
    current = dict(current_registry or {})
    rows = []
    for selector, entry in _load_compose_registry_from_root(backup_root).items():
        source_selector = str(selector or "").strip()
        if _normalize_status_kind((entry or {}).get("status") or "") != "deprecated":
            continue
        current_entry = current.get(source_selector) or current.get(_migration_strip_old_suffix(source_selector))
        if current_entry and _normalize_status_kind((current_entry or {}).get("status") or "") == "deprecated":
            continue
        rel_path = _normalize_compose_rel_path((entry or {}).get("compose_path"))
        if not rel_path or _compose_rel_path_is_archived(rel_path):
            continue
        source_path = os.path.join(backup_root, rel_path.replace("/", os.sep))
        if not os.path.isfile(source_path) or not _looks_like_runtime_compose_file(source_path):
            continue
        rows.append({
            "path": source_path,
            "rel_path": rel_path,
            "source_meta": {
                "selector": source_selector,
                "entry": dict(entry or {}),
                "status_kind": "deprecated",
                "target_status_kind": "deprecated",
                "inventory_origin": "deprecated_backup_registry",
                "rel_path": rel_path,
            },
            "force_import": True,
        })
    return rows


def _migration_strip_old_suffix(value):
    text = str(value or "").strip()
    while True:
        match = re.fullmatch(r"(.+?)-old(?:\s*\(\d+\)|-\d+)?", text, flags=re.IGNORECASE)
        if not match:
            break
        text = match.group(1).rstrip()
    return text


def _migration_public_selector(source_selector, use_old_suffix=False, old_generation=1):
    base_selector = _migration_strip_old_suffix(source_selector)
    if not base_selector:
        return ""
    if use_old_suffix:
        try:
            generation = max(1, int(old_generation or 1))
        except Exception:
            generation = 1
        if generation > 1:
            return f"{base_selector}-OLD ({generation})"
        return f"{base_selector}-OLD"
    return base_selector


def _migration_source_candidates(source_selector):
    raw = str(source_selector or "").strip()
    base = _migration_strip_old_suffix(raw)
    candidates = {item for item in (raw, base) if item}
    if base:
        candidates.add(f"{base}-OLD")
    tokenized = {_selector_token(item) for item in candidates if item}
    candidates.update(item for item in tokenized if item)
    return candidates


def _migration_existing_row_matches(row, rel_path, source_selector):
    rel = _normalize_compose_rel_path(rel_path)
    if rel and str(row.get("source_compose_rel_path") or "") == rel:
        return True
    candidates = _migration_source_candidates(source_selector)
    if not candidates:
        return False
    row_values = {
        str(row.get("source_selector") or "").strip(),
        str(row.get("slug") or "").strip(),
        str(row.get("display_name") or "").strip(),
        str(row.get("profile_like") or "").strip(),
    }
    row_selector = str(row.get("selector") or "").strip()
    if row_selector.startswith("custom/"):
        row_values.add(row_selector[len("custom/") :])
    normalized_values = set(row_values)
    normalized_values.update(_migration_strip_old_suffix(value) for value in row_values if value)
    return bool(candidates.intersection(item for item in normalized_values if item))


def _migration_row_compose_matches_source(row, source_path):
    source_hash = _migration_file_sha256(source_path)
    row_hash = str((row or {}).get("source_compose_sha256") or "").strip()
    if source_hash and row_hash:
        return source_hash == row_hash
    compose_path = str((row or {}).get("compose_path") or "").strip()
    if not compose_path or not source_path or not os.path.isfile(compose_path) or not os.path.isfile(source_path):
        return False
    try:
        with open(compose_path, "rb") as left, open(source_path, "rb") as right:
            return hashlib.sha256(left.read()).hexdigest() == hashlib.sha256(right.read()).hexdigest()
    except Exception:
        return False


def _migration_old_generation_for_row(row, source_selector):
    base_selector = _migration_strip_old_suffix(source_selector)
    if not base_selector:
        return 0
    public_base = f"{base_selector}-OLD"
    generation = 0
    for key in ("display_name", "slug", "source_selector", "profile_like"):
        value = str((row or {}).get(key) or "").strip()
        if value == public_base:
            generation = max(generation, 1)
            continue
        match = re.fullmatch(re.escape(public_base) + r"\s*\((\d+)\)", value)
        if match:
            try:
                generation = max(generation, int(match.group(1)))
            except Exception:
                pass
    base_token = _selector_token(public_base)
    for key in ("id", "selector", "registry_key", "upstream_tag"):
        value = str((row or {}).get(key) or "").strip()
        if value.startswith("custom/"):
            value = value[len("custom/"):]
        token = _selector_token(value)
        if token == base_token:
            generation = max(generation, 1)
            continue
        match = re.fullmatch(re.escape(base_token) + r"-(\d+)", token)
        if match:
            try:
                generation = max(generation, int(match.group(1)))
            except Exception:
                pass
    return generation


def _migration_next_old_generation(rows, source_selector):
    generations = [
        _migration_old_generation_for_row(row, source_selector)
        for row in (rows or [])
        if isinstance(row, dict)
    ]
    return max([0] + [value for value in generations if value > 0]) + 1


def _migration_file_sha256(path):
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except Exception:
        return ""


def _migration_unique_record_id(base, used_ids):
    base_id = _selector_token(base)
    record_id = base_id
    suffix = 2
    while record_id in used_ids:
        record_id = f"{base_id}-{suffix}"
        suffix += 1
    return record_id


def _migration_replace_json_strings(value, replacements):
    if isinstance(value, dict):
        return {key: _migration_replace_json_strings(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_migration_replace_json_strings(item, replacements) for item in value]
    if isinstance(value, str):
        text = value
        for old, new in replacements:
            if old:
                text = text.replace(old, new)
        return text
    return value


def _migration_score_dir_candidates(source_token, include_live=True):
    benchmarks_dir = os.path.join(CONTROL_DIR, "benchmarks")
    candidates = []
    seen = set()
    if include_live:
        live_candidate = os.path.join(benchmarks_dir, "presets", source_token)
        candidates.append(live_candidate)
        seen.add(os.path.abspath(live_candidate))
    try:
        children = sorted(os.listdir(benchmarks_dir))
    except Exception:
        children = []
    for child in children:
        if child == "presets":
            continue
        candidate = os.path.join(benchmarks_dir, child, source_token)
        normalized = os.path.abspath(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(candidate)
    return candidates


def _migration_score_dir_has_results(path):
    if not os.path.isdir(path):
        return False
    for name in ("quick-latest.json", "full-latest.json", "latest.json"):
        payload = read_json_file(os.path.join(path, name), {})
        if isinstance(payload, dict) and str(payload.get("status") or "").strip().lower() == "complete" and payload.get("score") is not None:
            return True
    return False


def _migration_canonicalize_relinked_score_dir(target_dir):
    if not os.path.isdir(target_dir):
        return 0
    changed = 0
    keep_run_ids = set()
    run_modes = {}
    runs_dir = os.path.join(target_dir, "runs")

    def push_chain_id(stack, seen, value):
        run_id = str(value or "").strip()
        if not run_id or run_id in seen:
            return
        seen.add(run_id)
        stack.append(run_id)

    def keep_result_run_chain(payload):
        if not isinstance(payload, dict):
            return []
        stack = []
        seen = set()
        for key in ("run_id", "base_run_id", "repair_run_id"):
            push_chain_id(stack, seen, payload.get(key))
        repair = payload.get("repair") if isinstance(payload.get("repair"), dict) else {}
        for key in ("base_run_id", "repair_run_id"):
            push_chain_id(stack, seen, repair.get(key))
        artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
        artifact_run_dir = str((artifacts or {}).get("run_dir") or "").replace("\\", "/").strip("/")
        if artifact_run_dir:
            push_chain_id(stack, seen, artifact_run_dir.rsplit("/", 1)[-1])
        ordered = []
        while stack:
            run_id = stack.pop(0)
            if run_id in ordered:
                continue
            ordered.append(run_id)
            run_payload = read_json_file(os.path.join(runs_dir, run_id, "run.json"), {})
            if not isinstance(run_payload, dict):
                continue
            for key in ("run_id", "base_run_id", "repair_run_id"):
                push_chain_id(stack, seen, run_payload.get(key))
            run_repair = run_payload.get("repair") if isinstance(run_payload.get("repair"), dict) else {}
            for key in ("base_run_id", "repair_run_id"):
                push_chain_id(stack, seen, run_repair.get(key))
        return ordered

    for mode in ("quick", "full"):
        path = os.path.join(target_dir, f"{mode}-latest.json")
        payload = read_json_file(path, {})
        if not isinstance(payload, dict) or str(payload.get("status") or "").strip().lower() != "complete":
            continue
        chain_ids = keep_result_run_chain(payload)
        if not chain_ids:
            continue
        keep_run_ids.update(chain_ids)
        sidecar_ids = [str(payload.get("run_id") or "").strip()]
        if not sidecar_ids[0]:
            sidecar_ids = [chain_ids[0]]
        for run_id in sidecar_ids:
            if not run_id:
                continue
            run_modes.setdefault(run_id, set()).add(mode)
            run_dir = os.path.join(target_dir, "runs", run_id)
            os.makedirs(run_dir, exist_ok=True)
            sidecar_path = os.path.join(run_dir, f"{mode}.json")
            if not os.path.isfile(sidecar_path):
                write_json_file(sidecar_path, payload)
                changed += 1
    if os.path.isdir(runs_dir):
        for name in sorted(os.listdir(runs_dir)):
            run_dir = os.path.join(runs_dir, name)
            if not os.path.isdir(run_dir):
                continue
            if keep_run_ids and name not in keep_run_ids:
                shutil.rmtree(run_dir, ignore_errors=True)
                changed += 1
                continue
            allowed = {"run.json"}
            for mode in run_modes.get(name, set()):
                allowed.add(f"{mode}.json")
            for filename in os.listdir(run_dir):
                if not filename.endswith(".json") or filename in allowed:
                    continue
                try:
                    os.remove(os.path.join(run_dir, filename))
                    changed += 1
                except Exception:
                    pass
    return changed


def _migration_relink_score_artifacts(source_selector, target_selector, remove_source=False, fallback_only=False):
    source_selector = str(source_selector or "").strip()
    target_selector = str(target_selector or "").strip()
    if not source_selector or not target_selector:
        return {"copied": False, "updated_json": 0}
    presets_dir = os.path.join(CONTROL_DIR, "benchmarks", "presets")
    source_token = _selector_token(source_selector)
    target_token = _selector_token(target_selector)
    if not source_token or not target_token or source_token == target_token:
        return {"copied": False, "updated_json": 0}
    source_dir = next((path for path in _migration_score_dir_candidates(source_token, include_live=not fallback_only) if _migration_score_dir_has_results(path)), "")
    target_dir = os.path.join(presets_dir, target_token)
    if not source_dir or not os.path.isdir(source_dir):
        return {"copied": False, "updated_json": 0}
    if os.path.isdir(target_dir):
        shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir)
    replacements = [
        (source_selector, target_selector),
        (f"presets/{source_token}", f"presets/{target_token}"),
        (f"/presets/{source_token}", f"/presets/{target_token}"),
    ]
    updated = 0
    for dirpath, _dirnames, filenames in os.walk(target_dir):
        for name in filenames:
            if not name.endswith(".json"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except Exception:
                continue
            next_payload = _migration_replace_json_strings(payload, replacements)
            if next_payload == payload:
                continue
            write_json_file(path, next_payload)
            updated += 1
    updated += _migration_canonicalize_relinked_score_dir(target_dir)
    if remove_source and os.path.abspath(source_dir) != os.path.abspath(target_dir):
        presets_source_dir = os.path.join(presets_dir, source_token)
        if os.path.abspath(source_dir) == os.path.abspath(presets_source_dir) and os.path.isdir(source_dir):
            shutil.rmtree(source_dir, ignore_errors=True)
    return {"copied": True, "updated_json": updated}


def _migration_backfill_existing_row_scores(row, source_meta=None):
    if not isinstance(row, dict):
        return False
    target_selector = str(row.get("selector") or "").strip()
    if not target_selector:
        return False
    target_dir = os.path.join(CONTROL_DIR, "benchmarks", "presets", _selector_token(target_selector))
    if _migration_score_dir_has_results(target_dir):
        return False
    candidates = []
    meta = dict(source_meta or {})
    for value in (
        meta.get("selector"),
        row.get("source_selector"),
        row.get("display_name"),
        row.get("slug"),
        row.get("profile_like"),
        row.get("replacement_selector"),
    ):
        candidate = _migration_strip_old_suffix(str(value or "").strip())
        if candidate and candidate != target_selector and candidate not in candidates:
            candidates.append(candidate)
    for candidate in candidates:
        score_result = _migration_relink_score_artifacts(candidate, target_selector, remove_source=False, fallback_only=True)
        if score_result.get("copied"):
            return True
    return False


def _migration_score_dir_has_mode_result(path, mode):
    mode = "full" if str(mode or "").strip().lower() == "full" else "quick"
    payload = read_json_file(os.path.join(str(path or ""), f"{mode}-latest.json"), {})
    return (
        isinstance(payload, dict)
        and str(payload.get("status") or "").strip().lower() == "complete"
        and payload.get("score") is not None
    )


def _migration_score_dir_mode_rank(path, mode):
    mode = "full" if str(mode or "").strip().lower() == "full" else "quick"
    latest_path = os.path.join(str(path or ""), f"{mode}-latest.json")
    payload = read_json_file(latest_path, {})
    rank_text = ""
    if isinstance(payload, dict):
        for key in ("finished_at", "completed_at", "updated_at", "created_at", "started_at", "timestamp"):
            value = payload.get(key)
            text = str(value or "").strip()
            if text:
                rank_text = text
                break
    try:
        mtime = os.path.getmtime(latest_path)
    except Exception:
        mtime = 0.0
    return (rank_text, mtime)


def _migration_score_fingerprint_switches(text):
    skip_value_for = {
        "--host",
        "--port",
        "--served-model-name",
    }
    tokens = [
        str(line or "").strip()
        for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if str(line or "").strip() and not str(line or "").strip().startswith("#")
    ]
    normalized = []
    skipping = ""
    for token in tokens:
        lower = token.lower()
        if lower.startswith("--"):
            skipping = lower if lower in skip_value_for else ""
            if not skipping:
                if "=" in token:
                    flag, value = token.split("=", 1)
                    normalized.append(f"{flag}={_extract_shell_default_value(value)}")
                else:
                    normalized.append(token)
            continue
        if skipping:
            continue
        normalized.append(_extract_shell_default_value(token))
    return "\n".join(normalized)


def _migration_score_fingerprint_sequence(value):
    if isinstance(value, dict):
        values = [f"{key}={value[key]}" for key in sorted(value)]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = str(value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    normalized = [
        str(item or "").strip()
        for item in values
        if str(item or "").strip()
    ]
    return "\n".join(sorted(normalized))


GENERIC_LAUNCH_ENV_KEYS = {
    "CUDA_VISIBLE_DEVICES",
    "NVIDIA_VISIBLE_DEVICES",
    "VLLM_USE_DEEP_GEMM",
}


def _compose_environment_runtime_sequence(value):
    if isinstance(value, dict):
        raw_values = [f"{key}={value[key]}" for key in sorted(value)]
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = str(value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    normalized = []
    for item in raw_values:
        text = str(item or "").strip()
        if not text or text.startswith("#"):
            continue
        key = re.split(r"\s*[:=]\s*", text, maxsplit=1)[0].strip()
        if key.upper() in GENERIC_LAUNCH_ENV_KEYS:
            continue
        normalized.append(_extract_shell_default_value(text))
    return "\n".join(sorted(normalized))


def _migration_normalize_kv_format(value):
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.match(r"^([A-Za-z0-9_.-]+)", text)
    return match.group(1) if match else text


def _split_compose_colon_fields(value):
    text = str(value or "").strip().strip('"').strip("'")
    if not text:
        return []
    fields = []
    current = []
    brace_depth = 0
    for char in text:
        if char == "$":
            current.append(char)
            continue
        if char == "{" and current and current[-1] == "$":
            brace_depth += 1
            current.append(char)
            continue
        if char == "}" and brace_depth:
            brace_depth -= 1
            current.append(char)
            continue
        if char == ":" and brace_depth == 0:
            fields.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    fields.append("".join(current).strip())
    return fields


def _compose_volume_target_signature(value):
    fields = _split_compose_colon_fields(value)
    if len(fields) < 2:
        return str(value or "").strip()
    target = fields[1].strip()
    options = ":".join(part.strip() for part in fields[2:] if str(part or "").strip())
    return f"{target}:{options}" if options else target


def _compose_volume_target_sequence(value):
    if isinstance(value, dict):
        raw_values = [f"{key}:{value[key]}" for key in sorted(value)]
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = str(value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    signatures = [
        _compose_volume_target_signature(item)
        for item in raw_values
        if str(item or "").strip() and not str(item or "").strip().startswith("#")
    ]
    return "\n".join(sorted(item for item in signatures if item))


def _migration_score_runtime_fingerprint(row):
    if not isinstance(row, dict):
        return ""
    def numeric(value):
        try:
            return int(float(value or 0) or 0)
        except Exception:
            return 0

    payload = {
        "model_id": str(row.get("model_id") or row.get("profile_model_id") or "").strip(),
        "engine": str(row.get("engine") or row.get("engine_display") or "").strip().lower(),
        "topology": str(row.get("topology") or row.get("scope_kind") or "").strip().lower(),
        "max_model_len": numeric(row.get("max_model_len")),
        "tensor_parallel": numeric(row.get("tensor_parallel") or row.get("requires_min_gpu_count")),
        "model_path": str(row.get("model_path") or "").strip(),
        "draft_model_path": str(row.get("draft_model_path") or "").strip(),
        "mmproj_path": str(row.get("mmproj_path") or "").strip(),
        "drafter": str(row.get("drafter") or row.get("drafter_profile") or "").strip(),
        "kv_format": _migration_normalize_kv_format(row.get("kv_format")),
        "service_image": str(row.get("service_image") or row.get("image") or row.get("container_image") or "").strip(),
        "compose_environment": _compose_environment_runtime_sequence(row.get("compose_environment") or row.get("environment") or []),
        "compose_volume_targets": _compose_volume_target_sequence(row.get("compose_volume_targets") or row.get("compose_volumes") or row.get("volumes") or []),
        "switches": _migration_score_fingerprint_switches(row.get("default_engine_switches") or ""),
    }
    if not payload["model_id"] or not payload["engine"] or not payload["switches"]:
        return ""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _migration_compose_runtime_fingerprint(path, entry=None, selector="", rel_path=""):
    path = str(path or "").strip()
    if not path or not os.path.isfile(path):
        return ""
    entry = dict(entry or {})
    selector = str(selector or "").strip()
    rel_path = _normalize_compose_rel_path(rel_path)
    profile = _read_compose_profile_header(path)
    runtime_meta = _read_compose_runtime_metadata(path)
    engine_hint = " ".join([selector, rel_path, path]).lower()
    engine = str(entry.get("engine") or "").strip()
    engine_family = "llamacpp" if ("llamacpp" in engine_hint or "llama-cpp" in engine_hint or "ik-llama" in engine_hint) else "vllm"
    topology_hint = "multi" if int(entry.get("tp") or runtime_meta.get("tensor_parallel") or 1) > 2 else ("dual" if int(entry.get("tp") or runtime_meta.get("tensor_parallel") or 1) > 1 else "")
    topology = _infer_topology_from_compose_path(rel_path or path.replace("\\", "/"), topology_hint)
    if engine_family == "llamacpp":
        max_model_len = int(runtime_meta.get("max_model_len") or _extract_token_count(profile.get("max_ctx") or profile.get("default_ctx")) or entry.get("max_ctx") or 0)
    else:
        max_model_len = int(entry.get("max_ctx") or runtime_meta.get("max_model_len") or _extract_token_count(profile.get("max_ctx") or profile.get("default_ctx")) or 0)
    row = {
        "model_id": str(entry.get("model") or entry.get("model_id") or entry.get("profile_model_id") or "").strip() or _model_id_from_compose_rel_path(rel_path),
        "engine": engine_family,
        "topology": topology,
        "max_model_len": max_model_len,
        "tensor_parallel": int(entry.get("tp") or runtime_meta.get("tensor_parallel") or 0),
        "model_path": runtime_meta.get("model_path") or "",
        "draft_model_path": runtime_meta.get("draft_model_path") or "",
        "mmproj_path": runtime_meta.get("mmproj_path") or "",
        "drafter": str(entry.get("drafter") or entry.get("profile_drafter_id") or runtime_meta.get("speculative_method") or profile.get("drafter") or "").strip(),
        "kv_format": str(entry.get("kv_format") or (entry.get("compose_meta") or {}).get("kv_format") or profile.get("kv") or "").strip(),
        "service_image": str(runtime_meta.get("service_image") or "").strip(),
        "compose_environment": list(runtime_meta.get("compose_environment") or []),
        "compose_volumes": list(runtime_meta.get("compose_volumes") or []),
        "compose_volume_targets": list(runtime_meta.get("compose_volume_targets") or []),
        "default_engine_switches": _read_compose_command_text(path),
    }
    return _migration_score_runtime_fingerprint(row)


def _model_id_from_compose_rel_path(rel_path):
    parts = _normalize_compose_rel_path(rel_path).split("/")
    return parts[1] if len(parts) >= 2 and parts[0] == "models" else ""


def _migration_compose_runtime_equivalent(source_path, source_entry, source_selector, source_rel, current_path, current_entry, current_selector, current_rel):
    source_fp = _migration_compose_runtime_fingerprint(source_path, source_entry, source_selector, source_rel)
    current_fp = _migration_compose_runtime_fingerprint(current_path, current_entry, current_selector, current_rel)
    return bool(source_fp and current_fp and source_fp == current_fp)


def _migration_current_selector_entry(current_registry, selector):
    selector = str(selector or "").strip()
    candidates = [selector, _migration_strip_old_suffix(selector)]
    for candidate in candidates:
        if candidate and isinstance(current_registry.get(candidate), dict):
            return candidate, dict(current_registry.get(candidate) or {})
    return "", {}


def _migration_prune_runtime_equivalent_old_rows(rows, current_registry):
    kept = []
    pruned = []
    score_relinked = 0
    for row in rows or []:
        if not isinstance(row, dict):
            kept.append(row)
            continue
        source_selector = str(row.get("source_selector") or row.get("display_name") or row.get("slug") or "").strip()
        if _migration_old_generation_for_row(row, source_selector) <= 0:
            kept.append(row)
            continue
        origin = str(row.get("inventory_origin") or "").strip()
        if origin not in {"migrated_custom_registry", "deprecated_backup_registry"}:
            kept.append(row)
            continue
        current_selector, current_entry = _migration_current_selector_entry(current_registry, source_selector)
        current_rel = _normalize_compose_rel_path((current_entry or {}).get("compose_path"))
        current_path = os.path.join(os.path.abspath(CLUB3090_DIR), current_rel.replace("/", os.sep)) if current_rel else ""
        row_path = str(row.get("compose_path") or "").strip()
        if not row_path or not current_path:
            kept.append(row)
            continue
        if _migration_compose_runtime_equivalent(
            row_path,
            row,
            str(row.get("selector") or row.get("display_name") or ""),
            _normalize_compose_rel_path(row.get("compose_rel_path") or row.get("source_compose_rel_path")),
            current_path,
            current_entry,
            current_selector,
            current_rel,
        ):
            row_selector = str(row.get("selector") or "").strip()
            score_result = _migration_relink_score_artifacts(row_selector, current_selector, remove_source=True, fallback_only=False)
            if score_result.get("copied"):
                score_relinked += 1
            _migration_copy_tps_stats(row_selector, current_selector)
            pruned.append(row)
            continue
        kept.append(row)
    return kept, {"pruned": pruned, "score_relinked": score_relinked}


def _migration_normalize_migrated_public_name_collisions(current_registry=None, tag_by_compose=None):
    current_registry = current_registry or _load_upstream_compose_registry()
    tag_by_compose = dict(tag_by_compose or {})
    rows = read_custom_model_registry()
    live_current_by_base = {}
    live_current_by_rel = {}
    for selector, entry in dict(current_registry or {}).items():
        selector = str(selector or "").strip()
        if not selector:
            continue
        compose_rel = _normalize_compose_rel_path((entry or {}).get("compose_path"))
        if compose_rel and _compose_rel_path_is_archived(compose_rel):
            continue
        if compose_rel:
            live_current_by_rel.setdefault(compose_rel, selector)
        base = _migration_strip_old_suffix(selector)
        if base:
            live_current_by_base.setdefault(base, selector)
    for source_path in _migration_compose_candidates(CLUB3090_DIR):
        try:
            rel = _normalize_compose_rel_path(os.path.relpath(source_path, os.path.abspath(CLUB3090_DIR)).replace("\\", "/"))
        except Exception:
            rel = ""
        selector = str(tag_by_compose.get(rel) or "").strip()
        if not rel or not selector or _compose_rel_path_is_archived(rel):
            continue
        live_current_by_rel.setdefault(rel, selector)
        base = _migration_strip_old_suffix(selector)
        if base:
            live_current_by_base.setdefault(base, selector)
    current_rels = _current_compose_rel_paths()
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_rel = _normalize_compose_rel_path(row.get("source_compose_rel_path"))
        if not source_rel or source_rel not in current_rels:
            continue
        source_selector = str(row.get("source_selector") or row.get("display_name") or row.get("slug") or row.get("profile_like") or "").strip()
        base = _migration_strip_old_suffix(source_selector)
        if base:
            live_current_by_base.setdefault(base, live_current_by_rel.get(source_rel) or base)
    if not live_current_by_base:
        return 0
    changed = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        origin = str(row.get("inventory_origin") or "").strip()
        if origin not in {"migrated_custom_registry", "deprecated_backup_registry"}:
            continue
        row_selector = str(row.get("selector") or "").strip()
        if row_selector and not row_selector.startswith("custom/"):
            continue
        source_selector = str(row.get("source_selector") or row.get("display_name") or row.get("slug") or row.get("profile_like") or "").strip()
        base = _migration_strip_old_suffix(source_selector)
        current_selector = live_current_by_base.get(base or "")
        if not base or not current_selector:
            continue
        if _migration_old_generation_for_row(row, base) > 0:
            if str(row.get("replacement_selector") or "").strip() != current_selector:
                row["replacement_selector"] = current_selector
                changed += 1
            continue
        public_selector = _migration_public_selector(
            base,
            use_old_suffix=True,
            old_generation=_migration_next_old_generation(rows, base),
        )
        updates = {
            "display_name": public_selector,
            "slug": public_selector,
            "source_selector": base,
            "profile_like": base,
            "replacement_selector": current_selector,
            "gate_reason": (
                str(row.get("gate_reason") or "").strip()
                or f"Preserved pre-migration preset {base} with an -OLD suffix because the updated upstream checkout contains a preset at the same selector."
            ),
            "compat_reason_summary": f"Pre-migration preset preserved as {public_selector} for historical comparison.",
        }
        for key, value in updates.items():
            if row.get(key) != value:
                row[key] = value
                changed += 1
    if changed:
        write_custom_model_registry(rows)
        log_control(f"MIGRATE normalized {changed} migrated custom public name collision field(s)")
    return changed


def _migration_runtime_variant_selector(row):
    return str((row or {}).get("selector") or (row or {}).get("upstream_tag") or (row or {}).get("registry_key") or "").strip()


def _migration_runtime_variant_lineage_base(row):
    if not isinstance(row, dict):
        return ""
    for key in ("source_selector", "display_name", "slug", "profile_like", "replacement_selector", "selector", "upstream_tag", "registry_key"):
        value = str(row.get(key) or "").strip()
        if value:
            base = _migration_strip_old_suffix(value)
            if base:
                return base
    return ""


def _migration_prune_runtime_equivalent_hydrated_old_rows(rows, inventory):
    variants = [row for row in ((inventory or {}).get("variants") or []) if isinstance(row, dict)]
    if not rows or not variants:
        return rows, {"pruned": [], "score_relinked": 0}
    current_by_base = {}
    for variant in variants:
        selector = _migration_runtime_variant_selector(variant)
        if not selector:
            continue
        generation = _migration_old_generation_for_row(variant, variant.get("source_selector") or variant.get("display_name") or selector)
        if generation > 0:
            continue
        base = _migration_runtime_variant_lineage_base(variant)
        if not base:
            continue
        rank = 0
        if not selector.startswith("custom/"):
            rank += 100
        if str(variant.get("inventory_origin") or "").strip() not in {"migrated_custom_registry", "deprecated_backup_registry", "legacy_backup_registry"}:
            rank += 50
        if str(variant.get("status_kind") or "").strip() not in {"migrated", "deprecated"}:
            rank += 10
        previous = current_by_base.get(base)
        if not previous or rank > previous[0]:
            current_by_base[base] = (rank, variant)
    variant_by_selector = {
        _migration_runtime_variant_selector(variant): variant
        for variant in variants
        if _migration_runtime_variant_selector(variant)
    }
    kept = []
    pruned = []
    score_relinked = 0
    for row in rows or []:
        if not isinstance(row, dict):
            kept.append(row)
            continue
        origin = str(row.get("inventory_origin") or "").strip()
        if origin not in {"migrated_custom_registry", "deprecated_backup_registry"}:
            kept.append(row)
            continue
        source_selector = str(row.get("source_selector") or row.get("display_name") or row.get("slug") or "").strip()
        if _migration_old_generation_for_row(row, source_selector) <= 0:
            kept.append(row)
            continue
        row_selector = str(row.get("selector") or "").strip()
        row_variant = variant_by_selector.get(row_selector)
        base = _migration_runtime_variant_lineage_base(row_variant or row)
        current_variant = (current_by_base.get(base) or (None, None))[1] if base else None
        current_selector = _migration_runtime_variant_selector(current_variant) if current_variant else ""
        if (
            not row_variant
            or not current_variant
            or not row_selector
            or not current_selector
            or row_selector == current_selector
            or _migration_score_runtime_fingerprint(row_variant) != _migration_score_runtime_fingerprint(current_variant)
        ):
            kept.append(row)
            continue
        score_result = _migration_relink_score_artifacts(row_selector, current_selector, remove_source=True, fallback_only=False)
        if score_result.get("copied"):
            score_relinked += 1
        _migration_copy_tps_stats(row_selector, current_selector)
        pruned.append(row)
    return kept, {"pruned": pruned, "score_relinked": score_relinked}


def _migration_backfill_equivalent_runtime_scores(inventory):
    variants = [
        row for row in ((inventory or {}).get("variants") or [])
        if isinstance(row, dict) and str(row.get("selector") or row.get("upstream_tag") or "").strip()
    ]
    by_fingerprint = {}
    for row in variants:
        fingerprint = _migration_score_runtime_fingerprint(row)
        if not fingerprint:
            continue
        by_fingerprint.setdefault(fingerprint, []).append(row)
    copied = 0
    for fingerprint_rows in by_fingerprint.values():
        scored_sources = []
        for source in fingerprint_rows:
            source_selector = str(source.get("selector") or source.get("upstream_tag") or "").strip()
            if not source_selector:
                continue
            source_dir = os.path.join(CONTROL_DIR, "benchmarks", "presets", _selector_token(source_selector))
            if _migration_score_dir_has_mode_result(source_dir, "full"):
                scored_sources.append(
                    {
                        "selector": source_selector,
                        "dir": source_dir,
                        "has_quick": _migration_score_dir_has_mode_result(source_dir, "quick"),
                        "rank": _migration_score_dir_mode_rank(source_dir, "full"),
                    }
                )
        if not scored_sources:
            continue
        for target in fingerprint_rows:
            target_selector = str(target.get("selector") or target.get("upstream_tag") or "").strip()
            if not target_selector:
                continue
            target_dir = os.path.join(CONTROL_DIR, "benchmarks", "presets", _selector_token(target_selector))
            if _migration_score_dir_has_mode_result(target_dir, "full"):
                continue
            target_has_quick = _migration_score_dir_has_mode_result(target_dir, "quick")
            candidates = [
                source
                for source in scored_sources
                if source.get("selector") != target_selector and (not target_has_quick or source.get("has_quick"))
            ]
            if not candidates:
                continue
            source = max(candidates, key=lambda item: item.get("rank") or ("", 0.0))
            source_selector = source.get("selector") or ""
            score_result = _migration_relink_score_artifacts(source_selector, target_selector, remove_source=False, fallback_only=False)
            if score_result.get("copied"):
                copied += 1
    return copied


def _migration_copy_tps_stats(source_selector, target_selector):
    target_key = _preset_tps_selector_key(target_selector)
    source_candidates = []
    for value in source_selector, _migration_strip_old_suffix(source_selector):
        key = _preset_tps_selector_key(value)
        if key and key not in source_candidates:
            source_candidates.append(key)
    target_text = str(target_selector or "").strip()
    target_base = _migration_strip_old_suffix(target_text)
    for value in target_base, target_text.replace("-OLD", "").replace("-old", ""):
        key = _preset_tps_selector_key(value)
        if key and key not in source_candidates:
            source_candidates.append(key)
    if not source_candidates or not target_key:
        return False
    with preset_tps_stats_lock:
        rows = _read_preset_tps_stats_unlocked()
        source_row = next((rows.get(key) for key in source_candidates if key != target_key and rows.get(key)), None)
        if not source_row:
            return False
        if _sanitize_preset_tps_row(rows.get(target_key) or {}) == _sanitize_preset_tps_row(source_row):
            return False
        rows[target_key] = _sanitize_preset_tps_row(source_row)
        _write_preset_tps_stats_unlocked(rows)
    return True


def _migration_copy_row_tps_stats(row):
    if not isinstance(row, dict):
        return False
    target_selector = str(row.get("selector") or "").strip()
    candidates = [
        row.get("source_selector"),
        row.get("display_name"),
        row.get("slug"),
        row.get("profile_like"),
        row.get("replacement_selector"),
    ]
    changed = False
    for candidate in candidates:
        if _migration_copy_tps_stats(candidate, target_selector):
            changed = True
            break
    return changed


def _migration_remove_duplicated_source_scores(source_selector, target_selector):
    source_selector = str(source_selector or "").strip()
    target_selector = str(target_selector or "").strip()
    if not source_selector or not target_selector:
        return False
    presets_dir = os.path.join(CONTROL_DIR, "benchmarks", "presets")
    source_dir = os.path.join(presets_dir, _selector_token(source_selector))
    target_dir = os.path.join(presets_dir, _selector_token(target_selector))
    if not os.path.isdir(source_dir) or not os.path.isdir(target_dir):
        return False
    compared = 0
    replacements = [
        (target_selector, source_selector),
        (f"presets/{_selector_token(target_selector)}", f"presets/{_selector_token(source_selector)}"),
        (f"/presets/{_selector_token(target_selector)}", f"/presets/{_selector_token(source_selector)}"),
    ]
    for mode in ("quick", "full"):
        source_path = os.path.join(source_dir, f"{mode}-latest.json")
        target_path = os.path.join(target_dir, f"{mode}-latest.json")
        if not os.path.isfile(source_path):
            continue
        if not os.path.isfile(target_path):
            return False
        source_payload = read_json_file(source_path, {})
        target_payload = read_json_file(target_path, {})
        if not source_payload or not target_payload:
            return False
        if _migration_replace_json_strings(target_payload, replacements) != source_payload:
            return False
        compared += 1
    if not compared:
        return False
    if os.path.isdir(source_dir):
        shutil.rmtree(source_dir, ignore_errors=True)
    return True


def _migration_update_existing_row_from_source(row, source_path, backup_dir, rel_path, source_meta, use_old_suffix=False, used_ids=None, old_generation=1):
    if not isinstance(row, dict):
        return {"changed": False, "score_copied": False}
    backup_root = os.path.abspath(str(backup_dir or "").strip())
    rel_path = _normalize_compose_rel_path(rel_path) or os.path.relpath(source_path, backup_root).replace("\\", "/")
    source_meta = dict(source_meta or _migration_source_metadata(source_path, backup_root, rel_path))
    source_selector = str(source_meta.get("selector") or "").strip()
    source_entry = dict(source_meta.get("entry") or {})
    source_status_kind = str(source_meta.get("status_kind") or "migrated").strip() or "migrated"
    target_status_kind = _normalize_status_kind(
        source_meta.get("target_status_kind")
        or ("deprecated" if source_status_kind == "deprecated" else source_status_kind)
    )
    if target_status_kind in {"unknown", "migrated"}:
        target_status_kind = "experimental"
    inventory_origin = str(source_meta.get("inventory_origin") or ("deprecated_backup_registry" if target_status_kind == "deprecated" else "migrated_custom_registry")).strip()
    target_confidence = "migrated" if target_status_kind == "migrated" else "custom"
    if inventory_origin == "migrated_custom_registry":
        target_confidence = "migrated"
    target_gate = ""
    public_selector = _migration_public_selector(source_selector, use_old_suffix=use_old_suffix, old_generation=old_generation)
    source_label = source_selector or rel_path
    old_id = _selector_token(row.get("id") or row.get("selector") or row.get("model_id") or "")
    old_selector = str(row.get("selector") or "").strip()
    target_id = _selector_token(public_selector or old_id or f"migrated-{rel_path}{'-old' if use_old_suffix else ''}")
    used = set(used_ids or set())
    if target_id != old_id and target_id in used:
        target_id = _migration_unique_record_id(target_id, used)
    target_selector = f"custom/{target_id}" if target_id else old_selector
    changed = False
    score_copied = False

    if target_id and target_id != old_id:
        target_path = _copy_migrated_compose_file(source_path, target_id, backup_root)
        row["id"] = target_id
        row["selector"] = target_selector
        row["registry_key"] = target_selector
        row["compose_path"] = target_path
        row["compose_rel_path"] = _normalize_compose_rel_path(os.path.join("custom-models", target_id, "docker-compose.yml"))
        if old_selector and old_selector != target_selector:
            score_result = _migration_relink_score_artifacts(old_selector, target_selector, remove_source=True)
            if not score_result.get("copied"):
                score_result = _migration_relink_score_artifacts(source_selector, target_selector, remove_source=True)
            score_copied = bool(score_result.get("copied"))
            _migration_copy_tps_stats(source_selector or old_selector, target_selector)
        changed = True
    elif not str(row.get("compose_path") or "").strip():
        target_path = _copy_migrated_compose_file(source_path, target_id, backup_root)
        row["compose_path"] = target_path
        row["compose_rel_path"] = _normalize_compose_rel_path(os.path.join("custom-models", target_id, "docker-compose.yml"))
        changed = True

    profile = _read_compose_profile_header(source_path)
    compose_path = str(row.get("compose_path") or source_path).strip()
    runtime_meta = _read_compose_runtime_metadata(compose_path)
    hardware_meta = _read_compose_hardware_metadata(compose_path)
    nvlink_mode = _variant_nvlink_mode(source_entry, hardware_meta, "dual" if "/dual/" in rel_path else "")
    if nvlink_mode:
        runtime_meta["nvlink_mode"] = nvlink_mode
        runtime_meta["requires_nvlink"] = nvlink_mode == "required"
    else:
        runtime_meta.pop("nvlink_mode", None)
        runtime_meta.pop("requires_nvlink", None)
    caveat_suffix = " with an -OLD suffix because the updated upstream checkout contains a different preset at the same selector/path" if use_old_suffix else ""
    updates = {
        "slug": public_selector or row.get("slug") or rel_path,
        "source_selector": source_selector,
        "replacement_selector": str(source_meta.get("replacement_selector") or "").strip(),
        "source_compose_rel_path": rel_path,
        "source_compose_sha256": _migration_file_sha256(source_path),
        "source_status_kind": source_status_kind,
        "display_name": public_selector or row.get("display_name") or source_label,
        "profile_like": _migration_strip_old_suffix(source_selector) or source_selector,
        "status_kind": target_status_kind,
        "inventory_origin": inventory_origin,
        "compat_status": target_status_kind,
        "confidence_tier": target_confidence,
        "gate_terminal": target_gate,
        "gate_reason": f"Preserved pre-migration preset {source_label} from older Club-3090 checkout path {rel_path}{caveat_suffix}.",
        "compat_reason_summary": f"Pre-migration preset preserved as {target_selector} for historical comparison.",
        "requires_nvlink": bool(nvlink_mode == "required"),
        "nvlink_mode": nvlink_mode,
        "compose_meta": runtime_meta,
    }
    if source_entry:
        updates.update({
            "profile_model_id": str(source_entry.get("model") or row.get("profile_model_id") or "").strip(),
            "profile_engine_id": str(source_entry.get("engine") or row.get("profile_engine_id") or "").strip(),
            "profile_workload_id": str(source_entry.get("workload") or row.get("profile_workload_id") or "").strip(),
            "profile_drafter_id": str(source_entry.get("drafter") or row.get("profile_drafter_id") or profile.get("drafter") or "").strip(),
        })
    if not str(row.get("best_for") or "").strip():
        updates["best_for"] = str(profile.get("best_for") or f"Migrated custom preset from {source_label}.").strip()
    if not str(row.get("quality_summary") or "").strip():
        updates["quality_summary"] = str(profile.get("quality") or "").strip()
    if target_status_kind == "deprecated" or not str(row.get("caveats") or "").strip():
        updates["caveats"] = str(profile.get("caveats") or f"Migrated preset{caveat_suffix}; original status was {source_status_kind}.").strip()
    for key, value in updates.items():
        if row.get(key) != value:
            row[key] = value
            changed = True
    return {"changed": changed, "score_copied": score_copied}


def _migration_record_from_compose(source_path, backup_dir, existing_ids=None, use_old_suffix=False, rel_path_override="", source_meta_override=None, old_generation=1):
    backup_root = os.path.abspath(str(backup_dir or "").strip())
    rel_path = _normalize_compose_rel_path(rel_path_override) or os.path.relpath(source_path, backup_root).replace("\\", "/")
    used_ids = set(existing_ids or set())
    source_meta = dict(source_meta_override or _migration_source_metadata(source_path, backup_root, rel_path))
    source_selector = str(source_meta.get("selector") or "").strip()
    source_entry = dict(source_meta.get("entry") or {})
    source_status_kind = str(source_meta.get("status_kind") or "migrated").strip() or "migrated"
    target_status_kind = _normalize_status_kind(
        source_meta.get("target_status_kind")
        or ("deprecated" if source_status_kind == "deprecated" else source_status_kind)
    )
    if target_status_kind in {"unknown", "migrated"}:
        target_status_kind = "experimental"
    inventory_origin = str(source_meta.get("inventory_origin") or ("deprecated_backup_registry" if target_status_kind == "deprecated" else "migrated_custom_registry")).strip()
    target_confidence = "migrated" if target_status_kind == "migrated" else "custom"
    if inventory_origin == "migrated_custom_registry":
        target_confidence = "migrated"
    target_gate = ""
    public_selector = _migration_public_selector(source_selector, use_old_suffix=use_old_suffix, old_generation=old_generation)
    record_base = public_selector or f"migrated-{rel_path}{'-old' if use_old_suffix else ''}"
    record_id = _migration_unique_record_id(record_base, used_ids)
    selector = f"custom/{record_id}"
    target_path = _copy_migrated_compose_file(source_path, record_id, backup_root)
    profile = _read_compose_profile_header(source_path)
    runtime_meta = _read_compose_runtime_metadata(target_path)
    hardware_meta = _read_compose_hardware_metadata(target_path)
    nvlink_mode = _variant_nvlink_mode(source_entry, hardware_meta, "dual" if "/dual/" in rel_path else "")
    if nvlink_mode:
        runtime_meta["nvlink_mode"] = nvlink_mode
        runtime_meta["requires_nvlink"] = nvlink_mode == "required"
    parts = rel_path.split("/")
    source_model_id = parts[1] if len(parts) >= 2 and parts[0] == "models" else ""
    engine_hint = rel_path.lower()
    engine_profile_id = str(source_entry.get("engine") or "").strip() or ("llama-cpp-local" if ("/llama-cpp/" in engine_hint or "/ik-llama/" in engine_hint) else "vllm-nightly-clean")
    display_leaf = os.path.splitext(os.path.basename(source_path))[0]
    display_name = str(profile.get("name") or profile.get("profile") or display_leaf or record_id).strip()
    public_name = public_selector or f"Migrated {display_name}{' OLD' if use_old_suffix else ''}"
    caveat_suffix = " with an -OLD suffix because the updated upstream checkout contains a different preset at the same selector/path" if use_old_suffix else ""
    source_label = source_selector or rel_path
    return {
        "id": record_id,
        "selector": selector,
        "slug": public_selector or rel_path,
        "source_selector": source_selector,
        "replacement_selector": str(source_meta.get("replacement_selector") or "").strip(),
        "source_compose_rel_path": rel_path,
        "source_compose_sha256": _migration_file_sha256(source_path),
        "source_status_kind": source_status_kind,
        "model_id": str(source_entry.get("model") or source_model_id or f"custom-{record_id}").strip(),
        "model_display_name": _format_model_display_name(source_model_id) if source_model_id else "",
        "display_name": public_name,
        "custom_preset": bool(source_model_id),
        "profile_like": _migration_strip_old_suffix(source_selector) or source_selector,
        "compose_path": target_path,
        "compose_rel_path": _normalize_compose_rel_path(os.path.join("custom-models", record_id, "docker-compose.yml")),
        "status_kind": target_status_kind,
        "inventory_origin": inventory_origin,
        "registry_key": selector,
        "profile_model_id": str(source_entry.get("model") or source_model_id or "").strip(),
        "profile_engine_id": engine_profile_id,
        "profile_workload_id": str(source_entry.get("workload") or "").strip(),
        "profile_drafter_id": str(source_entry.get("drafter") or profile.get("drafter") or "").strip(),
        "requires_nvlink": bool(nvlink_mode == "required"),
        "nvlink_mode": nvlink_mode,
        "confidence_tier": target_confidence,
        "gate_terminal": target_gate,
        "gate_reason": f"Preserved pre-migration preset {source_label} from older Club-3090 checkout path {rel_path}{caveat_suffix}.",
        "compat_status": target_status_kind,
        "compat_reason_summary": f"Pre-migration preset preserved as {selector} for historical comparison.",
        "best_for": str(profile.get("best_for") or f"Migrated custom preset from {source_label}.").strip(),
        "quality_summary": str(profile.get("quality") or "").strip(),
        "caveats": str(profile.get("caveats") or f"Migrated preset{caveat_suffix}; original status was {source_status_kind}.").strip(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host_model_dir": "",
        "install_command": "",
        "install_reason": "",
        "compose_meta": runtime_meta,
    }


def migrate_missing_custom_presets_from_backup(backup_dir):
    backup_root = os.path.abspath(str(backup_dir or "").strip())
    if not backup_root or not os.path.isdir(backup_root):
        return {"ok": True, "backup_dir": backup_root, "imported": 0, "relinked": 0, "skipped": 0, "records": []}
    rows = read_custom_model_registry()
    changed = False
    relinked = 0
    normalized = normalize_custom_model_compose_volume_sources(backup_root)
    if normalized:
        rows = read_custom_model_registry()
        changed = True
    used_ids = {_selector_token(row.get("id") or "") for row in rows if _selector_token(row.get("id") or "")}
    for row in rows:
        record_id = _selector_token(row.get("id") or row.get("selector") or row.get("model_id") or "")
        current_path = os.path.normpath(str(row.get("compose_path") or "").strip())
        current_abs = os.path.abspath(current_path) if current_path else ""
        if current_abs and os.path.exists(current_abs) and _path_is_within(CUSTOM_MODELS_DIR, current_abs):
            continue
        candidates = []
        rel = _normalize_compose_rel_path(row.get("compose_rel_path"))
        if rel:
            candidates.append(os.path.join(backup_root, rel.replace("/", os.sep)))
        if record_id:
            candidates.append(os.path.join(backup_root, "custom-models", record_id, "docker-compose.yml"))
        if current_abs and _path_is_within(backup_root, current_abs):
            candidates.append(current_abs)
        source = next((candidate for candidate in candidates if candidate and os.path.exists(candidate) and _looks_like_runtime_compose_file(candidate)), "")
        if not source:
            continue
        target_path = _copy_migrated_compose_file(source, record_id, backup_root)
        row["compose_path"] = target_path
        row["compose_rel_path"] = _normalize_compose_rel_path(os.path.join("custom-models", record_id, "docker-compose.yml"))
        row["inventory_origin"] = str(row.get("inventory_origin") or "migrated_custom_registry").strip()
        row["compose_meta"] = _read_compose_runtime_metadata(target_path)
        changed = True
        relinked += 1

    # The control service can survive the checkout replacement during --migrate.
    # Never classify collisions using a registry cached from the old checkout.
    setattr(_load_upstream_compose_registry, "_cache", None)
    current_rels = _current_compose_rel_paths()
    current_registry = _load_upstream_compose_registry()
    current_selector_by_rel = {}
    for selector, entry in current_registry.items():
        compose_rel = _normalize_compose_rel_path((entry or {}).get("compose_path"))
        if compose_rel and not _compose_rel_path_is_archived(compose_rel):
            current_selector_by_rel.setdefault(compose_rel, str(selector or "").strip())
    backup_registry = _load_compose_registry_from_root(backup_root)
    imported = []
    score_relinked = 0
    skipped = 0
    source_descriptors = []
    for source in _migration_compose_candidates(backup_root):
        rel_path = _normalize_compose_rel_path(os.path.relpath(source, backup_root).replace("\\", "/"))
        registry_matches = [
            (str(selector or "").strip(), dict(entry or {}))
            for selector, entry in backup_registry.items()
            if _normalize_compose_rel_path((entry or {}).get("compose_path")) == rel_path
        ]
        if registry_matches:
            for selector, entry in registry_matches:
                status_kind = _normalize_status_kind(entry.get("status") or "")
                source_descriptors.append({
                    "path": source,
                    "rel_path": rel_path,
                    "source_meta": {
                        "selector": selector,
                        "entry": entry,
                        "status_kind": status_kind if status_kind != "unknown" else "experimental",
                        "rel_path": rel_path,
                    },
                })
        else:
            source_descriptors.append({"path": source, "rel_path": rel_path, "source_meta": None})
    source_descriptors.extend(_migration_deprecated_registry_sources(backup_root, current_registry))
    source_descriptors.extend(_migration_git_deleted_nvlink_sources(backup_root))
    for descriptor in source_descriptors:
        source = descriptor.get("path")
        rel = _normalize_compose_rel_path(descriptor.get("rel_path"))
        force_import = bool(descriptor.get("force_import"))
        source_meta = dict(descriptor.get("source_meta") or _migration_source_metadata(source, backup_root, rel))
        source_selector = str(source_meta.get("selector") or "").strip()
        current_same = rel in current_rels and _current_compose_matches_source(rel, source)
        source_base = _migration_strip_old_suffix(source_selector)
        current_live_selector, current_selector_entry = _migration_current_selector_entry(current_registry, source_selector)
        current_selector_live = bool(current_selector_entry and not _compose_rel_path_is_archived(current_selector_entry.get("compose_path")))
        use_old_suffix = (rel in current_rels and not current_same) or current_selector_live
        replacement_selector = str(current_selector_by_rel.get(rel) or "").strip() if use_old_suffix else ""
        if use_old_suffix:
            equivalent_selector = current_live_selector or replacement_selector
            equivalent_entry = dict(current_selector_entry or {})
            equivalent_rel = _normalize_compose_rel_path((equivalent_entry or {}).get("compose_path"))
            if not equivalent_rel and replacement_selector:
                equivalent_entry = dict(current_registry.get(replacement_selector) or {})
                equivalent_rel = _normalize_compose_rel_path((equivalent_entry or {}).get("compose_path"))
                equivalent_selector = replacement_selector
            equivalent_path = os.path.join(os.path.abspath(CLUB3090_DIR), equivalent_rel.replace("/", os.sep)) if equivalent_rel else ""
            if equivalent_selector and equivalent_path and _migration_compose_runtime_equivalent(
                source,
                source_meta.get("entry") or {},
                source_selector,
                rel,
                equivalent_path,
                equivalent_entry,
                equivalent_selector,
                equivalent_rel,
            ):
                score_result = _migration_relink_score_artifacts(source_selector, equivalent_selector, remove_source=False, fallback_only=True)
                if score_result.get("copied"):
                    score_relinked += 1
                _migration_copy_tps_stats(source_selector, equivalent_selector)
                skipped += 1
                continue
        if replacement_selector and replacement_selector != source_base:
            source_meta["replacement_selector"] = replacement_selector
        else:
            source_meta.pop("replacement_selector", None)
        if current_same and current_selector_live and not force_import:
            skipped += 1
            continue
        matching_rows = [
            row for row in rows
            if _migration_existing_row_matches(row, rel, source_selector)
        ]
        selector_matching_rows = [
            row for row in matching_rows
            if not source_selector or _migration_existing_row_matches(row, "", source_selector)
        ]
        rel_only_matching_rows = [row for row in matching_rows if row not in selector_matching_rows]
        matching_same_source_row = next(
            (row for row in selector_matching_rows if _migration_row_compose_matches_source(row, source)),
            None,
        )
        if not matching_same_source_row and not source_selector:
            matching_same_source_row = next(
                (row for row in rel_only_matching_rows if _migration_row_compose_matches_source(row, source)),
                None,
            )
        matching_row = matching_same_source_row or (selector_matching_rows[0] if selector_matching_rows else None)
        if not matching_row and not source_selector and rel_only_matching_rows:
            matching_row = rel_only_matching_rows[0]
        if matching_row:
            desired_public_selector = _migration_public_selector(source_selector, use_old_suffix=use_old_suffix)
            current_public_selector = str(matching_row.get("display_name") or matching_row.get("slug") or "").strip()
            migrated_row = str(matching_row.get("inventory_origin") or "").strip() in {
                "migrated_custom_registry",
                "deprecated_backup_registry",
            }
            historical_collision_rows = [
                row for row in matching_rows
                if str((row or {}).get("inventory_origin") or "").strip() in {
                    "migrated_custom_registry",
                    "deprecated_backup_registry",
                }
                and _migration_old_generation_for_row(row, source_selector) > 0
            ]
            if use_old_suffix and historical_collision_rows and not matching_same_source_row:
                next_old_generation = _migration_next_old_generation(rows, source_selector)
                record = _migration_record_from_compose(
                    source,
                    backup_root,
                    used_ids,
                    use_old_suffix=use_old_suffix,
                    rel_path_override=rel,
                    source_meta_override=source_meta,
                    old_generation=next_old_generation,
                )
                used_ids.add(record["id"])
                rows.append(record)
                imported.append(record)
                score_result = _migration_relink_score_artifacts(
                    record.get("source_selector"),
                    record.get("selector"),
                    remove_source=True,
                )
                if score_result.get("copied"):
                    score_relinked += 1
                _migration_copy_row_tps_stats(record)
                changed = True
                continue
            needs_suffix_repair = migrated_row and desired_public_selector and current_public_selector != desired_public_selector
            needs_provenance_repair = (
                migrated_row
                and (
                    str(matching_row.get("status_kind") or "").strip() == "migrated"
                    or str(matching_row.get("category") or "").strip() == "migrated"
                    or str(matching_row.get("gate_terminal") or "").strip() == "migrated"
                )
            )
            needs_replacement_repair = (
                migrated_row
                and str(matching_row.get("replacement_selector") or "").strip()
                != str(source_meta.get("replacement_selector") or "").strip()
            )
            if force_import or needs_suffix_repair or needs_provenance_repair or needs_replacement_repair:
                existing_old_generation = _migration_old_generation_for_row(matching_row, source_selector) if use_old_suffix else 1
                update_result = _migration_update_existing_row_from_source(
                    matching_row,
                    source,
                    backup_root,
                    rel,
                    source_meta,
                    use_old_suffix=use_old_suffix,
                    used_ids=used_ids,
                    old_generation=existing_old_generation,
                )
                if update_result.get("changed"):
                    changed = True
                    updated_id = _selector_token(matching_row.get("id") or "")
                    if updated_id:
                        used_ids.add(updated_id)
                if update_result.get("score_copied"):
                    score_relinked += 1
            if _migration_remove_duplicated_source_scores(source_selector, matching_row.get("selector")):
                score_relinked += 1
            if _migration_backfill_existing_row_scores(matching_row, source_meta):
                score_relinked += 1
            _migration_copy_row_tps_stats(matching_row)
            skipped += 1
            continue
        record = _migration_record_from_compose(source, backup_root, used_ids, use_old_suffix=use_old_suffix, rel_path_override=rel, source_meta_override=source_meta)
        used_ids.add(record["id"])
        rows.append(record)
        imported.append(record)
        score_result = _migration_relink_score_artifacts(
            record.get("source_selector"),
            record.get("selector"),
            remove_source=True,
        )
        if score_result.get("copied"):
            score_relinked += 1
        _migration_copy_row_tps_stats(record)
        changed = True

    for row in rows:
        if _migration_backfill_existing_row_scores(row, {}):
            score_relinked += 1

    rows, prune_result = _migration_prune_runtime_equivalent_old_rows(rows, current_registry)
    pruned_old = prune_result.get("pruned") or []
    if pruned_old:
        changed = True
        score_relinked += int(prune_result.get("score_relinked") or 0)

    if changed:
        write_custom_model_registry(rows)
    inventory = rebuild_runtime_inventory() if changed else load_runtime_inventory(force=False, rebuild_if_missing=True)
    rows, hydrated_prune_result = _migration_prune_runtime_equivalent_hydrated_old_rows(rows, inventory)
    hydrated_pruned_old = hydrated_prune_result.get("pruned") or []
    if hydrated_pruned_old:
        write_custom_model_registry(rows)
        inventory = rebuild_runtime_inventory()
        score_relinked += int(hydrated_prune_result.get("score_relinked") or 0)
        pruned_old.extend(hydrated_pruned_old)
    equivalent_score_relinked = _migration_backfill_equivalent_runtime_scores(inventory)
    if equivalent_score_relinked:
        score_relinked += equivalent_score_relinked
    log_control(f"MIGRATE custom presets backup={backup_root} imported={len(imported)} pruned_old={len(pruned_old)} relinked={relinked} normalized={normalized} score_relinked={score_relinked} skipped={skipped}")
    return {
        "ok": True,
        "backup_dir": backup_root,
        "imported": len(imported),
        "relinked": relinked,
        "normalized": normalized,
        "score_relinked": score_relinked,
        "skipped": skipped,
        "pruned_old": len(pruned_old),
        "records": [{key: value for key, value in row.items() if key != "compose_text"} for row in imported],
        "runtime_inventory": inventory,
    }


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
        result = {}
    if not any(str(result.get(key) or "").strip() for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_TOKEN")):
        token_candidates = []
        hf_home = str(os.environ.get("HF_HOME") or "").strip()
        home = str(os.environ.get("HOME") or "").strip()
        if hf_home:
            token_candidates.append(os.path.join(hf_home, "token"))
        if home:
            token_candidates.extend([
                os.path.join(home, ".cache", "huggingface", "token"),
                os.path.join(home, ".huggingface", "token"),
            ])
        token_candidates.extend([
            "/root/.cache/huggingface/token",
            "/root/.huggingface/token",
            *glob.glob("/home/*/.cache/huggingface/token"),
            *glob.glob("/home/*/.huggingface/token"),
        ])
        for token_path in token_candidates:
            try:
                with open(token_path, "r", encoding="utf-8", errors="replace") as token_file:
                    token = token_file.read(4096).strip()
            except Exception:
                continue
            if token.startswith("hf_"):
                result["HF_TOKEN"] = token
                break
    return result


def _repo_subprocess_env():
    env = os.environ.copy()
    for key, value in _load_repo_env_map().items():
        if key:
            env[str(key)] = str(value)
    if str(os.environ.get("CLUB3090_RESTART") or "").strip():
        env["CLUB3090_RESTART"] = str(os.environ.get("CLUB3090_RESTART") or "").strip()
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


def _safetensors_shards_complete(path):
    try:
        if not os.path.isdir(path):
            return None
        groups = {}
        pattern = re.compile(r"^(?P<prefix>.+)-(?P<index>\d+)-of-(?P<total>\d+)\.safetensors$", re.I)
        for root, _dirs, files in os.walk(path):
            for name in files:
                match = pattern.match(str(name or ""))
                if not match:
                    continue
                total = int(match.group("total"))
                index = int(match.group("index"))
                key = (os.path.normpath(root), match.group("prefix"), total)
                groups.setdefault(key, set()).add(index)
        if not groups:
            return None
        for (_root, _prefix, total), indices in groups.items():
            if indices != set(range(1, total + 1)):
                return False
        return True
    except Exception:
        return None


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
        env["CUDA_VISIBLE_DEVICES"] = chosen
        env["NVIDIA_VISIBLE_DEVICES"] = chosen
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
    if host_visible_devices:
        env["ESTATE_GPUS"] = host_visible_devices
        env["CUDA_VISIBLE_DEVICES"] = host_visible_devices
        env["NVIDIA_VISIBLE_DEVICES"] = host_visible_devices
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


def _resolve_shell_value_with_env(raw, env_map):
    text = str(raw or "").strip().strip('"').strip("'")
    if not text:
        return ""
    env = {
        str(key or "").strip(): str(value or "").strip()
        for key, value in dict(env_map or {}).items()
        if str(key or "").strip() and str(value or "").strip()
    }
    for key, value in sorted(env.items(), key=lambda item: len(item[0]), reverse=True):
        escaped = re.escape(key)
        text = re.sub(rf"\$\{{{escaped}:-(?:[^{{}}]|\$\{{[^{{}}]*\}})*\}}", value, text)
        text = re.sub(rf"\$\{{{escaped}\}}", value, text)
    previous = None
    while previous != text:
        previous = text
        text = _extract_shell_default_value(text)
    return text.strip()


def _apply_effective_service_image(variant):
    row = variant if isinstance(variant, dict) else {}
    raw_image = str(row.get("service_image") or "").strip()
    if not raw_image:
        return row
    try:
        launch_env = resolve_variant_launch_env(row)
    except Exception:
        launch_env = {}
    effective = _resolve_shell_value_with_env(raw_image, launch_env)
    override_image = str(launch_env.get("VLLM_IMAGE") or "").strip()
    if (
        override_image
        and effective == raw_image
        and (
            "VLLM_NIGHTLY_SHA" in raw_image
            or "${VLLM_IMAGE" in raw_image
            or raw_image.startswith("vllm/vllm-openai:nightly-")
        )
    ):
        effective = override_image
    if effective and effective != raw_image:
        row["service_image_raw"] = raw_image
        row["service_image"] = effective
    return row


def _strip_yaml_inline_comment(raw):
    text = str(raw or "").strip()
    if not text:
        return ""
    quote = ""
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {"'", '"'}:
            if not quote:
                quote = char
            elif quote == char:
                quote = ""
            continue
        if char == "#" and not quote and (index == 0 or text[index - 1].isspace()):
            return text[:index].rstrip()
    return text


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
    status_text = str(status_kind or "").strip().lower()
    if status_text == "migrated":
        return "migrated"
    if status_text == "deprecated":
        return "deprecated"
    if topology_text.startswith("single"):
        return "single"
    if topology_text.startswith("multi"):
        return "multi"
    if status_text in {"experimental", "incubating", "preview", "upstream_gated", "tombstoned", "blocked"}:
        return "experimental"
    if topology_text.startswith("dual"):
        return "dual"
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


def _variant_nvlink_mode(registry_entry=None, hardware_meta=None, topology=""):
    registry = dict(registry_entry or {})
    hardware = dict(hardware_meta or {})
    raw = str(registry.get("nvlink_mode") or hardware.get("nvlink_mode") or "").strip().lower()
    if registry.get("requires_nvlink") or hardware.get("requires_nvlink") or raw in {"required", "requires", "require", "bridge", "force_on", "on", "yes", "true"}:
        return "required"
    return ""


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
        "requires_nvlink": False,
    }
    key_map = {
        "requires-min-vram-gb": "requires_min_vram_gb",
        "requires-min-gpu-count": "requires_min_gpu_count",
        "tensor-parallel": "tensor_parallel",
        "requires-sm": "requires_sm",
        "engine-profile": "engine_profile",
        "requires-nvlink": "requires_nvlink",
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
                match = re.match(r"^#\s*([A-Za-z0-9_-]+)\s*:\s*(.+?)\s*$", line)
                if not match:
                    continue
                target_key = key_map.get(str(match.group(1) or "").strip().lower())
                if not target_key:
                    continue
                value = str(match.group(2) or "").strip()
                if target_key in {"requires_min_vram_gb", "requires_min_gpu_count", "tensor_parallel"}:
                    fields[target_key] = int(_extract_default_number(value) or 0)
                elif target_key == "requires_nvlink":
                    fields[target_key] = value.lower() not in {"", "0", "no", "none", "false", "off"}
                elif target_key == "nvlink_mode":
                    lowered = value.lower()
                    if any(token in lowered for token in ("required", "requires", "bridge", "force_on")) or lowered in {"on", "yes", "true"}:
                        fields[target_key] = "required"
                    elif lowered in {"no", "none", "false", "off", "auto", "automatic", "auto-detected", "auto detected", "capable", "optional"}:
                        fields[target_key] = ""
                    else:
                        fields[target_key] = lowered
                else:
                    fields[target_key] = value
    except Exception:
        return dict(fields)
    if not fields.get("nvlink_mode"):
        rel = str(path or "").replace("\\", "/").lower()
        if "/nvlink" in rel or rel.endswith("nvlink.yml") or "nvlink-" in rel:
            fields["nvlink_mode"] = "required"
            fields["requires_nvlink"] = True
    return dict(fields)


def _read_compose_runtime_metadata(path):
    service_name = ""
    container_name = ""
    service_image = ""
    default_port = None
    served_model_name = ""
    max_model_len = None
    model_path = ""
    mmproj_path = ""
    speculative_json = ""
    draft_model_path = ""
    tensor_parallel = None
    command_items = []
    environment_items = []
    volume_items = []
    in_command = False
    in_ports = False
    in_environment = False
    in_volumes = False
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
                    in_environment = False
                    in_volumes = False
                    command_block_mode = ""
                if not service_image:
                    match = re.match(r"^image:\s*(.+)$", stripped)
                    if match:
                        service_image = _extract_shell_default_value(_strip_yaml_inline_comment(match.group(1)))
                        continue
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
                if stripped == "environment:":
                    in_environment = True
                    current_indent = indent
                    continue
                if stripped == "volumes:":
                    in_volumes = True
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
                if in_environment and indent > current_indent:
                    item = stripped[2:].strip() if stripped.startswith("- ") else stripped
                    if item and not item.startswith("#"):
                        environment_items.append(_extract_shell_default_value(item))
                    continue
                if in_volumes and indent > current_indent and stripped.startswith("- "):
                    item = stripped[2:].strip()
                    if item:
                        volume_items.append(_extract_shell_default_value(item))
                    continue
                if not container_name:
                    match = re.match(r"^container_name:\s*(.+)$", stripped)
                    if match:
                        container_name = _extract_shell_default_value(match.group(1))
                        continue
    except Exception:
        return {}
    for idx, item in enumerate(command_items):
        if (
            item == "serve"
            and idx > 0
            and os.path.basename(str(command_items[idx - 1] or "").strip()) == "vllm"
            and idx + 1 < len(command_items)
            and not str(command_items[idx + 1] or "").strip().startswith("-")
        ):
            model_path = _extract_shell_default_value(command_items[idx + 1])
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
            served_model_name = _extract_shell_default_value(command_items[idx + 1])
        elif item.startswith("--served-model-name="):
            served_model_name = _extract_shell_default_value(item.split("=", 1)[1])
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
        if item == "--tensor-parallel-size" and idx + 1 < len(command_items):
            tensor_parallel = _extract_default_number(command_items[idx + 1], minimum_digits=1)
        elif item.startswith("--tensor-parallel-size="):
            tensor_parallel = _extract_default_number(item.split("=", 1)[1], minimum_digits=1)
        if item in {"--tp", "--tp-size"} and idx + 1 < len(command_items):
            tensor_parallel = _extract_default_number(command_items[idx + 1], minimum_digits=1)
        elif item.startswith("--tp=") or item.startswith("--tp-size="):
            tensor_parallel = _extract_default_number(item.split("=", 1)[1], minimum_digits=1)
    if not served_model_name and model_path:
        lowered_items = [str(item or "").strip().lower() for item in command_items]
        if "vllm" in {os.path.basename(item) for item in lowered_items} and "serve" in lowered_items:
            served_model_name = model_path
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
        "service_image": service_image,
        "compose_environment": environment_items,
        "compose_volumes": volume_items,
        "compose_volume_targets": _compose_volume_target_sequence(volume_items).splitlines(),
        "default_port": default_port,
        "served_model_name": served_model_name,
        "max_model_len": max_model_len,
        "model_path": model_path,
        "mmproj_path": mmproj_path,
        "speculative_method": speculative_method,
        "drafted_tokens": drafted_tokens,
        "draft_model_path": draft_model_path,
        "tp": int(tensor_parallel or 0),
        "tensor_parallel": int(tensor_parallel or 0),
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


def _read_compose_command_summary(path, limit=2400):
    text = _read_compose_command_text(path)
    lines = [
        str(line or "").strip()
        for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if str(line or "").strip()
    ]
    summary = "\n".join(lines).strip()
    limit = max(200, int(limit or 2400))
    return summary if len(summary) <= limit else summary[:limit].rstrip() + "\n..."


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
        "MAX_NUM_BATCHED_TOKENS": "Max Batched Tokens",
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
    for _ in range(3):
        shell_match = re.search(r"\$\{[A-Z][A-Z0-9_]*(?::-|-)([^{}$]+)\}?", text)
        if not shell_match:
            break
        text = str(shell_match.group(1) or "").strip()
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


def _read_command_option_launch_defaults(command_text):
    option_keys = {
        "--max-model-len": "MAX_MODEL_LEN",
        "--ctx-size": "CTX_SIZE",
        "-c": "CTX_SIZE",
        "--gpu-memory-utilization": "GPU_MEMORY_UTILIZATION",
        "--max-num-seqs": "MAX_NUM_SEQS",
        "--max-num-batched-tokens": "MAX_NUM_BATCHED_TOKENS",
        "--kv-cache-dtype": "KV_CACHE_DTYPE",
        "--served-model-name": "MODEL_NAME",
    }
    try:
        tokens = shlex.split(str(command_text or "").replace("\r", " ").replace("\n", " "))
    except Exception:
        tokens = str(command_text or "").replace("\r", " ").replace("\n", " ").split()
    defaults = {}
    for idx, token in enumerate(tokens[:-1]):
        key = option_keys.get(str(token or "").strip())
        if not key or key in defaults:
            continue
        raw_value = str(tokens[idx + 1] or "").strip()
        if not raw_value or raw_value.startswith("--"):
            continue
        defaults[key] = _sanitize_launch_setting_default(_extract_shell_default_value(raw_value))
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
        "MAX_NUM_BATCHED_TOKENS": 31,
        "GPU_MEMORY_UTILIZATION": 32,
        "KV_CACHE_DTYPE": 33,
        "KV_TYPE": 34,
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
    fallback_descriptions = {
        "MAX_MODEL_LEN": "Controls the vLLM context window in tokens. Higher values preserve longer conversations but reserve more KV cache and can reduce concurrency.",
        "CTX_SIZE": "Controls the llama.cpp context window in tokens. Higher values preserve longer conversations but increase KV memory pressure.",
        "GPU_MEMORY_UTILIZATION": "Sets the fraction of GPU memory vLLM may reserve for weights, KV cache, and runtime buffers.",
        "MAX_NUM_SEQS": "Caps concurrent vLLM sequences. Higher values improve parallel serving but increase memory pressure.",
        "MAX_NUM_BATCHED_TOKENS": "Caps total batched prompt tokens vLLM may schedule at once. Larger values can improve prompt throughput but increase activation memory pressure.",
        "KV_CACHE_DTYPE": "Selects the vLLM KV cache format. Smaller formats save VRAM while higher precision can improve long-context reliability.",
        "KV_TYPE": "Selects the llama.cpp KV cache quantization. Smaller formats save VRAM and extend context at the cost of precision.",
        "BATCH_SIZE": "Controls llama.cpp logical batch size. Larger values can improve prompt throughput when memory headroom allows it.",
        "UBATCH_SIZE": "Controls llama.cpp micro-batch size. It is the main activation-memory lever for long context stability.",
        "NP": "Controls llama.cpp parallel slots. Extra slots improve serving concurrency but split throughput and may disable speculative decoding.",
        "MTP_DRAFT_N_MAX": "Caps llama.cpp MTP draft tokens. Higher values can improve speed when acceptance is high but may hurt stability.",
        "MTP_N_MAX": "Caps speculative draft tokens. Higher values can improve speed when acceptance is high but may hurt stability.",
        "DRAFT_P_MIN": "Sets the minimum draft acceptance probability for speculative decoding.",
        "MTP_P_MIN": "Sets the minimum MTP acceptance probability for speculative decoding.",
        "REASONING": "Controls whether the model emits hidden reasoning when the engine supports a reasoning switch.",
        "REASONING_FORMAT": "Selects the reasoning parser or formatting mode used by the engine.",
        "TEMPERATURE": "Controls sampling randomness. Lower values are more deterministic; higher values are more varied.",
        "TEMP": "Controls sampling randomness. Lower values are more deterministic; higher values are more varied.",
        "TOP_P": "Limits sampling to the smallest token set whose cumulative probability reaches this value.",
        "TOP_K": "Limits sampling to the top K candidate tokens.",
        "MIN_P": "Filters very low probability tokens relative to the most likely token.",
        "REPEAT_PENALTY": "Adjusts repetition suppression for llama.cpp style engines.",
        "REPETITION_PENALTY": "Adjusts repetition suppression for vLLM style engines.",
        "MODEL_NAME": "Sets the served OpenAI model name exposed by the runtime endpoint.",
        "VLLM_ENFORCE_EAGER": "Disables CUDA graph capture for vLLM when graph memory or stability is a problem.",
        "ENABLE_THINKING": "Enables template-level thinking controls when the backend supports them.",
        "PRESERVE_THINKING": "Preserves thinking text in responses when the backend supports it.",
    }
    try:
        command_defaults = _read_command_option_launch_defaults(_read_compose_command_text(path))
        env_defaults = {**command_defaults, **env_defaults}
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
    for key, default_value in env_defaults.items():
        clean_key = str(key or "").strip().upper()
        if not clean_key or clean_key in settings or _launch_setting_ignored(clean_key):
            continue
        if clean_key not in fallback_descriptions:
            continue
        settings[clean_key] = {
            "name": clean_key,
            "label": _launch_setting_label(clean_key),
            "type": _launch_setting_type(clean_key, default_value),
            "default": default_value,
            "description": fallback_descriptions.get(clean_key, ""),
        }
    rows = sorted(settings.values(), key=lambda row: (_launch_setting_sort_rank(row.get("name")), row.get("label") or row.get("name") or ""))
    return rows


def _apply_builtin_launch_setting_defaults(variant):
    entry = dict(variant or {})
    overrides = preset_builtin_launch_env_overrides(entry)
    if not overrides:
        return entry
    launch_settings = [dict(row) for row in (entry.get("launch_settings") or []) if isinstance(row, dict)]
    settings_by_name = {
        str(row.get("name") or "").strip().upper(): row
        for row in launch_settings
        if str(row.get("name") or "").strip()
    }
    for key, value in overrides.items():
        setting = settings_by_name.get(str(key or "").strip().upper())
        if setting is not None:
            setting["default"] = str(value)
            setting["type"] = _launch_setting_type(key, value)
    entry["launch_settings"] = launch_settings
    max_context = overrides.get("CTX_SIZE") or overrides.get("MAX_MODEL_LEN")
    if max_context:
        try:
            entry["max_model_len"] = int(max_context)
        except Exception:
            pass
    if "GPU_MEMORY_UTILIZATION" in overrides:
        try:
            entry["mem_util"] = float(overrides["GPU_MEMORY_UTILIZATION"])
        except Exception:
            pass
    if "MAX_NUM_SEQS" in overrides:
        try:
            entry["max_num_seqs"] = int(overrides["MAX_NUM_SEQS"])
        except Exception:
            pass
    return entry


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


def _known_hf_file_download_command(model_dir_root, repo_id, rel_path):
    rel = str(rel_path or "").replace("\\", "/").strip().strip("/")
    repo = str(repo_id or "").strip()
    if not rel or not repo:
        return ""
    target_dir = os.path.join(model_dir_root, os.path.dirname(rel).replace("/", os.sep))
    filename = os.path.basename(rel)
    return f'hf download {repo} {shlex.quote(filename)} --local-dir "{target_dir}"'


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
    shard_state = _safetensors_shards_complete(text)
    if shard_state is False:
        return False
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
    if not draft_recipe and draft_fallback_subdir:
        draft_download = _drafter_download_meta(model_profiles, drafter_id)
        draft_repo = str(draft_download.get("hf_repo") or "").strip()
        if draft_repo:
            draft_recipe = {
                "WEIGHT_KEY": f"{model_id}:{drafter_id or draft_fallback_subdir}",
                "WEIGHT_VARIANT": drafter_id or "draft",
                "WEIGHT_REPO": draft_repo,
                "WEIGHT_SUBDIR": draft_fallback_subdir,
                "WEIGHT_FILES": "",
                "WEIGHT_KIND": "draft",
                "WEIGHT_VERIFY_GLOB": "*.safetensors",
            }
    if model_id == "gemma-4-12b":
        _, assistant_meta = _profile_weight_meta(model_profiles, model_id, "assistant")
        assistant_repo = str((assistant_meta or {}).get("hf_repo") or "").strip()
        assistant_subdir = str(
            (assistant_meta or {}).get("local_subdir")
            or (assistant_meta or {}).get("path")
            or "gemma-4-12b-it-assistant"
        ).replace("\\", "/").strip().strip("/")
        if assistant_repo and assistant_subdir:
            draft_recipe = {
                "WEIGHT_KEY": f"{model_id}:assistant",
                "WEIGHT_MODEL": model_id,
                "WEIGHT_VARIANT": "assistant",
                "WEIGHT_REPO": assistant_repo,
                "WEIGHT_SUBDIR": assistant_subdir,
                "WEIGHT_FILES": "",
                "WEIGHT_KIND": "draft",
                "WEIGHT_VERIFY_GLOB": "*.safetensors",
            }
            if not draft_fallback_subdir:
                draft_fallback_subdir = assistant_subdir
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
    compose_hint_path = str(spec.get("compose_abs_path") or spec.get("derived_compose_path") or "").strip()
    compose_hints = _read_compose_repo_hints(compose_hint_path) if compose_hint_path else {"target": [], "draft": [], "generic": []}

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
        rel_file = str(asset.get("rel_path") or "").replace("\\", "/").strip().strip("/")
        direct_repo = ""
        if role == "model":
            direct_repo = next((item for item in compose_hints.get("target") or [] if str(item or "").strip()), "")
            if not direct_repo:
                direct_repo = next((item for item in compose_hints.get("generic") or [] if str(item or "").strip()), "")
        elif role == "draft":
            direct_repo = next((item for item in compose_hints.get("draft") or [] if str(item or "").strip()), "")
            if not direct_repo:
                direct_repo = next((item for item in compose_hints.get("generic") or [] if item not in set(compose_hints.get("target") or [])), "")
        elif role == "mmproj":
            direct_repo = next((item for item in compose_hints.get("generic") or [] if item not in set(compose_hints.get("target") or [])), "")

        direct_command = ""
        if (
            direct_repo
            and rel_file
            and os.path.basename(rel_file)
            and role in {"model", "draft", "mmproj"}
            and rel_file.lower().endswith((".gguf", ".safetensors", ".bin"))
        ):
            direct_command = _known_hf_file_download_command(model_dir_root, direct_repo, rel_file)
        if not direct_command:
            direct_command = _recipe_download_command(model_dir_root, recipe)
        if not direct_command:
            repo = ""
            if role == "model":
                repo = next((item for item in compose_hints.get("target") or [] if str(item or "").strip()), "")
                if not repo:
                    repo = next((item for item in compose_hints.get("generic") or [] if str(item or "").strip()), "")
            elif role == "draft":
                repo = next((item for item in compose_hints.get("draft") or [] if str(item or "").strip()), "")
                if not repo:
                    repo = next((item for item in compose_hints.get("generic") or [] if item not in set(compose_hints.get("target") or [])), "")
            elif role == "mmproj":
                repo = next((item for item in compose_hints.get("generic") or [] if item not in set(compose_hints.get("target") or [])), "")
            if repo and rel_file and os.path.basename(rel_file):
                if rel_file.lower().endswith((".gguf", ".safetensors", ".bin")):
                    direct_command = _known_hf_file_download_command(model_dir_root, repo, rel_file)
                else:
                    direct_command = _known_hf_download_command(model_dir_root, repo, rel_file)
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

    if not compose_abs_path:
        compose_abs_path = str(spec.get("derived_compose_path") or "").strip()
    repo_hints = _read_compose_repo_hints(compose_abs_path) if compose_abs_path else {"target": [], "draft": [], "generic": []}
    commands = []
    target_subdir = _hf_cache_subdir_from_model_path(spec.get("model_path"))
    draft_subdir = _hf_cache_subdir_from_model_path(spec.get("draft_model_path"))
    mmproj_subdir = _hf_cache_subdir_from_model_path(spec.get("mmproj_path"))
    target_rel_file = _model_rel_path_from_model_path(spec.get("model_path"))
    draft_rel_file = _model_rel_path_from_model_path(spec.get("draft_model_path"))
    mmproj_rel_file = _model_rel_path_from_model_path(spec.get("mmproj_path"))
    if target_subdir and repo_hints.get("target"):
        commands.append(_known_hf_download_command(model_dir_root, repo_hints["target"][0], target_subdir))
    elif target_subdir and repo_hints.get("generic"):
        commands.append(_known_hf_download_command(model_dir_root, repo_hints["generic"][0], target_subdir))
    elif target_rel_file and repo_hints.get("target"):
        commands.append(_known_hf_file_download_command(model_dir_root, repo_hints["target"][0], target_rel_file))
    elif target_rel_file and repo_hints.get("generic"):
        commands.append(_known_hf_file_download_command(model_dir_root, repo_hints["generic"][0], target_rel_file))
    if draft_subdir and repo_hints.get("draft"):
        commands.append(_known_hf_download_command(model_dir_root, repo_hints["draft"][0], draft_subdir))
    elif draft_subdir:
        generic_draft = next((repo for repo in repo_hints.get("generic") or [] if repo not in repo_hints.get("target", [])), "")
        if generic_draft:
            commands.append(_known_hf_download_command(model_dir_root, generic_draft, draft_subdir))
    elif draft_rel_file:
        generic_draft = next((repo for repo in repo_hints.get("draft") or [] if repo), "")
        if not generic_draft:
            generic_draft = next((repo for repo in repo_hints.get("generic") or [] if repo not in repo_hints.get("target", [])), "")
        if generic_draft:
            commands.append(_known_hf_file_download_command(model_dir_root, generic_draft, draft_rel_file))
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
    elif mmproj_rel_file and repo_hints.get("generic"):
        mmproj_repo = next(
            (
                repo for repo in repo_hints.get("generic") or []
                if repo != (repo_hints.get("target") or [""])[0]
            ),
            (repo_hints.get("generic") or [""])[0],
        )
        if mmproj_repo:
            commands.append(_known_hf_file_download_command(model_dir_root, mmproj_repo, mmproj_rel_file))
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


def _model_rel_path_from_model_path(model_path):
    path = str(model_path or "").replace("\\", "/").strip()
    marker = "/models/"
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
        compose_backed = bool(
            str((variant or {}).get("compose_rel_path") or "").strip()
            or str((variant or {}).get("model_path") or "").strip()
            or str((variant or {}).get("draft_model_path") or "").strip()
            or str((variant or {}).get("mmproj_path") or "").strip()
        )
        if host_model_dir and _path_has_model_assets(host_model_dir):
            return {
                "install_state": "ready",
                "install_command": "",
                "install_reason": "",
            }
        if not compose_backed:
            return {
                "install_state": "requires_download",
                "install_command": "",
                "install_reason": f"Expected imported model assets under {host_model_dir}." if host_model_dir else "Custom model assets are missing from disk.",
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
    elif model_id == "gemma-4-12b" and ("mtp" in selector.lower() or "mtp" in rel_path):
        base_subdir = compose_model_subdir or "gemma-4-12b-autoround-int8"
        draft_subdir = draft_model_subdir or "gemma-4-12b-it-assistant"
        base_ready = _dir_has_filetype(os.path.join(model_dir_root, base_subdir), {".safetensors"})
        assistant_ready = _dir_has_filetype(os.path.join(model_dir_root, draft_subdir), {".safetensors"})
        ready = base_ready and assistant_ready
        install_command = (
            _known_hf_download_command(model_dir_root, "Intel/gemma-4-12B-it-int8-AutoRound", base_subdir)
            + f' && {_known_hf_download_command(model_dir_root, "google/gemma-4-12B-it-assistant", draft_subdir)}'
        )
        install_reason = "This preset needs the Gemma 12B int8 weights plus the official Gemma assistant drafter."
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
    elif model_id == "qwen3-omni-30b-a3b":
        base_subdir = compose_model_subdir or "qwen3-omni-30b-a3b-instruct-int4-autoround"
        ready = _dir_has_filetype(os.path.join(model_dir_root, base_subdir), {".safetensors"})
        install_command = _known_hf_download_command(
            model_dir_root,
            "Intel/Qwen3-Omni-30B-A3B-Instruct-int4-AutoRound",
            base_subdir,
        )
        install_reason = "This preset needs Qwen3-Omni int4 AutoRound weights."
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
    if install_state == "ready" or _install_state_satisfied_by_resource_roles(spec):
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
    present_roles = set()
    for row in resources:
        if not row.get("exists"):
            continue
        role = "projector" if str(row.get("role") or "").strip().lower() == "projector" else str(row.get("role") or "").strip().lower()
        if role in {"model", "draft"} and not _path_has_model_assets(row.get("path")):
            continue
        present_roles.add(role)
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
            "container_name": _extract_shell_default_value(entry.get("container_name") or ""),
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
    _clear_root_aware_cache(_load_upstream_profiles)
    _clear_root_aware_cache(_load_upstream_compose_registry)
    _clear_root_aware_cache(_load_upstream_weights_reader)
    _clear_root_aware_cache(_load_upstream_weight_models)
    setattr(_weight_recipe_from_model_variant, "_cache", None)
    setattr(_weight_recipe_from_subpath, "_cache", None)
    write_custom_model_registry(read_custom_model_registry())
    custom_model_rows = read_custom_model_registry()
    tag_by_compose = _parse_switch_variants()
    model_profiles = _load_upstream_profiles()
    compose_registry = _load_upstream_compose_registry()
    if _migration_normalize_migrated_public_name_collisions(compose_registry, tag_by_compose=tag_by_compose):
        custom_model_rows = read_custom_model_registry()
    migrated_selector_by_source_compose = {}
    for row in custom_model_rows:
        source_rel_path = _normalize_compose_rel_path(row.get("source_compose_rel_path"))
        source_selector = _migration_strip_old_suffix(row.get("source_selector"))
        if source_rel_path and source_selector:
            migrated_selector_by_source_compose.setdefault(source_rel_path, source_selector)
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
        "custom_models": custom_model_rows,
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
        entry = _apply_builtin_launch_setting_defaults(variant)
        selector = _mode_selector_for_variant(entry)
        variant_id = str(entry.get("variant_id") or "").strip()
        if not selector and not variant_id:
            return
        if selector and not str(entry.get("selector") or "").strip():
            entry["selector"] = selector
        _apply_effective_service_image(entry)
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
            source_kind=entry.get("model_source_kind") or entry.get("source_kind") or "curated",
            inventory_origin=entry.get("model_inventory_origin") or entry.get("inventory_origin") or "compose_registry",
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
        if _compose_rel_path_is_archived(compose_rel_path):
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
            "service_image": runtime_meta.get("service_image") or "",
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
            "nvlink_mode": _variant_nvlink_mode(registry_entry, hardware_meta, topology),
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
            "compose_environment": runtime_meta.get("compose_environment") or [],
            "compose_volumes": runtime_meta.get("compose_volumes") or [],
            "compose_volume_targets": runtime_meta.get("compose_volume_targets") or [],
            "compose_command_summary": _read_compose_command_summary(compose_abs_path),
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
        if _compose_rel_path_is_archived(rel_path):
            continue
        if rel_path in registry_variant_keys:
            continue
        parts = rel_path.split("/")
        if len(parts) < 6 or parts[0] != "models":
            continue
        model_id = parts[1]
        engine = _normalize_engine("llama-cpp" if parts[2] == "llama-cpp" else parts[2])
        discovered_selector = (
            str(tag_by_compose.get(rel_path) or "").strip()
            or str(migrated_selector_by_source_compose.get(rel_path) or "").strip()
        )
        engine_display = _selector_engine_display(discovered_selector, rel_path)
        topology = parts[4]
        profile = _read_compose_profile_header(compose_abs_path)
        status_hints = _read_compose_status_hints(compose_abs_path)
        hardware_meta = _read_compose_hardware_metadata(compose_abs_path)
        runtime_meta = _read_compose_runtime_metadata(compose_abs_path)
        status_text = _variant_status_text(profile, status_hints, discovered_selector, {}, model_profiles)
        variant = {
            "variant_id": _variant_id_from_selector(discovered_selector) if discovered_selector else _variant_id_from_rel_path(rel_path),
            "upstream_tag": discovered_selector,
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
            "service_image": runtime_meta.get("service_image") or "",
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
            "profile_like": discovered_selector,
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
            "nvlink_mode": _variant_nvlink_mode({}, hardware_meta, topology),
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
            "compose_environment": runtime_meta.get("compose_environment") or [],
            "compose_volumes": runtime_meta.get("compose_volumes") or [],
            "compose_volume_targets": runtime_meta.get("compose_volume_targets") or [],
            "compose_command_summary": _read_compose_command_summary(compose_abs_path),
            "launch_settings": _read_compose_launch_settings(compose_abs_path),
            "default_engine_switches": _read_compose_command_text(compose_abs_path),
        }
        if variant["status_kind"] == "unknown" and variant["caveats"]:
            variant["status_kind"] = "production_caveat"
        variant["category"] = _category_for_variant(variant["topology"], variant["status_kind"])
        variant["scope_kind"] = _scope_kind_for_topology(variant["topology"])
        append_variant(variant)

    for row in custom_model_rows:
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
        if compose_abs_path:
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
        runtime_tp = int((runtime_meta.get("tp") or runtime_meta.get("tensor_parallel") or registry_entry.get("tp") or 1) or 1)
        topology = _infer_topology_from_compose_path(
            str(registry_entry.get("compose_path") or compose_rel_path or row.get("selector") or row.get("slug") or ""),
            _topology_from_gpu_count(runtime_tp),
        )
        gate_terminal = str(row.get("gate_terminal") or "").strip()
        row_status_kind = _normalize_status_kind(row.get("status_kind") or row.get("compat_status") or "")
        if row_status_kind == "deprecated":
            status_text = "deprecated"
        elif row_status_kind not in {"unknown", "migrated"}:
            status_text = row_status_kind.replace("_", " ")
        elif gate_terminal == "override-accepted":
            status_text = "experimental"
        elif gate_terminal == "confirm→proceed":
            status_text = "production caveat"
        else:
            status_text = "production"
        custom_preset = _custom_registry_row_is_preset(row)
        custom_nvlink_mode = _variant_nvlink_mode(
            {
                **dict(registry_entry or {}),
                "requires_nvlink": bool(row.get("requires_nvlink") or registry_entry.get("requires_nvlink")),
                "nvlink_mode": row.get("nvlink_mode") or registry_entry.get("nvlink_mode"),
            },
            runtime_meta,
            topology,
        )
        required_gpu_count = 2 if topology == "dual" else (max(1, runtime_tp) if topology == "multi" else 1)
        if custom_nvlink_mode == "required":
            required_gpu_count = max(required_gpu_count, 2)
        record_model_id = str(row.get("model_id") or row.get("profile_model_id") or "").strip()
        record_model_display_name = str(row.get("model_display_name") or "").strip()
        if custom_preset:
            record_model_display_name = record_model_display_name or _model_display_name_from_profiles(model_profiles, record_model_id)
        else:
            record_model_display_name = record_model_display_name or str(row.get("display_name") or row.get("slug") or record_model_id).strip()
        preset_display_name = str(row.get("display_name") or row.get("slug") or row.get("selector") or record_model_id).strip()
        ensure_model_row(
            record_model_id,
            display_name=record_model_display_name,
            source_kind="curated" if custom_preset else "custom",
            inventory_origin="compose_registry" if custom_preset else (str(row.get("inventory_origin") or "custom_registry").strip() or "custom_registry"),
        )
        variant = {
            "variant_id": _variant_id_from_selector(row.get("selector")),
            "upstream_tag": str(row.get("selector") or "").strip(),
            "registry_key": str(row.get("registry_key") or row.get("selector") or "").strip(),
            "model_id": record_model_id,
            "model_display_name": record_model_display_name,
            "display_name": preset_display_name,
            "custom_preset": bool(custom_preset),
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
            "service_image": runtime_meta.get("service_image") or "",
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
            "requires_min_gpu_count": required_gpu_count,
            "tensor_parallel": runtime_tp,
            "requires_sm": str(registry_entry.get("required_sm") or "").strip(),
            "requires_nvlink": bool(custom_nvlink_mode == "required"),
            "nvlink_mode": custom_nvlink_mode,
            "source_kind": "custom",
            "model_source_kind": "curated" if custom_preset else "custom",
            "model_inventory_origin": "compose_registry" if custom_preset else (str(row.get("inventory_origin") or "custom_registry").strip() or "custom_registry"),
            "inventory_origin": str(row.get("inventory_origin") or "custom_registry").strip() or "custom_registry",
            "profile_model_id": str(row.get("profile_model_id") or "").strip(),
            "profile_engine_id": str(row.get("profile_engine_id") or registry_entry.get("engine") or "").strip(),
            "profile_workload_id": str(row.get("profile_workload_id") or registry_entry.get("workload") or "").strip(),
            "profile_drafter_id": str(row.get("profile_drafter_id") or registry_entry.get("drafter") or "").strip(),
            "target_resource_key": str(row.get("target_resource_key") or "").strip(),
            "target_resource_path": str(row.get("target_resource_path") or "").strip(),
            "source_selector": str(row.get("source_selector") or "").strip(),
            "replacement_selector": str(row.get("replacement_selector") or "").strip(),
            "source_compose_rel_path": _normalize_compose_rel_path(row.get("source_compose_rel_path")),
            "source_status_kind": str(row.get("source_status_kind") or "").strip(),
            "confidence_tier": str(row.get("confidence_tier") or "").strip(),
            "gate_terminal": gate_terminal,
            "gate_reason": str(row.get("gate_reason") or "").strip(),
            "derived_compose_path": compose_abs_path,
            "compat_status": str(row.get("compat_status") or gate_terminal or "").strip(),
            "compat_reason_summary": str(row.get("compat_reason_summary") or "").strip(),
            "compose_environment": runtime_meta.get("compose_environment") or [],
            "compose_volumes": runtime_meta.get("compose_volumes") or [],
            "compose_volume_targets": runtime_meta.get("compose_volume_targets") or [],
            "compose_command_summary": _read_compose_command_summary(compose_abs_path) if compose_abs_path and os.path.exists(compose_abs_path) else "",
            "launch_settings": _read_compose_launch_settings(compose_abs_path) if compose_abs_path and os.path.exists(compose_abs_path) else [],
            "default_engine_switches": str((row.get("compose_meta") or {}).get("command_text") or _read_compose_command_text(compose_abs_path) if compose_abs_path and os.path.exists(compose_abs_path) else "").strip(),
        }
        variant["category"] = _category_for_variant(topology, variant["status_kind"])
        variant["scope_kind"] = _scope_kind_for_topology(topology)
        host_model_dir = str(row.get("host_model_dir") or (row.get("compose_meta") or {}).get("host_model_dir") or "").strip()
        if (
            host_model_dir
            and not _path_has_model_assets(host_model_dir)
            and str(row.get("inventory_origin") or "").strip() in {"migrated_custom_registry", "deprecated_backup_registry"}
        ):
            host_model_dir = ""
        variant["host_model_dir"] = host_model_dir
        ready = _path_has_model_assets(host_model_dir)
        compose_backed_resources = bool(
            str(variant.get("model_path") or "").strip()
            or str(variant.get("draft_model_path") or "").strip()
            or str(variant.get("mmproj_path") or "").strip()
        )
        fallback_install_state = {}
        if (
            not compose_backed_resources
            and not ready
            and not str(row.get("install_command") or "").strip()
            and str(row.get("inventory_origin") or "").strip() in {"migrated_custom_registry", "deprecated_backup_registry"}
        ):
            try:
                fallback_install_state = _detect_variant_install_state(variant, _resolve_variant_model_dir_root(variant))
            except Exception:
                fallback_install_state = {}
        append_variant(
            variant,
            force_install_state=None if compose_backed_resources else {
                "install_state": "ready" if ready else str(fallback_install_state.get("install_state") or "requires_download"),
                "install_command": "" if ready else (
                    str(row.get("install_command") or "").strip()
                    or str(fallback_install_state.get("install_command") or "").strip()
                ),
                "install_reason": "" if ready else (
                    str(row.get("install_reason") or "").strip()
                    or str(fallback_install_state.get("install_reason") or "").strip()
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

    _ensure_runtime_upstream_repo_on_sys_path()
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
    repo_root = Path(_ensure_runtime_upstream_repo_on_sys_path())
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


def _apply_launch_env_to_command_text(command_text, env):
    text = str(command_text or "").replace("\r", "").strip()
    if not text:
        return ""
    option_map = {
        "MAX_MODEL_LEN": ["--max-model-len"],
        "CTX_SIZE": ["--ctx-size", "-c"],
        "GPU_MEMORY_UTILIZATION": ["--gpu-memory-utilization"],
        "MAX_NUM_SEQS": ["--max-num-seqs"],
        "MAX_NUM_BATCHED_TOKENS": ["--max-num-batched-tokens"],
        "KV_CACHE_DTYPE": ["--kv-cache-dtype"],
        "MODEL_NAME": ["--served-model-name"],
    }
    for key, value in dict(env or {}).items():
        env_key = str(key or "").strip().upper()
        env_value = str(value or "").strip()
        if not env_key or not env_value:
            continue
        if env_key == "TEMPERATURE":
            text = re.sub(r"\$\{TEMP(?::-|-)\$\{TEMPERATURE(?::-|-)[^}]*\}\}", env_value, text)
            text = re.sub(r"\$\{TEMP(?::-|-)[^}]*\}", env_value, text)
        text = re.sub(rf"\$\{{{re.escape(env_key)}(?::-|-)[^}}]*\}}", env_value, text)
        text = re.sub(rf"\$\{{{re.escape(env_key)}\}}", env_value, text)
        if env_key in option_map:
            text = _replace_command_option_value(text, option_map[env_key], env_value)
    return text


def _split_compose_volume_spec(body):
    text = str(body or "")
    for index, char in enumerate(text):
        if char != ":":
            continue
        if index == 1 and text[:1].isalpha() and len(text) > 2 and text[2] in {"/", "\\"}:
            continue
        source = text[:index]
        rest = text[index + 1 :]
        target = rest.split(":", 1)[0]
        if source and target.startswith(("/", "${")):
            return source, ":", rest
    return text, "", ""


def _compose_volume_source_is_absolute_like(source_text):
    text = str(source_text or "").strip()
    return bool(text.startswith(("/", "~")) or re.match(r"^[A-Za-z]:[\\/]", text))


def _rewrite_compose_relative_volume_sources(compose_text, source_dir):
    source_root = os.path.abspath(str(source_dir or ""))
    if not source_root:
        return str(compose_text or "")
    output = []
    for raw_line in str(compose_text or "").splitlines():
        line = raw_line
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if not stripped.startswith("- "):
            output.append(line)
            continue
        body = stripped[2:].strip()
        quote = ""
        if len(body) >= 2 and body[0] in {"'", '"'} and body[-1] == body[0]:
            quote = body[0]
            body_inner = body[1:-1]
        else:
            body_inner = body
        source, sep, rest = _split_compose_volume_spec(body_inner)
        source_text = source.strip()
        if (
            sep
            and source_text
            and not source_text.startswith(("${", "/", "~"))
            and (source_text.startswith("../") or source_text.startswith("./"))
        ):
            absolute_source = os.path.abspath(os.path.join(source_root, source_text))
            absolute_source = absolute_source.replace("\\", "/")
            body_inner = f"{absolute_source}:{rest}"
            body = f"{quote}{body_inner}{quote}" if quote else body_inner
            line = f"{indent}- {body}"
        output.append(line)
    trailing = "\n" if str(compose_text or "").endswith("\n") else ""
    return "\n".join(output) + trailing


def _migration_checkout_root_for_path(path):
    current = os.path.abspath(str(path or ""))
    if os.path.isfile(current):
        current = os.path.dirname(current)
    while current and current != os.path.dirname(current):
        if (
            os.path.exists(os.path.join(current, ".git"))
            or os.path.exists(os.path.join(current, "scripts", "lib", "profiles", "compose_registry.py"))
        ):
            return current
        current = os.path.dirname(current)
    return ""


def _migration_volume_source_candidate(source_text, backup_root):
    source = os.path.abspath(os.path.expanduser(str(source_text or "").strip()))
    if os.path.isfile(source) or os.path.isdir(source):
        return source
    backup = os.path.abspath(str(backup_root or "").strip())
    current_root = os.path.abspath(str(CLUB3090_DIR or "").strip())
    if backup and current_root:
        try:
            rel = os.path.relpath(source, current_root)
        except Exception:
            rel = ""
        if rel and not rel.startswith("..") and not os.path.isabs(rel):
            mapped = os.path.join(backup, rel)
            if os.path.isfile(mapped) or os.path.isdir(mapped):
                return mapped
    return ""


def _migration_volume_source_within_checkout(source_text, backup_root):
    source = os.path.abspath(os.path.expanduser(str(source_text or "").strip()))
    for root in (backup_root, CLUB3090_DIR):
        root_abs = os.path.abspath(str(root or "").strip())
        if not root_abs:
            continue
        try:
            if os.path.commonpath([root_abs, source]) == root_abs:
                return True
        except Exception:
            continue
    return False


def _migration_volume_target_is_cache(rest):
    target = str(rest or "").split(":", 1)[0].strip().lower()
    return any(
        token in target
        for token in (
            "/.cache/",
            "/cache/",
            "torch_compile",
            "triton",
            "lmcache",
        )
    )


def _migration_path_size_bytes(path, limit_bytes=64 * 1024 * 1024):
    total = 0
    try:
        if os.path.isfile(path):
            return os.path.getsize(path)
        for dirpath, _dirnames, filenames in os.walk(path):
            for name in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, name))
                except Exception:
                    continue
                if total > limit_bytes:
                    return total
    except Exception:
        return limit_bytes + 1
    return total


def _migration_volume_rel_hint(candidate, backup, fallback):
    for root in (backup, os.path.abspath(str(CLUB3090_DIR or "").strip())):
        if not root:
            continue
        try:
            rel = os.path.relpath(candidate, root)
        except Exception:
            rel = ""
        if rel and not rel.startswith("..") and not os.path.isabs(rel):
            return rel.replace("\\", "/")
    return str(fallback or os.path.basename(candidate) or "migrated-volume-source")


def _migration_moved_asset_equivalent(candidate, backup):
    backup_root = os.path.abspath(str(backup or "").strip())
    current_root = os.path.abspath(str(CLUB3090_DIR or "").strip())
    source = os.path.abspath(str(candidate or "").strip())
    if not backup_root or not current_root:
        return ""
    try:
        rel = os.path.relpath(source, backup_root)
    except Exception:
        return ""
    if not rel or rel.startswith("..") or os.path.isabs(rel):
        return ""
    rel_parts = rel.replace("\\", "/").split("/")
    top_level = rel_parts[0] if rel_parts else ""
    moved_top_levels = {"models-cache", "ai-studio-models", "results", "lmcache-kv"}
    is_moved_model_cache = len(rel_parts) >= 3 and rel_parts[0] == "models" and rel_parts[-1] == "cache"
    if top_level not in moved_top_levels and not is_moved_model_cache:
        return ""
    mapped = os.path.join(current_root, rel)
    if os.path.exists(mapped):
        return mapped
    return ""


def _migration_backup_root_for_path(path, fallback=""):
    source = os.path.abspath(str(path or "").strip())
    fallback_root = os.path.abspath(str(fallback or "").strip())
    if fallback_root and _path_is_within(fallback_root, source):
        return fallback_root
    normalized = source.replace("\\", "/")
    marker = "/club-3090-backup"
    index = normalized.find(marker)
    if index < 0:
        return fallback_root
    end = normalized.find("/", index + 1)
    root = normalized[:end] if end > index else normalized
    return root if root and os.path.isdir(root) else fallback_root


def _migration_control_owned_volume_dir(target_root, folder, stem):
    stem = _migration_scrub_volume_stem(stem)
    path = os.path.join(target_root, folder, stem[:120] or "migrated-volume-source")
    os.makedirs(path, exist_ok=True)
    return path


def _migration_scrub_volume_stem(stem):
    token = _selector_token(stem)
    token = re.sub(
        r"(^|-)opt-ai-club-3090-backup(?:-[a-z0-9]+)*?-(models-cache|ai-studio-models|results|lmcache-kv|models)-",
        r"\1\2-",
        token,
    )
    token = re.sub(r"(^|-)club-3090-backup(?:-[a-z0-9]+)*?-", r"\1backup-", token)
    token = token.replace("club-3090-backup", "backup")
    token = re.sub(r"-+", "-", token).strip("-")
    return token or "migrated-volume-source"


def _migration_rehome_control_owned_volume_source(source_text, target_root):
    source = os.path.abspath(os.path.expanduser(str(source_text or "").strip()))
    target = os.path.abspath(str(target_root or "").strip())
    if not source or not target or not _path_is_within(target, source):
        return ""
    normalized = source.replace("\\", "/")
    if "club-3090-backup" not in normalized:
        return ""
    parent = os.path.dirname(source)
    leaf = os.path.basename(source.rstrip(os.sep))
    stem, ext = os.path.splitext(leaf)
    cleaned = _migration_scrub_volume_stem(stem)
    new_leaf = cleaned + ext
    if not new_leaf or new_leaf == leaf:
        return ""
    destination = os.path.join(parent, new_leaf)
    if os.path.abspath(destination) == source:
        return ""
    try:
        if os.path.exists(source):
            if not os.path.exists(destination):
                shutil.move(source, destination)
            elif os.path.isdir(source) and os.path.isdir(destination):
                shutil.copytree(source, destination, dirs_exist_ok=True)
                shutil.rmtree(source, ignore_errors=True)
            elif os.path.isfile(source) and not os.path.isfile(destination):
                shutil.copy2(source, destination)
        elif not os.path.exists(destination):
            os.makedirs(destination, exist_ok=True)
    except Exception:
        return ""
    return destination


def _vendor_migrated_compose_file_volume_sources(compose_text, source_dir, target_dir, backup_root=""):
    backup = os.path.abspath(str(backup_root or "").strip()) or _migration_checkout_root_for_path(source_dir)
    target_root = os.path.abspath(str(target_dir or "").strip())
    if not target_root:
        return str(compose_text or "")
    output = []
    for raw_line in str(compose_text or "").splitlines():
        line = raw_line
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if not stripped.startswith("- "):
            output.append(line)
            continue
        body = stripped[2:].strip()
        quote = ""
        if len(body) >= 2 and body[0] in {"'", '"'} and body[-1] == body[0]:
            quote = body[0]
            body_inner = body[1:-1]
        else:
            body_inner = body
        source, sep, rest = _split_compose_volume_spec(body_inner)
        source_text = source.strip()
        if not sep or not source_text or not _compose_volume_source_is_absolute_like(source_text):
            output.append(line)
            continue
        target_is_cache = _migration_volume_target_is_cache(rest)
        rehomed_source = _migration_rehome_control_owned_volume_source(source_text, target_root)
        if rehomed_source:
            body_inner = f"{rehomed_source.replace('\\', '/')}:{rest}"
            body = f"{quote}{body_inner}{quote}" if quote else body_inner
            output.append(f"{indent}- {body}")
            continue
        source_backup = _migration_backup_root_for_path(source_text, backup)
        candidate = _migration_volume_source_candidate(source_text, source_backup)
        if not candidate:
            if target_is_cache and _migration_volume_source_within_checkout(source_text, source_backup):
                stem = _selector_token(source_text)
                cache_path = _migration_control_owned_volume_dir(target_root, "migrated-cache", stem)
                body_inner = f"{cache_path.replace('\\', '/')}:{rest}"
                body = f"{quote}{body_inner}{quote}" if quote else body_inner
                output.append(f"{indent}- {body}")
                continue
            output.append(line)
            continue
        if _path_is_within(target_root, candidate):
            output.append(line)
            continue
        candidate_backup = _migration_backup_root_for_path(candidate, backup)
        rel_hint = _migration_volume_rel_hint(candidate, candidate_backup, source_text)
        stem = _selector_token(rel_hint or os.path.basename(candidate) or "migrated-volume-file")
        ext = os.path.splitext(candidate)[1]
        if target_is_cache:
            asset_source = _migration_control_owned_volume_dir(target_root, "migrated-cache", stem).replace("\\", "/")
        else:
            moved_asset = _migration_moved_asset_equivalent(candidate, candidate_backup)
            if moved_asset:
                body_inner = f"{moved_asset.replace('\\', '/')}:{rest}"
                body = f"{quote}{body_inner}{quote}" if quote else body_inner
                output.append(f"{indent}- {body}")
                continue
            asset_dir = os.path.join(target_root, "migrated-assets")
            os.makedirs(asset_dir, exist_ok=True)
            if os.path.isdir(candidate):
                asset_path = os.path.join(asset_dir, stem[:120] or "migrated-volume-dir")
                shutil.copytree(candidate, asset_path, dirs_exist_ok=True)
                asset_source = asset_path.replace("\\", "/")
            else:
                asset_path = os.path.join(asset_dir, (stem[:120] or "migrated-volume-file") + ext)
                shutil.copy2(candidate, asset_path)
                asset_source = asset_path.replace("\\", "/")
        body_inner = f"{asset_source}:{rest}"
        body = f"{quote}{body_inner}{quote}" if quote else body_inner
        line = f"{indent}- {body}"
        output.append(line)
    trailing = "\n" if str(compose_text or "").endswith("\n") else ""
    return "\n".join(output) + trailing


def normalize_custom_model_compose_volume_sources(backup_root=""):
    rows = read_custom_model_registry()
    changed = False
    normalized = 0
    seen_compose_paths = set()

    def normalize_compose_file(compose_path, record_id="", row=None):
        nonlocal changed, normalized
        compose_path = os.path.normpath(str(compose_path or "").strip())
        if (
            not compose_path
            or not os.path.isfile(compose_path)
            or not _path_is_within(CUSTOM_MODELS_DIR, os.path.abspath(compose_path))
        ):
            return
        seen_compose_paths.add(os.path.abspath(compose_path))
        with open(compose_path, "r", encoding="utf-8", errors="replace") as handle:
            compose_text = handle.read()
        normalized_text = _vendor_migrated_compose_file_volume_sources(
            compose_text,
            os.path.dirname(compose_path),
            os.path.dirname(compose_path),
            backup_root=backup_root,
        )
        if normalized_text == compose_text:
            return
        write_text_atomic_if_changed(compose_path, normalized_text)
        if isinstance(row, dict):
            row["compose_path"] = compose_path
            if record_id:
                row["compose_rel_path"] = _normalize_compose_rel_path(os.path.join("custom-models", record_id, "docker-compose.yml"))
            row["compose_meta"] = _read_compose_runtime_metadata(compose_path)
            changed = True
        normalized += 1

    for row in rows:
        if not isinstance(row, dict):
            continue
        record_id = _selector_token(row.get("id") or row.get("selector") or row.get("model_id") or "")
        compose_path = os.path.normpath(str(row.get("compose_path") or "").strip())
        if not compose_path and record_id:
            compose_path = os.path.join(CUSTOM_MODELS_DIR, record_id, "docker-compose.yml")
        normalize_compose_file(compose_path, record_id=record_id, row=row)
    for pattern in ("docker-compose.yml", "docker-compose.yaml"):
        for compose_path in glob.glob(os.path.join(CUSTOM_MODELS_DIR, "*", pattern)):
            if os.path.abspath(compose_path) in seen_compose_paths:
                continue
            normalize_compose_file(compose_path, record_id=os.path.basename(os.path.dirname(compose_path)), row=None)
    if changed:
        write_custom_model_registry(rows)
    return normalized


def _rename_compose_service_identity(compose_text, record_id):
    text = str(compose_text or "")
    service_name = f"club3090-custom-{_selector_token(record_id)}"
    container_name = f"club3090-custom-{_selector_token(record_id)}"
    output = []
    in_services = False
    service_replaced = False
    for raw_line in text.splitlines():
        line = raw_line
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if stripped == "services:":
            in_services = True
            output.append(line)
            continue
        if in_services and not service_replaced and indent == 2 and stripped.endswith(":") and not stripped.startswith("x-"):
            output.append(f"  {service_name}:")
            service_replaced = True
            continue
        if service_replaced and re.match(r"^\s*container_name\s*:", line):
            output.append("    container_name: \"${ESTATE_CONTAINER:-" + container_name + "}\"")
            continue
        output.append(line)
    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(output) + trailing


def _duplicate_preset_source_variant(selector):
    key = str(selector or "").strip()
    if not key:
        raise ValueError("Source preset selector is required")
    inventory = load_runtime_inventory(force=True, rebuild_if_missing=True)
    variant = next(
        (
            row for row in (inventory.get("variants") or [])
            if str(row.get("selector") or row.get("upstream_tag") or row.get("variant_id") or "").strip() == key
        ),
        None,
    )
    if not variant:
        raise ValueError("Source preset not found in runtime inventory")
    return dict(variant)


def _duplicate_engine_family(engine):
    value = str(engine or "").strip().lower().replace("_", "-")
    if value in {"ik-llama", "llamacpp", "llama-cpp"}:
        return "llamacpp"
    return value


def _variant_model_resource_matches(row, target_resource_key="", target_resource_path=""):
    wanted_key = str(target_resource_key or "").strip()
    wanted_path = os.path.normpath(str(target_resource_path or "").strip()) if str(target_resource_path or "").strip() else ""
    if not wanted_key and not wanted_path:
        return False
    for resource in row.get("resources") or []:
        if not isinstance(resource, dict):
            continue
        role = str(resource.get("role") or "").strip().lower()
        if role and role != "model":
            continue
        resource_key = str(resource.get("identity_key") or resource.get("path") or "").strip()
        resource_path = os.path.normpath(str(resource.get("path") or "").strip()) if str(resource.get("path") or "").strip() else ""
        if wanted_key and resource_key == wanted_key:
            return True
        if wanted_path and resource_path == wanted_path:
            return True
    return False


def _choose_duplicate_target_variant(inventory, source, target_model_id="", target_resource_key="", target_resource_path=""):
    source_engine = str((source or {}).get("engine") or "").strip().lower()
    source_family = _duplicate_engine_family(source_engine)
    source_topology = str((source or {}).get("topology") or "").strip().lower()
    target_model = str(target_model_id or "").strip()
    rows = [
        dict(row)
        for row in (inventory.get("variants") or [])
        if _duplicate_engine_family(row.get("engine")) == source_family
    ]
    if target_resource_key or target_resource_path:
        rows = [
            row
            for row in rows
            if _variant_model_resource_matches(row, target_resource_key, target_resource_path)
        ]
    elif target_model:
        rows = [row for row in rows if str(row.get("model_id") or "").strip() == target_model]
    if not rows:
        return None
    rows.sort(
        key=lambda row: (
            0 if str(row.get("engine") or "").strip().lower() == source_engine else 1,
            0 if str(row.get("topology") or "").strip().lower() == source_topology else 1,
            0 if str(row.get("status_kind") or "").strip() in {"production", "production_caveat"} else 1,
            str(row.get("selector") or row.get("upstream_tag") or row.get("variant_id") or ""),
        )
    )
    return rows[0]


def _replace_command_option_value(command_text, option_names, value):
    replacement = str(value or "").strip()
    if not replacement:
        return str(command_text or "")
    options = {str(item or "").strip() for item in (option_names or []) if str(item or "").strip()}
    lines = [str(line or "").rstrip() for line in str(command_text or "").replace("\r", "").splitlines()]
    output = []
    idx = 0
    changed = False
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        matched_inline = False
        for option in options:
            if stripped.startswith(f"{option} "):
                output.append(f"{option} {replacement}")
                changed = True
                matched_inline = True
                break
            if stripped.startswith(f"{option}="):
                output.append(f"{option}={replacement}")
                changed = True
                matched_inline = True
                break
        if matched_inline:
            idx += 1
            continue
        if stripped in options and idx + 1 < len(lines):
            output.append(line)
            output.append(replacement)
            idx += 2
            changed = True
            continue
        output.append(line)
        idx += 1
    return "\n".join(output).strip() if changed else str(command_text or "")


def _retarget_duplicate_command_text(command_text, source, target_variant, skip_model_path=False):
    target = target_variant if isinstance(target_variant, dict) else {}
    if not target:
        return str(command_text or "")
    text = str(command_text or "")
    model_path = str(target.get("model_path") or "").strip()
    served_name = str(target.get("served_model_name") or "").strip()
    draft_path = str(target.get("draft_model_path") or "").strip()
    mmproj_path = str(target.get("mmproj_path") or "").strip()
    if model_path and not skip_model_path:
        text = _replace_command_option_value(text, ["--model", "--model-path", "-m"], model_path)
    if served_name:
        text = _replace_command_option_value(text, ["--served-model-name"], served_name)
    if draft_path:
        text = _replace_command_option_value(text, ["--spec-draft-model", "--draft-model", "--speculative-draft-model-path"], draft_path)
    if mmproj_path:
        text = _replace_command_option_value(text, ["--mmproj"], mmproj_path)
    max_len = int(target.get("max_model_len") or 0)
    if max_len > 0 and int((source or {}).get("max_model_len") or 0) > 0:
        text = _replace_command_option_value(text, ["--max-model-len", "--ctx-size", "-c"], str(max_len))
    return text


def duplicate_custom_preset(data):
    payload = dict(data or {})
    source = _duplicate_preset_source_variant(payload.get("selector") or payload.get("source_selector") or "")
    source_selector = str(source.get("selector") or source.get("upstream_tag") or "").strip()
    record_id = _selector_token(payload.get("name") or f"{source_selector}-optimized")
    if not record_id:
        raise ValueError("Custom preset name is required")
    selector = f"custom/{record_id}"
    if any(str(row.get("id") or "") == record_id or str(row.get("selector") or "") == selector for row in read_custom_model_registry()):
        raise ValueError(f"A custom preset named {record_id} is already registered")
    target_model_id = str(payload.get("target_model_id") or "").strip()
    target_resource_key = str(payload.get("target_model_resource_key") or payload.get("target_resource_key") or "").strip()
    target_resource_path = str(payload.get("target_model_resource_path") or payload.get("target_resource_path") or "").strip()
    if not target_model_id and not target_resource_key and not target_resource_path:
        target_model_id = str(source.get("profile_model_id") or source.get("model_id") or "").strip()
    if not target_model_id and not target_resource_key and not target_resource_path:
        raise ValueError("Target model resource is required")
    inventory = load_runtime_inventory(force=False, rebuild_if_missing=True)
    target_variant = _choose_duplicate_target_variant(inventory, source, target_model_id, target_resource_key, target_resource_path)
    if not target_variant:
        raise ValueError("Target model resource is not compatible with the source preset engine family")
    target_model_id = target_model_id or str(target_variant.get("model_id") or "").strip()
    target_model_display_name = str(
        target_variant.get("model_display_name")
        or target_variant.get("model_display")
        or _format_model_display_name(target_model_id)
    ).strip()
    compose_path = str(source.get("compose_abs_path") or "").strip()
    if not compose_path or not os.path.exists(compose_path):
        raise ValueError("Source preset compose file is missing")
    with open(compose_path, "r", encoding="utf-8", errors="replace") as handle:
        compose_text = handle.read()
    env = {
        str(key or "").strip().upper(): str(value or "").strip()
        for key, value in dict(payload.get("env") or {}).items()
        if str(key or "").strip() and str(value or "").strip()
    }
    command_text = str(payload.get("command_text") or "").replace("\r", "").strip()
    if not command_text:
        command_text = _apply_launch_env_to_command_text(_read_compose_command_text(compose_path), env)
    else:
        command_text = _apply_launch_env_to_command_text(command_text, env)
    if target_resource_key or target_resource_path or target_model_id != str(source.get("model_id") or "").strip():
        command_text = _retarget_duplicate_command_text(
            command_text,
            source,
            target_variant,
            skip_model_path="GGUF_FILE" in env,
        )
    custom_dir = os.path.join(CUSTOM_MODELS_DIR, record_id)
    compose_text = _rewrite_compose_relative_volume_sources(compose_text, os.path.dirname(compose_path))
    compose_text = _vendor_migrated_compose_file_volume_sources(
        compose_text,
        os.path.dirname(compose_path),
        custom_dir,
    )
    compose_text = _rename_compose_service_identity(compose_text, record_id)
    if command_text:
        compose_text = _replace_compose_command_text(compose_text, command_text)
    custom_compose_path = os.path.join(custom_dir, "docker-compose.yml")
    write_text_atomic_if_changed(custom_compose_path, compose_text)
    runtime_meta = _read_compose_runtime_metadata(custom_compose_path)
    if command_text:
        runtime_meta["command_text"] = command_text
    display_name = str(payload.get("display_name") or payload.get("name") or record_id).strip() or record_id
    root_model_dir = _resolve_variant_model_dir_root(target_variant or source)
    record = {
        "id": record_id,
        "selector": selector,
        "slug": source_selector,
        "model_id": target_model_id,
        "model_display_name": target_model_display_name,
        "display_name": display_name,
        "custom_preset": True,
        "profile_like": str(source.get("profile_like") or source_selector or "").strip(),
        "compose_path": custom_compose_path,
        "compose_rel_path": _normalize_compose_rel_path(os.path.join("custom-models", record_id, "docker-compose.yml")),
        "inventory_origin": "custom_registry",
        "registry_key": selector,
        "profile_model_id": target_model_id,
        "target_resource_key": target_resource_key,
        "target_resource_path": target_resource_path,
        "profile_engine_id": str(source.get("profile_engine_id") or source.get("engine_profile") or "").strip(),
        "profile_workload_id": str(source.get("profile_workload_id") or source.get("workload_id") or "").strip(),
        "profile_drafter_id": str(source.get("profile_drafter_id") or source.get("drafter_profile") or "").strip(),
        "confidence_tier": "custom",
        "gate_terminal": "override-accepted",
        "gate_reason": f"Duplicated from {source_selector or source.get('variant_id') or 'preset'}.",
        "compat_status": "custom",
        "compat_reason_summary": f"Custom duplicate of {source_selector or source.get('variant_id') or 'preset'} targeting {target_model_id}.",
        "best_for": str(payload.get("best_for") or f"Custom optimized duplicate of {source_selector or source.get('variant_id') or 'preset'}.").strip(),
        "quality_summary": str(source.get("quality_summary") or "").strip(),
        "caveats": str(payload.get("caveats") or "Custom preset; benchmark before production use.").strip(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host_model_dir": root_model_dir,
        "install_command": str(source.get("install_command") or "").strip(),
        "install_reason": str(source.get("install_reason") or "").strip(),
        "compose_meta": runtime_meta,
    }
    rows = read_custom_model_registry()
    rows.append(record)
    write_custom_model_registry(rows)
    if env or command_text:
        cfg = read_server_config()
        overrides = dict(cfg.get("preset_launch_overrides") or {})
        overrides[selector] = {"env": env}
        if command_text:
            overrides[selector]["command_text"] = command_text
        write_server_config({"preset_launch_overrides": overrides})
    inventory = enrich_runtime_inventory_cache_sizes(rebuild_runtime_inventory())
    log_control(f"CUSTOM_PRESET duplicated source={source_selector} selector={selector}")
    return {
        "ok": True,
        "selector": selector,
        "record": {key: value for key, value in record.items() if key != "compose_text"},
        "runtime_inventory": inventory,
        "models": inventory.get("models") or [],
        "variants": inventory.get("variants") or [],
    }


def delete_custom_preset_record(selector):
    target = delete_custom_model_record(selector)
    cfg = read_server_config()
    overrides = dict(cfg.get("preset_launch_overrides") or {})
    removed_selector = str(target.get("selector") or selector or "").strip()
    if removed_selector and removed_selector in overrides:
        overrides.pop(removed_selector, None)
        write_server_config({"preset_launch_overrides": overrides})
    inventory = enrich_runtime_inventory_cache_sizes(load_runtime_inventory(force=True))
    log_control(f"CUSTOM_PRESET deleted selector={removed_selector}")
    return {
        "ok": True,
        "deleted": target,
        "runtime_inventory": inventory,
        "models": inventory.get("models") or [],
        "variants": inventory.get("variants") or [],
    }


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
            run_cmd(compose_cmd() + ["--project-directory", compose_dir, "-f", compose_path, "down"], timeout=60, cwd=compose_dir, env=env)
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
