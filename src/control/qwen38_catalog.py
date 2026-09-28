import json
import os


QWEN38_MODEL_PROFILE = {
    "id": "qwen3.8-27b",
    "display_name": "Qwen 3.8 27B",
    "family": "qwen35-dense",
    "hidden_size": 5120,
    "num_hidden_layers": 64,
    "num_gdn_layers": 48,
    "num_attn_layers": 16,
    "num_attn_heads": 24,
    "num_kv_heads": 4,
    "head_dim_attn": 256,
    "linear_num_v_heads": 48,
    "linear_num_k_heads": 16,
    "linear_v_head_dim": 128,
    "linear_k_head_dim": 128,
    "linear_conv_kernel_dim": 4,
    "max_ctx_supported": 262144,
    "attention_k_eq_v": False,
    "vision_capable": True,
    "default_weight_variant": "hauhaucs-aggressive-iq4xs",
    "requires_min_vram_gb": 20,
}

QWEN38_WEIGHT_VARIANTS = (
    {
        "variant": "orcarouter-uncensored-iq4xs",
        "repo": "orcarouter/Qwen3.8-27B-Uncensored-GGUF",
        "model_file": "Qwen3.8-27B-Uncensored-IQ4_XS.gguf",
        "mmproj_file": "mmproj-Qwen3.8-27B-Uncensored-f16.gguf",
        "mmproj_kind": "f16",
        "size_gb": 15.3,
        "mmproj_size_gb": 0.93,
        "subdir": "qwen3.8-27b-gguf/orcarouter-uncensored-iq4xs",
        "name": "OrcaRouter Uncensored IQ4_XS",
        "caveats": "Experimental third-party GGUF. The Hugging Face repository is gated and requires an authenticated account that accepted its access terms. Publisher behavior and quality are not independently validated.",
    },
    {
        "variant": "hauhaucs-aggressive-iq4xs",
        "repo": "HauhauCS/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-MTP-GGUF",
        "model_file": "Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-IQ4_XS.gguf",
        "mmproj_file": "mmproj-Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-BF16.gguf",
        "mmproj_kind": "bf16",
        "size_gb": 15.71,
        "mmproj_size_gb": 0.93,
        "subdir": "qwen3.8-27b-gguf/hauhaucs-aggressive-iq4xs",
        "name": "HauhauCS Aggressive IQ4_XS",
        "caveats": "Experimental third-party GGUF containing the native NextN/MTP head. This does not use the optional publisher-patched FastMTP-32K sidecar. Publisher behavior, quality, and performance are not independently validated.",
    },
)


def _qwen38_vision_compose(service_name, model_cache_root, model_file, mmproj_file):
    volume = json.dumps(f"{model_cache_root}:/models:ro")
    return f'''services:
  {service_name}:
    image: ${{LLAMACPP_IMAGE:-ghcr.io/ggml-org/llama.cpp:server-cuda}}
    container_name: "${{ESTATE_CONTAINER:-{service_name}}}"
    restart: unless-stopped
    ports:
      - "${{ESTATE_PORT:-${{PORT:-8020}}}}:8080"
    volumes:
      - {volume}
    command: >-
      --host 0.0.0.0
      --port 8080
      -m /models/{model_file}
      --mmproj /models/{mmproj_file}
      --image-min-tokens ${{IMAGE_MIN_TOKENS:-1024}}
      --image-max-tokens ${{IMAGE_MAX_TOKENS:-1024}}
      -c ${{CTX_SIZE:-65536}}
      -b ${{BATCH_SIZE:-1024}}
      -ub ${{UBATCH_SIZE:-1024}}
      -ngl 99
      -fa on
      --cache-type-k ${{KV_TYPE:-q4_0}}
      --cache-type-v ${{KV_TYPE:-q4_0}}
      -np ${{NP:-1}}
      --spec-type draft-mtp
      --spec-draft-n-max ${{MTP_DRAFT_N_MAX:-2}}
      --jinja
      --reasoning ${{REASONING:-off}}
      --reasoning-format ${{REASONING_FORMAT:-deepseek}}
      --temp ${{TEMP:-${{TEMPERATURE:-0.6}}}}
      --top-p ${{TOP_P:-0.95}}
      --top-k ${{TOP_K:-20}}
      --min-p ${{MIN_P:-0.0}}
      --repeat-penalty ${{REPEAT_PENALTY:-1.0}}
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ["${{ESTATE_GPUS:-${{CUDA_VISIBLE_DEVICES:-0}}}}"]
              capabilities: [compute, utility]
'''


