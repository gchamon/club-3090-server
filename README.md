# Club-3090 Server

Club-3090 Server is the management layer for the upstream [club-3090](https://github.com/noonghunna/club-3090) inference runtime. It provides a browser admin panel at `:8008/admin` and an OpenAI-compatible proxy at `:8009/v1`; the upstream project supplies the model runtime.

## Quickstart

Install the base prerequisites manually before cloning. The installer checks dependencies but does not install packages. Docker must be enabled and configured according to your distribution.
Use Docker's official [Ubuntu](https://docs.docker.com/engine/install/ubuntu/), [Debian](https://docs.docker.com/engine/install/debian/), or [Fedora](https://docs.docker.com/engine/install/fedora/) repository instructions below. The installer only checks that `docker` and Compose commands are available.

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

Clone both repositories, placing the upstream checkout at `club-3090` beside this repository, or set `CLUB3090_DIR` to its location:

```bash
git clone https://github.com/noonghunna/club-3090-server.git
cd club-3090-server
git clone https://github.com/noonghunna/club-3090.git
sudo ./install.sh
```

To provision a model during installation, use:

```bash
sudo env CLUB3090_SETUP_MODEL=qwen3.6-27b HF_TOKEN=hf_xxx ./install.sh
```

Without `CLUB3090_SETUP_MODEL`, installation registers the server without downloading model assets. With it, the installer invokes the existing upstream `scripts/setup.sh` from the supplied checkout; upstream variables such as `MODEL_DIR`, `WEIGHTS`, and `WITH_DFLASH_DRAFT=1` pass through unchanged. The installer never installs packages or clones/updates either checkout, and does not embed or copy application code.

Successful installation starts the control, updater, and vLLM services, then waits up to 60 seconds for all three to report `active` through systemd; a timeout reports inactive units. In AI Studio, use each inference runtime row's **Start this inference runtime automatically at boot** checkbox to control whether that runtime starts on subsequent boots. Verify service state with `systemctl is-active club3090-control.service`, `systemctl is-active club3090-updater.service`, and `systemctl is-active club3090-vllm.service`; inspect the installed control unit with `systemctl cat club3090-control.service` and test the proxy with `curl http://HOST:8009/v1/models`.

Open `http://HOST:8008/admin` in a browser, substituting the server host for `HOST`. The services execute code and assets directly from this checkout; keep it in place while installed. `/etc/club3090-server.env` contains service configuration and `${CLUB3090_CONTROL_DIR:-/var/lib/club3090-control}` is the mutable runtime-data location.

To remove service registration, run `sudo ./uninstall.sh`. It removes the registered units and `/etc/club3090-server.env`; it leaves this source checkout and runtime data intact and does not uninstall dependency packages. See [Uninstallation](docs/OPERATIONS.md#uninstallation).
