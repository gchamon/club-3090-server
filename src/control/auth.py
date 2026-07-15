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


def normalize_permissions(raw):
    data = raw if isinstance(raw, dict) else {}
    permissions = data.get("permissions") if isinstance(data.get("permissions"), dict) else data
    permissions = permissions if isinstance(permissions, dict) else {}
    return {
        "proxy_swap": bool(
            permissions.get("proxy_swap")
            or permissions.get("allow_proxy_swap")
            or data.get("proxy_swap")
            or data.get("allow_proxy_swap")
        ),
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


def normalize_allowed_target_entry(value):
    item = str(value or "").strip()
    if not item:
        return ""
    item_upper = item.upper()
    item_lower = item.lower()
    if item == "*" or item_lower == "all":
        return "*"
    if item_lower == "legacy":
        return "GLOBAL"
    if item_upper == "GLOBAL":
        return "GLOBAL"
    if re.fullmatch(r"GPU[0-9]+", item_upper):
        return item_upper
    if re.fullmatch(r"PAIR[0-9]+_[0-9]+", item_upper):
        pair = parse_instance_identifier(item_upper)
        return str((pair or {}).get("id") or "")
    raise ValueError("Allowed targets must be *, GLOBAL, GPU<n>, or PAIRx_y")


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
        normalized_target = normalize_allowed_target_entry(item)
        if normalized_target:
            allowed_clean.append(normalized_target)
    if not allowed_clean:
        allowed_clean = ["*"]
    limits_raw = raw.get("limits") if isinstance(raw.get("limits"), dict) else raw
    limits = normalize_limits(limits_raw)
    permissions = normalize_permissions(raw)
    return {
        "name": name,
        "enabled": bool(raw.get("enabled", True)),
        "created_at": int(raw.get("created_at") or time.time()),
        "description": str(raw.get("description") or "").strip(),
        "allowed_targets": sorted(set(allowed_clean), key=lambda x: ("*" not in x, x)),
        "limits": limits,
        "permissions": permissions,
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
        "permissions": normalize_permissions(group.get("permissions") or {}),
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
        normalized_target = normalize_allowed_target_entry(item)
        if normalized_target:
            allowed_clean.append(normalized_target)
    if not allowed_clean:
        allowed_clean = ["*"]
    groups = normalize_group_names(raw.get("groups"))
    limits_raw = raw.get("limits") if isinstance(raw.get("limits"), dict) else raw
    limits = normalize_limits(limits_raw)
    permissions = normalize_permissions(raw)
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
        "permissions": permissions,
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


def effective_permissions(user):
    merged = normalize_permissions(user.get("permissions") or {})
    for group in effective_group_records(user):
        group_permissions = normalize_permissions(group.get("permissions") or {})
        for key, value in group_permissions.items():
            merged[key] = bool(merged.get(key) or value)
    return merged


def public_user_view(user):
    usage = user.get("usage") or default_user_usage()
    now = int(time.time())
    effective_targets = effective_allowed_targets(user)
    merged_limits = effective_limits(user)
    merged_permissions = effective_permissions(user)
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
        "permissions": normalize_permissions(user.get("permissions") or {}),
        "effective_permissions": merged_permissions,
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
        "permissions": payload.get("permissions", existing.get("permissions", {}) if existing else {}),
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
        "permissions": payload.get("permissions", existing.get("permissions", {}) if existing else {}),
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
    if primary:
        return str(primary["id"]).upper()
    current_mode_value = canonical_mode_selector(active_mode())
    current_spec = resolve_variant_spec(current_mode_value) or {}
    if str(current_spec.get("scope_kind") or "").strip().lower() in {"dual", "multi", "global_only"}:
        return "GLOBAL"
    return "GLOBAL"


def target_gpu_labels(target_id):
    target_id = str(target_id or "").strip().upper()
    if target_id == "GLOBAL":
        return [f"GPU{idx}" for idx in range(max(0, int(detect_gpu_count_runtime() or 0)))]
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
    if raw_key and user is None:
        log_audit("proxy_auth_denied", reason="invalid_api_key", target=target_id, path=upstream_path)
        return False, 401, {"error": "Invalid API key"}
    if user is not None:
        if not user_can_access_target(user, target_id):
            log_audit("proxy_access_denied", reason="target_not_allowed", user=user["name"], target=target_id, path=upstream_path)
            return False, 403, {"error": "API key is not allowed to access this backend", "target": target_id}
        err = user_limit_error(user, count_request=count_request, request_usage=request_usage)
        if err:
            log_audit("proxy_quota_denied", user=user["name"], target=target_id, path=upstream_path, reason=err)
            return False, 429, {"error": err, "user": user["name"]}
        permissions = effective_permissions(user)
        return True, {"mode": "user", "user_name": user["name"], "target_id": target_id, "count_request": count_request, "permissions": permissions}
    if cfg.get("allow_proxy_without_api_key", True):
        return True, {"mode": "anonymous", "user_name": None, "target_id": target_id, "count_request": False, "permissions": normalize_permissions({})}
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