def qwen38_builtin_custom_model_rows():
    model_cache_root = os.path.abspath(_resolve_variant_model_dir_root({}))
    overlay_root = os.path.join(CONTROL_DIR, "builtin-models", "qwen3.8-27b")
    rows = []
    for weight in QWEN38_WEIGHT_VARIANTS:
        variant = weight["variant"]
        selector = (
            "llamacpp/qwen38-27b-single-iq4xs"
            if variant == "orcarouter-uncensored-iq4xs"
            else "llamacpp/qwen38-27b-hauhaucs-aggressive-single-iq4xs"
        )
        service_name = "llama-cpp-" + selector.rsplit("/", 1)[-1].replace("_", "-")
        compose_dir = os.path.join(overlay_root, variant)
        compose_path = os.path.join(compose_dir, "mtp-vision.yml")
        os.makedirs(compose_dir, exist_ok=True)
        compose_text = _qwen38_vision_compose(
            service_name,
            model_cache_root,
            f"{weight['subdir']}/{weight['model_file']}",
            f"{weight['subdir']}/{weight['mmproj_file']}",
        )
        write_text_atomic_if_changed(compose_path, compose_text)
        recipe = {
            "WEIGHT_REPO": weight["repo"],
            "WEIGHT_FILES": f"{weight['model_file']} {weight['mmproj_file']}",
            "WEIGHT_SUBDIR": weight["subdir"],
        }
        target_dir = _recipe_subdir_host_path(model_cache_root, recipe)
        rows.append(
            {
                "id": selector.rsplit("/", 1)[-1],
                "selector": selector,
                "registry_key": selector,
                "profile_like": selector,
                "model_id": QWEN38_MODEL_PROFILE["id"],
                "profile_model_id": QWEN38_MODEL_PROFILE["id"],
                "model_display_name": QWEN38_MODEL_PROFILE["display_name"],
                "custom_preset": True,
                "inventory_origin": "control_catalog",
                "profile_engine_id": "llama-cpp-local",
                "profile_workload_id": "vision-coding",
                "profile_drafter_id": "qwen-mtp-builtin",
                "vision": "vision",
                "weights_variant": variant,
                "weights_repo": weight["repo"],
                "weights_files": [weight["model_file"], weight["mmproj_file"]],
                "weight_size_gb": weight["size_gb"],
                "mmproj_size_gb": weight["mmproj_size_gb"],
                "requires_min_vram_gb": QWEN38_MODEL_PROFILE["requires_min_vram_gb"],
                "requires_min_gpu_count": 1,
                "status_kind": "experimental",
                "caveats": weight["caveats"],
                "best_for": "Experimental single-GPU vision coding and multimodal chat with built-in MTP speculation.",
                "quality_summary": "Third-party uncensored IQ4_XS GGUF with a matching vision projector.",
                "compose_path": compose_path,
                "compose_rel_path": f"control-builtin-models/qwen3.8-27b/{variant}/mtp-vision.yml",
                "host_model_dir": target_dir,
                "install_command": _recipe_download_command(model_cache_root, recipe),
                "install_reason": f"Download both the model and {weight['mmproj_kind'].upper()} vision projector from {weight['repo']} into {target_dir}.",
                "compose_meta": {"max_model_len": 65536, "kv_format": "q4_0", "max_num_seqs": 1},
            }
        )
    return rows
