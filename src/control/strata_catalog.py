import json
import os


STRATA_COMMIT = "82f46a8c8f475f001ad76d92f58f4a4f8ffb0253"
STRATA_IMAGE = "club3090-strata:v0.1.40.1"
STRATA_FIT_GUIDANCE_GB = {"Q2_0": 37.6, "IQ2_XS": 39.2, "IQ3_XXS": 47.0, "IQ3_S": 54.8}
STRATA_VARIANTS = (
    {"slug": "q2-0", "model": "Q2_0", "family": "qwen", "display": "Qwen 3.8 Flash Next — Strata Q2_0", "model_id": "qwen3.8-flash-next", "served": "qwen3.8-flash-next", "combined": 37.6},
    {"slug": "iq2-xs", "model": "IQ2_XS", "family": "qwen", "display": "Qwen 3.8 Flash Next — Strata IQ2_XS", "model_id": "qwen3.8-flash-next", "served": "qwen3.8-flash-next", "combined": 39.2},
    {"slug": "iq3-xxs", "model": "IQ3_XXS", "family": "qwen", "display": "Qwen 3.8 Flash Next — Strata IQ3_XXS", "model_id": "qwen3.8-flash-next", "served": "qwen3.8-flash-next", "combined": 47.0},
    {"slug": "iq3-s", "model": "IQ3_S", "family": "qwen", "display": "Qwen 3.8 Flash Next — Strata IQ3_S", "model_id": "qwen3.8-flash-next", "served": "qwen3.8-flash-next", "combined": 54.8},
    {"slug": "coder-iq1-m", "selector": "strata/qwen3.8-flash-next-coder-iq1-m", "model": "IQ1_M", "family": "coder", "display": "Qwen 3.8 Flash Next — Coder IQ1_M", "download": 58.4, "ram": 32, "caveat": "Half-expert coding specialization; weaker outside code and limited non-English/CJK performance."},
    {"slug": "swift-1-5-iq2-xs", "selector": "strata/swift-1-5-iq2-xs", "model": "IQ2_XS", "family": "swift", "display": "Qwen 3.8 Flash Next — Swift 1.5 IQ2_XS", "caveat": "Swift 1.5 thinks shorter; approximately the original model's same-size RAM requirements."},
    {"slug": "swift-1-5-iq3-xxs", "selector": "strata/swift-1-5-iq3-xxs", "model": "IQ3_XXS", "family": "swift", "display": "Qwen 3.8 Flash Next — Swift 1.5 IQ3_XXS", "caveat": "Swift 1.5 thinks shorter; approximately the original model's same-size RAM requirements."},
    {"slug": "unsloth-ud-iq4-xs", "selector": "strata/unsloth-ud-iq4-xs", "model": "UD-IQ4_XS", "family": "unsloth", "display": "Qwen 3.8 Flash Next — Unsloth UD-IQ4_XS", "download": 93.7, "ram": 48, "resident": 59.5, "nvme": True, "caveat": "Below approximately 80 GB RAM, expert offload to SSD/NVMe slows inference."},
    {"slug": "unsloth-ud-q4-k-xl", "selector": "strata/unsloth-ud-q4-k-xl", "model": "UD-Q4_K_XL", "family": "unsloth", "display": "Qwen 3.8 Flash Next — Unsloth UD-Q4_K_XL", "download": 111.3, "ram": 48, "resident": 77, "nvme": True, "status": "experimental", "caveat": "No vision. Requires NVMe; upstream reports 7–8.5 tokens/s with 64 GB RAM and a 12 GB GPU."},
    {"slug": "orcarouter-qwen3.8-flash-next-uncensored-iq3-xxs", "selector": "strata/orcarouter-qwen3.8-flash-next-uncensored-iq3-xxs", "model": "IQ3_XXS", "family": "orca", "display": "Qwen 3.8 Flash Next — OrcaRouter Uncensored IQ3_XXS", "model_id": "orcarouter-qwen3.8-flash-next-uncensored-iq3_xxs", "served": "orcarouter-qwen3.8-flash-next-uncensored-iq3_xxs", "install_mode": "orca", "status": "experimental", "download": 85.2, "resident": 49.8, "caveat": "85.20 GB gated two-shard download; compatibility packing and MTP preparation; 49.8 GiB expert arena before runtime buffers; text-only 32K. Original-model performance claims do not apply."},
)


