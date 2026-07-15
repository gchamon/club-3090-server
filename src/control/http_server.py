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
    def read_raw_body(self):
        n = int(self.headers.get("content-length","0") or "0")
        return self.rfile.read(n) if n else b""
    def redirect(self, location, code=302):
        self.close_connection = True
        self.send_response(code)
        self.send_header("Location", location)
        self.emit_pending_headers()
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
    def accepts_gzip_response(self):
        accepted = str(self.headers.get("Accept-Encoding", "") or "").lower()
        return any(part.strip().split(";", 1)[0] == "gzip" for part in accepted.split(","))
    def should_gzip_response(self, payload, content_type="", code=200):
        if code < 200 or code in {204, 304}:
            return False
        if not payload or len(payload) < 1024:
            return False
        lowered = str(content_type or "").split(";", 1)[0].strip().lower()
        return (
            lowered.startswith("text/") or
            lowered in {
                "application/json",
                "application/javascript",
                "application/xml",
                "image/svg+xml",
            }
        )
    def send_bytes(self, payload, content_type="application/octet-stream", code=200):
        self.close_connection = True
        body = bytes(payload or b"")
        gzip_response = False
        if self.accepts_gzip_response() and self.should_gzip_response(body, content_type, code):
            try:
                compressed = gzip.compress(body, compresslevel=5)
                if len(compressed) < len(body):
                    body = compressed
                    gzip_response = True
            except Exception:
                gzip_response = False
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if gzip_response:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.emit_pending_headers()
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.write_response_bytes(body)
    def write_response_bytes(self, payload):
        try:
            self.wfile.write(payload)
            return True
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            self.close_connection = True
            return False
    def send_json(self, obj, code=200):
        self.send_bytes(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), "application/json", code)
    def send_stream(self, file_path, content_type="application/octet-stream", download_name="", code=200, cleanup_path=""):
        target = str(file_path or "").strip()
        if not target or not os.path.exists(target):
            raise FileNotFoundError(target or "stream file")
        size = os.path.getsize(target)
        self.close_connection = True
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(download_name)}"')
        self.emit_pending_headers()
        self.send_header("Content-Length", str(size))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            with open(target, "rb") as handle:
                while True:
                    chunk = handle.read(1024 * 256)
                    if not chunk:
                        break
                    if not self.write_response_bytes(chunk):
                        break
        finally:
            if cleanup_path:
                try:
                    os.remove(cleanup_path)
                except Exception:
                    pass
    def send_file_range(self, file_path, content_type="application/octet-stream", download_name="", inline=True):
        target = str(file_path or "").strip()
        if not target or not os.path.exists(target):
            raise FileNotFoundError(target or "stream file")
        size = int(os.path.getsize(target) or 0)
        start = 0
        end = max(0, size - 1)
        partial = False
        range_header = str(self.headers.get("Range", "") or "").strip()
        if range_header.startswith("bytes=") and size > 0:
            match = re.match(r"bytes=(\d*)-(\d*)$", range_header)
            if match:
                raw_start, raw_end = match.groups()
                if raw_start == "" and raw_end:
                    suffix = min(size, max(0, int(raw_end or 0)))
                    start = max(0, size - suffix)
                    end = size - 1
                    partial = True
                else:
                    start = max(0, int(raw_start or 0))
                    end = min(size - 1, int(raw_end or size - 1))
                    if start <= end:
                        partial = True
                    else:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.emit_pending_headers()
                        self.send_header("Content-Length", "0")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        return
        length = max(0, end - start + 1) if size > 0 else 0
        self.close_connection = True
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        disposition = "inline" if inline else "attachment"
        if download_name:
            self.send_header("Content-Disposition", f'{disposition}; filename="{os.path.basename(download_name)}"')
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.emit_pending_headers()
        self.send_header("Content-Length", str(length))
        self.send_header("Connection", "close")
        self.end_headers()
        with open(target, "rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(1024 * 256, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                if not self.write_response_bytes(chunk):
                    break

def admin_service_worker_script():
    version_json = json.dumps(str(SCRIPT_VERSION or "unknown"))
    return f"""
const CLUB3090_SW_VERSION = {version_json};
const CACHE_NAME = `club3090-admin-shell-${{CLUB3090_SW_VERSION}}`;
const SHELL_URL = "/admin";
const NAVIGATION_TIMEOUT_MS = 10 * 1000;

async function normalizedShellResponse(response) {{
  if (!response || !response.ok) return null;
  const body = await response.clone().arrayBuffer();
  const headers = new Headers(response.headers);
  headers.set("Cache-Control", "max-age=31536000");
  headers.set("X-Club3090-Cached-Shell", CLUB3090_SW_VERSION);
  return new Response(body, {{
    status: response.status,
    statusText: response.statusText,
    headers,
  }});
}}

async function cacheAdminShell() {{
  const cache = await caches.open(CACHE_NAME);
  const response = await fetch(new Request(SHELL_URL, {{ credentials: "include", cache: "no-store" }}));
  const shell = await normalizedShellResponse(response);
  if (shell) await cache.put(SHELL_URL, shell);
}}

async function cachedAdminShell() {{
  const cache = await caches.open(CACHE_NAME);
  return (await cache.match(SHELL_URL)) || (await caches.match(SHELL_URL));
}}

async function networkFirstAdminNavigation(request) {{
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), NAVIGATION_TIMEOUT_MS);
  try {{
    const response = await fetch(new Request(request, {{ signal: controller.signal, cache: "no-store" }}));
    clearTimeout(timer);
    if (response && response.ok) {{
      const cache = await caches.open(CACHE_NAME);
      const shell = await normalizedShellResponse(response);
      if (shell) await cache.put(SHELL_URL, shell).catch(() => {{}});
    }} else if (response && [502, 503, 504].includes(Number(response.status))) {{
      const fallback = await cachedAdminShell();
      if (fallback) return fallback;
    }}
    return response;
  }} catch (error) {{
    clearTimeout(timer);
    const fallback = await cachedAdminShell();
    if (fallback) return fallback;
    throw error;
  }}
}}

self.addEventListener("install", (event) => {{
  event.waitUntil((async () => {{
    await cacheAdminShell().catch(() => {{}});
    await self.skipWaiting();
  }})());
}});

self.addEventListener("activate", (event) => {{
  event.waitUntil((async () => {{
    const names = await caches.keys();
    await Promise.all(names.map((name) => name.startsWith("club3090-admin-shell-") && name !== CACHE_NAME ? caches.delete(name) : Promise.resolve(false)));
    await cacheAdminShell().catch(() => {{}});
    await self.clients.claim();
  }})());
}});

self.addEventListener("message", (event) => {{
  if (event && event.data && event.data.type === "CACHE_ADMIN_SHELL") {{
    event.waitUntil(cacheAdminShell().catch(() => {{}}));
  }}
}});

self.addEventListener("fetch", (event) => {{
  const request = event.request;
  if (!request || request.method !== "GET" || request.mode !== "navigate") return;
  const url = new URL(request.url);
  if (!url.pathname.startsWith("/admin") || url.pathname === "/admin/sw.js") return;
  event.respondWith(networkFirstAdminNavigation(request));
}});
""".strip() + "\n"

def admin_favicon_svg():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="12" fill="#0b1220"/>'
        '<path d="M18 42V22h28v7h-6v-2H24v10h16v-3h6v8H18z" fill="#7dd3fc"/>'
        '<path d="M28 46h20v-6H34v-4h12v-6H28v16z" fill="#a7f3d0"/>'
        '</svg>'
    )

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
        try:
            self.wfile.write(f"event: {event_name}\ndata: {body}\n\n".encode("utf-8", errors="replace"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            self.close_connection = True
            raise
    def send_sse_comment(self, text="ping"):
        try:
            self.wfile.write(f": {text}\n\n".encode("utf-8", errors="replace"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            self.close_connection = True
            raise
    def admin_stream_client_key(self, label):
        forwarded = str(self.headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
        client_ip = forwarded or (self.client_address[0] if self.client_address else "")
        user_agent = re.sub(r"\s+", " ", str(self.headers.get("User-Agent") or "").strip())[:120]
        return f"{client_ip}|{user_agent}|{str(label or '').strip()}"
    def begin_admin_stream(self, label):
        key = self.admin_stream_client_key(label)
        stop_event = threading.Event()
        with admin_stream_registry_lock:
            old_event = admin_stream_registry.get(key)
            if old_event is not None:
                try:
                    old_event.set()
                except Exception:
                    pass
            admin_stream_registry[key] = stop_event
        return key, stop_event
    def end_admin_stream(self, key, stop_event):
        with admin_stream_registry_lock:
            if admin_stream_registry.get(key) is stop_event:
                admin_stream_registry.pop(key, None)
        self.close_connection = True
    def admin_stream_stopped(self, stop_event):
        return bool(stop_event is not None and stop_event.is_set())
    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/favicon.ico":
            self.queue_header("Cache-Control", "public, max-age=86400")
            self.send_bytes(admin_favicon_svg().encode("utf-8"), "image/svg+xml; charset=utf-8")
            return
        if path == "/admin/update-status":
            params = parse_admin_query_params(parsed)
            requested_token = str(params.get("token") or "").strip()
            update_state = read_self_update_state()
            update_token = str(update_state.get("token") or "").strip()
            if not requested_token or not update_token or requested_token != update_token:
                self.send_json({"ok": False, "error": "Invalid update token"}, 403)
                return
            self.send_json({"ok": True, "self_update": update_state})
            return
        if path == "/admin/sw.js":
            self.queue_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.queue_header("Service-Worker-Allowed", "/admin")
            self.send_bytes(admin_service_worker_script().encode("utf-8"), "application/javascript; charset=utf-8")
            return
        if not self.require_auth():
            return
        if path == "/admin/update-signal":
            update_state = read_self_update_state()
            self.send_json({
                "ok": True,
                "self_update": {
                    "active": bool(update_state.get("active")),
                    "status": update_state.get("status"),
                    "scope": update_state.get("scope"),
                    "token": update_state.get("token"),
                    "stream_url": update_state.get("stream_url"),
                    "status_url": update_state.get("status_url"),
                },
            })
            return
        if path == "/":
            self.redirect("/admin")
            return
        if path == "/admin":
            html = get_admin_html_template().replace("__SCRIPT_VERSION__", SCRIPT_VERSION).replace(":8008/admin", f":{ADMIN_PORT}/admin").replace(":8009", f":{PROXY_PORT}")
            self.queue_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.queue_header("Pragma", "no-cache")
            self.send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/admin/status":
            params = parse_admin_query_params(parsed)
            force = str(params.get("force") or "").strip().lower() in {"1", "true", "yes", "on"}
            request_options = parse_status_request_options(params)
            refresh_remote_metadata = str(params.get("refresh_remote_update") or "").strip().lower() in {"1", "true", "yes", "on"}
            started_at = time.time()
            if (
                request_options.get("tab") == "metrics"
                and request_options.get("include_series")
                and not request_options.get("include_inventory")
            ):
                snapshot = get_lightweight_status_snapshot(series_limit=request_options.get("series_limit"))
            else:
                snapshot = get_status_snapshot(force=force, refresh_remote_metadata=refresh_remote_metadata)
            payload = shape_status_snapshot(
                snapshot,
                request_options,
            )
            payload["access_hint"] = tailscale_access_hint_for_client(self.client_address[0] if self.client_address else "")
            elapsed = time.time() - started_at
            if elapsed >= 1.0 or payload.get("status_error"):
                log_control(f"ADMIN status served force={force} elapsed={round(elapsed, 3)}s status_error={bool(payload.get('status_error'))}")
            self.send_json(payload)
            return
        if path == "/admin/benchmarks":
            params = parse_admin_query_params(parsed)
            live_only = str(params.get("live") or "").strip().lower() in {"1", "true", "yes", "on"}
            inventory_flags = [params.get("full"), params.get("inventory"), params.get("include_inventory")]
            force_full = any(str(flag or "").strip().lower() in {"1", "true", "yes", "on"} for flag in inventory_flags)
            compact_requested = any(str(flag or "").strip().lower() in {"0", "false", "no", "off"} for flag in inventory_flags)
            include_scores = str(params.get("scores") or params.get("include_scores") or "").strip().lower() in {"1", "true", "yes", "on"}
            include_logs = str(params.get("logs") or params.get("include_logs") or params.get("include_details") or "").strip().lower() in {"1", "true", "yes", "on"}
            active_job = benchmark_job_active()
            if live_only or compact_requested or (active_job and not force_full):
                base = benchmarks_status_snapshot(include_scores=include_scores) if include_scores else {}
                self.send_json({"ok": True, "benchmarks": benchmarks_live_status_overlay(base, include_logs=include_logs)})
            else:
                self.send_json({"ok": True, "benchmarks": benchmarks_snapshot(include_logs=include_logs, include_scores=include_scores)})
            return
        if path == "/admin/scripts":
            params = parse_admin_query_params(parsed)
            include_internal = str(params.get("include_internal") or "").strip().lower() in {"1", "true", "yes", "on"}
            self.send_json({"ok": True, "scripts": discover_upstream_scripts(include_internal=include_internal), "include_internal": include_internal, "job": script_job_snapshot()})
            return
        if path == "/admin/scripts/jobs":
            self.send_json({"ok": True, "job": script_job_snapshot()})
            return
        if path == "/admin/scripts/log":
            params = parse_admin_query_params(parsed)
            self.send_json({"ok": True, **script_log_snapshot(job_id=params.get("job_id") or "", tail_lines=parse_tail_lines_param(params, 500))})
            return
        if path == "/admin/benchmarks/detail":
            params = parse_admin_query_params(parsed)
            try:
                self.send_json(benchmark_detail(params.get("selector") or ""))
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/log-bootstrap":
            params = parse_admin_query_params(parsed)
            source = str(params.get("source") or "docker").strip().lower()
            instance_id = str(params.get("instance") or "").strip().upper()
            service_id = str(params.get("service") or "").strip().lower()
            tail_lines = parse_tail_lines_param(params, 250)
            payload = read_selected_log_snapshot(source=source, instance_id=instance_id, service_id=service_id, tail_lines=tail_lines)
            self.send_json({"ok": True, **payload})
            return
        if path == "/admin/logs":
            params = parse_admin_query_params(parsed)
            if str(params.get("source") or "").strip().lower() == "benchmarks":
                stream_key, stop_event = self.begin_admin_stream("logs:benchmarks")
                self.close_connection = True
                self.send_response(200)
                self.send_header("Content-Type","text/event-stream")
                self.send_header("Cache-Control","no-cache")
                self.send_header("Connection","close")
                self.emit_pending_headers()
                self.end_headers()
                try:
                    self.stream_dynamic_text_file(benchmark_active_script_log_file, "no benchmark script output yet; waiting...", initial_tail_lines=parse_tail_lines_param(params, 250), stop_event=stop_event)
                finally:
                    self.end_admin_stream(stream_key, stop_event)
                return
            if str(params.get("source") or "").strip().lower() == "script":
                requested_job_id = str(params.get("job_id") or "").strip()
                stream_key, stop_event = self.begin_admin_stream(f"logs:script:{requested_job_id or 'latest'}")
                self.close_connection = True
                self.send_response(200)
                self.send_header("Content-Type","text/event-stream")
                self.send_header("Cache-Control","no-cache")
                self.send_header("Connection","close")
                self.emit_pending_headers()
                self.end_headers()
                try:
                    self.stream_dynamic_text_file(lambda: script_current_log_file(requested_job_id), "no script output yet; waiting...", initial_tail_lines=parse_tail_lines_param(params, 250), stop_event=stop_event)
                finally:
                    self.end_admin_stream(stream_key, stop_event)
                return
            requested_source = str(params.get("source") or "docker").strip().lower()
            requested_instance = str(params.get("instance") or "").strip().upper()
            requested_service = str(params.get("service") or "").strip().lower()
            stream_key, stop_event = self.begin_admin_stream(f"logs:{requested_source}:{requested_instance}:{requested_service}")
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache")
            self.send_header("Connection","close")
            self.emit_pending_headers()
            self.end_headers()
            try:
                self.stream_logs(parsed, stop_event=stop_event)
            finally:
                self.end_admin_stream(stream_key, stop_event)
            return
        if path == "/admin/audit-stream":
            params = parse_admin_query_params(parsed)
            stream_key, stop_event = self.begin_admin_stream("logs:audit")
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache")
            self.send_header("Connection","close")
            self.emit_pending_headers()
            self.end_headers()
            try:
                self.stream_text_file(AUDIT_LOG_FILE, "no audit entries yet; waiting...", initial_tail_lines=parse_tail_lines_param(params, 250), stop_event=stop_event)
            finally:
                self.end_admin_stream(stream_key, stop_event)
            return
        if path == "/admin/control-stream":
            params = parse_admin_query_params(parsed)
            stream_key, stop_event = self.begin_admin_stream("logs:control")
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache")
            self.send_header("Connection","close")
            self.emit_pending_headers()
            self.end_headers()
            try:
                self.stream_text_file(CONTROL_LOG_FILE, "no web UI server entries yet; waiting...", initial_tail_lines=parse_tail_lines_param(params, 250), stop_event=stop_event)
            finally:
                self.end_admin_stream(stream_key, stop_event)
            return
        if path == "/admin/debug-stream":
            params = parse_admin_query_params(parsed)
            stream_key, stop_event = self.begin_admin_stream("logs:debug")
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache")
            self.send_header("Connection","close")
            self.emit_pending_headers()
            self.end_headers()
            try:
                self.stream_text_file(DEBUG_LOG_FILE, "no debug entries yet; waiting...", initial_tail_lines=parse_tail_lines_param(params, 250), stop_event=stop_event)
            finally:
                self.end_admin_stream(stream_key, stop_event)
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
        if path == "/admin/code-syntax":
            payload = read_effective_code_syntax_config_bytes()
            if not payload:
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_json({
                    "aliases": {},
                    "fallback_family": "clike",
                    "theme": {"tokens": {}},
                    "families": {},
                })
                return
            self.queue_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.queue_header("Pragma", "no-cache")
            self.send_bytes(payload, "application/json; charset=utf-8")
            return
        if path == "/admin/storage-browser/preview":
            params = parse_admin_query_params(parsed)
            try:
                row = resolve_storage_browser_file(params.get("root_path"), params.get("relative_path") or "")
                self.queue_header("Cache-Control", "no-store")
                self.send_file_range(
                    row.get("path"),
                    row.get("mime") or "application/octet-stream",
                    row.get("name") or "preview",
                    inline=True,
                )
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 404)
            return
        if path == "/admin/storage-browser/subtitle":
            params = parse_admin_query_params(parsed)
            try:
                row = read_storage_browser_subtitle_payload(
                    params.get("root_path"),
                    params.get("relative_path") or "",
                    params.get("external_relative_path") or "",
                    params.get("embedded_stream_index"),
                )
                if not row.get("found"):
                    self.send_json({"ok": False, "error": "Subtitle not found."}, 404)
                    return
                self.queue_header("Cache-Control", "no-store")
                self.send_bytes(row.get("payload") or b"", row.get("content_type") or "text/vtt; charset=utf-8")
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 404)
            return
        if path == "/admin/chat-conversation":
            params = parse_admin_query_params(parsed)
            debug_audit("chat_conversation_get", conversation_id=params.get("conversation_id") or params.get("id") or "")
            self.send_json(read_chat_conversation_detail(params.get("conversation_id") or params.get("id") or ""))
            return
        if path == "/admin/chat-stream-state":
            params = parse_admin_query_params(parsed)
            conversation_id = params.get("conversation_id") or params.get("id") or ""
            self.send_json({"ok": True, "stream": read_admin_chat_stream_state(conversation_id)})
            return
        if path in {"/admin/ai-studio/generation", "/admin/image-studio/generation"}:
            params = parse_admin_query_params(parsed)
            try:
                self.send_json({"ok": True, "generation": image_studio_generation_status(params.get("job_id") or params.get("id") or "")})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 404)
            return
        if path in {"/admin/ai-studio/gallery", "/admin/image-studio/gallery"}:
            params = parse_admin_query_params(parsed)
            try:
                limit = int(params.get("limit") or 120)
            except Exception:
                limit = 120
            self.send_json({"ok": True, "items": image_studio_gallery_items(limit)})
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
        if path == "/admin/debug-log":
            try:
                payload = subprocess.check_output(["tail","-n","300",DEBUG_LOG_FILE], text=True, stderr=subprocess.DEVNULL, timeout=3).encode("utf-8", errors="replace")
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
                ensure_benchmark_idle("Preset launch")
                instance_id = str(data.get("instance_id") or "").strip().upper()
                mode = canonical_mode_selector(data.get("mode"))
                spec = resolve_variant_spec(mode)
                if not spec:
                    raise ValueError("Invalid mode")
                scope_kind = str(spec.get("scope_kind") or "")
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
                        launch_result = start_instances_parallel(updated_targets)
                        for row in launch_result.get("started") or []:
                            target = row.get("instance") or {}
                            outputs.append(f"{target.get('id') or 'instance'}: {str(row.get('output') or '')[-2400:]}")
                        partial_failures = launch_result.get("failed") or []
                        if partial_failures:
                            outputs.extend(
                                f"{str((row.get('instance') or {}).get('id') or 'instance')}: {str(row.get('error') or '')[-2400:]}"
                                for row in partial_failures
                            )
                        if not launch_result.get("started"):
                            raise RuntimeError("\n\n".join(outputs).strip() or "All global single-GPU launches failed.")
                        write_active_mode(mode)
                        write_last_good_mode(mode)
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
                        launch_result = start_instances_parallel(updated_targets)
                        for row in launch_result.get("started") or []:
                            target = row.get("instance") or {}
                            outputs.append(f"{target.get('id') or 'instance'}: {str(row.get('output') or '')[-2400:]}")
                        partial_failures = launch_result.get("failed") or []
                        if partial_failures:
                            outputs.extend(
                                f"{str((row.get('instance') or {}).get('id') or 'instance')}: {str(row.get('error') or '')[-2400:]}"
                                for row in partial_failures
                            )
                        if not launch_result.get("started"):
                            raise RuntimeError("\n\n".join(outputs).strip() or "All global dual-GPU launches failed.")
                        write_active_mode(mode)
                        write_last_good_mode(mode)
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
                ensure_benchmark_idle("Model DB rebuild")
                inventory = enrich_runtime_inventory_cache_sizes(rebuild_runtime_inventory())
                inventory = enrich_inventory_model_update_state(inventory)
                benchmark_inventory = benchmark_rebuild_inventory_state_file(reason="runtime inventory rebuilt from admin")
                log_audit("admin_runtime_inventory_rebuilt", models=len(inventory.get("models") or []), variants=len(inventory.get("variants") or []))
                self.send_json({
                    "ok": True,
                    "runtime_inventory": inventory,
                    "benchmark_inventory": benchmark_compact_inventory_state_summary(benchmark_inventory),
                    "models": inventory.get("models") or [],
                    "variants": inventory.get("variants") or [],
                })
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/model-updates/check":
            try:
                summary = start_model_update_check("manual")
                inventory = enrich_inventory_model_update_state(enrich_runtime_inventory_cache_sizes(load_runtime_inventory(force=True)))
                self.send_json({
                    "ok": True,
                    "model_updates": summary,
                    "runtime_inventory": inventory,
                    "models": inventory.get("models") or [],
                    "variants": inventory.get("variants") or [],
                    "focus_log_source": "audit",
                })
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/model-update":
            try:
                data = self.read_json_body()
                job = start_model_update_job(
                    data.get("model_id"),
                    data.get("variant_id"),
                    data.get("resource_key"),
                )
                self.send_json({"ok": True, "model_install_job": job, "model_install_jobs": model_install_jobs_snapshot(), "focus_log_source": "audit"})
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
                self.send_json({"ok": True, "model_install_job": job, "model_install_jobs": model_install_jobs_snapshot(), "focus_log_source": "audit"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/model-install/stop":
            try:
                data = self.read_json_body()
                job = stop_model_install_job(data.get("job_id"))
                self.send_json({"ok": True, "model_install_job": job, "model_install_jobs": model_install_jobs_snapshot(), "focus_log_source": "audit"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/model-resources/plan":
            try:
                data = self.read_json_body()
                plan = preset_resource_delete_plan(data.get("selector"), data.get("variant_id"))
                self.send_json({"ok": True, **plan})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/model-resources/delete":
            try:
                data = self.read_json_body()
                if data.get("paths"):
                    result = delete_model_resource_paths(data.get("paths") or [])
                else:
                    result = delete_preset_resources(data.get("selector"), data.get("variant_id"))
                inventory = enrich_runtime_inventory_cache_sizes(load_runtime_inventory(force=True))
                self.send_json({
                    **result,
                    "runtime_inventory": inventory,
                    "models": inventory.get("models") or [],
                    "variants": inventory.get("variants") or [],
                    "focus_log_source": "audit",
                }, 200 if result.get("ok") else 500)
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/model-resources/delete-with-caches":
            try:
                data = self.read_json_body()
                if data.get("paths"):
                    result = delete_model_resource_paths_and_caches(data.get("paths") or [], data.get("selectors") or [])
                else:
                    result = delete_preset_resources_and_caches(data.get("selector"), data.get("variant_id"))
                inventory = enrich_runtime_inventory_cache_sizes(load_runtime_inventory(force=True))
                self.send_json({
                    **result,
                    "runtime_inventory": inventory,
                    "models": inventory.get("models") or [],
                    "variants": inventory.get("variants") or [],
                    "focus_log_source": "audit",
                }, 200 if result.get("ok") else 500)
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/model-cache/delete":
            try:
                ensure_benchmark_idle("Model cache deletion")
                data = self.read_json_body()
                result = delete_model_cache_paths(data.get("paths") or [])
                inventory = enrich_runtime_inventory_cache_sizes(load_runtime_inventory(force=True))
                self.send_json({
                    **result,
                    "runtime_inventory": inventory,
                    "models": inventory.get("models") or [],
                    "variants": inventory.get("variants") or [],
                    "focus_log_source": "audit",
                }, 200 if result.get("ok") else 500)
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/preset-caches/plan":
            try:
                data = self.read_json_body()
                plan = preset_cache_delete_plan(data.get("selector"), data.get("variant_id"))
                self.send_json({"ok": True, **plan})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/preset-caches/delete":
            try:
                ensure_benchmark_idle("Preset cache deletion")
                data = self.read_json_body()
                result = delete_preset_caches(data.get("selector"), data.get("variant_id"))
                self.send_json({**result, "focus_log_source": "audit"}, 200 if result.get("ok") else 500)
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/custom-models":
            try:
                ensure_benchmark_idle("Custom model changes")
                data = self.read_json_body()
                action = str(data.get("action") or "").strip().lower()
                if action == "add":
                    job = start_custom_model_add_job(data)
                    self.send_json({"ok": True, "custom_model_job": job, "focus_log_source": "audit"})
                    return
                if action == "delete":
                    job = start_custom_model_remove_job(data.get("id") or data.get("model_id") or data.get("selector"))
                    self.send_json({"ok": True, "custom_model_job": job, "focus_log_source": "audit"})
                    return
                raise ValueError("Invalid custom model action")
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/custom-presets":
            try:
                ensure_benchmark_idle("Custom preset changes")
                data = self.read_json_body()
                action = str(data.get("action") or "").strip().lower()
                if action == "duplicate":
                    self.send_json({**duplicate_custom_preset(data), "focus_log_source": "audit"})
                    return
                if action == "delete":
                    self.send_json({**delete_custom_preset_record(data.get("selector") or data.get("id") or ""), "focus_log_source": "audit"})
                    return
                raise ValueError("Invalid custom preset action")
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/benchmarks/start":
            try:
                data = self.read_json_body()
                if image_studio_activity_active(max_age=0):
                    raise RuntimeError("Stop active AI Studio generations before starting Model Scores benchmarks.")
                snapshot = start_benchmark_job(
                    data.get("mode") or "quick",
                    selectors=data.get("selectors") or ([data.get("selector")] if data.get("selector") else None),
                    include_completed=bool(data.get("include_completed", False)),
                    include_deprecated=bool(data.get("include_deprecated", BENCHMARK_INCLUDE_APPROVED_DEPRECATED_BY_DEFAULT)),
                    include_experimental=bool(data.get("include_experimental", BENCHMARK_INCLUDE_EXPERIMENTAL_BY_DEFAULT)),
                    thermal_cooldown=bool(data.get("thermal_cooldown", True)),
                    mock=bool(data.get("mock", False)),
                    step_scope=data.get("step_scope") or "",
                    selected_stages=data.get("stages") or {},
                )
                self.send_json({"ok": True, "benchmarks": snapshot, "focus_log_source": "benchmarks"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/benchmarks/cancel":
            try:
                data = self.read_json_body()
                self.send_json({"ok": True, "benchmarks": cancel_benchmark_job(force=bool(data.get("force", False))), "focus_log_source": "benchmarks"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/benchmarks/queue":
            try:
                data = self.read_json_body()
                snapshot = update_benchmark_queue(
                    selectors=data.get("selectors") or [],
                    order=data.get("order") or data.get("selectors") or [],
                    stages=data.get("stages") or {},
                )
                self.send_json({"ok": True, "benchmarks": snapshot, "focus_log_source": "benchmarks"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/benchmarks/rerun":
            try:
                data = self.read_json_body()
                snapshot = enqueue_benchmark_rerun(
                    data.get("selector") or "",
                    mode=data.get("mode") or "quick",
                    step_scope=data.get("step_scope") or data.get("metric_id") or data.get("category") or "",
                    selected_stages=data.get("selected_stages") or data.get("stages") or [],
                    append=bool(data.get("append") or str(data.get("position") or "").strip().lower() in {"append", "tail", "end"}),
                )
                self.send_json({"ok": True, "benchmarks": snapshot, "focus_log_source": "benchmarks"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/benchmarks/revalidate-compliance":
            try:
                data = self.read_json_body()
                self.send_json({**benchmark_revalidate_compliance_result(data.get("selector") or "", data.get("mode") or "quick"), "focus_log_source": "benchmarks"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/benchmarks/clear":
            try:
                data = self.read_json_body()
                self.send_json({"ok": True, "benchmarks": clear_benchmark_result(data.get("selector") or "")})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/scripts/run":
            try:
                data = self.read_json_body()
                job = start_script_job(data.get("script_id") or "", args=data.get("args") or "", instance_id=data.get("instance_id") or "")
                self.send_json({"ok": True, "script_job": job, "focus_log_source": "script"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path in {"/admin/ai-studio/setup", "/admin/image-studio/setup"}:
            try:
                self.send_json({"ok": True, "script_job": start_image_studio_setup_job(), "focus_log_source": "script"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path in {"/admin/ai-studio/start", "/admin/image-studio/start"}:
            try:
                self.send_json({"ok": True, "script_job": start_image_studio_runtime_job(), "focus_log_source": "script"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path in {"/admin/ai-studio/stop", "/admin/image-studio/stop"}:
            try:
                self.send_json({"ok": True, "script_job": stop_image_studio_runtime_job(), "focus_log_source": "script"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path in {"/admin/ai-studio/download", "/admin/image-studio/download"}:
            try:
                data = self.read_json_body()
                self.send_json({"ok": True, "script_job": start_image_studio_model_download_job(data.get("model_key") or ""), "focus_log_source": "script"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path in {"/admin/ai-studio/remove", "/admin/image-studio/remove"}:
            try:
                self.send_json({"ok": True, "script_job": start_image_studio_remove_job(), "focus_log_source": "script"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path in {"/admin/ai-studio/generate", "/admin/image-studio/generate"}:
            try:
                self.send_json({"ok": True, "generation": start_image_studio_generation(self.read_json_body())})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path in {"/admin/ai-studio/plan", "/admin/image-studio/plan"}:
            try:
                self.send_json({"ok": True, "plan": plan_image_studio_interactive(self.read_json_body())})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path in {"/admin/ai-studio/backend-plan", "/admin/image-studio/backend-plan"}:
            try:
                self.send_json({"ok": True, "generation": start_image_studio_backend_plan(self.read_json_body())})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path in {"/admin/ai-studio/cancel", "/admin/image-studio/cancel"}:
            try:
                data = self.read_json_body()
                self.send_json({"ok": True, "generation": cancel_image_studio_generation(data.get("job_id") or data.get("id") or "")})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path in {"/admin/ai-studio/gallery/delete", "/admin/image-studio/gallery/delete"}:
            try:
                data = self.read_json_body()
                self.send_json({"ok": True, **delete_image_studio_gallery_artifact(data.get("root_path") or "/", data.get("relative_path") or "")})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/scripts/cancel":
            try:
                data = self.read_json_body()
                self.send_json({"ok": True, "script_job": cancel_script_job(data.get("job_id") or ""), "focus_log_source": "script"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/scripts/remove":
            try:
                data = self.read_json_body()
                self.send_json({"ok": True, "script_job": remove_script_job(data.get("job_id") or ""), "focus_log_source": "script"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/update":
            try:
                data = self.read_json_body()
                scope_name = _selector_token(data.get("scope"))
                benchmark_active = benchmark_job_active()
                if scope_name == "club3090" and benchmark_active:
                    message = "Stop Model Scores benchmarking before migrating Club-3090."
                    append_audit_text_line(f"Rejected Club-3090 migration while Model Scores benchmarking is active.")
                    self.send_json({"ok": False, "error": message}, 409)
                    return
                if benchmark_active:
                    append_audit_text_line("Self-update requested while Model Scores benchmarking is active; leaving benchmark queue and runtimes untouched.")
                result = start_self_update_job(scope_name or data.get("scope"), data.get("target_commit"))
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
                ensure_benchmark_idle("Chat")
                data = self.read_json_body()
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
                return
            stream_admin_chat_request(self, data)
            return
        if path == "/admin/chat":
            try:
                ensure_benchmark_idle("Chat")
                data = self.read_json_body()
                self.send_json(run_admin_chat_request(data))
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/chat-stop":
            try:
                data = self.read_json_body()
                conversation_id = data.get("conversation_id") or data.get("id") or ""
                result = request_admin_chat_stream_stop(conversation_id)
                if not result.get("ok"):
                    self.send_json(result, 400)
                    return
                self.send_json({
                    **result,
                    "stream": read_admin_chat_stream_state(conversation_id),
                })
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
                if action not in {"archive", "restore", "delete", "delete_all"}:
                    raise ValueError("Invalid conversation action.")
                conversation_id = data.get("conversation_id") or ""
                with suppress_chat_debug_audit():
                    debug_audit("chat_conversation_action", action=action, conversation_id=conversation_id)
                    if action == "archive":
                        result = archive_chat_conversation(conversation_id)
                    elif action == "restore":
                        result = restore_chat_conversation(conversation_id)
                    elif action == "delete_all":
                        result = delete_all_chat_conversations()
                    else:
                        result = delete_chat_conversation(conversation_id)
                self.send_json(result)
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
        if path == "/admin/storage-browser":
            try:
                data = self.read_json_body()
                action = str(data.get("action") or "list").strip().lower()
                if action == "list":
                    self.send_json(list_storage_browser_entries(data.get("root_path"), data.get("relative_path") or ""))
                    return
                if action == "mount":
                    self.send_json(mount_storage_browser_volume(data.get("device_path")))
                    return
                if action == "unmount":
                    self.send_json(unmount_storage_browser_volume(data.get("root_path")))
                    return
                if action == "delete":
                    self.send_json(delete_storage_browser_entries(data.get("root_path"), data.get("entries") or []))
                    return
                if action == "read_file":
                    self.send_json(read_storage_browser_file(data.get("root_path"), data.get("relative_path") or ""))
                    return
                if action == "media_metadata":
                    self.send_json(read_storage_browser_media_metadata(data.get("root_path"), data.get("relative_path") or ""))
                    return
                if action == "read_file_chunk":
                    self.send_json(
                        read_storage_browser_file_chunk(
                            data.get("session_id"),
                            data.get("offset") or 0,
                            data.get("limit") or STORAGE_BROWSER_CHUNK_BYTES,
                        )
                    )
                    return
                if action == "save_file":
                    self.send_json(save_storage_browser_file(data.get("root_path"), data.get("relative_path") or "", data.get("text") or ""))
                    return
                if action == "save_binary_file":
                    self.send_json(save_storage_browser_binary_file(data.get("root_path"), data.get("relative_path") or "", data.get("hex") or ""))
                    return
                if action == "save_file_chunk":
                    self.send_json(
                        save_storage_browser_file_chunk(
                            data.get("session_id"),
                            data.get("offset") or 0,
                            data.get("text"),
                            data.get("base64"),
                            data.get("expected_bytes") or 0,
                        )
                    )
                    return
                if action == "close_file_session":
                    self.send_json(close_storage_browser_file_session(data.get("session_id")))
                    return
                if action == "create_folder":
                    self.send_json(create_storage_browser_folder(data.get("root_path"), data.get("relative_path") or "", data.get("name") or ""))
                    return
                if action == "create_file":
                    self.send_json(create_storage_browser_file(data.get("root_path"), data.get("relative_path") or "", data.get("name") or ""))
                    return
                raise ValueError("Invalid storage browser action.")
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/storage-browser/upload":
            try:
                params = parse_admin_query_params(urlsplit(self.path))
                file_name = params.get("name") or self.headers.get("X-Club3090-File-Name") or ""
                self.send_json(
                    write_storage_browser_upload(
                        params.get("root") or "",
                        params.get("relative_path") or "",
                        file_name,
                        self.read_raw_body(),
                    )
                )
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/storage-browser/download":
            try:
                data = self.read_json_body()
                action = str(data.get("action") or "fetch").strip().lower()
                if action == "plan":
                    self.send_json(prepare_storage_browser_download_plan(data.get("root_path"), data.get("entries") or []))
                    return
                if action == "start":
                    started = start_storage_browser_download_job(data.get("root_path"), data.get("entries") or [])
                    self.send_json(started)
                    return
                if action == "status":
                    self.send_json({"ok": True, "job": storage_browser_download_job_status(data.get("job_id"))})
                    return
                if action == "fetch_job":
                    job = storage_browser_download_job_status(data.get("job_id"))
                    if not job:
                        raise ValueError("Download job not found.")
                    if str(job.get("status") or "") != "ready":
                        raise ValueError("Download job is not ready yet.")
                    self.send_stream(
                        job.get("file_path"),
                        content_type="application/zip",
                        download_name=job.get("archive_name") or "",
                        cleanup_path=job.get("cleanup_path") or "",
                    )
                    return
                download = prepare_storage_browser_download(data.get("root_path"), data.get("entries") or [])
                self.send_stream(
                    download.get("file_path"),
                    content_type=download.get("content_type") or "application/octet-stream",
                    download_name=download.get("download_name") or "",
                    cleanup_path=download.get("cleanup_path") or "",
                )
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
        if path == "/admin/debug-log-command":
            try:
                data = self.read_json_body()
                self.send_json(submit_debug_log_command((data or {}).get("command") or ""))
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/debug-log-complete":
            try:
                data = self.read_json_body()
                self.send_json(
                    build_debug_shell_completion(
                        (data or {}).get("command") or "",
                        (data or {}).get("cursor"),
                    )
                )
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/debug-transfer/plan":
            try:
                data = self.read_json_body()
                entries = (data or {}).get("entries") or (data or {}).get("paths") or (data or {}).get("names") or []
                self.send_json({"ok": True, **build_debug_transfer_plan((data or {}).get("mode") or "", entries)})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/debug-transfer/upload":
            try:
                params = parse_admin_query_params(urlsplit(self.path))
                file_name = params.get("name") or self.headers.get("X-Club3090-File-Name") or ""
                self.send_json(write_debug_transfer_upload(file_name, self.read_raw_body()))
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/debug-transfer/download":
            try:
                data = self.read_json_body()
                download = prepare_debug_transfer_download((data or {}).get("paths") or [])
                self.send_stream(
                    download.get("file_path"),
                    content_type=download.get("content_type") or "application/octet-stream",
                    download_name=download.get("download_name") or "",
                    cleanup_path=download.get("cleanup_path") or "",
                )
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/power":
            try:
                data = self.read_json_body()
                ensure_benchmark_idle("Power action")
                action = data.get("action")
                instance_id = data.get("instance_id")
                log_control(f"POWER action requested action={action} instance={instance_id}")
                if action == "active":
                    out = {"cpu": apply_cpu_active_power(), "gpu": apply_gpu_active_power()}
                elif action == "idle_clocks":
                    out = {"cpu": apply_cpu_idle_power(), "gpu": apply_gpu_idle_power()}
                elif action == "stop_container":
                    if str(instance_id or "").strip().upper() == "GLOBAL":
                        out = global_scope_power_action(action)
                    else:
                        rc, msg = stop_runtime_scope(instance_id=instance_id, mode=data.get("mode"))
                        out = {"container_stop_rc": rc, "container_stop_output": msg, "cpu": apply_cpu_idle_power(), "gpu": apply_gpu_idle_power()}
                elif action == "start_instance":
                    out = global_scope_power_action(action) if str(instance_id or "").strip().upper() == "GLOBAL" else start_instance(instance_id)
                elif action == "restart_instance":
                    if str(instance_id or "").strip().upper() == "GLOBAL":
                        out = global_scope_power_action(action)
                    else:
                        stop_vllm_container("manual_restart", instance_id=instance_id)
                        out = start_instance(instance_id)
                elif action == "toggle_enabled":
                    enabled = bool(data.get("enabled"))
                    if str(instance_id or "").strip().upper() == "GLOBAL":
                        out = global_scope_power_action(action, enabled=enabled)
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
                elif action == "free_gpu":
                    out = {
                        "gpu_resources": free_gpu_runtime_resources(data.get("gpu_index")),
                        "cpu": apply_cpu_idle_power(),
                        "gpu": apply_gpu_idle_power(skip_fans=True),
                    }
                else:
                    raise ValueError("Invalid power action")
                log_audit(
                    "admin_power_action",
                    action=action,
                    instance=instance_id,
                    result_summary=summarize_audit_result(out),
                )
                self.send_json({"ok": True, "action": action, "result": out, "power": power_status(), "focus_log_source": "audit"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/profile":
            try:
                data = self.read_json_body()
                ensure_benchmark_idle("Power profile")
                profile_name = data.get("profile")
                instance_id = str(data.get("instance_id") or "").strip().upper()
                log_control(f"PROFILE request received name={profile_name} instance={instance_id or 'GLOBAL'}")
                out = apply_performance_profile(profile_name)
                log_audit(
                    "admin_profile",
                    profile=profile_name,
                    instance=instance_id or "GLOBAL",
                    result_summary=summarize_audit_result(out),
                )
                self.send_json({"ok": True, "profile": profile_name, "result": out, "power": power_status(), "focus_log_source": "audit"})
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
        if path == "/admin/resource-colors":
            try:
                data = self.read_json_body()
                colors = write_resource_color_config(data.get("resource_colors") or {})
                self.send_json({"ok": True, "resource_colors": colors})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/preset-tps-stats":
            try:
                data = self.read_json_body()
                action = str(data.get("action") or "").strip().lower()
                selector = str(data.get("selector") or data.get("mode") or "").strip()
                if action == "clear":
                    snapshot = clear_preset_tps_stats(selector)
                elif action == "record":
                    snapshot = record_preset_tps_sample(selector, data.get("tps"))
                else:
                    raise ValueError("Unsupported TPS stats action.")
                self.send_json({"ok": True, "preset_tps_stats": snapshot})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/metrics-history":
            try:
                data = self.read_json_body()
                action = str(data.get("action") or "").strip().lower()
                if action != "clear":
                    raise ValueError("Unsupported metrics history action.")
                self.send_json(clear_recorded_metrics_history())
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/log-export":
            try:
                data = self.read_json_body()
                export_payload = export_selected_log(
                    source=data.get("source") or "docker",
                    instance_id=data.get("instance_id") or "",
                    service_id=data.get("service_id") or "",
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
                    if "selected_preset_model" in data:
                        cfg_data["selected_preset_model"] = str(data.get("selected_preset_model") or "").strip()
                    if "hidden_preset_selectors" in data:
                        cfg_data["hidden_preset_selectors"] = list(data.get("hidden_preset_selectors") or [])
                    if "preset_launch_overrides" in data:
                        cfg_data["preset_launch_overrides"] = data.get("preset_launch_overrides") or {}
                    cfg = write_server_config(cfg_data)
                    read_instances_config()
                    if cfg != before_cfg:
                        log_audit(
                            "admin_server_config",
                            allow_proxy_without_api_key=cfg.get("allow_proxy_without_api_key", True),
                            selected_preset_model=cfg.get("selected_preset_model") or "",
                            hidden_preset_selectors=len(cfg.get("hidden_preset_selectors") or []),
                            preset_launch_overrides=len((cfg.get("preset_launch_overrides") or {}).keys()),
                        )
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
                    threading.Thread(
                        target=lambda: (
                            time.sleep(1),
                            subprocess.run(
                                ["systemctl", "reboot"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                timeout=10,
                            ),
                        ),
                        daemon=True,
                    ).start()
                    return
                if action == "force_reboot":
                    log_audit("admin_machine", action="force_reboot")
                    self.send_json({"ok": True, "action": "force_reboot", "message": "Force reboot command accepted"})
                    threading.Thread(
                        target=lambda: (
                            time.sleep(1),
                            subprocess.run(
                                ["bash", "-lc", "echo 1 >/proc/sys/kernel/sysrq; echo b >/proc/sysrq-trigger"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                timeout=10,
                            ),
                        ),
                        daemon=True,
                    ).start()
                    return
                if action == "shutdown":
                    log_audit("admin_machine", action="shutdown")
                    self.send_json({"ok": True, "action": "shutdown", "message": "Shutdown command accepted"})
                    threading.Thread(
                        target=lambda: (
                            time.sleep(1),
                            subprocess.run(
                                ["systemctl", "poweroff"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                timeout=10,
                            ),
                        ),
                        daemon=True,
                    ).start()
                    return
                raise ValueError("Invalid machine action")
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        self.send_error(404)
    def stream_logs(self, parsed, stop_event=None):
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
            if self.admin_stream_stopped(stop_event):
                return
            resolved = resolve_log_source(requested_source, requested, requested_service)
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
                time.sleep(1 if stop_event is not None else 2)
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
                watcher.wait_for_change(client_generation, client_seq, timeout=1 if stop_event is not None else 15)
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
                self.close_connection = True
                return
    def stream_text_file(self, path, empty_message="waiting...", initial_tail_lines=250, stop_event=None):
        sent_reset = False
        offset = 0
        idle_since = time.time()
        while True:
            if self.admin_stream_stopped(stop_event):
                return
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
                self.close_connection = True
                return
            time.sleep(1)
    def stream_dynamic_text_file(self, path_fn, empty_message="waiting...", initial_tail_lines=250, stop_event=None):
        current_path = ""
        sent_reset = False
        offset = 0
        idle_since = time.time()
        tail_lines = int(initial_tail_lines or 0)
        while True:
            if self.admin_stream_stopped(stop_event):
                return
            try:
                next_path = str(path_fn() or "").strip()
                if next_path != current_path:
                    current_path = next_path
                    sent_reset = False
                    offset = 0
                    tail_lines = int(initial_tail_lines or 0)
                if not current_path or not os.path.exists(current_path):
                    if not sent_reset:
                        self.send_sse_event("reset", {"text": str(empty_message or "waiting...").rstrip("\n") + "\n"})
                        sent_reset = True
                    else:
                        self.send_sse_comment()
                    time.sleep(2)
                    continue
                with open(current_path, "r", encoding="utf-8", errors="replace") as f:
                    if offset <= 0:
                        if tail_lines > 0:
                            lines = collections.deque(f, maxlen=tail_lines)
                            text = "".join(lines)
                        else:
                            text = ""
                            f.seek(0, os.SEEK_END)
                        self.send_sse_event("reset", {"text": text or (str(empty_message or "waiting...").rstrip("\n") + "\n")})
                        offset = f.tell()
                        sent_reset = True
                        tail_lines = 0
                        idle_since = time.time()
                    else:
                        size_now = os.path.getsize(current_path)
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
                self.close_connection = True
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
        if path == "/power":
            self.send_json({"ok": True, "power": power_status()})
            return
        if path == "/benchmarks":
            self.send_json({"ok": True, "benchmarks": benchmarks_active_safe_snapshot()})
            return
        if path == "/audit-log":
            tail = int(params.get("tail") or 300)
            match_text = str(params.get("match") or "")
            case_sensitive = str(params.get("case_sensitive") or "").strip().lower() in {"1", "true", "yes", "on"}
            payload = query_text_log_file(AUDIT_LOG_FILE, tail_lines=tail, match_text=match_text, case_sensitive=case_sensitive)
            self.send_bytes(payload.encode("utf-8", errors="replace"), "text/plain; charset=utf-8")
            return
        if path == "/debug-log":
            tail = int(params.get("tail") or 300)
            match_text = str(params.get("match") or "")
            case_sensitive = str(params.get("case_sensitive") or "").strip().lower() in {"1", "true", "yes", "on"}
            payload = query_text_log_file(DEBUG_LOG_FILE, tail_lines=tail, match_text=match_text, case_sensitive=case_sensitive)
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
            if path == "/power":
                ensure_benchmark_idle("Local API power action")
                action = data.get("action")
                instance_id = data.get("instance_id")
                log_control(f"LOCAL POWER action requested action={action} instance={instance_id}")
                if action == "active":
                    out = {"cpu": apply_cpu_active_power(), "gpu": apply_gpu_active_power()}
                elif action == "idle_clocks":
                    out = {"cpu": apply_cpu_idle_power(), "gpu": apply_gpu_idle_power()}
                elif action == "stop_container":
                    if str(instance_id or "").strip().upper() == "GLOBAL":
                        out = global_scope_power_action(action)
                    else:
                        rc, msg = stop_runtime_scope(instance_id=instance_id, mode=data.get("mode"))
                        out = {"container_stop_rc": rc, "container_stop_output": msg, "cpu": apply_cpu_idle_power(), "gpu": apply_gpu_idle_power()}
                elif action == "start_instance":
                    out = global_scope_power_action(action) if str(instance_id or "").strip().upper() == "GLOBAL" else start_instance(instance_id)
                elif action == "restart_instance":
                    if str(instance_id or "").strip().upper() == "GLOBAL":
                        out = global_scope_power_action(action)
                    else:
                        stop_vllm_container("local_api_restart", instance_id=instance_id)
                        out = start_instance(instance_id)
                elif action == "toggle_enabled":
                    enabled = bool(data.get("enabled"))
                    if str(instance_id or "").strip().upper() == "GLOBAL":
                        out = global_scope_power_action(action, enabled=enabled)
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
                elif action == "free_gpu":
                    out = {
                        "gpu_resources": free_gpu_runtime_resources(data.get("gpu_index")),
                        "cpu": apply_cpu_idle_power(),
                        "gpu": apply_gpu_idle_power(skip_fans=True),
                    }
                else:
                    raise ValueError("Invalid power action")
                log_audit(
                    "local_api_power_action",
                    action=action,
                    instance=instance_id,
                    result_summary=summarize_audit_result(out),
                )
                self.send_json({"ok": True, "action": action, "result": out, "power": power_status()})
                return
            if path == "/profile":
                ensure_benchmark_idle("Local API power profile")
                profile_name = data.get("profile")
                instance_id = str(data.get("instance_id") or "").strip().upper()
                log_control(f"LOCAL PROFILE request received name={profile_name} instance={instance_id or 'GLOBAL'}")
                out = apply_performance_profile(profile_name)
                log_audit(
                    "local_api_profile",
                    profile=profile_name,
                    instance=instance_id or "GLOBAL",
                    result_summary=summarize_audit_result(out),
                )
                self.send_json({"ok": True, "profile": profile_name, "result": out, "power": power_status()})
                return
            if path in {"/benchmarks", "/benchmarks/start", "/benchmarks/speed", "/benchmarks/category", "/benchmarks/queue", "/benchmarks/rerun"}:
                default_action = "speed" if path.endswith("/speed") else ("start" if path.endswith("/start") else "")
                if path.endswith("/category"):
                    default_action = "category"
                if path.endswith("/queue"):
                    default_action = "queue"
                if path.endswith("/rerun"):
                    default_action = "rerun"
                action = str(data.get("action") or default_action).strip().lower()
                if action == "rerun":
                    self.send_json({
                        "ok": True,
                        "benchmarks": enqueue_benchmark_rerun(
                            data.get("selector") or "",
                            mode=data.get("mode") or "quick",
                            step_scope=data.get("step_scope") or data.get("metric_id") or data.get("category") or "",
                            selected_stages=data.get("selected_stages") or data.get("stages") or [],
                            append=bool(data.get("append") or str(data.get("position") or "").strip().lower() in {"append", "tail", "end"}),
                        ),
                    })
                    return
                if action == "queue":
                    self.send_json({
                        "ok": True,
                        "benchmarks": update_benchmark_queue(
                            selectors=data.get("selectors") or [],
                            order=data.get("order") or data.get("selectors") or [],
                            stages=data.get("stages") or {},
                        ),
                    })
                    return
                if action in {"", "start", "speed", "category"}:
                    step_scope = (
                        "speed"
                        if action == "speed"
                        else (data.get("metric_id") or data.get("category") or data.get("step_scope") or "")
                    )
                    snapshot = start_benchmark_job(
                        data.get("mode") or "quick",
                        selectors=data.get("selectors") or ([data.get("selector")] if data.get("selector") else None),
                        include_completed=bool(data.get("include_completed", False)),
                        include_deprecated=bool(data.get("include_deprecated", BENCHMARK_INCLUDE_APPROVED_DEPRECATED_BY_DEFAULT)),
                        include_experimental=bool(data.get("include_experimental", BENCHMARK_INCLUDE_EXPERIMENTAL_BY_DEFAULT)),
                        thermal_cooldown=bool(data.get("thermal_cooldown", True)),
                        mock=bool(data.get("mock", False)),
                        step_scope=step_scope,
                        selected_stages=data.get("stages") or {},
                    )
                    self.send_json({"ok": True, "benchmarks": snapshot})
                    return
                if action == "cancel":
                    self.send_json({"ok": True, "benchmarks": cancel_benchmark_job()})
                    return
                if action == "clear":
                    self.send_json({"ok": True, "benchmarks": clear_benchmark_result(data.get("selector") or "")})
                    return
                raise ValueError("Invalid benchmarks action")
            if path == "/benchmarks/cancel":
                self.send_json({"ok": True, "benchmarks": cancel_benchmark_job()})
                return
            if path == "/benchmarks/clear":
                self.send_json({"ok": True, "benchmarks": clear_benchmark_result(data.get("selector") or "")})
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
        self.forward(body, upstream_path, preset_name, cap, instance_id=instance_id)
    def forward(self, body, upstream_path, preset_name, cap, instance_id=None):
        global last_request_finished_at
        start = time.time()
        status = None
        first_chunk_at = None
        last_chunk_at = None
        authoritative_output_tokens = None
        response_usage = {"tokens": 0, "input_tokens": 0, "output_tokens": 0, "tool_calls": 0}
        request_log_metric_peaks = {}
        final_log_metrics = {}
        log_metrics = {}
        log_watcher = None
        log_stream_start_generation = -1
        log_stream_start_seq = 0
        swap_lock_acquired = False
        swap_handled_model = False
        queued_for_swap = False
        original_body = body
        target = get_instance(instance_id) if instance_id else primary_instance()
        target_id = str((target or {}).get("id") or "GLOBAL").strip().upper()
        target_spec = resolve_variant_spec(target.get("mode")) if target else resolve_variant_spec(active_mode())
        if benchmark_job_active():
            self.send_json({
                "error": "Model Scores benchmarking is active; proxy inference is temporarily disabled.",
                "benchmarks": read_benchmark_state(),
            }, 503)
            return
        is_completion_request = body is not None and proxy_completion_path(upstream_path)
        server_swap_enabled = proxy_swap_feature_enabled()
        requested_selector = proxy_requested_selector(body, preset_name) if is_completion_request else ""
        requested_target = None
        requested_spec = None
        if requested_selector:
            requested_target, requested_spec = proxy_running_target_for_selector(requested_selector, instance_id=instance_id)
            if requested_target:
                target = requested_target
                target_spec = requested_spec or target_spec
            elif server_swap_enabled:
                target_spec = requested_spec or resolve_variant_spec(requested_selector) or target_spec
        if is_completion_request:
            body = apply_preset(body, preset_name, cap, target_spec)
            if requested_selector and requested_target:
                body = proxy_rewrite_body_model_for_selector(body, requested_selector)
        request_usage = extract_request_usage(body) if body is not None and is_quota_counted_path(upstream_path) else {}
        auth_result = authorize_proxy_request(self.headers, instance_id, upstream_path, request_usage=request_usage)
        if auth_result[0] is False:
            _, code, payload = auth_result
            self.send_json(payload, code)
            return
        auth_context = auth_result[1]
        if is_completion_request and requested_selector and not requested_target:
            requested_target, requested_spec = proxy_running_target_for_selector(requested_selector, instance_id=instance_id)
            if requested_target:
                target = requested_target
                target_spec = requested_spec or target_spec
                body = apply_preset(original_body, preset_name, cap, target_spec)
                body = proxy_rewrite_body_model_for_selector(body, requested_selector)
                request_usage = extract_request_usage(body) if is_quota_counted_path(upstream_path) else request_usage
        swap_allowed = bool(server_swap_enabled and (auth_context.get("permissions") or {}).get("proxy_swap"))
        if is_completion_request and requested_selector and not requested_target and server_swap_enabled and not swap_allowed:
            log_audit(
                "proxy_swap_denied",
                reason="permission_missing",
                user=auth_context.get("user_name") or "anonymous",
                requested_model=requested_selector,
                path=upstream_path,
            )
            self.send_json({
                "error": "API key is not allowed to auto-load inactive presets through the proxy.",
                "requested_model": requested_selector,
                "permission": "proxy_swap",
            }, 403)
            return
        if is_completion_request and requested_selector and not requested_target and swap_allowed:
            target_spec = requested_spec or resolve_variant_spec(requested_selector) or target_spec
            body = apply_preset(original_body, preset_name, cap, target_spec)
            body = proxy_rewrite_body_model_for_selector(body, requested_selector)
            request_usage = extract_request_usage(body) if is_quota_counted_path(upstream_path) else request_usage
        with metrics_lock:
            metrics["total_requests"] += 1
            metrics["active_requests"] += 1
            metrics["last_preset"] = preset_name or "raw"
            metrics["last_path"] = self.path
        needs_model = upstream_path.startswith("/v1/models") or is_completion_request
        try:
            if needs_model:
                if is_completion_request and requested_selector and swap_allowed:
                    live_target, live_spec = proxy_running_target_for_selector(requested_selector, instance_id=instance_id)
                    if live_target:
                        target = live_target
                        target_spec = live_spec or target_spec
                        swap_handled_model = True
                    else:
                        with metrics_lock:
                            metrics["queued_requests"] += 1
                            request_queue.append({"time": time.strftime("%H:%M:%S"), "path": self.path, "preset": requested_selector, "instance": target_id, "state": "proxy-swap"})
                        if not proxy_swap_lock.acquire(timeout=1800):
                            with metrics_lock:
                                metrics["queued_requests"] = max(0, metrics["queued_requests"] - 1)
                            raise TimeoutError(f"Timed out waiting for proxy swap queue before loading {requested_selector}")
                        swap_lock_acquired = True
                        try:
                            live_target, live_spec = proxy_running_target_for_selector(requested_selector, instance_id=instance_id)
                            if live_target:
                                target = live_target
                                target_spec = live_spec or target_spec
                            else:
                                queued_for_swap = True
                                self.queue_header("X-Club3090-Queued", "true")
                                self.queue_header("X-Club3090-Queued-Reason", "preset-load")
                                self.queue_header("X-Club3090-Target-Model", requested_selector)
                                log_control(f"PROXY queued preset swap requested={requested_selector} instance={target_id} path={self.path}")
                                target, target_spec = ensure_proxy_swap_target(requested_selector, instance_id=instance_id)
                            swap_handled_model = True
                        finally:
                            with metrics_lock:
                                metrics["queued_requests"] = max(0, metrics["queued_requests"] - 1)
                if not swap_handled_model:
                    with metrics_lock:
                        metrics["queued_requests"] += 1
                        request_queue.append({"time": time.strftime("%H:%M:%S"), "path": self.path, "preset": preset_name or "raw", "instance": target_id})
                    try:
                        ensure_vllm_running_for_request(target["id"] if target else None)
                    finally:
                        with metrics_lock:
                            metrics["queued_requests"] = max(0, metrics["queued_requests"] - 1)
        except Exception as startup_error:
            status = 502
            latency = round(time.time() - start, 3)
            if swap_lock_acquired:
                try:
                    proxy_swap_lock.release()
                except RuntimeError:
                    pass
                swap_lock_acquired = False
            with metrics_lock:
                metrics["queued_requests"] = max(0, metrics["queued_requests"] - 1)
                metrics["active_requests"] = max(0, metrics["active_requests"] - 1)
                metrics["failed_requests"] += 1
                metrics["last_latency_s"] = latency
                metrics["last_status"] = status
            record_user_usage(auth_context.get("user_name"), auth_context.get("count_request", False), status, request_usage, response_usage, latency)
            log_control(f"PROXY startup failed requested={requested_selector or ''} instance={target_id} queued={queued_for_swap} error={startup_error}")
            self.send_json({
                "error": str(startup_error),
                "queued": bool(queued_for_swap),
                "requested_model": requested_selector,
                "active_mode": active_mode(),
                "active_port": active_port(),
            }, 502)
            return
        target_id = str((target or {}).get("id") or "GLOBAL").strip().upper()
        target_metrics_key = str(target_id or "").strip().upper()
        with metrics_lock:
            target_request_metrics.setdefault(target_metrics_key, default_target_request_metrics())
        if target and target.get("container"):
            log_watcher = get_runtime_log_watcher(target.get("container"))
            if log_watcher is not None:
                log_snapshot = log_watcher.snapshot()
                log_stream_start_generation = int(log_snapshot.get("generation") or 0)
                log_stream_start_seq = int(log_snapshot.get("seq") or 0)
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
                content_type = r.headers.get("Content-Type","")
                stream_mode = "text/event-stream" in content_type.lower()
                allow_visible_thinking = payload_allows_visible_thinking(
                    json.loads(body.decode("utf-8", errors="ignore") or "{}")
                ) if body is not None and upstream_path.startswith("/v1/chat/completions") else True
                if stream_mode:
                    self.send_response(r.status)
                    for k,v in r.headers.items():
                        if k.lower() not in HOP_HEADERS:
                            self.send_header(k,v)
                    self.emit_pending_headers()
                    self.send_header("X-Club3090-Instance", target_id)
                    self.send_header("Connection","close")
                    self.end_headers()
                    with metrics_lock:
                        metrics["streaming_requests"] += 1
                total_bytes = bytearray()
                if stream_mode:
                    while True:
                        chunk = r.read1(8192) if hasattr(r, "read1") else r.read(8192)
                        if not chunk:
                            break
                        if first_chunk_at is None:
                            first_chunk_at = time.time()
                        last_chunk_at = time.time()
                        if len(total_bytes) < 2000000:
                            total_bytes.extend(chunk)
                        self.wfile.write(chunk)
                        self.wfile.flush()
                else:
                    payload_bytes = r.read()
                    if payload_bytes:
                        first_chunk_at = time.time()
                        last_chunk_at = first_chunk_at
                        if len(total_bytes) < 2000000:
                            total_bytes.extend(payload_bytes)
                    payload_bytes = sanitize_chat_completion_response_bytes(
                        payload_bytes,
                        allow_visible_thinking,
                    )
                    self.send_response(r.status)
                    for k,v in r.headers.items():
                        if k.lower() not in HOP_HEADERS and k.lower() != "content-length":
                            self.send_header(k,v)
                    self.emit_pending_headers()
                    self.send_header("Content-Length", str(len(payload_bytes)))
                    self.send_header("X-Club3090-Instance", target_id)
                    self.send_header("Connection","close")
                    self.end_headers()
                    if payload_bytes:
                        self.wfile.write(payload_bytes)
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
                authoritative_output_tokens = max(
                    int(authoritative_output_tokens or 0),
                    int(parsed_usage.get("output_tokens") or 0),
                ) or authoritative_output_tokens
                for key in ("tokens", "input_tokens", "output_tokens", "tool_calls"):
                    response_usage[key] = max(int(response_usage.get(key) or 0), int(parsed_usage.get(key) or 0))
        except urllib.error.HTTPError as e:
            status = e.code
            payload = e.read()
            parsed_usage = extract_response_usage(payload)
            authoritative_output_tokens = max(
                int(authoritative_output_tokens or 0),
                int(parsed_usage.get("output_tokens") or 0),
            ) or authoritative_output_tokens
            for key in ("tokens", "input_tokens", "output_tokens", "tool_calls"):
                response_usage[key] = max(int(response_usage.get(key) or 0), int(parsed_usage.get(key) or 0))
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type","text/plain"))
            self.emit_pending_headers()
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
                    if target and target_id != "GLOBAL":
                        start_instance(target["id"])
                    else:
                        run_switch(str((target or {}).get("mode") or active_mode()))
                    retry_url = f"http://127.0.0.1:{instance_runtime_port(target) if target else active_port()}" + upstream_path
                    retry_req = urllib.request.Request(retry_url, data=body, headers=headers, method=self.command)
                    with urllib.request.urlopen(retry_req, timeout=None) as r2:
                        status = r2.status
                        self.send_response(r2.status)
                        for k,v in r2.headers.items():
                            if k.lower() not in HOP_HEADERS:
                                self.send_header(k,v)
                        self.emit_pending_headers()
                        self.send_header("X-Club3090-Instance", target_id)
                        self.send_header("Connection","close")
                        self.end_headers()
                        retry_bytes = bytearray()
                        while True:
                            chunk = r2.read1(8192) if hasattr(r2, "read1") else r2.read(8192)
                            if not chunk:
                                break
                            if first_chunk_at is None:
                                first_chunk_at = time.time()
                            last_chunk_at = time.time()
                            if len(retry_bytes) < 2000000:
                                retry_bytes.extend(chunk)
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        parsed_retry_usage = extract_response_usage(bytes(retry_bytes))
                        authoritative_output_tokens = max(
                            int(authoritative_output_tokens or 0),
                            int(parsed_retry_usage.get("output_tokens") or 0),
                        ) or authoritative_output_tokens
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
            prompt_tokens = int(response_usage.get("input_tokens") or 0) or int(request_usage.get("input_tokens") or 0)
            output_tokens = int(response_usage.get("output_tokens") or 0)
            if output_tokens <= 0:
                output_tokens = max(0, int(response_usage.get("tokens") or 0) - int(prompt_tokens))
            total_tokens = int(response_usage.get("tokens") or 0)
            if total_tokens <= 0:
                total_tokens = int(prompt_tokens) + int(output_tokens)
            tool_calls = int(response_usage.get("tool_calls") or 0)
            if log_watcher is not None:
                request_log_metric_peaks = collect_request_window_log_metric_peaks(
                    log_watcher,
                    log_stream_start_generation,
                    log_stream_start_seq,
                )
            final_log_metrics = (
                settle_runtime_log_metrics_for_container(target.get("container"))
                if target and target.get("container")
                else {}
            )
            log_metrics = merge_runtime_metric_peaks(final_log_metrics, request_log_metric_peaks)
            ttft = round(first_chunk_at - start, 3) if first_chunk_at else None
            display_tps = resolve_best_generation_tps(
                resolve_request_generation_tps(
                    request_log_metric_peaks,
                    final_log_metrics,
                    log_metrics,
                ),
                authoritative_output_tokens,
                output_tokens,
                first_chunk_at,
                last_chunk_at,
            )
            prompt_tps = derive_request_prompt_tps(
                prompt_tokens,
                output_tokens,
                ttft,
                latency,
                display_tps,
                request_log_metric_peaks.get("prompt_tps"),
                final_log_metrics.get("prompt_tps"),
                log_metrics.get("prompt_tps"),
            )
            with metrics_lock:
                metrics["active_requests"] = max(0, metrics["active_requests"] - 1)
                if metrics["active_requests"] <= 0:
                    last_request_finished_at = time.time()
                metrics["completed_requests"] += 1
                if status is None or int(status) >= 400:
                    metrics["failed_requests"] += 1
                metrics["last_latency_s"] = latency
                metrics["last_status"] = status
                if ttft is not None:
                    metrics["last_ttft_s"] = ttft
                if display_tps not in (None, "", 0, 0.0):
                    metrics["last_tokens_per_second"] = display_tps
                recent_requests.appendleft({"time":time.strftime("%H:%M:%S"),"status":status,"latency_s":latency,"preset":preset_name or "raw","path":self.path,"upstream":upstream_path,"instance":target_id,"user":auth_context.get("user_name") or "anonymous"})
                target_row = dict(target_request_metrics.get(target_metrics_key) or default_target_request_metrics())
                target_row["last_status"] = status
                target_row["last_latency_s"] = latency
                if ttft is not None:
                    target_row["last_ttft_s"] = ttft
                target_row["last_prompt_tps"] = prompt_tps
                if display_tps not in (None, "", 0, 0.0):
                    target_row["last_tokens_per_second"] = display_tps
                target_row["last_gpu_kv_cache_usage_pct"] = log_metrics.get("gpu_kv_cache_usage_pct")
                target_row["last_cpu_kv_cache_usage_pct"] = log_metrics.get("cpu_kv_cache_usage_pct")
                target_row["last_prefix_cache_hit_rate_pct"] = log_metrics.get("prefix_cache_hit_rate_pct")
                target_row["last_speculative"] = dict(log_metrics.get("speculative") or {})
                target_row["last_input_tokens"] = prompt_tokens
                target_row["last_output_tokens"] = output_tokens
                target_row["last_total_tokens"] = total_tokens
                target_row["last_tool_calls"] = tool_calls
                target_row["last_preset"] = preset_name or "raw"
                target_row["last_path"] = self.path
                target_row["last_request_at"] = int(time.time())
                target_request_metrics[target_metrics_key] = target_row
            if (
                status is not None
                and int(status or 0) < 400
                and display_tps not in (None, "", 0, 0.0)
                and (upstream_path.startswith("/v1/chat/completions") or upstream_path.startswith("/v1/completions"))
            ):
                record_preset_tps_sample(str((target or {}).get("mode") or active_mode()), display_tps)
            record_user_usage(auth_context.get("user_name"), auth_context.get("count_request", False), status, request_usage, response_usage, latency)
            log_control(f"REQ user={(auth_context.get('user_name') or 'anonymous')} instance={target_id} status={status} latency={latency}s preset={preset_name or 'raw'} path={self.path} upstream={upstream_path} input_tokens={prompt_tokens} output_tokens={output_tokens} total_tokens={total_tokens} tool_calls={tool_calls}")
            if swap_lock_acquired:
                try:
                    proxy_swap_lock.release()
                except RuntimeError:
                    pass
                if queued_for_swap:
                    log_control(f"PROXY queued preset swap completed requested={requested_selector} instance={target_id} status={status}")

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

def startup_power_primer_blocked_by_benchmark():
    try:
        state = read_benchmark_state()
        if state.get("active") or benchmark_worker_service_active():
            log_control("STARTUP power primer skipped because a benchmark worker is active")
            append_benchmark_log("[startup] control power primer skipped while benchmark worker is active")
            return True
    except Exception as e:
        log_control(f"STARTUP benchmark power-primer check error: {e}")
    return False

def startup_power_primer():
    if startup_power_primer_blocked_by_benchmark():
        return
    try:
        restore_persisted_performance_profile(apply_now=False)
        apply_cpu_active_power()
    except Exception as e:
        log_control(f"STARTUP cpu power primer error: {e}")
    try:
        apply_gpu_active_power(skip_fans=True)
    except Exception as e:
        log_control(f"STARTUP gpu power primer error: {e}")
    try:
        restore_persisted_fan_state(apply_now=True)
    except Exception as e:
        log_control(f"STARTUP fan state restore error: {e}")

def start_control_background_loops():
    def metrics_bootstrap():
        try:
            ensure_metrics_history_loaded()
        except Exception as e:
            log_control(f"metrics history load error: {e}")
        try:
            build_series_point()
        except Exception as e:
            log_control(f"initial metrics snapshot error: {e}")
        metrics_collector()

    def status_bootstrap():
        try:
            refresh_status_snapshot()
        except Exception as e:
            log_control(f"initial status snapshot error: {e}")
        status_snapshot_collector()

    def docker_logrotate_bootstrap():
        try:
            refresh_docker_logrotate_config()
        except Exception as e:
            log_control(f"docker logrotate bootstrap error: {e}")
        docker_logrotate_refresher()

    def model_update_check_bootstrap():
        time.sleep(20)
        while True:
            try:
                run_model_update_check("scheduled")
            except Exception as e:
                log_control(f"model update check error: {e}")
            time.sleep(max(300, int(MODEL_UPDATE_CHECK_INTERVAL_SECONDS or 3600)))

    threading.Thread(target=idle_watchdog, daemon=True).start()
    threading.Thread(target=image_studio_power_watchdog, daemon=True).start()
    threading.Thread(target=metrics_bootstrap, daemon=True).start()
    threading.Thread(target=status_bootstrap, daemon=True).start()
    threading.Thread(target=docker_logrotate_bootstrap, daemon=True).start()
    threading.Thread(target=model_update_check_bootstrap, daemon=True).start()
    threading.Thread(target=startup_power_primer, daemon=True).start()

def startup_runtime_inventory_bootstrap():
    try:
        inventory_exists = os.path.exists(RUNTIME_INVENTORY_FILE)
        inventory = load_runtime_inventory(force=not inventory_exists, rebuild_if_missing=not inventory_exists)
        if not (isinstance(inventory, dict) and inventory.get("variants")):
            log_control("STARTUP runtime inventory cache missing or empty; background rebuild starting")
            inventory = rebuild_runtime_inventory()
        if resolve_variant_spec(DEFAULT_MODE) and read_active_mode_file() is None:
            write_active_mode(DEFAULT_MODE)
        read_instances_config()
        log_control(f"STARTUP runtime inventory ready models={len((inventory or {}).get('models') or [])} variants={len((inventory or {}).get('variants') or [])}")
    except Exception as e:
        log_control(f"STARTUP runtime inventory bootstrap error: {e}")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--audit-log":
        emit_cli_log_query(AUDIT_LOG_FILE, sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--debug-log":
        emit_cli_log_query(DEBUG_LOG_FILE, sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--control-log":
        emit_cli_log_query(CONTROL_LOG_FILE, sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--refresh-docker-logrotate":
        ok = refresh_docker_logrotate_config()
        print(json.dumps({"ok": bool(ok), "path": DOCKER_LOGROTATE_FILE, "retention_days": max(1, int(DOCKER_LOG_RETENTION_DAYS or 7))}))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--docker-pull-space-preflight":
        cli_docker_pull_space_preflight(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--docker-compose-pull-space-preflight":
        cli_docker_compose_pull_space_preflight(sys.argv[2:])
        return
    os.makedirs(CONTROL_DIR, exist_ok=True)
    os.makedirs(INSTANCES_DIR, exist_ok=True)
    ensure_runtime_config_file()
    ensure_code_syntax_config_file()
    restore_persisted_performance_profile(apply_now=False)
    restore_persisted_fan_state(apply_now=False)
    write_server_config(read_server_config())
    ensure_local_api_token()
    if len(sys.argv) > 1 and sys.argv[1] == "--benchmark-worker":
        run_benchmark_worker_service()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--rederive-benchmark-scores":
        load_runtime_inventory(force=not os.path.exists(RUNTIME_INVENTORY_FILE), rebuild_if_missing=True)
        print(json.dumps(rederive_benchmark_scores(force="--force" in sys.argv[2:]), ensure_ascii=False))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup-benchmark-global-results":
        print(json.dumps(benchmark_archive_unreferenced_global_results(reason="cli"), ensure_ascii=False))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--rebuild-benchmark-inventory":
        load_runtime_inventory(force=not os.path.exists(RUNTIME_INVENTORY_FILE), rebuild_if_missing=True)
        rebuilt = benchmark_rebuild_inventory_state_file(reason="cli")
        print(json.dumps(benchmark_compact_inventory_state_summary(rebuilt), ensure_ascii=False))
        return
    recover_benchmark_state_on_startup()
    # Hard fail early if an update somehow produced an incomplete control script.
    # This specifically guards the proxy/autostart path that depends on port_open().
    if not callable(globals().get("port_open")):
        raise RuntimeError("internal install error: port_open() is not defined")
    if len(sys.argv) > 1 and sys.argv[1] == "--migrate-custom-presets":
        backup_dir = sys.argv[2] if len(sys.argv) > 2 else ""
        result = migrate_missing_custom_presets_from_backup(backup_dir)
        benchmark_archive_unreferenced_global_results(reason="custom-preset-migration")
        benchmark_rebuild_inventory_state_file(reason="custom preset migration")
        print(json.dumps(result))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--rebuild-inventory":
        rebuilt = rebuild_runtime_inventory()
        print(json.dumps({"ok": True, "models": len(rebuilt.get("models") or []), "variants": len(rebuilt.get("variants") or [])}))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--boot-enabled-instances":
        load_runtime_inventory(force=not os.path.exists(RUNTIME_INVENTORY_FILE), rebuild_if_missing=True)
        boot_enabled_instances()
        return
    log_control("control service starting")
    cfg = read_server_config()
    admin_server = build_server(ADMIN_BIND_PORT, AdminHandler, ADMIN_BIND_HOST)
    if cfg.get("local_api_enabled", False):
        local_api_port = int(cfg.get("local_api_port", LOCAL_API_PORT))
        local_api_server = build_server(local_api_port, LocalApiHandler, "127.0.0.1")
        threading.Thread(target=serve, args=(local_api_server, "local-api"), daemon=True).start()
    proxy_server = build_server(PROXY_BIND_PORT, ProxyHandler, PROXY_BIND_HOST)
    threading.Thread(target=serve, args=(proxy_server, "proxy"), daemon=True).start()
    threading.Thread(target=startup_runtime_inventory_bootstrap, daemon=True).start()
    start_control_background_loops()
    serve(admin_server, "admin")

if __name__ == "__main__":
    main()
