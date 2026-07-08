IMAGE_STUDIO_JOB_LOCK = threading.Lock()
IMAGE_STUDIO_JOBS = {}
IMAGE_STUDIO_JOB_LIMIT = 40
IMAGE_STUDIO_COMFY_URL = "http://127.0.0.1:8188"
IMAGE_STUDIO_ORCHESTRATOR_URL = "http://127.0.0.1:8190"
IMAGE_STUDIO_STEP_VOICE_URL = "http://127.0.0.1:8193"
IMAGE_STUDIO_PRODUCTION_URL = os.environ.get("STUDIO_PRODUCTION_URL", "http://127.0.0.1:8195")
IMAGE_STUDIO_OUTPUT_ROOT = os.path.join(CLUB3090_DIR, "ai-studio-models", "comfyui", "output")
IMAGE_STUDIO_WORKFLOW_DIR = os.path.join(CLUB3090_DIR, "services", "studio", "workflows")
IMAGE_STUDIO_LAST_KIND_FILE = os.path.join(CONTROL_DIR, "ai-studio-last-kind")
IMAGE_STUDIO_DIRECTOR_AUTO_MIN_FREE_MIB = 6500
IMAGE_STUDIO_DIRECTOR_RESIDENT_ESTIMATE_MIB = 5200
IMAGE_STUDIO_GENERATION_FREE_MIB = {
    "image": 18000,
    "audio": 16000,
    "voice": 20000,
    "video": 22000,
}
IMAGE_STUDIO_VIDEO_TEXT_BAN = (
    "Avoid generated on-screen text unless the request explicitly needs readable writing. Do not add "
    "readable overlays, logos, watermarks, credits, lower thirds, UI overlays, signs, labels, or random "
    "writing-like marks."
)
IMAGE_STUDIO_VIDEO_NEGATIVE_PROMPT = (
    "text, readable text, letters, words, typography, title card, caption, captions, subtitle, subtitles, "
    "lower third, chyron, credits, logo, watermark, UI overlay, graphic overlay, signs, labels, gibberish writing, "
    "random writing, blurry, distorted, low quality, still frame, duplicate frames, split screen, contact sheet, panels"
)


def _image_studio_container_store_free_space():
    rows = []
    for path in ("/var/lib/containerd", "/var/lib/docker", "/"):
        try:
            if os.path.exists(path):
                usage = shutil.disk_usage(path)
                rows.append((int(usage.free), path))
        except Exception:
            continue
    if rows:
        return min(rows, key=lambda row: row[0])
    try:
        usage = shutil.disk_usage("/")
        return int(usage.free), "/"
    except Exception:
        return 0, "/"


def _image_studio_preflight_compose_images(label, compose_dir, compose_file, env=None, env_file=None, may_build=False):
    images = docker_compose_config_images(compose_dir, compose_file, env=env, env_file=env_file, timeout=60)
    plan = _preflight_docker_pull_space(label, images, include_build=may_build)
    try:
        log_audit(
            "image_studio_docker_pull_preflight",
            label=label,
            missing=plan.get("missing") or [],
            incoming_gb=round((int(plan.get("image_bytes") or 0) / (1024 ** 3)), 2),
            buffer_gb=round((int(plan.get("buffer_bytes") or 0) / (1024 ** 3)), 2),
            may_build=bool(may_build),
        )
    except Exception:
        pass


IMAGE_STUDIO_LANES = {
    "ideogram": {"workflow": "ideogram4.json", "kind": "image", "label": "Ideogram-4"},
    "hidream": {"workflow": "hidream_o1.json", "kind": "image", "label": "HiDream-O1"},
    "chroma": {"workflow": "chroma1_hd.json", "kind": "image", "label": "Chroma"},
    "zimage": {"workflow": "z_image_turbo.json", "kind": "image", "label": "Z-Image"},
    "krea": {"workflow": "krea2.json", "kind": "image", "label": "Krea 2"},
    "music": {"workflow": "ace_step_music.json", "kind": "audio", "label": "ACE-Step Music"},
    "sfx": {"workflow": "stable_audio_sfx.json", "kind": "audio", "label": "Stable Audio SFX"},
    "ltx": {"workflow": "ltx_distilled_distorch.json", "kind": "video", "label": "LTX-2.3"},
    "sulphur": {"workflow": "ltx_distilled_distorch.json", "kind": "video", "label": "Sulphur"},
    "10eros": {"workflow": "ltx_distilled_distorch.json", "kind": "video", "label": "10Eros"},
    "wan": {"workflow": "wan22_rapid.json", "kind": "video", "label": "Wan2.2"},
    "voice": {"workflow": "", "kind": "audio", "label": "Step-Audio-EditX Voice"},
    "kokoro": {"workflow": "", "kind": "audio", "label": "Kokoro Voiceover"},
}
IMAGE_STUDIO_OPTIONAL_MODEL_PATHS = {
    "ideogram": (
        "diffusion_models/ideogram4_fp8_scaled.safetensors",
        "diffusion_models/ideogram4_unconditional_fp8_scaled.safetensors",
        "text_encoders/qwen3vl_8b_fp8_scaled.safetensors",
        "vae/flux2-vae.safetensors",
    ),
    "hidream": ("diffusion_models/HiDream-O1-Image-Dev-2604-FP8/model.safetensors",),
    "chroma": (
        "diffusion_models/Chroma1-HD-fp8mixed.safetensors",
        "text_encoders/t5xxl_fp16.safetensors",
        "vae/flux/ae.safetensors",
    ),
    "zimage": (
        "diffusion_models/z-image-turbo-fp8-e4m3fn.safetensors",
        "text_encoders/qwen_3_4b_fp8_mixed.safetensors",
        "vae/ae.safetensors",
    ),
    "krea": (
        "diffusion_models/krea2_turbo_fp8_scaled.safetensors",
        "text_encoders/qwen3vl_4b_fp8_scaled.safetensors",
        "vae/qwen_image_vae.safetensors",
    ),
    "music": ("checkpoints/ace-step-1.5/all_in_one/ace_step_v1_3.5b.safetensors",),
    "sfx": ("checkpoints/stable-audio-open-1.0.safetensors", "text_encoders/t5-base.safetensors"),
    "ltx": (
        "unet/ltx2.3/distilled-1.1/ltx-2.3-22b-distilled-1.1-Q8_0.gguf",
        "vae/ltx-2.3-22b-distilled_audio_vae.safetensors",
        "vae/ltx-2.3-22b-distilled_video_vae.safetensors",
        "text_encoders/ltx-2.3-22b-distilled_embeddings_connectors.safetensors",
        "text_encoders/gemma_3_12B_it_fp8_scaled.safetensors",
    ),
    "sulphur": (
        "unet/sulphur-2/sulphur_dev-Q8_0.gguf",
        "vae/ltx-2.3-22b-dev_audio_vae.safetensors",
        "vae/ltx-2.3-22b-dev_video_vae.safetensors",
        "text_encoders/ltx-2.3-22b-dev_embeddings_connectors.safetensors",
        "loras/ltx-2.3-22b-distilled-lora-384-1.1.safetensors",
        "text_encoders/gemma_3_12B_it_fp8_scaled.safetensors",
    ),
    "10eros": (
        "unet/10eros/10Eros_v1-Q8_0.gguf",
        "vae/ltx-2.3-22b-dev_audio_vae.safetensors",
        "vae/ltx-2.3-22b-dev_video_vae.safetensors",
        "text_encoders/ltx-2.3-22b-dev_embeddings_connectors.safetensors",
        "loras/ltx-2.3-22b-distilled-lora-384-1.1.safetensors",
        "text_encoders/gemma_3_12B_it_fp8_scaled.safetensors",
    ),
    "wan": (
        "unet/wan-rapid/Mega-v10/wan2.2-rapid-mega-aio-nsfw-v10-Q8_0.gguf",
        "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "vae/wan_2.1_vae.safetensors",
    ),
    "voice": ("Step-Audio/Step-Audio-EditX", "Step-Audio/Step-Audio-Tokenizer"),
    "kokoro": ("tts/kokoro/kokoro-v1.0.onnx", "tts/kokoro/voices-v1.0.bin"),
}
image_studio_activity_cache = {"checked_at": 0.0, "active": False}
image_studio_runtime_cache = {"checked_at": 0.0, "snapshot": {}}
image_studio_director_env_repair_cache = {"checked_at": 0.0}
image_studio_comfy_model_cache = {"kind": ""}
image_studio_object_info_cache = {}
image_studio_seen_prompt_ids = set()
IMAGE_STUDIO_IMAGE_LANES = {"ideogram", "hidream", "chroma", "zimage", "krea"}
IMAGE_STUDIO_VIDEO_LANES = {"ltx", "sulphur", "10eros", "wan"}
IMAGE_STUDIO_CONTAINERS = {
    "comfyui": {"label": "ComfyUI", "port": 8188, "role": "render"},
    "open-webui": {"label": "Open WebUI", "port": 8080, "role": "compatibility"},
    "litellm": {"label": "LiteLLM", "port": 4000, "role": "optional"},
    "searxng": {"label": "SearXNG", "port": 8088, "role": "optional"},
    "studio-director": {"label": "Studio Director", "port": 8090, "role": "director"},
    "studio-image-shim": {"label": "Image Shim", "port": 8191, "role": "image"},
    "studio-gallery": {"label": "Studio Gallery", "port": 8189, "role": "gallery"},
    "studio-orchestrator": {"label": "Studio Orchestrator", "port": 8190, "role": "video"},
    "studio-tts": {"label": "Studio TTS", "port": 8192, "role": "speech"},
    "studio-step-voice": {"label": "Step Voice", "port": 8193, "role": "speech"},
}
IMAGE_STUDIO_DIRECTOR_MODEL = "qwen3.5-4b-uncensored"
IMAGE_STUDIO_DIRECTOR_IMG_SYS = (
    "You are an award-winning art director writing prompts for Ideogram-4, which is trained on "
    "STRUCTURED JSON captions. First silently infer the KIND of image the user wants, then output "
    "ONE JSON object and NOTHING ELSE, with keys: high_level_description, style_description, and "
    "compositional_deconstruction. style_description must include aesthetics, lighting, photo, "
    "medium, and color_palette. compositional_deconstruction must include background and elements. "
    "For visible text, put the exact text in quotes in high_level_description and the relevant "
    "element description. Output ONLY valid JSON."
)
IMAGE_STUDIO_INTERACTIVE_PLAN_SYS = (
    "You are the Club 3090 AI Studio Director. Decide whether the user's message should be normal "
    "chat or an AI Studio generation plan. Output ONE JSON object and nothing else with these "
    "keys: action, title, rationale, response, steps. action is either chat or generate. title is "
    "metadata only: write a short descriptive conversation title under 10 words based on the "
    "user's actual request, equivalent to the normal Chat <title> metadata line; never use runtime, "
    "lane, model, preset, or UI labels such as Active Chat preset, Plan Mode, Interactive Mode, "
    "AI Studio, or Chat response as the title. steps is an ordered JSON array of objects with keys "
    "lane, prompt, purpose, batch, and depends_on. lane "
    "is one of text, ideogram, hidream, chroma, zimage, krea, music, sfx, ltx, sulphur, 10eros, wan, voice, kokoro, or empty "
    "for chat. Use text for research, factual prose, lists, scripts, or structured source content "
    "that should be generated by the active Chat preset before multimedia work. "
    "Build the shortest useful sequence that fully satisfies the request; use multiple steps only "
    "when the requested result genuinely requires multiple independent artifacts. For repeated "
    "outputs, create one grouped batch step instead of one step per item. batch is either null or "
    "an object with keys source_step, items, count, and strategy. depends_on is an array of earlier "
    "1-based step numbers. Order grouped work to minimize model switching and permit progressive "
    "presentation; complete fast speech batches before slower image batches when both use the same "
    "text source. A text step that feeds a batch MUST request ONLY a JSON array of objects. Every "
    "object must contain stable fields needed by dependent prompts, normally name, dates, text, "
    "image_prompt, and speech_text. Batch prompts must reference fields as {{name}}, {{dates}}, "
    "{{text}}, {{image_prompt}}, or {{speech_text}} so the executor can expand them deterministically. "
    "Preserve ordinal words, counts, requested ordering, and exact membership from the user request; "
    "never skip intermediate entries when the user asks for the first, last, next, every, or all items. "
    "If the user asks narration to read, speak, or voice a paragraph/body/copy/text field, speech_text "
    "must be the same narration copy as text, not a quotation, oath, slogan, excerpt, or invented speech. "
    "For factual or real-world source records, text prompts must request conservative widely established facts "
    "and must avoid invented events, dates, roles, names, achievements, causal links, attributions, or quotations. "
    "Image prompts in batch objects must include aggressive, meaningful variation directions; every "
    "candidate should differ on at least three major axes across pose, viewpoint, setting/scenery, "
    "action, lighting, crop, foreground/background depth, color emphasis, contextual props, and "
    "composition while keeping the requested identity/style. "
    "Never inline the actual batch records or long generated source data inside the plan JSON; the "
    "text step prompt requests that data later, and batch.items must stay a short descriptor such as "
    "'all objects from step 1' with a numeric count when known. "
    "Only choose a lane listed as ready. Use ideogram for logos, design, text/typography images, "
    "posters, and general images unless another ready image lane is more appropriate. Use zimage "
    "for fast uncensored stills, krea for aesthetic/stylized stills, chroma for uncensored images "
    "that benefit from real CFG/negative control, and hidream for top-quality photoreal stills. Use music "
    "for songs, beats, instrumentals, and musical stings. Use sfx for sound effects, ambiences, "
    "foley, and non-musical audio. Use kokoro for text-to-speech narration. Use voice only when the "
    "user supplies an audio reference attachment for cloning; never choose voice without one. "
    "Use ltx for video whenever it is ready unless the user explicitly requests Sulphur, 10Eros, or Wan; "
    "use wan for uncensored text-to-video when requested or when LTX-family lanes are unavailable, "
    "and use sulphur/10eros for uncensored LTX-family text/image video. Video prompts must be "
    "rich production prompts with a clear subject, setting, visual style, camera movement, action "
    "beats, and exact requested duration; do not summarize the user's request into a vague topic. "
    "If the user explicitly asks for no media, a no-media dry run, text-only output, or says not to "
    "call image/audio/video/download/file/external tools, do not choose any media lane and do not add "
    "image_prompt, speech_text, batch media, download, file, or external-tool steps. Use chat or text-only "
    "steps instead. "
    "If a previous_plan is supplied, revise that plan using the user's latest "
    "criticism rather than starting over. If the message is small talk, a question, or too vague "
    "to generate, set action to chat, put a short helpful reply in response, and use an empty steps "
    "array. Every step prompt must be the exact generation prompt for that lane and preserve all "
    "requested durations, visible text, ordering, and constraints."
)
IMAGE_STUDIO_PLAN_REVISION_SYS = (
    "You are auditing a revised Club 3090 AI Studio plan. Output ONE corrected JSON object and "
    "nothing else. original_request defines the task scope; never narrow, replace, or discard that "
    "scope unless latest_revision explicitly asks to remove part of it. The latest_revision is "
    "authoritative for requested changes and overrides every conflicting phrase copied from "
    "previous_plan or candidate_plan. Preserve candidate details that do not conflict, "
    "but remove stale contradictions. Check every step prompt, template placeholder, batch order, "
    "dependency, count, date, duration, and requested exact wording against latest_revision. "
    "If latest_revision says the plan needs exactly N steps, output exactly N complete step "
    "objects and do not collapse the plan to a single summary step. "
    "Return the same action/title/rationale/response/steps schema used by candidate_plan, keeping "
    "title as a short descriptive conversation title based on original_request."
)


def image_studio_runtime_snapshot(max_age=2.0):
    _image_studio_repair_director_env_default()
    now = time.time()
    with IMAGE_STUDIO_JOB_LOCK:
        cached = image_studio_runtime_cache.get("snapshot")
        if cached and now - float(image_studio_runtime_cache.get("checked_at") or 0) < max(0.0, float(max_age or 0)):
            return dict(cached)
    discovered = {}
    try:
        output = subprocess.check_output(
            ["docker", "ps", "-a", "--format", "{{json .}}"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        for line in output.splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            name = str(row.get("Names") or "").strip()
            if name in IMAGE_STUDIO_CONTAINERS:
                discovered[name] = {
                    **IMAGE_STUDIO_CONTAINERS[name],
                    "name": name,
                    "state": str(row.get("State") or "").strip().lower(),
                    "status": str(row.get("Status") or "").strip(),
                    "running": str(row.get("State") or "").strip().lower() == "running",
                }
    except Exception:
        discovered = {}
    if discovered.get("studio-director", {}).get("running"):
        placement = _image_studio_director_actual_placement()
        match = re.fullmatch(r"gpu(\d+)", placement or "")
        discovered["studio-director"]["gpu_indices"] = [int(match.group(1))] if match else []
    queue_running = 0
    queue_pending = 0
    queue_prompt_ids = set()
    comfy_ready = False
    if discovered.get("comfyui", {}).get("running"):
        try:
            queue = _image_studio_json_request("/queue", timeout=2)
            running_rows = queue.get("queue_running") or []
            pending_rows = queue.get("queue_pending") or []
            queue_running = len(running_rows)
            queue_pending = len(pending_rows)
            for row in [*running_rows, *pending_rows]:
                if isinstance(row, (list, tuple)) and len(row) > 1:
                    queue_prompt_ids.add(str(row[1] or "").strip())
                elif isinstance(row, dict):
                    queue_prompt_ids.add(str(row.get("prompt_id") or row.get("id") or "").strip())
            queue_prompt_ids.discard("")
            comfy_ready = True
        except Exception:
            comfy_ready = False
    running = [name for name in IMAGE_STUDIO_CONTAINERS if discovered.get(name, {}).get("running")]
    with IMAGE_STUDIO_JOB_LOCK:
        active_jobs = [
            _image_studio_job_public(row)
            for row in IMAGE_STUDIO_JOBS.values()
            if row.get("status") not in {"success", "failed", "cancelled"}
        ]
        direct_prompt_ids = {str(row.get("prompt_id") or "").strip() for row in IMAGE_STUDIO_JOBS.values()}
        direct_active = bool(active_jobs)
        video_active = any(str(row.get("lane") or "") in IMAGE_STUDIO_VIDEO_LANES for row in active_jobs)
        new_external_prompt_ids = queue_prompt_ids - direct_prompt_ids - image_studio_seen_prompt_ids
        image_studio_seen_prompt_ids.update(queue_prompt_ids)
        if len(image_studio_seen_prompt_ids) > 2000:
            image_studio_seen_prompt_ids.intersection_update(queue_prompt_ids | direct_prompt_ids)
    generation_active = bool(queue_running or queue_pending or direct_active)
    snapshot = {
        "installed": bool(discovered),
        "active": bool(running),
        "ready": comfy_ready,
        "mode": "ai-studio" if running else "",
        "port": 8188 if discovered.get("comfyui", {}).get("running") else 0,
        "containers": [discovered[name] for name in IMAGE_STUDIO_CONTAINERS if name in discovered],
        "running_containers": running,
        "queue_running": queue_running,
        "queue_pending": queue_pending,
        "generation_active": generation_active,
        "gpu_indices": ([0, 1] if video_active else [0]) if generation_active else [],
    }
    model_missing = {lane: _image_studio_optional_models_ready(lane) for lane in IMAGE_STUDIO_LANES}
    snapshot["model_missing"] = model_missing
    snapshot["model_ready"] = {lane: not bool(missing) for lane, missing in model_missing.items()}
    production = image_studio_backend_plan_status()
    snapshot["production"] = production
    snapshot["backend_plan_ready"] = bool(production.get("ready"))
    snapshot["model_ready"]["production"] = bool(production.get("ready"))
    snapshot["active_jobs"] = active_jobs
    if new_external_prompt_ids:
        with metrics_lock:
            metrics["total_requests"] = int(metrics.get("total_requests", 0) or 0) + len(new_external_prompt_ids)
            metrics["last_status"] = "running"
            metrics["last_path"] = "ai-studio:external"
            metrics["last_request_at"] = int(time.time())
    with IMAGE_STUDIO_JOB_LOCK:
        image_studio_runtime_cache.update(checked_at=now, snapshot=snapshot)
        image_studio_activity_cache.update(checked_at=now, active=generation_active)
    return dict(snapshot)


def image_studio_activity_active(max_age=2.0):
    now = time.time()
    with IMAGE_STUDIO_JOB_LOCK:
        if any(
            row.get("status") not in {"success", "failed", "cancelled"}
            for row in IMAGE_STUDIO_JOBS.values()
        ):
            image_studio_activity_cache.update(checked_at=now, active=True)
            return True
        if now - float(image_studio_activity_cache.get("checked_at") or 0) < max(0.0, float(max_age or 0)):
            return bool(image_studio_activity_cache.get("active"))
    active = False
    try:
        payload = _image_studio_json_request("/queue", timeout=2)
        active = bool(payload.get("queue_running") or payload.get("queue_pending"))
    except Exception:
        active = False
    with IMAGE_STUDIO_JOB_LOCK:
        image_studio_activity_cache.update(checked_at=now, active=active)
    return active


def _image_studio_job_public(row):
    result = dict(row or {})
    result.pop("cancel_event", None)
    result.pop("thread", None)
    return result


def _set_image_studio_job(job_id, **fields):
    with IMAGE_STUDIO_JOB_LOCK:
        row = IMAGE_STUDIO_JOBS.get(job_id)
        if not row:
            return {}
        row.update(fields)
        return _image_studio_job_public(row)


def _finish_image_studio_request(job_id, status, **fields):
    global last_request_finished_at
    finished_at = int(time.time())
    with IMAGE_STUDIO_JOB_LOCK:
        row = IMAGE_STUDIO_JOBS.get(job_id)
        if not row:
            return {}
        was_terminal = row.get("status") in {"success", "failed", "cancelled"}
        row.update(status=status, finished_at=finished_at, **fields)
        result = _image_studio_job_public(row)
        image_studio_runtime_cache["checked_at"] = 0.0
        image_studio_activity_cache.update(checked_at=0.0, active=False)
    if not was_terminal:
        with metrics_lock:
            metrics["active_requests"] = max(0, int(metrics.get("active_requests", 0) or 0) - 1)
            if status == "success":
                metrics["completed_requests"] = int(metrics.get("completed_requests", 0) or 0) + 1
            elif status == "failed":
                metrics["failed_requests"] = int(metrics.get("failed_requests", 0) or 0) + 1
            metrics["last_status"] = status
            metrics["last_path"] = f"ai-studio:{row.get('lane') or 'generation'}"
            metrics["last_request_at"] = finished_at
            last_request_finished_at = time.time()
        try:
            refresh_status_snapshot()
        except Exception as exc:
            log_control(f"AI Studio terminal status refresh failed: {exc}")
    return result


def _load_image_studio_workflow(lane):
    spec = IMAGE_STUDIO_LANES.get(lane)
    if not spec:
        raise ValueError("Unsupported AI Studio lane.")
    return _load_image_studio_workflow_file(lane, spec["workflow"])


def _load_image_studio_workflow_file(lane, workflow_name):
    spec = IMAGE_STUDIO_LANES.get(lane)
    if not spec:
        raise ValueError("Unsupported AI Studio lane.")
    label = str(spec.get("label") or lane)
    path = os.path.join(IMAGE_STUDIO_WORKFLOW_DIR, workflow_name)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"{label} requires the AI Studio workflow file {workflow_name}, but it is missing from "
            f"{IMAGE_STUDIO_WORKFLOW_DIR}. Run Setup AI Studio after migrating the Club-3090 checkout "
            "to v0.10.0 or newer, then retry the generation."
        )
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle), spec


def _bounded_studio_dimension(value, default=1024):
    try:
        value = int(value)
    except Exception:
        value = default
    return max(256, min(2048, (value // 64) * 64))


def _image_studio_option_float(options, key, default=0.0):
    try:
        return float((options or {}).get(key) or default)
    except Exception:
        return float(default)


def _image_studio_prompt_seconds(text, default, min_seconds, max_seconds):
    value = str(text or "")
    lowered = value.lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|min|m)\b", lowered)
    if match:
        seconds = float(match.group(1)) * 60.0
    else:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|sec|s)\b", lowered)
        seconds = float(match.group(1)) if match else 0.0
    if not seconds:
        if re.search(r"\b(?:very\s+)?short\b", lowered):
            seconds = min(float(default), 5.0)
        elif re.search(r"\b(?:brief|quick|tiny)\b", lowered):
            seconds = min(float(default), 8.0)
        elif re.search(r"\b(?:long|extended)\b", lowered):
            seconds = max(float(default), min(float(max_seconds), 60.0))
        else:
            seconds = float(default)
    return max(float(min_seconds), min(float(max_seconds), float(seconds)))


def _image_studio_bool_option(options, *keys):
    for key in keys:
        value = (options or {}).get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str) and value.strip():
            return value.strip().lower() in {"1", "true", "yes", "on", "hi", "high", "high-res", "hi-res"}
    return False


