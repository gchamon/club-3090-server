def default_chat_state():
    return {
        "revision": 0,
        "activeConversationId": "",
        "conversations": [],
        "archivedConversations": [],
        "promptTemplates": [],
    }


def chat_folder_name(value):
    cleaned = re.sub(r"[^A-Za-z0-9 _-]+", "", str(value or "")).strip()
    return re.sub(r"\s+", " ", cleaned)


def chat_conversation_file_relpath(conversation):
    conversation = conversation if isinstance(conversation, dict) else {}
    conversation_id = re.sub(r"[^A-Za-z0-9._-]+", "", str(conversation.get("id") or "").strip())
    if not conversation_id:
        raise ValueError("Conversation id is required.")
    folder = chat_folder_name(conversation.get("folder"))
    filename = f"{conversation_id}.json"
    return os.path.join(folder, filename) if folder else filename


def chat_conversation_file_path(conversation):
    return os.path.join(CHAT_CONVERSATIONS_DIR, chat_conversation_file_relpath(conversation))


def chat_conversation_index_row(item):
    row = sanitize_chat_conversation(item)
    index_row = {
        "id": str(row.get("id") or "").strip(),
        "title": str(row.get("title") or "Untitled conversation").strip() or "Untitled conversation",
        "folder": chat_folder_name(row.get("folder")),
        "createdAt": int(row.get("createdAt") or int(time.time() * 1000)),
        "updatedAt": int(row.get("updatedAt") or int(time.time() * 1000)),
        "lastUsedAt": int(row.get("lastUsedAt") or int(time.time() * 1000)),
        "summary": str(row.get("summary") or ""),
        "autoNamed": bool(row.get("autoNamed")),
        "smartTitleEnabled": row.get("smartTitleEnabled") is not False,
        "generationActive": bool(row.get("generationActive")),
        "presetId": str(row.get("presetId") or ""),
        "apiPresetName": str(row.get("apiPresetName") or ""),
        "messagesLoaded": False,
        "storagePath": chat_conversation_file_relpath(row),
    }
    runtime_snapshot = row.get("runtimeSnapshot")
    if isinstance(runtime_snapshot, dict) and runtime_snapshot:
        index_row["runtimeSnapshot"] = runtime_snapshot
    if row.get("archivedAt") not in (None, ""):
        index_row["archivedAt"] = int(row.get("archivedAt") or 0)
    return index_row


def split_chat_conversations_by_archive(rows):
    active_rows = []
    archived_rows = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        row = sanitize_chat_conversation(item)
        if row.get("archivedAt") not in (None, ""):
            archived_rows.append(row)
        else:
            active_rows.append(row)
    active_rows.sort(key=lambda item: int(item.get("updatedAt") or 0), reverse=True)
    archived_rows.sort(key=lambda item: int(item.get("archivedAt") or item.get("updatedAt") or 0), reverse=True)
    return active_rows, archived_rows


def _iter_chat_conversation_file_paths():
    if not os.path.isdir(CHAT_CONVERSATIONS_DIR):
        return []
    rows = []
    for root, dirnames, filenames in os.walk(CHAT_CONVERSATIONS_DIR):
        dirnames[:] = [name for name in dirnames if name not in {"attachments", "backups", "manual-backups"}]
        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            path = os.path.join(root, filename)
            if os.path.normpath(path) == os.path.normpath(CHAT_STATE_FILE):
                continue
            rows.append(path)
    return sorted(rows)


def read_chat_conversation_file(path):
    payload = read_json_file(path, {})
    if not isinstance(payload, dict):
        return None
    conversation_id = str(payload.get("id") or "").strip()
    if not conversation_id:
        return None
    return sanitize_chat_conversation(payload)


