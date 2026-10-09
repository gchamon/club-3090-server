# Operations

## Services and checks

Inspect the registered unit and service state with systemd:

```bash
systemctl cat club3090-control.service
sudo systemctl status club3090-control.service
sudo systemctl start club3090-control.service
```

After starting the control service, check the admin route in a browser at `http://HOST:8008/admin` and test the proxy with:

```bash
curl http://HOST:8009/v1/models
```

Use systemd's journal to inspect service output, for example `journalctl -u club3090-control.service`. Services execute directly from the repository checkout, so do not move or remove the checkout while they are installed.

## Strata presets

The Model DB lists instance-scoped Strata presets. Install the pinned Strata runtime from a preset card, then select and start a preset in **Instances**. The shared runtime image and source checkout are installed once; each preset keeps its persistent model data, prepared pack, MTP tensors, and setup config at `${MODEL_DIR}/strata-<preset>`. Generated Compose files and the shared source checkout stay below `${CLUB3090_CONTROL_DIR}/builtin-models`. Stop or remove an instance from **Instances**; generic model-resource and cache deletion do not apply to Strata.
Controller-managed Strata presets are prepared for the model's trained 262,144-token context (over 200K); this is a configured maximum, not a promise that every host can run it efficiently. The server clamps an oversized requested completion to the remaining context instead of rejecting an otherwise valid prompt. Existing preset data keeps its previous context until refreshed: after updating the controller, use **Install** on each existing Strata preset, then restart it from **Instances**. Confirm the active capacity at `/v1/strata/<preset>/models` in the returned model's `meta.n_ctx`.


After upgrading from a version that stored Strata data in the control directory, stop all Strata instances and any Strata model-install jobs. Set `CONTROL_DIR` to the host’s configured `CLUB3090_CONTROL_DIR` (default `/var/lib/club3090-control`) and `MODEL_DIR` to the same absolute model root used by the controller. The command below moves only existing per-preset `data` directories, preserves the generated Compose files and source checkout, refuses non-empty destination conflicts, and tolerates empty destination directories created during inventory rebuild:

```bash
CONTROL_DIR=/var/lib/club3090-control
MODEL_DIR=/media/fast-storage/club-3090-models
sudo env CONTROL_DIR="$CONTROL_DIR" MODEL_DIR="$MODEL_DIR" bash -euo pipefail -c '
shopt -s nullglob
mkdir -p "$MODEL_DIR"
for source in "$CONTROL_DIR"/builtin-models/strata-*/data; do
  [ -d "$source" ] || continue
  target="$MODEL_DIR/$(basename "$(dirname "$source")")"
  if [ -e "$target" ] && { [ ! -d "$target" ] || [ -n "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit)" ]; }; then
    printf "refusing non-empty destination: %s\n" "$target" >&2
    exit 1
  fi
done
for source in "$CONTROL_DIR"/builtin-models/strata-*/data; do
  [ -d "$source" ] || continue
  target="$MODEL_DIR/$(basename "$(dirname "$source")")"
  [ ! -d "$target" ] || rmdir "$target"
  mv -- "$source" "$target"
done
'
```

After it completes, rebuild runtime inventory or restart `club3090-control.service`, then start the presets from **Instances**. If the command refuses a non-empty destination, compare both directories and preserve the complete data before retrying; do not delete either copy blindly.

Strata requires Linux, Docker with either the NVIDIA runtime or a discovered NVIDIA CDI GPU device, a working `nvidia-smi`, NVIDIA driver 580 or newer, and a GPU with compute capability 7.5, 8.0, 8.6, 8.9, or 12.0. The hardware-blocked preset list reports failed prerequisites. Combined RAM+VRAM figures on the cards are upstream fit guidance, not launch thresholds.

OpenAI-compatible requests can target a running Strata preset with `http://HOST:8009/v1/strata/<preset>/models` or `http://HOST:8009/strata/<preset>/models`; Chat Completions use the same prefixes. A Strata request returns HTTP 503 when no ready matching instance is running. Start it from **Instances**.

## Updating

Use **System Update** in the admin panel to fast-forward both the Club-3090 Server checkout and the configured upstream `club-3090` checkout. The updater requires both worktrees to be clean and on branches with configured upstreams; it stops before fetching or merging if either checkout has local changes or is not tracking a branch. It never resets or stashes user changes. For a rejected dirty checkout, inspect it with `git -C /path/to/checkout status`, resolve the changes or commit/stash them locally, then retry.

The updater runs Git as each worktree's filesystem owner, preserving that account's Git and SSH configuration. It fetches both origins, merges only with `--ff-only`, rebuilds the Model DB from the updated server and upstream sources, then runs `install.sh` to refresh service registration and queue service starts without waiting for them to become active. The updater reports completion after the control plane returns. The admin UI then monitors `club3090-vllm.service` for up to one minute and unlocks the panel if inference is still starting; inspect `systemctl status club3090-vllm.service` and `journalctl -u club3090-vllm.service` for its startup state. System Update is not an automatic background update. The admin panel selects Audit Logs when an update starts and keeps the updater status monitor running through its restart; the Logs tab remains usable to switch sources, export or copy displayed logs, and download the log archive while the update runs. Updater output is mirrored to the audit log. Admin tabs use `/admin` for Overview and `/admin/{tab-name}` for other sections; tab subcategories remain …

## Troubleshooting

- If installation reports missing prerequisites, install the named commands/modules with your distribution package manager, then run `sudo ./install.sh` again.
- If the upstream checkout is not found, set `CLUB3090_DIR` to its existing absolute path.
- Check `systemctl cat club3090-control.service` to verify the service points to the expected checkout and configured environment file (default `/etc/club3090-server.env`).
- Check the service journal and confirm the configured mutable data directory is writable and has sufficient space.

## Uninstallation

Run the repository's root uninstaller:

```bash
sudo ./uninstall.sh
```

It removes registered service units and `/etc/club3090-server.env`, while keeping the repository checkout and mutable runtime data intact. Dependency packages remain installed; uninstallation does not remove them. Preserve or remove runtime data separately according to your retention needs.

See [Removed Model Manager](removed-model-manager.md) for remaining model-resource cleanup controls and their effect on shared assets.
