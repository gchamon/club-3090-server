# Strata model preset: technical implementation plan

## Context

Strata is a separate inference server for Qwen3.8-Flash-Next, with an OpenAI-compatible API and its own engine, model assets, setup, and runtime lifecycle. Club-3090 Server currently discovers runtime presets through its inventory and can launch instance-scoped Compose services, but its instance artifacts and selected runtime behaviors assume vLLM in several places. This plan defines the changes needed to offer Strata through the admin runtime preset flow and route compatible requests through the existing proxy; this is an implementation plan, not a report of a completed runtime test.

Use the pinned upstream Strata `v0.1.40.1` source at commit `82f46a8c8f475f001ad76d92f58f4a4f8ffb0253`. Strata documents a Linux NVIDIA Docker deployment built from its Dockerfile, persisting model/config assets at `/data`, serving on container port `8080`, and exposing `/health`, `/v1/models`, and `/v1/chat/completions`. Its Dockerfile sets a `/health` healthcheck and requires `--ulimit memlock=-1`; first start downloads model files into `/data`.

## Implementation plan

### 1. Add one builtin Strata model runtime to preset inventory

- Add `src/control/strata_catalog.py` and register it in `src/control/__init__.py` after `qwen38_catalog.py` and before `runtime_inventory.py`. Reuse `qwen38_builtin_custom_model_rows()`'s builtin-catalog insertion pattern; do not use the vLLM-only custom HF model import flow.
- Define one preset variant:
  - selector `strata/qwen3.8-flash-next-iq2-xs`
  - model ID `qwen3.8-flash-next`
  - display name `Qwen 3.8 Flash Next — Strata IQ2_XS`
  - engine family `strata`, engine display `Strata`
  - topology `single`, scope `single`
  - upstream settings `FAMILY=qwen`, `MODEL=IQ2_XS`, `CONTEXT=32768`, `VISION=no`, `LOW_RAM=auto`
- Do not expose Strata's `API_KEY`, internal `PORT`, image/version tag, model family/size, `GPUS`, or `LAYER_SPLIT` as user-editable generic launch settings. Keep the API key controller-managed, model image and preset version pinned, and model selection single-choice. Set `GPU` from the instance GPU assignment instead of exposing a second conflicting GPU selector.
- Generate a controller-owned Compose file at `${CLUB3090_CONTROL_DIR}/builtin-models/strata-qwen3.8-flash-next-iq2-xs/compose.yaml`. Pin service image `club3090-strata:v0.1.40.1`; map host instance port to container `8080`; mount `${CLUB3090_CONTROL_DIR}/builtin-models/strata-qwen3.8-flash-next-iq2-xs/data` at `/data`; set Strata environment above plus `HOST=0.0.0.0`, `PORT=8080`, and the managed API key; configure NVIDIA device reservation and `memlock: -1`. Set the healthcheck to upstream's `/health` behavior and 600-second start period. Do not publish a fixed host port in the base Compose file.

### 2. Add the image build/install and persistent resource lifecycle

- Add a Strata-specific install command/helper in the existing model install job path. Clone only the pinned repository commit into `${CLUB3090_CONTROL_DIR}/builtin-models/strata-qwen3.8-flash-next-iq2-xs/source`, verify the exact commit, and build `club3090-strata:v0.1.40.1` from that checkout. Never build from `main` or an unpinned checkout.
- Treat install as ready only when the expected image tag exists and the source checkout is at the pinned commit. Make repeat install idempotent: preserve the `/data` directory and source checkout, rebuild the image only when absent or when its pinned-version metadata is invalid.
- Keep model weights, prepared pack, MTP layer, and Strata install config in the persistent `/data` directory. Do not feed this runtime through Hugging Face file deletion or model-update operations. Surface a catalog caveat that model data is managed by Strata in `/data`; disable generic resource update/delete actions for this variant.
- The build phase needs outbound access to the pinned Strata Git repository and the upstream dependencies fetched by its Dockerfile; first runtime start needs outbound model-download access. Treat a denied fetch as a failed install/start with the upstream error visible in the admin runtime logs, while retaining any partially downloaded `/data` so a later retry can resume.
- Ensure missing source/network access, failed commit verification, Docker build failure, absent image, and unwritable data directory report a failed install state with actionable error text; do not mark the preset install-ready on a partial build.

