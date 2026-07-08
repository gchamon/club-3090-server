# Club-3090 Server

Single-file installer for a [club-3090](https://github.com/noonghunna/club-3090) inference host, providing a full-featured browser admin control panel, distro-aware install/update logic, systemd service setup, a reverse proxy that automatically routes requests to the correct containers via a single endpoint with optional configurable vLLM setting presets, live log management, GPU power and fan speed controls, multi-instance GPU orchestration, and API access control for multiple users.

This repository is the server-management layer. It integrates with the upstream [club-3090](https://github.com/noonghunna/club-3090) runtime and, on a fresh install clones that upstream repo automatically into `/opt/ai/club-3090` before wiring up the control plane.

## Important Notes

- Users are encouraged to first deploy [club-3090](https://github.com/noonghunna/club-3090) to /opt/ai/, follow the Quick Start Guide in the original project and ensure that everything works correctly before attempting to deploy Club-3090-Server. If /opt/ai/club-3090 is not found, the script will automatically clone the latest repo for you and deploy it in that location and attempt to run setup.sh and set everything up for you anyway, but it's best to first familiarize yourself with the original project's strengths and ensure it meets your needs and works correctly before attempting to host a server.
- The latest release of this script tracks the original repo's fast evolving architecture, with the current compatibility gate covering the upstream `v0.10.1*` release family. The admin panel shows an unsupported-checkout warning when the local upstream `club-3090` checkout falls outside the release patterns baked into the installer. You may let `--migrate` pull the latest upstream checkout, but if upstream introduced breaking changes, use that warning as a cue to audit the affected presets or AI Studio lanes before treating the host as production-ready.

## What This Script Provides

- Fully self contained script that handles everything you need to self-host a club-3090 based inference server, optimized for headless Arch and Debian/Ubuntu based distros
- A control stack installed under `/opt/club3090-control` and an admin web panel running on `localhost:8008/admin`
- An OpenAI-compatible proxy on `:8009` so you can chat with the LLM on a unified port regardless of what docker containers are in use.
- GPU-aware backend selection with per-GPU and multi-instance runtime management for single-card, dual-card or multi-card presets with dynamic runtime inventory discovery from the local `club-3090` checkout
- A modern scope model built around `GLOBAL`, `GPU<n>`, and `PAIRx_y` targets, including built-in sequential auto-pairs and custom user-defined pairs
- A Presets experience that includes model-summary relaunch surfaces, Setup Assistant recommendations, selector-scoped launch overrides, and a first-class Custom Model import path backed by upstream `pull.sh`
- Built-in local inference chat with server-persisted conversations across browsers/devices, per-conversation saved settings, folders, automatic conversation naming, system-prompt templates, rich markdown/media rendering, collapsible thinking trace rendering, local attachments, and automatic context compaction/rollover
- AI Studio integration for multimodal Plan, Interactive, and upstream Backend Plan workflows, including upstream image, video, speech, music, and SFX lanes, one-click setup/download controls, gallery browsing, persistent proof conversations, and dynamic Director placement
- Model Scores benchmarking for Quick and Full preset validation, with live queue monitoring, per-stage logs, GPU telemetry, thermal protection, resume/retry handling, score badges on preset cards, and artifact cleanup that keeps only authoritative current evidence
- Live Docker, Audit, and Debug log streaming that stays aware of multiple backend containers, including an interactive debug-shell lane with autocomplete, history, upload/download helpers, and zip-based folder transfers
- Preset launch state that only flips to `Active` after the backend fully finishes booting, with boot/error browser notifications and fast failure reporting when a compose never actually starts a container
- UI-driven model download/setup jobs with stdout/stderr streamed into Audit Logs
- Hardware metrics, uptime, health reporting, detachable Metrics popouts, storage browsing/editing helpers, persisted peak tracking, and backend auto-start and manual control, as well as full server remote management controls
- HTTPS admin sessions that survive controller restarts/updates, plus a cached offline admin shell on secure `/admin` routes so refreshes can show the last known panel state while the remote service is temporarily unreachable and reconnect automatically when service returns
- Optional GDDR6/GDDR6X junction and VRAM temperature telemetry in the Main GPU cards and Metrics graphs, using a vendored helper source/header compiled locally when supported
- Power presets, fan speed control, idle downclocking, and system information for remote server management
- Create dynamic instances and run multiple docker containers per GPU or GPU Pairs and be able to run inference on a single unified endpoint with different configurable vLLM setting presets 
- Optional per-user API key authentication, access control, and optional quota enforcement
- An optional loopback-only automation API for local tools on the same machine
- Optional `--online` mode that opens and forwards only the admin/proxy ports to the internet
- Optional `--online use-https` mode that enables a Caddy-backed self-signed HTTPS frontend for the admin panel and proxy
- Docker logs automatically printed to tty1 and last instance autostart if the kernel condition club3090.server=1 is active
- Optional `--skip-temps` installer switch for operators who do not want the extra temperature helper, dependency install, bootloader `iomem=relaxed` staging, or reboot notice

## Screenshots
Video coming soon.
Click any thumbnail to open the full-size screenshot.

<p align="center">
  <a href="./screenshots/1.%20Main%20Window.png"><img src="./screenshots/1.%20Main%20Window.png" alt="1. Main Window" width="260" /></a>
  <a href="./screenshots/2.%20System%20Tab.png"><img src="./screenshots/2.%20System%20Tab.png" alt="2. System Tab" width="260" /></a>
  <a href="./screenshots/3.%20System%20Tab%20pt%202.png"><img src="./screenshots/3.%20System%20Tab%20pt%202.png" alt="3. System Tab pt 2" width="260" /></a>
  <a href="./screenshots/4.%20Presets.png"><img src="./screenshots/4.%20Presets.png" alt="4. Presets" width="260" /></a>
  <a href="./screenshots/5.%20Presets%20pt%202.png"><img src="./screenshots/5.%20Presets%20pt%202.png" alt="5. Presets pt 2" width="260" /></a>
  <a href="./screenshots/6.%20Users.png"><img src="./screenshots/6.%20Users.png" alt="6. Users" width="260" /></a>
  <a href="./screenshots/7.%20Metrics.png"><img src="./screenshots/7.%20Metrics.png" alt="7. Metrics" width="260" /></a>
  <a href="./screenshots/8.%20Metrics%20pt%202%20.png"><img src="./screenshots/8.%20Metrics%20pt%202%20.png" alt="8. Metrics pt 2" width="260" /></a>
  <a href="./screenshots/9.%20Metrics%20pt%203.png"><img src="./screenshots/9.%20Metrics%20pt%203.png" alt="9. Metrics pt 3" width="260" /></a>
  <a href="./screenshots/10.%20Metrics%20pt%204.png"><img src="./screenshots/10.%20Metrics%20pt%204.png" alt="10. Metrics pt 4" width="260" /></a>
  <a href="./screenshots/11.%20Metrics%20pt%205.png"><img src="./screenshots/11.%20Metrics%20pt%205.png" alt="11. Metrics pt 5" width="260" /></a>
  <a href="./screenshots/12.%20Logs.png"><img src="./screenshots/12.%20Logs.png" alt="12. Logs" width="260" /></a>
  <a href="./screenshots/13.%20Run%20Script.png"><img src="./screenshots/13.%20Run%20Script.png" alt="13. Run Script" width="260" /></a>
  <a href="./screenshots/14.%20Chat%20UI.png"><img src="./screenshots/14.%20Chat%20UI.png" alt="14. Chat UI" width="260" /></a>
  <a href="./screenshots/15.%20Chat%20UI%20pt%202.png"><img src="./screenshots/15.%20Chat%20UI%20pt%202.png" alt="15. Chat UI pt 2" width="260" /></a>
  <a href="./screenshots/16.%20API%20Presets.png"><img src="./screenshots/16.%20API%20Presets.png" alt="16. API Presets" width="260" /></a>
  <a href="./screenshots/17.%20Benchmarks.png"><img src="./screenshots/17.%20Benchmarks.png" alt="17. Benchmarks" width="260" /></a>
  <a href="./screenshots/18.%20Detailed%20Benchmark%20Scores.png"><img src="./screenshots/18.%20Detailed%20Benchmark%20Scores.png" alt="18. Detailed Benchmark Scores" width="260" /></a>
  <a href="./screenshots/19.%20Model%20Manager.png"><img src="./screenshots/19.%20Model%20Manager.png" alt="19. Model Manager" width="260" /></a>
  <a href="./screenshots/20.%20Custom%20Models.png"><img src="./screenshots/20.%20Custom%20Models.png" alt="20. Custom Models" width="260" /></a>
  <a href="./screenshots/21.%20Preset%20Launch%20Settings.png"><img src="./screenshots/21.%20Preset%20Launch%20Settings.png" alt="21. Preset Launch Settings" width="260" /></a>
  <a href="./screenshots/22.%20Duplicate%20Presets.png"><img src="./screenshots/22.%20Duplicate%20Presets.png" alt="22. Duplicate Presets" width="260" /></a>
  <a href="./screenshots/23.%20Setup%20Assistant.png"><img src="./screenshots/23.%20Setup%20Assistant.png" alt="23. Setup Assistant" width="260" /></a>
  <a href="./screenshots/24.%20AI%20Studio.png"><img src="./screenshots/24.%20AI%20Studio.png" alt="24. AI Studio" width="260" /></a>
  <a href="./screenshots/25.%20AI%20Studio%20Gallery.png"><img src="./screenshots/25.%20AI%20Studio%20Gallery.png" alt="25. AI Studio Gallery" width="260" /></a>
  <a href="./screenshots/26.%20Preset%20Filter.png"><img src="./screenshots/26.%20Preset%20Filter.png" alt="26. Preset Filter" width="260" /></a>
  <a href="./screenshots/27.%20Dynamic%20Documentation.png"><img src="./screenshots/27.%20Dynamic%20Documentation.png" alt="27. Dynamic Documentation" width="260" /></a>
  <a href="./screenshots/28.%20File%20Navigator.png"><img src="./screenshots/28.%20File%20Navigator.png" alt="28. File Navigator" width="260" /></a>
  <a href="./screenshots/29.%20File%20Editor.png"><img src="./screenshots/29.%20File%20Editor.png" alt="29. File Editor" width="260" /></a>
  <a href="./screenshots/30.%20Hex%20Editor.png"><img src="./screenshots/30.%20Hex%20Editor.png" alt="30. Hex Editor" width="260" /></a>
</p>


## Quick Start Guide

This section is written for someone who just wants the server working and may not be so familiar with the complexities of LLM configuration.

### What this project does

- [club-3090](https://github.com/noonghunna/club-3090) is the stack that actually runs the AI models
- this server script adds a browser-based admin panel, a stable proxy port, logs, power controls, and easier model/preset management
- after setup, you can control everything from the admin panel instead of manually typing long terminal commands

### Before you begin

Make sure your Linux machine already has:

- a supported NVIDIA GPU
- working NVIDIA drivers
- Docker
- internet access
- a normal Linux user account that can use `sudo`

If you plan to download gated Hugging Face models, also have your Hugging Face token ready.

By default the installer also prepares optional GDDR6/GDDR6X junction and VRAM temperature telemetry for supported NVIDIA cards. It vendors the helper source and NVIDIA NVML header inside the installer, compiles the helper locally against the host NVIDIA/libpci libraries, stages the required `iomem=relaxed` kernel command-line flag when it is not already active, and tells you to reboot only when that reboot is needed for the new readings to work.

### Step 1: Run the installer

Run the installer directly:

```bash
curl -fsSL https://tinyurl.com/club-3090-webserver | bash
```

If you already downloaded this repo locally, you can also run:

```bash
bash install-club3090-server.sh
```

If you need gated model downloads and already have a Hugging Face token, use:

```bash
curl -fsSL https://tinyurl.com/club-3090-webserver | \
  HF_TOKEN=hf_xxx bash
```

On a fresh machine, the installer will create `/opt/ai/` if needed, clone the upstream `club-3090` repo into `/opt/ai/club-3090`, fix script permissions, and then continue with the normal setup.

### Step 2: Open the admin panel

When the installer finishes, open a browser and go to:

```text
http://YOUR-SERVER-IP:8008/admin
```

If you installed with custom ports, replace `8008` with your chosen admin port.

### Step 3: Log in

When the login screen appears, sign in with your normal Linux user credentials.

Use:

- your Linux username
- your Linux password

In other words, log in with the same account you would normally use for `sudo` or for signing into that Linux machine. The admin panel does not create a separate default password for you.

### Step 4: Download or prepare a model

After logging in, open the `Presets` tab.

You will see discovered model presets from the local `club-3090` checkout. Some presets may show that downloads are still required.

If a preset is not ready:

1. Click its `Download` button.
2. Wait for the download/setup job to finish.
3. Watch progress in `Audit Logs`.

If you prefer to prepare the model manually in the terminal first, a common example is:

```bash
cd /opt/ai/club-3090
bash scripts/setup.sh qwen3.6-27b
```

Some advanced presets, such as DFlash variants, may require extra model files. The admin panel will usually tell you what command is needed.

### Step 5: Start your first preset

Still in the `Presets` tab:

1. Pick the model you want.
2. Pick a preset that says it is ready.
3. Click `Apply`.
4. The UI will jump into Docker Logs immediately so you can follow the launch.
5. Wait while the instance launches.
6. When startup completes successfully, the ready badge flips to `Active`, the card shows how long launch took, and the action button becomes `Stop`

If something fails, the preset will show `Error` and the logs will show what happened.

For most beginners:

- Use a single-GPU preset if you only want one model running on one GPU, or the global scope to automatically distribute presets to all available GPUs.
- Use the default or recommended preset first before trying special variants like long-context, dual-card, turbo, or DFlash
- Test if inference is working correctly via the built-in chat interface and watch the generated statistics

### Step 6: Test the AI server

Once a preset is active, the proxy is usually available on:

```text
http://YOUR-SERVER-IP:8009/v1
```

That proxy gives you one stable API endpoint even if you switch between different backends later.

You can test it with:

```bash
curl http://YOUR-SERVER-IP:8009/v1/models
```

Or with a chat request:

```bash
curl -s http://YOUR-SERVER-IP:8009/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.6-27b-autoround","messages":[{"role":"user","content":"Hello"}],"max_tokens":128}'
```

### Step 7: Everyday admin panel usage

Here is the simple mental model for the main tabs:

- `Main`: quick status, running containers, uptime, and GPU overview
- `System`: service controls, power/fan controls, and machine information
- `Presets`: download models, start/stop presets, and manage which runtime is active
- `Chat`: built-in local streaming chat client with server-backed conversation storage, lazy detail loading, per-conversation stats caching, share/export links, configuration, and local or remote MCP servers
- `AI Studio`: multimodal setup, model-resource checks, gallery browsing, and Plan/Interactive generation lanes from the Presets and Chat surfaces
- `Users`: create API users and keys if you want to share the server safely
- `Metrics`: request counts, usage history, runtime performance data, storage browsing, and detachable monitoring
- `Logs`: Docker logs and audit logs for troubleshooting

### Common first tasks

After installation, most people will want to do these things:

1. Log in with their Linux username and password.
2. Open `Presets`.
3. Download the model files the desired preset needs.
4. Click `Launch` on a recommended preset.
5. Wait until it becomes `Active`.
6. Copy the proxy base URL `http://YOUR-SERVER-IP:8009/v1` into their AI client.

### If you want to use an app like Open WebUI, Cline, or another OpenAI-compatible client

Most OpenAI-compatible apps need:

- Base URL: `http://YOUR-SERVER-IP:8009/v1`
- API key: only if you enabled user/API-key protection
- Model name: whichever model the active backend serves

If the client asks for an endpoint and does not mention presets, start with the plain proxy URL above.

### If something does not work

Try these checks in order:

1. Confirm the admin panel opens.
2. Confirm you can log in with your Linux user credentials.
3. Confirm the preset you selected finished downloading.
4. Confirm the preset reached `Active`, not just `Booting`.
5. Read `Docker Logs` and `Audit Logs` for the exact failure message.
6. Confirm Docker and the NVIDIA driver are working on the Linux host.

If you changed the upstream repo manually or pulled a new upstream version, run update or migrate again so the control layer and upstream runtime stay in sync.

## Supported Linux Families

- Arch
- Manjaro
- EndeavourOS
- Ubuntu
- Debian
- Linux Mint
- Pop!_OS

The script reads `/etc/os-release` and installs the right package names for the detected family.

## Requirements

- Linux with `systemd`
- NVIDIA drivers already installed
- Docker already installed and usable
- Docker Compose plugin or compatible `docker compose`
- Internet access so the installer can clone the upstream `club-3090` repo into `/opt/ai/club-3090` on first install

## Supported Runtime Presets

As of `v0.5`, the server no longer ships a hardcoded preset catalog. Instead it scans the local upstream repo under `/opt/ai/club-3090`, parses compose headers and compose files directly, and builds `/opt/club3090-control/runtime_inventory.json`.

That means the Presets tab now reflects whatever models and variants exist in the checked-out upstream repo, including:

- single-GPU presets
- dual-GPU presets
- multi-GPU presets
- experimental or caveat-marked upstream variants

Upstream switch tags such as `vllm/default`, `vllm/dual`, `vllm/gemma-mtp`, and `llamacpp/default` are still recognized when present, but the control layer can also launch compose variants that are only discoverable by scanning the repo tree.

Since the broader `v0.8.x`, `v0.9.x`, and `v0.10.x` migrations, the inventory path is also registry/profile-aware and understands the newer nested upstream compose hierarchy, so the admin panel can surface richer upstream metadata such as:

- preview, production, experimental, and caveat-marked variants
- structured launch defaults pulled from compose/profile metadata instead of a local hardcoded table
- compose-registry aliases, shared profile resources, and newer upstream families such as `autoround-int4`, `awq`, `unsloth-q4km`, `ubergarm-iq4ks`, and `ex0bit-prism`
- v0.10-era Gemma, DiffusionGemma, Qwen Omni, LMCache, NVFP4, Agents-A1, incubating, pod-aware, and upstream-gated variants when they are present in the local checkout
- profile-driven asset planning for model paths, draft models, projectors, Hugging Face cache-backed assets, directory-backed vLLM resources, and setup-script driven resources
- family summaries and model-summary relaunch cards
- built-in and custom API-preset aware routes
- Custom Model imports that register as persistent local runtime cards once upstream import succeeds, while control-owned wrappers keep local compatibility adaptations out of the upstream checkout

## Preset UX And Scope Model

The older single-mode/legacy-dual distinction has gradually been replaced by a clearer scope-oriented control model.

The admin panel now thinks in terms of:

- `GLOBAL`: fan a compatible preset out across every eligible target automatically
- `GPU0`, `GPU1`, `GPU2`, ...: explicit single-card targets
- `PAIR0_1`, `PAIR2_3`, ...: dual-card targets
- built-in automatic sequential pairs plus custom user-defined pairs

Important behaviors added across the `v0.7.x` and `v0.8.x` series include:

- built-in auto-pairs are preserved separately from custom pairs
- Global single-card and Global dual-card launches fan out in parallel instead of waiting for each target to finish before starting the next one
- generated compose overrides now keep host GPU reservation separate from the in-container CUDA ordinal view, which is critical for higher-index GPUs and pairs
- preset cards can expose selector-scoped Launch Settings overrides sourced from compose/profile metadata
- preset cards show richer disk/download status, shared-resource markers, provenance tooltips, and safer delete dialogs that preview the exact files and reclaim size
- per-runtime Generation Statistics reflect the actual launched context and runtime state rather than only a static catalog guess
- Setup Assistant / Preset Recommendation Survey can recommend curated presets based on detected hardware and desired rollout style

If you use many presets often, the Summary view is also worth calling out. It keeps a relaunch-oriented cache of recent and active presets per model, including temporary boot entries and bulk stop/restart actions.

## Custom Model Imports

One of the biggest `v0.8.x` additions is the first-class Custom Model flow in the Presets tab.

Instead of manually treating every non-curated model as a one-off local hack, the panel now supports:

- a dedicated `[+] Custom Model` entry point
- import flows that delegate to upstream `scripts/pull.sh`
- streaming import progress and gate/caveat output into Audit Logs
- reference-profile guidance so imports can reuse a known-good compose shape
- persistent registration of successful imports as local runtime cards
- removal flows that clean up the registered runtime state instead of leaving orphaned cards behind

This keeps the UI model-first while still deferring the actual import/evaluation logic to upstream Club-3090.

## AI Studio And Multimodal Workflows

The admin panel now includes a first-class AI Studio surface for upstream Club-3090's unified `ai-studio` scene. It is meant to make image, video, audio, and speech workflows usable from the same browser panel as inference presets.

Current AI Studio support includes:

- one-click Setup AI Studio, start/stop, model download, and resource detection controls
- Resource Manager grouping for Studio assets by image, video, audio, and speech modality
- generated-media gallery browsing backed by the repo-local ComfyUI output tree
- Plan and Interactive modes in the Chat interface, so a single request can be decomposed into text, image, speech, video, music, or SFX steps
- dynamic Studio Director placement: the Director defaults to GPU-first auto placement for fast planning, falls back to an already-loaded chat runtime when possible, and offloads to CPU only when media lanes need the VRAM or CPU is explicitly requested
- compatibility with the current upstream v0.10 AI Studio lanes, including HiDream-O1, Ideogram 4, Chroma, Z-Image, Krea 2, LTX/Sulphur, 10Eros, Wan2.2, ACE-Step music, Stable Audio Open SFX, Kokoro, and Step-Audio
- model readiness, storage usage, related resource subcards, and Download actions only for lanes whose shared or primary assets are genuinely not installed yet
- a separate Backend Plan option for upstream's Production Director flow, alongside the original local Plan and Interactive modes

The control layer keeps AI Studio integration in its own wrapper/setup logic instead of patching files inside the upstream checkout. Legacy `/admin/image-studio/...` routes remain as backend compatibility aliases, but the browser and current API surface use `/admin/ai-studio/...`.

## Model Scores And Benchmarking

Model Scores are the built-in preset validation and scoring system. They are designed to answer two different questions:

- Quick scores: a shorter run for launch, throughput, basic quality, reasoning, safety, and metadata checks
- Full scores: a longer validation pass with stress, soak, quality, sandbox behavior packs, reasoning suites, compliance, resource peaks, and final weighted score summaries

The Benchmarks modal and preset score badges are backed by saved artifacts under `/opt/club3090-control/benchmarks`. The current score reader only treats a Quick or Full result as valid when every required stage for that mode has a saved zero return code. Partial selected-stage shells, stale failures, and superseded sidecar JSON are ignored or archived so old artifacts do not masquerade as current scores.

Benchmark behavior includes:

- live Running, Finished, Failed, Skipped, Already Scored, Experimental, and Deprecated queue groups
- a persisted benchmark inventory cache and compact status polling path, so opening the modal or refreshing the admin panel does not repeatedly rescan large historical artifacts
- compact live refreshes while a benchmark is active, so stage labels, logs, and ETA update without blocking behind full inventory rescans
- a collapsed Benchmark monitor with total progress, per-running-preset progress, GPU temperature/power/fan telemetry, and a Finished state for review
- per-stage logs and detailed score summaries with direct artifact evidence links
- selected-stage reruns for repairing missing or failed categories without forcing a complete re-benchmark
- per-stage evidence coloring and status icons for completed, failed, stale, active, next, and deferred work
- scheduler handling for single-GPU, dual-GPU, exclusive sandbox, strict thermal retry, and multi-GPU machines
- thermal protection that preserves required Fast/Turbo speed profiles for throughput, pauses hot runtimes for cooldown, aborts only after the configured sustained guard windows, and has an emergency critical trip for truly unsafe temperatures

## Metrics, Storage, And Offline Admin Resilience

The Metrics tab now uses lightweight live status payloads and bounded chart history so charts can refresh at foreground cadence even while benchmark history or model-resource scans are large. Peak markers are persisted separately from the visible rolling window, and each chart draws a single dashed peak guide for the recorded max.

Metrics also provides:

- detachable popout and reattach behavior, mirroring the Logs popout workflow
- per-GPU utilization, VRAM, core/junction/VRAM temperature, power, and fan charts
- CPU, RAM, storage, network, and system inventory panes
- persisted maxima that survive control-service restarts, with a clear-recorded-metrics action
- a storage browser and chunked file/text/hex editor path, including popup-local state when Metrics is detached

When the admin panel is served from a secure HTTPS `/admin` route, a Service Worker caches the admin shell and last-known status snapshot. A normal open panel labels itself disconnected only after continuous status failures exceed the configured timeout, while a refreshed page falls back to the cached shell if the remote service cannot be contacted quickly. Any successful live status response automatically exits disconnected mode.

## Install

Default install:

```bash
curl -fsSL https://tinyurl.com/club-3090-webserver | bash
```

Custom upstream checkout path and default mode:

```bash
curl -fsSL https://tinyurl.com/club-3090-webserver | \
  CLUB3090_DIR=/opt/ai/club-3090 DEFAULT_MODE=vllm/dual-dflash bash
```

Pass a Hugging Face token inline when gated downloads are needed:

```bash
curl -fsSL https://tinyurl.com/club-3090-webserver | \
  HF_TOKEN=hf_xxx bash
```

Running a local copy:

```bash
bash install-club3090-server.sh
```

Custom admin and proxy ports:

```bash
bash install-club3090-server.sh --ports 18008:18009
```

Enable the local automation API:

```bash
bash install-club3090-server.sh --local-automation
```

Persist a Hugging Face token into the local `club-3090` repo `.env` so setup jobs and later admin-panel model downloads can reuse it automatically:

```bash
bash install-club3090-server.sh --hf-token hf_xxx
```

Public internet exposure:

```bash
bash install-club3090-server.sh --online
```

Public internet exposure with TLS layer:

```bash
bash install-club3090-server.sh --online use-https
```

Skip optional junction/VRAM temperature telemetry setup and keep the old install/update behavior:

```bash
bash install-club3090-server.sh --skip-temps
```

`--skip-temps` bypasses helper unpacking, compiler/libpci dependency installation, bootloader `iomem=relaxed` staging, and the related reboot notice.

## Update

Updates the control layer without intentionally stopping an already-running backend:

```bash
curl -fsSL https://tinyurl.com/club-3090-webserver | bash -s -- --update
```

Or from a local copy:

```bash
bash install-club3090-server.sh --update
```

Public-mode update:

```bash
bash install-club3090-server.sh --update --online
```

Update with custom ports:

```bash
bash install-club3090-server.sh --update --ports 18008:18009
```

## Migrate

Use `--migrate` when the upstream repo checkout itself needs to be replaced with a fresh clone while preserving downloaded model assets and runtime state:

```bash
curl -fsSL https://tinyurl.com/club-3090-webserver | bash -s -- --migrate
```

Or from a local copy:

```bash
bash install-club3090-server.sh --migrate
```

If an interrupted migration needs to be discarded and restarted from scratch instead of resumed:

```bash
bash install-club3090-server.sh --migrate restart
```

`--migrate`:

- compares the local checkout head to the latest upstream head and skips repo replacement entirely if they already match
- renames the old checkout to a timestamped backup
- clones a fresh upstream `club-3090` repo into the original path
- preserves `.env`, `models-cache`, AI Studio assets, generated results, LMCache KV data, safe compose cache directories, and the effective `MODEL_DIR`
- logs the resolved old and new `MODEL_DIR` paths during migration and mirrors preserved weights into the effective post-merge model directory when it differs from the repo-local default
- normalizes older preserved Qwen GGUF assets into the paths expected by the newer upstream compose/profile tree
- moves or merges large asset trees before creating compatibility symlinks, avoiding peak disk duplication on low-free-space hosts
- preserves old Genesis patch trees in the migration backup instead of copying them back into the fresh repo before `setup.sh` reclones them
- imports custom presets and shared-compose selector aliases as separate local rows, preserving `OLD`, `OLD (2)`, and later generations when upstream presets changed again
- prunes runtime-equivalent historical `OLD` presets while preserving genuinely different generations for comparison
- exposes runtime-difference history in the preset UI so kept `OLD` rows can be audited against their current counterpart
- vendors small compose-mounted support files/directories into control-owned custom preset storage so migrated custom presets do not depend on patched or backed-up upstream files
- relinks benchmark scores and selected-stage repair chains to the preserved selector that actually produced them
- rebuilds the dynamic runtime inventory
- replays the required upstream setup commands and re-runs only the model setup commands required by the currently configured presets
- runs the lighter migration-time upstream storage preflight so model/cache preservation does not require destructive Docker image cleanup
- writes resumable migration state to `/opt/club3090-control/migration-state.env`
- emits continuous step-by-step progress and heartbeat messages during long-running phases like clone, setup, and update
- resumes interrupted migrations automatically on the next `--migrate`
- deletes the resume-state file automatically after a successful migration
- accepts Hugging Face credentials either through `HF_TOKEN=...` or `--hf-token ...`, then stores that token in the repo `.env` so later setup and admin-panel download jobs can reuse it

## GPU Detection and Default Behavior

If `DEFAULT_MODE` is not set, the installer counts GPUs with `nvidia-smi` and chooses:

- `vllm/default` when 0 or 1 GPU is detected
- `vllm/dual` when 2 or more GPUs are detected

For testing or overrides, you can force the detected count:

```bash
CLUB3090_GPU_COUNT_OVERRIDE=1 bash install-club3090-server.sh
```

You can still hard-set a default mode:

```bash
DEFAULT_MODE=vllm/long-text bash install-club3090-server.sh
```

## Multi-Instance GPU Model

When the server is using single-card presets, the control service can manage one backend instance per GPU. Each instance has:

- its own GPU binding
- its own docker project/container naming
- its own backend port
- its own admin-panel state
- its own proxy path prefix
- its own boot autostart toggle

The instance catalog is stored in:

```text
/opt/club3090-control/instances.json
```

On multi-GPU systems, this lets you run:

- the same single-card preset on every GPU
- different single-card presets on different GPUs
- only a subset of GPUs

This is intentionally separate from the legacy dual-GPU presets. If no per-GPU single-card instances are enabled, the control service can still fall back to the old upstream dual-mode flow.

In newer releases this model also extends cleanly into the scope-based control plane:

- instance relaunch, boot tracking, and log handoff are scope-aware
- popout log viewers keep the selected runtime target instead of collapsing back to a generic bootstrap snapshot
- runtime readiness for non-vLLM stacks such as llama.cpp and ik-llama is tracked by real local API reachability, not only by vLLM-style log markers
- higher-index GPU scopes and pair scopes are protected by the remapped env/export fixes added during the `v0.8.4x` cycle

## Online Exposure Model

When you install or update with `--online`, the script treats the control service as the only public surface.

That means:

- only the configured admin and proxy ports are opened in the firewall
- only the configured admin and proxy ports are attempted for UPnP forwarding
- raw backend ports such as `8010`-`8020` and per-instance ports like `8200+` are intentionally left private
- all internet-facing inference traffic is expected to go through the proxy

This prevents security bypass around API-key checks, user limits, and per-instance access controls.

If you also pass `use-https`, the installer binds the Python control service to loopback-only internal ports and places Caddy in front of it as the public HTTPS endpoint for both admin and proxy traffic.

When HTTPS mode is enabled, the installer places Caddy in front of the admin UI and proxy on the public admin/proxy ports. Direct IP access uses the self-signed certificate path under `/opt/club3090-control/tls.crt` and `/opt/club3090-control/tls.key` by default. For a browser-trusted certificate, point a DNS or DDNS hostname at the server and set `CLUB3090_HTTPS_HOST` or `CLUB3090_ONLINE_HOST`; Caddy will then request and renew a normal Let's Encrypt certificate for that hostname. Direct IP Let's Encrypt certificates are only attempted with the explicit `--online use-https:cert-ip` mode, or when you explicitly set an IP host and `CLUB3090_ENABLE_IP_LE=true`.

If the server is already on Tailscale, `--online use-https:tailscale` detects the node's MagicDNS name, such as `aardwolf-halfmoon.ts.net`, and writes Caddy routes for that hostname. This avoids router port-forwarding for certificate issuance and is intended for access from devices inside the tailnet. Public internet access still requires Tailscale Funnel or a separately configured public hostname/DDNS path.

`--online use-https:tailscale:enable-funnel` additionally configures Tailscale Funnel. Because Funnel only exposes HTTPS on selected public ports, the installer maps the admin UI to `https://YOUR-NODE.ts.net/admin` on public port `443` and the proxy API to `https://YOUR-NODE.ts.net:8443/v1/chat/completions`. Funnel may require interactive approval in Tailscale or a tailnet policy update the first time it is used.

Tailscale HTTPS modes skip persistent router exposure because tailnet/Funnel routing does not depend on NAT mappings. Caddy binds the `.ts.net` hostname to the Tailscale interface and obtains its certificate directly from the local Tailscale daemon, which keeps that certificate renewed automatically. A separate LAN-bound public-IP route retains the self-signed certificate as a fallback while a managed on-boot, on-update, and daily Certbot job attempts to replace it with a short-lived Let's Encrypt IP certificate. For each attempt, the refresh job requests a temporary 10-minute TCP/80 lease through UPnP or NAT-PMP and lets that lease expire automatically. Issuance failures are logged and leave the working fallback untouched; the router or upstream DMZ must still make public port 80 reach the server for the ACME challenge to succeed. Renewed certificates are activated with a graceful Caddy reload so active admin streams are not interrupted. Private Tailscale IP addresses cannot receive publicly trusted certificates, so use the detected `.ts.net` hostname for tailnet access.

## Configurable Control Ports

The admin and proxy ports are configurable at install/update time with:

```text
--ports ADMIN:PROXY
```

Example:

```bash
bash install-club3090-server.sh --ports 18008:18009
```

Defaults remain:

- admin: `8008`
- proxy: `8009`

The chosen ports are propagated into the generated control service and, when `--online` is used, those same ports are the ones opened in the firewall and requested through UPnP. In `use-https` mode, those public ports are owned by Caddy while the control service moves behind it onto internal loopback-only ports. The installer also opens ports `80` and `443` when needed so Caddy can complete ACME validation for automatic certificates.

## Ports and Routing

- Admin UI: `http://SERVER:8008/admin`
- Default proxy base: `http://SERVER:8009/v1`
- Default chat completions: `http://SERVER:8009/v1/chat/completions`

Per-GPU routes are also supported:

- `http://SERVER:8009/GPU0/v1/chat/completions`
- `http://SERVER:8009/GPU1/v1/chat/completions`
- `http://SERVER:8009/GPU2/v1/chat/completions`

Custom preset routes also work globally and per GPU:

- `http://SERVER:8009/v1/<preset>/chat/completions`
- `http://SERVER:8009/<preset>/v1/chat/completions`
- `http://SERVER:8009/GPU0/v1/<preset>/chat/completions`
- `http://SERVER:8009/GPU1/<preset>/v1/chat/completions`

Length-capped variants remain available with `short-` and `concise-` prefixes.

## Authentication and User Control

The admin web panel uses Linux account credentials through `pamtester` and is served from:

```text
http://SERVER:8008/admin
```

With `--online use-https`, the public entrypoint becomes:

```text
https://SERVER:8008/admin
```

The inference proxy can run in either mode:

- open proxy mode, where requests to `:8009` are allowed without a per-user API key
- authenticated proxy mode, where OpenAI-compatible API keys are required

This is controlled from the Users tab in the admin panel. In `--online` installs, authenticated proxy mode is enabled by default.

Per-user API entries support:

- generated API keys
- optional group/plan membership for shared policies
- enable/disable state
- allowed backend targets such as `legacy`, `GPU0`, `GPU1`, or `*`
- total request limits
- request limits per 5 hours
- request limits per week
- total token limits
- total tool-call limits
- total thinking-time limits

The proxy enforces those controls before forwarding a request to the backend.

User groups/plans can define shared allowed-target rules and quota defaults, so multiple users can inherit the same service tier without repeating the whole policy by hand.

## Local Automation API

If installed or updated with `--local-automation`, the control service also exposes a loopback-only API:

```text
http://127.0.0.1:10881
```

This API is intentionally not part of the online/public surface. It is:

- bound only to loopback
- protected with a local token stored in `/opt/club3090-control/local_api_token`

Typical uses:

- automatic user creation
- automatic user deletion
- user quota updates
- API key rotation

The current implementation exposes local user-management and server-config endpoints for same-machine tools.

`--online`, `use-https`, and `--local-automation` are explicit opt-in flags on each install or update run. If you omit them on a later `--update`, the installer turns those surfaces back off and removes the tracked firewall and UPnP exposure it previously created.

## Admin Panel

The admin UI is designed to control the whole server from one place. It exposes:

- current active backend, service state, and uptime
- request counters and recent latency/token metrics
- GPU, RAM, CPU, storage, and network telemetry
- optional GPU core, junction/hotspot, and VRAM temperature telemetry when the helper is installed and the kernel allows MMIO access
- per-instance GPU subtabs for multi-GPU systems
- dynamic model cards for upstream-discovered single, dual, multi, and experimental presets
- model-summary view that caches up to the latest five active or previously active presets per model as a quick relaunch surface, including temporary boot entries and bulk stop/restart controls
- Setup Assistant / Preset Recommendation Survey for guided preset selection from detected hardware and workload intent
- first-class Custom Model import, registration, and removal flows
- AI Studio setup, lane inventory, downloads, generated-media gallery, and Plan/Interactive routing for multimodal generation
- Model Scores benchmarking with Quick/Full queue planning, live stage logs, grouped queue cards, score badges, and detailed artifact-backed score summaries
- per-instance preset assignment for single-card runtimes
- per-instance start, restart, stop, and boot-autostart toggles with boot-progress log handoff, active/booting/error state badges, and launch-time reporting
- one-click runtime inventory rebuild from the web panel
- preset-aware model downloads that stream installer output into Audit Logs
- direct Hugging Face downloads, setup-script downloads, and missing-size file probes report progress through the same Audit Log job path
- selector-scoped Launch Settings / engine-switch override editing sourced from compose/profile defaults
- per-runtime generation stats cards that aggregate live latency, TTFT, throughput, context fill, KV-cache usage, prefix-cache, speculative/MTP drafted and accepted tokens, acceptance rate, and token counters across all running instances
- a local inference chat interface with realtime streaming, container and API-preset selection, richer markdown rendering, multi-attachment image/text upload support, paste-to-Markdown attachment conversion for long pastes, optional browser voice dictation, shareable Markdown conversation exports, a compact modal chat-settings editor, per-conversation plus per-runtime generation stats, and archived-chat restore flows
- chat conversations are stored server-side in `/opt/club3090-control/conversations/state.json`, with the conversation list loading first and individual transcripts fetched on demand to keep large histories responsive
- chat conversations archive by default from the Chats tab so they can be restored later from Chat Options; hold `Shift` while using the archive button for permanent deletion instead
- assistant transcript bodies now favor a plain-text presentation path for stability, while preserving the expandable reasoning panel, attachments, exports, and per-runtime stats
- live chat recovery across refreshes, including persisted partial assistant output and server-side stream-state tracking
- per-conversation stop/recovery handling so refreshed pages can still abort an active server-side generation
- chat transcript auto-follow, fit-to-content resize helpers, and lighter live streaming paths for long responses
- optional MCP integration for the local chat interface, with UI-managed add/enable/disable flows for both local stdio commands and remote MCP URLs so enabled tools can be exposed to the model during chat
- a Users tab for API-key users, quotas, access rules, and proxy-auth policy
- persistent admin sessions, reducing repeated PAM prompts across control-service restarts and updates
- cached offline admin shell and last-known status snapshot on secure `/admin` routes, with automatic reconnection when live status returns
- global power profile management
- fan control and optimization toggles
- Wake-on-LAN support
- machine restart and shutdown controls
- self-update controls that read shipped release metadata directly from the root `metadata.json`
- update flows lock the panel onto updater logs while the updater is running and resume update monitoring after a page reload
- custom API preset creation, editing, and deletion
- detachable Metrics windows with live chart refresh, persisted peak reset, storage browser, and file/text/hex editor helpers
- live Docker and Audit logs streaming with search tools
- an interactive Debug Logs shell lane with inline ghost completion, command history, file upload/download helpers, and shell-aware zip transfers for files, folders, and glob patterns
- shared searchable audit-log streaming backed by `/opt/club3090-control/audit.log`

Authentication uses Linux usernames and passwords through `pamtester`.
On Ubuntu and Debian-family systems the installer pulls `pamtester` from `apt`. On Arch-family systems it first tries the normal package path and then falls back to `yay` or `paru` if needed, failing safely with a clear manual-install message if it still cannot be installed.

Successful admin logins are also cached in a private control-owned session file, so browser cookies can survive controller restarts and normal `--update` runs without forcing constant PAM reauthentication. Failed PAM checks are coalesced briefly to avoid stale browser credentials hammering the host account lockout policy.

## Log Handling

The console log follower and browser log stream both understand the newer instance-aware docker naming scheme.

That means:

- single backend mode still works
- multiple backend containers can be tailed correctly
- logs remain usable even when container names differ by instance or runtime
- the admin panel can subscribe to the selected instance's log stream

The browser-side logging stack is also much richer now than the early `v0.7.x` path:

- Docker, Audit, Debug, updater, and upstream-service streams can all be switched in-panel
- detached/popped-out viewers stay pinned to the same runtime target
- Audit Logs carry long-running installer and model-download progress instead of stalling on carriage-return updates
- Debug Logs include an interactive bash command box with autocomplete, history, and transfer actions
- the debug-shell transfer helpers can upload files, zip and upload folders, and zip/download explicit files, folders, or glob-expanded results from the current shell working directory
- updater logs remain selected during self-update runs so duplicate updates and accidental log-source switches are avoided

## Chat Experience

The built-in local chat client has grown significantly since early `v0.7.x` and the `v0.9.x` stabilization pass. In addition to basic local chat, it now includes:

- server-persisted conversations with lazy transcript loading
- per-conversation state recovery after refreshes or network interruptions
- per-conversation and per-runtime generation statistics
- support for reasoning/thinking traces with collapsible display
- image and text attachments, including paste-to-Markdown conversion for long pasted text
- optional browser voice dictation
- share/export flows for conversation Markdown
- optional local and remote MCP tool integration
- streaming paths that prioritize transcript stability and progressively lighter render/update behavior during long generations
- incremental stream-metrics handling so per-message and conversation Generation Statistics update before the final response completes

The chat renderer and syntax pipeline also received a long series of fixes across the `v0.7.x`, `v0.8.x`, and `v0.9.x` lines:

- streamed fenced code and inline code render more reliably while text is still arriving
- syntax colors now come from the normalized `code_syntax.json` theme/config instead of brittle embedded fallbacks
- Markdown list/inline-span split bugs were fixed for live streaming
- HTML/XML fenced blocks, footnotes, Mermaid export helpers, and admonition rendering were all improved

## Runtime Behavior

- The control service stores the active default mode in `/opt/club3090-control/active_mode`
- It stores the last known-good legacy mode in `/opt/club3090-control/last_good_mode`
- It stores per-instance configuration in `/opt/club3090-control/instances.json`
- It stores the scanned upstream runtime registry in `/opt/club3090-control/runtime_inventory.json`
- It stores public/auth policy in `/opt/club3090-control/server_config.json`
- It stores persistent admin web sessions in `/opt/club3090-control/admin_sessions.json`
- It stores group/plan definitions in `/opt/club3090-control/groups.json`
- It stores tracked online firewall and UPnP state in `/opt/club3090-control/network_state.json`
- It stores chat conversations and chat prompt-template state in `/opt/club3090-control/conversations/state.json`
- It stores API users, quotas, and usage accounting in `/opt/club3090-control/users.json`
- It stores custom runtime registrations and vendored custom-compose support files under `/opt/club3090-control/custom_models.json` and `/opt/club3090-control/custom-models/`
- It stores validated Model Scores artifacts under `/opt/club3090-control/benchmarks/`
- It stores shipped code-syntax configuration under `/opt/club3090-control/code_syntax.json`
- It stores the loopback automation token in `/opt/club3090-control/local_api_token`
- It applies the selected power profile before backend startup
- It can auto-start a backend when a proxied inference request arrives
- It can stop idle containers after a configurable quiet period
- It can downclock hardware during idle windows
- It can restore enabled per-GPU instances on boot
- It can fall back to the last known-good legacy mode if a startup attempt fails
- It can persist and resume migration/update state with metadata-aware self-update handling
- It can rebuild the upstream-derived runtime inventory after repo/profile changes
- It can keep shipped metadata, changelog text, and code-syntax config synchronized with the browser/admin payloads
- It can preserve model caches, AI Studio assets, result evidence, custom preset support files, and benchmark score lineage across upstream migrations
- It can compile and install the optional vendored `gputemps` helper under `/opt/club3090-control/bin/gputemps` for junction/hotspot and VRAM temperature telemetry

## Installed Services

The script writes these systemd units:

- `club3090-vllm.service`
  - restores enabled per-GPU instances on boot, or falls back to legacy mode startup
- `club3090-control.service`
  - hosts the admin UI and proxy
- `club3090-benchmarks.service`
  - owns long-running Model Scores workers so benchmark queues can survive control-plane updates
- `club3090-caddy.service`
  - provides the HTTPS frontend when `--online use-https` is enabled
- `club3090-console-log.service`
  - streams matching backend Docker logs to `tty1`
- `club3090-headless-x.service`
  - provides a private on-demand Xorg session for NVIDIA fan control

These services are gated by the kernel command-line flag `club3090.server=1`, so they can be installed without forcing server mode on every boot.

## Files Written

- `/opt/club3090-control/control.py`
- `/opt/club3090-control/start-vllm-last-mode.sh`
- `/opt/club3090-control/follow-vllm-log.sh`
- `/opt/club3090-control/prepare-headless-x.sh`
- `/opt/club3090-control/active_mode`
- `/opt/club3090-control/last_good_mode`
- `/opt/club3090-control/instances.json`
- `/opt/club3090-control/server_config.json`
- `/opt/club3090-control/admin_sessions.json`
- `/opt/club3090-control/groups.json`
- `/opt/club3090-control/users.json`
- `/opt/club3090-control/custom_models.json`
- `/opt/club3090-control/custom-models/`
- `/opt/club3090-control/benchmarks/`
- `/opt/club3090-control/code_syntax.json`
- `/opt/club3090-control/network_state.json`
- `/opt/club3090-control/Caddyfile`
- `/opt/club3090-control/local_api_token`
- `/opt/club3090-control/bin/gputemps`
- `/opt/club3090-control/include/nvml.h`
- `/opt/club3090-control/src/gputemps/gputemps.c`
- `/opt/club3090-control/src/gputemps/nvml.h`
- `/opt/club3090-control/control.log`
- `/opt/club3090-control/audit.log`
- `/etc/systemd/system/club3090-vllm.service`
- `/etc/systemd/system/club3090-control.service`
- `/etc/systemd/system/club3090-benchmarks.service`
- `/etc/systemd/system/club3090-caddy.service`
- `/etc/systemd/system/club3090-console-log.service`
- `/etc/systemd/system/club3090-headless-x.service`

## Notes

- This script manages upstream `club-3090`; it does not replace it
- The design goal is to avoid forking upstream runtime files wherever possible
- Docker and NVIDIA drivers should be installed before first use
- Headless fan control depends on `nvidia-settings` and a private Xorg display
- Extra junction/VRAM telemetry depends on a locally compiled helper that links against the host NVIDIA Management Library and libpci; the installer vendors the helper source/header, installs only the compile/link packages when the helper is missing, and can be bypassed with `--skip-temps`
- The `iomem=relaxed` kernel switch is required for that extra telemetry on systems that otherwise block GPU MMIO mapping. It is useful on trusted single-user inference hosts, but it does relax a kernel I/O-memory safety boundary, so security-sensitive or shared systems may prefer `--skip-temps`
- The installer attempts to install `nvidia-settings`, Xorg, `pamtester`, OpenSSL, Caddy, `miniupnpc`, and firewall tooling as needed, and exits safely with a clear error if a required dependency still cannot be installed
- The control layer is intended for unattended inference hosts and physical server consoles

## Repository Layout

- [`install-club3090-server.sh`](./install-club3090-server.sh): full installer/updater
- [`README.md`](./README.md): feature and usage reference
- [`src/control/`](./src/control): split-source Python backend modules used to build the shipped control plane
- [`src/web/`](./src/web): split-source HTML/CSS/JS for the admin panel
- [`src/build/`](./src/build): build pipeline, smoke tests, and vendored payload inputs used to compose the shipped single-file installer
- [`src/build/vendor/`](./src/build/vendor): vendored helper source/header payloads embedded into the installer for optional junction/VRAM temperature telemetry
- [`metadata.json`](./metadata.json): root release metadata consumed by the build and updater flows

The project has used a split-source build pipeline since the `v0.7.0` refactor, but still ships a single integrated installer artifact. Day-to-day development happens in `src/control/`, `src/web/`, and `src/build/`, then the root [`build.py`](./build.py) wrapper regenerates the monolithic script and bundled assets from those sources. Shipped control, updater, admin UI, code-syntax, and optional temperature-helper payloads are compressed into the installer so release artifacts stay deterministic and do not depend on helper repositories being reachable during install.

Build usage:

- `python build.py --changes "..."`: normal release build; advances the numeric patch version such as `v0.9.32 -> v0.9.33`
- `python build.py --iterative --changes "..."`: iterative rebuild on the same numeric release; advances only the letter suffix such as `v0.9.32 -> v0.9.32a -> v0.9.32b`
- both modes append the supplied bullets to `change_log_latest`; only the non-iterative mode rolls the previous numeric release notes down into `change_log_release`
- `python build.py --list-smoke-tests` prints numbered smoke checks, and `--smoke-tests=ID,ID` can run only the relevant targeted checks during narrow fix iterations
- `--change` remains accepted as a compatibility alias, but new build notes should use `--changes`
