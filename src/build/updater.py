#!/usr/bin/env python3
from __future__ import annotations

import json
import os
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
    snapshot["update_instructions"] = "System Update fast-forwards clean tracking branches in both Club-3090 checkouts, rebuilds the Model DB, and restarts managed services."
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



def build_update_command(operation, scope_name="controller"):
    operation = str(operation or "").strip().lower()
    scope = str(scope_name or "").strip().lower()
    if operation != "update":
        raise ValueError("Only the System Update operation is supported")
    if scope != "club3090":
        raise ValueError("System Update requires the Club-3090 scope")
    upstream_dir = str(os.environ.get("CLUB3090_DIR") or "").strip()
    if not upstream_dir:
        raise ValueError("CLUB3090_DIR is required for System Update")
    server_dir = str(SERVER_DIR)
    control_dir = CONTROL_DIR
    quoted_server = shlex.quote(server_dir)
    quoted_upstream = shlex.quote(upstream_dir)
    quoted_control = shlex.quote(control_dir)
    command = f"""set -euo pipefail
SERVER_DIR={quoted_server}
UPSTREAM_DIR={quoted_upstream}
CONTROL_DIR={quoted_control}
command -v runuser >/dev/null 2>&1 || {{ echo "System Update requires runuser to access Git worktrees as their owners" >&2; exit 1; }}
git_as_repo_owner() {{
  local repo="$1" repo_uid passwd_entry repo_home
  shift
  repo_uid="$(stat -c '%u' -- "$repo")" || {{ echo "Unable to determine Git worktree owner: $repo" >&2; return 1; }}
  passwd_entry="$(getent passwd "$repo_uid")" || {{ echo "No account found for Git worktree owner uid $repo_uid ($repo)" >&2; return 1; }}
  repo_home="$(printf '%s\\n' "$passwd_entry" | cut -d: -f6)"
  runuser --user "$repo_uid" -- env HOME="$repo_home" git -C "$repo" "$@"
}}
for repo in "$SERVER_DIR" "$UPSTREAM_DIR"; do
  git_as_repo_owner "$repo" rev-parse --show-toplevel >/dev/null || {{
    echo "Not a Git worktree or inaccessible as its owner: $repo" >&2
    exit 1
  }}
done
for repo in "$SERVER_DIR" "$UPSTREAM_DIR"; do
  if ! worktree_status="$(git_as_repo_owner "$repo" status --porcelain)"; then
    echo "Unable to inspect Git worktree status: $repo" >&2
    exit 1
  fi
  if [[ -n "$worktree_status" ]]; then
    echo "Refusing System Update: checkout has local changes: $repo" >&2
    exit 1
  fi
  git_as_repo_owner "$repo" rev-parse --abbrev-ref --symbolic-full-name '@{{u}}' >/dev/null || {{
    echo "Refusing System Update: checkout has no upstream tracking branch: $repo" >&2
    exit 1
  }}
done
echo "[system-update] Fast-forwarding Club-3090 Server checkout"
git_as_repo_owner "$SERVER_DIR" fetch --prune origin
git_as_repo_owner "$SERVER_DIR" merge --ff-only '@{{u}}'
echo "[system-update] Fast-forwarding upstream Club-3090 checkout"
git_as_repo_owner "$UPSTREAM_DIR" fetch --prune origin
git_as_repo_owner "$UPSTREAM_DIR" merge --ff-only '@{{u}}'
echo "[system-update] Rebuilding Model DB"
cd "$SERVER_DIR/src"
CLUB3090_CONTROL_DIR="$CONTROL_DIR" CLUB3090_DIR="$UPSTREAM_DIR" PYTHONPATH="$SERVER_DIR/src" python3 -m control.http_server --rebuild-inventory
echo "[system-update] Reinstalling and restarting services"
CLUB3090_RUNNING_FROM_UPDATER=1 CLUB3090_CONTROL_DIR="$CONTROL_DIR" CLUB3090_DIR="$UPSTREAM_DIR" bash "$SERVER_DIR/install.sh"
"""
    return "club3090", "System Update", command, "local Git checkouts"


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
    restart_updater = False
    if int(return_code or 0) == 0 and operation == "update":
        control_ready = wait_for_systemd_unit("club3090-control.service", timeout=180)
        http_ready = wait_for_admin_http(timeout=120)
        ready = control_ready and http_ready
        summary = "System Update completed successfully" if ready else "System Update command finished but service readiness checks timed out"
        status = "completed" if ready else "degraded"
        if ready:
            ensure_dir()
            Path(UPDATE_RELOAD_FLAG_FILE).touch()
            restart_updater = True
    else:
        summary = f"System Update failed with return code {return_code}"
        status = "failed"
    set_state(
        active=False, status=status, finished_at=int(time.time()),
        return_code=int(return_code or 0), summary=summary,
        script_version=SCRIPT_VERSION,
    )
    append_update_log(f"[self-update service] {summary}")
    if restart_updater:
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
    finalize_job(rc, operation)

def start_update(operation, scope_name="controller"):
    with state_lock:
        if state.get("active"):
            raise RuntimeError("A System Update job is already running")
    normalized, label, command, source = build_update_command(operation, scope_name=scope_name)
    token = secrets.token_urlsafe(24)
    reset_update_log()
    now = int(time.time())
    snapshot = set_state(
        active=True, status="running", operation="update", scope=normalized,
        label=label, command=command, started_at=now, finished_at=0,
        return_code=None, summary=f"{label} queued", token=token,
        log_file=UPDATE_LOG_FILE, script_version=SCRIPT_VERSION,
        ui_ack_token="", ui_ack_at=0,
    )
    append_update_log(f"[self-update service] queued {label}")
    worker = threading.Thread(
        target=run_update_job,
        args=(normalized, label, command, source, "update"),
        name="club3090-system-update",
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
            result = start_update(payload.get("operation"), payload.get("scope"))
            self.send_json(result)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, 500)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        print(json.dumps({
            "repository_revision": repository_revision(),
            "update_instructions": "System Update fast-forwards clean tracking branches in both Club-3090 checkouts, rebuilds the Model DB, and restarts managed services.",
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
