# Upstream script discovery and scoped script runner.

SCRIPT_RUNS_DIR = os.path.join(CONTROL_DIR, "script-runs")
SCRIPT_STATE_FILE = os.path.join(SCRIPT_RUNS_DIR, "state.json")
SCRIPT_LOG_TAIL_LINES = 500
AI_STUDIO_EXTENSION_PAYLOAD_GZIP_BASE64 = ""  # Injected by build.py for shipped outputs.

script_job_lock = threading.RLock()
script_worker_thread = None
script_process = None


def ensure_script_dirs():
    os.makedirs(SCRIPT_RUNS_DIR, exist_ok=True)


def default_script_job_state():
    return {
        "schema_version": 2,
        "active": False,
        "job_id": "",
        "status": "idle",
        "summary": "",
        "script_id": "",
        "script_path": "",
        "label": "",
        "command": "",
        "instance_id": "",
        "mode": "",
        "container": "",
        "url": "",
        "started_at": "",
        "finished_at": "",
        "return_code": None,
        "log_file": "",
        "log_tail": [],
        "queue": [],
    }


def read_script_job_state():
    ensure_script_dirs()
    state = read_json_file(SCRIPT_STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}
    base = default_script_job_state()
    base.update(state)
    if not isinstance(base.get("log_tail"), list):
        base["log_tail"] = []
    if not isinstance(base.get("queue"), list):
        base["queue"] = []
    base["queue"] = [dict(row) for row in base["queue"] if isinstance(row, dict)]
    return base


def write_script_job_state(state):
    ensure_script_dirs()
    payload = default_script_job_state()
    payload.update(dict(state or {}))
    write_json_file(SCRIPT_STATE_FILE, payload)
    return payload


def script_job_snapshot():
    state = reconcile_script_job_state(read_script_job_state(), persist=True)
    for row in state.get("queue") or []:
        status = str(row.get("status") or "")
        row["progress"] = 0.5 if status == "running" else (1.0 if status in {"success", "failed", "cancelled"} else 0.0)
    log_file = str(state.get("log_file") or "").strip()
    if log_file and os.path.exists(log_file):
        state["log_tail"] = query_text_log_file(log_file, tail_lines=SCRIPT_LOG_TAIL_LINES).splitlines()[-SCRIPT_LOG_TAIL_LINES:]
    return state


def script_queue_job(state, job_id):
    wanted = str(job_id or "").strip()
    if not wanted:
        return {}
    return next((dict(row) for row in (state.get("queue") or []) if str(row.get("job_id") or "") == wanted), {})


def script_current_log_file(job_id=""):
    state = read_script_job_state()
    row = script_queue_job(state, job_id)
    log_file = str((row or state).get("log_file") or "").strip()
    if log_file:
        return log_file
    return os.path.join(SCRIPT_RUNS_DIR, "script.log")


def script_log_snapshot(job_id="", tail_lines=500):
    state = read_script_job_state()
    requested = str(job_id or "").strip()
    row = script_queue_job(state, requested) or state
    log_file = script_current_log_file(requested)
    return {
        "source": "script",
        "signature": f"script:{requested or row.get('job_id') or 'latest'}",
        "text": query_text_log_file(log_file, tail_lines=tail_lines) if log_file and os.path.exists(log_file) else "no script output yet; waiting...\n",
        "label": str(row.get("label") or row.get("script_id") or "Script"),
        "script_id": str(row.get("script_id") or ""),
        "job_id": str(row.get("job_id") or requested),
        "preset": str(row.get("mode") or ""),
        "progress": 0.5 if row.get("status") == "running" else (1.0 if row.get("status") in {"success", "failed", "cancelled"} else 0.0),
        "active": str(row.get("status") or "") == "running",
    }


def script_discovery_root():
    return os.path.join(CLUB3090_DIR, "scripts")


def script_doc_candidates(script_path):
    stem = os.path.splitext(os.path.basename(script_path))[0].lower().replace("_", "-")
    docs_dir = os.path.join(CLUB3090_DIR, "docs")
    candidates = []
    if os.path.isdir(docs_dir):
        for root, _dirs, files in os.walk(docs_dir):
            for name in files:
                lower = name.lower()
                if not lower.endswith((".md", ".txt", ".rst")):
                    continue
                path = os.path.join(root, name)
                token = os.path.splitext(lower)[0].replace("_", "-")
                if stem in token or token in stem or (stem.startswith("quality") and "quality" in token):
                    candidates.append(path)
    if stem.startswith("quality"):
        quality = os.path.join(docs_dir, "QUALITY_TEST.md")
        if os.path.exists(quality) and quality not in candidates:
            candidates.insert(0, quality)
    rows = []
    for path in candidates[:4]:
        abs_path = os.path.realpath(os.path.abspath(path))
        rel = os.path.relpath(abs_path, os.path.realpath(os.sep)).replace("\\", "/")
        rows.append({
            "path": abs_path,
            "root_path": os.path.realpath(os.sep),
            "relative_path": rel,
            "label": os.path.basename(abs_path),
        })
    return rows


def script_read_head(path, max_chars=200000):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(max_chars)
    except Exception:
        return ""


def script_extract_description(text, name):
    lines = []
    for raw in str(text or "").splitlines()[:80]:
        line = raw.strip()
        if line.startswith("#!"):
            continue
        if line.startswith("#"):
            line = line.lstrip("#").strip()
        elif line.startswith(":") or line.startswith("set ") or line.startswith("function "):
            continue
        elif lines:
            break
        else:
            continue
        if line:
            lines.append(line)
        if len(" ".join(lines)) > 220:
            break
    if lines:
        return " ".join(lines)[:260]
    lower = str(name or "").lower()
    if "quality" in lower:
        return "Runs quality and instruction-following prompts against the selected local endpoint."
    if "bench" in lower:
        return "Measures runtime throughput, latency, and token-generation behavior."
    if "verify" in lower:
        return "Runs endpoint and model-response verification checks."
    if "report" in lower:
        return "Collects runtime, container, and model configuration diagnostics."
    if "soak" in lower:
        return "Exercises repeated sessions to look for stability regressions."
    return "Upstream Club-3090 maintenance or diagnostic script."


SCRIPT_OPTION_DESCRIPTION_HINTS = {
    "--help": "Show the script's built-in usage and option help.",
    "--quick": "Run the short/fast benchmark or quality pack variant.",
    "--full": "Run the complete benchmark or quality pack variant.",
    "--reasoning": "Run the reasoning-focused benchmark pack.",
    "--endpoint": "Override the OpenAI-compatible endpoint URL used by the script.",
    "--model": "Override the served model name sent to the endpoint.",
    "--timeout": "Set the request or script timeout budget.",
    "--yes": "Automatically accept prompts that would otherwise require confirmation.",
    "--force": "Force the operation even when the script detects a cautious default path.",
    "--force-download": "Proceed with a low-confidence or advisory custom-model download path.",
    "--trust-remote-code": "Allow model repositories that require custom remote Python code.",
    "--experimental-arch": "Allow an experimental or not-yet-formally-mapped model architecture.",
    "--hf-home": "Override the Hugging Face cache root used by the script.",
    "--sm": "Override the detected CUDA streaming multiprocessor capability.",
    "--gpus": "Override the detected GPU topology or VRAM hints.",
}


def script_option_description_from_source(option, text):
    pattern = re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(option)}(?![A-Za-z0-9_-])")
    for raw in str(text or "").splitlines()[:220]:
        if not pattern.search(raw):
            continue
        line = raw.strip().strip("\"'`")
        line = re.sub(r"^[#*;\s-]+", "", line).strip()
        line = re.sub(r"^echo\s+['\"]?", "", line).strip()
        line = line.replace("\\t", " ").replace("\\n", " ")
        line = re.sub(r"\s+", " ", line)
        if not line or line.startswith(("if ", "elif ", "case ", "for ", "while ")):
            continue
        if "#" in line:
            before, after = line.split("#", 1)
            if pattern.search(before) and after.strip():
                line = after.strip()
            else:
                line = pattern.sub("", line).strip(" :=,-)")
        else:
            line = pattern.sub("", line).strip(" :=,-)")
        line = re.sub(r"^(?:bash\s+)?scripts/[A-Za-z0-9_./-]+(?:\.sh|\.py)?\s*", "", line).strip()
        line = re.sub(r"^(?:[A-Z][A-Z0-9_-]*|<[^>]+>|\[[^]]+\])\s+", "", line).strip()
        line = re.sub(r"^\[[^]]+\]\s*", "", line).strip()
        if len(line) >= 12 and not re.fullmatch(r"[A-Za-z0-9_./=-]+", line):
            return line[:180]
    return ""


def script_option_source_text(text):
    def looks_like_help_output_line(line):
        stripped_line = str(line or "").strip()
        if not stripped_line:
            return False
        if re.match(r"^(?:echo|printf)\b", stripped_line):
            return True
        stripped_line = stripped_line.strip("\"'`")
        return bool(re.match(r"^(?:--|-|USAGE\b|OPTIONS\b|MODES\b|EXAMPLES\b|Usage\b|Options\b|Modes\b|Examples\b)", stripped_line))

    source_lines = []
    raw_lines = str(text or "").splitlines()[:260]
    in_leading_comments = True
    in_help_heredoc = False
    heredoc_marker = ""
    help_context = []
    for raw in raw_lines:
        stripped = raw.strip()
        if in_help_heredoc:
            if stripped == heredoc_marker:
                in_help_heredoc = False
                heredoc_marker = ""
                continue
            source_lines.append(raw)
            continue
        if stripped.startswith("#!"):
            continue
        if in_leading_comments and (not stripped or stripped.startswith("#")):
            if stripped.startswith("#"):
                source_lines.append(re.sub(r"^#\s?", "", stripped))
            continue
        if in_leading_comments:
            in_leading_comments = False
        help_context.append(raw)
        help_context = help_context[-6:]
        heredoc = re.search(r"<<-?\s*['\"]?([A-Za-z0-9_./-]+)['\"]?", raw)
        if heredoc and re.search(r"\b(usage|help|print_help)\b|USAGE|OPTIONS|MODES", "\n".join(help_context), re.I):
            heredoc_marker = heredoc.group(1)
            in_help_heredoc = True
            continue
        if re.search(r"\b(usage|options|modes|examples)\b", raw, re.I) or re.search(r"(?<![A-Za-z0-9_-])--[A-Za-z][A-Za-z0-9_-]*", raw):
            if stripped.startswith("#"):
                source_lines.append(re.sub(r"^#\s?", "", stripped))
            elif looks_like_help_output_line(raw) and re.search(r"\b(usage|help|print_help)\b|USAGE|OPTIONS|MODES", "\n".join(help_context), re.I):
                source_lines.append(raw)
    return "\n".join(source_lines)


def script_extract_options(text):
    options = []
    seen = set()
    option_text = script_option_source_text(text)
    for match in re.finditer(r"(?<![A-Za-z0-9_-])--[A-Za-z][A-Za-z0-9_-]*", option_text):
        option = match.group(0)
        if option in seen:
            continue
        seen.add(option)
        description = script_option_description_from_source(option, option_text) or SCRIPT_OPTION_DESCRIPTION_HINTS.get(option)
        if not description:
            label = option.lstrip("-").replace("-", " ")
            description = f"Controls the script's {label} behavior; open More Info to inspect the exact upstream usage."
        options.append({"name": option, "description": description})
        if len(options) >= 40:
            break
    return options


