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
                    self.wfile.write(chunk)
        finally:
            if cleanup_path:
                try:
                    os.remove(cleanup_path)
                except Exception:
                    pass

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
            html = get_admin_html_template().replace("__SCRIPT_VERSION__", SCRIPT_VERSION).replace(":8008/admin", f":{ADMIN_PORT}/admin").replace(":8009", f":{PROXY_PORT}")
            self.queue_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.queue_header("Pragma", "no-cache")
            self.send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/admin/status":
            params = parse_admin_query_params(parsed)
            force = str(params.get("force") or "").strip().lower() in {"1", "true", "yes", "on"}
            request_options = parse_status_request_options(params)
            started_at = time.time()
            payload = shape_status_snapshot(get_status_snapshot(force=force), request_options)
            payload["access_hint"] = tailscale_access_hint_for_client(self.client_address[0] if self.client_address else "")
            elapsed = time.time() - started_at
            if elapsed >= 1.0 or payload.get("status_error"):
                log_control(f"ADMIN status served force={force} elapsed={round(elapsed, 3)}s status_error={bool(payload.get('status_error'))}")
            self.send_json(payload)
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
        if path == "/admin/debug-stream":
            params = parse_admin_query_params(parsed)
            self.close_connection = False
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache")
            self.send_header("Connection","keep-alive")
            self.emit_pending_headers()
            self.end_headers()
            self.stream_text_file(DEBUG_LOG_FILE, "no debug entries yet; waiting...", initial_tail_lines=parse_tail_lines_param(params, 250))
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
                data = self.read_json_body()
                result = delete_preset_caches(data.get("selector"), data.get("variant_id"))
                self.send_json({**result, "focus_log_source": "audit"}, 200 if result.get("ok") else 500)
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/custom-models":
            try:
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
        if path == "/admin/benchmark":
            try:
                data = self.read_json_body()
                job = start_admin_task_job("benchmark", data.get("instance_id"))
                self.send_json({"ok": True, "admin_task_job": job, "focus_log_source": "audit"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/run-report":
            try:
                data = self.read_json_body()
                job = start_admin_task_job("report", data.get("instance_id"))
                self.send_json({"ok": True, "admin_task_job": job, "focus_log_source": "audit"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/rebench":
            try:
                data = self.read_json_body()
                job = start_admin_task_job("rebench", data.get("instance_id"), data.get("variant"))
                self.send_json({"ok": True, "admin_task_job": job, "focus_log_source": "audit"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/update":
            try:
                data = self.read_json_body()
                result = start_self_update_job(data.get("scope"), data.get("target_commit"))
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
                if action == "save_file":
                    self.send_json(save_storage_browser_file(data.get("root_path"), data.get("relative_path") or "", data.get("text") or ""))
                    return
                if action == "save_binary_file":
                    self.send_json(save_storage_browser_binary_file(data.get("root_path"), data.get("relative_path") or "", data.get("hex") or ""))
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
        target = get_instance(instance_id) if instance_id else primary_instance()
        target_id = target["id"] if target else "GLOBAL"
        target_spec = resolve_variant_spec(target.get("mode")) if target else resolve_variant_spec(active_mode())
        if body is not None and (upstream_path.startswith("/v1/chat/completions") or upstream_path.startswith("/v1/completions")):
            body = apply_preset(body, preset_name, cap, target_spec)
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
        if target and target.get("container"):
            log_watcher = get_runtime_log_watcher(target.get("container"))
            if log_watcher is not None:
                log_snapshot = log_watcher.snapshot()
                log_stream_start_generation = int(log_snapshot.get("generation") or 0)
                log_stream_start_seq = int(log_snapshot.get("seq") or 0)
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
        restore_persisted_performance_profile(apply_now=False)
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
    os.makedirs(CONTROL_DIR, exist_ok=True)
    os.makedirs(INSTANCES_DIR, exist_ok=True)
    ensure_code_syntax_config_file()
    restore_persisted_performance_profile(apply_now=False)
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
