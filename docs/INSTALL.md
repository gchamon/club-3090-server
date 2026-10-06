# Installation

## Components and prerequisites

Club-3090 Server is the management/control layer; [club-3090](https://github.com/noonghunna/club-3090) is the separate upstream inference runtime. The upstream checkout is operator-owned. Place it at `club-3090` inside this repository, or provide its absolute path in `CLUB3090_DIR`.

Install prerequisites manually before installing. Base requirements include `git`, Python 3 with PyYAML, Docker with Compose, systemd, `sudo`, `curl`, `openssl`, and `pamtester`. The installer verifies these requirements but never installs packages. Docker must be enabled/configured for your distribution.
Use Docker's official [Ubuntu](https://docs.docker.com/engine/install/ubuntu/), [Debian](https://docs.docker.com/engine/install/debian/), and [Fedora](https://docs.docker.com/engine/install/fedora/) repository instructions below. The installer only checks that `docker` and Compose commands are available.

```bash
# Arch Linux
sudo pacman -S --needed git python python-yaml docker docker-compose sudo curl openssl pamtester
```

```bash
# Ubuntu: add Docker's official apt repository, then install Engine and Compose.
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin git python3 python3-yaml sudo openssl pamtester
sudo systemctl enable --now docker
```

```bash
# Debian: use Docker's Debian apt repository (not Ubuntu's).
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin git python3 python3-yaml sudo openssl pamtester
sudo systemctl enable --now docker
```

```bash
# Fedora: add Docker's official RPM repository, then install Engine and Compose.
sudo dnf config-manager addrepo --from-repofile https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin git python3 python3-pyyaml sudo curl openssl pamtester
sudo systemctl enable --now docker
```

For explicit model setup, also provide a working NVIDIA driver exposed through `nvidia-smi`, `sha256sum`, and an externally installed `hf` or `huggingface-cli`. These are checked only when `CLUB3090_SETUP_MODEL` is supplied. Optional features may require Caddy and Tailscale, Xorg and `nvidia-settings` for fan control, `cpupower`, `ntfs-3g`, compiler/libpci dependencies for the temperature helper, and Hugging Face CLI for AI Studio downloads. Install only dependencies for features you use.

To opt in to junction/VRAM temperature telemetry, install `gcc`, the libpci development package, and NVIDIA Management Library linker package using your distribution package manager, then run `sudo env CLUB3090_ENABLE_EXTRA_TEMPS=1 ./install.sh`. The helper is compiled from `src/build/vendor/gputemps.c` and `src/build/vendor/nvml.h` into the runtime data directory; no source is copied out of this checkout. The installer does not edit bootloader configuration. If the helper reports that its readings require `iomem=relaxed`, configure that kernel option manually and reboot.

## Install

Clone this repository and upstream runtime, then install:

```bash
git clone https://github.com/noonghunna/club-3090-server.git
cd club-3090-server
git clone https://github.com/noonghunna/club-3090.git
sudo ./install.sh
```

To provision a model during installation:

```bash
sudo env CLUB3090_SETUP_MODEL=qwen3.6-27b HF_TOKEN=hf_xxx ./install.sh
```

This invokes the existing upstream `scripts/setup.sh` from the supplied checkout. Upstream setup variables such as `MODEL_DIR`, `WEIGHTS`, and `WITH_DFLASH_DRAFT=1` pass through unchanged. The installer never installs packages, clones or updates either checkout, or embeds/copies application code.

For an upstream checkout at another path:

```bash
sudo env CLUB3090_DIR=/absolute/path/to/club-3090 ./install.sh
```

The checkout must remain at the installed path: systemd services execute the Python modules, scripts, and web assets directly from it. The installer registers systemd units and stores the service environment in `/etc/club3090-server.env`; mutable runtime data defaults to `/var/lib/club3090-control` and can be redirected with `CLUB3090_CONTROL_DIR`.

Successful installation starts the control, updater, and vLLM services. In AI Studio, each inference runtime row's **Start this inference runtime automatically at boot** checkbox controls whether that runtime starts on subsequent boots. Verify with `systemctl is-active club3090-control.service`, `systemctl is-active club3090-updater.service`, and `systemctl is-active club3090-vllm.service`; inspect the installed unit with `systemctl cat club3090-control.service`. For service operations see [Operations](OPERATIONS.md).

## Uninstall

From the repository checkout, run:

```bash
sudo ./uninstall.sh
```

This removes the registered units and `/etc/club3090-server.env`. It deliberately leaves the source checkout and mutable runtime data intact. It never removes dependency packages.