def _image_studio_bool_option_with_default(options, default, *keys):
    options = options or {}
    for key in keys:
        if key not in options:
            continue
        value = options.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on", "hi", "high", "high-res", "hi-res"}:
                return True
            if lowered in {"0", "false", "no", "off", "lo", "low", "none"}:
                return False
    return bool(default)


def _image_studio_backend_plan_audio_defaults(prompt):
    text = str(prompt or "").lower()
    wants_narration = bool(
        re.search(r"\b(?:narration|narrator|voice[-\s]?over|spoken|speech|dialogue|dialog|says?|talking|read aloud)\b", text)
    )
    wants_music = bool(
        re.search(r"\b(?:music|soundtrack|score|song|audio bed|background audio|ambient audio|sound design|sfx|sound effects?)\b", text)
    )
    no_audio = bool(re.search(r"\b(?:silent|no audio|without audio|no sound|mute|muted)\b", text))
    if no_audio:
        return False, False
    return wants_music, wants_narration


def _image_studio_backend_plan_shots(prompt, options):
    try:
        explicit = int((options or {}).get("shots") or 0)
    except Exception:
        explicit = 0
    if explicit > 0:
        return max(1, min(24, explicit))
    text = str(prompt or "").lower()
    match = re.search(r"\b(\d{1,2})\s*(?:shots?|scenes?|segments?)\b", text)
    if match:
        return max(1, min(24, int(match.group(1))))
    if re.search(r"\b(?:single|one)[-\s]+(?:shot|scene|segment)\b", text):
        return 1
    return 0


def _image_studio_backend_plan_lane_token(value):
    token = str(value or "").strip().lower()
    return "" if token in {"", "auto", "default"} else token


def _image_studio_backend_plan_video_lane_order(prompt):
    lowered = str(prompt or "").lower()
    if re.search(r"\bwan(?:2\.2)?\b", lowered):
        return ["wan", "ltx", "sulphur", "10eros"]
    if re.search(r"\bsulphur|sulfur\b", lowered):
        return ["sulphur", "10eros", "ltx", "wan"]
    if re.search(r"\b10\s*eros|10eros\b", lowered):
        return ["10eros", "sulphur", "ltx", "wan"]
    return ["ltx", "wan", "sulphur", "10eros"]


def _image_studio_backend_plan_keyframe_lane_order(prompt):
    order = _image_studio_image_lane_order(prompt)
    return [lane for lane in order if lane in {"chroma", "zimage", "krea", "hidream"}]


def _image_studio_backend_plan_select_lane(kind, requested, candidates, ready, production_status):
    lane_map = (production_status or {}).get(f"{kind}_lanes") or {}
    wired = {
        lane for lane, meta in lane_map.items()
        if isinstance(meta, dict) and bool(meta.get("wired", True))
    }
    if not wired and kind == "video":
        wired = {"wan", "ltx", "sulphur", "10eros"}
    elif not wired:
        wired = {"chroma", "zimage", "krea", "hidream"}
    requested = _image_studio_backend_plan_lane_token(requested)
    if requested:
        if requested not in wired:
            raise RuntimeError(f"Backend Plan Mode production cannot render {kind} lane {requested!r}.")
        if not ready.get(requested):
            missing = _image_studio_optional_models_ready(requested)
            detail = ", ".join(missing[:3])
            if len(missing) > 3:
                detail += f", and {len(missing) - 3} more"
            raise RuntimeError(
                f"Backend Plan Mode {kind} lane {requested!r} is not installed locally"
                + (f": {detail}" if detail else ".")
            )
        return requested, False
    for lane in candidates:
        if lane in wired and ready.get(lane):
            return lane, True
    return "", True


def _image_studio_prompt_explicitly_needs_visual_text(prompt):
    text = str(prompt or "").lower()
    if re.search(r"\b(?:no|without|avoid|exclude|forbid)\s+(?:any\s+)?(?:text|letters?|words?|logos?|labels?|signs?|subtitles?|captions?|title cards?)\b", text):
        return False
    return bool(re.search(r"\b(?:readable text|visible text|typography|caption|subtitle|title card|logo|label|sign|wordmark|letters?|slogan)\b", text))


def _image_studio_backend_plan_brief(prompt):
    text = str(prompt or "").strip()
    constraints = [
        "Prompt fidelity comes first: follow the prompt explicitly without adding other elements, and preserve the user's requested subject, attributes, setting, style, camera motion, lighting, duration, and any requested inclusions or omissions.",
        "Write model-facing shot prompts in affirmative terms whenever possible: describe the requested visible content and avoid turning absent or unrequested objects into prompt_intent content.",
        "Do not add unrequested objects, characters, faces, markings, readable text, props, effects, damage, segmentation, transitions, or story beats. If the user explicitly requests any of those elements, include them normally.",
        "Keep single-shot or minimal briefs minimal; for ornate, busy, damaged, textual, character, or effects-heavy briefs, follow those requests explicitly instead of simplifying them away.",
        "For single-shot or minimal briefs, do not invent extra visual beats; use only the requested subject, attributes, setting, style, camera, motion, duration, and lighting.",
    ]
    if not _image_studio_prompt_explicitly_needs_visual_text(text):
        constraints.append("Do not add readable writing, labels, logos, subtitles, title cards, or watermarks unless the request explicitly needs readable writing.")
        constraints.append("Do not place absent visual-text concepts into prompt_intent as negated prose; use affirmative wording that keeps surfaces and backgrounds faithful to the brief instead.")
    if not text:
        return " ".join(constraints)
    return f"{text}\n\n" + "\n".join(constraints)


def _image_studio_backend_plan_payload(prompt, options, status):
    ready = _image_studio_ready_lanes()
    production = (status or {}).get("production") or status or {}
    video_lane, auto_video = _image_studio_backend_plan_select_lane(
        "video",
        (options or {}).get("video_lane"),
        _image_studio_backend_plan_video_lane_order(prompt),
        ready,
        production,
    )
    if not video_lane:
        raise RuntimeError("Backend Plan Mode has no installed production video lane. Download LTX, Wan, Sulphur, or 10Eros first.")
    requested_continuity = _image_studio_backend_plan_lane_token((options or {}).get("continuity"))
    continuity = requested_continuity or "storyboard"
    keyframe_lane, auto_keyframe = _image_studio_backend_plan_select_lane(
        "keyframe",
        (options or {}).get("keyframe_lane"),
        _image_studio_backend_plan_keyframe_lane_order(prompt),
        ready,
        production,
    )
    if continuity in {"chain", "hero", "storyboard"} and not keyframe_lane:
        if requested_continuity:
            raise RuntimeError(
                "Backend Plan Mode continuity needs an installed production keyframe lane. "
                "Download Chroma, Z-Image, Krea, or HiDream, or use continuity='none'."
            )
        continuity = "none"
        keyframe_lane = "chroma"
    elif not keyframe_lane:
        keyframe_lane = "chroma"
    default_music, default_narration = _image_studio_backend_plan_audio_defaults(prompt)
    music = _image_studio_bool_option_with_default(options, default_music, "music")
    narration = _image_studio_bool_option_with_default(options, default_narration, "narration")
    payload = {
        "brief": _image_studio_backend_plan_brief(prompt),
        "video_lane": video_lane,
        "keyframe_lane": keyframe_lane,
        "continuity": continuity,
        "music": music,
        "narration": narration,
        "voice": (options or {}).get("voice") or "",
        "shots": _image_studio_backend_plan_shots(prompt, options),
        "research": _image_studio_bool_option(options, "research"),
        "backend": (options or {}).get("backend") or "live",
    }
    return payload, {
        "auto_video_lane": auto_video,
        "auto_keyframe_lane": auto_keyframe,
        "audio_requested": bool(music or narration),
        "ready_lanes": {lane: bool(value) for lane, value in ready.items()},
    }


def _image_studio_strip_audio(input_path, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    commands = [
        ["ffmpeg", "-y", "-v", "error", "-i", input_path, "-map", "0:v:0", "-an", "-c:v", "copy", output_path],
        ["ffmpeg", "-y", "-v", "error", "-i", input_path, "-map", "0:v:0", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", output_path],
    ]
    last_error = ""
    for command in commands:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
            if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                return output_path
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(f"Failed to strip audio from Backend Plan output: {last_error}")


def _image_studio_backend_plan_recover_visual_output(production_job_id, audio_requested):
    prod_dir = os.path.join(IMAGE_STUDIO_OUTPUT_ROOT, "productions", str(production_job_id or ""))
    shots_dir = os.path.join(prod_dir, "shots")
    if not os.path.isdir(shots_dir):
        return None
    candidates = [
        os.path.join(shots_dir, name)
        for name in sorted(os.listdir(shots_dir))
        if name.lower().endswith((".mp4", ".mov", ".mkv", ".webm"))
    ]
    candidates = [path for path in candidates if os.path.isfile(path) and os.path.getsize(path) > 0]
    if not candidates:
        return None
    source = candidates[-1]
    if audio_requested:
        return _image_studio_output_for_local_path(source, "video")
    output_path = os.path.join(prod_dir, "assembly", "final.visual-only.no-audio.mp4")
    return _image_studio_output_for_local_path(_image_studio_strip_audio(source, output_path), "video")


def _image_studio_wan_hi_res(prompt, options):
    if _image_studio_bool_option(options, "wan_hi_res", "hi_res", "high_res"):
        return True
    try:
        width = int((options or {}).get("width") or 0)
        height = int((options or {}).get("height") or 0)
    except Exception:
        width = height = 0
    if width >= 1200 or height >= 700:
        return True
    return bool(re.search(r"\b(?:720p|1280\s*x\s*720|hi[-\s]?res|high[-\s]?resolution)\b", str(prompt or ""), re.I))


def _image_studio_wan_distorch_loader(unet_name):
    return {
        "class_type": "UnetLoaderGGUFDisTorch2MultiGPU",
        "inputs": {
            "unet_name": unet_name,
            "compute_device": "cuda:0",
            "donor_device": "cuda:1",
            "virtual_vram_gb": 24.0,
            "eject_models": True,
        },
    }


def _image_studio_wan_dimensions(prompt, options):
    if _image_studio_wan_hi_res(prompt, options):
        return 1280, 720, True
    return (
        _bounded_studio_dimension((options or {}).get("width"), 832),
        _bounded_studio_dimension((options or {}).get("height"), 480),
        False,
    )


def _image_studio_wan_target_seconds(prompt, options):
    max_seconds = 20.0
    try:
        max_seconds = max(1.0, min(60.0, float((options or {}).get("wan_max_seconds") or max_seconds)))
    except Exception:
        pass
    for key in ("target_seconds", "duration_seconds", "seconds"):
        try:
            value = float((options or {}).get(key) or 0)
        except Exception:
            value = 0.0
        if value > 0:
            return max(1.0, min(max_seconds, value))
    return _image_studio_prompt_seconds(prompt, default=5.0, min_seconds=1.0, max_seconds=max_seconds)


def _image_studio_wan_segment_plan(prompt, options):
    fps = float((options or {}).get("fps") or (options or {}).get("wan_fps") or 16.0)
    fps = max(1.0, min(60.0, fps))
    target_seconds = _image_studio_wan_target_seconds(prompt, options)
    explicit_frames = (options or {}).get("frames") or (options or {}).get("wan_frames")
    try:
        frames = int(explicit_frames or 0)
    except Exception:
        frames = 0
    if frames <= 0:
        native_frames = 81
        target_frames = int(round(target_seconds * fps))
        frames = target_frames if target_seconds < (native_frames / fps) - 0.25 else native_frames
    frames = max(17, min(321, frames))
    frames = ((frames - 1) // 4) * 4 + 1
    segment_seconds = max(1.0 / fps, frames / fps)
    segments = 1
    if target_seconds > segment_seconds + 0.5:
        try:
            max_seconds = max(1.0, min(60.0, float((options or {}).get("wan_max_seconds") or 20.0)))
        except Exception:
            max_seconds = 20.0
        segment_cap = max(1, int(math.ceil(max_seconds / segment_seconds)))
        segments = min(segment_cap, max(2, int(math.ceil(target_seconds / segment_seconds))))
    return frames, fps, target_seconds, segments


def _image_studio_wan_workflow(prompt, options):
    image_name = str((options or {}).get("comfy_image_name") or "").strip()
    lane_spec = IMAGE_STUDIO_LANES["wan"]
    workflow_name = "wan22_rapid_i2v.json" if image_name else lane_spec["workflow"]
    workflow, _ = _load_image_studio_workflow_file("wan", workflow_name)
    width, height, hi_res = _image_studio_wan_dimensions(prompt, options)
    frames, fps, _target_seconds, _segments = _image_studio_wan_segment_plan(prompt, options)
    workflow["pos"]["inputs"]["text"] = _image_studio_video_positive_prompt(prompt)
    workflow["neg"]["inputs"]["text"] = IMAGE_STUDIO_VIDEO_NEGATIVE_PROMPT
    if hi_res and "unet" in workflow:
        workflow["unet"] = _image_studio_wan_distorch_loader(workflow["unet"]["inputs"]["unet_name"])
    for key in ("latent", "i2v"):
        if key in workflow:
            workflow[key]["inputs"].update({"width": width, "height": height, "length": frames})
    if "resize" in workflow:
        workflow["resize"]["inputs"].update({"width": width, "height": height})
    if "ksampler" in workflow:
        workflow["ksampler"]["inputs"].update({
            "steps": int((options or {}).get("steps") or 4),
            "cfg": float((options or {}).get("cfg") or 1.0),
            "seed": int((options or {}).get("seed") or secrets.randbelow(2**31 - 1)),
        })
    if "video" in workflow:
        workflow["video"]["inputs"]["fps"] = fps
    if image_name and "loadimage" in workflow:
        workflow["loadimage"]["inputs"]["image"] = image_name
    return workflow


def _image_studio_wan_chain_workflow(prompt, options):
    base, _ = _load_image_studio_workflow("wan")
    image_name = str((options or {}).get("comfy_image_name") or "").strip()
    width, height, hi_res = _image_studio_wan_dimensions(prompt, options)
    frames, fps, _target_seconds, segments = _image_studio_wan_segment_plan(prompt, options)
    seed = int((options or {}).get("seed") or secrets.randbelow(2**31 - 1))
    unet_name = base["unet"]["inputs"]["unet_name"]
    unet = _image_studio_wan_distorch_loader(unet_name) if hi_res else {
        "class_type": "UnetLoaderGGUF",
        "inputs": {"unet_name": unet_name},
    }

    def ksamp(positive, negative, latent, segment_seed):
        return {
            "class_type": "KSampler",
            "inputs": {
                "model": ["modelsampling", 0],
                "seed": segment_seed,
                "steps": int((options or {}).get("steps") or 4),
                "cfg": float((options or {}).get("cfg") or 1.0),
                "sampler_name": "euler_ancestral",
                "scheduler": "beta",
                "positive": positive,
                "negative": negative,
                "latent_image": latent,
                "denoise": 1.0,
            },
        }

    workflow = {
        "unet": unet,
        "clip": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": base["clip"]["inputs"]["clip_name"],
                "type": "wan",
                "device": "default",
            },
        },
        "vae": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": base["vae"]["inputs"]["vae_name"]},
        },
        "modelsampling": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"model": ["unet", 0], "shift": 5.0},
        },
        "pos": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": _image_studio_video_positive_prompt(prompt), "clip": ["clip", 0]},
        },
        "neg": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": IMAGE_STUDIO_VIDEO_NEGATIVE_PROMPT, "clip": ["clip", 0]},
        },
    }
    if image_name:
        workflow["loadimage"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
        workflow["resize"] = {
            "class_type": "ImageScale",
            "inputs": {"image": ["loadimage", 0], "upscale_method": "lanczos", "width": width, "height": height, "crop": "center"},
        }
        workflow["i2v1"] = {
            "class_type": "WanImageToVideo",
            "inputs": {
                "positive": ["pos", 0],
                "negative": ["neg", 0],
                "vae": ["vae", 0],
                "width": width,
                "height": height,
                "length": frames,
                "batch_size": 1,
                "start_image": ["resize", 0],
            },
        }
        workflow["ksampler1"] = ksamp(["i2v1", 0], ["i2v1", 1], ["i2v1", 2], seed)
    else:
        workflow["latent1"] = {
            "class_type": "EmptyHunyuanLatentVideo",
            "inputs": {"width": width, "height": height, "length": frames, "batch_size": 1},
        }
        workflow["ksampler1"] = ksamp(["pos", 0], ["neg", 0], ["latent1", 0], seed)
    workflow["decode1"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["ksampler1", 0], "vae": ["vae", 0]},
    }
    cat = ["decode1", 0]
    previous_decode = "decode1"
    for index in range(2, max(2, segments) + 1):
        last = f"last{index}"
        i2v = f"i2v{index}"
        sampler = f"ksampler{index}"
        decode = f"decode{index}"
        trim = f"trim{index}"
        concat = f"concat{index}"
        workflow[last] = {
            "class_type": "ImageFromBatch",
            "inputs": {"image": [previous_decode, 0], "batch_index": frames - 1, "length": 1},
        }
        workflow[i2v] = {
            "class_type": "WanImageToVideo",
            "inputs": {
                "positive": ["pos", 0],
                "negative": ["neg", 0],
                "vae": ["vae", 0],
                "width": width,
                "height": height,
                "length": frames,
                "batch_size": 1,
                "start_image": [last, 0],
            },
        }
        workflow[sampler] = ksamp([i2v, 0], [i2v, 1], [i2v, 2], seed + index)
        workflow[decode] = {
            "class_type": "VAEDecode",
            "inputs": {"samples": [sampler, 0], "vae": ["vae", 0]},
        }
        workflow[trim] = {
            "class_type": "ImageFromBatch",
            "inputs": {"image": [decode, 0], "batch_index": 1, "length": frames - 1},
        }
        workflow[concat] = {
            "class_type": "ImageBatch",
            "inputs": {"image1": cat, "image2": [trim, 0]},
        }
        cat = [concat, 0]
        previous_decode = decode
    workflow["video"] = {
        "class_type": "CreateVideo",
        "inputs": {"images": cat, "fps": fps},
    }
    workflow["save"] = {
        "class_type": "SaveVideo",
        "inputs": {"video": ["video", 0], "filename_prefix": "wan-long", "format": "auto", "codec": "auto"},
    }
    return workflow


def _image_studio_video_workflow(lane, prompt, options):
    if lane == "wan":
        if _image_studio_wan_segment_plan(prompt, options)[3] > 1:
            return _image_studio_wan_chain_workflow(prompt, options)
        return _image_studio_wan_workflow(prompt, options)
    workflow, _ = _load_image_studio_workflow(lane)
    dev_ltx = lane in {"sulphur", "10eros"}
    unet_name = {
        "sulphur": "sulphur-2/sulphur_dev-Q8_0.gguf",
        "10eros": "10eros/10Eros_v1-Q8_0.gguf",
    }.get(lane, "ltx2.3/distilled-1.1/ltx-2.3-22b-distilled-1.1-Q8_0.gguf")
    workflow["3"]["inputs"].update({
        "unet_name": unet_name,
        "compute_device": "cuda:0",
        "donor_device": "cuda:1",
        "virtual_vram_gb": 24.0,
        "eject_models": True,
    })
    workflow["1"]["inputs"]["vae_name"] = "ltx-2.3-22b-dev_audio_vae.safetensors" if dev_ltx else "ltx-2.3-22b-distilled_audio_vae.safetensors"
    workflow["2"]["inputs"]["vae_name"] = "ltx-2.3-22b-dev_video_vae.safetensors" if dev_ltx else "ltx-2.3-22b-distilled_video_vae.safetensors"
    workflow["47"]["inputs"]["clip_name2"] = "ltx-2.3-22b-dev_embeddings_connectors.safetensors" if dev_ltx else "ltx-2.3-22b-distilled_embeddings_connectors.safetensors"
    width, height = ((1280, 720) if dev_ltx else (768, 512))
    workflow["7"]["inputs"].update({"width": width, "height": height})
    workflow["8"]["inputs"]["scale_by"] = 1.0
    target_seconds = _image_studio_video_target_seconds(prompt, options)
    target_frames = int(round(target_seconds * 24.0)) if target_seconds > 0 else 241
    frames = max(49, min(361, int(options.get("frames") or target_frames or 241)))
    frames = ((frames - 1) // 8) * 8 + 1
    workflow["10"]["inputs"]["value"] = frames
    workflow["5"]["inputs"]["text"] = _image_studio_video_positive_prompt(prompt)
    workflow["6"]["inputs"]["text"] = IMAGE_STUDIO_VIDEO_NEGATIVE_PROMPT
    workflow["16"]["inputs"]["noise_seed"] = int(options.get("seed") or secrets.randbelow(2**31 - 1))
    if dev_ltx:
        workflow["50"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["3", 0],
                "lora_name": "ltx-2.3-22b-distilled-lora-384-1.1.safetensors",
                "strength_model": 1.0,
            },
        }
        workflow["18"]["inputs"]["model"] = ["50", 0]
    image_name = str(options.get("comfy_image_name") or "").strip()
    if image_name:
        workflow["100"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
        workflow["101"] = {"class_type": "ResizeImagesByLongerEdge", "inputs": {"images": ["100", 0], "longer_edge": 1280 if dev_ltx else 768}}
        workflow["102"] = {"class_type": "LTXVPreprocess", "inputs": {"image": ["101", 0], "img_compression": 35}}
        workflow["103"] = {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {"vae": ["2", 0], "image": ["102", 0], "latent": ["14", 0], "strength": 1.0, "bypass": False},
        }
        workflow["15"]["inputs"]["video_latent"] = ["103", 0]
    return workflow


def _image_studio_video_positive_prompt(prompt):
    text = str(prompt or "").strip()
    lowered = text.lower()
    if "no on-screen text" in lowered and "under any condition" in lowered:
        return text
    if not text:
        return IMAGE_STUDIO_VIDEO_TEXT_BAN
    return f"{text}\n\n{IMAGE_STUDIO_VIDEO_TEXT_BAN}"


def _image_studio_video_target_seconds(prompt, options):
    for key in ("target_seconds", "duration_seconds", "seconds"):
        try:
            value = float((options or {}).get(key) or 0)
        except Exception:
            value = 0.0
        if value > 0:
            return max(1.0, min(120.0, value))
    return _image_studio_prompt_seconds(prompt, default=10.0, min_seconds=1.0, max_seconds=120.0)


def _image_studio_orchestrator_request(path, payload=None, timeout=30):
    request = urllib.request.Request(
        IMAGE_STUDIO_ORCHESTRATOR_URL.rstrip("/") + path,
        data=(
            json.dumps(payload or {}, separators=(",", ":")).encode("utf-8")
            if payload is not None
            else None
        ),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=max(5, int(timeout or 30))) as response:
        return json.loads(response.read().decode("utf-8", errors="replace") or "{}")


def _image_studio_video_output_from_orchestrator(job):
    filename = str((job or {}).get("filename") or "").strip()
    if not filename:
        return None
    subfolder = str((job or {}).get("subfolder") or "video").strip("/\\")
    relative = _image_studio_output_relative_path(filename, subfolder)
    query = urllib.parse.urlencode({"root_path": "/", "relative_path": relative})
    return {
        "kind": "video",
        "name": filename,
        "root_path": "/",
        "relative_path": relative,
        "url": f"/admin/storage-browser/preview?{query}",
        "duration_seconds": (job or {}).get("target_seconds"),
        "segments": (job or {}).get("segments"),
    }


def _image_studio_trim_video_output(output, target_seconds):
    try:
        seconds = float(target_seconds or 0)
    except Exception:
        seconds = 0.0
    if seconds <= 0:
        return output
    source = _image_studio_output_abs_path(output)
    if not source or not os.path.isfile(source):
        return output
    root, ext = os.path.splitext(source)
    target = f"{root}__{int(round(seconds))}s{ext or '.mp4'}"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-i",
                source,
                "-t",
                ("%.3f" % seconds).rstrip("0").rstrip("."),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                target,
            ],
            check=True,
            timeout=300,
        )
        if os.path.isfile(target) and os.path.getsize(target) > 0:
            relative = os.path.relpath(target, "/").replace("\\", "/")
            query = urllib.parse.urlencode({"root_path": "/", "relative_path": relative})
            output = dict(output or {})
            output.update({
                "name": os.path.basename(target),
                "root_path": "/",
                "relative_path": relative,
                "url": f"/admin/storage-browser/preview?{query}",
                "duration_seconds": seconds,
            })
    except Exception as exc:
        log_audit("image_studio_long_video_trim_failed", error=str(exc), target_seconds=seconds)
    return output


