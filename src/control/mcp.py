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


