# Club-3090 Server

Club-3090 Server is the management layer for the upstream [club-3090](https://github.com/noonghunna/club-3090) inference runtime. It provides a browser admin panel at `:8008/admin` and an OpenAI-compatible proxy at `:8009/v1`; the upstream project supplies the model runtime.

## Quickstart

See [Installation](docs/INSTALL.md) for prerequisite packages and [the documentation index](docs/README.md) for configuration, networking, and operations details. Install prerequisites manually; the installer does not install packages.

Clone both repositories, placing the upstream checkout at `club-3090` beside this repository, or set `CLUB3090_DIR` to its location:

```bash
git clone https://github.com/noonghunna/club-3090-server.git
cd club-3090-server
git clone https://github.com/noonghunna/club-3090.git
# If upstream is elsewhere, export CLUB3090_DIR=/absolute/path/to/club-3090
sudo ./install.sh
sudo systemctl start club3090-control.service
systemctl cat club3090-control.service
curl http://HOST:8009/v1/models
```

Open `http://HOST:8008/admin` in a browser, substituting the server host for `HOST`. The services execute code and assets directly from this checkout; keep it in place while installed. `/etc/club3090-server.env` contains service configuration and `${CLUB3090_CONTROL_DIR:-/var/lib/club3090-control}` is the mutable runtime-data location.

To remove service registration, run `sudo ./uninstall.sh`. It removes the registered units and `/etc/club3090-server.env`; it leaves this source checkout and runtime data intact and does not uninstall dependency packages. See [Uninstallation](docs/OPERATIONS.md#uninstallation).
