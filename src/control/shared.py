#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit
import mimetypes
import base64
import calendar
import codecs
import collections
import fnmatch
import glob
import gzip
import hashlib
import ipaddress
import json
import math
import os
import platform
try:
    import pwd
except Exception:
    pwd = None
try:
    import pty
except Exception:
    pty = None
import posixpath
import re
import secrets
import select
import shlex
import shutil
import signal
import site
import socket
import subprocess
import sys
import stat
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
try:
    import tomllib
except Exception:
    tomllib = None

CLUB3090_DIR = os.environ.get("CLUB3090_DIR", "/opt/ai/club-3090")
CONTROL_DIR = "/opt/club3090-control"
SCRIPT_VERSION = os.environ.get("CLUB3090_SCRIPT_VERSION", "unknown")
SCRIPT_CLUB3090_COMPAT = {}
_SCRIPT_VERSION_MATCH = re.search(r"v(\d+)\.(\d+)\.(\d+)([a-z]*)\s*$", str(SCRIPT_VERSION or ""))
DEBUG_LOGS = not (_SCRIPT_VERSION_MATCH and int(_SCRIPT_VERSION_MATCH.group(3)) == 0)
ACTIVE_MODE_FILE = os.path.join(CONTROL_DIR, "active_mode")
LAST_GOOD_MODE_FILE = os.path.join(CONTROL_DIR, "last_good_mode")
CONTROL_LOG_FILE = os.path.join(CONTROL_DIR, "control.log")
AUDIT_LOG_FILE = os.path.join(CONTROL_DIR, "audit.log")
DEBUG_LOG_FILE = os.path.join(CONTROL_DIR, "debug.log")
UPDATE_LOG_FILE = os.path.join(CONTROL_DIR, "self-update.log")
UPDATE_STATE_FILE = os.path.join(CONTROL_DIR, "self-update-state.json")
UI_CONFIG_FILE = os.path.join(CONTROL_DIR, "ui_config.json")
PRESET_TPS_STATS_FILE = os.path.join(CONTROL_DIR, "preset_tps_stats.json")
SYSTEM_METRIC_PEAKS_FILE = os.path.join(CONTROL_DIR, "system_metric_peaks.json")
GPU_LAST_SEEN_FILE = os.path.join(CONTROL_DIR, "gpu_last_seen.json")
METRICS_HISTORY_FILE = os.path.join(CONTROL_DIR, "metrics_history.json")
CONFIG_TOML_FILE = os.path.join(CONTROL_DIR, "config.toml")


def _env_int(name, default):
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return int(default)


def _env_float(name, default):
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return float(default)


def _env_str(name, default):
    return str(os.environ.get(name, str(default)))


DEFAULT_RUNTIME_CONFIG = {
    "network": {
        "admin_port": _env_int("CLUB3090_ADMIN_PORT", 8008),
        "proxy_port": _env_int("CLUB3090_PROXY_PORT", 8009),
        "local_api_port": _env_int("CLUB3090_LOCAL_API_PORT", 10881),
        "admin_bind_host": _env_str("CLUB3090_ADMIN_BIND_HOST", "0.0.0.0"),
        "proxy_bind_host": _env_str("CLUB3090_PROXY_BIND_HOST", "0.0.0.0"),
        "updater_bind_host": _env_str("CLUB3090_UPDATER_BIND_HOST", "127.0.0.1"),
        "updater_bind_port": _env_int("CLUB3090_UPDATER_BIND_PORT", 18010),
    },
    "metrics": {
        "history_retention_seconds": max(86400, _env_int("CLUB3090_METRICS_HISTORY_RETENTION_SECONDS", 86400)),
        "history_max_points": max(240, min(172800, _env_int("CLUB3090_METRICS_HISTORY_MAX_POINTS", _env_int("CLUB3090_METRICS_HISTORY_RETENTION_SECONDS", 86400)))),
        "history_status_max_points": max(240, min(480, _env_int("CLUB3090_METRICS_HISTORY_STATUS_MAX_POINTS", 480))),
        "history_persist_interval_seconds": max(5, _env_int("CLUB3090_METRICS_HISTORY_PERSIST_INTERVAL_SECONDS", 30)),
    },
    "power": {
        "idle_after_seconds": _env_int("CLUB3090_POWER_IDLE_AFTER_SECONDS", 600),
        "container_stop_after_seconds": _env_int("CLUB3090_CONTAINER_STOP_AFTER_SECONDS", 3600),
        "gpu_active_power_limit_w": _env_int("CLUB3090_GPU_ACTIVE_POWER_LIMIT_W", 280),
        "gpu_idle_power_limit_w": _env_int("CLUB3090_GPU_IDLE_POWER_LIMIT_W", 120),
        "gpu_idle_lock_clocks": _env_str("CLUB3090_GPU_IDLE_LOCK_CLOCKS", "210,900"),
        "gpu_active_lock_clocks": _env_str("CLUB3090_GPU_ACTIVE_LOCK_CLOCKS", ""),
        "cpu_active_governor": _env_str("CLUB3090_CPU_ACTIVE_GOVERNOR", "performance"),
        "cpu_idle_governor": _env_str("CLUB3090_CPU_IDLE_GOVERNOR", "powersave"),
    },
    "fans": {
        "max_speed": _env_int("CLUB3090_FAN_MAX_SPEED", 100),
        "min_safe_speed": _env_int("CLUB3090_FAN_MIN_SAFE_SPEED", 35),
    },
    "profiles": {
        "eco": {"gpu_active": 240, "gpu_idle": 90, "idle_clocks": "210,705", "cpu_active": "schedutil", "cpu_idle": "powersave", "idle_after": 300, "stop_after": 1800},
        "balanced": {"gpu_active": _env_int("CLUB3090_GPU_ACTIVE_POWER_LIMIT_W", 280), "gpu_idle": _env_int("CLUB3090_GPU_IDLE_POWER_LIMIT_W", 120), "idle_clocks": _env_str("CLUB3090_GPU_IDLE_LOCK_CLOCKS", "210,900"), "cpu_active": _env_str("CLUB3090_CPU_ACTIVE_GOVERNOR", "performance"), "cpu_idle": _env_str("CLUB3090_CPU_IDLE_GOVERNOR", "powersave"), "idle_after": _env_int("CLUB3090_POWER_IDLE_AFTER_SECONDS", 600), "stop_after": _env_int("CLUB3090_CONTAINER_STOP_AFTER_SECONDS", 3600)},
        "fast": {"gpu_active": 300, "gpu_idle": 120, "idle_clocks": "", "cpu_active": "schedutil", "cpu_idle": "powersave", "idle_after": 900, "stop_after": 3600},
        "benchmark_ready": {"gpu_active": 220, "gpu_idle": 120, "idle_clocks": "", "cpu_active": "schedutil", "cpu_idle": "powersave", "idle_after": 1800, "stop_after": 7200},
        "benchmark_safe": {"gpu_active": 200, "gpu_idle": 120, "idle_clocks": "", "cpu_active": "schedutil", "cpu_idle": "powersave", "idle_after": 1800, "stop_after": 7200},
        "turbo": {"gpu_active": 350, "gpu_idle": 160, "idle_clocks": "", "cpu_active": "performance", "cpu_idle": "schedutil", "idle_after": 1800, "stop_after": 7200},
    },
    "benchmarks": {
        "log_tail_lines": 500,
        "comparison_limit": 8,
        "session_success_icon_ttl_seconds": 7200,
        "quick_quality_thinking_max_tokens": 2048,
        "quick_reasoning_thinking_max_tokens": 4096,
        "quick_reasoning_timeout_per_case": 120,
        "quick_reasoning_step_timeout_seconds": 2400,
        "quick_compliance_prompts_per_category": 10,
        "full_compliance_prompts_per_category": 20,
        "quick_compliance_attempts_per_prompt": 1,
        "full_compliance_attempts_per_prompt": 3,
        "launch_vram_settle_timeout_seconds": _env_int("CLUB3090_BENCHMARK_LAUNCH_VRAM_SETTLE_TIMEOUT_SECONDS", 60),
        "launch_vram_free_ratio": _env_float("CLUB3090_BENCHMARK_LAUNCH_VRAM_FREE_RATIO", 0.94),
        "thermal": {
            "cool_core_target_c": _env_float("CLUB3090_BENCHMARK_SPEED_COOL_TARGET_C", 35),
            "cool_junction_target_c": _env_float("CLUB3090_BENCHMARK_SPEED_COOL_JUNCTION_TARGET_C", 49),
            "cool_vram_target_c": _env_float("CLUB3090_BENCHMARK_SPEED_COOL_VRAM_TARGET_C", 49),
            "cool_timeout_seconds": _env_int("CLUB3090_BENCHMARK_SPEED_COOL_TIMEOUT_SECONDS", 300),
            "core_abort_c": _env_float("CLUB3090_BENCHMARK_SPEED_CORE_ABORT_C", 83),
            "junction_abort_c": _env_float("CLUB3090_BENCHMARK_SPEED_JUNCTION_ABORT_C", 98),
            "vram_abort_c": _env_float("CLUB3090_BENCHMARK_SPEED_VRAM_ABORT_C", 98),
            "critical_core_abort_c": _env_float("CLUB3090_BENCHMARK_SPEED_CRITICAL_CORE_ABORT_C", 90),
            "critical_junction_abort_c": _env_float("CLUB3090_BENCHMARK_SPEED_CRITICAL_JUNCTION_ABORT_C", 108),
            "critical_vram_abort_c": _env_float("CLUB3090_BENCHMARK_SPEED_CRITICAL_VRAM_ABORT_C", 108),
            "turbo_skip_margin_c": _env_float("CLUB3090_BENCHMARK_SPEED_TURBO_SKIP_MARGIN_C", 2),
            "turbo_thermal_fallback_attempts": _env_int("CLUB3090_BENCHMARK_SPEED_TURBO_THERMAL_FALLBACK_ATTEMPTS", 3),
            "script_pause_margin_c": _env_float("CLUB3090_BENCHMARK_SCRIPT_THERMAL_PAUSE_MARGIN_C", 6),
            "script_power_limit_w": _env_int("CLUB3090_BENCHMARK_SCRIPT_POWER_LIMIT_W", 220),
            "script_safe_power_limit_w": _env_int("CLUB3090_BENCHMARK_SCRIPT_SAFE_POWER_LIMIT_W", 200),
            "thermal_penalty_score": _env_float("CLUB3090_BENCHMARK_SPEED_THERMAL_PENALTY_SCORE", 0.75),
            "thermal_grace_seconds": _env_int("CLUB3090_BENCHMARK_SPEED_THERMAL_GRACE_SECONDS", 600),
            "thermal_sustained_seconds": _env_int("CLUB3090_BENCHMARK_SPEED_THERMAL_SUSTAINED_SECONDS", 1800),
        },
    },
}
runtime_config_cache = {"path": "", "mtime": None, "data": None, "error": ""}


def _deep_copy_jsonish(value):
    try:
        return json.loads(json.dumps(value))
    except Exception:
        return value