### 3. Make runtime instance launch, readiness, and admin lifecycle engine-aware

- In `src/control/runtime_inventory.py`, preserve `strata` as its own engine family, display it as `Strata`, and include the builtin variant in the normal runtime variant/model inventory and `VARIANT_SPECS` lookup. Preserve selector, model ID, scope, compose service/path, install state, resource path, readiness path, and caveat in the API shape consumed by the UI.
- In `src/control/instances.py`, retain the existing per-instance Compose launch/stop path. For Strata only, omit VLLM/TorchInductor/Triton cache environment and cache volume creation; attach the Strata persistent `/data` volume and selected GPU; map the instance host port to Strata container port 8080. Leave existing vLLM instance overrides unchanged.
- Pass Strata `GPU` as the GPU ordinal exposed inside its container, derived from the instance's Compose device assignment and container-local ordinal remapping. Keep the assignment deterministic and verify it against the generated Compose configuration.
- Add Strata readiness behavior in `src/control/system.py` and the instance start path: require successful HTTP responses from both `/health` and `/v1/models`; TCP-open alone is not ready. Supply Strata's API key on the `/v1/models` probe. Preserve the existing 900-second model startup timeout and provide container logs on timeout/failure.
- Integrate Strata with the existing per-GPU admin instance controls and enabled-instance boot flow. Keep it instance-scoped; do not route it through `run_switch`, global runtime launch, or vLLM-specific systemd helpers. Ensure GPU overlap exclusion stops conflicting managed instances before launch and that stop/delete-instance operations stop the Strata Compose project without deleting persistent `/data`.
- Expose engine identity and Strata readiness/install state correctly in admin status. Do not report a Strata instance as the `club3090-vllm.service` runtime. Keep the existing service unit unchanged; Strata instance boot/stop is owned by the controller's instance lifecycle.

### 4. Route OpenAI-compatible requests through the existing proxy

- Use runtime selector `strata/qwen3.8-flash-next-iq2-xs` as the preset route, following `parse_preset_path()`'s `/v1/<selector>/...` and `/<selector>/...` forms. In `http_server.py`'s `forward()`, resolve the selector for GET and POST requests, not only completion requests. Route `GET /v1/strata/qwen3.8-flash-next-iq2-xs/models` to Strata `/v1/models`; route `POST /v1/strata/qwen3.8-flash-next-iq2-xs/chat/completions` to `/v1/chat/completions`.
- Resolve the route to a running Strata instance via `proxy_running_target_for_selector()` and `instances_snapshot()`. Do not let Strata fall through the `vllm_container_names()` global-container lookup or `ensure_proxy_swap_target()` / `run_switch()`. Admin UI owns Strata start/stop; if no matching Strata instance is running, return HTTP 503 with a clear “start this runtime from Instances” response rather than silently switching the global runtime.
- Store a controller-generated Strata API key at `${CLUB3090_CONTROL_DIR}/strata_api_key`, create it once with `secrets.token_urlsafe(32)`, and set file mode `0600` following `ensure_local_api_token()` in `src/control/mcp.py`. Inject its value into the Strata Compose environment and add `Authorization: Bearer <key>` only on controller-to-Strata requests. The existing proxy strips client `Authorization`, `X-API-Key`, and `api-key` before forwarding; preserve Club-3090's client authorization boundary and never forward client credentials upstream. Never expose the Strata API key in inventory, status, logs, generated browser data, or proxy responses.
- For Chat Completions, preserve the OpenAI request body, streaming flag, response status, JSON/SSE framing, tool calls, and errors Strata supports. Avoid vLLM-only request mutation for Strata unless it is part of the shared OpenAI-compatible contract. The exact request compatibility and stream framing must be verified against pinned upstream; if fields need adaptation, implement only specific documented mappings and do not claim general drop-in compatibility.
- Support model-list and non-streaming/streaming Chat Completions through both preset URL forms. Do not claim Anthropic or Responses API proxy support unless separately added and verified; the current proxy is centered on OpenAI-compatible paths.

### 5. Verify catalog, install, lifecycle, proxy, and regression behavior