def read_chat_index_state():
    data = read_json_file(CHAT_STATE_FILE, default_chat_state())
    if not isinstance(data, dict):
        return default_chat_state()
    return {
        "revision": max(0, int(data.get("revision") or 0)),
        "activeConversationId": str(data.get("activeConversationId") or "").strip(),
        "conversations": [item for item in (data.get("conversations") or []) if isinstance(item, dict)],
        "archivedConversations": [item for item in (data.get("archivedConversations") or []) if isinstance(item, dict)],
        "promptTemplates": list(data.get("promptTemplates") or []),
    }


def load_chat_conversations_from_storage(index_state):
    index_state = index_state if isinstance(index_state, dict) else default_chat_state()
    embedded_rows = []
    for item in list(index_state.get("conversations") or []) + list(index_state.get("archivedConversations") or []):
        if not isinstance(item, dict):
            continue
        conversation_id = str(item.get("id") or "").strip()
        if not conversation_id:
            continue
        if "messages" in item or "attachments" in item or "systemPrompt" in item:
            embedded_rows.append(sanitize_chat_conversation(item))
    if embedded_rows:
        return embedded_rows
    file_rows = []
    for path in _iter_chat_conversation_file_paths():
        row = read_chat_conversation_file(path)
        if row:
            file_rows.append(row)
    if file_rows:
        file_rows.sort(key=lambda item: int(item.get("updatedAt") or 0), reverse=True)
        return file_rows
    fallback_rows = []
    for item in list(index_state.get("conversations") or []) + list(index_state.get("archivedConversations") or []):
        if isinstance(item, dict):
            fallback_rows.append(sanitize_chat_conversation(item))
    return fallback_rows


def write_chat_conversations_to_storage(state):
    state = state if isinstance(state, dict) else default_chat_state()
    os.makedirs(CHAT_CONVERSATIONS_DIR, exist_ok=True)
    expected_paths = set()
    index_rows = []
    archived_index_rows = []
    for conversation in list(state.get("conversations") or []) + list(state.get("archivedConversations") or []):
        row = sanitize_chat_conversation(conversation)
        path = chat_conversation_file_path(row)
        expected_paths.add(os.path.normpath(path))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_json_file(path, row)
        if row.get("archivedAt") not in (None, ""):
            archived_index_rows.append(chat_conversation_index_row(row))
        else:
            index_rows.append(chat_conversation_index_row(row))
    for path in _iter_chat_conversation_file_paths():
        if os.path.normpath(path) in expected_paths:
            continue
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except Exception:
            continue
    index_payload = {
        "revision": max(0, int(state.get("revision") or 0)),
        "activeConversationId": str(state.get("activeConversationId") or "").strip(),
        "conversations": index_rows,
        "archivedConversations": archived_index_rows,
        "promptTemplates": list(state.get("promptTemplates") or []),
    }
    write_json_file(CHAT_STATE_FILE, index_payload)
    return index_payload


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
        "inputTokens",
        "inputTokensEstimate",
        "inputTokensApprox",
        "outputTokens",
        "ttftSeconds",
        "tokensPerSecond",
        "maxTokensPerSecond",
        "thinkingExpanded",
        "thinkingDone",
        "thinkingLive",
        "thinkingStartedAt",
        "thinkingDurationMs",
        "generationActive",
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
    threshold_pct = max(25, min(95, threshold_pct))
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
        "smartTitleEnabled": item.get("smartTitleEnabled") is not False,
        "autoCompactEnabled": item.get("autoCompactEnabled") is not False,
        "autoCompactThresholdPct": threshold_pct,
        "messages": [sanitize_chat_message(message) for message in (item.get("messages") or []) if isinstance(message, dict)],
        "attachments": [sanitize_chat_attachment(attachment) for attachment in (item.get("attachments") or []) if isinstance(attachment, dict)],
        "draftText": str(item.get("draftText") or ""),
        "generationActive": bool(item.get("generationActive")),
        "compactedFromId": str(item.get("compactedFromId") or ""),
        "compactionSequence": compaction_sequence,
    }
    for key in (
        "lastInputTokens",
        "lastOutputTokens",
        "lastTotalTokens",
        "lastCtxSizeTokens",
        "lastKvCacheUsagePct",
        "lastCpuKvCacheUsagePct",
        "lastPrefixCacheHitRatePct",
        "lastPromptTokensPerSecond",
        "lastPromptTokensPerSecondPeak",
        "lastRuntimeRequestAt",
        "lastStatus",
        "lastLatencySeconds",
        "lastTtftSeconds",
        "lastTokensPerSecond",
        "lastTokensPerSecondPeak",
        "lastToolCalls",
        "lastRequestPath",
        "totalInputTokens",
        "totalOutputTokens",
        "totalTokens",
        "transcriptHeightPx",
        "transcriptAutoscroll",
        "archivedAt",
    ):
        value = item.get(key)
        if value not in (None, ""):
            row[key] = value
    runtime_snapshot = item.get("runtimeSnapshot")
    if isinstance(runtime_snapshot, dict) and runtime_snapshot:
        row["runtimeSnapshot"] = runtime_snapshot
    return row