def _image_studio_run_long_video_job(job_id, lane, prompt, options, cancel_event):
    target_seconds = _image_studio_video_target_seconds(prompt, options)
    if lane == "wan" or target_seconds <= 15 or str((options or {}).get("comfy_image_name") or "").strip():
        return None
    segments = max(2, min(12, int(math.ceil(target_seconds / 10.0))))
    timeout_seconds = max(
        900,
        min(7200, int((options or {}).get("timeout_seconds") or (segments * 1500))),
    )
    _set_image_studio_job(
        job_id,
        status="submitting",
        detail=f"Submitting long video to the Studio Orchestrator ({segments} segments, {target_seconds:g}s target).",
    )
    start = _image_studio_orchestrator_request(
        "/extend",
        {
            "prompt": prompt,
            "lane": lane,
            "segments": segments,
            "frames": 241,
            "target_seconds": target_seconds,
        },
        timeout=60,
    )
    orchestrator_job_id = str(start.get("job_id") or "")
    if not orchestrator_job_id:
        raise RuntimeError("Studio Orchestrator did not return a long-video job id.")
    deadline = time.monotonic() + timeout_seconds
    last_progress = ""
    while time.monotonic() < deadline:
        if cancel_event.wait(5):
            try:
                _image_studio_json_request("/interrupt", {}, timeout=10)
            except Exception:
                pass
            _finish_image_studio_request(job_id, "cancelled", detail="Generation cancelled.")
            return {"cancelled": True}
        job = _image_studio_orchestrator_request(
            "/job/" + urllib.parse.quote(orchestrator_job_id),
            timeout=30,
        )
        progress = str(job.get("progress") or "")
        if progress and progress != last_progress:
            last_progress = progress
            _set_image_studio_job(
                job_id,
                status="running",
                detail=f"Long video segment {progress} is rendering ({target_seconds:g}s target).",
                orchestrator_job_id=orchestrator_job_id,
            )
        status = str(job.get("status") or "").lower()
        if status == "done":
            output = _image_studio_video_output_from_orchestrator(job)
            if not output:
                raise RuntimeError("Studio Orchestrator completed without a video output.")
            return _image_studio_trim_video_output(output, target_seconds)
        if status == "error":
            raise RuntimeError(str(job.get("error") or "Studio Orchestrator failed."))
    raise TimeoutError("Long video generation timed out.")


def _prepare_image_studio_workflow(lane, prompt, options):
    if lane in {"ltx", "sulphur", "10eros", "wan"}:
        return _image_studio_video_workflow(lane, prompt, options), IMAGE_STUDIO_LANES[lane]
    workflow, spec = _load_image_studio_workflow(lane)
    seed = int(options.get("seed") or secrets.randbelow(2**31 - 1))
    width = _bounded_studio_dimension(options.get("width"), 1024)
    height = _bounded_studio_dimension(options.get("height"), 1024)
    if lane == "ideogram":
        candidate_grid = bool(options.get("candidate_grid", True))
        workflow["pos"]["inputs"]["text"] = (
            _image_studio_ideogram_candidate_grid_caption(
                prompt,
                options.get("candidate_identity"),
            )
            if candidate_grid
            else _image_studio_craft_ideogram_caption(prompt)
        )
        workflow["sigmas"]["inputs"].update({"steps": int(options.get("steps") or 20), "width": width, "height": height})
        workflow["latent"]["inputs"].update({"width": width, "height": height})
        workflow["noise"]["inputs"]["noise_seed"] = seed
    elif lane == "chroma":
        workflow["pos"]["inputs"]["text"] = prompt
        workflow["latent"]["inputs"].update({"width": width, "height": height})
        workflow["sigmas"]["inputs"]["steps"] = int(options.get("steps") or 26)
        workflow["guider"]["inputs"]["cfg"] = float(options.get("cfg") or 3.5)
        workflow["noise"]["inputs"]["noise_seed"] = seed
    elif lane == "hidream":
        workflow["cond"]["inputs"]["prompt"] = prompt
        workflow["sampler"]["inputs"].update({
            "width": width,
            "height": height,
            "steps": int(options.get("steps") or 0),
            "seed": seed,
        })
    elif lane == "zimage":
        workflow["pos"]["inputs"]["text"] = prompt
        workflow["latent"]["inputs"].update({"width": width, "height": height})
        workflow["ksampler"]["inputs"].update({
            "steps": int(options.get("steps") or 8),
            "cfg": float(options.get("cfg") or 1.0),
            "seed": seed,
        })
    elif lane == "krea":
        workflow["pos"]["inputs"]["text"] = prompt
        workflow["latent"]["inputs"].update({"width": width, "height": height})
        workflow["ksampler"]["inputs"].update({
            "steps": int(options.get("steps") or 8),
            "cfg": float(options.get("cfg") or 1.0),
            "seed": seed,
        })
    elif lane == "music":
        workflow["pos"]["inputs"]["tags"] = prompt
        workflow["pos"]["inputs"]["lyrics"] = str(options.get("lyrics") or "[instrumental]")
        seconds = _image_studio_option_float(options, "seconds") or _image_studio_prompt_seconds(prompt, 60.0, 5.0, 180.0)
        workflow["latent"]["inputs"]["seconds"] = max(5.0, min(180.0, seconds))
        workflow["ksampler"]["inputs"].update({
            "steps": int(options.get("steps") or 50),
            "cfg": float(options.get("cfg") or 5.0),
            "seed": seed,
        })
    elif lane == "sfx":
        workflow["pos"]["inputs"]["text"] = prompt
        seconds = _image_studio_option_float(options, "seconds") or _image_studio_prompt_seconds(prompt, 10.0, 1.0, 47.0)
        workflow["latent"]["inputs"]["seconds"] = max(1.0, min(47.0, seconds))
        workflow["ksampler"]["inputs"].update({
            "steps": int(options.get("steps") or 50),
            "seed": seed,
        })
    return workflow, spec


def _store_image_studio_workflow(job_id, workflow, spec, lane):
    if not workflow or not spec:
        return
    try:
        snapshot = json.loads(json.dumps(workflow))
    except Exception:
        snapshot = workflow
    _set_image_studio_job(
        job_id,
        workflow=snapshot,
        workflow_label=str((spec or {}).get("label") or ""),
        workflow_kind=str((spec or {}).get("kind") or ""),
        workflow_lane=str(lane or ""),
    )