- Add permanent smoke coverage in `src/build/smoke_tests.py` using isolated inventory and Compose fixtures:
  - exact Strata selector, model ID, engine, single scope, and install/readiness metadata appear in runtime inventory;
  - generated Compose has the pinned image, persistent `/data`, managed API key wiring, selected GPU reservation, and port mapping, with no fixed host port;
  - Strata instance override omits all three vLLM/Triton/TorchInductor caches while a pre-existing vLLM fixture retains them;
  - readiness does not pass on an open port or `/health` alone; both health and authenticated model-list probes must succeed;
  - the proxy selects a running Strata instance and maps preset `/models` and `/chat/completions` paths to the correct upstream paths without entering the global vLLM branch.
- Run `python3 -m build.smoke_tests` from repository root.
- On the configured Strata runtime, verify from admin UI: preset appears with engine `Strata`; install/build state transitions to ready only after pinned image is built; selected instance GPU starts one Strata instance; snapshot reports its selector, engine, port, and readiness; stop/start preserves `/data`.
- Exercise the real proxy with authenticated GET model list and Chat Completion POSTs using both `stream:false` and `stream:true`. Require a valid OpenAI response for non-streaming and forwarded SSE chunks ending in `[DONE]` for streaming. Verify a request with an unsupported payload produces the upstream's clear error rather than a controller-generated success.
- Start and stop an existing vLLM per-instance runtime before/after Strata; verify vLLM readiness, cache environment/mounts, and proxy routing remain unchanged. Check the Strata key is absent from inventory/API snapshots and logs.

## Critical files & anchors

- `src/control/__init__.py` — `_SOURCE_ORDER`; register the builtin catalog before runtime inventory loads.
- `src/control/qwen38_catalog.py` — `qwen38_builtin_custom_model_rows()`; use as the catalog generation precedent, not its GGUF download behavior.
- `src/control/runtime_inventory.py` — `_normalize_engine()`, builtin catalog append in `rebuild_runtime_inventory()`, and `_rebuild_runtime_mode_tables()`; project Strata identity into runtime APIs.
- `src/control/instances.py` — `write_instance_artifacts()`, `instance_compose_args()`, and `_instance_wait_until_ready()`; separate Strata data/GPU config from vLLM-only cache artifacts.
- `src/control/proxy_chat.py` — `parse_preset_path()`, `proxy_running_target_for_selector()`, and `ensure_proxy_swap_target()`; route Strata instance requests without invoking the global vLLM switch path.

## Feasibility status and assumptions

- **Implementation status:** the initial four original-Qwen presets and the special Coder, Swift 1.5, Unsloth, and OrcaRouter presets are implemented in the controller and covered by `strata_preset_smoke`; live hardware startup and authorized Orca downloads remain host-level integration checks.
- Pin Strata `v0.1.40.1` / commit `82f46a8c8f475f001ad76d92f58f4a4f8ffb0253`. If the pinned upstream Dockerfile or API contract changes, update the catalog/install contract and rerun integration verification rather than silently following `main`.
- Catalog scope includes the four original Qwen quantizations, Coder `IQ1_M`, Swift 1.5 `IQ2_XS` and `IQ3_XXS`, Unsloth `UD-IQ4_XS` and experimental `UD-Q4_K_XL`, and the distinct experimental OrcaRouter uncensored `IQ3_XXS` conversion preset. Other model families, AMD/HIP, multi-GPU, vision input, Anthropic/Responses proxy APIs, benchmarking, global-mode switching, and generic model resource update/delete remain excluded.
- Keep model bytes and user configuration persistent outside the image; image rebuild/update and stopping/deleting instances must not clear each variant's `/data`.

## Expanded special presets and timestamped logs

The four original Qwen entries remain unchanged. The added entries use the pinned Strata family/model tokens, distinct persistent data roots, and advisory fit metadata. Swift exposes only the two sizes supported by the pin; the experimental Unsloth and OrcaRouter rows remain installable. OrcaRouter is a separate gated download and compatibility-pack/MTP preparation path with a non-secret direct-server configuration; installation requires an HF token already authorized for its repository.

Human-readable control, audit, debug, streamed install/build, Docker runtime, and browser-generated log entries show their production time. Structured audit JSON retains its integer `ts`; historic log files are not rewritten.

The isolated `python3 src/build/build.py --smoke-tests strata_preset_smoke` test covers catalog metadata, Orca preparation contracts, and timestamped log behavior. It does not replace the pinned-host checks above, particularly real gated HF authorization, GPU startup, or live OpenAI-proxy traffic.
