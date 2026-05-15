#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import mimetypes
import base64
import codecs
import collections
import glob
import hashlib
import json
import math
import os
import platform
import re
import secrets
import select
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

CLUB3090_DIR = os.environ.get("CLUB3090_DIR", "/opt/ai/club-3090")
CONTROL_DIR = "/opt/club3090-control"
SCRIPT_VERSION = os.environ.get("CLUB3090_SCRIPT_VERSION", "unknown")
_SCRIPT_VERSION_MATCH = re.search(r"v(\d+)\.(\d+)\.(\d+)\s*$", str(SCRIPT_VERSION or ""))
DEBUG_LOGS = not (_SCRIPT_VERSION_MATCH and int(_SCRIPT_VERSION_MATCH.group(3)) == 0)
ACTIVE_MODE_FILE = os.path.join(CONTROL_DIR, "active_mode")
LAST_GOOD_MODE_FILE = os.path.join(CONTROL_DIR, "last_good_mode")
CONTROL_LOG_FILE = os.path.join(CONTROL_DIR, "control.log")
AUDIT_LOG_FILE = os.path.join(CONTROL_DIR, "audit.log")
UI_CONFIG_FILE = os.path.join(CONTROL_DIR, "ui_config.json")
CUSTOM_PRESETS_FILE = os.path.join(CONTROL_DIR, "custom_presets.json")
INSTANCES_CONFIG_FILE = os.path.join(CONTROL_DIR, "instances.json")
SERVER_CONFIG_FILE = os.path.join(CONTROL_DIR, "server_config.json")
USERS_FILE = os.path.join(CONTROL_DIR, "users.json")
GROUPS_FILE = os.path.join(CONTROL_DIR, "groups.json")
CHAT_CONVERSATIONS_DIR = os.path.join(CONTROL_DIR, "conversations")
CHAT_STATE_FILE = os.path.join(CHAT_CONVERSATIONS_DIR, "state.json")
CHAT_ATTACHMENTS_DIR = os.path.join(CHAT_CONVERSATIONS_DIR, "attachments")
MCP_PROTOCOL_VERSION = "2025-03-26"
LOCAL_API_TOKEN_FILE = os.path.join(CONTROL_DIR, "local_api_token")
INSTANCES_DIR = os.path.join(CONTROL_DIR, "instances")
RUNTIME_INVENTORY_FILE = os.path.join(CONTROL_DIR, "runtime_inventory.json")
SWITCH_FAILURE_FILE = os.path.join(CONTROL_DIR, "switch_failure.json")
DEFAULT_MODE = os.environ.get("DEFAULT_MODE", "vllm/default")
ADMIN_PORT = int(os.environ.get("CLUB3090_ADMIN_PORT", "8008"))
PROXY_PORT = int(os.environ.get("CLUB3090_PROXY_PORT", "8009"))
LOCAL_API_PORT = int(os.environ.get("CLUB3090_LOCAL_API_PORT", "10881"))
ADMIN_BIND_HOST = os.environ.get("CLUB3090_ADMIN_BIND_HOST", "0.0.0.0")
PROXY_BIND_HOST = os.environ.get("CLUB3090_PROXY_BIND_HOST", "0.0.0.0")
ADMIN_BIND_PORT = int(os.environ.get("CLUB3090_ADMIN_BIND_PORT", str(ADMIN_PORT)))
PROXY_BIND_PORT = int(os.environ.get("CLUB3090_PROXY_BIND_PORT", str(PROXY_PORT)))
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

PRESETS = {
    "chat": {
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 1.5, "repetition_penalty": 1.0,
    },
    "general": {
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0,
        "presence_penalty": 1.5, "repetition_penalty": 1.0,
    },
    "coding": {
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 0, "repetition_penalty": 1.0,
    },
    "coding_fast": {
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0.8, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 0, "repetition_penalty": 1.0,
    },
    "thinking": {
        "chat_template_kwargs": {"enable_thinking": True},
        "temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 1.5,
    },
    "preserve-thinking": {
        "chat_template_kwargs": {"enable_thinking": True, "preserve_thinking": True},
        "temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 1.5,
    },
}

DEFAULT_PRESET_DESCRIPTIONS = {
    "chat": "No thinking, temperature 1.0, top_p 0.95, top_k 20, min_p 0, presence penalty 1.5.",
    "general": "No thinking, lower temperature 0.7, top_p 0.8, top_k 20, presence penalty 1.5.",
    "coding": "Coding-tuned sampling: no thinking, temperature 0.6, top_p 0.95, no presence penalty.",
    "coding_fast": "Faster/looser coding preset: no thinking, temperature 0.8, top_p 0.95, no presence penalty.",
    "thinking": "Enables Qwen thinking with temperature 1.0, top_p 0.95, presence penalty 1.5.",
    "preserve-thinking": "Enables thinking and preserves thinking output with same as above parameters.",
}
LENGTH_PREFIXES = {"short-": 4096, "concise-": 512}
HOP_HEADERS = {"connection","keep-alive","proxy-authenticate","proxy-authorization","te","trailers","transfer-encoding","upgrade","content-length","host"}