def script_discovery_row(root, path, internal=False):
    name = os.path.basename(path)
    lower = name.lower()
    rel = os.path.relpath(path, root).replace("\\", "/")
    text = script_read_head(path)
    docs = script_doc_candidates(path)
    description = script_extract_description(text, name)
    options = script_extract_options(text)
    if not internal and description == "Upstream Club-3090 maintenance or diagnostic script." and not options:
        internal = True
    return {
        "id": rel,
        "name": name,
        "label": os.path.splitext(name)[0].replace("-", " ").replace("_", " ").title(),
        "path": path,
        "relative_path": rel,
        "description": description,
        "options": options,
        "docs": docs,
        "kind": "python" if lower.endswith(".py") else "shell",
        "internal": bool(internal),
    }


def discover_upstream_scripts(include_internal=False):
    root = script_discovery_root()
    rows = []
    if not os.path.isdir(root):
        return rows
    seen = set()
    for name in sorted(os.listdir(root)):
        if name.startswith(".") or not name.lower().endswith(".sh"):
            continue
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        rows.append(script_discovery_row(root, path, internal=False))
        seen.add(os.path.normpath(path))
    if include_internal:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [name for name in dirs if not name.startswith(".") and name not in {"__pycache__", "node_modules"}]
            for name in sorted(files):
                lower = name.lower()
                if not lower.endswith((".sh", ".py")):
                    continue
                path = os.path.normpath(os.path.join(dirpath, name))
                if path in seen:
                    continue
                rows.append(script_discovery_row(root, path, internal=True))
                seen.add(path)
    rows.sort(key=lambda row: (1 if row.get("internal") else 0, str(row.get("label") or row.get("name") or row.get("relative_path") or "").lower(), str(row.get("relative_path") or "").lower()))
    return rows


def resolve_upstream_script(script_id):
    wanted = str(script_id or "").strip().replace("\\", "/")
    if not wanted:
        raise ValueError("script_id is required")
    for row in discover_upstream_scripts(include_internal=True):
        if row.get("id") == wanted:
            return row
    raise ValueError(f"Unknown upstream script: {script_id}")


def normalize_script_args(args):
    if isinstance(args, list):
        return [str(item) for item in args if str(item or "").strip()]
    text = str(args or "").strip()
    if not text:
        return []
    return shlex.split(text)


def script_runtime_context(instance_id=""):
    try:
        return _resolve_admin_task_context(instance_id)
    except Exception:
        return {"instance_id": str(instance_id or "").strip().upper() or "GLOBAL", "mode": "", "container": "", "url": "", "served_model_name": "", "engine": ""}


def script_command_for(row, args):
    path = str(row.get("path") or "")
    quoted_path = shlex.quote(path)
    suffix = " ".join(shlex.quote(str(arg)) for arg in normalize_script_args(args))
    if row.get("kind") == "python":
        base = f"python3 {quoted_path}"
    else:
        base = f"bash {quoted_path}"
    return f"{base} {suffix}".strip()


def image_studio_extension_install_snippet():
    payload = str(AI_STUDIO_EXTENSION_PAYLOAD_GZIP_BASE64 or "")
    if not payload:
        return """
echo "[ai-studio] ERROR: AI Studio extension payload is missing from the control backend" >&2
exit 1
"""
    quoted_payload = shlex.quote(payload)
    return f"""
echo "[ai-studio] installing Club-3090 ComfyUI workflow preview extension"
CLUB3090_CONTROL_DIR="${{CLUB3090_CONTROL_DIR:-/opt/club3090-control}}"
AI_STUDIO_EXTENSION_ROOT="$CLUB3090_CONTROL_DIR/extensions"
sudo mkdir -p "$AI_STUDIO_EXTENSION_ROOT"
sudo env AI_STUDIO_EXTENSION_PAYLOAD={quoted_payload} python3 - "$AI_STUDIO_EXTENSION_ROOT" <<'PYEXT'
import base64, gzip, json, os, sys
root = os.path.abspath(sys.argv[1])
payload = os.environ.get("AI_STUDIO_EXTENSION_PAYLOAD", "")
files = json.loads(gzip.decompress(base64.b64decode(payload.encode("ascii"))).decode("utf-8"))
for rel, text in files.items():
    rel = rel.replace("\\\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise SystemExit(f"unsafe extension path: {{rel}}")
    target = os.path.abspath(os.path.join(root, rel))
    if not target.startswith(root + os.sep):
        raise SystemExit(f"extension path escaped root: {{rel}}")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\\n") as handle:
        handle.write(text)
PYEXT
sudo mkdir -p /mnt/models/comfyui/ComfyUI/custom_nodes
sudo rm -rf /mnt/models/comfyui/ComfyUI/custom_nodes/club3090_workflow_preview
sudo cp -a "$AI_STUDIO_EXTENSION_ROOT/comfyui-club3090-preview" /mnt/models/comfyui/ComfyUI/custom_nodes/club3090_workflow_preview
sudo chmod -R a+rX /mnt/models/comfyui/ComfyUI/custom_nodes/club3090_workflow_preview
"""


def ai_studio_runtime_compat_snippet():
    return r"""
echo "[ai-studio] applying Club-3090 AI Studio runtime compatibility defaults"
sudo python3 - <<'PYSTUDIO'
import os
from pathlib import Path

env_path = Path(".env")

def existing_env_value(key):
    prefix = key + "="
    if not env_path.exists():
        return ""
    for line in reversed(env_path.read_text(encoding="utf-8").splitlines()):
        if line.startswith(prefix):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

def set_env_value(key, value):
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    prefix = key + "="
    row = f"{key}={value}"
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = row
            break
    else:
        lines.append(row)
    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")

def set_env_default(key, value):
    if not existing_env_value(key):
        set_env_value(key, value)

# v0.10+ reads STUDIO_DIRECTOR_DEVICE in gpu-mode and derives the compose env
# from there. We default to our control-layer auto policy: fast GPU placement
# for planning, with CPU relocation only when a media lane needs the VRAM.
requested_director_device = os.environ.get("STUDIO_DIRECTOR_DEVICE", "").strip().lower()
existing_director_device = existing_env_value("STUDIO_DIRECTOR_DEVICE").lower()
if requested_director_device:
    set_env_value("STUDIO_DIRECTOR_DEVICE", requested_director_device)
elif existing_director_device in {"", "cpu"}:
    set_env_value("STUDIO_DIRECTOR_DEVICE", "auto")
else:
    set_env_default("STUDIO_DIRECTOR_DEVICE", "auto")
if existing_env_value("STUDIO_DIRECTOR_DEVICE").lower() == "cpu":
    set_env_value("STUDIO_DIRECTOR_GPU_LAYERS", "0")
    set_env_value("DIRECTOR_NGL", "0")
    set_env_value("STUDIO_DIRECTOR_CUDA", "")
PYSTUDIO

apply_ai_studio_director_healthcheck_override() {
  local compose_file="services/studio/enhancer/docker-compose.yml"
  if [ ! -f "$compose_file" ]; then
    return 0
  fi
  if ! sudo docker inspect studio-director >/dev/null 2>&1; then
    return 0
  fi
  local override_dir="/opt/club3090-control/compose-overrides"
  local override_file="$override_dir/studio-director-healthcheck.override.yml"
  sudo mkdir -p "$override_dir"
  sudo tee "$override_file" >/dev/null <<'YAML'
services:
  studio-director:
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS --max-time 3 http://127.0.0.1:${STUDIO_DIRECTOR_PORT:-8090}/v1/models >/dev/null"]
      interval: 15s
      timeout: 5s
      retries: 20
      start_period: 20s
YAML
  local director_cuda=""
  local director_gpu=""
  director_cuda="$(sudo docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' studio-director 2>/dev/null | sed -n 's/^CUDA_VISIBLE_DEVICES=//p' | tail -n 1 || true)"
  director_gpu="$(sudo docker inspect -f '{{range .HostConfig.DeviceRequests}}{{range .DeviceIDs}}{{println .}}{{end}}{{end}}' studio-director 2>/dev/null | head -n 1 || true)"
  director_gpu="${director_gpu:-${STUDIO_DIRECTOR_GPU:-0}}"
  local director_ngl="${DIRECTOR_NGL:-99}"
  if [ -z "$director_cuda" ]; then
    director_ngl="0"
  fi
  local env_file_args=()
  if [ -f .env ]; then
    env_file_args=(--env-file .env)
  fi
  echo "[ai-studio] applying Studio Director healthcheck override on :${STUDIO_DIRECTOR_PORT:-8090}"
  sudo env \
    HOME="$HOME" \
    PATH="$PATH" \
    MODEL_DIR="${MODEL_DIR:-$PWD/models-cache}" \
    STUDIO_DIRECTOR_CUDA="$director_cuda" \
    STUDIO_DIRECTOR_GPU="$director_gpu" \
    DIRECTOR_NGL="$director_ngl" \
    DIRECTOR_THINK_ARGS="${DIRECTOR_THINK_ARGS:-}" \
    STUDIO_DIRECTOR_PORT="${STUDIO_DIRECTOR_PORT:-8090}" \
    docker compose "${env_file_args[@]}" --project-directory services/studio/enhancer -f "$compose_file" -f "$override_file" up -d --force-recreate studio-director
}
"""


def ai_studio_docker_headroom_snippet():
    return r"""
require_compose_docker_pull_space() {
  local label="$1"
  local compose_dir="$2"
  local compose_file="$3"
  local may_build="${4:-0}"
  shift 4 || true
  local control_py="${CONTROL_PY:-/opt/club3090-control/control.py}"
  sudo env HOME="$HOME" PATH="$PATH" "$@" python3 "$control_py" --docker-compose-pull-space-preflight "$label" "$compose_dir" "$may_build" "$compose_file"
}
"""


