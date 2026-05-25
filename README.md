# Club-3090 Server

Single-file installer for a [club-3090](https://github.com/noonghunna/club-3090) inference host, providing a full-featured browser admin control panel, distro-aware install/update logic, systemd service setup, a reverse proxy that automatically routes requests to the correct containers via a single endpoint with optional configurable vLLM setting presets, live log management, GPU power and fan speed controls, multi-instance GPU orchestration, and API access control for multiple users.

This repository is the server-management layer. It integrates with the upstream [club-3090](https://github.com/noonghunna/club-3090) runtime and, on a fresh install clones that upstream repo automatically into `/opt/ai/club-3090` before wiring up the control plane.

## Important Notes

- Users are encouraged to first deploy [club-3090](https://github.com/noonghunna/club-3090) to /opt/ai/, follow the Quick Start Guide in the original project and ensure that everything works correctly before attempting to deploy Club-3090-Server. If /opt/ai/club-3090 is not found, the script will automatically clone the latest repo for you and deploy it in that location and attempt to run setup.sh and set everything up for you anyway, but it's best to first familiarize yourself with the original project's strengths and ensure it meets your needs and works correctly before attempting to host a server.
- The latest release of this script may or may not be up to date with the original repo's fast evolving architecture. To avoid unforeseen issues, make sure the commit of [club-3090](https://github.com/noonghunna/club-3090) you're using with club-3090-server matches the expected version from the latest release. You may also simply trust the installer and let it pull the latest commit but your YMMV depending on whether the original project has introduced breaking changes since this script was last updated.

## What This Script Provides

- Fully self contained script that handles everything you need to self-host a club-3090 based inference server, optimized for headless Arch and Debian/Ubuntu based distros
- A control stack installed under `/opt/club3090-control` and an admin web panel running on `localhost:8008/admin`
- An OpenAI-compatible proxy on `:8009` so you can chat with the LLM on a unified port regardless of what docker containers are in use.
- GPU-aware backend selection with per-GPU and multi-instance runtime management for single-card, dual-card or multi-card presets with dynamic runtime inventory discovery from the local `club-3090` checkout
- A modern scope model built around `GLOBAL`, `GPU<n>`, and `PAIRx_y` targets, including built-in sequential auto-pairs and custom user-defined pairs
- A Presets experience that includes model-summary relaunch surfaces, Setup Assistant recommendations, selector-scoped launch overrides, and a first-class Custom Model import path backed by upstream `pull.sh`
- Built-in local inference chat with server-persisted conversations across browsers/devices, per-conversation saved settings, folders, automatic conversation naming, system-prompt templates, rich markdown/media rendering, collapsible thinking trace rendering, local attachments, and automatic context compaction/rollover
- Live Docker, Audit, and Debug log streaming that stays aware of multiple backend containers, including an interactive debug-shell lane with autocomplete, history, upload/download helpers, and zip-based folder transfers
- Preset launch state that only flips to `Active` after the backend fully finishes booting, with boot/error browser notifications and fast failure reporting when a compose never actually starts a container
- UI-driven model download/setup jobs with stdout/stderr streamed into Audit Logs
- Hardware metrics, uptime, health reporting, and backend auto-start and manual control, as well as full server remote management controls
- Power presets, fan speed control, idle downclocking, and system information for remote server management
- Create dynamic instances and run multiple docker containers per GPU or GPU Pairs and be able to run inference on a single unified endpoint with different configurable vLLM setting presets 
- Optional per-user API key authentication, access control, and optional quota enforcement
- An optional loopback-only automation API for local tools on the same machine
- Optional `--online` mode that opens and forwards only the admin/proxy ports to the internet
- Optional `--online use-https` mode that enables a Caddy-backed self-signed HTTPS frontend for the admin panel and proxy
- Docker logs automatically printed to tty1 and last instance autostart if the kernel condition club3090.server=1 is active

## Screenshots
Video coming soon.
<img width="1080" height="2408" alt="image" src="https://github.com/user-attachments/assets/3ee63ab8-7fc9-4db9-8bce-b2d2308a71fa" />
<img width="1080" height="2408" alt="image" src="https://github.com/user-attachments/assets/85fdb73f-5e1f-4041-b30d-f787b9ec979c" />
<img width="1080" height="2408" alt="Screenshot_20260508-074059" src="https://github.com/user-attachments/assets/bdb2e054-3da8-43fd-9667-b1101693c90e" />
<img width="1080" height="2408" alt="Screenshot_20260509-052022" src="https://github.com/user-attachments/assets/7d46da12-21a9-40d1-a7cc-135ea9573bfb" />
<img width="1080" height="2408" alt="Screenshot_20260509-052048" src="https://github.com/user-attachments/assets/02683f61-144e-48cb-9c22-83765fa87e20" />
<img width="1080" height="2408" alt="Screenshot_20260509-052058" src="https://github.com/user-attachments/assets/a6837107-e0a1-43de-afaa-04751dd47ab8" />
<img width="1080" height="2408" alt="Screenshot_20260509-052110" src="https://github.com/user-attachments/assets/69cbde3a-731f-451d-9a2f-d5ede08a4ec5" />
<img width="1080" height="2408" alt="Screenshot_20260509-052121" src="https://github.com/user-attachments/assets/1e5bb5a1-177d-4fb7-92b1-be87a3884f74" />
<img width="1080" height="2408" alt="Screenshot_20260509-052131" src="https://github.com/user-attachments/assets/86ce63e2-b5fc-41d7-86aa-2b39c935316e" />
<img width="1080" height="2408" alt="Screenshot_20260508-072044" src="https://github.com/user-attachments/assets/6e04fbdf-7fc4-4ab9-a4d6-4f46d8dde932" />

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

- Use a single-GPU preset if you only want one model running on one GPU, or the global scope to automatically distribute presets to alll available GPUs.
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
- `Users`: create API users and keys if you want to share the server safely
- `Metrics`: request counts, usage history, and runtime performance data
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

Since the broader `v0.8.x` migration, the inventory path is also registry/profile-aware, so the admin panel can surface richer upstream metadata such as:

- preview, production, experimental, and caveat-marked variants
- structured launch defaults pulled from compose/profile metadata instead of a local hardcoded table
- family summaries and model-summary relaunch cards
- built-in and custom API-preset aware routes
- Custom Model imports that register as persistent local runtime cards once upstream import succeeds

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

Public internet exposure with TLS layewr:

```bash
bash install-club3090-server.sh --online use-https
```
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
- preserves `models-cache`, safe compose cache directories, and `.env`
- logs the resolved old and new `MODEL_DIR` paths during migration and mirrors preserved weights into the effective post-merge model directory when it differs from the repo-local default
- preserves old Genesis patch trees in the migration backup instead of copying them back into the fresh repo before `setup.sh` reclones them
- rebuilds the dynamic runtime inventory
- re-runs only the model setup commands required by the currently configured presets
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

Tailscale HTTPS modes skip UPnP installation, router port-forwarding, and UPnP cleanup because tailnet/Funnel routing does not depend on router NAT mappings. The installer materializes the Tailscale certificate with `tailscale cert` into `/opt/club3090-control/tailscale.crt` and `/opt/club3090-control/tailscale.key`, then points the hostname-specific Caddy route at those files.

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
- per-instance GPU subtabs for multi-GPU systems
- dynamic model cards for upstream-discovered single, dual, multi, and experimental presets
- model-summary view that caches up to the latest five active or previously active presets per model as a quick relaunch surface, including temporary boot entries and bulk stop/restart controls
- Setup Assistant / Preset Recommendation Survey for guided preset selection from detected hardware and workload intent
- first-class Custom Model import, registration, and removal flows
- per-instance preset assignment for single-card runtimes
- per-instance start, restart, stop, and boot-autostart toggles with boot-progress log handoff, active/booting/error state badges, and launch-time reporting
- one-click runtime inventory rebuild from the web panel
- preset-aware model downloads that stream installer output into Audit Logs
- selector-scoped Launch Settings / engine-switch override editing sourced from compose/profile defaults
- per-runtime generation stats cards that aggregate the latest latency, throughput, KV-cache, and token counters across all running instances
- a local inference chat interface with realtime streaming, container and API-preset selection, richer markdown rendering, multi-attachment image/text upload support, paste-to-Markdown attachment conversion for long pastes, optional browser voice dictation, shareable Markdown conversation exports, a compact modal chat-settings editor, per-conversation plus per-runtime generation stats, and archived-chat restore flows
- chat conversations are stored server-side in `/opt/club3090-control/conversations/state.json`, with the conversation list loading first and individual transcripts fetched on demand to keep large histories responsive
- chat conversations archive by default from the Chats tab so they can be restored later from Chat Options; hold `Shift` while using the archive button for permanent deletion instead
- assistant transcript bodies now favor a plain-text presentation path for stability, while preserving the expandable reasoning panel, attachments, exports, and per-runtime stats
- live chat recovery across refreshes, including persisted partial assistant output and server-side stream-state tracking
- per-conversation stop/recovery handling so refreshed pages can still abort an active server-side generation
- chat transcript auto-follow, fit-to-content resize helpers, and lighter live streaming paths for long responses
- optional MCP integration for the local chat interface, with UI-managed add/enable/disable flows for both local stdio commands and remote MCP URLs so enabled tools can be exposed to the model during chat
- a Users tab for API-key users, quotas, access rules, and proxy-auth policy
- global power profile management
- fan control and optimization toggles
- Wake-on-LAN support
- machine restart and shutdown controls
- self-update controls that read shipped release metadata directly from `build/metadata.json`
- custom API preset creation, editing, and deletion
- live Docker and Audit logs streaming with search tools
- an interactive Debug Logs shell lane with inline ghost completion, command history, file upload/download helpers, and shell-aware zip transfers for files, folders, and glob patterns
- shared searchable audit-log streaming backed by `/opt/club3090-control/audit.log`

Authentication uses Linux usernames and passwords through `pamtester`.
On Ubuntu and Debian-family systems the installer pulls `pamtester` from `apt`. On Arch-family systems it first tries the normal package path and then falls back to `yay` or `paru` if needed, failing safely with a clear manual-install message if it still cannot be installed.

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

## Chat Experience

The built-in local chat client has grown significantly since early `v0.7.x`. In addition to basic local chat, it now includes:

- server-persisted conversations with lazy transcript loading
- per-conversation state recovery after refreshes or network interruptions
- per-conversation and per-runtime generation statistics
- support for reasoning/thinking traces with collapsible display
- image and text attachments, including paste-to-Markdown conversion for long pasted text
- optional browser voice dictation
- share/export flows for conversation Markdown
- optional local and remote MCP tool integration
- streaming paths that prioritize transcript stability and progressively lighter render/update behavior during long generations

The chat renderer and syntax pipeline also received a long series of fixes across the `v0.7.x` and `v0.8.x` line:

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
- It stores group/plan definitions in `/opt/club3090-control/groups.json`
- It stores tracked online firewall and UPnP state in `/opt/club3090-control/network_state.json`
- It stores chat conversations and chat prompt-template state in `/opt/club3090-control/conversations/state.json`
- It stores API users, quotas, and usage accounting in `/opt/club3090-control/users.json`
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

## Installed Services

The script writes these systemd units:

- `club3090-vllm.service`
  - restores enabled per-GPU instances on boot, or falls back to legacy mode startup
- `club3090-control.service`
  - hosts the admin UI and proxy
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
- `/opt/club3090-control/groups.json`
- `/opt/club3090-control/users.json`
- `/opt/club3090-control/network_state.json`
- `/opt/club3090-control/Caddyfile`
- `/opt/club3090-control/local_api_token`
- `/opt/club3090-control/control.log`
- `/opt/club3090-control/audit.log`
- `/etc/systemd/system/club3090-vllm.service`
- `/etc/systemd/system/club3090-control.service`
- `/etc/systemd/system/club3090-caddy.service`
- `/etc/systemd/system/club3090-console-log.service`
- `/etc/systemd/system/club3090-headless-x.service`

## Notes

- This script manages upstream `club-3090`; it does not replace it
- The design goal is to avoid forking upstream runtime files wherever possible
- Docker and NVIDIA drivers should be installed before first use
- Headless fan control depends on `nvidia-settings` and a private Xorg display
- The installer attempts to install `nvidia-settings`, Xorg, `pamtester`, OpenSSL, Caddy, `miniupnpc`, and firewall tooling as needed, and exits safely with a clear error if a required dependency still cannot be installed
- The control layer is intended for unattended inference hosts and physical server consoles

## Repository Layout

- [`install-club3090-server.sh`](./install-club3090-server.sh): full installer/updater
- [`README.md`](./README.md): feature and usage reference
- [`control/`](./control): split-source Python backend modules used to build the shipped control plane
- [`web/`](./web): split-source HTML/CSS/JS for the admin panel
- [`build/`](./build): build pipeline, metadata, and smoke tests used to compose the shipped single-file installer

The project has used a split-source build pipeline since the `v0.7.0` refactor, but still ships a single integrated installer artifact. Day-to-day development happens in `control/`, `web/`, and `build/`, then `build/build.py` regenerates the monolithic script and bundled assets.
