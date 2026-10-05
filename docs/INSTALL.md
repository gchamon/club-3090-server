# Installation

## Components and prerequisites

Club-3090 Server is the management/control layer; [club-3090](https://github.com/noonghunna/club-3090) is the separate upstream inference runtime. The upstream checkout is operator-owned. Place it at `club-3090` inside this repository, or provide its absolute path in `CLUB3090_DIR`.

Install prerequisites manually before installing this service. Base requirements include `git`, Python 3 with PyYAML, Docker with Compose, systemd, `sudo`, `curl`, `openssl`, and `pamtester`. Example base-package commands are:

```bash
# Arch Linux
sudo pacman -S --needed git python python-yaml docker docker-compose sudo curl openssl pamtester

# Debian/Ubuntu
sudo apt-get update
sudo apt-get install git python3 python3-yaml docker.io docker-compose-plugin sudo curl openssl pamtester
```

Enable and configure Docker as required by your distribution; installation does not configure the host's package manager or Docker daemon. Optional features may require Caddy and Tailscale, Xorg and `nvidia-settings` for fan control, `cpupower`, `ntfs-3g`, and compiler/libpci dependencies for the temperature helper. Install only the dependencies for features you intend to use.
To opt in to junction/VRAM temperature telemetry, install `gcc`, the libpci development package, and the NVIDIA Management Library linker package using your distribution package manager, then run `sudo env CLUB3090_ENABLE_EXTRA_TEMPS=1 ./install.sh`. The helper is compiled from `src/build/vendor/gputemps.c` and `src/build/vendor/nvml.h` into the runtime data directory; no source is copied out of this checkout. The installer does not edit bootloader configuration. If the helper reports that its readings require `iomem=relaxed`, configure that kernel option manually and reboot.

## Install

Clone this repository and upstream runtime, then install:

```bash
git clone https://github.com/noonghunna/club-3090-server.git
cd club-3090-server
git clone https://github.com/noonghunna/club-3090.git
sudo ./install.sh
```

For an upstream checkout at another path:

```bash
sudo env CLUB3090_DIR=/absolute/path/to/club-3090 ./install.sh
```

The checkout must remain at the installed path: systemd services execute the Python modules, scripts, and web assets directly from it. The installer registers systemd units and stores the service environment in `/etc/club3090-server.env`; mutable runtime data defaults to `/var/lib/club3090-control` and can be redirected with `CLUB3090_CONTROL_DIR`.

Start the management service explicitly and inspect its installed unit:

```bash
sudo systemctl start club3090-control.service
systemctl cat club3090-control.service
```

The installer does not automatically start an inference runtime. For service operations see [Operations](OPERATIONS.md).

## Uninstall

From the repository checkout, run:

```bash
sudo ./uninstall.sh
```

This removes the registered units and `/etc/club3090-server.env`. It deliberately leaves the source checkout and mutable runtime data intact. It never removes dependency packages.