def ai_studio_production_service_snippet():
    return r"""
start_ai_studio_production_service() {
  if [ ! -f services/studio/production/server.py ]; then
    return 0
  fi
  local port="${STUDIO_PRODUCTION_PORT:-8195}"
  local output_root="${COMFYUI_OUTPUT_DIR:-${COMFYUI_MODELS_ROOT:-$PWD/ai-studio-models/comfyui}/output}"
  local workflow_dir="${STUDIO_WORKFLOW_DIR:-$PWD/services/studio/workflows}"
  local pidfile="$output_root/studio-production.pid"
  local logfile="$output_root/studio-production.log"
  local unit="club3090-studio-production.service"
  local patch_dir="/opt/club3090-control/studio-production-patches"
  local production_pythonpath="$patch_dir:$PWD${PYTHONPATH:+:$PYTHONPATH}"
  sudo mkdir -p "$output_root"
  sudo mkdir -p "$patch_dir"
  sudo tee "$patch_dir/sitecustomize.py" >/dev/null <<'PY'
# Control-owned runtime compatibility shims for upstream Studio Production.
#
# This file is loaded through PYTHONPATH when club3090-studio-production starts.
# It deliberately lives outside the upstream checkout so migrations can replace
# services/studio freely while the admin server keeps its production guarantees.
from __future__ import annotations

import re


_DAMAGE_WORDS = (
    "crack",
    "cracks",
    "cracked",
    "cracking",
    "damage",
    "damaged",
    "broken",
    "break",
    "breaks",
    "scratch",
    "scratches",
    "scratched",
    "mark",
    "marks",
    "markings",
    "debris",
    "shattered",
    "fractured",
)
_TEXT_WORDS = (
    "text",
    "letter",
    "letters",
    "logo",
    "logos",
    "label",
    "labels",
    "caption",
    "captions",
    "subtitle",
    "subtitles",
    "watermark",
    "watermarks",
    "sign",
    "signs",
    "signage",
    "writing",
    "typography",
    "title card",
    "title cards",
    "credits",
    "lower third",
    "lower thirds",
)
_EXTRA_OBJECT_WORDS = (
    "water",
    "drop",
    "drops",
    "droplet",
    "droplets",
    "liquid",
    "paint",
    "ink",
    "nozzle",
    "tube",
    "pipe",
    "stream",
    "pour",
    "pours",
    "pouring",
    "ripple",
    "ripples",
    "smoke",
    "fog",
    "mist",
    "vapor",
    "spark",
    "sparks",
    "flame",
    "flames",
    "dust",
    "debris",
    "hand",
    "hands",
    "tool",
    "tools",
    "wire",
    "wires",
    "rod",
    "needle",
)
_GEOMETRIC_OBJECT_WORDS = (
    "cube",
    "sphere",
    "ball",
    "cylinder",
    "cone",
    "pyramid",
    "prism",
    "torus",
    "ring",
    "capsule",
    "disc",
    "disk",
    "polyhedron",
    "geometric object",
    "geometric shape",
    "product object",
)
_CHARACTER_OR_LIVING_WORDS = (
    "person",
    "people",
    "human",
    "humans",
    "man",
    "woman",
    "child",
    "children",
    "portrait",
    "actor",
    "actress",
    "character",
    "creature",
    "animal",
    "dog",
    "cat",
    "bird",
    "horse",
    "face",
    "faces",
    "facial",
    "eyes",
    "eye",
    "mouth",
    "lips",
    "nose",
    "eyebrows",
    "expression",
    "hand",
    "hands",
    "arm",
    "arms",
    "body",
    "bodies",
    "limb",
    "limbs",
)
_SEGMENTED_SURFACE_WORDS = (
    "rubik",
    "rubik's",
    "puzzle",
    "segment",
    "segmented",
    "subdivided",
    "tiles",
    "tile",
    "panels",
    "panel",
    "grid",
    "blocks",
    "block",
    "markings",
    "symbols",
)
_PROMPT_FIDELITY_LTX_BASE_NEGATIVE = (
    "unrequested object",
    "extra object",
    "unrequested prop",
    "extra prop",
    "unrequested story beat",
)
_PROMPT_FIDELITY_LTX_CHARACTER_NEGATIVE = (
    "face",
    "faces",
    "facial features",
    "eyes",
    "eye",
    "mouth",
    "lips",
    "nose",
    "eyebrows",
    "expression",
    "character",
    "anthropomorphic",
    "cartoon face",
    "toy face",
    "person",
    "head",
    "limbs",
    "hands",
)
_PROMPT_FIDELITY_LTX_SEGMENTATION_NEGATIVE = (
    "seams",
    "panel lines",
    "panels",
    "tiles",
    "segmented object",
    "subdivided object",
    "rubik cube",
    "rubik's cube",
    "puzzle object",
    "block grid",
    "markings",
    "symbols",
)
_PROMPT_FIDELITY_LTX_EXTRA_NEGATIVE = (
    "water",
    "droplet",
    "nozzle",
    "paint stream",
    "text",
    "logo",
    "label",
    "watermark",
)


def _brief_requests_exact_minimal(brief: str) -> bool:
    text = str(brief or "").lower()
    return bool(re.search(
        r"\b(?:single|one|minimal|minimalist|plain|simple|only|exact(?:ly)?|preserve|avoid extra|no extra|nothing else)\b",
        text,
    ))


def _brief_allows(brief: str, words: tuple[str, ...]) -> bool:
    text = str(brief or "").lower()
    for word in words:
        if re.search(r"\b" + re.escape(word) + r"\b", text):
            before = text[max(0, text.find(word) - 32): text.find(word)]
            if not re.search(r"\b(?:no|without|avoid|exclude|forbid|forbids|forbidden|free of)\b", before):
                return True
    return False


def _user_brief_text(brief: str) -> str:
    text = str(brief or "")
    if "\n\n" in text:
        return text.split("\n\n", 1)[0]
    return text


def _clean_prompt_text(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"(?:[,;]\s*){2,}", ", ", text)
    text = re.sub(r"(?:\.\s*){2,}", ". ", text)
    return text.strip(" ,;")


def _strip_negated_visual_nouns(text: str, words: tuple[str, ...]) -> str:
    token = "|".join(re.escape(word) for word in words)
    # Replace common "uniform texture with no cracks" clauses with affirmative
    # surface language, then delete remaining negated absent-object sentences.
    text = re.sub(
        rf"\b(?:revealing|showing|displaying)\s+([^.!?\n]{{0,96}}?)\s+with\s+(?:no|without)\s+(?:any\s+)?[^.!?\n]*(?:{token})[^.!?\n]*(?:[.!?]|$)",
        r"revealing \1 with the requested surface quality. ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        rf"\b(?:with|showing|revealing)\s+(?:no|without)\s+(?:any\s+)?[^.!?\n]*(?:{token})[^.!?\n]*(?:[.!?]|$)",
        " with the requested surface quality. ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        rf"\b(?:no|without|avoid(?:ing)?|exclude|excluding|forbid(?:ding)?|free of)\b[^.!?\n]*(?:{token})[^.!?\n]*(?:[.!?]|$)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(rf"\b(?:{token})\b", "", text, flags=re.IGNORECASE)


def _strip_unrequested_extra_objects(text: str, brief: str) -> str:
    if not _brief_requests_exact_minimal(brief):
        return text
    blocked = tuple(word for word in _EXTRA_OBJECT_WORDS if not _brief_allows(brief, (word,)))
    if not blocked:
        return text
    token = "|".join(re.escape(word) for word in blocked)
    parts = re.split(r"(?<=[.!?])\s+", str(text or ""))
    kept = [
        part
        for part in parts
        if part and not re.search(rf"\b(?:{token})\b", part, re.IGNORECASE)
    ]
    return " ".join(kept)


def _mentions_any_allowed(text: str, words: tuple[str, ...]) -> bool:
    return _brief_allows(text, words)


def _sanitize_prompt_intent(prompt: str, brief: str) -> str:
    out = str(prompt or "")
    user_brief = _user_brief_text(brief)
    allow_damage = _brief_allows(user_brief, _DAMAGE_WORDS)
    allow_text = _brief_allows(user_brief, _TEXT_WORDS)
    if not allow_damage:
        before_damage = out
        out = _strip_negated_visual_nouns(out, _DAMAGE_WORDS)
        damage_clause_removed = before_damage != out
    else:
        damage_clause_removed = False
    if not allow_text:
        before_text = out
        out = _strip_negated_visual_nouns(out, _TEXT_WORDS)
        text_clause_removed = before_text != out
    else:
        text_clause_removed = False
    out = _strip_unrequested_extra_objects(out, user_brief)
    out = _clean_prompt_text(out)
    if _brief_requests_exact_minimal(user_brief) and not re.search(r"\b(?:only the requested|requested elements only|without unrequested|avoid unrequested)\b", out, re.IGNORECASE):
        out = (
            out.rstrip(". ")
            + ". Only the requested subject, requested attributes, setting, style, camera motion, lighting, duration, and explicitly requested inclusions or omissions should appear; avoid unrequested additions."
        ).strip()
    if damage_clause_removed and not re.search(r"\b(?:surface quality|material condition|faithful to the brief|as requested)\b", out, re.IGNORECASE):
        out = (out.rstrip(". ") + ". Requested surface quality and material condition remain faithful to the brief.").strip()
    if text_clause_removed and not re.search(r"\b(?:faithful to the brief|as requested|requested surfaces|requested backgrounds)\b", out, re.IGNORECASE):
        out = (out.rstrip(". ") + ". Requested surfaces, backgrounds, and graphic elements remain faithful to the brief.").strip()
    return _clean_prompt_text(out)


def _merge_negative_prompt(existing: str, extra: tuple[str, ...]) -> str:
    parts = []
    seen = set()
    for value in (str(existing or ""), ", ".join(extra)):
        for part in re.split(r"\s*,\s*", value):
            text = part.strip()
            key = text.lower()
            if text and key not in seen:
                parts.append(text)
                seen.add(key)
    return ", ".join(parts)


def _ltx_negative_for_prompt(prompt: str) -> tuple[str, ...]:
    text = str(prompt or "").lower()
    if not re.search(r"\b(?:only the requested|requested elements only|avoid unrequested|without unrequested|minimal|minimalist|plain|simple)\b", text):
        return ()
    negative = list(_PROMPT_FIDELITY_LTX_BASE_NEGATIVE)
    if not _mentions_any_allowed(text, _CHARACTER_OR_LIVING_WORDS):
        negative.extend(_PROMPT_FIDELITY_LTX_CHARACTER_NEGATIVE)
    if _mentions_any_allowed(text, _GEOMETRIC_OBJECT_WORDS) and not _mentions_any_allowed(text, _SEGMENTED_SURFACE_WORDS):
        negative.extend(_PROMPT_FIDELITY_LTX_SEGMENTATION_NEGATIVE)
    for word in _PROMPT_FIDELITY_LTX_EXTRA_NEGATIVE:
        if not _brief_allows(text, (word,)):
            negative.append(word)
    return tuple(negative)


def _patch_planner() -> None:
    from services.studio.production import planner

    if getattr(planner, "_club3090_prompt_sanitizer_patched", False):
        return
    original = planner.plan_from_brief

    def patched_plan_from_brief(brief, *args, **kwargs):
        plan, artifacts = original(brief, *args, **kwargs)
        for shot in getattr(plan, "shots", []) or []:
            shot.prompt_intent = _sanitize_prompt_intent(getattr(shot, "prompt_intent", ""), brief)
        for task in getattr(plan, "asset_tasks", []) or []:
            task.prompt = _sanitize_prompt_intent(getattr(task, "prompt", ""), brief)
        return plan, artifacts

    planner.plan_from_brief = patched_plan_from_brief
    planner._club3090_prompt_sanitizer_patched = True
    print("[club3090-production-patch] affirmative prompt sanitizer active", flush=True)


def _patch_ltx_negative_guard() -> None:
    from services.studio.production import ltx_workflows

    if getattr(ltx_workflows, "_club3090_ltx_negative_guard_patched", False):
        return
    original = ltx_workflows.render_graph

    def patched_render_graph(lane: str, *args, prompt: str = "", negative: str = "", **kwargs):
        guard = _ltx_negative_for_prompt(prompt)
        if guard:
            negative = _merge_negative_prompt(negative, guard)
        return original(lane, *args, prompt=prompt, negative=negative, **kwargs)

    ltx_workflows.render_graph = patched_render_graph
    ltx_workflows._club3090_ltx_negative_guard_patched = True
    print("[club3090-production-patch] LTX prompt fidelity negative guard active", flush=True)


try:
    _patch_planner()
    _patch_ltx_negative_guard()
except Exception as exc:  # fail open so upstream remains usable if internals move
    print(f"[club3090-production-patch] prompt sanitizer unavailable: {exc}", flush=True)
PY
  sudo chmod 0644 "$patch_dir/sitecustomize.py" >/dev/null 2>&1 || true
  if command -v systemctl >/dev/null 2>&1 && sudo systemctl is-active --quiet "$unit" 2>/dev/null; then
    if curl -fsS --max-time 2 "http://127.0.0.1:${port}/produce/health" >/dev/null; then
      sudo systemctl show -p MainPID --value "$unit" 2>/dev/null | sudo tee "$pidfile" >/dev/null || true
      echo "[ai-studio] backend Production Director service is already ready on :${port}"
      return 0
    fi
    echo "[ai-studio] stopping unhealthy backend Production Director unit"
    sudo systemctl stop "$unit" >/dev/null 2>&1 || true
    sudo systemctl reset-failed "$unit" >/dev/null 2>&1 || true
  fi
  if [ -f "$pidfile" ]; then
    local existing_pid
    existing_pid="$(sudo cat "$pidfile" 2>/dev/null || true)"
    if [ -n "$existing_pid" ] && sudo kill -0 "$existing_pid" 2>/dev/null; then
      if curl -fsS --max-time 2 "http://127.0.0.1:${port}/produce/health" >/dev/null; then
        echo "[ai-studio] backend Production Director service is already ready on :${port}"
        return 0
      fi
      echo "[ai-studio] stopping stale backend Production Director pid $existing_pid"
      sudo kill "$existing_pid" >/dev/null 2>&1 || true
      sleep 2
    fi
  fi
  if curl -fsS --max-time 2 "http://127.0.0.1:${port}/produce/health" >/dev/null; then
    echo "[ai-studio] backend Production Director service is already reachable on :${port}"
    return 0
  fi
  echo "[ai-studio] starting backend Production Director service on :${port}"
  if command -v systemd-run >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    sudo systemctl stop "$unit" >/dev/null 2>&1 || true
    sudo systemctl reset-failed "$unit" >/dev/null 2>&1 || true
    sudo systemd-run \
      --unit="${unit%.service}" \
      --collect \
      --property=Restart=on-failure \
      --property=RestartSec=5 \
      --property=WorkingDirectory="$PWD" \
      --property=StandardOutput=append:"$logfile" \
      --property=StandardError=append:"$logfile" \
      --setenv=HOME="$HOME" \
      --setenv=PATH="$PATH" \
      --setenv=CLUB3090_DIR="$PWD" \
      --setenv=COMFYUI_OUTPUT_DIR="$output_root" \
      --setenv=STUDIO_WORKFLOW_DIR="$workflow_dir" \
      --setenv=COMFYUI_URL="${COMFYUI_URL:-http://localhost:8188}" \
      --setenv=TTS_URL="${TTS_URL:-http://localhost:8192}" \
      --setenv=VOICE_URL="${VOICE_URL:-http://localhost:8193}" \
      --setenv=DIRECTOR_URL="${DIRECTOR_URL:-http://localhost:8090/v1}" \
      --setenv=DIRECTOR_MODEL="${DIRECTOR_MODEL:-qwen3.5-4b-uncensored}" \
      --setenv=SEARXNG_URL="${SEARXNG_URL:-http://localhost:8088}" \
      --setenv=STUDIO_PRODUCTION_PORT="$port" \
      --setenv=STUDIO_GALLERY_BASE="${STUDIO_GALLERY_BASE:-}" \
      --setenv=STUDIO_PRODUCTION_LOG="$logfile" \
      --setenv=STUDIO_PRODUCTION_PID="$pidfile" \
      --setenv=PYTHONPATH="$production_pythonpath" \
      /usr/bin/python3 -m services.studio.production.server
  else
    sudo env \
      HOME="$HOME" \
      PATH="$PATH" \
      CLUB3090_DIR="$PWD" \
      COMFYUI_OUTPUT_DIR="$output_root" \
      STUDIO_WORKFLOW_DIR="$workflow_dir" \
      COMFYUI_URL="${COMFYUI_URL:-http://localhost:8188}" \
      TTS_URL="${TTS_URL:-http://localhost:8192}" \
      VOICE_URL="${VOICE_URL:-http://localhost:8193}" \
      DIRECTOR_URL="${DIRECTOR_URL:-http://localhost:8090/v1}" \
      DIRECTOR_MODEL="${DIRECTOR_MODEL:-qwen3.5-4b-uncensored}" \
      SEARXNG_URL="${SEARXNG_URL:-http://localhost:8088}" \
      STUDIO_PRODUCTION_PORT="$port" \
      STUDIO_GALLERY_BASE="${STUDIO_GALLERY_BASE:-}" \
      STUDIO_PRODUCTION_LOG="$logfile" \
      STUDIO_PRODUCTION_PID="$pidfile" \
      PYTHONPATH="$production_pythonpath" \
      bash -c 'cd "$CLUB3090_DIR"; nohup python3 -m services.studio.production.server > "$STUDIO_PRODUCTION_LOG" 2>&1 & echo $! > "$STUDIO_PRODUCTION_PID"'
  fi
  sudo chmod a+r "$pidfile" "$logfile" 2>/dev/null || true
  local deadline=$((SECONDS + 45))
  until curl -fsS --max-time 2 "http://127.0.0.1:${port}/produce/health" >/dev/null; do
    if command -v systemctl >/dev/null 2>&1 && sudo systemctl list-units --full --all "$unit" --no-legend 2>/dev/null | grep -q "$unit"; then
      if ! sudo systemctl is-active --quiet "$unit" 2>/dev/null; then
        echo "[ai-studio] backend Production Director service exited during startup" >&2
        sudo tail -n 80 "$logfile" 2>/dev/null || true
        exit 1
      fi
      sudo systemctl show -p MainPID --value "$unit" 2>/dev/null | sudo tee "$pidfile" >/dev/null || true
    elif [ -f "$pidfile" ]; then
      local started_pid
      started_pid="$(sudo cat "$pidfile" 2>/dev/null || true)"
      if [ -n "$started_pid" ] && ! sudo kill -0 "$started_pid" 2>/dev/null; then
        echo "[ai-studio] backend Production Director service exited during startup" >&2
        sudo tail -n 80 "$logfile" 2>/dev/null || true
        exit 1
      fi
    fi
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "[ai-studio] backend Production Director service did not become ready within 45 seconds" >&2
      sudo tail -n 80 "$logfile" 2>/dev/null || true
      exit 1
    fi
    sleep 2
  done
  if command -v systemctl >/dev/null 2>&1 && sudo systemctl is-active --quiet "$unit" 2>/dev/null; then
    sudo systemctl show -p MainPID --value "$unit" 2>/dev/null | sudo tee "$pidfile" >/dev/null || true
  fi
}

stop_ai_studio_production_service() {
  local output_root="${COMFYUI_OUTPUT_DIR:-${COMFYUI_MODELS_ROOT:-$PWD/ai-studio-models/comfyui}/output}"
  local pidfile="$output_root/studio-production.pid"
  local unit="club3090-studio-production.service"
  if command -v systemctl >/dev/null 2>&1 && sudo systemctl list-units --full --all "$unit" --no-legend 2>/dev/null | grep -q "$unit"; then
    echo "[ai-studio] stopping backend Production Director service"
    sudo systemctl stop "$unit" >/dev/null 2>&1 || true
    sudo systemctl reset-failed "$unit" >/dev/null 2>&1 || true
  fi
  if [ ! -f "$pidfile" ]; then
    return 0
  fi
  local pid
  pid="$(sudo cat "$pidfile" 2>/dev/null || true)"
  if [ -n "$pid" ] && sudo kill -0 "$pid" 2>/dev/null; then
    echo "[ai-studio] stopping backend Production Director service"
    sudo kill "$pid" >/dev/null 2>&1 || true
    for _ in 1 2 3 4 5; do
      sudo kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    sudo kill -9 "$pid" >/dev/null 2>&1 || true
  fi
  sudo rm -f "$pidfile" 2>/dev/null || true
}
"""