def _image_studio_upload_attachment(attachment):
    data_url = chat_attachment_data_url(str((attachment or {}).get("url") or ""))
    if not data_url.startswith("data:image/") or ";base64," not in data_url:
        raise ValueError("Video animation requires an image attachment.")
    header, encoded = data_url.split(",", 1)
    mime = header[5:].split(";", 1)[0]
    ext = (mime.split("/", 1)[-1] or "png").split("+", 1)[0]
    raw = base64.b64decode(encoded)
    boundary = "----club3090studio" + secrets.token_hex(8)
    filename = f"studio_input_{secrets.token_hex(5)}.{ext}"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8") + raw + (
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue"
        f"\r\n--{boundary}--\r\n"
    ).encode("utf-8")
    request = urllib.request.Request(
        IMAGE_STUDIO_COMFY_URL.rstrip("/") + "/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return str((json.load(response) or {}).get("name") or filename)


def _image_studio_local_output(kind, filename, subfolder=""):
    relative = _image_studio_output_relative_path(filename, subfolder)
    query = urllib.parse.urlencode({"root_path": "/", "relative_path": relative})
    return {
        "kind": kind,
        "name": os.path.basename(str(filename or "")),
        "root_path": "/",
        "relative_path": relative,
        "url": f"/admin/storage-browser/preview?{query}",
    }


def _image_studio_output_abs_path(output):
    relative = str((output or {}).get("relative_path") or "").strip().lstrip("/\\")
    if not relative:
        return ""
    return os.path.realpath(os.path.join("/", relative))


def _image_studio_delete_outputs(outputs):
    for output in outputs or []:
        try:
            os.remove(_image_studio_output_abs_path(output))
        except FileNotFoundError:
            pass


def _image_studio_split_grid_output(output, labels):
    source_path = _image_studio_output_abs_path(output)
    clean_labels = [str(value or "").strip() for value in (labels or []) if str(value or "").strip()][:4]
    if not source_path or not clean_labels:
        return []
    from PIL import Image
    stem, _extension = os.path.splitext(source_path)
    cropped = []
    def inset_box(box, panel_width, panel_height):
        inset = max(6, int(round(min(panel_width, panel_height) * 0.025)))
        left, top, right, bottom = box
        return (left + inset, top + inset, right - inset, bottom - inset)
    def trim_light_frame(panel):
        try:
            width, height = panel.size
            pixels = panel.load()
            def light_edge_columns(from_left=True):
                limit = max(2, min(24, width // 10))
                count = 0
                for offset in range(limit):
                    x = offset if from_left else width - 1 - offset
                    samples = [pixels[x, y] for y in range(0, height, max(1, height // 64))]
                    if not samples:
                        break
                    light = sum(1 for red, green, blue in samples if red >= 235 and green >= 235 and blue >= 235)
                    if light / len(samples) < 0.82:
                        break
                    count += 1
                return count
            def light_edge_rows(from_top=True):
                limit = max(2, min(24, height // 10))
                count = 0
                for offset in range(limit):
                    y = offset if from_top else height - 1 - offset
                    samples = [pixels[x, y] for x in range(0, width, max(1, width // 64))]
                    if not samples:
                        break
                    light = sum(1 for red, green, blue in samples if red >= 235 and green >= 235 and blue >= 235)
                    if light / len(samples) < 0.82:
                        break
                    count += 1
                return count
            left = light_edge_columns(True)
            right = light_edge_columns(False)
            top = light_edge_rows(True)
            bottom = light_edge_rows(False)
            if left or right or top or bottom:
                return panel.crop((left, top, max(left + 1, width - right), max(top + 1, height - bottom)))
        except Exception:
            pass
        return panel
    with Image.open(source_path) as image:
        image = image.convert("RGB")
        width, height = image.size
        half_width = width // 2
        half_height = height // 2
        boxes = [
            inset_box((0, 0, half_width, half_height), half_width, half_height),
            inset_box((half_width, 0, width, half_height), width - half_width, half_height),
            inset_box((0, half_height, half_width, height), half_width, height - half_height),
            inset_box((half_width, half_height, width, height), width - half_width, height - half_height),
        ]
        for index, label in enumerate(clean_labels):
            filename = f"{os.path.basename(stem)}_panel_{index + 1}.png"
            target = os.path.join(os.path.dirname(source_path), filename)
            trim_light_frame(image.crop(boxes[index])).save(target, format="PNG", optimize=True)
            subfolder = os.path.relpath(
                os.path.dirname(source_path),
                IMAGE_STUDIO_OUTPUT_ROOT,
            ).replace("\\", "/")
            if subfolder == "." or subfolder.startswith("../"):
                subfolder = ""
            crop = _image_studio_local_output("image", filename, subfolder)
            crop["label"] = label
            cropped.append(crop)
    return cropped


def _image_studio_director_pick_grid(outputs, prompt, identity=""):
    prompt = str(prompt or "").strip()
    identity = str(identity or "").strip()
    if not outputs or not prompt:
        return None, False
    content = [{
        "type": "text",
        "text": (
            "You are selecting the best surviving candidate from an Ideogram contact sheet. "
            f"Original image request: {prompt}. "
            + (
                f"The named subject must be recognizable specifically as {identity} from official or public-domain likenesses. "
                if identity
                else ""
            )
            + "Choose the single crop that best satisfies the requested subject, composition, style, objects, palette, "
            "and readable text. Every acceptable crop must be exactly one coherent complete image with no internal "
            "panel divider, split-screen layout, contact sheet, collage, or multiple alternative renderings. "
            "Reject wrong subjects, generic substitutions, malformed crops, duplicated contact sheets, "
            'or safety-filter placeholders. Return only JSON: {"best_index":1,"confidence":0.0,"acceptable":true}. '
            "best_index is 1-based among the supplied surviving crops."
        ),
    }]
    try:
        for output in outputs:
            path = _image_studio_output_abs_path(output)
            with open(path, "rb") as handle:
                encoded = base64.b64encode(handle.read()).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}})
        payload = {
            "model": IMAGE_STUDIO_DIRECTOR_MODEL,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 240,
            "temperature": 0.0,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = urllib.request.Request(
            "http://127.0.0.1:8090/v1/chat/completions",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.load(response)
        message = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        parsed = _image_studio_parse_json_object(message)
        best_index = int(parsed.get("best_index") or 0) - 1
        confidence = float(parsed.get("confidence") or 0.0)
        if 0 <= best_index < len(outputs):
            selected = outputs[best_index]
            selected["identity_confidence"] = confidence
            if identity:
                selected["label"] = identity
            accepted = bool(parsed.get("acceptable", False)) and confidence >= 0.35
            return selected, accepted
    except Exception as exc:
        log_audit("image_studio_grid_rank_failed", error=str(exc))
        return None, False
    return None, False


def _image_studio_ideogram_placeholder_detected(output):
    path = _image_studio_output_abs_path(output)
    if not path or not os.path.isfile(path):
        return False
    try:
        from PIL import Image, ImageStat
        with Image.open(path) as img:
            rgb = img.convert("RGB").resize((96, 96))
            gray = rgb.convert("L")
            gray_stat = ImageStat.Stat(gray)
            rgb_stat = ImageStat.Stat(rgb)
            extrema = gray.getextrema()
            spread = float((extrema[1] if extrema else 0) - (extrema[0] if extrema else 0))
            stddev = float((gray_stat.stddev or [0])[0])
            channel_means = [float(value) for value in (rgb_stat.mean or [0, 0, 0])]
            colorfulness = max(channel_means) - min(channel_means)
        return colorfulness < 8 and spread < 110 and stddev < 32
    except Exception:
        return False


def _image_studio_internal_panel_divider_detected(output):
    path = _image_studio_output_abs_path(output)
    if not path or not os.path.isfile(path):
        return False
    try:
        from PIL import Image, ImageStat
        with Image.open(path) as img:
            gray = img.convert("L").resize((256, 256))
            return (
                _image_studio_grid_line_detected(gray, ImageStat, True, (0.5,))
                or _image_studio_grid_line_detected(gray, ImageStat, False, (0.5,))
            )
    except Exception:
        return False


def _image_studio_grid_line_detected(gray, image_stat, vertical, fractions):
    width, height = gray.size
    axis = width if vertical else height
    for fraction in fractions:
        center_pos = int(round(axis * float(fraction)))
        start = max(5, center_pos - 5)
        end = min(axis - 5, center_pos + 6)
        for pos in range(start, end):
            if vertical:
                center = image_stat.Stat(gray.crop((pos, 0, pos + 1, height)))
                before = image_stat.Stat(gray.crop((pos - 4, 0, pos - 3, height)))
                after = image_stat.Stat(gray.crop((pos + 4, 0, pos + 5, height)))
            else:
                center = image_stat.Stat(gray.crop((0, pos, width, pos + 1)))
                before = image_stat.Stat(gray.crop((0, pos - 4, width, pos - 3)))
                after = image_stat.Stat(gray.crop((0, pos + 4, width, pos + 5)))
            if (
                center.stddev[0] <= 45
                and abs(center.mean[0] - before.mean[0]) >= 50
                and abs(center.mean[0] - after.mean[0]) >= 50
            ):
                return True
    return False


def _image_studio_extra_grid_divider_detected(output):
    path = _image_studio_output_abs_path(output)
    if not path or not os.path.isfile(path):
        return False
    try:
        from PIL import Image, ImageStat
        with Image.open(path) as img:
            gray = img.convert("L").resize((256, 256))
            return (
                _image_studio_grid_line_detected(gray, ImageStat, True, (0.25, 0.75))
                or _image_studio_grid_line_detected(gray, ImageStat, False, (0.25, 0.75))
            )
    except Exception:
        return False


def _image_studio_ideogram_retry_prompt(prompt, attempt):
    value = str(prompt or "").strip()
    portrait = re.search(
        r"\b(?:portrait|painting|photograph|photo)\s+of\s+"
        r"([A-Z][A-Za-z.' -]{2,70}?)(?=\s+(?:in|wearing|standing|seated|with|before)\b|[,.;]|$)",
        value,
    )
    if portrait:
        identity = portrait.group(1).strip()
        return (
            f"Create a neutral educational archive portrait of the named subject {identity}. "
            f"The subject must be recognizable specifically as {identity} when public reference likenesses exist, "
            "with distinctive facial features, hair, age, clothing, setting, and era preserved from the request. "
            "Use a dignified archival illustration or editorial portrait rather than a deceptive modern photograph. "
            "No slogans, advocacy, violence, symbols, or visible text unless the request explicitly requires text. "
            f"Original art direction: {value}"
        )
    return (
        "Reframe this as clearly benign editorial artwork with a neutral educational context, no violence, "
        "sexual content, political advocacy, or visible text. Preserve the requested subject and composition "
        f"faithfully. Retry variation {int(attempt)}. Original art direction: {value}"
    )


def _image_studio_model_roots():
    roots = [
        os.environ.get("COMFYUI_MODELS_DIR", ""),
        os.path.join(CLUB3090_DIR, "ai-studio-models", "comfyui", "models"),
        os.path.join(CLUB3090_DIR, "ai-studio-models", "comfyui", "ComfyUI", "models"),
        "/mnt/models/comfyui/models",
    ]
    comfy_root = os.environ.get("COMFYUI_ROOT", "")
    if comfy_root:
        roots.append(os.path.join(comfy_root, "models"))
    result = []
    seen = set()
    for root in roots:
        value = os.path.realpath(os.path.abspath(str(root or "").strip()))
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _image_studio_required_model_path_exists(relative):
    rel_parts = str(relative or "").strip("/\\").split("/")
    if not rel_parts or not rel_parts[0]:
        return False
    for model_root in _image_studio_model_roots():
        path = os.path.join(model_root, *rel_parts)
        if os.path.isdir(path):
            try:
                if any(os.scandir(path)):
                    return True
            except OSError:
                continue
        elif os.path.isfile(path):
            return True
    return False


def _image_studio_optional_models_ready(lane):
    missing = []
    for relative in IMAGE_STUDIO_OPTIONAL_MODEL_PATHS.get(lane, ()):
        if not _image_studio_required_model_path_exists(relative):
            missing.append(relative)
    return missing


def _image_studio_min_ideogram_caption(text):
    value = str(text or "").strip() or "A polished Club 3090 studio image."
    quoted_text = re.findall(r'"([^"]{1,80})"', value)
    visible_text = quoted_text[0] if quoted_text else ("CLUB 3090" if "club 3090" in value.lower() else "")
    subject = (
        f'a polished professional graphic design composition featuring the exact readable text "{visible_text}"'
        if visible_text else
        f"a polished professional graphic design composition based on this brief: {value}"
    )
    text_detail = (
        f'exact visible text "{visible_text}", crisp typography, centered readable letterforms, high contrast'
        if visible_text else
        "clean central subject with clear silhouette, premium design hierarchy, no clutter"
    )
    return json.dumps({
        "high_level_description": (
            f"{subject}. The image is a complete, print-ready 1024 by 1024 composition with a clear focal subject, "
            "balanced negative space, crisp edges, and no empty or ambiguous regions."
        ),
        "style_description": {
            "aesthetics": (
                "premium modern vector logo and poster design, crisp geometric forms, polished brand identity, "
                "clean negative space, strong visual hierarchy, production-quality finish"
            ),
            "lighting": "soft cyan rim light, subtle graphite studio glow, controlled contrast with no harsh glare",
            "photo": "sharp focus, high resolution, readable details, crisp edges, no blur, no watermark",
            "medium": "vector-style digital graphic design rendered with subtle dimensional depth",
            "color_palette": ["#070B18", "#0B1020", "#22D3EE", "#67E8F9", "#94A3B8", "#F8FAFC"],
        },
        "compositional_deconstruction": {
            "background": (
                "dark graphite and midnight-blue background with a subtle radial gradient, faint technical grid lines, "
                "soft cyan glow behind the focal subject, and clean empty margins"
            ),
            "elements": [
                {
                    "type": "obj",
                    "bbox": [120, 120, 904, 360],
                    "desc": "subtle luminous header panel and framing shape that anchors the design without covering the subject",
                    "color_palette": ["#0B1020", "#22D3EE", "#334155"],
                },
                {
                    "type": "obj",
                    "bbox": [170, 260, 854, 720],
                    "desc": subject,
                    "color_palette": ["#22D3EE", "#67E8F9", "#F8FAFC", "#64748B"],
                },
                {
                    "type": "obj",
                    "bbox": [220, 650, 804, 830],
                    "desc": text_detail,
                    "color_palette": ["#F8FAFC", "#22D3EE", "#94A3B8"],
                },
                {
                    "type": "obj",
                    "bbox": [160, 830, 864, 950],
                    "desc": "small polished footer accents, thin cyan lines, balanced spacing, professional presentation details",
                    "color_palette": ["#22D3EE", "#334155", "#F8FAFC"],
                }
            ],
        },
    }, separators=(",", ":"))


def _image_studio_caption_section(value, scalar_key, list_key=""):
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (list, tuple)) and list_key:
        return {str(list_key): list(value)}
    text = str(value or "").strip()
    return {str(scalar_key): text} if text else {}


def _image_studio_ideogram_candidate_grid_caption(prompt, identity=""):
    base_caption = _image_studio_craft_ideogram_caption(prompt)
    try:
        base = json.loads(base_caption)
    except Exception:
        base = json.loads(_image_studio_min_ideogram_caption(prompt))
    identity = str(identity or "").strip()
    subject = str(base.get("high_level_description") or prompt or "").strip()
    style = _image_studio_caption_section(
        base.get("style_description"),
        "aesthetics",
    )
    composition = _image_studio_caption_section(
        base.get("compositional_deconstruction"),
        "background",
        "elements",
    )
    palette = style.get("color_palette")
    if isinstance(palette, str):
        palette = [
            value.strip()
            for value in re.split(r"[,;]", palette)
            if value.strip()
        ]
    elif isinstance(palette, (list, tuple)):
        palette = [str(value).strip() for value in palette if str(value).strip()]
    else:
        palette = []
    if not palette:
        palette = ["#17130F", "#4A3828", "#9A7B59", "#D8C3A5", "#F1E5D2"]
    style["color_palette"] = palette
    boxes = [
        [16, 16, 496, 496],
        [528, 16, 1008, 496],
        [16, 528, 496, 1008],
        [528, 528, 1008, 1008],
    ]
    portrait_request = bool(re.search(
        r"\b(?:portrait|headshot|face|person|figure|photograph|photo|painting|likeness)\b",
        f"{prompt} {subject}",
        re.I,
    ))
    variations = (
        [
            "front-facing portrait candidate with the clearest face, formal posture, direct gaze, and balanced archival framing",
            "three-quarter portrait candidate with a different head angle, different body posture, side-lit facial planes, and a tighter asymmetric crop",
            "environmental portrait candidate with a meaningfully different room, landscape, props, clothing emphasis, depth cues, and contextual storytelling",
            "action-oriented portrait candidate with a different gaze direction, hand/arm pose, foreground detail, camera height, and dramatic focal hierarchy",
        ]
        if portrait_request
        else [
            "primary faithful candidate with the clearest focal subject, balanced composition, and readable visual hierarchy",
            "alternate viewpoint candidate with a substantially different camera angle, spatial arrangement, subject scale, and lighting emphasis",
            "environmental candidate with a distinct setting, time of day, scenery, supporting details, and stronger contextual storytelling",
            "detail/action candidate with a different crop, foreground emphasis, movement, pose or object arrangement, and visual rhythm",
        ]
    )
    elements = []
    for index, variation in enumerate(variations):
        elements.append({
            "type": "obj",
            "bbox": boxes[index],
            "desc": (
                f"Candidate {index + 1} for this exact request: {subject}. {variation}. "
                + (
                    f"The subject must remain immediately recognizable specifically as {identity}, matching "
                    f"{identity}'s public-reference likeness when applicable, distinctive structure, age, styling, "
                    "and contextual attributes from the request. "
                    if identity
                    else ""
                )
                + "Preserve every requested object, readable text requirement, palette, style, and safety-neutral context."
                + " Keep this candidate visually distinct from the other three through at least three simultaneous major changes: "
                "pose or object arrangement, camera angle, subject scale, setting/scenery, crop, lighting, color emphasis, "
                "foreground/background depth, and action or mood while still depicting the same requested subject."
            ),
            "color_palette": palette,
        })
    return json.dumps({
        "high_level_description": (
            "A clean 2x2 contact sheet containing exactly four complete candidate renderings of the same requested image, "
            "arranged as exactly two columns by exactly two rows, one candidate per quadrant, no more and no fewer. "
            "Never create a 4x2, 2x4, 3x3, eight-panel, storyboard, or thumbnail grid. "
            f"Original request: {subject}. "
            "Each quadrant is an independent edge-to-edge candidate; do not draw panel labels, separator text, "
            "contact-sheet captions, borders, nested grids, repeated sub-panels, or extra internal dividers."
        ),
        "style_description": style,
        "compositional_deconstruction": {
            "background": (
                "Four isolated equal-size square quadrants only. Each repeats the complete requested scene using the original "
                f"background direction: {composition.get('background') or 'faithful to the request'}."
            ),
            "elements": elements,
        },
    }, separators=(",", ":"))


def _image_studio_coerce_ideogram_caption(text, fallback_text):
    value = str(text or "").strip()
    if value.startswith("```"):
        value = value.strip("`").strip()
        if value[:4].lower() == "json":
            value = value[4:].strip()
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict) and parsed.get("high_level_description"):
            return json.dumps(parsed, separators=(",", ":"))
    except Exception:
        pass
    return _image_studio_min_ideogram_caption(fallback_text)


def _image_studio_craft_ideogram_caption(prompt):
    _image_studio_ensure_director_runtime("caption")
    fallback = _image_studio_min_ideogram_caption(prompt)
    payload = {
        "model": IMAGE_STUDIO_DIRECTOR_MODEL,
        "messages": [
            {"role": "system", "content": IMAGE_STUDIO_DIRECTOR_IMG_SYS},
            {"role": "user", "content": str(prompt or "")},
        ],
        "max_tokens": 700,
        "temperature": 0.7,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    for _ in range(3):
        try:
            request = urllib.request.Request(
                "http://127.0.0.1:8090/v1/chat/completions",
                data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.load(response)
            message = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            caption = _image_studio_coerce_ideogram_caption(message, prompt)
            if caption != fallback:
                return caption
        except Exception:
            time.sleep(1)
    return fallback


def _image_studio_director_message(system_prompt, user_prompt, max_tokens=500, temperature=0.4, include_metrics=False):
    _image_studio_ensure_director_runtime("planning")
    try:
        timeout_seconds = max(120, min(360, 90 + int(max_tokens or 500) // 16))
    except Exception:
        timeout_seconds = 120
    payload = {
        "model": IMAGE_STUDIO_DIRECTOR_MODEL,
        "messages": [
            {"role": "system", "content": str(system_prompt or "")},
            {"role": "user", "content": str(user_prompt or "")},
        ],
        "max_tokens": int(max_tokens or 500),
        "temperature": float(temperature or 0.4),
        "chat_template_kwargs": {"enable_thinking": False},
    }
    request = urllib.request.Request(
        "http://127.0.0.1:8090/v1/chat/completions",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started_at = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        data = json.load(response)
    elapsed = max(0.001, time.monotonic() - started_at)
    message = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not include_metrics:
        return message
    usage = dict(data.get("usage") or {})
    input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    if output_tokens <= 0 and message:
        output_tokens = max(1, len(message) // 4)
    total_tokens = int(usage.get("total_tokens") or usage.get("tokens") or 0)
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens
    return message, {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "latency_s": round(elapsed, 3),
        "generation_tps": round(output_tokens / elapsed, 2) if output_tokens > 0 else None,
    }


def _image_studio_parse_json_object(text):
    value = str(text or "").strip()
    if value.startswith("```"):
        value = value.strip("`").strip()
        if value[:4].lower() == "json":
            value = value[4:].strip()
    object_start = value.find("{")
    if object_start >= 0:
        value = value[object_start:]
    parsed, _end = json.JSONDecoder().raw_decode(value)
    if not isinstance(parsed, dict):
        raise ValueError("Planner returned a non-object JSON value.")
    return parsed


def _image_studio_ready_lanes():
    return {
        lane: not bool(_image_studio_optional_models_ready(lane))
        for lane in IMAGE_STUDIO_LANES
    }


def _image_studio_first_ready(candidates, ready):
    for lane in candidates:
        if ready.get(lane):
            return lane
    return ""


def _image_studio_image_lane_order(request_text):
    value = str(request_text or "").lower()
    if re.search(r"\bz[-\s]?image|fast\s+uncensored\b", value):
        return ["zimage", "chroma", "krea", "ideogram", "hidream"]
    if re.search(r"\bkrea|aesthetic|stylized|stylised\b", value):
        return ["krea", "ideogram", "hidream", "zimage", "chroma"]
    if re.search(r"\buncensored|unrestricted|nsfw\b", value):
        return ["zimage", "chroma", "krea", "ideogram", "hidream"]
    if re.search(r"\bphotoreal|highest\s+quality|top[-\s]?quality|hidream\b", value):
        return ["hidream", "ideogram", "krea", "zimage", "chroma"]
    return ["ideogram", "zimage", "krea", "hidream", "chroma"]


def _image_studio_speech_lane_order(request_text):
    preferred = _image_studio_speech_lane_preference(request_text)
    order = []
    for lane in (preferred, "kokoro", "voice"):
        if lane and lane not in order:
            order.append(lane)
    return order


def _image_studio_heuristic_plan(prompt, attachments, ready):
    text = str(prompt or "").strip()
    lowered = text.lower()
    if re.search(r"\b10\s*eros|10eros\b", lowered):
        video_lanes = ["10eros", "sulphur", "wan", "ltx"]
    elif re.search(r"\bwan(?:2\.2)?\b", lowered):
        video_lanes = ["wan", "ltx", "sulphur", "10eros"]
    elif re.search(r"\bsulphur|sulfur\b", lowered):
        video_lanes = ["sulphur", "10eros", "wan", "ltx"]
    else:
        video_lanes = ["ltx", "wan", "sulphur", "10eros"]
    image_lanes = _image_studio_image_lane_order(lowered)
    speech_lanes = _image_studio_speech_lane_order(lowered)
    kinds = {str((row or {}).get("kind") or "").lower() for row in (attachments or [])}
    if "image" in kinds:
        lane = _image_studio_first_ready(video_lanes, ready)
        if lane:
            return {"action": "generate", "lane": lane, "prompt": text, "rationale": "Image attachment implies image-to-video animation."}
    if "audio" in kinds:
        lane = _image_studio_first_ready(["voice", "kokoro"], ready)
        if lane:
            return {"action": "generate", "lane": lane, "prompt": text, "rationale": "Audio attachment implies voice/reference speech work."}
    wants_text_source = re.search(r"\b(list|table|catalog|every|all|each|paragraph|script|structured|records?)\b", lowered)
    wants_image = re.search(r"\b(image|picture|photo|photograph|portrait|poster|logo|design|illustration|draw|render)\b", lowered)
    wants_speech = re.search(r"\b(audio|speech|voiceover|narrat\w*|read|tts|speak)\b", lowered)
    wants_video = re.search(r"\b(video|clip|film|cinematic|animate|animation|camera|shot|scene)\b", lowered)
    if wants_text_source and sum(bool(item) for item in (wants_image, wants_speech, wants_video)) >= 2:
        steps = [{
            "lane": "text",
            "prompt": (
                "Generate only a strict JSON array of source objects for the user's full request. "
                "Include every requested item in the requested order, preserving duplicates or separate editions "
                "when the request implies them. Each object must include name, dates when applicable, text, "
                "image_prompt when image generation is requested, and speech_text when speech generation is requested."
            ),
            "purpose": "Create the structured source records for dependent media steps.",
        }]
        speech_lane = _image_studio_first_ready(speech_lanes, ready) if wants_speech else ""
        if speech_lane:
            steps.append({
                "lane": speech_lane,
                "prompt": "{{speech_text}}",
                "purpose": "Generate one speech clip for each source object.",
                "batch": {"source_step": 1, "items": "all objects from step 1", "count": 0, "strategy": "sequential"},
                "depends_on": [1],
            })
        if wants_image and _image_studio_first_ready(image_lanes, ready):
            steps.append({
                "lane": _image_studio_first_ready(image_lanes, ready),
                "prompt": "{{image_prompt}}",
                "purpose": "Generate one image for each source object.",
                "batch": {"source_step": 1, "items": "all objects from step 1", "count": 0, "strategy": "sequential"},
                "depends_on": [1],
            })
        if wants_video and _image_studio_first_ready(video_lanes, ready):
            steps.append({
                "lane": _image_studio_first_ready(video_lanes, ready),
                "prompt": text,
                "purpose": "Generate the requested summary video.",
                "depends_on": [1],
            })
        if len(steps) > 1:
            return {
                "action": "generate",
                "rationale": "Fallback produced a structured multi-step media plan from the request.",
                "steps": steps,
            }
    if re.search(r"\b(video|clip|film|cinematic|animate|animation|camera|shot|scene)\b", lowered):
        lane = _image_studio_first_ready(video_lanes, ready)
        if lane:
            return {"action": "generate", "lane": lane, "prompt": text, "rationale": "Video language matched an installed video lane."}
    if re.search(r"\b(song|music|beat|instrumental|melody|chorus|verse|synth|guitar|drum|soundtrack|score)\b", lowered):
        lane = _image_studio_first_ready(["music"], ready)
        if lane:
            return {"action": "generate", "lane": lane, "prompt": text, "rationale": "Music language matched ACE-Step."}
    if re.search(r"\b(sound effect|sfx|foley|ambience|ambient|chime|whoosh|impact|rain|thunder|noise|texture)\b", lowered):
        lane = _image_studio_first_ready(["sfx"], ready)
        if lane:
            return {"action": "generate", "lane": lane, "prompt": text, "rationale": "Sound-effect language matched Stable Audio."}
    if re.search(r"\b(say|speak|voiceover|narrat\w*|read this|tts|speech)\b", lowered):
        lane = _image_studio_first_ready(speech_lanes, ready)
        if lane:
            return {"action": "generate", "lane": lane, "prompt": text, "rationale": "Speech language matched an installed voice lane."}
    if re.search(r"\b(image|picture|photo|poster|logo|design|illustration|draw|render|typography|badge|icon)\b", lowered):
        lane = _image_studio_first_ready(image_lanes, ready)
        if lane:
            return {"action": "generate", "lane": lane, "prompt": text, "rationale": "Image/design language matched an installed image lane."}
    return {
        "action": "chat",
        "lane": "",
        "prompt": "Tell me what you want to create: an image, sound, song, speech clip, or video.",
        "rationale": "The message was not specific enough to route to a generation lane.",
    }


def _image_studio_no_media_direct_plan(prompt):
    if not _image_studio_request_forbids_media(prompt):
        return None
    text = str(prompt or "").strip()
    lowered = text.lower()
    name_match = re.search(r"\bnamed\s+([A-Z][A-Za-z0-9 -]{1,60})(?:[.;,\n]|$)", text)
    run_name = re.sub(r"\s+", " ", name_match.group(1)).strip() if name_match else "the dry run"
    count_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
    count_token = r"(\d{1,2}|one|two|three|four|five|six)"

    def requested_count(pattern):
        match = re.search(pattern, lowered)
        if not match:
            return 0
        raw = match.group(1)
        value = int(raw) if raw.isdigit() else count_words.get(raw, 0)
        return max(1, min(6, value)) if value else 0

    step_count = requested_count(rf"\b(?:exactly\s+)?{count_token}\s+(?:concise\s+)?(?:numbered\s+)?steps?\b")
    bullet_count = requested_count(rf"\b(?:exactly\s+)?{count_token}\s+(?:concise\s+)?(?:confirmation\s+)?bullets?\b")
    if bullet_count:
        lines = [
            f"- {run_name} is confirmed as a text-only dry run.",
            "- No image, audio, video, download, file, or external tool lane is required.",
            "- The request can complete without loading additional media models.",
            "- The final response remains deterministic and does not call Studio generators.",
            "- The active chat interface can stay in no-media mode.",
            "- Resource allocation can remain unchanged.",
        ][:bullet_count]
    else:
        count = step_count or 2
        lines = [
            f"1. Treat {run_name} as a text-only dry run and keep all AI Studio media lanes idle.",
            "2. Return the requested confirmation without generating images, audio, video, downloads, files, or external-tool calls.",
            "3. Preserve the current loaded runtime state unless a later real generation request requires a change.",
            "4. Mark the dry run complete using deterministic UI text.",
            "5. Avoid loading large models for non-generative completion copy.",
            "6. Leave media resources available for the next real Studio request.",
        ][:count]
    response = "\n".join(lines)
    return {
        "action": "chat",
        "title": "Text-only dry run",
        "lane": "",
        "label": "Chat response",
        "prompt": response,
        "response": response,
        "rationale": "Explicit no-media request; no Studio media lane or Director planning pass is required.",
        "steps": [],
        "ready_lanes": [],
        "generation_metrics": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "latency_s": 0,
            "generation_tps": None,
            "director_skipped": True,
        },
    }


def _image_studio_clone_plan_steps(plan):
    steps = (plan or {}).get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list):
        return []
    cloned = []
    for step in steps:
        if isinstance(step, dict):
            cloned.append(json.loads(json.dumps(step)))
    return cloned


def _image_studio_repair_revision_plan(prompt, original_request, previous_plan, candidate_plan):
    latest = str(prompt or "")
    lowered = latest.lower()
    previous_steps = _image_studio_clone_plan_steps(previous_plan)
    candidate_steps = _image_studio_clone_plan_steps(candidate_plan)
    exact_steps_match = re.search(r"\bexactly\s+(\d{1,2})\s+steps?\b", lowered)
    exact_step_count = int(exact_steps_match.group(1)) if exact_steps_match else 0
    object_count_match = re.search(r"\bexactly\s+(\d{1,4})\s+(?:objects?|items?|entries|artifacts?)\b", lowered)
    object_count = int(object_count_match.group(1)) if object_count_match else 0
    field_match = re.search(
        r"\bfields?\s*:?\s*([a-zA-Z0-9_,\s-]+?)(?:\.|\n|$)",
        latest,
        re.I,
    )
    field_list = ""
    if field_match:
        raw_fields = [
            re.sub(r"[^a-zA-Z0-9_]", "", item).strip()
            for item in re.split(r",|\band\b", field_match.group(1))
        ]
        field_list = ", ".join(item for item in raw_fields if item)
    placeholders = set(re.findall(r"\{\{([a-zA-Z0-9_]+)\}\}", latest))
    exact_seconds_match = re.search(r"\bexactly\s+(\d{1,4})\s*seconds?\b", lowered)
    exact_seconds = int(exact_seconds_match.group(1)) if exact_seconds_match else 0
    candidate_text = json.dumps(candidate_plan or {}, sort_keys=True)
    candidate_step_prompts = [
        (
            str((step or {}).get("lane") or "").strip().lower(),
            str((step or {}).get("prompt") or ""),
        )
        for step in candidate_steps
    ]
    violates_explicit_constraints = bool(
        exact_step_count and len(candidate_steps) != exact_step_count
    )
    if object_count and str(object_count) not in candidate_text:
        violates_explicit_constraints = True
    if "speech_text" in placeholders and not any(
        lane in {"kokoro", "voice"} and "{{speech_text}}" in step_prompt
        for lane, step_prompt in candidate_step_prompts
    ):
        violates_explicit_constraints = True
    if "image_prompt" in placeholders and not any(
        lane in IMAGE_STUDIO_IMAGE_LANES and "{{image_prompt}}" in step_prompt
        for lane, step_prompt in candidate_step_prompts
    ):
        violates_explicit_constraints = True
    for placeholder in placeholders - {"speech_text", "image_prompt"}:
        if "{{" + placeholder + "}}" not in candidate_text:
            violates_explicit_constraints = True
            break
    if exact_seconds and not re.search(rf"\b{exact_seconds}\s*seconds?\b", candidate_text, re.I):
        violates_explicit_constraints = True
    if exact_seconds and not any(
        lane in IMAGE_STUDIO_VIDEO_LANES
        and re.search(rf"\bexactly\s+{exact_seconds}\s*seconds?\b", step_prompt, re.I)
        for lane, step_prompt in candidate_step_prompts
    ):
        violates_explicit_constraints = True
    if not (previous_steps and exact_step_count and violates_explicit_constraints):
        return None
    steps = previous_steps[:exact_step_count]
    if len(steps) != exact_step_count:
        return None
    revision_note = latest.strip()
    for index, step in enumerate(steps):
        lane = str(step.get("lane") or "").strip().lower()
        prompt_text = str(step.get("prompt") or "").strip()
        if lane == "text":
            additions = []
            if object_count:
                additions.append(f"Output exactly {object_count} objects/items.")
            if field_list:
                additions.append(f"Each object/item must include exactly these fields: {field_list}.")
            if placeholders:
                additions.append(
                    "Include stable fields required by downstream prompt templates: "
                    + ", ".join(sorted(placeholders))
                    + "."
                )
            additions.append("Apply these latest revision constraints without narrowing the original request: " + revision_note)
            step["prompt"] = " ".join(part for part in [prompt_text, *additions] if part).strip()
        elif lane in {"kokoro", "voice"} and "speech_text" in placeholders:
            step["prompt"] = "{{speech_text}}"
        elif lane in IMAGE_STUDIO_IMAGE_LANES and "image_prompt" in placeholders:
            step["prompt"] = "{{image_prompt}}"
        elif lane in IMAGE_STUDIO_VIDEO_LANES and exact_seconds:
            if not re.search(r"\bexactly\s+\d{1,4}\s*seconds?\b", prompt_text, re.I):
                step["prompt"] = f"{prompt_text} Generate exactly {exact_seconds} seconds."
        batch = step.get("batch") if isinstance(step.get("batch"), dict) else None
        if batch and object_count and index > 0:
            batch["count"] = object_count
            batch.setdefault("strategy", "sequential")
            step["batch"] = batch
    return {
        "action": "generate",
        "rationale": (
            "Repaired the prior multi-step plan using the latest explicit revision constraints "
            "instead of accepting a collapsed candidate plan."
        ),
        "steps": steps,
        "original_request": str(original_request or (previous_plan or {}).get("original_request") or prompt or ""),
    }


def _image_studio_explicit_seconds(text):
    value = str(text or "").lower()
    minute_match = re.search(r"\b(\d{1,4}(?:\.\d+)?)\s*[- ]?\s*(?:minutes?|mins?|min)\b", value)
    if minute_match:
        return max(1, int(round(float(minute_match.group(1)) * 60.0)))
    second_match = re.search(r"\b(\d{1,4}(?:\.\d+)?)\s*[- ]?\s*(?:seconds?|secs?|sec|s)\b", value)
    if second_match:
        return max(1, int(round(float(second_match.group(1)))))
    return 0


def _image_studio_explicit_video_seconds(text):
    value = str(text or "").lower()
    number = r"(\d{1,4}(?:\.\d+)?)"
    duration = r"(?:seconds?|secs?|sec|s)"
    video = r"(?:ltx|sulphur|10eros|wan|video|clip|film|teaser|montage|animation)"
    patterns = (
        rf"\b{number}\s*[- ]?\s*{duration}\s+{video}\b",
        rf"\b{number}\s*[- ]?\s*{duration}\s+(?:\w+\s+){{0,8}}{video}\b",
        rf"\b{video}[^.\n;]{{0,120}}?\b{number}\s*[- ]?\s*{duration}\b",
    )
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return max(1, int(round(float(match.group(1)))))
    return 0


def _image_studio_count_word(value):
    token = str(value or "").strip().lower()
    words = {
        "a": 1,
        "an": 1,
        "one": 1,
        "single": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
    }
    if token in words:
        return words[token]
    try:
        return int(token)
    except Exception:
        return 0


def _image_studio_requested_artifact_count(text, lane):
    value = str(text or "").lower()
    lane = str(lane or "").strip().lower()
    number = r"(?:\d{1,3}|a|an|one|single|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    source_unit = r"(?:scenes?|source\s+objects?|source\s+items?|objects?|items?|entries|records?|sections?|rows?)"
    scene_match = re.search(rf"\b({number})[-\s]+scenes?\b", value)
    scene_count = _image_studio_count_word(scene_match.group(1)) if scene_match else 0
    source_match = re.search(rf"\b({number})[-\s]+(?:structured\s+)?{source_unit}\b", value)
    source_count = _image_studio_count_word(source_match.group(1)) if source_match else scene_count
    if lane in {"kokoro", "voice"}:
        nouns = r"(?:kokoro\s+)?(?:voiceovers?|narrations?|speech(?:\s+clips?)?|audio(?:\s+clips?)?|tts(?:\s+clips?)?)"
    elif lane in IMAGE_STUDIO_IMAGE_LANES:
        nouns = r"(?:logos?|images?|pictures?|photos?|photographs?|portraits?|illustrations?|renders?)"
    elif lane in {"music"}:
        nouns = r"(?:music(?:\s+beds?|\s+tracks?)?|instrumentals?|instrumental\s+scores?|scores?|songs?|tracks?|soundtracks?|cues?)"
    elif lane in {"sfx"}:
        nouns = r"(?:sfx(?:\s+beds?|\s+cues?)?|sound\s+effects?|sound\s+cues?|foley|ambien(?:ce|t)(?:\s+beds?)?|audio\s+beds?|chimes?)"
    elif lane in IMAGE_STUDIO_VIDEO_LANES:
        nouns = r"(?:(?:ltx|sulphur|sulfur|10eros|wan)\s+)?(?:videos?|clips?|films?|teasers?|montages?|animations?)"
    else:
        return 0
    per_scene = re.search(rf"\b({number})\s+{nouns}\s+(?:for|per)\s+scene\b", value)
    if per_scene and scene_count:
        per_count = max(1, _image_studio_count_word(per_scene.group(1)))
        return per_count * scene_count
    per_source = re.search(
        rf"\b({number})\s+(?:(?:[a-z0-9-]+)\s+){{0,8}}{nouns}\s+(?:for|per)\s+(?:each|every|the\s+)?{source_unit}\b",
        value,
    )
    if per_source and source_count:
        per_count = max(1, _image_studio_count_word(per_source.group(1)))
        return per_count * source_count
    if source_count and _image_studio_lane_source_batch_requested(value, lane):
        return source_count
    explicit = re.search(rf"\b({number})\s+(?:(?:[a-z0-9-]+)\s+){{0,10}}{nouns}\b", value)
    if explicit:
        return max(1, _image_studio_count_word(explicit.group(1)))
    return 0


def _image_studio_lane_source_batch_requested(text, lane):
    value = str(text or "").lower()
    lane = str(lane or "").strip().lower()
    if lane in {"kokoro", "voice"}:
        nouns = r"(?:kokoro\s+)?(?:voiceovers?|narrations?|speech(?:\s+clips?)?|audio(?:\s+clips?)?|tts(?:\s+clips?)?)"
    elif lane in IMAGE_STUDIO_IMAGE_LANES:
        nouns = r"(?:logos?|images?|pictures?|photos?|photographs?|portraits?|illustrations?|renders?|visuals?)"
    elif lane in {"music"}:
        nouns = r"(?:music(?:\s+beds?|\s+tracks?)?|instrumentals?|instrumental\s+scores?|scores?|songs?|tracks?|soundtracks?|cues?)"
    elif lane in {"sfx"}:
        nouns = r"(?:sfx(?:\s+beds?|\s+cues?)?|sound\s+effects?|sound\s+cues?|foley|ambien(?:ce|t)(?:\s+beds?)?|audio\s+beds?|chimes?)"
    elif lane in IMAGE_STUDIO_VIDEO_LANES:
        nouns = r"(?:(?:ltx|sulphur|sulfur|10eros|wan)\s+)?(?:videos?|clips?|films?|teasers?|montages?|animations?)"
    else:
        return False
    source_unit = r"(?:scenes?|source\s+objects?|source\s+items?|objects?|items?|entries|records?|sections?|rows?)"
    each_source = rf"(?:each|every)(?:\s+of\s+the)?(?:\s+(?:\d{{1,3}}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve))?\s+{source_unit}"
    patterns = (
        rf"\b(?:(?:one|a|an|single|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d{{1,3}})\s+)?(?:(?:[a-z0-9-]+)\s+){{0,8}}{nouns}\s+(?:for|per)\s+(?:{each_source}|{source_unit})\b",
        rf"\b(?:generate|create|produce|make)\s+(?:(?:[a-z0-9-]+)\s+){{0,8}}{nouns}\s+(?:for|per)\s+{each_source}\b",
        rf"\b{each_source}\s+(?:gets?|needs?|requires?|has|includes?|receives?|with)\s+(?:(?:[a-z0-9-]+)\s+){{0,8}}{nouns}\b",
        rf"\b(?:one|a|an|single)\s+(?:(?:[a-z0-9-]+)\s+){{0,8}}{nouns}\s+per\s+(?:scene|object|item|entry|record|section|row)\b",
    )
    return any(re.search(pattern, value) for pattern in patterns)


def _image_studio_batch_can_repeat_for_lane(step, lane, request_text):
    lane = str(lane or "").strip().lower()
    if lane in {"kokoro", "voice"} or lane in IMAGE_STUDIO_IMAGE_LANES:
        return True
    if lane not in {"music", "sfx"} and lane not in IMAGE_STUDIO_VIDEO_LANES:
        return False
    if _image_studio_lane_source_batch_requested(request_text, lane):
        return True
    prompt_context = " ".join(
        str((step or {}).get(key) or "")
        for key in ("purpose", "prompt")
    ).lower()
    if re.search(r"\b(?:one|single|exactly\s+one)\b", str(request_text or "").lower()) and not _image_studio_lane_source_batch_requested(str(request_text or ""), lane):
        return False
    return "{{" in prompt_context and "}}" in prompt_context


def _image_studio_single_artifact_phrase(request_text, lane):
    value = str(request_text or "").lower()
    lane = str(lane or "").strip().lower()
    if lane == "music":
        nouns = r"(?:music(?:\s+beds?|\s+tracks?)?|instrumentals?|instrumental\s+scores?|scores?|songs?|tracks?|soundtracks?|cues?)"
    elif lane == "sfx":
        nouns = r"(?:sfx(?:\s+beds?|\s+cues?)?|sound\s+effects?|sound\s+cues?|foley|ambien(?:ce|t)(?:\s+beds?)?|audio\s+beds?|chimes?)"
    elif lane in IMAGE_STUDIO_VIDEO_LANES:
        nouns = r"(?:(?:ltx|sulphur|sulfur|10eros|wan)\s+)?(?:videos?|clips?|films?|teasers?|montages?|animations?)"
    else:
        return ""
    match = re.search(
        rf"\b((?:exactly\s+)?(?:one|single|1)\s+(?:(?:[a-z0-9-]+)\s+){{0,10}}{nouns}(?:\s+of\s+exactly\s+\d{{1,4}}\s*seconds?|\s+exactly\s+\d{{1,4}}\s*seconds?)?)\b",
        value,
        re.I,
    )
    if not match:
        return ""
    phrase = re.sub(r"\s+", " ", match.group(1)).strip()
    return phrase


def _image_studio_global_media_prompt(prompt, lane, request_text):
    lane = str(lane or "").strip().lower()
    text = _image_studio_sanitize_media_step_prompt(prompt)
    text = re.sub(
        r"\s*\b(?:repeat|run)\s+(?:this\s+)?(?:generation|step|prompt|output)?[^.]{0,100}?\b(?:times|per\s+(?:scene|item|record|entry)|for\s+each)[^.]*\.",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\s+\b(?:for|per)\s+(?:each|every)(?:\s+of\s+the)?(?:\s+(?:\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve))?\s+(?:scenes?|objects?|items?|records?|entries|sections|rows)\b",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text).strip()
    single_phrase = _image_studio_single_artifact_phrase(request_text, lane)
    if single_phrase:
        prefix = "Generate " if single_phrase.startswith("exactly ") else "Generate exactly "
        text = f"{prefix}{single_phrase} for the full requested plan context."
    if lane in IMAGE_STUDIO_VIDEO_LANES:
        seconds = (
            _image_studio_explicit_seconds(text)
            or _image_studio_explicit_video_seconds(request_text)
            or _image_studio_explicit_seconds(request_text)
        )
        correction = "Create exactly one final video total using the full plan context; do not create separate scene, item, record, or variation outputs."
        if seconds and not re.search(r"\bexactly\s+\d{1,4}\s*seconds?\b", text, re.I):
            correction = f"Create exactly one final video total of exactly {seconds} seconds using the full plan context; do not create separate scene, item, record, or variation outputs."
    elif lane == "music":
        correction = "Create exactly one music bed or score total using the full plan context; do not create separate scene, item, record, or variation outputs."
    elif lane == "sfx":
        correction = "Create exactly one SFX or ambience bed total using the full plan context; do not create separate scene, item, record, or variation outputs."
    else:
        correction = "Create exactly one media output total using the full plan context; do not create separate scene, item, record, or variation outputs."
    if correction.lower() not in text.lower():
        text = f"{text} {correction}".strip()
    return text


def _image_studio_sanitize_media_step_prompt(prompt):
    text = str(prompt or "").strip()
    if not text:
        return text
    patterns = (
        r"\s*(?:Output|Generate|Return)\s+ONLY\s+(?:one\s+complete\s+)?(?:a\s+)?(?:strict\s+)?JSON\s+array[^.]*\.",
        r"\s*Each object must include[^.]*\.",
        r"\s*Use these exact field names[^.]*\.",
        r"\s*Do not include literal \{\{\.\.\.\}\} template placeholders[^.]*\.",
        r"\s*Do not include other fields[^.]*\.",
    )
    for pattern in patterns:
        text = re.sub(pattern, " ", text, flags=re.I)
    text = re.sub(r"\s*(?:Output|Generate|Return)\s+ONLY\s+.*$", "", text, flags=re.I)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return text.strip()


def _image_studio_sanitize_source_count_prompt(prompt, expected_count=0):
    text = str(prompt or "").strip()
    if not text:
        return text
    patterns = (
        r"\s*(?:The\s+)?array\s+must\s+contain\s+exactly\s+\d{1,4}\s+(?:top[-\s]+level\s+)?(?:objects?|items?)[^.]*\.",
        r"\s*(?:Output|Return)\s+exactly\s+\d{1,4}\s+(?:top[-\s]+level\s+)?(?:objects?|items?)[^.]*\.",
        r"\s*(?:Output|Return)\s+ONLY\s+(?:one\s+complete\s+)?(?:a\s+)?(?:strict\s+)?JSON\s+array\s+of\s+exactly\s+\d{1,4}\s+(?:objects?|items?)[^.]*\.",
    )
    for pattern in patterns:
        text = re.sub(pattern, " ", text, flags=re.I)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return text.strip()


def _image_studio_ideogram_single_render_requested(prompt, options=None):
    opts = options if isinstance(options, dict) else {}
    single_value = str(opts.get("single_image") or "").strip().lower()
    no_grid_value = str(opts.get("no_candidate_grid") or "").strip().lower()
    candidate_grid_value = opts.get("candidate_grid")
    candidate_grid_text = str(candidate_grid_value).strip().lower()
    if opts.get("single_image") is True or single_value in {"1", "true", "yes", "on"}:
        return True
    if opts.get("no_candidate_grid") is True or no_grid_value in {"1", "true", "yes", "on"}:
        return True
    if candidate_grid_value is False or candidate_grid_text in {"0", "false", "no", "off"}:
        return True
    if candidate_grid_value is True or candidate_grid_text in {"1", "true", "yes", "on"}:
        return False
    value = str(prompt or "").lower()
    return bool(
        re.search(r"\b(?:single|one)\s+(?:final\s+)?(?:image|render|picture|photo|photograph|poster|logo|illustration)\b", value)
        or re.search(r"\b(?:exactly\s+)?(?:one|single|1)\s+(?:(?:[a-z0-9-]+)\s+){0,6}(?:image|render|picture|photo|photograph|poster|logo|illustration)\b", value)
        or re.search(r"\b(?:no|not|without)\s+(?:a\s+)?(?:grid|contact\s+sheet|candidate\s+sheet|2x2|two[-\s]+by[-\s]+two|four[-\s]+panel)\b", value)
        or re.search(r"\b(?:high[-\s]+resolution|high[-\s]+quality|hi[-\s]*res|full[-\s]+resolution)\b", value)
        or re.search(r"\b(?:1080p|1440p|2160p|4k|8k|uhd|qhd|hd)\b", value)
        or re.search(r"\b\d{3,5}\s*[x×]\s*\d{3,5}\b", value)
    )


def _image_studio_plan_source_requirements(steps, original_request, latest_prompt):
    request_text = f"{original_request or ''}\n{latest_prompt or ''}".lower()
    requirements = {}
    if not isinstance(steps, list):
        return requirements
    for index, step in enumerate(steps):
        lane = str((step or {}).get("lane") or "").strip().lower()
        batch = (step or {}).get("batch") if isinstance((step or {}).get("batch"), dict) else None
        source_step = int((batch or {}).get("source_step") or 0)
        if not source_step:
            dependencies = (step or {}).get("depends_on") or []
            source_step = int(dependencies[0]) if dependencies and isinstance(dependencies[0], (int, float)) else 1
        if lane not in IMAGE_STUDIO_IMAGE_LANES and lane not in {"kokoro", "voice"}:
            continue
        required = requirements.setdefault(source_step, set(["name"]))
        if re.search(r"\b(date|served|term|period|year|chronolog|order)\b", request_text):
            required.add("dates")
        if re.search(r"\b(paragraph|accomplishment|description|summary|script|narrat\w*|read|speech|voice|audio)\b", request_text):
            required.add("text")
        if lane in IMAGE_STUDIO_IMAGE_LANES:
            required.add("image_prompt")
        if lane in {"kokoro", "voice"}:
            required.add("speech_text")
            required.add("text")
    return requirements


def _image_studio_single_text_source_for_step(steps, step_index):
    text_sources = [
        index + 1
        for index, candidate in enumerate(steps[:step_index])
        if str((candidate or {}).get("lane") or "").strip().lower() == "text"
    ]
    return text_sources[0] if len(text_sources) == 1 else 0


def _image_studio_source_item_step(step, steps, step_index):
    lane = str((step or {}).get("lane") or "").strip().lower()
    if lane not in IMAGE_STUDIO_IMAGE_LANES and lane not in {"kokoro", "voice"}:
        return 0
    if isinstance((step or {}).get("batch"), dict):
        return 0
    dependencies = [
        int(value)
        for value in ((step or {}).get("depends_on") or [])
        if isinstance(value, (int, float)) and int(value) > 0
    ]
    for dependency in dependencies:
        if 0 < dependency <= len(steps) and str((steps[dependency - 1] or {}).get("lane") or "").strip().lower() == "text":
            return dependency
    prompt_text = " ".join(
        str((step or {}).get(key) or "")
        for key in ("purpose", "prompt")
    ).lower()
    if re.search(r"\b(previous|source|structured)\s+(?:step|data|record|records|object|objects|item|items|entry|entries)\b", prompt_text):
        return _image_studio_single_text_source_for_step(steps, step_index)
    return 0


def _image_studio_source_item_prompt(step):
    text = " ".join(
        str((step or {}).get(key) or "")
        for key in ("purpose", "prompt")
    ).lower()
    ordinal_words = (
        "first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
        "eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|"
        "eighteenth|nineteenth|twentieth"
    )
    ordinal_pattern = (
        rf"\b(?:{ordinal_words}|\d{{1,4}}(?:st|nd|rd|th)?)\s+"
        r"(?:source\s+)?(?:object|item|record|entry|scene|section|row|paragraph)\b"
    )
    return bool(
        re.search(ordinal_pattern, text)
        or re.search(r"\b(?:from|for|using)\s+(?:the\s+)?(?:previous|source|structured)\s+(?:step|data|records?|objects?|items?|entries)\b", text)
        or re.search(r"\b(?:each|every|per[- ]item|one\s+(?:image|audio|speech|voice|portrait|clip)\s+(?:for|per))\b", text)
    )


def _image_studio_batch_lane_family(lane):
    if lane in {"kokoro", "voice"}:
        return "speech"
    if lane in IMAGE_STUDIO_IMAGE_LANES:
        return "image"
    return ""


def _image_studio_allows_multiple_speech_steps(request_text):
    value = str(request_text or "").lower()
    return bool(re.search(
        r"\b(?:both|compare|comparison|side[- ]by[- ]side|multiple|several)\s+"
        r"(?:voices?|voiceovers?|narrations?|speech|tts|audio)\b"
        r"|\b(?:two|three|four)\s+(?:different\s+)?(?:voices?|voiceovers?|narrations?)\b"
        r"|\b(?:dialogue|conversation|cast|characters?)\b",
        value,
    ))


def _image_studio_speech_lane_preference(request_text):
    value = str(request_text or "").lower()
    if re.search(r"\bkokoro\b", value):
        return "kokoro"
    if re.search(r"\b(?:step[- ]?audio|editx|premium\s+voice|reference\s+voice)\b", value):
        return "voice"
    return ""


def _image_studio_speech_step_signature(step, steps, step_index):
    batch = (step or {}).get("batch") if isinstance((step or {}).get("batch"), dict) else None
    source_step = int((batch or {}).get("source_step") or 0)
    if not source_step:
        source_step = _image_studio_source_item_step(step, steps, step_index)
    prompt = re.sub(r"\s+", " ", str((step or {}).get("prompt") or "").strip().lower())
    if "{{speech_text}}" in prompt:
        prompt = "{{speech_text}}"
    return (source_step, prompt)


def _image_studio_prune_duplicate_speech_steps(steps, original_request, latest_prompt):
    if not isinstance(steps, list):
        return steps
    request_text = f"{original_request or ''}\n{latest_prompt or ''}"
    speech_indexes = [
        index
        for index, step in enumerate(steps)
        if str((step or {}).get("lane") or "").strip().lower() in {"kokoro", "voice"}
    ]
    if len(speech_indexes) <= 1 or _image_studio_allows_multiple_speech_steps(request_text):
        return steps

    requested_count = max(
        _image_studio_requested_artifact_count(request_text, "kokoro"),
        _image_studio_requested_artifact_count(request_text, "voice"),
    )
    groups = {}
    if requested_count == 1:
        groups[("single-requested-speech-output", "")] = speech_indexes
    else:
        for index in speech_indexes:
            signature = _image_studio_speech_step_signature(steps[index], steps, index)
            groups.setdefault(signature, []).append(index)
    groups = {key: indexes for key, indexes in groups.items() if len(indexes) > 1}
    if not groups:
        return steps

    preferred_lane = _image_studio_speech_lane_preference(request_text)
    duplicate_to_keep = {}
    remove_indexes = set()
    for indexes in groups.values():
        keep_index = indexes[0]
        if preferred_lane:
            keep_index = next(
                (
                    index
                    for index in indexes
                    if str((steps[index] or {}).get("lane") or "").strip().lower() == preferred_lane
                ),
                keep_index,
            )
        for index in indexes:
            if index == keep_index:
                continue
            remove_indexes.add(index)
            duplicate_to_keep[index + 1] = keep_index + 1
    if not remove_indexes:
        return steps

    pruned = []
    old_to_new = {}
    for old_index, step in enumerate(steps):
        if old_index in remove_indexes:
            continue
        pruned.append(step)
        old_to_new[old_index + 1] = len(pruned)
    for old_number, keep_number in duplicate_to_keep.items():
        if keep_number in old_to_new:
            old_to_new[old_number] = old_to_new[keep_number]

    for step in pruned:
        dependencies = []
        for value in (step.get("depends_on") or []):
            if not isinstance(value, (int, float)):
                continue
            mapped = old_to_new.get(int(value), int(value))
            if 0 < mapped <= len(pruned) and mapped not in dependencies:
                dependencies.append(mapped)
        step["depends_on"] = dependencies
        batch = step.get("batch") if isinstance(step.get("batch"), dict) else None
        if batch:
            source_step = int(batch.get("source_step") or 0)
            if source_step in old_to_new:
                batch["source_step"] = old_to_new[source_step]
                step["batch"] = batch
    return pruned


def _image_studio_collapse_indexed_source_steps(steps, original_request, latest_prompt):
    if not isinstance(steps, list):
        return steps
    groups = {}
    for index, step in enumerate(steps):
        lane = str((step or {}).get("lane") or "").strip().lower()
        family = _image_studio_batch_lane_family(lane)
        if not family or not _image_studio_source_item_prompt(step):
            continue
        source_step = _image_studio_source_item_step(step, steps, index)
        if not source_step:
            continue
        groups.setdefault((source_step, family), []).append(index)
    groups = {
        key: indexes
        for key, indexes in groups.items()
        if len(indexes) >= 2
    }
    if not groups:
        return steps

    group_for_index = {}
    group_first_index = {}
    for key, indexes in groups.items():
        group_first_index[key] = indexes[0]
        for index in indexes:
            group_for_index[index] = key

    collapsed = []
    old_to_new = {}
    for old_index, step in enumerate(steps):
        key = group_for_index.get(old_index)
        if key and group_first_index.get(key) != old_index:
            continue
        if key:
            source_step, family = key
            indexes = groups[key]
            first_step = steps[indexes[0]]
            first_lane = str((first_step or {}).get("lane") or "").strip().lower()
            placeholder = "{{speech_text}}" if family == "speech" else "{{image_prompt}}"
            purpose = (
                "Generate one speech clip for each structured source item."
                if family == "speech"
                else "Generate one image for each structured source item."
            )
            collapsed.append({
                "lane": first_lane,
                "label": str((first_step or {}).get("label") or IMAGE_STUDIO_LANES.get(first_lane, {}).get("label") or first_lane),
                "prompt": placeholder,
                "purpose": purpose,
                "batch": {
                    "source_step": source_step,
                    "items": f"all objects from step {source_step}",
                    "count": len(indexes),
                    "strategy": "sequential",
                },
                "depends_on": [source_step],
            })
            new_number = len(collapsed)
            for index in indexes:
                old_to_new[index + 1] = new_number
            continue
        cloned = json.loads(json.dumps(step))
        collapsed.append(cloned)
        old_to_new[old_index + 1] = len(collapsed)

    for step in collapsed:
        dependencies = []
        for value in (step.get("depends_on") or []):
            if not isinstance(value, (int, float)):
                continue
            mapped = old_to_new.get(int(value), int(value))
            if 0 < mapped <= len(collapsed) and mapped not in dependencies:
                dependencies.append(mapped)
        step["depends_on"] = dependencies

    image_batch_steps = [
        index + 1
        for index, step in enumerate(collapsed)
        if str((step or {}).get("lane") or "").strip().lower() in IMAGE_STUDIO_IMAGE_LANES
        and isinstance((step or {}).get("batch"), dict)
    ]
    request_text = f"{original_request or ''}\n{latest_prompt or ''}".lower()
    wants_generated_visual_refs = bool(
        image_batch_steps
        and re.search(r"\b(generated|previous|prior|source|reference|references|montage|portraits?|photos?|images?|visuals?)\b", request_text)
        and re.search(r"\b(video|clip|film|montage|animate|animation)\b", request_text)
    )
    if wants_generated_visual_refs:
        for index, step in enumerate(collapsed):
            lane = str((step or {}).get("lane") or "").strip().lower()
            if lane not in IMAGE_STUDIO_VIDEO_LANES:
                continue
            dependencies = list(step.get("depends_on") or [])
            for batch_step in image_batch_steps:
                if batch_step < index + 1 and batch_step not in dependencies:
                    dependencies.append(batch_step)
            step["depends_on"] = dependencies

    return collapsed


def _image_studio_requested_source_count(text):
    value = str(text or "").lower()
    number = r"(?:\d{1,3}|a|an|one|single|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    source_unit = r"(?:scenes?|source\s+objects?|source\s+items?|objects?|items?|entries|records?|sections?|rows?)"
    scene_match = re.search(rf"\b({number})[-\s]+scenes?\b", value)
    if scene_match:
        return _image_studio_count_word(scene_match.group(1))
    source_match = re.search(rf"\b({number})[-\s]+(?:structured\s+)?{source_unit}\b", value)
    if source_match:
        return _image_studio_count_word(source_match.group(1))
    return 0


def _image_studio_request_forbids_media(request_text):
    value = str(request_text or "").lower()
    if re.search(r"\b(?:no|non)[-\s]*media\b|\btext[-\s]*only\b|\bno[-\s]*tool(?:s)?\b|\bdry[-\s]*run\b", value):
        return True
    media_terms = (
        r"(?:media|images?|pictures?|photos?|photographs?|portraits?|illustrations?|logos?|renders?|visuals?|"
        r"audio|speech|voiceovers?|narrations?|tts|sounds?|sfx|music|songs?|videos?|clips?|films?|animations?|"
        r"downloads?|files?|external\s+tools?|tools?)"
    )
    return bool(
        re.search(rf"\b(?:do\s+not|don't|dont|never|without|avoid|skip|exclude|no)\b[^.\n;]{{0,120}}\b{media_terms}\b", value)
        or re.search(rf"\b{media_terms}\b[^.\n;]{{0,80}}\b(?:are|is)?\s*(?:not\s+)?(?:needed|required|wanted|allowed)\b", value)
    )


def _image_studio_text_only_step_prompt(prompt, request_text):
    request = re.sub(r"\s+", " ", str(request_text or "").strip())
    if len(request) > 4000:
        request = request[:4000].rstrip() + "..."
    base = str(prompt or "").strip()
    if base:
        base = re.sub(r"\{\{[^}]+\}\}", "the relevant text value", base)
        base = re.sub(r"\b(?:image_prompt|visual_prompt|speech_text)\b", "text", base, flags=re.I)
    return (
        "Fulfill this request as text only. Do not request, call, or generate images, audio, speech, "
        "video, downloads, files, external tools, media fields, or template placeholders. "
        f"User request: {request}"
    )


def _image_studio_prune_forbidden_media_steps(steps, request_text):
    if not _image_studio_request_forbids_media(request_text):
        return steps
    pruned = []
    old_to_new = {}
    for index, step in enumerate(steps if isinstance(steps, list) else []):
        if not isinstance(step, dict):
            continue
        lane = str(step.get("lane") or "").strip().lower()
        if lane and lane != "text":
            continue
        updated = dict(step)
        updated["lane"] = "text"
        updated["label"] = "Active Chat preset"
        updated["prompt"] = _image_studio_text_only_step_prompt(updated.get("prompt") or "", request_text)
        updated["purpose"] = str(updated.get("purpose") or "Produce a text-only response.").strip()
        updated["batch"] = None
        updated["depends_on"] = []
        old_to_new[index + 1] = len(pruned) + 1
        pruned.append(updated)
    if not pruned:
        pruned.append({
            "lane": "text",
            "label": "Active Chat preset",
            "prompt": _image_studio_text_only_step_prompt("", request_text),
            "purpose": "Produce a text-only response.",
            "batch": None,
            "depends_on": [],
        })
    return pruned


def _image_studio_request_needs_speech_step(request_text):
    value = str(request_text or "").lower()
    if _image_studio_request_forbids_media(value):
        return False
    return bool(
        re.search(r"\b(?:speech_text|narration_text|voiceover|voiceovers|narration|narrations|tts|text[-\s]*to[-\s]*speech|read\s+(?:the\s+)?(?:text|copy|script|paragraph|narration))\b", value)
        or _image_studio_requested_artifact_count(value, "kokoro")
        or _image_studio_requested_artifact_count(value, "voice")
        or _image_studio_lane_source_batch_requested(value, "kokoro")
        or _image_studio_lane_source_batch_requested(value, "voice")
    )


def _image_studio_request_needs_image_step(request_text):
    value = str(request_text or "").lower()
    if _image_studio_request_forbids_media(value):
        return False
    return bool(
        re.search(r"\b(?:image_prompt|visual_prompt|images?|pictures?|photos?|photographs?|portraits?|illustrations?|logos?|renders?|visuals?)\b", value)
        or _image_studio_requested_artifact_count(value, "ideogram")
        or _image_studio_lane_source_batch_requested(value, "ideogram")
    )


def _image_studio_synthesize_missing_dependent_steps(steps, original_request, latest_prompt):
    if not isinstance(steps, list):
        return steps
    request_text = f"{original_request or ''}\n{latest_prompt or ''}"
    ready_lanes = _image_studio_ready_lanes()
    text_source_step = 0
    for index, step in enumerate(steps):
        if str((step or {}).get("lane") or "").strip().lower() == "text":
            text_source_step = index + 1
            break
    if not text_source_step:
        return steps

    present_lanes = {
        str((step or {}).get("lane") or "").strip().lower()
        for step in steps
        if isinstance(step, dict)
    }
    source_count = _image_studio_requested_source_count(request_text)
    synthesized = list(steps)

    if _image_studio_request_needs_speech_step(request_text) and not (present_lanes & {"kokoro", "voice"}):
        speech_lane = _image_studio_first_ready(_image_studio_speech_lane_order(request_text), ready_lanes)
        if speech_lane:
            speech_count = (
                _image_studio_requested_artifact_count(request_text, speech_lane)
                or _image_studio_requested_artifact_count(request_text, "kokoro")
                or _image_studio_requested_artifact_count(request_text, "voice")
                or source_count
                or 1
            )
            synthesized.append({
                "lane": speech_lane,
                "label": IMAGE_STUDIO_LANES.get(speech_lane, {}).get("label") or speech_lane,
                "prompt": "{{speech_text}}",
                "purpose": "Generate one speech clip for each structured source item.",
                "batch": {
                    "source_step": text_source_step,
                    "items": f"all objects from step {text_source_step}",
                    "count": speech_count,
                    "strategy": "sequential",
                },
                "depends_on": [text_source_step],
            })
            present_lanes.add(speech_lane)

    if _image_studio_request_needs_image_step(request_text) and not (present_lanes & IMAGE_STUDIO_IMAGE_LANES):
        image_lane = _image_studio_first_ready(_image_studio_image_lane_order(request_text), ready_lanes)
        if image_lane:
            image_count = (
                _image_studio_requested_artifact_count(request_text, image_lane)
                or source_count
                or 1
            )
            synthesized.append({
                "lane": image_lane,
                "label": IMAGE_STUDIO_LANES.get(image_lane, {}).get("label") or image_lane,
                "prompt": "{{image_prompt}}",
                "purpose": "Generate one image for each structured source item.",
                "batch": {
                    "source_step": text_source_step,
                    "items": f"all objects from step {text_source_step}",
                    "count": image_count,
                    "strategy": "sequential",
                },
                "depends_on": [text_source_step],
            })

    return synthesized


def _image_studio_enforce_step_contracts(steps, original_request, latest_prompt):
    if not isinstance(steps, list):
        return steps
    steps = _image_studio_synthesize_missing_dependent_steps(steps, original_request, latest_prompt)
    request_text = f"{original_request or ''}\n{latest_prompt or ''}"
    steps = _image_studio_prune_forbidden_media_steps(steps, request_text)
    explicit_seconds = _image_studio_explicit_seconds(original_request) or _image_studio_explicit_seconds(latest_prompt)
    source_counts = {}
    for index, step in enumerate(steps):
        lane = str((step or {}).get("lane") or "").strip().lower()
        batch = (step or {}).get("batch") if isinstance((step or {}).get("batch"), dict) else None
        if not batch and lane in {"kokoro", "voice"}:
            source_step = _image_studio_source_item_step(step, steps, index)
            prompt_context = " ".join(
                str((step or {}).get(key) or "")
                for key in ("purpose", "prompt")
            )
            if source_step and re.search(r"\b(?:step\s*\d+|from|use|using|source|text|paragraph|copy|script|positioning|description|summary)\b", prompt_context, re.I):
                batch = {
                    "source_step": source_step,
                    "items": f"all objects from step {source_step}",
                    "count": _image_studio_requested_artifact_count(request_text, lane) or 1,
                    "strategy": "sequential",
                }
                step["batch"] = batch
        if not batch:
            continue
        if not _image_studio_batch_can_repeat_for_lane(step, lane, request_text):
            step["batch"] = None
            step["prompt"] = _image_studio_global_media_prompt(step.get("prompt") or "", lane, request_text)
            continue
        requested_count = _image_studio_requested_artifact_count(request_text, lane)
        if requested_count:
            batch["count"] = requested_count
            batch.setdefault("strategy", "sequential")
            step["batch"] = batch
        source_step = int((batch or {}).get("source_step") or 0)
        count = int((batch or {}).get("count") or 0)
        if source_step and count:
            source_counts[source_step] = max(source_counts.get(source_step, 0), count)
    source_requirements = _image_studio_plan_source_requirements(steps, original_request, latest_prompt)
    source_prompts = {
        index + 1: str((step or {}).get("prompt") or "")
        for index, step in enumerate(steps)
        if str((step or {}).get("lane") or "").strip().lower() == "text"
    }
    for index, step in enumerate(steps):
        lane = str((step or {}).get("lane") or "").strip().lower()
        if lane == "text":
            prompt_text = str(step.get("prompt") or "")
            if "{{" in prompt_text:
                prompt_text = re.sub(
                    r"\{\{([a-zA-Z0-9_]+)\}\}",
                    lambda match: "the object's " + match.group(1) + " value",
                    prompt_text,
                )
            required_fields = source_requirements.get(index + 1, set())
            if required_fields:
                ordered_fields = [
                    field
                    for field in ("name", "dates", "text", "image_prompt", "speech_text")
                    if field in required_fields
                ]
                expected_count = source_counts.get(index + 1, 0)
                prompt_text = _image_studio_sanitize_source_count_prompt(prompt_text, expected_count)
                object_count_guidance = (
                    "If earlier wording asks for separate entries for individual assets but the required count is one, combine the source details into that one top-level object instead of returning multiple asset entries. "
                    if expected_count == 1
                    else "If the request names or implies multiple objects, put each object at the top level of the array and never combine them into a single wrapper object. "
                )
                prompt_text = (
                    prompt_text.rstrip()
                    + " Output ONLY a strict JSON array. "
                    + (f"Output exactly {expected_count} top-level object(s)/item(s). " if expected_count else "")
                    + object_count_guidance
                    + "Preserve the user's requested count, order, ordinal range, membership, duplicates, editions, and named constraints exactly. "
                    + "Each object must include exactly these downstream fields: "
                    + ", ".join(ordered_fields)
                    + ". The text field should be the paragraph/body copy. "
                    + "The image_prompt field should be the exact prompt for that object's image and should include distinct pose, viewpoint, crop, setting/scenery, lighting, action, foreground/background depth, color emphasis, composition, and contextual details when multiple images are requested; vary at least three of those axes at once. "
                    + "The speech_text field should be the exact narration text for that object; when the request says to read, narrate, speak, or voice the paragraph/body/copy/text, speech_text must match text instead of quotes, excerpts, oaths, slogans, or alternate speeches. "
                    + "For fictional products, brands, worlds, facilities, or scenarios, stay inside the user's stated premise and do not add unrelated elements, audiences, claims, technologies, names, locations, objectives, story details, or worldbuilding that the user did not request. "
                    + "Use these exact field names and do not replace them with synonyms such as accomplishments, paragraph, narration, image, or speech."
                )
            if "image_prompt" in prompt_text or "speech_text" in prompt_text:
                prompt_text = (
                    prompt_text.rstrip()
                    + " Do not include literal {{...}} template placeholders in any generated field value."
                )
            step["prompt"] = prompt_text.strip()
            step["batch"] = None
            source_prompts[index + 1] = step["prompt"]
            continue
        batch = step.get("batch") if isinstance(step.get("batch"), dict) else None
        source_step = int((batch or {}).get("source_step") or 0)
        source_prompt = source_prompts.get(source_step, "")
        required_fields = source_requirements.get(source_step, set())
        if batch and lane in IMAGE_STUDIO_IMAGE_LANES and ("image_prompt" in source_prompt or "image_prompt" in required_fields):
            step["prompt"] = "{{image_prompt}}"
        elif batch and lane in {"kokoro", "voice"} and ("speech_text" in source_prompt or "speech_text" in required_fields):
            step["prompt"] = "{{speech_text}}"
        else:
            step["prompt"] = _image_studio_sanitize_media_step_prompt(step.get("prompt") or "")
        if lane in IMAGE_STUDIO_VIDEO_LANES:
            prompt_text = str(step.get("prompt") or "").strip()
            video_seconds = (
                _image_studio_explicit_seconds(prompt_text)
                or _image_studio_explicit_video_seconds(request_text)
                or explicit_seconds
            )
            if not video_seconds:
                continue
            if not re.search(r"\bexactly\s+\d{1,4}\s*seconds?\b", prompt_text, re.I):
                step["prompt"] = f"{prompt_text} Generate exactly {video_seconds} seconds.".strip()
    def step_order_key(item):
        index, step = item
        lane = str((step or {}).get("lane") or "").strip().lower()
        if lane == "text":
            return (index, -1, index)
        batch = (step or {}).get("batch") if isinstance((step or {}).get("batch"), dict) else None
        if batch:
            source_step = int((batch or {}).get("source_step") or 0)
            if source_step and (lane in {"kokoro", "voice"} or lane in IMAGE_STUDIO_IMAGE_LANES):
                lane_rank = 0 if lane in {"kokoro", "voice"} else 1
                return (source_step, lane_rank, index)
        return (index, 9, index)

    steps = _image_studio_prune_duplicate_speech_steps(steps, original_request, latest_prompt)
    return [
        step
        for _index, step in sorted(enumerate(steps), key=step_order_key)
    ]


def plan_image_studio_interactive(data):
    if benchmark_job_active():
        raise RuntimeError("AI Studio is disabled while Model Scores benchmarking is active.")
    prompt = str((data or {}).get("prompt") or "").strip()
    if not prompt:
        raise ValueError("Enter a prompt for Interactive Mode.")
    if len(prompt) > 20000:
        raise ValueError("Interactive prompt is too large.")
    attachments = list((data or {}).get("attachments") or [])
    previous_plan = (data or {}).get("previous_plan")
    original_request = (
        str(previous_plan.get("original_request") or "").strip()
        if isinstance(previous_plan, dict)
        else ""
    ) or prompt
    no_media_plan = _image_studio_no_media_direct_plan(prompt)
    if no_media_plan and not attachments:
        return no_media_plan
    ready = _image_studio_ready_lanes()
    ready_names = [lane for lane, ok in ready.items() if ok]
    fallback = _image_studio_heuristic_plan(prompt, attachments, ready)
    attachment_kinds = [str((row or {}).get("kind") or "file") for row in attachments]
    planner_input = json.dumps({
        "user_prompt": prompt,
        "attachment_kinds": attachment_kinds,
        "ready_lanes": ready_names,
        "previous_plan": previous_plan if isinstance(previous_plan, dict) else None,
    }, ensure_ascii=False)
    generation_metrics = {}
    try:
        message, generation_metrics = _image_studio_director_message(
            IMAGE_STUDIO_INTERACTIVE_PLAN_SYS,
            planner_input,
            max_tokens=4000,
            temperature=0.2,
            include_metrics=True,
        )
        plan = _image_studio_parse_json_object(message)
        if isinstance(previous_plan, dict):
            revision_input = json.dumps({
                "latest_revision": prompt,
                "original_request": original_request,
                "previous_plan": previous_plan,
                "candidate_plan": plan,
                "ready_lanes": ready_names,
            }, ensure_ascii=False)
            revised_message, generation_metrics = _image_studio_director_message(
                IMAGE_STUDIO_PLAN_REVISION_SYS,
                revision_input,
                max_tokens=4000,
                temperature=0.1,
                include_metrics=True,
            )
            plan = _image_studio_parse_json_object(revised_message)
    except Exception as exc:
        plan = {**fallback, "rationale": f"{fallback.get('rationale')} Director fallback: {exc}"}
    repaired_plan = _image_studio_repair_revision_plan(
        prompt,
        original_request,
        previous_plan if isinstance(previous_plan, dict) else None,
        plan if isinstance(plan, dict) else None,
    )
    if repaired_plan:
        plan = repaired_plan
    action = str(plan.get("action") or "").strip().lower()
    if action != "generate":
        return {
            "action": "chat",
            "title": str(plan.get("title") or fallback.get("title") or ""),
            "lane": "",
            "label": "Chat response",
            "prompt": str(plan.get("response") or plan.get("prompt") or fallback.get("prompt") or ""),
            "rationale": str(plan.get("rationale") or fallback.get("rationale") or ""),
            "steps": [],
            "ready_lanes": ready_names,
            "generation_metrics": generation_metrics,
        }
    raw_steps = plan.get("steps")
    if not isinstance(raw_steps, list):
        raw_steps = [{"lane": plan.get("lane"), "prompt": plan.get("prompt"), "purpose": plan.get("rationale")}]
    steps = []
    for row in raw_steps[:16]:
        if not isinstance(row, dict):
            continue
        lane = str(row.get("lane") or "").strip().lower()
        if lane != "text" and (lane not in IMAGE_STUDIO_LANES or not ready.get(lane)):
            continue
        step_prompt = str(row.get("prompt") or "").strip()
        if not step_prompt:
            continue
        dependencies = [
            int(value) for value in (row.get("depends_on") or [])
            if isinstance(value, (int, float)) and 0 < int(value) <= 16
        ]
        batch = row.get("batch") if isinstance(row.get("batch"), dict) else None
        purpose = str(row.get("purpose") or "").strip()
        repeated_work = re.search(
            r"\b(each|every|batch|repeated|per[- ]item|for all|one (?:image|audio|clip|portrait) (?:for|per))\b",
            purpose,
            re.I,
        )
        if batch is None and repeated_work and re.search(r"\{\{[a-zA-Z0-9_]+\}\}", step_prompt):
            source_step = dependencies[0] if dependencies else 1
            count_match = re.search(r"\b(?:count|items?)\D{0,8}(\d{1,4})\b", purpose, re.I)
            batch = {
                "source_step": source_step,
                "items": "all structured source items",
                "count": int(count_match.group(1)) if count_match else 0,
                "strategy": "sequential",
            }
        if lane == "text":
            batch = None
        steps.append({
            "lane": lane,
            "label": "Active Chat preset" if lane == "text" else IMAGE_STUDIO_LANES[lane]["label"],
            "prompt": step_prompt,
            "purpose": purpose,
            "batch": batch,
            "depends_on": dependencies,
        })
    if not steps:
        lane = str(fallback.get("lane") or "")
        fallback_prompt = str(fallback.get("prompt") or prompt).strip() or prompt
        if lane and ready.get(lane):
            steps = [{
                "lane": lane,
                "label": IMAGE_STUDIO_LANES[lane]["label"],
                "prompt": fallback_prompt,
                "purpose": str(fallback.get("rationale") or ""),
            }]
    if not steps:
        return {
            "action": "chat",
            "title": str(plan.get("title") or fallback.get("title") or ""),
            "lane": "",
            "label": "Chat response",
            "prompt": "That Studio lane is not installed yet. Pick an installed lane or download the missing models first.",
            "rationale": "Planner selected an unavailable lane.",
            "steps": [],
            "ready_lanes": ready_names,
            "generation_metrics": generation_metrics,
        }
    exact_lane_prompts = {
        str(lane).lower(): value
        for lane, value in re.findall(
            r"\b(kokoro|ideogram|hidream|chroma|zimage|krea|music|sfx|ltx|sulphur|10eros|wan|voice)\b"
            r"[^.\n]{0,80}?\b(?:must\s+use|prompt\s+must\s+be|use)\s+exactly\s+"
            r"(\{\{[a-zA-Z0-9_]+\}\})",
            prompt,
            re.I,
        )
    }
    for step in steps:
        exact_prompt = exact_lane_prompts.get(step["lane"])
        if exact_prompt:
            step["prompt"] = exact_prompt
    steps = _image_studio_collapse_indexed_source_steps(steps, original_request, prompt)
    steps = _image_studio_enforce_step_contracts(steps, original_request, prompt)
    first = steps[0]
    return {
        "action": "generate",
        "title": str(plan.get("title") or fallback.get("title") or ""),
        "lane": first["lane"],
        "label": first["label"],
        "prompt": first["prompt"],
        "rationale": str(plan.get("rationale") or fallback.get("rationale") or ""),
        "steps": steps,
        "ready_lanes": ready_names,
        "original_request": original_request,
        "generation_metrics": generation_metrics,
    }


def _image_studio_step_voice_health(timeout=3):
    try:
        request = urllib.request.Request(IMAGE_STUDIO_STEP_VOICE_URL.rstrip("/") + "/health")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response) or {}
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _image_studio_step_voice_available():
    payload = _image_studio_step_voice_health()
    if payload.get("ready"):
        return True
    return bool(payload.get("ok") and payload.get("lazy"))


def _image_studio_step_voice_unload(timeout=5):
    request = urllib.request.Request(
        IMAGE_STUDIO_STEP_VOICE_URL.rstrip("/") + "/unload",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


def _image_studio_voice_request(prompt, options, cancel_event=None):
    ready = _image_studio_step_voice_available()
    if not ready:
        compose_dir = os.path.join(CLUB3090_DIR, "services", "studio", "step-voice")
        compose_file = os.path.join(compose_dir, "docker-compose.yml")
        _image_studio_preflight_compose_images("Step-Audio runtime compose up", compose_dir, compose_file, may_build=True)
        command = ["docker", "compose", "--project-directory", compose_dir, "-f", compose_file, "up", "-d", "--build"]
        process = subprocess.Popen(
            command,
            cwd=CLUB3090_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.monotonic() + 600
        while process.poll() is None:
            if cancel_event and cancel_event.wait(1):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise InterruptedError("Voice generation cancelled.")
            if time.monotonic() >= deadline:
                process.kill()
                raise TimeoutError("Step-Audio service build timed out.")
        if process.returncode:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"Step-Audio service failed to start: {output[-800:]}")
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if cancel_event and cancel_event.wait(0):
                raise InterruptedError("Voice generation cancelled.")
            if _image_studio_step_voice_available():
                ready = True
                break
            if cancel_event:
                cancel_event.wait(2)
            else:
                time.sleep(2)
    if not ready:
        raise RuntimeError("Step-Audio voice service did not become reachable within 180 seconds.")
    attachments = list(options.get("attachments") or [])
    reference = str(options.get("voice_reference") or "Narrator.wav")
    audio_attachment = next((row for row in attachments if str(row.get("kind") or "") == "audio"), None)
    if audio_attachment:
        reference = chat_attachment_data_url(str(audio_attachment.get("url") or ""))
    payload = json.dumps({
        "text": prompt,
        "reference": reference,
        "prompt_text": str(options.get("reference_transcript") or ""),
    }).encode("utf-8")
    request = urllib.request.Request(
        IMAGE_STUDIO_STEP_VOICE_URL.rstrip("/") + "/clone",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=max(60, min(1800, int(options.get("timeout_seconds") or 900)))) as response:
        result = json.load(response)
    filename = str(result.get("filename") or "")
    if not filename:
        raise RuntimeError(str(result.get("error") or "Voice service returned no output."))
    return _image_studio_local_output("audio", filename, result.get("subfolder") or "")


def _image_studio_kokoro_voice(prompt, options):
    requested = str((options or {}).get("voice") or "").strip()
    if requested:
        return requested
    text = " ".join(
        str(value or "")
        for value in (
            prompt,
            (options or {}).get("voice_hint"),
            (options or {}).get("gender"),
            (options or {}).get("speaker"),
        )
    ).lower()
    female_voices = ("af_heart", "af_bella", "af_nicole")
    male_voices = ("am_adam", "am_michael", "bm_george", "am_echo")
    if re.search(r"\b(?:she|her|hers|woman|female|girl|mother|queen|actress|soprano|alto)\b", text):
        return female_voices[0]
    if re.search(r"\b(?:he|him|his|man|male|boy|father|king|president|actor|baritone|tenor|bass)\b", text):
        return male_voices[0]
    return female_voices[0]


def _image_studio_kokoro_request(prompt, options, cancel_event=None):
    if cancel_event and cancel_event.wait(0):
        raise InterruptedError("Kokoro generation cancelled.")
    payload = json.dumps({
        "text": prompt,
        "voice": _image_studio_kokoro_voice(prompt, options),
        "speed": float(options.get("speed") or 1.0),
    }).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:8192/tts",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=max(60, min(600, int(options.get("timeout_seconds") or 300)))) as response:
        result = json.load(response)
    filename = str(result.get("wav") or "")
    if not filename:
        raise RuntimeError(str(result.get("error") or "Kokoro returned no output."))
    output = _image_studio_local_output("audio", filename)
    if cancel_event and cancel_event.wait(0):
        _image_studio_delete_outputs([output])
        raise InterruptedError("Kokoro generation cancelled.")
    return output


def _image_studio_json_request(path, payload=None, timeout=30):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        IMAGE_STUDIO_COMFY_URL.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _image_studio_http_error_detail(exc):
    detail = str(exc)
    try:
        body = exc.read().decode("utf-8", "replace")
    except Exception:
        body = ""
    if body:
        try:
            payload = json.loads(body)
            body = str(payload.get("error") or payload)
        except Exception:
            body = body.strip()
        if body:
            detail = f"{detail}: {body[:800]}"
    return detail


def _image_studio_production_json_request(path, payload=None, timeout=30):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        IMAGE_STUDIO_PRODUCTION_URL.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_image_studio_http_error_detail(exc)) from exc


def image_studio_backend_plan_status():
    try:
        payload = _image_studio_production_json_request("/produce/health", timeout=2)
        return {
            "ready": bool(payload.get("ok")),
            "active": bool(payload.get("active")),
            "url": IMAGE_STUDIO_PRODUCTION_URL,
            "renders_today": payload.get("renders_today") or {},
            "video_lanes": payload.get("video_lanes") or {},
            "keyframe_lanes": payload.get("keyframe_lanes") or {},
            "error": "",
        }
    except Exception as exc:
        return {
            "ready": False,
            "active": False,
            "url": IMAGE_STUDIO_PRODUCTION_URL,
            "renders_today": {},
            "video_lanes": {},
            "keyframe_lanes": {},
            "error": str(exc),
        }


def _image_studio_output_for_local_path(path, kind=""):
    abs_path = os.path.realpath(os.path.abspath(str(path or "")))
    detected_kind = kind or _image_studio_media_kind_for_path(abs_path)
    if not detected_kind or not os.path.isfile(abs_path):
        return None
    relative = os.path.relpath(abs_path, "/").replace("\\", "/")
    query = urllib.parse.urlencode({"root_path": "/", "relative_path": relative})
    return {
        "kind": detected_kind,
        "name": os.path.basename(abs_path),
        "root_path": "/",
        "relative_path": relative,
        "url": f"/admin/storage-browser/preview?{query}",
    }


def _image_studio_output_from_production_status(status):
    final_path = str(
        (status or {}).get("final")
        or (status or {}).get("final_path")
        or (status or {}).get("output")
        or ""
    ).strip()
    manifest = (status or {}).get("manifest")
    if not final_path and isinstance(manifest, dict):
        final_path = str(manifest.get("final") or "").strip()
    output = _image_studio_output_for_local_path(final_path, "video") if final_path else None
    if output:
        return output
    gallery_url = str((status or {}).get("gallery_url") or "").strip()
    if gallery_url and not urllib.parse.urlparse(gallery_url).scheme:
        output = _image_studio_output_for_local_path(os.path.join(IMAGE_STUDIO_OUTPUT_ROOT, gallery_url.lstrip("/")), "video")
        if output:
            return output
    if gallery_url:
        return {
            "kind": "video",
            "name": os.path.basename(gallery_url.rstrip("/")) or "production.mp4",
            "root_path": "",
            "relative_path": gallery_url,
            "url": gallery_url,
        }
    return None


def _image_studio_ui_workflow(api_workflow):
    with IMAGE_STUDIO_JOB_LOCK:
        object_info = dict(image_studio_object_info_cache)
    if not object_info:
        try:
            object_info = _image_studio_json_request("/object_info", timeout=30)
        except Exception:
            object_info = {}
        with IMAGE_STUDIO_JOB_LOCK:
            image_studio_object_info_cache.clear()
            image_studio_object_info_cache.update(object_info)
    source_rows = list((api_workflow or {}).items())
    node_ids = {str(source_id): index + 1 for index, (source_id, _row) in enumerate(source_rows)}
    nodes = []
    links = []
    output_links = {}
    linked_output_slots = {}
    next_link_id = 1
    for _source_id, source_row in source_rows:
        for input_value in ((source_row or {}).get("inputs") or {}).values():
            if (
                isinstance(input_value, (list, tuple))
                and len(input_value) == 2
                and str(input_value[0]) in node_ids
            ):
                linked_output_slots.setdefault(str(input_value[0]), set()).add(int(input_value[1]))
    for order, (source_id, source_row) in enumerate(source_rows):
        class_type = str((source_row or {}).get("class_type") or "Unknown")
        class_info = object_info.get(class_type) or {}
        input_info = class_info.get("input") or {}
        declared_inputs = {}
        for group in ("required", "optional"):
            declared_inputs.update(input_info.get(group) or {})
        inputs = []
        widgets = []
        for input_name, input_value in ((source_row or {}).get("inputs") or {}).items():
            type_spec = declared_inputs.get(input_name) or ["*"]
            input_type = type_spec[0] if isinstance(type_spec, (list, tuple)) and type_spec else "*"
            if isinstance(input_type, (list, tuple)):
                input_type = "COMBO"
            if (
                isinstance(input_value, (list, tuple))
                and len(input_value) == 2
                and str(input_value[0]) in node_ids
            ):
                origin_id = node_ids[str(input_value[0])]
                origin_slot = int(input_value[1])
                link_id = next_link_id
                next_link_id += 1
                inputs.append({"name": str(input_name), "type": input_type, "link": link_id})
                links.append([
                    link_id,
                    origin_id,
                    origin_slot,
                    node_ids[str(source_id)],
                    len(inputs) - 1,
                    input_type,
                ])
                output_links.setdefault((origin_id, origin_slot), []).append(link_id)
            else:
                widgets.append(input_value)
        output_types = list(class_info.get("output") or [])
        output_names = list(class_info.get("output_name") or [])
        linked_slots = linked_output_slots.get(str(source_id), set())
        output_count = max(len(output_types), max(linked_slots, default=-1) + 1)
        outputs = []
        for output_index in range(output_count):
            output_type = output_types[output_index] if output_index < len(output_types) else "*"
            outputs.append({
                "name": str(output_names[output_index] if output_index < len(output_names) else output_type),
                "type": output_type,
                "links": output_links.get((node_ids[str(source_id)], output_index)) or None,
                "slot_index": output_index,
            })
        nodes.append({
            "id": node_ids[str(source_id)],
            "type": class_type,
            "pos": [40 + (order % 4) * 360, 40 + (order // 4) * 220],
            "size": [320, max(100, 70 + 24 * max(len(inputs), len(widgets)))],
            "flags": {},
            "order": order,
            "mode": 0,
            "inputs": inputs,
            "outputs": outputs,
            "properties": {"Node name for S&R": class_type},
            "title": str(((source_row or {}).get("_meta") or {}).get("title") or class_type),
            "widgets_values": widgets,
        })
    for node in nodes:
        for output in node.get("outputs") or []:
            output["links"] = output_links.get((node["id"], output["slot_index"])) or None
    workflow_hex = secrets.token_hex(16)
    workflow_id = (
        f"{workflow_hex[:8]}-{workflow_hex[8:12]}-"
        f"4{workflow_hex[13:16]}-"
        f"8{workflow_hex[17:20]}-"
        f"{workflow_hex[20:32]}"
    )
    return {
        "id": workflow_id,
        "revision": 0,
        "last_node_id": len(nodes),
        "last_link_id": next_link_id - 1,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {},
        "version": 0.4,
    }


def _image_studio_free_memory(timeout=30):
    payload = json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8")
    request = urllib.request.Request(
        IMAGE_STUDIO_COMFY_URL.rstrip("/") + "/free",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


def _image_studio_should_free_memory(kind):
    if kind not in {"image", "audio", "video", "voice"}:
        return False
    with IMAGE_STUDIO_JOB_LOCK:
        previous_kind = str(image_studio_comfy_model_cache.get("kind") or "")
        if not previous_kind:
            try:
                previous_kind = open(IMAGE_STUDIO_LAST_KIND_FILE, "r", encoding="utf-8").read().strip()
            except Exception:
                previous_kind = ""
        image_studio_comfy_model_cache["kind"] = kind
        try:
            os.makedirs(CONTROL_DIR, exist_ok=True)
            with open(IMAGE_STUDIO_LAST_KIND_FILE, "w", encoding="utf-8") as handle:
                handle.write(kind)
        except Exception:
            pass
    return bool(previous_kind and previous_kind != kind)


def _image_studio_container_running(name):
    try:
        output = subprocess.check_output(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            cwd=CLUB3090_DIR,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return output.strip().lower() == "true"
    except Exception:
        return False


def _image_studio_env_path():
    return os.path.join(CLUB3090_DIR, ".env")


def _image_studio_repair_director_env_default(max_age=60.0):
    now = time.time()
    last_checked = float(image_studio_director_env_repair_cache.get("checked_at") or 0.0)
    if now - last_checked < max(1.0, float(max_age or 0.0)):
        return False
    image_studio_director_env_repair_cache["checked_at"] = now
    if str(os.environ.get("STUDIO_DIRECTOR_DEVICE") or "").strip().lower() == "cpu":
        return False
    env_path = _image_studio_env_path()
    if not os.path.isfile(env_path):
        return False
    try:
        with open(env_path, "r", encoding="utf-8") as handle:
            original = handle.read()
    except Exception:
        return False
    lines = original.splitlines()

    def env_value(key):
        value = ""
        prefix = key + "="
        for line in lines:
            if line.startswith(prefix):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
        return value

    if env_value("STUDIO_DIRECTOR_DEVICE").lower() != "cpu":
        return False
    updates = {
        "STUDIO_DIRECTOR_DEVICE": "auto",
        "DIRECTOR_NGL": "99",
        "STUDIO_DIRECTOR_CUDA": "0",
        "STUDIO_DIRECTOR_GPU": "0",
        "STUDIO_DIRECTOR_GPU_LAYERS": "99",
        "DIRECTOR_THINK_ARGS": "",
    }
    seen = set()
    rewritten = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in updates:
            if key in seen:
                continue
            rewritten.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            rewritten.append(line)
    for key, value in updates.items():
        if key not in seen:
            rewritten.append(f"{key}={value}")
    new_text = "\n".join(rewritten)
    if original.endswith("\n"):
        new_text += "\n"
    if new_text == original:
        return False
    temp_path = env_path + ".club3090.tmp"
    try:
        mode = os.stat(env_path).st_mode
        with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(new_text)
        os.chmod(temp_path, mode)
        os.replace(temp_path, env_path)
    except Exception as exc:
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except Exception:
            pass
        log_control(f"AI Studio Director env repair failed: {exc}")
        return False
    log_audit(
        "image_studio_director_env_repair",
        from_device="cpu",
        to_device="auto",
        updated=sorted(updates),
    )
    return True


def _image_studio_read_env_value(key):
    if key == "STUDIO_DIRECTOR_DEVICE":
        _image_studio_repair_director_env_default()
    prefix = str(key or "") + "="
    try:
        with open(_image_studio_env_path(), "r", encoding="utf-8") as handle:
            for line in reversed(handle.read().splitlines()):
                if line.startswith(prefix):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _image_studio_all_gpu_indices():
    free_map = _image_studio_gpu_free_mib()
    if free_map:
        return set(free_map)
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader,nounits"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        return set()
    result = set()
    for line in output.splitlines():
        text = line.strip()
        if text.isdigit():
            result.add(int(text))
    return result


def _image_studio_container_env(name):
    try:
        output = subprocess.check_output(
            ["docker", "inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", name],
            cwd=CLUB3090_DIR,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        return {}
    result = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def _image_studio_container_gpu_indices(name):
    try:
        output = subprocess.check_output(
            ["docker", "inspect", "-f", "{{json .HostConfig.DeviceRequests}}", name],
            cwd=CLUB3090_DIR,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        requests = json.loads(output or "null") or []
    except Exception:
        return set()
    indices = set()
    for request in requests if isinstance(requests, list) else []:
        row = request if isinstance(request, dict) else {}
        device_ids = row.get("DeviceIDs") or []
        for value in device_ids:
            text = str(value or "").strip()
            if text.isdigit():
                indices.add(int(text))
        if not device_ids and int(row.get("Count") or 0) != 0:
            indices.update(_image_studio_all_gpu_indices() or {0, 1})
    return indices


def _image_studio_director_gpu_layers():
    device_candidates = [os.environ.get("STUDIO_DIRECTOR_DEVICE")]
    layer_candidates = [
        os.environ.get("STUDIO_DIRECTOR_GPU_LAYERS"),
        os.environ.get("DIRECTOR_NGL"),
    ]
    cuda_candidates = [
        os.environ.get("STUDIO_DIRECTOR_CUDA"),
        os.environ.get("CUDA_VISIBLE_DEVICES"),
    ]
    try:
        with open(_image_studio_env_path(), "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("STUDIO_DIRECTOR_DEVICE="):
                    device_candidates.append(line.split("=", 1)[1].strip().strip('"').strip("'"))
                if line.startswith("STUDIO_DIRECTOR_GPU_LAYERS="):
                    layer_candidates.append(line.split("=", 1)[1].strip().strip('"').strip("'"))
                if line.startswith("DIRECTOR_NGL="):
                    layer_candidates.append(line.split("=", 1)[1].strip().strip('"').strip("'"))
                if line.startswith("STUDIO_DIRECTOR_CUDA="):
                    cuda_candidates.append(line.split("=", 1)[1].strip().strip('"').strip("'"))
    except Exception:
        pass
    container_env = _image_studio_container_env("studio-director")
    container_cuda_visible = str(container_env.get("CUDA_VISIBLE_DEVICES") or "").strip()
    container_gpu_indices = _image_studio_container_gpu_indices("studio-director")
    if len(container_gpu_indices) == 1 and container_cuda_visible and container_cuda_visible != "0":
        return 0
    for key in ("STUDIO_DIRECTOR_DEVICE",):
        if key in container_env:
            device_candidates.append(container_env.get(key))
    for key in ("STUDIO_DIRECTOR_GPU_LAYERS", "DIRECTOR_NGL"):
        if key in container_env:
            layer_candidates.append(container_env.get(key))
    for key in ("STUDIO_DIRECTOR_CUDA", "CUDA_VISIBLE_DEVICES"):
        if key in container_env:
            cuda_candidates.append(container_env.get(key))
    for value in reversed(device_candidates):
        text = str(value or "").strip().lower()
        if text == "cpu":
            return 0
        if text == "gpu" or re.fullmatch(r"gpu\d+", text):
            return 99
    for value in reversed(cuda_candidates):
        text = str(value if value is not None else "").strip()
        if text == "":
            return 0
        if text.lower() not in {"none", "cpu", "-1"}:
            return 99
    for value in layer_candidates:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            return max(0, int(float(text)))
        except Exception:
            continue
    return 0


def _image_studio_ensure_comfyui_running(timeout=180):
    if _image_studio_container_running("comfyui"):
        return
    env = dict(os.environ)
    env["COMFYUI_CUDA_VISIBLE_DEVICES"] = ""
    compose_dir = os.path.join(CLUB3090_DIR, "services", "comfyui")
    compose_file = os.path.join(compose_dir, "docker-compose.yml")
    _image_studio_preflight_compose_images("ComfyUI runtime compose up", compose_dir, compose_file, env=env)
    subprocess.run(
        ["docker", "compose", "--project-directory", compose_dir, "-f", compose_file, "up", "-d"],
        cwd=CLUB3090_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=60,
    )
    deadline = time.monotonic() + max(5, timeout)
    while time.monotonic() < deadline:
        try:
            _image_studio_json_request("/system_stats", timeout=5)
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("ComfyUI did not become ready after restart.")


def _image_studio_prepare_video_resources():
    if _image_studio_container_running("studio-step-voice"):
        try:
            _image_studio_step_voice_unload(timeout=8)
            return
        except Exception:
            pass
    subprocess.run(
        ["docker", "stop", "studio-step-voice"],
        cwd=CLUB3090_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=30,
    )


def image_studio_release_idle_gpu_resources_for_benchmark(gpu_indices=None):
    targets = {
        int(index)
        for index in (gpu_indices or [])
        if str(index).strip().lstrip("-").isdigit() and int(index) >= 0
    }
    if not targets:
        return []
    if image_studio_activity_active(max_age=0):
        return []
    stopped = []
    warnings = []

    def stop_container(name, reason):
        if not _image_studio_container_running(name):
            return
        try:
            proc = subprocess.run(
                ["docker", "stop", name],
                cwd=CLUB3090_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                timeout=45,
            )
            if proc.returncode == 0:
                stopped.append(f"{name}:{reason}")
            else:
                warnings.append(f"{name}: rc={proc.returncode} {(proc.stdout or '')[-300:]}")
        except Exception as exc:
            warnings.append(f"{name}: {exc}")

    if targets:
        if _image_studio_container_running("comfyui"):
            try:
                _image_studio_free_memory(timeout=15)
            except Exception as exc:
                warnings.append(f"comfyui/free: {exc}")
            stop_container("comfyui", "benchmark-vram")
            with IMAGE_STUDIO_JOB_LOCK:
                image_studio_comfy_model_cache["kind"] = ""
    if _image_studio_director_gpu_layers() > 0 and _image_studio_container_gpu_indices("studio-director").intersection(targets):
        stop_container("studio-director", "benchmark-gpu")
    if 0 in targets:
        stop_container("llama-cpp-gemma4-12b", "benchmark-gpu0")
    if 1 in targets:
        stop_container("studio-step-voice", "benchmark-gpu1")

    if stopped or warnings:
        log_audit(
            "benchmark_ai_studio_gpu_release",
            target_gpus=sorted(targets),
            stopped=stopped,
            warnings=warnings,
        )
    return stopped


def _image_studio_gpu_free_mib():
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        return {}
    result = {}
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            result[int(parts[0])] = int(float(parts[1]))
        except Exception:
            continue
    return result


def _image_studio_generation_target_gpus(kind):
    free_map = _image_studio_gpu_free_mib()
    all_gpus = set(free_map) or _image_studio_all_gpu_indices()
    if not all_gpus:
        return set()
    kind = str(kind or "").strip().lower()
    if kind == "video":
        return set(all_gpus)
    if kind == "voice":
        return {1} if 1 in all_gpus else {max(all_gpus)}
    if kind in {"image", "audio"}:
        return {0} if 0 in all_gpus else {min(all_gpus)}
    return set()


def _image_studio_director_policy():
    explicit = str(os.environ.get("STUDIO_DIRECTOR_DEVICE") or "").strip().lower()
    configured = explicit or _image_studio_read_env_value("STUDIO_DIRECTOR_DEVICE").strip().lower()
    if not configured:
        return "auto"
    if configured in {"auto", "dynamic"}:
        return "auto"
    if configured in {"cpu", "gpu"} or re.fullmatch(r"gpu\d+", configured):
        return configured
    return "auto"


def _image_studio_director_actual_placement():
    if not _image_studio_container_running("studio-director"):
        return ""
    if _image_studio_director_gpu_layers() <= 0:
        return "cpu"
    indices = _image_studio_container_gpu_indices("studio-director")
    if indices:
        return "gpu" + str(min(indices))
    cuda_value = str(_image_studio_container_env("studio-director").get("CUDA_VISIBLE_DEVICES") or "").strip()
    cuda_index = next(
        (int(part) for part in re.split(r"\s*,\s*", cuda_value) if part.isdigit()),
        None,
    )
    if cuda_index is not None:
        return "gpu" + str(cuda_index)
    return "gpu0"


def _image_studio_director_best_gpu():
    free_map = _image_studio_gpu_free_mib()
    if not free_map:
        return None
    return max(free_map, key=lambda index: (free_map.get(index, 0), -index))


def _image_studio_director_desired_for_planning():
    policy = _image_studio_director_policy()
    if policy == "cpu":
        return "cpu"
    if re.fullmatch(r"gpu\d+", policy):
        return policy
    current = _image_studio_director_actual_placement()
    if current.startswith("gpu"):
        return current
    best_gpu = _image_studio_director_best_gpu()
    if best_gpu is None:
        return "cpu"
    if _image_studio_gpu_free_mib().get(best_gpu, 0) < IMAGE_STUDIO_DIRECTOR_AUTO_MIN_FREE_MIB:
        return "cpu"
    return "gpu" + str(best_gpu)


def _image_studio_director_compose_env(placement):
    placement = str(placement or "").strip().lower()
    match = re.fullmatch(r"gpu(\d+)", placement)
    if match:
        gpu = int(match.group(1))
        return {
            "DIRECTOR_NGL": "99",
            # Docker's device_ids selects the physical GPU; inside the container that
            # single exposed device is CUDA index 0. Passing the physical id here can
            # hide the GPU and leave llama.cpp on CPU.
            "STUDIO_DIRECTOR_CUDA": "0",
            "STUDIO_DIRECTOR_GPU": str(gpu),
            "DIRECTOR_THINK_ARGS": "",
        }
    return {
        "DIRECTOR_NGL": "0",
        "STUDIO_DIRECTOR_CUDA": "",
        "STUDIO_DIRECTOR_GPU": "0",
        "DIRECTOR_THINK_ARGS": "--jinja --reasoning off",
    }


def _image_studio_director_healthcheck_override():
    override_dir = os.path.join(CONTROL_DIR, "compose-overrides")
    override_path = os.path.join(override_dir, "studio-director-healthcheck.override.yml")
    override_text = """services:
  studio-director:
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS --max-time 3 http://127.0.0.1:${STUDIO_DIRECTOR_PORT:-8090}/v1/models >/dev/null"]
      interval: 15s
      timeout: 5s
      retries: 20
      start_period: 20s
"""
    os.makedirs(override_dir, exist_ok=True)
    try:
        current = ""
        if os.path.isfile(override_path):
            with open(override_path, "r", encoding="utf-8") as handle:
                current = handle.read()
        if current != override_text:
            with open(override_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(override_text)
    except Exception as exc:
        log_control(f"AI Studio Director healthcheck override write failed: {exc}")
        return ""
    return override_path


def _image_studio_wait_director_ready(timeout=180):
    deadline = time.monotonic() + max(10, int(timeout or 180))
    last_error = ""
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request("http://127.0.0.1:8090/v1/models")
            with urllib.request.urlopen(request, timeout=5) as response:
                response.read()
            return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(2)
    raise RuntimeError(f"Studio Director did not become ready after placement change: {last_error}")


def _image_studio_restart_director(placement, reason=""):
    compose_dir = os.path.join(CLUB3090_DIR, "services", "studio", "enhancer")
    compose_file = os.path.join(compose_dir, "docker-compose.yml")
    if not os.path.isfile(compose_file):
        raise FileNotFoundError("Studio Director compose file is missing.")
    override_file = _image_studio_director_healthcheck_override()
    env = dict(os.environ)
    env.update(_image_studio_director_compose_env(placement))
    cmd = ["docker", "compose"]
    env_path = _image_studio_env_path()
    env_file = env_path if os.path.isfile(env_path) else None
    if os.path.isfile(env_path):
        cmd += ["--env-file", env_path]
    cmd += ["--project-directory", compose_dir, "-f", compose_file]
    if override_file:
        cmd += ["-f", override_file]
    cmd += ["up", "-d", "--force-recreate", "studio-director"]
    _image_studio_preflight_compose_images("Studio Director compose up", compose_dir, compose_file, env=env, env_file=env_file)
    proc = subprocess.run(
        cmd,
        cwd=CLUB3090_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Studio Director placement failed: {(proc.stdout or '')[-800:]}")
    image_studio_runtime_cache["checked_at"] = 0.0
    log_audit(
        "image_studio_director_placement",
        placement=placement,
        reason=reason,
        output=(proc.stdout or "")[-800:],
    )
    _image_studio_wait_director_ready(timeout=180)


def _image_studio_ensure_director_runtime(reason="planning"):
    if benchmark_job_active():
        return
    desired = _image_studio_director_desired_for_planning()
    current = _image_studio_director_actual_placement()
    if current == desired:
        _image_studio_wait_director_ready(timeout=30)
        return
    _image_studio_restart_director(desired, reason=reason or "planning")


def _image_studio_prepare_director_for_generation(kind):
    policy = _image_studio_director_policy()
    if policy == "cpu":
        if _image_studio_director_actual_placement() != "cpu":
            _image_studio_restart_director("cpu", reason=f"{kind}-explicit-cpu")
        return []
    if not _image_studio_container_running("studio-director"):
        return []
    current = _image_studio_director_actual_placement()
    if not current.startswith("gpu"):
        return []
    target_gpus = _image_studio_generation_target_gpus(kind)
    director_gpus = _image_studio_container_gpu_indices("studio-director")
    if not director_gpus:
        match = re.fullmatch(r"gpu(\d+)", current)
        director_gpus = {int(match.group(1))} if match else set()
    if not target_gpus.intersection(director_gpus):
        return []
    required = IMAGE_STUDIO_GENERATION_FREE_MIB.get(str(kind or "").strip().lower(), 0)
    free_before = _image_studio_gpu_free_mib()
    if required and all(free_before.get(gpu, 0) >= required for gpu in target_gpus):
        return []
    _image_studio_restart_director("cpu", reason=f"{kind}-vram-pressure")
    log_audit(
        "image_studio_director_cpu_offload",
        kind=kind,
        target_gpus=sorted(target_gpus),
        director_gpus=sorted(director_gpus),
        free_before=free_before,
        required_free_mib=required,
    )
    return ["studio-director:cpu-offload"]


def _image_studio_release_conflicting_runtimes(kind):
    required = IMAGE_STUDIO_GENERATION_FREE_MIB.get(str(kind or "").strip().lower(), 0)
    target_gpus = _image_studio_generation_target_gpus(kind)
    if not required:
        return []
    free_before = _image_studio_gpu_free_mib()
    constrained = {gpu for gpu in target_gpus if free_before.get(gpu, 0) < required}
    if not constrained:
        return []
    stopped = []
    for row in running_runtime_rows(instances_snapshot()):
        row_gpus = {int(value) for value in (row.get("gpu_indices") or [row.get("gpu_index", 0)])}
        if not row_gpus.intersection(constrained):
            continue
        runtime_id = str(row.get("id") or "").strip()
        if not runtime_id:
            continue
        rc, _output = stop_instance(runtime_id)
        if rc == 0:
            stopped.append(runtime_id)
    if stopped:
        log_audit(
            "image_studio_runtime_handoff",
            kind=kind,
            stopped=stopped,
            free_before=free_before,
            required_free_mib=required,
        )
        time.sleep(2)
    return stopped


def _image_studio_prepare_voice_resources():
    step_voice_hot = _image_studio_container_running("studio-step-voice")
    if _image_studio_should_free_memory("voice") or not step_voice_hot:
        _image_studio_free_memory(timeout=30)
        subprocess.run(
            ["docker", "stop", "comfyui"],
            cwd=CLUB3090_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )


def _image_studio_output_from_history(history, prompt_id, wanted_kind):
    row = (history or {}).get(prompt_id) or {}
    for output in (row.get("outputs") or {}).values():
        groups = []
        if wanted_kind == "audio":
            groups = [output.get("audio") or []]
        elif wanted_kind == "video":
            groups = [output.get("videos") or [], output.get("gifs") or [], output.get("images") or []]
        else:
            groups = [output.get("images") or []]
        for group in groups:
            for item in group:
                filename = str(item.get("filename") or "")
                if not filename or item.get("type") == "temp":
                    continue
                suffix = Path(filename).suffix.lower()
                valid = (
                    wanted_kind == "image" and suffix in {".png", ".jpg", ".jpeg", ".webp"}
                    or wanted_kind == "audio" and suffix in {".mp3", ".flac", ".wav", ".opus", ".m4a", ".ogg"}
                    or wanted_kind == "video" and suffix in {".mp4", ".m4v", ".mov", ".webm", ".ogv"}
                )
                if valid:
                    subfolder = str(item.get("subfolder") or "").strip("/\\")
                    relative = _image_studio_output_relative_path(filename, subfolder)
                    query = urllib.parse.urlencode({"root_path": "/", "relative_path": relative})
                    return {
                        "kind": wanted_kind,
                        "name": filename,
                        "root_path": "/",
                        "relative_path": relative,
                        "url": f"/admin/storage-browser/preview?{query}",
                    }
    return None


def _image_studio_output_relative_path(filename, subfolder=""):
    path = os.path.join(
        IMAGE_STUDIO_OUTPUT_ROOT,
        str(subfolder or "").strip("/\\"),
        os.path.basename(str(filename or "")),
    )
    return os.path.relpath(os.path.realpath(os.path.abspath(path)), "/").replace("\\", "/")


def _image_studio_media_kind_for_path(path):
    suffix = Path(path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "image"
    if suffix in {".mp3", ".flac", ".wav", ".opus", ".m4a", ".ogg"}:
        return "audio"
    if suffix in {".mp4", ".m4v", ".mov", ".webm", ".ogv"}:
        return "video"
    return ""


def _image_studio_gallery_item(path, source):
    abs_path = os.path.realpath(os.path.abspath(path))
    kind = _image_studio_media_kind_for_path(abs_path)
    if not kind or not os.path.isfile(abs_path):
        return None
    try:
        stat = os.stat(abs_path)
    except Exception:
        return None
    relative = os.path.relpath(abs_path, "/").replace("\\", "/")
    query = urllib.parse.urlencode({"root_path": "/", "relative_path": relative})
    return {
        "kind": kind,
        "source": source,
        "name": os.path.basename(abs_path),
        "root_path": "/",
        "relative_path": relative,
        "url": f"/admin/storage-browser/preview?{query}",
        "size_bytes": int(stat.st_size),
        "mtime": int(stat.st_mtime),
    }


def image_studio_gallery_items(limit=120):
    roots = [
        ("conversation", os.path.join(CHAT_CONVERSATIONS_DIR, "media")),
        ("studio", IMAGE_STUDIO_OUTPUT_ROOT),
    ]
    items = []
    seen = set()
    for source, root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if not name.startswith(".")]
            for filename in filenames:
                path = os.path.join(dirpath, filename)
                try:
                    stat_row = os.stat(path)
                    key = (stat_row.st_dev, stat_row.st_ino)
                except Exception:
                    key = os.path.realpath(os.path.abspath(path))
                if key in seen:
                    continue
                seen.add(key)
                item = _image_studio_gallery_item(path, source)
                if item:
                    items.append(item)
    items.sort(key=lambda row: int(row.get("mtime") or 0), reverse=True)
    return items[: max(1, min(500, int(limit or 120)))]


def _image_studio_gallery_roots():
    return [
        os.path.realpath(os.path.abspath(IMAGE_STUDIO_OUTPUT_ROOT)),
        os.path.realpath(os.path.abspath(os.path.join(CHAT_CONVERSATIONS_DIR, "media"))),
    ]


def _image_studio_gallery_resolve_path(root_path, relative_path):
    root_path = str(root_path or "/").strip() or "/"
    relative_path = str(relative_path or "").strip().lstrip("/\\")
    if not relative_path:
        raise ValueError("Artifact path is required.")
    base = os.path.realpath(os.path.abspath(root_path))
    target = os.path.realpath(os.path.abspath(os.path.join(base, relative_path.replace("/", os.sep))))
    if not any(target == root or target.startswith(root.rstrip(os.sep) + os.sep) for root in _image_studio_gallery_roots()):
        raise ValueError("Refusing to delete a non-gallery path.")
    if not os.path.isfile(target):
        raise FileNotFoundError("Gallery artifact not found.")
    if not _image_studio_media_kind_for_path(target):
        raise ValueError("Refusing to delete a non-media gallery file.")
    return target


def delete_image_studio_gallery_artifact(root_path, relative_path):
    target = _image_studio_gallery_resolve_path(root_path, relative_path)
    try:
        target_stat = os.stat(target)
        target_key = (target_stat.st_dev, target_stat.st_ino)
    except Exception:
        target_key = None
    removed = []
    for root in _image_studio_gallery_roots():
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if not name.startswith(".")]
            for filename in filenames:
                candidate = os.path.join(dirpath, filename)
                should_remove = os.path.realpath(os.path.abspath(candidate)) == target
                if not should_remove and target_key:
                    try:
                        stat_row = os.stat(candidate)
                        should_remove = (stat_row.st_dev, stat_row.st_ino) == target_key
                    except Exception:
                        should_remove = False
                if not should_remove:
                    continue
                try:
                    os.remove(candidate)
                    removed.append(os.path.relpath(candidate, "/").replace("\\", "/"))
                except FileNotFoundError:
                    pass
    return {"removed": removed, "removed_count": len(removed)}


def _run_image_studio_job(job_id, lane, prompt, options):
    try:
        if lane == "kokoro":
            cancel_event = IMAGE_STUDIO_JOBS[job_id]["cancel_event"]
            if cancel_event.wait(0):
                _finish_image_studio_request(job_id, "cancelled", detail="Generation cancelled.")
                return
            _set_image_studio_job(job_id, status="running", detail="Kokoro is synthesizing narration.")
            output = _image_studio_kokoro_request(prompt, options, cancel_event)
            if cancel_event.wait(0):
                _image_studio_delete_outputs([output])
                _finish_image_studio_request(job_id, "cancelled", detail="Generation cancelled.")
                return
            _finish_image_studio_request(job_id, "success", detail="Kokoro voiceover complete.", output=output)
            log_audit("image_studio_generation_complete", lane=lane, job_id=job_id, output=output.get("relative_path"))
            return
        if lane == "voice":
            _set_image_studio_job(job_id, status="preparing", detail="Preparing GPU memory for Step-Audio.")
            _image_studio_prepare_director_for_generation("voice")
            _image_studio_prepare_voice_resources()
            _set_image_studio_job(job_id, status="running", detail="Step-Audio-EditX is synthesizing speech.")
            output = _image_studio_voice_request(prompt, options, IMAGE_STUDIO_JOBS[job_id]["cancel_event"])
            _finish_image_studio_request(job_id, "success", detail="Voice generation complete.", output=output)
            log_audit("image_studio_generation_complete", lane=lane, job_id=job_id, output=output.get("relative_path"))
            return
        attachments = list(options.get("attachments") or [])
        _image_studio_release_conflicting_runtimes(IMAGE_STUDIO_LANES[lane]["kind"])
        _image_studio_prepare_director_for_generation(IMAGE_STUDIO_LANES[lane]["kind"])
        freed_for_kind = False
        if lane in IMAGE_STUDIO_VIDEO_LANES:
            image_attachment = next((row for row in attachments if str(row.get("kind") or "") == "image"), None)
            if image_attachment:
                _set_image_studio_job(job_id, status="uploading", detail="Uploading image to ComfyUI.")
                options["comfy_image_name"] = _image_studio_upload_attachment(image_attachment)
            _set_image_studio_job(job_id, status="preparing", detail="Freeing GPU1 for video rendering.")
            _image_studio_prepare_video_resources()
            if _image_studio_should_free_memory(IMAGE_STUDIO_LANES[lane]["kind"]):
                freed_for_kind = True
                _set_image_studio_job(job_id, status="preparing", detail="Freeing ComfyUI model memory before video rendering.")
                _image_studio_free_memory(timeout=30)
        render_prompt = prompt
        render_options = dict(options)
        if lane == "ideogram":
            single_render = _image_studio_ideogram_single_render_requested(
                prompt,
                render_options,
            )
            render_options["candidate_grid"] = not single_render
            render_options["width"] = render_options.get("width") or 1024
            render_options["height"] = render_options.get("height") or 1024
        if lane in IMAGE_STUDIO_VIDEO_LANES:
            workflow, spec = _prepare_image_studio_workflow(
                lane,
                render_prompt,
                render_options,
            )
            _store_image_studio_workflow(job_id, workflow, spec, lane)
            long_video_output = _image_studio_run_long_video_job(
                job_id,
                lane,
                render_prompt,
                render_options,
                IMAGE_STUDIO_JOBS[job_id]["cancel_event"],
            )
            if long_video_output:
                if long_video_output.get("cancelled"):
                    return
                _finish_image_studio_request(
                    job_id,
                    "success",
                    detail=f"{IMAGE_STUDIO_LANES[lane]['label']} long video generation complete.",
                    output=long_video_output,
                )
                log_audit(
                    "image_studio_generation_complete",
                    lane=lane,
                    job_id=job_id,
                    output=long_video_output.get("relative_path"),
                    long_video=True,
                    duration_seconds=long_video_output.get("duration_seconds"),
                )
                return
        workflow, spec = _prepare_image_studio_workflow(
            lane,
            render_prompt,
            render_options,
        )
        _store_image_studio_workflow(job_id, workflow, spec, lane)
        cancel_event = IMAGE_STUDIO_JOBS[job_id]["cancel_event"]
        if not freed_for_kind and _image_studio_should_free_memory(spec.get("kind")):
            _set_image_studio_job(job_id, status="preparing", detail="Freeing ComfyUI model memory.")
            _image_studio_free_memory(timeout=30)
            if cancel_event.wait(1):
                _finish_image_studio_request(job_id, "cancelled", detail="Generation cancelled.")
                return
        candidate_grid = lane == "ideogram" and bool(
            render_options.get("candidate_grid")
        )
        candidate_identity = str(
            render_options.get("candidate_identity") or ""
        ).strip()
        candidate_labels = [
            candidate_identity or f"candidate {index + 1}"
            for index in range(4)
        ]
        max_attempts = 3 if lane == "ideogram" else 1
        for render_attempt in range(max_attempts):
            if render_attempt:
                render_prompt = _image_studio_ideogram_retry_prompt(prompt, render_attempt + 1)
                render_options["seed"] = secrets.randbelow(2**31 - 1)
                workflow, spec = _prepare_image_studio_workflow(lane, render_prompt, render_options)
                _store_image_studio_workflow(job_id, workflow, spec, lane)
                _set_image_studio_job(
                    job_id,
                    status="preparing",
                    detail=f"Ideogram blocked the prior variation; retrying {render_attempt + 1}/{max_attempts}.",
                )
            _set_image_studio_job(job_id, status="submitting", detail="Submitting workflow to ComfyUI.")
            ui_workflow = _image_studio_ui_workflow(workflow)
            response = _image_studio_json_request(
                "/prompt",
                {
                    "prompt": workflow,
                    "client_id": f"club3090-admin-{job_id}",
                    "extra_data": {"extra_pnginfo": {"workflow": ui_workflow, "prompt": workflow}},
                },
                timeout=60,
            )
            if response.get("node_errors"):
                raise RuntimeError("ComfyUI rejected the workflow: " + json.dumps(response["node_errors"])[:800])
            prompt_id = str(response.get("prompt_id") or "")
            if not prompt_id:
                raise RuntimeError("ComfyUI did not return a prompt id.")
            _set_image_studio_job(job_id, status="running", prompt_id=prompt_id, detail=f"{spec['label']} is rendering.")
            default_timeout = 1200
            if lane == "wan":
                _frames, _fps, _target_seconds, wan_segments = _image_studio_wan_segment_plan(render_prompt, render_options)
                wan_hi_res = _image_studio_wan_hi_res(render_prompt, render_options)
                default_timeout = max(default_timeout, int(wan_segments * (540 if wan_hi_res else 180) + 300))
            deadline = time.monotonic() + max(60, min(7200, int(options.get("timeout_seconds") or default_timeout)))
            retry_placeholder = False
            while time.monotonic() < deadline:
                if cancel_event.wait(2):
                    try:
                        _image_studio_json_request("/interrupt", {}, timeout=10)
                    except Exception:
                        pass
                    _finish_image_studio_request(job_id, "cancelled", detail="Generation cancelled.")
                    return
                history = _image_studio_json_request("/history/" + urllib.parse.quote(prompt_id), timeout=30)
                prompt_row = (history or {}).get(prompt_id) or {}
                status = prompt_row.get("status") or {}
                if status.get("status_str") == "error":
                    raise RuntimeError("ComfyUI reported a generation error.")
                if status.get("completed"):
                    output = _image_studio_output_from_history(history, prompt_id, spec["kind"])
                    if not output:
                        raise RuntimeError("ComfyUI completed without a usable output file.")
                    blocked_output = (
                        lane == "ideogram"
                        and _image_studio_ideogram_placeholder_detected(output)
                    )
                    if blocked_output:
                        _image_studio_delete_outputs([output])
                        log_audit(
                            "image_studio_ideogram_placeholder_retry",
                            job_id=job_id,
                            attempt=render_attempt + 1,
                            prompt_id=prompt_id,
                        )
                        if render_attempt + 1 < max_attempts:
                            retry_placeholder = True
                            break
                        raise RuntimeError(
                            "Ideogram returned blocked-placeholder images for every retry; no placeholder was saved."
                        )
                    if candidate_grid:
                        if _image_studio_extra_grid_divider_detected(output):
                            _image_studio_delete_outputs([output])
                            log_audit(
                                "image_studio_ideogram_nested_grid_retry",
                                job_id=job_id,
                                attempt=render_attempt + 1,
                                prompt_id=prompt_id,
                            )
                            if render_attempt + 1 < max_attempts:
                                retry_placeholder = True
                                break
                            raise RuntimeError(
                                "Ideogram returned nested or oversized candidate grids for every retry; no rejected image was saved."
                            )
                        grid_outputs = _image_studio_split_grid_output(
                            output,
                            candidate_labels,
                        )
                        usable_outputs = [
                            item
                            for item in grid_outputs
                            if (
                                not _image_studio_ideogram_placeholder_detected(item)
                                and not _image_studio_internal_panel_divider_detected(item)
                            )
                        ]
                        selected_output, director_accepted = (
                            _image_studio_director_pick_grid(
                                usable_outputs,
                                render_prompt,
                                candidate_identity,
                            )
                            if usable_outputs
                            else (None, False)
                        )
                        if not selected_output or not director_accepted:
                            _image_studio_delete_outputs([output, *grid_outputs])
                            log_audit(
                                "image_studio_ideogram_grid_retry",
                                job_id=job_id,
                                attempt=render_attempt + 1,
                                prompt_id=prompt_id,
                                crop_count=len(grid_outputs),
                                usable_crop_count=len(usable_outputs),
                                director_accepted=director_accepted,
                            )
                            if render_attempt + 1 < max_attempts:
                                retry_placeholder = True
                                break
                            raise RuntimeError(
                                "Ideogram candidate grids had no acceptable Director-selected crop after every retry; no rejected image was saved."
                            )
                        selected_path = _image_studio_output_abs_path(
                            selected_output
                        )
                        _image_studio_delete_outputs([
                            output,
                            *[
                                item
                                for item in grid_outputs
                                if _image_studio_output_abs_path(item)
                                != selected_path
                            ],
                        ])
                        output = selected_output
                    if lane in IMAGE_STUDIO_VIDEO_LANES:
                        output = _image_studio_trim_video_output(
                            output,
                            _image_studio_video_target_seconds(prompt, render_options),
                        )
                    _finish_image_studio_request(
                        job_id,
                        "success",
                        detail=f"{spec['label']} generation complete.",
                        output=output,
                    )
                    log_audit(
                        "image_studio_generation_complete",
                        lane=lane,
                        job_id=job_id,
                        output=output.get("relative_path"),
                    )
                    return
            if retry_placeholder:
                continue
            raise TimeoutError("ComfyUI generation timed out.")
    except Exception as exc:
        if isinstance(exc, InterruptedError):
            _finish_image_studio_request(job_id, "cancelled", detail="Generation cancelled.")
            log_audit("image_studio_generation_cancelled", lane=lane, job_id=job_id)
            return
        if lane not in {"voice", "kokoro"}:
            with IMAGE_STUDIO_JOB_LOCK:
                image_studio_comfy_model_cache["kind"] = ""
            try:
                _image_studio_free_memory(timeout=30)
            except Exception:
                pass
        _finish_image_studio_request(job_id, "failed", error=str(exc), detail=str(exc))
        log_audit("image_studio_generation_failed", lane=lane, job_id=job_id, error=str(exc))


def _run_image_studio_backend_plan_job(job_id, production_job_id, timeout_seconds):
    try:
        cancel_event = IMAGE_STUDIO_JOBS[job_id]["cancel_event"]
        payload_meta = dict(IMAGE_STUDIO_JOBS[job_id].get("production_payload_meta") or {})
        deadline = time.monotonic() + max(300, min(21600, int(timeout_seconds or 7200)))
        last_phase = ""
        last_state = ""
        last_progress = -1.0
        while time.monotonic() < deadline:
            if cancel_event.wait(2):
                _finish_image_studio_request(job_id, "cancelled", detail="Backend Plan Mode cancellation requested.")
                return
            status = _image_studio_production_json_request(
                "/job/" + urllib.parse.quote(str(production_job_id or "")),
                timeout=15,
            )
            state = str(status.get("status") or "running").strip().lower()
            phase = str(status.get("phase") or state or "Backend Plan Mode is running.").strip()
            progress = float(status.get("frac") or 0.0) if status.get("frac") is not None else 0.0
            if phase != last_phase or state != last_state or abs(progress - last_progress) >= 0.005:
                _set_image_studio_job(
                    job_id,
                    status="running" if state in {"planning", "rendering"} else state or "running",
                    detail=phase,
                    progress=progress,
                    production_status=status,
                )
                last_phase = phase
                last_state = state
                last_progress = progress
            if state == "done":
                output = _image_studio_output_from_production_status(status)
                if output and not payload_meta.get("audio_requested"):
                    final_path = str(
                        status.get("final")
                        or status.get("final_path")
                        or status.get("output")
                        or ""
                    ).strip()
                    if final_path and os.path.isfile(final_path):
                        silent_path = os.path.join(
                            os.path.dirname(final_path),
                            os.path.splitext(os.path.basename(final_path))[0] + ".no-audio.mp4",
                        )
                        output = _image_studio_output_for_local_path(_image_studio_strip_audio(final_path, silent_path), "video")
                _finish_image_studio_request(
                    job_id,
                    "success",
                    detail="Backend Plan Mode production complete.",
                    output=output,
                    production_status=status,
                )
                log_audit("image_studio_backend_plan_complete", job_id=job_id, production_job_id=production_job_id)
                return
            if state == "error":
                output = _image_studio_backend_plan_recover_visual_output(
                    production_job_id,
                    bool(payload_meta.get("audio_requested")),
                )
                if output:
                    _finish_image_studio_request(
                        job_id,
                        "success",
                        detail="Backend Plan Mode production complete.",
                        output=output,
                        production_status=status,
                    )
                    log_audit(
                        "image_studio_backend_plan_complete",
                        job_id=job_id,
                        production_job_id=production_job_id,
                        recovered_visual_only=True,
                    )
                    return
                raise RuntimeError(str(status.get("error") or "Backend Plan Mode production failed."))
        raise TimeoutError("Backend Plan Mode production timed out.")
    except Exception as exc:
        _finish_image_studio_request(job_id, "failed", error=str(exc), detail=str(exc))
        log_audit("image_studio_backend_plan_failed", job_id=job_id, production_job_id=production_job_id, error=str(exc))


def start_image_studio_backend_plan(data):
    if benchmark_job_active():
        raise RuntimeError("AI Studio is disabled while Model Scores benchmarking is active.")
    prompt = str((data or {}).get("prompt") or "").strip()
    if not prompt:
        raise ValueError("Enter a prompt for backend Plan Mode.")
    if len(prompt) > 20000:
        raise ValueError("Backend Plan Mode prompt is too large.")
    attachments = list((data or {}).get("attachments") or [])
    if attachments:
        raise ValueError("Backend Plan Mode does not use attachments yet.")
    status = image_studio_backend_plan_status()
    if not status.get("ready"):
        raise RuntimeError("Backend Plan Mode is not ready. Run Setup AI Studio or Start AI Studio and wait for the Production service.")
    with IMAGE_STUDIO_JOB_LOCK:
        direct_active = any(
            row.get("status") not in {"success", "failed", "cancelled"}
            for row in IMAGE_STUDIO_JOBS.values()
        )
    if direct_active or image_studio_activity_active(max_age=0):
        raise RuntimeError("Another AI Studio generation is already active. Wait for it to finish or cancel it first.")
    options = dict((data or {}).get("options") or {})
    payload, payload_meta = _image_studio_backend_plan_payload(prompt, options, status)
    response = _image_studio_production_json_request("/produce", payload, timeout=30)
    production_job_id = str(response.get("job_id") or "").strip()
    if not production_job_id:
        raise RuntimeError("Backend Plan Mode did not return a production job id.")
    job_id = secrets.token_hex(12)
    row = {
        "id": job_id,
        "lane": "plan-backend",
        "label": "Plan Mode (Backend)",
        "kind": "video",
        "status": "queued",
        "detail": "Backend Plan Mode queued.",
        "prompt": prompt,
        "created_at": int(time.time()),
        "finished_at": 0,
        "error": "",
        "output": None,
        "production_job_id": production_job_id,
        "production_payload": payload,
        "production_payload_meta": payload_meta,
        "production_status": response,
        "cancel_event": threading.Event(),
    }
    with IMAGE_STUDIO_JOB_LOCK:
        IMAGE_STUDIO_JOBS[job_id] = row
        image_studio_runtime_cache["checked_at"] = 0.0
        image_studio_activity_cache.update(checked_at=time.time(), active=True)
    with metrics_lock:
        metrics["total_requests"] = int(metrics.get("total_requests", 0) or 0) + 1
        metrics["active_requests"] = int(metrics.get("active_requests", 0) or 0) + 1
        metrics["last_status"] = "queued"
        metrics["last_path"] = "ai-studio:plan-backend"
        metrics["last_request_at"] = int(time.time())
    thread = threading.Thread(
        target=_run_image_studio_backend_plan_job,
        args=(job_id, production_job_id, int(options.get("timeout_seconds") or 7200)),
        daemon=True,
    )
    row["thread"] = thread
    thread.start()
    log_audit("image_studio_backend_plan_started", job_id=job_id, production_job_id=production_job_id)
    return _image_studio_job_public(row)


def start_image_studio_generation(data):
    if benchmark_job_active():
        raise RuntimeError("AI Studio is disabled while Model Scores benchmarking is active.")
    lane = str((data or {}).get("lane") or "ideogram").strip().lower()
    prompt = str((data or {}).get("prompt") or "").strip()
    prior_prompt = str((data or {}).get("prior_prompt") or "").strip()
    if lane not in IMAGE_STUDIO_LANES:
        raise ValueError("Unsupported AI Studio lane.")
    if not prompt:
        raise ValueError("Enter a generation prompt.")
    if len(prompt) > 20000:
        raise ValueError("Generation prompt is too large.")
    if prior_prompt:
        prompt = f"{prior_prompt}\n\nRequested refinement: {prompt}"
    attachments = list((data or {}).get("attachments") or [])
    if lane not in IMAGE_STUDIO_VIDEO_LANES and lane != "voice" and attachments:
        raise ValueError("Attachments are currently supported by video and voice Studio lanes.")
    if lane in IMAGE_STUDIO_VIDEO_LANES and any(str(row.get("kind") or "") != "image" for row in attachments):
        raise ValueError("Video lanes accept one image attachment for image-to-video.")
    if lane == "voice" and any(str(row.get("kind") or "") != "audio" for row in attachments):
        raise ValueError("Voice Studio accepts one audio reference attachment.")
    missing_models = _image_studio_optional_models_ready(lane)
    if missing_models:
        raise RuntimeError(
            f"{IMAGE_STUDIO_LANES[lane]['label']} is not installed. Download its model assets from AI Studio first."
        )
    with IMAGE_STUDIO_JOB_LOCK:
        direct_active = any(
            row.get("status") not in {"success", "failed", "cancelled"}
            for row in IMAGE_STUDIO_JOBS.values()
        )
    if direct_active or image_studio_activity_active(max_age=0):
        raise RuntimeError("Another AI Studio generation is already active. Wait for it to finish or cancel it first.")
    if lane not in {"voice", "kokoro"}:
        _image_studio_ensure_comfyui_running(timeout=180)
        try:
            _image_studio_json_request("/system_stats", timeout=5)
        except Exception as exc:
            raise RuntimeError("ComfyUI is not ready yet. Check Script logs for first-boot setup progress.") from exc
    ensure_ai_studio_runtime_power("ai_studio_generation", force=True)
    job_id = secrets.token_hex(12)
    row = {
        "id": job_id,
        "lane": lane,
        "label": IMAGE_STUDIO_LANES[lane]["label"],
        "kind": IMAGE_STUDIO_LANES[lane]["kind"],
        "status": "queued",
        "detail": "Generation queued.",
        "prompt": prompt,
        "created_at": int(time.time()),
        "finished_at": 0,
        "error": "",
        "output": None,
        "cancel_event": threading.Event(),
    }
    with IMAGE_STUDIO_JOB_LOCK:
        IMAGE_STUDIO_JOBS[job_id] = row
        image_studio_runtime_cache["checked_at"] = 0.0
        image_studio_activity_cache.update(checked_at=time.time(), active=True)
        terminal = sorted(
            (item for item in IMAGE_STUDIO_JOBS.values() if item.get("status") in {"success", "failed", "cancelled"}),
            key=lambda item: int(item.get("finished_at") or item.get("created_at") or 0),
        )
        for old in terminal[:-IMAGE_STUDIO_JOB_LIMIT]:
            IMAGE_STUDIO_JOBS.pop(old.get("id"), None)
    with metrics_lock:
        metrics["total_requests"] = int(metrics.get("total_requests", 0) or 0) + 1
        metrics["active_requests"] = int(metrics.get("active_requests", 0) or 0) + 1
        metrics["last_status"] = "queued"
        metrics["last_path"] = f"ai-studio:{lane}"
        metrics["last_request_at"] = int(time.time())
    options = dict((data or {}).get("options") or {})
    options["attachments"] = attachments
    thread = threading.Thread(target=_run_image_studio_job, args=(job_id, lane, prompt, options), daemon=True)
    row["thread"] = thread
    thread.start()
    try:
        refresh_status_snapshot()
    except Exception as exc:
        log_control(f"AI Studio start status refresh failed: {exc}")
    log_audit("image_studio_generation_started", lane=lane, job_id=job_id)
    return _image_studio_job_public(row)


def image_studio_generation_status(job_id):
    with IMAGE_STUDIO_JOB_LOCK:
        row = IMAGE_STUDIO_JOBS.get(str(job_id or ""))
        if not row:
            raise ValueError("Unknown AI Studio generation job.")
        return _image_studio_job_public(row)


def cancel_image_studio_generation(job_id):
    with IMAGE_STUDIO_JOB_LOCK:
        row = IMAGE_STUDIO_JOBS.get(str(job_id or ""))
        if not row:
            raise ValueError("Unknown AI Studio generation job.")
        if row.get("status") not in {"success", "failed", "cancelled"}:
            row["cancel_event"].set()
            row["detail"] = "Cancellation requested."
        return _image_studio_job_public(row)