def chat_conversation_title_summary(item):
    row = chat_conversation_index_row(item)
    row.pop("storagePath", None)
    return row


def merge_stream_state_into_chat_conversation(conversation, stream_state):
    row = sanitize_chat_conversation(conversation)
    stream = stream_state if isinstance(stream_state, dict) else {}
    assistant_text = str(stream.get("assistant_text") or "")
    reasoning_text = str(stream.get("reasoning_text") or "")
    status = str(stream.get("status") or "").strip().lower()
    if not assistant_text and not reasoning_text and not status:
        return row, False
    changed = False
    messages = list(row.get("messages") or [])
    last_assistant = None
    for message in reversed(messages):
      if isinstance(message, dict) and str(message.get("role") or "").strip().lower() == "assistant":
        last_assistant = message
        break
    if last_assistant is None and (assistant_text or reasoning_text):
        last_assistant = sanitize_chat_message({"role": "assistant", "text": "", "reasoningText": ""})
        messages.append(last_assistant)
        changed = True
    if last_assistant is not None:
        if assistant_text and len(assistant_text) >= len(str(last_assistant.get("text") or "")):
            if str(last_assistant.get("text") or "") != assistant_text:
                last_assistant["text"] = assistant_text
                changed = True
        if reasoning_text and len(reasoning_text) >= len(str(last_assistant.get("reasoningText") or "")):
            if str(last_assistant.get("reasoningText") or "") != reasoning_text:
                last_assistant["reasoningText"] = reasoning_text
                changed = True
    if status in {"done", "error", "aborted"} and row.get("generationActive"):
        row["generationActive"] = False
        changed = True
    if changed:
        row["messages"] = [sanitize_chat_message(message) for message in messages if isinstance(message, dict)]
        updated_at = max(
            int(row.get("updatedAt") or 0),
            int(stream.get("updated_at") or 0),
            int(time.time() * 1000),
        )
        row["updatedAt"] = updated_at
        row["lastUsedAt"] = updated_at
    return row, changed


def recover_chat_conversation_from_stream_state(state, conversation_id):
    state = state if isinstance(state, dict) else default_chat_state()
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return state, False
    stream_state = read_admin_chat_stream_state(conversation_id)
    if not isinstance(stream_state, dict) or not stream_state:
        return state, False
    changed = False
    next_conversations = []
    for conversation in state.get("conversations") or []:
        if not isinstance(conversation, dict) or str(conversation.get("id") or "").strip() != conversation_id:
            next_conversations.append(conversation)
            continue
        merged, row_changed = merge_stream_state_into_chat_conversation(conversation, stream_state)
        next_conversations.append(merged)
        changed = changed or row_changed
    if not changed:
        return state, False
    next_state = {
        **state,
        "conversations": next_conversations,
    }
    write_chat_conversations_to_storage(next_state)
    return next_state, True