def image_studio_setup_command():
    return r"""
set -euo pipefail
echo "[ai-studio] starting full setup"
studio_setup_script="scripts/setup-ai-studio.sh"
if [ ! -x "$studio_setup_script" ] && [ ! -f "$studio_setup_script" ]; then
  if [ -x scripts/setup-image-studio.sh ] || [ -f scripts/setup-image-studio.sh ]; then
    echo "[ai-studio] scripts/setup-ai-studio.sh was not found; using legacy setup-image-studio.sh wrapper"
    studio_setup_script="scripts/setup-image-studio.sh"
  else
    echo "[ai-studio] ERROR: scripts/setup-ai-studio.sh was not found in $PWD" >&2
    exit 1
  fi
fi
if [ ! -x "$studio_setup_script" ] && [ ! -f "$studio_setup_script" ]; then
  echo "[ai-studio] ERROR: $studio_setup_script was not found in $PWD" >&2
  exit 1
fi
if [ -z "${HOME:-}" ]; then
  HOME="$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f6 || true)"
fi
export HOME="${HOME:-/tmp}"
HF_CLI_VENV="/opt/club3090-control/hf-cli-venv"
export PATH="$HF_CLI_VENV/bin:$HOME/.local/bin:$PATH"
if [ ! -e /opt/ai/github/club-3090 ] || [ "$(readlink /opt/ai/github/club-3090 2>/dev/null || true)" != "$PWD" ]; then
  sudo mkdir -p /opt/ai/github
  if [ -L /opt/ai/github/club-3090 ] || [ ! -e /opt/ai/github/club-3090 ]; then
    sudo ln -sfn "$PWD" /opt/ai/github/club-3090
  fi
fi
if ! command -v hf >/dev/null 2>&1; then
  echo "[ai-studio] installing huggingface_hub CLI into $HF_CLI_VENV"
  sudo python3 -m venv "$HF_CLI_VENV"
  sudo chown -R "$(id -u):$(id -g)" "$HF_CLI_VENV"
  "$HF_CLI_VENV/bin/python" -m pip install -U pip huggingface_hub
fi
export ASSUME_YES=1
export LANIP="${LANIP:-127.0.0.1}"
export MODEL_DIR="${MODEL_DIR:-$PWD/models-cache}"
export AI_STUDIO_MODELS_ROOT="${AI_STUDIO_MODELS_ROOT:-$PWD/ai-studio-models}"
export COMFYUI_MODELS_ROOT="${COMFYUI_MODELS_ROOT:-$AI_STUDIO_MODELS_ROOT/comfyui}"
export COMFYUI_MODELS_DIR="${COMFYUI_MODELS_DIR:-$COMFYUI_MODELS_ROOT/models}"
export WITH_VOICE="${WITH_VOICE:-1}"
export HF_TOKEN="${HF_TOKEN:-$(sudo sed -n 's/^HF_TOKEN=//p' .env 2>/dev/null | tail -n 1)}"
export HF_HUB_DISABLE_XET=1
export SKIP_BUILD="${SKIP_BUILD:-}"
export SKIP_DOWNLOAD="${SKIP_DOWNLOAD:-}"
sudo mkdir -p "$MODEL_DIR" "$COMFYUI_MODELS_DIR" /mnt/models
if [ -L /mnt/models/comfyui ] && [ "$(readlink /mnt/models/comfyui 2>/dev/null || true)" != "$COMFYUI_MODELS_ROOT" ]; then
  sudo ln -sfn "$COMFYUI_MODELS_ROOT" /mnt/models/comfyui
elif [ ! -e /mnt/models/comfyui ]; then
  sudo ln -s "$COMFYUI_MODELS_ROOT" /mnt/models/comfyui
fi
if [ -z "$SKIP_BUILD" ] && sudo docker image inspect comfyui-local:latest >/dev/null 2>&1; then
  echo "[ai-studio] reusing existing comfyui-local:latest image; skipping ComfyUI rebuild"
  export SKIP_BUILD=1
fi
set_env_value() {
  key="$1"
  value="$2"
  if sudo grep -qE "^${key}=" .env 2>/dev/null; then
    sudo sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '%s=%s\n' "$key" "$value" | sudo tee -a .env >/dev/null
  fi
}
set_env_value MODEL_DIR "$MODEL_DIR"
set_env_value AI_STUDIO_MODELS_ROOT "$AI_STUDIO_MODELS_ROOT"
set_env_value COMFYUI_MODELS_DIR "$COMFYUI_MODELS_DIR"
set_env_value HF_HUB_DISABLE_XET "$HF_HUB_DISABLE_XET"
existing_director_device="$(sudo sed -n 's/^STUDIO_DIRECTOR_DEVICE=//p' .env 2>/dev/null | tail -n 1 | tr -d "\"'" || true)"
if [ "${STUDIO_DIRECTOR_DEVICE+x}" = x ]; then
  director_device="$STUDIO_DIRECTOR_DEVICE"
else
  director_device="${existing_director_device:-auto}"
  if [ "$director_device" = "cpu" ]; then
    director_device="auto"
  fi
fi
set_env_value STUDIO_DIRECTOR_DEVICE "$director_device"
if [ "$director_device" = "cpu" ]; then
  set_env_value STUDIO_DIRECTOR_GPU_LAYERS "0"
fi
run_image_studio_step() {
  sudo env HOME="$HOME" PATH="$PATH" HF_TOKEN="$HF_TOKEN" HF_HUB_DISABLE_XET="$HF_HUB_DISABLE_XET" SKIP_BUILD="$SKIP_BUILD" SKIP_DOWNLOAD="$SKIP_DOWNLOAD" WITH_VOICE="$WITH_VOICE" ASSUME_YES="$ASSUME_YES" LANIP="$LANIP" MODEL_DIR="$MODEL_DIR" AI_STUDIO_MODELS_ROOT="$AI_STUDIO_MODELS_ROOT" COMFYUI_MODELS_ROOT="$COMFYUI_MODELS_ROOT" COMFYUI_MODELS_DIR="$COMFYUI_MODELS_DIR" "$@"
}
""" + ai_studio_docker_headroom_snippet() + ai_studio_production_service_snippet() + ai_studio_runtime_compat_snippet() + r"""
echo "[ai-studio] running upstream $studio_setup_script --yes"
run_image_studio_step bash "$studio_setup_script" --yes
apply_ai_studio_director_healthcheck_override
if [ -z "${SKIP_DOWNLOAD:-}" ] && [ -f services/comfyui/download_hidream_o1.sh ]; then
  echo "[ai-studio] downloading HiDream-O1 assets not covered by the upstream all-models script"
  run_image_studio_step bash services/comfyui/download_hidream_o1.sh
fi
if [ -z "${SKIP_DOWNLOAD:-}" ] && { [ ! -f "$COMFYUI_MODELS_DIR/diffusion_models/Chroma1-HD-fp8mixed.safetensors" ] || [ ! -f "$COMFYUI_MODELS_DIR/text_encoders/t5xxl_fp16.safetensors" ] || [ ! -f "$COMFYUI_MODELS_DIR/vae/flux/ae.safetensors" ]; }; then
  echo "[ai-studio] downloading Chroma assets not covered by the upstream all-models script"
  sudo mkdir -p "$COMFYUI_MODELS_DIR/diffusion_models" "$COMFYUI_MODELS_DIR/text_encoders" "$COMFYUI_MODELS_DIR/vae/flux"
  run_image_studio_step hf download Comfy-Org/Chroma1-HD_repackaged split_files/diffusion_models/Chroma1-HD-fp8mixed.safetensors --local-dir "$COMFYUI_MODELS_DIR"
  if [ -f "$COMFYUI_MODELS_DIR/split_files/diffusion_models/Chroma1-HD-fp8mixed.safetensors" ] && [ ! -e "$COMFYUI_MODELS_DIR/diffusion_models/Chroma1-HD-fp8mixed.safetensors" ]; then
    sudo ln -s ../split_files/diffusion_models/Chroma1-HD-fp8mixed.safetensors "$COMFYUI_MODELS_DIR/diffusion_models/Chroma1-HD-fp8mixed.safetensors"
  fi
  run_image_studio_step hf download comfyanonymous/flux_text_encoders t5xxl_fp16.safetensors --local-dir "$COMFYUI_MODELS_DIR/text_encoders"
  run_image_studio_step hf download black-forest-labs/FLUX.1-dev ae.safetensors --local-dir "$COMFYUI_MODELS_DIR/vae/flux"
fi
""" + image_studio_extension_install_snippet() + r"""
echo "[ai-studio] reserving both GPUs for the direct ComfyUI client"
run_image_studio_step docker stop llama-cpp-gemma4-12b >/dev/null 2>&1 || true
require_compose_docker_pull_space "ComfyUI compose up" "services/comfyui" "services/comfyui/docker-compose.yml" 0 COMFYUI_CUDA_VISIBLE_DEVICES=
sudo env HOME="$HOME" PATH="$PATH" HF_TOKEN="$HF_TOKEN" COMFYUI_CUDA_VISIBLE_DEVICES= docker compose --project-directory services/comfyui -f services/comfyui/docker-compose.yml up -d --force-recreate
echo "[ai-studio] starting long-video orchestrator"
require_compose_docker_pull_space "AI Studio orchestrator compose up" "services/studio/orchestrator" "services/studio/orchestrator/docker-compose.yml" 1 COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output"
sudo env HOME="$HOME" PATH="$PATH" COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output" docker compose --project-directory services/studio/orchestrator -f services/studio/orchestrator/docker-compose.yml up -d --build
if [ -f "$COMFYUI_MODELS_DIR/tts/kokoro/kokoro-v1.0.onnx" ] && [ -f "$COMFYUI_MODELS_DIR/tts/kokoro/voices-v1.0.bin" ]; then
  echo "[ai-studio] starting Kokoro CPU voiceover service"
  require_compose_docker_pull_space "AI Studio Kokoro compose up" "services/studio/tts" "services/studio/tts/docker-compose.yml" 1 KOKORO_DIR="$COMFYUI_MODELS_DIR/tts/kokoro" COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output"
  sudo env HOME="$HOME" PATH="$PATH" KOKORO_DIR="$COMFYUI_MODELS_DIR/tts/kokoro" COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output" docker compose --project-directory services/studio/tts -f services/studio/tts/docker-compose.yml up -d --build
fi
STEP_AUDIO_DIR="$COMFYUI_MODELS_DIR/Step-Audio"
if [ -d "$STEP_AUDIO_DIR/Step-Audio-EditX" ] && [ -d "$STEP_AUDIO_DIR/Step-Audio-Tokenizer" ]; then
  echo "[ai-studio] starting Step-Audio premium voice service (lazy GPU load)"
  require_compose_docker_pull_space "AI Studio Step-Audio compose up" "services/studio/step-voice" "services/studio/step-voice/docker-compose.yml" 1 STEP_AUDIO_DIR="$STEP_AUDIO_DIR" COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output" STEP_VOICE_LAZY="${STEP_VOICE_LAZY:-1}" STEP_VOICE_IDLE_UNLOAD_S="${STEP_VOICE_IDLE_UNLOAD_S:-300}"
  sudo env HOME="$HOME" PATH="$PATH" STEP_AUDIO_DIR="$STEP_AUDIO_DIR" COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output" STEP_VOICE_LAZY="${STEP_VOICE_LAZY:-1}" STEP_VOICE_IDLE_UNLOAD_S="${STEP_VOICE_IDLE_UNLOAD_S:-300}" docker compose --project-directory services/studio/step-voice -f services/studio/step-voice/docker-compose.yml up -d --build
fi
COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output" start_ai_studio_production_service
director_root="$MODEL_DIR/qwen3.5-4b-gguf/hauhaucs-uncensored-q4km"
if [ ! -f "$director_root/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf" ] || [ ! -f "$director_root/mmproj-Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-BF16.gguf" ]; then
  echo "[ai-studio] Studio Director assets are not installed; stopping its optional container"
  run_image_studio_step docker stop studio-director >/dev/null 2>&1 || true
fi
for optional_compose in services/openwebui/docker-compose.yml services/litellm/docker-compose.yml services/searxng/docker-compose.yml services/qdrant/docker-compose.yml; do
  if [ -f "$optional_compose" ]; then
    optional_dir="$(dirname "$optional_compose")"
    echo "[ai-studio] stopping optional service $optional_compose"
    run_image_studio_step docker compose --project-directory "$optional_dir" -f "$optional_compose" stop || true
  fi
done
deadline=$((SECONDS + 300))
until curl -fsS --max-time 3 http://127.0.0.1:8188/system_stats >/dev/null; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "[ai-studio] ComfyUI did not become ready within 300 seconds" >&2
    exit 1
  fi
  sleep 2
done
if ! sudo docker exec comfyui test -f /workspace/ComfyUI/custom_nodes/club3090_workflow_preview/js/club3090-preview.js; then
  echo "[ai-studio] Club-3090 ComfyUI workflow preview extension was not installed" >&2
  exit 1
fi
echo "[ai-studio] setup complete"
echo "[ai-studio] optional lanes can be downloaded from the AI Studio panel"
"""