def _strata_base_compose(model_token, family, service, data_root):
    volume = json.dumps(f"{data_root}:/data")
    return f'''services:
  {service}:
    image: {STRATA_IMAGE}
    environment:
      FAMILY: {family}
      MODEL: {model_token}
      CONTEXT: "32768"
      VISION: "no"
      LOW_RAM: auto
      HOST: 0.0.0.0
      PORT: "8080"
      GPU: "${{GPU:-0}}"
      API_KEY: "${{STRATA_API_KEY}}"
    ports:
      - "${{PORT}}:8080"
    volumes:
      - {volume}
    ulimits:
      memlock:
        soft: -1
        hard: -1
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    healthcheck:
      test: ["CMD-SHELL", "curl -fs http://127.0.0.1:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 600s
'''


def strata_builtin_custom_model_rows():
    root = os.path.abspath(os.path.join(CONTROL_DIR, "builtin-models"))
    source = os.path.join(root, "strata", "source")
    rows = []
    for variant in STRATA_VARIANTS:
        slug = variant["slug"]
        model_token = variant["model"]
        selector = variant.get("selector") or f"strata/qwen3.8-flash-next-{slug}"
        overlay = os.path.join(root, f"strata-qwen3.8-flash-next-{slug}" if variant["family"] == "qwen" else f"strata-{slug}")
        compose = os.path.join(overlay, "compose.yaml")
        data = os.path.join(overlay, "data")
        os.makedirs(overlay, exist_ok=True)
        text = _strata_base_compose(model_token, variant["family"], "strata", data)
        if variant.get("install_mode") == "orca":
            text = text.replace(
                "    ports:\n",
                '    entrypoint: ["/opt/strata/.venv/bin/python", "-m", "serve.server"]\n'
                '    command: ["--engine", "strata", "--config", "/data/config/strata-orca-iq3_xxs.json", "--host", "0.0.0.0", "--port", "8080"]\n'
                "    ports:\n",
            )
        if not os.path.isfile(compose) or open(compose, "r", encoding="utf-8").read() != text:
            with open(compose, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        os.makedirs(data, exist_ok=True)
        model_id = variant.get("model_id", "qwen3.8-flash-next")
        row = {
            "id": f"builtin-strata-{slug}", "slug": selector, "selector": selector,
            "display_name": variant["display"], "model_id": model_id,
            "model_display_name": "Qwen 3.8 Flash Next", "profile_model_id": model_id,
            "profile_engine_id": "strata", "engine": "strata", "engine_display": "Strata",
            "engine_profile": "strata", "topology": "single", "compose_path": compose,
            "compose_rel_path": os.path.relpath(compose, root).replace(os.sep, "/"),
            "compose_meta": {"service_name": "strata", "port": 8080, "served_model_name": variant.get("served", "qwen3.8-flash-next")},
            "inventory_origin": "control_catalog", "source_kind": "curated", "custom_preset": True,
            "install_command": "strata-image-build", "install_reason": "Install the pinned Strata runtime image and source checkout.",
            "strata_model_token": model_token, "strata_family": variant["family"],
            "strata_install_mode": variant.get("install_mode", "standard"),
            "strata_source_path": source, "strata_data_path": data,
            "strata_image": STRATA_IMAGE, "strata_commit": STRATA_COMMIT,
            "status_kind": variant.get("status", "production"),
            "download_size_gb": variant.get("download"),
            "recommended_system_memory_gb": variant.get("ram"),
            "recommended_resident_memory_gb": variant.get("resident"),
            "requires_nvme": bool(variant.get("nvme")),
            "recommended_combined_memory_gb": variant.get("combined"),
            "max_ctx": 32768, "vision": "no", "requires_min_gpu_count": 1, "requires_sm": "75+",
            "caveats": variant.get("caveat") or (f"Combined RAM+VRAM fit guidance: {variant['combined']:g} GB; advisory only (Strata low-RAM mode)." if variant.get("combined") else ""),
        }
        rows.append(row)
    return rows
