import json
import os


STRATA_COMMIT = "82f46a8c8f475f001ad76d92f58f4a4f8ffb0253"
STRATA_IMAGE = "club3090-strata:v0.1.40.1"
STRATA_FIT_GUIDANCE_GB = {"Q2_0": 37.6, "IQ2_XS": 39.2, "IQ3_XXS": 47.0, "IQ3_S": 54.8}
STRATA_VARIANTS = (
    ("q2-0", "Q2_0", "Qwen 3.8 Flash Next — Strata Q2_0"),
    ("iq2-xs", "IQ2_XS", "Qwen 3.8 Flash Next — Strata IQ2_XS"),
    ("iq3-xxs", "IQ3_XXS", "Qwen 3.8 Flash Next — Strata IQ3_XXS"),
    ("iq3-s", "IQ3_S", "Qwen 3.8 Flash Next — Strata IQ3_S"),
)


def _strata_base_compose(model_token, service, data_root):
    volume = json.dumps(f"{data_root}:/data")
    return f'''services:
  {service}:
    image: {STRATA_IMAGE}
    environment:
      FAMILY: qwen
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
    for slug, model_token, display in STRATA_VARIANTS:
        selector = f"strata/qwen3.8-flash-next-{slug}"
        overlay = os.path.join(root, f"strata-qwen3.8-flash-next-{slug}")
        compose = os.path.join(overlay, "compose.yaml")
        data = os.path.join(overlay, "data")
        os.makedirs(overlay, exist_ok=True)
        text = _strata_base_compose(model_token, "strata", data)
        if not os.path.isfile(compose) or open(compose, "r", encoding="utf-8").read() != text:
            with open(compose, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        os.makedirs(data, exist_ok=True)
        rows.append({
            "id": f"builtin-strata-{slug}", "slug": selector, "selector": selector,
            "display_name": display, "model_id": "qwen3.8-flash-next",
            "model_display_name": "Qwen 3.8 Flash Next", "profile_model_id": "qwen3.8-flash-next",
            "profile_engine_id": "strata", "engine": "strata", "engine_display": "Strata",
            "engine_profile": "strata", "topology": "single", "compose_path": compose,
            "compose_rel_path": os.path.relpath(compose, root).replace(os.sep, "/"),
            "compose_meta": {"service_name": "strata", "port": 8080, "served_model_name": "qwen3.8-flash-next"},
            "inventory_origin": "control_catalog", "source_kind": "curated", "custom_preset": True,
            "install_command": "strata-image-build", "install_reason": "Install the pinned Strata runtime image and source checkout.",
            "strata_model_token": model_token, "strata_source_path": source, "strata_data_path": data,
            "strata_image": STRATA_IMAGE, "strata_commit": STRATA_COMMIT,
            "recommended_combined_memory_gb": STRATA_FIT_GUIDANCE_GB[model_token],
            "max_ctx": 32768, "vision": "no", "requires_min_gpu_count": 1, "requires_sm": "75+",
            "caveats": f"Combined RAM+VRAM fit guidance: {STRATA_FIT_GUIDANCE_GB[model_token]:g} GB; advisory only (Strata low-RAM mode).",
        })
    return rows