def image_studio_remove_command():
    return r"""
set -euo pipefail
echo "[ai-studio] removing AI Studio services"
if [ -z "${HOME:-}" ]; then
  HOME="$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f6 || true)"
fi
export HOME="${HOME:-/tmp}"
export PATH="$HOME/.local/bin:$PATH"
run_image_studio_step() {
  sudo env HOME="$HOME" PATH="$PATH" "$@"
}
AI_STUDIO_MODELS_ROOT="${AI_STUDIO_MODELS_ROOT:-$PWD/ai-studio-models}"
COMFYUI_MODELS_ROOT="${COMFYUI_MODELS_ROOT:-$AI_STUDIO_MODELS_ROOT/comfyui}"
""" + ai_studio_production_service_snippet() + r"""
stop_ai_studio_production_service
for compose in \
  services/comfyui/docker-compose.yml \
  services/studio/enhancer/docker-compose.yml \
  services/studio/image-shim/docker-compose.yml \
  services/studio/gallery/docker-compose.yml \
  services/studio/orchestrator/docker-compose.yml \
  services/studio/tts/docker-compose.yml \
  services/studio/step-voice/docker-compose.yml \
  services/openwebui/docker-compose.yml \
  services/litellm/docker-compose.yml \
  services/searxng/docker-compose.yml \
  services/qdrant/docker-compose.yml
do
  if [ -f "$compose" ]; then
    echo "[ai-studio] docker compose down $compose"
    dir="$(dirname "$compose")"
    run_image_studio_step docker compose --project-directory "$dir" -f "$compose" down --remove-orphans
  fi
done
echo "[ai-studio] remove complete; downloaded models were left in place"
"""


