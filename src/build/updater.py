#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import subprocess
import tempfile
import threading
import time
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def write_json_atomic(path, payload):
    ensure_dir()
    fd, temporary = tempfile.mkstemp(prefix=".self-update-", dir=CONTROL_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


CONTROL_DIR = os.environ.get("CLUB3090_CONTROL_DIR", "/var/lib/club3090-control")
SCRIPT_VERSION = os.environ.get("CLUB3090_SCRIPT_VERSION", "unknown")
AUDIT_LOG_FILE = os.path.join(CONTROL_DIR, "audit.log")
UPDATE_LOG_FILE = os.path.join(CONTROL_DIR, "self-update.log")
UPDATE_STATE_FILE = os.path.join(CONTROL_DIR, "self-update-state.json")
UPDATE_SECRET_FILE = os.path.join(CONTROL_DIR, "self-update-secret")
UPDATE_RELOAD_FLAG_FILE = os.path.join(CONTROL_DIR, "self-update-reload-updater")
REMOTE_UPDATE_REPO_URL = os.environ.get(
    "CLUB3090_SELF_UPDATE_REPO_URL",
    "__CLUB3090_SELF_UPDATE_REPO_URL__",
)
REMOTE_UPDATE_REF = os.environ.get("CLUB3090_SELF_UPDATE_REF", "__CLUB3090_SELF_UPDATE_REF__")
REMOTE_UPDATE_BRANCH = os.environ.get("CLUB3090_SELF_UPDATE_BRANCH", "__CLUB3090_SELF_UPDATE_BRANCH__")
REMOTE_UPDATE_RAW_URL_TEMPLATE = os.environ.get(
    "CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE",
    "__CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE__",
)
UPDATER_BIND_HOST = os.environ.get("CLUB3090_UPDATER_BIND_HOST", "127.0.0.1")
UPDATER_BIND_PORT = int(os.environ.get("CLUB3090_UPDATER_BIND_PORT", "18010") or "18010")
CONTROL_ADMIN_BIND_PORT = int(os.environ.get("CLUB3090_ADMIN_BIND_PORT", "8008") or "8008")
HTTPS_ENABLED = str(os.environ.get("CLUB3090_HTTPS_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
SERVER_CONFIG_FILE = os.path.join(CONTROL_DIR, "server_config.json")
SERVER_DIR = Path(os.environ.get("CLUB3090_SERVER_DIR") or Path(__file__).resolve().parents[2]).resolve()

state_lock = threading.Lock()
state = {
    "active": False,
    "status": "idle",
    "scope": "",
    "label": "",
    "command": "",
    "started_at": 0,
    "finished_at": 0,
    "return_code": None,
    "summary": "idle",
    "token": "",
    "log_file": UPDATE_LOG_FILE,
    "script_version": SCRIPT_VERSION,
    "ui_ack_token": "",
    "ui_ack_at": 0,
}


def ensure_dir():
    os.makedirs(CONTROL_DIR, exist_ok=True)


def write_json_atomic(path, payload):
    ensure_dir()
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
    os.replace(tmp, path)


def load_state():
    global state
    try:
        with open(UPDATE_STATE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            state.update(payload)
    except Exception:
        pass


def redact_state(snapshot):
    clean = dict(snapshot or {})
    clean.pop("internal_error", None)
    return clean


def sync_state_from_disk():
    try:
        with open(UPDATE_STATE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    with state_lock:
        state.update(payload)


def snapshot_state():
    sync_state_from_disk()
    with state_lock:
        snapshot = redact_state(dict(state))
    snapshot["repository_revision"] = repository_revision()
    snapshot["update_instructions"] = f"cd {shlex.quote(str(SERVER_DIR))} && git pull && sudo ./install.sh"
    return snapshot


def set_state(**changes):
    with state_lock:
        state.update(changes)
        snapshot = dict(state)
    write_json_atomic(UPDATE_STATE_FILE, snapshot)
    return redact_state(snapshot)


def append_line(path, text):
    ensure_dir()
    line = str(text or "")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line.rstrip("\n") + "\n")


def read_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, type(default)) else default
    except Exception:
        return default
def repository_revision():
    try:
        result = subprocess.run(
            ["git", "-C", str(SERVER_DIR), "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def read_systemd_unit_environment(unit_name):
    try:
        result = subprocess.run(
            ["systemctl", "show", unit_name, "--property=Environment", "--value"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception:
        return {}
    if result.returncode != 0:
        return {}
    payload = str(result.stdout or "").strip()
    if not payload:
        return {}
    env = {}
    for token in shlex.split(payload):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = str(key or "").strip()
        if key:
            env[key] = value
    return env


def current_server_https_enabled():
    config = read_json_file(SERVER_CONFIG_FILE, {})
    if isinstance(config, dict) and "https_enabled" in config:
        return bool(config.get("https_enabled"))
    return HTTPS_ENABLED


def current_control_admin_bind_port():
    env = read_systemd_unit_environment("club3090-control.service")
    try:
        return int(str(env.get("CLUB3090_ADMIN_BIND_PORT") or "").strip() or CONTROL_ADMIN_BIND_PORT)
    except Exception:
        return CONTROL_ADMIN_BIND_PORT


def should_wait_for_caddy():
    if not current_server_https_enabled():
        return False
    unit_path = "/etc/systemd/system/club3090-caddy.service"
    return os.path.exists(unit_path)


def append_update_log(text, mirror_audit=True):
    append_line(UPDATE_LOG_FILE, text)
    if mirror_audit:
        append_line(AUDIT_LOG_FILE, text)


def reset_update_log():
    ensure_dir()
    with open(UPDATE_LOG_FILE, "w", encoding="utf-8") as handle:
        handle.write("")


def tail_text(path, tail_lines=4000):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
        return "".join(lines[-max(1, int(tail_lines or 4000)):])
    except Exception:
        return ""


def ensure_secret():
    ensure_dir()
    try:
        if os.path.exists(UPDATE_SECRET_FILE):
            with open(UPDATE_SECRET_FILE, "r", encoding="utf-8") as handle:
                token = handle.read().strip()
            if token:
                return token
    except Exception:
        pass
    token = secrets.token_urlsafe(32)
    with open(UPDATE_SECRET_FILE, "w", encoding="utf-8") as handle:
        handle.write(token + "\n")
    try:
        os.chmod(UPDATE_SECRET_FILE, 0o600)
    except Exception:
        pass
    return token


def is_loopback_client(handler):
    client = handler.client_address[0] if handler.client_address else ""
    return client in {"127.0.0.1", "::1", "::ffff:127.0.0.1"}


def valid_request_secret(handler):
    supplied = str(handler.headers.get("X-Club3090-Update-Secret", "") or "").strip()
    expected = ensure_secret()
    return bool(supplied) and bool(expected) and secrets.compare_digest(supplied, expected)


def shell_single_quote(value):
    return "'" + str(value or "").replace("'", "'\"'\"'") + "'"


def update_source_file():
    return os.path.join(CONTROL_DIR, "self-update-source.json")


def load_update_source():
    payload = read_json_file(update_source_file(), {})
    try:
        if not isinstance(payload, dict):
            raise ValueError("invalid source record")
        kind, name = normalized_version(payload.get("version_kind", "branch"), payload.get("version_name", REMOTE_UPDATE_BRANCH))
        cached_sha = str(payload.get("cached_sha") or "").lower()
        applied_sha = str(payload.get("applied_sha") or "").lower()
        if cached_sha and not re.fullmatch(r"[0-9a-f]{40}", cached_sha):
            raise ValueError("invalid cached SHA")
        if applied_sha and not re.fullmatch(r"[0-9a-f]{40}", applied_sha):
            raise ValueError("invalid applied SHA")
        cached_at = int(payload.get("cached_at") or 0)
        return {
            "version_kind": kind, "version_name": name,
            "cached_sha": cached_sha,
            "cached_script_version": str(payload.get("cached_script_version") or ""),
            "cached_at": cached_at, "applied_sha": applied_sha,
        }
    except (TypeError, ValueError, subprocess.TimeoutExpired):
        return {
            "version_kind": "branch", "version_name": REMOTE_UPDATE_BRANCH,
            "cached_sha": "", "cached_script_version": "", "cached_at": 0,
            "applied_sha": "",
        }


def write_update_source(payload):
    write_json_atomic(update_source_file(), payload)


def normalized_version(kind, name):
    kind = str(kind or "").strip().lower()
    name = str(name or "").strip()
    if kind not in {"branch", "tag"} or not name or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise ValueError("Invalid branch or tag")
    ref = f"refs/heads/{name}" if kind == "branch" else f"refs/tags/{name}"
    result = subprocess.run(["git", "check-ref-format", ref], capture_output=True, text=True, check=False, timeout=10)
    if result.returncode != 0:
        raise ValueError("Invalid branch or tag name")
    return kind, name


def build_update_command(operation, scope_name="controller", target_commit="", version_kind="", version_name=""):
    raise ValueError(f"Automatic updates are disabled. Update the checkout manually: cd {shlex.quote(str(SERVER_DIR))} && git pull && sudo ./install.sh")



def wait_for_systemd_unit(unit_name, timeout=120):
    deadline = time.time() + max(5.0, float(timeout or 120))
    while time.time() < deadline:
        result = subprocess.run(
            ["systemctl", "is-active", unit_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0 and str(result.stdout or "").strip() == "active":
            return True
        time.sleep(1.0)
    return False


def wait_for_admin_http(timeout=120):
    deadline = time.time() + max(5.0, float(timeout or 120))
    admin_bind_port = current_control_admin_bind_port()
    url = f"http://127.0.0.1:{admin_bind_port}/admin"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                if int(getattr(response, "status", 200) or 200) >= 200:
                    return True
        except urllib.error.HTTPError as exc:
            if int(getattr(exc, "code", 0) or 0) in {200, 302, 401, 403}:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False

def maybe_reload_updater():
    if not os.path.exists(UPDATE_RELOAD_FLAG_FILE):
        return
    try:
        os.remove(UPDATE_RELOAD_FLAG_FILE)
    except Exception:
        pass
    subprocess.Popen(
        [
            "bash",
            "-lc",
            "sleep 5; systemctl restart club3090-updater.service >/dev/null 2>&1 || true",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def finalize_job(return_code, operation):
    if int(return_code or 0) == 0 and operation == "upgrade":
        control_ready = wait_for_systemd_unit("club3090-control.service", timeout=180)
        http_ready = wait_for_admin_http(timeout=120)
        summary = "upgrade finished successfully" if control_ready and http_ready else "upgrade finished but readiness checks timed out"
        status = "completed" if control_ready else "degraded"
    elif int(return_code or 0) == 0:
        summary, status = "update staged in local cache", "completed"
    else:
        summary, status = f"update failed with return code {return_code}", "failed"
    source_state = load_update_source()
    set_state(
        active=False, status=status, finished_at=int(time.time()),
        return_code=int(return_code or 0), summary=summary,
        script_version=SCRIPT_VERSION,
        version_kind=source_state["version_kind"],
        version_name=source_state["version_name"],
        cached_sha=source_state["cached_sha"],
        pending_upgrade=bool(source_state["cached_sha"] and source_state["cached_sha"] != source_state["applied_sha"]),
    )
    append_update_log(f"[self-update service] {summary}")
    if operation == "upgrade":
        maybe_reload_updater()


def run_update_job(scope_name, label, command, source, operation):
    append_update_log(f"[self-update service] starting {label} via {source}")
    append_update_log(f"[self-update service] command: {command}")
    rc = 1
    try:
        proc = subprocess.Popen(
            ["bash", "-lc", command], cwd="/",
            env={**os.environ, "CLUB3090_RUNNING_FROM_UPDATER": "1"},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            append_update_log(str(raw_line or "").rstrip("\n"))
        rc = int(proc.wait())
        append_update_log(f"[self-update service] command exited with rc={rc}")
    except Exception as exc:
        append_update_log(f"[self-update service] launcher error: {exc}")
        rc = 1
    if rc == 0 and operation == "upgrade":
        source_state = load_update_source()
        source_state["applied_sha"] = source_state["cached_sha"]
        write_update_source(source_state)
    finalize_job(rc, operation)

def start_update(operation, scope_name="controller", target_commit="", version_kind="", version_name=""):
    operation = str(operation or "").strip().lower()
    with state_lock:
        if state.get("active"):
            raise RuntimeError("A self-update job is already running")
    normalized, label, command, source, target_commit = build_update_command(
        operation, scope_name=scope_name, target_commit=target_commit,
        version_kind=version_kind, version_name=version_name,
    )
    source_state = load_update_source()
    if operation == "change_version":
        return {"ok": True, "operation": operation, "self_update_source": source_state}
    token = secrets.token_urlsafe(24)
    reset_update_log()
    now = int(time.time())
    snapshot = set_state(
        active=True, status="running", operation=operation, scope=normalized,
        label=label, command=command, started_at=now, finished_at=0,
        return_code=None, summary=f"{label} queued", token=token,
        log_file=UPDATE_LOG_FILE, script_version=SCRIPT_VERSION,
        target_commit=target_commit, version_kind=source_state["version_kind"],
        version_name=source_state["version_name"], cached_sha=source_state["cached_sha"],
        pending_upgrade=bool(source_state["cached_sha"] and source_state["cached_sha"] != source_state["applied_sha"]),
        ui_ack_token="", ui_ack_at=0,
    )
    append_update_log(f"[self-update service] queued {label} operation={operation} version={source_state['version_kind']}:{source_state['version_name']}")
    worker = threading.Thread(
        target=run_update_job,
        args=(normalized, label, command, source, operation),
        name=f"club3090-self-update-{operation}",
        daemon=True,
    )
    worker.start()
    return {
        **snapshot, "ok": True,
        "stream_url": f"/admin/update-stream?token={token}&tail=4000",
        "status_url": f"/admin/update-status?token={token}",
        "focus_log_source": "update",
    }
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def send_json(self, payload, code=200):
        raw = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_sse_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def sse(self, event_name, payload):
        body = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(f"event: {event_name}\ndata: {body}\n\n".encode("utf-8"))
        self.wfile.flush()

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8", errors="replace") or "{}")

    def token_ok(self, params):
        supplied = ""
        if isinstance(params, dict):
            supplied = str((params.get("token") or [""])[0] or "").strip()
        current = snapshot_state()
        expected = str(current.get("token") or "").strip()
        return bool(supplied) and bool(expected) and secrets.compare_digest(supplied, expected)

    def do_GET(self):
        parsed = urlsplit(self.path)
        params = parse_qs(parsed.query or "", keep_blank_values=True)
        if parsed.path == "/healthz":
            self.send_json({"ok": True, "service": "club3090-updater", "script_version": SCRIPT_VERSION})
            return
        if parsed.path == "/admin/update-status":
            if not self.token_ok(params):
                self.send_json({"ok": False, "error": "invalid update token"}, 403)
                return
            self.send_json({"ok": True, **snapshot_state()})
            return
        if parsed.path == "/admin/update-stream":
            if not self.token_ok(params):
                self.send_json({"ok": False, "error": "invalid update token"}, 403)
                return
            tail_lines = int(str((params.get("tail") or ["4000"])[0] or "4000"))
            self.send_sse_headers()
            self.sse("reset", {"text": tail_text(UPDATE_LOG_FILE, tail_lines=tail_lines)})
            self.sse("status", snapshot_state())
            last_size = os.path.getsize(UPDATE_LOG_FILE) if os.path.exists(UPDATE_LOG_FILE) else 0
            last_ping = time.time()
            while True:
                try:
                    if os.path.exists(UPDATE_LOG_FILE):
                        current_size = os.path.getsize(UPDATE_LOG_FILE)
                        if current_size < last_size:
                            last_size = 0
                            self.sse("reset", {"text": tail_text(UPDATE_LOG_FILE, tail_lines=tail_lines)})
                        elif current_size > last_size:
                            with open(UPDATE_LOG_FILE, "r", encoding="utf-8", errors="replace") as handle:
                                handle.seek(last_size)
                                chunk = handle.read()
                            last_size = current_size
                            if chunk:
                                self.sse("append", {"text": chunk})
                    snapshot = snapshot_state()
                    if time.time() - last_ping >= 5.0:
                        self.sse("status", snapshot)
                        last_ping = time.time()
                    if not snapshot.get("active"):
                        self.sse("complete", snapshot)
                        break
                    time.sleep(0.5)
                except (BrokenPipeError, ConnectionResetError):
                    break
                except Exception as exc:
                    self.sse("append", {"text": f"[self-update service] stream error: {exc}\n"})
                    break
            return
        self.send_json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/admin/update-ack":
            try:
                payload = self.read_json()
                supplied = str(payload.get("token") or "").strip()
                snapshot = snapshot_state()
                expected = str(snapshot.get("token") or "").strip()
                if (
                    not supplied
                    or not expected
                    or not secrets.compare_digest(supplied, expected)
                    or not snapshot.get("active")
                ):
                    self.send_json({"ok": False, "error": "invalid update token"}, 403)
                    return
                acknowledged = set_state(
                    ui_ack_token=expected,
                    ui_ack_at=int(time.time()),
                )
                self.send_json({"ok": True, "ui_ack_at": acknowledged.get("ui_ack_at")})
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, 500)
            return
        if parsed.path != "/start":
            self.send_json({"ok": False, "error": "not found"}, 404)
            return
        if not is_loopback_client(self) or not valid_request_secret(self):
            self.send_json({"ok": False, "error": "forbidden"}, 403)
            return
        try:
            payload = self.read_json()
            result = start_update(payload.get("operation"), payload.get("scope"), payload.get("target_commit"), payload.get("version_kind"), payload.get("version_name"))
            self.send_json(result)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, 500)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        print(json.dumps({
            "repository_revision": repository_revision(),
            "update_instructions": f"cd {shlex.quote(str(SERVER_DIR))} && git pull && sudo ./install.sh",
            "automatic_updates": False,
        }, ensure_ascii=False))
        return
    ensure_dir()
    ensure_secret()
    load_state()
    server = ThreadingHTTPServer((UPDATER_BIND_HOST, UPDATER_BIND_PORT), Handler)
    server.serve_forever()

if __name__ == "__main__":
    main()