def _deep_merge_config(base, override):
    result = _deep_copy_jsonish(base if isinstance(base, dict) else {})
    for key, value in (override if isinstance(override, dict) else {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_config(result.get(key), value)
        else:
            result[key] = value
    return result


def _fallback_parse_toml(text):
    root = {}
    current = root
    for raw in str(text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = root
            for part in line.strip("[]").split("."):
                key = part.strip().replace("-", "_")
                current = current.setdefault(key, {})
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().replace("-", "_")
        value = value.strip()
        if value.lower() in {"true", "false"}:
            parsed = value.lower() == "true"
        elif (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            parsed = value[1:-1]
        else:
            try:
                parsed = float(value) if "." in value else int(value)
            except Exception:
                parsed = value
        current[key] = parsed
    return root


def _read_config_toml_file(path):
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as handle:
        data = handle.read()
    if tomllib is not None:
        return tomllib.loads(data.decode("utf-8", errors="replace") or "")
    return _fallback_parse_toml(data.decode("utf-8", errors="replace"))


def runtime_config_snapshot(force=False):
    path = str(CONFIG_TOML_FILE)
    try:
        mtime = os.path.getmtime(path) if os.path.exists(path) else None
    except Exception:
        mtime = None
    cached = runtime_config_cache
    if not force and cached.get("path") == path and cached.get("mtime") == mtime and isinstance(cached.get("data"), dict):
        return cached.get("data")
    try:
        loaded = _read_config_toml_file(path)
        merged = _deep_merge_config(DEFAULT_RUNTIME_CONFIG, loaded)
        runtime_config_cache.update({"path": path, "mtime": mtime, "data": merged, "error": ""})
        return merged
    except Exception as exc:
        fallback = _deep_copy_jsonish(DEFAULT_RUNTIME_CONFIG)
        runtime_config_cache.update({"path": path, "mtime": mtime, "data": fallback, "error": str(exc)})
        return fallback


def runtime_config_get(section, key, default=None):
    current = runtime_config_snapshot()
    node = current
    for part in str(section or "").split("."):
        if not part:
            continue
        if not isinstance(node, dict):
            return default
        node = node.get(part) if part in node else node.get(part.replace("-", "_"))
    if isinstance(node, dict):
        return node.get(key) if key in node else node.get(str(key or "").replace("-", "_"), default)
    return default


def config_int(section, key, default=0, minimum=None, maximum=None):
    try:
        value = int(runtime_config_get(section, key, default))
    except Exception:
        value = int(default or 0)
    if minimum is not None:
        value = max(int(minimum), value)
    if maximum is not None:
        value = min(int(maximum), value)
    return value


def config_float(section, key, default=0.0, minimum=None, maximum=None):
    try:
        value = float(runtime_config_get(section, key, default))
    except Exception:
        value = float(default or 0.0)
    if minimum is not None:
        value = max(float(minimum), value)
    if maximum is not None:
        value = min(float(maximum), value)
    return value


def config_str(section, key, default=""):
    return str(runtime_config_get(section, key, default))


def config_bool(section, key, default=False):
    value = runtime_config_get(section, key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)

def resource_color_config():
    raw = runtime_config_get("ui", "resource_colors_json", "{}")
    try:
        parsed = json.loads(str(raw or "{}"))
    except Exception:
        parsed = {}
    return {
        str(key): str(value)
        for key, value in (parsed.items() if isinstance(parsed, dict) else [])
        if str(key).strip() and re.fullmatch(r"#[0-9a-fA-F]{6}", str(value or "").strip())
    }


def write_resource_color_config(colors):
    clean = {
        str(key): str(value).lower()
        for key, value in (colors.items() if isinstance(colors, dict) else [])
        if str(key).strip() and re.fullmatch(r"#[0-9a-fA-F]{6}", str(value or "").strip())
    }
    ensure_runtime_config_file()
    with open(CONFIG_TOML_FILE, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    encoded = _toml_scalar(json.dumps(clean, separators=(",", ":"), sort_keys=True))
    pattern = r"(?m)^\s*resource_colors_json\s*=\s*.*$"
    if re.search(pattern, text):
        updated = re.sub(pattern, f"resource_colors_json = {encoded}", text)
    elif re.search(r"(?m)^\s*\[ui\]\s*$", text):
        updated = re.sub(
            r"(?m)^(\s*\[ui\]\s*)$",
            rf"\1\nresource_colors_json = {encoded}",
            text,
            count=1,
        )
    else:
        updated = text.rstrip() + f"\n\n[ui]\nresource_colors_json = {encoded}\n"
    with open(CONFIG_TOML_FILE, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(updated)
    runtime_config_snapshot(force=True)
    return resource_color_config()


def _toml_scalar(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return json.dumps(str(value))


def _toml_section_lines(section, values):
    lines = [f"[{section}]"]
    for key, value in values.items():
        if isinstance(value, dict):
            continue
        lines.append(f"{key} = {_toml_scalar(value)}")
    lines.append("")
    for key, value in values.items():
        if isinstance(value, dict):
            lines.extend(_toml_section_lines(f"{section}.{key}", value))
    return lines


def default_runtime_config_toml():
    lines = [
        "# Club-3090 control runtime configuration.",
        "# Missing keys fall back to the built-in defaults from the installed script.",
        "",
    ]
    for section, values in DEFAULT_RUNTIME_CONFIG.items():
        if isinstance(values, dict):
            lines.extend(_toml_section_lines(section, values))
    return "\n".join(lines).rstrip() + "\n"


def normalize_runtime_config_file_defaults():
    try:
        if not os.path.exists(CONFIG_TOML_FILE):
            return False
        with open(CONFIG_TOML_FILE, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        def replace_section_numeric_floor(source, section, key, minimum):
            pattern = (
                r"(?ms)(^\s*\[" + re.escape(section) + r"\]\s*$"
                r"(?:(?!^\s*\[).)*?^\s*" + re.escape(key) + r"\s*=\s*)"
                r"([-+]?\d+(?:\.\d+)?)"
                r"(\s*(?:#.*)?$)"
            )

            def repl(match):
                try:
                    value = float(match.group(2))
                except Exception:
                    return match.group(0)
                if value >= float(minimum):
                    return match.group(0)
                return f"{match.group(1)}{int(minimum)}{match.group(3)}"

            return re.sub(pattern, repl, source)

        updated = re.sub(
            r"(^\s*history_status_max_points\s*=\s*)2880(\s*$)",
            r"\g<1>480\2",
            text,
            flags=re.MULTILINE,
        )
        updated = re.sub(
            r"(?ms)(^\s*\[profiles\.benchmark_ready\]\s*$(?:(?!^\s*\[).)*?^\s*gpu_active\s*=\s*)250(\s*(?:#.*)?$)",
            r"\g<1>220\2",
            updated,
        )
        updated = replace_section_numeric_floor(
            updated,
            "benchmarks.thermal",
            "thermal_grace_seconds",
            600,
        )
        updated = replace_section_numeric_floor(
            updated,
            "benchmarks.thermal",
            "thermal_sustained_seconds",
            1800,
        )
        if updated == text:
            return False
        with open(CONFIG_TOML_FILE, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)
        return True
    except Exception:
        return False


def ensure_runtime_config_file():
    try:
        if os.path.exists(CONFIG_TOML_FILE):
            if normalize_runtime_config_file_defaults():
                runtime_config_snapshot(force=True)
                return True
            return False
        os.makedirs(os.path.dirname(CONFIG_TOML_FILE), exist_ok=True)
        with open(CONFIG_TOML_FILE, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(default_runtime_config_toml())
        runtime_config_snapshot(force=True)
        return True
    except Exception:
        return False


METRICS_HISTORY_RETENTION_SECONDS = max(86400, config_int("metrics", "history_retention_seconds", _env_int("CLUB3090_METRICS_HISTORY_RETENTION_SECONDS", 86400)))
METRICS_HISTORY_MAX_POINTS = max(240, min(172800, config_int("metrics", "history_max_points", _env_int("CLUB3090_METRICS_HISTORY_MAX_POINTS", str(METRICS_HISTORY_RETENTION_SECONDS)))))
METRICS_HISTORY_STATUS_MAX_POINTS = max(240, min(480, config_int("metrics", "history_status_max_points", _env_int("CLUB3090_METRICS_HISTORY_STATUS_MAX_POINTS", 480))))
METRICS_HISTORY_PERSIST_INTERVAL_SECONDS = max(5, config_int("metrics", "history_persist_interval_seconds", _env_int("CLUB3090_METRICS_HISTORY_PERSIST_INTERVAL_SECONDS", 30)))
CUSTOM_PRESETS_FILE = os.path.join(CONTROL_DIR, "custom_presets.json")
CUSTOM_MODELS_FILE = os.path.join(CONTROL_DIR, "custom_models.json")
CUSTOM_MODELS_DIR = os.path.join(CONTROL_DIR, "custom-models")
INSTANCES_CONFIG_FILE = os.path.join(CONTROL_DIR, "instances.json")
SERVER_CONFIG_FILE = os.path.join(CONTROL_DIR, "server_config.json")
USERS_FILE = os.path.join(CONTROL_DIR, "users.json")
GROUPS_FILE = os.path.join(CONTROL_DIR, "groups.json")
CHAT_CONVERSATIONS_DIR = os.path.join(CONTROL_DIR, "conversations")
CHAT_STATE_FILE = os.path.join(CHAT_CONVERSATIONS_DIR, "state.json")
CHAT_ATTACHMENTS_DIR = os.path.join(CHAT_CONVERSATIONS_DIR, "attachments")
CHAT_STATE_BACKUP_DIR = os.path.join(CHAT_CONVERSATIONS_DIR, "backups")
CHAT_STREAM_STATE_DIR = os.path.join(CHAT_CONVERSATIONS_DIR, "stream-state")
CODE_SYNTAX_CONFIG_FILE = os.path.join(CONTROL_DIR, "code_syntax.json")
CODE_SYNTAX_CONFIG_GZIP_BASE64 = ""  # Injected by build.py for shipped outputs.
MCP_PROTOCOL_VERSION = "2025-03-26"
LOCAL_API_TOKEN_FILE = os.path.join(CONTROL_DIR, "local_api_token")
INSTANCES_DIR = os.path.join(CONTROL_DIR, "instances")
GENERATED_COMPOSE_OVERRIDES_DIR = os.path.join(CONTROL_DIR, "compose-overrides")
INSTANCE_RUNTIME_CACHE_HOST_ROOT = os.path.join(CLUB3090_DIR, "models-cache", ".runtime", "instances")
RUNTIME_INVENTORY_FILE = os.path.join(CONTROL_DIR, "runtime_inventory.json")
SWITCH_FAILURE_FILE = os.path.join(CONTROL_DIR, "switch_failure.json")
DEFAULT_MODE = os.environ.get("DEFAULT_MODE", "vllm/default")
ADMIN_PORT = config_int("network", "admin_port", _env_int("CLUB3090_ADMIN_PORT", 8008))
PROXY_PORT = config_int("network", "proxy_port", _env_int("CLUB3090_PROXY_PORT", 8009))
LOCAL_API_PORT = config_int("network", "local_api_port", _env_int("CLUB3090_LOCAL_API_PORT", 10881))
ADMIN_BIND_HOST = _env_str("CLUB3090_ADMIN_BIND_HOST", config_str("network", "admin_bind_host", "0.0.0.0"))
PROXY_BIND_HOST = _env_str("CLUB3090_PROXY_BIND_HOST", config_str("network", "proxy_bind_host", "0.0.0.0"))
ADMIN_BIND_PORT = int(os.environ.get("CLUB3090_ADMIN_BIND_PORT", str(ADMIN_PORT)))
PROXY_BIND_PORT = int(os.environ.get("CLUB3090_PROXY_BIND_PORT", str(PROXY_PORT)))
UPDATER_BIND_HOST = config_str("network", "updater_bind_host", _env_str("CLUB3090_UPDATER_BIND_HOST", "127.0.0.1"))
UPDATER_BIND_PORT = config_int("network", "updater_bind_port", _env_int("CLUB3090_UPDATER_BIND_PORT", 18010))
SELF_UPDATE_SECRET_FILE = os.path.join(CONTROL_DIR, "self-update-secret")
LOCAL_INSTALLER_SCRIPT_FILE = os.path.join(CONTROL_DIR, "install-club3090-server.sh")
REMOTE_UPDATE_REPO_URL = os.environ.get(
    "CLUB3090_SELF_UPDATE_REPO_URL",
    "https://github.com/VykosX/club-3090-server.git",
)
REMOTE_UPDATE_REF = os.environ.get("CLUB3090_SELF_UPDATE_REF", "refs/heads/master")
REMOTE_UPDATE_BRANCH = os.environ.get("CLUB3090_SELF_UPDATE_BRANCH", "master")
REMOTE_UPDATE_RAW_URL_TEMPLATE = os.environ.get(
    "CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE",
    "https://raw.githubusercontent.com/VykosX/club-3090-server/{sha}/install-club3090-server.sh",
)
REMOTE_UPDATE_METADATA_URL_TEMPLATE = os.environ.get(
    "CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE",
    "https://raw.githubusercontent.com/VykosX/club-3090-server/{sha}/metadata.json",
)
REMOTE_UPDATE_METADATA_CACHE_TTL_SECONDS = 300
REMOTE_UPDATE_METADATA_CACHE = {}
REMOTE_UPDATE_METADATA_CACHE_AT = 0.0
REMOTE_UPDATE_METADATA_REFRESHING = False
REMOTE_UPDATE_METADATA_LOCK = threading.Lock()
HTTPS_CERT_FILE = os.path.join(CONTROL_DIR, "tls.crt")
HTTPS_KEY_FILE = os.path.join(CONTROL_DIR, "tls.key")
DOCKER_LOGROTATE_FILE = "/etc/logrotate.d/club3090-docker-containers"

MODES = {}
SINGLE_GPU_MODES = ()
DUAL_GPU_MODES = ()
VARIANT_SPECS = {}
VARIANT_BY_ID = {}
VARIANT_BY_TAG = {}
VARIANT_BY_CONTAINER = {}
VARIANT_BY_SERVICE = {}
VARIANT_BY_COMPOSE = {}
MODEL_INDEX = {}
INSTANCE_PORT_BASE = int(os.environ.get("CLUB3090_INSTANCE_PORT_BASE", "8200"))
PAIR_INSTANCE_PORT_BASE = int(os.environ.get("CLUB3090_PAIR_INSTANCE_PORT_BASE", "8300"))
COMPOSE_BIN = os.environ.get("CLUB3090_COMPOSE_BIN", "docker compose")
GLOBAL_VLLM_CACHE_CONTAINER_ROOT = "/root/.cache/club3090-runtime"
INSTANCE_VLLM_CACHE_CONTAINER_ROOT = "/root/.cache/club3090-instance"

PRESETS = {
    "qwen_chat": {
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 1.5, "repetition_penalty": 1.0,
    },
    "qwen_general": {
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0,
        "presence_penalty": 1.5, "repetition_penalty": 1.0,
    },
    "qwen_coding": {
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 0, "repetition_penalty": 1.0,
    },
    "qwen_coding_fast": {
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0.8, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 0, "repetition_penalty": 1.0,
    },
    "qwen_thinking": {
        "chat_template_kwargs": {"enable_thinking": True},
        "temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 1.5,
    },
    "qwen_preserve_thinking": {
        "chat_template_kwargs": {"enable_thinking": True, "preserve_thinking": True},
        "temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 1.5,
    },
    "gemma_coding": {
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 1.0, "top_p": 0.95, "top_k": 64, "min_p": 0,
        "presence_penalty": 0, "repetition_penalty": 1.0,
    },
    "gemma_thinking": {
        "chat_template_kwargs": {"enable_thinking": True},
        "temperature": 1.0, "top_p": 0.95, "top_k": 64, "min_p": 0,
        "presence_penalty": 0, "repetition_penalty": 1.0,
    },
}

DEFAULT_PRESET_DESCRIPTIONS = {
    "qwen_chat": "Qwen general chat: no thinking, temperature 1.0, top_p 0.95, top_k 20, min_p 0, presence penalty 1.5.",
    "qwen_general": "Qwen lower-temperature general preset: no thinking, temperature 0.7, top_p 0.8, top_k 20, presence penalty 1.5.",
    "qwen_coding": "Qwen coding-tuned sampling: no thinking, temperature 0.6, top_p 0.95, no presence penalty.",
    "qwen_coding_fast": "Qwen faster/looser coding preset: no thinking, temperature 0.8, top_p 0.95, no presence penalty.",
    "qwen_thinking": "Qwen thinking enabled with temperature 1.0, top_p 0.95, presence penalty 1.5.",
    "qwen_preserve_thinking": "Qwen thinking enabled and preserved in output with the same base sampling parameters.",
    "gemma_coding": "Gemma coding preset from Unsloth guidance: no thinking, temperature 1.0, top_p 0.95, top_k 64.",
    "gemma_thinking": "Gemma thinking preset from Unsloth guidance: enable_thinking true, temperature 1.0, top_p 0.95, top_k 64.",
}
LENGTH_PREFIXES = {"short-": 4096, "concise-": 512}
HOP_HEADERS = {"connection","keep-alive","proxy-authenticate","proxy-authorization","te","trailers","transfer-encoding","upgrade","content-length","host"}

switch_lock = threading.Lock()
proxy_swap_lock = threading.Lock()
metrics_lock = threading.Lock()
preset_tps_stats_lock = threading.Lock()
system_metric_peaks_lock = threading.Lock()
gpu_last_seen_lock = threading.Lock()
metrics_history_lock = threading.Lock()
chat_stream_state_lock = threading.Lock()
admin_chat_stream_control_lock = threading.Lock()
runtime_ready_probe_cache = {}
runtime_bootstrap_marker_cache = {}
docker_log_path_cache = {}
chat_audit_context = threading.local()
auth_cache = {}
auth_failure_cache = {}
auth_inflight_locks = {}
auth_lock = threading.Lock()
AUTH_CACHE_SECONDS = 120
AUTH_FAILURE_CACHE_SECONDS = int(os.environ.get("CLUB3090_ADMIN_AUTH_FAILURE_CACHE_SECONDS", "30"))
AUTH_CACHE_MAX_ENTRIES = int(os.environ.get("CLUB3090_ADMIN_AUTH_CACHE_MAX_ENTRIES", "256"))
ADMIN_SESSION_COOKIE_NAME = "club3090_admin_session"
ADMIN_SESSION_TTL_SECONDS = int(os.environ.get("CLUB3090_ADMIN_SESSION_TTL_SECONDS", "86400"))
ADMIN_SESSIONS_FILE = os.path.join(CONTROL_DIR, "admin_sessions.json")
ADMIN_AUTH_DENIAL_LOG_WINDOW_SECONDS = int(os.environ.get("CLUB3090_ADMIN_AUTH_DENIAL_LOG_WINDOW_SECONDS", "30"))
startup_time = time.time()
recent_requests = collections.deque(maxlen=120)
series_points = collections.deque(maxlen=METRICS_HISTORY_MAX_POINTS)
request_queue = collections.deque(maxlen=50)
metrics = {"total_requests":0,"active_requests":0,"completed_requests":0,"failed_requests":0,"streaming_requests":0,"queued_requests":0,"cold_starts":0,"failovers":0,"last_latency_s":None,"last_ttft_s":None,"last_tokens_per_second":None,"last_estimated_tokens":None,"last_preset":None,"last_path":None,"last_status":None}
LOG_BOOTSTRAP_MARKER = os.environ.get("CLUB3090_LOG_BOOTSTRAP_MARKER", "Application startup complete")
LOG_TAIL_MAX_BYTES = int(os.environ.get("CLUB3090_LOG_TAIL_MAX_BYTES", "102400"))
LOG_INITIAL_TAIL_LINES = int(os.environ.get("CLUB3090_LOG_INITIAL_TAIL_LINES", "250"))
LOG_INITIAL_SNAPSHOT_TIMEOUT_SECONDS = float(os.environ.get("CLUB3090_LOG_INITIAL_TIMEOUT_SECONDS", "15"))
DOCKER_LOG_RETENTION_DAYS = int(os.environ.get("CLUB3090_DOCKER_LOG_RETENTION_DAYS", "7"))
DOCKER_LOGROTATE_REFRESH_SECONDS = int(os.environ.get("CLUB3090_DOCKER_LOGROTATE_REFRESH_SECONDS", "21600"))
runtime_log_watchers = {}
runtime_log_watchers_lock = threading.Lock()
admin_stream_registry = {}
admin_stream_registry_lock = threading.Lock()
latest_gpu_rows = []
latest_system_snapshot = {"memory": {}, "cpu": {"cores": []}, "disks": [], "network": {}, "info": {}}
latest_metrics_collected_at = 0.0
gpu_session_peaks = {}
system_metric_peaks_cache = None
gpu_last_seen_cache = {"value": None, "time": 0.0, "write_time": 0.0}
metrics_history_cache = {"loaded": False, "write_time": 0.0}
disk_stats_cache = {"value": [], "time": 0.0}
system_info_cache = {"value": {}, "time": 0.0}
status_snapshot_cache = {}
status_snapshot_updated_at = 0.0
status_snapshot_refresh_started_at = 0.0
status_lightweight_cache = {}
status_lightweight_updated_at = 0.0
status_snapshot_lock = threading.Lock()
status_snapshot_refresh_lock = threading.Lock()
slow_cache_lock = threading.Lock()
upstream_services_cache = {"value": [], "time": 0.0}
docker_names_cache = {
    "running": {"value": [], "time": 0.0},
    "all": {"value": [], "time": 0.0},
}
service_status_cache = {}
gpu_count_cache = {"value": 0, "time": 0.0}
compose_metadata_cache = {}
runtime_log_metrics_cache = {}
runtime_log_metric_memory = {}
nvlink_status_cache = {"value": {}, "time": 0.0}
tailscale_access_hint_cache = {"value": {}, "time": 0.0}
target_request_metrics = {}
admin_chat_stream_states = {}
admin_chat_stream_controls = {}
runtime_inventory_lock = threading.Lock()
runtime_inventory_cache = {}
storage_browser_size_lock = threading.Lock()
storage_browser_size_cache = {}
storage_browser_size_pending = set()
storage_browser_file_session_lock = threading.Lock()
storage_browser_file_sessions = {}
storage_browser_download_job_lock = threading.Lock()
storage_browser_download_jobs = {}
STORAGE_BROWSER_CHUNK_BYTES = 1024 * 1024
STORAGE_BROWSER_MAX_FILE_BYTES = 1024 * 1024 * 1024
runtime_inventory_built_at = 0.0
model_install_job_lock = threading.RLock()
admin_session_lock = threading.Lock()
admin_sessions = {}
admin_sessions_loaded = False
admin_auth_denial_lock = threading.Lock()
admin_auth_denial_state = {}
audit_rate_limit_lock = threading.Lock()
audit_rate_limit_state = {}
AUDIT_RATE_LIMIT_WINDOWS = {
    "admin_auth_denied": 5,
    "local_api_denied": 5,
    "proxy_auth_denied": 5,
}
AUDIT_TEXT_FILTERED_EVENTS = {
    "admin_auth_denied",
}
model_install_job = {
    "active": False,
    "status": "idle",
    "job_id": "",
    "model_id": "",
    "variant_id": "",
    "command": "",
    "started_at": 0,
    "finished_at": 0,
    "return_code": None,
    "summary": "",
    "inventory_rebuild_ok": None,
}
MODEL_INSTALL_JOB_HISTORY_LIMIT = 12
model_install_jobs = {}
model_install_job_order = collections.deque(maxlen=MODEL_INSTALL_JOB_HISTORY_LIMIT)
model_install_processes = {}
model_install_cleanup_targets = {}
model_install_process_lock = threading.Lock()
model_install_download_lock_guard = threading.Lock()
model_install_download_locks = {}
custom_model_job_lock = threading.Lock()
custom_model_job = {
    "active": False,
    "status": "idle",
    "action": "",
    "model_id": "",
    "selector": "",
    "slug": "",
    "command": "",
    "started_at": 0,
    "finished_at": 0,
    "return_code": None,
    "summary": "",
    "inventory_rebuild_ok": None,
}
switch_job_lock = threading.Lock()
switch_job = {
    "active": False,
    "status": "idle",
    "mode": "",
    "target": "",
    "started_at": 0,
    "finished_at": 0,
    "error": "",
}
debug_shell_lock = threading.Lock()
debug_shell_session = {
    "process": None,
    "master_fd": None,
    "slave_fd": None,
    "session_id": "",
    "started_at": 0,
    "cwd_hint": CLUB3090_DIR,
}

POWER_IDLE_AFTER_SECONDS = config_int("power", "idle_after_seconds", _env_int("CLUB3090_POWER_IDLE_AFTER_SECONDS", 600))
CONTAINER_STOP_AFTER_SECONDS = config_int("power", "container_stop_after_seconds", _env_int("CLUB3090_CONTAINER_STOP_AFTER_SECONDS", 3600))
CONTAINER_AUTO_STOP_ENABLED = False
GPU_ACTIVE_POWER_LIMIT_W = config_int("power", "gpu_active_power_limit_w", _env_int("CLUB3090_GPU_ACTIVE_POWER_LIMIT_W", 280))
GPU_IDLE_POWER_LIMIT_W = config_int("power", "gpu_idle_power_limit_w", _env_int("CLUB3090_GPU_IDLE_POWER_LIMIT_W", 120))
GPU_IDLE_LOCK_CLOCKS = config_str("power", "gpu_idle_lock_clocks", _env_str("CLUB3090_GPU_IDLE_LOCK_CLOCKS", "210,900"))
GPU_ACTIVE_LOCK_CLOCKS = config_str("power", "gpu_active_lock_clocks", _env_str("CLUB3090_GPU_ACTIVE_LOCK_CLOCKS", ""))
CPU_ACTIVE_GOVERNOR = config_str("power", "cpu_active_governor", _env_str("CLUB3090_CPU_ACTIVE_GOVERNOR", "performance"))
CPU_IDLE_GOVERNOR = config_str("power", "cpu_idle_governor", _env_str("CLUB3090_CPU_IDLE_GOVERNOR", "powersave"))
FAN_CURVE = [(30, 35), (35, 40), (40, 45), (45, 55), (50, 65), (55, 75), (60, 85), (65, 95)]
FAN_MAX_SPEED = config_int("fans", "max_speed", _env_int("CLUB3090_FAN_MAX_SPEED", 100), minimum=1, maximum=100)
FAN_MIN_SAFE_SPEED = config_int("fans", "min_safe_speed", _env_int("CLUB3090_FAN_MIN_SAFE_SPEED", 35), minimum=1, maximum=100)
WOL_MAC = os.environ.get("CLUB3090_WOL_MAC", "")
WOL_BROADCAST = os.environ.get("CLUB3090_WOL_BROADCAST", "255.255.255.255")
PERFORMANCE_PROFILES = {
    "eco": {"gpu_active": config_int("profiles.eco", "gpu_active", 240), "gpu_idle": config_int("profiles.eco", "gpu_idle", 90), "idle_clocks": config_str("profiles.eco", "idle_clocks", "210,705"), "cpu_active": config_str("profiles.eco", "cpu_active", "schedutil"), "cpu_idle": config_str("profiles.eco", "cpu_idle", "powersave"), "idle_after": config_int("profiles.eco", "idle_after", 300), "stop_after": config_int("profiles.eco", "stop_after", 1800)},
    "balanced": {"gpu_active": config_int("profiles.balanced", "gpu_active", GPU_ACTIVE_POWER_LIMIT_W), "gpu_idle": config_int("profiles.balanced", "gpu_idle", GPU_IDLE_POWER_LIMIT_W), "idle_clocks": config_str("profiles.balanced", "idle_clocks", GPU_IDLE_LOCK_CLOCKS), "cpu_active": config_str("profiles.balanced", "cpu_active", CPU_ACTIVE_GOVERNOR), "cpu_idle": config_str("profiles.balanced", "cpu_idle", CPU_IDLE_GOVERNOR), "idle_after": config_int("profiles.balanced", "idle_after", POWER_IDLE_AFTER_SECONDS), "stop_after": config_int("profiles.balanced", "stop_after", CONTAINER_STOP_AFTER_SECONDS)},
    "fast": {"gpu_active": config_int("profiles.fast", "gpu_active", 300), "gpu_idle": config_int("profiles.fast", "gpu_idle", 120), "idle_clocks": config_str("profiles.fast", "idle_clocks", ""), "cpu_active": config_str("profiles.fast", "cpu_active", "schedutil"), "cpu_idle": config_str("profiles.fast", "cpu_idle", "powersave"), "idle_after": config_int("profiles.fast", "idle_after", 900), "stop_after": config_int("profiles.fast", "stop_after", 3600)},
    "benchmark-ready": {"gpu_active": config_int("profiles.benchmark_ready", "gpu_active", 220), "gpu_idle": config_int("profiles.benchmark_ready", "gpu_idle", 120), "idle_clocks": config_str("profiles.benchmark_ready", "idle_clocks", ""), "cpu_active": config_str("profiles.benchmark_ready", "cpu_active", "schedutil"), "cpu_idle": config_str("profiles.benchmark_ready", "cpu_idle", "powersave"), "idle_after": config_int("profiles.benchmark_ready", "idle_after", 1800), "stop_after": config_int("profiles.benchmark_ready", "stop_after", 7200)},
    "benchmark-safe": {"gpu_active": config_int("profiles.benchmark_safe", "gpu_active", 200), "gpu_idle": config_int("profiles.benchmark_safe", "gpu_idle", 120), "idle_clocks": config_str("profiles.benchmark_safe", "idle_clocks", ""), "cpu_active": config_str("profiles.benchmark_safe", "cpu_active", "schedutil"), "cpu_idle": config_str("profiles.benchmark_safe", "cpu_idle", "powersave"), "idle_after": config_int("profiles.benchmark_safe", "idle_after", 1800), "stop_after": config_int("profiles.benchmark_safe", "stop_after", 7200)},
    "turbo": {"gpu_active": config_int("profiles.turbo", "gpu_active", 350), "gpu_idle": config_int("profiles.turbo", "gpu_idle", 160), "idle_clocks": config_str("profiles.turbo", "idle_clocks", ""), "cpu_active": config_str("profiles.turbo", "cpu_active", "performance"), "cpu_idle": config_str("profiles.turbo", "cpu_idle", "schedutil"), "idle_after": config_int("profiles.turbo", "idle_after", 1800), "stop_after": config_int("profiles.turbo", "stop_after", 7200)},
}
current_profile = "balanced"
last_inference_time = time.time()
last_request_finished_at = time.time()
power_optimizations_enabled = True
fan_manual_override = False
fan_curve_pause_until = 0.0
power_state = {"gpu":"unknown", "cpu":"unknown", "container":"running", "fans":"auto", "power_optimizations":"enabled", "last_action":"startup", "last_error":""}
cooling_scope_instance_id = "GLOBAL"
fan_curve_resume_token = 0


def _chat_stream_state_path(conversation_id):
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "", str(conversation_id or "").strip())
    if not safe_id:
        raise ValueError("Conversation id is required.")
    return os.path.join(CHAT_STREAM_STATE_DIR, f"{safe_id}.json")


def _sanitize_chat_stream_state_payload(state):
    row = state if isinstance(state, dict) else {}
    return {
        "conversation_id": str(row.get("conversation_id") or "").strip(),
        "status": str(row.get("status") or "idle").strip() or "idle",
        "message": str(row.get("message") or ""),
        "error": str(row.get("error") or ""),
        "instance_id": str(row.get("instance_id") or "").strip(),
        "mode": str(row.get("mode") or "").strip(),
        "model": str(row.get("model") or "").strip(),
        "assistant_text": str(row.get("assistant_text") or ""),
        "reasoning_text": str(row.get("reasoning_text") or ""),
        "usage": dict(row.get("usage") or {}) if isinstance(row.get("usage"), dict) else {},
        "generation_tps": row.get("generation_tps"),
        "prompt_tps": row.get("prompt_tps"),
        "gpu_kv_cache_usage_pct": row.get("gpu_kv_cache_usage_pct"),
        "cpu_kv_cache_usage_pct": row.get("cpu_kv_cache_usage_pct"),
        "prefix_cache_hit_rate_pct": row.get("prefix_cache_hit_rate_pct"),
        "speculative": dict(row.get("speculative") or {}) if isinstance(row.get("speculative"), dict) else {},
        "ttft_s": row.get("ttft_s"),
        "latency_s": row.get("latency_s"),
        "started_at": int(row.get("started_at") or 0),
        "updated_at": int(row.get("updated_at") or 0),
        "finished_at": int(row.get("finished_at") or 0),
    }


def refresh_power_config_globals():
    global POWER_IDLE_AFTER_SECONDS, CONTAINER_STOP_AFTER_SECONDS
    global GPU_ACTIVE_POWER_LIMIT_W, GPU_IDLE_POWER_LIMIT_W, GPU_IDLE_LOCK_CLOCKS, GPU_ACTIVE_LOCK_CLOCKS
    global CPU_ACTIVE_GOVERNOR, CPU_IDLE_GOVERNOR, FAN_MAX_SPEED, FAN_MIN_SAFE_SPEED, PERFORMANCE_PROFILES
    POWER_IDLE_AFTER_SECONDS = config_int("power", "idle_after_seconds", POWER_IDLE_AFTER_SECONDS)
    CONTAINER_STOP_AFTER_SECONDS = config_int("power", "container_stop_after_seconds", CONTAINER_STOP_AFTER_SECONDS)
    GPU_ACTIVE_POWER_LIMIT_W = config_int("power", "gpu_active_power_limit_w", GPU_ACTIVE_POWER_LIMIT_W)
    GPU_IDLE_POWER_LIMIT_W = config_int("power", "gpu_idle_power_limit_w", GPU_IDLE_POWER_LIMIT_W)
    GPU_IDLE_LOCK_CLOCKS = config_str("power", "gpu_idle_lock_clocks", GPU_IDLE_LOCK_CLOCKS)
    GPU_ACTIVE_LOCK_CLOCKS = config_str("power", "gpu_active_lock_clocks", GPU_ACTIVE_LOCK_CLOCKS)
    CPU_ACTIVE_GOVERNOR = config_str("power", "cpu_active_governor", CPU_ACTIVE_GOVERNOR)
    CPU_IDLE_GOVERNOR = config_str("power", "cpu_idle_governor", CPU_IDLE_GOVERNOR)
    FAN_MAX_SPEED = config_int("fans", "max_speed", FAN_MAX_SPEED, minimum=1, maximum=100)
    FAN_MIN_SAFE_SPEED = config_int("fans", "min_safe_speed", FAN_MIN_SAFE_SPEED, minimum=1, maximum=100)
    PERFORMANCE_PROFILES = {
        "eco": {"gpu_active": config_int("profiles.eco", "gpu_active", 240), "gpu_idle": config_int("profiles.eco", "gpu_idle", 90), "idle_clocks": config_str("profiles.eco", "idle_clocks", "210,705"), "cpu_active": config_str("profiles.eco", "cpu_active", "schedutil"), "cpu_idle": config_str("profiles.eco", "cpu_idle", "powersave"), "idle_after": config_int("profiles.eco", "idle_after", 300), "stop_after": config_int("profiles.eco", "stop_after", 1800)},
        "balanced": {"gpu_active": config_int("profiles.balanced", "gpu_active", GPU_ACTIVE_POWER_LIMIT_W), "gpu_idle": config_int("profiles.balanced", "gpu_idle", GPU_IDLE_POWER_LIMIT_W), "idle_clocks": config_str("profiles.balanced", "idle_clocks", GPU_IDLE_LOCK_CLOCKS), "cpu_active": config_str("profiles.balanced", "cpu_active", CPU_ACTIVE_GOVERNOR), "cpu_idle": config_str("profiles.balanced", "cpu_idle", CPU_IDLE_GOVERNOR), "idle_after": config_int("profiles.balanced", "idle_after", POWER_IDLE_AFTER_SECONDS), "stop_after": config_int("profiles.balanced", "stop_after", CONTAINER_STOP_AFTER_SECONDS)},
        "fast": {"gpu_active": config_int("profiles.fast", "gpu_active", 300), "gpu_idle": config_int("profiles.fast", "gpu_idle", 120), "idle_clocks": config_str("profiles.fast", "idle_clocks", ""), "cpu_active": config_str("profiles.fast", "cpu_active", "schedutil"), "cpu_idle": config_str("profiles.fast", "cpu_idle", "powersave"), "idle_after": config_int("profiles.fast", "idle_after", 900), "stop_after": config_int("profiles.fast", "stop_after", 3600)},
        "benchmark-ready": {"gpu_active": config_int("profiles.benchmark_ready", "gpu_active", 220), "gpu_idle": config_int("profiles.benchmark_ready", "gpu_idle", 120), "idle_clocks": config_str("profiles.benchmark_ready", "idle_clocks", ""), "cpu_active": config_str("profiles.benchmark_ready", "cpu_active", "schedutil"), "cpu_idle": config_str("profiles.benchmark_ready", "cpu_idle", "powersave"), "idle_after": config_int("profiles.benchmark_ready", "idle_after", 1800), "stop_after": config_int("profiles.benchmark_ready", "stop_after", 7200)},
        "benchmark-safe": {"gpu_active": config_int("profiles.benchmark_safe", "gpu_active", 200), "gpu_idle": config_int("profiles.benchmark_safe", "gpu_idle", 120), "idle_clocks": config_str("profiles.benchmark_safe", "idle_clocks", ""), "cpu_active": config_str("profiles.benchmark_safe", "cpu_active", "schedutil"), "cpu_idle": config_str("profiles.benchmark_safe", "cpu_idle", "powersave"), "idle_after": config_int("profiles.benchmark_safe", "idle_after", 1800), "stop_after": config_int("profiles.benchmark_safe", "stop_after", 7200)},
        "turbo": {"gpu_active": config_int("profiles.turbo", "gpu_active", 350), "gpu_idle": config_int("profiles.turbo", "gpu_idle", 160), "idle_clocks": config_str("profiles.turbo", "idle_clocks", ""), "cpu_active": config_str("profiles.turbo", "cpu_active", "performance"), "cpu_idle": config_str("profiles.turbo", "cpu_idle", "schedutil"), "idle_after": config_int("profiles.turbo", "idle_after", 1800), "stop_after": config_int("profiles.turbo", "stop_after", 7200)},
    }
    active_profile = PERFORMANCE_PROFILES.get(str(current_profile or "").strip().lower())
    if active_profile:
        GPU_ACTIVE_POWER_LIMIT_W = int(active_profile["gpu_active"])
        GPU_IDLE_POWER_LIMIT_W = int(active_profile["gpu_idle"])
        GPU_IDLE_LOCK_CLOCKS = str(active_profile["idle_clocks"])
        CPU_ACTIVE_GOVERNOR = str(active_profile["cpu_active"])
        CPU_IDLE_GOVERNOR = str(active_profile["cpu_idle"])
        POWER_IDLE_AFTER_SECONDS = int(active_profile["idle_after"])
        CONTAINER_STOP_AFTER_SECONDS = int(active_profile["stop_after"])
    return PERFORMANCE_PROFILES


def begin_admin_chat_stream_state(conversation_id, **fields):
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return {}
    now_ms = int(time.time() * 1000)
    state = _sanitize_chat_stream_state_payload({
        "conversation_id": conversation_id,
        "status": "streaming",
        "started_at": now_ms,
        "updated_at": now_ms,
        **fields,
    })
    with chat_stream_state_lock:
        admin_chat_stream_states[conversation_id] = state
    try:
        write_json_file(_chat_stream_state_path(conversation_id), state)
    except Exception:
        pass
    return dict(state)


def update_admin_chat_stream_state(conversation_id, **fields):
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return {}
    now_ms = int(time.time() * 1000)
    with chat_stream_state_lock:
        current = dict(admin_chat_stream_states.get(conversation_id) or {"conversation_id": conversation_id, "started_at": now_ms})
        current.update(fields)
        current["conversation_id"] = conversation_id
        current["updated_at"] = now_ms
        if current.get("status") in {"done", "error", "aborted"} and not current.get("finished_at"):
            current["finished_at"] = now_ms
        state = _sanitize_chat_stream_state_payload(current)
        admin_chat_stream_states[conversation_id] = state
    try:
        write_json_file(_chat_stream_state_path(conversation_id), state)
    except Exception:
        pass
    return dict(state)


def read_admin_chat_stream_state(conversation_id):
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return {}
    with chat_stream_state_lock:
        state = admin_chat_stream_states.get(conversation_id)
    if isinstance(state, dict):
        return dict(state)
    try:
        payload = read_json_file(_chat_stream_state_path(conversation_id), {})
        return dict(payload) if isinstance(payload, dict) else {}
    except Exception:
        return {}


def begin_admin_chat_stream_control(conversation_id):
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return {}
    with admin_chat_stream_control_lock:
        control = admin_chat_stream_controls.get(conversation_id) or {}
        control["stop_requested"] = False
        control["cancel"] = None
        control["updated_at"] = int(time.time() * 1000)
        admin_chat_stream_controls[conversation_id] = control
        return dict(control)


def register_admin_chat_stream_cancel(conversation_id, cancel):
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return {}
    with admin_chat_stream_control_lock:
        control = dict(admin_chat_stream_controls.get(conversation_id) or {})
        control["stop_requested"] = bool(control.get("stop_requested"))
        control["cancel"] = cancel if callable(cancel) else None
        control["updated_at"] = int(time.time() * 1000)
        admin_chat_stream_controls[conversation_id] = control
        return {"stop_requested": bool(control.get("stop_requested"))}


def admin_chat_stream_stop_requested(conversation_id):
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return False
    with admin_chat_stream_control_lock:
        control = admin_chat_stream_controls.get(conversation_id) or {}
        return bool(control.get("stop_requested"))


def request_admin_chat_stream_stop(conversation_id):
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return {"ok": False, "error": "Conversation id is required.", "active": False}
    with admin_chat_stream_control_lock:
        control = dict(admin_chat_stream_controls.get(conversation_id) or {})
        cancel = control.get("cancel")
        control["stop_requested"] = True
        control["updated_at"] = int(time.time() * 1000)
        admin_chat_stream_controls[conversation_id] = control
    if callable(cancel):
        try:
            cancel()
        except Exception:
            pass
    return {"ok": True, "conversation_id": conversation_id, "active": callable(cancel)}


def clear_admin_chat_stream_control(conversation_id):
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return
    with admin_chat_stream_control_lock:
        admin_chat_stream_controls.pop(conversation_id, None)


def _apply_profile_globals(profile_name):
    global current_profile, GPU_ACTIVE_POWER_LIMIT_W, GPU_IDLE_POWER_LIMIT_W
    global GPU_IDLE_LOCK_CLOCKS, CPU_ACTIVE_GOVERNOR, CPU_IDLE_GOVERNOR
    global POWER_IDLE_AFTER_SECONDS, CONTAINER_STOP_AFTER_SECONDS
    refresh_power_config_globals()
    name = str(profile_name or "").strip().lower()
    if name in {"standard", "default"}:
        name = "balanced"
    if name not in PERFORMANCE_PROFILES:
        raise ValueError("Invalid performance profile")
    cfg = PERFORMANCE_PROFILES[name]
    GPU_ACTIVE_POWER_LIMIT_W = int(cfg["gpu_active"])
    GPU_IDLE_POWER_LIMIT_W = int(cfg["gpu_idle"])
    GPU_IDLE_LOCK_CLOCKS = str(cfg["idle_clocks"])
    CPU_ACTIVE_GOVERNOR = str(cfg["cpu_active"])
    CPU_IDLE_GOVERNOR = str(cfg["cpu_idle"])
    POWER_IDLE_AFTER_SECONDS = int(cfg["idle_after"])
    CONTAINER_STOP_AFTER_SECONDS = int(cfg["stop_after"])
    current_profile = name
    return name


def ensure_upstream_repo_on_sys_path():
    repo_root = os.path.abspath(str(CLUB3090_DIR or "").strip() or ".")
    if repo_root and os.path.isdir(repo_root) and repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    scripts_dir = os.path.join(repo_root, "scripts")
    scripts_module = sys.modules.get("scripts")
    if scripts_module is not None:
        module_paths = list(getattr(scripts_module, "__path__", []) or [])
        module_file = str(getattr(scripts_module, "__file__", "") or "")
        candidates = module_paths + ([module_file] if module_file else [])
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
            sys.modules.pop("scripts", None)
            scripts_module = None
    if scripts_module is None and os.path.isdir(scripts_dir):
        upstream_scripts = ModuleType("scripts")
        upstream_scripts.__path__ = [scripts_dir]
        upstream_scripts.__package__ = "scripts"
        upstream_scripts.__file__ = os.path.join(scripts_dir, "__init__.py")
        sys.modules["scripts"] = upstream_scripts
    return repo_root


def _cache_slug(text):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "").strip().lower()).strip("-")
    return slug or "variant"


def variant_engine_family(spec):
    row = spec if isinstance(spec, dict) else {}
    engine = str(row.get("engine_family") or row.get("engine") or "").strip().lower().replace("_", "-")
    if engine:
        return "llamacpp" if engine in {"llama-cpp", "ik-llama"} else engine
    compose_rel = str(row.get("compose_rel_path") or "").replace("\\", "/").lower()
    if "/vllm/" in compose_rel:
        return "vllm"
    if "/llama-cpp/" in compose_rel or "/llamacpp/" in compose_rel or "/ik-llama/" in compose_rel or "/beellama/" in compose_rel:
        return "llamacpp"
    selector = str(row.get("selector") or row.get("upstream_tag") or row.get("registry_key") or "").strip().lower()
    if selector.startswith("vllm/"):
        return "vllm"
    if selector.startswith("llamacpp/") or selector.startswith("llama-cpp/") or selector.startswith("ik-llama/") or selector.startswith("beellama/"):
        return "llamacpp"
    return ""


def variant_runtime_root_dir(spec):
    row = spec if isinstance(spec, dict) else {}
    compose_project_dir = str(row.get("compose_project_dir_abs_path") or "").strip()
    compose_abs_path = str(row.get("compose_abs_path") or "").strip()
    compose_dir = compose_project_dir or (os.path.dirname(compose_abs_path) if compose_abs_path else "")
    if compose_dir:
        normalized = os.path.normpath(compose_dir)
        lowered = normalized.lower()
        marker = f"{os.sep}compose{os.sep}"
        marker_index = lowered.find(marker.lower())
        if marker_index >= 0:
            return normalized[:marker_index]
        marker_tail = f"{os.sep}compose"
        if lowered.endswith(marker_tail.lower()):
            return normalized[: -len(marker_tail)]
        return normalized
    compose_rel = str(row.get("compose_rel_path") or "").replace("\\", "/").strip("/")
    if compose_rel:
        parts = compose_rel.split("/")
        if "compose" in parts:
            return os.path.join(CLUB3090_DIR, *parts[: parts.index("compose")])
    return ""


def variant_uses_vllm(spec):
    return variant_engine_family(spec) == "vllm"


def variant_persistent_cache_host_root(spec):
    row = spec if isinstance(spec, dict) else {}
    if not variant_uses_vllm(row):
        return ""
    runtime_root = variant_runtime_root_dir(row)
    if runtime_root:
        return os.path.normpath(os.path.join(runtime_root, "cache"))
    return os.path.join(
        CONTROL_DIR,
        "runtime-cache",
        _cache_slug(row.get("selector") or row.get("variant_id") or row.get("model_id") or "vllm"),
    )


def ensure_vllm_runtime_cache_dirs(host_root):
    root = os.path.normpath(str(host_root or "").strip())
    if not root:
        return {}
    paths = {
        "root": root,
        "triton": os.path.join(root, "triton"),
        "vllm": os.path.join(root, "vllm"),
        "torch_compile": os.path.join(root, "torch_compile"),
        "torchinductor": os.path.join(root, "torchinductor"),
    }
    for path in paths.values():
        os.makedirs(path, exist_ok=True)
    return paths


def instance_runtime_cache_host_root(instance_id):
    ident = _cache_slug(instance_id or "instance")
    return os.path.normpath(os.path.join(INSTANCE_RUNTIME_CACHE_HOST_ROOT, ident))


def ensure_instance_runtime_cache_link(instance_id):
    ident = _cache_slug(instance_id or "instance")
    if not ident:
        ident = "instance"
    target = instance_runtime_cache_host_root(ident)
    legacy = os.path.join(INSTANCES_DIR, ident, "cache")
    os.makedirs(os.path.dirname(legacy), exist_ok=True)
    os.makedirs(target, exist_ok=True)
    if os.path.islink(legacy):
        current = os.readlink(legacy)
        if os.path.realpath(os.path.abspath(current if os.path.isabs(current) else os.path.join(os.path.dirname(legacy), current))) == os.path.realpath(target):
            return target
        try:
            os.unlink(legacy)
        except Exception:
            return legacy
    if os.path.isdir(legacy):
        legacy_real = os.path.realpath(os.path.abspath(legacy))
        target_real = os.path.realpath(os.path.abspath(target))
        if legacy_real != target_real:
            for name in os.listdir(legacy):
                source = os.path.join(legacy, name)
                dest = os.path.join(target, name)
                try:
                    if os.path.exists(dest) or os.path.islink(dest):
                        continue
                    shutil.move(source, dest)
                except Exception:
                    pass
            try:
                os.rmdir(legacy)
            except Exception:
                pass
    if not os.path.lexists(legacy):
        try:
            os.symlink(target, legacy, target_is_directory=True)
        except Exception:
            os.makedirs(legacy, exist_ok=True)
            return legacy
    return target


def build_variant_compose_override_yaml(spec):
    row = spec if isinstance(spec, dict) else {}
    service_name = str(row.get("service_name") or "").strip()
    if not service_name:
        return ""
    command_text = preset_launch_command_override(row)
    cache_root = ""
    if variant_uses_vllm(row):
        cache_root = variant_persistent_cache_host_root(row)
    if not command_text and not cache_root:
        return ""
    lines = ["services:", f"  {service_name}:"]
    if command_text:
        lines.append("    command: >-")
        for raw_line in command_text.splitlines():
            text = str(raw_line or "").rstrip()
            if text:
                lines.append(f"      {text}")
    if cache_root:
        cache_paths = ensure_vllm_runtime_cache_dirs(cache_root)
        if cache_paths:
            lines.extend(
                [
                    "    environment:",
                    f"      VLLM_CACHE_ROOT: {GLOBAL_VLLM_CACHE_CONTAINER_ROOT}/vllm",
                    f"      TORCHINDUCTOR_CACHE_DIR: {GLOBAL_VLLM_CACHE_CONTAINER_ROOT}/torchinductor",
                    f"      TRITON_CACHE_DIR: {GLOBAL_VLLM_CACHE_CONTAINER_ROOT}/triton",
                    "    volumes:",
                    f"      - {cache_paths['root']}:{GLOBAL_VLLM_CACHE_CONTAINER_ROOT}",
                ]
            )
    return "\n".join(lines) + "\n"


def override_file_for_variant(spec):
    row = spec if isinstance(spec, dict) else {}
    selector = row.get("selector") or row.get("variant_id") or row.get("model_id") or "variant"
    os.makedirs(GENERATED_COMPOSE_OVERRIDES_DIR, exist_ok=True)
    return os.path.join(GENERATED_COMPOSE_OVERRIDES_DIR, f"{_cache_slug(selector)}.cache.override.yml")


def refresh_variant_cache_override(spec):
    row = spec if isinstance(spec, dict) else {}
    override_text = build_variant_compose_override_yaml(row)
    if not override_text:
        override_path = override_file_for_variant(row)
        if override_path and os.path.exists(override_path):
            try:
                os.remove(override_path)
            except Exception:
                pass
        return ""
    override_path = override_file_for_variant(row)
    write_text_atomic_if_changed(override_path, override_text)
    return override_path


def _warmup_model_candidates(spec, ready_url):
    row = spec if isinstance(spec, dict) else {}
    candidates = []
    live_model_names = []

    def add_candidate(value):
        text = str(value or "").strip()
        if text and "${" not in text and text not in candidates:
            candidates.append(text)

    add_candidate(row.get("served_model_name"))
    try:
        req = urllib.request.Request(
            str(ready_url or "").strip(),
            headers={"Accept": "application/json", "User-Agent": "club3090-control/warmup-models"},
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        for row in payload.get("data") or []:
            text = str((row or {}).get("id") or "").strip()
            if text:
                live_model_names.append(text)
                add_candidate(text)
    except Exception:
        pass
    if not live_model_names:
        add_candidate(row.get("model_id"))
        add_candidate(row.get("profile_model_id"))
    return candidates


def maybe_warmup_variant_runtime(spec, ready_url, *, timeout=240):
    row = spec if isinstance(spec, dict) else {}
    target_url = str(ready_url or "").strip()
    if not target_url:
        return {"ok": False, "skipped": True, "reason": "missing-ready-url"}
    model_candidates = _warmup_model_candidates(row, target_url)
    if not model_candidates:
        return {"ok": False, "skipped": True, "reason": "missing-model-name"}
    parsed = urlsplit(target_url)
    warmup_url = f"{parsed.scheme or 'http'}://{parsed.netloc}/v1/chat/completions"
    last_error = ""
    started_at = time.time()
    deadline = started_at + max(5, int(timeout or 240))
    while time.time() < deadline:
        for model_name in model_candidates:
            payload = json.dumps(
                {
                    "model": model_name,
                    "messages": [{"role": "user", "content": "warmup"}],
                    "max_tokens": 32,
                    "stream": False,
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                warmup_url,
                data=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "club3090-control/warmup",
                },
                method="POST",
            )
            remaining = max(1.0, deadline - time.time())
            try:
                with urllib.request.urlopen(req, timeout=min(30.0, remaining)) as response:
                    if 200 <= int(getattr(response, "status", 0) or 0) < 300:
                        duration = round(time.time() - started_at, 2)
                        return {"ok": True, "skipped": False, "model": model_name, "duration_s": duration}
                    last_error = f"HTTP {int(getattr(response, 'status', 0) or 0)}"
            except urllib.error.HTTPError as exc:
                try:
                    body = exc.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    body = ""
                last_error = f"HTTP {int(getattr(exc, 'code', 0) or 0)}" + (f": {body}" if body else "")
            except Exception as exc:
                last_error = str(exc)
        if time.time() < deadline:
            time.sleep(1)
    return {"ok": False, "skipped": False, "reason": last_error or "warmup request failed"}

def log_control(message):
    os.makedirs(CONTROL_DIR, exist_ok=True)
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + str(message).rstrip() + "\n"
    try:
        with open(CONTROL_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def audit_event_category(event_type):
    name = str(event_type or "").strip().lower()
    if name.startswith("proxy_"):
        return "proxy"
    if name.startswith("admin_ui_"):
        return "ui"
    if name.startswith("admin_"):
        return "admin"
    if name.startswith("local_api_"):
        return "automation"
    if name.startswith("user_") or name.startswith("group_"):
        return "access"
    if name.startswith("model_install_") or name.startswith("instance_"):
        return "runtime"
    return "system"


def _audit_rate_limit_key(event_type, fields):
    parts = [str(event_type or "")]
    for key in ("reason", "user", "client", "path", "instance", "action"):
        value = fields.get(key)
        if value not in (None, ""):
            parts.append(f"{key}={value}")
    return "|".join(parts)


def should_emit_audit_event(event_type, fields):
    window = int(AUDIT_RATE_LIMIT_WINDOWS.get(str(event_type or ""), 0) or 0)
    if window <= 0:
        return True
    now = time.time()
    key = _audit_rate_limit_key(event_type, fields)
    with audit_rate_limit_lock:
        last = float(audit_rate_limit_state.get(key, 0.0) or 0.0)
        if last and (now - last) < window:
            return False
        audit_rate_limit_state[key] = now
        stale_before = now - max(window * 2, 30)
        for stale_key, stale_ts in list(audit_rate_limit_state.items()):
            if stale_ts < stale_before:
                audit_rate_limit_state.pop(stale_key, None)
    return True


def should_mirror_audit_text_event(event_type):
    return str(event_type or "").strip().lower() not in AUDIT_TEXT_FILTERED_EVENTS


def log_audit(event_type, **fields):
    os.makedirs(CONTROL_DIR, exist_ok=True)
    if not should_emit_audit_event(event_type, fields):
        return
    entry = {
        "ts": int(time.time()),
        "event": str(event_type),
        "category": audit_event_category(event_type),
    }
    for key, value in fields.items():
        try:
            json.dumps(value)
            entry[key] = value
        except Exception:
            entry[key] = str(value)
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
    except Exception:
        pass
    if should_mirror_audit_text_event(event_type):
        append_audit_text_line(format_audit_text_entry(entry))


def debug_audit(event_type, **fields):
    if not DEBUG_LOGS:
        return
    if (
        getattr(chat_audit_context, "suppress_debug", 0)
        and str(event_type or "").strip().lower().startswith("chat_")
    ):
        return
    safe_fields = {"debug": True, "script_version": SCRIPT_VERSION}
    for key, value in fields.items():
        if value not in (None, ""):
            safe_fields[key] = value
    log_audit(f"debug_{str(event_type or '').strip() or 'event'}", **safe_fields)


class suppress_chat_debug_audit:
    def __enter__(self):
        chat_audit_context.suppress_debug = int(getattr(chat_audit_context, "suppress_debug", 0) or 0) + 1
        return self

    def __exit__(self, exc_type, exc, tb):
        current = int(getattr(chat_audit_context, "suppress_debug", 0) or 0)
        if current <= 1:
            try:
                delattr(chat_audit_context, "suppress_debug")
            except Exception:
                chat_audit_context.suppress_debug = 0
        else:
            chat_audit_context.suppress_debug = current - 1
        return False


def script_user_agent():
    version = str(SCRIPT_VERSION or "").strip() or "unknown"
    return f"club3090-control/{version}"


def append_audit_text_line(text):
    os.makedirs(CONTROL_DIR, exist_ok=True)
    line = str(text or "").rstrip("\n") + "\n"
    try:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def append_debug_text_line(text):
    os.makedirs(CONTROL_DIR, exist_ok=True)
    line = str(text or "").rstrip("\n") + "\n"
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def append_debug_text_chunk(text):
    os.makedirs(CONTROL_DIR, exist_ok=True)
    chunk = str(text or "")
    if not chunk:
        return
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(chunk)
    except Exception:
        pass


def _clear_debug_shell_session_locked():
    process = debug_shell_session.get("process")
    master_fd = debug_shell_session.get("master_fd")
    slave_fd = debug_shell_session.get("slave_fd")
    debug_shell_session.update({
        "process": None,
        "master_fd": None,
        "slave_fd": None,
        "session_id": "",
        "started_at": 0,
        "cwd_hint": CLUB3090_DIR,
    })
    for fd in (master_fd, slave_fd):
        if fd not in (None, ""):
            try:
                os.close(fd)
            except Exception:
                pass
    if process is not None and process.poll() is None:
        try:
            process.terminate()
        except Exception:
            pass


def _debug_shell_reader(process, master_fd, session_id):
    while True:
        if process.poll() is not None:
            break
        try:
            ready, _, _ = select.select([master_fd], [], [], 0.25)
        except Exception:
            break
        if not ready:
            continue
        try:
            chunk = os.read(master_fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        append_debug_text_chunk(chunk.decode("utf-8", errors="replace"))
    rc = None
    try:
        rc = process.wait(timeout=0.2)
    except Exception:
        pass
    append_debug_text_line(f"[debug-shell] session {session_id or 'unknown'} closed (rc={rc if rc is not None else 'unknown'})")
    with debug_shell_lock:
        if str(debug_shell_session.get("session_id") or "") == str(session_id or ""):
            _clear_debug_shell_session_locked()


def ensure_debug_shell_session():
    if pty is None:
        raise RuntimeError("Interactive debug shell support requires a POSIX control host.")
    with debug_shell_lock:
        process = debug_shell_session.get("process")
        if process is not None and process.poll() is None and debug_shell_session.get("master_fd") is not None:
            return dict(debug_shell_session)
        if process is not None:
            _clear_debug_shell_session_locked()
        master_fd, slave_fd = pty.openpty()
        session_id = secrets.token_hex(6)
        process = subprocess.Popen(
            ["bash", "-li"],
            cwd=CLUB3090_DIR,
            env=_repo_subprocess_env(),
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            text=False,
            bufsize=0,
            close_fds=True,
        )
        debug_shell_session.update({
            "process": process,
            "master_fd": master_fd,
            "slave_fd": slave_fd,
            "session_id": session_id,
            "started_at": int(time.time()),
            "cwd_hint": CLUB3090_DIR,
        })
        thread = threading.Thread(
            target=_debug_shell_reader,
            args=(process, master_fd, session_id),
            name=f"club3090-debug-shell-{session_id}",
            daemon=True,
        )
        thread.start()
    append_debug_text_line(f"[debug-shell] interactive session {session_id} started")
    return dict(debug_shell_session)


def _debug_shell_candidate_cwd(command_text, cwd):
    text = str(command_text or "").strip()
    base_dir = str(cwd or CLUB3090_DIR).strip() or CLUB3090_DIR
    if not text or any(token in text for token in ("&&", "||", ";", "|", "`", "$(", "<", ">")):
        return ""
    try:
        parts = shlex.split(text)
    except Exception:
        return ""
    if not parts or parts[0] != "cd" or len(parts) > 2:
        return ""
    destination = parts[1] if len(parts) == 2 else "~"
    if destination == "-":
        return ""
    try:
        expanded = os.path.expanduser(destination)
        target = expanded if os.path.isabs(expanded) else os.path.join(base_dir, expanded)
        resolved = os.path.realpath(os.path.normpath(target))
    except Exception:
        return ""
    return resolved if os.path.isdir(resolved) else ""


def submit_debug_log_command(command):
    text = str(command or "")
    if not text.strip():
        raise ValueError("Debug shell command cannot be empty.")
    session = ensure_debug_shell_session()
    master_fd = session.get("master_fd")
    if master_fd is None:
        raise RuntimeError("Debug shell session is unavailable.")
    os.write(master_fd, (text + "\n").encode("utf-8", errors="replace"))
    next_cwd = _debug_shell_candidate_cwd(text, session.get("cwd_hint") or CLUB3090_DIR)
    if next_cwd:
        with debug_shell_lock:
            if str(debug_shell_session.get("session_id") or "") == str(session.get("session_id") or ""):
                debug_shell_session["cwd_hint"] = next_cwd
    debug_audit("debug_shell_input", source="logs_tab", command_length=len(text))
    return {
        "ok": True,
        "session_id": str(session.get("session_id") or ""),
        "started_at": int(session.get("started_at") or 0),
    }


def debug_shell_current_directory():
    try:
        session = ensure_debug_shell_session()
    except Exception:
        return CLUB3090_DIR
    process = session.get("process")
    pid = int(getattr(process, "pid", 0) or 0)
    if pid > 0:
        try:
            cwd = os.path.realpath(os.readlink(f"/proc/{pid}/cwd"))
            if cwd:
                with debug_shell_lock:
                    if str(debug_shell_session.get("session_id") or "") == str(session.get("session_id") or ""):
                        debug_shell_session["cwd_hint"] = cwd
                return cwd
        except Exception:
            pass
    return str(session.get("cwd_hint") or CLUB3090_DIR)


def build_debug_shell_completion(command, cursor=None):
    text = str(command or "")
    try:
        cursor_pos = int(cursor if cursor is not None else len(text))
    except Exception:
        cursor_pos = len(text)
    cursor_pos = max(0, min(len(text), cursor_pos))
    cwd = debug_shell_current_directory()
    before = text[:cursor_pos]
    line_start = before.rfind("\n") + 1
    line_prefix = before[line_start:]
    match = re.search(r"([^\s]*)$", line_prefix)
    fragment = str(match.group(1) or "") if match else ""
    token_start = cursor_pos - len(fragment)
    payload = {
        "ok": True,
        "cwd": cwd,
        "cursor": cursor_pos,
        "replace_from": token_start,
        "fragment": fragment,
        "suggestion": "",
        "matches": [],
    }
    raw_path = fragment.strip()
    if not raw_path:
        return payload
    quote_prefix = ""
    if raw_path[0] in {"'", '"'}:
        quote_prefix = raw_path[0]
        raw_path = raw_path[1:]
    user_dir_part, base_name = os.path.split(raw_path)
    expanded_dir_part = os.path.expanduser(user_dir_part) if user_dir_part else ""
    if raw_path.startswith("/") or raw_path.startswith("~"):
        search_dir = os.path.realpath(expanded_dir_part or os.path.dirname(os.path.expanduser(raw_path)) or os.path.expanduser("~"))
    else:
        search_dir = os.path.realpath(os.path.join(cwd, expanded_dir_part or "."))
    try:
        names = sorted(os.listdir(search_dir))
    except Exception:
        return payload
    candidates = []
    for name in names:
        if base_name and not str(name).startswith(base_name):
            continue
        full_path = os.path.join(search_dir, name)
        suffix = "/" if os.path.isdir(full_path) else ""
        display = f"{user_dir_part.rstrip('/') + '/' if user_dir_part else ''}{name}{suffix}"
        candidates.append(f"{quote_prefix}{display}")
    payload["matches"] = candidates[:64]
    if not candidates:
        return payload
    if len(candidates) == 1:
        payload["suggestion"] = candidates[0]
        return payload
    prefix = os.path.commonprefix(candidates)
    if len(prefix) > len(fragment):
        payload["suggestion"] = prefix
    return payload


def _normalize_debug_transfer_name(name):
    candidate = os.path.basename(str(name or "").replace("\\", "/").strip())
    if not candidate or candidate in {".", ".."}:
        raise ValueError("A valid file name is required.")
    return candidate


def _resolve_debug_transfer_path(raw_path, cwd):
    text = str(raw_path or "").strip()
    if not text:
        raise ValueError("A file path is required.")
    if os.path.isabs(text):
        resolved = text
    else:
        resolved = os.path.join(str(cwd or CLUB3090_DIR), text)
    return os.path.realpath(os.path.normpath(resolved))


def _debug_transfer_pattern_has_glob(text):
    return any(char in str(text or "") for char in ("*", "?", "["))


def _split_debug_transfer_request(raw_path):
    text = str(raw_path or "").strip()
    recurse = True
    if text.endswith(":"):
        recurse = False
        text = text[:-1].rstrip()
    return text, recurse


def _split_debug_transfer_glob_root(pattern_text, cwd):
    normalized = str(pattern_text or "").replace("\\", "/").strip()
    if not normalized:
        return _resolve_debug_transfer_path(".", cwd), ""
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    wildcard_index = next(
        (index for index, part in enumerate(parts) if _debug_transfer_pattern_has_glob(part)),
        len(parts),
    )
    if normalized.startswith("/"):
        root_prefix = "/" + "/".join(parts[:wildcard_index])
    else:
        root_prefix = "/".join(parts[:wildcard_index])
    relative_pattern = "/".join(parts[wildcard_index:])
    root_dir = _resolve_debug_transfer_path(root_prefix or ".", cwd)
    return root_dir, relative_pattern


def _match_debug_transfer_glob_recursive(root_dir, relative_pattern):
    base_dir = str(root_dir or "").strip() or CLUB3090_DIR
    pattern = str(relative_pattern or "").replace("\\", "/").strip()
    if not os.path.isdir(base_dir):
        return []
    basename_pattern = posixpath.basename(pattern)
    matches = []
    seen = set()
    for walk_root, _dirs, file_names in os.walk(base_dir):
        for file_name in file_names:
            full_path = os.path.realpath(os.path.join(walk_root, file_name))
            relative_path = os.path.relpath(full_path, base_dir).replace(os.sep, "/")
            if pattern and not (
                fnmatch.fnmatch(relative_path, pattern)
                or fnmatch.fnmatch(file_name, basename_pattern)
            ):
                continue
            if full_path in seen:
                continue
            seen.add(full_path)
            matches.append(full_path)
    return sorted(matches)


def _expand_debug_transfer_download_entry(raw_path, cwd):
    requested_raw, recurse = _split_debug_transfer_request(raw_path)
    if not requested_raw:
        return []
    requested_path = str(requested_raw or "").strip()
    resolved_path = _resolve_debug_transfer_path(requested_path, cwd)
    if os.path.isdir(resolved_path):
        rows = []
        for walk_root, _dirs, file_names in os.walk(resolved_path):
            for file_name in sorted(file_names):
                full_path = os.path.realpath(os.path.join(walk_root, file_name))
                archive_path = os.path.relpath(full_path, resolved_path).replace(os.sep, "/")
                rows.append(
                    {
                        "requested_path": str(raw_path or "").strip(),
                        "resolved_path": full_path,
                        "exists": True,
                        "size_bytes": os.path.getsize(full_path),
                        "download_name": os.path.basename(full_path),
                        "archive_path": archive_path,
                        "source_kind": "directory",
                    }
                )
        if rows:
            return rows
        return [
            {
                "requested_path": str(raw_path or "").strip(),
                "resolved_path": resolved_path,
                "exists": False,
                "size_bytes": 0,
                "download_name": os.path.basename(resolved_path) or os.path.basename(requested_path),
                "archive_path": "",
                "source_kind": "directory",
            }
        ]
    if _debug_transfer_pattern_has_glob(requested_path):
        root_dir, relative_pattern = _split_debug_transfer_glob_root(requested_path, cwd)
        if recurse:
            matched_paths = _match_debug_transfer_glob_recursive(root_dir, relative_pattern)
        else:
            matched_paths = [
                os.path.realpath(path)
                for path in glob.glob(
                    os.path.join(root_dir, relative_pattern.replace("/", os.sep)),
                    recursive=False,
                )
                if os.path.isfile(path)
            ]
        matched_paths = sorted(dict.fromkeys(matched_paths))
        rows = []
        for full_path in matched_paths:
            archive_path = os.path.relpath(full_path, root_dir).replace(os.sep, "/")
            rows.append(
                {
                    "requested_path": str(raw_path or "").strip(),
                    "resolved_path": full_path,
                    "exists": True,
                    "size_bytes": os.path.getsize(full_path),
                    "download_name": os.path.basename(full_path),
                    "archive_path": archive_path,
                    "source_kind": "pattern",
                }
            )
        if rows:
            return rows
        return [
            {
                "requested_path": str(raw_path or "").strip(),
                "resolved_path": os.path.join(root_dir, relative_pattern.replace("/", os.sep)).rstrip(os.sep),
                "exists": False,
                "size_bytes": 0,
                "download_name": os.path.basename(requested_path.rstrip("/")) or "download",
                "archive_path": "",
                "source_kind": "pattern",
            }
        ]
    exists = os.path.isfile(resolved_path)
    return [
        {
            "requested_path": str(raw_path or "").strip(),
            "resolved_path": resolved_path,
            "exists": exists,
            "size_bytes": os.path.getsize(resolved_path) if exists else 0,
            "download_name": os.path.basename(resolved_path) if exists else os.path.basename(requested_path),
            "archive_path": os.path.basename(resolved_path) if exists else "",
            "source_kind": "file",
        }
    ]


def _read_debug_transfer_bytes(path):
    target = str(path or "").strip()
    if not target:
        raise ValueError("A file path is required.")
    if getattr(os, "geteuid", lambda: 0)() == 0:
        with open(target, "rb") as handle:
            return handle.read()
    process = subprocess.run(
        ["sudo", "-n", "cat", "--", target],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    if process.returncode != 0:
        detail = (process.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"Unable to read {target}")
    return bytes(process.stdout or b"")


def _read_debug_transfer_byte_range(path, offset=0, limit=0):
    target = str(path or "").strip()
    if not target:
        raise ValueError("A file path is required.")
    start = max(0, int(offset or 0))
    size = max(0, int(limit or 0))
    if getattr(os, "geteuid", lambda: 0)() == 0:
        with open(target, "rb") as handle:
            handle.seek(start)
            return handle.read(size) if size > 0 else handle.read()
    script = (
        "import os,sys\n"
        "path=sys.argv[1]\n"
        "offset=max(0,int(sys.argv[2]))\n"
        "limit=max(0,int(sys.argv[3]))\n"
        "with open(path,'rb') as handle:\n"
        "    handle.seek(offset)\n"
        "    data=handle.read(limit) if limit > 0 else handle.read()\n"
        "sys.stdout.buffer.write(data)\n"
    )
    process = subprocess.run(
        ["sudo", "-n", "python3", "-c", script, target, str(start), str(size)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    if process.returncode != 0:
        detail = (process.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"Unable to read {target}")
    return bytes(process.stdout or b"")


def _write_debug_transfer_bytes(path, payload):
    target = str(path or "").strip()
    if not target:
        raise ValueError("A destination path is required.")
    os.makedirs(os.path.dirname(target) or "/", exist_ok=True)
    if getattr(os, "geteuid", lambda: 0)() == 0:
        with open(target, "wb") as handle:
            handle.write(payload)
        return
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, dir=CONTROL_DIR) as handle:
            handle.write(payload)
            tmp_path = handle.name
        process = subprocess.run(
            ["sudo", "-n", "install", "-D", "-m", "0644", tmp_path, target],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        if process.returncode != 0:
            detail = (process.stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(detail or f"Unable to write {target}")
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _write_debug_transfer_byte_range(path, payload, offset=0):
    target = str(path or "").strip()
    if not target:
        raise ValueError("A destination path is required.")
    start = max(0, int(offset or 0))
    data = bytes(payload or b"")
    os.makedirs(os.path.dirname(target) or "/", exist_ok=True)
    if getattr(os, "geteuid", lambda: 0)() == 0:
        mode = "r+b" if os.path.exists(target) else "wb"
        with open(target, mode) as handle:
            handle.seek(start)
            handle.write(data)
        return
    script = (
        "import os,sys\n"
        "path=sys.argv[1]\n"
        "offset=max(0,int(sys.argv[2]))\n"
        "data=sys.stdin.buffer.read()\n"
        "os.makedirs(os.path.dirname(path) or '/', exist_ok=True)\n"
        "mode='r+b' if os.path.exists(path) else 'wb'\n"
        "with open(path,mode) as handle:\n"
        "    handle.seek(offset)\n"
        "    handle.write(data)\n"
    )
    process = subprocess.run(
        ["sudo", "-n", "python3", "-c", script, target, str(start)],
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    if process.returncode != 0:
        detail = (process.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"Unable to write {target}")


def build_debug_transfer_plan(mode, entries):
    mode_name = str(mode or "").strip().lower()
    cwd = debug_shell_current_directory()
    rows = []
    if mode_name == "upload":
        for raw_name in entries if isinstance(entries, list) else []:
            file_name = _normalize_debug_transfer_name(raw_name)
            target_path = os.path.realpath(os.path.join(cwd, file_name))
            rows.append(
                {
                    "name": file_name,
                    "resolved_path": target_path,
                    "exists": os.path.exists(target_path),
                }
            )
        if not rows:
            raise ValueError("Choose at least one file to upload.")
        return {"mode": "upload", "cwd": cwd, "files": rows}
    if mode_name == "download":
        for raw_path in entries if isinstance(entries, list) else []:
            rows.extend(_expand_debug_transfer_download_entry(raw_path, cwd))
        if not rows:
            raise ValueError("Enter at least one file path to download.")
        missing = sorted(dict.fromkeys(row["requested_path"] for row in rows if not row.get("exists")))
        archive_forced = any(str(row.get("source_kind") or "") in {"directory", "pattern"} for row in rows)
        return {
            "mode": "download",
            "cwd": cwd,
            "files": rows,
            "missing_paths": missing,
            "archive_forced": archive_forced,
            "archive_name": f"club3090-download-{time.strftime('%Y%m%d-%H%M%S')}.zip",
        }
    raise ValueError("Unsupported debug transfer mode.")


def write_debug_transfer_upload(file_name, payload):
    data = bytes(payload or b"")
    if not data:
        raise ValueError("Upload payload is empty.")
    cwd = debug_shell_current_directory()
    normalized_name = _normalize_debug_transfer_name(file_name)
    target_path = os.path.realpath(os.path.join(cwd, normalized_name))
    _write_debug_transfer_bytes(target_path, data)
    append_debug_text_line(
        f"[debug-transfer upload] wrote {normalized_name} to {target_path} ({len(data)} bytes)"
    )
    return {
        "ok": True,
        "cwd": cwd,
        "file_name": normalized_name,
        "resolved_path": target_path,
        "size_bytes": len(data),
    }


def _storage_browser_lsblk_rows():
    try:
        output = subprocess.check_output(
            [
                "lsblk",
                "-J",
                "-a",
                "-o",
                "NAME,PATH,TYPE,FSTYPE,MOUNTPOINTS",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
        payload = json.loads(output or "{}")
    except Exception:
        return []
    rows = []

    def walk(nodes):
        for node in nodes or []:
            item = dict(node or {})
            rows.append(item)
            walk(item.get("children") or [])

    walk(payload.get("blockdevices") or [])
    return rows


def _storage_browser_known_roots():
    roots = {os.path.realpath(os.sep)}
    for row in _storage_browser_lsblk_rows():
        mounts = row.get("mountpoints")
        if not isinstance(mounts, list):
            mounts = [mounts]
        for mount in mounts:
            text = str(mount or "").strip()
            if text and text != "[SWAP]" and os.path.isdir(text):
                roots.add(os.path.realpath(text))
    return roots


def _normalize_storage_browser_root(root_path):
    root = os.path.realpath(os.path.abspath(str(root_path or "").strip() or os.sep))
    allowed = _storage_browser_known_roots()
    if root not in allowed:
        raise ValueError("The requested volume root is not currently mounted.")
    return root


def _storage_browser_protected_mount(mount_path):
    target = os.path.realpath(os.path.abspath(str(mount_path or "").strip() or os.sep))
    return target in {os.sep, "/boot", "/boot/efi", "/efi", "/var", "/usr", "/home"}


def _storage_browser_relative_path(root_path, current_path):
    root = os.path.realpath(os.path.abspath(root_path))
    current = os.path.realpath(os.path.abspath(current_path))
    relative = os.path.relpath(current, root).replace(os.sep, "/")
    return "" if relative == "." else relative


def _storage_browser_resolve_path(root_path, relative_path=""):
    root = _normalize_storage_browser_root(root_path)
    target = os.path.realpath(
        os.path.abspath(
            os.path.join(root, str(relative_path or "").replace("/", os.sep).replace("\\", os.sep))
        )
    )
    if os.path.commonpath([root, target]) != root:
        raise ValueError("Requested path escapes the mounted volume root.")
    return root, target


def _storage_browser_stat_metadata(path, stat_info):
    owner = ""
    permissions = ""
    try:
        owner = pwd.getpwuid(int(stat_info.st_uid)).pw_name if pwd is not None else str(getattr(stat_info, "st_uid", ""))
    except Exception:
        owner = str(getattr(stat_info, "st_uid", ""))
    try:
        permissions = stat.filemode(int(stat_info.st_mode))
    except Exception:
        permissions = ""
    return owner, permissions


def _storage_browser_size_cache_key(path, stat_info=None):
    target = os.path.realpath(os.path.abspath(str(path or "").strip()))
    inode = getattr(stat_info, "st_ino", 0) if stat_info is not None else 0
    device = getattr(stat_info, "st_dev", 0) if stat_info is not None else 0
    mtime = getattr(stat_info, "st_mtime_ns", 0) if stat_info is not None else 0
    return f"{target}|{device}|{inode}|{mtime}"


def _storage_browser_probe_directory_size(path, timeout=30):
    target = str(path or "").strip()
    if not target or not os.path.isdir(target):
        return None
    try:
        probe = subprocess.run(
            ["du", "-sB1", "--", target],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=max(5, int(timeout or 30)),
            check=False,
        )
        first = str((probe.stdout or "").strip().split(None, 1)[0] if probe.stdout else "").strip()
        if probe.returncode == 0 and first.isdigit():
            return int(first)
    except Exception:
        return None
    return None


def _storage_browser_directory_size_worker(path, cache_key):
    value = None
    try:
        value = _storage_browser_probe_directory_size(path)
    finally:
        with storage_browser_size_lock:
            storage_browser_size_pending.discard(cache_key)
            storage_browser_size_cache[cache_key] = {
                "value": value,
                "time": time.time(),
                "ok": value is not None,
            }


def _storage_browser_queue_directory_size(path, cache_key):
    with storage_browser_size_lock:
        if cache_key in storage_browser_size_pending:
            return
        active = len(storage_browser_size_pending)
        if active >= 8:
            return
        storage_browser_size_pending.add(cache_key)
    thread = threading.Thread(
        target=_storage_browser_directory_size_worker,
        args=(path, cache_key),
        daemon=True,
    )
    thread.start()


def _storage_browser_entry_size_info(path, stat_info=None, is_dir=False):
    if is_dir:
        try:
            cache_key = _storage_browser_size_cache_key(path, stat_info)
        except Exception:
            return {"size_bytes": None, "size_pending": False, "size_estimated": False}
        now = time.time()
        with storage_browser_size_lock:
            cached = dict(storage_browser_size_cache.get(cache_key) or {})
            pending = cache_key in storage_browser_size_pending
        cached_time = float(cached.get("time") or 0.0)
        if cached and now - cached_time < 900:
            value = cached.get("value")
            return {
                "size_bytes": int(value) if isinstance(value, int) and value >= 0 else None,
                "size_pending": False,
                "size_estimated": bool(cached.get("ok")),
            }
        if not pending:
            _storage_browser_queue_directory_size(path, cache_key)
            pending = True
        return {"size_bytes": None, "size_pending": bool(pending), "size_estimated": False}
    if not is_dir and stat_info is not None:
        try:
            return {"size_bytes": int(stat_info.st_size or 0), "size_pending": False, "size_estimated": False}
        except Exception:
            return {"size_bytes": 0, "size_pending": False, "size_estimated": False}
    target = str(path or "").strip()
    if not target:
        return {"size_bytes": 0, "size_pending": False, "size_estimated": False}
    try:
        probe = subprocess.run(
            ["du", "-sb", "--apparent-size", "--", target],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
        first = str((probe.stdout or "").strip().split(None, 1)[0] if probe.stdout else "").strip()
        if probe.returncode == 0 and first.isdigit():
            return {"size_bytes": int(first), "size_pending": False, "size_estimated": False}
    except Exception:
        pass
    try:
        total = 0
        for root, _dirs, files in os.walk(target):
            for name in files:
                try:
                    total += int(os.path.getsize(os.path.join(root, name)) or 0)
                except Exception:
                    pass
        return {"size_bytes": total, "size_pending": False, "size_estimated": False}
    except Exception:
        return {"size_bytes": 0, "size_pending": False, "size_estimated": False}


def _storage_browser_clear_size_cache():
    with storage_browser_size_lock:
        storage_browser_size_cache.clear()


def list_storage_browser_entries(root_path, relative_path=""):
    root, current = _storage_browser_resolve_path(root_path, relative_path)
    if not os.path.isdir(current):
        raise ValueError("The requested storage browser path is not a directory.")
    entries = []
    current_rel = _storage_browser_relative_path(root, current)
    if current != root:
        parent_rel = _storage_browser_relative_path(root, os.path.dirname(current))
        entries.append(
            {
                "name": "..",
                "relative_path": parent_rel,
                "size_bytes": None,
                "type": "folder",
                "attributes": "dir parent",
                "modified_at": None,
            }
        )
    for item in sorted(os.scandir(current), key=lambda row: (not row.is_dir(follow_symlinks=False), row.name.lower())):
        try:
            stat_info = item.stat(follow_symlinks=False)
        except Exception:
            stat_info = None
        entry_path = os.path.realpath(item.path)
        rel = _storage_browser_relative_path(root, entry_path)
        is_dir = item.is_dir(follow_symlinks=False)
        is_link = item.is_symlink()
        attrs = []
        if is_dir:
            attrs.append("dir")
        if is_link:
            attrs.append("link")
        if item.name.startswith("."):
            attrs.append("hidden")
        if os.path.exists(item.path) and not os.access(item.path, os.W_OK):
            attrs.append("ro")
        file_type = "folder" if is_dir else (str(os.path.splitext(item.name)[1] or "").lstrip(".").lower() or "file")
        owner, permissions = _storage_browser_stat_metadata(entry_path, stat_info) if stat_info is not None else ("", "")
        size_info = _storage_browser_entry_size_info(entry_path, stat_info=stat_info, is_dir=is_dir)
        entries.append(
            {
                "name": item.name,
                "relative_path": rel,
                "size_bytes": size_info.get("size_bytes"),
                "size_pending": bool(size_info.get("size_pending")),
                "size_estimated": bool(size_info.get("size_estimated")),
                "type": file_type,
                "attributes": " ".join(attrs),
                "owner": owner,
                "permissions": permissions,
                "modified_at": int(stat_info.st_mtime) if stat_info is not None else None,
            }
        )
    return {
        "ok": True,
        "root_path": root,
        "current_path": current,
        "relative_path": current_rel,
        "entries": entries,
    }


def mount_storage_browser_volume(device_path):
    wanted = os.path.realpath(os.path.abspath(str(device_path or "").strip()))
    row = next(
        (
            dict(item)
            for item in _storage_browser_lsblk_rows()
            if os.path.realpath(os.path.abspath(str(item.get("path") or ""))) == wanted
        ),
        None,
    )
    if not row:
        raise ValueError("Storage device not found.")
    mounts = row.get("mountpoints")
    if not isinstance(mounts, list):
        mounts = [mounts]
    mounted = next((str(mount or "").strip() for mount in mounts if str(mount or "").strip() and str(mount or "").strip() != "[SWAP]"), "")
    if mounted and os.path.isdir(mounted):
        return {"ok": True, "mount_path": os.path.realpath(mounted), "already_mounted": True}
    mount_root = os.path.join("/mnt", "club3090")
    mount_path = os.path.join(mount_root, os.path.basename(wanted).replace("/", "_"))
    os.makedirs(mount_path, exist_ok=True)
    rc, out = run_cmd(["mount", wanted, mount_path], timeout=120)
    if rc != 0:
        raise RuntimeError(str(out or "mount failed").strip() or "mount failed")
    return {"ok": True, "mount_path": os.path.realpath(mount_path), "already_mounted": False}


def unmount_storage_browser_volume(root_path):
    root = _normalize_storage_browser_root(root_path)
    if _storage_browser_protected_mount(root):
        raise ValueError("That filesystem is managed by the system and cannot be unmounted from the panel.")
    rc, out = run_cmd(["umount", root], timeout=120)
    if rc != 0:
        raise RuntimeError(str(out or "unmount failed").strip() or "unmount failed")
    managed_root = os.path.realpath(os.path.abspath(os.path.join("/mnt", "club3090")))
    try:
        if os.path.commonpath([managed_root, root]) == managed_root and os.path.isdir(root):
            os.rmdir(root)
    except Exception:
        pass
    return {"ok": True, "unmounted_path": root}


def write_storage_browser_upload(root_path, relative_path, file_name, payload):
    root, current = _storage_browser_resolve_path(root_path, relative_path)
    if not os.path.isdir(current):
        raise ValueError("Uploads require an existing folder.")
    normalized_name = _normalize_debug_transfer_name(file_name)
    target_path = os.path.realpath(os.path.join(current, normalized_name))
    if os.path.commonpath([root, target_path]) != root:
        raise ValueError("Upload target escapes the mounted volume root.")
    data = bytes(payload or b"")
    if not data:
        raise ValueError("Upload payload is empty.")
    _write_debug_transfer_bytes(target_path, data)
    _storage_browser_clear_size_cache()
    return {
        "ok": True,
        "root_path": root,
        "current_path": current,
        "file_name": normalized_name,
        "resolved_path": target_path,
        "size_bytes": len(data),
    }


def _storage_browser_is_text_payload(sample):
    probe = bytes(sample or b"")
    if not probe:
        return True
    if b"\x00" in probe:
        return False
    try:
        probe.decode("utf-8")
        return True
    except Exception:
        return False


def _storage_browser_chunk_payload(session, offset=0, limit=STORAGE_BROWSER_CHUNK_BYTES):
    size_bytes = max(0, int(session.get("size_bytes") or 0))
    chunk_offset = min(max(0, int(offset or 0)), size_bytes)
    chunk_limit = max(1, min(int(limit or STORAGE_BROWSER_CHUNK_BYTES), STORAGE_BROWSER_CHUNK_BYTES))
    payload = _read_debug_transfer_byte_range(session.get("path"), chunk_offset, chunk_limit)
    is_text = bool(session.get("is_text"))
    if is_text:
        return {
            "offset": chunk_offset,
            "size_bytes": size_bytes,
            "length_bytes": len(payload),
            "text": payload.decode("utf-8", errors="replace"),
            "encoding": "utf-8",
            "eof": chunk_offset + len(payload) >= size_bytes,
        }
    return {
        "offset": chunk_offset,
        "size_bytes": size_bytes,
        "length_bytes": len(payload),
        "base64": base64.b64encode(payload).decode("ascii"),
        "eof": chunk_offset + len(payload) >= size_bytes,
    }


def read_storage_browser_file(root_path, relative_path):
    root, target = _storage_browser_resolve_path(root_path, relative_path)
    if not os.path.isfile(target):
        raise ValueError("The requested path is not a file.")
    size_bytes = int(os.path.getsize(target) or 0)
    if size_bytes > STORAGE_BROWSER_MAX_FILE_BYTES:
        raise ValueError("Files larger than 1 GB cannot be opened in the editor.")
    mime = mimetypes.guess_type(target)[0] or "application/octet-stream"
    sample = _read_debug_transfer_byte_range(target, 0, min(size_bytes, 65536))
    is_text = _storage_browser_is_text_payload(sample)
    session = {
        "session_id": secrets.token_urlsafe(18),
        "root_path": root,
        "relative_path": _storage_browser_relative_path(root, target),
        "path": target,
        "name": os.path.basename(target),
        "mime": mime,
        "size_bytes": size_bytes,
        "is_text": is_text,
        "chunk_size": STORAGE_BROWSER_CHUNK_BYTES,
        "opened_at": time.time(),
    }
    with storage_browser_file_session_lock:
        storage_browser_file_sessions[session["session_id"]] = dict(session)
    payload = _storage_browser_chunk_payload(session, 0, STORAGE_BROWSER_CHUNK_BYTES)
    response = {
        "ok": True,
        **session,
        "chunked": size_bytes > STORAGE_BROWSER_CHUNK_BYTES,
        "chunk": payload,
    }
    if size_bytes <= STORAGE_BROWSER_CHUNK_BYTES:
        if is_text:
            response["text"] = str(payload.get("text") or "")
        else:
            raw = base64.b64decode(str(payload.get("base64") or "").encode("ascii")) if payload.get("base64") else b""
            response["hex_text"] = raw.hex()
            response["hex_rows"] = []
    return response


def resolve_storage_browser_file(root_path, relative_path):
    root, target = _storage_browser_resolve_path(root_path, relative_path)
    if not os.path.isfile(target):
        raise ValueError("The requested path is not a file.")
    return {
        "ok": True,
        "root_path": root,
        "relative_path": _storage_browser_relative_path(root, target),
        "path": target,
        "name": os.path.basename(target),
        "size_bytes": int(os.path.getsize(target) or 0),
        "mime": mimetypes.guess_type(target)[0] or "application/octet-stream",
    }


def _storage_browser_srt_to_vtt_bytes(payload):
    text = bytes(payload or b"").decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?m)^(\d{2}:\d{2}:\d{2}),(\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}),(\d{3})$", r"\1.\2 --> \3.\4", text)
    return ("WEBVTT\n\n" + text.lstrip("\n")).encode("utf-8")


def read_storage_browser_subtitle_track(root_path, relative_path):
    file_row = resolve_storage_browser_file(root_path, relative_path)
    target = str(file_row.get("path") or "")
    folder = os.path.dirname(target)
    stem = os.path.splitext(os.path.basename(target))[0]
    candidates = []
    for name in sorted(os.listdir(folder)):
        lower = name.lower()
        if not (lower.endswith(".vtt") or lower.endswith(".srt")):
            continue
        if os.path.splitext(name)[0].lower() == stem.lower():
            candidates.append(os.path.join(folder, name))
    if not candidates:
        return {"ok": True, "found": False}
    subtitle_path = candidates[0]
    ext = os.path.splitext(subtitle_path)[1].lower()
    if ext == ".srt":
        payload = _storage_browser_srt_to_vtt_bytes(_read_debug_transfer_bytes(subtitle_path))
        content_type = "text/vtt; charset=utf-8"
        download_name = os.path.splitext(os.path.basename(subtitle_path))[0] + ".vtt"
    else:
        payload = _read_debug_transfer_bytes(subtitle_path)
        content_type = "text/vtt; charset=utf-8"
        download_name = os.path.basename(subtitle_path)
    return {
        "ok": True,
        "found": True,
        "path": subtitle_path,
        "content_type": content_type,
        "download_name": download_name,
        "payload": payload,
    }


def _storage_browser_guess_language(name):
    text = str(name or "").strip().lower()
    if not text:
        return {"code": "", "label": ""}
    alias_map = {
        "en": "English",
        "eng": "English",
        "pt": "Portuguese",
        "ptbr": "Portuguese (Brazil)",
        "pt-br": "Portuguese (Brazil)",
        "pt_br": "Portuguese (Brazil)",
        "por": "Portuguese",
        "br": "Portuguese (Brazil)",
        "es": "Spanish",
        "spa": "Spanish",
        "fr": "French",
        "fra": "French",
        "fre": "French",
        "de": "German",
        "ger": "German",
        "deu": "German",
        "it": "Italian",
        "ita": "Italian",
        "ja": "Japanese",
        "jp": "Japanese",
        "jpn": "Japanese",
        "ko": "Korean",
        "kor": "Korean",
        "zh": "Chinese",
        "zho": "Chinese",
        "chi": "Chinese",
        "ru": "Russian",
        "rus": "Russian",
    }
    tokens = [part for part in re.split(r"[^a-z0-9]+", text) if part]
    for token in tokens:
        if token in alias_map:
            normalized = token.replace("_", "-")
            return {"code": normalized, "label": alias_map[token]}
    return {"code": "", "label": ""}


def _storage_browser_ffprobe_streams(target_path, timeout=12):
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            target_path,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=max(4, int(timeout or 12)),
    )
    if probe.returncode != 0:
        detail = str(probe.stderr or probe.stdout or "ffprobe failed").strip()
        raise RuntimeError(detail or "ffprobe failed")
    payload = json.loads(str(probe.stdout or "{}") or "{}")
    return payload if isinstance(payload, dict) else {}


def _storage_browser_subtitles_dir_candidates(folder):
    rows = []
    current = str(folder or "").strip()
    if not current:
        return rows
    direct = os.path.join(current, "subtitles")
    if os.path.isdir(direct):
        rows.append(direct)
    parent = os.path.dirname(current)
    sibling = os.path.join(parent, "subtitles") if parent else ""
    if sibling and os.path.isdir(sibling) and sibling not in rows:
        rows.append(sibling)
    return rows


def _storage_browser_external_subtitle_rows(target_path):
    folder = os.path.dirname(str(target_path or ""))
    stem = os.path.splitext(os.path.basename(str(target_path or "")))[0].lower()
    roots = [folder] + _storage_browser_subtitles_dir_candidates(folder)
    rows = []
    seen = set()
    for root in roots:
        for name in sorted(os.listdir(root)):
            lower = name.lower()
            if not lower.endswith((".srt", ".vtt", ".ass")):
                continue
            full = os.path.join(root, name)
            if full in seen or not os.path.isfile(full):
                continue
            seen.add(full)
            base = os.path.splitext(name)[0].lower()
            lang = _storage_browser_guess_language(base)
            rows.append(
                {
                    "kind": "external",
                    "path": full,
                    "relative_path": name if root == folder else os.path.relpath(full, folder).replace("\\", "/"),
                    "name": name,
                    "format": os.path.splitext(name)[1].lstrip(".").lower(),
                    "default": base == stem,
                    "language_code": lang.get("code") or "",
                    "language_label": lang.get("label") or "",
                    "label": name + (f" · {lang.get('label')}" if lang.get("label") else ""),
                }
            )
    rows.sort(key=lambda row: (0 if row.get("default") else 1, str(row.get("name") or "").lower()))
    return rows


def _storage_browser_embedded_media_rows(target_path):
    payload = _storage_browser_ffprobe_streams(target_path)
    audio_rows = []
    subtitle_rows = []
    for stream in payload.get("streams") or []:
        if not isinstance(stream, dict):
            continue
        codec_type = str(stream.get("codec_type") or "").strip().lower()
        index = int(stream.get("index") or 0)
        tags = stream.get("tags") or {}
        lang = _storage_browser_guess_language(tags.get("language") or tags.get("LANGUAGE") or "")
        title = str(tags.get("title") or tags.get("TITLE") or "").strip()
        if codec_type == "audio":
            channels = int(stream.get("channels") or 0)
            codec = str(stream.get("codec_name") or "").strip()
            audio_rows.append(
                {
                    "kind": "embedded_audio",
                    "stream_index": index,
                    "channels": channels,
                    "codec": codec,
                    "language_code": lang.get("code") or "",
                    "language_label": lang.get("label") or "",
                    "title": title,
                    "label": " · ".join(part for part in [title or f"Audio {len(audio_rows) + 1}", lang.get("label") or "", f"{channels}ch" if channels else "", codec] if part),
                }
            )
        elif codec_type == "subtitle":
            codec = str(stream.get("codec_name") or "").strip()
            subtitle_rows.append(
                {
                    "kind": "embedded",
                    "stream_index": index,
                    "format": codec,
                    "language_code": lang.get("code") or "",
                    "language_label": lang.get("label") or "",
                    "title": title,
                    "default": False,
                    "label": " · ".join(part for part in [title or f"Embedded Subtitle {len(subtitle_rows) + 1}", lang.get("label") or "", codec] if part),
                }
            )
    return {"audio_streams": audio_rows, "subtitle_streams": subtitle_rows}


def read_storage_browser_media_metadata(root_path, relative_path):
    file_row = resolve_storage_browser_file(root_path, relative_path)
    target = str(file_row.get("path") or "")
    media = _storage_browser_embedded_media_rows(target)
    subtitles = _storage_browser_external_subtitle_rows(target)
    return {
        "ok": True,
        "file": file_row,
        "audio_streams": media.get("audio_streams") or [],
        "subtitle_streams": (media.get("subtitle_streams") or []) + subtitles,
    }


def _storage_browser_extract_embedded_subtitle_bytes(target_path, stream_index):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".vtt", dir=CONTROL_DIR)
    tmp_path = tmp.name
    tmp.close()
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-i",
                target_path,
                "-map",
                f"0:{int(stream_index)}",
                tmp_path,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if result.returncode != 0:
            detail = str(result.stderr or result.stdout or "ffmpeg subtitle extraction failed").strip()
            raise RuntimeError(detail or "ffmpeg subtitle extraction failed")
        payload = _read_debug_transfer_bytes(tmp_path)
        return payload
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def read_storage_browser_subtitle_payload(root_path, relative_path, external_relative_path="", embedded_stream_index=None):
    file_row = resolve_storage_browser_file(root_path, relative_path)
    target = str(file_row.get("path") or "")
    if embedded_stream_index not in (None, ""):
        payload = _storage_browser_extract_embedded_subtitle_bytes(target, int(embedded_stream_index))
        return {
            "ok": True,
            "found": True,
            "content_type": "text/vtt; charset=utf-8",
            "download_name": f"{os.path.splitext(file_row.get('name') or 'subtitle')[0]}.vtt",
            "payload": payload,
        }
    ext_rel = str(external_relative_path or "").strip()
    if ext_rel:
        root, current = _storage_browser_resolve_path(file_row.get("root_path"), os.path.dirname(file_row.get("relative_path") or ""))
        candidate = os.path.realpath(os.path.join(current, ext_rel))
        if not os.path.isfile(candidate):
            raise FileNotFoundError("Subtitle not found.")
        ext = os.path.splitext(candidate)[1].lower()
        if ext == ".srt":
            payload = _storage_browser_srt_to_vtt_bytes(_read_debug_transfer_bytes(candidate))
            name = os.path.splitext(os.path.basename(candidate))[0] + ".vtt"
        elif ext == ".ass":
            payload = _storage_browser_extract_embedded_subtitle_bytes(candidate, 0)
            name = os.path.splitext(os.path.basename(candidate))[0] + ".vtt"
        else:
            payload = _read_debug_transfer_bytes(candidate)
            name = os.path.basename(candidate)
        return {
            "ok": True,
            "found": True,
            "content_type": "text/vtt; charset=utf-8",
            "download_name": name,
            "payload": payload,
        }
    return read_storage_browser_subtitle_track(root_path, relative_path)


def read_storage_browser_file_chunk(session_id, offset=0, limit=STORAGE_BROWSER_CHUNK_BYTES):
    session_key = str(session_id or "").strip()
    with storage_browser_file_session_lock:
        session = dict(storage_browser_file_sessions.get(session_key) or {})
    if not session:
        raise ValueError("The requested file session is no longer available.")
    payload = _storage_browser_chunk_payload(session, offset, limit)
    return {"ok": True, "session_id": session_key, "is_text": bool(session.get("is_text")), **payload}


def close_storage_browser_file_session(session_id):
    session_key = str(session_id or "").strip()
    with storage_browser_file_session_lock:
        storage_browser_file_sessions.pop(session_key, None)
    return {"ok": True, "session_id": session_key}


def save_storage_browser_file(root_path, relative_path, text):
    root, target = _storage_browser_resolve_path(root_path, relative_path)
    _write_debug_transfer_bytes(target, str(text or "").encode("utf-8"))
    _storage_browser_clear_size_cache()
    return {"ok": True, "root_path": root, "relative_path": _storage_browser_relative_path(root, target), "path": target}


def save_storage_browser_binary_file(root_path, relative_path, hex_text):
    root, target = _storage_browser_resolve_path(root_path, relative_path)
    normalized = re.sub(r"[^0-9a-fA-F]", "", str(hex_text or ""))
    if len(normalized) % 2 != 0:
        raise ValueError("Hex data must contain complete byte pairs.")
    payload = bytes.fromhex(normalized) if normalized else b""
    _write_debug_transfer_bytes(target, payload)
    _storage_browser_clear_size_cache()
    return {
        "ok": True,
        "root_path": root,
        "relative_path": _storage_browser_relative_path(root, target),
        "path": target,
        "size_bytes": len(payload),
    }


def save_storage_browser_file_chunk(session_id, offset=0, text=None, base64_data=None, expected_bytes=0):
    session_key = str(session_id or "").strip()
    with storage_browser_file_session_lock:
        session = dict(storage_browser_file_sessions.get(session_key) or {})
    if not session:
        raise ValueError("The requested file session is no longer available.")
    target = str(session.get("path") or "")
    chunk_offset = max(0, int(offset or 0))
    expected_length = max(0, int(expected_bytes or 0))
    if bool(session.get("is_text")):
        payload = str(text or "").encode("utf-8")
    else:
        payload = base64.b64decode(str(base64_data or "").encode("ascii")) if base64_data else b""
    if expected_length and len(payload) != expected_length:
        raise ValueError("Chunk saves must keep the current chunk length unchanged.")
    _write_debug_transfer_byte_range(target, payload, chunk_offset)
    try:
        size_bytes = int(os.path.getsize(target) or 0)
    except Exception:
        size_bytes = int(session.get("size_bytes") or 0)
    with storage_browser_file_session_lock:
        if session_key in storage_browser_file_sessions:
            storage_browser_file_sessions[session_key]["size_bytes"] = size_bytes
    _storage_browser_clear_size_cache()
    return {"ok": True, "session_id": session_key, "offset": chunk_offset, "length_bytes": len(payload), "size_bytes": size_bytes}


def create_storage_browser_folder(root_path, relative_path, name):
    root, current = _storage_browser_resolve_path(root_path, relative_path)
    target = os.path.realpath(os.path.join(current, _normalize_debug_transfer_name(name)))
    if os.path.commonpath([root, target]) != root:
        raise ValueError("Folder target escapes the mounted volume root.")
    os.makedirs(target, exist_ok=False)
    _storage_browser_clear_size_cache()
    return {"ok": True, "path": target}


def create_storage_browser_file(root_path, relative_path, name):
    root, current = _storage_browser_resolve_path(root_path, relative_path)
    target = os.path.realpath(os.path.join(current, _normalize_debug_transfer_name(name)))
    if os.path.commonpath([root, target]) != root:
        raise ValueError("File target escapes the mounted volume root.")
    if os.path.exists(target):
        raise ValueError("That file already exists.")
    _write_debug_transfer_bytes(target, b"")
    _storage_browser_clear_size_cache()
    return {"ok": True, "path": target, "relative_path": _storage_browser_relative_path(root, target)}


def prepare_storage_browser_download(root_path, entries):
    root = _normalize_storage_browser_root(root_path)
    resolved_paths = []
    for entry in entries if isinstance(entries, list) else []:
        _root, target = _storage_browser_resolve_path(root, entry)
        resolved_paths.append(target)
    if not resolved_paths:
        raise ValueError("Choose at least one file or folder to download.")
    return prepare_debug_transfer_download(resolved_paths)


def prepare_storage_browser_download_plan(root_path, entries):
    root = _normalize_storage_browser_root(root_path)
    resolved_paths = []
    for entry in entries if isinstance(entries, list) else []:
        _root, target = _storage_browser_resolve_path(root, entry)
        resolved_paths.append(target)
    if not resolved_paths:
        raise ValueError("Choose at least one file or folder to download.")
    plan = build_debug_transfer_plan("download", resolved_paths)
    rows = list(plan.get("files") or [])
    total_bytes = sum(max(0, int(row.get("size_bytes") or 0)) for row in rows)
    archive_forced = bool(plan.get("archive_forced")) or len(rows) != 1
    free_bytes = shutil.disk_usage(CONTROL_DIR).free if os.path.isdir(CONTROL_DIR) else shutil.disk_usage("/").free
    required_temp_bytes = total_bytes if archive_forced else 0
    return {
        "ok": True,
        "archive_forced": archive_forced,
        "archive_name": plan.get("archive_name") or "",
        "entry_count": len(rows),
        "total_bytes": total_bytes,
        "requires_confirmation": archive_forced and total_bytes > STORAGE_BROWSER_MAX_FILE_BYTES,
        "enough_temp_space": free_bytes > required_temp_bytes,
        "free_bytes": free_bytes,
        "required_temp_bytes": required_temp_bytes,
    }


def _set_storage_browser_download_job(job_id, **updates):
    with storage_browser_download_job_lock:
        key = str(job_id or "").strip()
        current = dict(storage_browser_download_jobs.get(key) or {"job_id": key})
        current.update(updates)
        storage_browser_download_jobs[key] = current
        return dict(current)


def storage_browser_download_job_status(job_id):
    with storage_browser_download_job_lock:
        return dict(storage_browser_download_jobs.get(str(job_id or "").strip()) or {})


def _run_storage_browser_download_job(job_id, plan):
    rows = list(plan.get("files") or [])
    archive_name = str(plan.get("archive_name") or f"club3090-download-{job_id}.zip")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=CONTROL_DIR)
    tmp_path = tmp.name
    tmp.close()
    used_names = set()
    total_bytes = sum(max(0, int(row.get("size_bytes") or 0)) for row in rows)
    done_bytes = 0
    _set_storage_browser_download_job(
        job_id,
        active=True,
        status="running",
        archive_name=archive_name,
        total_bytes=total_bytes,
        done_bytes=0,
        percent=0,
        summary=f"Zipping {len(rows)} item{'s' if len(rows) != 1 else ''} for download...",
        file_path="",
        cleanup_path="",
        error="",
    )
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for index, row in enumerate(rows, start=1):
                data = _read_debug_transfer_bytes(row.get("resolved_path"))
                archive_name_row = _dedupe_debug_transfer_archive_path(
                    used_names,
                    row.get("requested_path"),
                    row.get("resolved_path"),
                    row.get("archive_path"),
                )
                archive.writestr(archive_name_row, data)
                done_bytes += len(data)
                percent = int((done_bytes / total_bytes) * 100) if total_bytes > 0 else 100
                _set_storage_browser_download_job(
                    job_id,
                    done_bytes=done_bytes,
                    percent=max(0, min(100, percent)),
                    summary=f"Zipping {archive_name}: {max(0, min(100, percent))}% done...",
                    current_entry=archive_name_row,
                    current_index=index,
                    total_entries=len(rows),
                )
        size_bytes = os.path.getsize(tmp_path)
        _set_storage_browser_download_job(
            job_id,
            active=False,
            status="ready",
            percent=100,
            done_bytes=total_bytes,
            size_bytes=size_bytes,
            summary=f"Zip ready: {archive_name}",
            file_path=tmp_path,
            cleanup_path=tmp_path,
        )
    except Exception as error:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        _set_storage_browser_download_job(
            job_id,
            active=False,
            status="error",
            error=str(error),
            summary=f"Zip failed: {error}",
        )


def start_storage_browser_download_job(root_path, entries):
    root = _normalize_storage_browser_root(root_path)
    resolved_paths = []
    for entry in entries if isinstance(entries, list) else []:
        _root, target = _storage_browser_resolve_path(root, entry)
        resolved_paths.append(target)
    if not resolved_paths:
        raise ValueError("Choose at least one file or folder to download.")
    plan = build_debug_transfer_plan("download", resolved_paths)
    rows = list(plan.get("files") or [])
    if len(rows) == 1 and not plan.get("archive_forced"):
        direct = prepare_debug_transfer_download(resolved_paths)
        return {"ok": True, "mode": "direct", "download": direct}
    meta = prepare_storage_browser_download_plan(root, entries)
    if not meta.get("enough_temp_space"):
        raise RuntimeError(
            f"Not enough free disk space to prepare the zip. Need about {_format_progress_bytes(meta.get('required_temp_bytes') or 0)} free but only {_format_progress_bytes(meta.get('free_bytes') or 0)} is available."
        )
    job_id = f"storage-download-{int(time.time() * 1000)}-{secrets.token_hex(3)}"
    _set_storage_browser_download_job(
        job_id,
        active=False,
        status="queued",
        archive_name=meta.get("archive_name") or "",
        total_bytes=meta.get("total_bytes") or 0,
        done_bytes=0,
        percent=0,
        summary="Queued zip download job...",
        file_path="",
        cleanup_path="",
        error="",
    )
    threading.Thread(
        target=_run_storage_browser_download_job,
        args=(job_id, plan),
        name=f"club3090-storage-download-{job_id[-6:]}",
        daemon=True,
    ).start()
    return {"ok": True, "mode": "job", "job": storage_browser_download_job_status(job_id)}


def delete_storage_browser_entries(root_path, entries):
    root = _normalize_storage_browser_root(root_path)
    removed = []
    for entry in entries if isinstance(entries, list) else []:
        _root, target = _storage_browser_resolve_path(root, entry)
        if target == root:
            raise ValueError("The mounted volume root itself cannot be deleted.")
        if os.path.isdir(target) and not os.path.islink(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        removed.append(target)
    if removed:
        _preset_cache_size_summary_cache.clear()
        _storage_browser_clear_size_cache()
    return {"ok": True, "removed": removed, "removed_count": len(removed)}


def _dedupe_debug_transfer_arcname(used, requested_path, resolved_path):
    preferred = os.path.basename(str(resolved_path or "").strip()) or os.path.basename(str(requested_path or "").strip()) or "file"
    preferred = preferred.replace("\\", "/").strip("/") or "file"
    if preferred not in used:
        used.add(preferred)
        return preferred
    stem, ext = os.path.splitext(preferred)
    index = 2
    while True:
        candidate = f"{stem}-{index}{ext}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        index += 1


def _dedupe_debug_transfer_archive_path(used, requested_path, resolved_path, archive_path=""):
    preferred = str(archive_path or "").replace("\\", "/").strip("/")
    if not preferred:
        return _dedupe_debug_transfer_arcname(used, requested_path, resolved_path)
    if preferred not in used:
        used.add(preferred)
        return preferred
    parts = preferred.rsplit("/", 1)
    if len(parts) == 2:
        parent, name = parts
    else:
        parent, name = "", parts[0]
    stem, ext = os.path.splitext(name)
    index = 2
    while True:
        candidate_name = f"{stem}-{index}{ext}"
        candidate = f"{parent}/{candidate_name}".strip("/") if parent else candidate_name
        if candidate not in used:
            used.add(candidate)
            return candidate
        index += 1


def prepare_debug_transfer_download(entries):
    plan = build_debug_transfer_plan("download", entries)
    missing = list(plan.get("missing_paths") or [])
    if missing:
        raise FileNotFoundError("Missing file(s): " + ", ".join(missing))
    rows = list(plan.get("files") or [])
    if len(rows) == 1 and not plan.get("archive_forced"):
        row = dict(rows[0])
        append_debug_text_line(
            f"[debug-transfer download] prepared {row.get('resolved_path')} ({row.get('size_bytes')} bytes)"
        )
        return {
            "kind": "single",
            "cwd": plan.get("cwd") or CLUB3090_DIR,
            "resolved_paths": [row.get("resolved_path")],
            "download_name": row.get("download_name") or os.path.basename(str(row.get("resolved_path") or "")),
            "content_type": mimetypes.guess_type(str(row.get("resolved_path") or ""))[0] or "application/octet-stream",
            "file_path": row.get("resolved_path") or "",
            "size_bytes": int(row.get("size_bytes") or 0),
            "cleanup_path": "",
        }
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=CONTROL_DIR)
    tmp_path = tmp.name
    tmp.close()
    used_names = set()
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            total_rows = len(rows)
            for index, row in enumerate(rows, start=1):
                data = _read_debug_transfer_bytes(row.get("resolved_path"))
                archive_name = _dedupe_debug_transfer_archive_path(
                    used_names,
                    row.get("requested_path"),
                    row.get("resolved_path"),
                    row.get("archive_path"),
                )
                append_debug_text_line(
                    f"[debug-transfer download] zipping {index}/{total_rows} {archive_name}"
                )
                archive.writestr(
                    archive_name,
                    data,
                )
        size_bytes = os.path.getsize(tmp_path)
        append_debug_text_line(
            f"[debug-transfer download] prepared {len(rows)} files as {plan.get('archive_name')} ({size_bytes} bytes)"
        )
        return {
            "kind": "archive",
            "cwd": plan.get("cwd") or CLUB3090_DIR,
            "resolved_paths": [str(row.get("resolved_path") or "") for row in rows],
            "download_name": plan.get("archive_name") or os.path.basename(tmp_path),
            "content_type": "application/zip",
            "file_path": tmp_path,
            "size_bytes": int(size_bytes or 0),
            "cleanup_path": tmp_path,
        }
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise


def _stream_process_output_to_audit(process, prefix):
    stream = getattr(process, "stdout", None)
    if stream is None:
        return
    pending = ""
    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        if isinstance(chunk, bytes):
            pending += chunk.decode("utf-8", errors="replace")
        else:
            pending += str(chunk)
        pending = pending.replace("\r\n", "\n").replace("\r", "\n")
        while "\n" in pending:
            line, pending = pending.split("\n", 1)
            append_audit_text_line(f"{prefix} {str(line or '').rstrip()}")
    if pending:
        append_audit_text_line(f"{prefix} {str(pending or '').rstrip()}")


def _format_progress_bytes(num_bytes):
    value = float(max(0, int(num_bytes or 0)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{value:.1f} TB"


def _parse_hf_download_segment(tokens):
    rows = list(tokens or [])
    while rows and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", str(rows[0] or "").strip()):
        rows.pop(0)
    if rows and str(rows[0] or "").strip() == "env":
        rows.pop(0)
        while rows and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", str(rows[0] or "").strip()):
            rows.pop(0)
    if len(rows) < 4 or rows[:2] not in (["hf", "download"], ["huggingface-cli", "download"]):
        return None
    repo_id = str(rows[2] or "").strip()
    if not repo_id:
        return None
    local_dir = ""
    filenames = []
    idx = 3
    while idx < len(rows):
        token = str(rows[idx] or "").strip()
        if token == "--local-dir" and idx + 1 < len(rows):
            local_dir = str(rows[idx + 1] or "").strip()
            idx += 2
            continue
        if token.startswith("--local-dir="):
            local_dir = token.split("=", 1)[1].strip()
            idx += 1
            continue
        if token.startswith("-"):
            idx += 2 if idx + 1 < len(rows) and not str(rows[idx + 1] or "").startswith("-") else 1
            continue
        filenames.append(token)
        idx += 1
    if not local_dir:
        return None
    return {
        "repo_id": repo_id,
        "filenames": filenames,
        "local_dir": local_dir,
    }


def _parse_simple_hf_download_plan(install_command):
    text = str(install_command or "").replace("\r", " ").replace("\n", " ").strip()
    if not text or "hf download" not in text or ";" in text:
        return []
    plan = []
    for segment in [part.strip() for part in text.split("&&") if str(part or "").strip()]:
        normalized_segment = segment
        while normalized_segment.startswith("(") and normalized_segment.endswith(")"):
            normalized_segment = normalized_segment[1:-1].strip()
        alternatives = [part.strip() for part in normalized_segment.split("||") if str(part or "").strip()]
        if not alternatives:
            return []
        parsed_alternatives = []
        for alternative in alternatives:
            try:
                tokens = shlex.split(alternative)
                parsed = _parse_hf_download_segment(tokens)
            except Exception:
                return []
            if not parsed:
                return []
            parsed_alternatives.append(parsed)
        first = parsed_alternatives[0]
        if any(
            parsed.get("local_dir") != first.get("local_dir")
            or list(parsed.get("filenames") or []) != list(first.get("filenames") or [])
            for parsed in parsed_alternatives[1:]
        ):
            return []
        plan.append({
            "repo_ids": [parsed.get("repo_id") for parsed in parsed_alternatives if str(parsed.get("repo_id") or "").strip()],
            "filenames": list(first.get("filenames") or []),
            "local_dir": str(first.get("local_dir") or "").strip(),
        })
    return plan


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


def _parse_setup_install_command(install_command):
    text = str(install_command or "").replace("\r", " ").replace("\n", " ").strip()
    if not text or ";" in text or "&&" in text or "||" in text:
        return None
    try:
        tokens = shlex.split(text)
    except Exception:
        return None
    if not tokens:
        return None
    env_tokens = []
    idx = 0
    while idx < len(tokens):
        token = str(tokens[idx] or "").strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            env_tokens.append(token)
            idx += 1
            continue
        break
    if idx >= len(tokens):
        return None
    command_tokens = tokens[idx:]
    if not command_tokens:
        return None
    command_text = str(command_tokens[0] or "").strip()
    if command_text in {"bash", "sh"}:
        if len(command_tokens) < 3:
            return None
        script_path = str(command_tokens[1] or "").strip()
        if script_path not in {"scripts/setup.sh", "./scripts/setup.sh"}:
            return None
        model_id = str(command_tokens[2] or "").strip()
        extra_args = command_tokens[3:]
        shell_name = command_text
    elif command_text in {"scripts/setup.sh", "./scripts/setup.sh"}:
        if len(command_tokens) < 2:
            return None
        script_path = command_text
        model_id = str(command_tokens[1] or "").strip()
        extra_args = command_tokens[2:]
        shell_name = ""
    else:
        return None
    if not model_id or extra_args:
        return None
    env_map = {}
    for token in env_tokens:
        key, value = token.split("=", 1)
        key = str(key or "").strip()
        if key:
            env_map[key] = str(value or "")
    return {
        "env_tokens": list(env_tokens),
        "env_map": env_map,
        "model_id": model_id,
        "script_path": script_path,
        "shell_name": shell_name,
    }


def _setup_install_command_with_skip_model(parsed_setup):
    setup = parsed_setup if isinstance(parsed_setup, dict) else {}
    model_id = str(setup.get("model_id") or "").strip()
    script_path = str(setup.get("script_path") or "scripts/setup.sh").strip() or "scripts/setup.sh"
    if not model_id:
        return ""
    env_map = dict(setup.get("env_map") or {})
    env_map["SKIP_MODEL"] = "1"
    env_prefix = " ".join(
        f"{key}={shlex.quote(str(value or ''))}"
        for key, value in env_map.items()
        if str(key or "").strip()
    )
    shell_name = str(setup.get("shell_name") or "bash").strip() or "bash"
    command = f"{shell_name} {shlex.quote(script_path)} {shlex.quote(model_id)}"
    return f"{env_prefix} {command}".strip() if env_prefix else command


def _setup_weight_variant_from_env(setup_model, setup_env):
    model_id = str(setup_model or "").strip()
    env = dict(setup_env or {})
    for key in ("WEIGHT_KEY", "MODEL_WEIGHT_KEY"):
        value = str(env.get(key) or "").strip()
        if ":" in value:
            candidate_model, candidate_variant = value.split(":", 1)
            if (not model_id or candidate_model == model_id) and candidate_variant.strip():
                return candidate_variant.strip()
    for key in ("WEIGHTS", "WEIGHT_VARIANT", "MODEL_WEIGHTS"):
        value = str(env.get(key) or "").strip()
        if value:
            return value
    return ""


def _weight_recipe_size_bytes(recipe):
    model_id = str((recipe or {}).get("WEIGHT_MODEL") or "").strip()
    variant = str((recipe or {}).get("WEIGHT_VARIANT") or "").strip()
    if not model_id or not variant:
        return 0
    try:
        reader = _load_weight_reader()
        model = reader._load_models().get(model_id) or {}
        meta = (model.get("weights") or {}).get(variant) or {}
        size_gb = float(meta.get("size_gb") or 0)
        return int(size_gb * 1024 * 1024 * 1024) if size_gb > 0 else 0
    except Exception:
        return 0


def _monitor_plan_from_variant_install(variant, install_command=""):
    parsed = _parse_simple_hf_download_plan(install_command)
    row = variant if isinstance(variant, dict) else {}
    model_dir_root = str(row.get("host_model_dir") or "").strip()
    if not model_dir_root:
        model_dir_root = os.path.join(CLUB3090_DIR, "models-cache")
    if not model_dir_root:
        return []
    plan = []
    seen = set()
    targets = [
        ("model_path", _container_model_subpath(row.get("model_path"))),
        ("draft_model_path", _container_model_subpath(row.get("draft_model_path"))),
        ("mmproj_path", _container_model_subpath(row.get("mmproj_path"))),
    ]
    setup = _parse_setup_install_command(install_command)
    if setup:
        setup_model = str(setup.get("model_id") or row.get("model_id") or "").strip()
        setup_env = dict(setup.get("env_map") or {})
        setup_variant = _setup_weight_variant_from_env(setup_model, setup_env)
        if not targets[0][1] and setup_variant:
            recipe = _weight_recipe_from_model_variant(setup_model, setup_variant)
            subdir = str((recipe or {}).get("WEIGHT_SUBDIR") or "").strip().strip("/")
            if subdir:
                targets[0] = ("model_path", subdir)
        if setup_model == "diffusiongemma-26b-a4b" and not any(subpath for _, subpath in targets):
            targets = [("model_path", "diffusiongemma-26b-a4b-it-fp8-dynamic")]
        elif setup_model == "qwen3.6-35b-a3b" and not targets[0][1]:
            targets[0] = ("model_path", "qwen3.6-35b-a3b-autoround-int4")
        elif setup_model == "gemma-4-26b-a4b":
            if not targets[0][1]:
                targets[0] = ("model_path", "gemma-4-26b-a4b-autoround-int4-mixed")
            if str(setup_env.get("WEIGHTS") or "").strip().lower() == "awq":
                targets[0] = ("model_path", "gemma-4-26b-a4b-awq-4bit")
            if str(setup_env.get("WITH_ASSISTANT_DRAFT") or "").strip() == "1":
                targets.append(("draft_model_path", "gemma-4-26b-a4b-it-assistant"))
        elif setup_model == "gemma-4-12b":
            if not any(role == "draft_model_path" and subpath for role, subpath in targets):
                targets.append(("draft_model_path", "gemma-4-12b-it-assistant"))
        elif setup_model == "gemma-4-31b":
            draft_subdir = (
                "gemma-4-31b-it-dflash"
                if str(setup_env.get("WITH_DFLASH_DRAFT") or "").strip() == "1"
                else "gemma-4-31b-it-assistant"
            )
            if not targets[0][1]:
                targets[0] = ("model_path", "gemma-4-31b-autoround-int4")
            if not any(role == "draft_model_path" and subpath for role, subpath in targets):
                targets.append(("draft_model_path", draft_subdir))
    if not targets[0][1] and str(row.get("model_id") or "").strip() and str(row.get("weights_variant") or "").strip():
        recipe = _weight_recipe_from_model_variant(row.get("model_id"), row.get("weights_variant"))
        if recipe:
            subdir = str(recipe.get("WEIGHT_SUBDIR") or "").strip().strip("/")
            if subdir:
                targets[0] = ("model_path", subdir)
    for key, subpath in targets:
        clean = str(subpath or "").strip()
        if not clean:
            continue
        recipe = _weight_recipe_from_subpath(clean)
        if not recipe and clean == "diffusiongemma-26b-a4b-it-fp8-dynamic":
            recipe = {
                "WEIGHT_REPO": "RedHatAI/diffusiongemma-26B-A4B-it-FP8-dynamic",
                "WEIGHT_SUBDIR": clean,
            }
        if not recipe and clean == "gemma-4-12b-it-assistant":
            recipe = {
                "WEIGHT_REPO": "google/gemma-4-12B-it-assistant",
                "WEIGHT_MODEL": "gemma-4-12b",
                "WEIGHT_VARIANT": "assistant",
                "WEIGHT_SUBDIR": clean,
            }
        if key == "model_path" and not recipe:
            recipe = _weight_recipe_from_model_variant(
                row.get("model_id"),
                row.get("weights_variant"),
            )
        if key == "draft_model_path" and not recipe and setup:
            draft_variant = ""
            clean_name = clean.rstrip("/").split("/")[-1]
            try:
                reader = _load_weight_reader()
                model = reader._load_models().get(setup_model) or {}
                for variant_name, meta in (model.get("weights") or {}).items():
                    meta_subdir = str((meta or {}).get("local_subdir") or (meta or {}).get("path") or "").strip().strip("/")
                    meta_kind = str((meta or {}).get("kind") or "").strip().lower()
                    if meta_subdir == clean or meta_subdir.rstrip("/").split("/")[-1] == clean_name or meta_kind == "draft":
                        draft_variant = str(variant_name or "").strip()
                        if meta_subdir == clean:
                            break
            except Exception:
                draft_variant = ""
            if draft_variant:
                recipe = _weight_recipe_from_model_variant(setup_model, draft_variant)
        local_dir = str(_recipe_subdir_host_path(model_dir_root, recipe) or "").strip()
        repo_ids = []
        primary_repo = str((recipe or {}).get("WEIGHT_REPO") or "").strip()
        if primary_repo:
            repo_ids.append(primary_repo)
        repo_ids.extend(
            str(item or "").strip()
            for item in ((recipe or {}).get("WEIGHT_REPO_CANDIDATES") or [])
            if str(item or "").strip()
        )
        repo_ids = [item for item in dict.fromkeys(repo_ids) if item]
        filenames = [
            str(item or "").strip()
            for item in shlex.split(str((recipe or {}).get("WEIGHT_FILES") or ""))
            if str(item or "").strip()
        ]
        if not local_dir or not repo_ids:
            continue
        dedupe_key = (local_dir, tuple(filenames), tuple(repo_ids))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        plan.append({
            "repo_ids": repo_ids,
            "filenames": filenames,
            "local_dir": local_dir,
            "expected_total_bytes": _weight_recipe_size_bytes(recipe),
        })
    if parsed:
        hints_by_target = {}
        hints_by_repo = {}
        for item in plan:
            target = os.path.abspath(str((item or {}).get("local_dir") or "").strip())
            expected = int((item or {}).get("expected_total_bytes") or 0)
            repos = tuple(str(repo or "").strip() for repo in ((item or {}).get("repo_ids") or []) if str(repo or "").strip())
            if expected > 0:
                if target:
                    hints_by_target[target] = max(int(hints_by_target.get(target) or 0), expected)
                for repo in repos:
                    hints_by_repo[repo] = max(int(hints_by_repo.get(repo) or 0), expected)
        enriched = []
        for item in parsed:
            row_item = dict(item or {})
            if int(row_item.get("expected_total_bytes") or 0) <= 0:
                target = os.path.abspath(str(row_item.get("local_dir") or "").strip())
                expected = int(hints_by_target.get(target) or 0)
                if expected <= 0:
                    for repo in row_item.get("repo_ids") or []:
                        expected = max(expected, int(hints_by_repo.get(str(repo or "").strip()) or 0))
                if expected > 0:
                    row_item["expected_total_bytes"] = expected
            enriched.append(row_item)
        return enriched
    return plan


def _hf_auth_headers(env_map):
    env = env_map if isinstance(env_map, dict) else {}
    token = (
        str(env.get("HF_TOKEN") or "").strip()
        or str(env.get("HUGGING_FACE_HUB_TOKEN") or "").strip()
        or str(env.get("HUGGINGFACE_HUB_TOKEN") or "").strip()
    )
    headers = {"User-Agent": script_user_agent()}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _hf_repo_file_sizes(repo_ids, filenames, env_map):
    wanted = [str(name or "").strip().lstrip("/") for name in (filenames or []) if str(name or "").strip()]
    candidates = repo_ids if isinstance(repo_ids, (list, tuple)) else [repo_ids]
    for repo_id in candidates:
        repo = str(repo_id or "").strip()
        if not repo:
            continue
        url = f"https://huggingface.co/api/models/{quote(repo, safe='/')}"
        req = urllib.request.Request(url, headers=_hf_auth_headers(env_map))
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        siblings = payload.get("siblings") or []
        sizes = {}
        for row in siblings:
            if not isinstance(row, dict):
                continue
            name = str(row.get("rfilename") or "").strip().lstrip("/")
            if not name:
                continue
            if wanted and name not in wanted:
                continue
            size = row.get("size")
            if size in (None, "") and isinstance(row.get("lfs"), dict):
                size = row.get("lfs", {}).get("size")
            try:
                sizes[name] = int(size or 0)
            except Exception:
                continue
        if sizes:
            if wanted:
                missing = [name for name in wanted if name not in sizes or not int(sizes.get(name) or 0)]
                for name in missing:
                    try:
                        file_url = f"https://huggingface.co/{repo}/resolve/main/{quote(name, safe='/')}"
                        head_req = urllib.request.Request(
                            file_url,
                            headers=_hf_auth_headers(env_map),
                            method="HEAD",
                        )
                        with urllib.request.urlopen(head_req, timeout=20) as head_response:
                            length = head_response.headers.get("Content-Length")
                        if length not in (None, ""):
                            sizes[name] = int(length)
                    except Exception:
                        continue
                return {name: sizes[name] for name in wanted if name in sizes}
            return sizes
    return {}


def _hf_download_target_paths(plan):
    rows = []
    seen = set()
    for step in plan or []:
        local_dir = str(step.get("local_dir") or "").strip()
        if not local_dir:
            continue
        filenames = [str(name or "").strip().lstrip("/") for name in (step.get("filenames") or []) if str(name or "").strip()]
        if filenames:
            for name in filenames:
                target_path = os.path.join(local_dir, name.replace("/", os.sep))
                if target_path not in seen:
                    rows.append({"path": target_path, "name": name})
                    seen.add(target_path)
        else:
            if local_dir not in seen:
                rows.append({"path": local_dir, "name": ""})
                seen.add(local_dir)
    return rows


def _model_install_download_lock_keys(plan):
    keys = []
    for step in plan or []:
        local_dir = str((step or {}).get("local_dir") or "").strip()
        if not local_dir:
            continue
        key = os.path.normcase(os.path.realpath(os.path.abspath(local_dir)))
        if key and key not in keys:
            keys.append(key)
    return sorted(keys)


def _model_install_affected_variants(inventory, plan):
    target_keys = set(_model_install_download_lock_keys(plan))
    affected = []
    if not target_keys:
        return affected
    for variant in (inventory or {}).get("variants") or []:
        if not isinstance(variant, dict):
            continue
        candidate_plan = _monitor_plan_from_variant_install(
            variant,
            variant.get("install_command") or "",
        )
        if not target_keys.intersection(_model_install_download_lock_keys(candidate_plan)):
            continue
        affected.append(
            {
                "variant_id": str(variant.get("variant_id") or "").strip(),
                "selector": str(variant.get("selector") or variant.get("upstream_tag") or "").strip(),
            }
        )
    return affected


def _release_model_install_download_locks(acquired):
    for lock in reversed(list(acquired or [])):
        try:
            lock.release()
        except RuntimeError:
            pass


def _acquire_model_install_download_locks(job_id, prefix, plan):
    keys = _model_install_download_lock_keys(plan)
    with model_install_download_lock_guard:
        locks = [
            model_install_download_locks.setdefault(key, threading.Lock())
            for key in keys
        ]
    acquired = []
    waiting_logged = False
    try:
        for lock in locks:
            while not lock.acquire(timeout=1.0):
                if _model_install_stop_requested(job_id):
                    raise RuntimeError("model install stopped by request")
                if not waiting_logged:
                    waiting_logged = True
                    _set_model_install_job_entry(
                        job_id,
                        status="waiting",
                        summary="Waiting for another download using the same model target",
                    )
                    append_audit_text_line(
                        f"{prefix} waiting for another model download using the same target"
                    )
            acquired.append(lock)
        if waiting_logged:
            _set_model_install_job_entry(
                job_id,
                status="running",
                summary="Running model install job",
            )
            append_audit_text_line(f"{prefix} shared model download target is ready")
        return acquired
    except Exception:
        _release_model_install_download_locks(acquired)
        raise


def _hf_cache_root_candidates(env_map):
    env = env_map if isinstance(env_map, dict) else {}
    roots = []
    explicit_cache = str(env.get("HUGGINGFACE_HUB_CACHE") or env.get("HF_HUB_CACHE") or "").strip()
    if explicit_cache:
        roots.append(explicit_cache)
    hf_home = str(env.get("HF_HOME") or "").strip()
    if hf_home:
        roots.append(os.path.join(hf_home, "hub"))
    home = str(env.get("HOME") or os.path.expanduser("~") or "").strip()
    if home:
        roots.append(os.path.join(home, ".cache", "huggingface", "hub"))
    normalized = []
    for root in roots:
        text = str(root or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _hf_repo_cache_dir_candidates(repo_id, env_map):
    repo = str(repo_id or "").strip()
    if not repo:
        return []
    cache_key = f"models--{repo.replace('/', '--')}"
    return [
        os.path.join(root, cache_key)
        for root in _hf_cache_root_candidates(env_map)
    ]


def _hf_download_step_loaded_bytes(step, env_map, step_total_bytes=0):
    local_dir = str(step.get("local_dir") or "").strip()
    filenames = [
        str(name or "").strip().lstrip("/")
        for name in (step.get("filenames") or [])
        if str(name or "").strip()
    ]
    file_bytes = 0
    if local_dir and filenames:
        file_bytes = sum(
            _path_size_bytes(os.path.join(local_dir, name.replace("/", os.sep)))
            for name in filenames
        )
    dir_bytes = _path_size_bytes(local_dir) if local_dir else 0
    cache_bytes = 0
    for repo_id in (step.get("repo_ids") or []):
        for candidate in _hf_repo_cache_dir_candidates(repo_id, env_map):
            cache_bytes = max(cache_bytes, _path_size_bytes(candidate))
    loaded = max(file_bytes, dir_bytes, cache_bytes)
    if step_total_bytes and loaded > int(step_total_bytes or 0):
        loaded = int(step_total_bytes or 0)
    return int(max(0, loaded))


def _existing_parent_dir(path):
    current = os.path.abspath(str(path or "").strip() or ".")
    while current and not os.path.exists(current):
        parent = os.path.dirname(current)
        if not parent or parent == current:
            break
        current = parent
    return current if current and os.path.exists(current) else "."


def _filesystem_free_bytes(path):
    try:
        return int(shutil.disk_usage(_existing_parent_dir(path)).free or 0)
    except Exception:
        return 0


def _docker_pull_space_buffer_bytes():
    try:
        value = str(os.environ.get("CLUB3090_DOCKER_PULL_BUFFER_GB") or "").strip()
        if value:
            gb = float(value)
        else:
            gb = float(config_float("docker", "pull_space_buffer_gb", 1, minimum=0.1))
    except Exception:
        gb = 1.0
    return int(max(0.1, gb) * 1024 * 1024 * 1024)


def _container_store_free_space():
    rows = []
    for path in ("/var/lib/containerd", "/var/lib/docker", "/"):
        try:
            if os.path.exists(path):
                usage = shutil.disk_usage(path)
                rows.append((int(usage.free), path))
        except Exception:
            continue
    if rows:
        return min(rows, key=lambda row: row[0])
    try:
        usage = shutil.disk_usage("/")
        return int(usage.free), "/"
    except Exception:
        return 0, "/"


def _docker_preflight_image_present(image):
    image = str(image or "").strip()
    if not image or image == "scratch" or "$" in image:
        return True
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _docker_ref_repository(image):
    ref = str(image or "").strip().split("@", 1)[0]
    slash = ref.rfind("/")
    colon = ref.rfind(":")
    if colon > slash:
        return ref[:colon]
    return ref


def _docker_manifest_inspect_json(image):
    image = str(image or "").strip()
    commands = (
        ["docker", "manifest", "inspect", image],
        ["docker", "buildx", "imagetools", "inspect", "--raw", image],
    )
    last_output = ""
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=90,
                check=False,
            )
        except Exception as exc:
            last_output = str(exc)
            continue
        last_output = str(proc.stdout or "")
        if proc.returncode != 0:
            continue
        try:
            return json.loads(last_output or "{}")
        except Exception as exc:
            last_output = f"{exc}: {last_output[-400:]}"
    raise RuntimeError(f"could not inspect remote Docker manifest for {image}: {last_output[-800:]}")


def _docker_manifest_platform_score(platform):
    platform = platform if isinstance(platform, dict) else {}
    os_name = str(platform.get("os") or "").lower()
    arch = str(platform.get("architecture") or "").lower()
    variant = str(platform.get("variant") or "").lower()
    if os_name == "linux" and arch == "amd64":
        return 0 if not variant else 1
    if os_name == "linux":
        return 10
    return 20


def _docker_remote_image_size_bytes(image):
    payload = _docker_manifest_inspect_json(image)
    manifests = payload.get("manifests") if isinstance(payload, dict) else None
    if isinstance(manifests, list) and manifests:
        rows = [row for row in manifests if isinstance(row, dict) and row.get("digest")]
        if rows:
            rows.sort(key=lambda row: _docker_manifest_platform_score(row.get("platform") or {}))
            digest = str(rows[0].get("digest") or "").strip()
            ref = f"{_docker_ref_repository(image)}@{digest}"
            payload = _docker_manifest_inspect_json(ref)
    if not isinstance(payload, dict):
        return 0
    total = 0
    config = payload.get("config")
    if isinstance(config, dict):
        try:
            total += max(0, int(config.get("size") or 0))
        except Exception:
            pass
    layers = payload.get("layers")
    if isinstance(layers, list):
        for layer in layers:
            if not isinstance(layer, dict):
                continue
            try:
                total += max(0, int(layer.get("size") or 0))
            except Exception:
                pass
    return total


def _format_bytes_gib(value):
    try:
        return f"{(int(value) / (1024 ** 3)):.1f} GiB"
    except Exception:
        return "0.0 GiB"


def _docker_pull_space_plan(images, include_build=False):
    unique = []
    seen = set()
    for image in images or []:
        image = str(image or "").strip()
        if not image or image == "scratch" or "$" in image or image in seen:
            continue
        seen.add(image)
        unique.append(image)
    missing = [image for image in unique if not _docker_preflight_image_present(image)]
    sizes = {}
    unknown = []
    total = 0
    for image in missing:
        try:
            size = int(_docker_remote_image_size_bytes(image) or 0)
        except Exception as exc:
            unknown.append(f"{image} ({exc})")
            continue
        if size <= 0:
            unknown.append(f"{image} (manifest reported no layer sizes)")
            continue
        sizes[image] = size
        total += size
    buffer_bytes = _docker_pull_space_buffer_bytes()
    if include_build and not missing:
        total = 0
    return {
        "images": unique,
        "missing": missing,
        "sizes": sizes,
        "unknown": unknown,
        "image_bytes": total,
        "buffer_bytes": buffer_bytes,
        "required_bytes": total + buffer_bytes,
    }


def docker_compose_config_images(compose_dir, compose_files, env=None, env_file=None, project_name=None, timeout=90):
    files = compose_files if isinstance(compose_files, (list, tuple)) else [compose_files]
    cmd = shlex.split(COMPOSE_BIN) if COMPOSE_BIN else ["docker", "compose"]
    compose_dir = str(compose_dir or CLUB3090_DIR)
    if project_name:
        cmd += ["-p", str(project_name)]
    if env_file:
        cmd += ["--env-file", str(env_file)]
    cmd += ["--project-directory", compose_dir]
    for compose_file in files:
        compose_file = str(compose_file or "").strip()
        if compose_file:
            cmd += ["-f", compose_file]
    cmd += ["config", "--images"]
    proc = subprocess.run(
        cmd,
        cwd=CLUB3090_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=max(15, int(timeout or 90)),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Docker compose image inspection failed: {(proc.stdout or '')[-1000:]}")
    return sorted({line.strip() for line in (proc.stdout or "").splitlines() if line.strip()})


def _preflight_docker_pull_space(label, images, include_build=False):
    plan = _docker_pull_space_plan(images, include_build=include_build)
    missing = plan.get("missing") or []
    unknown = plan.get("unknown") or []
    if not missing and not include_build:
        return plan
    if unknown:
        raise RuntimeError(
            f"{label} needs Docker image(s), but their remote size could not be measured before pulling: "
            + "; ".join(unknown)
        )
    free_bytes, free_path = _container_store_free_space()
    required_bytes = int(plan.get("required_bytes") or 0)
    if free_bytes < required_bytes:
        size_rows = ", ".join(
            f"{image}={_format_bytes_gib(size)}"
            for image, size in sorted((plan.get("sizes") or {}).items())
        )
        raise RuntimeError(
            f"{label} needs Docker image(s) before launch: {', '.join(missing) or 'compose build'}. "
            f"Measured pull size is {_format_bytes_gib(plan.get('image_bytes') or 0)}"
            f"{f' ({size_rows})' if size_rows else ''}; with a 1.0 GiB buffer it needs "
            f"{_format_bytes_gib(required_bytes)}, but {free_path} has only {_format_bytes_gib(free_bytes)} free. "
            "Free space or use a larger Docker store, then try again."
        )
    if missing:
        append_audit_text_line(
            f"{label} Docker pull space ok: {_format_bytes_gib(plan.get('image_bytes') or 0)} incoming "
            f"+ {_format_bytes_gib(plan.get('buffer_bytes') or 0)} buffer <= {_format_bytes_gib(free_bytes)} free on {free_path}"
        )
    return plan


def cli_docker_pull_space_preflight(argv):
    args = list(argv or [])
    if not args:
        raise SystemExit("usage: --docker-pull-space-preflight <label> <may-build:0|1> [image...]")
    label = args[0]
    may_build = str(args[1] if len(args) > 1 else "0").lower() in {"1", "true", "yes", "on"}
    images = args[2:] if len(args) > 2 else []
    plan = _preflight_docker_pull_space(label, images, include_build=may_build)
    print(json.dumps({
        "ok": True,
        "label": label,
        "missing": plan.get("missing") or [],
        "image_bytes": plan.get("image_bytes") or 0,
        "buffer_bytes": plan.get("buffer_bytes") or 0,
        "required_bytes": plan.get("required_bytes") or 0,
        "sizes": plan.get("sizes") or {},
    }, ensure_ascii=False))


def cli_docker_compose_pull_space_preflight(argv):
    args = list(argv or [])
    if len(args) < 4:
        raise SystemExit("usage: --docker-compose-pull-space-preflight <label> <compose-dir> <may-build:0|1> <compose-file> [compose-file...]")
    label = args[0]
    compose_dir = args[1]
    may_build = str(args[2]).lower() in {"1", "true", "yes", "on"}
    compose_files = args[3:]
    images = docker_compose_config_images(compose_dir, compose_files, env=os.environ.copy())
    plan = _preflight_docker_pull_space(label, images, include_build=may_build)
    print(json.dumps({
        "ok": True,
        "label": label,
        "images": images,
        "missing": plan.get("missing") or [],
        "image_bytes": plan.get("image_bytes") or 0,
        "buffer_bytes": plan.get("buffer_bytes") or 0,
        "required_bytes": plan.get("required_bytes") or 0,
        "sizes": plan.get("sizes") or {},
    }, ensure_ascii=False))


def _model_install_space_plan(plan, env_map):
    steps = [dict(step or {}) for step in (plan or []) if isinstance(step, dict)]
    if not steps:
        return {"ok": True, "steps": [], "required_bytes": 0, "available_bytes": 0}
    rows = []
    total_required = 0
    min_available = None
    for step in steps:
        repo_ids = list(step.get("repo_ids") or [])
        filenames = list(step.get("filenames") or [])
        total_bytes = sum(
            int(value or 0)
            for value in (_hf_repo_file_sizes(repo_ids, filenames, env_map) or {}).values()
        )
        local_dir = str(step.get("local_dir") or "").strip()
        loaded_bytes = _hf_download_step_loaded_bytes(step, env_map, total_bytes)
        required_bytes = max(0, int(total_bytes or 0) - int(loaded_bytes or 0))
        available_bytes = _filesystem_free_bytes(local_dir or CLUB3090_DIR)
        reserve_bytes = max(1024 * 1024 * 1024, int(total_bytes * 0.02)) if total_bytes > 0 else 0
        ok = total_bytes <= 0 or required_bytes <= max(0, available_bytes - reserve_bytes)
        rows.append(
            {
                "repo_ids": repo_ids,
                "filenames": filenames,
                "local_dir": local_dir,
                "total_bytes": int(total_bytes or 0),
                "loaded_bytes": int(loaded_bytes or 0),
                "required_bytes": int(required_bytes or 0),
                "available_bytes": int(available_bytes or 0),
                "reserve_bytes": int(reserve_bytes or 0),
                "ok": bool(ok),
            }
        )
        total_required += int(required_bytes or 0)
        min_available = available_bytes if min_available is None else min(min_available, available_bytes)
    return {
        "ok": all(bool(row.get("ok")) for row in rows if int(row.get("total_bytes") or 0) > 0),
        "steps": rows,
        "required_bytes": int(total_required or 0),
        "available_bytes": int(min_available or 0),
    }


def _format_model_install_space_error(space_plan):
    rows = [row for row in (space_plan or {}).get("steps") or [] if int(row.get("total_bytes") or 0) > 0]
    if not rows:
        return "The download size could not be estimated safely."
    worst = max(
        rows,
        key=lambda row: int(row.get("required_bytes") or 0) - int(row.get("available_bytes") or 0),
    )
    repos = ", ".join(str(repo_id or "").strip() for repo_id in (worst.get("repo_ids") or [])[:2] if str(repo_id or "").strip())
    repo_hint = f" for {repos}" if repos else ""
    return (
        "Not enough free disk space to start this download"
        f"{repo_hint}. Need about {_format_progress_bytes(worst.get('required_bytes') or 0)} more "
        f"but only {_format_progress_bytes(worst.get('available_bytes') or 0)} is currently free on the target filesystem."
    )


def _snapshot_model_install_cleanup_targets(plan):
    snapshot = []
    for target in _hf_download_target_paths(plan):
        path = str(target.get("path") or "").strip()
        if not path:
            continue
        snapshot.append(
            {
                "path": path,
                "existed": os.path.lexists(path),
            }
        )
    return snapshot


def _cleanup_model_install_targets(prefix, cleanup_targets):
    removed = []
    for item in cleanup_targets or []:
        path = str((item or {}).get("path") or "").strip()
        if not path or bool((item or {}).get("existed")):
            continue
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=False)
            else:
                os.remove(path)
            removed.append(path)
        except FileNotFoundError:
            continue
        except Exception as exc:
            append_audit_text_line(f"{prefix} cleanup skipped for {path}: {exc}")
    return removed


def _register_model_install_process(job_id, process):
    if not process:
        return
    with model_install_process_lock:
        model_install_processes[str(job_id or "").strip()] = process


def _clear_model_install_process(job_id, process=None):
    with model_install_process_lock:
        key = str(job_id or "").strip()
        current = model_install_processes.get(key)
        if process is not None and current is not process:
            return
        model_install_processes.pop(key, None)


def _terminate_model_install_process(job_id):
    with model_install_process_lock:
        process = model_install_processes.get(str(job_id or "").strip())
    if not process:
        return False
    try:
        process.terminate()
    except Exception:
        pass
    try:
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
    return True


def _sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _replace_file_with_hardlink(canonical_path, duplicate_path):
    canonical = str(canonical_path or "").strip()
    duplicate = str(duplicate_path or "").strip()
    if not canonical or not duplicate or canonical == duplicate:
        return False
    if not (os.path.isfile(canonical) and os.path.isfile(duplicate)):
        return False
    try:
        canonical_stat = os.stat(canonical)
        duplicate_stat = os.stat(duplicate)
    except Exception:
        return False
    if canonical_stat.st_ino == duplicate_stat.st_ino and canonical_stat.st_dev == duplicate_stat.st_dev:
        return False
    if _sha256_file(canonical) != _sha256_file(duplicate):
        return False
    temp_path = duplicate + ".club3090-hardlink-tmp"
    try:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        os.link(canonical, temp_path)
        os.replace(temp_path, duplicate)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
    return True


def _normalize_shared_mmproj_hardlinks(model_dir_root=""):
    root = str(model_dir_root or "").strip()
    if not root:
        try:
            root = _resolve_variant_model_dir_root({})
        except Exception:
            root = os.path.join(CLUB3090_DIR, "models-cache")
    if not os.path.isdir(root):
        return []
    normalized = []
    for family_name in sorted(os.listdir(root)):
        family_root = os.path.join(root, family_name)
        if not os.path.isdir(family_root):
            continue
        canonical_by_name = {}
        for name in os.listdir(family_root):
            canonical_path = os.path.join(family_root, name)
            if os.path.isfile(canonical_path) and re.fullmatch(r"mmproj.*\.gguf", str(name or ""), flags=re.I):
                canonical_by_name[str(name)] = canonical_path
        if not canonical_by_name:
            continue
        for current_root, _dirs, files in os.walk(family_root):
            if os.path.abspath(current_root) == os.path.abspath(family_root):
                continue
            for name in files:
                canonical_path = canonical_by_name.get(str(name))
                if not canonical_path:
                    continue
                duplicate_path = os.path.join(current_root, name)
                try:
                    replaced = _replace_file_with_hardlink(canonical_path, duplicate_path)
                except Exception:
                    replaced = False
                if replaced:
                    normalized.append(
                        f"hardlinked shared projector {duplicate_path} -> {canonical_path}"
                    )
    return normalized


def _normalize_duplicate_model_file_hardlinks(model_dir_root=""):
    root = str(model_dir_root or "").strip()
    if not root:
        try:
            root = _resolve_variant_model_dir_root({})
        except Exception:
            root = os.path.join(CLUB3090_DIR, "models-cache")
    if not os.path.isdir(root):
        return []
    candidates = {}
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if str(name or "") not in {".cache", ".runtime", "cache"}]
        for name in files:
            if os.path.splitext(str(name or ""))[1].lower() not in {".gguf", ".safetensors", ".bin", ".pt", ".pth", ".model"}:
                continue
            path = os.path.join(current_root, name)
            try:
                stat = os.stat(path)
            except Exception:
                continue
            if stat.st_size <= 0:
                continue
            candidates.setdefault((str(name), int(stat.st_size)), []).append(path)
    normalized = []
    for (_name, _size), paths in candidates.items():
        if len(paths) < 2:
            continue
        canonical = sorted(paths)[0]
        for duplicate in sorted(paths)[1:]:
            try:
                replaced = _replace_file_with_hardlink(canonical, duplicate)
            except Exception:
                replaced = False
            if replaced:
                normalized.append(f"hardlinked duplicate model asset {duplicate} -> {canonical}")
    return normalized


def _path_size_bytes(path):
    text = str(path or "").strip()
    if not text:
        return 0
    try:
        if os.path.isfile(text):
            return int(os.path.getsize(text) or 0)
        if os.path.isdir(text):
            total = 0
            for root, _dirs, files in os.walk(text):
                for name in files:
                    try:
                        total += int(os.path.getsize(os.path.join(root, name)) or 0)
                    except Exception:
                        continue
            return total
    except Exception:
        return 0
    return 0


def _resource_extension_hint(path):
    text = str(path or "").strip()
    if not text:
        return ""
    try:
        if os.path.isfile(text):
            return str(os.path.splitext(text)[1] or "").lower()
        if os.path.isdir(text):
            best_ext = ""
            best_size = -1
            for root, _dirs, files in os.walk(text):
                for name in files:
                    ext = str(os.path.splitext(name)[1] or "").lower()
                    if not ext:
                        continue
                    candidate = os.path.join(root, name)
                    try:
                        size = int(os.path.getsize(candidate) or 0)
                    except Exception:
                        size = 0
                    if size > best_size:
                        best_ext = ext
                        best_size = size
            return best_ext
    except Exception:
        return ""
    return ""


def _resource_display_label(path, label=""):
    resolved = str(path or "").strip()
    label_text = str(label or "").strip()
    if os.path.isdir(resolved) and label_text.lower() in {"", "download", "resource"}:
        base_label = str(os.path.basename(resolved) or resolved)
    else:
        base_label = str(label_text or os.path.basename(resolved) or resolved)
    if os.path.isdir(resolved):
        return base_label
    ext = _resource_extension_hint(resolved)
    if ext and ext not in base_label.lower():
        return f"{base_label}{ext}" if not base_label.endswith(ext) else base_label
    return base_label


def _resource_model_root_for_variant(row):
    variant = row if isinstance(row, dict) else {}
    host_model_dir = str(variant.get("host_model_dir") or "").strip()
    if host_model_dir:
        return os.path.realpath(os.path.abspath(host_model_dir))
    return os.path.realpath(os.path.abspath(os.path.join(CLUB3090_DIR, "models-cache")))


def _container_resource_subpath(value):
    text = str(value or "").replace("\\", "/").strip().strip('"').strip("'")
    if not text or "$" in text:
        return ""
    for prefix in (
        "/root/.cache/huggingface/",
        "root/.cache/huggingface/",
        "/models/",
        "models/",
    ):
        if text.startswith(prefix):
            return text[len(prefix):].strip("/")
    return ""


def _resource_identity_key(path):
    try:
        resolved = os.path.realpath(os.path.abspath(str(path or "")))
    except Exception:
        return ""
    if not resolved:
        return ""
    try:
        if os.path.isfile(resolved):
            stat_info = os.stat(resolved)
            return f"file:{stat_info.st_dev}:{stat_info.st_ino}:{int(stat_info.st_size or 0)}"
        if os.path.isdir(resolved):
            return f"dir:{resolved}"
        if os.path.lexists(resolved):
            return f"path:{resolved}"
    except Exception:
        pass
    return f"path:{resolved}"


def _preset_resource_allowed_roots(row):
    roots = [
        os.path.join(CLUB3090_DIR, "models-cache"),
        "/opt/ai/models-cache",
    ]
    host_root = str((row or {}).get("host_model_dir") or "").strip()
    if host_root:
        roots.append(host_root)
        parent = os.path.dirname(os.path.realpath(os.path.abspath(host_root)))
        if parent:
            roots.append(parent)
    normalized = []
    for root in roots:
        try:
            text = os.path.realpath(os.path.abspath(str(root or "")))
        except Exception:
            continue
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _preset_resource_path_allowed(path, row):
    try:
        target = os.path.realpath(os.path.abspath(str(path or "")))
    except Exception:
        return False
    if not target or target in {"/", os.path.expanduser("~")}:
        return False
    allowed_roots = _preset_resource_allowed_roots(row)
    host_root = str((row or {}).get("host_model_dir") or "").strip()
    host_root_abs = os.path.realpath(os.path.abspath(host_root)) if host_root else ""
    for root in allowed_roots:
        try:
            if os.path.commonpath([root, target]) != root:
                continue
            common_model_root = os.path.realpath(os.path.abspath(os.path.join(CLUB3090_DIR, "models-cache")))
            shared_model_root = os.path.realpath(os.path.abspath("/opt/ai/models-cache"))
            if target in {common_model_root, shared_model_root}:
                return False
            if target == root and target != host_root_abs:
                return False
            return True
        except Exception:
            continue
    return False


def variant_resource_plan_from_row(row, include_missing=False):
    variant = row if isinstance(row, dict) else {}
    model_root = _resource_model_root_for_variant(variant)
    resources = []
    seen = set()

    def add_path(path, role="", label=""):
        try:
            resolved = os.path.realpath(os.path.abspath(str(path or "")))
        except Exception:
            return
        if not resolved:
            return
        if not _preset_resource_path_allowed(resolved, variant):
            return
        exists = os.path.lexists(resolved)
        size = _path_size_bytes(resolved) if exists else 0
        if not include_missing and not exists and size <= 0:
            return
        if resolved in seen:
            existing = next((item for item in resources if item.get("path") == resolved), None)
            incoming_role = str(role or "").strip()
            incoming_label = str(label or "").strip()
            existing_role = str((existing or {}).get("role") or "").strip().lower()
            existing_label = str((existing or {}).get("label") or "").strip().lower()
            if existing and incoming_label and (
                existing_role in {"", "resource", "download"}
                or existing_label in {"", "resource", "download"}
                or incoming_role.lower() in {"model", "draft", "projector"}
            ):
                existing["role"] = incoming_role or existing.get("role") or "resource"
                existing["label"] = incoming_label
                existing["display_label"] = _resource_display_label(resolved, incoming_label)
            return
        seen.add(resolved)
        resources.append(
            {
                "path": resolved,
                "role": str(role or "resource"),
                "label": str(label or os.path.basename(resolved) or resolved),
                "display_label": _resource_display_label(resolved, label),
                "identity_key": _resource_identity_key(resolved),
                "exists": bool(exists),
                "size_bytes": int(size or 0),
                "kind": "directory" if os.path.isdir(resolved) else ("file" if os.path.isfile(resolved) else "missing"),
            }
        )

    install_command = variant.get("install_command") or ""
    plan = _parse_simple_hf_download_plan(install_command)
    if not plan:
        plan = _monitor_plan_from_variant_install(variant, install_command)
    for target in _hf_download_target_paths(plan):
        add_path(target.get("path"), "download", target.get("name") or "download")
    explicit_resource_subpaths = []
    for key, role in (
        ("model_path", "model"),
        ("draft_model_path", "draft"),
        ("mmproj_path", "projector"),
    ):
        subpath = _container_resource_subpath(variant.get(key))
        if not subpath:
            continue
        explicit_resource_subpaths.append((subpath, role))
        candidate = os.path.join(model_root, subpath.replace("/", os.sep))
        if os.path.lexists(candidate):
            add_path(candidate, role, subpath)
            continue
        filename = os.path.basename(subpath)
        if not filename:
            continue
        matches = glob.glob(os.path.join(model_root, "**", filename), recursive=True)
        if len(matches) == 1:
            add_path(matches[0], role, subpath)
    resources.sort(key=lambda item: (str(item.get("role") or ""), str(item.get("path") or "")))
    total = sum(int(item.get("size_bytes") or 0) for item in resources if item.get("exists"))
    return {
        "resources": resources,
        "resource_paths": [item["path"] for item in resources if item.get("exists")],
        "resource_size_bytes": int(total or 0),
        "resource_count": len([item for item in resources if item.get("exists")]),
    }


def _find_runtime_variant_for_resources(selector="", variant_id=""):
    wanted_selector = str(selector or "").strip()
    wanted_variant = str(variant_id or "").strip()
    inventory = load_runtime_inventory()
    for row in inventory.get("variants") or []:
        if wanted_variant and str(row.get("variant_id") or "") == wanted_variant:
            return dict(row)
        keys = {
            str(row.get("selector") or "").strip(),
            str(row.get("upstream_tag") or "").strip(),
            str(row.get("registry_key") or "").strip(),
            str(row.get("variant_id") or "").strip(),
        }
        if wanted_selector and wanted_selector in keys:
            return dict(row)
    raise ValueError("Preset was not found in the runtime inventory.")


def preset_resource_delete_plan(selector="", variant_id=""):
    row = _find_runtime_variant_for_resources(selector, variant_id)
    plan = variant_resource_plan_from_row(row, include_missing=False)
    return {
        "variant_id": str(row.get("variant_id") or ""),
        "selector": str(row.get("selector") or row.get("upstream_tag") or row.get("registry_key") or ""),
        "model_id": str(row.get("model_id") or ""),
        "display_name": str(row.get("model_display_name") or row.get("model_id") or ""),
        **plan,
    }


def _runtime_delete_guard_variant_keys(variant):
    keys = set()
    row = variant if isinstance(variant, dict) else {}
    for field in ("selector", "upstream_tag", "registry_key", "variant_id", "mode"):
        raw = str(row.get(field) or "").strip()
        if not raw:
            continue
        keys.add(raw)
        try:
            canonical = canonical_mode_selector(raw)
        except Exception:
            canonical = raw
        if canonical:
            keys.add(str(canonical).strip())
    return {key for key in keys if key}


def _runtime_delete_guard_running_rows():
    rows = []
    try:
        rows.extend(running_runtime_rows(instances_snapshot()))
    except Exception:
        pass
    try:
        active_selector = canonical_mode_selector(active_mode())
    except Exception:
        active_selector = ""
    try:
        active_container = current_container()
    except Exception:
        active_container = ""
    if active_selector and active_container:
        rows.append({"id": "GLOBAL", "mode": active_selector, "container": active_container})
    return [dict(row) for row in rows if row]


def ensure_preset_resources_not_running(variants, action="delete model resources"):
    variant_rows = [dict(row) for row in (variants or []) if isinstance(row, dict)]
    if not variant_rows:
        return
    affected_keys = set()
    affected_labels = {}
    for variant in variant_rows:
        selector = str(variant.get("selector") or variant.get("upstream_tag") or variant.get("registry_key") or variant.get("variant_id") or "").strip()
        for key in _runtime_delete_guard_variant_keys(variant):
            affected_keys.add(key)
            if selector:
                affected_labels.setdefault(key, selector)
    if not affected_keys:
        return
    blocked = []
    for row in _runtime_delete_guard_running_rows():
        mode = str(row.get("mode") or row.get("selector") or "").strip()
        if not mode:
            continue
        row_keys = {mode}
        try:
            row_keys.add(canonical_mode_selector(mode))
        except Exception:
            pass
        match = next((key for key in row_keys if key in affected_keys), "")
        if match:
            blocked.append(affected_labels.get(match) or mode)
    blocked = list(dict.fromkeys([item for item in blocked if item]))
    if blocked:
        label = ", ".join(blocked[:3])
        if len(blocked) > 3:
            label += f", +{len(blocked) - 3} more"
        raise RuntimeError(f"Stop the running preset {label} before {action}.")


def delete_preset_resources(selector="", variant_id=""):
    plan = preset_resource_delete_plan(selector, variant_id)
    removed = []
    errors = []
    row = _find_runtime_variant_for_resources(plan.get("selector"), plan.get("variant_id"))
    ensure_preset_resources_not_running([row], "deleting model resources")
    active_jobs = [
        job
        for job in (model_install_jobs_snapshot() or [])
        if job
        and bool(job.get("active"))
        and str(job.get("variant_id") or "") == str(plan.get("variant_id") or "")
    ]
    for job in active_jobs:
        try:
            stop_model_install_job(job.get("job_id"))
        except Exception as exc:
            errors.append(
                {
                    "path": plan.get("selector"),
                    "error": f"failed to stop install job {job.get('job_id')}: {exc}",
                }
            )
    for resource in plan.get("resources") or []:
        path = str(resource.get("path") or "").strip()
        if not resource.get("exists"):
            continue
        if not _preset_resource_path_allowed(path, row):
            errors.append({"path": path, "error": "outside allowed model resource roots"})
            continue
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            removed.append(resource)
        except FileNotFoundError:
            pass
        except Exception as exc:
            errors.append({"path": path, "error": str(exc)})
    try:
        rebuild_runtime_inventory()
    except Exception as exc:
        errors.append({"path": "runtime_inventory", "error": f"resource deletion succeeded but inventory rebuild failed: {exc}"})
    log_audit(
        "preset_resources_deleted",
        model_id=plan.get("model_id"),
        variant_id=plan.get("variant_id"),
        target=plan.get("selector"),
        result_summary=summarize_audit_result({"removed": len(removed), "errors": errors}),
    )
    return {
        "ok": not errors,
        "removed": removed,
        "errors": errors,
        "removed_size_bytes": sum(int(item.get("size_bytes") or 0) for item in removed),
        "removed_count": len(removed),
        "preset": {
            "selector": plan.get("selector"),
            "variant_id": plan.get("variant_id"),
            "model_id": plan.get("model_id"),
        },
    }


def delete_preset_resources_and_caches(selector="", variant_id=""):
    cache_result = delete_preset_caches(selector, variant_id)
    resource_result = delete_preset_resources(selector, variant_id)
    errors = list(cache_result.get("errors") or []) + list(resource_result.get("errors") or [])
    return {
        "ok": bool(cache_result.get("ok")) and bool(resource_result.get("ok")) and not errors,
        "cache_result": cache_result,
        "resource_result": resource_result,
        "errors": errors,
        "removed_size_bytes": int(cache_result.get("removed_size_bytes") or 0) + int(resource_result.get("removed_size_bytes") or 0),
        "removed_count": int(cache_result.get("removed_count") or 0) + int(resource_result.get("removed_count") or 0),
        "focus_log_source": "audit",
    }


def _fast_disk_usage_bytes(path, timeout=20):
    target = str(path or "").strip()
    if not target or not os.path.exists(target):
        return 0
    try:
        if os.path.isfile(target) or os.path.islink(target):
            return int(os.path.getsize(target) or 0)
    except Exception:
        return 0
    value = _storage_browser_probe_directory_size(target, timeout=timeout)
    if int(value or 0) <= 0:
        value = _path_size_bytes(target)
    return int(value or 0)


def _path_contains_model_payload(path, max_files=800):
    target = str(path or "").strip()
    if not target or not os.path.exists(target):
        return False
    model_exts = {".safetensors", ".gguf", ".bin", ".pt", ".pth", ".model", ".onnx", ".npy"}
    if os.path.isfile(target):
        return os.path.splitext(target)[1].lower() in model_exts
    try:
        checked = 0
        for root, _dirs, files in os.walk(target):
            for name in files:
                checked += 1
                if os.path.splitext(str(name or ""))[1].lower() in model_exts:
                    return True
                if checked >= int(max_files or 800):
                    return False
    except Exception:
        return False
    return False


def _preset_cache_instance_candidates(selector=""):
    try:
        target_selector = canonical_mode_selector(selector) if selector else ""
    except Exception:
        target_selector = str(selector or "").strip()
    candidates = []
    try:
        rows = read_instances_config()
    except Exception:
        rows = []
    for instance in rows if isinstance(rows, list) else []:
        try:
            instance_mode = canonical_mode_selector(instance.get("mode"))
        except Exception:
            instance_mode = str(instance.get("mode") or "").strip()
        if target_selector and instance_mode != target_selector:
            continue
        try:
            paths = instance_paths(instance)
            instance_id = str(instance.get("id") or "").strip()
            cache_path = instance_runtime_cache_host_root(instance_id) if instance_id else os.path.join(paths["dir"], "cache")
        except Exception:
            instance_id = str(instance.get("id") or "").strip()
            if not instance_id:
                continue
            cache_path = instance_runtime_cache_host_root(instance_id)
        instance_id = str(instance.get("id") or "").strip() or "instance"
        candidates.append(
            {
                "path": os.path.realpath(os.path.abspath(cache_path)),
                "role": "instance-cache",
                "label": f"{instance_id} runtime cache",
            }
        )
    return candidates


def _preset_cache_path_allowed(path, row):
    try:
        target = os.path.realpath(os.path.abspath(str(path or "")))
    except Exception:
        return False
    if not target or target in {"/", os.path.expanduser("~")}:
        return False
    allowed_roots = []
    control_cache_root = os.path.realpath(os.path.abspath(os.path.join(CONTROL_DIR, "runtime-cache")))
    allowed_roots.append(control_cache_root)
    runtime_root = variant_runtime_root_dir(row)
    if runtime_root:
        runtime_root_abs = os.path.realpath(os.path.abspath(runtime_root))
        club_root = os.path.realpath(os.path.abspath(CLUB3090_DIR))
        try:
            if os.path.commonpath([club_root, runtime_root_abs]) == club_root:
                allowed_roots.append(os.path.realpath(os.path.abspath(os.path.join(runtime_root_abs, "cache"))))
        except Exception:
            pass
    selector = str(row.get("selector") or row.get("upstream_tag") or row.get("registry_key") or "").strip()
    allowed_roots.extend(item["path"] for item in _preset_cache_instance_candidates(selector))
    for root in dict.fromkeys(allowed_roots):
        try:
            if target == root or os.path.commonpath([root, target]) == root:
                return True
        except Exception:
            continue
    return False


def preset_cache_delete_plan(selector="", variant_id=""):
    row = _find_runtime_variant_for_resources(selector, variant_id)
    cache_root = variant_persistent_cache_host_root(row)
    caches = []
    candidates = []
    if cache_root:
        candidates.append({"path": cache_root, "role": "runtime-cache", "label": "Runtime cache"})
    selector_key = str(row.get("selector") or row.get("upstream_tag") or row.get("registry_key") or "").strip()
    candidates.extend(_preset_cache_instance_candidates(selector_key))
    seen_paths = set()
    for candidate in candidates:
        path = os.path.realpath(os.path.abspath(candidate.get("path") or ""))
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        if _preset_cache_path_allowed(path, row):
            exists = os.path.lexists(path)
            caches.append(
                {
                    "path": path,
                    "role": str(candidate.get("role") or "runtime-cache"),
                    "label": str(candidate.get("label") or "Runtime cache"),
                    "exists": bool(exists),
                    "size_bytes": _fast_disk_usage_bytes(path) if exists else 0,
                    "kind": "directory" if os.path.isdir(path) else ("file" if os.path.isfile(path) else "missing"),
                }
            )
    total = sum(int(item.get("size_bytes") or 0) for item in caches if item.get("exists"))
    return {
        "variant_id": str(row.get("variant_id") or ""),
        "selector": str(row.get("selector") or row.get("upstream_tag") or row.get("registry_key") or ""),
        "model_id": str(row.get("model_id") or ""),
        "display_name": str(row.get("model_display_name") or row.get("model_id") or ""),
        "caches": caches,
        "cache_paths": [item["path"] for item in caches if item.get("exists")],
        "cache_size_bytes": int(total or 0),
        "cache_count": len([item for item in caches if item.get("exists")]),
    }


_preset_cache_size_summary_cache = {}


def preset_cache_size_summary_for_row(row, max_age=30.0):
    variant = row if isinstance(row, dict) else {}
    selector = str(variant.get("selector") or variant.get("upstream_tag") or variant.get("registry_key") or variant.get("variant_id") or "").strip()
    variant_id = str(variant.get("variant_id") or "").strip()
    cache_key = (selector, variant_id)
    now = time.time()
    cached = _preset_cache_size_summary_cache.get(cache_key)
    if cached and now - float(cached.get("time") or 0.0) <= float(max_age or 0.0):
        return dict(cached.get("value") or {})
    candidates = []
    cache_root = variant_persistent_cache_host_root(variant)
    if cache_root:
        candidates.append({"path": cache_root})
    candidates.extend(_preset_cache_instance_candidates(selector))
    seen_paths = set()
    total = 0
    count = 0
    cache_entries = []
    for candidate in candidates:
        try:
            path = os.path.realpath(os.path.abspath(candidate.get("path") or ""))
        except Exception:
            continue
        if not path or path in seen_paths or not _preset_cache_path_allowed(path, variant):
            continue
        seen_paths.add(path)
        if not os.path.lexists(path):
            continue
        count += 1
        size_bytes = int(_fast_disk_usage_bytes(path, timeout=2) or 0)
        total += size_bytes
        cache_entries.append({"path": path, "size_bytes": size_bytes})
    value = {
        "cache_size_bytes": int(total or 0),
        "cache_count": int(count or 0),
        "cache_paths": sorted(seen_paths),
        "cache_entries": sorted(cache_entries, key=lambda item: item["path"]),
    }
    _preset_cache_size_summary_cache[cache_key] = {"time": now, "value": dict(value)}
    return value


def enrich_runtime_inventory_cache_sizes(inventory):
    payload = inventory if isinstance(inventory, dict) else {}
    variants = payload.get("variants") if isinstance(payload.get("variants"), list) else []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        try:
            variant.update(preset_cache_size_summary_for_row(variant))
        except Exception:
            variant.setdefault("cache_size_bytes", 0)
            variant.setdefault("cache_count", 0)
            variant.setdefault("cache_paths", [])
            variant.setdefault("cache_entries", [])
    payload.update(model_cache_root_size_summary())
    return payload


def _persistent_model_cache_roots():
    models_root = os.path.join(CLUB3090_DIR, "models")
    roots = []
    for pattern in (
        os.path.join(models_root, "*", "cache"),
        os.path.join(models_root, "*", "vllm", "cache"),
    ):
        for path in glob.glob(pattern):
            if not os.path.isdir(path):
                continue
            roots.append(os.path.realpath(os.path.abspath(path)))
    return sorted(set(roots))


def model_cache_root_size_summary():
    roots = [
        os.path.join(CLUB3090_DIR, "models-cache"),
        "/opt/ai/models-cache",
    ]
    studio_roots = [
        os.environ.get("COMFYUI_MODELS_DIR", os.path.join(CLUB3090_DIR, "ai-studio-models", "comfyui", "models")),
        "/mnt/models/comfyui/models",
    ]
    seen = set()
    seen_stat_keys = set()
    cache_entries = []
    resource_entries = []
    resource_file_entries = []
    cache_total = 0
    resource_total = 0
    model_file_exts = {".gguf", ".safetensors", ".bin", ".pt", ".pth", ".model", ".onnx", ".npy"}

    def seen_key_for_path(path):
        try:
            stat_info = os.stat(path)
            return f"{stat_info.st_dev}:{stat_info.st_ino}"
        except Exception:
            return ""

    def mark_seen(path):
        try:
            resolved = os.path.realpath(os.path.abspath(str(path or "")))
        except Exception:
            resolved = ""
        stat_key = seen_key_for_path(resolved or path)
        if resolved:
            seen.add(resolved)
        if stat_key:
            seen_stat_keys.add(stat_key)

    def already_seen(path):
        try:
            resolved = os.path.realpath(os.path.abspath(str(path or "")))
        except Exception:
            resolved = ""
        if resolved and resolved in seen:
            return True
        stat_key = seen_key_for_path(resolved or path)
        return bool(stat_key and stat_key in seen_stat_keys)

    def is_cache_path(path):
        name = os.path.basename(str(path or "").rstrip(os.sep)).lower()
        if name in {".cache", "cache", ".runtime", "runtime-cache", "__pycache__"}:
            return True
        if name.startswith(("vllm-cache", "torchinductor", "triton", "cuda-cache")):
            return True
        return False

    def has_model_payload(path):
        return _path_contains_model_payload(path)

    def studio_modality_for_path(path):
        text = str(path or "").replace("\\", "/").lower()
        if any(token in text for token in ("video", "ltx", "sulphur", "wan", "hunyuan")):
            return "video"
        if any(token in text for token in ("speech", "voice", "tts", "kokoro", "step-voice", "narrat")):
            return "speech"
        if any(token in text for token in ("audio", "music", "sfx", "stable-audio", "ace-step")):
            return "audio"
        return "image"

    for root in roots:
        try:
            root_abs = os.path.realpath(os.path.abspath(root))
        except Exception:
            continue
        if not root_abs or not os.path.isdir(root_abs) or already_seen(root_abs):
            continue
        mark_seen(root_abs)
        try:
            names = sorted(os.listdir(root_abs))
        except Exception:
            names = []
        for name in names:
            path = os.path.join(root_abs, name)
            try:
                real = os.path.realpath(os.path.abspath(path))
            except Exception:
                continue
            if not real or already_seen(real):
                continue
            mark_seen(real)
            if not os.path.lexists(path):
                continue
            size = int(_fast_disk_usage_bytes(path, timeout=2) or 0)
            entry = {
                "path": path,
                "real_path": real,
                "size_bytes": size,
                "kind": "directory" if os.path.isdir(path) else ("file" if os.path.isfile(path) else "missing"),
            }
            if is_cache_path(path) and not has_model_payload(path):
                cache_total += size
                cache_entries.append(entry)
            else:
                resource_total += size
                resource_entries.append(entry)
                if os.path.isdir(path):
                    try:
                        for dirpath, dirnames, filenames in os.walk(path):
                            dirnames[:] = [
                                dirname
                                for dirname in dirnames
                                if not is_cache_path(os.path.join(dirpath, dirname))
                            ]
                            safetensor_files = [name for name in filenames if os.path.splitext(str(name or ""))[1].lower() == ".safetensors"]
                            for filename in filenames:
                                ext = os.path.splitext(filename)[1].lower()
                                if ext == ".safetensors" and not (len(safetensor_files) == 1 and filename == "model.safetensors"):
                                    continue
                                if ext not in model_file_exts and not (ext == ".safetensors" and filename == "model.safetensors"):
                                    continue
                                file_path = os.path.join(dirpath, filename)
                                try:
                                    file_real = os.path.realpath(os.path.abspath(file_path))
                                    file_size = int(os.path.getsize(file_path) or 0)
                                except Exception:
                                    continue
                                resource_file_entries.append(
                                    {
                                        "path": file_path,
                                        "real_path": file_real,
                                        "size_bytes": file_size,
                                        "kind": "file",
                                        "root_path": path,
                                    }
                                )
                    except Exception:
                        pass
                elif os.path.isfile(path) and os.path.splitext(path)[1].lower() in model_file_exts:
                    resource_file_entries.append(
                        {
                            "path": path,
                            "real_path": real,
                            "size_bytes": size,
                            "kind": "file",
                            "root_path": path,
                        }
                    )
    for root in studio_roots:
        try:
            root_abs = os.path.realpath(os.path.abspath(root))
        except Exception:
            continue
        if not root_abs or not os.path.isdir(root_abs) or already_seen(root_abs):
            continue
        mark_seen(root_abs)
        root_size = int(_fast_disk_usage_bytes(root_abs, timeout=3) or 0)
        if root_size > 0:
            resource_total += root_size
            resource_entries.append({
                "path": root_abs,
                "real_path": root_abs,
                "size_bytes": root_size,
                "kind": "directory",
                "role": "studio-model-root",
                "modality": "image",
            })
        try:
            for dirpath, dirnames, filenames in os.walk(root_abs):
                dirnames[:] = [
                    dirname
                    for dirname in dirnames
                    if not is_cache_path(os.path.join(dirpath, dirname))
                ]
                for filename in filenames:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in model_file_exts:
                        continue
                    file_path = os.path.join(dirpath, filename)
                    try:
                        file_real = os.path.realpath(os.path.abspath(file_path))
                        file_size = int(os.path.getsize(file_path) or 0)
                    except Exception:
                        continue
                    if not file_real or already_seen(file_real):
                        continue
                    mark_seen(file_real)
                    resource_file_entries.append(
                        {
                            "path": file_path,
                            "real_path": file_real,
                            "size_bytes": file_size,
                            "kind": "file",
                            "root_path": root_abs,
                            "role": "studio-model",
                            "modality": studio_modality_for_path(file_path),
                        }
                    )
        except Exception:
            pass
    for path in _persistent_model_cache_roots():
        try:
            real = os.path.realpath(os.path.abspath(path))
        except Exception:
            continue
        if not real or not os.path.isdir(real) or already_seen(real):
            continue
        mark_seen(real)
        size = int(_fast_disk_usage_bytes(real, timeout=2) or 0)
        cache_total += size
        cache_entries.append(
            {
                "path": path,
                "real_path": real,
                "size_bytes": size,
                "kind": "directory",
            }
        )
    return {
        "model_cache_size_bytes": int(cache_total or 0),
        "model_cache_entries": sorted(cache_entries, key=lambda item: item["path"]),
        "model_resource_root_size_bytes": int(resource_total or 0),
        "model_resource_root_entries": sorted(resource_entries, key=lambda item: item["path"]),
        "model_resource_file_entries": sorted(resource_file_entries, key=lambda item: item["path"]),
    }


def _model_cache_path_allowed(path):
    try:
        target = os.path.realpath(os.path.abspath(str(path or "")))
    except Exception:
        return False
    if not target or target in {"/", os.path.expanduser("~")}:
        return False
    if target in _persistent_model_cache_roots():
        return True
    for root in (os.path.join(CLUB3090_DIR, "models-cache"), "/opt/ai/models-cache"):
        try:
            root_abs = os.path.realpath(os.path.abspath(root))
            if target == root_abs:
                return False
            if os.path.commonpath([root_abs, target]) == root_abs:
                name = os.path.basename(target.rstrip(os.sep)).lower()
                if name not in {".cache", "cache", ".runtime", "runtime-cache", "__pycache__"} and not name.startswith(("vllm-cache", "torchinductor", "triton", "cuda-cache")):
                    return False
                if _path_contains_model_payload(target):
                    return False
                return True
        except Exception:
            continue
    return False


def _model_resource_path_allowed_generic(path):
    try:
        target = os.path.realpath(os.path.abspath(str(path or "")))
    except Exception:
        return False
    if not target or target in {"/", os.path.expanduser("~")}:
        return False
    roots = [
        os.path.join(CLUB3090_DIR, "models-cache"),
        os.path.join(CLUB3090_DIR, "ai-studio-models"),
        "/opt/ai/models-cache",
        os.environ.get("COMFYUI_MODELS_DIR", os.path.join(CLUB3090_DIR, "ai-studio-models", "comfyui", "models")),
        "/mnt/models/comfyui/models",
    ]
    for root in roots:
        try:
            root_abs = os.path.realpath(os.path.abspath(str(root or "")))
        except Exception:
            continue
        if not root_abs or target == root_abs:
            continue
        try:
            if os.path.commonpath([root_abs, target]) == root_abs:
                return True
        except Exception:
            continue
    return False


def delete_model_cache_paths(paths):
    requested_paths = [
        os.path.realpath(os.path.abspath(str(path or "").strip()))
        for path in (paths or [])
        if str(path or "").strip()
    ]
    requested_paths = list(dict.fromkeys([path for path in requested_paths if path]))
    if not requested_paths:
        raise ValueError("Choose at least one model cache path to delete.")
    inventory = load_runtime_inventory(force=True)
    affected_variants = []
    def _path_matches_requested(candidate):
        if not candidate:
            return False
        for requested in requested_paths:
            if candidate == requested:
                return True
            try:
                if os.path.commonpath([requested, candidate]) == requested:
                    return True
            except Exception:
                continue
        return False
    for variant in inventory.get("variants") or []:
        resource_paths = {
            os.path.realpath(os.path.abspath(str(item.get("path") or "").strip()))
            for item in (variant_resource_plan_from_row(variant, include_missing=True).get("resources") or [])
            if str(item.get("path") or "").strip()
        }
        cache_paths = {
            os.path.realpath(os.path.abspath(str(item.get("path") or "").strip()))
            for item in (preset_cache_size_summary_for_row(variant, max_age=0).get("cache_entries") or [])
            if str(item.get("path") or "").strip()
        }
        if any(_path_matches_requested(path) for path in [*resource_paths, *cache_paths]):
            affected_variants.append(dict(variant))
    ensure_preset_resources_not_running(affected_variants, "deleting model cache paths")
    removed = []
    errors = []
    for path in requested_paths:
        if not _model_cache_path_allowed(path):
            errors.append({"path": path, "error": "outside allowed model cache roots"})
            continue
        try:
            size_bytes = _fast_disk_usage_bytes(path, timeout=5) if os.path.lexists(path) else 0
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            removed.append({"path": path, "size_bytes": int(size_bytes or 0)})
        except FileNotFoundError:
            pass
        except Exception as exc:
            errors.append({"path": path, "error": str(exc)})
    if removed:
        _preset_cache_size_summary_cache.clear()
        _storage_browser_clear_size_cache()
    try:
        rebuild_runtime_inventory()
    except Exception:
        pass
    log_audit(
        "model_cache_paths_deleted",
        result_summary=summarize_audit_result({"removed": len(removed), "errors": errors}),
    )
    return {
        "ok": not errors,
        "removed": removed,
        "errors": errors,
        "removed_size_bytes": sum(int(item.get("size_bytes") or 0) for item in removed),
        "removed_count": len(removed),
    }


def delete_preset_caches(selector="", variant_id=""):
    plan = preset_cache_delete_plan(selector, variant_id)
    row = _find_runtime_variant_for_resources(plan.get("selector"), plan.get("variant_id"))
    removed = []
    errors = []
    ensure_preset_resources_not_running([row], "clearing preset caches")
    for cache in plan.get("caches") or []:
        path = str(cache.get("path") or "").strip()
        if not cache.get("exists"):
            continue
        if not _preset_cache_path_allowed(path, row):
            errors.append({"path": path, "error": "outside allowed preset cache roots"})
            continue
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            removed.append(cache)
        except FileNotFoundError:
            pass
        except Exception as exc:
            errors.append({"path": path, "error": str(exc)})
    if removed:
        _preset_cache_size_summary_cache.clear()
        _storage_browser_clear_size_cache()
    log_audit(
        "preset_caches_cleared",
        model_id=plan.get("model_id"),
        variant_id=plan.get("variant_id"),
        target=plan.get("selector"),
        result_summary=summarize_audit_result({"removed": len(removed), "errors": errors}),
    )
    return {
        "ok": not errors,
        "removed": removed,
        "errors": errors,
        "removed_size_bytes": sum(int(item.get("size_bytes") or 0) for item in removed),
        "removed_count": len(removed),
        "preset": {
            "selector": plan.get("selector"),
            "variant_id": plan.get("variant_id"),
            "model_id": plan.get("model_id"),
        },
    }


def delete_model_resource_paths(paths):
    requested_paths = [
        os.path.realpath(os.path.abspath(str(path or "").strip()))
        for path in (paths or [])
        if str(path or "").strip()
    ]
    requested_paths = list(dict.fromkeys([path for path in requested_paths if path]))
    if not requested_paths:
        raise ValueError("Choose at least one resource path to delete.")
    inventory = load_runtime_inventory(force=True)
    affected_variants = []
    for variant in inventory.get("variants") or []:
        resources = variant_resource_plan_from_row(variant, include_missing=True).get("resources") or []
        resource_paths = {
            os.path.realpath(os.path.abspath(str(item.get("path") or "").strip()))
            for item in resources
            if str(item.get("path") or "").strip()
        }
        matched = False
        for requested in requested_paths:
            for resource_path in resource_paths:
                if requested == resource_path:
                    matched = True
                    break
                try:
                    if os.path.commonpath([resource_path, requested]) == resource_path:
                        matched = True
                        break
                except Exception:
                    continue
            if matched:
                break
        if matched:
            affected_variants.append(dict(variant))
    errors = []
    removed = []
    ensure_preset_resources_not_running(affected_variants, "deleting model resources")
    for job in (model_install_jobs_snapshot() or []):
        if not job or not bool(job.get("active")):
            continue
        if any(str(job.get("variant_id") or "") == str(variant.get("variant_id") or "") for variant in affected_variants):
            try:
                stop_model_install_job(job.get("job_id"))
            except Exception as exc:
                errors.append({"path": str(job.get("job_id") or ""), "error": f"failed to stop install job: {exc}"})
    path_to_variant = {}
    for variant in affected_variants:
        for item in (variant_resource_plan_from_row(variant, include_missing=True).get("resources") or []):
            item_path = os.path.realpath(os.path.abspath(str(item.get("path") or "").strip()))
            if item_path and item_path not in path_to_variant:
                path_to_variant[item_path] = dict(variant)
            for requested in requested_paths:
                if requested in path_to_variant:
                    continue
                try:
                    if item_path and os.path.commonpath([item_path, requested]) == item_path:
                        path_to_variant[requested] = dict(variant)
                except Exception:
                    continue
    for path in requested_paths:
        variant = path_to_variant.get(path) or {}
        if variant and not _preset_resource_path_allowed(path, variant):
            errors.append({"path": path, "error": "outside allowed model resource roots"})
            continue
        if not variant and not _model_resource_path_allowed_generic(path):
            errors.append({"path": path, "error": "outside allowed model resource roots"})
            continue
        try:
            size_bytes = _fast_disk_usage_bytes(path, timeout=5) if os.path.lexists(path) else 0
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            removed.append({"path": path, "size_bytes": int(size_bytes or 0)})
        except FileNotFoundError:
            pass
        except Exception as exc:
            errors.append({"path": path, "error": str(exc)})
    try:
        rebuild_runtime_inventory()
        _preset_cache_size_summary_cache.clear()
    except Exception as exc:
        errors.append({"path": "runtime_inventory", "error": f"resource deletion succeeded but inventory rebuild failed: {exc}"})
    log_audit(
        "model_resource_paths_deleted",
        variants=len(affected_variants),
        paths=len(requested_paths),
        result_summary=summarize_audit_result({"removed": len(removed), "errors": errors}),
    )
    return {
        "ok": not errors,
        "removed": removed,
        "errors": errors,
        "removed_size_bytes": sum(int(item.get("size_bytes") or 0) for item in removed),
        "removed_count": len(removed),
        "focus_log_source": "audit",
    }


def delete_model_resource_paths_and_caches(paths, selectors=None):
    selector_rows = [str(selector or "").strip() for selector in (selectors or []) if str(selector or "").strip()]
    cache_results = []
    errors = []
    for selector in dict.fromkeys(selector_rows):
        try:
            result = delete_preset_caches(selector)
            cache_results.append(result)
            errors.extend(result.get("errors") or [])
        except Exception as exc:
            errors.append({"path": selector, "error": str(exc)})
    resource_result = delete_model_resource_paths(paths)
    errors.extend(resource_result.get("errors") or [])
    return {
        "ok": bool(resource_result.get("ok")) and not errors,
        "cache_results": cache_results,
        "resource_result": resource_result,
        "errors": errors,
        "removed_size_bytes": int(resource_result.get("removed_size_bytes") or 0) + sum(int(item.get("removed_size_bytes") or 0) for item in cache_results),
        "removed_count": int(resource_result.get("removed_count") or 0) + sum(int(item.get("removed_count") or 0) for item in cache_results),
        "focus_log_source": "audit",
    }


def _monitor_hf_download_progress(process, job_id, prefix, plan, env_map):
    if not plan:
        return
    step_totals = []
    try:
        for step in plan:
            sizes = _hf_repo_file_sizes(step.get("repo_ids") or [], step.get("filenames") or [], env_map)
            api_total = sum(int(value or 0) for value in sizes.values()) if sizes else 0
            hint_total = int((step or {}).get("expected_total_bytes") or 0)
            step_totals.append(api_total or hint_total)
    except Exception:
        step_totals = [int((step or {}).get("expected_total_bytes") or 0) for step in plan]
    total_bytes = sum(int(value or 0) for value in step_totals)
    estimated_total = total_bytes <= 0
    started_at = time.time()
    next_percent = 5
    last_state_percent = -1
    last_loaded_bytes = 0
    estimated_progress = 1
    while True:
        loaded_bytes = sum(
            _hf_download_step_loaded_bytes(step, env_map, step_totals[index] if index < len(step_totals) else 0)
            for index, step in enumerate(plan)
        )
        if estimated_total:
            if loaded_bytes > last_loaded_bytes:
                estimated_progress = min(95, max(1, estimated_progress + 1))
                last_loaded_bytes = loaded_bytes
            percent = estimated_progress if loaded_bytes > 0 else 1
        else:
            percent = int(min(100, max(0, math.floor((loaded_bytes / total_bytes) * 100)))) if total_bytes else 0
        if percent != last_state_percent:
            _set_model_install_job_entry(
                job_id,
                progress_percent=percent,
                progress_loaded_bytes=int(loaded_bytes or 0),
                progress_total_bytes=int(total_bytes or 0),
                summary=f"Downloading model: {percent}%{' estimated' if estimated_total else ''}...",
            )
            last_state_percent = percent
        while percent >= next_percent and next_percent <= 100:
            append_audit_text_line(
                f"{prefix} progress {next_percent}%{' estimated' if estimated_total else ''} ({_format_progress_bytes(loaded_bytes)} / {_format_progress_bytes(total_bytes) if total_bytes else 'unknown'}) elapsed {max(1, int(time.time() - started_at))}s"
            )
            next_percent += 5
        if process.poll() is not None:
            break
        time.sleep(2.0)
    loaded_bytes = sum(
        _hf_download_step_loaded_bytes(step, env_map, step_totals[index] if index < len(step_totals) else 0)
        for index, step in enumerate(plan)
    )
    if loaded_bytes > 0 and next_percent <= 100:
        final_percent = int(min(100, max(0, math.floor((loaded_bytes / total_bytes) * 100)))) if total_bytes else 100
        if final_percent >= 100:
            append_audit_text_line(
                f"{prefix} progress 100% ({_format_progress_bytes(loaded_bytes)} / {_format_progress_bytes(total_bytes)}) elapsed {max(1, int(time.time() - started_at))}s"
            )


def _resolve_hf_cli_binary():
    for candidate in ("hf", "huggingface-cli"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    extra_candidates = []
    sudo_user = str(os.environ.get("SUDO_USER") or "").strip()
    if sudo_user and sudo_user.lower() != "root":
        extra_candidates.extend(
            [
                f"/home/{sudo_user}/.local/bin/hf",
                f"/home/{sudo_user}/.local/bin/huggingface-cli",
            ]
        )
        try:
            user_base = site.USER_BASE
        except Exception:
            user_base = ""
        if user_base:
            extra_candidates.extend(
                [
                    os.path.join(user_base, "bin", "hf"),
                    os.path.join(user_base, "bin", "huggingface-cli"),
                ]
            )
    extra_candidates.extend(
        [
            "/root/.local/bin/hf",
            "/root/.local/bin/huggingface-cli",
            *sorted(glob.glob("/home/*/.venvs/*/bin/hf")),
            *sorted(glob.glob("/home/*/.venvs/*/bin/huggingface-cli")),
            *sorted(glob.glob("/root/.venvs/*/bin/hf")),
            *sorted(glob.glob("/root/.venvs/*/bin/huggingface-cli")),
        ]
    )
    for candidate in extra_candidates:
        path = str(candidate or "").strip()
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    raise RuntimeError(
        "Neither 'hf' nor 'huggingface-cli' is installed on the server, so the built-in model downloader cannot start."
    )


def _run_hf_download_step(job_id, prefix, step, env_map, progress_plan=None):
    row = step if isinstance(step, dict) else {}
    repo_ids = [
        str(repo_id or "").strip()
        for repo_id in (row.get("repo_ids") or [])
        if str(repo_id or "").strip()
    ]
    local_dir = str(row.get("local_dir") or "").strip()
    filenames = [
        str(name or "").strip().lstrip("/")
        for name in (row.get("filenames") or [])
        if str(name or "").strip()
    ]
    if not repo_ids or not local_dir:
        raise RuntimeError("Built-in download step is missing a repo id or local target path.")
    os.makedirs(local_dir, exist_ok=True)
    hf_cli = _resolve_hf_cli_binary()
    env = dict(env_map or {})
    env.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
    env.setdefault("HF_HUB_DISABLE_XET", "1")
    last_error = ""
    for repo_id in repo_ids:
        attempts = 2
        for attempt in range(1, attempts + 1):
            if _model_install_stop_requested(job_id):
                raise RuntimeError("model install stopped by request")
            argv = [hf_cli, "download", repo_id]
            argv.extend(filenames)
            argv.extend(["--local-dir", local_dir])
            append_audit_text_line(
                f"{prefix} built-in downloader fetching {repo_id} -> {local_dir} (attempt {attempt}/{attempts})"
            )
            process = subprocess.Popen(
                argv,
                cwd=CLUB3090_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                bufsize=0,
            )
            _register_model_install_process(job_id, process)
            monitor = threading.Thread(
                target=_monitor_hf_download_progress,
                args=(process, job_id, prefix, list(progress_plan or [dict(row, repo_ids=[repo_id])]), env),
                name=f"club3090-hf-step-{_selector_token(repo_id)}",
                daemon=True,
            )
            monitor.start()
            try:
                _stream_process_output_to_audit(process, prefix)
            finally:
                rc = int(process.wait())
                _clear_model_install_process(job_id, process)
                monitor.join(timeout=5)
            if rc == 0:
                return 0
            last_error = f"hf download failed for {repo_id} (rc={rc})"
            if attempt < attempts and not _model_install_stop_requested(job_id):
                append_audit_text_line(f"{prefix} {last_error}; retrying")
                time.sleep(2)
        if len(repo_ids) > 1:
            append_audit_text_line(f"{prefix} {last_error}; trying next source")
    raise RuntimeError(last_error or "hf download failed")


def _run_hf_download_plan(job_id, prefix, plan, env_map):
    steps = [dict(step or {}) for step in (plan or []) if isinstance(step, dict)]
    if not steps:
        return 0
    append_audit_text_line(
        f"{prefix} using built-in downloader for {len(steps)} Hugging Face step{'s' if len(steps) != 1 else ''}"
    )
    for step in steps:
        _run_hf_download_step(job_id, prefix, step, env_map, progress_plan=steps)
    return 0


def trim_audit_text_value(value, limit=180):
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > int(limit or 180):
        text = text[: max(0, int(limit or 180) - 14)] + " …<truncated>"
    return text


def humanize_audit_event_name(event_name):
    text = str(event_name or "").strip().replace("debug_", "debug ")
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.capitalize() if text else "Event"


def audit_identity_label(entry):
    for key in (
        "conversation_id",
        "user",
        "group",
        "server",
        "instance",
        "service",
        "profile",
        "model_id",
        "variant_id",
        "target",
        "path",
    ):
        value = entry.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def audit_detail_bits(entry):
    labels = {
        "action": "action",
        "instance": "instance",
        "mode": "mode",
        "profile": "profile",
        "service": "service",
        "target": "target",
        "reason": "reason",
        "status": "status",
        "provider": "provider",
        "url": "url",
        "target_commit": "commit",
        "via": "via",
        "models": "models",
        "variants": "variants",
    }
    bits = []
    for key in (
        "action",
        "instance",
        "mode",
        "profile",
        "service",
        "target",
        "reason",
        "status",
        "provider",
        "url",
        "target_commit",
        "via",
        "models",
        "variants",
    ):
        value = entry.get(key)
        if value in (None, ""):
            continue
        bits.append(f"{labels.get(key, key)}={trim_audit_text_value(value, 120)}")
    result_summary = entry.get("result_summary")
    if result_summary not in (None, ""):
        bits.append(f"result={trim_audit_text_value(result_summary, 200)}")
    return bits


def format_audit_text_entry(entry):
    entry = entry if isinstance(entry, dict) else {}
    ts = int(entry.get("ts") or time.time())
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    category = str(entry.get("category") or "system").strip() or "system"
    event_name = str(entry.get("event") or "").strip()
    message = humanize_audit_event_name(event_name)
    identity = audit_identity_label(entry)
    if identity:
        message = f"{message}: {trim_audit_text_value(identity, 120)}"
    detail = audit_detail_bits(entry)
    suffix = f" | {' | '.join(detail)}" if detail else ""
    return f"{stamp} [{category}] {message}{suffix}"


def summarize_audit_result(value, limit=1200):
    try:
        text = json.dumps(value, sort_keys=True)
    except Exception:
        text = str(value)
    text = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > int(limit or 1200):
        text = text[: max(0, int(limit or 1200) - 16)] + " …<truncated>"
    return text


def read_switch_failure():
    data = read_json_file(SWITCH_FAILURE_FILE, {})
    return data if isinstance(data, dict) else {}


def write_switch_failure(mode, error_text):
    payload = {
        "mode": canonical_mode_selector(mode),
        "error": str(error_text or "")[-12000:],
        "ts": int(time.time()),
    }
    write_json_file(SWITCH_FAILURE_FILE, payload)
    return payload


def clear_switch_failure(mode=""):
    existing = read_switch_failure()
    if not existing:
        return
    target_mode = canonical_mode_selector(mode) if mode else ""
    if target_mode and str(existing.get("mode") or "") != target_mode:
        return
    try:
        os.remove(SWITCH_FAILURE_FILE)
    except FileNotFoundError:
        pass
    except Exception:
        pass


def decode_embedded_code_syntax_config():
    payload = str(CODE_SYNTAX_CONFIG_GZIP_BASE64 or "").strip()
    if not payload:
        return ""
    try:
        raw = gzip.decompress(base64.b64decode(payload.encode("ascii")))
        text = raw.decode("utf-8")
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return ""
        return json.dumps(parsed, ensure_ascii=False, indent=2) + "\n"
    except Exception:
        return ""


def ensure_code_syntax_config_file():
    os.makedirs(CONTROL_DIR, exist_ok=True)
    rendered = decode_embedded_code_syntax_config()
    if not rendered:
        return CODE_SYNTAX_CONFIG_FILE if os.path.exists(CODE_SYNTAX_CONFIG_FILE) else ""
    try:
        with open(CODE_SYNTAX_CONFIG_FILE, "r", encoding="utf-8") as handle:
            existing = handle.read()
        if existing == rendered:
            return CODE_SYNTAX_CONFIG_FILE
    except Exception:
        pass
    with open(CODE_SYNTAX_CONFIG_FILE, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)
    return CODE_SYNTAX_CONFIG_FILE


def read_effective_code_syntax_config_bytes():
    syntax_path = ensure_code_syntax_config_file()
    if not syntax_path or not os.path.exists(syntax_path):
        return b""
    try:
        with open(syntax_path, "rb") as handle:
            return handle.read()
    except Exception:
        return b""


def write_json_atomic_if_changed(path, data, *, indent=None, sort_keys=False, separators=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rendered = json.dumps(
        data,
        indent=indent,
        sort_keys=sort_keys,
        separators=separators,
        ensure_ascii=False,
    )
    if indent is not None:
        rendered += "\n"
    try:
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()
        if existing == rendered:
            return False
    except Exception:
        pass
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(rendered)
        last_error = None
        for attempt in range(6):
            try:
                os.replace(tmp, path)
                return True
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.05 * (attempt + 1))
        if last_error:
            raise last_error
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except Exception:
            pass
    return True


def model_install_job_snapshot():
    with model_install_job_lock:
        return dict(model_install_job)


def model_install_jobs_snapshot():
    with model_install_job_lock:
        return [
            dict(model_install_jobs[job_id])
            for job_id in reversed(model_install_job_order)
            if job_id in model_install_jobs
        ]


def model_install_jobs_active():
    with model_install_job_lock:
        return any(bool(job.get("active")) for job in model_install_jobs.values())


def _refresh_model_install_job_summary_locked():
    active_jobs = [
        dict(job)
        for job in model_install_jobs.values()
        if bool(job.get("active"))
    ]
    latest_job = None
    for job_id in reversed(model_install_job_order):
        job = model_install_jobs.get(job_id)
        if job:
            latest_job = dict(job)
            break
    if active_jobs:
        active_jobs.sort(
            key=lambda job: (
                int(job.get("started_at") or 0),
                str(job.get("job_id") or ""),
            )
        )
        summary = dict(active_jobs[0])
        summary["active"] = True
        summary["summary"] = (
            f"{len(active_jobs)} model download job"
            f"{'' if len(active_jobs) == 1 else 's'} running"
        )
    elif latest_job:
        summary = dict(latest_job)
    else:
        summary = {
            "active": False,
            "status": "idle",
            "job_id": "",
            "model_id": "",
            "variant_id": "",
            "command": "",
            "started_at": 0,
            "finished_at": 0,
            "return_code": None,
            "summary": "",
            "inventory_rebuild_ok": None,
        }
    model_install_job.clear()
    model_install_job.update(summary)


def _set_model_install_job_entry(job_id, **updates):
    with model_install_job_lock:
        key = str(job_id or "").strip()
        if not key:
            raise ValueError("model install job id is required")
        current = dict(model_install_jobs.get(key) or {})
        current.update(updates)
        current["job_id"] = key
        model_install_jobs[key] = current
        if key in model_install_job_order:
            try:
                model_install_job_order.remove(key)
            except ValueError:
                pass
        model_install_job_order.append(key)
        retained = set(model_install_job_order)
        for stale_key in [job_key for job_key in list(model_install_jobs.keys()) if job_key not in retained]:
            model_install_jobs.pop(stale_key, None)
        _refresh_model_install_job_summary_locked()
        return dict(current)


def stop_model_install_job(job_id):
    key = str(job_id or "").strip()
    if not key:
        raise ValueError("Model install job id is required.")
    with model_install_job_lock:
        job = dict(model_install_jobs.get(key) or {})
    if not job:
        raise ValueError("Model install job not found.")
    if not bool(job.get("active")):
        return dict(job)
    _set_model_install_job_entry(
        key,
        stop_requested=True,
        summary="Stopping model install job",
    )
    stopped = _terminate_model_install_process(key)
    append_audit_text_line(
        f"[model-install {job.get('model_id') or 'unknown'}] stop requested for job {key}{'' if stopped else ' (waiting for current step to exit)'}"
    )
    return dict(model_install_job_snapshot())


def _model_install_stop_requested(job_id):
    with model_install_job_lock:
        job = dict(model_install_jobs.get(str(job_id or "").strip()) or {})
    return bool(job.get("stop_requested"))


def custom_model_job_snapshot():
    with custom_model_job_lock:
        return dict(custom_model_job)


def _set_custom_model_job(**updates):
    with custom_model_job_lock:
        custom_model_job.update(updates)
        return dict(custom_model_job)


def switch_job_snapshot():
    with switch_job_lock:
        return dict(switch_job)


def _set_switch_job(**updates):
    with switch_job_lock:
        switch_job.update(updates)
        return dict(switch_job)


def switch_job_active():
    with switch_job_lock:
        return bool(switch_job.get("active"))


def _run_model_install_job(job_id, model_id, variant_id, install_command):
    prefix = f"[model-install {model_id}]"
    append_audit_text_line(f"{prefix} starting {install_command}")
    _set_model_install_job_entry(
        job_id,
        active=True,
        status="running",
        model_id=model_id,
        variant_id=variant_id,
        command=install_command,
        started_at=int(time.time()),
        finished_at=0,
        return_code=None,
        summary="Running model install job",
        inventory_rebuild_ok=None,
        progress_percent=0,
        progress_loaded_bytes=0,
        progress_total_bytes=0,
    )
    rc = 999
    rebuild_ok = False
    cleanup_targets = []
    download_locks = []
    try:
        inventory = load_runtime_inventory()
        variant = next(
            (
                row for row in (inventory.get("variants") or [])
                if str(row.get("variant_id") or "").strip() == str(variant_id or "").strip()
            ),
            {},
        )
        plan = _monitor_plan_from_variant_install(variant, install_command)
        env_map = _repo_subprocess_env()
        download_locks = _acquire_model_install_download_locks(job_id, prefix, plan)
        cleanup_targets = _snapshot_model_install_cleanup_targets(plan)
        with model_install_process_lock:
            model_install_cleanup_targets[str(job_id or "").strip()] = list(cleanup_targets)
        space_plan = _model_install_space_plan(plan, env_map) if plan else {"ok": True, "steps": []}
        if plan and not space_plan.get("ok"):
            message = _format_model_install_space_error(space_plan)
            append_audit_text_line(f"{prefix} {message}")
            raise RuntimeError(message)
        setup_install = _parse_setup_install_command(install_command)
        shell_command = str(install_command or "").strip()
        used_builtin_downloads = False
        if plan and _parse_simple_hf_download_plan(install_command):
            _run_hf_download_plan(job_id, prefix, plan, env_map)
            used_builtin_downloads = True
            shell_command = ""
        elif plan and setup_install:
            _run_hf_download_plan(job_id, prefix, plan, env_map)
            used_builtin_downloads = True
            shell_command = _setup_install_command_with_skip_model(setup_install)
            append_audit_text_line(
                f"{prefix} continuing setup with SKIP_MODEL=1 after built-in downloads"
            )
        if shell_command:
            process = subprocess.Popen(
                ["bash", "-lc", shell_command],
                cwd=CLUB3090_DIR,
                env=env_map,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                bufsize=0,
            )
            _register_model_install_process(job_id, process)
            monitor = None
            if plan and not used_builtin_downloads:
                monitor = threading.Thread(
                    target=_monitor_hf_download_progress,
                    args=(process, job_id, prefix, plan, env_map),
                    name=f"club3090-hf-progress-{_selector_token(model_id)}",
                    daemon=True,
                )
                monitor.start()
            try:
                _stream_process_output_to_audit(process, prefix)
            finally:
                rc = int(process.wait())
                _clear_model_install_process(job_id, process)
                if monitor is not None:
                    monitor.join(timeout=5)
        else:
            rc = 0
    except Exception as e:
        append_audit_text_line(f"{prefix} launcher error: {e}")
        rc = 999
    finally:
        with model_install_process_lock:
            model_install_cleanup_targets.pop(str(job_id or "").strip(), None)
        _release_model_install_download_locks(download_locks)
    if rc == 0:
        try:
            normalized_files = _normalize_shared_mmproj_hardlinks()
            normalized_files.extend(_normalize_duplicate_model_file_hardlinks())
            for line in normalized_files:
                append_audit_text_line(f"{prefix} {line}")
            rebuild_runtime_inventory()
            rebuild_ok = True
            append_audit_text_line(f"{prefix} inventory rebuild succeeded")
        except Exception as e:
            rebuild_ok = False
            append_audit_text_line(f"{prefix} inventory rebuild failed: {e}")
    else:
        current_job = {}
        with model_install_job_lock:
            current_job = dict(model_install_jobs.get(str(job_id or "").strip()) or {})
        was_stopped = bool(current_job.get("stop_requested"))
        if was_stopped:
            removed_paths = _cleanup_model_install_targets(prefix, cleanup_targets)
            if removed_paths:
                append_audit_text_line(
                    f"{prefix} removed {len(removed_paths)} partial download target{'s' if len(removed_paths) != 1 else ''} after stop"
                )
        elif cleanup_targets:
            append_audit_text_line(f"{prefix} preserved partial download targets for resume after failure")
        append_audit_text_line(f"{prefix} command failed with return code {rc}")
    current_job = {}
    with model_install_job_lock:
        current_job = dict(model_install_jobs.get(str(job_id or "").strip()) or {})
    was_stopped = bool(current_job.get("stop_requested"))
    status = "stopped" if was_stopped and rc != 0 else ("success" if rc == 0 else "failed")
    summary = (
        "Model install stopped by request"
        if was_stopped and rc != 0
        else f"Model install {'completed' if rc == 0 else 'failed'} (rc={rc})"
    )
    _set_model_install_job_entry(
        job_id,
        active=False,
        status=status,
        finished_at=int(time.time()),
        return_code=rc,
        summary=summary,
        inventory_rebuild_ok=rebuild_ok if rc == 0 else False,
        stop_requested=bool(was_stopped),
        progress_percent=100 if rc == 0 else current_job.get("progress_percent"),
    )
    log_audit(
        "model_install_job_finished",
        model_id=model_id,
        variant_id=variant_id,
        return_code=rc,
        inventory_rebuild_ok=rebuild_ok if rc == 0 else False,
    )
    try:
        refresh_status_snapshot()
    except Exception:
        pass
    append_audit_text_line(f"{prefix} {summary}")


def start_model_install_job(model_id, variant_id, install_command):
    inventory = load_runtime_inventory()
    variant_key = str(variant_id or "").strip()
    variant = next(
        (
            row
            for row in inventory.get("variants") or []
            if variant_key
            and (
                str(row.get("variant_id") or "") == variant_key
                or str(row.get("selector") or "") == variant_key
            )
        ),
        None,
    )
    if not variant:
        raise ValueError("Unknown variant")
    if str(variant.get("model_id") or "") != str(model_id or ""):
        raise ValueError("Variant/model mismatch")
    expected_command = str(variant.get("install_command") or "").strip()
    requested_command = str(install_command or "").strip()
    if not requested_command:
        requested_command = expected_command
    if not expected_command:
        raise ValueError("This preset does not have a supported install command")
    normalized_expected_command = re.sub(r"\s+", " ", expected_command).strip()
    normalized_requested_command = re.sub(r"\s+", " ", requested_command).strip()
    if normalized_expected_command != normalized_requested_command:
        raise ValueError("Install command validation failed")
    plan = _monitor_plan_from_variant_install(variant, expected_command)
    download_target_keys = _model_install_download_lock_keys(plan)
    affected_variants = _model_install_affected_variants(inventory, plan)
    with model_install_job_lock:
        requested_targets = set(download_target_keys)
        for job in model_install_jobs.values():
            if not bool(job.get("active")):
                continue
            if (
                str(job.get("model_id") or "") == str(model_id or "")
                and str(job.get("variant_id") or "") == str(variant_id or "")
            ):
                raise RuntimeError("This preset is already downloading")
            active_targets = {
                str(item or "").strip()
                for item in (job.get("download_target_keys") or [])
                if str(item or "").strip()
            }
            if requested_targets.intersection(active_targets):
                owner = str(job.get("selector") or job.get("variant_id") or "another preset")
                raise RuntimeError(f"Shared model assets are already downloading for {owner}")
        job_id = f"model-install-{int(time.time() * 1000)}-{secrets.token_hex(3)}"
        _set_model_install_job_entry(
            job_id,
            active=True,
            status="queued",
            model_id=model_id,
            variant_id=variant_id,
            command=expected_command,
            started_at=int(time.time()),
            finished_at=0,
            return_code=None,
            summary="Queued model install job",
            inventory_rebuild_ok=None,
            progress_percent=0,
            progress_loaded_bytes=0,
            progress_total_bytes=0,
            selector=str(variant.get("selector") or variant.get("upstream_tag") or "").strip(),
            download_target_keys=download_target_keys,
            affected_variant_ids=[
                row.get("variant_id") for row in affected_variants
                if str(row.get("variant_id") or "").strip()
            ],
            affected_selectors=[
                row.get("selector") for row in affected_variants
                if str(row.get("selector") or "").strip()
            ],
        )
    threading.Thread(
        target=_run_model_install_job,
        args=(job_id, str(model_id), str(variant_id), expected_command),
        name=f"club3090-model-install-{_selector_token(model_id)}",
        daemon=True,
    ).start()
    log_audit("model_install_job_started", job_id=job_id, model_id=model_id, variant_id=variant_id)
    return dict(model_install_jobs_snapshot()[0] if model_install_jobs_snapshot() else {})


def _run_custom_model_add_job(job_request):
    request = dict(job_request or {})
    slug = str(request.get("slug") or "").strip()
    profile_like = str(request.get("profile_like") or "").strip()
    label = str(request.get("display_name") or slug or "custom-model").strip()
    prefix = f"[custom-model {label}]"
    append_audit_text_line(f"{prefix} validating import plan for {slug} against {profile_like}")
    _set_custom_model_job(
        active=True,
        status="planning",
        action="add",
        model_id="",
        selector="",
        slug=slug,
        command="",
        started_at=int(time.time()),
        finished_at=0,
        return_code=None,
        summary="Validating custom model import plan",
        inventory_rebuild_ok=None,
    )
    rc = 999
    rebuild_ok = False
    plan = None
    try:
        plan = _build_custom_model_pull_plan(
            slug,
            profile_like,
            display_name=request.get("display_name") or "",
            accept_confirm=bool(request.get("accept_confirm", False)),
            force_download=bool(request.get("force_download", False)),
            trust_remote_code=bool(request.get("trust_remote_code", False)),
            experimental_arch=bool(request.get("experimental_arch", False)),
            hf_home=str(request.get("hf_home") or "").strip(),
            hardware_sm=request.get("hardware_sm"),
            hardware_gpus=str(request.get("hardware_gpus") or "").strip(),
            engine_switches=str(request.get("engine_switches") or "").strip(),
        )
        command = str(plan.get("command") or "").strip()
        selector = str(plan.get("selector") or "").strip()
        model_id = str(plan.get("model_id") or "").strip()
        _set_custom_model_job(
            active=True,
            status="running",
            action="add",
            model_id=model_id,
            selector=selector,
            slug=slug,
            command=command,
            summary="Running upstream pull.sh import",
        )
        append_audit_text_line(f"{prefix} starting {command}")
        process = subprocess.Popen(
            ["bash", "-lc", command],
            cwd=CLUB3090_DIR,
            env=_repo_subprocess_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
            bufsize=0,
        )
        try:
            _stream_process_output_to_audit(process, prefix)
        finally:
            rc = int(process.wait())
        if rc == 0:
            compose_text = str(plan.pop("compose_text") or "")
            record = dict(plan)
            compose_path = str(record.get("compose_path") or "").strip()
            if not compose_text or not compose_path:
                raise RuntimeError("Custom model import finished without a persistent compose payload")
            write_text_atomic_if_changed(compose_path, compose_text)
            rows = read_custom_model_registry()
            rows.append(record)
            write_custom_model_registry(rows)
            rebuild_runtime_inventory()
            rebuild_ok = True
            append_audit_text_line(f"{prefix} registry saved at {compose_path}")
        else:
            append_audit_text_line(f"{prefix} command failed with return code {rc}")
    except Exception as e:
        append_audit_text_line(f"{prefix} import failed: {e}")
        rc = 999 if rc == 999 else rc
    summary = f"Custom model import {'completed' if rc == 0 and rebuild_ok else 'failed'} (rc={rc})"
    _set_custom_model_job(
        active=False,
        status=("success" if rc == 0 and rebuild_ok else "failed"),
        finished_at=int(time.time()),
        return_code=rc,
        summary=summary,
        inventory_rebuild_ok=rebuild_ok if rc == 0 else False,
    )
    log_audit(
        "custom_model_job_finished",
        action="add",
        slug=slug,
        profile_like=profile_like,
        selector=str((plan or {}).get("selector") or ""),
        return_code=rc,
        inventory_rebuild_ok=rebuild_ok if rc == 0 else False,
    )
    try:
        refresh_status_snapshot()
    except Exception:
        pass
    append_audit_text_line(f"{prefix} {summary}")


def start_custom_model_add_job(data):
    payload = dict(data or {})
    slug = str(payload.get("slug") or "").strip()
    profile_like = str(payload.get("profile_like") or "").strip()
    if not slug or not profile_like:
        raise ValueError("Custom model import requires both a Hugging Face slug and a reference profile")
    if model_install_jobs_active():
            raise RuntimeError("Wait for the current model install job to finish before importing a custom model")
    with custom_model_job_lock:
        if custom_model_job.get("active"):
            raise RuntimeError("Another custom model job is already running")
        custom_model_job.update(
            {
                "active": True,
                "status": "queued",
                "action": "add",
                "model_id": "",
                "selector": "",
                "slug": slug,
                "command": "",
                "started_at": int(time.time()),
                "finished_at": 0,
                "return_code": None,
                "summary": "Queued custom model import",
                "inventory_rebuild_ok": None,
            }
        )
    threading.Thread(
        target=_run_custom_model_add_job,
        args=(payload,),
        name=f"club3090-custom-model-add-{_selector_token(slug)}",
        daemon=True,
    ).start()
    log_audit("custom_model_job_started", action="add", slug=slug, profile_like=profile_like)
    return custom_model_job_snapshot()


def _run_custom_model_remove_job(record_id):
    target = None
    try:
        target = next((row for row in read_custom_model_registry() if _selector_token(row.get("id") or "") == _selector_token(record_id) or _selector_token(row.get("model_id") or "") == _selector_token(record_id) or _selector_token(row.get("selector") or "") == _selector_token(record_id)), None)
    except Exception:
        target = None
    label = str((target or {}).get("display_name") or record_id or "custom-model").strip()
    prefix = f"[custom-model {label}]"
    append_audit_text_line(f"{prefix} starting uninstall")
    _set_custom_model_job(
        active=True,
        status="running",
        action="remove",
        model_id=str((target or {}).get("model_id") or ""),
        selector=str((target or {}).get("selector") or ""),
        slug=str((target or {}).get("slug") or ""),
        command="delete_custom_model_record",
        started_at=int(time.time()),
        finished_at=0,
        return_code=None,
        summary="Removing custom model",
        inventory_rebuild_ok=None,
    )
    rc = 0
    rebuild_ok = False
    try:
        removed = delete_custom_model_record(record_id)
        rebuild_ok = True
        append_audit_text_line(f"{prefix} removed {removed.get('compose_path') or removed.get('slug') or removed.get('id')}")
    except Exception as e:
        rc = 999
        append_audit_text_line(f"{prefix} uninstall failed: {e}")
    summary = f"Custom model uninstall {'completed' if rc == 0 and rebuild_ok else 'failed'} (rc={rc})"
    _set_custom_model_job(
        active=False,
        status=("success" if rc == 0 and rebuild_ok else "failed"),
        finished_at=int(time.time()),
        return_code=rc,
        summary=summary,
        inventory_rebuild_ok=rebuild_ok if rc == 0 else False,
    )
    log_audit(
        "custom_model_job_finished",
        action="remove",
        slug=str((target or {}).get("slug") or ""),
        selector=str((target or {}).get("selector") or ""),
        return_code=rc,
        inventory_rebuild_ok=rebuild_ok if rc == 0 else False,
    )
    try:
        refresh_status_snapshot()
    except Exception:
        pass
    append_audit_text_line(f"{prefix} {summary}")


def start_custom_model_remove_job(record_id):
    target_id = str(record_id or "").strip()
    if not target_id:
        raise ValueError("Custom model id is required")
    if model_install_jobs_active():
            raise RuntimeError("Wait for the current model install job to finish before removing a custom model")
    with custom_model_job_lock:
        if custom_model_job.get("active"):
            raise RuntimeError("Another custom model job is already running")
        custom_model_job.update(
            {
                "active": True,
                "status": "queued",
                "action": "remove",
                "model_id": "",
                "selector": "",
                "slug": "",
                "command": "delete_custom_model_record",
                "started_at": int(time.time()),
                "finished_at": 0,
                "return_code": None,
                "summary": "Queued custom model uninstall",
                "inventory_rebuild_ok": None,
            }
        )
    threading.Thread(
        target=_run_custom_model_remove_job,
        args=(target_id,),
        name=f"club3090-custom-model-remove-{_selector_token(target_id)}",
        daemon=True,
    ).start()
    log_audit("custom_model_job_started", action="remove", selector=target_id)
    return custom_model_job_snapshot()


def _task_context_from_runtime_entry(mode="", port=0, container="", instance_id=""):
    selector = canonical_mode_selector(mode)
    spec = resolve_variant_spec(selector) or {}
    resolved_port = int(port or 0)
    return {
        "instance_id": str(instance_id or "").strip().upper(),
        "mode": selector,
        "spec": spec,
        "port": resolved_port,
        "url": (f"http://localhost:{resolved_port}" if resolved_port > 0 else ""),
        "container": str(container or "").strip(),
        "engine": str(spec.get("engine") or "").strip(),
        "served_model_name": str(spec.get("served_model_name") or "").strip(),
    }


def _active_runtime_task_context():
    return _task_context_from_runtime_entry(
        active_mode(),
        active_port(),
        current_container(),
        "GLOBAL",
    )


def _running_runtime_task_contexts():
    contexts = []
    seen = set()
    for instance in visible_instances(read_instances_config()):
        if not instance_running(instance):
            continue
        context = _task_context_from_runtime_entry(
            instance.get("mode"),
            instance_runtime_port(instance),
            instance_runtime_container_name(instance),
            instance.get("id"),
        )
        key = (
            str(context.get("instance_id") or ""),
            str(context.get("mode") or ""),
            str(context.get("container") or ""),
            int(context.get("port") or 0),
        )
        if key in seen:
            continue
        seen.add(key)
        contexts.append(context)
    global_context = _active_runtime_task_context()
    global_scope = str((global_context.get("spec") or {}).get("scope_kind") or "")
    if (
        global_scope in {"multi", "global_only"}
        and int(global_context.get("port") or 0) > 0
        and port_open(int(global_context.get("port") or 0), timeout=0.25)
    ):
        key = (
            "GLOBAL",
            str(global_context.get("mode") or ""),
            str(global_context.get("container") or ""),
            int(global_context.get("port") or 0),
        )
        if key not in seen:
            seen.add(key)
            contexts.append(global_context)
    return contexts


def _resolve_admin_task_context(instance_id=""):
    requested = str(instance_id or "").strip().upper()
    if requested and requested != "GLOBAL":
        instance = get_instance(requested)
        if not instance:
            raise ValueError(f"Unknown instance: {requested}")
        if not instance_running(instance):
            raise RuntimeError(f"{requested} is not running. Start that scope first.")
        return _task_context_from_runtime_entry(
            instance.get("mode"),
            instance_runtime_port(instance),
            instance_runtime_container_name(instance),
            instance.get("id"),
        )
    running = _running_runtime_task_contexts()
    if requested == "GLOBAL":
        if len(running) == 1:
            return running[0]
        raise RuntimeError("Global scope can only launch this task when exactly one runtime is running.")
    active = _active_runtime_task_context()
    if int(active.get("port") or 0) > 0 and port_open(int(active.get("port") or 0), timeout=0.25):
        return active
    if len(running) == 1:
        return running[0]
    raise RuntimeError("This task requires a running backend. Start a preset first.")


def read_self_update_secret():
    try:
        return open(SELF_UPDATE_SECRET_FILE, "r", encoding="utf-8").read().strip()
    except Exception:
        return ""


def request_self_update_service(path, payload=None, timeout=15):
    secret = read_self_update_secret()
    if not secret:
        raise RuntimeError("Self-update service secret is unavailable")
    req = urllib.request.Request(
        f"http://127.0.0.1:{UPDATER_BIND_PORT}{path}",
        data=json.dumps(payload or {}, separators=(",", ":")).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Club3090-Update-Secret": secret,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=max(5, int(timeout or 15))) as response:
            return json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(detail or str(exc))


def start_self_update_job(scope, target_commit=""):
    scope_name = _selector_token(scope)
    if scope_name not in {"controller", "club3090"}:
        raise ValueError("Invalid update scope")
    target_commit = re.sub(r"[^0-9A-Fa-f]+", "", str(target_commit or "").strip())
    fetch_remote_script_metadata(force=True)
    if model_install_jobs_active():
            raise RuntimeError("Wait for the current model install job to finish before starting an update")
    if scope_name == "club3090":
        active_fn = globals().get("benchmark_job_active")
        try:
            if callable(active_fn) and active_fn():
                raise RuntimeError("Stop Model Scores benchmarking before migrating Club-3090.")
        except RuntimeError:
            raise
        except Exception:
            pass
    prefix = f"[self-update {scope_name}]"
    subprocess.run(["systemctl", "start", "club3090-updater.service"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    result = request_self_update_service("/start", {"scope": scope_name, "target_commit": target_commit}, timeout=20)
    if not result or result.get("ok") is False:
        raise RuntimeError(str((result or {}).get("error") or "Self-update service rejected the request"))
    label = str(result.get("label") or ("club-3090 migration" if scope_name == "club3090" else "admin script update"))
    command = str(result.get("command") or "")
    append_audit_text_line(f"{prefix} queued {label} via club3090-updater.service")
    if command:
        append_audit_text_line(f"{prefix} command: {command}")
    log_audit("self_update_job_started", scope=scope_name, command=command, target_commit=target_commit, via="club3090-updater.service")
    return {
        "ok": True,
        "scope": scope_name,
        "label": label,
        "command": command,
        "target_commit": target_commit,
        "stream_url": result.get("stream_url") or "",
        "status_url": result.get("status_url") or "",
        "update_token": str(result.get("token") or ""),
        "focus_log_source": "update",
    }


def default_target_request_metrics():
    return {
        "last_status": None,
        "last_latency_s": None,
        "last_ttft_s": None,
        "last_prompt_tps": None,
        "last_tokens_per_second": None,
        "last_estimated_tokens": None,
        "last_gpu_kv_cache_usage_pct": None,
        "last_cpu_kv_cache_usage_pct": None,
        "last_prefix_cache_hit_rate_pct": None,
        "last_speculative": {},
        "last_input_tokens": None,
        "last_output_tokens": None,
        "last_total_tokens": None,
        "last_tool_calls": None,
        "last_preset": None,
        "last_path": None,
        "last_request_at": 0,
        "benchmark_active": False,
        "benchmark_mode": "",
        "benchmark_step": "",
        "benchmark_step_index": 0,
        "benchmark_step_count": 0,
        "benchmark_step_progress": 0.0,
    }


def snapshot_target_request_metrics():
    with metrics_lock:
        return {key: dict(value) for key, value in target_request_metrics.items()}


def _preset_tps_selector_key(selector):
    text = str(selector or "").strip()
    if not text:
        return ""
    try:
        text = canonical_mode_selector(text)
    except Exception:
        pass
    return str(text or "").strip()


def _sanitize_preset_tps_samples(values, limit=10):
    samples = []
    for value in values if isinstance(values, list) else []:
        try:
            number = float(value)
        except Exception:
            continue
        if not math.isfinite(number) or number <= 0:
            continue
        samples.append(round(number, 3))
    return samples[-int(limit or 10):]


def _sanitize_preset_tps_row(row):
    data = row if isinstance(row, dict) else {}
    recent = _sanitize_preset_tps_samples(data.get("recent") or data.get("samples") or [], 10)
    peaks = _sanitize_preset_tps_samples(data.get("peaks") or data.get("max_samples") or [], 10)
    peaks = sorted(peaks, reverse=True)[:10]
    if not peaks and recent:
        peaks = sorted(recent, reverse=True)[:10]
    return {
        "recent": recent,
        "peaks": peaks,
        "sample_count": max(0, int(float(data.get("sample_count") or data.get("count") or len(recent) or 0))),
        "updated_at": max(0, int(float(data.get("updated_at") or 0))),
    }


def _read_preset_tps_stats_unlocked():
    try:
        with open(PRESET_TPS_STATS_FILE, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception:
        raw = {}
    if isinstance(raw, dict) and isinstance(raw.get("selectors"), dict):
        raw_rows = raw.get("selectors") or {}
    elif isinstance(raw, dict):
        raw_rows = raw
    else:
        raw_rows = {}
    rows = {}
    for selector, row in raw_rows.items():
        key = _preset_tps_selector_key(selector)
        if not key:
            continue
        clean = _sanitize_preset_tps_row(row)
        if clean["recent"] or clean["peaks"]:
            rows[key] = clean
    return rows


def _write_preset_tps_stats_unlocked(rows):
    clean = {}
    for selector, row in (rows or {}).items():
        key = _preset_tps_selector_key(selector)
        if not key:
            continue
        clean_row = _sanitize_preset_tps_row(row)
        if clean_row["recent"] or clean_row["peaks"]:
            clean[key] = clean_row
    write_json_atomic_if_changed(
        PRESET_TPS_STATS_FILE,
        {"selectors": clean},
        indent=2,
        sort_keys=True,
    )
    return clean


def preset_tps_stats_snapshot():
    with preset_tps_stats_lock:
        rows = _read_preset_tps_stats_unlocked()
    snapshot = {}
    for selector, row in rows.items():
        recent = _sanitize_preset_tps_samples(row.get("recent") or [], 10)
        peaks = sorted(_sanitize_preset_tps_samples(row.get("peaks") or [], 10), reverse=True)[:10]
        avg_tps = round(sum(recent) / len(recent), 2) if recent else None
        max_tps = round(max(peaks), 2) if peaks else None
        snapshot[selector] = {
            "avg_tps": avg_tps,
            "max_tps": max_tps,
            "recent_sample_count": len(recent),
            "max_sample_count": len(peaks),
            "sample_count": int(row.get("sample_count") or len(recent) or 0),
            "updated_at": int(row.get("updated_at") or 0),
        }
    return snapshot


def record_preset_tps_sample(selector, tps):
    key = _preset_tps_selector_key(selector)
    try:
        value = float(tps)
    except Exception:
        return preset_tps_stats_snapshot()
    if not key or not math.isfinite(value) or value <= 0:
        return preset_tps_stats_snapshot()
    value = round(value, 3)
    with preset_tps_stats_lock:
        rows = _read_preset_tps_stats_unlocked()
        row = _sanitize_preset_tps_row(rows.get(key) or {})
        recent = list(row.get("recent") or [])
        recent.append(value)
        row["recent"] = recent[-10:]
        peaks = sorted((list(row.get("peaks") or []) + [value]), reverse=True)[:10]
        row["peaks"] = peaks
        row["sample_count"] = int(row.get("sample_count") or 0) + 1
        row["updated_at"] = int(time.time())
        rows[key] = row
        _write_preset_tps_stats_unlocked(rows)
    return preset_tps_stats_snapshot()


def clear_preset_tps_stats(selector):
    key = _preset_tps_selector_key(selector)
    with preset_tps_stats_lock:
        rows = _read_preset_tps_stats_unlocked()
        if key:
            rows.pop(key, None)
        else:
            rows.clear()
        _write_preset_tps_stats_unlocked(rows)
    return preset_tps_stats_snapshot()


SYSTEM_METRIC_PEAK_CHART_KEYS = (
    "gpu_util",
    "mem_pct",
    "mem_used_gib",
    "latency_s",
    "tps",
    "ram_pct",
    "ram_used_gib",
    "cpu_pct",
    "system_util_pct",
    "net_rx_mbps",
    "net_tx_mbps",
)

SYSTEM_METRIC_PEAK_GPU_KEYS = (
    "util",
    "mem_pct",
    "temp",
    "temp_junction",
    "temp_vram",
    "power",
)

SYSTEM_METRIC_PEAK_CHART_LIMITS = {
    "gpu_util": 100.0,
    "mem_pct": 100.0,
    "mem_used_gib": 1048576.0,
    "latency_s": 120.0,
    "tps": 10000.0,
    "ram_pct": 100.0,
    "ram_used_gib": 1048576.0,
    "cpu_pct": 100.0,
    "system_util_pct": 100.0,
    "net_rx_mbps": 100000.0,
    "net_tx_mbps": 100000.0,
}

SYSTEM_METRIC_PEAK_GPU_LIMITS = {
    "util": 100.0,
    "mem_pct": 100.0,
    "temp": 150.0,
    "temp_junction": 200.0,
    "temp_vram": 200.0,
    "power": 2000.0,
}

def _sanitize_metric_peak_number(value, digits=2, upper_bound=None):
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number) or number < 0:
        return None
    if upper_bound is not None and number > float(upper_bound):
        return None
    return round(number, int(digits or 2))


def _sanitize_system_metric_peak_gpu_row(row):
    data = row if isinstance(row, dict) else {}
    clean = {}
    for key in SYSTEM_METRIC_PEAK_GPU_KEYS:
        value = _sanitize_metric_peak_number(
            data.get(key),
            upper_bound=SYSTEM_METRIC_PEAK_GPU_LIMITS.get(key),
        )
        if value is not None:
            clean[key] = value
    return clean


def sanitize_system_metric_peaks(payload):
    data = payload if isinstance(payload, dict) else {}
    clean = {"charts": {}, "gpus": {}}
    charts = data.get("charts") if isinstance(data.get("charts"), dict) else {}
    for key in SYSTEM_METRIC_PEAK_CHART_KEYS:
        value = _sanitize_metric_peak_number(
            charts.get(key),
            upper_bound=SYSTEM_METRIC_PEAK_CHART_LIMITS.get(key),
        )
        if value is not None:
            clean["charts"][key] = value
    gpus = data.get("gpus") if isinstance(data.get("gpus"), dict) else {}
    for gpu_key, row in gpus.items():
        safe_gpu_key = re.sub(r"[^0-9]+", "", str(gpu_key or "").strip())
        if not safe_gpu_key:
            continue
        clean_row = _sanitize_system_metric_peak_gpu_row(row)
        if clean_row:
            clean["gpus"][safe_gpu_key] = clean_row
    return clean


def _read_system_metric_peaks_unlocked():
    global system_metric_peaks_cache
    if isinstance(system_metric_peaks_cache, dict):
        return sanitize_system_metric_peaks(system_metric_peaks_cache)
    raw = read_json_file(SYSTEM_METRIC_PEAKS_FILE, {})
    clean = sanitize_system_metric_peaks(raw)
    system_metric_peaks_cache = clean
    return clean


def _write_system_metric_peaks_unlocked(peaks):
    global system_metric_peaks_cache
    clean = sanitize_system_metric_peaks(peaks)
    write_json_atomic_if_changed(
        SYSTEM_METRIC_PEAKS_FILE,
        clean,
        indent=2,
        sort_keys=True,
    )
    system_metric_peaks_cache = clean
    return clean


def system_metric_peaks_snapshot():
    with system_metric_peaks_lock:
        return _read_system_metric_peaks_unlocked()

def read_ui_config():
    default = {
        "show_global_logs": True,
        "active_tab": "overview",
        "selected_scope": "GPU0",
        "current_log_source": "docker",
    }
    try:
        with open(UI_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default
        merged = dict(default)
        if "show_global_logs" in data:
            merged["show_global_logs"] = bool(data.get("show_global_logs"))
        if str(data.get("active_tab") or "") in {"overview", "system", "presets", "users", "metrics", "logs", "audit", "chat"}:
            merged["active_tab"] = str(data.get("active_tab"))
        current_log_source = str(data.get("current_log_source") or "").strip()
        if current_log_source in {"docker", "audit", "debug"} or re.fullmatch(r"service:[a-z0-9_-]+", current_log_source):
            merged["current_log_source"] = current_log_source
        if data.get("selected_scope") not in (None, ""):
            merged["selected_scope"] = str(data.get("selected_scope"))
        return merged
    except Exception:
        return default

def write_ui_config(data):
    current = read_ui_config()
    original = dict(current)
    if "show_global_logs" in data:
        current["show_global_logs"] = bool(data["show_global_logs"])
    if str(data.get("active_tab") or "") in {"overview", "system", "presets", "users", "metrics", "logs", "audit", "chat"}:
        current["active_tab"] = str(data.get("active_tab"))
    current_log_source = str(data.get("current_log_source") or "").strip()
    if current_log_source in {"docker", "audit", "debug"} or re.fullmatch(r"service:[a-z0-9_-]+", current_log_source):
        current["current_log_source"] = current_log_source
    if data.get("selected_scope") not in (None, ""):
        current["selected_scope"] = str(data.get("selected_scope"))
    if current == original:
        return current, False
    write_json_atomic_if_changed(UI_CONFIG_FILE, current, separators=(",", ":"))
    return current, True


def _parse_script_multiline_constant(script_text, name):
    match = re.search(
        rf"{re.escape(name)}=\$\(cat <<'EOF_[A-Z0-9_]+'\n(.*?)\nEOF_[A-Z0-9_]+\n\)",
        str(script_text or ""),
        flags=re.S,
    )
    return (match.group(1).strip() if match else "")


def _parse_script_singleline_constant(script_text, name):
    match = re.search(rf'^{re.escape(name)}="([^"]*)"$', str(script_text or ""), flags=re.M)
    if match:
        return match.group(1).strip()
    match = re.search(rf"^{re.escape(name)}='([^']*)'$", str(script_text or ""), flags=re.M)
    return (match.group(1).strip() if match else "")


def _sanitize_metadata_text(value):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


def parse_installer_script_metadata(script_text):
    text = str(script_text or "")
    version = _parse_script_singleline_constant(text, "SCRIPT_VERSION")
    return {
        "script_version": version,
        "change_log_latest": "",
        "change_log_release": "",
        "change_log_icons": {},
        "club_3090_version": {},
    }


def parse_remote_build_metadata(metadata_text):
    payload = json.loads(str(metadata_text or ""))
    if not isinstance(payload, dict):
        raise ValueError("remote metadata.json is not an object")
    version = str(payload.get("version") or "").strip()
    release_date = str(payload.get("release_date") or "").strip()
    if not version or not release_date:
        raise ValueError("remote metadata.json is missing version or release_date")
    script_version = f"{release_date}.v{version}"
    change_log_icons = payload.get("change_log_icons") or {}
    club_version = payload.get("club3090_version") or {}
    return {
        "script_version": script_version,
        "change_log_latest": _sanitize_metadata_text(
            payload.get("change_log_latest") or ""
        ),
        "change_log_release": _sanitize_metadata_text(
            payload.get("change_log_release") or ""
        ),
        "change_log_icons": change_log_icons if isinstance(change_log_icons, dict) else {},
        "club_3090_version": club_version if isinstance(club_version, dict) else {},
    }


def read_local_installer_metadata():
    for path in (LOCAL_INSTALLER_SCRIPT_FILE, os.path.join(os.path.dirname(__file__), "base.sh")):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    return parse_installer_script_metadata(handle.read())
        except Exception:
            pass
    return {
        "script_version": SCRIPT_VERSION,
        "change_log_latest": "",
        "change_log_release": "",
        "change_log_icons": {},
        "club_3090_version": {},
    }


def read_self_update_state():
    payload = read_json_file(UPDATE_STATE_FILE, {})
    if not isinstance(payload, dict):
        payload = {}
    active = bool(payload.get("active"))
    token = str(payload.get("token") or "").strip()
    result = {
        "active": active,
        "status": str(payload.get("status") or ("running" if active else "idle")).strip() or ("running" if active else "idle"),
        "scope": str(payload.get("scope") or "").strip(),
        "label": str(payload.get("label") or "").strip(),
        "started_at": int(payload.get("started_at") or 0),
        "finished_at": int(payload.get("finished_at") or 0),
        "return_code": payload.get("return_code"),
        "summary": str(payload.get("summary") or "").strip(),
        "token": token,
        "script_version": str(payload.get("script_version") or "").strip(),
        "target_commit": str(payload.get("target_commit") or "").strip(),
        "ui_ack_token": str(payload.get("ui_ack_token") or "").strip(),
        "ui_ack_at": int(payload.get("ui_ack_at") or 0),
        "stream_url": "",
        "status_url": "",
    }
    if token:
        result["stream_url"] = f"/admin/update-stream?token={token}&tail=4000"
        result["status_url"] = f"/admin/update-status?token={token}"
    return result


def parse_script_version_tuple(value):
    match = re.search(r"v(\d+)\.(\d+)\.(\d+)([a-z]*)\s*$", str(value or "").strip())
    if not match:
        return None
    suffix = str(match.group(4) or "")
    suffix_rank = 0
    for char in suffix:
        suffix_rank = suffix_rank * 26 + (ord(char) - ord("a") + 1)
    return tuple(int(match.group(index)) for index in range(1, 4)) + (suffix_rank,)


def compare_script_versions(left, right):
    left_tuple = parse_script_version_tuple(left)
    right_tuple = parse_script_version_tuple(right)
    if not left_tuple or not right_tuple:
        return 0
    return (left_tuple > right_tuple) - (left_tuple < right_tuple)


def resolve_remote_update_commit(timeout=12):
    result = subprocess.run(
        ["git", "ls-remote", REMOTE_UPDATE_REPO_URL, REMOTE_UPDATE_REF],
        capture_output=True,
        text=True,
        check=False,
        timeout=max(5, int(timeout or 12)),
    )
    output = str(result.stdout or "").strip()
    if result.returncode != 0 or not output:
        detail = str(result.stderr or result.stdout or f"git ls-remote exited with {result.returncode}").strip()
        raise RuntimeError(f"git ls-remote failed: {detail}")
    sha = output.split()[0].strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise RuntimeError(f"git ls-remote returned an invalid commit SHA: {sha!r}")
    return sha.lower()


def remote_update_script_url_for_sha(sha):
    commit_sha = str(sha or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise ValueError("A full 40-character commit SHA is required.")
    return str(REMOTE_UPDATE_RAW_URL_TEMPLATE or "").format(sha=commit_sha)

def remote_update_metadata_url_for_sha(sha):
    commit_sha = str(sha or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise ValueError("A full 40-character commit SHA is required.")
    return str(REMOTE_UPDATE_METADATA_URL_TEMPLATE or "").format(sha=commit_sha)


def remote_update_metadata_url_for_ref():
    ref = str(REMOTE_UPDATE_REF or "").strip()
    if not ref:
        return ""
    repo_match = re.fullmatch(
        r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?",
        str(REMOTE_UPDATE_REPO_URL or "").strip(),
    )
    if not repo_match:
        return ""
    owner = repo_match.group(1)
    repo = repo_match.group(2)
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/metadata.json"

def fetch_remote_text(remote_url, timeout=12):
    curl_cmd = [
        "curl",
        "-fsSL",
        "-H",
        "Cache-Control: no-cache",
        "-H",
        "Pragma: no-cache",
        remote_url,
    ]
    try:
        result = subprocess.run(
            curl_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=max(5, int(timeout or 12)),
        )
        if result.returncode == 0 and str(result.stdout or "").strip():
            return str(result.stdout or ""), "curl"
        curl_error = str(result.stderr or result.stdout or f"curl exited with {result.returncode}").strip()
    except FileNotFoundError:
        curl_error = "curl is not installed"
    except Exception as exc:
        curl_error = str(exc)
    request = urllib.request.Request(
        remote_url,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": script_user_agent(),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=max(5, float(timeout or 12))) as response:
            return response.read().decode("utf-8", errors="replace"), "urllib"
    except Exception as exc:
        raise RuntimeError(f"{curl_error}; urllib fallback failed: {exc}")


def fetch_remote_update_metadata_text(commit_sha="", timeout=12):
    candidates = []
    ref_url = remote_update_metadata_url_for_ref()
    sha_url = ""
    if str(commit_sha or "").strip():
        sha_url = remote_update_metadata_url_for_sha(commit_sha)
    for remote_url in (sha_url, ref_url):
        if remote_url and remote_url not in candidates:
            candidates.append(remote_url)
    if not candidates:
        raise RuntimeError("remote metadata URL is empty")
    failures = []
    for remote_url in candidates:
        try:
            payload, fetch_method = fetch_remote_text(remote_url, timeout=timeout)
            return payload, fetch_method, remote_url
        except Exception as exc:
            failures.append(f"{remote_url}: {exc}")
    raise RuntimeError("; ".join(failures) if failures else "remote metadata fetch failed")


def fetch_remote_script_metadata(force=False):
    now = time.time()
    result = {
        "source_url": "",
        "source_repo_url": REMOTE_UPDATE_REPO_URL,
        "source_ref": REMOTE_UPDATE_REF,
        "source_branch": REMOTE_UPDATE_BRANCH,
        "commit_sha": "",
        "metadata_url": "",
        "fetched_at": int(now),
        "script_version": "",
        "change_log_latest": "",
        "change_log_release": "",
        "change_log_icons": {},
        "club_3090_version": {},
        "update_available": False,
        "error": "",
        "fetch_method": "",
    }
    try:
        commit_sha = ""
        remote_url = ""
        try:
            commit_sha = resolve_remote_update_commit(timeout=12)
        except Exception:
            commit_sha = ""
        if commit_sha:
            remote_url = remote_update_script_url_for_sha(commit_sha)
        metadata_payload, metadata_fetch_method, metadata_url = fetch_remote_update_metadata_text(commit_sha, timeout=12)
        result["fetch_method"] = metadata_fetch_method
        result["commit_sha"] = commit_sha
        result["source_url"] = remote_url
        result["metadata_url"] = metadata_url
        metadata_parsed = parse_remote_build_metadata(str(metadata_payload or ""))
        result.update(metadata_parsed)
        result["update_available"] = compare_script_versions(result.get("script_version"), SCRIPT_VERSION) > 0
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _default_remote_script_metadata():
    now = time.time()
    return {
        "source_url": "",
        "source_repo_url": REMOTE_UPDATE_REPO_URL,
        "source_ref": REMOTE_UPDATE_REF,
        "source_branch": REMOTE_UPDATE_BRANCH,
        "commit_sha": "",
        "metadata_url": "",
        "fetched_at": int(now),
        "script_version": "",
        "change_log_latest": "",
        "change_log_release": "",
        "change_log_icons": {},
        "club_3090_version": {},
        "update_available": False,
        "error": "",
        "fetch_method": "",
    }


def _refresh_remote_script_metadata_cache():
    global REMOTE_UPDATE_METADATA_CACHE, REMOTE_UPDATE_METADATA_CACHE_AT, REMOTE_UPDATE_METADATA_REFRESHING
    try:
        result = fetch_remote_script_metadata(force=True)
        with REMOTE_UPDATE_METADATA_LOCK:
            REMOTE_UPDATE_METADATA_CACHE = dict(result)
            REMOTE_UPDATE_METADATA_CACHE_AT = time.time()
    finally:
        with REMOTE_UPDATE_METADATA_LOCK:
            REMOTE_UPDATE_METADATA_REFRESHING = False


def cached_remote_script_metadata(refresh=False):
    global REMOTE_UPDATE_METADATA_REFRESHING
    now = time.time()
    with REMOTE_UPDATE_METADATA_LOCK:
        cached = dict(REMOTE_UPDATE_METADATA_CACHE) if REMOTE_UPDATE_METADATA_CACHE else {}
        cached_at = float(REMOTE_UPDATE_METADATA_CACHE_AT or 0.0)
        refreshing = bool(REMOTE_UPDATE_METADATA_REFRESHING)
        stale = not cached or now - cached_at > REMOTE_UPDATE_METADATA_CACHE_TTL_SECONDS
        if (refresh or stale) and not refreshing:
            REMOTE_UPDATE_METADATA_REFRESHING = True
            threading.Thread(
                target=_refresh_remote_script_metadata_cache,
                name="remote-update-metadata-refresh",
                daemon=True,
            ).start()
            refreshing = True
    if cached:
        cached["refreshing"] = refreshing
        cached["cache_age_seconds"] = max(0, int(now - cached_at)) if cached_at else 0
        return cached
    result = _default_remote_script_metadata()
    result["refreshing"] = refreshing
    result["cache_age_seconds"] = 0
    return result


def git_is_ancestor(repo_root, ancestor_commit, descendant_commit):
    try:
        result = subprocess.run(
            ["git", "-C", repo_root, "merge-base", "--is-ancestor", ancestor_commit, descendant_commit],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def read_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def write_json_file(path, data):
    write_json_atomic_if_changed(path, data, indent=2, sort_keys=True)


def write_text_atomic_if_changed(path, text):
    path = str(path or "")
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    next_text = str(text or "")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            if handle.read() == next_text:
                return False
    except Exception:
        pass
    fd, temp_path = tempfile.mkstemp(prefix=".tmp-", dir=(parent or None))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(next_text)
        os.replace(temp_path, path)
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
    return True