def image_studio_start_command():
    return r"""
set -euo pipefail
cd "${CLUB3090_DIR:-/opt/ai/club-3090}"
if [ -z "${HOME:-}" ]; then
  HOME="$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f6 || true)"
fi
export HOME="${HOME:-/tmp}"
export PATH="$HOME/.local/bin:$PATH"
if [ ! -e /opt/ai/github/club-3090 ] || [ "$(readlink /opt/ai/github/club-3090 2>/dev/null || true)" != "$PWD" ]; then
  sudo mkdir -p /opt/ai/github
  if [ -L /opt/ai/github/club-3090 ] || [ ! -e /opt/ai/github/club-3090 ]; then
    sudo ln -sfn "$PWD" /opt/ai/github/club-3090
  fi
fi
echo "[ai-studio] starting direct AI Studio runtime"
""" + ai_studio_docker_headroom_snippet() + ai_studio_production_service_snippet() + ai_studio_runtime_compat_snippet() + r"""
MODEL_DIR="${MODEL_DIR:-$PWD/models-cache}"
AI_STUDIO_MODELS_ROOT="${AI_STUDIO_MODELS_ROOT:-$PWD/ai-studio-models}"
COMFYUI_MODELS_ROOT="${COMFYUI_MODELS_ROOT:-$AI_STUDIO_MODELS_ROOT/comfyui}"
COMFYUI_MODELS_DIR="${COMFYUI_MODELS_DIR:-$COMFYUI_MODELS_ROOT/models}"
require_compose_docker_pull_space "ComfyUI compose up" "services/comfyui" "services/comfyui/docker-compose.yml" 0 COMFYUI_CUDA_VISIBLE_DEVICES=
require_compose_docker_pull_space "AI Studio orchestrator compose up" "services/studio/orchestrator" "services/studio/orchestrator/docker-compose.yml" 1 COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output"
if [ -f "$COMFYUI_MODELS_DIR/tts/kokoro/kokoro-v1.0.onnx" ] && [ -f "$COMFYUI_MODELS_DIR/tts/kokoro/voices-v1.0.bin" ]; then
  require_compose_docker_pull_space "AI Studio Kokoro compose up" "services/studio/tts" "services/studio/tts/docker-compose.yml" 1 KOKORO_DIR="$COMFYUI_MODELS_DIR/tts/kokoro" COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output"
fi
STEP_AUDIO_DIR="$COMFYUI_MODELS_DIR/Step-Audio"
if [ -d "$STEP_AUDIO_DIR/Step-Audio-EditX" ] && [ -d "$STEP_AUDIO_DIR/Step-Audio-Tokenizer" ]; then
  require_compose_docker_pull_space "AI Studio Step-Audio compose up" "services/studio/step-voice" "services/studio/step-voice/docker-compose.yml" 1 STEP_AUDIO_DIR="$STEP_AUDIO_DIR" COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output" STEP_VOICE_LAZY="${STEP_VOICE_LAZY:-1}" STEP_VOICE_IDLE_UNLOAD_S="${STEP_VOICE_IDLE_UNLOAD_S:-300}"
fi
sudo env HOME="$HOME" PATH="$PATH" bash scripts/gpu-mode.sh ai-studio
apply_ai_studio_director_healthcheck_override
echo "[ai-studio] reserving both GPUs for direct multimedia workflows"
sudo env HOME="$HOME" PATH="$PATH" docker stop llama-cpp-gemma4-12b >/dev/null 2>&1 || true
""" + image_studio_extension_install_snippet() + r"""
sudo env HOME="$HOME" PATH="$PATH" COMFYUI_CUDA_VISIBLE_DEVICES= docker compose --project-directory services/comfyui -f services/comfyui/docker-compose.yml up -d --force-recreate
echo "[ai-studio] starting long-video orchestrator"
sudo env HOME="$HOME" PATH="$PATH" COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output" docker compose --project-directory services/studio/orchestrator -f services/studio/orchestrator/docker-compose.yml up -d --build
if [ -f "$COMFYUI_MODELS_DIR/tts/kokoro/kokoro-v1.0.onnx" ] && [ -f "$COMFYUI_MODELS_DIR/tts/kokoro/voices-v1.0.bin" ]; then
  echo "[ai-studio] starting Kokoro CPU voiceover service"
  sudo env HOME="$HOME" PATH="$PATH" KOKORO_DIR="$COMFYUI_MODELS_DIR/tts/kokoro" COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output" docker compose --project-directory services/studio/tts -f services/studio/tts/docker-compose.yml up -d --build
fi
if [ -d "$STEP_AUDIO_DIR/Step-Audio-EditX" ] && [ -d "$STEP_AUDIO_DIR/Step-Audio-Tokenizer" ]; then
  echo "[ai-studio] starting Step-Audio premium voice service (lazy GPU load)"
  sudo env HOME="$HOME" PATH="$PATH" STEP_AUDIO_DIR="$STEP_AUDIO_DIR" COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output" STEP_VOICE_LAZY="${STEP_VOICE_LAZY:-1}" STEP_VOICE_IDLE_UNLOAD_S="${STEP_VOICE_IDLE_UNLOAD_S:-300}" docker compose --project-directory services/studio/step-voice -f services/studio/step-voice/docker-compose.yml up -d --build
fi
COMFYUI_OUTPUT_DIR="$COMFYUI_MODELS_ROOT/output" start_ai_studio_production_service
director_root="$MODEL_DIR/qwen3.5-4b-gguf/hauhaucs-uncensored-q4km"
if [ ! -f "$director_root/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf" ] || [ ! -f "$director_root/mmproj-Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-BF16.gguf" ]; then
  echo "[ai-studio] Studio Director assets are not installed; stopping its optional container"
  sudo env HOME="$HOME" PATH="$PATH" docker stop studio-director >/dev/null 2>&1 || true
fi
for optional_compose in services/openwebui/docker-compose.yml services/litellm/docker-compose.yml services/searxng/docker-compose.yml services/qdrant/docker-compose.yml; do
  if [ -f "$optional_compose" ]; then
    optional_dir="$(dirname "$optional_compose")"
    echo "[ai-studio] stopping optional client $optional_compose"
    sudo env HOME="$HOME" PATH="$PATH" docker compose --project-directory "$optional_dir" -f "$optional_compose" stop || true
  fi
done
deadline=$((SECONDS + 180))
until curl -fsS --max-time 3 http://127.0.0.1:8188/system_stats >/dev/null; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "[ai-studio] ComfyUI did not become ready within 180 seconds" >&2
    exit 1
  fi
  sleep 2
done
if ! sudo docker exec comfyui test -f /workspace/ComfyUI/custom_nodes/club3090_workflow_preview/js/club3090-preview.js; then
  echo "[ai-studio] Club-3090 ComfyUI workflow preview extension was not installed" >&2
  exit 1
fi
echo "[ai-studio] direct AI Studio runtime is ready"
"""


def image_studio_stop_command():
    return r"""
set -euo pipefail
cd "${CLUB3090_DIR:-/opt/ai/club-3090}"
if [ -z "${HOME:-}" ]; then
  HOME="$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f6 || true)"
fi
export HOME="${HOME:-/tmp}"
export PATH="$HOME/.local/bin:$PATH"
echo "[ai-studio] stopping AI Studio runtime; installed models are preserved"
AI_STUDIO_MODELS_ROOT="${AI_STUDIO_MODELS_ROOT:-$PWD/ai-studio-models}"
COMFYUI_MODELS_ROOT="${COMFYUI_MODELS_ROOT:-$AI_STUDIO_MODELS_ROOT/comfyui}"
""" + ai_studio_production_service_snippet() + r"""
stop_ai_studio_production_service
for compose in \
  services/comfyui/docker-compose.yml \
  services/studio/enhancer/docker-compose.yml \
  services/studio/image-shim/docker-compose.yml \
  services/studio/gallery/docker-compose.yml \
  services/studio/orchestrator/docker-compose.yml \
  services/studio/tts/docker-compose.yml \
  services/studio/step-voice/docker-compose.yml
do
  if [ -f "$compose" ]; then
    dir="$(dirname "$compose")"
    sudo env HOME="$HOME" PATH="$PATH" docker compose --project-directory "$dir" -f "$compose" stop || true
  fi
done
if [ -f compose.base.yml ]; then
  sudo env HOME="$HOME" PATH="$PATH" ESTATE_GPUS=1 CTX_SIZE=32768 PORT=8069 docker compose -f compose.base.yml stop llama-cpp-gemma4-12b || true
fi
echo "[ai-studio] runtime stopped"
"""


SCRIPT_TERMINAL_STATUSES = {"success", "failed", "cancelled"}


def _script_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default or 0)


def _process_alive(pid):
    pid = _script_int(pid)
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _process_group_alive(pgid):
    pgid = _script_int(pgid)
    if pgid <= 0:
        return False
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _script_job_process_alive(job):
    job = dict(job or {})
    return _process_group_alive(job.get("process_group_id")) or _process_alive(job.get("process_id"))


def _parse_script_log_return_code(log_file):
    path = str(log_file or "")
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            tail = handle.readlines()[-80:]
    except Exception:
        return None
    for line in reversed(tail):
        match = re.search(r"\[script\]\s+finished\s+rc=([0-9]+)", str(line or ""))
        if match:
            return int(match.group(1))
    return None


def script_state_mirror_job(state, job):
    payload = dict(state or {})
    row = dict(job or {})
    queue = list(payload.get("queue") or [])
    for key in (
        "job_id", "status", "summary", "script_id", "script_path", "label", "command",
        "instance_id", "mode", "container", "url", "started_at", "finished_at",
        "return_code", "log_file", "context", "process_id", "process_group_id",
    ):
        payload[key] = row.get(key)
    payload["active"] = str(row.get("status") or "") == "running"
    payload["log_tail"] = []
    payload["queue"] = queue
    return payload


def reconcile_script_job_state(state, persist=False):
    payload = dict(state or {})
    queue = [dict(row) for row in (payload.get("queue") or []) if isinstance(row, dict)]
    payload["queue"] = queue
    current_id = str(payload.get("job_id") or "").strip()
    current_status = str(payload.get("status") or "").strip()
    matching = next((dict(row) for row in queue if str(row.get("job_id") or "").strip() == current_id), {})
    replacement = {}
    if matching:
        row_status = str(matching.get("status") or "").strip()
        if row_status and (row_status != current_status or bool(payload.get("active")) != (row_status == "running")):
            replacement = matching
    elif current_status in {"queued", "running", "cancelling"} or payload.get("active"):
        replacement = (
            next((dict(row) for row in queue if str(row.get("status") or "").strip() == "running"), {})
            or next((dict(row) for row in queue if str(row.get("status") or "").strip() == "queued"), {})
            or next((dict(row) for row in reversed(queue)), {})
        )
    if replacement:
        payload = script_state_mirror_job(payload, replacement)
        payload["queue"] = queue
    elif not queue and (current_status in {"queued", "running", "cancelling"} or payload.get("active")):
        payload = default_script_job_state()
    if str(payload.get("status") or "").strip() != "running":
        payload["active"] = False
    if persist:
        comparable = dict(state or {})
        comparable["log_tail"] = []
        next_payload = dict(payload)
        next_payload["log_tail"] = []
        if comparable != next_payload:
            write_script_job_state(payload)
    return payload


