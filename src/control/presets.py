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

