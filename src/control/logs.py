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
    instance = get_instance(requested) if requested else primary_instance()
    container = instance_runtime_container_name(instance) if instance else current_container()
    return instance, container


def resolve_log_source(source="docker", instance_id="", service_id=""):
    source_name = str(source or "docker").strip().lower()
    if source_name == "audit":
        return {"source": "audit", "instance": None, "container": "", "service": {}, "label": "Audit"}
    if source_name == "debug":
        return {"source": "debug", "instance": None, "container": "", "service": {}, "label": "Debug"}
    if source_name == "benchmarks":
        return {"source": "benchmarks", "instance": None, "container": "", "service": {}, "label": "Benchmarks"}
    if source_name == "script":
        return {"source": "script", "instance": None, "container": "", "service": {}, "label": "Script"}
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


def read_selected_log_snapshot(source="docker", instance_id="", service_id="", tail_lines=250):
    resolved = resolve_log_source(source, instance_id, service_id)
    source_name = str(resolved.get("source") or "docker")
    if source_name == "audit":
        return {
            "source": source_name,
            "signature": "audit",
            "text": query_text_log_file(AUDIT_LOG_FILE, tail_lines=tail_lines),
        }
    if source_name == "debug":
        return {
            "source": source_name,
            "signature": "debug",
            "text": query_text_log_file(DEBUG_LOG_FILE, tail_lines=tail_lines),
        }
    if source_name == "benchmarks":
        return {
            "source": source_name,
            "signature": "benchmarks",
            **benchmark_log_only_snapshot(tail_lines=tail_lines),
        }
    if source_name == "script":
        return script_log_snapshot(tail_lines=tail_lines)
    if source_name == "service":
        service = resolved.get("service") or {}
        service_id_text = str(service.get("id") or service_id or "").strip().lower()
        container = str(resolved.get("container") or "").strip()
        text = ""
        if container:
            watcher = get_runtime_log_watcher(container)
            if watcher is not None:
                text = str((watcher.snapshot() or {}).get("text") or "")
            if not text:
                text, _ = _docker_logs_tail_snapshot(container, lines=tail_lines, timeout=4)
        return {
            "source": source_name,
            "signature": f"service:{service_id_text}",
            "text": text or f"no active {str(resolved.get('label') or service_id_text or 'service').strip()} log source found; waiting...\n",
        }
    instance = resolved.get("instance") or {}
    container = str(resolved.get("container") or "").strip()
    signature_id = str(instance.get("id") or (str(instance_id or "").strip().upper() or "primary"))
    text = ""
    if container:
        watcher = get_runtime_log_watcher(container)
        if watcher is not None:
            text = str((watcher.snapshot() or {}).get("text") or "")
        if not text:
            text, _ = _docker_logs_tail_snapshot(container, lines=tail_lines, timeout=4)
    return {
        "source": "docker",
        "signature": f"docker:{signature_id or 'primary'}",
        "text": text or f"no active {str(resolved.get('label') or signature_id or 'docker').strip()} log source found; waiting...\n",
    }


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
            output, snapshot_error = _docker_logs_tail_snapshot(
                self.container_name,
                lines=tail_lines if tail_lines > 0 else 1,
                include_timestamps=True,
                timeout=max(1.0, float(LOG_INITIAL_SNAPSHOT_TIMEOUT_SECONDS or 15)),
            )
            if tail_lines <= 0:
                output = ""
        except Exception as e:
            self._set_status(f"could not load docker logs for {self.container_name}: {e}")
            return "", ""
        if not output and snapshot_error:
            self._set_status(f"could not load docker logs for {self.container_name}: {snapshot_error}")
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

    def _follow_docker_json_log(self, log_path):
        path = str(log_path or "").strip()
        if not path:
            return False
        try:
            offset = os.path.getsize(path)
        except Exception:
            return False
        while True:
            if self.container_name not in docker_names(all_containers=False):
                self._set_status(f"{self.container_name} is not running; waiting...")
                return True
            next_path = _docker_log_path(self.container_name)
            if next_path and os.path.abspath(str(next_path)) != os.path.abspath(path):
                self._set_status(f"log path for {self.container_name} rotated; reconnecting...")
                return True
            try:
                size_now = os.path.getsize(path)
            except Exception:
                self._set_status(f"log file for {self.container_name} is unavailable; reconnecting...")
                return True
            if size_now < offset:
                self._set_status(f"log file for {self.container_name} was truncated; reconnecting...")
                return True
            if size_now > offset:
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as handle:
                        handle.seek(offset)
                        chunk = handle.read()
                        offset = handle.tell()
                except Exception as exc:
                    self._set_status(f"could not follow {self.container_name} log file: {exc}")
                    return True
                for entry in str(chunk or "").splitlines():
                    try:
                        payload = json.loads(entry)
                    except Exception:
                        continue
                    clean = str(payload.get("log") or "").rstrip("\n")
                    stamp = str(payload.get("time") or "").strip()
                    self._append_line(clean, timestamp=stamp)
            time.sleep(0.5)

    def _follow_docker_logs_command(self, last_timestamp="", last_line=""):
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
        return True

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
                log_path = _docker_log_path(self.container_name)
                if log_path and os.path.exists(log_path):
                    self._follow_docker_json_log(log_path)
                else:
                    self._follow_docker_logs_command(last_timestamp, last_line)
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