def execute_script_job(job):
    global script_process
    job = dict(job or {})
    log_file = str(job.get("log_file") or "")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    command = str(job.get("command") or "")
    context = dict(job.get("context") or {})
    env = _repo_subprocess_env()
    if context.get("url"):
        env["URL"] = str(context.get("url") or "")
        env["PREFLIGHT_NO_AUTODETECT"] = "1"
    if context.get("container"):
        env["CONTAINER"] = str(context.get("container") or "")
    if context.get("served_model_name"):
        env["MODEL"] = str(context.get("served_model_name") or "")
    if context.get("engine"):
        env["ENGINE_KIND"] = str(context.get("engine") or "")
    rc = 999
    try:
        with open(log_file, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"$ {command}\n\n")
            handle.flush()
            process = subprocess.Popen(
                ["bash", "-lc", command],
                cwd=CLUB3090_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                start_new_session=True,
            )
            script_process = process
            try:
                pgid = os.getpgid(process.pid)
            except Exception:
                pgid = process.pid
            with script_job_lock:
                state = read_script_job_state()
                queue = list(state.get("queue") or [])
                for index, row in enumerate(queue):
                    if str((row or {}).get("job_id") or "") == str(job.get("job_id") or ""):
                        row = dict(row)
                        row["process_id"] = process.pid
                        row["process_group_id"] = pgid
                        queue[index] = row
                        job["process_id"] = process.pid
                        job["process_group_id"] = pgid
                        break
                state["queue"] = queue
                write_script_job_state(script_state_mirror_job(state, job))
            for line in process.stdout:
                handle.write(line)
                handle.flush()
            rc = int(process.wait())
            handle.write(f"\n[script] finished rc={rc}\n")
    except Exception as exc:
        try:
            with open(log_file, "a", encoding="utf-8", newline="\n") as handle:
                handle.write(f"\n[script] launcher error: {exc}\n")
        except Exception:
            pass
        rc = 999
    finally:
        script_process = None
    return rc


def run_script_queue_worker():
    global script_worker_thread
    try:
        while True:
            with script_job_lock:
                state = read_script_job_state()
                queue = list(state.get("queue") or [])
                next_index = next(
                    (index for index, row in enumerate(queue) if str((row or {}).get("status") or "") == "queued"),
                    -1,
                )
                if next_index < 0:
                    state["active"] = False
                    write_script_job_state(state)
                    script_worker_thread = None
                    return
                job = dict(queue[next_index])
                job.update({
                    "status": "running",
                    "summary": f"{job.get('label') or 'Script'} running",
                    "started_at": benchmark_utc_now(),
                    "finished_at": "",
                    "return_code": None,
                })
                queue[next_index] = job
                state["queue"] = queue
                write_script_job_state(script_state_mirror_job(state, job))
            rc = execute_script_job(job)
            with script_job_lock:
                state = read_script_job_state()
                queue = list(state.get("queue") or [])
                current_index = next(
                    (index for index, row in enumerate(queue) if str((row or {}).get("job_id") or "") == str(job.get("job_id") or "")),
                    -1,
                )
                if current_index < 0:
                    state["active"] = False
                    write_script_job_state(state)
                    continue
                finished = dict(queue[current_index])
                if str(finished.get("status") or "") not in {"cancelled", "cancelling"}:
                    finished.update({
                        "status": "success" if rc == 0 else "failed",
                        "summary": f"{job.get('label') or 'Script'} {'completed' if rc == 0 else 'failed'} (rc={rc})",
                        "finished_at": benchmark_utc_now(),
                        "return_code": rc,
                    })
                else:
                    finished.update({
                        "status": "cancelled",
                        "summary": f"{job.get('label') or 'Script'} cancelled",
                        "finished_at": finished.get("finished_at") or benchmark_utc_now(),
                        "return_code": 130,
                    })
                queue[current_index] = finished
                state["queue"] = queue
                next_queued = next(
                    (dict(row) for row in queue if str((row or {}).get("status") or "") == "queued"),
                    None,
                )
                write_script_job_state(script_state_mirror_job(state, next_queued or finished))
    finally:
        with script_job_lock:
            script_worker_thread = None


def ensure_script_queue_worker():
    global script_worker_thread
    with script_job_lock:
        if script_worker_thread is not None and script_worker_thread.is_alive():
            return
        script_worker_thread = threading.Thread(target=run_script_queue_worker, name="club3090-script-queue", daemon=True)
        script_worker_thread.start()


def start_script_job(script_id, args=None, instance_id=""):
    if benchmark_job_active():
        raise RuntimeError("Scripts cannot be run while Model Scores benchmarking is active.")
    row = resolve_upstream_script(script_id)
    context = script_runtime_context(instance_id)
    command = script_command_for(row, args)
    job_id = time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + f"-{int(time.time() * 1000) % 1000000:06d}-" + _selector_token(row.get("id"))
    log_dir = os.path.join(SCRIPT_RUNS_DIR, job_id)
    log_file = os.path.join(log_dir, "script.log")
    job = {
        "schema_version": 2,
        "job_id": job_id,
        "status": "queued",
        "summary": f"{row.get('label')} queued",
        "script_id": row.get("id") or "",
        "script_path": row.get("path") or "",
        "label": row.get("label") or row.get("name") or "",
        "command": command,
        "instance_id": str(context.get("instance_id") or instance_id or ""),
        "mode": str(context.get("mode") or ""),
        "container": str(context.get("container") or ""),
        "url": str(context.get("url") or ""),
        "queued_at": benchmark_utc_now(),
        "started_at": "",
        "finished_at": "",
        "return_code": None,
        "log_file": log_file,
        "log_tail": [],
        "context": context,
    }
    with script_job_lock:
        state = read_script_job_state()
        queue = list(state.get("queue") or [])
        queue.append(job)
        state["queue"] = queue[-50:]
        if not state.get("job_id") or str(state.get("status") or "") in {"success", "failed", "cancelled"}:
            state = script_state_mirror_job(state, job)
        write_script_job_state(state)
        ensure_script_queue_worker()
    return script_job_snapshot()


def queue_image_studio_script_job(script_id, label, command, script_path="", audit_line=""):
    if benchmark_job_active():
        raise RuntimeError("AI Studio scripts cannot run while Model Scores benchmarking is active.")
    clean_id = str(script_id or "ai-studio").strip() or "ai-studio"
    clean_label = str(label or "AI Studio").strip() or "AI Studio"
    context = {"instance_id": "GLOBAL", "mode": "", "container": "", "url": "", "served_model_name": "", "engine": ""}
    job_id = time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + f"-{int(time.time() * 1000) % 1000000:06d}-{_selector_token(clean_id)}"
    log_dir = os.path.join(SCRIPT_RUNS_DIR, job_id)
    log_file = os.path.join(log_dir, "script.log")
    job = {
        "schema_version": 2,
        "job_id": job_id,
        "status": "queued",
        "summary": f"{clean_label} queued",
        "script_id": clean_id,
        "script_path": script_path or os.path.join(CLUB3090_DIR, "scripts", clean_id),
        "label": clean_label,
        "command": command,
        "instance_id": "GLOBAL",
        "mode": "",
        "container": "",
        "url": "",
        "queued_at": benchmark_utc_now(),
        "started_at": "",
        "finished_at": "",
        "return_code": None,
        "log_file": log_file,
        "log_tail": [],
        "context": context,
    }
    if audit_line:
        append_audit_text_line(audit_line)
    with script_job_lock:
        state = read_script_job_state()
        queue = list(state.get("queue") or [])
        queue.append(job)
        state["queue"] = queue[-50:]
        if not state.get("job_id") or str(state.get("status") or "") in {"success", "failed", "cancelled"}:
            state = script_state_mirror_job(state, job)
        write_script_job_state(state)
        ensure_script_queue_worker()
    return script_job_snapshot()


def start_image_studio_setup_job():
    return queue_image_studio_script_job(
        "setup-ai-studio",
        "Setup AI Studio",
        image_studio_setup_command(),
        os.path.join(CLUB3090_DIR, "scripts", "setup-ai-studio.sh"),
        "[ai-studio] queued full AI Studio setup",
    )


def start_image_studio_remove_job():
    return queue_image_studio_script_job(
        "remove-ai-studio",
        "Remove AI Studio",
        image_studio_remove_command(),
        os.path.join(CLUB3090_DIR, "scripts", "gpu-mode.sh"),
        "[ai-studio] queued AI Studio service removal",
    )


def start_image_studio_runtime_job():
    return queue_image_studio_script_job(
        "start-ai-studio",
        "Start AI Studio",
        image_studio_start_command(),
        os.path.join(CLUB3090_DIR, "scripts", "gpu-mode.sh"),
        "[ai-studio] queued AI Studio runtime start",
    )


def stop_image_studio_runtime_job():
    return queue_image_studio_script_job(
        "stop-ai-studio",
        "Stop AI Studio",
        image_studio_stop_command(),
        os.path.join(CLUB3090_DIR, "scripts", "gpu-mode.sh"),
        "[ai-studio] queued AI Studio runtime stop",
    )


