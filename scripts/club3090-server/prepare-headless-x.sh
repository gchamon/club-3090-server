#!/usr/bin/env bash
set -euo pipefail

CONFIG="${CLUB3090_HEADLESS_XORG_CONFIG:-/etc/X11/club3090-headless-xorg.conf}"
DISPLAY_NUM="${CLUB3090_FAN_DISPLAY_NUM:-99}"
LOGFILE="${CLUB3090_HEADLESS_XORG_LOG:-/var/log/club3090-headless-xorg.log}"

command -v /usr/bin/Xorg >/dev/null 2>&1 || { echo "Xorg is required for fan control" >&2; exit 1; }
install -d -m 0755 "$(dirname "${CONFIG}")" "$(dirname "${LOGFILE}")"

if command -v nvidia-xconfig >/dev/null 2>&1; then
  nvidia-xconfig \
    --enable-all-gpus \
    --cool-bits=28 \
    --allow-empty-initial-configuration \
    --use-display-device=None \
    --virtual=1280x720 \
    --xconfig="${CONFIG}" >/tmp/club3090-nvidia-xconfig.log 2>&1 || true
fi

if [[ ! -s "${CONFIG}" ]]; then
  cat >"${CONFIG}" <<'XCONF'
Section "ServerLayout"
    Identifier "club3090-headless"
    Screen 0 "Screen0"
EndSection

Section "Device"
    Identifier "Device0"
    Driver "nvidia"
    Option "AllowEmptyInitialConfiguration" "true"
    Option "Coolbits" "28"
    Option "UseDisplayDevice" "None"
EndSection

Section "Screen"
    Identifier "Screen0"
    Device "Device0"
    Option "AllowEmptyInitialConfiguration" "true"
    Option "UseDisplayDevice" "None"
    SubSection "Display"
        Virtual 1280 720
    EndSubSection
EndSection
XCONF
fi

exec /usr/bin/Xorg ":${DISPLAY_NUM}" \
  -config "${CONFIG}" -noreset -nolisten tcp -ac -novtswitch -sharevts \
  +extension GLX +extension RANDR +extension RENDER -logfile "${LOGFILE}"
