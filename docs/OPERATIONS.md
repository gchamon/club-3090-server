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

The Model DB lists four instance-scoped Strata presets for Qwen3.8-Flash-Next (`Q2_0`, `IQ2_XS`, `IQ3_XXS`, and `IQ3_S`). Install the pinned Strata runtime from the preset card, then select and start a preset in **Instances**. The shared runtime image and source checkout are installed once; each size keeps its own persistent data directory. Stop or remove an instance from **Instances**; generic model-resource and cache deletion do not apply to Strata.

Strata requires Linux, Docker with either the NVIDIA runtime or a discovered NVIDIA CDI GPU device, a working `nvidia-smi`, NVIDIA driver 580 or newer, and a GPU with compute capability 7.5, 8.0, 8.6, 8.9, or 12.0. The hardware-blocked preset list reports failed prerequisites. Combined RAM+VRAM figures on the cards are upstream fit guidance, not launch thresholds.

OpenAI-compatible requests can target a running Strata preset with `http://HOST:8009/v1/strata/<preset>/models` or `http://HOST:8009/strata/<preset>/models`; Chat Completions use the same prefixes. A Strata request returns HTTP 503 when no ready matching instance is running. Start it from **Instances**.

## Updating

Use **System Update** in the admin panel to fast-forward both the Club-3090 Server checkout and the configured upstream `club-3090` checkout. The updater requires both worktrees to be clean and on branches with configured upstreams; it stops before fetching or merging if either checkout has local changes or is not tracking a branch. It never resets or stashes user changes. For a rejected dirty checkout, inspect it with `git -C /path/to/checkout status`, resolve the changes or commit/stash them locally, then retry.

The updater runs Git as each worktree's filesystem owner, preserving that account's Git and SSH configuration. It fetches both origins, merges only with `--ff-only`, rebuilds the Model DB from the updated server and upstream sources, then runs `install.sh` to refresh service registration and restart services. System Update is not an automatic background update. The admin panel selects Audit Logs when an update starts and keeps the updater status monitor running through its restart; the Logs tab remains usable to switch sources, export or copy displayed logs, and download the log archive while the update runs. Updater output is mirrored to the audit log. Admin tabs use `/admin` for Overview and `/admin/{tab-name}` for other sections; tab subcategories remain in the query string. Completion requires the control service and admin HTTP endpoint to become ready.

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