def read_chat_state_titles():
    state = read_chat_state()
    debug_audit(
        "chat_state_titles",
        revision=max(0, int(state.get("revision") or 0)),
        active_conversation_id=str(state.get("activeConversationId") or "").strip(),
        conversation_count=len(state.get("conversations") or []),
        archived_conversation_count=len(state.get("archivedConversations") or []),
    )
    return {
        "revision": max(0, int(state.get("revision") or 0)),
        "activeConversationId": str(state.get("activeConversationId") or "").strip(),
        "conversations": [
            chat_conversation_title_summary(conversation)
            for conversation in (state.get("conversations") or [])
            if isinstance(conversation, dict)
        ],
        "archivedConversations": [
            chat_conversation_title_summary(conversation)
            for conversation in (state.get("archivedConversations") or [])
            if isinstance(conversation, dict)
        ],
        "promptTemplates": list(state.get("promptTemplates") or []),
    }


def read_chat_conversation_detail(conversation_id):
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        raise ValueError("Conversation id is required.")
    state = read_chat_state()
    state, _ = recover_chat_conversation_from_stream_state(state, conversation_id)
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
        for row in list(current_state.get("conversations") or []) + list(current_state.get("archivedConversations") or [])
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }
    merged_rows = []
    merged_archived_rows = []
    preserved_detail_rows = 0
    for raw_row, target_rows in [
        *((item, merged_rows) for item in (payload.get("conversations") or [])),
        *((item, merged_archived_rows) for item in (payload.get("archivedConversations") or [])),
    ]:
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
            if raw_row.get("archivedAt") not in (None, ""):
                existing["archivedAt"] = int(raw_row.get("archivedAt") or 0)
            else:
                existing.pop("archivedAt", None)
            target_rows.append(existing)
            preserved_detail_rows += 1
            continue
        target_rows.append(sanitize_chat_conversation(raw_row))
    debug_audit(
        "chat_state_merge",
        incoming_revision=payload.get("revision") or 0,
        current_revision=current_state.get("revision") or 0,
        incoming_conversation_count=len(payload.get("conversations") or []),
        incoming_archived_conversation_count=len(payload.get("archivedConversations") or []),
        merged_conversation_count=len(merged_rows),
        merged_archived_conversation_count=len(merged_archived_rows),
        preserved_detail_rows=preserved_detail_rows,
        active_conversation_id=str(payload.get("activeConversationId") or current_state.get("activeConversationId") or "").strip(),
    )
    return {
        "revision": payload.get("revision") or 0,
        "activeConversationId": str(payload.get("activeConversationId") or current_state.get("activeConversationId") or "").strip(),
        "conversations": merged_rows,
        "archivedConversations": merged_archived_rows,
        "promptTemplates": list(payload.get("promptTemplates") or current_state.get("promptTemplates") or []),
    }


def sanitize_chat_state_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    try:
        revision = max(0, int(payload.get("revision") or 0))
    except Exception:
        revision = 0
    conversations = []
    archived_conversations = []
    seen_ids = set()
    for source_key, target_rows, archived_default in (
        ("conversations", conversations, False),
        ("archivedConversations", archived_conversations, True),
    ):
        for conversation in (payload.get(source_key) or []):
            if not isinstance(conversation, dict):
                continue
            row = sanitize_chat_conversation(conversation)
            conversation_id = str(row.get("id") or "").strip()
            if not conversation_id or conversation_id in seen_ids:
                continue
            if archived_default and row.get("archivedAt") in (None, ""):
                row["archivedAt"] = int(time.time() * 1000)
            if not archived_default:
                row.pop("archivedAt", None)
            seen_ids.add(conversation_id)
            target_rows.append(row)
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
        "archivedConversations": archived_conversations,
        "promptTemplates": prompt_templates,
    }