switch_lock = threading.Lock()
metrics_lock = threading.Lock()
runtime_ready_probe_cache = {}
auth_cache = {}
AUTH_CACHE_SECONDS = 120
ADMIN_SESSION_COOKIE_NAME = "club3090_admin_session"
ADMIN_SESSION_TTL_SECONDS = int(os.environ.get("CLUB3090_ADMIN_SESSION_TTL_SECONDS", "86400"))
ADMIN_AUTH_DENIAL_LOG_WINDOW_SECONDS = int(os.environ.get("CLUB3090_ADMIN_AUTH_DENIAL_LOG_WINDOW_SECONDS", "30"))
startup_time = time.time()
recent_requests = collections.deque(maxlen=120)
series_points = collections.deque(maxlen=240)
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
latest_gpu_rows = []
latest_system_snapshot = {"memory": {}, "cpu": {"cores": []}, "disks": [], "network": {}, "info": {}}
latest_metrics_collected_at = 0.0
gpu_session_peaks = {}
disk_stats_cache = {"value": [], "time": 0.0}
system_info_cache = {"value": {}, "time": 0.0}
status_snapshot_cache = {}
status_snapshot_updated_at = 0.0
status_snapshot_lock = threading.Lock()
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
target_request_metrics = {}
runtime_inventory_lock = threading.Lock()
runtime_inventory_cache = {}
runtime_inventory_built_at = 0.0
model_install_job_lock = threading.Lock()
admin_session_lock = threading.Lock()
admin_sessions = {}
admin_auth_denial_lock = threading.Lock()
admin_auth_denial_state = {}
audit_rate_limit_lock = threading.Lock()
audit_rate_limit_state = {}
AUDIT_RATE_LIMIT_WINDOWS = {
    "admin_auth_denied": 5,
    "local_api_denied": 5,
    "proxy_auth_denied": 5,
}
model_install_job = {
    "active": False,
    "status": "idle",
    "model_id": "",
    "variant_id": "",
    "command": "",
    "started_at": 0,
    "finished_at": 0,
    "return_code": None,
    "summary": "",
    "inventory_rebuild_ok": None,
}
admin_task_job_lock = threading.Lock()
admin_task_job = {
    "active": False,
    "status": "idle",
    "task": "",
    "label": "",
    "command": "",
    "started_at": 0,
    "finished_at": 0,
    "return_code": None,
    "summary": "",
    "mode": "",
    "container": "",
    "url": "",
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

POWER_IDLE_AFTER_SECONDS = int(os.environ.get("CLUB3090_POWER_IDLE_AFTER_SECONDS", "600"))
CONTAINER_STOP_AFTER_SECONDS = int(os.environ.get("CLUB3090_CONTAINER_STOP_AFTER_SECONDS", "3600"))
CONTAINER_AUTO_STOP_ENABLED = False
GPU_ACTIVE_POWER_LIMIT_W = int(os.environ.get("CLUB3090_GPU_ACTIVE_POWER_LIMIT_W", "280"))
GPU_IDLE_POWER_LIMIT_W = int(os.environ.get("CLUB3090_GPU_IDLE_POWER_LIMIT_W", "120"))
GPU_IDLE_LOCK_CLOCKS = os.environ.get("CLUB3090_GPU_IDLE_LOCK_CLOCKS", "210,900")
GPU_ACTIVE_LOCK_CLOCKS = os.environ.get("CLUB3090_GPU_ACTIVE_LOCK_CLOCKS", "")
CPU_ACTIVE_GOVERNOR = os.environ.get("CLUB3090_CPU_ACTIVE_GOVERNOR", "performance")
CPU_IDLE_GOVERNOR = os.environ.get("CLUB3090_CPU_IDLE_GOVERNOR", "powersave")
FAN_CURVE = [(30, 35), (35, 40), (40, 45), (45, 55), (50, 65), (55, 75), (60, 85), (65, 95)]
FAN_MAX_SPEED = int(os.environ.get("CLUB3090_FAN_MAX_SPEED", "100"))
FAN_MIN_SAFE_SPEED = int(os.environ.get("CLUB3090_FAN_MIN_SAFE_SPEED", "35"))
WOL_MAC = os.environ.get("CLUB3090_WOL_MAC", "")
WOL_BROADCAST = os.environ.get("CLUB3090_WOL_BROADCAST", "255.255.255.255")
PERFORMANCE_PROFILES = {
    "eco": {"gpu_active": 240, "gpu_idle": 90, "idle_clocks": "210,705", "cpu_active": "schedutil", "cpu_idle": "powersave", "idle_after": 300, "stop_after": 1800},
    "balanced": {"gpu_active": GPU_ACTIVE_POWER_LIMIT_W, "gpu_idle": GPU_IDLE_POWER_LIMIT_W, "idle_clocks": GPU_IDLE_LOCK_CLOCKS, "cpu_active": CPU_ACTIVE_GOVERNOR, "cpu_idle": CPU_IDLE_GOVERNOR, "idle_after": POWER_IDLE_AFTER_SECONDS, "stop_after": CONTAINER_STOP_AFTER_SECONDS},
    "default": {"gpu_active": 280, "gpu_idle": 120, "idle_clocks": "", "cpu_active": "schedutil", "cpu_idle": "powersave", "idle_after": 900, "stop_after": 3600},
    "turbo": {"gpu_active": 350, "gpu_idle": 160, "idle_clocks": "", "cpu_active": "performance", "cpu_idle": "schedutil", "idle_after": 1800, "stop_after": 7200},
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
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
    except Exception:
        pass


def debug_audit(event_type, **fields):
    if not DEBUG_LOGS:
        return
    safe_fields = {"debug": True, "script_version": SCRIPT_VERSION}
    for key, value in fields.items():
        if value not in (None, ""):
            safe_fields[key] = value
    log_audit(f"debug_{str(event_type or '').strip() or 'event'}", **safe_fields)


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
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(rendered)
    os.replace(tmp, path)
    return True


def model_install_job_snapshot():
    with model_install_job_lock:
        return dict(model_install_job)


def _set_model_install_job(**updates):
    with model_install_job_lock:
        model_install_job.update(updates)
        return dict(model_install_job)


def admin_task_job_snapshot():
    with admin_task_job_lock:
        return dict(admin_task_job)


def _set_admin_task_job(**updates):
    with admin_task_job_lock:
        admin_task_job.update(updates)
        return dict(admin_task_job)


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


def _run_model_install_job(model_id, variant_id, install_command):
    prefix = f"[model-install {model_id}]"
    append_audit_text_line(f"{prefix} starting {install_command}")
    _set_model_install_job(
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
    )
    rc = 999
    rebuild_ok = False
    try:
        process = subprocess.Popen(
            ["bash", "-lc", install_command],
            cwd=CLUB3090_DIR,
            env=_repo_subprocess_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        try:
            if process.stdout is not None:
                for raw_line in process.stdout:
                    append_audit_text_line(f"{prefix} {str(raw_line or '').rstrip()}")
        finally:
            rc = int(process.wait())
    except Exception as e:
        append_audit_text_line(f"{prefix} launcher error: {e}")
        rc = 999
    if rc == 0:
        try:
            rebuild_runtime_inventory()
            rebuild_ok = True
            append_audit_text_line(f"{prefix} inventory rebuild succeeded")
        except Exception as e:
            rebuild_ok = False
            append_audit_text_line(f"{prefix} inventory rebuild failed: {e}")
    else:
        append_audit_text_line(f"{prefix} command failed with return code {rc}")
    summary = f"Model install {'completed' if rc == 0 else 'failed'} (rc={rc})"
    _set_model_install_job(
        active=False,
        status=("success" if rc == 0 else "failed"),
        finished_at=int(time.time()),
        return_code=rc,
        summary=summary,
        inventory_rebuild_ok=rebuild_ok if rc == 0 else False,
    )
    log_audit(
        "model_install_job_finished",
        model_id=model_id,
        variant_id=variant_id,
        return_code=rc,
        inventory_rebuild_ok=rebuild_ok if rc == 0 else False,
    )
    append_audit_text_line(f"{prefix} {summary}")


def start_model_install_job(model_id, variant_id, install_command):
    inventory = load_runtime_inventory()
    variant = next((row for row in inventory.get("variants") or [] if str(row.get("variant_id") or "") == str(variant_id or "")), None)
    if not variant:
        raise ValueError("Unknown variant")
    if str(variant.get("model_id") or "") != str(model_id or ""):
        raise ValueError("Variant/model mismatch")
    expected_command = str(variant.get("install_command") or "").strip()
    requested_command = str(install_command or "").strip()
    if not expected_command:
        raise ValueError("This preset does not have a supported install command")
    if expected_command != requested_command:
        raise ValueError("Install command validation failed")
    with admin_task_job_lock:
        if admin_task_job.get("active"):
            raise RuntimeError("Wait for the current admin task to finish before starting a model install")
    with model_install_job_lock:
        if model_install_job.get("active"):
            raise RuntimeError("A model install job is already running")
        model_install_job.update(
            {
                "active": True,
                "status": "queued",
                "model_id": model_id,
                "variant_id": variant_id,
                "command": expected_command,
                "started_at": int(time.time()),
                "finished_at": 0,
                "return_code": None,
                "summary": "Queued model install job",
                "inventory_rebuild_ok": None,
            }
        )
    threading.Thread(
        target=_run_model_install_job,
        args=(str(model_id), str(variant_id), expected_command),
        name=f"club3090-model-install-{_selector_token(model_id)}",
        daemon=True,
    ).start()
    log_audit("model_install_job_started", model_id=model_id, variant_id=variant_id)
    return model_install_job_snapshot()


def _active_runtime_task_context():
    mode = active_mode()
    spec = resolve_variant_spec(mode) or {}
    port = int(active_port() or 0)
    return {
        "mode": mode,
        "spec": spec,
        "port": port,
        "url": (f"http://localhost:{port}" if port > 0 else ""),
        "container": current_container(),
        "engine": str(spec.get("engine") or "").strip(),
        "served_model_name": str(spec.get("served_model_name") or "").strip(),
    }


def _build_admin_task_command(task_name):
    task = _selector_token(task_name)
    if task not in {"benchmark", "report"}:
        raise ValueError("Unsupported admin task")
    runtime = _active_runtime_task_context()
    if task == "benchmark":
        if runtime["port"] <= 0 or not port_open(runtime["port"], timeout=0.25):
            raise RuntimeError("Benchmark requires a running backend. Start a preset first.")
        parts = [f"URL={shlex.quote(runtime['url'])}", "PREFLIGHT_NO_AUTODETECT=1"]
        if runtime["container"]:
            parts.append(f"CONTAINER={shlex.quote(runtime['container'])}")
        if runtime["served_model_name"]:
            parts.append(f"MODEL={shlex.quote(runtime['served_model_name'])}")
        parts.append("bash scripts/bench.sh")
        return {
            "task": "benchmark",
            "label": "Benchmark",
            "command": " ".join(parts),
            "mode": runtime["mode"],
            "container": runtime["container"],
            "url": runtime["url"],
        }
    parts = []
    if runtime["container"]:
        parts.append(f"CONTAINER={shlex.quote(runtime['container'])}")
    if runtime["engine"] in {"vllm", "llamacpp"}:
        parts.append(f"ENGINE_KIND={shlex.quote(runtime['engine'])}")
    parts.append("bash scripts/report.sh")
    return {
        "task": "report",
        "label": "Run Report",
        "command": " ".join(parts),
        "mode": runtime["mode"],
        "container": runtime["container"],
        "url": runtime["url"],
    }


def _run_admin_task_job(task_info):
    task = dict(task_info or {})
    task_name = str(task.get("task") or "task").strip() or "task"
    label = str(task.get("label") or task_name).strip() or task_name
    command = str(task.get("command") or "").strip()
    prefix = f"[admin-task {task_name}]"
    append_audit_text_line(f"{prefix} starting {command}")
    _set_admin_task_job(
        active=True,
        status="running",
        task=task_name,
        label=label,
        command=command,
        started_at=int(time.time()),
        finished_at=0,
        return_code=None,
        summary=f"{label} running",
        mode=str(task.get("mode") or ""),
        container=str(task.get("container") or ""),
        url=str(task.get("url") or ""),
    )
    rc = 999
    try:
        process = subprocess.Popen(
            ["bash", "-lc", command],
            cwd=CLUB3090_DIR,
            env=_repo_subprocess_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        try:
            if process.stdout is not None:
                for raw_line in process.stdout:
                    append_audit_text_line(f"{prefix} {str(raw_line or '').rstrip()}")
        finally:
            rc = int(process.wait())
    except Exception as e:
        append_audit_text_line(f"{prefix} launcher error: {e}")
        rc = 999
    if rc != 0:
        append_audit_text_line(f"{prefix} command failed with return code {rc}")
    summary = f"{label} {'completed' if rc == 0 else 'failed'} (rc={rc})"
    _set_admin_task_job(
        active=False,
        status=("success" if rc == 0 else "failed"),
        finished_at=int(time.time()),
        return_code=rc,
        summary=summary,
    )
    log_audit(
        "admin_task_job_finished",
        task=task_name,
        label=label,
        mode=str(task.get("mode") or ""),
        container=str(task.get("container") or ""),
        url=str(task.get("url") or ""),
        return_code=rc,
    )
    append_audit_text_line(f"{prefix} {summary}")


def start_admin_task_job(task_name):
    task_info = _build_admin_task_command(task_name)
    with admin_task_job_lock:
        if admin_task_job.get("active"):
            raise RuntimeError("Another admin task is already running")
    with model_install_job_lock:
        if model_install_job.get("active"):
            raise RuntimeError("Wait for the current model install job to finish before starting this task")
    _set_admin_task_job(
        active=True,
        status="queued",
        task=str(task_info.get("task") or ""),
        label=str(task_info.get("label") or ""),
        command=str(task_info.get("command") or ""),
        started_at=int(time.time()),
        finished_at=0,
        return_code=None,
        summary=f"{str(task_info.get('label') or task_name)} queued",
        mode=str(task_info.get("mode") or ""),
        container=str(task_info.get("container") or ""),
        url=str(task_info.get("url") or ""),
    )
    threading.Thread(
        target=_run_admin_task_job,
        args=(task_info,),
        name=f"club3090-admin-task-{_selector_token(task_name)}",
        daemon=True,
    ).start()
    log_audit(
        "admin_task_job_started",
        task=str(task_info.get("task") or ""),
        label=str(task_info.get("label") or ""),
        mode=str(task_info.get("mode") or ""),
        container=str(task_info.get("container") or ""),
        url=str(task_info.get("url") or ""),
    )
    return admin_task_job_snapshot()


def start_self_update_job(scope):
    scope_name = _selector_token(scope)
    if scope_name not in {"controller", "club3090"}:
        raise ValueError("Invalid update scope")
    with admin_task_job_lock:
        if admin_task_job.get("active"):
            raise RuntimeError("Wait for the current admin task to finish before starting an update")
    with model_install_job_lock:
        if model_install_job.get("active"):
            raise RuntimeError("Wait for the current model install job to finish before starting an update")
    mode_flag = "--update" if scope_name == "controller" else "--migrate"
    label = "admin script update" if scope_name == "controller" else "club-3090 migration"
    command = f"set -o pipefail; curl -fsSL https://tinyurl.com/club-3090-webserver | bash -s -- {mode_flag}"
    prefix = f"[self-update {scope_name}]"
    append_audit_text_line(f"{prefix} queued {label}")
    append_audit_text_line(f"{prefix} command: {command}")
    log_audit("self_update_job_started", scope=scope_name, command=command)
    audit_log_path = shlex.quote(AUDIT_LOG_FILE)
    launcher = (
        f'printf "%s\\n" "{prefix} starting {label}" >> {audit_log_path}; '
        "sleep 1; "
        f'bash -lc {shlex.quote(command)} >> {audit_log_path} 2>&1; '
        'rc=$?; '
        f'printf "%s\\n" "{prefix} finished (rc=${{rc}})" >> {audit_log_path}; '
        f'printf "%s\\n" "{prefix} update flow complete" >> {audit_log_path}'
    )
    subprocess.Popen(
        ["bash", "-lc", launcher],
        cwd=CLUB3090_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {
        "ok": True,
        "scope": scope_name,
        "label": label,
        "command": command,
        "focus_log_source": "audit",
    }


def default_target_request_metrics():
    return {
        "last_status": None,
        "last_latency_s": None,
        "last_ttft_s": None,
        "last_tokens_per_second": None,
        "last_estimated_tokens": None,
        "last_input_tokens": None,
        "last_output_tokens": None,
        "last_total_tokens": None,
        "last_tool_calls": None,
        "last_preset": None,
        "last_path": None,
        "last_request_at": 0,
    }


def snapshot_target_request_metrics():
    with metrics_lock:
        return {key: dict(value) for key, value in target_request_metrics.items()}

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
        if current_log_source in {"docker", "audit"} or re.fullmatch(r"service:[a-z0-9_-]+", current_log_source):
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
    if current_log_source in {"docker", "audit"} or re.fullmatch(r"service:[a-z0-9_-]+", current_log_source):
        current["current_log_source"] = current_log_source
    if data.get("selected_scope") not in (None, ""):
        current["selected_scope"] = str(data.get("selected_scope"))
    if current == original:
        return current, False
    write_json_atomic_if_changed(UI_CONFIG_FILE, current, separators=(",", ":"))
    return current, True


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


def default_chat_state():
    return {
        "revision": 0,
        "activeConversationId": "",
        "conversations": [],
        "promptTemplates": [],
    }


def _chat_attachment_kind(value):
    return "image" if str(value or "").strip().lower() == "image" else "text"


def sanitize_chat_attachment(item):
    item = item if isinstance(item, dict) else {}
    kind = _chat_attachment_kind(item.get("kind"))
    row = {
        "id": str(item.get("id") or "").strip(),
        "kind": kind,
        "name": str(item.get("name") or "").strip() or ("image" if kind == "image" else "attachment"),
        "mime": str(item.get("mime") or "").strip(),
        "source": str(item.get("source") or "").strip(),
    }
    if kind == "image":
        row["url"] = str(item.get("url") or "").strip()
    else:
        row["text"] = str(item.get("text") or "")
    size_bytes = item.get("size_bytes")
    try:
        if size_bytes not in (None, ""):
            row["size_bytes"] = max(0, int(size_bytes))
    except Exception:
        pass
    return row


def sanitize_chat_message(item):
    item = item if isinstance(item, dict) else {}
    row = {
        "role": str(item.get("role") or "").strip().lower() or "user",
        "text": str(item.get("text") or ""),
        "attachments": [sanitize_chat_attachment(attachment) for attachment in (item.get("attachments") or []) if isinstance(attachment, dict)],
    }
    for key in (
        "reasoningText",
        "reasoning_content",
        "reasoning",
        "modelLabel",
        "thinkingExpanded",
        "thinkingDone",
        "thinkingLive",
        "thinkingStartedAt",
        "thinkingDurationMs",
    ):
        value = item.get(key)
        if value not in (None, ""):
            row[key] = value
    return row


def sanitize_chat_conversation(item):
    item = item if isinstance(item, dict) else {}
    try:
        threshold_pct = int(item.get("autoCompactThresholdPct") or 95)
    except Exception:
        threshold_pct = 95
    try:
        compaction_sequence = max(1, int(item.get("compactionSequence") or 1))
    except Exception:
        compaction_sequence = 1
    row = {
        "id": str(item.get("id") or "").strip(),
        "title": str(item.get("title") or "").strip() or "Untitled conversation",
        "folder": str(item.get("folder") or "").strip(),
        "summary": str(item.get("summary") or ""),
        "autoNamed": bool(item.get("autoNamed")),
        "createdAt": int(item.get("createdAt") or int(time.time() * 1000)),
        "updatedAt": int(item.get("updatedAt") or int(time.time() * 1000)),
        "lastUsedAt": int(item.get("lastUsedAt") or int(time.time() * 1000)),
        "statsCollapsed": bool(item.get("statsCollapsed")),
        "presetId": str(item.get("presetId") or ""),
        "apiPresetName": str(item.get("apiPresetName") or ""),
        "params": dict(item.get("params") or {}) if isinstance(item.get("params"), dict) else {},
        "systemPrompt": str(item.get("systemPrompt") or ""),
        "autoCompactEnabled": item.get("autoCompactEnabled") is not False,
        "autoCompactThresholdPct": threshold_pct,
        "messages": [sanitize_chat_message(message) for message in (item.get("messages") or []) if isinstance(message, dict)],
        "attachments": [sanitize_chat_attachment(attachment) for attachment in (item.get("attachments") or []) if isinstance(attachment, dict)],
        "draftText": str(item.get("draftText") or ""),
        "compactedFromId": str(item.get("compactedFromId") or ""),
        "compactionSequence": compaction_sequence,
    }
    for key in (
        "lastInputTokens",
        "lastOutputTokens",
        "lastTotalTokens",
        "lastCtxSizeTokens",
        "lastKvCacheUsagePct",
        "lastRuntimeRequestAt",
        "lastStatus",
        "lastLatencySeconds",
        "lastTtftSeconds",
        "lastTokensPerSecond",
        "lastTokensPerSecondPeak",
        "lastToolCalls",
        "lastRequestPath",
    ):
        value = item.get(key)
        if value not in (None, ""):
            row[key] = value
    return row


def chat_conversation_title_summary(item):
    row = sanitize_chat_conversation(item)
    return {
        "id": str(row.get("id") or "").strip(),
        "title": str(row.get("title") or "Untitled conversation").strip() or "Untitled conversation",
        "folder": str(row.get("folder") or "").strip(),
        "updatedAt": int(row.get("updatedAt") or int(time.time() * 1000)),
        "lastUsedAt": int(row.get("lastUsedAt") or int(time.time() * 1000)),
        "messagesLoaded": False,
    }


def read_chat_state_titles():
    state = read_chat_state()
    debug_audit(
        "chat_state_titles",
        revision=max(0, int(state.get("revision") or 0)),
        active_conversation_id=str(state.get("activeConversationId") or "").strip(),
        conversation_count=len(state.get("conversations") or []),
    )
    return {
        "revision": max(0, int(state.get("revision") or 0)),
        "activeConversationId": str(state.get("activeConversationId") or "").strip(),
        "conversations": [
            chat_conversation_title_summary(conversation)
            for conversation in (state.get("conversations") or [])
            if isinstance(conversation, dict)
        ],
        "promptTemplates": list(state.get("promptTemplates") or []),
    }


def read_chat_conversation_detail(conversation_id):
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        raise ValueError("Conversation id is required.")
    state = read_chat_state()
    conversation = next(
        (
            row
            for row in (state.get("conversations") or [])
            if isinstance(row, dict) and str(row.get("id") or "").strip() == conversation_id
        ),
        None,
    )
    if not conversation:
        debug_audit(
            "chat_conversation_detail_missing",
            conversation_id=conversation_id,
            revision=max(0, int(state.get("revision") or 0)),
            known_ids=[
                str(row.get("id") or "").strip()
                for row in (state.get("conversations") or [])
                if isinstance(row, dict)
            ][:24],
        )
        raise ValueError("Conversation not found.")
    detail = sanitize_chat_conversation(conversation)
    detail["messagesLoaded"] = True
    debug_audit(
        "chat_conversation_detail",
        conversation_id=conversation_id,
        revision=max(0, int(state.get("revision") or 0)),
        message_count=len(detail.get("messages") or []),
        attachment_count=len(detail.get("attachments") or []),
        title=str(detail.get("title") or ""),
    )
    return {
        "ok": True,
        "revision": max(0, int(state.get("revision") or 0)),
        "conversation": detail,
    }


def merge_chat_state_payload(payload, current_state):
    payload = payload if isinstance(payload, dict) else {}
    current_state = current_state if isinstance(current_state, dict) else default_chat_state()
    existing_by_id = {
        str(row.get("id") or "").strip(): sanitize_chat_conversation(row)
        for row in (current_state.get("conversations") or [])
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }
    merged_rows = []
    preserved_detail_rows = 0
    for raw_row in payload.get("conversations") or []:
        if not isinstance(raw_row, dict):
            continue
        conversation_id = str(raw_row.get("id") or "").strip()
        if not conversation_id:
            continue
        if raw_row.get("messagesLoaded") is False and conversation_id in existing_by_id:
            existing = dict(existing_by_id[conversation_id])
            existing["title"] = str(raw_row.get("title") or existing.get("title") or "Untitled conversation").strip() or "Untitled conversation"
            existing["folder"] = str(raw_row.get("folder") or existing.get("folder") or "").strip()
            existing["updatedAt"] = int(raw_row.get("updatedAt") or existing.get("updatedAt") or int(time.time() * 1000))
            existing["lastUsedAt"] = int(raw_row.get("lastUsedAt") or existing.get("lastUsedAt") or int(time.time() * 1000))
            merged_rows.append(existing)
            preserved_detail_rows += 1
            continue
        merged_rows.append(sanitize_chat_conversation(raw_row))
    debug_audit(
        "chat_state_merge",
        incoming_revision=payload.get("revision") or 0,
        current_revision=current_state.get("revision") or 0,
        incoming_conversation_count=len(payload.get("conversations") or []),
        merged_conversation_count=len(merged_rows),
        preserved_detail_rows=preserved_detail_rows,
        active_conversation_id=str(payload.get("activeConversationId") or current_state.get("activeConversationId") or "").strip(),
    )
    return {
        "revision": payload.get("revision") or 0,
        "activeConversationId": str(payload.get("activeConversationId") or current_state.get("activeConversationId") or "").strip(),
        "conversations": merged_rows,
        "promptTemplates": list(payload.get("promptTemplates") or current_state.get("promptTemplates") or []),
    }


def sanitize_chat_state_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    try:
        revision = max(0, int(payload.get("revision") or 0))
    except Exception:
        revision = 0
    conversations = []
    seen_ids = set()
    for conversation in (payload.get("conversations") or []):
        if not isinstance(conversation, dict):
            continue
        row = sanitize_chat_conversation(conversation)
        conversation_id = str(row.get("id") or "").strip()
        if not conversation_id or conversation_id in seen_ids:
            continue
        seen_ids.add(conversation_id)
        conversations.append(row)
    prompt_templates = []
    for item in payload.get("promptTemplates") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        text = str(item.get("text") or "")
        if not name and not text:
            continue
        prompt_templates.append(
            {
                "id": str(item.get("id") or secrets.token_hex(6)),
                "name": name,
                "text": text,
            }
        )
    active_id = str(payload.get("activeConversationId") or "").strip()
    if active_id and not any(str(row.get("id") or "").strip() == active_id for row in conversations):
        active_id = ""
    if not active_id and conversations:
        active_id = str(conversations[0].get("id") or "")
    return {
        "revision": revision,
        "activeConversationId": active_id,
        "conversations": conversations,
        "promptTemplates": prompt_templates,
    }


def read_chat_state():
    data = read_json_file(CHAT_STATE_FILE, default_chat_state())
    state = sanitize_chat_state_payload(data)
    debug_audit(
        "chat_state_read",
        revision=max(0, int(state.get("revision") or 0)),
        active_conversation_id=str(state.get("activeConversationId") or "").strip(),
        conversation_count=len(state.get("conversations") or []),
        prompt_template_count=len(state.get("promptTemplates") or []),
    )
    return state


def write_chat_state(payload):
    current_state = read_chat_state()
    state = sanitize_chat_state_payload(merge_chat_state_payload(payload, current_state))
    current_revision = max(0, int(current_state.get("revision") or 0))
    incoming_revision = max(0, int(state.get("revision") or 0))
    if incoming_revision and incoming_revision <= current_revision:
        debug_audit(
            "chat_state_write_rejected",
            current_revision=current_revision,
            incoming_revision=incoming_revision,
            current_active_conversation_id=str(current_state.get("activeConversationId") or "").strip(),
            incoming_active_conversation_id=str(state.get("activeConversationId") or "").strip(),
            current_conversation_count=len(current_state.get("conversations") or []),
            incoming_conversation_count=len(state.get("conversations") or []),
        )
        return current_state
    state["revision"] = max(current_revision + 1, incoming_revision or 0)
    write_json_file(CHAT_STATE_FILE, state)
    removed_attachments = prune_unused_chat_attachments(state)
    debug_audit(
        "chat_state_write",
        previous_revision=current_revision,
        incoming_revision=incoming_revision,
        written_revision=state["revision"],
        active_conversation_id=str(state.get("activeConversationId") or "").strip(),
        conversation_count=len(state.get("conversations") or []),
        removed_attachment_count=len(removed_attachments),
    )
    return state


def _chat_attachment_blob_path(attachment_id):
    return os.path.join(CHAT_ATTACHMENTS_DIR, f"{attachment_id}.bin")


def _chat_attachment_meta_path(attachment_id):
    return os.path.join(CHAT_ATTACHMENTS_DIR, f"{attachment_id}.json")


def chat_attachment_url(attachment_id):
    return f"/admin/chat-attachments/{attachment_id}"


def read_chat_attachment_meta(attachment_id):
    return read_json_file(_chat_attachment_meta_path(attachment_id), {})


def save_chat_attachment(item):
    item = item if isinstance(item, dict) else {}
    kind = _chat_attachment_kind(item.get("kind"))
    if kind != "image":
        raise ValueError("Only image attachments are uploaded separately.")
    data_url = str(item.get("data_url") or "").strip()
    if not data_url.startswith("data:") or ";base64," not in data_url:
        raise ValueError("Image attachment must include a base64 data URL.")
    header, encoded = data_url.split(",", 1)
    mime = str(item.get("mime") or "").strip()
    if not mime:
        mime = str(header[5:].split(";", 1)[0] or "").strip()
    if not mime.startswith("image/"):
        raise ValueError("Only image attachments are supported.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("Invalid image attachment encoding.") from exc
    attachment_id = str(item.get("id") or f"chat-attachment-{secrets.token_hex(8)}").strip()
    if not attachment_id:
        raise ValueError("Attachment id is required.")
    os.makedirs(CHAT_ATTACHMENTS_DIR, exist_ok=True)
    with open(_chat_attachment_blob_path(attachment_id), "wb") as handle:
        handle.write(raw)
    meta = {
        "id": attachment_id,
        "kind": "image",
        "name": str(item.get("name") or "image").strip() or "image",
        "mime": mime,
        "source": str(item.get("source") or "").strip(),
        "size_bytes": len(raw),
        "created_at": int(time.time()),
        "url": chat_attachment_url(attachment_id),
    }
    write_json_file(_chat_attachment_meta_path(attachment_id), meta)
    return meta


def read_chat_attachment_response(attachment_id):
    meta = read_chat_attachment_meta(attachment_id)
    if not isinstance(meta, dict) or not meta.get("id"):
        return None, None
    blob_path = _chat_attachment_blob_path(attachment_id)
    try:
        with open(blob_path, "rb") as handle:
            payload = handle.read()
    except Exception:
        return None, None
    mime = str(meta.get("mime") or "").strip() or "application/octet-stream"
    return payload, mime


def local_chat_attachment_id_from_url(url):
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        path = urlsplit(raw).path
    except Exception:
        path = raw
    prefix = "/admin/chat-attachments/"
    if not path.startswith(prefix):
        return ""
    attachment_id = path[len(prefix):].strip().split("/", 1)[0]
    return re.sub(r"[^A-Za-z0-9._-]+", "", attachment_id)


def _collect_chat_attachment_ids_from_attachment(item):
    item = item if isinstance(item, dict) else {}
    attachment_ids = set()
    attachment_id = re.sub(r"[^A-Za-z0-9._-]+", "", str(item.get("id") or "").strip())
    if attachment_id:
        attachment_ids.add(attachment_id)
    url_attachment_id = local_chat_attachment_id_from_url(item.get("url") or "")
    if url_attachment_id:
        attachment_ids.add(url_attachment_id)
    return attachment_ids


def collect_chat_attachment_ids_from_state(state):
    attachment_ids = set()
    state = state if isinstance(state, dict) else {}
    for conversation in state.get("conversations") or []:
        if not isinstance(conversation, dict):
            continue
        for attachment in conversation.get("attachments") or []:
            attachment_ids.update(_collect_chat_attachment_ids_from_attachment(attachment))
        for message in conversation.get("messages") or []:
            if not isinstance(message, dict):
                continue
            for attachment in message.get("attachments") or []:
                attachment_ids.update(_collect_chat_attachment_ids_from_attachment(attachment))
    return attachment_ids


def prune_unused_chat_attachments(state):
    referenced_ids = collect_chat_attachment_ids_from_state(state)
    if not os.path.isdir(CHAT_ATTACHMENTS_DIR):
        return []
    removed_ids = []
    for suffix in ("*.bin", "*.json"):
        for path in glob.glob(os.path.join(CHAT_ATTACHMENTS_DIR, suffix)):
            attachment_id = re.sub(r"[^A-Za-z0-9._-]+", "", os.path.splitext(os.path.basename(path))[0])
            if attachment_id and attachment_id not in referenced_ids:
                try:
                    os.remove(path)
                    removed_ids.append(attachment_id)
                except FileNotFoundError:
                    pass
                except Exception:
                    continue
    return sorted(set(removed_ids))


def delete_chat_conversation(conversation_id):
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        raise ValueError("Conversation id is required.")
    state = read_chat_state()
    conversations = list(state.get("conversations") or [])
    conversation = next((row for row in conversations if str(row.get("id") or "") == conversation_id), None)
    if not conversation:
        raise ValueError("Conversation not found.")
    next_rows = [row for row in conversations if str(row.get("id") or "") != conversation_id]
    next_active_id = str(state.get("activeConversationId") or "").strip()
    if next_active_id == conversation_id:
        next_active_id = str(next_rows[0].get("id") or "") if next_rows else ""
    next_state = write_chat_state(
        {
            "revision": max(0, int(state.get("revision") or 0)) + 1,
            "activeConversationId": next_active_id,
            "conversations": next_rows,
            "promptTemplates": state.get("promptTemplates") or [],
        }
    )
    debug_audit(
        "chat_conversation_delete",
        conversation_id=conversation_id,
        previous_revision=max(0, int(state.get("revision") or 0)),
        next_revision=max(0, int(next_state.get("revision") or 0)),
        remaining_conversation_count=len(next_state.get("conversations") or []),
        next_active_conversation_id=str(next_state.get("activeConversationId") or "").strip(),
    )
    log_audit(
        "admin_chat_delete",
        conversation_id=conversation_id,
        title=str(conversation.get("title") or "").strip() or "Untitled conversation",
        messages=len(conversation.get("messages") or []),
        attachments=len(conversation.get("attachments") or []),
    )
    return {
        "ok": True,
        "conversation_id": conversation_id,
        "state": next_state,
    }


def chat_attachment_data_url(url):
    attachment_id = local_chat_attachment_id_from_url(url)
    if not attachment_id:
        return str(url or "").strip()
    payload, mime = read_chat_attachment_response(attachment_id)
    if payload is None:
        return str(url or "").strip()
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


def _format_model_display_name(model_id):
    if not model_id:
        return "Unknown Model"
    if model_id == "qwen3.6-27b":
        return "Qwen3.6-27B"
    if model_id == "gemma-4-31b":
        return "Gemma 4 31B"
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
    env_map = _load_repo_env_map()
    raw = str(env_map.get("MODEL_DIR") or "").strip()
    if not raw:
        return os.path.join(CLUB3090_DIR, "models-cache")
    if os.path.isabs(raw):
        return raw
    compose_root = str((variant or {}).get("compose_project_dir_abs_path") or "").strip()
    if compose_root:
        candidate = os.path.normpath(os.path.join(compose_root, raw))
        if os.path.exists(candidate):
            return candidate
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
    match = re.match(r"^\$\{[^}:]+:-([^}]+)\}$", text)
    if match:
        return match.group(1).strip()
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


def _normalize_status_kind(status_raw):
    text = str(status_raw or "").strip().lower()
    if not text:
        return "unknown"
    if "tombstoned" in text or "not shipping" in text:
        return "tombstoned"
    if "hardware-blocked" in text or ("blocked" in text and "hardware" in text):
        return "blocked"
    if "deprecated" in text:
        return "deprecated"
    if "upstream" in text and ("blocked" in text or "gated" in text):
        return "upstream_gated"
    if "preview" in text:
        return "preview"
    if "experimental" in text or "community" in text:
        return "experimental"
    if "working" in text:
        return "production_caveat"
    if "caveat" in text or "known issue" in text or "warning" in text:
        return "production_caveat"
    if "production" in text or "prod" in text:
        return "production"
    return "unknown"


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
                match = re.match(r"^#\s*([A-Za-z0-9_-]+)\s*:\s*(.+?)\s*$", line)
                if not match:
                    continue
                target_key = key_map.get(str(match.group(1) or "").strip().lower())
                if not target_key:
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
                        command_items.append(item)
                        continue
                    if command_block_mode:
                        block_line = stripped
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
        if item == "-c" and idx + 1 < len(command_items) and max_model_len is None:
            max_model_len = _extract_default_number(command_items[idx + 1], minimum_digits=4)
        elif item.startswith("-c=") and max_model_len is None:
            max_model_len = _extract_default_number(item.split("=", 1)[1], minimum_digits=4)
        if item == "--mmproj" and idx + 1 < len(command_items):
            mmproj_path = _extract_shell_default_value(command_items[idx + 1])
        elif item.startswith("--mmproj="):
            mmproj_path = _extract_shell_default_value(item.split("=", 1)[1])
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


def _parse_switch_variants():
    switch_path = os.path.join(CLUB3090_DIR, "scripts", "switch.sh")
    tag_by_compose = {}
    if not os.path.exists(switch_path):
        return tag_by_compose
    try:
        with open(switch_path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = str(raw_line or "").strip()
                match = re.match(r'^\[([^\]]+)\]="([^|"]+)\|([^|"]+)\|([^"]+)"$', line)
                if not match:
                    continue
                tag = match.group(1).strip()
                compose_dir = match.group(3).strip().strip("/")
                compose_file = match.group(4).strip().strip("/")
                rel_path = (compose_dir + "/" + compose_file).replace("\\", "/").strip("/")
                if tag and rel_path:
                    tag_by_compose[rel_path] = tag
    except Exception:
        return {}
    return tag_by_compose


def _qwen_llamacpp_install_command(model_dir_root):
    model_root = os.path.join(model_dir_root, "qwen3.6-27b-gguf")
    gguf_dir = os.path.join(model_root, "unsloth-q3kxl")
    return (
        f'hf download unsloth/Qwen3.6-27B-GGUF Qwen3.6-27B-UD-Q3_K_XL.gguf mmproj-F16.gguf --local-dir "{gguf_dir}"'
        f' && mkdir -p "{model_root}"'
        f' && if [ -f "{os.path.join(gguf_dir, "mmproj-F16.gguf")}" ]; then cp -f "{os.path.join(gguf_dir, "mmproj-F16.gguf")}" "{os.path.join(model_root, "mmproj-F16.gguf")}"; fi'
    )


def _known_hf_download_command(model_dir_root, repo_id, subdir):
    target_dir = os.path.join(model_dir_root, subdir)
    return f'hf download {repo_id} --local-dir "{target_dir}"'


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
            candidate = os.path.join(gguf_root, "unsloth-q3kxl", "Qwen3.6-27B-UD-Q3_K_XL.gguf")
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
            install_command = _qwen_llamacpp_install_command(model_dir_root)
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
            "model_id": str(entry.get("model_id") or "").strip(),
            "engine": str(entry.get("engine") or "").strip(),
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
            "max_model_len": entry.get("max_model_len"),
            "drafter": str(entry.get("drafter") or "").strip(),
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
            "engine_profile": str(entry.get("engine_profile") or "").strip(),
            "nvlink_mode": str(entry.get("nvlink_mode") or "").strip(),
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


def rebuild_runtime_inventory():
    global runtime_inventory_cache, runtime_inventory_built_at
    repo_root = os.path.abspath(CLUB3090_DIR)
    tag_by_compose = _parse_switch_variants()
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
    inventory = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo_root": repo_root,
        "repo_head": repo_head,
        "switch_script_present": os.path.exists(os.path.join(repo_root, "scripts", "switch.sh")),
        "setup_script_present": os.path.exists(os.path.join(repo_root, "scripts", "setup.sh")),
        "launch_script_present": os.path.exists(os.path.join(repo_root, "scripts", "launch.sh")),
        "update_script_present": os.path.exists(os.path.join(repo_root, "scripts", "update.sh")),
        "models": [],
        "variants": [],
    }
    model_rows = {}
    pattern = os.path.join(repo_root, "models", "*", "*", "compose", "**", "*.yml")
    compose_paths = sorted(glob.glob(pattern, recursive=True))
    for compose_abs_path in compose_paths:
        rel_path = os.path.relpath(compose_abs_path, repo_root).replace("\\", "/")
        parts = rel_path.split("/")
        if len(parts) < 6 or parts[0] != "models":
            continue
        model_id = parts[1]
        engine = _normalize_engine(parts[2])
        topology = parts[4]
        profile = _read_compose_profile_header(compose_abs_path)
        status_hints = _read_compose_status_hints(compose_abs_path)
        hardware_meta = _read_compose_hardware_metadata(compose_abs_path)
        runtime_meta = _read_compose_runtime_metadata(compose_abs_path)
        status_text = str(profile.get("status") or "").strip()
        if not status_text:
            status_text = status_hints
        variant = {
            "variant_id": _variant_id_from_rel_path(rel_path),
            "upstream_tag": tag_by_compose.get(rel_path),
            "model_id": model_id,
            "engine": engine,
            "topology": topology,
            "compose_rel_path": rel_path,
            "compose_abs_path": compose_abs_path,
            "compose_dir_abs_path": os.path.dirname(compose_abs_path),
            "compose_project_dir_abs_path": os.path.join(repo_root, "models", model_id, parts[2], "compose"),
            "service_name": runtime_meta.get("service_name") or "",
            "container_name": runtime_meta.get("container_name") or "",
            "default_port": runtime_meta.get("default_port") or 0,
            "served_model_name": runtime_meta.get("served_model_name") or "",
            "max_model_len": runtime_meta.get("max_model_len") or _extract_token_count(profile.get("max_ctx")),
            "model_path": runtime_meta.get("model_path") or "",
            "mmproj_path": runtime_meta.get("mmproj_path") or "",
            "draft_model_path": runtime_meta.get("draft_model_path") or "",
            "drafter": str(profile.get("drafter") or "").strip(),
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
        }
        if variant["status_kind"] == "unknown" and variant["caveats"]:
            variant["status_kind"] = "production_caveat"
        variant["category"] = _category_for_variant(variant["topology"], variant["status_kind"])
        variant["scope_kind"] = _scope_kind_for_topology(variant["topology"])
        variant.update(_detect_variant_install_state(variant, _resolve_variant_model_dir_root(variant)))
        inventory["variants"].append(variant)
        model_row = model_rows.setdefault(
            model_id,
            {
                "model_id": model_id,
                "display_name": _format_model_display_name(model_id),
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
            },
        )
        if engine not in model_row["engine_groups"]:
            model_row["engine_groups"].append(engine)
        if variant["category"] in model_row["categories"]:
            model_row["categories"][variant["category"]].append(variant["variant_id"])
        if not model_row["summary"] and variant["best_for"]:
            model_row["summary"] = variant["best_for"]
    for model_id, model_row in model_rows.items():
        variants = [row for row in inventory["variants"] if row.get("model_id") == model_id]
        safe_variants = [row for row in variants if row.get("status_kind") in {"production", "production_caveat"}]
        any_ready = any(row.get("install_state") == "ready" for row in safe_variants)
        any_known = any(row.get("install_state") in {"ready", "requires_download"} for row in variants)
        any_partial = any(row.get("install_state") == "ready" for row in variants)
        any_downloadable = any(row.get("install_state") == "requires_download" for row in variants)
        preferred_summary_order = {"vllm/default": 0, "vllm/gemma-mtp": 0, "llamacpp/default": 1}
        preferred_summaries = [
            row for row in variants
            if str(row.get("upstream_tag") or "") in preferred_summary_order
        ]
        preferred_summaries.sort(key=lambda row: preferred_summary_order.get(str(row.get("upstream_tag") or ""), 99))
        if preferred_summaries:
            model_row["summary"] = str(preferred_summaries[0].get("best_for") or model_row.get("summary") or "")
        else:
            fallback_summary = next((str(row.get("best_for") or "") for row in safe_variants if row.get("best_for")), "")
            if fallback_summary:
                model_row["summary"] = fallback_summary
        model_row["default_install_command"] = next(
            (
                str(row.get("install_command") or "")
                for row in variants
                if row.get("install_command")
                and str(row.get("engine") or "") == "vllm"
                and "WITH_DFLASH_DRAFT=1" not in str(row.get("install_command") or "")
            ),
            "",
        )
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
    inventory["models"].sort(key=lambda row: row.get("display_name") or row.get("model_id") or "")
    inventory["variants"].sort(key=lambda row: (row.get("model_id") or "", row.get("category") or "", _mode_selector_for_variant(row)))
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
        "gpu_pairing_enabled": True,
        "selected_preset_model": "",
        "mcp_servers": [],
    }


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
    if "gpu_pairing_enabled" in data:
        merged["gpu_pairing_enabled"] = bool(data.get("gpu_pairing_enabled"))
    else:
        merged["gpu_pairing_enabled"] = detect_gpu_count_runtime() != 2
    try:
        merged["local_api_port"] = int(merged.get("local_api_port", LOCAL_API_PORT))
    except Exception:
        merged["local_api_port"] = LOCAL_API_PORT
    merged["https_cert_file"] = str(merged.get("https_cert_file") or HTTPS_CERT_FILE)
    merged["https_key_file"] = str(merged.get("https_key_file") or HTTPS_KEY_FILE)
    merged["admin_path"] = "/admin"
    merged["selected_preset_model"] = str(data.get("selected_preset_model") or "").strip()
    merged["mcp_servers"] = sanitize_mcp_servers(data.get("mcp_servers") or [])
    return merged


def write_server_config(data):
    current = read_server_config()
    original = dict(current)
    for key in ("allow_proxy_without_api_key", "online_enabled", "upnp_enabled", "https_enabled", "local_api_enabled", "gpu_pairing_enabled"):
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
    if "mcp_servers" in data:
        current["mcp_servers"] = sanitize_mcp_servers(data.get("mcp_servers") or [])
    current["admin_path"] = "/admin"
    if current != original:
        write_json_file(SERVER_CONFIG_FILE, current)
    return current


MCP_CLIENTS = {}
MCP_CLIENTS_LOCK = threading.Lock()


class McpStdioClient:
    def __init__(self, server_row):
        self.server = dict(server_row or {})
        self.proc = None
        self.lock = threading.Lock()
        self.request_id = 0

    def _ensure_started(self):
        if self.proc and self.proc.poll() is None:
            return
        command = str(self.server.get("command") or "").strip()
        if not command:
            raise RuntimeError("MCP server command is empty")
        self.proc = subprocess.Popen(
            shlex.split(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=CLUB3090_DIR,
            bufsize=0,
        )
        self.request_id += 1
        init_id = self.request_id
        self._write_message({"jsonrpc": "2.0", "id": init_id, "method": "initialize", "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "club3090-control", "version": SCRIPT_VERSION},
        }})
        while True:
            payload = self._read_message(timeout=20)
            if payload.get("id") != init_id:
                continue
            if payload.get("error"):
                raise RuntimeError(str(payload.get("error")))
            break
        self._write_message({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def _write_message(self, payload):
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("utf-8")
        self.proc.stdin.write(header + raw)
        self.proc.stdin.flush()

    def _read_message(self, timeout=20):
        stdout = self.proc.stdout
        if stdout is None:
            raise RuntimeError("MCP stdout is unavailable")
        fd = stdout.fileno()
        deadline = time.time() + max(1.0, float(timeout or 20))
        header = b""
        while b"\r\n\r\n" not in header:
            remaining = max(0.1, deadline - time.time())
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                raise RuntimeError("Timed out waiting for MCP response headers")
            chunk = os.read(fd, 1)
            if not chunk:
                raise RuntimeError("MCP server closed the connection")
            header += chunk
        header_text = header.decode("utf-8", errors="ignore")
        match = re.search(r"Content-Length:\s*(\d+)", header_text, re.I)
        if not match:
            raise RuntimeError("MCP response did not include Content-Length")
        length = int(match.group(1))
        body = b""
        while len(body) < length:
            remaining = max(0.1, deadline - time.time())
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                raise RuntimeError("Timed out waiting for MCP response body")
            chunk = os.read(fd, length - len(body))
            if not chunk:
                raise RuntimeError("MCP server closed during response body")
            body += chunk
        return json.loads(body.decode("utf-8", errors="ignore") or "{}")

    def _notify(self, method, params):
        with self.lock:
            self._ensure_started()
            self._write_message({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _request(self, method, params, timeout=20):
        with self.lock:
            self._ensure_started()
            self.request_id += 1
            req_id = self.request_id
            self._write_message({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
            while True:
                payload = self._read_message(timeout=timeout)
                if payload.get("id") != req_id:
                    continue
                if payload.get("error"):
                    raise RuntimeError(str(payload.get("error")))
                return payload.get("result") or {}

    def tools(self):
        result = self._request("tools/list", {}, timeout=20)
        return list(result.get("tools") or [])

    def call_tool(self, name, arguments):
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}}, timeout=60)
        return result

    def close(self):
        proc = self.proc
        self.proc = None
        if not proc:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _parse_mcp_sse_response(body_text, request_id):
    matched_result = None
    matched_error = None
    frame_lines = []
    for raw_line in str(body_text or "").splitlines() + [""]:
        if raw_line.strip():
            frame_lines.append(raw_line)
            continue
        if not frame_lines:
            continue
        payload_lines = [line[5:].lstrip() for line in frame_lines if line.startswith("data:")]
        frame_lines = []
        if not payload_lines:
            continue
        try:
            payload = json.loads("\n".join(payload_lines))
        except Exception:
            continue
        if payload.get("id") != request_id:
            continue
        if payload.get("error"):
            matched_error = payload.get("error")
            break
        matched_result = payload.get("result") or {}
        break
    if matched_error:
        raise RuntimeError(str(matched_error))
    return matched_result or {}


class McpHttpClient:
    def __init__(self, server_row):
        self.server = dict(server_row or {})
        self.endpoint = mcp_server_endpoint(server_row)
        self.lock = threading.Lock()
        self.request_id = 0
        self.initialized = False
        self.session_id = ""

    def _headers(self):
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
            "User-Agent": f"club3090-control/{SCRIPT_VERSION}",
        }
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
        return headers

    def _read_response(self, response, request_id):
        session_id = str(response.headers.get("MCP-Session-Id") or "").strip()
        if session_id:
            self.session_id = session_id
        content_type = str(response.headers.get("Content-Type") or "").lower()
        raw = response.read()
        if not raw:
            return {}
        if "text/event-stream" in content_type:
            return _parse_mcp_sse_response(raw.decode("utf-8", errors="ignore"), request_id)
        payload = json.loads(raw.decode("utf-8", errors="ignore") or "{}")
        if payload.get("error"):
            raise RuntimeError(str(payload.get("error")))
        return payload.get("result") or {}

    def _ensure_started(self):
        if self.initialized:
            return
        self.request_id += 1
        req_id = self.request_id
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "club3090-control", "version": SCRIPT_VERSION},
            },
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            self._read_response(response, req_id)
        self.initialized = True
        try:
            self._notify("notifications/initialized", {})
        except Exception:
            pass

    def _notify(self, method, params):
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}}, separators=(",", ":")).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                session_id = str(response.headers.get("MCP-Session-Id") or "").strip()
                if session_id:
                    self.session_id = session_id
                response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(detail or str(exc))

    def _request(self, method, params, timeout=20):
        with self.lock:
            self._ensure_started()
            self.request_id += 1
            req_id = self.request_id
            payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
            request = urllib.request.Request(
                self.endpoint,
                data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                headers=self._headers(),
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=max(5, int(timeout or 20))) as response:
                    return self._read_response(response, req_id)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                raise RuntimeError(detail or str(exc))

    def tools(self):
        result = self._request("tools/list", {}, timeout=20)
        return list(result.get("tools") or [])

    def call_tool(self, name, arguments):
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}}, timeout=60)
        return result

    def close(self):
        if not self.session_id:
            return
        request = urllib.request.Request(
            self.endpoint,
            headers=self._headers(),
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read()
        except Exception:
            pass
        self.session_id = ""
        self.initialized = False


def get_mcp_client(server_row):
    server_id = str(server_row.get("id") or "").strip()
    if not server_id:
        raise RuntimeError("Invalid MCP server definition")
    transport = mcp_server_transport(server_row)
    command = str(server_row.get("command") or "").strip()
    with MCP_CLIENTS_LOCK:
        client = MCP_CLIENTS.get(server_id)
        if client and client.server.get("command") == command and client.server.get("transport") == transport:
            return client
        if client:
            client.close()
        server_copy = {**dict(server_row or {}), "transport": transport}
        client = McpHttpClient(server_copy) if transport == "http" else McpStdioClient(server_copy)
        MCP_CLIENTS[server_id] = client
        return client


def close_removed_mcp_clients(server_rows):
    active_ids = {str(row.get("id") or "").strip() for row in server_rows if isinstance(row, dict)}
    with MCP_CLIENTS_LOCK:
        for server_id, client in list(MCP_CLIENTS.items()):
            if server_id not in active_ids:
                try:
                    client.close()
                finally:
                    MCP_CLIENTS.pop(server_id, None)


def mcp_server_status(server_row):
    row = dict(server_row or {})
    transport = mcp_server_transport(row)
    if not row.get("enabled"):
        return {**row, "transport": transport, "endpoint": mcp_server_endpoint(row), "status": "disabled", "tools": [], "error": ""}
    try:
        client = get_mcp_client(row)
        tools = client.tools()
        return {
            **row,
            "transport": transport,
            "endpoint": mcp_server_endpoint(row),
            "status": "connected",
            "tools": [
                {
                    "name": str(tool.get("name") or ""),
                    "description": str(tool.get("description") or ""),
                }
                for tool in tools
                if isinstance(tool, dict)
            ],
            "error": "",
        }
    except Exception as e:
        return {**row, "transport": transport, "endpoint": mcp_server_endpoint(row), "status": "error", "tools": [], "error": str(e)}

def validate_mcp_server_row(server_row):
    row = dict(server_row or {})
    command = str(row.get("command") or "").strip()
    if not command:
        raise ValueError("MCP server command or URL is required")
    if mcp_server_transport(row) == "http" and not re.match(r"^https?://", command, re.I):
        raise ValueError("Remote MCP endpoints must start with http:// or https://")
    client = get_mcp_client(row)
    tools = client.tools()
    return {
        **row,
        "transport": mcp_server_transport(row),
        "endpoint": mcp_server_endpoint(row),
        "status": "connected",
        "tools": [
            {
                "name": str(tool.get("name") or ""),
                "description": str(tool.get("description") or ""),
            }
            for tool in tools
            if isinstance(tool, dict)
        ],
        "error": "",
    }


def list_mcp_server_statuses():
    rows = sanitize_mcp_servers(read_server_config().get("mcp_servers") or [])
    close_removed_mcp_clients(rows)
    return [mcp_server_status(row) for row in rows]


def build_enabled_mcp_tools():
    tools = []
    tool_map = {}
    for server in list_mcp_server_statuses():
        if server.get("status") != "connected":
            continue
        client = get_mcp_client(server)
        for tool in client.tools():
            if not isinstance(tool, dict):
                continue
            base_name = str(tool.get("name") or "").strip()
            if not base_name:
                continue
            qualified = f"{server['id']}__{base_name}"
            tool_map[qualified] = {"server": server, "name": base_name}
            tools.append({
                "type": "function",
                "function": {
                    "name": qualified,
                    "description": str(tool.get("description") or f"{server['name']} :: {base_name}"),
                    "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
                },
            })
    return tools, tool_map


def call_enabled_mcp_tool(tool_name, arguments, tool_map):
    mapping = dict(tool_map.get(str(tool_name) or "") or {})
    if not mapping:
        raise RuntimeError(f"Unknown MCP tool: {tool_name}")
    client = get_mcp_client(mapping["server"])
    result = client.call_tool(mapping["name"], arguments or {})
    parts = []
    for item in list(result.get("content") or []):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
        elif "text" in item:
            parts.append(str(item.get("text") or ""))
    if not parts and result.get("structuredContent") is not None:
        parts.append(json.dumps(result.get("structuredContent"), indent=2, ensure_ascii=False))
    return "\n".join([part for part in parts if part]).strip() or json.dumps(result, indent=2, ensure_ascii=False)


def ensure_local_api_token():
    try:
        if os.path.exists(LOCAL_API_TOKEN_FILE):
            token = open(LOCAL_API_TOKEN_FILE, "r", encoding="utf-8").read().strip()
            if token:
                return token
        token = secrets.token_urlsafe(32)
        os.makedirs(CONTROL_DIR, exist_ok=True)
        with open(LOCAL_API_TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(token + "\n")
        os.chmod(LOCAL_API_TOKEN_FILE, 0o600)
        return token
    except Exception:
        return ""


def safe_user_name(name):
    name = str(name or "").strip()
    if not name:
        raise ValueError("User name is required")
    if len(name) > 64:
        raise ValueError("User name is too long")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError("User names may only contain letters, numbers, dot, underscore, and hyphen")
    return name


def normalize_limit_int(value):
    if value in ("", None, False):
        return None
    n = int(value)
    if n < 0:
        raise ValueError("Limits cannot be negative")
    return n


def normalize_limit_float(value):
    if value in ("", None, False):
        return None
    n = float(value)
    if n < 0:
        raise ValueError("Limits cannot be negative")
    return round(n, 3)


DEFAULT_USAGE_WEIGHTS = {
    "input_tokens": 1.0,
    "output_tokens": 1.0,
    "tool_calls": 4000.0,
    "thinking_seconds": 250.0,
}
USAGE_RETENTION_SECONDS = 8 * 24 * 3600


def first_defined(*values):
    for value in values:
        if value not in ("", None, False):
            return value
    return None


def normalize_weight(value, default=None, fill_defaults=False):
    if value in ("", None, False):
        if fill_defaults:
            return round(float(default or 0.0), 3)
        return None
    n = float(value)
    if n < 0:
        raise ValueError("Weights cannot be negative")
    return round(n, 3)


def normalize_limits(raw, fill_defaults=False):
    raw = raw if isinstance(raw, dict) else {}
    return {
        "score_per_5h": normalize_limit_float(raw.get("score_per_5h")),
        "score_per_week": normalize_limit_float(raw.get("score_per_week")),
        "max_tokens_per_message": normalize_limit_int(raw.get("max_tokens_per_message")),
        "max_tool_calls_per_message": normalize_limit_int(raw.get("max_tool_calls_per_message")),
        "input_token_weight": normalize_weight(raw.get("input_token_weight"), DEFAULT_USAGE_WEIGHTS["input_tokens"], fill_defaults=fill_defaults),
        "output_token_weight": normalize_weight(raw.get("output_token_weight"), DEFAULT_USAGE_WEIGHTS["output_tokens"], fill_defaults=fill_defaults),
        "tool_call_weight": normalize_weight(raw.get("tool_call_weight"), DEFAULT_USAGE_WEIGHTS["tool_calls"], fill_defaults=fill_defaults),
        "thinking_second_weight": normalize_weight(raw.get("thinking_second_weight"), DEFAULT_USAGE_WEIGHTS["thinking_seconds"], fill_defaults=fill_defaults),
    }


def default_user_usage():
    return {
        "events": [],
        "last_request_at": 0,
    }


def usage_weights_from_limits(limits):
    limits = normalize_limits(limits or {}, fill_defaults=True)
    return {
        "input_tokens": float(limits.get("input_token_weight") or DEFAULT_USAGE_WEIGHTS["input_tokens"]),
        "output_tokens": float(limits.get("output_token_weight") or DEFAULT_USAGE_WEIGHTS["output_tokens"]),
        "tool_calls": float(limits.get("tool_call_weight") or DEFAULT_USAGE_WEIGHTS["tool_calls"]),
        "thinking_seconds": float(limits.get("thinking_second_weight") or DEFAULT_USAGE_WEIGHTS["thinking_seconds"]),
    }


def usage_score(metrics, limits):
    weights = usage_weights_from_limits(limits)
    return round(
        max(0, int(metrics.get("input_tokens") or 0)) * weights["input_tokens"]
        + max(0, int(metrics.get("output_tokens") or 0)) * weights["output_tokens"]
        + max(0, int(metrics.get("tool_calls") or 0)) * weights["tool_calls"]
        + max(0.0, float(metrics.get("thinking_seconds") or 0.0)) * weights["thinking_seconds"],
        3,
    )


def normalize_usage_event(event):
    if not isinstance(event, dict):
        return None
    try:
        ts = int(event.get("ts") or 0)
    except Exception:
        ts = 0
    try:
        status = int(event.get("status") or 0)
    except Exception:
        status = 0
    input_tokens = max(0, int(first_defined(event.get("input_tokens"), event.get("prompt_tokens"), 0) or 0))
    output_tokens = max(0, int(first_defined(event.get("output_tokens"), event.get("completion_tokens"), event.get("tokens"), 0) or 0))
    tool_calls = max(0, int(event.get("tool_calls") or 0))
    thinking_seconds = round(max(0.0, float(event.get("thinking_seconds") or 0.0)), 3)
    requests = max(0, int(event.get("requests") or 0))
    if not requests and (input_tokens or output_tokens or tool_calls or thinking_seconds):
        requests = 1
    return {
        "ts": ts,
        "requests": requests,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": tool_calls,
        "thinking_seconds": thinking_seconds,
        "status": status,
    }


def prune_usage_events(events):
    keep_after = int(time.time()) - USAGE_RETENTION_SECONDS
    clean = []
    for event in events or []:
        normalized = normalize_usage_event(event)
        if normalized and int(normalized.get("ts") or 0) >= keep_after:
            clean.append(normalized)
    return clean


def usage_window_totals(events, since_ts, limits):
    totals = {
        "requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "tool_calls": 0,
        "thinking_seconds": 0.0,
        "score": 0.0,
    }
    for raw_event in events or []:
        event = normalize_usage_event(raw_event)
        if not event or int(event.get("ts") or 0) < since_ts:
            continue
        totals["requests"] += int(event.get("requests") or 0)
        totals["input_tokens"] += int(event.get("input_tokens") or 0)
        totals["output_tokens"] += int(event.get("output_tokens") or 0)
        totals["tool_calls"] += int(event.get("tool_calls") or 0)
        totals["thinking_seconds"] = round(totals["thinking_seconds"] + float(event.get("thinking_seconds") or 0.0), 3)
        totals["score"] = round(totals["score"] + usage_score(event, limits), 3)
    return totals


def normalize_group_names(value):
    items = value
    if items in ("", None, False):
        return []
    if isinstance(items, str):
        items = [x.strip() for x in items.split(",") if x.strip()]
    if not isinstance(items, list):
        raise ValueError("groups must be a list")
    names = []
    for item in items:
        name = safe_user_name(item)
        if name not in names:
            names.append(name)
    return names


def normalize_group_record(raw_name, raw):
    if not isinstance(raw, dict):
        raise ValueError("Group record must be an object")
    name = safe_user_name(raw.get("name") or raw_name)
    allowed_targets = raw.get("allowed_targets")
    if allowed_targets in (None, "", []):
        allowed_targets = ["*"]
    if isinstance(allowed_targets, str):
        allowed_targets = [x.strip() for x in allowed_targets.split(",") if x.strip()]
    if not isinstance(allowed_targets, list):
        raise ValueError("allowed_targets must be a list")
    allowed_clean = []
    for item in allowed_targets:
        item = str(item or "").strip()
        if not item:
            continue
        item_upper = item.upper()
        item_lower = item.lower()
        if item == "*" or item_lower in ("legacy", "all"):
            allowed_clean.append("*" if item == "*" or item_lower == "all" else "legacy")
            continue
        if re.fullmatch(r"GPU[0-9]+", item_upper):
            allowed_clean.append(item_upper)
            continue
        raise ValueError("Allowed targets must be *, legacy, or GPU<n>")
    if not allowed_clean:
        allowed_clean = ["*"]
    limits_raw = raw.get("limits") if isinstance(raw.get("limits"), dict) else raw
    limits = normalize_limits(limits_raw)
    return {
        "name": name,
        "enabled": bool(raw.get("enabled", True)),
        "created_at": int(raw.get("created_at") or time.time()),
        "description": str(raw.get("description") or "").strip(),
        "allowed_targets": sorted(set(allowed_clean), key=lambda x: ("*" not in x, x)),
        "limits": limits,
    }


def read_groups():
    data = read_json_file(GROUPS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    clean = {}
    for raw_name, raw_group in data.items():
        try:
            grp = normalize_group_record(raw_name, raw_group)
            clean[grp["name"]] = grp
        except Exception:
            continue
    return clean


def write_groups(data):
    normalized = {}
    for raw_name, raw_group in (data or {}).items():
        grp = normalize_group_record(raw_name, raw_group)
        normalized[grp["name"]] = grp
    write_json_file(GROUPS_FILE, normalized)
    return normalized


def public_group_view(group):
    return {
        "name": group["name"],
        "enabled": bool(group.get("enabled", True)),
        "created_at": int(group.get("created_at") or 0),
        "description": str(group.get("description") or ""),
        "allowed_targets": list(group.get("allowed_targets") or ["*"]),
        "limits": dict(group.get("limits") or {}),
        "resolved_limits": normalize_limits(group.get("limits") or {}, fill_defaults=True),
    }


def list_groups_public():
    return [public_group_view(g) for _, g in sorted(read_groups().items())]


def normalize_user_record(raw_name, raw):
    if not isinstance(raw, dict):
        raise ValueError("User record must be an object")
    name = safe_user_name(raw.get("name") or raw_name)
    allowed_targets = raw.get("allowed_targets")
    if allowed_targets in (None, "", []):
        allowed_targets = ["*"]
    if isinstance(allowed_targets, str):
        allowed_targets = [x.strip() for x in allowed_targets.split(",") if x.strip()]
    if not isinstance(allowed_targets, list):
        raise ValueError("allowed_targets must be a list")
    allowed_clean = []
    for item in allowed_targets:
        item = str(item or "").strip()
        if not item:
            continue
        item_upper = item.upper()
        item_lower = item.lower()
        if item == "*" or item_lower in ("legacy", "all"):
            allowed_clean.append("*" if item == "*" or item_lower == "all" else "legacy")
            continue
        if re.fullmatch(r"GPU[0-9]+", item_upper):
            allowed_clean.append(item_upper)
            continue
        raise ValueError("Allowed targets must be *, legacy, or GPU<n>")
    if not allowed_clean:
        allowed_clean = ["*"]
    groups = normalize_group_names(raw.get("groups"))
    limits_raw = raw.get("limits") if isinstance(raw.get("limits"), dict) else raw
    limits = normalize_limits(limits_raw)
    usage = default_user_usage()
    raw_usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    usage["last_request_at"] = int(raw_usage.get("last_request_at") or 0)
    usage["events"] = prune_usage_events(raw_usage.get("events") or [])
    api_key_hash = str(raw.get("api_key_hash") or "").strip()
    api_key_plain = str(raw.get("api_key_plain") or raw.get("api_key") or "").strip()
    if api_key_plain:
        digest = hashlib.sha256(api_key_plain.encode("utf-8")).hexdigest()
        if not api_key_hash or api_key_hash != digest:
            api_key_hash = digest
    return {
        "name": name,
        "enabled": bool(raw.get("enabled", True)),
        "created_at": int(raw.get("created_at") or time.time()),
        "allowed_targets": sorted(set(allowed_clean), key=lambda x: ("*" not in x, x)),
        "groups": groups,
        "limits": limits,
        "usage": usage,
        "api_key_hash": api_key_hash,
        "api_key_plain": api_key_plain,
    }


def read_users():
    data = read_json_file(USERS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    clean = {}
    for raw_name, raw_user in data.items():
        try:
            user = normalize_user_record(raw_name, raw_user)
            clean[user["name"]] = user
        except Exception:
            continue
    return clean


def write_users(data):
    normalized = {}
    for raw_name, raw_user in (data or {}).items():
        user = normalize_user_record(raw_name, raw_user)
        normalized[user["name"]] = user
    write_json_file(USERS_FILE, normalized)
    return normalized


def effective_group_records(user):
    groups = read_groups()
    names = user.get("groups") or []
    return [groups[name] for name in names if name in groups and groups[name].get("enabled", True)]


def effective_allowed_targets(user):
    allowed = set(user.get("allowed_targets") or ["*"])
    for group in effective_group_records(user):
        allowed.update(group.get("allowed_targets") or [])
    if not allowed:
        allowed.add("*")
    return sorted(allowed, key=lambda x: ("*" not in x, x))


def effective_limits(user):
    merged = dict(user.get("limits") or {})
    for group in effective_group_records(user):
        for key, value in (group.get("limits") or {}).items():
            if merged.get(key) is None and value is not None:
                merged[key] = value
    return normalize_limits(merged, fill_defaults=True)


def public_user_view(user):
    usage = user.get("usage") or default_user_usage()
    now = int(time.time())
    effective_targets = effective_allowed_targets(user)
    merged_limits = effective_limits(user)
    window_5h = usage_window_totals(usage.get("events") or [], now - (5 * 3600), merged_limits)
    window_week = usage_window_totals(usage.get("events") or [], now - (7 * 24 * 3600), merged_limits)
    return {
        "name": user["name"],
        "enabled": bool(user.get("enabled", True)),
        "created_at": int(user.get("created_at") or 0),
        "allowed_targets": list(user.get("allowed_targets") or ["*"]),
        "groups": list(user.get("groups") or []),
        "effective_allowed_targets": effective_targets,
        "limits": dict(user.get("limits") or {}),
        "effective_limits": merged_limits,
        "usage": {
            "last_request_at": int(usage.get("last_request_at") or 0),
            "window_5h": window_5h,
            "window_week": window_week,
        },
        "has_api_key": bool(user.get("api_key_hash")),
        "api_key_available": bool(user.get("api_key_plain")),
    }


def list_users_public():
    return [public_user_view(u) for _, u in sorted(read_users().items())]


def issue_api_key_for_user(name):
    users = read_users()
    if name not in users:
        raise ValueError("User not found")
    key = "club3090_" + secrets.token_urlsafe(24)
    users[name]["api_key_hash"] = hashlib.sha256(key.encode("utf-8")).hexdigest()
    users[name]["api_key_plain"] = key
    write_users(users)
    log_control(f"USER reset_api_key name={name}")
    log_audit("user_api_key_reset", user=name)
    return key, public_user_view(users[name])


def show_api_key_for_user(name):
    users = read_users()
    if name not in users:
        raise ValueError("User not found")
    key = str(users[name].get("api_key_plain") or "").strip()
    if not key:
        raise ValueError("This API key was created before v4.46 and cannot be recovered. Reset it once to store a viewable copy.")
    return key, public_user_view(users[name])


def save_user_record(payload):
    if not isinstance(payload, dict):
        raise ValueError("User payload must be an object")
    name = safe_user_name(payload.get("name"))
    users = read_users()
    existing = users.get(name)
    merged = {
        "name": name,
        "enabled": bool(payload.get("enabled", True if existing is None else existing.get("enabled", True))),
        "created_at": int(existing.get("created_at") if existing else time.time()),
        "allowed_targets": payload.get("allowed_targets", existing.get("allowed_targets", ["*"]) if existing else ["*"]),
        "groups": payload.get("groups", existing.get("groups", []) if existing else []),
        "limits": payload.get("limits", existing.get("limits", {}) if existing else {}),
        "usage": existing.get("usage", default_user_usage()) if existing else default_user_usage(),
        "api_key_hash": existing.get("api_key_hash", "") if existing else "",
        "api_key_plain": existing.get("api_key_plain", "") if existing else "",
    }
    users[name] = normalize_user_record(name, merged)
    write_users(users)
    log_control(f"USER saved name={name}")
    log_audit("user_saved", user=name, enabled=users[name]["enabled"], allowed_targets=users[name]["allowed_targets"], limits=users[name]["limits"])
    created_key = None
    if payload.get("generate_api_key") or not users[name].get("api_key_hash"):
        created_key, view = issue_api_key_for_user(name)
        return view, created_key
    return public_user_view(users[name]), None


def delete_user_record(name):
    name = safe_user_name(name)
    users = read_users()
    if name not in users:
        raise ValueError("User not found")
    del users[name]
    write_users(users)
    log_control(f"USER deleted name={name}")
    log_audit("user_deleted", user=name)
    return list_users_public()


def save_group_record(payload):
    if not isinstance(payload, dict):
        raise ValueError("Group payload must be an object")
    name = safe_user_name(payload.get("name"))
    groups = read_groups()
    existing = groups.get(name)
    merged = {
        "name": name,
        "enabled": bool(payload.get("enabled", True if existing is None else existing.get("enabled", True))),
        "created_at": int(existing.get("created_at") if existing else time.time()),
        "description": str(payload.get("description", existing.get("description", "") if existing else "")),
        "allowed_targets": payload.get("allowed_targets", existing.get("allowed_targets", ["*"]) if existing else ["*"]),
        "limits": payload.get("limits", existing.get("limits", {}) if existing else {}),
    }
    groups[name] = normalize_group_record(name, merged)
    write_groups(groups)
    log_control(f"GROUP saved name={name}")
    log_audit("group_saved", group=name, enabled=groups[name]["enabled"], allowed_targets=groups[name]["allowed_targets"], limits=groups[name]["limits"])
    return public_group_view(groups[name])


def delete_group_record(name):
    name = safe_user_name(name)
    groups = read_groups()
    if name not in groups:
        raise ValueError("Group not found")
    del groups[name]
    write_groups(groups)
    users = read_users()
    changed = False
    for user_name, user in users.items():
        current_groups = [g for g in (user.get("groups") or []) if g != name]
        if current_groups != (user.get("groups") or []):
            user["groups"] = current_groups
            users[user_name] = normalize_user_record(user_name, user)
            changed = True
    if changed:
        write_users(users)
    log_control(f"GROUP deleted name={name}")
    log_audit("group_deleted", group=name)
    return list_groups_public()


def extract_api_key(headers):
    auth = headers.get("Authorization", "") or headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip()
    for key in ("X-API-Key", "x-api-key", "api-key"):
        val = headers.get(key, "")
        if val:
            return str(val).strip()
    return ""


def get_user_by_api_key(raw_key):
    if not raw_key:
        return None
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    for user in read_users().values():
        if user.get("enabled", True) and user.get("api_key_hash") == digest:
            return user
    return None


def resolve_target_id(instance_id=None):
    if instance_id:
        return str(instance_id).upper()
    primary = primary_instance()
    return primary["id"] if primary else "legacy"


def target_gpu_labels(target_id):
    parsed = parse_instance_identifier(target_id)
    if not parsed:
        return []
    return [f"GPU{int(idx)}" for idx in parsed.get("gpu_indices") or []]


def user_can_access_target(user, target_id):
    allowed = set(effective_allowed_targets(user))
    if "*" in allowed or target_id in allowed:
        return True
    labels = target_gpu_labels(target_id)
    return bool(labels) and all(label in allowed for label in labels)


def is_quota_counted_path(upstream_path):
    return upstream_path.startswith("/v1/chat/completions") or upstream_path.startswith("/v1/completions")


def estimate_text_tokens(text):
    text = str(text or "")
    return max(0, int(len(text) / 4)) if text else 0


def collect_request_text_fragments(value, out):
    if value in ("", None, False):
        return
    if isinstance(value, str):
        out.append(value)
        return
    if isinstance(value, list):
        for item in value:
            collect_request_text_fragments(item, out)
        return
    if isinstance(value, dict):
        for key in ("text", "content", "prompt", "input", "instructions", "system", "developer", "user", "assistant"):
            if key in value:
                collect_request_text_fragments(value.get(key), out)


def extract_request_usage(body):
    usage = {
        "input_tokens": 0,
        "requested_output_tokens": 0,
        "estimated_total_tokens": 0,
        "requested_tool_calls": None,
    }
    if not body:
        return usage
    text = body.decode("utf-8", errors="ignore") if isinstance(body, (bytes, bytearray)) else str(body)
    usage["input_tokens"] = estimate_text_tokens(text)
    try:
        obj = json.loads(text)
    except Exception:
        usage["estimated_total_tokens"] = usage["input_tokens"]
        return usage
    if isinstance(obj, dict):
        fragments = []
        for key in ("messages", "prompt", "input", "instructions"):
            if key in obj:
                collect_request_text_fragments(obj.get(key), fragments)
        if fragments:
            usage["input_tokens"] = max(usage["input_tokens"], estimate_text_tokens(" ".join(fragments)))
        try:
            usage["requested_output_tokens"] = max(0, int(first_defined(obj.get("max_completion_tokens"), obj.get("max_tokens")) or 0))
        except Exception:
            usage["requested_output_tokens"] = 0
        try:
            requested_tools = first_defined(obj.get("max_tool_calls"), obj.get("max_parallel_tool_calls"))
            if requested_tools not in ("", None, False):
                usage["requested_tool_calls"] = max(0, int(requested_tools))
            elif isinstance(obj.get("tool_choice"), dict):
                usage["requested_tool_calls"] = 1
            elif str(obj.get("tool_choice") or "").strip().lower() == "required":
                usage["requested_tool_calls"] = 1
        except Exception:
            usage["requested_tool_calls"] = None
    usage["estimated_total_tokens"] = usage["input_tokens"] + usage["requested_output_tokens"]
    return usage


def user_limit_error(user, count_request, request_usage=None):
    if not count_request:
        return None
    usage = user.get("usage") or default_user_usage()
    limits = effective_limits(user)
    request_usage = request_usage or {}
    estimated_total_tokens = max(0, int(request_usage.get("estimated_total_tokens") or 0))
    max_tokens_per_message = limits.get("max_tokens_per_message")
    if max_tokens_per_message is not None and estimated_total_tokens > int(max_tokens_per_message):
        return "per-message token limit reached"
    requested_tool_calls = request_usage.get("requested_tool_calls")
    max_tool_calls_per_message = limits.get("max_tool_calls_per_message")
    if max_tool_calls_per_message is not None and requested_tool_calls is not None and int(requested_tool_calls) > int(max_tool_calls_per_message):
        return "per-message tool-call limit reached"
    now = int(time.time())
    events = usage.get("events") or []
    window_5h = usage_window_totals(events, now - (5 * 3600), limits)
    window_week = usage_window_totals(events, now - (7 * 24 * 3600), limits)
    estimated_score = usage_score({
        "input_tokens": max(0, int(request_usage.get("input_tokens") or 0)),
        "output_tokens": max(0, int(request_usage.get("requested_output_tokens") or 0)),
        "tool_calls": max(0, int(requested_tool_calls or 0)),
        "thinking_seconds": 0.0,
    }, limits)
    if limits.get("score_per_5h") is not None and round(window_5h["score"] + estimated_score, 3) > float(limits["score_per_5h"]):
        return "5-hour usage score limit reached"
    if limits.get("score_per_week") is not None and round(window_week["score"] + estimated_score, 3) > float(limits["score_per_week"]):
        return "weekly usage score limit reached"
    return None


def authorize_proxy_request(headers, instance_id, upstream_path, request_usage=None):
    cfg = read_server_config()
    target_id = resolve_target_id(instance_id)
    count_request = is_quota_counted_path(upstream_path)
    raw_key = extract_api_key(headers)
    user = get_user_by_api_key(raw_key) if raw_key else None
    if user is not None:
        if not user_can_access_target(user, target_id):
            log_audit("proxy_access_denied", reason="target_not_allowed", user=user["name"], target=target_id, path=upstream_path)
            return False, 403, {"error": "API key is not allowed to access this backend", "target": target_id}
        err = user_limit_error(user, count_request=count_request, request_usage=request_usage)
        if err:
            log_audit("proxy_quota_denied", user=user["name"], target=target_id, path=upstream_path, reason=err)
            return False, 429, {"error": err, "user": user["name"]}
        return True, {"mode": "user", "user_name": user["name"], "target_id": target_id, "count_request": count_request}
    if cfg.get("allow_proxy_without_api_key", True):
        return True, {"mode": "anonymous", "user_name": None, "target_id": target_id, "count_request": False}
    log_audit("proxy_auth_denied", reason="missing_or_invalid_api_key", target=target_id, path=upstream_path)
    return False, 401, {"error": "Missing or invalid API key"}


def extract_response_usage(payload):
    usage = {"tokens": 0, "input_tokens": 0, "output_tokens": 0, "tool_calls": 0}
    try:
        obj = json.loads(payload.decode("utf-8", errors="ignore"))
    except Exception:
        return usage
    if isinstance(obj, dict):
        if isinstance(obj.get("usage"), dict):
            try:
                usage_block = obj["usage"]
                usage["input_tokens"] = max(0, int(first_defined(usage_block.get("prompt_tokens"), usage_block.get("input_tokens")) or 0))
                usage["output_tokens"] = max(0, int(first_defined(usage_block.get("completion_tokens"), usage_block.get("output_tokens")) or 0))
                usage["tokens"] = max(0, int(usage_block.get("total_tokens") or (usage["input_tokens"] + usage["output_tokens"])))
                if usage["output_tokens"] == 0 and usage["tokens"] and usage["input_tokens"] == 0:
                    usage["output_tokens"] = usage["tokens"]
            except Exception:
                usage["tokens"] = 0
        tool_calls = 0
        for choice in obj.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            msg = choice.get("message") if isinstance(choice.get("message"), dict) else {}
            tool_calls += len(msg.get("tool_calls") or [])
        usage["tool_calls"] = tool_calls
    return usage


def record_user_usage(user_name, count_request, status_code, request_usage, response_usage, thinking_seconds):
    if not user_name or not count_request:
        return
    users = read_users()
    user = users.get(user_name)
    if not user:
        return
    usage = user.get("usage") or default_user_usage()
    limits = effective_limits(user)
    now = int(time.time())
    request_usage = request_usage or {}
    response_usage = response_usage or {}
    input_tokens = max(0, int(first_defined(response_usage.get("input_tokens"), request_usage.get("input_tokens"), 0) or 0))
    output_tokens = max(0, int(first_defined(response_usage.get("output_tokens"), response_usage.get("tokens"), 0) or 0))
    tool_calls = max(0, int(response_usage.get("tool_calls") or 0))
    thinking_seconds = round(max(0.0, float(thinking_seconds or 0.0)), 3)
    score = usage_score({
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": tool_calls,
        "thinking_seconds": thinking_seconds,
    }, limits)
    usage["last_request_at"] = now
    usage.setdefault("events", [])
    usage["events"].append({
        "ts": now,
        "requests": 1,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": tool_calls,
        "thinking_seconds": thinking_seconds,
        "status": int(status_code or 0),
        "score": score,
    })
    usage["events"] = prune_usage_events(usage.get("events") or [])
    user["usage"] = usage
    users[user_name] = normalize_user_record(user_name, user)
    write_users(users)
    combined_tokens = input_tokens + output_tokens
    overages = []
    if limits.get("max_tokens_per_message") is not None and combined_tokens > int(limits["max_tokens_per_message"]):
        overages.append("message_tokens")
    if limits.get("max_tool_calls_per_message") is not None and tool_calls > int(limits["max_tool_calls_per_message"]):
        overages.append("message_tool_calls")
    window_5h = usage_window_totals(user["usage"].get("events") or [], now - (5 * 3600), limits)
    window_week = usage_window_totals(user["usage"].get("events") or [], now - (7 * 24 * 3600), limits)
    if limits.get("score_per_5h") is not None and window_5h["score"] > float(limits["score_per_5h"]):
        overages.append("score_5h")
    if limits.get("score_per_week") is not None and window_week["score"] > float(limits["score_per_week"]):
        overages.append("score_week")
    log_audit("proxy_usage", user=user_name, status=int(status_code or 0), input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=combined_tokens, tool_calls=tool_calls, thinking_seconds=thinking_seconds, score=score)
    if overages:
        log_audit("proxy_usage_overage", user=user_name, status=int(status_code or 0), kinds=overages, total_tokens=combined_tokens, tool_calls=tool_calls, thinking_seconds=thinking_seconds, score=score)


def local_api_token_ok(header_value):
    token = ensure_local_api_token()
    supplied = str(header_value or "").strip()
    return bool(token) and bool(supplied) and secrets.compare_digest(token, supplied)


def _safe_preset_name(name):
    name = str(name or "").strip()
    if not name:
        raise ValueError("Preset endpoint name is required")
    if len(name) > 48:
        raise ValueError("Preset endpoint name is too long")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if any(ch not in allowed for ch in name):
        raise ValueError("Preset endpoint names may only contain letters, numbers, underscore, and hyphen")
    if name.startswith("short-") or name.startswith("concise-"):
        raise ValueError("Preset endpoint names cannot start with short- or concise-")
    if name in PRESETS:
        raise ValueError("Default presets cannot be overwritten")
    return name

def _coerce_preset_value(key, value):
    if value is None or value == "":
        return None
    if key in ("top_k", "max_tokens", "max_completion_tokens", "truncate_prompt_tokens", "seed", "min_tokens", "logprobs", "top_logprobs"):
        return int(value)
    if key in ("temperature", "top_p", "min_p", "presence_penalty", "frequency_penalty", "repetition_penalty", "length_penalty"):
        return float(value)
    return value

def sanitize_custom_preset(raw):
    if not isinstance(raw, dict):
        raise ValueError("Preset body must be an object")
    payload = {}
    numeric_keys = ("temperature", "top_p", "top_k", "min_p", "presence_penalty", "frequency_penalty", "repetition_penalty", "length_penalty", "max_tokens", "max_completion_tokens", "min_tokens", "truncate_prompt_tokens", "seed", "logprobs", "top_logprobs")
    for key in numeric_keys:
        if key in raw:
            val = _coerce_preset_value(key, raw.get(key))
            if val is not None:
                payload[key] = val
    boolean_keys = ("ignore_eos", "skip_special_tokens", "spaces_between_special_tokens", "include_stop_str_in_output")
    for key in boolean_keys:
        if key in raw:
            payload[key] = bool(raw.get(key))
    if "stop" in raw:
        stop_val = raw.get("stop")
        if isinstance(stop_val, str):
            stops = [x.strip() for x in stop_val.replace("\r", "").split("\n") if x.strip()]
            if len(stops) == 1 and "," in stops[0]:
                stops = [x.strip() for x in stops[0].split(",") if x.strip()]
            if stops:
                payload["stop"] = stops if len(stops) > 1 else stops[0]
        elif isinstance(stop_val, list):
            stops = [str(x) for x in stop_val if str(x)]
            if stops:
                payload["stop"] = stops
    ctk = {}
    if "enable_thinking" in raw:
        ctk["enable_thinking"] = bool(raw.get("enable_thinking"))
    if "preserve_thinking" in raw:
        ctk["preserve_thinking"] = bool(raw.get("preserve_thinking"))
        if ctk["preserve_thinking"]:
            ctk["enable_thinking"] = True
    if ctk:
        payload["chat_template_kwargs"] = ctk
    desc = str(raw.get("description") or "").strip()
    system_prompt = str(raw.get("system_prompt") or "").strip()
    return {"params": payload, "description": desc, "system_prompt": system_prompt}

def read_custom_presets():
    try:
        with open(CUSTOM_PRESETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        clean = {}
        for name, preset in data.items():
            try:
                clean_name = _safe_preset_name(name)
            except Exception:
                continue
            if isinstance(preset, dict) and "params" in preset:
                params = preset.get("params") if isinstance(preset.get("params"), dict) else {}
                desc = str(preset.get("description") or "")
                system_prompt = str(preset.get("system_prompt") or "")
            elif isinstance(preset, dict):
                params = preset
                desc = ""
                system_prompt = ""
            else:
                continue
            clean[clean_name] = {"params": params, "description": desc, "system_prompt": system_prompt}
        return clean
    except Exception:
        return {}

def write_custom_presets(data):
    write_json_atomic_if_changed(CUSTOM_PRESETS_FILE, data, indent=2, sort_keys=True)
    return data

def get_all_presets():
    all_presets = {k: dict(v) for k, v in PRESETS.items()}
    for name, item in read_custom_presets().items():
        params = item.get("params") if isinstance(item, dict) else None
        if isinstance(params, dict):
            all_presets[name] = params
    return all_presets

def preset_system_prompt(name):
    key = str(name or "").strip()
    if not key:
        return ""
    if key in PRESETS:
        return ""
    item = read_custom_presets().get(key) or {}
    return str(item.get("system_prompt") or "")

def preset_catalog():
    defaults = []
    for name in PRESETS:
        defaults.append({"name": name, "endpoint": f"/v1/{name}", "endpoint_alt": f"/{name}", "locked": True, "params": PRESETS[name], "description": DEFAULT_PRESET_DESCRIPTIONS.get(name, "Default preset"), "system_prompt": ""})
    customs = []
    for name, item in sorted(read_custom_presets().items()):
        customs.append({"name": name, "endpoint": f"/v1/{name}", "endpoint_alt": f"/{name}", "locked": False, "params": item.get("params", {}), "description": item.get("description", ""), "system_prompt": item.get("system_prompt", "")})
    return {"defaults": defaults, "custom": customs, "length_prefixes": LENGTH_PREFIXES}

def save_custom_preset(name, preset_data):
    name = _safe_preset_name(name)
    custom = read_custom_presets()
    custom[name] = sanitize_custom_preset(preset_data)
    write_custom_presets(custom)
    log_control(f"PRESET saved name={name}")
    return preset_catalog()

def delete_custom_preset(name):
    name = _safe_preset_name(name)
    custom = read_custom_presets()
    if name not in custom:
        raise ValueError("Custom preset not found")
    del custom[name]
    write_custom_presets(custom)
    log_control(f"PRESET deleted name={name}")
    return preset_catalog()

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
    return count != 2

def gpu_pairing_enabled(cfg=None, gpu_count=None):
    config = cfg if isinstance(cfg, dict) else read_server_config()
    try:
        count = int(gpu_count if gpu_count is not None else detect_gpu_count_runtime())
    except Exception:
        count = 0
    if isinstance(config, dict) and "gpu_pairing_enabled" in config:
        return bool(config.get("gpu_pairing_enabled"))
    return gpu_pairing_default_enabled(count)

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
    if count == 2 and gpu_pairing_enabled(gpu_count=count):
        rows.append({
            "id": "PAIR0_1",
            "kind": "dual",
            "gpu_indices": [0, 1],
            "mode": dual_mode,
            "enabled": dual_mode in DUAL_GPU_MODES,
            "port": PAIR_INSTANCE_PORT_BASE,
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
    return {
        "id": instance_id,
        "kind": kind,
        "gpu_indices": gpu_indices,
        "gpu_index": gpu_index,
        "mode": mode,
        "enabled": bool(raw.get("enabled", False)),
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
    if count == 2 and gpu_pairing_enabled(gpu_count=count) and "PAIR0_1" not in existing_ids:
        default_dual_mode = default_dual_mode_selector()
        inst = normalize_instance({"id": "PAIR0_1", "kind": "dual", "gpu_indices": [0, 1], "mode": default_dual_mode, "enabled": default_dual_mode in DUAL_GPU_MODES, "port": PAIR_INSTANCE_PORT_BASE}, used_ids, used_ports, substitutions=substitutions)
        if inst is not None:
            clean.append(inst)
    if not clean:
        clean = default_instances_config()
    clean.sort(key=lambda d: (d.get("gpu_index", 9999), d.get("id", "")))
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
    count = detect_gpu_count_runtime()
    changed = bool(substitutions)
    if count == 2 and not gpu_pairing_enabled(gpu_count=count):
        filtered = [row for row in rows if row.get("kind") != "dual"]
        changed = len(filtered) != len(rows)
        rows = filtered
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

def write_instance_artifacts(instance):
    spec = instance_variant_spec(instance)
    paths = instance_paths(instance)
    os.makedirs(paths["dir"], exist_ok=True)
    os.makedirs(os.path.join(paths["dir"], "cache"), exist_ok=True)
    visible_devices = ",".join(str(int(idx)) for idx in (instance.get("gpu_indices") or [instance["gpu_index"]]))
    cache_root = os.path.join(paths["dir"], "cache")
    repo_env = _load_repo_env_map()
    with open(paths["env"], "w", encoding="utf-8") as f:
        for key in sorted(repo_env):
            if key in {"PORT", "CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "MODEL_DIR", "CLUB3090_GPU"}:
                continue
            value = str(repo_env.get(key) or "").replace("\r", " ").replace("\n", " ")
            f.write(f"{key}={value}\n")
        f.write(f"MODEL_DIR={_resolve_variant_model_dir_root(spec)}\n")
        f.write(f"PORT={int(instance['port'])}\n")
        f.write(f"CUDA_VISIBLE_DEVICES={visible_devices}\n")
        f.write(f"NVIDIA_VISIBLE_DEVICES={visible_devices}\n")
    override = (
        "services:\n"
        f"  {spec['service_name']}:\n"
        f"    container_name: {instance_container_name(instance)}\n"
        "    environment:\n"
        f"      CUDA_VISIBLE_DEVICES: \"{visible_devices}\"\n"
        f"      NVIDIA_VISIBLE_DEVICES: \"{visible_devices}\"\n"
        "      VLLM_CACHE_ROOT: /root/.cache/club3090-instance/vllm\n"
        "      TORCHINDUCTOR_CACHE_DIR: /root/.cache/club3090-instance/torchinductor\n"
        "      TRITON_CACHE_DIR: /root/.cache/club3090-instance/triton\n"
        "    volumes:\n"
        f"      - {cache_root}:/root/.cache/club3090-instance\n"
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

def instance_compose_args(instance):
    spec = instance_variant_spec(instance)
    paths = write_instance_artifacts(instance)
    compose_file = str(spec.get("compose_abs_path") or "").strip()
    compose_project_dir = str(spec.get("compose_project_dir_abs_path") or "").strip() or os.path.dirname(compose_file)
    if not os.path.exists(compose_file):
        raise RuntimeError(f"Compose file missing for {instance['mode']}: {compose_file}")
    return compose_cmd() + ["--project-directory", compose_project_dir, "-p", instance_project_name(instance), "--env-file", paths["env"], "-f", compose_file, "-f", paths["override"]]


def instance_compose_project_dir(instance):
    spec = instance_variant_spec(instance)
    compose_file = str(spec.get("compose_abs_path") or "").strip()
    return str(spec.get("compose_project_dir_abs_path") or "").strip() or os.path.dirname(compose_file) or CLUB3090_DIR


def instance_subprocess_env(instance):
    spec = instance_variant_spec(instance)
    env = _repo_subprocess_env()
    visible_devices = ",".join(str(int(idx)) for idx in (instance.get("gpu_indices") or [instance["gpu_index"]]))
    env.pop("CLUB3090_GPU", None)
    env["MODEL_DIR"] = _resolve_variant_model_dir_root(spec)
    env["PORT"] = str(int(instance["port"]))
    env["CUDA_VISIBLE_DEVICES"] = visible_devices
    env["NVIDIA_VISIBLE_DEVICES"] = visible_devices
    env["COMPOSE_BIN"] = COMPOSE_BIN
    return _apply_variant_hardware_guard(spec, env)

def start_instance(instance_id, track_switch_job=True):
    instance = get_instance(instance_id)
    if not instance:
        raise ValueError(f"Unknown instance: {instance_id}")
    try:
        spec = instance_variant_spec(instance)
        ensure_variant_install_ready(spec)
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
        cmd = instance_compose_args(instance) + ["up", "-d"]
        rc, out = run_cmd(cmd, timeout=1800, cwd=instance_compose_project_dir(instance), env=instance_subprocess_env(instance))
        log_control(f"INSTANCE start {instance['id']} mode={instance['mode']} rc={rc}: {out[-4000:]}")
        if rc != 0:
            raise RuntimeError(out or f"docker compose up failed for {instance['id']}")
        wait_for_runtime_ready(
            instance_container_name(instance),
            instance_ready_url(instance),
            timeout=900,
        )
        clear_switch_failure(instance["mode"])
        if track_switch_job:
            _set_switch_job(
                active=False,
                status="success",
                mode=str(instance.get("mode") or ""),
                target=str(instance.get("id") or ""),
                finished_at=int(time.time()),
                error="",
            )
        return {"instance": instance, "output": out[-4000:]}
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
    rc, out = run_cmd(cmd, timeout=600, cwd=instance_compose_project_dir(instance), env=instance_subprocess_env(instance))
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
        gpu_count = detect_gpu_count_runtime()
        if gpu_count == 2 and not gpu_pairing_enabled(gpu_count=gpu_count):
            return [{"id": "GLOBAL", "kind": "dual", "mode": selector}]
        return [dict(row) for row in rows if row.get("kind") == "dual" and canonical_mode_selector(row.get("mode")) == selector]
    if scope_kind in {"multi", "global_only"}:
        return [{"id": "GLOBAL", "kind": "global", "mode": selector}]
    return []


def stop_runtime_scope(instance_id=None, mode=None):
    selector = canonical_mode_selector(mode) if mode else ""
    target_id = str(instance_id or "").strip().upper()
    if is_legacy_global_instance_id(target_id):
        return stop_legacy_global_instance()
    if target_id and target_id != "GLOBAL":
        return stop_instance(target_id)
    matching = []
    if selector:
        matching = [
            dict(row)
            for row in running_runtime_rows(instances_snapshot(), legacy_global_instance_snapshot())
            if canonical_mode_selector(row.get("mode")) == selector
        ]
    elif target_id == "GLOBAL":
        matching = [dict(row) for row in running_runtime_rows(instances_snapshot(), legacy_global_instance_snapshot())]
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
        if is_legacy_global_instance_id(row_id):
            item_rc, item_out = stop_legacy_global_instance()
        elif row_id == "GLOBAL":
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
    if not gpu_pairing_enabled(gpu_count=detect_gpu_count_runtime()):
        raise ValueError("Enable GPU pairing before creating pair groups")
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
    write_instances_config(rows)
    return get_instance(pair_id)

def delete_pair_instance(instance_id):
    parsed = parse_instance_identifier(instance_id)
    if not parsed or parsed.get("kind") != "dual":
        raise ValueError("Only dual GPU pair groups can be removed")
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


def detect_legacy_dual_mode():
    load_runtime_inventory()
    if detect_gpu_count_runtime() != 2:
        return None
    file_mode = None
    try:
        file_mode = canonical_mode_selector(open(ACTIVE_MODE_FILE, "r", encoding="utf-8").read().strip())
    except Exception:
        file_mode = None
    if file_mode in DUAL_GPU_MODES and port_open(mode_default_port(file_mode, PAIR_INSTANCE_PORT_BASE), timeout=0.08):
        return file_mode
    open_dual = [mode for mode in dict.fromkeys(DUAL_GPU_MODES) if port_open(mode_default_port(mode, PAIR_INSTANCE_PORT_BASE), timeout=0.08)]
    if len(open_dual) == 1:
        return open_dual[0]
    return None

def instance_uses_legacy_dual_runtime(instance):
    return bool(
        instance
        and instance.get("kind") == "dual"
        and instance.get("id") == "PAIR0_1"
        and detect_gpu_count_runtime() == 2
        and not gpu_pairing_enabled(gpu_count=2)
    )

def visible_instances(rows=None):
    items = list(rows if isinstance(rows, list) else read_instances_config())
    if gpu_pairing_enabled(gpu_count=detect_gpu_count_runtime()):
        return items
    return [inst for inst in items if inst.get("kind") != "dual"]

def instance_runtime_mode(instance):
    mode = str((instance or {}).get("mode") or "")
    if instance_uses_legacy_dual_runtime(instance):
        legacy_mode = detect_legacy_dual_mode()
        if legacy_mode in DUAL_GPU_MODES:
            return legacy_mode
    return mode

def instance_runtime_port(instance):
    if instance_uses_legacy_dual_runtime(instance):
        mode = instance_runtime_mode(instance)
        return int(mode_default_port(mode, (instance or {}).get("port") or PAIR_INSTANCE_PORT_BASE))
    return int((instance or {}).get("port") or 0)

def instance_running(instance):
    return port_open(instance_runtime_port(instance), timeout=0.08)

def legacy_runtime_container_name():
    names = vllm_container_names(all_containers=False)
    if not names:
        return ""
    active_spec = resolve_variant_spec(active_mode())
    active_name = str((active_spec or {}).get("container_name") or "")
    if active_name and active_name in names:
        return active_name
    preferred = [name for name in names if "pair0_1" not in name.lower()]
    return preferred[0] if preferred else names[0]

def instance_runtime_container_name(instance):
    if instance_uses_legacy_dual_runtime(instance):
        return legacy_runtime_container_name()
    return instance_container_name(instance)

def legacy_global_target_mode():
    legacy_mode = detect_legacy_dual_mode()
    if legacy_mode in DUAL_GPU_MODES:
        return legacy_mode
    for candidate in (
        read_active_mode_file(),
        read_last_good_mode_file(),
        DEFAULT_MODE,
        default_dual_mode_selector(),
    ):
        if candidate in DUAL_GPU_MODES:
            return canonical_mode_selector(candidate)
    return default_dual_mode_selector()

def legacy_global_disable_mode():
    for row in read_instances_config():
        if row.get("kind") != "single":
            continue
        mode = str(row.get("mode") or "")
        if row.get("enabled") and mode in SINGLE_GPU_MODES:
            return mode
    return default_single_mode_selector()

def legacy_global_enabled():
    file_mode = read_active_mode_file()
    legacy_mode = detect_legacy_dual_mode()
    if file_mode:
        return file_mode in DUAL_GPU_MODES
    return legacy_mode in DUAL_GPU_MODES

def is_legacy_global_instance_id(instance_id):
    return (
        detect_gpu_count_runtime() == 2
        and not gpu_pairing_enabled(gpu_count=2)
        and str(instance_id or "").strip().upper() == "GLOBAL"
    )

def start_legacy_global_instance():
    mode = legacy_global_target_mode()
    output = run_switch(mode)
    return {"instance": legacy_global_instance_snapshot(), "output": output[-4000:]}

def stop_legacy_global_instance():
    out = cleanup_vllm_containers()
    log_control(f"INSTANCE legacy global stop rc=0: {out}")
    return 0, str(out or "")[-4000:]

def set_legacy_global_enabled(enabled):
    if bool(enabled):
        write_active_mode(legacy_global_target_mode())
    else:
        write_active_mode(legacy_global_disable_mode())
    return legacy_global_instance_snapshot()

def primary_instance():
    rows = visible_instances(read_instances_config())
    if not rows:
        return None
    if detect_gpu_count_runtime() == 2 and not gpu_pairing_enabled(gpu_count=2) and detect_legacy_dual_mode():
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
    if detect_gpu_count_runtime() == 2 and not gpu_pairing_enabled(gpu_count=2):
        if file_mode in DUAL_GPU_MODES:
            try:
                result = start_legacy_global_instance()
                outputs.append(f"legacy dual started from active mode {file_mode}: {(result.get('output') or '')[-800:]}")
                log_control("BOOT instances: " + " || ".join(outputs))
                return outputs
            except Exception as e:
                outputs.append(f"legacy dual fallback failed: {e}")
    for inst in rows:
        if not inst.get("enabled"):
            continue
        try:
            result = start_instance(inst["id"])
            outputs.append(f"{inst['id']} started: {(result.get('output') or '')[-800:]}")
        except Exception as e:
            outputs.append(f"{inst['id']} failed: {e}")
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
    legacy = legacy_global_instance_snapshot()
    if legacy and legacy.get("running"):
        rows.append(dict(legacy))
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
    legacy = legacy_global_instance_snapshot()
    if legacy and legacy.get("running") and legacy.get("id") not in excluded:
        legacy_indices = {int(idx) for idx in (legacy.get("gpu_indices") or [])}
        if wanted.intersection(legacy_indices):
            rc, out = stop_legacy_global_instance()
            results.append({"id": legacy["id"], "rc": rc, "output": out[-1200:]})
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

def stop_instances_for_gpu_indices(indices):
    return stop_overlapping_instances(indices)

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
    for pair in running_dual_instances():
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

def instance_snapshot(instance):
    container = instance_runtime_container_name(instance)
    runtime_mode = instance_runtime_mode(instance)
    runtime_port = instance_runtime_port(instance)
    ready_url = f"http://127.0.0.1:{runtime_port}/v1/models"
    boot_state = runtime_boot_state(container, ready_url)
    assigned = instance_assignment(instance)
    return {
        "id": instance["id"],
        "kind": instance.get("kind", "single"),
        "gpu_index": instance["gpu_index"],
        "gpu_indices": list(instance.get("gpu_indices") or [instance["gpu_index"]]),
        "mode": runtime_mode,
        "enabled": bool(instance.get("enabled")),
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
    return [instance_snapshot(inst) for inst in visible_instances(read_instances_config())]

def legacy_global_instance_snapshot():
    if detect_gpu_count_runtime() != 2 or gpu_pairing_enabled(gpu_count=2):
        return None
    mode = legacy_global_target_mode()
    running_mode = detect_legacy_dual_mode()
    runtime_mode = running_mode if running_mode in DUAL_GPU_MODES else mode
    runtime_port = int(mode_default_port(runtime_mode, PAIR_INSTANCE_PORT_BASE))
    ready_url = f"http://127.0.0.1:{runtime_port}/v1/models"
    container_name = legacy_runtime_container_name()
    boot_state = runtime_boot_state(container_name, ready_url)
    return {
        "id": "GLOBAL",
        "kind": "dual",
        "gpu_index": 0,
        "gpu_indices": [0, 1],
        "mode": runtime_mode,
        "enabled": legacy_global_enabled(),
        "port": runtime_port,
        "container": container_name if boot_state.get("exists") or boot_state.get("running") or boot_state.get("booting") else "",
        "running": bool(boot_state.get("running")),
        "booting": bool(boot_state.get("booting")),
        "container_state": boot_state.get("status") or "",
        "ready_url": ready_url,
        "proxy_prefix": "/v1",
        "display_name": "Global Dual",
        "assignment_scope": "global",
        "assignment_mode": runtime_mode,
        "assignment_text": f"Global dual runtime uses GPUs 0, 1 with preset {runtime_mode}",
        "overrides_dual_mode": False,
    }

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


def runtime_boot_state(container_name="", ready_url=""):
    name = str(container_name or "").strip()
    target_url = str(ready_url or "").strip()
    state = _docker_inspect_state(name) if name else {"exists": False, "running": False, "exit_code": None, "status": ""}
    ready = False
    try:
        if name:
            ready = bool(state.get("running")) and (
                _container_bootstrap_complete(name)
                or _runtime_models_available_once(name, target_url, min_interval=15)
            )
    except Exception:
        ready = False
    booting = bool(name and state.get("running") and not ready)
    return {
        "exists": bool(state.get("exists")),
        "running": bool(ready),
        "booting": booting,
        "status": str(state.get("status") or ""),
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

def current_container():
    primary = primary_instance()
    if primary and instance_running(primary):
        return instance_runtime_container_name(primary)
    if detect_gpu_count_runtime() == 2 and not gpu_pairing_enabled(gpu_count=2) and detect_legacy_dual_mode():
        legacy_name = legacy_runtime_container_name()
        if legacy_name:
            return legacy_name
    names = vllm_container_names(all_containers=False)
    active_spec = resolve_variant_spec(active_mode())
    active_name = str((active_spec or {}).get("container_name") or "")
    if active_name and active_name in names:
        return active_name
    return names[0] if names else ""


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


def running_runtime_rows(instances=None, legacy_instance=None):
    rows = []
    if legacy_instance and (legacy_instance.get("running") or legacy_instance.get("booting")):
        rows.append(dict(legacy_instance))
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

def parse_admin_query_params(parsed):
    if not parsed or not parsed.query:
        return {}
    try:
        return {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
    except Exception:
        return {}

def parse_tail_lines_param(params, default=250):
    raw = params.get("tail") if isinstance(params, dict) else None
    try:
        return max(0, min(1000, int(raw)))
    except Exception:
        return int(default)

def resolve_runtime_log_container(requested_instance_id=""):
    requested = str(requested_instance_id or "").strip().upper()
    if is_legacy_global_instance_id(requested):
        return None, current_container()
    instance = get_instance(requested) if requested else primary_instance()
    container = instance_runtime_container_name(instance) if instance else current_container()
    return instance, container


def resolve_log_source(source="docker", instance_id="", service_id=""):
    source_name = str(source or "docker").strip().lower()
    if source_name == "audit":
        return {"source": "audit", "instance": None, "container": "", "service": {}, "label": "Audit"}
    if source_name == "service":
        service = resolve_upstream_service(service_id, force=True)
        container = str((service or {}).get("container_name") or "").strip()
        return {
            "source": "service",
            "instance": None,
            "container": container,
            "service": service,
            "label": str((service or {}).get("display_name") or service_id or "Service"),
        }
    instance, container = resolve_runtime_log_container(instance_id)
    label = str((instance or {}).get("id") or (str(instance_id or "").strip().upper() or "Docker"))
    return {"source": "docker", "instance": instance, "container": container, "service": {}, "label": label}


def split_timestamped_docker_log_line(raw):
    text = str(raw or "").rstrip("\n")
    head, sep, tail = text.partition(" ")
    if sep and re.match(r"^\d{4}-\d{2}-\d{2}T", head):
        return head, tail
    return "", text


class RuntimeLogWatcher:
    def __init__(self, container_name):
        self.container_name = str(container_name or "").strip()
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.generation = 0
        self.seq = 0
        self.status_message = ""
        self.bootstrap_lines = []
        self.bootstrap_done = False
        self.tail_lines = collections.deque()
        self.tail_bytes = 0
        self.events = collections.deque(maxlen=4096)
        self.last_timestamp = ""
        self.last_line = ""
        self.thread = threading.Thread(target=self._run, name=f"club3090-log-{self.container_name}", daemon=True)
        self.thread.start()

    def _reset_locked(self, status=""):
        self.generation += 1
        self.seq = 0
        self.status_message = str(status or "")
        self.bootstrap_lines = []
        self.bootstrap_done = False
        self.tail_lines = collections.deque()
        self.tail_bytes = 0
        self.events = collections.deque(maxlen=4096)
        self.last_timestamp = ""
        self.last_line = ""
        self.cond.notify_all()

    def _set_status(self, status):
        with self.cond:
            self.status_message = str(status or "")
            self.cond.notify_all()

    def _snapshot_text_locked(self):
        if self.bootstrap_lines or self.tail_lines:
            text = "\n".join(self.bootstrap_lines + list(self.tail_lines))
            if text and not text.endswith("\n"):
                text += "\n"
            return text
        return ((self.status_message or "waiting for logs...").rstrip("\n") + "\n")

    def snapshot(self):
        with self.cond:
            return {"generation": self.generation, "seq": self.seq, "text": self._snapshot_text_locked()}

    def wait_for_change(self, generation, seq, timeout=15):
        deadline = time.time() + max(1.0, float(timeout or 15))
        with self.cond:
            while self.generation == generation and self.seq == seq:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return False
                self.cond.wait(remaining)
            return True

    def collect_updates_since(self, generation, seq):
        with self.cond:
            if self.generation != generation:
                return {"reset": True, "generation": self.generation, "seq": self.seq, "text": self._snapshot_text_locked()}
            if seq >= self.seq:
                return {"reset": False, "generation": self.generation, "seq": self.seq, "text": ""}
            if self.events:
                first_seq = self.events[0][0]
                if seq < first_seq - 1:
                    return {"reset": True, "generation": self.generation, "seq": self.seq, "text": self._snapshot_text_locked()}
            text = "".join(chunk for event_seq, chunk in self.events if event_seq > seq)
            return {"reset": False, "generation": self.generation, "seq": self.seq, "text": text}

    def _append_line(self, line, timestamp=""):
        clean = str(line or "").rstrip("\n")
        if not clean or "GET /health HTTP/1.1" in clean:
            return
        encoded_len = len((clean + "\n").encode("utf-8", errors="replace"))
        with self.cond:
            if timestamp and timestamp == self.last_timestamp and clean == self.last_line:
                return
            self.last_timestamp = timestamp or self.last_timestamp
            self.last_line = clean
            if not self.bootstrap_done:
                self.bootstrap_lines.append(clean)
                if LOG_BOOTSTRAP_MARKER in clean:
                    self.bootstrap_done = True
            else:
                self.tail_lines.append(clean)
                self.tail_bytes += encoded_len
                while self.tail_lines and self.tail_bytes > LOG_TAIL_MAX_BYTES:
                    dropped = self.tail_lines.popleft()
                    self.tail_bytes -= len((dropped + "\n").encode("utf-8", errors="replace"))
            self.status_message = f"following {self.container_name}"
            self.seq += 1
            self.events.append((self.seq, clean + "\n"))
            self.cond.notify_all()

    def _load_initial_snapshot(self):
        try:
            tail_lines = max(0, int(LOG_INITIAL_TAIL_LINES or 0))
            cmd = ["docker", "logs", "--timestamps"]
            if tail_lines > 0:
                cmd += ["--tail", str(tail_lines)]
            else:
                cmd += ["--tail", "0"]
            cmd.append(self.container_name)
            p = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=max(1.0, float(LOG_INITIAL_SNAPSHOT_TIMEOUT_SECONDS or 15)),
            )
            output = p.stdout or ""
        except Exception as e:
            self._set_status(f"could not load docker logs for {self.container_name}: {e}")
            return "", ""
        last_timestamp = ""
        last_line = ""
        for raw in output.splitlines():
            timestamp, clean = split_timestamped_docker_log_line(raw)
            self._append_line(clean, timestamp=timestamp)
            if clean:
                last_timestamp = timestamp or last_timestamp
                last_line = clean
        if not output.strip():
            self._set_status(f"waiting for first log lines from {self.container_name}...")
        return last_timestamp, last_line

    def _run(self):
        while True:
            try:
                if self.container_name not in docker_names(all_containers=False):
                    self._set_status(f"{self.container_name} is not running; waiting...")
                    time.sleep(2)
                    continue
                with self.cond:
                    self._reset_locked(f"loading logs for {self.container_name}...")
                last_timestamp, last_line = self._load_initial_snapshot()
                cmd = ["docker", "logs", "--timestamps", "-f"]
                if last_timestamp:
                    cmd += ["--since", last_timestamp]
                else:
                    cmd += ["--tail", "0"]
                cmd.append(self.container_name)
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                try:
                    if p.stdout is not None:
                        for raw in p.stdout:
                            timestamp, clean = split_timestamped_docker_log_line(raw)
                            if timestamp == last_timestamp and clean == last_line:
                                continue
                            self._append_line(clean, timestamp=timestamp)
                            if clean:
                                last_timestamp = timestamp or last_timestamp
                                last_line = clean
                finally:
                    try:
                        p.terminate()
                    except Exception:
                        pass
                self._set_status(f"log stream for {self.container_name} ended; reconnecting...")
            except Exception as e:
                self._set_status(f"log watcher error for {self.container_name}: {e}")
            time.sleep(2)


def get_runtime_log_watcher(container_name):
    key = str(container_name or "").strip()
    if not key:
        return None
    with runtime_log_watchers_lock:
        watcher = runtime_log_watchers.get(key)
        if watcher is None:
            watcher = RuntimeLogWatcher(key)
            runtime_log_watchers[key] = watcher
        return watcher

def cleanup_vllm_containers():
    results = []
    for inst in read_instances_config():
        try:
            rc, out = stop_instance(inst["id"])
            results.append(f"{inst['id']} down rc={rc} {out[-500:]}")
        except Exception as e:
            results.append(f"{inst['id']} down error {e}")
    names = vllm_container_names(all_containers=True, force=True, timeout=5)
    for name in names:
        if name in [instance_container_name(inst) for inst in read_instances_config()]:
            continue
        rc, out = run_cmd(["docker", "rm", "-f", name], timeout=60)
        results.append(f"docker rm -f {name}: rc={rc} {out[-500:]}")
    if not results:
        return "no club-3090 runtime containers to clean"
    msg = " || ".join(results)
    log_control("CLEANUP " + msg)
    return msg

def service_status(name):
    cache_key = str(name or "").strip()
    now = time.time()
    with slow_cache_lock:
        cached = dict(service_status_cache.get(cache_key) or {})
        cached_value = str(cached.get("value") or "")
        cached_time = float(cached.get("time") or 0.0)
    if cached_time and now - cached_time < 3.0:
        return cached_value or "unknown"
    value = cached_value or "unknown"
    try:
        value = subprocess.check_output(["systemctl","is-active",cache_key], text=True, stderr=subprocess.DEVNULL, timeout=1.0).strip() or "inactive"
    except subprocess.CalledProcessError as e:
        value = (e.output or "inactive").strip() or "inactive"
    except Exception:
        value = cached_value or "unknown"
    with slow_cache_lock:
        service_status_cache[cache_key] = {"value": value, "time": time.time()}
    return value


def compose_variant_metadata(mode):
    cache_key = str(mode or "").strip()
    default = {
        "ctx_size_tokens": None,
        "speculative_method": None,
        "drafted_tokens": None,
    }
    if not cache_key:
        return dict(default)
    with slow_cache_lock:
        cached = compose_metadata_cache.get(cache_key)
        if isinstance(cached, dict):
            return dict(cached)
    spec = resolve_variant_spec(cache_key) or {}
    meta = {
        "ctx_size_tokens": spec.get("max_model_len"),
        "speculative_method": spec.get("speculative_method"),
        "drafted_tokens": spec.get("drafted_tokens"),
    }
    for key, value in default.items():
        if meta.get(key) in ("", None, False):
            meta[key] = value
    with slow_cache_lock:
        compose_metadata_cache[cache_key] = dict(meta)
    return dict(meta)


def _normalize_ratio_percent(value):
    number = safe_float(value)
    if number <= 1.0:
        number *= 100.0
    return round(number, 2)


def clear_gpu_session_peaks():
    with metrics_lock:
        gpu_session_peaks.clear()
    log_control("GPU session peaks reset")
    return {"cleared": True}


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
        if metrics_out["prompt_tps"] is None and ("Avg prompt throughput:" in line or "GPU KV cache usage:" in line):
            prompt_match = re.search(r"Avg prompt throughput:\s*([0-9.]+)\s*tokens/s", line)
            gen_match = re.search(r"Avg generation throughput:\s*([0-9.]+)\s*tokens/s", line)
            running_match = re.search(r"Running:\s*([0-9]+)\s*reqs", line)
            waiting_match = re.search(r"Waiting:\s*([0-9]+)\s*reqs", line)
            pending_match = re.search(r"Pending:\s*([0-9]+)\s*reqs", line)
            swapped_match = re.search(r"Swapped:\s*([0-9]+)\s*reqs", line)
            gpu_kv_match = re.search(r"GPU KV cache usage:\s*([0-9.]+)\s*%", line)
            cpu_kv_match = re.search(r"CPU KV cache usage:\s*([0-9.]+)\s*%", line)
            prefix_match = re.search(r"Prefix cache hit rate:\s*(?:GPU:\s*)?([0-9.]+)%", line)
            if prompt_match:
                metrics_out["prompt_tps"] = round(safe_float(prompt_match.group(1)), 2)
            if gen_match:
                metrics_out["generation_tps"] = round(safe_float(gen_match.group(1)), 2)
            if running_match:
                metrics_out["running_requests"] = int(running_match.group(1))
            if waiting_match:
                metrics_out["waiting_requests"] = int(waiting_match.group(1))
            if pending_match:
                metrics_out["pending_requests"] = int(pending_match.group(1))
            if swapped_match:
                metrics_out["swapped_requests"] = int(swapped_match.group(1))
            if gpu_kv_match:
                metrics_out["gpu_kv_cache_usage_pct"] = round(safe_float(gpu_kv_match.group(1)), 2)
            if cpu_kv_match:
                metrics_out["cpu_kv_cache_usage_pct"] = round(safe_float(cpu_kv_match.group(1)), 2)
            if prefix_match:
                metrics_out["prefix_cache_hit_rate_pct"] = round(safe_float(prefix_match.group(1)), 2)
        if not metrics_out["speculative"] and ("Speculative metrics:" in line or "SpecDecoding metrics:" in line):
            spec = {}
            drafted_match = re.search(r"Number of speculative tokens:\s*([0-9]+)", line)
            accepted_match = re.search(r"(?:Number of accepted tokens|Accepted):\s*([0-9]+)", line)
            draft_tokens_match = re.search(r"(?:Number of draft tokens|Drafted):\s*([0-9]+)", line)
            emitted_match = re.search(r"Number of emitted tokens:\s*([0-9]+)", line)
            accept_rate_match = re.search(r"(?:Draft acceptance rate|Avg Draft acceptance rate):\s*([0-9.]+)%?", line)
            efficiency_match = re.search(r"System efficiency:\s*([0-9.]+)", line)
            mean_accept_match = re.search(r"Mean acceptance length:\s*([0-9.]+)", line)
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
            if spec:
                metrics_out["speculative"] = spec
        if metrics_out["prompt_tps"] is not None and metrics_out["speculative"]:
            break
    return metrics_out


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
    if parsed.get("prompt_tps") not in (None, "", 0, 0.0):
        remembered["prompt_tps"] = parsed.get("prompt_tps")
    elif remembered.get("prompt_tps") not in (None, ""):
        parsed["prompt_tps"] = remembered.get("prompt_tps")
    if parsed.get("generation_tps") not in (None, "", 0, 0.0):
        remembered["generation_tps"] = parsed.get("generation_tps")
    elif remembered.get("generation_tps") not in (None, ""):
        parsed["generation_tps"] = remembered.get("generation_tps")
    if parsed.get("gpu_kv_cache_usage_pct") not in (None, "", 0, 0.0):
        remembered["gpu_kv_cache_usage_pct"] = parsed.get("gpu_kv_cache_usage_pct")
    elif not active_now and remembered.get("gpu_kv_cache_usage_pct") not in (None, ""):
        parsed["gpu_kv_cache_usage_pct"] = remembered.get("gpu_kv_cache_usage_pct")
    if parsed.get("cpu_kv_cache_usage_pct") not in (None, "", 0, 0.0):
        remembered["cpu_kv_cache_usage_pct"] = parsed.get("cpu_kv_cache_usage_pct")
    elif not active_now and remembered.get("cpu_kv_cache_usage_pct") not in (None, ""):
        parsed["cpu_kv_cache_usage_pct"] = remembered.get("cpu_kv_cache_usage_pct")
    with slow_cache_lock:
        runtime_log_metric_memory[cache_key] = dict(remembered)
    with slow_cache_lock:
        runtime_log_metrics_cache[cache_key] = {"value": dict(parsed), "time": time.time()}
    return parsed


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

def gpu_stats():
    if not shutil.which("nvidia-smi"):
        return []
    vendor_map = gpu_vendors_by_index()
    field_sets = [
        "index,name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,power.limit,fan.speed,clocks.current.graphics,clocks.current.memory,compute_cap",
        "index,name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,power.limit,fan.speed,clocks.current.graphics,clocks.current.memory",
    ]
    out = ""
    last_error = None
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
        return [{"error": str(last_error or "nvidia-smi query failed")}]
    rows = []
    for line in out.splitlines():
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
            peak_key = str(idx)
            with metrics_lock:
                peak_row = gpu_session_peaks.setdefault(peak_key, {})
                if temp_now is not None:
                    peak_row["temp_c"] = round(max(temp_now, safe_float(peak_row.get("temp_c"))), 2)
                if power_now is not None:
                    peak_row["power_w"] = round(max(power_now, safe_float(peak_row.get("power_w"))), 2)
                if core_clock_now is not None:
                    peak_row["core_clock_mhz"] = round(max(core_clock_now, safe_float(peak_row.get("core_clock_mhz"))), 2)
                if mem_clock_now is not None:
                    peak_row["mem_clock_mhz"] = round(max(mem_clock_now, safe_float(peak_row.get("mem_clock_mhz"))), 2)
                peak_temp = peak_row.get("temp_c")
                peak_power = peak_row.get("power_w")
                peak_core = peak_row.get("core_clock_mhz")
                peak_mem = peak_row.get("mem_clock_mhz")
            rows.append({
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
            })
        except Exception as e:
            rows.append({"error": f"parse gpu stat failed: {e}"})
    return rows

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
        rx_kbps=tx_kbps=0.0
        if prev and iface in prev[1]:
            dt=max(now-prev[0],0.001)
            rx_kbps=max(0.0,(vals['rx']-prev[1][iface]['rx'])*8/1000/dt)
            tx_kbps=max(0.0,(vals['tx']-prev[1][iface]['tx'])*8/1000/dt)
        total_rx += rx_kbps; total_tx += tx_kbps
        ifaces.append({'iface':iface,'rx_kbps':round(rx_kbps,1),'tx_kbps':round(tx_kbps,1),'rx_mb':round(vals['rx']/1024/1024,1),'tx_mb':round(vals['tx']/1024/1024,1)})
    return {'local_ip':local_ip(),'public_ip':public_ip(),'rx_kbps':round(total_rx,1),'tx_kbps':round(total_tx,1),'interfaces':ifaces}


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
    util=[]; mem=[]; temps=[]; watts=[]; gpu_points=[]
    for g in gpus:
        if "error" in g: continue
        util_v=safe_float(g.get("util_pct")); mem_v=safe_float(g.get("mem_pct")); temp_v=safe_float(g.get("temp_c")); watt_v=safe_float(g.get("power_w")); fan_v=safe_float(g.get("fan_pct"))
        util.append(util_v); mem.append(mem_v); temps.append(temp_v); watts.append(watt_v)
        gpu_points.append({"index":g.get("index"),"util":util_v,"mem_pct":mem_v,"temp":temp_v,"power":watt_v,"fan":fan_v})
    ram_pct=safe_float((sysinfo.get('memory') or {}).get('used_pct')); cpu_pct=safe_float((sysinfo.get('cpu') or {}).get('total_pct'))
    disks=sysinfo.get('disks') or []; disk_pct=max([safe_float(d.get('used_pct')) for d in disks if isinstance(d,dict)] or [0])
    net=sysinfo.get('network') or {}; rx_kbps=safe_float(net.get('rx_kbps')); tx_kbps=safe_float(net.get('tx_kbps'))
    with metrics_lock:
        point={"t":int(time.time()),"gpu_util":round(sum(util)/len(util),1) if util else 0,"mem_pct":round(sum(mem)/len(mem),1) if mem else 0,"temp_c":round(max(temps),1) if temps else 0,"power_w":round(sum(watts),1) if watts else 0,"ram_pct":round(ram_pct,1),"cpu_pct":round(cpu_pct,1),"disk_pct":round(disk_pct,1),"system_util_pct":round((cpu_pct+ram_pct+(sum(util)/len(util) if util else 0))/3,1),"net_rx_kbps":round(rx_kbps,1),"net_tx_kbps":round(tx_kbps,1),"gpus":gpu_points,"cpu_cores":(sysinfo.get('cpu') or {}).get('cores',[]),"active_requests":metrics.get("active_requests",0),"latency_s":metrics.get("last_latency_s") or 0,"ttft_s":metrics.get("last_ttft_s") or 0,"tps":metrics.get("last_tokens_per_second") or 0}
        series_points.append(point)
        latest_gpu_rows = gpus
        latest_system_snapshot = sysinfo
        latest_metrics_collected_at = time.time()
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
    if request_key == "GLOBAL" and "LEGACY" in target_metrics_snapshot:
        request_key = "LEGACY"
    request_metrics = dict(target_metrics_snapshot.get(request_key) or default_target_request_metrics())
    spec = resolve_variant_spec(row.get("mode")) or {}
    runtime_meta = compose_variant_metadata(row.get("mode"))
    log_metrics = runtime_log_metrics_for_container(row.get("container")) if row.get("running") and row.get("container") else {}
    speculative = dict(log_metrics.get("speculative") or {})
    if speculative.get("drafted_tokens") in (None, "") and runtime_meta.get("drafted_tokens") not in (None, ""):
        speculative["drafted_tokens"] = runtime_meta.get("drafted_tokens")
    prompt_tps = log_metrics.get("prompt_tps")
    input_tokens = first_defined(request_metrics.get("last_input_tokens"), request_metrics.get("last_total_tokens"))
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
        "generation_tps": log_metrics.get("generation_tps"),
        "running_requests": log_metrics.get("running_requests"),
        "waiting_requests": first_defined(log_metrics.get("waiting_requests"), log_metrics.get("pending_requests")),
        "pending_requests": log_metrics.get("pending_requests"),
        "swapped_requests": log_metrics.get("swapped_requests"),
        "gpu_kv_cache_usage_pct": log_metrics.get("gpu_kv_cache_usage_pct"),
        "cpu_kv_cache_usage_pct": log_metrics.get("cpu_kv_cache_usage_pct"),
        "prefix_cache_hit_rate_pct": log_metrics.get("prefix_cache_hit_rate_pct"),
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
    }


def build_instance_runtime_metrics_snapshot(instances, legacy_instance, target_metrics_snapshot=None):
    rows = {}
    if legacy_instance:
        rows[str(legacy_instance.get("id") or "").strip().upper()] = build_instance_runtime_metrics_entry(legacy_instance, target_metrics_snapshot)
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
    speculative = dict(log_metrics.get("speculative") or {})
    if speculative.get("drafted_tokens") in (None, "") and spec.get("drafted_tokens") not in (None, ""):
        speculative["drafted_tokens"] = spec.get("drafted_tokens")
    prompt_tps = log_metrics.get("prompt_tps")
    input_tokens = first_defined(metrics_snapshot.get("last_input_tokens"), metrics_snapshot.get("last_total_tokens"))
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
        "generation_tps": log_metrics.get("generation_tps"),
        "running_requests": log_metrics.get("running_requests"),
        "waiting_requests": first_defined(log_metrics.get("waiting_requests"), log_metrics.get("pending_requests")),
        "pending_requests": log_metrics.get("pending_requests"),
        "swapped_requests": log_metrics.get("swapped_requests"),
        "gpu_kv_cache_usage_pct": log_metrics.get("gpu_kv_cache_usage_pct"),
        "cpu_kv_cache_usage_pct": log_metrics.get("cpu_kv_cache_usage_pct"),
        "prefix_cache_hit_rate_pct": log_metrics.get("prefix_cache_hit_rate_pct"),
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
    }


def build_status_snapshot():
    with metrics_lock:
        m = dict(metrics)
        recent = list(recent_requests)
        series = list(series_points)
    runtime_inventory = load_runtime_inventory()
    upstream_services = discover_upstream_services(force=False, max_age=30.0)
    current_mode = active_mode()
    ap = active_port()
    current_container_name = current_container()
    cfg = read_server_config()
    gpu_count = detect_gpu_count_runtime()
    instances = instances_snapshot()
    legacy_instance = legacy_global_instance_snapshot()
    target_metrics_snapshot = snapshot_target_request_metrics()
    instance_runtime_metrics = build_instance_runtime_metrics_snapshot(instances, legacy_instance, target_metrics_snapshot)
    runtime_rows = running_runtime_rows(instances, legacy_instance)
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
    legacy_dual_mode = legacy_instance.get("mode") if legacy_instance and legacy_instance.get("running") else None
    failed_mode = str(read_switch_failure().get("mode") or "")
    active_modes = [mode for mode in runtime_mode_list(runtime_rows, "") if mode and mode != failed_mode]
    containers = runtime_container_list(runtime_rows, "")
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
    gpus_snapshot, system_snapshot, _ = get_latest_runtime_snapshot()
    return {
        "active_mode": reported_active_mode,
        "active_modes": active_modes,
        "active_port": reported_active_port,
        "container": (containers[0] if containers else ""),
        "containers": containers,
        "club3090_dir": CLUB3090_DIR,
        "script_version": SCRIPT_VERSION,
        "uptime_seconds": int(time.time() - startup_time),
        "vllm_service": service_status("club3090-vllm.service"),
        "control_service": service_status("club3090-control.service"),
        "caddy_service": service_status("club3090-caddy.service") if cfg.get("https_enabled", False) else "disabled",
        "console_service": service_status("club3090-console-log.service"),
        "metrics": m,
        "recent_requests": recent,
        "gpus": gpus_snapshot,
        "power": power_status(),
        "system": system_snapshot,
        "series": series,
        "ui_config": read_ui_config(),
        "presets": preset_catalog(),
        "gpu_count": gpu_count,
        "instances": instances,
        "legacy_global_instance": legacy_instance,
        "runtime_inventory": runtime_inventory,
        "models": list(runtime_inventory.get("models") or []),
        "variants": list(runtime_inventory.get("variants") or []),
        "nvlink": detect_nvlink_status(),
        "upstream_services": upstream_services,
        "model_install_job": model_install_job_snapshot(),
        "admin_task_job": admin_task_job_snapshot(),
        "single_gpu_modes": list(SINGLE_GPU_MODES),
        "dual_gpu_modes": list(DUAL_GPU_MODES),
        "running_dual_mode": (dual_rows[0]["mode"] if dual_rows else legacy_dual_mode),
        "running_dual_gpu_indices": (dual_rows[0]["gpu_indices"] if dual_rows else ([0, 1] if legacy_dual_mode else [])),
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


def refresh_status_snapshot():
    global status_snapshot_cache, status_snapshot_updated_at
    snapshot = build_status_snapshot()
    with status_snapshot_lock:
        status_snapshot_cache = snapshot
        status_snapshot_updated_at = time.time()
    return snapshot


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
        "club3090_dir": CLUB3090_DIR,
        "script_version": SCRIPT_VERSION,
        "uptime_seconds": int(time.time() - startup_time),
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
        "ui_config": ui_cfg,
        "presets": previous.get("presets") if isinstance(previous.get("presets"), dict) else preset_catalog(),
        "gpu_count": int(previous.get("gpu_count") or 0),
        "instances": list(previous.get("instances") or []),
        "legacy_global_instance": previous.get("legacy_global_instance") if isinstance(previous.get("legacy_global_instance"), dict) else {},
        "runtime_inventory": runtime_inventory,
        "models": list(runtime_inventory.get("models") or previous.get("models") or []),
        "variants": list(runtime_inventory.get("variants") or previous.get("variants") or []),
        "nvlink": dict(previous.get("nvlink") or {}),
        "upstream_services": list(previous.get("upstream_services") or []),
        "model_install_job": previous.get("model_install_job") if isinstance(previous.get("model_install_job"), dict) else model_install_job_snapshot(),
        "admin_task_job": previous.get("admin_task_job") if isinstance(previous.get("admin_task_job"), dict) else admin_task_job_snapshot(),
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


def get_status_snapshot(force=False):
    with status_snapshot_lock:
        snapshot = status_snapshot_cache
        updated_at = status_snapshot_updated_at
    try:
        if force or not snapshot or not updated_at:
            return refresh_status_snapshot()
        return snapshot
    except Exception as e:
        log_control(f"status snapshot fallback: {e}")
        return build_status_error_snapshot(e, snapshot)


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
    legacy = legacy_global_instance_snapshot()
    if legacy and legacy.get("running"):
        add(legacy, legacy.get("container"))
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


def export_selected_log(source="docker", instance_id=""):
    source_name = str(source or "docker").strip().lower()
    service_id = ""
    if source_name.startswith("service:"):
        service_id = source_name.split(":", 1)[1]
        source_name = "service"
    exported_at = time.strftime("%Y-%m-%d %H:%M:%S")
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
    global current_profile, GPU_ACTIVE_POWER_LIMIT_W, GPU_IDLE_POWER_LIMIT_W, GPU_IDLE_LOCK_CLOCKS, CPU_ACTIVE_GOVERNOR, CPU_IDLE_GOVERNOR, POWER_IDLE_AFTER_SECONDS, CONTAINER_STOP_AFTER_SECONDS
    if name not in PERFORMANCE_PROFILES:
        raise ValueError("Invalid performance profile")
    log_control(f"PROFILE requested name={name}")
    cfg = PERFORMANCE_PROFILES[name]
    GPU_ACTIVE_POWER_LIMIT_W = int(cfg["gpu_active"]); GPU_IDLE_POWER_LIMIT_W = int(cfg["gpu_idle"]); GPU_IDLE_LOCK_CLOCKS = str(cfg["idle_clocks"])
    CPU_ACTIVE_GOVERNOR = str(cfg["cpu_active"]); CPU_IDLE_GOVERNOR = str(cfg["cpu_idle"])
    POWER_IDLE_AFTER_SECONDS = int(cfg["idle_after"]); CONTAINER_STOP_AFTER_SECONDS = int(cfg["stop_after"])
    current_profile = name
    clear_gpu_session_peaks()
    result = {"cpu": apply_cpu_active_power(), "gpu": apply_gpu_active_power(), "profile": name}
    log_control(f"PROFILE applied name={name} cpu={result.get('cpu')} gpu={result.get('gpu')}")
    return result



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


def fan_targets_from_temps():
    temps = parse_gpu_temps()
    if not temps:
        return {idx: 70 for idx in gpu_indices()}
    return {idx: fan_speed_for_temp(temp) for idx, temp in temps}


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


def apply_gpu_active_power(skip_fans=False):
    if not power_optimizations_enabled:
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
            log_control(f"POWER legacy stop requested reason={reason}")
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
    apply_cpu_active_power()
    apply_gpu_active_power(skip_fans=True)
    target = get_instance(instance_id) if instance_id else primary_instance()
    if target is None:
        mode = active_mode()
        port = mode_default_port(mode, 8020)
        if port_open(port, timeout=0.25):
            with metrics_lock:
                power_state["container"] = "running"
            return
        log_control(f"POWER auto-starting legacy default mode={mode}")
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
            now = time.time()
            with metrics_lock:
                active = metrics.get("active_requests", 0)
                booting = switch_job_active()
                idle_for = 0 if active > 0 or booting else max(0.0, now - last_request_finished_at)
            if active == 0 and not booting and idle_for >= POWER_IDLE_AFTER_SECONDS and not idle_power_applied:
                apply_cpu_idle_power()
                apply_gpu_idle_power()
                idle_power_applied = True
            if active > 0 or booting or idle_for < POWER_IDLE_AFTER_SECONDS:
                idle_power_applied = False
            if power_optimizations_enabled and not fan_manual_override:
                # Refresh manual fan curve periodically even while idle; Linux/NVIDIA
                # auto fan behavior can leave 3090 fans off until temps are too high.
                apply_fan_curve_once()
        except Exception as e:
            log_control(f"POWER watchdog error: {e}")
        time.sleep(15)



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
        power_state["gpu"] = "default"
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
        return set_gpu_fans(speed=FAN_MAX_SPEED, auto=False, indices=target_indices)
    fan_curve_pause_until = time.time() + (1 if power_optimizations_enabled else 0)
    results = set_gpu_fans(auto=True, indices=target_indices)
    if power_optimizations_enabled:
        schedule_fan_curve_resume(indices=target_indices, delay=1.0)
    else:
        fan_curve_pause_until = 0.0
    return results

def power_status():
    with metrics_lock:
        active = int(metrics.get("active_requests", 0) or 0)
        booting = switch_job_active()
        idle_for = 0 if active > 0 or booting else int(max(0.0, time.time() - last_request_finished_at))
        fan_curve_text = ", ".join([f"<{temp}C={speed}%" for temp, speed in FAN_CURVE]) + ", >=65C=100%"
        return {**power_state, "profile": current_profile, "idle_for_seconds": idle_for, "idle_power_after_seconds": POWER_IDLE_AFTER_SECONDS, "container_stop_after_seconds": 0, "container_auto_stop_enabled": CONTAINER_AUTO_STOP_ENABLED, "gpu_active_power_limit_w": GPU_ACTIVE_POWER_LIMIT_W, "gpu_idle_power_limit_w": GPU_IDLE_POWER_LIMIT_W, "gpu_idle_lock_clocks": GPU_IDLE_LOCK_CLOCKS, "cpu_active_governor": CPU_ACTIVE_GOVERNOR, "cpu_idle_governor": CPU_IDLE_GOVERNOR, "optimizations_enabled": power_optimizations_enabled, "fan_manual_override": fan_manual_override, "fan_curve": fan_curve_text, "fan_min_safe_speed": FAN_MIN_SAFE_SPEED}

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


def _docker_logs_tail(container_name, lines=80):
    name = str(container_name or "").strip()
    if not name:
        return ""
    try:
        return subprocess.check_output(
            ["docker", "logs", "--tail", str(max(1, int(lines))), name],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        )
    except Exception:
        return ""


def _container_bootstrap_complete(container_name):
    logs = _docker_logs_tail(container_name, lines=200)
    if not logs:
        return False
    marker = str(LOG_BOOTSTRAP_MARKER or "").strip()
    if marker and marker in logs:
        return True
    return "Application startup complete" in logs


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


def wait_for_runtime_ready(container_name, ready_url, timeout=900):
    name = str(container_name or "").strip()
    target_url = str(ready_url or "").strip()
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
        elif seen_container:
            raise RuntimeError(f"Container {name} disappeared before reaching ready state.")
        if (
            not name
            or _container_bootstrap_complete(name)
            or _runtime_models_available_once(name, target_url, min_interval=15)
        ):
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
        env = _repo_subprocess_env()
        env.pop("CLUB3090_GPU", None)
        env["READY_URL"] = ready_url_for_mode(target_mode)
        env["PORT"] = str(int(target_port))
        env["MODEL_DIR"] = _resolve_variant_model_dir_root(target_spec)
        env["COMPOSE_BIN"] = COMPOSE_BIN
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
            env["CUDA_VISIBLE_DEVICES"] = visible_devices
            env["NVIDIA_VISIBLE_DEVICES"] = visible_devices
        env = _apply_variant_hardware_guard(target_spec, env)
        apply_cpu_active_power()
        apply_gpu_active_power(skip_fans=True)
        log_control(f"SWITCH {label} cleanup before mode={target_mode}")
        cleanup_msg = cleanup_vllm_containers()
        log_control(f"SWITCH {label} start mode={target_mode} port={env['PORT']} ready_url={env['READY_URL']}")
        output = ""
        rc = 0
        upstream_tag = str(target_spec.get("upstream_tag") or "").strip()
        used_upstream_wait = False
        switch_path = os.path.join(CLUB3090_DIR, "scripts", "switch.sh")
        if upstream_tag and os.path.exists(switch_path):
            used_upstream_wait = True
            p = subprocess.run(["bash", "scripts/switch.sh", upstream_tag], cwd=CLUB3090_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1800)
            rc = int(p.returncode)
            output = p.stdout or ""
        else:
            compose_file = str(target_spec.get("compose_abs_path") or "").strip()
            compose_project_dir = str(target_spec.get("compose_project_dir_abs_path") or "").strip() or os.path.dirname(compose_file) or CLUB3090_DIR
            cmd = compose_cmd() + ["--project-directory", compose_project_dir, "-f", compose_file, "up", "-d"]
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
        if not used_upstream_wait:
            wait_for_runtime_ready(
                str(target_spec.get("container_name") or ""),
                env["READY_URL"],
                timeout=900,
            )
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
            write_switch_failure(selector, first_error)
            if read_active_mode_file() == selector:
                clear_active_mode()
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

def apply_preset(body, preset_name, max_token_cap):
    try:
        data = json.loads(body or b"{}")
    except Exception:
        return body
    preset = get_all_presets().get(preset_name)
    if not preset:
        return body
    data = merge_preset_params(dict(data), preset)
    data = inject_system_prompt_into_payload(data, preset_system_prompt(preset_name))
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
    runtime_rows = running_runtime_rows(instances_snapshot(), legacy_global_instance_snapshot())
    if target_id:
        match = next((dict(row) for row in runtime_rows if str(row.get("id") or "").strip().upper() == target_id), None)
        if match:
            return match, resolve_variant_spec(match.get("mode")) or {}
        if is_legacy_global_instance_id(target_id):
            legacy = legacy_global_instance_snapshot()
            if legacy and legacy.get("running"):
                return dict(legacy), resolve_variant_spec(legacy.get("mode")) or {}
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
    if stream:
        payload["stream_options"] = {"include_usage": True}
    return payload


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
            return json.loads(raw.decode("utf-8", errors="ignore") or "{}")
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
    status_code = 200
    metrics_started = False
    stream_opened = False
    response_usage = {"tokens": 0, "input_tokens": 0, "output_tokens": 0, "tool_calls": 0}
    request_usage = {}
    try:
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
        tools, tool_map = build_enabled_mcp_tools()
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
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
        with metrics_lock:
            metrics["total_requests"] += 1
            metrics["active_requests"] += 1
            metrics["last_preset"] = preset_name
            metrics["last_path"] = "/admin/chat-stream"
            target_request_metrics.setdefault(target_key, default_target_request_metrics())
        metrics_started = True

        handler.close_connection = False
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "keep-alive")
        handler.emit_pending_headers()
        handler.end_headers()
        stream_opened = True

        assistant_text = ""
        current_payload = dict(payload)
        for _ in range(6):
            stream_response, current_payload = open_chat_backend_stream(port, current_payload)
            pass_text_parts = []
            pass_reasoning_parts = []
            tool_delta_store = {}
            with stream_response as response:
                for raw_event in iter_sse_events(response):
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
                    if first_chunk_at is None:
                        first_chunk_at = time.time()
                    usage_block = event_obj.get("usage") if isinstance(event_obj.get("usage"), dict) else {}
                    if usage_block:
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
                        if reasoning_chunk:
                            pass_reasoning_parts.append(reasoning_chunk)
                            handler.send_sse_event("reasoning", {"text": reasoning_chunk})
                        content_chunk = str(delta.get("content") or choice.get("text") or "")
                        if content_chunk:
                            assistant_text += content_chunk
                            pass_text_parts.append(content_chunk)
                            handler.send_sse_event("delta", {"text": content_chunk})
                        merge_stream_tool_call_delta(tool_delta_store, delta.get("tool_calls") or [])
            tool_calls = finalize_stream_tool_calls(tool_delta_store)
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
                call_id = str(tool_call.get("id") or secrets.token_hex(6))
                function = dict(tool_call.get("function") or {})
                tool_name = str(function.get("name") or "")
                handler.send_sse_event("tool", {"name": tool_name, "message": f"Running tool {tool_name}..."})
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

        log_metrics = runtime_log_metrics_for_container(target.get("container"), force=True) if target and target.get("container") else {}
        ttft = round(first_chunk_at - start, 3) if first_chunk_at else None
        generation_tps = first_defined(log_metrics.get("generation_tps"), None)
        if generation_tps in (None, "", 0, 0.0) and first_chunk_at and int(response_usage.get("output_tokens") or 0) > 0:
            generation_tps = round(
                float(response_usage.get("output_tokens") or 0) / max(time.time() - first_chunk_at, 0.001),
                2,
            )
        else:
            generation_tps = round(float(generation_tps), 2) if generation_tps not in (None, "", 0, 0.0) else None

        handler.send_sse_event("done", {
            "ok": True,
            "instance_id": target_id,
            "mode": str(target.get("mode") or ""),
            "model": str(current_payload.get("model") or ""),
            "usage": response_usage,
            "generation_tps": generation_tps,
            "prompt_tps": log_metrics.get("prompt_tps"),
            "ttft_s": ttft,
            "latency_s": round(time.time() - start, 3),
            "status": 200,
            "path": "/admin/chat-stream",
        })
        handler.close_connection = True
    except Exception as e:
        status_code = 500
        if stream_opened:
            try:
                handler.send_sse_event("error", {"error": str(e)})
            except Exception:
                pass
            handler.close_connection = True
        else:
            handler.send_json({"ok": False, "error": str(e)}, 500)
    finally:
        if metrics_started:
            latency = round(time.time() - start, 3)
            prompt_tokens = max(int(request_usage.get("input_tokens") or 0), int(response_usage.get("input_tokens") or 0))
            output_tokens = max(int(response_usage.get("output_tokens") or 0), max(0, int(response_usage.get("tokens") or 0) - int(prompt_tokens)))
            total_tokens = max(int(response_usage.get("tokens") or 0), int(prompt_tokens) + int(output_tokens))
            log_metrics = runtime_log_metrics_for_container(target.get("container"), force=True) if target and target.get("container") else {}
            ttft = round(first_chunk_at - start, 3) if first_chunk_at else None
            display_tps = first_defined(log_metrics.get("generation_tps"), None)
            if display_tps in (None, "", 0, 0.0) and first_chunk_at and output_tokens > 0:
                display_tps = round(float(output_tokens) / max(time.time() - first_chunk_at, 0.001), 2)
            elif display_tps not in (None, "", 0, 0.0):
                display_tps = round(float(display_tps), 2)
            else:
                display_tps = None
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
                if display_tps not in (None, "", 0, 0.0):
                    target_row["last_tokens_per_second"] = display_tps
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

HTML = ""  # Injected by build.py for shipped outputs.
class CommonMixin:
    def log_message(self, fmt, *args):
        return
    def queue_header(self, name, value):
        pending = list(getattr(self, "_pending_headers", []) or [])
        pending.append((str(name), str(value)))
        self._pending_headers = pending
    def emit_pending_headers(self):
        for name, value in list(getattr(self, "_pending_headers", []) or []):
            self.send_header(name, value)
        self._pending_headers = []
    def read_json_body(self):
        n = int(self.headers.get("content-length","0") or "0")
        body = self.rfile.read(n) if n else b"{}"
        if not body:
            return {}
        return json.loads(body)
    def redirect(self, location, code=302):
        self.close_connection = True
        self.send_response(code)
        self.send_header("Location", location)
        self.emit_pending_headers()
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
    def send_bytes(self, payload, content_type="application/octet-stream", code=200):
        self.close_connection = True
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.emit_pending_headers()
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
    def send_json(self, obj, code=200):
        self.send_bytes(json.dumps(obj, indent=2).encode("utf-8"), "application/json", code)

class AdminHandler(CommonMixin, BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def require_auth(self):
        client_ip = self.client_address[0] if self.client_address else ""
        secure_cookie = request_is_https(self.headers)
        if admin_session_ok(self.headers, client_ip):
            return True
        auth_header = self.headers.get("Authorization","")
        if check_basic_auth(auth_header):
            self.queue_header("Set-Cookie", build_admin_session_cookie(create_admin_session(client_ip), secure=secure_cookie))
            return True
        if parse_cookie_header(self.headers.get("Cookie", "")).get(ADMIN_SESSION_COOKIE_NAME):
            self.queue_header("Set-Cookie", expired_admin_session_cookie(secure=secure_cookie))
        if should_log_admin_auth_denial(client_ip, self.path):
            log_audit("admin_auth_denied", client=client_ip, path=self.path)
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="club-3090"')
        self.emit_pending_headers()
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        return False
    def send_sse_event(self, event_name, payload):
        body = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(f"event: {event_name}\ndata: {body}\n\n".encode("utf-8", errors="replace"))
        try:
            self.wfile.flush()
        except Exception:
            pass
        self.wfile.flush()
    def send_sse_comment(self, text="ping"):
        self.wfile.write(f": {text}\n\n".encode("utf-8", errors="replace"))
        self.wfile.flush()
    def do_GET(self):
        if not self.require_auth():
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/":
            self.redirect("/admin")
            return
        if path == "/admin":
            html = HTML.replace("__SCRIPT_VERSION__", SCRIPT_VERSION).replace(":8008/admin", f":{ADMIN_PORT}/admin").replace(":8009", f":{PROXY_PORT}")
            self.send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/admin/status":
            params = parse_admin_query_params(parsed)
            force = str(params.get("force") or "").strip().lower() in {"1", "true", "yes", "on"}
            started_at = time.time()
            payload = get_status_snapshot(force=force)
            elapsed = time.time() - started_at
            if elapsed >= 1.0 or payload.get("status_error"):
                log_control(f"ADMIN status served force={force} elapsed={round(elapsed, 3)}s status_error={bool(payload.get('status_error'))}")
            self.send_json(payload)
            return
        if path == "/admin/logs":
            self.close_connection = False
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache")
            self.send_header("Connection","keep-alive")
            self.emit_pending_headers()
            self.end_headers()
            self.stream_logs(parsed)
            return
        if path == "/admin/audit-stream":
            params = parse_admin_query_params(parsed)
            self.close_connection = False
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache")
            self.send_header("Connection","keep-alive")
            self.emit_pending_headers()
            self.end_headers()
            self.stream_text_file(AUDIT_LOG_FILE, "no audit entries yet; waiting...", initial_tail_lines=parse_tail_lines_param(params, 250))
            return
        if path == "/admin/presets":
            self.send_json({"ok": True, "presets": preset_catalog()})
            return
        if path == "/admin/instances":
            self.send_json({"ok": True, "instances": instances_snapshot(), "single_gpu_modes": list(SINGLE_GPU_MODES), "dual_gpu_modes": list(DUAL_GPU_MODES), "running_dual_instances": running_dual_instance_snapshots()})
            return
        if path == "/admin/users":
            self.send_json({"ok": True, "users": list_users_public(), "groups": list_groups_public(), "server_config": read_server_config()})
            return
        if path == "/admin/groups":
            self.send_json({"ok": True, "groups": list_groups_public(), "users": list_users_public(), "server_config": read_server_config()})
            return
        if path == "/admin/mcp":
            self.send_json({"ok": True, "servers": list_mcp_server_statuses()})
            return
        if path == "/admin/chat-state":
            params = parse_admin_query_params(parsed)
            titles_only = str(params.get("titles") or "").strip().lower() in {"1", "true", "yes", "on"}
            debug_audit("chat_state_get", titles_only=titles_only)
            self.send_json({"ok": True, "state": read_chat_state_titles() if titles_only else read_chat_state()})
            return
        if path == "/admin/chat-conversation":
            params = parse_admin_query_params(parsed)
            debug_audit("chat_conversation_get", conversation_id=params.get("conversation_id") or params.get("id") or "")
            self.send_json(read_chat_conversation_detail(params.get("conversation_id") or params.get("id") or ""))
            return
        if path.startswith("/admin/chat-attachments/"):
            attachment_id = re.sub(r"[^A-Za-z0-9._-]+", "", path.rsplit("/", 1)[-1])
            payload, content_type = read_chat_attachment_response(attachment_id)
            if payload is None:
                self.send_error(404)
                return
            self.send_bytes(payload, f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
            return
        if path == "/admin/control-log":
            try:
                payload = subprocess.check_output(["tail","-n","300",CONTROL_LOG_FILE], text=True, stderr=subprocess.DEVNULL, timeout=3).encode("utf-8", errors="replace")
            except Exception:
                payload = b""
            self.send_bytes(payload, "text/plain; charset=utf-8")
            return
        if path == "/admin/audit-log":
            try:
                payload = subprocess.check_output(["tail","-n","300",AUDIT_LOG_FILE], text=True, stderr=subprocess.DEVNULL, timeout=3).encode("utf-8", errors="replace")
            except Exception:
                payload = b""
            self.send_bytes(payload, "text/plain; charset=utf-8")
            return
        self.send_error(404)
    def do_POST(self):
        if not self.require_auth():
            return
        path = urlsplit(self.path).path
        if path == "/admin/switch":
            try:
                data = self.read_json_body()
                instance_id = str(data.get("instance_id") or "").strip().upper()
                mode = canonical_mode_selector(data.get("mode"))
                spec = resolve_variant_spec(mode)
                if not spec:
                    raise ValueError("Invalid mode")
                scope_kind = str(spec.get("scope_kind") or "")
                if is_legacy_global_instance_id(instance_id):
                    if mode not in DUAL_GPU_MODES:
                        raise ValueError("Preset type does not match the selected instance scope")
                    rc, stop_msg = stop_legacy_global_instance()
                    result = run_switch(mode)
                    log_audit("admin_switch_mode_legacy_global", instance="GLOBAL", mode=mode, stop_rc=rc)
                    self.send_json({"ok": True, "instance": legacy_global_instance_snapshot(), "mode": mode, "output": (stop_msg + "\n" + result)[-12000:], "stopped_instances": ([{"id": "GLOBAL", "rc": rc, "output": stop_msg[-1200:]}] if stop_msg else []), "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
                    return
                if instance_id == "GLOBAL" and scope_kind == "single":
                    targets = [inst for inst in read_instances_config() if inst.get("kind") == "single"]
                    if not targets:
                        raise ValueError("No single-GPU targets are available")
                    wanted_indices = []
                    for target in targets:
                        wanted_indices.extend(target.get("gpu_indices") or [target.get("gpu_index")])
                    stopped = stop_overlapping_instances(wanted_indices)
                    updated_targets = [update_instance(target["id"], mode=mode, enabled=True) for target in targets]
                    outputs = []
                    _set_switch_job(
                        active=True,
                        status="booting",
                        mode=mode,
                        target="GLOBAL",
                        started_at=int(time.time()),
                        finished_at=0,
                        error="",
                    )
                    try:
                        for target in updated_targets:
                            result = start_instance(target["id"], track_switch_job=False)
                            outputs.append(f"{target['id']}: {(result.get('output') or '')[-2400:]}")
                        clear_switch_failure(mode)
                        _set_switch_job(
                            active=False,
                            status="success",
                            mode=mode,
                            target="GLOBAL",
                            finished_at=int(time.time()),
                            error="",
                        )
                    except Exception as e:
                        write_switch_failure(mode, e)
                        _set_switch_job(
                            active=False,
                            status="failed",
                            mode=mode,
                            target="GLOBAL",
                            finished_at=int(time.time()),
                            error=str(e)[-12000:],
                        )
                        raise
                    log_audit("admin_switch_mode_global_single", instance="GLOBAL", mode=mode, targets=[row["id"] for row in updated_targets], stopped_instances=[row["id"] for row in stopped])
                    self.send_json({"ok": True, "instance": None, "mode": mode, "output": "\n\n".join(outputs)[-12000:], "stopped_instances": stopped, "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
                    return
                if instance_id == "GLOBAL" and scope_kind == "dual":
                    gpu_count = detect_gpu_count_runtime()
                    if gpu_count == 2:
                        rc, stop_msg = stop_legacy_global_instance()
                        result = run_switch(mode)
                        log_audit("admin_switch_mode_legacy_global", instance="GLOBAL", mode=mode, stop_rc=rc)
                        self.send_json({"ok": True, "instance": legacy_global_instance_snapshot(), "mode": mode, "output": (stop_msg + "\n" + result)[-12000:], "stopped_instances": ([{"id": "GLOBAL", "rc": rc, "output": stop_msg[-1200:]}] if stop_msg else []), "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
                        return
                    pair_targets = sequential_global_gpu_pairs(gpu_count)
                    if not pair_targets:
                        raise ValueError("At least two GPUs are required before applying a dual preset globally")
                    stopped = stop_overlapping_instances([idx for pair in pair_targets for idx in pair])
                    updated_targets = []
                    outputs = []
                    _set_switch_job(
                        active=True,
                        status="booting",
                        mode=mode,
                        target="GLOBAL",
                        started_at=int(time.time()),
                        finished_at=0,
                        error="",
                    )
                    try:
                        for pair in pair_targets:
                            target = save_pair_instance(pair, mode=mode, enabled=True)
                            target = update_instance(target["id"], mode=mode, enabled=True)
                            updated_targets.append(target)
                            result = start_instance(target["id"], track_switch_job=False)
                            outputs.append(f"{target['id']}: {(result.get('output') or '')[-2400:]}")
                        clear_switch_failure(mode)
                        _set_switch_job(
                            active=False,
                            status="success",
                            mode=mode,
                            target="GLOBAL",
                            finished_at=int(time.time()),
                            error="",
                        )
                    except Exception as e:
                        write_switch_failure(mode, e)
                        _set_switch_job(
                            active=False,
                            status="failed",
                            mode=mode,
                            target="GLOBAL",
                            finished_at=int(time.time()),
                            error=str(e)[-12000:],
                        )
                        raise
                    log_audit("admin_switch_mode_global_dual", instance="GLOBAL", mode=mode, targets=[row["id"] for row in updated_targets], stopped_instances=[row["id"] for row in stopped])
                    self.send_json({"ok": True, "instance": None, "mode": mode, "output": "\n\n".join(outputs)[-12000:], "stopped_instances": stopped, "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
                    return
                if instance_id == "GLOBAL" and scope_kind in {"multi", "global_only"}:
                    stop_msg = cleanup_vllm_containers()
                    result = run_switch(mode)
                    log_audit("admin_switch_mode_global", instance="GLOBAL", mode=mode)
                    self.send_json({"ok": True, "instance": None, "mode": mode, "output": (str(stop_msg) + "\n" + result)[-12000:], "stopped_instances": [], "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
                    return
                if instance_id:
                    target = get_instance(instance_id)
                    if not target:
                        raise ValueError(f"Unknown instance: {instance_id}")
                    valid_modes = DUAL_GPU_MODES if target.get("kind") == "dual" else SINGLE_GPU_MODES
                    if mode not in valid_modes:
                        raise ValueError("Preset type does not match the selected instance scope")
                    stopped = stop_overlapping_instances(target.get("gpu_indices") or [target.get("gpu_index")])
                    updated = update_instance(instance_id, mode=mode, enabled=True)
                    result = start_instance(updated["id"])
                    log_audit("admin_switch_mode", instance=updated["id"], mode=mode, stopped_instances=[row["id"] for row in stopped])
                    self.send_json({"ok": True, "instance": instance_snapshot(updated), "mode": mode, "output": result.get("output", ""), "stopped_instances": stopped, "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
                else:
                    if scope_kind in {"multi", "global_only"}:
                        stop_msg = cleanup_vllm_containers()
                        result = run_switch(mode)
                        log_audit("admin_switch_mode_global", instance="GLOBAL", mode=mode)
                        self.send_json({"ok": True, "instance": None, "mode": mode, "output": (str(stop_msg) + "\n" + result)[-12000:], "stopped_instances": [], "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
                        return
                    if detect_gpu_count_runtime() == 2 and not gpu_pairing_enabled():
                        rc, stop_msg = stop_vllm_container("legacy_dual_switch")
                        result = run_switch(mode)
                        log_audit("admin_switch_mode_legacy_global", instance="legacy", mode=mode, stop_rc=rc)
                        self.send_json({"ok": True, "instance": None, "mode": mode, "output": (stop_msg + "\n" + result)[-12000:], "stopped_instances": ([{"id": "legacy", "rc": rc, "output": stop_msg[-1200:]}] if stop_msg else []), "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
                        return
                    pairs = [inst for inst in read_instances_config() if inst.get("kind") == "dual"]
                    if len(pairs) != 1:
                        raise ValueError("Select a specific dual pair scope before applying a dual preset")
                    target = pairs[0]
                    stopped = stop_overlapping_instances(target.get("gpu_indices") or [target.get("gpu_index")])
                    updated = update_instance(target["id"], mode=mode, enabled=True)
                    result = start_instance(updated["id"])
                    log_audit("admin_switch_mode_pair_default", instance=updated["id"], mode=mode, stopped_instances=[row["id"] for row in stopped])
                    self.send_json({"ok": True, "instance": instance_snapshot(updated), "mode": mode, "output": result.get("output", ""), "stopped_instances": stopped, "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/rebuild-inventory":
            try:
                inventory = rebuild_runtime_inventory()
                log_audit("admin_runtime_inventory_rebuilt", models=len(inventory.get("models") or []), variants=len(inventory.get("variants") or []))
                self.send_json({"ok": True, "runtime_inventory": inventory, "models": inventory.get("models") or [], "variants": inventory.get("variants") or []})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/model-install":
            try:
                data = self.read_json_body()
                job = start_model_install_job(
                    data.get("model_id"),
                    data.get("variant_id"),
                    data.get("install_command"),
                )
                self.send_json({"ok": True, "model_install_job": job, "focus_log_source": "audit"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/benchmark":
            try:
                job = start_admin_task_job("benchmark")
                self.send_json({"ok": True, "admin_task_job": job, "focus_log_source": "audit"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/run-report":
            try:
                job = start_admin_task_job("report")
                self.send_json({"ok": True, "admin_task_job": job, "focus_log_source": "audit"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/update":
            try:
                data = self.read_json_body()
                result = start_self_update_job(data.get("scope"))
                self.send_json(result)
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/services":
            try:
                data = self.read_json_body()
                action = str(data.get("action") or "").strip().lower()
                service_id = str(data.get("service_id") or "").strip().lower()
                result = run_upstream_service_action(service_id, action)
                self.send_json({"ok": True, "result": result, "upstream_services": discover_upstream_services(force=True, max_age=0.0)})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/chat-stream":
            try:
                data = self.read_json_body()
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
                return
            stream_admin_chat_request(self, data)
            return
        if path == "/admin/chat":
            try:
                data = self.read_json_body()
                self.send_json(run_admin_chat_request(data))
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/chat-state":
            try:
                data = self.read_json_body()
                debug_audit(
                    "chat_state_post",
                    incoming_revision=data.get("revision") if isinstance(data, dict) else None,
                    incoming_active_conversation_id=(data.get("activeConversationId") if isinstance(data, dict) else ""),
                    incoming_conversation_count=len((data.get("conversations") or [])) if isinstance(data, dict) else 0,
                )
                self.send_json({"ok": True, "state": write_chat_state(data)})
            except Exception as e:
                debug_audit("chat_state_post_error", error=str(e))
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/chat-conversations":
            try:
                data = self.read_json_body()
                action = str(data.get("action") or "").strip().lower()
                if action != "delete":
                    raise ValueError("Invalid conversation action.")
                debug_audit("chat_conversation_action", action=action, conversation_id=data.get("conversation_id") or "")
                self.send_json(delete_chat_conversation(data.get("conversation_id") or ""))
            except Exception as e:
                debug_audit("chat_conversation_action_error", error=str(e))
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/chat-attachments":
            try:
                data = self.read_json_body()
                self.send_json({"ok": True, "attachment": save_chat_attachment(data)})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/debug-log":
            try:
                data = self.read_json_body()
                debug_audit(
                    f"ui_{str((data or {}).get('event') or 'event').strip().lower().replace(' ', '_')}",
                    source=str((data or {}).get("source") or "ui"),
                    fields=(data or {}).get("fields") if isinstance((data or {}).get("fields"), dict) else {},
                )
                self.send_json({"ok": True, "debug": DEBUG_LOGS})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/power":
            try:
                data = self.read_json_body()
                action = data.get("action")
                instance_id = data.get("instance_id")
                log_control(f"POWER action requested action={action} instance={instance_id}")
                if action == "active":
                    out = {"cpu": apply_cpu_active_power(), "gpu": apply_gpu_active_power()}
                elif action == "idle_clocks":
                    out = {"cpu": apply_cpu_idle_power(), "gpu": apply_gpu_idle_power()}
                elif action == "stop_container":
                    if is_legacy_global_instance_id(instance_id):
                        rc, msg = stop_legacy_global_instance()
                    else:
                        rc, msg = stop_runtime_scope(instance_id=instance_id, mode=data.get("mode"))
                    out = {"container_stop_rc": rc, "container_stop_output": msg, "cpu": apply_cpu_idle_power(), "gpu": apply_gpu_idle_power()}
                elif action == "start_instance":
                    out = start_legacy_global_instance() if is_legacy_global_instance_id(instance_id) else start_instance(instance_id)
                elif action == "restart_instance":
                    if is_legacy_global_instance_id(instance_id):
                        stop_legacy_global_instance()
                        out = start_legacy_global_instance()
                    else:
                        stop_vllm_container("manual_restart", instance_id=instance_id)
                        out = start_instance(instance_id)
                elif action == "toggle_enabled":
                    enabled = bool(data.get("enabled"))
                    if is_legacy_global_instance_id(instance_id) or (not instance_id and detect_gpu_count_runtime() == 2 and not gpu_pairing_enabled(gpu_count=2)):
                        instance_id = "GLOBAL"
                        out = {"instance": set_legacy_global_enabled(enabled)}
                    else:
                        inst = update_instance(instance_id, enabled=enabled)
                        out = {"instance": instance_snapshot(inst)}
                elif action == "disable_optimizations":
                    out = set_power_optimizations(False, instance_id=instance_id)
                elif action == "enable_optimizations":
                    out = set_power_optimizations(True, instance_id=instance_id)
                elif action == "fans_max":
                    out = {"fans": set_fan_max_toggle(True, instance_id=instance_id)}
                elif action == "fans_auto":
                    out = {"fans": set_fan_max_toggle(False, instance_id=instance_id)}
                else:
                    raise ValueError("Invalid power action")
                log_audit("admin_power_action", action=action, instance=instance_id)
                self.send_json({"ok": True, "action": action, "result": out, "power": power_status()})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/profile":
            try:
                data = self.read_json_body()
                profile_name = data.get("profile")
                instance_id = str(data.get("instance_id") or "").strip().upper()
                log_control(f"PROFILE request received name={profile_name} instance={instance_id or 'GLOBAL'}")
                out = apply_performance_profile(profile_name)
                log_audit("admin_profile", profile=profile_name, instance=instance_id or "GLOBAL")
                self.send_json({"ok": True, "profile": profile_name, "result": out, "power": power_status()})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/wol":
            try:
                data = self.read_json_body()
                out = wake_on_lan(data.get("mac") or None, data.get("broadcast") or None)
                log_audit("admin_wol", mac=data.get("mac") or "", broadcast=data.get("broadcast") or "")
                self.send_json({"ok": True, "result": out})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/presets":
            try:
                data = self.read_json_body()
                action = data.get("action")
                if action == "save":
                    catalog = save_custom_preset(data.get("name"), data.get("preset") or {})
                    log_audit("admin_preset_save", name=data.get("name"))
                elif action == "delete":
                    catalog = delete_custom_preset(data.get("name"))
                    log_audit("admin_preset_delete", name=data.get("name"))
                else:
                    raise ValueError("Invalid preset action")
                self.send_json({"ok": True, "presets": catalog})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/mcp":
            try:
                data = self.read_json_body()
                action = str(data.get("action") or "").strip().lower()
                rows = sanitize_mcp_servers(read_server_config().get("mcp_servers") or [])
                if action == "save":
                    row = {
                        "id": str(data.get("id") or "").strip() or secrets.token_hex(6),
                        "name": str(data.get("name") or "").strip() or "mcp-server",
                        "command": str(data.get("command") or "").strip(),
                        "enabled": bool(data.get("enabled", True)),
                    }
                    validate_mcp_server_row(row)
                    rows = [item for item in rows if str(item.get("id") or "") != row["id"]] + [row]
                    write_server_config({"mcp_servers": rows})
                    log_audit("admin_mcp_saved", server=row["id"], enabled=row["enabled"])
                elif action == "delete":
                    server_id = str(data.get("id") or "").strip()
                    rows = [item for item in rows if str(item.get("id") or "") != server_id]
                    write_server_config({"mcp_servers": rows})
                    close_removed_mcp_clients(rows)
                    log_audit("admin_mcp_deleted", server=server_id)
                elif action == "toggle":
                    server_id = str(data.get("id") or "").strip()
                    enabled = bool(data.get("enabled"))
                    for row in rows:
                        if str(row.get("id") or "") == server_id:
                            row["enabled"] = enabled
                            if enabled:
                                validate_mcp_server_row(row)
                            break
                    write_server_config({"mcp_servers": rows})
                    if not enabled:
                        close_removed_mcp_clients([row for row in rows if row.get("enabled")])
                    log_audit("admin_mcp_toggled", server=server_id, enabled=enabled)
                else:
                    raise ValueError("Invalid MCP action")
                self.send_json({"ok": True, "servers": list_mcp_server_statuses()})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/ui-config":
            try:
                data = self.read_json_body()
                cfg, changed = write_ui_config(data)
                self.send_json({"ok": True, "ui_config": cfg, "changed": changed})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/log-export":
            try:
                data = self.read_json_body()
                export_payload = export_selected_log(
                    source=data.get("source") or "docker",
                    instance_id=data.get("instance_id") or "",
                )
                upload = upload_text_to_share_host(
                    export_payload.get("text") or "",
                    filename=export_payload.get("file_name") or "club3090-log.txt",
                )
                log_audit(
                    "admin_log_export",
                    source=export_payload.get("source"),
                    instance=export_payload.get("instance_id"),
                    container=export_payload.get("container"),
                    provider=upload.get("provider"),
                    url=upload.get("url"),
                )
                self.send_json(
                    {
                        "ok": True,
                        "source": export_payload.get("source"),
                        "instance_id": export_payload.get("instance_id"),
                        "container": export_payload.get("container"),
                        "file_name": export_payload.get("file_name"),
                        "provider": upload.get("provider"),
                        "url": upload.get("url"),
                    }
                )
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/chat-export":
            try:
                data = self.read_json_body()
                export_payload = export_chat_conversation(data.get("conversation_id") or "")
                upload = upload_text_to_share_host(
                    export_payload.get("text") or "",
                    filename=export_payload.get("file_name") or "club3090-chat.md",
                )
                log_audit(
                    "admin_chat_export",
                    conversation_id=data.get("conversation_id") or "",
                    provider=upload.get("provider"),
                    url=upload.get("url"),
                )
                self.send_json(
                    {
                        "ok": True,
                        "conversation_id": data.get("conversation_id") or "",
                        "file_name": export_payload.get("file_name"),
                        "provider": upload.get("provider"),
                        "url": upload.get("url"),
                    }
                )
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/instances":
            try:
                data = self.read_json_body()
                action = str(data.get("action") or "").strip()
                if action == "save_pair":
                    instance = save_pair_instance(data.get("gpu_indices") or [], mode=data.get("mode"), enabled=data.get("enabled"))
                    log_audit("admin_pair_saved", instance=instance["id"], gpu_indices=instance.get("gpu_indices") or [], mode=instance.get("mode"))
                    self.send_json({"ok": True, "instance": instance_snapshot(instance), "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
                    return
                if action == "delete_pair":
                    instances = delete_pair_instance(data.get("instance_id"))
                    log_audit("admin_pair_deleted", instance=str(data.get("instance_id") or "").strip().upper())
                    self.send_json({"ok": True, "instances": instances, "running_dual_instances": running_dual_instance_snapshots()})
                    return
                raise ValueError("Invalid instances action")
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/users":
            try:
                data = self.read_json_body()
                action = str(data.get("action") or "").strip()
                if action == "save":
                    user, api_key = save_user_record(data.get("user") or {})
                    self.send_json({"ok": True, "user": user, "api_key": api_key, "users": list_users_public(), "groups": list_groups_public(), "server_config": read_server_config()})
                    return
                if action == "delete":
                    users = delete_user_record(data.get("name"))
                    self.send_json({"ok": True, "users": users, "groups": list_groups_public(), "server_config": read_server_config()})
                    return
                if action == "reset_key":
                    api_key, user = issue_api_key_for_user(safe_user_name(data.get("name")))
                    self.send_json({"ok": True, "user": user, "api_key": api_key, "users": list_users_public(), "groups": list_groups_public(), "server_config": read_server_config()})
                    return
                if action == "show_key":
                    api_key, user = show_api_key_for_user(safe_user_name(data.get("name")))
                    self.send_json({"ok": True, "user": user, "api_key": api_key})
                    return
                if action == "save_server_config":
                    before_cfg = read_server_config()
                    cfg_data = {}
                    if "allow_proxy_without_api_key" in data:
                        cfg_data["allow_proxy_without_api_key"] = bool(data.get("allow_proxy_without_api_key", True))
                    if "gpu_pairing_enabled" in data:
                        cfg_data["gpu_pairing_enabled"] = bool(data.get("gpu_pairing_enabled"))
                    cfg = write_server_config(cfg_data)
                    read_instances_config()
                    if cfg != before_cfg:
                        log_audit("admin_server_config", allow_proxy_without_api_key=cfg.get("allow_proxy_without_api_key", True), gpu_pairing_enabled=cfg.get("gpu_pairing_enabled"))
                    self.send_json({"ok": True, "server_config": cfg, "users": list_users_public(), "groups": list_groups_public()})
                    return
                raise ValueError("Invalid users action")
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/groups":
            try:
                data = self.read_json_body()
                action = str(data.get("action") or "").strip()
                if action == "save":
                    group = save_group_record(data.get("group") or {})
                    self.send_json({"ok": True, "group": group, "groups": list_groups_public(), "users": list_users_public(), "server_config": read_server_config()})
                    return
                if action == "delete":
                    groups = delete_group_record(data.get("name"))
                    self.send_json({"ok": True, "groups": groups, "users": list_users_public(), "server_config": read_server_config()})
                    return
                raise ValueError("Invalid groups action")
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/machine":
            try:
                data = self.read_json_body()
                action = data.get("action")
                if action == "reboot":
                    log_audit("admin_machine", action="reboot")
                    self.send_json({"ok": True, "action": "reboot", "message": "Reboot command accepted"})
                    threading.Thread(target=lambda: (time.sleep(1), subprocess.run(["systemctl", "reboot"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)), daemon=True).start()
                    return
                if action == "shutdown":
                    log_audit("admin_machine", action="shutdown")
                    self.send_json({"ok": True, "action": "shutdown", "message": "Shutdown command accepted"})
                    threading.Thread(target=lambda: (time.sleep(1), subprocess.run(["systemctl", "poweroff"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)), daemon=True).start()
                    return
                raise ValueError("Invalid machine action")
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        self.send_error(404)
    def stream_logs(self, parsed):
        params = parse_admin_query_params(parsed)
        requested = str(params.get("instance") or "").strip().upper()
        requested_source = str(params.get("source") or "docker").strip().lower()
        requested_service = str(params.get("service") or "").strip().lower()
        log_control(f"ADMIN log stream open source={requested_source} instance={requested or '-'} service={requested_service or '-'}")
        last_container = ""
        client_generation = -1
        client_seq = 0
        waiting_sent = False
        while True:
            resolved = resolve_log_source(requested_source, requested, requested_service)
            instance = resolved.get("instance")
            container = str(resolved.get("container") or "").strip()
            source_label = str(resolved.get("label") or requested_source or "source")
            if not container:
                try:
                    if not waiting_sent:
                        text = (
                            f"\n[log stream] {source_label} is no longer available; waiting for it to return...\n"
                            if last_container
                            else f"no active {source_label} log source found; waiting...\n"
                        )
                        log_control(f"ADMIN log stream waiting source={requested_source} instance={requested or '-'} service={requested_service or '-'} label={source_label}")
                        self.send_sse_event("append", {"text": text})
                        waiting_sent = True
                        last_container = ""
                    else:
                        self.send_sse_comment()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    return
                time.sleep(2)
                continue
            waiting_sent = False
            watcher = get_runtime_log_watcher(container)
            if watcher is None:
                time.sleep(1)
                continue
            if container != last_container:
                last_container = container
                client_generation = -1
                client_seq = 0
            try:
                watcher.wait_for_change(client_generation, client_seq, timeout=15)
                snapshot = watcher.snapshot()
                if snapshot["generation"] != client_generation:
                    self.send_sse_event("reset", {"text": snapshot["text"]})
                    client_generation = snapshot["generation"]
                    client_seq = snapshot["seq"]
                    continue
                update = watcher.collect_updates_since(client_generation, client_seq)
                if update["reset"]:
                    self.send_sse_event("reset", {"text": update["text"]})
                    client_generation = update["generation"]
                    client_seq = update["seq"]
                elif update["text"]:
                    self.send_sse_event("append", {"text": update["text"]})
                    client_seq = update["seq"]
                else:
                    self.send_sse_comment()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return
    def stream_text_file(self, path, empty_message="waiting...", initial_tail_lines=250):
        sent_reset = False
        offset = 0
        idle_since = time.time()
        while True:
            try:
                if not os.path.exists(path):
                    if not sent_reset:
                        self.send_sse_event("reset", {"text": str(empty_message or "waiting...").rstrip("\n") + "\n"})
                        sent_reset = True
                    else:
                        self.send_sse_comment()
                    time.sleep(2)
                    continue
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    if offset <= 0:
                        if int(initial_tail_lines) > 0:
                            lines = collections.deque(f, maxlen=int(initial_tail_lines))
                            text = "".join(lines)
                        else:
                            text = ""
                            f.seek(0, os.SEEK_END)
                        self.send_sse_event("reset", {"text": text or (str(empty_message or "waiting...").rstrip("\n") + "\n")})
                        offset = f.tell()
                        sent_reset = True
                        initial_tail_lines = 0
                        idle_since = time.time()
                    else:
                        try:
                            size_now = os.path.getsize(path)
                        except Exception:
                            size_now = offset
                        if size_now < offset:
                            offset = 0
                            sent_reset = False
                            continue
                        f.seek(offset)
                        chunk = f.read()
                        if chunk:
                            self.send_sse_event("append", {"text": chunk})
                            offset = f.tell()
                            idle_since = time.time()
                        elif time.time() - idle_since >= 15:
                            self.send_sse_comment()
                            idle_since = time.time()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return
            time.sleep(1)


class LocalApiHandler(CommonMixin, BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def require_local_access(self):
        client_ip = self.client_address[0] if self.client_address else ""
        if client_ip not in ("127.0.0.1", "::1"):
            log_audit("local_api_denied", reason="non_loopback", client=client_ip, path=self.path)
            self.send_json({"ok": False, "error": "Local API is loopback-only"}, 403)
            return False
        if not local_api_token_ok(self.headers.get("X-Club3090-Local-Token", "")):
            log_audit("local_api_denied", reason="invalid_token", client=client_ip, path=self.path)
            self.send_json({"ok": False, "error": "Missing or invalid local API token"}, 401)
            return False
        return True
    def do_GET(self):
        if not self.require_local_access():
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        params = parse_admin_query_params(parsed)
        if path == "/users":
            self.send_json({"ok": True, "users": list_users_public(), "groups": list_groups_public(), "server_config": read_server_config()})
            return
        if path == "/groups":
            self.send_json({"ok": True, "groups": list_groups_public(), "users": list_users_public(), "server_config": read_server_config()})
            return
        if path == "/server-config":
            self.send_json({"ok": True, "server_config": read_server_config()})
            return
        if path == "/audit-log":
            tail = int(params.get("tail") or 300)
            match_text = str(params.get("match") or "")
            case_sensitive = str(params.get("case_sensitive") or "").strip().lower() in {"1", "true", "yes", "on"}
            payload = query_text_log_file(AUDIT_LOG_FILE, tail_lines=tail, match_text=match_text, case_sensitive=case_sensitive)
            self.send_bytes(payload.encode("utf-8", errors="replace"), "text/plain; charset=utf-8")
            return
        if path == "/control-log":
            tail = int(params.get("tail") or 300)
            match_text = str(params.get("match") or "")
            case_sensitive = str(params.get("case_sensitive") or "").strip().lower() in {"1", "true", "yes", "on"}
            payload = query_text_log_file(CONTROL_LOG_FILE, tail_lines=tail, match_text=match_text, case_sensitive=case_sensitive)
            self.send_bytes(payload.encode("utf-8", errors="replace"), "text/plain; charset=utf-8")
            return
        self.send_error(404)
    def do_POST(self):
        if not self.require_local_access():
            return
        path = urlsplit(self.path).path
        try:
            data = self.read_json_body()
            if path == "/users":
                action = str(data.get("action") or "").strip()
                if action == "save":
                    user, api_key = save_user_record(data.get("user") or {})
                    self.send_json({"ok": True, "user": user, "api_key": api_key, "users": list_users_public(), "groups": list_groups_public()})
                    return
                if action == "delete":
                    users = delete_user_record(data.get("name"))
                    self.send_json({"ok": True, "users": users, "groups": list_groups_public()})
                    return
                if action == "reset_key":
                    api_key, user = issue_api_key_for_user(safe_user_name(data.get("name")))
                    self.send_json({"ok": True, "user": user, "api_key": api_key, "users": list_users_public(), "groups": list_groups_public()})
                    return
                raise ValueError("Invalid users action")
            if path == "/groups":
                action = str(data.get("action") or "").strip()
                if action == "save":
                    group = save_group_record(data.get("group") or {})
                    self.send_json({"ok": True, "group": group, "groups": list_groups_public(), "users": list_users_public()})
                    return
                if action == "delete":
                    groups = delete_group_record(data.get("name"))
                    self.send_json({"ok": True, "groups": groups, "users": list_users_public()})
                    return
                raise ValueError("Invalid groups action")
            if path == "/server-config":
                cfg = write_server_config(data or {})
                self.send_json({"ok": True, "server_config": cfg})
                return
            raise ValueError("Unknown local API path")
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

class ProxyHandler(CommonMixin, BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/":
            self.send_json({"ok": True, "service": "club3090-proxy", "base_path": "/v1"})
            return
        if parsed.path in {"/favicon.ico", "/robots.txt"}:
            self.send_bytes(b"", "text/plain; charset=utf-8", 204)
            return
        if parsed.path in {"/health", "/v1/health"}:
            self.send_json({
                "ok": True,
                "active_mode": active_mode(),
                "active_port": active_port(),
                "container": current_container(),
            })
            return
        instance_id, stripped = parse_instance_path(self.path)
        upstream_path, preset_name, cap = parse_preset_path(stripped)
        if not is_supported_proxy_path(upstream_path, self.command):
            self.send_json({"error": "Unsupported proxy path", "path": parsed.path}, 404)
            return
        self.forward(None, upstream_path, preset_name, cap, instance_id=instance_id)
    def do_POST(self):
        n = int(self.headers.get("content-length","0") or "0")
        body = self.rfile.read(n) if n else b""
        instance_id, stripped = parse_instance_path(self.path)
        upstream_path, preset_name, cap = parse_preset_path(stripped)
        if not is_supported_proxy_path(upstream_path, self.command):
            self.send_json({"error": "Unsupported proxy path", "path": urlsplit(self.path).path}, 404)
            return
        if preset_name and (upstream_path.startswith("/v1/chat/completions") or upstream_path.startswith("/v1/completions")):
            body = apply_preset(body, preset_name, cap)
        self.forward(body, upstream_path, preset_name, cap, instance_id=instance_id)
    def forward(self, body, upstream_path, preset_name, cap, instance_id=None):
        global last_request_finished_at
        start = time.time()
        status = None
        response_usage = {"tokens": 0, "input_tokens": 0, "output_tokens": 0, "tool_calls": 0}
        target = get_instance(instance_id) if instance_id else primary_instance()
        target_id = target["id"] if target else "legacy"
        target_metrics_key = str(target_id or "").strip().upper()
        request_usage = extract_request_usage(body) if body is not None and is_quota_counted_path(upstream_path) else {}
        auth_result = authorize_proxy_request(self.headers, instance_id, upstream_path, request_usage=request_usage)
        if auth_result[0] is False:
            _, code, payload = auth_result
            self.send_json(payload, code)
            return
        auth_context = auth_result[1]
        with metrics_lock:
            metrics["total_requests"] += 1
            metrics["active_requests"] += 1
            metrics["last_preset"] = preset_name or "raw"
            metrics["last_path"] = self.path
            target_request_metrics.setdefault(target_metrics_key, default_target_request_metrics())
        needs_model = upstream_path.startswith("/v1/models") or (body is not None and (upstream_path.startswith("/v1/chat/completions") or upstream_path.startswith("/v1/completions")))
        if needs_model:
            with metrics_lock:
                metrics["queued_requests"] += 1
                request_queue.append({"time": time.strftime("%H:%M:%S"), "path": self.path, "preset": preset_name or "raw", "instance": target_id})
            ensure_vllm_running_for_request(target["id"] if target else None)
            with metrics_lock:
                metrics["queued_requests"] = max(0, metrics["queued_requests"] - 1)
        url = f"http://127.0.0.1:{instance_runtime_port(target) if target else active_port()}" + upstream_path
        headers = {k:v for k,v in self.headers.items() if k.lower() not in HOP_HEADERS}
        for secret_header in ("Authorization", "authorization", "X-API-Key", "x-api-key", "api-key"):
            headers.pop(secret_header, None)
        if body is not None:
            headers["Content-Type"] = headers.get("Content-Type", "application/json")
        req = urllib.request.Request(url, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=None) as r:
                status = r.status
                self.send_response(r.status)
                for k,v in r.headers.items():
                    if k.lower() not in HOP_HEADERS:
                        self.send_header(k,v)
                self.send_header("X-Club3090-Instance", target_id)
                self.send_header("Connection","close")
                self.end_headers()
                if "text/event-stream" in r.headers.get("Content-Type","").lower():
                    with metrics_lock:
                        metrics["streaming_requests"] += 1
                first_chunk_at = None
                total_bytes = bytearray()
                while True:
                    chunk = r.read1(8192) if hasattr(r, "read1") else r.read(8192)
                    if not chunk:
                        break
                    if first_chunk_at is None:
                        first_chunk_at = time.time()
                    if len(total_bytes) < 2000000:
                        total_bytes.extend(chunk)
                    self.wfile.write(chunk)
                    self.wfile.flush()
                if first_chunk_at is not None:
                    toks = estimate_tokens_from_stream_bytes(bytes(total_bytes))
                    response_usage["output_tokens"] = max(int(response_usage.get("output_tokens") or 0), int(toks or 0))
                    response_usage["tokens"] = max(int(response_usage.get("tokens") or 0), int(toks or 0))
                    ttft = round(first_chunk_at - start, 3)
                    gen_time = max(0.001, time.time() - first_chunk_at)
                    with metrics_lock:
                        metrics["last_ttft_s"] = ttft
                        metrics["last_estimated_tokens"] = toks
                        metrics["last_tokens_per_second"] = round(toks / gen_time, 2) if toks else None
                        target_row = dict(target_request_metrics.get(target_metrics_key) or default_target_request_metrics())
                        target_row["last_ttft_s"] = ttft
                        target_row["last_estimated_tokens"] = toks
                        target_row["last_tokens_per_second"] = round(toks / gen_time, 2) if toks else None
                        target_request_metrics[target_metrics_key] = target_row
                parsed_usage = extract_response_usage(bytes(total_bytes))
                for key in ("tokens", "input_tokens", "output_tokens", "tool_calls"):
                    response_usage[key] = max(int(response_usage.get(key) or 0), int(parsed_usage.get(key) or 0))
        except urllib.error.HTTPError as e:
            status = e.code
            payload = e.read()
            parsed_usage = extract_response_usage(payload)
            for key in ("tokens", "input_tokens", "output_tokens", "tool_calls"):
                response_usage[key] = max(int(response_usage.get(key) or 0), int(parsed_usage.get(key) or 0))
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type","text/plain"))
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection","close")
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:
            status = 502
            # Best-effort self-healing failover for stopped/crashed containers.
            # Only attempt for model discovery/completion paths, and only once.
            if upstream_path.startswith("/v1/models") or upstream_path.startswith("/v1/chat/completions") or upstream_path.startswith("/v1/completions"):
                try:
                    with metrics_lock:
                        metrics["failovers"] += 1
                    log_control(f"PROXY failover attempt instance={target_id} mode={(target['mode'] if target else active_mode())} error={e}")
                    if target:
                        start_instance(target["id"])
                    else:
                        run_switch(active_mode())
                    retry_url = f"http://127.0.0.1:{instance_runtime_port(target) if target else active_port()}" + upstream_path
                    retry_req = urllib.request.Request(retry_url, data=body, headers=headers, method=self.command)
                    with urllib.request.urlopen(retry_req, timeout=None) as r2:
                        status = r2.status
                        self.send_response(r2.status)
                        for k,v in r2.headers.items():
                            if k.lower() not in HOP_HEADERS:
                                self.send_header(k,v)
                        self.send_header("X-Club3090-Instance", target_id)
                        self.send_header("Connection","close")
                        self.end_headers()
                        retry_bytes = bytearray()
                        while True:
                            chunk = r2.read1(8192) if hasattr(r2, "read1") else r2.read(8192)
                            if not chunk:
                                break
                            if len(retry_bytes) < 2000000:
                                retry_bytes.extend(chunk)
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        parsed_retry_usage = extract_response_usage(bytes(retry_bytes))
                        for key in ("tokens", "input_tokens", "output_tokens", "tool_calls"):
                            response_usage[key] = max(int(response_usage.get(key) or 0), int(parsed_retry_usage.get(key) or 0))
                        if int(response_usage.get("output_tokens") or 0) == 0:
                            retry_toks = estimate_tokens_from_stream_bytes(bytes(retry_bytes))
                            response_usage["output_tokens"] = max(int(response_usage.get("output_tokens") or 0), int(retry_toks or 0))
                            response_usage["tokens"] = max(int(response_usage.get("tokens") or 0), int(retry_toks or 0))
                        return
                except Exception as failover_error:
                    log_control(f"PROXY failover failed: {failover_error}")
            self.send_json({"error": str(e), "active_mode": active_mode(), "active_port": active_port()}, 502)
        finally:
            latency = round(time.time() - start, 3)
            prompt_tokens = max(int(request_usage.get("input_tokens") or 0), int(response_usage.get("input_tokens") or 0))
            output_tokens = max(int(response_usage.get("output_tokens") or 0), max(0, int(response_usage.get("tokens") or 0) - int(prompt_tokens)))
            total_tokens = max(int(response_usage.get("tokens") or 0), int(prompt_tokens) + int(output_tokens))
            tool_calls = int(response_usage.get("tool_calls") or 0)
            log_metrics = runtime_log_metrics_for_container(target.get("container"), force=True) if target and target.get("container") else {}
            display_tps = first_defined(log_metrics.get("generation_tps"), None)
            if display_tps not in (None, "", 0, 0.0):
                try:
                    display_tps = round(float(display_tps), 2)
                except Exception:
                    display_tps = None
            else:
                display_tps = None
            with metrics_lock:
                metrics["active_requests"] = max(0, metrics["active_requests"] - 1)
                if metrics["active_requests"] <= 0:
                    last_request_finished_at = time.time()
                metrics["completed_requests"] += 1
                if status is None or int(status) >= 400:
                    metrics["failed_requests"] += 1
                metrics["last_latency_s"] = latency
                metrics["last_status"] = status
                if display_tps not in (None, "", 0, 0.0):
                    metrics["last_tokens_per_second"] = display_tps
                recent_requests.appendleft({"time":time.strftime("%H:%M:%S"),"status":status,"latency_s":latency,"preset":preset_name or "raw","path":self.path,"upstream":upstream_path,"instance":target_id,"user":auth_context.get("user_name") or "anonymous"})
                target_row = dict(target_request_metrics.get(target_metrics_key) or default_target_request_metrics())
                target_row["last_status"] = status
                target_row["last_latency_s"] = latency
                if display_tps not in (None, "", 0, 0.0):
                    target_row["last_tokens_per_second"] = display_tps
                target_row["last_input_tokens"] = prompt_tokens
                target_row["last_output_tokens"] = output_tokens
                target_row["last_total_tokens"] = total_tokens
                target_row["last_tool_calls"] = tool_calls
                target_row["last_preset"] = preset_name or "raw"
                target_row["last_path"] = self.path
                target_row["last_request_at"] = int(time.time())
                target_request_metrics[target_metrics_key] = target_row
            record_user_usage(auth_context.get("user_name"), auth_context.get("count_request", False), status, request_usage, response_usage, latency)
            log_control(f"REQ user={(auth_context.get('user_name') or 'anonymous')} instance={target_id} status={status} latency={latency}s preset={preset_name or 'raw'} path={self.path} upstream={upstream_path} input_tokens={prompt_tokens} output_tokens={output_tokens} total_tokens={total_tokens} tool_calls={tool_calls}")

def build_server(port, handler, bind="0.0.0.0"):
    server = ThreadingHTTPServer((bind, port), handler)
    server.daemon_threads = True
    return server

def serve(server, label="server"):
    sock = None
    try:
        sock = server.socket.getsockname()
    except Exception:
        sock = ("?", "?")
    log_control(f"{label} listening on {sock[0]}:{sock[1]}")
    server.serve_forever()

def startup_power_primer():
    try:
        apply_cpu_active_power()
    except Exception as e:
        log_control(f"STARTUP cpu power primer error: {e}")
    try:
        apply_gpu_active_power(skip_fans=True)
    except Exception as e:
        log_control(f"STARTUP gpu power primer error: {e}")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--audit-log":
        emit_cli_log_query(AUDIT_LOG_FILE, sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--control-log":
        emit_cli_log_query(CONTROL_LOG_FILE, sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--refresh-docker-logrotate":
        ok = refresh_docker_logrotate_config()
        print(json.dumps({"ok": bool(ok), "path": DOCKER_LOGROTATE_FILE, "retention_days": max(1, int(DOCKER_LOG_RETENTION_DAYS or 7))}))
        return
    os.makedirs(CONTROL_DIR, exist_ok=True)
    os.makedirs(INSTANCES_DIR, exist_ok=True)
    write_server_config(read_server_config())
    ensure_local_api_token()
    # Hard fail early if an update somehow produced an incomplete control script.
    # This specifically guards the proxy/autostart path that depends on port_open().
    if not callable(globals().get("port_open")):
        raise RuntimeError("internal install error: port_open() is not defined")
    load_runtime_inventory(force=not os.path.exists(RUNTIME_INVENTORY_FILE), rebuild_if_missing=True)
    if len(sys.argv) > 1 and sys.argv[1] == "--rebuild-inventory":
        rebuilt = rebuild_runtime_inventory()
        print(json.dumps({"ok": True, "models": len(rebuilt.get("models") or []), "variants": len(rebuilt.get("variants") or [])}))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--boot-enabled-instances":
        boot_enabled_instances()
        return
    if resolve_variant_spec(DEFAULT_MODE) and read_active_mode_file() is None:
        write_active_mode(DEFAULT_MODE)
    read_instances_config()
    log_control("control service starting")
    try:
        build_series_point()
    except Exception as e:
        log_control(f"initial metrics snapshot error: {e}")
    try:
        refresh_status_snapshot()
    except Exception as e:
        log_control(f"initial status snapshot error: {e}")
    refresh_docker_logrotate_config()
    threading.Thread(target=idle_watchdog, daemon=True).start()
    threading.Thread(target=metrics_collector, daemon=True).start()
    threading.Thread(target=status_snapshot_collector, daemon=True).start()
    threading.Thread(target=docker_logrotate_refresher, daemon=True).start()
    cfg = read_server_config()
    admin_server = build_server(ADMIN_BIND_PORT, AdminHandler, ADMIN_BIND_HOST)
    if cfg.get("local_api_enabled", False):
        local_api_port = int(cfg.get("local_api_port", LOCAL_API_PORT))
        local_api_server = build_server(local_api_port, LocalApiHandler, "127.0.0.1")
        threading.Thread(target=serve, args=(local_api_server, "local-api"), daemon=True).start()
    proxy_server = build_server(PROXY_BIND_PORT, ProxyHandler, PROXY_BIND_HOST)
    threading.Thread(target=serve, args=(proxy_server, "proxy"), daemon=True).start()
    threading.Thread(target=startup_power_primer, daemon=True).start()
    serve(admin_server, "admin")

if __name__ == "__main__":
    main()
