# Configuration

The services read `/etc/club3090-server.env` for runtime settings; a new file contains the selected admin and proxy ports. The systemd units record the resolved source checkout, upstream checkout, and runtime-data paths. Set installer environment overrides before running `sudo ./install.sh`; the installer does not install packages or modify shell profiles.

## Checkout and state boundaries

- `CLUB3090_DIR` identifies the pre-existing upstream `club-3090` checkout. The installer does not clone, update, or configure that repository.
- `CLUB3090_CONTROL_DIR` selects mutable server runtime data; its default is `/var/lib/club3090-control`.
- The server application and web assets remain in this repository checkout and are executed/read there, not copied into the runtime-data directory.
- `/etc/club3090-server.env` is the operator-visible service configuration file.

Runtime state includes server-managed settings, sessions, logs, and generated operational data. Preserve the configured data directory if you want to retain that state when removing the service registration.

## Ports and installer overrides

The default admin interface is `http://HOST:8008/admin`; the OpenAI-compatible proxy is `http://HOST:8009/v1`. `CLUB3090_ADMIN_PORT` and `CLUB3090_PROXY_PORT` set initial port values when the environment file is first created. Existing environment-file values are preserved on reinstall.

| Variable | Effect |
| --- | --- |
| `CLUB3090_DIR` | Select the existing upstream `club-3090` checkout. |
| `CLUB3090_CONTROL_DIR` | Select mutable server runtime data; default `/var/lib/club3090-control`. |
| `CLUB3090_ADMIN_PORT` / `CLUB3090_PROXY_PORT` | Set initial ports in a newly created environment file. |
| `CLUB3090_SERVER_ENV_FILE` | Select an alternate service environment-file path. |
| `CLUB3090_ENABLE_EXTRA_TEMPS=1` | Opt in to compiling the optional GPU temperature helper; see [Installation](INSTALL.md). |

## Feature configuration

Set `DEFAULT_MODE` and supported runtime feature variables in `/etc/club3090-server.env`. `CLUB3090_ENABLE_EXTRA_TEMPS=1` is an installer-only opt-in; it is not stored in the service environment file. Optional features also require their host dependencies to be installed and configured.