def read_chat_state():
    index_state = read_chat_index_state()
    all_rows = load_chat_conversations_from_storage(index_state)
    active_rows, archived_rows = split_chat_conversations_by_archive(all_rows)
    combined_state = {
        "revision": max(0, int(index_state.get("revision") or 0)),
        "activeConversationId": str(index_state.get("activeConversationId") or "").strip(),
        "conversations": active_rows,
        "archivedConversations": archived_rows,
        "promptTemplates": list(index_state.get("promptTemplates") or []),
    }
    state = sanitize_chat_state_payload(combined_state)
    debug_audit(
        "chat_state_read",
        revision=max(0, int(state.get("revision") or 0)),
        active_conversation_id=str(state.get("activeConversationId") or "").strip(),
        conversation_count=len(state.get("conversations") or []),
        archived_conversation_count=len(state.get("archivedConversations") or []),
        prompt_template_count=len(state.get("promptTemplates") or []),
    )
    return state


def backup_chat_state_snapshot(state):
    state = state if isinstance(state, dict) else {}
    conversations = list(state.get("conversations") or []) + list(state.get("archivedConversations") or [])
    revision = max(0, int(state.get("revision") or 0))
    if revision <= 0 or not conversations:
        return ""
    os.makedirs(CHAT_STATE_BACKUP_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(CHAT_STATE_BACKUP_DIR, f"state-r{revision:06d}-{stamp}.json")
    write_json_file(path, state)
    backups = sorted(glob.glob(os.path.join(CHAT_STATE_BACKUP_DIR, "state-r*.json")))
    for stale_path in backups[:-24]:
        try:
            os.remove(stale_path)
        except Exception:
            pass
    return path


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
    previous_conversation_count = len(current_state.get("conversations") or []) + len(current_state.get("archivedConversations") or [])
    next_conversation_count = len(state.get("conversations") or []) + len(state.get("archivedConversations") or [])
    if previous_conversation_count >= 3 and next_conversation_count + 1 < previous_conversation_count:
        debug_audit(
            "chat_state_write_blocked",
            previous_revision=current_revision,
            incoming_revision=incoming_revision,
            previous_conversation_count=previous_conversation_count,
            next_conversation_count=next_conversation_count,
        )
        raise ValueError(
            f"Refusing to replace {previous_conversation_count} conversations with {next_conversation_count}. "
            "Use the delete endpoint for removals or restore from a fuller local cache."
        )
    backup_path = backup_chat_state_snapshot(current_state)
    state["revision"] = max(current_revision + 1, incoming_revision or 0)
    write_chat_conversations_to_storage(state)
    removed_attachments = prune_unused_chat_attachments(state)
    debug_audit(
        "chat_state_write",
        previous_revision=current_revision,
        incoming_revision=incoming_revision,
        written_revision=state["revision"],
        active_conversation_id=str(state.get("activeConversationId") or "").strip(),
        conversation_count=len(state.get("conversations") or []),
        archived_conversation_count=len(state.get("archivedConversations") or []),
        removed_attachment_count=len(removed_attachments),
        backup_path=backup_path,
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
    for conversation in list(state.get("conversations") or []) + list(state.get("archivedConversations") or []):
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
    with suppress_chat_debug_audit():
        state = read_chat_state()
        conversations = list(state.get("conversations") or [])
        archived_conversations = list(state.get("archivedConversations") or [])
        conversation = next(
            (row for row in conversations + archived_conversations if str(row.get("id") or "") == conversation_id),
            None,
        )
        if not conversation:
            raise ValueError("Conversation not found.")
        next_rows = [row for row in conversations if str(row.get("id") or "") != conversation_id]
        next_archived_rows = [row for row in archived_conversations if str(row.get("id") or "") != conversation_id]
        next_active_id = str(state.get("activeConversationId") or "").strip()
        if next_active_id == conversation_id:
            next_active_id = str(next_rows[0].get("id") or "") if next_rows else ""
        next_state = write_chat_state(
            {
                "revision": max(0, int(state.get("revision") or 0)) + 1,
                "activeConversationId": next_active_id,
                "conversations": next_rows,
                "archivedConversations": next_archived_rows,
                "promptTemplates": state.get("promptTemplates") or [],
            }
        )
    log_audit(
        "admin_chat_delete",
        conversation_id=conversation_id,
        title=str(conversation.get("title") or "").strip() or "Untitled conversation",
    )
    return {
        "ok": True,
        "conversation_id": conversation_id,
        "state": next_state,
    }


def delete_all_chat_conversations():
    with suppress_chat_debug_audit():
        state = read_chat_state()
        removed = [
            {
                "id": str(row.get("id") or "").strip(),
                "title": str(row.get("title") or "").strip() or "Untitled conversation",
            }
            for row in list(state.get("conversations") or []) + list(state.get("archivedConversations") or [])
            if isinstance(row, dict)
        ]
        next_state = write_chat_state(
            {
                "revision": max(0, int(state.get("revision") or 0)) + 1,
                "activeConversationId": "",
                "conversations": [],
                "archivedConversations": [],
                "promptTemplates": state.get("promptTemplates") or [],
            }
        )
    log_audit(
        "admin_chat_delete_all",
        conversations=len(removed),
        result_summary=summarize_audit_result({"deleted": len(removed)}),
    )
    return {
        "ok": True,
        "deleted_count": len(removed),
        "state": next_state,
    }


def archive_chat_conversation(conversation_id):
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        raise ValueError("Conversation id is required.")
    with suppress_chat_debug_audit():
        state = read_chat_state()
        conversations = list(state.get("conversations") or [])
        archived_conversations = list(state.get("archivedConversations") or [])
        conversation = next((row for row in conversations if str(row.get("id") or "") == conversation_id), None)
        if not conversation:
            raise ValueError("Conversation not found.")
        archived_row = sanitize_chat_conversation(conversation)
        archived_row["archivedAt"] = int(time.time() * 1000)
        next_rows = [row for row in conversations if str(row.get("id") or "") != conversation_id]
        next_archived_rows = [archived_row] + [
            row for row in archived_conversations if str(row.get("id") or "") != conversation_id
        ]
        next_active_id = str(state.get("activeConversationId") or "").strip()
        if next_active_id == conversation_id:
            next_active_id = str(next_rows[0].get("id") or "") if next_rows else ""
        next_state = write_chat_state(
            {
                "revision": max(0, int(state.get("revision") or 0)) + 1,
                "activeConversationId": next_active_id,
                "conversations": next_rows,
                "archivedConversations": next_archived_rows,
                "promptTemplates": state.get("promptTemplates") or [],
            }
        )
    log_audit(
        "admin_chat_archive",
        conversation_id=conversation_id,
        title=str(conversation.get("title") or "").strip() or "Untitled conversation",
    )
    return {
        "ok": True,
        "conversation_id": conversation_id,
        "state": next_state,
    }


def restore_chat_conversation(conversation_id):
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        raise ValueError("Conversation id is required.")
    with suppress_chat_debug_audit():
        state = read_chat_state()
        conversations = list(state.get("conversations") or [])
        archived_conversations = list(state.get("archivedConversations") or [])
        conversation = next((row for row in archived_conversations if str(row.get("id") or "") == conversation_id), None)
        if not conversation:
            raise ValueError("Archived conversation not found.")
        restored_row = sanitize_chat_conversation(conversation)
        restored_row.pop("archivedAt", None)
        restored_row["updatedAt"] = int(time.time() * 1000)
        restored_row["lastUsedAt"] = restored_row["updatedAt"]
        next_rows = [restored_row] + [row for row in conversations if str(row.get("id") or "") != conversation_id]
        next_archived_rows = [row for row in archived_conversations if str(row.get("id") or "") != conversation_id]
        next_state = write_chat_state(
            {
                "revision": max(0, int(state.get("revision") or 0)) + 1,
                "activeConversationId": conversation_id,
                "conversations": next_rows,
                "archivedConversations": next_archived_rows,
                "promptTemplates": state.get("promptTemplates") or [],
            }
        )
    log_audit(
        "admin_chat_restore",
        conversation_id=conversation_id,
        title=str(conversation.get("title") or "").strip() or "Untitled conversation",
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
