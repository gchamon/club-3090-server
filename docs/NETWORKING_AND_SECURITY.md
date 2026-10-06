# Networking and security

## Service endpoints

- Admin panel: `http://HOST:8008/admin`
- OpenAI-compatible API base: `http://HOST:8009/v1`
- Model-list smoke check: `curl http://HOST:8009/v1/models`

Ports can be changed with `CLUB3090_ADMIN_PORT` and `CLUB3090_PROXY_PORT`; consult `/etc/club3090-server.env` for the installed values. Do not expose backend/container ports as substitutes for the proxy endpoint.

The admin panel authenticates with Linux account credentials through `pamtester`. The inference proxy supports open or API-key-authenticated operation; its access policy and user keys are managed in the admin interface. Review the active policy before making the proxy reachable by untrusted clients.

## Network exposure

Installation does not configure firewalls, router forwarding, UPnP, TLS, or public DNS. Operators are responsible for network controls and any reverse proxy/TLS deployment. Keep the admin interface and proxy on trusted networks unless they have been deliberately secured for the intended audience.

Optional integrations such as Caddy or Tailscale require operator-installed dependencies and operator-managed network configuration; the installer does not install or configure those systems.

## Optional GPU telemetry

The optional junction/VRAM temperature helper requires compiler and NVIDIA/libpci development dependencies. On some systems, access to GPU MMIO may require the kernel option `iomem=relaxed`; enabling it is a manual operator decision and may require a reboot. Consider the security implications before enabling this kernel option, especially on shared or security-sensitive hosts.
