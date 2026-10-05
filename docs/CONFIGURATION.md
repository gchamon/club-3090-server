# Configuration

The services read `/etc/club3090-server.env` for runtime settings. It records the resolved server, upstream, and runtime-data paths, admin/proxy ports and bind hosts, `DEFAULT_MODE`, and the optional temperature-helper flag. Existing values are preserved on reinstall unless the matching environment override is supplied. The checkout itself is used directly; the installer does not install packages or modify shell profiles.

## Checkout and state boundaries

- `CLUB3090_DIR` identifies the pre-existing upstream `club-3090` checkout. The installer does not clone, update, or configure that repository.
- `CLUB3090_CONTROL_DIR` selects mutable server runtime data; its default is `/var/lib/club3090-control`.
- The server application and web assets remain in this repository checkout and are executed/read there, not copied into the runtime-data directory.
- `/etc/club3090-server.env` is the operator-visible service configuration file.

Runtime state includes server-managed settings, sessions, logs, and generated operational data. Preserve the configured data directory if you want to retain that state when removing the service registration.

## Ports and installer overrides

The default admin interface is `http://HOST:8008/admin`; the OpenAI-compatible proxy is `http://HOST:8009/v1`. `CLUB3090_ADMIN_PORT` and `CLUB3090_PROXY_PORT` set ports in the service environment file. Existing values remain unchanged on reinstall unless the corresponding override is supplied.

| Variable | Effect |
| --- | --- |
| `CLUB3090_DIR` | Select the existing upstream `club-3090` checkout. |
| `CLUB3090_CONTROL_DIR` | Select mutable server runtime data; default `/var/lib/club3090-control`. |
| `CLUB3090_ADMIN_BIND_HOST` / `CLUB3090_PROXY_BIND_HOST` | Set service bind hosts; defaults to `0.0.0.0`. |
| `DEFAULT_MODE` | Set the preferred runtime mode for startup helpers. |
| `CLUB3090_ADMIN_PORT` / `CLUB3090_PROXY_PORT` | Set the ports; values are preserved on reinstall unless overridden. |
| `CLUB3090_SERVER_ENV_FILE` | Select an alternate service environment-file path. |
| `CLUB3090_ENABLE_EXTRA_TEMPS=1` | Opt in to compiling the optional GPU temperature helper; see [Installation](INSTALL.md). |

## Feature configuration

`CLUB3090_ENABLE_EXTRA_TEMPS=1` is an installer opt-in and is recorded in the service environment file. Optional features also require their host dependencies to be installed and configured.
