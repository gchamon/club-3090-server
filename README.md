# Club-3090 Server

Single-file installer for a [club-3090](https://github.com/noonghunna/club-3090) inference host, providing a full-featured browser admin control panel, distro-aware install/update logic, systemd service setup, a reverse proxy that automatically routes requests to the correct containers via a single endpoint with optional configurable vLLM setting presets, live log management, GPU power and fan speed controls, multi-instance GPU orchestration, and API access control for multiple users.

This repository is the server-management layer. It is designed to integrate with an existing [club-3090](https://github.com/noonghunna/club-3090) installation and allow for easy remote management of the server.

## What This Script Provides

- Linux distribution detection for Arch-family and Ubuntu/Debian-family systems
- Installer and updater logic in one self-contained script
- A control stack installed under `/opt/club3090-control`
- An admin UI on `:8008/admin`
- An OpenAI-compatible proxy on `:8009` so you can chat with the LLM on a unified port regardless of what docker container is in use.
- GPU-aware backend selection
- Per-GPU multi-instance runtime management for single-card presets
- Native support for dual-GPU presets
- Live Docker log streaming that stays aware of multiple backend containers
- A dedicated Audit tab that reuses the shared searchable live-log viewer for audit events
- Request metrics, uptime, health reporting, and backend auto-start behavior
- Per-user API key authentication, access control, and quota enforcement
- An optional loopback-only automation API for local tools on the same machine
- Optional `--online` mode that opens and forwards only the admin/proxy ports to the internet
- Optional `--online use-https` mode that enables a Caddy-backed self-signed HTTPS frontend for the admin panel and proxy
- Power presets, fan speed control, idle downclocking, and system information for remote server management

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
- An existing `club-3090` checkout that contains the upstream runtime assets and `scripts/switch.sh` resident in `/opt/ai/club-3090`

Typical upstream checkout:

```bash
git clone https://github.com/noonghunna/club-3090.git /opt/ai/club-3090
```

## Supported Runtime Presets

Single-card presets that can be assigned per GPU:

- `vllm/default`
- `vllm/long-vision`
- `vllm/long-text`
- `vllm/bounded-thinking`
- `vllm/tools-text`
- `vllm/minimal`
- `llamacpp/default`
- `llamacpp/concurrent`

Legacy upstream dual-GPU presets that remain available as fallback/default modes:

- `vllm/dual`
- `vllm/dual-turbo`
- `vllm/dual-dflash`
- `vllm/dual-dflash-noviz`

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

## Online Exposure Model

When you install or update with `--online`, the script treats the control service as the only public surface.

That means:

- only the configured admin and proxy ports are opened in the firewall
- only the configured admin and proxy ports are attempted for UPnP forwarding
- raw backend ports such as `8010`-`8020` and per-instance ports like `8200+` are intentionally left private
- all internet-facing inference traffic is expected to go through the proxy

This prevents security bypass around API-key checks, user limits, and per-instance access controls.

If you also pass `use-https`, the installer generates a self-signed certificate under `/opt/club3090-control/tls.crt` and `/opt/club3090-control/tls.key`, binds the Python control service to loopback-only internal ports, and places Caddy in front of it as the public HTTPS endpoint for both admin and proxy traffic.

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

The chosen ports are propagated into the generated control service and, when `--online` is used, those same ports are the ones opened in the firewall and requested through UPnP. In `use-https` mode, those public ports are owned by Caddy while the control service moves behind it onto internal loopback-only ports.

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
- per-instance preset assignment for single-card runtimes
- per-instance start, restart, stop, and boot-autostart toggles
- a Users tab for API-key users, quotas, access rules, and proxy-auth policy
- a dedicated Audit tab for global admin controls and live audit-event review
- global power profile management
- fan control and optimization toggles
- Wake-on-LAN support
- machine restart and shutdown controls
- custom API preset creation, editing, and deletion
- live Docker log streaming with search tools
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
- the Audit tab reuses the same searchable viewer against the audit log instead of Docker output

## Runtime Behavior

- The control service stores the active default mode in `/opt/club3090-control/active_mode`
- It stores the last known-good legacy mode in `/opt/club3090-control/last_good_mode`
- It stores per-instance configuration in `/opt/club3090-control/instances.json`
- It stores public/auth policy in `/opt/club3090-control/server_config.json`
- It stores group/plan definitions in `/opt/club3090-control/groups.json`
- It stores tracked online firewall and UPnP state in `/opt/club3090-control/network_state.json`
- It stores API users, quotas, and usage accounting in `/opt/club3090-control/users.json`
- It stores the loopback automation token in `/opt/club3090-control/local_api_token`
- It applies the selected power profile before backend startup
- It can auto-start a backend when a proxied inference request arrives
- It can stop idle containers after a configurable quiet period
- It can downclock hardware during idle windows
- It can restore enabled per-GPU instances on boot
- It can fall back to the last known-good legacy mode if a startup attempt fails

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