def image_studio_model_download_command(model_key):
    key = str(model_key or "").strip().lower()
    key = {
        "director": "studio-director",
        "music": "ace-step",
        "ace": "ace-step",
        "sfx": "stable-audio-open",
        "stable-audio": "stable-audio-open",
        "stable_audio": "stable-audio-open",
        "hidream": "hidream-o1",
        "hidream_o1": "hidream-o1",
        "ideogram": "ideogram-4",
        "ideogram4": "ideogram-4",
        "voice": "step-audio-editx",
        "speech": "step-audio-editx",
        "step-audio": "step-audio-editx",
        "step-audio-voice": "step-audio-editx",
        "krea2": "krea",
        "krea-2": "krea",
        "z-image": "zimage",
        "z-image-turbo": "zimage",
        "wan2.2": "wan",
        "wan2.2-rapid": "wan",
    }.get(key, key)
    script_map = {
        "hidream-o1": ("services/comfyui/download_hidream_o1.sh", "HiDream-O1"),
        "ideogram-4": ("services/comfyui/download_ideogram4.sh", "Ideogram-4"),
        "chroma": ("services/comfyui/download_chroma.sh", "Chroma1-HD"),
        "zimage": ("services/comfyui/download_zimage.sh", "Z-Image"),
        "krea": ("services/comfyui/download_krea.sh", "Krea 2"),
        "ltx": ("services/comfyui/download_video_models.sh", "LTX/Sulphur/10Eros"),
        "ltx-2.3": ("services/comfyui/download_video_models.sh", "LTX/Sulphur/10Eros"),
        "sulphur": ("services/comfyui/download_video_models.sh", "LTX/Sulphur/10Eros"),
        "10eros": ("services/comfyui/download_video_models.sh", "LTX/Sulphur/10Eros"),
        "wan": ("services/comfyui/download_wan.sh", "Wan2.2"),
        "ace-step": ("services/comfyui/download_ace_step.sh", "ACE-Step"),
        "stable-audio-open": ("services/comfyui/download_stable_audio.sh", "Stable Audio"),
        "kokoro": ("services/comfyui/download_kokoro.sh", "Kokoro"),
        "step-audio-editx": ("services/comfyui/download_step_audio.sh", "Step-Audio-EditX"),
        "studio-director": ("services/comfyui/download_director.sh", "Studio Director"),
    }
    script_available = key in script_map and (
        key != "chroma" or os.path.exists(os.path.join(CLUB3090_DIR, script_map[key][0]))
    )
    if script_available:
        script_path, label = script_map[key]
        return f"""
set -euo pipefail
cd {shlex.quote(CLUB3090_DIR)}
echo "[ai-studio] downloading {label} assets"
if [ -z "${{HOME:-}}" ]; then
  HOME="$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f6 || true)"
fi
export HOME="${{HOME:-/tmp}}"
HF_CLI_VENV="/opt/club3090-control/hf-cli-venv"
export PATH="$HF_CLI_VENV/bin:$HOME/.local/bin:$PATH"
if ! command -v hf >/dev/null 2>&1; then
  sudo python3 -m venv "$HF_CLI_VENV"
  sudo chown -R "$(id -u):$(id -g)" "$HF_CLI_VENV"
  "$HF_CLI_VENV/bin/python" -m pip install -U pip huggingface_hub
fi
export MODEL_DIR="${{MODEL_DIR:-$PWD/models-cache}}"
export AI_STUDIO_MODELS_ROOT="${{AI_STUDIO_MODELS_ROOT:-$PWD/ai-studio-models}}"
export COMFYUI_MODELS_ROOT="${{COMFYUI_MODELS_ROOT:-$AI_STUDIO_MODELS_ROOT/comfyui}}"
export COMFYUI_MODELS_DIR="${{COMFYUI_MODELS_DIR:-$COMFYUI_MODELS_ROOT/models}}"
export HF_TOKEN="${{HF_TOKEN:-$(sudo sed -n 's/^HF_TOKEN=//p' .env 2>/dev/null | tail -n 1)}}"
export HF_HUB_DISABLE_XET=1
sudo mkdir -p "$MODEL_DIR" "$COMFYUI_MODELS_DIR" /mnt/models
if [ -L /mnt/models/comfyui ] && [ "$(readlink /mnt/models/comfyui 2>/dev/null || true)" != "$COMFYUI_MODELS_ROOT" ]; then
  sudo ln -sfn "$COMFYUI_MODELS_ROOT" /mnt/models/comfyui
elif [ ! -e /mnt/models/comfyui ]; then
  sudo ln -s "$COMFYUI_MODELS_ROOT" /mnt/models/comfyui
fi
sudo env HOME="$HOME" PATH="$PATH" HF_TOKEN="$HF_TOKEN" HF_HUB_DISABLE_XET="$HF_HUB_DISABLE_XET" MODEL_DIR="$MODEL_DIR" AI_STUDIO_MODELS_ROOT="$AI_STUDIO_MODELS_ROOT" COMFYUI_MODELS_ROOT="$COMFYUI_MODELS_ROOT" COMFYUI_MODELS_DIR="$COMFYUI_MODELS_DIR" bash {shlex.quote(script_path)}
echo "[ai-studio] {label} asset download complete"
"""
    direct = {
        "chroma": [
            ("Comfy-Org/Chroma1-HD_repackaged", "split_files/diffusion_models/Chroma1-HD-fp8mixed.safetensors", "${COMFYUI_MODELS_DIR}"),
            ("comfyanonymous/flux_text_encoders", "t5xxl_fp16.safetensors", "${COMFYUI_MODELS_DIR}/text_encoders"),
            ("black-forest-labs/FLUX.1-dev", "ae.safetensors", "${COMFYUI_MODELS_DIR}/vae/flux"),
        ],
    }.get(key)
    if not direct:
        raise ValueError("Unknown AI Studio model download target.")
    lines = [
        "set -euo pipefail",
        f"cd {shlex.quote(CLUB3090_DIR)}",
        f'echo "[ai-studio] downloading {key} assets"',
        'if [ -z "${HOME:-}" ]; then HOME="$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f6 || true)"; fi',
        'export HOME="${HOME:-/tmp}"',
        'HF_CLI_VENV="/opt/club3090-control/hf-cli-venv"',
        'export PATH="$HF_CLI_VENV/bin:$HOME/.local/bin:$PATH"',
        'if ! command -v hf >/dev/null 2>&1; then sudo python3 -m venv "$HF_CLI_VENV"; sudo chown -R "$(id -u):$(id -g)" "$HF_CLI_VENV"; "$HF_CLI_VENV/bin/python" -m pip install -U pip huggingface_hub; fi',
        'export AI_STUDIO_MODELS_ROOT="${AI_STUDIO_MODELS_ROOT:-$PWD/ai-studio-models}"',
        'export MODEL_DIR="${MODEL_DIR:-$PWD/models-cache}"',
        'export COMFYUI_MODELS_ROOT="${COMFYUI_MODELS_ROOT:-$AI_STUDIO_MODELS_ROOT/comfyui}"',
        'export COMFYUI_MODELS_DIR="${COMFYUI_MODELS_DIR:-$COMFYUI_MODELS_ROOT/models}"',
        'export HF_TOKEN="${HF_TOKEN:-$(sudo sed -n \'s/^HF_TOKEN=//p\' .env 2>/dev/null | tail -n 1)}"',
        'export HF_HUB_DISABLE_XET=1',
        'sudo mkdir -p "$MODEL_DIR" "$COMFYUI_MODELS_DIR" /mnt/models',
        'if [ -L /mnt/models/comfyui ] && [ "$(readlink /mnt/models/comfyui 2>/dev/null || true)" != "$COMFYUI_MODELS_ROOT" ]; then sudo ln -sfn "$COMFYUI_MODELS_ROOT" /mnt/models/comfyui; elif [ ! -e /mnt/models/comfyui ]; then sudo ln -s "$COMFYUI_MODELS_ROOT" /mnt/models/comfyui; fi',
    ]
    for repo, files, target in direct:
        file_args = " ".join(shlex.quote(part) for part in shlex.split(files)) if files else ""
        lines.append(f"sudo env HOME=\"$HOME\" PATH=\"$PATH\" HF_TOKEN=\"$HF_TOKEN\" HF_HUB_DISABLE_XET=\"$HF_HUB_DISABLE_XET\" hf download {shlex.quote(repo)} {file_args} --local-dir \"{target}\"")
    if key == "chroma":
        lines.extend([
            'sudo mkdir -p "$COMFYUI_MODELS_DIR/diffusion_models"',
            'if [ -f "$COMFYUI_MODELS_DIR/split_files/diffusion_models/Chroma1-HD-fp8mixed.safetensors" ] && [ ! -e "$COMFYUI_MODELS_DIR/diffusion_models/Chroma1-HD-fp8mixed.safetensors" ]; then sudo ln -s ../split_files/diffusion_models/Chroma1-HD-fp8mixed.safetensors "$COMFYUI_MODELS_DIR/diffusion_models/Chroma1-HD-fp8mixed.safetensors"; fi',
        ])
    lines.append(f'echo "[ai-studio] {key} asset download complete"')
    return "\n".join(lines) + "\n"


def start_image_studio_model_download_job(model_key):
    key = str(model_key or "").strip().lower()
    if not key:
        raise ValueError("AI Studio model key is required.")
    return queue_image_studio_script_job(
        f"download-ai-studio-{key}",
        f"Download AI Studio {key}",
        image_studio_model_download_command(key),
        os.path.join(CLUB3090_DIR, "services"),
        f"[ai-studio] queued {key} asset download",
    )



def terminate_script_process(process):
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except Exception:
        try:
            process.terminate()
        except Exception:
            return
    try:
        process.wait(timeout=8)
        return
    except Exception:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def remove_script_job(job_id=""):
    global script_process
    process = None
    with script_job_lock:
        state = read_script_job_state()
        wanted = str(job_id or state.get("job_id") or "").strip()
        queue = list(state.get("queue") or [])
        target = next((dict(row) for row in queue if str((row or {}).get("job_id") or "") == wanted), {})
        if not target:
            return script_job_snapshot()
        running = str(target.get("status") or "") in {"running", "cancelling"}
        queue = [row for row in queue if str((row or {}).get("job_id") or "") != wanted]
        state["queue"] = queue
        if running:
            state.update({
                "active": False,
                "status": "cancelled",
                "summary": f"{target.get('label') or 'Script'} cancelled",
                "finished_at": benchmark_utc_now(),
                "return_code": 130,
            })
            process = script_process
        elif str(state.get("job_id") or "") == wanted:
            replacement = next((dict(row) for row in reversed(queue)), {})
            state = script_state_mirror_job(state, replacement) if replacement else default_script_job_state()
            state["queue"] = queue
        write_script_job_state(state)
    if process is not None:
        terminate_script_process(process)
    ensure_script_queue_worker()
    return script_job_snapshot()


def cancel_script_job(job_id=""):
    return remove_script_job(job_id)


def recover_script_queue():
    recovered_running = []
    with script_job_lock:
        state = read_script_job_state()
        queue = list(state.get("queue") or [])
        changed = False
        for index, row in enumerate(queue):
            item = dict(row or {})
            if str(item.get("status") or "") in {"running", "cancelling"}:
                if _script_job_process_alive(item):
                    item.update({
                        "status": "running",
                        "summary": f"{item.get('label') or 'Script'} running",
                        "finished_at": "",
                        "return_code": None,
                    })
                    recovered_running.append(dict(item))
                else:
                    rc = _parse_script_log_return_code(item.get("log_file"))
                    item.update({
                        "status": "success" if rc == 0 else "failed",
                        "summary": (
                            f"{item.get('label') or 'Script'} completed (rc={rc})"
                            if rc == 0
                            else f"{item.get('label') or 'Script'} interrupted by control-service restart"
                        ),
                        "finished_at": benchmark_utc_now(),
                        "return_code": 143 if rc is None else rc,
                    })
                queue[index] = item
                changed = True
        if changed:
            state["queue"] = queue
            if recovered_running:
                state = script_state_mirror_job(state, recovered_running[0])
            else:
                state["active"] = False
            write_script_job_state(state)
        has_queued = any(str((row or {}).get("status") or "") == "queued" for row in queue)
    for item in recovered_running:
        threading.Thread(target=monitor_recovered_script_job, args=(item,), name=f"club3090-script-recover-{item.get('job_id') or 'job'}", daemon=True).start()
    if has_queued:
        ensure_script_queue_worker()


def monitor_recovered_script_job(job):
    job = dict(job or {})
    job_id = str(job.get("job_id") or "")
    for _ in range(21600):
        if not _script_job_process_alive(job):
            break
        time.sleep(2)
    rc = _parse_script_log_return_code(job.get("log_file"))
    if rc is None:
        rc = 143
    with script_job_lock:
        state = read_script_job_state()
        queue = list(state.get("queue") or [])
        current_index = next(
            (index for index, row in enumerate(queue) if str((row or {}).get("job_id") or "") == job_id),
            -1,
        )
        if current_index >= 0:
            finished = dict(queue[current_index])
            if str(finished.get("status") or "") not in {"cancelled", "cancelling"}:
                finished.update({
                    "status": "success" if rc == 0 else "failed",
                    "summary": f"{finished.get('label') or 'Script'} {'completed' if rc == 0 else 'failed'} (rc={rc})",
                    "finished_at": benchmark_utc_now(),
                    "return_code": rc,
                })
            queue[current_index] = finished
            state["queue"] = queue
            next_queued = next(
                (dict(row) for row in queue if str((row or {}).get("status") or "") == "queued"),
                None,
            )
            write_script_job_state(script_state_mirror_job(state, next_queued or finished))
    ensure_script_queue_worker()


if __name__ == "__main__":
    recover_script_queue()
